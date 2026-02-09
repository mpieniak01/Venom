"use client";

import { IconButton } from "@/components/ui/icon-button";
import { Pin, PinOff } from "lucide-react";

import { type LogEntryType, isLogPayload } from "@/lib/logs";
import { useTranslation } from "@/lib/i18n";

type LogEntryProps = Readonly<{
  entry: LogEntryType;
  pinned?: boolean;
  onPin?: () => void;
}>;

export function LogEntry({ entry, pinned, onPin }: LogEntryProps) {
  const payload = entry.payload;
  const t = useTranslation();
  const logObj = isLogPayload(payload) ? payload : null;
  const rawText = (() => {
    if (logObj?.message) return logObj.message;
    if (typeof payload === "string") return payload;
    return JSON.stringify(payload, null, 2);
  })();

  // Próbujemy przetłumaczyć rawText jako klucz i18n
  const text = t(rawText, logObj?.data);

  const level = logObj?.level ? logObj.level.toUpperCase() : "INFO";
  const type = logObj?.type || "log";

  return (
    <div className="mb-2 rounded border border-emerald-500/20 bg-black/10 p-2 font-mono text-xs text-emerald-200 shadow-inner">
      <div className="flex items-center justify-between text-caption text-emerald-300/70">
        <span>{new Date(entry.ts).toLocaleTimeString()}</span>
        <div className="flex items-center gap-2">
          <span>
            {type} • {level}
          </span>
          {onPin && (
            <IconButton
              label={pinned ? "Odepnij log" : "Przypnij log"}
              size="xs"
              variant="outline"
              className={
                pinned
                  ? "border-emerald-400/60 bg-emerald-500/20 text-emerald-100"
                  : "border-emerald-400/30 text-emerald-200"
              }
              icon={pinned ? <PinOff className="h-3.5 w-3.5" /> : <Pin className="h-3.5 w-3.5" />}
              onClick={onPin}
            />
          )}
        </div>
      </div>
      {logObj?.details ? (
        <details className="mt-1">
          <summary className="cursor-pointer text-emerald-200">Szczegóły</summary>
          <pre className="mt-1 max-h-40 overflow-auto text-emerald-100">
            {typeof logObj.details === "string"
              ? logObj.details
              : JSON.stringify(logObj.details, null, 2)}
          </pre>
        </details>
      ) : (
        <pre className="mt-1 whitespace-pre-wrap text-emerald-100">{"> " + text}</pre>
      )}
    </div>
  );
}
