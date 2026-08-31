import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { GlassCard, LoadingBlock, MetricCard } from "../components/ui";

export function TokenUsagePage() {
  const { data, isLoading } = useQuery({ queryKey: ["token-usage"], queryFn: api.tokenUsage });

  if (isLoading || !data) return <LoadingBlock label="Loading token usage…" />;

  return (
    <div>
      <div className="hero-banner">
        <div className="hero-title">📈 Token Usage &amp; Cost</div>
        <div className="hero-subtitle">Last 30 days of LLM consumption across all phases</div>
      </div>

      <div className="grid-4" style={{ marginBottom: 24 }}>
        <MetricCard label="Total Tokens" value={data.total_tokens.toLocaleString()} colour="var(--accent-blue)" />
        <MetricCard label="Total Cost (USD)" value={`$${data.total_cost_usd.toFixed(4)}`} colour="var(--accent-green)" />
        <MetricCard label="LLM Calls" value={data.call_count} colour="var(--accent-purple)" />
        <MetricCard label="Avg Duration" value={`${data.avg_duration_ms}ms`} colour="var(--accent-amber)" />
      </div>

      <div className="grid-3">
        <GlassCard>
          <div className="section-title">Cost by Model</div>
          {Object.entries(data.by_model).map(([k, v]) => (
            <div key={k} className="flex-row" style={{ justifyContent: "space-between", fontSize: "0.85rem", padding: "6px 0", borderBottom: "1px solid var(--border-glass)" }}>
              <span>{k}</span><span style={{ fontWeight: 700 }}>${v.toFixed(4)}</span>
            </div>
          ))}
          {Object.keys(data.by_model).length === 0 && <p className="muted">No usage recorded yet.</p>}
        </GlassCard>
        <GlassCard>
          <div className="section-title">Cost by Phase</div>
          {Object.entries(data.by_use_case).map(([k, v]) => (
            <div key={k} className="flex-row" style={{ justifyContent: "space-between", fontSize: "0.85rem", padding: "6px 0", borderBottom: "1px solid var(--border-glass)" }}>
              <span>{k}</span><span style={{ fontWeight: 700 }}>${v.toFixed(4)}</span>
            </div>
          ))}
          {Object.keys(data.by_use_case).length === 0 && <p className="muted">No usage recorded yet.</p>}
        </GlassCard>
        <GlassCard>
          <div className="section-title">Cost by Stage</div>
          {Object.entries(data.by_stage).map(([k, v]) => (
            <div key={k} className="flex-row" style={{ justifyContent: "space-between", fontSize: "0.85rem", padding: "6px 0", borderBottom: "1px solid var(--border-glass)" }}>
              <span>{k}</span><span style={{ fontWeight: 700 }}>${v.toFixed(4)}</span>
            </div>
          ))}
          {Object.keys(data.by_stage).length === 0 && <p className="muted">No usage recorded yet.</p>}
        </GlassCard>
      </div>

      <GlassCard style={{ marginTop: 8 }}>
        <div className="section-title">💡 Cost Optimisation</div>
        <p className="muted" style={{ fontSize: "0.85rem" }}>
          Every tier currently runs gpt-4o-mini. Detect and Respond's Tier 3 "reasoning" slot is configured for
          gpt-4o, but a demo cost guard unconditionally clamps it to gpt-4o-mini regardless of what's set in
          Settings — any gpt-4o cost in the breakdown above predates that guard being added; going forward, this
          platform can't spend gpt-4o's ~17x-higher per-token rate ($2.50 vs $0.15 per 1M input tokens) even if
          you set the reasoning model to gpt-4o. The clamp lives in <code>app/llm/router.py</code>'s{" "}
          <code>_demo_safe()</code> and exists specifically to keep this demo cheap to run.
        </p>
      </GlassCard>
    </div>
  );
}
