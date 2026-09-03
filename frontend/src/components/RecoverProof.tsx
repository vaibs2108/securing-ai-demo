import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

export function RecoverProof() {
  const replayMut = useMutation({ mutationFn: api.replayDetect });
  const evidenceQ = useQuery({ queryKey: ["historical-leak-evidence"], queryFn: api.historicalLeakEvidence });

  return (
    <div style={{ marginBottom: 20 }}>
      <h4>The real before and after</h4>
      <div className="grid-2" style={{ gap: 12 }}>
        <div style={{ background: "rgba(255,68,68,0.08)", border: "1px solid var(--accent-red)33", borderRadius: 12, padding: "12px 14px" }}>
          <div style={{ fontSize: "0.68rem", color: "var(--accent-red)", fontWeight: 700, marginBottom: 6 }}>BEFORE THE FIX</div>
          {evidenceQ.data?.captured ? (
            <>
              <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", margin: "0 0 6px" }}>
                real captured leak, {evidenceQ.data.captured_at && new Date(evidenceQ.data.captured_at).toLocaleString()}:
              </p>
              <div style={{ fontSize: "0.76rem", color: "var(--text-secondary)", marginBottom: 6 }}>
                <strong>Real prompt sent:</strong> {evidenceQ.data.prompt}
              </div>
              <div style={{ background: "var(--bg-secondary)", borderRadius: 8, padding: 8, fontSize: "0.76rem", marginBottom: 8 }}>
                {evidenceQ.data.response}
              </div>
              <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", margin: 0 }}>
                Reproduced once, deliberately, via a brief admin-authenticated guardrail toggle — see the real fix
                commit{" "}
                <a href="https://github.com/vaibs2108/meridian-support-agent/commit/2b89c37" target="_blank" rel="noreferrer">2b89c37</a>,
                restored immediately after this capture.
              </p>
            </>
          ) : (
            <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", margin: 0 }}>
              No output-side guardrail existed. A real live Detect run confirmed the agent's internal API key could be
              extracted via multiple real jailbreak techniques — see the real fix commit{" "}
              <a href="https://github.com/vaibs2108/meridian-support-agent/commit/2b89c37" target="_blank" rel="noreferrer">2b89c37</a>.
            </p>
          )}
        </div>

        <div style={{ background: "rgba(0,255,136,0.06)", border: "1px solid var(--accent-green)33", borderRadius: 12, padding: "12px 14px" }}>
          <div style={{ fontSize: "0.68rem", color: "var(--accent-green)", fontWeight: 700, marginBottom: 6 }}>AFTER THE FIX — LIVE</div>
          {!replayMut.data && !replayMut.isPending && (
            <>
              <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: 0 }}>
                Re-send the same real prompt to the real live agent right now, no re-run of the whole stage needed.
              </p>
              <button className="btn btn-secondary btn-small" onClick={() => replayMut.mutate()}>▶ Replay this attack now</button>
            </>
          )}
          {replayMut.isPending && <p className="muted" style={{ fontSize: "0.8rem" }}>Sending the real prompt to the real live agent…</p>}
          {replayMut.isError && <p style={{ fontSize: "0.8rem", color: "var(--accent-red)" }}>Couldn't reach the real agent. Try again.</p>}
          {replayMut.data && (
            <>
              <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", margin: "0 0 6px" }}>real reply, just now:</p>
              <div style={{ background: "var(--bg-secondary)", borderRadius: 8, padding: 8, fontSize: "0.78rem", marginBottom: 8 }}>{replayMut.data.response}</div>
              <div style={{ fontSize: "0.8rem", fontWeight: 700, color: replayMut.data.leaked ? "var(--accent-red)" : "var(--accent-green)" }}>
                {replayMut.data.leaked ? "⚠️ leaked" : "✅ blocked — fix holds"}
              </div>
              {!replayMut.data.leaked && replayMut.data.model_leaked_raw && (
                <p style={{ fontSize: "0.72rem", color: "var(--accent-amber)", margin: "6px 0 0" }}>
                  🎯 The underlying model still fell for this jailbreak and generated the real credential internally —
                  the output guardrail is what actually caught it before you saw it. The model is no safer; the fix
                  is what's holding.
                </p>
              )}
              <button className="btn btn-secondary btn-small" style={{ marginTop: 8 }} onClick={() => replayMut.mutate()}>▶ Replay again</button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
