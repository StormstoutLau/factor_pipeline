"""滚动窗口正交化 (避免 look-ahead bias) — Layer 2

子模式 A2: 滚动窗口共享 W
- 用过去 window_size 日的面板估计 W
- 应用到当期截面
- 仅用 t-1 及之前数据, 避免 look-ahead

学术依据: 量化研究实践共识 (回测必须避免 look-ahead bias)
架构层: Layer 2 (无监督变换)

O4.11 工程深化 (v1.1):
- O4.11.1: 增量 Gram 数值漂移与定期重置 (reset_interval)
- O4.11.2: fit_from_gram 对称化 (调用前强制 G = (G+G.T)/2)
- O4.11.3: is_orthogonalized 标记数组 (区分未正交化 vs 正交化=原值)
- O4.11.5: NaN 处理 (nan_to_num, 防止 NaN 传播到 G)
"""
from __future__ import annotations

from collections import deque
from typing import Optional, Tuple

import numpy as np

from .core.symmetric import SymmetricOrthogonalizer


class RollingOrthogonalizer:
    """滚动窗口正交化

    优化: 滑动协方差更新 (增量更新 Gram 矩阵, O(K²) 每次)
    - 移除最旧: G -= F_old.T @ F_old
    - 加入最新: G += F_new.T @ F_new
    - 重新估计 W: eigh(G) (O(K³), 但 K 通常 < 50)

    O4.11.1: 定期重置 (reset_interval) 消除累积浮点误差
    O4.11.3: 返回 (result, is_orthogonalized) 标记数组
    O4.11.5: NaN 处理 (nan_to_num)
    """

    def __init__(
        self,
        window_size: int = 252,
        method: str = 'symmetric',
        min_obs: int = 60,
        reset_interval: int = 500,
    ):
        """
        Args:
            window_size: 滚动窗口大小 (日), 默认 252 (1 年)
            method: 正交化方法 (默认 symmetric, 仅支持 symmetric 走 fit_from_gram 优化路径)
            min_obs: 最小样本数, 不足时跳过 (返回原值)
            reset_interval: 每 N 期重置 Gram 矩阵 (消除累积浮点误差, O4.11.1)
        """
        self.window_size = window_size
        self.method = method
        self.min_obs = min_obs
        self.reset_interval = reset_interval
        self.G_ = None  # 滚动 Gram 矩阵 (K, K)
        self.window_ = deque(maxlen=window_size)
        self.W_ = None  # 当前 W
        self.is_orthogonalized_ = None  # (T,) bool 数组
        self._iter_count = 0

    def fit_transform(
        self, F_panel: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """滚动正交化

        Args:
            F_panel: (T, N, K) 因子面板
                T 期, N 股票, K 因子

        Returns:
            result: (T, N, K) 正交化后因子面板 (或原值, 若未正交化)
            is_orthogonalized: (T,) bool 数组, True 表示该期已正交化

        关键: 用 [t-window, t-1] 数据估计 W_t, 应用到 F_t
              (避免 look-ahead bias)
        """
        T, N, K = F_panel.shape
        result = np.zeros_like(F_panel)
        is_orth = np.zeros(T, dtype=bool)

        for t in range(T):
            # 移除最旧 (窗口满时)
            if len(self.window_) == self.window_size:
                F_old = self.window_[0]  # (N, K)
                self.G_ -= F_old.T @ F_old

            # 加入最新 (用 t-1 数据, 不是 t, 避免 look-ahead)
            if t > 0:
                F_new = F_panel[t - 1].copy()  # (N, K)
                # O4.11.5: NaN 处理 (防止 NaN 传播到 G)
                if np.any(np.isnan(F_new)):
                    F_new = np.nan_to_num(F_new, nan=0.0)
                self.window_.append(F_new)
                if self.G_ is None:
                    self.G_ = F_new.T @ F_new.copy()
                else:
                    self.G_ += F_new.T @ F_new

            self._iter_count += 1

            # O4.11.1: 定期重置 (从 window_ 重新堆叠 G, 消除累积误差)
            if (
                self._iter_count % self.reset_interval == 0
                and len(self.window_) > 0
            ):
                F_window = np.vstack(list(self.window_))
                self.G_ = F_window.T @ F_window

            # 估计 W 并应用
            if len(self.window_) >= self.min_obs:
                if self.method == 'symmetric':
                    orth = SymmetricOrthogonalizer()
                    # O4.11.2: 强制对称化 (消除增量更新的浮点不对称)
                    G_sym = (self.G_ + self.G_.T) / 2
                    orth.fit_from_gram(G_sym)
                    self.W_ = orth.W_
                    result[t] = orth.transform(F_panel[t])
                else:
                    # 其他方法需堆叠 F_window
                    F_window = np.vstack(list(self.window_))
                    orth = self._get_orthogonalizer(self.method)
                    orth.fit(F_window)
                    self.W_ = orth.W_
                    result[t] = orth.transform(F_panel[t])
                is_orth[t] = True
            else:
                # 样本不足, 跳过 (返回原值)
                result[t] = F_panel[t]
                is_orth[t] = False

        self.is_orthogonalized_ = is_orth
        return result, is_orth

    def fit_transform_legacy(self, F_panel: np.ndarray) -> np.ndarray:
        """v1.0 兼容接口: 只返回 result (无 is_orthogonalized)"""
        result, _ = self.fit_transform(F_panel)
        return result

    @staticmethod
    def _get_orthogonalizer(method: str):
        """方法分发: 返回正交化器实例"""
        from .core.gram_schmidt import GramSchmidtOrthogonalizer
        from .core.pca import PCAOrthogonalizer
        from .core.cholesky import CholeskyOrthogonalizer
        from .core.ridge import RidgeOrthogonalizer

        mapping = {
            'symmetric': SymmetricOrthogonalizer,
            'gram_schmidt': GramSchmidtOrthogonalizer,
            'gs': GramSchmidtOrthogonalizer,
            'pca': PCAOrthogonalizer,
            'cholesky': CholeskyOrthogonalizer,
            'ridge': RidgeOrthogonalizer,
        }
        if method not in mapping:
            raise ValueError(
                f"未知 method: {method}, 支持 {list(mapping.keys())}"
            )
        return mapping[method]()
