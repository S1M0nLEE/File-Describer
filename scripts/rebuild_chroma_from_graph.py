#!/usr/bin/env python3
"""从 graph_store 重建 Chroma 向量库（索引损坏时使用）。"""
from __future__ import annotations

import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import settings  # noqa: E402
from src.indexing.embedder import Embedder  # noqa: E402
from src.models.descriptor import FileDescriptor, FileStatus  # noqa: E402
from src.storage.chroma_store import ChromaStore  # noqa: E402
from src.storage.factory import create_stores  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH = 64


def main() -> None:
    os.environ["FILEKG_INDEX_FAST"] = "1"
    os.environ["FILEKG_LLM_ENABLED"] = "false"
    settings.llm_enabled = False

    chroma_dir = Path(settings.chroma_dir)
    if chroma_dir.exists():
        logger.info("删除损坏的 Chroma 目录: %s", chroma_dir)
        shutil.rmtree(chroma_dir, ignore_errors=True)

    graph, _ = create_stores()
    chroma = ChromaStore()
    ChromaStore._broken = False
    embedder = Embedder.get()

    files = graph.list_all_files()
    logger.info("待重建向量: %d 个文件", len(files))

    batch: list[FileDescriptor] = []
    done = 0
    for rec in files:
        fid = rec.get("file_id")
        if not fid:
            continue
        node = graph.get_file(fid) or {}
        path = node.get("path") or ""
        name = node.get("name") or fid
        text = " ".join(
            x
            for x in (
                node.get("summary") or "",
                node.get("ai_summary") or "",
                name,
            )
            if x
        ).strip() or name
        try:
            mtime = datetime.fromisoformat(str(node.get("modified_time") or ""))
        except (ValueError, TypeError):
            mtime = datetime.utcnow()
        try:
            ctime = datetime.fromisoformat(str(node.get("created_time") or ""))
        except (ValueError, TypeError):
            ctime = mtime

        desc = FileDescriptor(
            file_id=fid,
            path=path,
            name=name,
            extension=node.get("extension") or Path(name).suffix.lower(),
            size=int(node.get("size") or 0),
            created_time=ctime,
            modified_time=mtime,
            summary=node.get("summary") or "",
            ai_summary=node.get("ai_summary") or "",
            status=FileStatus(node.get("status") or "ACTIVE"),
            file_embedding=embedder.embed(text),
        )
        batch.append(desc)
        if len(batch) >= BATCH:
            for d in batch:
                chroma.upsert_file(d)
            done += len(batch)
            logger.info("  已写入 %d / %d", done, len(files))
            batch.clear()

    if batch:
        for d in batch:
            chroma.upsert_file(d)
        done += len(batch)

    logger.info("完成，共 %d 条。请重启 Web 服务。", done)


if __name__ == "__main__":
    main()
