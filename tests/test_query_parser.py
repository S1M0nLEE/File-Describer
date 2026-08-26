import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.search.intent_parser import IntentParser


def test_parse_extensions():
    pq = IntentParser().parse("find .py files about budget")
    assert ".py" in pq.extensions


def test_parse_keywords():
    pq = IntentParser().parse("季度经营报告")
    assert pq.keywords
