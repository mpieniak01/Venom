import assert from "node:assert/strict";
import { afterEach, describe, it, mock } from "node:test";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";

import type { SelfLearningRunStatus } from "../lib/academy-api";
import { LanguageProvider } from "../lib/i18n";
import {
  SelfLearningConfigurator,
  type SelfLearningConfig,
} from "../components/academy/self-learning-configurator";
import { SelfLearningHistory } from "../components/academy/self-learning-history";

afterEach(() => {
  cleanup();
});

function renderWithLanguage(children: ReactNode) {
  return render(<LanguageProvider>{children}</LanguageProvider>);
}

function makeRun(overrides: Partial<SelfLearningRunStatus>): SelfLearningRunStatus {
  return {
    run_id: "aaaaaaaa-0000-0000-0000-000000000000",
    status: "running",
    mode: "rag_index",
    sources: ["docs"],
    created_at: "2026-03-04T10:00:00+00:00",
    started_at: "2026-03-04T10:00:01+00:00",
    finished_at: null,
    progress: {
      files_discovered: 10,
      files_processed: 3,
      chunks_created: 12,
      records_created: 12,
      indexed_vectors: 6,
    },
    artifacts: {},
    logs: [],
    error_message: null,
    ...overrides,
  };
}

function firstCallArg<T>(fn: { mock: { calls: Array<{ arguments: unknown[] }> } }): T {
  const call = fn.mock.calls[0];
  assert.ok(call);
  return call.arguments[0] as T;
}

function selectSelfLearningBaseModel(modelId: string) {
  fireEvent.click(
    screen.getByRole("button", {
      name: /Training base model|Model bazowy treningu|Trainings-Basismodell/i,
    }),
  );
  fireEvent.click(screen.getByText(modelId));
}

describe("SelfLearningConfigurator", () => {
  it("disables start button when no source is selected", async () => {
    const onStart = mock.fn(async () => {});
    renderWithLanguage(
      <SelfLearningConfigurator
        loading={false}
        runtimeOptions={[{ id: "ollama", label: "ollama" }]}
        selectedRuntime="ollama"
        onRuntimeChange={() => {}}
        trainableModels={[
          {
            model_id: "qwen2.5-coder:3b",
            label: "qwen2.5-coder:3b",
            provider: "ollama",
            recommended: true,
            runtime_compatibility: { ollama: true },
            recommended_runtime: "ollama",
          },
        ]}
        embeddingProfiles={[
          {
            profile_id: "local:default",
            provider: "local",
            model: "sentence-transformers/all-MiniLM-L6-v2",
            dimension: 384,
            healthy: true,
            fallback_active: false,
            details: {},
          },
        ]}
        onStart={onStart}
      />
    );

    const startButton = screen.getByRole("button", { name: /Start Self-Learning/i });
    assert.equal((startButton as HTMLButtonElement).disabled, false);

    fireEvent.click(screen.getByText(/Repository docs/i));

    assert.equal((startButton as HTMLButtonElement).disabled, true);
  });

  it("submits selected mode, dry-run and limits", async () => {
    const onStart = mock.fn(async () => {});
    renderWithLanguage(
      <SelfLearningConfigurator
        loading={false}
        runtimeOptions={[{ id: "ollama", label: "ollama" }]}
        selectedRuntime="ollama"
        onRuntimeChange={() => {}}
        trainableModels={[
          {
            model_id: "qwen2.5-coder:3b",
            label: "qwen2.5-coder:3b",
            provider: "ollama",
            recommended: true,
            runtime_compatibility: { ollama: true },
            recommended_runtime: "ollama",
          },
        ]}
        embeddingProfiles={[
          {
            profile_id: "local:default",
            provider: "local",
            model: "sentence-transformers/all-MiniLM-L6-v2",
            dimension: 384,
            healthy: true,
            fallback_active: false,
            details: {},
          },
        ]}
        onStart={onStart}
      />
    );

    fireEvent.click(screen.getByText(/LLM Fine-tune/i));
    selectSelfLearningBaseModel("qwen2.5-coder:3b");
    fireEvent.click(screen.getByText(/Dry run/i));

    fireEvent.change(screen.getByLabelText(/Max file size/i), { target: { value: "512" } });
    fireEvent.change(screen.getByLabelText(/Max files/i), { target: { value: "123" } });
    fireEvent.change(screen.getByLabelText(/Max total size/i), { target: { value: "42" } });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Start Self-Learning/i }));
    });

    assert.equal(onStart.mock.callCount(), 1);
    const payload = firstCallArg<SelfLearningConfig>(onStart);
    assert.equal(payload.mode, "llm_finetune");
    assert.equal(payload.dry_run, true);
    assert.equal(payload.limits.max_file_size_kb, 512);
    assert.equal(payload.limits.max_files, 123);
    assert.equal(payload.limits.max_total_size_mb, 42);
    assert.deepEqual(payload.sources, ["docs"]);
    assert.equal(payload.llm_config?.base_model, "qwen2.5-coder:3b");
    assert.equal(payload.llm_config?.dataset_strategy, "reconstruct");
    assert.equal(payload.llm_config?.task_mix_preset, "balanced");
  });

  it("submits selected dataset strategy and task mix for llm mode", async () => {
    const onStart = mock.fn(async () => {});
    renderWithLanguage(
      <SelfLearningConfigurator
        loading={false}
        runtimeOptions={[{ id: "ollama", label: "ollama" }]}
        selectedRuntime="ollama"
        onRuntimeChange={() => {}}
        trainableModels={[
          {
            model_id: "qwen2.5-coder:3b",
            label: "qwen2.5-coder:3b",
            provider: "ollama",
            recommended: true,
            runtime_compatibility: { ollama: true },
            recommended_runtime: "ollama",
          },
        ]}
        embeddingProfiles={[]}
        onStart={onStart}
      />
    );

    fireEvent.click(screen.getByText(/LLM Fine-tune/i));
    selectSelfLearningBaseModel("qwen2.5-coder:3b");
    fireEvent.change(screen.getByLabelText(/Dataset strategy/i), {
      target: { value: "repo_tasks_basic" },
    });
    fireEvent.change(screen.getByLabelText(/Task mix preset/i), {
      target: { value: "repair-heavy" },
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Start Self-Learning/i }));
    });

    const payload = firstCallArg<SelfLearningConfig>(onStart);
    assert.equal(payload.llm_config?.dataset_strategy, "repo_tasks_basic");
    assert.equal(payload.llm_config?.task_mix_preset, "repair-heavy");
  });

  it("blocks llm start until base model is selected explicitly", async () => {
    const onStart = mock.fn(async () => {});
    renderWithLanguage(
      <SelfLearningConfigurator
        loading={false}
        runtimeOptions={[{ id: "ollama", label: "ollama" }]}
        selectedRuntime="ollama"
        onRuntimeChange={() => {}}
        trainableModels={[
          {
            model_id: "qwen2.5-coder:3b",
            label: "qwen2.5-coder:3b",
            provider: "ollama",
            recommended: true,
            runtime_compatibility: { ollama: true },
            recommended_runtime: "ollama",
          },
        ]}
        embeddingProfiles={[]}
        onStart={onStart}
      />
    );

    fireEvent.click(screen.getByText(/LLM Fine-tune/i));

    assert.equal(
      screen.getByText(/LLM fine-tune requires an explicit base model selection/i) instanceof HTMLElement,
      true,
    );

    const startButton = screen.getByRole("button", { name: /Start Self-Learning/i });
    assert.equal((startButton as HTMLButtonElement).disabled, true);

    await act(async () => {
      fireEvent.click(startButton);
    });

    assert.equal(onStart.mock.callCount(), 0);
  });

  it("shows runtime-family warning and blocks llm start when selected runtime has no compatible model", async () => {
    const onStart = mock.fn(async () => {});
    renderWithLanguage(
      <SelfLearningConfigurator
        loading={false}
        runtimeOptions={[{ id: "ollama", label: "ollama" }]}
        selectedRuntime="ollama"
        onRuntimeChange={() => {}}
        trainableModels={[
          {
            model_id: "unsloth/Phi-3-mini-4k-instruct",
            label: "unsloth/Phi-3-mini-4k-instruct",
            provider: "unsloth",
            recommended: true,
            runtime_compatibility: { vllm: true, ollama: false },
            recommended_runtime: "vllm",
          },
        ]}
        embeddingProfiles={[]}
        onStart={onStart}
      />
    );

    fireEvent.click(screen.getByText(/LLM Fine-tune/i));

    const warnings = screen.getAllByText(
      /Selected runtime ollama has no compatible base model for self-learning/i,
    );
    assert.equal(warnings.length, 2);

    const startButton = screen.getByRole("button", { name: /Start Self-Learning/i });
    assert.equal((startButton as HTMLButtonElement).disabled, true);

    await act(async () => {
      fireEvent.click(startButton);
    });

    assert.equal(onStart.mock.callCount(), 0);
  });

  it("blocks rag start in strict policy when embedding fallback is active", async () => {
    const onStart = mock.fn(async () => {});
    renderWithLanguage(
      <SelfLearningConfigurator
        loading={false}
        runtimeOptions={[{ id: "vllm", label: "vllm" }]}
        selectedRuntime="vllm"
        onRuntimeChange={() => {}}
        trainableModels={[]}
        embeddingProfiles={[
          {
            profile_id: "local:default",
            provider: "local",
            model: "sentence-transformers/all-MiniLM-L6-v2",
            dimension: 384,
            healthy: true,
            fallback_active: true,
            details: {},
          },
        ]}
        onStart={onStart}
      />
    );

    const startButton = screen.getByRole("button", { name: /Start Self-Learning/i });
    assert.equal((startButton as HTMLButtonElement).disabled, true);

    fireEvent.change(screen.getByLabelText(/Embedding policy/i), {
      target: { value: "allow_fallback" },
    });

    assert.equal((startButton as HTMLButtonElement).disabled, false);
  });

  it("submits rag chunking and retrieval modes", async () => {
    const onStart = mock.fn(async () => {});
    renderWithLanguage(
      <SelfLearningConfigurator
        loading={false}
        runtimeOptions={[{ id: "vllm", label: "vllm" }]}
        selectedRuntime="vllm"
        onRuntimeChange={() => {}}
        trainableModels={[]}
        embeddingProfiles={[
          {
            profile_id: "local:default",
            provider: "local",
            model: "sentence-transformers/all-MiniLM-L6-v2",
            dimension: 384,
            healthy: true,
            fallback_active: false,
            details: {},
          },
        ]}
        onStart={onStart}
      />
    );

    fireEvent.change(screen.getByLabelText(/RAG chunking mode/i), {
      target: { value: "code_aware" },
    });
    fireEvent.change(screen.getByLabelText(/RAG retrieval mode/i), {
      target: { value: "hybrid" },
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Start Self-Learning/i }));
    });

    const payload = firstCallArg<SelfLearningConfig>(onStart);
    assert.equal(payload.rag_config?.chunking_mode, "code_aware");
    assert.equal(payload.rag_config?.retrieval_mode, "hybrid");
  });
});

describe("SelfLearningHistory", () => {
  it("selects run from history list and triggers callback", async () => {
    const runA = makeRun({
      run_id: "aaaaaaaa-0000-0000-0000-000000000000",
      progress: { files_discovered: 2, files_processed: 2, chunks_created: 4, records_created: 4, indexed_vectors: 4 },
      status: "completed",
      finished_at: "2026-03-04T10:01:00+00:00",
    });
    const runB = makeRun({
      run_id: "bbbbbbbb-0000-0000-0000-000000000000",
      status: "failed",
      progress: { files_discovered: 2, files_processed: 1, chunks_created: 2, records_created: 2, indexed_vectors: 0 },
      error_message: "Parsing failed",
    });

    const onSelectRun = mock.fn(() => {});
    const onRefresh = mock.fn(async () => {});
    const onDeleteRun = mock.fn(async () => {});
    const onClearAll = mock.fn(async () => {});

    renderWithLanguage(
      <SelfLearningHistory
        runs={[runA, runB]}
        selectedRunId={runA.run_id}
        onSelectRun={onSelectRun}
        onRefresh={onRefresh}
        onDeleteRun={onDeleteRun}
        onClearAll={onClearAll}
      />,
    );

    const runBButton = screen.getByRole("button", { name: /bbbbbbbb/i });
    await act(async () => {
      fireEvent.click(runBButton);
    });
    assert.equal(onSelectRun.mock.callCount(), 1);
    assert.equal(firstCallArg<string>(onSelectRun), runB.run_id);
  });

  it("renders selected run details and allows deleting selected run", async () => {
    const run = makeRun({
      run_id: "cccccccc-0000-0000-0000-000000000000",
      status: "completed_with_warnings",
      progress: { files_discovered: 8, files_processed: 8, chunks_created: 16, records_created: 16, indexed_vectors: 14 },
      artifacts: {
        repo_commit_sha: "0123456789abcdef0123456789abcdef01234567",
        knowledge_snapshot_at: "2026-03-04T10:00:00+00:00",
        knowledge_freshness: {
          indexed_at: "2026-03-04T10:05:00+00:00",
          mode: "indexed",
        },
        evaluation: {
          kind: "proxy_eval",
          score: 0.7421,
          decision: "promote",
        },
      },
      error_message: "Skipped binary files",
    });

    const onSelectRun = mock.fn(() => {});
    const onRefresh = mock.fn(async () => {});
    const onDeleteRun = mock.fn(async () => {});
    const onClearAll = mock.fn(async () => {});

    renderWithLanguage(
      <SelfLearningHistory
        runs={[run]}
        selectedRunId={run.run_id}
        onSelectRun={onSelectRun}
        onRefresh={onRefresh}
        onDeleteRun={onDeleteRun}
        onClearAll={onClearAll}
      />,
    );

    assert.ok(screen.getByText(run.run_id));
    assert.ok(screen.getByText(/Completed with warnings/i));
    assert.ok(screen.getByText(/Skipped binary files/i));
    assert.ok(screen.getByText(/Knowledge commit/i));
    assert.ok(screen.getByText(/0123456789ab/i));
    assert.ok(screen.getByText(/Index freshness/i));
    assert.ok(screen.getByText(/Eval score/i));
    assert.ok(screen.getByText(/0.7421/i));
    assert.ok(screen.getByText(/Promotion decision/i));
    assert.ok(screen.getByText(/Promote/i));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Delete run/i }));
    });
    assert.equal(onDeleteRun.mock.callCount(), 1);
    assert.equal(firstCallArg<string>(onDeleteRun), run.run_id);
  });
});
