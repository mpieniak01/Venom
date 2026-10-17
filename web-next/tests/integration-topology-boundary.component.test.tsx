import "./component-test-setup";
import Link from "next/link";
import assert from "node:assert/strict";
import { afterEach, it, mock } from "node:test";
import { cleanup, render, screen } from "@testing-library/react";
import { TopologyErrorBoundary } from "../components/config/integration-topology-boundary";

afterEach(() => { cleanup(); mock.restoreAll(); });
it("isolates a renderer/chunk failure and keeps navigation outside the canvas usable", () => {
  mock.method(console, "error", () => undefined);
  function BrokenCanvas(): never { throw new Error("chunk unavailable"); }
  render(<><button>Other config tab</button><TopologyErrorBoundary fallback={<Link href="/config?tab=integrations">Integration list</Link>}><BrokenCanvas /></TopologyErrorBoundary></>);
  assert.equal(screen.getByRole("link", { name: "Integration list" }).getAttribute("href"), "/config?tab=integrations");
  assert.ok(screen.getByRole("button", { name: "Other config tab" }));
});
it("renders a working canvas without the fallback", () => {
  render(<TopologyErrorBoundary fallback={<span>Failure</span>}><span>Canvas</span></TopologyErrorBoundary>);
  assert.ok(screen.getByText("Canvas"));
  assert.equal(screen.queryByText("Failure"), null);
});
