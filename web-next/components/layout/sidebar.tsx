"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Command, Brain, BugPlay, Target, Layers } from "lucide-react";
import { cn } from "@/lib/utils";

export const navItems = [
  { href: "/", label: "Cockpit", icon: Command },
  { href: "/brain", label: "Brain", icon: Brain },
  { href: "/inspector", label: "Inspector", icon: BugPlay },
  { href: "/strategy", label: "Strategy", icon: Target },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="glass-panel fixed inset-y-0 left-0 z-40 hidden w-64 flex-col border-r border-white/5 bg-black/20 px-5 py-6 text-zinc-100 shadow-neon lg:flex">
      <div className="flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-600/70 to-indigo-600/70 text-2xl shadow-neon">
          🕷️
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">
            Venom
          </p>
          <p className="text-lg font-semibold tracking-wide">Command</p>
        </div>
      </div>
      <nav className="mt-8 space-y-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition",
                active
                  ? "bg-gradient-to-r from-violet-600/30 to-indigo-600/30 text-white shadow-neon"
                  : "text-zinc-400 hover:bg-white/5 hover:text-white",
              )}
            >
              <Icon className={cn("h-4 w-4", active && "text-violet-200")} />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto rounded-2xl border border-white/5 bg-white/5 p-4">
        <p className="text-xs uppercase tracking-[0.25em] text-zinc-500">
          SYSTEM STATUS
        </p>
        <div className="mt-2 flex items-center gap-2 text-sm">
          <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          Core services synced
        </div>
        <div className="mt-3 flex items-center gap-2 text-xs text-zinc-500">
          <Layers className="h-4 w-4 text-zinc-400" />
          Next.js + FastAPI
        </div>
      </div>
    </aside>
  );
}
