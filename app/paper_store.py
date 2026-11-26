"""SQLite persistence for simulated trades and account balance.

For durable persistence on a hosted platform, PAPER_DB_PATH must point to
a mounted persistent volume. The default application filesystem may be
ephemeral depending on the hosting provider.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any


class PaperStore:
    def __init__(self, path: str | None = None):
        self.path = path or os.getenv(
            "PAPER_DB_PATH",
            str(Path(__file__).resolve().parent.parent / "data" / "paper.sqlite3"),
        )
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self.durable_configured = os.getenv("PAPER_STORAGE_DURABLE", "false").lower() == "true"
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("CREATE TABLE IF NOT EXISTS paper_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS paper_trades (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
            connection.execute(
                "INSERT OR IGNORE INTO paper_state(key, value) VALUES('balance', '10000.0')"
            )

    def load(self) -> tuple[float, list[dict[str, Any]]]:
        with self._connect() as connection:
            row = connection.execute("SELECT value FROM paper_state WHERE key='balance'").fetchone()
            balance = float(row["value"]) if row else 10_000.0
            trades = [
                json.loads(row["payload"])
                for row in connection.execute("SELECT payload FROM paper_trades ORDER BY id")
            ]
        return balance, trades

    def save(self, balance: float, trades: list[dict[str, Any]]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO paper_state(key, value) VALUES('balance', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(float(balance)),),
            )
            connection.execute("DELETE FROM paper_trades")
            connection.executemany(
                "INSERT INTO paper_trades(id, payload) VALUES(?, ?)",
                [(int(trade["id"]), json.dumps(trade, separators=(",", ":"), allow_nan=False)) for trade in trades],
            )

    def reset(self, balance: float = 10_000.0) -> None:
        self.save(balance, [])
