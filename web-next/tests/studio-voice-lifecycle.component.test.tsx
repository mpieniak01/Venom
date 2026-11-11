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
  globalThis.fetch = async input => { if (String(input).includes("/speak")) { speech++; return new Response(new Blob(["wav"])); } assert.equal(new URL(String(input), "http://localhost").searchParams.has("prefer_native"), true); return Response.json({ session_id: "one", text: "one user turn" }); };
  const hook = renderHook(props => useStudioVoice(props, async () => ({ finish: async () => recorded(), dispose: () => {} })), { initialProps: fixture.props });
  await act(async () => { await hook.result.current.start(); }); await act(async () => { await hook.result.current.finish(); });
  assert.deepEqual(fixture.turns, ["one user turn"]);
  hook.rerender({ ...fixture.props, busy: true });
  const partial: ChatMessage = { bubbleId: "new-answer", requestId: "id", role: "assistant", text: "stopped partial", status: "CANCELLED", pending: false, timestamp: "" };
  hook.rerender({ ...fixture.props, busy: false, stopRevision: 1, messages: [partial] });
  await act(async () => { await Promise.resolve(); }); assert.equal(speech, 0); assert.equal(hook.result.current.status, "voiceIdle");
});

test("refreshing the Omni capability keeps an ordinary voice turn in progress", async () => {
  const fixture = options();
  const props = { ...fixture.props, mode: "conversation" as const, multimodalEnabled: true };
  let disposed = 0;
  globalThis.fetch = async input => {
    assert.ok(String(input).includes("/transcribe?"));
    return Response.json({ session_id: "one", text: "Co to jest kwadrat?" });
  };
  const hook = renderHook(current => useStudioVoice(current, async () => ({
    finish: async () => recorded(),
    dispose: () => { disposed++; },
  })), { initialProps: props });

  await act(async () => { await hook.result.current.start(); });
  hook.rerender({ ...props, multimodalEnabled: false });
  assert.equal(hook.result.current.status, "listening");
  assert.equal(disposed, 0);
  await act(async () => { await hook.result.current.finish(); });
  assert.deepEqual(fixture.turns, ["Co to jest kwadrat?"]);
  assert.equal(disposed, 1);
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


for (const [cause, expected] of [
  [new DOMException("denied", "NotAllowedError"), "micDenied"],
  [new Error("micUnavailable"), "micUnavailable"],
  [new Error("another capture failure"), "voiceError"],
] as const) {
  test(`capture failure ${expected} retains its translated error category`, async () => {
    const fixture = options();
    const hook = renderHook(() => useStudioVoice(fixture.props, async () => { throw cause; }));
    await act(async () => { await hook.result.current.start(); });
    assert.equal(hook.result.current.error, expected);
    assert.equal(hook.result.current.status, "voiceIdle");
    assert.deepEqual(fixture.drafts, []);
    assert.deepEqual(fixture.turns, []);
  });
}

test("the first image turn sends raw PCM and image together, then speaks a follow-up in the same session", async context => {
  const fixture = options();
  const activity: boolean[] = [];
  const submissions: FormData[] = [];
  const spoken: string[] = [];
  let commits = 0;
  let plays = 0;
  let pauses = 0;
  const playback = {
    onended: null as (() => void) | null,
    onerror: null as (() => void) | null,
    play: async () => { plays++; },
    pause: () => { pauses++; },
    removeAttribute: () => {},
  };
  const audioDescriptor = Object.getOwnPropertyDescriptor(globalThis, "Audio");
  Object.defineProperty(globalThis, "Audio", { configurable: true, value: function () { return playback; } });
  context.after(() => {
    if (audioDescriptor) Object.defineProperty(globalThis, "Audio", audioDescriptor);
    else Reflect.deleteProperty(globalThis, "Audio");
  });
  globalThis.fetch = async (input, init) => {
    if (String(input).endsWith("/multimodal-turn")) {
      assert.ok(init?.body instanceof FormData);
      submissions.push(init.body);
      if (submissions.length === 1) {
        return Response.json({ session_id: "one", text: "Nie słyszę pytania", sources: [], no_speech: true });
      }
      return Response.json({ session_id: "one", text: "Odpowiedź " + (submissions.length - 1), sources: ["Instrukcja"] });
    }
    assert.ok(String(input).endsWith("/speak"), "must not transcribe the input separately");
    const speech = JSON.parse(String(init?.body));
    assert.equal(speech.prefer_native, true);
    spoken.push(speech.text);
    return new Response(new Blob(["waveform"]));
  };
  const props = {
    ...fixture.props,
    mode: "conversation" as const,
    multimodalEnabled: true,
    onMultimodalBusy: (busy: boolean) => { activity.push(busy); },
    onMultimodalCommit: () => { commits++; },
  };
  const hook = renderHook(() => useStudioVoice(props, async () => ({ finish: async () => recorded(), dispose: () => {} })));
  act(() => hook.result.current.selectImage(new File(["snapshot"], "screen.png", { type: "image/png" })));
  await act(async () => { await hook.result.current.start(); await hook.result.current.finish(); });
  assert.equal(hook.result.current.error, "silence");
  assert.equal(hook.result.current.image?.name, "screen.png");
  assert.equal(commits, 0);
  assert.deepEqual(spoken, []);
  await act(async () => { await hook.result.current.start(); await hook.result.current.finish(); });
  assert.equal(submissions[0].get("session_id"), "one");
  assert.equal(submissions[0].get("sample_rate"), "16000");
  assert.equal(submissions[0].get("language"), "pl");
  const clip = submissions[0].get("audio");
  const attachment = submissions[0].get("image");
  assert.ok(clip instanceof File);
  assert.deepEqual(await clip.arrayBuffer(), recorded().pcm);
  assert.ok(attachment instanceof File);
  assert.equal(attachment.name, "screen.png");
  assert.equal(await attachment.text(), "snapshot");
  assert.deepEqual(hook.result.current.sources, ["Instrukcja"]);
  assert.equal(hook.result.current.image, null);
  assert.equal(hook.result.current.status, "speaking");

  await act(async () => { await hook.result.current.stop(); });
  assert.equal(pauses, 1);
  assert.equal(hook.result.current.status, "voiceIdle");

  await act(async () => { await hook.result.current.start(); await hook.result.current.finish(); });
  assert.equal(submissions[1].has("image"), true);
  assert.equal(submissions[2].get("session_id"), "one");
  assert.equal(submissions[2].has("image"), false);
  assert.deepEqual(spoken, ["Odpowiedź 1", "Odpowiedź 2"]);
  assert.deepEqual(activity, [true, false, true, false, true, false]);
  assert.equal(commits, 2);
  assert.equal(plays, 2);
  assert.deepEqual(fixture.turns, []);
  hook.unmount();
});

test("stopping an image turn aborts the request and ignores a late response", async () => {
  const fixture = options();
  let resolve!: (value: Response) => void;
  let signal: AbortSignal | null | undefined;
  let commits = 0;
  globalThis.fetch = async (input, init) => {
    assert.ok(String(input).endsWith("/multimodal-turn"));
    signal = init?.signal;
    return new Promise<Response>(ready => { resolve = ready; });
  };
  const props = {
    ...fixture.props,
    mode: "conversation" as const,
    multimodalEnabled: true,
    onMultimodalCommit: () => { commits++; },
  };
  const hook = renderHook(() => useStudioVoice(props, async () => ({ finish: async () => recorded(), dispose: () => {} })));
  act(() => hook.result.current.selectImage(new File(["snapshot"], "screen.png", { type: "image/png" })));
  await act(async () => { await hook.result.current.start(); });
  let finishing!: Promise<void>;
  act(() => { finishing = hook.result.current.finish(); });
  await waitFor(() => assert.ok(signal));
  await act(async () => { await hook.result.current.stop(); });
  assert.equal(signal?.aborted, true);
  await act(async () => {
    resolve(Response.json({ session_id: "one", text: "late response", sources: ["Instrukcja"] }));
    await finishing;
  });
  assert.equal(commits, 0);
  assert.deepEqual(hook.result.current.sources, []);
  assert.equal(hook.result.current.status, "voiceIdle");
});

test("ordinary Omni conversation recovers after silence and keeps native ASR and TTS despite host availability", async (context) => {
  const fixture = options();
  const transcripts = ["", "Co to jest kwadrat?", "Ile to trzy razy trzy?"];
  const spoken: string[] = [];
  const playback = {
    onended: null as (() => void) | null,
    onerror: null as (() => void) | null,
    play: async () => {},
    pause: () => {},
    removeAttribute: () => {},
  };
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "Audio");
  Object.defineProperty(globalThis, "Audio", { configurable: true, value: function () { return playback; } });
  context.after(() => {
    if (descriptor) Object.defineProperty(globalThis, "Audio", descriptor);
    else Reflect.deleteProperty(globalThis, "Audio");
  });
  globalThis.fetch = async (input, init) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname.endsWith("/transcribe")) {
      assert.equal(url.searchParams.has("prefer_native"), true);
      return Response.json({ session_id: "one", text: transcripts.shift() });
    }
    assert.ok(url.pathname.endsWith("/speak"));
    const speech = JSON.parse(String(init?.body));
    assert.equal(speech.prefer_native, true);
    spoken.push(speech.text);
    return new Response(new Blob(["waveform"]));
  };
  const props = { ...fixture.props, mode: "conversation" as const, hostAudioAvailable: true, multimodalEnabled: true };
  const hook = renderHook(
    current => useStudioVoice(current, async () => ({ finish: async () => recorded(), dispose: () => {} })),
    { initialProps: props },
  );
  const record = async () => {
    await act(async () => { await hook.result.current.start(); await hook.result.current.finish(); });
  };
  await record();
  assert.equal(hook.result.current.error, "silence");
  assert.equal(hook.result.current.status, "voiceIdle");
  assert.deepEqual(fixture.turns, []);

  const messages: ChatMessage[] = [];
  for (const [index, reply] of ["Kwadrat ma cztery równe boki i cztery kąty proste.", "Dziewięć."].entries()) {
    await record();
    messages.push({ bubbleId: String(index), requestId: String(index), role: "assistant", text: reply, status: "COMPLETED", pending: false, timestamp: "" });
    await act(async () => { hook.rerender({ ...props, messages: [...messages] }); });
    await waitFor(() => assert.equal(spoken[index], reply));
    act(() => playback.onended?.());
    assert.equal(hook.result.current.status, "voiceIdle");
  }
  assert.deepEqual(fixture.turns, ["Co to jest kwadrat?", "Ile to trzy razy trzy?"]);
});

test("a recognized question rejected by chat survives in the draft of the same session", async () => {
  const fixture = options();
  fixture.props.mode = "conversation";
  fixture.props.onTurn = async () => false;
  globalThis.fetch = async () => Response.json({ session_id: "one", text: "Ile to trzy razy trzy?" });
  const hook = renderHook(() => useStudioVoice(fixture.props, async () => ({
    finish: async () => recorded(),
    dispose: () => {},
  })));

  await act(async () => { await hook.result.current.start(); await hook.result.current.finish(); });

  assert.deepEqual(fixture.drafts, ["Ile to trzy razy trzy?"]);
  assert.equal(hook.result.current.error, "voiceDraftSaved");
  assert.equal(hook.result.current.status, "voiceIdle");
});

test("removing an image during a MediaRecorder turn keeps the audio and omits the image", async context => {
  class PilotRecorder {
    static isTypeSupported = () => true;
    mimeType = "audio/webm;codecs=opus";
    state = "inactive";
    ondataavailable: ((event: { data: Blob }) => void) | null = null;
    onstop: (() => void) | null = null;

    start() { this.state = "recording"; }
    stop() {
      this.state = "inactive";
      this.ondataavailable?.({ data: new Blob(["voice"], { type: this.mimeType }) });
      this.onstop?.();
    }
  }

  const recorderDescriptor = Object.getOwnPropertyDescriptor(globalThis, "MediaRecorder");
  const mediaDescriptor = Object.getOwnPropertyDescriptor(navigator, "mediaDevices");
  Object.defineProperty(globalThis, "MediaRecorder", { configurable: true, value: PilotRecorder });
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: async () => ({ getTracks: () => [] }) },
  });
  context.after(() => {
    if (recorderDescriptor) Object.defineProperty(globalThis, "MediaRecorder", recorderDescriptor);
    else Reflect.deleteProperty(globalThis, "MediaRecorder");
    if (mediaDescriptor) Object.defineProperty(navigator, "mediaDevices", mediaDescriptor);
    else Reflect.deleteProperty(navigator, "mediaDevices");
  });

  const submissions: FormData[] = [];
  globalThis.fetch = async (input, init) => {
    assert.ok(String(input).endsWith("/multimodal-turn"));
    assert.ok(init?.body instanceof FormData);
    submissions.push(init.body);
    // A different session suppresses playback so the test can inspect the upload.
    return Response.json({ session_id: "ignored", text: "reply", sources: [] });
  };
  const props = { ...options().props, mode: "conversation" as const, multimodalEnabled: true };
  const hook = renderHook(() => useStudioVoice(props));
  act(() => hook.result.current.selectImage(new File(["snapshot"], "screen.png", { type: "image/png" })));
  await act(async () => hook.result.current.start());
  assert.equal(hook.result.current.status, "listening");
  act(() => hook.result.current.selectImage(null));
  await act(async () => hook.result.current.finish());

  assert.equal(submissions.length, 1);
  assert.equal(submissions[0].has("image"), false);
  const audio = submissions[0].get("audio");
  assert.ok(audio instanceof File);
  assert.equal(audio.type, "audio/webm;codecs=opus");
  assert.equal(await audio.text(), "voice");
  assert.equal(hook.result.current.error, null);
});

for (const mode of ["interleaved", "audio"] as const) {
  test("Studio plays native Omni " + mode + " without an ASR or TTS request", async context => {
    const fixture = options();
    const captured: Blob[] = [];
    let commits = 0;
    let plays = 0;
    const createObjectURL = context.mock.method(URL, "createObjectURL", (blob: Blob) => {
      captured.push(blob);
      return "blob:native-omni";
    });
    context.mock.method(URL, "revokeObjectURL", () => {});
    const audioDescriptor = Object.getOwnPropertyDescriptor(globalThis, "Audio");
    Object.defineProperty(globalThis, "Audio", {
      configurable: true,
      value: function () {
        return { play: async () => { plays++; }, pause() {}, removeAttribute() {} };
      },
    });
    context.after(() => {
      if (audioDescriptor) Object.defineProperty(globalThis, "Audio", audioDescriptor);
      else Reflect.deleteProperty(globalThis, "Audio");
    });
    const requests: string[] = [];
    globalThis.fetch = async (input, init) => {
      requests.push(String(input));
      assert.ok(String(input).endsWith("/multimodal-turn"));
      assert.ok(init?.body instanceof FormData);
      assert.equal(init.body.get("generation_mode"), mode);
      assert.equal(init.body.has("image"), false);
      return Response.json({
        session_id: "one", text: mode === "audio" ? null : "Tekst modelu", sources: [],
        generation_mode: mode, audio_base64: "UklGRg==",
      });
    };
    const props = {
      ...fixture.props, mode: "conversation" as const, multimodalEnabled: true, generationMode: mode,
      onMultimodalCommit: () => { commits++; },
    };
    const hook = renderHook(() => useStudioVoice(props, async () => ({
      finish: async () => recorded(), dispose() {},
    })));
    await act(async () => { await hook.result.current.start(); await hook.result.current.finish(); });

    assert.equal(requests.length, 1);
    assert.equal(commits, 1);
    assert.equal(plays, 1);
    assert.equal(createObjectURL.mock.callCount(), 1);
    assert.equal(captured[0].type, "audio/wav");
    assert.equal(await captured[0].text(), "RIFF");
    assert.equal(hook.result.current.nativeAudioOnly, mode === "audio");
    assert.equal(hook.result.current.status, "speaking");
    assert.deepEqual(fixture.turns, []);
    hook.unmount();
  });
}

test("an unavailable native Studio turn stays in the selected mode without falling back", async () => {
  const fixture = options();
  const props = {
    ...fixture.props, mode: "conversation" as const, multimodalEnabled: true, generationMode: "audio" as const,
  };
  let requests = 0;
  globalThis.fetch = async (input, init) => {
    requests++;
    assert.ok(String(input).endsWith("/multimodal-turn"));
    assert.ok(init?.body instanceof FormData);
    assert.equal(init.body.get("generation_mode"), "audio");
    return Response.json({ detail: { reason_code: "omni_native_unavailable" } }, { status: 503 });
  };
  const hook = renderHook(() => useStudioVoice(props, async () => ({
    finish: async () => recorded(), dispose() {},
  })));
  await act(async () => { await hook.result.current.start(); await hook.result.current.finish(); });
  assert.equal(requests, 1);
  assert.equal(hook.result.current.error, "voiceNativeUnavailable");
  assert.equal(hook.result.current.status, "voiceIdle");
});
