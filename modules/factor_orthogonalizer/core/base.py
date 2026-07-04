"""正交化器抽象基类 — sklearn transformer 风格

架构层: Layer 2 (无监督变换)
接口契约: fit(F) → transform(F) → fit_transform(F)
输入: F ∈ R^(N × K) — N 股票, K 因子 (单期或滚动窗口堆叠)
输出: T ∈ R^(N × K) — 正交化后因子, 同 shape

O1.12.6: fit_from_gram 接口 (RollingOrthogonalizer 优化)
O1.12.7: dtype 强制与内存布局检查
"""
from abc import ABC, abstractmethod
from typing import Optional
import numpy as np


class BaseOrthogonalizer(ABC):
    """所有正交化方法的抽象基类

    子类必须实现:
    - _compute_W(F, **kwargs) → 计算 W ∈ R^(K × K) 变换矩阵
    - transform(F) → 应用 W

    子类可选实现:
    - _compute_W_from_gram(G, **kwargs) → 从 Gram 矩阵计算 W (O1.12.6)

    通用诊断属性 (fit 后填充):
    - W_: 变换矩阵
    - condition_number_: 条件数 κ
    - eigvals_: 特征值 (升序)

    sklearn 约定: 算法参数在 __init__ 声明, _compute_W 用 self.xxx 作默认,
                  fit(**kwargs) 可临时覆盖。
    """

    def __init__(self):
        self.W_ = None
        self.condition_number_ = None
        self.eigvals_ = None
        self.is_fitted_ = False
        self._fitted_from_gram = False

    @abstractmethod
    def _compute_W(self, F: np.ndarray, **kwargs) -> np.ndarray:
        """子类实现: 计算 W ∈ R^(K × K)"""
        pass

    def _compute_W_from_gram(self, G: np.ndarray, **kwargs) -> np.ndarray:
        """子类可选实现: 从 G 计算 W (O1.12.6)

        默认: 抛 NotImplementedError, GS/Cholesky 不支持
        支持: Symmetric/Ridge/PCA (只需 G)
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} 不支持 fit_from_gram, "
            f"仅 Symmetric/Ridge/PCA 支持"
        )

    def fit(self, F: np.ndarray, **kwargs) -> 'BaseOrthogonalizer':
        """拟合变换矩阵 W

        Args:
            F: (N, K) 因子暴露矩阵
            **kwargs: 临时覆盖 __init__ 参数 (传给 _compute_W)

        Returns: self

        O1.12.7: dtype 强制 + C-contiguous 强制
        """
        # O1.12.7: dtype 强制
        if not np.issubdtype(F.dtype, np.floating):
            F = F.astype(np.float64)
        elif F.dtype != np.float64:
            F = F.astype(np.float64)
        # O1.12.7: C-contiguous 强制
        if not F.flags['C_CONTIGUOUS']:
            F = np.ascontiguousarray(F)
        # 形状校验
        if F.ndim != 2:
            raise ValueError(f"F 必须为 2D 数组, 收到 {F.ndim}D")
        if F.shape[0] < F.shape[1]:
            raise ValueError(
                f"N ({F.shape[0]}) < K ({F.shape[1]}), "
                f"样本不足, 无法估计 W"
            )
        self.W_ = self._compute_W(F, **kwargs)
        # 通用诊断
        G = F.T @ F
        self.eigvals_ = np.linalg.eigvalsh(G)
        self.condition_number_ = self.eigvals_[-1] / max(self.eigvals_[0], 1e-12)
        self.is_fitted_ = True
        self._fitted_from_gram = False
        return self

    def fit_from_gram(
        self, G: np.ndarray, n_samples: Optional[int] = None, **kwargs
    ) -> 'BaseOrthogonalizer':
        """从 Gram 矩阵 G = F^T F 直接估计 W (无需 F) (O1.12.6)

        Args:
            G: (K, K) Gram 矩阵 (对称半正定)
            n_samples: 原始样本数 N (用于诊断, 可选)
            **kwargs: 临时覆盖 __init__ 参数

        Returns: self

        注意:
        - 不是所有算法都支持 (GS/Cholesky 需 F 本身, 不支持)
        - Symmetric/Ridge/PCA 支持 (只需 G)
        - RollingOrthogonalizer 的增量更新依赖此接口
        """
        if G.ndim != 2 or G.shape[0] != G.shape[1]:
            raise ValueError(f"G 必须为方阵, 收到 {G.shape}")
        # 对称化 (消除浮点不对称)
        G = (G + G.T) / 2
        G = np.ascontiguousarray(G, dtype=np.float64)
        self.W_ = self._compute_W_from_gram(G, **kwargs)
        self.eigvals_ = np.linalg.eigvalsh(G)
        self.condition_number_ = self.eigvals_[-1] / max(self.eigvals_[0], 1e-12)
        self.is_fitted_ = True
        self._fitted_from_gram = True
        return self

    def transform(self, F: np.ndarray) -> np.ndarray:
        """应用变换: T = F @ W

        Args:
            F: (N, K) 因子暴露矩阵

        Returns: T (N, K) 正交化后因子
        """
        if not self.is_fitted_:
            raise RuntimeError("必须先调用 fit()")
        if F.shape[1] != self.W_.shape[0]:
            raise ValueError(
                f"F 的列数 ({F.shape[1]}) 与 W 维度 ({self.W_.shape[0]}) 不匹配"
            )
        return F @ self.W_

    def fit_transform(self, F: np.ndarray, **kwargs) -> np.ndarray:
        return self.fit(F, **kwargs).transform(F)
