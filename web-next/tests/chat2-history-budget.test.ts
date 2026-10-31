import assert from "node:assert/strict";
import { test } from "node:test";
import { boundChatHistory, type ChatHistoryTurn } from "../components/chat/history-budget";
import { mergeStreamsIntoHistory } from "../components/cockpit/hooks/cockpit-history-utils";

test("transport history keeps recent complete turns inside both count and combined text budgets", () => {
  const history: ChatHistoryTurn[] = Array.from({ length: 30 }, (_, index) => ({ role: index % 2 ? "assistant" : "user", content: String(index).padStart(2, "0") + "x".repeat(4998) }));
  const bounded = boundChatHistory(history, 10000);
  assert.equal(bounded.length, 8);
  assert.equal(bounded[0].content.slice(0, 2), "22");
  assert.equal(bounded.at(-1)?.role, "assistant");
  assert.equal(history.length, 30);
  assert.equal(boundChatHistory(history, 50000).length, 0);
  assert.equal(boundChatHistory(history.map(turn => ({ ...turn, content: "short" }))).length, 20);
});

test("incomplete or failed turns do not distort ordering or mutate material references", () => {
  const ids = ["material"];
  const history: ChatHistoryTurn[] = [{ role: "assistant", content: "orphan" }, { role: "user", content: "one", material_ids: ids }, { role: "assistant", content: "answer" }, { role: "user", content: "unfinished" }];
  const bounded = boundChatHistory(history);
  assert.deepEqual(bounded.map(turn => turn.content), ["one", "answer"]);
  bounded[0].material_ids?.push("different");
  assert.deepEqual(ids, ["material"]);
});

test("a terminal task clears a cached pending flag even when its final text is unchanged", () => {
  const entries = [{ request_id: "task", role: "assistant", content: "partial", pending: true, status: "PROCESSING" }];
  mergeStreamsIntoHistory(entries, { task: { result: "partial", status: "COMPLETED" } });
  assert.equal(entries[0].pending, false);
  assert.equal(entries[0].status, "COMPLETED");
  assert.equal(entries[0].content, "partial");
});


test("Normal stream snapshots retain pending content and terminal status for session cache recovery", () => {
  const source = [{ role: "assistant", request_id: "normal-task", content: "", pending: true, status: "PENDING" }];
  const partial = [...source];
  mergeStreamsIntoHistory(partial, { "normal-task": { result: "partial", status: "PROCESSING" } });
  assert.equal(partial[0].pending, true);
  assert.equal(partial[0].content, "partial");
  assert.equal(source[0].status, "PENDING");
  const terminal = [...partial];
  mergeStreamsIntoHistory(terminal, { "normal-task": { result: "partial", status: "COMPLETED" } });
  assert.equal(terminal[0].pending, false);
  assert.equal(terminal[0].status, "COMPLETED");
});
