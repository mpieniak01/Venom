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

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("venom-language", "pl");
    });

    let activated = false;

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
  });

  test("status + start training + activate adapter flow", async ({ page }) => {
    await page.goto(buildHttpUrl(host, port, "/academy"));

    await expect(page.getByRole("heading", { name: /Model Training & Fine-tuning/i })).toBeVisible();

    await page.getByRole("button", { name: "Trening" }).click();
    await expect(page.getByRole("heading", { name: "Trening Modelu" })).toBeVisible();

    await page.getByRole("button", { name: "Start Training" }).click();
    await expect(page.getByText("training_20260211_120000")).toBeVisible();

    await page.getByRole("button", { name: "Adaptery" }).click();
    await expect(page.getByRole("heading", { name: "Adaptery LoRA" })).toBeVisible();

    await page.getByRole("button", { name: "Aktywuj" }).click();
    await expect(page.getByText("Aktywny").first()).toBeVisible();
  });
});
