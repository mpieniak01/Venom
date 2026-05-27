"use client";

import type {
  AnalysisResult,
  AnalysisUpdateFn,
} from "@/components/inspector/model-introspection-dashboard-types";

type ParsedSseBlock = {
  event: string;
  data: string;
};

type SseDispatchState = {
  streamStartedAt: number;
  sawFirstChunk: boolean;
  sawAnalysisDone: boolean;
  streamErrorMessage: string | null;
};

type SseDispatchContext = {
  onSetLiveResult: (result: AnalysisResult) => void;
  onPatchLiveResult: (updater: AnalysisUpdateFn) => void;
};

export function parseSseBlock(block: string): ParsedSseBlock | null {
  const trimmed = block.trim();
  if (!trimmed) {
    return null;
  }
  let event = "message";
  const dataLines: string[] = [];
  for (const rawLine of trimmed.split("\n")) {
    const line = rawLine.trimEnd();
    if (line.startsWith("event:")) {
      event = line.slice(6).trim() || "message";
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  return { event, data: dataLines.join("\n") };
}

async function* readSseBlocks(reader: ReadableStreamDefaultReader<Uint8Array>) {
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true }).replaceAll("\r\n", "\n");
    let separatorIndex = buffer.indexOf("\n\n");
    while (separatorIndex !== -1) {
      const block = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      if (block.trim()) {
        yield block;
      }
      separatorIndex = buffer.indexOf("\n\n");
    }
  }
  buffer += decoder.decode().replaceAll("\r\n", "\n");
  if (buffer.trim()) {
    yield buffer;
  }
}

function appendUniqueEvent(events: string[], nextEvent: string): string[] {
  if (events.includes(nextEvent)) {
    return events;
  }
  return [...events, nextEvent];
}

function upsertFirstChunkTimelineEntry(args: {
  timeline: NonNullable<AnalysisResult["analysis"]>["timeline"];
  detail: string;
  atMs: number;
}): NonNullable<AnalysisResult["analysis"]>["timeline"] {
  const { timeline, detail, atMs } = args;
  const firstChunkIndex = timeline.findIndex((entry) => entry.id === "first_chunk");
  if (firstChunkIndex === -1) {
    return [
      ...timeline,
      {
        id: "first_chunk",
        label: "First content chunk",
        status: "done",
        detail,
        at_ms: atMs,
        progress: 40,
      },
    ];
  }
  const nextTimeline = [...timeline];
  const currentEntry = nextTimeline[firstChunkIndex];
  nextTimeline[firstChunkIndex] = {
    ...currentEntry,
    status: "done",
    detail,
    at_ms: atMs,
  };
  return nextTimeline;
}

function applyContentEvent(args: {
  analysis: NonNullable<AnalysisResult["analysis"]>;
  dataText: string;
  state: SseDispatchState;
}): NonNullable<AnalysisResult["analysis"]> {
  const { analysis, dataText, state } = args;
  const payload = dataText ? (JSON.parse(dataText) as { text?: string }) : {};
  const text = String(payload.text ?? "");
  if (!text) {
    return analysis;
  }
  const nextChunkCount = analysis.chunk_count + 1;
  const nowMs = performance.now() - state.streamStartedAt;
  let nextTimeline = analysis.timeline;
  if (!state.sawFirstChunk) {
    state.sawFirstChunk = true;
    nextTimeline = upsertFirstChunkTimelineEntry({
      timeline: analysis.timeline,
      detail: `${nextChunkCount} chunk(s) total`,
      atMs: nowMs,
    });
  }
  return {
    ...analysis,
    response: `${analysis.response}${text}`,
    chunk_count: nextChunkCount,
    events: [...analysis.events, "content"],
    timeline: nextTimeline,
    elapsed_ms: nowMs,
  };
}

function applyDoneEvent(
  analysis: NonNullable<AnalysisResult["analysis"]>,
  state: SseDispatchState,
): NonNullable<AnalysisResult["analysis"]> {
  const nextTimeline = [...analysis.timeline];
  const hasFinalized = nextTimeline.some((entry) => entry.id === "response_finalized");
  if (!hasFinalized) {
    nextTimeline.push({
      id: "response_finalized",
      label: "Response assembled",
      status: "done",
      detail: `${analysis.response.length} chars`,
      at_ms: performance.now() - state.streamStartedAt,
      progress: 85,
    });
  }
  return {
    ...analysis,
    events: [...analysis.events, "done"],
    timeline: nextTimeline,
    elapsed_ms: performance.now() - state.streamStartedAt,
  };
}

function dispatchAnalysisEvent(args: {
  eventName: string;
  dataText: string;
  state: SseDispatchState;
  context: SseDispatchContext;
  onFinalResult: (result: AnalysisResult) => void;
}) {
  const { eventName, dataText, state, context, onFinalResult } = args;
  if (eventName === "analysis_start" || eventName === "analysis_done") {
    if (eventName === "analysis_done") {
      state.sawAnalysisDone = true;
      const finalResult = JSON.parse(dataText) as AnalysisResult;
      onFinalResult(finalResult);
      context.onSetLiveResult({
        ...finalResult,
        status: "running",
      });
      return;
    }
    context.onSetLiveResult(JSON.parse(dataText) as AnalysisResult);
    return;
  }
  if (eventName === "error") {
    state.streamErrorMessage = dataText || "Analysis stream failed";
    context.onPatchLiveResult((analysis) => ({
      ...analysis,
      events: appendUniqueEvent(analysis.events, "error"),
    }));
    return;
  }
  if (eventName === "start") {
    context.onPatchLiveResult((analysis) => ({
      ...analysis,
      events: appendUniqueEvent(analysis.events, "start"),
    }));
    return;
  }
  if (eventName === "content") {
    context.onPatchLiveResult((analysis) =>
      applyContentEvent({ analysis, dataText, state }),
    );
    return;
  }
  if (eventName !== "done") {
    return;
  }
  context.onPatchLiveResult((analysis) => applyDoneEvent(analysis, state));
}

export async function processAnalysisStream(params: {
  response: Response;
  streamStartedAt: number;
  onSetLiveResult: (result: AnalysisResult) => void;
  onPatchLiveResult: (updater: AnalysisUpdateFn) => void;
}): Promise<void> {
  const { response, streamStartedAt, onSetLiveResult, onPatchLiveResult } = params;
  if (!response.body) {
    throw new Error("Streaming response unavailable.");
  }

  const reader = response.body.getReader();
  const state: SseDispatchState = {
    streamStartedAt,
    sawFirstChunk: false,
    sawAnalysisDone: false,
    streamErrorMessage: null,
  };
  const context: SseDispatchContext = { onSetLiveResult, onPatchLiveResult };
  let pendingFinalResult: AnalysisResult | null = null;

  const flushPendingFinalResult = () => {
    if (!pendingFinalResult) {
      return;
    }
    onSetLiveResult(pendingFinalResult);
    pendingFinalResult = null;
  };

  try {
    for await (const block of readSseBlocks(reader)) {
      const parsed = parseSseBlock(block);
      if (!parsed) {
        continue;
      }
      dispatchAnalysisEvent({
        eventName: parsed.event,
        dataText: parsed.data,
        state,
        context,
        onFinalResult: (result) => {
          pendingFinalResult = result;
        },
      });
    }
    flushPendingFinalResult();
    if (state.streamErrorMessage && !state.sawAnalysisDone) {
      flushPendingFinalResult();
      throw new Error(state.streamErrorMessage);
    }
  } catch (streamError) {
    flushPendingFinalResult();
    throw streamError;
  } finally {
    reader.releaseLock();
  }
}

export function updateLiveAnalysisResult(
  liveResult: AnalysisResult | null,
  updater: AnalysisUpdateFn,
): AnalysisResult | null {
  if (!liveResult?.analysis) {
    return liveResult;
  }
  return {
    ...liveResult,
    analysis: updater(liveResult.analysis),
  };
}
