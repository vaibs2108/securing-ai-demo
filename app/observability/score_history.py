"""
Securing AI — persisted daily posture-score history.

The dashboard's trend chart used to be entirely fabricated: backend/main.py's
_synth_trend() generated a random walk anchored so its *last* point matched
the real current score, with the other 29 points invented — there was no
real history to plot, since nothing persisted past scores. This store keeps
one real snapshot per phase per calendar day (SQLite, data/score_history.db),
so as the app actually gets used across sessions and days, the chart fills
in with genuine history instead of noise. It starts sparse (one point on day
one) rather than pretending to have 30 days of data it doesn't have.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB_PATH = str(_PROJECT_ROOT / "data" / "score_history.db")


class ScoreHistoryStore:
    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS score_history (
                    day   TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    score REAL NOT NULL,
                    PRIMARY KEY (day, phase)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def record_snapshot(self, scores: Dict[str, float]) -> None:
        """Upsert today's score for each phase. Safe to call on every
        dashboard load — only the latest value per calendar day is kept, so
        visiting the page repeatedly in one day doesn't create fake extra
        points, it just keeps today's point current."""
        today = date.today().isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            for phase, score in scores.items():
                conn.execute(
                    """
                    INSERT INTO score_history (day, phase, score) VALUES (?, ?, ?)
                    ON CONFLICT(day, phase) DO UPDATE SET score = excluded.score
                    """,
                    (today, phase, float(score)),
                )
            conn.commit()
        finally:
            conn.close()

    def get_history(self, phase: str, days: int = 30) -> List[Dict[str, object]]:
        """Real recorded snapshots for one phase, oldest first, capped at
        the most recent `days` calendar days that actually have a record."""
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT day, score FROM score_history WHERE phase = ? ORDER BY day DESC LIMIT ?",
                (phase, days),
            ).fetchall()
        finally:
            conn.close()
        return [{"day": day, "score": score} for day, score in reversed(rows)]
