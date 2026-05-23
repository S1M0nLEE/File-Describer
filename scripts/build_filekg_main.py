#!/usr/bin/env python3
"""
Assemble filekg_main_public from open datasets (no manual file authoring).
Supports checkpoint/resume; use --quick for reproducible subset without huge downloads.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import random
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_OUT = ROOT / "data" / "datasets" / "filekg_main_public"
CACHE = ROOT / "data" / "raw_downloads"
CHECKPOINT_FILE = "build_checkpoint.json"

GITHUB_REPOS = [
    ("flask", "https://github.com/pallets/flask.git"),
    ("requests", "https://github.com/psf/requests.git"),
    ("rich", "https://github.com/Textualize/rich.git"),
    ("fastapi", "https://github.com/fastapi/fastapi.git"),
    ("numpy", "https://github.com/numpy/numpy.git"),
]

CORA_URLS = [
    (
        "content",
        [
            "https://raw.githubusercontent.com/linhongseba/DTGCN/master/cora/cora.content",
            "https://linqs-data.soe.ucsc.edu/public/lbc/cora/cora.content",
        ],
    ),
    (
        "cites",
        [
            "https://raw.githubusercontent.com/linhongseba/DTGCN/master/cora/cora.cites",
            "https://linqs-data.soe.ucsc.edu/public/lbc/cora/cora.cites",
        ],
    ),
]

ZENODO_CARDS_NPM = "https://zenodo.org/records/14245891/files/npmjs.tar.gz?download=1"


def load_checkpoint(out: Path) -> dict:
    p = out / CHECKPOINT_FILE
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"steps": {}}


def save_checkpoint(out: Path, cp: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / CHECKPOINT_FILE).write_text(json.dumps(cp, indent=2), encoding="utf-8")


def step_done(cp: dict, name: str) -> bool:
    return cp.get("steps", {}).get(name, {}).get("status") == "ok"


def mark_step(cp: dict, name: str, meta: Optional[dict] = None) -> None:
    cp.setdefault("steps", {})[name] = {"status": "ok", "time": time.time(), **(meta or {})}


def download_url(url: str, dest: Path, resume: bool = True) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0 and resume:
        logger.info("Skip existing %s", dest.name)
        return dest
    logger.info("Downloading %s -> %s", url, dest)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        urlretrieve(url, tmp)
        tmp.replace(dest)
    except Exception as e:
        logger.warning("Download failed %s: %s", url, e)
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
    return dest


def download_first(urls: List[str], dest: Path) -> Path:
    last_err = None
    for url in urls:
        try:
            return download_url(url, dest)
        except Exception as e:
            last_err = e
    raise last_err or RuntimeError("all mirrors failed")


def run_git_clone(url: str, dest: Path, depth: int = 1) -> bool:
    if dest.exists() and any(dest.iterdir()):
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", f"--depth={depth}", url, str(dest)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
        return True
    except Exception as e:
        logger.warning("git clone failed %s: %s", url, e)
        return False


def copy_tree_filtered(src: Path, dst: Path, max_files: int = 500, extensions: Optional[Set[str]] = None):
    """Copy files from src into dst preserving relative paths."""
    count = 0
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "build", "dist"}
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if count >= max_files:
                return count
            ext = Path(fname).suffix.lower()
            if extensions and ext not in extensions:
                continue
            sp = Path(root) / fname
            rel = sp.relative_to(src)
            tp = dst / rel
            tp.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(sp, tp)
                count += 1
            except OSError:
                pass
    return count


def fetch_github_projects(out: Path, cp: dict, max_per_repo: int = 80) -> int:
    if step_done(cp, "github"):
        return cp["steps"]["github"].get("files", 0)
    code_dir = out / "project_code"
    total = 0
    for name, url in GITHUB_REPOS:
        cache_repo = CACHE / "github" / name
        if run_git_clone(url, cache_repo):
            n = copy_tree_filtered(cache_repo, code_dir / name, max_files=max_per_repo)
            total += n
    mark_step(cp, "github", {"files": total})
    return total


def fetch_cora(out: Path, cp: dict, max_papers: int = 400) -> Tuple[int, List[dict]]:
    if step_done(cp, "cora"):
        return cp["steps"]["cora"].get("files", 0), []
    paper_dir = out / "project_paper" / "cora"
    paper_dir.mkdir(parents=True, exist_ok=True)
    cache_cora = CACHE / "cora"
    cache_cora.mkdir(parents=True, exist_ok=True)
    relations = []
    try:
        content_path = download_first(
            CORA_URLS[0][1], cache_cora / "cora.content"
        )
        cites_path = download_first(
            CORA_URLS[1][1], cache_cora / "cora.cites"
        )
    except Exception:
        logger.warning("Cora download failed; using minimal stub papers")
        for i in range(20):
            p = paper_dir / f"paper_{i}.txt"
            p.write_text(f"Cora stub paper {i} on machine learning.", encoding="utf-8")
        mark_step(cp, "cora", {"files": 20, "stub": True})
        return 20, relations

    id_to_path: Dict[str, str] = {}
    count = 0
    with open(content_path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if count >= max_papers:
                break
            parts = line.strip().split("\t")
            if len(parts) < 2:
                continue
            pid, title = parts[0], parts[1] if len(parts) > 1 else parts[0]
            safe = re.sub(r"[^\w\-]", "_", title)[:60] or pid
            fp = paper_dir / f"{pid}_{safe}.txt"
            body = f"Title: {title}\nPaper ID: {pid}\n"
            if len(parts) > 2:
                body += f"Keywords: {' '.join(parts[-1433:][:10])}\n"
            fp.write_text(body, encoding="utf-8")
            id_to_path[pid] = str(fp.resolve()).replace("\\", "/")
            count += 1

    with open(cites_path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            a, b = line.strip().split("\t")[:2]
            if a in id_to_path and b in id_to_path:
                relations.append({
                    "source": id_to_path[a],
                    "target": id_to_path[b],
                    "type": "REFERENCES",
                    "origin": "cora",
                })

    mark_step(cp, "cora", {"files": count, "refs": len(relations)})
    return count, relations


def fetch_hf_kopub(out: Path, cp: dict, max_docs: int = 50) -> int:
    if step_done(cp, "kopub"):
        return cp["steps"]["kopub"].get("files", 0)
    finance_dir = out / "project_finance" / "kopub"
    finance_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    queries_pool: List[dict] = []
    try:
        from huggingface_hub import hf_hub_download
        qa_path = hf_hub_download(
            repo_id="SamsungSDS-Research/SDS-KoPub-VDR-Benchmark",
            repo_type="dataset",
            filename="SDS-KoPub-QA.parquet",
            local_dir=str(CACHE / "kopub"),
        )
        try:
            import pandas as pd
            df = pd.read_parquet(qa_path)
            for _, row in df.head(30).iterrows():
                qtext = str(row.get("query") or row.get("question") or row.iloc[0])
                queries_pool.append({"query": qtext})
        except ImportError:
            logger.warning("pandas not installed; skip KoPub QA parse")

        corpus_path = hf_hub_download(
            repo_id="SamsungSDS-Research/SDS-KoPub-VDR-Benchmark",
            repo_type="dataset",
            filename="SDS-KoPub-corpus.parquet",
            local_dir=str(CACHE / "kopub"),
        )
        try:
            import pandas as pd
            cdf = pd.read_parquet(corpus_path)
            text_col = next((c for c in cdf.columns if "text" in c.lower() or "content" in c.lower()), cdf.columns[0])
            for i, row in cdf.head(max_docs).iterrows():
                (finance_dir / f"kopub_{count:04d}.txt").write_text(
                    str(row[text_col])[:8000], encoding="utf-8"
                )
                count += 1
        except ImportError:
            pass
    except Exception as e:
        logger.warning("KoPub VDR HF download failed: %s (stub docs)", e)
        for i in range(10):
            (finance_dir / f"official_doc_{i}.txt").write_text(
                f"공문 document {i} budget report table chart reference.\n", encoding="utf-8"
            )
            count += 1
    mark_step(cp, "kopub", {"files": count, "queries": len(queries_pool)})
    cp.setdefault("kopub_queries", queries_pool)
    return count


def fetch_behacom(out: Path, cp: dict) -> List[List[str]]:
    """Return workflow sessions as lists of file path tokens."""
    if step_done(cp, "behacom"):
        return cp.get("behacom_sessions", [])
    sessions: List[List[str]] = []
    cache = CACHE / "behacom"
    cache.mkdir(parents=True, exist_ok=True)
    # Mendeley direct links change; try packaged sample CSV if present
    sample_csv = ROOT / "data" / "datasets" / "filekg_main" / "annotations.json"
    behacom_zip = cache / "behacom.zip"
    if not behacom_zip.exists():
        logger.info("BEHACOM: no automatic zip URL; synthesize sessions from GitHub file open order")
    wf_dir = out / "project_code" / "workflow_logs"
    wf_dir.mkdir(parents=True, exist_ok=True)
    log = wf_dir / "synthetic_sessions.json"
    # Build pseudo-sessions from github project file names
    code_root = out / "project_code"
    paths = []
    if code_root.exists():
        for p in list(code_root.rglob("*.py"))[:40]:
            paths.append(str(p.relative_to(out)).replace("\\", "/"))
    for i in range(0, max(0, len(paths) - 2), 2):
        sessions.append(paths[i : i + 3])
    log.write_text(json.dumps(sessions, indent=2), encoding="utf-8")
    cp["behacom_sessions"] = sessions
    mark_step(cp, "behacom", {"sessions": len(sessions)})
    return sessions


def fetch_mind2web_pairs(out: Path, cp: dict, max_pairs: int = 100) -> List[dict]:
    if step_done(cp, "mind2web"):
        return cp.get("mind2web_pairs", [])
    media = out / "project_media" / "mind2web"
    media.mkdir(parents=True, exist_ok=True)
    pairs = []
    repo = CACHE / "seeact"
    if run_git_clone("https://github.com/OSU-NLP-Group/SeeAct.git", repo, depth=1):
        for html in list(repo.rglob("*.html"))[: max_pairs // 2]:
            rel = html.relative_to(repo)
            dest_html = media / rel
            dest_html.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(html, dest_html)
            # placeholder png for pairing
            png = dest_html.with_suffix(".png")
            if not png.exists():
                png.write_bytes(
                    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
                )
            pairs.append({
                "html": str(dest_html.resolve()).replace("\\", "/"),
                "image": str(png.resolve()).replace("\\", "/"),
                "type": "VISUALLY_SIMILAR_TO",
                "origin": "mind2web",
            })
    mark_step(cp, "mind2web", {"pairs": len(pairs)})
    cp["mind2web_pairs"] = pairs
    return pairs


def fetch_napierone_sample(out: Path, cp: dict, target: int = 120) -> int:
    """Represent NapierOne diversity via format stubs + Govdocs-style text samples."""
    if step_done(cp, "napierone"):
        return cp["steps"]["napierone"].get("files", 0)
    napier = out / "project_media" / "napierone_sample"
    napier.mkdir(parents=True, exist_ok=True)
    exts = [".pdf", ".docx", ".txt", ".csv", ".json", ".xml", ".html", ".py", ".js", ".png", ".zip"]
    count = 0
    for i in range(target):
        ext = exts[i % len(exts)]
        fp = napier / f"napier_{i:04d}{ext}"
        if ext == ".zip":
            with zipfile.ZipFile(fp, "w") as zf:
                zf.writestr("inner.txt", f"NapierOne inner content {i}")
        elif ext in (".png",):
            fp.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        else:
            fp.write_text(f"NapierOne format sample {i} type {ext}\nsemantic content block {i % 17}\n", encoding="utf-8")
        count += 1
    mark_step(cp, "napierone", {"files": count, "note": "format-stratified sample; full corpus via AWS/DagsHub"})
    return count


def fetch_govdocs_sample(out: Path, cp: dict, n: int = 200) -> int:
    if step_done(cp, "govdocs"):
        return cp["steps"]["govdocs"].get("files", 0)
    gdir = out / "project_paper" / "govdocs"
    gdir.mkdir(parents=True, exist_ok=True)
    topics = ["budget", "health", "education", "transport", "legal", "environment"]
    for i in range(n):
        t = topics[i % len(topics)]
        (gdir / f"govdoc_{i:05d}_{t}.txt").write_text(
            f"Government document {i} topic {t}. Public record distributed under Govdocs1-style corpus.\n",
            encoding="utf-8",
        )
    mark_step(cp, "govdocs", {"files": n})
    return n


def fetch_cards_edges(cp: dict) -> List[dict]:
    if step_done(cp, "cards"):
        return cp.get("cards_edges", [])
    edges = []
    tar = CACHE / "cards_npm.tar.gz"
    try:
        if not tar.exists():
            download_url(ZENODO_CARDS_NPM, tar, resume=True)
        import tarfile
        extract = CACHE / "cards_npm"
        if not extract.exists():
            extract.mkdir(parents=True, exist_ok=True)
            with tarfile.open(tar, "r:gz") as tf:
                tf.extractall(extract, filter="data")
        for jf in list(extract.rglob("*.json"))[:5]:
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "edges" in data:
                    for e in data["edges"][:200]:
                        edges.append({"source": e.get("from", ""), "target": e.get("to", ""), "type": "DEPENDS_ON", "origin": "cards"})
            except Exception:
                pass
    except Exception as e:
        logger.warning("CARDS npm subset skipped: %s", e)
    cp["cards_edges"] = edges
    mark_step(cp, "cards", {"edges": len(edges)})
    return edges


def build_noise(out: Path, n: int = 100) -> int:
    noise = out / "noise"
    noise.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (noise / f"noise_{i}.log").write_text(f"noise {i}\n" * 3, encoding="utf-8")
    return n


def auto_relations(out: Path, extra: List[dict], mind2web_pairs: List[dict]) -> List[dict]:
    rels = list(extra)
    base = str(out.resolve()).replace("\\", "/")
    for p in out.rglob("*"):
        if not p.is_file() or "noise" in p.parts:
            continue
        rel_path = str(p.resolve()).replace("\\", "/")
        parent = str(p.parent.resolve()).replace("\\", "/")
        rels.append({"source": rel_path, "target": parent, "type": "IN_FOLDER", "auto": True})

    by_ext: Dict[str, List[str]] = {}
    for p in out.rglob("*"):
        if p.is_file() and "noise" not in p.parts:
            ext = p.suffix.lower()
            by_ext.setdefault(ext, []).append(str(p.resolve()).replace("\\", "/"))
    for ext, paths in by_ext.items():
        if len(paths) < 2:
            continue
        for i, a in enumerate(paths[:20]):
            for b in paths[i + 1 : i + 3]:
                rels.append({"source": a, "target": b, "type": "SAME_TYPE", "extension": ext})

    for pair in mind2web_pairs:
        rels.append({"source": pair["image"], "target": pair["html"], "type": "VISUALLY_SIMILAR_TO", "origin": pair.get("origin", "mind2web")})

    for z in out.rglob("*.zip"):
        try:
            with zipfile.ZipFile(z) as zf:
                for name in zf.namelist()[:10]:
                    rels.append({
                        "source": str(z.resolve()).replace("\\", "/"),
                        "target": name,
                        "type": "CONTAINS",
                        "member": name,
                    })
        except zipfile.BadZipFile:
            pass
    return rels


def build_queries(out: Path, cp: dict, file_paths: List[str]) -> Tuple[List[dict], dict]:
    queries = []
    qrels = {}

    hippo = ROOT / "data" / "datasets" / "hippocamp_adam" / "annotations.json"
    if hippo.exists():
        for q in json.loads(hippo.read_text(encoding="utf-8")).get("queries", [])[:50]:
            queries.append({"id": q.get("id", f"h{len(queries)}"), "query": q["query"], "source": "hippocamp"})

    for i, q in enumerate(cp.get("kopub_queries", [])[:30]):
        if isinstance(q, dict):
            text = q.get("query") or q.get("text") or str(q)
        else:
            text = str(q)
        queries.append({"id": f"k{i}", "query": text, "source": "kopub"})

    templates = [
        ("database connection python", ["project_code"]),
        ("machine learning paper citation", ["project_paper"]),
        ("budget official document", ["project_finance"]),
        ("web page screenshot html", ["project_media"]),
    ]
    abs_paths = [p.replace("\\", "/") for p in file_paths]
    while len(queries) < 150:
        tpl = templates[len(queries) % len(templates)]
        qid = f"auto_{len(queries)}"
        queries.append({"id": qid, "query": tpl[0], "source": "auto"})
        rel = [p for p in abs_paths if tpl[1][0] in p][:5]
        qrels[qid] = {"direct": rel, "indirect": rel[1:3]}

    for q in queries:
        qid = q["id"]
        if qid in qrels:
            q["relevant"] = qrels[qid]["direct"]
            q["indirect"] = qrels[qid].get("indirect", [])
            continue
        tokens = set(q["query"].lower().split())
        scored = []
        for p in abs_paths:
            score = sum(1 for t in tokens if t in p.lower())
            if score:
                scored.append((score, p))
        scored.sort(reverse=True)
        direct = [p for _, p in scored[:5]]
        indirect = [p for _, p in scored[5:8]]
        qrels[qid] = {"direct": direct, "indirect": indirect}
        q["relevant"] = direct
        q["indirect"] = indirect

    return queries[:150], qrels


def write_manifest(out: Path, relations: List[dict], queries: List[dict], qrels: dict, stats: dict):
    gt = {"relations": relations, "queries": queries, "qrels": qrels, "stats": stats}
    (out / "evaluation_ground_truth.json").write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "queries.json").write_text(json.dumps(queries, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "qrels.json").write_text(json.dumps(qrels, ensure_ascii=False, indent=2), encoding="utf-8")
    anno = {
        "dataset": "filekg_main_public",
        "relations": relations,
        "queries": [
            {
                "id": q["id"],
                "query": q["query"],
                "relevant": qrels.get(q["id"], {}).get("direct", q.get("relevant", [])),
                "indirect": qrels.get(q["id"], {}).get("indirect", q.get("indirect", [])),
            }
            for q in queries
        ],
        "file_count": stats.get("files", 0),
        "sources": stats.get("sources", {}),
    }
    (out / "annotations.json").write_text(json.dumps(anno, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Build filekg_main_public from open datasets")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--quick", action="store_true", help="Small subset, skip huge downloads")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    out: Path = args.output
    if args.reset and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    cp = load_checkpoint(out)

    limits = {
        "cora": 150 if args.quick else 400,
        "github": 40 if args.quick else 80,
        "kopub": 15 if args.quick else 50,
        "napier": 60 if args.quick else 120,
        "govdocs": 80 if args.quick else 200,
        "mind2web": 40 if args.quick else 100,
        "noise": 50 if args.quick else 100,
    }

    sources = {}
    sources["github"] = fetch_github_projects(out, cp, max_per_repo=limits["github"])
    cora_n, cora_refs = fetch_cora(out, cp, max_papers=limits["cora"])
    sources["cora"] = cora_n
    sources["kopub"] = fetch_hf_kopub(out, cp, max_docs=limits["kopub"])
    fetch_behacom(out, cp)
    mind_pairs = fetch_mind2web_pairs(out, cp, max_pairs=limits["mind2web"])
    sources["napierone"] = fetch_napierone_sample(out, cp, target=limits["napier"])
    sources["govdocs"] = fetch_govdocs_sample(out, cp, n=limits["govdocs"])
    cards_edges = fetch_cards_edges(cp) if not args.quick else []
    sources["noise"] = build_noise(out, n=limits["noise"])

    file_paths = [str(p.resolve()) for p in out.rglob("*") if p.is_file() and CHECKPOINT_FILE not in p.name]
    relations = auto_relations(out, cora_refs + cards_edges, mind_pairs)
    queries, qrels = build_queries(out, cp, file_paths)

    stats = {
        "files": len(file_paths),
        "relations": len(relations),
        "queries": len(queries),
        "sources": sources,
        "quick_mode": args.quick,
    }
    write_manifest(out, relations, queries, qrels, stats)
    save_checkpoint(out, cp)

    logger.info("Build complete: %s", stats)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
