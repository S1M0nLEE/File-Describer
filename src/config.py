"""Global configuration for FileKG."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional
import os


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


@dataclass
class Config:
    """Central configuration; paths relative to project root unless absolute."""

    project_root: Path = field(default_factory=_project_root)
    data_root: Path = field(default_factory=lambda: _project_root() / "data" / "datasets")
    evaluation_dir: Path = field(default_factory=lambda: _project_root() / "data" / "evaluation")
    chroma_persist_dir: str = "data/chroma"
    local_graph_path: str = "data/local_graph.json"

    # auto: try Neo4j, fall back to local JSON | neo4j | local
    graph_backend: str = "auto"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "filekg123"

    # Skip CLIP-based relation during indexing (faster; enable for image datasets)
    skip_visual_similarity: bool = True

    embedding_model_name: str = "BAAI/bge-small-zh-v1.5"
    clip_model_name: str = "openai/clip-vit-base-patch32"

    sim_threshold: float = 0.85
    sim_topk: int = 5
    near_in_time_window_min: int = 10
    near_in_time_max_edges_per_cluster: int = 20

    summary_max_chars: int = 512
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "phi3:mini"
    use_llm_summary: bool = False
    use_llm_query_parse: bool = False

    # Ranker: vector_score 为主，其余信号为有界加分（避免 BM25/图种子压过语义相关）
    alpha: float = 1.0
    beta: float = 0.12
    gamma: float = 0.04
    delta: float = 0.06
    max_aux_boost: float = 0.06
    min_graph_expand_vector: float = 0.38
    graph_discovery_boost: float = 0.05

    # Hybrid retrieval (vector + BM25 seeds, graph expansion)
    use_hybrid_seeds: bool = True
    vector_seed_top_n: int = 120
    bm25_seed_top_n: int = 60
    bm25_fusion_weight: float = 0.08
    seed_boost: float = 0.0
    max_graph_hops: int = 2
    min_qrel_similarity: float = 0.42
    metadata_filter_hard: bool = False

    relation_weights: Optional[Dict[str, float]] = None

    def __post_init__(self) -> None:
        if not self.data_root.is_absolute():
            self.data_root = self.project_root / self.data_root
        if not self.evaluation_dir.is_absolute():
            self.evaluation_dir = self.project_root / self.evaluation_dir
        if not Path(self.chroma_persist_dir).is_absolute():
            self.chroma_persist_dir = str(self.project_root / self.chroma_persist_dir)
        self.graph_backend = os.environ.get("FILEKG_GRAPH_BACKEND", self.graph_backend)
        if not Path(self.local_graph_path).is_absolute():
            self.local_graph_path = str(self.project_root / self.local_graph_path)
        self.neo4j_uri = os.environ.get("NEO4J_URI", self.neo4j_uri)
        self.neo4j_user = os.environ.get("NEO4J_USER", self.neo4j_user)
        self.neo4j_password = os.environ.get("NEO4J_PASSWORD", self.neo4j_password)
        skip_vis = os.environ.get("FILEKG_SKIP_VISUAL", "")
        if skip_vis.lower() in ("0", "false", "no"):
            self.skip_visual_similarity = False
        if self.relation_weights is None:
            self.relation_weights = {
                "SIMILAR_TO": 0.8,
                "IN_FOLDER": 0.7,
                "SAME_TYPE": 0.4,
                "NEAR_IN_TIME": 0.5,
                "DEPENDS_ON": 0.9,
                "REFERENCES": 0.6,
                "WORKFLOW_WITH": 0.6,
                "VISUALLY_SIMILAR_TO": 0.5,
                "HAS_VERSION": 0.3,
                "CONTAINS": 0.5,
                "BELONGS_TO_PROJECT": 0.6,
                "TAGGED_WITH": 0.5,
            }


def get_config() -> Config:
    return Config()
