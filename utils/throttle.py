import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)


def _get_env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _get_env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


class AdaptiveThrottle:
    def __init__(
        self,
        min_delay: float,
        max_delay: float,
        increase_step: float,
        decrease_step: float,
        cooldown_threshold: int,
    ):
        self.min_delay = max(0.0, min_delay)
        self.max_delay = max(self.min_delay, max_delay)
        self.increase_step = max(0.0, increase_step)
        self.decrease_step = max(0.0, decrease_step)
        self.cooldown_threshold = max(1, cooldown_threshold)
        self._delay = self.min_delay
        self._stable_count = 0
        self._next_time = 0.0
        self._wait_lock = asyncio.Lock()

    @property
    def delay(self) -> float:
        return self._delay

    async def wait(self) -> None:
        async with self._wait_lock:
            now = time.monotonic()
            if self._next_time > now:
                await asyncio.sleep(self._next_time - now)
            self._next_time = time.monotonic() + self._delay

    def on_success(self) -> None:
        if self._delay <= self.min_delay:
            return
        self._stable_count += 1
        if self._stable_count >= self.cooldown_threshold:
            self._delay = max(self.min_delay, self._delay - self.decrease_step)
            self._stable_count = 0

    def on_flood_wait(self, wait_seconds: Optional[int]) -> None:
        self._stable_count = 0
        if wait_seconds is None:
            return
        wait_seconds = max(0, int(wait_seconds))
        next_delay = max(self._delay, wait_seconds + 1)
        next_delay = max(next_delay, self._delay + self.increase_step)
        self._delay = min(self.max_delay, next_delay)

    def on_failure(self) -> None:
        self._stable_count = 0
        if self.increase_step > 0:
            self._delay = min(self.max_delay, self._delay + self.increase_step)


_REALTIME_THROTTLES = {}
_REALTIME_CONFIG = None


def _load_realtime_config():
    enabled = _get_env_bool("REALTIME_ADAPTIVE_THROTTLE", True)
    if not enabled:
        return None
    return {
        "min_delay": _get_env_float("REALTIME_THROTTLE_MIN_DELAY", 0.2),
        "max_delay": _get_env_float("REALTIME_THROTTLE_MAX_DELAY", 6.0),
        "increase_step": _get_env_float("REALTIME_THROTTLE_INCREASE_STEP", 0.5),
        "decrease_step": _get_env_float("REALTIME_THROTTLE_DECREASE_STEP", 0.2),
        "cooldown_threshold": _get_env_int("REALTIME_THROTTLE_COOLDOWN_THRESHOLD", 10),
    }


def get_realtime_throttle(name: str = "default"):
    global _REALTIME_CONFIG
    if _REALTIME_CONFIG is None:
        _REALTIME_CONFIG = _load_realtime_config()
    if _REALTIME_CONFIG is None:
        return None
    throttle = _REALTIME_THROTTLES.get(name)
    if throttle is None:
        throttle = AdaptiveThrottle(**_REALTIME_CONFIG)
        _REALTIME_THROTTLES[name] = throttle
    return throttle
