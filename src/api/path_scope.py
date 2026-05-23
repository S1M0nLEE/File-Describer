"""区分本机用户目录索引与项目内评测/样例数据集路径。"""
from __future__ import annotations

from pathlib import Path

from src.config import settings


def is_benchmark_path(path: str | None) -> bool:
    if not path:
        return False
    p = Path(path).as_posix().lower()
    root = settings.data_dir.resolve().as_posix().lower()
    markers = (
        f"{root}/benchmarks/",
        f"{root}/dataset/",
        "/data/benchmarks/",
        "/data/dataset/",
        "/evaluation/",
        "/noise/",
    )
    return any(m in p for m in markers)


def is_under_user_profile(path: str | None) -> bool:
    if not path:
        return False
    try:
        return Path(path).resolve().is_relative_to(Path.home().resolve())
    except (OSError, ValueError):
        return False
