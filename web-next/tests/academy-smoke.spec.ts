import { expect, test } from "@playwright/test";
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
    default_base_model: "unsloth/Phi-3-mini-4k-instruct",
  },
};

test.describe("Academy smoke", () => {
  const host = process.env.PLAYWRIGHT_HOST ?? "127.0.0.1";
  const port = Number(process.env.PLAYWRIGHT_PORT ?? 3000);
  let selfLearningStartPayload: Record<string, unknown> | null = null;

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("venom-language", "pl");
    });

    let activated = false;
    const selfLearningRunId = "selflearn_20260211_120100";
    selfLearningStartPayload = null;
    let selfLearningRuns: Array<Record<string, unknown>> = [];

    const buildSelfLearningRun = (status: "pending" | "running" | "completed") => ({
      run_id: selfLearningRunId,
      status,
      mode: "rag_index",
      sources: ["docs"],
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
      artifacts: {
        index_manifest: "data/academy/self_learning/selflearn_20260211_120100/index_manifest.jsonl",
      },
      logs: [
        "Discovering files for selected sources...",
        "Indexing chunks into vector store...",
        status === "completed" ? "Self-learning run completed successfully." : "Self-learning run in progress.",
      ],
      error_message: null,
    });

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
          runtimes: [],
          model_catalog: {
            all_models: [],
            chat_models: [],
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

    await page.route("**/api/v1/academy/self-learning/capabilities", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          trainable_models: [
            {
              model_id: "unsloth/Phi-3-mini-4k-instruct",
              label: "Phi-3 Mini 4K (Unsloth)",
              provider: "unsloth",
              recommended: true,
              runtime_compatibility: {
                vllm: true,
                ollama: false,
                onnx: false,
              },
              recommended_runtime: "vllm",
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
          default_base_model: "unsloth/Phi-3-mini-4k-instruct",
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
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            adapter_id: "training_20260211_120000",
            adapter_path: "./data/models/training_20260211_120000/adapter",
            base_model: "unsloth/Phi-3-mini-4k-instruct",
            created_at: "2026-02-11T12:05:00",
            training_params: {
              num_epochs: 3,
            },
            is_active: activated,
          },
        ]),
      });
    });

    await page.route("**/api/v1/academy/adapters/activate", async (route) => {
      activated = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          message: "Adapter activated",
        }),
      });
    });

    await page.route("**/api/v1/academy/adapters/deactivate", async (route) => {
      activated = false;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          message: "Adapter deactivated",
        }),
      });
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
      selfLearningRuns = [buildSelfLearningRun("running")];
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
      selfLearningRuns = [buildSelfLearningRun("completed")];
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

  });

  test("status + start training + activate adapter flow", async ({ page }) => {
    await page.goto(buildHttpUrl(host, port, "/academy"));

    await expect(
      page.getByRole("heading", { name: /Model Training & Fine-tuning|Trening i Dostrajanie Modeli/i }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Trening" }).click();
    await expect(page.getByRole("heading", { name: "Trening Modelu" })).toBeVisible();

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

    await expect(page.getByText("selflearn")).toBeVisible();
    await expect(page.getByText("Zakończony").first()).toBeVisible();
    expect(selfLearningStartPayload).not.toBeNull();
    expect((selfLearningStartPayload?.sources as string[]) ?? []).toEqual(["docs"]);
    const ragConfig = (selfLearningStartPayload?.rag_config as Record<string, unknown>) ?? {};
    expect(ragConfig.embedding_profile_id).toBe("local:default");
    expect(ragConfig.embedding_policy).toBe("strict");
  });
});
