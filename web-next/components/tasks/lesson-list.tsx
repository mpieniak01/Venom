"use client";

import type { Lesson } from "@/lib/types";
import { useTranslation } from "@/lib/i18n";

type LessonListProps = {
  lessons: Lesson[];
  emptyMessage?: string;
};

export function LessonList({ lessons, emptyMessage }: LessonListProps) {
  const t = useTranslation();
  const finalEmptyMessage = emptyMessage || t("brain.lessons.emptyDescription");

  if (!lessons.length) {
    return (
      <p className="rounded-2xl box-subtle px-3 py-2 text-sm text-hint">
        {finalEmptyMessage}
      </p>
    );
  }

  return (
    <ul className="space-y-2 text-sm text-zinc-300">
      {lessons.map((lesson, index) => (
        <li
          key={`${lesson.id ?? lesson.title ?? "lesson"}-${index}`}
          className="rounded-2xl box-base px-3 py-2"
        >
          <span className="font-semibold text-white">{lesson.title}</span>
          <p className="text-hint">{lesson.summary || t("brain.recentOperations.defaultSummary")}</p>
          {lesson.tags && lesson.tags.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {lesson.tags.map((tag, tagIndex) => (
                <span
                  key={`${tag}-${tagIndex}`}
                  className="pill-badge text-zinc-400"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
