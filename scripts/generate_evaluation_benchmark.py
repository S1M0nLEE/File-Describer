#!/usr/bin/env python3
"""
生成对比实验用基准数据集（对应方案第八章）。

规模预设:
  small  - 约 230 文件 / 40 查询（快速调试）
  scheme - 约 1200 文件 / 80 查询（与方案 8.2 量级一致，默认）
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BENCH = ROOT / "data" / "benchmarks"
ANNOT = BENCH / "annotations"
RNG = random.Random(42)

# 构建时登记的文件清单，用于扩展查询标注
FILE_MANIFEST: list[dict] = []


class Scale:
    def __init__(
        self,
        *,
        core_files: int = 1000,
        noise: int = 200,
        main_queries: int = 80,
        code_files: int = 80,
        code_queries: int = 25,
        mixed_noise: int = 100,
        mixed_queries: int = 25,
        research_runs: int = 80,
        software_services: int = 35,
        finance_docs: int = 40,
        media_assets: int = 50,
    ) -> None:
        self.core_files = core_files
        self.noise = noise
        self.main_queries = main_queries
        self.code_files = code_files
        self.code_queries = code_queries
        self.mixed_noise = mixed_noise
        self.mixed_queries = mixed_queries
        self.research_runs = research_runs
        self.software_services = software_services
        self.finance_docs = finance_docs
        self.media_assets = media_assets

    @classmethod
    def small(cls) -> Scale:
        return cls(
            core_files=32,
            noise=200,
            main_queries=40,
            code_files=11,
            code_queries=15,
            mixed_noise=40,
            mixed_queries=12,
            research_runs=0,
            software_services=0,
            finance_docs=0,
            media_assets=0,
        )

    @classmethod
    def scheme(cls) -> Scale:
        return cls(
            core_files=1000,
            noise=200,
            main_queries=80,
            code_files=80,
            code_queries=25,
            mixed_noise=100,
            mixed_queries=25,
            research_runs=150,
            software_services=55,
            finance_docs=60,
            media_assets=70,
        )


def write_annotations(dataset_id: str, gt: dict) -> None:
    ANNOT.mkdir(parents=True, exist_ok=True)
    out = ANNOT / f"{dataset_id}.json"
    out.write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    legacy = BENCH / dataset_id / "ground_truth.json"
    if legacy.exists():
        legacy.unlink()


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def touch(path: Path, base: datetime, minutes: int = 0) -> None:
    import os

    t = base + timedelta(minutes=minutes)
    os.utime(path, (t.timestamp(), t.timestamp()))


def reg(name: str, project: str, role: str = "content") -> None:
    FILE_MANIFEST.append({"name": name, "project": project, "role": role})


def noise_files(root: Path, base: datetime, n: int = 200) -> None:
    topics = ["会议纪要", "购物清单", "旅游攻略", "菜谱", "读书笔记", "健身计划"]
    for i in range(n):
        name = f"{topics[i % len(topics)]}_{i:04d}.txt"
        write(root / "noise" / name, f"# {topics[i % len(topics)]}\n\n占位内容 {i}\n")
    for p in (root / "noise").glob("*"):
        if p.is_file():
            touch(p, base, RNG.randint(0, 500))


def build_project_a(root: Path, base: datetime, scale: Scale) -> None:
    pr = root / "project_a_research"
    write(pr / ".project", json.dumps({"id": "research_ml", "name": "科研项目A"}, ensure_ascii=False))
    core = [
        ("论文_v1.docx.md", "# ML论文 v1\nimport data_processing\n[bib](file://参考文献.bib)\n"),
        ("论文_v2.docx.md", "# ML论文 v2\nimport data_processing\n更新实验。\n"),
        ("论文终稿.pdf.md", "# 论文终稿\n" + "深度学习实验结果。\n" * 8),
        ("实验数据.csv", "id,accuracy\n1,0.95\n2,0.88\n"),
        ("data_processing.py", '"""处理实验数据"""\nimport csv\nDATA_FILE="实验数据.csv"\n'),
        ("data_visualization.ipynb.md", "# 可视化\nimport data_processing\n输出图表1.png\n"),
        ("图表1.png.md", "实验结果图表1 准确率曲线"),
        ("图表2.png.md", "实验结果图表2 损失曲线"),
        ("参考文献.bib", "@article{ml2024,title={Deep Learning}}\n"),
        ("项目说明.md", "说明文档 [模板](file://论文模板.docx.md)\n"),
        ("论文模板.docx.md", "# 论文格式模板\n"),
    ]
    for name, body in core:
        write(pr / name, body)
        reg(name, "project_a_research")

    with zipfile.ZipFile(pr / "原始数据.zip", "w") as zf:
        zf.writestr("实验日志.log", "run 2024-01 ok\n")

    for i in range(1, scale.research_runs + 1):
        tag = f"{i:03d}"
        metrics = f"run_{tag}_metrics.csv"
        notebook = f"run_{tag}_analysis.ipynb.md"
        plot = f"run_{tag}_plot.png.md"
        write(pr / "runs" / metrics, f"run_id,{tag}\nacc,0.{90 + (i % 9)}\n")
        write(
            pr / "runs" / notebook,
            f"# 运行 {tag}\nimport data_processing\n处理 run_{tag} 实验数据\n",
        )
        write(pr / "runs" / plot, f"实验 {tag} 准确率曲线图")
        for n in (metrics, notebook, plot):
            reg(n, "project_a_research", "run")

    for i in range(1, max(1, scale.research_runs // 4)):
        name = f"技术报告_v{i}.docx.md"
        write(pr / "reports" / name, f"# 技术报告 版本 {i}\n中间结果摘要\n")
        reg(name, "project_a_research")

    batch = base
    for i, p in enumerate(sorted(pr.rglob("*"))):
        if p.is_file() and p.name != ".project":
            touch(p, batch, i % 9)


def build_project_b(root: Path, base: datetime, scale: Scale) -> None:
    pr = root / "project_b_software"
    write(pr / ".project", json.dumps({"id": "web_platform", "name": "软件项目B"}, ensure_ascii=False))
    modules = {
        "app/main.py": "from app.utils import helper\nfrom config.settings import DEBUG\n",
        "app/utils.py": "def helper():\n    return 42\n",
        "app/models.py": "from app.utils import helper\n",
        "config/settings.py": "DEBUG = True\nAPI_KEY = 'x'\n",
        "config/database.yaml": "host: localhost\ninclude: settings.py\n",
        "tests/test_main.py": "from app.main import *\n",
        "tests/test_utils.py": "from app.utils import helper\n",
        "README.md": "软件项目说明\n",
        "common/auth.py": "def token():\n    return 'ok'\n",
        "common/logging.py": "def log(msg):\n    print(msg)\n",
    }
    for rel, content in modules.items():
        write(pr / rel, content)
        reg(Path(rel).name, "project_b_software")

    for i in range(1, scale.software_services + 1):
        tag = f"{i:03d}"
        handler = f"svc_{tag}_handler.py"
        model = f"svc_{tag}_model.py"
        write(
            pr / f"services/svc_{tag}" / handler,
            f"from common.auth import token\nfrom svc_{tag}_model import Entity\n",
        )
        write(pr / f"services/svc_{tag}" / model, f"class Entity:\n    id = {i}\n")
        reg(handler, "project_b_software")
        reg(model, "project_b_software")

    for i in range(1, max(1, scale.software_services // 2)):
        cfg = f"feature_{i:03d}.yaml"
        write(pr / "features" / cfg, f"feature_id: {i}\ninclude: settings.py\n")
        reg(cfg, "project_b_software")

    for i, p in enumerate(pr.rglob("*")):
        if p.is_file() and p.name != ".project":
            touch(p, base, i % 20)


def build_project_c(root: Path, base: datetime, scale: Scale) -> None:
    pr = root / "project_c_finance"
    write(pr / ".project", json.dumps({"id": "finance", "name": "财务项目C"}, ensure_ascii=False))
    core = [
        ("账单.xlsx.md", "月份,金额\n1,1200\n"),
        ("账单_backup.xlsx.md", "月份,金额\n1,1200\n备份\n"),
        ("发票.pdf.md", "电子发票 增值税专用"),
        ("发票扫描.jpg.md", "发票扫描件 与PDF一致"),
        ("~$账单.xlsx", "temp"),
        ("合同_v1.docx.md", "采购合同 第一版\n"),
        ("合同_v2_修改.docx.md", "采购合同 修订版\n"),
        ("合同终稿.pdf.md", "采购合同 终稿\n" * 3),
    ]
    for name, body in core:
        write(pr / name, body)
        reg(name, "project_c_finance")

    for i in range(1, scale.finance_docs + 1):
        tag = f"{i:03d}"
        inv = f"发票_{tag}.pdf.md"
        scan = f"发票_{tag}_扫描.jpg.md"
        bill = f"报销单_{tag}.xlsx.md"
        write(pr / "invoices" / inv, f"电子发票 编号 {tag}\n")
        write(pr / "invoices" / scan, f"发票 {tag} 扫描件\n")
        write(pr / "expenses" / bill, f"报销明细 {tag}\n")
        for n in (inv, scan, bill):
            reg(n, "project_c_finance")

    touch(pr / "账单.xlsx.md", base)
    touch(pr / "账单_backup.xlsx.md", base, 2)
    touch(pr / "发票.pdf.md", base, 3)


def build_project_d(root: Path, base: datetime, scale: Scale) -> None:
    pr = root / "project_d_media"
    write(pr / ".project", json.dumps({"id": "media", "name": "媒体项目D"}, ensure_ascii=False))
    core = [
        ("photos/vacation.jpg.md", "度假照片 海边"),
        ("screenshots/ppt_slide.png.md", "季度汇报PPT截图"),
        ("slides/汇报.pptx.md", "季度汇报 销售数据"),
        ("video/demo.mp4.md", "产品演示视频"),
    ]
    for rel, body in core:
        write(pr / rel, body)
        reg(Path(rel).name, "project_d_media")

    for i in range(1, scale.media_assets + 1):
        tag = f"{i:03d}"
        photo = f"活动_{tag}.jpg.md"
        shot = f"截图_{tag}.png.md"
        slide = f"幻灯片_{tag}.pptx.md"
        write(pr / "photos" / photo, f"活动记录照片 {tag}\n")
        write(pr / "screenshots" / shot, f"界面截图 {tag}\n")
        write(pr / "slides" / slide, f"演示文稿 {tag} 销售数据\n")
        for n in (photo, shot, slide):
            reg(n, "project_d_media")

    for p in pr.rglob("*"):
        if p.is_file() and p.name != ".project":
            touch(p, base, RNG.randint(0, 30))


def workflow_log(root: Path, scale: Scale) -> None:
    log = ROOT / "data" / "workflow_log.jsonl"
    seq = [
        root / "project_a_research" / "实验数据.csv",
        root / "project_a_research" / "data_visualization.ipynb.md",
        root / "project_a_research" / "图表1.png.md",
    ]
    if scale.research_runs > 0:
        seq.append(root / "project_a_research" / "runs" / "run_001_analysis.ipynb.md")
        seq.append(root / "project_a_research" / "runs" / "run_001_metrics.csv")
    entries: list[dict] = []
    for _ in range(8):
        for p in seq:
            if p.exists():
                entries.append({"path": str(p.resolve()), "event": "open"})
        entries.append({"event": "session_end"})
    with log.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def main_queries_core() -> list[dict]:
    """原 40 条核心查询（方案 8.2 种子集）。"""
    return [
        {"q": "项目A的论文最新版本", "direct": ["论文终稿.pdf.md"], "indirect": ["论文_v2.docx.md", "论文_v1.docx.md"]},
        {"q": "处理实验数据的代码", "direct": ["data_processing.py"], "indirect": ["实验数据.csv", "data_visualization.ipynb.md"]},
        {"q": "实验数据可视化 notebook", "direct": ["data_visualization.ipynb.md"], "indirect": ["实验数据.csv", "图表1.png.md"]},
        {"q": "上周修改的实验图表", "direct": ["图表1.png.md", "图表2.png.md"], "indirect": ["data_visualization.ipynb.md"]},
        {"q": "机器学习论文参考文献", "direct": ["参考文献.bib"], "indirect": ["项目说明.md"]},
        {"q": "论文模板文件", "direct": ["论文模板.docx.md"], "indirect": ["项目说明.md"]},
        {"q": "压缩包里的实验日志", "direct": [], "indirect": ["原始数据.zip"]},
        {"q": "项目A同目录的数据处理脚本", "direct": ["data_processing.py"], "indirect": ["data_visualization.ipynb.md"]},
        {"q": "软件项目入口 main", "direct": ["main.py"], "indirect": ["utils.py", "settings.py"]},
        {"q": "测试 main 的脚本", "direct": ["test_main.py"], "indirect": ["main.py"]},
        {"q": "应用配置 DEBUG", "direct": ["settings.py"], "indirect": ["database.yaml", "main.py"]},
        {"q": "utils 单元测试", "direct": ["test_utils.py"], "indirect": ["utils.py"]},
        {"q": "账单 Excel 文件", "direct": ["账单.xlsx.md"], "indirect": ["账单_backup.xlsx.md"]},
        {"q": "账单备份文件", "direct": ["账单_backup.xlsx.md"], "indirect": ["账单.xlsx.md"]},
        {"q": "发票 PDF", "direct": ["发票.pdf.md"], "indirect": ["发票扫描.jpg.md"]},
        {"q": "合同最新版本", "direct": ["合同终稿.pdf.md"], "indirect": ["合同_v2_修改.docx.md", "合同_v1.docx.md"]},
        {"q": "采购合同修订", "direct": ["合同_v2_修改.docx.md"], "indirect": ["合同_v1.docx.md"]},
        {"q": "季度汇报 PPT", "direct": ["汇报.pptx.md"], "indirect": ["ppt_slide.png.md"]},
        {"q": "PPT 截图", "direct": ["ppt_slide.png.md"], "indirect": ["汇报.pptx.md"]},
        {"q": "度假照片", "direct": ["vacation.jpg.md"], "indirect": []},
        {"q": "pdf 论文终稿", "direct": ["论文终稿.pdf.md"], "indirect": [], "extensions_hint": [".pdf"]},
        {"q": "python 数据处理", "direct": ["data_processing.py"], "indirect": ["实验数据.csv"]},
        {"q": "csv 实验结果数据", "direct": ["实验数据.csv"], "indirect": ["data_processing.py"]},
        {"q": "项目说明 markdown", "direct": ["项目说明.md"], "indirect": ["论文模板.docx.md"]},
        {"q": "引用参考文献的文档", "direct": ["论文_v1.docx.md", "论文_v2.docx.md"], "indirect": ["参考文献.bib"]},
        {"q": "app 目录代码", "direct": ["main.py", "utils.py", "models.py"], "indirect": []},
        {"q": "配置文件 yaml", "direct": ["database.yaml"], "indirect": ["settings.py"]},
        {"q": "财务发票扫描件", "direct": ["发票扫描.jpg.md"], "indirect": ["发票.pdf.md"]},
        {"q": "临时 office 文件", "direct": ["~$账单.xlsx"], "indirect": ["账单.xlsx.md"]},
        {"q": "产品演示视频", "direct": ["demo.mp4.md"], "indirect": []},
        {"q": "深度学习实验论文章节", "direct": ["论文终稿.pdf.md", "论文_v2.docx.md"], "indirect": ["data_visualization.ipynb.md"]},
        {"q": "损失曲线图", "direct": ["图表2.png.md"], "indirect": ["data_visualization.ipynb.md"]},
        {"q": "准确率曲线图", "direct": ["图表1.png.md"], "indirect": ["实验数据.csv"]},
        {"q": "软件 README", "direct": ["README.md"], "indirect": ["main.py"]},
        {"q": "models 模块", "direct": ["models.py"], "indirect": ["utils.py"]},
        {"q": "原始实验 zip", "direct": ["原始数据.zip"], "indirect": []},
        {"q": "同文件夹图表", "direct": ["图表1.png.md"], "indirect": ["图表2.png.md"]},
        {"q": "最近修改的论文", "direct": ["论文终稿.pdf.md"], "indirect": ["论文_v2.docx.md"]},
        {"q": "发票相关所有文件", "direct": ["发票.pdf.md", "发票扫描.jpg.md"], "indirect": ["账单.xlsx.md"]},
        {"q": "合同所有版本", "direct": ["合同终稿.pdf.md"], "indirect": ["合同_v2_修改.docx.md", "合同_v1.docx.md"]},
    ]


def main_queries_extended(scale: Scale) -> list[dict]:
    """在核心 40 条之外，按清单自动生成查询（降低文件名直写泄漏）。"""
    queries = main_queries_core()
    seen_q: set[str] = {q["q"] for q in queries}

    def add(q: str, direct: list[str], indirect: list[str] | None = None) -> None:
        if q in seen_q:
            return
        queries.append({"q": q, "direct": direct, "indirect": indirect or []})
        seen_q.add(q)

    for i in range(1, min(scale.research_runs, 25) + 1):
        tag = f"{i:03d}"
        add(
            f"实验批次 {i} 的指标表",
            [f"run_{tag}_metrics.csv"],
            [f"run_{tag}_analysis.ipynb.md", f"run_{tag}_plot.png.md"],
        )

    for i in range(1, min(scale.software_services, 20) + 1):
        tag = f"{i:03d}"
        add(
            f"微服务 {i} 的处理逻辑",
            [f"svc_{tag}_handler.py"],
            [f"svc_{tag}_model.py", "auth.py"],
        )

    for i in range(1, min(scale.finance_docs, 15) + 1):
        tag = f"{i:03d}"
        add(
            f"编号 {i} 的电子发票",
            [f"发票_{tag}.pdf.md"],
            [f"发票_{tag}_扫描.jpg.md"],
        )

    for i in range(1, min(scale.media_assets, 15) + 1):
        tag = f"{i:03d}"
        add(
            f"活动 {i} 的现场照片",
            [f"活动_{tag}.jpg.md"],
            [f"幻灯片_{tag}.pptx.md"],
        )

    for i in range(1, max(1, scale.research_runs // 4) + 1):
        add(f"技术报告第 {i} 版", [f"技术报告_v{i}.docx.md"], [])

    return queries[: scale.main_queries]


def build_filekg_main(scale: Scale, *, clean: bool = False) -> None:
    global FILE_MANIFEST
    FILE_MANIFEST = []
    root = BENCH / "filekg_main"
    if clean and root.exists():
        shutil.rmtree(root)
    base = datetime.now() - timedelta(days=7)
    build_project_a(root, base, scale)
    build_project_b(root, base, scale)
    build_project_c(root, base, scale)
    build_project_d(root, base, scale)
    noise_files(root, base, scale.noise)
    workflow_log(root, scale)
    gt = {
        "dataset": "filekg_main",
        "description": f"方案 8.2 规模：核心约 {scale.core_files} + 噪声 {scale.noise}，{scale.main_queries} 查询",
        "scale": scale.__dict__,
        "file_manifest_count": len(FILE_MANIFEST),
        "queries": main_queries_extended(scale),
    }
    write_annotations("filekg_main", gt)
    write(ANNOT / "filekg_main_manifest.json", json.dumps(FILE_MANIFEST, ensure_ascii=False, indent=2))


def build_code_dependency(scale: Scale, *, clean: bool = False) -> None:
    root = BENCH / "code_dependency"
    if clean and root.exists():
        shutil.rmtree(root)
    base = datetime.now() - timedelta(days=5)
    pr = root / "webapp"
    tree = {
        "server.py": "from handlers.api import handle_request\nfrom db.connector import connect\n",
        "handlers/api.py": "from services.auth import authenticate\nfrom models.user import User\n",
        "handlers/admin.py": "from services.auth import authenticate\n",
        "services/auth.py": "from models.user import User\nSECRET='k'\n",
        "services/billing.py": "from models.invoice import Invoice\n",
        "models/user.py": "class User: pass\n",
        "models/invoice.py": "class Invoice: pass\n",
        "db/connector.py": "import config\n",
        "config.py": "DATABASE_URL='sqlite:///app.db'\n",
        "tests/test_api.py": "from handlers.api import handle_request\n",
        "tests/test_auth.py": "from services.auth import authenticate\n",
    }
    for rel, c in tree.items():
        write(pr / rel, c)

    n_extra = max(0, scale.code_files - len(tree))
    for i in range(1, n_extra + 1):
        tag = f"{i:03d}"
        api = f"api_{tag}.py"
        write(
            pr / f"handlers/{api}",
            f"from services.worker_{tag} import run\nfrom models.record_{tag} import Record\n",
        )
        write(pr / f"services/worker_{tag}.py", f"def run():\n    return {i}\n")
        write(pr / f"models/record_{tag}.py", f"class Record: id={i}\n")

    for i, p in enumerate(pr.rglob("*")):
        if p.is_file():
            touch(p, base, i)

    queries = [
        {"q": "API 请求处理入口", "direct": ["api.py"], "indirect": ["server.py", "user.py"]},
        {"q": "用户认证服务", "direct": ["auth.py"], "indirect": ["user.py", "api.py"]},
        {"q": "数据库连接模块", "direct": ["connector.py"], "indirect": ["config.py", "server.py"]},
        {"q": "测试 API 的脚本", "direct": ["test_api.py"], "indirect": ["api.py"]},
        {"q": "账单 invoice 模型", "direct": ["invoice.py"], "indirect": ["billing.py"]},
        {"q": "admin 处理器", "direct": ["admin.py"], "indirect": ["auth.py"]},
        {"q": "server 启动文件", "direct": ["server.py"], "indirect": ["api.py", "connector.py"]},
        {"q": "用户模型定义", "direct": ["user.py"], "indirect": ["auth.py", "api.py"]},
        {"q": "认证测试", "direct": ["test_auth.py"], "indirect": ["auth.py"]},
        {"q": "配置文件", "direct": ["config.py"], "indirect": ["connector.py"]},
        {"q": "billing 服务依赖", "direct": ["billing.py"], "indirect": ["invoice.py"]},
        {"q": "handlers 包", "direct": ["api.py", "admin.py"], "indirect": ["server.py"]},
        {"q": "models 包所有", "direct": ["user.py", "invoice.py"], "indirect": []},
        {"q": "webapp 测试目录", "direct": ["test_api.py", "test_auth.py"], "indirect": []},
        {"q": "依赖 user 的模块", "direct": ["auth.py", "api.py"], "indirect": ["user.py"]},
    ]
    for i in range(1, max(0, scale.code_queries - len(queries)) + 1):
        tag = f"{i:03d}"
        queries.append(
            {
                "q": f"扩展接口模块 {i}",
                "direct": [f"api_{tag}.py"],
                "indirect": [f"worker_{tag}.py", f"record_{tag}.py"],
            }
        )
    gt = {
        "dataset": "code_dependency",
        "description": f"工程依赖专项，约 {scale.code_files} 文件",
        "queries": queries[: scale.code_queries],
    }
    write_annotations("code_dependency", gt)


def build_personal_mixed(scale: Scale, *, clean: bool = False) -> None:
    root = BENCH / "personal_mixed"
    if clean and root.exists():
        shutil.rmtree(root)
    base = datetime.now() - timedelta(days=10)
    small = Scale.small()
    small.research_runs = min(20, scale.research_runs)
    small.software_services = 0
    small.finance_docs = min(15, scale.finance_docs)
    small.media_assets = min(10, scale.media_assets)
    build_project_a(root, base - timedelta(days=3), small)
    build_project_c(root, base - timedelta(days=1), small)
    noise_files(root, base, scale.mixed_noise)
    queries = main_queries_core()[:12]
    for i in range(1, max(0, scale.mixed_queries - len(queries)) + 1):
        tag = f"{i:03d}"
        queries.append(
            {
                "q": f"混合场景发票 {i}",
                "direct": [f"发票_{tag}.pdf.md"],
                "indirect": [f"发票_{tag}_扫描.jpg.md"],
            }
        )
    gt = {
        "dataset": "personal_mixed",
        "description": f"跨场景混合，噪声 {scale.mixed_noise}",
        "queries": queries[: scale.mixed_queries],
    }
    write_annotations("personal_mixed", gt)


def build_version_lineage(*, clean: bool = False) -> dict:
    """专项：版本链 / 备份（HAS_VERSION、IS_BACKUP_OF）。"""
    root = BENCH / "version_lineage"
    if clean and root.exists():
        shutil.rmtree(root)
    base = datetime.now() - timedelta(days=14)
    docs = [
        ("白皮书_v1.docx.md", "# 白皮书 初稿\n概述产品路线。\n"),
        ("白皮书_v2.docx.md", "# 白皮书 修订\n补充竞品分析。\n"),
        ("白皮书_v3.docx.md", "# 白皮书 三稿\n更新指标表格。\n"),
        ("白皮书终稿.pdf.md", "# 白皮书 终稿\n正式发布版本。\n" * 4),
        ("白皮书_backup.docx.md", "# 白皮书 备份\n与 v2 内容一致备份。\n"),
        ("需求说明书_draft.md", "# 需求 草案\n"),
        ("需求说明书_final.md", "# 需求 定稿\n"),
        ("会议纪要_v1.md", "# 周会纪要 v1\n"),
        ("会议纪要_v2.md", "# 周会纪要 v2\n"),
        ("附录A.md", "# 附录\n引用白皮书终稿指标。\n"),
        ("noise_note.txt", "无关笔记\n"),
        ("readme_versions.md", "版本目录说明\n"),
    ]
    for i, (name, body) in enumerate(docs):
        write(root / name, body)
        touch(root / name, base, i * 30)

    queries = [
        {
            "q": "白皮书最新终稿",
            "direct": ["白皮书终稿.pdf.md"],
            "indirect": ["白皮书_v3.docx.md", "白皮书_v2.docx.md"],
        },
        {
            "q": "白皮书第二版修订",
            "direct": ["白皮书_v2.docx.md"],
            "indirect": ["白皮书_v1.docx.md", "白皮书_backup.docx.md"],
        },
        {
            "q": "白皮书备份文件",
            "direct": ["白皮书_backup.docx.md"],
            "indirect": ["白皮书_v2.docx.md"],
        },
        {
            "q": "需求说明书定稿",
            "direct": ["需求说明书_final.md"],
            "indirect": ["需求说明书_draft.md"],
        },
        {
            "q": "周会纪要最新版",
            "direct": ["会议纪要_v2.md"],
            "indirect": ["会议纪要_v1.md"],
        },
        {
            "q": "白皮书所有历史版本",
            "direct": ["白皮书终稿.pdf.md"],
            "indirect": ["白皮书_v1.docx.md", "白皮书_v2.docx.md", "白皮书_v3.docx.md"],
        },
        {
            "q": "附录引用的白皮书",
            "direct": ["附录A.md"],
            "indirect": ["白皮书终稿.pdf.md"],
        },
        {
            "q": "需求草案文档",
            "direct": ["需求说明书_draft.md"],
            "indirect": ["需求说明书_final.md"],
        },
    ]
    gt = {
        "dataset": "version_lineage",
        "description": "版本链专项：HAS_VERSION / 备份关系",
        "focus_relations": ["HAS_VERSION", "IS_BACKUP_OF", "IS_PREVIOUS_VERSION_OF"],
        "queries": queries,
    }
    write_annotations("version_lineage", gt)
    return {"id": "version_lineage", "files": len(docs), "queries": len(queries)}


def build_office_workflow(*, clean: bool = False) -> dict:
    """专项：办公共现 / 时间邻近（WORKFLOW_WITH、NEAR_IN_TIME）。"""
    root = BENCH / "office_workflow"
    if clean and root.exists():
        shutil.rmtree(root)
    base = datetime.now() - timedelta(days=3)
    # 同一时间窗内的「打开」簇：议程 → 纪要 → 幻灯片
    cluster_a = [
        ("季度规划_议程.md", "# 议程\n1. 指标回顾\n2. 下季规划\n"),
        ("季度规划_纪要.md", "# 纪要\n讨论了销售指标与资源。\n"),
        ("季度规划_幻灯片.pptx.md", "# 幻灯片\n销售漏斗与 OKR\n"),
    ]
    cluster_b = [
        ("客户拜访_清单.csv", "客户,日期\nA,2024-01-02\n"),
        ("客户拜访_记录.md", "# 拜访记录\n跟进清单中的客户 A。\n"),
        ("客户拜访_邮件草稿.md", "# 跟进邮件\n引用拜访记录要点。\n"),
    ]
    extras = [
        ("无关_购物清单.txt", "牛奶 鸡蛋\n"),
        ("模板_空白.md", "# 空模板\n"),
        ("归档_旧议程.md", "# 去年议程\n"),
        ("归档_旧纪要.md", "# 去年纪要\n"),
    ]
    for i, (name, body) in enumerate(cluster_a):
        write(root / "q1" / name, body)
        touch(root / "q1" / name, base, i)  # 同分钟窗
    for i, (name, body) in enumerate(cluster_b):
        write(root / "sales" / name, body)
        touch(root / "sales" / name, base + timedelta(hours=2), i)
    for i, (name, body) in enumerate(extras):
        write(root / "misc" / name, body)
        touch(root / "misc" / name, base - timedelta(days=10), i * 60)

    # 工作流日志：重复打开簇 A，便于 WORKFLOW_WITH
    log = ROOT / "data" / "workflow_log_office.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    seq = [root / "q1" / n for n, _ in cluster_a]
    with log.open("w", encoding="utf-8") as f:
        for _ in range(6):
            for p in seq:
                f.write(json.dumps({"path": str(p.resolve()), "event": "open"}, ensure_ascii=False) + "\n")
            f.write(json.dumps({"event": "session_end"}) + "\n")

    queries = [
        {
            "q": "季度规划会议纪要",
            "direct": ["季度规划_纪要.md"],
            "indirect": ["季度规划_议程.md", "季度规划_幻灯片.pptx.md"],
        },
        {
            "q": "与议程一起打开的幻灯片",
            "direct": ["季度规划_幻灯片.pptx.md"],
            "indirect": ["季度规划_议程.md", "季度规划_纪要.md"],
        },
        {
            "q": "客户拜访跟进邮件",
            "direct": ["客户拜访_邮件草稿.md"],
            "indirect": ["客户拜访_记录.md", "客户拜访_清单.csv"],
        },
        {
            "q": "拜访清单 csv",
            "direct": ["客户拜访_清单.csv"],
            "indirect": ["客户拜访_记录.md"],
        },
        {
            "q": "季度规划议程文档",
            "direct": ["季度规划_议程.md"],
            "indirect": ["季度规划_纪要.md"],
        },
        {
            "q": "销售拜访记录",
            "direct": ["客户拜访_记录.md"],
            "indirect": ["客户拜访_清单.csv", "客户拜访_邮件草稿.md"],
        },
        {
            "q": "同一时段的规划材料",
            "direct": ["季度规划_议程.md", "季度规划_纪要.md"],
            "indirect": ["季度规划_幻灯片.pptx.md"],
        },
        {
            "q": "去年归档议程",
            "direct": ["归档_旧议程.md"],
            "indirect": ["归档_旧纪要.md"],
        },
    ]
    gt = {
        "dataset": "office_workflow",
        "description": "办公共现专项：WORKFLOW_WITH / NEAR_IN_TIME",
        "focus_relations": ["WORKFLOW_WITH", "NEAR_IN_TIME", "IN_FOLDER"],
        "queries": queries,
    }
    write_annotations("office_workflow", gt)
    return {
        "id": "office_workflow",
        "files": len(cluster_a) + len(cluster_b) + len(extras),
        "queries": len(queries),
    }


def build_doc_references(*, clean: bool = False) -> dict:
    """专项：引用 / 包含（REFERENCES、CONTAINS）。"""
    root = BENCH / "doc_references"
    if clean and root.exists():
        shutil.rmtree(root)
    base = datetime.now() - timedelta(days=20)
    files = [
        ("survey_paper.md", "# Survey\n参见 [bib](file://refs.bib) 与图 fig_arch.png.md\n"),
        ("method_paper.md", "# Method\n依赖 survey_paper 背景，引用 refs.bib\n"),
        ("refs.bib", "@article{kg2024,title={File Knowledge Graph}}\n@inproceedings{ir2023,title={IR}}\n"),
        ("fig_arch.png.md", "系统架构图\n"),
        ("fig_ablation.png.md", "消融实验图\n"),
        ("supplement.pdf.md", "# 补充材料\n包含额外表格。\n"),
        ("notes_on_survey.md", "阅读笔记：survey_paper 第3节\n"),
        ("dataset_readme.md", "数据说明，打包于 corpus.zip\n"),
        ("unrelated_todo.txt", "买菜\n"),
        ("cite_guide.md", "引用格式说明，示例见 refs.bib\n"),
    ]
    for i, (name, body) in enumerate(files):
        write(root / name, body)
        touch(root / name, base, i * 15)

    with zipfile.ZipFile(root / "corpus.zip", "w") as zf:
        zf.writestr("raw/table.csv", "a,b\n1,2\n")
        zf.writestr("raw/meta.json", '{"n": 2}\n')

    queries = [
        {
            "q": "综述论文引用的 bib",
            "direct": ["refs.bib"],
            "indirect": ["survey_paper.md", "method_paper.md"],
        },
        {
            "q": "架构图文件",
            "direct": ["fig_arch.png.md"],
            "indirect": ["survey_paper.md"],
        },
        {
            "q": "方法论文档",
            "direct": ["method_paper.md"],
            "indirect": ["survey_paper.md", "refs.bib"],
        },
        {
            "q": "引用格式指南",
            "direct": ["cite_guide.md"],
            "indirect": ["refs.bib"],
        },
        {
            "q": "语料压缩包",
            "direct": ["corpus.zip"],
            "indirect": ["dataset_readme.md"],
        },
        {
            "q": "综述阅读笔记",
            "direct": ["notes_on_survey.md"],
            "indirect": ["survey_paper.md"],
        },
        {
            "q": "消融实验图",
            "direct": ["fig_ablation.png.md"],
            "indirect": ["supplement.pdf.md"],
        },
        {
            "q": "补充材料 pdf",
            "direct": ["supplement.pdf.md"],
            "indirect": ["fig_ablation.png.md"],
        },
    ]
    gt = {
        "dataset": "doc_references",
        "description": "文档引用专项：REFERENCES / CONTAINS",
        "focus_relations": ["REFERENCES", "CONTAINS", "IN_FOLDER"],
        "queries": queries,
    }
    write_annotations("doc_references", gt)
    return {"id": "doc_references", "files": len(files) + 1, "queries": len(queries)}


def build_extended_benchmarks(*, clean: bool = False) -> list[dict]:
    """新增三项合成专项（版本链 / 办公共现 / 文档引用）。"""
    return [
        build_version_lineage(clean=clean),
        build_office_workflow(clean=clean),
        build_doc_references(clean=clean),
    ]


def write_registry(scale: Scale) -> None:
    reg = {
        "datasets": [
            {
                "id": "filekg_main",
                "name": "FileKG 合成主基准（方案 8.2）",
                "path": "data/benchmarks/filekg_main",
                "ground_truth": "data/benchmarks/annotations/filekg_main.json",
                "queries": scale.main_queries,
                "target_files": scale.core_files + scale.noise,
                "source": "synthetic",
            },
            {
                "id": "code_dependency",
                "name": "工程依赖专项",
                "path": "data/benchmarks/code_dependency",
                "ground_truth": "data/benchmarks/annotations/code_dependency.json",
                "queries": scale.code_queries,
                "target_files": scale.code_files,
                "source": "synthetic",
            },
            {
                "id": "personal_mixed",
                "name": "跨场景个人文件混合",
                "path": "data/benchmarks/personal_mixed",
                "ground_truth": "data/benchmarks/annotations/personal_mixed.json",
                "queries": scale.mixed_queries,
                "source": "synthetic",
            },
            {
                "id": "version_lineage",
                "name": "版本链专项（HAS_VERSION）",
                "path": "data/benchmarks/version_lineage",
                "ground_truth": "data/benchmarks/annotations/version_lineage.json",
                "queries": 8,
                "target_files": 12,
                "source": "synthetic_extended",
            },
            {
                "id": "office_workflow",
                "name": "办公共现专项（WORKFLOW_WITH）",
                "path": "data/benchmarks/office_workflow",
                "ground_truth": "data/benchmarks/annotations/office_workflow.json",
                "queries": 8,
                "target_files": 10,
                "source": "synthetic_extended",
            },
            {
                "id": "doc_references",
                "name": "文档引用专项（REFERENCES）",
                "path": "data/benchmarks/doc_references",
                "ground_truth": "data/benchmarks/annotations/doc_references.json",
                "queries": 8,
                "target_files": 11,
                "source": "synthetic_extended",
            },
            {
                "id": "hippocamp_adam",
                "name": "HippoCamp Adam-Subset（真实个人文件）",
                "path": "data/benchmarks/hippocamp_adam",
                "ground_truth": "data/benchmarks/annotations/hippocamp_adam.json",
                "queries": 0,
                "source": "hippocamp",
                "note": "运行 download_hippocamp_subset.py 后可用",
            },
        ]
    }
    write(BENCH / "registry.json", json.dumps(reg, ensure_ascii=False, indent=2))


def write_human_review_template() -> None:
    tpl = ANNOT / "HUMAN_REVIEW_CHECKLIST.md"
    tpl.write_text(
        """# 人工抽检清单（建议 ≥10% 查询）

对每条查询确认：
- [ ] direct / indirect 标注正确
- [ ] 查询未直接包含目标完整文件名（避免泄漏）
- [ ] 间接相关确实需通过图关系才能发现

抽检人: ______  日期: ______
""",
        encoding="utf-8",
    )


def count_index_files() -> int:
    n = 0
    for p in BENCH.rglob("*"):
        if not p.is_file():
            continue
        if "annotations" in p.parts:
            continue
        if p.suffix == ".json" and p.name == "registry.json":
            continue
        n += 1
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description="生成评测基准数据集")
    parser.add_argument(
        "--scale",
        choices=("small", "scheme"),
        default="scheme",
        help="small=快速调试, scheme≈1200文件（默认）",
    )
    parser.add_argument("--clean", action="store_true", help="重建前删除已有目录")
    parser.add_argument(
        "--extended-only",
        action="store_true",
        help="仅生成三项扩展专项（version_lineage / office_workflow / doc_references）",
    )
    args = parser.parse_args()
    scale = Scale.small() if args.scale == "small" else Scale.scheme()

    if args.extended_only:
        stats = build_extended_benchmarks(clean=args.clean)
        write_registry(scale)
        for s in stats:
            print(f"  - {s['id']}: {s['files']} 文件, {s['queries']} 查询")
        print(f"扩展基准已生成: {BENCH}")
        return

    build_filekg_main(scale, clean=args.clean)
    build_code_dependency(scale, clean=args.clean)
    build_personal_mixed(scale, clean=args.clean)
    ext_stats = build_extended_benchmarks(clean=args.clean)
    write_registry(scale)
    write_human_review_template()

    main_n = sum(1 for _ in (BENCH / "filekg_main").rglob("*") if _.is_file())
    total = count_index_files()
    print(f"基准已生成: {BENCH}")
    print(f"  - filekg_main: 约 {main_n} 个文件, {scale.main_queries} 查询 (目标 {scale.core_files + scale.noise})")
    print(f"  - code_dependency: 目标 {scale.code_files} 文件, {scale.code_queries} 查询")
    print(f"  - personal_mixed: {scale.mixed_queries} 查询")
    for s in ext_stats:
        print(f"  - {s['id']}: {s['files']} 文件, {s['queries']} 查询")
    print(f"  - 索引目录合计约 {total} 个文件")


if __name__ == "__main__":
    main()
