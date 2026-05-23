from __future__ import annotations

import logging
from pathlib import Path

from src.config import settings
from src.indexing.extractor import extract_text
from src.multimodal.ollama_media import describe_image, transcribe_audio
from src.multimodal.types import ExtractedMedia, MediaKind
from src.multimodal.video_frames import is_video, sample_frame_paths
from src.multimodal.vision_encoder import VisionEncoder

logger = logging.getLogger(__name__)

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma", ".opus"}
_DOC_EXT = {".pdf", ".docx", ".xlsx"}


def extract_media_content(path: Path) -> ExtractedMedia:
    ext = path.suffix.lower()
    name = path.name

    if ext in _IMAGE_EXT:
        return _extract_image(path, ext, name)
    if is_video(ext):
        return _extract_video(path, ext, name)
    if ext in _AUDIO_EXT:
        return _extract_audio(path, ext, name)
    if ext in _DOC_EXT or ext in {".txt", ".md", ".eml", ".ics", ".html", ".py"}:
        text = extract_text(path)
        return ExtractedMedia(kind=MediaKind.DOCUMENT, text=text)
    text = extract_text(path)
    if text.strip():
        return ExtractedMedia(kind=MediaKind.TEXT, text=text)
    return ExtractedMedia(kind=MediaKind.OTHER, text=f"文件 {name}")


def _extract_image(path: Path, ext: str, name: str) -> ExtractedMedia:
    caption = describe_image(path) if settings.multimodal_enabled else ""
    vec = None
    if settings.multimodal_visual_index_enabled or settings.visual_enabled:
        enc = VisionEncoder.get()
        arr = enc.embed_image_path(path, ext)
        if arr is not None:
            vec = arr.tolist()

    parts = [f"[图片] {name}"]
    if caption:
        parts.append(f"视觉描述: {caption}")
    return ExtractedMedia(
        kind=MediaKind.IMAGE,
        text="\n".join(parts),
        vision_caption=caption,
        visual_embedding=vec,
        tags=["image"],
    )


def _extract_video(path: Path, ext: str, name: str) -> ExtractedMedia:
    if path.stat().st_size > settings.multimodal_max_video_bytes:
        return ExtractedMedia(
            kind=MediaKind.VIDEO,
            text=f"[视频] {name}（文件过大，仅索引文件名）",
            tags=["video"],
        )

    transcript = ""
    if settings.multimodal_whisper_enabled:
        transcript = transcribe_audio(path)

    frame_caps: list[str] = []
    enc = VisionEncoder.get()
    visual_vec = None
    n_frames = settings.multimodal_video_max_frames

    if settings.multimodal_enabled:
        for fp in sample_frame_paths(path, n_frames):
            cap = describe_image(fp) if settings.multimodal_vision_caption_enabled else ""
            if cap:
                frame_caps.append(cap)
            if visual_vec is None and enc.available():
                arr = enc.embed_image_path(fp, ".jpg")
                if arr is not None:
                    visual_vec = arr.tolist()

    parts = [f"[视频] {name}"]
    if transcript:
        parts.append(f"语音转写: {transcript}")
    if frame_caps:
        parts.append("画面描述: " + " | ".join(frame_caps[:6]))
    return ExtractedMedia(
        kind=MediaKind.VIDEO,
        text="\n".join(parts),
        transcript=transcript,
        frame_captions=frame_caps,
        visual_embedding=visual_vec,
        tags=["video"],
    )


def _extract_audio(path: Path, ext: str, name: str) -> ExtractedMedia:
    transcript = transcribe_audio(path) if settings.multimodal_whisper_enabled else ""
    parts = [f"[音频] {name}"]
    if transcript:
        parts.append(f"转写: {transcript}")
    else:
        parts.append("（无转写或 Ollama whisper 不可用）")
    return ExtractedMedia(
        kind=MediaKind.AUDIO,
        text="\n".join(parts),
        transcript=transcript,
        tags=["audio"],
    )
