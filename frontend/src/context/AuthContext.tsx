import { createContext, useEffect, useState, type ReactNode } from "react";
import { api, clearToken, getToken, setToken } from "../lib/api";

export interface AuthState {
  username: string | null;
  role: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

// Fast Refresh requires a file to export only components — the useAuth hook
// lives in ./useAuth.ts specifically so editing it (or anything that
// triggers this file's HMR graph) doesn't force a full module invalidation
// that briefly desyncs this context from already-mounted consumers (was
// producing a real, reproducible "useAuth must be used within AuthProvider"
// console error on nearly every edit — see AGENTS.md).
export const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [username, setUsername] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getToken()) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then((me) => {
        setUsername(me.username);
        setRole(me.role);
      })
      .catch(() => {
        clearToken();
      })
      .finally(() => setLoading(false));
  }, []);

  async function login(u: string, p: string) {
    const res = await api.login(u, p);
    setToken(res.token);
    setUsername(res.username);
    setRole(res.role);
  }

  function logout() {
    clearToken();
    setUsername(null);
    setRole(null);
  }

  return (
    <AuthContext.Provider value={{ username, role, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
