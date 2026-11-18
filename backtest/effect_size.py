# -*- coding: utf-8 -*-
"""效应量与置信区间：Newey-West、stationary bootstrap、Sharpe CI（v3.7.0 E3）。

设计依据：``docs/private/DESIGN_STAT_EVIDENCE_CHAIN.md`` §8；
实施依据：``docs/EXECUTION_V3.7.0_STAT_EVIDENCE_CHAIN.md`` §2.3。

模块边界：不 import ``backtest.overfitting``；Sharpe 逐期口径在本模块用
私有 ``_sharpe_per_period`` 按同一公式（``ddof=1``）实现。
"""
import math
from typing import Any, Dict, Optional

import numpy as np
from scipy import stats


# ============================================================
# 内部辅助
# ============================================================

def _as_1d_finite(values: Any, name: str = "values") -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise ValueError("%s 必须是一维序列" % name)
    if arr.size < 1:
        raise ValueError("%s 不能为空" % name)
    if not np.all(np.isfinite(arr)):
        raise ValueError("%s 含 NaN 或 Inf" % name)
    return arr


def _validate_alpha(alpha: float) -> float:
    alpha = float(alpha)
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha 必须在 (0, 1) 内")
    return alpha


def _sharpe_per_period(returns: np.ndarray) -> float:
    """与 ``overfitting.sharpe_ratio`` 一致的逐期 Sharpe（ddof=1）。"""
    std = float(returns.std(ddof=1))
    if float(np.ptp(returns)) == 0.0:
        # 常数序列因均值舍入可能 std ≈ 1e-19 > 0，需显式拦截（v3.7.0 复审 H1）
        raise ValueError("returns 为常数序列，无法计算 Sharpe")
    if not math.isfinite(std) or std <= 0.0:
        raise ValueError("returns 方差为 0，无法计算 Sharpe")
    return float(returns.mean() / std)


def _default_block_size(n: int) -> int:
    return max(1, int(math.ceil(math.sqrt(n))))


# ============================================================
# Newey-West
# ============================================================

def _resolve_lag(n: int, max_lag: Optional[int]) -> int:
    if max_lag is None:
        lag = max(1, int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0))))
    else:
        if int(max_lag) != max_lag or max_lag < 0:
            raise ValueError("max_lag 必须是 >= 0 的整数")
        lag = int(max_lag)
    if lag >= n:
        raise ValueError("max_lag 必须小于样本长度")
    return lag


def newey_west_se(
    values: Any,
    max_lag: Optional[int] = None,
) -> Dict[str, Any]:
    """Newey-West (Bartlett) HAC 标准误，未做小样本修正。"""
    arr = _as_1d_finite(values)
    n = int(arr.size)
    if n < 3:
        raise ValueError("values 长度必须 >= 3")
    if float(np.ptp(arr)) == 0.0:
        raise ValueError("values 为常数序列，长期方差为 0")
    lag = _resolve_lag(n, max_lag)
    demeaned = arr - arr.mean()
    omega = float(np.dot(demeaned, demeaned) / n)
    for j in range(1, lag + 1):
        weight = 1.0 - j / (lag + 1.0)
        gamma_j = float(np.dot(demeaned[j:], demeaned[:-j]) / n)
        omega += 2.0 * weight * gamma_j
    if not math.isfinite(omega) or omega <= 0.0:
        raise ValueError("Newey-West 长期方差非正，无法计算标准误")
    return {
        "mean": float(arr.mean()),
        "se": math.sqrt(omega / n),
        "lag": lag,
        "n_periods": n,
        "method": "newey_west",
    }


def mean_ci(
    values: Any,
    *,
    alpha: float = 0.05,
    max_lag: Optional[int] = None,
) -> Dict[str, Any]:
    """均值的 Newey-West 置信区间。"""
    alpha = _validate_alpha(alpha)
    nw = newey_west_se(values, max_lag=max_lag)
    n = nw["n_periods"]
    critical = float(stats.t.ppf(1.0 - alpha / 2.0, df=n - 1))
    half = critical * nw["se"]
    return {
        "mean": nw["mean"],
        "se": nw["se"],
        "ci_low": nw["mean"] - half,
        "ci_high": nw["mean"] + half,
        "critical_value": critical,
        "alpha": alpha,
        "lag": nw["lag"],
        "n_periods": n,
        "method": "newey_west",
    }


# ============================================================
# Stationary bootstrap
# ============================================================

def stationary_bootstrap_indices(
    n: int,
    n_bootstrap: int = 1000,
    block_size: Optional[int] = None,
    seed: int = 0,
) -> np.ndarray:
    """Politis-Romano stationary bootstrap 索引矩阵 (B, n)。"""
    n = int(n)
    if n < 1:
        raise ValueError("n 必须 >= 1")
    if int(n_bootstrap) != n_bootstrap or n_bootstrap < 100:
        raise ValueError("n_bootstrap 必须是 >= 100 的整数")
    if block_size is None:
        block = _default_block_size(n)
    else:
        if int(block_size) != block_size or block_size < 1:
            raise ValueError("block_size 必须是 >= 1 的整数")
        block = int(block_size)

    rng = np.random.default_rng(seed)
    idx = np.empty((int(n_bootstrap), n), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, size=int(n_bootstrap))
    if n > 1:
        if block == 1:
            idx[:, 1:] = rng.integers(0, n, size=(int(n_bootstrap), n - 1))
        else:
            probability = 1.0 / block
            for t in range(1, n):
                fresh = rng.random(int(n_bootstrap)) < probability
                draws = rng.integers(0, n, size=int(n_bootstrap))
                idx[:, t] = np.where(
                    fresh, draws, (idx[:, t - 1] + 1) % n)
    return idx


def sharpe_ci(
    returns: Any,
    *,
    alpha: float = 0.05,
    n_bootstrap: int = 1000,
    block_size: Optional[int] = None,
    seed: int = 0,
    periods_per_year: int = 12,
) -> Dict[str, Any]:
    """年化 Sharpe 的 stationary bootstrap 百分位置信区间。"""
    alpha = _validate_alpha(alpha)
    arr = _as_1d_finite(returns, "returns")
    n = int(arr.size)
    if n < 3:
        raise ValueError("returns 长度必须 >= 3")
    sr_per_period = _sharpe_per_period(arr)
    idx = stationary_bootstrap_indices(
        n, n_bootstrap=n_bootstrap, block_size=block_size, seed=seed)
    samples = arr[idx]
    means = samples.mean(axis=1)
    stds = samples.std(axis=1, ddof=1)
    if np.any(~np.isfinite(stds)) or np.any(stds <= 0.0):
        raise ValueError("bootstrap 样本出现零方差，无法计算 Sharpe")
    sharpes = means / stds * math.sqrt(periods_per_year)
    ci_low, ci_high = np.quantile(sharpes, [alpha / 2.0, 1.0 - alpha / 2.0])
    effective_block = (block_size if block_size is not None
                       else _default_block_size(n))
    return {
        "sharpe": sr_per_period * math.sqrt(periods_per_year),
        "sharpe_per_period": sr_per_period,
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "se": float(sharpes.std(ddof=1)),
        "alpha": alpha,
        "n_bootstrap": int(n_bootstrap),
        "block_size": int(effective_block),
        "seed": int(seed),
        "n_periods": n,
        "method": "stationary_bootstrap",
    }


# ============================================================
# 统一门面
# ============================================================

_MEAN_METRICS = ("lambda_mean", "ic_mean")


def effect_summary(
    metric: str,
    values: Any,
    *,
    alpha: float = 0.05,
    max_lag: Optional[int] = None,
    n_bootstrap: int = 1000,
    block_size: Optional[int] = None,
    seed: int = 0,
    periods_per_year: int = 12,
) -> Dict[str, Any]:
    """按 metric 分派效应量与置信区间。"""
    if metric == "sharpe":
        out = sharpe_ci(
            values, alpha=alpha, n_bootstrap=n_bootstrap,
            block_size=block_size, seed=seed,
            periods_per_year=periods_per_year)
        return {
            "metric": metric,
            "effect_size": out["sharpe"],
            "sharpe_per_period": out["sharpe_per_period"],
            "ci_low": out["ci_low"],
            "ci_high": out["ci_high"],
            "se": out["se"],
            "alpha": out["alpha"],
            "n_bootstrap": out["n_bootstrap"],
            "block_size": out["block_size"],
            "seed": out["seed"],
            "n_periods": out["n_periods"],
            "method": out["method"],
        }
    if metric in _MEAN_METRICS:
        out = mean_ci(values, alpha=alpha, max_lag=max_lag)
        return {
            "metric": metric,
            "effect_size": out["mean"],
            "ci_low": out["ci_low"],
            "ci_high": out["ci_high"],
            "se": out["se"],
            "critical_value": out["critical_value"],
            "alpha": out["alpha"],
            "lag": out["lag"],
            "n_periods": out["n_periods"],
            "method": out["method"],
        }
    raise ValueError("不支持的 metric: %r" % (metric,))
