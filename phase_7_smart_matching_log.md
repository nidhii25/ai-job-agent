# Phase 7 Log — Smart Matching and Safety Hardening

Date: 2026-10-25
Status: Complete

## Context

The uncommitted "smart matching" work added useful education/major matching,
but it also introduced unsafe behavior:

- work authorization, sponsorship, and citizenship were inferred from the
  candidate's country/location;
- "Security Clearance Type" was treated as a sponsorship question because its
  help text contains the word "sponsor";
- a long legal acknowledgement containing "federal, state or local law" was
  treated as a State field;
- "Are you Hispanic/Latino?" could derive the city because `city` is a substring
  of `ethnicity`;
- the AI prompt was given a hardcoded `derived_facts` object with guessed
  eligibility values;
- React hydration could clear values filled immediately after
  `DOMContentLoaded`;
- delayed React-select options were missed by fixed 400 ms waits;
- optional fields that could not be matched could create review items and block
  submission.

This phase removes the unsafe inference and keeps only the safe matching work.

## Safety fixes

### Explicit-only eligibility

- `_work_authorization_answer()` now answers only work-authorization and
  sponsorship questions, and only from `profile.work_authorization` or an
  explicit saved answer.
- It never infers eligibility from country, city, education, or other profile
  facts.
- Citizenship, permanent-residency, security-clearance, export-control,
  background-check, criminal, drug-test, demographic, disability, veteran,
  legal-attestation, signature, and home/mailing-address questions always
  require an explicit saved answer.
- Explicit country clauses are handled conservatively. For the current profile
  statement:
  - U.S. work authorization → **No**
  - U.S. sponsorship → **Yes**
  - India work authorization → **Yes**
  - India sponsorship → **No**
  - U.S. citizenship / security clearance / legal acknowledgement → no answer
    (review).

### Conservative derived answers

`_find_derived_answer()` now:

- looks only at the short visible label (or a short question), not long legal
  paragraphs;
- uses whole-word matching, so `city` never matches `ethnicity`;
- requires a short label for State/Province and City/Town derivation;
- derives graduation year/month and current-student status from explicit
  education dates (not a hardcoded "Yes");
- derives highest education level from the explicit degree;
- no longer invents notice period, relocation willingness, or internship
  preference because those facts are not in the profile.

### AI hardening

- Removed the hardcoded `derived_facts` object from `ai_mapper.py`.
- The prompt now says to use only explicitly present profile facts. Education
  option equivalence is handled deterministically by the filler.
- Added legal/attestation and address categories to the sensitive-field block
  list, including affirmation, acknowledgement, at-will, arbitration, consent,
  signature, certify, attest, home address, mailing address, street address, and
  export control.
- AI direct-fact validation no longer accepts generic "yes"/"no" answers for
  education or work authorization unless they are literally present.
- Gemini 429/quota responses are no longer retried. The first quota error sets a
  per-run circuit breaker, and later fields skip AI instead of spending more
  quota. Other 5xx/connection failures still retry.

## Automation fixes

### Hydration-safe filling

`backend/automation/runner.py` now waits for `networkidle` (up to 15 seconds)
after navigation and then a short settle delay before filling. This prevents
client-side re-renders from wiping values that were typed too early.

### Delayed React-select options

- `_wait_for_options()` polls for visible `role="option"` elements for up to
  2 seconds instead of assuming a fixed 400 ms delay.
- Option matching still prefers exact text, then prefix, then whole-word
  containment.
- Education fallbacks are limited to education controls:
  - degree → equivalent degree level or `Other`;
  - school → stripped school name, then `Other / Not Listed`;
  - discipline/field of study → direct or equivalent option text.
- The generic "Other" fallback for arbitrary required fields was removed.

### Optional fields do not block

- If an optional select, combobox, or text field cannot be matched, it is
  skipped without creating a review item.
- Required fields still create review items when no safe answer exists.
- Radio groups now create review items only when the group is required.

## Live verification

Target: `https://job-boards.greenhouse.io/grvty/jobs/4463989009`

Mode: fill-only, no Submit click.

Results after the fix:

- Education selected correctly in the live React-select controls:
  - School → **Other**
  - Degree → **Bachelor's Degree**
  - Discipline → **Computer Science**
- Explicit eligibility fields filled correctly:
  - Employment Eligibility Information → **No**
  - Visa Requirement Status → **Yes**
- No value was filled for:
  - Security Clearance Type
  - Affirmation
  - Authorization and Acknowledgement
  - Desired Salary
  - Home Address
  - U.S. citizenship question
- Those six fields remained required review items because the profile does not
  contain explicit answers. This is the intended safe behavior.
- The optional Hispanic/Latino field was left empty and did **not** create a
  review item.
- No AI errors occurred because the run used deterministic matching and the
  remaining fields were recognized as sensitive/unsupported.

## Tests

Offline:

```powershell
backend\venv\Scripts\python.exe -m unittest tests.test_ai_mapper tests.test_smart_matching
```

Result: **65 tests passed** (21 AI mapper + 44 smart matching).

The new suite covers:

- degree, school, and discipline option matching;
- explicit-only U.S./India work authorization and sponsorship;
- citizenship, security clearance, and legal acknowledgement never inferred;
- graduation date, student status, state, and city derivation;
- legal paragraphs and ethnicity labels not matching State/City;
- optional unmatched fields not creating review items;
- delayed React-select options;
- removal of hardcoded AI derived facts;
- legal attestations blocked before the AI call;
- quota circuit breaker stopping further AI calls.

API and UI regression:

| Suite | Result |
|---|---|
| `tests/test_phase3_api.py` | 33 checks passed |
| `tests/test_submission_api.py` | 51 checks passed |
| `tests/test_phase6_api.py` | 48 checks passed |
| `tests/test_fill_only_api.py` | 11 checks passed |
| `tests/test_resume_parser.py` | 10 tests passed |
| `tests/e2e_phase2.py` | 7 checks passed |
| `npm run lint` | passed |
| `npm run build` | passed |

API tests used a separate temporary database/profile/upload/log directory so the
user's real `backend/profile.json` and database were not modified.

The UI end-to-end script was updated from the older page labels to the current
redesigned Apply, Application Ledger, and Candidate Profile pages. It verifies
profile save/reload, saved answers, resume upload, live fill and review, review
resolution, submission, filtering, and a clean browser console.

## Required user action

The six live review items cannot be answered safely without user input. Add
explicit saved answers in **My Profile → Approved Saved Answers** for:

- security clearance level (or "No Clearance");
- legal affirmation / typed signature;
- authorization and acknowledgement;
- desired salary;
- home/mailing address;
- U.S. citizenship (if applicable to the role).

The agent will then reuse those answers deterministically on the next run.
