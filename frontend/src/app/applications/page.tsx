"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  applicationsExportUrl,
  confirmationSummary,
  confirmSubmission,
  deleteApplication,
  formatDateTime,
  getApplication,
  listApplications,
  markNotSubmitted,
  resumeApplication,
  retryApplication,
  statusClasses,
} from "@/lib/api";
import type { Application, ApplicationDetail } from "@/lib/api";
import ReviewItems from "@/components/ReviewItems";

const STATUSES = ["In Progress", "Needs Review", "Submitted", "Failed"];

function errorMessage(error: unknown): string {
  return error instanceof ApiError || error instanceof Error
    ? error.message
    : String(error);
}

export default function ApplicationsPage() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionPending, setActionPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadApplications = useCallback(async (filter: string) => {
    setLoading(true);
    try {
      const data = await listApplications(filter || undefined);
      setApplications(data);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (id: number) => {
    try {
      setDetail(await getApplication(id));
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    let active = true;
    listApplications(statusFilter || undefined)
      .then((data) => {
        if (active) {
          setApplications(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (active) setError(errorMessage(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [statusFilter]);

  useEffect(() => {
    if (selectedId === null) return;

    let active = true;
    getApplication(selectedId)
      .then((data) => {
        if (active) setDetail(data);
      })
      .catch((err) => {
        if (active) setError(errorMessage(err));
      });
    return () => {
      active = false;
    };
  }, [selectedId]);

  const handleRetry = async (id: number) => {
    setActionPending(true);
    setError(null);
    setMessage(null);
    try {
      await retryApplication(id);
      await loadApplications(statusFilter);
      if (selectedId === id) await loadDetail(id);
      setMessage(`Application #${id} retry initiated.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setActionPending(false);
    }
  };

  const handleResume = async (id: number) => {
    setActionPending(true);
    setError(null);
    setMessage(null);
    try {
      await resumeApplication(id, true);
      await loadApplications(statusFilter);
      if (selectedId === id) await loadDetail(id);
      setMessage(`Application #${id} resumed with automatic submission enabled.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setActionPending(false);
    }
  };

  const handleConfirmSubmission = async (id: number) => {
    if (
      !window.confirm(
        "Only confirm this after checking the employer site. This marks the application as submitted."
      )
    ) {
      return;
    }
    setActionPending(true);
    setError(null);
    setMessage(null);
    try {
      await confirmSubmission(
        id,
        "User manually verified the submission on the employer site."
      );
      await loadApplications(statusFilter);
      if (selectedId === id) await loadDetail(id);
      setMessage(`Application #${id} marked as submitted.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setActionPending(false);
    }
  };

  const handleMarkNotSubmitted = async (id: number) => {
    if (
      !window.confirm(
        "Only mark this if you verified the application was NOT submitted. This allows another automatic attempt."
      )
    ) {
      return;
    }
    setActionPending(true);
    setError(null);
    setMessage(null);
    try {
      await markNotSubmitted(
        id,
        "User verified the application was not submitted."
      );
      await loadApplications(statusFilter);
      if (selectedId === id) await loadDetail(id);
      setMessage(`Application #${id} marked as not submitted.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setActionPending(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm(`Delete application #${id}? This cannot be undone.`)) {
      return;
    }

    setActionPending(true);
    setError(null);
    setMessage(null);
    try {
      await deleteApplication(id);
      if (selectedId === id) {
        setSelectedId(null);
        setDetail(null);
      }
      await loadApplications(statusFilter);
      setMessage(`Application #${id} deleted.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setActionPending(false);
    }
  };

  const openReviewItems =
    detail?.review_items.filter((item) => !item.resolved_at) ?? [];
  const submissionOutcome = detail?.submission_outcome ?? null;
  const needsManualVerification =
    detail?.status === "Needs Review" &&
    (submissionOutcome === "pending" || submissionOutcome === "uncertain");
  const submissionWasAttempted = ["pending", "uncertain", "confirmed"].includes(
    submissionOutcome ?? ""
  );
  const confirmation = confirmationSummary(detail?.confirmation_details ?? null);

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-5xl">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-bold">All Applications</h1>
          <a
            href={applicationsExportUrl()}
            download="applications.json"
            className="rounded border border-blue-600 px-4 py-2 text-sm font-semibold text-blue-700 transition-colors hover:bg-blue-50"
          >
            Download JSON export
          </a>
        </div>

        <div className="mb-4 flex flex-wrap items-end gap-3">
          <div className="min-w-56">
            <label
              htmlFor="status-filter"
              className="mb-2 block text-sm font-medium text-gray-700"
            >
              Status Filter
            </label>
            <select
              id="status-filter"
              value={statusFilter}
              onChange={(event) => {
                setLoading(true);
                setStatusFilter(event.target.value);
              }}
              className="w-full rounded border border-gray-300 px-3 py-2 text-gray-800 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All Statuses</option>
              {STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={() => loadApplications(statusFilter)}
            className="rounded bg-green-600 px-4 py-2 font-semibold text-white transition-colors hover:bg-green-700"
          >
            Refresh
          </button>
        </div>

        {error && (
          <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}
        {message && (
          <div className="mb-4 rounded border border-green-200 bg-green-50 p-3 text-sm text-green-700">
            {message}
          </div>
        )}

        {loading ? (
          <p className="mt-4 text-sm text-gray-500">Loading applications...</p>
        ) : applications.length === 0 ? (
          <p className="mt-4 text-sm text-gray-500">
            No applications found.{" "}
            <a href="/apply" className="font-medium text-blue-600">
              Start a new application
            </a>
          </p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full overflow-hidden rounded-lg bg-white shadow-sm">
              <thead className="bg-gray-50">
                <tr className="border-b border-gray-200">
                  <th className="p-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Company
                  </th>
                  <th className="p-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Role
                  </th>
                  <th className="p-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    URL
                  </th>
                  <th className="p-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Status
                  </th>
                  <th className="p-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Created
                  </th>
                  <th className="p-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Updated
                  </th>
                  <th className="p-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {applications.map((application) => (
                  <tr
                    key={application.id}
                    className="border-b border-gray-100 hover:bg-gray-50"
                  >
                    <td className="p-3 text-sm">
                      {application.company || "-"}
                    </td>
                    <td className="p-3 text-sm">{application.role || "-"}</td>
                    <td className="max-w-64 truncate p-3 text-sm">
                      <a
                        href={application.job_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 underline hover:text-blue-800"
                        title={application.job_url}
                      >
                        {application.job_url}
                      </a>
                    </td>
                    <td className="p-3">
                      <span
                        className={`rounded px-2 py-1 text-xs font-medium ${statusClasses(
                          application.status
                        )}`}
                      >
                        {application.status}
                      </span>
                    </td>
                    <td className="p-3 text-xs text-gray-500">
                      {formatDateTime(application.created_at)}
                    </td>
                    <td className="p-3 text-xs text-gray-500">
                      {formatDateTime(application.updated_at)}
                    </td>
                    <td className="p-3">
                      <div className="flex flex-wrap gap-2 text-sm">
                        {application.status === "Failed" && (
                          <button
                            onClick={() => handleRetry(application.id)}
                            disabled={actionPending}
                            className="text-blue-600 hover:text-blue-800 disabled:text-blue-300"
                          >
                            Retry
                          </button>
                        )}
                        {application.status === "Needs Review" &&
                          !["pending", "uncertain", "confirmed"].includes(
                            application.submission_outcome ?? ""
                          ) && (
                            <button
                              onClick={() => handleResume(application.id)}
                              disabled={actionPending}
                              className="text-yellow-600 hover:text-yellow-800 disabled:text-yellow-300"
                            >
                              Resume
                            </button>
                          )}
                        <button
                          onClick={() => {
                            if (selectedId === application.id) {
                              // Re-open/reload an already selected detail panel.
                              void loadDetail(application.id);
                            } else {
                              setDetail(null);
                              setSelectedId(application.id);
                            }
                          }}
                          className="text-gray-600 hover:text-gray-900"
                        >
                          Detail
                        </button>
                        <button
                          onClick={() => handleDelete(application.id)}
                          disabled={actionPending}
                          className="text-red-600 hover:text-red-800 disabled:text-red-300"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {selectedId !== null && (
          <div className="mt-8 rounded-lg border border-gray-200 bg-gray-50 p-6">
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-xl font-bold">
                Application #{selectedId}
                {detail ? ` · ${detail.company || "Unknown company"}` : ""}
              </h2>
              <button
                onClick={() => {
                  setSelectedId(null);
                  setDetail(null);
                }}
                className="text-sm text-gray-500 hover:text-gray-800"
              >
                Close
              </button>
            </div>

            {!detail ? (
              <p className="mt-3 text-sm text-gray-500">Loading detail...</p>
            ) : (
              <>
                <dl className="mt-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-gray-500">
                      Company
                    </dt>
                    <dd>{detail.company || "-"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-gray-500">
                      Role
                    </dt>
                    <dd>{detail.role || "-"}</dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="text-xs uppercase tracking-wide text-gray-500">
                      Job URL
                    </dt>
                    <dd className="truncate">
                      <a
                        href={detail.job_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 underline"
                      >
                        {detail.job_url}
                      </a>
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-gray-500">
                      Status
                    </dt>
                    <dd>
                      <span
                        className={`rounded px-2 py-1 text-xs font-medium ${statusClasses(
                          detail.status
                        )}`}
                      >
                        {detail.status}
                      </span>
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-gray-500">
                      Submitted
                    </dt>
                    <dd>{formatDateTime(detail.submitted_at)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-gray-500">
                      Submission outcome
                    </dt>
                    <dd>{detail.submission_outcome || "-"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-gray-500">
                      Created
                    </dt>
                    <dd>{formatDateTime(detail.created_at)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-gray-500">
                      Updated
                    </dt>
                    <dd>{formatDateTime(detail.updated_at)}</dd>
                  </div>
                </dl>

                {detail.last_error && (
                  <p className="mt-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                    <strong>Error:</strong> {detail.last_error}
                  </p>
                )}

                {detail.status === "Submitted" && confirmation && (
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
                      The agent clicked Submit but could not verify a
                      confirmation. Check the employer site first. Automatic
                      resubmission is disabled to avoid duplicate applications.
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        onClick={() =>
                          selectedId !== null &&
                          handleConfirmSubmission(selectedId)
                        }
                        disabled={actionPending}
                        className="rounded bg-green-600 px-3 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:bg-green-300"
                      >
                        I verified it was submitted
                      </button>
                      <button
                        onClick={() =>
                          selectedId !== null &&
                          handleMarkNotSubmitted(selectedId)
                        }
                        disabled={actionPending}
                        className="rounded border border-yellow-500 bg-white px-3 py-2 text-sm font-semibold text-yellow-800 hover:bg-yellow-100 disabled:opacity-50"
                      >
                        It was not submitted
                      </button>
                    </div>
                  </div>
                )}

                <h3 className="mt-6 text-lg font-medium">Progress History</h3>
                {detail.events.length === 0 ? (
                  <p className="mt-2 text-sm text-gray-500">No events yet.</p>
                ) : (
                  <ol className="mt-2 space-y-2 border-l border-blue-300 pl-4 text-sm text-gray-700">
                    {detail.events.map((event) => (
                      <li key={event.id}>
                        <p>{event.message}</p>
                        <p className="text-xs text-gray-500">
                          {event.event_type} · {formatDateTime(event.created_at)}
                        </p>
                      </li>
                    ))}
                  </ol>
                )}

                <h3 className="mt-6 text-lg font-medium">Review Items</h3>
                <ReviewItems
                  applicationId={detail.id}
                  items={detail.review_items}
                  onChanged={() => loadDetail(detail.id)}
                  disabled={actionPending || detail.status !== "Needs Review"}
                />

                {detail.status === "Needs Review" &&
                  !needsManualVerification && (
                    <div className="mt-4 flex flex-wrap items-center gap-3">
                      <button
                        onClick={() => handleResume(detail.id)}
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
                      {openReviewItems.length > 0 && (
                        <span className="text-sm text-gray-600">
                          {openReviewItems.length} unanswered item(s)
                        </span>
                      )}
                    </div>
                  )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
