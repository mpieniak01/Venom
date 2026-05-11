"use client";

import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";

const computeRms = (
  analyser: AnalyserNode,
  bufferRef: RefObject<Float32Array | null>,
): number => {
  if (bufferRef.current?.length !== analyser.fftSize) {
    bufferRef.current = new Float32Array(analyser.fftSize);
  }

  const buffer = bufferRef.current;
  if (!buffer) {
    return 0;
  }

  analyser.getFloatTimeDomainData(buffer);
  let sum = 0;
  for (const sample of buffer) {
    sum += sample ** 2;
  }
  return Math.sqrt(sum / buffer.length);
};

export const useAudioLevel = (
  analyserRef: RefObject<AnalyserNode | null>,
  active: boolean,
): number => {
  const [level, setLevel] = useState(0);
  const decayRef = useRef(0);
  const bufferRef = useRef<Float32Array | null>(null);

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
        const rms = computeRms(analyser, bufferRef);
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
