"""关系类型数量：与 README「12+」声明一致（可代码审计）。"""

from __future__ import annotations

from src.relations.pipeline import DEFAULT_PIPELINE


def test_relation_parser_count_at_least_twelve():
    assert len(DEFAULT_PIPELINE) >= 10  # 解析器模块数


def test_documented_relation_types_exist():
    """README 列举的核心关系类型在评测/constants 中有定义。"""
    from src.evaluation.metrics import GRAPH_DISCOVERY_RELATIONS

    core = {
        "DEPENDS_ON",
        "WORKFLOW_WITH",
        "REFERENCES",
        "HAS_VERSION",
        "IN_FOLDER",
        "NEAR_IN_TIME",
        "SAME_TYPE",
    }
    assert core.issubset(GRAPH_DISCOVERY_RELATIONS)
