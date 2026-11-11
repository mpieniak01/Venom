"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage } from "@/components/cockpit/cockpit-chat-thread";
import { createAudioCapture, createPilotAudioCapture, sendMultimodalVoiceTurn, speakChatAudio, transcribeChatAudio, type AudioCapture, type NativeVoiceGenerationMode, type PcmCapture } from "@/lib/chat-audio";
import { voiceRecorderMimeType } from "@/lib/voice-media-recorder";
export type StudioVoiceStatus = "voiceIdle" | "permission" | "listening" | "transcribing" | "generating" | "speaking" | "muted" | "voiceEnded";
export type StudioVoiceOptions = { session: string; stopRevision?: number; mode: "dictation" | "conversation"; language: string; busy: boolean; messages: ChatMessage[];
  onDraft: (text: string) => void; onTurn: (text: string) => Promise<boolean>; onStop: () => Promise<void>; onClose: () => void;
  multimodalEnabled?: boolean; generationMode?: NativeVoiceGenerationMode | null;
  onMultimodalBusy?: (busy: boolean) => void; onMultimodalCommit?: () => void };
type CapturedVoiceTurn = {
  audio: PcmCapture | Blob;
  options: StudioVoiceOptions;
  signal: AbortSignal;
  isCurrent: () => boolean;
};
type ActiveCapture = {
  recording: AudioCapture<PcmCapture | Blob>;
  useMultimodal: boolean;
  generationMode?: NativeVoiceGenerationMode;
};
const MAX_VOICE_IMAGE_BYTES = 2 * 1024 * 1024;
/** Map capture failures without treating unrelated errors as permission denial. */
function captureError(cause: unknown): "micDenied" | "micUnavailable" | "voiceError" {
  if (cause instanceof DOMException && cause.name === "NotAllowedError") return "micDenied";
  if (cause instanceof Error && cause.message === "micUnavailable") return "micUnavailable";
  return "voiceError";
}

/** Keep translated turn failures specific and use the generic key for other errors. */
function voiceTurnError(cause: unknown): string {
  if (cause instanceof Error && ["voiceWait", "voiceImageInvalid", "voiceNativeUnavailable"].includes(cause.message)) {
    return cause.message;
  }
  return "voiceError";
}

/** Keep microphone capture, response playback and cancellation bound to the Studio session. */
export function useStudioVoice(options: StudioVoiceOptions, captureFactory?: typeof createAudioCapture) {
  const [status, setStatus] = useState<StudioVoiceStatus>("voiceIdle");
  const [error, setError] = useState<string | null>(null);
  const [image, setImage] = useState<File | null>(null);
  const [sources, setSources] = useState<string[]>([]);
  const [nativeAudioOnly, setNativeAudioOnly] = useState(false);
  const selectedImage = useRef<File | null>(null);
  const multimodalContext = useRef(false);
  const multimodalPending = useRef(false);
  const epoch = useRef(0);
  const capture = useRef<ActiveCapture | null>(null);
  const permission = useRef<AbortController | null>(null);
  const starting = useRef(false);
  const finishing = useRef(false);
  const request = useRef<AbortController | null>(null);
  const playback = useRef<{ audio: HTMLAudioElement; url: string } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const waiting = useRef<{ previous: Set<string>; observedBusy: boolean } | null>(null);
  const latest = useRef(options);
  useEffect(() => { latest.current = options; }, [options]);
  const releasePlayback = useCallback(() => {
    const current = playback.current; playback.current = null;
    if (current) { current.audio.onended = null; current.audio.onerror = null; current.audio.pause(); current.audio.removeAttribute("src"); URL.revokeObjectURL(current.url); }
  }, []);
  const releaseCapture = useCallback(() => {
    capture.current?.recording.dispose(); capture.current = null;
    if (timer.current) { clearTimeout(timer.current); }
    timer.current = null;
  }, []);
  useEffect(() => {
    if (options.multimodalEnabled) return;
    // Model capabilities refresh independently of the microphone lifecycle.
    multimodalContext.current = false;
    selectedImage.current = null;
    setImage(null);
    setSources([]);
  }, [options.multimodalEnabled]);
  useEffect(() => {
    multimodalContext.current = false;
    setNativeAudioOnly(false);
  }, [options.generationMode]);
  const setMultimodalBusy = useCallback((busy: boolean) => {
    if (multimodalPending.current === busy) return;
    multimodalPending.current = busy;
    latest.current.onMultimodalBusy?.(busy);
  }, []);
  const reset = useCallback(() => {
    setMultimodalBusy(false);
    epoch.current++; permission.current?.abort(); permission.current = null; waiting.current = null; request.current?.abort(); request.current = null;
    releaseCapture(); releasePlayback(); starting.current = false; finishing.current = false;
  }, [releaseCapture, releasePlayback, setMultimodalBusy]);
  useEffect(() => () => reset(), [options.session, options.mode, reset]);
  const previousStop = useRef(options.stopRevision);
  useEffect(() => {
    if (options.stopRevision !== previousStop.current) { previousStop.current = options.stopRevision; reset(); setStatus("voiceIdle"); }
  }, [options.stopRevision, reset]);
  const playReply = useCallback(async (blob: Blob, isCurrent: () => boolean) => {
    if (!isCurrent()) return;
    releasePlayback();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    playback.current = { audio, url };
    setStatus("speaking");
    audio.onended = () => {
      if (!isCurrent()) return;
      releasePlayback();
      setStatus("voiceIdle");
    };
    audio.onerror = () => {
      if (!isCurrent()) return;
      releasePlayback();
      setError("voiceError");
      setStatus("voiceIdle");
    };
    try {
      await audio.play();
    } catch (cause) {
      if (isCurrent()) releasePlayback();
      throw cause;
    }
  }, [releasePlayback]);
  const speak = useCallback(async (text: string, preferNative = true) => {
    const current = epoch.current;
    const controller = new AbortController(); request.current?.abort(); request.current = controller;
    const isCurrent = () => !controller.signal.aborted && current === epoch.current;
    setStatus("speaking");
    try {
      const blob = await speakChatAudio(latest.current.session, text, controller.signal, latest.current.language, preferNative);
      await playReply(blob, isCurrent);
    } catch { if (isCurrent()) { setError("voiceError"); setStatus("voiceIdle"); } }
  }, [playReply]);
  useEffect(() => {
    const turn = waiting.current;
    if (!turn) return;
    if (options.busy) turn.observedBusy = true;
    const answer = [...options.messages].reverse().find(message => message.role === "assistant" && message.text && !message.pending && !["FAILED", "CANCELLED", "LOST"].includes(message.status ?? "") && !turn.previous.has(message.bubbleId));
    if (answer && !options.busy) { waiting.current = null; void speak(answer.text); }
    else if (!options.busy && turn.observedBusy) { waiting.current = null; setError("voiceError"); setStatus("voiceIdle"); }
  }, [options.messages, options.busy, speak]);
  const selectImage = useCallback((file: File | null) => {
    if (file && (file.size === 0 || !["image/png", "image/jpeg"].includes(file.type))) {
      setError("voiceImageInvalid");
      return;
    }
    if (file && file.size > MAX_VOICE_IMAGE_BYTES) {
      setError("voiceImageTooLarge");
      return;
    }
    selectedImage.current = file;
    setImage(file);
    setError(null);
  }, []);
  const idleWithError = useCallback((key: string) => {
    setError(key);
    setStatus("voiceIdle");
  }, []);
  /** Publish the reply and sources only while the originating voice request is current. */
  const submitMultimodalTurn = useCallback(async (
    { audio, options: voiceOptions, signal, isCurrent }: CapturedVoiceTurn,
    attachment: File | null,
    generationMode?: NativeVoiceGenerationMode,
  ) => {
    if ((audio instanceof Blob ? audio.size : audio.pcm.byteLength) === 0) {
      idleWithError("silence");
      return;
    }
    const reply = await sendMultimodalVoiceTurn(
      voiceOptions.session, audio, voiceOptions.language, attachment, signal, generationMode,
    );
    if (!isCurrent() || reply.session_id !== latest.current.session) return;
    if (reply.no_speech) {
      idleWithError("silence");
      return;
    }

    let nativeWav: Blob | undefined;
    if (generationMode) {
      if (reply.generation_mode !== generationMode || !reply.audio_base64) {
        idleWithError("voiceError");
        return;
      }
      const bytes = Uint8Array.from(atob(reply.audio_base64), character => character.codePointAt(0) ?? 0);
      nativeWav = new Blob([bytes], { type: "audio/wav" });
    }
    multimodalContext.current = true;
    selectImage(null);
    setSources(reply.sources);
    setNativeAudioOnly(Boolean(nativeWav && !reply.text));
    voiceOptions.onMultimodalCommit?.();
    if (nativeWav) await playReply(nativeWav, isCurrent);
    else if (reply.text) await speak(reply.text, true);
    else idleWithError("voiceError");
  }, [idleWithError, playReply, selectImage, speak]);

  /** Route a transcript to the draft or start a normal chat turn. */
  const submitTranscribedTurn = useCallback(async ({
    audio, options: voiceOptions, signal, isCurrent,
  }: CapturedVoiceTurn) => {
    if (audio instanceof Blob) {
      idleWithError("voiceWait");
      return;
    }
    if (!audio.pcm.byteLength) {
      idleWithError("silence");
      return;
    }
    setSources([]);
    const result = await transcribeChatAudio(voiceOptions.session, audio, voiceOptions.language, signal, true);
    if (!isCurrent()) return;
    if (result.session_id !== voiceOptions.session) {
      idleWithError("voiceError");
      return;
    }

    const text = result.text.trim();
    if (!text) {
      idleWithError("silence");
      return;
    }
    if (latest.current.mode === "dictation") {
      latest.current.onDraft(text);
      setStatus("voiceIdle");
      return;
    }

    waiting.current = { previous: new Set(latest.current.messages.map(message => message.bubbleId)), observedBusy: false };
    setStatus("generating");
    const accepted = await latest.current.onTurn(text);
    if (isCurrent() && !accepted) {
      waiting.current = null;
      latest.current.onDraft(text);
      idleWithError("voiceDraftSaved");
    }
  }, [idleWithError]);

  /** Dispose this recording without resetting capture state from a newer epoch. */
  const settleCapture = useCallback((active: ActiveCapture, current: number) => {
    active.recording.dispose();
    if (capture.current === active) capture.current = null;
    if (current !== epoch.current) return;
    finishing.current = false;
    if (active.useMultimodal) setMultimodalBusy(false);
  }, [setMultimodalBusy]);

  /** Flush the active capture and dispatch it through its selected voice path. */
  const finish = useCallback(async () => {
    const active = capture.current;
    if (!active || finishing.current) return;
    const { recording, useMultimodal, generationMode } = active;
    finishing.current = true;
    const current = epoch.current;
    const voiceOptions = latest.current;
    const attachment = selectedImage.current;
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    const controller = new AbortController();
    request.current?.abort();
    request.current = controller;
    const isCurrent = () => current === epoch.current && !controller.signal.aborted;
    setStatus(useMultimodal ? "generating" : "transcribing");

    try {
      if (useMultimodal && voiceOptions.busy) {
        idleWithError("voiceWait");
        return;
      }
      if (useMultimodal) setMultimodalBusy(true);
      const audio = await recording.finish();
      if (capture.current === active) capture.current = null;
      if (current !== epoch.current) return;

      const turn = { audio, options: voiceOptions, signal: controller.signal, isCurrent };
      if (useMultimodal) await submitMultimodalTurn(turn, attachment, generationMode);
      else await submitTranscribedTurn(turn);
    } catch (cause) {
      if (isCurrent()) idleWithError(voiceTurnError(cause));
    } finally {
      settleCapture(active, current);
    }
  }, [idleWithError, setMultimodalBusy, settleCapture, submitMultimodalTurn, submitTranscribedTurn]);
  const finishRef = useRef(finish);
  useEffect(() => { finishRef.current = finish; }, [finish]);
  const start = useCallback(async () => {
    if (starting.current || capture.current || latest.current.busy || finishing.current) return;
    starting.current = true; setError(null); setNativeAudioOnly(false); setStatus("permission");
    releasePlayback(); const current = epoch.current;
    const controller = new AbortController(); permission.current = controller;
    try {
      const onLimit = () => { void finishRef.current(); };
      const voiceOptions = latest.current;
      const generationMode = voiceOptions.mode === "conversation"
        ? voiceOptions.generationMode ?? undefined : undefined;
      const pilot = Boolean(generationMode) || (
        voiceOptions.mode === "conversation" && voiceOptions.multimodalEnabled === true
        && (selectedImage.current !== null || multimodalContext.current)
      );
      const mimeType = pilot && !captureFactory ? voiceRecorderMimeType() : "";
      const microphone = mimeType
        ? await createPilotAudioCapture(mimeType, controller.signal, onLimit)
        : await (captureFactory ?? createAudioCapture)(onLimit, controller.signal);
      if (current !== epoch.current) { microphone.dispose(); return; }
      capture.current = { recording: microphone, useMultimodal: pilot, generationMode };
      setStatus("listening");
      timer.current = setTimeout(() => { void finishRef.current(); }, 60000);
    } catch (cause) {
      if (current === epoch.current) {
        setError(captureError(cause));
        setStatus("voiceIdle");
      }
    } finally { if (current === epoch.current) starting.current = false; }
  }, [captureFactory, releasePlayback]);
  const mute = useCallback(() => { reset(); setStatus("muted"); }, [reset]);
  const stop = useCallback(async () => {
    const ownsTurn = !!waiting.current; reset(); setStatus("voiceIdle");
    if (ownsTurn) await latest.current.onStop();
  }, [reset]);
  const end = useCallback(() => {
    const ownsTurn = !!waiting.current; reset(); setStatus("voiceEnded");
    if (ownsTurn) void latest.current.onStop();
    latest.current.onClose();
  }, [reset]);
  return { status, error, image, selectImage, sources, nativeAudioOnly, start, finish, mute, stop, end };
}
