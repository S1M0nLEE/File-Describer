from __future__ import annotations

from pydantic import BaseModel, Field


class IndexRequest(BaseModel):
    path: str
    clear: bool = False
    max_files: int | None = None
    multimodal: bool | None = None


class IndexOptionsRequest(BaseModel):
    multimodal: bool
    persist: bool = True


class SearchRequest(BaseModel):
    query: str
    expand_graph: bool = True


class TagRequest(BaseModel):
    file_id: str
    tag: str


class RagChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    history: list[dict[str, str]] = Field(default_factory=list)
    stream: bool = False
    top_k: int | None = Field(None, ge=1, le=50)


class RagRetrieveRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int | None = Field(None, ge=1, le=50)


class LoadStartRequest(BaseModel):
    build_search: bool = Field(True, description="是否加载检索引擎与 RAG")
    build_corpus: bool = Field(False, description="是否构建全量 BM25 语料")
