import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  parseSseBlock,
  processAnalysisStream,
  updateLiveAnalysisResult,
} from "../components/inspector/model-introspection-analysis-stream";
import type { AnalysisResult } from "../components/inspector/model-introspection-dashboard-types";

function encode(text: string): Uint8Array {
  return new TextEncoder().encode(text);
}

function makeRunningResult(): AnalysisResult {
  return {
    status: "running",
    analysis: {
      prompt: "Co to jest slonce?",
      response: "",
      chunk_count: 0,
      events: [],
      timeline: [
        {
          id: "snapshot_before",
          label: "Snapshot captured",
          status: "done",
          detail: "runtime",
          at_ms: 0,
          progress: 0,
        },
        {
          id: "request_ready",
          label: "Prompt prepared",
          status: "done",
          detail: "prompt",
          at_ms: 0,
          progress: 10,
        },
      ],
      elapsed_ms: 0,
      provider: "multi_runtime",
      model: "gemma",
      runtime_label: "runtime",
    },
  };
}

describe("model introspection analysis stream parser", () => {
  it("parses event and data lines", () => {
    const parsed = parseSseBlock('event: content\ndata: {"text":"abc"}\n');
    assert.deepEqual(parsed, { event: "content", data: '{"text":"abc"}' });
  });

  it("returns null for empty blocks", () => {
    assert.equal(parseSseBlock("\n\n"), null);
  });
});

describe("model introspection stream processor", () => {
  it("handles chunk boundary and assembles content timeline", async () => {
    const blocks = [
      `event: analysis_start\ndata: ${JSON.stringify(makeRunningResult())}\n\n`,
      "event: start\ndata: {}\n\n",
      'event: content\ndata: {"text":"Slonce "}\n',
      '\nevent: content\ndata: {"text":"to gwiazda."}\n\n',
      "event: done\ndata: {}\n\n",
      `event: analysis_done\ndata: ${JSON.stringify({
        ...makeRunningResult(),
        status: "completed",
        analysis: {
          ...makeRunningResult().analysis!,
          response: "Slonce to gwiazda.",
          chunk_count: 2,
          events: ["start", "content", "content", "done"],
        },
      })}\n\n`,
    ];
    const response = new Response(
      new ReadableStream({
        start(controller) {
          for (const block of blocks) {
            controller.enqueue(encode(block));
          }
          controller.close();
        },
      }),
      { status: 200, headers: { "Content-Type": "text/event-stream" } },
    );
    const collected: AnalysisResult[] = [];
    let liveResult: AnalysisResult | null = null;
    await processAnalysisStream({
      response,
      streamStartedAt: performance.now(),
      onSetLiveResult: (result) => {
        liveResult = result;
        collected.push(result);
      },
      onPatchLiveResult: (updater) => {
        liveResult = updateLiveAnalysisResult(liveResult, updater);
      },
    });
    assert.ok(collected.length >= 2);
    const finalResult = collected.at(-1);
    assert.ok(finalResult);
    assert.equal(finalResult?.status, "completed");
  });

  it("throws when error arrives without analysis_done", async () => {
    const response = new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(encode("event: error\ndata: analysis failed\n\n"));
          controller.close();
        },
      }),
      { status: 200, headers: { "Content-Type": "text/event-stream" } },
    );

    await assert.rejects(
      () =>
        processAnalysisStream({
          response,
          streamStartedAt: performance.now(),
          onSetLiveResult: () => undefined,
          onPatchLiveResult: () => undefined,
        }),
      /analysis failed/,
    );
  });
});
