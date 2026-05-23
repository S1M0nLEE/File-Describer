"""Create graph store: auto-detect Neo4j or fall back to local JSON."""

import logging
import os

from src.config import Config
from src.graph.local_store import LocalGraphStore
from src.graph.neo4j_store import Neo4jGraphStore
from src.graph.store import GraphStore

logger = logging.getLogger(__name__)


def create_graph_store(config: Config) -> GraphStore:
    backend = os.environ.get("FILEKG_GRAPH_BACKEND", config.graph_backend).lower()
    local_path = config.project_root / config.local_graph_path

    if backend == "local":
        logger.info("Using local graph store at %s", local_path)
        return LocalGraphStore(local_path)

    if backend == "neo4j":
        store = Neo4jGraphStore(config.neo4j_uri, config.neo4j_user, config.neo4j_password)
        store.verify_connectivity()
        logger.info("Connected to Neo4j at %s", config.neo4j_uri)
        return store

    # auto
    try:
        store = Neo4jGraphStore(config.neo4j_uri, config.neo4j_user, config.neo4j_password)
        store.verify_connectivity()
        logger.info("Auto: using Neo4j at %s", config.neo4j_uri)
        return store
    except Exception as exc:
        logger.warning("Neo4j unavailable (%s), using local graph store", exc)
        return LocalGraphStore(local_path)
