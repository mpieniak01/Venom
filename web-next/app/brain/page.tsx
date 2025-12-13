"use client";

import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";
import { useGraphSummary, useKnowledgeGraph } from "@/hooks/use-api";
import type cytoscapeType from "cytoscape";
import { useEffect, useRef } from "react";

export default function BrainPage() {
  const { data: summary } = useGraphSummary();
  const { data: graph } = useKnowledgeGraph();
  const cyRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cyInstance: cytoscapeType.Core | null = null;
    const mount = async () => {
      if (!cyRef.current || !graph?.elements) return;
      const cytoscape = (await import("cytoscape")).default as typeof cytoscapeType;
      cyInstance = cytoscape({
        container: cyRef.current,
        elements: graph.elements,
        layout: { name: "cose", padding: 30, animate: false },
        style: [
          {
            selector: "node",
            style: {
              "background-color": (ele: cytoscapeType.NodeSingular) =>
                ele.data("type") === "agent"
                  ? "#22c55e"
                  : ele.data("type") === "memory"
                    ? "#f59e0b"
                    : "#6366f1",
              label: "data(label)",
              color: "#e5e7eb",
              "font-size": 11,
              "text-wrap": "wrap",
              "text-max-width": 120,
              "border-width": 1,
              "border-color": "#1f2937",
            },
          },
          {
            selector: "edge",
            style: {
              width: 1.5,
              "line-color": "#475569",
              "target-arrow-color": "#475569",
              "target-arrow-shape": "triangle",
              "curve-style": "bezier",
              label: "data(label)",
              "font-size": 9,
              color: "#94a3b8",
              "text-background-opacity": 0.4,
              "text-background-color": "#0f172a",
              "text-background-padding": 2,
            },
          },
        ],
      });
    };
    mount();
    return () => {
      if (cyInstance) {
        cyInstance.destroy();
      }
    };
  }, [graph]);

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-2xl border border-[--color-border] bg-[--color-panel]/70 p-6 shadow-xl shadow-black/40">
        <p className="text-sm text-[--color-muted]">Brain / Knowledge Graph</p>
        <h1 className="mt-2 text-3xl font-semibold">Wizualizacja pamięci</h1>
        <p className="mt-2 text-sm text-[--color-muted]">
          Widok grafu zasila /api/v1/graph/summary i /api/v1/graph/scan. Rendering
          planowany z użyciem Cytoscape (dynamic import).
        </p>
        <div className="mt-4 flex gap-2">
          <Badge tone="neutral">/graph/summary</Badge>
          <Badge tone="neutral">
            węzły: {summary?.nodes ?? "—"} / krawędzie: {summary?.edges ?? "—"}
          </Badge>
          <Badge tone="warning">Cytoscape (client)</Badge>
        </div>
      </div>

      <Panel title="Statystyki grafu" description="Stub danych do zastąpienia API.">
        <div className="grid gap-3 sm:grid-cols-3">
          <StatRow label="Węzły" value={summary?.nodes ?? "—"} />
          <StatRow label="Krawędzie" value={summary?.edges ?? "—"} />
          <StatRow
            label="Ostatnia aktualizacja"
            value={summary?.lastUpdated ?? "—"}
          />
        </div>
      </Panel>

      <Panel
        title="Obszary filtrów"
        description="Tagi, typy węzłów, ostatnie aktualizacje — do wpięcia w API grafu."
      >
        <div className="flex flex-wrap gap-2 text-sm text-[--color-muted]">
          <Badge tone="neutral">kod</Badge>
          <Badge tone="neutral">workflow</Badge>
          <Badge tone="neutral">dokumentacja</Badge>
          <Badge tone="neutral">lekcje</Badge>
        </div>
      </Panel>

      <Panel
        title="Widok grafu"
        description="Miejsce na komponent grafu (Cytoscape) + szczegóły węzła."
      >
        <div className="grid gap-4 md:grid-cols-3">
          <div className="md:col-span-2 rounded-xl border border-[--color-border] bg-white/5 p-2 text-sm text-[--color-muted]">
            <div ref={cyRef} className="h-[480px] w-full rounded-lg bg-[#0b1220]" />
          </div>
          <div className="rounded-xl border border-[--color-border] bg-white/5 p-6">
            <h4 className="text-sm font-semibold text-white">Szczegóły węzła</h4>
            <p className="mt-2 text-sm text-[--color-muted]">
              Tu pojawi się panel szczegółów (tagi, relacje, ostatnie akcji agentów).
            </p>
          </div>
        </div>
      </Panel>
    </div>
  );
}

type StatRowProps = {
  label: string;
  value: string | number;
};

function StatRow({ label, value }: StatRowProps) {
  return (
    <div className="rounded-xl border border-[--color-border] bg-white/5 p-4">
      <p className="text-xs uppercase tracking-wide text-[--color-muted]">
        {label}
      </p>
      <p className="mt-2 text-xl font-semibold">{value}</p>
    </div>
  );
}
