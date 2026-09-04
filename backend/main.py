"""
Securing AI — FastAPI backend.
Wraps the existing app/ business logic (synthetic data engine, LangGraph agent
pipeline, KPI engine, guardrails, hallucination detector, MCP registry) behind
a REST API consumed by the React frontend. No business logic is duplicated
here — this module is orchestration + JSON shaping only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import random
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, File, Response
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
from app.mcp.client import MCPClient
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

def _compute_storyline() -> List[Dict[str, str]]:
    """Real per-phase status for the story bar's case-file thread — derived
    entirely from state.datasets already fetched this run, no new calls.
    Mirrors the same `if df is not None and not df.empty` checks
    KPIEngine already uses throughout app/kpi/engine.py."""
    ds = state.datasets

    def _empty(name: str) -> bool:
        df = ds.get(name)
        return df is None or df.empty

    nodes = []

    gov = ds.get("governance_compliance_evaluation")
    if _empty("governance_compliance_evaluation"):
        nodes.append({"phase": "govern", "status": "pending", "label": "policy not loaded"})
    else:
        triggered = int(gov["triggered"].sum())
        nodes.append({"phase": "govern", "status": "warning" if triggered else "clean",
                      "label": f"{triggered} rule(s) triggered" if triggered else f"{len(gov)} rule(s) compliant"})

    agents = ds.get("ai_agent_inventory")
    if _empty("ai_agent_inventory"):
        nodes.append({"phase": "identify", "status": "pending", "label": "no agent discovered yet"})
    else:
        risk = ds.get("agent_risk_register")
        blast = risk.iloc[0]["blast_radius"] if risk is not None and not risk.empty else "unknown"
        nodes.append({"phase": "identify", "status": "clean", "label": f"{len(agents)} real agent(s) · risk {blast.lower()}"})

    secrets = ds.get("secrets_exposure_scan")
    if _empty("secrets_exposure_scan") and _empty("guardrail_policies"):
        nodes.append({"phase": "protect", "status": "pending", "label": "not checked yet"})
    else:
        gaps = int(secrets["isolation_status"].astype(str).str.contains("Not Isolated|Exposed", case=False, regex=True).sum()) if secrets is not None and not secrets.empty else 0
        nodes.append({"phase": "protect", "status": "warning" if gaps else "clean",
                      "label": f"{gaps} gap(s) found" if gaps else "no gaps found"})

    redteam = ds.get("redteam_campaign_results")
    if _empty("redteam_campaign_results"):
        nodes.append({"phase": "detect", "status": "pending", "label": "not tested yet"})
    else:
        leaked = bool((redteam["outcome"] == "Success").any())
        nodes.append({"phase": "detect", "status": "critical" if leaked else "clean",
                      "label": "leak confirmed" if leaked else "no leak found"})

    if _empty("containment_actions"):
        if not _empty("incident_queue"):
            nodes.append({"phase": "respond", "status": "warning", "label": "incident open"})
        else:
            nodes.append({"phase": "respond", "status": "pending", "label": "no incident yet"})
    else:
        nodes.append({"phase": "respond", "status": "resolved", "label": "agent contained"})

    if _empty("rollback_events") and _empty("guardrail_update_log"):
        nodes.append({"phase": "recover", "status": "pending", "label": "no fix yet"})
    else:
        nodes.append({"phase": "recover", "status": "resolved", "label": "fix verified"})

    return nodes


@app.get("/api/dashboard")
def dashboard(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    kpi = state.kpi_engine
    kpis = kpi.compute_all()
    posture_index = kpi.get_ai_readiness_index()

    gauges = [
        {"phase": uc, "label": USE_CASE_LABELS[uc], "score": kpi.get_use_case_score(uc), "color": USE_CASE_COLOURS[uc]}
        for uc in ["identify", "protect", "detect", "govern", "respond", "recover"]
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
    phase_scores = {uc: kpi.get_use_case_score(uc) for uc in ["identify", "protect", "detect", "govern", "respond", "recover"]}
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
        "storyline": _compute_storyline(),
        "trend": trend,
        "blast_radius": blast_radius,
        "recent_operations": audit,
        # Real per-phase fetch failures against the current live target —
        # e.g. a retargeted repo missing governance/policy.yaml, or a token
        # without access. Empty dict means every phase's real fetch succeeded.
        "data_health": state.fetch_errors,
    }


@app.get("/api/asset-graph")
def asset_graph(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """The reviewer's specific ask: a connective view of the real entities
    already flowing through the system — not a new fetch, just a different
    shape over app.datasets (all real since Milestone 3). Nodes/edges are
    built directly from real rows; an empty dataset just means fewer nodes,
    never a fabricated placeholder node."""
    ds = state.datasets
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    agents = ds.get("ai_agent_inventory")
    agent_id = None
    if agents is not None and not agents.empty:
        row = agents.iloc[0]
        agent_id = row["agent_id"]
        risk_row = ds.get("agent_risk_register")
        risk_score = None
        blast_radius = None
        if risk_row is not None and not risk_row.empty:
            r = risk_row.iloc[0]
            risk_score = float(r["risk_score"])
            blast_radius = r["blast_radius"]
        nodes.append({
            "id": agent_id, "type": "agent", "label": row["agent_name"],
            "detail": f"{row['agent_type']} · {row['sanctioned_status']} · {row['llm_provider']}",
            "risk_score": risk_score, "blast_radius": blast_radius,
            "internet_facing": bool(row["internet_facing"]),
        })

    lineage = ds.get("model_data_lineage")
    if agent_id and lineage is not None and not lineage.empty:
        for _, m in lineage.iterrows():
            mid = f"model:{m['model_id']}"
            nodes.append({"id": mid, "type": "model", "label": m["model_name"], "detail": f"base: {m['base_model']}"})
            edges.append({"from": mid, "to": agent_id, "label": "powers"})

    tool_access = ds.get("tool_access_map")
    if agent_id and tool_access is not None and not tool_access.empty:
        for _, t in tool_access.iterrows():
            tid = f"identity:{t['mapping_id']}"
            nodes.append({
                "id": tid, "type": "identity", "label": t["tool_name"],
                "detail": f"{t['granted_permission']} access" + (" — over-provisioned" if bool(t.get("over_provisioned")) else ""),
            })
            edges.append({"from": tid, "to": agent_id, "label": t["granted_permission"]})

    secrets = ds.get("secrets_exposure_scan")
    if agent_id and secrets is not None and not secrets.empty:
        for _, s in secrets.iterrows():
            sid = f"secret:{s['secret_id']}"
            nodes.append({
                "id": sid, "type": "secret", "label": s["secret_type"][:40],
                "detail": s["isolation_status"], "critical": "Not Isolated" in str(s["isolation_status"]) or "Exposed" in str(s["isolation_status"]),
            })
            edges.append({"from": sid, "to": agent_id, "label": "exposed in"})

    policies = ds.get("guardrail_policies")
    governance = ds.get("governance_compliance_evaluation")
    triggered_by_rule = {}
    if governance is not None and not governance.empty:
        for _, g in governance.iterrows():
            triggered_by_rule[g["rule_id"]] = {"triggered": bool(g["triggered"]), "decision": g["decision"]}
    if agent_id and policies is not None and not policies.empty:
        for _, p in policies.iterrows():
            pid = f"policy:{p['policy_id']}"
            gov = triggered_by_rule.get(p["policy_id"])
            nodes.append({
                "id": pid, "type": "policy", "label": p["policy_id"],
                "detail": p["policy_name"],
                "triggered": gov["triggered"] if gov else None,
                "decision": gov["decision"] if gov else None,
            })
            edges.append({
                "from": pid, "to": agent_id,
                "label": (gov["decision"] if gov else p["enforcement_mode"]),
                "critical": bool(gov and gov["triggered"]),
            })

    return {"nodes": nodes, "edges": edges}


# ═══════════════════════════════════════════════════════════════════════════
# Phases / stages
# ═══════════════════════════════════════════════════════════════════════════

PHASE_KEYS = ["identify", "protect", "detect", "govern", "respond", "recover"]


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
    # "live" (default): the real LiveDataEngine data every stage always
    # analyses. "mcp": same real base data, plus real-time external
    # enrichment for the stages that support one — additive, not a fallback
    # tier. That enrichment is two things under one option, both real: (a)
    # Lakera/Garak/PyRIT for the three stages they're actually wired to, and
    # (b) a generic external_source (bring-your-own SIEM/API — see
    # app/mcp/registry.py) that applies to any stage once genuinely
    # connected. No more "synthetic"/"upload" — nothing in this app's data
    # path is fabricated or uploaded any more (Milestone 3+).
    data_source: str = "live"


def _maybe_augment_with_live_mcp(uc: str, stage_key: str, data_source: str) -> Dict[str, pd.DataFrame]:
    """When data_source == 'mcp' and the relevant real tool is actually live
    (credentials configured — app/mcp/registry.py's tools only), call it for
    real and return extra dataset entries to merge into what the agent
    analyses. Empty dict when not applicable, in which case the run proceeds
    on the normal real datasets exactly as before — this never fabricates a
    "live" result."""
    if data_source != "mcp":
        return {}

    extra: Dict[str, pd.DataFrame] = {}

    # Generic external source (SIEM/API) — applies to any stage, unlike the
    # three tool-specific hooks below, since there's no fixed vendor to
    # scope it to. Only fires anything when a user has actually configured
    # SIEM_API_URL/SIEM_API_KEY in Settings; otherwise this is a no-op, same
    # as every other honest mock-fallback tool in this app.
    ext_status = state.mcp_client.get_connection_status("external_source")
    if ext_status["live"]:
        try:
            events = state.mcp_client.external_source_fetch_events()
            if events:
                extra["external_source_events"] = pd.DataFrame(events)
        except MCPClient.LiveConnectorError as exc:
            logging.getLogger(__name__).warning("external_source fetch failed: %s", exc)
            extra["external_source_events"] = pd.DataFrame([{"note": f"External source fetch failed: {exc}"}])

    if uc == "protect" and stage_key == "guardrail_proxy":
        status = state.mcp_client.get_connection_status("lakera_guard")
        if status["live"]:
            # Real prompt samples to screen — deliberately Detect's real
            # adversarial_prompt_corpus.payload, not guardrail_events. The
            # latter is honestly *always* empty (no real guardrail
            # middleware is deployed on the target agent — that's the whole
            # gap this phase demonstrates), so sourcing samples from it made
            # this branch permanently unreachable dead code: a real,
            # correctly-configured LAKERA_API_KEY could never produce a
            # result because there was never anything to sample. The
            # adversarial corpus is unconditionally populated every run
            # (LiveDataEngine._generate_detect()) and is exactly the real
            # incoming-prompt traffic a real guardrail proxy would screen.
            corpus = state.datasets.get("adversarial_prompt_corpus")
            samples = (
                corpus["payload"].drop_duplicates().head(5).tolist()
                if corpus is not None and not corpus.empty else []
            )
            rows = []
            for text in samples:
                result = state.mcp_client.screen_prompt(text)
                rows.append({"prompt_sample": text, "lakera_flagged": result.get("flagged"), "live": result.get("live")})
            if rows:
                lakera_df = pd.DataFrame(rows)
                extra["lakera_guard_live_results"] = lakera_df
                # Persist beyond this one request, and recompute KPIs from it
                # immediately — otherwise a real Lakera scan only ever
                # changed this run's LLM-written prose, never anything the
                # rest of the app (Guardrail Block Rate, Protect's phase
                # score, the overall posture index) actually reads. See
                # app/kpi/engine.py: Guardrail Block Rate now prefers this
                # real dataset over its static fallback when present.
                state.datasets["lakera_guard_live_results"] = lakera_df
                state.recompute_kpis()

    elif uc == "detect" and stage_key in ("injection_detection", "red_teaming"):
        # Real target, not the placeholder "demo-agent-fleet" string this
        # carried from before the live rebuild (when there was no single
        # real target to point a runner at) — garak/pyrit need a real,
        # reachable URL to actually scan.
        target_agent_url = os.getenv("TARGET_AGENT_URL", "").rstrip("/")
        scan_target = f"{target_agent_url}/chat" if target_agent_url else "demo-agent-fleet"
        for tool_name in ["garak", "pyrit"]:
            status = state.mcp_client.get_connection_status(tool_name)
            if status["live"]:
                result = state.mcp_client.trigger_runner_scan(tool_name, target=scan_target, target_label="Meridian Financial Support Agent")
                findings = result.get("findings") or []
                errors = result.get("errors")
                if errors:
                    # Real per-probe failures (e.g. a rate limit on the
                    # shared free-tier LLM backend when garak's ~150-190s
                    # scan runs immediately before pyrit's) — surfaced, not
                    # silently dropped, so a smaller real finding count has
                    # a real reason attached rather than reading as a clean
                    # scan that just happened to find less.
                    logging.getLogger(__name__).warning("%s runner scan had real errors: %s", tool_name, errors)
                if not findings:
                    findings = [{"note": "scan returned no findings" + (f" (errors: {errors})" if errors else "")}]
                elif errors:
                    findings = findings + [{"note": f"{len(errors)} probe(s) failed with real errors", "errors": "; ".join(errors)[:300]}]
                scan_df = pd.DataFrame(findings)
                extra[f"{tool_name}_live_scan"] = scan_df
                # Same fix as Lakera's (see the guardrail_proxy branch above):
                # persist beyond this one request and recompute KPIs from it
                # immediately, so a real garak/pyrit scan's real per-attempt
                # canary_leaked results actually widen the real sample behind
                # Red-Team Attack Success Rate below — not just the 3 baseline
                # direct-call rows in redteam_campaign_results, which is all
                # that KPI reflected before, no matter how thorough a real
                # scan you'd just run.
                state.datasets[f"{tool_name}_live_scan"] = scan_df

                # Propagate confirmed findings to redteam_campaign_results and Govern
                any_leaked = any(bool(f.get("canary_leaked") or f.get("model_leaked_raw")) for f in findings if isinstance(f, dict))
                if any_leaked:
                    try:
                        from datetime import datetime, timezone
                        from app.data.live_engine import _AGENT_ID
                        redteam = state.datasets.get("redteam_campaign_results")
                        rt_rows = redteam.to_dict("records") if redteam is not None and not redteam.empty else []
                        for f in findings:
                            if isinstance(f, dict) and (f.get("canary_leaked") or f.get("model_leaked_raw")):
                                rt_rows.append({
                                    "test_id": f"{tool_name.upper()}-{uuid.uuid4().hex[:6]}",
                                    "campaign_id": f"CAMP-LIVE-{tool_name.upper()}",
                                    "campaign_name": f"Live {tool_name.title()} Vulnerability Assessment",
                                    "agent_id": _AGENT_ID,
                                    "outcome": "Success",
                                    "severity": "Critical" if f.get("canary_leaked") else "High",
                                    "technique": f.get("probe") or f.get("category") or f"{tool_name} automated probe",
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                })
                        state.datasets["redteam_campaign_results"] = pd.DataFrame(rt_rows)
                        if "governance_compliance_evaluation" in state.datasets:
                            gov_df = state.datasets["governance_compliance_evaluation"].copy()
                            mask = gov_df["rule_id"] == "GOV-002"
                            if mask.any():
                                gov_df.loc[mask, "triggered"] = True
                                gov_df.loc[mask, "decision"] = "Blocked"
                                gov_df.loc[mask, "evidence"] = f"Live {tool_name.title()} scan confirmed real secret leakage against live target agent."
                                state.datasets["governance_compliance_evaluation"] = gov_df
                    except Exception as exc:
                        logging.getLogger(__name__).warning("Failed to propagate %s live findings to redteam/govern: %s", tool_name, exc)
        state.recompute_kpis()

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
    # Recover's Guardrail Update Loop needs to see the same live consolidated
    # incident_queue Respond uses (not just its own rollback_events) to
    # genuinely cross-reference which real open Govern/Identify/Protect/
    # Detect items still lack a deployed update — see its real prompt
    # instructions in agent_manager.py. Added here rather than as its
    # official input_key so the UI's "Target Ingested Dataset" panel still
    # shows the Rollback Event Log as the primary displayed input.
    if uc == "recover" and stage_key == "guardrail_update" and "incident_queue" not in input_keys:
        input_keys.append("incident_queue")

    if uc == "recover":
        try:
            state.mcp_client.target_agent_set_guardrail_enabled(True)
        except Exception as exc:
            logging.getLogger(__name__).warning("Failed to enable target agent guardrail during recover stage: %s", exc)

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
    # Same real decision path as check_hitl_required above, returned as a
    # structured "Policy → Decision → Control → Evidence" trace instead of
    # just the bare bool — the reviewer's ask that this app's existing
    # V5_THRESHOLDS gate logic be surfaced, not hidden (Milestone 6).
    decision_trace = gm.explain_hitl_decision(
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
        "policy_decision_trace": decision_trace,
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


# Real Respond/Recover actions a Slack approval can trigger — deliberately
# limited to actions against our own demo target agent, never anything that
# touches repo collaborator access (see AGENTS.md's explicit safety note on
# why github_revoke_collaborator is never wired to auto-execute here).
def _restore_and_secure_agent() -> Dict[str, Any]:
    try:
        state.mcp_client.target_agent_set_guardrail_enabled(True)
    except Exception as exc:
        logging.getLogger(__name__).warning("Failed to enable guardrail on target agent during restore: %s", exc)
    return state.mcp_client.target_agent_set_disabled(False)


_REAL_ACTION_EXECUTORS = {
    "suspend_target_agent": lambda: state.mcp_client.target_agent_set_disabled(True),
    "restore_target_agent": _restore_and_secure_agent,
}


class RequestApprovalRequest(BaseModel):
    action_type: str  # one of _REAL_ACTION_EXECUTORS's keys
    summary: str


@app.post("/api/phases/{uc}/stages/{stage_key}/request-approval")
def request_approval(uc: str, stage_key: str, body: RequestApprovalRequest, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Posts a real Slack approval request for a real Respond/Recover action
    and registers it as pending — the actual action fires from
    slack_interactions() below once a human clicks Approve in Slack, not
    from this call. This route only exists to kick off that real round trip."""
    if uc not in PHASE_KEYS:
        raise HTTPException(status_code=404, detail="Unknown phase")
    if body.action_type not in _REAL_ACTION_EXECUTORS:
        raise HTTPException(status_code=400, detail=f"Unknown action_type '{body.action_type}'. Valid: {list(_REAL_ACTION_EXECUTORS)}")

    action_id = uuid.uuid4().hex[:12]
    slack_result = state.mcp_client.slack_post_approval_request(body.summary, action_id)
    state.pending_actions[action_id] = {
        "uc": uc,
        "stage_key": stage_key,
        "action_type": body.action_type,
        "summary": body.summary,
        "requested_by": user["u"],
        "requested_at": time.time(),
    }
    AuditLogger().log_action(
        action=f"Real Action Requested (awaiting Slack approval): {body.action_type}",
        username=user["u"],
        status="Pending",
        target=action_id,
        details=f"{body.summary} — real Slack approval message posted to channel {slack_result.get('channel')}.",
    )
    return {"action_id": action_id, "slack": slack_result}


@app.post("/api/recover/replay-detect")
def replay_detect(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Recover's live proof: re-sends the same real injection payload used
    in Detect (app/data/live_engine.py's REAL_INJECTION_PAYLOADS[0]) to the
    real deployed target agent right now, and checks the real reply for the
    real canary. Reprovable on demand — not a stored screenshot."""
    from app.data.live_engine import REAL_INJECTION_PAYLOADS, _canary_leaked

    # Explicitly ensure the output guardrail is deployed and active for the replay proof!
    try:
        state.mcp_client.target_agent_set_guardrail_enabled(True)
    except Exception as exc:
        logging.getLogger(__name__).warning("Failed to deploy output guardrail during replay-detect: %s", exc)

    payload = REAL_INJECTION_PAYLOADS[0]
    try:
        result = state.mcp_client.target_agent_chat(payload["payload"], provider="groq")
    except MCPClient.LiveConnectorError as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't reach the real target agent: {exc}")

    reply = result.get("reply") or ""
    leaked = _canary_leaked(reply)
    model_leaked_raw = bool(result.get("model_leaked_raw", leaked))
    AuditLogger().log_action(
        action="Recover Replay — Live",
        username=user["u"],
        status="Leaked" if leaked else "Blocked",
        target="meridian-support-agent",
        details=f"Real replay of '{payload['category']}' against the live target agent. {'Canary leaked.' if leaked else 'No leak — real fix held.'}",
    )
    return {"prompt": payload["payload"], "category": payload["category"], "response": reply, "leaked": leaked, "model_leaked_raw": model_leaked_raw}


_HISTORICAL_LEAK_EVIDENCE_PATH = PROJECT_ROOT / "data" / "historical_leak_evidence.json"


@app.get("/api/recover/historical-leak-evidence")
def get_historical_leak_evidence(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """The real, durably-captured pre-fix leak evidence (see the capture
    endpoint below) — or {"captured": false} if it's never been captured on
    this deployment. Read-only; never triggers a real capture itself."""
    if not _HISTORICAL_LEAK_EVIDENCE_PATH.exists():
        return {"captured": False}
    return {"captured": True, **json.loads(_HISTORICAL_LEAK_EVIDENCE_PATH.read_text(encoding="utf-8"))}


@app.post("/api/recover/capture-historical-leak")
def capture_historical_leak(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """One-time, deliberate reproduction of the real pre-fix leak, to
    permanently capture durable 'before' evidence for Recover — see
    AGENTS.md's live-demo notes for why this exists (no exact historical
    leak transcript was ever preserved otherwise) and the explicit user
    approval this required, given it briefly weakens a real live guardrail.

    Real, in order: disables meridian-support-agent's real output guardrail
    → sends a real jailbreak payload → captures whatever real reply comes
    back → ALWAYS re-enables the guardrail (try/finally — runs even if the
    chat call itself fails) → persists the real result to
    data/historical_leak_evidence.json so this never needs to run again.

    If the real attempt doesn't leak this time (model behaviour isn't
    perfectly deterministic), any previously-captured real evidence is left
    untouched rather than being overwritten with a non-leak — this endpoint
    only ever records a real confirmed leak, never a negative result."""
    from datetime import datetime, timezone
    from app.data.live_engine import REAL_INJECTION_PAYLOADS, _canary_leaked

    payload = REAL_INJECTION_PAYLOADS[0]

    state.mcp_client.target_agent_set_guardrail_enabled(False)
    try:
        result = state.mcp_client.target_agent_chat(payload["payload"], provider="groq")
    except MCPClient.LiveConnectorError as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't reach the real target agent: {exc}")
    finally:
        state.mcp_client.target_agent_set_guardrail_enabled(True)

    reply = result.get("reply") or ""
    leaked = _canary_leaked(reply)

    AuditLogger().log_action(
        action="Historical Leak Evidence Capture Attempt — Real",
        username=user["u"],
        status="Leaked" if leaked else "No Leak",
        target="meridian-support-agent",
        details=(
            f"Real guardrail toggle off → real '{payload['category']}' payload → real reply captured → "
            f"guardrail restored. {'Real leak confirmed and persisted.' if leaked else 'No leak this attempt — not persisted; existing evidence (if any) left unchanged.'}"
        ),
    )

    if not leaked:
        return {"captured": False, "leaked": False, "response": reply, "note": "No leak this attempt — real model behaviour isn't perfectly deterministic. Try again, or check existing evidence via GET."}

    evidence = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "captured_by": user["u"],
        "prompt": payload["payload"],
        "category": payload["category"],
        "response": reply,
        "leaked": True,
        "note": "Real leak reproduced via a deliberate, brief, admin-authenticated guardrail toggle — the real output-side fix (meridian-support-agent commit 2b89c37) was restored immediately after this one real capture.",
    }
    _HISTORICAL_LEAK_EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _HISTORICAL_LEAK_EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return {"captured": True, **evidence}


class LiveVulnerabilityDemoRequest(BaseModel):
    prompt_id: str = "PROMPT-001"  # one of REAL_INJECTION_PAYLOADS
    provider: str = "groq"


@app.post("/api/detect/live-vulnerability-demo")
def detect_live_vulnerability_demo(body: LiveVulnerabilityDemoRequest, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """The repeatable, on-demand counterpart to capture-historical-leak
    above — same real mechanism (briefly disable the real output guardrail,
    send a real payload, ALWAYS restore the guardrail via try/finally), but
    triggerable any time from Detect instead of a one-time historical
    capture. Exists because a deterministic exact-string guardrail is hard
    to beat with clever prompting alone (verified this session: neither
    character-spacing nor reversal produced a genuine bypass — allam-2-7b
    isn't reliable enough at exact character transforms to smuggle the real
    key past an exact-match check, and kept blurting the literal key
    alongside its attempt). Rather than chase an unreliable prompt-injection
    bypass, this shows the real, honest alternative fact directly: if this
    guardrail weren't there, the jailbreak the app already proves works
    (model_leaked_raw) would produce a real visible leak right now. Recover's
    replay-detect endpoint is the deliberate counterpart — same real payload,
    guardrail back to its normal on state, proving the fix holds."""
    from app.data.live_engine import REAL_INJECTION_PAYLOADS, _canary_leaked

    payload = next((p for p in REAL_INJECTION_PAYLOADS if p["prompt_id"] == body.prompt_id), REAL_INJECTION_PAYLOADS[0])

    state.mcp_client.target_agent_set_guardrail_enabled(False)
    try:
        result = state.mcp_client.target_agent_chat(payload["payload"], provider=body.provider)
    except MCPClient.LiveConnectorError as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't reach the real target agent: {exc}")
    finally:
        restore = state.mcp_client.target_agent_set_guardrail_enabled(True)

    reply = result.get("reply") or ""
    leaked = _canary_leaked(reply)

    AuditLogger().log_action(
        action="Live Vulnerability Demo — Detect Panel",
        username=user["u"],
        status="Leaked" if leaked else "No Leak",
        target="meridian-support-agent",
        details=(
            f"Real guardrail toggle off → real '{payload['category']}' payload → real reply captured → "
            f"guardrail restored (guardrail_enabled={restore.get('guardrail_enabled')}). "
            f"{'Real leak confirmed.' if leaked else 'No leak this attempt — real model behaviour is not perfectly deterministic.'}"
        ),
    )

    return {
        "prompt": payload["payload"],
        "category": payload["category"],
        "response": reply,
        "leaked": leaked,
        "guardrail_restored": bool(restore.get("guardrail_enabled")),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Dashboard — live AI security tools panel (Lakera Guard interactive test)
# ═══════════════════════════════════════════════════════════════════════════

# One added real benign prompt, kept separate from
# app.data.live_engine.REAL_INJECTION_PAYLOADS (which Detect's real
# adversarial_prompt_corpus iterates unconditionally) — adding it there
# would silently grow Detect's real corpus row count and campaign results
# with a non-attack row. This picker needs a "clear verdict" example too, so
# it's defined here instead, alongside (not inside) that shared list.
_BENIGN_TEST_PROMPT = {"prompt_id": "PROMPT-BENIGN", "category": "Benign Baseline", "payload": "Hi, can you tell me your name and what you help with?"}


@app.get("/api/security-tools/test-prompts")
def security_tools_test_prompts(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """The real, curated prompt picker for the Dashboard's live Lakera Guard
    panel — the same 3 real injection payloads Detect actually sends to the
    live target agent, plus one real benign baseline for contrast."""
    from app.data.live_engine import REAL_INJECTION_PAYLOADS

    return {"prompts": REAL_INJECTION_PAYLOADS + [_BENIGN_TEST_PROMPT]}


class LakeraScreenRequest(BaseModel):
    prompt: str


@app.post("/api/security-tools/lakera-screen")
def lakera_screen(body: LakeraScreenRequest, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Real, synchronous Lakera Guard screening of one prompt — the
    interactive counterpart to Protect's Guardrail Proxy stage (which
    screens a fixed batch). Returns MCPClient.screen_prompt's real result
    as-is: {live, flagged, raw} — raw carries Lakera's own real response
    fields (action, metadata.request_uuid) so the UI can show something a
    skeptical viewer can point to as proof, not just a flagged/clear label."""
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt must not be empty")
    result = state.mcp_client.screen_prompt(prompt)
    if result.get("live"):
        AuditLogger().log_action(
            action="Lakera Guard Live Test — Dashboard Panel",
            username=user["u"],
            status="Flagged" if result.get("flagged") else "Clear",
            target="lakera_guard",
            details=f"Real Lakera Guard screen of a user-selected prompt: {'flagged' if result.get('flagged') else 'clear'}.",
        )
    return {"prompt": prompt, **result}


class GuardrailProxyChatRequest(BaseModel):
    prompt: str
    provider: str = "groq"


@app.post("/api/protect/guardrail-proxy/chat")
def guardrail_proxy_chat(body: GuardrailProxyChatRequest, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Real guardrail middleware — not a batch test against 4 fixed prompts,
    an actual proxy any prompt can be sent through. Deliberately free-text:
    a script replayed against the same known-flagged payloads would always
    produce the same result and prove nothing new each run.

    Real, in order: Lakera Guard screens the real input first. If flagged,
    the real target agent is never even called — a genuine block, not a
    simulated one — and a real row is appended to guardrail_events. If
    clear, the real prompt is forwarded to the real target agent, and its
    real reply is *also* screened (a second, independent real layer on top
    of whatever the target agent's own output check already did — see
    meridian-support-agent commit 2b89c37). Either way a real event is
    logged, so guardrail_events actually grows now instead of staying
    permanently empty (Section 43's documented honest gap — this is what
    finally closes it for real, not a workaround)."""
    from datetime import datetime, timezone
    from app.data.live_engine import _AGENT_ID

    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt must not be empty")

    def _log_event(event_type: str, action_taken: str) -> Dict[str, Any]:
        event = {
            "event_id": f"GPE-{uuid.uuid4().hex[:8]}",
            "agent_id": _AGENT_ID,
            "event_type": event_type,
            "action_taken": action_taken,
            "input_snippet_redacted": prompt[:120],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        existing = state.datasets.get("guardrail_events")
        rows = existing.to_dict("records") if existing is not None and not existing.empty else []
        rows.append(event)
        state.datasets["guardrail_events"] = pd.DataFrame(rows)
        state.recompute_kpis()
        return event

    input_screen = state.mcp_client.screen_prompt(prompt)
    if input_screen.get("flagged"):
        event = _log_event("prompt_injection_or_jailbreak", "Blocked")
        AuditLogger().log_action(
            action="Real Guardrail Proxy — Input Blocked",
            username=user["u"], status="Blocked", target="meridian-support-agent",
            details="Real Lakera Guard flagged this real prompt on input — never forwarded to the real target agent.",
        )
        return {"blocked": True, "blocked_at": "input", "lakera_input": input_screen, "reply": None, "event": event}

    try:
        result = state.mcp_client.target_agent_chat(prompt, provider=body.provider)
    except MCPClient.LiveConnectorError as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't reach the real target agent: {exc}")
    reply = result.get("reply") or ""
    model_leaked_raw = bool(result.get("model_leaked_raw", False))
    from app.data.live_engine import _canary_leaked
    canary_leaked = _canary_leaked(reply)

    output_screen = state.mcp_client.screen_prompt(reply) if reply else {"live": input_screen.get("live"), "flagged": False}
    if output_screen.get("flagged"):
        event = _log_event("sensitive_output", "Redacted")
        AuditLogger().log_action(
            action="Real Guardrail Proxy — Output Blocked",
            username=user["u"], status="Redacted", target="meridian-support-agent",
            details="Real Lakera Guard flagged the real target agent's real reply — withheld from the caller.",
        )
        return {"blocked": True, "blocked_at": "output", "lakera_input": input_screen, "lakera_output": output_screen, "reply": "[REDACTED BY GUARDRAIL PROXY]", "event": event, "model_leaked_raw": model_leaked_raw, "canary_leaked": False}

    if canary_leaked:
        event = _log_event("credential_exfiltrated", "Leaked (Gaps in Output Control)")
        AuditLogger().log_action(
            action="Real Guardrail Proxy — Exfiltration Detected",
            username=user["u"], status="Leaked", target="meridian-support-agent",
            details="Prompt bypassed input screening; target agent output guardrail inactive — confidential credential leaked.",
        )
        # Update redteam_campaign_results so Govern immediately sees that an active leak occurred
        try:
            redteam = state.datasets.get("redteam_campaign_results")
            rows = redteam.to_dict("records") if redteam is not None and not redteam.empty else []
            rows.append({
                "test_id": f"PROXY-LEAK-{uuid.uuid4().hex[:6]}",
                "campaign_id": "CAMP-LIVE-PROXY",
                "campaign_name": "Guardrail Proxy Evasion Bypass",
                "agent_id": _AGENT_ID,
                "outcome": "Success",
                "severity": "Critical",
                "technique": "Evasion Bypass (Prompt-Injection Slipthrough)",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            state.datasets["redteam_campaign_results"] = pd.DataFrame(rows)
            # Recompute Govern compliance so GOV-002 immediately shows Blocked
            if "governance_compliance_evaluation" in state.datasets:
                gov_df = state.datasets["governance_compliance_evaluation"].copy()
                mask = gov_df["rule_id"] == "GOV-002"
                if mask.any():
                    gov_df.loc[mask, "triggered"] = True
                    gov_df.loc[mask, "decision"] = "Blocked"
                    gov_df.loc[mask, "evidence"] = "Live prompt injection through Guardrail Proxy successfully extracted confidential credential (real canary leak confirmed)."
                    state.datasets["governance_compliance_evaluation"] = gov_df
            state.recompute_kpis()
        except Exception as exc:
            logging.getLogger(__name__).warning("Failed to update redteam_campaign_results on proxy leak: %s", exc)

        return {"blocked": False, "lakera_input": input_screen, "lakera_output": output_screen, "reply": reply, "event": event, "model_leaked_raw": model_leaked_raw, "canary_leaked": True}

    event = _log_event("clean", "Allowed")
    AuditLogger().log_action(
        action="Real Guardrail Proxy — Allowed",
        username=user["u"], status="Allowed", target="meridian-support-agent",
        details="Real prompt passed both real input and output Lakera screens; real reply returned to caller.",
    )
    return {"blocked": False, "lakera_input": input_screen, "lakera_output": output_screen, "reply": reply, "event": event, "model_leaked_raw": model_leaked_raw, "canary_leaked": False}


def _categorize_scan_finding(row: Dict[str, Any]) -> str:
    """Honest, derived-not-invented label for a real garak/pyrit finding row:
    did the real target agent's own output guardrail (2b89c37) intervene, or
    did the model refuse the jailbreak on its own before the guardrail was
    ever needed? Read straight off the real response text already returned
    by the runner — no new data, just naming what already happened."""
    text = str(row.get("response_snippet") or "")
    if "RESPONSE BLOCKED" in text:
        return "guardrail_blocked"
    if str(row.get("probe") or "") == "meridian_custom.CredentialLeak":
        # This one real garak probe checks the target's raw, pre-guardrail
        # model_leaked_raw_text field directly (see garak-runner/main.py's
        # RAW_LEAK_PROBE) — response_snippet here is a real descriptive
        # sentence, not real reply text, so it never contains "RESPONSE
        # BLOCKED" even on a real jailbreak the guardrail would have caught
        # on the normal /chat path. canary_leaked==True for this probe
        # specifically means "the model was genuinely jailbroken raw", which
        # the real guardrail always catches on that path — label it that
        # way rather than as a caller-facing leak.
        return "guardrail_blocked" if row.get("canary_leaked") else "model_self_refused"
    if row.get("canary_leaked"):
        return "leaked"
    return "model_self_refused"


class LiveScanRequest(BaseModel):
    tools: List[str]  # subset of ["garak", "pyrit"]


@app.post("/api/detect/live-scan")
def detect_live_scan(body: LiveScanRequest, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Real, on-demand Garak/PyRIT scan(s) — the same real
    MCPClient.trigger_runner_scan already used by the Detect stage's
    "+ External Source" data-source path, just triggered directly and made
    prominent instead of buried behind a generic radio + Execute combo.
    Genuinely slow (each real tool runs dozens of real LLM calls, ~150-190s)
    — the frontend shows a real elapsed-time state while this blocks, not a
    fake instant result. Every real finding gets a real, derived category
    (guardrail_blocked / model_self_refused / leaked) so the guardrail's
    actual role in the outcome is visible, not just a bare pass/fail."""
    tools = [t for t in body.tools if t in ("garak", "pyrit")]
    if not tools:
        raise HTTPException(status_code=400, detail="tools must include at least one of: garak, pyrit")

    target_agent_url = os.getenv("TARGET_AGENT_URL", "").rstrip("/")
    scan_target = f"{target_agent_url}/chat" if target_agent_url else "demo-agent-fleet"

    results: Dict[str, Any] = {}
    for tool_name in tools:
        status = state.mcp_client.get_connection_status(tool_name)
        if not status["live"]:
            results[tool_name] = {"live": False, "rows": [], "summary": None, "error": f"{tool_name} is not configured (missing runner URL)."}
            continue

        scan_result = state.mcp_client.trigger_runner_scan(tool_name, target=scan_target, target_label="Meridian Financial Support Agent")
        findings = [f for f in (scan_result.get("findings") or []) if "probe" in f]
        errors = scan_result.get("errors")

        rows = []
        for f in findings:
            row = dict(f)
            row["outcome"] = _categorize_scan_finding(row)
            rows.append(row)

        if findings:
            state.datasets[f"{tool_name}_live_scan"] = pd.DataFrame(findings)

        summary = {
            "total": len(rows),
            "guardrail_blocked": sum(1 for r in rows if r["outcome"] == "guardrail_blocked"),
            "model_self_refused": sum(1 for r in rows if r["outcome"] == "model_self_refused"),
            "leaked": sum(1 for r in rows if r["outcome"] == "leaked"),
        }
        results[tool_name] = {"live": True, "rows": rows, "summary": summary, "errors": errors}

        leaked_note = f", {summary['leaked']} leaked" if summary["leaked"] else ""
        AuditLogger().log_action(
            action=f"Live {tool_name.title()} Scan — Detect Panel",
            username=user["u"],
            status="Success" if rows else "No findings",
            target="meridian-support-agent",
            details=(
                f"Real {tool_name} scan: {summary['total']} real attempts — "
                f"{summary['guardrail_blocked']} guardrail-blocked, {summary['model_self_refused']} model-self-refused{leaked_note}."
            ),
        )

    state.recompute_kpis()
    return {"results": results}


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


def _verify_slack_signature(raw_body: bytes, timestamp: str, signature: str) -> bool:
    """Real HMAC-SHA256 verification per Slack's own spec — confirms a
    callback genuinely came from Slack (not a forged POST to our endpoint)
    and isn't a replayed old request. https://api.slack.com/authentication/verifying-requests-from-slack"""
    signing_secret = os.getenv("SLACK_SIGNING_SECRET", "")
    if not signing_secret:
        return False
    try:
        if abs(time.time() - int(timestamp)) > 60 * 5:
            return False  # older than 5 minutes — reject as a possible replay
    except (TypeError, ValueError):
        return False
    basestring = f"v0:{timestamp}:{raw_body.decode('utf-8')}".encode("utf-8")
    computed = "v0=" + hmac.new(signing_secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature or "")


@app.post("/api/slack/interactions")
async def slack_interactions(request: Request) -> Dict[str, Any]:
    """Real callback target for the Approve/Reject buttons posted by
    MCPClient.slack_post_approval_request(). Slack calls this directly —
    see the Slack App's Interactivity Request URL setup.

    On approve, looks up the pending real action registered by
    request_approval() above (keyed by action_id) and actually executes it —
    e.g. a real target_agent_set_disabled() call — not just records the
    click. On reject, or if the action_id isn't pending (already handled, or
    the backend restarted since it was requested), no real action fires;
    the click is still recorded either way."""
    raw_body = await request.body()
    if not _verify_slack_signature(
        raw_body,
        request.headers.get("x-slack-request-timestamp", ""),
        request.headers.get("x-slack-signature", ""),
    ):
        raise HTTPException(status_code=401, detail="Invalid Slack request signature.")

    form = dict(pair.split("=", 1) for pair in raw_body.decode("utf-8").split("&") if "=" in pair)
    from urllib.parse import unquote_plus
    payload = json.loads(unquote_plus(form.get("payload", "{}")))

    action = (payload.get("actions") or [{}])[0]
    decision = action.get("action_id", "unknown")  # "approve" or "reject"
    action_id = action.get("value", "")
    approver = payload.get("user", {}).get("username", "unknown")
    response_url = payload.get("response_url")

    AuditLogger().log_action(
        action="Slack Approval Decision — Live",
        username=approver,
        status="Approved" if decision == "approve" else "Rejected",
        target=action_id,
        details=f"Real Slack interaction: {approver} clicked {decision} for action_id={action_id}.",
    )

    pending = state.pending_actions.pop(action_id, None)
    execution_result: Optional[Dict[str, Any]] = None
    if pending is None:
        status_note = "No pending real action found for this action_id (already handled, or the backend restarted since it was requested)."
    elif decision != "approve":
        status_note = f"Rejected by @{approver} — real action '{pending['action_type']}' was NOT executed."
    else:
        executor = _REAL_ACTION_EXECUTORS.get(pending["action_type"])
        if executor is None:
            status_note = f"No executor wired for action_type '{pending['action_type']}'."
        else:
            try:
                execution_result = executor()
                status_note = f"Real action '{pending['action_type']}' executed successfully."
                AuditLogger().log_action(
                    action=f"Real Action Executed (Slack-approved): {pending['action_type']}",
                    username=approver,
                    status="Success",
                    target=action_id,
                    details=f"{pending['summary']} — approved by @{approver} in Slack, real action executed.",
                )
            except MCPClient.LiveConnectorError as exc:
                status_note = f"Real action '{pending['action_type']}' FAILED: {exc}"
                AuditLogger().log_action(
                    action=f"Real Action FAILED: {pending['action_type']}",
                    username=approver,
                    status="Failed",
                    target=action_id,
                    details=str(exc),
                )

    # Acknowledge back to the same Slack message for real, immediate feedback
    if response_url:
        label = "✅ Approved" if decision == "approve" else "❌ Rejected"
        try:
            httpx.post(response_url, json={
                "replace_original": True,
                "text": f"{label} by @{approver} — {status_note}",
            }, timeout=10.0)
        except httpx.HTTPError:
            pass  # best-effort UI update in Slack; the real decision is already audit-logged above

    state.resolved_actions[action_id] = {
        "decision": decision,
        "approver": approver,
        "status_note": status_note,
        "execution_result": execution_result,
    }

    return {"ok": True, "decision": decision, "action_id": action_id, "approver": approver, "status_note": status_note, "execution_result": execution_result}


@app.get("/api/approval-status/{action_id}")
def approval_status(action_id: str, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Polled by SlackApprovalCard once a real approval request is posted —
    tells the app's own UI what a real human actually clicked in Slack,
    instead of leaving the card saying 'waiting' forever after it's already
    been resolved. Returns resolved: false while state.pending_actions still
    holds the action_id (or it's unknown — e.g. a stale action_id from before
    a backend restart)."""
    resolved = state.resolved_actions.get(action_id)
    if resolved is None:
        return {"resolved": False}
    return {"resolved": True, **resolved}


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
    """Every dataset here is real (LiveDataEngine, Milestone 3) or honestly
    empty pending a real fetcher/action — never synthetic. `is_live` just
    reflects whether real rows currently exist for this dataset, so the
    frontend can present this page as an evidence store: populated =
    real evidence on record, empty = no real evidence yet, not "missing
    data" or a placeholder."""
    result = {}
    for uc, names in PHASE_DATASETS.items():
        result[uc] = []
        for name in names:
            df = state.datasets.get(name)
            row_count = 0 if df is None else len(df)
            result[uc].append({
                "name": name,
                "row_count": row_count,
                "column_count": 0 if df is None else len(df.columns),
                "is_live": row_count > 0,
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
    github_target_repo: Optional[str] = None  # "owner/name" — retargets the whole live pipeline
    github_token: Optional[str] = None        # fine-grained PAT scoped to that repo


def _mask(value: str) -> str:
    if not value:
        return ""
    return value[:4] + "…" + value[-2:] if len(value) > 8 else "•" * len(value)


@app.get("/api/settings")
def get_settings(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    # Real reachability, not just "is a URL configured" — a cheap real
    # GET /healthz against the actual target agent process (same call
    # AppState._ensure_target_agent_enabled() makes at startup). Every other
    # live-systems chip on the Dashboard reflects a real connection check;
    # this one was the one exception, silently reporting "connected" the
    # instant a URL string existed even if the process behind it was dead.
    target_agent_reachable = False
    target_agent_disabled = False
    if os.getenv("TARGET_AGENT_URL"):
        try:
            health = state.mcp_client.target_agent_healthz()
            target_agent_reachable = True
            target_agent_disabled = bool(health.get("disabled"))
        except Exception:
            target_agent_reachable = False

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
        # Real live target this whole pipeline currently analyses — editable
        # from the Settings page (Reload live data). Only works for repos
        # the configured GITHUB_TOKEN can actually access; a different real
        # repo needs a matching token too. target_agent_url stays read-only
        # here since it isn't part of this retargeting flow.
        "github_target_repo": os.getenv("GITHUB_TARGET_REPO", ""),
        "github_token_set": bool(os.getenv("GITHUB_TOKEN")),
        "target_agent_url": os.getenv("TARGET_AGENT_URL", ""),
        "target_agent_reachable": target_agent_reachable,
        "target_agent_disabled": target_agent_disabled,
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

    retarget = False
    if body.github_target_repo and body.github_target_repo != os.getenv("GITHUB_TARGET_REPO", ""):
        updates["GITHUB_TARGET_REPO"] = body.github_target_repo
        retarget = True
    if body.github_token:
        updates["GITHUB_TOKEN"] = body.github_token
        retarget = True

    _apply_settings(updates)
    state.reload_llm_router()
    if retarget:
        state.reload_datasets()
    return {"saved": True, "reloaded": retarget, "fetch_errors": state.fetch_errors if retarget else None}


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
