import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { auditFixture, blockedAuditFixture } from "./fixtures/academy-data-audit";
import AcademyPage from "../app/(console)/academy/page";
import { CampaignPanel } from "../components/academy/campaign-panel";
import type { Campaign, CampaignRequest } from "../lib/academy-campaign-api";
import type { ExperimentInitialAdapter } from "../lib/academy-experiments-api";

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
  handlers: Record<string, (init?: RequestInit, url?: string) => Response> = {},
  optunaAvailable?: boolean,
) {
  globalThis.fetch = async (input, init) => {
    const path = new URL(String(input), "http://localhost").pathname;
    const key = `${init?.method ?? "GET"} ${path}`;
    if (handlers[key]) return handlers[key](init, String(input));
    if (key === `GET ${base}/profiles`) {
      return Response.json({ profiles: [{ id: "omni", label: "Omni", model: "Omni", dataset: "pilot", recipe: { rank: 8 } }] });
    }
    if (key === `GET ${base}/adapters`) return Response.json({ adapters: [] });
    if (key === `GET ${campaignsPath}/quality`) return Response.json({ records: [] });
    if (key === `GET ${campaignsPath}`) {
      return Response.json({
        campaigns: campaigns(),
        ...(optunaAvailable === undefined ? {} : { capabilities: { optuna: { available: optunaAvailable } } }),
      });
    }
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

  it("pins ordered checkpoint steps and shows the selected step or no candidate", async () => {
    globalThis.FormData = window.FormData;
    let current: Campaign[] = [];
    const requests: CampaignRequest[] = [];
    const record = { record_id: `checkpoint:${runId}:2`, split: "dev", source: { identity: runId } };
    const checkpointAnalysis = {
      record, decision: "GO", comparable: true, comparison_issues: [], summary: [],
      comparison: [], findings: [], protected_case_ids: [],
      proposal: { status: "insufficient_evidence", variants: [], reasons: [] },
    };
    const checkpoints = {
      ...planned,
      plan: { ...planned.plan, checkpoint_steps: [2, 4] },
    };
    serve(() => current, {
      [`GET ${campaignsPath}/quality`]: () => Response.json({ records: [] }),
      [`GET ${campaignsPath}/quality/${encodeURIComponent(record.record_id)}/analysis`]: () => Response.json(checkpointAnalysis),
      [`POST ${campaignsPath}/plan`]: (init) => {
        requests.push(JSON.parse(String(init?.body)) as CampaignRequest);
        current = [checkpoints];
        return Response.json(checkpoints);
      },
    });
    render(<CampaignPanel onOpenRun={() => {}} />);
    fireEvent.change(await screen.findByLabelText("Identyfikator kampanii"), { target: { value: planned.campaign_id } });
    const field = screen.getByLabelText("Kroki oceny checkpointów");
    const submit = screen.getByRole("button", { name: "Przygotuj plan kampanii" });
    fireEvent.change(field, { target: { value: "4, 2" } });
    fireEvent.click(submit);
    assert.ok(screen.getByRole("alert"));
    assert.equal(requests.length, 0);

    fireEvent.change(field, { target: { value: "2, 4" } });
    fireEvent.click(submit);
    await screen.findByText("Kroki oceny checkpointów · 2, 4");
    assert.deepEqual(requests[0]?.checkpoint_steps, [2, 4]);
    cleanup();

    const scored = {
      ...checkpoints,
      status: "succeeded",
      trials: [{
        run_id: runId,
        status: "succeeded",
        checkpoint_evaluations: [
          { step: 2, status: "succeeded", usable_delta: 0.25, critical_delta: 0, result_sha256: planHash },
          { step: 4, status: "succeeded", usable_delta: -0.25, critical_delta: 0.25 },
        ],
      }],
    };
    current = [{ ...scored, selected_run_id: runId, selected_checkpoint_step: 2 }];
    const historical = { ...record, record_id: "history:older", outcome: "REVISE" };
    serve(() => current, {
      [`GET ${campaignsPath}/quality`]: () => Response.json({ records: [historical, record] }),
      [`GET ${campaignsPath}/quality/${encodeURIComponent(historical.record_id)}/analysis`]: () =>
        Response.json({ ...checkpointAnalysis, record: historical, decision: "REVISE" }),
      [`GET ${campaignsPath}/quality/${encodeURIComponent(record.record_id)}/analysis`]: () => Response.json(checkpointAnalysis),
    });
    render(<CampaignPanel onOpenRun={() => {}} />);
    await screen.findByText(`Wybrany adapter ${runId} · Checkpoint w kroku 2`);
    assert.ok(screen.getByRole("row", { name: /Checkpoint w kroku 4.*-25/ }));
    assert.equal(screen.queryByRole("button", { name: "Pokaż wynik kroku 4" }), null);
    await screen.findByText(/REVISE · Wymaga poprawki/);
    fireEvent.click(screen.getByRole("button", { name: "Pokaż wynik kroku 2" }));
    await screen.findByText(/^GO ·/);
    assert.equal((screen.getByLabelText("Kandydat") as HTMLSelectElement).value, record.record_id);
    assert.equal(document.activeElement, screen.getByRole("heading", { name: "Wnioski i następna próba" }));
    cleanup();

    current = [scored];
    render(<CampaignPanel onOpenRun={() => {}} />);
    await screen.findByText("Żaden checkpoint nie spełnił warunków wyboru.");
  });

  it("inspects mix evidence, blocks rejected profiles, and reads the audit pinned to the plan", async () => {
    globalThis.FormData = window.FormData;
    let current: Campaign[] = [];
    const requests: CampaignRequest[] = [];
    const audit = auditFixture();
    const common = { model: "Omni", dataset: "pilot", recipe: { rank: 8 } };
    serve(() => current, {
      [`GET ${base}/profiles`]: () => Response.json({ profiles: [
        { ...common, id: "omni", label: "Audited", data_audit: audit },
        { ...common, id: "blocked", label: "Blocked", data_audit: blockedAuditFixture() },
        { ...common, id: "legacy", label: "Legacy" },
      ] }),
      [`POST ${campaignsPath}/plan`]: (init) => {
        requests.push(JSON.parse(String(init?.body)) as CampaignRequest);
        current = [{ ...planned, plan: { ...planned.plan, data_audit: audit } }];
        return Response.json(current[0]);
      },
      [`POST ${campaignsPath}/pilot-campaign/start`]: () => Response.json(
        { detail: { code: "experiment_data_audit_incompatible" } }, { status: 409 },
      ),
    });

    render(<CampaignPanel onOpenRun={() => {}} />);
    fireEvent.change(await screen.findByLabelText("Identyfikator kampanii"), { target: { value: "pilot-campaign" } });
    const profile = screen.getByLabelText("Profil eksperymentu");
    const planButton = screen.getByRole("button", { name: "Przygotuj plan kampanii" }) as HTMLButtonElement;
    fireEvent.click(screen.getByText("Audyt danych przeszedł"));
    assert.ok(screen.getByRole("row", { name: /Replay.*9 \/ 12.*40 \/ 100/ }));
    assert.ok(screen.getByRole("row", { name: /state_update.*9 \/ 40.*0 \/ 0/ }));

    fireEvent.change(profile, { target: { value: "blocked" } });
    assert.equal(planButton.disabled, true);
    assert.match(screen.getByRole("alert").textContent ?? "", /state_update.*9 \/ minimum 10/);
    fireEvent.submit(planButton.closest("form")!);
    assert.equal(requests.length, 0);
    fireEvent.change(profile, { target: { value: "legacy" } });
    assert.equal(planButton.disabled, false);
    assert.ok(screen.getByText("Brak przypiętego audytu danych."));

    fireEvent.change(profile, { target: { value: "omni" } });
    fireEvent.click(planButton);
    const start = await screen.findByRole("button", { name: "Uruchom zaplanowaną kampanię" });
    assert.equal(requests[0]?.profile_id, "omni");
    const setup = start.closest("section");
    assert.ok(setup?.textContent?.includes(audit.report_sha256));
    fireEvent.click(start);
    assert.match((await screen.findByRole("alert")).textContent ?? "", /Audyt nie pasuje do danych/);
  });

  it("keeps an adapter selection explicit across profile changes and pins it to the plan", async () => {
    globalThis.FormData = window.FormData;
    const adapter: ExperimentInitialAdapter = {
      adapter_id: "p13-145",
      label: "P13 checkpoint 145",
      model: "Omni",
      revision: "a".repeat(40),
      snapshot_sha256: "b".repeat(64),
      config_sha256: "c".repeat(64),
      weights_sha256: "d".repeat(64),
      source: { identity: "P13", sha256: "e".repeat(64) },
    };
    const pendingRun = "pilot-campaign-02";
    let current: Campaign[] = [];
    const requests: CampaignRequest[] = [];
    serve(() => current, {
      [`GET ${base}/profiles`]: () => Response.json({ profiles: [
        { id: "omni", label: "Omni", model: "Omni", dataset: "pilot", recipe: { rank: 8 } },
        { id: "other", label: "Other", model: "Other", dataset: "pilot", recipe: { rank: 8 } },
      ] }),
      [`GET ${base}/adapters`]: () => Response.json({ adapters: [adapter] }),
      [`POST ${campaignsPath}/plan`]: (init) => {
        requests.push(JSON.parse(String(init?.body)) as CampaignRequest);
        const variant = planned.plan.variants[0];
        const next = {
          ...planned,
          plan: { ...planned.plan, variants: [variant, { ...variant, run_id: pendingRun, initial_adapter: adapter }] },
          trials: [...planned.trials, { run_id: pendingRun, status: "pending" }],
        };
        current = [next];
        return Response.json(next);
      },
      [`POST ${campaignsPath}/pilot-campaign/start`]: () => Response.json(
        { detail: { code: "experiment_initial_adapter_changed" } }, { status: 409 },
      ),
    });

    render(<CampaignPanel onOpenRun={() => {}} />);
    fireEvent.change(await screen.findByLabelText("Identyfikator kampanii"), { target: { value: "pilot-campaign" } });
    fireEvent.click(screen.getByRole("button", { name: "Dodaj wariant" }));
    await screen.findAllByRole("option", { name: /P13 checkpoint 145/ });
    fireEvent.change(screen.getByLabelText("Źródło inicjalizacji 2"), { target: { value: adapter.adapter_id } });
    const profileSelector = screen.getByLabelText("Profil eksperymentu");
    fireEvent.change(profileSelector, { target: { value: "other" } });
    const planButton = screen.getByRole("button", { name: "Przygotuj plan kampanii" });
    fireEvent.click(planButton);
    assert.equal(requests.length, 0);
    assert.ok(screen.getByRole("alert"));
    fireEvent.change(profileSelector, { target: { value: "omni" } });
    fireEvent.click(planButton);

    const start = await screen.findByRole("button", { name: "Uruchom zaplanowaną kampanię" });
    assert.deepEqual(requests[0]?.variants, [{}, { initial_adapter_id: adapter.adapter_id }]);
    const row = screen.getByRole("row", { name: /pilot-campaign-02/ });
    assert.match(row.textContent ?? "", /P13 checkpoint 145/);
    assert.match(row.textContent ?? "", /dddddddddddd/);
    assert.match(screen.getByRole("row", { name: /^pilot-campaign-01/ }).textContent ?? "", /Nowa LoRA od modelu bazowego/);
    fireEvent.click(start);
    assert.match((await screen.findByRole("alert")).textContent ?? "", /Adapter startowy zmienił się/);
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

describe("Optuna campaigns", () => {
  const searchSpace = { learning_rate: { low: 0.0001, high: 0.001, log: true } };
  const optunaPlan: Campaign = {
    ...planned,
    plan: { ...planned.plan, strategy: "optuna", search_space: searchSpace, sampler_seed: 0 },
  };

  it("keeps a saved Optuna plan visible while the controller dependency is unavailable", async () => {
    serve(() => [optunaPlan], {}, false);
    render(<CampaignPanel onOpenRun={() => {}} />);

    const select = (await screen.findByLabelText("Strategia doboru parametrów")) as HTMLSelectElement;
    assert.equal(select.value, "fixed");
    assert.equal((screen.getByRole("option", { name: "Optuna" }) as HTMLOptionElement).disabled, true);
    assert.ok(screen.getByText("Optuna jest niedostępna w środowisku sterownika kampanii."));
    assert.ok(screen.getByText("Zapisane zakresy wyszukiwania Optuny"));
    const start = screen.getByRole("button", { name: "Uruchom zaplanowaną kampanię" }) as HTMLButtonElement;
    assert.equal(start.disabled, true);
  });

  it("approves saved search ranges and renders the sampled recipe and outcome", async () => {
    globalThis.FormData = window.FormData;
    let current: Campaign[] = [];
    let submitted: unknown;
    let started: unknown;
    serve(() => current, {
      [`POST ${campaignsPath}/plan`]: (init) => {
        submitted = JSON.parse(String(init?.body));
        current = [optunaPlan];
        return Response.json(optunaPlan);
      },
      [`POST ${campaignsPath}/pilot-campaign/start`]: (init) => {
        started = JSON.parse(String(init?.body));
        current = [{
          ...optunaPlan,
          status: "succeeded",
          trial_index: 1,
          selected_run_id: runId,
          trials: [
            {
              run_id: runId, status: "succeeded", optuna_trial_number: 0, optuna_trial_state: "COMPLETE",
              recipe: { rank: 8, alpha: 16, dropout: 0.05, learning_rate: 0.000437 },
              usable_delta: 0.125, critical_delta: 0,
            },
            {
              run_id: "duplicate-run", status: "skipped", optuna_trial_number: 1, optuna_trial_state: "FAIL",
              error: "campaign_duplicate_suggestion",
            },
          ],
        }];
        return Response.json(current[0]);
      },
    }, true);

    render(<CampaignPanel onOpenRun={() => {}} />);
    fireEvent.change(await screen.findByLabelText("Identyfikator kampanii"), { target: { value: "pilot-campaign" } });
    fireEvent.change(screen.getByLabelText("Strategia doboru parametrów"), { target: { value: "optuna" } });
    assert.equal(screen.queryByRole("button", { name: "Dodaj wariant" }), null);
    fireEvent.change(screen.getByLabelText("Tempo uczenia · minimum"), { target: { value: "0.0001" } });
    fireEvent.change(screen.getByLabelText("Tempo uczenia · maksimum"), { target: { value: "0.001" } });
    fireEvent.change(screen.getByLabelText("Ziarno samplera"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Przygotuj plan kampanii" }));

    const start = await screen.findByRole("button", { name: "Uruchom zaplanowaną kampanię" });
    assert.equal(started, undefined);
    assert.deepEqual(submitted, {
      campaign_id: "pilot-campaign",
      profile_id: "omni",
      strategy: "optuna",
      variants: [],
      search_space: searchSpace,
      sampler_seed: 0,
      budget: planned.plan.budget,
      selection: planned.plan.selection,
      retention: "keep_all",
      review_mode: "manual",
    });
    assert.ok(screen.getByText(/0,0001 – 0,001 · Skala logarytmiczna/));
    assert.equal(screen.queryByText("0,000437"), null);
    fireEvent.click(start);
    await screen.findByText("Próba Optuny 0 · Ocena zakończona");
    assert.deepEqual(started, { plan_sha256: planHash });
    assert.ok(screen.getByText("0,000437"));
    assert.ok(screen.getByText("Powtórzona konfiguracja"));
    assert.equal((screen.getByRole("button", { name: "duplicate-run" }) as HTMLButtonElement).disabled, true);
  });

  it("rejects a reversed range before submitting a campaign plan", async () => {
    globalThis.FormData = window.FormData;
    let calls = 0;
    serve(() => [], {
      [`POST ${campaignsPath}/plan`]: () => {
        calls += 1;
        return Response.json(optunaPlan);
      },
    }, true);

    render(<CampaignPanel onOpenRun={() => {}} />);
    fireEvent.change(await screen.findByLabelText("Identyfikator kampanii"), { target: { value: "pilot-campaign" } });
    fireEvent.change(screen.getByLabelText("Strategia doboru parametrów"), { target: { value: "optuna" } });
    fireEvent.change(screen.getByLabelText("Tempo uczenia · minimum"), { target: { value: "0.001" } });
    fireEvent.change(screen.getByLabelText("Tempo uczenia · maksimum"), { target: { value: "0.0001" } });
    fireEvent.click(screen.getByRole("button", { name: "Przygotuj plan kampanii" }));

    assert.match((await screen.findByRole("alert")).textContent ?? "", /granice/);
    assert.equal(calls, 0);
  });
});

it("opens the campaign from the operator link and identifies a missing one", async () => {
  const second = {
    ...planned,
    campaign_id: "operator-campaign",
    plan: { ...planned.plan, campaign_id: "operator-campaign", profile_id: "operator-profile" },
  };
  serve(() => [planned, second]);
  const first = render(<CampaignPanel initialCampaignId="operator-campaign" onOpenRun={() => {}} />);
  await screen.findByText("operator-profile");
  assert.equal(screen.queryByText("Brak kampanii o identyfikatorze"), null);
  first.unmount();

  render(<CampaignPanel initialCampaignId="missing-campaign" onOpenRun={() => {}} />);
  const missing = await screen.findByText("Brak kampanii o identyfikatorze");
  assert.match(missing.textContent ?? "", /missing-campaign/);
  assert.equal(screen.queryByText("operator-profile"), null);
});


it("opens a different campaign when the Academy query changes", async () => {
  const second = {
    ...planned,
    campaign_id: "second-campaign",
    plan: { ...planned.plan, campaign_id: "second-campaign", profile_id: "second-profile" },
  };
  serve(() => [planned, second], {
    "GET /api/v1/academy/status": () => Response.json({ enabled: true }),
  });
  const view = render(await AcademyPage({
    searchParams: Promise.resolve({ campaign: planned.campaign_id }),
  }));
  await screen.findByText(planned.plan.profile_id, { selector: "dd" });
  view.rerender(await AcademyPage({
    searchParams: Promise.resolve({ campaign: second.campaign_id }),
  }));
  await screen.findByText("second-profile", { selector: "dd" });
  assert.equal(screen.queryByText(planned.plan.profile_id, { selector: "dd" }), null);
});

describe("Campaign quality feedback", () => {
  const qualityPath = campaignsPath + "/quality";
  const candidate = {
    record_id: "history:p14-candidate",
    split: "dev",
    source: { identity: "fixture" },
    evidence_gaps: ["quality_critical_unknown"],
  };
  const reference = { record_id: "history:p13-reference", split: "dev", source: { identity: "fixture" } };
  const trial = { rank: 8, steps: 128, max_tokens: 1024, microbatch: 1, gradient_accumulation_steps: 8, loss_mode: "supervised_token", gradient_checkpointing: true, gpu_allocator_reserve_mib: 1000, gpu_step_min_free_mib: 600 };
  const control = { ...trial, target_modules: ["q_proj", "v_proj"], loss_mode: "historic" };
  const isolated = { ...control, target_modules: ["q_proj", "k_proj", "v_proj", "o_proj", "in_proj", "out_proj", "w1", "w2", "w3"] };
  const sourceControls = { train_sha256: "d".repeat(64), runtime: { dtype: "bf16" } };
  const comparison = {
    record: candidate,
    decision: "REVISE",
    reference_id: reference.record_id,
    comparable: true,
    comparison_issues: [],
    summary: [],
    comparison: [{
      category: "instructions", n: 9, reference_usable: 6, candidate_usable: 5, lost_usable: 3, gained_usable: 2,
    }],
    findings: [{ code: "quality_lost_usable", case_ids: ["lost-1"] }],
    protected_case_ids: ["lost-1"],
    proposal: {
      status: "ready",
      kind: "isolate_recipe_factor",
      factor: "target_modules",
      reference_id: reference.record_id,
      fixed: sourceControls,
      variants: [
        { name: "control", recipe: control },
        { name: "isolated", recipe: isolated },
      ],
      reasons: [],
    },
  };

  it("compares paired outcomes and fills an editable draft without creating a campaign", async () => {
    globalThis.FormData = window.FormData;
    let current: Campaign[] = [];
    let submitted: unknown;
    let analysisUrl: string | undefined;
    serve(() => current, {
      ["GET " + qualityPath]: () => Response.json({
        records: [candidate, reference],
        unavailable_record_ids: ["history:unreadable"],
      }),
      ["GET " + qualityPath + "/" + encodeURIComponent(candidate.record_id) + "/analysis"]: (_init, url) => {
        analysisUrl = url;
        return Response.json(comparison);
      },
      ["POST " + campaignsPath + "/plan"]: (init) => {
        const body = JSON.parse(String(init?.body));
        submitted = body;
        const next = { ...planned, plan: { ...planned.plan, quality_policy: body.quality_policy } };
        current = [next];
        return Response.json(next);
      },
    });

    render(<CampaignPanel onOpenRun={() => {}} />);
    await screen.findByText(/REVISE · Wymaga poprawki/);
    assert.ok(analysisUrl?.endsWith("/analysis"));
    const candidateSelect = await screen.findByLabelText("Kandydat") as HTMLSelectElement;
    assert.equal(candidateSelect.value, candidate.record_id);
    assert.ok(screen.getByText("history:unreadable", { selector: "code" }));
    assert.equal(screen.queryByRole("option", { name: /history:unreadable/ }), null);
    fireEvent.change(screen.getByLabelText("Odniesienie"), { target: { value: reference.record_id } });
    await screen.findByText(/REVISE · Wymaga poprawki/);
    assert.ok(analysisUrl?.endsWith(encodeURIComponent(reference.record_id)));
    const row = screen.getByRole("row", { name: /instructions/ });
    assert.match(row.textContent ?? "", /instructions96532/);
    fireEvent.click(screen.getByRole("button", { name: "Uzupełnij formularz kampanii" }));
    assert.equal(submitted, undefined);
    const formPlan = screen.getByRole("button", { name: "Przygotuj plan kampanii" }) as HTMLButtonElement;
    assert.equal(formPlan.disabled, true);
    const draft = screen.getByLabelText("Parametry wariantu (JSON) 2") as HTMLTextAreaElement;
    assert.deepEqual(JSON.parse(draft.value), isolated);
    assert.ok(screen.getByText(/pola z rekomendacji/));
    const draftForm = formPlan.closest("form");
    assert.ok(draftForm?.textContent?.includes(candidate.record_id));
    assert.ok(draftForm?.textContent?.includes(sourceControls.train_sha256));
    assert.ok(draftForm?.textContent?.includes("bf16"));
    const qualityToggle = screen.getByRole("checkbox", { name: "Stosuj reguły jakości" }) as HTMLInputElement;
    assert.equal(qualityToggle.checked, true);
    assert.equal(qualityToggle.disabled, true);

    fireEvent.change(screen.getByLabelText("Profil eksperymentu"), { target: { value: "omni" } });
    fireEvent.change(screen.getByLabelText("Identyfikator kampanii"), { target: { value: "pilot-campaign" } });
    fireEvent.click(formPlan);
    await screen.findByText("Sprawdź JSON wariantów, pola trenera i limity kampanii.");
    assert.equal(submitted, undefined);

    fireEvent.change(screen.getByLabelText("Parametry wariantu (JSON) 1"), {
      target: { value: JSON.stringify({ ...trial, target_modules: control.target_modules }) },
    });
    fireEvent.change(draft, { target: { value: JSON.stringify({ ...trial, target_modules: isolated.target_modules }) } });
    fireEvent.change(screen.getByLabelText("Hipoteza"), { target: { value: "Porównanie szerszego zakresu z kontrolą." } });
    fireEvent.click(formPlan);
    await screen.findByRole("button", { name: "Uruchom zaplanowaną kampanię" });
    assert.deepEqual(submitted, {
      campaign_id: "pilot-campaign",
      profile_id: "omni",
      variants: [{ ...trial, target_modules: control.target_modules }, { ...trial, target_modules: isolated.target_modules }],
      budget: { ...planned.plan.budget, max_tokens: 2_097_152 },
      selection: planned.plan.selection,
      retention: "keep_all",
      review_mode: "manual",
      quality_policy: {
        hypothesis: "Porównanie szerszego zakresu z kontrolą.",
        source_record_id: candidate.record_id,
        reference_record_ids: [reference.record_id],
        protected_case_ids: ["lost-1"],
        protect_reference_hits: true,
        protect_base_hits: false,
        min_category_usable_delta: {},
        no_new_critical: true,
      },
    });

    fireEvent.click(screen.getByRole("button", { name: "Odrzuć szkic z rekomendacji" }));
    assert.equal(screen.queryByLabelText("Parametry wariantu (JSON) 1"), null);
    const standardForm = screen.getByRole("button", { name: "Przygotuj plan kampanii" }).closest("form");
    assert.equal(standardForm?.textContent?.includes(candidate.record_id), false);
  });

  it("preserves edited quality values while temporarily disabling the policy", async () => {
    serve(() => [], {
      ["GET " + qualityPath]: () => Response.json({ records: [reference] }),
    });
    render(<CampaignPanel onOpenRun={() => {}} />);
    await screen.findByLabelText("Profil eksperymentu");
    fireEvent.click(screen.getByText("Reguły jakości"));
    const toggle = screen.getByRole("checkbox", { name: "Stosuj reguły jakości" });
    fireEvent.click(toggle);
    const hypothesis = await screen.findByLabelText("Hipoteza") as HTMLTextAreaElement;
    const protectedIds = screen.getByLabelText("Chronione przypadki") as HTMLTextAreaElement;
    const referenceInput = await screen.findByRole("checkbox", { name: reference.record_id }) as HTMLInputElement;
    fireEvent.change(hypothesis, { target: { value: "Chronimy dotychczasowe trafienia." } });
    fireEvent.change(protectedIds, { target: { value: "protected-1" } });
    fireEvent.click(referenceInput);
    fireEvent.click(toggle);
    const policyFields = hypothesis.closest("fieldset");
    assert.equal(policyFields?.hidden, true);
    assert.equal(policyFields?.disabled, true);
    fireEvent.click(toggle);
    assert.equal(hypothesis.value, "Chronimy dotychczasowe trafienia.");
    assert.equal(protectedIds.value, "protected-1");
    assert.equal(referenceInput.checked, true);
    assert.equal(policyFields?.hidden, false);
  });

  it("offers to reassess a blocked result after the time budget expires", async () => {
    const expired: Campaign = {
      ...planned,
      status: "blocked",
      elapsed_seconds: planned.plan.budget.max_seconds,
      trials: [{ run_id: runId, status: "succeeded" }],
    };
    const guarded: Campaign = {
      ...expired,
      trials: [{
        ...expired.trials[0],
        quality_guard: {
          status: "blocked",
          reasons: [{ code: "campaign_quality_case_evidence_missing" }],
          protected_count: null,
          lost_case_ids: [],
          new_critical_case_ids: [],
          category_deltas: {},
        },
      }],
    };
    const unguarded = { ...expired, campaign_id: "expired-no-guard" };
    let resumed = false;
    serve(() => [unguarded, guarded], {
      ["POST " + campaignsPath + "/pilot-campaign/resume"]: () => {
        resumed = true;
        return Response.json({ ...guarded, status: "stopping" });
      },
    });

    render(<CampaignPanel onOpenRun={() => {}} />);
    const unguardedButton = await screen.findByRole("button", { name: /expired-no-guard/ });
    fireEvent.click(unguardedButton);
    assert.equal(screen.queryByRole("button", { name: "Wznów kampanię" }), null);

    fireEvent.click(screen.getByRole("button", { name: /^pilot-campaignZablokowana$/ }));
    fireEvent.click(screen.getByRole("button", { name: "Wznów kampanię" }));
    await waitFor(() => assert.equal(resumed, true));
  });

  it("shows a trial rejection and keeps an unknown category threshold unquantified", async () => {
    serve(() => [{
      ...planned,
      status: "succeeded",
      trial_index: 1,
      trials: [{
        run_id: runId,
        status: "succeeded",
        quality_guard: {
          status: "rejected",
          reasons: [{ code: "protected_case_lost", count: 1 }],
          protected_count: 2,
          lost_case_ids: ["lost-1"],
          new_critical_case_ids: [],
          category_deltas: { instructions: { n: 4, usable_delta: -0.25, minimum: null } },
        },
      }],
    }]);

    render(<CampaignPanel onOpenRun={() => {}} />);
    fireEvent.click(await screen.findByText("Reguły jakości odrzuciły próbę"));
    assert.ok(screen.getByText(/Utracone chronione przypadki · lost-1/));
    assert.ok(screen.getByText("instructions · -25 / — p.p."));
  });
});
