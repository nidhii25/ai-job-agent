# Deployment and Multi-User Upgrade Plan

Status: discussion / planning document  
Date: 2026-10-25  
Current product: local, single-user AI job application agent for Greenhouse

## 1. Purpose

The current project is complete as a local, single-user application. This
document describes what would need to change to deploy it for other people,
either as a self-hosted app, an invite-only hosted service, or a public SaaS.

**Important:** the current backend should not be exposed directly to the public
internet. It has no authentication, no tenant isolation, local filesystem
storage, and an in-process background runner. Those are acceptable local
assumptions, but not safe public-service assumptions.

## 2. Executive summary

There are three realistic deployment models:

1. **Desktop / self-hosted**
   - Each user runs the app on their own machine.
   - Closest to the current architecture.
   - Lowest security and operational burden.
   - Recommended for the first external release.

2. **Invite-only hosted service**
   - You run it for a small number of users.
   - Requires authentication, isolation, object storage, a durable queue, and
     remote browser handoff for login/CAPTCHA.
   - Recommended as the first hosted product.

3. **Public multi-user SaaS**
   - Requires billing, abuse prevention, compliance, support, and significant
     reliability work.
   - Not realistic until the hosted foundation is proven.

Recommended path:

> Harden the local app → ship a self-hosted/desktop edition → run an
> invite-only hosted beta with manual submission approval → only then consider
> a public SaaS.

## 3. Current architecture assumptions

The current implementation assumes:

- One user, one machine.
- SQLite for application history.
- `profile.json` for profile data.
- Local uploads, logs, export, and browser-profile directories.
- One Playwright run at a time via `RUN_LOCK`.
- A visible local browser for login and CAPTCHA handoff.
- FastAPI `BackgroundTasks` for launching runs.
- No authentication or user accounts.
- No tenant data isolation.
- A shared server-side Gemini API key.
- Local filesystem paths for all runtime data.
- Automatic submission when no review items remain and the host is supported.

Each of these is reasonable for a personal local tool and a blocker or risk for
a multi-user service.

## 4. Deployment model comparison

| Concern | Desktop / self-hosted | Invite-only hosted | Public SaaS |
|---|---|---|---|
| User data stays on user machine | Yes | No | No |
| Authentication required | Low / optional | Yes | Yes |
| Tenant isolation | Minimal | Required | Required |
| Durable job queue | Nice to have | Required | Required |
| Remote browser handoff | Not needed | Required | Required |
| Billing and quotas | No | Optional | Required |
| Compliance burden | Low | Medium | High |
| Abuse prevention | Low | Medium | High |
| Operational complexity | Low | Medium–high | High |
| Recommended first step | Yes | Next | Later |

### Recommended first release: desktop or self-hosted

Package the existing app so each user runs it locally:

- Docker Compose, or a desktop wrapper such as Electron/Tauri.
- User supplies their own Gemini key.
- All data remains local.
- Visible browser remains on the user's machine.
- Manual login/CAPTCHA remains simple.
- No central service storing resumes or application data.

This preserves most of the current design and avoids the hardest hosted
problems.

### Recommended first hosted release: invite-only beta

Only after the local edition is polished:

- Add accounts and tenant isolation.
- Move data to PostgreSQL and object storage.
- Run browser automation in dedicated workers.
- Stream a live browser view to the user for manual steps.
- Default to manual approval before submission.
- Limit users and jobs while reliability is measured.

## 5. Public-launch blockers

These are the highest-priority gaps. They should be resolved before any
multi-user deployment.

### 5.1 Authentication and tenant isolation

Current state: no user concept.

Required:

- Sign-up, login, logout, password reset.
- Optional MFA.
- Session/token management.
- `user_id` or `tenant_id` on every application, event, review item, profile,
  upload, and job.
- Authorization checks on every API endpoint.
- Per-user data scoping in every query.
- Admin/support roles with audit logging.
- Account deletion and data export.

Without this, one user could potentially access another user's applications,
resume, or profile.

### 5.2 Durable job execution

Current state: FastAPI `BackgroundTasks` and a process-local `RUN_LOCK`.

Problems:

- Jobs are lost on restart.
- No durable status for queued/running work.
- No safe retry policy.
- No cancellation.
- Only one run at a time per API process.
- No worker isolation or autoscaling.

Required:

- A queue such as Redis + Celery/RQ/Dramatiq/Arq, or a managed queue.
- Separate browser worker service.
- Job records with states: queued, running, waiting for review, waiting for
  manual verification, submitting, submitted, failed, cancelled.
- Idempotency keys and duplicate-submission protection.
- Timeouts, retries with safe semantics, and dead-letter handling.
- One active run per user, configurable global concurrency.
- Crash recovery that marks uncertain submissions as uncertain, never retryable
  automatically.

### 5.3 Remote browser and manual handoff

Current state: visible browser on the local machine.

Hosted users cannot see a browser running on the server. They need a way to:

- Complete login/OTP manually.
- Solve a CAPTCHA manually.
- Inspect the page when automation is unsure.
- Verify whether a submission actually happened.

Options:

- Self-hosted headless Chromium with noVNC/live-view streaming.
- Browser infrastructure such as Browserbase, Browserless, or Steel.
- A "pause and notify" flow that gives the user a time-limited live browser
  link.

Rules:

- Never bypass CAPTCHA or verification.
- Never ask users to send OTP codes to the service.
- Expire browser sessions and clean them up reliably.
- Record only the minimum needed for support and audit.
- Warn users that a live browser session may expose employer page content.

### 5.4 Data security and privacy

Hosted storage will contain resumes, contact details, saved answers, and job
history. Required controls:

- HTTPS everywhere.
- Encryption in transit and at rest.
- Secrets in a managed secret store, not `.env` on a shared server.
- Encrypted resume/object storage with short-lived signed URLs.
- File type, size, and malware checks.
- Strict URL validation and SSRF protection.
- Rate limiting and abuse detection.
- Redacted logs and short retention.
- Backups with tested restore procedures.
- Data export and deletion workflows.
- A privacy policy and clear retention terms.
- Regional privacy compliance where applicable (for example GDPR/CCPA).

The current local URL validation is not sufficient for a public service.

### 5.5 Database and file storage

Current state: SQLite plus local files.

For hosted use:

- PostgreSQL for multi-user data.
- Schema migrations (for example Alembic).
- Object storage (S3-compatible) for resumes.
- Tenant-scoped queries and backups.
- No reliance on local disk for anything that must survive a restart.
- Point-in-time recovery for the database.
- Retention jobs for logs and old artifacts.

SQLite can remain acceptable for a very small invite-only beta, but the
architecture should not depend on local files.

### 5.6 AI cost, abuse, and data governance

A shared Gemini key can be exhausted or abused. Required:

- Per-user quotas and rate limits.
- Usage metering and cost dashboards.
- Optional bring-your-own-key mode.
- Provider abstraction and fallback models.
- Prompt-injection defenses for job-page text.
- Strict structured-output validation.
- Explicit disclosure of what data is sent to the AI provider.
- Data-processing terms and retention review for the AI vendor.
- Sensitive/eligibility fields remain blocked from AI.
- Generated prose remains review-only by default.

Treat all employer page content as untrusted input. It must never become an
instruction to the model or the automation layer.

### 5.7 Legal and platform policy

Before automating applications for others, review:

- Greenhouse and employer terms of service.
- Whether automated form filling or submission is permitted.
- Whether users must explicitly approve submission.
- Whether the product must disclose that automation is being used.
- Anti-abuse and fair-use expectations.
- Privacy law obligations for storing resumes and personal data.

This is not legal advice, but it is a product blocker. Prefer official APIs or
partner integrations where they exist rather than browser automation.

### 5.8 Observability and support

Hosted operations need:

- Structured logs with request and job IDs.
- Metrics: queue time, run duration, success rate, review rate, confirmation
  rate, failure reasons, AI calls, and cost.
- Error tracking (for example Sentry).
- Alerts for stuck queues, high failure rates, and uncertain submissions.
- An admin view for stuck applications and safe manual resolution.
- Audit logs for support access.

Submission uncertainty needs a human escalation path, not just a database row.

### 5.9 Concurrency and browser resources

Playwright browsers are resource-heavy. Hosted workers need:

- CPU/memory limits per browser session.
- Container sandboxing.
- Browser timeout and cleanup guarantees.
- Queue capacity and backpressure.
- Concurrency limits per user and globally.
- Stuck-job detection.
- Stable egress IPs if required by employer sites, without using evasion
  techniques.

The current global lock is intentionally safe for one user; it is not a scaling
strategy.

## 6. Target hosted architecture

```text
Browser
  |
  v
Next.js frontend
  |
  v
FastAPI API  ---->  Auth provider (OIDC / sessions / MFA)
  |                 |
  |                 +--> PostgreSQL (users, applications, events, reviews)
  |                 +--> Object storage (resumes, artifacts)
  |                 +--> Redis (queue, rate limits, sessions)
  |
  v
Job queue
  |
  v
Browser workers (Playwright/Chromium)
  |
  +--> ATS adapters (Greenhouse first)
  +--> AI adapter (Gemini first)
  +--> Live-view handoff for login/CAPTCHA
  |
  v
Status updates / events / notifications
```

Recommended components:

- Frontend: Next.js
- API: FastAPI
- Database: PostgreSQL
- Queue/cache: Redis
- Workers: Python + Playwright in isolated containers
- Files: S3-compatible object storage
- Auth: Clerk, Auth0, Supabase, Cognito, or a standards-based OIDC provider
- Secrets: AWS Secrets Manager, Azure Key Vault, Doppler, or equivalent
- Browser live view: noVNC/self-hosted or a managed browser provider
- Observability: OpenTelemetry, Sentry, managed logs/metrics
- Deployment: Docker, TLS reverse proxy, CI/CD, staging environment

The API should never run Playwright directly in a hosted deployment. It should
enqueue jobs and expose status.

## 7. Required data-model changes

Add or change:

- `users`
- `sessions` or external auth identifiers
- `organizations` / `tenants` if teams are in scope
- `user_id` on `applications`
- `user_id` on `profile` storage
- `user_id` on review items and events (directly or through the application)
- `jobs` table for queue state, attempts, timestamps, worker ID, and errors
- `uploads` table for object-store keys and scan status
- `audit_events` for support/admin actions
- `usage_counters` for AI quotas and billing
- `idempotency_keys` for safe retries
- `deleted_at` / retention metadata where required

Keep SQLite as the source of truth for local mode, but introduce a storage
abstraction so local and hosted backends can coexist.

## 8. API and service changes

- Add authentication and authorization dependencies to every route.
- Scope every query by the authenticated user.
- Replace application-run side effects with enqueue operations.
- Add job status and cancellation endpoints.
- Add live-browser session creation and expiry endpoints.
- Add upload signed-URL endpoints instead of base64 payloads for large files.
- Add quotas and rate-limit responses.
- Add audit logging for sensitive actions.
- Add health/readiness endpoints for API and workers.
- Add versioning for breaking API changes.
- Keep the JSON export per user, not a single global file.

Suggested additional endpoints:

- `POST /api/jobs/{application_id}/cancel`
- `GET /api/jobs/{application_id}/live-session`
- `POST /api/uploads/presign`
- `GET /api/usage`
- `GET /api/admin/stuck-jobs`
- `POST /api/admin/applications/{id}/resolve`
- `DELETE /api/account`
- `GET /api/account/export`

## 9. Product changes for other users

The current three pages are a good base, but a hosted product needs:

- Onboarding and profile completeness checks.
- Resume parsing with user review.
- Review-before-submit as the default.
- A fill-only/dry-run mode.
- Clear "filled vs. needs review" reporting.
- Notifications when manual action is needed.
- Duplicate-job and already-applied detection.
- Per-user application limits or plans.
- Export and delete-my-data controls.
- Support contact and issue reporting.
- Better handling of stale or changed ATS forms.
- Optional multiple resumes or job-specific variants.

## 10. ATS expansion

Greenhouse-only remains the right first scope. To add more platforms:

- Create a formal ATS adapter interface.
- Keep deterministic mappings per ATS separate from AI fallback.
- Add fixture pages and live smoke tests per platform.
- Version selectors and detect form changes.
- Use feature flags and canary rollout.
- Add a clear "unsupported form" path instead of guessing.
- Prefer official APIs or partner integrations where available.

Do not let one broken platform break the whole worker pool.

## 11. Phased roadmap

### Phase A: Harden the local edition

Goal: make it easy and safe for individual users to run locally.

- Docker Compose or desktop packaging.
- Configurable storage paths.
- User-supplied Gemini key.
- Review-before-submit toggle and/or fill-only mode.
- Backup/restore instructions.
- One-command startup and health checks.
- Clear privacy guidance.
- Keep `ALLOW_LOCAL_URLS=false` by default.

Exit criteria:

- A new user can install and run it without developer help.
- No central service stores their data.
- No public network exposure.

### Phase B: Invite-only hosted beta

Goal: prove the hosted workflow with a small number of users.

- Accounts, sessions, and tenant-scoped data.
- PostgreSQL and object storage.
- Redis-backed queue and separate workers.
- Live browser handoff for login/CAPTCHA.
- Manual approval before real submission.
- Per-user quotas and admin tooling.
- Privacy policy, retention, and deletion.
- Error tracking and metrics.

Exit criteria:

- Two users cannot access each other's data.
- Worker crashes do not lose jobs or cause duplicate submissions.
- Stuck jobs are visible and recoverable.
- A real user can complete a real application with explicit approval.

### Phase C: Public SaaS

Goal: operate reliably for many users.

- Billing and plans.
- Abuse prevention and fraud controls.
- Stronger compliance and security program.
- Autoscaling browser workers.
- Multi-region backups or disaster recovery as needed.
- More ATS adapters.
- Support workflows and SLA targets.
- Cost and reliability dashboards.

Exit criteria:

- Documented incident response.
- Tested backups and restores.
- Predictable per-run cost.
- Clear escalation path for uncertain submissions.
- Security and privacy review completed.

## 12. Launch-readiness checklist

### Security

- [ ] Authentication enforced on every non-public route.
- [ ] Tenant isolation tested with two accounts.
- [ ] Secrets in a managed secret store.
- [ ] HTTPS and secure cookies/tokens.
- [ ] Resume uploads scanned and stored privately.
- [ ] SSRF protections and URL allowlisting reviewed.
- [ ] Rate limits and quotas active.
- [ ] Logs redact contact data, resume contents, and API keys.
- [ ] Account deletion and data export work.

### Reliability

- [ ] Durable queue and worker recovery tested.
- [ ] Duplicate-submission protection tested under retries.
- [ ] Stuck-job detection and alerting active.
- [ ] Browser cleanup verified after crashes.
- [ ] Backups and restore tested.
- [ ] Status updates survive API restarts.

### Product

- [ ] Review-before-submit is the default.
- [ ] Fill-only mode is available.
- [ ] Manual login/CAPTCHA handoff works remotely.
- [ ] Uncertain outcomes require human verification.
- [ ] Users can clearly see what was filled and what was not.
- [ ] Notifications work when action is required.

### Legal and operations

- [ ] ATS/employer automation policy reviewed.
- [ ] Privacy policy and terms published.
- [ ] Data retention and deletion policy documented.
- [ ] AI data-processing terms reviewed.
- [ ] Support and escalation process defined.
- [ ] Incident response plan documented.

## 13. Cost drivers

Hosted costs will be driven by:

- Browser worker CPU and memory.
- Browser session duration, especially manual waits.
- Database and object storage.
- Gemini calls and retry volume.
- Live-view bandwidth.
- Logs, metrics, and error tracking.
- Support time for stuck or uncertain applications.

Browser time is likely the largest and least predictable cost. Set strict
timeouts and show queue/wait states to users.

## 14. Key risks and mitigations

| Risk | Mitigation |
|---|---|
| One user sees another user's data | Tenant-scoped queries, tests, and authorization reviews |
| Duplicate submissions | Idempotency, uncertain-outcome blocking, manual verification |
| Worker crash loses a run | Durable queue, job state, recovery, dead-letter handling |
| Resume/PII leak | Encryption, private object storage, signed URLs, redaction |
| Shared AI key abuse | Quotas, metering, BYO key, rate limits |
| CAPTCHA/login blocks hosted runs | Live browser handoff; never bypass |
| ATS form changes break automation | Adapter isolation, fixtures, monitoring, feature flags |
| Unexpected AI cost | Per-run field caps, caching, usage dashboards |
| Legal/ToS problem | Review before launch; prefer official APIs/partners |
| Support burden from uncertain submissions | Admin tooling, notifications, clear user guidance |

## 15. Open product decisions

These should be decided before building Phase B:

1. Desktop/self-hosted first, or hosted beta first?
2. Do users bring their own Gemini key, or does the platform pay and meter usage?
3. Is submission always manual-approved, or can users opt into auto-submit?
4. Is live browser handoff acceptable, or should the product only support
   accounts without login/CAPTCHA?
5. Which regions and privacy regimes are in scope?
6. Is this a personal tool, a paid product, or an open-source project?
7. Are teams/organizations needed, or only individual accounts?
8. Which ATS platforms come after Greenhouse?
9. What is the retention period for resumes, logs, and application history?
10. What happens when a submission outcome is uncertain and the user does not
    respond?

## 16. Recommended next steps

1. Decide between **desktop/self-hosted** and **invite-only hosted**.
2. If self-hosted: Dockerize and add review-before-submit/fill-only mode.
3. If hosted: build auth, tenant isolation, PostgreSQL, object storage, and the
   queue before adding any new ATS.
4. Add a live-browser handoff prototype for login/CAPTCHA.
5. Run a security and legal review before accepting real user resumes.
6. Keep real submissions manual-approved until confirmation reliability is
   measured across multiple employers.
