"use client";

import type { Chart } from "chart.js/auto";
import { useCallback, useEffect, useRef, useState } from "react";

import { useTranslation } from "@/lib/i18n";

import type { TokenSample } from "@/components/cockpit/token-types";

type ChartModule = Pick<typeof import("chart.js/auto"), "default">;

const loadChartModule = () => import("chart.js/auto");

type TokenChartProps = Readonly<{
  history: TokenSample[];
  height?: number;
  loadChart?: () => Promise<ChartModule>;
}>;

export function TokenChart({ history, height = 220, loadChart = loadChartModule }: TokenChartProps) {
  const t = useTranslation();
  const [failed, setFailed] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartRef = useRef<Chart | null>(null);
  const chartModuleRef = useRef<ChartModule | null>(null);

  const destroyChart = useCallback(() => {
    const chart = chartRef.current;
    chartRef.current = null;
    try {
      chart?.destroy();
    } catch (error) {
      console.warn("Token chart cleanup failed", error);
    }
  }, []);

  useEffect(() => {
    return () => {
      destroyChart();
    };
  }, [destroyChart]);

  useEffect(() => {
    if (!canvasRef.current) return;
    if (height) {
      canvasRef.current.style.height = `${height}px`;
    }
    const labels = history.map((h) => h.timestamp);
    const dataPoints = history.map((h) => h.value);

    let isMounted = true;
    const renderChart = async () => {
      if (!canvasRef.current) return;
      let chartModule = chartModuleRef.current;
      if (!chartModule) {
        chartModule = await loadChart();
        chartModuleRef.current = chartModule;
      }
      if (!isMounted) return;
      const ChartJS = chartModule.default;

      if (chartRef.current) {
        chartRef.current.data.labels = labels;
        chartRef.current.data.datasets[0].data = dataPoints;
        chartRef.current.update();
        return;
      }

      chartRef.current = new ChartJS(canvasRef.current, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Total tokens",
              data: dataPoints,
              borderColor: "#8b5cf6",
              backgroundColor: "rgba(139,92,246,0.2)",
              tension: 0.3,
              fill: true,
            },
          ],
        },
        options: {
          responsive: true,
          plugins: {
            legend: {
              labels: {
                color: "#e5e7eb",
              },
            },
          },
          scales: {
            x: {
              ticks: { color: "#94a3b8", maxTicksLimit: 5 },
              grid: { color: "rgba(148,163,184,0.2)" },
            },
            y: {
              ticks: { color: "#94a3b8" },
              grid: { color: "rgba(148,163,184,0.2)" },
            },
          },
        },
      });
    };

    void renderChart().catch((error: unknown) => {
      if (!isMounted) return;
      console.warn("Token chart rendering failed", error);
      destroyChart();
      setFailed(true);
    });

    return () => {
      isMounted = false;
    };
  }, [history, height, loadChart, destroyChart]);

  if (failed) {
    return (
      <div className="overflow-auto text-xs text-theme-muted" style={{ height }}>
        <ul aria-label={t("cockpit.metrics.tokens.history")}>
          {history.map((sample, index) => (
            <li key={`${sample.timestamp}-${index}`}>{sample.timestamp}: {sample.value}</li>
          ))}
        </ul>
      </div>
    );
  }

  return <canvas ref={canvasRef} className="w-full" style={{ height }} />;
}
