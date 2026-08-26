# FileKG — Personal File Knowledge Graph

> GitHub repo: **File-Describer** · Project codename: **FileKG**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/S1M0nLEE/File-Describer/actions/workflows/ci.yml/badge.svg)](https://github.com/S1M0nLEE/File-Describer/actions/workflows/ci.yml)

English · [中文 README](README.md)

## Overview

FileKG indexes local files as **Virtual File Entities (VFEs)**, discovers **12+ relation types**, and runs **explainable hybrid retrieval**: vector seeds → graph expansion → multi-factor ranking.

| Metric (synthetic / mixed benchmarks, `tois_eval`) | Value |
|-----------------------------------------------------|-------|
| Relation retention after file moves | **97.9%** |
| SDR@20 (code dependency scenario) | **0.522** |
| MAP@20 (main synthetic benchmark) | **0.691** |

Reproduce locally: `scripts/run_evaluation.py` → results under `data/evaluation/` (gitignored).

## 5-Minute Demo

```bash
git clone https://github.com/S1M0nLEE/File-Describer.git && cd File-Describer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/setup_models.py
python scripts/generate_dataset.py
python scripts/index_directory.py data/dataset --clear
python scripts/run_server.py
# Open http://localhost:8765 — try query: 实验数据
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for module map and data flow.

## Install

**Core** (indexing, search, API):

```bash
pip install -r requirements.txt
```

**Optional** (vision / multimodal, ~2GB+):

```bash
pip install -r requirements-visual.txt
```

## Features

- Multi-format indexing (PDF, DOCX, code, optional image/audio/video)
- Plugin relation pipeline: folder, temporal, dependency, version, similarity, workflow, …
- Chroma ANN + Neo4j or local JSON graph store
- FastAPI + Web UI with graph visualization
- Optional DeepSeek RAG over indexed files

## Tests

```bash
pytest tests/ -q
```

## Roadmap

[docs/ROADMAP.md](docs/ROADMAP.md)

## License

MIT — see [LICENSE](LICENSE).
