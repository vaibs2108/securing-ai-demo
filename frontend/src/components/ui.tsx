import type { ReactNode } from "react";
import { useTheme } from "../context/ThemeContext";
import { readableAccent } from "../lib/color";

export function GlassCard({ children, accent, style }: { children: ReactNode; accent?: string; style?: React.CSSProperties }) {
  return (
    <div className="glass-card" style={{ borderTop: accent ? `2px solid ${accent}` : undefined, ...style }}>
      {children}
    </div>
  );
}

export function Badge({ children, variant = "blue" }: { children: ReactNode; variant?: string }) {
  return <span className={`badge badge-${variant}`}>{children}</span>;
}

export function severityVariant(sev: string): string {
  const s = sev.toLowerCase();
  if (s === "critical") return "red";
  if (s === "high") return "red";
  if (s === "medium") return "amber";
  if (s === "low") return "blue";
  return "green";
}

export function MetricCard({ label, value, colour = "var(--accent-blue)", delta }: { label: string; value: string | number; colour?: string; delta?: string }) {
  return (
    <div className="metric-card">
      <div className="metric-value" style={{ color: colour }}>{value}</div>
      <div className="metric-label">{label}</div>
      {delta && <div className="metric-delta positive">{delta}</div>}
    </div>
  );
}

export function Gauge({ score, title, subtext, color }: { score: number; title: string; subtext?: string; color: string }) {
  const { theme } = useTheme();
  // color is a raw dark-tuned hex from the backend (phase accent) — fine as
  // the arc's stroke, unreadable as the small title text below it on the
  // light theme. See lib/color.ts.
  const titleColor = readableAccent(color, theme);
  const arcLength = 251.3;
  const dashoffset = arcLength * (1 - Math.min(100, Math.max(0, score)) / 100);
  return (
    <div style={{ textAlign: "center", margin: "10px 0" }}>
      <svg width="100%" height="110" viewBox="0 0 200 120" style={{ display: "block", margin: "0 auto" }}>
        <path d="M 20 105 A 80 80 0 0 1 180 105" fill="none" stroke="rgba(var(--overlay-rgb), 0.12)" strokeWidth="14" strokeLinecap="round" />
        <path
          d="M 20 105 A 80 80 0 0 1 180 105"
          fill="none"
          stroke={color}
          strokeWidth="14"
          strokeLinecap="round"
          strokeDasharray={arcLength}
          strokeDashoffset={dashoffset}
          style={{ transition: "stroke-dashoffset 0.8s ease-in-out" }}
        />
        <text x="100" y="90" textAnchor="middle" fontFamily="Inter, sans-serif" fontWeight={800} fontSize={28} fill="var(--text-heading)">
          {score.toFixed(1)}%
        </text>
        <text x="100" y="115" textAnchor="middle" fontFamily="Inter, sans-serif" fontWeight={600} fontSize={12} fill={titleColor} letterSpacing="0.05em">
          {title.toUpperCase()}
        </text>
      </svg>
      {subtext && <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: 4 }}>{subtext}</div>}
    </div>
  );
}

export function KpiProgressCard({ label, value, colour, subtext }: { label: string; value: number; colour: string; subtext?: string }) {
  const { theme } = useTheme();
  const pct = Math.min(100, Math.max(0, value));
  return (
    <div style={{ background: "rgba(var(--overlay-rgb), 0.04)", border: "1px solid var(--border-glass)", borderRadius: 10, padding: "14px 18px", marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-heading)" }}>{label}</span>
        <span style={{ fontSize: "0.95rem", fontWeight: 800, color: readableAccent(colour, theme) }}>{value.toFixed(1)}%</span>
      </div>
      <div style={{ width: "100%", height: 8, background: "rgba(var(--overlay-rgb), 0.12)", borderRadius: 4, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: `linear-gradient(90deg, ${colour} 0%, ${colour}cc 100%)`, borderRadius: 4, transition: "width 0.6s ease" }} />
      </div>
      {subtext && <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 4 }}>{subtext}</div>}
    </div>
  );
}

export function Spinner() {
  return <span className="spinner" />;
}

export function LoadingBlock({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex-row muted" style={{ padding: 24 }}>
      <Spinner /> <span>{label}</span>
    </div>
  );
}

export function DataTable({ columns, records, limit = 50 }: { columns: string[]; records: Record<string, unknown>[]; limit?: number }) {
  const rows = records.slice(0, limit);
  const fmt = (v: unknown) => {
    if (v === null || v === undefined) return "";
    if (typeof v === "boolean") return v ? "true" : "false";
    if (Array.isArray(v)) return v.join(", ");
    return String(v);
  };
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>{columns.map((c) => <td key={c}>{fmt(row[c])}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
