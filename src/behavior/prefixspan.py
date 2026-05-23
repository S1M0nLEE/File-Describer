from __future__ import annotations

from collections import defaultdict


def mine_frequent_adjacent_pairs(
    sequences: list[list[str]],
    min_support: int = 2,
) -> dict[tuple[str, str], int]:
    """PrefixSpan 简化：挖掘频繁相邻文件对（方案 4.2.7）。"""
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for seq in sequences:
        seen_pairs: set[tuple[str, str]] = set()
        for i in range(len(seq) - 1):
            pair = (seq[i], seq[i + 1])
            if pair not in seen_pairs:
                counts[pair] += 1
                seen_pairs.add(pair)
    return {p: c for p, c in counts.items() if c >= min_support}


def mine_frequent_subsequences(
    sequences: list[list[str]],
    min_support: int = 2,
    max_len: int = 4,
) -> list[tuple[list[str], int]]:
    """长度 2~max_len 的频繁子序列（相邻窗口内）。"""
    patterns: dict[tuple[str, ...], int] = defaultdict(int)
    for seq in sequences:
        n = len(seq)
        for length in range(2, min(max_len, n) + 1):
            local: set[tuple[str, ...]] = set()
            for i in range(n - length + 1):
                sub = tuple(seq[i : i + length])
                if sub not in local:
                    patterns[sub] += 1
                    local.add(sub)
    return [(list(k), v) for k, v in patterns.items() if v >= min_support]
