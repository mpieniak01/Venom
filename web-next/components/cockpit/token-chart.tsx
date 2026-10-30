"use client";

import type { Chart } from "chart.js";
import { useCallback, useEffect, useRef, useState } from "react";

import { useTranslation } from "@/lib/i18n";

import type { TokenSample } from "@/components/cockpit/token-types";

type ChartModule = Pick<typeof import("./token-line-chart"), "default">;

const loadChartModule = () => import("./token-line-chart");

type TokenChartProps = Readonly<{
  history: TokenSample[];
  height?: number;
  loadChart?: () => Promise<ChartModule>;
}>;

export function TokenChart({ history, height = 220, loadChart = loadChartModule }: TokenChartProps) {
  const t = useTranslation();
  const [failed, setFailed] = useState(false);
  const [visible, setVisible] = useState(() => typeof IntersectionObserver === "undefined");
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartRef = useRef<Chart | null>(null);
  const chartModuleRef = useRef<ChartModule | null>(null);
  const chartLoadRef = useRef<Promise<ChartModule> | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      setVisible(true);
      observer.disconnect();
    });
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

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
    if (!canvasRef.current || !visible || (history.length === 0 && !chartRef.current)) return;
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
        chartLoadRef.current ??= loadChart();
        chartModule = await chartLoadRef.current;
        chartModuleRef.current = chartModule;
      }
      if (!isMounted) return;
      const ChartJS = chartModule.default;

      if (chartRef.current) {
        chartRef.current.data.labels = labels;
        chartRef.current.data.datasets[0].data = dataPoints;
        chartRef.current.data.datasets[0].label = t("cockpit.metrics.tokens.title");
        chartRef.current.update();
        return;
      }

      chartRef.current = new ChartJS(canvasRef.current, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: t("cockpit.metrics.tokens.title"),
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
  }, [history, height, loadChart, destroyChart, visible, t]);

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
