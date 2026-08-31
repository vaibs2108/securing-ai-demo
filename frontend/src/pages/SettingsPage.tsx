import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../lib/api";
import { GlassCard, Badge } from "../components/ui";

export function SettingsPage() {
  const qc = useQueryClient();
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const { data: mcpTools } = useQuery({ queryKey: ["mcp-tools"], queryFn: api.mcpTools });

  const [apiKey, setApiKey] = useState("");
  const [tracing, setTracing] = useState(false);
  const [project, setProject] = useState("");
  const [modelName, setModelName] = useState("");
  const [reasoningModel, setReasoningModel] = useState("");
  const [ollamaModel, setOllamaModel] = useState("");
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState("");
  const [mcpCreds, setMcpCreds] = useState<Record<string, string>>({});
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [credError, setCredError] = useState<string | null>(null);
  const [credMsg, setCredMsg] = useState<string | null>(null);

  useEffect(() => {
    if (settings) {
      setTracing(settings.langchain_tracing);
      setProject(settings.langchain_project);
      setModelName(settings.model_name);
      setReasoningModel(settings.reasoning_model);
      setOllamaModel(settings.ollama_model);
      setOllamaBaseUrl(settings.ollama_base_url);
    }
  }, [settings]);

  const saveMut = useMutation({
    mutationFn: () => {
      const mcp_credentials = Object.fromEntries(Object.entries(mcpCreds).filter(([, v]) => v.trim() !== ""));
      return api.saveSettings({
        openai_api_key: apiKey || undefined,
        langchain_tracing: tracing,
        langchain_project: project,
        model_name: modelName || undefined,
        reasoning_model: reasoningModel || undefined,
        ollama_model: ollamaModel || undefined,
        ollama_base_url: ollamaBaseUrl || undefined,
        mcp_credentials: Object.keys(mcp_credentials).length > 0 ? mcp_credentials : undefined,
      });
    },
    onSuccess: () => {
      setSavedMsg("Configuration saved and applied. Connectors re-checked.");
      setApiKey("");
      setMcpCreds({});
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["mcp-tools"] });
      setTimeout(() => setSavedMsg(null), 4000);
    },
  });

  const credMut = useMutation({
    mutationFn: () =>
      api.changeCredentials({
        current_password: currentPassword,
        new_username: newUsername.trim() || undefined,
        new_password: newPassword.trim() || undefined,
      }),
    onSuccess: (res) => {
      setCredError(null);
      setCredMsg(
        res.new_username
          ? `Credentials updated. New username: ${res.new_username}. Use the new credentials next time you log in.`
          : "Password updated. Use the new password next time you log in."
      );
      setCurrentPassword("");
      setNewUsername("");
      setNewPassword("");
      setTimeout(() => setCredMsg(null), 6000);
    },
    onError: (err: unknown) => {
      setCredMsg(null);
      setCredError(err instanceof ApiError ? err.message : "Failed to update credentials.");
    },
  });

  return (
    <div>
      <div className="hero-banner">
        <div className="hero-title">⚙️ System Settings</div>
        <div className="hero-subtitle">Configure AI routing engines and enterprise vendor credentials</div>
      </div>

      <div className="grid-2">
        <GlassCard accent="var(--accent-blue)">
          <div className="section-title">🔑 Core API Configuration</div>
          <label className="field-label">OpenAI API Key</label>
          <input type="password" placeholder={settings?.openai_api_key_set ? `Currently set (${settings.openai_api_key_masked})` : "sk-…"} value={apiKey} onChange={(e) => setApiKey(e.target.value)} style={{ marginBottom: 14 }} />
          <label className="radio-option" style={{ marginBottom: 14 }}>
            <input type="checkbox" checked={tracing} onChange={(e) => setTracing(e.target.checked)} /> Enable LangSmith Tracing
          </label>
          <label className="field-label">LangSmith Project</label>
          <input type="text" value={project} onChange={(e) => setProject(e.target.value)} style={{ marginBottom: 16 }} />
        </GlassCard>

        <GlassCard accent="var(--accent-green)">
          <div className="section-title">🤖 LLM Routing Framework</div>
          <p className="muted" style={{ fontSize: "0.78rem", marginBottom: 12 }}>
            Tier 1 (Primary) handles Identify/Protect. Tier 3 (Reasoning) routes Detect/Respond. Changes apply
            immediately on save — no restart needed.
          </p>

          <div className="flex-row" style={{ justifyContent: "space-between", marginBottom: 4 }}>
            <label className="field-label" style={{ marginBottom: 0 }}>Tier 1 — Primary model</label>
            {settings?.llm_model_info && (
              <span className={`badge ${settings.llm_model_info.primary.status === "available" ? "badge-green" : "badge-amber"}`}>
                {settings.llm_model_info.primary.status === "available" ? "🟢 Available" : "🟡 " + settings.llm_model_info.primary.status}
              </span>
            )}
          </div>
          <input type="text" value={modelName} onChange={(e) => setModelName(e.target.value)} placeholder="gpt-4o-mini" style={{ marginBottom: 14 }} />

          <div className="flex-row" style={{ justifyContent: "space-between", marginBottom: 4 }}>
            <label className="field-label" style={{ marginBottom: 0 }}>Tier 3 — Reasoning model</label>
            {settings?.llm_model_info && (
              <span className={`badge ${settings.llm_model_info.reasoning.status === "available" ? "badge-green" : "badge-amber"}`}>
                {settings.llm_model_info.reasoning.status === "available" ? "🟢 Available" : "🟡 " + settings.llm_model_info.reasoning.status}
              </span>
            )}
          </div>
          <input type="text" value={reasoningModel} onChange={(e) => setReasoningModel(e.target.value)} placeholder="gpt-4o-mini" style={{ marginBottom: 6 }} />
          <p className="muted" style={{ fontSize: "0.72rem", marginBottom: 14 }}>
            <code>gpt-4o</code> is intentionally disabled for demo cost control — entering it will resolve to
            <code> gpt-4o-mini</code> instead of actually calling GPT-4o.
          </p>

          <div className="flex-row" style={{ justifyContent: "space-between", marginBottom: 4 }}>
            <label className="field-label" style={{ marginBottom: 0 }}>Tier 2 — Local (Ollama) model</label>
            {settings?.llm_model_info && (
              <span className={`badge ${settings.llm_model_info.secondary.status === "available" ? "badge-green" : "badge-amber"}`}>
                {settings.llm_model_info.secondary.status === "available" ? "🟢 Available" : "🟡 " + settings.llm_model_info.secondary.status}
              </span>
            )}
          </div>
          <input type="text" value={ollamaModel} onChange={(e) => setOllamaModel(e.target.value)} placeholder="llama3.1:8b" style={{ marginBottom: 8 }} />
          <label className="field-label">Ollama base URL</label>
          <input type="text" value={ollamaBaseUrl} onChange={(e) => setOllamaBaseUrl(e.target.value)} placeholder="http://localhost:11434" />
        </GlassCard>
      </div>

      <div className="section-title" style={{ marginTop: 24 }}>🔌 MCP Integrations</div>
      <p className="muted" style={{ fontSize: "0.82rem", marginBottom: 16 }}>
        Only tools with a real, specifically-named product and a genuinely wireable integration are listed —
        no generic placeholders. <strong>Hosted API</strong> tools take a vendor API key. <strong>Self-hosted
        runner</strong> tools (Garak, PyRIT) have no public vendor API — you run them yourself and give us the
        URL of your own runner.
      </p>
      {mcpTools && Object.entries(mcpTools).map(([category, tools]) => (
        <div key={category} style={{ marginBottom: 20 }}>
          <div className="muted" style={{ fontSize: "0.8rem", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.05em" }}>🏷️ {category}</div>
          <div className="grid-2">
            {tools.map((t) => (
              <GlassCard key={t.name} accent={t.live ? "var(--accent-blue)" : undefined}>
                <div className="flex-row" style={{ justifyContent: "space-between" }}>
                  <strong>{t.display_name}</strong>
                  <span className={`badge ${t.live ? "badge-green" : "badge-blue"}`}>{t.live ? "🟢 Connected (Live)" : "🔵 Mock Fallback"}</span>
                </div>
                <div className="muted" style={{ fontSize: "0.8rem", marginTop: 6 }}>{t.description}</div>
                <div style={{ marginTop: 8 }}>
                  <Badge variant={t.integration_type === "hosted_api" ? "purple" : "amber"}>
                    {t.integration_type === "hosted_api" ? "Hosted API" : "Self-hosted runner"}
                  </Badge>
                </div>
                <div className="muted" style={{ fontSize: "0.75rem", marginTop: 8 }}>Capabilities: {t.capabilities.join(", ")}</div>

                <div style={{ marginTop: 12 }}>
                  {t.required_env_vars.map((v) => {
                    const isSecret = v.includes("KEY") || v.includes("TOKEN") || v.includes("PASSWORD");
                    const masked = t.env_var_values_masked[v];
                    return (
                      <div key={v} style={{ marginBottom: 8 }}>
                        <label className="field-label">{v}</label>
                        <input
                          type={isSecret ? "password" : "text"}
                          placeholder={masked ? `Currently set (${masked})` : `e.g. ${isSecret ? "your api key" : "value"}`}
                          value={mcpCreds[v] ?? ""}
                          onChange={(e) => setMcpCreds((prev) => ({ ...prev, [v]: e.target.value }))}
                        />
                      </div>
                    );
                  })}
                </div>
                {t.docs_url && (
                  <a href={t.docs_url} target="_blank" rel="noreferrer" style={{ fontSize: "0.72rem", color: "var(--accent-blue)" }}>
                    Setup docs →
                  </a>
                )}
              </GlassCard>
            ))}
          </div>
        </div>
      ))}

      <button className="btn" style={{ marginTop: 8 }} onClick={() => saveMut.mutate()} disabled={saveMut.isPending}>
        💾 Apply Settings &amp; Reconnect
      </button>
      {savedMsg && <div className="badge badge-green" style={{ marginTop: 10, marginLeft: 10 }}>{savedMsg}</div>}

      <div className="section-title" style={{ marginTop: 32 }}>🔐 Login Credentials</div>
      <p className="muted" style={{ fontSize: "0.82rem", marginBottom: 16 }}>
        Change the username/password used to log into this app. Stored the same way as everything else on this
        page — no server file access required, so this works on a deployed instance too.
      </p>
      <div className="grid-2">
        <GlassCard accent="var(--accent-purple)">
          <label className="field-label">Current password</label>
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            placeholder="Required to confirm this change"
            style={{ marginBottom: 14 }}
          />
          <label className="field-label">New username</label>
          <input
            type="text"
            value={newUsername}
            onChange={(e) => setNewUsername(e.target.value)}
            placeholder="Leave blank to keep current username"
            style={{ marginBottom: 14 }}
          />
          <label className="field-label">New password</label>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="Leave blank to keep current password (min 6 chars)"
            style={{ marginBottom: 16 }}
          />
          <button
            className="btn"
            onClick={() => credMut.mutate()}
            disabled={credMut.isPending || !currentPassword || (!newUsername.trim() && !newPassword.trim())}
          >
            🔑 Update Credentials
          </button>
          {credMsg && <div className="badge badge-green" style={{ marginTop: 10, marginLeft: 10 }}>{credMsg}</div>}
          {credError && <div className="badge badge-red" style={{ marginTop: 10, marginLeft: 10 }}>{credError}</div>}
        </GlassCard>
      </div>
    </div>
  );
}
