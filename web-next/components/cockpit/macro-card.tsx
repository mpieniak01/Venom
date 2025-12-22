"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { formatLogPayload, isLogPayload, type LogEntryType } from "@/lib/logs";
import { PinOff } from "lucide-react";

type MacroCardProps = {
  title: string;
  description?: string;
  isCustom?: boolean;
  pending?: boolean;
  onRun: () => void;
  onRemove?: () => void;
};

export function MacroCard({
  title,
  description,
  isCustom,
  pending,
  onRun,
  onRemove,
}: MacroCardProps) {
  return (
    <div className="card-shell bg-gradient-to-br from-violet-500/20 via-violet-500/5 to-transparent p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.25em] text-violet-200">
            Makro
          </p>
          <h3 className="text-lg font-semibold text-white">{title}</h3>
          <p className="text-xs text-zinc-400">{description || "Brak opisu."}</p>
        </div>
        {isCustom && onRemove && (
          <Button
            variant="ghost"
            size="xs"
            className="text-zinc-400 hover:text-rose-300"
            onClick={onRemove}
          >
            Usuń
          </Button>
        )}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          variant="macro"
          size="md"
          className="rounded-full px-4 text-sm font-semibold"
          disabled={pending}
          onClick={onRun}
        >
          {pending ? "Wysyłam..." : "Uruchom"}
        </Button>
        {isCustom && (
          <Badge tone="neutral" className="border border-white/10 bg-black/20 text-[11px]">
            Custom
          </Badge>
        )}
      </div>
    </div>
  );
}

type PinnedLogCardProps = {
  log: LogEntryType;
  onUnpin: () => void;
};

export function PinnedLogCard({ log, onUnpin }: PinnedLogCardProps) {
  const payload = isLogPayload(log.payload) ? log.payload : null;
  const level = payload?.level?.toUpperCase() ?? "INFO";
  const type = payload?.type?.toUpperCase() ?? "LOG";
  const tone =
    level.includes("ERR") || level.includes("FAIL")
      ? "danger"
      : level.includes("WARN")
        ? "warning"
        : "neutral";

  return (
    <div className="rounded-3xl border border-emerald-400/20 bg-black/30 p-4 text-sm text-white shadow-inner shadow-emerald-500/10">
      <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.3em] text-emerald-200">
        <span>{new Date(log.ts).toLocaleTimeString()}</span>
        <div className="flex items-center gap-2">
          <Badge tone={tone}>
            {type} • {level}
          </Badge>
          <IconButton
            label="Odepnij log"
            size="xs"
            icon={<PinOff className="h-3.5 w-3.5" />}
            className="text-emerald-200 hover:text-rose-300"
            onClick={onUnpin}
          />
        </div>
      </div>
      {payload?.message && (
        <p className="mt-2 font-mono text-xs text-emerald-100/90">{payload.message}</p>
      )}
      <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-xs text-emerald-100">
        {formatLogPayload(payload ?? log.payload)}
      </pre>
    </div>
  );
}
