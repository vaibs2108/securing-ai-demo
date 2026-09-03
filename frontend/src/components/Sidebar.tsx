import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../context/useAuth";
import { useTheme } from "../context/ThemeContext";
import { readableAccent } from "../lib/color";

const PHASE_ORDER = ["identify", "protect", "detect", "govern", "respond", "recover"] as const;

export function Sidebar() {
  const { username, role, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const { data: dashboard } = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, staleTime: 30_000 });

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="icon">🛡️</div>
        <div className="name">Securing AI</div>
        <div className="tag">Agentic AI Security Showcase</div>
      </div>
      <hr />

      <div className="flex-row" style={{ marginBottom: 4, padding: "0 4px" }}>
        <div style={{ width: 34, height: 34, borderRadius: "50%", background: "rgba(0,212,255,0.15)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "1rem" }}>👤</div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: "0.85rem", fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{username}</div>
          <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "capitalize" }}>{role}</div>
        </div>
      </div>
      <hr />

      <NavLink to="/" end className={({ isActive }) => `nav-btn${isActive ? " active" : ""}`}>🏠 Home</NavLink>
      <NavLink to="/data-explorer" className={({ isActive }) => `nav-btn${isActive ? " active" : ""}`}>📊 Data Explorer</NavLink>
      <NavLink to="/agents" className={({ isActive }) => `nav-btn${isActive ? " active" : ""}`}>🤖 Agents</NavLink>
      <NavLink to="/copilot" className={({ isActive }) => `nav-btn${isActive ? " active" : ""}`}>💬 Copilot</NavLink>
      <hr />
      <NavLink to="/settings" className={({ isActive }) => `nav-btn${isActive ? " active" : ""}`}>⚙️ Settings</NavLink>
      <NavLink to="/token-usage" className={({ isActive }) => `nav-btn${isActive ? " active" : ""}`}>📈 Token Usage</NavLink>
      <NavLink to="/observability" className={({ isActive }) => `nav-btn${isActive ? " active" : ""}`}>🔭 Observability</NavLink>
      <hr />

      {dashboard && (
        <>
          <div className="posture-index">
            <div className="label">AI Security Posture Index</div>
            <div className="value">{dashboard.posture_index.toFixed(1)}%</div>
            <div className="sub">Scoping: Complete · Status: Verified</div>
          </div>

          {PHASE_ORDER.map((uc) => {
            const g = dashboard.gauges.find((x) => x.phase === uc);
            if (!g) return null;
            return (
              <div className="phase-score-card" key={uc}>
                <div className="row">
                  <span style={{ color: "var(--nav-text)" }}>{g.label}</span>
                  <span style={{ color: readableAccent(g.color, theme), fontWeight: 700 }}>{g.score.toFixed(0)}%</span>
                </div>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${g.score}%`, background: g.color }} />
                </div>
              </div>
            );
          })}
        </>
      )}

      <hr />
      <div className="theme-toggle" role="group" aria-label="Theme">
        <button className={theme === "dark" ? "active" : ""} onClick={() => setTheme("dark")}>🌙 Dark</button>
        <button className={theme === "light" ? "active" : ""} onClick={() => setTheme("light")}>☀️ Light</button>
      </div>
      <button className="nav-btn" onClick={logout}>🚪 Logout</button>
    </aside>
  );
}
