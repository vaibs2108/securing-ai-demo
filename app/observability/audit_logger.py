"""
AI Capability Demo — Audit Logger
Structured JSON logging (structlog) + sqlite3 persistent audit trail for HITL and remediation events.
AGENTS.md Section 2 & 4
"""

import os
import sqlite3
import time
import uuid
import structlog
from pathlib import Path
from typing import Any, Dict

# Resolve project root so database path remains stable
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_AUDIT_DB = str(_PROJECT_ROOT / "data" / "audit_log.db")

# Setup structlog configuration
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

struct_logger = structlog.get_logger()

class AuditLogger:
    """Manages structured JSON logging and writes persistent security event logs to SQLite."""
    
    def __init__(self, db_path: str = _DEFAULT_AUDIT_DB) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create the audit_logs table if it does not exist."""
        conn = sqlite3.connect(self.db_path)
        ddl = """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id          TEXT PRIMARY KEY,
            timestamp   TEXT NOT NULL,
            action      TEXT NOT NULL,
            username    TEXT NOT NULL,
            status      TEXT NOT NULL,
            target      TEXT NOT NULL,
            details     TEXT NOT NULL
        );
        """
        conn.execute(ddl)
        conn.commit()
        conn.close()

    def log_action(self, action: str, username: str, status: str, target: str, details: str) -> str:
        """Log a structured security action and write to DB."""
        event_id = str(uuid.uuid4())
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Write to JSON stdout via structlog
        struct_logger.info(
            "security_audit_event",
            event_id=event_id,
            timestamp=now,
            action=action,
            username=username,
            status=status,
            target=target,
            details=details
        )

        # Write to persistent SQLite db
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """
                INSERT INTO audit_logs (id, timestamp, action, username, status, target, details)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, now, action, username, status, target, details)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            struct_logger.error("failed_to_write_audit_db", error=str(e))

        return event_id

    def get_logs(self, limit: int = 100) -> list:
        """Retrieve latest audit logs from the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT timestamp, action, username, status, target, details FROM audit_logs ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            conn.close()
            return [
                {
                    "timestamp": r[0],
                    "action": r[1],
                    "username": r[2],
                    "status": r[3],
                    "target": r[4],
                    "details": r[5]
                }
                for r in rows
            ]
        except Exception:
            return []
