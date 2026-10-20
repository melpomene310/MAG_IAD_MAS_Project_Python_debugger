"""Общий интерфейс решателей (docs/spec.md, раздел 8.3)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from debugmas.config import ExperimentConfig
from debugmas.data.schema import AgentView
from debugmas.experiment.tracing import TaskTracer
from debugmas.llm.client import ChatModel, LLMError, LLMResponse
from debugmas.llm.usage import Usage
from debugmas.tools.context import ToolContext
from debugmas.tools.registry import ToolRegistry

STATUSES = ("solved", "attempts_exhausted", "step_limit", "token_limit", "error")


@dataclass
class Attempt:
    index: int
    code: str | None
    verdicts: dict[str, str]
    passed_all: bool
    usage: Usage
    wall_time_s: float
    note: str | None = None  # например «блок кода не найден», «синтаксическая ошибка»

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["usage"] = self.usage.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Attempt:
        d = dict(d)
        d["usage"] = Usage.from_dict(d.get("usage"))
        return cls(**d)


@dataclass
class SolverResult:
    task_id: str
    solver: str
    status: str
    attempts: list[Attempt]
    final_code: str | None
    usage: Usage
    wall_time_s: float
    llm_time_s: float
    sandbox_time_s: float
    steps: int
    tool_calls: dict[str, int]
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["usage"] = self.usage.to_dict()
        d["attempts"] = [a.to_dict() for a in self.attempts]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SolverResult:
        d = dict(d)
        d["usage"] = Usage.from_dict(d.get("usage"))
        d["attempts"] = [Attempt.from_dict(a) for a in d.get("attempts", [])]
        return cls(**d)


@dataclass
class SolverLimits:
    max_attempts: int = 3
    max_steps: int = 30
    max_tokens_per_task: int = 300_000
    task_timeout_s: float = 1800.0


@dataclass
class RunContext:
    llm: ChatModel
    tools: ToolRegistry
    limits: SolverLimits
    tracer: TaskTracer
    config: ExperimentConfig
    started: float = field(default_factory=time.monotonic)

    @property
    def deadline_passed(self) -> bool:
        return time.monotonic() - self.started > self.limits.task_timeout_s

    def tool_context(self, view: AgentView) -> ToolContext:
        cfg = self.config
        return ToolContext(
            view=view,
            failing_shown=cfg.tool_failing_shown,
            show_expected=cfg.show_expected_output,
            max_chars=cfg.tool_response_max_chars,
            memory_mb=cfg.memory_mb,
            workers=cfg.sandbox_workers,
            trace_max_hits=cfg.trace_max_hits,
            max_submissions=self.limits.max_attempts,
        )


class Solver(Protocol):
    name: str

    def solve(self, view: AgentView, ctx: RunContext) -> SolverResult: ...


SOLVERS: dict[str, Callable[[ExperimentConfig], Solver]] = {}


def register_solver(name: str) -> Callable[[Callable[..., Solver]], Callable[..., Solver]]:
    def deco(factory: Callable[..., Solver]) -> Callable[..., Solver]:
        SOLVERS[name] = factory
        return factory

    return deco


def make_solver(name: str, cfg: ExperimentConfig) -> Solver:
    import debugmas.solvers  # noqa: F401 — регистрирует встроенные решатели

    if name not in SOLVERS:
        raise KeyError(f"Неизвестный решатель '{name}'; доступны: {sorted(SOLVERS)}")
    return SOLVERS[name](cfg)


class TokenLimitReached(RuntimeError):
    pass


class LLMSession:
    """Обёртка над вызовами модели: суммирует usage (вкл. неудачные), время, пишет трассу."""

    def __init__(self, ctx: RunContext, agent: str | None = None) -> None:
        self.ctx = ctx
        self.agent = agent
        self.usage = Usage()
        self.llm_time_s = 0.0
        self.calls = 0

    def check_budget(self) -> None:
        if self.usage.total >= self.ctx.limits.max_tokens_per_task:
            raise TokenLimitReached(
                f"израсходовано {self.usage.total} токенов "
                f"(лимит {self.ctx.limits.max_tokens_per_task})"
            )

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        step: int | None = None,
    ) -> LLMResponse:
        self.check_budget()
        start = time.monotonic()
        try:
            resp = self.ctx.llm.chat(messages, tools)
        except LLMError as exc:
            self.usage = self.usage + exc.usage
            self.ctx.tracer.emit(
                "llm_error", agent=self.agent, step=step, error=str(exc), usage=exc.usage.short()
            )
            raise
        elapsed = time.monotonic() - start
        self.calls += 1
        self.usage = self.usage + resp.usage
        if not resp.cache_hit:
            self.llm_time_s += elapsed
        self.ctx.tracer.emit(
            "llm_call",
            agent=self.agent,
            step=step,
            result={
                "content": resp.content,
                "tool_calls": [tc.to_dict()["function"] for tc in resp.tool_calls],
                "finish_reason": resp.finish_reason,
            },
            usage=resp.usage.short(),
            cache_hit=resp.cache_hit,
            latency_s=round(resp.latency_s, 3),
        )
        return resp
