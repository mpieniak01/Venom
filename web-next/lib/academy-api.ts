/**
 * Academy API Client
 *
 * API client dla endpointów THE_ACADEMY - trenowanie modeli.
 */

import { apiFetch } from "./api-client";

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
}): Promise<{ success: boolean; message: string }> {
  return apiFetch<{ success: boolean; message: string }>("/api/v1/academy/adapters/activate", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/**
 * Dezaktywacja adaptera (rollback do modelu bazowego)
 */
export async function deactivateAdapter(): Promise<{ success: boolean; message: string }> {
  return apiFetch<{ success: boolean; message: string }>("/api/v1/academy/adapters/deactivate", {
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
}

/**
 * Upload plików użytkownika do Academy
 */
export async function uploadDatasetFiles(params: {
  files: FileList | File[];
  tag?: string;
  description?: string;
}): Promise<{
  success: boolean;
  uploaded: number;
  files: UploadFileInfo[];
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
  const baseUrl = typeof window !== "undefined" 
    ? window.location.origin 
    : "http://localhost:8000";
  
  const response = await fetch(`${baseUrl}/api/v1/academy/dataset/upload`, {
    method: "POST",
    body: formData,
    // Don't set Content-Type - browser will set it with boundary automatically
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || "Upload failed");
  }

  return response.json();
}

/**
 * Lista uploadowanych plików
 */
export async function listDatasetUploads(): Promise<UploadFileInfo[]> {
  return apiFetch<UploadFileInfo[]>("/api/v1/academy/dataset/uploads");
}

/**
 * Usuń uploadowany plik
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
 * Preview datasetu przed curate
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
 * Kuracja datasetu z wybranym scope (v2)
 */
export async function curateDatasetV2(
  params: DatasetScopeRequest
): Promise<DatasetResponse> {
  return apiFetch<DatasetResponse>("/api/v1/academy/dataset", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/**
 * Lista modeli trenowalnych
 */
export async function getTrainableModels(): Promise<TrainableModelInfo[]> {
  return apiFetch<TrainableModelInfo[]>("/api/v1/academy/models/trainable");
}
