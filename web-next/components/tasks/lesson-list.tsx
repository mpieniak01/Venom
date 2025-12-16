"use client";

import type { Lesson } from "@/lib/types";

type LessonListProps = {
  lessons: Lesson[];
  emptyMessage?: string;
};

export function LessonList({ lessons, emptyMessage = "Brak lekcji" }: LessonListProps) {
  if (!lessons.length) {
    return (
      <p className="rounded-2xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-zinc-500">
        {emptyMessage}
      </p>
    );
  }

  return (
    <ul className="space-y-2 text-sm text-zinc-300">
      {lessons.map((lesson, index) => (
        <li
          key={`${lesson.id ?? lesson.title ?? "lesson"}-${index}`}
          className="rounded-2xl border border-white/10 bg-white/5 px-3 py-2"
        >
          <span className="font-semibold text-white">{lesson.title}</span>
          <p className="text-xs text-zinc-400">{lesson.summary || "Brak opisu."}</p>
          {lesson.tags && lesson.tags.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {lesson.tags.map((tag, tagIndex) => (
                <span
                  key={`${tag}-${tagIndex}`}
                  className="rounded-full bg-white/10 px-2 py-[2px] text-[10px] uppercase tracking-wide text-zinc-400"
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
