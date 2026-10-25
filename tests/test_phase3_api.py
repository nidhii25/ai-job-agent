"""API-level verification for Phase 3 (Playwright automation).

Prerequisites:
  - Backend running on http://127.0.0.1:8000 with:
      BROWSER_HEADLESS=true
      BROWSER_CLOSE_DELAY_SECONDS=0
      ALLOW_LOCAL_URLS=true
  - Chromium installed: backend\\venv\\Scripts\\python.exe -m playwright install chromium

Usage (from the repo root):
    backend\\venv\\Scripts\\python.exe tests\\test_phase3_api.py
"""

import base64
import json
import os
import tempfile
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8000"
TEST_FORM_URL = f"{API}/test/greenhouse"
NOT_A_FORM_URL = f"{API}/test/not-a-form"

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

TEST_PROFILE = {
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


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def wait_until_finished(application_id, timeout=90):
    deadline = time.time() + timeout
    detail = None
    while time.time() < deadline:
        detail = call("GET", f"/api/applications/{application_id}")["data"]
        if detail["status"] in ("Needs Review", "Submitted", "Failed"):
            return detail
        time.sleep(0.5)
    raise AssertionError(
        f"Application {application_id} did not finish in {timeout}s "
        f"(status={detail and detail['status']})"
    )


def main():
    passed = []

    def check(condition, message):
        if not condition:
            raise AssertionError(message)
        passed.append(message)
        print(f"PASS: {message}")

    health = call("GET", "/api/health")
    check(health.get("status") == "healthy", "backend is healthy")
    if not health.get("allow_local_urls"):
        raise SystemExit(
            "Backend must run with ALLOW_LOCAL_URLS=true so the local test form "
            "can be used."
        )

    created_ids = []
    resume_source = os.path.join(tempfile.gettempdir(), "phase3_resume.txt")
    uploaded_paths = []

    with open(resume_source, "w", encoding="utf-8") as handle:
        handle.write("Phase 3 test resume")

    try:
        call("PUT", "/api/profile", TEST_PROFILE)
        upload = call(
            "POST",
            "/api/profile/resume",
            {
                "filename": "phase3_resume.txt",
                "content_base64": base64.b64encode(
                    open(resume_source, "rb").read()
                ).decode(),
            },
        )
        uploaded_paths.append(upload["resume_path"])
        check(
            os.path.isfile(upload["resume_path"]),
            "resume upload created a file on disk",
        )

        # --- Successful fill run ---
        created = call(
            "POST", "/api/applications", {"job_url": TEST_FORM_URL}
        )
        application_id = created["application_id"]
        created_ids.append(application_id)

        detail = wait_until_finished(application_id)
        check(
            detail["status"] == "Needs Review",
            "a run with a missing required answer ends in Needs Review",
        )
        check(detail["last_error"] is None, "successful run has no error")
        check(
            detail["company"] == "Acme Corp",
            "company detected from the page",
        )
        check(
            detail["role"] == "Software Engineering Intern",
            "role detected from the page",
        )

        event_types = [event["event_type"] for event in detail["events"]]
        for expected in (
            "run_started",
            "browser_opened",
            "navigated",
            "job_details_detected",
            "form_inspected",
            "field_filled",
            "resume_uploaded",
            "form_filled",
            "awaiting_review",
        ):
            check(expected in event_types, f"event stored: {expected}")

        filled_messages = " | ".join(
            event["message"]
            for event in detail["events"]
            if event["event_type"] in ("field_filled", "resume_uploaded")
        )
        for label in (
            "First Name",
            "Last Name",
            "Email",
            "Phone",
            "Country",
            "Location (City)",
            "LinkedIn Profile",
            "Are you legally authorized",
            "How did you hear about this job",
            "Will you now or in the future require sponsorship",
            "Uploaded resume",
        ):
            check(label in filled_messages, f"filled or uploaded: {label}")

        check(
            len(detail["review_items"]) == 1,
            "exactly one required field needs review",
        )
        review = detail["review_items"][0]
        check(
            review["field_name"] == "Expected salary",
            "review item is the unsaved salary question",
        )
        check(
            review["resolved_at"] is None,
            "review item is unresolved and blocks submission",
        )
        check(
            detail["submission_outcome"] is None,
            "no submission was attempted while review items are open",
        )

        # --- Unsupported page failure run ---
        created = call(
            "POST", "/api/applications", {"job_url": NOT_A_FORM_URL}
        )
        failure_id = created["application_id"]
        created_ids.append(failure_id)

        failure = wait_until_finished(failure_id)
        check(failure["status"] == "Failed", "unsupported page ends in Failed")
        check(
            "no greenhouse application form"
            in (failure["last_error"] or "").lower(),
            "failure reason explains that no Greenhouse form was found",
        )
        check(
            "failed"
            in [event["event_type"] for event in failure["events"]],
            "failure event is stored",
        )

        print(f"\nPHASE 3 API RESULT: {len(passed)} checks passed")
    finally:
        for application_id in created_ids:
            try:
                call("DELETE", f"/api/applications/{application_id}")
            except Exception:
                pass
        try:
            call("PUT", "/api/profile", EMPTY_PROFILE)
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
