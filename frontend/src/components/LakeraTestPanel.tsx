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
export function LakeraTestPanel() {
  const promptsQ = useQuery({ queryKey: ["security-tools-test-prompts"], queryFn: api.securityToolsTestPrompts });
  const [prompt, setPrompt] = useState("");
  const qc = useQueryClient();
  const chatMut = useMutation({
    mutationFn: (p: string) => api.guardrailProxyChat(p),
    // Every real call here appends a real guardrail_events row and
    // recomputes KPIs server-side (Guardrail Block Rate especially) — the
    // Dashboard/StoryBar should reflect that immediately, not on next poll.
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboard"] }),
  });

  const prompts = promptsQ.data?.prompts ?? [];

  return (
    <GlassCard style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <span className="section-title" style={{ margin: 0 }}>🛡️ Real Guardrail Proxy — try anything</span>
        <Badge variant="green">🟢 Live</Badge>
      </div>
      <p className="muted" style={{ fontSize: "0.8rem", marginBottom: 10 }}>
        This is real middleware, not a screening demo — type any prompt. Lakera Guard screens it first; if flagged,
        the real target agent is never even called. If it's clear, your prompt is really forwarded, the real reply
        comes back, and that reply is screened too before you see it. Every real outcome logs a real row below in
        Guardrail Proxy Event Stream — that dataset stops being empty starting now.
      </p>
      <div style={{ background: "rgba(var(--overlay-rgb), 0.04)", borderRadius: 8, padding: "8px 10px", marginBottom: 14, fontSize: "0.76rem", color: "var(--text-secondary)" }}>
        💡 <strong>Only traffic sent through here is protected.</strong> Detect's real attacks deliberately go
        straight to the target agent, bypassing this proxy, to measure raw exposure — see Detect →
        Live Jailbreak &amp; Injection Detection for that real, separate result.
        <br />
        <strong>Lakera's real role:</strong> a pattern classifier, not a secret-matcher — it recognizes jailbreak/
        injection techniques and sensitive-content categories generally, independent of the target agent's own
        narrow deterministic filter (which only catches one exact leaked string). Two different, complementary real
        layers, not the same check twice.
      </div>

      <label className="field-label">Quick real examples (or write your own below)</label>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        {prompts.map((p) => (
          <button
            key={p.prompt_id}
            type="button"
            onClick={() => { setPrompt(p.payload); chatMut.reset(); }}
            style={{
              all: "unset", cursor: "pointer", padding: "6px 10px", borderRadius: 8,
              background: "rgba(var(--overlay-rgb), 0.03)", border: "1px solid var(--border-glass)",
              fontSize: "0.74rem", fontWeight: 700, color: "var(--text-heading)",
            }}
          >
            {p.category}
          </button>
        ))}
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
            background: chatMut.data.blocked ? "rgba(255,68,68,0.08)" : "rgba(0,255,136,0.06)",
            border: `1px solid ${chatMut.data.blocked ? "var(--accent-red)" : "var(--accent-green)"}33`,
          }}
        >
          <div style={{ fontWeight: 700, fontSize: "0.85rem", color: chatMut.data.blocked ? "var(--accent-red)" : "var(--accent-green)" }}>
            {chatMut.data.blocked
              ? chatMut.data.blocked_at === "input"
                ? "🚫 Blocked at input — never reached the real target agent"
                : "🚫 Blocked at output — real agent replied, but the reply was withheld"
              : "✅ Allowed — real reply below"}
          </div>

          {chatMut.data.lakera_input && (
            <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 6 }}>
              Real Lakera input verdict: {chatMut.data.lakera_input.flagged ? "flagged" : "clear"}
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

          {chatMut.data.model_leaked_raw && (
            <div style={{ fontSize: "0.72rem", color: "var(--accent-amber)", marginTop: 8 }}>
              🎯 The real target agent's underlying model actually generated the confidential credential for this
              prompt — a genuine jailbreak at the model level. {chatMut.data.blocked
                ? "This proxy's own Lakera screen is what kept it from reaching you."
                : "The target's own output guardrail already substituted it before this proxy even saw the reply."}
            </div>
          )}

          <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: 8, fontFamily: "JetBrains Mono, monospace" }}>
            real event logged: {chatMut.data.event.event_id} · {chatMut.data.event.action_taken} · see Output & Handoff below
          </div>
        </div>
      )}
      {chatMut.isError && <p style={{ fontSize: "0.78rem", color: "var(--accent-red)", marginTop: 10 }}>Couldn't reach the real guardrail proxy. Try again.</p>}
    </GlassCard>
  );
}
