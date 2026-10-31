import { getApiBaseUrl } from "./env";
import { apiFetch } from "./api-client";
export type AudioCapture = { finish: () => Promise<{ pcm: ArrayBuffer; sampleRate: number }>; dispose: () => void };
export function encodeMonoPcm(frames: Float32Array[]): ArrayBuffer {
  const length = frames.reduce((total, frame) => total + frame.length, 0);
  const buffer = new ArrayBuffer(length * 2);
  const view = new DataView(buffer); let offset = 0;
  for (const frame of frames) for (const sample of frame) {
    const value = Number.isFinite(sample) ? Math.max(-1, Math.min(1, sample)) : 0;
    view.setInt16(offset, value < 0 ? Math.round(value * 32768) : Math.round(value * 32767), true); offset += 2;
  }
  return buffer;
}
export async function createAudioCapture(onLimit: () => void, signal?: AbortSignal): Promise<AudioCapture> {
  if (!navigator.mediaDevices?.getUserMedia || !globalThis.AudioContext || !globalThis.AudioWorkletNode) throw new Error("micUnavailable");
  if (signal?.aborted) throw new DOMException("Cancelled", "AbortError");
  const media = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
  if (signal?.aborted) { media.getTracks().forEach(track => track.stop()); throw new DOMException("Cancelled", "AbortError"); }
  let context: AudioContext | null = null;
  let node: AudioWorkletNode | null = null;
  let source: MediaStreamAudioSourceNode | null = null;
  let mute: GainNode | null = null;
  let disposed = false;
  const dispose = () => {
    if (disposed) return; disposed = true;
    signal?.removeEventListener("abort", dispose);
    media.getTracks().forEach(track => track.stop());
    node?.disconnect(); source?.disconnect(); mute?.disconnect();
    node?.port.close();
    if (context && context.state !== "closed") void context.close().catch(() => {});
  };
  signal?.addEventListener("abort", dispose, { once: true });
  try {
    context = new AudioContext({ sampleRate: 16000 });
    if (!context.audioWorklet) throw new Error("micUnavailable");
    await context.audioWorklet.addModule("/chat2-capture-worklet.js");
    if (signal?.aborted) throw new DOMException("Cancelled", "AbortError");
    await context.resume();
    if (signal?.aborted) throw new DOMException("Cancelled", "AbortError");
    node = new AudioWorkletNode(context, "venom-chat2-capture");
    source = context.createMediaStreamSource(media);
    mute = context.createGain(); mute.gain.value = 0;
    source.connect(node); node.connect(mute); mute.connect(context.destination);
    const frames: Float32Array[] = []; let samples = 0; let limited = false;
    const maxSamples = Math.min(context.sampleRate * 60, 4 * 1024 * 1024);
    let flushed: (() => void) | null = null;
    node.port.onmessage = event => {
      if (event.data?.flushed) { flushed?.(); return; }
      if (disposed || !(event.data instanceof ArrayBuffer)) return;
      const frame = new Float32Array(event.data);
      const remaining = maxSamples - samples;
      if (remaining > 0) { frames.push(frame.slice(0, remaining)); samples += Math.min(frame.length, remaining); }
      if (samples >= maxSamples && !limited) { limited = true; onLimit(); }
    };
    const sampleRate = context.sampleRate;
    let finishing: Promise<{ pcm: ArrayBuffer; sampleRate: number }> | null = null;
    return { dispose, finish: () => {
      if (finishing) return finishing;
      finishing = (async () => {
        if (disposed) throw new Error("capture_closed");
        try {
          await new Promise<void>((resolve, reject) => {
            const timeout = setTimeout(() => reject(new Error("capture_flush_failed")), 500);
            flushed = () => { clearTimeout(timeout); resolve(); };
            node!.port.postMessage({ type: "flush" });
          });
          return { pcm: encodeMonoPcm(frames), sampleRate };
        } finally { dispose(); }
      })();
      return finishing;
    } };
  } catch (error) { dispose(); throw error; }
}
export function transcribeChatAudio(session: string, capture: { pcm: ArrayBuffer; sampleRate: number }, language: string, signal: AbortSignal) {
  return apiFetch<{ session_id: string; text: string }>("/api/v1/chat/audio/transcribe?session_id=" + encodeURIComponent(session) + "&sample_rate=" + capture.sampleRate + "&language=" + encodeURIComponent(language), {
    method: "POST", body: capture.pcm, headers: { "Content-Type": "application/octet-stream" }, signal,
  });
}
export async function speakChatAudio(session: string, text: string, signal: AbortSignal) {
  const response = await fetch(getApiBaseUrl() + "/api/v1/chat/audio/speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: session, text }), signal });
  if (!response.ok) throw new Error("voiceError");
  return response.blob();
}
