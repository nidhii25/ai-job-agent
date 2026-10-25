# Phase 3: Basic Playwright Automation - Log Report

**Date:** 2026-10-25
**Status:** Completed (Phase 3 checkpoint)

> **Later update:** Verified submission, review-item resolution, manual
> login/CAPTCHA pauses, and uncertain-outcome handling were implemented
> afterward in the submission-first Phase 5 work. See `phase_4_log.md`.
> Statements below describe the Phase 3 checkpoint before submission existed.

## What Was Built

### Browser lifecycle (Task 3.1)
- Playwright and Chromium are installed in `backend/venv`.
- `backend/automation/browser.py` launches a fresh Chromium browser for each
  application run and always closes it.
- Visible browser mode is the default (`BROWSER_HEADLESS=false`). The filled
  form stays on screen for `BROWSER_CLOSE_DELAY_SECONDS` (default 5) so the
  user can observe the result.
- Runs are serialized with a process lock. Only one visible browser session is
  active at a time; a second application waits instead of racing the first
  browser's close.

### Greenhouse form inspection (Task 3.2)
- `backend/automation/greenhouse.py` recognizes both modern Greenhouse
  (`form#application-form`) and legacy (`form#application_form`) markup.
- It inspects all inputs, selects, textareas, radio groups, checkbox groups,
  and file inputs, and records:
  - field id/name/type/tag
  - visible label and question text
  - required state from `required`, `aria-required`, an asterisk, or a
    required group
  - native select options
  - React-select combobox role
  - current value, checked state, and file count
- Hidden proxy inputs used by React-select (`tabindex="-1"`,
  `aria-hidden="true"`, `requiredInput`) are filtered out.
- If the form is not on the page, one visible "Apply" button/link is clicked
  and the form is checked again.
- Company and role are read from `h1`, `.company-name`, Open Graph metadata,
  and the page title.

### Deterministic field filling (Task 3.3)
- Standard fields map from the profile:
  - first name, last name, full name fallback split
  - email, phone
  - location / candidate location / city
  - country
  - LinkedIn, GitHub, portfolio/website
- Native `<select>` dropdowns choose the approved saved answer that matches an
  option.
- React-select comboboxes (used by current Greenhouse boards) are opened, the
  approved answer is typed, and the matching `role="option"` is clicked.
- Radio and checkbox groups are matched against approved saved answers.
- Resume upload uses the saved `profile.resume_path` and fails review-safely
  if the file is missing.
- Cover-letter textareas are filled from `profile.cover_letter`.
- Unknown required fields are never guessed; they become review items.
- Values are never fabricated. A field with no profile value or approved saved
  answer is left empty, and a required one creates a review item.

### Events and failure handling (Task 3.4)
- Every run writes committed SQLite events as it progresses:
  - `run_started`, `browser_opened`, `navigated`
  - `job_details_detected`, `form_inspected`
  - `field_filled`, `resume_uploaded`
  - `review_item_created`
  - `form_filled`, `automation_complete`
  - `failed`
- Navigation errors, browser errors, unsupported portals, and missing forms
  set status `Failed`, store `last_error`, and write a `failed` event. The
  existing UI displays the reason.
- A successful fill sets status `Needs Review` and records
  "Form filled. Automatic submission is added in Phase 5."
- `POST /api/applications/{id}/retry` now actually re-runs the browser for a
  failed application.
- `POST /api/applications/{id}/resume` returns HTTP 409 while unresolved review
  items exist, because review resolution is Phase 5.
- URL validation now blocks localhost/private-network destinations unless
  `ALLOW_LOCAL_URLS=true`. This is an SSRF guard; it is off by default.

### UI and storage changes
- Moved SQLite/profile helpers from `main.py` into `backend/storage.py` so the
  API and automation share one implementation.
- Added profile fields: first name override, last name override, country,
  portfolio/website URL.
- Apply page shows live field counts including `resume_uploaded`, and explains
  when a run is still in progress.
- The Apply page's old "browser automation is added in Phase 3" placeholder is
  gone.

### Local Greenhouse-shaped test form
- `GET /test/greenhouse` serves `backend/test_form.html`, which mirrors current
  Greenhouse markup:
  - `#application-form`, `#first_name`, `#last_name`, `#email`, `#phone`
  - Country and Candidate Location comboboxes with `role="option"` menus
  - hidden `#resume` file input
  - native select, radio group, optional text, and one required unsaved field
    ("Expected salary") to exercise review items
  - a submit button that intentionally does nothing
- `GET /test/not-a-form` serves a non-application page used to test the
  unsupported-portal failure path.

## Verification

All commands were run from the repository root.

1. **Phase 3 API test** - `backend\venv\Scripts\python.exe tests\test_phase3_api.py`
   - 32 checks passed against the local test form and unsupported page.
   - Verified company/role detection, 11 filled/uploaded fields, resume upload,
     all expected events, exactly one review item, and a useful failure reason.
   - Run twice: once headless and once with a visible browser. The first headed
     run exposed a cross-run page-closing race; serializing runs fixed it and
     the headed run then passed all 32 checks.

2. **Full UI E2E** - `backend\venv\Scripts\python.exe tests\e2e_phase2.py`
   - 5 checks passed with zero console/page errors:
     navigation, profile + saved answers + resume persistence, live automation
     with company/role/review item, list/filter/detail, and clean rendering.
   - The test now uses the local Greenhouse-shaped form and waits for the real
     run to finish.

3. **Frontend** - `npm run lint` and `npm run build` both pass. Routes:
   `/`, `/apply`, `/applications`, `/profile`.

4. **Restart persistence**
   - Created an application, waited for `Needs Review`, stopped the backend,
     restarted it, and re-fetched the record.
   - Status, company, role, all 19 events, the review item, the profile, and the
     uploaded resume path were all still present.

## Known Limitations (intentional for Phase 3)

- Nothing is submitted and no submit button is clicked. Success ends at
  `Needs Review`; verified submission is Phase 5.
- AI is not used yet. Unknown required fields receive a deterministic review
  item instead of an inferred answer (Phase 4).
- Review items cannot be resolved yet; the resume endpoint returns 409 until
  Phase 5 adds resolution.
- Cover-letter **file** uploads are not supported; only the saved cover-letter
  text is used.
- Greenhouse selectors were checked against current live Greenhouse HTML, but
  the automated fill runs were performed against the local Greenhouse-shaped
  fixture only. No live employer application was submitted or modified.
- Visible browsers close after the configured delay. There is no long-lived
  browser window to inspect after the run.
- The local test form is reachable only when the backend runs with
  `ALLOW_LOCAL_URLS=true`, because the default SSRF guard blocks it.

## Configuration

```env
BROWSER_HEADLESS=false
BROWSER_CLOSE_DELAY_SECONDS=5
BROWSER_SLOW_MO_MS=0
BROWSER_TIMEOUT_MS=15000
NAVIGATION_TIMEOUT_MS=30000
ALLOW_LOCAL_URLS=false
```

To run the Phase 3 tests:

```powershell
# Terminal 1 - backend configured for automated local testing
cd backend
$env:BROWSER_HEADLESS='true'
$env:BROWSER_CLOSE_DELAY_SECONDS='0'
$env:ALLOW_LOCAL_URLS='true'
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000

# Terminal 2 - test API or UI
.\backend\venv\Scripts\python.exe tests\test_phase3_api.py
.\backend\venv\Scripts\python.exe tests\e2e_phase2.py
```

## Post-Phase 6 hardening (2026-10-25)

A later safety pass corrected form-filling issues found on live Greenhouse
forms. Full details are in `phase_7_smart_matching_log.md`.

- The runner now waits for network idle and a short settle period after
  navigation. Filling immediately after `DOMContentLoaded` could be wiped by a
  React re-render.
- React-select option waits now poll for up to 2 seconds instead of assuming a
  400 ms delay. This fixes delayed education dropdowns.
- School, degree, and discipline controls use equivalent option matching:
  `B.Tech` → `Bachelor's Degree`, unlisted school → `Other / Not Listed`,
  `Computer Science` → `Computer Science`.
- Optional fields that cannot be matched are skipped without creating a review
  item. Required fields still create review items.
- Eligibility inference was removed. Work authorization and sponsorship are
  explicit-only; citizenship, security clearance, legal attestations,
  demographics, and addresses always require an explicit saved answer.
- Long legal paragraphs and demographic labels can no longer trigger State/City
  derivation through substring matches.
- Live GRVTY fill-only verification selected the correct education options and
  left the six genuinely unsupported required fields in Needs Review.

Regression after the hardening: Phase 3 API 33/33, submission 51/51, Phase 6
48/48, fill-only 11/11, AI mapper 21/21, smart matching 44/44, resume parser
10/10, UI e2e 7/7, frontend lint/build pass.

## Next Phase

Phase 4 (AI-assisted mapping) remains deferred. The submission-first Phase 5
work (review resolution, safe submission, verified confirmation, ambiguous
outcome handling, manual login/CAPTCHA pauses) is documented in `phase_4_log.md`.
The next remaining work is AI mapping (Phase 4), Phase 6 JSON export/reliability,
and the final setup guide. Phase 7 hardening is documented in
`phase_7_smart_matching_log.md`.
