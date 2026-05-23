from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _base_url() -> str:
    return settings.llm_ollama_base.rstrip("/")


def ollama_reachable() -> bool:
    try:
        r = httpx.get(f"{_base_url()}/api/tags", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def transcribe_audio(path: Path) -> str:
    """音频/视频转写：优先 Ollama /api/transcribe，失败则用本地 faster-whisper。"""
    if not settings.multimodal_whisper_enabled:
        return ""
    if path.stat().st_size > settings.multimodal_max_audio_bytes:
        logger.info("音频过大跳过转写: %s", path.name)
        return ""
    text = _transcribe_ollama(path)
    if text:
        return text
    return _transcribe_faster_whisper(path)


def _transcribe_ollama(path: Path) -> str:
    if not ollama_reachable() or not settings.multimodal_whisper_model:
        return ""
    try:
        with path.open("rb") as f:
            files = {"file": (path.name, f, "application/octet-stream")}
            data = {"model": settings.multimodal_whisper_model}
            r = httpx.post(
                f"{_base_url()}/api/transcribe",
                files=files,
                data=data,
                timeout=settings.multimodal_ollama_timeout,
            )
        if r.status_code != 200:
            return ""
        return (r.json().get("text") or "").strip()
    except Exception as e:
        logger.debug("Ollama transcribe %s: %s", path.name, e)
        return ""


def _transcribe_faster_whisper(path: Path) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        logger.info(
            "未安装 faster-whisper，音频将仅索引文件名。运行: pip install faster-whisper"
        )
        return ""
    try:
        model = WhisperModel(
            settings.multimodal_faster_whisper_size,
            device="cpu",
            compute_type="int8",
        )
        segments, _ = model.transcribe(str(path), vad_filter=True)
        return " ".join(seg.text.strip() for seg in segments if seg.text).strip()
    except Exception as e:
        logger.warning("faster-whisper 转写失败 %s: %s", path.name, e)
        return ""


def describe_image(path: Path, *, prompt: str | None = None) -> str:
    """Ollama 视觉模型生成图像描述（moondream / llava 等）。"""
    if not settings.multimodal_vision_caption_enabled or not ollama_reachable():
        return ""
    if path.suffix.lower() not in _IMAGE_EXT:
        return ""
    try:
        raw = path.read_bytes()
        if len(raw) > settings.multimodal_max_image_bytes:
            return ""
        b64 = base64.b64encode(raw).decode("ascii")
        user_prompt = prompt or (
            "Describe this image in detail for personal file search indexing. "
            "Include scene, objects, people, text visible, and mood. "
            "Reply in the same language as visible text, otherwise English or Chinese."
        )
        payload = {
            "model": settings.multimodal_vision_llm_model,
            "messages": [
                {
                    "role": "user",
                    "content": user_prompt,
                    "images": [b64],
                }
            ],
            "stream": False,
        }
        r = httpx.post(
            f"{_base_url()}/api/chat",
            json=payload,
            timeout=settings.multimodal_ollama_timeout,
        )
        if r.status_code != 200:
            return ""
        msg = r.json().get("message") or {}
        return (msg.get("content") or "").strip()
    except Exception as e:
        logger.debug("describe_image %s: %s", path, e)
        return ""


def describe_image_bytes(image_bytes: bytes, *, prompt: str | None = None) -> str:
    if not settings.multimodal_vision_caption_enabled or not ollama_reachable():
        return ""
    try:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        user_prompt = prompt or "Briefly describe this video frame for file search."
        payload = {
            "model": settings.multimodal_vision_llm_model,
            "messages": [{"role": "user", "content": user_prompt, "images": [b64]}],
            "stream": False,
        }
        r = httpx.post(
            f"{_base_url()}/api/chat",
            json=payload,
            timeout=settings.multimodal_ollama_timeout,
        )
        if r.status_code != 200:
            return ""
        return ((r.json().get("message") or {}).get("content") or "").strip()
    except Exception:
        return ""
