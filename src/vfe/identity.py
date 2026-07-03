"""VFE 持久标识：SHA256(inode + first_seen)，含 inode 复用与跨卷移动回退。"""
from __future__ import annotations

import hashlib
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any

from src.config import settings


def get_inode_key(path: str | Path) -> str:
    """卷级 inode 键（与物理路径无关）。"""
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(path)
    if sys.platform == "win32":
        from src.indexing.file_id import _windows_file_id

        return _windows_file_id(p)
    st = os.stat(p)
    return f"{st.st_dev}:{st.st_ino}"


def compute_vfe_id(inode_key: str, first_seen_ts: float, *, salt: str = "") -> str:
    """规格 2.1.1：id = SHA256(inode_bytes + first_seen_timestamp_bytes [+ salt])。 """
    payload = f"{inode_key}|{int(first_seen_ts)}|{salt}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def content_hash_prefix(path: str | Path, *, nbytes: int = 1024) -> str:
    p = Path(path)
    if not p.is_file():
        return ""
    h = hashlib.sha256()
    with p.open("rb") as f:
        h.update(f.read(nbytes))
    return h.hexdigest()[:16]


def content_hash_full(path: str | Path) -> str:
    p = Path(path)
    if not p.is_file():
        return ""
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_vfe_identity(
    path: str | Path,
    graph: Any | None = None,
    *,
    id_mode: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    解析或创建 VFE 身份。
    返回 (file_id, metadata_updates)。
    """
    mode = id_mode or getattr(settings, "vfe_id_mode", "sha256")
    p = Path(path).resolve()
    inode_key = get_inode_key(p)
    now = time.time()

    if mode == "volume":
        return inode_key, {"inode_key": inode_key, "first_seen_ts": now}

    # sha256 模式
    meta: dict[str, Any] = {"inode_key": inode_key}

    if graph is not None:
        existing = _find_by_inode(graph, inode_key)
        if existing:
            fid = existing.get("file_id") or existing.get("id")
            if fid:
                return str(fid), meta

        archived = _find_archived_by_inode(graph, inode_key)
        if archived:
            prefix = content_hash_prefix(p)
            old_prefix = (archived.get("metadata") or {}).get("content_hash_prefix", "")
            if old_prefix and prefix == old_prefix:
                fid = archived["file_id"]
                return fid, {
                    **meta,
                    "restore_archived": True,
                    "content_hash_prefix": prefix,
                }

    first_seen = now
    candidate = compute_vfe_id(inode_key, first_seen)

    if graph is not None and _id_exists(graph, candidate):
        archived = graph.get_file(candidate) if hasattr(graph, "get_file") else None
        if archived and archived.get("status") == "ARCHIVED":
            prefix = content_hash_prefix(p)
            old_prefix = (archived.get("metadata") or {}).get("content_hash_prefix", "")
            if old_prefix and prefix != old_prefix:
                salt = secrets.token_hex(8)
                candidate = compute_vfe_id(inode_key, first_seen, salt=salt)
                meta["inode_conflict"] = True
                meta["salt"] = salt
            else:
                meta["restore_archived"] = True
        elif archived:
            salt = secrets.token_hex(8)
            candidate = compute_vfe_id(inode_key, first_seen, salt=salt)
            meta["inode_conflict"] = True
            meta["salt"] = salt

    meta["first_seen_ts"] = first_seen
    meta["content_hash_prefix"] = content_hash_prefix(p)
    meta["content_hash"] = content_hash_full(p)

    if graph is not None:
        dup = _find_active_by_content_hash(graph, meta["content_hash"], exclude_path=str(p))
        if dup:
            meta["duplicate_of"] = dup

    return candidate, meta


def _iter_nodes(graph: Any):
    if hasattr(graph, "_nodes"):
        yield from graph._nodes.items()
        return
    for rec in graph.list_all_files():
        fid = rec.get("file_id")
        if fid:
            yield fid, graph.get_file(fid) or rec


def _find_by_inode(graph: Any, inode_key: str) -> dict | None:
    for _, node in _iter_nodes(graph):
        md = node.get("metadata") or {}
        if md.get("inode_key") == inode_key and node.get("status") not in ("ARCHIVED", "GHOST"):
            return node
        if node.get("file_id") == inode_key:
            return node
    return None


def _find_archived_by_inode(graph: Any, inode_key: str) -> dict | None:
    for _, node in _iter_nodes(graph):
        if node.get("status") != "ARCHIVED":
            continue
        md = node.get("metadata") or {}
        if md.get("inode_key") == inode_key:
            return node
    return None


def _find_active_by_content_hash(
    graph: Any, content_hash: str, *, exclude_path: str = ""
) -> str | None:
    for fid, node in _iter_nodes(graph):
        if node.get("status") not in ("ACTIVE", "DORMANT"):
            continue
        if (node.get("path") or "") == exclude_path:
            continue
        md = node.get("metadata") or {}
        if md.get("content_hash") == content_hash:
            return fid
    return None


def _id_exists(graph: Any, fid: str) -> bool:
    if hasattr(graph, "get_file"):
        return graph.get_file(fid) is not None
    return False
