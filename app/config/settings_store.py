"""
Securing AI — persistent, UI-owned settings store.

Every previous version of the Settings page persisted changes by writing
lines into a .env file on disk. That works fine on a laptop, but breaks the
moment the app is actually deployed (HF Spaces, Docker, any real host): the
user has no shell, no file browser, nothing that lets them see or edit that
file — the only settings they can practically change are the ones they typed
into the UI, and those need to land somewhere the UI itself owns.

SettingsStore is a small SQLite table (data/app_settings.db, alongside the
app's other local data) that IS that "somewhere". It requires nothing the
user can't already reach through the browser. On every write it also mirrors
the value into os.environ for the current process, and on startup
apply_to_environment() loads everything already stored — so every existing
os.getenv(...) call in the codebase (ours, and any third-party SDK's, e.g.
LangSmith's tracing config) transparently sees UI-configured values without
needing to know this store exists. A .env file / real platform secret still
works as the initial bootstrap value; once something is saved through the
UI, the stored value takes precedence from then on.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Dict, Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB_PATH = str(_PROJECT_ROOT / "data" / "app_settings.db")


class SettingsStore:
    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, key: str) -> Optional[str]:
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def set(self, key: str, value: str) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()
        os.environ[key] = value  # immediate effect for the current process

    def delete(self, key: str) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            conn.commit()
        finally:
            conn.close()
        os.environ.pop(key, None)

    def get_all(self) -> Dict[str, str]:
        conn = sqlite3.connect(self.db_path)
        try:
            return dict(conn.execute("SELECT key, value FROM settings").fetchall())
        finally:
            conn.close()

    def apply_to_environment(self) -> None:
        """Load every stored setting into os.environ. Call once at process
        startup, before anything else reads env vars."""
        for key, value in self.get_all().items():
            os.environ[key] = value
