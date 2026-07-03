"""虚拟文件实体（VFE）核心：持久身份、交互记忆、生命周期辅助。"""

from src.vfe.identity import (
    compute_vfe_id,
    content_hash_prefix,
    get_inode_key,
    resolve_vfe_identity,
)
from src.vfe.memory import MemoryRecord, VFEMemoryStack, update_memory

__all__ = [
    "MemoryRecord",
    "VFEMemoryStack",
    "compute_vfe_id",
    "content_hash_prefix",
    "get_inode_key",
    "resolve_vfe_identity",
    "update_memory",
]
