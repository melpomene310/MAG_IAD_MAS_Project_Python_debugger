"""Ограничения ресурсов для процесса песочницы (выполняются в дочернем процессе до exec)."""

from __future__ import annotations

import math
import os
import resource
from collections.abc import Callable
from dataclasses import dataclass

NOBODY_UID = 65534
NOBODY_GID = 65534


@dataclass(frozen=True)
class Limits:
    time_limit_s: float = 2.0  # лимит теста (вердикт TLE)
    memory_mb: int = 1024
    file_size_mb: int = 64  # включая stdout/stderr (пишутся в файлы)
    max_processes: int = 256  # RLIMIT_NPROC считает и потоки
    wall_factor: float = 1.5  # таймаут по реальному времени = limit × factor + 0.5 с

    @property
    def wall_timeout_s(self) -> float:
        return self.time_limit_s * self.wall_factor + 0.5

    @property
    def cpu_seconds(self) -> int:
        return int(math.ceil(self.time_limit_s * self.wall_factor)) + 1


def make_preexec(limits: Limits) -> Callable[[], None]:
    def _apply() -> None:
        mem = limits.memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds + 1))
        fsize = limits.file_size_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        # Под root (в контейнере) понижаем привилегии: иначе RLIMIT_NPROC не действует,
        # а программа могла бы писать в /app.
        # RLIMIT_NPROC считается по пользователю, поэтому ставится только для nobody:
        # у обычного пользователя хоста уже могут быть сотни процессов и потоков.
        if os.geteuid() == 0:
            os.setgroups([])
            os.setgid(NOBODY_GID)
            os.setuid(NOBODY_UID)
            nproc = limits.max_processes
            resource.setrlimit(resource.RLIMIT_NPROC, (nproc, nproc))

    return _apply
