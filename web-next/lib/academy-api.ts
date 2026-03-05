/**
 * Academy API Client
 *
 * API client dla endpointów THE_ACADEMY - trenowanie modeli.
 */

import { apiFetch } from "./api-client";
import { getApiBaseUrl } from "./env";

export interface DatasetStats {
  total_examples: number;
  lessons_collected: number;
  git_commits_collected: number;
  removed_low_quality: number;
  avg_input_length: number;
  avg_output_length: number;
  by_source?: Record<string, number>;
}

export interface DatasetResponse {
  success: boolean;
  dataset_path?: string;
  statistics: DatasetStats;
  message: string;
}

export interface TrainingParams {
  dataset_path?: string;
  base_model?: string;
  lora_rank?: number;
  learning_rate?: number;
  num_epochs?: number;
  batch_size?: number;
  max_seq_length?: number;
}

export interface TrainingResponse {
  success: boolean;
  job_id?: string;
  message: string;
  parameters: Record<string, unknown>;
}

export type TrainingJobStatus =
  | "queued"
  | "preparing"
  | "running"
  | "finished"
  | "failed"
  | "cancelled";

export interface JobStatus {
  job_id: string;
  status: TrainingJobStatus;
  logs: string;
  started_at?: string;
  finished_at?: string;
  adapter_path?: string;
  error?: string;
}

export interface TrainingJob {
  job_id: string;
  job_name: string;
  dataset_path: string;
  base_model: string;
  parameters: TrainingParams;
  status: TrainingJobStatus;
  started_at: string;
  finished_at?: string;
  container_id?: string;
  output_dir?: string;
  adapter_path?: string;
}

export interface AdapterInfo {
  adapter_id: string;
  adapter_path: string;
  base_model: string;
  created_at: string;
  training_params: Record<string, unknown>;
  is_active: boolean;
}

export interface AcademyStatus {
  enabled: boolean;
  components: {
    professor: boolean;
    dataset_curator: boolean;
    gpu_habitat: boolean;
    lessons_store: boolean;
    model_manager: boolean;
  };
  gpu: {
    available: boolean;
    enabled: boolean;
  };
  lessons: {
    total_lessons?: number;
  };
  jobs: {
    total: number;
    running: number;
    finished: number;
    failed: number;
  };
  config: {
    min_lessons: number;
    training_interval_hours: number;
    default_base_model: string;
  };
}

/**
 * Pobiera status Academy
 */
export async function getAcademyStatus(): Promise<AcademyStatus> {
  return apiFetch<AcademyStatus>("/api/v1/academy/status");
}

/**
 * Kuracja datasetu
 */
export async function curateDataset(params: {
  lessons_limit?: number;
  git_commits_limit?: number;
  include_task_history?: boolean;
  format?: "alpaca" | "sharegpt";
}): Promise<DatasetResponse> {
  return apiFetch<DatasetResponse>("/api/v1/academy/dataset", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/**
 * Start treningu
 */
export async function startTraining(params: TrainingParams): Promise<TrainingResponse> {
  return apiFetch<TrainingResponse>("/api/v1/academy/train", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/**
 * Pobiera status joba
 */
export async function getJobStatus(jobId: string): Promise<JobStatus> {
  return apiFetch<JobStatus>(`/api/v1/academy/train/${jobId}/status`);
}

/**
 * Lista wszystkich jobów
 */
export async function listJobs(params?: {
  limit?: number;
  status?: TrainingJobStatus;
}): Promise<{ count: number; jobs: TrainingJob[] }> {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", params.limit.toString());
  if (params?.status) query.set("status", params.status);

  const queryString = query.toString();
  const url = queryString ? `/api/v1/academy/jobs?${queryString}` : "/api/v1/academy/jobs";

  return apiFetch<{ count: number; jobs: TrainingJob[] }>(url);
}

/**
 * Lista adapterów
 */
export async function listAdapters(): Promise<AdapterInfo[]> {
  return apiFetch<AdapterInfo[]>("/api/v1/academy/adapters");
}

/**
 * Aktywacja adaptera
 */
export async function activateAdapter(params: {
  adapter_id: string;
  adapter_path: string;
  runtime_id?: string;
  model_id?: string;
  deploy_to_chat_runtime?: boolean;
}): Promise<{
  success: boolean;
  message: string;
  deployed?: boolean;
  runtime_id?: string;
  chat_model?: string;
}> {
  return apiFetch<{
    success: boolean;
    message: string;
    deployed?: boolean;
    runtime_id?: string;
    chat_model?: string;
  }>("/api/v1/academy/adapters/activate", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/**
 * Dezaktywacja adaptera (rollback do modelu bazowego)
 */
export async function deactivateAdapter(): Promise<{
  success: boolean;
  message: string;
  rolled_back?: boolean;
  runtime_id?: string;
  chat_model?: string;
}> {
  return apiFetch<{
    success: boolean;
    message: string;
    rolled_back?: boolean;
    runtime_id?: string;
    chat_model?: string;
  }>("/api/v1/academy/adapters/deactivate", {
    method: "POST",
  });
}

/**
 * Anuluj trening
 */
export async function cancelTraining(jobId: string): Promise<{ success: boolean; message: string }> {
  return apiFetch<{ success: boolean; message: string }>(`/api/v1/academy/train/${jobId}`, {
    method: "DELETE",
  });
}

// ==================== Academy v2: Upload & Scope ====================

export interface UploadFileInfo {
  id: string;
  name: string;
  size_bytes: number;
  mime: string;
  created_at: string;
  status: "validating" | "ready" | "failed";
  records_estimate: number;
  sha256: string;
  error?: string;
}

export interface DatasetScopeRequest {
  lessons_limit?: number;
  git_commits_limit?: number;
  include_task_history?: boolean;
  format?: "alpaca" | "sharegpt";
  include_lessons?: boolean;
  include_git?: boolean;
  upload_ids?: string[];
  conversion_file_ids?: string[] | null;
  quality_profile?: "strict" | "balanced" | "lenient";
}

export interface DatasetPreviewResponse {
  total_examples: number;
  by_source: Record<string, number>;
  removed_low_quality: number;
  warnings: string[];
  samples: Array<{
    instruction: string;
    input: string;
    output: string;
  }>;
}

export interface TrainableModelInfo {
  model_id: string;
  label: string;
  provider: string;
  trainable: boolean;
  reason_if_not_trainable?: string;
  recommended: boolean;
  installed_local: boolean;
  source_type: "local" | "cloud";
  cost_tier: "free" | "paid" | "unknown";
  priority_bucket: number;
  runtime_compatibility: Record<string, boolean>;
  recommended_runtime?: string | null;
  canonical_model_id?: string | null;
  aliases?: string[];
  coding_eligible?: boolean;
}

export interface RuntimeCatalogModelInfo {
  id: string;
  name: string;
  provider: string;
  runtime_id: string;
  source_type: "local-runtime" | "cloud-api";
  active: boolean;
  chat_compatible?: boolean;
  feedback_loop_ready?: boolean;
  feedback_loop_tier?: "primary" | "fallback" | "not_recommended";
  canonical_model_id?: string | null;
  aliases?: string[];
  coding_eligible?: boolean;
  owned_by_runtime?: string | null;
  ownership_status?: "native" | "foreign" | "unknown";
  compatible_runtimes?: string[];
}

export interface UnifiedModelCatalogResponse {
  active?: {
    runtime_id?: string | null;
    active_server?: string | null;
    active_model?: string | null;
  };
  runtimes: Array<{
    runtime_id: string;
    source_type: "local-runtime" | "cloud-api";
    configured: boolean;
    available: boolean;
    status: string;
    reason?: string | null;
    active: boolean;
    adapter_deploy_supported?: boolean;
    adapter_deploy_mode?: string;
  }>;
  all_models: RuntimeCatalogModelInfo[];
  chat_models: RuntimeCatalogModelInfo[];
  coding_models: RuntimeCatalogModelInfo[];
  runtime_servable_models: RuntimeCatalogModelInfo[];
  trainable_base_models: TrainableModelInfo[];
  inference_only_artifacts: RuntimeCatalogModelInfo[];
  trainable_models: TrainableModelInfo[];
  adapter_catalog: {
    all_adapters: Array<{
      adapter_id: string;
      adapter_path: string;
      base_model: string;
      canonical_base_model_id?: string;
      is_active: boolean;
      created_at?: string | null;
      compatible_runtimes?: string[];
    }>;
    by_runtime: Record<
      string,
      Array<{
        adapter_id: string;
        adapter_path: string;
        base_model: string;
        canonical_base_model_id?: string;
        is_active: boolean;
        created_at?: string | null;
        compatible_runtimes?: string[];
      }>
    >;
    by_runtime_model: Record<
      string,
      Record<
        string,
        Array<{
          adapter_id: string;
          adapter_path: string;
          base_model: string;
          canonical_base_model_id?: string;
          is_active: boolean;
          created_at?: string | null;
          compatible_runtimes?: string[];
        }>
      >
    >;
  };
  selector_flow: string[];
  model_audit?: {
    issues_count?: number;
    issues?: Array<{
      name?: string;
      path?: string;
      source?: string | null;
      reason?: string;
    }>;
  };
}

export interface DatasetConversionFileInfo {
  file_id: string;
  name: string;
  extension: string;
  size_bytes: number;
  created_at: string;
  category: "source" | "converted";
  source_file_id?: string;
  target_format?: "md" | "txt" | "json" | "jsonl" | "csv";
  selected_for_training?: boolean;
  status: string;
  error?: string;
}

export interface DatasetConversionListResponse {
  user_id: string;
  workspace_dir: string;
  source_files: DatasetConversionFileInfo[];
  converted_files: DatasetConversionFileInfo[];
}

export interface DatasetFilePreviewResponse {
  file_id: string;
  name: string;
  extension: string;
  preview: string;
  truncated: boolean;
}

type ParsedErrorBody = {
  message?: unknown;
  detail?: unknown;
  errors?: unknown;
};

function extractErrorMessageFromArray(items: unknown[]): string | null {
  const messages: string[] = [];
  for (const item of items) {
    if (typeof item === "string") {
      messages.push(item);
      continue;
    }
    if (item && typeof item === "object") {
      const obj = item as { msg?: unknown; message?: unknown; detail?: unknown };
      const nested =
        (typeof obj.msg === "string" && obj.msg) ||
        (typeof obj.message === "string" && obj.message) ||
        (typeof obj.detail === "string" && obj.detail);
      if (nested) messages.push(nested);
    }
  }
  return messages.length > 0 ? messages.join("; ") : null;
}

function extractErrorMessage(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return extractErrorMessageFromArray(value);
  if (value && typeof value === "object") {
    const obj = value as { message?: unknown; detail?: unknown };
    if (typeof obj?.message === "string") return obj.message;
    if (typeof obj?.detail === "string") return obj.detail;
  }
  return null;
}

function parseErrorBody(text: string): ParsedErrorBody | null {
  try {
    const parsed = JSON.parse(text) as unknown;
    if (!parsed || typeof parsed !== "object") return null;
    return parsed as ParsedErrorBody;
  } catch {
    return null;
  }
}

function resolveErrorMessage(body: ParsedErrorBody): string | null {
  return (
    extractErrorMessage(body.message) ||
    extractErrorMessage(body.detail) ||
    extractErrorMessage(body.errors)
  );
}

/**
 * Upload user dataset files to Academy
 */
async function parseUploadErrorMessage(response: Response): Promise<string> {
  const defaultError = "Upload failed";
  try {
    const text = await response.text();
    if (!text?.trim()) return defaultError;
    const body = parseErrorBody(text);
    if (!body) return text;
    return resolveErrorMessage(body) || text;
  } catch {
    return defaultError;
  }
}

const resolveMultipartApiBase = (): string => {
  const configuredBase = getApiBaseUrl();
  if (configuredBase) return configuredBase;
  const browserOrigin = globalThis.window?.location?.origin;
  if (browserOrigin) return browserOrigin;
  return "";
};

export async function uploadDatasetFiles(params: {
  files: FileList | File[];
  tag?: string;
  description?: string;
}): Promise<{
  success: boolean;
  uploaded: number;
  failed: number;
  files: UploadFileInfo[];
  errors: Array<{ name: string; error: string }>;
  message: string;
}> {
  const formData = new FormData();

  // Add files
  const filesArray = Array.from(params.files);
  filesArray.forEach((file) => {
    formData.append("files", file);
  });

  // Add metadata
  if (params.tag) {
    formData.append("tag", params.tag);
  }
  if (params.description) {
    formData.append("description", params.description);
  }

  // Use custom fetch for multipart/form-data (apiFetch sets application/json by default)
  const baseUrl = resolveMultipartApiBase();
  const uploadUrl = baseUrl ? `${baseUrl}/api/v1/academy/dataset/upload` : "/api/v1/academy/dataset/upload";
  const response = await fetch(uploadUrl, {
    method: "POST",
    body: formData,
    // Don't set Content-Type - browser will set it with boundary automatically
  });

  if (!response.ok) {
    throw new Error(await parseUploadErrorMessage(response));
  }

  return response.json();
}

/**
 * List uploaded dataset files
 */
export async function listDatasetUploads(): Promise<UploadFileInfo[]> {
  return apiFetch<UploadFileInfo[]>("/api/v1/academy/dataset/uploads");
}

/**
 * Delete an uploaded file
 */
export async function deleteDatasetUpload(fileId: string): Promise<{
  success: boolean;
  message: string;
}> {
  return apiFetch<{
    success: boolean;
    message: string;
  }>(`/api/v1/academy/dataset/uploads/${fileId}`, {
    method: "DELETE",
  });
}

/**
 * Preview dataset before curation
 */
export async function previewDataset(
  params: DatasetScopeRequest
): Promise<DatasetPreviewResponse> {
  return apiFetch<DatasetPreviewResponse>("/api/v1/academy/dataset/preview", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/**
 * Curate dataset with selected scope (v2)
 */
export async function curateDatasetV2(
  params: DatasetScopeRequest
): Promise<DatasetResponse> {
  return curateDataset(params);
}

function asArray<T>(value: T[] | undefined | null): T[] {
  return Array.isArray(value) ? value : [];
}

function resolveRuntimeServableModels(catalog: RuntimeOptionsPayload["model_catalog"]) {
  const runtimeServableModels = asArray(catalog?.runtime_servable_models);
  if (runtimeServableModels.length > 0) {
    return runtimeServableModels;
  }
  return asArray(catalog?.chat_models);
}

function resolveTrainableBaseModels(catalog: RuntimeOptionsPayload["model_catalog"]) {
  const trainableBaseModels = asArray(catalog?.trainable_base_models);
  if (trainableBaseModels.length > 0) {
    return trainableBaseModels;
  }
  return asArray(catalog?.trainable_models);
}

function resolveTrainableModels(catalog: RuntimeOptionsPayload["model_catalog"]) {
  const trainableModels = asArray(catalog?.trainable_models);
  if (trainableModels.length > 0) {
    return trainableModels;
  }
  return asArray(catalog?.trainable_base_models);
}

function resolveAdapterCatalog(
  payload: RuntimeOptionsPayload,
): UnifiedModelCatalogResponse["adapter_catalog"] {
  return {
    all_adapters: asArray(payload?.adapter_catalog?.all_adapters),
    by_runtime:
      payload?.adapter_catalog?.by_runtime &&
      typeof payload.adapter_catalog.by_runtime === "object"
        ? payload.adapter_catalog.by_runtime
        : {},
    by_runtime_model:
      payload?.adapter_catalog?.by_runtime_model &&
      typeof payload.adapter_catalog.by_runtime_model === "object"
        ? payload.adapter_catalog.by_runtime_model
        : {},
  };
}

function resolveSelectorFlow(payload: RuntimeOptionsPayload): string[] {
  return asArray(payload?.selector_flow).length > 0
    ? asArray(payload?.selector_flow)
    : ["server", "model", "adapter"];
}

type RuntimeOptionsPayload = {
  active?: {
    runtime_id?: string | null;
    active_server?: string | null;
    active_model?: string | null;
  };
  runtimes?: Array<{
    runtime_id: string;
    source_type: "local-runtime" | "cloud-api";
    configured: boolean;
    available: boolean;
    status: string;
    reason?: string | null;
    active: boolean;
    adapter_deploy_supported?: boolean;
    adapter_deploy_mode?: string;
  }>;
  model_catalog?: {
    all_models?: RuntimeCatalogModelInfo[];
    chat_models?: RuntimeCatalogModelInfo[];
    coding_models?: RuntimeCatalogModelInfo[];
    runtime_servable_models?: RuntimeCatalogModelInfo[];
    trainable_base_models?: TrainableModelInfo[];
    inference_only_artifacts?: RuntimeCatalogModelInfo[];
    trainable_models?: TrainableModelInfo[];
  };
  adapter_catalog?: UnifiedModelCatalogResponse["adapter_catalog"];
  selector_flow?: string[];
  model_audit?: UnifiedModelCatalogResponse["model_audit"];
};

export async function getUnifiedModelCatalog(): Promise<UnifiedModelCatalogResponse> {
  const payload = await apiFetch<RuntimeOptionsPayload>(
    "/api/v1/system/llm-runtime/options",
  );
  const catalog = payload?.model_catalog;
  return {
    active:
      payload?.active && typeof payload.active === "object"
        ? payload.active
        : undefined,
    runtimes: Array.isArray(payload?.runtimes) ? payload.runtimes : [],
    all_models: asArray(catalog?.all_models),
    chat_models: asArray(catalog?.chat_models),
    coding_models: asArray(catalog?.coding_models),
    runtime_servable_models: resolveRuntimeServableModels(catalog),
    trainable_base_models: resolveTrainableBaseModels(catalog),
    inference_only_artifacts: asArray(catalog?.inference_only_artifacts),
    trainable_models: resolveTrainableModels(catalog),
    adapter_catalog: resolveAdapterCatalog(payload),
    selector_flow: resolveSelectorFlow(payload),
    model_audit:
      payload?.model_audit && typeof payload.model_audit === "object"
        ? payload.model_audit
        : undefined,
  };
}

export async function listDatasetConversionFiles(): Promise<DatasetConversionListResponse> {
  return apiFetch<DatasetConversionListResponse>("/api/v1/academy/dataset/conversion/files");
}

export async function uploadDatasetConversionFiles(params: {
  files: FileList | File[];
}): Promise<{
  success: boolean;
  uploaded: number;
  failed: number;
  files: DatasetConversionFileInfo[];
  errors: Array<{ name: string; error: string }>;
  message: string;
}> {
  const formData = new FormData();
  const filesArray = Array.from(params.files);
  filesArray.forEach((file) => {
    formData.append("files", file);
  });

  const baseUrl = resolveMultipartApiBase();
  const uploadUrl = baseUrl
    ? `${baseUrl}/api/v1/academy/dataset/conversion/upload`
    : "/api/v1/academy/dataset/conversion/upload";
  const response = await fetch(uploadUrl, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await parseUploadErrorMessage(response));
  }

  return response.json();
}

export async function convertDatasetFile(params: {
  fileId: string;
  targetFormat: "md" | "txt" | "json" | "jsonl" | "csv";
}): Promise<{
  success: boolean;
  message: string;
  source_file: DatasetConversionFileInfo;
  converted_file?: DatasetConversionFileInfo;
}> {
  return apiFetch<{
    success: boolean;
    message: string;
    source_file: DatasetConversionFileInfo;
    converted_file?: DatasetConversionFileInfo;
  }>(`/api/v1/academy/dataset/conversion/files/${params.fileId}/convert`, {
    method: "POST",
    body: JSON.stringify({ target_format: params.targetFormat }),
  });
}

export async function previewDatasetFile(fileId: string): Promise<DatasetFilePreviewResponse> {
  return apiFetch<DatasetFilePreviewResponse>(`/api/v1/academy/dataset/conversion/files/${fileId}/preview`);
}

export async function setDatasetConversionTrainingSelection(params: {
  fileId: string;
  selectedForTraining: boolean;
}): Promise<DatasetConversionFileInfo> {
  return apiFetch<DatasetConversionFileInfo>(
    `/api/v1/academy/dataset/conversion/files/${params.fileId}/training-selection`,
    {
      method: "POST",
      body: JSON.stringify({ selected_for_training: params.selectedForTraining }),
    }
  );
}

// ==================== Academy v3: Self-Learning ====================

export type SelfLearningMode = "llm_finetune" | "rag_index";
export type SelfLearningSource = "docs" | "docs_en" | "docs_pl" | "docs_dev" | "code";
export type SelfLearningEmbeddingPolicy = "strict" | "allow_fallback";
export type SelfLearningRagChunkingMode = "plain" | "code_aware";
export type SelfLearningRagRetrievalMode = "vector" | "hybrid";
export type SelfLearningDatasetStrategy =
  | "reconstruct"
  | "qa_from_docs"
  | "repo_tasks_basic";
export type SelfLearningTaskMixPreset = "balanced" | "qa-heavy" | "repair-heavy";
export type SelfLearningStatus =
  | "pending"
  | "running"
  | "completed"
  | "completed_with_warnings"
  | "failed";

export interface SelfLearningLimits {
  max_file_size_kb: number;
  max_files: number;
  max_total_size_mb: number;
}

export interface SelfLearningLlmConfig {
  base_model?: string | null;
  runtime_id?: string | null;
  dataset_strategy?: SelfLearningDatasetStrategy;
  task_mix_preset?: SelfLearningTaskMixPreset;
  lora_rank: number;
  learning_rate: number;
  num_epochs: number;
  batch_size: number;
  max_seq_length: number;
}

export interface SelfLearningRagConfig {
  collection: string;
  category: string;
  chunk_text: boolean;
  chunking_mode?: SelfLearningRagChunkingMode;
  retrieval_mode?: SelfLearningRagRetrievalMode;
  embedding_profile_id?: string | null;
  embedding_policy?: SelfLearningEmbeddingPolicy;
}

export interface SelfLearningTrainableModelInfo {
  model_id: string;
  label: string;
  provider: string;
  recommended: boolean;
  runtime_compatibility: Record<string, boolean>;
  recommended_runtime?: string | null;
}

export interface SelfLearningEmbeddingProfile {
  profile_id: string;
  provider: string;
  model: string;
  dimension?: number | null;
  healthy: boolean;
  fallback_active: boolean;
  details: Record<string, unknown>;
}

export interface SelfLearningCapabilitiesResponse {
  trainable_models: SelfLearningTrainableModelInfo[];
  embedding_profiles: SelfLearningEmbeddingProfile[];
  default_base_model?: string | null;
  default_embedding_profile_id?: string | null;
}

export interface SelfLearningStartRequest {
  mode: SelfLearningMode;
  sources: SelfLearningSource[];
  limits: SelfLearningLimits;
  llm_config?: SelfLearningLlmConfig | null;
  rag_config?: SelfLearningRagConfig | null;
  dry_run: boolean;
}

export interface SelfLearningProgress {
  files_discovered: number;
  files_processed: number;
  chunks_created: number;
  records_created: number;
  indexed_vectors: number;
}

export interface SelfLearningRunStatus {
  run_id: string;
  status: SelfLearningStatus;
  mode: SelfLearningMode;
  sources: SelfLearningSource[];
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  progress: SelfLearningProgress;
  artifacts: Record<string, unknown>;
  logs: string[];
  error_message?: string | null;
}

export interface SelfLearningStartResponse {
  run_id: string;
  message: string;
}

export interface SelfLearningListResponse {
  runs: SelfLearningRunStatus[];
  count: number;
}

export interface SelfLearningDeleteResponse {
  message: string;
  count?: number;
}

export async function startSelfLearning(
  payload: SelfLearningStartRequest
): Promise<SelfLearningStartResponse> {
  return apiFetch<SelfLearningStartResponse>("/api/v1/academy/self-learning/start", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getSelfLearningRunStatus(
  runId: string
): Promise<SelfLearningRunStatus> {
  return apiFetch<SelfLearningRunStatus>(`/api/v1/academy/self-learning/${runId}/status`);
}

export async function listSelfLearningRuns(
  limit = 20
): Promise<SelfLearningListResponse> {
  return apiFetch<SelfLearningListResponse>(`/api/v1/academy/self-learning/list?limit=${limit}`);
}

export async function deleteSelfLearningRun(
  runId: string
): Promise<SelfLearningDeleteResponse> {
  return apiFetch<SelfLearningDeleteResponse>(`/api/v1/academy/self-learning/${runId}`, {
    method: "DELETE",
  });
}

export async function clearAllSelfLearningRuns(): Promise<SelfLearningDeleteResponse> {
  return apiFetch<SelfLearningDeleteResponse>("/api/v1/academy/self-learning/all", {
    method: "DELETE",
  });
}

export async function getSelfLearningCapabilities(): Promise<SelfLearningCapabilitiesResponse> {
  return apiFetch<SelfLearningCapabilitiesResponse>("/api/v1/academy/self-learning/capabilities");
}
