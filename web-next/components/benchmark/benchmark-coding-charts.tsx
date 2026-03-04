"use client";

import { useEffect, useMemo, useRef } from "react";
import type { MutableRefObject, ReactNode } from "react";
import type { CodingJob } from "@/lib/types";
import { useTranslation } from "@/lib/i18n";

// ─── Pure data adapters (exported for tests) ─────────────────────────────────

export interface ModelPassRate {
  model: string;
  passRate: number;
  total: number;
  passed: number;
}

export interface ModelTiming {
  model: string;
  warmupSeconds: number;
  codingSeconds: number;
  requestSeconds: number;
}

type ChartInstance = import("chart.js").Chart;
type BarChartConfig = import("chart.js").ChartConfiguration<"bar">;

async function renderBarChart(
  canvas: HTMLCanvasElement,
  chartRef: MutableRefObject<ChartInstance | null>,
  config: BarChartConfig,
  isActive: () => boolean,
): Promise<void> {
  const { Chart } = await import("chart.js/auto");
  if (!isActive()) return;
  if (!chartRef.current) {
    chartRef.current = new Chart(canvas, config);
    return;
  }
  chartRef.current.data = config.data;
  chartRef.current.options = config.options ?? {};
  chartRef.current.update("none");
}

function destroyChart(chartRef: MutableRefObject<ChartInstance | null>) {
  chartRef.current?.destroy();
  chartRef.current = null;
}

/** Compute pass-rate per model from a flat list of jobs. */
export function computePassRates(jobs: ReadonlyArray<CodingJob>): ModelPassRate[] {
  const acc: Record<string, { total: number; passed: number }> = {};
  for (const job of jobs) {
    if (!acc[job.model]) acc[job.model] = { total: 0, passed: 0 };
    acc[job.model].total += 1;
    if (job.passed === true) acc[job.model].passed += 1;
  }
  return Object.entries(acc).map(([model, { total, passed }]) => ({
    model,
    total,
    passed,
    passRate: total > 0 ? (passed / total) * 100 : 0,
  }));
}

/** Compute average timing per model from a flat list of jobs. */
export function computeTimings(jobs: ReadonlyArray<CodingJob>): ModelTiming[] {
  const acc: Record<
    string,
    { warmup: number[]; coding: number[]; request: number[] }
  > = {};
  for (const job of jobs) {
    if (!acc[job.model]) acc[job.model] = { warmup: [], coding: [], request: [] };
    if (job.warmup_seconds != null) acc[job.model].warmup.push(job.warmup_seconds);
    if (job.coding_seconds != null) acc[job.model].coding.push(job.coding_seconds);
    if (job.request_wall_seconds != null)
      acc[job.model].request.push(job.request_wall_seconds);
  }
  const avg = (arr: number[]) =>
    arr.length > 0 ? arr.reduce((s, v) => s + v, 0) / arr.length : 0;
  return Object.entries(acc).map(([model, { warmup, coding, request }]) => ({
    model,
    warmupSeconds: avg(warmup),
    codingSeconds: avg(coding),
    requestSeconds: avg(request),
  }));
}

// ─── Chart components ─────────────────────────────────────────────────────────

interface BenchmarkCodingChartsProps {
  readonly jobs: ReadonlyArray<CodingJob>;
}

export function BenchmarkCodingCharts({ jobs }: BenchmarkCodingChartsProps) {
  const t = useTranslation();

  const passRates = useMemo(() => computePassRates(jobs), [jobs]);
  const timings = useMemo(() => computeTimings(jobs), [jobs]);
  const timingLabels = useMemo(
    () => ({
      warmup: t("benchmark.coding.charts.warmup"),
      coding: t("benchmark.coding.charts.coding"),
      request: t("benchmark.coding.charts.request"),
    }),
    [t],
  );

  if (jobs.length === 0) {
    return (
      <p className="text-sm text-[color:var(--ui-muted)] py-4 text-center">
        {t("benchmark.coding.charts.noData")}
      </p>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <PassRateChart passRates={passRates} title={t("benchmark.coding.charts.passRate")} />
      <TimingChart
        timings={timings}
        title={t("benchmark.coding.charts.timing")}
        labels={timingLabels}
      />
    </div>
  );
}

// ─── Pass Rate Bar Chart ───────────────────────────────────────────────────────

interface PassRateChartProps {
  readonly passRates: ModelPassRate[];
  readonly title: string;
}

function PassRateChart({ passRates, title }: PassRateChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<ChartInstance | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let active = true;

    const config: BarChartConfig = {
      type: "bar",
      data: {
        labels: passRates.map((r) => r.model),
        datasets: [
          {
            label: title,
            data: passRates.map((r) => Math.round(r.passRate * 10) / 10),
            backgroundColor: passRates.map((r) =>
              r.passRate >= 80 ? "rgba(52, 211, 153, 0.7)" : "rgba(251, 191, 36, 0.7)",
            ),
            borderColor: passRates.map((r) =>
              r.passRate >= 80 ? "rgb(52, 211, 153)" : "rgb(251, 191, 36)",
            ),
            borderWidth: 1,
            borderRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: {
            min: 0,
            max: 100,
            ticks: { color: "#9ca3af", callback: (v) => `${v}%` },
            grid: { color: "rgba(255,255,255,0.05)" },
          },
          x: { ticks: { color: "#9ca3af" }, grid: { display: false } },
        },
      },
    };

    void renderBarChart(canvas, chartRef, config, () => active);

    return () => {
      active = false;
      destroyChart(chartRef);
    };
  }, [passRates, title]);

  return (
    <ChartPanel title={title}>
      <canvas ref={canvasRef} />
    </ChartPanel>
  );
}

// ─── Timing Stacked Bar Chart ─────────────────────────────────────────────────

interface TimingChartProps {
  readonly timings: ModelTiming[];
  readonly title: string;
  readonly labels: { warmup: string; coding: string; request: string };
}

function TimingChart({ timings, title, labels }: TimingChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<ChartInstance | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let active = true;

    const config: BarChartConfig = {
      type: "bar",
      data: {
        labels: timings.map((t) => t.model),
        datasets: [
          {
            label: labels.warmup,
            data: timings.map((t) => Math.round(t.warmupSeconds * 10) / 10),
            backgroundColor: "rgba(139, 92, 246, 0.7)",
            borderColor: "rgb(139, 92, 246)",
            borderWidth: 1,
            borderRadius: 2,
          },
          {
            label: labels.coding,
            data: timings.map((t) => Math.round(t.codingSeconds * 10) / 10),
            backgroundColor: "rgba(52, 211, 153, 0.7)",
            borderColor: "rgb(52, 211, 153)",
            borderWidth: 1,
          },
          {
            label: labels.request,
            data: timings.map((t) => Math.round(t.requestSeconds * 10) / 10),
            backgroundColor: "rgba(251, 191, 36, 0.7)",
            borderColor: "rgb(251, 191, 36)",
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: "#9ca3af", boxWidth: 10 } } },
        scales: {
          y: {
            stacked: true,
            ticks: { color: "#9ca3af", callback: (v) => `${v}s` },
            grid: { color: "rgba(255,255,255,0.05)" },
          },
          x: {
            stacked: true,
            ticks: { color: "#9ca3af" },
            grid: { display: false },
          },
        },
      },
    };

    void renderBarChart(canvas, chartRef, config, () => active);

    return () => {
      active = false;
      destroyChart(chartRef);
    };
  }, [timings, title, labels.warmup, labels.coding, labels.request]);

  return (
    <ChartPanel title={title}>
      <canvas ref={canvasRef} />
    </ChartPanel>
  );
}

function ChartPanel({
  title,
  children,
}: Readonly<{ title: string; children: ReactNode }>) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-[color:var(--text-secondary)] uppercase tracking-wider">
        {title}
      </p>
      <div className="relative h-[292px] rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] p-3">
        {children}
      </div>
    </div>
  );
}
