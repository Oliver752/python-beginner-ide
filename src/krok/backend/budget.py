"""Limity záznamu: počet krokov, čas a pamäť procesu."""

import time

import psutil

from krok.common.trace import Limits

# Zistenie pamäte procesu je systémové volanie, stačí občas.
_MEMORY_CHECK_INTERVAL = 0.05


class Budget:
    def __init__(self, limits: Limits) -> None:
        self._max_steps = limits.steps
        self._process = psutil.Process()
        # Limit sa týka toho, čo záznam a program pridržia, nie samotného interpretera.
        self._max_rss = self._rss() + limits.memory_mb * 1024 * 1024
        self._started = time.monotonic()
        self._deadline = self._started + limits.seconds
        self._excluded = 0.0
        self._next_memory_check = self._started

    def exclude(self, seconds: float) -> None:
        """Čas, keď program čakal na študenta, sa do limitu nepočíta."""
        self._deadline += seconds
        self._excluded += seconds

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._started - self._excluded) * 1000)

    def exceeded(self, steps: int) -> str | None:
        """Názov prekročeného limitu pre pole status stopy, inak None."""
        if steps >= self._max_steps:
            return "step_limit"
        now = time.monotonic()
        if now > self._deadline:
            return "time_limit"
        if now >= self._next_memory_check:
            self._next_memory_check = now + _MEMORY_CHECK_INTERVAL
            if self._rss() > self._max_rss:
                return "memory_limit"
        return None

    def _rss(self) -> int:
        return self._process.memory_info().rss
