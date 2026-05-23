"""OCR 文本路与版面特征（PaddleOCR 可选；回退为已索引文本 + 启发式版面）。"""
from __future__ import annotations

import re
from pathlib import Path

from src.models.descriptor import FileDescriptor

_SCREENSHOT_HINTS = re.compile(
    r"screenshot|截图|snipaste|screen.?shot|截屏",
    re.I,
)


def extract_ocr_text(descriptor: FileDescriptor) -> str:
    meta = descriptor.metadata or {}
    if meta.get("ocr_text"):
        return str(meta["ocr_text"])
    if meta.get("multimodal_caption"):
        return str(meta["multimodal_caption"])
    parts = [descriptor.summary, descriptor.ai_summary]
    return "\n".join(p for p in parts if p).strip()


def infer_media_route(descriptor: FileDescriptor, ocr_len: int) -> str:
    ext = descriptor.extension.lower()
    name_l = descriptor.name.lower()
    if ext in {".pdf", ".doc", ".docx", ".ppt", ".pptx"}:
        return "document_page"
    if ocr_len >= 50 or _SCREENSHOT_HINTS.search(name_l):
        return "screenshot"
    if ocr_len < 50 and ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        return "natural_photo"
    return "generic_image"


def layout_features(text: str) -> tuple[int, int]:
    """返回 (文本块数估计, 列数推断)。"""
    if not text.strip():
        return 0, 0
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    block_count = max(len(blocks), 1)
    line_lens = [len(ln) for ln in text.splitlines() if ln.strip()]
    if not line_lens:
        return block_count, 1
    avg = sum(line_lens) / len(line_lens)
    cols = 2 if avg < 40 and len(line_lens) > 8 else 1
    return block_count, cols


def text_similarity(a: str, b: str) -> float:
    if not a.strip() or not b.strip():
        return 0.0
    ta = set(re.findall(r"[\w\u4e00-\u9fff]+", a.lower()))
    tb = set(re.findall(r"[\w\u4e00-\u9fff]+", b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def try_paddle_ocr(path: Path) -> str:
    try:
        from paddleocr import PaddleOCR

        ocr = PaddleOCR(use_angle_cls=False, lang="ch", show_log=False)
        result = ocr.ocr(str(path), cls=False)
        lines = []
        for page in result or []:
            for line in page or []:
                if line and len(line) > 1:
                    lines.append(str(line[1][0]))
        return "\n".join(lines)
    except Exception:
        return ""
