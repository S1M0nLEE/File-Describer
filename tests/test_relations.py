import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.models.descriptor import FileDescriptor
from src.relations.content_relations import DependsOnParser
from src.relations.metadata_relations import MetadataRelationsParser
from src.relations.version_relations import VersionRelationsParser


def _desc(name: str, *, ext: str = ".txt", mtime: datetime | None = None) -> FileDescriptor:
    path = f"/tmp/filekg_test/{name}"
    mt = mtime or datetime(2024, 6, 1, 12, 0, 0)
    return FileDescriptor(
        file_id=f"fid:{name}",
        path=path,
        name=name,
        extension=ext,
        size=100,
        created_time=mt,
        modified_time=mt,
    )


def test_same_type():
    files = [_desc("a.py", ext=".py"), _desc("b.py", ext=".py"), _desc("c.txt", ext=".txt")]
    edges = MetadataRelationsParser().discover(files, None)
    assert any(e.rel_type == "SAME_TYPE" for e in edges)


def test_near_in_time():
    t0 = datetime(2024, 6, 1, 12, 0, 0)
    t1 = t0 + timedelta(minutes=5)
    files = [_desc("a.txt", mtime=t0), _desc("b.txt", mtime=t1)]
    edges = MetadataRelationsParser().discover(files, None)
    assert any(e.rel_type == "NEAR_IN_TIME" for e in edges)


def test_has_version():
    files = [_desc("report_v1.md", ext=".md"), _desc("report_v2.md", ext=".md")]
    edges = VersionRelationsParser().discover(files, None)
    assert any(e.rel_type == "HAS_VERSION" for e in edges)


def test_depends_on_python(tmp_path: Path):
    util = tmp_path / "utils.py"
    main = tmp_path / "main.py"
    util.write_text("def helper():\n    return 1\n", encoding="utf-8")
    main.write_text("from utils import helper\n", encoding="utf-8")
    t = datetime(2024, 6, 1, 12, 0, 0)

    def from_path(p: Path) -> FileDescriptor:
        return FileDescriptor(
            file_id=f"fid:{p.name}",
            path=str(p.resolve()),
            name=p.name,
            extension=p.suffix.lower(),
            size=p.stat().st_size,
            created_time=t,
            modified_time=t,
        )

    files = [from_path(util), from_path(main)]
    edges = DependsOnParser().discover(files, None)
    assert any(e.rel_type == "DEPENDS_ON" for e in edges)
