Personal AI Job Application Agent
Project Proposal and Implementation Plan
Project type: Local, single-user web application
Status: Proposed design
Primary goal: Automate repetitive job application form-filling while
maintaining a reliable record of every application.
1. Project Overview
The Personal AI Job Application Agent is a locally run web application
that helps one user complete job applications. The user pastes a job
application URL into the interface. The agent opens the page in a
browser, identifies the form fields, fills fields using saved profile
information, uses an AI model when interpretation or written responses
are needed, and records the outcome.

If a required field cannot be answered confidently from the saved
profile or approved answer rules, the application is moved to Needs
Review instead of inventing information. When the form is complete and
all required answers are resolved, the agent can submit it automatically
on supported forms. It marks an application as Submitted only after
detecting a credible success signal from the website.

The first version is intended for personal use on a local computer. It
will not be deployed as a public or multi-user service.
2. Project Objectives
- Provide a simple interface with exactly three main pages.
- Reuse profile information across applications.
- Automate supported browser-based job application forms.
- Use AI only where it adds value, keeping straightforward field
  filling deterministic and fast.
- Track application progress, review requirements, submissions, and
  failures.
- Store application records locally in SQLite and maintain JSON
  profile/export files.
- Keep the initial implementation small enough to build, test, and
  demonstrate reliably.
3. Scope
Included in the first version
- Paste a job application URL and start an application run.
- Open the application in a visible browser window using Playwright.
- Read supported form fields and map them to saved profile data.
- Fill common text fields, supported dropdowns, checkboxes, and resume
  uploads.
- Use an AI API for unfamiliar field labels and suitable written
  questions.
- Identify missing or uncertain required information and add it to
  Needs Review.
- Show live progress and store status changes.
- Track application history and failure reasons.
- Save the profile in JSON and application data in SQLite.
- Export application history to JSON.
- Resume an application after review where technically possible.
Out of scope for the initial version
- Public deployment, multiple users, teams, or role-based permissions.
- Supporting every job portal or guaranteeing compatibility with every
  form.
- CAPTCHA bypass, defeating bot protections, or bypassing
  authentication.
- Automatically inventing qualifications, work authorization, salary
  history, or other personal information.
- A complex distributed task queue, microservices, vector database, or
  cloud infrastructure.
The first target should be one supported application portal and a small
set of representative forms. Support for other portals can be added
after the initial workflow is reliable.
4. Application Pages
Page 1 --- Apply for a Job
Purpose: Start and observe an application run.

Main elements: - Job application URL input. - Start Application
button. - Current company and role, when detectable. - Current workflow
stage and progress messages. - Fields filled and fields that require
review. - Link or action to resume after review, when supported.

Expected behavior: 1. The user enters a URL and starts the process. 2.
The backend validates the URL and creates an application record. 3. The
browser opens the page and begins inspecting the form. 4. The UI
displays progress updates. 5. The run either proceeds to submission,
pauses for review, or records a failure.
Page 2 --- All Applications
Purpose: View and manage application history.

Main elements: - Application list with company, role, URL, created date,
updated date, and status. - Filters for In Progress, Needs Review,
Submitted, and Failed. - Application detail view with progress history,
review items, and error details. - Retry or resume action where safe and
supported.
Page 3 --- My Profile
Purpose: Maintain reusable information for form filling.

Suggested sections: - Personal details: full name, email, phone,
location, and professional links. - Education: institution, degree,
field of study, dates, GPA/CGPA where appropriate. - Experience:
employer, title, dates, responsibilities, and achievements. - Skills and
projects. - Resume file path and optional cover letter. - Saved answers
to common application questions. - Work authorization and other
eligibility answers, entered explicitly by the user.

The user must be able to edit profile information. The agent must not
infer or fabricate sensitive or eligibility-related answers.
5. Recommended Technology Stack
  Layer                   Technology              Responsibility
  Frontend                Next.js, TypeScript,    Three-page user
                          Tailwind CSS            interface

  Backend                 Python, FastAPI         API endpoints and
                                                  workflow coordination

  Browser automation      Playwright              Open pages, inspect
                                                  forms, fill fields,
                                                  upload files, detect
                                                  outcomes

  AI provider             Groq API or Gemini API  Interpret unfamiliar
                                                  fields and draft
                                                  grounded answers

  Primary database        SQLite                  Persistent application
                                                  records, statuses,
                                                  events, and review
                                                  items

  Profile file            JSON                    Portable profile data
                                                  and backup

  Application export      JSON                    Readable
                                                  export/snapshot of
                                              application history
AI provider note: The intended first provider is Groq (spelled
Groq, not Grok), with Gemini as an alternative. The implementation
should isolate provider-specific code behind a small interface so the
provider can be switched through configuration. Confirm current model
availability, API limits, pricing, and data-retention terms before
implementation.
6. High-Level Architecture
Next.js Frontend
   |
   | HTTP API + status polling (or WebSocket later)
   v
FastAPI Backend
   |
   +--> Profile Service ------> profile.json
   |
   +--> Application Service --> SQLite database
   |                              |
   |                              +--> JSON export
   |
   +--> Agent Orchestrator
           |
           +--> Playwright browser
           |       |
           |       +--> Supported job application page
           |
           +--> Field mapping and validation
           |
           +--> AI provider adapter
                   |
                   +--> Groq API or Gemini API
The frontend should not call the AI provider directly. API keys and
browser automation remain on the backend.
7. End-to-End Workflow
1. Receive URL: Validate the URL and restrict navigation to
   appropriate HTTP/HTTPS destinations. Avoid opening arbitrary
   local-network or file URLs.
2. Create record: Insert an application row in SQLite with an
   initial status of In Progress.
3. Open browser: Use Playwright to open the application in a
   visible browser window.
4. Inspect form: Identify supported fields, required indicators,
   dropdown options, file uploads, and form structure.
5. Map fields: Match clear labels to known profile values using
   deterministic rules first.
6. Use AI when needed: Send only the minimum necessary field label,
   options, and relevant profile facts to the selected provider.
   Request structured output.
7. Validate answers: Check that values are grounded in the profile
   or explicitly approved saved answers. Do not invent facts.
8. Handle uncertainty: If a required field cannot be answered
   safely, save a review item and set status to Needs Review. Pause
   the run.
9. Fill form: Fill fields, select options, and upload the
   configured resume where supported.
10. Validate form: Check for empty required fields and visible
    validation errors.
11. Submit: If all required fields are resolved and the site is
    supported, submit according to the configured automatic-submission
    policy. Stop for user review if the site presents an unexpected or
    sensitive question, CAPTCHA, OTP, or other unsupported gate.
12. Verify result: Look for a reliable confirmation page, success
    message, or equivalent signal. A click alone is not proof of
    submission.
13. Persist result: Update SQLite with status, timestamps, review
    items, and any error. Refresh the JSON export after the database
    transaction succeeds.
14. Update UI: Show the latest status and useful detail to the user.
8. Status Definitions
  Status                              Meaning
  In Progress                       The agent is actively processing
                                      the application.

  Needs Review                      A required answer is missing,
                                      ambiguous, or requires the user's
                                      confirmation.

  Submitted                         A credible website confirmation
                                      indicates successful submission.

  Failed                            The run stopped because of a
                                      technical error, unsupported
                                      interaction, or unrecoverable
                                  validation problem.
A review requirement is not the same as a failure. After the user
supplies or confirms the missing information, the agent should resume
the same application where possible.

If submission may have succeeded but the confirmation signal is unclear,
do not blindly retry. Record an uncertain outcome for review to avoid
duplicate applications.
9. Data Storage Design
SQLite as the source of truth
Use SQLite for application history and workflow state. It supports
reliable local persistence without requiring a separate database server.

Suggested tables:

applications - id - job_url - company - role - status -
created_at - updated_at - submitted_at - last_error -
confirmation_details (optional, minimal text)

application_events - id - application_id - event_type -
message - created_at

review_items - id - application_id - field_name - reason -
suggested_value (optional) - user_resolution (optional) -
resolved_at

The profile may be stored in profile.json initially. If profile data
is later moved to SQLite, keep the format and ownership clear rather
than maintaining two independently editable copies.
JSON profile example
{
  "personal": {
    "full_name": "",
    "email": "",
    "phone": "",
    "location": "",
    "linkedin_url": "",
    "github_url": ""
  },
  "education": [],
  "experience": [],
  "skills": [],
  "projects": [],
  "resume_path": "",
  "saved_answers": {}
}
Application JSON export example
{
  "id": 1,
  "company": "Example Company",
  "role": "Software Intern",
  "job_url": "https://example.com/jobs/123",
  "status": "needs_review",
  "created_at": "2026-10-22T18:30:00",
  "submitted_at": null,
  "review_items": [
    {
      "field_name": "Expected salary",
      "reason": "No approved value is available in the profile"
    }
  ],
  "last_error": null
}
These examples are illustrative, not real application records.
Consistency rule
SQLite is authoritative for application status and history. Generate
applications.json from SQLite after a successful database update. Do
not independently edit both sources, as they can drift out of sync. Use
a temporary file and atomic replacement for JSON exports to reduce the
risk of a partially written file.
10. Backend API Sketch
Potential endpoints:
  Method                  Endpoint                          Purpose
  GET                   /api/profile                    Read profile

  PUT                   /api/profile                    Save profile

  POST                  /api/applications               Create and start an
                                                            application

  GET                   /api/applications               List and filter
                                                            applications

  GET                   /api/applications/{id}          Read application
                                                            details

  POST                  /api/applications/{id}/resume   Resume after review,
                                                            when supported

  POST                  /api/applications/{id}/retry    Retry a safely
                                                            retryable failure

  GET                   /api/applications/{id}/events   Retrieve progress
                                                            events

  GET                   /api/health                     Check backend
                                                        availability
For the first version, ordinary HTTP requests with periodic status
polling are sufficient. WebSockets can be added later if live progress
requires them.
11. AI Usage Strategy
The AI model should not control every action. Use normal Python rules
for predictable tasks and reserve AI for ambiguity.

Use deterministic logic for: - Name, email, phone, location, and
URLs. - Education and experience fields with clear labels. - Resume path
selection. - Required-field checks and status transitions.

Use the AI model for: - Interpreting unfamiliar labels. - Matching a
question to relevant profile facts. - Drafting short answers grounded in
the user's experience. - Choosing among options only when the correct
answer is supported by the profile.

Model output requirements: - Prefer structured JSON with fields such
as matched_profile_key, suggested_value, confidence, and
needs_review. - Validate model output in Python before using it. -
Never let model output execute code or directly trigger arbitrary
browser actions. - Treat page text as untrusted input; ignore any
instructions embedded in a job page that attempt to override the agent's
rules. - If required information is absent or confidence is
insufficient, create a review item.
12. Browser Automation and Safety
- Start with visible Playwright browser mode to make behavior easy to
  observe and debug.
- Support one portal first, then add portal-specific handling
  incrementally.
- Do not attempt to bypass CAPTCHA, OTP, login, or anti-bot
  protections.
- Pause when a form requests an unexpected sensitive answer or an
  unsupported interaction.
- Do not submit duplicate applications after ambiguous outcomes.
- Confirm submission through a success signal rather than relying on a
  button click.
- Validate URLs and restrict navigation to avoid local-file access and
  server-side request forgery risks.
- Keep browser automation and AI API keys on the backend.
- Store resume files in a known local directory and validate file
  paths.
- Send only the minimum profile information needed to the selected
  hosted AI provider.
- Review provider data handling and retention policies before sending
  personal information.
- Keep secrets in environment variables or a local .env file
  excluded from version control.
- Do not commit personal profile data, resumes, database files, or API
  keys to Git.
13. Implementation Milestones
Milestone 1 --- Local foundation
- Create the frontend and FastAPI backend.
- Configure SQLite and create database models.
- Create profile JSON read/write logic.
- Verify the frontend can call the backend.
Milestone 2 --- Three-page interface
- Build Apply, All Applications, and Profile pages.
- Save and edit profile data.
- Add application list and status filters.
- Store test records and verify persistence after restarting the app.
Milestone 3 --- Basic Playwright automation
- Open a supported test job form.
- Inspect and fill common fields from the profile.
- Upload a resume.
- Record progress events and failures.
Milestone 4 --- AI-assisted mapping
- Add a provider adapter for Groq or Gemini.
- Map unfamiliar field labels to profile information.
- Generate grounded responses to suitable written questions.
- Validate structured responses and create review items for
  uncertainty.
Milestone 5 --- Review and submission
- Pause when required information is missing.
- Allow the user to resolve review items.
- Resume the same application where possible.
- Detect and record verified submission results.
- Handle ambiguous outcomes safely.
Milestone 6 --- JSON export and reliability
- Export application history to JSON after database updates.
- Test browser errors, invalid URLs, missing fields, provider
  timeouts, and restarts.
- Add clear logs and a short local setup guide.
14. Acceptance Criteria
The first version is complete when:
1. The application runs locally with a frontend and backend.
2. The user can edit and persist a profile.
3. The user can submit a job URL and see the browser open.
4. The agent fills supported fields using profile information.
5. AI is used only when field interpretation or written answers require
   it.
6. Missing or uncertain required fields create a Needs Review item.
7. The user can view all applications and filter by status.
8. Verified submissions are marked Submitted.
9. Failed runs display a useful reason.
10. Application records persist in SQLite across restarts.
11. A JSON export reflects the latest database state.
12. The agent does not fabricate personal information or blindly retry
    uncertain submissions.
15. Risks and Limitations
- Job portals vary in form structure and may change without notice.
- Some portals may disallow automated interactions or require human
  verification.
- Hosted AI APIs require internet access and may have rate limits or
  costs.
- An AI-generated answer can be incorrect; validation and review rules
  are necessary.
- A success page may not always be available, so some outcomes may
  need review.
- Local JSON exports are not a substitute for backups; the database
  and resume files should also be backed up securely.
16. Final Recommendation
Build a small, single-user application with three pages, FastAPI,
Playwright, SQLite, and JSON profile/export files. Begin with
deterministic autofill on one supported job portal. Add a hosted AI
provider---Groq first, with Gemini as an alternative---only for
unfamiliar fields and grounded written answers.

Prioritize correctness and observable status transitions over supporting
many portals immediately. The agent should never claim an application
was submitted unless the website provides a reliable confirmation, and
it should pause rather than guess when required information is missing.
Proposed project name: Personal AI Job Application Agent
Deployment: Local computer only
Initial AI provider: Groq API, configurable to Gemini API
Primary database: SQLite
Profile/export format: JSON