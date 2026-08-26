"""启动自检：嵌入模型、存储、可选服务等。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

import httpx

from src.config import settings


def _check(name: str, ok: bool, *, detail: str, severity: str = "info", hint: str = "") -> dict[str, Any]:
    return {
        "id": name,
        "ok": ok,
        "detail": detail,
        "severity": severity,
        "hint": hint,
    }


def run_diagnostics(*, probe_network: bool = False) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    # Python
    checks.append(
        _check(
            "python",
            sys.version_info >= (3, 12),
            detail=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            severity="warning" if sys.version_info < (3, 12) else "info",
            hint="推荐 Python 3.12",
        )
    )

    # Embedding
    try:
        from src.indexing.embedder import Embedder

        Embedder.reset()
        emb = Embedder.get()
        ok = emb.backend != "hash"
        checks.append(
            _check(
                "embedding",
                ok,
                detail=f"backend={emb.backend}, dim={emb.dimension}, model={settings.embedding_model}",
                severity="critical" if not ok else "info",
                hint="运行 python scripts/setup_models.py 或设置 HF_ENDPOINT 镜像",
            )
        )
    except Exception as e:
        checks.append(
            _check(
                "embedding",
                False,
                detail=str(e),
                severity="critical",
                hint="pip install sentence-transformers 或 fastembed",
            )
        )

    # Graph store
    graph_path = settings.data_dir / "graph_store.json"
    graph_exists = graph_path.exists() and graph_path.stat().st_size > 2
    checks.append(
        _check(
            "graph_index",
            graph_exists,
            detail=f"path={graph_path}, size={graph_path.stat().st_size if graph_exists else 0} bytes",
            severity="warning" if not graph_exists else "info",
            hint="python scripts/generate_dataset.py && python scripts/index_directory.py data/dataset --clear",
        )
    )

    # Chroma
    chroma_dir = Path(settings.chroma_dir)
    chroma_ok = chroma_dir.exists() and any(chroma_dir.iterdir()) if chroma_dir.exists() else False
    checks.append(
        _check(
            "chroma_index",
            chroma_ok,
            detail=f"path={chroma_dir}",
            severity="warning" if not chroma_ok else "info",
            hint="索引目录后会自动创建 Chroma 数据",
        )
    )

    # Disk space (data dir)
    try:
        usage = shutil.disk_usage(settings.data_dir if settings.data_dir.exists() else Path("."))
        free_gb = usage.free / (1024**3)
        checks.append(
            _check(
                "disk_free",
                free_gb > 1.0,
                detail=f"{free_gb:.1f} GB free",
                severity="warning" if free_gb <= 1.0 else "info",
                hint="索引大目录前请保留足够磁盘空间",
            )
        )
    except OSError as e:
        checks.append(_check("disk_free", True, detail=str(e), severity="info"))

    # DeepSeek RAG
    rag_ok = bool(settings.deepseek_enabled and settings.deepseek_api_key)
    checks.append(
        _check(
            "deepseek_rag",
            rag_ok,
            detail="configured" if rag_ok else "disabled or missing DEEPSEEK_API_KEY",
            severity="info",
            hint="在 .env 设置 DEEPSEEK_API_KEY 并开启 deepseek.enabled",
        )
    )

    # Ollama (optional)
    ollama_ok = False
    if probe_network and settings.llm_enabled:
        try:
            r = httpx.get(f"{settings.llm_ollama_base.rstrip('/')}/api/tags", timeout=2.0)
            ollama_ok = r.status_code == 200
        except Exception:
            ollama_ok = False
    checks.append(
        _check(
            "ollama",
            ollama_ok if probe_network else True,
            detail="reachable" if ollama_ok else ("skipped" if not probe_network else "unreachable"),
            severity="info",
            hint="多模态/LLM 意图解析需本地 Ollama",
        )
    )

    # Neo4j optional
    neo4j_configured = bool(settings.neo4j_uri)
    checks.append(
        _check(
            "neo4j",
            True,
            detail=settings.neo4j_uri if neo4j_configured else "using local JSON graph",
            severity="info",
            hint="可选 docker compose up neo4j",
        )
    )

    critical_fail = any(c["severity"] == "critical" and not c["ok"] for c in checks)
    warning_fail = any(c["severity"] == "warning" and not c["ok"] for c in checks)
    return {
        "ok": not critical_fail,
        "ready_for_search": graph_exists and chroma_ok and not critical_fail,
        "warnings": warning_fail,
        "checks": checks,
        "manual_load": settings.api_manual_load,
        "fast_startup": settings.api_fast_startup,
    }
