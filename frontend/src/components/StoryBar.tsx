import { useQuery } from "@tanstack/react-query";
import { NavLink, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import type { StoryNode } from "../lib/types";

// Matches the real backend data-generation order (app/data/live_engine.py's
// generate_all()): Govern's real cross-phase evaluation needs Identify/
// Protect/Detect's real findings to exist first, so it's computed (and
// shown here) right after Detect, not before it — Respond/Recover's own
// real consolidated incident_queue then builds on Govern's result too.
const PHASE_ORDER = ["identify", "protect", "detect", "govern", "respond", "recover"] as const;
const PHASE_ICON: Record<string, string> = {
  govern: "🏛️", identify: "🔎", protect: "🛡️", detect: "🚨", respond: "🚑", recover: "♻️",
};
const STATUS_COLOR: Record<StoryNode["status"], string> = {
  pending: "var(--text-muted)",
  clean: "var(--accent-green)",
  warning: "var(--accent-amber)",
  critical: "var(--accent-red)",
  resolved: "var(--accent-blue)",
};

export function StoryBar() {
  const location = useLocation();
  const { data } = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, refetchInterval: 15_000 });

  // Hide on the login page (no data yet / not useful there)
  if (location.pathname === "/login") return null;
  if (!data) return null;

  const storyline = data.storyline ?? [];

  // Dashboard + the 6 phases render as one continuous, evenly-spaced row —
  // deliberately the same array, same item markup, same connector-line
  // mechanism for every entry (previously Dashboard sat in a separate
  // fixed-gap flex container next to the phases' own flex:1 row, which
  // produced two different spacing rhythms side by side).
  const items: { key: string; to: string; icon: string; label: string; sub?: string; subColor?: string }[] = [
    { key: "dashboard", to: "/", icon: "📊", label: "Dashboard" },
    ...PHASE_ORDER.map((phase) => {
      const node = storyline.find((n) => n.phase === phase);
      return {
        key: phase,
        to: `/phase/${phase}`,
        icon: PHASE_ICON[phase],
        label: phase.charAt(0).toUpperCase() + phase.slice(1),
        sub: node?.label ?? "—",
        subColor: node ? STATUS_COLOR[node.status] : "var(--text-muted)",
      };
    }),
  ];

  return (
    <div className="story-bar" style={{ display: "flex", alignItems: "flex-start", padding: "10px 20px", borderBottom: "1px solid var(--border-glass)" }}>
      {items.map((item, i) => (
        <div key={item.key} style={{ display: "flex", alignItems: "center", flex: 1 }}>
          <NavLink
            to={item.to}
            end={item.to === "/"}
            style={({ isActive }) => ({
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 2,
              textDecoration: "none",
              minWidth: 0,
              color: isActive ? "var(--accent-blue)" : "var(--text-secondary)",
            })}
          >
            <span style={{ fontSize: "0.85rem" }}>{item.icon}</span>
            <span style={{ fontSize: "0.62rem" }}>{item.label}</span>
            {item.sub !== undefined && (
              <span style={{ fontSize: "0.58rem", color: item.subColor, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 90 }}>
                {item.sub}
              </span>
            )}
          </NavLink>
          {i < items.length - 1 && <div style={{ height: 1, background: "var(--border-glass)", flex: 1, margin: "0 4px 14px" }} />}
        </div>
      ))}
    </div>
  );
}
