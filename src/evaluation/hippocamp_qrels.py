"""从 HippoCamp 条目提取标注文件名（与 download_real_benchmarks 一致）。"""

from __future__ import annotations

from pathlib import Path


def split_direct_indirect(item: dict, *, max_direct: int = 3) -> tuple[list[str], list[str]]:
    """将 HippoCamp 条目拆分为 direct（主证据）与 indirect（支撑证据）。"""
    all_files = extract_hippocamp_files(item)
    primary: list[str] = []
    top = item.get("file_path")
    if isinstance(top, list):
        primary = _basename_paths([str(x) for x in top])
    elif isinstance(top, str) and top.strip():
        primary = _basename_paths([top])

    if primary:
        direct = primary[:max_direct]
        indirect = [f for f in all_files if f not in set(direct)]
    elif all_files:
        direct = all_files[:1]
        indirect = all_files[1:]
    else:
        direct, indirect = [], []
    return direct, indirect


def extract_hippocamp_files(item: dict) -> list[str]:
    names: list[str] = []
    top = item.get("file_path")
    if isinstance(top, list):
        names.extend(_basename_paths([str(x) for x in top]))
    elif isinstance(top, str) and top.strip():
        names.extend(_basename_paths([top]))
    for ev in item.get("evidence") or []:
        if not isinstance(ev, dict):
            continue
        fp = ev.get("file_path") or ev.get("path") or ev.get("file_name") or ""
        if fp:
            names.extend(_basename_paths([str(fp)]))
    return list(dict.fromkeys(names))


def _basename_paths(paths: list[str]) -> list[str]:
    out: list[str] = []
    for p in paths:
        if not p:
            continue
        name = Path(str(p).replace("\\", "/")).name
        if name and name not in out:
            out.append(name)
    return out
