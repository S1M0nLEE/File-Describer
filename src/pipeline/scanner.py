"""Directory scanner and file metadata extraction."""

import os
from pathlib import Path
from typing import List, Optional, Set

from src.config import Config
from src.models.file_descriptor import FileDescriptor
from src.utils.helpers import extension_of, get_file_inode, normalize_path

try:
    import magic
    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False


class FileScanner:
    SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".chroma"}

    def __init__(self, config: Optional[Config] = None):
        self.config = config

    def scan(
        self,
        root_path: Path,
        extensions: Optional[Set[str]] = None,
    ) -> List[FileDescriptor]:
        root = Path(root_path).resolve()
        files: List[FileDescriptor] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in self.SKIP_DIRS]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                ext = extension_of(fpath)
                if extensions and ext not in extensions:
                    continue
                try:
                    st = fpath.stat()
                except OSError:
                    continue
                norm = normalize_path(fpath)
                mime = self._detect_mime(fpath)
                fd = FileDescriptor(
                    id=FileDescriptor.generate_id(norm),
                    path=norm,
                    name=fname,
                    extension=ext,
                    size=st.st_size,
                    modified_time=st.st_mtime,
                    created_time=getattr(st, "st_ctime", st.st_mtime),
                    file_id=get_file_inode(fpath),
                    mime_type=mime,
                )
                files.append(fd)
        return files

    def _detect_mime(self, path: Path) -> str:
        if not HAS_MAGIC:
            return ""
        try:
            return magic.from_file(str(path), mime=True) or ""
        except Exception:
            return ""
