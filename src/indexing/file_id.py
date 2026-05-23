from __future__ import annotations

import os
import sys
from pathlib import Path


def get_path_based_id(path: str | Path) -> str:
    """以规范化路径为身份（移动/重命名后视为新文件，用于对比实验）。"""
    return "path:" + str(Path(path).resolve()).lower()


def get_file_id(path: str | Path, *, mode: str = "volume") -> str:
    """
    文件数字身份。
    mode:
      volume — 卷级 File ID / inode（默认，移动后身份不变）
      path   — 路径字符串（移动后身份变化）
    """
    if mode == "path":
        return get_path_based_id(path)
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(path)

    if sys.platform == "win32":
        return _windows_file_id(p)
    st = os.stat(p)
    return f"{st.st_dev}:{st.st_ino}"


def _windows_file_id(path: Path) -> str:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    GENERIC_READ = 0x80000000
    FILE_SHARE_READ = 0x00000001
    OPEN_EXISTING = 3
    FILE_ATTRIBUTE_NORMAL = 0x80

    handle = kernel32.CreateFileW(
        str(path),
        GENERIC_READ,
        FILE_SHARE_READ,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )
    if handle == -1:
        st = path.stat()
        return f"fallback:{path.drive}:{st.st_ino}:{st.st_mtime_ns}"

    class FILE_ID_INFO(ctypes.Structure):
        _fields_ = [
            ("VolumeSerialNumber", wintypes.DWORD),
            ("FileId", ctypes.c_byte * 16),
        ]

    info = FILE_ID_INFO()
    ok = kernel32.GetFileInformationByHandleEx(
        handle, 18, ctypes.byref(info), ctypes.sizeof(info)
    )
    kernel32.CloseHandle(handle)
    if not ok:
        st = path.stat()
        return f"fallback:{path.drive}:{st.st_ino}:{st.st_mtime_ns}"

    fid = bytes(info.FileId).hex()
    return f"{info.VolumeSerialNumber}:{fid}"
