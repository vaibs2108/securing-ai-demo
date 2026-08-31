export type PhaseKey = "identify" | "protect" | "detect" | "respond" | "recover";

export interface PhaseOverview {
  title: string;
  subtitle: string;
  goal: string;
  frameworks: string[];
  color: string;
}

export interface Phase {
  key: PhaseKey;
  label: string;
  color: string;
  overview: PhaseOverview;
  stage_count: number;
}

export interface StageIO {
  input_key?: string;
  input_name?: string;
  input_desc?: string;
  output_key?: string;
  output_name?: string;
  output_desc?: string;
}

export interface AgentInfo {
  agent: string;
  analysis: string;
  output: string;
}

export interface ChartSpec {
  dataset: string;
  column: string;
  type: "bar" | "donut";
  title: string;
  value_column?: string;
}

export interface HitlSpec {
  dataset: string;
  id_column: string;
  label_template: string;
  match_column: string;
  match_value: unknown;
}

export interface StageUiConfig {
  filter_column: string;
  filter_options: string[];
  chart?: ChartSpec;
  hitl?: HitlSpec | null;
}

export interface Stage {
  index: number;
  key: string;
  name: string;
  icon: string;
  description: string;
  agent: string;
  io: StageIO;
  agent_info: AgentInfo;
  ui_config: StageUiConfig;
  previous_stage_output: string;
  input_row_count: number;
  input_columns: string[];
  dataset_summary: string;
}

export interface PhaseStagesResponse {
  overview: PhaseOverview;
  color: string;
  stages: Stage[];
}

export interface PhaseState {
  active_stage: number;
  completed_stages: number[];
  stage_outputs: Record<string, AgentOutcome>;
  hitl_approved: Record<string, boolean>;
}

export interface Finding {
  id: string;
  title: string;
  severity: string;
  description: string;
  evidence: string;
  recommendation: string;
}

export interface AgentOutcome {
  agent_name: string;
  use_case: string;
  stage: string;
  data_source: string;
  ai_confidence: number;
  step_by_step_execution: string[];
  output_generated: string;
  passed_to_next_stage: string;
  summary: string;
  findings: Finding[];
  kpi_deltas: Record<string, number>;
  recommendations: string[];
  timestamp: number;
  error?: string;
}

export interface ChartData {
  labels: string[];
  values: number[];
  title: string;
  type: "bar" | "donut";
}

export interface HitlCandidate {
  id: string;
  label: string;
}

export interface RunStageResponse {
  outcome: AgentOutcome;
  hitl_required: boolean;
  hitl_candidates: HitlCandidate[];
  completed_stages: number[];
  output_preview: {
    name: string;
    row_count: number;
    columns: string[];
    records: Record<string, unknown>[];
  };
  chart: ChartData | null;
  live_mcp_used: string[];
}

export interface TicketResult {
  live: boolean;
  success: boolean;
  ticket_ref?: string;
  url?: string | null;
  error?: string;
}

export interface DispatchTicketsResponse {
  jira: TicketResult;
  servicenow: TicketResult;
}

export interface DashboardData {
  kpis: Record<string, number>;
  posture_index: number;
  gauges: { phase: string; label: string; score: number; color: string }[];
  operational: { label: string; value: number; color: string }[];
  trend: Record<string, { day: string; score: number }[]>;
  blast_radius: Record<string, number>;
  recent_operations: AuditLogEntry[];
}

export interface AuditLogEntry {
  timestamp: string;
  action: string;
  username: string;
  status: string;
  target: string;
  details: string;
}

export interface AgentEntry {
  name: string;
  stage: string;
  role: string;
  mitre_ref: string;
}

export interface AgentsDb {
  [phase: string]: {
    color: string;
    framework: string;
    agents: AgentEntry[];
  };
}

export interface DatasetSummary {
  name: string;
  row_count: number;
  column_count: number;
}

export interface DatasetDetail {
  name: string;
  row_count: number;
  columns: string[];
  records: Record<string, unknown>[];
}

export interface McpTool {
  name: string;
  display_name: string;
  category: string;
  description: string;
  capabilities: string[];
  endpoints: Record<string, string>;
  required_env_vars: string[];
  env_var_values_masked: Record<string, string>;
  integration_type: "hosted_api" | "self_hosted_runner";
  docs_url: string;
  live: boolean;
  status: string;
}

export interface TokenUsage {
  total_tokens: number;
  total_cost_usd: number;
  call_count: number;
  avg_duration_ms: number;
  by_model: Record<string, number>;
  by_use_case: Record<string, number>;
  by_stage: Record<string, number>;
  timeline: Record<string, unknown>[];
}

export interface ObservabilityData {
  traces: {
    id: string; timestamp: string; agent: string; status: string;
    duration_ms: number; langsmith_synced: boolean; error: string | null;
  }[];
  hallucination_reports: Record<string, {
    total_citations: number;
    flags: { citation: string; source_checked: string; finding: string; severity: string }[];
    hallucination_rate: number;
    validated_at: string;
  }>;
  health_summary: {
    total_llm_calls: number;
    success_rate: number;
    avg_latency_ms: number;
    p95_latency_ms: number;
    total_tokens: number;
    guardrail_events_count: number;
    hitl_approval_ratio: number;
    total_hitl_decisions: number;
    active_since: string;
  };
  guardrail_events: { timestamp: string; type: string; action: string; context: string }[];
  audit_log: AuditLogEntry[];
}

export interface CopilotSource {
  text: string;
  score: number;
  collection: string;
  source?: string | null;
}

export interface CopilotResponse {
  answer: string;
  sources: CopilotSource[];
}

export interface UploadedDoc {
  filename: string;
  chunks: number;
  chars: number;
  uploaded_at: number;
}

export interface CopilotMemoryStatus {
  ready: boolean;
  building: boolean;
  error: string | null;
  dataset_status: Record<string, string>;
  dataset_vector_counts: Record<string, number>;
  total_dataset_vectors: number;
  upload_vector_count: number;
  uploads: UploadedDoc[];
}

export interface CopilotUploadResponse {
  filename: string;
  chunks: number;
  chars: number;
}
