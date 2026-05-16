import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  computeAnalysisProgress,
  getAnalysisPhase,
  getAnswerStatusLabel,
  getAnswerTone,
  splitAnswerHighlights,
} from "../components/inspector/model-introspection-dashboard-view-model";

describe("model introspection dashboard view-model", () => {
  it("computes waiting progress for running analysis before first chunk", () => {
    const progress = computeAnalysisProgress({
      analysisVisible: true,
      analysisTimelineProgress: 0,
      analysisStepCount: 3,
      chunkCount: 0,
      firstChunkMs: null,
      elapsedMs: 5000,
      analysisStatus: "running",
    });
    assert.ok(progress >= 30);
    assert.ok(progress <= 100);
  });

  it("returns zero progress when analysis is not visible", () => {
    const progress = computeAnalysisProgress({
      analysisVisible: false,
      analysisTimelineProgress: 20,
      analysisStepCount: 3,
      chunkCount: 0,
      firstChunkMs: null,
      elapsedMs: 1000,
      analysisStatus: "idle",
    });
    assert.equal(progress, 0);
  });

  it("maps phase to completed when timeline finalized", () => {
    const phase = getAnalysisPhase({
      analysisVisible: true,
      analysisLoading: false,
      analysisStatus: "running",
      timelineHasResponseFinalized: true,
      firstChunkMs: 10,
      chunkCount: 1,
    });
    assert.equal(phase, "completed");
  });

  it("returns warning tone for contextual answers", () => {
    const tone = getAnswerTone("Potrzebuję więcej kontekstu.", true);
    assert.equal(tone, "warning");
  });

  it("returns streaming answer label for running result without text", () => {
    const label = getAnswerStatusLabel({
      response: "",
      analysisRunning: true,
    });
    assert.equal(label, "streaming answer");
  });

  it("splits answer highlights into short list", () => {
    const highlights = splitAnswerHighlights(
      "Pierwsze zdanie. Drugie zdanie. Trzecie zdanie. Czwarte zdanie. Piąte zdanie.",
    );
    assert.equal(highlights.length, 4);
  });
});
