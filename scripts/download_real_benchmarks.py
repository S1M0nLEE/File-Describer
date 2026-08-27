#!/usr/bin/env python3
"""
从 Hugging Face / GitHub 拉取真实公开数据集，物化为 FileKG 可索引目录 + 标注。

不依赖原合成 filekg_main。下载后须运行:
  python scripts/download_real_benchmarks.py --scale paper
  python scripts/run_evaluation.py --registry real --all --results-dir results_real
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_hf_env() -> None:
    """加载 .env 中 HF_*（须在 import huggingface_hub 之前）。"""
    import os

    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if key.startswith("HF_") and key not in os.environ:
            os.environ[key] = val


_load_hf_env()

BENCH = ROOT / "data" / "benchmarks"
ANNOT = BENCH / "annotations"
REGISTRY_REAL = BENCH / "registry_real.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

HIPPO_REPO = "MMMem-org/HippoCamp"
REPOBENCH_DS = "tianyang/repobench_python_v1.1"

# 顶刊/主文规模（HippoCamp 三档案 Fullset + 大规模 RepoBench + GitHub）
PAPER_HIPPO_PROFILES = [("adam", False), ("bei", False), ("victoria", False)]
PAPER_REPOBENCH = {"max_repos": 100, "max_queries": 500, "splits": ["cross_file_first", "cross_file_random"]}

# 中等体量仓库，避免 cpython/django 级巨型克隆
GITHUB_REPOS = [
    ("psf/requests", "main"),
    ("pallets/flask", "main"),
    ("tiangolo/fastapi", "main"),
    ("encode/httpx", "main"),
    ("Textualize/rich", "main"),
    ("pydantic/pydantic", "main"),
    ("pytest-dev/pytest", "main"),
    ("sqlalchemy/sqlalchemy", "main"),
    ("celery/celery", "main"),
    ("aio-libs/aiohttp", "main"),
    ("python-attrs/attrs", "main"),
    ("pallets/click", "main"),
    ("marshmallow-code/marshmallow", "main"),
    ("benoitc/gunicorn", "main"),
    ("urllib3/urllib3", "main"),
]


def _safe_name(s: str) -> str:
    return re.sub(r'[<>:"|?*\\]', "_", s).strip() or "unnamed"


def _basename_paths(paths: list[str]) -> list[str]:
    out: list[str] = []
    for p in paths:
        if not p:
            continue
        name = Path(str(p).replace("\\", "/")).name
        if name and name not in out:
            out.append(name)
    return out


def _extract_hippocamp_files(item: dict) -> list[str]:
    """从 HippoCamp manifest 提取相关文件名（用于 MAP 标注）。"""
    names: list[str] = []
    top = item.get("file_path")
    if isinstance(top, list):
        names.extend(_basename_paths([str(x) for x in top]))
    elif isinstance(top, str) and top.strip():
        names.extend(_basename_paths([top]))
    for ev in item.get("evidence") or []:
        if not isinstance(ev, dict):
            continue
        fp = ev.get("file_path") or ev.get("path") or ""
        if fp:
            names.extend(_basename_paths([str(fp)]))
    return list(dict.fromkeys(names))


def download_hippocamp(profile: str = "adam", *, use_subset: bool = False) -> dict:
    """HippoCamp 真实个人文件 + QA（路径对齐 HF：Fullset/Subset）。"""
    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except ImportError:
        raise SystemExit("pip install huggingface_hub")

    profile = profile.lower()
    prof_cap = profile.capitalize()
    out_id = f"hippocamp_{profile}"
    out = BENCH / out_id
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "hf_cache"

    scope = "Subset" if use_subset else "Fullset"
    json_name = f"{prof_cap}_Subset.json" if use_subset else f"{prof_cap}.json"
    json_rel = f"{prof_cap}/{scope}/{json_name}"
    files_subdir = f"{prof_cap}_Subset" if use_subset else prof_cap
    files_pattern = f"{prof_cap}/{scope}/{files_subdir}/**"

    logger.info("下载 HippoCamp 标注: %s", json_rel)
    json_path = hf_hub_download(
        repo_id=HIPPO_REPO,
        repo_type="dataset",
        filename=json_rel,
        local_dir=str(cache),
    )
    raw = json.loads(Path(json_path).read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("data", raw.get("questions", []))

    logger.info("下载 HippoCamp 文件树（可能较久）: %s", files_pattern)
    files_dir = out / "files"
    try:
        snapshot_download(
            repo_id=HIPPO_REPO,
            repo_type="dataset",
            allow_patterns=[files_pattern],
            local_dir=str(cache),
        )
        src = cache / prof_cap / scope / files_subdir
        if src.exists():
            if files_dir.exists():
                shutil.rmtree(files_dir)
            shutil.copytree(src, files_dir)
        else:
            logger.warning("未找到文件目录: %s", src)
    except Exception as e:
        logger.warning("文件下载不完整: %s", e)

    queries = []
    with_gt = 0
    for item in items:
        q = item.get("question") or item.get("query") or item.get("q", "")
        if not q:
            continue
        files = _extract_hippocamp_files(item)
        if files:
            with_gt += 1
        queries.append(
            {
                "q": q,
                "direct": files[:5],
                "indirect": files[5:10],
                "source_id": str(item.get("id", "")),
            }
        )

    gt = {
        "dataset": out_id,
        "description": f"HippoCamp 真实个人文件 ({profile}, {scope})",
        "source": HIPPO_REPO,
        "queries": queries,
        "queries_with_file_gt": with_gt,
    }
    ANNOT.mkdir(parents=True, exist_ok=True)
    (ANNOT / f"{out_id}.json").write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")

    n_files = sum(1 for _ in files_dir.rglob("*") if _.is_file()) if files_dir.exists() else 0
    logger.info(
        "HippoCamp %s (%s): %d 文件, %d 查询 (%d 条含文件 GT)",
        profile,
        scope,
        n_files,
        len(queries),
        with_gt,
    )
    return {
        "id": out_id,
        "name": f"HippoCamp {profile} ({scope})",
        "path": f"data/benchmarks/{out_id}/files",
        "ground_truth": f"data/benchmarks/annotations/{out_id}.json",
        "queries": len(queries),
        "file_count": n_files,
        "source": "hippocamp",
        "scale": "paper" if not use_subset else "subset",
    }


def download_repobench(
    *,
    max_repos: int = 25,
    max_queries: int = 200,
    splits: list[str] | None = None,
) -> dict:
    """RepoBench Python：物化跨文件仓库为真实目录树。"""
    try:
        from datasets import load_dataset
    except ImportError:
        raise SystemExit("pip install datasets")

    splits = splits or ["cross_file_first"]
    out_id = "real_repobench"
    root = BENCH / out_id / "repos"
    if root.exists():
        shutil.rmtree(BENCH / out_id)
    root.mkdir(parents=True, exist_ok=True)

    by_repo: dict[str, list] = defaultdict(list)
    for split in splits:
        logger.info("加载 %s split=%s ...", REPOBENCH_DS, split)
        ds = load_dataset(REPOBENCH_DS, split=split)
        for row in ds:
            rn = row.get("repo_name") or "unknown"
            by_repo[rn].append(row)

    top_repos = sorted(by_repo.keys(), key=lambda r: len(by_repo[r]), reverse=True)[:max_repos]
    queries: list[dict] = []
    total_files = 0

    for repo in top_repos:
        repo_dir = root / _safe_name(repo)
        repo_dir.mkdir(parents=True, exist_ok=True)
        paths_written: dict[str, Path] = {}

        for row in by_repo[repo]:
            fp = row.get("file_path") or "main.py"
            rel = Path(str(fp).replace("\\", "/").lstrip("/"))
            target = repo_dir / rel
            if rel.as_posix() not in paths_written:
                target.parent.mkdir(parents=True, exist_ok=True)
                body = row.get("cropped_code") or ""
                imports = row.get("import_statement") or ""
                content = f"{imports}\n\n{body}\n".strip() + "\n"
                target.write_text(content, encoding="utf-8")
                paths_written[rel.as_posix()] = target
                total_files += 1

            for ctx in row.get("context") or []:
                if not isinstance(ctx, dict):
                    continue
                cpath = ctx.get("path") or ""
                if not cpath:
                    continue
                rel_c = Path(str(cpath).replace("\\", "/").lstrip("/"))
                dest = repo_dir / rel_c
                if rel_c.as_posix() not in paths_written:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text((ctx.get("snippet") or "") + "\n", encoding="utf-8")
                    paths_written[rel_c.as_posix()] = dest
                    total_files += 1

        if len(queries) >= max_queries:
            continue
        per_repo = max(3, max_queries // max(1, len(top_repos)))
        for row in by_repo[repo][:per_repo]:
            fp = Path(str(row.get("file_path", "a.py")).replace("\\", "/")).name
            ctx_names = []
            for ctx in row.get("context") or []:
                if isinstance(ctx, dict) and ctx.get("path"):
                    ctx_names.append(Path(str(ctx["path"]).replace("\\", "/")).name)
            ctx_names = list(dict.fromkeys(ctx_names))[:8]
            if not fp:
                continue
            queries.append(
                {
                    "q": f"仓库 {repo.split('/')[-1]} 中文件 {fp} 的跨文件依赖上下文",
                    "direct": [fp],
                    "indirect": [n for n in ctx_names if n != fp][:6],
                    "repo": repo,
                }
            )
            if len(queries) >= max_queries:
                break

    split_label = "+".join(splits)
    gt = {
        "dataset": out_id,
        "description": f"RepoBench {split_label} 物化，{len(top_repos)} 仓库",
        "source": REPOBENCH_DS,
        "queries": queries[:max_queries],
    }
    (ANNOT / f"{out_id}.json").write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("RepoBench: %d 仓库, ~%d 文件, %d 查询", len(top_repos), total_files, len(queries))
    return {
        "id": out_id,
        "name": f"RepoBench Python ({split_label})",
        "path": f"data/benchmarks/{out_id}/repos",
        "ground_truth": f"data/benchmarks/annotations/{out_id}.json",
        "queries": len(queries[:max_queries]),
        "file_count": total_files,
        "source": "repobench",
        "scale": "paper" if max_repos >= 50 else "default",
    }


def download_github_repos(*, shallow: bool = True, max_repos: int | None = None) -> dict:
    """克隆知名开源仓库，用于 DEPENDS_ON 真实图。"""
    out_id = "real_github_repos"
    root = BENCH / out_id
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    repos = GITHUB_REPOS[: max_repos or len(GITHUB_REPOS)]
    queries = []
    total_files = 0
    cloned = 0
    for repo, branch in repos:
        name = repo.replace("/", "__")
        dest = root / name
        url = f"https://github.com/{repo}.git"
        logger.info("克隆 %s -> %s", repo, dest)
        cmd = ["git", "clone", "--depth", "1", "-b", branch, url, str(dest)]
        if shallow:
            cmd = ["git", "clone", "--depth", "1", url, str(dest)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=900)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.warning("跳过 %s: %s", repo, e)
            continue
        cloned += 1
        py_files = [p for p in dest.rglob("*.py") if ".git" not in p.parts][:800]
        total_files += len(py_files)
        if py_files:
            entry = py_files[0].relative_to(dest).as_posix()
            queries.append(
                {
                    "q": f"{repo} 项目入口与核心模块",
                    "direct": [Path(entry).name],
                    "indirect": [p.name for p in py_files[1:8]],
                    "repo": repo,
                }
            )

    gt = {
        "dataset": out_id,
        "description": f"GitHub 克隆的真实 Python 仓库（{cloned} 个）",
        "source": "github.com",
        "queries": queries,
    }
    (ANNOT / f"{out_id}.json").write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "id": out_id,
        "name": "GitHub Python 仓库",
        "path": f"data/benchmarks/{out_id}",
        "ground_truth": f"data/benchmarks/annotations/{out_id}.json",
        "queries": len(queries),
        "file_count": total_files,
        "source": "github",
        "scale": "paper",
    }


def write_registry(entries: list[dict], *, paper_mode: bool = False) -> None:
    if paper_mode:
        merged = {e["id"]: e for e in entries}
    elif REGISTRY_REAL.exists():
        merged = {e["id"]: e for e in json.loads(REGISTRY_REAL.read_text(encoding="utf-8")).get("datasets", [])}
        for e in entries:
            merged[e["id"]] = e
    else:
        merged = {e["id"]: e for e in entries}

    total_files = sum(e.get("file_count", 0) for e in merged.values())
    total_queries = sum(e.get("queries", 0) for e in merged.values())
    reg = {
        "datasets": list(merged.values()),
        "note": "真实公开数据；指标须 run_evaluation --registry real 跑出",
        "aggregate": {
            "datasets": len(merged),
            "files": total_files,
            "queries": total_queries,
            "target_paper": "HippoCamp Fullset ~1930 files / 581 QA + RepoBench 数千文件",
        },
    }
    REGISTRY_REAL.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "已写入 %s (%d 数据集, 合计 ~%d 文件 / %d 查询)",
        REGISTRY_REAL,
        len(merged),
        total_files,
        total_queries,
    )


def run_scale_paper() -> list[dict]:
    entries: list[dict] = []
    for profile, use_subset in PAPER_HIPPO_PROFILES:
        entries.append(download_hippocamp(profile, use_subset=use_subset))
    entries.append(
        download_repobench(
            max_repos=PAPER_REPOBENCH["max_repos"],
            max_queries=PAPER_REPOBENCH["max_queries"],
            splits=PAPER_REPOBENCH["splits"],
        )
    )
    entries.append(download_github_repos())
    return entries


def main() -> None:
    p = argparse.ArgumentParser(description="下载真实公开评测数据集")
    p.add_argument(
        "--scale",
        choices=("default", "paper"),
        default="default",
        help="paper=顶刊主文规模（HippoCamp 三档案 Fullset + 大规模 RepoBench + GitHub）",
    )
    p.add_argument("--all", action="store_true")
    p.add_argument("--hippocamp", action="store_true")
    p.add_argument("--profile", default="adam", choices=["adam", "bei", "victoria"])
    p.add_argument("--subset", action="store_true", help="HippoCamp 轻量子集（调试用）")
    p.add_argument("--all-profiles", action="store_true", help="下载 adam/bei/victoria（配合 --subset 或 Fullset）")
    p.add_argument("--repobench", action="store_true")
    p.add_argument("--max-repos", type=int, default=None)
    p.add_argument("--max-queries", type=int, default=None)
    p.add_argument("--github-repos", action="store_true")
    args = p.parse_args()

    if args.scale == "paper":
        entries = run_scale_paper()
        write_registry(entries, paper_mode=True)
        print("\n顶刊规模下载完成。汇总见 registry_real.json -> aggregate")
        print("  python scripts/run_evaluation.py --registry real --all --results-dir results_real")
        return

    if not any([args.all, args.hippocamp, args.repobench, args.github_repos]):
        args.all = True

    max_repos = args.max_repos if args.max_repos is not None else 25
    max_queries = args.max_queries if args.max_queries is not None else 200

    entries: list[dict] = []
    if args.all or args.hippocamp:
        profiles = ["adam", "bei", "victoria"] if args.all_profiles else [args.profile]
        for prof in profiles:
            entries.append(download_hippocamp(prof, use_subset=args.subset))
    if args.all or args.repobench:
        entries.append(download_repobench(max_repos=max_repos, max_queries=max_queries))
    if args.all or args.github_repos:
        entries.append(download_github_repos())

    write_registry(entries)
    print("\n完成。下一步:")
    print("  python scripts/run_evaluation.py --registry real --all --results-dir results_real")


if __name__ == "__main__":
    main()
