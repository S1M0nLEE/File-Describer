from __future__ import annotations

import json
import logging
import os
import platform
from datetime import datetime
from pathlib import Path

from src.config import settings

logger = logging.getLogger(__name__)


class WorkflowCollector:
    """
    方案 4.2.7：本地行为流水采集。
    - 应用内打开/检索时写入 jsonl
    - Windows：可选解析 ETW 导出（用户自备 CSV）
    - macOS/Linux：可解析 fs_usage 文本导出
  """

    def __init__(self, log_path: Path | None = None) -> None:
        settings.ensure_dirs()
        self.log_path = log_path or (settings.data_dir / "workflow_log.jsonl")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._session: list[str] = []
        self._session_paths: list[str] = []

    def record_open(self, path: str | Path, *, event: str = "open") -> None:
        if not settings.workflow_collection_enabled:
            return
        path = str(Path(path).resolve())
        entry = {
            "path": path,
            "event": event,
            "ts": datetime.utcnow().isoformat(),
            "pid": os.getpid(),
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if event == "session_end":
            self._session.clear()
            self._session_paths.clear()
        else:
            if not self._session_paths or self._session_paths[-1] != path:
                self._session_paths.append(path)

    def end_session(self) -> None:
        self.record_open("", event="session_end")

    def import_etw_csv(self, csv_path: Path) -> int:
        """导入 Windows ETW/Procmon 导出 CSV（列含 Path 与 Time）。"""
        if not csv_path.exists():
            return 0
        count = 0
        try:
            import csv

            with csv_path.open(encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    path = row.get("Path") or row.get("path") or ""
                    if path and Path(path).is_file():
                        self.record_open(path)
                        count += 1
        except Exception as e:
            logger.warning("ETW CSV 导入失败: %s", e)
        return count

    def import_fs_usage_log(self, log_path: Path) -> int:
        """解析 fs_usage 文本行中的文件路径。"""
        if not log_path.exists():
            return 0
        count = 0
        for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            for token in line.split():
                if "/" in token or "\\" in token:
                    p = Path(token.strip("'\""))
                    if p.is_file():
                        self.record_open(p)
                        count += 1
                        break
        return count

    @staticmethod
    def try_background_windows_recent() -> int:
        """尽力从 Recent 目录推断最近打开（无需管理员）。"""
        if platform.system() != "Windows":
            return 0
        recent = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Recent"
        if not recent.is_dir():
            return 0
        coll = WorkflowCollector()
        n = 0
        for lnk in sorted(recent.glob("*.lnk"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
            coll.record_open(lnk)
            n += 1
        return n
