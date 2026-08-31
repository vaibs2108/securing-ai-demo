"""
Securing AI — FastAPI process state.
Builds the synthetic datasets, KPI engine, and shared service clients once at
startup and reuses them across every request. Single-user demo process, so a
module-level singleton is sufficient (no per-request DB round trip needed).
"""

from __future__ import annotations

import logging
import random
import threading
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

from app.data.generator import SyntheticDataEngine
from app.kpi.engine import KPIEngine
from app.runtime.agent_manager import AgentManager
from app.mcp.registry import MCPToolRegistry
from app.mcp.client import MCPClient
from app.memory.short_term import ShortTermMemory
from app.llm.token_tracker import TokenUsageTracker
from backend.rag_service import RAGService


class AppState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.datasets: Dict[str, pd.DataFrame] = {}
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
            "identify": 0, "protect": 0, "detect": 0, "respond": 0, "recover": 0,
        }
        self.completed_stages: Dict[str, List[int]] = {
            "identify": [], "protect": [], "detect": [], "respond": [], "recover": [],
        }
        self.stage_outputs: Dict[str, Dict[str, Any]] = {
            "identify": {}, "protect": {}, "detect": {}, "respond": {}, "recover": {},
        }
        self.hitl_approved: Dict[str, Dict[str, bool]] = {
            "identify": {}, "protect": {}, "detect": {}, "respond": {}, "recover": {},
        }
        self.workflow_state: Dict[str, Dict[str, Any]] = {}  # f"{uc}_{stage}" -> ticket workflow

    def init(self) -> None:
        # A fresh random seed every process start means the 16 datasets (and
        # every metric computed from them) genuinely differ per restart,
        # instead of the previous fixed seed=42. Logged so a specific run's
        # data can be reproduced later if needed. Tradeoff: the RAG/Copilot
        # embedding cache (backend/rag_service.py) can no longer hit across
        # restarts, since it was keyed on the old deterministic content —
        # every restart now pays the full re-embedding cost again.
        seed = random.randint(1, 2**31 - 1)
        logger.info("Generating synthetic datasets with seed=%d", seed)
        engine = SyntheticDataEngine(seed=seed)
        self.datasets = engine.generate_all()
        self.kpi_engine = KPIEngine(self.datasets)
        self._init_llm_router()
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
