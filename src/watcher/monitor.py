from __future__ import annotations

import logging
import threading
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from src.indexing.builder import IndexBuilder
from src.indexing.file_id import get_file_id
from src.storage.factory import GraphStore

logger = logging.getLogger(__name__)


class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, builder: IndexBuilder) -> None:
        self.builder = builder

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._handle(event.src_path, "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._handle(event.src_path, "modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._handle_delete(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        try:
            self.builder.relocate_file(event.src_path, event.dest_path)
        except Exception as e:
            logger.warning("移动回退为重建索引: %s", e)
            self._handle_delete(event.src_path)
            self._handle(event.dest_path, "moved")

    def _handle(self, path: str, kind: str) -> None:
        p = Path(path)
        if not p.is_file():
            return
        try:
            logger.info("[%s] 索引: %s", kind, path)
            self.builder.index_single(p)
        except Exception as e:
            logger.error("索引失败 %s: %s", path, e)

    def _handle_delete(self, path: str) -> None:
        from src.models.descriptor import FileStatus

        try:
            fid = get_file_id(path)
        except Exception:
            fid = f"ghost:{path}"
        logger.info("[deleted/archived] %s", path)
        node = self.builder.neo4j.get_file(fid)
        if node and hasattr(self.builder.neo4j, "patch_file"):
            self.builder.neo4j.patch_file(fid, {"status": FileStatus.ARCHIVED.value, "path": None})
        elif hasattr(self.builder.neo4j, "_nodes") and fid in getattr(self.builder.neo4j, "_nodes", {}):
            self.builder.neo4j._nodes[fid]["status"] = FileStatus.ARCHIVED.value
            self.builder.neo4j._nodes[fid]["path"] = None
        else:
            self.builder.neo4j.delete_file(fid)
            self.builder.chroma.delete_file(fid)


class FileWatcher:
    def __init__(self, roots: list[str], builder: IndexBuilder | None = None) -> None:
        self.roots = roots
        self.builder = builder or IndexBuilder()
        self._observer: Observer | None = None

    def start(self, blocking: bool = False) -> None:
        handler = FileChangeHandler(self.builder)
        self._observer = Observer()
        for root in self.roots:
            self._observer.schedule(handler, root, recursive=True)
        self._observer.start()
        logger.info("文件监控已启动: %s", self.roots)
        if blocking:
            try:
                self._observer.join()
            except KeyboardInterrupt:
                self.stop()

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
