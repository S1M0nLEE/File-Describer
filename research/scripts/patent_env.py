"""专利实施例评测环境变量（供子进程注入，避免 import 顺序问题）。"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def env_for_profile(profile: str) -> dict[str, str]:
    base = dict(os.environ)
    base["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    if profile == "patent_full":
        base["FILEKG_CONFIG"] = str(ROOT / "config_patent_full.yaml")
        base["FILEKG_EVAL_PROFILE"] = "patent_full"
        base["FILEKG_LLM_ENABLED"] = "true"
        base["FILEKG_VISUAL_ENABLED"] = "true"
    elif profile == "hippocamp_en":
        base["FILEKG_CONFIG"] = str(ROOT / "config_patent_hippocamp.yaml")
        base["FILEKG_EVAL_PROFILE"] = "hippocamp_en"
        base["FILEKG_LLM_ENABLED"] = "true"
        base["FILEKG_VISUAL_ENABLED"] = "true"
        base["FILEKG_EMBEDDING_MODEL"] = "BAAI/bge-small-en-v1.5"
    elif profile == "default":
        base["FILEKG_CONFIG"] = str(ROOT / "config.yaml")
        base["FILEKG_EVAL_PROFILE"] = "default"
    else:
        raise ValueError(profile)
    return base
