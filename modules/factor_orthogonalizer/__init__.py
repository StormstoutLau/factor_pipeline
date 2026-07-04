"""factor_orthogonalizer — 多因子横截面正交化模块 (v2.5.0, ADR-020)

三层架构 Layer 2: cross-factor 横截面正交化 (无监督变换)

5 种正交化算法:
- Symmetric (Löwdin): 默认主方法, VRR=1, 无顺序依赖
- Ridge: 病态矩阵兜底, λ 自适应 (Ledoit-Wolf 2004)
- PCA: 降维场景, center 参数兼容 Layer 1 标准化
- Gram-Schmidt: 顺序依赖场景, κ>100 启用 Kahan (1966) 二次投影
- Cholesky: 半正定保证场景

学术依据: Löwdin (1950), Ledoit-Wolf (2004), Kahan (1966)
"""

__version__ = "1.0.0"

from factor_pipeline.modules.factor_orthogonalizer.core.base import BaseOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.core.symmetric import SymmetricOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.core.gram_schmidt import GramSchmidtOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.core.pca import PCAOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.core.cholesky import CholeskyOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.core.ridge import RidgeOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.rolling import RollingOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.grouped import GroupedOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.triple_chain import TripleChainCoordinator

__all__ = [
    "BaseOrthogonalizer",
    "SymmetricOrthogonalizer",
    "GramSchmidtOrthogonalizer",
    "PCAOrthogonalizer",
    "CholeskyOrthogonalizer",
    "RidgeOrthogonalizer",
    "RollingOrthogonalizer",
    "GroupedOrthogonalizer",
    "TripleChainCoordinator",
]
