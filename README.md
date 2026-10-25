# Personal AI Job Application Agent

A local, single-user job application assistant for **Greenhouse** application
forms. It fills supported fields from your saved profile, pauses for answers it
cannot ground safely, verifies submission results, and keeps a durable history
of every run.

Planning a hosted or multi-user version? See
[`deployment_upgrade_plan.md`](deployment_upgrade_plan.md) for the architecture,
required security changes, and phased rollout plan.

The app has exactly three pages:

- **Apply** — paste a Greenhouse job link, upload a resume, start the run, watch
  progress, and answer review items.
- **All Applications** — filter, inspect, resume/retry, delete applications, and
  download the JSON export.
- **My Profile** — edit personal details, education, experience, skills,
  projects, resume, cover letter, work authorization, and saved answers.

## Current scope and safety rules

- Only Greenhouse application forms are supported in this version.
- Use a direct Greenhouse job-board link (for example
  `https://job-boards.greenhouse.io/company/jobs/1234567`). MyGreenhouse search
  links are rejected.
- The agent pauses instead of guessing when a required field cannot be answered
  from the profile or an explicit saved answer.
- Sensitive/eligibility questions (salary, authorization, sponsorship,
  demographics, criminal/background, IDs, etc.) are never sent to AI. Work
  authorization and sponsorship answers are filled only from an explicit
  work-authorization profile value or saved answer; the agent never infers them
  from country or location.
- AI-generated prose is shown as a review suggestion by default. It is not
  auto-filled unless `AI_AUTO_FILL_GENERATED=true`.
- CAPTCHA and login/OTP challenges are never bypassed. Complete them manually in
  the visible browser; the agent waits for the form to become available.
- A submission is marked **Submitted** only after a confirmation signal is
  observed (or you manually verify it after an uncertain result).
- An uncertain submission blocks automatic resubmission to avoid duplicates.
- Do not use test data for a real employer submission. Perform a fill-only review
  with your real profile/resume first.
- The **Apply** page has a **Submit automatically after filling** checkbox. Turn
  it off for a fill-only run: the form is filled and the record stays in
  **Needs Review** with no submission. After inspecting it, click
  **Resume & Submit** to enable automatic submission for that run.
- `AUTO_SUBMIT` sets the default state of the checkbox. An explicit choice on the
  Apply page is stored with that application.

## Prerequisites

- Windows 10/11 (the included start scripts are PowerShell).
- Python 3.11+.
- Node.js 20+ and npm.
- A Gemini API key if you want AI-assisted mapping. Deterministic filling works
  without AI.
- Internet access for Greenhouse and Gemini. The browser profile, SQLite
  database, profile JSON, resumes, export, and logs stay on this machine.

## First-time setup

Open PowerShell in the project root (`intern task`).

### 1. Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env
```

Edit `backend\.env`:

- Set `GEMINI_API_KEY` to your key if using AI.
- Keep `AI_ENABLED=false` until the key is configured; set it to `true` when
  ready.
- Keep `ALLOW_LOCAL_URLS=false` for real use. Set it to `true` only for local
  fixture tests.
- Keep `BROWSER_HEADLESS=false` if you want to watch and manually handle login or
  CAPTCHA prompts.

### 2. Frontend

```powershell
cd ..\frontend
npm install
```

### 3. Optional environment overrides

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_PATH` | `backend/database.db` | SQLite database location |
| `PROFILE_PATH` | `backend/profile.json` | Profile JSON location |
| `UPLOAD_DIR` | `backend/uploads` | Resume uploads |
| `APPLICATIONS_EXPORT_PATH` | `backend/applications.json` | JSON export location |
| `LOG_DIR` | `backend/logs` | Rotating log directory |
| `LOG_LEVEL` | `INFO` | Log verbosity |
| `BROWSER_PROFILE_DIR` | `backend/browser_profile` | Persistent Chromium profile |
| `AI_ENABLED` | `false` | Enable Gemini mapping when a key exists |
| `AI_CONFIDENCE_THRESHOLD` | `0.75` | Minimum auto-fill confidence |
| `AI_MAX_FIELDS_PER_RUN` | `8` | AI call budget per run |
| `AI_AUTO_FILL_GENERATED` | `false` | Auto-fill AI-written prose |
| `AUTO_SUBMIT` | `true` | Default for the Apply-page automatic submission checkbox |
| `SUBMISSION_TIMEOUT_MS` | `30000` | Wait for confirmation |
| `LOGIN_WAIT_SECONDS` | `300` | Manual login/OTP wait |
| `CAPTCHA_WAIT_SECONDS` | `300` | Manual CAPTCHA wait |

See `backend/.env.example` for the complete list.

## Running the app

From the project root, in two terminals:

```powershell
.\start-backend.ps1
```

```powershell
.\start-frontend.ps1
```

Then open <http://localhost:3000>.

You can also start both with:

```powershell
.\start-app.ps1
```

Manual commands:

```powershell
cd backend
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm run dev
```

Backend health: <http://127.0.0.1:8000/api/health>

## Using the three pages

### Apply

1. Go to **My Profile**, upload your resume under **Autofill from Resume**, and
   review the extracted fields. Add any missing details and saved answers the job
   form needs, then click **Save Profile**.
2. Open **Apply**, paste a direct Greenhouse job-board application URL, and choose
   whether to submit automatically after filling. You can also replace the resume
   and cover letter files there.
3. Start the application. The visible browser opens and fills supported fields.
4. If the run stops at **Needs Review**, open **All Applications**, select the
   application, and answer each open review item. Then click **Resume**.
5. If the site asks you to sign in or solve a CAPTCHA, do it in the visible
   browser. The agent waits; it never bypasses verification.
6. A confirmed run ends **Submitted**. An unclear result ends **Needs Review**
   with an uncertain outcome; verify it on the employer site before using a
   manual confirmation action.

### All Applications

- Filter by status and open a record to see company, role, timestamps, event
  history, review items, confirmation details, and errors.
- **Download JSON export** saves `applications.json` from SQLite.
- Retry is available only for safely retryable failures. Uncertain submissions
  cannot be retried automatically.
- Delete removes the application and its events/review items.

### My Profile

- Edits are stored in `backend/profile.json`.
- **Autofill from Resume** accepts PDF, DOCX, TXT, and RTF files. It extracts
  contact details, education, experience, skills, and projects into the form;
  review the values and click **Save Profile** to keep them.
- Legacy `.doc` files can be stored but are not parsed automatically. Save them
  as PDF or DOCX to use autofill.
- Resume text is sent to Gemini only when AI is enabled. Extracted values are
  checked against the resume text before they appear in the form, and missing
  facts are left blank instead of invented.
- Resume and cover letter files can be chosen with visible file buttons. Uploads
  are stored in `backend/uploads`, and their paths are saved in the profile.
- Uploading a cover letter extracts its text into the cover letter field. The file
  itself is also used when a Greenhouse form requires a cover-letter upload.
- Saved answers are matched by question text. Sensitive questions require an
  explicit saved answer or, for work authorization, an explicit work
  authorization profile value; AI is not allowed to answer them. Education
  fields such as school, degree, major, GPA, and dates are filled from a
  uniquely saved education record, with AI mapping available for other grounded
  fields when enabled.
- Keep your profile and resume accurate. The agent is designed to pause rather
  than invent personal facts.

## JSON export

`backend/applications.json` is regenerated after each relevant database update.
Writes use a temporary file plus `os.replace`, so readers never see a partially
written file.

The export schema is:

```json
{
  "exported_at": "2026-10-25T12:00:00+00:00",
  "application_count": 1,
  "applications": [
    {
      "id": 1,
      "job_url": "https://job-boards.greenhouse.io/example/jobs/123",
      "company": "Example",
      "role": "Engineer",
      "status": "Submitted",
      "created_at": "...",
      "updated_at": "...",
      "submitted_at": "...",
      "last_error": null,
      "confirmation_details": "{\"signal\":\"success_text\",...}",
      "submission_attempted_at": "...",
      "submission_outcome": "confirmed",
      "review_items": [],
      "events": []
    }
  ]
}
```

You can also download it from **All Applications** or:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/api/applications/export -OutFile applications.json
```

## Logs

Rotating logs are written to `backend/logs/jobagent.log` (2 MB per file, 5
backups by default). They include:

- application creation and status transitions,
- browser/run milestones and stored events,
- field and review-item counts (labels only, not profile values),
- AI call metadata (field label, action, confidence, matched key, errors),
- export and API actions.

Logs are designed not to contain contact details, resume contents, or API keys.
Field labels, workflow messages, and short AI reasons can appear. The Gemini key
is scrubbed from provider error messages. Treat logs as local personal data.

## Tests

Start a test backend first. Use `AI_ENABLED=false` for deterministic tests:

```powershell
cd backend
$env:ALLOW_LOCAL_URLS="true"
$env:BROWSER_HEADLESS="true"
$env:BROWSER_CLOSE_DELAY_SECONDS="0"
$env:SUBMISSION_TIMEOUT_MS="4000"
$env:AI_ENABLED="false"
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

In another terminal, run:

```powershell
backend\venv\Scripts\python.exe -m unittest tests.test_ai_mapper -v
backend\venv\Scripts\python.exe tests\test_phase3_api.py
backend\venv\Scripts\python.exe tests\test_submission_api.py
backend\venv\Scripts\python.exe tests\test_phase6_api.py
```

For the fill-only safety test, restart the test backend with `AUTO_SUBMIT=false`,
then run:

```powershell
backend\venv\Scripts\python.exe tests\test_fill_only_api.py
```

For the UI test, start the frontend too, then:

```powershell
backend\venv\Scripts\python.exe tests\e2e_phase2.py
```

Frontend checks:

```powershell
cd frontend
npm run lint
npm run build
```

The tests create and delete their own application records and reset the profile
to empty at the end. Local fixture tests must never be used as real employer
submissions.

## Data, backups, and privacy

Local runtime files (gitignored):

- `backend/database.db` — application history, events, review items.
- `backend/profile.json` — profile and saved answers.
- `backend/uploads/` — resumes.
- `backend/applications.json` — JSON export.
- `backend/logs/` — rotating logs.
- `backend/browser_profile/` — Chromium cookies/session state.
- `backend/.env` — API key and configuration.

Back up the database and profile/resume files together. The JSON export is a
portable snapshot, not a substitute for a database backup.

Recommended security hygiene:

- Never commit `backend/.env` or personal data.
- Rotate the Gemini API key if it may have been exposed.
- Keep the backend bound to `127.0.0.1`; do not expose it to a network.
- Keep `ALLOW_LOCAL_URLS=false` outside local tests.

## Troubleshooting

**`Cannot reach the backend` in the UI**
- Confirm the backend is running at <http://127.0.0.1:8000/api/health>.
- Confirm `frontend/.env.local` does not point at a different backend URL.
- Check that `ALLOWED_ORIGINS` includes the frontend origin.

**`Executable doesn't exist` / Playwright browser missing**
```powershell
cd backend
.\venv\Scripts\python.exe -m playwright install chromium
```

**The browser opens but no form is found**
- Use a direct Greenhouse job-board application link, not a search page.
- Some employers use a different ATS; only Greenhouse is supported now.
- Try again after the page fully loads.

**The app is waiting at login or CAPTCHA**
- Finish it manually in the visible browser.
- The wait timeout is controlled by `LOGIN_WAIT_SECONDS` and
  `CAPTCHA_WAIT_SECONDS`.
- The agent will not solve or bypass challenges for you.

**AI is not used**
- Check `AI_ENABLED=true`, `AI_PROVIDER=gemini`, and a non-empty
  `GEMINI_API_KEY`.
- Review the logs for `AI error` / quota / timeout messages.
- AI is optional; deterministic filling and review items still work.

**AI output is shown instead of filled**
- This is expected for generated prose. Review the suggestion, then edit it in
  the review item and resume.
- Only set `AI_AUTO_FILL_GENERATED=true` if you accept generated text being
  filled without a review step.

**Submission result is uncertain**
- Open the employer site and verify whether the application was received.
- If it was received, use **Confirm submission**; otherwise mark it not
  submitted before retrying.
- Do not click Submit again until you know the first attempt did not succeed.

**`ALLOW_LOCAL_URLS` blocked**
- This is the safety default. Only set it to `true` for local fixture tests.

**Export or logs are missing**
- Both are created on backend startup. Check the paths reported by
  `/api/health`.
- Ensure the `backend` directory is writable.

## Limitations

- Greenhouse only. Other ATS platforms are intentionally out of scope.
- Incremental resume at the exact paused field is not implemented. The agent
  safely reloads and refills using the profile plus stored review resolutions.
- Generated AI prose requires review unless explicitly enabled otherwise.
- A real employer submission still requires your real profile/resume, a job you
  actually want, and explicit approval after a fill-only review.
