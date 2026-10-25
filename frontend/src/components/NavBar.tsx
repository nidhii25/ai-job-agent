"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";
import type { HealthStatus } from "@/lib/api";

const links = [
  { href: "/apply", label: "Apply" },
  { href: "/applications", label: "All Applications" },
  { href: "/profile", label: "My Profile" },
];

export default function NavBar() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [health, setHealth] = useState<HealthStatus | null>(null);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  return (
    <header className="sticky top-0 z-50 h-16 w-full border-b border-[#dee1e6] bg-white/95 backdrop-blur-md">
      <div className="content-container flex h-full items-center justify-between">
        {/* Brand Link & Wordmark */}
        <div className="flex items-center gap-8">
          <Link href="/apply" className="flex items-center gap-2.5 text-[#0a0b0d] hover:opacity-90 transition-opacity">
            <span className="grid h-8 w-8 place-items-center rounded-full bg-[#0052ff] text-white font-bold text-sm tracking-tight shadow-sm">
              A
            </span>
            <div className="flex flex-col">
              <span className="text-[15px] font-semibold tracking-tight text-[#0a0b0d] leading-none">
                Application Agent
              </span>
              <span className="text-[10px] uppercase font-bold tracking-widest text-[#7c828a] mt-0.5">
                Local Assistant
              </span>
            </div>
          </Link>

          {/* Desktop Navigation Links */}
          <nav className="hidden md:flex items-center gap-1.5" aria-label="Main Navigation">
            {links.map((link) => {
              const active = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                    active
                      ? "bg-[#eef0f3] text-[#0a0b0d]"
                      : "text-[#5b616e] hover:bg-[#f7f7f7] hover:text-[#0a0b0d]"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Right Section: System Badge & Quick Action */}
        <div className="hidden sm:flex items-center gap-3">
          {health ? (
            <div
              className="inline-flex items-center gap-1.5 rounded-full bg-[#eef0f3] px-3 py-1.5 text-xs font-medium text-[#0a0b0d]"
              title={`Provider: ${health.ai_provider} (${health.ai_model})`}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-[#05b169]" />
              <span>Core Ready</span>
              {health.ai_enabled && (
                <span className="rounded-full bg-[#0052ff]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[#0052ff]">
                  AI Active
                </span>
              )}
            </div>
          ) : (
            <div className="inline-flex items-center gap-1.5 rounded-full bg-[#eef0f3] px-3 py-1.5 text-xs font-medium text-[#7c828a]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#a8acb3]" />
              <span>Local Agent</span>
            </div>
          )}

          <Link
            href="/apply"
            className="btn-primary text-xs !min-h-[36px] !py-1.5 !px-4"
          >
            + Start Application
          </Link>
        </div>

        {/* Mobile Menu Toggle Button */}
        <button
          type="button"
          className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-[#dee1e6] bg-white text-[#0a0b0d] md:hidden hover:bg-[#f7f7f7] transition-colors"
          aria-label={menuOpen ? "Close navigation menu" : "Open navigation menu"}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          {menuOpen ? (
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          ) : (
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          )}
        </button>
      </div>

      {/* Mobile Drawer Menu */}
      {menuOpen && (
        <div className="absolute top-16 left-0 w-full border-b border-[#dee1e6] bg-white p-4 shadow-lg md:hidden">
          <nav className="flex flex-col gap-1">
            {links.map((link) => {
              const active = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  onClick={() => setMenuOpen(false)}
                  className={`rounded-xl px-4 py-3 text-sm font-medium transition-colors ${
                    active
                      ? "bg-[#eef0f3] text-[#0a0b0d]"
                      : "text-[#5b616e] hover:bg-[#f7f7f7] hover:text-[#0a0b0d]"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
          <div className="mt-4 pt-3 border-t border-[#eef0f3] flex flex-col gap-2">
            <Link
              href="/apply"
              onClick={() => setMenuOpen(false)}
              className="btn-primary w-full text-center"
            >
              + Start Application
            </Link>
          </div>
        </div>
      )}
    </header>
  );
}
