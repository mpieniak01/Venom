"use client";

import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Command, Brain, BugPlay, Target, Sparkles, Shield } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  setAutonomy,
  setCostMode,
  useAutonomyLevel,
  useCostMode,
} from "@/hooks/use-api";
import { SystemStatusPanel } from "./system-status-panel";

export const navItems = [
  { href: "/", label: "Cockpit", icon: Command },
  { href: "/brain", label: "Brain", icon: Brain },
  { href: "/inspector", label: "Inspector", icon: BugPlay },
  { href: "/strategy", label: "Strategy", icon: Target },
];

const AUTONOMY_LEVELS = [0, 10, 20, 30, 40];
const AUTONOMY_LABELS: Record<number, string> = {
  0: "Boot",
  10: "Monitor",
  20: "Assistant",
  30: "Hybrid",
  40: "Full",
};
const AUTONOMY_DETAILS: Record<number, { name: string; risk: string; description: string }> = {
  0: { name: "ISOLATED", risk: "zero", description: "Lokalny odczyt bez dostępu do sieci." },
  10: { name: "CONNECTED", risk: "low", description: "Dostęp do internetu i darmowych API." },
  20: { name: "FUNDED", risk: "medium", description: "Włączone płatne API / SOTA modele." },
  30: { name: "BUILDER", risk: "high", description: "Prawo zapisu w repozytorium i refaktorów." },
  40: { name: "ROOT", risk: "critical", description: "Pełny dostęp do shell/Dockera." },
};

type AutonomySnapshot = {
  level: number;
  name: string;
  risk: string;
  description: string;
};

export function Sidebar() {
  const pathname = usePathname();
  const { data: costMode, refresh: refreshCost } = useCostMode(15000);
  const { data: autonomy, refresh: refreshAutonomy } = useAutonomyLevel(20000);
  const [costLoading, setCostLoading] = useState(false);
  const [autonomyLoading, setAutonomyLoading] = useState<number | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [selectedAutonomy, setSelectedAutonomy] = useState<string>("");
  const [localAutonomy, setLocalAutonomy] = useState<AutonomySnapshot | null>(null);

  const resolveAutonomyDetails = (level: number | null) => {
    if (level === null || level === undefined) return null;
    const details = AUTONOMY_DETAILS[level];
    if (!details) return null;
    return { level, ...details };
  };

  const autonomyInfo = useMemo(() => {
    if (autonomy) {
      return {
        level: autonomy.current_level,
        name: autonomy.current_level_name,
        risk: autonomy.risk_level,
        description: autonomy.description,
      };
    }
    if (localAutonomy) return localAutonomy;
    const fallbackLevel = selectedAutonomy ? Number(selectedAutonomy) : null;
    return (
      resolveAutonomyDetails(fallbackLevel) ?? {
        level: null,
        name: "Brak danych",
        risk: "n/a",
        description: "AutonomyGate offline.",
      }
    );
  }, [autonomy, localAutonomy, selectedAutonomy]);

  const handleCostToggle = async () => {
    setCostLoading(true);
    setStatusMessage(null);
    try {
      await setCostMode(!(costMode?.enabled ?? false));
      refreshCost();
      setStatusMessage(`Przełączono tryb na ${costMode?.enabled ? "Eco" : "Paid (Pro)"}.`);
    } catch (error) {
      setStatusMessage(
        error instanceof Error ? error.message : "Nie udało się przełączyć trybu kosztów.",
      );
    } finally {
      setCostLoading(false);
    }
  };

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem("sidebar-autonomy");
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as AutonomySnapshot;
        setLocalAutonomy(parsed);
        setSelectedAutonomy(String(parsed.level));
      } catch {
        // ignore corrupted storage
      }
    }
  }, []);

  useEffect(() => {
    if (!autonomy) return;
    const snapshot: AutonomySnapshot = {
      level: autonomy.current_level,
      name: autonomy.current_level_name,
      risk: autonomy.risk_level,
      description: autonomy.description ?? AUTONOMY_DETAILS[autonomy.current_level]?.description ?? "AutonomyGate",
    };
    setLocalAutonomy(snapshot);
    setSelectedAutonomy(String(autonomy.current_level));
    if (typeof window !== "undefined") {
      window.localStorage.setItem("sidebar-autonomy", JSON.stringify(snapshot));
    }
  }, [autonomy]);

  const handleAutonomyChange = async (level: number) => {
    if (autonomy?.current_level === level) return;
    setAutonomyLoading(level);
    setStatusMessage(null);
    try {
      await setAutonomy(level);
      refreshAutonomy();
      setStatusMessage(`Ustawiono poziom autonomii ${level}.`);
    } catch (error) {
      const fallback = resolveAutonomyDetails(level);
      if (fallback) {
        setLocalAutonomy(fallback);
        if (typeof window !== "undefined") {
          window.localStorage.setItem("sidebar-autonomy", JSON.stringify(fallback));
        }
      }
      setStatusMessage(
        error instanceof Error
          ? error.message
          : "Nie udało się zmienić poziomu autonomii (tryb offline).",
      );
    } finally {
      setAutonomyLoading(null);
    }
  };

  return (
    <aside className="glass-panel fixed inset-y-0 left-0 z-40 hidden w-72 flex-col border-r border-white/5 bg-black/25 px-6 py-6 text-zinc-100 shadow-card lg:flex">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-400/60 to-cyan-400/60 text-xl shadow-neon">
            🕷️
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">Venom</p>
            <p className="text-lg font-semibold tracking-[0.1em] text-white">Command Center</p>
          </div>
        </div>
        <span className="rounded-full border border-white/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.3em] text-zinc-400">
          v2.4.1
        </span>
      </div>
      <nav className="mt-8 space-y-5">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">Modules</p>
          <div className="mt-3 space-y-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href;
              return (
                <a
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-2xl border px-3 py-2 text-sm font-medium transition pointer-events-auto",
                    active
                      ? "border-emerald-300/60 bg-gradient-to-r from-emerald-500/10 to-transparent text-emerald-200 shadow-neon"
                      : "border-white/10 bg-black/30 text-white hover:border-white/30 hover:bg-white/5",
                    "cursor-pointer",
                  )}
                  aria-current={active ? "page" : undefined}
                >
                  <Icon className={cn("h-4 w-4", active ? "text-emerald-300" : "text-zinc-400")} />
                  <span>{item.label}</span>
                </a>
              );
            })}
          </div>
        </div>
      </nav>
      <div className="mt-auto space-y-5">
        <SystemStatusPanel />

        <section
          className="rounded-2xl border border-white/10 bg-gradient-to-b from-emerald-500/5 to-transparent p-4 text-sm text-zinc-100"
          data-testid="sidebar-cost-mode"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">Cost Mode</p>
              <p className="text-lg font-semibold text-white">
                {costMode?.enabled ? "Paid (Pro)" : "Eco"}
              </p>
              <p className="text-xs text-zinc-400">
                Provider: {costMode?.provider ?? "n/a"}
              </p>
            </div>
            <Sparkles className="h-5 w-5 text-emerald-200" />
          </div>
          <Button
            className="mt-3 w-full justify-center"
            size="sm"
            variant={costMode?.enabled ? "warning" : "secondary"}
            disabled={costLoading}
            onClick={handleCostToggle}
          >
            {costLoading ? "Przełączam..." : `Przełącz na ${costMode?.enabled ? "Eco" : "Paid"}`}
          </Button>
        </section>

        <section
          className="rounded-2xl border border-white/10 bg-gradient-to-b from-violet-500/5 to-transparent p-4 text-sm text-zinc-100"
          data-testid="sidebar-autonomy"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">Autonomy</p>
              <p className="text-lg font-semibold text-white">{autonomyInfo.name}</p>
              <p className="text-xs text-zinc-400">
                Poziom {autonomyInfo.level ?? "n/a"} • {autonomyInfo.risk}
              </p>
            </div>
            <Shield className="h-5 w-5 text-violet-200" />
          </div>
          <div className="mt-3">
            <label className="text-xs text-zinc-500" htmlFor="autonomy-select">
              Wybierz poziom autonomii
            </label>
            <select
              id="autonomy-select"
              data-testid="sidebar-autonomy-select"
              className="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-violet-400 focus:ring-0"
              value={selectedAutonomy}
              onChange={async (event) => {
                const value = event.target.value;
                setSelectedAutonomy(value);
                if (value) {
                  await handleAutonomyChange(Number(value));
                }
              }}
              disabled={autonomyLoading !== null}
            >
              <option value="" disabled>
                {autonomyInfo.level === null ? "Brak danych" : "Wybierz poziom"}
              </option>
              {AUTONOMY_LEVELS.map((level) => {
                const label = AUTONOMY_LABELS[level] ?? `Poziom ${level}`;
                return (
                  <option key={level} value={level}>
                    {label}
                  </option>
                );
              })}
            </select>
          </div>
          <p className="mt-3 text-xs text-zinc-400">{autonomyInfo.description}</p>
        </section>

        {statusMessage && (
          <p className="text-xs text-emerald-300" data-testid="sidebar-status-message">
            {statusMessage}
          </p>
        )}
      </div>
    </aside>
  );
}
