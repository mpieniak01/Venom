import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { LessonActions } from "@/components/brain/lesson-actions";
import { LessonStats } from "@/components/brain/lesson-stats";
import { LessonList } from "@/components/tasks/lesson-list";
import type { Lesson } from "@/lib/types";

type LessonStatEntry = {
  label: string;
  value: number;
};

type LessonTagEntry = {
  name: string;
  count: number;
};

type BrainLessonsPanelProps = Readonly<{
  title: string;
  description: string;
  refreshLabel: string;
  lessonStatsEntries: LessonStatEntry[];
  lessonTags: LessonTagEntry[];
  highlightTag: string | null;
  lessons: Lesson[];
  loading?: boolean;
  onRefresh: () => void;
  onSelectTag: (tag: string | null) => void;
}>;

export function BrainLessonsPanel({
  title,
  description,
  refreshLabel,
  lessonStatsEntries,
  lessonTags,
  highlightTag,
  lessons,
  loading = false,
  onRefresh,
  onSelectTag,
}: BrainLessonsPanelProps) {
  return (
    <Panel
      title={title}
      description={description}
      action={
        <Button size="sm" onClick={onRefresh} disabled={loading}>
          {refreshLabel}
        </Button>
      }
    >
      <div className="space-y-4" data-testid="brain-lessons-panel">
        {loading ? <div className="h-20 animate-pulse rounded-2xl border border-white/10 bg-white/5" /> : null}
        <LessonStats entries={lessonStatsEntries} />
        <LessonActions tags={lessonTags} activeTag={highlightTag} onSelect={onSelectTag} />
        <LessonList lessons={lessons || []} />
      </div>
    </Panel>
  );
}
