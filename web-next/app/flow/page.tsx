"use client";

import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";
import { fetchHistoryDetail, useHistory, useTasks } from "@/hooks/use-api";
import { useEffect, useRef, useState } from "react";

export default function FlowInspectorPage() {
  const { data: history } = useHistory(50);
  const { data: tasks } = useTasks();
  const [diagram, setDiagram] = useState<string>("graph TD\nA[Brak danych]");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [steps, setSteps] = useState<HistoryStep[]>([]);
  const [steps, setSteps] = useState<HistoryStep[]>([]);
  const svgRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let isMounted = true;
    (async () => {
      const mermaid = (await import("mermaid")).default;
      mermaid.initialize({
        startOnLoad: false,
        theme: "dark",
        securityLevel: "loose",
      });
      const renderSvg = async () => {
        try {
          const { svg } = await mermaid.render("flow-chart", diagram);
          if (svgRef.current && isMounted) {
            svgRef.current.innerHTML = svg;
          }
        } catch (err) {
          console.error("Mermaid render error:", err);
        }
      };
      await renderSvg();
    })();
    return () => {
      isMounted = false;
    };
  }, [diagram]);

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-2xl border border-[--color-border] bg-[--color-panel]/70 p-6 shadow-xl shadow-black/40">
        <p className="text-sm text-[--color-muted]">Flow Inspector</p>
        <h1 className="mt-2 text-3xl font-semibold">Graf wykonania zadań</h1>
        <p className="mt-2 text-sm text-[--color-muted]">
          Wizualizacja kroków z RequestTracer i timeline kroków planu. Docelowo
          dane z /api/v1/history/requests i mermaid/markdown w trybie client.
        </p>
        <div className="mt-4 flex gap-2">
          <Badge tone="neutral">/history/requests</Badge>
          <Badge tone="neutral">/tasks</Badge>
          <Badge tone="warning">mermaid (client)</Badge>
        </div>
      </div>

      <Panel
        title="Lista requestów"
        description="Źródło: /api/v1/history/requests?limit=50"
      >
        <div className="grid gap-3 sm:grid-cols-2">
          {(history || []).length === 0 && (
            <div className="rounded-xl border border-[--color-border] bg-white/5 p-4 text-sm text-[--color-muted]">
              Brak historii. Uruchom zadanie, aby zobaczyć timeline.
            </div>
          )}
          {(history || []).map((req) => (
            <button
              key={req.request_id}
              className="rounded-xl border border-[--color-border] bg-white/5 p-4 text-left hover:bg-white/10"
              onClick={() =>
                loadHistoryDetail(req.request_id, setDiagram, setSelectedId, setSteps)
              }
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold">#{req.request_id}</p>
                  <p className="text-xs text-[--color-muted]">{req.prompt}</p>
                </div>
                <Badge tone={statusTone(req.status)}>{req.status}</Badge>
              </div>
              {req.duration_seconds !== undefined && req.duration_seconds !== null && (
                <p className="mt-2 text-xs text-[--color-muted]">
                  Czas: {req.duration_seconds.toFixed(1)}s
                </p>
              )}
            </button>
          ))}
        </div>
      </Panel>

      <Panel
        title="Timeline wykonania"
        description="Docelowo mermaid + listowane kroki z RequestTracer."
      >
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-xl border border-[--color-border] bg-white/5 p-4 text-sm text-[--color-muted] md:col-span-2">
            <div className="min-h-[300px]" ref={svgRef} />
          </div>
          <div className="rounded-xl border border-[--color-border] bg-white/5 p-4 text-sm text-[--color-muted]">
            <p className="text-xs uppercase tracking-wide text-[--color-muted]">
              Bieżące zadania: {(tasks || []).length}
            </p>
            {selectedId ? (
              <div className="mt-2 space-y-2">
                <p className="text-xs">Wybrany request: {selectedId}</p>
                <ul className="space-y-1 text-xs">
                  {steps.length === 0 && (
                    <li className="text-[--color-muted]">Brak kroków.</li>
                  )}
                  {steps.map((step, idx) => (
                    <li
                      key={idx}
                      className="rounded border border-[--color-border] bg-white/5 px-2 py-1"
                    >
                      <span className="font-semibold text-white">
                        {step.component || "step"}
                      </span>
                      : {step.action || ""}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="mt-2 text-xs">Wybierz request z listy.</p>
            )}
          </div>
        </div>
      </Panel>
    </div>
  );
}

function statusTone(status: string | undefined) {
  if (!status) return "neutral" as const;
  if (status === "COMPLETED") return "success" as const;
  if (status === "PROCESSING") return "warning" as const;
  if (status === "FAILED") return "danger" as const;
  return "neutral" as const;
}

type HistoryStep = {
  component?: string;
  action?: string;
};

async function loadHistoryDetail(
  requestId: string,
  setDiagram: (d: string) => void,
  setSelected: (id: string) => void,
  setSteps: (s: HistoryStep[]) => void,
) {
  const detail = (await fetchHistoryDetail(requestId)) as { steps?: HistoryStep[] };
  const steps = detail.steps || [];
  const diagram = buildMermaid(steps);
  setDiagram(diagram);
  setSelected(requestId);
  setSteps(steps);
}

function buildMermaid(steps: HistoryStep[]) {
  if (!steps.length) {
    return "graph TD\nA[Brak kroków]";
  }
  const lines = ["graph TD"];
  steps.forEach((step, idx) => {
    const nodeId = `S${idx}`;
    const label = `${step.component || "step"}: ${step.action || ""}`
      .replace(/"/g, "'")
      .slice(0, 40);
    lines.push(`${nodeId}["${label}"]`);
    if (idx > 0) {
      lines.push(`S${idx - 1} --> ${nodeId}`);
    }
  });
  return lines.join("\n");
}
