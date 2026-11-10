import { getApiBaseUrl } from "./env";
import { apiFetch } from "./api-client";
import { normalizeRuntimeId } from "./cockpit-runtime-selection";
import { VOICE_MICROPHONE_CONSTRAINTS } from "./voice-media-recorder";

export type PcmCapture = { pcm: ArrayBuffer; sampleRate: number };
export type AudioCapture<T = PcmCapture> = { finish: () => Promise<T>; dispose: () => void };

const MAX_RECORDING_BYTES = 8 * 1024 * 1024;

/** Capture the same browser media container as Full for an Omni pilot turn. */
export async function createPilotAudioCapture(
  mimeType: string,
  signal: AbortSignal,
  onLimit: () => void,
): Promise<AudioCapture<Blob>> {
  signal.throwIfAborted();
  if (!navigator.mediaDevices?.getUserMedia) throw new Error("micUnavailable");
  const media = await navigator.mediaDevices.getUserMedia({ audio: VOICE_MICROPHONE_CONSTRAINTS });
  const releaseTracks = () => media.getTracks().forEach((track) => track.stop());
  let recorder: MediaRecorder;
  try {
    signal.throwIfAborted();
    recorder = new MediaRecorder(media, { mimeType });
  } catch (error) {
    releaseTracks();
    throw error;
  }

  const chunks: Blob[] = [];
  let size = 0;
  let disposed = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let complete!: (blob: Blob) => void;
  let fail!: (error: Error) => void;
  const result = new Promise<Blob>((resolve, reject) => {
    complete = resolve;
    fail = reject;
  });
  // Errors can arrive while the user is still recording.
  void result.catch(() => {});
  const cleanup = () => {
    if (disposed) return;
    disposed = true;
    clearTimeout(timer);
    signal.removeEventListener("abort", dispose);
    recorder.ondataavailable = recorder.onstop = recorder.onerror = null;
    releaseTracks();
  };
  const dispose = () => {
    cleanup();
    if (recorder.state !== "inactive") recorder.stop();
    fail(new DOMException("Cancelled", "AbortError"));
  };
  recorder.ondataavailable = (event) => {
    size += event.data.size;
    if (size > MAX_RECORDING_BYTES) {
      fail(new Error("audio_too_large"));
      dispose();
      onLimit();
    } else if (event.data.size > 0) {
      chunks.push(event.data);
    }
  };
  recorder.onstop = () => {
    cleanup();
    complete(new Blob(chunks, { type: recorder.mimeType || mimeType }));
  };
  recorder.onerror = () => {
    fail(new Error("capture_failed"));
    dispose();
  };
  signal.addEventListener("abort", dispose, { once: true });
  try {
    recorder.start(100);
  } catch (error) {
    dispose();
    throw error;
  }
  return { dispose, finish: () => {
    if (recorder.state !== "inactive") {
      timer = setTimeout(dispose, 1000);
      recorder.stop();
    }
    return result;
  } };
}
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
    if (disposed) return;
    disposed = true;
    signal?.removeEventListener("abort", dispose);
    media.getTracks().forEach(track => track.stop());
    node?.disconnect(); source?.disconnect(); mute?.disconnect();
    node?.port.close();
    if (context && context.state !== "closed") void context.close().catch(() => {});
  };
  signal?.addEventListener("abort", dispose, { once: true });
  try {
    context = new AudioContext();
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
export function transcribeChatAudio(session: string, capture: { pcm: ArrayBuffer; sampleRate: number }, language: string, signal: AbortSignal, preferNative = false) {
  return apiFetch<{ session_id: string; text: string }>("/api/v1/chat/audio/transcribe?session_id=" + encodeURIComponent(session) + "&sample_rate=" + capture.sampleRate + "&language=" + encodeURIComponent(language) + (preferNative ? "&prefer_native=true" : ""), {
    method: "POST", body: capture.pcm, headers: { "Content-Type": "application/octet-stream" }, signal,
  });
}
/** Limit the pilot UI to the selected Omni model on a loopback Ollama endpoint. */
export function supportsLocalOmniVoice(runtime: {
  active_server?: string | null;
  active_model?: string | null;
  active_endpoint?: string | null;
} | null | undefined): boolean {
  if (normalizeRuntimeId(runtime?.active_server) !== "ollama"
    || runtime?.active_model !== "lfm3-omni:2b" || !runtime.active_endpoint) return false;
  try {
    const host = new URL(runtime.active_endpoint).hostname;
    return host === "localhost" || host === "127.0.0.1" || host === "[::1]";
  } catch {
    return false;
  }
}

export type MultimodalVoiceReply = { session_id: string; text: string; sources: string[] };

/** Upload PCM and an optional image together, preserving the caller's cancellation signal. */
export async function sendMultimodalVoiceTurn(
  session: string,
  capture: PcmCapture | Blob,
  language: string,
  image: File | null,
  signal: AbortSignal,
): Promise<MultimodalVoiceReply> {
  const body = new FormData();
  body.set("session_id", session);
  body.set("language", language);
  if (capture instanceof Blob) {
    body.set("sample_rate", "16000");
    body.set("audio", capture, "voice-recording");
  } else {
    body.set("sample_rate", String(capture.sampleRate));
    body.set("audio", new Blob([capture.pcm], { type: "application/octet-stream" }), "voice.pcm");
  }
  if (image) body.set("image", image);
  const response = await fetch(getApiBaseUrl() + "/api/v1/chat/audio/multimodal-turn", {
    method: "POST",
    body,
    signal,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: { reason_code?: string } } | null;
    const reason = payload?.detail?.reason_code;
    if (reason === "omni_pilot_invalid_image") throw new Error("voiceImageInvalid");
    throw new Error(response.status === 409 ? "voiceWait" : "voiceError");
  }
  return response.json() as Promise<MultimodalVoiceReply>;
}

/** Synthesize a reply with the host voice or the explicitly selected native voice. */
export async function speakChatAudio(session: string, text: string, signal: AbortSignal, language = "pl", preferNative = true) {
  const response = await fetch(getApiBaseUrl() + "/api/v1/chat/audio/speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: session, text, prefer_native: preferNative, language }), signal });
  if (!response.ok) throw new Error("voiceError");
  return response.blob();
}
