import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import { createAudioCapture, encodeMonoPcm } from "../lib/chat-audio";

test("PCM encoding is finite, bounded mono signed little-endian with no lost frames", () => {
  const encoded = encodeMonoPcm([new Float32Array([-2, -1, -0.5]), new Float32Array([0, 0.5, 1, 2, NaN])]);
  const view = new DataView(encoded);
  assert.deepEqual(Array.from({ length: 8 }, (_, index) => view.getInt16(index * 2, true)), [-32768, -32768, -16384, 0, 16384, 32767, 32767, 0]);
});

test("worklet flush delivers the final short frame before acknowledging completion", () => {
  const sent: unknown[] = []; let Capture: new () => { process: (inputs: Float32Array[][]) => boolean; port: { onmessage: (event: unknown) => void } };
  class Processor { port = { postMessage: (value: unknown) => sent.push(value), onmessage: null }; }
  runInNewContext(readFileSync(new URL("../public/chat2-capture-worklet.js", import.meta.url), "utf8"), { AudioWorkletProcessor: Processor, Float32Array, Number, registerProcessor: (_name: string, type: typeof Capture) => { Capture = type; } });
  const capture = new Capture!();
  assert.equal(capture.process([[new Float32Array([0.25, -0.5, NaN])]]), true);
  assert.equal(sent.length, 0);
  capture.port.onmessage({ data: { type: "flush" } });
  assert.deepEqual([...new Float32Array(sent[0] as ArrayBuffer)], [0.25, -0.5, 0]);
  assert.equal((sent[1] as { flushed: boolean }).flushed, true);
});

test("permission arriving after cancellation stops its tracks before constructing an audio context", async () => {
  const mediaDescriptor = Object.getOwnPropertyDescriptor(globalThis.navigator, "mediaDevices");
  const contextDescriptor = Object.getOwnPropertyDescriptor(globalThis, "AudioContext");
  const workletDescriptor = Object.getOwnPropertyDescriptor(globalThis, "AudioWorkletNode");
  let resolve!: (value: MediaStream) => void; let stopped = 0; let contexts = 0;
  Object.defineProperty(globalThis.navigator, "mediaDevices", { configurable: true, value: { getUserMedia: () => new Promise<MediaStream>(ready => { resolve = ready; }) } });
  Object.defineProperty(globalThis, "AudioContext", { configurable: true, value: class { constructor() { contexts++; } } });
  Object.defineProperty(globalThis, "AudioWorkletNode", { configurable: true, value: class {} });
  try {
    const controller = new AbortController(); const pending = createAudioCapture(() => {}, controller.signal);
    controller.abort(); resolve({ getTracks: () => [{ stop: () => { stopped++; } }] } as unknown as MediaStream);
    await assert.rejects(pending, { name: "AbortError" }); assert.equal(stopped, 1); assert.equal(contexts, 0);
  } finally {
    for (const [object, name, descriptor] of [[globalThis.navigator, "mediaDevices", mediaDescriptor], [globalThis, "AudioContext", contextDescriptor], [globalThis, "AudioWorkletNode", workletDescriptor]] as const) {
      if (descriptor) Object.defineProperty(object, name, descriptor); else Reflect.deleteProperty(object, name);
    }
  }
});

test("ending during worklet setup releases the microphone before the module promise resolves", async () => {
  const mediaDescriptor = Object.getOwnPropertyDescriptor(globalThis.navigator, "mediaDevices");
  const contextDescriptor = Object.getOwnPropertyDescriptor(globalThis, "AudioContext");
  const workletDescriptor = Object.getOwnPropertyDescriptor(globalThis, "AudioWorkletNode");
  let ready!: () => void; let loaded!: () => void; let stopped = 0; let resumed = 0;
  const entered = new Promise<void>(resolve => { ready = resolve; });
  Object.defineProperty(globalThis.navigator, "mediaDevices", { configurable: true, value: { getUserMedia: async () => ({ getTracks: () => [{ stop: () => { stopped++; } }] }) } });
  Object.defineProperty(globalThis, "AudioContext", { configurable: true, value: class {
    state = "suspended";
    audioWorklet = { addModule: () => { ready(); return new Promise<void>(resolve => { loaded = resolve; }); } };
    resume = async () => { resumed++; }; close = async () => { this.state = "closed"; };
  } });
  Object.defineProperty(globalThis, "AudioWorkletNode", { configurable: true, value: class {} });
  try {
    const controller = new AbortController(); const pending = createAudioCapture(() => {}, controller.signal);
    await entered; controller.abort(); assert.equal(stopped, 1); loaded();
    await assert.rejects(pending, { name: "AbortError" }); assert.equal(stopped, 1); assert.equal(resumed, 0);
  } finally {
    for (const [object, name, descriptor] of [[globalThis.navigator, "mediaDevices", mediaDescriptor], [globalThis, "AudioContext", contextDescriptor], [globalThis, "AudioWorkletNode", workletDescriptor]] as const) {
      if (descriptor) Object.defineProperty(object, name, descriptor); else Reflect.deleteProperty(object, name);
    }
  }
});
