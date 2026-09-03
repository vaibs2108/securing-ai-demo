import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { GlassCard, LoadingBlock } from "../components/ui";
import { useTheme } from "../context/ThemeContext";
import { readableAccent } from "../lib/color";

const PHASE_ORDER = ["identify", "protect", "detect", "govern", "respond", "recover"] as const;
const PHASE_LABELS: Record<string, string> = {
  identify: "🔎 Identify", protect: "🛡️ Protect", detect: "🚨 Detect", respond: "🚑 Respond", recover: "♻️ Recover", govern: "🏛️ Govern",
};

export function AgentsPage() {
  const { data, isLoading } = useQuery({ queryKey: ["agents"], queryFn: api.agents });
  const [phase, setPhase] = useState<string>("identify");
  const { theme } = useTheme();

  if (isLoading || !data) return <LoadingBlock label="Loading agent catalogue…" />;

  const totalAgents = PHASE_ORDER.reduce((n, uc) => n + (data[uc]?.agents.length ?? 0), 0);
  const phaseInfo = data[phase];

  return (
    <div>
      <div className="hero-banner">
        <div className="hero-title">🤖 Agents Repository</div>
        <div className="hero-subtitle">{totalAgents} specialised security agents across the 6 NIST CSF phases</div>
      </div>

      <div className="top-tabs">
        {PHASE_ORDER.map((uc) => (
          <span key={uc} className={`top-tab${phase === uc ? " active" : ""}`} onClick={() => setPhase(uc)}>{PHASE_LABELS[uc]}</span>
        ))}
      </div>

      {phaseInfo && (
        <>
          <p className="muted" style={{ marginBottom: 16 }}>Frameworks: {phaseInfo.framework}</p>
          <div className="grid-2">
            {phaseInfo.agents.map((a) => (
              <GlassCard key={a.name} accent={phaseInfo.color}>
                <div style={{ fontWeight: 700, fontSize: "1.05rem", color: readableAccent(phaseInfo.color, theme) }}>{a.name}</div>
                <div className="muted" style={{ fontSize: "0.78rem", marginBottom: 8 }}>{a.stage}</div>
                <p style={{ fontSize: "0.88rem", color: "var(--text-secondary)" }}>{a.role}</p>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>MITRE ATLAS: {a.mitre_ref}</div>
              </GlassCard>
            ))}
          </div>

          <p className="muted" style={{ fontSize: "0.8rem", marginTop: 12 }}>
            To actually run one of these agents, open its phase from the sidebar and hit{" "}
            <strong>Execute AI Analysis</strong> on the matching stage — that calls the real LLM pipeline against
            live dataset context, not a canned response.
          </p>
        </>
      )}
    </div>
  );
}
