# Phase 4: Gemini AI-Assisted Mapping Log

**Date:** 2026-10-25
**Status:** Complete for required unfamiliar fields

## Provider and configuration

- Provider: **Gemini** (`AI_PROVIDER=gemini`)
- Model: **Gemini 3.5 Flash** (`gemini-3.5-flash`)
- The live model list was checked before selecting the model.
- The API key is stored only in `backend/.env`, which is gitignored.
- `backend/main.py` now loads `.env` with `python-dotenv` before importing
  modules that read environment variables.
- `python-dotenv==1.1.1` was added to `backend/requirements.txt`.

Relevant settings:

```env
GEMINI_API_KEY=...
AI_PROVIDER=gemini
GEMINI_MODEL=gemini-3.5-flash
AI_ENABLED=true
AI_CONFIDENCE_THRESHOLD=0.75
AI_TIMEOUT_SECONDS=25
AI_MAX_RETRIES=2
AI_MAX_FIELDS_PER_RUN=8
AI_AUTO_FILL_GENERATED=false
```

## What was built

### Adapter (`backend/automation/ai_mapper.py`)

- Calls the Gemini `generateContent` endpoint with structured JSON output.
- Uses a compact profile summary, not the full profile file.
- Sends **no** name, email, phone, resume bytes, cover-letter text, or sensitive
  saved answers.
- Caches repeated field mappings.
- Limits calls per run.
- Retries temporary Gemini 500/502/503/504 and connection failures with a short
  backoff. HTTP 429/quota errors are **not** retried.
- Stops making further AI calls for the rest of the run after a quota error.
- Returns a safe error mapping instead of raising into the automation run.

### Response validation

The model output is treated as a suggestion, not as truth. Python validates:

- `answer_kind` is `direct_fact`, `generated`, or `none`.
- Confidence meets the configured threshold.
- Direct-fact answers are traceable to the profile/saved answers.
- Option answers match an available option.
- Placeholder answers such as "N/A" or "Unknown" are rejected.
- Sensitive/eligibility questions are never sent to AI.

Sensitive categories include salary/compensation, work authorization,
sponsorship, visa/citizenship, demographics, disability, veteran status,
criminal/background checks, government IDs, security clearance, age/date of
birth, drug tests, legal attestations/acknowledgements/arbitration/consent,
signatures, export controls, and home/mailing/street addresses.

### Auto-fill policy

- **Direct fact** with sufficient confidence and valid grounding: auto-fill.
- **Generated prose** (for example a project description): review item with the
  text prefilled as `suggested_value`. It is not auto-filled by default.
- **None / low confidence / provider error:** deterministic review item.
- Set `AI_AUTO_FILL_GENERATED=true` only if you explicitly accept auto-submitting
  AI-written prose without reviewing it first.

### Filler integration (`backend/automation/greenhouse.py`)

- AI is only tried when a **required** field has no deterministic answer.
- Standard personal fields, saved answers, native selects, comboboxes, radio
  groups, resume upload, and resolved answers still run deterministically.
- AI-assisted choices are attempted for required radio groups.
- Checkbox groups are not AI-filled, to avoid partial multi-select answers.
- AI-filled fields are recorded separately from deterministic fields.
- AI review suggestions appear in the existing review editor with the suggested
  answer prefilled.
- File fields are never sent to AI.

### Runner integration (`backend/automation/runner.py`)

New events:

- `ai_mapping_enabled`
- `ai_field_filled`
- `ai_mapping_error`
- `ai_mapping_summary`

`/api/health` now reports `ai_enabled`, `ai_provider`, and `ai_model` without
exposing the key.

## Verification

### Offline tests

`backend/venv/Scripts/python.exe -m unittest tests.test_ai_mapper -v`

Result: **21/21 passed** (current suite)

Coverage includes:

- direct saved-answer mapping
- generated prose requiring review
- generated prose auto-fill only when explicitly enabled
- low-confidence fallback
- hallucinated facts rejected
- option mismatch rejected
- sensitive field blocked before the API call
- legal attestation blocked before the API call
- quota circuit breaker stops further AI calls
- no hardcoded derived eligibility facts in the prompt
- contact details and sensitive saved answers excluded from the prompt
- structured JSON schema in the request
- provider error fallback
- per-run caching and field limits
- Playwright filler integration with AI fill and AI review suggestions
- deterministic answers skip AI

### Live Gemini smoke test

Dummy profile only. Results:

- "How did you hear about this job?" → exact saved answer `LinkedIn`, filled.
- "Which computer type do you use; Mac, Linux or PC?" → no profile fact, review.
- "Describe a project you built with Python." → generated suggestion, review by
  default.
- "Are you legally authorized to work in the United States?" → blocked before
  the API call.

### Live Greenhouse fill-only test with AI enabled

Target: `https://job-boards.greenhouse.io/instead/jobs/7761474003`
(Instead — Software Engineer)

Dummy profile only. The script used `fill_application` directly, so it never
had a Submit path.

- Form detected; no login wall or CAPTCHA challenge.
- Deterministic fields filled: first/last name, email, country, phone, resume,
  LinkedIn.
- AI used exactly one call for the required computer-type question.
- No profile fact supported an answer, so AI created a review item instead of
  guessing: "Which computer type do you use; Mac, Linux or PC?"
- Zero AI errors.
- Submit was **not** clicked.
- Screenshot: `test_artifacts/instead_ai_fill_only.png`
- Report: `test_artifacts/instead_ai_fill_only_report.json`

That page uses ARIA required markers without native `required` attributes, so
`form.checkValidity()` can return true even while a review item is required.
The review-item list, not HTML5 validity alone, is the submission gate.

### End-to-end local API test

The local fixture now supports `?ai=1`, which adds a required paraphrased
question: "Where did you first hear about this role?"

With AI enabled:

- AI mapped it to the existing saved answer "How did you hear about this job?"
- Event `ai_field_filled` recorded confidence `1.00`.
- Event `ai_mapping_summary` recorded 1 call, 1 fill, 0 errors.
- No review items remained.
- The local fixture submitted and confirmed successfully.

### Regression suites

- `tests/test_phase3_api.py`: **33/33 passed** with AI disabled.
- `tests/test_submission_api.py`: **51/51 passed** with AI disabled.
- `AI_ENABLED=false` preserves the previous deterministic behavior.

## Post-Phase 6 safety hardening (2026-10-25)

A later pass removed unsafe AI/filler behavior. Full details are in
`phase_7_smart_matching_log.md`.

- Removed the hardcoded `derived_facts` object that guessed degree level,
  current-student status, graduation year, country, city/state, and eligibility
  answers.
- The prompt now maps only explicitly present profile facts. Education
  equivalents such as `B.Tech` → `Bachelor's Degree` are handled by the
  deterministic filler instead of model-derived facts.
- `_fact_supported()` no longer accepts generic `yes`/`no` for education or work
  authorization unless the literal value is present.
- Added legal/attestation/address categories to the sensitive-field block list.
- HTTP 429/quota is no longer retried; the first quota error sets a per-run
  circuit breaker and later fields skip AI.
- Live fill-only verification on GRVTY filled only the explicit eligibility
  answers and left security clearance, citizenship, legal acknowledgements,
  salary, and home address for review.

## Limitations and next steps

- Only Gemini is implemented; Groq remains a future option.
- AI is used only for required fields, not optional custom questions.
- Generated prose is reviewed rather than auto-filled by default.
- AI does not bypass login, CAPTCHA, or OTP prompts.
- Live submission with real personal data is still pending the user's real
  profile/resume and a job they actually want to apply to.
- If the API key was shared in a chat or screen recording, rotate it before using
  this project for real applications.
