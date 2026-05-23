"""全局加载进度（供前端轮询）。"""

from __future__ import annotations

import threading
from typing import Any, Callable

_lock = threading.Lock()
_state: dict[str, Any] = {
    "state": "idle",  # idle | running | done | error
    "percent": 0,
    "stage": "",
    "message": "尚未加载全局索引",
    "current": 0,
    "total": 0,
}


def snapshot() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def reset_idle(message: str = "尚未加载全局索引") -> None:
    with _lock:
        _state.update(
            {
                "state": "idle",
                "percent": 0,
                "stage": "idle",
                "message": message,
                "current": 0,
                "total": 0,
            }
        )


def set_running(stage: str, message: str, percent: int) -> None:
    with _lock:
        _state.update(
            {
                "state": "running",
                "stage": stage,
                "message": message,
                "percent": max(0, min(100, percent)),
            }
        )


def set_counter(current: int, total: int, message: str | None = None) -> None:
    with _lock:
        _state["current"] = current
        _state["total"] = total
        if message:
            _state["message"] = message
        if total > 0:
            # 语料阶段占 75–99%
            frac = min(1.0, current / total)
            _state["percent"] = max(_state.get("percent", 75), int(75 + frac * 24))


def set_done(message: str = "全局索引已就绪") -> None:
    with _lock:
        _state.update(
            {
                "state": "done",
                "percent": 100,
                "stage": "done",
                "message": message,
            }
        )


def set_error(message: str) -> None:
    with _lock:
        _state.update(
            {
                "state": "error",
                "stage": "error",
                "message": message,
            }
        )


ProgressCallback = Callable[[int, int, str], None]


def make_corpus_callback() -> ProgressCallback:
    def cb(current: int, total: int, message: str) -> None:
        set_counter(current, total, message)

    return cb
