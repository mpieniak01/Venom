import { apiFetch } from "./api-client";
import type { ExperimentRecipe } from "./academy-experiments-api";

const CAMPAIGNS = "/api/v1/academy/experiments/campaigns";

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
}

export type CampaignStrategy = "fixed" | "optuna";
export type OptunaParameter = "rank" | "alpha" | "learning_rate" | "dropout";
export type OptunaSearchSpace = Partial<Record<OptunaParameter, { low: number; high: number; log?: boolean }>>;

export interface CampaignRequest {
  campaign_id: string;
  profile_id: string;
  variants: ExperimentRecipe[];
  strategy?: CampaignStrategy;
  search_space?: OptunaSearchSpace;
  sampler_seed?: number;
  budget: CampaignBudget;
  selection: CampaignSelection;
  retention: "keep_all" | "discard_rejected";
  review_mode: "manual" | "automatic";
}

export interface CampaignPlan extends Omit<CampaignRequest, "variants"> {
  plan_sha256: string;
  variants: { run_id: string; recipe: ExperimentRecipe; workload: { updates: number; tokens: number } }[];
}

export interface CampaignTrial {
  run_id: string;
  status: string;
  attempt?: number;
  usable_delta?: number;
  critical_delta?: number;
  error?: string | null;
  resume_available?: boolean;
  recipe?: ExperimentRecipe | null;
  optuna_trial_number?: number | null;
  optuna_trial_state?: "WAITING" | "RUNNING" | "COMPLETE" | "PRUNED" | "FAIL" | null;
}

export interface Campaign {
  campaign_id: string;
  plan: CampaignPlan;
  status: string;
  trial_index: number;
  trials: CampaignTrial[];
  selected_run_id?: string | null;
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
