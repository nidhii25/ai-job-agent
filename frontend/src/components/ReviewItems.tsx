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
      <p className="mt-2 text-sm text-gray-500">
        No review items for this application.
      </p>
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
    <div className="mt-2">
      {error && (
        <p className="mb-2 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
          {error}
        </p>
      )}
      <ul className="space-y-2 text-sm text-gray-700">
        {items.map((item) => {
          const fileRelated = /resume|cover letter|file/i.test(
            `${item.field_name} ${item.reason}`
          );
          return (
            <li
              key={item.id}
              className="rounded border border-gray-200 bg-white p-3"
            >
              <p className="font-medium">{item.field_name}</p>
              <p className="text-gray-600">{item.reason}</p>
              {item.suggested_value && (
                <p className="text-gray-500">
                  Suggested: {item.suggested_value}
                </p>
              )}

              {item.resolved_at ? (
                <p className="mt-2 text-xs text-green-700">
                  Resolved: {item.user_resolution}
                </p>
              ) : (
                <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                  <input
                    value={drafts[item.id] ?? item.suggested_value ?? ""}
                    onChange={(event) =>
                      setDrafts((current) => ({
                        ...current,
                        [item.id]: event.target.value,
                      }))
                    }
                    placeholder="Type your answer"
                    disabled={disabled || pendingId === item.id}
                    className="min-w-0 flex-1 rounded border border-gray-300 px-3 py-2 text-gray-800 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <button
                    onClick={() => save(item)}
                    disabled={disabled || pendingId === item.id}
                    className="rounded bg-yellow-500 px-3 py-2 text-sm font-semibold text-white hover:bg-yellow-600 disabled:bg-yellow-300"
                  >
                    {pendingId === item.id ? "Saving..." : "Save answer"}
                  </button>
                </div>
              )}

              {!item.resolved_at && fileRelated && (
                <p className="mt-2 text-xs text-gray-500">
                  If this is about a file, upload the file on{" "}
                  <a href="/profile" className="underline">
                    My Profile
                  </a>{" "}
                  or above, then save a short note here.
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
