"""多路融合视觉关系发现（OCR / 文档页 / 视觉对齐 + pHash NEAR_DUPLICATE）。"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from src.config import settings
from src.models.descriptor import FileDescriptor
from src.multimodal.vision_encoder import VisionEncoder
from src.relations.base import RelationEdge
from src.relations.visual_fusion.confidence import Confidence, decide_confidence
from src.relations.visual_fusion.confidence import PairSignals
from src.relations.visual_fusion.doc_page import DocPageSimilarity
from src.relations.visual_fusion.ocr_layout import (
    extract_ocr_text,
    infer_media_route,
    layout_features,
    text_similarity,
)
from src.relations.visual_fusion.phash_util import (
    _IMAGE_EXT,
    compute_phash,
    discover_near_duplicate_edges,
)

logger = logging.getLogger(__name__)

_PDF_EXT = {".pdf"}
_VISUAL_EXT = _IMAGE_EXT | _PDF_EXT


class VisualFusionDiscoverer:
    def discover(self, descriptors: list[FileDescriptor]) -> list[RelationEdge]:
        if not settings.visual_enabled and not settings.multimodal_visual_index_enabled:
            return []

        enc = VisionEncoder.get()
        if not enc.available():
            return []

        candidates: dict[str, FileDescriptor] = {}
        vectors: dict[str, np.ndarray] = {}
        phashes: dict[str, tuple[Path, int]] = {}

        for d in descriptors:
            if "/noise/" in d.path.replace("\\", "/").lower():
                continue
            ext = d.extension.lower()
            if ext not in _VISUAL_EXT:
                continue
            path = Path(d.path)
            if not path.is_file():
                continue
            candidates[d.file_id] = d
            if d.visual_embedding:
                vectors[d.file_id] = np.array(d.visual_embedding, dtype=np.float32)
            else:
                vec = enc.embed_image_path(path, ext)
                if vec is not None:
                    vectors[d.file_id] = vec
            if ext in _IMAGE_EXT:
                ph = compute_phash(path)
                if ph is not None:
                    phashes[d.file_id] = (path, ph)

        edges: list[RelationEdge] = []
        edges.extend(self._near_duplicate_edges(candidates, phashes, vectors))

        if len(vectors) < 2:
            return edges

        doc_sim = DocPageSimilarity()
        ocr_cache: dict[str, tuple[str, int, int, str]] = {}
        for fid, d in candidates.items():
            text = extract_ocr_text(d)
            bc, cols = layout_features(text)
            ocr_cache[fid] = (text, bc, cols, infer_media_route(d, len(text)))

        ids = list(vectors.keys())
        mat = np.stack([vectors[i] for i in ids], axis=0)
        sims = mat @ mat.T
        prefilter = float(getattr(settings, "visual_prefilter_threshold", 0.55))

        doc_scores: dict[tuple[str, str], float] = {}
        for i, fid_a in enumerate(ids):
            da = candidates[fid_a]
            route_a = ocr_cache[fid_a][3]
            for j in range(i + 1, len(ids)):
                fid_b = ids[j]
                s_vis = float(sims[i, j])
                if s_vis < prefilter:
                    continue
                db = candidates[fid_b]
                route_b = ocr_cache[fid_b][3]
                ta, ba, ca, _ = ocr_cache[fid_a]
                tb, bb, cb, _ = ocr_cache[fid_b]
                s_text = text_similarity(ta, tb)
                s_align = float(np.clip((s_vis + s_text) / 2, 0, 1))
                s_doc = 0.0
                if route_a == "document_page" or route_b == "document_page":
                    key = (fid_a, fid_b)
                    if key not in doc_scores:
                        doc_scores[key] = doc_sim.page_similarity(
                            Path(da.path),
                            da.extension,
                            Path(db.path),
                            db.extension,
                        )
                    s_doc = doc_scores[key]

                phash_d = None
                if fid_a in phashes and fid_b in phashes:
                    from src.relations.visual_fusion.phash_util import hamming_distance

                    phash_d = hamming_distance(phashes[fid_a][1], phashes[fid_b][1])

                sig = PairSignals(
                    s_text=s_text,
                    s_doc=s_doc,
                    s_visual=s_vis,
                    s_align=s_align,
                    phash_dist=phash_d,
                    doc_is_top1=s_doc >= float(getattr(settings, "visual_theta_doc", 0.7)),
                    layout_verified=ba > 0 and bb > 0 and abs(ba - bb) <= 3 and ca == cb,
                    layout_skip_reason="" if (ba and bb) else "no_layout",
                    ocr_blocks_a=ba,
                    ocr_blocks_b=bb,
                    ocr_cols_a=ca,
                    ocr_cols_b=cb,
                )
                decision = decide_confidence(sig)
                if decision.level == Confidence.LOW and not getattr(
                    settings, "visual_emit_low_confidence", False
                ):
                    continue
                weight = {
                    Confidence.HIGH: 0.85,
                    Confidence.MED: 0.65,
                    Confidence.LOW: 0.35,
                }[decision.level]
                edges.append(
                    RelationEdge(
                        fid_a,
                        "VISUALLY_SIMILAR_TO",
                        fid_b,
                        weight=weight,
                        symmetric=True,
                        props={
                            **decision.props,
                            "relation_label": decision.relation_subtype,
                            "short_circuit": decision.short_circuit,
                        },
                    )
                )
        return edges

    def _near_duplicate_edges(
        self,
        candidates: dict[str, FileDescriptor],
        phashes: dict[str, tuple[Path, int]],
        vectors: dict[str, np.ndarray],
    ) -> list[RelationEdge]:
        edges: list[RelationEdge] = []
        enc = VisionEncoder.get()
        for fid_a, fid_b, dist in discover_near_duplicate_edges(phashes):
            s_vis = 0.0
            if fid_a in vectors and fid_b in vectors:
                s_vis = float(np.dot(vectors[fid_a], vectors[fid_b]))
            elif enc.available():
                va = vectors.get(fid_a) or enc.embed_image_path(
                    phashes[fid_a][0], candidates[fid_a].extension
                )
                vb = vectors.get(fid_b) or enc.embed_image_path(
                    phashes[fid_b][0], candidates[fid_b].extension
                )
                if va is not None and vb is not None:
                    s_vis = float(np.dot(va, vb))
            conf = "HIGH" if s_vis >= float(getattr(settings, "visual_theta_visual_high", 0.9)) else "MED"
            edges.append(
                RelationEdge(
                    fid_a,
                    "NEAR_DUPLICATE",
                    fid_b,
                    weight=0.9 if conf == "HIGH" else 0.6,
                    symmetric=True,
                    props={
                        "phash_dist": dist,
                        "s_visual": round(s_vis, 4),
                        "confidence": conf,
                        "relation_subtype": "near_duplicate",
                    },
                )
            )
        return edges
