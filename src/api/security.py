"""API 安全：可选 Token、索引路径 allowlist、路径脱敏。"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import get_config

_ROOT = Path(__file__).resolve().parents[2]
_bearer = HTTPBearer(auto_error=False)

PUBLIC_PATH_PREFIXES = (
    "/",
    "/health",
    "/static",
    "/docs",
    "/redoc",
    "/openapi.json",
)


def _default_allow_bases() -> list[Path]:
    settings = get_config()
    bases = [
        Path.home().resolve(),
        settings.data_dir.resolve(),
        _ROOT.resolve(),
    ]
    seen: set[str] = set()
    out: list[Path] = []
    for b in bases:
        key = str(b)
        if key not in seen:
            seen.add(key)
            out.append(b)
    return out


def resolve_allow_bases() -> list[Path]:
    settings = get_config()
    raw = settings.api_index_allow_roots or []
    if not raw:
        return _default_allow_bases()
    return [Path(os_expand(p)).resolve() for p in raw]


def os_expand(p: str) -> str:
    import os

    return str(Path(os.path.expandvars(p)).expanduser())


def is_path_allowed(path: str | Path) -> bool:
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError:
        return False
    if not resolved.exists():
        # 允许尚不存在的子路径规划（仅目录索引会再校验 is_dir）
        resolved = resolved
    for base in resolve_allow_bases():
        try:
            if resolved.is_relative_to(base):
                return True
        except (ValueError, OSError):
            continue
    return False


def validate_index_directory(path: str | Path) -> Path:
    p = Path(path).expanduser()
    if not p.is_dir():
        raise HTTPException(status_code=400, detail=f"目录不存在: {path}")
    try:
        resolved = p.resolve()
    except OSError as e:
        raise HTTPException(status_code=400, detail="无法解析路径") from e
    if not is_path_allowed(resolved):
        raise HTTPException(
            status_code=403,
            detail="路径不在允许索引的范围内，请在 config.yaml 的 api.index_allow_roots 中配置",
        )
    return resolved


def validate_readable_file(path: str | Path) -> Path:
    p = Path(path).expanduser()
    if not p.is_file():
        raise HTTPException(status_code=400, detail=f"文件不存在: {path}")
    resolved = p.resolve()
    if not is_path_allowed(resolved):
        raise HTTPException(status_code=403, detail="文件路径不在允许范围内")
    return resolved


def redact_path(path: str | None) -> str:
    if not path:
        return ""
    settings = get_config()
    if settings.api_expose_full_paths:
        return path
    p = Path(path)
    try:
        rel = p.resolve().relative_to(Path.home().resolve())
        return f"~/{rel.as_posix()}"
    except ValueError:
        name = p.name
        return f"…/{name}" if name else "…"


def redact_file_record(record: dict) -> dict:
    out = dict(record)
    if "path" in out:
        out["path"] = redact_path(out.get("path"))
    return out


def is_public_path(path: str) -> bool:
    if path in ("/", "/docs", "/redoc", "/openapi.json"):
        return True
    return any(
        path == prefix or path.startswith(prefix + "/")
        for prefix in PUBLIC_PATH_PREFIXES
        if prefix != "/"
    )


def verify_api_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    if is_public_path(request.url.path):
        return
    settings = get_config()
    token = settings.api_token
    if not token:
        return
    if not settings.api_require_token:
        return
    if credentials is None or not secrets.compare_digest(credentials.credentials, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或缺失 API Token",
            headers={"WWW-Authenticate": "Bearer"},
        )


RequireAuth = Annotated[None, Depends(verify_api_token)]
