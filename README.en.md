# FileKG — Personal File Knowledge Graph

> GitHub repo: **File-Describer** · Project codename: **FileKG**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/S1M0nLEE/File-Describer/actions/workflows/ci.yml/badge.svg)](https://github.com/S1M0nLEE/File-Describer/actions/workflows/ci.yml)

English · [中文 README](README.md)

## Overview

FileKG indexes local files as **Virtual File Entities (VFEs)**, discovers **12+ relation types**, and runs **explainable hybrid retrieval**: vector seeds → graph expansion → multi-factor ranking.

### Metrics (synthetic benchmarks — auditable)

See [`docs/evaluation_snapshot.json`](docs/evaluation_snapshot.json) and [`docs/EVALUATION.md`](docs/EVALUATION.md). **Not** production or third-party certified numbers.

| Metric | Value | Setting |
|--------|-------|---------|
| MAP@20 | **0.691** | `filekg_main`, 238 files / 40 queries |
| Serendipity@20 | **0.522** | `code_dependency`, 15 queries |
| Volume relation retention | **97.85%** | After moving 8 files (rate 0.9785) |

Resume wording: [`docs/RESUME.md`](docs/RESUME.md)

## 5-Minute Demo

```bash
git clone https://github.com/S1M0nLEE/File-Describer.git && cd File-Describer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/setup_models.py
python scripts/generate_dataset.py
python scripts/index_directory.py data/dataset --clear
python scripts/run_server.py
# Open http://127.0.0.1:8765 — try query: 实验数据
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Install

**Core**:

```bash
pip install -r requirements.txt
python scripts/setup_models.py
```

**Optional** (vision / multimodal):

```bash
pip install -r requirements-visual.txt
```

## Engineering

- **53** automated tests (`pytest tests/ -q`)
- CI: ruff · unit · e2e · Docker smoke
- Default bind `127.0.0.1`, optional API token — [SECURITY.md](docs/SECURITY.md)

## License

MIT — see [LICENSE](LICENSE).
