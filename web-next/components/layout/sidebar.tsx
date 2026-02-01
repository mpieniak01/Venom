"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState, useCallback } from "react";
import {
  Command,
  Brain,
  BugPlay,
  Sparkles,
  Shield,
  Gauge,
  Settings,
  Calendar,
  Layers,
  PanelLeftClose,
  PanelLeftOpen,
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
import { AuthorSignature } from "./author-signature";
import { useTranslation } from "@/lib/i18n";

export const navItems = [
  { href: "/", label: "Kokpit", labelKey: "sidebar.nav.cockpit", icon: Command },
  { href: "/inspector", label: "Inspektor", labelKey: "sidebar.nav.inspector", icon: BugPlay },
  { href: "/brain", label: "Graf wiedzy", labelKey: "sidebar.nav.brain", icon: Brain },
  // { href: "/strategy", label: "Strategia", labelKey: "sidebar.nav.strategy", icon: Target }, // Postponed to v2.0
  { href: "/models", label: "Przeglad modeli", labelKey: "sidebar.nav.models", icon: Layers },
  { href: "/calendar", label: "Kalendarz", labelKey: "sidebar.nav.calendar", icon: Calendar },
  { href: "/benchmark", label: "Benchmark", labelKey: "sidebar.nav.benchmark", icon: Gauge },
  { href: "/config", label: "Konfiguracja", labelKey: "sidebar.nav.config", icon: Settings },
];

const getAutonomyDetails = (level: number) => {
  const detailsMap: Record<number, { name: string; riskKey: string; descriptionKey: string }> = {
    0: { name: "ISOLATED", riskKey: "zero", descriptionKey: "0" },
    10: { name: "CONNECTED", riskKey: "low", descriptionKey: "10" },
    20: { name: "FUNDED", riskKey: "medium", descriptionKey: "20" },
    30: { name: "BUILDER", riskKey: "high", descriptionKey: "30" },
    40: { name: "ROOT", riskKey: "critical", descriptionKey: "40" },
  };
  return detailsMap[level];
};

const AUTONOMY_LEVELS = [0, 10, 20, 30, 40];


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
  const [collapsed, setCollapsed] = useState(false);
  const [isSynced, setIsSynced] = useState(false);
  const t = useTranslation();

  const resolveAutonomyDetails = useCallback(
    (level: number | null) => {
      if (level === null || level === undefined) return null;
      const details = getAutonomyDetails(level);
      if (!details) return null;
      return {
        level,
        name: details.name,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        risk: t(`sidebar.autonomy.risks.${details.riskKey}` as any),
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        description: t(`sidebar.autonomy.descriptions.${details.descriptionKey}` as any),
      };
    },
    [t],
  );

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
        name: t("sidebar.autonomy.noData"),
        risk: "n/a",
        description: t("sidebar.autonomy.offline"),
      }
    );
  }, [autonomy, localAutonomy, selectedAutonomy, t, resolveAutonomyDetails]);

  const handleCostToggle = async () => {
    const targetState = !(costMode?.enabled ?? false);
    if (
      targetState &&
      typeof window !== "undefined" &&
      !window.confirm(t("sidebar.messages.costConfirm"))
    ) {
      setStatusMessage(t("sidebar.messages.costCancelled"));
      return;
    }
    setCostLoading(true);
    setStatusMessage(null);
    try {
      await setCostMode(targetState);
      refreshCost();
      setStatusMessage(
        t("sidebar.messages.costSuccess", {
          mode: targetState ? t("sidebar.cost.pro") : t("sidebar.cost.eco"),
        }),
      );
    } catch (error) {
      setStatusMessage(
        error instanceof Error ? error.message : t("sidebar.messages.costError"),
      );
    } finally {
      setCostLoading(false);
    }
  };

  useEffect(() => {
    if (typeof window === "undefined") return;
    const storedCollapsed = window.localStorage.getItem("sidebar-collapsed");
    if (storedCollapsed) {
      setCollapsed(storedCollapsed === "true");
    }
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
    // Enable transitions after initial state sync
    const timer = setTimeout(() => setIsSynced(true), 100);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("sidebar-collapsed", String(collapsed));
    const root = document.documentElement;
    if (!root) return;
    const styles = getComputedStyle(root);
    const expandedWidth =
      styles.getPropertyValue("--sidebar-width-expanded").trim() || "18rem";
    const collapsedWidth =
      styles.getPropertyValue("--sidebar-width-collapsed").trim() || "6rem";
    root.style.setProperty(
      "--sidebar-width",
      collapsed ? collapsedWidth : expandedWidth,
    );
  }, [collapsed]);

  useEffect(() => {
    if (!autonomy) return;
    const detailsComp = resolveAutonomyDetails(autonomy.current_level);
    const snapshot: AutonomySnapshot = {
      level: autonomy.current_level,
      name: autonomy.current_level_name,
      risk: autonomy.risk_level,
      description:
        autonomy.description ?? detailsComp?.description ?? "AutonomyGate",
    };
    setLocalAutonomy(snapshot);
    setSelectedAutonomy(String(autonomy.current_level));
    if (typeof window !== "undefined") {
      window.localStorage.setItem("sidebar-autonomy", JSON.stringify(snapshot));
    }
  }, [autonomy, resolveAutonomyDetails]);

  const handleAutonomyChange = async (level: number) => {
    if (autonomy?.current_level === level) return;
    setAutonomyLoading(level);
    setStatusMessage(null);
    try {
      await setAutonomy(level);
      refreshAutonomy();
      setStatusMessage(t("sidebar.messages.autonomySuccess", { level }));
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
          : t("sidebar.messages.autonomyError"),
      );
    } finally {
      setAutonomyLoading(null);
    }
  };

  return (
    <aside
      className={cn(
        "glass-panel fixed inset-y-0 left-0 z-40 hidden flex-col border-r border-white/5 bg-black/25 py-6 text-zinc-100 shadow-card lg:flex overflow-y-auto overflow-x-hidden",
        isSynced && "transition-all duration-300 ease-in-out",
        collapsed ? "w-24 px-3" : "w-72 px-5",
      )}
      data-testid="sidebar"
    >
      <div className="flex flex-col gap-6">
        <div className={cn("flex items-center", collapsed ? "justify-center" : "justify-between")}>
          <div className="flex items-center">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-xl">
              🐍
            </div>
            <div className={cn(isSynced && "transition-all duration-300 ease-in-out", collapsed ? "max-w-0 opacity-0 overflow-hidden" : "max-w-[200px] opacity-100 ml-3")}>
              <div className="flex items-center gap-2 whitespace-nowrap">
                <p className="eyebrow">
                  {t("sidebar.brand.caption")}
                </p>
                <span className="pill-badge">v1.0</span>
              </div>
            </div>
          </div>
          <div className={cn(isSynced && "transition-all duration-300", collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100 w-auto")}>
            <button
              type="button"
              aria-label={collapsed ? t("sidebar.expand") : t("sidebar.collapse")}
              className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/20 bg-black/80 text-white shadow-card transition hover:border-white/40 hover:bg-white/10"
              onClick={() => setCollapsed((prev) => !prev)}
              data-testid="sidebar-toggle"
            >
              <PanelLeftClose className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className={cn("flex justify-center", isSynced && "transition-all duration-300", collapsed ? "max-h-12 opacity-100" : "max-h-0 opacity-0 overflow-hidden")}>
          <button
            type="button"
            aria-label={t("sidebar.expand")}
            className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/20 bg-black/80 text-white shadow-card transition hover:border-white/40 hover:bg-white/10"
            onClick={() => setCollapsed(false)}
          >
            <PanelLeftOpen className="h-4 w-4" />
          </button>
        </div>
      </div>
      <nav className="mt-8 space-y-5">
        <div>
          <div className={cn(isSynced && "transition-all duration-300 ease-in-out", collapsed ? "opacity-0 max-h-0 overflow-hidden" : "opacity-100 max-h-12 mb-3")}>
            <p className="eyebrow">
              {t("sidebar.modulesTitle")}
            </p>
          </div>
          <div className="mt-3 space-y-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href;
              const label = item.labelKey ? t(item.labelKey) : item.label;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  title={label}
                  aria-label={label}
                  className={cn(
                    "flex w-full items-center rounded-2xl border text-sm font-medium pointer-events-auto",
                    isSynced && "transition-all duration-300 ease-in-out",
                    collapsed ? "justify-center px-0 py-3" : "px-4 py-2",
                    active
                      ? "border-emerald-300/60 bg-gradient-to-r from-emerald-500/10 to-transparent text-emerald-200 shadow-neon"
                      : "border-white/10 bg-black/30 text-white hover:border-white/30 hover:bg-white/5",
                    "cursor-pointer",
                  )}
                  aria-current={active ? "page" : undefined}
                >
                  <Icon className={cn("h-4 w-4 shrink-0 transition-colors", active ? "text-emerald-300" : "text-zinc-400")} />
                  <span className={cn(isSynced && "transition-all duration-300 ease-in-out", "whitespace-nowrap overflow-hidden", collapsed ? "max-w-0 opacity-0 ml-0" : "max-w-[200px] opacity-100 ml-3")}>
                    {label}
                  </span>
                </Link>
              );
            })}
          </div>
        </div>
      </nav>
      <div className={cn("mt-auto", isSynced && "transition-all duration-300 ease-in-out", collapsed ? "opacity-0 translate-y-4 pointer-events-none overflow-hidden max-h-0" : "opacity-100 translate-y-0 max-h-[1000px]")}>
        <div className="space-y-5 pt-8">
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
                  {autonomyInfo.level === null ? t("sidebar.autonomy.noData") : t("sidebar.autonomy.select")}
                </option>
                {AUTONOMY_LEVELS.map((level) => {
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  const label = t(`sidebar.autonomy.levels.${level}` as any) ?? `Poziom ${level}`;
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

          <AuthorSignature />
        </div>
      </div>
    </aside>
  );
}
