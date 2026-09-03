import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge } from "./ui";
import type { LiveScanRow } from "../lib/types";

const TOOLS = [
  { key: "garak", label: "🐛 Garak", desc: "NVIDIA's open-source LLM vulnerability scanner — DAN-family jailbreak probes" },
  { key: "pyrit", label: "🎯 PyRIT", desc: "Microsoft's AI red-teaming framework — adversarial prompt probes" },
] as const;

function outcomeMeta(outcome: LiveScanRow["outcome"]): { label: string; color: string; bg: string } {
  if (outcome === "leaked") return { label: "⚠️ leaked", color: "var(--accent-red)", bg: "rgba(255,68,68,0.1)" };
  if (outcome === "guardrail_blocked") return { label: "🎯 jailbreak succeeded · 🛡️ guardrail caught it", color: "var(--accent-amber)", bg: "rgba(255,170,0,0.1)" };
  return { label: "🧠 model refused on its own", color: "var(--accent-green)", bg: "rgba(0,255,136,0.08)" };
}

function probeLabel(probe?: string): string {
  if (!probe) return "probe";
  return probe.replace(/^garak\./, "").replace(/^pyrit\./, "").replace(/^probes\./, "");
}

export function GarakPyritLivePanel() {
  const [selected, setSelected] = useState<string[]>(["garak"]);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const scanMut = useMutation({
    mutationFn: (tools: string[]) => api.detectLiveScan(tools),
    onMutate: () => {
      setElapsed(0);
      timerRef.current = setInterval(() => setElapsed((e) => e + 1), 1000);
    },
    onSettled: () => {
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = null;
    },
  });

  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current); }, []);

  function toggle(key: string) {
    setSelected((s) => (s.includes(key) ? s.filter((k) => k !== key) : [...s, key]));
  }

  return (
    <div style={{ background: "var(--surface-1, rgba(255,255,255,0.03))", borderRadius: 12, padding: "14px 16px", marginBottom: 16 }}>
      <h4 style={{ margin: "0 0 6px" }}>⚔️ Real Garak / PyRIT Live Scan</h4>
      <p style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: 0 }}>
        Runs the real, self-hosted Garak and/or PyRIT tool against the real deployed target agent right now —
        dozens of real probe attempts, each a real LLM call. Genuinely slow (roughly 2–3 minutes per tool) — this
        waits for the real result rather than faking instant progress.
      </p>

      <div style={{ display: "flex", gap: 16, marginBottom: 10, flexWrap: "wrap" }}>
        {TOOLS.map((t) => (
          <label key={t.key} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.82rem", cursor: "pointer" }} title={t.desc}>
            <input
              type="checkbox"
              checked={selected.includes(t.key)}
              disabled={scanMut.isPending}
              onChange={() => toggle(t.key)}
            />
            {t.label}
          </label>
        ))}
      </div>

      <button
        className="btn btn-secondary btn-small"
        disabled={selected.length === 0 || scanMut.isPending}
        onClick={() => scanMut.mutate(selected)}
      >
        {scanMut.isPending ? `⏳ Scanning… ${elapsed}s elapsed` : "▶ Run live scan"}
      </button>

      {scanMut.isError && (
        <p style={{ fontSize: "0.8rem", color: "var(--accent-red)", marginTop: 8 }}>
          Scan request failed: {scanMut.error instanceof Error ? scanMut.error.message : "Unknown error"}
        </p>
      )}

      {scanMut.data && (
        <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 16 }}>
          {Object.entries(scanMut.data.results).map(([tool, res]) => (
            <div key={tool}>
              <div style={{ fontWeight: 700, fontSize: "0.85rem", marginBottom: 6, textTransform: "capitalize" }}>{tool}</div>

              {!res.live && (
                <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{res.error}</p>
              )}
              {res.live && res.errors && (
                <p style={{ fontSize: "0.78rem", color: "var(--accent-red)" }}>Runner reported an error: {res.errors}</p>
              )}
              {res.live && res.summary && res.summary.total === 0 && !res.errors && (
                <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Real scan completed with no probe findings returned.</p>
              )}

              {res.live && res.summary && res.summary.total > 0 && (
                <>
                  <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
                    <Badge variant="blue">{res.summary.total} real attempts</Badge>
                    {res.summary.leaked > 0 && <Badge variant="red">{res.summary.leaked} leaked</Badge>}
                    {res.summary.guardrail_blocked > 0 && <Badge variant="amber">{res.summary.guardrail_blocked} guardrail-blocked</Badge>}
                    {res.summary.model_self_refused > 0 && <Badge variant="green">{res.summary.model_self_refused} model self-refused</Badge>}
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {res.rows.map((row, i) => {
                      const meta = outcomeMeta(row.outcome);
                      return (
                        <div key={i} style={{ background: meta.bg, border: `1px solid ${meta.color}33`, borderRadius: 8, padding: "8px 10px" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 4 }}>
                            <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontFamily: "JetBrains Mono, monospace" }}>{probeLabel(row.probe)}</span>
                            <span style={{ fontSize: "0.68rem", color: meta.color, fontWeight: 600, textAlign: "right" }}>{meta.label}</span>
                          </div>
                          {row.prompt && (
                            <div style={{ fontSize: "0.76rem", color: "var(--text-secondary)", marginBottom: 4 }}>
                              {row.prompt.length > 200 ? row.prompt.slice(0, 200) + "…" : row.prompt}
                            </div>
                          )}
                          {row.response_snippet && (
                            <div style={{ fontSize: "0.76rem", background: "var(--bg-secondary)", borderRadius: 6, padding: "6px 8px" }}>
                              {row.response_snippet.length > 260 ? row.response_snippet.slice(0, 260) + "…" : row.response_snippet}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
