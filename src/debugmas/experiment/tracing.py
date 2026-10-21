"""Трасса событий запуска (`trace.jsonl`, docs/spec.md, раздел 10.1)."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class EventSink:
    """Потокобезопасная запись событий в jsonl (или в память, если путь не задан)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.events: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def write(self, event: dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False, default=str)
        with self._lock:
            if self.path is None:
                self.events.append(json.loads(line))
            else:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")


class TaskTracer:
    """Трассировщик, привязанный к одной задаче и решателю."""

    def __init__(self, sink: EventSink, run_id: str, task_id: str, solver: str) -> None:
        self.sink = sink
        self.run_id = run_id
        self.task_id = task_id
        self.solver = solver

    def emit(
        self,
        event: str,
        *,
        agent: str | None = None,
        step: int | None = None,
        tool: str | None = None,
        args: Any = None,
        result: Any = None,
        usage: dict[str, Any] | None = None,
        cache_hit: bool | None = None,
        **extra: Any,
    ) -> None:
        rec: dict[str, Any] = {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "solver": self.solver,
            "agent": agent or self.solver,
            "step": step,
            "event": event,
        }
        if tool is not None:
            rec["tool"] = tool
        if args is not None:
            rec["args"] = args
        if result is not None:
            rec["result"] = result
        if usage is not None:
            rec["usage"] = usage
        if cache_hit is not None:
            rec["cache_hit"] = cache_hit
        rec.update(extra)
        rec["ts"] = datetime.now(UTC).isoformat()
        self.sink.write(rec)


def null_tracer(task_id: str = "-", solver: str = "-") -> TaskTracer:
    return TaskTracer(EventSink(None), "-", task_id, solver)
