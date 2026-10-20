"""GroundTruth не попадает к решателям (docs/spec.md, раздел 12, п. 1).

Статический разбор: модули solvers/, tools/, llm/, sandbox/ (и общие модули, которые они
импортируют) не импортируют GroundTruth/ground_truth и не содержат строк с путём
ground_truth.json. Не удалять и не ослаблять.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "debugmas"
PROTECTED = ("solvers", "tools", "llm", "sandbox")
# общие модули, которые импортируются решателями и инструментами
SHARED = ("feedback.py", "config.py", "data/schema.py", "experiment/tracing.py")
FORBIDDEN_NAMES = {"GroundTruth", "load_ground_truth", "save_ground_truth", "GROUND_TRUTH_FILE"}
FORBIDDEN_MODULES = ("debugmas.data.ground_truth", "debugmas.eval", "debugmas.report")
FORBIDDEN_STRINGS = ("ground_truth", "groundtruth", "correctversion", "faultlocation")


def _files() -> list[Path]:
    files = [p for d in PROTECTED for p in (SRC / d).rglob("*.py")]
    files += [SRC / s for s in SHARED]
    return sorted(files)


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith(FORBIDDEN_MODULES):
                out.append(f"import from {mod}")
            out += [f"import {a.name}" for a in node.names if a.name in FORBIDDEN_NAMES]
        elif isinstance(node, ast.Import):
            out += [f"import {a.name}" for a in node.names if a.name.startswith(FORBIDDEN_MODULES)]
        elif isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if name in FORBIDDEN_NAMES:
                out.append(f"name {name}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            low = node.value.lower().replace("-", "_")
            if any(s in low for s in FORBIDDEN_STRINGS):
                out.append(f"string {node.value[:60]!r}")
    return out


def test_files_found():
    assert len(_files()) > 10


@pytest.mark.parametrize("path", _files(), ids=lambda p: str(p.relative_to(SRC)))
def test_no_ground_truth_access(path: Path):
    if path.name == "schema.py":
        # schema.py определяет GroundTruth (docs/spec.md, раздел 4.2), но ничего не читает
        tree = ast.parse(path.read_text(encoding="utf-8"))
        strings = [
            n.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
        assert not [s for s in strings if "ground_truth" in s.lower()]
        return
    assert _violations(path) == []


def test_detector_catches_leak(tmp_path: Path):
    bad = tmp_path / "bad.py"
    bad.write_text(
        "from debugmas.data.ground_truth import load_ground_truth\n"
        "p = 'tasks/x/ground_truth.json'\n"
    )
    assert len(_violations(bad)) >= 2


def test_agent_view_has_no_fix(tmp_path: Path):
    from debugmas.data.schema import AgentView

    fields = set(AgentView.__dataclass_fields__)
    assert not fields & {"fixed_code", "fault_lines", "fixed_line"}
