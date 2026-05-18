"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getServerApiBaseUrl } from "@/lib/env";
import {
  processAnalysisStream,
  updateLiveAnalysisResult,
} from "@/components/inspector/model-introspection-analysis-stream";
import type {
  AnalysisResult,
} from "@/components/inspector/model-introspection-dashboard-types";

type UseModelIntrospectionAnalysisStreamArgs = {
  analysisMechanismEnabled: boolean;
  analysisPrompt: string;
};

type UseModelIntrospectionAnalysisStreamResult = {
  analysisLoading: boolean;
  analysisError: string | null;
  analysisResult: AnalysisResult | null;
  setAnalysisResult: (result: AnalysisResult | null) => void;
  runAnalysis: () => Promise<void>;
};

function resolveApiErrorMessage(errorBody: string): string {
  let message = errorBody || "Analysis failed";
  try {
    const parsed = JSON.parse(errorBody) as { detail?: string };
    message = parsed.detail ?? message;
  } catch {
    // fallback to raw body
  }
  return message;
}

export function useModelIntrospectionAnalysisStream(
  args: UseModelIntrospectionAnalysisStreamArgs,
): UseModelIntrospectionAnalysisStreamResult {
  const { analysisMechanismEnabled, analysisPrompt } = args;
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const isRunningRef = useRef(false);
  const analysisHasPayload = Boolean(analysisResult?.analysis);

  useEffect(() => {
    isRunningRef.current = analysisResult?.status === "running";
  }, [analysisResult?.status]);

  useEffect(() => {
    if (!isRunningRef.current) {
      return;
    }
    if (!analysisHasPayload) {
      return;
    }
    const startedAt = performance.now();
    const timer = globalThis.setInterval(() => {
      if (!isRunningRef.current) {
        globalThis.clearInterval(timer);
        return;
      }
      setAnalysisResult((current) => {
        if (!current?.analysis || current.status !== "running") {
          return current;
        }
        const elapsed = performance.now() - startedAt;
        const nextElapsedMs = Math.max(current.analysis.elapsed_ms, elapsed);
        return {
          ...current,
          analysis: {
            ...current.analysis,
            elapsed_ms: nextElapsedMs,
          },
        };
      });
    }, 200);
    return () => {
      globalThis.clearInterval(timer);
    };
  }, [analysisHasPayload, analysisResult?.status]);

  const runAnalysis = useCallback(async () => {
    if (!analysisPrompt.trim()) {
      setAnalysisError("Prompt cannot be empty.");
      return;
    }
    setAnalysisLoading(true);
    setAnalysisError(null);
    setAnalysisResult(null);
    try {
      const response = await fetch(
        `${getServerApiBaseUrl()}/api/v1/models/introspection/analyze/stream`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify({
            prompt: analysisPrompt,
            live_analysis_enabled: analysisMechanismEnabled,
            max_tokens: 128,
            temperature: 0.2,
            top_p: 0.9,
          }),
        },
      );
      if (!response.ok) {
        const errorBody = await response.text();
        throw new Error(resolveApiErrorMessage(errorBody));
      }
      if (!response.body) {
        throw new Error("Streaming response unavailable.");
      }
      const streamStartedAt = performance.now();
      let liveResult: AnalysisResult | null = null;
      const onSetLiveResult = (nextResult: AnalysisResult) => {
        liveResult = nextResult;
        setAnalysisResult(nextResult);
      };
      const onPatchLiveResult = (
        updater: (
          analysis: NonNullable<AnalysisResult["analysis"]>,
        ) => NonNullable<AnalysisResult["analysis"]>,
      ) => {
        const nextResult = updateLiveAnalysisResult(liveResult, updater);
        if (!nextResult) {
          return;
        }
        liveResult = nextResult;
        setAnalysisResult(nextResult);
      };
      await processAnalysisStream({
        response,
        streamStartedAt,
        onSetLiveResult,
        onPatchLiveResult,
      });
    } catch (analysisRunError) {
      const message =
        analysisRunError instanceof Error
          ? analysisRunError.message
          : "Analysis failed";
      setAnalysisResult(null);
      setAnalysisError(message);
    } finally {
      setAnalysisLoading(false);
    }
  }, [analysisMechanismEnabled, analysisPrompt]);

  return {
    analysisLoading,
    analysisError,
    analysisResult,
    setAnalysisResult,
    runAnalysis,
  };
}
