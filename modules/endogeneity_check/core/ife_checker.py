# -*- coding: utf-8 -*-
"""交互固定效应检验器 (Bai 2009 IFE).

数学公式 (v1.3 修正: IFE `lambda_i' * F_t`, Bai 2009 标准记号):

    y_it = alpha_i + beta * x_it + lambda_i' * F_t + eps_it

其中 `lambda_i` 是 R×1 个体载荷向量, `F_t` 是 R×1 时间因子向量,
`lambda_i' * F_t` 是标量 (两者交互形成时变不可观测异质性).

注 (v1.3): IFE 吸收内生性而非消除. 残差检查通过 = 交互维度已分离,
不等于内生性已消除.

实现说明: Bai 2009 迭代估计计算成本高, 用 PCA 近似 + Bai-Ng IC 选择 R.
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from .base import BaseEndogeneityChecker


class InteractiveFEChecker(BaseEndogeneityChecker):
    """交互固定效应检验器 (Bai 2009, v1.3 记号: lambda_i' * F_t).

    吸收时变多维因子结构内生性.
    注 (v1.3): IFE 吸收内生性而非消除. 残差检查通过 = 交互维度已分离, 不等于内生性已消除.

    数学: y_it = alpha_i + beta * x_it + lambda_i' * F_t + eps_it
    其中 lambda_i (R×1) 个体载荷, F_t (R×1) 时间因子, lambda_i' * F_t 是标量.
    """

    def __init__(self, max_dim: int = 5, min_t: int = 20, min_n: int = 50):
        self.max_dim = max_dim
        self.min_t = min_t
        self.min_n = min_n

    def fit(
        self,
        factor_data: pd.DataFrame,
        returns: pd.DataFrame,
        controls: Optional[pd.DataFrame] = None,
    ) -> 'InteractiveFEChecker':
        """估计 IFE 模型, 选择最优维度 R."""
        T, N = factor_data.shape
        if T < self.min_t or N < self.min_n:
            self._threat_tau = 0.5
            self._selected_r = 0
            self._warning = f'样本不足 (T={T}<{self.min_t} or N={N}<{self.min_n}), IFE 不可靠'
            return self

        # 简化: 用 PCA 估计因子结构 (Bai 2009 的迭代估计计算成本高, PCA 是近似)
        residual = (factor_data - returns).fillna(0).values
        residual_centered = residual - residual.mean(axis=0)
        U, s, Vt = np.linalg.svd(residual_centered, full_matrices=False)

        # Bai-Ng 信息准则选择 R
        ic_values = []
        max_r = min(self.max_dim, len(s))
        for r in range(1, max_r + 1):
            residual_reconstructed = U[:, :r] @ np.diag(s[:r]) @ Vt[:r, :]
            v_r = np.mean((residual_centered - residual_reconstructed) ** 2)
            g_nt = (N + T) / (N * T) * np.log(1.0 / min(N, T))
            ic_r = np.log(v_r + 1e-10) + r * g_nt
            ic_values.append(ic_r)

        self._selected_r = int(np.argmin(ic_values) + 1) if ic_values else 0

        # 吸收后残差: lambda_i' * F_t (标量, 对每个 (i, t))
        if self._selected_r > 0:
            F_t = U[:, :self._selected_r] @ np.diag(s[:self._selected_r])  # T × R
            lambda_i = Vt[:self._selected_r, :].T  # N × R
            ife_component = lambda_i @ F_t.T  # N × T, 即 lambda_i' * F_t
            residual_after_ife = residual - ife_component.T
            var_before = np.var(residual_centered)
            var_after = np.var(residual_after_ife)
            absorption_ratio = 1.0 - var_after / max(var_before, 1e-10)
            self._threat_tau = float(max(0.0, 1.0 - absorption_ratio))
            self._warning = ''
        else:
            self._threat_tau = 0.8
            self._warning = 'IFE 维度选择为 0, 无法吸收交互结构'

        return self

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            'selected_r': getattr(self, '_selected_r', 0),
            'threat_tau': getattr(self, '_threat_tau', 0.5),
            'warning': getattr(self, '_warning', ''),
            'interpretation': (
                f"IFE (Bai 2009) 选择 R={getattr(self, '_selected_r', 0)}, "
                f"lambda_i' * F_t 吸收交互结构"
            ),
        }

    def get_threat_level(self) -> float:
        return getattr(self, '_threat_tau', 0.5)
