import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../lib/api";
import { GlassCard, Badge } from "../components/ui";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: { text: string; score: number; collection: string; source?: string | null }[];
}

const PIPELINE_STEPS = [
  { icon: "📊", label: "Live Data", sub: "17 Datasets" },
  { icon: "📁", label: "Uploads", sub: "Live File Context" },
  { icon: "🧠", label: "FAISS Core", sub: "Vector Store" },
  { icon: "🔍", label: "Hybrid Search", sub: "Semantic + BM25" },
  { icon: "🛡️", label: "Security Copilot", sub: "GPT Generation" },
];

const ACCEPTED_EXT = ".txt,.json,.log,.csv,.py,.js,.yaml,.yml,.pdf,.docx,.tf,.conf";

export function CopilotPage() {
  const qc = useQueryClient();
  const { data: starters } = useQuery({ queryKey: ["copilot-starters"], queryFn: api.copilotStarters });
  const { data: memory } = useQuery({
    queryKey: ["copilot-memory"],
    queryFn: api.copilotMemory,
    refetchInterval: (query) => (query.state.data?.building ? 3000 : false),
  });

  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "assistant", content: "Hi, I'm the Security Analyst Copilot. Ask me anything across the 16 Securing AI datasets, or upload your own policies/logs/code for me to search too." },
  ]);
  const [input, setInput] = useState("");
  const [uploadOpen, setUploadOpen] = useState(true);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const sendMut = useMutation({
    mutationFn: (message: string) => api.copilotMessage(message),
    onSuccess: (res, message) => {
      setMessages((prev) => [
        ...prev,
        { role: "user", content: message },
        { role: "assistant", content: res.answer, sources: res.sources },
      ]);
    },
  });

  const uploadMut = useMutation({
    mutationFn: (file: File) => api.copilotUpload(file),
    onSuccess: () => {
      setUploadError(null);
      qc.invalidateQueries({ queryKey: ["copilot-memory"] });
    },
    onError: (err) => setUploadError(err instanceof ApiError ? err.message : "Upload failed"),
  });

  const clearUploadsMut = useMutation({
    mutationFn: api.copilotClearUploads,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["copilot-memory"] }),
  });

  function send(text: string) {
    if (!text.trim() || sendMut.isPending) return;
    setInput("");
    sendMut.mutate(text);
  }

  function onFilesSelected(files: FileList | null) {
    if (!files) return;
    Array.from(files).forEach((f) => uploadMut.mutate(f));
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  const datasetsIndexed = memory
    ? Object.values(memory.dataset_status).filter((s) => s.startsWith("indexed") || s.startsWith("cached")).length
    : 0;
  const datasetsTotal = memory ? Object.keys(memory.dataset_status).length : 16;

  return (
    <div>
      <div className="hero-banner">
        <div className="hero-title">🛡️ Security Analyst Copilot</div>
        <div className="hero-subtitle">
          <strong>Objective:</strong>&nbsp;AI-powered RAG assistant with full dataset context and live file retrieval.
        </div>
      </div>

      {/* Pipeline visual */}
      <GlassCard>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
          {PIPELINE_STEPS.map((step, i) => (
            <div key={step.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ textAlign: "center", minWidth: 100 }}>
                <div style={{ fontSize: "1.8rem" }}>{step.icon}</div>
                <div style={{ fontSize: "0.78rem", fontWeight: 700, marginTop: 4 }}>{step.label}</div>
                <div className="muted" style={{ fontSize: "0.68rem" }}>{step.sub}</div>
                {step.label === "Live Data" && (
                  <div style={{ marginTop: 4 }}>
                    <Badge variant={memory?.ready ? "green" : "amber"}>
                      {memory?.ready ? `${memory.total_dataset_vectors} vectors` : `${datasetsIndexed}/${datasetsTotal} indexing…`}
                    </Badge>
                  </div>
                )}
                {step.label === "Uploads" && (
                  <div style={{ marginTop: 4 }}>
                    <Badge variant="blue">{memory?.uploads.length ?? 0} files</Badge>
                  </div>
                )}
                {step.label === "FAISS Core" && (
                  <div style={{ marginTop: 4 }}>
                    <Badge variant="purple">{(memory?.total_dataset_vectors ?? 0) + (memory?.upload_vector_count ?? 0)} total</Badge>
                  </div>
                )}
              </div>
              {i < PIPELINE_STEPS.length - 1 && <div className="muted" style={{ fontSize: "1.2rem" }}>→</div>}
            </div>
          ))}
        </div>
      </GlassCard>

      {/* Upload section */}
      <GlassCard>
        <div
          style={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}
          onClick={() => setUploadOpen((v) => !v)}
        >
          <div className="section-title" style={{ margin: 0 }}>{uploadOpen ? "▾" : "▸"} 📁 Upload Custom Data to AI Memory Bank</div>
        </div>
        {uploadOpen && (
          <div style={{ marginTop: 14 }}>
            <p className="muted" style={{ fontSize: "0.85rem", marginBottom: 12 }}>
              Upload policies, logs, or code files. The Copilot chunks, embeds, and adds them to the FAISS vector
              store for real-time retrieval alongside the platform's real live datasets.
            </p>
            <div className="flex-row" style={{ marginBottom: 12 }}>
              <button className="btn" onClick={() => fileInputRef.current?.click()} disabled={uploadMut.isPending}>
                {uploadMut.isPending ? "Uploading…" : "⬆ Upload"}
              </button>
              <span className="muted" style={{ fontSize: "0.78rem" }}>
                10MB per file · TXT, JSON, LOG, CSV, PY, JS, YAML, PDF, DOCX
              </span>
              <input ref={fileInputRef} type="file" multiple accept={ACCEPTED_EXT} style={{ display: "none" }} onChange={(e) => onFilesSelected(e.target.files)} />
            </div>
            {uploadError && <div className="login-error" style={{ marginBottom: 10 }}>{uploadError}</div>}
            {memory && memory.uploads.length > 0 && (
              <div>
                <div className="data-table-wrap">
                  <table className="data-table">
                    <thead><tr><th>File</th><th>Chunks</th><th>Chars</th></tr></thead>
                    <tbody>
                      {memory.uploads.map((u) => (
                        <tr key={u.filename + u.uploaded_at}>
                          <td>{u.filename}</td>
                          <td>{u.chunks}</td>
                          <td>{u.chars.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <button className="btn btn-secondary btn-small" style={{ marginTop: 10 }} onClick={() => clearUploadsMut.mutate()} disabled={clearUploadsMut.isPending}>
                  🗑 Clear Uploaded Memory
                </button>
              </div>
            )}
          </div>
        )}
      </GlassCard>

      {/* Chat */}
      <GlassCard style={{ minHeight: 320 }}>
        {messages.map((m, i) => (
          <div key={i} style={{ marginBottom: 16 }}>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: 4, textTransform: "uppercase" }}>
              {m.role === "user" ? "You" : "🛡️ Security Analyst Copilot"}
            </div>
            <div style={{ fontSize: "0.9rem", color: m.role === "user" ? "var(--text-heading)" : "var(--text-secondary)", whiteSpace: "pre-line" }}>{m.content}</div>
            {m.sources && m.sources.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <div className="muted" style={{ fontSize: "0.75rem", marginBottom: 6 }}>Retrieved via hybrid search:</div>
                {m.sources.map((s, si) => (
                  <div key={si} className="finding-card" style={{ padding: "8px 12px", marginBottom: 6 }}>
                    <div className="flex-row" style={{ justifyContent: "space-between", marginBottom: 4 }}>
                      <Badge variant={s.source ? "blue" : "purple"}>{s.source ?? s.collection}</Badge>
                      <span className="muted" style={{ fontSize: "0.7rem" }}>score {s.score}</span>
                    </div>
                    <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", fontFamily: "JetBrains Mono, monospace" }}>
                      {s.text.slice(0, 220)}{s.text.length > 220 ? "…" : ""}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        {sendMut.isPending && <div className="muted">Thinking…</div>}
      </GlassCard>

      <div className="flex-row" style={{ marginBottom: 20 }}>
        <input
          type="text"
          value={input}
          placeholder="Ask about agents, guardrails, red-teaming, incidents, or your uploaded files…"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") send(input); }}
        />
        <button className="btn" onClick={() => send(input)} disabled={sendMut.isPending}>Send</button>
      </div>

      <div className="section-title">💡 Try asking</div>
      <div className="grid-3" style={{ marginBottom: 12 }}>
        {(starters ?? []).map((q) => (
          <button key={q} className="btn btn-secondary" style={{ textAlign: "left" }} onClick={() => send(q)}>{q}</button>
        ))}
      </div>
      <button className="btn btn-secondary btn-small" onClick={() => setMessages([messages[0]])}>🧹 Clear Chat History</button>
    </div>
  );
}
