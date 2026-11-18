# -*- coding: utf-8 -*-
"""回测过拟合证据：DSR 与 PBO / CSCV（v3.7.0 E2）。

设计依据：``docs/private/DESIGN_STAT_EVIDENCE_CHAIN.md`` §5 / §6；
实施依据：``docs/EXECUTION_V3.7.0_STAT_EVIDENCE_CHAIN.md`` §2.2。

本模块不被 ``backtest/__init__.py`` 导入；只依赖 numpy / scipy。
"""
import itertools
import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from scipy import stats

EULER_GAMMA = 0.5772156649


# ============================================================
# 内部辅助
# ============================================================

def _as_1d_finite(values: Any, name: str = "returns") -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise ValueError("%s 必须是一维序列" % name)
    if arr.size < 1:
        raise ValueError("%s 不能为空" % name)
    if not np.all(np.isfinite(arr)):
        raise ValueError("%s 含 NaN 或 Inf" % name)
    return arr


def _require_positive_std(arr: np.ndarray, name: str = "returns") -> float:
    if arr.size < 3:
        raise ValueError("%s 长度必须 >= 3" % name)
    std = float(arr.std(ddof=1))
    if float(np.ptp(arr)) == 0.0:
        # 均值舍入可能使常数序列的 std ≈ 1e-19 > 0，需显式拦截（v3.7.0 复审 H1）
        raise ValueError("%s 为常数序列，无法计算 Sharpe" % name)
    if not math.isfinite(std) or std <= 0.0:
        raise ValueError("%s 方差为 0，无法计算 Sharpe" % name)
    return std


def _dsr_from_stats(
    sr: float,
    sr_variance: float,
    n_trials: int,
    t: int,
    skew: float,
    kurtosis: float,
    periods_per_year: int = 12,
    variance_source: str = "sr_variance",
) -> Dict[str, Any]:
    """由已算好的统计量计算 DSR（含分母非正分支）。"""
    gamma = EULER_GAMMA
    sr0 = math.sqrt(sr_variance) * (
        (1.0 - gamma) * stats.norm.ppf(1.0 - 1.0 / n_trials)
        + gamma * stats.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    )
    denominator_sq = (
        1.0 - skew * sr + ((kurtosis - 1.0) / 4.0) * sr ** 2)
    if not math.isfinite(denominator_sq) or denominator_sq <= 0.0:
        dsr = float("nan")
        reason = "denominator_non_positive"
    else:
        denominator = math.sqrt(denominator_sq)
        dsr = float(stats.norm.cdf(
            (sr - sr0) * math.sqrt(t - 1) / denominator))
        reason = "ok"
    return {
        "dsr": dsr,
        "sr_per_period": sr,
        "sr_annualized": sr * math.sqrt(periods_per_year),
        "sr0": sr0,
        "T": t,
        "n_trials": n_trials,
        "skew": skew,
        "kurtosis": kurtosis,
        "sr_variance": sr_variance,
        "variance_source": variance_source,
        "reason": reason,
    }


# ============================================================
# Sharpe（唯一公共实现）
# ============================================================

def sharpe_ratio(
    returns: Any,
    *,
    periods_per_year: int = 12,
) -> Dict[str, Any]:
    """逐期 Sharpe 与年化 Sharpe（``ddof=1``）。"""
    arr = _as_1d_finite(returns)
    std = _require_positive_std(arr)
    sr = float(arr.mean() / std)
    return {
        "sharpe": sr * math.sqrt(periods_per_year),
        "sharpe_per_period": sr,
        "mean": float(arr.mean()),
        "std": std,
        "n_periods": int(arr.size),
        "periods_per_year": periods_per_year,
    }


# ============================================================
# DSR
# ============================================================

def deflated_sharpe_ratio(
    returns: Any,
    n_trials: int,
    *,
    sr_variance: Optional[float] = None,
    trial_sharpes: Optional[Sequence[float]] = None,
    periods_per_year: int = 12,
) -> Dict[str, Any]:
    """Deflated Sharpe Ratio（Bailey & López de Prado）。"""
    arr = _as_1d_finite(returns)
    _require_positive_std(arr)
    if int(n_trials) != n_trials or int(n_trials) < 2:
        raise ValueError("n_trials 必须是 >= 2 的整数")
    n_trials = int(n_trials)

    if sr_variance is not None and trial_sharpes is not None:
        raise ValueError("sr_variance 与 trial_sharpes 只能二选一")

    if trial_sharpes is not None:
        trials = _as_1d_finite(trial_sharpes, "trial_sharpes")
        if trials.size != n_trials:
            raise ValueError(
                "trial_sharpes 长度 %d 与 n_trials %d 不一致"
                % (trials.size, n_trials))
        variance = float(np.var(trials, ddof=1))
        source = "trial_sharpes"
    elif sr_variance is not None:
        variance = float(sr_variance)
        source = "sr_variance"
    else:
        variance = 1.0 / (arr.size - 1)
        source = "null"

    if not math.isfinite(variance) or variance <= 0.0:
        raise ValueError("Sharpe 方差必须为正且有限")

    t = int(arr.size)
    sr = float(arr.mean() / arr.std(ddof=1))
    skew = float(stats.skew(arr, bias=False))
    kurt = float(stats.kurtosis(arr, fisher=False, bias=False))
    return _dsr_from_stats(
        sr=sr, sr_variance=variance, n_trials=n_trials, t=t,
        skew=skew, kurtosis=kurt,
        periods_per_year=periods_per_year,
        variance_source=source,
    )


# ============================================================
# PBO / CSCV
# ============================================================

def trim_to_divisible(
    n_samples: int,
    n_blocks: int,
    keep: str = "recent",
) -> slice:
    """返回对齐 ``n_blocks`` 整数的裁剪切片。

    ``keep="recent"`` 丢弃最早 ``n_samples % n_blocks`` 期；
    ``keep="earliest"`` 丢弃最近 ``n_samples % n_blocks`` 期。
    """
    if n_samples < 0:
        raise ValueError("n_samples 必须 >= 0")
    if int(n_blocks) != n_blocks or n_blocks < 2 or n_blocks % 2 != 0:
        raise ValueError("n_blocks 必须是 >= 2 的偶数")
    if keep not in ("recent", "earliest"):
        raise ValueError("keep 必须是 'recent' 或 'earliest'")
    remainder = n_samples % n_blocks
    if keep == "recent":
        return slice(remainder, n_samples)
    return slice(0, n_samples - remainder)


def _block_metric(data: np.ndarray, metric: str) -> np.ndarray:
    if metric == "mean":
        return data.mean(axis=0)
    return data.mean(axis=0) / data.std(axis=0, ddof=1)


def probability_of_backtest_overfitting(
    returns_matrix: Any,
    n_blocks: int,
    *,
    metric: str = "sharpe",
    return_logits: bool = False,
) -> Dict[str, Any]:
    """CSCV 组合对称交叉验证下的 PBO。"""
    data = np.asarray(returns_matrix, dtype=float)
    if data.ndim != 2:
        raise ValueError("returns_matrix 必须是二维 (T, N)")
    t, n = data.shape
    if n < 2:
        raise ValueError("策略数 N 必须 >= 2")
    if int(n_blocks) != n_blocks or n_blocks < 2 or n_blocks % 2 != 0:
        raise ValueError("n_blocks 必须是 >= 2 的偶数")
    n_blocks = int(n_blocks)
    if t % n_blocks != 0:
        slice_ = trim_to_divisible(t, n_blocks)
        raise ValueError(
            "T=%d 不能被 n_blocks=%d 整除；可先裁剪 %r"
            % (t, n_blocks, slice_))
    if metric not in ("sharpe", "mean"):
        raise ValueError("metric 必须是 'sharpe' 或 'mean'")
    if not np.all(np.isfinite(data)):
        raise ValueError("returns_matrix 含 NaN 或 Inf")

    block_len = t // n_blocks
    if block_len < 2:
        raise ValueError("每个 block 至少需要 2 期")
    blocks = [np.arange(i * block_len, (i + 1) * block_len)
              for i in range(n_blocks)]

    # 每个 block、每个策略必须有正方差
    for block in blocks:
        chunk = data[block]
        stds = chunk.std(axis=0, ddof=1)
        if (np.any(~np.isfinite(stds)) or np.any(stds <= 0.0)
                or np.any(np.ptp(chunk, axis=0) == 0.0)):
            raise ValueError("存在零方差 block/策略，无法计算相对秩")

    logits: List[float] = []
    for combo in itertools.combinations(range(n_blocks), n_blocks // 2):
        is_idx = np.concatenate([blocks[i] for i in combo])
        oos_idx = np.setdiff1d(np.arange(t), is_idx)
        is_score = _block_metric(data[is_idx], metric)
        star = int(np.argmax(is_score))
        oos_score = _block_metric(data[oos_idx], metric)
        selected = float(oos_score[star])
        rank = (1.0
                + float(np.sum(oos_score < selected))
                + 0.5 * (float(np.sum(oos_score == selected)) - 1.0))
        omega = rank / (n + 1.0)
        logits.append(math.log(omega / (1.0 - omega)))

    logit_arr = np.asarray(logits, dtype=float)
    result = {
        "pbo": float(np.mean(logit_arr <= 0.0)),
        "n_splits": int(logit_arr.size),
        "n_blocks": n_blocks,
        "n_strategies": int(n),
        "n_periods": int(t),
        "metric": metric,
        "tie_policy": "average_rank",
    }
    if return_logits:
        result["logits"] = [float(x) for x in logit_arr]
    return result
