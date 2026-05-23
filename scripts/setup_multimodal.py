#!/usr/bin/env python3
"""拉取多模态依赖：Ollama whisper/moondream + HuggingFace CLIP（本地缓存）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], label: str) -> bool:
    print(f"\n>>> {label}")
    print(" ".join(cmd))
    try:
        subprocess.check_call(cmd, cwd=str(ROOT))
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"  跳过或失败: {e}")
        return False


def main() -> None:
    run(["ollama", "pull", "moondream"], "Ollama moondream（图像/视频帧描述）")
    print("\n>>> 音频转写使用 faster-whisper（Ollama 无 whisper 官方模型名）")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "faster-whisper"],
        cwd=str(ROOT),
    )

    print("\n>>> 预下载 CLIP 视觉编码器")
    try:
        from transformers import CLIPModel, CLIPProcessor

        name = "openai/clip-vit-base-patch32"
        CLIPProcessor.from_pretrained(name)
        CLIPModel.from_pretrained(name)
        print(f"  CLIP 已缓存: {name}")
    except Exception as e:
        print(f"  CLIP 预下载失败（索引时可自动重试）: {e}")

    print("\n>>> 检查 opencv（视频抽帧）")
    try:
        import cv2  # noqa: F401

        print("  opencv 可用")
    except ImportError:
        print("  请安装: pip install opencv-python-headless")

    print("\n完成。启动服务前请确认 Ollama 正在运行: ollama serve")
    print("  配置见 config.yaml -> multimodal / visual / llm")


if __name__ == "__main__":
    main()
