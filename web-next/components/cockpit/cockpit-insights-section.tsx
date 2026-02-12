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
import { useTranslation } from "@/lib/i18n";
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
  readonly chatFullscreen: boolean;
  readonly showArtifacts: boolean;
  readonly showReferenceSections: boolean;
  readonly showSharedSections: boolean;
  readonly usageMetrics?: { memory_usage_percent?: number | null } | null;
  readonly cpuUsageValue: string;
  readonly gpuUsageValue: string;
  readonly ramValue: string;
  readonly vramValue: string;
  readonly diskValue: string;
  readonly diskPercent?: string | null;
  readonly sessionCostValue: string;
  readonly graphNodes: number;
  readonly graphEdges: number;
  readonly agentDeck: AgentDeckEntry[];
  readonly queue: QueueStatus | null;
  readonly queueLoading: boolean;
  readonly queueAction: string | null;
  readonly queueActionMessage: string | null;
  readonly onToggleQueue: () => void;
  readonly onExecuteQueueMutation: (action: "purge" | "emergency") => void;
  readonly history: HistoryRequest[];
  readonly historyStatusEntries: StatusEntry[];
  readonly selectedRequestId?: string | null;
  readonly onSelectHistory: (entry: HistoryRequest) => void;
  readonly loadingHistory: boolean;
  readonly historyError?: string | null;
  readonly learningLogs?: LearningLogsResponse | null;
  readonly learningLoading: boolean;
  readonly learningError?: string | null;
  readonly feedbackLogs?: FeedbackLogsResponse | null;
  readonly feedbackLoading: boolean;
  readonly feedbackError?: string | null;
  readonly hiddenPromptsPanel: ReactNode;
  readonly services: ServiceStatus[] | null | undefined;
  readonly entries: TelemetryEvent[];
  readonly newMacro: { label: string; description: string; content: string };
  readonly setNewMacro: (value: { label: string; description: string; content: string }) => void;
  readonly customMacros: MacroAction[];
  readonly setCustomMacros: (next: MacroAction[]) => void;
  readonly allMacros: MacroAction[];
  readonly macroSending: string | null;
  readonly onRunMacro: (macro: MacroAction) => void;
  readonly onOpenQuickActions: () => void;
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
}: Readonly<CockpitInsightsSectionProps>) {
  const t = useTranslation();

  if (chatFullscreen || !showArtifacts) {
    return null;
  }

  return (
    <>
      {showReferenceSections && (
        <>
          <section className="grid gap-6">
            <Panel
              title={t("cockpit.insights.resources.title")}
              description={t("cockpit.insights.resources.description")}
            >
              <div className="grid gap-3 sm:grid-cols-3">
                <ResourceMetricCard
                  label="CPU"
                  value={cpuUsageValue}
                  hint={t("cockpit.insights.resources.cpuHint")}
                />
                <ResourceMetricCard
                  label="GPU"
                  value={gpuUsageValue}
                  hint={t("cockpit.insights.resources.gpuHint")}
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
                  hint={t("cockpit.insights.resources.vramHint")}
                />
                <ResourceMetricCard label={t("cockpit.insights.resources.title")} value={diskValue} hint={diskPercent ?? ""} />
              </div>
              <div className="mt-4 flex items-center justify-between rounded-2xl box-muted px-4 py-3 text-xs text-zinc-400">
                <span className="uppercase tracking-[0.35em]">{t("cockpit.insights.resources.sessionCost")}</span>
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
                    {t("cockpit.insights.agents.eyebrow")}
                  </p>
                  <h2 className="heading-h2">{t("cockpit.insights.agents.title")}</h2>
                </div>
              </header>
              <div className="flex flex-wrap gap-2 text-xs">
                <Badge tone="neutral">{t("cockpit.insights.agents.nodes")}: {graphNodes}</Badge>
                <Badge tone="neutral">{t("cockpit.insights.agents.edges")}: {graphEdges}</Badge>
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
                        {svc.detail ?? t("common.noDescription")}
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
            title={t("cockpit.history.title")}
            description={t("cockpit.history.description")}
          >
            <HistoryList
              entries={history}
              limit={5}
              selectedId={selectedRequestId}
              onSelect={(entry) => onSelectHistory(entry)}
              variant="preview"
              viewAllHref="/inspector"
              emptyTitle={t("cockpit.history.emptyTitle")}
              emptyDescription={t("cockpit.history.emptyDescription")}
            />
            {loadingHistory && (
              <p className="mt-2 text-hint">{t("cockpit.history.loading")}</p>
            )}
            {historyError && (
              <p className="mt-2 text-xs text-rose-300">{historyError}</p>
            )}
            <p className="mt-2 text-caption">
              {t("cockpit.selection.hint")}
            </p>
          </Panel>
        )}
        {showSharedSections && (
          <Panel
            title={t("cockpit.insights.learning.title")}
            description={t("cockpit.insights.learning.description")}
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
                        {entry.success ? "OK" : t("cockpit.chatStatus.failed")}
                      </Badge>
                      <span>{entry.intent ?? "—"}</span>
                      <span>{formatRelativeTime(entry.timestamp)}</span>
                    </div>
                    <p className="mt-2 text-sm text-white">
                      {(entry.need ?? t("common.noDescription")).slice(0, 160)}
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
                title={t("cockpit.insights.learning.emptyTitle")}
                description={t("cockpit.insights.learning.emptyDescription")}
              />
            )}
            {learningLoading && (
              <p className="mt-2 text-hint">{t("cockpit.insights.learning.loading")}</p>
            )}
            {learningError && (
              <p className="mt-2 text-xs text-rose-300">{learningError}</p>
            )}
          </Panel>
        )}
        {showSharedSections && (
          <Panel
            title={t("cockpit.insights.feedback.title")}
            description={t("cockpit.insights.feedback.description")}
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
                      {(entry.prompt ?? t("common.noDescription")).slice(0, 160)}
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
                title={t("cockpit.insights.feedback.emptyTitle")}
                description={t("cockpit.insights.feedback.emptyDescription")}
              />
            )}
            {feedbackLoading && (
              <p className="mt-2 text-hint">{t("cockpit.insights.feedback.loading")}</p>
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
          title={t("cockpit.insights.macros.title")}
          description={t("cockpit.insights.macros.description")}
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
                      description: newMacro.description.trim() || t("cockpit.insights.macros.desc"),
                      content: newMacro.content.trim(),
                      custom: true,
                    },
                  ]);
                  setNewMacro({ label: "", description: "", content: "" });
                }}
              >
                <p className="text-caption text-zinc-400">{t("cockpit.insights.macros.add")}</p>
                <input
                  className="rounded-xl border border-white/10 bg-black/30 px-2 py-1 text-white outline-none placeholder:text-zinc-500"
                  placeholder={t("cockpit.insights.macros.name")}
                  value={newMacro.label}
                  onChange={(event) =>
                    setNewMacro({ ...newMacro, label: event.target.value })
                  }
                />
                <input
                  className="rounded-xl border border-white/10 bg-black/30 px-2 py-1 text-white outline-none placeholder:text-zinc-500"
                  placeholder={t("cockpit.insights.macros.desc")}
                  value={newMacro.description}
                  onChange={(event) =>
                    setNewMacro({ ...newMacro, description: event.target.value })
                  }
                />
                <textarea
                  className="min-h-[60px] rounded-xl border border-white/10 bg-black/30 px-2 py-1 text-white outline-none placeholder:text-zinc-500"
                  placeholder={t("cockpit.insights.macros.content")}
                  value={newMacro.content}
                  onChange={(event) =>
                    setNewMacro({ ...newMacro, content: event.target.value })
                  }
                />
                <Button type="submit" size="xs" variant="outline" className="px-3">
                  {t("cockpit.insights.macros.submit")}
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
                  {t("cockpit.insights.macros.reset")}
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
            description={t("cockpit.history.description")}
          >
            <div className="grid gap-4 md:grid-cols-2">
              <TaskStatusBreakdown
                title={t("cockpit.metrics.statusTitle")}
                datasetLabel={t("cockpit.history.title")}
                totalLabel={t("common.total")}
                totalValue={(history || []).length}
                entries={historyStatusEntries}
                emptyMessage={t("cockpit.history.emptyDescription")}
              />
              <RecentRequestList requests={history} />
            </div>
          </Panel>

          <Panel
            title={t("cockpit.insights.queue.title")}
            description={t("cockpit.insights.queue.description")}
            action={
              <Badge tone={queue?.paused ? "warning" : "success"}>
                {queue?.paused ? t("cockpit.insights.queue.paused") : t("cockpit.insights.queue.active")}
              </Badge>
            }
          >
            <div className="space-y-4">
              <QueueStatusCard queue={queue} loading={queueLoading && !queue} />
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
                  {t("cockpit.insights.queue.quickActions")}
                </p>
                <Button
                  variant="secondary"
                  size="sm"
                  className="rounded-full border border-emerald-400/40 bg-emerald-500/10 px-4 text-emerald-100 hover:border-emerald-400/60"
                  onClick={onOpenQuickActions}
                >
                  {t("cockpit.insights.queue.openQuickActions")}
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
