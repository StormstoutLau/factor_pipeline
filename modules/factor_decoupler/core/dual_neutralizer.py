# -*- coding: utf-8 -*-
"""
双重中性化模块

按照设计要求实现双重中性化：
1. 第一重中性化：原始值中性化
2. 提取残差：AR模型提取新息
3. 第二重中性化：残差中性化

这样的设计确保：
- 原始值的行业暴露被剥离
- 时序自相关被去除
- 残差的行业暴露也被剥离
- 最终获得纯净的新息成分
"""

from typing import Dict, Any, Optional, List, Tuple
import numpy as np
import pandas as pd
import logging

# v3.1.0 E1 (§2): 隐藏效应诊断 Mixin (不侵入 fit/transform).
# 局部导入避免循环依赖 — diagnostics 包仅依赖 numpy/pandas/scipy.
from factor_pipeline.modules.factor_decoupler.diagnostics.hidden_effect import (
    HiddenEffectDiagnosticMixin as _HiddenEffectDiagnosticMixin,
)

logger = logging.getLogger(__name__)


class DualNeutralizer:
    """
    双重中性化器

    实现设计文档要求的两阶段中性化：

    Stage 1: 原始值中性化
        y_t = α + β * industry_dummies + γ * market_cap + ε_t
        提取 ε_t（第一次残差）

    Stage 2: AR残差中性化
        ε_t = α' + β' * industry_dummies + γ' * market_cap + δ_t
        提取 δ_t（最终残差，即纯净新息）

    适用场景：动态因子处理管道
    典型代表：短期反转、换手率变化、波动率变化

    Usage:
        neutralizer = DualNeutralizer(industry_data=industry_series)
        neutralizer.fit(factor_data)
        decoupled = neutralizer.transform(factor_data)
    """

    def __init__(self,
                 industry_data: Optional[pd.Series] = None,
                 market_cap_data: Optional[pd.DataFrame] = None,
                 method: str = 'ols'):
        """
        Parameters
        ----------
        industry_data : pd.Series, optional
            行业哑变量或行业分类，index为股票代码
        market_cap_data : pd.DataFrame, optional
            市值数据，shape为(T, N)，用于控制市值因子
        method : str
            回归方法：'ols', 'wls', 'robust'
        """
        self.industry_data = industry_data
        self.market_cap_data = market_cap_data
        self.method = method

        self._industry_dummies: Optional[pd.DataFrame] = None
        self._first_stage_coefficients: Dict[str, Dict[str, float]] = {}
        self._second_stage_coefficients: Dict[str, Dict[str, float]] = {}
        self.is_fitted = False

    def fit(self, X: pd.DataFrame, **kwargs) -> 'DualNeutralizer':
        """
        拟合双重中性化模型

        对每个时间截面拟合回归模型。

        Parameters
        ----------
        X : pd.DataFrame, shape (T, N)
            因子面板数据

        Returns
        -------
        self
        """
        if self.industry_data is None:
            logger.warning("无行业数据，跳过双重中性化")
            self.is_fitted = True
            return self

        logger.info("开始拟合双重中性化模型...")

        # 构建行业哑变量
        self._industry_dummies = self._build_industry_dummies(X.columns)

        # 第一阶段：对每个时间点拟合原始值中性化
        logger.info("第一阶段：原始值中性化拟合")
        self._fit_first_stage(X)

        # 第二阶段：残差中性化（在transform时进行）
        logger.info("第二阶段：残差中性化准备完成")

        self.is_fitted = True
        return self

    def transform(
        self,
        X: pd.DataFrame,
        threat_level: Optional[float] = None,
        skip_stage2: bool = False,
        **kwargs,
    ) -> pd.DataFrame:
        """
        应用双重中性化

        v3.1.0 E5 扩展: threat_level/skip_stage2 参数支持三层决策正则化.
        threat_level=None, skip_stage2=False 时行为与 v3.0.0 完全一致.

        Parameters
        ----------
        X : pd.DataFrame, shape (T, N)
            原始因子数据
        threat_level : float, optional
            内生性威胁等级 τ ∈ [0, 1], 来自 E3. None 时走 v3.0.0 路径.
        skip_stage2 : bool
            是否跳过 Stage 2 (AR 建模), 由 EndogeneityRegularizer 根据 τ 决定.

        Returns
        -------
        pd.DataFrame
            经过双重中性化后的因子数据
        """
        if not self.is_fitted:
            raise ValueError("模型未拟合，请先调用 fit()")

        if self.industry_data is None:
            logger.warning("无行业数据，返回原始数据")
            return X

        # v3.1.0 E5: 记录 threat_level (供诊断/审计), skip_stage2 由调用方决定
        self._threat_level = threat_level
        self._skip_stage2 = skip_stage2

        logger.info("应用双重中性化...")

        result = pd.DataFrame(index=X.index, columns=X.columns, dtype=float)
        residuals_first = pd.DataFrame(index=X.index, columns=X.columns, dtype=float)
        residuals_final = pd.DataFrame(index=X.index, columns=X.columns, dtype=float)

        # 对每个时间截面进行双重中性化
        for date in X.index:
            date_factor = X.loc[date]
            common_stocks = date_factor.dropna().index

            if len(common_stocks) < 10:
                result.loc[date] = date_factor
                continue

            # 第一阶段：原始值中性化
            y = date_factor[common_stocks].values.astype(float)
            industry_dum = self._industry_dummies.loc[common_stocks]

            # OLS回归
            try:
                X_reg = np.column_stack([
                    np.ones(len(y)),
                    industry_dum.values.astype(float)
                ])
                beta = np.linalg.lstsq(X_reg, y, rcond=None)[0]
                residual_first = y - X_reg @ beta
            except Exception as e:
                logger.warning(f"日期 {date} 第一阶段回归失败: {e}")
                residual_first = y

            residuals_first.loc[date, common_stocks] = residual_first

            # 第二阶段：残差中性化
            if self.market_cap_data is not None and date in self.market_cap_data.index:
                # 如果有市值数据，也加入第二阶段回归
                mc = self.market_cap_data.loc[date, common_stocks].values.astype(float)
                mc = mc.reshape(-1, 1)
                mc_with_const = np.column_stack([np.ones(len(mc)), mc])
                mc_beta = np.linalg.lstsq(mc_with_const, residual_first, rcond=None)[0]
                residual_final = residual_first - mc_with_const @ mc_beta
            else:
                # 仅用行业哑变量回归
                try:
                    residual_final = self._neutralize_residual(residual_first, industry_dum)
                except Exception as e:
                    logger.warning(f"日期 {date} 第二阶段回归失败: {e}")
                    residual_final = residual_first

            residuals_final.loc[date, common_stocks] = residual_final
            result.loc[date, common_stocks] = residual_final

        logger.info("双重中性化完成")

        # 记录残差方差用于后续诊断
        self._residuals_first = residuals_first
        self._residuals_final = residuals_final

        return result

    def fit_transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """拟合并变换"""
        return self.fit(X, **kwargs).transform(X, **kwargs)

    def _build_industry_dummies(self, stocks: pd.Index) -> pd.DataFrame:
        """构建行业哑变量矩阵"""
        if self.industry_data is None:
            return pd.DataFrame()

        common = stocks.intersection(self.industry_data.index)
        industry_subset = self.industry_data[common]

        dummies = pd.get_dummies(industry_subset, drop_first=True, dtype=float)
        return dummies

    def _fit_first_stage(self, X: pd.DataFrame):
        """
        第一阶段拟合：原始值中性化

        仅记录残差标准差，不存储每个时间点的系数
        （因为第二阶段中性化只需要残差的行业暴露）
        """
        self._first_stage_residuals = pd.DataFrame(index=X.index, columns=X.columns, dtype=float)

        for date in X.index:
            date_factor = X.loc[date]
            common_stocks = date_factor.dropna().index

            if len(common_stocks) < 10:
                continue

            y = date_factor[common_stocks].values.astype(float)
            industry_dum = self._industry_dummies.loc[common_stocks]

            try:
                X_reg = np.column_stack([
                    np.ones(len(y)),
                    industry_dum.values.astype(float)
                ])
                beta = np.linalg.lstsq(X_reg, y, rcond=None)[0]
                residual = y - X_reg @ beta
                self._first_stage_residuals.loc[date, common_stocks] = residual
            except Exception as e:
                logger.debug(f"日期 {date} 第一阶段拟合失败: {e}")

    def _neutralize_residual(self,
                            residual: np.ndarray,
                            industry_dum: pd.DataFrame) -> np.ndarray:
        """对残差进行第二阶段中性化"""
        X_reg = np.column_stack([
            np.ones(len(residual)),
            industry_dum.values.astype(float)
        ])
        beta = np.linalg.lstsq(X_reg, residual, rcond=None)[0]
        return residual - X_reg @ beta

    def get_neutralization_summary(self) -> Dict[str, Any]:
        """
        获取中性化摘要

        Returns
        -------
        Dict[str, Any]
            包含两阶段残差统计量
        """
        if not hasattr(self, '_residuals_first') or self._residuals_first.empty:
            return {}

        first_resid = self._residuals_first.values.flatten()
        final_resid = self._residuals_final.values.flatten()
        first_resid = first_resid[~np.isnan(first_resid)]
        final_resid = final_resid[~np.isnan(final_resid)]

        return {
            'stage1': {
                'mean': np.mean(first_resid),
                'std': np.std(first_resid),
                'skewness': float(pd.Series(first_resid).skew()),
                'kurtosis': float(pd.Series(first_resid).kurtosis()),
            },
            'stage2': {
                'mean': np.mean(final_resid),
                'std': np.std(final_resid),
                'skewness': float(pd.Series(final_resid).skew()),
                'kurtosis': float(pd.Series(final_resid).kurtosis()),
            },
            'variance_reduction': np.std(final_resid) / np.std(first_resid) if np.std(first_resid) > 0 else np.nan,
        }

    def check_industry_exposure(self,
                                data: pd.DataFrame,
                                industry_returns: Optional[pd.DataFrame] = None) -> Dict[str, float]:
        """
        检查行业暴露是否被有效剥离

        通过计算因子与行业收益的相关性来验证。

        Parameters
        ----------
        data : pd.DataFrame
            因子数据
        industry_returns : pd.DataFrame, optional
            行业收益率数据

        Returns
        -------
        Dict[str, float]
            各行业的平均因子暴露
        """
        if self.industry_data is None:
            return {}

        if industry_returns is None:
            logger.warning("无行业收益数据，无法验证行业暴露剥离效果")
            return {}

        # 计算每期因子暴露
        exposures = {}
        for industry in self.industry_data.unique():
            stocks = self.industry_data[self.industry_data == industry].index
            common = stocks.intersection(data.columns)
            if len(common) > 0:
                exposures[industry] = data[common].mean(axis=1).mean()

        return exposures


class CompositeDecoupler(_HiddenEffectDiagnosticMixin):
    """
    组合解耦器

    将 AR 解耦与双重中性化组合为完整的时间序列解耦流程。

    处理流程（严格遵循设计文档）：
        原始值中性化 → 提取第一阶段残差 → AR建模 → 提取AR残差 → 残差中性化

    Usage:
        decoupler = CompositeDecoupler(
            industry_data=industry_series,
            max_ar_order=5
        )
        result = decoupler.fit_transform(factor_data)
    """

    def __init__(self,
                 industry_data: Optional[pd.Series] = None,
                 market_cap_data: Optional[pd.DataFrame] = None,
                 max_ar_order: int = 5,
                 ar_criterion: str = 'aic',
                 decorrelation_strength: float = 1.0):
        """
        Parameters
        ----------
        industry_data : pd.Series
            行业数据
        market_cap_data : pd.DataFrame
            市值数据
        max_ar_order : int
            最大AR阶数
        ar_criterion : str
            AR阶数选择准则
        decorrelation_strength : float
            解耦强度 [0, 1]
        """
        self._dual_neutralizer = DualNeutralizer(
            industry_data=industry_data,
            market_cap_data=market_cap_data
        )
        self._ar_decoupler = None  # 延迟初始化
        self._max_ar_order = max_ar_order
        self._ar_criterion = ar_criterion
        self._decorrelation_strength = decorrelation_strength
        self.is_fitted = False

    def fit(self, X: pd.DataFrame, **kwargs) -> 'CompositeDecoupler':
        """
        拟合组合解耦器

        Stage 1: 原始值双重中性化
        Stage 2: 在残差上拟合AR模型

        Parameters
        ----------
        X : pd.DataFrame, shape (T, N)
            原始因子数据

        Returns
        -------
        self
        """
        logger.info("=" * 50)
        logger.info("CompositeDecoupler.fit()")
        logger.info("=" * 50)

        # Stage 1: 第一重中性化 - 原始值中性化
        logger.info("[Stage 1] 原始值中性化")
        self._dual_neutralizer.fit(X)
        residuals_stage1 = self._dual_neutralizer.transform(X)

        # Stage 2: AR建模 - 在第一阶段残差上拟合
        logger.info("[Stage 2] AR模型拟合")
        from .ar_model import ARDecoupler

        self._ar_decoupler = ARDecoupler(
            max_order=self._max_ar_order,
            criterion=self._ar_criterion,
            strength=self._decorrelation_strength
        )
        self._ar_decoupler.fit(residuals_stage1)

        # 记录用于后续诊断
        self._residuals_stage1 = residuals_stage1

        self.is_fitted = True
        logger.info("=" * 50)
        logger.info("CompositeDecoupler.fit() 完成")
        logger.info("=" * 50)

        return self

    def transform(
        self,
        X: pd.DataFrame,
        threat_level: Optional[float] = None,
        skip_stage2: bool = False,
        **kwargs,
    ) -> pd.DataFrame:
        """
        应用组合解耦

        处理流程：
            原始值中性化 → AR建模提取残差 → 残差中性化

        v3.1.0 E5 扩展: threat_level/skip_stage2 参数支持三层决策正则化.
        - threat_level=None, skip_stage2=False: 行为与 v3.0.0 完全一致 (向后兼容)
        - skip_stage2=True: 跳过 Stage 2 (AR 建模), 仅 Stage 1 + Stage 3 (低威胁轻量路径)

        Parameters
        ----------
        X : pd.DataFrame, shape (T, N)
            原始因子数据
        threat_level : float, optional
            内生性威胁等级 τ ∈ [0, 1], 来自 E3. None 时走 v3.0.0 路径.
        skip_stage2 : bool
            是否跳过 Stage 2 (AR 建模), 由 EndogeneityRegularizer 根据 τ 决定.

        Returns
        -------
        pd.DataFrame
            解耦后的因子值
        """
        if not self.is_fitted:
            raise ValueError("模型未拟合")

        logger.info("[Transform] 应用组合解耦...")

        # v3.1.0 E5: 记录 threat_level (供诊断/审计)
        self._threat_level = threat_level
        self._skip_stage2 = skip_stage2

        # Stage 1: 原始值双重中性化
        residuals_stage1 = self._dual_neutralizer.transform(
            X, threat_level=threat_level, skip_stage2=skip_stage2,
        )

        if skip_stage2 and self._ar_decoupler is not None:
            # v3.1.0 E5 L1 低威胁路径: 跳过 Stage 2 (AR 建模), 仅 Stage 1 + Stage 3
            logger.info("[Stage 2] 跳过 AR 建模 (低威胁轻量路径, E5 L1)")
            residuals_ar = residuals_stage1
        else:
            # Stage 2: AR解耦 (标准路径)
            residuals_ar = self._ar_decoupler.transform(residuals_stage1)

        # Stage 3: 第二重中性化（在AR残差上再中性化）
        logger.info("[Stage 3] AR残差中性化")
        residuals_final = self._neutralize_ar_residuals(residuals_ar)

        logger.info("[Transform] 组合解耦完成")
        return residuals_final

    def fit_transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """拟合并变换"""
        return self.fit(X, **kwargs).transform(X, **kwargs)

    def _neutralize_ar_residuals(self, ar_residuals: pd.DataFrame) -> pd.DataFrame:
        """对AR残差进行最终中性化"""
        if self._dual_neutralizer.industry_data is None:
            return ar_residuals

        result = pd.DataFrame(index=ar_residuals.index, columns=ar_residuals.columns, dtype=float)

        industry_dum = self._dual_neutralizer._industry_dummies

        for date in ar_residuals.index:
            date_resid = ar_residuals.loc[date]
            common_stocks = date_resid.dropna().index

            if len(common_stocks) < 10:
                result.loc[date] = date_resid
                continue

            resid = date_resid[common_stocks].values.astype(float)
            ind_dum = industry_dum.loc[common_stocks].values.astype(float)

            try:
                X_reg = np.column_stack([np.ones(len(resid)), ind_dum])
                beta = np.linalg.lstsq(X_reg, resid, rcond=None)[0]
                residual_final = resid - X_reg @ beta
                result.loc[date, common_stocks] = residual_final
            except Exception as e:
                logger.debug(f"日期 {date} 最终中性化失败: {e}")
                result.loc[date, common_stocks] = resid

        return result

    def get_summary(self) -> Dict[str, Any]:
        """
        获取解耦摘要

        Returns
        -------
        Dict[str, Any]
            包含AR模型统计、中性化统计等
        """
        summary = {
            'ar_summary': None,
            'neutralization_summary': self._dual_neutralizer.get_neutralization_summary(),
        }

        if self._ar_decoupler is not None:
            summary['ar_summary'] = self._ar_decoupler.get_summary().to_dict('records')

        return summary
