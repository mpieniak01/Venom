"use client";

import type { Chart } from "chart.js/auto";
import { useEffect, useRef } from "react";

import type { TokenSample } from "@/components/cockpit/token-types";

type TokenChartProps = Readonly<{
  history: TokenSample[];
  height?: number;
}>;

export function TokenChart({ history, height = 220 }: TokenChartProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartRef = useRef<Chart | null>(null);
  const chartModuleRef = useRef<typeof import("chart.js/auto") | null>(null);

  useEffect(() => {
    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, []);

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
        chartModule = await import("chart.js/auto");
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

    renderChart();

    return () => {
      isMounted = false;
    };
  }, [history, height]);

  return <canvas ref={canvasRef} className="w-full" style={{ height }} />;
}
