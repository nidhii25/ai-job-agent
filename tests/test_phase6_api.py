"""Phase 6 checks: JSON export, logs, invalid input, and failure handling.

Prerequisites:
  - Backend on http://127.0.0.1:8000 with:
      BROWSER_HEADLESS=true
      BROWSER_CLOSE_DELAY_SECONDS=0
      ALLOW_LOCAL_URLS=true
      SUBMISSION_TIMEOUT_MS=4000
  - Frontend is not required for this test.

Usage (from the repo root):
    backend\\venv\\Scripts\\python.exe tests\\test_phase6_api.py
"""

import base64
import glob
import json
import os
import tempfile
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8000"
TEST_FORM_URL = f"{API}/test/greenhouse"

EMPTY_PROFILE = {
    "personal": {
        "full_name": "",
        "first_name": "",
        "last_name": "",
        "email": "",
        "phone": "",
        "location": "",
        "country": "",
        "linkedin_url": "",
        "github_url": "",
        "website_url": "",
    },
    "education": [],
    "experience": [],
    "skills": [],
    "projects": [],
    "resume_path": "",
    "cover_letter": "",
    "work_authorization": "",
    "saved_answers": {},
}

BASE_PROFILE = {
    "personal": {
        "full_name": "Test Candidate",
        "first_name": "",
        "last_name": "",
        "email": "test.candidate@example.com",
        "phone": "555-0100",
        "location": "Remote",
        "country": "United States",
        "linkedin_url": "https://linkedin.com/in/test-candidate",
        "github_url": "https://github.com/test-candidate",
        "website_url": "https://test-candidate.example.com",
    },
    "education": [],
    "experience": [],
    "skills": [],
    "projects": [],
    "resume_path": "",
    "cover_letter": "Test cover letter.",
    "work_authorization": "Authorized to work in the United States",
    "saved_answers": {
        "Are you legally authorized to work in the United States?": "Yes",
        "Will you now or in the future require sponsorship?": "No",
        "How did you hear about this job?": "LinkedIn",
    },
}


def request(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read()
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            parsed = json.loads(body) if body else {}
        except ValueError:
            parsed = {"raw": body.decode("utf-8", "replace")}
        return exc.code, parsed


def request_raw(method, path):
    req = urllib.request.Request(f"{API}{path}", method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def wait_until_finished(application_id, timeout=90):
    deadline = time.time() + timeout
    detail = None
    while time.time() < deadline:
        status, payload = request("GET", f"/api/applications/{application_id}")
        if status != 200:
            raise AssertionError(f"Could not read application: {status} {payload}")
        detail = payload["data"]
        if detail["status"] in ("Needs Review", "Submitted", "Failed"):
            return detail
        time.sleep(0.4)
    raise AssertionError(
        f"Application {application_id} did not finish in {timeout}s "
        f"(status={detail and detail['status']})"
    )


def exported_application(export, application_id):
    return next(
        (
            item
            for item in export.get("applications", [])
            if item.get("id") == application_id
        ),
        None,
    )


def main():
    passed = []

    def check(condition, message):
        if not condition:
            raise AssertionError(message)
        passed.append(message)
        print(f"PASS: {message}")

    health_status, health = request("GET", "/api/health")
    check(health_status == 200 and health.get("status") == "healthy", "backend is healthy")
    if not health.get("allow_local_urls"):
        raise SystemExit(
            "Backend must run with ALLOW_LOCAL_URLS=true for the local test form."
        )
    export_path = health.get("applications_export")
    log_path = health.get("log_file")
    check(bool(export_path), "health reports the applications export path")
    check(bool(log_path), "health reports the log file path")

    created_ids = []
    resume_source = os.path.join(tempfile.gettempdir(), "phase6_resume.txt")
    uploaded_paths = []

    with open(resume_source, "w", encoding="utf-8") as handle:
        handle.write("Phase 6 test resume")

    try:
        # --- URL validation ---
        for invalid_url, label in (
            ("not-a-url", "scheme-less URL"),
            ("ftp://example.com/job", "non-HTTP URL"),
            ("http://", "URL with no host"),
        ):
            status, _ = request(
                "POST", "/api/applications", {"job_url": invalid_url}
            )
            check(status == 400, f"{label} is rejected with 400")

        # --- Export exists and has a stable schema ---
        status, headers, body = request_raw("GET", "/api/applications/export")
        check(status == 200, "JSON export endpoint returns 200")
        lower_headers = {key.lower(): value for key, value in headers.items()}
        check(
            "application/json" in lower_headers.get("content-type", ""),
            "JSON export has an application/json content type",
        )
        check(
            "attachment" in lower_headers.get("content-disposition", ""),
            "JSON export is served as a download",
        )
        export = json.loads(body)
        check("exported_at" in export, "JSON export has exported_at")
        check(
            export.get("application_count") == len(export.get("applications", [])),
            "JSON export application_count matches its list",
        )
        check(os.path.isfile(export_path), "JSON export file exists on disk")
        with open(export_path, "r", encoding="utf-8") as handle:
            disk_export = json.load(handle)
        check(
            [item.get("id") for item in disk_export.get("applications", [])]
            == [item.get("id") for item in export.get("applications", [])],
            "JSON export on disk matches the endpoint snapshot",
        )
        leftovers = glob.glob(
            os.path.join(os.path.dirname(export_path), ".applications-*.tmp")
        )
        check(not leftovers, "atomic export leaves no temporary files")

        # --- A review-flow application is reflected immediately ---
        with open(resume_source, "rb") as handle:
            upload_status, upload = request(
                "POST",
                "/api/profile/resume",
                {
                    "filename": "phase6_resume.txt",
                    "content_base64": base64.b64encode(handle.read()).decode(),
                },
            )
        check(upload_status == 200, "resume upload succeeded")
        resume_path = upload["resume_path"]
        uploaded_paths.append(resume_path)

        review_profile = json.loads(json.dumps(BASE_PROFILE))
        review_profile["resume_path"] = resume_path
        request("PUT", "/api/profile", review_profile)

        status, created = request(
            "POST", "/api/applications", {"job_url": TEST_FORM_URL}
        )
        check(status == 200, "review-flow application was created")
        review_id = created["application_id"]
        created_ids.append(review_id)

        detail = wait_until_finished(review_id)
        check(detail["status"] == "Needs Review", "missing answer pauses at Needs Review")
        open_items = [item for item in detail["review_items"] if not item["resolved_at"]]
        check(len(open_items) == 1, "one review item is open")
        review_item_id = open_items[0]["id"]

        status, _, body = request_raw("GET", "/api/applications/export")
        check(status == 200, "JSON export can be re-downloaded")
        export = json.loads(body)
        exported = exported_application(export, review_id)
        check(exported is not None, "new application appears in the JSON export")
        check(exported["status"] == "Needs Review", "exported status is current")
        check(
            len(exported.get("review_items", [])) == 1,
            "review items are included in the JSON export",
        )
        check(
            exported["review_items"][0]["field_name"] == "Expected salary",
            "exported review item identifies the missing salary question",
        )
        check(
            any(
                event["event_type"] == "awaiting_review"
                for event in exported.get("events", [])
            ),
            "event history is included in the JSON export",
        )

        status, resolved = request(
            "POST",
            f"/api/applications/{review_id}/review-items/{review_item_id}/resolve",
            {"resolution": "75000"},
        )
        check(status == 200 and resolved["status"] == "success", "review answer saved")

        status, _, body = request_raw("GET", "/api/applications/export")
        export = json.loads(body)
        exported = exported_application(export, review_id)
        exported_item = next(
            item
            for item in exported["review_items"]
            if item["id"] == review_item_id
        )
        check(
            exported_item["user_resolution"] == "75000",
            "review resolution is reflected in the JSON export",
        )
        check(
            exported_item["resolved_at"] is not None,
            "resolution timestamp is reflected in the JSON export",
        )

        # --- A confirmed submission is exported with its confirmation ---
        submit_profile = json.loads(json.dumps(review_profile))
        submit_profile["saved_answers"]["Expected salary"] = "70000"
        request("PUT", "/api/profile", submit_profile)
        status, created = request(
            "POST", "/api/applications", {"job_url": TEST_FORM_URL}
        )
        check(status == 200, "submittable application was created")
        submitted_id = created["application_id"]
        created_ids.append(submitted_id)
        detail = wait_until_finished(submitted_id)
        check(detail["status"] == "Submitted", "submittable run ends in Submitted")

        status, _, body = request_raw("GET", "/api/applications/export")
        export = json.loads(body)
        exported = exported_application(export, submitted_id)
        check(exported is not None, "submitted application appears in the export")
        check(exported["status"] == "Submitted", "exported submission status is current")
        check(
            exported["submission_outcome"] == "confirmed",
            "exported submission outcome is confirmed",
        )
        check(
            "Thank you for applying" in (exported.get("confirmation_details") or ""),
            "exported confirmation details are preserved",
        )
        check(
            any(
                event["event_type"] == "submission_confirmed"
                for event in exported.get("events", [])
            ),
            "exported event history contains submission_confirmed",
        )

        # --- A network failure is recorded, not silently lost ---
        status, created = request(
            "POST", "/api/applications", {"job_url": "http://127.0.0.1:1"}
        )
        check(status == 200, "unreachable URL is accepted after validation")
        failed_id = created["application_id"]
        created_ids.append(failed_id)
        detail = wait_until_finished(failed_id, timeout=60)
        check(detail["status"] == "Failed", "unreachable URL ends in Failed")
        check(bool(detail.get("last_error")), "unreachable URL stores a useful error")
        check(
            "could not open" in (detail.get("last_error") or "").lower(),
            "navigation failure explains that the page could not be opened",
        )
        status, _, body = request_raw("GET", "/api/applications/export")
        export = json.loads(body)
        exported = exported_application(export, failed_id)
        check(exported is not None, "failed application appears in the export")
        check(
            exported["status"] == "Failed" and bool(exported.get("last_error")),
            "exported failure status and error are current",
        )

        # --- Deleting an application removes it from the export ---
        status, _ = request("DELETE", f"/api/applications/{failed_id}")
        check(status == 200, "failed application can be deleted")
        created_ids.remove(failed_id)
        status, _, body = request_raw("GET", "/api/applications/export")
        export = json.loads(body)
        check(
            exported_application(export, failed_id) is None,
            "deleted application is removed from the JSON export",
        )

        # --- Logs exist and never contain profile contact values ---
        check(os.path.isfile(log_path), "rotating log file exists")
        with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
            logs = handle.read()
        check("Logging initialized" in logs, "logs were initialized at startup")
        check("Application created" in logs, "logs record application creation")
        check("run_started" in logs, "logs record automation run events")
        check(
            "test.candidate@example.com" not in logs,
            "logs do not contain the test email",
        )
        check("555-0100" not in logs, "logs do not contain the test phone")

        print(f"\nPHASE 6 API RESULT: {len(passed)} checks passed")
    finally:
        for application_id in created_ids:
            try:
                request("DELETE", f"/api/applications/{application_id}")
            except Exception:
                pass
        try:
            request("PUT", "/api/profile", EMPTY_PROFILE)
        except Exception:
            pass
        for path in uploaded_paths:
            try:
                os.remove(path)
            except OSError:
                pass
        try:
            os.remove(resume_source)
        except OSError:
            pass
        print(
            f"cleanup: removed {len(created_ids)} application(s), "
            "reset profile, removed test uploads"
        )


if __name__ == "__main__":
    main()
