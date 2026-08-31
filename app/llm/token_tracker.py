"""
TokenUsageTracker — Persistent LLM usage tracking with cost analytics.

Every LLM call is recorded in a SQLite database with:
- Session, use-case, and lifecycle-stage context
- Model name and provider
- Input/output token counts
- Computed cost (from ``token_pricing.yaml``)
- Call duration

Provides aggregation helpers for the Token Usage dashboard and
the executive cost-optimisation views.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

# Resolve project root so relative paths work regardless of cwd
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB_PATH = str(_PROJECT_ROOT / "data" / "token_usage.db")
_PRICING_PATH = str(_PROJECT_ROOT / "token_pricing.yaml")

# Thread-local storage for SQLite connections (one per thread)
_thread_local = threading.local()


def _load_pricing(path: str = _PRICING_PATH) -> Dict[str, Dict[str, Any]]:
    """Load model pricing from YAML.  Returns ``{}`` on failure."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        return raw.get("models", {})
    except FileNotFoundError:
        logger.warning("Pricing file not found at %s — costs will be zero.", path)
        return {}
    except Exception:
        logger.exception("Failed to load pricing YAML.")
        return {}


class TokenUsageTracker:
    """Persistent token-usage and cost tracker backed by SQLite.

    Thread-safe: each thread gets its own SQLite connection.

    Usage::

        tracker = TokenUsageTracker()
        tracker.track(
            session_id="abc-123",
            use_case="ctem",
            stage="prioritisation",
            model="gpt-4o-mini",
            input_tokens=1200,
            output_tokens=500,
            duration_ms=1340,
        )
        summary = tracker.get_session_summary("abc-123")
    """

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self.db_path: str = db_path
        self._pricing: Dict[str, Dict[str, Any]] = _load_pricing()

        # Ensure the directory exists
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)

        # Create table on first init
        self._init_db()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """Return a thread-local SQLite connection."""
        conn = getattr(_thread_local, "conn", None)
        db_path = getattr(_thread_local, "db_path", None)
        if conn is None or db_path != self.db_path:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            _thread_local.conn = conn
            _thread_local.db_path = self.db_path
        return conn

    def _init_db(self) -> None:
        """Create the ``token_events`` table if it does not exist."""
        ddl = """
        CREATE TABLE IF NOT EXISTS token_events (
            id          TEXT PRIMARY KEY,
            session_id  TEXT NOT NULL,
            timestamp   TEXT NOT NULL,
            use_case    TEXT NOT NULL DEFAULT 'general',
            stage       TEXT NOT NULL DEFAULT 'analysis',
            model       TEXT NOT NULL,
            provider    TEXT NOT NULL DEFAULT 'openai',
            input_tokens  INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd    REAL NOT NULL DEFAULT 0.0,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            context     TEXT NOT NULL DEFAULT 'analysis'
        );
        """
        conn = self._get_conn()
        conn.execute(ddl)
        # Indices for common queries
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_te_session "
            "ON token_events(session_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_te_timestamp "
            "ON token_events(timestamp)"
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Cost computation
    # ------------------------------------------------------------------

    def _compute_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Compute USD cost for a single call using pricing YAML."""
        pricing = self._pricing.get(model)
        if pricing is None:
            # Try normalised key (e.g. "gpt-4o-mini" from "gpt-4o-mini")
            for key, val in self._pricing.items():
                if val.get("display_name", "").lower() == model.lower():
                    pricing = val
                    break

        if pricing is None:
            return 0.0

        input_cost = (input_tokens / 1_000_000) * pricing.get(
            "input_cost_per_1m", 0.0
        )
        output_cost = (output_tokens / 1_000_000) * pricing.get(
            "output_cost_per_1m", 0.0
        )
        return round(input_cost + output_cost, 8)

    def _resolve_provider(self, model: str) -> str:
        """Look up the provider for a model name from the pricing config."""
        pricing = self._pricing.get(model)
        if pricing:
            return pricing.get("provider", "unknown")
        for val in self._pricing.values():
            if val.get("display_name", "").lower() == model.lower():
                return val.get("provider", "unknown")
        return "unknown"

    # ------------------------------------------------------------------
    # Tracking
    # ------------------------------------------------------------------

    def track(
        self,
        session_id: str,
        use_case: str,
        stage: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int,
        context: str = "analysis",
    ) -> str:
        """Record a single LLM call event.

        Args:
            session_id: Streamlit session identifier.
            use_case: E.g. ``ctem``, ``hunt``, ``pentest``, ``detection``.
            stage: Lifecycle stage (``scoping``, ``discovery``, etc.).
            model: Model name as known to the pricing YAML.
            input_tokens: Prompt token count.
            output_tokens: Completion token count.
            duration_ms: Wall-clock duration in milliseconds.
            context: Free-form label (``analysis``, ``structured_output``, etc.).

        Returns:
            The UUID of the inserted event row.
        """
        event_id = str(uuid.uuid4())
        cost = self._compute_cost(model, input_tokens, output_tokens)
        provider = self._resolve_provider(model)
        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO token_events
                (id, session_id, timestamp, use_case, stage, model, provider,
                 input_tokens, output_tokens, cost_usd, duration_ms, context)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                session_id,
                now,
                use_case,
                stage,
                model,
                provider,
                input_tokens,
                output_tokens,
                cost,
                duration_ms,
                context,
            ),
        )
        conn.commit()

        logger.debug(
            "Tracked: model=%s tokens=%d+%d cost=$%.6f dur=%dms",
            model,
            input_tokens,
            output_tokens,
            cost,
            duration_ms,
        )
        return event_id

    # ------------------------------------------------------------------
    # Aggregation queries
    # ------------------------------------------------------------------

    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """Aggregate totals for a single session.

        Returns:
            Dict with ``total_input_tokens``, ``total_output_tokens``,
            ``total_tokens``, ``total_cost_usd``, ``call_count``,
            ``avg_duration_ms``.
        """
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(input_tokens), 0),
                COALESCE(SUM(output_tokens), 0),
                COALESCE(SUM(cost_usd), 0.0),
                COUNT(*),
                COALESCE(AVG(duration_ms), 0)
            FROM token_events
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()

        return {
            "total_input_tokens": row[0],
            "total_output_tokens": row[1],
            "total_tokens": row[0] + row[1],
            "total_cost_usd": round(row[2], 6),
            "call_count": row[3],
            "avg_duration_ms": int(row[4]),
        }

    def get_historical(self, days: int = 30) -> pd.DataFrame:
        """Return all token events from the last *days* days.

        Returns:
            A pandas DataFrame of raw event rows.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).isoformat()
        conn = self._get_conn()
        df = pd.read_sql_query(
            "SELECT * FROM token_events WHERE timestamp >= ? ORDER BY timestamp",
            conn,
            params=(cutoff,),
        )
        return df

    def get_cost_by_model(self, session_id: str) -> Dict[str, float]:
        """Return cost breakdown by model for a session.

        Returns:
            Dict mapping model name → total cost USD.
        """
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT model, COALESCE(SUM(cost_usd), 0.0)
            FROM token_events
            WHERE session_id = ?
            GROUP BY model
            """,
            (session_id,),
        ).fetchall()
        return {row[0]: round(row[1], 6) for row in rows}

    def get_cost_by_usecase(self, session_id: str) -> Dict[str, float]:
        """Return cost breakdown by use-case for a session.

        Returns:
            Dict mapping use-case label → total cost USD.
        """
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT use_case, COALESCE(SUM(cost_usd), 0.0)
            FROM token_events
            WHERE session_id = ?
            GROUP BY use_case
            """,
            (session_id,),
        ).fetchall()
        return {row[0]: round(row[1], 6) for row in rows}

    def get_cost_by_stage(self, session_id: str) -> Dict[str, float]:
        """Return cost breakdown by lifecycle stage for a session."""
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT stage, COALESCE(SUM(cost_usd), 0.0)
            FROM token_events
            WHERE session_id = ?
            GROUP BY stage
            """,
            (session_id,),
        ).fetchall()
        return {row[0]: round(row[1], 6) for row in rows}

    def get_total_cost(self) -> float:
        """Return total cost across all sessions (lifetime)."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) FROM token_events"
        ).fetchone()
        return round(row[0], 6)
