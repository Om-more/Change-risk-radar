"""Persistent result storage, keyed by commit hash.

Replaces the single `_latest_result` global variable in main.py, which
had three real problems: two commits close together overwrote each
other, nothing survived a server restart, and there was no history to
look back through. SQLite is the minimum viable fix -- still a single
file, no server to run, but actually durable and queryable.
"""

import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "risk_radar.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS results (
            commit_hash TEXT PRIMARY KEY,
            repo_path   TEXT NOT NULL,
            created_at  REAL NOT NULL,
            result_json TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON results(created_at)")
    return conn


def save(commit_hash: str, repo_path: str, result: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO results (commit_hash, repo_path, created_at, result_json) "
            "VALUES (?, ?, ?, ?)",
            (commit_hash, repo_path, time.time(), json.dumps(result)),
        )


def get(commit_hash: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT result_json FROM results WHERE commit_hash = ?", (commit_hash,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def get_latest() -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT commit_hash, result_json FROM results ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    result = json.loads(row[1])
    result["commit_hash"] = row[0]
    return result


def list_recent(limit: int = 20) -> list:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT commit_hash, repo_path, created_at FROM results "
            "ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [{"commit_hash": r[0], "repo_path": r[1], "created_at": r[2]} for r in rows]
