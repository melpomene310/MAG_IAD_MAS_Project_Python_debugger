"""Сравнение вывода и вердикты (docs/spec.md, раздел 6.2)."""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from debugmas.sandbox.runner import RunResult

FLOAT_TOL = 1e-6
VERDICTS = ("AC", "WA", "RE", "TLE", "MLE")
_NUMBER = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def _is_number(tok: str) -> bool:
    return bool(_NUMBER.match(tok))


def _is_float_like(tok: str) -> bool:
    return "." in tok or "e" in tok or "E" in tok


def tokens_equal(a: str, b: str, tol: float = FLOAT_TOL) -> bool:
    if a == b:
        return True
    if _is_number(a) and _is_number(b) and (_is_float_like(a) or _is_float_like(b)):
        x, y = float(a), float(b)
        if math.isnan(x) or math.isnan(y):
            return False
        diff = abs(x - y)
        return diff <= tol or diff <= tol * max(abs(x), abs(y))
    return False


def outputs_match(actual: str, expected: str, tol: float = FLOAT_TOL) -> bool:
    """Сравнение по токенам, разделённым пробельными символами."""
    got, exp = actual.split(), expected.split()
    if len(got) != len(exp):
        return False
    return all(tokens_equal(a, b, tol) for a, b in zip(got, exp, strict=True))


def judge(res: RunResult, expected: str) -> str:
    if res.timed_out:
        return "TLE"
    if res.memory_exceeded:
        return "MLE"
    if res.exit_code != 0:
        return "RE"
    return "AC" if outputs_match(res.stdout, expected) else "WA"
