import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api";
import { GlassCard, LoadingBlock, MetricCard } from "../components/ui";

type StatusLevel = "good" | "ok" | "urgent";

const STATUS_META: Record<StatusLevel, { label: string; variant: string }> = {
  good: { label: "🟢 Good", variant: "green" },
  ok: { label: "🟡 Monitor", variant: "amber" },
  urgent: { label: "🔴 Urgent", variant: "red" },
};

// higher = better (e.g. success rate)
function statusHigherBetter(value: number, goodAt: number, okAt: number): StatusLevel {
  if (value >= goodAt) return "good";
  if (value >= okAt) return "ok";
  return "urgent";
}

// lower = better (e.g. latency)
function statusLowerBetter(value: number, goodAt: number, okAt: number): StatusLevel {
  if (value <= goodAt) return "good";
  if (value <= okAt) return "ok";
  return "urgent";
}

function HealthCard({ label, value, colour, status }: { label: string; value: string | number; colour: string; status?: StatusLevel }) {
  return (
    <div className="metric-card">
      <div className="metric-value" style={{ color: colour }}>{value}</div>
      <div className="metric-label">{label}</div>
      {status && (
        <div style={{ marginTop: 8 }}>
          <span className={`badge badge-${STATUS_META[status].variant}`}>{STATUS_META[status].label}</span>
        </div>
      )}
    </div>
  );
}

const TABS = ["LangSmith Traces", "Hallucination Detection", "Health Metrics", "Security Audit Trail"] as const;

const GRID_STROKE = "rgba(var(--overlay-rgb), 0.08)";
const TICK_STYLE = { fill: "var(--text-muted)" };
const TOOLTIP_STYLE = { background: "var(--bg-secondary)", border: "1px solid var(--border-glass)", borderRadius: 8 };
const TOOLTIP_LABEL_STYLE = { color: "var(--text-primary)" };
const TOOLTIP_ITEM_STYLE = { color: "var(--text-primary)" };

const VALIDATORS = [
  {
    name: "NVD",
    fullName: "National Vulnerability Database",
    accent: "var(--accent-blue)",
    checks: "Every CVE ID cited in AI output is looked up live against NIST's public vulnerability registry.",
    sourceLabel: "nvd.nist.gov",
    sourceUrl: "https://nvd.nist.gov/",
    internal: false,
  },
  {
    name: "MITRE ATT&CK / ATLAS",
    fullName: "Adversary Tactics & AI-Attack Technique Catalogues",
    accent: "var(--accent-red)",
    checks: "Every technique ID (T#### or AML.T####) is checked against MITRE's classic and AI-specific adversary technique catalogues.",
    sourceLabel: "attack.mitre.org · atlas.mitre.org",
    sourceUrl: "https://attack.mitre.org/",
    internal: false,
  },
  {
    name: "Agent Boundary",
    fullName: "Discovered AI Agent Inventory",
    accent: "var(--accent-teal)",
    checks: "Every agent/hostname reference is checked against your own discovered agent inventory — flags anything outside the known boundary.",
    sourceLabel: "Internal — Data Explorer",
    sourceUrl: "/data-explorer",
    internal: true,
  },
];

export function ObservabilityPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({ queryKey: ["observability"], queryFn: api.observability, refetchInterval: 15_000 });
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [tab, setTab] = useState<typeof TABS[number]>("LangSmith Traces");

  if (isLoading || !data) return <LoadingBlock label="Loading observability data…" />;

  const lsActive = !!(settings?.langchain_tracing && settings?.langchain_api_key_set);
  const lsProject = settings?.langchain_project || "securing-ai-demo";
  const avgTraceLatency = data.traces.length > 0
    ? data.traces.reduce((sum, t) => sum + t.duration_ms, 0) / data.traces.length
    : 0;
  const agentLatencyData = data.traces.map((t, i) => ({
    label: `${t.agent.replace(/Agent$/, "")} #${i + 1}`,
    duration_ms: t.duration_ms,
    status: t.status,
  }));

  const reportEntries = Object.entries(data.hallucination_reports);
  const totalFlags = reportEntries.reduce((n, [, r]) => n + r.flags.length, 0);

  // Chronological (oldest-first) view of real per-call latency, for the "over time" chart.
  const latencyOverTime = data.traces.map((t, i) => ({
    call: `#${i + 1}`,
    time: new Date(t.timestamp).toLocaleTimeString(),
    duration_ms: t.duration_ms,
    status: t.status,
  }));

  // Latency distribution — real per-call durations bucketed into ranges, not simulated.
  const LATENCY_BUCKETS = [500, 1000, 1500, 2000, 3000, 5000, 8000];
  const latencyDistribution = LATENCY_BUCKETS.map((upper, i) => {
    const lower = i === 0 ? 0 : LATENCY_BUCKETS[i - 1];
    const label = i === LATENCY_BUCKETS.length - 1 ? `${lower}ms+` : `${lower}-${upper}ms`;
    const count = data.traces.filter((t) => t.duration_ms > lower && (i === LATENCY_BUCKETS.length - 1 || t.duration_ms <= upper)).length;
    return { range: label, count };
  });

  const guardrailEventsByType = Object.entries(
    data.guardrail_events.reduce<Record<string, number>>((acc, e) => {
      acc[e.type] = (acc[e.type] ?? 0) + 1;
      return acc;
    }, {})
  ).map(([type, count]) => ({ type, count }));

  return (
    <div>
      <div className="hero-banner">
        <div className="hero-title">🔭 Observability</div>
        <div className="hero-subtitle">LLM traces, hallucination detection, health metrics, and audit trail</div>
      </div>

      <div className="top-tabs">
        {TABS.map((t) => <span key={t} className={`top-tab${tab === t ? " active" : ""}`} onClick={() => setTab(t)}>{t}</span>)}
      </div>

      {tab === "LangSmith Traces" && (
        <div>
          <div className="grid-2" style={{ marginBottom: 16 }}>
            <GlassCard accent={lsActive ? "var(--accent-green)" : "var(--accent-amber)"}>
              <strong style={{ fontSize: "1.05rem", color: lsActive ? "var(--accent-green)" : "var(--accent-amber)" }}>
                {lsActive ? "🟢 LangSmith Synced & Active" : "🟡 Running in Offline Sandbox Mode"}
              </strong>
              <div className="muted" style={{ fontSize: "0.82rem", marginTop: 6 }}>
                {lsActive
                  ? "Tracing is enabled and an API key is configured — LangChain calls are sent to LangSmith for full trace trees."
                  : "Tracing is off or no LangSmith API key is set. Traces below are still captured locally, just not synced externally."}
              </div>
            </GlassCard>
            <GlassCard accent="var(--accent-blue)">
              <strong style={{ fontSize: "1.05rem", color: "var(--accent-blue)" }}>Agent Telemetry Latency</strong>
              <div className="muted" style={{ fontSize: "0.82rem", marginTop: 6 }}>
                Average execution time: <strong style={{ color: "var(--text-heading)" }}>{avgTraceLatency.toFixed(0)}ms</strong> across <strong style={{ color: "var(--text-heading)" }}>{data.traces.length} calls</strong> this session.
              </div>
            </GlassCard>
          </div>

          <div className="grid-2" style={{ marginBottom: 16, alignItems: "stretch" }}>
            <GlassCard>
              <div className="section-title">Agent Execution Latency (ms)</div>
              {agentLatencyData.length === 0 ? (
                <p className="muted" style={{ fontSize: "0.82rem" }}>No traces yet — execute a stage to generate one.</p>
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={agentLatencyData}>
                    <CartesianGrid stroke={GRID_STROKE} />
                    <XAxis dataKey="label" tick={{ ...TICK_STYLE, fontSize: 9 }} interval={0} angle={-20} textAnchor="end" height={60} />
                    <YAxis tick={{ ...TICK_STYLE, fontSize: 10 }} unit="ms" />
                    <Tooltip
                      contentStyle={TOOLTIP_STYLE}
                      labelStyle={TOOLTIP_LABEL_STYLE}
                      itemStyle={TOOLTIP_ITEM_STYLE}
                      formatter={(v) => [`${v}ms`, "Duration"]}
                    />
                    <Bar dataKey="duration_ms" name="Duration" radius={[4, 4, 0, 0]}>
                      {agentLatencyData.map((d, i) => <Cell key={i} fill={d.status === "Success" ? "var(--accent-green)" : "var(--accent-red)"} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </GlassCard>

            <GlassCard>
              <div className="section-title">🔗 LangSmith Tracing Details</div>
              <div className="muted" style={{ fontSize: "0.78rem", marginBottom: 12 }}>
                Syncing provides full trace trees including tools run and prompt templates.
              </div>
              <div style={{ background: "rgba(var(--overlay-rgb), 0.04)", padding: 14, borderRadius: 8, border: "1px solid var(--border-glass)", fontSize: "0.85rem", lineHeight: 1.9 }}>
                <strong>Project Workspace:</strong> <code style={{ color: "var(--accent-blue)" }}>{lsProject}</code><br />
                <strong>Tracing Status:</strong> <code style={{ color: lsActive ? "var(--accent-green)" : "var(--accent-amber)" }}>{lsActive ? "Active" : "Inactive"}</code><br />
                <strong>Orchestration:</strong> <code>LangGraph StateGraph (LangChain V2 tracing client)</code>
              </div>
              <div className="flex-row" style={{ gap: 10, marginTop: 14 }}>
                <button className="btn" style={{ flex: 1 }} onClick={() => navigate("/settings")}>⚙️ Configure API Keys</button>
                <a
                  className="btn"
                  style={{ flex: 1, textAlign: "center", textDecoration: "none" }}
                  href={`https://smith.langchain.com/projects/p/${encodeURIComponent(lsProject)}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  🔗 Open LangSmith Dashboard
                </a>
              </div>
            </GlassCard>
          </div>

          <div className="section-title">Raw Trace Logs</div>
          <GlassCard>
            <div className="data-table-wrap">
              <table className="data-table">
                <thead><tr><th>Agent</th><th>Status</th><th>Duration</th><th>Timestamp</th><th>Error</th></tr></thead>
                <tbody>
                  {data.traces.slice().reverse().map((t) => (
                    <tr key={t.id}>
                      <td>{t.agent}</td>
                      <td><span className={`badge ${t.status === "Success" ? "badge-green" : "badge-red"}`}>{t.status}</span></td>
                      <td>{t.duration_ms.toFixed(0)}ms</td>
                      <td>{t.timestamp}</td>
                      <td className="muted">{t.error ?? "—"}</td>
                    </tr>
                  ))}
                  {data.traces.length === 0 && <tr><td colSpan={5} className="muted">No traces yet — execute a stage to generate one.</td></tr>}
                </tbody>
              </table>
            </div>
          </GlassCard>
        </div>
      )}

      {tab === "Hallucination Detection" && (
        <div>
          <div className="grid-2" style={{ marginBottom: 16 }}>
            <MetricCard label="Reports Generated" value={reportEntries.length} colour="var(--accent-blue)" />
            <MetricCard label="Total Flags" value={totalFlags} colour="var(--accent-amber)" />
          </div>

          <div className="section-title" style={{ fontSize: "0.95rem", marginBottom: 8 }}>🔎 Validators</div>
          <p className="muted" style={{ fontSize: "0.78rem", marginBottom: 12 }}>
            Every AI-generated finding is cross-checked against these sources before it's trusted.
          </p>
          <div className="grid-3" style={{ marginBottom: 24 }}>
            {VALIDATORS.map((v) => (
              <GlassCard key={v.name} accent={v.accent}>
                <div style={{ fontWeight: 700, marginBottom: 2 }}>{v.name}</div>
                <div className="muted" style={{ fontSize: "0.72rem", marginBottom: 8 }}>{v.fullName}</div>
                <div style={{ fontSize: "0.82rem", marginBottom: 10 }}>{v.checks}</div>
                {v.internal ? (
                  <a href={v.sourceUrl} style={{ fontSize: "0.72rem", color: v.accent }}>
                    {v.sourceLabel} →
                  </a>
                ) : (
                  <a href={v.sourceUrl} target="_blank" rel="noreferrer" style={{ fontSize: "0.72rem", color: v.accent }}>
                    {v.sourceLabel} ↗
                  </a>
                )}
              </GlassCard>
            ))}
          </div>

          {reportEntries.map(([key, report]) => (
            <GlassCard key={key}>
              <div className="section-title">{key.replace(/_/g, " ")}</div>
              <div className="muted" style={{ fontSize: "0.8rem", marginBottom: 8 }}>
                {report.total_citations} citations checked · {(report.hallucination_rate * 100).toFixed(1)}% flagged · {report.validated_at}
              </div>
              {report.flags.length === 0 ? (
                <div className="badge badge-green">✓ VALIDATED — no issues found</div>
              ) : (
                report.flags.map((f, i) => (
                  <div className="finding-card" key={i}>
                    <div className="top"><span className="title">{f.citation}</span><span className={`badge ${f.severity === "error" ? "badge-red" : "badge-amber"}`}>{f.severity}</span></div>
                    <div className="desc">{f.finding}</div>
                    <div className="meta">Source checked: {f.source_checked}</div>
                  </div>
                ))
              )}
            </GlassCard>
          ))}
          {reportEntries.length === 0 && <GlassCard><p className="muted">No hallucination reports yet — execute a stage to generate one.</p></GlassCard>}
        </div>
      )}

      {tab === "Health Metrics" && (
        <div>
          <div className="section-title" style={{ fontSize: "0.95rem", marginBottom: 8 }}>⚡ Status</div>
          <div className="grid-3" style={{ marginBottom: 20 }}>
            <HealthCard
              label="LLM Success Rate"
              value={`${data.health_summary.success_rate.toFixed(1)}%`}
              colour="var(--accent-green)"
              status={data.health_summary.total_llm_calls > 0 ? statusHigherBetter(data.health_summary.success_rate, 90, 70) : undefined}
            />
            <HealthCard
              label="Avg Latency"
              value={`${data.health_summary.avg_latency_ms.toFixed(0)}ms`}
              colour="var(--accent-blue)"
              status={data.health_summary.total_llm_calls > 0 ? statusLowerBetter(data.health_summary.avg_latency_ms, 1500, 4000) : undefined}
            />
            <HealthCard
              label="P95 Latency"
              value={`${data.health_summary.p95_latency_ms.toFixed(0)}ms`}
              colour="var(--accent-purple)"
              status={data.health_summary.total_llm_calls > 0 ? statusLowerBetter(data.health_summary.p95_latency_ms, 3000, 7000) : undefined}
            />
          </div>

          <div className="section-title" style={{ fontSize: "0.95rem", marginBottom: 8 }}>📊 Activity</div>
          <div className="grid-4" style={{ marginBottom: 24 }}>
            <HealthCard label="Active Since" value={new Date(data.health_summary.active_since).toLocaleTimeString()} colour="var(--accent-amber)" />
            <HealthCard label="Total LLM Calls" value={data.health_summary.total_llm_calls} colour="var(--accent-blue)" />
            <HealthCard label="Guardrail Events" value={data.health_summary.guardrail_events_count} colour="var(--accent-red)" />
            <HealthCard label="HITL Decisions" value={data.health_summary.total_hitl_decisions} colour="var(--accent-teal)" />
          </div>

          <div className="grid-2">
            <GlassCard accent="var(--accent-blue)">
              <div className="section-title">LLM Call Latency Over Time</div>
              {latencyOverTime.length === 0 ? (
                <p className="muted" style={{ fontSize: "0.82rem" }}>No calls yet — execute a stage to generate data.</p>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={latencyOverTime}>
                    <CartesianGrid stroke={GRID_STROKE} />
                    <XAxis dataKey="call" tick={{ ...TICK_STYLE, fontSize: 10 }} />
                    <YAxis tick={{ ...TICK_STYLE, fontSize: 10 }} unit="ms" />
                    <Tooltip
                      contentStyle={TOOLTIP_STYLE}
                      labelStyle={TOOLTIP_LABEL_STYLE}
                      itemStyle={TOOLTIP_ITEM_STYLE}
                      formatter={(v) => [`${v}ms`, "Duration"]}
                    />
                    <Bar dataKey="duration_ms" name="Duration" radius={[4, 4, 0, 0]}>
                      {latencyOverTime.map((d, i) => <Cell key={i} fill={d.status === "Success" ? "var(--accent-blue)" : "var(--accent-red)"} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </GlassCard>

            <GlassCard accent="var(--accent-purple)">
              <div className="section-title">Latency Distribution</div>
              {latencyOverTime.length === 0 ? (
                <p className="muted" style={{ fontSize: "0.82rem" }}>No calls yet — execute a stage to generate data.</p>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={latencyDistribution}>
                    <CartesianGrid stroke={GRID_STROKE} />
                    <XAxis dataKey="range" tick={{ ...TICK_STYLE, fontSize: 9 }} interval={0} angle={-20} textAnchor="end" height={50} />
                    <YAxis tick={{ ...TICK_STYLE, fontSize: 10 }} allowDecimals={false} />
                    <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} />
                    <Bar dataKey="count" name="Calls" fill="var(--accent-purple)" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </GlassCard>
          </div>

          <div className="grid-2" style={{ marginTop: 16 }}>
            <GlassCard accent="var(--accent-red)">
              <div className="section-title">Guardrail Events by Type</div>
              {guardrailEventsByType.length === 0 ? (
                <p className="muted" style={{ fontSize: "0.82rem" }}>No guardrail events yet.</p>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={guardrailEventsByType}>
                    <CartesianGrid stroke={GRID_STROKE} />
                    <XAxis dataKey="type" tick={{ ...TICK_STYLE, fontSize: 10 }} />
                    <YAxis tick={{ ...TICK_STYLE, fontSize: 10 }} allowDecimals={false} />
                    <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} />
                    <Bar dataKey="count" fill="var(--accent-red)" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </GlassCard>
            <GlassCard accent="var(--accent-green)">
              <div className="section-title">HITL Approval Ratio</div>
              <div style={{ fontSize: "0.82rem", marginBottom: 10 }}>
                <span style={{ fontSize: "2rem", fontWeight: 800, color: "var(--accent-green)" }}>
                  {data.health_summary.hitl_approval_ratio.toFixed(1)}%
                </span>
                <span className="muted"> of {data.health_summary.total_hitl_decisions} human-in-the-loop decisions approved</span>
              </div>
              <p className="muted" style={{ fontSize: "0.75rem" }}>
                Not scored good/bad — a very high ratio can mean confident automation, or reviewers rubber-stamping. Read alongside the audit trail.
              </p>
            </GlassCard>
          </div>
        </div>
      )}

      {tab === "Security Audit Trail" && (
        <GlassCard>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead><tr><th>Timestamp</th><th>Action</th><th>User</th><th>Status</th><th>Target</th></tr></thead>
              <tbody>
                {data.audit_log.map((a, i) => (
                  <tr key={i}>
                    <td>{a.timestamp}</td><td>{a.action}</td><td>{a.username}</td>
                    <td><span className={`badge ${a.status === "Success" || a.status === "Approved" ? "badge-green" : a.status === "Failed" || a.status === "Rejected" ? "badge-red" : "badge-blue"}`}>{a.status}</span></td>
                    <td>{a.target}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassCard>
      )}
    </div>
  );
}
