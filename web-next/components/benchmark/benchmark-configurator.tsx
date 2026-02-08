"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { BenchmarkConfig } from "@/lib/types";

interface BenchmarkConfiguratorProps {
  availableModels: { name: string; provider: string }[];
  onStart: (config: BenchmarkConfig) => void;
  disabled?: boolean;
}

export function BenchmarkConfigurator({
  availableModels,
  onStart,
  disabled = false,
}: BenchmarkConfiguratorProps) {
  const [runtime, setRuntime] = useState<"vllm" | "ollama">("vllm");
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

  const isValid = selectedModels.length > 0 && numQuestions > 0;

  return (
    <div className="space-y-4">
      {/* Runtime Selection */}
      <fieldset className="space-y-2 border-0 p-0 m-0">
        <legend className="mb-2 block text-sm font-medium text-zinc-300">Runtime</legend>
        <div className="flex gap-2" role="radiogroup" aria-label="Wybór runtime">
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
                : "border-white/10 bg-black/30 text-zinc-400 hover:bg-white/5",
              disabled && "cursor-not-allowed opacity-50"
            )}
          >
            vLLM
          </Button>
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
                : "border-white/10 bg-black/30 text-zinc-400 hover:bg-white/5",
              disabled && "cursor-not-allowed opacity-50"
            )}
          >
            Ollama
          </Button>
        </div>
      </fieldset>

      {/* Models Multi-Select */}
      <div>
        <p className="mb-2 block text-sm font-medium text-zinc-300">
          Modele do testowania
          {" "}
          <span className="ml-2 text-xs text-zinc-500">
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
                      : "border-white/5 bg-black/20 hover:border-white/20",
                    disabled && "cursor-not-allowed opacity-50"
                  )}
                >
                  <input
                    id={checkboxId}
                    type="checkbox"
                    checked={selectedModels.includes(model.name)}
                    onChange={() => handleModelToggle(model.name)}
                    disabled={disabled}
                    className="h-4 w-4 rounded border-white/20 bg-black/50 text-violet-500 focus:ring-violet-500/50"
                  />
                  <span className="flex-1 text-sm text-zinc-200">
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
          className="mb-2 block text-sm font-medium text-zinc-300"
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
          className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-2 text-sm text-white outline-none transition focus:border-violet-400 disabled:cursor-not-allowed disabled:opacity-50"
        />
        <p className="mt-1 text-xs text-zinc-500">
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
