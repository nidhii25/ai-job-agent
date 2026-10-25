"use client";

import Link from "next/link";
import { applicationsExportUrl } from "@/lib/api";

export default function Footer() {
  return (
    <footer className="footer-light mt-auto">
      <div className="content-container">
        <div className="grid grid-cols-1 gap-10 md:grid-cols-2 lg:grid-cols-5">
          {/* Brand Column */}
          <div className="lg:col-span-2">
            <div className="flex items-center gap-3">
              <span className="grid h-8 w-8 place-items-center rounded-full bg-[#0052ff] text-white font-bold text-sm tracking-tight">
                A
              </span>
              <span className="text-base font-semibold tracking-tight text-[#0a0b0d]">
                AI Job Agent
              </span>
            </div>
            <p className="mt-4 max-w-sm text-sm text-[#5b616e] leading-relaxed">
              Institutional-grade automated job application assistant designed for direct
              Greenhouse job boards. Operates with strict deterministic profile grounding
              and double-check verification.
            </p>
            <div className="mt-5 flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-[#eef0f3] px-3 py-1 text-xs font-medium text-[#0a0b0d]">
                <span className="h-1.5 w-1.5 rounded-full bg-[#05b169]" />
                Local Runtime • Privacy Safe
              </span>
            </div>
          </div>

          {/* Column 1: Workspace */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-[#0a0b0d]">
              Workspace
            </h4>
            <ul className="mt-4 space-y-2.5 text-sm">
              <li>
                <Link href="/apply" className="text-[#5b616e] hover:text-[#0052ff] transition-colors">
                  Start Application
                </Link>
              </li>
              <li>
                <Link href="/applications" className="text-[#5b616e] hover:text-[#0052ff] transition-colors">
                  All Applications
                </Link>
              </li>
              <li>
                <Link href="/profile" className="text-[#5b616e] hover:text-[#0052ff] transition-colors">
                  Candidate Profile
                </Link>
              </li>
              <li>
                <a
                  href={applicationsExportUrl()}
                  download="applications.json"
                  className="text-[#5b616e] hover:text-[#0052ff] transition-colors"
                >
                  Download JSON Ledger
                </a>
              </li>
            </ul>
          </div>

          {/* Column 2: Supported Systems */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-[#0a0b0d]">
              Integration
            </h4>
            <ul className="mt-4 space-y-2.5 text-sm">
              <li className="text-[#5b616e]">Greenhouse Job Boards</li>
              <li className="text-[#5b616e]">Playwright Chromium</li>
              <li className="text-[#5b616e]">Gemini 2.5 AI Mapping</li>
              <li className="text-[#5b616e]">SQLite Durable Storage</li>
            </ul>
          </div>

          {/* Column 3: Trust & Safety */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-[#0a0b0d]">
              Governance
            </h4>
            <ul className="mt-4 space-y-2.5 text-sm">
              <li className="text-[#5b616e]">Zero Guesswork Policy</li>
              <li className="text-[#5b616e]">Deterministic Fallback</li>
              <li className="text-[#5b616e]">Human Review Gates</li>
              <li className="text-[#5b616e]">Anti-Duplicate Lock</li>
            </ul>
          </div>
        </div>

        {/* Legal Band */}
        <div className="legal-band flex flex-col items-start justify-between gap-4 md:flex-row md:items-center">
          <p className="caption">
            © 2026 AI Job Application Agent. All processing executed locally on your machine.
          </p>
          <div className="flex items-center gap-6 text-xs text-[#7c828a]">
            <span>Coinbase Design Standard</span>
            <span>Single-Tenant Secure</span>
            <span>v1.0.0</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
