# -*- coding: utf-8 -*-
"""正则化 DOLS 估计器 (Stock-Watson 1993, §5.10.4).

核心思想:
  Dynamic OLS (DOLS) 通过加入领先/滞后差分项修正协整回归的内生性.
  正则化版用 ElasticNet (L1+L2) 处理高维 lead-lag 项, 避免过拟合.

数学:
  协整回归: y_t = α + β x_t + Σ_{j=-p}^{p} γ_j Δx_{t-j} + ε_t

  其中 Δx_{t-j} = x_{t-j} - x_{t-j-1} (差分项, j=-p..p, j≠0)
  β 为长期协整系数, γ_j 修正短期动态 (内生性来源)

  正则化: min ||y - α - βx - Σγ_j Δx_{t-j}||^2
            + λ_1 ||γ||_1 + λ_2 ||γ||_2^2

适用条件: 需要协整关系 (Engle-Granger 检验). 无协整 → DOLS 无意义.
"""
from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

from .base import BaseEndogeneityEstimator


class RegularizedDOLSEstimator(BaseEndogeneityEstimator):
    """正则化 DOLS 估计器 (Stock-Watson 1993).

    Args:
        lag_order: 领先/滞后阶数 p (默认 3). 共 2p 个差分项.
        lambda_l1: L1 正则化强度 (默认 0.0, 不正则化)
        lambda_l2: L2 正则化强度 (默认 0.0, 不正则化)
    """

    METHOD = 'dols'
    METHOD_FORMAL = 'Regularized DOLS (Stock-Watson 1993)'

    def __init__(
        self,
        lag_order: int = 3,
        lambda_l1: float = 0.0,
        lambda_l2: float = 0.0,
    ):
        super().__init__()
        self.lag_order = int(lag_order)
        self.lambda_l1 = float(lambda_l1)
        self.lambda_l2 = float(lambda_l2)

    def _adf_test(self, residuals: np.ndarray) -> tuple:
        """ADF 检验 (简化版): 返回 (adf_stat, p_value).

        H0: 单位根 (非平稳)
        H1: 平稳 (协整)
        """
        # 简化 ADF: Δe_t = α + ρ e_{t-1} + ε_t
        # 检验 ρ = 0 (单位根) vs ρ < 0 (平稳)
        e = residuals
        n = len(e)
        if n < 5:
            return 0.0, 1.0  # 样本不足, 不拒绝单位根

        de = np.diff(e)
        e_lag = e[:-1]

        # OLS: de = α + ρ e_lag
        X = np.column_stack([np.ones(n - 1), e_lag])
        try:
            beta = np.linalg.lstsq(X, de, rcond=None)[0]
            rho = beta[1]
            resid = de - X @ beta
            sigma2 = np.var(resid)
            XtX_inv = np.linalg.inv(X.T @ X)
            se_rho = np.sqrt(sigma2 * XtX_inv[1, 1])
            adf_stat = rho / se_rho if se_rho > 1e-12 else 0.0
            # 近似 p-value (大样本, 用正态近似)
            p_value = 2 * (1 - stats.norm.cdf(abs(adf_stat)))
            # ADF 临界值偏移 (MacKinnon), 简化处理
            p_value = float(np.clip(p_value, 0.0, 1.0))
        except (np.linalg.LinAlgError, ValueError):
            adf_stat = 0.0
            p_value = 1.0

        return float(adf_stat), p_value

    def _build_dols_design(
        self, y: np.ndarray, x: np.ndarray, p: int
    ) -> tuple:
        """构造 DOLS 设计矩阵: y_t = α + βx_t + Σγ_j Δx_{t-j} + ε_t.

        Returns:
            (X_design, y_trimmed, n_gamma): 设计矩阵, 因变量, gamma 系数个数
        """
        T = len(y)
        dx = np.diff(x)  # Δx, length T-1

        # 截取有效范围: t = p..T-p-1 (有足够的 lead-lag)
        start = p
        end = T - p
        if end <= start:
            start = 0
            end = T
            return (
                np.column_stack([x, np.ones(T)]),
                y,
                0,
            )

        n_obs = end - start
        cols = [x[start:end]]  # β x_t
        # lead-lag: j = -p..p, j ≠ 0
        gamma_indices: List[int] = []
        for j in range(-p, p + 1):
            if j == 0:
                continue
            # Δx_{t-j}: 需要取 dx 索引 (t-j-1) 到 (t-j-1), 即 x[t-j] - x[t-j-1]
            # dx[t'] = x[t'+1] - x[t'], 所以 Δx_{t-j} = dx[t-j-1]
            col = np.zeros(n_obs)
            for i, t in enumerate(range(start, end)):
                idx = t - j - 1
                if 0 <= idx < len(dx):
                    col[i] = dx[idx]
            cols.append(col)
            gamma_indices.append(j)

        cols.append(np.ones(n_obs))  # 截距
        X_design = np.column_stack(cols)
        y_trimmed = y[start:end]
        n_gamma = len(gamma_indices)

        return X_design, y_trimmed, n_gamma

    def _fit_impl(
        self,
        factor_data: pd.DataFrame,
        returns: pd.DataFrame,
        controls: Optional[pd.DataFrame] = None,
    ) -> None:
        F = factor_data.values.astype(float)
        R = returns.values.astype(float)
        T, N = F.shape

        # ── Step 1: 协整检验 (Engle-Granger 2-step) ──
        # 对每个截面做协整检验, 取中位数 p-value
        p_values = []
        for n in range(min(N, R.shape[1], 10)):
            x = F[:, n]
            y = R[:, n]
            # Step 1: OLS y = α + βx + ε
            X_ols = np.column_stack([x, np.ones(T)])
            try:
                beta_ols = np.linalg.lstsq(X_ols, y, rcond=None)[0]
                resid = y - X_ols @ beta_ols
                # Step 2: ADF 检验残差
                _, pval = self._adf_test(resid)
                p_values.append(pval)
            except (np.linalg.LinAlgError, ValueError):
                p_values.append(1.0)

        coint_pvalue = float(np.median(p_values)) if p_values else 1.0
        is_cointegrated = coint_pvalue < 0.1  # 10% 显著性

        # ── Step 2: DOLS 估计 ──
        betas = []
        gamma_coefs_all = []
        r_squareds = []

        for n in range(min(N, R.shape[1])):
            x = F[:, n]
            y = R[:, n]
            X_design, y_trim, n_gamma = self._build_dols_design(
                y, x, self.lag_order
            )

            if len(y_trim) < X_design.shape[1] + 2:
                betas.append(float('nan'))
                r_squareds.append(float('nan'))
                continue

            try:
                if self.lambda_l1 > 0 or self.lambda_l2 > 0:
                    # ElasticNet 正则化
                    from sklearn.linear_model import ElasticNet
                    l1_ratio = (
                        self.lambda_l1 / (self.lambda_l1 + self.lambda_l2)
                        if (self.lambda_l1 + self.lambda_l2) > 1e-12
                        else 0.5
                    )
                    alpha_en = self.lambda_l1 + self.lambda_l2
                    model = ElasticNet(
                        alpha=alpha_en,
                        l1_ratio=l1_ratio,
                        fit_intercept=False,
                        max_iter=5000,
                    )
                    model.fit(X_design, y_trim)
                    coef = model.coef_
                else:
                    # OLS
                    coef = np.linalg.lstsq(X_design, y_trim, rcond=None)[0]

                beta = float(coef[0])
                betas.append(beta)

                # gamma 系数 (lead-lag)
                if n_gamma > 0:
                    gamma_coefs_all.extend(coef[1:1 + n_gamma].tolist())

                # R²
                y_pred = X_design @ coef
                ss_res = np.sum((y_trim - y_pred) ** 2)
                ss_tot = np.sum((y_trim - np.mean(y_trim)) ** 2)
                if ss_tot > 1e-12:
                    r2 = 1.0 - ss_res / ss_tot
                else:
                    r2 = 0.0
                r_squareds.append(float(np.clip(r2, 0.0, 1.0)))
            except (np.linalg.LinAlgError, ValueError, ImportError):
                betas.append(float('nan'))
                r_squareds.append(float('nan'))

        beta = float(np.nanmean(betas)) if betas else float('nan')
        r_squared = float(np.nanmean(r_squareds)) if r_squareds else float('nan')

        # ── 残留威胁 τ ──
        if is_cointegrated:
            tau = 0.3  # 协整 → DOLS 有效 → 低威胁
            warning = ''
        else:
            tau = 0.8  # 无协整 → DOLS 无意义 → 高威胁
            warning = (
                'DOLS 要求协整关系, 但 Engle-Granger 检验未发现协整 '
                f'(p-value={coint_pvalue:.4f}). DOLS 估计可能无意义, '
                '建议使用 IVX 或 Profile GMM.'
            )
            warnings.warn(warning, UserWarning, stacklevel=2)

        tau = self._clamp_tau(tau)

        self._diagnostics = {
            'method': self.METHOD,
            'method_formal_name': self.METHOD_FORMAL,
            'beta': beta,
            'is_cointegrated': is_cointegrated,
            'cointegration_pvalue': coint_pvalue,
            'warning': warning,
            'lag_order': self.lag_order,
            'gamma_lag_coefficients': gamma_coefs_all,
            'lambda_l1': self.lambda_l1,
            'lambda_l2': self.lambda_l2,
            'r_squared': r_squared,
            'residual_threat_tau': tau,
            'n_factors': int(N),
            'n_periods': int(T),
        }

    def get_diagnostics(self) -> Dict[str, Any]:
        return self._diagnostics.copy()

    def get_residual_threat(self) -> float:
        return float(self._diagnostics.get('residual_threat_tau', 1.0))
