import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import { Sidebar } from "./Sidebar";
import { StoryBar } from "./StoryBar";
import { LoadingBlock } from "./ui";

export function Layout({ children }: { children: ReactNode }) {
  const { username, loading } = useAuth();

  if (loading) return <LoadingBlock label="Checking session…" />;
  if (!username) return <Navigate to="/login" replace />;

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main-content">
        <StoryBar />
        <div className="main-content-inner">{children}</div>
      </main>
    </div>
  );
}
