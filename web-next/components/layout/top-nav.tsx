"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Cockpit" },
  { href: "/flow", label: "Flow" },
  { href: "/brain", label: "Brain" },
  { href: "/strategy", label: "Strategy" },
];

export function TopNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-30 border-b border-[--color-border] bg-[--color-background]/85 backdrop-blur">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
        <Link href="/" className="flex items-center gap-3 font-semibold">
          <span className="text-xl">🕷️ Venom</span>
          <span className="rounded-full bg-[--color-panel] px-3 py-1 text-xs text-[--color-muted]">
            Next Cockpit
          </span>
        </Link>
        <nav className="flex items-center gap-2">
          {links.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`rounded-full px-4 py-2 text-sm transition ${
                  active
                    ? "bg-[--color-panel] text-white shadow-lg shadow-purple-900/30"
                    : "text-[--color-muted] hover:bg-[--color-panel] hover:text-white"
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
