# FileKG — Personal File Knowledge Graph

> GitHub repo: **File-Describer** · Project codename: **FileKG**  
> 中文: [README.md](README.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/S1M0nLEE/File-Describer/actions/workflows/ci.yml/badge.svg)](https://github.com/S1M0nLEE/File-Describer/actions/workflows/ci.yml)

File systems expose paths and names, not the connections between files—a contract linked to case law, a script that feeds a paper draft, a backup of an older version. **FileKG** builds a **Virtual File Entity (VFE)** graph over local files, discovers **12+ relation types**, and runs **explainable hybrid retrieval**: vector seeds, graph expansion, and multi-factor ranking with relation paths in the response.

Includes a Web UI and REST API.

## Features

- Directory indexing with text/metadata extraction (optional multimodal)
- Pluggable relation pipeline: `SIMILAR_TO`, `DEPENDS_ON`, `REFERENCES`, `HAS_VERSION`, `WORKFLOW_WITH`, etc.
- Natural-language search with intent parsing and graph-expanded results
- Stable `file_id` (volume/inode mode) so edges survive moves and renames
- Optional Neo4j, DeepSeek RAG, vision relations

## Quick start

```bash
git clone https://github.com/S1M0nLEE/File-Describer.git && cd File-Describer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/setup_models.py
python scripts/generate_dataset.py
python scripts/index_directory.py data/dataset --clear
python scripts/run_server.py
# Open http://127.0.0.1:8765 — try: 实验数据
```

Docker demo: `./scripts/docker-demo.sh` or `docker compose up --build -d filekg`

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). High level:

```
Indexing (scan → embed → Chroma + graph)
    → Relation pipeline (metadata, content, version, semantic, workflow, …)
    → Search (intent → seeds → expand → rank) → UI / API
```

## Install

```bash
pip install -r requirements.txt
cp .env.example .env
python scripts/setup_models.py
```

Optional vision/multimodal: `pip install -r requirements-visual.txt`

Default bind address is `127.0.0.1`. See [docs/SECURITY.md](docs/SECURITY.md) before exposing the service.

## Evaluation

Reproducible offline benchmarks (BM25, vector-only, graph-augmented, FileKG-Full). Details: [docs/EVALUATION.md](docs/EVALUATION.md).

**Synthetic** ([evaluation_snapshot.json](docs/evaluation_snapshot.json)): MAP@20 **0.691** on `filekg_main`; Serendipity@20 **0.522** on `code_dependency`.

**Extended synthetic suites** ([extended_benchmark_snapshot.json](docs/extended_benchmark_snapshot.json)): `version_lineage` (version edges), `office_workflow` (co-open / near-time), `doc_references` (citations / archives). CI smoke only — run `python scripts/generate_evaluation_benchmark.py --extended-only` then `run_evaluation.py` for MAP.

**Public real-world** ([real_benchmark_snapshot.json](docs/real_benchmark_snapshot.json)): HippoCamp adam MAP@20 **0.618** (328 files / 123 queries) with `config_hippocamp_eval.yaml`.

```bash
python scripts/run_evaluation.py --config config_hippocamp_eval.yaml \
  --registry real --dataset hippocamp_adam
```

## Development

```bash
pytest tests/ -q
ruff check src tests scripts
```

CI jobs: lint · unit · e2e · **security** · **extended-benchmark** · **config-profiles** · real-benchmark · docker.

## License

MIT — see [LICENSE](LICENSE).
