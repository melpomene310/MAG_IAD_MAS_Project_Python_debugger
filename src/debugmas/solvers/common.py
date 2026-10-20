"""Общие части решателей."""

from __future__ import annotations

from typing import Any

from debugmas.config import ExperimentConfig, load_prompt, render
from debugmas.data.schema import AgentView
from debugmas.feedback import initial_report, numbered


def initial_messages(
    view: AgentView, cfg: ExperimentConfig, system_prompt: str
) -> list[dict[str, Any]]:
    """Системное и стартовое сообщения (одинаковая стартовая информация для решателей)."""
    user = render(
        load_prompt("task_initial.md"),
        code=numbered(view.code),
        report=initial_report(view, cfg.initial_failing_shown, cfg.show_expected_output),
    )
    return [
        {"role": "system", "content": load_prompt(system_prompt)},
        {"role": "user", "content": user},
    ]
