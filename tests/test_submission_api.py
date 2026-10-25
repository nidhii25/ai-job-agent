"""Submission, review resolution, and uncertain-outcome checks.

Prerequisites:
  - Backend on http://127.0.0.1:8000 with:
      BROWSER_HEADLESS=true
      BROWSER_CLOSE_DELAY_SECONDS=0
      ALLOW_LOCAL_URLS=true
      SUBMISSION_TIMEOUT_MS=4000
  - Frontend is not required for this test.

Usage (from the repo root):
    backend\\venv\\Scripts\\python.exe tests\\test_submission_api.py
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

    created_ids = []
    resume_source = os.path.join(tempfile.gettempdir(), "submission_resume.txt")
    uploaded_paths = []

    with open(resume_source, "w", encoding="utf-8") as handle:
        handle.write("Submission test resume")

    try:
        # Reject a MyGreenhouse search URL before it creates a run.
        status, payload = request(
            "POST",
            "/api/applications",
            {"job_url": "https://my.greenhouse.io/jobs/search?query=software%20"},
        )
        check(status == 400, "MyGreenhouse search URL is rejected with 400")

        with open(resume_source, "rb") as handle:
            upload_status, upload = request(
                "POST",
                "/api/profile/resume",
                {
                    "filename": "submission_resume.txt",
                    "content_base64": base64.b64encode(handle.read()).decode(),
                },
            )
        check(upload_status == 200, "resume upload succeeded")
        resume_path = upload["resume_path"]
        uploaded_paths.append(resume_path)

        profile_with_salary = json.loads(json.dumps(BASE_PROFILE))
        profile_with_salary["resume_path"] = resume_path
        profile_with_salary["saved_answers"]["Expected salary"] = "70000"

        profile_without_salary = json.loads(json.dumps(BASE_PROFILE))
        profile_without_salary["resume_path"] = resume_path

        # --- Fully answerable run: auto-submit and verify confirmation ---
        request("PUT", "/api/profile", profile_with_salary)
        status, created = request(
            "POST", "/api/applications", {"job_url": TEST_FORM_URL}
        )
        check(status == 200, "fully answerable application was created")
        application_id = created["application_id"]
        created_ids.append(application_id)

        detail = wait_until_finished(application_id)
        check(detail["status"] == "Submitted", "verified run ends in Submitted")
        check(detail["submitted_at"] is not None, "submitted_at timestamp is stored")
        check(
            detail["submission_outcome"] == "confirmed",
            "submission outcome is confirmed",
        )
        check(detail["last_error"] is None, "submitted run has no error")
        check(
            len(detail["review_items"]) == 0,
            "fully answerable run has no review items",
        )
        confirmation = detail.get("confirmation_details") or ""
        check(
            "Thank you for applying" in confirmation,
            "confirmation details contain the site confirmation text",
        )
        event_types = [event["event_type"] for event in detail["events"]]
        for expected in (
            "submitting",
            "submit_clicked",
            "submission_confirmed",
        ):
            check(expected in event_types, f"event stored: {expected}")
        status, _ = request("POST", f"/api/applications/{application_id}/resume")
        check(status == 409, "a submitted application cannot be resumed")

        # --- Manual login gate: wait, then continue and submit ---
        status, created = request(
            "POST",
            "/api/applications",
            {"job_url": f"{TEST_FORM_URL}?login=1"},
        )
        check(status == 200, "login-gated application was created")
        login_id = created["application_id"]
        created_ids.append(login_id)
        detail = wait_until_finished(login_id)
        check(detail["status"] == "Submitted", "login-gated run submits after the form appears")
        login_events = [event["event_type"] for event in detail["events"]]
        check("login_required" in login_events, "manual login pause is recorded")
        check("login_completed" in login_events, "manual login completion is recorded")

        # --- CAPTCHA challenge: pause, wait for the human, then verify ---
        status, created = request(
            "POST",
            "/api/applications",
            {"job_url": f"{TEST_FORM_URL}?captcha=1"},
        )
        check(status == 200, "captcha-gated application was created")
        captcha_id = created["application_id"]
        created_ids.append(captcha_id)
        detail = wait_until_finished(captcha_id)
        check(detail["status"] == "Submitted", "captcha-gated run submits after the challenge")
        captcha_events = [event["event_type"] for event in detail["events"]]
        check(
            "manual_verification_required" in captcha_events,
            "CAPTCHA pause is recorded",
        )
        check(
            "submission_confirmed" in captcha_events,
            "CAPTCHA-gated run is confirmed after the challenge clears",
        )

        # --- Review pause, resolve, then submit ---
        request("PUT", "/api/profile", profile_without_salary)
        status, created = request(
            "POST", "/api/applications", {"job_url": TEST_FORM_URL}
        )
        check(status == 200, "review-flow application was created")
        review_app_id = created["application_id"]
        created_ids.append(review_app_id)

        detail = wait_until_finished(review_app_id)
        check(detail["status"] == "Needs Review", "missing answer pauses at Needs Review")
        check(
            detail["submission_outcome"] is None,
            "no submission is attempted while review items are open",
        )
        open_items = [item for item in detail["review_items"] if not item["resolved_at"]]
        check(len(open_items) == 1, "exactly one review item is open")
        check(
            open_items[0]["field_name"] == "Expected salary",
            "review item identifies the missing salary question",
        )
        review_item_id = open_items[0]["id"]

        status, _ = request("POST", f"/api/applications/{review_app_id}/resume")
        check(status == 409, "resume is blocked while review items are unresolved")

        status, resolved = request(
            "POST",
            f"/api/applications/{review_app_id}/review-items/{review_item_id}/resolve",
            {"resolution": "75000"},
        )
        check(status == 200 and resolved["status"] == "success", "review answer saved")

        detail = request("GET", f"/api/applications/{review_app_id}")[1]["data"]
        resolved_item = next(
            item for item in detail["review_items"] if item["id"] == review_item_id
        )
        check(resolved_item["user_resolution"] == "75000", "resolution is persisted")
        check(resolved_item["resolved_at"] is not None, "resolved_at is persisted")

        status, _ = request("POST", f"/api/applications/{review_app_id}/resume")
        check(status == 200, "resume is allowed after all review items are resolved")
        detail = wait_until_finished(review_app_id)
        check(detail["status"] == "Submitted", "resumed application is submitted")
        check(
            "Thank you for applying" in (detail.get("confirmation_details") or ""),
            "resumed run records the confirmation",
        )
        event_types = [event["event_type"] for event in detail["events"]]
        check("review_item_resolved" in event_types, "review resolution event is stored")
        check("resume" in event_types, "resume event is stored")

        # --- Unclear submission: do not resubmit automatically ---
        request("PUT", "/api/profile", profile_with_salary)
        ambiguous_url = f"{TEST_FORM_URL}?outcome=uncertain"
        status, created = request(
            "POST", "/api/applications", {"job_url": ambiguous_url}
        )
        check(status == 200, "uncertain-outcome application was created")
        uncertain_id = created["application_id"]
        created_ids.append(uncertain_id)

        detail = wait_until_finished(uncertain_id, timeout=60)
        check(detail["status"] == "Needs Review", "unclear submission stays Needs Review")
        check(
            detail["submission_outcome"] == "uncertain",
            "unclear submission is marked uncertain",
        )
        check(
            "no confirmation signal" in (detail["last_error"] or "").lower(),
            "unclear submission explains the missing confirmation",
        )
        status, _ = request("POST", f"/api/applications/{uncertain_id}/resume")
        check(status == 409, "uncertain submission cannot be retried automatically")

        status, _ = request(
            "POST",
            f"/api/applications/{uncertain_id}/confirm-submission",
            {"details": "Verified manually in the test harness."},
        )
        check(status == 200, "manual confirmation is accepted")
        detail = request("GET", f"/api/applications/{uncertain_id}")[1]["data"]
        check(detail["status"] == "Submitted", "manual confirmation marks Submitted")
        check(
            detail["submission_outcome"] == "confirmed",
            "manual confirmation updates the outcome",
        )
        check(
            "Verified manually" in (detail.get("confirmation_details") or ""),
            "manual confirmation details are stored",
        )
        check(
            "submission_confirmed_manually"
            in [event["event_type"] for event in detail["events"]],
            "manual confirmation event is stored",
        )

        # --- Rejected form: a known non-submission may be resumed ---
        rejected_url = f"{TEST_FORM_URL}?outcome=rejected"
        status, created = request(
            "POST", "/api/applications", {"job_url": rejected_url}
        )
        check(status == 200, "rejected-outcome application was created")
        rejected_id = created["application_id"]
        created_ids.append(rejected_id)

        detail = wait_until_finished(rejected_id, timeout=60)
        check(detail["status"] == "Needs Review", "rejected form stays Needs Review")
        check(
            detail["submission_outcome"] == "rejected",
            "rejected form is marked rejected (not submitted)",
        )
        check(
            "not accepted" in (detail["last_error"] or "").lower(),
            "rejected form records the validation error",
        )
        status, _ = request("POST", f"/api/applications/{rejected_id}/resume")
        check(
            status == 200,
            "a rejected (non-submitted) form can be resumed after fixing issues",
        )
        # Let the resumed run finish so cleanup does not race a browser.
        wait_until_finished(rejected_id, timeout=60)

        print(f"\nSUBMISSION API RESULT: {len(passed)} checks passed")
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
