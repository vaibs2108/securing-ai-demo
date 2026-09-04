import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { GlassCard, Badge } from "./ui";

/** Lives on Protect's Guardrail Proxy stage — real middleware, not a batch
 * test. Free-text: a fixed script replayed against the same known-flagged
 * prompts would always produce the same result and prove nothing new each
 * run. Any prompt sent here actually flows through the real pipeline —
 * Lakera screens it, a flagged one never reaches the real target agent, a
 * clear one does and its real reply gets screened too — and every real
 * outcome appends a real row to guardrail_events (Protect's own Output tab,
 * previously permanently empty). */
export function LakeraTestPanel({ onSent }: { onSent?: () => void }) {
  const promptsQ = useQuery({ queryKey: ["security-tools-test-prompts"], queryFn: api.securityToolsTestPrompts });
  const [prompt, setPrompt] = useState("");
  const qc = useQueryClient();
  const chatMut = useMutation({
    mutationFn: (p: string) => api.guardrailProxyChat(p),
    // Every real call here appends a real guardrail_events row and
    // recomputes KPIs server-side (Guardrail Block Rate especially) — the
    // Dashboard/StoryBar should reflect that immediately, not on next poll.
    // onSent silently re-runs this stage so Output & Handoff (a snapshot
    // from the last Execute AI Analysis run, not a live query) picks up
    // the new row too, without requiring a second manual click.
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      onSent?.();
    },
  });

  const prompts = promptsQ.data?.prompts ?? [];

  return (
    <GlassCard style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <span className="section-title" style={{ margin: 0 }}>🛡️ Real Guardrail Proxy — try it live</span>
        <Badge variant="green">🟢 Live</Badge>
      </div>
      <p className="muted" style={{ fontSize: "0.8rem", marginBottom: 12 }}>
        Pick a prompt below and send it. Lakera Guard screens it in real time — a flagged prompt never reaches the
        target agent; a clear one does, and its reply gets screened too.
      </p>

      <label className="field-label">Quick real examples (or write your own below)</label>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        {prompts.map((p) => {
          const isEvasion = p.prompt_id === "PROMPT-004";
          return (
            <button
              key={p.prompt_id}
              type="button"
              onClick={() => { setPrompt(p.payload); chatMut.reset(); }}
              style={{
                all: "unset", cursor: "pointer", padding: "6px 10px", borderRadius: 8,
                background: isEvasion ? "rgba(255, 170, 0, 0.12)" : "rgba(var(--overlay-rgb), 0.03)",
                border: `1px solid ${isEvasion ? "var(--accent-amber)" : "var(--border-glass)"}`,
                fontSize: "0.74rem", fontWeight: 700,
                color: isEvasion ? "var(--accent-amber)" : "var(--text-heading)",
              }}
            >
              {isEvasion ? `🎯 ${p.category}` : p.category}
            </button>
          );
        })}
      </div>

      <label className="field-label">Prompt to send through the real proxy</label>
      <textarea
        rows={3}
        value={prompt}
        onChange={(e) => { setPrompt(e.target.value); }}
        placeholder="Type anything — a real jailbreak attempt, a benign question, whatever you want to actually test…"
        style={{ marginBottom: 10, width: "100%", boxSizing: "border-box" }}
      />

      <button
        className="btn btn-secondary"
        disabled={!prompt.trim() || chatMut.isPending}
        onClick={() => chatMut.mutate(prompt.trim())}
      >
        {chatMut.isPending ? "Sending through the real proxy…" : "▶ Send through the Guardrail Proxy"}
      </button>

      {chatMut.data && (
        <div
          style={{
            marginTop: 12, padding: "10px 12px", borderRadius: 8,
            background: chatMut.data.canary_leaked ? "rgba(255,68,68,0.12)" : chatMut.data.blocked ? "rgba(255,68,68,0.08)" : "rgba(0,255,136,0.06)",
            border: `1px solid ${chatMut.data.canary_leaked || chatMut.data.blocked ? "var(--accent-red)" : "var(--accent-green)"}33`,
          }}
        >
          <div style={{ fontWeight: 700, fontSize: "0.85rem", color: chatMut.data.canary_leaked || chatMut.data.blocked ? "var(--accent-red)" : "var(--accent-green)" }}>
            {chatMut.data.canary_leaked
              ? "⚠️ EXFILTRATION DETECTED — Input screening bypassed, secret leaked"
              : chatMut.data.blocked
              ? chatMut.data.blocked_at === "input"
                ? "🚫 Blocked at input — never reached the real target agent"
                : "🚫 Blocked at output — real agent replied, but the reply was withheld"
              : "✅ Allowed — real reply below"}
          </div>

          {chatMut.data.lakera_input && (
            <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 6 }}>
              Real Lakera input verdict: {chatMut.data.lakera_input.flagged ? "flagged (blocked)" : "clear (allowed through)"}
              {chatMut.data.lakera_input.raw?.metadata?.request_uuid && ` (request_uuid: ${chatMut.data.lakera_input.raw.metadata.request_uuid})`}
            </div>
          )}
          {chatMut.data.lakera_output && (
            <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 2 }}>
              Real Lakera output verdict: {chatMut.data.lakera_output.flagged ? "flagged" : "clear"}
              {chatMut.data.lakera_output.raw?.metadata?.request_uuid && ` (request_uuid: ${chatMut.data.lakera_output.raw.metadata.request_uuid})`}
            </div>
          )}

          {chatMut.data.reply && (
            <div style={{ background: "var(--bg-secondary)", borderRadius: 8, padding: 8, fontSize: "0.78rem", marginTop: 8 }}>
              {chatMut.data.reply}
            </div>
          )}

          {chatMut.data.canary_leaked ? (
            <div
              style={{
                marginTop: 8, padding: "8px 10px", borderRadius: 6,
                background: "rgba(255, 68, 68, 0.15)", border: "1px solid var(--accent-red)",
                color: "var(--accent-red)", fontSize: "0.74rem",
              }}
            >
              <strong>Live Security Breach (AML.T0051):</strong> The prompt bypassed input screening via evasion and extracted the confidential credential (<code>ghp_Uh9...</code>) using MITRE ATLAS technique <strong>AML.T0051 (LLM Prompt Injection)</strong>. This is the exact same attack vector evaluated in Detect and remediated in Respond/Recover.
            </div>
          ) : chatMut.data.model_leaked_raw ? (
            <div style={{ fontSize: "0.72rem", color: "var(--accent-amber)", marginTop: 8 }}>
              🎯 The real target agent's underlying model actually generated the confidential credential for this
              prompt — a genuine jailbreak at the model level. {chatMut.data.blocked
                ? "This proxy's own Lakera screen is what kept it from reaching you."
                : "The target's own output guardrail already substituted it before this proxy even saw the reply."}
            </div>
          ) : null}

          <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: 8, fontFamily: "JetBrains Mono, monospace" }}>
            real event logged: {chatMut.data.event.event_id} · {chatMut.data.event.action_taken} · see Output & Handoff below
          </div>
        </div>
      )}
      {chatMut.isError && <p style={{ fontSize: "0.78rem", color: "var(--accent-red)", marginTop: 10 }}>Couldn't reach the real guardrail proxy. Try again.</p>}
    </GlassCard>
  );
}
