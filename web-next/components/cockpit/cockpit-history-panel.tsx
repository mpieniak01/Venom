"use client";

import { Panel } from "@/components/ui/panel";
import { HistoryList } from "@/components/history/history-list";
import { useTranslation } from "@/lib/i18n";

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
  const t = useTranslation();

  return (
    <Panel
      title={t("cockpit.history.title")}
      description={t("cockpit.history.description")}
    >
      <HistoryList
        entries={history}
        limit={6}
        selectedId={selectedRequestId}
        onSelect={(entry) => onSelect(entry)}
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
    </Panel>
  );
}
