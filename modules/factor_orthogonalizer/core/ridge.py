"""Ridge 正交化 (soft, 始终数值稳定)

数学: W = (F^T F + λI)^(-1/2)

性质:
- 始终数值稳定 (λ > 0 保证正定)
- 不严格正交 (W^T F^T F W ≈ I, 而非精确 I)
- λ 控制正交化强度 (λ → 0 退化为对称正交化)

O1.12.4: lambda_selection 三模式 (fixed/cv/ledoit_wolf)
O1.12.6: fit_from_gram 支持

学术依据: Ledoit-Wolf (2004) "A well-conditioned estimator for large-dimensional covariance matrices"
架构层: Layer 2 (无监督变换)

sklearn 约定: 算法参数在 __init__ 声明, _compute_W 用 self.xxx 作默认,
              fit(**kwargs) 可临时覆盖。
"""
import numpy as np
from scipy.linalg import eigh
from .base import BaseOrthogonalizer


class RidgeOrthogonalizer(BaseOrthogonalizer):
    """Ridge 正交化 (soft)

    Args:
        lambda_: 正则化参数 (lambda_ > 0, lambda_selection='fixed' 时使用, 默认 1.0)
        lambda_selection: O1.12.4 — 'fixed' / 'cv' / 'ledoit_wolf' (默认 'fixed')
    """

    def __init__(
        self,
        lambda_: float = 1.0,
        lambda_selection: str = 'fixed',
    ):
        super().__init__()
        self.lambda_ = lambda_
        self.lambda_selection = lambda_selection
        # fit 后覆盖为实际使用的值
        self.lambda_used_ = None
        self.lambda_selection_ = None

    def _compute_W(
        self,
        F: np.ndarray,
        lambda_: float = None,
        lambda_selection: str = None,
        **kwargs
    ) -> np.ndarray:
        """计算 W = (F^T F + λI)^(-1/2)

        Args (None 时用 self.xxx):
            F: (N, K)
            lambda_: 正则化参数 (lambda_ > 0, lambda_selection='fixed' 时使用)
            lambda_selection: O1.12.4 — 'fixed' / 'cv' / 'ledoit_wolf'

        Returns: W (K, K)
        """
        # 参数解析 (kwargs 优先于 self)
        lambda_ = self.lambda_ if lambda_ is None else lambda_
        lambda_selection = (
            self.lambda_selection if lambda_selection is None else lambda_selection
        )
        K = F.shape[1]

        if lambda_selection == 'fixed':
            if lambda_ <= 0:
                raise ValueError(f"lambda_ 必须 > 0, 收到 {lambda_}")
            lam = lambda_
        elif lambda_selection == 'cv':
            lam = self._select_lambda_cv(F)
        elif lambda_selection == 'ledoit_wolf':
            lam = self._select_lambda_ledoit_wolf(F)
        else:
            raise ValueError(f"未知 lambda_selection: {lambda_selection}")

        G = F.T @ F + lam * np.eye(K)
        eigvals, eigvecs = eigh(G)
        W = eigvecs @ np.diag(1.0 / np.sqrt(eigvals)) @ eigvecs.T
        self.lambda_used_ = lam
        self.lambda_selection_ = lambda_selection
        # 同步 self.lambda_ 以便外部访问 (例如 ledoit_wolf 选择的 lam)
        self.lambda_ = lam
        return W

    def _select_lambda_cv(self, F: np.ndarray) -> float:
        """O1.12.4: 交叉验证选 λ"""
        from sklearn.linear_model import RidgeCV
        lambdas = [0.01, 0.1, 1.0, 10.0, 100.0]
        ridge_cv = RidgeCV(alphas=lambdas, cv=5)
        ridge_cv.fit(F, F)
        return float(ridge_cv.alpha_)

    def _select_lambda_ledoit_wolf(self, F: np.ndarray) -> float:
        """O1.12.4: Ledoit-Wolf 收缩强度作为 λ"""
        from sklearn.covariance import LedoitWolf
        K = F.shape[1]
        lw = LedoitWolf().fit(F)
        return float(lw.shrinkage_) * np.trace(F.T @ F) / K

    def _compute_W_from_gram(
        self, G: np.ndarray, lambda_: float = None,
        lambda_selection: str = None, **kwargs
    ) -> np.ndarray:
        """O1.12.6: 从 Gram 矩阵计算 Ridge W

        注意: lambda_selection='cv'/'ledoit_wolf' 需要原始 F, 不支持从 Gram 估计。
        从 Gram 调用时强制使用 lambda_selection='fixed'。
        """
        # 参数解析
        lambda_ = self.lambda_ if lambda_ is None else lambda_
        # Gram 模式只支持 fixed (cv/ledoit_wolf 需原始 F)
        if lambda_selection is None:
            lambda_selection = (
                'fixed' if self.lambda_selection in ('cv', 'ledoit_wolf')
                else self.lambda_selection
            )
        # 强制: Gram 模式不支持 cv/ledoit_wolf
        if lambda_selection in ('cv', 'ledoit_wolf'):
            lambda_selection = 'fixed'

        K = G.shape[0]
        if lambda_ <= 0:
            raise ValueError(f"lambda_ 必须 > 0, 收到 {lambda_}")
        G_reg = G + lambda_ * np.eye(K)
        eigvals, eigvecs = eigh(G_reg)
        W = eigvecs @ np.diag(1.0 / np.sqrt(eigvals)) @ eigvecs.T
        self.lambda_used_ = lambda_
        self.lambda_selection_ = 'fixed'  # Gram 模式只支持 fixed
        self.lambda_ = lambda_
        return W
