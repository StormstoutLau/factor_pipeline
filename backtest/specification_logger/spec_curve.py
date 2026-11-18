# -*- coding: utf-8 -*-
"""SpecificationCurve — 规格曲线分析 (V3.1.0 E2, §3).

Specification curve (Simonsohn et al. 2020) 将所有合理规格的结果汇总,
展示效应在不同规格下的稳健性. 本类提供独立的曲线计算接口,
与 SpecificationLogger.get_specification_curve 互补.

学术依据:
- Simonsohn, U., Simmons, J. P., & Nelson, L. D. (2020). "Specification
  Curve Analysis." Nature Human Behaviour 4:1208-1214.
"""
from typing import Dict, Any, List, Optional
import math
import numpy as np
from scipy import stats


class SpecificationCurve:
    """规格曲线分析器 — 汇总所有规格结果的稳健性.

    接收一组记录 (来自 SpecificationLogger), 计算:
    - median_effect: 中位效应
    - consistency: 效应方向一致性 (high / medium / low)
    - specifications: 规格列表
    """

    def __init__(self, records: Optional[List[Dict[str, Any]]] = None):
        self.records = records or []

    def analyze(self) -> Dict[str, Any]:
        """计算规格曲线分析结果."""
        if not self.records:
            return {
                'specifications': [],
                'results': [],
                'p_values': [],
                'median_effect': float('nan'),
                'consistency': 'undefined',
            }

        results = [r.get('result', {}).get('ic', float('nan')) for r in self.records]
        p_values = [r.get('result', {}).get('p_value', float('nan')) for r in self.records]

        valid_results = [r for r in results if not (isinstance(r, float) and np.isnan(r))]
        if not valid_results:
            consistency = 'undefined'
        else:
            pos_ratio = sum(1 for r in valid_results if r > 0) / len(valid_results)
            consistency = 'high' if pos_ratio > 0.8 or pos_ratio < 0.2 else (
                'medium' if pos_ratio > 0.6 or pos_ratio < 0.4 else 'low'
            )

        return {
            'specifications': self.records,
            'results': results,
            'p_values': p_values,
            'median_effect': float(np.nanmedian(results)) if results else float('nan'),
            'consistency': consistency,
        }


# ============================================================
# 联合推断（v3.7.0 E4，设计 §7.4）
# ============================================================

_EFFECTS = ('mean', 'sharpe')
_DIRECTIONS = ('two-sided', 'greater', 'less')
_RESAMPLING = ('stationary', 'iid')


def _bootstrap_indices(
    n: int,
    n_bootstrap: int,
    block_size: int,
    resampling: str,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if resampling == 'iid':
        return rng.integers(0, n, size=(n_bootstrap, n))
    idx = np.empty((n_bootstrap, n), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, size=n_bootstrap)
    probability = 1.0 / block_size
    for t in range(1, n):
        fresh = rng.random(n_bootstrap) < probability
        draws = rng.integers(0, n, size=n_bootstrap)
        idx[:, t] = np.where(fresh, draws, (idx[:, t - 1] + 1) % n)
    return idx


def _effect(values: np.ndarray, effect: str) -> np.ndarray:
    if effect == 'mean':
        return values.mean(axis=0)
    std = values.std(axis=0, ddof=1)
    if np.any(std <= 0.0) or np.any(~np.isfinite(std)):
        raise ValueError("bootstrap 样本出现零方差列，请更换 seed")
    return values.mean(axis=0) / std


def _significance(z: np.ndarray, direction: str, alpha: float) -> np.ndarray:
    if direction == 'greater':
        return z > stats.norm.ppf(1.0 - alpha)
    if direction == 'less':
        return z < stats.norm.ppf(alpha)
    return np.abs(z) > stats.norm.ppf(1.0 - alpha / 2.0)


def _p_value(null: np.ndarray, observed: float,
             direction: str) -> float:
    n = null.size
    if direction == 'greater':
        count = int(np.sum(null >= observed))
    elif direction == 'less':
        count = int(np.sum(null <= observed))
    else:
        count = int(np.sum(np.abs(null) >= abs(observed)))
    return (1.0 + count) / (n + 1.0)


def joint_inference(
    values: np.ndarray,
    *,
    effect: str = "mean",
    direction: str = "two-sided",
    n_bootstrap: int = 1000,
    block_size: Optional[int] = None,
    resampling: str = "stationary",
    alpha: float = 0.05,
    seed: int = 0,
) -> Dict[str, Any]:
    """多规格联合推断（null-imposed bootstrap，设计 §7.4）。

    参数:
        values: ``(T, M)`` 矩阵，列为一个规格的逐期收益或 IC；
            **所有列必须同量纲**（同为收益或同为 IC）。
        effect: ``"mean"`` 或 ``"sharpe"``（逐期口径）
        direction: ``"two-sided"`` / ``"greater"`` / ``"less"``
        resampling: ``"stationary"``（Politis-Romano）或 ``"iid"``
        block_size: stationary bootstrap 平均块长，缺省 ``ceil(sqrt(T))``
        alpha: 显著性水平，同时用于 share_significant 的阈值
        seed: 随机种子

    做法:
        1. 观测统计量由原始 ``values`` 计算；
        2. 零假设强加：``centered = values - mean(values)``（逐列）；
        3. 所有规格共用同一组 bootstrap 索引，从 ``centered`` 重抽样；
        4. 零分布按 ``se_null``（bootstrap 效应量的标准差）标准化为 z；
        5. 三个统计量：median / share_significant / aggregated_z（Stouffer）。
    """
    data = np.asarray(values, dtype=float)
    if data.ndim != 2:
        raise ValueError("values 必须是二维 (T, M)")
    t, m = data.shape
    if t < 3:
        raise ValueError("T 必须 >= 3")
    if m < 1:
        raise ValueError("M 必须 >= 1")
    if not np.all(np.isfinite(data)):
        raise ValueError("values 含 NaN 或 Inf")
    if (np.any(data.std(axis=0, ddof=1) <= 0.0)
            or np.any(np.ptp(data, axis=0) == 0.0)):
        # ptp 守卫拦截均值舍入导致的 std≈1e-19 假阳性列（v3.7.0 复审 H1）
        raise ValueError("存在零方差列，无法做联合推断")
    if effect not in _EFFECTS:
        raise ValueError("effect 必须是 %r 之一" % (_EFFECTS,))
    if direction not in _DIRECTIONS:
        raise ValueError("direction 必须是 %r 之一" % (_DIRECTIONS,))
    if resampling not in _RESAMPLING:
        raise ValueError("resampling 必须是 %r 之一" % (_RESAMPLING,))
    if not (0.0 < float(alpha) < 1.0):
        raise ValueError("alpha 必须在 (0, 1) 内")
    if int(n_bootstrap) != n_bootstrap or n_bootstrap < 100:
        raise ValueError("n_bootstrap 必须是 >= 100 的整数")
    if block_size is None:
        block = max(1, int(math.ceil(math.sqrt(t))))
    else:
        if int(block_size) != block_size or block_size < 1:
            raise ValueError("block_size 必须是 >= 1 的整数")
        block = int(block_size)

    n_bootstrap = int(n_bootstrap)
    alpha = float(alpha)
    centered = data - data.mean(axis=0, keepdims=True)
    idx = _bootstrap_indices(t, n_bootstrap, block, resampling, seed)

    observed_effect = _effect(data, effect)
    null_effects = np.empty((n_bootstrap, m), dtype=float)
    for b in range(n_bootstrap):
        sample = centered[idx[b]]
        null_effects[b] = _effect(sample, effect)

    se_null = null_effects.std(axis=0, ddof=1)
    if np.any(~np.isfinite(se_null)) or np.any(se_null <= 0.0):
        raise ValueError("bootstrap 零分布出现零方差列，请更换 seed")

    z_obs = observed_effect / se_null
    z_null = null_effects / se_null
    sig_obs = _significance(z_obs, direction, alpha)
    sig_null = _significance(z_null, direction, alpha)

    null_stats = {
        'median': np.median(null_effects, axis=1),
        'share_significant': sig_null.mean(axis=1),
        'aggregated_z': z_null.sum(axis=1) / math.sqrt(m),
    }
    observed_stats = {
        'median': float(np.median(observed_effect)),
        'share_significant': float(sig_obs.mean()),
        'aggregated_z': float(z_obs.sum() / math.sqrt(m)),
    }
    p_direction = {
        'median': direction,
        'share_significant': 'greater',
        'aggregated_z': direction,
    }

    statistics = []
    for name in ('median', 'share_significant', 'aggregated_z'):
        null = null_stats[name]
        observed = observed_stats[name]
        statistics.append({
            'name': name,
            'estimate': observed,
            'null_lower': float(np.quantile(null, alpha / 2.0)),
            'null_upper': float(np.quantile(null, 1.0 - alpha / 2.0)),
            'p_value': _p_value(null, observed, p_direction[name]),
            'n_specs': int(m),
        })

    return {
        'statistics': statistics,
        'n_bootstrap': n_bootstrap,
        'block_size': block,
        'resampling': resampling,
        'effect': effect,
        'direction': direction,
        'alpha': alpha,
        'seed': int(seed),
        'n_periods': int(t),
        'n_specs': int(m),
        'method': 'null_imposed_bootstrap',
    }
