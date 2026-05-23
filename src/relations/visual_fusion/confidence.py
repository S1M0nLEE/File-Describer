"""
三路信号置信度裁决（发明说明 5.4.3 + 审查修改意见 问题1/2）。

表 1：三路信号组合与置信度裁决真值表（实现为 decide_confidence）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.config import settings


class Confidence(str, Enum):
    HIGH = "HIGH"
    MED = "MED"
    LOW = "LOW"


# 关系子类型优先级（多短路同时触发时）
SUBTYPE_PRIORITY = (
    "ocr_text_consistent",
    "document_layout_match",
    "near_duplicate",
    "semantic_visual",
)


@dataclass
class PairSignals:
    s_text: float = 0.0
    s_doc: float = 0.0
    s_visual: float = 0.0
    s_align: float = 0.0
    phash_dist: int | None = None
    doc_is_top1: bool = False
    layout_verified: bool = False
    layout_skip_reason: str = ""
    ocr_blocks_a: int = 0
    ocr_blocks_b: int = 0
    ocr_cols_a: int = 0
    ocr_cols_b: int = 0


@dataclass
class ConfidenceDecision:
    level: Confidence
    relation_subtype: str
    short_circuit: str
    props: dict[str, Any]


def _th(name: str, default: float) -> float:
    return float(getattr(settings, name, default))


def ocr_short_circuit_ok(sig: PairSignals) -> tuple[bool, str]:
    """OCR 文本一致短路（θ_text 默认 0.75 + 版面约束，问题2）。"""
    theta_text = _th("visual_theta_text", 0.75)
    theta_align_low = _th("visual_theta_align_low", 0.4)
    if sig.s_text < theta_text or sig.s_align < theta_align_low:
        return False, ""

    both_have_layout = sig.ocr_blocks_a > 0 and sig.ocr_blocks_b > 0
    if both_have_layout:
        if abs(sig.ocr_blocks_a - sig.ocr_blocks_b) > 3:
            return False, ""
        if sig.ocr_cols_a != sig.ocr_cols_b:
            return False, ""
        return True, "ocr_text_consistent"
    return True, "ocr_text_consistent_no_layout"


def doc_top1_short_circuit(sig: PairSignals) -> bool:
    theta_doc = _th("visual_theta_doc", 0.7)
    theta_align_low = _th("visual_theta_align_low", 0.4)
    return sig.doc_is_top1 and sig.s_doc >= theta_doc and sig.s_align >= theta_align_low


def near_dup_short_circuit(sig: PairSignals) -> bool:
    t_phash = int(_th("visual_phash_threshold", 6))
    theta_visual_high = _th("visual_theta_visual_high", 0.9)
    if sig.phash_dist is None:
        return False
    return sig.phash_dist <= t_phash and sig.s_visual >= theta_visual_high


def decide_confidence(sig: PairSignals) -> ConfidenceDecision:
    """
    按表 1 裁决；多短路触发时 relation_subtype 取 SUBTYPE_PRIORITY 最高项。
    """
    triggered: list[tuple[str, Confidence, str]] = []

    ok, sub = ocr_short_circuit_ok(sig)
    if ok:
        triggered.append((sub or "ocr_text_consistent", Confidence.HIGH, "ocr_text"))

    if doc_top1_short_circuit(sig):
        triggered.append(("document_layout_match", Confidence.HIGH, "doc_top1"))

    if near_dup_short_circuit(sig):
        triggered.append(("near_duplicate", Confidence.HIGH, "phash_near_dup"))

    if (
        ocr_short_circuit_ok(sig)[0]
        and doc_top1_short_circuit(sig)
        and not any(t[2] == "ocr+doc" for t in triggered)
    ):
        triggered.append(
            ("ocr_text_consistent+document_layout_match", Confidence.HIGH, "ocr+doc")
        )

    if triggered:
        best = min(triggered, key=lambda t: SUBTYPE_PRIORITY.index(t[0].split("+")[0]) if t[0].split("+")[0] in SUBTYPE_PRIORITY else 99)
        subtype = best[0]
        if len([t for t in triggered if t[1] == Confidence.HIGH]) > 1:
            labels = [t[0] for t in triggered if t[1] == Confidence.HIGH]
            if "ocr_text_consistent" in str(labels) and "document_layout_match" in str(labels):
                subtype = "ocr_text_consistent+document_layout_match"
        return ConfidenceDecision(
            level=Confidence.HIGH,
            relation_subtype=subtype,
            short_circuit=",".join(sorted({t[2] for t in triggered})),
            props=_props(sig, subtype, Confidence.HIGH),
        )

    theta_text = _th("visual_theta_text", 0.75)
    theta_doc = _th("visual_theta_doc", 0.7)
    theta_visual_med = _th("visual_theta_visual_med", 0.75)
    theta_align_med = _th("visual_theta_align_med", 0.55)

    med_reasons: list[str] = []
    if sig.s_text >= theta_text and not ocr_short_circuit_ok(sig)[0]:
        med_reasons.append("text_only")
    if sig.s_doc >= theta_doc and not sig.doc_is_top1:
        med_reasons.append("doc_only")
    if sig.s_visual >= theta_visual_med and sig.s_align >= theta_align_med:
        med_reasons.append("visual_align_med")

    if med_reasons:
        return ConfidenceDecision(
            level=Confidence.MED,
            relation_subtype="semantic_visual" if "visual_align_med" in med_reasons else "partial_route",
            short_circuit="",
            props=_props(sig, "partial_route", Confidence.MED),
        )

    return ConfidenceDecision(
        level=Confidence.LOW,
        relation_subtype="weak_single_route",
        short_circuit="",
        props=_props(sig, "weak_single_route", Confidence.LOW),
    )


def _props(sig: PairSignals, subtype: str, level: Confidence) -> dict[str, Any]:
    return {
        "confidence": level.value,
        "relation_subtype": subtype,
        "s_text": round(sig.s_text, 4),
        "s_doc": round(sig.s_doc, 4),
        "s_visual": round(sig.s_visual, 4),
        "s_align": round(sig.s_align, 4),
        "phash_dist": sig.phash_dist,
        "layout_verified": sig.layout_verified,
        "layout_skip_reason": sig.layout_skip_reason,
    }
