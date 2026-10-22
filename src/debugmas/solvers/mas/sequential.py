"""Последовательная MAS: исследователь, исправитель, проверяющий."""

from __future__ import annotations

import json
import time
from collections import Counter
from typing import Any

from debugmas.config import ExperimentConfig, load_prompt, render
from debugmas.data.schema import AgentView
from debugmas.feedback import format_test_report, summary_line
from debugmas.llm.client import LLMError, LLMResponse
from debugmas.solvers.base import (
    Attempt,
    LLMSession,
    RunContext,
    SolverResult,
    TokenLimitReached,
    register_solver,
)
from debugmas.solvers.common import initial_messages
from debugmas.solvers.workflow import extract_code

RESEARCH_TOOLS = ("get_test", "run_program", "trace", "run_tests")


class StepLimitReached(RuntimeError):
    pass


class SequentialMASSolver:
    name = "mas_sequential"

    def __init__(self, cfg: ExperimentConfig) -> None:
        self.cfg = cfg

    def solve(self, view: AgentView, ctx: RunContext) -> SolverResult:
        start = time.monotonic()
        session = LLMSession(ctx)
        tctx = ctx.tool_context(view)
        researcher = initial_messages(view, self.cfg, "mas_researcher.md")
        research_tools = ctx.tools.subset(RESEARCH_TOOLS)
        attempts: list[Attempt] = []
        counts: Counter[str] = Counter()
        steps = 0
        status = "attempts_exhausted"
        error: str | None = None

        def chat(
            agent: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
        ) -> LLMResponse:
            nonlocal steps
            if steps >= ctx.limits.max_steps:
                raise StepLimitReached
            if ctx.deadline_passed:
                raise TimeoutError("task timeout exceeded")
            session.agent = agent
            response = session.chat(messages, tools, step=steps + 1)
            steps += 1
            return response

        try:
            while len(attempts) < ctx.limits.max_attempts:
                attempt_start = time.monotonic()
                # Исследователь выбирает инструменты до того, как сформулирует вывод.
                while True:
                    response = chat("researcher", researcher, research_tools.schemas())
                    researcher.append(response.assistant_message())
                    if not response.tool_calls:
                        finding = (response.content or "").strip()
                        break
                    for call in response.tool_calls:
                        counts[call.name] += 1
                        result = research_tools.call(call.name, call.arguments, tctx)
                        try:
                            args = json.loads(call.arguments)
                        except (json.JSONDecodeError, TypeError):
                            args = call.arguments
                        if isinstance(args, dict) and isinstance(args.get("code"), str):
                            args = {**args, "code": f"<{len(args['code'].splitlines())} lines>"}
                        ctx.tracer.emit(
                            "tool_call",
                            agent="researcher",
                            step=steps,
                            tool=call.name,
                            args=args,
                            result=result,
                        )
                        researcher.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": json.dumps(result, ensure_ascii=False),
                            }
                        )

                fixer = initial_messages(view, self.cfg, "mas_fixer.md")
                fixer.append(
                    {
                        "role": "user",
                        "content": render(load_prompt("mas_fix_request.md"), finding=finding),
                    }
                )
                response = chat("fixer", fixer)
                code = extract_code(response.content)
                if ctx.deadline_passed:
                    raise TimeoutError("task timeout exceeded")
                if code is None:
                    results = []
                    feedback = load_prompt("feedback_no_code.md")
                    note = "no_code_block"
                else:
                    # Только полный прогон исправленного кода считается сдачей.
                    counts["run_tests"] += 1
                    results = tctx.run_all(code)
                    feedback = format_test_report(
                        view.tests,
                        results,
                        self.cfg.initial_failing_shown,
                        self.cfg.show_expected_output,
                    )
                    ctx.tracer.emit(
                        "tool_call",
                        agent="checker",
                        step=steps,
                        tool="run_tests",
                        args={"code": f"<{len(code.splitlines())} lines>"},
                        result={"summary": summary_line(results)},
                    )
                    note = None
                verdicts = {r.name: r.verdict for r in results}
                passed = bool(results) and all(v == "AC" for v in verdicts.values())
                attempts.append(
                    Attempt(
                        index=len(attempts) + 1,
                        code=code,
                        verdicts=verdicts,
                        passed_all=passed,
                        usage=session.usage,
                        wall_time_s=round(time.monotonic() - attempt_start, 3),
                        note=note,
                    )
                )
                ctx.tracer.emit(
                    "attempt",
                    agent="checker",
                    step=steps,
                    result={
                        "index": len(attempts),
                        "passed_all": passed,
                        "summary": summary_line(results) if results else note,
                    },
                    usage=session.usage.short(),
                )
                if passed:
                    status = "solved"
                    break
                if len(attempts) >= ctx.limits.max_attempts:
                    break
                checker = [
                    {"role": "system", "content": load_prompt("mas_checker.md")},
                    {
                        "role": "user",
                        "content": render(
                            load_prompt("mas_check_request.md"),
                            code=code or "(code was not extracted)",
                            feedback=feedback,
                        ),
                    },
                ]
                explanation = (chat("checker", checker).content or "").strip()
                researcher.append(
                    {
                        "role": "user",
                        "content": render(
                            load_prompt("mas_recheck.md"),
                            feedback=feedback,
                            explanation=explanation,
                        ),
                    }
                )
        except StepLimitReached:
            status = "step_limit"
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
            steps=steps,
            tool_calls=dict(counts),
            error=error,
        )


@register_solver("mas_sequential")
def _make(cfg: ExperimentConfig) -> SequentialMASSolver:
    return SequentialMASSolver(cfg)
