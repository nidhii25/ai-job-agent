import base64
import binascii
import ipaddress
import json
import logging
import os
import socket
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

# Allow running the backend from any working directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Load local-only settings (including API keys) before importing modules that
# read environment variables. backend/.env is gitignored.
from dotenv import load_dotenv

load_dotenv(os.path.join(BASE_DIR, ".env"))

from logging_config import configure_logging, log_file_path

configure_logging()
logger = logging.getLogger("jobagent.api")

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from automation.runner import run_application
from resume_parser import (
    ResumeParseError,
    ResumeProfileExtractor,
    empty_resume_profile,
    extract_document_text,
    extract_resume_text,
)
from storage import (
    DB_PATH,
    EXPORT_PATH,
    PROFILE_PATH,
    add_event,
    get_connection,
    init_db,
    load_profile,
    refresh_applications_export,
    resolve_review_item,
    save_profile,
    utc_now,
    write_applications_export,
)

app = FastAPI(title="Personal AI Job Application Agent")

# ---- Configuration ----

UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads"))
TEST_FORM_PATH = os.path.join(BASE_DIR, "test_form.html")
ALLOWED_RESUME_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".rtf"}
MAX_RESUME_BYTES = 10 * 1024 * 1024  # 10 MB
STARTED_AT = datetime.now(timezone.utc).isoformat()


def env_bool(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


ALLOW_LOCAL_URLS = env_bool("ALLOW_LOCAL_URLS", False)

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
try:
    write_applications_export()
except Exception as exc:
    logger.warning("Could not create the initial applications export: %s", exc)

# ---- Request Models ----


class ApplicationCreate(BaseModel):
    job_url: str
    auto_submit: bool | None = None


class ResumeUpload(BaseModel):
    filename: str
    content_base64: str


class ReviewResolution(BaseModel):
    resolution: str


class ManualSubmissionUpdate(BaseModel):
    details: str = ""


class ApplicationResume(BaseModel):
    auto_submit: bool | None = None


# ---- URL Validation ----


def _is_local_host(hostname):
    if not hostname:
        return False
    if hostname.lower() in ("localhost", "localhost.localdomain"):
        return True
    try:
        addresses = {
            item[4][0] for item in socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        }
    except OSError:
        return False

    for address in addresses:
        try:
            ip = ipaddress.ip_address(address.split("%")[0])
        except ValueError:
            continue
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return True
    return False


def validate_job_url(job_url):
    parsed = urlparse(job_url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail="Invalid URL. Must start with http:// or https://",
        )
    if not parsed.netloc or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Invalid URL. Host is missing.")

    if (
        parsed.hostname.lower() == "my.greenhouse.io"
        and parsed.path.lower().startswith("/jobs/search")
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "MyGreenhouse search links are not application forms. "
                "Open a specific job and paste its Greenhouse job-board link instead."
            ),
        )

    if not ALLOW_LOCAL_URLS and _is_local_host(parsed.hostname):
        raise HTTPException(
            status_code=400,
            detail=(
                "Local and private network URLs are blocked. "
                "Set ALLOW_LOCAL_URLS=true only for local testing."
            ),
        )


# ---- API Endpoints ----


@app.get("/api/health")
def health_check():
    ai_provider = os.getenv("AI_PROVIDER", "gemini").strip().lower()
    ai_enabled = (
        os.getenv("AI_ENABLED", "true").strip().lower()
        in ("1", "true", "yes", "on")
        and ai_provider == "gemini"
        and bool(os.getenv("GEMINI_API_KEY", "").strip())
    )
    return {
        "status": "healthy",
        "message": "Backend is running",
        "started_at": STARTED_AT,
        "allow_local_urls": ALLOW_LOCAL_URLS,
        "auto_submit": env_bool("AUTO_SUBMIT", True),
        "database": DB_PATH,
        "applications_export": EXPORT_PATH,
        "log_file": log_file_path(),
        "ai_enabled": ai_enabled,
        "ai_provider": ai_provider,
        "ai_model": os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
    }


@app.get("/api/profile")
def read_profile():
    return {"status": "success", "data": load_profile()}


@app.put("/api/profile")
def save_profile_endpoint(profile: dict):
    if not isinstance(profile, dict):
        raise HTTPException(status_code=400, detail="Profile must be a JSON object")
    save_profile(profile)
    logger.info("Profile saved")
    return {"status": "success", "message": "Profile saved successfully"}


def _store_resume_upload(payload):
    """Validate and store one uploaded resume, returning name, path, and bytes."""
    safe_name = os.path.basename(payload.filename or "").strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="Filename is required")

    extension = os.path.splitext(safe_name)[1].lower()
    if extension not in ALLOWED_RESUME_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_RESUME_EXTENSIONS))}",
        )

    try:
        raw = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="File content is not valid base64")

    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(raw) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=400, detail="Resume must be 10 MB or smaller")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    stored_name = f"{stamp}_{safe_name}"
    stored_path = os.path.join(UPLOAD_DIR, stored_name)

    with open(stored_path, "wb") as handle:
        handle.write(raw)

    return safe_name, stored_path, raw


@app.post("/api/profile/resume")
def upload_resume(payload: ResumeUpload):
    """Store a resume locally and save its path in the profile."""
    _, stored_path, _ = _store_resume_upload(payload)

    profile = load_profile()
    profile["resume_path"] = stored_path
    save_profile(profile)
    logger.info("Resume uploaded")

    return {
        "status": "success",
        "message": "Resume uploaded successfully",
        "resume_path": stored_path,
    }


@app.post("/api/profile/resume/prefill")
def prefill_profile_from_resume(payload: ResumeUpload):
    """Store a resume, extract facts, and return them for user review."""
    safe_name, stored_path, raw = _store_resume_upload(payload)

    profile = load_profile()
    profile["resume_path"] = stored_path
    save_profile(profile)

    try:
        text = extract_resume_text(safe_name, raw)
        extraction = ResumeProfileExtractor().extract(text)
        extracted_profile = extraction.profile
        fields_found = extraction.fields_found
        warnings = extraction.warnings
        ai_used = extraction.ai_used
        text_chars = extraction.text_chars
    except ResumeParseError as exc:
        logger.info("Resume prefill could not parse text: %s", exc)
        extracted_profile = empty_resume_profile()
        fields_found = 0
        warnings = [str(exc)]
        ai_used = False
        text_chars = 0
    except Exception as exc:
        logger.exception("Resume prefill failed")
        extracted_profile = empty_resume_profile()
        fields_found = 0
        warnings = [f"Resume parsing failed: {exc}"]
        ai_used = False
        text_chars = 0

    logger.info(
        "Resume prefill completed: fields=%s ai_used=%s warnings=%s",
        fields_found,
        ai_used,
        len(warnings),
    )
    return {
        "status": "success",
        "message": "Resume uploaded and profile extraction completed",
        "resume_path": stored_path,
        "profile": extracted_profile,
        "fields_found": fields_found,
        "warnings": warnings,
        "ai_used": ai_used,
        "text_chars": text_chars,
    }


@app.post("/api/profile/cover-letter")
def upload_cover_letter(payload: ResumeUpload):
    """Store a cover letter file and extract its text into the profile."""
    safe_name, stored_path, raw = _store_resume_upload(payload)

    profile = load_profile()
    profile["cover_letter_path"] = stored_path
    warnings = []
    try:
        cover_letter_text = extract_document_text(
            safe_name, raw, label="cover letter"
        )
        if len(cover_letter_text) > 20000:
            cover_letter_text = cover_letter_text[:20000]
            warnings.append(
                "Cover letter text was truncated to 20,000 characters."
            )
        profile["cover_letter"] = cover_letter_text
    except ResumeParseError as exc:
        logger.info("Cover letter text extraction failed: %s", exc)
        warnings.append(str(exc))
    except Exception as exc:
        logger.exception("Cover letter text extraction failed")
        warnings.append(f"Cover letter parsing failed: {exc}")

    save_profile(profile)
    logger.info(
        "Cover letter uploaded: text_chars=%s warnings=%s",
        len(profile.get("cover_letter") or ""),
        len(warnings),
    )
    return {
        "status": "success",
        "message": "Cover letter uploaded",
        "cover_letter_path": stored_path,
        "cover_letter": profile.get("cover_letter") or "",
        "warnings": warnings,
    }


@app.post("/api/applications")
def create_application(payload: ApplicationCreate, background_tasks: BackgroundTasks):
    """Create a new application record and start the browser automation."""
    job_url = (payload.job_url or "").strip()
    validate_job_url(job_url)

    auto_submit = (
        payload.auto_submit
        if payload.auto_submit is not None
        else env_bool("AUTO_SUBMIT", True)
    )

    conn = get_connection()
    cursor = conn.cursor()
    now = utc_now()

    cursor.execute(
        """
        INSERT INTO applications
            (job_url, company, role, status, created_at, updated_at, auto_submit)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (job_url, "", "", "In Progress", now, now, 1 if auto_submit else 0),
    )
    application_id = cursor.lastrowid
    add_event(
        cursor,
        application_id,
        "application_created",
        f"Application created for URL: {job_url}",
    )
    add_event(
        cursor,
        application_id,
        "submission_mode",
        (
            "Automatic submission is enabled; the agent will submit after a "
            "complete fill with no unresolved review items."
            if auto_submit
            else "Fill-only mode is enabled; the agent will fill the form and "
            "stop for review before submission."
        ),
    )
    conn.commit()
    refresh_applications_export(conn)
    conn.close()
    logger.info(
        "Application created: id=%s auto_submit=%s url=%s",
        application_id,
        auto_submit,
        job_url,
    )

    background_tasks.add_task(run_application, application_id, job_url)

    return {
        "status": "success",
        "application_id": application_id,
        "application_status": "In Progress",
        "auto_submit": auto_submit,
    }


@app.get("/api/applications")
def list_applications(status: str = None):
    conn = get_connection()
    cursor = conn.cursor()

    if status:
        cursor.execute(
            """
            SELECT id, job_url, company, role, status, created_at, updated_at,
                   submitted_at, last_error, submission_attempted_at,
                   submission_outcome
            FROM applications WHERE status = ?
            ORDER BY created_at DESC
            """,
            (status,),
        )
    else:
        cursor.execute(
            """
            SELECT id, job_url, company, role, status, created_at, updated_at,
                   submitted_at, last_error, submission_attempted_at,
                   submission_outcome
            FROM applications ORDER BY created_at DESC
            """
        )

    applications = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"status": "success", "data": applications}


@app.get("/api/applications/export")
def export_applications():
    """Download the atomic JSON snapshot generated from SQLite."""
    try:
        export_path = write_applications_export()
    except Exception as exc:
        logger.exception("Applications export failed")
        raise HTTPException(
            status_code=500,
            detail=f"Could not create the applications JSON export: {exc}",
        )
    logger.info("Applications export downloaded")
    return FileResponse(
        export_path,
        media_type="application/json",
        filename="applications.json",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/api/applications/{application_id}")
def read_application(application_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, job_url, company, role, status, created_at, updated_at,
               submitted_at, last_error, confirmation_details,
               submission_attempted_at, submission_outcome
        FROM applications WHERE id = ?
        """,
        (application_id,),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Application not found")

    application = dict(row)

    cursor.execute(
        """
        SELECT id, event_type, message, created_at
        FROM application_events WHERE application_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (application_id,),
    )
    application["events"] = [dict(row) for row in cursor.fetchall()]

    cursor.execute(
        """
        SELECT id, field_name, reason, suggested_value, user_resolution, resolved_at
        FROM review_items WHERE application_id = ?
        ORDER BY id ASC
        """,
        (application_id,),
    )
    application["review_items"] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return {"status": "success", "data": application}


@app.delete("/api/applications/{application_id}")
def delete_application(application_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM applications WHERE id = ?", (application_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Application not found")

    cursor.execute("DELETE FROM applications WHERE id = ?", (application_id,))
    conn.commit()
    refresh_applications_export(conn)
    conn.close()
    logger.info("Application deleted: id=%s", application_id)
    return {"status": "success", "message": "Application deleted"}


@app.post("/api/applications/{application_id}/review-items/{item_id}/resolve")
def resolve_item(
    application_id: int, item_id: int, payload: ReviewResolution
):
    """Store the user's answer for one review item."""
    resolution = (payload.resolution or "").strip()
    if not resolution:
        raise HTTPException(status_code=400, detail="A resolution is required")
    if len(resolution) > 4000:
        raise HTTPException(
            status_code=400, detail="Resolution must be 4000 characters or fewer"
        )

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status FROM applications WHERE id = ?", (application_id,)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Application not found")
    if row["status"] != "Needs Review":
        current = row["status"]
        conn.close()
        raise HTTPException(
            status_code=409,
            detail=f"Application is {current}; review items cannot be changed",
        )

    resolved = resolve_review_item(
        conn, application_id, item_id, resolution
    )
    conn.close()
    if not resolved:
        raise HTTPException(status_code=404, detail="Review item not found")
    return {"status": "success", "data": resolved}


@app.post("/api/applications/{application_id}/resume")
def resume_application(
    application_id: int,
    background_tasks: BackgroundTasks,
    payload: ApplicationResume | None = None,
):
    """Resume an application after its review items have been answered."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT status, job_url, submission_attempted_at, submission_outcome
        FROM applications WHERE id = ?
        """,
        (application_id,),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Application not found")

    if row["status"] != "Needs Review":
        current = row["status"]
        conn.close()
        raise HTTPException(
            status_code=409,
            detail=f"Application is {current}, cannot resume",
        )

    if row["submission_outcome"] in ("pending", "uncertain", "confirmed"):
        conn.close()
        raise HTTPException(
            status_code=409,
            detail=(
                "A submission was already attempted for this application. "
                "Verify the employer site and use the manual confirmation action "
                "before trying again."
            ),
        )

    cursor.execute(
        """
        SELECT COUNT(*) AS total FROM review_items
        WHERE application_id = ? AND resolved_at IS NULL
        """,
        (application_id,),
    )
    unresolved = cursor.fetchone()["total"]
    if unresolved:
        conn.close()
        raise HTTPException(
            status_code=409,
            detail=(
                f"{unresolved} review item(s) are unresolved. "
                "Answer them before resuming."
            ),
        )

    job_url = row["job_url"]
    now = utc_now()
    auto_submit = payload.auto_submit if payload is not None else None

    if auto_submit is not None:
        cursor.execute(
            """
            UPDATE applications
            SET status = 'In Progress', updated_at = ?, last_error = NULL,
                auto_submit = ?
            WHERE id = ?
            """,
            (now, 1 if auto_submit else 0, application_id),
        )
    else:
        cursor.execute(
            """
            UPDATE applications
            SET status = 'In Progress', updated_at = ?, last_error = NULL
            WHERE id = ?
            """,
            (now, application_id),
        )

    add_event(cursor, application_id, "resume", "Application resumed after review")
    if auto_submit is not None:
        add_event(
            cursor,
            application_id,
            "submission_mode",
            (
                "Automatic submission enabled for this resumed run."
                if auto_submit
                else "Fill-only mode enabled for this resumed run."
            ),
        )
    conn.commit()
    refresh_applications_export(conn)
    conn.close()
    logger.info(
        "Application resumed: id=%s auto_submit=%s",
        application_id,
        auto_submit,
    )

    background_tasks.add_task(run_application, application_id, job_url)
    return {
        "status": "success",
        "message": "Application resumed",
        "application_status": "In Progress",
        "auto_submit": auto_submit,
    }


@app.post("/api/applications/{application_id}/confirm-submission")
def confirm_submission(
    application_id: int, payload: ManualSubmissionUpdate
):
    """Record a submission the user verified manually after an unclear result."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT status, submission_outcome FROM applications WHERE id = ?
        """,
        (application_id,),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Application not found")
    if row["status"] != "Needs Review" or row["submission_outcome"] not in (
        "pending",
        "uncertain",
    ):
        conn.close()
        raise HTTPException(
            status_code=409,
            detail="This application is not awaiting manual submission verification",
        )

    now = utc_now()
    details = {
        "signal": "manual",
        "message": (payload.details or "Manually verified by the user.")[:800],
        "verified_at": now,
    }
    cursor.execute(
        """
        UPDATE applications
        SET status = 'Submitted', submitted_at = ?, submission_outcome = 'confirmed',
            confirmation_details = ?, last_error = NULL, updated_at = ?
        WHERE id = ?
        """,
        (now, json.dumps(details), now, application_id),
    )
    add_event(
        cursor,
        application_id,
        "submission_confirmed_manually",
        "User manually confirmed the application was submitted.",
    )
    conn.commit()
    refresh_applications_export(conn)
    conn.close()
    logger.info("Submission manually confirmed: id=%s", application_id)
    return {"status": "success", "message": "Submission marked as confirmed"}


@app.post("/api/applications/{application_id}/mark-not-submitted")
def mark_not_submitted(
    application_id: int, payload: ManualSubmissionUpdate
):
    """Allow a resubmission only after the user says it was not submitted."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status, submission_outcome FROM applications WHERE id = ?",
        (application_id,),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Application not found")
    if row["status"] != "Needs Review" or row["submission_outcome"] not in (
        "pending",
        "uncertain",
    ):
        conn.close()
        raise HTTPException(
            status_code=409,
            detail="This application is not awaiting manual submission verification",
        )

    now = utc_now()
    cursor.execute(
        """
        UPDATE applications
        SET status = 'Needs Review', submission_outcome = 'rejected',
            last_error = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            (payload.details or "User verified the application was not submitted.")[
                :2000
            ],
            now,
            application_id,
        ),
    )
    add_event(
        cursor,
        application_id,
        "submission_marked_not_submitted",
        "User verified the application was not submitted; resubmission is allowed.",
    )
    conn.commit()
    refresh_applications_export(conn)
    conn.close()
    logger.info("Application marked as not submitted: id=%s", application_id)
    return {"status": "success", "message": "Application marked as not submitted"}


@app.post("/api/applications/{application_id}/retry")
def retry_application(application_id: int, background_tasks: BackgroundTasks):
    """Retry a failed application by running the automation again."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT status, job_url FROM applications WHERE id = ?", (application_id,)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Application not found")

    if row["status"] != "Failed":
        current = row["status"]
        conn.close()
        raise HTTPException(
            status_code=409,
            detail=f"Application is {current}, retry not supported",
        )

    job_url = row["job_url"]
    now = utc_now()
    cursor.execute(
        """
        UPDATE applications
        SET status = 'In Progress', updated_at = ?, last_error = NULL,
            submitted_at = NULL, submission_attempted_at = NULL,
            submission_outcome = NULL, confirmation_details = NULL
        WHERE id = ?
        """,
        (now, application_id),
    )
    add_event(cursor, application_id, "retry", "Application retry initiated")
    conn.commit()
    refresh_applications_export(conn)
    conn.close()
    logger.info("Application retry initiated: id=%s", application_id)

    background_tasks.add_task(run_application, application_id, job_url)
    return {
        "status": "success",
        "message": "Retry initiated",
        "application_status": "In Progress",
    }


@app.get("/api/applications/{application_id}/events")
def get_events(application_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, event_type, message, created_at
        FROM application_events WHERE application_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (application_id,),
    )
    events = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"status": "success", "data": events}


# ---- Local Greenhouse-shaped test form (no submission) ----


@app.get("/test/greenhouse", response_class=HTMLResponse)
def greenhouse_test_form():
    if not os.path.isfile(TEST_FORM_PATH):
        raise HTTPException(status_code=404, detail="Test form not found")
    return FileResponse(
        TEST_FORM_PATH,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/test/not-a-form", response_class=HTMLResponse)
def not_a_form_page():
    return """
    <!doctype html>
    <html><head><title>Not an application</title></head>
    <body><h1>Example article page</h1><p>There is no application form here.</p></body></html>
    """


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
