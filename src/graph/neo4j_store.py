"""Neo4j graph storage backend."""

from typing import Any, Dict, List, Set

from neo4j import GraphDatabase

from src.graph.constants import FILE_FILE_RELATIONS
from src.graph.store import EdgeRow, ExpandRow, GraphStore

LABEL_BY_REL = {
    "IN_FOLDER": "Folder",
    "BELONGS_TO_PROJECT": "Project",
    "TAGGED_WITH": "Tag",
}


class Neo4jGraphStore(GraphStore):
    backend_name = "neo4j"

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self.driver.close()

    def verify_connectivity(self) -> None:
        self.driver.verify_connectivity()

    def ensure_indexes(self) -> None:
        stmts = [
            "CREATE INDEX file_id IF NOT EXISTS FOR (f:FileDescriptor) ON (f.id)",
            "CREATE INDEX folder_id IF NOT EXISTS FOR (f:Folder) ON (f.id)",
            "CREATE INDEX project_id IF NOT EXISTS FOR (p:Project) ON (p.id)",
            "CREATE INDEX tag_id IF NOT EXISTS FOR (t:Tag) ON (t.id)",
        ]
        with self.driver.session() as session:
            for s in stmts:
                session.run(s)

    def clear(self) -> None:
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def merge_node(self, label: str, node_id: str, props: Dict[str, Any]) -> None:
        with self.driver.session() as session:
            session.run(
                f"MERGE (n:{label} {{id: $id}}) SET n += $props",
                id=node_id, props=props,
            )

    def write_relationships(self, edges: List[EdgeRow]) -> None:
        with self.driver.session() as session:
            for src, tgt, rtype, props in edges:
                tgt_label = LABEL_BY_REL.get(rtype, "FileDescriptor")
                session.run(
                    f"""
                    MATCH (a:FileDescriptor {{id: $src}})
                    MERGE (b:{tgt_label} {{id: $tgt}})
                    MERGE (a)-[r:{rtype}]->(b)
                    SET r += $props
                    """,
                    src=src, tgt=tgt, props=props or {},
                )

    def update_file_status(self, file_id: str, status: str) -> None:
        with self.driver.session() as session:
            session.run(
                "MATCH (n:FileDescriptor {id: $id}) SET n.status = $status",
                id=file_id, status=status,
            )

    def delete_file(self, file_id: str) -> None:
        with self.driver.session() as session:
            session.run("MATCH (n:FileDescriptor {id: $id}) DETACH DELETE n", id=file_id)

    def list_file_file_relation_types(self) -> Set[str]:
        """Return file-file relation types that exist in the DB."""
        with self.driver.session() as session:
            rows = session.run(
                """
                MATCH (:FileDescriptor)-[r]->(:FileDescriptor)
                RETURN DISTINCT type(r) AS t
                """
            )
            found = {r["t"] for r in rows}
        return found & set(FILE_FILE_RELATIONS)

    def expand_files(
        self,
        seed_ids: List[str],
        allowed_relations: Set[str],
        max_hops: int = 1,
        limit: int = 500,
    ) -> List[ExpandRow]:
        if not seed_ids:
            return []

        allowed = set(allowed_relations) & set(FILE_FILE_RELATIONS)
        existing = self.list_file_file_relation_types()
        rels = sorted(allowed & existing)
        if not rels:
            return []

        rel_types = "|".join(rels)
        cypher = f"""
        UNWIND $seeds AS seed_id
        MATCH (seed:FileDescriptor {{id: seed_id}})
        OPTIONAL MATCH path = (seed)-[r:{rel_types}*1..{max_hops}]-(neighbor:FileDescriptor)
        WHERE neighbor IS NOT NULL AND neighbor.id <> seed.id
        RETURN seed.id AS seed_id, neighbor.id AS neighbor_id,
               [rel IN relationships(path) | type(rel)] AS rels,
               length(path) AS hops
        LIMIT $limit
        """
        rows: List[ExpandRow] = []
        with self.driver.session() as session:
            for record in session.run(cypher, seeds=seed_ids, limit=limit):
                rows.append((
                    record["seed_id"],
                    record["neighbor_id"],
                    record["rels"] or [],
                    record["hops"] or 1,
                ))
        return rows
