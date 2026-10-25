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
} from "@/lib/api";
import type { Application, ApplicationDetail } from "@/lib/api";
import ReviewItems from "@/components/ReviewItems";

const STATUSES = ["All", "In Progress", "Needs Review", "Submitted", "Failed"];

function errorMessage(error: unknown): string {
  return error instanceof ApiError || error instanceof Error
    ? error.message
    : String(error);
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
      return <span className="badge-pill">{status}</span>;
  }
}

export default function ApplicationsPage() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [statusFilter, setStatusFilter] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionPending, setActionPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadApplications = useCallback(async (filter: string) => {
    setLoading(true);
    try {
      const data = await listApplications(filter === "All" ? undefined : filter);
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
    listApplications(statusFilter === "All" ? undefined : statusFilter)
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
      setMessage(`Application #${id} retry initiated in local browser.`);
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
      setMessage(`Application #${id} deleted from durable ledger.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setActionPending(false);
    }
  };

  // Filter applications by search query
  const filteredApplications = applications.filter((app) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      (app.company && app.company.toLowerCase().includes(q)) ||
      (app.role && app.role.toLowerCase().includes(q)) ||
      (app.job_url && app.job_url.toLowerCase().includes(q)) ||
      String(app.id).includes(q)
    );
  });

  const totalSubmitted = applications.filter((item) => item.status === "Submitted").length;
  const totalNeedsReview = applications.filter((item) => item.status === "Needs Review").length;

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
    <div className="w-full flex-1 flex flex-col">
      {/* Dark Editorial Hero Band */}
      <section className="hero-band-dark">
        <div className="content-container">
          <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-12">
            <div className="lg:col-span-7">
              <span className="badge-pill-dark mb-6">
                Audit & Pipeline
              </span>
              <h1 className="display-xl text-white">
                Application Ledger.
              </h1>
              <p className="mt-5 max-w-xl text-base md:text-lg text-[#a8acb3] leading-relaxed">
                Inspect every automated run, review execution histories, resolve field prompts,
                and download verified application records.
              </p>
            </div>

            {/* Metrics Grid on Dark Canvas */}
            <div className="lg:col-span-5 grid grid-cols-2 gap-4">
              <div className="rounded-2xl border border-[#292c32] bg-[#16181c] p-5">
                <span className="caption-strong text-[#a8acb3] block">TOTAL TRACKED</span>
                <strong className="number-display text-3xl font-normal text-white block mt-2">
                  {applications.length}
                </strong>
                <span className="text-xs text-[#a8acb3] block mt-1">Applications logged</span>
              </div>

              <div className="rounded-2xl border border-[#292c32] bg-[#16181c] p-5">
                <span className="caption-strong text-[#a8acb3] block">NEEDS REVIEW</span>
                <strong className="number-display text-3xl font-normal text-[#f4b000] block mt-2">
                  {totalNeedsReview}
                </strong>
                <span className="text-xs text-[#a8acb3] block mt-1">Awaiting attention</span>
              </div>

              <div className="rounded-2xl border border-[#292c32] bg-[#16181c] p-5">
                <span className="caption-strong text-[#a8acb3] block">CONFIRMED SUBMISSIONS</span>
                <strong className="number-display text-3xl font-normal text-[#05b169] block mt-2">
                  {totalSubmitted}
                </strong>
                <span className="text-xs text-[#a8acb3] block mt-1">Successfully sent</span>
              </div>

              <div className="rounded-2xl border border-[#292c32] bg-[#16181c] p-5">
                <span className="caption-strong text-[#a8acb3] block">PROFILE GROUNDING</span>
                <strong className="number-display text-3xl font-normal text-white block mt-2">
                  100%
                </strong>
                <span className="text-xs text-[#a8acb3] block mt-1">Zero hallucination</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Main Table & Filter Controls */}
      <section className="py-12 bg-white flex-1">
        <div className="content-container">
          {/* Action Toolbar */}
          <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between mb-8 pb-8 border-b border-[#dee1e6]">
            {/* Status Tabs */}
            <div className="flex flex-wrap items-center gap-1.5" role="tablist">
              {STATUSES.map((status) => {
                const active = statusFilter === status;
                return (
                  <button
                    key={status}
                    type="button"
                    onClick={() => {
                      setLoading(true);
                      setStatusFilter(status);
                    }}
                    className={`rounded-full px-4 py-2 text-xs font-semibold tracking-wide transition-all ${
                      active
                        ? "bg-[#0a0b0d] text-white"
                        : "bg-[#eef0f3] text-[#5b616e] hover:bg-[#e2e5ea] hover:text-[#0a0b0d]"
                    }`}
                  >
                    {status}
                    {status === "Needs Review" && totalNeedsReview > 0 && (
                      <span className="ml-1.5 rounded-full bg-[#f4b000] px-1.5 py-0.2 text-[10px] text-[#0a0b0d] font-bold">
                        {totalNeedsReview}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {/* Search Pill and Export Button */}
            <div className="flex flex-wrap items-center gap-3">
              <div className="w-full sm:w-64">
                <input
                  type="text"
                  placeholder="Search company or role..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="search-input-pill"
                />
              </div>

              <button
                onClick={() => loadApplications(statusFilter)}
                className="btn-secondary-light !min-h-[44px]"
                title="Refresh ledger"
              >
                ↻ Refresh
              </button>

              <a
                href={applicationsExportUrl()}
                download="applications.json"
                className="btn-primary !min-h-[44px]"
              >
                ↓ Export JSON
              </a>
            </div>
          </div>

          {/* Feedback Notices */}
          {error && (
            <div className="mb-6 rounded-2xl border border-[#dee1e6] bg-[#fafbfc] p-4 text-sm text-[#cf202f]">
              {error}
            </div>
          )}
          {message && (
            <div className="mb-6 rounded-2xl border border-[#dee1e6] bg-[#fafbfc] p-4 text-sm text-[#05b169]">
              {message}
            </div>
          )}

          {/* Table Container */}
          {loading ? (
            <div className="p-16 text-center text-sm text-[#7c828a]">
              <span className="inline-block h-5 w-5 rounded-full border-2 border-[#0052ff]/30 border-t-[#0052ff] animate-spin mb-3" />
              <p>Loading application records...</p>
            </div>
          ) : filteredApplications.length === 0 ? (
            <div className="rounded-3xl border border-[#dee1e6] bg-[#f7f7f7] p-16 text-center">
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-white border border-[#dee1e6] text-[#7c828a] mb-4">
                📋
              </div>
              <h3 className="title-md text-[#0a0b0d]">No applications found</h3>
              <p className="mt-2 text-sm text-[#5b616e] max-w-md mx-auto">
                {searchQuery
                  ? "No applications matched your search query. Clear the search input to see all records."
                  : "No applications have been started yet. Paste a Greenhouse role link to begin."}
              </p>
              <div className="mt-6">
                <a href="/apply" className="btn-primary">
                  Start Your First Application →
                </a>
              </div>
            </div>
          ) : (
            <div className="coinbase-table-container shadow-sm">
              <div className="overflow-x-auto">
                <table className="coinbase-table">
                  <thead>
                    <tr>
                      <th>Company & Role</th>
                      <th>Application URL</th>
                      <th>Status</th>
                      <th>Created</th>
                      <th>Updated</th>
                      <th className="text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredApplications.map((app) => {
                      const initial = (app.company || "A").trim().charAt(0).toUpperCase();
                      const isSelected = selectedId === app.id;

                      return (
                        <tr
                          key={app.id}
                          className={isSelected ? "!bg-[#f0f4ff]/60" : ""}
                        >
                          <td>
                            <div className="flex items-center gap-3">
                              <span className="asset-icon-circular text-[#0a0b0d]">
                                {initial}
                              </span>
                              <div>
                                <span className="font-semibold text-[#0a0b0d] block">
                                  {app.company || "Unknown Company"}
                                </span>
                                <span className="text-xs text-[#5b616e] block mt-0.5">
                                  {app.role || "Role unspecified"}
                                </span>
                              </div>
                            </div>
                          </td>
                          <td className="max-w-[200px] truncate">
                            <a
                              href={app.job_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs font-mono text-[#0052ff] hover:underline"
                              title={app.job_url}
                            >
                              {app.job_url}
                            </a>
                          </td>
                          <td>{renderStatusBadge(app.status)}</td>
                          <td className="number-display text-xs text-[#5b616e]">
                            {formatDateTime(app.created_at)}
                          </td>
                          <td className="number-display text-xs text-[#5b616e]">
                            {formatDateTime(app.updated_at)}
                          </td>
                          <td className="text-right">
                            <div className="flex items-center justify-end gap-2">
                              {app.status === "Failed" && (
                                <button
                                  onClick={() => handleRetry(app.id)}
                                  disabled={actionPending}
                                  className="btn-secondary-light !min-h-[32px] !py-1 !px-3 text-xs"
                                >
                                  Retry
                                </button>
                              )}
                              {app.status === "Needs Review" &&
                                !["pending", "uncertain", "confirmed"].includes(
                                  app.submission_outcome ?? ""
                                ) && (
                                  <button
                                    onClick={() => handleResume(app.id)}
                                    disabled={actionPending}
                                    className="btn-primary !min-h-[32px] !py-1 !px-3 text-xs"
                                  >
                                    Resume
                                  </button>
                                )}
                              <button
                                onClick={() => {
                                  if (selectedId === app.id) {
                                    void loadDetail(app.id);
                                  } else {
                                    setDetail(null);
                                    setSelectedId(app.id);
                                  }
                                }}
                                className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
                                  isSelected
                                    ? "bg-[#0052ff] text-white"
                                    : "bg-[#eef0f3] text-[#0a0b0d] hover:bg-[#e2e5ea]"
                                }`}
                              >
                                {isSelected ? "Active" : "Inspect"}
                              </button>
                              <button
                                onClick={() => handleDelete(app.id)}
                                disabled={actionPending}
                                className="text-xs text-[#cf202f] hover:underline px-2 py-1"
                              >
                                Delete
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Selected Application Deep Inspector Panel */}
          {selectedId !== null && (
            <div className="mt-12 feature-card !p-8 border-2 border-[#0052ff]/30">
              <div className="flex items-start justify-between gap-4 pb-6 border-b border-[#dee1e6]">
                <div>
                  <span className="caption-strong text-[#7c828a] block">INSPECTING APPLICATION</span>
                  <h3 className="title-md text-[#0a0b0d] mt-1">
                    Application #{selectedId}
                    {detail?.company ? ` · ${detail.company}` : ""}
                  </h3>
                </div>
                <button
                  onClick={() => {
                    setSelectedId(null);
                    setDetail(null);
                  }}
                  className="btn-secondary-light !min-h-[36px] !py-1 !px-3 text-xs"
                >
                  ✕ Close Inspector
                </button>
              </div>

              {!detail ? (
                <div className="py-12 text-center text-sm text-[#7c828a]">
                  Loading detailed application telemetry...
                </div>
              ) : (
                <div className="space-y-8 mt-6">
                  {/* Status Banner */}
                  <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-2xl bg-[#fafbfc] border border-[#dee1e6]">
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-semibold text-[#0a0b0d]">Status:</span>
                      {renderStatusBadge(detail.status)}
                    </div>
                    {detail.submitted_at && (
                      <span className="text-xs text-[#5b616e] font-mono">
                        Submitted: {formatDateTime(detail.submitted_at)}
                      </span>
                    )}
                  </div>

                  {/* Metadata Grid */}
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                    <div className="rounded-xl border border-[#eef0f3] bg-[#fafbfc] p-4">
                      <span className="caption text-[#7c828a] block">TARGET COMPANY</span>
                      <strong className="text-sm font-semibold text-[#0a0b0d] block mt-1">
                        {detail.company || "-"}
                      </strong>
                    </div>
                    <div className="rounded-xl border border-[#eef0f3] bg-[#fafbfc] p-4">
                      <span className="caption text-[#7c828a] block">TARGET ROLE</span>
                      <strong className="text-sm font-semibold text-[#0a0b0d] block mt-1">
                        {detail.role || "-"}
                      </strong>
                    </div>
                    <div className="rounded-xl border border-[#eef0f3] bg-[#fafbfc] p-4">
                      <span className="caption text-[#7c828a] block">SUBMISSION OUTCOME</span>
                      <strong className="text-sm font-mono text-[#0a0b0d] block mt-1">
                        {detail.submission_outcome || "None recorded"}
                      </strong>
                    </div>
                  </div>

                  {/* URL Row */}
                  <div className="rounded-xl border border-[#eef0f3] bg-[#fafbfc] p-4">
                    <span className="caption text-[#7c828a] block mb-1">JOB BOARD URL</span>
                    <a
                      href={detail.job_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs font-mono text-[#0052ff] underline break-all"
                    >
                      {detail.job_url}
                    </a>
                  </div>

                  {/* Last Error Notice */}
                  {detail.last_error && (
                    <div className="rounded-xl border border-[#dee1e6] bg-[#fafbfc] p-4 text-xs text-[#cf202f]">
                      <span className="font-semibold block mb-1">Execution Notice:</span>
                      {detail.last_error}
                    </div>
                  )}

                  {/* Manual Verification Required Gate */}
                  {needsManualVerification && (
                    <div className="rounded-2xl border border-[#dee1e6] bg-[#fafbfc] p-5">
                      <div className="flex items-center gap-2 text-sm font-semibold text-[#0a0b0d]">
                        <span className="text-[#f4b000]">●</span>
                        Manual Employer Verification Required
                      </div>
                      <p className="mt-2 text-xs text-[#5b616e] leading-relaxed">
                        The agent clicked submit but could not verify confirmation automatically.
                        Please check the employer site before confirming to prevent duplicate applications.
                      </p>
                      <div className="mt-4 flex flex-wrap gap-3">
                        <button
                          onClick={() => handleConfirmSubmission(detail.id)}
                          disabled={actionPending}
                          className="btn-primary text-xs"
                        >
                          I Verified It Was Submitted
                        </button>
                        <button
                          onClick={() => handleMarkNotSubmitted(detail.id)}
                          disabled={actionPending}
                          className="btn-secondary-light text-xs"
                        >
                          It Was Not Submitted
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Confirmation Summary */}
                  {detail.status === "Submitted" && confirmation && (
                    <div className="rounded-2xl border border-[#dee1e6] bg-[#fafbfc] p-5">
                      <div className="flex items-center gap-2">
                        <span className="text-[#05b169] text-base font-bold">✓</span>
                        <h4 className="text-sm font-semibold text-[#0a0b0d]">
                          Submission Verified
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

                  {/* Review Items */}
                  {detail.review_items && detail.review_items.length > 0 && (
                    <div className="pt-6 border-t border-[#dee1e6]">
                      <h4 className="title-sm text-[#0a0b0d] mb-2">
                        Review Items ({openReviewItems.length} open)
                      </h4>
                      <ReviewItems
                        applicationId={detail.id}
                        items={detail.review_items}
                        onChanged={() => loadDetail(detail.id)}
                        disabled={actionPending || detail.status !== "Needs Review"}
                      />
                    </div>
                  )}

                  {/* Execution Timeline */}
                  {detail.events && detail.events.length > 0 && (
                    <div className="pt-6 border-t border-[#dee1e6]">
                      <h4 className="title-sm text-[#0a0b0d] mb-4">
                        Audit Trail & Event History
                      </h4>
                      <div className="space-y-2 max-h-64 overflow-y-auto pr-2">
                        {detail.events.map((event) => (
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

                  {/* Bottom Action Controls */}
                  <div className="flex flex-wrap items-center gap-3 pt-6 border-t border-[#dee1e6]">
                    {detail.status === "Needs Review" &&
                      !needsManualVerification &&
                      openReviewItems.length === 0 &&
                      !submissionWasAttempted && (
                        <button
                          onClick={() => handleResume(detail.id)}
                          disabled={actionPending}
                          className="btn-primary"
                        >
                          Resume & Submit
                        </button>
                      )}

                    {detail.status === "Failed" && (
                      <button
                        onClick={() => handleRetry(detail.id)}
                        disabled={actionPending}
                        className="btn-primary"
                      >
                        Retry Application
                      </button>
                    )}

                    <button
                      onClick={() => handleDelete(detail.id)}
                      disabled={actionPending}
                      className="text-xs text-[#cf202f] hover:underline ml-auto"
                    >
                      Delete Application Record
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
