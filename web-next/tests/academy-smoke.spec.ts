import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import type { Campaign, CampaignRequest } from "../lib/academy-campaign-api";
import { buildHttpUrl } from "./utils/url";

const academyStatusPayload = {
  enabled: true,
  components: {
    professor: true,
    dataset_curator: true,
    gpu_habitat: true,
    lessons_store: true,
    model_manager: true,
  },
  gpu: {
    available: false,
    enabled: false,
  },
  lessons: {
    total_lessons: 42,
  },
  jobs: {
    total: 1,
    running: 1,
    finished: 0,
    failed: 0,
  },
  config: {
    min_lessons: 100,
    training_interval_hours: 24,
  },
};

async function clickSelectOptionByTestId(page: Page, testId: string) {
  await page.getByTestId(testId).evaluate((element) => {
    (element as HTMLButtonElement).click();
  });
}

function buildSelfLearningRun(
  runId: string,
  status: "pending" | "running" | "completed",
  mode: "rag_index" | "llm_finetune" = "rag_index",
) {
  return {
    run_id: runId,
    status,
    mode,
    sources: mode === "llm_finetune" ? ["repo_readmes"] : ["docs"],
    created_at: "2026-02-11T12:01:00+00:00",
    started_at: "2026-02-11T12:01:02+00:00",
    finished_at: status === "completed" ? "2026-02-11T12:01:08+00:00" : null,
    progress: {
      files_discovered: 4,
      files_processed: status === "completed" ? 4 : 2,
      chunks_created: status === "completed" ? 8 : 3,
      records_created: status === "completed" ? 8 : 3,
      indexed_vectors: status === "completed" ? 8 : 3,
    },
    artifacts:
      mode === "llm_finetune"
        ? {
            adapter_path: `data/models/self_learning_${runId}/adapter`,
          }
        : {
            index_manifest:
              `data/academy/self_learning/${runId}/index_manifest.jsonl`,
          },
    logs: [
      "Discovering files for selected sources...",
      mode === "llm_finetune"
        ? "Preparing fine-tuning dataset..."
        : "Indexing chunks into vector store...",
      status === "completed"
        ? "Self-learning run completed successfully."
        : "Self-learning run in progress.",
    ],
    error_message: null,
  };
}

test.describe("Academy smoke", () => {
  const host = process.env.PLAYWRIGHT_HOST ?? "127.0.0.1";
  const port = Number(process.env.PLAYWRIGHT_PORT ?? 3000);
  const selfLearningRunId = "selflearn_20260211_120100";
  const selfLearningAdapterId = `self_learning_${selfLearningRunId}`;
  let selfLearningStartPayload: Record<string, unknown> | null = null;
  let selfLearningRuns: Array<Record<string, unknown>> = [];

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("venom-language", "pl");
    });

    let activeAdapterId: string | null = null;
    selfLearningStartPayload = null;
    selfLearningRuns = [];

    await page.route("**/api/v1/academy/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(academyStatusPayload),
      });
    });

    await page.route("**/api/v1/academy/jobs**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          count: 1,
          jobs: [
            {
              job_id: "training_20260211_120000",
              job_name: "training_20260211_120000",
              dataset_path: "./data/training/dataset_123.jsonl",
              base_model: "unsloth/Phi-3-mini-4k-instruct",
              parameters: {
                num_epochs: 3,
                lora_rank: 16,
                learning_rate: 0.0002,
                batch_size: 4,
              },
              status: "running",
              started_at: "2026-02-11T12:00:00",
            },
          ],
        }),
      });
    });

    const buildTrainingAdapter = () => ({
        adapter_id: "training_20260211_120000",
        adapter_path: "./data/models/training_20260211_120000/adapter",
        base_model: "gemma-3-4b-it",
        canonical_base_model_id: "gemma-3-4b-it",
        is_active: activeAdapterId === "training_20260211_120000",
        compatible_runtimes: ["ollama"],
      });
    const buildSelfLearningAdapter = () => ({
      adapter_id: selfLearningAdapterId,
      adapter_path: `data/models/${selfLearningAdapterId}/adapter`,
      base_model: "gemma-3-4b-it",
      canonical_base_model_id: "gemma-3-4b-it",
      is_active: activeAdapterId === selfLearningAdapterId,
      compatible_runtimes: ["ollama"],
    });
    const listAvailableAdapters = () => {
      const adapters = [buildTrainingAdapter()];
      const hasCompletedSelfLearningAdapter = selfLearningRuns.some(
        (run) => run.run_id === selfLearningRunId && run.mode === "llm_finetune" && run.status === "completed",
      );
      if (hasCompletedSelfLearningAdapter) {
        adapters.unshift(buildSelfLearningAdapter());
      }
      return adapters;
    };

    await page.route("**/api/v1/system/llm-runtime/options", async (route) => {
      const academyAdapters = listAvailableAdapters();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "success",
          active: {
            runtime_id: "ollama",
            active_server: "ollama",
            active_model: "gemma3:latest",
            active_endpoint: "http://127.0.0.1:11434/v1",
            config_hash: "test-hash",
            source_type: "local-runtime",
          },
          runtimes: [
            {
              runtime_id: "ollama",
              source_type: "local-runtime",
              configured: true,
              available: true,
              status: "online",
              reason: null,
              active: true,
              adapter_deploy_supported: true,
              adapter_deploy_mode: "ollama_modelfile",
              supports_native_training: false,
              supports_adapter_import_safetensors: true,
              supports_adapter_import_gguf: true,
              supports_adapter_runtime_apply: true,
              models: [
                {
                  id: "gemma3:latest",
                  name: "gemma3:latest",
                  provider: "ollama",
                  runtime_id: "ollama",
                  source_type: "local-runtime",
                  active: true,
                  chat_compatible: true,
                  canonical_model_id: "gemma-3-4b-it",
                },
              ],
            },
          ],
          model_catalog: {
            all_models: [],
            chat_models: [
              {
                id: "gemma3:latest",
                name: "gemma3:latest",
                provider: "ollama",
                runtime_id: "ollama",
                source_type: "local-runtime",
                active: true,
                chat_compatible: true,
              },
            ],
            coding_models: [],
            trainable_models: [
              {
                model_id: "gemma-3-4b-it",
                label: "gemma-3-4b-it",
                provider: "vllm",
                trainable: true,
                recommended: true,
                installed_local: true,
                source_type: "local",
                cost_tier: "free",
                priority_bucket: 0,
                runtime_compatibility: {
                  vllm: true,
                  ollama: true,
                  onnx: false,
                },
                recommended_runtime: "ollama",
              },
              {
                model_id: "unsloth/Phi-3-mini-4k-instruct",
                label: "Phi-3 Mini 4K (Unsloth)",
                provider: "unsloth",
                trainable: true,
                recommended: false,
                installed_local: true,
                source_type: "local",
                cost_tier: "free",
                priority_bucket: 1,
                runtime_compatibility: {
                  vllm: true,
                  ollama: true,
                  onnx: false,
                },
                recommended_runtime: "ollama",
              },
            ],
          },
          adapter_catalog: {
            all_adapters: academyAdapters,
            by_runtime: {
              ollama: academyAdapters,
            },
            by_runtime_model: {
              ollama: {
                "gemma-3-4b-it": academyAdapters,
                "gemma3:latest": academyAdapters,
                "gemma3": academyAdapters,
                "google/gemma-3-4b-it": academyAdapters,
                "unsloth/gemma-3-4b-it": academyAdapters,
              },
            },
          },
          selector_flow: ["server", "model", "adapter"],
          feedback_loop: {
            requested_alias: "OpenCodeInterpreter-Qwen2.5-7B",
            primary: "qwen2.5-coder:7b",
            fallbacks: ["qwen2.5-coder:3b", "codestral:latest"],
            active_tier: "fallback",
            active_ready: true,
            active_resolved_model_id: "qwen2.5-coder:3b",
          },
        }),
      });
    });

    await page.route("**/api/v1/system/llm-servers/active", async (route) => {
      const method = route.request().method();
      if (method === "GET" || method === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "success",
            active_server: "ollama",
            active_model: "gemma3:latest",
            active_endpoint: "http://127.0.0.1:11434/v1",
            config_hash: "test-hash",
            runtime_id: "ollama",
            last_models: {
              ollama: "gemma3:latest",
            },
          }),
        });
        return;
      }
      await route.fallback();
    });

    await page.route("**/api/v1/academy/self-learning/capabilities", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          trainable_models: [
            {
              model_id: "gemma-3-4b-it",
              label: "gemma-3-4b-it",
              provider: "vllm",
              recommended: true,
              runtime_compatibility: {
                vllm: true,
                ollama: true,
                onnx: false,
              },
              recommended_runtime: "ollama",
            },
            {
              model_id: "unsloth/Phi-3-mini-4k-instruct",
              label: "Phi-3 Mini 4K (Unsloth)",
              provider: "unsloth",
              recommended: false,
              runtime_compatibility: {
                vllm: true,
                ollama: true,
                onnx: false,
              },
              recommended_runtime: "ollama",
            },
          ],
          embedding_profiles: [
            {
              profile_id: "local:default",
              provider: "local",
              model: "sentence-transformers/all-MiniLM-L6-v2",
              dimension: 384,
              healthy: true,
              fallback_active: false,
              details: {},
            },
          ],
          default_embedding_profile_id: "local:default",
        }),
      });
    });

    await page.route("**/api/v1/academy/train", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            success: true,
            job_id: "training_20260211_120000",
            message: "Training started",
            parameters: {
              num_epochs: 3,
              lora_rank: 16,
            },
          }),
        });
        return;
      }
      await route.fallback();
    });

    await page.route("**/api/v1/academy/adapters", async (route) => {
      const adapters = [
        {
          adapter_id: "training_20260211_120000",
          adapter_path: "./data/models/training_20260211_120000/adapter",
          base_model: "gemma-3-4b-it",
          created_at: "2026-02-11T12:05:00",
          training_params: {
            num_epochs: 3,
          },
          target_runtime: "ollama",
          source_flow: "training",
          metadata_status: "canonical",
          is_active: activeAdapterId === "training_20260211_120000",
        },
      ];
      const hasCompletedSelfLearningAdapter = selfLearningRuns.some(
        (run) => run.run_id === selfLearningRunId && run.mode === "llm_finetune" && run.status === "completed",
      );
      if (hasCompletedSelfLearningAdapter) {
        adapters.unshift({
          adapter_id: selfLearningAdapterId,
          adapter_path: `data/models/${selfLearningAdapterId}/adapter`,
          base_model: "gemma-3-4b-it",
          created_at: "2026-02-11T12:01:08+00:00",
          training_params: {
            num_epochs: 2,
          },
          target_runtime: "ollama",
          source_flow: "self_learning",
          metadata_status: "canonical",
          is_active: activeAdapterId === selfLearningAdapterId,
        });
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(adapters),
      });
    });

    await page.route("**/api/v1/academy/adapters/audit**", async (route) => {
      const adapters = listAvailableAdapters().map((adapter) => ({
        adapter_id: adapter.adapter_id,
        adapter_path: adapter.adapter_path,
        base_model: "gemma-3-4b-it",
        canonical_base_model: "gemma-3-4b-it",
        trusted_metadata: true,
        category: "compatible",
        reason_code: null,
        message: "Adapter metadata is consistent",
        is_active: adapter.is_active,
        sources: [],
        manual_repair_hint: null,
      }));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          count: adapters.length,
          adapters,
          summary: {
            compatible: adapters.length,
            blocked_unknown_base: 0,
            blocked_mismatch: 0,
          },
          runtime_id: "ollama",
          model_id: "gemma3:latest",
        }),
      });
    });

    await page.route("**/api/v1/academy/adapters/activate", async (route) => {
      const payload = (await route.request().postDataJSON()) as Record<string, string>;
      activeAdapterId = payload.adapter_id ?? null;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          message: "Adapter activated",
          runtime_id: "ollama",
          chat_model:
            activeAdapterId === selfLearningAdapterId
              ? `venom-adapter-${selfLearningAdapterId}`
              : "venom-adapter-training_20260211_120000",
          deployed: true,
        }),
      });
    });

    await page.route("**/api/v1/academy/adapters/*/sign", async (route) => {
      const path = new URL(route.request().url()).pathname;
      const adapterId = decodeURIComponent(path.split("/").slice(-2)[0] || "unknown");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          adapter_id: adapterId,
          signature: {
            adapter_id: adapterId,
            runtime_id: "ollama",
            model_id: "gemma3:latest",
            signer: "academy-ui",
          },
        }),
      });
    });

    await page.route("**/api/v1/academy/adapters/deactivate", async (route) => {
      activeAdapterId = null;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          message: "Adapter deactivated",
        }),
      });
    });

    await page.route("**/api/v1/academy/self-learning/evaluation/baseline", async (route) => {
      const baseline = {
        repo_qa_accuracy: 0.7,
        code_localization_accuracy: 0.7,
        fix_success_rate: 0.6,
        hallucination_rate_max: 0.1,
      };
      await route.fulfill({ json: { llm_finetune: baseline, rag_index: baseline } });
    });

    await page.route("**/api/v1/academy/self-learning/list**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          runs: selfLearningRuns,
          count: selfLearningRuns.length,
        }),
      });
    });

    await page.route("**/api/v1/academy/self-learning/start", async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }

      selfLearningStartPayload = (await route.request().postDataJSON()) as Record<string, unknown>;
      const requestedMode =
        ((selfLearningStartPayload?.mode as string | undefined) === "llm_finetune"
          ? "llm_finetune"
          : "rag_index");
      selfLearningRuns = [buildSelfLearningRun(selfLearningRunId, "running", requestedMode)];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          run_id: selfLearningRunId,
          message: "Self-learning run started",
        }),
      });
    });

    await page.route("**/api/v1/academy/self-learning/*/status", async (route) => {
      const mode =
        ((selfLearningStartPayload?.mode as string | undefined) === "llm_finetune"
          ? "llm_finetune"
          : "rag_index");
      selfLearningRuns = [buildSelfLearningRun(selfLearningRunId, "completed", mode)];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(selfLearningRuns[0]),
      });
    });

    await page.route("**/api/v1/academy/self-learning/all", async (route) => {
      if (route.request().method() !== "DELETE") {
        await route.fallback();
        return;
      }
      selfLearningRuns = [];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          message: "Cleared",
          count: 0,
        }),
      });
    });

    await page.route("**/api/v1/academy/self-learning/*", async (route) => {
      if (route.request().method() !== "DELETE") {
        await route.fallback();
        return;
      }
      if (route.request().url().endsWith("/all")) {
        await route.fallback();
        return;
      }
      selfLearningRuns = [];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          message: "Deleted",
          count: 1,
        }),
      });
    });

    await page.route("**/api/v1/tasks", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: "[]",
        });
        return;
      }
      await route.fallback();
    });

    await page.route("**/api/v1/llm/simple/stream", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body:
          'event: content\ndata: {"text": "Venom "}\n\n' +
          'event: content\ndata: {"text": "to framework AI."}\n\n' +
          "event: done\ndata: {}\n\n",
      });
    });

  });

  for (const strategy of ["fixed", "optuna"] as const) {
    test("plans and starts an Omni campaign with " + strategy + " strategy", async ({ page }) => {
      const optuna = strategy === "optuna";
      const api = "**/api/v1/academy/experiments";
      const campaigns = `${api}/campaigns`;
      const campaignId = "omni-e2e-" + strategy;
      const runId = `${campaignId}-01`;
      const profile = {
        id: "polski-czat",
        label: "Polski czat Omni",
        model: "LiquidAI/LFM3-Omni-2B",
        dataset: "Polskie dialogi dev",
        recipe: { rank: 4, alpha: 8, learning_rate: 0.0002 },
        automatic_review: false,
      };
      const planSha256 = "a".repeat(64);
      const space = {
        rank: { low: 4, high: 8, log: false },
        learning_rate: { low: 0.0001, high: 0.001, log: true },
      };
      const sampled = { rank: 6, alpha: 8, learning_rate: 0.000437, dropout: 0.05 };
      const mock: { current?: Campaign } = {};
      let planRequest: CampaignRequest | undefined;
      let startRequest: { plan_sha256: string } | undefined;

      // All experiment calls in this scenario are fixtures, including writes.
      await page.route(api + "/**", (route) => route.abort("blockedbyclient"));
      await page.route(`${api}/profiles`, (route) =>
        route.fulfill({ json: { profiles: [{ ...profile, id: "other-profile", label: "Drugi profil" }, profile] } }),
      );
      await page.route(campaigns, (route) =>
        route.fulfill({
          json: {
            campaigns: mock.current ? [mock.current] : [],
            capabilities: { optuna: { available: optuna } },
          },
        }),
      );
      await page.route(`${campaigns}/plan`, async (route) => {
        planRequest = route.request().postDataJSON() as CampaignRequest;
        mock.current = {
          campaign_id: campaignId,
          plan: {
            ...planRequest,
            plan_sha256: planSha256,
            variants: [
              {
                run_id: runId,
                recipe: { ...profile.recipe, ...planRequest.variants[0] },
                workload: { updates: 8, tokens: 8192 },
              },
            ],
          },
          status: "planned",
          trial_index: 0,
          trials: [{ run_id: runId, status: "pending" }],
          elapsed_seconds: 0,
          used_updates: 0,
          used_tokens: 0,
          retries: 0,
          artifact_bytes: 0,
        };
        await route.fulfill({ json: mock.current });
      });
      await page.route(`${campaigns}/${campaignId}/start`, async (route) => {
        startRequest = route.request().postDataJSON() as { plan_sha256: string };
        if (!mock.current) throw new Error("Campaign plan has not been created");
        mock.current = {
          ...mock.current,
          status: "running",
          trials: [{
            run_id: runId,
            status: "running",
            ...(optuna ? { recipe: sampled, optuna_trial_number: 0, optuna_trial_state: "RUNNING" as const } : {}),
          }],
        };
        await route.fulfill({ json: mock.current });
      });

      await page.goto(buildHttpUrl(host, port, "/academy"));
      await page.getByRole("button", { name: "Trening", exact: true }).click();
      await page.getByRole("button", { name: "Kampania", exact: true }).click();
      await page.locator("#campaign-profile").selectOption(profile.id);
      await page.getByLabel("Identyfikator kampanii").fill(campaignId);
      const strategyInput = page.getByLabel("Strategia doboru parametrów");
      await expect(strategyInput).toHaveValue("fixed");
      if (optuna) {
        await strategyInput.selectOption("optuna");
        await expect(page.getByRole("button", { name: "Dodaj wariant" })).toBeHidden();
        await page.getByRole("checkbox", { name: "Ranga LoRA", exact: true }).check();
        await page.getByLabel("Ranga LoRA · minimum").fill("4");
        await page.getByLabel("Ranga LoRA · maksimum").fill("8");
        await page.getByLabel("Tempo uczenia · minimum").fill("0.0001");
        await page.getByLabel("Tempo uczenia · maksimum").fill("0.001");
        await page.getByLabel("Ziarno samplera").fill("0");
      } else {
        await expect(strategyInput.locator('option[value="optuna"]')).toBeDisabled();
        await expect(page.getByText("Optuna jest niedostępna w środowisku sterownika kampanii.")).toBeVisible();
        await page.locator("#variant-0-rank").fill("6");
      }
      await page.getByRole("button", { name: "Przygotuj plan kampanii" }).click();
      const start = page.getByRole("button", { name: "Uruchom zaplanowaną kampanię" });
      await expect(start).toBeEnabled();
      expect(planRequest).toMatchObject({ campaign_id: campaignId, profile_id: profile.id, review_mode: "manual" });
      expect(startRequest).toBeUndefined();
      if (optuna) {
        expect(planRequest).toMatchObject({ strategy: "optuna", variants: [], search_space: space, sampler_seed: 0 });
        await expect(page.getByRole("heading", { name: "Zapisane zakresy wyszukiwania Optuny" })).toBeVisible();
        await expect(page.getByText("4 – 8 · Skala liniowa")).toBeVisible();
        await expect(page.getByText("0,0001 – 0,001 · Skala logarytmiczna")).toBeVisible();
      } else {
        expect(planRequest?.strategy).toBeUndefined();
        expect(planRequest?.variants).toEqual([{ rank: 6 }]);
      }

      await start.click();
      await expect(page.getByRole("button", { name: "Zatrzymaj kampanię" })).toBeEnabled();
      expect(startRequest).toEqual({ plan_sha256: planSha256 });

      if (!mock.current) throw new Error("Campaign did not start");
      mock.current = {
        ...mock.current,
        status: "awaiting_review",
        trials: mock.current.trials.map((item) => ({ ...item, status: "awaiting_review" })),
      };
      const trial = page.getByRole("row").filter({ has: page.getByRole("button", { name: runId, exact: true }) });
      await expect(trial).toContainText("Oczekuje na ocenę");
      if (optuna) {
        await expect(trial).toContainText("Próba Optuny 0");
        await expect(trial).toContainText("0,000437");
        mock.current = {
          ...mock.current,
          status: "succeeded",
          selected_run_id: runId,
          trials: mock.current.trials.map((item) => ({
            ...item, status: "succeeded", optuna_trial_state: "COMPLETE", usable_delta: 0.125, critical_delta: 0,
          })),
        };
        await expect(trial).toContainText("Ocena zakończona");
        await expect(trial).toContainText("+12,5");
      }
    });
  }

  test("status + start training + activate adapter flow", async ({ page }) => {
    await page.goto(buildHttpUrl(host, port, "/academy"));

    await expect(
      page.getByRole("heading", { name: /Model Training & Fine-tuning|Trening i Dostrajanie Modeli/i }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Trening" }).click();
    await expect(page.getByRole("heading", { name: "Trening Modelu" })).toBeVisible();

    await page.getByTestId("academy-training-base-model-select").click();
    await clickSelectOptionByTestId(
      page,
      "academy-training-base-model-option-gemma-3-4b-it",
    );

    await page.getByRole("button", { name: "Start Training" }).click();
    await expect(page.getByText("training_20260211_120000")).toBeVisible();

    await page.getByRole("button", { name: "Adaptery" }).click();
    await expect(page.getByRole("heading", { name: "Adaptery LoRA" })).toBeVisible();

    await page.getByRole("button", { name: "Aktywuj" }).click();
    await expect(page.getByText("Aktywny").first()).toBeVisible();

    await page.getByRole("button", { name: "Samokształcenie" }).click();
    await expect(page.getByRole("heading", { name: "Samokształcenie" })).toBeVisible();

    await page.getByText("Dokumentacja developerska (/docs_dev)").click();
    await page.getByText("Kod źródłowy (venom_core, web-next, scripts)").click();
    await page.getByRole("button", { name: "Uruchom samokształcenie" }).click();

    await expect(page.getByText(selfLearningRunId.slice(0, 8), { exact: true })).toBeVisible();
    await expect(page.getByText("Zakończony").first()).toBeVisible();
    expect(selfLearningStartPayload).not.toBeNull();
    expect((selfLearningStartPayload?.sources as string[]) ?? []).toEqual([
      "docs",
      "docs_dev",
      "code",
    ]);
    const ragConfig = (selfLearningStartPayload?.rag_config as Record<string, unknown>) ?? {};
    expect(ragConfig.embedding_profile_id).toBe("local:default");
    expect(ragConfig.embedding_policy).toBe("strict");
  });

  test("activated adapter is visible in chat and serves prompt on selected runtime model", async ({
    page,
  }) => {
    await page.goto(buildHttpUrl(host, port, "/academy"));
    await page.getByRole("button", { name: "Adaptery" }).click();
    await expect(page.getByRole("heading", { name: "Adaptery LoRA" })).toBeVisible();

    await page.getByRole("button", { name: "Aktywuj" }).click();
    await expect(page.getByText("Aktywny").first()).toBeVisible();

    await page.goto(buildHttpUrl(host, port, "/chat"));
    await page.getByTestId("llm-model-select").click();
    await clickSelectOptionByTestId(page, "llm-model-option-gemma3:latest");
    await page.getByTestId("chat-adapter-select").click();
    await page
      .getByTestId("chat-adapter-option-training_20260211_120000")
      .evaluate((element) => {
        (element as HTMLButtonElement).click();
      });
    await expect(page.getByTestId("chat-adapter-select")).toContainText(
      "training_20260211_120000",
    );

    await page.getByTestId("chat-mode-select").click();
    await page.getByTestId("chat-mode-option-direct").click();

    await page.getByTestId("cockpit-prompt-input").fill("co to jest Venom");
    await page.getByTestId("cockpit-send-button").click();

    await expect(page.getByTestId("conversation-bubble-assistant").last()).toContainText(
      "Venom to framework AI.",
    );
  });

  test("training blocks ollama when no runtime-compatible model family is available", async ({
    page,
  }) => {
    await page.route("**/api/v1/system/llm-runtime/options", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "success",
          active: {
            runtime_id: "ollama",
            active_server: "ollama",
            active_model: "gemma3:latest",
            active_endpoint: "http://127.0.0.1:11434/v1",
            config_hash: "test-hash",
            source_type: "local-runtime",
          },
          runtimes: [
            {
              runtime_id: "ollama",
              source_type: "local-runtime",
              configured: true,
              available: true,
              status: "online",
              reason: null,
              active: true,
              adapter_deploy_supported: true,
              adapter_deploy_mode: "ollama_modelfile",
              supports_native_training: false,
              supports_adapter_import_safetensors: true,
              supports_adapter_import_gguf: true,
              supports_adapter_runtime_apply: true,
              models: [
                {
                  id: "gemma3:latest",
                  name: "gemma3:latest",
                  provider: "ollama",
                  runtime_id: "ollama",
                  source_type: "local-runtime",
                  active: true,
                  chat_compatible: true,
                  canonical_model_id: "gemma-3-4b-it",
                },
              ],
            },
          ],
          model_catalog: {
            all_models: [],
            chat_models: [
              {
                id: "gemma3:latest",
                name: "gemma3:latest",
                provider: "ollama",
                runtime_id: "ollama",
                source_type: "local-runtime",
                active: true,
                chat_compatible: true,
                canonical_model_id: "gemma-3-4b-it",
              },
            ],
            coding_models: [],
            trainable_models: [
              {
                model_id: "unsloth/Phi-3-mini-4k-instruct",
                label: "Phi-3 Mini 4K (Unsloth)",
                provider: "unsloth",
                trainable: true,
                recommended: true,
                installed_local: true,
                source_type: "local",
                cost_tier: "free",
                priority_bucket: 0,
                runtime_compatibility: {
                  vllm: true,
                  ollama: false,
                  onnx: false,
                },
                recommended_runtime: "vllm",
              },
            ],
          },
          adapter_catalog: {
            all_adapters: [],
            by_runtime: {
              ollama: [],
            },
            by_runtime_model: {
              ollama: {
                "gemma-3-4b-it": [],
              },
            },
          },
          selector_flow: ["server", "model", "adapter"],
        }),
      });
    });

    await page.goto(buildHttpUrl(host, port, "/academy"));
    await page.getByRole("button", { name: "Trening" }).click();
    await expect(page.getByRole("heading", { name: "Trening Modelu" })).toBeVisible();
    await expect(
      page.getByText(
        /Dla runtime Ollama nie ma teraz żadnego zgodnego modelu bazowego do treningu/i,
      ),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Start Training" }),
    ).toBeDisabled();
  });

  test("self-learning llm_finetune sends repo_readmes with runtime-compatible gemma model", async ({
    page,
  }) => {
    await page.route("**/api/v1/academy/self-learning/capabilities", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          trainable_models: [
            {
              model_id: "gemma-3-4b-it",
              label: "gemma-3-4b-it",
              provider: "ollama",
              recommended: true,
              runtime_compatibility: {
                vllm: false,
                ollama: true,
                onnx: false,
              },
              recommended_runtime: "ollama",
              installed_local: true,
            },
          ],
          embedding_profiles: [
            {
              profile_id: "local:default",
              provider: "local",
              model: "sentence-transformers/all-MiniLM-L6-v2",
              dimension: 384,
              healthy: true,
              fallback_active: false,
              details: {},
            },
          ],
          default_embedding_profile_id: "local:default",
        }),
      });
    });

    await page.route("**/api/v1/academy/self-learning/start", async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }

      selfLearningStartPayload = (await route.request().postDataJSON()) as Record<string, unknown>;
      selfLearningRuns = [buildSelfLearningRun(selfLearningRunId, "running", "llm_finetune")];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          run_id: selfLearningRunId,
          message: "Self-learning run started",
        }),
      });
    });

    await page.route("**/api/v1/academy/self-learning/*/status", async (route) => {
      selfLearningRuns = [buildSelfLearningRun(selfLearningRunId, "completed", "llm_finetune")];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(selfLearningRuns[0]),
      });
    });

    await page.goto(buildHttpUrl(host, port, "/academy"));
    await page.getByRole("button", { name: "Samokształcenie" }).click();
    await expect(page.getByRole("heading", { name: "Samokształcenie" })).toBeVisible();

    await page.getByText("Doszkalanie LLM").click();
    await page.getByTestId("academy-self-learning-base-model-select").click();
    await clickSelectOptionByTestId(
      page,
      "academy-self-learning-base-model-option-gemma-3-4b-it",
    );
    await page.getByText("Tylko README z root repo (/README.md, /README_PL.md)").click();
    await page.getByText("Dokumentacja repozytorium (/docs)").click();
    await page.getByRole("button", { name: "Uruchom samokształcenie" }).click();

    await expect(page.getByText(selfLearningRunId.slice(0, 8), { exact: true })).toBeVisible();
    await expect(page.getByText("Zakończony").first()).toBeVisible();
    expect(selfLearningStartPayload).not.toBeNull();
    expect(selfLearningStartPayload?.mode).toBe("llm_finetune");
    expect((selfLearningStartPayload?.sources as string[]) ?? []).toEqual(["repo_readmes"]);
    const llmConfig = (selfLearningStartPayload?.llm_config as Record<string, unknown>) ?? {};
    expect(llmConfig.runtime_id).toBe("ollama");
    expect(llmConfig.base_model).toBe("gemma-3-4b-it");
  });

  test("self-learning repo_readmes creates canonical adapter that can be activated and used in chat", async ({
    page,
  }) => {
    await page.route("**/api/v1/academy/self-learning/capabilities", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          trainable_models: [
            {
              model_id: "gemma-3-4b-it",
              label: "gemma-3-4b-it",
              provider: "ollama",
              recommended: true,
              runtime_compatibility: {
                vllm: false,
                ollama: true,
                onnx: false,
              },
              recommended_runtime: "ollama",
              installed_local: true,
            },
          ],
          embedding_profiles: [],
          default_embedding_profile_id: null,
        }),
      });
    });

    await page.goto(buildHttpUrl(host, port, "/academy"));
    await page.getByRole("button", { name: "Samokształcenie" }).click();
    await expect(page.getByRole("heading", { name: "Samokształcenie" })).toBeVisible();

    await page.getByText("Doszkalanie LLM").click();
    await page.getByTestId("academy-self-learning-base-model-select").click();
    await clickSelectOptionByTestId(
      page,
      "academy-self-learning-base-model-option-gemma-3-4b-it",
    );
    await page.getByText("Tylko README z root repo (/README.md, /README_PL.md)").click();
    await page.getByRole("button", { name: "Uruchom samokształcenie" }).click();

    await expect(page.getByText(selfLearningRunId.slice(0, 8), { exact: true })).toBeVisible();
    await expect(page.getByText("Zakończony").first()).toBeVisible();

    await page.getByRole("button", { name: "Adaptery" }).click();
    await expect(page.getByRole("heading", { name: "Adaptery LoRA" })).toBeVisible();
    await expect(page.getByText(selfLearningAdapterId, { exact: true })).toBeVisible();
    await expect(page.getByText("gemma-3-4b-it").first()).toBeVisible();
    await expect(page.getByText("ollama").first()).toBeVisible();
    await expect(
      page.getByText(`data/models/${selfLearningAdapterId}/adapter`, { exact: true }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Aktywuj" }).first().click();
    await expect(page.getByText("Aktywny").first()).toBeVisible();

    await page.goto(buildHttpUrl(host, port, "/chat"));
    await page.getByTestId("llm-model-select").click();
    await clickSelectOptionByTestId(page, "llm-model-option-gemma3:latest");
    await page.getByTestId("chat-adapter-select").click();
    await page
      .getByTestId(`chat-adapter-option-${selfLearningAdapterId}`)
      .evaluate((element) => {
        (element as HTMLButtonElement).click();
      });
    await expect(page.getByTestId("chat-adapter-select")).toContainText(
      selfLearningAdapterId,
    );

    await page.getByTestId("chat-mode-select").click();
    await page.getByTestId("chat-mode-option-direct").click();
    await page.getByTestId("cockpit-prompt-input").fill("co to jest Venom");
    await page.getByTestId("cockpit-send-button").click();

    await expect(page.getByTestId("conversation-bubble-assistant").last()).toContainText(
      "Venom to framework AI.",
    );
  });
});
