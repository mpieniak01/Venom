"use client";

import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { HistoryList } from "@/components/history/history-list";
import { TaskStatusBreakdown } from "@/components/tasks/task-status-breakdown";
import type { HistoryRequest } from "@/lib/types";
import { RefreshCw } from "lucide-react";

type Translator = (key: string, params?: Record<string, string | number>) => string;

type Props = {
  t: Translator;
  hidden: boolean;
  history?: HistoryRequest[] | null;
  selectedId: string | null;
  onSelect: (requestId: string) => void;
  onRefresh: () => Promise<void>;
  refreshPending: boolean;
  activeTasks: number;
  taskBreakdown: Array<{ status: string; count: number }>;
};

export function InspectorSidebar({
  t,
  hidden,
  history,
  selectedId,
  onSelect,
  onRefresh,
  refreshPending,
  activeTasks,
  taskBreakdown,
}: Props) {
  if (hidden) return null;

  return (
    <aside className="space-y-4">
      <Panel
        title={t("inspector.panels.queue.title")}
        description={t("inspector.panels.queue.description")}
        action={
          <Button
            variant="outline"
            size="xs"
            onClick={onRefresh}
            disabled={refreshPending}
          >
            <RefreshCw className="mr-2 h-3.5 w-3.5" />
            {refreshPending ? t("inspector.actions.refreshing") : t("inspector.actions.refresh")}
          </Button>
        }
      >
        <div className="relative min-h-[280px]">
          <HistoryList
            entries={history}
            selectedId={selectedId}
            onSelect={(entry) => onSelect(entry.request_id)}
            emptyTitle={t("inspector.panels.queue.emptyTitle")}
            emptyDescription={t("inspector.panels.queue.emptyDesc")}
          />
        </div>
      </Panel>

      <Panel
        title={t("inspector.panels.telemetry.title")}
        description={t("inspector.panels.telemetry.description")}
      >
        <TaskStatusBreakdown
          title={t("inspector.panels.telemetry.title")}
          datasetLabel={t("inspector.panels.telemetry.dataset")}
          totalLabel={t("inspector.panels.telemetry.active")}
          totalValue={activeTasks}
          entries={taskBreakdown.map((entry) => ({
            label: entry.status,
            value: entry.count,
          }))}
          emptyMessage={t("inspector.panels.telemetry.empty")}
        />
      </Panel>
    </aside>
  );
}
