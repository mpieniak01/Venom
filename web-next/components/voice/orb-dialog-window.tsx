"use client";

import { useEffect, useRef, useState } from "react";
import type { VoiceOrbState } from "@/components/voice/voice-orb";

type OrbDialogWindowProps = Readonly<{
  role: "user" | "assistant";
  text: string;
  orbState: VoiceOrbState;
  reducedMotion: boolean;
  emptyLabel?: string;
}>;

const TYPEWRITER_INTERVAL_MS = 18;

function getBubbleClass(role: "user" | "assistant", isEmpty: boolean): string {
  if (isEmpty) return "border-transparent bg-transparent";
  return role === "user"
    ? "border-white/10 bg-white/[0.05] text-zinc-200 self-end text-right"
    : "border-white/10 bg-white/[0.04] text-zinc-100 self-start text-left";
}

function getEnterClass(
  role: "user" | "assistant",
  entering: boolean,
  reducedMotion: boolean,
): string {
  if (!entering || reducedMotion) return "";
  return role === "user" ? "animate-orb-dialog-in-top" : "animate-orb-dialog-in-bottom";
}

function getOpacity(visible: boolean, isActive: boolean): number {
  if (!visible) return 0;
  return isActive ? 1 : 0.45;
}

function getSpeakerLabel(role: "user" | "assistant"): string {
  return role === "user" ? "Ty" : "Asystent";
}

export function OrbDialogWindow({
  role,
  text,
  orbState,
  reducedMotion,
  emptyLabel,
}: OrbDialogWindowProps) {
  const [displayed, setDisplayed] = useState(text);
  const [visible, setVisible] = useState(!!text);
  const [entering, setEntering] = useState(false);
  const prevTextRef = useRef(text);

  useEffect(() => {
    if (role !== "assistant" || !text) return;

    if (reducedMotion) {
      prevTextRef.current = text;
      const id = globalThis.setTimeout(() => setDisplayed(text), 0);
      return () => globalThis.clearTimeout(id);
    }

    const previousText = prevTextRef.current;
    const startIndex = text.startsWith(previousText) ? previousText.length : 0;
    prevTextRef.current = text;
    let index = startIndex;
    let intervalId: ReturnType<typeof setInterval> | null = null;
    const startId = globalThis.setTimeout(() => {
      setDisplayed(text.slice(0, index));
      intervalId = globalThis.setInterval(() => {
        index += 1;
        setDisplayed(text.slice(0, index));
        if (index >= text.length && intervalId) {
          globalThis.clearInterval(intervalId);
          intervalId = null;
        }
      }, TYPEWRITER_INTERVAL_MS);
    }, 0);

    return () => {
      globalThis.clearTimeout(startId);
      if (intervalId) globalThis.clearInterval(intervalId);
    };
  }, [text, role, reducedMotion]);

  useEffect(() => {
    if (role !== "user") return;
    prevTextRef.current = text;
    const id = globalThis.setTimeout(() => setDisplayed(text), 0);
    return () => globalThis.clearTimeout(id);
  }, [text, role]);

  useEffect(() => {
    if (text) {
      const visibleId = globalThis.setTimeout(() => setVisible(true), 0);
      const enterId = reducedMotion ? null : globalThis.setTimeout(() => setEntering(true), 0);
      const exitId = reducedMotion ? null : globalThis.setTimeout(() => setEntering(false), 240);
      return () => {
        globalThis.clearTimeout(visibleId);
        if (enterId) globalThis.clearTimeout(enterId);
        if (exitId) globalThis.clearTimeout(exitId);
      };
    }

    const hideId = globalThis.setTimeout(() => setVisible(false), 0);
    return () => globalThis.clearTimeout(hideId);
  }, [text, reducedMotion]);

  const isActive =
    (role === "user" && (orbState === "recording" || orbState === "stt")) ||
    (role === "assistant" && (orbState === "thinking" || orbState === "tts" || orbState === "complete"));

  const isEmpty = !text;

  const bubbleClasses = [
    "w-full rounded-2xl border px-4 py-3 text-sm leading-relaxed",
    "transition-all duration-300",
    getBubbleClass(role, isEmpty),
    isActive ? "border-white/15" : "",
    getEnterClass(role, entering, reducedMotion),
  ]
    .filter(Boolean)
    .join(" ");

  const opacity = getOpacity(visible, isActive);

  return (
    <div
      className="w-full"
      style={{
        minHeight: "56px",
        display: "flex",
        alignItems: "center",
        transition: "opacity 600ms ease",
        opacity,
      }}
      aria-live={role === "assistant" ? "polite" : "off"}
      aria-atomic="true"
    >
      {visible && (
        <div className={bubbleClasses}>
          <span className="mb-1 block text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
            {getSpeakerLabel(role)}
          </span>
          <span>{displayed || emptyLabel}</span>
        </div>
      )}
    </div>
  );
}
