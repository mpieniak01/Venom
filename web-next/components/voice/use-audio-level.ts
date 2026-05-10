"use client";

import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";

const computeRms = (analyser: AnalyserNode): number => {
  const buffer = new Float32Array(analyser.fftSize);
  analyser.getFloatTimeDomainData(buffer);
  let sum = 0;
  for (let i = 0; i < buffer.length; i++) {
    sum += (buffer[i] ?? 0) ** 2;
  }
  return Math.sqrt(sum / buffer.length);
};

export const useAudioLevel = (
  analyserRef: RefObject<AnalyserNode | null>,
  active: boolean,
): number => {
  const [level, setLevel] = useState(0);
  const decayRef = useRef(0);

  useEffect(() => {
    if (!active) {
      decayRef.current = 0;
      setLevel(0);
      return;
    }

    let frameId: number | null = null;

    const tick = () => {
      const analyser = analyserRef.current;
      if (analyser) {
        const rms = computeRms(analyser);
        decayRef.current = Math.max(rms, decayRef.current * 0.85);
      } else {
        decayRef.current *= 0.85;
      }
      setLevel(Math.min(1, decayRef.current * 4));
      frameId = requestAnimationFrame(tick);
    };

    frameId = requestAnimationFrame(tick);
    return () => {
      if (frameId !== null) cancelAnimationFrame(frameId);
    };
    // analyserRef is a stable RefObject — intentionally excluded from deps
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  return level;
};
