from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv"}


def is_video(ext: str) -> bool:
    return ext.lower() in _VIDEO_EXT


def sample_frame_paths(path: Path, max_frames: int) -> list[Path]:
    """抽取视频关键帧到临时目录，返回图片路径列表。"""
    frames = _sample_cv2(path, max_frames)
    if frames:
        return frames
    return _sample_ffmpeg(path, max_frames)


def _sample_cv2(path: Path, max_frames: int) -> list[Path]:
    try:
        import cv2
    except ImportError:
        return []
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        cap.release()
        return []
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total <= 0:
        cap.release()
        return []
    step = max(1, total // max(1, max_frames))
    out_dir = Path(tempfile.mkdtemp(prefix="filekg_frames_"))
    paths: list[Path] = []
    idx = 0
    saved = 0
    while saved < max_frames and idx < total:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if ok and frame is not None:
            fp = out_dir / f"frame_{saved:04d}.jpg"
            cv2.imwrite(str(fp), frame)
            paths.append(fp)
            saved += 1
        idx += step
    cap.release()
    return paths


def _sample_ffmpeg(path: Path, max_frames: int) -> list[Path]:
    out_dir = Path(tempfile.mkdtemp(prefix="filekg_ff_"))
    pattern = str(out_dir / "frame_%04d.jpg")
    fps = max(0.05, 1.0 / max(1, max_frames))
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(path),
        "-vf",
        f"fps={fps}",
        "-frames:v",
        str(max_frames),
        pattern,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.debug("ffmpeg 抽帧失败 %s: %s", path.name, e)
        return []
    return sorted(out_dir.glob("frame_*.jpg"))[:max_frames]
