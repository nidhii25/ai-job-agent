"""Fill-only safety check.

Prerequisites:
  - Backend on http://127.0.0.1:8000 with:
      ALLOW_LOCAL_URLS=true
      AUTO_SUBMIT=false
      BROWSER_HEADLESS=true
      BROWSER_CLOSE_DELAY_SECONDS=0
      AI_ENABLED=false

Usage (from the repo root):
    backend\\venv\\Scripts\\python.exe tests\\test_fill_only_api.py
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

PROFILE = {
    "personal": {
        "full_name": "Fill Only Candidate",
        "first_name": "",
        "last_name": "",
        "email": "fill.only@example.com",
        "phone": "555-0122",
        "location": "Remote",
        "country": "United States",
        "linkedin_url": "https://linkedin.com/in/fill-only",
        "github_url": "",
        "website_url": "",
    },
    "education": [],
    "experience": [],
    "skills": [],
    "projects": [],
    "resume_path": "",
    "cover_letter": "",
    "work_authorization": "Authorized to work in the United States",
    "saved_answers": {
        "Are you legally authorized to work in the United States?": "Yes",
        "Will you now or in the future require sponsorship?": "No",
        "How did you hear about this job?": "LinkedIn",
        "Expected salary": "70000",
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

    status, health = request("GET", "/api/health")
    check(status == 200 and health.get("status") == "healthy", "backend is healthy")
    if not health.get("allow_local_urls"):
        raise SystemExit("Backend must run with ALLOW_LOCAL_URLS=true.")
    if health.get("auto_submit"):
        raise SystemExit("Backend must run with AUTO_SUBMIT=false for this test.")

    created_ids = []
    resume_source = os.path.join(tempfile.gettempdir(), "fill_only_resume.txt")
    uploaded_paths = []
    with open(resume_source, "w", encoding="utf-8") as handle:
        handle.write("Fill-only test resume")

    try:
        with open(resume_source, "rb") as handle:
            upload_status, upload = request(
                "POST",
                "/api/profile/resume",
                {
                    "filename": "fill_only_resume.txt",
                    "content_base64": base64.b64encode(handle.read()).decode(),
                },
            )
        check(upload_status == 200, "resume upload succeeded")
        resume_path = upload["resume_path"]
        uploaded_paths.append(resume_path)

        profile = json.loads(json.dumps(PROFILE))
        profile["resume_path"] = resume_path
        request("PUT", "/api/profile", profile)

        status, created = request(
            "POST", "/api/applications", {"job_url": TEST_FORM_URL}
        )
        check(status == 200, "fill-only application was created")
        application_id = created["application_id"]
        created_ids.append(application_id)

        detail = wait_until_finished(application_id)
        check(detail["status"] == "Needs Review", "fill-only run stops at Needs Review")
        check(
            detail["submission_outcome"] is None,
            "fill-only run records no submission outcome",
        )
        check(
            detail["submission_attempted_at"] is None,
            "fill-only run records no submission attempt",
        )
        check(
            "fill-only mode" in (detail.get("last_error") or "").lower(),
            "fill-only reason is stored",
        )
        event_types = [event["event_type"] for event in detail["events"]]
        check("submission_skipped" in event_types, "submission_skipped event is stored")
        check("submitting" not in event_types, "Submit was never clicked")
        check("submit_clicked" not in event_types, "Submit click event is absent")
        check(
            len(detail["review_items"]) == 0,
            "complete fill-only form has no review items",
        )

        print(f"\nFILL-ONLY RESULT: {len(passed)} checks passed")
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
        print("cleanup: removed fill-only application and reset profile")


if __name__ == "__main__":
    main()
