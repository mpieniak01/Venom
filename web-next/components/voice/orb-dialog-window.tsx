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

const FADE_DELAY_MS = 5000;
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
  const fadeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Typewriter for assistant bubble
  useEffect(() => {
    if (role !== "assistant" || !text) return;

    if (reducedMotion) {
      const id = globalThis.setTimeout(() => setDisplayed(text), 0);
      return () => globalThis.clearTimeout(id);
    }

    let i = prevTextRef.current === text ? text.length : 0;
    prevTextRef.current = text;
    let intervalId: ReturnType<typeof setInterval> | null = null;
    const startId = globalThis.setTimeout(() => {
      setDisplayed(text.slice(0, i));
      intervalId = globalThis.setInterval(() => {
        i += 1;
        setDisplayed(text.slice(0, i));
        if (i >= text.length && intervalId) {
          clearInterval(intervalId);
        }
      }, TYPEWRITER_INTERVAL_MS);
    }, 0);

    return () => {
      globalThis.clearTimeout(startId);
      if (intervalId) clearInterval(intervalId);
    };
  }, [text, role, reducedMotion]);

  // For user bubble just show full text immediately
  useEffect(() => {
    if (role !== "user") return;
    prevTextRef.current = text;
    const id = globalThis.setTimeout(() => setDisplayed(text), 0);
    return () => globalThis.clearTimeout(id);
  }, [text, role]);

  // Visibility + enter animation on text change
  useEffect(() => {
    if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current);

    if (text) {
      const visibleId = globalThis.setTimeout(() => setVisible(true), 0);
      if (!reducedMotion) {
        const enterId = globalThis.setTimeout(() => setEntering(true), 0);
        const exitId = globalThis.setTimeout(() => setEntering(false), 240);
        return () => {
          globalThis.clearTimeout(visibleId);
          globalThis.clearTimeout(enterId);
          globalThis.clearTimeout(exitId);
        };
      }
    } else {
      const id = globalThis.setTimeout(() => setVisible(false), 0);
      return () => globalThis.clearTimeout(id);
    }
  }, [text, reducedMotion]);

  // Auto-fade after conversation ends
  useEffect(() => {
    if (!text) return;
    const isActive =
      orbState === "recording" ||
      orbState === "stt" ||
      orbState === "thinking" ||
      orbState === "tts";

    if (!isActive) {
      fadeTimerRef.current = setTimeout(() => {
        // just dim — don't remove from DOM so layout stays stable
      }, FADE_DELAY_MS);
    }
    return () => {
      if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current);
    };
  }, [orbState, text]);

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

  const opacity = visible ? (isActive ? 1 : 0.45) : 0;

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
          <span className="block text-[10px] font-semibold uppercase tracking-widest text-zinc-500 mb-1">
            {role === "user" ? "Ty" : "Asystent"}
          </span>
          <span>{displayed || emptyLabel}</span>
        </div>
      )}
    </div>
  );
}
