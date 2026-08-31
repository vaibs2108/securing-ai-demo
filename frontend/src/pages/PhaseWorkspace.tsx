import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { PhaseKey, RunStageResponse, Stage, TicketResult } from "../lib/types";
import { TopTabs } from "../components/TopTabs";
import { Chart } from "../components/Chart";
import { Badge, DataTable, GlassCard, LoadingBlock, severityVariant } from "../components/ui";
import { useTheme } from "../context/ThemeContext";
import { readableAccent } from "../lib/color";

const DATA_SOURCE_OPTIONS: { value: string; label: string }[] = [
  { value: "mcp", label: "API/MCP Live Tools (Priority 1)" },
  { value: "upload", label: "File Upload Ingestion (Priority 2)" },
  { value: "synthetic", label: "Synthetic Data Engine (Priority 3)" },
];

const FRAMEWORK_VARIANT = (fw: string): string => {
  const f = fw.toLowerCase();
  if (f.includes("nist")) return "blue";
  if (f.includes("mitre") || f.includes("atlas")) return "red";
  if (f.includes("cis")) return "amber";
  if (f.includes("owasp")) return "purple";
  return "green";
};

interface WorkflowState {
  status: "APPROVAL QUEUE" | "IMPLEMENTATION TRACKING" | "COMPLETED & VERIFIED";
  jira?: TicketResult;
  servicenow?: TicketResult;
}

export function PhaseWorkspace() {
  const { uc } = useParams<{ uc: PhaseKey }>();
  const phase = (uc ?? "identify") as PhaseKey;
  const qc = useQueryClient();
  const { theme } = useTheme();

  const stagesQ = useQuery({ queryKey: ["phase-stages", phase], queryFn: () => api.phaseStages(phase) });
  const stateQ = useQuery({ queryKey: ["phase-state", phase], queryFn: () => api.phaseState(phase) });

  const [dataSource, setDataSource] = useState<Record<string, string>>({});
  const [categoryFilter, setCategoryFilter] = useState<Record<string, string>>({});
  const [previewOpen, setPreviewOpen] = useState<Record<string, boolean>>({});
  const [runResult, setRunResult] = useState<Record<string, RunStageResponse>>({});
  const [resultTab, setResultTab] = useState<"analysis" | "output" | "workflow">("analysis");
  const [workflow, setWorkflow] = useState<Record<string, WorkflowState>>({});

  useEffect(() => {
    setResultTab("analysis");
  }, [stateQ.data?.active_stage, phase]);

  const activeIndex = stateQ.data?.active_stage ?? 0;
  const completedStages = stateQ.data?.completed_stages ?? [];
  const stages = stagesQ.data?.stages ?? [];
  const activeStage: Stage | undefined = stages[activeIndex];

  const previewQ = useQuery({
    queryKey: ["dataset-preview", activeStage?.io.input_key],
    queryFn: () => api.dataset(activeStage!.io.input_key!, 100),
    enabled: !!activeStage?.io.input_key && !!previewOpen[activeStage?.key ?? ""],
  });

  const setActiveStageMut = useMutation({
    mutationFn: (index: number) => api.setActiveStage(phase, index),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["phase-state", phase] }),
  });

  const runMut = useMutation({
    mutationFn: (stageKey: string) => api.runStage(phase, stageKey, dataSource[stageKey] ?? "synthetic"),
    onSuccess: (res, stageKey) => {
      setRunResult((prev) => ({ ...prev, [stageKey]: res }));
      qc.invalidateQueries({ queryKey: ["phase-state", phase] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      setResultTab("analysis");
    },
  });

  const hitlMut = useMutation({
    mutationFn: ({ stageKey, decision }: { stageKey: string; decision: "approve" | "reject" }) =>
      api.hitlDecision(phase, stageKey, decision),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["phase-state", phase] }),
  });

  const result: RunStageResponse | undefined = activeStage ? runResult[activeStage.key] : undefined;
  const priorOutcome = activeStage ? stateQ.data?.stage_outputs[activeStage.key] : undefined;
  const outcome = result?.outcome ?? priorOutcome;
  const hitlApprovedMap = stateQ.data?.hitl_approved ?? {};
  const isFinalStage = activeStage ? activeStage.index === stages.length - 1 : false;

  const previewRecords = useMemo(() => {
    if (!previewQ.data || !activeStage) return [];
    const col = activeStage.ui_config.filter_column;
    const val = categoryFilter[activeStage.key];
    if (!val || val === "ALL") return previewQ.data.records;
    return previewQ.data.records.filter((r) => String(r[col]) === val);
  }, [previewQ.data, categoryFilter, activeStage]);

  const dispatchMut = useMutation({
    mutationFn: ({ stageKey, summary, description }: { stageKey: string; summary: string; description: string }) =>
      api.dispatchTickets(phase, stageKey, summary, description),
    onSuccess: (res, { stageKey }) => {
      setWorkflow((prev) => ({
        ...prev,
        [stageKey]: { status: "IMPLEMENTATION TRACKING", jira: res.jira, servicenow: res.servicenow },
      }));
    },
  });

  function closeWorkflow(stageKey: string) {
    setWorkflow((prev) => {
      const cur = prev[stageKey];
      if (!cur) return prev;
      return { ...prev, [stageKey]: { ...cur, status: "COMPLETED & VERIFIED" } };
    });
  }

  if (stagesQ.isLoading || !stagesQ.data) return <><TopTabs /><LoadingBlock label={`Loading ${phase}…`} /></>;

  const overview = stagesQ.data.overview;
  const color = stagesQ.data.color;
  // color comes from the backend as a raw dark-tuned hex (e.g. Protect's
  // neon "#00ff88") — fine as a border/background accent, unreadable as
  // text on the light theme's near-white background. textColor is the
  // legible variant for every text usage below; color itself stays raw for
  // borders/backgrounds/fills, which read fine either way.
  const textColor = readableAccent(color, theme);

  return (
    <div>
      <TopTabs />
      <h1 style={{ color: textColor, marginBottom: 8, fontSize: "1.6rem" }}>{overview.title}</h1>

      <div className="overview-card" style={{ borderTop: `3px solid ${color}` }}>
        <div className="top-row">
          <div>
            <div className="title">{overview.title}</div>
            <div className="subtitle" style={{ color: textColor }}>{overview.subtitle}</div>
          </div>
          <div className="badges">
            {overview.frameworks.map((f) => <Badge key={f} variant={FRAMEWORK_VARIANT(f)}>{f}</Badge>)}
          </div>
        </div>
        <div className="goal"><strong style={{ color: "var(--text-heading)" }}>🎯 STRATEGIC GOAL STATEMENT:</strong> {overview.goal}</div>
      </div>

      <div className="stage-progress">
        {stages.map((s, i) => {
          const isDone = completedStages.includes(i);
          const isActive = i === activeIndex;
          return (
            <span key={s.key}>
              <span
                className={`stage-pill${isDone ? " completed" : ""}`}
                style={isActive ? { borderColor: color, background: `${color}26`, color: "var(--text-heading)", boxShadow: `0 4px 16px ${color}33` } : undefined}
                onClick={() => setActiveStageMut.mutate(i)}
              >
                {isDone ? "✓" : s.icon} {s.name}
              </span>
              {i < stages.length - 1 && <span className="stage-connector" style={{ background: isDone ? "var(--rag-green)" : "var(--border-glass)" }} />}
            </span>
          );
        })}
      </div>

      <hr style={{ border: 0, borderTop: "1px solid var(--border-glass)", margin: "20px 0" }} />

      {activeStage && (
        <>
          <div className="stage-header">
            <div className="stage-badge" style={{ background: `${color}33`, borderColor: color, color: textColor }}>{activeIndex + 1}</div>
            <div>
              <div className="name">{activeStage.name}<span className="of">Stage {activeIndex + 1} of {stages.length}</span></div>
              <div className="desc">{activeStage.description}</div>
            </div>
          </div>

          {/* 3-column input panel */}
          <GlassCard style={{ padding: 24 }}>
            <div className="grid-3">
              <div>
                <div className="section-title" style={{ color: textColor }}>📥 Column 1: Ingestion &amp; Filtering</div>
                <div style={{ background: "rgba(var(--overlay-rgb), 0.03)", border: "1px solid var(--border-glass)", borderLeft: `3px solid ${color}`, borderRadius: 8, padding: "12px 14px", marginBottom: 12 }}>
                  <div style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.05em", color: textColor, fontWeight: 700, marginBottom: 4 }}>
                    {activeIndex === 0 ? "📁 Target Ingested Dataset" : "🔄 Input Payload (From Previous Stage)"}
                  </div>
                  <div style={{ fontWeight: 700, marginBottom: 6, color: "var(--text-heading)" }}>{activeStage.io.input_name}</div>
                  <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginBottom: 10 }}>{activeStage.io.input_desc}</div>
                  <div style={{ display: "flex", gap: 12, fontSize: "0.75rem", fontFamily: "JetBrains Mono, monospace", background: "rgba(var(--overlay-rgb), 0.05)", padding: "6px 8px", borderRadius: 4 }}>
                    <span>📊 {activeStage.input_row_count.toLocaleString()} rows</span>
                    <span>🎛️ {activeStage.input_columns.length} columns</span>
                  </div>
                </div>

                {activeIndex > 0 && activeStage.previous_stage_output && (
                  <div style={{ background: "rgba(0,255,136,0.04)", border: "1px solid rgba(0,255,136,0.12)", borderRadius: 8, padding: 12, marginBottom: 12, fontSize: "0.8rem" }}>
                    <div style={{ color: "var(--rag-green)", fontWeight: 700, marginBottom: 6, fontSize: "0.75rem", textTransform: "uppercase" }}>⬇️ Received from Previous Stage</div>
                    <div style={{ color: "var(--text-secondary)" }}>{activeStage.previous_stage_output}</div>
                  </div>
                )}

                <label className="field-label">Data Source Provider</label>
                <div className="radio-group" style={{ marginBottom: 12 }}>
                  {DATA_SOURCE_OPTIONS.map((opt) => (
                    <label className="radio-option" key={opt.value}>
                      <input
                        type="radio"
                        name={`ds-${activeStage.key}`}
                        checked={(dataSource[activeStage.key] ?? "synthetic") === opt.value}
                        onChange={() => setDataSource((prev) => ({ ...prev, [activeStage.key]: opt.value }))}
                      />
                      {opt.label}
                    </label>
                  ))}
                </div>

                <label className="field-label">Category / Focus Class</label>
                <select
                  value={categoryFilter[activeStage.key] ?? "ALL"}
                  onChange={(e) => setCategoryFilter((prev) => ({ ...prev, [activeStage.key]: e.target.value }))}
                  style={{ marginBottom: 10 }}
                >
                  <option value="ALL">ALL</option>
                  {activeStage.ui_config.filter_options.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button className="btn btn-secondary btn-small" onClick={() => setPreviewOpen((p) => ({ ...p, [activeStage.key]: !p[activeStage.key] }))}>
                    🔍 {previewOpen[activeStage.key] ? "Hide" : "Preview"} Input Data ({activeStage.input_row_count.toLocaleString()} rows)
                  </button>
                  {activeStage.io.input_key && (
                    <button className="btn btn-secondary btn-small" onClick={() => api.downloadDataset(activeStage.io.input_key!)}>
                      ⬇️ Download Input CSV
                    </button>
                  )}
                </div>
                {previewOpen[activeStage.key] && (
                  previewQ.isLoading
                    ? <div style={{ marginTop: 10 }}><LoadingBlock label="Loading preview…" /></div>
                    : <div style={{ marginTop: 10, maxHeight: 260, overflowY: "auto" }}>
                        <DataTable columns={previewQ.data?.columns ?? []} records={previewRecords} limit={30} />
                      </div>
                )}
              </div>

              <div>
                <div className="section-title" style={{ color: textColor }}>🛡️ Column 2: Frameworks &amp; Scenario</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14 }}>
                  {overview.frameworks.map((f) => <Badge key={f} variant={FRAMEWORK_VARIANT(f)}>{f}</Badge>)}
                </div>
                <label className="field-label">Custom Threat Scenario / Scope Context</label>
                <textarea rows={6} placeholder="Enter specific agent IDs, departments, adversarial techniques, or target logic specs to direct the agent…" />
              </div>

              <div>
                <div className="section-title" style={{ color: textColor }}>👁️ Column 3: Active Guardrails</div>
                <div style={{ background: "rgba(var(--overlay-rgb), 0.03)", border: "1px solid var(--border-glass)", borderRadius: 12, padding: "14px 18px", minHeight: 200 }}>
                  <div style={{ fontSize: "0.72rem", textTransform: "uppercase", color: "var(--text-muted)", fontWeight: 700, marginBottom: 10 }}>Active Security Shields</div>
                  <div style={{ marginBottom: 10 }}>
                    <Badge variant="green">🟢 Structured JSON Extraction</Badge>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-secondary)", marginTop: 4 }}>
                      Extracts and parses the agent's JSON response, tolerating preamble text or code fences —
                      malformed output degrades to a raw-text fallback instead of crashing.
                    </div>
                  </div>
                  <div style={{ marginBottom: 10 }}>
                    <Badge variant="green">🟢 Hallucination Cross-Check</Badge>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-secondary)", marginTop: 4 }}>
                      After execution, every cited CVE, MITRE ATT&amp;CK/ATLAS technique, and agent reference is
                      checked against real sources — see the Observability tab for this stage's report.
                    </div>
                  </div>
                  <div>
                    <Badge variant={activeStage.ui_config.hitl ? "amber" : "blue"}>
                      {activeStage.ui_config.hitl ? "🟡 HITL Gate Active" : "🟢 Automated — Advisory"}
                    </Badge>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-secondary)", marginTop: 4 }}>
                      {activeStage.ui_config.hitl ? "Critical-severity findings require manual analyst approval before handoff." : "Findings feed directly into the next stage without a manual gate."}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </GlassCard>

          {/* Agent details bar */}
          <div className="agent-bar" style={{ borderLeftColor: color }}>
            <div className="label"><span style={{ color: textColor, fontSize: "1.1rem" }}>🤖</span> Agent Scope: <span style={{ color: textColor }}>{activeStage.agent_info.agent}</span></div>
            <div className="divider" />
            <div className="content"><span className="label">🧠 Expected AI Analysis:</span> {activeStage.agent_info.analysis}</div>
            <div className="divider" />
            <div className="content"><span className="label">📄 Expected Output:</span> {activeStage.agent_info.output}</div>
          </div>

          <button
            className="btn btn-execute"
            disabled={runMut.isPending || (activeIndex > 0 && !completedStages.includes(activeIndex - 1))}
            onClick={() => runMut.mutate(activeStage.key)}
          >
            {runMut.isPending ? "Running…" : "🚀 Execute AI Analysis"}
          </button>
          {activeIndex > 0 && !completedStages.includes(activeIndex - 1) && (
            <div className="muted" style={{ fontSize: "0.78rem", marginTop: 6 }}>Complete the previous stage first.</div>
          )}

          {/* Results */}
          {outcome && (
            <div>
              <div className="result-tabs">
                <span className={`result-tab${resultTab === "analysis" ? " active" : ""}`} onClick={() => setResultTab("analysis")}>🧠 AI Analysis</span>
                <span className={`result-tab${resultTab === "output" ? " active" : ""}`} onClick={() => setResultTab("output")}>📋 Output &amp; Handoff</span>
                {isFinalStage && (
                  <span className={`result-tab${resultTab === "workflow" ? " active" : ""}`} onClick={() => setResultTab("workflow")}>🛠️ Remediation &amp; Workflow</span>
                )}
              </div>

              {resultTab === "analysis" && (
                <div className="ai-panel">
                  {dataSource[activeStage.key] === "synthetic" || !dataSource[activeStage.key] ? (
                    <div className="synthetic-banner">⚠️ Synthetic Data — This analysis uses AI-generated demonstration data.</div>
                  ) : null}
                  {result && result.live_mcp_used.length > 0 && (
                    <div className="badge badge-green" style={{ marginBottom: 12 }}>
                      🟢 Includes real live data from: {result.live_mcp_used.join(", ")}
                    </div>
                  )}
                  {outcome.error && <div className="login-error" style={{ marginBottom: 12 }}>Agent execution failed: {outcome.error}</div>}

                  <div className="grid-4" style={{ marginBottom: 20 }}>
                    <div className="metric-card"><div className="metric-value" style={{ color: textColor }}>{outcome.ai_confidence}%</div><div className="metric-label">AI Confidence</div></div>
                    <div className="metric-card"><div className="metric-value" style={{ color: textColor }}>{outcome.findings.length}</div><div className="metric-label">Findings</div></div>
                    <div className="metric-card"><div className="metric-value" style={{ color: textColor }}>{outcome.findings.filter((f) => f.severity === "Critical").length}</div><div className="metric-label">Critical</div></div>
                    <div className="metric-card"><div className="metric-value" style={{ color: textColor }}>{outcome.recommendations.length}</div><div className="metric-label">Recommendations</div></div>
                  </div>

                  <h4>Analysis Summary</h4>
                  <p style={{ color: "var(--text-secondary)", whiteSpace: "pre-line", fontSize: "0.9rem", lineHeight: 1.6 }}>{outcome.summary}</p>

                  <h4>AI-Scored Findings Catalog</h4>
                  {outcome.findings.map((f) => (
                    <div className="finding-card" key={f.id}>
                      <div className="top">
                        <span className="title">{f.title}</span>
                        <Badge variant={severityVariant(f.severity)}>{f.severity.toUpperCase()}</Badge>
                      </div>
                      <div className="desc">{f.description}</div>
                      <div className="meta"><strong>Evidence:</strong> {f.evidence}</div>
                      <div className="meta"><strong>Recommendation:</strong> {f.recommendation}</div>
                    </div>
                  ))}

                  {outcome.step_by_step_execution?.length > 0 && (
                    <>
                      <h4>Under the Hood: Agent Execution Trace</h4>
                      <ol style={{ color: "var(--text-secondary)", fontSize: "0.85rem", lineHeight: 1.8 }}>
                        {outcome.step_by_step_execution.map((s, i) => <li key={i}>{s}</li>)}
                      </ol>
                    </>
                  )}

                  <h4>Recommended Action Plan</h4>
                  <ul style={{ color: "var(--text-secondary)", fontSize: "0.9rem", lineHeight: 1.8 }}>
                    {outcome.recommendations.map((r, i) => <li key={i} dangerouslySetInnerHTML={{ __html: r.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>") }} />)}
                  </ul>

                  {result?.chart && <GlassCard style={{ marginTop: 16 }}><Chart chart={result.chart} accent={color} /></GlassCard>}
                </div>
              )}

              {resultTab === "output" && (
                <GlassCard>
                  <div className="section-title">{activeStage.io.output_name}</div>
                  <p className="muted" style={{ fontSize: "0.85rem" }}>{activeStage.io.output_desc}</p>
                  {result ? (
                    <>
                      <div style={{ display: "flex", gap: 16, alignItems: "center", fontSize: "0.8rem", marginBottom: 12 }}>
                        <span>📊 {result.output_preview.row_count.toLocaleString()} rows</span>
                        <span>🎛️ {result.output_preview.columns.length} columns</span>
                        {activeStage.io.output_key && (
                          <button className="btn btn-secondary btn-small" onClick={() => api.downloadDataset(activeStage.io.output_key!)}>
                            ⬇️ Download Output CSV
                          </button>
                        )}
                      </div>
                      <DataTable columns={result.output_preview.columns} records={result.output_preview.records} />
                    </>
                  ) : (
                    <p className="muted">Run this stage to see the output dataset preview.</p>
                  )}
                  <p style={{ marginTop: 14, fontSize: "0.85rem", color: "var(--text-secondary)" }}>{outcome.passed_to_next_stage}</p>
                </GlassCard>
              )}

              {resultTab === "workflow" && isFinalStage && (() => {
                const wf = workflow[activeStage.key] ?? { status: "APPROVAL QUEUE" as const };
                const ticketCard = (label: string, color: string, t?: TicketResult) => (
                  <div className="metric-card">
                    <div className="metric-value" style={{ fontSize: "1.2rem", color }}>
                      {t ? (t.success ? (t.ticket_ref ?? "—") : "Failed") : "—"}
                    </div>
                    <div className="metric-label">
                      {label}{t && (t.live ? <Badge variant="green">🟢 Live</Badge> : <Badge variant="blue">🔵 Mock</Badge>)}
                    </div>
                    {t?.url && <a href={t.url} target="_blank" rel="noreferrer" style={{ fontSize: "0.72rem" }}>Open ticket →</a>}
                    {t?.error && <div className="muted" style={{ fontSize: "0.7rem", color: "var(--accent-red)" }}>{t.error}</div>}
                  </div>
                );
                return (
                  <GlassCard>
                    <div className="section-title">Remediation Workflow — {wf.status}</div>
                    <div className="grid-2" style={{ marginBottom: 16 }}>
                      {ticketCard("Jira", "var(--accent-blue)", wf.jira)}
                      {ticketCard("ServiceNow", "var(--accent-purple)", wf.servicenow)}
                    </div>
                    {wf.status === "APPROVAL QUEUE" && (
                      <button
                        className="btn"
                        disabled={dispatchMut.isPending}
                        onClick={() => dispatchMut.mutate({
                          stageKey: activeStage.key,
                          summary: `${overview.title} — ${activeStage.name} remediation`,
                          description: outcome.summary?.slice(0, 500) ?? "",
                        })}
                      >
                        {dispatchMut.isPending ? "Dispatching…" : "✅ Approve & Dispatch Remediation Tickets"}
                      </button>
                    )}
                    {wf.status === "IMPLEMENTATION TRACKING" && (
                      <button className="btn" onClick={() => closeWorkflow(activeStage.key)}>
                        ✅ Verify Deployment & Close Active Tickets
                      </button>
                    )}
                    {wf.status === "COMPLETED & VERIFIED" && <div className="badge badge-green">✓ Workflow Complete</div>}
                  </GlassCard>
                );
              })()}
            </div>
          )}

          {/* HITL gate */}
          {result?.hitl_required && hitlApprovedMap[activeStage.key] === undefined && (
            <div className="hitl-gate">
              <div className="title">⚠️ Human-in-the-Loop Gate — {activeStage.name}</div>
              {result.hitl_candidates.map((c) => <div className="item" key={c.id}>{c.label}</div>)}
              <div className="actions">
                <button className="btn" onClick={() => hitlMut.mutate({ stageKey: activeStage.key, decision: "approve" })}>✅ Approve &amp; Proceed</button>
                <button className="btn btn-danger" onClick={() => hitlMut.mutate({ stageKey: activeStage.key, decision: "reject" })}>❌ Reject &amp; Review</button>
              </div>
            </div>
          )}
          {hitlApprovedMap[activeStage.key] === true && (
            <div className="badge badge-green" style={{ marginTop: 12 }}>✅ Approved — handed off to the next stage.</div>
          )}
          {hitlApprovedMap[activeStage.key] === false && (
            <div className="badge badge-red" style={{ marginTop: 12 }}>❌ Rejected for further review.</div>
          )}
        </>
      )}
    </div>
  );
}
