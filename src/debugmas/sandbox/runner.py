"""Единственная точка запуска чужого кода (docs/spec.md, раздел 6.1)."""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from debugmas.data.schema import TestCase, TestResult
from debugmas.sandbox.compare import judge
from debugmas.sandbox.limits import Limits, make_preexec

log = logging.getLogger(__name__)

STORE_LIMIT_BYTES = 64 * 1024
PROGRAM_FILE = "main.py"
_DEFAULT_PYTHON = "/usr/local/bin/python"
_MEMORY_MARKERS = ("MemoryError", "Cannot allocate memory", "std::bad_alloc")


def sandbox_python() -> str:
    from debugmas.config import Settings

    return Settings().sandbox_python or _DEFAULT_PYTHON


@dataclass
class RunResult:
    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool
    memory_exceeded: bool
    wall_time: float

    def to_dict(self, max_bytes: int = STORE_LIMIT_BYTES) -> dict[str, Any]:
        d = asdict(self)
        d["stdout"] = truncate_text(self.stdout, max_bytes)
        d["stderr"] = truncate_text(self.stderr, max_bytes)
        return d


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...[обрезано, всего {len(text)} символов]"


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="replace")


def execute(
    files: dict[str, str],
    entry: str,
    stdin: str | bytes,
    limits: Limits,
    python: str | None = None,
) -> RunResult:
    """Запуск `entry` из временной папки с файлами `files` в отдельном процессе `python -I`."""
    python = python or sandbox_python()
    workdir = Path(tempfile.mkdtemp(prefix="dbgmas_run_"))
    iodir = Path(tempfile.mkdtemp(prefix="dbgmas_io_"))
    try:
        os.chmod(workdir, 0o777)
        for name, content in files.items():
            p = workdir / name
            p.write_text(content, encoding="utf-8")
            os.chmod(p, 0o644)
        data = stdin.encode("utf-8") if isinstance(stdin, str) else stdin
        (iodir / "stdin").write_bytes(data)
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "HOME": str(workdir),
        }
        with (
            open(iodir / "stdin", "rb") as fin,
            open(iodir / "stdout", "wb") as fout,
            open(iodir / "stderr", "wb") as ferr,
        ):
            start = time.monotonic()
            proc = subprocess.Popen(
                [python, "-I", entry],
                cwd=workdir,
                env=env,
                stdin=fin,
                stdout=fout,
                stderr=ferr,
                preexec_fn=make_preexec(limits),
                start_new_session=True,
                close_fds=True,
            )
            timed_out = False
            try:
                proc.wait(timeout=limits.wall_timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_group(proc)
                proc.wait()
            wall = time.monotonic() - start
            _kill_group(proc)  # добиваем оставшихся потомков
        stdout = _read(iodir / "stdout")
        stderr = _read(iodir / "stderr")
        code = proc.returncode
        if code in (-signal.SIGXCPU, -signal.SIGKILL) and not timed_out:
            # SIGXCPU — превышен RLIMIT_CPU
            timed_out = wall > limits.time_limit_s or code == -signal.SIGXCPU
        if wall > limits.time_limit_s:
            timed_out = True
        memory_exceeded = code != 0 and any(m in stderr for m in _MEMORY_MARKERS)
        return RunResult(stdout, stderr, code, timed_out, memory_exceeded, round(wall, 4))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        shutil.rmtree(iodir, ignore_errors=True)


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run_program(
    code: str,
    stdin: str | bytes,
    time_limit_s: float = 2.0,
    memory_mb: int = 1024,
    python: str | None = None,
) -> RunResult:
    return execute(
        {PROGRAM_FILE: code},
        PROGRAM_FILE,
        stdin,
        Limits(time_limit_s=time_limit_s, memory_mb=memory_mb),
        python,
    )


def run_test(
    code: str, test: TestCase, memory_mb: int = 1024, python: str | None = None
) -> tuple[TestResult, RunResult]:
    res = run_program(code, test.input_path.read_bytes(), test.time_limit_s, memory_mb, python)
    verdict = judge(res, test.read_expected())
    tr = TestResult(
        name=test.name,
        verdict=verdict,
        stdout=truncate_text(res.stdout, STORE_LIMIT_BYTES),
        stderr=truncate_text(res.stderr, STORE_LIMIT_BYTES),
        exit_code=res.exit_code,
        wall_time=res.wall_time,
        timed_out=res.timed_out,
        memory_exceeded=res.memory_exceeded,
    )
    return tr, res


def run_tests(
    code: str,
    tests: Sequence[TestCase],
    workers: int = 8,
    memory_mb: int = 1024,
    python: str | None = None,
) -> list[TestResult]:
    """Прогон всех тестов параллельно; порядок результатов совпадает с порядком тестов."""
    if not tests:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(tests)))) as pool:
        futures = [pool.submit(run_test, code, t, memory_mb, python) for t in tests]
        return [f.result()[0] for f in futures]
