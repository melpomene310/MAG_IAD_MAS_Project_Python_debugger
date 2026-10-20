"""Решатель `single_agent`: один агент в цикле tool calling (docs/spec.md, раздел 8.2)."""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

from debugmas.config import ExperimentConfig, load_prompt
from debugmas.data.schema import AgentView
from debugmas.llm.client import LLMError
from debugmas.solvers.base import (
    Attempt,
    LLMSession,
    RunContext,
    SolverResult,
    TokenLimitReached,
    register_solver,
)
from debugmas.solvers.common import initial_messages
from debugmas.tools.registry import ToolRegistry


@dataclass
class _ToolMessage:
    index: int  # позиция в списке сообщений
    step: int
    summary: str


def compact_messages(
    messages: list[dict[str, Any]], tool_msgs: list[_ToolMessage], step: int, keep_steps: int
) -> list[dict[str, Any]]:
    """Результаты инструментов старше последних `keep_steps` шагов заменяются сводкой."""
    old = {tm.index: tm.summary for tm in tool_msgs if step - tm.step >= keep_steps}
    if not old:
        return messages
    return [{**m, "content": old[i]} if i in old else m for i, m in enumerate(messages)]


def _parse_args(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


def _args_for_trace(args: Any) -> Any:
    if isinstance(args, dict) and isinstance(args.get("code"), str):
        return {**args, "code": f"<{len(args['code'].splitlines())} строк>"}
    return args


class SingleAgentSolver:
    name = "single_agent"

    def __init__(self, cfg: ExperimentConfig) -> None:
        self.cfg = cfg

    def solve(self, view: AgentView, ctx: RunContext) -> SolverResult:
        cfg = self.cfg
        start = time.monotonic()
        session = LLMSession(ctx, agent=self.name)
        tools: ToolRegistry = ctx.tools
        schemas = tools.schemas()
        tctx = ctx.tool_context(view)
        messages = initial_messages(view, cfg, "single_agent_system.md")
        tool_msgs: list[_ToolMessage] = []
        counts: Counter[str] = Counter()
        attempts: list[Attempt] = []
        status: str | None = None
        error: str | None = None
        step = 0

        try:
            while status is None:
                if step >= ctx.limits.max_steps:
                    status = "step_limit"
                    break
                if ctx.deadline_passed:
                    raise TimeoutError("превышен таймаут задачи")
                visible = compact_messages(messages, tool_msgs, step, cfg.context_keep_steps)
                resp = session.chat(visible, schemas, step=step + 1)
                step += 1
                messages.append(resp.assistant_message())
                if not resp.tool_calls:
                    messages.append(
                        {"role": "user", "content": load_prompt("single_agent_reminder.md")}
                    )
                    ctx.tracer.emit("reminder", agent=self.name, step=step)
                    continue
                for tc in resp.tool_calls:
                    counts[tc.name] += 1
                    n_sub = len(tctx.submissions)
                    result = tools.call(tc.name, tc.arguments, tctx)
                    ctx.tracer.emit(
                        "tool_call",
                        agent=self.name,
                        step=step,
                        tool=tc.name,
                        args=_args_for_trace(_parse_args(tc.arguments)),
                        result=result,
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                    tool_msgs.append(
                        _ToolMessage(len(messages) - 1, step, tools.summarize(tc.name, result))
                    )
                    if len(tctx.submissions) > n_sub:
                        sub = tctx.submissions[-1]
                        attempts.append(
                            Attempt(
                                index=len(attempts) + 1,
                                code=sub.code,
                                verdicts=sub.verdicts,
                                passed_all=sub.passed_all,
                                usage=session.usage,
                                wall_time_s=round(time.monotonic() - start, 3),
                            )
                        )
                        ctx.tracer.emit(
                            "attempt",
                            agent=self.name,
                            step=step,
                            result={"index": len(attempts), "passed_all": sub.passed_all},
                        )
                        if sub.passed_all:
                            status = "solved"
                        elif tctx.submissions_left <= 0:
                            status = "attempts_exhausted"
                    if status is not None:
                        break
        except TokenLimitReached as exc:
            status, error = "token_limit", str(exc)
        except LLMError as exc:
            status, error = "error", str(exc)
        except TimeoutError as exc:
            status, error = "error", f"task_timeout: {exc}"

        final = next((a.code for a in attempts if a.passed_all), None)
        if final is None and attempts:
            final = attempts[-1].code
        return SolverResult(
            task_id=view.task_id,
            solver=self.name,
            status=status or "error",
            attempts=attempts,
            final_code=final,
            usage=session.usage,
            wall_time_s=round(time.monotonic() - start, 3),
            llm_time_s=round(session.llm_time_s, 3),
            sandbox_time_s=round(tctx.sandbox_time_s, 3),
            steps=step,
            tool_calls=dict(counts),
            error=error,
        )


@register_solver("single_agent")
def _make(cfg: ExperimentConfig) -> SingleAgentSolver:
    return SingleAgentSolver(cfg)
