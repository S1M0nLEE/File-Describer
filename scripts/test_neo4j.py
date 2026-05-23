#!/usr/bin/env python3
"""Verify Neo4j connectivity for FileKG."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neo4j import GraphDatabase

_env = ROOT / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
user = os.environ.get("NEO4J_USER", "neo4j")
password = os.environ.get("NEO4J_PASSWORD", "filekg123")

driver = GraphDatabase.driver(uri, auth=(user, password))
driver.verify_connectivity()
with driver.session() as s:
    r = s.run("RETURN 1 AS ok").single()
    print(f"Neo4j OK: {uri} user={user} result={r['ok']}")
driver.close()
