# -*- coding: utf-8 -*-
"""
统一时序解耦器 - 完整工具链

支持多种解耦方法：
- 'ar' : AR模型残差（自适应阶数选择）
- 'difference' : 一阶差分
- 'hp_filter' : Hodrick-Prescott滤波
- 'none' : 跳过解耦

解耦方法选择策略：
- 'ar1_median' : 基于AR(1)系数中位数自动选择
- 'fingerprint' : 基于完整因子指纹选择（与factor_pipeline集成）
- 'auto' : 自动选择最优方法
"""

from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
import logging

try:
    from statsmodels.tsa.filters.hp_filter import hpfilter
    HAS_STATSMODELS = True
except ImportError:
    HAS_STATSMODELS = False
    logging.warning("statsmodels not available, HP filter disabled")

from .ar_model import AROrderSelector
from .dual_neutralizer import DualNeutralizer

logger = logging.getLogger(__name__)


class TemporalDecoupler:
    """
    统一时序解耦器 - 完整工具链

    根据因子面板的时序特征，自动选择解耦方法，
    将高度自相关的因子转化为"新息"序列，保护增量信息。

    Parameters
    ----------
    method : str, default='auto'
        解耦方法。可选：
        - 'auto' : 自动选择最优方法
        - 'ar' : AR模型残差（自适应阶数选择）
        - 'difference' : 一阶差分
        - 'hp_filter' : Hodrick-Prescott滤波取周期项
        - 'none' : 跳过解耦

    method_selection : str, default='ar1_median'
        方法选择策略。仅在 method='auto' 时生效。
        - 'ar1_median' : 基于AR(1)系数中位数
        - 'fingerprint' : 基于完整因子指纹（需要factor_pipeline）

    ar_max_order : int, default=5
        AR模型最大阶数。

    ar_criterion : str, default='aic'
        AR阶数选择准则：'aic', 'bic', 'hqic'

    strong_ar_threshold : float, default=0.8
        AR(1)系数中位数高于此阈值视为强自相关。

    medium_ar_threshold : float, default=0.4
        AR(1)系数中位数低于此阈值视为弱自相关（直接跳过）。

    hp_lambda : float, default=1600
        HP滤波的平滑参数：
        - 月度数据: 14400
        - 季度数据: 1600
        - 年度数据: 6.25

    decorrelation_strength : float, default=1.0
        解耦强度 [0, 1]，软混合原始信号与残差。

    enable_neutralization : bool, default=False
        是否启用双重中性化（需要提供industry_data）。

    industry_data : pd.Series, optional
        行业分类数据，index为股票代码。

    market_cap_data : pd.DataFrame, optional
        市值数据，shape为(T, N)。

    verbose : bool, default=False
        是否输出诊断信息。
    """

    def __init__(
        self,
        method: str = 'auto',
        method_selection: str = 'ar1_median',
        ar_max_order: int = 5,
        ar_criterion: str = 'aic',
        strong_ar_threshold: float = 0.8,
        medium_ar_threshold: float = 0.4,
        hp_lambda: float = 1600,
        decorrelation_strength: float = 1.0,
        enable_neutralization: bool = False,
        industry_data: Optional[pd.Series] = None,
        market_cap_data: Optional[pd.DataFrame] = None,
        verbose: bool = False
    ):
        self.method = method
        self.method_selection = method_selection
        self.ar_max_order = ar_max_order
        self.ar_criterion = ar_criterion
        self.strong_ar_threshold = strong_ar_threshold
        self.medium_ar_threshold = medium_ar_threshold
        self.hp_lambda = hp_lambda
        self.decorrelation_strength = decorrelation_strength
        self.enable_neutralization = enable_neutralization
        self.industry_data = industry_data
        self.market_cap_data = market_cap_data
        self.verbose = verbose

        # fit后填入
        self.ar1_median_: Optional[float] = None
        self.selected_method_: Optional[str] = None
        self._neutralizer: Optional[DualNeutralizer] = None
        self._ar_selector: Optional[AROrderSelector] = None
        self._ar_results: Dict[str, Any] = {}
        self._is_fitted: bool = False

    def fit(self, X: pd.DataFrame, y=None, **kwargs) -> 'TemporalDecoupler':
        """
        拟合解耦器，选择解耦方法

        Parameters
        ----------
        X : pd.DataFrame
            因子面板，index为时间（DatetimeIndex），columns为股票代码。

        Returns
        -------
        self
        """
        if not isinstance(X, pd.DataFrame):
            raise TypeError("X must be a pandas DataFrame.")

        # 确定解耦方法
        if self.method == 'auto':
            self.selected_method_ = self._select_method(X)
        else:
            self.selected_method_ = self.method

        # 计算AR1中位数（用于诊断）
        self.ar1_median_ = self._calculate_ar1_median(X)

        # 初始化中性化器（如果启用）
        if self.enable_neutralization and self.industry_data is not None:
            self._neutralizer = DualNeutralizer(
                industry_data=self.industry_data,
                market_cap_data=self.market_cap_data
            )
            self._neutralizer.fit(X)

        # 初始化AR模型选择器（如果需要）
        if self.selected_method_ in ['ar', 'auto']:
            self._ar_selector = AROrderSelector(
                max_order=self.ar_max_order,
                criterion=self.ar_criterion
            )
            self._ar_results = self._ar_selector.batch_fit(X)

        self._is_fitted = True

        if self.verbose:
            print(f"[TemporalDecoupler] AR1 median = {self.ar1_median_:.3f} | "
                  f"Selected method: {self.selected_method_}")

        return self

    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        对因子面板应用选定的解耦方法

        Parameters
        ----------
        X : pd.DataFrame
            与fit相同的因子面板（或相同结构的新面板）。

        Returns
        -------
        X_decoupled : pd.DataFrame
            解耦后的因子面板。
        """
        if not self._is_fitted:
            raise RuntimeError("Must fit before transform.")

        if self.selected_method_ == 'none':
            return X.copy()

        # 应用中性化（如果启用且为AR方法）
        if self.enable_neutralization and self._neutralizer is not None:
            X = self._neutralizer.transform(X)

        # 应用解耦方法
        result = X.copy()
        for col in X.columns:
            series = X[col].copy()
            if self.selected_method_ == 'difference':
                result[col] = self._apply_difference(series)
            elif self.selected_method_ == 'ar':
                result[col] = self._apply_ar_residual(series, col)
            elif self.selected_method_ == 'hp_filter':
                result[col] = self._apply_hp_filter(series)

        # 应用软解耦强度
        if self.decorrelation_strength < 1.0:
            result = (1 - self.decorrelation_strength) * X + self.decorrelation_strength * result

        return result

    def fit_transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """拟合并转换"""
        return self.fit(X).transform(X)

    def get_summary(self) -> Dict[str, Any]:
        """
        获取解耦摘要信息

        Returns
        -------
        Dict[str, Any]
            包含AR1中位数、选择的方法等信息
        """
        summary = {
            'ar1_median': self.ar1_median_,
            'selected_method': self.selected_method_,
            'decorrelation_strength': self.decorrelation_strength,
            'enable_neutralization': self.enable_neutralization
        }

        if self._ar_results:
            orders = [r.order for r in self._ar_results.values()]
            summary['ar_orders'] = {
                'min': np.min(orders),
                'max': np.max(orders),
                'mean': np.mean(orders),
                'median': np.median(orders)
            }

        return summary

    # -----------------------------------------------------------------
    # 内部方法
    # -----------------------------------------------------------------

    def _select_method(self, X: pd.DataFrame) -> str:
        """自动选择解耦方法"""
        ar1_median = self._calculate_ar1_median(X)

        if self.method_selection == 'ar1_median':
            if ar1_median > self.strong_ar_threshold:
                return 'ar'
            elif ar1_median > self.medium_ar_threshold:
                return 'difference'
            else:
                return 'none'
        elif self.method_selection == 'fingerprint':
            # TODO: 集成factor_pipeline的fingerprint系统
            logger.warning("fingerprint method selection not fully implemented, fallback to ar1_median")
            return self._select_method(X)
        else:
            raise ValueError(f"Unknown method_selection: {self.method_selection}")

    def _calculate_ar1_median(self, X: pd.DataFrame) -> float:
        """计算每只股票的AR(1)系数中位数"""
        ar1_coeffs = []
        for col in X.columns:
            series = X[col].dropna()
            if len(series) > 2:
                ar1 = self._estimate_ar1(series)
                ar1_coeffs.append(ar1)
        if len(ar1_coeffs) == 0:
            return 0.0
        return np.median(ar1_coeffs)

    @staticmethod
    def _estimate_ar1(series: pd.Series) -> float:
        """估计AR(1)系数"""
        y = series.values[1:]
        X = series.values[:-1]
        mask = np.isfinite(y) & np.isfinite(X)
        y, X = y[mask], X[mask]
        if len(y) < 3:
            return 0.0
        # 快速计算：用corr代替完整OLS
        return np.corrcoef(y, X)[0, 1] if len(y) > 1 else 0.0

    @staticmethod
    def _apply_difference(series: pd.Series) -> pd.Series:
        """一阶差分"""
        return series.diff()

    def _apply_ar_residual(self, series: pd.Series, col: str) -> pd.Series:
        """AR模型残差"""
        if col in self._ar_results:
            result = self._ar_results[col]
            residuals = result.residuals.reindex(series.index)
            return residuals
        return series

    def _apply_hp_filter(self, series: pd.Series) -> pd.Series:
        """HP滤波，返回周期成分"""
        if not HAS_STATSMODELS:
            logger.warning("statsmodels not available, skipping HP filter")
            return series

        valid = series.dropna()
        if len(valid) < 4:
            return pd.Series(np.nan, index=series.index)

        try:
            _, cycle = hpfilter(valid.values, lamb=self.hp_lambda)
            result = pd.Series(np.nan, index=series.index)
            result.loc[valid.index] = cycle
            return result
        except Exception as e:
            logger.warning(f"HP filter failed for series: {e}")
            return series


# ---------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------

def decouple_ar(
    X: pd.DataFrame,
    max_order: int = 5,
    criterion: str = 'aic',
    decorrelation_strength: float = 1.0,
    enable_neutralization: bool = False,
    industry_data: Optional[pd.Series] = None,
    verbose: bool = False
) -> pd.DataFrame:
    """
    AR模型解耦 - 便捷函数

    Parameters
    ----------
    X : pd.DataFrame
        因子面板数据
    max_order : int
        最大AR阶数
    criterion : str
        阶数选择准则
    decorrelation_strength : float
        解耦强度
    enable_neutralization : bool
        是否启用双重中性化
    industry_data : pd.Series
        行业数据
    verbose : bool
        输出详情

    Returns
    -------
    pd.DataFrame
        解耦后的因子
    """
    decoupler = TemporalDecoupler(
        method='ar',
        ar_max_order=max_order,
        ar_criterion=criterion,
        decorrelation_strength=decorrelation_strength,
        enable_neutralization=enable_neutralization,
        industry_data=industry_data,
        verbose=verbose
    )
    return decoupler.fit_transform(X)


def decouple_difference(
    X: pd.DataFrame,
    decorrelation_strength: float = 1.0,
    enable_neutralization: bool = False,
    industry_data: Optional[pd.Series] = None,
    verbose: bool = False
) -> pd.DataFrame:
    """
    一阶差分解耦 - 便捷函数

    Parameters
    ----------
    X : pd.DataFrame
        因子面板数据
    decorrelation_strength : float
        解耦强度
    enable_neutralization : bool
        是否启用双重中性化
    industry_data : pd.Series
        行业数据
    verbose : bool
        输出详情

    Returns
    -------
    pd.DataFrame
        解耦后的因子
    """
    decoupler = TemporalDecoupler(
        method='difference',
        decorrelation_strength=decorrelation_strength,
        enable_neutralization=enable_neutralization,
        industry_data=industry_data,
        verbose=verbose
    )
    return decoupler.fit_transform(X)


def decouple_hp(
    X: pd.DataFrame,
    hp_lambda: float = 1600,
    decorrelation_strength: float = 1.0,
    enable_neutralization: bool = False,
    industry_data: Optional[pd.Series] = None,
    verbose: bool = False
) -> pd.DataFrame:
    """
    HP滤波解耦 - 便捷函数

    Parameters
    ----------
    X : pd.DataFrame
        因子面板数据
    hp_lambda : float
        HP滤波参数
    decorrelation_strength : float
        解耦强度
    enable_neutralization : bool
        是否启用双重中性化
    industry_data : pd.Series
        行业数据
    verbose : bool
        输出详情

    Returns
    -------
    pd.DataFrame
        解耦后的因子
    """
    decoupler = TemporalDecoupler(
        method='hp_filter',
        hp_lambda=hp_lambda,
        decorrelation_strength=decorrelation_strength,
        enable_neutralization=enable_neutralization,
        industry_data=industry_data,
        verbose=verbose
    )
    return decoupler.fit_transform(X)


def decouple_auto(
    X: pd.DataFrame,
    method_selection: str = 'ar1_median',
    ar_max_order: int = 5,
    strong_ar_threshold: float = 0.8,
    medium_ar_threshold: float = 0.4,
    hp_lambda: float = 1600,
    decorrelation_strength: float = 1.0,
    enable_neutralization: bool = False,
    industry_data: Optional[pd.Series] = None,
    verbose: bool = False
) -> pd.DataFrame:
    """
    自动解耦 - 便捷函数

    自动选择最优解耦方法

    Parameters
    ----------
    X : pd.DataFrame
        因子面板数据
    method_selection : str
        方法选择策略
    ar_max_order : int
        AR最大阶数
    strong_ar_threshold : float
        强自相关阈值
    medium_ar_threshold : float
        中等自相关阈值
    hp_lambda : float
        HP滤波参数
    decorrelation_strength : float
        解耦强度
    enable_neutralization : bool
        是否启用双重中性化
    industry_data : pd.Series
        行业数据
    verbose : bool
        输出详情

    Returns
    -------
    pd.DataFrame
        解耦后的因子
    """
    decoupler = TemporalDecoupler(
        method='auto',
        method_selection=method_selection,
        ar_max_order=ar_max_order,
        strong_ar_threshold=strong_ar_threshold,
        medium_ar_threshold=medium_ar_threshold,
        hp_lambda=hp_lambda,
        decorrelation_strength=decorrelation_strength,
        enable_neutralization=enable_neutralization,
        industry_data=industry_data,
        verbose=verbose
    )
    return decoupler.fit_transform(X)
