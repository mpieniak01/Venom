import type { DataAudit, PassedDataAudit } from "./academy-data-audit";
import type { QualityDecision } from "./academy-quality-api";
import { apiFetch } from "./api-client";

const EXPERIMENTS = "/api/v1/academy/experiments";

export interface ExperimentRecipe {
  rank?: number;
  alpha?: number;
  learning_rate?: number;
  dropout?: number;
}

export interface ExperimentProfile {
  id: string;
  label: string;
  model: string;
  dataset: string;
  automatic_review?: boolean;
  data_audit?: DataAudit | null;
  recipe: ExperimentRecipe;
}

export interface ExperimentInitialAdapter {
  adapter_id: string;
  label: string;
  model: string;
  revision: string;
  snapshot_sha256: string;
  config_sha256: string;
  weights_sha256: string;
  source: { identity: string; sha256: string };
}

export interface ExperimentRun {
  run_id: string;
  profile_id: string;
  status: string;
  stage: string;
  created_at: number;
  updated_at: number;
  elapsed_seconds?: number;
  actions?: { stop: boolean; resume: boolean; evaluate: boolean; review: boolean };
  attempt: number;
  recipe: ExperimentRecipe;
  checkpoint_step?: number | null;
  checkpoint_steps?: number[];
  review_checkpoint_step?: number | null;
  resume_available: boolean;
  error?: string | null;
  report?: ExperimentReport | null;
  initial_adapter?: ExperimentInitialAdapter | null;
  data_audit?: PassedDataAudit | null;
  external_review?: { record_id: string; outcome: QualityDecision } | null;
}

export interface ExperimentMetrics {
  n: number;
  semantic: number;
  usable: number;
  passed: number;
  format: number;
  critical: number;
  runtime_or_length_failure: number;
}

export interface ExperimentAnswer {
  text?: string;
  reason?: string;
  finish?: string | null;
  error?: string | null;
}

export interface ExperimentMessage {
  role: string;
  content: string;
}

export interface ExperimentCase {
  case_id: string;
  messages?: ExperimentMessage[];
  base?: ExperimentAnswer;
  candidate?: ExperimentAnswer;
}

export interface ExperimentArtifact {
  kind: string;
  bytes?: number;
  sha256?: string;
  available: boolean;
}

export type ExperimentVerdict = { semantic: number; usable: number; passed: number };

export interface ExperimentCheckpointResult {
  step: number;
  status: string;
  summaries?: ExperimentReport["summaries"];
  result_sha256?: string;
}

export interface ExperimentReport {
  checkpoint_evaluations?: ExperimentCheckpointResult[];
  initial_adapter?: ExperimentInitialAdapter | null;
  data_audit?: PassedDataAudit | null;
  historical?: boolean;
  summaries: {
    base: Record<string, ExperimentMetrics>;
    candidate: Record<string, ExperimentMetrics>;
  };
  verdicts?: Record<string, Record<string, ExperimentVerdict>>;
  cases?: ExperimentCase[];
  artifacts?: ExperimentArtifact[];
}

interface ReviewCase {
  record_id: string;
  messages?: ExperimentMessage[];
  criteria?: { id: string; kind: string; description?: string }[];
}

export interface ExperimentReview {
  checkpoint_step?: number;
  cases: ReviewCase[];
  answers: { case: ReviewCase; answers: Record<string, ExperimentAnswer> }[];
}

export interface ExperimentStartRequest {
  profile_id: string;
  run_id: string;
  recipe?: ExperimentRecipe;
}

export type ExperimentAction = "stop" | "resume" | "evaluate";

function runPath(runId: string) {
  return `${EXPERIMENTS}/runs/${encodeURIComponent(runId)}`;
}

export async function listInitialAdapters(signal?: AbortSignal) {
  return (await apiFetch<{ adapters: ExperimentInitialAdapter[] }>(`${EXPERIMENTS}/adapters`, { signal })).adapters;
}

export async function listExperimentProfiles(signal?: AbortSignal) {
  return (await apiFetch<{ profiles: ExperimentProfile[] }>(`${EXPERIMENTS}/profiles`, { signal })).profiles;
}

export async function listExperimentRuns(signal?: AbortSignal) {
  return (await apiFetch<{ runs: ExperimentRun[] }>(`${EXPERIMENTS}/runs`, { signal })).runs;
}

export function startExperiment(request: ExperimentStartRequest) {
  return apiFetch<ExperimentRun>(`${EXPERIMENTS}/runs`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function updateExperiment(runId: string, action: ExperimentAction) {
  return apiFetch<ExperimentRun>(`${runPath(runId)}/${action}`, { method: "POST" });
}

export function getExperimentLogs(runId: string, signal?: AbortSignal) {
  return apiFetch<{ logs: string }>(`${runPath(runId)}/logs`, { signal });
}

export function getExperimentReport(runId: string, signal?: AbortSignal) {
  return apiFetch<ExperimentReport>(`${runPath(runId)}/report`, { signal });
}

export function getExperimentReview(runId: string, signal?: AbortSignal) {
  return apiFetch<ExperimentReview>(`${runPath(runId)}/review`, { signal });
}

export function submitExperimentJudgments(
  runId: string, judgments: Record<string, unknown>[], checkpointStep?: number,
) {
  return apiFetch<ExperimentRun>(`${runPath(runId)}/judgments`, {
    method: "POST",
    body: JSON.stringify({ judgments, checkpoint_step: checkpointStep }),
  });
}
