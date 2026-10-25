"""End-to-end check for the current three-page UI (Phases 1-3 + submission).

Covers navigation, profile editing/upload, starting a Greenhouse application,
live Playwright progress, review-item resolution, auto-submission, confirmation
display, list filtering, detail history, and error-free rendering.

Prerequisites:
  - Backend on http://127.0.0.1:8000 with:
      BROWSER_HEADLESS=true
      BROWSER_CLOSE_DELAY_SECONDS=0
      ALLOW_LOCAL_URLS=true
  - Frontend on http://localhost:3000
  - Chromium installed: backend\\venv\\Scripts\\python.exe -m playwright install chromium

Usage (from the repo root):
    backend\\venv\\Scripts\\python.exe tests\\e2e_phase2.py
"""

import json
import os
import re
import tempfile
import urllib.request

from playwright.sync_api import expect, sync_playwright

BASE = "http://localhost:3000"
API = "http://127.0.0.1:8000"
JOB_URL = f"{API}/test/greenhouse"

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

AUTHORIZATION_QUESTION = (
    "Are you legally authorized to work in the United States?"
)
SPONSORSHIP_QUESTION = "Will you now or in the future require sponsorship?"
REFERRAL_QUESTION = "How did you hear about this job?"


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


def cleanup(created_ids, uploaded_resume_path):
    for application_id in created_ids:
        try:
            call("DELETE", f"/api/applications/{application_id}")
        except Exception:
            pass
    try:
        call("PUT", "/api/profile", EMPTY_PROFILE)
    except Exception:
        pass
    if uploaded_resume_path:
        try:
            os.remove(uploaded_resume_path)
        except OSError:
            pass


def add_saved_answer(page, question, answer):
    page.get_by_placeholder("e.g., Are you willing to relocate?").fill(question)
    page.get_by_placeholder("e.g., Yes").fill(answer)
    page.get_by_role("button", name="Add Saved Answer").click()
    expect(page.get_by_text(question, exact=True)).to_be_visible()


def main():
    health = call("GET", "/api/health")
    if not health.get("allow_local_urls"):
        raise SystemExit(
            "Backend must run with ALLOW_LOCAL_URLS=true so the local "
            "Greenhouse test form can be used."
        )

    created_ids = []
    uploaded_resume_path = ""
    console_errors = []
    passed = []

    def step(name):
        passed.append(name)
        print(f"PASS: {name}")

    resume_path = os.path.join(tempfile.gettempdir(), "e2e_resume.txt")
    with open(resume_path, "w", encoding="utf-8") as handle:
        handle.write("E2E resume")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.on("pageerror", lambda error: console_errors.append(str(error)))

            page.goto(BASE, wait_until="networkidle")
            expect(page).to_have_url(f"{BASE}/apply")
            expect(
                page.get_by_role("heading", name="Apply for a Job")
            ).to_be_visible()
            expect(
                page.get_by_role("navigation").get_by_role("link")
            ).to_have_count(3)
            step("home redirects to /apply with 3-link navigation")

            page.get_by_role("link", name="My Profile", exact=True).click()
            expect(page.get_by_role("heading", name="My Profile")).to_be_visible()
            page.get_by_placeholder("Full name", exact=True).fill("E2E Test User")
            page.get_by_placeholder("email@example.com").fill("e2e@example.com")
            page.get_by_placeholder("Phone number").fill("555-0101")
            page.get_by_placeholder("City, Country").fill("Remote")
            page.get_by_placeholder("e.g., United States").fill("United States")
            page.get_by_placeholder(
                "https://linkedin.com/in/username"
            ).fill("https://linkedin.com/in/e2e-user")
            page.get_by_placeholder(
                "e.g., Authorized to work in the US without sponsorship"
            ).fill("Authorized to work in the US")

            add_saved_answer(page, AUTHORIZATION_QUESTION, "Yes")
            add_saved_answer(page, SPONSORSHIP_QUESTION, "No")
            add_saved_answer(page, REFERRAL_QUESTION, "LinkedIn")

            page.locator(
                "section",
                has=page.get_by_role("heading", name="Resume & Cover Letter"),
            ).locator('input[type="file"]').set_input_files(resume_path)
            expect(
                page.get_by_text("Resume uploaded and saved to the profile.")
            ).to_be_visible(timeout=15000)

            page.get_by_role("button", name="Save Profile").click()
            expect(page.get_by_text("Profile saved successfully.")).to_be_visible()

            profile = call("GET", "/api/profile")["data"]
            uploaded_resume_path = profile["resume_path"]

            page.reload(wait_until="networkidle")
            expect(
                page.get_by_placeholder("Full name", exact=True)
            ).to_have_value("E2E Test User")
            expect(page.get_by_placeholder("email@example.com")).to_have_value(
                "e2e@example.com"
            )
            expect(page.get_by_text(AUTHORIZATION_QUESTION, exact=True)).to_be_visible()
            step("profile edits, saved answers, resume upload, save, and reload")

            existing_ids = {
                application["id"]
                for application in call("GET", "/api/applications")["data"]
                if application["job_url"] == JOB_URL
            }

            page.get_by_role("link", name="Apply", exact=True).click()
            expect(
                page.get_by_role("heading", name="Apply for a Job")
            ).to_be_visible()
            page.locator("#job-url").fill(JOB_URL)
            page.get_by_role("button", name="Start Application").click()
            expect(
                page.get_by_text("Application created for URL")
            ).to_be_visible(timeout=15000)

            for application in call("GET", "/api/applications")["data"]:
                if (
                    application["job_url"] == JOB_URL
                    and application["id"] not in existing_ids
                ):
                    created_ids.append(application["id"])

            expect(
                page.get_by_text("Acme Corp", exact=True)
            ).to_be_visible(timeout=90000)
            expect(
                page.get_by_text("Software Engineering Intern", exact=True)
            ).to_be_visible(timeout=15000)
            expect(
                page.get_by_text("Needs Review", exact=True).first
            ).to_be_visible(timeout=15000)
            expect(
                page.get_by_text("Expected salary", exact=True)
            ).to_be_visible(timeout=15000)
            expect(
                page.get_by_text(
                    "Submission paused until the review items are answered."
                )
            ).to_be_visible()
            expect(
                page.get_by_text(
                    "Uploaded resume for Resume/CV", exact=True
                )
            ).to_be_visible()
            step(
                "live Playwright run fills the form and shows company, role, "
                "review item, and filled status"
            )

            page.get_by_role("link", name="All Applications", exact=True).click()
            expect(page).to_have_url(f"{BASE}/applications")
            expect(
                page.get_by_role("heading", name="All Applications")
            ).to_be_visible()
            export_link = page.get_by_role("link", name="Download JSON export")
            expect(export_link).to_be_visible()
            expect(export_link).to_have_attribute(
                "href",
                re.compile(
                    r"^http://(localhost|127\.0\.0\.1):8000/api/applications/export$"
                ),
            )

            # Reload so only this route's DOM is present, then exercise the table.
            page.goto(f"{BASE}/applications", wait_until="networkidle")
            row = page.locator("tbody tr", has_text=JOB_URL).first
            expect(row).to_be_visible(timeout=15000)
            expect(row.get_by_text("Needs Review", exact=True)).to_be_visible()

            page.get_by_label("Status Filter").select_option("Submitted")
            expect(page.get_by_text("No applications found.")).to_be_visible(
                timeout=15000
            )
            page.get_by_label("Status Filter").select_option("Needs Review")
            expect(row).to_be_visible(timeout=15000)
            page.get_by_label("Status Filter").select_option("")
            expect(row).to_be_visible(timeout=15000)

            row.get_by_role("button", name="Detail").click()
            expect(
                page.get_by_role("heading", name="Progress History")
            ).to_be_visible()
            expect(page.get_by_text("application_created").first).to_be_visible()
            expect(page.get_by_text("form_inspected").first).to_be_visible()
            expect(page.get_by_text("form_filled").first).to_be_visible()
            expect(page.get_by_text("Expected salary", exact=True)).to_be_visible()
            expect(
                page.get_by_text("Review Items", exact=True)
            ).to_be_visible()
            step("applications list, status filter, detail events, and review items")

            page.get_by_placeholder("Type your answer").fill("70000")
            page.get_by_role("button", name="Save answer").click()
            expect(page.get_by_text("Resolved: 70000")).to_be_visible(
                timeout=15000
            )
            page.get_by_role("button", name="Resume & Submit").click()

            # The detail panel does not poll, so refresh the list manually.
            submitted_row = page.locator("tbody tr", has_text=JOB_URL).first
            for _ in range(60):
                page.get_by_role("button", name="Refresh").click()
                page.wait_for_timeout(1000)
                if "Submitted" in submitted_row.inner_text():
                    break
            expect(
                submitted_row.get_by_text("Submitted", exact=True)
            ).to_be_visible(timeout=15000)
            submitted_row.get_by_role("button", name="Detail").click()
            expect(
                page.get_by_text("Submission confirmed", exact=True)
            ).to_be_visible(timeout=15000)
            expect(
                page.get_by_text("Thank you for applying.", exact=False).first
            ).to_be_visible(timeout=15000)
            step("review resolution, resume, and verified submission")

            page.get_by_label("Status Filter").select_option("Submitted")
            expect(
                page.locator("tbody tr", has_text=JOB_URL).first
            ).to_be_visible(timeout=15000)
            page.get_by_label("Status Filter").select_option("Needs Review")
            expect(page.get_by_text("No applications found.")).to_be_visible(
                timeout=15000
            )
            step("Submitted filter includes the verified application")

            assert not console_errors, f"console errors: {console_errors}"
            step("no browser console or page errors")

            browser.close()
    finally:
        cleanup(created_ids, uploaded_resume_path)
        try:
            os.remove(resume_path)
        except OSError:
            pass
        print(
            f"cleanup: removed {len(created_ids)} test application(s), "
            "reset profile, removed test uploads"
        )

    print(f"E2E RESULT: {len(passed)} checks passed")


if __name__ == "__main__":
    main()
