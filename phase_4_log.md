# Phase 4 Substitute: Submission-First Implementation Log

**Date:** 2026-10-25
**Status:** Completed (Phase 5 scope implemented before Phase 4 AI)

## Why the order changed

The original plan put AI-assisted field mapping (Phase 4) before submission
(Phase 5). After reviewing a MyGreenhouse search link, the user clarified the
actual target:

- Paste one direct Greenhouse job-board link, not a search page.
- Fill the company's public Greenhouse board form.
- Submit automatically when the form is fully filled and verified.
- Pause for the user when a required answer is missing.
- Pause for manual login; never automate or bypass OTP/email codes.
- Do not integrate company portals or MyGreenhouse Quick Apply yet.

This log covers the submission-first work, which maps to the Phase 5 checklist
in `implementation_plan.md`. AI mapping was implemented afterward; see
`phase_4_ai_log.md`.

## What was built

### Review resolution (Phase 5.1)

- New endpoint:
  `POST /api/applications/{id}/review-items/{item_id}/resolve`
- Stores `user_resolution` and `resolved_at`, and records a
  `review_item_resolved` event.
- New shared frontend component `ReviewItems.tsx` appears on both Apply and
  All Applications detail views.
- Unresolved items show an answer field and "Save answer"; resolved items show
  the stored answer.
- File-related review items point the user to My Profile/upload.

### Resume and re-fill (Phase 5.2)

- The resume endpoint now permits resumption only when every review item is
  resolved and no submission is pending/unconfirmed.
- Resolved answers are loaded for that application and merged into the filler
  lookup, including standard fields, saved-answer fields, selects, comboboxes,
  and radio groups.
- The agent reloads the page and refills the whole form. This is not an
  incremental DOM resume, but it uses the same application record and all
  stored resolutions.

### Submission logic (Phase 5.3)

- Auto-submit only when:
  - zero review items remain,
  - the page is a supported Greenhouse host (plus `localhost`/`127.0.0.1` for
    the local fixture),
  - an enabled Submit button is present.
- The attempt is recorded *before* clicking (`submission_outcome = pending`) so
  a crash cannot be mistaken for a safe retry.
- MyGreenhouse search URLs are rejected with HTTP 400 and a clear message.

### Confirmation verification (Phase 5.4)

- The runner waits for a real signal:
  - URL/path ending in `/confirmation`, or
  - visible confirmation text such as "Thank you for applying" or "Your
    application has been received" when the form is gone.
- A button click alone is never treated as success.
- Confirmation details store the signal type, URL, message snippet, and
  verification time.

### Persistence (Phase 5.5)

- New application columns (migrated in place):
  - `submission_attempted_at`
  - `submission_outcome` (`pending`, `confirmed`, `uncertain`, `rejected`)
- Submitted records persist `submitted_at`, `confirmation_details`,
  `last_error = NULL`, and `status = Submitted`.
- JSON export remains Phase 6.

### Ambiguous and rejected outcomes (Phase 5.6)

- **Uncertain** (click happened, no confirmation): status `Needs Review`,
  `submission_outcome = uncertain`, clear explanation, and resume is blocked.
- **Rejected** (visible validation errors): status `Needs Review`,
  `submission_outcome = rejected`, error message stored; resume is allowed
  after the user fixes the issue.
- UI actions for uncertain outcomes:
  - "I verified it was submitted" → manual confirmation, status `Submitted`.
  - "It was not submitted" → explicitly unlocks another attempt.
- These actions require user confirmation dialogs because both can affect
  duplicate-submission risk.

### Manual login and CAPTCHA pauses

- The browser now uses a persistent Chromium profile
  (`BROWSER_PROFILE_DIR`, default `backend/browser_profile`).
- If a sign-in/OTP wall is detected, the visible browser stays open and the run
  waits up to `LOGIN_WAIT_SECONDS` (default 300) for the user to complete it.
  The agent never reads or enters the code.
- The live Greenhouse board loads reCAPTCHA Enterprise. If a challenge appears
  after submit, the run records `manual_verification_required`, keeps the
  browser open, and waits up to `CAPTCHA_WAIT_SECONDS` (default 300) for the
  user to solve it. It does not bypass or solve the challenge.
- If the challenge clears and a confirmation appears, the run is marked
  `Submitted`; otherwise it becomes `uncertain`.

### Test fixture

`backend/test_form.html` now supports:

- successful submission with a visible confirmation,
- `?outcome=uncertain` (click does nothing / no confirmation),
- `?outcome=rejected` (visible validation error),
- `?login=1` (simulated sign-in wall that reveals the form after a wait),
- `?captcha=1` (simulated challenge that clears after a wait).

The test-form route sends `Cache-Control: no-store` so browser-profile caching
cannot hide fixture changes.

## Verification

All checks were run against the local fixture. No live employer form was
submitted or modified.

| Check | Result |
|---|---|
| `tests/test_phase3_api.py` | 33/33 |
| `tests/test_submission_api.py` | 51/51 |
| `tests/e2e_phase2.py` (UI flow through submission) | 7/7 |
| `npm run lint` | passed |
| `npm run build` | passed |
| Live Greenhouse inspection (Figma board) | form, submit button, reCAPTCHA, `/confirmation` path detected; no submit |

The submission API test covers:

- full auto-submit and confirmation,
- review pause → resolve → resume → submit,
- unresolved resume blocked,
- manual login pause/completion,
- CAPTCHA pause/completion,
- uncertain outcome and automatic resubmission block,
- manual confirmation,
- rejected form and allowed resume,
- MyGreenhouse search URL rejection.

## Known limitations

- AI-assisted mapping is not implemented (Phase 4 deferred). Unknown required
  questions still become review items.
- Resume is a reload-and-refill, not incremental from the exact paused field.
- Auto-submit is limited to Greenhouse hosts (and the local test server).
- A custom confirmation page with no URL change and no recognizable success
  text will be treated as uncertain. The user can verify manually.
- CAPTCHA/OTP are never automated; unattended runs can pause waiting for the
  user.
- Cover-letter file uploads and unsupported required file uploads still need
  manual handling.
- JSON export, broader error testing, logging polish, and the setup guide are
  Phase 6.
- No live employer application was submitted during testing.

## Configuration used for tests

```env
BROWSER_HEADLESS=true
BROWSER_CLOSE_DELAY_SECONDS=0
ALLOW_LOCAL_URLS=true
SUBMISSION_TIMEOUT_MS=4000
LOGIN_WAIT_SECONDS=20
CAPTCHA_WAIT_SECONDS=20
BROWSER_PROFILE_DIR=<temporary test profile>
```

Commands:

```powershell
backend\venv\Scripts\python.exe tests\test_phase3_api.py
backend\venv\Scripts\python.exe tests\test_submission_api.py
backend\venv\Scripts\python.exe tests\e2e_phase2.py
cd frontend; npm run lint; npm run build
```

## Files changed

- `backend/storage.py`: submission columns, review resolution helpers.
- `backend/main.py`: review resolution, manual confirmation/not-submitted
  endpoints, resume guards, MyGreenhouse search rejection, no-store fixture.
- `backend/automation/browser.py`: persistent Chromium profile.
- `backend/automation/greenhouse.py`: resolved-answer filling, submit/confirmation
  detection, login/CAPTCHA signals.
- `backend/automation/runner.py`: submission-first orchestration and outcome
  handling.
- `backend/test_form.html`: confirmation, uncertain/rejected/login/CAPTCHA
  variants.
- `backend/.env.example`, `.gitignore`: browser profile and wait configuration.
- `frontend/src/lib/api.ts`: new endpoints/types.
- `frontend/src/components/ReviewItems.tsx`: shared review resolution UI.
- `frontend/src/app/apply/page.tsx`: review editing, resume/submit, manual
  verification, confirmation display.
- `frontend/src/app/applications/page.tsx`: same resolution/submission actions
  in the detail view.
- `tests/test_phase3_api.py`, `tests/e2e_phase2.py`,
  `tests/test_submission_api.py`: updated/new coverage.
