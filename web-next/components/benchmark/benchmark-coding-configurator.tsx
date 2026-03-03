"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { CodingBenchmarkStartRequest } from "@/lib/types";
import { useTranslation } from "@/lib/i18n";

const AVAILABLE_TASKS = [
  { id: "python_sanity", key: "benchmark.coding.tasks.python_sanity" },
  { id: "python_simple", key: "benchmark.coding.tasks.python_simple" },
  { id: "python_complex", key: "benchmark.coding.tasks.python_complex" },
  { id: "python_complex_bugfix", key: "benchmark.coding.tasks.python_complex_bugfix" },
] as const;

interface BenchmarkCodingConfiguratorProps {
  readonly availableModels: ReadonlyArray<{ readonly name: string; readonly provider: string }>;
  readonly onStart: (req: CodingBenchmarkStartRequest) => void;
  readonly disabled?: boolean;
}

export function BenchmarkCodingConfigurator({
  availableModels,
  onStart,
  disabled = false,
}: BenchmarkCodingConfiguratorProps) {
  const t = useTranslation();
  const ollamaModels = availableModels.filter((m) => m.provider === "ollama");

  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [selectedTasks, setSelectedTasks] = useState<string[]>(["python_complex"]);
  const [loopTask, setLoopTask] = useState("python_complex_bugfix");
  const [timeout, setTimeout] = useState(180);
  const [maxRounds, setMaxRounds] = useState(3);
  const [stopOnFailure, setStopOnFailure] = useState(false);

  const toggleModel = (name: string) => {
    setSelectedModels((prev) =>
      prev.includes(name) ? prev.filter((m) => m !== name) : [...prev, name],
    );
  };

  const toggleTask = (id: string) => {
    setSelectedTasks((prev) =>
      prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id],
    );
  };

  const handleStart = () => {
    if (selectedModels.length === 0 || selectedTasks.length === 0) return;
    onStart({
      models: selectedModels,
      tasks: selectedTasks,
      loop_task: loopTask,
      first_sieve_task: "",
      timeout,
      max_rounds: maxRounds,
      stop_on_failure: stopOnFailure,
    });
  };

  const canStart = selectedModels.length > 0 && selectedTasks.length > 0 && !disabled;

  return (
    <div className="space-y-5">
      {/* Modele Ollama */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-[color:var(--text-secondary)] uppercase tracking-wider">
          {t("benchmark.coding.config.modelsLabel")}
        </p>
        {ollamaModels.length === 0 ? (
          <p className="text-xs text-[color:var(--ui-muted)]">
            {t("benchmark.coding.config.noModels")}
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {ollamaModels.map((model) => (
              <button
                key={model.name}
                onClick={() => toggleModel(model.name)}
                disabled={disabled}
                className={cn(
                  "px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border",
                  selectedModels.includes(model.name)
                    ? "bg-violet-500/20 border-violet-400/50 text-violet-300"
                    : "bg-[color:var(--surface-muted)] border-[color:var(--ui-border)] text-[color:var(--text-secondary)] hover:border-violet-400/30 hover:text-[color:var(--text-primary)]",
                  disabled && "opacity-50 cursor-not-allowed",
                )}
              >
                {model.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Zadania codingowe */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-[color:var(--text-secondary)] uppercase tracking-wider">
          {t("benchmark.coding.config.tasksLabel")}
        </p>
        <div className="flex flex-wrap gap-2">
          {AVAILABLE_TASKS.map((task) => (
            <button
              key={task.id}
              onClick={() => toggleTask(task.id)}
              disabled={disabled}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border",
                selectedTasks.includes(task.id)
                  ? "bg-emerald-500/20 border-emerald-400/50 text-emerald-300"
                  : "bg-[color:var(--surface-muted)] border-[color:var(--ui-border)] text-[color:var(--text-secondary)] hover:border-emerald-400/30 hover:text-[color:var(--text-primary)]",
                disabled && "opacity-50 cursor-not-allowed",
              )}
            >
              {t(task.key)}
            </button>
          ))}
        </div>
      </div>

      {/* Zadanie pętli */}
      <div className="space-y-2">
        <label
          htmlFor="coding-loop-task"
          className="text-xs font-medium text-[color:var(--text-secondary)] uppercase tracking-wider"
        >
          {t("benchmark.coding.config.loopTaskLabel")}
        </label>
        <select
          id="coding-loop-task"
          value={loopTask}
          onChange={(e) => setLoopTask(e.target.value)}
          disabled={disabled}
          className="w-full rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] px-3 py-2 text-xs text-[color:var(--text-primary)] focus:outline-none focus:border-violet-400/50 disabled:opacity-50"
        >
          <option value="">{t("benchmark.coding.config.loopTaskDisabled")}</option>
          {AVAILABLE_TASKS.map((task) => (
            <option key={task.id} value={task.id}>
              {t(task.key)}
            </option>
          ))}
        </select>
      </div>

      {/* Parametry */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <label htmlFor="coding-timeout" className="text-xs text-[color:var(--text-secondary)]">
            {t("benchmark.coding.config.timeoutLabel")}
          </label>
          <input
            id="coding-timeout"
            type="number"
            min={10}
            max={3600}
            value={timeout}
            onChange={(e) => setTimeout(Number(e.target.value))}
            disabled={disabled}
            className="w-full rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] px-3 py-2 text-xs text-[color:var(--text-primary)] focus:outline-none focus:border-violet-400/50 disabled:opacity-50"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="coding-max-rounds" className="text-xs text-[color:var(--text-secondary)]">
            {t("benchmark.coding.config.maxRoundsLabel")}
          </label>
          <input
            id="coding-max-rounds"
            type="number"
            min={1}
            max={20}
            value={maxRounds}
            onChange={(e) => setMaxRounds(Number(e.target.value))}
            disabled={disabled}
            className="w-full rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] px-3 py-2 text-xs text-[color:var(--text-primary)] focus:outline-none focus:border-violet-400/50 disabled:opacity-50"
          />
        </div>
      </div>

      {/* Stop on failure */}
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={stopOnFailure}
          onChange={(e) => setStopOnFailure(e.target.checked)}
          disabled={disabled}
          className="rounded border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] accent-violet-500 disabled:opacity-50"
        />
        <span className="text-xs text-[color:var(--text-secondary)]">
          {t("benchmark.coding.config.stopOnFailureLabel")}
        </span>
      </label>

      {/* Przycisk Start */}
      <Button
        onClick={handleStart}
        disabled={!canStart}
        className={cn("w-full", !canStart && "opacity-50 cursor-not-allowed")}
      >
        {disabled ? t("benchmark.coding.config.running") : t("benchmark.coding.config.start")}
      </Button>
    </div>
  );
}
