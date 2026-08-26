import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.search.intent_parser import IntentParser


def test_parse_pdf_extension():
    pq = IntentParser().parse("上周修改的 pdf 实验")
    assert ".pdf" in pq.extensions


def test_parse_python_keyword():
    pq = IntentParser().parse("python 数据处理脚本")
    assert ".py" in pq.extensions


def test_parse_time_hint():
    pq = IntentParser().parse("昨天的 docx 报告")
    assert pq.modified_after is not None
    assert ".docx" in pq.extensions


def test_keywords_fallback():
    pq = IntentParser().parse("季度经营报告")
    assert pq.keywords
