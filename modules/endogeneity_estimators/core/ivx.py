# -*- coding: utf-8 -*-
"""IVX 估计器 (Kostakis-Magdalinos-Stamatogiannis 2015, §5.10.3).

v1.3 术语: "IVX 指数衰减滤波" (非分数差分, NOT fractional differencing).

核心思想:
  持久因子 (ρ > 0.9) 的预测回归存在内生性 (Cov(x_t, ε_{t+1}) ≠ 0).
  IVX 通过指数衰减滤波构造工具变量 z_t, 降低持久性, 减少内生性偏倚.

数学 (指数衰减滤波, v1.3 严格对齐 Kostakis et al. 2015):
  z_t = Σ_{j=0}^{t-1} α^{j+1} × x_{t-j}

  α 自适应公式 (Kostakis 2015 原始建议):
    α = 1 - c / max(T^δ, 1.0)
    其中 c=5.0, δ=0.95 为论文建议参数, T 为样本量.

  α 使 z_t "温和持久" (mildly persistent):
    - T=100 → α ≈ 0.937 (温和滤波, 接近 1)
    - T=500 → α ≈ 0.987
    - T→∞  → α → 1 (z_t 接近 x_t, 但仍比 x_t 弱持久)

  β_IVX = (Z'X)^{-1} Z'Y  (IV 估计)

  bias_reduction = |β_OLS - β_IVX|  (IVX 相对 OLS 的偏倚减少量)

注: v1.3 明确不使用分数差分 (fractional differencing), 也不使用因子增强 IVX.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from .base import BaseEndogeneityEstimator


class IVXEstimator(BaseEndogeneityEstimator):
    """IVX 估计器 (Kostakis-Magdalinos-Stamatogiannis 2015, 指数衰减滤波).

    Args:
        alpha: 指数衰减速率 α ∈ (0, 1). None 时自适应 (基于样本量 T).
        c: α = 1 - c/T^δ 中的常数 c (默认 5.0, Kostakis 2015 建议).
        delta: α = 1 - c/T^δ 中的指数 δ (默认 0.95, Kostakis 2015 建议).
    """

    METHOD = 'ivx'
    METHOD_FORMAL = 'IVX (Kostakis-Magdalinos-Stamatogiannis 2015)'

    def __init__(
        self,
        alpha: Optional[float] = None,
        c: float = 5.0,
        delta: float = 0.95,
    ):
        super().__init__()
        self.alpha_input = alpha
        self.c = float(c)
        self.delta = float(delta)
        self._alpha_used: float = 0.95
        self._rho_persistence: float = 0.0

    def _adaptive_alpha(self, T: int) -> float:
        """自适应 α: 基于样本量 T (Kostakis et al. 2015 原始公式).

        α = 1 - c / max(T^δ, 1.0)

        T 大 → α 接近 1 (温和滤波, 保留更多信息, z_t 接近 x_t)
        T 小 → α 较小 (激进滤波, z_t 更外生)

        这使 z_t "温和持久" (mildly persistent), 是 IVX 方法的核心特性.
        """
        T_int = max(int(T), 1)
        alpha = 1.0 - self.c / max(float(T_int) ** self.delta, 1.0)
        return float(np.clip(alpha, 0.01, 0.99))

    def _exponential_filter(self, x: np.ndarray, alpha: float) -> np.ndarray:
        """指数衰减滤波: z_t = Σ_{j=0}^{t-1} α^{j+1} × x_{t-j}.

        这是几何衰减加权移动平均, 非分数差分.
        """
        T = len(x)
        z = np.zeros(T)
        # 向量化: z_t = Σ_{j=0}^{t-1} α^{j+1} x_{t-j}
        weights = alpha ** (np.arange(1, T + 1))  # α^1, α^2, ..., α^T
        for t in range(T):
            j_max = t + 1  # j = 0..t
            w = weights[:j_max][::-1]  # α^{j+1} for j=0..t, reversed to match x_{t-j}
            z[t] = np.dot(w, x[:j_max])
        return z

    def _estimate_rho(self, x: np.ndarray) -> float:
        """估计 AR(1) 系数 ρ (因子持久性)."""
        if len(x) < 2:
            return 0.0
        x_lag = x[:-1]
        x_lead = x[1:]
        denom = np.dot(x_lag, x_lag)
        if abs(denom) < 1e-12:
            return 0.0
        rho = np.dot(x_lag, x_lead) / denom
        return float(np.clip(rho, -1.0, 1.0))

    def _fit_impl(
        self,
        factor_data: pd.DataFrame,
        returns: pd.DataFrame,
        controls: Optional[pd.DataFrame] = None,
    ) -> None:
        F = factor_data.values.astype(float)
        R = returns.values.astype(float)
        T, N = F.shape

        # ── 估计因子持久性 ρ (跨列中位数) ──
        rhos = [self._estimate_rho(F[:, n]) for n in range(min(N, 10))]
        self._rho_persistence = float(np.median(rhos)) if rhos else 0.0

        # ── 确定 α (v1.3: 基于 T, Kostakis 2015 原始公式) ──
        if self.alpha_input is not None:
            self._alpha_used = float(self.alpha_input)
        else:
            self._alpha_used = self._adaptive_alpha(T)
        # 确保 α ∈ (0, 1)
        self._alpha_used = float(np.clip(self._alpha_used, 0.01, 0.999))

        # ── 指数衰减滤波 + IV 估计 ──
        betas_ivx = []
        betas_ols = []
        for n in range(min(N, R.shape[1])):
            x = F[:, n]
            y = R[:, n]
            # IVX 滤波
            z = self._exponential_filter(x, self._alpha_used)
            # IV 估计: β = (Z'X)^{-1} Z'Y
            ZX = np.dot(z, x)
            ZY = np.dot(z, y)
            if abs(ZX) > 1e-12:
                beta_iv = ZY / ZX
            else:
                beta_iv = 0.0
            betas_ivx.append(beta_iv)

            # OLS 估计 (用于 bias_reduction)
            XX = np.dot(x, x)
            if abs(XX) > 1e-12:
                beta_ols = np.dot(x, y) / XX
            else:
                beta_ols = 0.0
            betas_ols.append(beta_ols)

        beta_ivx = float(np.nanmean(betas_ivx)) if betas_ivx else float('nan')
        beta_ols = float(np.nanmean(betas_ols)) if betas_ols else float('nan')

        # bias_reduction
        if not np.isnan(beta_ivx) and not np.isnan(beta_ols):
            bias_reduction = abs(beta_ols - beta_ivx)
        else:
            bias_reduction = 0.0

        # ── 残留威胁 τ ──
        # IVX 降低了内生性, 但残留威胁取决于:
        # 1. 持久性 (ρ 高 → IVX 更有效 → τ 低)
        # 2. bias_reduction (减少多 → τ 低)
        if self._rho_persistence > 0.9:
            tau_base = 0.3  # IVX 对高持久性有效
        elif self._rho_persistence > 0.5:
            tau_base = 0.5
        else:
            tau_base = 0.7  # 低持久性 → IVX 优势不大
        # bias_reduction 越大 → τ 越低
        tau = tau_base * max(0.0, 1.0 - min(bias_reduction, 1.0))
        tau = self._clamp_tau(tau)

        self._diagnostics = {
            'method': self.METHOD,
            'method_formal_name': self.METHOD_FORMAL,
            'beta': beta_ivx,
            'beta_ols': beta_ols,
            'filtering_type': 'exponential_filtering',
            'alpha_decay_rate': self._alpha_used,
            'alpha_c_constant': self.c,
            'alpha_delta_exponent': self.delta,
            'rho_persistence': self._rho_persistence,
            'bias_reduction': float(bias_reduction),
            'factor_augmented_ivx_used': False,
            'residual_threat_tau': tau,
            'n_factors': int(N),
            'n_periods': int(T),
        }

    def get_diagnostics(self) -> Dict[str, Any]:
        return self._diagnostics.copy()

    def get_residual_threat(self) -> float:
        return float(self._diagnostics.get('residual_threat_tau', 1.0))
