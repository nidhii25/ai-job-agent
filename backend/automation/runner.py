"""Orchestrates a single application run using Playwright."""

import json
import logging
import os
import threading
import time
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from automation.ai_mapper import build_ai_mapper
from automation.browser import open_browser_page
from automation.greenhouse import (
    AutomationError,
    click_submit,
    collect_submission_errors,
    fill_application,
    find_submit_button,
    has_greenhouse_form,
    is_login_wall,
    read_job_meta,
    reveal_form_if_needed,
    wait_for_confirmation,
    wait_for_form,
    wait_for_submission_signal,
)
from storage import (
    create_review_item,
    get_connection,
    load_profile,
    load_resolved_answers,
    record_event,
    update_application,
    utc_now,
)

logger = logging.getLogger("jobagent.runner")
RUN_LOCK = threading.Lock()

SUPPORTED_SUBMISSION_HOSTS = {
    "greenhouse.io",
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "localhost",
    "127.0.0.1",
}


def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _is_headless():
    return os.getenv("BROWSER_HEADLESS", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _auto_submit_enabled(application_setting=None):
    if application_setting is not None:
        return bool(application_setting)
    return os.getenv("AUTO_SUBMIT", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _fail(conn, application_id, message):
    try:
        row = conn.execute(
            "SELECT submission_outcome FROM applications WHERE id = ?",
            (application_id,),
        ).fetchone()
        if row and row["submission_outcome"] == "pending":
            # A crash after the submit click is an uncertain outcome, not a
            # safe failure to retry. Keep it in review and block resubmission.
            update_application(
                conn,
                application_id,
                status="Needs Review",
                submission_outcome="uncertain",
                last_error=(
                    f"{message} The submission outcome is uncertain; verify the "
                    "employer site before trying again."
                )[:2000],
            )
            record_event(
                conn,
                application_id,
                "submission_uncertain",
                "Run interrupted after the submit click; outcome not confirmed.",
            )
            return
        update_application(
            conn,
            application_id,
            status="Failed",
            last_error=message[:2000],
        )
        record_event(conn, application_id, "failed", message)
    except Exception:
        logger.exception("Failed to store failure for application=%s", application_id)


def _wait_for_manual_login(page, conn, application_id, timeout_seconds):
    """Pause while the user signs in manually in the visible browser.

    The agent deliberately does not read, request, or automate email/OTP codes.
    """
    record_event(
        conn,
        application_id,
        "login_required",
        "The site is asking for manual sign-in. Complete it in the visible browser; "
        "the agent is waiting and will never handle your code.",
    )
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if has_greenhouse_form(page):
            record_event(
                conn,
                application_id,
                "login_completed",
                "Manual sign-in completed; continuing the application.",
            )
            return True
        reveal_form_if_needed(page)
        if has_greenhouse_form(page):
            record_event(
                conn,
                application_id,
                "login_completed",
                "Manual sign-in completed; continuing the application.",
            )
            return True
        try:
            page.wait_for_timeout(1000)
        except Exception:
            return False
    return False


def _submission_host_supported(page):
    host = (urlparse(page.url).hostname or "").lower()
    return host in SUPPORTED_SUBMISSION_HOSTS


def run_application(application_id, job_url):
    """Background entry point. Never raises; failures are stored on the record.

    Playwright runs are serialized: this is a local single-user agent, and
    overlapping visible browsers make observation and cleanup unreliable.
    """
    with RUN_LOCK:
        _run_application_locked(application_id, job_url)


def _run_application_locked(application_id, job_url):
    logger.info("Run started application=%s url=%s", application_id, job_url)
    conn = get_connection()
    try:
        record_event(
            conn,
            application_id,
            "run_started",
            "Starting browser automation.",
        )
        profile = load_profile()
        application_row = conn.execute(
            "SELECT auto_submit FROM applications WHERE id = ?",
            (application_id,),
        ).fetchone()
        auto_submit_setting = (
            application_row["auto_submit"] if application_row else None
        )
        resolved_answers = load_resolved_answers(conn, application_id)
        ai_mapper = build_ai_mapper(profile)
        if ai_mapper is not None:
            record_event(
                conn,
                application_id,
                "ai_mapping_enabled",
                f"AI mapping enabled ({ai_mapper.model}, max "
                f"{ai_mapper.max_fields} fields per run).",
            )

        with open_browser_page() as page:
            record_event(
                conn,
                application_id,
                "browser_opened",
                "Browser opened in visible mode." if not _is_headless() else "Browser opened.",
            )

            try:
                page.goto(job_url, wait_until="domcontentloaded")
            except PlaywrightTimeoutError as exc:
                raise AutomationError(
                    "Timed out while loading the application page."
                ) from exc
            except Exception as exc:
                raise AutomationError(f"Could not open the application page: {exc}") from exc

            page.wait_for_timeout(1000)
            try:
                # React/Greenhouse may still be hydrating after DOMContentLoaded.
                # Filling before hydration can be silently wiped by a re-render.
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                pass
            page.wait_for_timeout(500)
            record_event(
                conn,
                application_id,
                "navigated",
                f"Opened page: {page.url}",
            )

            login_timeout = _env_int("LOGIN_WAIT_SECONDS", 300)

            if not wait_for_form(page, timeout_ms=2500):
                if is_login_wall(page):
                    if not _wait_for_manual_login(
                        page, conn, application_id, login_timeout
                    ):
                        raise AutomationError(
                            "Timed out waiting for manual sign-in. "
                            "Sign in in the browser, then retry the application."
                        )
                else:
                    reveal_form_if_needed(page)
                    if not wait_for_form(page, timeout_ms=8000):
                        if is_login_wall(page):
                            if not _wait_for_manual_login(
                                page, conn, application_id, login_timeout
                            ):
                                raise AutomationError(
                                    "Timed out waiting for manual sign-in. "
                                    "Sign in in the browser, then retry the application."
                                )
                        else:
                            raise AutomationError(
                                "Unsupported page: no Greenhouse application form was found. "
                                "Only Greenhouse application forms are supported in this version."
                            )

            if not has_greenhouse_form(page):
                raise AutomationError(
                    "Unsupported page: no Greenhouse application form was found. "
                    "Only Greenhouse application forms are supported in this version."
                )

            company, role = read_job_meta(page)
            if company or role:
                update_application(
                    conn, application_id, company=company, role=role
                )
                record_event(
                    conn,
                    application_id,
                    "job_details_detected",
                    f"Detected job: {role or 'Unknown role'} at {company or 'Unknown company'}.",
                )

            result = fill_application(
                page, profile, resolved_answers, ai_mapper=ai_mapper
            )

            record_event(
                conn,
                application_id,
                "form_inspected",
                f"Inspected {result.inspected} form fields "
                f"({result.required} required).",
            )

            ai_details = {
                item["label"]: item for item in result.ai_filled
            }
            for label, value in result.filled:
                detail = ai_details.get(label)
                if detail:
                    record_event(
                        conn,
                        application_id,
                        "ai_field_filled",
                        f"AI filled {label} "
                        f"(confidence {detail['confidence']:.2f}): "
                        f"{detail['reason']}",
                    )
                elif "resume" in label.lower() or "cv" in label.lower():
                    record_event(
                        conn,
                        application_id,
                        "resume_uploaded",
                        f"Uploaded resume for {label}",
                    )
                elif "cover letter" in label.lower():
                    record_event(
                        conn,
                        application_id,
                        "cover_letter_uploaded",
                        f"Uploaded cover letter for {label}",
                    )
                else:
                    record_event(
                        conn,
                        application_id,
                        "field_filled",
                        f"Filled {label}",
                    )

            for error in result.ai_errors:
                record_event(
                    conn,
                    application_id,
                    "ai_mapping_error",
                    f"AI mapping fallback: {error}",
                )

            for item in result.review_items:
                create_review_item(
                    conn,
                    application_id,
                    item["field_name"],
                    item["reason"],
                    item.get("suggested_value"),
                )
                prefix = (
                    "AI suggests review"
                    if item.get("source") == "ai"
                    else "Needs review"
                )
                record_event(
                    conn,
                    application_id,
                    "review_item_created",
                    f"{prefix}: {item['field_name']} — {item['reason']}",
                )

            if ai_mapper is not None:
                record_event(
                    conn,
                    application_id,
                    "ai_mapping_summary",
                    f"AI mapping used {ai_mapper.calls_made} call(s), "
                    f"{len(result.ai_filled)} fill(s), "
                    f"{ai_mapper.error_count} error(s).",
                )

            if result.review_items:
                summary = (
                    f"Filled {len(result.filled)} field(s); "
                    f"{len(result.review_items)} item(s) require review."
                )
                update_application(
                    conn,
                    application_id,
                    status="Needs Review",
                    last_error=None,
                )
                record_event(conn, application_id, "form_filled", summary)
                record_event(
                    conn,
                    application_id,
                    "awaiting_review",
                    "Submission paused until the review items are answered.",
                )
                return

            if not _submission_host_supported(page):
                update_application(
                    conn,
                    application_id,
                    status="Needs Review",
                    last_error=(
                        "Automatic submission is currently enabled only for "
                        "Greenhouse job boards. The form was filled but not submitted."
                    ),
                )
                record_event(
                    conn,
                    application_id,
                    "submission_skipped",
                    "Unsupported host for automatic submission; form left unsubmitted.",
                )
                return

            if not _auto_submit_enabled(auto_submit_setting):
                update_application(
                    conn,
                    application_id,
                    status="Needs Review",
                    last_error=(
                        "Fill-only mode is active for this application: the form "
                        "was filled but not submitted. Review it, then resume with "
                        "automatic submission enabled to submit."
                    ),
                )
                record_event(
                    conn,
                    application_id,
                    "submission_skipped",
                    "Fill-only mode: form filled; submission skipped until "
                    "explicit approval.",
                )
                return

            if find_submit_button(page) is None:
                raise AutomationError(
                    "The application form is complete, but no enabled Submit button was found."
                )

            # Record the attempt before clicking. A crash after this point is an
            # uncertain outcome, not permission to submit again automatically.
            now = utc_now()
            update_application(
                conn,
                application_id,
                submission_attempted_at=now,
                submission_outcome="pending",
            )
            record_event(
                conn,
                application_id,
                "submitting",
                "All required fields are filled; submitting the application.",
            )

            try:
                click_submit(page)
            except AutomationError as exc:
                update_application(
                    conn,
                    application_id,
                    status="Needs Review",
                    submission_outcome="uncertain",
                    last_error=(
                        f"{exc} The submission outcome is uncertain. "
                        "Verify the employer page before trying again."
                    ),
                )
                record_event(
                    conn,
                    application_id,
                    "submission_uncertain",
                    "Submit click failed or was interrupted; outcome not confirmed.",
                )
                return

            record_event(
                conn,
                application_id,
                "submit_clicked",
                "Clicked Submit application; waiting for a confirmation signal.",
            )

            signal = wait_for_submission_signal(
                page, timeout_ms=_env_int("SUBMISSION_TIMEOUT_MS", 30000)
            )

            if signal.get("kind") == "captcha":
                record_event(
                    conn,
                    application_id,
                    "manual_verification_required",
                    "A CAPTCHA challenge appeared. Solve it in the visible browser; "
                    "the agent will not bypass it and is waiting for the result.",
                )
                signal = wait_for_confirmation(
                    page,
                    timeout_ms=_env_int("CAPTCHA_WAIT_SECONDS", 300) * 1000,
                )
            elif signal.get("kind") == "login":
                record_event(
                    conn,
                    application_id,
                    "login_required",
                    "The site is asking for manual sign-in after submit. "
                    "Sign in in the visible browser; the agent is waiting.",
                )
                signal = wait_for_confirmation(
                    page,
                    timeout_ms=_env_int("LOGIN_WAIT_SECONDS", 300) * 1000,
                )

            confirmed = bool(signal and signal.get("kind") == "confirmed")
            if confirmed:
                submitted_at = utc_now()
                details = {
                    "signal": signal.get("signal"),
                    "url": signal.get("url") or page.url,
                    "message": (signal.get("message") or "")[:800],
                    "verified_at": submitted_at,
                }
                update_application(
                    conn,
                    application_id,
                    status="Submitted",
                    submitted_at=submitted_at,
                    submission_outcome="confirmed",
                    confirmation_details=json.dumps(details),
                    last_error=None,
                )
                record_event(
                    conn,
                    application_id,
                    "submission_confirmed",
                    "Submission confirmed by the site: "
                    + (signal.get("signal") or "confirmation").replace("_", " "),
                )
                return

            errors = collect_submission_errors(page)
            if errors:
                message = "The form was not accepted: " + " | ".join(errors)
                update_application(
                    conn,
                    application_id,
                    status="Needs Review",
                    submission_outcome="rejected",
                    last_error=message[:2000],
                )
                record_event(
                    conn,
                    application_id,
                    "submission_rejected",
                    "The form reported validation errors; nothing was confirmed as submitted.",
                )
                return

            update_application(
                conn,
                application_id,
                status="Needs Review",
                submission_outcome="uncertain",
                last_error=(
                    "Submission was attempted, but no confirmation signal was detected. "
                    "Check the employer site before retrying; automatic resubmission "
                    "is disabled for this application."
                ),
            )
            record_event(
                conn,
                application_id,
                "submission_uncertain",
                "No confirmation signal was found after clicking Submit. "
                "This application will not be resubmitted automatically.",
            )
    except AutomationError as exc:
        logger.warning(
            "Run failed application=%s reason=%s", application_id, exc
        )
        _fail(conn, application_id, str(exc))
    except Exception as exc:
        logger.exception("Run crashed application=%s", application_id)
        _fail(conn, application_id, f"Automation error: {exc}")
    finally:
        logger.info("Run finished application=%s", application_id)
        conn.close()
