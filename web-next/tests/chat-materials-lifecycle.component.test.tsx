import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useChatMaterials } from "../components/chat/use-chat-materials";
import type { ChatMaterial } from "../lib/chat-materials";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
function material(id: string, session = "one"): ChatMaterial {
  return { id, session_id: session, name: id + ".txt", mime_type: "text/plain", size_bytes: 1,
    kind: "document", status: "ready", created_at: "now", preview_url: "unused" };
}
function capabilities() {
  return Response.json({ document: true, image: true, audio: false, video: false, max_bytes: 8388608,
    max_document_chars: 64000, runtime_id: "ollama", config_hash: "cfg", model: "model" });
}
function useMaterials(session = "one") { return useChatMaterials(session, "model", "ollama", "ollama", "cfg", true); }
afterEach(() => { cleanup(); mock.restoreAll(); });

test("an initial delayed list preserves an upload accepted after the list began", async () => {
  const list = deferred<Response>();
  const created = material("uploaded");
  mock.method(globalThis, "fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).includes("/capabilities")) return capabilities();
    return init?.method === "POST" ? Response.json(created) : list.promise;
  });
  const hook = renderHook(() => useMaterials());
  await act(async () => { await hook.result.current.upload([new File(["x"], "context.txt")]); });
  assert.deepEqual(hook.result.current.items.map(item => item.id), ["uploaded"]);
  await act(async () => { list.resolve(Response.json({ materials: [material("already-present")] })); });
  assert.deepEqual(hook.result.current.items.map(item => item.id), ["already-present", "uploaded"]);
});

test("a delayed list cannot resurrect a material removed during its request", async () => {
  const delayed = deferred<Response>(); let lists = 0;
  mock.method(globalThis, "fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).includes("/capabilities")) return capabilities();
    if (init?.method === "DELETE") return new Response(null, { status: 204 });
    return ++lists === 1 ? Response.json({ materials: [material("removed")] }) : delayed.promise;
  });
  const hook = renderHook(() => useMaterials());
  await act(async () => { await Promise.resolve(); });
  let refresh!: Promise<void>;
  await act(async () => { refresh = hook.result.current.refresh(); await hook.result.current.remove("removed"); });
  assert.deepEqual(hook.result.current.items, []);
  await act(async () => { delayed.resolve(Response.json({ materials: [material("removed")] })); await refresh; });
  assert.deepEqual(hook.result.current.items, []);
});

test("a slower earlier refresh cannot replace a newer list", async () => {
  const first = deferred<Response>(), second = deferred<Response>(); let lists = 0;
  mock.method(globalThis, "fetch", async (input: RequestInfo | URL) => {
    if (String(input).includes("/capabilities")) return capabilities();
    return ++lists === 1 ? first.promise : second.promise;
  });
  const hook = renderHook(() => useMaterials());
  let refresh!: Promise<void>;
  await act(async () => { refresh = hook.result.current.refresh(); second.resolve(Response.json({ materials: [material("newer")] })); await refresh; });
  await act(async () => { first.resolve(Response.json({ materials: [material("older")] })); });
  assert.deepEqual(hook.result.current.items.map(item => item.id), ["newer"]);
});

test("late upload completion after a session switch cannot return or publish old references", async () => {
  const uploaded = deferred<Response>(); let uploadSignal: AbortSignal | null = null;
  mock.method(globalThis, "fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).includes("/capabilities")) return capabilities();
    if (init?.method === "POST") { uploadSignal = init.signal as AbortSignal; return uploaded.promise; }
    return Response.json({ materials: [] });
  });
  const hook = renderHook(({ session }) => useMaterials(session), { initialProps: { session: "one" } });
  let upload!: Promise<ChatMaterial[]>;
  act(() => { upload = hook.result.current.upload([new File(["x"], "note.txt")]); });
  assert.equal(hook.result.current.uploading, true);
  hook.rerender({ session: "two" });
  assert.equal(hook.result.current.uploading, false);
  assert.equal((uploadSignal as AbortSignal | null)?.aborted, true);
  await act(async () => { uploaded.resolve(Response.json(material("old"))); assert.deepEqual(await upload, []); });
  assert.deepEqual(hook.result.current.items, []);
  assert.equal(hook.result.current.error, null);
});

test("late deletion cannot report success to the next session and errors reset on navigation", async () => {
  const deleted = deferred<Response>();
  mock.method(globalThis, "fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).includes("/capabilities")) return capabilities();
    if (init?.method === "DELETE") return deleted.promise;
    const session = new URL(String(input), "http://localhost").searchParams.get("session_id")!;
    return Response.json({ materials: [material(session + "-item", session)] });
  });
  const hook = renderHook(({ session }) => useMaterials(session), { initialProps: { session: "one" } });
  await act(async () => { await hook.result.current.upload([new File(["html"], "active.html", { type: "text/html" })]); });
  assert.equal(hook.result.current.error, "fileUnsupported");
  let removal!: Promise<boolean>;
  act(() => { removal = hook.result.current.remove("one-item"); });
  hook.rerender({ session: "two" });
  await act(async () => { deleted.resolve(new Response(null, { status: 204 })); assert.equal(await removal, false); });
  assert.deepEqual(hook.result.current.items.map(item => item.id), ["two-item"]);
  assert.equal(hook.result.current.error, null);
});

test("a failed old list cannot overwrite a successful upload with stale error state", async () => {
  const list = deferred<Response>();
  mock.method(globalThis, "fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).includes("/capabilities")) return capabilities();
    return init?.method === "POST" ? Response.json(material("new")) : list.promise;
  });
  const hook = renderHook(() => useMaterials());
  await act(async () => { await hook.result.current.upload([new File(["x"], "note.txt")]); });
  await act(async () => { list.resolve(Response.json({ detail: "old list failure" }, { status: 400 })); });
  assert.equal(hook.result.current.error, null);
  assert.deepEqual(hook.result.current.items.map(item => item.id), ["new"]);
});
