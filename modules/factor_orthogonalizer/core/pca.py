"""PCA 正交化 (主成分分析, 降维场景)

数学: 对协方差矩阵 Σ = F^T F / N 特征值分解
      Σ = V Λ V^T (主成分按方差降序)
      T = (F - mean) V (只保留前 k 个主成分)

性质:
- 全局最优去相关
- 主成分经济意义模糊
- 对因子尺度敏感 (需先标准化)

O1.12.3: center 参数兼容 Layer 1 标准化
O1.12.6: fit_from_gram 支持

架构层: Layer 2 (无监督变换)

sklearn 约定: 算法参数在 __init__ 声明, _compute_W 用 self.xxx 作默认,
              fit(**kwargs) 可临时覆盖。transform 中心化与 fit 一致。
"""
import numpy as np
from typing import Optional
from scipy.linalg import eigh
from .base import BaseOrthogonalizer


class PCAOrthogonalizer(BaseOrthogonalizer):
    """PCA 正交化

    Args:
        n_components: 保留的主成分数 (None 则按 variance_threshold 自动选)
        variance_threshold: 方差保留阈值 (默认 0.95)
        center: O1.12.3 — True 中心化, False 假设已中心化 (默认 True)
    """

    def __init__(
        self,
        n_components: Optional[int] = None,
        variance_threshold: float = 0.95,
        center: bool = True,
    ):
        super().__init__()
        self.n_components = n_components
        self.variance_threshold = variance_threshold
        self.center = center
        self.n_components_ = 0
        self.explained_variance_ratio_ = None
        self.centered_ = center
        # O1.12.3: 中心化均值 (fit 时存储, transform 时使用)
        # fit_from_gram 模式下 mean_ = None (Gram 矩阵不含均值信息)
        self.mean_ = None

    def _compute_W(
        self,
        F: np.ndarray,
        n_components: Optional[int] = None,
        variance_threshold: float = None,
        center: bool = None,
        **kwargs
    ) -> np.ndarray:
        """计算 PCA 变换矩阵

        Args (None 时用 self.xxx):
            F: (N, K)
            n_components: 保留的主成分数 (None 则按 variance_threshold 自动选)
            variance_threshold: 方差保留阈值 (默认 0.95)
            center: O1.12.3 — True 中心化, False 假设已中心化

        Returns: W (K, k) where k <= K
        """
        n_components = self.n_components if n_components is None else n_components
        variance_threshold = self.variance_threshold if variance_threshold is None else variance_threshold
        center = self.center if center is None else center

        # O1.12.3: 中心化兼容
        if center:
            self.mean_ = F.mean(axis=0)
            F_centered = F - self.mean_
        else:
            self.mean_ = None
            F_centered = F

        # 协方差矩阵特征分解
        N = F_centered.shape[0]
        Sigma = (F_centered.T @ F_centered) / N
        eigvals, eigvecs = eigh(Sigma)
        # 降序排列
        idx = np.argsort(eigvals)[::-1]
        eigvals = eigvals[idx]
        eigvecs = eigvecs[:, idx]

        if n_components is None:
            cum_var = np.cumsum(eigvals) / np.sum(eigvals)
            n_components = int(np.searchsorted(cum_var, variance_threshold) + 1)

        W = eigvecs[:, :n_components]
        self.n_components_ = n_components
        self.explained_variance_ratio_ = eigvals[:n_components] / np.sum(eigvals)
        self.centered_ = center
        return W

    def transform(self, F: np.ndarray) -> np.ndarray:
        """应用 PCA 变换: T = (F - mean_) @ W

        O1.12.3: 当 center=True (centered_=True) 且 mean_ 非空时,
                 先中心化 F 再投影, 与 sklearn PCA 行为一致。
        fit_from_gram 模式下 mean_=None, 不中心化。
        """
        if not self.is_fitted_:
            raise RuntimeError("必须先调用 fit()")
        if F.shape[1] != self.W_.shape[0]:
            raise ValueError(
                f"F 的列数 ({F.shape[1]}) 与 W 维度 ({self.W_.shape[0]}) 不匹配"
            )
        if self.centered_ and self.mean_ is not None:
            F = F - self.mean_
        return F @ self.W_

    def _compute_W_from_gram(
        self, G: np.ndarray, n_components: Optional[int] = None,
        variance_threshold: float = None, **kwargs
    ) -> np.ndarray:
        """O1.12.6: 从 Gram 矩阵计算 PCA W

        注意: Gram 矩阵不含均值信息, 无法中心化。
        调用者需保证 G 已是中心化后的 F^T F。
        """
        n_components = self.n_components if n_components is None else n_components
        variance_threshold = self.variance_threshold if variance_threshold is None else variance_threshold

        eigvals, eigvecs = eigh(G)
        idx = np.argsort(eigvals)[::-1]
        eigvals = eigvals[idx]
        eigvecs = eigvecs[:, idx]

        if n_components is None:
            cum_var = np.cumsum(eigvals) / np.sum(eigvals)
            n_components = int(np.searchsorted(cum_var, variance_threshold) + 1)

        W = eigvecs[:, :n_components]
        self.n_components_ = n_components
        self.explained_variance_ratio_ = eigvals[:n_components] / np.sum(eigvals)
        self.centered_ = False  # Gram 矩阵无法中心化
        self.mean_ = None  # Gram 模式无均值信息
        return W
