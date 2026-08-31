import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ChartData } from "../lib/types";

const PALETTE = [
  "var(--accent-blue)", "var(--accent-green)", "var(--accent-amber)", "var(--accent-red)",
  "var(--accent-purple)", "var(--accent-teal)", "var(--accent-orange)", "var(--text-muted)",
];

const TOOLTIP_STYLE = { background: "var(--bg-secondary)", border: "1px solid var(--border-glass)", borderRadius: 8 };
const TOOLTIP_LABEL_STYLE = { color: "var(--text-primary)" };
const TOOLTIP_ITEM_STYLE = { color: "var(--text-primary)" };

export function Chart({ chart, accent }: { chart: ChartData; accent?: string }) {
  const data = chart.labels.map((l, i) => ({ name: l, value: chart.values[i] }));

  if (chart.type === "donut") {
    return (
      <div>
        <div className="section-title">{chart.title}</div>
        <ResponsiveContainer width="100%" height={240}>
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius={50} outerRadius={85} paddingAngle={2}>
              {data.map((d, i) => <Cell key={d.name} fill={PALETTE[i % PALETTE.length]} />)}
            </Pie>
            <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    );
  }

  return (
    <div>
      <div className="section-title">{chart.title}</div>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data}>
          <CartesianGrid stroke="rgba(var(--overlay-rgb), 0.08)" />
          <XAxis dataKey="name" tick={{ fill: "var(--text-muted)", fontSize: 10 }} interval={0} angle={-20} textAnchor="end" height={60} />
          <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
          <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} />
          <Bar dataKey="value" fill={accent ?? "var(--accent-blue)"} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
