"""本地多模态内容抽取：图像 / 视频 / 音频 → 可检索文本 + 可选视觉向量。"""

from src.multimodal.extractor import extract_media_content

__all__ = ["extract_media_content"]
