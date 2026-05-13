"use client";

import { useEffect, useRef, useState } from "react";
import type { VoiceOrbState } from "@/components/voice/voice-orb";
import { isActiveVoiceOrbState } from "@/components/voice/orb-visibility";

const DEFAULT_COOLDOWN_MS = 4500;

export function useOrbActivityWindow(
  state: VoiceOrbState,
  enabled: boolean,
  cooldownMs = DEFAULT_COOLDOWN_MS,
): boolean {
  const [activeWindow, setActiveWindow] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }

    const schedule = (nextValue: boolean, delayMs: number) => {
      timeoutRef.current = setTimeout(() => {
        setActiveWindow(nextValue);
        timeoutRef.current = null;
      }, delayMs);
    };

    if (!enabled) {
      if (activeWindow) schedule(false, 0);
      return () => {
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
      };
    }

    if (isActiveVoiceOrbState(state)) {
      if (!activeWindow) schedule(true, 0);
      return () => {
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
      };
    }

    if (activeWindow) {
      schedule(false, Math.max(500, cooldownMs));
    }

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [activeWindow, cooldownMs, enabled, state]);

  return enabled && activeWindow;
}
