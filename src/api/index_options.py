"""索引选项：多模态开关（供 API 与前端同步）。"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

from src.config import config_path, settings


def apply_index_multimodal(multimodal: bool | None = None) -> bool:
    """配置本次/后续索引是否启用多模态。关闭时自动启用快速索引模式。"""
    enabled = settings.rag_index_multimodal if multimodal is None else multimodal
    settings.rag_index_multimodal = enabled
    settings.multimodal_enabled = enabled
    if enabled:
        os.environ.pop("FILEKG_INDEX_FAST", None)
        os.environ["FILEKG_MULTIMODAL_ENABLED"] = "true"
    else:
        os.environ["FILEKG_INDEX_FAST"] = "1"
        os.environ["FILEKG_MULTIMODAL_ENABLED"] = "false"
    return enabled


def persist_index_multimodal(enabled: bool) -> None:
    path = config_path()
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    rag = data.setdefault("rag", {})
    rag["index_multimodal"] = enabled
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
