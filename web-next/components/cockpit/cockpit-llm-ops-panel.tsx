"use client";

import type { LogEntryType } from "@/lib/logs";
import type { LlmServerInfo, Task } from "@/lib/types";
import type { SelectMenuOption } from "@/components/ui/select-menu";
import { CockpitLogs } from "@/components/cockpit/cockpit-logs";
import { CockpitModels } from "@/components/cockpit/cockpit-models";

type CockpitLlmOpsPanelProps = Readonly<{
  llmServersLoading: boolean;
  llmServers: LlmServerInfo[];
  selectedLlmServer: string;
  llmServerOptions: SelectMenuOption[];
  onSelectLlmServer: (value: string) => void;
  selectedLlmModel: string;
  llmModelOptions: SelectMenuOption[];
  onSelectLlmModel: (value: string) => void;
  availableModelsForServer: Array<{ name?: string }>;
  selectedServerEntry?: LlmServerInfo | null;
  resolveServerStatus: (displayName?: string, status?: string | null) => string;
  sessionId: string;
  memoryAction: "session" | "global" | null;
  onSessionReset: () => void;
  onServerSessionReset: () => void;
  onClearSessionMemory: () => void;
  onClearGlobalMemory: () => void;
  activeServerInfo?: { active_model?: string | null } | null;
  activeServerName?: string | null;
  llmActionPending: string | null;
  onActivateServer: () => void;
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

export function CockpitLlmOpsPanel({
  llmServersLoading,
  llmServers,
  selectedLlmServer,
  llmServerOptions,
  onSelectLlmServer,
  selectedLlmModel,
  llmModelOptions,
  onSelectLlmModel,
  availableModelsForServer,
  selectedServerEntry,
  resolveServerStatus,
  sessionId,
  memoryAction,
  onSessionReset,
  onServerSessionReset,
  onClearSessionMemory,
  onClearGlobalMemory,
  activeServerInfo,
  activeServerName,
  llmActionPending,
  onActivateServer,
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
}: CockpitLlmOpsPanelProps) {
  return (
    <>
      <CockpitModels
        llmServersLoading={llmServersLoading}
        llmServers={llmServers}
        selectedLlmServer={selectedLlmServer}
        llmServerOptions={llmServerOptions}
        onSelectLlmServer={onSelectLlmServer}
        selectedLlmModel={selectedLlmModel}
        llmModelOptions={llmModelOptions}
        onSelectLlmModel={onSelectLlmModel}
        availableModelsForServer={availableModelsForServer}
        selectedServerEntry={selectedServerEntry}
        resolveServerStatus={resolveServerStatus}
        sessionId={sessionId}
        memoryAction={memoryAction}
        onSessionReset={onSessionReset}
        onServerSessionReset={onServerSessionReset}
        onClearSessionMemory={onClearSessionMemory}
        onClearGlobalMemory={onClearGlobalMemory}
        activeServerInfo={activeServerInfo}
        activeServerName={activeServerName}
        llmActionPending={llmActionPending}
        onActivateServer={onActivateServer}
      />
      <CockpitLogs
        connected={connected}
        logFilter={logFilter}
        onLogFilterChange={onLogFilterChange}
        logEntries={logEntries}
        pinnedLogs={pinnedLogs}
        onTogglePin={onTogglePin}
        exportingPinned={exportingPinned}
        onExportPinnedLogs={onExportPinnedLogs}
        onClearPinnedLogs={onClearPinnedLogs}
        tasksPreview={tasksPreview}
      />
    </>
  );
}
