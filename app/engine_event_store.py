"""Append-only SQLite event store for research, audit and replay metadata.

This store is read/write only for application telemetry. It never places or
modifies exchange orders. Durability depends on the database path being on a
real persistent volume; the environment flag is an operator declaration.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EngineEventStore:
    def __init__(self, path: str | None = None):
        self.path = path or os.getenv(
            "ENGINE_EVENT_DB_PATH",
            os.getenv("PAPER_DB_PATH", str(Path(__file__).resolve().parent.parent / "data" / "paper.sqlite3")),
        )
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self.durable_configured = os.getenv("ENGINE_EVENT_STORAGE_DURABLE", "false").lower() == "true"
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS engine_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    symbol TEXT,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    dedupe_key TEXT UNIQUE,
                    payload TEXT NOT NULL,
                    consumed_at TEXT
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS idx_engine_events_type_symbol ON engine_events(event_type, symbol, id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_engine_events_timestamp ON engine_events(timestamp)")

    def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        symbol: str | None = None,
        source: str = "quant_nexus",
        dedupe_key: str | None = None,
    ) -> dict:
        if not event_type or len(event_type) > 80:
            raise ValueError("invalid_event_type")
        if not isinstance(payload, dict):
            raise ValueError("event_payload_must_be_object")
        encoded = json.dumps(payload, separators=(",", ":"), allow_nan=False)
        event_id = uuid.uuid4().hex
        timestamp = _now()
        with self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO engine_events(event_id,event_type,symbol,timestamp,source,dedupe_key,payload) VALUES(?,?,?,?,?,?,?)",
                    (event_id, event_type, symbol, timestamp, source, dedupe_key, encoded),
                )
                inserted = True
            except sqlite3.IntegrityError:
                if not dedupe_key:
                    raise
                row = connection.execute(
                    "SELECT event_id,event_type,symbol,timestamp,source,payload FROM engine_events WHERE dedupe_key=?",
                    (dedupe_key,),
                ).fetchone()
                if row is None:
                    raise
                return self._row(row, inserted=False)
        return {
            "event_id": event_id,
            "event_type": event_type,
            "symbol": symbol,
            "timestamp": timestamp,
            "source": source,
            "payload": payload,
            "inserted": inserted,
        }

    @staticmethod
    def _row(row, inserted: bool = False) -> dict:
        return {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "symbol": row["symbol"],
            "timestamp": row["timestamp"],
            "source": row["source"],
            "payload": json.loads(row["payload"]),
            "inserted": inserted,
        }

    def list_events(
        self,
        *,
        event_type: str | None = None,
        symbol: str | None = None,
        limit: int = 200,
        include_consumed: bool = True,
    ) -> list[dict]:
        limit = max(1, min(int(limit), 2000))
        clauses = []
        params: list[Any] = []
        if event_type:
            clauses.append("event_type=?")
            params.append(event_type)
        if symbol:
            clauses.append("symbol=?")
            params.append(symbol.upper())
        if not include_consumed:
            clauses.append("consumed_at IS NULL")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_id,event_type,symbol,timestamp,source,payload FROM engine_events"
                + where + " ORDER BY id DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
        return [self._row(row) for row in reversed(rows)]

    def acknowledge(self, event_ids: list[str]) -> int:
        clean = [str(value) for value in event_ids if value]
        if not clean:
            return 0
        now = _now()
        with self._connect() as connection:
            cursor = connection.executemany(
                "UPDATE engine_events SET consumed_at=? WHERE event_id=? AND consumed_at IS NULL",
                [(now, value) for value in clean],
            )
            return cursor.rowcount

    def stats(self) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS published, SUM(CASE WHEN consumed_at IS NOT NULL THEN 1 ELSE 0 END) AS consumed FROM engine_events"
            ).fetchone()
        published = int(row["published"] or 0)
        consumed = int(row["consumed"] or 0)
        return {
            "status": "ok",
            "backend": "sqlite_append_only_event_log",
            "published": published,
            "consumed": consumed,
            "backlog": max(0, published - consumed),
            "durable_configured": self.durable_configured,
            "scope": "shared_database_file; durability depends on mounted persistent storage",
        }
