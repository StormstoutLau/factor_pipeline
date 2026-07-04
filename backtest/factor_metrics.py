# -*- coding: utf-8 -*-
"""
因子级指标计算模块 — 单一真相源 (Single Source of Truth)

所有函数为纯计算:
  - 输入: numpy arrays
  - 输出: float 或 np.ndarray
  - 无副作用，不依赖任何外部模块

这是整个系统中"指标计算"的唯一权威来源。
FactorHealthMonitor、optimizer、drift reporter 均通过此模块获取指标。
"""

import numpy as np
from scipy import stats as scipy_stats
from typing import Optional, Literal


# =============================================================================
# 数值稳定常数
# =============================================================================
MIN_VALID_PAIRS = 3       # 最小有效配对数
EPS = 1e-12                # 数值稳定 epsilon


# =============================================================================
# IC 计算
# =============================================================================

def _get_valid_mask(
    factor: np.ndarray,
    fwd_return: np.ndarray,
) -> np.ndarray:
    """获取两个数组中同时有效的索引。"""
    return ~(np.isnan(factor) | np.isnan(fwd_return))


def compute_rank_ic(
    factor: np.ndarray,
    fwd_return: np.ndarray,
) -> float:
    """
    计算 Rank IC (Spearman Rank Correlation)。

    手工计算: scipy.stats.spearmanr(factor, return)[0]

    Parameters
    ----------
    factor : np.ndarray, shape (n_stocks,)
        因子值
    fwd_return : np.ndarray, shape (n_stocks,)
        前向收益率

    Returns
    -------
    float
        Rank IC 值，不足 3 个有效配对时返回 NaN
    """
    valid = _get_valid_mask(factor, fwd_return)
    if valid.sum() < MIN_VALID_PAIRS:
        return np.nan

    f = factor[valid]
    r = fwd_return[valid]

    ic, _ = scipy_stats.spearmanr(f, r)
    return float(ic)


def compute_pearson_ic(
    factor: np.ndarray,
    fwd_return: np.ndarray,
) -> float:
    """
    计算 Pearson IC (Pearson Correlation)。

    手工计算: np.corrcoef(factor, return)[0, 1]

    Parameters
    ----------
    factor : np.ndarray, shape (n_stocks,)
        因子值
    fwd_return : np.ndarray, shape (n_stocks,)
        前向收益率

    Returns
    -------
    float
        Pearson IC 值，不足 3 个有效配对时返回 NaN
    """
    valid = _get_valid_mask(factor, fwd_return)
    if valid.sum() < MIN_VALID_PAIRS:
        return np.nan

    f = factor[valid]
    r = fwd_return[valid]

    corr_matrix = np.corrcoef(f, r)
    ic = corr_matrix[0, 1]
    if np.isnan(ic):
        return np.nan
    return float(ic)


# =============================================================================
# IC 序列
# =============================================================================

def compute_ic_series(
    factor: np.ndarray,
    returns: np.ndarray,
    method: Literal['rank', 'pearson'] = 'rank',
    weighting: Literal['equal', 'ewma'] = 'equal',
    halflife: Optional[int] = None,
) -> np.ndarray:
    """
    计算 IC 时间序列 (v2.6.0 P3-1' 新增 EWMA 加权选项).

    手工计算: 对每期 t，计算 factor[:, t] 与 return[:, t+1] 的 IC。

    Parameters
    ----------
    factor : np.ndarray, shape (n_stocks, n_periods)
        因子值矩阵
    returns : np.ndarray, shape (n_stocks, n_periods)
        收益率矩阵
    method : 'rank' | 'pearson'
        IC 计算方法
    weighting : 'equal' | 'ewma'  (v2.6.0 P3-1' 新增)
        'equal': 等权 (默认, 向后兼容, 返回完整 IC 序列)
        'ewma': 指数加权, 近期 IC 权重更高 (返回加权后的标量, shape (1,))
    halflife : int, optional
        EWMA 半衰期 (仅 weighting='ewma' 时生效)
        默认: max(1, len(ic_series) // 4) (自适应)

    Returns
    -------
    np.ndarray
        weighting='equal': shape (n_periods - 1,), IC 序列
        weighting='ewma': shape (1,), 加权 IC 标量 (有效 IC 不足时为 NaN)

    学术依据:
    - equal: 行业标准
    - ewma: Ferson & Siegel (2001) JF 56(3):967-982 (条件信息时变加权)
            Barroso & Santa-Clara (2015) JFE 115(3):464-482 (IC 高波动期衰减)
            RiskMetrics (1996) EWMA 框架
    """
    n_periods = factor.shape[1]
    ic_series = np.full(n_periods - 1, np.nan)

    if method == 'rank':
        ic_func = compute_rank_ic
    elif method == 'pearson':
        ic_func = compute_pearson_ic
    else:
        raise ValueError(f"未知 IC 方法: {method}，可选 'rank' / 'pearson'")

    for t in range(n_periods - 1):
        ic_series[t] = ic_func(factor[:, t], returns[:, t + 1])

    # v2.6.0 P3-1': EWMA 时间加权
    if weighting == 'ewma':
        n = len(ic_series)
        if halflife is None:
            halflife = max(1, n // 4)

        # EWMA 权重: w[t] = (1-alpha)^(n-1-t), 近期 (t 大) 权重大
        # alpha = 1 - exp(-ln2/halflife), 半衰期含义: w[t-halflife] = 0.5 * w[t]
        alpha = 1.0 - np.exp(-np.log(2.0) / max(halflife, 1))
        weights = (1.0 - alpha) ** np.arange(n)[::-1]
        weights /= weights.sum()

        # 加权求和 (忽略 NaN)
        valid = ~np.isnan(ic_series)
        if valid.sum() < MIN_VALID_PAIRS:
            return np.array([np.nan])
        weighted_ic = np.nansum(ic_series * weights)
        return np.array([weighted_ic])

    return ic_series


# =============================================================================
# ICIR
# =============================================================================

def compute_icir(ic_series: np.ndarray) -> float:
    """
    计算 IC Information Ratio。

    手工计算: ICIR = mean(IC) / std(IC, ddof=1)

    Parameters
    ----------
    ic_series : np.ndarray
        IC 序列

    Returns
    -------
    float
        ICIR 值，std≈0 或不足 3 个有效值时返回 NaN
    """
    clean = ic_series[~np.isnan(ic_series)]

    if len(clean) < MIN_VALID_PAIRS:
        return np.nan

    mean_ic = np.mean(clean)
    std_ic = np.std(clean, ddof=1)

    if std_ic < EPS:
        return np.nan

    return float(mean_ic / std_ic)


# =============================================================================
# IC Decay
# =============================================================================

def compute_ic_decay(
    factor: np.ndarray,
    returns: np.ndarray,
    max_lag: int = 12,
) -> np.ndarray:
    """
    计算 IC 衰减曲线。

    手工计算: decay[lag] = mean( IC(factor[:, t], return[:, t + lag + 1]) )
              对所有 t = 0..n_periods-lag-2

    Parameters
    ----------
    factor : np.ndarray, shape (n_stocks, n_periods)
        因子值矩阵
    returns : np.ndarray, shape (n_stocks, n_periods)
        收益率矩阵
    max_lag : int
        最大滞后阶数

    Returns
    -------
    np.ndarray, shape (actual_lags,)
        IC 衰减值，actual_lags = min(max_lag, n_periods - 1)
    """
    n_periods = factor.shape[1]
    actual_lags = min(max_lag, n_periods - 1)
    decay = np.full(actual_lags, np.nan)

    for lag in range(actual_lags):
        offset = lag + 1  # lag=0 → factor[:,t] → return[:, t+1]
        ic_values = []

        for t in range(n_periods - offset):
            ic = compute_rank_ic(factor[:, t], returns[:, t + offset])
            if not np.isnan(ic):
                ic_values.append(ic)

        if len(ic_values) >= MIN_VALID_PAIRS:
            decay[lag] = np.mean(ic_values)

    return decay


# =============================================================================
# 换手率
# =============================================================================

def compute_turnover(positions: np.ndarray) -> np.ndarray:
    """
    计算换手率序列。

    手工计算: turnover[t] = 0.5 * sum(|w[t] - w[t-1]|)

    Parameters
    ----------
    positions : np.ndarray, shape (n_dates, n_stocks)
        仓位矩阵，每行为一期权重

    Returns
    -------
    np.ndarray, shape (n_dates - 1,)
        换手率序列
    """
    if positions.shape[0] < 2:
        return np.array([])

    diffs = np.abs(np.diff(positions, axis=0))
    turnover = 0.5 * np.sum(diffs, axis=1)

    return turnover


# =============================================================================
# 多空收益
# =============================================================================

def compute_long_short_returns(
    factor: np.ndarray,
    returns: np.ndarray,
    top_n: int = 0,
) -> np.ndarray:
    """
    计算多空组合收益。

    手工计算: 每期将因子值排序，取 top_n 个做多，bottom_n 个做空。

    Parameters
    ----------
    factor : np.ndarray, shape (n_stocks, n_periods)
        因子值矩阵
    returns : np.ndarray, shape (n_stocks, n_periods)
        收益率矩阵
    top_n : int or float
        int: 每侧固定股票数量
        float (0~0.5): 每侧比例

    Returns
    -------
    np.ndarray, shape (n_periods - 1,)
        多空收益序列
    """
    n_stocks, n_periods = factor.shape
    ls_returns = np.full(n_periods - 1, np.nan)

    for t in range(n_periods - 1):
        f = factor[:, t]
        r = returns[:, t + 1]

        valid = _get_valid_mask(f, r)
        n_valid = valid.sum()
        if n_valid < MIN_VALID_PAIRS:
            continue

        f_valid = f[valid]
        r_valid = r[valid]

        # 确定选股数量
        if isinstance(top_n, float) and 0 < top_n <= 0.5:
            n_select = max(1, int(n_valid * top_n))
        elif isinstance(top_n, int) and top_n > 0:
            n_select = min(top_n, n_valid // 2)
        else:
            # 默认: 20% 分位
            n_select = max(1, int(n_valid * 0.2))

        if n_select < 1 or n_valid < n_select * 2:
            continue

        # 排序索引
        sorted_idx = np.argsort(f_valid)

        # 空头: bottom n_select
        short_idx = sorted_idx[:n_select]
        # 多头: top n_select
        long_idx = sorted_idx[-n_select:]

        short_ret = np.mean(r_valid[short_idx])
        long_ret = np.mean(r_valid[long_idx])

        ls_returns[t] = long_ret - short_ret

    return ls_returns


# =============================================================================
# Spread
# =============================================================================

def compute_spread(ls_returns: np.ndarray) -> float:
    """
    计算多空收益 spread。

    手工计算: spread = mean(ls_ret) / std(ls_ret, ddof=1)

    Parameters
    ----------
    ls_returns : np.ndarray
        多空收益序列

    Returns
    -------
    float
        Spread 值，不足 3 个有效值时返回 NaN
    """
    clean = ls_returns[~np.isnan(ls_returns)]

    if len(clean) < MIN_VALID_PAIRS:
        return np.nan

    mean_ls = np.mean(clean)
    std_ls = np.std(clean, ddof=1)

    if std_ls < EPS:
        return np.nan

    return float(mean_ls / std_ls)


# =============================================================================
# Hit Rate (IC 胜率)
# =============================================================================

def compute_hit_rate(ic_series: np.ndarray) -> float:
    """
    计算 IC 胜率。

    手工计算: hit_rate = count(IC > 0) / count(valid IC)

    Parameters
    ----------
    ic_series : np.ndarray
        IC 序列

    Returns
    -------
    float
        Hit rate [0, 1]，不足 3 个有效值时返回 NaN
    """
    clean = ic_series[~np.isnan(ic_series)]

    if len(clean) < MIN_VALID_PAIRS:
        return np.nan

    return float(np.sum(clean > 0) / len(clean))