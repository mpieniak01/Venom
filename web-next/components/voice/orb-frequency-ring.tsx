"use client";

import { RefObject, useEffect, useRef } from "react";

type OrbPoint = Readonly<{ x: number; y: number }>;

function buildSmoothClosedPath(points: readonly OrbPoint[]): string {
  if (points.length === 0) return "";
  if (points.length === 1) {
    const point = points[0];
    if (!point) return "";
    return `M ${point.x.toFixed(2)} ${point.y.toFixed(2)} Z`;
  }

  const commands = [`M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`];
  for (let i = 0; i < points.length; i++) {
    const p0 = points[(i - 1 + points.length) % points.length];
    const p1 = points[i];
    const p2 = points[(i + 1) % points.length];
    const p3 = points[(i + 2) % points.length];
    if (!p0 || !p1 || !p2 || !p3) continue;
    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;
    commands.push(
      `C ${cp1x.toFixed(2)} ${cp1y.toFixed(2)} ${cp2x.toFixed(2)} ${cp2y.toFixed(2)} ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`,
    );
  }
  commands.push("Z");
  return commands.join(" ");
}

type OrbFrequencyRingProps = Readonly<{
  analyserRef: RefObject<AnalyserNode | null>;
  active: boolean;
  color: string;
  size: number;
}>;

export function OrbFrequencyRing({ analyserRef, active, color, size }: OrbFrequencyRingProps) {
  const bufferRef = useRef<Uint8Array | null>(null);
  const currentRadiiRef = useRef<number[]>([]);
  const targetRadiiRef = useRef<number[]>([]);
  const lastSampleRef = useRef(0);
  const lastFrameRef = useRef(0);
  const pathRef = useRef<SVGPathElement | null>(null);

  useEffect(() => {
    if (!active) return;

    const N = 40;
    const cx = size / 2;
    const cy = size / 2;
    const baseR = size * 0.41;
    const safeMaxR = size * 0.46;
    const maxDisp = Math.min(size * 0.085, safeMaxR - baseR);
    const SAMPLE_MS = 44;

    currentRadiiRef.current = Array.from({ length: N }, () => baseR);
    targetRadiiRef.current = Array.from({ length: N }, () => baseR);
    lastSampleRef.current = 0;
    lastFrameRef.current = 0;

    const draw = (now: number) => {
      const analyser = analyserRef.current;
      const shouldSample = now - lastSampleRef.current >= SAMPLE_MS || lastSampleRef.current === 0;

      if (analyser && shouldSample) {
        lastSampleRef.current = now;
        const binCount = analyser.frequencyBinCount;
        if (!bufferRef.current || bufferRef.current.length !== binCount) {
          bufferRef.current = new Uint8Array(binCount);
        }
        analyser.getByteFrequencyData(
          bufferRef.current as unknown as Uint8Array<ArrayBuffer>,
        );
        const data = bufferRef.current;
        const step = Math.max(1, Math.floor(binCount / N));

        targetRadiiRef.current = targetRadiiRef.current.map((radius, index) => {
          const raw = data[Math.min(index * step, binCount - 1)] / 255;
          const val = Math.pow(raw, 0.72);
          const target = Math.min(safeMaxR, baseR + val * maxDisp);
          return target > radius ? radius + (target - radius) * 0.55 : radius * 0.88;
        });
      } else if (!analyser) {
        targetRadiiRef.current = targetRadiiRef.current.map((radius) => Math.max(baseR, Math.min(safeMaxR, radius * 0.86)));
      }

      const frameDelta = lastFrameRef.current === 0 ? 16 : Math.max(8, now - lastFrameRef.current);
      lastFrameRef.current = now;
      const smoothing = Math.min(0.45, frameDelta / 1000 * 14);

      const points: OrbPoint[] = currentRadiiRef.current.map((currentRadius, index) => {
        const targetRadius = targetRadiiRef.current[index] ?? baseR;
        const nextRadius = currentRadius + (targetRadius - currentRadius) * smoothing;
        currentRadiiRef.current[index] = Math.min(safeMaxR, Math.max(baseR, nextRadius));
        const angle = (2 * Math.PI * index) / N - Math.PI / 2;
        return {
          x: cx + currentRadiiRef.current[index] * Math.cos(angle),
          y: cy + currentRadiiRef.current[index] * Math.sin(angle),
        };
      });

      const d = buildSmoothClosedPath(points);
      const pathEl = pathRef.current;
      if (pathEl && pathEl.getAttribute("d") !== d) {
        pathEl.setAttribute("d", d);
      }
    };

    const frame = (now: number) => {
      draw(now);
      rafId = requestAnimationFrame(frame);
    };

    let rafId = requestAnimationFrame(frame);
    return () => {
      globalThis.cancelAnimationFrame(rafId);
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
        d=""
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity="0.86"
      />
    </svg>
  );
}
