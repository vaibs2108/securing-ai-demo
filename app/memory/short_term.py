"""
AI Capability Demo — Short-Term Memory System
SQLite-backed 48-hour conversation + session context store.
AGENTS.md Section 7.
"""

from __future__ import annotations

import os
import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class ShortTermMemory:
    """SQLite-backed 48-hour memory store.
    Auto-expires entries older than TTL_HOURS.
    Works identically on all platforms — SQLite is Python stdlib.
    """
    DB_PATH = "data/memory.db"
    TTL_HOURS = 48

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path:
            self.DB_PATH = db_path
        
        # Ensure data folder exists
        os.makedirs(os.path.dirname(self.DB_PATH), exist_ok=True)
        
        self._init_db()
        self._expire_old_entries()

    def _init_db(self) -> None:
        """Create the database table and indices if they do not exist."""
        conn = sqlite3.connect(self.DB_PATH)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id   TEXT NOT NULL,
                    user         TEXT NOT NULL,
                    entry_type   TEXT NOT NULL,
                    use_case     TEXT,
                    stage        TEXT,
                    key          TEXT NOT NULL,
                    value        TEXT NOT NULL,     -- JSON serialised
                    created_at   TEXT NOT NULL,
                    expires_at   TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_user ON memory_entries(user)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_key  ON memory_entries(key)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_exp  ON memory_entries(expires_at)")
            conn.commit()
        except sqlite3.Error as e:
            logger.error("Failed to initialize memory database: %s", e)
            conn.rollback()
        finally:
            conn.close()

    def store(
        self,
        user: str,
        entry_type: str,
        key: str,
        value: Any,
        use_case: Optional[str] = None,
        stage: Optional[str] = None,
        session_id: Optional[str] = None,
        ttl_hours: int = 48
    ) -> bool:
        """Store a memory entry with TTL."""
        # Clean up old entries first to prevent bloated database
        self._expire_old_entries()
        
        now = datetime.utcnow()
        created_at = now.isoformat()
        expires_at = (now + timedelta(hours=ttl_hours)).isoformat()
        session_str = session_id or "default_session"
        
        try:
            val_json = json.dumps(value)
        except (TypeError, ValueError) as e:
            logger.error("Failed to serialize value to JSON for key '%s': %s", key, e)
            return False

        conn = sqlite3.connect(self.DB_PATH)
        try:
            conn.execute(
                """
                INSERT INTO memory_entries (session_id, user, entry_type, use_case, stage, key, value, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_str, user, entry_type, use_case, stage, key, val_json, created_at, expires_at)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error("Failed to store memory key '%s': %s", key, e)
            conn.rollback()
            return False
        finally:
            conn.close()

    def recall(
        self,
        user: str,
        entry_type: Optional[str] = None,
        key: Optional[str] = None,
        use_case: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve non-expired memory entries for a user."""
        self._expire_old_entries()
        
        now_str = datetime.utcnow().isoformat()
        query = "SELECT session_id, user, entry_type, use_case, stage, key, value, created_at, expires_at FROM memory_entries WHERE user = ? AND expires_at > ?"
        params = [user, now_str]
        
        if entry_type:
            query += " AND entry_type = ?"
            params.append(entry_type)
        if key:
            query += " AND key = ?"
            params.append(key)
        if use_case:
            query += " AND use_case = ?"
            params.append(use_case)
            
        query += " ORDER BY created_at DESC"
        
        results = []
        conn = sqlite3.connect(self.DB_PATH)
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            for row in cursor.fetchall():
                try:
                    val_data = json.loads(row[6])
                except json.JSONDecodeError:
                    val_data = row[6]
                    
                results.append({
                    "session_id": row[0],
                    "user": row[1],
                    "entry_type": row[2],
                    "use_case": row[3],
                    "stage": row[4],
                    "key": row[5],
                    "value": val_data,
                    "created_at": row[7],
                    "expires_at": row[8],
                })
        except sqlite3.Error as e:
            logger.error("Failed to recall memory for user '%s': %s", user, e)
        finally:
            conn.close()
            
        return results

    def recall_recent_analyses(self, user: str, use_case: str) -> List[Dict[str, Any]]:
        """Get all stage analysis results from last 48h for a usecase."""
        entry_type = "stage_result"
        uc_filter = None if use_case == "all" else use_case
        return self.recall(user=user, entry_type=entry_type, use_case=uc_filter)

    def recall_conversation(self, user: str, last_n: int = 20) -> List[Dict[str, Any]]:
        """Get last N copilot messages for conversation continuity."""
        self._expire_old_entries()
        
        now_str = datetime.utcnow().isoformat()
        query = (
            "SELECT value, created_at FROM memory_entries "
            "WHERE user = ? AND entry_type = 'copilot_message' AND expires_at > ? "
            "ORDER BY created_at ASC"
        )
        params = [user, now_str]
        
        results = []
        conn = sqlite3.connect(self.DB_PATH)
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # Fetch last N records
            if len(rows) > last_n:
                rows = rows[-last_n:]
                
            for row in rows:
                try:
                    msg_data = json.loads(row[0])
                except json.JSONDecodeError:
                    msg_data = {"role": "unknown", "content": str(row[0])}
                results.append(msg_data)
        except sqlite3.Error as e:
            logger.error("Failed to recall conversation for user '%s': %s", user, e)
        finally:
            conn.close()
            
        return results

    def _expire_old_entries(self) -> None:
        """Delete rows past expires_at. Called on init and write events."""
        now_str = datetime.utcnow().isoformat()
        conn = sqlite3.connect(self.DB_PATH)
        try:
            conn.execute("DELETE FROM memory_entries WHERE expires_at < ?", (now_str,))
            conn.commit()
        except sqlite3.Error as e:
            logger.error("Failed to purge expired memory entries: %s", e)
            conn.rollback()
        finally:
            conn.close()
