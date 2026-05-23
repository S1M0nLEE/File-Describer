from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from src.config import settings
from src.models.descriptor import FileDescriptor

logger = logging.getLogger(__name__)


class Neo4jStore:
    def __init__(self) -> None:
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        self._ensure_schema()

    def close(self) -> None:
        self._driver.close()

    def _ensure_schema(self) -> None:
        with self._driver.session() as session:
            session.run(
                "CREATE CONSTRAINT file_id_unique IF NOT EXISTS "
                "FOR (f:File) REQUIRE f.file_id IS UNIQUE"
            )

    def clear_all(self) -> None:
        with self._driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def upsert_file(self, desc: FileDescriptor) -> None:
        props = desc.to_neo4j_props()
        with self._driver.session() as session:
            session.run(
                """
                MERGE (f:File {file_id: $file_id})
                SET f += $props
                """,
                file_id=desc.file_id,
                props=props,
            )

    def upsert_files(self, descriptors: list[FileDescriptor]) -> None:
        for d in descriptors:
            self.upsert_file(d)

    def create_relation(
        self,
        src_id: str,
        rel_type: str,
        dst_id: str,
        *,
        weight: float = 1.0,
        props: dict[str, Any] | None = None,
        symmetric: bool = False,
    ) -> None:
        rel_props = {"weight": weight, **(props or {})}
        cypher = f"""
        MATCH (a:File {{file_id: $src}}), (b:File {{file_id: $dst}})
        MERGE (a)-[r:{rel_type}]->(b)
        SET r += $props
        """
        with self._driver.session() as session:
            session.run(cypher, src=src_id, dst=dst_id, props=rel_props)
            if symmetric:
                session.run(
                    cypher.replace(f"-[r:{rel_type}]->", f"-[r:{rel_type}]->"),
                    src=dst_id,
                    dst=src_id,
                    props=rel_props,
                )

    def create_symmetric_relation(
        self, a_id: str, rel_type: str, b_id: str, **kwargs: Any
    ) -> None:
        self.create_relation(a_id, rel_type, b_id, **kwargs)
        self.create_relation(b_id, rel_type, a_id, **kwargs)

    def delete_file(self, file_id: str) -> None:
        with self._driver.session() as session:
            session.run(
                "MATCH (f:File {file_id: $fid}) DETACH DELETE f",
                fid=file_id,
            )

    def update_path(self, file_id: str, new_path: str, new_name: str) -> None:
        with self._driver.session() as session:
            session.run(
                """
                MATCH (f:File {file_id: $fid})
                SET f.path = $path, f.name = $name
                """,
                fid=file_id,
                path=new_path,
                name=new_name,
            )

    def get_neighbors(
        self,
        file_id: str,
        rel_types: list[str] | None = None,
        hops: int = 1,
    ) -> list[dict[str, Any]]:
        if rel_types:
            rel_filter = "|".join(rel_types)
            pattern = f"-[r:{rel_filter}]-"
        else:
            pattern = "-[r]-"

        cypher = f"""
        MATCH (f:File {{file_id: $fid}}){pattern}(n:File)
        WHERE f <> n
        RETURN n.file_id AS file_id, n.path AS path, n.name AS name,
               type(r) AS rel_type, r.weight AS weight,
               startNode(r).file_id AS from_id
        LIMIT 200
        """
        with self._driver.session() as session:
            result = session.run(cypher, fid=file_id)
            return [dict(rec) for rec in result]

    def get_file(self, file_id: str) -> dict[str, Any] | None:
        with self._driver.session() as session:
            rec = session.run(
                "MATCH (f:File {file_id: $fid}) RETURN f",
                fid=file_id,
            ).single()
            if rec:
                return dict(rec["f"])
            return None

    def list_all_files(self) -> list[dict[str, Any]]:
        with self._driver.session() as session:
            result = session.run(
                "MATCH (f:File) RETURN f.file_id AS file_id, f.path AS path, "
                "f.name AS name, f.status AS status, f.modified_time AS modified_time"
            )
            return [dict(r) for r in result]

    def indexed_mtime_by_path(self, root: Path) -> dict[str, str]:
        root = root.resolve()
        out: dict[str, str] = {}
        with self._driver.session() as session:
            result = session.run(
                "MATCH (f:File) WHERE f.path STARTS WITH $prefix "
                "RETURN f.path AS path, f.modified_time AS modified_time",
                prefix=str(root) + ("\\" if os.name == "nt" else "/"),
            )
            for rec in result:
                p = rec.get("path")
                if not p:
                    continue
                try:
                    out[str(Path(p).resolve())] = str(rec.get("modified_time") or "")
                except OSError:
                    continue
        return out

    def mark_dangling_relations(self, deleted_id: str) -> None:
        with self._driver.session() as session:
            session.run(
                """
                MATCH ()-[r]->()
                WHERE NOT EXISTS { MATCH (f:File) WHERE f.file_id = $fid }
                SET r.dangling = true
                """,
                fid=deleted_id,
            )
