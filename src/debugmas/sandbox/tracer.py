"""Неинтерактивная трассировка значений выражений (docs/spec.md, раздел 6.3)."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from debugmas.sandbox.limits import Limits
from debugmas.sandbox.runner import PROGRAM_FILE, execute, truncate_text

HARNESS_FILE = "trace_harness.py"
TRACE_TIME_FACTOR = 5.0
_HARNESS_SOURCE = (Path(__file__).parent / HARNESS_FILE).read_text(encoding="utf-8")


@dataclass
class TraceResult:
    hits: list[dict[str, Any]] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    finished: str | None = None  # finished | exit | exception | None (не завершилась)
    timed_out: bool = False
    max_hits_reached: bool = False
    hint: str | None = None

    def to_dict(self, output_limit: int = 2000) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "n_hits": len(self.hits),
            "max_hits_reached": self.max_hits_reached,
            "stdout": truncate_text(self.stdout, output_limit),
            "stderr": truncate_text(self.stderr, output_limit),
            "exit_code": self.exit_code,
            "finished": self.finished,
            "timed_out": self.timed_out,
            **({"hint": self.hint} if self.hint else {}),
        }


def trace(
    code: str,
    stdin: str | bytes,
    lines: list[int],
    expressions: list[str],
    max_hits: int = 30,
    time_limit_s: float = 2.0,
    memory_mb: int = 1024,
    python: str | None = None,
) -> TraceResult:
    marker = f"@@TRACE{secrets.token_hex(6)}@@"
    config = {
        "marker": marker,
        "program": PROGRAM_FILE,
        "lines": [int(x) for x in lines],
        "expressions": [str(e) for e in expressions],
        "max_hits": int(max_hits),
    }
    limits = Limits(time_limit_s=time_limit_s * TRACE_TIME_FACTOR, memory_mb=memory_mb)
    res = execute(
        {
            PROGRAM_FILE: code,
            HARNESS_FILE: _HARNESS_SOURCE,
            "trace_config.json": json.dumps(config),
        },
        HARNESS_FILE,
        stdin,
        limits,
        python,
    )
    out = TraceResult(stdout=res.stdout, timed_out=res.timed_out, exit_code=res.exit_code)
    program_stderr: list[str] = []
    for raw in res.stderr.splitlines(keepends=True):
        idx = raw.find(marker)
        if idx < 0:
            program_stderr.append(raw)
            continue
        if idx > 0:
            program_stderr.append(raw[:idx])
        try:
            rec = json.loads(raw[idx + len(marker) :])
        except json.JSONDecodeError:
            continue
        if "end" in rec:
            out.finished = rec["end"]
            out.exit_code = rec["exit_code"]
            out.max_hits_reached = bool(rec.get("max_hits_reached"))
        else:
            out.hits.append(rec)
    out.stderr = "".join(program_stderr)
    if len(out.hits) >= max_hits:
        out.max_hits_reached = True
    if res.timed_out:
        out.hint = (
            "Трассировка прервана по таймауту; возвращены собранные значения. "
            "Возьмите вход поменьше (run_program/trace с input) или меньше строк."
        )
    return out
