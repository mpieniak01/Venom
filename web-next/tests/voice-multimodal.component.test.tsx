import "./component-test-setup";
import assert from "node:assert/strict";
import { it } from "node:test";
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

it("keeps the attached image, audio, sources, and follow-up on the Full voice connection", async (test) => {
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
  await act(async () => {
    socket.receive({ type: "response_text", text: "Sprawdź kod błędu.", sources: ["Instrukcja E42"], multimodal: true });
    socket.receive({ type: "audio_response", audio: "AAABAAIAAwA=", sample_rate: 24000 });
    socket.receive({ type: "complete", multimodal: true });
  });
  assert.ok(screen.getByText("Instrukcja E42"));
  await screen.findByText("Sprawdź kod błędu.");
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
