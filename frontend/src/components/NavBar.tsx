"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/apply", label: "Apply" },
  { href: "/applications", label: "All Applications" },
  { href: "/profile", label: "My Profile" },
];

export default function NavBar() {
  const pathname = usePathname();

  return (
    <header className="border-b border-gray-200 bg-white">
      <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-4">
        <Link href="/apply" className="text-sm font-semibold text-gray-900">
          AI Job Application Agent
        </Link>
        <nav className="flex gap-1">
          {links.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`rounded px-3 py-1.5 text-sm font-medium transition-colors ${
                  active
                    ? "bg-blue-600 text-white"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
