#!/usr/bin/env python3
"""Set Neo4j password (handles first-login credential change on system DB)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neo4j import GraphDatabase

OLD = "neo4j"
NEW = "filekg123"
uri = "bolt://localhost:7687"

driver = GraphDatabase.driver(uri, auth=("neo4j", OLD))
with driver.session(database="system") as session:
    session.run(
        "ALTER CURRENT USER SET PASSWORD FROM $old TO $new",
        old=OLD,
        new=NEW,
    )
driver.close()

driver2 = GraphDatabase.driver(uri, auth=("neo4j", NEW))
driver2.verify_connectivity()
with driver2.session() as s:
    print("Query test:", s.run("RETURN 1 AS n").single()["n"])
driver2.close()
print(f"Neo4j ready: neo4j / {NEW}")
