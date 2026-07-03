"""规格核心模块单元测试。"""
from __future__ import annotations

import math

from src.indexing.projection import project_to_512
from src.relations.behavior_ema import ema_update
from src.relations.cold_start import ColdStartManager
from src.search.explanation import (
    explanation_fidelity,
    generate_explanation,
    rule_match_score,
)
from src.vfe.identity import compute_vfe_id, content_hash_prefix
from src.vfe.memory import MemoryRecord, VFEMemoryStack, calc_co_weight


def test_vfe_id_deterministic():
    a = compute_vfe_id("1:42", 1000.0)
    b = compute_vfe_id("1:42", 1000.0)
    assert a == b
    assert len(a) == 64


def test_projection_512_dim():
    vec = project_to_512([0.1] * 384)
    assert len(vec) == 512
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 0.01


def test_memory_stack_capacity():
    stack = VFEMemoryStack(capacity=3)
    mem: list = []
    for i in range(5):
        mem = stack.push(mem, "accessed")
    assert len(mem) == 3


def test_co_weight():
    ts = 1000.0
    a = {"memory_stack": [MemoryRecord("accessed", ts, None).to_dict()]}
    b = {"memory_stack": [MemoryRecord("accessed", ts + 10, None).to_dict()]}
    assert calc_co_weight(a, b, delta_t=300) > 0


def test_ema_update():
    assert ema_update(1.0, 0.0, alpha=0.7) == 0.7


def test_cold_start_progression():
    mgr = ColdStartManager()
    mgr.on_file_event(50)
    assert "NEAR_IN_TIME" in mgr.enabled_relations
    mgr.on_file_event(100)
    assert "WORKFLOW_WITH" in mgr.enabled_relations


def test_explanation_and_fidelity():
    node = {"name": "report.pdf", "extension": ".pdf"}
    factors = {"semantic": 0.4, "centrality": 0.1, "recency": 0.05, "rule": 0.0, "frequency": 0.0}
    expl = generate_explanation("report", node, None, factors)
    assert "report.pdf" in expl
    fid = explanation_fidelity(factors, 0.55)
    assert 0 < fid <= 1.0


def test_rule_match_score():
    assert rule_match_score("notes.docx", {"name": "notes.docx", "extension": ".docx"}) == 1.0
    assert rule_match_score("pdf", {"name": "a.txt", "extension": ".pdf"}) == 0.5
