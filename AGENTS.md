# Securing AI — AGENTS.md
# Version: 6.0 — Complete Platform Specification
# Source of Truth for all development, AI agent prompting, and demo delivery

---

> **History note.** This project originally shipped as a Streamlit app (v1.0–v5.x),
> then grew a parallel FastAPI + React frontend for production/HF-Spaces hosting
> (Section 28), and later — once the React port reached full feature parity —
> retired and deleted the Streamlit app entirely. Every section below has been
> updated to describe the **current React + FastAPI architecture only**; nothing
> past this point describes a UI that still exists. `app/ui/components/lifecycle_stage.py`
> is the one file that survived the deletion, trimmed to just its pure-data
> `STAGE_DEFINITIONS`/`STAGE_INPUT_OUTPUT_MAP` and lookup functions (its old
> Streamlit-rendering functions were removed). `streamlit`, `plotly`, and `altair`
> are no longer dependencies.

---

# 1. Platform Vision

**Name**: Securing AI — Agentic AI Security Showcase
**Version**: Demo Phase (pre-production) — v6.0
**Purpose**: Demonstrate AI/agent security applied across the full NIST Cybersecurity
Framework (CSF) 2.0 lifecycle to CXO and technical audiences. The platform functions as a
compelling pre-sales demo and a credible production implementation blueprint simultaneously.

**One Use Case, Five NIST CSF Phases — Each Showing the Full AI Lifecycle:**
1. **Identify** — AI/Agent Asset & Risk Discovery — 3-stage lifecycle
2. **Protect** — Guardrails, Least Privilege & Secrets — 4-stage lifecycle
3. **Detect** — Live Detection & Automated Red-Teaming — 3-stage lifecycle
4. **Respond** — Containment & Incident Playbooks — 2-stage lifecycle
5. **Recover** — Rollback & Guardrail Update Loop — 2-stage lifecycle

One synthetic company and one recurring "target agent" identity are reused as narrative
flavour across all five phases; each phase's datasets are still generated independently.

**Core Design Principles:**
- Every phase shows the FULL AI lifecycle — Discovery → Analysis → Validation →
  Action — not just a finding list
- Data always flows: MCP/API Live tools (P1) → File Upload (P2) → Synthetic (P3)
- Synthetic data is enterprise-grade in structure, always clearly watermarked
- Human-in-the-loop (HITL) gates are visible and mandatory for Critical-severity findings
  in one stage per phase
- Remediation ticketing (Jira/ServiceNow) is simulated for demo purposes at every final
  stage — see Section 15 for the real vs. legacy mechanism
- Observability is active on every layer and fully visible inside the application UI
- 48-hour short-term memory — context persists across browser sessions within 2 days
- Every stage shows its objective, agent identity, expected analysis, and expected output
  BEFORE the user clicks Execute — transparency is a first-class feature
- Each stage result shows: AI Analysis, Under the Hood (pipeline transparency), AI
  Recommendations, Output Dataset Preview, and Handoff to next stage
- The five phases close a loop: Recover's Guardrail Update Loop stage feeds directly back
  into Protect's policy library, so the narrative doesn't just end at Stage 14

---

# 2. Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Frontend | React 19 + TypeScript + Vite | Single-page app, served as static assets by the FastAPI backend in production (Section 28) |
| Backend | FastAPI + Uvicorn | Thin JSON API over the same `app/` Python business logic; no business logic duplicated in JS |
| Charts | Recharts (React) | Interactive gauges, distributions, trend charts — client-side, driven by backend-computed data |
| Agent Orchestration | LangChain + LangGraph | 4-node StateGraph per stage execution |
| Primary LLM | GPT-4o-mini (OpenAI API) | 128k context, $0.15/1M input, consistent quality, no GPU |
| Reasoning LLM | GPT-4o-mini (OpenAI API) | Routed to for Detect and Respond phases. GPT-4o is deliberately kept a "dummy" — resolvable as a config value but transparently downgraded to GPT-4o-mini by `app/llm/router.py`'s `_demo_safe()`, so no configuration path can trigger an accidental high-cost call during a demo |
| Optional LLM | Ollama (UI config only) | Shown in Settings for future production use — not active in demo |
| Structured Output | Pydantic v2 | Guardrail schemas defined in `app/guardrails/validator.py` |
| Content Safety | Regex PII/injection scan + OpenAI Moderation API (best-effort) | Layer 2 guardrail |
| Vector DB | FAISS (faiss-cpu) + BM25, hybrid RRF-merged | Powers the real Copilot RAG retrieval — see Section 28.7 |
| Data Engine | Pandas + NumPy | Pre-aggregation before every LLM call |
| File Parsing | PyMuPDF + chardet + python-docx | PDF, encoded text, Word documents |
| MCP Client | httpx + mcp SDK | Mock/live dispatch pattern per registered tool |
| Token Tracking | SQLite (stdlib) | Zero setup, persistent, works everywhere |
| Short-Term Memory | SQLite (stdlib) | 48-hour conversation + session context store |
| LLM Observability | LangSmith (SaaS) | Traces surfaced in-app via API, with offline fallback |
| App Metrics | In-memory dict, rendered via Recharts | Session-scoped health metrics |
| Hallucination Detection | `HallucinationDetector` (custom) | NVD API (CVE) + MITRE ATT&CK/ATLAS technique validation, shown in-app, persisted to SQLite (Section 28.9) |
| Workflow Ticketing | Simulated Jira/ServiceNow state machine | See Section 15 — no live API calls in the current build |
| Hosting | HF Spaces (Docker) or any Python host | `Dockerfile` — two-stage Node→Python build, see Section 25.4 |

---

# 3. Infrastructure — Demo Phase

## 3.1 What Installs

```
uv sync
```

Dependencies are managed with `uv` (`pyproject.toml` / `uv.lock` are authoritative);
this single command installs the complete Python platform into a local `.venv`. No
Docker required for local dev, no GPU, no system packages beyond Python 3.10+.
`requirements.txt` is kept only as a pip-compatible fallback for environments without
`uv` (`pip install -r requirements.txt`) — it is not used by `uv` or the Dockerfile,
and can drift; treat `pyproject.toml`/`uv.lock` as ground truth.

## 3.2 Hosting Options

| Platform | What to do | Notes |
|---|---|---|
| **Local (laptop/desktop)** | `uv sync` + the React/FastAPI stack (Section 28.6) | Works on Mac/Windows/Linux |
| **HuggingFace Spaces** | Push to HF repo — uses `Dockerfile` (React + FastAPI, Section 28) | Free tier works |
| **Any cloud VM (Azure/GCP/AWS)** | Same as local — Python + uv + Node for the frontend build | No special cloud config needed |

## 3.3 File Structure

```
securing_AI_demo/
├── requirements.txt                     # pip-compatible fallback (pyproject.toml/uv.lock are ground truth)
├── Dockerfile                           # Two-stage build: Node (frontend) → Python (backend), HF Spaces target
├── .env / .env.example                  # Secrets and config
├── token_pricing.yaml                   # LLM cost rates — editable without code change
├── scratch_check.py                     # Module import verification script
│
├── data/                                 # SQLite files, auto-created, gitignored
│   ├── token_usage.db                   # Token events + cost log
│   ├── audit_log.db                     # HITL decisions + guardrail events
│   ├── memory.db                        # 48-hour short-term memory store
│   ├── score_history.db                 # Real daily phase-score snapshots (dashboard trend chart)
│   ├── hallucination_reports.db         # Per-stage hallucination validation reports
│   ├── app_settings.db                  # SettingsStore — API keys, MCP creds, admin password (Section 28.8)
│   └── rag_cache/                       # Cached FAISS indexes for the Copilot (Section 28.7)
│
├── backend/                              # FastAPI app — see Section 28.2 for full detail
│   ├── main.py                          # All routes: auth, dashboard, phases, datasets, agents,
│   │                                     #   mcp, settings, token-usage, observability, copilot
│   ├── state.py                         # AppState — process-wide singleton (datasets, KPIEngine,
│   │                                     #   AgentManager, MCPClient, ShortTermMemory, RAGService)
│   ├── security.py                      # HMAC-signed session token (SESSION_SECRET env var)
│   ├── data_content.py                  # STAGE_UI_CONFIG, AGENTS_DB, PHASE_DATASETS — pure data
│   ├── rag_service.py                   # RAGService — Copilot dataset indexing + caching
│   └── utils.py                         # df_to_records / chart_data / hitl_candidates helpers
│
├── frontend/                             # Vite + React 19 + TypeScript
│   └── src/
│       ├── theme.css                    # Dark + light theme, CSS custom properties, glassmorphism
│       ├── App.tsx                      # Router + ThemeProvider + AuthProvider wiring
│       ├── lib/
│       │   ├── api.ts                   # Typed fetch client (Bearer auth) for every backend route
│       │   ├── types.ts                 # Response/request shape types
│       │   ├── color.ts                 # readableAccent() — WCAG-contrast-aware light-theme text colour
│       │   └── kpiMeta.ts               # KPI status/colour thresholds
│       ├── context/
│       │   ├── AuthContext.tsx          # Login state, token in localStorage
│       │   └── ThemeContext.tsx         # Dark/light toggle, persisted to localStorage
│       ├── components/
│       │   ├── Sidebar.tsx              # Left nav — phase score bars, theme toggle, logout
│       │   ├── TopTabs.tsx              # Dashboard / 5-phase horizontal tab bar
│       │   ├── Chart.tsx                # Recharts wrapper
│       │   ├── Layout.tsx               # App shell (sidebar + routed content)
│       │   └── ui.tsx                   # GlassCard, Badge, Gauge, KpiProgressCard, DataTable, etc.
│       └── pages/
│           ├── PhaseWorkspace.tsx       # ONE generic component renders all 5 phases / 14 stages,
│           │                             #   driven by STAGE_UI_CONFIG from the backend
│           ├── DashboardPage.tsx        # Executive dashboard — gauges, KPI cards, trend charts
│           ├── AgentsPage.tsx           # Agent catalogue (14 agents)
│           ├── CopilotPage.tsx          # Hybrid-RAG chat (Section 28.7)
│           ├── DataExplorerPage.tsx     # Raw dataset browser + CSV download
│           ├── SettingsPage.tsx         # API keys, LLM routing, MCP integrations, credentials
│           ├── TokenUsagePage.tsx       # Token consumption + cost breakdown
│           ├── ObservabilityPage.tsx    # LangSmith traces, hallucination detection, health, audit
│           └── LoginPage.tsx
│
└── app/                                  # Business logic shared by nothing but backend/ now
    ├── data/
    │   ├── generator.py                 # SyntheticDataEngine — 16 datasets
    │   └── compliance_frameworks.yaml   # NIST AI RMF, MITRE ATT&CK/ATLAS, OWASP LLM Top 10 refs
    │
    ├── kpi/
    │   └── engine.py                    # KPIEngine — 20 metrics + AI Security Posture Index
    │
    ├── llm/
    │   ├── router.py                    # LLMRouter — 3-tier (primary/local/reasoning)
    │   ├── chunker.py                   # DataChunkEngine — map-reduce pipeline (unused by current flow)
    │   └── token_tracker.py             # TokenUsageTracker — SQLite + cost calc
    │
    ├── rag/                             # Real hybrid FAISS + BM25 engine — wired into the Copilot
    │   ├── collections.py               #   via backend/rag_service.py (Section 28.7)
    │   ├── indexes.py
    │   ├── ingestor.py
    │   └── retriever.py
    │
    ├── memory/
    │   └── short_term.py                # ShortTermMemory — 48h SQLite-backed store
    │
    ├── mcp/
    │   ├── registry.py                  # MCPToolRegistry — AI security tool catalogue
    │   ├── client.py                    # MCPClient — mock/live connection dispatch
    │   └── transformers/base.py         # MCPTransformer base class
    │
    ├── runtime/
    │   ├── agent_manager.py             # AgentManager — LangGraph pipeline + all 14 stage prompts
    │   └── evaluator.py                 # Stage output evaluator
    │
    ├── guardrails/
    │   └── validator.py                 # GuardrailManager — Pydantic + Moderation + HITL thresholds
    │
    ├── observability/
    │   ├── langsmith_client.py          # LangSmith API queries for in-app display
    │   ├── hallucination.py             # HallucinationDetector — NVD + ATT&CK/ATLAS validation
    │   ├── health_metrics.py            # InAppMetrics — process-wide health store
    │   ├── score_history.py             # ScoreHistoryStore — real daily phase-score snapshots
    │   ├── trace_store.py               # Plain module-level execution trace store
    │   ├── metrics.py                   # Prometheus metrics registry (not imported by the live app)
    │   └── audit_logger.py              # SQLite audit trail writer
    │
    ├── upload/
    │   └── processor.py                 # FileUploadProcessor
    │
    ├── config/
    │   └── settings_store.py            # SettingsStore — SQLite-backed runtime settings (Section 28.8)
    │
    └── ui/components/
        └── lifecycle_stage.py           # STAGE_DEFINITIONS, STAGE_INPUT_OUTPUT_MAP, lookup functions —
                                          #   pure data only, imported directly by backend/main.py
```

## 3.4 Production Migration Notes

| Demo Component | Production Replacement | Effort |
|---|---|---|
| SQLite (local file) | PostgreSQL / Supabase — multi-instance, replicated | 1 day — swap connection string |
| OpenAI API only | Add Ollama (local GPU) — configure in Settings UI | 1 day — install Ollama, pull model |
| In-app metrics | Prometheus + Grafana (Docker) — persistent time-series | 2 days |
| Simulated ticketing | Real Jira/ServiceNow REST clients — see Section 15.2 for the existing (orphaned) model classes | 1 week |
| Single instance | Container autoscaling (Azure Container Apps / GCP Cloud Run) | 1 week |
| React bundle | Route-based code-splitting (currently one ~750KB chunk) | 1-2 days |

---

# 4. Navigation Architecture

## 4.1 Sidebar (Left Panel — Always Visible After Login)

**File**: `frontend/src/components/Sidebar.tsx`

```
🛡️  Securing AI
     Agentic AI Security Showcase
─────────────────────────────────
👤  [username]  [role]
─────────────────────────────────
🏠  Home
📊  Data Explorer
🤖  Agents
💬  Copilot
─────────────────────────────────
⚙️  Settings
📈  Token Usage
🔭  Observability
─────────────────────────────────
[LLM Badge]          🟢 GPT-4o-mini  OR  🟡 LLM: Not configured
─────────────────────────────────
AI Security Posture Index
     XX.X%
     Scoping: Complete · Status: Verified
─────────────────────────────────
[Phase Score Cards — 5 cards]
  🔎 Identify   XX%  ████░░
  🛡️ Protect    XX%  ████░░
  🚨 Detect     XX%  ███░░░
  🚑 Respond    XX%  █████░
  ♻️ Recover    XX%  ████░░
─────────────────────────────────
[🌙 Dark | ☀️ Light theme toggle]
[Logout Button]
```

The AI Security Posture Index and per-phase score bars come from `GET /api/dashboard`,
which calls `KPIEngine` fresh on every request against the live datasets — not hardcoded,
not cached client-side beyond React Query's normal staleness window.

## 4.2 Authentication

- `frontend/src/context/AuthContext.tsx` holds `{ username, role, token }`, persisted to
  `localStorage`; `frontend/src/lib/api.ts`'s `request()` attaches the token as a Bearer
  header on every call and force-redirects to `/login` on any `401`
- `POST /api/auth/login` (`backend/main.py`) checks `ADMIN_USERNAME`/`ADMIN_PASSWORD`
  (bootstrapped from `.env`, changeable at runtime — Section 28.8) and returns a
  self-rolled HMAC-signed opaque token (Section 28.4)
- Login page (`LoginPage.tsx`) renders before any routed content — an unauthenticated
  request to any other route redirects here
- Logout clears the stored token and redirects to `/login`; it does not call a backend
  endpoint (the token is simply discarded client-side — it stays valid server-side until
  its 12h TTL expires or the backend restarts with a new `SESSION_SECRET`)

## 4.3 Home Page — Horizontal Tab Layout

**File**: `frontend/src/components/TopTabs.tsx`

```
📊 Dashboard  |  🔎 Identify  |  🛡️ Protect  |  🚨 Detect  |  🚑 Respond  |  ♻️ Recover
```

Six React Router routes (`/`, `/phase/identify` … `/phase/recover`). `/` renders
`DashboardPage.tsx`; the five phase routes all render the same `PhaseWorkspace.tsx`
component, parameterised by the `:uc` route param.

## 4.4 Phase Page Structure — Standard Layout for All Five

**File**: `frontend/src/pages/PhaseWorkspace.tsx` — one component renders all 5 phases /
14 stages, driven entirely by `STAGE_UI_CONFIG` served from the backend (Section 28.5).
Every phase follows this exact layout:

```
[Phase Title + Accent Colour Header]
[Phase Overview Card — goal statement + framework badges]
[Horizontal Stage Progress Bar — clickable pills with ✅ for completed stages]
────────────────────────────────────────────────────────────────────
[Stage Header — Stage N of M | Stage Name | Stage Description]
────────────────────────────────────────────────────────────────────
[3-Column Input & Configuration Panel — see Section 6.1]
[Agent Scope Bar — agent name, expected analysis, expected output]
[🚀 Execute AI Analysis Button]
[Results — rendered after execution, 2 or 3 tabs]
  Tab 1: 🧠 AI Analysis
  Tab 2: 📋 Output & Handoff
  Tab 3: 🛠️ Remediation & Workflow  (final stage of each phase only)
```

Stage completion is tracked server-side (`AppState.completed_stages`, Section 23) —
completed stages show ✅ in the progress bar. A stage is disabled (`Execute` button
greyed out) until the previous stage in the same phase is completed — sequential gating,
not client-side-only. Clicking a completed stage pill navigates back to see its results.

---

# 5. Stage Objective Cards (All 14 Stages)

Every stage renders a phase overview card and stage header (Section 4.4) before any
input controls. The overview card contains: strategic goal statement, subtitle, and
active framework badges. Per-stage, the agent scope bar states the
business objective, expected AI analysis, and expected output.

## 5.1 Identify Stage Objectives

**Stage 1 — Shadow AI Discovery**
- Objective: Establish full visibility into every AI agent, copilot, and model running
  across the org — sanctioned or shadow — before any risk work can begin.
- AI Question: "Which AI systems exist in this environment, which are internet-facing,
  and which are unknown to the sanctioned registry (shadow AI)?"
- Input: Config/Repo/Network Scan Sources → `ai_agent_inventory` (300 rows)
- Output: AI Agent & Model Inventory with sanctioned-vs-shadow classification, LLM
  provider, and internet-facing exposure flags
- Frameworks: NIST AI RMF 1.0 (Map), MITRE ATLAS, OWASP LLM Top 10, ISO/IEC 42001

**Stage 2 — Model & Data Lineage Mapping**
- Objective: Trace every discovered model's base model, fine-tune dataset, and
  training-data source to classify data sensitivity and downstream blast radius.
- AI Question: "Where did this model's training data come from, how sensitive is it, and
  how many downstream systems consume it?"
- Input: AI Agent & Model Inventory
- Output: Model & Data Lineage Map (`model_data_lineage`, ~120 rows) with sensitivity
  classification and downstream consumer counts
- Frameworks: NIST AI RMF 1.0 (Map), MITRE ATLAS, OWASP LLM Top 10, ISO/IEC 42001

**Stage 3 — Agent Risk Scoring**
- Objective: Compose a single composite risk score per agent from permission scope,
  exposure, data sensitivity, and ownership gaps — so Protect/Detect/Respond can
  prioritise where guardrails matter most.
- AI Question: "Given permission scope, internet exposure, data sensitivity, and
  ownership status, what is this agent's composite risk score and blast radius?"
- Key Demo Moment: A Read-Only agent processing Regulated-PII with no owner outranks an
  Admin-scope agent with sanctioned, low-sensitivity access — permission scope alone is
  an insufficient risk proxy.
- Input: Model & Data Lineage Map
- Output: Agent Risk Register (`agent_risk_register`, 300 rows) with 0–100 risk scores
  and blast-radius ratings
- Frameworks: NIST AI RMF 1.0 (Measure), MITRE ATLAS, OWASP LLM Top 10, ISO/IEC 42001
- **HITL Gate**: Critical blast-radius agents require manual validation before handoff.

## 5.2 Protect Stage Objectives

**Stage 1 — Guardrail Proxy**
- Objective: Intercept every prompt/response through a guardrail proxy that filters
  prompt injection, jailbreaks, PII, and toxic content in real time.
- AI Question: "Which policy is triggered by this interaction, and what enforcement
  action (block/redact/flag/log) should be taken?"
- Input: Guardrail Policy Library → `guardrail_policies` (40 rows)
- Output: Guardrail Proxy Event Stream (`guardrail_events`, 800 rows) with policy
  attribution and action taken per event
- Frameworks: NIST AI RMF 1.0 (Govern/Manage), OWASP LLM Top 10, NIST SP 800-53 r5

**Stage 2 — Least-Privilege Tool Access**
- Objective: Audit every agent's granted tool permissions against a least-privilege
  baseline and flag over-provisioned access.
- AI Question: "Does this agent's granted permission exceed what it actually needs for
  its function, and what is the recommended downgrade?"
- Input: Guardrail Proxy Event Stream
- Output: Tool Permission Map (`tool_access_map`, 250 rows) with over-provisioning flags
- Frameworks: NIST SP 800-53 r5 (AC-6), OWASP LLM Top 10, NIST AI RMF 1.0

**Stage 3 — Secrets Isolation**
- Objective: Scan prompt history, code repositories, environment variables, and chat
  logs for API keys, credentials, and tokens reachable by an LLM.
- AI Question: "Is this secret isolated from LLM context, or is it exposed and
  exfiltratable through a jailbroken prompt?"
- Input: Tool Permission Map
- Output: Secrets Exposure Scan (`secrets_exposure_scan`, 60 rows) with isolation status
- Frameworks: OWASP LLM Top 10 (LLM02), NIST SP 800-53 r5 (IA-5), NIST AI RMF 1.0
- **HITL Gate**: Secrets classified Exposed/reachable by LLM context require manual
  rotation approval before handoff.

**Stage 4 — Policy-as-Code**
- Objective: Codify guardrail, access, and secrets findings into versioned, enforceable
  policy-as-code definitions ready for CI/CD-gated deployment.
- AI Question: "How should this cycle's findings be compiled into deployable,
  version-controlled policy?"
- Input: Secrets Exposure Scan
- Output: Policy-as-Code Package (updated `guardrail_policies`) mapped to OWASP LLM
  Top 10 references
- Frameworks: NIST AI RMF 1.0 (Govern), OWASP LLM Top 10, NIST SP 800-53 r5 (CM-3)

## 5.3 Detect Stage Objectives

**Stage 1 — Live Jailbreak & Injection Detection**
- Objective: Run a controlled adversarial prompt corpus against live agents to measure
  real-time jailbreak and prompt-injection detection rates.
- AI Question: "Was this adversarial payload detected live, and which MITRE ATLAS
  technique does it map to?"
- Input: Adversarial Prompt Corpus (`adversarial_prompt_corpus`, 500 rows)
- Output: Live Detection Results with per-payload outcome and confidence score
- Frameworks: MITRE ATLAS, OWASP LLM Top 10, NIST AI RMF 1.0 (Measure)

**Stage 2 — Anomalous Agent Behaviour Monitoring**
- Objective: Monitor agent action telemetry (tool calls, data access, external API
  calls) for statistically anomalous behaviour.
- AI Question: "Is this agent's action pattern consistent with its behavioural
  baseline, or does it show automated, non-human-paced misuse?"
- Key Demo Moment: An anomaly cluster concentrated in a narrow overnight window —
  a pattern consistent with automated agent misuse rather than normal usage variance.
- Input: Live Detection Results
- Output: Agent Behaviour Telemetry (`agent_behavior_telemetry`, 2,000 rows) with
  anomaly scores and baseline-deviation flags
- Frameworks: MITRE ATLAS, OWASP LLM Top 10, NIST AI RMF 1.0 (Measure)

**Stage 3 — Automated Red-Teaming**
- Objective: Run Garak/PyRIT-style automated adversarial campaigns against agents and
  compile outcomes into a red-team findings report.
- AI Question: "Which campaigns bypassed current guardrails, and what specific policy
  change would close the gap?"
- Key Demo Moment: Multi-turn jailbreak campaigns achieve a meaningfully higher bypass
  rate than single-turn static probes — multi-turn context tracking is the priority fix.
- Input: Agent Behaviour Telemetry
- Output: Red-Team Campaign Report (`redteam_campaign_results`, 200 rows) with
  Success/Blocked/Partial outcomes and remediation recommendations
- Frameworks: MITRE ATLAS, OWASP LLM Top 10, NIST AI RMF 1.0 (Measure)
- **HITL Gate**: Critical-severity successful bypasses require manual validation before
  handoff to Respond.

## 5.4 Respond Stage Objectives

**Stage 1 — Automated Containment**
- Objective: Automatically contain a flagged agent — isolate, revoke API key, disable
  tool access, or rate-limit — with HITL approval on high-risk actions.
- AI Question: "Given this incident's trigger and severity, what containment action is
  appropriate, and does it require human authorisation first?"
- Input: Security Incident Queue (`incident_queue`, 80 rows)
- Output: Containment Action Log (`containment_actions`, 120 rows) with automation and
  HITL-approval status per action
- Frameworks: NIST CSF 2.0 (RS.MI), NIST AI RMF 1.0 (Manage)
- **HITL Gate**: Critical-severity incidents require manual authorisation before
  containment executes.

**Stage 2 — SOAR Incident Playbook**
- Objective: Match each incident to a named SOAR playbook and execute it end to end,
  from trigger condition through resolution.
- AI Question: "Which playbook matches this incident's trigger condition, and what was
  the execution outcome?"
- Input: Containment Action Log
- Output: SOAR Playbook Execution Package (`soar_playbooks`, 15 named playbooks) with
  execution time and success rate
- Frameworks: NIST CSF 2.0 (RS.AN, RS.CO), NIST AI RMF 1.0 (Manage)

## 5.5 Recover Stage Objectives

**Stage 1 — Config & Prompt Rollback**
- Objective: Roll back an agent's prompt template, guardrail policy, or model config
  to the last known-good version snapshot.
- AI Question: "What is the last known-good snapshot for this agent, and is a clean
  rollback possible?"
- Input: Config Version Snapshots (`config_snapshots`, 100 rows)
- Output: Rollback Event Log (`rollback_events`, 40 rows) with source/target version,
  reason, and outcome
- Frameworks: NIST CSF 2.0 (RC.RP), NIST AI RMF 1.0 (Manage)
- **HITL Gate**: Config rollback always requires analyst authorisation.

**Stage 2 — Guardrail Update Loop**
- Objective: Convert red-team and incident root causes into deployed guardrail policy
  updates, closing the loop back into Protect with a measured effectiveness delta.
- AI Question: "What specific policy change addresses this finding's root cause, and
  how much did it improve the block rate?"
- Key Demo Moment: The Detect-phase multi-turn jailbreak gap is closed here — a
  deployed update with a measured before/after block-rate improvement.
- Input: Rollback Event Log
- Output: Guardrail Update Log (`guardrail_update_log`, 60 rows), feeding directly back
  into Protect's `guardrail_policies` library
- Frameworks: NIST CSF 2.0 (RC.IM), NIST AI RMF 1.0 (Manage)

---

# 6. Stage Panel — Detailed Layout Specification

## 6.1 Three-Column Input & Configuration Panel

Rendered inline in `frontend/src/pages/PhaseWorkspace.tsx` (the old Streamlit build's
`render_3col_input_panel()` no longer exists — its column contents were reorganised, not
ported 1:1).

**Column 1 — Ingestion & Filtering**
- Target ingested dataset box: input dataset name/description, row/column counts
  (`STAGE_INPUT_OUTPUT_MAP`, Section 8)
- "Received from Previous Stage" context block (stages after the first in a phase)
- Data source radio: `API/MCP Live Tools` / `File Upload Ingestion` / `Synthetic Data
  Engine` — selection is per-stage local React state, not persisted server-side.
  **Current gap**: File Upload is UI-selectable but not wired to `FileUploadProcessor`
  for per-stage analysis (it falls through to synthetic) — see Section 27.4. File
  upload *is* fully wired for the Copilot's RAG ingestion (Section 28.7), just not here.
- Category/type filter dropdown (`STAGE_UI_CONFIG.filter_options`, per stage)
- "🔍 Preview Input Data" — expands a live table of the filtered input dataset
  (`GET /api/datasets/{name}`, capped at 100 rows for the preview)
- "⬇️ Download Input CSV" — downloads the **full**, unfiltered input dataset
  (`GET /api/datasets/{name}/download`)

**Column 2 — Frameworks & Scenario**
- Active framework badges for this phase (e.g. NIST AI RMF 1.0, MITRE ATLAS)
- "Custom Threat Scenario / Scope Context" free-text textarea — UI-present, not
  currently sent to the backend or used by the LLM call

**Column 3 — Active Guardrails**
- "🟢 Structured JSON Extraction" — describes the response-parsing guardrail
  (Section 11.3's `_extract_json_text`/`_salvage_truncated_json`)
- "🟢 Hallucination Cross-Check" — describes the post-execution validation
  (Section 14, Tab 2)
- HITL gate status badge: "🟡 HITL Gate Active" or "🟢 Automated — Advisory", per stage
  (`STAGE_UI_CONFIG.hitl`)

## 6.2 Agent Scope Bar

Always visible before the Execute button. Shows: agent name, expected AI analysis,
expected output. Metadata comes from `get_agent_details_for_stage()` in
`app/ui/components/lifecycle_stage.py`, served via `GET /api/phases/{uc}/stages`, and
mirrors `agent_manager.py`'s `AGENT_NAME_MAP` (used for actual LLM routing).

Full agent catalogue — 14 agents, internally consistent between `agents_repo.py` and
`agent_manager.py` (a naming-drift issue present in the pre-Securing-AI version of this
app has been fixed):

**Identify (3 agents)**
| Agent | Stage | MITRE ATLAS Ref |
|---|---|---|
| ShadowAIDiscoveryAgent | Shadow AI Discovery | AML.T0034 (Discover LLM System Information) |
| LineageMappingAgent | Model & Data Lineage Mapping | AML.T0020 (Poison Training Data surface analysis) |
| AgentRiskScoringAgent | Agent Risk Scoring | N/A (Analytical / Risk Scoring) |

**Protect (4 agents)**
| Agent | Stage | MITRE ATLAS Ref |
|---|---|---|
| GuardrailProxyAgent | Guardrail Proxy | AML.T0051 (LLM Prompt Injection — defensive) |
| LeastPrivilegeAuditAgent | Least-Privilege Tool Access | N/A (Access Control Auditing) |
| SecretsIsolationAgent | Secrets Isolation | N/A (Credential Exposure Scanning) |
| PolicyAsCodeAgent | Policy-as-Code | N/A (Policy Codification) |

**Detect (3 agents)**
| Agent | Stage | MITRE ATLAS Ref |
|---|---|---|
| InjectionDetectionAgent | Live Jailbreak & Injection Detection | AML.T0051, AML.T0054 |
| BehaviorMonitoringAgent | Anomalous Agent Behaviour Monitoring | AML.T0034 |
| RedTeamOrchestratorAgent | Automated Red-Teaming | AML.T0048, AML.T0043 |

**Respond (2 agents)**
| Agent | Stage | MITRE ATLAS Ref |
|---|---|---|
| ContainmentAgent | Automated Containment | N/A (Containment / Active Defense) |
| SOARPlaybookAgent | SOAR Incident Playbook | N/A (Incident Response Orchestration) |

**Recover (2 agents)**
| Agent | Stage | MITRE ATLAS Ref |
|---|---|---|
| RollbackAgent | Config & Prompt Rollback | N/A (Recovery / Configuration Management) |
| GuardrailUpdateAgent | Guardrail Update Loop | N/A (Closed-Loop Policy Update) |

## 6.3 Execute AI Analysis

- Large primary action button: "🚀 Execute AI Analysis" — disabled until the previous
  stage in the same phase is completed (sequential gating, Section 4.4)
- On click: `POST /api/phases/{uc}/stages/{stage}/run` → `AgentManager.run_stage()`
  (Section 11.3) → response includes the outcome, HITL requirement, and output preview
- React Query mutation state drives the button's "Running…" label; no separate
  step-by-step progress indicator UI (the old Streamlit build's 3-step progress bar
  was not ported — the call is a single request/response round trip)
- On completion: result cached client-side in local component state, and persisted
  server-side in `AppState.stage_outputs`/`completed_stages` (Section 23) so a page
  refresh or revisit still shows the completed stage

## 6.4 Results Panel

Results render in 2 or 3 tabs depending on stage.

### Tab 1: 🧠 AI Analysis

- **Synthetic data banner** (when active): amber warning strip
- **"Includes real live data from…" badge** when any MCP tool contributed live data
- **Explicit error banner** if agent execution failed (`outcome.error` — the panel
  never crashes or goes blank, Section 11.3)
- **4 metric cards**: AI Confidence, Findings count, Critical count, Recommendations
  count — computed from the actual returned outcome, not separately faked
- **Analysis Summary** — markdown-rendered narrative with framework citations
- **AI-Scored Findings Catalog** — cards with severity badges, evidence, and
  per-finding recommendation
- **Under the Hood: Agent Execution Trace** — numbered step list, when returned
- **Recommended Action Plan** — bulleted next steps
- **Chart** — when `STAGE_UI_CONFIG.chart` is configured for the stage

### Tab 2: 📋 Output & Handoff

Rendered from `STAGE_INPUT_OUTPUT_MAP` (`app/ui/components/lifecycle_stage.py`).

- Output dataset name, description, row/column counts
- "⬇️ Download Output CSV" — downloads the **full** output dataset
  (`GET /api/datasets/{name}/download`)
- Table preview of the output dataset (capped at 25 rows in the run-stage response)
- Handoff text naming what the next stage receives

### Tab 3: 🛠️ Remediation & Workflow (Final Stage of Each Phase Only)

Rendered only at: Identify → Agent Risk Scoring, Protect → Policy-as-Code,
Detect → Automated Red-Teaming, Respond → SOAR Incident Playbook,
Recover → Guardrail Update Loop.

See Section 15 for the full mechanism — a simulated 3-state ticket flow
(Approval Queue → Implementation Tracking → Completed & Verified) with mock
Jira/ServiceNow reference numbers.

---

# 7. Phase-Level KPI Specifications (All 5 Phases)

KPI cards are displayed identically across every stage within a phase — computed live
by `KPIEngine` (Section 17) on every dashboard/phase request, not per-stage or cached.

| Phase | KPI 1 | KPI 2 | KPI 3 | KPI 4 |
|---|---|---|---|---|
| Identify | Shadow AI Discovery Rate | High-Risk Agent Rate | Lineage Coverage Rate | Avg Agent Risk Score |
| Protect | Guardrail Block Rate | Least-Privilege Compliance Rate | Secrets Isolation Rate | PII Redaction Rate |
| Detect | Jailbreak Detection Rate | Red-Team Attack Success Rate | MTTD (Mean Time to Detect) | Anomaly Detection Coverage |
| Respond | Automated Containment Rate | MTTC (Mean Time to Contain) | Playbook Success Rate | HITL Approval Rate |
| Recover | Rollback Success Rate | Guardrail Update Coverage | Effectiveness Improvement | Config Snapshot Coverage |

---

# 8. Input/Output Dataset Flow (All 14 Stages)

Sourced from `STAGE_INPUT_OUTPUT_MAP` in `lifecycle_stage.py`. This map drives the
handoff card in Tab 2 and the "Received from Previous Stage" context block.

## 8.1 Identify Dataset Flow

```
ai_agent_inventory (300 rows)
  → [Shadow AI Discovery] → ai_agent_inventory (self — classified sanctioned/shadow)
  → [Lineage Mapping] → model_data_lineage (~120 rows)
  → [Risk Scoring] → agent_risk_register (300 rows)
```

## 8.2 Protect Dataset Flow

```
guardrail_policies (40 rows)
  → [Guardrail Proxy] → guardrail_events (800 rows)
  → [Least-Privilege] → tool_access_map (250 rows)
  → [Secrets Isolation] → secrets_exposure_scan (60 rows)
  → [Policy-as-Code] → guardrail_policies (updated — loops back)
```

## 8.3 Detect Dataset Flow

```
adversarial_prompt_corpus (500 rows)
  → [Injection Detection] → adversarial_prompt_corpus (self — live detection outcomes)
  → [Behavior Monitoring] → agent_behavior_telemetry (2,000 rows)
  → [Red-Teaming] → redteam_campaign_results (200 rows)
```

## 8.4 Respond Dataset Flow

```
incident_queue (80 rows)
  → [Containment] → containment_actions (120 rows)
  → [Incident Playbook] → soar_playbooks (15 rows)
```

## 8.5 Recover Dataset Flow

```
config_snapshots (100 rows)
  → [Rollback] → rollback_events (40 rows)
  → [Guardrail Update] → guardrail_update_log (60 rows) → feeds back into Protect
```

---

# 9. Data Architecture

## 9.1 Data Ingestion Hierarchy

```
Priority 1 — API/MCP Live Tools
  REST API call → MCPClient (mock/live dispatch) → Normalised DataFrame

Priority 2 — File Upload
  Uploaded file → FileUploadProcessor → Parsed text/DataFrame

Priority 3 — Synthetic Data
  SyntheticDataEngine → Generated DataFrame
  [SYNTHETIC DATA watermark active everywhere]
```

## 9.2 FAISS Index Architecture — Wired Into the Live Copilot

`app/rag/collections.py` and `app/rag/indexes.py` define one FAISS `IndexFlatIP`
collection per synthetic dataset (16, matching `app/data/generator.py`'s dataset names
exactly) plus a 17th `"uploads"` collection for analyst-uploaded documents. Unlike an
earlier version of this platform where this layer existed as unused scaffolding, it is
now the real retrieval engine behind the Copilot's hybrid semantic + BM25 search — see
Section 28.7 for the full ingestion/caching/query pipeline.

```python
DATASET_COLLECTIONS = [
    "ai_agent_inventory", "model_data_lineage", "agent_risk_register",
    "guardrail_policies", "guardrail_events", "tool_access_map", "secrets_exposure_scan",
    "adversarial_prompt_corpus", "agent_behavior_telemetry", "redteam_campaign_results",
    "incident_queue", "containment_actions", "soar_playbooks",
    "config_snapshots", "rollback_events", "guardrail_update_log",
]  # + "uploads", 17 total — each {"vector_size": 1536, "distance": "Cosine"}
```

## 9.3 Framework References

`app/data/compliance_frameworks.yaml` holds a phase-keyed reference: MITRE ATT&CK/ATLAS
technique lists (consumed by `HallucinationDetector` to build its authoritative
technique-ID set — the only part of the YAML actually read by code) plus NIST AI RMF 1.0
and NIST CSF 2.0 documentation sections (human-reference only, not parsed).

| Phase | Key Techniques Cited |
|---|---|
| Identify | AML.T0034, AML.T0007, AML.T0020, T1592, T1590 |
| Protect | AML.T0051, AML.T0054, AML.T0053, T1552, T1078 |
| Detect | AML.T0051, AML.T0054, AML.T0048, AML.T0043, AML.T0024, AML.T0034 |
| Respond | AML.T0048, T1531, T1489 |
| Recover | AML.T0020, T1490 |

## 9.4 Synthetic Data Engine

**File**: `app/data/generator.py` — `SyntheticDataEngine(seed: Optional[int] = 42)`
- Seed defaults to 42 for reproducible demos; `generate_all()` regenerates all 16
  datasets deterministically for a given seed
- All 16 datasets cross-linked via shared `agent_id`/dataset-specific foreign keys
- Every generator method follows the same convention: seeded `np.random`, weighted
  `np.random.choice` for categoricals, prefix+incrementing-index IDs (`AGT-1000`,
  `GRD-50000`, etc.)

**16 Datasets (by phase):**
- Identify (3): `ai_agent_inventory` (300), `model_data_lineage` (~120), `agent_risk_register` (300)
- Protect (4): `guardrail_policies` (40), `guardrail_events` (800), `tool_access_map` (250), `secrets_exposure_scan` (60)
- Detect (3): `adversarial_prompt_corpus` (500), `agent_behavior_telemetry` (2,000), `redteam_campaign_results` (200)
- Respond (3): `incident_queue` (80), `containment_actions` (120), `soar_playbooks` (15)
- Recover (3): `config_snapshots` (100), `rollback_events` (40), `guardrail_update_log` (60)

---

# 10. Fallback Content — What Renders When the LLM Doesn't

There is no separate "always compute rich content from live stats" engine in the
current build (the old Streamlit build's `interactive_demo.py:_build_data_driven_content()`,
with its `_rows()`/`_unique()`/`_count_where()`/`_count_true()` helpers, was deleted along
with the rest of that file). Two genuinely different situations instead:

- **No LLM router configured** (missing/invalid `OPENAI_API_KEY`): `agent_manager.py`'s
  `_node_call_llm` falls back to `_generate_synthetic_response()` — hand-authored,
  realistic findings/summary/recommendations per phase/stage (Section 11.3's
  `findings_map`/`summaries`/`recommendations_map`). This is genuinely rich, specific
  content (real-looking finding IDs, evidence, framework citations) — just not
  recomputed from live dataset statistics on every call.
- **LLM call fails at runtime** (expired key, rate limit, network error): `run_stage()`
  returns `_error_outcome()` — `ai_confidence=0`, an empty findings list, and a summary
  string naming the error. The Results panel still renders its full structure (4 metric
  cards, findings section, etc.) around that sparse content plus a visible error banner
  — it never crashes or goes blank — but it does **not** fabricate findings to fill the
  gap the way the old Streamlit build's data-driven engine did.

KPI cards, gauges, and dashboard numbers are unaffected either way — those are computed
fresh by `KPIEngine` directly from the dataset DataFrames on every request (Section 17),
independent of whether any given stage's LLM call succeeded.

---

# 11. LLM Architecture

## 11.1 LLM Router

**File**: `app/llm/router.py` — `LLMRouter`, 3-tier:
- **Primary** (`gpt-4o-mini`): agent discovery, lineage mapping, guardrail enforcement,
  general orchestration
- **Local** (Ollama, e.g. `llama3.1:8b`): air-gapped option, gracefully falls back to
  Primary if the local Ollama server is unreachable
- **Reasoning** (`gpt-4o`): routed to for the **Detect** and **Respond** phases, where
  deeper adversarial reasoning matters (`model_tier = "reasoning" if use_case in
  ["detect", "respond"] else "primary"`)

All calls are tracked by `TokenUsageTracker` (SQLite) and `InAppMetrics` (session health).

## 11.2 System Prompt Standards (All 14 Stage Prompts)

All stage system prompts in `agent_manager.py` follow these rules:

1. **Data source declaration** (first sentence): `SYNTHETIC` / `MCP LIVE` / `FILE UPLOAD`
2. **Lifecycle stage context**: "You are {AgentName}, a senior security AI agent within
   the Securing AI — {Phase} pipeline"
3. **AI Confidence Score**: Dynamic 40–99%, integer, clamped server-side. Variance
   across findings is mandatory — static values are a prompt violation.
4. **Specificity**: Remediation/recommendations must be specific and actionable, not
   generic advice
5. **False positive discipline**: findings are grounded in the aggregated dataset
   statistics injected into the prompt (Section 10), not invented
6. **Output format**: strict JSON matching the `AgentOutcome` dict schema (Section 11.3)

## 11.3 AgentManager — LangGraph Pipeline

**File**: `app/runtime/agent_manager.py`

Unlike a naive per-stage dispatch table, `AgentManager` compiles a single shared
4-node LangGraph `StateGraph` once at construction and invokes it for every stage call:

```python
class AgentState(TypedDict):
    use_case: str
    stage: str
    data_source: str
    datasets: Dict[str, Any]
    aggregation: Dict[str, Any]
    system_prompt: str
    task_prompt: str
    raw_response: str
    outcome: Dict[str, Any]
    error: Optional[str]

class AgentManager:
    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("pre_aggregate", self._node_pre_aggregate)   # Pandas stats, zero LLM cost
        graph.add_node("build_prompts", self._node_build_prompts)   # system + task prompt
        graph.add_node("call_llm", self._node_call_llm)             # real call, or synthetic fallback if no router
        graph.add_node("format_outcome", self._node_format_outcome) # parse + clamp confidence
        graph.set_entry_point("pre_aggregate")
        graph.add_edge("pre_aggregate", "build_prompts")
        graph.add_edge("build_prompts", "call_llm")
        graph.add_edge("call_llm", "format_outcome")
        graph.add_edge("format_outcome", END)
        return graph.compile()

    def run_stage(self, use_case: str, stage: str, datasets: dict, data_source: str) -> Dict[str, Any]:
        """Invokes the compiled graph. Also runs HallucinationDetector on the output text,
        logs to AuditLogger and InAppMetrics, and persists the result to ShortTermMemory."""
```

**No LLM router configured** (e.g. missing/invalid `OPENAI_API_KEY`): `_node_call_llm`
falls back to `_generate_synthetic_response()` — a hand-authored JSON response per
phase/stage drawn from `findings_map`, `summaries`, and `recommendations_map` dicts,
so the demo runs convincingly with zero API calls.

**LLM call fails at runtime** (e.g. expired key, rate limit): the exception propagates
to `run_stage`, which returns `_error_outcome()` — `ai_confidence=0`, a summary string
of `"Agent execution failed: {error}"`, and an empty findings list. The React results
panel still renders its normal structure (metric cards, findings section) around that
sparse content, plus the visible error banner — see Section 10 for how this differs from
the "no LLM configured at all" fallback path, which is genuinely rich.

The `AGENT_NAME_MAP` and `FRAMEWORK_REFS` module-level dicts key every phase by its
snake_case identifier (`identify`, `protect`, `detect`, `respond`, `recover`):

```python
FRAMEWORK_REFS = {
    "identify": "NIST AI RMF 1.0 (Map), MITRE ATLAS, OWASP LLM Top 10, ISO/IEC 42001",
    "protect":  "NIST AI RMF 1.0 (Govern/Manage), OWASP LLM Top 10, NIST SP 800-53 r5",
    "detect":   "MITRE ATLAS, OWASP LLM Top 10, NIST AI RMF 1.0 (Measure)",
    "respond":  "NIST CSF 2.0 (Respond), NIST AI RMF 1.0 (Manage)",
    "recover":  "NIST CSF 2.0 (Recover), NIST AI RMF 1.0 (Manage)",
}
```

---

# 12. Guardrails

## Layer 1 — Pydantic v2 Structured Output (defined, not wired into the live call path)

`app/guardrails/validator.py` defines a generic `AgentOutcome` Pydantic model
(`lifecycle_stage`, `data_source`, `analysis_markdown`, `metrics: List[MetricCard]`,
`data_grid`, `ai_confidence`, `confidence_rationale`) plus `GuardrailManager.validate_output()`
for schema validation with one auto-retry. **This validator class is not currently
called from `agent_manager.py`'s real `_format_outcome()`**, which does its own manual
JSON parsing and confidence clamping (Section 11.3) directly on a plain dict — a
pre-existing gap inherited from the earlier version of this app, not introduced by the
Securing AI content rewrite. Reconnecting these two paths is a good first production
hardening task.

## Layer 2 — Content Safety

- Regex PII scan (email, SSN, credit card, phone, IP) on all screened input
- Regex prompt-injection pattern scan ("ignore previous instructions", jailbreak
  phrases, etc.)
- OpenAI Moderation API — best-effort, only called if `OPENAI_API_KEY` is set
- Detect-phase red-teaming outputs are description-only (no executable payloads
  rendered as runnable code)

## Layer 3 — Human-in-the-Loop (HITL)

One HITL gate per phase, defined in `app/guardrails/validator.py`'s `GuardrailManager.
check_hitl_required()` / `V5_THRESHOLDS` dict, called by `backend/main.py`'s run-stage
endpoint after every execution:

```python
V5_THRESHOLDS = {
    "identify_stage3": {"condition": "blast_radius == Critical", "confidence_floor": 85},
    "protect_stage3":  {"condition": "isolation_status == Exposed AND exposed_to_llm", "confidence_floor": 85},
    "detect_stage3":   {"condition": "outcome == Success AND severity == Critical", "confidence_floor": 80},
    "respond_stage1":  {"condition": "severity == Critical", "confidence_floor": 85},
    "recover_stage1":  {"condition": "reason is Critical-sourced", "confidence_floor": 85},
}
```

When triggered, the run-stage response includes `hitl_required: true` and a list of
candidate findings; `PhaseWorkspace.tsx` renders the gate:
```
⚠️ Human-in-the-Loop Gate — {Stage Name}
[Findings requiring approval, with severity + confidence per item]
[✅ Approve & Proceed]    [❌ Reject & Review]
```
The decision posts to `POST /api/phases/{uc}/stages/{stage}/hitl`, stored in
`AppState.hitl_approved` and written to `audit_log.db` + `InAppMetrics`.

## Layer 4 — Synthetic Data Watermark

Confirmed current location: an amber banner in the AI Analysis results tab
("⚠️ Synthetic Data — This analysis uses AI-generated demonstration data.",
`frontend/src/pages/PhaseWorkspace.tsx`, `.synthetic-banner` in `theme.css`), shown
whenever the selected data source is `synthetic` (the default). The old Streamlit
build additionally desaturated accent colours and showed watermark badges in 3 more
locations (sidebar, Column 3, a per-result blockquote) — that multi-location treatment
was not ported to React; only the one AI Analysis banner currently exists.

---

# 13. Short-Term Memory

**File**: `app/memory/short_term.py` — `ShortTermMemory`, unchanged infrastructure from
the pre-Securing-AI build.

## 13.1 Purpose

- Copilot remembers context from previous conversations within the session window
- Stage analysis results are recalled across browser sessions (within 48h)
- Conversation continuity — e.g. "what did we find in the last Identify scan?"

## 13.2 What Gets Stored

| Entry Type | Key | Value | TTL |
|---|---|---|---|
| `stage_result` | `{phase}_{stage}` | AgentOutcome (JSON) | 48h |
| `copilot_message` | `msg_{timestamp}` | {role, content} | 48h |
| `finding_context` | `{phase}_{stage}_findings` | Top findings from last analysis | 48h |
| `kpi_snapshot` | `{phase}_{stage}_kpis` | KPI values at analysis time | 48h |

---

# 14. Observability — Full In-App Dashboard

**File**: `frontend/src/pages/ObservabilityPage.tsx`, served by `GET /api/observability`
**Sidebar label**: 🔭 Observability

Four tabs (a fifth, Token Usage, is also reachable as its own standalone sidebar page).

## Tab 1 — LangSmith Traces

Real-time `LANGCHAIN_TRACING_V2`/`LANGCHAIN_API_KEY` sync check; recent-runs table
(agent, status, latency, tokens); offline fallback to in-session trace log when
LangSmith isn't configured; deep-link to `https://smith.langchain.com/projects/p/{project}`.

## Tab 2 — Hallucination Detection

**File**: `app/observability/hallucination.py`

```python
class HallucinationDetector:
    def validate_cve_ids(self, text: str) -> List[HallucinationFlag]:
        """Extract CVE IDs (if any are cited) and validate against the NVD API."""

    def validate_attack_techniques(self, text: str) -> List[HallucinationFlag]:
        """Extract T-codes AND AML.T-codes; validate against compliance_frameworks.yaml's
        flattened technique-ID set (regex: \\b(?:AML\\.T\\d{4}(?:\\.\\d{3})?|T\\d{4}(?:\\.\\d{3})?)\\b)."""

    def validate_asset_references(self, text: str, asset_df: pd.DataFrame) -> List[HallucinationFlag]:
        """Validate cited agent/host identifiers against the ai_agent_inventory dataset."""

    def run_all(self, text: str, asset_df: pd.DataFrame = None) -> HallucinationReport: ...
```

`agent_manager.py` calls `run_all()` after every stage execution, passing
`datasets["ai_agent_inventory"]` as `asset_df`. The Verification Validator Status
cards on this tab check three source strings — `"NVD"`, `"MITRE"`, `"Agent"` — against
flagged citations to render VALIDATED/WARNING per validator.

## Tab 3 — Health Metrics

4 health KPI cards (LLM Success Rate / Avg Latency / P95 Latency / Active Session);
latency histogram; RAG-score distribution — real now, sourced from the Copilot's
actual hybrid FAISS+BM25 retrieval scores (Section 28.7), not decorative; guardrail
events table; HITL decision pie.

## Tab 4 — Security Audit Trail

**File**: `app/observability/audit_logger.py`

Events logged: `hitl_decision`, `guardrail_violation`, agent stage execution
initiated/completed/failed. Filterable table, status/user distribution charts, CSV export.

---

# 15. Remediation System

## 15.1 Active Mechanism — Simulated Ticket State Machine

Every phase's final stage (Section 6.4, Tab 3) uses a 3-state workflow, client-side in
`frontend/src/pages/PhaseWorkspace.tsx` (`WorkflowState`), backed by a real dispatch
call — **not** a live Jira/ServiceNow API integration:

```ts
interface WorkflowState {
  status: "APPROVAL QUEUE" | "IMPLEMENTATION TRACKING" | "COMPLETED & VERIFIED";
  jira?: TicketResult;
  servicenow?: TicketResult;
}
```

"✅ Approve & Dispatch" calls `POST /api/phases/{uc}/stages/{stage}/dispatch-tickets`
(`backend/main.py`), which calls `MCPClient.create_ticket()` (Section 24) for both
`jira` and `servicenow` — live if their env vars are configured, a realistic mock
ticket reference otherwise, never silently presenting a mock as real. "✅ Verify &
Close" then moves
the state to `COMPLETED & VERIFIED` client-side only. **Current gap**: workflow state
lives in React component state, not persisted server-side — a page refresh resets it
to `APPROVAL QUEUE` even for a stage already dispatched (Section 27.4).

## 15.2 Legacy — `RemediationWorkflowEngine` (Deleted)

A more elaborate Path A implementation existed from the pre-Securing-AI Streamlit
build — Pydantic `RemediationTicketSpec`/`WorkflowItem` models, an Approval Queue /
Kanban / Analytics 3-tab UI. It was never imported by any current page (dead code even
before the Streamlit removal) and was deleted along with the rest of `app/workflow/`
when Streamlit was retired. If a richer Kanban/analytics remediation view is wanted for
React, it would need to be built fresh against `backend/main.py`'s dispatch-tickets
endpoint (Section 15.1) rather than resurrected from this file.

## 15.3 Path B — Proposed (Not Implemented)

Shown as a greyed-out glass card in the UI concept, never built:
- Pre-Action Impact Assessment (exact API call, target, payload, blast radius)
- Single scroll-gated approval button
- Execution + post-remediation verification grid
- Estimated build effort: 3–4 weeks; requires real MCP write credentials

---

# 16. Settings Page

**File**: `frontend/src/pages/SettingsPage.tsx`, `GET`/`POST /api/settings`
**Sidebar label**: ⚙️ Settings
**Sections on one page** (not tabs): 🔑 Core API Configuration | 🤖 LLM Routing
Framework | 🔌 MCP Integrations | 🔐 Login Credentials

Persistence mechanism is `SettingsStore` (SQLite), not a `.env` file writer — see
Section 28.8 for the full explanation of why and how.

## Core API Configuration

`OPENAI_API_KEY`, LangSmith tracing toggle, `LANGCHAIN_PROJECT`. Saving takes effect
immediately (no restart) because `SettingsStore.set()` writes straight into
`os.environ` and reconstructs the cached `LLMRouter`.

## LLM Routing Framework

| Tier | Field | Used For |
|---|---|---|
| Tier 1: Primary | Model name (default `gpt-4o-mini`) | Identify/Protect phases, general orchestration |
| Tier 2: Local (Ollama) | Model name + base URL | Air-gapped option; falls back to Primary if unreachable |
| Tier 3: Reasoning | Model name (default `gpt-4o-mini`) | Detect/Respond phases |

Each tier shows a live 🟢 Available / 🟡 status badge from `GET /api/settings`.
`gpt-4o` is intentionally disabled for demo cost control — entering it resolves to
`gpt-4o-mini` instead of actually calling GPT-4o (`app/llm/router.py`'s `_demo_safe()`).

## MCP Integrations

Iterates `MCPToolRegistry().tools` generically (no hardcoded phase filter) and groups
cards by `tool.category`:

| Category | Tools |
|---|---|
| AI Security | AI-SPM Scanner, Protect AI Guardian, HiddenLayer AISec, Lakera Guard, Guardrails AI, Garak (NVIDIA), PyRIT (Microsoft), SOAR Platform |
| Remediation | Jira, ServiceNow |

Per-tool card: display name, connection status (🟢 Live / 🔵 Mock Fallback), category,
capabilities, and a credentials expander for each `required_env_var`.

---

# 17. KPI Engine

**File**: `app/kpi/engine.py`

| Phase | KPI | Formula |
|---|---|---|
| Identify | Shadow AI Discovery Rate | % agents classified Shadow AI |
| Identify | High-Risk Agent Rate | % agents rated High/Critical blast radius |
| Identify | Lineage Coverage Rate | min(100, lineage rows / agent rows × 100) |
| Identify | Avg Agent Risk Score | Mean composite risk score (0–100) |
| Protect | Guardrail Block Rate | % enforcement events resulting in Blocked |
| Protect | Least-Privilege Compliance Rate | % tool grants NOT over-provisioned |
| Protect | Secrets Isolation Rate | % secrets Isolated or Remediated |
| Protect | PII Redaction Rate | % PII-Detected events Redacted or Blocked |
| Detect | Jailbreak Detection Rate | % adversarial payloads detected live |
| Detect | Red-Team Attack Success Rate | % campaigns with outcome=Success |
| Detect | MTTD | Real mean delta: `incident_queue.detected_at − incident_queue.occurred_at`, hours (falls back to 1.6 only if `incident_queue` is missing/empty) |
| Detect | Anomaly Detection Coverage | % unique agents represented in telemetry |
| Respond | Automated Containment Rate | % containment actions with automated=True |
| Respond | MTTC | Real mean delta: `containment_actions.timestamp − matched incident's detected_at`, hours (falls back to 1.2 only if data is missing/empty) |
| Respond | Playbook Success Rate | Mean `success_rate` across soar_playbooks |
| Respond | HITL Approval Rate | % containment actions with hitl_approved=True |
| Recover | Rollback Success Rate | % rollback_events with outcome=Success |
| Recover | Guardrail Update Coverage | min(100, updated policies / total policies × 100) |
| Recover | Effectiveness Improvement | Mean `effectiveness_delta` across updates |
| Recover | Config Snapshot Coverage | % snapshots with rollback_available=True |

**Composite phase scores** (`get_use_case_score(uc)`, weighted sum of that phase's KPIs,
clamped to [0, 100]):

```python
identify: (100 - shadow_rate) * 0.4 + (100 - high_risk) * 0.35 + lineage_cov * 0.25
protect:  block_rate * 0.4 + lp_compliance * 0.3 + secrets_iso * 0.3
detect:   jailbreak_rate * 0.35 + (100 - attack_success) * 0.35 + anomaly_cov * 0.3
respond:  auto_rate * 0.4 + playbook_success * 0.35 + hitl_rate * 0.25
recover:  rollback_success * 0.45 + update_cov * 0.30 + snap_cov * 0.25
```

**AI Security Posture Index** (`get_ai_readiness_index()`) — the unweighted mean of the
five phase scores. Called by the sidebar and Executive Dashboard on every render.

---

# 18. Executive Dashboard

**File**: `frontend/src/pages/DashboardPage.tsx`, `GET /api/dashboard`

1. Hero banner — "AI Security Command Center", gradient title
2. Phase Score Gauges — 5 SVG gauges (Identify/Protect/Detect/Respond/Recover),
   `frontend/src/components/ui.tsx`'s `Gauge` component
3. Operational Performance Index — 6 progress cards: AI Security Posture Index, Shadow
   AI Containment Rate, Guardrail Enforcement Efficacy, Red-Team Bypass Resistance,
   Automated Containment Rate, Rollback & Recovery Reliability
4. Operational KPIs & Technical Performance table — all 20 raw KPIs grouped by phase,
   with dynamic OPTIMAL/STABLE/WARNING/CRITICAL/DEFICIT status badges (lower-is-better
   logic applied specifically to Red-Team Attack Success Rate, MTTD, MTTC, and Avg Agent
   Risk Score; points-based logic for Effectiveness Improvement)
5. 30-Day Score Optimisation Timeline — line chart, one series per phase. **Real
   recorded history**, not a fabricated random walk: `app/observability/score_history.py`
   (`ScoreHistoryStore`, SQLite) upserts one row per phase per calendar day, computed
   fresh from `KPIEngine` on every dashboard load — restarting the backend multiple
   times in one day just overwrites that day's row, it doesn't fake extra trend points
6. Agent Risk Blast-Radius Profile — donut chart from `agent_risk_register`
   (Critical/High/Medium/Low)
7. Recent AI Operations & HITL Actions table — pulled live from `AuditLogger`, with a
   4-row structured fallback when the audit log is still empty

The old Streamlit build additionally showed 8 "Executive KPI Cards" in CXO language
(e.g. "IDENTIFY — SHADOW AI CONTROL") — not ported to React; the Operational
Performance Index cards (item 3) cover similar ground with more direct KPI names.

---

# 19. Copilot

**File**: `frontend/src/pages/CopilotPage.tsx`, `POST /api/copilot/message`
**Sidebar label**: 💬 Copilot

**This section previously described a keyword/substring-search implementation
(`search_local_data_rag`, branching on words like "agent"/"guardrail"/"redteam" over 4
Pandas datasets) from the retired Streamlit build. That implementation no longer
exists — see Section 28.7 for the current real hybrid FAISS + BM25 retrieval engine,
which searches all 16 datasets plus uploads, not 4 keyword-gated ones.**

What's still accurate:
- 48-hour memory: recalls recent stage analyses, findings, and KPI snapshots into the
  system prompt for conversational continuity (`app/memory/short_term.py`)
- File upload **is** wired to the ingestion pipeline now — `POST /api/copilot/upload`
  chunks and embeds uploaded documents into the Copilot's "uploads" collection
  (Section 28.7), unlike per-stage file upload (Section 6.1's noted gap)
- 6 starter "Try asking" buttons (`backend/data_content.py:COPILOT_STARTER_QUESTIONS`):
  - "Which agents are Shadow AI?"
  - "What's our guardrail block rate this week?"
  - "Show the latest red-team campaign results"
  - "Which agents are highest risk right now?"
  - "Show MITRE ATLAS technique distribution"
  - "Which agents had a recent rollback?"
- Persona: "Antigravity Copilot" (unchanged naming from the earlier build)
- All calls tracked by `TokenUsageTracker`

---

# 20. Agents Repository Page

**File**: `frontend/src/pages/AgentsPage.tsx`, `GET /api/agents`
**Sidebar label**: 🤖 Agents

Displays the full 14-agent catalogue (Section 6.2) grouped by phase via a horizontal
tab selector (Identify / Protect / Detect / Respond / Recover). Per agent: name, stage,
role description, MITRE ATLAS reference. **Not ported to React**: the old Streamlit
build's "Live Sandbox Console" (an editable system-prompt textarea + mocked execution
trace) — the React page is catalogue-only; running an agent for real means going to its
phase and clicking Execute (Section 6.3).

---

# 21. Data Explorer Page

**File**: `frontend/src/pages/DataExplorerPage.tsx`, `GET /api/datasets`,
`GET /api/datasets/{name}`
**Sidebar label**: 📊 Data Explorer

- Phase selector (Identify / Protect / Detect / Respond / Recover) → dataset card
  selector (all 16 synthetic datasets, grouped per Section 9.4)
- Row count, column count summary card
- Interactive table browse (capped at 200 rows) with a free-text search box
  (`?q=` param, substring match across all columns)
- "⬇️ Download CSV" button — full, unfiltered dataset via
  `GET /api/datasets/{name}/download` (not the capped/filtered preview)

---

# 22. UI/UX Design System

**File**: `frontend/src/theme.css` — CSS custom properties, dark theme as `:root`
default, light theme as a `:root[data-theme="light"]` override. Toggled by
`frontend/src/context/ThemeContext.tsx`'s `useTheme()` hook, persisted to
`localStorage["securing_ai_theme"]`.

```css
/* Dark theme (default) */
--bg-primary:    #0a0e27;
--bg-secondary:  #111638;
--accent-blue:   #00d4ff;   /* Identify */
--accent-green:  #00ff88;   /* Protect */
--accent-red:    #ff4444;   /* Detect */
--accent-purple: #a855f7;   /* Respond */
--accent-teal:   #14b8a6;   /* Recover */
--accent-amber:  #ffaa00;   /* HITL gates, warnings */
--accent-orange: #ff6b35;   /* Synthetic data watermark */
--text-primary:  #ffffff;
--text-secondary: #d1d1e0;
--text-muted:    #8c8cab;
--border-glass:  rgba(255, 255, 255, 0.08);
```

- Dark + light glassmorphism cards, Inter font (JetBrains Mono for code/rule blocks)
- RAG colour coding: Green ≥80, Amber ≥60, Red <60
- **Light theme contrast fix**: the 5 phase accent colours are hand-tuned for a
  near-black background and are genuinely unreadable as text on the light theme's
  near-white background (verified: as low as ~1.8:1 contrast, WCAG AA needs 4.5:1).
  `frontend/src/lib/color.ts`'s `readableAccent(colour, theme)` computes real WCAG
  contrast ratio against the light background and iteratively darkens (HSL lightness,
  55%→10% in 2% steps) until it clears 4.5:1 — used for text only; borders/backgrounds
  keep the raw accent colour, which is forgiving of vividness either way. Dark theme
  and any `var(--...)` colour reference pass through unchanged.
- Stage progress bar: horizontal pills, ✅ for completed, clickable navigation
- `frontend/src/components/ui.tsx`: `GlassCard`, `Badge` (variants: blue, green, amber,
  red, purple, teal), `severityVariant()`, `Gauge` (SVG), `KpiProgressCard`,
  `MetricCard`, `DataTable` — reusable components

---

# 23. Application State

There is no `st.session_state` any more — state is split across the browser
(`localStorage`, React component state, React Query's cache) and the backend
(`AppState`, a process-wide singleton in `backend/state.py`, plus SQLite for anything
that must survive a restart).

**Browser-side (`frontend/src/`)**

| Location | Holds | Purpose |
|---|---|---|
| `localStorage["securing_ai_token"]` | str | Bearer auth token (Section 4.2) |
| `localStorage["securing_ai_theme"]` | "dark" \| "light" | Theme choice (Section 22) |
| `AuthContext` (React context) | `{ username, role }` | Derived from the token, held in memory |
| React Query cache | per-endpoint response data | `["dashboard"]`, `["phase-stages", uc]`, `["phase-state", uc]`, `["datasets"]`, etc. — refetched per each hook's own staleness policy, not a single global store |
| `PhaseWorkspace.tsx` component state | data source / category filter per stage, run results, workflow status | Local to the mounted page — a full page reload re-fetches from the backend instead |

**Backend-side (`backend/state.py: AppState`, in-memory unless noted)**

| Field | Type | Purpose |
|---|---|---|
| `datasets` | dict[str, DataFrame] | 16 synthetic DataFrames, regenerated with a fresh random seed on every process start (Section 9.4) |
| `kpi_engine` | KPIEngine | Recomputed per dashboard request, not cached across requests |
| `llm_router` | LLMRouter \| None | Rebuilt whenever `SettingsStore` credentials change (Section 28.8) |
| `active_stage` | dict[phase, int] | Active stage index per phase |
| `completed_stages` | dict[phase, list[int]] | Completed stage indices per phase |
| `stage_outputs` | dict[phase, dict] | AgentOutcome per completed stage_key |
| `hitl_approved` | dict[phase, dict] | HITL gate decision per stage_key |
| `workflow_state` | dict[f"{uc}_{stage}", dict] | Remediation ticket dispatch state (Section 15.1) |
| `memory` | ShortTermMemory | 48h SQLite-backed (`data/memory.db`) |
| `mcp_client` / `mcp_registry` | MCPClient / MCPToolRegistry | Tool connection dispatch |
| `token_tracker` | TokenUsageTracker | SQLite-backed (`data/token_usage.db`) |
| `rag` | RAGService | Copilot FAISS+BM25 index (Section 28.7) |

**Persisted independently of `AppState`** (survive a restart): `data/audit_log.db`
(HITL decisions, guardrail events), `data/score_history.db` (dashboard trend, Section
18), `data/hallucination_reports.db` (Section 28.9), `data/app_settings.db`
(`SettingsStore`, Section 28.8), `data/rag_cache/` (Copilot embeddings, Section 28.7).
Everything in `AppState` itself, and the observability trace log
(`app/observability/trace_store.py`), resets on every backend restart.

---

# 24. MCP Tool Registry

**File**: `app/mcp/registry.py` — `MCPToolRegistry`

| Tool ID | Display Name | Category | Required Env Vars |
|---|---|---|---|
| `ai_spm_scanner` | AI-SPM Scanner | AI Security | `AI_SPM_API_KEY` |
| `protect_ai_guardian` | Protect AI Guardian | AI Security | `PROTECT_AI_API_KEY` |
| `hiddenlayer` | HiddenLayer AISec | AI Security | `HIDDENLAYER_API_KEY` |
| `lakera_guard` | Lakera Guard | AI Security | `LAKERA_API_KEY` |
| `guardrails_ai` | Guardrails AI | AI Security | `GUARDRAILS_AI_API_KEY` |
| `garak` | Garak (NVIDIA) | AI Security | `GARAK_RUNNER_URL` |
| `pyrit` | PyRIT (Microsoft) | AI Security | `PYRIT_RUNNER_URL` |
| `soar_platform` | SOAR Platform | AI Security | `SOAR_API_KEY`, `SOAR_URL` |
| `jira` | Jira | Remediation | `JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN` |
| `servicenow` | ServiceNow | Remediation | `SERVICENOW_INSTANCE`, `SERVICENOW_USERNAME`, `SERVICENOW_PASSWORD` |

The old Streamlit build showed a per-phase MCP tool status strip in Column 1 (Identify:
ai_spm_scanner/protect_ai_guardian/hiddenlayer, Protect: lakera_guard/guardrails_ai/
ai_spm_scanner, etc., from `lifecycle_stage.py`'s now-deleted `use_case_tools` map).
**Not currently shown in React's Column 1** — the full tool registry is still browsable
on the Settings page (Section 16); it's just not surfaced per-stage in the workspace.

`MCPClient` (`app/mcp/client.py`) uses the same mock/live dispatch pattern as before:
if all required env vars for a tool are set, `is_live_capable()` returns True and the
UI shows 🟢 Live; otherwise it falls back to 🔵 Mock Fallback with realistic simulated
responses.

---

# 25. Requirements & Environment

## 25.1 requirements.txt (Actual — matches the repository exactly)

```
# Core
python-dotenv>=1.0
pydantic>=2.7
PyYAML>=6.0

# React frontend API backend
fastapi>=0.111
uvicorn[standard]>=0.30
python-multipart>=0.0.9

# LLM & Agents
langchain>=0.2
langchain-openai>=0.1
langchain-community>=0.2
langgraph>=0.2
openai>=1.35
tiktoken>=0.7

# Vector DB
faiss-cpu>=1.8

# Observability
langsmith>=0.1
prometheus-client>=0.20
structlog>=24.1

# Data
pandas>=2.2
numpy>=1.26

# File parsing
PyMuPDF>=1.24
chardet>=5.2
python-docx>=1.1

# MCP
mcp>=1.0

# Async
aiohttp>=3.9

# Utilities
httpx>=0.27
tenacity>=8.3
cachetools>=5.3

# Testing
pytest>=8.0
pytest-asyncio>=0.23
```

`prometheus-client` is listed but `app/observability/metrics.py` (its only consumer) is
not imported anywhere in the live app — safe to omit locally, kept here for parity with
the committed `requirements.txt`. `streamlit`, `plotly`, and `altair` were removed when
the legacy Streamlit UI was retired — Recharts (a JS dependency in `frontend/package.json`,
not this file) now covers all charting.

## 25.2 Environment Variables (.env) — Complete Reference

### Minimum Required to Run (Synthetic Data Only, No Live LLM)
```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme_before_demo
SESSION_SECRET=<random 64-char hex — python -c "import secrets; print(secrets.token_hex(32))">
```
The app runs fully on synthetic-fallback content with zero LLM calls if `OPENAI_API_KEY`
is unset or invalid — see Section 11.3. `SESSION_SECRET` is not strictly required to run
(`backend/security.py` generates a random one if unset), but without a fixed value every
backend restart invalidates every logged-in session — see Section 28.4.

### Full .env Reference

```bash
# ── LLM ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY=sk-your-key-here
MODEL_NAME=gpt-4o-mini

# ── Auth ───────────────────────────────────────────────────────────────────
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme_before_demo
SESSION_SECRET=

# ── LangSmith (LLM Tracing & Observability) ───────────────────────────────
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_your-key-here
LANGCHAIN_PROJECT=securing-ai-demo
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com

# ── Optional MCP AI Security Vendor API keys (enables live data modes) ────
# AI_SPM_API_KEY=
# PROTECT_AI_API_KEY=
# HIDDENLAYER_API_KEY=
# LAKERA_API_KEY=
# GUARDRAILS_AI_API_KEY=
# GARAK_RUNNER_URL=
# PYRIT_RUNNER_URL=
# SOAR_API_KEY=
# SOAR_URL=
# JIRA_URL=
# JIRA_USERNAME=
# JIRA_API_TOKEN=
# SERVICENOW_INSTANCE=
# SERVICENOW_USERNAME=
# SERVICENOW_PASSWORD=
```

`.env` **is** excluded by `.gitignore` (line 13) — never committed. On a host (HF
Spaces or otherwise), set these as platform secrets/variables instead of shipping a
`.env` file — see Section 25.4.

## 25.3 Quickstart

Dependencies are uv-managed (`pyproject.toml` / `uv.lock`); `requirements.txt` is kept
only as a pip-compatible fallback and is not what `uv` or the Dockerfile use.

```bash
# Step 1: Install Python deps (one-time — creates .venv from uv.lock)
uv sync

# Step 2: Configure environment
cp .env.example .env
# Edit .env — minimum required: ADMIN_USERNAME, ADMIN_PASSWORD, SESSION_SECRET

# Step 3a: Build the frontend once, then serve everything from one process
npm --prefix frontend install
npm --prefix frontend run build
uv run uvicorn backend.main:app --port 8420

# Step 3b (alternative): two-terminal dev mode with hot reload
uv run uvicorn backend.main:app --reload --port 8420
npm --prefix frontend run dev   # separate terminal, http://localhost:5173
```

Opens at `http://localhost:8420` (single-process mode) or `http://localhost:5173`
(dev mode). Log in with the `ADMIN_USERNAME`/`ADMIN_PASSWORD` pair from `.env`. See
Section 28 for the full backend/frontend architecture.

## 25.4 Docker / HuggingFace Spaces

The [`Dockerfile`](Dockerfile) is a two-stage build (Node → Python) that serves the
**React frontend + FastAPI backend** (Section 28) — the only UI this project has. It
installs dependencies via `uv sync --frozen` from the same `uv.lock` used locally, so
the containerised environment is identical to a local `uv sync`. Summary of what it does:

1. Stage 1 (`node:20-slim`): `npm install && npm run build` → `frontend/dist`
2. Stage 2 (`python:3.11-slim`): copies the `uv` binary from `ghcr.io/astral-sh/uv`,
   creates the UID-1000 non-root user HF Spaces requires, copies the repo + the built
   `frontend/dist`, runs `uv sync --frozen --no-dev` (skips the `dev` dependency group
   — pytest etc.), and starts `uv run uvicorn backend.main:app --host=0.0.0.0 --port=7860`
3. `HEALTHCHECK` hits the unauthenticated `GET /healthz` endpoint

On HF Spaces (or any host), set secrets — `OPENAI_API_KEY`, `SESSION_SECRET`,
`ADMIN_USERNAME`/`ADMIN_PASSWORD`, etc. — as **platform secrets/variables**, never
committed to a `.env` file. `SESSION_SECRET` specifically matters on a host: without a
fixed value, every container restart (redeploy, or free-tier scale-to-zero after
inactivity) invalidates every logged-in session (see `backend/security.py`).

---

# 26. token_pricing.yaml

Cost rates loaded by `TokenUsageTracker` — editable without code change (as committed):

```yaml
models:
  gpt-4o-mini:
    input_cost_per_1m: 0.15
    output_cost_per_1m: 0.60
    display_name: "GPT-4o-mini"
    provider: "openai"

  gpt-4o:
    input_cost_per_1m: 2.50
    output_cost_per_1m: 10.00
    display_name: "GPT-4o"
    provider: "openai"

  text-embedding-3-small:
    input_cost_per_1m: 0.02
    output_cost_per_1m: 0.0
    display_name: "text-embedding-3-small"
    provider: "openai"

  text-embedding-3-large:
    input_cost_per_1m: 0.13
    output_cost_per_1m: 0.0
    display_name: "text-embedding-3-large"
    provider: "openai"

  ollama-llama3.1-8b:
    input_cost_per_1m: 0.0
    output_cost_per_1m: 0.0
    display_name: "Ollama llama3.1:8b"
    provider: "ollama"
    compute_cost_per_hour: 0.50

  ollama-deepseek-r1-7b:
    input_cost_per_1m: 0.0
    output_cost_per_1m: 0.0
    display_name: "Ollama deepseek-r1:7b"
    provider: "ollama"
    compute_cost_per_hour: 0.50
```

---

# 27. Demo Delivery Guide

## 27.1 Recommended Demo Flow (CXO Audience — 20 minutes)

1. **Login** → Show authentication gate + profile badge (30 sec)
2. **Executive Dashboard** → AI Security Posture Index, 5 phase gauges, KPI cards (3 min)
3. **Identify → Agent Risk Scoring** → Execute, show key demo moment: a low-permission
   agent handling Regulated-PII outranks an Admin-scope agent on risk score (4 min)
4. **Protect → Guardrail Proxy** → Execute, show live block-rate on injection/PII events (3 min)
5. **Detect → Automated Red-Teaming** → Execute, show the multi-turn jailbreak bypass
   finding and its remediation recommendation (4 min)
6. **Respond → Automated Containment** → Approve the HITL gate on a Critical incident,
   watch the containment action log populate (3 min)
7. **Recover → Guardrail Update Loop** → Show the closed loop: the Detect-phase gap now
   has a deployed policy update with a measured effectiveness delta (2 min)
8. **Observability Page** → Hallucination detection, token cost (1 min)

## 27.2 Recommended Demo Flow (Technical Audience — 45 minutes)

Same as above, plus:
- Identify → Shadow AI Discovery → show the sanctioned-vs-shadow classification breakdown
- Protect → Secrets Isolation → show the exposed-API-key-in-chat-log finding and its HITL gate
- Data Explorer → browse the raw synthetic datasets
- Agents Repository → walk through all 14 agents and their MITRE ATLAS mappings
- Settings → show the MCP/API tool connection framework (AI-SPM, Lakera, Garak, PyRIT, SOAR)
- Token Usage → show cost breakdown per phase, Tier 1 vs. Tier 3 routing rationale

## 27.3 Key Demo Moments (Must Not Miss)

| Phase | Stage | Demo Moment |
|---|---|---|
| Identify | Agent Risk Scoring | Low-permission, high-data-sensitivity agent outranks a high-permission, sanctioned agent — risk isn't just about access level |
| Protect | Secrets Isolation | Live API key found sitting in chat history, reachable by any future LLM prompt referencing "past conversations" |
| Detect | Automated Red-Teaming | Multi-turn jailbreak campaigns bypass guardrails at a meaningfully higher rate than single-turn probes — the exact gap the Recover loop closes |
| Respond | Automated Containment | A Critical incident is contained in minutes with zero analyst intervention, fully audited |
| Recover | Guardrail Update Loop | The loop actually closes — a Detect-phase finding becomes a deployed Protect-phase policy update with a measured before/after delta |
| All | AI Analysis tab | Every result renders real dataset-derived numbers even when the configured LLM key is invalid — the demo never goes blank |

## 27.4 Roadmap — React Port Status

The FastAPI + React port described in Section 28 is now built and is the **only** UI —
the Streamlit app described in Sections 1–27 above was retired and deleted (see the
notice at the top of this file). `app/`'s business logic that both UIs used to share is
now used by React/FastAPI alone. Known gaps: file-upload data-source mode is UI-visible
but not wired to `FileUploadProcessor` (falls through to synthetic); the remediation
ticket workflow (Section 15.1) is client-side-only in React, not persisted server-side;
bundle size is unoptimised (no route-based code-splitting yet). None of these block the
core demo flow — every stage's Execute → AI Analysis → Output → HITL path works end to
end against the real backend.

---

# 28. React Frontend & FastAPI Backend (Production UI)

## 28.1 Why

Streamlit's own free-tier restrictions on HuggingFace Spaces made a React frontend the
target for production/public hosting. Rather than reimplementing the LangGraph agent
pipeline, synthetic data engine, KPI formulas, and guardrails in JavaScript, the backend
wraps the exact same `app/` Python modules the original Streamlit build used, behind a
REST API. The Streamlit app itself was later retired once the React port was complete
(see the notice at the top of this file) — `app/`'s business logic now serves React alone.

## 28.2 Architecture

```
backend/                       FastAPI app — orchestration + JSON shaping only
  main.py                      All routes: auth, dashboard, phases, datasets,
                                agents, mcp, settings, token-usage, observability, copilot
  state.py                     AppState — process-wide singleton: datasets, KPIEngine,
                                AgentManager, MCPClient, ShortTermMemory, TokenUsageTracker
  security.py                  Minimal HMAC-signed session token (no new JWT dependency)
  data_content.py              Pure-data config the old Streamlit pages had inline:
                                USE_CASE_OVERVIEW, STAGE_UI_CONFIG (filter/chart/HITL
                                spec per stage), AGENTS_DB, PHASE_DATASETS
  utils.py                     df_to_records / chart_data / hitl_candidates helpers

frontend/                      Vite + React 19 + TypeScript, no CSS framework —
  src/theme.css                 originally hand-ported from the (now-deleted) Streamlit
                                 build's theme.py, since extended with a light theme
  src/lib/{api,types}.ts        typed fetch client + response shapes
  src/context/AuthContext.tsx   token in localStorage, Bearer header on every request
  src/pages/PhaseWorkspace.tsx  ONE generic component renders all 5 phases / 14 stages,
                                 driven entirely by STAGE_UI_CONFIG from the backend —
                                 not 5 hand-ported page files
  src/pages/{Dashboard,Agents,Copilot,Settings,TokenUsage,Observability,DataExplorer}Page.tsx
```

Both processes run from the same repo, importing the same `app/` package — the backend
is not a separate deployable artifact.

## 28.3 Streamlit-coupling removed from `app/` (history — now fully deleted)

While both UIs coexisted, three modules had a hard `import streamlit as st` /
`st.session_state` dependency that would crash outside a Streamlit script context, and
were first made runtime-agnostic (best-effort-detect a live Streamlit context, fall
back to plain module state otherwise) so the FastAPI backend could call them safely:
`app/runtime/agent_manager.py`, `app/observability/health_metrics.py`,
`app/mcp/client.py`. Once Streamlit was deleted entirely, that best-effort detection
code was itself removed as dead weight — these three files now hold no Streamlit
reference at all, just the plain module-level state they fell back to. Their public
APIs are unchanged (`AgentManager.run_stage()` takes explicit `username`/`session_id`/
`memory` params; `InAppMetrics` and `MCPClient` use process-wide state/`AuditLogger`).

## 28.4 Auth

Single-admin demo scope: `POST /api/auth/login` checks `ADMIN_USERNAME`/`ADMIN_PASSWORD`
(bootstrapped from `.env`, changeable at runtime via `POST /api/settings/credentials` —
see Section 28.8) and returns a self-rolled HMAC-signed opaque token (12h TTL, no new
pyjwt/itsdangerous dependency). `SESSION_SECRET` env var pins the signing key across
restarts — set it (Section 25.2); left unset, a fresh key is generated per process
start and every restart invalidates every session, which is confusing during active
local development (repeated restarts silently 401 any open browser tab).

## 28.5 Key design decision — `STAGE_UI_CONFIG`

The 5 old Streamlit page files (`identify.py` … `recover.py`) each hand-wrote a
3-column input panel, category filter, and result chart per stage — ~1,500 lines of
near-duplicate code. `backend/data_content.py`'s `STAGE_UI_CONFIG` dict consolidates
that per-stage config (filter column/options, chart dataset/column/type, HITL
candidate spec) into pure data, served via `GET /api/phases/{uc}/stages`. React's
`PhaseWorkspace.tsx` is the only component that renders a phase — one implementation
for all 14 stages instead of 5 parallel ones.

## 28.6 Running locally

Same `uv`-managed environment as the rest of the project (Section 3.1) —
`fastapi`/`uvicorn` are already in `pyproject.toml`'s `dependencies`, no separate
install step for the backend. The frontend needs its own `npm install` in `frontend/`.

```bash
# Terminal 1 — backend (serves the API on :8420)
uv run uvicorn backend.main:app --reload --port 8420

# Terminal 2 — frontend dev server (proxies /api to :8420, hot reload on :5173)
npm --prefix frontend run dev
```

Open `http://localhost:5173`. For a single-process run — **the same command the
Dockerfile uses** (Section 25.4), just on a different port/host — rebuild the frontend
first, then:

```bash
npm --prefix frontend run build      # writes frontend/dist
uv run uvicorn backend.main:app --port 8420
```

Open `http://localhost:8420` — this one process now serves both the API and the built
React app. This is exactly what runs in Docker/HF, just bound to `0.0.0.0:7860` there
instead of `127.0.0.1:8420`.

## 28.7 Copilot — Hybrid RAG

The React Copilot page is a real hybrid-search RAG assistant (Section 19 describes the
keyword-branch lookup the retired Streamlit copilot used — historical only now). It
turned out `app/rag/`
(`indexes.py`, `ingestor.py`, `retriever.py`) already contained a fully-built FAISS +
BM25 + Reciprocal-Rank-Fusion engine from the pre-Securing-AI build — it just wasn't
wired into anything. Rewired for this use case rather than rebuilt:

- **Collections** (`app/rag/indexes.py`, `app/rag/collections.py`): one FAISS
  `IndexFlatIP` collection per dataset (16, renamed from the old CTEM-era names) plus
  a 17th `"uploads"` collection for analyst-uploaded documents.
- **Startup indexing** (`backend/rag_service.py: RAGService`): on backend startup,
  each dataset is sampled (capped at 300 rows — full ingestion of all ~5,000 rows
  isn't worth re-embedding on every restart for a demo) and embedded via
  `text-embedding-3-small` in a **background thread**, so `/healthz` and every other
  route respond immediately rather than waiting ~2–3 minutes for indexing to finish.
  `GET /api/copilot/memory` reports live per-dataset progress for the UI's pipeline
  status badges.
- **Disk cache** (`data/rag_cache/`, one `.faiss` + `.pkl` file pair per dataset
  collection plus a `manifest.json`): the synthetic datasets are seeded (seed=42), so
  their embeddings are identical run to run — recomputing them from scratch on every
  process restart is pure waste. Before embedding, `RAGService` fingerprints exactly
  what it's about to embed (a SHA-256 of each sampled dataframe's shape + content hash,
  plus the cache format version and row cap) and checks it against
  `data/rag_cache/manifest.json`. On a match, it loads the cached FAISS indexes +
  metadata directly (near-instant, zero embedding calls); on a miss — first run, a
  changed dataset, a bumped `_CACHE_VERSION`, or a corrupt/partial cache — it re-embeds
  and writes a fresh cache afterward (only if every dataset indexed cleanly; a partial
  failure never gets cached as if complete). Uploaded documents are intentionally
  **not** cached — the "uploads" collection is meant to reset with each new session/
  container start. Whether this cache survives a Hugging Face Space's free-tier
  sleep→wake cycle depends on whether HF preserves that container's disk across sleep
  (unconfirmed) — a full redeploy always wipes it regardless, so a `uv run uvicorn ...`
  restart during active local development gets the speedup reliably, HF's benefit is
  restart-mechanism-dependent.
- **Uploads** (`POST /api/copilot/upload`, multipart): routes through the existing
  `FileUploadProcessor` (Section 4 file structure) to extract text from
  txt/json/log/csv/py/js/yaml/pdf/docx, fixed-size chunks it (1000 chars, 150 overlap),
  embeds, and adds to the `"uploads"` collection. `DELETE /api/copilot/uploads` clears
  it (rebuilds an empty index — no per-file deletion, out of scope for the demo).
- **Query** (`POST /api/copilot/message`): embeds the question once, hybrid-searches
  (semantic + BM25, RRF-merged) across all 17 collections, feeds the top-k chunks to
  GPT-4o-mini as grounding context, and returns both the answer and the raw retrieved
  chunks (with collection/source and relevance score) for the UI to show as citations.

**Concurrency fix worth knowing about**: the first working version locked
`RAGService`'s shared FAISS-access lock around each *entire* dataset-ingest call,
including the OpenAI embedding network round-trip. Since startup indexing runs for
several minutes in the background, any Copilot query issued during that window queued
behind whatever embedding call happened to be in flight — observed hangs up to 30s+.
Fixed by narrowing the lock to only the fast, local `manager.add()`/`hybrid_search()`
calls; the network-bound embedding calls (which also now carry an explicit 20s
timeout + capped retries, so a stalled request fails fast instead of hanging
indefinitely) happen outside the lock. A query issued mid-indexing now returns in
single-digit seconds instead of blocking on unrelated ingestion work.

**Encoding fix**: `FileUploadProcessor.detect_encoding()` (Section 4) now tries strict
UTF-8 decoding first before falling back to `chardet`'s statistical guess — chardet
was misdetecting short, mostly-ASCII uploaded files containing a handful of UTF-8
multi-byte characters (em dashes, smart quotes) as Windows-1252, producing mojibake
in retrieved chunks.

## 28.8 Settings persistence — `SettingsStore` (no `.env` access required)

The old Streamlit Settings page used to write directly to a local `.env` file, which
only works when the user can reach the filesystem the process runs on — true on a
laptop, false the moment the app is actually deployed (HF Spaces, Docker, anywhere
without a shell). The React Settings page (Section 16) instead persists everything
through `app/config/settings_store.py: SettingsStore`, a small SQLite table
(`data/app_settings.db`, gitignored — it holds the OpenAI key, MCP credentials, and the
admin password in plaintext) that the UI itself fully owns.

**How it takes effect without code changes elsewhere**: `SettingsStore.set()` mirrors
every write straight into `os.environ`, and `apply_to_environment()` loads every
already-stored key into `os.environ` once at process start — so any existing
`os.getenv(...)` call anywhere in the codebase (ours, or a third-party SDK's, e.g.
LangSmith's tracing config) transparently sees a UI-configured value without needing to
know the store exists. A `.env` value / platform secret is only the bootstrap default;
once something is saved through the UI, the DB-stored value wins from then on, forever
(across restarts too) — until deleted.

**Two ordering bugs to be aware of if you touch this** (both already fixed, keep them
that way):

1. `backend/main.py` must construct `SettingsStore` and call
   `apply_to_environment()` **before** `from backend.state import state` — that import
   triggers `AppState()` → `RAGService()` → `RAGIngestor()`/`RAGRetriever()`
   construction, and those read `OPENAI_API_KEY` from the environment. Import it after
   and a stored key would still be applied one beat too late for RAG's first read.
2. Several modules (`app/rag/ingestor.py`, `app/rag/retriever.py`, `app/llm/router.py`,
   `app/guardrails/validator.py`) call `load_dotenv()` at import time, and all of them
   load **after** `backend/main.py` has already applied stored settings. They must use
   `load_dotenv(override=False)` — `override=True` would re-read `.env` and silently
   stomp a value the user just set via the UI back to whatever is still sitting in
   `.env`. Only `backend/main.py`'s own first `load_dotenv(override=True)` call (before
   `SettingsStore` runs) is safe to keep as `override=True`, since nothing has layered
   DB values on top of `os.environ` yet at that point.

Also watch for the general "frozen at import/construction time" trap this store is
designed to route around: `RAGIngestor`/`RAGRetriever` used to cache
`os.getenv("OPENAI_API_KEY")` once in `__init__` (same bug class as an earlier
`MODEL_TIERS` issue in `app/llm/router.py`) — fixed to read the key fresh via a
`@property` on every embedding call, and `RAGRetriever`'s cached `OpenAI` client is
rebuilt whenever the key changes rather than reused forever.

**Login credentials**: `POST /api/settings/credentials` lets a logged-in admin change
`ADMIN_USERNAME`/`ADMIN_PASSWORD` from inside the app — no `.env` access needed. It
requires `current_password` (so a stolen/left-open session token can't silently take
over login) and returns **400**, not 401, on a wrong current password — the frontend's
`api.ts` request wrapper treats any 401 as "session expired" and force-redirects to
`/login`, which would be wrong here (the session itself is still valid; only the
supplied current-password guess was wrong).

## 28.9 Hallucination report persistence

`app/observability/trace_store.py` used to hold hallucination reports (Section 28.7's
CVE/MITRE-technique/asset-reference cross-checks against real data, run on every stage
`Execute`) in a plain module-level dict — meaning the Observability page's
"Hallucination Detection" tab reset to empty on every backend restart, including HF
Spaces' free-tier sleep→wake cycle. That silently erased the only evidence the demo has
that the check works. Reports are now persisted to SQLite
(`data/hallucination_reports.db`, gitignored via the existing `data/*.db` pattern),
keyed by `{use_case}_{stage}`, upserted on every stage run — `record_hallucination_report`
still accepts the same `HallucinationReport` pydantic model `agent_manager.py` already
produces, and `get_hallucination_reports()` now returns plain dicts (not pydantic
objects), so `backend/main.py`'s `/api/observability` handler no longer needs its own
`.model_dump()` step. The in-memory `_TRACES` list (LangSmith-style execution traces,
Section 28's other tab) is unchanged — deliberately still ephemeral, since those are
high-volume and less valuable to keep across restarts than the hallucination evidence.
