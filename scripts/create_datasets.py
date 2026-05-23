#!/usr/bin/env python3
"""Generate synthetic datasets: filekg_main, code_dependency, personal_mixed."""

import argparse
import json
import random
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "datasets"


def write_file(path: Path, content: str, mtime: float | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if mtime is not None:
        import os
        os.utime(path, (mtime, mtime))


def create_filekg_main(base: Path):
    """133 relevant + 100 noise files with preset relations."""
    base.mkdir(parents=True, exist_ok=True)
    relations = []
    t0 = time.time() - 86400 * 30

    topics = [
        ("budget", "2024年度预算草案", ["Q1预算", "成本分析"]),
        ("contract", "采购合同模板", ["供应商A", "条款修订"]),
        ("report", "季度经营报告", ["营收", "利润率"]),
        ("design", "产品原型设计", ["UI草图", "交互说明"]),
    ]

    idx = 0
    for topic, title, subs in topics:
        folder = base / topic
        for i, sub in enumerate(subs):
            idx += 1
            fname = f"{title}_{sub}_v{i+1}.md"
            fpath = folder / fname
            body = f"# {sub}\n\n相关内容属于 {title}。参见 {topic}/README.md\n"
            mt = t0 + idx * 120
            write_file(fpath, body, mt)
            if i > 0:
                relations.append({
                    "source": str(fpath.relative_to(base)).replace("\\", "/"),
                    "target": str((folder / f"{title}_{subs[0]}_v1.md").relative_to(base)).replace("\\", "/"),
                    "type": "HAS_VERSION",
                })

        readme = folder / "README.md"
        write_file(readme, f"# {title}\n\n目录说明 for {topic}\n", t0 + idx * 60)
        for sub in subs:
            relations.append({
                "source": str((folder / f"{title}_{sub}_v1.md").relative_to(base)).replace("\\", "/"),
                "target": str(readme.relative_to(base)).replace("\\", "/"),
                "type": "REFERENCES",
            })

    py_dir = base / "scripts"
    utils_py = py_dir / "utils.py"
    main_py = py_dir / "main.py"
    write_file(utils_py, "def helper():\n    return 42\n", t0 + 5000)
    write_file(main_py, "from utils import helper\n\nprint(helper())\n", t0 + 5100)
    relations.append({
        "source": "scripts/main.py", "target": "scripts/utils.py", "type": "DEPENDS_ON"
    })

    write_file(base / ".filekg_project.json", json.dumps({"name": "filekg_main"}), t0)
    write_file(
        base / ".filekg_tags.json",
        json.dumps({"tags": {"files": {"budget/Q1预算_2024年度预算草案_Q1预算_v1.md": ["finance"]}}}),
        t0,
    )

    while idx < 133:
        idx += 1
        folder = base / f"docs_{idx // 20}"
        fpath = folder / f"doc_{idx}.txt"
        write_file(fpath, f"Document {idx} content about topic {idx % 7}\n", t0 + idx * 30)

    noise_dir = base / "noise"
    for n in range(100):
        write_file(noise_dir / f"noise_{n}.log", f"noise log line {n}\n" * 5, t0 + n)

    queries = [
        {"id": "q1", "query": "预算 Q1", "relevant": ["budget/2024年度预算草案_Q1预算_v1.md"]},
        {"id": "q2", "query": "采购合同", "relevant": ["contract/采购合同模板_供应商A_v1.md"]},
        {"id": "q3", "query": "python import utils", "relevant": ["scripts/main.py", "scripts/utils.py"]},
    ]
    for q in queries:
        q["relevant"] = [str(base / p).replace("\\", "/") for p in q["relevant"]]

    anno = {"dataset": "filekg_main", "relations": relations, "queries": queries, "file_count": 133 + 100}
    write_file(base / "annotations.json", json.dumps(anno, ensure_ascii=False, indent=2), t0)
    print(f"Created filekg_main at {base} ({133}+100 files)")


def create_code_dependency(base: Path):
    base.mkdir(parents=True, exist_ok=True)
    relations = []
    t0 = time.time() - 86400 * 10

    files = {
        "app/main.py": "from app.service import run\n\nif __name__ == '__main__':\n    run()\n",
        "app/service.py": "from app.db import connect\nfrom app.config import settings\n\ndef run():\n    connect(settings.DSN)\n",
        "app/db.py": "def connect(dsn):\n    pass\n",
        "app/config.py": "class settings:\n    DSN = 'sqlite:///local.db'\n",
        "app/__init__.py": "",
        "web/index.js": "const api = require('./api');\napi.fetch();\n",
        "web/api.js": "exports.fetch = () => console.log('ok');\n",
        "web/package.json": '{"name":"web-demo","dependencies":{}}',
        "config/settings.json": '{"database": "app/db.py", "debug": true}',
        "config/deploy.yaml": "service: app\nfiles:\n  - app/main.py\n",
        "tests/test_main.py": "import app.main\n\ndef test_main():\n    assert True\n",
        "README.md": "# Code dependency dataset\n\nSee app/main.py\n",
    }

    for rel, content in files.items():
        write_file(base / rel, content, t0 + hash(rel) % 5000)

    relations.extend([
        {"source": "app/main.py", "target": "app/service.py", "type": "DEPENDS_ON"},
        {"source": "app/service.py", "target": "app/db.py", "type": "DEPENDS_ON"},
        {"source": "app/service.py", "target": "app/config.py", "type": "DEPENDS_ON"},
        {"source": "web/index.js", "target": "web/api.js", "type": "DEPENDS_ON"},
        {"source": "README.md", "target": "app/main.py", "type": "REFERENCES"},
    ])

    queries = [
        {"id": "c1", "query": "database connection", "relevant": ["app/db.py", "app/service.py"]},
        {"id": "c2", "query": "javascript api module", "relevant": ["web/api.js", "web/index.js"]},
    ]
    for q in queries:
        q["relevant"] = [str((base / p).resolve()).replace("\\", "/") for p in q["relevant"]]

    anno = {"dataset": "code_dependency", "relations": relations, "queries": queries, "file_count": len(files)}
    write_file(base / "annotations.json", json.dumps(anno, ensure_ascii=False, indent=2), t0)
    print(f"Created code_dependency at {base} ({len(files)} files)")


def create_personal_mixed(base: Path):
    base.mkdir(parents=True, exist_ok=True)
    relations = []
    t0 = time.time() - 86400 * 60
    random.seed(42)

    categories = {
        "photos": [("trip.png", ""), ("family.jpg", "")],
        "work": [("slides.pptx", "Q4 Review"), ("notes.docx", "Meeting notes")],
        "personal": [("diary.txt", "Dear diary"), ("todo.md", "- [ ] buy milk")],
        "archive": [("old_report.pdf", "PDF placeholder content")],
    }

    count = 0
    for cat, items in categories.items():
        for name, text in items:
            count += 1
            fpath = base / cat / name
            if name.endswith((".txt", ".md", ".docx")):
                write_file(fpath, text + f"\n#tag_{cat}\n", t0 + count * 100)
            else:
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_bytes(b"\x89PNG\r\n\x1a\n" if name.endswith(".png") else b"\xff\xd8\xff")
                import os
                os.utime(fpath, (t0 + count * 100, t0 + count * 100))

    for i in range(count, 61):
        ext = random.choice([".txt", ".csv", ".json", ".md"])
        write_file(base / f"misc/file_{i}{ext}", f"misc content {i}\n", t0 + i * 50)

    relations.append({"source": "work/notes.docx", "target": "work/slides.pptx", "type": "NEAR_IN_TIME"})

    queries = [
        {"id": "p1", "query": "meeting notes", "relevant": [str((base / "work/notes.docx").resolve()).replace("\\", "/")]},
        {"id": "p2", "query": "diary personal", "relevant": [str((base / "personal/diary.txt").resolve()).replace("\\", "/")]},
    ]

    anno = {"dataset": "personal_mixed", "relations": relations, "queries": queries, "file_count": 61}
    write_file(base / "annotations.json", json.dumps(anno, ensure_ascii=False, indent=2), t0)
    print(f"Created personal_mixed at {base} (61 files)")


def main():
    parser = argparse.ArgumentParser(description="Create FileKG synthetic datasets")
    parser.add_argument("--dataset", choices=["all", "filekg_main", "code_dependency", "personal_mixed"], default="all")
    parser.add_argument("--output", type=Path, default=DATA)
    args = parser.parse_args()

    creators = {
        "filekg_main": create_filekg_main,
        "code_dependency": create_code_dependency,
        "personal_mixed": create_personal_mixed,
    }
    if args.dataset == "all":
        for name, fn in creators.items():
            fn(args.output / name)
    else:
        creators[args.dataset](args.output / args.dataset)


if __name__ == "__main__":
    main()
