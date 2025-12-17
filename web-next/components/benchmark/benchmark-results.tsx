"use client";

import { cn } from "@/lib/utils";
import type { BenchmarkModelResult } from "@/lib/types";

interface BenchmarkResultsProps {
  results: BenchmarkModelResult[];
}

// Funkcja pomocnicza do sortowania wyników benchmarku
function sortBenchmarkResults(results: BenchmarkModelResult[]): BenchmarkModelResult[] {
  return [...results].sort((a, b) => {
    // Sukces na górze
    if (a.status === "success" && b.status !== "success") return -1;
    if (a.status !== "success" && b.status === "success") return 1;
    // Jeśli oba sukces, sortuj według czasu
    if (a.status === "success" && b.status === "success") {
      return a.avg_response_time_ms - b.avg_response_time_ms;
    }
    return 0;
  });
}

export function BenchmarkResults({ results }: BenchmarkResultsProps) {
  if (results.length === 0) {
    return (
      <div className="rounded-xl border border-white/10 bg-black/30 p-8 text-center">
        <p className="text-sm text-zinc-500">
          Wyniki pojawią się po zakończeniu testu
        </p>
      </div>
    );
  }

  const getStatusColor = (status: BenchmarkModelResult["status"]) => {
    switch (status) {
      case "success":
        return "text-emerald-400 bg-emerald-500/10 border-emerald-500/30";
      case "oom":
        return "text-rose-400 bg-rose-500/10 border-rose-500/30";
      case "error":
        return "text-amber-400 bg-amber-500/10 border-amber-500/30";
      default:
        return "text-zinc-400 bg-zinc-500/10 border-zinc-500/30";
    }
  };

  const getStatusLabel = (status: BenchmarkModelResult["status"]) => {
    switch (status) {
      case "success":
        return "✓ Sukces";
      case "oom":
        return "⚠ OOM (brak pamięci)";
      case "error":
        return "✗ Błąd";
      default:
        return "—";
    }
  };

  const sortedResults = sortBenchmarkResults(results);

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold text-zinc-300">
        Wyniki porównawcze
      </h4>

      <div className="overflow-x-auto rounded-xl border border-white/10 bg-black/30">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/10">
              <th className="px-4 py-3 text-left font-medium text-zinc-400">
                Model
              </th>
              <th className="px-4 py-3 text-right font-medium text-zinc-400">
                Śr. Czas (ms)
              </th>
              <th className="px-4 py-3 text-right font-medium text-zinc-400">
                Tokens/sec
              </th>
              <th className="px-4 py-3 text-right font-medium text-zinc-400">
                Max VRAM (MB)
              </th>
              <th className="px-4 py-3 text-center font-medium text-zinc-400">
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedResults.map((result) => (
              <tr
                key={result.model_name}
                className={cn(
                  "border-b border-white/5 transition hover:bg-white/5",
                  result.status === "oom" && "bg-rose-500/5"
                )}
              >
                <td className="px-4 py-3 font-medium text-zinc-200">
                  {result.model_name}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-zinc-300">
                  {result.status === "success"
                    ? result.avg_response_time_ms.toFixed(0)
                    : "—"}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-zinc-300">
                  {result.status === "success"
                    ? result.tokens_per_sec.toFixed(2)
                    : "—"}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-zinc-300">
                  {result.status === "success" || result.status === "oom"
                    ? result.max_vram_mb.toFixed(0)
                    : "—"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-center">
                    <span
                      className={cn(
                        "inline-flex rounded-full border px-3 py-1 text-xs font-medium",
                        getStatusColor(result.status)
                      )}
                    >
                      {getStatusLabel(result.status)}
                    </span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Podsumowanie / Best Model */}
      {sortedResults.some((r) => r.status === "success") && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
          <p className="text-xs uppercase tracking-wide text-emerald-400">
            Najlepszy wynik
          </p>
          <p className="mt-1 text-lg font-semibold text-white">
            {sortedResults.find((r) => r.status === "success")?.model_name}
          </p>
          <p className="mt-1 text-xs text-zinc-400">
            Najkrótszy średni czas odpowiedzi:{" "}
            {sortedResults
              .find((r) => r.status === "success")
              ?.avg_response_time_ms.toFixed(0)}{" "}
            ms
          </p>
        </div>
      )}
    </div>
  );
}
