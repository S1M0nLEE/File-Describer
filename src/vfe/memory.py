"""VFE 交互记忆栈（规格 2.2.1，容量 K=50）。"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from src.config import settings


@dataclass
class MemoryRecord:
    action: str  # accessed | modified | retrieved | co_edited
    timestamp: float
    related_vfe_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryRecord:
        return cls(
            action=str(data.get("action", "accessed")),
            timestamp=float(data.get("timestamp", time.time())),
            related_vfe_id=data.get("related_vfe_id"),
        )


class VFEMemoryStack:
    def __init__(self, capacity: int | None = None) -> None:
        self.capacity = capacity or int(getattr(settings, "vfe_memory_capacity", 50))

    def push(self, records: list[dict] | list[MemoryRecord], action: str, *, related_id: str | None = None) -> list[dict]:
        if records and isinstance(records[0], MemoryRecord):
            stack = [r.to_dict() for r in records]  # type: ignore[arg-type]
        else:
            stack = list(records or [])
        stack.append(
            MemoryRecord(action=action, timestamp=time.time(), related_vfe_id=related_id).to_dict()
        )
        if len(stack) > self.capacity:
            stack = stack[-self.capacity :]
        return stack


def update_memory(
    node: dict[str, Any],
    action: str,
    *,
    related_id: str | None = None,
) -> dict[str, Any]:
    stack = VFEMemoryStack()
    mem = stack.push(node.get("memory_stack") or [], action, related_id=related_id)
    return {"memory_stack": mem}


def calc_co_weight(vfe_i: dict, vfe_j: dict, *, delta_t: float | None = None) -> float:
    """规格 2.3 / 式 3-1：时间窗口内共现强度。"""
    window = delta_t if delta_t is not None else float(getattr(settings, "vfe_near_time_window_seconds", 300))
    mem_i = [MemoryRecord.from_dict(x) for x in (vfe_i.get("memory_stack") or [])]
    mem_j = [MemoryRecord.from_dict(x) for x in (vfe_j.get("memory_stack") or [])]
    if not mem_i or not mem_j:
        return 0.0
    count = 0
    for rec_i in mem_i:
        for rec_j in mem_j:
            if abs(rec_i.timestamp - rec_j.timestamp) < window:
                count += 1
                break
    denom = max(len(mem_i), len(mem_j))
    return count / denom if denom else 0.0
