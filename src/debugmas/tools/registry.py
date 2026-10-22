"""Реестр инструментов для tool calling (docs/spec.md, раздел 6.4)."""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from debugmas.tools.context import ToolContext

BUILTIN_MODULES = ("run_tests", "get_test", "run_program", "trace", "submit")


class ToolArgumentError(ValueError):
    pass


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[[ToolContext, dict[str, Any]], dict[str, Any]]
    summarize: Callable[[dict[str, Any]], str]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


_TOOLS: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    _TOOLS[tool.name] = tool
    return tool


def _load_builtins() -> None:
    for mod in BUILTIN_MODULES:
        importlib.import_module(f"debugmas.tools.{mod}")


def available_tools() -> list[str]:
    _load_builtins()
    return sorted(_TOOLS)


_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


def _check_type(name: str, value: Any, spec: dict[str, Any]) -> None:
    t = spec.get("type")
    if t is None:
        return
    allowed = _JSON_TYPES[t]
    if isinstance(value, bool) and t in ("integer", "number"):
        raise ToolArgumentError(f"argument '{name}' must be {t}, got boolean")
    if not isinstance(value, allowed):
        raise ToolArgumentError(f"argument '{name}' must be {t}, got {type(value).__name__}")
    if t == "array" and "items" in spec:
        for i, item in enumerate(value):
            _check_type(f"{name}[{i}]", item, spec["items"])


def validate_args(tool: Tool, args: Any) -> dict[str, Any]:
    if not isinstance(args, dict):
        raise ToolArgumentError("arguments must be a JSON object")
    props: dict[str, Any] = tool.parameters.get("properties", {})
    for req in tool.parameters.get("required", []):
        if req not in args:
            raise ToolArgumentError(f"required argument '{req}' is missing")
    unknown = sorted(set(args) - set(props))
    if unknown:
        raise ToolArgumentError(
            f"unknown arguments: {', '.join(unknown)}; allowed: {', '.join(props)}"
        )
    for k, v in args.items():
        if v is None:
            continue
        _check_type(k, v, props[k])
    return {k: v for k, v in args.items() if v is not None}


def truncate_response(result: dict[str, Any], max_chars: int) -> dict[str, Any]:
    """Укорачивает самые длинные строковые поля, пока JSON не уложится в `max_chars`."""
    size = len(json.dumps(result, ensure_ascii=False))
    if size <= max_chars:
        return result
    data = json.loads(json.dumps(result, ensure_ascii=False))

    def leaves(node: Any, path: tuple[Any, ...] = ()) -> Iterable[tuple[tuple[Any, ...], str]]:
        if isinstance(node, dict):
            for k, v in node.items():
                yield from leaves(v, (*path, k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from leaves(v, (*path, i))
        elif isinstance(node, str):
            yield path, node

    def set_at(path: tuple[Any, ...], value: Any) -> None:
        node = data
        for p in path[:-1]:
            node = node[p]
        node[path[-1]] = value

    for _ in range(200):
        if len(json.dumps(data, ensure_ascii=False)) <= max_chars:
            break
        cands = sorted(leaves(data), key=lambda p: len(p[1]), reverse=True)
        if not cands or len(cands[0][1]) <= 60:
            # строки уже короткие — режем длинные списки
            lists = _longest_list(data)
            if lists is None:
                break
            path, lst = lists
            set_at(path, lst[: max(1, len(lst) // 2)])
            continue
        path, text = cands[0]
        set_at(path, text[: max(40, len(text) // 2)] + "…")
    data["truncated"] = True
    data["original_size"] = size
    return data


def _longest_list(
    node: Any, path: tuple[Any, ...] = ()
) -> tuple[tuple[Any, ...], list[Any]] | None:
    best: tuple[tuple[Any, ...], list[Any]] | None = None
    if isinstance(node, list) and len(node) > 1 and path:
        best = (path, node)
    if isinstance(node, dict):
        children: Iterable[tuple[Any, Any]] = node.items()
    elif isinstance(node, list):
        children = enumerate(node)
    else:
        children = []
    for k, v in children:
        sub = _longest_list(v, (*path, k))
        if sub and (best is None or len(sub[1]) > len(best[1])):
            best = sub
    return best


class ToolRegistry:
    """Набор включённых инструментов для одного решателя."""

    def __init__(self, names: Iterable[str]) -> None:
        _load_builtins()
        names = list(names)
        unknown = [n for n in names if n not in _TOOLS]
        if unknown:
            raise KeyError(f"Неизвестные инструменты: {unknown}; доступны: {sorted(_TOOLS)}")
        self.tools = {n: _TOOLS[n] for n in names}

    def names(self) -> list[str]:
        return list(self.tools)

    def subset(self, names: Iterable[str]) -> ToolRegistry:
        return ToolRegistry([n for n in names if n in self.tools])

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self.tools.values()]

    def call(self, name: str, raw_args: str | dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        """Ошибки возвращаются как результат `{"error": ...}`, а не исключением."""
        tool = self.tools.get(name)
        if tool is None:
            return {"error": f"unknown tool '{name}'; available: {self.names()}"}
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            if args is None:
                args = {}
        except json.JSONDecodeError as exc:
            return {"error": f"arguments are not valid JSON: {exc}"}
        try:
            args = validate_args(tool, args)
            result = tool.fn(ctx, args)
        except ToolArgumentError as exc:
            return {"error": f"argument error in {name}: {exc}"}
        except Exception as exc:  # noqa: BLE001 — инструмент не должен ронять решатель
            return {"error": f"execution error in {name}: {type(exc).__name__}: {exc}"}
        return truncate_response(result, ctx.max_chars)

    def summarize(self, name: str, result: dict[str, Any]) -> str:
        if "error" in result:
            return f"[{name} error — truncated]"
        tool = self.tools.get(name)
        body = tool.summarize(result) if tool else name
        return f"[{name} result: {body} — truncated]"
