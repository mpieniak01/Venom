"use client";

import type { Lesson } from "@/lib/types";

type LessonListProps = {
  lessons: Lesson[];
  emptyMessage?: string;
};

export function LessonList({ lessons, emptyMessage = "Brak lekcji" }: LessonListProps) {
  if (!lessons.length) {
    return (
      <p className="rounded-2xl box-subtle px-3 py-2 text-sm text-hint">
        {emptyMessage}
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
          <p className="text-hint">{lesson.summary || "Brak opisu."}</p>
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
