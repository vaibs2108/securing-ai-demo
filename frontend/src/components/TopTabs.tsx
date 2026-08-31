import { NavLink } from "react-router-dom";

const TABS = [
  { to: "/", label: "📊 Dashboard" },
  { to: "/phase/identify", label: "🔎 Identify" },
  { to: "/phase/protect", label: "🛡️ Protect" },
  { to: "/phase/detect", label: "🚨 Detect" },
  { to: "/phase/respond", label: "🚑 Respond" },
  { to: "/phase/recover", label: "♻️ Recover" },
];

export function TopTabs() {
  return (
    <div className="top-tabs">
      {TABS.map((t) => (
        <NavLink key={t.to} to={t.to} end={t.to === "/"} className={({ isActive }) => `top-tab${isActive ? " active" : ""}`}>
          {t.label}
        </NavLink>
      ))}
    </div>
  );
}
