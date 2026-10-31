"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage } from "@/components/cockpit/cockpit-chat-thread";
import { createAudioCapture, speakChatAudio, transcribeChatAudio, type AudioCapture } from "@/lib/chat-audio";
export type StudioVoiceStatus = "voiceIdle" | "permission" | "listening" | "transcribing" | "generating" | "speaking" | "muted" | "voiceEnded";
type VoiceOptions = { session: string; stopRevision?: number; mode: "dictation" | "conversation"; language: string; busy: boolean; messages: ChatMessage[];
  onDraft: (text: string) => void; onTurn: (text: string) => Promise<boolean>; onStop: () => Promise<void>; onClose: () => void };
/** Map capture failures without treating unrelated errors as permission denial. */
function captureError(cause: unknown): "micDenied" | "micUnavailable" | "voiceError" {
  if (cause instanceof DOMException && cause.name === "NotAllowedError") return "micDenied";
  if (cause instanceof Error && cause.message === "micUnavailable") return "micUnavailable";
  return "voiceError";
}

export function useStudioVoice(options: VoiceOptions, captureFactory: typeof createAudioCapture = createAudioCapture) {
  const [status, setStatus] = useState<StudioVoiceStatus>("voiceIdle");
  const [error, setError] = useState<string | null>(null);
  const epoch = useRef(0);
  const capture = useRef<AudioCapture | null>(null);
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
    capture.current?.dispose(); capture.current = null;
    if (timer.current) { clearTimeout(timer.current); }
    timer.current = null;
  }, []);
  const reset = useCallback(() => {
    epoch.current++; permission.current?.abort(); permission.current = null; waiting.current = null; request.current?.abort(); request.current = null;
    releaseCapture(); releasePlayback(); starting.current = false; finishing.current = false;
  }, [releaseCapture, releasePlayback]);
  useEffect(() => () => reset(), [options.session, options.mode, reset]);
  const previousStop = useRef(options.stopRevision);
  useEffect(() => {
    if (options.stopRevision !== previousStop.current) { previousStop.current = options.stopRevision; reset(); setStatus("voiceIdle"); }
  }, [options.stopRevision, reset]);
  const speak = useCallback(async (text: string) => {
    const current = epoch.current;
    const controller = new AbortController(); request.current?.abort(); request.current = controller;
    setStatus("speaking");
    try {
      const blob = await speakChatAudio(latest.current.session, text, controller.signal);
      if (controller.signal.aborted || current !== epoch.current) return;
      releasePlayback();
      const url = URL.createObjectURL(blob); const audio = new Audio(url);
      playback.current = { audio, url };
      audio.onended = () => { if (current === epoch.current) { releasePlayback(); setStatus("voiceIdle"); } };
      audio.onerror = () => { if (current === epoch.current) { releasePlayback(); setError("voiceError"); setStatus("voiceIdle"); } };
      await audio.play();
    } catch { if (!controller.signal.aborted && current === epoch.current) { releasePlayback(); setError("voiceError"); setStatus("voiceIdle"); } }
  }, [releasePlayback]);
  useEffect(() => {
    const turn = waiting.current;
    if (!turn) return;
    if (options.busy) turn.observedBusy = true;
    const answer = [...options.messages].reverse().find(message => message.role === "assistant" && message.text && !message.pending && !["FAILED", "CANCELLED", "LOST"].includes(message.status ?? "") && !turn.previous.has(message.bubbleId));
    if (answer && !options.busy) { waiting.current = null; void speak(answer.text); }
    else if (!options.busy && turn.observedBusy) { waiting.current = null; setError("voiceError"); setStatus("voiceIdle"); }
  }, [options.messages, options.busy, speak]);
  const finish = useCallback(async () => {
    if (!capture.current || finishing.current) return;
    finishing.current = true;
    const current = epoch.current;
    const recording = capture.current;
    if (timer.current) { clearTimeout(timer.current); }
    timer.current = null;
    const controller = new AbortController(); request.current?.abort(); request.current = controller;
    setStatus("transcribing");
    try {
      const audio = await recording.finish();
      if (capture.current === recording) capture.current = null;
      if (current !== epoch.current) return;
      const result = await transcribeChatAudio(latest.current.session, audio, latest.current.language, controller.signal);
      if (current !== epoch.current || controller.signal.aborted || result.session_id !== latest.current.session) return;
      const text = result.text.trim();
      if (!text) { setError("silence"); setStatus("voiceIdle"); return; }
      if (latest.current.mode === "dictation") { latest.current.onDraft(text); setStatus("voiceIdle"); return; }
      waiting.current = { previous: new Set(latest.current.messages.map(message => message.bubbleId)), observedBusy: false };
      setStatus("generating");
      const accepted = await latest.current.onTurn(text);
      if (current !== epoch.current || controller.signal.aborted) return;
      if (!accepted) { waiting.current = null; setError("voiceWait"); setStatus("voiceIdle"); }
    } catch { if (!controller.signal.aborted && current === epoch.current) { setError("voiceError"); setStatus("voiceIdle"); } }
    finally {
      recording.dispose();
      if (capture.current === recording) { capture.current = null; }
      if (current === epoch.current) { finishing.current = false; }
    }
  }, []);
  const finishRef = useRef(finish);
  useEffect(() => { finishRef.current = finish; }, [finish]);
  const start = useCallback(async () => {
    if (starting.current || capture.current || latest.current.busy || finishing.current) return;
    starting.current = true; setError(null); setStatus("permission");
    releasePlayback(); const current = epoch.current;
    const controller = new AbortController(); permission.current = controller;
    try {
      const microphone = await captureFactory(() => { void finishRef.current(); }, controller.signal);
      if (current !== epoch.current) { microphone.dispose(); return; }
      capture.current = microphone; setStatus("listening");
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
  return { status, error, start, finish, mute, stop, end };
}
