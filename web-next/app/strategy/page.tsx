"use client";

import { Badge } from "@/components/ui/badge";
import { Panel, StatCard } from "@/components/ui/panel";
import { MarkdownPreview } from "@/components/ui/markdown";
import {
  createRoadmap,
  requestRoadmapStatus,
  startCampaign,
  useRoadmap,
} from "@/hooks/use-api";
import { useState } from "react";

export default function StrategyPage() {
  const { data: roadmap, refresh: refreshRoadmap } = useRoadmap();
  const [visionInput, setVisionInput] = useState("");
  const [showVisionForm, setShowVisionForm] = useState(false);
  const [statusReport, setStatusReport] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);

  const kpis = roadmap?.kpis;
  const kpiCards = [
    {
      label: "Postęp ogólny",
      value: kpis?.completion_rate
        ? `${kpis.completion_rate.toFixed(1)}%`
        : "0%",
      hint: "wg ukończonych milestones",
    },
    {
      label: "Milestones",
      value: `${kpis?.milestones_completed ?? 0} / ${kpis?.milestones_total ?? 0}`,
      hint: "complete / total",
      accent: "blue" as const,
    },
    {
      label: "Tasks",
      value: `${kpis?.tasks_completed ?? 0} / ${kpis?.tasks_total ?? 0}`,
      hint: "complete / total",
      accent: "green" as const,
    },
  ];

  const handleCreateRoadmap = async () => {
    if (!visionInput.trim()) {
      setActionMessage("Podaj opis wizji.");
      return;
    }
    setCreating(true);
    setActionMessage(null);
    try {
      await createRoadmap(visionInput.trim());
      setActionMessage("Roadmapa utworzona.");
      setVisionInput("");
      setShowVisionForm(false);
      refreshRoadmap();
    } catch (err) {
      setActionMessage(
        err instanceof Error ? err.message : "Nie udało się utworzyć roadmapy.",
      );
    } finally {
      setCreating(false);
    }
  };

  const handleStatusReport = async () => {
    setReportLoading(true);
    setStatusReport(null);
    try {
      const res = await requestRoadmapStatus();
      setStatusReport(res.report || "Brak danych z Executive.");
    } catch (err) {
      setStatusReport(
        err instanceof Error ? err.message : "Nie udało się pobrać raportu.",
      );
    } finally {
      setReportLoading(false);
    }
  };

  const handleStartCampaign = async () => {
    setActionMessage(null);
    try {
      const res = await startCampaign();
      setActionMessage(res.message || "Kampania wystartowała (patrz logi).");
    } catch (err) {
      setActionMessage(
        err instanceof Error ? err.message : "Nie udało się uruchomić kampanii.",
      );
    }
  };

  const milestones = roadmap?.milestones || [];

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-2xl border border-[--color-border] bg-[--color-panel]/70 p-6 shadow-xl shadow-black/40">
        <p className="text-sm text-[--color-muted]">War Room</p>
        <h1 className="mt-2 text-3xl font-semibold">Strategia i roadmapa</h1>
        <p className="mt-2 text-sm text-[--color-muted]">
          Dane z `/api/roadmap` – wizja, kamienie milowe, raport statusu. Integracja ze
          Strategy Agentem i Goal Store.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Badge tone="neutral">/api/roadmap</Badge>
          <Badge tone="neutral">/api/roadmap/status</Badge>
          <Badge tone="neutral">/api/campaign/start</Badge>
        </div>
        <div className="mt-4 flex flex-wrap gap-3">
          <button
            className="rounded-lg bg-[--color-accent]/40 px-4 py-2 text-sm font-semibold text-white hover:bg-[--color-accent]/60"
            onClick={() => refreshRoadmap()}
          >
            🔄 Odśwież Roadmapę
          </button>
          <button
            className="rounded-lg border border-[--color-border] px-4 py-2 text-sm text-white hover:bg-white/10"
            onClick={() => setShowVisionForm((prev) => !prev)}
          >
            ✨ {showVisionForm ? "Ukryj" : "Zdefiniuj"} Wizję
          </button>
          <button
            className="rounded-lg border border-[--color-border] px-4 py-2 text-sm text-white hover:bg-white/10"
            onClick={handleStartCampaign}
          >
            🚀 Uruchom Kampanię
          </button>
          <button
            className="rounded-lg border border-[--color-border] px-4 py-2 text-sm text-white hover:bg-white/10"
            onClick={handleStatusReport}
            disabled={reportLoading}
          >
            📊 {reportLoading ? "Ładuję..." : "Raport Statusu"}
          </button>
        </div>
        {actionMessage && (
          <p className="mt-2 text-xs text-[--color-muted]">{actionMessage}</p>
        )}
      </div>

      {showVisionForm && (
        <Panel
          title="Nowa wizja"
          description="Utwórz roadmapę na bazie swojej wizji (/api/roadmap/create)."
        >
          <div className="space-y-3">
            <textarea
              className="min-h-[120px] w-full rounded-xl border border-[--color-border] bg-white/5 p-3 text-sm text-white outline-none focus:border-[--color-accent]"
              placeholder="Opisz wizję produktową..."
              value={visionInput}
              onChange={(e) => setVisionInput(e.target.value)}
            />
            <button
              className="rounded-lg bg-[--color-accent]/40 px-4 py-2 text-sm font-semibold text-white hover:bg-[--color-accent]/60 disabled:opacity-60"
              disabled={creating}
              onClick={handleCreateRoadmap}
            >
              {creating ? "Tworzenie..." : "Utwórz roadmapę"}
            </button>
          </div>
        </Panel>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        {kpiCards.map((kpi) => (
          <StatCard
            key={kpi.label}
            label={kpi.label}
            value={kpi.value}
            hint={kpi.hint}
            accent={kpi.accent || "purple"}
          />
        ))}
      </div>

      <Panel title="Wizja" description="Dane z goal store.">
        {roadmap?.vision ? (
          <div className="rounded-xl border border-[--color-border] bg-white/5 p-4 text-sm text-[--color-muted] space-y-3">
            <h3 className="text-lg font-semibold text-white">
              {roadmap.vision.title}
            </h3>
            <MarkdownPreview content={roadmap.vision.description} />
            <p className="text-xs">
              Status: {roadmap.vision.status} • Postęp:{" "}
              {roadmap.vision.progress?.toFixed(1) ?? 0}%
            </p>
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-[--color-border] bg-white/5 p-4 text-sm text-[--color-muted]">
            Brak zdefiniowanej wizji. Użyj formularza powyżej.
          </div>
        )}
      </Panel>

      <Panel title="Milestones" description="Dane z goal store + tasks.">
        {milestones.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[--color-border] bg-white/5 p-4 text-sm text-[--color-muted]">
            Brak kamieni milowych w roadmapie.
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {milestones.map((milestone) => (
              <div
                key={milestone.title}
                className="rounded-xl border border-[--color-border] bg-white/5 p-4"
              >
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-white">
                    {milestone.title}
                  </p>
                  <Badge tone={statusTone(milestone.status)}>{milestone.status}</Badge>
                </div>
                <p className="text-xs text-[--color-muted]">{milestone.description}</p>
                <p className="mt-2 text-xs">
                  Postęp: {milestone.progress?.toFixed(1) ?? 0}% • Priorytet:{" "}
                  {milestone.priority ?? "-"}
                </p>
                <ul className="mt-2 space-y-1 text-xs">
                  {(milestone.tasks || []).map((task, idx) => (
                    <li
                      key={`${milestone.title}-${idx}`}
                      className="rounded border border-[--color-border] bg-black/30 px-2 py-1"
                    >
                      <span className="font-semibold text-white">{task.title}</span>{" "}
                      <span className="text-[--color-muted]">
                        ({task.status || "TODO"})
                      </span>
                    </li>
                  ))}
                  {(milestone.tasks || []).length === 0 && (
                    <li className="text-[--color-muted]">Brak zadań.</li>
                  )}
                </ul>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Pełny raport" description="/api/roadmap (pole report)">
        <MarkdownPreview
          content={roadmap?.report}
          emptyState="Brak raportu."
        />
      </Panel>

      {statusReport && (
        <Panel title="Raport statusu" description="/api/roadmap/status">
          <MarkdownPreview content={statusReport} />
        </Panel>
      )}
    </div>
  );
}

function statusTone(status?: string) {
  if (!status) return "neutral" as const;
  const normalized = status.toUpperCase();
  if (normalized.includes("COMPLETE")) return "success" as const;
  if (normalized.includes("IN_PROGRESS") || normalized.includes("DOING"))
    return "warning" as const;
  return "neutral" as const;
}
