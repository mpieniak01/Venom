import "./component-test-setup";
import assert from "node:assert/strict";
import { it, type TestContext } from "node:test";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { VoiceCommandCenter } from "../components/voice/voice-command-center";

class VoiceSocket {
  static readonly OPEN = 1;
  static instances: VoiceSocket[] = [];
  readyState = 0;
  sent: Array<string | Blob> = [];
  onopen?: () => void;
  onclose?: (event: { code: number }) => void;
  onmessage?: (event: { data: string }) => void;

  constructor() {
    VoiceSocket.instances.push(this);
  }

  open() {
    this.readyState = VoiceSocket.OPEN;
    this.onopen?.();
  }

  close(code = 1000) {
    this.readyState = 3;
    this.onclose?.({ code });
  }

  send(data: string | Blob) {
    this.sent.push(data);
  }

  receive(data: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

class VoiceRecorder {
  static isTypeSupported() { return true; }
  mimeType = "audio/webm;codecs=opus";
  state = "inactive";
  onstop?: () => void;
  ondataavailable?: (event: { data: Blob }) => void;

  start() { this.state = "recording"; }
  requestData() {}
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new window.Blob(["voice"], { type: this.mimeType }) });
    this.onstop?.();
  }
}

class VoiceAudioContext {
  sampleRate = 48000;
  state = "running";
  destination = {};
  static stopped = 0;
  createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
  createAnalyser() {
    return { connect() {}, disconnect() {}, getByteFrequencyData() {}, getFloatTimeDomainData() {} };
  }
  createBuffer(_channels: number, count: number) {
    return { getChannelData: () => new Float32Array(count) };
  }
  createBufferSource() {
    return { connect() {}, disconnect() {}, start() {}, stop() { VoiceAudioContext.stopped += 1; } };
  }
  async close() { this.state = "closed"; }
}

function replaceProperty(target: object, key: string, value: unknown) {
  const previous = Object.getOwnPropertyDescriptor(target, key);
  Object.defineProperty(target, key, { configurable: true, writable: true, enumerable: true, value });
  return () => {
    if (previous) Object.defineProperty(target, key, previous);
    else Reflect.deleteProperty(target, key);
  };
}

function installVoiceEnvironment(test: TestContext) {
  const restore = [
    replaceProperty(process.env, "NEXT_PUBLIC_ENABLE_AUDIO_INTERFACE", "true"),
    replaceProperty(globalThis, "WebSocket", VoiceSocket),
    replaceProperty(globalThis, "MediaRecorder", VoiceRecorder),
    replaceProperty(globalThis, "AudioContext", VoiceAudioContext),
    replaceProperty(globalThis, "addEventListener", window.addEventListener.bind(window)),
    replaceProperty(globalThis, "removeEventListener", window.removeEventListener.bind(window)),
    replaceProperty(globalThis, "matchMedia", () => ({ matches: true, addEventListener() {}, removeEventListener() {} })),
    replaceProperty(navigator, "mediaDevices", {
      getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }),
    }),
    replaceProperty(globalThis, "fetch", async (url: string) => new Response(JSON.stringify(
      url.endsWith("/audio/status")
        ? {
            enabled: true,
            connected_clients: 1,
            active_recordings: 0,
            runtime_snapshot: { provider: "ollama", model_name: "lfm3-omni:2b" },
          }
        : { models: [] },
    ))),
  ];
  test.after(async () => {
    await act(async () => cleanup());
    restore.reverse().forEach((reset) => reset());
    VoiceSocket.instances = [];
    VoiceAudioContext.stopped = 0;
  });
}

it("keeps the attached image, audio, sources, and follow-up on the Full voice connection", async (test) => {
  installVoiceEnvironment(test);
  await act(async () => render(<VoiceCommandCenter />));
  const socket = VoiceSocket.instances.at(-1);
  assert.ok(socket);
  const socketCount = VoiceSocket.instances.length;
  await act(async () => socket.open());

  const imageInput = screen.getByLabelText("Dołącz obraz do pytania głosowego");
  const gif = new window.File(["image"], "invalid.gif", { type: "image/gif" });
  fireEvent.change(imageInput, { target: { files: [gif] } });
  assert.match(screen.getByRole("alert").textContent ?? "", /JPEG lub PNG/);

  const image = new window.File(["screen"], "screen.png", { type: "image/png" });
  fireEvent.change(imageInput, { target: { files: [image] } });
  const record = screen.getByRole<HTMLButtonElement>("button", { name: /Przytrzymaj i mów/ });
  await waitFor(() => assert.equal(record.disabled, false));

  const recordTurn = async () => {
    const start = socket.sent.length;
    await act(async () => fireEvent.pointerDown(record));
    await act(async () => fireEvent.pointerUp(record));
    const frames = socket.sent.slice(start);
    assert.equal(frames.length, 4);
    const [configuration, startRecording, audio, stopRecording] = frames;
    assert.equal(JSON.parse(configuration as string).command, "audio_config");
    assert.ok(audio instanceof window.Blob);
    assert.deepEqual(JSON.parse(stopRecording as string), { command: "stop_recording" });
    return JSON.parse(startRecording as string);
  };

  const first = await recordTurn();
  assert.equal(first.command, "start_recording");
  assert.equal(first.multimodal, true);
  assert.equal(first.image, "c2NyZWVu");
  assert.equal(record.disabled, true);
  await act(async () => socket.receive({ type: "complete" }));
  assert.equal(record.disabled, true);
  await act(async () => socket.receive({ type: "complete", multimodal: true, no_speech: true }));
  assert.equal(record.disabled, false);
  assert.ok(screen.getByText("screen.png"));
  await screen.findByText("Nie rozpoznano mowy.");
  const retry = await recordTurn();
  assert.equal(retry.image, "c2NyZWVu");
  await act(async () => {
    socket.receive({ type: "response_text", text: "Sprawdź kod błędu.", question: "Co zrobić z błędem?", sources: ["Instrukcja E42"], multimodal: true });
    socket.receive({ type: "audio_response", audio: "AAABAAIAAwA=", sample_rate: 24000 });
    socket.receive({ type: "complete", multimodal: true });
  });
  assert.ok(screen.getByText("Instrukcja E42"));
  await screen.findByText("Sprawdź kod błędu.");
  assert.ok(screen.getByText("Co zrobić z błędem?"));
  assert.equal(screen.queryByText("screen.png"), null);
  fireEvent.click(screen.getByRole("button", { name: "Zatrzymaj odtwarzanie" }));
  assert.equal(VoiceAudioContext.stopped, 1);
  assert.equal(VoiceSocket.instances.length, socketCount);

  const next = await recordTurn();
  assert.equal(next.multimodal, true);
  assert.equal(next.image, undefined);
  await act(async () => {
    socket.receive({ type: "response_text", text: "Zacznij od ustawień.", multimodal: true });
    socket.receive({ type: "complete", multimodal: true });
  });
  assert.equal(screen.queryByText("Instrukcja E42"), null);

  fireEvent.click(screen.getByRole("button", { name: "Zakończ rozmowę o obrazie" }));
  const regular = await recordTurn();
  assert.equal(regular.multimodal, false);
  assert.equal(regular.image, undefined);
  assert.equal(VoiceSocket.instances.length, socketCount);

});

it("uses one Full voice socket and unlocks a pending image turn after reconnecting", async (test) => {
  installVoiceEnvironment(test);
  await act(async () => render(<VoiceCommandCenter />));
  assert.equal(VoiceSocket.instances.length, 1);
  const [socket] = VoiceSocket.instances;
  await act(async () => socket.open());

  const imageInput = screen.getByLabelText("Dołącz obraz do pytania głosowego");
  const image = new window.File(["screen"], "screen.png", { type: "image/png" });
  fireEvent.change(imageInput, { target: { files: [image] } });
  const record = screen.getByRole<HTMLButtonElement>("button", { name: /Przytrzymaj i mów/ });
  await waitFor(() => assert.equal(record.disabled, false));

  await act(async () => fireEvent.pointerDown(record));
  await act(async () => fireEvent.pointerUp(record));
  assert.equal(record.disabled, true);

  await act(async () => socket.close(1006));
  assert.equal(screen.queryByText("screen.png"), null);
  await waitFor(() => assert.equal(VoiceSocket.instances.length, 2), { timeout: 2500 });
  await act(async () => VoiceSocket.instances[1].open());
  await waitFor(() => assert.equal(record.disabled, false));
});


it("sends Direct mode before a Full voice turn and preserves explicit agent selection", async (test) => {
  installVoiceEnvironment(test);
  let view!: ReturnType<typeof render>;
  await act(async () => { view = render(<VoiceCommandCenter voiceModePreset="direct" />); });
  const socket = VoiceSocket.instances.at(-1);
  assert.ok(socket);
  await act(async () => socket.open());
  const modes = () => socket.sent.filter((item): item is string => typeof item === "string")
    .map(item => JSON.parse(item)).filter(item => item.command === "voice_mode").map(item => item.mode);
  await waitFor(() => assert.deepEqual(modes(), ["direct"]));
  await act(async () => view.rerender(<VoiceCommandCenter voiceModePreset="standard" />));
  await waitFor(() => assert.deepEqual(modes(), ["direct", "standard"]));
});

it("keeps mode switching busy during microphone permission and rejects a stale mode", async test => {
  installVoiceEnvironment(test);
  let grant!: (stream: Pick<MediaStream, "getTracks">) => void;
  const permission = new Promise<Pick<MediaStream, "getTracks">>(resolve => { grant = resolve; });
  const getUserMedia = test.mock.fn(() => permission);
  const restore = replaceProperty(navigator, "mediaDevices", { getUserMedia });
  const onTurnBusy = test.mock.fn();
  let view!: ReturnType<typeof render>;
  try {
    await act(async () => {
      view = render(<VoiceCommandCenter voiceModePreset="direct" generationMode="interleaved" onTurnBusy={onTurnBusy} />);
    });
    const [socket] = VoiceSocket.instances;
    assert.ok(socket);
    await act(async () => socket.open());
    const record = screen.getByRole<HTMLButtonElement>("button", { name: /Przytrzymaj i mów/ });
    await waitFor(() => assert.equal(record.disabled, false));
    const callsBeforeRecording = getUserMedia.mock.callCount();
    await act(async () => fireEvent.pointerDown(record));
    assert.equal(getUserMedia.mock.callCount(), callsBeforeRecording + 1);
    assert.equal(onTurnBusy.mock.calls.at(-1)?.arguments[0], true);
    await act(async () => {
      view.rerender(<VoiceCommandCenter voiceModePreset="direct" generationMode="audio" onTurnBusy={onTurnBusy} />);
    });
    await act(async () => grant({ getTracks: () => [] }));
    const sent = socket.sent.filter((frame): frame is string => typeof frame === "string")
      .map(frame => JSON.parse(frame).command);
    assert.ok(sent.includes("reset_native_dialogue"));
    assert.ok(!sent.includes("start_recording"));
    assert.equal(onTurnBusy.mock.calls.at(-1)?.arguments[0], false);
  } finally {
    restore();
  }
});

it("Full sends native generation modes, plays audio-only replies and resets the conversation on the same socket", async test => {
  installVoiceEnvironment(test);
  const onTranscriptReady = test.mock.fn();
  let view!: ReturnType<typeof render>;
  await act(async () => {
    view = render(<VoiceCommandCenter voiceModePreset="direct" generationMode="interleaved" onTranscriptReady={onTranscriptReady} />);
  });
  const [socket] = VoiceSocket.instances;
  assert.ok(socket);
  await act(async () => socket.open());

  const record = screen.getByRole<HTMLButtonElement>("button", { name: /Przytrzymaj i mów/ });
  const controls = () => socket.sent
    .filter((frame): frame is string => typeof frame === "string")
    .map(frame => JSON.parse(frame));
  const recordTurn = async () => {
    await waitFor(() => assert.equal(record.disabled, false));
    await act(async () => fireEvent.pointerDown(record));
    await act(async () => fireEvent.pointerUp(record));
    const [start] = controls().filter(frame => frame.command === "start_recording").slice(-1);
    assert.equal(start.multimodal, true);
    assert.equal(start.image, undefined);
    assert.equal(record.disabled, true);
    return start;
  };

  assert.equal((await recordTurn()).generation_mode, "interleaved");
  await act(async () => {
    socket.receive({ type: "response_text", text: "Własny tekst Omni.", multimodal: true, generation_mode: "interleaved" });
    socket.receive({ type: "audio_response", audio: "AAABAAIAAwA=", sample_rate: 24000 });
    socket.receive({ type: "complete", multimodal: true, generation_mode: "interleaved" });
  });
  await screen.findByText("Własny tekst Omni.");
  assert.equal(screen.queryByText("Pytanie głosowe"), null);
  await screen.findByRole("button", { name: "Zatrzymaj odtwarzanie" });
  fireEvent.click(screen.getByRole("button", { name: "Zatrzymaj odtwarzanie" }));

  await act(async () => {
    view.rerender(<VoiceCommandCenter voiceModePreset="direct" generationMode="audio" onTranscriptReady={onTranscriptReady} />);
  });
  assert.equal(controls().at(-1).command, "reset_native_dialogue");
  await act(async () => {
    view.rerender(<VoiceCommandCenter voiceModePreset="direct" generationMode="interleaved" onTranscriptReady={onTranscriptReady} />);
  });
  assert.equal(screen.queryByRole("button", { name: "Zakończ natywną rozmowę" }), null);
  await act(async () => {
    view.rerender(<VoiceCommandCenter voiceModePreset="direct" generationMode="audio" onTranscriptReady={onTranscriptReady} />);
  });
  assert.equal((await recordTurn()).generation_mode, "audio");
  await act(async () => {
    socket.receive({ type: "response_text", text: null, multimodal: true, generation_mode: "audio" });
    socket.receive({ type: "audio_response", audio: "AAABAAIAAwA=", sample_rate: 24000 });
    socket.receive({ type: "complete", multimodal: true, generation_mode: "audio" });
  });
  await screen.findByText("Odpowiedź dźwiękowa");
  assert.equal(screen.queryByText("Własny tekst Omni."), null);
  assert.equal(screen.queryByText("Pytanie głosowe"), null);
  assert.equal(onTranscriptReady.mock.callCount(), 0);
  await screen.findByRole("button", { name: "Zatrzymaj odtwarzanie" });
  fireEvent.click(screen.getByRole("button", { name: "Zatrzymaj odtwarzanie" }));
  fireEvent.click(screen.getByRole("button", { name: "Zakończ natywną rozmowę" }));
  assert.equal(controls().at(-1).command, "end_native_dialogue");
  assert.equal(screen.queryByText("Odpowiedź dźwiękowa"), null);
  assert.equal(VoiceSocket.instances.length, 1);

  assert.equal((await recordTurn()).generation_mode, "audio");
  await act(async () => {
    socket.receive({
      type: "error", multimodal: true, generation_mode: "audio", reason_code: "omni_native_unavailable",
    });
  });
  await screen.findByText(/Wybrany tryb natywny Omni jest niedostępny/);
  assert.equal(record.disabled, false);

  assert.equal((await recordTurn()).generation_mode, "audio");
  await act(async () => socket.receive({ type: "audio_response", audio: "AAABAAIAAwA=", sample_rate: 24000 }));
  await screen.findByRole("button", { name: "Zatrzymaj odtwarzanie" });
  const stoppedBeforeCancel = VoiceAudioContext.stopped;
  fireEvent.click(screen.getByRole("button", { name: "Anuluj odpowiedź Omni" }));
  assert.equal(VoiceAudioContext.stopped, stoppedBeforeCancel + 1);
  const cancel = controls().at(-1);
  assert.equal(cancel.command, "reset_native_dialogue");
  assert.equal(typeof cancel.cancel_id, "string");
  await act(async () => {
    socket.receive({ type: "response_text", text: "Stara odpowiedź", multimodal: true, generation_mode: "audio" });
    socket.receive({ type: "audio_response", audio: "AAABAAIAAwA=", sample_rate: 24000 });
    socket.receive({ type: "complete", multimodal: true, generation_mode: "audio" });
    socket.receive({ type: "native_dialogue_reset", cancel_id: "unrelated" });
  });
  assert.equal(screen.queryByText("Stara odpowiedź"), null);
  assert.equal(screen.queryByRole("button", { name: "Zatrzymaj odtwarzanie" }), null);
  assert.equal(record.disabled, true);
  await act(async () => socket.receive({ type: "native_dialogue_reset", cancel_id: cancel.cancel_id }));
  await screen.findByText("Odpowiedź Omni anulowana.");
  assert.equal(record.disabled, false);
});
