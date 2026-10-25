# Phase 6 Log — JSON Export and Reliability

Date: 2026-10-25

## Completed

### 6.1 Application JSON export

- Added `build_applications_export()`, `write_applications_export()`, and
  `refresh_applications_export()` in `backend/storage.py`.
- Export schema:
  - `exported_at`
  - `application_count`
  - `applications[]` with status, job metadata, timestamps, last error,
    confirmation details, submission attempt/outcome, review items, and events.
- Writes use `tempfile.mkstemp()` in the destination directory, `fsync`, and
  `os.replace()` for atomic replacement. A process-level lock serializes writes.
- Export refresh runs after commits for application create/delete, events,
  updates, review item creation/resolution, resume, retry, and manual submission
  confirmation.
- Added `GET /api/applications/export` with `application/json` and attachment
  headers.
- Added a **Download JSON export** action on All Applications.
- Added `APPLICATIONS_EXPORT_PATH` configuration and ignored the personal export
  file in `.gitignore`.

### 6.2 Error testing

- Invalid URLs (`not-a-url`, `ftp://...`, `http://` without a host) return 400.
- An unreachable local URL creates a record, ends `Failed`, and stores the
  navigation error.
- Missing required answers still create review items and pause before submission.
- AI transport timeouts and arbitrary provider/parsing errors now return an
  `error` mapping instead of raising. The application run continues and creates
  review items where needed.
- Verified backend restart persistence: application, 19 events, 2 review items,
  and the export snapshot survived a restart.

### 6.3 Logging and monitoring

- Added `backend/logging_config.py` with a rotating file handler at
  `backend/logs/jobagent.log` (2 MB, 5 backups) and a console handler.
- Configured through `LOG_LEVEL`, `LOG_DIR`, `LOG_MAX_BYTES`, and
  `LOG_BACKUP_COUNT`.
- Logged:
  - application create/delete/resume/retry/manual confirmation,
  - every stored event and status transition,
  - review item creation and resolution,
  - run start/finish and automation failures,
  - AI call metadata, retries, field limits, and errors,
  - export downloads.
- AI logs contain field labels, metadata, and short reasons. They do not contain
  contact details, resume text, suggested values, or API keys. The Gemini key is
  redacted from provider error messages. Logs are still local personal data.
- Health endpoint now reports `applications_export` and `log_file` paths.

### Fill-only safety mode (pre-real-run hardening)

- Added `AUTO_SUBMIT` (default `true`) to support a fill-only review run.
- With `AUTO_SUBMIT=false`, a complete form ends in **Needs Review** without
  clicking Submit, records `submission_skipped`, and stores a clear reason.
- After review, set `AUTO_SUBMIT=true`, restart the backend, and resume to submit.
- Health reports the current `auto_submit` setting.
- Added `tests/test_fill_only_api.py`: 11 checks passed, including proof that no
  submission attempt or Submit click occurred.

### 6.4 Setup guide

- Added root `README.md` covering prerequisites, installation, `.env`, AI setup,
  starting the app, the three pages, JSON export, logs, tests, privacy/backups,
  troubleshooting, and limitations.
- Added `start-backend.ps1`, `start-frontend.ps1`, and `start-app.ps1`.
- Updated `backend/.env.example` with export and logging settings.
- Updated `.gitignore` for `backend/applications.json`, temporary export files,
  and `backend/logs/`.

### 6.5 Final verification

| Check | Result |
|---|---|
| `tests/test_ai_mapper.py` | 17 passed |
| `tests/test_phase3_api.py` | 33 passed |
| `tests/test_submission_api.py` | 51 passed |
| `tests/test_phase6_api.py` | 48 passed |
| `tests/e2e_phase2.py` | 7 passed, no console/page errors |
| `npm run lint` | passed |
| `npm run build` | passed |
| Restart persistence + export | passed |
| Log secret/PII scan | no test email, phone, or `AIza` key material |
| Atomic export temp cleanup | passed |

### Post-Phase 6 smart-matching safety hardening (2026-10-25)

A later pass corrected unsafe inference and dropdown failures found during live
Greenhouse runs. Full details are in `phase_7_smart_matching_log.md`.

- Work authorization and sponsorship are explicit-only; country/location are
  never used to infer them.
- Citizenship, security clearance, legal attestations, demographics, and
  home/mailing addresses always require an explicit saved answer.
- Long legal paragraphs and `ethnicity` labels can no longer trigger State/City
  derivation through substring matches.
- React hydration and delayed React-select options are handled by waiting for
  network idle and polling for options.
- School/degree/discipline options use equivalent matching; optional unmatched
  fields no longer block submission.
- Hardcoded AI `derived_facts` were removed. Legal/attestation/address fields are
  blocked before AI, and HTTP 429/quota stops further AI calls for the run.
- Live GRVTY fill-only run selected School → Other, Degree → Bachelor's Degree,
  and Discipline → Computer Science, filled only the explicit U.S. eligibility
  answers, and left the six genuinely unsupported required fields in review.

Updated regression results:

| Check | Result |
|---|---|
| `tests/test_ai_mapper.py` | 21 passed |
| `tests/test_smart_matching.py` | 44 passed |
| `tests/test_phase3_api.py` | 33 passed |
| `tests/test_submission_api.py` | 51 passed |
| `tests/test_phase6_api.py` | 48 passed |
| `tests/test_fill_only_api.py` | 11 passed |
| `tests/test_resume_parser.py` | 10 passed |
| `tests/e2e_phase2.py` | 7 passed |
| `npm run lint` | passed |
| `npm run build` | passed |

API tests used a separate temporary data directory; the real profile, database,
uploads, export, and logs were not modified.

## Acceptance criteria

All 12 acceptance criteria are now met. Criterion 11 (JSON export) is covered by
the on-disk export, API endpoint, UI download, and tests. Criterion 12 is
reinforced by the Phase 7 explicit-only eligibility and AI quota hardening.

## Intentional limitations

- Exact-DOM incremental resume is not implemented. The agent reloads and
  refills with deterministic data plus stored review resolutions. This is
  documented as the only intentionally open Phase 5 checkbox.
- Greenhouse is still the only supported ATS.
- No real employer submission was made. That requires the user's real
  profile/resume, a chosen job, and explicit approval after a fill-only review.
  Test data was only submitted to the local fixture and never to a real employer.
