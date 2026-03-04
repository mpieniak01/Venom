import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  clearAllSelfLearningRuns,
  deleteSelfLearningRun,
  getSelfLearningCapabilities,
  getSelfLearningRunStatus,
  listSelfLearningRuns,
  startSelfLearning,
} from "../lib/academy-api";

describe("academy self-learning api client", () => {
  it("uses expected routes for start/status/list/delete/clear", async () => {
    const originalFetch = globalThis.fetch;
    const calls: Array<{ url: string; method: string }> = [];

    globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({
        url: String(input),
        method: init?.method ?? "GET",
      });
      return new Response(
        JSON.stringify({
          run_id: "run-1",
          message: "ok",
          status: "running",
          runs: [],
          count: 0,
          sources: ["docs"],
          mode: "rag_index",
          created_at: "2026-01-01T00:00:00Z",
          progress: {
            files_discovered: 0,
            files_processed: 0,
            chunks_created: 0,
            records_created: 0,
            indexed_vectors: 0,
          },
          artifacts: {},
          logs: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    };

    try {
      await startSelfLearning({
        mode: "rag_index",
        sources: ["docs"],
        limits: {
          max_file_size_kb: 256,
          max_files: 100,
          max_total_size_mb: 20,
        },
        dry_run: true,
      });
      await getSelfLearningRunStatus("run-1");
      await listSelfLearningRuns(10);
      await deleteSelfLearningRun("run-1");
      await clearAllSelfLearningRuns();
      await getSelfLearningCapabilities();
    } finally {
      globalThis.fetch = originalFetch;
    }

    assert.equal(calls.length, 6);
    assert.equal(calls[0]?.url.includes("/api/v1/academy/self-learning/start"), true);
    assert.equal(calls[1]?.url.includes("/api/v1/academy/self-learning/run-1/status"), true);
    assert.equal(calls[2]?.url.includes("/api/v1/academy/self-learning/list?limit=10"), true);
    assert.equal(calls[3]?.method, "DELETE");
    assert.equal(calls[4]?.url.includes("/api/v1/academy/self-learning/all"), true);
    assert.equal(calls[5]?.url.includes("/api/v1/academy/self-learning/capabilities"), true);
  });
});
