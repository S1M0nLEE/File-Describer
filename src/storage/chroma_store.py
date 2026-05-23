from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.errors import InternalError, NotFoundError
from chromadb.config import Settings as ChromaSettings

from src.config import settings
from src.models.descriptor import FileDescriptor

logger = logging.getLogger(__name__)

COLLECTION_FILES = "file_embeddings"
COLLECTION_CHUNKS = "file_chunks"
COLLECTION_VISUAL = "visual_embeddings"


class ChromaStore:
    _broken: bool = False

    def __init__(self, persist_path: str | None = None) -> None:
        settings.ensure_dirs()
        self._persist_path = persist_path or settings.chroma_dir
        Path(self._persist_path).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=self._persist_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._refresh_collections()

    def is_healthy(self) -> bool:
        if ChromaStore._broken:
            return False
        try:
            self._files.count()
            return True
        except (InternalError, NotFoundError, Exception) as e:
            logger.warning("Chroma 不可用: %s", e)
            ChromaStore._broken = True
            return False

    def _query_collection(self, collection, **kwargs: Any) -> dict[str, Any]:
        try:
            return collection.query(**kwargs)
        except NotFoundError:
            logger.warning("Chroma 集合失效，正在刷新后重试")
            self._refresh_collections()
            return collection.query(**kwargs)
        except InternalError as e:
            logger.error("Chroma 索引损坏，查询已跳过: %s", e)
            ChromaStore._broken = True
            return {"ids": [[]], "distances": [[]], "metadatas": [[]], "documents": [[]]}

    def _refresh_collections(self) -> None:
        self._files = self._client.get_or_create_collection(
            COLLECTION_FILES,
            metadata={"hnsw:space": "cosine"},
        )
        self._chunks = self._client.get_or_create_collection(
            COLLECTION_CHUNKS,
            metadata={"hnsw:space": "cosine"},
        )
        self._visual = self._client.get_or_create_collection(
            COLLECTION_VISUAL,
            metadata={"hnsw:space": "cosine"},
        )

    def clear_all(self) -> None:
        for name in (COLLECTION_FILES, COLLECTION_CHUNKS, COLLECTION_VISUAL):
            try:
                self._client.delete_collection(name)
            except Exception:
                pass
        self._refresh_collections()

    def upsert_file(self, desc: FileDescriptor) -> None:
        if not desc.file_embedding:
            return
        meta = {
            "file_id": desc.file_id,
            "path": desc.path,
            "name": desc.name,
            "extension": desc.extension,
            "status": desc.status.value,
            "modified_time": desc.modified_time.isoformat(),
            "project_id": desc.project_id or "",
        }
        self._files.upsert(
            ids=[desc.file_id],
            embeddings=[desc.file_embedding],
            documents=[desc.display_summary()],
            metadatas=[meta],
        )
        self._index_chunks(desc)
        if desc.visual_embedding:
            self._upsert_visual(desc)

    def _upsert_visual(self, desc: FileDescriptor) -> None:
        meta = {
            "file_id": desc.file_id,
            "path": desc.path,
            "name": desc.name,
            "extension": desc.extension,
            "media_kind": desc.media_kind or "",
        }
        doc = desc.display_summary() or desc.name
        self._visual.upsert(
            ids=[desc.file_id],
            embeddings=[desc.visual_embedding],
            documents=[doc],
            metadatas=[meta],
        )

    def _index_chunks(self, desc: FileDescriptor, chunk_size: int = 400) -> None:
        text = desc.summary
        if len(text) < chunk_size:
            chunks = [text or desc.name]
        else:
            chunks = [
                text[i : i + chunk_size]
                for i in range(0, min(len(text), 4000), chunk_size)
            ]

        from src.indexing.embedder import Embedder

        embedder = Embedder.get()
        embeddings = embedder.embed_batch(chunks)
        ids = []
        metas = []
        for i, chunk in enumerate(chunks):
            cid = f"{desc.file_id}::chunk::{i}"
            ids.append(cid)
            metas.append(
                {
                    "file_id": desc.file_id,
                    "path": desc.path,
                    "name": desc.name,
                    "extension": desc.extension,
                    "chunk_index": i,
                    "modified_time": desc.modified_time.isoformat(),
                }
            )
        self._chunks.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metas,
        )

    def list_file_ids(self) -> list[str]:
        try:
            data = self._files.get(include=[])
            return list(data.get("ids") or [])
        except Exception:
            return []

    def delete_file(self, file_id: str) -> None:
        try:
            self._files.delete(ids=[file_id])
        except Exception:
            pass
        try:
            self._visual.delete(ids=[file_id])
        except Exception:
            pass
        try:
            existing = self._chunks.get(where={"file_id": file_id})
            if existing and existing["ids"]:
                self._chunks.delete(ids=existing["ids"])
        except Exception:
            pass

    def search_chunks(
        self,
        query_embedding: list[float],
        *,
        n_results: int = 30,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["metadatas", "distances", "documents"],
        }
        if where:
            kwargs["where"] = where

        result = self._query_collection(self._chunks, **kwargs)
        hits: list[dict[str, Any]] = []
        if not result["ids"] or not result["ids"][0]:
            return hits

        for i, cid in enumerate(result["ids"][0]):
            dist = result["distances"][0][i] if result["distances"] else 0
            sim = 1.0 - dist
            meta = result["metadatas"][0][i] if result["metadatas"] else {}
            hits.append(
                {
                    "chunk_id": cid,
                    "file_id": meta.get("file_id"),
                    "path": meta.get("path"),
                    "name": meta.get("name"),
                    "similarity": sim,
                    "document": result["documents"][0][i] if result["documents"] else "",
                }
            )
        return hits

    def get_file_embedding(self, file_id: str) -> list[float] | None:
        try:
            result = self._files.get(ids=[file_id], include=["embeddings"])
            if result["embeddings"] and result["embeddings"][0]:
                return result["embeddings"][0]
        except Exception:
            pass
        return None

    def search_files(
        self, query_embedding: list[float], n_results: int = 20
    ) -> list[dict[str, Any]]:
        result = self._query_collection(
            self._files,
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["metadatas", "distances", "documents"],
        )
        hits = []
        if not result["ids"] or not result["ids"][0]:
            return hits
        for i, fid in enumerate(result["ids"][0]):
            dist = result["distances"][0][i]
            hits.append(
                {
                    "file_id": fid,
                    "similarity": 1.0 - dist,
                    "metadata": result["metadatas"][0][i],
                }
            )
        return hits

    def search_visual(
        self,
        query_embedding: list[float],
        *,
        n_results: int = 20,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not query_embedding:
            return []
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["metadatas", "distances", "documents"],
        }
        if where:
            kwargs["where"] = where
        result = self._query_collection(self._visual, **kwargs)
        hits: list[dict[str, Any]] = []
        if not result["ids"] or not result["ids"][0]:
            return hits
        for i, fid in enumerate(result["ids"][0]):
            dist = result["distances"][0][i]
            meta = result["metadatas"][0][i] if result["metadatas"] else {}
            hits.append(
                {
                    "file_id": fid,
                    "path": meta.get("path", ""),
                    "name": meta.get("name", ""),
                    "similarity": 1.0 - dist,
                    "source": "visual",
                }
            )
        return hits
