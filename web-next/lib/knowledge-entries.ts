import type { KnowledgeEntriesResponse, Lesson, LessonsResponse } from "@/lib/types";

function _fallbackLessonTitle(content: string, index: number): string {
  const normalized = content.trim();
  if (!normalized) {
    return `Lesson ${index + 1}`;
  }
  return normalized.slice(0, 72);
}

function _coerceOptionalString(value: unknown): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }
  const normalized = value.trim();
  return normalized || undefined;
}

export function mapKnowledgeEntriesToLessons(
  payload: KnowledgeEntriesResponse,
): LessonsResponse {
  const entries = Array.isArray(payload.entries) ? payload.entries : [];
  const lessons: Lesson[] = entries
    .filter((entry) => entry.source_meta?.origin === "lesson")
    .map((entry, index) => {
      const metadata =
        entry.metadata && typeof entry.metadata === "object" ? entry.metadata : {};
      const title =
        _coerceOptionalString(metadata["title"]) ??
        _coerceOptionalString(entry.summary) ??
        _fallbackLessonTitle(entry.content, index);
      return {
        id: entry.entry_id,
        title,
        summary: entry.summary ?? entry.content,
        tags: Array.isArray(entry.tags) ? entry.tags : [],
        created_at: entry.created_at,
        metadata,
      };
    });

  return {
    status: payload.status ?? "success",
    count: lessons.length,
    lessons,
  };
}
