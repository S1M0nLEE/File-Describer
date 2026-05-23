"""本地 FileKG 检索 + DeepSeek 生成（RAG）。"""
from __future__ import annotations

import logging
from typing import Any

from src.config import settings
from src.indexing.embedder import Embedder
from src.llm.deepseek_client import DeepSeekClient
from src.rag.description_retriever import DescriptionRetriever
from src.search.engine import SearchEngine
from src.storage.chroma_store import ChromaStore
from src.storage.factory import GraphStore

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是个人文件知识助手。仅根据「检索到的文件节点 Description（索引时生成的摘要）」回答用户问题。
规则：
1. 若上下文不足以回答，明确说明缺少哪些信息，不要编造文件内容。
2. 回答使用简体中文，条理清晰。
3. 在末尾列出引用来源，格式：来源: 文件名 (完整路径)。
4. 可结合多个节点的 Description 归纳；路径、文件名也是重要线索。"""


class RagPipeline:
    def __init__(self, graph: GraphStore, chroma: ChromaStore, search: SearchEngine | None = None) -> None:
        self.graph = graph
        self.chroma = chroma
        self.search = search
        self.embedder = Embedder.get()
        self.llm = DeepSeekClient()
        self._desc_retriever = DescriptionRetriever(graph, chroma, self.embedder)

    def retrieve(self, question: str, *, top_k: int | None = None) -> list[dict[str, Any]]:
        k = top_k if top_k is not None else settings.rag_top_k
        k = min(max(int(k), 1), settings.rag_top_k_max)
        hits = self._desc_retriever.retrieve(question, top_k=k)

        if settings.rag_use_graph_search and self.search and len(hits) < k:
            try:
                graph_hits = self.search.search(question, expand_graph=False)
                seen = {h["file_id"] for h in hits}
                for r in (graph_hits.get("results") or [])[:5]:
                    fid = r.get("file_id")
                    if not fid or fid in seen:
                        continue
                    summary = r.get("summary") or r.get("name", "")
                    hits.append(
                        {
                            "file_id": fid,
                            "path": r.get("path", ""),
                            "name": r.get("name", ""),
                            "description": summary,
                            "document": summary[: settings.rag_chunk_max_chars],
                            "similarity": float(r.get("score", 0.4)),
                            "source": "graph_fallback",
                        }
                    )
                    seen.add(fid)
            except Exception as e:
                logger.debug("图检索补充失败: %s", e)

        return hits[:k]

    def build_context(self, chunks: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for i, c in enumerate(chunks, 1):
            text = (c.get("document") or "").strip()
            if not text:
                continue
            rank = c.get("rank", i)
            parts.append(
                f"[{rank}] 节点: {c.get('name', '')}\n"
                f"路径: {c.get('path', '')}\n"
                f"相关度: {c.get('similarity', 0):.3f} (score={c.get('score', '-')})\n"
                f"Description:\n{text[:settings.rag_chunk_max_chars]}\n"
            )
        return "\n---\n".join(parts) if parts else "（未检索到相关本地文件片段，请先建立索引。）"

    def ask(
        self,
        question: str,
        *,
        history: list[dict[str, str]] | None = None,
        stream: bool = False,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        if not self.llm.is_available():
            return {
                "answer": "",
                "error": "DeepSeek 未配置：请设置 DEEPSEEK_API_KEY 并 pip install openai",
                "sources": [],
            }

        k = top_k if top_k is not None else settings.rag_top_k
        k = min(max(int(k), 1), settings.rag_top_k_max)
        chunks = self.retrieve(question, top_k=k)
        context = self.build_context(chunks)
        user_content = f"问题：{question}\n\n--- 本地检索上下文 ---\n{context}"

        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            for m in history[-6:]:
                if m.get("role") in ("user", "assistant") and m.get("content"):
                    messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user_content})

        if stream:
            return {
                "stream": self.llm.chat(messages, stream=True),
                "sources": self._format_sources(chunks),
                "context_chunks": len(chunks),
                "top_k": k,
            }

        answer = self.llm.chat(messages, stream=False)
        return {
            "answer": answer,
            "sources": self._format_sources(chunks),
            "context_chunks": len(chunks),
            "top_k": k,
            "model": settings.deepseek_model,
        }

    @staticmethod
    def _format_sources(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        seen: set[str] = set()
        for c in chunks:
            path = c.get("path") or ""
            if path in seen:
                continue
            seen.add(path)
            sources.append(
                {
                    "rank": c.get("rank"),
                    "name": c.get("name", ""),
                    "path": path,
                    "file_id": c.get("file_id"),
                    "similarity": round(float(c.get("similarity", 0)), 4),
                    "score": c.get("score"),
                }
            )
        return sources
