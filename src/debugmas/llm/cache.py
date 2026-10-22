"""Дисковый кэш ответов LLM на SQLite (docs/spec.md, раздел 7)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
    key TEXT PRIMARY KEY,
    response TEXT NOT NULL,
    usage TEXT,
    latency_s REAL NOT NULL,
    created TEXT DEFAULT CURRENT_TIMESTAMP
)
"""


def cache_key(
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    params: dict[str, Any],
    repeat_idx: int,
) -> str:
    payload = {
        "base_url": base_url,
        "model": model,
        "messages": messages,
        "tools": tools or [],
        "params": params,
        "repeat_idx": repeat_idx,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class LLMCache:
    def __init__(self, cache_dir: str | Path) -> None:
        self.path = Path(cache_dir) / "llm_cache.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as con:
            row = con.execute(
                "SELECT response, usage, latency_s FROM responses WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        return {
            "response": json.loads(row[0]),
            "usage": json.loads(row[1]) if row[1] else None,
            "latency_s": row[2],
        }

    def put(
        self, key: str, response: dict[str, Any], usage: dict[str, Any] | None, latency_s: float
    ) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO responses (key, response, usage, latency_s) "
                "VALUES (?, ?, ?, ?)",
                (
                    key,
                    json.dumps(response, ensure_ascii=False),
                    json.dumps(usage, ensure_ascii=False) if usage is not None else None,
                    latency_s,
                ),
            )
