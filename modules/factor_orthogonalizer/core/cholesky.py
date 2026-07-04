"""Cholesky 分解正交化 (风险模型场景)

数学: Σ = F^T F = L L^T (L 为下三角)
      T = F L^(-T) → T^T T = L^(-1) Σ L^(-T) = I

性质:
- 数值稳定 (需 Σ 正定)
- 顺序依赖 (第一个因子完全保留)
- 比 LU 分解快约 2 倍

不支持 fit_from_gram (需要 F 本身构造 Σ, 但 Gram 矩阵本身就是 Σ, 实际可支持)
但为保持 API 一致性, Cholesky 不支持 fit_from_gram (语义: Cholesky 需要正定保证)

架构层: Layer 2 (无监督变换)
"""
import numpy as np
from scipy.linalg import cholesky, solve_triangular
from .base import BaseOrthogonalizer


class CholeskyOrthogonalizer(BaseOrthogonalizer):
    """Cholesky 分解正交化"""

    def _compute_W(self, F: np.ndarray, **kwargs) -> np.ndarray:
        """计算 W = L^(-T)

        Args:
            F: (N, K)

        Returns: W (K, K)
        """
        Sigma = F.T @ F
        # Cholesky 分解: Σ = L L^T
        try:
            L = cholesky(Sigma, lower=True)
        except np.linalg.LinAlgError:
            raise ValueError(
                "F^T F 非正定, Cholesky 失败. "
                "考虑用 SymmetricOrthogonalizer (特征值截断) 或 RidgeOrthogonalizer"
            )
        # W = L^(-T), 即 solve(L^T, I)
        I = np.eye(F.shape[1])
        W = solve_triangular(L.T, I, lower=False)
        return W
