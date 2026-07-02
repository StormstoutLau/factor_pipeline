# -*- coding: utf-8 -*-
"""
时间序列解耦器基类

定义解耦器的基本接口和通用功能。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)


@dataclass
class DecouplerConfig:
    """解耦器配置"""
    max_ar_order: int = 5                 # 最大AR阶数
    min_ar_order: int = 1                 # 最小AR阶数
    order_selection: str = 'aic'          # 阶数选择准则：'aic', 'bic', 'hqic'
    min_obs_per_stock: int = 20           # 每只股票最少观测数
    min_stocks: int = 10                  # 最少股票数
    decorrelation_strength: float = 1.0   # 解耦强度 [0, 1]
    fit_intercept: bool = True            # 是否拟合截距
    rolling_window: Optional[int] = None  # 滚动窗口，None表示全窗口
    industry_neutralize_first: bool = True # 是否先进行行业中性化
    industry_neutralize_residual: bool = True  # 是否对残差再中性化
    verbose: bool = True                  # 是否输出详细日志


class BaseDecoupler(ABC):
    """
    时间序列解耦器基类

    抽象基类，定义解耦器的通用接口。
    所有具体实现必须继承此类并实现核心方法。

    设计原则：
    1. sklearn 风格：fit/transform/fit_transform
    2. 前瞻偏差防护：仅使用历史信息
    3. 股票级独立建模：每只股票独立拟合
    4. 完整状态追踪：记录所有模型参数和统计量
    """

    def __init__(self, config: Optional[DecouplerConfig] = None):
        self.config = config or DecouplerConfig()
        self.is_fitted = False
        self._models: Dict[str, Dict[str, Any]] = {}  # {stock_code: {params}}
        self._fitted_params: Dict[str, pd.DataFrame] = {}  # 记录拟合参数
        self._stats: Dict[str, Dict[str, float]] = {}  # 统计量

    @abstractmethod
    def fit(self, X: pd.DataFrame, **kwargs) -> 'BaseDecoupler':
        """
        拟合解耦模型

        Parameters
        ----------
        X : pd.DataFrame, shape (T, N)
            因子面板数据，index为时间，columns为股票代码

        Returns
        -------
        self
        """
        pass

    @abstractmethod
    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        应用解耦变换

        Parameters
        ----------
        X : pd.DataFrame, shape (T, N)
            因子面板数据

        Returns
        -------
        pd.DataFrame
            解耦后的因子值
        """
        pass

    def fit_transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """拟合并变换"""
        return self.fit(X, **kwargs).transform(X, **kwargs)

    def _validate_data(self, X: pd.DataFrame) -> Tuple[bool, str]:
        """
        验证输入数据

        Returns
        -------
        (is_valid, message)
        """
        if X.empty:
            return False, "输入数据为空"

        if X.shape[0] < self.config.min_ar_order * 2:
            return False, f"数据长度 {X.shape[0]} 不足以拟合AR模型（至少需要 {self.config.min_ar_order * 2} 期）"

        valid_stocks = X.dropna(axis=1, how='all').columns.tolist()
        if len(valid_stocks) < self.config.min_stocks:
            return False, f"有效股票数 {len(valid_stocks)} 少于最小要求 {self.config.min_stocks}"

        return True, "OK"

    def _compute_residuals(self,
                           series: pd.Series,
                           params: Dict[str, Any]) -> pd.Series:
        """
        计算AR残差（模板方法）

        由子类实现具体的残差计算逻辑。
        """
        raise NotImplementedError

    def get_model_summary(self) -> pd.DataFrame:
        """
        获取模型摘要

        Returns
        -------
        pd.DataFrame
            包含每只股票的AR阶数、系数、R²等统计量
        """
        if not self._fitted_params:
            return pd.DataFrame()

        summary = []
        for stock, params in self._fitted_params.items():
            row = {'stock': stock}
            row.update(params)
            summary.append(row)

        return pd.DataFrame(summary).set_index('stock')

    def get_residual_stats(self) -> Dict[str, Dict[str, float]]:
        """
        获取残差统计量

        Returns
        -------
        Dict[str, Dict[str, float]]
            每只股票的残差统计量
        """
        return self._stats.copy()

    def check_autocorrelation_removal(self,
                                      residuals: pd.DataFrame,
                                      threshold: float = 0.1) -> Dict[str, bool]:
        """
        检查自相关是否被有效移除

        对残差进行Ljung-Box检验，p值 > threshold 表示无显著自相关。

        Parameters
        ----------
        residuals : pd.DataFrame
            残差数据
        threshold : float
            显著性阈值

        Returns
        -------
        Dict[str, bool]
            每只股票是否通过检验
        """
        from scipy.stats import kstest

        results = {}
        for col in residuals.columns:
            series = residuals[col].dropna()
            if len(series) < 10:
                results[col] = False
                continue

            try:
                from statsmodels.stats.diagnostic import acorr_ljungbox
                lb = acorr_ljungbox(series, lags=[5], return_df=True)
                pvalue = lb['lb_pvalue'].iloc[0]
                results[col] = pvalue > threshold
            except Exception:
                # 回退：检查标准差是否显著
                results[col] = series.std() < 1.5

        pass_rate = sum(results.values()) / len(results) if results else 0
        logger.info(f"自相关移除检查通过率: {pass_rate:.1%}")

        return results

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(order_selection={self.config.order_selection}, " \
               f"max_order={self.config.max_ar_order}, " \
               f"strength={self.config.decorrelation_strength})"
