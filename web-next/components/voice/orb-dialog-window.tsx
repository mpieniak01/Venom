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
      setDisplayed(text);
      return;
    }

    let i = prevTextRef.current === text ? text.length : 0;
    prevTextRef.current = text;
    setDisplayed(text.slice(0, i));

    const id = setInterval(() => {
      i += 1;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) clearInterval(id);
    }, TYPEWRITER_INTERVAL_MS);

    return () => clearInterval(id);
  }, [text, role, reducedMotion]);

  // For user bubble just show full text immediately
  useEffect(() => {
    if (role !== "user") return;
    prevTextRef.current = text;
    setDisplayed(text);
  }, [text, role]);

  // Visibility + enter animation on text change
  useEffect(() => {
    if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current);

    if (text) {
      setVisible(true);
      if (!reducedMotion) {
        setEntering(true);
        const id = setTimeout(() => setEntering(false), 240);
        return () => clearTimeout(id);
      }
    } else {
      setVisible(false);
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
    role === "user"
      ? "border-white/10 bg-white/[0.05] text-zinc-200 self-end text-right"
      : "border-white/10 bg-white/[0.04] text-zinc-100 self-start text-left",
    isEmpty ? "border-transparent bg-transparent" : "",
    isActive ? "border-white/15" : "",
    entering && !reducedMotion
      ? role === "user"
        ? "animate-orb-dialog-in-top"
        : "animate-orb-dialog-in-bottom"
      : "",
  ]
    .filter(Boolean)
    .join(" ");

  const opacity = !visible ? 0 : isActive ? 1 : 0.45;

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
