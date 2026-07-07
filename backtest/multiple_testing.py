# -*- coding: utf-8 -*-
"""多重检验校正模块 (v3.0.0 T3.5)

低级多重检验校正函数, 供 unified_drift / pipelines_v2 / factor_significance 共享调用.

支持三种校正方法:
1. BH-FDR (Benjamini-Hochberg 1995) — 默认, 检测力高
2. Bonferroni — 保守, FWER 控制
3. None — 无校正 (raw p-value)

学术依据:
- Benjamini, Y. & Hochberg, Y. (1995). "Controlling the False Discovery Rate."
  JRSS-B 57(1):289-300.
- Bonferroni, C. E. (1936). "Teoria statistica delle classi e calcolo delle
  probabilità." Pubblicazioni del R Istituto Superiore di Scienze Sociali e
  Politiche di Firenze 8:3-62.

API 设计:
    apply_bh_fdr(p_values, alpha) -> (p_adj, is_significant)
    apply_bonferroni(p_values, alpha) -> (p_adj, is_significant)
    apply_no_correction(p_values, alpha) -> (p_adj, is_significant)

    p_adj: List[float] — 校正后 p 值 (与输入顺序一致)
    is_significant: List[bool] — 是否显著
"""
from typing import List, Tuple
import logging
import numpy as np

logger = logging.getLogger(__name__)


def _validate_p_values(p_values: List[float]) -> None:
    """校验 p 值合法性"""
    if len(p_values) == 0:
        return
    arr = np.asarray(p_values, dtype=float)
    if np.any(np.isnan(arr)):
        raise ValueError("p_values contains NaN")
    if np.any(arr < 0):
        raise ValueError("p_values contains negative value")
    if np.any(arr > 1):
        raise ValueError("p_values contains value > 1")


def _validate_alpha(alpha: float) -> None:
    """校验 alpha 合法性"""
    if not (0 < alpha <= 1):
        raise ValueError(f"alpha must be in (0, 1], got {alpha}")


def apply_bh_fdr(
    p_values: List[float],
    alpha: float = 0.05,
) -> Tuple[List[float], List[bool]]:
    """BH-FDR 校正 (Benjamini-Hochberg 1995)

    控制 False Discovery Rate (FDR) — 错误拒绝数占总拒绝数的期望比例.

    公式:
        p_adj_(k) = p_(k) * K / rank, 从大到小累积 min, clip [0, 1]
        判定: 找到最大 k* 使 p_adj_(k*) <= alpha, 然后 1..k* 都显著

    Args:
        p_values: 原始 p 值列表 (顺序任意)
        alpha: 显著性水平 (默认 0.05)

    Returns:
        (p_adj, is_significant)
        p_adj: 校正后 p 值 (与输入顺序一致)
        is_significant: 是否显著 (与输入顺序一致)

    Raises:
        ValueError: p 值非法 / alpha 非法

    Reference:
        Benjamini, Y. & Hochberg, Y. (1995). "Controlling the False Discovery
        Rate." JRSS-B 57(1):289-300.
    """
    _validate_alpha(alpha)
    _validate_p_values(p_values)

    if len(p_values) == 0:
        return [], []

    K = len(p_values)
    p_arr = np.asarray(p_values, dtype=float)

    # BH 校正: 排序, 从大到小累积 min
    order = np.argsort(p_arr)
    p_adj = np.empty_like(p_arr)
    prev = 1.0
    for i in range(K - 1, -1, -1):
        rank = i + 1
        idx = order[i]
        bh = p_arr[idx] * K / rank
        prev = min(prev, bh)
        p_adj[idx] = min(prev, 1.0)

    # 显著性判定: BH step-up procedure
    # 找到最大的 k 使 p_(k) <= alpha * k / K
    sorted_p = np.sort(p_arr)
    is_sig_sorted = np.zeros(K, dtype=bool)
    k_star = 0
    for k in range(1, K + 1):
        if sorted_p[k - 1] <= alpha * k / K:
            k_star = k
    if k_star > 0:
        is_sig_sorted[:k_star] = True

    # 还原到原顺序
    is_significant = np.zeros(K, dtype=bool)
    for i in range(K):
        is_significant[order[i]] = is_sig_sorted[i]

    return p_adj.tolist(), is_significant.tolist()


def apply_bonferroni(
    p_values: List[float],
    alpha: float = 0.05,
) -> Tuple[List[float], List[bool]]:
    """Bonferroni 校正 (FWER 控制)

    控制 Family-Wise Error Rate (FWER) — 至少一个错误拒绝的概率.

    公式:
        p_adj = p * N
        判定: p_adj < alpha (等价 p < alpha / N)

    Args:
        p_values: 原始 p 值列表
        alpha: 显著性水平

    Returns:
        (p_adj, is_significant)
    """
    _validate_alpha(alpha)
    _validate_p_values(p_values)

    if len(p_values) == 0:
        return [], []

    N = len(p_values)
    p_arr = np.asarray(p_values, dtype=float)
    p_adj = np.minimum(p_arr * N, 1.0)
    is_significant = (p_arr < alpha / N).tolist()

    return p_adj.tolist(), is_significant


def apply_no_correction(
    p_values: List[float],
    alpha: float = 0.05,
) -> Tuple[List[float], List[bool]]:
    """无校正 (raw p-value)

    直接用原始 p 值与 alpha 比较, 不做多重检验校正.

    Args:
        p_values: 原始 p 值列表
        alpha: 显著性水平

    Returns:
        (p_values_copy, is_significant)
    """
    _validate_alpha(alpha)
    _validate_p_values(p_values)

    if len(p_values) == 0:
        return [], []

    p_arr = np.asarray(p_values, dtype=float)
    is_significant = (p_arr < alpha).tolist()

    return p_arr.tolist(), is_significant


def apply_correction(
    p_values: List[float],
    method: str = 'benjamini_hochberg',
    alpha: float = 0.05,
) -> Tuple[List[float], List[bool]]:
    """统一入口: 根据方法名调用对应校正

    Args:
        p_values: 原始 p 值列表
        method: 'benjamini_hochberg' | 'bonferroni' | 'none'
        alpha: 显著性水平

    Returns:
        (p_adj, is_significant)

    Raises:
        ValueError: method 不识别
    """
    if method == 'benjamini_hochberg':
        return apply_bh_fdr(p_values, alpha)
    elif method == 'bonferroni':
        return apply_bonferroni(p_values, alpha)
    elif method == 'none':
        return apply_no_correction(p_values, alpha)
    else:
        raise ValueError(
            f"Unknown correction method: {method}. "
            f"Supported: benjamini_hochberg, bonferroni, none"
        )
