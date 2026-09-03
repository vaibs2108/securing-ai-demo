import { useMemo, useState } from "react";
import { GlassCard, Badge } from "./ui";
import type { AssetGraphData, AssetGraphNode, AssetGraphEdge } from "../lib/types";

const TYPE_COLOR: Record<string, string> = {
  agent: "#00d4ff",
  model: "#a855f7",
  identity: "#f5b700",
  secret: "#ff4444",
  policy: "#14b8a6",
};

const TYPE_LABEL: Record<string, string> = {
  agent: "🤖 Agent",
  model: "🧠 Model",
  identity: "🔑 Identity / Access",
  secret: "🔓 Secret Finding",
  policy: "🏛️ Policy Rule",
};

const SECTION_ORDER: AssetGraphNode["type"][] = ["model", "identity", "policy", "secret"];
const SECTION_TITLE: Record<string, string> = {
  model: "🧠 Models this agent runs on",
  identity: "🔑 Access this agent holds",
  policy: "🏛️ Governance rules evaluated",
  secret: "🔓 Secrets this agent touches",
};

const BLAST_COLOR: Record<string, string> = {
  Critical: "#ff2222",
  High: "#ff4444",
  Medium: "#f5b700",
  Low: "#00ff88",
};

/** A real, plain-English read-out of this graph's actual node/edge data —
 * every clause below is derived straight from real fields the backend
 * already returns (app/main.py's /api/asset-graph), never invented. */
function buildNarrative(nodes: AssetGraphNode[]): string | null {
  const agent = nodes.find((n) => n.type === "agent");
  if (!agent) return null;

  const models = nodes.filter((n) => n.type === "model");
  const identities = nodes.filter((n) => n.type === "identity");
  const secrets = nodes.filter((n) => n.type === "secret");
  const criticalSecrets = secrets.filter((n) => n.critical);
  const policies = nodes.filter((n) => n.type === "policy");
  const triggered = policies.filter((n) => n.triggered);

  const parts: string[] = [];
  parts.push(
    `${agent.label} (risk ${agent.risk_score ?? "—"} · ${agent.blast_radius ?? "unscored"}) is powered by ${models.length || "no"} real model${models.length === 1 ? "" : "s"}`
    + (identities.length > 0 ? `, and holds ${identities.map((i) => i.detail?.replace(" access", "") || i.label).join(", ")} access` : "") + "."
  );
  if (secrets.length > 0) {
    parts.push(
      criticalSecrets.length > 0
        ? `${criticalSecrets.length} of ${secrets.length} real secret finding${secrets.length === 1 ? "" : "s"} ${criticalSecrets.length === 1 ? "is" : "are"} exposed and not isolated.`
        : `All ${secrets.length} real secret finding${secrets.length === 1 ? "" : "s"} checked ${secrets.length === 1 ? "is" : "are"} properly isolated.`
    );
  }
  if (policies.length > 0) {
    const passCount = policies.length - triggered.length;
    parts.push(
      triggered.length > 0
        ? `${passCount}/${policies.length} governance rules pass — ${triggered.map((p) => p.label).join(", ")} triggered a real "${triggered[0].decision}" decision.`
        : `All ${policies.length}/${policies.length} governance rules pass.`
    );
  }
  return parts.join(" ");
}

function Chip({ node, edge, active, onClick }: { node: AssetGraphNode; edge?: AssetGraphEdge; active: boolean; onClick: () => void }) {
  const critical = node.critical || edge?.critical;
  const color = node.type === "policy" ? (node.triggered ? "#ff4444" : "#14b8a6") : TYPE_COLOR[node.type];
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        all: "unset",
        cursor: "pointer",
        display: "flex",
        flexDirection: "column",
        gap: 3,
        minWidth: 150,
        maxWidth: 220,
        padding: "8px 12px",
        borderRadius: 8,
        background: active ? "rgba(var(--overlay-rgb), 0.08)" : "rgba(var(--overlay-rgb), 0.03)",
        border: `1px solid ${active ? color : "var(--border-glass)"}`,
        borderLeft: `3px solid ${color}`,
      }}
    >
      <span style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-heading)" }}>{node.label}</span>
      {edge && <span style={{ fontSize: "0.68rem", color: critical ? "#ff4444" : "var(--text-muted)", fontWeight: critical ? 700 : 400 }}>{edge.label}</span>}
      {node.detail && <span style={{ fontSize: "0.68rem", color: "var(--text-secondary)" }}>{node.detail}</span>}
    </button>
  );
}

export function AssetGraph({ data }: { data: AssetGraphData }) {
  const nodes = data.nodes ?? [];
  const agent = nodes.find((n) => n.type === "agent") ?? null;
  const edgesByFrom = useMemo(() => {
    const m: Record<string, AssetGraphEdge> = {};
    (data.edges ?? []).forEach((e) => { m[e.from] = e; });
    return m;
  }, [data]);

  // Default selection: surface the most consequential real node first
  // (an exposed secret, else a triggered policy, else the agent itself)
  // instead of leaving the detail panel empty until someone clicks.
  const defaultSelected = useMemo<AssetGraphNode | null>(() => {
    return (
      nodes.find((n) => n.type === "secret" && n.critical) ??
      nodes.find((n) => n.type === "policy" && n.triggered) ??
      agent ??
      nodes[0] ??
      null
    );
  }, [data]);
  const [selected, setSelected] = useState<AssetGraphNode | null>(defaultSelected);
  const active = selected ?? defaultSelected;

  const narrative = useMemo(() => buildNarrative(nodes), [data]);
  const sections = SECTION_ORDER.map((t) => ({ type: t, items: nodes.filter((n) => n.type === t) })).filter((s) => s.items.length > 0);

  return (
    <div className="grid-2" style={{ gridTemplateColumns: "1fr 320px", gap: 16, alignItems: "start" }}>
      <GlassCard>
        {narrative && (
          <div style={{ fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.5, marginBottom: 14, paddingBottom: 14, borderBottom: "1px solid var(--border-glass)" }}>
            <span style={{ fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-muted)", marginRight: 6 }}>Read:</span>
            {narrative}
          </div>
        )}

        {agent && (
          <button
            type="button"
            onClick={() => setSelected(agent)}
            style={{
              all: "unset", cursor: "pointer", display: "flex", alignItems: "center", gap: 12,
              padding: "12px 16px", borderRadius: 10, marginBottom: 18, width: "100%", boxSizing: "border-box",
              background: `${BLAST_COLOR[agent.blast_radius ?? ""] ?? TYPE_COLOR.agent}18`,
              border: `1px solid ${active?.id === agent.id ? (BLAST_COLOR[agent.blast_radius ?? ""] ?? TYPE_COLOR.agent) : "var(--border-glass)"}`,
            }}
          >
            <span style={{ fontSize: "1.6rem" }}>🤖</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: "0.95rem", color: "var(--text-heading)" }}>{agent.label}</div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>{agent.detail}</div>
            </div>
            <Badge variant={agent.blast_radius === "Critical" || agent.blast_radius === "High" ? "red" : agent.blast_radius === "Medium" ? "amber" : "green"}>
              risk {agent.risk_score ?? "—"} · {agent.blast_radius ?? "—"}
            </Badge>
          </button>
        )}

        {sections.map((section) => (
          <div key={section.type} style={{ marginBottom: 16 }}>
            <div style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-muted)", fontWeight: 700, marginBottom: 8 }}>
              {SECTION_TITLE[section.type]}
            </div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              {section.items.map((n) => (
                <Chip key={n.id} node={n} edge={edgesByFrom[n.id]} active={active?.id === n.id} onClick={() => setSelected(n)} />
              ))}
            </div>
          </div>
        ))}

        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 4, paddingTop: 12, borderTop: "1px solid var(--border-glass)", fontSize: "0.72rem", color: "var(--text-muted)" }}>
          {Object.entries(TYPE_LABEL).map(([k, label]) => (
            <div key={k} style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 9, height: 9, borderRadius: "50%", background: TYPE_COLOR[k], display: "inline-block" }} />
              {label}
            </div>
          ))}
        </div>
      </GlassCard>

      <GlassCard>
        <div className="section-title" style={{ marginBottom: 10 }}>
          {active ? active.label : "Select a node"}
        </div>
        {!active && (
          <p className="muted" style={{ fontSize: "0.82rem" }}>
            Click any card to see its real detail — every field here traces back to a real dataset row, not a
            placeholder.
          </p>
        )}
        {active && (
          <div style={{ fontSize: "0.85rem", display: "flex", flexDirection: "column", gap: 10 }}>
            <div><Badge variant="blue">{TYPE_LABEL[active.type]}</Badge></div>
            {active.detail && <div style={{ color: "var(--text-secondary)" }}>{active.detail}</div>}
            {active.risk_score !== undefined && active.risk_score !== null && (
              <div><strong>Risk score:</strong> {active.risk_score} ({active.blast_radius})</div>
            )}
            {active.internet_facing !== undefined && (
              <div><strong>Internet-facing:</strong> {active.internet_facing ? "Yes" : "No"}</div>
            )}
            {active.decision && (
              <div>
                <strong>Compliance decision:</strong>{" "}
                <Badge variant={active.triggered ? "red" : "green"}>{active.decision}</Badge>
              </div>
            )}
            {active.critical && <div style={{ color: "var(--accent-red)", fontWeight: 700 }}>⚠️ Flagged as critical</div>}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
