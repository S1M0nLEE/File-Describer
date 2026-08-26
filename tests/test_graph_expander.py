import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.models.descriptor import FileDescriptor
from src.search.graph_expander import GraphExpander
from src.storage.memory_graph import MemoryGraphStore


def _node(fid: str, name: str) -> FileDescriptor:
    t = datetime(2024, 1, 1)
    return FileDescriptor(
        file_id=fid,
        path=f"/tmp/{name}",
        name=name,
        extension=Path(name).suffix,
        size=10,
        created_time=t,
        modified_time=t,
    )


def test_graph_expander_one_hop(tmp_path: Path):
    store = MemoryGraphStore(path=tmp_path / "g.json")
    a = _node("a", "main.py")
    b = _node("b", "utils.py")
    store.upsert_file(a)
    store.upsert_file(b)
    store.create_relation("a", "DEPENDS_ON", "b", weight=0.9)
    store.flush()

    hits = GraphExpander(store).expand_seeds(
        [{"file_id": "a", "path": a.path, "name": a.name, "similarity": 0.9}],
        hops=1,
    )
    assert "a" in hits
    assert "b" in hits
    assert any(p.get("rel_type") == "DEPENDS_ON" for p in hits["b"].paths)


def test_update_path_keeps_file_id(tmp_path: Path):
    store = MemoryGraphStore(path=tmp_path / "g2.json")
    store.upsert_file(_node("fid-1", "old.txt"))
    store.update_path("fid-1", str(tmp_path / "new.txt"), "new.txt")
    store.flush()
    assert "fid-1" in store._nodes
    assert store._nodes["fid-1"]["name"] == "new.txt"
