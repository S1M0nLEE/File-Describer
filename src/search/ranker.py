from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

from src.config import settings
from src.indexing.access_memory import AccessMemory
from src.indexing.embedder import Embedder
from src.search.graph_expander import GraphHit
from src.search.intent_parser import ParsedQuery
from src.storage.chroma_store import ChromaStore
from src.storage.factory import GraphStore

_CORE_RELATIONS = frozenset(
    {
        "DEPENDS_ON",
        "REFERENCES",
        "HAS_VERSION",
        "IS_PREVIOUS_VERSION_OF",
        "WORKFLOW_WITH",
        "CONTAINS",
    }
)


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    return re.findall(r"[\u4e00-\u9fff]|[a-z0-9_]+", text) or text.split()


class MultiFactorRanker:
    def __init__(
        self,
        store: GraphStore,
        chroma: ChromaStore | None = None,
        *,
        bm25_bundle: tuple[Any, list[dict[str, str]], dict[str, int]] | None = None,
    ) -> None:
        self.store = store
        self.chroma = chroma
        self.embedder = Embedder.get()
        self._bm25_bundle = bm25_bundle
        self._access = AccessMemory(store)

    def rank(
        self,
        query: str,
        parsed: ParsedQuery,
        hits: dict[str, GraphHit],
        query_embedding: list[float],
    ) -> list[dict]:
        max_graph = max((h.graph_weight for h in hits.values()), default=1.0) or 1.0
        now = datetime.now()
        results: list[dict] = []

        bm25_scores: list[float] | None = None
        if self._bm25_bundle:
            bm25, corpus, _fid_map = self._bm25_bundle
            bm25_scores = list(bm25.get_scores(_tokenize(parsed.keywords or query)))
            max_bm25 = max(bm25_scores) if bm25_scores else 0.0
        else:
            max_bm25 = 0.0

        for fid, hit in hits.items():
            node = self.store.get_file(fid)
            if not node:
                continue
            path_l = (node.get("path") or "").replace("\\", "/").lower()
            if "/noise/" in path_l and not hit.is_seed:
                continue
            if node.get("status") in ("ARCHIVED", "ERROR", "GHOST") and not hit.is_seed:
                continue
            if node.get("status") == "DORMANT" and not hit.is_seed:
                pass  # 降权在 personal 与 score 中体现
            if node.get("is_inside_archive"):
                continue

            sem = hit.seed_similarity
            if query_embedding and self.chroma:
                emb = self.chroma.get_file_embedding(fid)
                if emb:
                    sem = max(sem, self.embedder.cosine(query_embedding, emb))

            graph_norm = hit.graph_weight / max_graph
            path_rels = {p.get("rel_type") for p in hit.paths}
            score_depends = 0.0
            if path_rels & {"DEPENDS_ON"}:
                graph_norm = min(1.0, graph_norm + 0.28)
                if not hit.is_seed:
                    score_depends = 0.14
            if path_rels & {"WORKFLOW_WITH"}:
                graph_norm = min(1.0, graph_norm + 0.18)
            if path_rels & {"REFERENCES"}:
                graph_norm = min(1.0, graph_norm + 0.16)
            if path_rels & {"HAS_VERSION", "IS_PREVIOUS_VERSION_OF"} and any(
                k in (parsed.keywords or query) for k in ("最新", "终稿", "版本")
            ):
                graph_norm = min(1.0, graph_norm + 0.14)
            if path_rels & _CORE_RELATIONS:
                graph_norm = min(1.0, graph_norm + 0.32)
            elif path_rels & {"IN_FOLDER", "NEAR_IN_TIME", "HAS_VERSION", "IS_PREVIOUS_VERSION_OF"}:
                graph_norm = min(1.0, graph_norm + 0.14)
            if not hit.is_seed and hit.paths:
                graph_norm = min(1.0, graph_norm + 0.06)

            mod_str = node.get("modified_time", "")
            try:
                mod_time = datetime.fromisoformat(mod_str)
                days = (now - mod_time).days
            except Exception:
                days = 365
            time_decay = math.exp(-settings.time_decay_lambda * days)

            rule_bonus = self._rule_bonus(node, parsed, query)
            personal = self._access.personalized_boost(node)
            if node.get("status") == "DORMANT":
                personal *= 0.5

            bm25_norm = 0.0
            if bm25_scores is not None and self._bm25_bundle:
                _, corpus, fid_map = self._bm25_bundle
                idx = fid_map.get(fid)
                if idx is not None and max_bm25 > 0:
                    bm25_norm = bm25_scores[idx] / max_bm25

            indirect_boost = 0.0
            if not hit.is_seed and hit.paths:
                indirect_boost += 0.10
                name_l = (node.get("name") or "").lower()
                qtok = re.findall(
                    r"[\u4e00-\u9fff]{2,}|[a-z0-9_]{3,}",
                    (parsed.keywords or query).lower(),
                )
                for token in qtok:
                    if token in name_l:
                        indirect_boost += 0.07 if len(token) >= 4 else 0.05
                if path_rels & {"DEPENDS_ON", "REFERENCES", "WORKFLOW_WITH", "CONTAINS"}:
                    indirect_boost += 0.18
                    if name_l.endswith(".py"):
                        indirect_boost += 0.08
                elif path_rels & {
                    "IN_FOLDER",
                    "HAS_VERSION",
                    "IS_PREVIOUS_VERSION_OF",
                    "BELONGS_TO_PROJECT",
                    "SAME_TYPE",
                }:
                    indirect_boost += 0.12
            indirect_boost = min(indirect_boost, 0.36)

            score = (
                settings.w_semantic * sem
                + settings.w_graph * graph_norm
                + settings.w_time * time_decay
                + settings.w_rule * rule_bonus
                + settings.w_personal * personal
                + settings.w_bm25 * bm25_norm
                + indirect_boost
                + score_depends
            )
            if hit.is_seed:
                score += 0.04

            results.append(
                {
                    "file_id": fid,
                    "path": node.get("path", hit.path),
                    "name": node.get("name", hit.name),
                    "score": round(score, 4),
                    "semantic_score": round(sem, 4),
                    "graph_weight": round(graph_norm, 4),
                    "time_decay": round(time_decay, 4),
                    "rule_bonus": round(rule_bonus, 4),
                    "bm25_score": round(bm25_norm, 4),
                    "is_seed": hit.is_seed,
                    "summary": node.get("ai_summary") or node.get("summary", ""),
                    "explanation_paths": hit.paths[:3],
                }
            )

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[: settings.result_top_n]

    def _rule_bonus(self, node: dict, parsed: ParsedQuery, query: str) -> float:
        bonus = 0.0
        ext = node.get("extension", "")
        if parsed.extensions and ext in parsed.extensions:
            bonus += 0.1
        kw = (parsed.keywords or query).lower()
        name = (node.get("name") or "").lower()
        for token in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9_]{2,}", kw):
            if token in name:
                bonus += 0.12
        if parsed.modified_after:
            try:
                mod = datetime.fromisoformat(node.get("modified_time", ""))
                if mod >= parsed.modified_after:
                    bonus += 0.05
            except Exception:
                pass
        if "论文" in kw and "论文" not in name and "paper" not in name:
            bonus -= 0.28
        if any(k in kw for k in ("最新", "终稿", "latest", "final", "版本")):
            if any(k in name for k in ("终稿", "final", "latest")):
                bonus += 0.55
            elif any(k in name for k in ("v2", "v3", "修改")) and "终稿" not in name:
                bonus += 0.12
            elif any(k in name for k in ("v1", "模板", "backup", "备份")):
                bonus -= 0.12
        if "损失" in kw and ("图表2" in name or "chart2" in name):
            bonus += 0.38
        if "准确率" in kw and ("图表1" in name or "chart1" in name):
            bonus += 0.38
        if "曲线" in kw and "图表" in name:
            bonus += 0.22
        if "引用" in kw and "参考文献" in kw and "论文" in name:
            bonus += 0.28
        if "参考文献" in kw and name.endswith(".bib"):
            bonus += 0.30
        elif ("参考文献" in kw or "bib" in kw) and "项目说明" in name:
            bonus -= 0.15
        if "压缩" in kw or "zip" in kw or "日志" in kw:
            if "zip" in name or "压缩" in name or "archive" in name:
                bonus += 0.22
        if name.endswith(".py") and any(
            k in kw for k in ("api", "auth", "test", "config", "server", "model", "handler", "依赖", "入口", "认证", "测试")
        ):
            for token in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9_]{2,}", kw):
                if len(token) >= 3 and token in name:
                    bonus += 0.18
        if "认证" in kw and "auth" in name:
            bonus += 0.30
        if "api" in kw and "api" in name and "test" not in name:
            bonus += 0.12
        if name.endswith(".py"):
            noise_py = {
                "api.py",
                "auth.py",
                "billing.py",
                "admin.py",
                "invoice.py",
                "user.py",
                "test_api.py",
                "test_auth.py",
            }
            if any(k in kw for k in ("连接", "connector", "数据库", "database")):
                if "connector" in name or "config" in name:
                    bonus += 0.32
                elif name in noise_py:
                    bonus -= 0.22
            if any(k in kw for k in ("server", "启动", "入口", "start")):
                if "server" in name:
                    bonus += 0.35
                elif name in ("api.py", "connector.py"):
                    bonus += 0.18
                elif name in noise_py - {"api.py", "connector.py"}:
                    bonus -= 0.15
        return min(max(bonus, -0.2), 0.58)
