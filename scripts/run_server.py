#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import uvicorn

if __name__ == "__main__":
    # 排除 data 日志/chroma 变更，避免 reload 卡在旧 worker
    uvicorn.run(
        "src.api.app:app",
        host="0.0.0.0",
        port=8765,
        reload=True,
        reload_excludes=["data/*", "*.log"],
    )
