#!/usr/bin/env python3
"""为评测基准注入合成行为日志（WORKFLOW_WITH 前置条件）。"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SESSIONS = [
    ["data_processing.py", "实验数据.csv", "data_visualization.ipynb.md", "图表1.png.md"],
    ["论文_v1.docx.md", "参考文献.bib", "论文_v2.docx.md", "论文终稿.pdf.md"],
    ["账单.xlsx.md", "发票扫描.jpg.md", "合同_v1.docx.md", "合同终稿.pdf.md"],
    ["main.py", "service.py", "models.py", "utils.py", "app/main.py", "app/service.py"],
]


def inject_for_dataset(ds_path: Path, log_path: Path, *, repeats: int = 8) -> int:
    """为单个基准目录写入行为日志；重复会话以满足 min_support。"""
    count = 0
    t0 = time.time() - 86400 * 14
    lines: list[str] = []
    for rep in range(repeats):
        for si, session in enumerate(SESSIONS):
            base_t = t0 + rep * 7200 + si * 3600
            session_hits = 0
            for fi, name in enumerate(session):
                hits = list(ds_path.rglob(name))
                if not hits:
                    continue
                path = str(hits[0].resolve())
                ts = datetime.fromtimestamp(base_t + fi * 120, tz=timezone.utc).isoformat()
                lines.append(
                    json.dumps({"path": path, "event": "open", "ts": ts, "pid": 0}, ensure_ascii=False)
                )
                session_hits += 1
                count += 1
            if session_hits >= 2:
                lines.append(json.dumps({"event": "session_end"}, ensure_ascii=False))
    if lines:
        with log_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return count


def main() -> None:
    from src.config import settings

    settings.ensure_dirs()
    log_path = settings.data_dir / "workflow_log.jsonl"
    log_path.write_text("", encoding="utf-8")
    total = 0
    for rel in ("data/benchmarks/filekg_main", "data/benchmarks/personal_mixed", "data/benchmarks/code_dependency"):
        p = ROOT / rel
        if p.is_dir():
            n = inject_for_dataset(p, log_path)
            print(f"{rel}: 注入 {n} 条行为事件")
            total += n
    print(f"日志: {log_path}  合计 {total} 条")


if __name__ == "__main__":
    main()
