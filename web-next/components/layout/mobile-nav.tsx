"use client";

import { useMemo, useState } from "react";
import { Menu, Layers, Activity, Radio, ListChecks, Sparkles, Shield, Terminal } from "lucide-react";
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
import { navItems } from "./sidebar";
import { LanguageSwitcher } from "./language-switcher";
import { useTranslation } from "@/lib/i18n";

type TelemetryTab = "queue" | "tasks" | "ws";

const AUTONOMY_LEVELS = [
  { value: 0, label: "Start" },
  { value: 10, label: "Monitor" },
  { value: 20, label: "Asystent" },
  { value: 30, label: "Hybryda" },
  { value: 40, label: "Pełny" },
];

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

  const latestLogs = useMemo(() => entries.slice(0, 5), [entries]);
  const telemetryContent = useMemo(() => {
    if (telemetryTab === "queue") {
      return {
        title: "Kolejka",
        rows: [
          { label: "Aktywne", value: queue?.active ?? "—" },
          { label: "Oczekujące", value: queue?.pending ?? "—" },
          { label: "Limit", value: queue?.limit ?? "∞" },
        ],
        badge: queue?.paused
          ? { tone: "warning" as const, text: "Wstrzymana" }
          : { tone: "success" as const, text: "Aktywna" },
      };
    }
    if (telemetryTab === "tasks") {
      return {
        title: "Zadania",
        rows: [
          { label: "Nowe", value: metrics?.tasks?.created ?? 0 },
          { label: "Skuteczność", value: metrics?.tasks?.success_rate ?? "—" },
          { label: "Uptime", value: metrics?.uptime_seconds ? formatUptime(metrics.uptime_seconds) : "—" },
        ],
        badge: { tone: "neutral" as const, text: "Podgląd" },
      };
    }
    return {
      title: "WebSocket",
      rows: [
        { label: "Status", value: connected ? "Połączono" : "Rozłączono" },
        { label: "Logi", value: `${entries.length}` },
        { label: "Ostatni", value: latestLogs[0] ? new Date(latestLogs[0].ts).toLocaleTimeString() : "—" },
      ],
      badge: connected
        ? { tone: "success" as const, text: "AKTYWNE" }
        : { tone: "danger" as const, text: "BRAK" },
    };
  }, [telemetryTab, queue, metrics, connected, entries.length, latestLogs]);

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
      >
        <Menu className="h-4 w-4" />
        {t("common.menu")}
      </Button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="glass-panel flex h-full max-w-md flex-col border-r border-white/10 bg-black/90 text-white">
          <SheetHeader className="pb-4">
            <SheetTitle className="flex items-center justify-between text-lg font-semibold text-white">
              <span className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-xl">
                  🐍
                </span>
                {t("mobileNav.navTitle")}
              </span>
              <Badge tone="neutral" className="uppercase tracking-[0.3em]">
                mobilne
              </Badge>
            </SheetTitle>
            <SheetDescription className="text-sm text-zinc-400">
              Neonowa konsola – dostęp do modułów, telemetrii i konfiguracji kosztów/autonomii.
            </SheetDescription>
          </SheetHeader>

          <nav className="mt-2 space-y-3 text-sm">
            {navItems.map((item) => {
              const label = item.labelKey ? t(item.labelKey) : item.label;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className="flex items-center gap-3 rounded-2xl border border-white/5 bg-black/40 px-4 py-3 text-white transition hover:border-emerald-400/40 hover:bg-emerald-500/10"
                  onClick={() => setOpen(false)}
                >
                  <item.icon className="h-4 w-4 text-emerald-200" />
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
                <p className="eyebrow">Telemetria</p>
                <p className="text-base font-semibold">{telemetryContent.title}</p>
              </div>
              <Badge tone={telemetryContent.badge.tone}>{telemetryContent.badge.text}</Badge>
            </div>
            <div className="mt-3 flex rounded-full border border-white/10 bg-black/40 text-xs">
              {(["queue", "tasks", "ws"] as TelemetryTab[]).map((tab) => (
                <Button
                  key={tab}
                  variant="ghost"
                  size="xs"
                  className={`flex-1 rounded-full px-3 py-1.5 uppercase tracking-[0.3em] ${
                    telemetryTab === tab ? "bg-emerald-500/20 text-white" : "text-zinc-400"
                  }`}
                  onClick={() => setTelemetryTab(tab)}
                >
                  {tab === "queue" ? "Kolejka" : tab === "tasks" ? "Zadania" : "WS"}
                </Button>
              ))}
            </div>
            <div className="mt-4 space-y-2 text-sm text-zinc-200">
              {telemetryContent.rows.map((row) => (
                <div key={row.label} className="list-row">
                  <span className="text-caption">{row.label}</span>
                  <span className="font-semibold text-white">{row.value}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="mt-4 card-shell bg-black/40 p-4">
            <div className="eyebrow flex items-center gap-2">
              <Terminal className="h-4 w-4 text-emerald-200" />
              Mini terminal
            </div>
            <div className="mt-3 max-h-32 overflow-y-auto text-xs font-mono text-zinc-300">
              {latestLogs.length === 0 && (
                <p className="text-zinc-500">
                  {connected ? "Czekam na logi..." : "Kanał rozłączony – brak logów."}
                </p>
              )}
              {latestLogs.map((entry) => (
                <p key={entry.id} className="mb-2 rounded-xl border border-white/5 bg-black/60 px-3 py-2">
                  <span className="text-emerald-300">{new Date(entry.ts).toLocaleTimeString()}</span>{" "}
                  <span className="text-white">
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
                  <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">Tryb kosztów</p>
                  <p className="text-lg font-semibold">
                    {costMode?.enabled ? "Pro (płatny)" : "Eco"}
                  </p>
                  <p className="text-xs text-zinc-400">Dostawca: {costMode?.provider ?? "brak"}</p>
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
                {costLoading ? "Przełączam..." : `Przełącz na ${costMode?.enabled ? "Eco" : "Pro"}`}
              </Button>
            </div>

            <div className="card-shell bg-gradient-to-br from-violet-500/20 via-violet-500/5 to-transparent p-4">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">Autonomia</p>
                  <p className="text-lg font-semibold">
                    {autonomy?.current_level_name ?? "Offline"}
                  </p>
                  <p className="text-xs text-zinc-400">
                    Poziom {autonomy?.current_level ?? "?"} • {autonomy?.risk_level ?? "brak"}
                  </p>
                </div>
                <Shield className="h-5 w-5 text-violet-200" />
              </div>
              <select
                className="mt-3 w-full rounded-2xl box-muted px-3 py-2 text-sm text-white outline-none focus:border-violet-400"
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
                  {autonomy ? "Wybierz poziom" : "Brak połączenia z AutonomyGate"}
                </option>
                {AUTONOMY_LEVELS.map((level) => (
                  <option key={level.value} value={level.value}>
                    {level.label}
                  </option>
                ))}
              </select>
              {autonomyLoading && (
                <p className="mt-2 text-xs text-zinc-400">Aktualizuję poziom autonomii...</p>
              )}
            </div>

            <div className="card-shell bg-black/40 p-3 text-center">
              <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">Język</p>
              <div className="mt-2 flex justify-center">
                <LanguageSwitcher className="justify-center" />
              </div>
            </div>
          </section>

          <div className="mt-6 card-shell bg-black/20 p-4 text-xs text-zinc-500">
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4" />
              Next.js + FastAPI
            </div>
            <div className="mt-2 flex items-center gap-2 text-emerald-300">
              <Activity className="h-4 w-4" />
              {connected ? "Kanał telemetryczny aktywny" : "Brak połączenia z WS"}
            </div>
            <div className="mt-2 flex items-center gap-2 text-sky-300">
              <ListChecks className="h-4 w-4" />
              {metrics?.tasks?.created ?? 0} zadań w sesji
            </div>
            <div className="mt-2 flex items-center gap-2 text-amber-200">
              <Radio className="h-4 w-4" />
              Kolejka {queue?.paused ? "wstrzymana" : "aktywna"}
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}

function formatUptime(totalSeconds: number) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}
