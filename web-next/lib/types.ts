export type TaskStatus = "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED" | "LOST";

export interface Task {
  task_id?: string;
  id?: string;
  content: string;
  status: TaskStatus;
  result?: string | null;
  logs?: string[];
  context_history?: Record<string, unknown>;
  llm_provider?: string | null;
  llm_model?: string | null;
  llm_endpoint?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface Metrics {
  tasks?: {
    created?: number;
    success_rate?: number;
  };
  uptime_seconds?: number;
  network?: {
    total_bytes?: number;
  };
}

export interface QueueStatus {
  active: number;
  pending: number;
  limit?: number;
  paused?: boolean;
}

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

export interface HistoryRequest {
  request_id: string;
  prompt: string;
  status: TaskStatus;
  model?: string;
  llm_provider?: string | null;
  llm_model?: string | null;
  llm_endpoint?: string | null;
  created_at: string;
  finished_at?: string | null;
  duration_seconds?: number | null;
}

export interface HistoryRequestDetail extends HistoryRequest {
  steps?: HistoryStep[];
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
  status: "healthy" | "degraded" | "down" | string;
  detail?: string;
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

export interface LlmActionResponse {
  status: string;
  action: string;
  message?: string;
  stdout?: string;
  stderr?: string;
  exit_code?: number | null;
}

export interface TokenMetrics {
  total_tokens?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  cached_tokens?: number;
  session_cost_usd?: number;
}

export interface GitStatus {
  branch?: string;
  changes?: string;
  dirty?: boolean;
  status?: string;
}

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
  models_count?: number;
}

export interface ModelsUsageResponse {
  success?: boolean;
  usage?: ModelsUsage;
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
  elements: {
    nodes: Array<{ data: Record<string, unknown> }>;
    edges: Array<{ data: Record<string, unknown> }>;
  };
  stats?: {
    nodes: number;
    edges: number;
  };
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

export interface LessonsStats {
  status?: string;
  stats?: Record<string, unknown>;
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

// Benchmark types
export type BenchmarkStatus = "idle" | "running" | "completed" | "failed";

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

export interface BenchmarkModelResult {
  model_name: string;
  avg_response_time_ms: number;
  tokens_per_sec: number;
  max_vram_mb: number;
  status: "success" | "oom" | "error";
  error_message?: string;
}

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
