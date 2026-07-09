# -*- coding: utf-8 -*-
"""Lewbel (2012) 内部 IV 构造检验器.

基于非正态异方差构造内部 IV, 不需要传统外生 IV.
适合作为 Oster δ 的辅助验证, 不适合独立使用.

数学 (v1.3 记号): Z_internal = (Z - Z̄) × ê²
其中 ê 为第一阶段回归残差, ê² 为残差平方.

含 Breusch-Pagan 异方差检验 + Sargan-Hansen J 过度识别检验:
  J = n × Q_min, Q_min = (e' P_Z e) / (e' e)
  过度识别 (L > K) 时 J ~ χ²(L - K), L=工具变量数, K=内生变量数.
  判定: J 的 p-value > 0.05 → IV 外生性不拒绝.
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from scipy import stats as scipy_stats
from .base import BaseEndogeneityChecker


class LewbelInternalIVChecker(BaseEndogeneityChecker):
    """Lewbel (2012) 内部 IV 构造检验器.

    基于非正态异方差构造内部 IV, 不需要传统外生 IV.
    适合作为 Oster δ 的辅助验证, 不适合独立使用.

    数学 (v1.3 记号): Z_internal = (Z - Z̄) × ê²
    其中 ê 为第一阶段回归残差, ê² 为残差平方.
    """

    def __init__(self, min_samples: int = 100):
        self.min_samples = min_samples

    def fit(
        self,
        factor_data: pd.DataFrame,
        returns: pd.DataFrame,
        controls: Optional[pd.DataFrame] = None,
    ) -> 'LewbelInternalIVChecker':
        n_total = factor_data.size
        if n_total < self.min_samples:
            self._threat_tau = 0.5
            self._warning = f'样本不足 ({n_total}<{self.min_samples}), Lewbel 不可靠'
            self._bp_pvalue = float('nan')
            self._has_heteroscedasticity = False
            self._beta_ols = float('nan')
            self._beta_iv = float('nan')
            self._sargan_j_stat = float('nan')
            self._sargan_j_pvalue = float('nan')
            self._sargan_j_df = 0
            self._iv_exogeneity_passed = False
            return self

        f_flat = factor_data.values.flatten()
        r_flat = returns.values.flatten()
        valid = ~(np.isnan(f_flat) | np.isnan(r_flat))

        if controls is not None:
            c_values = controls.values
            # 控制变量形状对齐: (T, K) → 广播到 (T*N, K) 以匹配展平的因子
            if c_values.shape[0] == factor_data.shape[0] and c_values.shape[0] != f_flat.shape[0]:
                N = factor_data.shape[1]
                z_flat = np.repeat(c_values, N, axis=0)
            elif controls.ndim == 3:
                z_flat = c_values.reshape(-1, c_values.shape[-1])
            else:
                z_flat = c_values
            z_valid = z_flat[:valid.sum()] if z_flat.shape[0] >= valid.sum() else z_flat
        else:
            z_valid = np.ones((valid.sum(), 1))

        # 第一阶段: Y2 (= factor) 对 Z 回归, 得残差 ê
        X_first = np.column_stack([np.ones(valid.sum()), z_valid])
        beta_first, *_ = np.linalg.lstsq(X_first, f_flat[valid], rcond=None)
        e_hat = f_flat[valid] - X_first @ beta_first
        e_hat_sq = e_hat ** 2

        # Breusch-Pagan 异方差检验
        bp_X = np.column_stack([np.ones(valid.sum()), z_valid[:, 0] if z_valid.ndim > 1 else z_valid])
        bp_test = self._breusch_pagan_test(e_hat, bp_X)

        # 构造内部 IV: Z_internal = (Z - Z̄) × ê² (v1.3 记号)
        z_mean = z_valid.mean(axis=0)
        z_internal = (z_valid - z_mean) * e_hat_sq[:, np.newaxis]

        # 用内部 IV 做 2SLS
        X_endog = np.column_stack([np.ones(valid.sum()), f_flat[valid]])
        try:
            beta_iv_1, *_ = np.linalg.lstsq(z_internal, f_flat[valid], rcond=None)
            f_hat = z_internal @ beta_iv_1
            X_2sls = np.column_stack([np.ones(valid.sum()), f_hat])
            beta_2sls, *_ = np.linalg.lstsq(X_2sls, r_flat[valid], rcond=None)
            beta_iv = beta_2sls[1]

            beta_ols, *_ = np.linalg.lstsq(X_endog, r_flat[valid], rcond=None)
            beta_ols = beta_ols[1]

            diff = abs(beta_ols - beta_iv)
            self._threat_tau = float(min(1.0, diff / max(abs(beta_ols), 1e-10)))
            self._beta_ols = float(beta_ols)
            self._beta_iv = float(beta_iv)

            # Sargan-Hansen J 过度识别检验 (验证内部 IV 外生性)
            # 仅在过度识别 (工具变量数 L > 内生变量数 K) 时有效.
            # J = n * Q_min, Q_min 为 GMM 目标函数最小值;
            # 过度识别时 J ~ χ²(L-K), L=工具变量数, K=内生变量数.
            # 判定: J 的 p-value > 0.05 → 工具变量外生性不能被拒绝.
            n_obs = valid.sum()
            e_2sls = r_flat[valid] - X_2sls @ beta_2sls
            sargan = self._sargan_hansen_j_test(
                e_2sls, z_internal, n_obs, n_endogenous=1
            )
            self._sargan_j_stat = sargan['j_statistic']
            self._sargan_j_pvalue = sargan['j_pvalue']
            self._sargan_j_df = sargan['j_df']
            self._iv_exogeneity_passed = sargan['iv_exogeneity_not_rejected']
            self._warning = ''
        except Exception:
            self._threat_tau = 0.5
            self._warning = 'Lewbel 2SLS 估计失败'
            self._beta_ols = float('nan')
            self._beta_iv = float('nan')
            self._sargan_j_stat = float('nan')
            self._sargan_j_pvalue = float('nan')
            self._sargan_j_df = 0
            self._iv_exogeneity_passed = False

        self._bp_pvalue = float(bp_test.get('pvalue', float('nan')))
        self._has_heteroscedasticity = bool(
            not np.isnan(self._bp_pvalue) and self._bp_pvalue < 0.05
        )
        return self

    def _breusch_pagan_test(self, residuals: np.ndarray, X: np.ndarray) -> Dict[str, float]:
        """Breusch-Pagan 异方差检验."""
        n = len(residuals)
        sigma2 = np.var(residuals)
        if sigma2 < 1e-10:
            return {'statistic': 0.0, 'pvalue': 1.0}
        e_sq = residuals ** 2
        bp_X = np.column_stack([np.ones(n), X[:, 1:] if X.shape[1] > 1 else X])
        try:
            beta_bp, *_ = np.linalg.lstsq(bp_X, e_sq, rcond=None)
            e_sq_pred = bp_X @ beta_bp
            bp_stat = np.sum((e_sq_pred - np.mean(e_sq)) ** 2) / (2 * sigma2 ** 2)
            from scipy.stats import chi2
            pvalue = 1 - chi2.cdf(bp_stat, df=X.shape[1] - 1)
            return {'statistic': float(bp_stat), 'pvalue': float(pvalue)}
        except Exception:
            return {'statistic': float('nan'), 'pvalue': float('nan')}

    def _sargan_hansen_j_test(
        self,
        residuals: np.ndarray,
        instruments: np.ndarray,
        n_obs: int,
        n_endogenous: int = 1,
    ) -> Dict[str, Any]:
        """Sargan-Hansen J 过度识别检验 (验证工具变量外生性).

        数学: J = n * Q_min, 其中 Q_min = (e' P_Z e) / (e' e),
        P_Z = Z (Z' Z)^{-1} Z' 为工具变量投影矩阵.
        过度识别 (L > K) 时 J ~ χ²(L - K), L=工具变量数, K=内生变量数.
        判定: p-value > 0.05 → 工具变量外生性不能被拒绝.

        Args:
            residuals: 2SLS 残差 e
            instruments: 工具变量矩阵 Z (n × L)
            n_obs: 样本数 n
            n_endogenous: 内生变量数 K (默认 1, 即因子本身)

        Returns:
            {'j_statistic', 'j_pvalue', 'j_df', 'iv_exogeneity_not_rejected'}
        """
        L = instruments.shape[1]
        K = n_endogenous
        df = L - K  # 过度识别自由度
        if df <= 0:
            # 恰好识别或不足识别, J 检验不可用
            return {
                'j_statistic': float('nan'),
                'j_pvalue': float('nan'),
                'j_df': 0,
                'iv_exogeneity_not_rejected': True,  # 无过度识别, 默认不拒绝
            }
        try:
            # P_Z = Z (Z' Z)^{-1} Z'
            ZtZ_inv = np.linalg.pinv(instruments.T @ instruments)
            P_Z = instruments @ ZtZ_inv @ instruments.T
            e = residuals
            # Q_min = (e' P_Z e) / (e' e)
            ePe = float(e @ P_Z @ e)
            ee = float(e @ e)
            if ee < 1e-10:
                return {
                    'j_statistic': float('nan'),
                    'j_pvalue': float('nan'),
                    'j_df': df,
                    'iv_exogeneity_not_rejected': True,
                }
            q_min = ePe / ee
            j_stat = n_obs * q_min
            from scipy.stats import chi2
            j_pvalue = float(1 - chi2.cdf(j_stat, df=df))
            return {
                'j_statistic': float(j_stat),
                'j_pvalue': j_pvalue,
                'j_df': int(df),
                'iv_exogeneity_not_rejected': bool(j_pvalue > 0.05),
            }
        except Exception:
            return {
                'j_statistic': float('nan'),
                'j_pvalue': float('nan'),
                'j_df': df,
                'iv_exogeneity_not_rejected': False,
            }

    def get_diagnostics(self) -> Dict[str, Any]:
        bp_pv = getattr(self, '_bp_pvalue', float('nan'))
        has_het = getattr(self, '_has_heteroscedasticity', False)
        sargan_pv = getattr(self, '_sargan_j_pvalue', float('nan'))
        sargan_df = getattr(self, '_sargan_j_df', 0)
        iv_passed = getattr(self, '_iv_exogeneity_passed', False)
        return {
            'beta_ols': getattr(self, '_beta_ols', float('nan')),
            'beta_iv': getattr(self, '_beta_iv', float('nan')),
            'bp_pvalue': bp_pv,
            'has_heteroscedasticity': has_het,
            'sargan_j_statistic': getattr(self, '_sargan_j_stat', float('nan')),
            'sargan_j_pvalue': sargan_pv,
            'sargan_j_df': sargan_df,
            'iv_exogeneity_not_rejected': iv_passed,
            'threat_tau': getattr(self, '_threat_tau', 0.5),
            'warning': getattr(self, '_warning', ''),
            'interpretation': (
                f'Lewbel 内部 IV (Z_internal = (Z - Z̄) × ê²), '
                f'Breusch-Pagan p={bp_pv:.3f}, '
                f'{"异方差显著" if has_het else "无异方差"}, '
                f'Sargan-Hansen J p={sargan_pv:.3f} '
                f'(df={sargan_df}, '
                f'{"IV 外生性不拒绝" if iv_passed else "IV 外生性被拒绝/未检验"})'
            ),
        }

    def get_threat_level(self) -> float:
        return getattr(self, '_threat_tau', 0.5)
