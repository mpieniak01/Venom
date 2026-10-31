import assert from "node:assert/strict";
import { test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useSessionHistoryState } from "../components/cockpit/cockpit-hooks";

test("changing session never overwrites the destination cache with the source history", () => {
  const refresh = () => {};
  const entry = (content: string) => ({ role: "assistant", content, request_id: content, pending: true });
  const a = "chat2-cache-a", b = "chat2-cache-b", boot = "chat2-cache-boot";
  const key = (id: string) => `venom-session-history:${id}:${boot}`;
  window.sessionStorage.setItem(key(b), JSON.stringify([entry("B")]));
  try {
    const hook = renderHook(({ id }) => useSessionHistoryState({ sessionId: id, backendBootId: boot, refreshSessionHistory: refresh, refreshHistory: refresh }), { initialProps: { id: a } });
    act(() => hook.result.current.setLocalSessionHistory([entry("A")]));
    hook.rerender({ id: b });
    assert.equal(hook.result.current.localSessionHistory[0]?.content, "B");
    assert.equal(JSON.parse(window.sessionStorage.getItem(key(b))!)[0].content, "B");
    hook.rerender({ id: a });
    assert.equal(hook.result.current.localSessionHistory[0]?.content, "A");
  } finally { cleanup(); window.sessionStorage.removeItem(key(a)); window.sessionStorage.removeItem(key(b)); }
});


for (const status of ["COMPLETED", "CANCELLED"]) test(`durable ${status} Direct history replaces a cached pending partial after reload`, () => {
  const id = `direct-${status}`, boot = "durable-boot", request = "9e786a0e-27ed-497a-a9e3-e922889cf136";
  const key = `venom-session-history:${id}:${boot}`;
  const refresh = () => {};
  window.sessionStorage.setItem(key, JSON.stringify([{ role: "assistant", request_id: request, content: "cached partial", pending: true, status: "PROCESSING" }]));
  try {
    const hook = renderHook(({ incoming }) => useSessionHistoryState({ sessionId: id, backendBootId: boot, sessionHistoryData: { history: incoming }, refreshSessionHistory: refresh, refreshHistory: refresh }), { initialProps: { incoming: [] as Array<{role:string;request_id:string;content:string;status:string;pending?:boolean}> } });
    assert.equal(hook.result.current.localSessionHistory[0].pending, true);
    hook.rerender({ incoming: [{ role: "assistant", request_id: request, content: "durable final", status }] });
    assert.equal(hook.result.current.localSessionHistory[0].content, "durable final");
    assert.equal(hook.result.current.localSessionHistory[0].status, status);
    assert.equal(hook.result.current.localSessionHistory[0].pending, false);
    assert.equal(JSON.parse(window.sessionStorage.getItem(key)!)[0].content, "durable final");
  } finally { cleanup(); window.sessionStorage.removeItem(key); }
});
