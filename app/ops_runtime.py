"""In-process background supervisor for scheduled, read-only market jobs.

The scheduler deliberately reports process-local scope. A sleeping/ephemeral
host or multiple replicas require an external worker and durable database.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Awaitable, Callable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BackgroundSupervisor:
    def __init__(self, interval_seconds: int = 300):
        self.interval_seconds = max(60, min(3600, int(interval_seconds)))
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._job: Callable[[], Awaitable[dict]] | None = None
        self._state = {
            "status": "stopped",
            "scope": "single_web_process",
            "scheduler_backend": "asyncio_in_process",
            "durable": False,
            "job_name": "watchlist_market_monitor",
            "interval_seconds": self.interval_seconds,
            "runs": 0,
            "failures": 0,
            "last_started_at": None,
            "last_finished_at": None,
            "last_result": None,
            "last_error": None,
        }

    async def start(self, job: Callable[[], Awaitable[dict]]) -> None:
        if self._task and not self._task.done():
            return
        self._job = job
        self._stopping = False
        self._state["status"] = "running"
        self._task = asyncio.create_task(self._run(), name="quant-nexus-background-supervisor")

    async def stop(self) -> None:
        self._stopping = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._state["status"] = "stopped"

    async def _run(self) -> None:
        while not self._stopping:
            self._state["last_started_at"] = _now()
            try:
                result = await self._job() if self._job else {}
                self._state["runs"] += 1
                self._state["last_result"] = result
                self._state["last_error"] = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._state["failures"] += 1
                self._state["last_error"] = type(exc).__name__
            finally:
                self._state["last_finished_at"] = _now()
            await asyncio.sleep(self.interval_seconds)

    def status(self) -> dict:
        task_running = bool(self._task and not self._task.done())
        return {**self._state, "status": "running" if task_running else "stopped"}
