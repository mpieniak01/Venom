"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ListCard } from "@/components/ui/list-card";
import { Panel } from "@/components/ui/panel";
import { LogEntry } from "@/components/cockpit/log-entry";
import { PinnedLogCard } from "@/components/cockpit/macro-card";
import type { LogEntryType } from "@/lib/logs";
import type { Task } from "@/lib/types";
import { statusTone } from "@/lib/status";
import { Inbox } from "lucide-react";
import { useTranslation } from "@/lib/i18n";

type CockpitLogsProps = Readonly<{
  connected: boolean;
  logFilter: string;
  onLogFilterChange: (value: string) => void;
  logEntries: LogEntryType[];
  pinnedLogs: LogEntryType[];
  onTogglePin: (entry: LogEntryType) => void;
  exportingPinned: boolean;
  onExportPinnedLogs: () => void;
  onClearPinnedLogs: () => void;
  tasksPreview: Task[];
}>;

export function CockpitLogs({
  connected,
  logFilter,
  onLogFilterChange,
  logEntries,
  pinnedLogs,
  onTogglePin,
  exportingPinned,
  onExportPinnedLogs,
  onClearPinnedLogs,
  tasksPreview,
}: CockpitLogsProps) {
  const t = useTranslation();

  return (
    <>
      <Panel
        title={t("cockpit.logs.title")}
        description={t("cockpit.logs.description")}
        action={
          <Badge tone={connected ? "success" : "warning"}>
            {connected ? t("topBar.connected") : t("topBar.offline")}
          </Badge>
        }
      >
        <div className="space-y-4">
          <input
            className="w-full rounded-full border border-white/10 bg-white/5 px-3 py-1 text-sm text-white outline-none placeholder:text-zinc-500"
            placeholder={t("cockpit.logs.filterPlaceholder")}
            value={logFilter}
            onChange={(event) => onLogFilterChange(event.target.value)}
          />
          <div className="terminal internal-scroll h-64 overflow-y-auto rounded-2xl border border-emerald-500/15 p-4 text-xs shadow-inner shadow-emerald-400/10">
            {logEntries.length === 0 && (
              <p className="text-emerald-200/70">{t("cockpit.logs.waiting")}</p>
            )}
            {logEntries
              .filter((entry) => {
                if (!logFilter.trim()) return true;
                const payload = entry.payload;
                const text =
                  typeof payload === "string"
                    ? payload
                    : JSON.stringify(payload, null, 2);
                return text.toLowerCase().includes(logFilter.toLowerCase());
              })
              .map((entry) => (
                <LogEntry
                  key={entry.id}
                  entry={entry}
                  pinned={pinnedLogs.some((log) => log.id === entry.id)}
                  onPin={() => onTogglePin(entry)}
                />
              ))}
          </div>
          {pinnedLogs.length > 0 && (
            <div className="rounded-3xl card-shell border-emerald-400/20 bg-gradient-to-br from-emerald-500/20 via-emerald-500/5 to-transparent p-4 text-xs">
              <div className="flex flex-wrap items-center gap-3">
                <div>
                  <p className="text-caption text-emerald-200/80">
                    {t("cockpit.logs.pinned.title")}
                  </p>
                  <p className="text-sm text-emerald-100/80">
                    {t("cockpit.logs.pinned.description")}
                  </p>
                </div>
                <div className="ml-auto flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="xs"
                    className="px-3 text-white"
                    disabled={exportingPinned}
                    onClick={onExportPinnedLogs}
                  >
                    {exportingPinned ? t("cockpit.logs.pinned.exporting") : t("cockpit.logs.pinned.export")}
                  </Button>
                  <Button
                    variant="danger"
                    size="xs"
                    className="px-3"
                    onClick={onClearPinnedLogs}
                  >
                    {t("cockpit.logs.pinned.clear")}
                  </Button>
                </div>
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {pinnedLogs.map((log) => (
                  <PinnedLogCard
                    key={`pinned-${log.id}`}
                    log={log}
                    onUnpin={() => onTogglePin(log)}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </Panel>
      <Panel
        title={t("cockpit.tasks.title")}
        description={t("cockpit.tasks.description")}
      >
        <div className="space-y-3">
          {tasksPreview.length === 0 && (
            <EmptyState
              icon={<Inbox className="h-4 w-4" />}
              title={t("cockpit.tasks.emptyTitle")}
              description={t("cockpit.tasks.emptyDescription")}
            />
          )}
          {tasksPreview.map((task, index) => (
            <ListCard
              key={`${(task as Task & { task_id?: string }).task_id ?? task.id ?? "task"}-${index}`}
              title={task.content}
              subtitle={
                task.created_at ? new Date(task.created_at).toLocaleString() : "—"
              }
              badge={<Badge tone={statusTone(task.status)}>{task.status}</Badge>}
            />
          ))}
        </div>
      </Panel>
    </>
  );
}
