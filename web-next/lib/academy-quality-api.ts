import { apiFetch } from "./api-client";

const QUALITY = "/api/v1/academy/experiments/campaigns/quality";

export interface QualityRecord {
  record_id: string;
  split: string;
  identity?: { model?: string; base_sha256?: string; dataset_sha256?: string; protocol_sha256?: string };
  source: { identity: string; sha256?: string };
  outcome?: QualityDecision | null;
  result_sha256?: string;
  evidence_gaps?: string[];
}

export type QualityDecision = "GO" | "REVISE" | "STOP" | "INCOMPLETE";

export interface QualityCounts {
  category: string;
  n: number;
  candidate_usable: number;
  base_usable?: number;
  reference_usable?: number;
  candidate_critical?: number | null;
  lost_usable?: number | null;
  gained_usable?: number | null;
}

export interface QualityProposal {
  status: "ready" | "insufficient_evidence";
  kind: "isolate_recipe_factor" | null;
  factor: string | null;
  reference_id: string | null;
  variants: { name: string; recipe: Record<string, unknown> }[];
  reasons: string[];
  measurement?: ("usable_by_category" | "protected_cases" | "critical_errors")[];
  stop_condition?: "stop_on_protected_regression_or_new_critical";
  fixed?: { train_sha256: string | null; runtime: Record<string, unknown> | null };
}

export interface QualityAnalysis {
  record: QualityRecord;
  decision: QualityDecision;
  reference_id?: string | null;
  comparable: boolean;
  comparison_issues: string[];
  summary: QualityCounts[];
  comparison: QualityCounts[];
  findings: { code: string; fields?: string[]; case_ids?: string[] }[];
  protected_case_ids: string[];
  protected?: { total: number; evaluated: number; passed: number; missing_case_ids?: string[] };
  proposal: QualityProposal;
  recommended_profile_id?: string | null;
}

export interface CampaignQualityPolicy {
  reference_record_ids: string[];
  protected_case_ids: string[];
  protect_reference_hits: boolean;
  protect_base_hits: boolean;
  min_category_usable_delta: Record<string, number>;
  no_new_critical: boolean;
  hypothesis?: string | null;
  references?: { record_id: string; result_sha256: string }[];
}

export interface TrialQualityGuard {
  status: "passed" | "rejected" | "blocked";
  reasons: { code: string; category?: string; count?: number }[];
  protected_count: number | null;
  lost_case_ids: string[];
  new_critical_case_ids: string[];
  category_deltas: Record<string, { n: number; usable_delta: number; minimum: number | null }>;
}

export interface QualityCampaignDraft {
  profileId?: string | null;
  variants: QualityProposal["variants"];
  qualityPolicy: CampaignQualityPolicy;
}

export async function listQualityRecords(signal?: AbortSignal) {
  return (await apiFetch<{ records: QualityRecord[] }>(QUALITY, { signal })).records;
}

export function getQualityAnalysis(recordId: string, referenceId: string, signal?: AbortSignal) {
  const query = referenceId ? `?reference_id=${encodeURIComponent(referenceId)}` : "";
  return apiFetch<QualityAnalysis>(`${QUALITY}/${encodeURIComponent(recordId)}/analysis${query}`, { signal });
}
