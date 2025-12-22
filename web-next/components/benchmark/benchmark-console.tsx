"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import type { BenchmarkLog } from "@/lib/types";

interface BenchmarkConsoleProps {
  logs: BenchmarkLog[];
  isRunning?: boolean;
}

// Stałe dla ikon poziomu logów
const LEVEL_ICONS = {
  error: "❌",
  warning: "⚠️",
  info: "ℹ️",
} as const;

// Funkcje pomocnicze wyodrębnione poza komponent dla lepszej wydajności
function getLevelColor(level: BenchmarkLog["level"]): string {
  switch (level) {
    case "error":
      return "text-rose-400";
    case "warning":
      return "text-amber-400";
    default:
      return "text-emerald-400";
  }
}

function getLevelIcon(level: BenchmarkLog["level"]): string {
  return LEVEL_ICONS[level] || LEVEL_ICONS.info;
}

export function BenchmarkConsole({ logs, isRunning = false }: BenchmarkConsoleProps) {
  const consoleRef = useRef<HTMLDivElement>(null);

  // Auto-scroll do dołu przy nowych logach
  useEffect(() => {
    if (consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="heading-h4 text-zinc-300">
          Logi wykonania
        </h4>
        {isRunning && (
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
            <span className="text-xs text-emerald-400">W trakcie...</span>
          </div>
        )}
      </div>

      <div
        ref={consoleRef}
        className="h-64 overflow-y-auto rounded-xl border border-white/10 bg-black/50 p-4 font-mono text-xs"
      >
        {logs.length === 0 ? (
          <p className="text-zinc-500">Brak logów. Uruchom benchmark, aby zobaczyć postęp.</p>
        ) : (
          <div className="space-y-1">
            {logs.map((log, index) => (
              <div key={index} className="flex gap-2">
                <span className="text-zinc-600">
                  {new Date(log.timestamp).toLocaleTimeString("pl-PL")}
                </span>
                <span className={getLevelColor(log.level)}>
                  {getLevelIcon(log.level)}
                </span>
                <span className={cn("flex-1", getLevelColor(log.level))}>
                  {log.message}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
