import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ChatMessage } from "../components/cockpit/cockpit-chat-thread";
import { useStudioVoice } from "../components/chat/use-studio-voice";
import type { AudioCapture } from "../lib/chat-audio";
const originalFetch = globalThis.fetch;
afterEach(() => { cleanup(); globalThis.fetch = originalFetch; });
function options() {
  const drafts: string[] = []; const turns: string[] = []; let stopped = 0;
  return { drafts, turns, stopped: () => stopped, props: { session: "one", mode: "dictation" as "dictation" | "conversation", language: "pl", busy: false, messages: [] as ChatMessage[], stopRevision: 0,
    onDraft: (text: string) => drafts.push(text), onTurn: async (text: string) => { turns.push(text); return true; }, onStop: async () => { stopped++; }, onClose: () => {} } };
}
const recorded = () => ({ pcm: new ArrayBuffer(4), sampleRate: 16000 });

test("mount requests no microphone; explicit dictation only edits the draft", async () => {
  const fixture = options(); let captures = 0; let disposed = 0; let requests = 0;
  globalThis.fetch = async () => { requests++; return Response.json({ session_id: "one", text: "editable transcript" }); };
  const hook = renderHook(() => useStudioVoice(fixture.props, async () => { captures++; return { finish: async () => recorded(), dispose: () => { disposed++; } }; }));
  assert.equal(captures, 0); assert.equal(requests, 0);
  await act(async () => { await hook.result.current.start(); });
  await act(async () => { await hook.result.current.finish(); });
  assert.deepEqual(fixture.drafts, ["editable transcript"]); assert.deepEqual(fixture.turns, []); assert.equal(disposed, 1); assert.equal(requests, 1);
});

test("ending a pending permission ignores the late capture and disposes it", async () => {
  const fixture = options(); let resolve!: (value: AudioCapture) => void; let signal!: AbortSignal | undefined; let disposed = 0;
  const hook = renderHook(() => useStudioVoice(fixture.props, async (_limit, current) => { signal = current; return new Promise<AudioCapture>(ready => { resolve = ready; }); }));
  let pending!: Promise<void>; act(() => { pending = hook.result.current.start(); });
  act(() => hook.result.current.end()); assert.equal(signal?.aborted, true);
  await act(async () => { resolve({ finish: async () => recorded(), dispose: () => { disposed++; } }); await pending; });
  assert.equal(disposed, 1); assert.equal(hook.result.current.status, "voiceEnded"); assert.deepEqual(fixture.drafts, []);
});

test("a late transcription after ending voice cannot alter a draft or send a turn", async () => {
  const fixture = options(); let resolve!: (value: Response) => void; let requested = false;
  globalThis.fetch = async () => { requested = true; return new Promise<Response>(ready => { resolve = ready; }); };
  const hook = renderHook(() => useStudioVoice(fixture.props, async () => ({ finish: async () => recorded(), dispose: () => {} })));
  await act(async () => { await hook.result.current.start(); });
  let pending!: Promise<void>; act(() => { pending = hook.result.current.finish(); });
  await waitFor(() => assert.equal(requested, true)); act(() => hook.result.current.end());
  await act(async () => { resolve(Response.json({ session_id: "one", text: "must not send" })); await pending; });
  assert.deepEqual(fixture.drafts, []); assert.deepEqual(fixture.turns, []);
});

test("conversation uses the same text turn once and never speaks a stopped partial", async () => {
  const fixture = options(); fixture.props.mode = "conversation"; let speech = 0;
  globalThis.fetch = async input => { if (String(input).includes("/speak")) { speech++; return new Response(new Blob(["wav"])); } return Response.json({ session_id: "one", text: "one user turn" }); };
  const hook = renderHook(props => useStudioVoice(props, async () => ({ finish: async () => recorded(), dispose: () => {} })), { initialProps: fixture.props });
  await act(async () => { await hook.result.current.start(); }); await act(async () => { await hook.result.current.finish(); });
  assert.deepEqual(fixture.turns, ["one user turn"]);
  hook.rerender({ ...fixture.props, busy: true });
  const partial: ChatMessage = { bubbleId: "new-answer", requestId: "id", role: "assistant", text: "stopped partial", status: "CANCELLED", pending: false, timestamp: "" };
  hook.rerender({ ...fixture.props, busy: false, stopRevision: 1, messages: [partial] });
  await act(async () => { await Promise.resolve(); }); assert.equal(speech, 0); assert.equal(hook.result.current.status, "voiceIdle");
});

test("ending during capture flush stops microphone immediately", async () => {
  const fixture = options(); let finish!: () => void; let disposed = 0;
  const hook = renderHook(() => useStudioVoice(fixture.props, async () => ({ finish: () => new Promise(ready => { finish = () => ready(recorded()); }), dispose: () => { disposed++; } })));
  await act(async () => { await hook.result.current.start(); });
  let pending!: Promise<void>; act(() => { pending = hook.result.current.finish(); });
  act(() => hook.result.current.end()); assert.equal(disposed, 1);
  await act(async () => { finish(); await pending; }); assert.deepEqual(fixture.drafts, []);
});


test("a late rejected voice turn cannot reset a new listening epoch after Stop", async () => {
  const fixture = options(); fixture.props.mode = "conversation";
  let resolveTurn!: (accepted: boolean) => void;
  let turnStarted = false; let captures = 0; let newCaptureDisposed = false;
  fixture.props.onTurn = async () => { turnStarted = true; return new Promise<boolean>(ready => { resolveTurn = ready; }); };
  globalThis.fetch = async () => Response.json({ session_id: "one", text: "old turn" });
  const hook = renderHook(() => useStudioVoice(fixture.props, async () => {
    const index = ++captures;
    return { finish: async () => recorded(), dispose: () => { if (index === 2) newCaptureDisposed = true; } };
  }));
  await act(async () => { await hook.result.current.start(); });
  let oldFinish!: Promise<void>; act(() => { oldFinish = hook.result.current.finish(); });
  await waitFor(() => assert.equal(turnStarted, true));
  await act(async () => { await hook.result.current.stop(); });
  await act(async () => { await hook.result.current.start(); });
  assert.equal(captures, 2); assert.equal(hook.result.current.status, "listening");
  await act(async () => { resolveTurn(false); await oldFinish; });
  assert.equal(hook.result.current.status, "listening");
  assert.equal(hook.result.current.error, null);
  assert.equal(newCaptureDisposed, false);
});
