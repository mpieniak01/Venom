import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { auditFixture } from "./fixtures/academy-data-audit";
import { ExperimentReviewPanel } from "../components/academy/experiment-results";
import { ExperimentsPanel } from "../components/academy/experiments-panel";
import { TrainingWorkspace } from "../components/academy/training-workspace";
import { ToastProvider } from "../components/ui/toast";
import type { ExperimentProfile, ExperimentRun } from "../lib/academy-experiments-api";

const prefix = "/api/v1/academy/experiments";
const originalFetch = globalThis.fetch;
const originalFormData = globalThis.FormData;

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  globalThis.FormData = originalFormData;
});

const profile: ExperimentProfile = {
  id: "omni-pl",
  label: "Omni PL",
  model: "Omni",
  dataset: "pilot",
  recipe: { rank: 8, alpha: 16, learning_rate: 0.0002, target_modules: ["q_proj", "v_proj"] },
};
const run: ExperimentRun = {
  run_id: "pilot-1",
  profile_id: profile.id,
  status: "running",
  stage: "train",
  created_at: 1794398400,
  updated_at: 1794398460,
  attempt: 1,
  recipe: profile.recipe,
  resume_available: false,
};

function serve(
  runs: () => ExperimentRun[],
  handlers: Record<string, (init?: RequestInit) => Response | Promise<Response>> = {},
) {
  globalThis.fetch = async (input, init) => {
    const path = new URL(String(input), "http://localhost").pathname;
    const key = `${init?.method ?? "GET"} ${path}`;
    if (handlers[key]) return handlers[key](init);
    if (key === `GET ${prefix}/profiles`) return Response.json({ profiles: [profile] });
    if (key === `GET ${prefix}/model-specs`) return Response.json({ models: [{
      model: "LiquidAI/LFM3-Omni-2B", path: "academy_omni_experiment",
      status: "local_gpu_executor_available", loader: "AutoModelForMultimodalLM",
      revision: "snapshot_manifest_pinned", target_families: ["q_proj", "w1", "w2", "w3"],
      modality: "text_only_lora_on_multimodal_base",
      data_contract: "reviewed_pl_chat_jsonl_selected_assistant_turns",
      qualification: "snapshot_data_masks_targets_and_gpu_preflight_per_run",
      recipe_defaults: { rank: 4, max_tokens: 1024 },
      runtime: "local_cuda_bf16_no_cpu_fallback", gpu_memory: "measured_by_preflight_no_fixed_minimum",
    }] });
    if (key === `GET ${prefix}/runs`) return Response.json({ runs: runs() });
    throw new Error(`Unexpected request: ${key}`);
  };
}

describe("Academy experiments", () => {
  it("shows model training scope and warns when the selected profile omits MLP", async () => {
    serve(() => []);
    render(<ExperimentsPanel />);
    await screen.findByText("LiquidAI/LFM3-Omni-2B");
    assert.ok(screen.getByText(/Ten profil pomija warstwy MLP w1\/w2\/w3/));
    assert.ok(screen.getByText(/q_proj, w1, w2, w3/));
    assert.ok(screen.getByText(/rank=4 · max_tokens=1024/));
  });

  it("submits a profile and edited recipe, then stops the selected run", async () => {
    globalThis.FormData = window.FormData;
    let current: ExperimentRun[] = [];
    let submitted: unknown;
    serve(() => current, {
      [`POST ${prefix}/runs`]: (init) => {
        submitted = JSON.parse(String(init?.body));
        current = [run];
        return Response.json(run);
      },
      [`POST ${prefix}/runs/pilot-1/stop`]: () => {
        current = [{ ...run, status: "stopped", checkpoint_step: 3, resume_available: true }];
        return Response.json(current[0]);
      },
    });
    render(<ExperimentsPanel />);
    fireEvent.change(await screen.findByLabelText("Identyfikator przebiegu"), { target: { value: "pilot-1" } });
    fireEvent.change(screen.getByLabelText("Ranga LoRA"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Uruchom eksperyment" }));
    fireEvent.click(await screen.findByRole("button", { name: "Zatrzymaj" }));
    await waitFor(() => assert.equal((screen.getByRole("button", { name: "Wznów trening" }) as HTMLButtonElement).disabled, false));
    assert.deepEqual(submitted, { profile_id: "omni-pl", run_id: "pilot-1", recipe: { rank: 4 } });
  });

  it("shows anonymous answers before a review and hides the model identities", async () => {
    serve(() => [{ ...run, status: "awaiting_review", stage: "score" }], {
      [`GET ${prefix}/runs/pilot-1/review`]: () => Response.json({
        cases: [{ record_id: "case-1" }],
        answers: [{
          case: { record_id: "case-1" },
          answers: { A: { text: "Pierwsza odpowiedź" }, B: { text: "Druga odpowiedź" } },
        }],
      }),
    });
    render(<ExperimentsPanel />);
    await screen.findByText("Pierwsza odpowiedź");
    assert.ok(screen.getByText("Druga odpowiedź"));
    assert.equal(screen.queryByText("Baza M0"), null);
    assert.ok(screen.getByLabelText("Plik ocen JSON lub JSONL"));
  });



  it("warns about the fee and runs the judge only when an eligible dialogue opens", async () => {
    let requests = 0;
    const dialogue = { record_id: "dialogue-a" };
    const single = { record_id: "single-a" };
    serve(() => [], {
      [`GET ${prefix}/runs/pilot-1/review`]: () => Response.json({
        checkpoint_step: 4,
        dialogue_judge: { model: "deepseek", available: true, case_ids: [dialogue.record_id] },
        cases: [dialogue, single],
        answers: [dialogue, single].map((item) => ({
          case: item, answers: { A: { text: "Anonimowa odpowiedź" } },
        })),
      }),
      [`POST ${prefix}/runs/pilot-1/review/dialogue-judge`]: (init) => {
        requests += 1;
        assert.deepEqual(JSON.parse(String(init?.body)), { record_id: dialogue.record_id, checkpoint_step: 4 });
        return Response.json({ model: "deepseek", answers: {
          A: { cost_usd: "0.000051", verdict: { pass: true, critical: false, reason: "Spełnia kryteria." } },
        } });
      },
    });
    render(<ExperimentReviewPanel runId="pilot-1" disabled={false} onSubmit={async () => true} />);
    const notice = await screen.findByText(/nalicza opłatę według zużycia tokenów/);
    assert.ok(notice);
    assert.ok(screen.getByText("Płatna ocena DeepSeek"));
    assert.equal(requests, 0);
    const details = (id: string) => screen.getByText(id).closest("details") as HTMLDetailsElement;
    const toggle = (element: HTMLDetailsElement, open: boolean) => {
      element.open = open;
      fireEvent(element, new Event("toggle"));
    };
    toggle(details(single.record_id), true);
    assert.equal(requests, 0);
    toggle(details(dialogue.record_id), true);
    await screen.findByText("Spełnia kryteria.");
    assert.ok(screen.getByText(/Opłata OpenRouter/));
    toggle(details(dialogue.record_id), false);
    toggle(details(dialogue.record_id), true);
    assert.equal(requests, 1);
  });

  it("rejects a verdict file for an earlier checkpoint before posting", async () => {
    const submit = async (_rows: Record<string, unknown>[], step?: number) => {
      assert.equal(step, 4);
      count += 1;
      return true;
    };
    let count = 0;
    serve(() => [], {
      [`GET ${prefix}/runs/pilot-1/review`]: () => Response.json({
        checkpoint_step: 4,
        cases: [],
        answers: [],
      }),
    });
    const previousFormData = window.FormData;
    let file: File;
    class FileFormData extends previousFormData {
      get() { return file; }
    }
    globalThis.FormData = FileFormData;
    render(<ExperimentReviewPanel runId="pilot-1" disabled={false} onSubmit={submit} />);
    await screen.findByRole("heading", { name: /Checkpoint w kroku 4/ });
    const form = screen.getByRole("button", { name: "Prześlij oceny" }).closest("form")!;
    const judgments = [{ case: "case-1", label: "A" }];
    file = new File([JSON.stringify({ checkpoint_step: 2, judgments })], "old.json");
    fireEvent.submit(form);
    await screen.findByText("Nie udało się odczytać pliku ocen.");
    assert.equal(count, 0);

    file = new File([JSON.stringify({ checkpoint_step: 4, judgments })], "current.json");
    fireEvent.submit(form);
    await waitFor(() => assert.equal(count, 1));
    assert.equal(screen.queryByText("Nie udało się odczytać pliku ocen."), null);
  });

  it("opens the exact queued review and separates its external disposition from native scoring", async () => {
    const pending = { ...run, run_id: "pilot-awaiting", status: "awaiting_review", stage: "score",
      external_review: { record_id: "history:pilot", outcome: "REVISE" as const } };
    const record = { record_id: "history:pilot", split: "dev", source: { identity: "external evaluation" } };
    const qualityPath = `${prefix}/campaigns/quality`;
    serve(() => [run, pending], {
      "GET /api/v1/academy/jobs": () => Response.json({ jobs: [] }),
      "GET /api/v1/system/llm-runtime/options": () => Response.json({}),
      [`GET ${prefix}/campaigns`]: () => Response.json({ campaigns: [] }),
      [`GET ${qualityPath}`]: () => Response.json({ records: [{ ...record, record_id: "history:other" }, record] }),
      [`GET ${qualityPath}/${encodeURIComponent(record.record_id)}/analysis`]: () => Response.json({
        record, decision: "REVISE", comparable: true, comparison_issues: [],
        summary: [{ category: "total", n: 13, base_usable: 5, candidate_usable: 8, base_critical: null, candidate_critical: null }],
        comparison: [], findings: [], protected_case_ids: [],
        cohorts: [
          { category: "structured_retention", n: 8, base_usable: 3, candidate_usable: 6, base_critical: 2, candidate_critical: 0 },
          { category: "new_dialogue", n: 5, base_usable: 2, candidate_usable: 2, base_critical: null, candidate_critical: null },
        ],
        proposal: { status: "insufficient_evidence", variants: [], reasons: [] },
      }),
      [`GET ${prefix}/runs/pilot-awaiting/review`]: () => Response.json({
        cases: [{ record_id: "queued-case" }],
        answers: [{ case: { record_id: "queued-case" }, answers: { A: { text: "Anonimowa odpowiedź" } } }],
      }),
    });

    render(<ToastProvider><TrainingWorkspace /></ToastProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Eksperyment Omni" }));
    fireEvent.click(await screen.findByRole("button", { name: "Otwórz ocenę · pilot-awaiting" }));
    await screen.findByText("Anonimowa odpowiedź");
    const heading = screen.getByRole("heading", { name: "pilot-awaiting" });
    assert.equal(document.activeElement, heading);
    assert.ok(heading.parentElement?.textContent?.includes("Stan wykonania · Oczekuje na ocenę"));
    assert.ok(screen.getByText(/Decyzja z oceny zewnętrznej · Wymaga poprawki/));
    fireEvent.click(screen.getByRole("button", { name: "Pokaż ocenę zewnętrzną" }));
    await screen.findByText(/REVISE · Wymaga poprawki/);
    assert.equal((screen.getByLabelText("Kandydat") as HTMLSelectElement).value, record.record_id);
    assert.ok(screen.getByRole("row", { name: /Zachowanie wcześniejszych umiejętności.*2 \/ 8 → 0 \/ 8/ }));
    assert.ok(screen.getByRole("row", { name: /Nowe dialogi wieloturowe.*— → —/ }));
    fireEvent.click(screen.getByText("Szczegóły według kategorii"));
    const totals = screen.getByRole("row", { name: /Łącznie.*— → —/ }).closest("table");
    assert.ok(totals);
    assert.ok(within(totals).getByRole("columnheader", { name: "Błędy krytyczne" }));
  });

  it("keeps an imported aggregate report available without offering a native quality decision", async () => {
    const metric = { n: 3, semantic: 2, usable: 2, passed: 1, format: 3, critical: 0, runtime_or_length_failure: 1 };
    const summaries = { base: { total: metric }, candidate: { total: metric } };
    let finishReport: ((response: Response) => void) | undefined;
    const report = new Promise<Response>((resolve) => { finishReport = resolve; });
    serve(() => [{ ...run, status: "succeeded", profile_id: "historical", attempt: 0, report: { summaries } }], {
      [`GET ${prefix}/runs/pilot-1/report`]: () => report,
    });
    render(<ExperimentsPanel onOpenQuality={() => assert.fail("Imported aggregates have no native quality record")} />);
    await screen.findByRole("table");
    assert.equal(screen.queryByRole("button", { name: "Pokaż decyzję jakościową" }), null);
    await act(async () => {
      assert.ok(finishReport);
      finishReport(Response.json({ historical: true, summaries }));
    });
    assert.ok(screen.getByRole("button", { name: "Pobierz raport JSON" }));
    assert.equal(screen.queryByRole("button", { name: "Pokaż decyzję jakościową" }), null);
  });

  it("shows the baseline and adapter counts after completed evaluation", async () => {
    const metric = { n: 3, semantic: 2, usable: 2, passed: 1, format: 3, critical: 0, runtime_or_length_failure: 1 };
    serve(() => [{ ...run, status: "succeeded" }], {
      [`GET ${prefix}/runs/pilot-1/report`]: () => Response.json({
        summaries: {
          base: { total: metric, dialogue: { ...metric, n: 1, usable: 0 } },
          candidate: { total: { ...metric, usable: 3 }, dialogue: { ...metric, n: 1, usable: 1 } },
        },
        data_audit: auditFixture(),
        initial_adapter: {
          adapter_id: "p13-145", label: "P13 checkpoint 145", model: "Omni",
          revision: "a".repeat(40), snapshot_sha256: "b".repeat(64),
          config_sha256: "c".repeat(64), weights_sha256: "d".repeat(64),
          source: { identity: "P13", sha256: "e".repeat(64) },
        },
        cases: [{ case_id: "case-1", base: { text: "Bazowa odpowiedź" }, candidate: { text: "Odpowiedź adaptera" } }],
      }),
    });
    const opened: string[] = [];
    render(<ExperimentsPanel onOpenQuality={(recordId) => opened.push(recordId)} />);
    const table = await screen.findByRole("table", { name: "Porównanie z bazą" });
    assert.match(table.textContent ?? "", /Użyteczność2 \/ 33 \/ 3/);
    fireEvent.change(screen.getByLabelText("Kategoria wyników"), { target: { value: "dialogue" } });
    assert.match(table.textContent ?? "", /Użyteczność0 \/ 11 \/ 1/);
    assert.ok(screen.getByText("Odpowiedź adaptera"));
    assert.ok(screen.getByText("p13-145"));
    fireEvent.click(screen.getByText("Audyt danych przeszedł"));
    assert.ok(screen.getByRole("row", { name: /Replay.*9 \/ 12.*40 \/ 100/ }));
    assert.equal(screen.getByText("d".repeat(12)).getAttribute("title"), "d".repeat(64));
    assert.ok(screen.getByRole("button", { name: "Pobierz raport JSON" }));
    fireEvent.click(screen.getByRole("button", { name: "Pokaż decyzję jakościową" }));
    assert.deepEqual(opened, [run.run_id]);
  });

  it("keeps resume disabled for a stopped run without a checkpoint", async () => {
    serve(() => [{ ...run, status: "stopped" }]);
    render(<ExperimentsPanel />);
    const resume = (await screen.findByRole("button", { name: "Wznów trening" })) as HTMLButtonElement;
    assert.equal(resume.disabled, true);
    assert.equal(screen.queryByRole("button", { name: "Ponów ocenę" }), null);
  });
});
