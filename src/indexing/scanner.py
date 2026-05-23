from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path

from src.config import settings
from src.indexing.embedder import Embedder
from src.indexing.extractor import build_summary, extract_text
from src.multimodal.extractor import extract_media_content
from src.indexing.file_id import get_file_id
from src.models.descriptor import FileDescriptor, FileStatus


SKIP_DIRS = {
    ".git", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "Library", "AppData", "$Recycle.Bin",
}
SKIP_EXTENSIONS = {".exe", ".dll", ".so", ".dylib", ".bin", ".iso", ".img"}
SKIP_FILENAMES = {
    "ground_truth.json",
    "registry.json",
    "metrics.json",
    "comparison_summary.json",
    "ablation.json",
}
SKIP_DIR_NAMES = {"annotations", "evaluation", "hf_cache"}


def scan_directory(
    root: str | Path,
    *,
    max_files: int | None = None,
    project_map: dict[str, str] | None = None,
    id_mode: str = "volume",
) -> list[FileDescriptor]:
    root = Path(root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)

    descriptors: list[FileDescriptor] = []
    embedder = Embedder.get()
    count = 0

    for path in root.rglob("*"):
        if max_files and count >= max_files:
            break
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.name in SKIP_FILENAMES:
            continue
        if path.suffix.lower() in SKIP_EXTENSIONS:
            continue
        try:
            desc = build_descriptor(path, embedder, project_map, id_mode=id_mode)
            descriptors.append(desc)
            count += 1
        except (OSError, PermissionError) as e:
            descriptors.append(
                FileDescriptor(
                    file_id=f"error:{path}",
                    path=str(path),
                    name=path.name,
                    extension=path.suffix.lower(),
                    size=0,
                    created_time=datetime.utcnow(),
                    modified_time=datetime.utcnow(),
                    status=FileStatus.ERROR,
                    summary=str(e),
                )
            )

    return descriptors


def build_descriptor(
    path: Path,
    embedder: Embedder | None = None,
    project_map: dict[str, str] | None = None,
    *,
    id_mode: str = "volume",
) -> FileDescriptor:
    embedder = embedder or Embedder.get()
    stat = path.stat()
    file_id = get_file_id(path, mode=id_mode)
    media_kind = ""
    visual_embedding: list[float] = []
    if settings.multimodal_enabled:
        media = extract_media_content(path)
        media_kind = media.kind.value
        text = media.searchable_text()
        if not text.strip():
            text = extract_text(path)
        summary, ai_summary = build_summary(path, text or f"文件 {path.name}")
        if media.vision_caption and media.vision_caption[:30] not in (ai_summary or ""):
            ai_summary = (media.vision_caption[:120] + " · " + (ai_summary or ""))[:200]
        if media.visual_embedding:
            visual_embedding = media.visual_embedding
    else:
        text = extract_text(path)
        summary, ai_summary = build_summary(path, text)
    embed_text = "\n".join(
        x for x in (summary, ai_summary, text) if x and x.strip()
    ).strip() or path.name
    embedding = embedder.embed(embed_text)

    project_id = None
    if project_map:
        path_str = str(path.resolve())
        for prefix, pid in sorted(project_map.items(), key=lambda x: -len(x[0])):
            if path_str.startswith(prefix):
                project_id = pid
                break

    mime, _ = mimetypes.guess_type(str(path))
    return FileDescriptor(
        file_id=file_id,
        path=str(path.resolve()),
        name=path.name,
        extension=path.suffix.lower(),
        size=stat.st_size,
        created_time=datetime.fromtimestamp(stat.st_ctime),
        modified_time=datetime.fromtimestamp(stat.st_mtime),
        mime_type=mime,
        summary=summary,
        ai_summary=ai_summary,
        file_embedding=embedding,
        visual_embedding=visual_embedding,
        media_kind=media_kind,
        project_id=project_id,
    )
