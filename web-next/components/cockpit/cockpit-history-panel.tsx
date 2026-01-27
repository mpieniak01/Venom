"use client";

import { Panel } from "@/components/ui/panel";
import { HistoryList } from "@/components/history/history-list";

import type { HistoryRequest } from "@/lib/types";

type CockpitHistoryPanelProps = {
  history: HistoryRequest[];
  selectedRequestId: string | null;
  onSelect: (entry: HistoryRequest) => void;
  loadingHistory: boolean;
  historyError: string | null;
};

export function CockpitHistoryPanel({
  history,
  selectedRequestId,
  onSelect,
  loadingHistory,
  historyError,
}: CockpitHistoryPanelProps) {
  return (
    <Panel
      title="Historia requestów"
      description="Najnowsze zadania użytkownika z /api/v1/history/requests."
    >
      <HistoryList
        entries={history}
        limit={6}
        selectedId={selectedRequestId}
        onSelect={(entry) => onSelect(entry)}
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
    </Panel>
  );
}
