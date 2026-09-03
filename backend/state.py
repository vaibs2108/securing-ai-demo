"""
Securing AI — FastAPI process state.
Builds the synthetic datasets, KPI engine, and shared service clients once at
startup and reuses them across every request. Single-user demo process, so a
module-level singleton is sufficient (no per-request DB round trip needed).
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

from app.data.live_engine import LiveDataEngine
from app.kpi.engine import KPIEngine
from app.runtime.agent_manager import AgentManager
from app.mcp.registry import MCPToolRegistry
from app.mcp.client import MCPClient
from app.memory.short_term import ShortTermMemory
from app.llm.token_tracker import TokenUsageTracker
from app.observability.audit_logger import AuditLogger
from backend.rag_service import RAGService


class AppState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.datasets: Dict[str, pd.DataFrame] = {}
        self.fetch_errors: Dict[str, str] = {}
        self.kpi_engine: Optional[KPIEngine] = None
        self.llm_router: Any = None
        self.agent_manager: Optional[AgentManager] = None
        self.mcp_registry = MCPToolRegistry()
        self.mcp_client = MCPClient(self.mcp_registry)
        self.memory = ShortTermMemory()
        self.token_tracker = TokenUsageTracker()
        self.rag = RAGService()

        # Per-phase workspace state (mirrors what Streamlit kept in session_state)
        self.active_stage: Dict[str, int] = {
            "identify": 0, "protect": 0, "detect": 0, "respond": 0, "recover": 0, "govern": 0,
        }
        self.completed_stages: Dict[str, List[int]] = {
            "identify": [], "protect": [], "detect": [], "respond": [], "recover": [], "govern": [],
        }
        self.stage_outputs: Dict[str, Dict[str, Any]] = {
            "identify": {}, "protect": {}, "detect": {}, "respond": {}, "recover": {}, "govern": {},
        }
        self.hitl_approved: Dict[str, Dict[str, bool]] = {
            "identify": {}, "protect": {}, "detect": {}, "respond": {}, "recover": {}, "govern": {},
        }
        self.workflow_state: Dict[str, Dict[str, Any]] = {}  # f"{uc}_{stage}" -> ticket workflow

        # Real Respond/Recover actions awaiting a real Slack approval —
        # in-memory only, by design: a real backend restart clears pending
        # approvals rather than silently executing a stale action against a
        # process that may have moved on. Keyed by the same action_id passed
        # to MCPClient.slack_post_approval_request; see backend/main.py's
        # request-approval / slack_interactions routes (Milestone 5).
        self.pending_actions: Dict[str, Dict[str, Any]] = {}
        # Resolved Slack decisions, kept around (in-memory, same lifetime as
        # pending_actions) so PhaseWorkspace's SlackApprovalCard can poll for
        # the real outcome instead of sitting on "waiting" forever after a
        # human has actually clicked Approve/Reject in Slack.
        self.resolved_actions: Dict[str, Dict[str, Any]] = {}

    def init(self) -> None:
        self._ensure_target_agent_enabled()

        # Real live data (app/data/live_engine.py) from the real
        # meridian-support-agent GitHub repo + deployed agent, via
        # self.mcp_client — replaces the old SyntheticDataEngine entirely.
        # Built incrementally: Identify's 3 datasets are real now, the
        # remaining 13 are empty (correct schema, zero rows) until their
        # real fetchers land — never fabricated placeholder rows. See
        # app/data/live_engine.py's module docstring and AGENTS.md's
        # live-demo architecture notes.
        logger.info("Fetching real live datasets from meridian-support-agent...")
        engine = LiveDataEngine(mcp_client=self.mcp_client)
        self.datasets = engine.generate_all()
        self.fetch_errors = engine.fetch_errors
        self.kpi_engine = KPIEngine(self.datasets)
        self._init_llm_router()
        self.rag.build_dataset_index_async(self.datasets)

    def _ensure_target_agent_enabled(self) -> None:
        """Self-heals a target agent left disabled by a prior session's real
        Respond containment test (target_agent_set_disabled(True)) — so
        every fresh backend start begins from a known-good state instead of
        silently demoing against a suspended agent. Real GET /healthz check
        (no LLM call), then a real POST /admin/enable only if actually
        needed. Best-effort: an unreachable/misconfigured agent shouldn't
        block the rest of startup — Identify's real fetch will surface that
        separately."""
        try:
            health = self.mcp_client.target_agent_healthz()
            if health.get("disabled"):
                logger.warning("Target agent was left disabled from a prior session — restoring it now.")
                self.mcp_client.target_agent_set_disabled(False)
                AuditLogger().log_action(
                    action="Target Agent Auto-Restored at Startup",
                    username="system",
                    status="Success",
                    target=os.getenv("TARGET_AGENT_URL", ""),
                    details="Found disabled at backend startup (left over from a prior Respond test) — real /admin/enable call issued so the demo starts from a clean state.",
                )
            else:
                logger.info("Target agent healthz check: already enabled.")
        except Exception:
            logger.exception("Target agent startup health check failed — leaving as-is; Identify's real fetch will surface any real connectivity issue.")

    def reload_datasets(self) -> None:
        """Re-fetch real datasets against whatever GITHUB_TARGET_REPO /
        GITHUB_TOKEN / TARGET_AGENT_URL are now in os.environ — called after
        a Settings save changes the live target, so the retarget takes
        effect immediately instead of waiting for the next process restart."""
        with self._lock:
            logger.info("Reloading real live datasets against updated target...")
            engine = LiveDataEngine(mcp_client=self.mcp_client)
            self.datasets = engine.generate_all()
            self.fetch_errors = engine.fetch_errors
            self.kpi_engine = KPIEngine(self.datasets)
        self.rag.build_dataset_index_async(self.datasets)

    def _init_llm_router(self) -> None:
        try:
            from app.llm.router import LLMRouter
            self.llm_router = LLMRouter()
        except Exception:
            self.llm_router = None
        self.agent_manager = AgentManager(self.llm_router, None, self.token_tracker)

    def reload_llm_router(self) -> None:
        with self._lock:
            self._init_llm_router()

    def recompute_kpis(self) -> KPIEngine:
        with self._lock:
            self.kpi_engine = KPIEngine(self.datasets)
        return self.kpi_engine


state = AppState()
