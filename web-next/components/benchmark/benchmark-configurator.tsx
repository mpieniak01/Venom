"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { BenchmarkConfig } from "@/lib/types";

interface BenchmarkConfiguratorProps {
  readonly availableModels: ReadonlyArray<{ readonly name: string; readonly provider: string }>;
  readonly onStart: (config: BenchmarkConfig) => void;
  readonly disabled?: boolean;
}

export function BenchmarkConfigurator({
  availableModels,
  onStart,
  disabled = false,
}: BenchmarkConfiguratorProps) {
  const hasOllamaModels = availableModels.some((model) => model.provider === "ollama");
  const hasVllmModels = availableModels.some(
    (model) => model.provider === "vllm" || model.provider === "huggingface",
  );
  const availableRuntimes: Array<"vllm" | "ollama"> = [
    ...(hasOllamaModels ? (["ollama"] as const) : []),
    ...(hasVllmModels ? (["vllm"] as const) : []),
  ];
  const defaultRuntime: "vllm" | "ollama" = availableRuntimes.includes("ollama") ? "ollama" : "vllm";
  const [runtime, setRuntime] = useState<"vllm" | "ollama">(defaultRuntime);
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [numQuestions, setNumQuestions] = useState(5);

  // Filtruj modele według wybranego runtime
  const filteredModels = availableModels.filter((model) => {
    if (runtime === "ollama") {
      return model.provider === "ollama";
    }
    return model.provider === "vllm" || model.provider === "huggingface";
  });

  const handleModelToggle = (modelName: string) => {
    setSelectedModels((prev) =>
      prev.includes(modelName)
        ? prev.filter((m) => m !== modelName)
        : [...prev, modelName]
    );
  };

  const handleStart = () => {
    const config: BenchmarkConfig = {
      runtime,
      models: selectedModels,
      num_questions: numQuestions,
    };

    onStart(config);
  };

  const isValid = selectedModels.length > 0 && numQuestions > 0 && availableRuntimes.length > 0;

  return (
    <div className="space-y-4">
      {/* Runtime Selection */}
      <fieldset className="space-y-2 border-0 p-0 m-0">
        <legend className="mb-2 block text-sm font-medium text-[color:var(--text-secondary)]">Runtime</legend>
        <div className="flex gap-2" role="radiogroup" aria-label="Wybór runtime">
          {hasVllmModels && (
            <Button
              type="button"
              role="radio"
              aria-checked={runtime === "vllm"}
              onClick={() => {
                setRuntime("vllm");
                setSelectedModels([]);
              }}
              disabled={disabled}
              variant="outline"
              size="sm"
              className={cn(
                "flex-1 justify-center rounded-xl border px-4 py-2 text-sm font-medium transition",
                runtime === "vllm"
                  ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-200"
                  : "border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] text-[color:var(--text-secondary)] hover:bg-[color:var(--ui-surface)]",
                disabled && "cursor-not-allowed opacity-50"
              )}
            >
              vLLM
            </Button>
          )}
          {hasOllamaModels && (
            <Button
              type="button"
              role="radio"
              aria-checked={runtime === "ollama"}
              onClick={() => {
                setRuntime("ollama");
                setSelectedModels([]);
              }}
              disabled={disabled}
              variant="outline"
              size="sm"
              className={cn(
                "flex-1 justify-center rounded-xl border px-4 py-2 text-sm font-medium transition",
                runtime === "ollama"
                  ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-200"
                  : "border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] text-[color:var(--text-secondary)] hover:bg-[color:var(--ui-surface)]",
                disabled && "cursor-not-allowed opacity-50"
              )}
            >
              Ollama
            </Button>
          )}
        </div>
      </fieldset>

      {/* Models Multi-Select */}
      <div>
        <p className="mb-2 block text-sm font-medium text-[color:var(--text-secondary)]">
          Modele do testowania
          {" "}
          <span className="ml-2 text-xs text-[color:var(--ui-muted)]">
            ({selectedModels.length} wybrano)
          </span>
        </p>
        <div className="max-h-64 space-y-2 overflow-y-auto rounded-xl box-muted p-3">
          {filteredModels.length === 0 ? (
            <p className="text-sm text-zinc-500">
              Brak dostępnych modeli dla {runtime}
            </p>
          ) : (
            filteredModels.map((model) => {
              const checkboxId = `model-${model.name.replaceAll(/[^a-zA-Z0-9]/g, "-")}`;
              return (
                <label
                  key={model.name}
                  htmlFor={checkboxId}
                  className={cn(
                    "flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 transition",
                    selectedModels.includes(model.name)
                      ? "border-violet-500/40 bg-violet-500/10"
                      : "border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] hover:border-[color:var(--ui-border-strong)]",
                    disabled && "cursor-not-allowed opacity-50"
                  )}
                >
                  <input
                    id={checkboxId}
                    type="checkbox"
                    checked={selectedModels.includes(model.name)}
                    onChange={() => handleModelToggle(model.name)}
                    disabled={disabled}
                    className="h-4 w-4 rounded border-[color:var(--ui-border)] bg-[color:var(--bg-panel)] text-[color:var(--accent)] focus:ring-[color:var(--primary-glow)]"
                  />
                  <span className="flex-1 text-sm text-[color:var(--text-primary)]">
                    {model.name}
                  </span>
                </label>
              );
            })
          )}
        </div>
      </div>

      {/* Number of Questions */}
      <div>
        <label
          htmlFor="num-questions"
          className="mb-2 block text-sm font-medium text-[color:var(--text-secondary)]"
        >
          Liczba pytań testowych
        </label>
        <input
          id="num-questions"
          type="number"
          min="1"
          max="100"
          value={numQuestions}
          onChange={(e) => setNumQuestions(Math.min(100, Math.max(1, Number.parseInt(e.target.value, 10) || 1)))}
          disabled={disabled}
          className="w-full rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] px-4 py-2 text-sm text-[color:var(--text-primary)] outline-none transition focus:border-[color:var(--accent)] disabled:cursor-not-allowed disabled:opacity-50"
        />
        <p className="mt-1 text-xs text-hint">
          Im więcej pytań, tym dokładniejszy pomiar (zalecane: 5-20)
        </p>
      </div>

      {/* Start Button */}
      <Button
        onClick={handleStart}
        disabled={disabled || !isValid}
        variant="primary"
        className="w-full"
        size="md"
      >
        {disabled ? "Test w trakcie..." : "Uruchom Benchmark"}
      </Button>
    </div>
  );
}
