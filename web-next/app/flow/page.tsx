import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";
import { useHistory, useTasks } from "@/hooks/use-api";

export default function FlowInspectorPage() {
  const { data: history } = useHistory(50);
  const { data: tasks } = useTasks();

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
            <div
              key={req.request_id}
              className="rounded-xl border border-[--color-border] bg-white/5 p-4"
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
          Bieżące zadania: {(tasks || []).length}
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
