import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./context/AuthContext";
import { ThemeProvider } from "./context/ThemeContext";
import { Layout } from "./components/Layout";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { PhaseWorkspace } from "./pages/PhaseWorkspace";
import { AgentsPage } from "./pages/AgentsPage";
import { CopilotPage } from "./pages/CopilotPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TokenUsagePage } from "./pages/TokenUsagePage";
import { ObservabilityPage } from "./pages/ObservabilityPage";
import { DataExplorerPage } from "./pages/DataExplorerPage";
import { AssetGraphPage } from "./pages/AssetGraphPage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/" element={<Layout><DashboardPage /></Layout>} />
              <Route path="/phase/:uc" element={<Layout><PhaseWorkspace /></Layout>} />
              <Route path="/data-explorer" element={<Layout><DataExplorerPage /></Layout>} />
              <Route path="/asset-graph" element={<Layout><AssetGraphPage /></Layout>} />
              <Route path="/agents" element={<Layout><AgentsPage /></Layout>} />
              <Route path="/copilot" element={<Layout><CopilotPage /></Layout>} />
              <Route path="/settings" element={<Layout><SettingsPage /></Layout>} />
              <Route path="/token-usage" element={<Layout><TokenUsagePage /></Layout>} />
              <Route path="/observability" element={<Layout><ObservabilityPage /></Layout>} />
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
