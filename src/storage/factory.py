from __future__ import annotations

import logging

from src.storage.chroma_store import ChromaStore
from src.storage.memory_graph import MemoryGraphStore

logger = logging.getLogger(__name__)

GraphStore = MemoryGraphStore  # 运行时可为 Neo4jStore


def create_graph_store(*, defer_load: bool = False) -> MemoryGraphStore:
    try:
        from src.storage.neo4j_store import Neo4jStore

        store = Neo4jStore()
        with store._driver.session() as session:
            session.run("RETURN 1")
        logger.info("使用 Neo4j 图数据库")
        return store
    except Exception as e:
        logger.warning("Neo4j 不可用 (%s)，回退到本地 JSON 图存储", e)
        return MemoryGraphStore(defer_load=defer_load)


def create_stores(*, defer_load: bool = False) -> tuple[GraphStore, ChromaStore]:
    return create_graph_store(defer_load=defer_load), ChromaStore()


def create_eval_stores(dataset_id: str) -> tuple[MemoryGraphStore, ChromaStore]:
    """评测专用隔离存储，避免污染生产 graph_store / chroma。"""
    from src.config import settings

    settings.ensure_dirs()
    graph_dir = settings.data_dir / "graph_eval"
    graph_dir.mkdir(parents=True, exist_ok=True)
    graph = MemoryGraphStore(graph_dir / f"{dataset_id}.json")
    chroma = ChromaStore(persist_path=str(settings.data_dir / "chroma_eval" / dataset_id))
    return graph, chroma
