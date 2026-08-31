import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { GlassCard } from "../components/ui";

export function LoginPage() {
  const { username, login } = useAuth();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (username) return <Navigate to="/" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(u, p);
    } catch {
      setError("Invalid credentials. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div style={{ textAlign: "center", fontSize: "2.5rem" }}>🛡️</div>
        <h1>Securing AI</h1>
        <div className="sub">Agentic AI Security Showcase</div>
        <GlassCard accent="var(--accent-blue)">
          <form onSubmit={onSubmit}>
            <label className="field-label" htmlFor="username">Username</label>
            <input id="username" type="text" value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" style={{ marginBottom: 14 }} />
            <label className="field-label" htmlFor="password">Password</label>
            <input id="password" type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" style={{ marginBottom: 18 }} />
            <button className="btn" type="submit" disabled={busy} style={{ width: "100%" }}>
              {busy ? "Signing in…" : "Sign In"}
            </button>
            {error && <div className="login-error">{error}</div>}
          </form>
        </GlassCard>
      </div>
    </div>
  );
}
