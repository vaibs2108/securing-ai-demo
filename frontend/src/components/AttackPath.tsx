import type { AttackRow } from "../lib/types";

export function AttackPath({ rows }: { rows: AttackRow[] }) {
  const anyLeaked = rows.some((r) => r.canary_leaked);
  const technique = rows.find((r) => r.mitre_atlas_ref)?.mitre_atlas_ref ?? "AML.T0051 — LLM Prompt Injection";

  const steps = [
    { icon: "📤", label: "Real injection sent", detail: technique.includes("AML.T0051") ? "AML.T0051 · Prompt Injection" : technique, color: "var(--text-secondary)" },
    { icon: "🛡️", label: "Guardrail check", detail: "none deployed (raw test)", color: "var(--accent-amber)" },
    { icon: "🤖", label: "Model response", detail: `${rows.length} real attempt(s)`, color: "var(--text-secondary)" },
    anyLeaked
      ? { icon: "⚠️", label: "Credential leaked", detail: "canary ghp_Uh9... (AML.T0051)", color: "var(--accent-red)" }
      : { icon: "✅", label: "No leak", detail: "fix held", color: "var(--accent-green)" },
  ];

  return (
    <div style={{ display: "flex", alignItems: "center", background: "var(--surface-1, rgba(255,255,255,0.03))", borderRadius: 12, padding: "12px 16px", marginBottom: 12, overflowX: "auto" }}>
      {steps.map((s, i) => (
        <div key={s.label} style={{ display: "flex", alignItems: "center", flex: "0 0 auto" }}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2, minWidth: 110 }}>
            <span style={{ fontSize: "1.1rem" }}>{s.icon}</span>
            <span style={{ fontSize: "0.72rem", fontWeight: 600 }}>{s.label}</span>
            <span style={{ fontSize: "0.65rem", color: s.color }}>{s.detail}</span>
          </div>
          {i < steps.length - 1 && <span style={{ color: "var(--text-muted)", margin: "0 8px", fontSize: "1rem" }}>→</span>}
        </div>
      ))}
    </div>
  );
}
