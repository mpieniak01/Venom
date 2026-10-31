import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useSessionDraft } from "../components/chat/use-session-draft";

test("draft survives shell remount, stays session-scoped and clears only after acceptance", () => {
  const session = "draft-remount-" + Date.now();
  const first = renderHook(() => useSessionDraft(session));
  act(() => first.result.current[1]("unfinished question"));
  first.unmount();
  const second = renderHook(({ id }) => useSessionDraft(id), { initialProps: { id: session } });
  assert.equal(second.result.current[0], "unfinished question");
  second.rerender({ id: session + "-other" });
  assert.equal(second.result.current[0], "");
  act(() => second.result.current[1]("other session"));
  second.rerender({ id: session });
  assert.equal(second.result.current[0], "unfinished question");
  act(() => second.result.current[1](value => value + "!"));
  assert.equal(second.result.current[0], "unfinished question!");
  act(() => second.result.current[1](""));
  assert.equal(second.result.current[0], "");
  cleanup();
});

test("two mounted consumers share a draft but an unresolved session cannot mutate it", () => {
  const session = "draft-consumers-" + Date.now();
  const first = renderHook(() => useSessionDraft(session));
  const second = renderHook(() => useSessionDraft(session));
  const waiting = renderHook(() => useSessionDraft(""));
  act(() => first.result.current[1]("shared draft"));
  assert.equal(second.result.current[0], "shared draft");
  act(() => waiting.result.current[1]("must not leak"));
  assert.equal(waiting.result.current[0], "");
  assert.equal(first.result.current[0], "shared draft");
  cleanup();
});


afterEach(() => { cleanup(); mock.restoreAll(); });

test("quota failure prefers the new draft over a readable old localStorage value", () => {
  const session = "draft-quota-" + Date.now(), key = "venom-chat-draft:" + session;
  window.localStorage.setItem(key, "old persisted draft");
  const storage = Object.getPrototypeOf(window.localStorage) as Storage;
  mock.method(storage, "setItem", () => { throw new Error("QuotaExceededError"); });
  const first = renderHook(() => useSessionDraft(session));
  assert.equal(first.result.current[0], "old persisted draft");
  act(() => first.result.current[1]("new unsaved draft"));
  assert.equal(first.result.current[0], "new unsaved draft");
  act(() => first.result.current[1](previous => previous + "!"));
  first.unmount();
  const second = renderHook(() => useSessionDraft(session));
  assert.equal(second.result.current[0], "new unsaved draft!");
  assert.equal(window.localStorage.getItem(key), "old persisted draft");
});

test("a cross-tab write invalidates the dirty fallback and later writes recover", () => {
  const session = "draft-cross-tab-" + Date.now(), key = "venom-chat-draft:" + session;
  window.localStorage.setItem(key, "old");
  const storage = Object.getPrototypeOf(window.localStorage) as Storage;
  const write = mock.method(storage, "setItem", () => { throw new Error("quota"); });
  const hook = renderHook(() => useSessionDraft(session));
  act(() => hook.result.current[1]("dirty"));
  assert.equal(hook.result.current[0], "dirty");
  write.mock.restore(); window.localStorage.setItem(key, "written elsewhere");
  act(() => window.dispatchEvent(new window.StorageEvent("storage", { key, newValue: "written elsewhere", storageArea: window.localStorage })));
  assert.equal(hook.result.current[0], "written elsewhere");
  act(() => hook.result.current[1](value => value + "!"));
  assert.equal(window.localStorage.getItem(key), "written elsewhere!");
});

test("unrelated storage events preserve dirty drafts while cross-tab clear removes them", () => {
  const session = "draft-clear-" + Date.now(), key = "venom-chat-draft:" + session;
  window.localStorage.setItem(key, "old");
  mock.method(Object.getPrototypeOf(window.localStorage) as Storage, "setItem", () => { throw new Error("quota"); });
  const hook = renderHook(() => useSessionDraft(session));
  act(() => hook.result.current[1]("dirty"));
  act(() => window.dispatchEvent(new window.StorageEvent("storage", { key: "other-setting", newValue: "unrelated" })));
  assert.equal(hook.result.current[0], "dirty");
  window.localStorage.clear();
  act(() => window.dispatchEvent(new window.StorageEvent("storage", { key: null })));
  assert.equal(hook.result.current[0], "");
});
