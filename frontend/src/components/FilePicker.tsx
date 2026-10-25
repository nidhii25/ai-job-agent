"use client";

import { useRef, useState } from "react";

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
  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (!disabled) setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (disabled) return;
    const file = e.dataTransfer.files?.[0];
    if (file) onSelect(file);
  };

  return (
    <div className="w-full">
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

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`relative flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 rounded-2xl border p-4 transition-all ${
          isDragging
            ? "border-[#0052ff] bg-[#f0f4ff]"
            : "border-[#dee1e6] bg-[#fafbfc] hover:border-[#a8acb3]"
        } ${disabled ? "opacity-60 cursor-not-allowed" : ""}`}
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="asset-icon-circular text-[#5b616e]">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-[#0a0b0d] truncate">
              {selectedName || "No file selected"}
            </p>
            <p className="text-xs text-[#7c828a]">
              {selectedName ? "Ready for attachment" : "Drop file here or browse"}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={disabled}
          className="btn-secondary-light !min-h-[38px] !py-2 !px-4 text-xs shrink-0 self-stretch sm:self-auto text-center"
        >
          {buttonLabel}
        </button>
      </div>

      {helpText && <p className="mt-2 text-xs text-[#7c828a] leading-relaxed">{helpText}</p>}
    </div>
  );
}
