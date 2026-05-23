#!/usr/bin/env python3
"""安装 RAG 依赖并检查 DeepSeek 配置。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "openai>=1.40.0", "python-dotenv>=1.0.0"],
        cwd=str(ROOT),
    )
    sys.path.insert(0, str(ROOT))
    from src.config import settings
    from src.llm.deepseek_client import DeepSeekClient

    print("DEEPSEEK_API_KEY:", "已设置" if settings.deepseek_api_key else "未设置（请编辑 .env）")
    print("模型:", settings.deepseek_model)
    client = DeepSeekClient()
    if client.is_available():
        try:
            ans = client.chat(
                [{"role": "user", "content": "回复：连接成功"}],
                stream=False,
            )
            print("API 测试:", (ans or "")[:200])
        except Exception as e:
            print("API 测试失败:", e)
    else:
        print("DeepSeek 客户端未就绪")
    print("\n下一步: python scripts/index_local_pc.py")
    print("然后:   python scripts/run_server.py")


if __name__ == "__main__":
    main()
