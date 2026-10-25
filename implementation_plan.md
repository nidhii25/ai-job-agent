# Personal AI Job Application Agent - Implementation Plan

## Overview
A local, single-user web application to automate job application form-filling while maintaining reliable records. The application consists of three pages (Apply, All Applications, Profile) with a Next.js frontend, FastAPI backend, Playwright browser automation, SQLite database, and Groq/Gemini AI integration.

### Supported Portal: Greenhouse
- The first version will target Greenhouse job application portals specifically
- Greenhouse forms have a recognizable structure that can be autofilled with deterministic rules
- AI will be used for any unfamiliar field labels outside the known Greenhouse pattern
- All other portals can be added incrementally after the initial workflow is reliable
- **Greenhouse-specific field mapping will be implemented in Phase 3** (see Task 3.3)

---

## Phase 1: Local Foundation

### Task 1.1: Project Setup
- [x] Initialize Next.js project with TypeScript and Tailwind CSS (created successfully using `npm create next-app@latest . -- --typescript --tailwind --eslint --src-dir --app --import-alias "@/*"`)
- [x] Initialize FastAPI Python project (venv created, FastAPI and uvicorn already available)
- [x] Set up project directory structure (frontend/ and backend/ directories created)
- [x] Create `.env` template for API keys and configuration (created .env.example in backend)
- [x] Add `.env` to `.gitignore` (verified in Next.js project)

### Task 1.2: Backend Foundation
- [x] Create FastAPI app structure with basic endpoints (main.py created with profile, application, health endpoints)
- [x] Set up SQLite database connection and session management (init_db function creates applications, application_events, review_items tables)
- [x] Create database models based on the schema (applications, application_events, review_items tables with correct columns)
- [x] Implement profile JSON read/write logic (profile.json with load_profile() and save_profile() functions)
- [x] Create API endpoints: GET /api/profile, PUT /api/profile, POST /api/applications, GET /api/applications, GET /api/applications/{id}, POST /api/applications/{id}/resume, POST /api/applications/{id}/retry, GET /api/applications/{id}/events, GET /api/health
- [x] Verify frontend can call backend (frontend can reach /api/health endpoint successfully)

### Task 1.3: Frontend Foundation
- [x] Create Next.js pages structure (3-page layout) (app/ directory with page.tsx files)
- [x] Set up basic routing for /apply, /applications, /profile (Next.js app router)
- [x] Create basic UI scaffolding with Tailwind CSS (Tailwind configured via create-next-app)
- [x] Implement API call patterns to FastAPI backend (shared client in `frontend/src/lib/api.ts`)
- [x] Verify frontend-backend communication works (health check, profile read/write, CORS preflight)

### Task 1.4: Verification
- [x] Start the application locally (frontend + backend created and running)
- [x] Confirm frontend can reach backend endpoints (/api/health returns healthy status)
- [x] Test profile read/write functionality (GET /api/profile and PUT /api/profile work correctly)
- [x] Document any issues found (see Phase 1 log correction notes)

---

## Phase 1 Complete - Local Foundation Built

### Summary
All 14 tasks in Phase 1 are completed:
- ✅ Project setup: Next.js + TypeScript + Tailwind, FastAPI + SQLite
- ✅ Backend: All API endpoints implemented (profile, applications, events, review items)
- ✅ Database: Three tables created (applications, application_events, review_items)
- ✅ Profile JSON: read/write logic with default structure
- ✅ Frontend: Next.js app router with shared navigation and API client
- ✅ Communication: CORS configured for the local frontend; verified in a browser

Verification note (2026-10-25): the original venv did not contain FastAPI or
uvicorn, and `main.py` had an invalid `DATE` import. Both are fixed.
`backend/requirements.txt` and `backend/.env.example` now exist. Backend
endpoints, CORS preflight, frontend lint, production build, and the full
browser workflow were all re-tested successfully.

## Phase 2: Three-Page Interface

### Summary
Build the three main user interface pages following the project plan specifications.

### Task 2.1: Apply for a Job Page
- [x] Add URL input field with validation (frontend + backend validation)
- [x] Add "Start Application" button
- [x] Display current company/role when detectable
- [x] Show workflow stage and progress messages (from real SQLite events, polled every 3s)
- [x] Display fields filled vs fields requiring review
- [x] Add resume upload control (uploads to `backend/uploads`, updates profile)
- [x] Add resume after review/resume action link (calls the resume endpoint)

### Task 2.2: All Applications Page
- [x] Build application list with columns: company, role, URL, created date, updated date, status
- [x] Implement status filters: In Progress, Needs Review, Submitted, Failed (refetches on change)
- [x] Application detail view with:
  - Progress history (loaded from the detail endpoint)
  - Review items list
  - Error details
- [x] Add retry action for safely retryable failures
- [x] Add resume action where supported
- [x] Add delete action with a real DELETE endpoint

### Task 2.3: My Profile Page
- [x] Build profile editing interface with sections:
  - Personal details: full_name, email, phone, location, linkedin_url, github_url
  - Education: institution, degree, field_of_study, dates, gpa
  - Experience: employer, title, dates, responsibilities, achievements
  - Skills and projects
  - Resume file path and upload
  - Cover letter
  - Saved answers to common questions (add/edit/remove)
  - Work authorization and eligibility answers (explicit user input only)
- [x] Implement save profile functionality
- [x] Implement profile data persistence to JSON (SQLite stores application data)

### Task 2.4: Cross-Page Functionality
- [x] Ensure profile changes reflect across all pages
- [x] Add application list persistence after restart
- [x] Test all three pages work independently and together

### Phase 2 Verification (2026-10-25)
- ✅ `backend/requirements.txt` added; FastAPI and uvicorn installed in the venv
- ✅ Backend smoke test: health, profile PUT/GET, application create/list/detail/delete
- ✅ Resume upload endpoint accepts PDF/DOC/DOCX/TXT/RTF up to 10 MB and rejects others
- ✅ CORS preflight from `http://localhost:3000` returns the expected headers
- ✅ `npm run lint` passes with no errors
- ✅ `npm run build` succeeds (all routes compile)
- ✅ Playwright end-to-end test passes:
  - home redirects to `/apply` and the 3-link navigation renders
  - profile edits, saved answer, resume upload, save, and reload persistence
  - starting an application creates a real SQLite record and shows its events
  - application list, status filter, and detail view with events
  - no browser console or page errors during the run
- ✅ Restart test: an application record was still present after stopping and
  restarting the backend

The Apply page no longer simulates progress. It polls real application events
and shows the real status. (Phase 2 originally left applications `In Progress`
until Phase 3; Phase 3 now transitions completed fills to `Needs Review`.)

---

## Phase 3: Basic Playwright Automation

### Task 3.1: Browser Setup
- [x] Install Playwright and browsers (Playwright in the venv, Chromium installed)
- [x] Configure visible browser mode (default) for observability
- [x] Set up browser launch/close lifecycle management (fresh browser per run,
      configurable close delay, runs serialized with a lock)

### Task 3.2: Form Inspection
- [x] Navigate to a Greenhouse job application form
- [x] Identify and list form fields specific to Greenhouse structure (modern
      `#application-form` and legacy `#application_form`)
- [x] Detect required indicators (`required`, `aria-required`, asterisk, group)
- [x] Recognize dropdown options, checkboxes, radio groups, and file uploads
      (native selects, React-select comboboxes, checkbox/radio groups, files)
- [x] Extract form structure and labeling (field ids/names/types, labels,
      question text, required state, options, current values)

### Task 3.3: Profile-Based Field Filling
- [x] Map Greenhouse-specific text fields to profile data:
  - first name, last name (with full-name fallback), email, phone, location,
    country, LinkedIn, GitHub, website
- [x] Map Greenhouse dropdowns from profile / approved saved answers (native
      selects and React-select comboboxes)
- [x] Map Greenhouse checkboxes and radios from approved saved answers (e.g.,
      work authorization and sponsorship)
- [x] Implement resume upload using configured path (missing file creates a
      review item instead of failing silently)
- [x] Record progress events in SQLite (`field_filled`, `resume_uploaded`,
      `form_inspected`, etc.)

### Task 3.4: Error & Failure Handling
- [x] Record progress events (start, field_filled, form_inspected, etc.)
- [x] Capture and store failure reasons (navigation, browser, unsupported page,
      missing form)
- [x] Display useful error information in UI

### Task 3.5: Verification
- [x] Open a supported test job form using Playwright (local
      Greenhouse-shaped fixture at `/test/greenhouse`, plus selector review
      against current live Greenhouse markup)
- [x] Fill common fields from profile
- [x] Upload a resume
- [x] Verify progress events are stored
- [x] Test restart persistence

### Phase 3 Verification (2026-10-25)
- ✅ `tests/test_phase3_api.py`: 32 checks passed, headless and headed
- ✅ `tests/e2e_phase2.py`: 5 UI checks passed with zero console errors
- ✅ `npm run lint` and `npm run build` pass
- ✅ Restart test: status, company, role, all 19 events, review item, profile,
  and resume path survived a backend restart
- ✅ Unsupported page ends `Failed` with a clear reason
- ✅ Missing required answer creates a review item instead of guessing
- ✅ Phase 3 fill-only behavior ended at `Needs Review`; verified submission was
  implemented afterward in the submission-first Phase 5 work. See
  `phase_4_log.md`.

Details and limitations are recorded in `phase_3_log.md`.

---

## Phase 4: AI-Assisted Mapping

> **Ordering note (2026-10-25):** By user request, verified submission was
> implemented before AI mapping. AI mapping is now implemented with Gemini
> (see `phase_4_ai_log.md`). Phase 5 is implemented except for incremental
> "resume at the paused field" (the agent safely reloads and refills the same
> application). The JSON export is implemented in Phase 6.

### Task 4.1: AI Provider Adapter
- [x] Research current Groq model availability, limits, pricing, data-retention terms
  - Gemini was selected by the user; Groq is not implemented in this version.
- [x] Research Gemini API alternatives
  - Gemini 3.5 Flash is configured; model availability was checked against the
    live Gemini model list.
- [x] Create provider interface/abstraction layer
  - `automation/ai_mapper.py` contains the provider adapter, strict response
    validation, caching, retries, and run limits.
- [x] Configure API keys from environment variables
  - `GEMINI_API_KEY` is read from `backend/.env` (gitignored); `main.py` loads
    `.env` with `python-dotenv`.
- [x] Define Greenhouse field label patterns that can be handled deterministically (no AI needed)
  - Existing standard-field, saved-answer, select, combobox, radio, resume, and
    resolved-answer paths remain deterministic and skip AI.
- [x] Identify which Greenhouse label variations require AI interpretation
  - Required custom questions that do not match deterministic rules or saved
    answers are sent to AI, subject to a per-run limit.
- [x] Define Greenhouse-specific field label patterns that don't need AI

### Task 4.2: Unfamiliar Field Interpretation
- [x] Identify field labels that don't match deterministic rules
- [x] Send minimal necessary data to AI provider:
  - Field label and question text
  - Available options (if any)
  - Relevant profile facts (no name, email, phone, resume bytes, or cover-letter text)
- [x] Request structured output JSON with fields:
  - `matched_profile_key`
  - `answer_kind` (`direct_fact`, `generated`, or `none`)
  - `suggested_value`
  - `confidence` (0-1)
  - `needs_review` (boolean)
  - `reason`

### Task 4.3: Grounded Answer Generation
- [x] Use AI for written questions grounded in user experience
  - Generated prose is returned as a review suggestion by default. It is only
    auto-filled when `AI_AUTO_FILL_GENERATED=true`.
- [x] Validate model output in Python before using
- [x] Never let model output execute code or trigger browser actions

### Task 4.4: Response Validation
- [x] Check that values are grounded in profile or explicitly approved saved answers
- [x] Never invent facts or qualifications
- [x] If confidence insufficient or information absent → create review item
- [x] Structured validation logic for all AI responses
  - Sensitive/eligibility fields are never sent to AI.
  - Legal attestations, security clearance, citizenship, and home/mailing address
    are treated as sensitive too.
  - Option fields require an option match.
  - Direct-fact answers must be traceable to the profile or saved answers. The
    prompt receives no hardcoded derived eligibility facts.
  - Provider errors and timeouts fall back to deterministic review handling.
  - HTTP 429/quota errors stop further AI calls for that run.

### Task 4.5: Review Item Creation
- [x] Save review items when required field cannot be answered safely
- [x] Set field reason (e.g., "No approved value available in profile")
- [x] Store suggested_value optionally
  - Generated suggestions are prefilled in the review editor.
- [x] Set application status to "Needs Review"
- [x] Pause the application run

### Phase 4 Verification (2026-10-25)
- ✅ `tests/test_ai_mapper.py`: 17 offline unit/integration checks passed
- ✅ Live Gemini smoke test:
  - exact saved answer → `direct_fact` / fill
  - missing computer-type fact → review
  - generated project description → review suggestion
  - sensitive work-authorization field → blocked before the API call
- ✅ End-to-end local API run with `?ai=1`:
  - one Gemini call mapped a paraphrased saved-answer question
  - field was filled with `ai_field_filled`
  - zero review items, local submission confirmed
- ✅ Live Greenhouse fill-only run with AI enabled (Instead, Software Engineer):
  - one AI call for the required computer-type question
  - no supporting profile fact → review item, not a guess
  - no Submit click; dummy data only
- ✅ Existing Phase 3 suite: 33/33 checks passed with AI disabled
- ✅ Existing submission suite: 51/51 checks passed with AI disabled
- ✅ `AI_ENABLED=false` preserves the deterministic behavior exactly
- Details are recorded in `phase_4_ai_log.md`.

---

## Phase 5: Review and Submission

### Task 5.1: Review Item Management
- [x] Display review items to user on Apply page
- [x] Allow user to resolve review items (enter missing information)
- [x] Store user_resolution in review_items table
- [x] Mark review_items as resolved_at when user confirms

### Task 5.2: Application Resumption
- [x] After user resolves review items, resume same application
- [x] Clear "Needs Review" status when all fields resolved
- [ ] Continue form filling from where paused
  - Intentionally not implemented as exact-DOM resume. The agent deliberately
    reloads and refills the whole form using the profile plus stored resolutions.
    This avoids stale DOM state and is functionally equivalent for the supported
    Greenhouse flow; it is not an incremental resume at the exact paused field.
    This is the only Phase 5 checkbox left intentionally open.

### Task 5.3: Submission Logic
- [x] Check if all required fields are resolved
- [x] Verify site is supported for automatic submission
- [x] Apply automatic-submission policy configuration
  - Policy: submit only when there are zero review items, the host is a
    Greenhouse domain (or the local test server), and a confirmation is
    verified. Never submit while any review item is unresolved.
- [x] Submit form only when all required fields resolved

### Task 5.4: Submission Verification
- [x] Look for reliable confirmation signals:
  - Success page navigation (`/confirmation` path)
  - Success message text
  - Form disappearance with a visible success message
- [x] Do NOT rely on button click alone as proof
- [x] If confirmation unclear → record uncertain outcome for review

### Task 5.5: Result Persistence
- [x] Update SQLite with:
  - status (Submitted/Failed)
  - submitted_at timestamp
  - last_error (if failed)
  - confirmation_details (minimal text)
  - review items status
- [x] Refresh JSON export after database transaction succeeds (Phase 6)
  - Every application, event, review-item, and deletion mutation refreshes
    `backend/applications.json` atomically after the SQLite commit.

### Task 5.6: Ambiguous Outcome Handling
- [x] If submission success unclear → do not blindly retry
- [x] Record uncertain outcome for review to avoid duplicate applications
- [x] Display appropriate status (Needs Review or Failed) based on outcome

---

## Phase 6: JSON Export and Reliability

### Task 6.1: Application Export
- [x] Export application history to JSON after database updates
- [x] Use temporary file and atomic replacement for JSON writes
- [x] Ensure JSON export reflects latest database state
- [x] Example export format per the project plan
  - Export includes `exported_at`, `application_count`, applications, review
    items, events, submission outcome, and confirmation details.
  - Available on disk at `backend/applications.json`, via
    `GET /api/applications/export`, and as a download button on All Applications.

### Task 6.2: Error Testing
- [x] Test browser errors (navigation failures, element not found, etc.)
- [x] Test invalid URLs and handle gracefully
- [x] Test missing fields and review item creation
- [x] Test AI provider timeouts and fallback behavior
- [x] Test application restarts and state persistence

### Task 6.3: Logging and Monitoring
- [x] Add clear logs for all major workflow steps
- [x] Log AI provider calls and responses (with sensitive data scrubbing)
  - Metadata only: field label, action, answer kind, confidence, matched key,
    retry/error reason. Profile values, resume text, and API keys are not logged.
- [x] Log browser automation steps
- [x] Log status transitions and review item changes
  - Rotating file at `backend/logs/jobagent.log` with 2 MB limit and 5 backups.

### Task 6.4: Setup Guide
- [x] Create local setup guide documenting:
  - Prerequisites (Node, Python, Playwright browsers, API keys)
  - Environment variable configuration
  - How to run the application
  - How to use the three pages
  - Basic troubleshooting
  - Data backup, export, privacy, and test commands
  - See the root `README.md` and the PowerShell start scripts.

### Task 6.5: Final Verification
- [x] Run through complete end-to-end workflow with a test job form
- [x] Verify all 12 acceptance criteria are met
- [x] Test profile editing and persistence
- [x] Test URL submission and browser opening
- [x] Test profile-based field filling
- [x] Test AI usage only when needed
- [x] Test Needs Review creation for missing fields
- [x] Test application viewing and status filtering
- [x] Test verified submission marking
- [x] Test failure reason display
- [x] Test SQLite persistence across restarts
- [x] Test JSON export reflects database state
- [x] Verify no fabrication of personal information occurs

### Phase 6 Verification (2026-10-25)
- ✅ `tests/test_ai_mapper.py`: 17 offline AI/fallback checks passed
- ✅ `tests/test_phase3_api.py`: 33 deterministic filling/review checks passed
- ✅ `tests/test_submission_api.py`: 51 submission/review/outcome checks passed
- ✅ `tests/test_phase6_api.py`: 48 export/log/error-handling checks passed
- ✅ `tests/e2e_phase2.py`: 7 UI checks passed with zero console/page errors
- ✅ `npm run lint` and `npm run build` pass
- ✅ JSON export updates after create, review resolution, submission, failure, and
  delete; atomic temp files are cleaned up
- ✅ Backend restart preserved an application, 19 events, 2 review items, and its
  export snapshot
- ✅ Logs contain workflow events but no test email, phone, or API key material
- ✅ Invalid URLs return 400; an unreachable page ends Failed with a useful reason
- ✅ AI transport timeout and arbitrary provider errors return review/error
  results instead of raising or stopping the run

**External step remaining:** a real employer submission requires the user's real
profile/resume, a specific job they want, and explicit approval after a fill-only
review. No fake data has been submitted to a real employer.

---

## Phase 7: Smart Matching and Safety Hardening

Completed 2026-10-25. See [`phase_7_smart_matching_log.md`](phase_7_smart_matching_log.md).

- [x] Remove eligibility inference from country/location and make work
      authorization/sponsorship explicit-only.
- [x] Always require an explicit saved answer for citizenship, security
      clearance, legal attestations, demographic questions, and home/mailing
      address.
- [x] Replace substring-based derivation with whole-word, short-label matching so
      "state" in a legal paragraph and "city" in "ethnicity" cannot match.
- [x] Derive student status from explicit education dates instead of returning a
      hardcoded "Yes".
- [x] Remove invented notice-period, relocation, and internship answers.
- [x] Remove hardcoded AI `derived_facts` and revert the AI prompt to explicit
      facts only.
- [x] Block legal/attestation/address fields before AI and stop retrying HTTP 429
      quota errors.
- [x] Add a per-run AI quota circuit breaker.
- [x] Wait for network idle and hydration before filling.
- [x] Poll for delayed React-select options instead of using a fixed 400 ms wait.
- [x] Match school/degree/discipline options, including `Other` for an unlisted
      school and `Bachelor's Degree` for `B.Tech`.
- [x] Do not create review items for optional fields that cannot be matched.
- [x] Verify live fill-only education selections and explicit eligibility
      behavior.
- [x] Add `tests/test_smart_matching.py` and update the README and phase logs.

### Phase 7 Verification

- ✅ `tests/test_ai_mapper.py`: 21 tests passed
- ✅ `tests/test_smart_matching.py`: 44 tests passed
- ✅ `tests/test_phase3_api.py`: 33 checks passed
- ✅ `tests/test_submission_api.py`: 51 checks passed
- ✅ `tests/test_phase6_api.py`: 48 checks passed
- ✅ `tests/test_fill_only_api.py`: 11 checks passed
- ✅ `tests/test_resume_parser.py`: 10 tests passed
- ✅ `tests/e2e_phase2.py`: 7 UI checks passed
- ✅ `npm run lint` and `npm run build` pass
- ✅ Live GRVTY fill-only run selected School → Other, Degree → Bachelor's
  Degree, and Discipline → Computer Science
- ✅ Live GRVTY run filled only the explicit U.S. eligibility answers and left
  security clearance, citizenship, legal acknowledgements, salary, and address
  for review
- ✅ No Submit click in the live fill-only run

---

## Acceptance Criteria Checklist

- [x] 1. Application runs locally with frontend and backend
- [x] 2. User can edit and persist a profile
- [x] 3. User can submit a job URL and see the browser open (Phase 3)
- [x] 4. Agent fills supported fields using profile information (Phase 3)
- [x] 5. AI is used only when field interpretation or written answers require it (Phase 4)
  - AI runs only for required fields that the deterministic mapper cannot answer.
  - Sensitive/eligibility fields are never sent to AI.
- [x] 6. Missing or uncertain required fields create a Needs Review item (deterministic gaps in Phase 3; AI-assisted gaps and resolution in Phase 4/5)
- [x] 7. User can view all applications and filter by status
- [x] 8. Verified submissions are marked Submitted (Phase 5, submission-first)
- [x] 9. Failed runs display a useful reason (Phase 3)
- [x] 10. Application records persist in SQLite across restarts
- [x] 11. A JSON export reflects the latest database state (Phase 6)
  - Atomic `applications.json` refresh after every mutation, plus an API download
    and a download action on All Applications.
- [x] 12. Agent does not fabricate personal information or blindly retry uncertain submissions
  - AI direct-fact answers must be traceable to the profile/saved answers.
  - AI-generated prose becomes a review suggestion by default.
  - Sensitive/eligibility fields are never answered by AI.
  - Work authorization and sponsorship are explicit-only; country/location are
    never used to infer them.
  - Citizenship, security clearance, legal attestations, demographics, and
    home/mailing addresses require an explicit saved answer.
  - An uncertain submission blocks automatic resubmission until the user verifies it.

---

## Risks & Mitigation

| Risk | Mitigation |
|------|------------|
| Job portals vary in form structure | Start with one supported portal, add others incrementally |
| AI answers can be incorrect | Strict Python validation of all AI output; never use unvalidated model output |
| Hosted AI APIs have rate limits/costs | Configure reasonable limits; cache profile lookups; use deterministic logic when possible |
| Success pages may not always be available | Record uncertain outcomes for review rather than claiming submission |
| Local JSON exports not a substitute for backups | Document backup procedures; emphasize database + resume file backup |
| Some portals disallow automation | Pause on unexpected interactions; never bypass CAPTCHA/OTP/login protections |

---

## Technology Stack Reference

- **Frontend**: Next.js, TypeScript, Tailwind CSS
- **Backend**: Python, FastAPI
- **Browser Automation**: Playwright (visible mode)
- **AI Provider**: Gemini API (implemented with Gemini 3.5 Flash); Groq is not implemented in this version
- **Primary Database**: SQLite
- **Profile/Export Format**: JSON
- **Secrets Storage**: Environment variables / .env file (excluded from Git)