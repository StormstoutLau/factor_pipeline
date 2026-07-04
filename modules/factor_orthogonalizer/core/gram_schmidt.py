"""修正 Gram-Schmidt 正交化 (数值稳定版)

数学: 迭代投影
    u_i = f_i - Σ_{j<i} <f_i, q_j> q_j
    q_i = u_i / ||u_i||

顺序依赖: 强 (首因子完全保留, 后续因子被投影)

O1.12.5: re-orthogonalization (Kahan 1966) — κ>100 时二次投影

架构层: Layer 2 (无监督变换)
"""
import numpy as np
from typing import List, Optional
from .base import BaseOrthogonalizer


class GramSchmidtOrthogonalizer(BaseOrthogonalizer):
    """修正 Gram-Schmidt (MGS) 正交化

    Args:
        order: 因子正交化顺序 (默认 [0, 1, ..., K-1])
        reorthogonalize: O1.12.5 — κ>100 时启用二次投影 (默认 False)
    """

    def __init__(
        self,
        order: Optional[List[int]] = None,
        reorthogonalize: bool = False,
    ):
        super().__init__()
        self.order = order
        self.reorthogonalize = reorthogonalize
        self.reorthogonalized_ = False

    def _compute_W(
        self,
        F: np.ndarray,
        order: Optional[List[int]] = None,
        reorthogonalize: bool = None,
        **kwargs
    ) -> np.ndarray:
        """计算变换矩阵 W

        Args (None 时用 self.xxx):
            F: (N, K)
            order: 因子正交化顺序 (默认 [0, 1, ..., K-1])
            reorthogonalize: O1.12.5 — 二次投影

        Returns: W (K, K)
        """
        N, K = F.shape
        order = self.order if order is None else order
        if order is None:
            order = list(range(K))
        elif sorted(order) != list(range(K)):
            raise ValueError(f"order 必须是 [0, ..., {K-1}] 的排列")

        reorthogonalize = self.reorthogonalize if reorthogonalize is None else reorthogonalize

        Q = np.zeros_like(F, dtype=np.float64)
        for i, idx in enumerate(order):
            v = F[:, idx].copy().astype(np.float64)
            # 第一次投影
            for j in range(i):
                v -= np.dot(Q[:, j], F[:, idx]) * Q[:, j]
            # O1.12.5: 二次投影 (re-orthogonalization, Kahan 1966)
            if reorthogonalize:
                for j in range(i):
                    v -= np.dot(Q[:, j], v) * Q[:, j]
            norm = np.linalg.norm(v)
            if norm < 1e-12:
                raise ValueError(
                    f"因子 {idx} 与前 {i} 个因子线性相关, "
                    f"无法构造正交基 (考虑用 Ridge 正交化)"
                )
            Q[:, i] = v / norm

        # W = F^+ Q (伪逆), 使得 F @ W = Q
        W = np.linalg.lstsq(F, Q, rcond=None)[0]
        self.reorthogonalized_ = reorthogonalize
        return W
