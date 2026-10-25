"use client";

import { useRef } from "react";

export default function FilePicker({
  accept,
  buttonLabel,
  selectedName,
  helpText,
  disabled = false,
  onSelect,
}: {
  accept: string;
  buttonLabel: string;
  selectedName?: string;
  helpText?: string;
  disabled?: boolean;
  onSelect: (file: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        disabled={disabled}
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) onSelect(file);
        }}
      />
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={disabled}
          className="rounded border border-blue-600 bg-white px-4 py-2 text-sm font-semibold text-blue-700 transition-colors hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {buttonLabel}
        </button>
        <span
          className={`text-sm ${
            selectedName ? "font-medium text-gray-800" : "text-gray-500"
          }`}
        >
          {selectedName ? `Selected: ${selectedName}` : "No file selected"}
        </span>
      </div>
      {helpText && <p className="mt-2 text-xs text-gray-500">{helpText}</p>}
    </div>
  );
}
