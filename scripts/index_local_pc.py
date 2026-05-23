#!/usr/bin/env python3

"""索引本机常用目录，供 RAG 使用。支持断点续传与失败重试。"""

from __future__ import annotations



import argparse

import json

import logging

import os

import sys

import time

from pathlib import Path



ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))



from src.config import settings  # noqa: E402

from src.indexing.builder import IndexBuilder  # noqa: E402

from src.storage.factory import create_stores  # noqa: E402



logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

logger = logging.getLogger(__name__)



EXTRA_SKIP_DIRS = {

    "Windows",

    "Program Files",

    "Program Files (x86)",

    "ProgramData",

    "System Volume Information",

    "$Recycle.Bin",

    "Recovery",

    "PerfLogs",

}



STATE_PATH = ROOT / "data" / "index_local_state.json"





def resolve_roots(extra: list[str] | None) -> list[Path]:

    roots: list[Path] = []

    sources = extra if extra else list(settings.rag_index_roots or [])
    for r in sources:

        p = Path(os.path.expandvars(r)).expanduser()

        if p.is_dir():

            roots.append(p.resolve())

    if not roots:

        home = Path.home()

        for name in ("Documents", "Desktop", "Downloads", "Pictures", "Videos"):

            p = home / name

            if p.is_dir():

                roots.append(p)

    return list(dict.fromkeys(roots))





def patch_scanner_skips() -> None:

    from src.indexing import scanner



    scanner.SKIP_DIRS = scanner.SKIP_DIRS | EXTRA_SKIP_DIRS





def load_state() -> dict:

    if not STATE_PATH.exists():

        return {"roots": {}, "last_run": None}

    try:

        return json.loads(STATE_PATH.read_text(encoding="utf-8"))

    except json.JSONDecodeError:

        return {"roots": {}, "last_run": None}





def save_state(state: dict) -> None:

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    tmp = STATE_PATH.with_suffix(".json.tmp")

    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    tmp.replace(STATE_PATH)





def apply_fast_mode() -> None:

    os.environ["FILEKG_INDEX_FAST"] = "1"

    os.environ["FILEKG_MULTIMODAL_ENABLED"] = "false"

    os.environ["FILEKG_LLM_ENABLED"] = "false"

    settings.llm_enabled = False

    settings.multimodal_enabled = False





def run_once(

    builder: IndexBuilder,

    roots: list[Path],

    *,

    clear: bool,

    max_files: int | None,

    resume: bool,

    skip_relations: bool,

) -> int:

    """返回非零表示失败。"""

    state = load_state()

    exit_code = 0

    for i, root in enumerate(roots):

        key = str(root)

        print(f"\n[{i + 1}/{len(roots)}] {root}")

        try:

            result = builder.build(

                root,

                clear=clear and i == 0,

                max_files=max_files,

                resume=resume and not (clear and i == 0),

                skip_relations=skip_relations,

            )

        except KeyboardInterrupt:

            raise

        except Exception as e:

            logger.exception("索引失败 %s: %s", root, e)

            state["roots"][key] = {"status": "error", "error": str(e)}

            save_state(state)

            exit_code = 1

            continue



        state["roots"][key] = {

            "status": "ok",

            "file_count": result.get("file_count"),

            "indexed_new": result.get("indexed_new"),

            "skipped_unchanged": result.get("skipped_unchanged"),

            "updated": result.get("updated"),

        }

        save_state(state)

        print("  新写入:", result.get("indexed_new", result.get("file_count")))

        print("  跳过:", result.get("skipped_unchanged", 0))

        print("  更新:", result.get("updated", 0))



    state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    save_state(state)

    return exit_code





def main() -> None:

    p = argparse.ArgumentParser(description="索引本机目录到 FileKG（RAG 数据源）")

    p.add_argument("--clear", action="store_true", help="首次全量：清空后从第一个根目录重建")

    p.add_argument(

        "--max-files",

        type=int,

        default=None,

        help="每个根目录最多新写入文件数（0=不限，默认读 config rag.max_files_per_root）",

    )

    p.add_argument("--root", action="append", default=[], help="额外根目录，可多次指定")

    p.add_argument("--no-multimodal", action="store_true", help="关闭多模态以加快索引")

    p.add_argument(

        "--no-resume",

        action="store_true",

        help="不跳过已索引且未修改的文件（默认开启断点续传）",

    )

    p.add_argument(

        "--skip-relations",

        action="store_true",

        help="跳过关系发现（补全大量文件时推荐）",

    )

    p.add_argument(

        "--retries",

        type=int,

        default=3,

        help="异常退出后自动重试次数（默认 3）",

    )

    args = p.parse_args()



    if args.no_multimodal or not settings.rag_index_multimodal:

        os.environ["FILEKG_MULTIMODAL_ENABLED"] = "false"

        settings.multimodal_enabled = False



    apply_fast_mode()

    patch_scanner_skips()

    roots = resolve_roots(args.root)

    if not roots:

        print("未找到可索引目录")

        sys.exit(1)



    resume = not args.no_resume and not args.clear

    cap = args.max_files
    if cap is not None and cap <= 0:
        cap = None
    elif cap is None:
        if resume:
            cap = None
        else:
            cap = settings.rag_max_files_per_root or None
            if cap is not None and cap <= 0:
                cap = None

    skip_relations = args.skip_relations or resume



    print("将索引以下目录:")

    for r in roots:

        print(" ", r)

    print("断点续传:", resume, "| 跳过重关系:", skip_relations, "| 每目录上限:", cap or "不限")



    graph, chroma = create_stores()

    builder = IndexBuilder(graph, chroma)



    attempts = max(1, args.retries + 1)

    for attempt in range(1, attempts + 1):

        if attempt > 1:

            wait = min(30, 5 * attempt)

            print(f"\n第 {attempt}/{attempts} 次尝试（{wait}s 后重试）…")

            time.sleep(wait)

        code = run_once(

            builder,

            roots,

            clear=args.clear and attempt == 1,

            max_files=cap,

            resume=resume,

            skip_relations=skip_relations,

        )

        if code == 0:

            print("\n完成。启动服务: python scripts/run_server.py")

            sys.exit(0)

        if attempt < attempts:

            logger.warning("本轮有目录失败，将续传重试…")



    print("\n补全索引在多次重试后仍失败，请查看日志 data/index_local_pc.log")

    sys.exit(1)





if __name__ == "__main__":

    main()

