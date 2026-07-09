# -*- coding: utf-8 -*-
"""PFGMM 估计器 (Ghosh-Thoresen 2019, §5.10.5).

v1.3 正式术语: "PFGMM (Ghosh-Thoresen 2019)".

核心思想:
  Profiled Focused GMM 处理 error-covariate endogeneity
  (Corr(X, ε) ≠ 0), 非弱工具变量 (weak IV) 场景.

  通过 profile 操作将无穷维 nuisance 参数投影到有限维,
  再用 GMM 估计焦点参数 β. 高维场景下用 SCAD/MCP 非凹惩罚实现稀疏.

适用性:
  - A 股适用性低: PFGMM 假设高维工具变量场景, A 股因子数据
    通常不满足假设 (工具变量维度不足, 或 error-covariate 结构不同).
  - 仅理论保留, 实践中降级为 Profile GMM 或 IVX.

注: v1.3 明确 PFGMM 处理 error-covariate 内生, 非 "弱 IV" 场景.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from .base import BaseEndogeneityEstimator


class PFGMMEstimator(BaseEndogeneityEstimator):
    """PFGMM 估计器 (Ghosh-Thoresen 2019).

    Args:
        penalty: 非凹惩罚类型, 'scad' 或 'mcp' (默认 'scad')
        lambda_penalty: 惩罚强度 λ (默认 0.1)
        sparse_dim_threshold: 启用稀疏惩罚的维度阈值 (默认 10)
    """

    METHOD = 'pfgmm'
    METHOD_FORMAL = 'PFGMM (Ghosh-Thoresen 2019)'
    APPLICABILITY = 'low'
    APPLICABILITY_WARNING = (
        'PFGMM 假设高维工具变量场景, A 股因子数据通常不满足假设. '
        '建议降级为 Profile GMM 或 IVX. PFGMM 仅作理论保留.'
    )

    def __init__(
        self,
        penalty: str = 'scad',
        lambda_penalty: float = 0.1,
        sparse_dim_threshold: int = 10,
    ):
        super().__init__()
        self.penalty = penalty.lower()
        self.lambda_penalty = float(lambda_penalty)
        self.sparse_dim_threshold = int(sparse_dim_threshold)

    def _scad_prox(self, x: np.ndarray, lam: float, a: float = 3.7) -> np.ndarray:
        """SCAD 近端算子 (简化版).

        SCAD (Smoothly Clipped Absolute Deviation):
          |x| ≤ λ: soft-threshold by λ
          λ < |x| ≤ aλ: linear taper
          |x| > aλ: no penalty
        """
        result = np.zeros_like(x)
        abs_x = np.abs(x)
        # Region 1: |x| ≤ λ
        mask1 = abs_x <= lam
        result[mask1] = np.sign(x[mask1]) * np.maximum(abs_x[mask1] - lam, 0)
        # Region 2: λ < |x| ≤ aλ
        mask2 = (abs_x > lam) & (abs_x <= a * lam)
        result[mask2] = (
            np.sign(x[mask2])
            * (a * lam * (abs_x[mask2] - lam))
            / ((a - 1) * lam)
        )
        # Region 3: |x| > aλ → no penalty
        mask3 = abs_x > a * lam
        result[mask3] = x[mask3]
        return result

    def _mcp_prox(self, x: np.ndarray, lam: float, gamma: float = 3.0) -> np.ndarray:
        """MCP 近端算子 (简化版).

        MCP (Minimax Concave Penalty):
          |x| ≤ γλ: quadratic taper
          |x| > γλ: no penalty
        """
        result = np.zeros_like(x)
        abs_x = np.abs(x)
        # Region 1: |x| ≤ γλ
        mask1 = abs_x <= gamma * lam
        result[mask1] = (
            np.sign(x[mask1])
            * np.maximum(abs_x[mask1] - lam / gamma, 0)
            * gamma / (gamma - 1 + 1e-12)
        )
        # Region 2: |x| > γλ
        mask2 = abs_x > gamma * lam
        result[mask2] = x[mask2]
        return result

    def _fit_impl(
        self,
        factor_data: pd.DataFrame,
        returns: pd.DataFrame,
        controls: Optional[pd.DataFrame] = None,
    ) -> None:
        F = factor_data.values.astype(float)
        R = returns.values.astype(float)
        T, N = F.shape

        # ── 判断是否启用稀疏惩罚 ──
        sparse_active = N > self.sparse_dim_threshold

        # ── PFGMM 估计 (简化版) ──
        # 1. Profile: 将 nuisance 参数 (截面效应) 投影掉
        #    F_resid = F - F @ (F'F)^{-1} F' F (去共性, 类似 NNR)
        # 2. GMM: 在 profiled 残差上估计 β
        # 3. 若 sparse_active: 用 SCAD/MCP 对 β 做稀疏化

        try:
            # Profile 操作: 去均值 (简化 profile)
            F_centered = F - F.mean(axis=0)
            R_centered = R - R.mean(axis=0)

            # 初始 GMM 估计 (pooled)
            betas_init = np.zeros(N)
            for n in range(min(N, R.shape[1])):
                fn = F_centered[:, n]
                rn = R_centered[:, n]
                denom = np.dot(fn, fn)
                if abs(denom) > 1e-12:
                    betas_init[n] = np.dot(fn, rn) / denom
                else:
                    betas_init[n] = 0.0

            # 稀疏惩罚 (SCAD/MCP)
            if sparse_active and self.lambda_penalty > 0:
                if self.penalty == 'scad':
                    betas_sparse = self._scad_prox(
                        betas_init, self.lambda_penalty
                    )
                elif self.penalty == 'mcp':
                    betas_sparse = self._mcp_prox(
                        betas_init, self.lambda_penalty
                    )
                else:
                    betas_sparse = betas_init
            else:
                betas_sparse = betas_init

            beta = float(np.nanmean(betas_sparse))
            n_zeroed = int(np.sum(np.abs(betas_sparse) < 1e-10))
        except (np.linalg.LinAlgError, ValueError):
            beta = float('nan')
            n_zeroed = 0

        # ── 残留威胁 τ ──
        # PFGMM 处理 error-covariate 内生, 但 A 股适用性低 → τ 较高
        if sparse_active:
            tau = 0.5  # 稀疏惩罚有一定效果
        else:
            tau = 0.7  # 低维 → PFGMM 优势不大
        tau = self._clamp_tau(tau)

        self._diagnostics = {
            'method': self.METHOD,
            'method_formal_name': self.METHOD_FORMAL,
            'beta': beta,
            'penalty': self.penalty,
            'lambda_penalty': self.lambda_penalty,
            'sparse_dim_threshold': self.sparse_dim_threshold,
            'sparse_penalty_active': sparse_active,
            'n_zeroed': n_zeroed,
            'a_stock_applicability': self.APPLICABILITY,
            'applicability_warning': self.APPLICABILITY_WARNING,
            'residual_threat_tau': tau,
            'n_factors': int(N),
            'n_periods': int(T),
        }

    def get_diagnostics(self) -> Dict[str, Any]:
        return self._diagnostics.copy()

    def get_residual_threat(self) -> float:
        return float(self._diagnostics.get('residual_threat_tau', 1.0))
