import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.indexing.file_id import get_file_id, get_path_based_id


def test_volume_id_stable_for_same_file(tmp_path: Path):
    f = tmp_path / "sample.txt"
    f.write_text("hello", encoding="utf-8")
    a = get_file_id(f, mode="volume")
    b = get_file_id(f, mode="volume")
    assert a == b
    assert a != get_path_based_id(f)


def test_path_id_changes_when_renamed(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    id_before = get_path_based_id(f)
    dest = tmp_path / "b.txt"
    f.rename(dest)
    id_after = get_path_based_id(dest)
    assert id_before != id_after


def test_volume_id_stable_after_rename(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    vol_before = get_file_id(f, mode="volume")
    dest = tmp_path / "b.txt"
    f.rename(dest)
    vol_after = get_file_id(dest, mode="volume")
    assert vol_before == vol_after
