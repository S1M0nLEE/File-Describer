#!/usr/bin/env python3
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import uvicorn

from src.config import settings

if __name__ == "__main__":
    reload = os.environ.get("FILEKG_NO_RELOAD", "").lower() not in ("1", "true", "yes")
    if "--no-reload" in sys.argv:
        reload = False
    host = os.environ.get("FILEKG_HOST", settings.api_host)
    port = int(os.environ.get("FILEKG_PORT", str(settings.api_port)))
    uvicorn.run(
        "src.api.app:app",
        host=host,
        port=port,
        reload=reload,
        reload_excludes=["data/*", "*.log"] if reload else None,
    )
