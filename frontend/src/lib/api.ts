import type {
  AgentsDb, AssetGraphData, DashboardData, DatasetDetail, DatasetSummary, McpTool,
  ObservabilityData, Phase, PhaseKey, PhaseStagesResponse, PhaseState,
  RunStageResponse, TokenUsage, CopilotResponse, CopilotMemoryStatus, CopilotUploadResponse,
  DispatchTicketsResponse, ReplayDetectResponse, TestPrompt, LakeraScreenResult, HistoricalLeakEvidence,
  GuardrailProxyChatResult, LiveScanResponse, LiveVulnerabilityDemoResult,
} from "./types";

const TOKEN_KEY = "securing_ai_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`/api${path}`, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    window.location.href = "/login";
    throw new ApiError(401, "Session expired");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ token: string; username: string; role: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<{ username: string; role: string }>("/auth/me"),

  dashboard: () => request<DashboardData>("/dashboard"),
  assetGraph: () => request<AssetGraphData>("/asset-graph"),
  replayDetect: () => request<ReplayDetectResponse>("/recover/replay-detect", { method: "POST" }),
  historicalLeakEvidence: () => request<HistoricalLeakEvidence>("/recover/historical-leak-evidence"),
  requestApproval: (uc: PhaseKey, stageKey: string, actionType: string, summary: string) =>
    request<{ action_id: string; slack: { live: boolean; channel?: string; ts?: string; permalink?: string | null } }>(
      `/phases/${uc}/stages/${stageKey}/request-approval`,
      { method: "POST", body: JSON.stringify({ action_type: actionType, summary }) },
    ),
  approvalStatus: (actionId: string) =>
    request<{ resolved: boolean; decision?: string; approver?: string; status_note?: string; execution_result?: unknown }>(
      `/approval-status/${actionId}`,
    ),

  securityToolsTestPrompts: () => request<{ prompts: TestPrompt[] }>("/security-tools/test-prompts"),
  lakeraScreen: (prompt: string) =>
    request<LakeraScreenResult>("/security-tools/lakera-screen", { method: "POST", body: JSON.stringify({ prompt }) }),
  guardrailProxyChat: (prompt: string) =>
    request<GuardrailProxyChatResult>("/protect/guardrail-proxy/chat", { method: "POST", body: JSON.stringify({ prompt }) }),
  detectLiveScan: (tools: string[]) =>
    request<LiveScanResponse>("/detect/live-scan", { method: "POST", body: JSON.stringify({ tools }) }),
  detectLiveVulnerabilityDemo: (promptId: string, provider = "groq") =>
    request<LiveVulnerabilityDemoResult>("/detect/live-vulnerability-demo", {
      method: "POST",
      body: JSON.stringify({ prompt_id: promptId, provider }),
    }),

  phases: () => request<Phase[]>("/phases"),
  phaseStages: (uc: PhaseKey) => request<PhaseStagesResponse>(`/phases/${uc}/stages`),
  phaseState: (uc: PhaseKey) => request<PhaseState>(`/phases/${uc}/state`),
  setActiveStage: (uc: PhaseKey, index: number) =>
    request<{ active_stage: number }>(`/phases/${uc}/active-stage`, {
      method: "POST",
      body: JSON.stringify({ index }),
    }),
  runStage: (uc: PhaseKey, stageKey: string, dataSource: string) =>
    request<RunStageResponse>(`/phases/${uc}/stages/${stageKey}/run`, {
      method: "POST",
      body: JSON.stringify({ data_source: dataSource }),
    }),
  hitlDecision: (uc: PhaseKey, stageKey: string, decision: "approve" | "reject") =>
    request<{ approved: boolean }>(`/phases/${uc}/hitl/${stageKey}`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    }),
  dispatchTickets: (uc: PhaseKey, stageKey: string, summary: string, description: string) =>
    request<DispatchTicketsResponse>(`/phases/${uc}/stages/${stageKey}/dispatch-tickets`, {
      method: "POST",
      body: JSON.stringify({ summary, description, priority: "Medium" }),
    }),

  datasets: () => request<Record<string, DatasetSummary[]>>("/datasets"),
  dataset: (name: string, limit = 200, q?: string) =>
    request<DatasetDetail>(`/datasets/${name}?limit=${limit}${q ? `&q=${encodeURIComponent(q)}` : ""}`),
  downloadDataset: async (name: string): Promise<void> => {
    const token = getToken();
    const res = await fetch(`/api/datasets/${name}/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new ApiError(res.status, res.statusText);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  agents: () => request<AgentsDb>("/agents"),

  mcpTools: () => request<Record<string, McpTool[]>>("/mcp/tools"),

  settings: () =>
    request<{
      openai_api_key_masked: string;
      openai_api_key_set: boolean;
      langchain_tracing: boolean;
      langchain_api_key_set: boolean;
      langchain_project: string;
      llm_model_info: Record<string, { model: string; provider: string; status: string }> | null;
      model_name: string;
      reasoning_model: string;
      ollama_model: string;
      ollama_base_url: string;
      mcp_tools: { name: string; required_env_vars: string[] }[];
      github_target_repo: string;
      github_token_set: boolean;
      target_agent_url: string;
      target_agent_reachable: boolean;
      target_agent_disabled: boolean;
    }>("/settings"),
  reloadLiveData: () =>
    request<{ reloaded: boolean; fetch_errors: Record<string, string> | null }>("/live-data/reload", { method: "POST" }),
  saveSettings: (body: Record<string, unknown>) =>
    request<{ saved: boolean; reloaded: boolean; fetch_errors: Record<string, string> | null }>("/settings", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  changeCredentials: (body: { current_password: string; new_username?: string; new_password?: string }) =>
    request<{ saved: boolean; new_username?: string }>("/settings/credentials", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  tokenUsage: () => request<TokenUsage>("/token-usage"),

  observability: () => request<ObservabilityData>("/observability"),

  copilotStarters: () => request<string[]>("/copilot/starters"),
  copilotMessage: (message: string) =>
    request<CopilotResponse>("/copilot/message", { method: "POST", body: JSON.stringify({ message }) }),
  copilotMemory: () => request<CopilotMemoryStatus>("/copilot/memory"),
  copilotUpload: async (file: File): Promise<CopilotUploadResponse> => {
    const token = getToken();
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/copilot/upload", {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      body: form,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail ?? detail;
      } catch {
        /* ignore */
      }
      throw new ApiError(res.status, detail);
    }
    return res.json();
  },
  copilotClearUploads: () => request<{ cleared: boolean }>("/copilot/uploads", { method: "DELETE" }),
};

export { ApiError };
