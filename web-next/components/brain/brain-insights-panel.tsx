import type { RelationEntry } from "@/components/brain/relation-list";
import { BrainSelectionSummary } from "@/components/brain/selection-summary";
import { RelationList } from "@/components/brain/relation-list";
import { RecentOperations } from "@/components/brain/recent-operations";

type OperationEntry = {
  id: string;
  title: string;
  summary: string;
  timestamp: string | null;
  tags: string[];
};

type BrainInsightsPanelProps = Readonly<{
  selected: Record<string, unknown> | null;
  relations: RelationEntry[];
  recentOperations: OperationEntry[];
  onOpenDetails: () => void;
}>;

export function BrainInsightsPanel({
  selected,
  relations,
  recentOperations,
  onOpenDetails,
}: BrainInsightsPanelProps) {
  return (
    <div className="grid gap-4 lg:grid-cols-3" data-testid="brain-insights-panel">
      <BrainSelectionSummary selected={selected} relations={relations} onOpenDetails={onOpenDetails} />
      <RelationList selectedId={String(selected?.id || "")} relations={relations} />
      <RecentOperations operations={recentOperations} />
    </div>
  );
}
