import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.retrieval.query_parser import QueryParser


def test_parse_extensions():
    pq = QueryParser().parse("find .py files about budget")
    assert ".py" in pq.extensions


def test_parse_keywords():
    pq = QueryParser().parse("季度经营报告")
    assert pq.semantic_text
