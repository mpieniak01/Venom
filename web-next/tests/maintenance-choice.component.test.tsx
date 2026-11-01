import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, it } from "node:test";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BenchmarkCodingConfigurator } from "../components/benchmark/benchmark-coding-configurator";
import type { CodingBenchmarkStartRequest } from "../lib/types";

const originalFetch = globalThis.fetch;
afterEach(() => { cleanup(); globalThis.fetch = originalFetch; });

it("uses catalog models and the complete fixed schedule without invoking generation", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({enabled: true, models: [{name: "mini-coder-1.7b", provider: "maintenance"}]}));
  const requests: CodingBenchmarkStartRequest[] = [];
  await act(async () => {render(<BenchmarkCodingConfigurator availableModels={[{name:"ollama-only",provider:"ollama"}]} onStart={request => requests.push(request)} />);});
  const checkbox = screen.getByRole("checkbox", {name: /Porównanie modeli utrzymania|Maintenance model comparison|Modellvergleich/i});
  await waitFor(() => assert.equal((checkbox as HTMLInputElement).disabled, false));
  fireEvent.click(checkbox);
  assert.equal(screen.queryByRole("button", {name: "ollama-only"}), null);
  fireEvent.click(screen.getByRole("button", {name: "mini-coder-1.7b"}));
  fireEvent.click(screen.getByRole("button", {name: /uruchom|start|rozpocznij/i}));
  assert.equal(requests.length, 1);
  assert.deepEqual(requests[0].models, ["mini-coder-1.7b"]);
  assert.deepEqual(requests[0].tasks, ["maintenance_operator","maintenance_repair","maintenance_localization"]);
  assert.equal(requests[0].loop_task, "");
  assert.equal(requests[0].max_rounds, 3);
  assert.equal(requests[0].stop_on_failure, false);
});

it("keeps the experiment unavailable when the host profile is disabled", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({enabled:false,models:[]}));
  await act(async () => {render(<BenchmarkCodingConfigurator availableModels={[]} onStart={() => assert.fail("must not start")} />);});
  const checkbox = screen.getByRole("checkbox", {name: /Porównanie modeli utrzymania|Maintenance model comparison|Modellvergleich/i});
  assert.equal((checkbox as HTMLInputElement).disabled, true);
});
