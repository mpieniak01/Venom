"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Panel } from "@/components/ui/panel";
import { HistoryList } from "@/components/history/history-list";
import { QueueStatusCard } from "@/components/queue/queue-status-card";
import { RecentRequestList } from "@/components/tasks/recent-request-list";
import { TaskStatusBreakdown } from "@/components/tasks/task-status-breakdown";
import { VoiceCommandCenter } from "@/components/voice/voice-command-center";
import { IntegrationMatrix } from "@/components/cockpit/integration-matrix";
import { MacroCard } from "@/components/cockpit/macro-card";
import { CockpitQueue } from "@/components/cockpit/cockpit-queue";
import { ResourceMetricCard } from "@/components/cockpit/cockpit-metric-cards";
import type {
  FeedbackLogsResponse,
  HistoryRequest,
  LearningLogsResponse,
  QueueStatus,
  ServiceStatus,
} from "@/lib/types";
import { formatRelativeTime } from "@/lib/date";
import { Bot, Inbox } from "lucide-react";
import type { ReactNode } from "react";

type MacroAction = {
  id: string;
  label: string;
  description: string;
  content: string;
  custom?: boolean;
};

type AgentDeckEntry = {
  name: string;
  status: string;
  detail?: string;
};

type TelemetryEvent = { id: string; ts: number; payload: unknown };

type StatusEntry = {
  label: string;
  value: number;
  hint?: string;
  tone?: "success" | "warning" | "danger" | "neutral";
  icon?: ReactNode;
};

type CockpitInsightsSectionProps = {
  chatFullscreen: boolean;
  showArtifacts: boolean;
  showReferenceSections: boolean;
  showSharedSections: boolean;
  usageMetrics?: { memory_usage_percent?: number | null } | null;
  cpuUsageValue: string;
  gpuUsageValue: string;
  ramValue: string;
  vramValue: string;
  diskValue: string;
  diskPercent?: string | null;
  sessionCostValue: string;
  graphNodes: number;
  graphEdges: number;
  agentDeck: AgentDeckEntry[];
  queue: QueueStatus | null;
  queueLoading: boolean;
  queueAction: string | null;
  queueActionMessage: string | null;
  onToggleQueue: () => void;
  onExecuteQueueMutation: (action: "purge" | "emergency") => void;
  history: HistoryRequest[];
  historyStatusEntries: StatusEntry[];
  selectedRequestId?: string | null;
  onSelectHistory: (entry: HistoryRequest) => void;
  loadingHistory: boolean;
  historyError?: string | null;
  learningLogs?: LearningLogsResponse | null;
  learningLoading: boolean;
  learningError?: string | null;
  feedbackLogs?: FeedbackLogsResponse | null;
  feedbackLoading: boolean;
  feedbackError?: string | null;
  hiddenPromptsPanel: ReactNode;
  services: ServiceStatus[] | null | undefined;
  entries: TelemetryEvent[];
  newMacro: { label: string; description: string; content: string };
  setNewMacro: (value: { label: string; description: string; content: string }) => void;
  customMacros: MacroAction[];
  setCustomMacros: (next: MacroAction[]) => void;
  allMacros: MacroAction[];
  macroSending: string | null;
  onRunMacro: (macro: MacroAction) => void;
  onOpenQuickActions: () => void;
};

export function CockpitInsightsSection({
  chatFullscreen,
  showArtifacts,
  showReferenceSections,
  showSharedSections,
  usageMetrics,
  cpuUsageValue,
  gpuUsageValue,
  ramValue,
  vramValue,
  diskValue,
  diskPercent,
  sessionCostValue,
  graphNodes,
  graphEdges,
  agentDeck,
  queue,
  queueLoading,
  queueAction,
  queueActionMessage,
  onToggleQueue,
  onExecuteQueueMutation,
  history,
  historyStatusEntries,
  selectedRequestId,
  onSelectHistory,
  loadingHistory,
  historyError,
  learningLogs,
  learningLoading,
  learningError,
  feedbackLogs,
  feedbackLoading,
  feedbackError,
  hiddenPromptsPanel,
  services,
  entries,
  newMacro,
  setNewMacro,
  customMacros,
  setCustomMacros,
  allMacros,
  macroSending,
  onRunMacro,
  onOpenQuickActions,
}: CockpitInsightsSectionProps) {
  if (chatFullscreen || !showArtifacts) {
    return null;
  }

  return (
    <>
      {showReferenceSections && (
        <>
          <section className="grid gap-6">
            <Panel
              title="Zasoby"
              description="Śledź wykorzystanie CPU/GPU/RAM/VRAM/Dysk oraz koszt sesji."
            >
              <div className="grid gap-3 sm:grid-cols-3">
                <ResourceMetricCard
                  label="CPU"
                  value={cpuUsageValue}
                  hint="Średnie obciążenie modeli"
                />
                <ResourceMetricCard
                  label="GPU"
                  value={gpuUsageValue}
                  hint="Wskaźnik wykorzystania akceleratora"
                />
                <ResourceMetricCard
                  label="RAM"
                  value={ramValue}
                  hint={
                    usageMetrics?.memory_usage_percent
                      ? `${usageMetrics.memory_usage_percent.toFixed(0)}%`
                      : ""
                  }
                />
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <ResourceMetricCard
                  label="VRAM"
                  value={vramValue}
                  hint="Aktywny model/GPU"
                />
                <ResourceMetricCard label="Dysk" value={diskValue} hint={diskPercent ?? ""} />
              </div>
              <div className="mt-4 flex items-center justify-between rounded-2xl box-muted px-4 py-3 text-xs text-zinc-400">
                <span className="uppercase tracking-[0.35em]">Koszt sesji</span>
                <span className="text-base font-semibold text-white">{sessionCostValue}</span>
              </div>
            </Panel>
          </section>

          <section className="grid gap-6 xl:grid-cols-[minmax(0,320px)]">
            <div className="glass-panel flex flex-col gap-4">
              <header className="flex items-center gap-3">
                <div className="rounded-2xl bg-violet-600/30 p-3 text-violet-100 shadow-neon">
                  <Bot className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
                    Agenci
                  </p>
                  <h2 className="heading-h2">Aktywność systemowa</h2>
                </div>
              </header>
              <div className="flex flex-wrap gap-2 text-xs">
                <Badge tone="neutral">Węzły: {graphNodes}</Badge>
                <Badge tone="neutral">Krawędzie: {graphEdges}</Badge>
              </div>
              <div className="space-y-3">
                {agentDeck.map((svc) => (
                  <div
                    key={svc.name}
                    className="flex items-center justify-between rounded-xl border border-white/5 bg-white/5 px-3 py-2 text-sm"
                  >
                    <div>
                      <p className="font-semibold text-white">{svc.name}</p>
                      <p className="text-xs text-zinc-500">
                        {svc.detail ?? "Brak opisu"}
                      </p>
                    </div>
                    <Badge tone={serviceTone(svc.status)}>{svc.status}</Badge>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <CockpitQueue
            queue={queue}
            queueAction={queueAction}
            queueActionMessage={queueActionMessage}
            onToggleQueue={onToggleQueue}
            onExecuteQueueMutation={onExecuteQueueMutation}
          />
        </>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {showReferenceSections && (
          <Panel
            title="Historia requestów"
            description="Ostatnie /api/v1/history/requests – kliknij, by odczytać szczegóły."
          >
            <HistoryList
              entries={history}
              limit={5}
              selectedId={selectedRequestId}
              onSelect={(entry) => onSelectHistory(entry)}
              variant="preview"
              viewAllHref="/inspector"
              emptyTitle="Brak historii"
              emptyDescription="Historia requestów pojawi się po wysłaniu zadań."
            />
            {loadingHistory && (
              <p className="mt-2 text-hint">Ładowanie szczegółów...</p>
            )}
            {historyError && (
              <p className="mt-2 text-xs text-rose-300">{historyError}</p>
            )}
            <p className="mt-2 text-caption">
              Kliknij element listy, aby otworzyć panel boczny „Szczegóły requestu”.
            </p>
          </Panel>
        )}
        {showSharedSections && (
          <Panel
            title="Logi nauki"
            description="Ostatnie wpisy LLM-only z `/api/v1/learning/logs`."
          >
            {learningLogs?.items?.length ? (
              <div className="space-y-3">
                {learningLogs.items.map((entry, idx) => (
                  <div
                    key={`learning-${entry.task_id ?? idx}`}
                    className="rounded-2xl box-muted p-3 text-xs text-zinc-300"
                  >
                    <div className="flex flex-wrap items-center gap-2 text-caption">
                      <Badge tone={entry.success ? "success" : "danger"}>
                        {entry.success ? "OK" : "Błąd"}
                      </Badge>
                      <span>{entry.intent ?? "—"}</span>
                      <span>{formatRelativeTime(entry.timestamp)}</span>
                    </div>
                    <p className="mt-2 text-sm text-white">
                      {(entry.need ?? "Brak opisu potrzeby.").slice(0, 160)}
                    </p>
                    {entry.error && (
                      <p className="mt-2 text-hint text-rose-300">
                        {entry.error.slice(0, 140)}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                icon={<Inbox className="h-4 w-4" />}
                title="Brak logów nauki"
                description="LLM-only zapisy pojawią się po pierwszych odpowiedziach."
              />
            )}
            {learningLoading && (
              <p className="mt-2 text-hint">Ładowanie logów nauki...</p>
            )}
            {learningError && (
              <p className="mt-2 text-xs text-rose-300">{learningError}</p>
            )}
          </Panel>
        )}
        {showSharedSections && (
          <Panel
            title="Feedback"
            description="Ostatnie oceny użytkowników z `/api/v1/feedback/logs`."
          >
            {feedbackLogs?.items?.length ? (
              <div className="space-y-3">
                {feedbackLogs.items.map((entry, idx) => (
                  <div
                    key={`feedback-${entry.task_id ?? "unknown"}-${entry.timestamp ?? idx}-${idx}`}
                    className="rounded-2xl box-muted p-3 text-xs text-zinc-300"
                  >
                    <div className="flex flex-wrap items-center gap-2 text-caption">
                      <Badge tone={entry.rating === "up" ? "success" : "danger"}>
                        {entry.rating === "up" ? "👍" : "👎"}
                      </Badge>
                      <span>{entry.intent ?? "—"}</span>
                      <span>{formatRelativeTime(entry.timestamp)}</span>
                    </div>
                    <p className="mt-2 text-sm text-white">
                      {(entry.prompt ?? "Brak promptu.").slice(0, 160)}
                    </p>
                    {entry.comment && (
                      <p className="mt-2 text-hint">
                        {entry.comment.slice(0, 140)}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                icon={<Inbox className="h-4 w-4" />}
                title="Brak feedbacku"
                description="Oceny pojawią się po pierwszych rundach."
              />
            )}
            {feedbackLoading && (
              <p className="mt-2 text-hint">Ładowanie feedbacku...</p>
            )}
            {feedbackError && (
              <p className="mt-2 text-xs text-rose-300">{feedbackError}</p>
            )}
          </Panel>
        )}
        {showReferenceSections && hiddenPromptsPanel}
      </div>

      {showReferenceSections && showArtifacts && (
        <section className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
          <VoiceCommandCenter />
          <IntegrationMatrix services={services} events={entries} />
        </section>
      )}

      {showSharedSections && showArtifacts && (
        <Panel
          title="Makra Cockpitu"
          description="Najczęściej używane polecenia wysyłane jednym kliknięciem."
          action={
            <div className="flex flex-col gap-3 rounded-2xl box-base p-3 text-xs text-white">
              <form
                className="flex flex-col gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!newMacro.label.trim() || !newMacro.content.trim()) return;
                  setCustomMacros([
                    ...customMacros,
                    {
                      id: `custom-${customMacros.length + 1}`,
                      label: newMacro.label.trim(),
                      description: newMacro.description.trim() || "Makro użytkownika",
                      content: newMacro.content.trim(),
                      custom: true,
                    },
                  ]);
                  setNewMacro({ label: "", description: "", content: "" });
                }}
              >
                <p className="text-caption text-zinc-400">Dodaj makro</p>
                <input
                  className="rounded-xl border border-white/10 bg-black/30 px-2 py-1 text-white outline-none placeholder:text-zinc-500"
                  placeholder="Nazwa"
                  value={newMacro.label}
                  onChange={(event) =>
                    setNewMacro({ ...newMacro, label: event.target.value })
                  }
                />
                <input
                  className="rounded-xl border border-white/10 bg-black/30 px-2 py-1 text-white outline-none placeholder:text-zinc-500"
                  placeholder="Opis"
                  value={newMacro.description}
                  onChange={(event) =>
                    setNewMacro({ ...newMacro, description: event.target.value })
                  }
                />
                <textarea
                  className="min-h-[60px] rounded-xl border border-white/10 bg-black/30 px-2 py-1 text-white outline-none placeholder:text-zinc-500"
                  placeholder="Treść polecenia / prompt"
                  value={newMacro.content}
                  onChange={(event) =>
                    setNewMacro({ ...newMacro, content: event.target.value })
                  }
                />
                <Button type="submit" size="xs" variant="outline" className="px-3">
                  Dodaj makro
                </Button>
              </form>
              {customMacros.length > 0 && (
                <Button
                  type="button"
                  size="xs"
                  variant="danger"
                  className="px-3"
                  onClick={() => setCustomMacros([])}
                >
                  Resetuj makra użytkownika
                </Button>
              )}
            </div>
          }
        >
          <div className="grid gap-4 lg:grid-cols-2">
            {allMacros.map((macro) => (
              <MacroCard
                key={macro.id}
                title={macro.label}
                description={macro.description}
                isCustom={macro.custom}
                pending={macroSending === macro.id}
                onRun={() => onRunMacro(macro)}
                onRemove={
                  macro.custom
                    ? () =>
                        setCustomMacros(
                          customMacros.filter((item) => item.id !== macro.id)
                        )
                    : undefined
                }
              />
            ))}
          </div>
        </Panel>
      )}

      {showReferenceSections && showArtifacts && (
        <>
          <Panel
            title="Task Insights"
            description="Podsumowanie statusów i ostatnich requestów /history/requests."
          >
            <div className="grid gap-4 md:grid-cols-2">
              <TaskStatusBreakdown
                title="Statusy"
                datasetLabel="Ostatnie 50 historii"
                totalLabel="Historia"
                totalValue={(history || []).length}
                entries={historyStatusEntries}
                emptyMessage="Brak historii do analizy."
              />
              <RecentRequestList requests={history} />
            </div>
          </Panel>

          <Panel
            title="Zarządzanie kolejką"
            description="Stan kolejki i szybkie akcje – zarządzaj z jednego miejsca."
            action={
              <Badge tone={queue?.paused ? "warning" : "success"}>
                {queue?.paused ? "Wstrzymana" : "Aktywna"}
              </Badge>
            }
          >
            <div className="space-y-4">
              <QueueStatusCard queue={queue} loading={queueLoading && !queue} />
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
                  Akcje dostępne w panelu Quick Actions.
                </p>
                <Button
                  variant="secondary"
                  size="sm"
                  className="rounded-full border border-emerald-400/40 bg-emerald-500/10 px-4 text-emerald-100 hover:border-emerald-400/60"
                  onClick={onOpenQuickActions}
                >
                  ⚡ Otwórz Quick Actions
                </Button>
              </div>
            </div>
          </Panel>
        </>
      )}
    </>
  );
}

function serviceTone(status?: string) {
  if (!status) return "neutral" as const;
  const lower = status.toLowerCase();
  if (lower.includes("healthy") || lower.includes("ok")) return "success" as const;
  if (lower.includes("degraded") || lower.includes("warn")) return "warning" as const;
  if (lower.includes("down") || lower.includes("error") || lower.includes("fail"))
    return "danger" as const;
  return "neutral" as const;
}
