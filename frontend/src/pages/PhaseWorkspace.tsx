import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { PhaseKey, RunStageResponse, Stage, TicketResult } from "../lib/types";
import { Chart } from "../components/Chart";
import { Badge, DataTable, GlassCard, LoadingBlock, severityVariant } from "../components/ui";
import { useTheme } from "../context/ThemeContext";
import { readableAccent } from "../lib/color";
import { AttackExchange, getAttackRows } from "../components/AttackExchange";
import { AttackPath } from "../components/AttackPath";
import { RecoverProof } from "../components/RecoverProof";
import { SlackApprovalCard } from "../components/SlackApprovalCard";
import { Expandable } from "../components/Expandable";
import { LakeraTestPanel } from "../components/LakeraTestPanel";
import { GarakPyritLivePanel } from "../components/GarakPyritLivePanel";
import { LiveVulnerabilityDemo } from "../components/LiveVulnerabilityDemo";

// Canonical story order — matches the real backend data-generation order
// (app/data/live_engine.py's generate_all()): Govern's real evaluation
// needs Identify/Protect/Detect's real findings first, so it runs (and is
// shown) right after Detect, feeding Respond/Recover's own real
// consolidated incident_queue in turn.
const STORY_ORDER: PhaseKey[] = ["identify", "protect", "detect", "govern", "respond", "recover"];
const STORY_LABELS: Record<string, string> = {
  govern: "Govern", identify: "Identify", protect: "Protect", detect: "Detect", respond: "Respond", recover: "Recover",
};

// Both options analyse the same real data (LiveDataEngine — the real
// meridian-support-agent repo + deployed agent, never synthetic, no
// upload path since there's nothing to upload in this demo). "mcp" adds
// real-time external enrichment on top for the stages that support one; it
// isn't a fallback tier, it's strictly additive — and it isn't tied to any
// one named vendor, since which external source actually applies depends
// on the stage and what's connected in Settings.
const DATA_SOURCE_OPTIONS: { value: string; label: string }[] = [
  { value: "live", label: "GitHub Repo + Deployed Agent" },
  { value: "mcp", label: "+ External Source (SIEM / Security API, via MCP)" },
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

/** Surfaces GuardrailManager's real V5_THRESHOLDS gate logic (app/guardrails/validator.py)
 * as a "Policy → Decision → Control → Evidence" strip, instead of only exposing the bare
 * hitl_required boolean it resolves to. */
function PolicyDecisionTrace({ trace, accent }: { trace: import("../lib/types").PolicyDecisionTrace; accent: string }) {
  const decisionColor = trace.decision ? "var(--accent-amber)" : "var(--accent-green)";
  const steps: { label: string; value: string; color?: string }[] = [
    { label: "Policy", value: trace.policy ?? "—" },
    { label: "Control", value: trace.control ?? "—" },
    { label: "Decision", value: trace.decision ? "Human Approval Required" : "Auto-Approved", color: decisionColor },
    { label: "Evidence", value: trace.evidence ?? trace.decision_reason ?? "—" },
  ];
  return (
    <div className="glass-card" style={{ borderLeft: `3px solid ${accent}`, marginBottom: 20, padding: "14px 16px" }}>
      <div style={{ fontSize: "0.72rem", fontWeight: 700, letterSpacing: "0.04em", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: 10 }}>
        ⚖️ Policy Decision Trace
      </div>
      <div style={{ display: "flex", alignItems: "stretch", gap: 0, flexWrap: "wrap" }}>
        {steps.map((s, i) => (
          <div key={s.label} style={{ display: "flex", alignItems: "center" }}>
            <div style={{ minWidth: 160, maxWidth: 240 }}>
              <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.03em", marginBottom: 3 }}>{s.label}</div>
              <div style={{ fontSize: "0.8rem", color: s.color ?? "var(--text-primary)", fontWeight: s.color ? 700 : 500, lineHeight: 1.4, wordBreak: "break-word" }}>{s.value}</div>
            </div>
            {i < steps.length - 1 && <div style={{ margin: "0 14px", color: "var(--text-muted)", fontSize: "1.1rem", alignSelf: "center" }}>→</div>}
          </div>
        ))}
      </div>
      {trace.decision_reason && trace.evidence && (
        <div style={{ marginTop: 10, fontSize: "0.78rem", color: "var(--text-secondary)", borderTop: "1px solid var(--border-glass)", paddingTop: 8 }}>
          {trace.decision_reason}
        </div>
      )}
    </div>
  );
}

export function PhaseWorkspace() {
  const { uc } = useParams<{ uc: PhaseKey }>();
  const phase = (uc ?? "identify") as PhaseKey;
  const qc = useQueryClient();
  const { theme } = useTheme();
  const navigate = useNavigate();

  const stagesQ = useQuery({ queryKey: ["phase-stages", phase], queryFn: () => api.phaseStages(phase) });
  const stateQ = useQuery({ queryKey: ["phase-state", phase], queryFn: () => api.phaseState(phase) });
  // Same queryKey the Sidebar already uses — shares its cache rather than
  // issuing a second real fetch.
  const settingsQ = useQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 30_000 });
  // Same queryKey the StoryBar/Sidebar already use — shares cache, no extra fetch.
  const dashboardQ = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, staleTime: 30_000 });
  const fetchError = dashboardQ.data?.data_health?.[phase];

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

  // Every dataset (and the row counts/previews/dashboard derived from them)
  // was just re-fetched server-side, so nothing cached client-side is safe.
  const reloadMut = useMutation({
    mutationFn: api.reloadLiveData,
    onSuccess: () => qc.invalidateQueries(),
  });

  const runMut = useMutation({
    mutationFn: (args: { stageKey: string; silent?: boolean }) => api.runStage(phase, args.stageKey, dataSource[args.stageKey] ?? "live"),
    onSuccess: (res, args) => {
      setRunResult((prev) => ({ ...prev, [args.stageKey]: res }));
      qc.invalidateQueries({ queryKey: ["phase-state", phase] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      // A silent re-run (e.g. the live Guardrail Proxy panel refreshing Output &
      // Handoff after a real send) shouldn't yank the user back to the AI
      // Analysis tab if they're looking at Output & Handoff.
      if (!args.silent) setResultTab("analysis");
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

  if (stagesQ.isLoading || !stagesQ.data) return <LoadingBlock label={`Loading ${phase}…`} />;

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
                  <div style={{ marginBottom: 6 }}>
                    <Expandable trigger={<span style={{ fontWeight: 700, color: "var(--text-heading)" }}>{activeStage.io.input_name}</span>}>
                      <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{activeStage.io.input_desc}</div>
                    </Expandable>
                  </div>
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
                {settingsQ.data?.github_target_repo && (
                  <div className="muted" style={{ fontSize: "0.76rem", marginBottom: 8 }}>
                    🎯 Targeting{" "}
                    <a href={`https://github.com/${settingsQ.data.github_target_repo}`} target="_blank" rel="noreferrer">
                      {settingsQ.data.github_target_repo}
                    </a>
                    {settingsQ.data.target_agent_url && <> · deployed agent at <code>{settingsQ.data.target_agent_url}</code></>}
                    {" · "}
                    <Link to="/settings" style={{ color: "var(--accent-blue)" }}>Change target →</Link>
                  </div>
                )}
                {fetchError && (
                  <div style={{ background: "rgba(255,68,68,0.08)", border: "1px solid var(--accent-red)", borderRadius: 8, padding: "8px 10px", marginBottom: 10, fontSize: "0.76rem", color: "var(--accent-red)" }}>
                    ⚠️ Couldn't fetch real {phase} data from this target: {fetchError}
                    <div style={{ marginTop: 8 }}>
                      <button className="btn btn-secondary btn-small" onClick={() => reloadMut.mutate()} disabled={reloadMut.isPending}>
                        {reloadMut.isPending ? "Retrying — waiting for the target to respond…" : "🔄 Retry live data fetch"}
                      </button>
                      {reloadMut.isError && <span style={{ marginLeft: 8 }}>Retry failed — try again in a moment.</span>}
                    </div>
                  </div>
                )}
                <div className="radio-group" style={{ marginBottom: 12 }}>
                  {DATA_SOURCE_OPTIONS.map((opt) => (
                    <label className="radio-option" key={opt.value}>
                      <input
                        type="radio"
                        name={`ds-${activeStage.key}`}
                        checked={(dataSource[activeStage.key] ?? "live") === opt.value}
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
                    <Expandable trigger={<Badge variant="green">🟢 Structured JSON Extraction</Badge>}>
                      <div style={{ fontSize: "0.68rem", color: "var(--text-secondary)" }}>
                        Extracts and parses the agent's JSON response, tolerating preamble text or code fences —
                        malformed output degrades to a raw-text fallback instead of crashing.
                      </div>
                    </Expandable>
                  </div>
                  <div style={{ marginBottom: 10 }}>
                    <Expandable trigger={<Badge variant="green">🟢 Hallucination Cross-Check</Badge>}>
                      <div style={{ fontSize: "0.68rem", color: "var(--text-secondary)" }}>
                        After execution, every cited CVE, MITRE ATT&amp;CK/ATLAS technique, and agent reference is
                        checked against real sources — see the Observability tab for this stage's report.
                      </div>
                    </Expandable>
                  </div>
                  <div>
                    <Expandable
                      trigger={
                        <Badge variant={activeStage.ui_config.hitl ? "amber" : "blue"}>
                          {activeStage.ui_config.hitl ? "🟡 HITL Gate Active" : "🟢 Automated — Advisory"}
                        </Badge>
                      }
                    >
                      <div style={{ fontSize: "0.68rem", color: "var(--text-secondary)" }}>
                        {activeStage.ui_config.hitl ? "Critical-severity findings require manual analyst approval before handoff." : "Findings feed directly into the next stage without a manual gate."}
                      </div>
                    </Expandable>
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

          {phase === "protect" && activeStage.key === "guardrail_proxy" && (
            <LakeraTestPanel onSent={() => runMut.mutate({ stageKey: activeStage.key, silent: true })} />
          )}
          {phase === "detect" && (activeStage.key === "injection_detection" || activeStage.key === "red_teaming") && <GarakPyritLivePanel />}
          {phase === "detect" && activeStage.key === "injection_detection" && <LiveVulnerabilityDemo />}

          <button
            className="btn btn-execute"
            disabled={runMut.isPending || (activeIndex > 0 && !completedStages.includes(activeIndex - 1))}
            onClick={() => runMut.mutate({ stageKey: activeStage.key })}
          >
            {runMut.isPending ? "Running…" : "🚀 Execute AI Analysis"}
          </button>
          {activeIndex > 0 && !completedStages.includes(activeIndex - 1) && (
            <div className="muted" style={{ fontSize: "0.78rem", marginTop: 6 }}>Complete the previous stage first.</div>
          )}
          {runMut.isError && (
            <div className="login-error" style={{ marginTop: 10 }}>
              Request failed: {runMut.error instanceof Error ? runMut.error.message : "Unknown error"} — click Execute to retry.
            </div>
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
                  {result && result.live_mcp_used.length > 0 && (
                    <div className="badge badge-green" style={{ marginBottom: 12 }}>
                      🟢 Includes real live data from: {result.live_mcp_used.join(", ")}
                    </div>
                  )}
                  {(() => {
                    // The real Lakera rows this run actually used to enrich the LLM's
                    // analysis — the LLM's findings paraphrase them, but nothing showed
                    // the raw real API results themselves anywhere on this page. This
                    // is that: the same rows outcome.aggregation already carries, not a
                    // separate fetch.
                    const lakeraAgg = outcome.aggregation?.lakera_guard_live_results;
                    if (!lakeraAgg?.rows?.length) return null;
                    return (
                      <div style={{ marginBottom: 16 }}>
                        <h4 style={{ marginBottom: 6 }}>🛡️ Real Lakera Guard results used in this run</h4>
                        <DataTable columns={lakeraAgg.columns ?? Object.keys(lakeraAgg.rows[0])} records={lakeraAgg.rows} />
                      </div>
                    );
                  })()}
                  {outcome.error && <div className="login-error" style={{ marginBottom: 12 }}>Agent execution failed: {outcome.error}</div>}

                  <div className="grid-4" style={{ marginBottom: 20 }}>
                    <div className="metric-card"><div className="metric-value" style={{ color: textColor }}>{outcome.ai_confidence}%</div><div className="metric-label">AI Confidence</div></div>
                    <div className="metric-card"><div className="metric-value" style={{ color: textColor }}>{outcome.findings.length}</div><div className="metric-label">Findings</div></div>
                    <div className="metric-card"><div className="metric-value" style={{ color: textColor }}>{outcome.findings.filter((f) => f.severity === "Critical").length}</div><div className="metric-label">Critical</div></div>
                    <div className="metric-card"><div className="metric-value" style={{ color: textColor }}>{outcome.recommendations.length}</div><div className="metric-label">Recommendations</div></div>
                  </div>

                  {result?.policy_decision_trace && <PolicyDecisionTrace trace={result.policy_decision_trace} accent={color} />}

                  {phase === "recover" && activeStage.key === "rollback" && (
                    <>
                      <RecoverProof />
                      <SlackApprovalCard
                        uc={phase}
                        stageKey={activeStage.key}
                        summary={outcome.summary}
                        actionType="restore_target_agent"
                        actionLabel="Restore the target agent to active service"
                      />
                    </>
                  )}
                  {phase === "respond" && activeStage.key === "containment" && (
                    <SlackApprovalCard
                      uc={phase}
                      stageKey={activeStage.key}
                      summary={outcome.summary}
                      actionType="suspend_target_agent"
                      actionLabel="Suspend the target agent"
                    />
                  )}

                  <h4>Analysis Summary</h4>
                  <p style={{ color: "var(--text-secondary)", whiteSpace: "pre-line", fontSize: "0.9rem", lineHeight: 1.6 }}>{outcome.summary}</p>

                  {(() => {
                    const isDetectAttack = phase === "detect" && (activeStage.key === "injection_detection" || activeStage.key === "red_teaming");
                    const attackRows = isDetectAttack ? getAttackRows(outcome) : [];
                    if (attackRows.length > 0) {
                      return (
                        <>
                          <div style={{ background: "rgba(255,68,68,0.07)", border: "1px solid var(--accent-red)44", borderRadius: 10, padding: "12px 14px", marginBottom: 16, display: "flex", flexDirection: "column", gap: 6, fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                              <span style={{ fontSize: "1.05rem" }}>🎯</span>
                              <strong style={{ color: "var(--accent-red)", fontSize: "0.85rem" }}>Standardized Attack Vector: MITRE ATLAS AML.T0051 (LLM Prompt Injection)</strong>
                              <span style={{ fontSize: "0.7rem", background: "rgba(255,68,68,0.18)", color: "var(--accent-red)", padding: "1px 7px", borderRadius: 4, fontWeight: 600 }}>
                                OWASP LLM01 / LLM06
                              </span>
                            </div>
                            <div style={{ fontSize: "0.78rem", lineHeight: 1.5 }}>
                              <strong>Consistent Target Canary &amp; Lifecycle Thread:</strong> The model was probed with Direct System Prompt Extraction to extract Meridian's internal GitHub deployment PAT (<code>ghp_Uh9...</code>). This is the exact same attack technique and credential tracked across all lifecycle phases:
                              <ul style={{ margin: "5px 0 2px 18px", padding: 0 }}>
                                <li><strong>Protect:</strong> Evasion bypasses input filters when output guardrail is unhardened.</li>
                                <li><strong>Detect:</strong> Direct adversarial queries measure raw agent exposure without perimeter proxy defense.</li>
                                <li><strong>Respond:</strong> SOAR Playbooks isolate the compromised agent session and revoke the leaked deployment token.</li>
                                <li><strong>Recover:</strong> Output guardrails are permanently hardened and prompt config rolled back to block this exact vector.</li>
                              </ul>
                            </div>
                            <div style={{ fontSize: "0.73rem", color: "var(--text-muted)", borderTop: "1px solid var(--accent-red)22", paddingTop: 5 }}>
                              ⚠️ <em>Why attacks leak here:</em> Detect evaluates the target agent's raw vulnerability surface — what an attacker who circumvents perimeter proxies actually faces.
                            </div>
                          </div>
                          <h4>Attack path</h4>
                          <AttackPath rows={attackRows} />
                          <h4>Attack exchange (real prompts and responses)</h4>
                          <AttackExchange rows={attackRows} />
                        </>
                      );
                    }
                    const toolBadge = (result?.live_mcp_used ?? [])
                      .map((k) => ({ garak_live_scan: "🐛 real garak scan", pyrit_live_scan: "🎯 real pyrit scan", lakera_guard_live_results: "🔰 real lakera scan" }[k]))
                      .find((v) => v);
                    return (
                      <>
                        <h4>AI-Scored Findings Catalog</h4>
                        {outcome.findings.map((f) => (
                          <div className="finding-card" key={f.id}>
                            <div className="top">
                              <span className="title">{f.title}</span>
                              <div style={{ display: "flex", gap: 6 }}>
                                {toolBadge && <Badge variant="blue">{toolBadge}</Badge>}
                                <Badge variant={severityVariant(f.severity)}>{f.severity.toUpperCase()}</Badge>
                              </div>
                            </div>
                            <div className="desc">{f.description}</div>
                            <div className="meta"><strong>Evidence:</strong> {f.evidence}</div>
                            <div className="meta"><strong>Recommendation:</strong> {f.recommendation}</div>
                          </div>
                        ))}
                      </>
                    );
                  })()}

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
                      {phase === "protect" && activeStage.key === "guardrail_proxy" && result.output_preview.row_count === 0 && (
                        <div style={{ background: "rgba(var(--overlay-rgb), 0.04)", border: "1px solid var(--border-glass)", borderRadius: 8, padding: "8px 10px", marginBottom: 12, fontSize: "0.76rem", color: "var(--text-secondary)" }}>
                          ℹ️ Empty until you try the live proxy above — send a prompt and this fills in.
                        </div>
                      )}
                      <DataTable columns={result.output_preview.columns} records={result.output_preview.records} />
                    </>
                  ) : (
                    <p className="muted">Run this stage to see the output dataset preview.</p>
                  )}
                  {outcome.passed_to_next_stage && (
                    <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--border-glass)" }}>
                      <div style={{ fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-muted)", fontWeight: 700, marginBottom: 4 }}>
                        🔄 Handoff Note
                      </div>
                      {(() => {
                        const trimmed = outcome.passed_to_next_stage.trim();
                        let formatted = trimmed;
                        try {
                          if (/^[\[{]/.test(trimmed)) {
                            formatted = JSON.stringify(JSON.parse(trimmed), null, 2);
                          }
                        } catch {
                          formatted = trimmed;
                        }
                        return /^[\[{]/.test(trimmed) ? (
                          <pre style={{ fontSize: "0.76rem", color: "var(--text-secondary)", whiteSpace: "pre-wrap", wordBreak: "break-word", margin: 0, fontFamily: "JetBrains Mono, monospace", background: "rgba(0,0,0,0.2)", padding: 10, borderRadius: 6 }}>
                            {formatted}
                          </pre>
                        ) : (
                          <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", margin: 0 }}>{outcome.passed_to_next_stage}</p>
                        );
                      })()}
                    </div>
                  )}
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

          {/* Guided storyboard: once this stage's real result is in (and any
              HITL gate is resolved, not pending/rejected), offer the next
              step in the story — free navigation via the tabs/pills above
              still works, this is just the default forward path. */}
          {outcome && !(result?.hitl_required && hitlApprovedMap[activeStage.key] === undefined) && hitlApprovedMap[activeStage.key] !== false && (() => {
            const stageIdx = stages.findIndex((s) => s.key === activeStage.key);
            const nextStage = stageIdx >= 0 ? stages[stageIdx + 1] : undefined;
            const storyIdx = STORY_ORDER.indexOf(phase);
            const nextPhase = storyIdx >= 0 && storyIdx < STORY_ORDER.length - 1 ? STORY_ORDER[storyIdx + 1] : null;
            const label = nextStage
              ? `Continue to ${nextStage.name} →`
              : nextPhase
              ? `Continue to ${STORY_LABELS[nextPhase]} →`
              : "Story complete — back to dashboard →";
            function handleContinue() {
              if (nextStage) setActiveStageMut.mutate(stageIdx + 1);
              else if (nextPhase) navigate(`/phase/${nextPhase}`);
              else navigate("/");
            }
            return (
              <button className="btn" style={{ marginTop: 16, background: color, borderColor: color }} onClick={handleContinue}>
                {label}
              </button>
            );
          })()}
        </>
      )}
    </div>
  );
}
