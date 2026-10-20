"""Папка результатов запуска (docs/spec.md, раздел 10.1)."""

from __future__ import annotations

import json
import platform
import subprocess
import threading
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from debugmas.solvers.base import SolverResult


def git_info(cwd: Path | None = None) -> dict[str, Any]:
    def _git(*args: str) -> str | None:
        try:
            return subprocess.run(
                ["git", "-c", "safe.directory=*", *args],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    commit = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    return {"commit": commit, "dirty": bool(status) if status is not None else None}


def _version(pkg: str) -> str | None:
    try:
        return metadata.version(pkg)
    except metadata.PackageNotFoundError:
        return None


def build_meta(run_id: str, llm: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "git": git_info(),
        "model": llm.get("model"),
        "endpoint_host": urlparse(llm.get("base_url") or "").netloc,
        "fake_llm": llm.get("fake", False),
        "versions": {
            "python": platform.python_version(),
            "debugmas": _version("debugmas"),
            "openai": _version("openai"),
        },
        "started": datetime.now(UTC).isoformat(),
        "finished": None,
        **extra,
    }


class RunDir:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / "candidates").mkdir(exist_ok=True)
        self._lock = threading.Lock()

    @property
    def tasks_path(self) -> Path:
        return self.path / "tasks.jsonl"

    @property
    def trace_path(self) -> Path:
        return self.path / "trace.jsonl"

    def done_task_ids(self) -> set[str]:
        if not self.tasks_path.exists():
            return set()
        done = set()
        with open(self.tasks_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    done.add(json.loads(line)["task_id"])
                except (json.JSONDecodeError, KeyError):
                    continue  # оборванная строка при прерывании
        return done

    def write_config(self, cfg: dict[str, Any]) -> None:
        with open(self.path / "config.resolved.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)

    def read_meta(self) -> dict[str, Any] | None:
        p = self.path / "meta.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def write_meta(self, meta: dict[str, Any]) -> None:
        (self.path / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    def append_result(self, res: SolverResult) -> None:
        cdir = self.path / "candidates" / res.task_id
        for a in res.attempts:
            if a.code is not None:
                cdir.mkdir(parents=True, exist_ok=True)
                (cdir / f"attempt_{a.index}.py").write_text(a.code, encoding="utf-8")
        line = json.dumps(res.to_dict(), ensure_ascii=False)
        with self._lock, open(self.tasks_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
