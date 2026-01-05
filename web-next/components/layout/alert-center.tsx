"use client";

import { useMemo, useState } from "react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ListCard } from "@/components/ui/list-card";
import { useTelemetryFeed } from "@/hooks/use-telemetry";
import { NOTIFICATIONS } from "@/lib/ui-config";
import { AlertTriangle, Filter, Copy } from "lucide-react";
import { OverlayFallback } from "./overlay-fallback";
import { useTranslation } from "@/lib/i18n";

type AlertCenterProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function AlertCenter({ open, onOpenChange }: AlertCenterProps) {
  const { entries, connected } = useTelemetryFeed(150);
  const t = useTranslation();
  const filterOptions = useMemo(
    () => [
      { value: "all" as const, label: t("alertCenter.filters.all") },
      { value: "error" as const, label: t("alertCenter.filters.error") },
      { value: "warn" as const, label: t("alertCenter.filters.warn") },
      { value: "info" as const, label: t("alertCenter.filters.info") },
    ],
    [t],
  );
  const [filter, setFilter] = useState<(typeof filterOptions)[number]["value"]>("all");
  const [copyMessage, setCopyMessage] = useState<string | null>(null);

  const parsedEntries = useMemo(() => entries.map(parseTelemetryEntry), [entries]);
  const visibleEntries = useMemo(
    () =>
      parsedEntries.filter((entry) => {
        if (filter === "all") return true;
        return entry.level === filter;
      }),
    [parsedEntries, filter],
  );

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(visibleEntries, null, 2));
      setCopyMessage(t("alertCenter.copySuccess"));
    } catch (err) {
      console.error("Clipboard error", err);
      setCopyMessage(t("alertCenter.copyError"));
    } finally {
      setTimeout(() => setCopyMessage(null), NOTIFICATIONS.COPY_MESSAGE_TIMEOUT_MS);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        data-testid="alert-center-drawer"
        className="flex h-full max-w-3xl flex-col gap-4 overflow-hidden border-l border-white/10 bg-zinc-950/95"
      >
        <SheetHeader>
          <SheetTitle>{t("alertCenter.title")}</SheetTitle>
          <SheetDescription>{t("alertCenter.description")}</SheetDescription>
        </SheetHeader>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <Filter className="h-4 w-4 text-zinc-500" />
          {filterOptions.map((item) => (
            <Button
              key={item.value}
              variant={filter === item.value ? "secondary" : "outline"}
              size="xs"
              className="px-3 uppercase tracking-wide"
              onClick={() => setFilter(item.value)}
            >
              {item.label}
            </Button>
          ))}
          <div className="ml-auto flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleCopy} className="flex items-center gap-2">
              <Copy className="h-3.5 w-3.5" />
              {t("alertCenter.copy")}
            </Button>
            {copyMessage && <span className="text-emerald-300">{copyMessage}</span>}
          </div>
        </div>

        <div className="flex-1 overflow-auto rounded-2xl box-muted p-4 space-y-3">
          {!connected ? (
            <OverlayFallback
              icon={<AlertTriangle className="h-5 w-5" />}
              title={t("alertCenter.offlineTitle")}
              description={t("alertCenter.offlineDescription")}
              hint={t("alertCenter.hint")}
              testId="alert-center-offline-state"
            />
          ) : visibleEntries.length === 0 ? (
            <OverlayFallback
              icon={<AlertTriangle className="h-5 w-5" />}
              title={t("alertCenter.emptyTitle")}
              description={t("alertCenter.emptyDescription")}
              hint={t("alertCenter.hint")}
              testId="alert-center-empty-state"
            />
          ) : (
            <div className="space-y-3" data-testid="alert-center-entries">
              {visibleEntries.map((entry) => (
                <ListCard
                  key={entry.id}
                  title={entry.message}
                  badge={<Badge tone={toneFromLevel(entry.level)}>{entry.levelLabel}</Badge>}
                  meta={<span className="text-hint">{formatTimestamp(entry.ts)}</span>}
                >
                  {entry.details && (
                    <pre className="mt-2 max-h-48 overflow-auto rounded-xl bg-black/40 p-3 text-xs text-zinc-300">
                      {entry.details}
                    </pre>
                  )}
                </ListCard>
              ))}
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function parseTelemetryEntry(entry: { id: string; ts: number; payload: unknown }) {
  const defaultMessage =
    typeof entry.payload === "string" ? entry.payload : JSON.stringify(entry.payload);

  if (isLogPayload(entry.payload)) {
    const levelRaw = entry.payload.level?.toLowerCase() ?? "info";
    const details =
      typeof entry.payload.details === "string"
        ? entry.payload.details
        : entry.payload.details
          ? JSON.stringify(entry.payload.details, null, 2)
          : undefined;
    return {
      id: entry.id,
      ts: entry.ts,
      level: (levelRaw.includes("error") && "error") ||
        (levelRaw.includes("warn") && "warn") ||
        "info",
      levelLabel: levelRaw.toUpperCase(),
      message: entry.payload.message ?? defaultMessage,
      details,
    };
  }

  return {
    id: entry.id,
    ts: entry.ts,
    level: "info" as const,
    levelLabel: "INFO",
    message: defaultMessage,
    details: undefined,
  };
}

type LogPayload = {
  message?: string;
  level?: string;
  type?: string;
  details?: unknown;
};

function isLogPayload(value: unknown): value is LogPayload {
  return typeof value === "object" && value !== null;
}

function formatTimestamp(ts: number) {
  return new Date(ts).toLocaleString();
}

function toneFromLevel(level: string) {
  if (level === "error") return "danger" as const;
  if (level === "warn") return "warning" as const;
  return "neutral" as const;
}
