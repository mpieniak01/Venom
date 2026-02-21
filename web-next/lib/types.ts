import type { components } from "./generated/api-types";

type ApiSchemas = components["schemas"];

export type TaskStatus = ApiSchemas["TaskStatus"] | "LOST";

export type Task = ApiSchemas["VenomTask"];

export type Metrics = ApiSchemas["MetricsResponse"];

export type QueueStatus = ApiSchemas["QueueStatusResponse"];

export interface IntegrationStatus {
  name: string;
  status: "online" | "degraded" | "offline";
  details?: string;
}

export interface GraphSummary {
  nodes?: number;
  edges?: number;
  lastUpdated?: string;
  summary?: {
    nodes?: number;
    edges?: number;
    last_updated?: string;
  };
}

export type HistoryRequest = ApiSchemas["HistoryRequestSummary"];

export interface HistoryRequestDetail
  extends Omit<
    ApiSchemas["HistoryRequestDetail"],
    "steps" | "first_token" | "streaming" | "context_used" | "feedback"
  > {
  steps?: HistoryStep[];
  first_token?: {
    at?: string | null;
    elapsed_ms?: number | null;
    preview?: string | null;
  } | null;
  streaming?: {
    first_chunk_ms?: number | null;
    last_emit_ms?: number | null;
    chunk_count?: number | null;
  } | null;
  context_used?: {
    lessons?: string[];
    memory_entries?: string[];
  } | null;
  result?: string | null;
  feedback?: {
    rating: "up" | "down";
    comment?: string | null;
  } | null;
}

export interface HistoryStep {
  component?: string;
  action?: string;
  status?: string;
  timestamp?: string;
  details?: string;
}

export interface FlowStep {
  component: string;
  action: string;
  timestamp?: string;
  status?: string;
  details?: string;
  is_decision_gate?: boolean;
}

export interface FlowTrace {
  request_id: string;
  prompt: string;
  status: string;
  created_at: string;
  finished_at?: string | null;
  duration_seconds?: number | null;
  steps: FlowStep[];
  mermaid_diagram?: string;
}

export interface ServiceStatus {
  name: string;
  type?: string;
  status: "online" | "offline" | "degraded" | "unknown";
  detail?: string;
  latency_ms?: number;
  last_check?: string;
  is_critical?: boolean;
  error_message?: string | null;
  description?: string;
}

export interface LlmServerInfo {
  name: string;
  display_name: string;
  description?: string;
  endpoint?: string;
  provider?: string;
  status?: string;
  latency_ms?: number;
  last_check?: string | null;
  error_message?: string | null;
  supports: {
    start?: boolean;
    stop?: boolean;
    restart?: boolean;
    [key: string]: boolean | undefined;
  };
}

export interface ActiveLlmServerResponse {
  status: string;
  active_server?: string | null;
  active_endpoint?: string | null;
  active_model?: string | null;
  config_hash?: string | null;
  runtime_id?: string | null;
  last_models?: {
    ollama?: string;
    vllm?: string;
    previous_ollama?: string;
    previous_vllm?: string;
  };
  start_result?: {
    ok?: boolean;
    exit_code?: number | null;
    error?: string;
  } | null;
  stop_results?: Record<
    string,
    { ok?: boolean; exit_code?: number | null; error?: string }
  > | null;
}

export interface LlmActionResponse {
  status: string;
  action: string;
  message?: string;
  stdout?: string;
  stderr?: string;
  exit_code?: number | null;
}

export type TokenMetrics = ApiSchemas["TokenMetricsResponse"];

export type GitStatus = ApiSchemas["GitStatusResponse"];

// Model Domain v2: Source types
export type ModelSourceType = "local-runtime" | "cloud-api" | "integrator-catalog";

// Model Domain v2: Roles
export type ModelRole = "llm-engine" | "intent-embedding";

// Model Domain v2: Trainability status
export type ModelTrainabilityStatus = "trainable" | "not-trainable";

export interface ModelInfo {
  name: string;
  size_gb?: number;
  installed?: boolean;
  active?: boolean;
  source?: string;
  type?: string;
  quantization?: string;
  path?: string;
  provider?: string | null;
}

export interface ModelCatalogEntry {
  provider: string;
  model_name: string;
  display_name: string;
  size_gb?: number | null;
  runtime: string;
  tags?: string[];
  downloads?: number | null;
  likes?: number | null;
}

// Model Domain v2: Unified view model with domain classifications
export interface EnrichedModelInfo {
  // Base model information
  name: string;
  display_name?: string;
  size_gb?: number | null;
  provider: string;
  runtime?: string;

  // Installation/activation state
  installed?: boolean;
  active?: boolean;

  // Domain classifications (v2)
  source_type: ModelSourceType;
  model_role: ModelRole;
  academy_trainable: ModelTrainabilityStatus;
  trainability_reason?: string | null;

  // Additional metadata
  tags?: string[];
  downloads?: number | null;
  likes?: number | null;
  quantization?: string;
  path?: string;
}

export interface ModelCatalogResponse {
  success?: boolean;
  provider?: string;
  models: ModelCatalogEntry[];
  count: number;
  stale?: boolean;
  error?: string | null;
}

export interface ModelOperation {
  operation_id: string;
  model_name: string;
  operation_type: string;
  status: string;
  progress?: number;
  message?: string;
  started_at?: string;
  completed_at?: string | null;
  error?: string | null;
}

export interface ModelOperationsResponse {
  success?: boolean;
  operations: ModelOperation[];
  count: number;
}

export interface ModelsResponse {
  success?: boolean;
  models: ModelInfo[];
  count: number;
  active?: ActiveModelRuntime;
  providers?: Record<string, ModelInfo[]>;
}

export interface ActiveModelRuntime {
  provider?: string;
  model?: string;
  endpoint?: string;
  endpoint_host?: string | null;
  endpoint_port?: number | null;
  service_type?: string;
  mode?: string;
  label?: string;
  configured_models?: {
    local?: string | null;
    hybrid_local?: string | null;
    cloud?: string | null;
  };
  status?: string;
  last_success_at?: string;
  last_error_at?: string;
  error?: string;
}

export interface ModelsUsage {
  cpu_usage_percent?: number;
  gpu_usage_percent?: number;
  vram_usage_mb?: number;
  vram_total_mb?: number;
  memory_used_gb?: number;
  memory_total_gb?: number;
  memory_usage_percent?: number;
  disk_usage_gb?: number;
  disk_limit_gb?: number;
  disk_usage_percent?: number;
  disk_system_total_gb?: number;
  disk_system_used_gb?: number;
  disk_system_usage_percent?: number;
  disk_system_mount?: string;
  models_count?: number;
}

export interface ModelsUsageResponse {
  success?: boolean;
  usage?: ModelsUsage;
}

// Provider management types
export type ProviderType = "cloud_provider" | "catalog_integrator" | "local_runtime";
export type ConnectionStatus = "connected" | "degraded" | "offline" | "unknown";

export interface ProviderCapability {
  install: boolean;
  search: boolean;
  activate: boolean;
  inference: boolean;
  trainable: boolean;
}

export interface ProviderConnectionStatus {
  status: ConnectionStatus;
  reason_code?: string | null;
  message?: string | null;
  latency_ms?: number | null;
}

export interface ProviderInfo {
  name: string;
  display_name: string;
  provider_type: ProviderType;
  runtime: string;
  capabilities: ProviderCapability;
  connection_status: ProviderConnectionStatus;
  is_active: boolean;
  endpoint?: string | null;
}

export interface ProvidersResponse {
  status: string;
  providers: ProviderInfo[];
  active_provider?: string | null;
  count: number;
}

export interface ProviderStatusResponse {
  status: string;
  provider: string;
  connection_status: ProviderConnectionStatus;
}

export interface ProviderActivateRequest {
  provider: string;
  runtime?: string | null;
  model?: string | null;
}

export interface CostMode {
  enabled: boolean;
  provider: string;
}

export interface AutonomyLevel {
  current_level: number;
  current_level_name: string;
  color: string;
  color_name: string;
  description: string;
  permissions: Record<string, unknown>;
  risk_level: string;
}

export interface KnowledgeGraph {
  status?: string;
  mock?: boolean;
  view?: "overview" | "focus" | "full";
  elements: {
    nodes: Array<{ data: Record<string, unknown> }>;
    edges: Array<{ data: Record<string, unknown> }>;
  };
  stats?: {
    nodes: number;
    edges: number;
    source_nodes?: number;
    source_edges?: number;
    view?: "overview" | "focus" | "full";
    max_hops?: number;
    seed_id?: string | null;
  };
}

export type BrainGraphViewMode = "overview" | "focus" | "full";

export interface BrainFocusRequest {
  view: BrainGraphViewMode;
  seedId?: string;
  maxHops?: number;
  includeIsolates?: boolean;
  limitNodes?: number;
}

export interface Lesson {
  id?: string;
  title?: string;
  summary?: string;
  tags?: string[];
  created_at?: string;
  metadata?: Record<string, unknown>;
}

export interface LessonsResponse {
  status?: string;
  count: number;
  lessons: Lesson[];
}

export interface GraphScanResponse {
  status?: string;
  message?: string;
  stats?: Record<string, unknown>;
}

export interface LessonsStatsData {
  total_lessons: number;
  tag_distribution: Record<string, number>;
  [key: string]: unknown;
}

export interface LessonsStats {
  status?: string;
  stats?: LessonsStatsData;
}

export interface LearningLogEntry {
  task_id?: string;
  timestamp?: string;
  intent?: string;
  tool_required?: boolean;
  success?: boolean;
  need?: string;
  outcome?: string;
  error?: string;
  fast_path_hint?: string;
  tags?: string[];
}

export interface LearningLogsResponse {
  count: number;
  items: LearningLogEntry[];
}

export interface FeedbackResponse {
  status: string;
  feedback_saved: boolean;
  follow_up_task_id?: string | null;
}

export interface FeedbackLogEntry {
  task_id?: string;
  timestamp?: string;
  rating?: "up" | "down";
  comment?: string | null;
  prompt?: string;
  result?: string;
  intent?: string | null;
  tool_required?: boolean | null;
}

export interface FeedbackLogsResponse {
  count: number;
  items: FeedbackLogEntry[];
}

export interface HiddenPromptEntry {
  intent?: string;
  prompt?: string;
  approved_response?: string;
  prompt_hash?: string;
  score?: number;
  last_timestamp?: string;
  activated_by?: string;
  activated_at?: string;
  updated_at?: string;
}

export interface HiddenPromptsResponse {
  count: number;
  items: HiddenPromptEntry[];
}

export interface ActiveHiddenPromptsResponse {
  count: number;
  items: HiddenPromptEntry[];
}

export interface GraphFileInfoResponse {
  status?: string;
  file_info?: Record<string, unknown>;
}

export interface GraphImpactResponse {
  status?: string;
  impact?: Record<string, unknown>;
}

export interface RoadmapVision {
  title?: string;
  description?: string;
  status?: string;
  progress?: number;
}

export interface RoadmapTask {
  title?: string;
  description?: string;
  status?: string;
  priority?: number;
}

export interface RoadmapMilestone {
  title?: string;
  description?: string;
  status?: string;
  progress?: number;
  priority?: number;
  tasks?: RoadmapTask[];
}

export interface RoadmapKPIs {
  completion_rate?: number;
  milestones_completed?: number;
  milestones_total?: number;
  tasks_completed?: number;
  tasks_total?: number;
}

export interface RoadmapResponse {
  status?: string;
  vision?: RoadmapVision | null;
  milestones?: RoadmapMilestone[];
  kpis?: RoadmapKPIs;
  report?: string;
}

export interface RoadmapStatusResponse {
  status?: string;
  report?: string;
}

export interface CampaignResponse {
  status?: string;
  message?: string;
  result?: unknown;
}

// Generation Parameters Types
export interface GenerationParams {
  temperature?: number | null;
  max_tokens?: number | null;
  top_p?: number | null;
  top_k?: number | null;
  repeat_penalty?: number | null;
  [key: string]: number | string | boolean | null | undefined;
}

export interface GenerationParameterSchema {
  type: "float" | "int" | "bool" | "list" | "enum";
  default: number | string | boolean | null;
  min?: number;
  max?: number;
  desc?: string;
  options?: Array<number | string>;
}

export type GenerationSchema = Record<string, GenerationParameterSchema>;

// Benchmark types
export type BenchmarkStatus = "idle" | "running" | "completed" | "failed" | "pending";

export interface BenchmarkConfig {
  runtime: "vllm" | "ollama";
  models: string[];
  num_questions: number;
}

export interface BenchmarkLog {
  timestamp: string;
  message: string;
  level: "info" | "warning" | "error";
}

export type BenchmarkModelResult = ApiSchemas["BenchmarkModelResultResponse"];

export interface BenchmarkResult {
  benchmark_id: string;
  config: BenchmarkConfig;
  results: BenchmarkModelResult[];
  started_at: string;
  finished_at?: string;
  duration_seconds?: number;
}

export interface BenchmarkResponse {
  success: boolean;
  benchmark_id?: string;
  message?: string;
  result?: BenchmarkResult;
}

export type BenchmarkStartResponse = ApiSchemas["BenchmarkStartResponse"];
export type BenchmarkStatusResponse = ApiSchemas["BenchmarkStatusResponse"];

// Calendar types
export interface CalendarEvent {
  id?: string;
  summary: string;
  description?: string;
  start: string;
  end: string;
  location?: string;
  status?: string;
}

export interface EventsResponse {
  events: CalendarEvent[];
  total: number;
  time_min: string;
  time_max: string;
}

export interface CreateEventRequest {
  title: string;
  start_time: string;
  duration_minutes: number;
  description?: string;
}

export interface CreateEventResponse {
  status: string;
  message: string;
  event_id?: string;
  event_link?: string;
}

export interface ContextUsed {
  lessons?: string[];
  memory_entries?: string[];
  [key: string]: unknown; // Allow for future expansion
}
