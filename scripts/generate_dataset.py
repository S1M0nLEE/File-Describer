#!/usr/bin/env python3
"""生成文档第八章描述的实验数据集（项目 A-D）。"""
from __future__ import annotations

import json
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "dataset"


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def touch_time(path: Path, base: datetime, offset_min: int = 0) -> None:
    t = base + timedelta(minutes=offset_min)
    ts = t.timestamp()
    import os

    os.utime(path, (ts, ts))


def project_a(base: datetime) -> None:
    root = OUT / "project_a_research"
    write(
        root / "论文_v1.docx.md",
        "# 机器学习实验论文 v1\n\nimport data_processing\n\n参见 [bib](file://参考文献.bib)\n",
    )
    write(
        root / "论文_v2.docx.md",
        "# 机器学习实验论文 v2\n\nimport data_processing\n\n更新实验结果。\n",
    )
    write(root / "论文终稿.pdf.md", "# 论文终稿\n\n与 v2 内容高度一致。\n" * 5)
    write(root / "实验数据.csv", "id,value\n1,0.95\n2,0.88\n")
    write(
        root / "data_processing.py",
        '"""处理实验数据"""\nimport csv\n\nDATA = "实验数据.csv"\n',
    )
    write(
        root / "data_visualization.ipynb.md",
        "# 可视化\n\nimport data_processing\n\n生成图表1.png\n",
    )
    write(root / "图表1.png.md", "[图片占位] 实验结果图表1")
    write(root / "图表2.png.md", "[图片占位] 实验结果图表2")
    write(root / "参考文献.bib", "@article{ml2024, title={Deep Learning}}\n")
    write(root / "项目说明.md", "# 说明\n\n模板见 [模板](file://论文模板.docx.md)\n")
    write(root / "论文模板.docx.md", "# 论文模板\n")
    zpath = root / "原始数据.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("实验日志.log", "2024-01-01 run ok\n")
    for i, p in enumerate(sorted(root.rglob("*"))):
        if p.is_file():
            touch_time(p, base, i % 8)


def project_b(base: datetime) -> None:
    root = OUT / "project_b_software"
    write(root / "app" / "main.py", 'from utils import helper\nfrom config import settings\n')
    write(root / "app" / "utils.py", "def helper():\n    return 1\n")
    write(root / "config" / "settings.py", "DEBUG = True\n")
    write(root / "config" / "app.yaml", "include: settings.py\n")
    write(root / "tests" / "test_main.py", "from app.main import *\n")
    for i, p in enumerate(root.rglob("*")):
        if p.is_file():
            touch_time(p, base, i)


def project_c(base: datetime) -> None:
    root = OUT / "project_c_finance"
    write(root / "账单.xlsx.md", "月份,金额\n1,1200\n")
    write(root / "账单_backup.xlsx.md", "月份,金额\n1,1200\n备份副本\n")
    write(root / "发票.pdf.md", "电子发票 PDF 内容")
    write(root / "发票扫描.jpg.md", "扫描件与 PDF 视觉相似")
    write(root / "~$账单.xlsx", "临时文件")
    touch_time(root / "账单.xlsx.md", base)
    touch_time(root / "账单_backup.xlsx.md", base, 1)
    touch_time(root / "发票.pdf.md", base, 2)


def project_d(base: datetime) -> None:
    root = OUT / "project_d_media"
    write(root / "photos" / "vacation.jpg.md", "度假照片")
    write(root / "screenshots" / "ppt_slide.png.md", "PPT 截图")
    write(root / "slides" / "汇报.pptx.md", "季度汇报 PPT")
    for p in root.rglob("*"):
        if p.is_file():
            touch_time(p, base)


def workflow_log() -> None:
    log = ROOT / "data" / "workflow_log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    seq = [
        OUT / "project_a_research" / "实验数据.csv",
        OUT / "project_a_research" / "data_visualization.ipynb.md",
        OUT / "project_a_research" / "图表1.png.md",
    ]
    entries = []
    for _ in range(5):
        for p in seq:
            entries.append({"path": str(p.resolve()), "event": "open"})
        entries.append({"event": "session_end"})
    with log.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def ground_truth() -> None:
    gt = {
        "queries": [
            {
                "q": "项目A的论文最新版本",
                "direct": ["论文终稿.pdf.md"],
                "indirect": ["论文_v2.docx.md"],
            },
            {
                "q": "处理实验数据的代码",
                "direct": ["data_visualization.ipynb.md"],
                "indirect": ["实验数据.csv"],
            },
            {
                "q": "上周修改的实验图表",
                "direct": ["图表1.png.md"],
                "indirect": ["data_visualization.ipynb.md"],
            },
        ]
    }
    (OUT / "ground_truth.json").write_text(
        json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    base = datetime.now() - timedelta(days=3)
    project_a(base)
    project_b(base)
    project_c(base)
    project_d(base)
    workflow_log()
    ground_truth()
    print(f"数据集已生成: {OUT}")


if __name__ == "__main__":
    main()
