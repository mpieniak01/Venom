import assert from "node:assert";
import { describe, it } from "node:test";

import { mapKnowledgeEntriesToLessons } from "../lib/knowledge-entries";
import type { KnowledgeEntriesResponse } from "../lib/types";

describe("mapKnowledgeEntriesToLessons", () => {
  it("maps only lesson-origin entries", () => {
    const payload: KnowledgeEntriesResponse = {
      status: "success",
      count: 2,
      entries: [
        {
          entry_id: "lesson-1",
          entry_type: "lesson",
          scope: "session",
          source: "lessons_store",
          content: "lesson content",
          summary: "lesson summary",
          tags: ["tag-a"],
          created_at: "2026-03-11T10:00:00+00:00",
          source_meta: { origin: "lesson", provenance: {} },
        },
        {
          entry_id: "mem-1",
          entry_type: "memory_entry",
          scope: "session",
          source: "vector_store",
          content: "memory content",
          tags: [],
          created_at: "2026-03-11T10:00:00+00:00",
          source_meta: { origin: "vector", provenance: {} },
        },
      ],
    };

    const mapped = mapKnowledgeEntriesToLessons(payload);
    assert.equal(mapped.count, 1);
    assert.equal(mapped.lessons.length, 1);
    assert.equal(mapped.lessons[0]?.id, "lesson-1");
    assert.equal(mapped.lessons[0]?.title, "lesson summary");
  });

  it("does not stringify object metadata title as [object Object]", () => {
    const payload: KnowledgeEntriesResponse = {
      status: "success",
      count: 1,
      entries: [
        {
          entry_id: "lesson-obj-title",
          entry_type: "lesson",
          scope: "session",
          source: "lessons_store",
          content: "fallback content title",
          summary: "summary title",
          tags: [],
          created_at: "2026-03-11T10:00:00+00:00",
          source_meta: { origin: "lesson", provenance: {} },
          metadata: { title: { nested: true } as unknown as string },
        },
      ],
    };

    const mapped = mapKnowledgeEntriesToLessons(payload);
    assert.equal(mapped.lessons.length, 1);
    assert.equal(mapped.lessons[0]?.title, "summary title");
    assert.notEqual(mapped.lessons[0]?.title, "[object Object]");
  });
});
