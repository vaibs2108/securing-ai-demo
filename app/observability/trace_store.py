"""
Securing AI — Process-wide observability store.
Holds agent execution traces in plain module-level state (readable from any
runtime — Streamlit session or FastAPI request — without depending on
st.session_state), and persists hallucination reports to SQLite
(data/hallucination_reports.db) so the Observability page's evidence that the
hallucination check works survives a backend restart / HF Spaces sleep-wake
cycle instead of resetting to empty every time.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_MAX_TRACES = 500

_TRACES: List[Dict[str, Any]] = []

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_HALLUCINATION_DB_PATH = str(_PROJECT_ROOT / "data" / "hallucination_reports.db")


def record_trace(trace: Dict[str, Any]) -> None:
    """Append an execution trace, capping the in-memory log at _MAX_TRACES."""
    _TRACES.append(trace)
    if len(_TRACES) > _MAX_TRACES:
        del _TRACES[: len(_TRACES) - _MAX_TRACES]


def get_traces(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if limit is None:
        return list(_TRACES)
    return list(_TRACES[-limit:])


def _hallucination_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_HALLUCINATION_DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(_HALLUCINATION_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hallucination_reports (
            key         TEXT PRIMARY KEY,
            report_json TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
        """
    )
    return conn


def record_hallucination_report(key: str, report: Any) -> None:
    """Persist a hallucination report (a HallucinationReport pydantic model,
    or any object/dict with an equivalent shape) keyed by `{use_case}_{stage}`."""
    payload = report.model_dump() if hasattr(report, "model_dump") else report
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn = _hallucination_db()
    try:
        conn.execute(
            """
            INSERT INTO hallucination_reports (key, report_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET report_json = excluded.report_json, updated_at = excluded.updated_at
            """,
            (key, json.dumps(payload), now),
        )
        conn.commit()
    finally:
        conn.close()


def get_hallucination_reports() -> Dict[str, Any]:
    """Return every stored report as {key: report_dict}, newest-updated first."""
    conn = _hallucination_db()
    try:
        rows = conn.execute(
            "SELECT key, report_json FROM hallucination_reports ORDER BY updated_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return {key: json.loads(report_json) for key, report_json in rows}


def get_hallucination_report(key: str) -> Optional[Any]:
    conn = _hallucination_db()
    try:
        row = conn.execute(
            "SELECT report_json FROM hallucination_reports WHERE key = ?", (key,)
        ).fetchone()
    finally:
        conn.close()
    return json.loads(row[0]) if row else None
