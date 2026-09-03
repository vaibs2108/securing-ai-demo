import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { GlassCard, DataTable, LoadingBlock, Badge } from "../components/ui";

const PHASE_ORDER = ["identify", "protect", "detect", "govern", "respond", "recover"] as const;
const PHASE_LABELS: Record<string, string> = {
  identify: "🔎 Identify", protect: "🛡️ Protect", detect: "🚨 Detect", respond: "🚑 Respond", recover: "♻️ Recover", govern: "🏛️ Govern",
};

export function DataExplorerPage() {
  const { data: datasets, isLoading } = useQuery({ queryKey: ["datasets"], queryFn: api.datasets });
  const [phase, setPhase] = useState<string>("identify");
  const [selected, setSelected] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const detailQ = useQuery({
    queryKey: ["dataset", selected, search],
    queryFn: () => api.dataset(selected!, 200, search || undefined),
    enabled: !!selected,
  });

  if (isLoading || !datasets) return <LoadingBlock label="Loading datasets…" />;

  const list = datasets[phase] ?? [];
  const allDatasets = Object.values(datasets).flat();
  const liveCount = allDatasets.filter((d) => d.is_live).length;
  const selectedMeta = list.find((d) => d.name === selected);

  return (
    <div>
      <div className="hero-banner">
        <div className="hero-title">🗂️ Evidence Store</div>
        <div className="hero-subtitle">
          {liveCount} of {allDatasets.length} datasets carry real evidence on record right now — fetched from the
          real target repo, the real deployed agent, or computed from both. An empty dataset means no real evidence
          has been collected for that slot yet, never a placeholder row.
        </div>
      </div>

      <div className="top-tabs">
        {PHASE_ORDER.map((uc) => (
          <span key={uc} className={`top-tab${phase === uc ? " active" : ""}`} onClick={() => { setPhase(uc); setSelected(null); }}>{PHASE_LABELS[uc]}</span>
        ))}
      </div>

      <div className="grid-3" style={{ marginBottom: 20 }}>
        {list.map((ds) => (
          <GlassCard key={ds.name} accent={selected === ds.name ? "var(--accent-blue)" : undefined} style={{ cursor: "pointer" }}>
            <div onClick={() => setSelected(ds.name)}>
              <div className="flex-row" style={{ justifyContent: "space-between" }}>
                <div style={{ fontWeight: 700 }}>{ds.name}</div>
                {ds.is_live ? <Badge variant="green">✓ Live Evidence</Badge> : <Badge variant="blue">No Evidence Yet</Badge>}
              </div>
              <div className="muted" style={{ fontSize: "0.8rem", marginTop: 4 }}>{ds.row_count.toLocaleString()} rows · {ds.column_count} columns</div>
            </div>
          </GlassCard>
        ))}
      </div>

      {selected && (
        <GlassCard>
          <div className="flex-row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
            <div className="flex-row" style={{ gap: 10 }}>
              <div className="section-title" style={{ margin: 0 }}>{selected}</div>
              {selectedMeta?.is_live ? <Badge variant="green">✓ Live Evidence</Badge> : <Badge variant="blue">No Evidence Yet</Badge>}
            </div>
            <div className="flex-row" style={{ gap: 8 }}>
              <input type="text" placeholder="Search…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ width: 220 }} />
              <button className="btn btn-secondary btn-small" onClick={() => api.downloadDataset(selected)}>⬇️ Download CSV</button>
            </div>
          </div>
          {detailQ.isLoading ? <LoadingBlock /> : (
            <>
              <div className="muted" style={{ fontSize: "0.8rem", marginBottom: 8 }}>
                {detailQ.data?.row_count.toLocaleString()} matching rows (showing up to 200)
                {detailQ.data?.row_count === 0 && " — no real evidence collected for this dataset yet"}
              </div>
              <DataTable columns={detailQ.data?.columns ?? []} records={detailQ.data?.records ?? []} limit={200} />
            </>
          )}
        </GlassCard>
      )}
    </div>
  );
}
