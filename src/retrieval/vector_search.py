"""Chroma vector search for seed files."""

import logging
from typing import Any, Dict, List, Optional

import chromadb

from src.config import Config, get_config
from src.pipeline.embedder import Embedder
from src.pipeline.chroma_store import CHROMA_COLLECTION

logger = logging.getLogger(__name__)


class VectorSearcher:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()
        self.embedder = Embedder(self.config)
        self.chroma = chromadb.PersistentClient(path=self.config.chroma_persist_dir)
        self.collection = self._open_collection()

    def _open_collection(self):
        try:
            return self.chroma.get_collection(name=CHROMA_COLLECTION)
        except Exception:
            return self.chroma.get_or_create_collection(
                name=CHROMA_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )

    def refresh(self) -> None:
        """Re-bind collection after index rebuild (avoids stale collection UUID)."""
        self.collection = self._open_collection()

    def count(self) -> int:
        try:
            return self.collection.count()
        except Exception as e:
            logger.warning("Chroma count failed, refreshing: %s", e)
            self.refresh()
            try:
                return self.collection.count()
            except Exception:
                return 0

    def search(
        self,
        query_text: str,
        filters: Optional[Dict[str, Any]] = None,
        top_n: int = 100,
    ) -> List[str]:
        if not query_text.strip():
            return []

        n = self.count()
        if n == 0:
            return []

        q_emb = self.embedder.encode(query_text)
        where = self._chroma_where(filters or {})
        k = min(top_n, n)

        try:
            result = self.collection.query(
                query_embeddings=[q_emb],
                n_results=k,
                where=where if where else None,
            )
        except Exception:
            self.refresh()
            result = self.collection.query(
                query_embeddings=[q_emb],
                n_results=k,
            )

        ids = result.get("ids", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        file_ids: List[str] = []
        seen: set = set()
        for i, meta in zip(ids, metas):
            fid = (meta or {}).get("file_id", i)
            if fid not in seen:
                seen.add(fid)
                file_ids.append(fid)
        return file_ids

    def _chroma_where(self, filters: Dict[str, Any]) -> Optional[Dict]:
        if not filters:
            return None
        clauses = []
        for key, val in filters.items():
            if isinstance(val, dict):
                for op, v in val.items():
                    if op == "$in":
                        clauses.append({key: {"$in": v}})
                    elif op == "$gte":
                        clauses.append({key: {"$gte": v}})
                    elif op == "$lte":
                        clauses.append({key: {"$lte": v}})
            else:
                clauses.append({key: val})
        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}
