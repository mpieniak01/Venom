"use client";

import { useState } from "react";
import { Panel } from "@/components/ui/panel";
import { BenchmarkConfigurator } from "@/components/benchmark/benchmark-configurator";
import { BenchmarkConsole } from "@/components/benchmark/benchmark-console";
import { BenchmarkResults } from "@/components/benchmark/benchmark-results";
import { useModels } from "@/hooks/use-api";
import type {
  BenchmarkConfig,
  BenchmarkLog,
  BenchmarkModelResult,
  BenchmarkStatus,
} from "@/lib/types";

export default function BenchmarkPage() {
  const { data: modelsData, loading: modelsLoading } = useModels(15000);
  const [status, setStatus] = useState<BenchmarkStatus>("idle");
  const [logs, setLogs] = useState<BenchmarkLog[]>([]);
  const [results, setResults] = useState<BenchmarkModelResult[]>([]);

  const addLog = (message: string, level: BenchmarkLog["level"] = "info") => {
    setLogs((prev) => [
      ...prev,
      {
        timestamp: new Date().toISOString(),
        message,
        level,
      },
    ]);
  };

  // Symulacja benchmarku (do zastąpienia prawdziwym API)
  const runBenchmark = async (config: BenchmarkConfig) => {
    setStatus("running");
    setLogs([]);
    setResults([]);

    addLog(`Rozpoczynam benchmark dla runtime: ${config.runtime}`);
    addLog(`Wybrane modele: ${config.models.join(", ")}`);
    addLog(`Liczba pytań testowych: ${config.num_questions}`);

    try {
      const mockResults: BenchmarkModelResult[] = [];

      for (let i = 0; i < config.models.length; i++) {
        const modelName = config.models[i];
        addLog(`[${i + 1}/${config.models.length}] Ładowanie modelu: ${modelName}...`);

        // Symulacja opóźnienia ładowania
        await new Promise((resolve) => setTimeout(resolve, 1500));

        addLog(`Model ${modelName} załadowany. Rozpoczynam generowanie odpowiedzi...`);

        // Symulacja testowania
        for (let q = 1; q <= config.num_questions; q++) {
          addLog(
            `  Generowanie odpowiedzi ${q}/${config.num_questions} dla ${modelName}...`
          );
          await new Promise((resolve) => setTimeout(resolve, 800));
        }

        // Symulacja wyników - losowe wartości dla demonstracji
        const isOOM = Math.random() < 0.15; // 15% szans na OOM
        const isError = !isOOM && Math.random() < 0.1; // 10% szans na błąd

        const result: BenchmarkModelResult = {
          model_name: modelName,
          avg_response_time_ms: isOOM || isError ? 0 : 800 + Math.random() * 2000,
          tokens_per_sec: isOOM || isError ? 0 : 10 + Math.random() * 40,
          max_vram_mb: 2048 + Math.random() * 4096,
          status: isOOM ? "oom" : isError ? "error" : "success",
          error_message: isError ? "Connection timeout" : undefined,
        };

        mockResults.push(result);

        if (isOOM) {
          addLog(
            `❌ Model ${modelName} przekroczył limit VRAM i spowodował OOM`,
            "error"
          );
        } else if (isError) {
          addLog(`⚠️ Model ${modelName} zakończył się błędem`, "warning");
        } else {
          addLog(
            `✅ Model ${modelName} ukończony - ${result.avg_response_time_ms.toFixed(0)}ms avg, ${result.tokens_per_sec.toFixed(2)} tok/s`,
            "info"
          );
        }
      }

      setResults(mockResults);
      addLog("🎉 Benchmark zakończony pomyślnie!", "info");
      setStatus("completed");
    } catch (error) {
      addLog(`Błąd podczas benchmarku: ${error}`, "error");
      setStatus("failed");
    }
  };

  const handleStart = (config: BenchmarkConfig) => {
    runBenchmark(config);
  };

  // Przygotuj listę modeli do wyboru
  const availableModels =
    modelsData?.models.map((model) => ({
      name: model.name || "unknown",
      provider: model.provider || "vllm",
    })) || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-white">
          Panel Benchmarkingu
        </h1>
        <p className="mt-2 text-sm text-zinc-400">
          Testuj wydajność modeli i porównaj ich parametry (czas odpowiedzi, tokens/sec, użycie VRAM)
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Konfigurator */}
        <Panel
          eyebrow="Krok 1"
          title="Konfiguracja testu"
          description="Wybierz runtime, modele i liczbę pytań"
        >
          {modelsLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-violet-500 border-t-transparent" />
              <span className="ml-3 text-sm text-zinc-400">
                Ładowanie modeli...
              </span>
            </div>
          ) : (
            <BenchmarkConfigurator
              availableModels={availableModels}
              onStart={handleStart}
              disabled={status === "running"}
            />
          )}
        </Panel>

        {/* Console / Logi */}
        <Panel
          eyebrow="Krok 2"
          title="Postęp wykonania"
          description="Podgląd na żywo logów z testów"
        >
          <BenchmarkConsole logs={logs} isRunning={status === "running"} />
        </Panel>
      </div>

      {/* Wyniki */}
      <Panel
        eyebrow="Krok 3"
        title="Wyniki porównawcze"
        description="Tabela z metrykami wydajności dla testowanych modeli"
      >
        <BenchmarkResults results={results} />
      </Panel>
    </div>
  );
}
