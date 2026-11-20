# -*- coding: utf-8 -*-
"""I4-I5：多空有效对 / RankIC 界。"""
import numpy as np

from backtest.factor_metrics import (
    compute_ic_series,
    compute_long_short_returns,
)

from .registry import Invariant, register


def _fwd_padded(panel):
    """factor[:, t] ↔ returns[:, t+1] 的填充规则（与 engine._evaluate_factor 一致）。"""
    T, N = panel.close.shape
    padded = np.full((T, N), np.nan)
    for t in range(T - 1):
        prev, curr = panel.close[t], panel.close[t + 1]
        valid = (prev > 1e-10) & np.isfinite(prev) & np.isfinite(curr)
        padded[t + 1, valid] = (curr[valid] - prev[valid]) / prev[valid]
    return padded


def check_i4(panel):
    factor = panel.factor.T
    returns = _fwd_padded(panel).T
    base = compute_long_short_returns(factor, returns, top_n=0.2)
    # 对齐：factor[:, t] 配对 returns[:, t+1]；只在配对位置注入
    mask = np.zeros_like(returns, dtype=bool)
    mask[:, 1:] = np.isnan(factor)[:, :-1]
    r2 = returns.copy()
    r2[mask] = 100.0
    alt = compute_long_short_returns(factor, r2, top_n=0.2)
    same = (base == alt) | (np.isnan(base) & np.isnan(alt))
    bad = np.flatnonzero(~same)
    if bad.size:
        return False, "first_diff_t=%d" % int(bad[0])
    return True, "NaN 股票注入收益不改 LS（%d 期）" % base.size


def check_i5(panel):
    factor = panel.factor.T
    returns = _fwd_padded(panel).T
    ic = compute_ic_series(factor, returns, method="rank")
    finite = ic[np.isfinite(ic)]
    if finite.size == 0:
        return False, "RankIC 全为 NaN"
    lo, hi = float(finite.min()), float(finite.max())
    if lo < -1.0 - 1e-9 or hi > 1.0 + 1e-9:
        return False, "RankIC 越界: [%.6f, %.6f]" % (lo, hi)
    return True, "RankIC ∈ [%.4f, %.4f]（%d 期）" % (lo, hi, finite.size)


register(Invariant("I4_long_short_valid_pairs", "backtest.factor_metrics",
                   "invariant", "clean", check_i4))
register(Invariant("I5_rank_ic_bound", "backtest.factor_metrics", "bound",
                   "clean", check_i5))
