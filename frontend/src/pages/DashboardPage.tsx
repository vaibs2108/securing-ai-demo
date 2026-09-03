import { useQuery } from "@tanstack/react-query";
import { CartesianGrid, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Cell, Legend } from "recharts";
import { api } from "../lib/api";
import { GlassCard, Gauge, KpiProgressCard, LoadingBlock } from "../components/ui";
import { AssetGraph } from "../components/AssetGraph";
import { PHASE_KPI_GROUPS, kpiStatus } from "../lib/kpiMeta";

const PHASE_ORDER = ["identify", "protect", "detect", "govern", "respond", "recover"] as const;
const PHASE_LABELS: Record<string, string> = {
  identify: "Identify", protect: "Protect", detect: "Detect", respond: "Respond", recover: "Recover", govern: "Govern",
};
const BLAST_COLORS: Record<string, string> = { Critical: "#ff2222", High: "var(--accent-red)", Medium: "var(--accent-amber)", Low: "var(--accent-blue)" };

export function DashboardPage() {
  const { data, isLoading } = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard });
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 30_000 });
  const { data: mcpTools } = useQuery({ queryKey: ["mcp-tools"], queryFn: api.mcpTools, staleTime: 30_000 });
  const { data: assetGraph } = useQuery({ queryKey: ["asset-graph"], queryFn: api.assetGraph, staleTime: 15_000 });

  if (isLoading || !data) return <LoadingBlock label="Loading dashboard…" />;

  const toolByName: Record<string, boolean> = {};
  if (mcpTools) {
    for (const tools of Object.values(mcpTools)) {
      for (const t of tools) toolByName[t.name] = t.live;
    }
  }
  // One canonical list of every real connected system this demo depends on
  // — deliberately a single strip, not split across multiple Dashboard
  // sections, after Garak/PyRIT status previously appeared twice (here and
  // in a since-removed second panel) and read as duplicated/inconsistent.
  // `dashboard` gates the loading screen below, but `settings`/`mcpTools`
  // are separate queries that can still be in flight on first paint — was
  // rendering a real false-negative "not configured"/"not live" flash for
  // every chip here on a fresh navigation, before those two caught up.
  // `settingsLoaded`/`toolsLoaded` distinguish "still checking" (neutral)
  // from a genuine "not configured" (only knowable once the query has
  // actually returned).
  const settingsLoaded = settings !== undefined;
  const toolsLoaded = mcpTools !== undefined;
  const liveSystems = [
    { icon: "🐙", label: "GitHub", detail: !settingsLoaded ? "checking…" : settings?.github_target_repo || "not configured", live: !!settings?.github_target_repo, loading: !settingsLoaded },
    {
      icon: "🤖", label: "Target agent",
      detail: !settingsLoaded ? "checking…" : !settings?.target_agent_url ? "not configured" : settings.target_agent_disabled ? `${settings.target_agent_url} (suspended)` : settings.target_agent_url,
      live: !!settings?.target_agent_reachable,
      loading: !settingsLoaded,
    },
    { icon: "💬", label: "Slack", detail: !toolsLoaded ? "checking…" : toolByName.slack ? "connected" : "not live", live: !!toolByName.slack, loading: !toolsLoaded },
    { icon: "🛡️", label: "Lakera Guard", detail: !toolsLoaded ? "checking…" : toolByName.lakera_guard ? "live scanner" : "mock fallback", live: !!toolByName.lakera_guard, loading: !toolsLoaded },
    { icon: "🐛", label: "Garak", detail: !toolsLoaded ? "checking…" : toolByName.garak ? "live scanner" : "mock fallback", live: !!toolByName.garak, loading: !toolsLoaded },
    { icon: "🎯", label: "PyRIT", detail: !toolsLoaded ? "checking…" : toolByName.pyrit ? "live scanner" : "mock fallback", live: !!toolByName.pyrit, loading: !toolsLoaded },
    {
      icon: "🧠", label: "LLM",
      detail: !settingsLoaded ? "checking…" : settings?.llm_model_info?.primary ? settings.llm_model_info.primary.model : "not configured",
      live: settings?.llm_model_info?.primary?.status === "available",
      loading: !settingsLoaded,
    },
  ];

  // Real recorded snapshots (one per calendar day the app was actually used),
  // not padded to a fixed 30 points — see app/observability/score_history.py.
  const allDays = Array.from(new Set(PHASE_ORDER.flatMap((uc) => (data.trend[uc] ?? []).map((p) => p.day)))).sort();
  const trendData = allDays.map((day) => {
    const row: Record<string, number | string> = { day };
    for (const uc of PHASE_ORDER) {
      const point = data.trend[uc]?.find((p) => p.day === day);
      if (point) row[uc] = point.score;
    }
    return row;
  });

  const blastData = Object.entries(data.blast_radius).map(([name, value]) => ({ name, value }));

  return (
    <div>
      <div className="hero-banner">
        <div className="hero-title">AI Security Command Center</div>
        <div className="hero-subtitle">Live posture across the NIST CSF 2.0 lifecycle — Identify, Protect, Detect, Govern, Respond, Recover</div>
      </div>

      <div className="grid-3" style={{ gridTemplateColumns: "repeat(7, 1fr)", gap: 10, marginBottom: 16 }}>
        {liveSystems.map((s) => (
          <GlassCard key={s.label}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
              <span>{s.icon}</span>
              <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{s.label}</span>
            </div>
            <div style={{ fontSize: "0.78rem", fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.detail}</div>
            <div style={{ fontSize: "0.68rem", color: s.loading ? "var(--text-muted)" : s.live ? "var(--accent-green)" : "var(--text-muted)", marginTop: 2 }}>
              {s.loading ? "○ checking…" : s.live ? "● connected" : "○ not live"}
            </div>
          </GlassCard>
        ))}
      </div>

      <div className="grid-3" style={{ gridTemplateColumns: "repeat(6, 1fr)", marginBottom: 8 }}>
        {data.gauges.map((g) => (
          <GlassCard key={g.phase} accent={g.color}>
            <Gauge score={g.score} title={g.label.replace(/^[^\s]+\s/, "")} color={g.color} />
          </GlassCard>
        ))}
      </div>

      <div className="section-title" style={{ marginTop: 24 }}>AI asset &amp; risk graph</div>
      <p className="muted" style={{ fontSize: "0.8rem", marginBottom: 12 }}>
        Every real entity flowing through the pipeline right now, in one connective view.{" "}
        <a href="/asset-graph">Open full screen →</a>
      </p>
      {assetGraph ? <AssetGraph data={assetGraph} /> : <LoadingBlock label="Assembling the real asset graph…" />}

      <div className="section-title" style={{ marginTop: 24 }}>Operational Performance Index</div>
      <div className="grid-3" style={{ marginBottom: 8 }}>
        {data.operational.map((o) => (
          <KpiProgressCard key={o.label} label={o.label} value={o.value} colour={o.color} />
        ))}
      </div>

      <div className="section-title" style={{ marginTop: 24 }}>Operational KPIs &amp; Technical Performance</div>
      <div className="grid-2">
        {PHASE_ORDER.map((uc) => (
          <GlassCard key={uc} accent={data.gauges.find((g) => g.phase === uc)?.color}>
            <div style={{ fontWeight: 700, marginBottom: 10 }}>{PHASE_LABELS[uc]}</div>
            <table className="data-table" style={{ width: "100%" }}>
              <tbody>
                {PHASE_KPI_GROUPS[uc].map((meta) => {
                  const value = data.kpis[meta.name];
                  const status = kpiStatus(meta, value);
                  return (
                    <tr key={meta.name}>
                      <td style={{ color: "var(--text-secondary)" }}>{meta.name}</td>
                      <td style={{ textAlign: "right", fontWeight: 700 }}>{value?.toFixed(1)}{meta.unit}</td>
                      <td style={{ textAlign: "right" }}>
                        <span className="badge" style={{ background: `color-mix(in srgb, ${status.colour} 13%, transparent)`, color: status.colour, border: `1px solid color-mix(in srgb, ${status.colour} 33%, transparent)` }}>
                          {status.label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </GlassCard>
        ))}
      </div>

      <div className="grid-2" style={{ marginTop: 24 }}>
        <GlassCard accent="var(--accent-blue)">
          <div className="section-title">Score History</div>
          <p className="muted" style={{ fontSize: "0.75rem", marginBottom: 10 }}>
            {trendData.length <= 1
              ? "First recorded snapshot — real history builds up as this app is used across more days."
              : `${trendData.length} days of recorded posture scores.`}
          </p>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={trendData}>
              <CartesianGrid stroke="rgba(var(--overlay-rgb), 0.08)" />
              <XAxis dataKey="day" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <YAxis domain={[0, 100]} tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <Tooltip contentStyle={{ background: "var(--bg-secondary)", border: "1px solid var(--border-glass)", borderRadius: 8 }} labelStyle={{ color: "var(--text-primary)" }} itemStyle={{ color: "var(--text-primary)" }} />
              <Legend wrapperStyle={{ fontSize: 11, color: "var(--text-secondary)" }} />
              {PHASE_ORDER.map((uc) => (
                <Line key={uc} type="monotone" dataKey={uc} name={PHASE_LABELS[uc]} stroke={data.gauges.find((g) => g.phase === uc)?.color} strokeWidth={2} dot={{ r: 3 }} connectNulls />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </GlassCard>

        <GlassCard accent="var(--accent-red)">
          <div className="section-title">Agent Risk Blast-Radius Profile</div>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={blastData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={2}>
                {blastData.map((d) => <Cell key={d.name} fill={BLAST_COLORS[d.name] ?? "var(--accent-blue)"} />)}
              </Pie>
              <Tooltip contentStyle={{ background: "var(--bg-secondary)", border: "1px solid var(--border-glass)", borderRadius: 8 }} labelStyle={{ color: "var(--text-primary)" }} itemStyle={{ color: "var(--text-primary)" }} />
              <Legend wrapperStyle={{ fontSize: 11, color: "var(--text-secondary)" }} />
            </PieChart>
          </ResponsiveContainer>
        </GlassCard>
      </div>

      <div className="section-title" style={{ marginTop: 24 }}>Recent AI Operations &amp; HITL Actions</div>
      <GlassCard>
        <div className="data-table-wrap">
          <table className="data-table">
            <thead><tr><th>Timestamp</th><th>Action</th><th>User</th><th>Status</th><th>Target</th><th>Details</th></tr></thead>
            <tbody>
              {data.recent_operations.map((op, i) => (
                <tr key={i}>
                  <td>{op.timestamp}</td>
                  <td>{op.action}</td>
                  <td>{op.username}</td>
                  <td>{op.status}</td>
                  <td>{op.target}</td>
                  <td style={{ whiteSpace: "normal", maxWidth: 400 }}>{op.details}</td>
                </tr>
              ))}
              {data.recent_operations.length === 0 && (
                <tr><td colSpan={6} className="muted">No operations recorded yet — execute a stage to populate the audit trail.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  );
}
