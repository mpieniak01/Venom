import type { PassedDataAudit } from "./academy-data-audit";
import { apiFetch } from "./api-client";
import { getApiBaseUrl } from "./env";
import type { ExperimentInitialAdapter, ExperimentRecipe } from "./academy-experiments-api";
import type { CampaignQualityPolicy, TrialQualityGuard } from "./academy-quality-api";

const CAMPAIGNS = "/api/v1/academy/experiments/campaigns";
const REMOTE_TEXT = `${CAMPAIGNS}/remote/text`;

export interface CampaignBudget {
  max_trials: number;
  max_updates: number;
  max_tokens: number;
  max_seconds: number;
  trial_seconds: number;
  max_retries: number;
  max_artifact_bytes: number;
  min_free_bytes: number;
}

export interface CampaignSelection {
  min_usable_delta: number;
  max_critical_delta: number;
  protect_parent_full_pass?: boolean;
}

export type CampaignStrategy = "fixed" | "optuna";
export type OptunaParameter = "rank" | "alpha" | "learning_rate" | "dropout";
export type OptunaSearchSpace = Partial<Record<OptunaParameter, { low: number; high: number; log?: boolean }>>;

export interface CampaignFinalInputs {
  inputs_id: string;
  final_test_sha256: string;
  final_calibration_sha256: string;
  max_seconds: number;
}

export interface CampaignFinalQualification {
  inputs_id: string;
  reserve_seconds: number;
}

export type CampaignQualificationStatus = "pending" | "running" | "passed" | "failed_quality" | "incomplete";

export interface CampaignRequest {
  campaign_id: string;
  profile_id: string;
  variants: Record<string, unknown>[];
  strategy?: CampaignStrategy;
  search_space?: OptunaSearchSpace;
  sampler_seed?: number;
  checkpoint_steps?: number[];
  extension?: { initial_trials: number; min_usable_delta: number; repeat_best_recipe?: boolean };
  budget: CampaignBudget;
  selection: CampaignSelection;
  retention: "keep_all" | "discard_rejected";
  review_mode: "manual" | "automatic";
  quality_policy?: CampaignQualityPolicy | null;
  final_qualification?: CampaignFinalQualification | null;
}

export interface CampaignPlan extends Omit<CampaignRequest, "variants"> {
  plan_sha256: string;
  data_audit?: PassedDataAudit | null;
  variants: {
    run_id: string;
    recipe: ExperimentRecipe;
    initial_adapter?: ExperimentInitialAdapter | null;
    workload: { updates: number; tokens: number };
  }[];
}

export interface CampaignCheckpointEvaluation {
  step: number;
  status: string;
  usable_delta?: number;
  critical_delta?: number;
  quality_guard?: TrialQualityGuard | null;
  result_sha256?: string;
}

export interface CampaignTrial {
  run_id: string;
  status: string;
  attempt?: number;
  usable_delta?: number;
  critical_delta?: number;
  error?: string | null;
  resume_available?: boolean;
  quality_guard?: TrialQualityGuard | null;
  checkpoint_evaluations?: CampaignCheckpointEvaluation[];
  recipe?: ExperimentRecipe | null;
  optuna_trial_number?: number | null;
  optuna_trial_state?: "WAITING" | "RUNNING" | "COMPLETE" | "PRUNED" | "FAIL" | null;
}

export interface Campaign {
  phase?: "trials" | "qualification" | "complete";
  qualification_status?: CampaignQualificationStatus;
  qualification?: { status?: string; qualified?: unknown; reason?: string; usable_delta?: number; critical_delta?: number; parent_full_pass_count?: number; candidate_full_pass_count?: number; full_pass_delta?: number } | null;
  deadline_at?: number | null;
  qualification_attempts?: number;
  repeat_confirmation?: {
    status: "passed" | "failed_quality" | "incomplete";
    repeat_run_id?: string | null;
  } | null;
  campaign_id: string;
  plan: CampaignPlan;
  status: string;
  trial_index: number;
  trials: CampaignTrial[];
  selected_run_id?: string | null;
  selected_checkpoint_step?: number | null;
  extension_decision?: {
    status: "approved" | "skipped";
    run_id: string | null;
    usable_delta: number | null;
  };
  quality_policy_error?: string | null;
  elapsed_seconds: number;
  used_updates: number;
  used_tokens: number;
  retries: number;
  artifact_bytes: number;
  error?: string | null;
}

export interface CampaignRetentionPlan {
  campaign_id: string;
  selected_run_id: string | null;
  files: { run_id: string; path: string; size_bytes: number; sha256: string }[];
  bytes: number;
  plan_sha256: string;
}

function pathFor(campaignId: string) {
  return `${CAMPAIGNS}/${encodeURIComponent(campaignId)}`;
}

export function campaignReportUrl(campaignId: string) {
  return `${pathFor(campaignId)}/report`;
}

interface CampaignListing {
  campaigns: Campaign[];
  capabilities?: { optuna?: { available: boolean; reason?: string | null } };
}

export interface RemoteTextCampaign {
  campaign_id: string;
  status: string;
  plan_sha256: string;
  quote: { estimated_microusd: number };
  cleanup: { state: string };
  cost?: { estimated_microusd?: number; billed_microusd?: number | null } | null;
  stop_requested: boolean;
  deadline_at: number | null;
  last_sync_at: number | null;
  qualification_status?: string;
  remote: Campaign | null;
  evidence: Record<string, { archive_bytes: number }>;
  result: {
    outcome: string;
    best_observed: { run_id: string; usable_delta?: number } | null;
    best_qualified: { run_id: string; adapter_id: string } | null;
  } | null;
  error: string | null;
}

export function listRemoteTextCampaigns(signal?: AbortSignal) {
  return apiFetch<{ campaigns: RemoteTextCampaign[] }>(REMOTE_TEXT, { signal });
}

export function planRemoteTextCampaign(
  campaign: CampaignRequest, planId: string, budget: number, testHash: string, calibrationHash: string,
) {
  return apiFetch<RemoteTextCampaign>(`${REMOTE_TEXT}/plan`, {
    method: "POST",
    body: JSON.stringify({
      campaign,
      environment_plan_id: planId,
      max_cost_microusd: budget,
      final_test_sha256: testHash || null,
      final_calibration_sha256: calibrationHash || null,
    }),
  });
}

export function controlRemoteTextCampaign(campaign: RemoteTextCampaign, action: "start" | "stop") {
  return apiFetch<RemoteTextCampaign>(
    `${REMOTE_TEXT}/${encodeURIComponent(campaign.campaign_id)}/${action}`,
    { method: "POST", body: action === "start" ? JSON.stringify({ plan_sha256: campaign.plan_sha256 }) : undefined },
  );
}

export function remoteTextEvidenceUrl(campaignId: string, runId: string) {
  return `${getApiBaseUrl()}${REMOTE_TEXT}/${encodeURIComponent(campaignId)}/evidence/${encodeURIComponent(runId)}`;
}

export function listCampaignFinalInputs(signal?: AbortSignal) {
  return apiFetch<{ inputs: CampaignFinalInputs[] }>(`${CAMPAIGNS}/final-inputs`, { signal });
}

export function listCampaigns(signal?: AbortSignal) {
  return apiFetch<CampaignListing>(CAMPAIGNS, { signal });
}

export function planCampaign(request: CampaignRequest) {
  return apiFetch<Campaign>(`${CAMPAIGNS}/plan`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function startCampaign(campaignId: string, planSha256: string) {
  return apiFetch<Campaign>(`${pathFor(campaignId)}/start`, {
    method: "POST",
    body: JSON.stringify({ plan_sha256: planSha256 }),
  });
}

export function updateCampaign(campaignId: string, action: "stop" | "resume") {
  return apiFetch<Campaign>(`${pathFor(campaignId)}/${action}`, { method: "POST" });
}

export function getCampaignRetentionPlan(campaignId: string) {
  return apiFetch<CampaignRetentionPlan>(`${pathFor(campaignId)}/retention`);
}

export function applyCampaignRetention(campaignId: string, planSha256: string) {
  return apiFetch<{ removed_bytes: number }>(`${pathFor(campaignId)}/retention`, {
    method: "POST",
    body: JSON.stringify({ plan_sha256: planSha256 }),
  });
}
