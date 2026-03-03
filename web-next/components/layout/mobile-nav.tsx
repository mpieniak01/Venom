"use client";

import { useMemo, useState } from "react";
import { Menu, Layers, Activity, Radio, ListChecks, Sparkles, Shield, Terminal } from "lucide-react";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import Link from "next/link";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  setAutonomy,
  setCostMode,
  useAutonomyLevel,
  useCostMode,
  useMetrics,
  useQueueStatus,
} from "@/hooks/use-api";
import { useTelemetryFeed } from "@/hooks/use-telemetry";
import { LanguageSwitcher } from "./language-switcher";
import { useLanguage, useTranslation } from "@/lib/i18n";
import { getNavigationItems } from "./sidebar-helpers";
import {
  TelemetryTab,
  AUTONOMY_LEVELS,
  getTelemetryContent
} from "./mobile-nav-helpers";

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const [telemetryTab, setTelemetryTab] = useState<TelemetryTab>("queue");
  const [costLoading, setCostLoading] = useState(false);
  const [autonomyLoading, setAutonomyLoading] = useState(false);

  const { data: queue } = useQueueStatus(10000);
  const { data: metrics } = useMetrics(10000);
  const { connected, entries } = useTelemetryFeed();
  const { data: costMode, refresh: refreshCost } = useCostMode(15000);
  const { data: autonomy, refresh: refreshAutonomy } = useAutonomyLevel(20000);
  const t = useTranslation();
  const pathname = usePathname();
  const { language } = useLanguage();
  const navigationItems = useMemo(() => getNavigationItems(language), [language]);

  const latestLogs = useMemo(() => entries.slice(0, 5), [entries]);
  const telemetryContent = useMemo(() =>
    getTelemetryContent({
      telemetryTab,
      queue,
      metrics,
      connected,
      entriesCount: entries.length,
      latestLogsTs: latestLogs[0] ? new Date(latestLogs[0].ts).toLocaleTimeString() : null,
      t
    }),
    [telemetryTab, queue, metrics, connected, entries.length, latestLogs, t]
  );
  const telemetryLabelByTab: Record<TelemetryTab, string> = {
    queue: t("mobileNav.telemetry.queue"),
    tasks: t("mobileNav.telemetry.tasks"),
    ws: t("mobileNav.telemetry.ws"),
  };

  const handleCostToggle = async () => {
    setCostLoading(true);
    try {
      await setCostMode(!(costMode?.enabled ?? false));
      refreshCost();
    } catch (err) {
      console.error("Cost toggle failed:", err);
    } finally {
      setCostLoading(false);
    }
  };

  const handleAutonomyChange = async (value: number) => {
    if (autonomy?.current_level === value) return;
    setAutonomyLoading(true);
    try {
      await setAutonomy(value);
      refreshAutonomy();
    } catch (err) {
      console.error("Autonomy change failed:", err);
    } finally {
      setAutonomyLoading(false);
    }
  };

  return (
    <>
      <Button
        className="gap-2 text-sm lg:hidden"
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        aria-label={t("common.openNavigation")}
        suppressHydrationWarning
      >
        <Menu className="h-4 w-4" />
        <span suppressHydrationWarning>{t("common.menu")}</span>
      </Button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="glass-panel flex h-full max-w-md flex-col border-r border-[color:var(--ui-border)] bg-[color:var(--bg-panel)] text-[color:var(--text-primary)]">
          <SheetHeader className="pb-4">
            <SheetTitle className="flex items-center justify-between text-lg font-semibold text-[color:var(--text-heading)]">
              <span className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-2xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface-hover)] text-xl">
                  🐍
                </span>
                {t("mobileNav.navTitle")}
              </span>
              <Badge tone="neutral" className="uppercase tracking-[0.3em]">
                mobilne
              </Badge>
            </SheetTitle>
            <SheetDescription className="text-sm text-[color:var(--text-secondary)]">
              Neonowa konsola – dostęp do modułów, telemetrii i konfiguracji kosztów/autonomii.
            </SheetDescription>
          </SheetHeader>

          <nav className="mt-2 space-y-3 text-sm">
            {navigationItems.map((item) => {
              const label = item.labelKey ? t(item.labelKey) : item.label;
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-2xl border px-4 py-3 transition",
                    active
                      ? "border-[color:var(--primary)]/30 bg-gradient-to-r from-[color:var(--primary)]/10 to-transparent text-[color:var(--text-heading)] shadow-sm"
                      : "border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] text-[color:var(--text-primary)] hover:border-[color:var(--ui-border-strong)] hover:bg-[color:var(--ui-surface-hover)]"
                  )}
                  onClick={() => setOpen(false)}
                >
                  <item.icon className={cn("h-4 w-4", active ? "text-[color:var(--primary)]" : "text-[color:var(--ui-muted)]")} />
                  <div>
                    <p className="font-semibold tracking-wide">{label}</p>
                    <p className="eyebrow">
                      /{item.href === "/" ? "cockpit" : item.href.replace("/", "")}
                    </p>
                  </div>
                </Link>
              );
            })}
          </nav>

          <section className="mt-6 card-shell card-base p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="eyebrow">{t("mobileNav.telemetry.title")}</p>
                <p className="text-base font-semibold">{telemetryContent.title}</p>
              </div>
              <Badge tone={telemetryContent.badge.tone}>{telemetryContent.badge.text}</Badge>
            </div>
            <div className="mt-3 flex rounded-full border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] text-xs">
              {(["queue", "tasks", "ws"] as TelemetryTab[]).map((tab) => (
                <Button
                  key={tab}
                  variant="ghost"
                  size="xs"
                  className={`flex-1 rounded-full px-3 py-1.5 uppercase tracking-[0.3em] ${telemetryTab === tab ? "bg-[color:var(--primary-glow)] text-[color:var(--text-heading)]" : "text-[color:var(--text-secondary)]"
                    }`}
                  onClick={() => setTelemetryTab(tab)}
                >
                  {telemetryLabelByTab[tab]}
                </Button>
              ))}
            </div>
            <div className="mt-4 space-y-2 text-sm text-[color:var(--text-primary)]">
              {telemetryContent.rows.map((row) => (
                <div key={row.label} className="list-row">
                  <span className="text-caption">{row.label}</span>
                  <span className="font-semibold text-[color:var(--text-heading)]">{row.value}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="mt-4 card-shell bg-[color:var(--ui-surface)] p-4">
            <div className="eyebrow flex items-center gap-2">
              <Terminal className="h-4 w-4 text-[color:var(--primary)]" />
              {t("mobileNav.telemetry.miniTerminal")}
            </div>
            <div className="mt-3 max-h-32 overflow-y-auto text-xs font-mono text-[color:var(--text-secondary)]">
              {latestLogs.length === 0 && (
                <p className="text-[color:var(--ui-muted)]">
                  {connected ? t("mobileNav.telemetry.logsWaiting") : t("mobileNav.telemetry.logsDisconnected")}
                </p>
              )}
              {latestLogs.map((entry) => (
                <p key={entry.id} className="mb-2 rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--bg-panel)] px-3 py-2">
                  <span className="text-[color:var(--primary)]">{new Date(entry.ts).toLocaleTimeString()}</span>{" "}
                  <span className="text-[color:var(--text-primary)]">
                    {typeof entry.payload === "string"
                      ? entry.payload
                      : JSON.stringify(entry.payload)}
                  </span>
                </p>
              ))}
            </div>
          </section>

          <section className="mt-4 space-y-3">
            <div className="card-shell bg-gradient-to-br from-emerald-500/20 via-emerald-500/5 to-transparent p-4">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.35em] text-[color:var(--ui-muted)]">{t("mobileNav.telemetry.costMode")}</p>
                  <p className="text-lg font-semibold text-[color:var(--text-heading)]">
                    {costMode?.enabled ? t("sidebar.cost.pro") : t("sidebar.cost.eco")}
                  </p>
                  <p className="text-xs text-[color:var(--text-secondary)]">{t("mobileNav.telemetry.provider")}: {costMode?.provider ?? t("mobileNav.telemetry.noneProvider")}</p>
                </div>
                <Sparkles className="h-5 w-5 text-emerald-200" />
              </div>
              <Button
                className="mt-3 w-full justify-center"
                variant={costMode?.enabled ? "warning" : "secondary"}
                size="sm"
                disabled={costLoading}
                onClick={handleCostToggle}
              >
                {(() => {
                  if (costLoading) return t("mobileNav.telemetry.switching");
                  const targetLabel = costMode?.enabled ? "Eco" : "Pro";
                  return `${t("mobileNav.telemetry.switchTo")} ${targetLabel}`;
                })()}
              </Button>
            </div>

            <div className="card-shell bg-gradient-to-br from-violet-500/20 via-violet-500/5 to-transparent p-4">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.35em] text-[color:var(--ui-muted)]">{t("mobileNav.telemetry.autonomy")}</p>
                  <p className="text-lg font-semibold text-[color:var(--text-heading)]">
                    {autonomy?.current_level_name ?? t("mobileNav.telemetry.offline")}
                  </p>
                  <p className="text-xs text-[color:var(--text-secondary)]">
                    {t("mobileNav.telemetry.level")} {autonomy?.current_level ?? "?"} • {autonomy?.risk_level ?? t("mobileNav.telemetry.risk")}
                  </p>
                </div>
                <Shield className="h-5 w-5 text-violet-200" />
              </div>
              <select
                className="mt-3 w-full rounded-2xl box-muted px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none focus:border-violet-400 bg-[color:var(--ui-surface)] border-[color:var(--ui-border)]"
                value={autonomy?.current_level ?? ""}
                onChange={(event) => {
                  const nextValue = Number(event.target.value);
                  if (!Number.isNaN(nextValue)) {
                    void handleAutonomyChange(nextValue);
                  }
                }}
                disabled={autonomyLoading}
              >
                <option value="" disabled>
                  {autonomy ? t("mobileNav.telemetry.select") : t("mobileNav.telemetry.noAutonomy")}
                </option>
                {AUTONOMY_LEVELS.map((level) => (
                  <option key={level.value} value={level.value}>
                    {level.label}
                  </option>
                ))}
              </select>
              {autonomyLoading && (
                <p className="mt-2 text-xs text-[color:var(--text-secondary)]">{t("mobileNav.telemetry.updatingAutonomy")}</p>
              )}
            </div>

            <div className="card-shell bg-[color:var(--ui-surface)] p-3 text-center">
              <p className="text-xs uppercase tracking-[0.35em] text-[color:var(--ui-muted)]">{t("mobileNav.telemetry.language")}</p>
              <div className="mt-2 flex justify-center">
                <LanguageSwitcher className="justify-center" />
              </div>
            </div>
          </section>

          <div className="mt-6 card-shell bg-[color:var(--ui-surface)] p-4 text-xs text-[color:var(--text-secondary)]">
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4" />
              Next.js + FastAPI
            </div>
            <div className="mt-2 flex items-center gap-2 text-emerald-300">
              <Activity className="h-4 w-4" />
              {connected ? t("mobileNav.telemetry.telemetryActive") : t("mobileNav.telemetry.noWsConnection")}
            </div>
            <div className="mt-2 flex items-center gap-2 text-sky-300">
              <ListChecks className="h-4 w-4" />
              {metrics?.tasks?.created ?? 0} {t("mobileNav.telemetry.tasksInSession")}
            </div>
            <div className="mt-2 flex items-center gap-2 text-amber-200">
              <Radio className="h-4 w-4" />
              {t("mobileNav.telemetry.queue")} {queue?.paused ? t("mobileNav.telemetry.queuePaused") : t("mobileNav.telemetry.queueActive")}
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
