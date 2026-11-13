import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  recipe: { rank: 8, alpha: 16, learning_rate: 0.0002 },
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
  handlers: Record<string, (init?: RequestInit) => Response> = {},
) {
  globalThis.fetch = async (input, init) => {
    const path = new URL(String(input), "http://localhost").pathname;
    const key = `${init?.method ?? "GET"} ${path}`;
    if (handlers[key]) return handlers[key](init);
    if (key === `GET ${prefix}/profiles`) return Response.json({ profiles: [profile] });
    if (key === `GET ${prefix}/runs`) return Response.json({ runs: runs() });
    throw new Error(`Unexpected request: ${key}`);
  };
}

describe("Academy experiments", () => {
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
        cases: [{ case_id: "case-1", base: { text: "Bazowa odpowiedź" }, candidate: { text: "Odpowiedź adaptera" } }],
      }),
    });
    const opened: string[] = [];
    render(<ExperimentsPanel onOpenQuality={(recordId) => opened.push(recordId)} />);
    const table = await screen.findByRole("table");
    assert.match(table.textContent ?? "", /Użyteczność2 \/ 33 \/ 3/);
    fireEvent.change(screen.getByLabelText("Kategoria wyników"), { target: { value: "dialogue" } });
    assert.match(table.textContent ?? "", /Użyteczność0 \/ 11 \/ 1/);
    assert.ok(screen.getByText("Odpowiedź adaptera"));
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
