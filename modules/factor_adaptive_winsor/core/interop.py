# -*- coding: utf-8 -*-
"""
互操作性适配层
提供与 Qlib / Alphalens 等主流量化框架的无缝集成接口

使用方式:
    from factor_adaptive_winsor.interop import (
        qlib_winsorize, alphalens_preprocess, to_qlib_format, to_alphalens_format
    )
"""

import pandas as pd
import numpy as np
from typing import Optional, Union, Dict, Any
import warnings

warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────
# Qlib 集成
# ─────────────────────────────────────────────────────────────────

def to_qlib_format(
    factor_data: pd.DataFrame,
    factor_name: str = "factor_value",
) -> pd.DataFrame:
    """
    将因子数据转换为 Qlib 兼容格式

    Qlib 期望的格式:
        pd.DataFrame with columns ['instrument', 'datetime', factor_name]

    Parameters
    ----------
    factor_data : pd.DataFrame
        宽格式因子数据，index=日期, columns=股票代码
    factor_name : str
        列名（默认 'factor_value'）

    Returns
    -------
    pd.DataFrame
        长格式，兼容 Qlib DataHandler
    """
    if factor_data.index.name is None:
        factor_data = factor_data.copy()
        factor_data.index.name = "datetime"

    stacked = factor_data.stack().reset_index()
    stacked.columns = ["datetime", "instrument", factor_name]
    return stacked


def qlib_winsorize(
    factor_data: pd.DataFrame,
    method: str = "smart_adaptive",
    max_outlier_frac: float = 0.05,
    preserve_tail_info: bool = True,
    cross_sectional: bool = True,
) -> pd.DataFrame:
    """
    Qlib 风格的因子去极值，直接替换 Qlib 中简单的 percentile winsorize

    Qlib 原生只支持固定分位数截断（如 CSRankNorm, CSZScoreNorm），
    本函数提供 C¹ 连续自适应软截断作为替代。

    Parameters
    ----------
    factor_data : pd.DataFrame
        宽格式因子数据，index=日期, columns=股票代码
    method : str
        去极值方法：'smart_adaptive' (默认), 'kde_based', 'mixture_model'
    max_outlier_frac : float
        最大异常值比例
    preserve_tail_info : bool
        是否保留尾部信息（推荐 True）
    cross_sectional : bool
        True=横截面处理（每个时间点单独处理）
        False=时间序列处理（每只股票单独处理）

    Returns
    -------
    pd.DataFrame
        去极值后的因子数据，格式与输入相同
    """
    from .enhanced_transformers import SmartAdaptiveWinsorizer

    result = factor_data.copy()

    if cross_sectional:
        # 横截面模式：每个时间截面对所有股票处理
        for date in result.index:
            row = result.loc[date].dropna()
            if len(row) < 3:
                continue
            winsorizer = SmartAdaptiveWinsorizer(
                method=method,
                max_outlier_frac=max_outlier_frac,
                preserve_tail_info=preserve_tail_info,
            )
            winsorizer.fit(row.values)
            result.loc[date, row.index] = winsorizer.transform(row.values)
    else:
        # 时间序列模式：每只股票的时间序列单独处理
        for col in result.columns:
            series = result[col].dropna()
            if len(series) < 3:
                continue
            winsorizer = SmartAdaptiveWinsorizer(
                method=method,
                max_outlier_frac=max_outlier_frac,
                preserve_tail_info=preserve_tail_info,
            )
            winsorizer.fit(series.values)
            result.loc[series.index, col] = winsorizer.transform(series.values)

    return result


# ─────────────────────────────────────────────────────────────────
# Alphalens 集成
# ─────────────────────────────────────────────────────────────────

def to_alphalens_format(
    factor_data: pd.DataFrame,
    prices: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    将因子数据转换为 Alphalens 兼容格式

    Alphalens 期望的 multi-index 格式:
        pd.DataFrame with MultiIndex [date, asset]

    Parameters
    ----------
    factor_data : pd.DataFrame
        宽格式因子数据，index=日期, columns=股票代码
    prices : pd.DataFrame, optional
        价格数据，用于生成 forward returns

    Returns
    -------
    pd.DataFrame
        Alphalens 兼容格式
    """
    stacked = factor_data.stack()
    stacked.index.names = ["date", "asset"]
    return pd.DataFrame({"factor": stacked})


def alphalens_preprocess(
    factor_data: pd.DataFrame,
    method: str = "smart_adaptive",
    max_outlier_frac: float = 0.05,
    standardize: bool = True,
    cross_sectional: bool = True,
) -> pd.DataFrame:
    """
    Alphalens 因子预处理流水线

    在 Alphalens 分析之前对因子数据进行完整的预处理：
    1. 自适应去极值（C¹ 连续软截断）
    2. 可选标准化

    Parameters
    ----------
    factor_data : pd.DataFrame
        宽格式因子数据，index=日期, columns=股票代码
    method : str
        去极值方法
    max_outlier_frac : float
        最大异常值比例
    standardize : bool
        是否进行横截面标准化（每期均值0标准差1）
    cross_sectional : bool
        是否横截面处理

    Returns
    -------
    pd.DataFrame
        预处理后的因子数据，可直接传入 alphalens.utils.get_clean_factor_and_forward_returns()
    """
    # 步骤1：去极值
    processed = qlib_winsorize(
        factor_data,
        method=method,
        max_outlier_frac=max_outlier_frac,
        preserve_tail_info=True,
        cross_sectional=cross_sectional,
    )

    # 步骤2：标准化
    if standardize:
        processed = (processed.subtract(processed.mean(axis=1), axis=0)
                     .divide(processed.std(axis=1).replace(0, 1), axis=0))

    return processed


# ─────────────────────────────────────────────────────────────────
# 通用工具
# ─────────────────────────────────────────────────────────────────

def compare_with_scipy(
    factor_data: pd.DataFrame,
    limits: tuple = (0.01, 0.01),
) -> Dict[str, Any]:
    """
    对比 SmartAdaptiveWinsorizer 与 scipy 传统 winsorize 的效果

    Parameters
    ----------
    factor_data : pd.DataFrame
        因子数据
    limits : tuple
        scipy winsorize 的参数

    Returns
    -------
    dict
        包含对比指标
    """
    from scipy.stats.mstats import winsorize
    from .enhanced_transformers import SmartAdaptiveWinsorizer

    # 展平数据
    flat_data = factor_data.values.flatten()
    flat_data = flat_data[~np.isnan(flat_data)]

    if len(flat_data) < 3:
        return {"error": "insufficient data"}

    # scipy winsorize（硬截断）
    scipy_result = winsorize(flat_data, limits=limits)
    scipy_tail = scipy_result[
        (scipy_result <= np.percentile(scipy_result, 1))
        | (scipy_result >= np.percentile(scipy_result, 99))
    ]
    scipy_unique = len(np.unique(scipy_tail)) / max(len(scipy_tail), 1)

    # SmartAdaptiveWinsorizer（软截断）
    winsorizer = SmartAdaptiveWinsorizer(
        method="smart_adaptive",
        preserve_tail_info=True,
    )
    winsorizer.fit(flat_data)
    adaptive_result = winsorizer.transform(flat_data)
    adaptive_tail = adaptive_result[
        (adaptive_result <= np.percentile(adaptive_result, 1))
        | (adaptive_result >= np.percentile(adaptive_result, 99))
    ]
    adaptive_unique = len(np.unique(adaptive_tail)) / max(len(adaptive_tail), 1)

    return {
        "scipy_winsorize": {
            "tail_unique_ratio": round(scipy_unique, 4),
            "has_hard_truncation": scipy_unique < 0.9,
        },
        "adaptive_winsor": {
            "tail_unique_ratio": round(adaptive_unique, 4),
            "has_hard_truncation": adaptive_unique < 0.9,
        },
        "recommendation": (
            "SmartAdaptiveWinsorizer 避免了硬截断"
            if adaptive_unique > scipy_unique
            else "结果相当"
        ),
    }