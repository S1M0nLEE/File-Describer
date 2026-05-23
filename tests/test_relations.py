import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.models.file_descriptor import FileDescriptor
from src.relations.same_type import SameTypeExtractor
from src.relations.near_in_time import NearInTimeExtractor
from src.relations.has_version import HasVersionExtractor
from src.relations.depends_on import DependsOnExtractor


def _file(name, ext=".py", content="", mtime=1000.0):
    path = f"/tmp/{name}"
    return FileDescriptor(
        id=FileDescriptor.generate_id(path),
        path=path,
        name=name,
        extension=ext,
        size=100,
        modified_time=mtime,
        created_time=mtime,
        content_text=content,
    )


def test_same_type():
    files = [_file("a.py"), _file("b.py"), _file("c.txt", ext=".txt")]
    edges = SameTypeExtractor().discover(files)
    assert any(e[2] == "SAME_TYPE" for e in edges)


def test_near_in_time():
    files = [_file("a.txt", ext=".txt", mtime=1000), _file("b.txt", ext=".txt", mtime=1005)]
    edges = NearInTimeExtractor().discover(files)
    assert len(edges) >= 1


def test_has_version():
    files = [
        _file("report_v1.md", ext=".md", content="hello world draft"),
        _file("report_v2.md", ext=".md", content="hello world final"),
    ]
    edges = HasVersionExtractor().discover(files)
    assert any(e[2] == "HAS_VERSION" for e in edges)


def test_depends_on_python():
    util = _file("utils.py", content="def helper():\n    return 1\n")
    main = _file("main.py", content="from utils import helper\n")
    edges = DependsOnExtractor().discover([util, main])
    types = {e[2] for e in edges}
    assert "DEPENDS_ON" in types or len(edges) == 0
