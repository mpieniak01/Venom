"use client";

import { useState } from "react";
import { Gauge } from "lucide-react";
import { Panel } from "@/components/ui/panel";
import { SectionHeading } from "@/components/ui/section-heading";
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

// Stałe dla symulacji benchmarku
const SIMULATION_MODEL_LOAD_DELAY_MS = 1500;
const SIMULATION_QUESTION_DELAY_MS = 800;
const OOM_PROBABILITY = 0.15; // 15% szans na OOM
const ERROR_PROBABILITY = 0.1; // 10% szans na błąd
const MIN_RESPONSE_TIME_MS = 800;
const RESPONSE_TIME_RANGE_MS = 2000;
const MIN_TOKENS_PER_SEC = 10;
const TOKENS_PER_SEC_RANGE = 40;
const MIN_VRAM_MB = 2048;
const VRAM_RANGE_MB = 4096;

export default function BenchmarkPage() {
  const { data: modelsData, loading: modelsLoading } = useModels(15000);
  const [status, setStatus] = useState<BenchmarkStatus>("idle");
  const [logs, setLogs] = useState<BenchmarkLog[]>([]);
  const [results, setResults] = useState<BenchmarkModelResult[]>([]);

  const addLog = (message: string, level: BenchmarkLog["level"] = "info") => {
    setLogs((prev) => {
      const newLog: BenchmarkLog = {
        timestamp: new Date().toISOString(),
        message,
        level,
      };
      // Używamy concat zamiast spread dla lepszej wydajności
      return prev.concat(newLog);
    });
  };

  /**
   * Symulacja benchmarku - funkcja demonstracyjna
   *
   * Ta funkcja generuje losowe wyniki dla celów demonstracyjnych.
   * Używa stałych zdefiniowanych na górze pliku (SIMULATION_MODEL_LOAD_DELAY_MS,
   * SIMULATION_QUESTION_DELAY_MS, OOM_PROBABILITY, ERROR_PROBABILITY, itp.)
   * do kontrolowania symulacji.
   *
   * W finalnej implementacji będzie zastąpiona przez prawdziwe wywołania API:
   * - POST /api/v1/models/benchmark/start
   * - WebSocket/SSE dla live logów
   * - GET /api/v1/models/benchmark/{id}
   */
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

        // Symulacja opóźnienia ładowania (zastąpi prawdziwy czas ładowania modelu)
        await new Promise((resolve) => setTimeout(resolve, SIMULATION_MODEL_LOAD_DELAY_MS));

        addLog(`Model ${modelName} załadowany. Rozpoczynam generowanie odpowiedzi...`);

        // Symulacja testowania (zastąpi prawdziwe wywołania API do modelu)
        for (let q = 1; q <= config.num_questions; q++) {
          addLog(
            `  Generowanie odpowiedzi ${q}/${config.num_questions} dla ${modelName}...`
          );
          await new Promise((resolve) => setTimeout(resolve, SIMULATION_QUESTION_DELAY_MS));
        }

        // Symulacja wyników - losowe wartości dla demonstracji
        const isOOM = Math.random() < OOM_PROBABILITY;
        const isError = !isOOM && Math.random() < ERROR_PROBABILITY;

        const result: BenchmarkModelResult = {
          model_name: modelName,
          avg_response_time_ms: isOOM || isError ? 0 : MIN_RESPONSE_TIME_MS + Math.random() * RESPONSE_TIME_RANGE_MS,
          tokens_per_sec: isOOM || isError ? 0 : MIN_TOKENS_PER_SEC + Math.random() * TOKENS_PER_SEC_RANGE,
          max_vram_mb: MIN_VRAM_MB + Math.random() * VRAM_RANGE_MB,
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
      const errorMessage = error instanceof Error
        ? error.message
        : "Nieznany błąd podczas wykonywania benchmarku. Sprawdź logi systemu lub spróbuj ponownie.";
      addLog(`Błąd podczas benchmarku: ${errorMessage}`, "error");
      setStatus("failed");
    }
  };

  const handleStart = async (config: BenchmarkConfig) => {
    await runBenchmark(config);
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
      <SectionHeading
        as="h1"
        size="lg"
        eyebrow="Benchmark Control"
        title="Panel Benchmarkingu"
        description="Testuj wydajność modeli i porównaj ich parametry (czas odpowiedzi, tokens/sec, użycie VRAM)"
        rightSlot={<Gauge className="page-heading-icon" />}
      />

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
