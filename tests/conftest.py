"""全局测试环境：hash 嵌入、快速索引、禁用心跳与后台加载。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("FILEKG_EMBEDDING_BACKEND", "hash")
os.environ.setdefault("FILEKG_INDEX_FAST", "1")
os.environ.setdefault("FILEKG_API_MANUAL_LOAD", "true")
os.environ.setdefault("FILEKG_API_HEARTBEAT_ENABLED", "false")
os.environ.setdefault("FILEKG_VISUAL_ENABLED", "false")
os.environ.setdefault("FILEKG_MULTIMODAL_ENABLED", "false")
os.environ.setdefault("FILEKG_MULTIMODAL_VISUAL_INDEX_ENABLED", "false")
os.environ.setdefault("FILEKG_MULTIMODAL_FUSE_VISUAL_SEARCH", "false")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from src.api.app import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)
