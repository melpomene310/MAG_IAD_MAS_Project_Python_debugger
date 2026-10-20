"""Решатель `workflow`: фиксированный цикл без инструментов (docs/spec.md, раздел 8.1)."""

from __future__ import annotations

import ast
import re
import time

from debugmas.config import ExperimentConfig, load_prompt, render
from debugmas.data.schema import AgentView
from debugmas.feedback import format_test_report, summary_line
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

_CODE_BLOCK = re.compile(r"```(?:python3?|py)[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_code(text: str | None) -> str | None:
    """Последний блок ```python ... ``` из ответа модели."""
    if not text:
        return None
    blocks = _CODE_BLOCK.findall(text)
    if not blocks:
        return None
    code = blocks[-1]
    return code if code.endswith("\n") else code + "\n"


class WorkflowSolver:
    name = "workflow"

    def __init__(self, cfg: ExperimentConfig) -> None:
        self.cfg = cfg

    def solve(self, view: AgentView, ctx: RunContext) -> SolverResult:
        cfg = self.cfg
        start = time.monotonic()
        session = LLMSession(ctx, agent=self.name)
        tctx = ctx.tool_context(view)
        messages = initial_messages(view, cfg, "workflow_system.md")
        attempts: list[Attempt] = []
        status, error = "attempts_exhausted", None
        last_code: str | None = None

        try:
            for i in range(1, ctx.limits.max_attempts + 1):
                if ctx.deadline_passed:
                    raise TimeoutError("превышен таймаут задачи")
                before = session.usage
                t0 = time.monotonic()
                resp = session.chat(messages, step=i)
                content = resp.content or ""
                messages.append({"role": "assistant", "content": content})
                code = extract_code(content)
                verdicts: dict[str, str] = {}
                passed, note = False, None
                if code is None:
                    note = "no_code_block"
                    feedback = load_prompt("feedback_no_code.md")
                else:
                    last_code = code
                    try:
                        ast.parse(code)
                    except (SyntaxError, ValueError) as exc:
                        note = "syntax_error"
                        feedback = render(load_prompt("feedback_syntax_error.md"), error=str(exc))
                    else:
                        results = tctx.run_all(code)
                        verdicts = {r.name: r.verdict for r in results}
                        passed = all(v == "AC" for v in verdicts.values())
                        feedback = format_test_report(
                            view.tests, results, cfg.initial_failing_shown, cfg.show_expected_output
                        )
                attempt = Attempt(
                    index=i,
                    code=code,
                    verdicts=verdicts,
                    passed_all=passed,
                    usage=session.usage - before,
                    wall_time_s=round(time.monotonic() - t0, 3),
                    note=note,
                )
                attempts.append(attempt)
                ctx.tracer.emit(
                    "attempt",
                    agent=self.name,
                    step=i,
                    result={
                        "index": i,
                        "passed_all": passed,
                        "summary": summary_line(verdicts) if verdicts else note,
                    },
                    usage=attempt.usage.short(),
                )
                if passed:
                    status = "solved"
                    break
                if i < ctx.limits.max_attempts:
                    messages.append(
                        {
                            "role": "user",
                            "content": render(
                                load_prompt("workflow_retry.md"),
                                code=last_code or "(код не извлечён)",
                                feedback=feedback,
                            ),
                        }
                    )
        except TokenLimitReached as exc:
            status, error = "token_limit", str(exc)
        except LLMError as exc:
            status, error = "error", str(exc)
        except TimeoutError as exc:
            status, error = "error", f"task_timeout: {exc}"

        final = next((a.code for a in attempts if a.passed_all), None)
        if final is None:
            final = next((a.code for a in reversed(attempts) if a.code), None)
        return SolverResult(
            task_id=view.task_id,
            solver=self.name,
            status=status,
            attempts=attempts,
            final_code=final,
            usage=session.usage,
            wall_time_s=round(time.monotonic() - start, 3),
            llm_time_s=round(session.llm_time_s, 3),
            sandbox_time_s=round(tctx.sandbox_time_s, 3),
            steps=session.calls,
            tool_calls={},
            error=error,
        )


@register_solver("workflow")
def _make(cfg: ExperimentConfig) -> WorkflowSolver:
    return WorkflowSolver(cfg)
