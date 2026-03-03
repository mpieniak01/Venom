import { useState, useEffect, useMemo, useCallback } from "react";
import { cn } from "@/lib/utils";
import type { BenchmarkModelResult } from "@/lib/types";
import { Trash2, History, RefreshCw, X, Clock } from "lucide-react";
import { useBenchmark } from "@/hooks/use-benchmark";
import { getApiBaseUrl } from "@/lib/env";

interface BenchmarkResultsProps {
  readonly currentResults: ReadonlyArray<BenchmarkModelResult>;
}

interface BenchmarkHistoryItem {
  benchmark_id: string;
  status: string;
  created_at: string;
  models: string[];
  results: BenchmarkModelResult[];
}

export function BenchmarkResults({ currentResults }: BenchmarkResultsProps) {
  const safeResults = useMemo(() => currentResults || [], [currentResults]);
  const [history, setHistory] = useState<BenchmarkHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const { deleteBenchmark, clearAllBenchmarks } = useBenchmark();
  const apiBase = useMemo(() => getApiBaseUrl() || "", []);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiBase}/api/v1/benchmark/list?limit=50`);
      if (res.ok) {
        const data = await res.json();
        setHistory(data.benchmarks || []);
      }
    } catch (e) {
      console.error("Failed to fetch history", e);
    } finally {
      setLoading(false);
    }
  }, [apiBase]);

  useEffect(() => {
    fetchHistory();
  }, [safeResults, fetchHistory]); // Odśwież jak zmienią się bieżące wyniki (np. po zakończeniu testu)

  const handleDelete = async (id: string) => {
    if (confirm("Czy na pewno chcesz usunąć ten wynik?")) {
      const success = await deleteBenchmark(id);
      if (success) fetchHistory();
    }
  };

  const handleClearAll = async () => {
    if (confirm("Czy na pewno chcesz usunąć CAŁĄ historię?")) {
      const success = await clearAllBenchmarks();
      if (success) fetchHistory();
    }
  };

  // Formatowanie daty
  const formatDate = (isoString: string) => {
    if (!isoString) return "-";
    return new Date(isoString).toLocaleString("pl-PL", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="space-y-6">
      {/* Sekcja bieżących wyników (jeśli są) */}
      {safeResults.length > 0 && (
        <div className="space-y-3">
          <h4 className="heading-h4 text-[color:var(--text-heading)]">Bieżący wynik</h4>
          <div className="overflow-x-auto rounded-xl bg-[color:var(--surface-muted)]">
            <ResultsTable results={safeResults} />
          </div>
        </div>
      )}

      {/* Sekcja historii */}
      <div className="space-y-3 pt-6 border-t border-[color:var(--ui-border)]">
        <div className="flex items-center justify-between">
          <h4 className="heading-h4 text-[color:var(--text-heading)] flex items-center gap-2">
            <History className="w-4 h-4 text-[color:var(--accent)]" />
            Historia Testów
          </h4>
          <div className="flex gap-2">
            <button
              onClick={fetchHistory}
              className="p-2 rounded-lg hover:bg-[color:var(--ui-surface-hover)] text-[color:var(--ui-muted)] hover:text-[color:var(--text-primary)] transition-colors"
              title="Odśwież"
            >
              <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
            </button>
            {history.length > 0 && (
              <button
                onClick={handleClearAll}
                className="p-2 rounded-lg hover:bg-rose-500/20 text-rose-400 hover:text-rose-300 transition-colors flex items-center gap-2 text-xs font-medium"
              >
                <Trash2 className="w-4 h-4" />
                Wyczyść wszystko
              </button>
            )}
          </div>
        </div>

        {history.length === 0 ? (
          <div className="text-center py-8 text-[color:var(--ui-muted)] text-sm">
            Brak zapisanych wyników benchmarków.
          </div>
        ) : (
          <div className="grid gap-4">
            {history.map((item) => (
              <div key={item.benchmark_id} className="rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] p-4 relative group">
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className={cn(
                        "w-2 h-2 rounded-full",
                        resolveStatusColor(item.status)
                      )} />
                      <span className="font-mono text-xs text-[color:var(--ui-muted)]">{item.benchmark_id.slice(0, 8)}</span>
                      <span className="text-xs text-[color:var(--text-secondary)] flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {formatDate(item.created_at)}
                      </span>
                    </div>
                    <div className="text-sm font-medium text-[color:var(--text-primary)]">
                      Modele: {item.models.join(", ")}
                    </div>
                  </div>
                  <button
                    onClick={() => handleDelete(item.benchmark_id)}
                    className="opacity-0 group-hover:opacity-100 p-2 text-[color:var(--ui-muted)] hover:text-rose-400 transition-all"
                    title="Usuń wynik"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {/* Tabela wyników dla danego wpisu historii */}
                {item.results && item.results.length > 0 && (
                  <div className="mt-2 text-xs">
                    <ResultsTable results={item.results} mini />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// Komponent tabeli (reusable)
function ResultsTable({ results, mini = false }: Readonly<{ results: ReadonlyArray<BenchmarkModelResult>, mini?: boolean }>) {
  return (
    <table className="w-full text-left">
      <thead>
        <tr className="border-b border-[color:var(--ui-border)] text-[color:var(--text-secondary)]">
          <th className="py-2 font-medium">Model</th>
          <th className="py-2 text-right">Latencja</th>
          <th className="py-2 text-right">Speed</th>
          <th className="py-2 text-right">VRAM</th>
          {!mini && <th className="py-2 text-center">Status</th>}
        </tr>
      </thead>
      <tbody className="divide-y divide-[color:var(--ui-border)]">
        {results.map((r: BenchmarkModelResult) => (
          <tr key={r.model_name}>
            <td className="py-2 font-medium text-[color:var(--text-primary)]">{r.model_name}</td>
            <td className="py-2 text-right text-[color:var(--ui-muted)]">{r.latency_ms == null ? "-" : `${r.latency_ms}ms`}</td>
            <td className="py-2 text-right text-[color:var(--ui-muted)]">{r.tokens_per_second == null ? "-" : `${r.tokens_per_second} t/s`}</td>
            <td className="py-2 text-right text-[color:var(--ui-muted)]">{r.peak_vram_mb == null ? "-" : `${r.peak_vram_mb} MB`}</td>
            {!mini && (
              <td className="py-2 text-center">
                <span className={cn(
                  "px-2 py-0.5 rounded-full text-[10px]",
                  resolveResultStatusColor(r.status)
                )}>
                  {r.status}
                </span>
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function resolveStatusColor(status: string): string {
  if (status === 'completed') return "bg-emerald-500";
  if (status === 'failed') return "bg-rose-500";
  return "bg-amber-500";
}

function resolveResultStatusColor(status: string): string {
  if (status === 'completed') return "bg-[color:var(--badge-success-bg)] text-[color:var(--badge-success-text)]";
  if (status === 'failed') return "bg-[color:var(--badge-danger-bg)] text-[color:var(--badge-danger-text)]";
  return "bg-[color:var(--badge-neutral-bg)] text-[color:var(--badge-neutral-text)]";
}
