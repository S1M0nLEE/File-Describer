import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.indexing.file_id import get_path_based_id


def test_path_id_stable():
    a = get_path_based_id("C:/foo/bar.txt")
    b = get_path_based_id("C:/foo/bar.txt")
    assert a == b
    assert a.startswith("path:")


def test_path_id_normalized():
    a = get_path_based_id("data/test.txt")
    b = get_path_based_id(str(Path("data/test.txt").resolve()))
    assert a == b
