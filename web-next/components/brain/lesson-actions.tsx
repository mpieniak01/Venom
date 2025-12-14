"use client";

import type { TagEntry } from "@/app/brain/page";
import { Button } from "@/components/ui/button";

type LessonActionsProps = {
  tags: TagEntry[];
  activeTag: string | null;
  onSelect: (tag: string | null) => void;
};

const PRESET_TAGS = ["agent", "memory", "analysis", "ops"];

export function LessonActions({ tags, activeTag, onSelect }: LessonActionsProps) {
  const mergedTags = mergeTags(tags);
  return (
    <div className="flex flex-wrap gap-2 text-xs">
      <Button
        size="xs"
        variant={activeTag === null ? "primary" : "outline"}
        onClick={() => onSelect(null)}
      >
        Wszystkie
      </Button>
      {mergedTags.map((tag) => (
        <Button
          key={tag.name}
          size="xs"
          variant={activeTag === tag.name ? "primary" : "outline"}
          onClick={() => onSelect(tag.name)}
        >
          #{tag.name}
          <span className="ml-2 text-[10px] uppercase text-zinc-500">{tag.count}</span>
        </Button>
      ))}
    </div>
  );
}

function mergeTags(tags: TagEntry[]) {
  const merged: Record<string, number> = {};
  PRESET_TAGS.forEach((name) => {
    merged[name] = 0;
  });
  tags.forEach((tag) => {
    merged[tag.name] = (merged[tag.name] || 0) + tag.count;
  });
  return Object.entries(merged)
    .filter(([, count]) => count > 0)
    .map(([name, count]) => ({ name, count }));
}
