"""
SQLite-backed History Store

Stores cost prediction runs for comparison between deployments.
Database is stored at: ~/.terraform-cost-predictor/history.db
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Default location for the history database
DEFAULT_DB_DIR = Path.home() / ".terraform-cost-predictor"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "history.db"


@dataclass
class HistoryEntry:
    """A recorded cost prediction run."""

    id: int
    run_id: str
    timestamp: str
    plan_hash: str
    label: str  # user-provided label (e.g., "staging", "production")
    total_cost: float
    currency: str
    resource_count: int
    resources_json: str  # JSON blob of all resource costs
    plan_path: str


class HistoryStore:
    """
    Manages the SQLite history of past cost prediction runs.

    Usage:
        store = HistoryStore()
        run_id = store.save_run(label, total_cost, resources, plan_path)
        previous = store.get_latest_run(label)
        all_runs = store.list_runs(label)
    """

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or DEFAULT_DB_PATH
        self._ensure_dir()
        self._init_db()

    def _ensure_dir(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create the database schema if it doesn't exist."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id          TEXT NOT NULL UNIQUE,
                    timestamp       TEXT NOT NULL,
                    plan_hash       TEXT NOT NULL,
                    label           TEXT NOT NULL DEFAULT '',
                    total_cost      REAL NOT NULL,
                    currency        TEXT NOT NULL DEFAULT 'USD',
                    resource_count  INTEGER NOT NULL DEFAULT 0,
                    resources_json  TEXT NOT NULL DEFAULT '[]',
                    plan_path       TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_label ON runs(label)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_timestamp ON runs(timestamp)
            """)
            conn.commit()

    def save_run(
        self,
        label: str,
        total_cost: float,
        resources: list[dict[str, Any]],
        plan_path: str = "",
        plan_hash: str = "",
        currency: str = "USD",
    ) -> str:
        """
        Save a cost prediction run to history.

        Returns:
            The generated run_id string.
        """
        import hashlib
        import uuid

        run_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        if not plan_hash:
            plan_hash = hashlib.md5(json.dumps(resources, sort_keys=True).encode()).hexdigest()[:12]

        resources_json = json.dumps(resources, default=str)

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO runs
                    (run_id, timestamp, plan_hash, label, total_cost, currency,
                     resource_count, resources_json, plan_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    timestamp,
                    plan_hash,
                    label,
                    total_cost,
                    currency,
                    len(resources),
                    resources_json,
                    plan_path,
                ),
            )
            conn.commit()

        return run_id

    def get_latest_run(self, label: str = "") -> dict[str, Any] | None:
        """Get the most recent run, optionally filtered by label."""
        with self._get_conn() as conn:
            if label:
                row = conn.execute(
                    "SELECT * FROM runs WHERE label = ? ORDER BY timestamp DESC LIMIT 1",
                    (label,),
                ).fetchone()
            else:
                row = conn.execute("SELECT * FROM runs ORDER BY timestamp DESC LIMIT 1").fetchone()

        if row is None:
            return None
        return self._row_to_dict(row)

    def get_run_by_id(self, run_id: str) -> dict[str, Any] | None:
        """Get a specific run by its run_id."""
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_runs(self, label: str = "", limit: int = 20) -> list[dict[str, Any]]:
        """List recent runs, optionally filtered by label."""
        with self._get_conn() as conn:
            if label:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE label = ? ORDER BY timestamp DESC LIMIT ?",
                    (label, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM runs ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def delete_run(self, run_id: str) -> bool:
        """Delete a run by ID."""
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
            conn.commit()
        return cursor.rowcount > 0

    def clear_all(self) -> int:
        """Clear all history. Returns the number of deleted rows."""
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM runs")
            conn.commit()
        return cursor.rowcount

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        try:
            d["resources"] = json.loads(d.pop("resources_json", "[]"))
        except (json.JSONDecodeError, KeyError):
            d["resources"] = []
        return d
