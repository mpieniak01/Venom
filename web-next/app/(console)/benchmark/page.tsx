"use client";

import { useState } from "react";
import { Gauge, Code2, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Panel } from "@/components/ui/panel";
import { SectionHeading } from "@/components/ui/section-heading";
import { BenchmarkConfigurator } from "@/components/benchmark/benchmark-configurator";
import { BenchmarkConsole } from "@/components/benchmark/benchmark-console";
import { BenchmarkResults } from "@/components/benchmark/benchmark-results";
import { BenchmarkCodingConfigurator } from "@/components/benchmark/benchmark-coding-configurator";
import { BenchmarkCodingConsole } from "@/components/benchmark/benchmark-coding-console";
import { BenchmarkCodingResults } from "@/components/benchmark/benchmark-coding-results";
import { useModels } from "@/hooks/use-api";
import { useBenchmark } from "@/hooks/use-benchmark";
import { useCodingBenchmark } from "@/hooks/use-coding-benchmark";
import type { BenchmarkConfig, CodingBenchmarkStartRequest } from "@/lib/types";
import { useTranslation } from "@/lib/i18n";

type BenchmarkTab = "llmModels" | "codeModels" | "codeResults";

export default function BenchmarkPage() {
  const t = useTranslation();
  const [activeTab, setActiveTab] = useState<BenchmarkTab>("llmModels");
  const { data: modelsData, loading: modelsLoading } = useModels(15000);

  const {
    status,
    logs,
    results,
    startBenchmark,
  } = useBenchmark();

  const {
    status: codingStatus,
    run: codingRun,
    logs: codingLogs,
    startBenchmark: startCodingBenchmark,
    deleteRun,
    clearAllRuns,
  } = useCodingBenchmark();

  const handleStart = async (config: BenchmarkConfig) => {
    await startBenchmark(config);
  };

  const handleCodingStart = async (req: CodingBenchmarkStartRequest) => {
    await startCodingBenchmark(req);
  };

  const availableModels =
    modelsData?.models.map((model) => ({
      name: model.name || "unknown",
      provider: model.provider || "vllm",
    })) || [];

  const tabs: Array<{ id: BenchmarkTab; label: string; icon: React.ReactNode }> = [
    { id: "llmModels", label: t("benchmark.tabs.llmModels"), icon: <Gauge className="w-4 h-4" /> },
    { id: "codeModels", label: t("benchmark.tabs.codeModels"), icon: <Code2 className="w-4 h-4" /> },
    { id: "codeResults", label: t("benchmark.tabs.codeResults"), icon: <BarChart3 className="w-4 h-4" /> },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <SectionHeading
        as="h1"
        size="lg"
        eyebrow={t("benchmark.page.eyebrow")}
        title={t("benchmark.page.title")}
        description={t("benchmark.page.description")}
        rightSlot={<Gauge className="page-heading-icon" />}
      />

      {/* Tab switcher */}
      <div className="flex gap-1 rounded-xl bg-[color:var(--surface-muted)] border border-[color:var(--ui-border)] p-1 w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors",
              activeTab === tab.id
                ? "bg-[color:var(--ui-surface)] text-[color:var(--text-primary)] shadow-sm"
                : "text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)]",
            )}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab 1: LLM Models Benchmark */}
      {activeTab === "llmModels" && (
        <>
          <div className="grid gap-6 lg:grid-cols-2">
            <Panel
              eyebrow={t("benchmark.steps.config.eyebrow")}
              title={t("benchmark.steps.config.title")}
              description={t("benchmark.steps.config.description")}
            >
              {modelsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <div className="h-6 w-6 animate-spin rounded-full border-2 border-violet-500 border-t-transparent" />
                  <span className="ml-3 text-sm text-zinc-400">
                    {t("benchmark.loading")}
                  </span>
                </div>
              ) : (
                <BenchmarkConfigurator
                  availableModels={availableModels}
                  onStart={handleStart}
                  disabled={status === "running" || status === "pending"}
                />
              )}
            </Panel>

            <Panel
              eyebrow={t("benchmark.steps.console.eyebrow")}
              title={t("benchmark.steps.console.title")}
              description={t("benchmark.steps.console.description")}
            >
              <BenchmarkConsole logs={logs} isRunning={status === "running"} />
            </Panel>
          </div>

          <Panel
            eyebrow={t("benchmark.steps.results.eyebrow")}
            title={t("benchmark.steps.results.title")}
            description={t("benchmark.steps.results.description")}
          >
            <BenchmarkResults currentResults={results} />
          </Panel>
        </>
      )}

      {/* Tab 2: Code Models — start/status */}
      {activeTab === "codeModels" && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Panel
            eyebrow={t("benchmark.coding.config.eyebrow")}
            title={t("benchmark.coding.config.title")}
            description={t("benchmark.coding.config.description")}
          >
            {modelsLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-violet-500 border-t-transparent" />
                <span className="ml-3 text-sm text-zinc-400">
                  {t("benchmark.loading")}
                </span>
              </div>
            ) : (
              <BenchmarkCodingConfigurator
                availableModels={availableModels}
                onStart={handleCodingStart}
                disabled={codingStatus === "running" || codingStatus === "pending"}
              />
            )}
          </Panel>

          <Panel
            eyebrow={t("benchmark.coding.console.eyebrow")}
            title={t("benchmark.coding.console.title")}
            description={t("benchmark.coding.console.description")}
          >
            <BenchmarkCodingConsole
              logs={codingLogs}
              run={codingRun}
              isRunning={codingStatus === "running"}
            />
          </Panel>
        </div>
      )}

      {/* Tab 3: Code Results — history + table + charts */}
      {activeTab === "codeResults" && (
        <Panel
          eyebrow={t("benchmark.coding.results.eyebrow")}
          title={t("benchmark.coding.results.title")}
          description={t("benchmark.coding.results.description")}
        >
          <BenchmarkCodingResults
            currentRun={codingRun}
            onDelete={deleteRun}
            onClearAll={clearAllRuns}
          />
        </Panel>
      )}
    </div>
  );
}
