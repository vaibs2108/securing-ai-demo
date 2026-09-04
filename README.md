---
title: Securing AI
emoji: 🛡️
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Securing AI — Agentic AI Security Showcase

A demo of AI/agent security applied across the full NIST Cybersecurity Framework (CSF)
2.0 lifecycle — **Identify → Protect → Detect → Respond → Recover** — with 16 synthetic
datasets, 14 specialised AI agents (LangGraph + GPT-4o-mini/GPT-4o), and a React
frontend backed by a FastAPI API.

See [`AGENTS.md`](AGENTS.md) for the full architecture spec, and Section 28 for the
React/FastAPI port specifically.

## Required Space secrets

Set these under **Settings → Repository secrets** before the Space will show live AI
analysis rather than visible LLM-failure errors:

| Secret | Required | Notes |
|---|---|---|
| `ADMIN_USERNAME` | Yes | Login username |
| `ADMIN_PASSWORD` | Yes | Login password — set a real one, not a demo default |
| `OPENAI_API_KEY` | Yes | A valid key with available quota. An invalid/exhausted key does **not** silently fall back to demo content — every stage will show "Agent execution failed" |
| `SESSION_SECRET` | Recommended | Any random string. Without it, a Space restart (including free-tier sleep/wake) invalidates all logged-in sessions |
| `LANGCHAIN_API_KEY`, `LANGCHAIN_TRACING_V2` | Optional | LangSmith tracing |

## Local development

Dependencies are managed with [uv](https://docs.astral.sh/uv/); `pyproject.toml` /
`uv.lock` are authoritative (`requirements.txt` is kept only as a pip-compatible
fallback and is not used by `uv` or the Dockerfile).

```bash
uv sync                        # one-time setup — creates .venv from uv.lock
npm --prefix frontend install  # one-time setup — frontend deps

uv run uvicorn backend.main:app --reload --port 8420   # terminal 1
npm --prefix frontend run dev                            # terminal 2, http://localhost:5173
```

### Single-process mode (dev or prod — same command Docker/HF uses)

```bash
npm --prefix frontend run build          # rebuild frontend/dist after any frontend change
uv run uvicorn backend.main:app --port 8420
```

Open `http://localhost:8420` — this one process serves both the API and the built
React app, identically to how the Docker image runs it (just on port 7860 there,
bound to `0.0.0.0` instead of `127.0.0.1`).

### Live companion services

The Dashboard's GitHub/Target Agent/Slack/Lakera/Garak/PyRIT/LLM chips reflect real
connections, not mocks. GitHub/Slack/Lakera/LLM come from this repo's own `.env`; the
other three are separate local processes this `.env`'s `TARGET_AGENT_URL` /
`GARAK_RUNNER_URL` / `PYRIT_RUNNER_URL` point at (`http://127.0.0.1:8091` / `:8095` /
`:8096` by default).

The target agent especially isn't just a Dashboard chip — `LiveDataEngine.generate_all()`
calls it on backend startup to fetch real Detect data, and several live panels
(Guardrail Proxy's real proxy test, Recover's replay/capture-evidence buttons) call it
directly too. **Start it before the backend** to avoid a benign-but-noisy
`httpx.ConnectError` / `LiveConnectorError` traceback in the backend's startup log (the
backend still starts fine either way — Detect just falls back to an empty dataset until
the target agent is reachable and you restart the backend).

Start whichever of the three you want live, each in its own terminal:

```bash
# Target agent (sibling repo D:\GenAi\Projects\meridian-support-agent) — start this first
cd ../meridian-support-agent
.venv/Scripts/uvicorn main:app --port 8091

# Garak runner (services/garak-runner)
cd services/garak-runner
.venv/Scripts/uvicorn main:app --port 8095

# PyRIT runner (services/pyrit-runner)
cd services/pyrit-runner
.venv/Scripts/uvicorn main:app --port 8096
```

Any of the three left unstarted just shows "not live" on its Dashboard chip — the rest
of the app still works normally.
