import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";

const sampleRequests = [
  { id: "a1b2", prompt: "Zbuduj plan migracji Next", status: "COMPLETED" },
  { id: "c3d4", prompt: "Scan repo i sync git", status: "PROCESSING" },
  { id: "e5f6", prompt: "Utwórz roadmapę Strategy", status: "PENDING" },
];

export default function FlowInspectorPage() {
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
        action={<Badge tone="neutral">stub</Badge>}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          {sampleRequests.map((req) => (
            <div
              key={req.id}
              className="rounded-xl border border-[--color-border] bg-white/5 p-4"
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold">#{req.id}</p>
                  <p className="text-xs text-[--color-muted]">{req.prompt}</p>
                </div>
                <Badge
                  tone={
                    req.status === "COMPLETED"
                      ? "success"
                      : req.status === "PROCESSING"
                        ? "warning"
                        : "neutral"
                  }
                >
                  {req.status}
                </Badge>
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel
        title="Timeline wykonania"
        description="Docelowo mermaid + listowane kroki z RequestTracer."
      >
        <div className="rounded-xl border border-dashed border-[--color-border] bg-white/5 p-6 text-sm text-[--color-muted]">
          Diagram mermaid zostanie wstrzyknięty po stronie klienta (dynamic import).
        </div>
      </Panel>
    </div>
  );
}
