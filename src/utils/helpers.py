"""Utility helpers for FileKG."""

import hashlib
import os
import stat
from pathlib import Path
from typing import Optional

TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml",
    ".html", ".css", ".xml", ".csv", ".log", ".rst", ".ini", ".cfg",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"}


def normalize_path(path: str | Path) -> str:
    return str(Path(path).resolve()).replace("\\", "/")


def path_hash(path: str) -> str:
    return hashlib.md5(normalize_path(path).encode("utf-8")).hexdigest()


def extension_of(path: str | Path) -> str:
    return Path(path).suffix.lower()


def is_text_extension(ext: str) -> bool:
    return ext.lower() in TEXT_EXTENSIONS


def is_image_extension(ext: str) -> bool:
    return ext.lower() in IMAGE_EXTENSIONS


def get_file_inode(file_path: str | Path) -> str:
    """Return OS-specific unique file identifier."""
    p = Path(file_path)
    if not p.exists():
        return ""
    try:
        st = p.stat()
        if os.name == "nt":
            return f"{st.st_dev}:{st.st_ino}"
        return str(st.st_ino)
    except OSError:
        return ""


def safe_read_text(file_path: str | Path, max_bytes: int = 1_000_000) -> str:
    path = Path(file_path)
    if not path.is_file():
        return ""
    try:
        with open(path, "rb") as f:
            raw = f.read(max_bytes)
        return raw.decode("utf-8", errors="ignore")
    except OSError:
        return ""


def days_since(timestamp: float, now: Optional[float] = None) -> float:
    import time
    if now is None:
        now = time.time()
    return max(0.0, (now - timestamp) / 86400.0)
