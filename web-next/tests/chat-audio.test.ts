import assert from "node:assert/strict";
import { test } from "node:test";
import { createAudioCapture } from "../lib/chat-audio";

for (const nativeRate of [44100, 48000]) {
  test(`capture preserves native ${nativeRate}Hz without overriding microphone rate`, async () => {
    const saved = [
      [navigator, "mediaDevices"], [globalThis, "AudioContext"], [globalThis, "AudioWorkletNode"],
    ].map(([object, key]) => ({ object: object as object, key: key as string, descriptor: Object.getOwnPropertyDescriptor(object, key as string) }));
    let stopped = 0;
    let closed = 0;
    const source = { connect: () => {}, disconnect: () => {} };
    class Context {
      constructor(options?: AudioContextOptions) { assert.equal(options, undefined); }
      sampleRate = nativeRate;
      state = "running";
      destination = {};
      audioWorklet = { addModule: async () => {} };
      resume = async () => {};
      close = async () => { closed++; this.state = "closed"; };
      createMediaStreamSource = () => source;
      createGain = () => ({ ...source, gain: { value: 1 } });
    }
    class Worklet {
      connect = () => {};
      disconnect = () => {};
      port = {
        onmessage: null as ((event: { data: unknown }) => void) | null,
        close: () => {},
        postMessage: () => { this.port.onmessage?.({ data: new Float32Array([0.5]).buffer }); this.port.onmessage?.({ data: { flushed: true } }); },
      };
    }
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: async () => ({ getTracks: () => [{ stop: () => { stopped++; } }] }) } });
    Object.defineProperty(globalThis, "AudioContext", { configurable: true, value: Context });
    Object.defineProperty(globalThis, "AudioWorkletNode", { configurable: true, value: Worklet });
    try {
      const capture = await createAudioCapture(() => {});
      const result = await capture.finish();
      assert.equal(result.sampleRate, nativeRate);
      assert.equal(new DataView(result.pcm).getInt16(0, true), 16384);
      assert.equal(stopped, 1);
      assert.equal(closed, 1);
      capture.dispose();
      assert.equal(stopped, 1);
    } finally {
      for (const { object, key, descriptor } of saved) {
        if (descriptor) Object.defineProperty(object, key, descriptor);
        else Reflect.deleteProperty(object, key);
      }
    }
  });
}
