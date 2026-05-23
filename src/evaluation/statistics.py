from __future__ import annotations

import math
from typing import Any


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float], mean: float | None = None) -> float:
    if len(xs) < 2:
        return 0.0
    m = mean if mean is not None else _mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def paired_t_test(diffs: list[float]) -> dict[str, Any]:
    """
    配对 t 检验（双尾），H0: 差值均值为 0。
    diffs[i] = method_a[i] - method_b[i]
    """
    n = len(diffs)
    if n < 2:
        return {"n": n, "mean_diff": 0.0, "t_statistic": None, "p_value": None, "significant_0_05": False}

    mean_d = _mean(diffs)
    sd_d = _std(diffs, mean_d)
    if sd_d == 0:
        return {
            "n": n,
            "mean_diff": mean_d,
            "t_statistic": 0.0 if mean_d == 0 else float("inf"),
            "p_value": 1.0 if mean_d == 0 else 0.0,
            "significant_0_05": mean_d != 0,
        }

    t = mean_d / (sd_d / math.sqrt(n))
    df = n - 1
    p = _t_cdf_two_tail(abs(t), df)
    return {
        "n": n,
        "mean_diff": mean_d,
        "t_statistic": t,
        "p_value": p,
        "significant_0_05": p < 0.05,
    }


def _t_cdf_two_tail(t_abs: float, df: int) -> float:
    """Student t 双尾 p 值近似（无 scipy 依赖）。"""
    x = df / (df + t_abs * t_abs)
    return _betainc(df / 2, 0.5, x)


def _betainc(a: float, b: float, x: float) -> float:
    """不完全 Beta 函数近似（连分式）。"""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    ln_beta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log(1 - x) - ln_beta) / a
    cf = _betacf(a, b, x)
    return min(1.0, max(0.0, front * cf))


def _betacf(a: float, b: float, x: float) -> float:
    qab = a + b
    qap = a + 1
    qam = a - 1
    c = 1.0
    d = 1 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1 / d
    h = d
    for m in range(1, 201):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 3e-7:
            break
    return h


def compare_baselines_per_query(
    per_query: dict[str, list[dict[str, Any]]],
    method_a: str,
    method_b: str,
    metric: str = "ap",
) -> dict[str, Any]:
    """逐查询对比两方法（默认 AP），返回配对 t 检验结果。"""
    a_map = {r["query"]: r[metric] for r in per_query.get(method_a, [])}
    b_map = {r["query"]: r[metric] for r in per_query.get(method_b, [])}
    shared = sorted(set(a_map) & set(b_map))
    diffs = [a_map[q] - b_map[q] for q in shared]
    stats = paired_t_test(diffs)
    stats.update(
        {
            "method_a": method_a,
            "method_b": method_b,
            "metric": metric,
            "queries": len(shared),
            "mean_a": _mean([a_map[q] for q in shared]) if shared else 0.0,
            "mean_b": _mean([b_map[q] for q in shared]) if shared else 0.0,
        }
    )
    return stats


def filekg_vs_best_baseline(per_query: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """FileKG-Full 相对其余基线中 AP 最高者的配对检验。"""
    baselines = [b for b in per_query if b != "FileKG-Full"]
    if not baselines or "FileKG-Full" not in per_query:
        return {}

    fk = {r["query"]: r["ap"] for r in per_query["FileKG-Full"]}
    best_name = None
    best_mean = -1.0
    for b in baselines:
        m = _mean([r["ap"] for r in per_query[b]])
        if m > best_mean:
            best_mean = m
            best_name = b
    if not best_name:
        return {}

    result = compare_baselines_per_query(per_query, "FileKG-Full", best_name, metric="ap")
    result["best_baseline"] = best_name
    return result
