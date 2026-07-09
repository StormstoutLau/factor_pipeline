# -*- coding: utf-8 -*-
"""
AR模型与阶数选择器

基于信息准则（AIC/BIC/HQIC）自动选择最优AR阶数。
"""

from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import pandas as pd
from dataclasses import dataclass
import logging

# v3.1.0 E1 (§2): 隐藏效应诊断 Mixin (不侵入 fit/transform).
# 局部导入避免循环依赖 — diagnostics 包仅依赖 numpy/pandas/scipy.
from factor_pipeline.modules.factor_decoupler.diagnostics.hidden_effect import (
    HiddenEffectDiagnosticMixin as _HiddenEffectDiagnosticMixin,
)

logger = logging.getLogger(__name__)


@dataclass
class ARModelResult:
    """AR模型拟合结果"""
    order: int              # 选定的AR阶数
    coefficients: np.ndarray  # AR系数 [phi_1, phi_2, ..., phi_p, intercept]
    residuals: pd.Series    # 残差
    fitted_values: pd.Series # 拟合值
    aic: float              # AIC
    bic: float              # BIC
    hqic: float            # HQIC
    r_squared: float        # R²
    sigma2: float           # 残差方差
    log_likelihood: float   # 对数似然


class AROrderSelector:
    """
    AR阶数选择器

    基于信息准则（AIC/BIC/HQIC）自动选择最优AR阶数。
    支持多只股票并行选择。

    Usage:
        selector = AROrderSelector(max_order=5, criterion='aic')
        results = selector.fit(series)
        print(f"最优阶数: {results.order}")
        print(f"AIC: {results.aic:.4f}")
    """

    def __init__(self,
                 max_order: int = 5,
                 min_order: int = 1,
                 criterion: str = 'aic',
                 min_obs: int = 20):
        self.max_order = max_order
        self.min_order = min_order
        self.criterion = criterion.lower()
        self.min_obs = min_obs

        self._criterion_funcs = {
            'aic': self._aic,
            'bic': self._bic,
            'hqic': self._hqic,
        }

        if self.criterion not in self._criterion_funcs:
            raise ValueError(f"不支持的信息准则: {criterion}，支持: {list(self._criterion_funcs.keys())}")

    def fit(self, series: pd.Series) -> ARModelResult:
        """
        拟合并选择最优阶数

        Parameters
        ----------
        series : pd.Series
            时间序列

        Returns
        -------
        ARModelResult
            包含最优阶数和详细结果
        """
        series = series.dropna()
        if len(series) < self.min_obs:
            raise ValueError(f"数据长度 {len(series)} 少于最小要求 {self.min_obs}")

        # 尝试不同阶数
        best_order = self.min_order
        best_result = None
        best_value = np.inf

        for order in range(self.min_order, self.max_order + 1):
            if len(series) <= order + 5:  # 至少需要 order + 5 个观测
                continue

            try:
                result = self._fit_ar(series, order)
                criterion_value = self._get_criterion_value(result)

                if criterion_value < best_value:
                    best_value = criterion_value
                    best_order = order
                    best_result = result

            except Exception as e:
                logger.debug(f"AR({order}) 拟合失败: {e}")
                continue

        if best_result is None:
            # 回退：使用AR(1)
            best_order = 1
            best_result = self._fit_ar(series, 1)
            logger.warning(f"所有AR模型拟合失败，使用AR(1)作为备选")

        best_result.order = best_order
        logger.info(f"AR阶数选择完成: order={best_order}, {self.criterion.upper()}={best_value:.4f}")

        return best_result

    def _fit_ar(self, series: pd.Series, order: int) -> ARModelResult:
        """拟合指定阶数的AR模型"""
        y = series.values
        n = len(y)

        # 构建滞后矩阵
        X = np.column_stack([y[order - i:None if i == 0 else -i] for i in range(1, order + 1)])
        y_trimmed = y[order:]

        # 添加常数项
        X = np.column_stack([np.ones(len(y_trimmed)), X])

        # OLS估计
        try:
            beta = np.linalg.lstsq(X, y_trimmed, rcond=None)[0]
        except np.linalg.LinAlgError:
            raise ValueError("OLS估计失败")

        coefficients = beta
        fitted = X @ beta
        residuals = y_trimmed - fitted

        # 统计量计算
        n_obs = len(residuals)
        k = len(coefficients)
        sigma2 = np.var(residuals, ddof=0)
        log_likelihood = -n_obs / 2 * (np.log(2 * np.pi * sigma2) + 1)
        r_squared = 1 - np.var(residuals) / np.var(y_trimmed) if np.var(y_trimmed) > 0 else 0

        # 信息准则
        aic = -2 * log_likelihood + 2 * k
        bic = -2 * log_likelihood + k * np.log(n_obs)
        hqic = -2 * log_likelihood + 2 * k * np.log(np.log(n_obs))

        return ARModelResult(
            order=order,
            coefficients=coefficients,
            residuals=pd.Series(residuals, index=series.index[order:]),
            fitted_values=pd.Series(fitted, index=series.index[order:]),
            aic=aic,
            bic=bic,
            hqic=hqic,
            r_squared=r_squared,
            sigma2=sigma2,
            log_likelihood=log_likelihood
        )

    def _aic(self, result: ARModelResult) -> float:
        return result.aic

    def _bic(self, result: ARModelResult) -> float:
        return result.bic

    def _hqic(self, result: ARModelResult) -> float:
        return result.hqic

    def _get_criterion_value(self, result: ARModelResult) -> float:
        func = self._criterion_funcs[self.criterion]
        return func(result)

    def batch_fit(self,
                  data: pd.DataFrame) -> Dict[str, ARModelResult]:
        """
        批量拟合多个股票

        Parameters
        ----------
        data : pd.DataFrame, shape (T, N)
            面板数据

        Returns
        -------
        Dict[str, ARModelResult]
            股票代码到拟合结果的映射
        """
        results = {}
        for col in data.columns:
            try:
                series = data[col].dropna()
                if len(series) >= self.min_obs:
                    results[col] = self.fit(series)
            except Exception as e:
                logger.debug(f"股票 {col} 拟合失败: {e}")
                continue

        logger.info(f"批量拟合完成: {len(results)}/{len(data.columns)} 只股票成功")
        return results


class ARDecoupler(_HiddenEffectDiagnosticMixin):
    """
    AR解耦器

    对时间序列进行AR建模，提取残差作为去相关后的新息。
    支持：
    1. 自动阶数选择（AIC/BIC）
    2. 固定阶数
    3. 软解耦（保留部分原始信号）

    Usage:
        decoupler = ARDecoupler(max_order=5, criterion='aic')
        residuals = decoupler.fit_transform(series)
    """

    def __init__(self,
                 max_order: int = 5,
                 min_order: int = 1,
                 criterion: str = 'aic',
                 strength: float = 1.0,
                 min_obs: int = 20):
        self.max_order = max_order
        self.min_order = min_order
        self.criterion = criterion
        self.strength = strength  # 解耦强度 [0, 1]
        self.min_obs = min_obs

        self._selector = AROrderSelector(
            max_order=max_order,
            min_order=min_order,
            criterion=criterion,
            min_obs=min_obs
        )
        self._results: Dict[str, ARModelResult] = {}
        self.is_fitted = False

    def fit(self, data: pd.DataFrame) -> 'ARDecoupler':
        """
        拟合AR模型

        Parameters
        ----------
        data : pd.DataFrame, shape (T, N)
            面板数据

        Returns
        -------
        self
        """
        self._results = self._selector.batch_fit(data)
        self.is_fitted = True
        logger.info(f"AR模型拟合完成: {len(self._results)} 只股票")
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        应用AR解耦

        Parameters
        ----------
        data : pd.DataFrame, shape (T, N)
            原始数据

        Returns
        -------
        pd.DataFrame
            解耦后的数据
        """
        if not self.is_fitted:
            raise ValueError("模型未拟合，请先调用 fit()")

        result = data.copy()

        for col in data.columns:
            if col not in self._results:
                continue

            ar_result = self._results[col]
            series = data[col].copy()

            # 计算残差
            predicted = ar_result.fitted_values.reindex(series.index).ffill()
            residual = series - predicted

            # 软混合
            result[col] = (1 - self.strength) * series + self.strength * residual

        return result

    def fit_transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """拟合并变换"""
        return self.fit(data).transform(data)

    def get_residual_stats(self) -> Dict[str, Dict[str, float]]:
        """
        获取残差统计量

        Returns
        -------
        Dict[str, Dict[str, float]]
            每只股票的残差统计量
        """
        if not self._results:
            return {}

        stats = {}
        for stock, result in self._results.items():
            residuals = result.residuals.dropna()
            if len(residuals) > 0:
                stats[stock] = {
                    'mean': float(residuals.mean()),
                    'std': float(residuals.std()),
                    'skewness': float(residuals.skew()),
                    'kurtosis': float(residuals.kurtosis()),
                }
        return stats

    def get_summary(self) -> pd.DataFrame:
        """
        获取模型摘要

        Returns
        -------
        pd.DataFrame
            包含阶数、系数、AIC/BIC等
        """
        if not self._results:
            return pd.DataFrame()

        rows = []
        for stock, result in self._results.items():
            row = {
                'stock': stock,
                'ar_order': result.order,
                'r_squared': result.r_squared,
                'aic': result.aic,
                'bic': result.bic,
                'sigma2': result.sigma2,
            }
            for i, coef in enumerate(result.coefficients[1:], 1):  # 跳过截距
                row[f'phi_{i}'] = coef
            rows.append(row)

        return pd.DataFrame(rows).set_index('stock')
