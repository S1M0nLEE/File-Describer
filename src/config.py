from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_YAML = _ROOT / "config.yaml"

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass


def config_path() -> Path:
    raw = os.environ.get("FILEKG_CONFIG", "")
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else _ROOT / p
    return _DEFAULT_YAML


def _load_yaml(path: Path | None = None) -> dict[str, Any]:
    p = path or config_path()
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def reload_settings(path: Path | str | None = None) -> "Settings":
    """切换配置文件（评测 profile 用）。"""
    global settings, _yaml
    if path is not None:
        os.environ["FILEKG_CONFIG"] = str(path)
    _yaml = _load_yaml()
    settings = Settings()
    return settings


_yaml = _load_yaml()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FILEKG_", extra="ignore")

    neo4j_uri: str = Field(default=_yaml.get("neo4j", {}).get("uri", "bolt://localhost:7687"))
    neo4j_user: str = Field(default=_yaml.get("neo4j", {}).get("user", "neo4j"))
    neo4j_password: str = Field(default=_yaml.get("neo4j", {}).get("password", "filekg123"))

    chroma_dir: str = Field(
        default=str(_ROOT / _yaml.get("chroma", {}).get("persist_directory", "./data/chroma"))
    )

    embedding_model: str = Field(
        default=_yaml.get("embeddings", {}).get("model_name", "BAAI/bge-small-zh-v1.5")
    )
    embedding_dim: int = Field(default=_yaml.get("embeddings", {}).get("dimension", 512))
    embedding_raw_dim: int = Field(default=int(_yaml.get("embeddings", {}).get("raw_dimension", 384)))
    embedding_use_projection: bool = Field(
        default=_yaml.get("embeddings", {}).get("use_projection", True)
    )
    embedding_backend: str = Field(
        default=_yaml.get("embeddings", {}).get("backend", "auto")
    )

    vfe_id_mode: str = Field(default=_yaml.get("vfe", {}).get("id_mode", "volume"))
    vfe_memory_capacity: int = Field(default=int(_yaml.get("vfe", {}).get("memory_capacity", 50)))
    vfe_near_time_window_seconds: float = Field(
        default=float(_yaml.get("vfe", {}).get("near_time_window_seconds", 300))
    )
    vfe_relation_ema_alpha: float = Field(
        default=float(_yaml.get("vfe", {}).get("relation_ema_alpha", 0.7))
    )
    index_purge_days: int = Field(default=int(_yaml.get("index", {}).get("purge_days", 365)))

    cold_start_near_in_time_events: int = Field(
        default=int(_yaml.get("cold_start", {}).get("near_in_time_events", 50))
    )
    cold_start_workflow_events: int = Field(
        default=int(_yaml.get("cold_start", {}).get("workflow_events", 150))
    )
    consistency_interval_hours: int = Field(
        default=int(_yaml.get("consistency", {}).get("interval_hours", 24))
    )
    workflow_max_gap: int = Field(default=int(_yaml.get("workflow", {}).get("max_gap", 5)))

    similar_threshold: float = Field(default=_yaml.get("index", {}).get("similar_threshold", 0.85))
    similar_top_k: int = Field(default=_yaml.get("index", {}).get("similar_top_k", 5))
    index_watch_roots: list[str] = Field(
        default_factory=lambda: _yaml.get("index", {}).get("watch_roots", [])
    )
    near_time_window_minutes: int = Field(
        default=_yaml.get("index", {}).get("near_time_window_minutes", 10)
    )
    near_time_max_pairs: int = Field(default=_yaml.get("index", {}).get("near_time_max_pairs", 20))
    dormant_days: int = Field(default=_yaml.get("index", {}).get("dormant_days", 30))
    deprecated_observation_days: int = Field(
        default=_yaml.get("index", {}).get("deprecated_observation_days", 7)
    )

    llm_enabled: bool = Field(default=_yaml.get("llm", {}).get("enabled", True))
    llm_ollama_base: str = Field(
        default=_yaml.get("llm", {}).get("ollama_base", "http://localhost:11434")
    )
    llm_model: str = Field(default=_yaml.get("llm", {}).get("model", "phi3:mini"))

    deepseek_enabled: bool = Field(default=_yaml.get("deepseek", {}).get("enabled", True))
    deepseek_api_key: str = Field(
        default=os.environ.get("DEEPSEEK_API_KEY", "")
        or _yaml.get("deepseek", {}).get("api_key", "")
    )
    deepseek_base_url: str = Field(
        default=_yaml.get("deepseek", {}).get("base_url", "https://api.deepseek.com")
    )
    deepseek_model: str = Field(
        default=_yaml.get("deepseek", {}).get("model", "deepseek-v4-pro")
    )
    deepseek_temperature: float = Field(
        default=float(_yaml.get("deepseek", {}).get("temperature", 0.3))
    )
    deepseek_max_tokens: int = Field(
        default=int(_yaml.get("deepseek", {}).get("max_tokens", 4096))
    )
    deepseek_reasoning_effort: str = Field(
        default=_yaml.get("deepseek", {}).get("reasoning_effort", "high")
    )
    deepseek_thinking_enabled: bool = Field(
        default=_yaml.get("deepseek", {}).get("thinking_enabled", True)
    )

    rag_top_k: int = Field(default=int(_yaml.get("rag", {}).get("top_k", 10)))
    rag_top_k_max: int = Field(default=int(_yaml.get("rag", {}).get("top_k_max", 50)))
    rag_chunk_max_chars: int = Field(default=int(_yaml.get("rag", {}).get("chunk_max_chars", 1200)))
    rag_use_graph_search: bool = Field(
        default=_yaml.get("rag", {}).get("use_graph_search", False)
    )
    rag_desc_pool: int = Field(default=int(_yaml.get("rag", {}).get("desc_pool", 800)))
    rag_index_roots: list[str] = Field(
        default_factory=lambda: _yaml.get("rag", {}).get("index_roots", [])
    )
    rag_max_files_per_root: int | None = Field(
        default=_yaml.get("rag", {}).get("max_files_per_root")
    )
    rag_index_multimodal: bool = Field(
        default=_yaml.get("rag", {}).get("index_multimodal", False)
    )

    visual_enabled: bool = Field(default=_yaml.get("visual", {}).get("enabled", True))
    visual_threshold: float = Field(default=_yaml.get("visual", {}).get("threshold", 0.9))
    visual_model: str = Field(
        default=_yaml.get("visual", {}).get("model", "openai/clip-vit-base-patch32")
    )
    visual_fusion_mode: str = Field(
        default=_yaml.get("visual", {}).get("fusion_mode", "multi_route")
    )
    visual_doc_backend: str = Field(
        default=_yaml.get("visual", {}).get("doc_backend", "auto")
    )
    visual_layoutlm_model: str = Field(
        default=_yaml.get("visual", {}).get("layoutlm_model", "microsoft/layoutlmv3-base")
    )
    visual_theta_text: float = Field(default=_yaml.get("visual", {}).get("theta_text", 0.75))
    visual_theta_doc: float = Field(default=_yaml.get("visual", {}).get("theta_doc", 0.7))
    visual_theta_align_low: float = Field(
        default=_yaml.get("visual", {}).get("theta_align_low", 0.4)
    )
    visual_theta_align_med: float = Field(
        default=_yaml.get("visual", {}).get("theta_align_med", 0.55)
    )
    visual_theta_visual_high: float = Field(
        default=_yaml.get("visual", {}).get("theta_visual_high", 0.9)
    )
    visual_theta_visual_med: float = Field(
        default=_yaml.get("visual", {}).get("theta_visual_med", 0.75)
    )
    visual_phash_threshold: int = Field(default=_yaml.get("visual", {}).get("phash_threshold", 6))
    visual_prefilter_threshold: float = Field(
        default=_yaml.get("visual", {}).get("prefilter_threshold", 0.55)
    )
    visual_emit_low_confidence: bool = Field(
        default=_yaml.get("visual", {}).get("emit_low_confidence", False)
    )
    visual_merge_near_duplicate_results: bool = Field(
        default=_yaml.get("visual", {}).get("merge_near_duplicate_results", True)
    )

    patent_visual_only: bool = Field(
        default=_yaml.get("patent", {}).get("visual_only", False)
    )

    multimodal_enabled: bool = Field(
        default=_yaml.get("multimodal", {}).get("enabled", True)
    )
    multimodal_whisper_enabled: bool = Field(
        default=_yaml.get("multimodal", {}).get("whisper_enabled", True)
    )
    multimodal_whisper_model: str = Field(
        default=_yaml.get("multimodal", {}).get("whisper_model", "")
    )
    multimodal_faster_whisper_size: str = Field(
        default=_yaml.get("multimodal", {}).get("faster_whisper_size", "base")
    )
    multimodal_vision_caption_enabled: bool = Field(
        default=_yaml.get("multimodal", {}).get("vision_caption_enabled", True)
    )
    multimodal_vision_llm_model: str = Field(
        default=_yaml.get("multimodal", {}).get("vision_llm_model", "moondream")
    )
    multimodal_visual_index_enabled: bool = Field(
        default=_yaml.get("multimodal", {}).get("visual_index_enabled", True)
    )
    multimodal_fuse_visual_search: bool = Field(
        default=_yaml.get("multimodal", {}).get("fuse_visual_search", True)
    )
    multimodal_video_max_frames: int = Field(
        default=_yaml.get("multimodal", {}).get("video_max_frames", 5)
    )
    multimodal_max_audio_bytes: int = Field(
        default=_yaml.get("multimodal", {}).get("max_audio_bytes", 52_428_800)
    )
    multimodal_max_video_bytes: int = Field(
        default=_yaml.get("multimodal", {}).get("max_video_bytes", 209_715_200)
    )
    multimodal_max_image_bytes: int = Field(
        default=_yaml.get("multimodal", {}).get("max_image_bytes", 15_728_640)
    )
    multimodal_ollama_timeout: float = Field(
        default=float(_yaml.get("multimodal", {}).get("ollama_timeout", 300))
    )

    workflow_collection_enabled: bool = Field(
        default=_yaml.get("workflow", {}).get("collection_enabled", True)
    )
    workflow_min_support: int = Field(default=_yaml.get("workflow", {}).get("min_support", 2))

    seed_top_n: int = Field(default=_yaml.get("search", {}).get("seed_top_n", 30))
    result_top_n: int = Field(default=_yaml.get("search", {}).get("result_top_n", 20))
    graph_hops: int = Field(default=_yaml.get("search", {}).get("graph_hops", 1))

    w_semantic: float = Field(default=_yaml.get("search", {}).get("weights", {}).get("semantic", 0.50))
    w_graph: float = Field(default=_yaml.get("search", {}).get("weights", {}).get("graph", 0.20))
    w_time: float = Field(default=_yaml.get("search", {}).get("weights", {}).get("time", 0.10))
    w_rule: float = Field(default=_yaml.get("search", {}).get("weights", {}).get("rule", 0.15))
    w_personal: float = Field(default=_yaml.get("search", {}).get("weights", {}).get("personal", 0.05))
    time_decay_lambda: float = Field(default=_yaml.get("search", {}).get("time_decay_lambda", 0.01))

    relation_weights: dict[str, float] = Field(
        default_factory=lambda: _yaml.get("relation_weights", {})
    )

    api_fast_startup: bool = Field(
        default=_yaml.get("api", {}).get("fast_startup", True)
    )
    api_preload_graph: bool = Field(
        default=_yaml.get("api", {}).get("preload_graph", False)
    )
    api_manual_load: bool = Field(
        default=_yaml.get("api", {}).get("manual_load", True)
    )
    api_disk_cache: bool = Field(default=_yaml.get("api", {}).get("disk_cache", True))
    api_persist_on_shutdown: bool = Field(
        default=_yaml.get("api", {}).get("persist_on_shutdown", False)
    )
    api_heartbeat_enabled: bool = Field(
        default=_yaml.get("api", {}).get("heartbeat_enabled", True)
    )
    api_heartbeat_interval_minutes: int = Field(
        default=int(_yaml.get("api", {}).get("heartbeat_interval_minutes", 30))
    )
    api_heartbeat_initial_delay_seconds: int = Field(
        default=int(_yaml.get("api", {}).get("heartbeat_initial_delay_seconds", 90))
    )
    api_heartbeat_skip_relations: bool = Field(
        default=_yaml.get("api", {}).get("heartbeat_skip_relations", True)
    )

    data_dir: Path = Field(default=_ROOT / "data")

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        Path(self.chroma_dir).mkdir(parents=True, exist_ok=True)


settings = Settings()
