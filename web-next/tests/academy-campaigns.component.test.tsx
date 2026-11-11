import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CampaignPanel } from "../components/academy/campaign-panel";
import type { Campaign } from "../lib/academy-campaign-api";

const base = "/api/v1/academy/experiments";
const campaignsPath = `${base}/campaigns`;
const originalFetch = globalThis.fetch;
const originalFormData = globalThis.FormData;
const planHash = "a".repeat(64);
const retentionHash = "b".repeat(64);
const runId = "pilot-campaign-01";

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  globalThis.FormData = originalFormData;
});

const planned: Campaign = {
  campaign_id: "pilot-campaign",
  status: "planned",
  trial_index: 0,
  elapsed_seconds: 0,
  used_updates: 0,
  used_tokens: 0,
  retries: 0,
  artifact_bytes: 0,
  plan: {
    campaign_id: "pilot-campaign",
    profile_id: "omni",
    plan_sha256: planHash,
    variants: [{ run_id: runId, recipe: { rank: 8, learning_rate: 0.0002 }, workload: { updates: 4, tokens: 2000 } }],
    budget: {
      max_trials: 3, max_updates: 1000, max_tokens: 2000000, max_seconds: 3600,
      trial_seconds: 1200, max_retries: 0, max_artifact_bytes: 4096 * 1024 ** 2, min_free_bytes: 8192 * 1024 ** 2,
    },
    selection: { min_usable_delta: 0, max_critical_delta: 0 },
    retention: "keep_all",
    review_mode: "manual",
  },
  trials: [{ run_id: runId, status: "pending" }],
};

function serve(
  campaigns: () => Campaign[],
  handlers: Record<string, (init?: RequestInit) => Response> = {},
) {
  globalThis.fetch = async (input, init) => {
    const path = new URL(String(input), "http://localhost").pathname;
    const key = `${init?.method ?? "GET"} ${path}`;
    if (handlers[key]) return handlers[key](init);
    if (key === `GET ${base}/profiles`) {
      return Response.json({ profiles: [{ id: "omni", label: "Omni", model: "Omni", dataset: "pilot", recipe: { rank: 8 } }] });
    }
    if (key === `GET ${campaignsPath}`) return Response.json({ campaigns: campaigns() });
    throw new Error(`Unexpected request: ${key}`);
  };
}

describe("Academy campaigns", () => {
  it("creates a preview before starting exactly the approved plan", async () => {
    globalThis.FormData = window.FormData;
    let current: Campaign[] = [];
    let submitted: unknown;
    let started: unknown;
    serve(() => current, {
      [`POST ${campaignsPath}/plan`]: (init) => {
        submitted = JSON.parse(String(init?.body));
        current = [planned];
        return Response.json(planned);
      },
      [`POST ${campaignsPath}/pilot-campaign/start`]: (init) => {
        started = JSON.parse(String(init?.body));
        current = [{ ...planned, status: "running", trials: [{ run_id: runId, status: "running" }] }];
        return Response.json(current[0]);
      },
    });

    const opened: string[] = [];
    render(<CampaignPanel onOpenRun={(id) => opened.push(id)} />);
    fireEvent.change(await screen.findByLabelText("Identyfikator kampanii"), { target: { value: "pilot-campaign" } });
    fireEvent.click(screen.getByRole("button", { name: "Przygotuj plan kampanii" }));
    const start = await screen.findByRole("button", { name: "Uruchom zaplanowaną kampanię" });
    assert.equal(started, undefined);
    assert.deepEqual(submitted, {
      campaign_id: "pilot-campaign",
      profile_id: "omni",
      variants: [{}],
      budget: planned.plan.budget,
      selection: planned.plan.selection,
      retention: "keep_all",
      review_mode: "manual",
    });

    fireEvent.click(start);
    await screen.findByRole("button", { name: "Zatrzymaj kampanię" });
    assert.deepEqual(started, { plan_sha256: planHash });
    fireEvent.click(screen.getByRole("button", { name: runId }));
    assert.deepEqual(opened, [runId]);
  });

  it("binds removal to the reviewed file list", async () => {
    const complete = {
      ...planned,
      status: "succeeded",
      trial_index: 1,
      selected_run_id: "winner",
      plan: { ...planned.plan, retention: "discard_rejected" as const },
      trials: [{ run_id: runId, status: "succeeded", usable_delta: 0.125, critical_delta: 0 }],
    };
    let apply: unknown;
    serve(() => [complete], {
      [`GET ${campaignsPath}/pilot-campaign/retention`]: () => Response.json({
        campaign_id: "pilot-campaign",
        selected_run_id: "winner",
        files: [{ run_id: runId, path: "checkpoint-4/adapter.safetensors", size_bytes: 1048576, sha256: "c".repeat(64) }],
        bytes: 1048576,
        plan_sha256: retentionHash,
      }),
      [`POST ${campaignsPath}/pilot-campaign/retention`]: (init) => {
        apply = JSON.parse(String(init?.body));
        return Response.json({ removed_bytes: 1048576 });
      },
    });

    render(<CampaignPanel onOpenRun={() => {}} />);
    const preview = await screen.findByRole("button", { name: "Sprawdź pliki do usunięcia" });
    assert.equal(screen.queryByRole("button", { name: "Usuń wskazane pliki" }), null);
    fireEvent.click(preview);
    const button = await screen.findByRole("button", { name: "Usuń wskazane pliki" });
    assert.ok(screen.getByText(/checkpoint-4\/adapter\.safetensors/));
    assert.equal(apply, undefined);
    fireEvent.click(button);
    await waitFor(() => assert.deepEqual(apply, { plan_sha256: retentionHash }));
    await screen.findByText(/Zwolniono/);
  });
});
