"""对称正交化 (Löwdin 1950) — 主方法

数学: W = (F^T F)^(-1/2)
     对 G = F^T F 特征值分解 G = V Λ V^T
     W = V Λ^(-1/2) V^T

性质:
- VRR = 1 (完美保留总方差)
- 无顺序依赖 (对所有因子对称)
- 数值稳定 (使用 eigh 对对称矩阵)

O1.12.1: threshold_mode 三模式 (relative/absolute/auto)
O1.12.2: eigh vs svd 选择 (decomposition 参数)
O1.12.6: fit_from_gram 支持

学术依据: Löwdin (1950) The Journal of Chemical Physics
架构层: Layer 2 (无监督变换)
"""
import numpy as np
from scipy.linalg import eigh
from .base import BaseOrthogonalizer


class SymmetricOrthogonalizer(BaseOrthogonalizer):
    """对称正交化 (Löwdin) — 横截面正交化主方法

    Args:
        min_eigval: 特征值截断参数 (默认 1e-10)
        threshold_mode: 'relative' / 'absolute' / 'auto' (O1.12.1, 默认 'auto')
        decomposition: 'eigh' (快) / 'svd' (稳, O1.12.2, 默认 'eigh')
    """

    def __init__(
        self,
        min_eigval: float = 1e-10,
        threshold_mode: str = 'auto',
        decomposition: str = 'eigh',
    ):
        super().__init__()
        self.min_eigval = min_eigval
        self.threshold_mode = threshold_mode
        self.decomposition = decomposition
        self.n_clipped_ = 0

    def _compute_W(
        self,
        F: np.ndarray,
        min_eigval: float = None,
        threshold_mode: str = None,
        decomposition: str = None,
        **kwargs
    ) -> np.ndarray:
        """计算 W = (F^T F)^(-1/2)

        Args (None 时用 self.xxx):
            F: (N, K) 因子暴露矩阵
            min_eigval: 特征值截断参数
            threshold_mode: 'relative' / 'absolute' / 'auto' (O1.12.1)
            decomposition: 'eigh' (快) / 'svd' (稳, O1.12.2)

        Returns: W (K, K)
        """
        # 参数解析 (kwargs 优先于 self)
        min_eigval = self.min_eigval if min_eigval is None else min_eigval
        threshold_mode = self.threshold_mode if threshold_mode is None else threshold_mode
        decomposition = self.decomposition if decomposition is None else decomposition

        if decomposition == 'eigh':
            G = F.T @ F
            eigvals, eigvecs = eigh(G)
            threshold = self._compute_threshold(eigvals, min_eigval, threshold_mode)
            eigvals_clipped = np.maximum(eigvals, threshold)
            W = eigvecs @ np.diag(1.0 / np.sqrt(eigvals_clipped)) @ eigvecs.T
            self.n_clipped_ = int(np.sum(eigvals < threshold))
        elif decomposition == 'svd':
            U, S, Vt = np.linalg.svd(F, full_matrices=False)
            # F = U S V^T, F^T F = V S^2 V^T
            # W = V S^(-1) V^T
            S_threshold = self._compute_threshold(S**2, min_eigval, threshold_mode)
            S_threshold = np.sqrt(S_threshold)
            S_clipped = np.maximum(S, S_threshold)
            W = Vt.T @ np.diag(1.0 / S_clipped) @ Vt
            self.n_clipped_ = int(np.sum(S < S_threshold))
        else:
            raise ValueError(f"未知 decomposition: {decomposition}")

        return W

    def _compute_threshold(
        self, eigvals: np.ndarray, min_eigval: float, threshold_mode: str
    ) -> float:
        """O1.12.1: 计算特征值截断阈值"""
        if threshold_mode == 'relative':
            return eigvals[-1] * min_eigval
        elif threshold_mode == 'absolute':
            return min_eigval
        elif threshold_mode == 'auto':
            return max(eigvals[-1] * min_eigval, 1e-12)
        else:
            raise ValueError(f"未知 threshold_mode: {threshold_mode}")

    def _compute_W_from_gram(
        self, G: np.ndarray, min_eigval: float = None,
        threshold_mode: str = None, **kwargs
    ) -> np.ndarray:
        """O1.12.6: 从 G 直接计算 W = G^(-1/2)"""
        min_eigval = self.min_eigval if min_eigval is None else min_eigval
        threshold_mode = self.threshold_mode if threshold_mode is None else threshold_mode
        eigvals, eigvecs = eigh(G)
        threshold = self._compute_threshold(eigvals, min_eigval, threshold_mode)
        eigvals_clipped = np.maximum(eigvals, threshold)
        self.n_clipped_ = int(np.sum(eigvals < threshold))
        return eigvecs @ np.diag(1.0 / np.sqrt(eigvals_clipped)) @ eigvecs.T
