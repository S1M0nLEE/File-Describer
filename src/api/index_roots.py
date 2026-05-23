from __future__ import annotations

import os
from pathlib import Path

from src.config import settings


def resolve_rag_index_roots() -> list[Path]:
    expanded: list[Path] = []
    for r in settings.rag_index_roots or []:
        p = Path(os.path.expandvars(r)).expanduser()
        if p.is_dir():
            expanded.append(p)
    if not expanded:
        home = Path.home()
        for name in ("Documents", "Desktop", "Downloads"):
            p = home / name
            if p.is_dir():
                expanded.append(p)
    return expanded
