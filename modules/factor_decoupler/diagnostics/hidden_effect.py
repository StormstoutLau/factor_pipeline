# -*- coding: utf-8 -*-
"""隐藏效应诊断 Mixin (V3.1.0 E1, §2)

时序解耦 (AR / 差分 / HP 滤波) 将水平值内生性**转移**到增量上, 而非**消除**.
AR 残差 η_t 仍包含 X_t 的线性组合:
    η_t = β·(X_t - φ·X_{t-1}) + (u_t - φ·u_{t-1})

本 Mixin 提供 4 类 post-hoc 诊断, 嵌入 CompositeDecoupler / ARDecoupler,
不侵入现有 fit/transform 接口, 仅扩展 diagnose_hidden_effects 方法.

设计要点 (两阶段分离, v1.3 修正):
- **fit 阶段**: 模型估计 (AR 系数 / 滤波参数), 不做 post-hoc 分析.
- **post-hoc 阶段**: 在 fit 完成后调用 diagnose_hidden_effects, 用已估计的
  模型做隐藏效应检测. 本方法调用 self.transform() (复用已拟合模型) 但不修改
  fit 状态.
- 两阶段严格分离: 必须先 fit, 再 diagnose; 不可在 fit 阶段混合 post-hoc 分析.
"""
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats


class HiddenEffectDiagnosticMixin:
    """时序解耦隐藏效应诊断 Mixin (§2).

    嵌入 CompositeDecoupler / ARDecoupler, 提供:
    1. 增量内生性诊断: Cov(η_t, X_t - φ·X_{t-1}) ≠ 0?
    2. 信息损失诊断: IC 衰减比例 (signal_lost / noise_removed / ambiguous)
    3. 平稳性 vs 内生性分离: ADF 通过 ≠ 内生性消除
    4. 方法敏感性: AR / 差分 / HP 滤波 IC 一致性

    不侵入 fit/transform, 仅扩展 diagnose_hidden_effects 诊断方法.
    """

    def diagnose_hidden_effects(
        self,
        factor_data: pd.DataFrame,
        controls: Optional[pd.DataFrame] = None,
        returns: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """时序解耦隐藏效应诊断 (post-hoc, 不修改 self 状态).

        两阶段分离 (v1.3 修正):
        - **fit 阶段**: 模型估计 (AR 系数 / 滤波参数), 不做 post-hoc 分析.
        - **post-hoc 阶段**: 在 fit 完成后调用本方法, 用已估计的模型做隐藏效应
          检测. 本方法调用 self.transform() (复用已拟合模型) 但不修改 fit 状态.
        - 两阶段严格分离: 必须先 fit, 再 diagnose; 不可在 fit 阶段混合 post-hoc 分析.

        Args:
            factor_data: 原始因子数据 (T, N)
            controls: 行业/市值控制变量 (T, N, K), 用于增量内生性检验
            returns: 未来收益 (T, N), 用于 IC 衰减对比

        Returns:
            {
                'incremental_endogeneity': {...},
                'information_loss': {...},
                'stationarity_vs_endogeneity': {...},
                'method_sensitivity': {...},
            }

        Raises (软处理):
            若模型未 fit, 返回各诊断含 'model not fitted' 提示, 不抛异常.
        """
        # 显式 fitted 状态守卫: post-hoc 诊断依赖已拟合的模型参数
        # (ar_coefficients_ / 滤波参数). 未 fit 时各子诊断降级提示.
        is_fitted = (
            getattr(self, 'ar_coefficients_', None) is not None
            or getattr(self, 'fitted_', False)
            or getattr(self, 'is_fitted', False)
        )
        if not is_fitted:
            return {
                'incremental_endogeneity': {
                    'diagnostic': 'model not fitted — 必须先 fit, 再做 post-hoc 诊断 (两阶段分离)',
                    'is_incremental_endogenous': False,
                },
                'information_loss': {
                    'diagnostic': 'model not fitted — transform 不可用, 跳过 IC 衰减诊断',
                    'interpretation': 'undefined',
                },
                'stationarity_vs_endogeneity': {
                    'diagnostic': 'model not fitted — 跳过增量内生性检验',
                    'warning': '必须先 fit, 再做 post-hoc 诊断 (两阶段分离)',
                },
                'method_sensitivity': {
                    'diagnostic': 'model not fitted — transform 不可用, 跳过方法敏感性诊断',
                    'consistency': 'undefined',
                },
            }

        result: Dict[str, Any] = {}
        result['incremental_endogeneity'] = self._diagnose_incremental_endogeneity(
            factor_data, controls
        )
        result['information_loss'] = self._diagnose_information_loss(
            factor_data, returns
        )
        result['stationarity_vs_endogeneity'] = (
            self._diagnose_stationarity_vs_endogeneity(factor_data, controls)
        )
        result['method_sensitivity'] = self._diagnose_method_sensitivity(
            factor_data, returns
        )
        return result

    # ------------------------------------------------------------------
    # 诊断 1: 增量内生性
    # ------------------------------------------------------------------

    def _diagnose_incremental_endogeneity(
        self,
        factor_data: pd.DataFrame,
        controls: Optional[pd.DataFrame],
    ) -> Dict[str, Any]:
        """诊断 1: 增量内生性 — AR 残差是否仍包含 X_t 的变换.

        数学: η_t = f_t - φ·f_{t-1}; ΔX_t = X_t - φ·X_{t-1}
        检验: Cov(η_t, ΔX_t) ≠ 0? (t 检验 p < 0.05)
        """
        if controls is None:
            return {
                'cov_eta_delta_X': float('nan'),
                'is_incremental_endogenous': False,
                'diagnostic': 'no controls provided',
            }

        phi = getattr(self, 'ar_coefficients_', None)
        if phi is None:
            # 回退: 用 ARDecoupler / CompositeDecoupler 拟合结果估计 φ
            phi = self._estimate_ar_phi()

        if phi is None:
            return {
                'cov_eta_delta_X': float('nan'),
                'is_incremental_endogenous': False,
                'diagnostic': 'AR model not fitted',
            }

        phi_1 = phi[0] if hasattr(phi, '__len__') else phi

        factor_arr = np.asarray(factor_data.values, dtype=float)
        eta = factor_arr[1:] - phi_1 * factor_arr[:-1]

        controls_arr = (
            controls.values if hasattr(controls, 'values') else np.asarray(controls)
        )
        controls_arr = np.asarray(controls_arr, dtype=float)
        delta_x = controls_arr[1:] - phi_1 * controls_arr[:-1]

        # 对齐列数 (factor vs controls)
        if eta.ndim == 2 and delta_x.ndim == 2:
            n_min = min(eta.shape[1], delta_x.shape[1])
            eta_aligned = eta[:, :n_min]
            delta_x_aligned = delta_x[:, :n_min]
        else:
            eta_aligned = eta
            delta_x_aligned = delta_x

        covs = []
        if eta_aligned.ndim == 2 and delta_x_aligned.ndim == 2:
            n_cols = eta_aligned.shape[1]
            for j in range(n_cols):
                valid = ~(
                    np.isnan(eta_aligned[:, j]) | np.isnan(delta_x_aligned[:, j])
                )
                if valid.sum() < 10:
                    continue
                cov_j = np.cov(
                    eta_aligned[valid, j], delta_x_aligned[valid, j]
                )[0, 1]
                covs.append(float(cov_j))
        else:
            valid = ~(np.isnan(eta_aligned) | np.isnan(delta_x_aligned))
            if valid.sum() >= 10:
                covs.append(float(np.cov(eta_aligned[valid], delta_x_aligned[valid])[0, 1]))

        if not covs:
            return {
                'cov_eta_delta_X': float('nan'),
                'is_incremental_endogenous': False,
                'diagnostic': 'insufficient valid samples',
            }

        cov_mean = float(np.mean(covs))
        t_stat, p_value = scipy_stats.ttest_1samp(covs, 0.0)
        is_endogenous = bool(p_value < 0.05 and abs(cov_mean) > 1e-6)

        return {
            'cov_eta_delta_X': cov_mean,
            't_statistic': float(t_stat),
            'p_value': float(p_value),
            'is_incremental_endogenous': is_endogenous,
            'diagnostic': (
                'incremental_endogeneity_detected'
                if is_endogenous
                else 'no_incremental_endogeneity'
            ),
        }

    # ------------------------------------------------------------------
    # 诊断 2: 信息损失 (IC 衰减)
    # ------------------------------------------------------------------

    def _diagnose_information_loss(
        self,
        factor_data: pd.DataFrame,
        returns: Optional[pd.DataFrame],
    ) -> Dict[str, Any]:
        """诊断 2: 信息损失 — 解耦前后 IC 衰减比例.

        ic_decay_ratio = IC_after / IC_before
        - > 0.9: noise_removed (解耦几乎无损信号)
        - < 0.5: signal_lost (解耦丢失信号)
        - 其他: ambiguous
        """
        if returns is None:
            return {
                'ic_before': float('nan'),
                'ic_after': float('nan'),
                'ic_decay_ratio': float('nan'),
                'interpretation': 'no returns provided',
            }

        ic_before = self._compute_cross_sectional_ic_mean(factor_data, returns)

        try:
            decoupled = self.transform(factor_data)
            ic_after = self._compute_cross_sectional_ic_mean(decoupled, returns)
        except Exception:
            return {
                'ic_before': ic_before,
                'ic_after': float('nan'),
                'ic_decay_ratio': float('nan'),
                'interpretation': 'transform failed',
            }

        if (
            abs(ic_before) < 1e-10
            or np.isnan(ic_before)
            or np.isnan(ic_after)
        ):
            ratio = float('nan')
            interpretation = 'undefined'
        else:
            ratio = float(ic_after / ic_before)
            if ratio > 0.9:
                interpretation = 'noise_removed'
            elif ratio < 0.5:
                interpretation = 'signal_lost'
            else:
                interpretation = 'ambiguous'

        return {
            'ic_before': float(ic_before),
            'ic_after': float(ic_after),
            'ic_decay_ratio': ratio,
            'interpretation': interpretation,
        }

    # ------------------------------------------------------------------
    # 诊断 3: 平稳性 vs 内生性分离
    # ------------------------------------------------------------------

    def _diagnose_stationarity_vs_endogeneity(
        self,
        factor_data: pd.DataFrame,
        controls: Optional[pd.DataFrame],
    ) -> Dict[str, Any]:
        """诊断 3: 平稳性 vs 内生性分离 — ADF 通过 ≠ 内生性消除.

        陷阱识别: adf_passes=True 且 endogeneity_present=True
                  → 输出警告 "ADF 通过 ≠ 内生性消除".
        """
        from statsmodels.tsa.stattools import adfuller

        factor_mean = factor_data.mean(axis=1).dropna()
        if len(factor_mean) < 20:
            return {
                'adf_pvalue': float('nan'),
                'adf_passes': False,
                'endogeneity_present': False,
                'warning': 'insufficient samples',
            }

        try:
            adf_stat, adf_pvalue, *_ = adfuller(factor_mean, autolag='AIC')
            adf_passes = bool(adf_pvalue < 0.05)
        except Exception:
            return {
                'adf_pvalue': float('nan'),
                'adf_passes': False,
                'endogeneity_present': False,
                'warning': 'ADF test failed',
            }

        endogeneity_present = False
        if controls is not None:
            inc = self._diagnose_incremental_endogeneity(factor_data, controls)
            endogeneity_present = inc.get('is_incremental_endogenous', False)

        if adf_passes and endogeneity_present:
            warning = 'ADF 通过 ≠ 内生性消除 — 平稳序列可能仍有内生性'
        elif adf_passes and not endogeneity_present:
            warning = 'ADF 通过且无增量内生性 — 解耦有效'
        else:
            warning = 'ADF 未通过 — 序列仍非平稳'

        return {
            'adf_pvalue': float(adf_pvalue),
            'adf_statistic': float(adf_stat),
            'adf_passes': adf_passes,
            'endogeneity_present': endogeneity_present,
            'warning': warning,
        }

    # ------------------------------------------------------------------
    # 诊断 4: 方法敏感性
    # ------------------------------------------------------------------

    def _diagnose_method_sensitivity(
        self,
        factor_data: pd.DataFrame,
        returns: Optional[pd.DataFrame],
    ) -> Dict[str, Any]:
        """诊断 4: 方法敏感性 — AR / 差分 / HP 滤波 IC 一致性.

        cv = std / mean of [ar_ic, diff_ic, hp_ic]
        - cv < 0.2: high
        - cv < 0.5: medium
        - 其他:    low
        """
        if returns is None:
            return {
                'ar_ic': float('nan'),
                'diff_ic': float('nan'),
                'hp_ic': float('nan'),
                'consistency': 'undefined',
            }

        try:
            ar_decoupled = self.transform(factor_data)
            ar_ic = self._compute_cross_sectional_ic_mean(ar_decoupled, returns)
        except Exception:
            ar_ic = float('nan')

        diff_decoupled = factor_data.diff().dropna()
        diff_ic = self._compute_cross_sectional_ic_mean(diff_decoupled, returns)

        try:
            from statsmodels.tsa.filters.hp_filter import hpfilter

            hp_decoupled = factor_data.apply(
                lambda col: (
                    hpfilter(col.dropna(), lamb=1600)[1]
                    if len(col.dropna()) > 20
                    else col
                ),
                axis=0,
            )
            hp_ic = self._compute_cross_sectional_ic_mean(hp_decoupled, returns)
        except Exception:
            hp_ic = float('nan')

        ics = [v for v in [ar_ic, diff_ic, hp_ic] if not np.isnan(v)]
        if len(ics) < 2:
            consistency = 'undefined'
        else:
            mean_ic = float(np.mean(ics))
            cv = float(np.std(ics) / max(abs(mean_ic), 1e-10))
            if cv < 0.2:
                consistency = 'high'
            elif cv < 0.5:
                consistency = 'medium'
            else:
                consistency = 'low'

        return {
            'ar_ic': float(ar_ic),
            'diff_ic': float(diff_ic),
            'hp_ic': float(hp_ic),
            'consistency': consistency,
        }

    # ------------------------------------------------------------------
    # IC 计算 (Spearman 秩相关)
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_cross_sectional_ic_mean(
        factor: pd.DataFrame,
        returns: pd.DataFrame,
    ) -> float:
        """计算截面 IC 均值 (Spearman 秩相关)."""
        n_periods = factor.shape[0]
        ics = []
        for t in range(n_periods):
            f_t = factor.iloc[t]
            r_t = returns.iloc[t]
            valid = ~(f_t.isna() | r_t.isna())
            if valid.sum() < 5:
                continue
            corr, _ = scipy_stats.spearmanr(f_t[valid], r_t[valid])
            if not np.isnan(corr):
                ics.append(corr)
        return float(np.mean(ics)) if ics else float('nan')

    # ------------------------------------------------------------------
    # 辅助: 从已拟合模型估计 AR(1) 系数 φ
    # ------------------------------------------------------------------

    def _estimate_ar_phi(self) -> Optional[Any]:
        """从宿主解耦器的已拟合结果中提取 AR(1) 系数 φ.

        兼容多种解耦器内部存储:
        - ARDecoupler: self._results[col].coefficients (含截距, phi_1 在 index 1)
        - CompositeDecoupler: self._ar_decoupler._results (嵌套)
        """
        # 直接属性 (统一接口, 由宿主在 fit 时设置)
        phi = getattr(self, 'ar_coefficients_', None)
        if phi is not None:
            return phi

        # ARDecoupler 内部存储: _results: Dict[col, ARModelResult]
        results = getattr(self, '_results', None)
        if results:
            phis = []
            for col, res in results.items():
                coeffs = getattr(res, 'coefficients', None)
                if coeffs is None:
                    continue
                # ARModelResult.coefficients = [intercept, phi_1, phi_2, ...]
                # 见 ar_model.py _fit_ar
                arr = np.asarray(coeffs).flatten()
                if arr.size >= 2:
                    phis.append(float(arr[1]))
            if phis:
                return [float(np.mean(phis))]

        # CompositeDecoupler: 嵌套 _ar_decoupler
        nested = getattr(self, '_ar_decoupler', None)
        if nested is not None:
            nested_results = getattr(nested, '_results', None)
            if nested_results:
                phis = []
                for col, res in nested_results.items():
                    coeffs = getattr(res, 'coefficients', None)
                    if coeffs is None:
                        continue
                    arr = np.asarray(coeffs).flatten()
                    if arr.size >= 2:
                        phis.append(float(arr[1]))
                if phis:
                    return [float(np.mean(phis))]

        return None
