import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ExperimentsPanel } from "../components/academy/experiments-panel";
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

  it("shows the baseline and adapter counts after completed evaluation", async () => {
    const metric = { n: 3, semantic: 2, usable: 2, passed: 1, format: 3, critical: 0, runtime_or_length_failure: 1 };
    serve(() => [{ ...run, status: "succeeded" }], {
      [`GET ${prefix}/runs/pilot-1/report`]: () => Response.json({
        summaries: { base: { total: metric }, candidate: { total: { ...metric, usable: 3 } } },
        cases: [{ case_id: "case-1", base: { text: "Bazowa odpowiedź" }, candidate: { text: "Odpowiedź adaptera" } }],
      }),
    });
    render(<ExperimentsPanel />);
    const table = await screen.findByRole("table");
    assert.match(table.textContent ?? "", /Użyteczność2 \/ 33 \/ 3/);
    assert.ok(screen.getByText("Odpowiedź adaptera"));
    assert.ok(screen.getByRole("button", { name: "Pobierz raport JSON" }));
  });

  it("keeps resume disabled for a stopped run without a checkpoint", async () => {
    serve(() => [{ ...run, status: "stopped" }]);
    render(<ExperimentsPanel />);
    const resume = (await screen.findByRole("button", { name: "Wznów trening" })) as HTMLButtonElement;
    assert.equal(resume.disabled, true);
    assert.equal(screen.queryByRole("button", { name: "Ponów ocenę" }), null);
  });
});
