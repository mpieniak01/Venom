"use client";

import { RefObject, useEffect, useRef } from "react";

type OrbFrequencyRingProps = Readonly<{
  analyserRef: RefObject<AnalyserNode | null>;
  active: boolean;
  color: string;
  size: number;
}>;

export function OrbFrequencyRing({ analyserRef, active, color, size }: OrbFrequencyRingProps) {
  const pathRef = useRef<SVGPathElement | null>(null);
  const rafRef = useRef<number | null>(null);
  const bufferRef = useRef<Uint8Array | null>(null);

  useEffect(() => {
    if (!active) {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      if (pathRef.current) pathRef.current.setAttribute("d", "");
      return;
    }

    const N = 48;
    const cx = size / 2;
    const cy = size / 2;
    const baseR = size * 0.415;
    const maxDisp = size * 0.095;

    const draw = () => {
      const analyser = analyserRef.current;

      if (!analyser) {
        rafRef.current = requestAnimationFrame(draw);
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

      if (pathRef.current) pathRef.current.setAttribute("d", d);
      rafRef.current = requestAnimationFrame(draw);
    };

    rafRef.current = requestAnimationFrame(draw);
    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
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
        ref={pathRef}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        opacity="0.75"
      />
    </svg>
  );
}
