import assert from "node:assert/strict";
import { test } from "node:test";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { useConversationData } from "../components/chat/use-conversation-data";
test("fresh active identity wins as a complete tuple over a stale catalog after Apply", async () => {
  const previous = globalThis.fetch; let model = "A"; let catalogRequests = 0;
  globalThis.fetch = async input => {
    if (String(input).includes("/llm-runtime/options")) { catalogRequests++; return Response.json({ active: { active_server: "openrouter", active_model: "A" }, model_catalog: {}, runtimes: [{ runtime_id: "openrouter", configured: true, available: true, source_type: "cloud-api", status: "ready", active: true, models: [] }] }); }
    return Response.json({ active_server: "openrouter", active_model: model, runtime_id: "openrouter@" + model, config_hash: "hash-" + model });
  };
  try {
    const hook = renderHook(() => useConversationData());
    await waitFor(() => assert.equal(hook.result.current.data.activeServerInfo?.active_model, "A"));
    model = "B"; await act(async () => { await hook.result.current.data.refresh.activeServer(); });
    const identity = hook.result.current.data.activeServerInfo;
    assert.deepEqual([identity?.active_server, identity?.active_model, identity?.runtime_id, identity?.config_hash], ["openrouter", "B", "openrouter@B", "hash-B"]);
    assert.equal(catalogRequests, 1);
  } finally { cleanup(); globalThis.fetch = previous; }
});
