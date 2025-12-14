"use client";

import { useState } from "react";
import { Menu, Layers } from "lucide-react";
import Link from "next/link";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { navItems } from "./sidebar";

export function MobileNav() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        className="flex items-center gap-2 rounded-full border border-white/10 px-3 py-2 text-sm text-white transition hover:bg-white/5 lg:hidden"
        onClick={() => setOpen(true)}
        aria-label="Otwórz nawigację"
      >
        <Menu className="h-4 w-4" />
        Menu
      </button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="flex h-full max-w-sm flex-col border-r border-white/10 bg-zinc-950/95 text-white">
          <SheetHeader>
            <SheetTitle>Venom Command</SheetTitle>
            <SheetDescription>
              Szybka nawigacja między Cockpit, Brain, Inspector oraz Strategy.
            </SheetDescription>
          </SheetHeader>
          <nav className="mt-6 space-y-2 text-sm">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="flex items-center gap-3 rounded-2xl border border-white/5 bg-white/5 px-4 py-3 text-white transition hover:border-violet-500/40 hover:bg-violet-500/10"
                onClick={() => setOpen(false)}
              >
                <item.icon className="h-4 w-4 text-violet-200" />
                <div>
                  <p className="font-semibold">{item.label}</p>
                  <p className="text-xs text-zinc-400">/ {item.href === "/" ? "cockpit" : item.label.toLowerCase()}</p>
                </div>
              </Link>
            ))}
          </nav>
          <div className="mt-auto rounded-2xl border border-white/10 bg-black/40 p-4 text-sm text-zinc-300">
            <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
              System
            </p>
            <div className="mt-2 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              Core services synced
            </div>
            <div className="mt-3 flex items-center gap-2 text-xs text-zinc-500">
              <Layers className="h-4 w-4" />
              Next.js + FastAPI
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
