"use client";

import { useState } from "react";
import { ApiError, resolveReviewItem } from "@/lib/api";
import type { ReviewItem } from "@/lib/api";

function errorMessage(error: unknown): string {
  return error instanceof ApiError || error instanceof Error
    ? error.message
    : String(error);
}

interface ReviewItemsProps {
  applicationId: number;
  items: ReviewItem[];
  onChanged: () => Promise<void> | void;
  disabled?: boolean;
}

export default function ReviewItems({
  applicationId,
  items,
  onChanged,
  disabled = false,
}: ReviewItemsProps) {
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (items.length === 0) {
    return (
      <div className="rounded-2xl border border-[#dee1e6] bg-[#f7f7f7] p-6 text-center text-sm text-[#5b616e]">
        No review items for this application. All required fields are grounded.
      </div>
    );
  }

  const save = async (item: ReviewItem) => {
    const resolution = (drafts[item.id] ?? item.suggested_value ?? "").trim();
    if (!resolution) {
      setError(`Enter an answer for “${item.field_name}”.`);
      return;
    }

    setPendingId(item.id);
    setError(null);
    try {
      await resolveReviewItem(applicationId, item.id, resolution);
      setDrafts((current) => {
        const next = { ...current };
        delete next[item.id];
        return next;
      });
      await onChanged();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPendingId(null);
    }
  };

  return (
    <div className="mt-4 space-y-4">
      {error && (
        <div className="rounded-xl border border-[#dee1e6] bg-[#fafbfc] p-3.5 text-sm text-[#cf202f]">
          {error}
        </div>
      )}

      <ul className="space-y-3">
        {items.map((item) => {
          const fileRelated = /resume|cover letter|file/i.test(
            `${item.field_name} ${item.reason}`
          );
          const isResolved = Boolean(item.resolved_at);

          return (
            <li
              key={item.id}
              className={`rounded-2xl border p-5 transition-all ${
                isResolved
                  ? "border-[#dee1e6] bg-[#fafbfc]"
                  : "border-[#dee1e6] bg-white shadow-sm"
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-base font-semibold text-[#0a0b0d]">
                  {item.field_name}
                </span>
                {isResolved ? (
                  <span className="status-pill-submitted text-xs">
                    <span className="h-1.5 w-1.5 rounded-full bg-[#05b169]" />
                    Resolved
                  </span>
                ) : (
                  <span className="status-pill-review text-xs">
                    <span className="h-1.5 w-1.5 rounded-full bg-[#f4b000]" />
                    Action Required
                  </span>
                )}
              </div>

              <p className="mt-2 text-sm text-[#5b616e] leading-relaxed">
                {item.reason}
              </p>

              {item.suggested_value && (
                <div className="mt-3 rounded-xl border border-[#eef0f3] bg-[#f7f7f7] p-3 text-xs">
                  <span className="font-semibold uppercase tracking-wider text-[#7c828a] block mb-1">
                    Suggested Value
                  </span>
                  <span className="font-mono text-[#0a0b0d] text-sm break-all">
                    {item.suggested_value}
                  </span>
                </div>
              )}

              {isResolved ? (
                <div className="mt-3.5 flex items-center gap-2 rounded-xl bg-[#eef0f3]/60 px-3.5 py-2.5 text-xs text-[#0a0b0d]">
                  <span className="font-semibold text-[#05b169]">✓</span>
                  <span className="font-medium text-[#5b616e]">Saved Answer:</span>
                  <span className="font-semibold">{item.user_resolution}</span>
                </div>
              ) : (
                <div className="mt-4 flex flex-col gap-2.5 sm:flex-row">
                  <input
                    value={drafts[item.id] ?? item.suggested_value ?? ""}
                    onChange={(event) =>
                      setDrafts((current) => ({
                        ...current,
                        [item.id]: event.target.value,
                      }))
                    }
                    placeholder="Type your approved answer"
                    disabled={disabled || pendingId === item.id}
                    className="text-input flex-1"
                  />
                  <button
                    onClick={() => save(item)}
                    disabled={disabled || pendingId === item.id}
                    className="btn-primary shrink-0"
                  >
                    {pendingId === item.id ? "Saving..." : "Save Answer"}
                  </button>
                </div>
              )}

              {!isResolved && fileRelated && (
                <p className="mt-2.5 text-xs text-[#7c828a]">
                  If this requires a document, attach it in Candidate Profile or the section above,
                  then enter a brief confirmation note here.
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
