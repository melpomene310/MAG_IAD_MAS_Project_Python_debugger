"""Скрипт-обёртка трассировки. Выполняется ВНУТРИ песочницы интерпретатором SANDBOX_PYTHON.

Не импортирует ничего из debugmas: копируется во временную папку рядом с main.py.
Конфиг читается из trace_config.json; срабатывания пишутся в копию дескриптора stderr
строками с маркером, чтобы при таймауте собранные значения сохранились.
"""

import json
import os
import sys
import threading
import traceback

REPR_LIMIT = 200

with open("trace_config.json", encoding="utf-8") as _f:
    CFG = json.load(_f)

_OUT_FD = os.dup(2)
MARKER = CFG["marker"]
TARGET = os.path.abspath(CFG.get("program", "main.py"))
LINES = set(CFG["lines"])
EXPRESSIONS = list(CFG["expressions"])
MAX_HITS = int(CFG["max_hits"])

_lock = threading.Lock()
_counts = {}
_state = {"total": 0, "done": False}


def _emit(record):
    os.write(_OUT_FD, (MARKER + json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))


def _short(text):
    return text if len(text) <= REPR_LIMIT else text[:REPR_LIMIT] + "..."


def _safe_repr(value):
    try:
        return _short(repr(value))
    except BaseException as exc:  # noqa: BLE001
        return f"<repr error: {type(exc).__name__}>"


def _local(frame, event, arg):
    if _state["done"]:
        return None
    if event == "line" and frame.f_lineno in LINES:
        line = frame.f_lineno
        with _lock:
            if _state["total"] >= MAX_HITS:
                _state["done"] = True
                return None
            _state["total"] += 1
            _counts[line] = _counts.get(line, 0) + 1
            hit = _counts[line]
        values = {}
        for expr in EXPRESSIONS:
            try:
                values[expr] = _safe_repr(eval(expr, frame.f_globals, frame.f_locals))
            except BaseException as exc:  # noqa: BLE001
                values[expr] = _short(f"<{type(exc).__name__}: {exc}>")
        _emit(
            {"line": line, "hit": hit, "thread": threading.current_thread().name, "values": values}
        )
    return _local


def _global(frame, event, arg):
    if _state["done"] or frame.f_code.co_filename != TARGET:
        return None
    return _local


def main():
    with open(TARGET, encoding="utf-8") as f:
        source = f.read()
    code = compile(source, TARGET, "exec")
    namespace = {"__name__": "__main__", "__file__": TARGET, "__builtins__": __builtins__}
    sys.argv = [TARGET]
    status, exit_code = "finished", 0
    threading.settrace(_global)
    sys.settrace(_global)
    try:
        exec(code, namespace)
        for t in threading.enumerate():
            if t is not threading.main_thread() and not t.daemon:
                t.join()
    except SystemExit as exc:
        status = "exit"
        if exc.code is None:
            exit_code = 0
        elif isinstance(exc.code, int):
            exit_code = exc.code
        else:
            print(exc.code, file=sys.stderr)
            exit_code = 1
    except BaseException as exc:  # noqa: BLE001
        status = "exception"
        exit_code = 1
        # tb_next: без кадра самой обёртки
        traceback.print_exception(type(exc), exc, exc.__traceback__.tb_next)
    finally:
        sys.settrace(None)
        threading.settrace(None)
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except BaseException:  # noqa: BLE001
        pass
    _emit(
        {
            "end": status,
            "exit_code": exit_code,
            "total_hits": _state["total"],
            "max_hits_reached": _state["done"],
        }
    )
    os._exit(exit_code)


main()
