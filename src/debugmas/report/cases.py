"""`make case`: хронология решения одной задачи (docs/spec.md, раздел 10.3)."""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any

from debugmas.data.ground_truth import load_ground_truth
from debugmas.data.schema import load_agent_view
from debugmas.eval.evaluate import load_results, load_run_config
from debugmas.feedback import summary_line

SHORT = 400


def _short(value: Any, limit: int = SHORT) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + f"… [{len(text)} символов]"


def _events(run_dir: Path, task_id: str) -> list[dict[str, Any]]:
    path = run_dir / "trace.jsonl"
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if f'"{task_id}"' not in line:
                continue
            ev = json.loads(line)
            if ev.get("task_id") == task_id:
                out.append(ev)
    return out


def _unified(a: str, b: str, from_name: str, to_name: str) -> str:
    # без keepends: отсутствие перевода строки в конце файла не считается изменением
    return "\n".join(
        difflib.unified_diff(a.splitlines(), b.splitlines(), from_name, to_name, lineterm="")
    )


def render_case(run_dir: Path, task_id: str) -> str:
    cfg = load_run_config(run_dir)
    task_dir = Path(cfg["data_dir"]) / "tasks" / task_id
    view = load_agent_view(task_dir)
    gt = load_ground_truth(task_dir)
    result = next((r for r in load_results(run_dir) if r.task_id == task_id), None)

    out = [f"# Задача {task_id} (программа {view.program_id}), запуск {run_dir.name}", ""]
    out.append(f"Сложность: {gt.difficulty}, дата: {gt.date}, тестов: {len(view.tests)}")
    out.append(f"Исходная программа: {summary_line(view.initial_results)}")
    out += ["", "## Исходный код (>> — строка ошибки по разметке)", "```"]
    for i, line in enumerate(view.code.splitlines(), 1):
        mark = ">>" if i in gt.fault_lines else "  "
        out.append(f"{mark}{i:>4} | {line}")
    out += ["```", f"Эталонная строка: `{gt.fixed_line.strip()}`", "", "## Хронология", ""]

    for ev in _events(run_dir, task_id):
        kind = ev.get("event")
        head = f"[шаг {ev.get('step')}] [{ev.get('agent')}] {kind}"
        if kind == "llm_call":
            res = ev.get("result", {})
            usage = ev.get("usage", {})
            out.append(f"{head} (токены {usage}, кэш: {ev.get('cache_hit')})")
            if res.get("content"):
                out.append("  модель: " + _short(res["content"], 1200).replace("\n", "\n  "))
            for tc in res.get("tool_calls", []):
                out.append(f"  → {tc.get('name')}({_short(tc.get('arguments', ''), 300)})")
        elif kind == "tool_call":
            out.append(f"{head}: {ev.get('tool')}({_short(ev.get('args'), 200)})")
            out.append("  ← " + _short(ev.get("result")))
        elif kind == "attempt":
            out.append(f"{head}: {ev.get('result')}")
        elif kind in ("llm_error", "crash"):
            out.append(f"{head}: {_short(ev.get('error'), 800)}")
        elif kind in ("task_end", "reminder", "task_start"):
            out.append(f"{head} {_short(ev.get('result', ''), 200)}")
    out.append("")

    if result is None:
        out.append("Результат задачи в tasks.jsonl не найден.")
        return "\n".join(out)
    out.append(f"## Итог: {result.status}" + (f" — {result.error}" if result.error else ""))
    out.append(
        f"Токены: {result.usage.total} (вход {result.usage.input}, выход {result.usage.output}); "
        f"время {result.wall_time_s} с; шаги {result.steps}; инструменты {result.tool_calls}"
    )
    for a in result.attempts:
        verdicts = summary_line(a.verdicts) if a.verdicts else (a.note or "—")
        out.append(f"- попытка {a.index}: {'AC' if a.passed_all else 'FAIL'} ({verdicts})")
    if result.final_code:
        out += ["", "## Diff: исходная → итоговая", "```diff"]
        out.append(_unified(view.code, result.final_code, "faulty.py", "final.py"))
        out += ["```", "", "## Diff: исходная → эталонная", "```diff"]
        out.append(_unified(view.code, gt.fixed_code, "faulty.py", "reference.py"))
        out.append("```")
    return "\n".join(out)
