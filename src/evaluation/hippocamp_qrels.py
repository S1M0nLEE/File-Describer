"""从 HippoCamp 条目提取标注文件名（与 download_real_benchmarks 一致）。"""

from __future__ import annotations

from pathlib import Path


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
