# -*- coding: utf-8 -*-
"""Profile GMM 估计器 (Hong-Su-Jiang 2022, §5.10.2).

v1.3 正式术语: "Profile GMM" (NNR+GMM 融合, NNR+GMM 为别名).

核心思想:
  1. NNR (Nuclear Norm Regularization): 对因子矩阵做 SVD, 软阈值奇异值,
     吸收共性 (低秩) 结构, 减少维度诅咒下的内生性.
  2. GMM: 在 NNR 残差上用广义矩估计拟合 β, 利用矩条件 E[z_t ε_t] = 0.

数学:
  - F = U S V' (SVD), S_soft = max(S - λ, 0) (软阈值)
  - F_common = U S_soft V' (吸收的共性结构)
  - F_residual = F - F_common (残差, 用于 GMM 估计)
  - absorption_ratio = 1 - ||S_soft||_F / ||S||_F (吸收比例)
  - β_GMM: 在 F_residual 上用 GMM 估计 (矩条件: E[F_res ε] = 0)

残留威胁 τ:
  τ = (1 - absorption_ratio) × min(1, |ρ(ε, F_res)| / threshold)
  absorption 越多 → τ 越低; 残差与因子相关性越低 → τ 越低.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from .base import BaseEndogeneityEstimator


class ProfileGMMEstimator(BaseEndogeneityEstimator):
    """Profile GMM 估计器 (Hong-Su-Jiang 2022).

    NNR (核范数正则化) + GMM 融合:
      - NNR 吸收因子矩阵的共性 (低秩) 结构
      - GMM 在残差上估计 β

    Args:
        nuclear_lambda: 核范数软阈值强度 λ (默认 0.1). λ 大 → 吸收多.
    """

    METHOD = 'profile_gmm'
    METHOD_FORMAL = 'Profile GMM (Hong-Su-Jiang 2022)'
    METHOD_ALIAS = 'NNR+GMM'

    def __init__(self, nuclear_lambda: float = 0.1):
        super().__init__()
        self.nuclear_lambda = float(nuclear_lambda)

    def _fit_impl(
        self,
        factor_data: pd.DataFrame,
        returns: pd.DataFrame,
        controls: Optional[pd.DataFrame] = None,
    ) -> None:
        F = factor_data.values.astype(float)
        R = returns.values.astype(float)
        T, N = F.shape

        # ── Step 1: NNR (核范数正则化) ──
        # SVD of factor matrix
        try:
            U, s_orig, Vt = np.linalg.svd(F, full_matrices=False)
        except np.linalg.LinAlgError:
            # SVD 失败 (数值问题), 降级为单位矩阵
            U = np.eye(min(T, N))
            s_orig = np.ones(min(T, N))
            Vt = np.eye(min(T, N))

        s_orig = np.asarray(s_orig, dtype=float)
        # 软阈值: S_soft = max(S - λ, 0)
        s_soft = np.maximum(s_orig - self.nuclear_lambda, 0.0)

        # 吸收共性结构
        F_common = U @ np.diag(s_soft) @ Vt
        F_residual = F - F_common

        # absorption_ratio: 被吸收的奇异值能量比例
        energy_orig = np.sum(s_orig ** 2)
        energy_soft = np.sum(s_soft ** 2)
        if energy_orig > 1e-12:
            absorption_ratio = 1.0 - energy_soft / energy_orig
        else:
            absorption_ratio = 0.0
        absorption_ratio = float(np.clip(absorption_ratio, 0.0, 1.0))

        # ── Step 2: GMM 估计 β (矩条件: E[F_res ε] = 0) ──
        # 在残差因子上做 pooled OLS (GMM 的同方差特例)
        # R = F_res @ β + ε
        # β = (F_res' F_res)^{-1} F_res' R
        try:
            FtF = F_residual.T @ F_residual
            FtR = F_residual.T @ R
            # 对每个截面 (列) 分别估计, 然后取均值
            beta_per_stock = np.zeros(N)
            for n in range(min(N, R.shape[1])):
                fn = F_residual[:, n] if N == R.shape[1] else F_residual[:, 0]
                rn = R[:, n] if R.shape[1] > n else R[:, 0]
                denom = np.dot(fn, fn)
                if abs(denom) > 1e-12:
                    beta_per_stock[n] = np.dot(fn, rn) / denom
                else:
                    beta_per_stock[n] = 0.0
            beta = float(np.nanmean(beta_per_stock))
        except (np.linalg.LinAlgError, ValueError):
            beta = float('nan')

        # 残差
        if not np.isnan(beta):
            residuals = R - beta * F_residual
            # 残差与因子的相关性 (衡量残留内生性)
            corr = np.corrcoef(F_residual.flatten(), residuals.flatten())[0, 1]
            if np.isnan(corr):
                corr = 0.0
        else:
            residuals = R
            corr = 1.0  # 估计失败 → 高威胁

        # ── 残留威胁 τ ──
        # absorption 越多 → τ 越低; 残差相关性越高 → τ 越高
        tau = (1.0 - absorption_ratio) * 0.5 + abs(corr) * 0.5
        tau = self._clamp_tau(tau)

        self._diagnostics = {
            'method': self.METHOD,
            'method_formal_name': self.METHOD_FORMAL,
            'method_alias': self.METHOD_ALIAS,
            'beta': beta,
            'nuclear_lambda': self.nuclear_lambda,
            'singular_values_original': s_orig,
            'singular_values_soft': s_soft,
            'absorption_ratio': absorption_ratio,
            'residual_threat_tau': tau,
            'n_factors': int(N),
            'n_periods': int(T),
        }

    def get_diagnostics(self) -> Dict[str, Any]:
        return self._diagnostics.copy()

    def get_residual_threat(self) -> float:
        return float(self._diagnostics.get('residual_threat_tau', 1.0))
