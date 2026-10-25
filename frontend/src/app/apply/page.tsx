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
  statusClasses,
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
        `Application #${created.application_id} created. ${
          created.auto_submit
            ? "Automatic submission is on; it will submit after a complete fill with no review items."
            : "Fill-only mode is on; you can review it before submitting."
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
      setMessage(`Resume saved: ${fileName(path)}`);
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
      setMessage(`Cover letter saved: ${fileName(result.cover_letter_path)}`);
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
      setMessage("Retry initiated.");
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
      setMessage("Submission marked as confirmed.");
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
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-3xl">
        <h1 className="mb-6 text-2xl font-bold">Apply for a Job</h1>

        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <label
            htmlFor="job-url"
            className="mb-2 block text-sm font-medium text-gray-700"
          >
            Job Application URL
          </label>
          <input
            id="job-url"
            value={jobUrl}
            onChange={(event) => setJobUrl(event.target.value)}
            className="w-full rounded border border-gray-300 px-3 py-2 text-gray-800 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="https://job-boards.greenhouse.io/company/jobs/123456"
            disabled={starting}
          />
          <p className="mt-2 text-xs text-gray-500">
            Paste a direct Greenhouse job-board link. MyGreenhouse search-result
            links are not application forms and are not supported.
          </p>

          <label className="mt-4 flex cursor-pointer items-start gap-3 rounded border border-gray-200 bg-gray-50 p-3">
            <input
              type="checkbox"
              checked={autoSubmit}
              onChange={(event) => setAutoSubmit(event.target.checked)}
              disabled={starting}
              className="mt-0.5 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span>
              <span className="block text-sm font-medium text-gray-800">
                Submit automatically after filling
              </span>
              <span className="mt-1 block text-xs text-gray-600">
                When enabled, the agent clicks Submit after a complete fill with
                no unresolved review items. Login, OTP, CAPTCHA, and review
                prompts still pause the run. Turn this off to fill only and
                review before submitting.
              </span>
            </span>
          </label>

          <div className="mt-4">
            <button
              onClick={handleStartApplication}
              disabled={starting}
              className="rounded bg-blue-600 px-4 py-2 font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
            >
              {starting ? "Creating application..." : "Start Application"}
            </button>
          </div>
        </div>

        {error && (
          <div className="mt-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}
        {message && (
          <div className="mt-4 rounded border border-green-200 bg-green-50 p-3 text-sm text-green-700">
            {message}
          </div>
        )}

        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="mb-3 text-sm font-semibold text-gray-900">Resume</h2>
            <FilePicker
              accept=".pdf,.doc,.docx,.txt,.rtf"
              buttonLabel={profile?.resume_path ? "Replace Resume" : "Choose Resume"}
              selectedName={fileName(profile?.resume_path ?? "")}
              onSelect={handleResumeUpload}
              disabled={uploading}
              helpText="PDF, DOC, DOCX, TXT, or RTF up to 10 MB. Stored locally in backend/uploads."
            />
            {uploading && (
              <p className="mt-2 text-sm font-medium text-blue-700">
                Uploading resume...
              </p>
            )}
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="mb-3 text-sm font-semibold text-gray-900">
              Cover Letter
            </h2>
            <FilePicker
              accept=".pdf,.doc,.docx,.txt,.rtf"
              buttonLabel={
                profile?.cover_letter_path
                  ? "Replace Cover Letter"
                  : "Choose Cover Letter"
              }
              selectedName={fileName(profile?.cover_letter_path ?? "")}
              onSelect={handleCoverLetterUpload}
              disabled={uploadingCoverLetter}
              helpText="Upload a cover letter file to store it and fill its text in your profile. Max 10 MB."
            />
            {uploadingCoverLetter && (
              <p className="mt-2 text-sm font-medium text-blue-700">
                Uploading cover letter...
              </p>
            )}
          </div>
        </div>

        {profile &&
          (!hasName || !profile.personal.email) && (
            <div className="mt-4 rounded border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800">
              Your name or email is missing.{" "}
              <Link href="/profile" className="font-medium underline">
                Complete your profile
              </Link>{" "}
              before an application can be filled.
            </div>
          )}

        {applicationId !== null && (
          <div className="mt-6 rounded-lg border border-blue-200 bg-blue-50 p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold text-gray-900">
                Application #{applicationId}
              </h2>
              {application && (
                <span
                  className={`rounded px-2 py-1 text-xs font-medium ${statusClasses(
                    application.status
                  )}`}
                >
                  {application.status}
                </span>
              )}
            </div>

            <dl className="mt-4 grid grid-cols-1 gap-2 text-sm text-gray-700 sm:grid-cols-3">
              <div>
                <dt className="text-xs uppercase tracking-wide text-gray-500">
                  Company
                </dt>
                <dd>{application?.company || "Not detected yet"}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-gray-500">
                  Role
                </dt>
                <dd>{application?.role || "Not detected yet"}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-gray-500">
                  Fields filled
                </dt>
                <dd>
                  {fieldsFilled} filled · {openReviewItems.length} need review
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-gray-500">
                  Submitted
                </dt>
                <dd>{formatDateTime(application?.submitted_at ?? null)}</dd>
              </div>
            </dl>

            {application?.last_error && (
              <p className="mt-3 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
                {application.last_error}
              </p>
            )}

            {application?.status === "In Progress" && (
              <div className="mt-4 rounded border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">
                <p>
                  Automation is running in the browser window. This page
                  refreshes every 3 seconds.
                </p>
                {latestEvent && (
                  <p className="mt-1 text-blue-700">
                    Current step: {latestEvent.message}
                  </p>
                )}
              </div>
            )}

            {application?.status === "Submitted" && confirmation && (
              <div className="mt-4 rounded border border-green-200 bg-green-50 p-3 text-sm text-green-800">
                <p className="font-medium">Submission confirmed</p>
                {confirmation.message && <p>{confirmation.message}</p>}
                {confirmation.url && (
                  <a
                    href={confirmation.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline"
                  >
                    Open confirmation page
                  </a>
                )}
              </div>
            )}

            {needsManualVerification && (
              <div className="mt-4 rounded border border-yellow-300 bg-yellow-50 p-3 text-sm text-yellow-900">
                <p className="font-medium">
                  Submission outcome needs your verification
                </p>
                <p className="mt-1">
                  The agent clicked Submit but could not verify a confirmation.
                  Check the employer site first. Automatic resubmission is
                  disabled to avoid duplicate applications.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    onClick={handleConfirmSubmission}
                    disabled={actionPending}
                    className="rounded bg-green-600 px-3 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:bg-green-300"
                  >
                    I verified it was submitted
                  </button>
                  <button
                    onClick={handleMarkNotSubmitted}
                    disabled={actionPending}
                    className="rounded border border-yellow-500 bg-white px-3 py-2 text-sm font-semibold text-yellow-800 hover:bg-yellow-100 disabled:opacity-50"
                  >
                    It was not submitted
                  </button>
                </div>
              </div>
            )}

            {application?.status === "Needs Review" &&
              !needsManualVerification && (
                <p className="mt-4 text-sm text-yellow-800">
                  {openReviewItems.length > 0
                    ? "Answer the review items below. The agent will not submit until every item is resolved."
                    : canResume
                      ? "All review items are answered. Resume to refill and submit the application."
                      : "This application is paused. Check the error above before resuming."}
                </p>
              )}

            {application && application.review_items.length > 0 && (
              <div className="mt-4">
                <h3 className="text-sm font-semibold text-gray-900">
                  Review items
                </h3>
                <ReviewItems
                  applicationId={application.id}
                  items={application.review_items}
                  onChanged={handleReviewChanged}
                  disabled={actionPending || application.status !== "Needs Review"}
                />
              </div>
            )}

            {application && application.events.length > 0 && (
              <div className="mt-4">
                <h3 className="text-sm font-semibold text-gray-900">
                  Progress history
                </h3>
                <ol className="mt-2 space-y-2 border-l border-blue-300 pl-4 text-sm text-gray-700">
                  {application.events.map((event) => (
                    <li key={event.id}>
                      <p>{event.message}</p>
                      <p className="text-xs text-gray-500">
                        {formatDateTime(event.created_at)}
                      </p>
                    </li>
                  ))}
                </ol>
              </div>
            )}

            <div className="mt-5 flex flex-wrap gap-3">
              {application?.status === "Needs Review" &&
                !needsManualVerification && (
                  <button
                    onClick={handleResumeApplication}
                    disabled={
                      actionPending ||
                      openReviewItems.length > 0 ||
                      submissionWasAttempted
                    }
                    className="rounded bg-yellow-500 px-4 py-2 text-sm font-semibold text-white hover:bg-yellow-600 disabled:cursor-not-allowed disabled:bg-yellow-300"
                  >
                    {openReviewItems.length > 0
                      ? "Resolve all items first"
                      : "Resume & Submit"}
                  </button>
                )}
              {application?.status === "Failed" && (
                <button
                  onClick={handleRetryApplication}
                  disabled={actionPending}
                  className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:bg-blue-300"
                >
                  Retry Application
                </button>
              )}
              <Link
                href="/applications"
                className="rounded border border-gray-300 bg-white px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-100"
              >
                View All Applications
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
