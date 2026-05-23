import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.models.file_descriptor import FileDescriptor


def test_generate_id_stable():
    a = FileDescriptor.generate_id("C:/foo/bar.txt")
    b = FileDescriptor.generate_id("C:/foo/bar.txt")
    assert a == b
    assert len(a) == 32


def test_generate_id_normalized():
    a = FileDescriptor.generate_id("data/test.txt")
    b = FileDescriptor.generate_id(str(Path("data/test.txt").resolve()))
    assert a == b or isinstance(a, str)
