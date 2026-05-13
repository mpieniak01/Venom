"use client";

import { RefObject, useEffect, useRef, useState } from "react";

type OrbFrequencyRingProps = Readonly<{
  analyserRef: RefObject<AnalyserNode | null>;
  active: boolean;
  color: string;
  size: number;
}>;

export function OrbFrequencyRing({ analyserRef, active, color, size }: OrbFrequencyRingProps) {
  const bufferRef = useRef<Uint8Array | null>(null);
  const [pathData, setPathData] = useState("");

  useEffect(() => {
    if (!active) return;

    const N = 24;
    const cx = size / 2;
    const cy = size / 2;
    const baseR = size * 0.415;
    const maxDisp = size * 0.095;
    const SAMPLE_MS = 80;

    const draw = () => {
      const analyser = analyserRef.current;

      if (!analyser) {
        return;
      }

      const binCount = analyser.frequencyBinCount;
      if (!bufferRef.current || bufferRef.current.length !== binCount) {
        bufferRef.current = new Uint8Array(binCount);
      }
      analyser.getByteFrequencyData(bufferRef.current);
      const data = bufferRef.current;
      const step = Math.max(1, Math.floor(binCount / N));

      let d = "";
      for (let i = 0; i < N; i++) {
        const angle = (2 * Math.PI * i) / N - Math.PI / 2;
        const val = data[Math.min(i * step, binCount - 1)] / 255;
        const r = baseR + val * maxDisp;
        const x = (cx + r * Math.cos(angle)).toFixed(2);
        const y = (cy + r * Math.sin(angle)).toFixed(2);
        d += i === 0 ? `M ${x} ${y}` : ` L ${x} ${y}`;
      }
      d += " Z";

      setPathData(d);
    };

    draw();
    const intervalId = globalThis.setInterval(draw, SAMPLE_MS);
    return () => {
      globalThis.clearInterval(intervalId);
    };
  }, [active, analyserRef, size]);

  if (!active) return null;

  return (
    <svg
      width={size}
      height={size}
      className="pointer-events-none absolute inset-0"
      aria-hidden="true"
    >
      <path
        d={pathData}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        opacity="0.75"
      />
    </svg>
  );
}
