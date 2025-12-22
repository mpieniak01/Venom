"use client";

import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  Command,
  Brain,
  BugPlay,
  Target,
  Sparkles,
  Shield,
  Gauge,
  Settings,
  Calendar,
  Layers,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  setAutonomy,
  setCostMode,
  useAutonomyLevel,
  useCostMode,
} from "@/hooks/use-api";
import { SystemStatusPanel } from "./system-status-panel";
import { useTranslation } from "@/lib/i18n";

export const navItems = [
  { href: "/", label: "Kokpit", labelKey: "sidebar.nav.cockpit", icon: Command },
  { href: "/brain", label: "Graf wiedzy", labelKey: "sidebar.nav.brain", icon: Brain },
  { href: "/inspector", label: "Inspektor", labelKey: "sidebar.nav.inspector", icon: BugPlay },
  { href: "/strategy", label: "Strategia", labelKey: "sidebar.nav.strategy", icon: Target },
  { href: "/models", label: "Przeglad modeli", labelKey: "sidebar.nav.models", icon: Layers },
  { href: "/calendar", label: "Kalendarz", labelKey: "sidebar.nav.calendar", icon: Calendar },
  { href: "/benchmark", label: "Benchmark", labelKey: "sidebar.nav.benchmark", icon: Gauge },
  { href: "/config", label: "Konfiguracja", labelKey: "sidebar.nav.config", icon: Settings },
];

const AUTONOMY_LEVELS = [0, 10, 20, 30, 40];
const AUTONOMY_LABELS: Record<number, string> = {
  0: "Start",
  10: "Monitor",
  20: "Asystent",
  30: "Hybryda",
  40: "Pełny",
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
  const t = useTranslation();

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
    const targetState = !(costMode?.enabled ?? false);
    if (
      targetState &&
      typeof window !== "undefined" &&
      !window.confirm(
        "Tryb Paid (Pro) wykorzysta płatne API i zasoby. Czy chcesz kontynuować?",
      )
    ) {
      setStatusMessage("Anulowano przełączenie trybu kosztów.");
      return;
    }
    setCostLoading(true);
    setStatusMessage(null);
    try {
      await setCostMode(targetState);
      refreshCost();
      setStatusMessage(`Przełączono tryb na ${targetState ? "Pro (płatny)" : "Eco"}.`);
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
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-xl">
            🐍
          </div>
          <div>
            <p className="eyebrow">
              {t("sidebar.brand.caption")}
            </p>
            <p className="text-lg font-semibold tracking-[0.1em] text-white">
              {t("sidebar.brand.title")}
            </p>
          </div>
        </div>
        <span className="pill-badge">v2.4.1</span>
      </div>
      <nav className="mt-8 space-y-5">
        <div>
          <p className="eyebrow">
            {t("sidebar.modulesTitle")}
          </p>
          <div className="mt-3 space-y-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href;
              const label = item.labelKey ? t(item.labelKey) : item.label;
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
                  <span>{label}</span>
                </a>
              );
            })}
          </div>
        </div>
      </nav>
      <div className="mt-auto space-y-5">
        <SystemStatusPanel />

        <section
          className="rounded-2xl card-shell bg-gradient-to-b from-emerald-500/5 to-transparent p-4 text-sm"
          data-testid="sidebar-cost-mode"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="eyebrow">
                {t("sidebar.cost.title")}
              </p>
              <p className="text-lg font-semibold text-white">
                {costMode?.enabled ? t("sidebar.cost.pro") : t("sidebar.cost.eco")}
              </p>
              <p className="text-xs text-zinc-400">
                {t("common.provider")}: {costMode?.provider ?? "brak"}
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
            {costLoading
              ? t("sidebar.cost.switching")
              : costMode?.enabled
                ? t("sidebar.cost.switchToEco")
                : t("sidebar.cost.switchToPro")}
          </Button>
        </section>

        <section
          className="rounded-2xl card-shell bg-gradient-to-b from-violet-500/5 to-transparent p-4 text-sm"
          data-testid="sidebar-autonomy"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="eyebrow">
                {t("sidebar.autonomy.title")}
              </p>
              <p className="text-lg font-semibold text-white">{autonomyInfo.name}</p>
              <p className="text-xs text-zinc-400">
                Poziom {autonomyInfo.level ?? "brak"} • {autonomyInfo.risk}
              </p>
            </div>
            <Shield className="h-5 w-5 text-violet-200" />
          </div>
          <div className="mt-3">
            <label className="text-xs text-zinc-500" htmlFor="autonomy-select">
              {t("sidebar.autonomy.selectLabel")}
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
