import type { AgentOutcome, AttackRow } from "../lib/types";

const SOURCE_KEYS = ["garak_live_scan", "pyrit_live_scan", "adversarial_prompt_corpus"] as const;

export function getAttackRows(outcome?: AgentOutcome): AttackRow[] {
  if (!outcome?.aggregation) return [];
  for (const key of SOURCE_KEYS) {
    const rows = outcome.aggregation[key]?.rows;
    if (rows && rows.length > 0) return rows as AttackRow[];
  }
  return [];
}

function sourceLabel(row: AttackRow): string {
  if (row.probe?.startsWith("garak")) return "garak · " + row.probe.replace("garak.jailbreak.", "").replace("dan.", "");
  if (row.probe?.startsWith("pyrit")) return "pyrit · " + row.probe.replace("pyrit.jailbreak.", "");
  return row.category ?? "live probe";
}

/** Three real, distinct outcomes, not one flattened leaked/blocked bool:
 * - canary_leaked: the secret actually reached the caller (worst case).
 * - model_leaked_raw (and not canary_leaked): the real model complied and
 *   generated the secret internally — the jailbreak genuinely worked
 *   against the model — but the target agent's own output guardrail caught
 *   it before it went out. This is the "we really did jailbreak this
 *   model" evidence, safe to show because the actual secret text is never
 *   part of model_leaked_raw, only the fact that it happened.
 * - neither: the model refused the jailbreak on its own; the guardrail
 *   was never even needed. */
function outcomeLabel(row: AttackRow): { text: string; color: string; bg: string } {
  if (row.canary_leaked) return { text: "⚠️ leaked", color: "var(--accent-red)", bg: "rgba(255,68,68,0.12)" };
  if (row.model_leaked_raw) return { text: "🎯 jailbreak succeeded · 🛡️ guardrail caught it", color: "var(--accent-amber)", bg: "rgba(255,170,0,0.1)" };
  return { text: "🧠 model refused on its own", color: "var(--accent-green)", bg: "rgba(0,255,136,0.08)" };
}

export function AttackExchange({ rows }: { rows: AttackRow[] }) {
  return (
    <div style={{ background: "var(--surface-1, rgba(255,255,255,0.03))", borderRadius: 12, padding: "14px 16px", display: "flex", flexDirection: "column", gap: 10, marginBottom: 16 }}>
      {rows.map((row, i) => {
        const promptText = row.prompt ?? row.payload ?? "";
        const responseText = row.response_snippet ?? "";
        const outcome = outcomeLabel(row);
        return (
          <div key={i} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", gap: 8, maxWidth: "88%" }}>
              <span style={{ fontSize: "1rem" }}>🐛</span>
              <div style={{ background: "var(--bg-secondary)", borderRadius: "4px 12px 12px 12px", padding: "8px 12px" }}>
                <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", marginBottom: 3 }}>{sourceLabel(row)}</div>
                <div style={{ fontSize: "0.8rem" }}>{promptText.length > 220 ? promptText.slice(0, 220) + "…" : promptText}</div>
              </div>
            </div>
            {responseText && (
              <div style={{ display: "flex", gap: 8, maxWidth: "88%", alignSelf: "flex-end", flexDirection: "row-reverse" }}>
                <span style={{ fontSize: "1rem" }}>🤖</span>
                <div style={{
                  background: outcome.bg,
                  border: `1px solid ${outcome.color}33`,
                  borderRadius: "12px 4px 12px 12px", padding: "8px 12px",
                }}>
                  <div style={{ fontSize: "0.65rem", color: outcome.color, marginBottom: 3, textAlign: "right", fontWeight: 600 }}>
                    meridian agent · {outcome.text}
                  </div>
                  <div style={{ fontSize: "0.8rem" }}>{responseText.length > 260 ? responseText.slice(0, 260) + "…" : responseText}</div>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
