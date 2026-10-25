"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  confirmationSummary,
  confirmSubmission,
  createApplication,
  formatDateTime,
  getApplication,
  getHealth,
  getProfile,
  markNotSubmitted,
  resumeApplication,
  retryApplication,
  uploadCoverLetter,
  uploadResume,
} from "@/lib/api";
import type { ApplicationDetail, Profile } from "@/lib/api";
import FilePicker from "@/components/FilePicker";
import ReviewItems from "@/components/ReviewItems";

function errorMessage(error: unknown): string {
  return error instanceof ApiError || error instanceof Error
    ? error.message
    : String(error);
}

function fileName(path: string): string {
  if (!path) return "";
  const parts = path.split(/[\\/]/);
  return parts[parts.length - 1];
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result ?? "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(new Error("Could not read the selected file"));
    reader.readAsDataURL(file);
  });
}

function renderStatusBadge(status: string) {
  switch (status) {
    case "Submitted":
      return (
        <span className="status-pill-submitted">
          <span className="h-1.5 w-1.5 rounded-full bg-[#05b169]" />
          Submitted
        </span>
      );
    case "Needs Review":
      return (
        <span className="status-pill-review">
          <span className="h-1.5 w-1.5 rounded-full bg-[#f4b000]" />
          Needs Review
        </span>
      );
    case "In Progress":
      return (
        <span className="status-pill-progress">
          <span className="h-1.5 w-1.5 rounded-full bg-[#0052ff] animate-pulse" />
          In Progress
        </span>
      );
    case "Failed":
      return (
        <span className="status-pill-failed">
          <span className="h-1.5 w-1.5 rounded-full bg-[#cf202f]" />
          Failed
        </span>
      );
    default:
      return (
        <span className="badge-pill">
          {status}
        </span>
      );
  }
}

export default function ApplyPage() {
  const [jobUrl, setJobUrl] = useState("");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [applicationId, setApplicationId] = useState<number | null>(null);
  const [application, setApplication] = useState<ApplicationDetail | null>(null);
  const [starting, setStarting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadingCoverLetter, setUploadingCoverLetter] = useState(false);
  const [autoSubmit, setAutoSubmit] = useState(true);
  const [actionPending, setActionPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadApplication = useCallback(async (id: number) => {
    try {
      const detail = await getApplication(id);
      setApplication(detail);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    Promise.all([getProfile(), getHealth()])
      .then(([nextProfile, health]) => {
        setProfile(nextProfile);
        setAutoSubmit(health.auto_submit);
      })
      .catch((err) => setError(errorMessage(err)));
  }, []);

  useEffect(() => {
    if (applicationId === null) return;

    let active = true;
    const load = () => {
      getApplication(applicationId)
        .then((detail) => {
          if (active) setApplication(detail);
        })
        .catch((err) => {
          if (active) setError(errorMessage(err));
        });
    };

    load();
    const timer = window.setInterval(load, 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [applicationId]);

  const handleStartApplication = async () => {
    const trimmed = jobUrl.trim();
    setError(null);
    setMessage(null);
    setApplication(null);
    setApplicationId(null);

    if (!trimmed) {
      setError("Please enter a job application URL.");
      return;
    }
    if (!trimmed.startsWith("http://") && !trimmed.startsWith("https://")) {
      setError("URL must start with http:// or https://");
      return;
    }

    setStarting(true);
    try {
      const created = await createApplication(trimmed, autoSubmit);
      setApplicationId(created.application_id);
      setMessage(
        `Application #${created.application_id} initialized. ${
          created.auto_submit
            ? "Automatic submission active: will submit after complete fill with zero unresolved review items."
            : "Fill-only mode active: form will be prepared for your inspection before submitting."
        }`
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setStarting(false);
    }
  };

  const handleResumeUpload = async (file: File) => {
    setError(null);
    setMessage(null);

    if (file.size > 10 * 1024 * 1024) {
      setError("Resume must be 10 MB or smaller.");
      return;
    }

    setUploading(true);
    try {
      const content = await readFileAsBase64(file);
      const path = await uploadResume(file.name, content);
      setProfile((current) =>
        current ? { ...current, resume_path: path } : current
      );
      setMessage(`Resume attached: ${fileName(path)}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setUploading(false);
    }
  };

  const handleCoverLetterUpload = async (file: File) => {
    setError(null);
    setMessage(null);

    if (file.size > 10 * 1024 * 1024) {
      setError("Cover letter must be 10 MB or smaller.");
      return;
    }

    setUploadingCoverLetter(true);
    try {
      const content = await readFileAsBase64(file);
      const result = await uploadCoverLetter(file.name, content);
      setProfile((current) =>
        current
          ? {
              ...current,
              cover_letter: result.cover_letter,
              cover_letter_path: result.cover_letter_path,
            }
          : current
      );
      setMessage(`Cover letter attached: ${fileName(result.cover_letter_path)}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setUploadingCoverLetter(false);
    }
  };

  const handleResumeApplication = async () => {
    if (applicationId === null) return;
    setActionPending(true);
    setError(null);
    try {
      await resumeApplication(applicationId, true);
      await loadApplication(applicationId);
      setMessage("Application resumed with automatic submission enabled.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setActionPending(false);
    }
  };

  const handleRetryApplication = async () => {
    if (applicationId === null) return;
    setActionPending(true);
    setError(null);
    try {
      await retryApplication(applicationId);
      await loadApplication(applicationId);
      setMessage("Retry initiated in local browser.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setActionPending(false);
    }
  };

  const handleReviewChanged = async () => {
    if (applicationId !== null) await loadApplication(applicationId);
  };

  const handleConfirmSubmission = async () => {
    if (applicationId === null) return;
    if (
      !window.confirm(
        "Only confirm this after checking the employer site. This marks the application as submitted."
      )
    ) {
      return;
    }
    setActionPending(true);
    setError(null);
    try {
      await confirmSubmission(
        applicationId,
        "User manually verified the submission on the employer site."
      );
      await loadApplication(applicationId);
      setMessage("Submission confirmed and recorded in durable ledger.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setActionPending(false);
    }
  };

  const handleMarkNotSubmitted = async () => {
    if (applicationId === null) return;
    if (
      !window.confirm(
        "Only mark this if you verified the application was NOT submitted. This allows another automatic attempt."
      )
    ) {
      return;
    }
    setActionPending(true);
    setError(null);
    try {
      await markNotSubmitted(
        applicationId,
        "User verified the application was not submitted."
      );
      await loadApplication(applicationId);
      setMessage("Marked as not submitted. You can resume when ready.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setActionPending(false);
    }
  };

  const fieldsFilled =
    application?.events.filter(
      (event) =>
        event.event_type === "field_filled" ||
        event.event_type === "resume_uploaded" ||
        event.event_type === "cover_letter_uploaded"
    ).length ?? 0;
  const openReviewItems =
    application?.review_items.filter((item) => !item.resolved_at) ?? [];
  const submissionOutcome = application?.submission_outcome ?? null;
  const needsManualVerification =
    application?.status === "Needs Review" &&
    (submissionOutcome === "pending" || submissionOutcome === "uncertain");
  const submissionWasAttempted = ["pending", "uncertain", "confirmed"].includes(
    submissionOutcome ?? ""
  );
  const canResume =
    application?.status === "Needs Review" &&
    openReviewItems.length === 0 &&
    !submissionWasAttempted;
  const confirmation = confirmationSummary(
    application?.confirmation_details ?? null
  );
  const latestEvent =
    application?.events[application.events.length - 1] ?? null;
  const hasName = Boolean(
    profile?.personal.full_name.trim() ||
      (profile?.personal.first_name.trim() &&
        profile?.personal.last_name.trim())
  );

  return (
    <div className="w-full flex-1 flex flex-col">
      {/* Dark Editorial Hero Band matching DESIGN.md */}
      <section className="hero-band-dark">
        <div className="content-container">
          <div className="grid grid-cols-1 items-center gap-12 lg:grid-cols-12">
            <div className="lg:col-span-7">
              <span className="badge-pill-dark mb-6">
                Institutional Workspace
              </span>
              <h1 className="display-xl text-white">
                Make your next move.
              </h1>
              <p className="mt-5 max-w-xl text-base md:text-lg text-[#a8acb3] leading-relaxed">
                Prepare, fill, and track job applications with deterministic profile grounding,
                zero hallucination safeguards, and durable local audit records.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-4 text-xs text-[#a8acb3]">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-[#05b169]" />
                  <span>Greenhouse Verified</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-[#0052ff]" />
                  <span>100% Local Retention</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-[#f4b000]" />
                  <span>Human Review Guardrails</span>
                </div>
              </div>
            </div>

            {/* Layered Product-UI Mockup Cards */}
            <div className="lg:col-span-5 flex justify-center lg:justify-end">
              <div className="mockup-stack">
                <div className="mockup-stack-back" />
                <div className="mockup-stack-front product-ui-card-dark">
                  <div className="flex items-center justify-between text-xs text-[#a8acb3]">
                    <span className="font-semibold uppercase tracking-wider">AUTOMATION ENGINE</span>
                    <span className="text-[#05b169] flex items-center gap-1 font-mono">● LIVE</span>
                  </div>
                  <div className="my-5 flex items-center justify-between">
                    <span className="text-xl font-normal text-white tracking-tight">Greenhouse Agent</span>
                    <span className="text-2xl text-[#0052ff]">↗</span>
                  </div>
                  <div className="h-px w-full bg-[#292c32] mb-5" />
                  <div className="space-y-3 text-xs">
                    <div className="flex justify-between text-[#a8acb3]">
                      <span>PROFILE GROUNDING</span>
                      <strong className="text-white font-mono">100% Exact</strong>
                    </div>
                    <div className="flex justify-between text-[#a8acb3]">
                      <span>CONFIRMATION GATE</span>
                      <strong className="text-white font-mono">Double-check</strong>
                    </div>
                    <div className="flex justify-between text-[#a8acb3]">
                      <span>RUNTIME</span>
                      <strong className="text-white font-mono">Local Chromium</strong>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Main Form & Application Workspace */}
      <section className="py-12 md:py-16 bg-white flex-1">
        <div className="content-container">
          <div className="mx-auto max-w-4xl space-y-10">
            {/* Step 1: Start Application Feature Card */}
            <div className="feature-card">
              <div className="flex items-start gap-4 mb-6">
                <div className="asset-icon-circular text-[#0052ff] bg-[#eef0f3] font-bold">
                  01
                </div>
                <div>
                  <h2 className="title-md text-[#0a0b0d]">Role Specification</h2>
                  <p className="body-sm text-[#5b616e] mt-0.5">
                    Paste the direct Greenhouse job board URL for the target position.
                  </p>
                </div>
              </div>

              <div>
                <label
                  htmlFor="job-url"
                  className="block text-xs font-semibold uppercase tracking-wider text-[#5b616e] mb-2"
                >
                  Job Application URL
                </label>
                <div className="relative">
                  <input
                    id="job-url"
                    value={jobUrl}
                    onChange={(event) => setJobUrl(event.target.value)}
                    className="text-input pr-28"
                    placeholder="https://job-boards.greenhouse.io/company/jobs/123456"
                    disabled={starting}
                  />
                  <div className="absolute right-3 top-1/2 -translate-y-1/2">
                    <span className="badge-pill !text-[10px] !py-1 !px-2.5">
                      Greenhouse
                    </span>
                  </div>
                </div>
                <p className="mt-2.5 text-xs text-[#7c828a]">
                  Supports direct Greenhouse application pages. Search-result pages and generic listing indexes are rejected.
                </p>
              </div>

              {/* Mode Toggle */}
              <div className="mt-6 rounded-2xl border border-[#dee1e6] bg-[#fafbfc] p-4">
                <label className="flex items-start gap-3.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={autoSubmit}
                    onChange={(event) => setAutoSubmit(event.target.checked)}
                    disabled={starting}
                    className="mt-1 h-4 w-4 rounded border-[#dee1e6] text-[#0052ff] focus:ring-[#0052ff]"
                  />
                  <div>
                    <span className="block text-sm font-semibold text-[#0a0b0d]">
                      Submit automatically after completing all fields
                    </span>
                    <span className="mt-1 block text-xs text-[#5b616e] leading-relaxed">
                      When active, the agent clicks Submit only when every field is grounded and no review items remain.
                      CAPTCHA, authentication, and ambiguity always trigger a safe pause. Turn off to inspect before submitting.
                    </span>
                  </div>
                </label>
              </div>

              {/* Launch CTA */}
              <div className="mt-6">
                <button
                  onClick={handleStartApplication}
                  disabled={starting}
                  className="btn-pill-cta w-full sm:w-auto"
                >
                  {starting ? (
                    <>
                      <span className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" />
                      <span>Initializing Application...</span>
                    </>
                  ) : (
                    <>
                      <span>Start Application</span>
                      <span>→</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Notification Messages */}
            {error && (
              <div className="rounded-2xl border border-[#dee1e6] bg-[#fafbfc] p-4 text-sm text-[#cf202f]">
                {error}
              </div>
            )}
            {message && (
              <div className="rounded-2xl border border-[#dee1e6] bg-[#fafbfc] p-4 text-sm text-[#05b169]">
                {message}
              </div>
            )}

            {/* Profile Health Notice */}
            {profile && (!hasName || !profile.personal.email) && (
              <div className="rounded-2xl border border-[#dee1e6] bg-[#fafbfc] p-5 text-sm text-[#5b616e]">
                <div className="flex items-center gap-2 font-semibold text-[#0a0b0d]">
                  <span className="text-[#f4b000]">●</span>
                  Profile Incomplete
                </div>
                <p className="mt-1.5 text-xs text-[#5b616e]">
                  Your full name or email address is missing. Please{" "}
                  <Link href="/profile" className="font-semibold text-[#0052ff] underline">
                    complete your profile
                  </Link>{" "}
                  before executing automated applications.
                </p>
              </div>
            )}

            {/* Step 2: Document Attachments Grid */}
            <div>
              <div className="flex items-center justify-between mb-4">
                <h3 className="title-sm text-[#0a0b0d]">Active Application Documents</h3>
                <Link href="/profile" className="btn-tertiary-text text-xs">
                  Manage in Profile →
                </Link>
              </div>

              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                <div className="feature-card !p-6">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-sm font-semibold text-[#0a0b0d]">Resume Attachment</span>
                    <span className="badge-pill !text-[11px]">Primary</span>
                  </div>
                  <FilePicker
                    accept=".pdf,.doc,.docx,.txt,.rtf"
                    buttonLabel={profile?.resume_path ? "Replace Resume" : "Attach Resume"}
                    selectedName={fileName(profile?.resume_path ?? "")}
                    onSelect={handleResumeUpload}
                    disabled={uploading}
                    helpText="PDF, DOCX, TXT, or RTF up to 10 MB. Attached locally during form submission."
                  />
                  {uploading && (
                    <p className="mt-2 text-xs font-medium text-[#0052ff]">
                      Uploading and verifying resume...
                    </p>
                  )}
                </div>

                <div className="feature-card !p-6">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-sm font-semibold text-[#0a0b0d]">Cover Letter Attachment</span>
                    <span className="badge-pill !text-[11px]">Optional</span>
                  </div>
                  <FilePicker
                    accept=".pdf,.doc,.docx,.txt,.rtf"
                    buttonLabel={profile?.cover_letter_path ? "Replace Letter" : "Attach Letter"}
                    selectedName={fileName(profile?.cover_letter_path ?? "")}
                    onSelect={handleCoverLetterUpload}
                    disabled={uploadingCoverLetter}
                    helpText="Stored locally and automatically filled in cover letter field prompts."
                  />
                  {uploadingCoverLetter && (
                    <p className="mt-2 text-xs font-medium text-[#0052ff]">
                      Uploading cover letter...
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* Active Application Telemetry & Inspector */}
            {applicationId !== null && (
              <div className="feature-card !p-8 border-2 border-[#0052ff]/20">
                <div className="flex flex-wrap items-center justify-between gap-4 pb-6 border-b border-[#dee1e6]">
                  <div>
                    <span className="caption-strong text-[#7c828a] block">ACTIVE EXECUTION</span>
                    <h3 className="title-md text-[#0a0b0d] mt-1">
                      Application #{applicationId}
                      {application?.company ? ` · ${application.company}` : ""}
                    </h3>
                  </div>
                  {application && renderStatusBadge(application.status)}
                </div>

                {/* Telemetry Metrics */}
                <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <div className="rounded-xl border border-[#eef0f3] bg-[#fafbfc] p-3.5">
                    <span className="caption text-[#7c828a] block">COMPANY</span>
                    <strong className="text-sm font-semibold text-[#0a0b0d] block mt-1 truncate">
                      {application?.company || "Detecting..."}
                    </strong>
                  </div>
                  <div className="rounded-xl border border-[#eef0f3] bg-[#fafbfc] p-3.5">
                    <span className="caption text-[#7c828a] block">ROLE</span>
                    <strong className="text-sm font-semibold text-[#0a0b0d] block mt-1 truncate">
                      {application?.role || "Detecting..."}
                    </strong>
                  </div>
                  <div className="rounded-xl border border-[#eef0f3] bg-[#fafbfc] p-3.5">
                    <span className="caption text-[#7c828a] block">FIELDS FILLED</span>
                    <strong className="number-display text-sm text-[#0a0b0d] block mt-1">
                      {fieldsFilled} filled
                    </strong>
                  </div>
                  <div className="rounded-xl border border-[#eef0f3] bg-[#fafbfc] p-3.5">
                    <span className="caption text-[#7c828a] block">SUBMITTED AT</span>
                    <strong className="number-display text-xs text-[#0a0b0d] block mt-1 truncate">
                      {formatDateTime(application?.submitted_at ?? null)}
                    </strong>
                  </div>
                </div>

                {/* Last Error Notice */}
                {application?.last_error && (
                  <div className="mt-5 rounded-xl border border-[#dee1e6] bg-[#fafbfc] p-4 text-xs text-[#cf202f]">
                    <span className="font-semibold block mb-1">Execution Notice:</span>
                    {application.last_error}
                  </div>
                )}

                {/* In Progress Live Pulse */}
                {application?.status === "In Progress" && (
                  <div className="mt-6 rounded-2xl border border-[#0052ff]/20 bg-[#f0f4ff]/50 p-5">
                    <div className="flex items-center gap-3">
                      <span className="h-3 w-3 rounded-full bg-[#0052ff] animate-ping" />
                      <span className="text-sm font-semibold text-[#0a0b0d]">
                        Browser automation is executing locally
                      </span>
                    </div>
                    {latestEvent && (
                      <p className="mt-2 text-xs text-[#5b616e] font-mono bg-white p-2.5 rounded-lg border border-[#dee1e6]">
                        Current Step: {latestEvent.message}
                      </p>
                    )}
                    <p className="mt-2 text-[11px] text-[#7c828a]">
                      Telemetry refreshes automatically every 3 seconds.
                    </p>
                  </div>
                )}

                {/* Submission Confirmed Receipt */}
                {application?.status === "Submitted" && confirmation && (
                  <div className="mt-6 rounded-2xl border border-[#dee1e6] bg-[#fafbfc] p-5">
                    <div className="flex items-center gap-2">
                      <span className="text-[#05b169] text-base font-bold">✓</span>
                      <h4 className="text-sm font-semibold text-[#0a0b0d]">
                        Submission Verified and Recorded
                      </h4>
                    </div>
                    {confirmation.message && (
                      <p className="mt-2 text-xs text-[#5b616e] leading-relaxed">
                        {confirmation.message}
                      </p>
                    )}
                    {confirmation.url && (
                      <a
                        href={confirmation.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn-tertiary-text text-xs mt-3"
                      >
                        Open Official Confirmation Page ↗
                      </a>
                    )}
                  </div>
                )}

                {/* Manual Verification Required Gate */}
                {needsManualVerification && (
                  <div className="mt-6 rounded-2xl border border-[#dee1e6] bg-[#fafbfc] p-5">
                    <div className="flex items-center gap-2 text-sm font-semibold text-[#0a0b0d]">
                      <span className="text-[#f4b000]">●</span>
                      Manual Employer Verification Required
                    </div>
                    <p className="mt-2 text-xs text-[#5b616e] leading-relaxed">
                      The agent submitted the application form, but the confirmation response was indeterminate.
                      To protect against duplicate submissions, please verify the status in your browser or email.
                    </p>
                    <div className="mt-4 flex flex-wrap gap-3">
                      <button
                        onClick={handleConfirmSubmission}
                        disabled={actionPending}
                        className="btn-primary text-xs"
                      >
                        I Verified It Was Submitted
                      </button>
                      <button
                        onClick={handleMarkNotSubmitted}
                        disabled={actionPending}
                        className="btn-secondary-light text-xs"
                      >
                        It Was Not Submitted
                      </button>
                    </div>
                  </div>
                )}

                {/* Review Items Resolver */}
                {application && application.review_items.length > 0 && (
                  <div className="mt-8 pt-6 border-t border-[#dee1e6]">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="title-sm text-[#0a0b0d]">
                        Review Items ({openReviewItems.length} open)
                      </h4>
                      <span className="badge-pill !text-[10px]">
                        Human Verification
                      </span>
                    </div>
                    <p className="text-xs text-[#7c828a]">
                      The agent halts execution whenever a question cannot be safely answered from your profile.
                    </p>
                    <ReviewItems
                      applicationId={application.id}
                      items={application.review_items}
                      onChanged={handleReviewChanged}
                      disabled={actionPending || application.status !== "Needs Review"}
                    />
                  </div>
                )}

                {/* Progress History Log */}
                {application && application.events.length > 0 && (
                  <div className="mt-8 pt-6 border-t border-[#dee1e6]">
                    <h4 className="title-sm text-[#0a0b0d] mb-4">
                      Execution Timeline
                    </h4>
                    <div className="space-y-2.5 max-h-60 overflow-y-auto pr-2">
                      {application.events.map((event) => (
                        <div
                          key={event.id}
                          className="flex items-start gap-3 rounded-xl border border-[#eef0f3] bg-[#fafbfc] p-3 text-xs"
                        >
                          <span className="font-mono text-[#7c828a] shrink-0 text-[11px]">
                            {formatDateTime(event.created_at)}
                          </span>
                          <span className="text-[#0a0b0d] leading-relaxed">
                            {event.message}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Primary Action Controls */}
                <div className="mt-8 flex flex-wrap items-center gap-3 pt-6 border-t border-[#dee1e6]">
                  {application?.status === "Needs Review" && !needsManualVerification && (
                    <button
                      onClick={handleResumeApplication}
                      disabled={actionPending || !canResume}
                      className="btn-primary"
                    >
                      {openReviewItems.length > 0
                        ? "Resolve Review Items First"
                        : "Resume & Submit Application"}
                    </button>
                  )}

                  {application?.status === "Failed" && (
                    <button
                      onClick={handleRetryApplication}
                      disabled={actionPending}
                      className="btn-primary"
                    >
                      Retry Application
                    </button>
                  )}

                  <Link href="/applications" className="btn-secondary-light">
                    View in Application Ledger
                  </Link>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
