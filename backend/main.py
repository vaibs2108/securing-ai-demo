"""
Securing AI — FastAPI backend.
Wraps the existing app/ business logic (synthetic data engine, LangGraph agent
pipeline, KPI engine, guardrails, hallucination detector, MCP registry) behind
a REST API consumed by the React frontend. No business logic is duplicated
here — this module is orchestration + JSON shaping only.
"""

from __future__ import annotations

import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv(override=True)

# Must run before `from backend.state import state` below: that import
# constructs AppState() -> RAGService() -> RAGIngestor()/RAGRetriever(),
# which read OPENAI_API_KEY from os.environ. Applying stored settings first
# ensures a key saved via the Settings UI on a prior run is already in
# os.environ by the time anything reads it. See app/config/settings_store.py.
from app.config.settings_store import SettingsStore

settings_store = SettingsStore()
settings_store.apply_to_environment()

from backend.state import state
from backend.security import issue_token, get_current_user
from backend.utils import df_to_records, chart_data, hitl_candidates
from backend.data_content import (
    USE_CASE_OVERVIEW, USE_CASE_COLOURS, USE_CASE_LABELS,
    STAGE_UI_CONFIG, PHASE_DATASETS, AGENTS_DB, COPILOT_STARTER_QUESTIONS,
)

from app.ui.components.lifecycle_stage import (
    STAGE_DEFINITIONS, STAGE_INPUT_OUTPUT_MAP,
    get_dataset_name_for_stage, get_agent_details_for_stage,
    _get_previous_stage_output,
)
from app.guardrails.validator import GuardrailManager
from app.observability import trace_store
from app.observability.health_metrics import InAppMetrics
from app.observability.audit_logger import AuditLogger
from app.observability.score_history import ScoreHistoryStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]

score_history = ScoreHistoryStore()

app = FastAPI(title="Securing AI API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    state.init()


@app.get("/healthz")
def healthz() -> Dict[str, Any]:
    """Unauthenticated liveness/readiness probe — no login required."""
    return {
        "status": "ok",
        "datasets_loaded": len(state.datasets),
        "llm_configured": state.llm_router is not None and bool(os.getenv("OPENAI_API_KEY")),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Auth
# ═══════════════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
def login(body: LoginRequest) -> Dict[str, Any]:
    admin_user = os.getenv("ADMIN_USERNAME", "admin")
    admin_pass = os.getenv("ADMIN_PASSWORD", "")
    if body.username != admin_user or not admin_pass or body.password != admin_pass:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = issue_token(body.username, "admin")
    return {"token": token, "username": body.username, "role": "admin"}


@app.get("/api/auth/me")
def me(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    return {"username": user["u"], "role": user["r"]}


# ═══════════════════════════════════════════════════════════════════════════
# Dashboard
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/dashboard")
def dashboard(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    kpi = state.kpi_engine
    kpis = kpi.compute_all()
    posture_index = kpi.get_ai_readiness_index()

    gauges = [
        {"phase": uc, "label": USE_CASE_LABELS[uc], "score": kpi.get_use_case_score(uc), "color": USE_CASE_COLOURS[uc]}
        for uc in ["identify", "protect", "detect", "respond", "recover"]
    ]

    operational = [
        {"label": "AI Security Posture Index", "value": posture_index, "color": "#00d4ff"},
        {"label": "Shadow AI Containment Rate", "value": round(100 - kpis["Shadow AI Discovery Rate"], 1), "color": "#00d4ff"},
        {"label": "Guardrail Enforcement Efficacy", "value": kpis["Guardrail Block Rate"], "color": "#00ff88"},
        {"label": "Red-Team Bypass Resistance", "value": round(100 - kpis["Red-Team Attack Success Rate"], 1), "color": "#ff4444"},
        {"label": "Automated Containment Rate", "value": kpis["Automated Containment Rate"], "color": "#a855f7"},
        {"label": "Rollback & Recovery Reliability", "value": kpis["Rollback Success Rate"], "color": "#14b8a6"},
    ]

    # Real recorded history, not a fabricated random walk — see
    # app/observability/score_history.py for why this replaced _synth_trend().
    phase_scores = {uc: kpi.get_use_case_score(uc) for uc in ["identify", "protect", "detect", "respond", "recover"]}
    score_history.record_snapshot(phase_scores)
    trend = {uc: score_history.get_history(uc, days=30) for uc in phase_scores}

    risk_df = state.datasets.get("agent_risk_register")
    blast_radius = risk_df["blast_radius"].value_counts().to_dict() if risk_df is not None else {}

    audit = AuditLogger().get_logs(limit=8)

    return {
        "kpis": kpis,
        "posture_index": posture_index,
        "gauges": gauges,
        "operational": operational,
        "trend": trend,
        "blast_radius": blast_radius,
        "recent_operations": audit,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Phases / stages
# ═══════════════════════════════════════════════════════════════════════════

PHASE_KEYS = ["identify", "protect", "detect", "respond", "recover"]


@app.get("/api/phases")
def list_phases(user: dict = Depends(get_current_user)) -> List[Dict[str, Any]]:
    return [
        {
            "key": uc,
            "label": USE_CASE_LABELS[uc],
            "color": USE_CASE_COLOURS[uc],
            "overview": USE_CASE_OVERVIEW[uc],
            "stage_count": len(STAGE_DEFINITIONS.get(uc, [])),
        }
        for uc in PHASE_KEYS
    ]


@app.get("/api/phases/{uc}/stages")
def phase_stages(uc: str, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    if uc not in PHASE_KEYS:
        raise HTTPException(status_code=404, detail="Unknown phase")

    stages = STAGE_DEFINITIONS.get(uc, [])
    out = []
    for idx, stage in enumerate(stages):
        key = stage["key"]
        io = STAGE_INPUT_OUTPUT_MAP.get(uc, {}).get(key, {})
        agent_info = get_agent_details_for_stage(uc, key)
        ui_config = STAGE_UI_CONFIG.get(uc, {}).get(key, {})
        input_df = state.datasets.get(io.get("input_key", ""))
        out.append({
            "index": idx,
            "key": key,
            "name": stage["name"],
            "icon": stage["icon"],
            "description": stage["description"],
            "agent": stage["agent"],
            "io": io,
            "agent_info": agent_info,
            "ui_config": ui_config,
            "previous_stage_output": _get_previous_stage_output(uc, key),
            "input_row_count": 0 if input_df is None else len(input_df),
            "input_columns": [] if input_df is None else list(input_df.columns),
            "dataset_summary": get_dataset_name_for_stage(uc, key),
        })

    return {
        "overview": USE_CASE_OVERVIEW.get(uc),
        "color": USE_CASE_COLOURS.get(uc),
        "stages": out,
    }


@app.get("/api/phases/{uc}/state")
def phase_state(uc: str, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    if uc not in PHASE_KEYS:
        raise HTTPException(status_code=404, detail="Unknown phase")
    return {
        "active_stage": state.active_stage[uc],
        "completed_stages": state.completed_stages[uc],
        "stage_outputs": state.stage_outputs[uc],
        "hitl_approved": state.hitl_approved[uc],
    }


class SetActiveStageRequest(BaseModel):
    index: int


@app.post("/api/phases/{uc}/active-stage")
def set_active_stage(uc: str, body: SetActiveStageRequest, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    if uc not in PHASE_KEYS:
        raise HTTPException(status_code=404, detail="Unknown phase")
    state.active_stage[uc] = body.index
    return {"active_stage": state.active_stage[uc]}


class RunStageRequest(BaseModel):
    data_source: str = "synthetic"


def _maybe_augment_with_live_mcp(uc: str, stage_key: str, data_source: str) -> Dict[str, pd.DataFrame]:
    """When data_source == 'mcp' and the relevant real tool is actually live
    (credentials configured — app/mcp/registry.py's 5 real tools only), call
    it for real and return extra dataset entries to merge into what the
    agent analyses. Empty dict when not applicable, in which case the run
    proceeds on the normal 16 synthetic datasets exactly as before — this
    never fabricates a "live" result."""
    if data_source != "mcp":
        return {}

    extra: Dict[str, pd.DataFrame] = {}

    if uc == "protect" and stage_key == "guardrail_proxy":
        status = state.mcp_client.get_connection_status("lakera_guard")
        if status["live"]:
            events = state.datasets.get("guardrail_events")
            samples = (
                events["input_snippet_redacted"].drop_duplicates().head(5).tolist()
                if events is not None else []
            )
            rows = []
            for text in samples:
                result = state.mcp_client.screen_prompt(text)
                rows.append({"prompt_sample": text, "lakera_flagged": result.get("flagged"), "live": result.get("live")})
            if rows:
                extra["lakera_guard_live_results"] = pd.DataFrame(rows)

    elif uc == "detect" and stage_key in ("injection_detection", "red_teaming"):
        for tool_name in ["garak", "pyrit"]:
            status = state.mcp_client.get_connection_status(tool_name)
            if status["live"]:
                result = state.mcp_client.trigger_runner_scan(tool_name, target="demo-agent-fleet")
                findings = result.get("findings") or []
                extra[f"{tool_name}_live_scan"] = pd.DataFrame(findings if findings else [{"note": "scan returned no findings"}])

    return extra


@app.post("/api/phases/{uc}/stages/{stage_key}/run")
def run_stage(uc: str, stage_key: str, body: RunStageRequest, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    if uc not in PHASE_KEYS or stage_key not in STAGE_UI_CONFIG.get(uc, {}):
        raise HTTPException(status_code=404, detail="Unknown phase/stage")

    live_mcp_data = _maybe_augment_with_live_mcp(uc, stage_key, body.data_source)
    datasets_for_run = {**state.datasets, **live_mcp_data} if live_mcp_data else state.datasets

    io = STAGE_INPUT_OUTPUT_MAP.get(uc, {}).get(stage_key, {})
    # Scope the LLM's aggregated context to this stage's real input dataset
    # (plus any live MCP enrichment) instead of all 16 datasets — see
    # AgentManager.run_stage's docstring for why that mattered.
    input_keys = [k for k in [io.get("input_key"), *live_mcp_data.keys()] if k]

    outcome = state.agent_manager.run_stage(
        uc, stage_key, datasets_for_run, body.data_source,
        username=user["u"], session_id="api_session", memory=state.memory,
        input_keys=input_keys or None,
    )

    stages = STAGE_DEFINITIONS.get(uc, [])
    idx = next((i for i, s in enumerate(stages) if s["key"] == stage_key), None)
    if idx is not None and idx not in state.completed_stages[uc]:
        state.completed_stages[uc].append(idx)
    state.stage_outputs[uc][stage_key] = outcome

    gm = GuardrailManager()
    hitl_required = gm.check_hitl_required(
        uc, stage_key, outcome.get("findings", []), outcome.get("ai_confidence")
    )
    ui_config = STAGE_UI_CONFIG.get(uc, {}).get(stage_key, {})
    candidates = hitl_candidates(state.datasets, ui_config.get("hitl")) if hitl_required else []

    output_df = state.datasets.get(io.get("output_key", ""))

    chart = chart_data(state.datasets, ui_config["chart"]) if ui_config.get("chart") else None

    return {
        "outcome": outcome,
        "hitl_required": hitl_required,
        "hitl_candidates": candidates,
        "completed_stages": state.completed_stages[uc],
        "output_preview": {
            "name": io.get("output_name", ""),
            "row_count": 0 if output_df is None else len(output_df),
            "columns": [] if output_df is None else list(output_df.columns),
            "records": df_to_records(output_df, limit=25),
        },
        "chart": chart,
        "live_mcp_used": list(live_mcp_data.keys()),
    }


class HitlDecisionRequest(BaseModel):
    decision: str  # "approve" | "reject"


@app.post("/api/phases/{uc}/hitl/{stage_key}")
def hitl_decision(uc: str, stage_key: str, body: HitlDecisionRequest, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    if uc not in PHASE_KEYS:
        raise HTTPException(status_code=404, detail="Unknown phase")
    approved = body.decision == "approve"
    state.hitl_approved[uc][stage_key] = approved
    outcome = state.stage_outputs[uc].get(stage_key, {})
    InAppMetrics().record_hitl_decision(
        uc, stage_key, "approved" if approved else "dismissed", outcome.get("ai_confidence", 0)
    )
    AuditLogger().log_action(
        action=f"HITL Gate Decision: {stage_key.replace('_', ' ').title()}",
        username=user["u"],
        status="Approved" if approved else "Rejected",
        target=outcome.get("agent_name", stage_key),
        details=f"Analyst {'approved' if approved else 'rejected'} the {uc}/{stage_key} HITL gate.",
    )
    return {"approved": approved}


class DispatchTicketsRequest(BaseModel):
    summary: str
    description: str = ""
    priority: str = "Medium"


@app.post("/api/phases/{uc}/stages/{stage_key}/dispatch-tickets")
def dispatch_tickets(uc: str, stage_key: str, body: DispatchTicketsRequest, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Create real Jira/ServiceNow tickets when configured (app/mcp/client.py),
    a mock reference number otherwise — never silently pretends a mock ref is
    a real one. Called from each phase's final-stage Remediation & Workflow tab."""
    if uc not in PHASE_KEYS:
        raise HTTPException(status_code=404, detail="Unknown phase")

    results: Dict[str, Any] = {}
    for tool_name in ["jira", "servicenow"]:
        try:
            results[tool_name] = state.mcp_client.create_ticket(tool_name, body.summary, body.description, body.priority)
        except Exception as exc:
            results[tool_name] = {"live": False, "success": False, "error": str(exc)}

    any_live = any(r.get("live") for r in results.values())
    AuditLogger().log_action(
        action=f"Remediation Tickets Dispatched: {stage_key.replace('_', ' ').title()}",
        username=user["u"],
        status="Success",
        target=f"{uc}/{stage_key}",
        details=f"jira={results['jira'].get('ticket_ref')} servicenow={results['servicenow'].get('ticket_ref')} (live={any_live})",
    )
    return results


# ═══════════════════════════════════════════════════════════════════════════
# Datasets (Data Explorer)
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/datasets")
def list_datasets(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    result = {}
    for uc, names in PHASE_DATASETS.items():
        result[uc] = []
        for name in names:
            df = state.datasets.get(name)
            result[uc].append({
                "name": name,
                "row_count": 0 if df is None else len(df),
                "column_count": 0 if df is None else len(df.columns),
            })
    return result


@app.get("/api/datasets/{name}")
def get_dataset(name: str, limit: int = 200, q: Optional[str] = None, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    df = state.datasets.get(name)
    if df is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    frame = df
    if q:
        mask = frame.astype(str).apply(lambda col: col.str.contains(q, case=False, na=False)).any(axis=1)
        frame = frame[mask]
    return {
        "name": name,
        "row_count": len(frame),
        "columns": list(df.columns),
        "records": df_to_records(frame, limit=limit),
    }


@app.get("/api/datasets/{name}/download")
def download_dataset(name: str, user: dict = Depends(get_current_user)) -> Response:
    """Full dataset as CSV — unlike /api/datasets/{name}, not capped by `limit`."""
    df = state.datasets.get(name)
    if df is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return Response(
        content=df.to_csv(index=False),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
    )


# ═══════════════════════════════════════════════════════════════════════════
# Agents repository
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/agents")
def list_agents(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    return AGENTS_DB


# ═══════════════════════════════════════════════════════════════════════════
# MCP tools
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/mcp/tools")
def mcp_tools(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    categories: Dict[str, List[Dict[str, Any]]] = {}
    for name, tool in state.mcp_registry.tools.items():
        status = state.mcp_client.get_connection_status(name)
        cat = tool.category
        categories.setdefault(cat, []).append({
            "name": name,
            "display_name": tool.display_name,
            "category": tool.category,
            "description": tool.description,
            "capabilities": tool.capabilities,
            "endpoints": tool.endpoints,
            "required_env_vars": tool.required_env_vars,
            "env_var_values_masked": {v: _mask(os.getenv(v, "")) for v in tool.required_env_vars},
            "integration_type": tool.integration_type,
            "docs_url": tool.docs_url,
            "live": status["live"],
            "status": status["status"],
        })
    return categories


# ═══════════════════════════════════════════════════════════════════════════
# Settings
# ═══════════════════════════════════════════════════════════════════════════

def _apply_settings(updates: Dict[str, str]) -> None:
    """Persist config through SettingsStore (data/app_settings.db) — not a
    .env file the user has no way to reach once deployed. See
    app/config/settings_store.py for why."""
    for key, value in updates.items():
        if value is not None:
            settings_store.set(key, str(value))


class SettingsRequest(BaseModel):
    openai_api_key: Optional[str] = None
    langchain_tracing: Optional[bool] = None
    langchain_api_key: Optional[str] = None
    langchain_project: Optional[str] = None
    mcp_credentials: Optional[Dict[str, str]] = None  # {"ENV_VAR_NAME": "value"}
    model_name: Optional[str] = None          # Tier 1 — Primary
    reasoning_model: Optional[str] = None     # Tier 3 — Reasoning (gpt-4o is clamped to gpt-4o-mini regardless — see app/llm/router.py)
    ollama_model: Optional[str] = None        # Tier 2 — Secondary (local)
    ollama_base_url: Optional[str] = None


def _mask(value: str) -> str:
    if not value:
        return ""
    return value[:4] + "…" + value[-2:] if len(value) > 8 else "•" * len(value)


@app.get("/api/settings")
def get_settings(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    return {
        "openai_api_key_masked": _mask(os.getenv("OPENAI_API_KEY", "")),
        "openai_api_key_set": bool(os.getenv("OPENAI_API_KEY")),
        "langchain_tracing": os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true",
        "langchain_api_key_set": bool(os.getenv("LANGCHAIN_API_KEY")),
        "langchain_project": os.getenv("LANGCHAIN_PROJECT", "securing-ai-demo"),
        "llm_model_info": state.llm_router.get_active_model_info() if state.llm_router else None,
        "model_name": os.getenv("MODEL_NAME", "gpt-4o-mini"),
        "reasoning_model": os.getenv("REASONING_MODEL", "gpt-4o-mini"),
        "ollama_model": os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
        "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        "mcp_tools": [
            {"name": name, "required_env_vars": tool.required_env_vars}
            for name, tool in state.mcp_registry.tools.items()
        ],
    }


@app.post("/api/settings")
def save_settings(body: SettingsRequest, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    updates: Dict[str, str] = {}
    if body.openai_api_key:
        updates["OPENAI_API_KEY"] = body.openai_api_key
    if body.langchain_tracing is not None:
        updates["LANGCHAIN_TRACING_V2"] = "true" if body.langchain_tracing else "false"
    if body.langchain_api_key:
        updates["LANGCHAIN_API_KEY"] = body.langchain_api_key
    if body.langchain_project:
        updates["LANGCHAIN_PROJECT"] = body.langchain_project
    if body.mcp_credentials:
        updates.update(body.mcp_credentials)
    if body.model_name:
        updates["MODEL_NAME"] = body.model_name
    if body.reasoning_model:
        updates["REASONING_MODEL"] = body.reasoning_model
    if body.ollama_model:
        updates["OLLAMA_MODEL"] = body.ollama_model
    if body.ollama_base_url:
        updates["OLLAMA_BASE_URL"] = body.ollama_base_url

    _apply_settings(updates)
    state.reload_llm_router()
    return {"saved": True}


class ChangeCredentialsRequest(BaseModel):
    current_password: str
    new_username: Optional[str] = None
    new_password: Optional[str] = None


@app.post("/api/settings/credentials")
def change_credentials(body: ChangeCredentialsRequest, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Change the login username/password. Stored the same way as everything
    else in Settings — no .env access required. Requires the current
    password so a stolen/left-open session can't silently take over login."""
    current_admin_pass = os.getenv("ADMIN_PASSWORD", "")
    if not current_admin_pass or body.current_password != current_admin_pass:
        # 400, not 401: the frontend treats any 401 as "session expired" and
        # force-redirects to /login — a wrong current-password guess here
        # must surface as an inline form error, not a forced logout.
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if not body.new_username and not body.new_password:
        raise HTTPException(status_code=400, detail="Provide a new username and/or password")

    updates: Dict[str, str] = {}
    if body.new_username:
        updates["ADMIN_USERNAME"] = body.new_username
    if body.new_password:
        if len(body.new_password) < 6:
            raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
        updates["ADMIN_PASSWORD"] = body.new_password

    _apply_settings(updates)
    changed = []
    if "ADMIN_USERNAME" in updates:
        changed.append("Username changed")
    if "ADMIN_PASSWORD" in updates:
        changed.append("Password changed")
    AuditLogger().log_action(
        action="Login Credentials Changed", username=user["u"], status="Success",
        target=updates.get("ADMIN_USERNAME", user["u"]),
        details=", ".join(changed),
    )
    return {"saved": True, "new_username": updates.get("ADMIN_USERNAME")}


# ═══════════════════════════════════════════════════════════════════════════
# Token usage
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/token-usage")
def token_usage(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    df = state.token_tracker.get_historical(days=30)
    if df.empty:
        return {
            "total_tokens": 0, "total_cost_usd": 0.0, "call_count": 0, "avg_duration_ms": 0,
            "by_model": {}, "by_use_case": {}, "by_stage": {}, "timeline": [],
        }

    by_model = df.groupby("model")["cost_usd"].sum().round(6).to_dict()
    by_use_case = df.groupby("use_case")["cost_usd"].sum().round(6).to_dict()
    by_stage = df.groupby("stage")["cost_usd"].sum().round(6).to_dict()

    return {
        "total_tokens": int(df["input_tokens"].sum() + df["output_tokens"].sum()),
        "total_cost_usd": round(float(df["cost_usd"].sum()), 6),
        "call_count": int(len(df)),
        "avg_duration_ms": int(df["duration_ms"].mean()),
        "by_model": by_model,
        "by_use_case": {USE_CASE_LABELS.get(k, k): v for k, v in by_use_case.items()},
        "by_stage": by_stage,
        "timeline": df_to_records(df.tail(200)),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Observability
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/observability")
def observability(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    metrics = InAppMetrics()
    return {
        "traces": trace_store.get_traces(limit=50),
        "hallucination_reports": trace_store.get_hallucination_reports(),
        "health_summary": metrics.get_summary(),
        "guardrail_events": metrics.guardrail_events[-50:],
        "audit_log": AuditLogger().get_logs(limit=50),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Copilot — hybrid (semantic + BM25) RAG over the 16 datasets + uploaded docs.
# See backend/rag_service.py and app/rag/{indexes,ingestor,retriever}.py.
# ═══════════════════════════════════════════════════════════════════════════

_UPLOAD_MAX_BYTES = 10 * 1024 * 1024  # 10MB per file, matches the UI copy
_UPLOAD_ALLOWED_EXT = {".txt", ".json", ".log", ".csv", ".py", ".js", ".yaml", ".yml", ".pdf", ".docx", ".tf", ".conf"}


class CopilotRequest(BaseModel):
    message: str


@app.get("/api/copilot/starters")
def copilot_starters(user: dict = Depends(get_current_user)) -> List[str]:
    return COPILOT_STARTER_QUESTIONS


@app.get("/api/copilot/memory")
def copilot_memory(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Status of the AI Memory Bank — dataset indexing progress + uploaded files."""
    return state.rag.status()


@app.post("/api/copilot/upload")
async def copilot_upload(file: UploadFile = File(...), user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    from pathlib import PurePosixPath
    from app.upload.processor import FileUploadProcessor

    ext = PurePosixPath(file.filename or "").suffix.lower()
    if ext not in _UPLOAD_ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(_UPLOAD_ALLOWED_EXT))}")

    raw = await file.read()
    if len(raw) > _UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=400, detail=f"File exceeds the {_UPLOAD_MAX_BYTES // (1024*1024)}MB limit")

    class _InMemoryFile:
        def __init__(self, name: str, data: bytes) -> None:
            self.name = name
            self._data = data

        def getvalue(self) -> bytes:
            return self._data

    processor = FileUploadProcessor()
    parsed = processor.process(_InMemoryFile(file.filename or "upload", raw))

    if parsed.get("type") == "error":
        raise HTTPException(status_code=400, detail=f"Could not parse file: {parsed.get('data')}")
    elif parsed.get("type") == "text":
        text = parsed["data"]
    elif parsed.get("type") == "dataframe":
        text = parsed["data"].to_csv(index=False)
    elif parsed.get("type") == "dict":
        import json as _json
        text = _json.dumps(parsed["data"], indent=2, default=str)
    else:
        text = ""

    if not text.strip():
        raise HTTPException(status_code=400, detail="File parsed to empty content")

    doc = state.rag.ingest_upload(file.filename or "upload", text)

    AuditLogger().log_action(
        action="Copilot Memory Bank — File Uploaded",
        username=user["u"], status="Success", target=doc.filename,
        details=f"Chunked into {doc.chunks} segments ({doc.chars:,} chars) and embedded into the 'uploads' FAISS collection.",
    )

    return {"filename": doc.filename, "chunks": doc.chunks, "chars": doc.chars}


@app.delete("/api/copilot/uploads")
def copilot_clear_uploads(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    state.rag.clear_uploads()
    return {"cleared": True}


@app.post("/api/copilot/message")
def copilot_message(body: CopilotRequest, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    results = state.rag.query(body.message, top_k=8)
    context = state.rag.build_context(results, max_tokens=4000)

    sources = [
        {
            "text": r.get("text", "")[:500],
            "score": round(r.get("rrf_score", r.get("score", 0.0)), 4),
            "collection": r.get("metadata", {}).get("collection", ""),
            "source": r.get("metadata", {}).get("source"),
        }
        for r in results
    ]

    answer = None
    if state.llm_router is not None:
        try:
            system = (
                "You are Antigravity Copilot, an AI security assistant for the Securing AI platform. "
                "Answer using ONLY the retrieved context below — it was pulled via hybrid semantic + "
                "keyword search over the platform's 16 datasets and any analyst-uploaded documents. "
                "Cite specific values (IDs, counts, names) from the context. If the context doesn't "
                "contain the answer, say so plainly rather than guessing."
            )
            user_msg = f"RETRIEVED CONTEXT:\n{context}\n\nQUESTION: {body.message}" if context else (
                f"No relevant context was retrieved for this question. QUESTION: {body.message}"
            )
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ]
            resp = state.llm_router.invoke(messages, model_tier="primary", temperature=0.3)
            answer = resp.get("content")
        except Exception:
            answer = None

    if not answer:
        if sources:
            answer = (
                f"Retrieved {len(sources)} relevant records via hybrid search, but couldn't generate a "
                "natural-language answer. Configure a valid OpenAI API key in Settings — see the sources below."
            )
        else:
            answer = (
                "No matching context found yet. The AI Memory Bank may still be indexing "
                "(check the pipeline status), or try rephrasing the question."
            )

    try:
        state.memory.store(user=user["u"], entry_type="copilot_message", key=f"msg_{time.time()}",
                            value={"role": "user", "content": body.message}, session_id="api_session")
        state.memory.store(user=user["u"], entry_type="copilot_message", key=f"msg_{time.time()}_r",
                            value={"role": "assistant", "content": answer}, session_id="api_session")
    except Exception:
        pass

    return {"answer": answer, "sources": sources}


# ═══════════════════════════════════════════════════════════════════════════
# Static frontend (production build) — mounted last so /api/* takes priority.
# StaticFiles(html=True) only serves index.html at "/" and for directories; it
# 404s on client-side routes like /phase/identify or /agents (no such file on
# disk). React Router owns those paths once the SPA shell has loaded, so any
# GET that isn't a real static asset and isn't under /api falls back to
# index.html here, letting the client-side router take over.
# ═══════════════════════════════════════════════════════════════════════════

_FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="frontend-assets")

    _INDEX_HTML = _FRONTEND_DIST / "index.html"

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_INDEX_HTML)
