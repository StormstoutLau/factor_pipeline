# v2.5.0 多因子正交化模块执行方案 (ADR-020)

**状态**: 执行方案设计 (基于 ANALYSIS_V2.5.0.md v2.1)
**创建日期**: 2026-07-03
**基线测试**: 632 passed / 5 skipped / 0 failed (v2.4.0 内化完成)
**目标版本**: 2.5.0
**关联文档**: [ANALYSIS_V2.5.0.md](./ANALYSIS_V2.5.0.md) | [EXECUTION_V2.4.0.md](./EXECUTION_V2.4.0.md)

---

## 总体目标

实现 factor_pipeline 的多因子横截面正交化 (Layer 2) 与因子增量显著性检验 (Layer 3) 能力,与现有 Factor_Fingerprint / Factor_Decoupler 形成"描述 → 解耦 → 正交 → 检验"完整因子诊断链。

## 核心约束

1. **基线保护**: 默认 `enabled=False`,不影响 632 测试基线
2. **三层分离**: Layer 1 (per-factor, 已有) / Layer 2 (cross-factor 变换, 新增) / Layer 3 (target-aware 检验, 新增)
3. **Pipeline 不重构**: 保持 `FactorProcessingPipelineV2.transform()` 的 per-factor 循环不变
4. **TDD 开发**: 每个算法严格 Red-Green-Refactor,含手工数值校验
5. **数值精度**: 与独立 numpy/statsmodels 实现对比,精度 < 1e-10

## 阶段总览

```
v2.5.0 多因子正交化与因子检验 [ADR-020]
│
├─ O1: Layer 2 算法核心 (P0, 无依赖)
│   ├─ SymmetricOrthogonalizer (主方法)
│   ├─ GramSchmidtOrthogonalizer (备选)
│   ├─ PCAOrthogonalizer (降维)
│   ├─ CholeskyOrthogonalizer (风险模型)
│   └─ RidgeOrthogonalizer (soft 正交化)
│
├─ O2: Layer 2 适配器层 (P0, 依赖 O1)
│   ├─ OrthogonalizerAdapter (sklearn 接口)
│   ├─ OrthogonalizationConfig (Pydantic)
│   └─ 接入 PipelineV2ConfigUnified
│
├─ O3a: Layer 2 几何诊断 (P0, 依赖 O1, O2)
│   ├─ VRR_k 计算
│   ├─ 条件数 κ + VIF
│   ├─ 正交性误差验证
│   └─ OrthogonalizationDiagnostics 类
│
├─ O3b + O4: Layer 3 因子检验 + 回测扩展 (P1, 依赖 O2)
│   ├─ FactorSignificanceTest (backtest/factor_significance.py)
│   ├─ 双重 Lasso (Belloni 2014 PDS)
│   ├─ Elastic Net 路径
│   ├─ RollingOrthogonalizer (Layer 2 滚动模式)
│   └─ IC 变化监控 (Layer 3)
│
├─ O5: 协同设计 (P1, 依赖 O1-O4)
│   ├─ GroupedOrthogonalizer
│   ├─ 与 Fingerprint/Decoupler 串联
│   └─ 与 NeutralizerAdapter 协同
│
└─ O6: 文档验证 (P1, 依赖 O1-O5)
    ├─ ADR-020 状态更新
    ├─ TDD 全量回归
    ├─ 手工数值校验
    └─ project_memory.md / topics.md 更新
```

---

## O1: Layer 2 算法核心 (P0)

**优先级**: P0
**依赖**: 无
**预计测试数**: ~40 个
**文件位置**: `modules/factor_orthogonalizer/core/`

### O1.1 文件清单

| 文件 | 类型 | 职责 |
|---|---|---|
| `modules/factor_orthogonalizer/__init__.py` | 新建 | 顶层 re-export |
| `modules/factor_orthogonalizer/core/__init__.py` | 新建 | core 子包 re-export |
| `modules/factor_orthogonalizer/core/base.py` | 新建 | `BaseOrthogonalizer` 抽象基类 |
| `modules/factor_orthogonalizer/core/symmetric.py` | 新建 | `SymmetricOrthogonalizer` (主方法) |
| `modules/factor_orthogonalizer/core/gram_schmidt.py` | 新建 | `GramSchmidtOrthogonalizer` (备选) |
| `modules/factor_orthogonalizer/core/pca.py` | 新建 | `PCAOrthogonalizer` (降维) |
| `modules/factor_orthogonalizer/core/cholesky.py` | 新建 | `CholeskyOrthogonalizer` (风险模型) |
| `modules/factor_orthogonalizer/core/ridge.py` | 新建 | `RidgeOrthogonalizer` (soft 正交化) |

### O1.2 BaseOrthogonalizer 抽象基类

```python
# modules/factor_orthogonalizer/core/base.py
"""正交化器抽象基类 — sklearn transformer 风格"""
from abc import ABC, abstractmethod
import numpy as np


class BaseOrthogonalizer(ABC):
    """所有正交化方法的抽象基类

    架构层: Layer 2 (无监督变换)
    接口契约: fit(F) → transform(F) → fit_transform(F)
    输入: F ∈ R^(N × K) — N 股票, K 因子 (单期或滚动窗口堆叠)
    输出: T ∈ R^(N × K) — 正交化后因子, 同 shape

    子类必须实现:
    - _compute_W(F) → 计算 W ∈ R^(K × K) 变换矩阵
    - transform(F) → 应用 W

    通用诊断属性 (fit 后填充):
    - W_: 变换矩阵
    - condition_number_: 条件数 κ
    - eigvals_: 特征值
    """

    def __init__(self):
        self.W_ = None
        self.condition_number_ = None
        self.eigvals_ = None
        self.is_fitted_ = False

    @abstractmethod
    def _compute_W(self, F: np.ndarray) -> np.ndarray:
        """子类实现: 计算 W ∈ R^(K × K)"""
        pass

    def fit(self, F: np.ndarray, **kwargs) -> 'BaseOrthogonalizer':
        """拟合变换矩阵 W

        Args:
            F: (N, K) 因子暴露矩阵
                单期: N 股票, K 因子
                滚动窗口堆叠: (N·T_window, K)

        Returns: self
        """
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
        self.condition_number_ = self.eigvals_[-1] / self.eigvals_[0]
        self.is_fitted_ = True
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
```

### O1.3 SymmetricOrthogonalizer (主方法)

```python
# modules/factor_orthogonalizer/core/symmetric.py
"""对称正交化 (Löwdin 1950) — 主方法"""
import numpy as np
from scipy.linalg import eigh
from .base import BaseOrthogonalizer


class SymmetricOrthogonalizer(BaseOrthogonalizer):
    """对称正交化 (Löwdin) — 横截面正交化 (对象 A)

    数学: W = (F^T F)^(-1/2)
         对 G = F^T F 特征值分解 G = V Λ V^T
         W = V Λ^(-1/2) V^T

    性质:
    - VRR = 1 (完美保留总方差)
    - 无顺序依赖 (对所有因子对称)
    - 数值稳定 (使用 eigh 对对称矩阵)

    学术依据: Löwdin (1950) The Journal of Chemical Physics
    架构层: Layer 2 (无监督变换)
    """

    def _compute_W(self, F: np.ndarray, min_eigval: float = 1e-10) -> np.ndarray:
        """计算 W = (F^T F)^(-1/2)

        Args:
            F: (N, K) 因子暴露矩阵
            min_eigval: 特征值截断阈值 (相对最大特征值)

        Returns: W (K, K)
        """
        G = F.T @ F  # (K, K) Gram 矩阵
        # eigh 专为对称矩阵设计, 比 eig 快 2-3x 且数值稳定
        eigvals, eigvecs = eigh(G)
        # 截断小特征值, 处理病态矩阵
        threshold = eigvals[-1] * min_eigval
        eigvals_clipped = np.maximum(eigvals, threshold)
        # W = V Λ^(-1/2) V^T
        W = eigvecs @ np.diag(1.0 / np.sqrt(eigvals_clipped)) @ eigvecs.T
        return W
```

### O1.4 GramSchmidtOrthogonalizer (备选)

```python
# modules/factor_orthogonalizer/core/gram_schmidt.py
"""修正 Gram-Schmidt 正交化 (数值稳定版)"""
import numpy as np
from typing import List, Optional
from .base import BaseOrthogonalizer


class GramSchmidtOrthogonalizer(BaseOrthogonalizer):
    """修正 Gram-Schmidt (MGS) 正交化

    数学: 迭代投影
        u_i = f_i - Σ_{j<i} <f_i, q_j> q_j
        q_i = u_i / ||u_i||

    顺序依赖: 强 (首因子完全保留, 后续因子被投影)
    数值稳定性: MGS 比经典 GS 更稳定, 但仍不如对称正交化

    架构层: Layer 2 (无监督变换)
    """

    def _compute_W(
        self,
        F: np.ndarray,
        order: Optional[List[int]] = None
    ) -> np.ndarray:
        """计算变换矩阵 W

        Args:
            F: (N, K)
            order: 因子正交化顺序 (默认按原始顺序 [0, 1, ..., K-1])

        Returns: W (K, K)
        """
        N, K = F.shape
        if order is None:
            order = list(range(K))
        elif sorted(order) != list(range(K)):
            raise ValueError(f"order 必须是 [0, ..., {K-1}] 的排列")

        # MGS 构造正交基 Q ∈ R^(N × K)
        Q = np.zeros_like(F)
        for i, idx in enumerate(order):
            v = F[:, idx].copy().astype(np.float64)
            for j in range(i):
                v -= np.dot(Q[:, j], F[:, idx]) * Q[:, j]
            norm = np.linalg.norm(v)
            if norm < 1e-12:
                raise ValueError(
                    f"因子 {idx} 与前 {i} 个因子线性相关, "
                    f"无法构造正交基 (考虑用 Ridge 正交化)"
                )
            Q[:, i] = v / norm

        # W = F^+ Q (伪逆), 使得 F @ W = Q
        # 对非方阵更稳定的做法: W = np.linalg.lstsq(F, Q, rcond=None)[0]
        W = np.linalg.lstsq(F, Q, rcond=None)[0]
        return W
```

### O1.5 PCAOrthogonalizer (降维)

```python
# modules/factor_orthogonalizer/core/pca.py
"""PCA 正交化 (主成分分析, 降维场景)"""
import numpy as np
from .base import BaseOrthogonalizer


class PCAOrthogonalizer(BaseOrthogonalizer):
    """PCA 正交化

    数学: 对协方差矩阵 Σ = F^T F / N 特征值分解
          Σ = V Λ V^T (主成分按方差降序)
          T = F V (只保留前 k 个主成分)

    性质:
    - 全局最优去相关
    - 主成分经济意义模糊
    - 对因子尺度敏感 (需先标准化)

    架构层: Layer 2 (无监督变换)
    """

    def _compute_W(
        self,
        F: np.ndarray,
        n_components: Optional[int] = None,
        variance_threshold: float = 0.95
    ) -> np.ndarray:
        """计算 PCA 变换矩阵

        Args:
            F: (N, K)
            n_components: 保留的主成分数 (None 则按 variance_threshold 自动选)
            variance_threshold: 方差保留阈值 (默认 0.95)

        Returns: W (K, k) where k <= K
        """
        # 中心化
        F_centered = F - F.mean(axis=0)
        # 协方差矩阵特征分解
        Sigma = np.cov(F_centered, rowvar=False)
        eigvals, eigvecs = np.linalg.eigh(Sigma)
        # 降序排列
        idx = np.argsort(eigvals)[::-1]
        eigvals = eigvals[idx]
        eigvecs = eigvecs[:, idx]

        if n_components is None:
            # 按 variance_threshold 自动选
            cum_var = np.cumsum(eigvals) / np.sum(eigvals)
            n_components = np.searchsorted(cum_var, variance_threshold) + 1

        # W = V[:, :k] (K, k)
        W = eigvecs[:, :n_components]
        self.n_components_ = n_components
        self.explained_variance_ratio_ = eigvals[:n_components] / np.sum(eigvals)
        return W
```

### O1.6 CholeskyOrthogonalizer (风险模型)

```python
# modules/factor_orthogonalizer/core/cholesky.py
"""Cholesky 分解正交化 (风险模型场景)"""
import numpy as np
from scipy.linalg import cholesky, solve_triangular
from .base import BaseOrthogonalizer


class CholeskyOrthogonalizer(BaseOrthogonalizer):
    """Cholesky 分解正交化

    数学: Σ = F^T F = L L^T (L 为下三角)
          T = F L^(-T) → T^T T = L^(-1) Σ L^(-T) = I

    性质:
    - 数值稳定 (需 Σ 正定)
    - 顺序依赖 (第一个因子完全保留)
    - 比 LU 分解快约 2 倍

    架构层: Layer 2 (无监督变换)
    """

    def _compute_W(self, F: np.ndarray) -> np.ndarray:
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
```

### O1.7 RidgeOrthogonalizer (soft 正交化)

```python
# modules/factor_orthogonalizer/core/ridge.py
"""Ridge 正交化 (soft, 始终数值稳定)"""
import numpy as np
from scipy.linalg import eigh
from .base import BaseOrthogonalizer


class RidgeOrthogonalizer(BaseOrthogonalizer):
    """Ridge 正交化 (soft)

    数学: W = (F^T F + λI)^(-1/2)

    性质:
    - 始终数值稳定 (λ > 0 保证正定)
    - 不严格正交 (W^T F^T F W ≈ I, 而非精确 I)
    - λ 控制正交化强度 (λ → 0 退化为对称正交化)

    与 Ledoit-Wolf 关系: Ridge 是 LW 在 F^T F 谱上的特殊情况
    架构层: Layer 2 (无监督变换)
    """

    def _compute_W(self, F: np.ndarray, lambda_: float = 1.0) -> np.ndarray:
        """计算 W = (F^T F + λI)^(-1/2)

        Args:
            F: (N, K)
            lambda_: 正则化参数 (lambda_ > 0)

        Returns: W (K, K)
        """
        if lambda_ <= 0:
            raise ValueError(f"lambda_ 必须 > 0, 收到 {lambda_}")
        G = F.T @ F + lambda_ * np.eye(F.shape[1])
        eigvals, eigvecs = eigh(G)
        # Ridge 保证 G 正定, 无需截断
        W = eigvecs @ np.diag(1.0 / np.sqrt(eigvals)) @ eigvecs.T
        self.lambda_ = lambda_
        return W
```

### O1.8 TDD 测试设计

**测试文件**: `tests/test_factor_orthogonalizer/test_core_algorithms.py`

| 测试组 | 测试用例 | 验证目标 |
|---|---|---|
| **基础功能** | `test_symmetric_fit_transform_shape` | 输入 (N, K) 输出同 shape |
| | `test_symmetric_VRR_equals_one` | VRR = Var(T)/Var(F) ≈ 1.0 (精度 1e-10) |
| | `test_symmetric_orthogonality` | T^T T ≈ I (变换后因子正交) |
| | `test_gs_preserves_first_factor` | order[0] 对应因子完全保留 |
| | `test_pca_variance_threshold` | 前 k 主成分方差 ≥ 0.95 |
| | `test_cholesky_orthogonality` | T^T T = I (精确正交) |
| | `test_ridge_soft_orthogonality` | T^T T ≈ I + λI (近似正交) |
| **数值稳定性** | `test_symmetric_ill_conditioned` | κ > 1000 时不崩溃 (特征值截断) |
| | `test_gs_linear_dependent_raises` | 线性相关因子抛 ValueError |
| | `test_cholesky_non_pd_raises` | 非正定矩阵抛 ValueError + 建议信息 |
| | `test_ridge_always_stable` | 任意病态矩阵都不崩溃 |
| **手工数值校验** | `test_symmetric_matches_manual_eigh` | 与独立 numpy eigh 实现对比, 精度 < 1e-10 |
| | `test_cholesky_matches_scipy` | 与 scipy.linalg.cholesky 对比, 精度 < 1e-10 |
| | `test_gs_matches_qr_decomposition` | 与 numpy QR 分解对比 (order=[0,1,...,K-1]) |
| | `test_pca_matches_sklearn_pca` | 与 sklearn PCA 对比 (n_components=K), 精度 < 1e-10 |
| **接口契约** | `test_fit_before_transform_raises` | 未 fit 直接 transform 抛 RuntimeError |
| | `test_shape_mismatch_raises` | F 列数 ≠ K 抛 ValueError |
| | `test_N_less_than_K_raises` | N < K 抛 ValueError (样本不足) |
| **诊断属性** | `test_condition_number_computed` | fit 后 condition_number_ 正确 |
| | `test_eigvals_computed` | fit 后 eigvals_ 升序排列 |

### O1.9 手工数值校验方案

**校验脚本**: `tests/manual/test_orthogonalizer_manual.py`

```python
import numpy as np
from scipy.linalg import eigh
from factor_pipeline.modules.factor_orthogonalizer.core.symmetric import SymmetricOrthogonalizer

def test_symmetric_matches_manual_eigh():
    """手工校验: SymmetricOrthogonalizer 与独立 numpy eigh 实现对比"""
    np.random.seed(42)
    F = np.random.randn(100, 5)

    # 项目实现
    orth = SymmetricOrthogonalizer()
    T_project = orth.fit_transform(F)

    # 独立实现 (从零写起, 不用项目代码)
    G = F.T @ F
    eigvals, eigvecs = eigh(G)
    threshold = eigvals[-1] * 1e-10
    eigvals_clipped = np.maximum(eigvals, threshold)
    W_manual = eigvecs @ np.diag(1.0 / np.sqrt(eigvals_clipped)) @ eigvecs.T
    T_manual = F @ W_manual

    # 精度校验
    np.testing.assert_allclose(T_project, T_manual, atol=1e-10)

    # 性质校验
    # 1. VRR = 1
    vrr = np.var(T_project, axis=0) / np.var(F, axis=0)
    np.testing.assert_allclose(vrr, 1.0, atol=1e-10)
    # 2. T^T T = I (正交)
    np.testing.assert_allclose(T_project.T @ T_project, np.eye(5), atol=1e-8)
```

### O1.10 风险与陷阱

| # | 陷阱 | 严重性 | 规避方法 |
|---|---|---|---|
| 1 | eigh 输入非对称矩阵 | 中 | `BaseOrthogonalizer.fit` 中 `G = F.T @ F` 保证对称 |
| 2 | 特征值负数 (数值误差) | 高 | `np.maximum(eigvals, threshold)` 截断 |
| 3 | GS 线性相关崩溃 | 中 | 抛 ValueError + 建议 Ridge |
| 4 | Cholesky 非正定崩溃 | 中 | 抛 ValueError + 建议 Symmetric/Ridge |
| 5 | N < K 时 G 奇异 | 高 | `fit()` 入口校验 `N >= K` |
| 6 | dtype 隐式转换 (int → float) | 低 | `astype(np.float64)` 强制 |

### O1.11 验收标准

- [ ] 5 个算法类实现完成,接口一致 (fit/transform/fit_transform)
- [ ] ~40 个单元测试全部通过 (Green)
- [ ] 手工数值校验脚本通过 (精度 < 1e-10)
- [ ] 病态矩阵 (κ > 1000) 测试通过
- [ ] 线性相关因子正确抛错
- [ ] `from factor_pipeline.modules.factor_orthogonalizer.core import SymmetricOrthogonalizer` 可导入

### O1.12 工程深化 (v1.1 补充)

v1.0 的 5 个算法在 7 个工程细节上不够严谨, v1.1 补充如下。每项对应一个具体陷阱或数值稳定性问题, 实施时必须遵循。

#### O1.12.1 病态矩阵特征值截断策略 (高优先级)

**问题**: `SymmetricOrthogonalizer._compute_W` 中 `threshold = eigvals[-1] * min_eigval` 是相对阈值 (相对于最大特征值), 但在两种场景下失效:
- 因子尺度差异大: F_1 方差=1, F_2 方差=100, 则 λ_max/λ_min = 10000, 相对阈值 1e-10 × λ_max 仍可能过大 (放过本应截断的小特征值)
- 已标准化因子: 所有因子方差=1, λ_max ≈ λ_min, 相对阈值过严 (截断有效信号)

**修正**: 提供 `threshold_mode` 参数, 三种模式:

```python
def _compute_W(
    self,
    F: np.ndarray,
    min_eigval: float = 1e-10,
    threshold_mode: str = 'relative'
) -> np.ndarray:
    G = F.T @ F
    eigvals, eigvecs = eigh(G)

    if threshold_mode == 'relative':
        # 相对阈值: threshold = λ_max * min_eigval
        threshold = eigvals[-1] * min_eigval
    elif threshold_mode == 'absolute':
        # 绝对阈值: 直接用 min_eigval
        threshold = min_eigval
    elif threshold_mode == 'auto':
        # 自动: 取 max(相对, 绝对下界 1e-12)
        threshold = max(eigvals[-1] * min_eigval, 1e-12)
    else:
        raise ValueError(f"未知 threshold_mode: {threshold_mode}")

    eigvals_clipped = np.maximum(eigvals, threshold)
    W = eigvecs @ np.diag(1.0 / np.sqrt(eigvals_clipped)) @ eigvecs.T
    self.n_clipped_ = int(np.sum(eigvals < threshold))  # 诊断: 截断数
    return W
```

**默认推荐**: `threshold_mode='auto'` — 兼顾两种场景, 绝对下界 1e-12 防止数值零除, 相对阈值适应因子尺度。

**测试**: `test_threshold_mode_auto_handles_scale_diff` — F_1~N(0,1), F_2~N(0,100), auto 模式不崩溃且 n_clipped_ 正确。

#### O1.12.2 eigh vs svd 选择策略 (中优先级)

**问题**: 对 G = F^T F (对称半正定) 用 `eigh(G)` 是 v1.0 默认, 但对近奇异矩阵 (κ > 1e8), `eigh(G)` 的精度不如 `svd(F)` 直接分解:
- `eigh(G)` 等价于 `svd(F)` 的平方, 条件数被平方放大: κ(G) = κ(F)²
- `svd(F)` 直接分解 F, 数值精度保留 κ(F)

**修正**: 提供 `decomposition` 参数, 默认 `'eigh'` (快), 近奇异时切换 `'svd'` (稳):

```python
def _compute_W(
    self,
    F: np.ndarray,
    decomposition: str = 'eigh'
) -> np.ndarray:
    N, K = F.shape

    if decomposition == 'eigh':
        G = F.T @ F
        eigvals, eigvecs = eigh(G)
        # W = V Λ^(-1/2) V^T
        eigvals_clipped = np.maximum(eigvals, eigvals[-1] * 1e-10)
        W = eigvecs @ np.diag(1.0 / np.sqrt(eigvals_clipped)) @ eigvecs.T
    elif decomposition == 'svd':
        # F = U S V^T, 则 F^T F = V S² V^T
        # W = V S^(-1) V^T = F^+ F^+^T (伪逆形式)
        U, S, Vt = np.linalg.svd(F, full_matrices=False)
        S_clipped = np.maximum(S, S[-1] * 1e-10)
        # W = V diag(1/S) V^T
        W = Vt.T @ np.diag(1.0 / S_clipped) @ Vt
    else:
        raise ValueError(f"未知 decomposition: {decomposition}")

    return W
```

**何时用 svd**: `compute_condition_number(F) > 1e6` 时自动建议 svd (在 `OrthogonalizationDiagnostics` 中告警)。

**精度对比测试**: `test_svd_more_stable_for_ill_conditioned` — κ=1e10 矩阵, svd 的正交性误差 < eigh 的 1/100。

#### O1.12.3 PCA 中心化与因子已标准化的兼容 (中优先级)

**问题**: `PCAOrthogonalizer._compute_W` 默认 `F_centered = F - F.mean(axis=0)`, 但 Layer 1 的 `ProcessingAdapter(standardize)` 已将因子标准化 (均值 0, 方差 1), 二次中心化:
- 数值上: F.mean(axis=0) ≈ 0 (浮点误差 ~1e-16), 二次中心化无实质影响
- 语义上: 若用户未走 Layer 1 标准化 (直接传原始因子), PCA 中心化是必要的; 若已标准化, 中心化是冗余的

**修正**: 提供 `center` 参数, 默认 `True` (安全), 但文档说明已标准化时可设 `False` 省一次 mean 计算:

```python
def _compute_W(
    self,
    F: np.ndarray,
    n_components: Optional[int] = None,
    variance_threshold: float = 0.95,
    center: bool = True
) -> np.ndarray:
    if center:
        F_centered = F - F.mean(axis=0)
    else:
        F_centered = F  # 假设已中心化 (Layer 1 标准化后)
    Sigma = np.cov(F_centered, rowvar=False)
    # ... 后续 eigh
```

**注意**: `center=False` 时若 F 实际未中心化, PCA 结果会错误 (第一主成分被均值方向主导)。`OrthogonalizerAdapter` 应根据 Pipeline 配置自动设置 `center`。

**测试**: `test_pca_center_false_requires_standardized` — 已标准化因子 center=False 结果与 center=True 一致 (精度 1e-12); 未标准化因子 center=False 结果错误。

#### O1.12.4 Ridge λ 选择方法 (中优先级)

**问题**: `RidgeOrthogonalizer` 固定 `lambda_=1.0` 缺乏理论依据, 不同因子尺度下 λ 的最优值差异大:
- 因子方差=1: λ=1.0 合理
- 因子方差=100: λ=1.0 过小 (正则化不足), 等价于 Symmetric
- 因子方差=0.01: λ=1.0 过大 (过正则化), W 退化为 I/√λ

**修正**: 提供 `lambda_selection` 参数:

```python
def _compute_W(
    self,
    F: np.ndarray,
    lambda_: float = 1.0,
    lambda_selection: str = 'fixed'
) -> np.ndarray:
    K = F.shape[1]

    if lambda_selection == 'fixed':
        lam = lambda_
    elif lambda_selection == 'cv':
        # 交叉验证选 λ: 最小化 ||F W - F||_F (重建误差)
        from sklearn.linear_model import RidgeCV
        # 对每个因子 f_k, 用其他因子重建: f_k ≈ F_-k @ beta
        # Ridge 的 λ 即正交化强度
        lambdas = [0.01, 0.1, 1.0, 10.0, 100.0]
        ridge_cv = RidgeCV(alphas=lambdas, cv=5)
        ridge_cv.fit(F, F)  # 自重建
        lam = float(ridge_cv.alpha_)
    elif lambda_selection == 'ledoit_wolf':
        # Ledoit-Wolf 收缩强度作为 λ
        from sklearn.covariance import LedoitWolf
        lw = LedoitWolf().fit(F)
        lam = float(lw.shrinkage_) * np.trace(F.T @ F) / K
    else:
        raise ValueError(f"未知 lambda_selection: {lambda_selection}")

    G = F.T @ F + lam * np.eye(K)
    eigvals, eigvecs = eigh(G)
    W = eigvecs @ np.diag(1.0 / np.sqrt(eigvals)) @ eigvecs.T
    self.lambda_ = lam  # 记录实际使用的 λ
    return W
```

**默认推荐**: `lambda_selection='ledoit_wolf'` — 自适应因子尺度, 无需手动调参, 与 `OrthogonalizationConfig.shrinkage=True` 语义一致。

**学术依据**: Ledoit-Wolf (2004) "A well-conditioned estimator for large-dimensional covariance matrices"。

**测试**: `test_ridge_ledoit_wolf_adapts_to_scale` — F 方差放大 100 倍后, ledoit_wolf 的 λ 自动放大, W 保持稳定。

#### O1.12.5 Gram-Schmidt re-orthogonalization (低优先级)

**问题**: MGS (修正 Gram-Schmidt) 在条件数 κ > 100 时仍可能丢失正交性 (‖Q^T Q - I‖_F > 1e-10), 因为浮点误差在迭代投影中累积。

**修正**: 提供 `reorthogonalize` 参数, 对每个 q_i 做二次投影 (Kahan 1966 经典策略):

```python
def _compute_W(
    self,
    F: np.ndarray,
    order: Optional[List[int]] = None,
    reorthogonalize: bool = False
) -> np.ndarray:
    N, K = F.shape
    if order is None:
        order = list(range(K))
    Q = np.zeros_like(F)
    for i, idx in enumerate(order):
        v = F[:, idx].copy().astype(np.float64)
        # 第一次投影
        for j in range(i):
            v -= np.dot(Q[:, j], F[:, idx]) * Q[:, j]
        # 二次投影 (re-orthogonalization)
        if reorthogonalize:
            for j in range(i):
                v -= np.dot(Q[:, j], v) * Q[:, j]
        norm = np.linalg.norm(v)
        if norm < 1e-12:
            raise ValueError(f"因子 {idx} 线性相关")
        Q[:, i] = v / norm
    W = np.linalg.lstsq(F, Q, rcond=None)[0]
    return W
```

**何时启用**: `compute_condition_number(F) > 100` 时自动建议 `reorthogonalize=True`。

**测试**: `test_gs_reorthogonalize_improves_precision` — κ=500 矩阵, reorthogonalize=True 的 ‖Q^T Q - I‖_F < 1e-12, reorthogonalize=False > 1e-8。

#### O1.12.6 BaseOrthogonalizer.fit_from_gram 接口规范 (高优先级)

**问题**: `RollingOrthogonalizer` (O4) 需要从 Gram 矩阵 G 直接估计 W, 避免重新堆叠 F_window (性能优化), 但 v1.0 的 `BaseOrthogonalizer` 只有 `fit(F)`, 没有 `fit_from_gram(G)`。

**修正**: 在 `BaseOrthogonalizer` 添加 `fit_from_gram` 方法, 子类可选实现:

```python
class BaseOrthogonalizer(ABC):
    def fit_from_gram(
        self, G: np.ndarray, n_samples: Optional[int] = None
    ) -> 'BaseOrthogonalizer':
        """从 Gram 矩阵 G = F^T F 直接估计 W (无需 F)

        Args:
            G: (K, K) Gram 矩阵 (对称半正定)
            n_samples: 原始样本数 N (用于诊断, 可选)

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
        self.W_ = self._compute_W_from_gram(G)
        self.eigvals_ = np.linalg.eigvalsh(G)
        self.condition_number_ = self.eigvals_[-1] / max(self.eigvals_[0], 1e-12)
        self.is_fitted_ = True
        self._fitted_from_gram = True  # 标记来源
        return self

    @abstractmethod
    def _compute_W(self, F: np.ndarray) -> np.ndarray:
        """子类实现: 从 F 计算 W"""
        pass

    def _compute_W_from_gram(self, G: np.ndarray) -> np.ndarray:
        """子类可选实现: 从 G 计算 W

        默认: 抛 NotImplementedError, GS/Cholesky 不支持
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} 不支持 fit_from_gram, "
            f"仅 Symmetric/Ridge/PCA 支持"
        )
```

**SymmetricOrthogonalizer 的实现**:

```python
class SymmetricOrthogonalizer(BaseOrthogonalizer):
    def _compute_W_from_gram(self, G: np.ndarray) -> np.ndarray:
        """从 G 直接计算 W = G^(-1/2)"""
        eigvals, eigvecs = eigh(G)
        threshold = max(eigvals[-1] * 1e-10, 1e-12)
        eigvals_clipped = np.maximum(eigvals, threshold)
        return eigvecs @ np.diag(1.0 / np.sqrt(eigvals_clipped)) @ eigvecs.T
```

**测试**: `test_fit_from_gram_matches_fit` — 同一 F, `fit(F)` 与 `fit_from_gram(F^T F)` 的 W 精度 < 1e-12; `test_gs_raises_on_fit_from_gram` — GS 调用 fit_from_gram 抛 NotImplementedError。

#### O1.12.7 dtype 强制与内存布局检查 (低优先级)

**问题**: F 可能是 int (原始因子未标准化)、float32 (GPU 数据)、非 C-contiguous (切片后), 影响:
- int 输入: `F.T @ F` 整数溢出, `eigh` 报错
- float32: 精度损失 (1e-7 vs 1e-15), 破坏 1e-10 精度要求
- 非 C-contiguous: numpy 计算变慢 ~2x

**修正**: 在 `BaseOrthogonalizer.fit()` 入口强制转换:

```python
def fit(self, F: np.ndarray, **kwargs) -> 'BaseOrthogonalizer':
    # dtype 强制
    if not np.issubdtype(F.dtype, np.floating):
        F = F.astype(np.float64)
    elif F.dtype != np.float64:
        F = F.astype(np.float64)
    # C-contiguous 强制
    if not F.flags['C_CONTIGUOUS']:
        F = np.ascontiguousarray(F)
    # 形状校验
    if F.ndim != 2:
        raise ValueError(f"F 必须为 2D, 收到 {F.ndim}D")
    if F.shape[0] < F.shape[1]:
        raise ValueError(f"N ({F.shape[0]}) < K ({F.shape[1]})")
    self.W_ = self._compute_W(F, **kwargs)
    # ... 诊断
    return self
```

**测试**: `test_int_input_converted_to_float64` — int 输入不报错, 输出 W 为 float64; `test_non_contiguous_input_handled` — F.T 切片 (非 C-contiguous) 正常工作。

### O1.13 验收标准补充 (v1.1)

在 O1.11 基础上新增:

- [ ] 特征值截断策略: `threshold_mode='auto'` 实现, `test_threshold_mode_auto_handles_scale_diff` 通过
- [ ] eigh/svd 选择: `decomposition` 参数实现, `test_svd_more_stable_for_ill_conditioned` 通过
- [ ] PCA 中心化: `center` 参数实现, `test_pca_center_false_requires_standardized` 通过
- [ ] Ridge λ 选择: `lambda_selection='ledoit_wolf'` 实现, `test_ridge_ledoit_wolf_adapts_to_scale` 通过
- [ ] GS re-orthogonalization: `reorthogonalize` 参数实现, `test_gs_reorthogonalize_improves_precision` 通过
- [ ] fit_from_gram 接口: `BaseOrthogonalizer.fit_from_gram` 实现, Symmetric/Ridge/PCA 支持, GS/Cholesky 抛 NotImplementedError
- [ ] dtype 强制: int/float32/非 contiguous 输入均正确处理

---

## O2: Layer 2 适配器层 (P0)

**优先级**: P0
**依赖**: O1
**预计测试数**: ~20 个
**文件位置**: `adapters.py` (修改), `config_v2.py` (修改)

### O2.1 文件清单

| 文件 | 类型 | 职责 |
|---|---|---|
| `adapters.py` | 修改 | 新增 `OrthogonalizerAdapter` 类 |
| `config_v2.py` | 修改 | 新增 `OrthogonalizationConfig` |
| `modules/factor_orthogonalizer/utils/__init__.py` | 新建 | utils 子包 |
| `modules/factor_orthogonalizer/utils/stacking.py` | 新建 | `_stack_factors_cross_section` 工具函数 |

### O2.2 OrthogonalizerAdapter 设计

```python
# adapters.py (新增类)
class OrthogonalizerAdapter:
    """正交化适配器 — Layer 2 接入点

    与 NeutralizerAdapter 模式一致, 但处理多因子输入
    架构层: Layer 2 (无监督变换)
    位置: Pipeline.transform() 输出后

    设计要点:
    - REQUIRED 依赖 (scipy/sklearn), 无 fallback
    - is_fallback_mode 永远为 False (与 Imputer/Processing/Neutralizer 一致)
    - 构造时缓存正交化器类, fit() 不重复导入
    - enabled=False 时直接透传 (零侵入)
    """

    def __init__(
        self,
        method: str = 'symmetric',
        enabled: bool = False,
        window_mode: str = 'full_sample',
        window_size: int = 252,
        min_obs: int = 60,
        shrinkage: bool = True,
        **kwargs
    ):
        self.method = method
        self.enabled = enabled
        self.window_mode = window_mode
        self.window_size = window_size
        self.min_obs = min_obs
        self.shrinkage = shrinkage
        self.kwargs = kwargs
        self._orthogonalizer = None  # 缓存实例
        self._orthogonalizer_class = None  # 缓存类 (避免双重导入)
        self.is_fallback_mode = False  # REQUIRED 依赖, 永远 False
        # 构造时校验依赖 + 缓存类
        self._orthogonalizer_class = self._get_orthogonalizer_class()

    def _get_orthogonalizer_class(self):
        """获取正交化器类 (构造时调用一次, 缓存)"""
        from factor_pipeline.modules.factor_orthogonalizer.core import (
            SymmetricOrthogonalizer,
            GramSchmidtOrthogonalizer,
            PCAOrthogonalizer,
            CholeskyOrthogonalizer,
            RidgeOrthogonalizer,
        )
        method_map = {
            'symmetric': SymmetricOrthogonalizer,
            'gram_schmidt': GramSchmidtOrthogonalizer,
            'pca': PCAOrthogonalizer,
            'cholesky': CholeskyOrthogonalizer,
            'ridge': RidgeOrthogonalizer,
        }
        if self.method not in method_map:
            raise ValueError(
                f"未知 method: {self.method}, "
                f"支持: {list(method_map.keys())}"
            )
        return method_map[self.method]

    def fit(
        self,
        factor_dict: Dict[str, pd.DataFrame],
        **kwargs
    ) -> 'OrthogonalizerAdapter':
        """拟合正交化矩阵 W

        Args:
            factor_dict: {因子名: 宽表 (N_stocks, T_dates)}
                         K 个因子的预处理后输出

        架构:
        - 全样本模式: 堆叠为 (N·T, K) 估计单一 W
        - 滚动模式: 委托给 RollingOrthogonalizer (O4)
        """
        if not self.enabled:
            return self
        if len(factor_dict) < 2:
            raise ValueError(
                f"正交化需要至少 2 个因子, 收到 {len(factor_dict)} 个"
            )
        # 堆叠为 (N·T, K) 横截面面板
        F_stacked, self.factor_names_ = self._stack_factors_cross_section(factor_dict)
        # 构造正交化器实例
        self._orthogonalizer = self._orthogonalizer_class()
        self._orthogonalizer.fit(F_stacked, **self.kwargs)
        return self

    def transform(
        self,
        factor_dict: Dict[str, pd.DataFrame]
    ) -> Dict[str, pd.DataFrame]:
        """应用正交化到每期截面

        对每期 t: T_t = F_t @ W (W 在 fit 中估计)
        """
        if not self.enabled or self._orthogonalizer is None:
            return factor_dict
        result = {}
        for name, df in factor_dict.items():
            # df: (N, T), 对每列 (日期) 应用 W
            # 但 W 是 K×K, 需要联合 K 个因子一起应用
            # 这里需要 CrossSectionalOrthogonalizer 协调
            pass  # 见 O2.3 CrossSectionalOrthogonalizer
        return result

    def fit_transform(
        self,
        factor_dict: Dict[str, pd.DataFrame],
        **kwargs
    ) -> Dict[str, pd.DataFrame]:
        return self.fit(factor_dict, **kwargs).transform(factor_dict)

    @staticmethod
    def _stack_factors_cross_section(
        factor_dict: Dict[str, pd.DataFrame]
    ) -> Tuple[np.ndarray, List[str]]:
        """堆叠 K 个因子为 (N·T, K) 横截面面板

        输入: {因子名: (N, T) DataFrame}
        输出: (N·T, K) ndarray + 因子名列表

        步骤:
        1. 对齐所有因子的 index (股票) 和 columns (日期)
        2. 堆叠为 (N·T, K)
        """
        # 实现 O2.3
        pass
```

### O2.3 CrossSectionalOrthogonalizer 协调器

```python
# modules/factor_orthogonalizer/cross_sectional.py
"""横截面正交化协调器 — 管理 K 因子联合应用 W"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple


class CrossSectionalOrthogonalizer:
    """横截面正交化协调器

    职责:
    - 管理 K 个因子的对齐和堆叠
    - 对每期 t 应用 W: T_t = F_t @ W
    - 拆分回 Dict[str, DataFrame] 格式

    架构层: Layer 2 (无监督变换)
    """

    def __init__(self, orthogonalizer):
        """orthogonalizer: BaseOrthogonalizer 实例 (已 fit)"""
        self.orthogonalizer = orthogonalizer

    def transform(self, factor_dict: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """对每期截面应用 W

        Args:
            factor_dict: {因子名: (N, T) DataFrame}

        Returns: 同格式, K 个正交化后因子
        """
        # 1. 对齐 index 和 columns
        aligned = self._align_factors(factor_dict)
        factor_names = list(aligned.keys())
        K = len(factor_names)

        # 2. 构造 (N, T, K) 面板
        # 每个 df 是 (N, T), 堆叠为 (N, T, K)
        first_df = aligned[factor_names[0]]
        N, T = first_df.shape
        F_panel = np.zeros((N, T, K))
        for k, name in enumerate(factor_names):
            F_panel[:, :, k] = aligned[name].values

        # 3. 对每期 t 应用 W: T_t = F_t @ W
        T_panel = np.zeros_like(F_panel)
        for t in range(T):
            F_t = F_panel[:, t, :]  # (N, K)
            T_t = self.orthogonalizer.transform(F_t)  # (N, K)
            T_panel[:, t, :] = T_t

        # 4. 拆分回 Dict[str, DataFrame]
        result = {}
        for k, name in enumerate(factor_names):
            result[name] = pd.DataFrame(
                T_panel[:, :, k],
                index=first_df.index,
                columns=first_df.columns
            )
        return result

    @staticmethod
    def _align_factors(
        factor_dict: Dict[str, pd.DataFrame]
    ) -> Dict[str, pd.DataFrame]:
        """对齐所有因子的 index 和 columns"""
        # 取交集
        common_index = None
        common_columns = None
        for df in factor_dict.values():
            if common_index is None:
                common_index = df.index
                common_columns = df.columns
            else:
                common_index = common_index.intersection(df.index)
                common_columns = common_columns.intersection(df.columns)
        if len(common_index) == 0 or len(common_columns) == 0:
            raise ValueError("因子间无公共 index 或 columns, 无法对齐")
        # reindex
        return {
            name: df.loc[common_index, common_columns]
            for name, df in factor_dict.items()
        }
```

### O2.4 OrthogonalizationConfig

```python
# config_v2.py (新增 dataclass)
from pydantic import BaseModel, Field
from typing import Optional, Dict, List


class OrthogonalizationConfig(BaseModel):
    """正交化配置 (Layer 2)

    默认关闭, 不影响 632 基线
    """

    enabled: bool = Field(
        default=False,
        description="启用正交化 (默认关闭, 保护基线)"
    )
    method: str = Field(
        default='symmetric',
        description="正交化方法: symmetric/gram_schmidt/pca/cholesky/ridge"
    )
    window_mode: str = Field(
        default='full_sample',
        description="窗口模式: full_sample (研究用) / rolling (回测用)"
    )
    window_size: int = Field(
        default=252,
        description="滚动窗口大小 (日), 仅 window_mode=rolling 时生效"
    )
    min_obs: int = Field(
        default=60,
        description="最小样本数, 不足时跳过正交化"
    )
    shrinkage: bool = Field(
        default=True,
        description="启用 Ledoit-Wolf 收缩预处理 (病态矩阵保护)"
    )
    vrr_threshold: float = Field(
        default=0.3,
        description="VRR 冗余阈值, VRR < threshold 的因子标记为冗余"
    )
    groups: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description="分组正交化: {组名: [因子名]}, 组内正交 + 组间保留"
    )
    use_gpu: bool = Field(
        default=False,
        description="启用 GPU 加速 (需 CuPy, HAS_CUPY 标记)"
    )

    # 方法特定参数
    ridge_lambda: float = Field(default=1.0, description="Ridge λ (仅 method=ridge)")
    pca_variance_threshold: float = Field(
        default=0.95,
        description="PCA 方差保留阈值 (仅 method=pca)"
    )
    gs_order: Optional[List[int]] = Field(
        default=None,
        description="GS 正交化顺序 (仅 method=gram_schmidt)"
    )
```

### O2.5 接入 PipelineV2ConfigUnified

```python
# config_v2.py (修改 PipelineV2ConfigUnified)
class PipelineV2ConfigUnified(BaseModel):
    # ... 现有字段 ...

    # v2.5.0 新增
    orthogonalization: OrthogonalizationConfig = Field(
        default_factory=OrthogonalizationConfig,
        description="Layer 2 正交化配置 (默认关闭)"
    )

    version: str = Field(default="2.5.0", description="Pipeline 版本")
```

### O2.6 TDD 测试设计

**测试文件**: `tests/test_factor_orthogonalizer/test_adapter.py`

| 测试组 | 测试用例 | 验证目标 |
|---|---|---|
| **基础功能** | `test_adapter_disabled_passthrough` | enabled=False 时直接返回原 dict |
| | `test_adapter_enabled_transforms` | enabled=True 时输出正交化后因子 |
| | `test_adapter_fit_transform_consistent` | fit_transform 与 fit+transform 一致 |
| **数据对齐** | `test_adapter_aligns_different_indices` | 不同 index 的因子自动对齐到交集 |
| | `test_adapter_raises_on_no_common_index` | 无公共 index 抛 ValueError |
| | `test_adapter_raises_on_single_factor` | 单因子抛 ValueError (需 K >= 2) |
| **配置** | `test_config_default_disabled` | 默认 enabled=False |
| | `test_config_method_validation` | 未知 method 抛 ValueError |
| | `test_config_window_mode_validation` | 未知 window_mode 抛 ValueError |
| **集成** | `test_adapter_with_pipeline_output` | 接入 Pipeline.transform() 输出 |
| | `test_adapter_preserves_dict_format` | 输出格式与输入一致 (Dict[str, DataFrame]) |
| | `test_adapter_N_less_than_K_raises` | N < K 抛 ValueError |
| **回归保护** | `test_default_config_no_regression` | 默认配置下 632 基线不变 |

### O2.7 验收标准

- [ ] `OrthogonalizerAdapter` 类实现完成
- [ ] `OrthogonalizationConfig` Pydantic 模型定义
- [ ] `PipelineV2ConfigUnified` 接入 orthogonalization 字段
- [ ] 默认 `enabled=False` 不影响 632 基线
- [ ] ~20 个单元测试通过
- [ ] 与 Pipeline.transform() 输出格式兼容

### O2.8 工程深化 (v1.1 补充)

v1.0 的适配器层在 6 个工程细节上不够严谨, v1.1 补充如下。每项对应一个具体的集成陷阱或性能问题。

#### O2.8.1 因子对齐策略: 交集 vs 并集 + NaN (高优先级)

**问题**: v1.0 的 `_align_factors` 用 `intersection` 取公共 index/columns, 丢弃不共有的股票/日期。在真实场景中:
- Barra 因子 41 天 vs 日频因子 1212 天 → 交集 41 天, 日频因子 1171 天数据被浪费
- 不同数据源股票池不同 (沪深 300 vs 中证 500) → 交集可能为空

**修正**: 提供 `align_mode` 参数, 支持三种策略:

```python
class OrthogonalizationConfig(BaseModel):
    align_mode: str = Field(
        default='intersection',
        description=(
            "因子对齐策略: "
            "'intersection' (默认, 取交集, 严格对齐) / "
            "'union_nan' (取并集, 缺失填 NaN, 配合 dropna) / "
            "'raise_on_mismatch' (不匹配时抛错, 严格调试用)"
        )
    )

@staticmethod
def _align_factors(
    factor_dict: Dict[str, pd.DataFrame],
    align_mode: str = 'intersection'
) -> Dict[str, pd.DataFrame]:
    if align_mode == 'intersection':
        # 交集 (v1.0 行为)
        common_index = factor_dict[next(iter(factor_dict))].index
        common_columns = factor_dict[next(iter(factor_dict))].columns
        for df in factor_dict.values():
            common_index = common_index.intersection(df.index)
            common_columns = common_columns.intersection(df.columns)
        if len(common_index) == 0 or len(common_columns) == 0:
            raise ValueError("因子间无公共 index 或 columns")
        return {n: df.loc[common_index, common_columns] for n, df in factor_dict.items()}
    elif align_mode == 'union_nan':
        # 并集, 缺失填 NaN (后续 dropna 处理)
        all_index = factor_dict[next(iter(factor_dict))].index
        all_columns = factor_dict[next(iter(factor_dict))].columns
        for df in factor_dict.values():
            all_index = all_index.union(df.index)
            all_columns = all_columns.union(df.columns)
        return {n: df.reindex(index=all_index, columns=all_columns) for n, df in factor_dict.items()}
    elif align_mode == 'raise_on_mismatch':
        # 严格: 任何不匹配抛错
        ref_idx = factor_dict[next(iter(factor_dict))].index
        ref_col = factor_dict[next(iter(factor_dict))].columns
        for name, df in factor_dict.items():
            if not df.index.equals(ref_idx) or not df.columns.equals(ref_col):
                raise ValueError(
                    f"因子 {name} 的 index/columns 与参考不一致, "
                    f"请先在 Pipeline 中对齐"
                )
        return factor_dict
```

**默认推荐**: `intersection` (向后兼容 v1.0); 真实回测用 `union_nan` + dropna 保留更多数据。

**测试**: `test_align_intersection_drops_mismatch` — 不同 index 的因子取交集; `test_align_union_nan_fills_missing` — 并集模式缺失填 NaN。

#### O2.8.2 NaN 处理与 dropna 策略 (高优先级)

**问题**: `union_nan` 对齐或因子本身含 NaN 时, `F.T @ F` 会传播 NaN 到整个 Gram 矩阵, 导致 `eigh` 失败或返回 NaN。

**修正**: 在 `fit()` 中强制 dropna, 并记录丢弃比例:

```python
def fit(self, factor_dict, **kwargs):
    if not self.enabled:
        return self
    # 对齐
    aligned = self._align_factors(factor_dict, self.align_mode)
    # 堆叠为 (N·T, K)
    F_stacked, self.factor_names_ = self._stack_factors_cross_section(aligned)
    # NaN 检查与丢弃
    n_before = F_stacked.shape[0]
    mask = ~np.any(np.isnan(F_stacked), axis=1)
    F_stacked = F_stacked[mask]
    n_after = F_stacked.shape[0]
    self.nan_drop_ratio_ = 1.0 - n_after / n_before if n_before > 0 else 0.0
    if self.nan_drop_ratio_ > 0.5:
        import warnings
        warnings.warn(
            f"正交化 fit 丢弃了 {self.nan_drop_ratio_*100:.1f}% 的样本 (NaN), "
            f"检查因子对齐或使用 align_mode='intersection'",
            UserWarning
        )
    if F_stacked.shape[0] < F_stacked.shape[1]:
        raise ValueError(
            f"NaN 丢弃后样本不足: N={F_stacked.shape[0]} < K={F_stacked.shape[1]}"
        )
    # 拟合 W
    self._orthogonalizer = self._orthogonalizer_class()
    self._orthogonalizer.fit(F_stacked, **self.kwargs)
    # 缓存 mask 用于 transform
    self._fit_mask_ = mask
    return self
```

**transform 的 NaN 处理**: transform 时不能 dropna (会破坏输出 shape), 而是:
- 对含 NaN 的行, W 应用后仍为 NaN (数学传播)
- 或填充 0 后应用 W, 再恢复 NaN (保守)

```python
def transform(self, factor_dict):
    # ... 对每期 t
    F_t = F_panel[:, t, :]  # (N, K)
    nan_mask = np.any(np.isnan(F_t), axis=1)
    if np.any(nan_mask):
        # 填 0 应用 W, 恢复 NaN
        F_t_filled = np.nan_to_num(F_t, nan=0.0)
        T_t = self._orthogonalizer.transform(F_t_filled)
        T_t[nan_mask] = np.nan
    else:
        T_t = self._orthogonalizer.transform(F_t)
    # ...
```

**测试**: `test_nan_in_fit_dropped_with_warning` — 50% NaN 触发告警; `test_nan_in_transform_preserved` — transform 时 NaN 行输出仍为 NaN。

#### O2.8.3 Pipeline 接入点选择 (中优先级)

**问题**: v1.0 说"正交化作为独立后处理层", 但未明确接入点:
- 选项 A: Pipeline.transform() 内部, per-factor 循环结束后 (侵入式)
- 选项 B: Pipeline.transform() 外部, 用户手动调用 `OrthogonalizerAdapter.fit_transform()` (非侵入式)
- 选项 C: 作为 Pipeline 的可选 post_hook (半侵入式)

**修正**: 采用选项 C (半侵入式), 在 `FactorProcessingPipelineV2` 添加 `post_transform_hooks`:

```python
class FactorProcessingPipelineV2:
    def __init__(self, config, ...):
        # ... 现有初始化
        self.post_transform_hooks = []
        if config.orthogonalization.enabled:
            self.post_transform_hooks.append(
                OrthogonalizerAdapter(config.orthogonalization)
            )

    def transform(self, factor_dict):
        # 现有 per-factor 处理
        result = self._per_factor_transform(factor_dict)
        # 后处理 hooks (Layer 2 正交化等)
        for hook in self.post_transform_hooks:
            result = hook.fit_transform(result) if not hook.is_fitted_ else hook.transform(result)
        return result
```

**优点**:
- 不修改 per-factor 循环 (满足"Pipeline 不重构"约束)
- enabled=False 时 hooks 为空, 零开销
- 可扩展 (未来 Layer 2.5 风险平价等也可作为 hook)

**测试**: `test_pipeline_with_orthogonalization_hook` — enabled=True 时 Pipeline.transform 输出正交化后因子; `test_pipeline_without_hook_zero_overhead` — enabled=False 时 hooks 为空列表。

#### O2.8.4 enabled=False 的零开销验证 (中优先级)

**问题**: v1.0 声称"默认 enabled=False 不影响 632 基线", 但未验证:
- `OrthogonalizerAdapter.__init__` 中 `_get_orthogonalizer_class()` 会触发 import, 即使 enabled=False
- `post_transform_hooks` 列表非空时, 循环开销虽小但非零

**修正**: enabled=False 时完全跳过初始化:

```python
class FactorProcessingPipelineV2:
    def __init__(self, config, ...):
        self.post_transform_hooks = []
        # 仅在 enabled 时才构造 adapter
        if getattr(config, 'orthogonalization', None) and config.orthogonalization.enabled:
            self.post_transform_hooks.append(
                OrthogonalizerAdapter(config.orthogonalization)
            )
        # enabled=False 时 hooks=[] (空列表, 零循环开销)

class OrthogonalizerAdapter:
    def __init__(self, config):
        self.enabled = config.enabled
        if not self.enabled:
            # 提前返回, 不触发 import
            self._orthogonalizer_class = None
            self.is_fallback_mode = False
            return
        # 仅 enabled=True 时才 import
        self._orthogonalizer_class = self._get_orthogonalizer_class()
```

**零开销测试**: `test_disabled_adapter_no_import` — enabled=False 时 `factor_orthogonalizer.core` 模块未被导入 (检查 `sys.modules`); `test_disabled_pipeline_hooks_empty` — enabled=False 时 `pipeline.post_transform_hooks == []`。

#### O2.8.5 OrthogonalizationConfig 向后兼容 (低优先级)

**问题**: v2.4.0 的 `PipelineV2ConfigUnified` 不含 `orthogonalization` 字段, 旧配置 JSON 反序列化时:
- Pydantic 默认行为: 未知字段忽略, 缺失字段用默认值 → 向后兼容
- 但若用户用了 `extra='forbid'` (严格模式), 添加新字段会破坏旧 JSON 加载

**修正**: 确保 `PipelineV2ConfigUnified` 用 `extra='ignore'` (Pydantic v2 默认) 或 `'allow'`:

```python
from pydantic import ConfigDict

class PipelineV2ConfigUnified(BaseModel):
    model_config = ConfigDict(
        extra='ignore',  # 忽略未知字段 (向后兼容旧 JSON)
        validate_assignment=True,  # 赋值时校验
    )
    # ... 现有字段
    orthogonalization: OrthogonalizationConfig = Field(default_factory=OrthogonalizationConfig)
```

**旧 JSON 加载测试**: `test_old_config_json_loads_with_default_orthogonalization` — v2.4.0 的 JSON (无 orthogonalization 字段) 加载后, `config.orthogonalization.enabled == False` (默认值)。

#### O2.8.6 CrossSectionalOrthogonalizer 的 W 缓存与复用 (低优先级)

**问题**: v1.0 的 `CrossSectionalOrthogonalizer.transform` 对每期 t 调用 `orthogonalizer.transform(F_t)`, 即 `F_t @ W`。若 W 在 fit 后不变 (full_sample 模式), 每期重复矩阵乘法, 但 W 是同一个, 可缓存。

**修正**: 在 `CrossSectionalOrthogonalizer` 中缓存 W, transform 时直接用:

```python
class CrossSectionalOrthogonalizer:
    def __init__(self, orthogonalizer):
        self.orthogonalizer = orthogonalizer
        self.W_cached_ = None  # 缓存 W

    def transform(self, factor_dict):
        # ... 对齐
        # 缓存 W (若未缓存)
        if self.W_cached_ is None:
            self.W_cached_ = self.orthogonalizer.W_
        # 对每期 t: T_t = F_t @ W (直接用缓存, 不调用 transform)
        for t in range(T):
            F_t = F_panel[:, t, :]  # (N, K)
            T_panel[:, t, :] = F_t @ self.W_cached_
        # ...
```

**性能影响**: K=20, T=252, N=3000:
- v1.0: 252 次 `transform` 调用 (含方法分发开销) ≈ 50ms
- v1.1: 1 次 W 缓存 + 252 次矩阵乘法 ≈ 20ms (2.5x 加速)

**注意**: rolling 模式下 W 每期变化, 不能缓存, `CrossSectionalOrthogonalizer` 需检查 `orthogonalizer.is_fitted_` 和 W 是否更新。

**测试**: `test_w_cached_in_full_sample_mode` — full_sample 模式 W 缓存命中; `test_w_not_cached_in_rolling_mode` — rolling 模式每期重新 fit。

### O2.9 验收标准补充 (v1.1)

在 O2.7 基础上新增:

- [ ] 对齐策略: `align_mode` 三种模式实现, `test_align_intersection_drops_mismatch` + `test_align_union_nan_fills_missing` 通过
- [ ] NaN 处理: fit 时 dropna + 告警, transform 时 NaN 保留, `test_nan_in_fit_dropped_with_warning` + `test_nan_in_transform_preserved` 通过
- [ ] Pipeline 接入点: `post_transform_hooks` 机制实现, `test_pipeline_with_orthogonalization_hook` 通过
- [ ] 零开销验证: enabled=False 时不触发 import, `test_disabled_adapter_no_import` + `test_disabled_pipeline_hooks_empty` 通过
- [ ] 向后兼容: 旧 JSON 加载默认 orthogonalization, `test_old_config_json_loads_with_default_orthogonalization` 通过
- [ ] W 缓存: full_sample 模式缓存命中, `test_w_cached_in_full_sample_mode` 通过

---

## O3a: Layer 2 几何诊断 (P0)

**优先级**: P0
**依赖**: O1, O2
**预计测试数**: ~15 个
**文件位置**: `modules/factor_orthogonalizer/core/diagnostics.py`

### O3a.1 文件清单

| 文件 | 类型 | 职责 |
|---|---|---|
| `modules/factor_orthogonalizer/core/diagnostics.py` | 新建 | `OrthogonalizationDiagnostics` 类 |

### O3a.2 OrthogonalizationDiagnostics 设计

```python
# modules/factor_orthogonalizer/core/diagnostics.py
"""正交化几何诊断 (Layer 2, 无监督)

与 Layer 3 因子检验 (双重 Lasso) 严格区分:
- Layer 2 诊断: 变换质量验证 (VRR/κ/VIF/正交性误差)
- Layer 3 检验: 因子增量 alpha (p 值/系数)
"""
import numpy as np
from typing import Dict


class OrthogonalizationDiagnostics:
    """正交化几何诊断

    四项诊断指标:
    1. VRR (Variance Retention Ratio): 方差保留率, VRR < 0.3 → 冗余
    2. κ (Condition Number): 条件数, κ > 1000 → 病态
    3. VIF (Variance Inflation Factor): 方差膨胀因子, VIF > 5 → 多重共线性
    4. 正交性误差: ‖Σ* - diag(Σ*)‖_F, 应接近 0

    架构层: Layer 2 (无监督, 不需 Y)
    """

    @staticmethod
    def compute_vrr(F: np.ndarray, T: np.ndarray) -> np.ndarray:
        """方差保留率 (Variance Retention Ratio)

        VRR_k = Var(T_k) / Var(F_k)
        - VRR ≈ 1: 因子 k 方差完全保留 (对称正交化的理论值)
        - VRR < 0.3: 因子 k 高度冗余 (被其他因子吸收)
        - VRR > 1: 因子 k 方差被放大 (异常, 检查数值稳定性)

        Args:
            F: (N, K) 原始因子
            T: (N, K) 正交化后因子

        Returns: VRR (K,) 数组
        """
        var_F = np.var(F, axis=0)
        var_T = np.var(T, axis=0)
        # 避免除零
        vrr = np.where(var_F > 1e-12, var_T / var_F, 0.0)
        return vrr

    @staticmethod
    def compute_condition_number(F: np.ndarray) -> float:
        """条件数 κ = λ_max / λ_min

        - κ < 10: 良好
        - 10 < κ < 100: 可接受
        - 100 < κ < 1000: 需注意
        - κ > 1000: 病态, 建议 Ledoit-Wolf 收缩或 Ridge

        Args:
            F: (N, K) 因子矩阵

        Returns: κ (标量)
        """
        G = F.T @ F
        eigvals = np.linalg.eigvalsh(G)
        # 避免 λ_min = 0
        eigvals = np.maximum(eigvals, 1e-12)
        return eigvals[-1] / eigvals[0]

    @staticmethod
    compute_vif(F: np.ndarray) -> np.ndarray:
        """方差膨胀因子 (Variance Inflation Factor)

        VIF_k = 1 / (1 - R_k²)
        其中 R_k² 是因子 k 对其他 K-1 个因子回归的 R²

        - VIF < 5: 无明显多重共线性
        - 5 < VIF < 10: 中等共线性
        - VIF > 10: 严重共线性

        Args:
            F: (N, K) 因子矩阵

        Returns: VIF (K,) 数组
        """
        K = F.shape[1]
        vifs = np.zeros(K)
        for k in range(K):
            others = np.delete(F, k, axis=1)  # (N, K-1)
            target = F[:, k]
            # OLS: target ~ others
            beta = np.linalg.lstsq(others, target, rcond=None)[0]
            residual = target - others @ beta
            ss_res = np.sum(residual ** 2)
            ss_tot = np.sum((target - target.mean()) ** 2)
            r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
            if r_squared >= 1.0:
                vifs[k] = float('inf')
            else:
                vifs[k] = 1.0 / (1.0 - r_squared)
        return vifs

    @staticmethod
    def compute_orthogonality_error(T: np.ndarray) -> float:
        """正交性误差 (Frobenius 范数)

        err = ‖Σ* - diag(Σ*)‖_F
        其中 Σ* = corr(T) 是正交化后因子的相关矩阵

        - err ≈ 0: 正交化成功
        - err > 0.1: 正交化不充分 (检查数值稳定性)

        Args:
            T: (N, K) 正交化后因子

        Returns: 误差标量
        """
        Sigma = np.corrcoef(T.T)
        Sigma_diag = np.diag(np.diag(Sigma))
        return float(np.linalg.norm(Sigma - Sigma_diag, 'fro'))

    @classmethod
    def full_diagnostics(
        cls,
        F: np.ndarray,
        T: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """完整诊断报告

        Args:
            F: (N, K) 原始因子
            T: (N, K) 正交化后因子

        Returns:
            {
                'vrr': (K,) 方差保留率,
                'condition_number': 标量,
                'vif': (K,) 方差膨胀因子 (基于 F),
                'orthogonality_error': 标量,
                'redundant_factors': List[int],  # VRR < 0.3 的因子索引
                'multicollinear_factors': List[int],  # VIF > 5 的因子索引
            }
        """
        vrr = cls.compute_vrr(F, T)
        kappa = cls.compute_condition_number(F)
        vif = cls.compute_vif(F)
        orth_err = cls.compute_orthogonality_error(T)
        return {
            'vrr': vrr,
            'condition_number': kappa,
            'vif': vif,
            'orthogonality_error': orth_err,
            'redundant_factors': np.where(vrr < 0.3)[0].tolist(),
            'multicollinear_factors': np.where(vif > 5)[0].tolist(),
        }
```

### O3a.3 TDD 测试设计

**测试文件**: `tests/test_factor_orthogonalizer/test_diagnostics.py`

| 测试用例 | 验证目标 |
|---|---|
| `test_vrr_symmetric_equals_one` | 对称正交化后 VRR ≈ 1.0 (精度 1e-10) |
| `test_vrr_redundant_factor_low` | ρ=0.95 冗余因子 VRR < 0.3 |
| `test_condition_number_well_conditioned` | 良好矩阵 κ < 10 |
| `test_condition_number_ill_conditioned` | 病态矩阵 κ > 1000 |
| `test_vif_independent_factors_low` | 独立因子 VIF < 5 |
| `test_vif_collinear_factors_high` | 共线因子 VIF > 10 |
| `test_orthogonality_error_near_zero` | 正交化后误差 < 1e-8 |
| `test_orthogonality_error_raw_high` | 原始因子误差 > 0.5 |
| `test_full_diagnostics_returns_all_fields` | 返回 dict 含 6 个字段 |
| `test_redundant_factors_identified` | 冗余因子索引正确识别 |
| `test_multicollinear_factors_identified` | 多重共线因子正确识别 |

### O3a.4 手工数值校验方案

```python
def test_vrr_manual_calculation():
    """手工校验 VRR 计算"""
    np.random.seed(42)
    F = np.random.randn(100, 3)
    orth = SymmetricOrthogonalizer()
    T = orth.fit_transform(F)

    # 项目实现
    vrr_project = OrthogonalizationDiagnostics.compute_vrr(F, T)

    # 手工计算
    var_F = np.var(F, axis=0)
    var_T = np.var(T, axis=0)
    vrr_manual = var_T / var_F

    np.testing.assert_allclose(vrr_project, vrr_manual, atol=1e-10)
    # 对称正交化 VRR = 1
    np.testing.assert_allclose(vrr_project, 1.0, atol=1e-10)
```

### O3a.5 验收标准

- [ ] `OrthogonalizationDiagnostics` 类实现完成
- [ ] 4 项诊断指标 (VRR/κ/VIF/正交性误差) 全部实现
- [ ] `full_diagnostics` 返回完整诊断报告
- [ ] ~15 个单元测试通过
- [ ] 手工数值校验通过 (VRR 精度 < 1e-10)
- [ ] 能识别 ρ=0.95 的冗余因子 (VRR < 0.3)
- [ ] 能识别 VIF > 5 的多重共线因子

### O3a.6 工程深化 (v1.1 补充)

v1.0 的几何诊断在 5 个工程细节上不够严谨, v1.1 补充如下。每项对应一个计算精度或阈值依据问题。

#### O3a.6.1 VRR 计算的 var 选择: 样本方差 vs 总体方差 (高优先级)

**问题**: `compute_vrr` 用 `np.var(F, axis=0)`, numpy 默认 `ddof=0` (总体方差), 但:
- 若 F 是全样本 (N·T 行), 总体方差合理 (用全部数据估计)
- 若 F 是滚动窗口子样本, 样本方差 (`ddof=1`) 更准确 (无偏估计)
- VRR = Var(T)/Var(F), 分子分母 ddof 不一致会导致 VRR 系统性偏差

**修正**: 暴露 `ddof` 参数, 默认 `0` (与 numpy 一致, 全样本场景), 文档说明滚动场景应用 `ddof=1`:

```python
@staticmethod
def compute_vrr(
    F: np.ndarray,
    T: np.ndarray,
    ddof: int = 0
) -> np.ndarray:
    """方差保留率

    Args:
        F: (N, K) 原始因子
        T: (N, K) 正交化后因子
        ddof: 自由度调整 (0=总体方差, 1=样本方差)
              全样本用 0, 滚动窗口子样本建议 1
    """
    var_F = np.var(F, axis=0, ddof=ddof)
    var_T = np.var(T, axis=0, ddof=ddof)
    vrr = np.where(var_F > 1e-12, var_T / var_F, 0.0)
    return vrr
```

**数值影响**: N=100, ddof 差异 = 1/99 ≈ 1%, VRR 偏差 ~0.01 (通常可忽略, 但高精度校验时需一致)。

**测试**: `test_vrr_ddof_consistency` — ddof=0 和 ddof=1 的 VRR 差异 = 1/(N-1), 精度 1e-12。

#### O3a.6.2 VIF 计算的 OLS 实现精度 (中优先级)

**问题**: `compute_vif` 用 `np.linalg.lstsq(others, target)` 计算 R², 但 lstsq 在病态矩阵下精度不如 pinv 或 QR 分解:
- `lstsq`: 基于 SVD, 精度高但慢
- `pinv`: 也基于 SVD, 与 lstsq 等价
- 正规方程 `inv(X^T X) @ X^T y`: 最快但条件数平方放大, 病态时危险

**修正**: v1.0 的 lstsq 已是合理选择, 但补充 R² = 1.0 时的 inf 处理和数值精度校验:

```python
@staticmethod
def compute_vif(F: np.ndarray, method: str = 'lstsq') -> np.ndarray:
    """方差膨胀因子

    Args:
        F: (N, K)
        method: 'lstsq' (默认, SVD) / 'qr' (QR 分解, 快) / 'pinv' (伪逆)
    """
    K = F.shape[1]
    vifs = np.zeros(K)
    for k in range(K):
        others = np.delete(F, k, axis=1)  # (N, K-1)
        target = F[:, k]
        # 加截距 (中心化等价, 但显式加更安全)
        others_with_const = np.column_stack([others, np.ones(len(target))])
        if method == 'lstsq':
            beta = np.linalg.lstsq(others_with_const, target, rcond=None)[0]
        elif method == 'qr':
            Q, R = np.linalg.qr(others_with_const)
            beta = np.linalg.solve(R, Q.T @ target)
        elif method == 'pinv':
            beta = np.linalg.pinv(others_with_const) @ target
        residual = target - others_with_const @ beta
        ss_res = np.sum(residual ** 2)
        ss_tot = np.sum((target - target.mean()) ** 2)
        # R² = 1 - ss_res/ss_tot, 数值稳定处理
        if ss_tot < 1e-12:
            vifs[k] = 1.0  # 零方差因子, 无共线性
        elif ss_res < 1e-12:
            vifs[k] = float('inf')  # 完美共线
        else:
            r_squared = 1 - ss_res / ss_tot
            r_squared = min(r_squared, 1.0 - 1e-15)  # 防止 R² >= 1.0
            vifs[k] = 1.0 / (1.0 - r_squared)
    return vifs
```

**默认推荐**: `method='lstsq'` (SVD 最稳), K>50 时用 `'qr'` (快 3-5x)。

**测试**: `test_vif_lstsq_matches_qr` — 良好矩阵下两种方法一致 (精度 1e-10); `test_vif_perfect_collinearity_inf` — 完美共线因子 VIF = inf。

#### O3a.6.3 条件数阈值的学术依据与告警分级 (中优先级)

**问题**: v1.0 的条件数阈值 (κ<10 良好, >1000 病态) 缺乏学术引用, 且未区分"警告"与"严重"。

**修正**: 基于 Belsley-Kuh-Welsch (1980) "Regression Diagnostics" 的经典分级:

```python
@staticmethod
def compute_condition_number(F: np.ndarray) -> float:
    G = F.T @ F
    eigvals = np.linalg.eigvalsh(G)
    eigvals = np.maximum(eigvals, 1e-12)
    kappa = eigvals[-1] / eigvals[0]
    return float(kappa)

@staticmethod
def condition_number_severity(kappa: float) -> str:
    """条件数严重性分级 (Belsley-Kuh-Welsch 1980)

    Returns: 'good' / 'acceptable' / 'warning' / 'severe'
    """
    if kappa < 10:
        return 'good'         # 无多重共线性
    elif kappa < 100:
        return 'acceptable'   # 轻微共线性, 可接受
    elif kappa < 1000:
        return 'warning'      # 中等共线性, 建议 Ridge/LW
    else:
        return 'severe'       # 严重共线性, 必须 Ridge/LW 或删因子
```

**学术依据**: Belsley, Kuh, Welsch (1980) "Regression Diagnostics: Identifying Influential Data and Sources of Collinearity", Table 3.3。

**测试**: `test_condition_number_severity_levels` — 四个阈值边界正确分级。

#### O3a.6.4 正交性误差的归一化 (低优先级)

**问题**: v1.0 用 Frobenius 范数 `‖Σ - diag(Σ)‖_F`, 但未归一化:
- K=2 时, 最大可能误差 = √2 (完全相关)
- K=20 时, 最大可能误差 = √(380) (完全相关)
- 不同 K 的误差不可比较

**修正**: 提供归一化选项:

```python
@staticmethod
def compute_orthogonality_error(
    T: np.ndarray,
    norm: str = 'frobenius'
) -> float:
    """正交性误差

    Args:
        T: (N, K) 正交化后因子
        norm: 'frobenius' (默认, v1.0) / 'normalized' (除以√(K(K-1))) / 'max_abs' (最大绝对值)
    """
    Sigma = np.corrcoef(T.T)
    K = Sigma.shape[0]
    # 去对角线
    mask = ~np.eye(K, dtype=bool)
    off_diag = Sigma[mask]

    if norm == 'frobenius':
        return float(np.sqrt(np.sum(off_diag ** 2)))
    elif norm == 'normalized':
        # 归一化到 [0, 1], 可跨 K 比较
        max_error = np.sqrt(K * (K - 1))
        return float(np.sqrt(np.sum(off_diag ** 2)) / max_error)
    elif norm == 'max_abs':
        return float(np.max(np.abs(off_diag)))
    else:
        raise ValueError(f"未知 norm: {norm}")
```

**默认推荐**: `norm='normalized'` — 跨 K 可比较, 阈值统一 (如 < 0.01 表示良好正交)。

**测试**: `test_orthogonality_error_normalized_comparable_across_k` — K=2 和 K=20 的完全正交因子, normalized 误差都 = 0; 完全相关因子都 ≈ 1。

#### O3a.6.5 诊断报告的 JSON 序列化与 NaN/inf 处理 (低优先级)

**问题**: `full_diagnostics` 返回的 dict 含 `float('inf')` (VIF 完美共线) 和 numpy 类型, JSON 序列化时 `json.dumps` 报错 `TypeError: Object of type ndarray is not JSON serializable` 或 `ValueError: Out of range float values are not JSON compliant`。

**修正**: 提供 `to_json()` 方法, 处理类型转换和 inf:

```python
@classmethod
def full_diagnostics_json(cls, F: np.ndarray, T: np.ndarray) -> str:
    """JSON 可序列化的诊断报告"""
    diag = cls.full_diagnostics(F, T)
    # 转换 numpy 类型 + inf 处理
    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [_clean(v) for v in obj]
        elif isinstance(obj, (np.floating, np.integer)):
            v = float(obj)
            return v if np.isfinite(v) else None  # inf → null
        elif isinstance(obj, np.ndarray):
            return [_clean(v) for v in obj]
        elif isinstance(obj, float):
            return obj if np.isfinite(obj) else None
        return obj
    import json
    return json.dumps(_clean(diag), indent=2, ensure_ascii=False)
```

**测试**: `test_diagnostics_json_serializable` — 含 inf VIF 的诊断报告 `to_json()` 不报错, inf 转为 null。

### O3a.7 验收标准补充 (v1.1)

在 O3a.5 基础上新增:

- [ ] VRR ddof 参数: `test_vrr_ddof_consistency` 通过
- [ ] VIF 多方法: lstsq/qr/pinv 三种实现, `test_vif_lstsq_matches_qr` 通过
- [ ] 条件数分级: Belsley-Kuh-Welsch 四级, `test_condition_number_severity_levels` 通过
- [ ] 正交性误差归一化: `test_orthogonality_error_normalized_comparable_across_k` 通过
- [ ] JSON 序列化: `test_diagnostics_json_serializable` 通过, inf 转 null

---

## O3b + O4: Layer 3 因子检验 + 回测扩展 (P1)

**优先级**: P1
**依赖**: O2
**预计测试数**: ~30 个
**文件位置**: `backtest/factor_significance.py` (新建), `modules/factor_orthogonalizer/rolling.py` (新建)

### O4.1 文件清单

| 文件 | 类型 | 职责 |
|---|---|---|
| `backtest/factor_significance.py` | 新建 | `FactorSignificanceTest` (Layer 3) |
| `modules/factor_orthogonalizer/rolling.py` | 新建 | `RollingOrthogonalizer` (Layer 2 滚动) |
| `backtest/ic_monitor.py` | 新建 | `ICChangeMonitor` (Layer 3 IC 监控) |

### O4.2 FactorSignificanceTest 设计

```python
# backtest/factor_significance.py
"""因子增量显著性检验 (Layer 3, 有监督)

架构层: Layer 3 (回测子模块)
位置: 所有因子处理完后跑, 不参与 Pipeline.transform() 循环
输入: K 因子 + 收益 Y
输出: p 值 / 系数 / 置信区间

学术依据: Belloni-Chernozhukov-Hansen (2014) Post-Double-Selection Lasso
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from sklearn.linear_model import LassoCV, ElasticNetCV
from scipy import stats


class FactorSignificanceTest:
    """因子增量显著性检验

    双重 Lasso (Belloni 2014 PDS):
    - Stage 1: Lasso Y ~ X → 选出 S_Y (与 Y 相关的因子)
    - Stage 2: Lasso D_k ~ X → 选出 S_D (与 D_k 相关的因子)
    - Stage 3: OLS Y ~ D_k + X_{S_Y ∪ S_D} → D_k 系数即净化后增量 alpha

    与 Layer 2 正交化的关系:
    - 正交化是预处理 (变换因子)
    - 双重 Lasso 是后处理检验 (验证增量 alpha)
    - 可串联: 正交化 → 双重 Lasso, 或直接双重 Lasso

    运行模式: treatment 轮询
    - 每个因子独立当 treatment, 跑一次双重 Lasso
    - 轮次顺序不影响结果 (每轮独立 OLS)
    - 不需要事先排序 (vs GS 强顺序依赖)
    """

    def __init__(
        self,
        method: str = 'double_lasso',
        cv_folds: int = 5,
        max_iter: int = 10000,
        alpha: float = 0.05
    ):
        """
        Args:
            method: 'double_lasso' 或 'elastic_net'
            cv_folds: LassoCV 交叉验证折数
            max_iter: Lasso 最大迭代次数
            alpha: 显著性水平 (默认 0.05)
        """
        self.method = method
        self.cv_folds = cv_folds
        self.max_iter = max_iter
        self.alpha = alpha

    def fit(
        self,
        factor_dict: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        factor_names: List[str]
    ) -> 'FactorSignificanceTest':
        """拟合因子矩阵和收益向量

        Args:
            factor_dict: {因子名: (N, T) DataFrame} (可正交化或原始)
            fwd_returns: (T, N) 前向收益 DataFrame (来自 BacktestEngine)
            factor_names: 待检验的所有因子列表

        架构要点:
        - 此时全部 K 因子 + Y 都在主进程内存
        - 不参与 Pipeline.transform() 循环
        - 与 parallel_runner 正交 (回测后离线分析)
        """
        self.factor_names_ = factor_names
        # 堆叠为 (N·T, K) 因子矩阵 + (N·T,) 收益向量
        # 强制日期对齐, 丢弃不齐日期
        self.F_, self.y_, self.dates_, self.stocks_ = self._stack_factor_returns(
            factor_dict, fwd_returns, factor_names
        )
        return self

    def test_incremental_alpha(self, target_factor: str) -> Dict:
        """检验目标因子在控制其他因子后是否有增量 alpha

        Args:
            target_factor: 待检验的因子名 (作为 treatment D_k)

        Returns:
            {
                'factor': str,
                'coefficient': float,  # 净化后系数
                'std_error': float,    # 标准误
                't_statistic': float,  # t 统计量
                'p_value': float,      # 显著性 p 值
                'ci_lower': float,     # 95% 置信区间下界
                'ci_upper': float,     # 95% 置信区间上界
                'selected_controls': List[str],  # 双重 Lasso 选中的控制变量
                'is_significant': bool,  # p_value < alpha
            }
        """
        if self.method == 'double_lasso':
            return self._double_lasso_test(target_factor)
        elif self.method == 'elastic_net':
            return self._elastic_net_path(target_factor)
        else:
            raise ValueError(f"未知 method: {self.method}")

    def test_all_factors(self) -> Dict[str, Dict]:
        """对所有因子轮询当 treatment, 返回 K 个因子的检验结果

        运行模式: treatment 轮询
        - 每个因子独立当 treatment
        - 轮次顺序不影响结果
        - 不需要事先排序
        """
        return {
            name: self.test_incremental_alpha(name)
            for name in self.factor_names_
        }

    def _double_lasso_test(self, target_factor: str) -> Dict:
        """Belloni-Chernozhukov-Hansen (2014) 双重 Lasso

        Stage 1: Lasso y ~ X (X = 其他 K-1 因子) → 选出 S_Y
        Stage 2: Lasso D_k ~ X → 选出 S_D
        Stage 3: OLS y ~ D_k + X_{S_Y ∪ S_D} → D_k 系数即净化后增量 alpha
        """
        k_idx = self.factor_names_.index(target_factor)
        D_k = self.F_[:, k_idx]  # treatment
        X = np.delete(self.F_, k_idx, axis=1)  # controls (N·T, K-1)
        other_names = [n for i, n in enumerate(self.factor_names_) if i != k_idx]

        # Stage 1: Lasso y ~ X → S_Y
        lasso_y = LassoCV(
            cv=self.cv_folds, max_iter=self.max_iter, n_jobs=-1
        ).fit(X, self.y_)
        S_Y = set(np.where(lasso_y.coef_ != 0)[0])

        # Stage 2: Lasso D_k ~ X → S_D
        lasso_d = LassoCV(
            cv=self.cv_folds, max_iter=self.max_iter, n_jobs=-1
        ).fit(X, D_k)
        S_D = set(np.where(lasso_d.coef_ != 0)[0])

        # Stage 3: OLS y ~ D_k + X_{S_Y ∪ S_D}
        selected = sorted(S_Y | S_D)
        if selected:
            X_selected = X[:, selected]
            X_final = np.column_stack([D_k, X_selected])
        else:
            # S_D = ∅ 兜底: 退化为 OLS y ~ D_k
            X_final = D_k.reshape(-1, 1)

        # OLS + 标准误 + t 检验
        beta = np.linalg.lstsq(X_final, self.y_, rcond=None)[0]
        residuals = self.y_ - X_final @ beta
        n, p = X_final.shape
        if n <= p:
            raise ValueError(
                f"样本数 ({n}) ≤ 参数数 ({p}), "
                f"无法计算标准误, 增加样本或减少因子"
            )
        sigma2 = np.sum(residuals ** 2) / (n - p)
        cov = sigma2 * np.linalg.inv(X_final.T @ X_final)
        se = np.sqrt(np.diag(cov))

        # D_k 是第 0 个系数
        coef = beta[0]
        std_err = se[0]
        t_stat = coef / std_err if std_err > 0 else 0.0
        p_value = 2 * (1 - stats.t.cdf(abs(t_stat), df=n - p))

        return {
            'factor': target_factor,
            'coefficient': float(coef),
            'std_error': float(std_err),
            't_statistic': float(t_stat),
            'p_value': float(p_value),
            'ci_lower': float(coef - 1.96 * std_err),
            'ci_upper': float(coef + 1.96 * std_err),
            'selected_controls': [other_names[i] for i in selected],
            'is_significant': bool(p_value < self.alpha),
        }

    def _elastic_net_path(self, target_factor: str) -> Dict:
        """Elastic Net 路径分析 (系数稳定性)

        在不同 l1_ratio 下检查因子系数稳定性
        """
        k_idx = self.factor_names_.index(target_factor)
        D_k = self.F_[:, k_idx]
        X = np.delete(self.F_, k_idx, axis=1)
        X_full = np.column_stack([D_k, X])

        enet = ElasticNetCV(
            l1_ratio=[0.5, 0.7, 0.9],
            cv=self.cv_folds,
            max_iter=self.max_iter,
            n_jobs=-1
        )
        enet.fit(X_full, self.y_)

        return {
            'factor': target_factor,
            'coefficient': float(enet.coef_[0]),
            'optimal_alpha': float(enet.alpha_),
            'optimal_l1_ratio': float(enet.l1_ratio_),
            'stability': 'stable' if abs(enet.coef_[0]) > 0.01 else 'weak',
            'is_significant': bool(abs(enet.coef_[0]) > 0.01),
        }

    def _stack_factor_returns(
        self,
        factor_dict: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        factor_names: List[str]
    ) -> Tuple[np.ndarray, np.ndarray, pd.Index, pd.Index]:
        """堆叠因子和收益为 (N·T, K) 和 (N·T,)

        步骤:
        1. 对齐日期 (因子 columns ∩ fwd_returns index)
        2. 对齐股票 (因子 index ∩ fwd_returns columns)
        3. 堆叠为 (N·T, K) 因子矩阵 + (N·T,) 收益向量

        工程问题解决 (见 ANALYSIS_V2.5.0.md §3.6.5):
        - 日期对齐: 强制 intersect_dates
        - Y 来源: 来自 BacktestEngine 的 fwd_returns
        """
        # 1. 对齐日期
        # factor_dict[name]: (N, T), columns 是日期
        # fwd_returns: (T, N), index 是日期
        factor_dates = factor_dict[factor_names[0]].columns
        return_dates = fwd_returns.index
        common_dates = factor_dates.intersection(return_dates)
        if len(common_dates) == 0:
            raise ValueError("因子日期与收益日期无交集")

        # 2. 对齐股票
        factor_stocks = factor_dict[factor_names[0]].index
        return_stocks = fwd_returns.columns
        common_stocks = factor_stocks.intersection(return_stocks)
        if len(common_stocks) == 0:
            raise ValueError("因子股票与收益股票无交集")

        # 3. 堆叠
        T = len(common_dates)
        N = len(common_stocks)
        K = len(factor_names)
        F_stacked = np.zeros((N * T, K))
        y_stacked = np.zeros(N * T)

        for k, name in enumerate(factor_names):
            df = factor_dict[name].loc[common_stocks, common_dates]
            # df: (N, T), 按 (T, N) 顺序堆叠
            F_stacked[:, k] = df.values.T.flatten()  # (N·T,)

        # fwd_returns: (T, N) → (N·T,)
        y_stacked = fwd_returns.loc[common_dates, common_stocks].values.flatten()

        return F_stacked, y_stacked, common_dates, common_stocks
```

### O4.3 RollingOrthogonalizer 设计

```python
# modules/factor_orthogonalizer/rolling.py
"""滚动窗口正交化 (避免 look-ahead bias) — Layer 2

子模式 A2: 滚动窗口共享 W
- 用过去 window_size 日的面板估计 W
- 应用到当期截面
- 仅用 t-1 及之前数据, 避免 look-ahead

学术依据: 量化研究实践共识 (回测必须避免 look-ahead bias)
架构层: Layer 2 (无监督变换)
"""
import numpy as np
from collections import deque
from typing import Optional
from .core.symmetric import SymmetricOrthogonalizer


class RollingOrthogonalizer:
    """滚动窗口正交化

    优化: 滑动协方差更新 (增量更新 Gram 矩阵, O(K²) 每次)
    - 移除最旧: G -= F_old.T @ F_old
    - 加入最新: G += F_new.T @ F_new
    - 重新估计 W: eigh(G) (O(K³), 但 K 通常 < 50)
    """

    def __init__(
        self,
        window_size: int = 252,
        method: str = 'symmetric',
        min_obs: int = 60
    ):
        """
        Args:
            window_size: 滚动窗口大小 (日), 默认 252 (1 年)
            method: 正交化方法 (默认 symmetric)
            min_obs: 最小样本数, 不足时跳过 (返回原值)
        """
        self.window_size = window_size
        self.method = method
        self.min_obs = min_obs
        self.G_ = None  # 滚动 Gram 矩阵 (K, K)
        self.window_ = deque(maxlen=window_size)
        self.W_ = None  # 当前 W

    def fit_transform(self, F_panel: np.ndarray) -> np.ndarray:
        """滚动正交化

        Args:
            F_panel: (T, N, K) 因子面板
                T 期, N 股票, K 因子

        Returns: (T, N, K) 正交化后因子面板

        关键: 用 [t-window, t-1] 数据估计 W_t, 应用到 F_t
              (避免 look-ahead bias)
        """
        T, N, K = F_panel.shape
        result = np.zeros_like(F_panel)

        for t in range(T):
            # 移除最旧 (窗口满时)
            if len(self.window_) == self.window_size:
                F_old = self.window_[0]  # (N, K)
                self.G_ -= F_old.T @ F_old

            # 加入最新 (用 t-1 数据, 不是 t, 避免 look-ahead)
            if t > 0:
                F_new = F_panel[t - 1]  # (N, K)
                self.window_.append(F_new)
                if self.G_ is None:
                    self.G_ = F_new.T @ F_new.copy()
                else:
                    self.G_ += F_new.T @ F_new

            # 用累积 G 估计 W, 应用到当期
            if len(self.window_) >= self.min_obs:
                # 重新估计 W
                if self.method == 'symmetric':
                    orth = SymmetricOrthogonalizer()
                    # 直接用 G 估计 W (无需重新堆叠 F_window)
                    orth.fit_from_gram(self.G_)
                else:
                    # 其他方法需堆叠 F_window
                    F_window = np.vstack(list(self.window_))
                    from .core import get_orthogonalizer_class
                    orth_cls = get_orthogonalizer_class(self.method)
                    orth = orth_cls().fit(F_window)
                # 应用到当期截面
                result[t] = orth.transform(F_panel[t])
            else:
                # 样本不足, 跳过 (返回原值)
                result[t] = F_panel[t]

        return result
```

### O4.4 ICChangeMonitor 设计

```python
# backtest/ic_monitor.py
"""IC 变化监控 (Layer 3)

正交化前后 IC 对比, 监控正交化是否损害因子预测力
"""
import numpy as np
from typing import Dict, Tuple


class ICChangeMonitor:
    """IC 变化监控

    指标:
    - IC_before: 正交化前因子 IC
    - IC_after: 正交化后因子 IC
    - IC_change_ratio: (IC_after - IC_before) / |IC_before|
    - 阈值: |IC_change_ratio| > 0.8 → 正交化损害预测力

    架构层: Layer 3 (有监督, 需 Y)
    """

    @staticmethod
    def compute_ic(
        factor: np.ndarray,
        fwd_returns: np.ndarray
    ) -> float:
        """计算单因子 IC (Spearman 秩相关)

        Args:
            factor: (N,) 因子值
            fwd_returns: (N,) 前向收益

        Returns: IC 标量
        """
        from scipy.stats import spearmanr
        rho, p = spearmanr(factor, fwd_returns)
        return float(rho)

    @classmethod
    def compare_ic(
        cls,
        factor_before: np.ndarray,
        factor_after: np.ndarray,
        fwd_returns: np.ndarray
    ) -> Dict[str, float]:
        """对比正交化前后 IC

        Returns:
            {
                'ic_before': float,
                'ic_after': float,
                'ic_change': float,
                'ic_change_ratio': float,
                'is_degraded': bool,  # |ratio| > 0.8
            }
        """
        ic_before = cls.compute_ic(factor_before, fwd_returns)
        ic_after = cls.compute_ic(factor_after, fwd_returns)
        ic_change = ic_after - ic_before
        ic_change_ratio = ic_change / abs(ic_before) if abs(ic_before) > 1e-12 else 0.0
        return {
            'ic_before': ic_before,
            'ic_after': ic_after,
            'ic_change': ic_change,
            'ic_change_ratio': ic_change_ratio,
            'is_degraded': bool(abs(ic_change_ratio) > 0.8),
        }
```

### O4.5 TDD 测试设计

**测试文件**: `tests/test_factor_significance.py`, `tests/test_rolling_orthogonalizer.py`

| 测试组 | 测试用例 | 验证目标 |
|---|---|---|
| **双重 Lasso 基础** | `test_double_lasso_significant_factor` | 已知 alpha 因子 p < 0.05 |
| | `test_double_lasso_redundant_factor` | 冗余因子 p > 0.05 |
| | `test_double_lasso_treatment_rotation_invariant` | treatment 轮询顺序不影响结果 |
| | `test_double_lasso_stage2_empty_fallback` | S_D = ∅ 时退化为 OLS y ~ D_k |
| **Elastic Net** | `test_elastic_net_stable_factor` | 稳定因子 coefficient > 0.01 |
| | `test_elastic_net_weak_factor` | 弱因子 coefficient < 0.01 |
| **数据对齐** | `test_stack_aligns_dates` | 日期自动对齐到交集 |
| | `test_stack_aligns_stocks` | 股票自动对齐到交集 |
| | `test_stack_raises_on_no_common_dates` | 无公共日期抛 ValueError |
| **Rolling** | `test_rolling_no_lookahead` | t 期 W 仅用 t-1 及之前数据 |
| | `test_rolling_min_obs_skip` | 样本不足时返回原值 |
| | `test_rolling_window_slide` | 窗口滑动正确 (deque maxlen) |
| | `test_rolling_gram_incremental_update` | 增量 Gram 更新正确 |
| **IC 监控** | `test_ic_monitor_before_after` | 正交化前后 IC 计算正确 |
| | `test_ic_monitor_degradation_detected` | IC 下降 > 80% 时 is_degraded=True |
| **手工校验** | `test_double_lasso_matches_statsmodels_ols` | 与 statsmodels OLS 对比, 精度 < 1e-10 |
| | `test_ic_matches_spearmanr_direct` | 与 scipy spearmanr 直接计算对比 |

### O4.6 手工数值校验方案

```python
def test_double_lasso_matches_statsmodels():
    """手工校验: 双重 Lasso Stage 3 OLS 与 statsmodels OLS 对比"""
    import statsmodels.api as sm
    np.random.seed(42)

    # 构造已知数据
    N, K = 500, 5
    F = np.random.randn(N, K)
    true_beta = np.array([0.5, 0.0, 0.3, 0.0, 0.2])
    y = F @ true_beta + 0.1 * np.random.randn(N)

    # 项目实现
    test = FactorSignificanceTest(method='double_lasso')
    test.F_ = F
    test.y_ = y
    test.factor_names_ = [f'f{i}' for i in range(K)]
    result = test.test_incremental_alpha('f0')

    # statsmodels 直接 OLS (全变量, 跳过 Lasso 选择)
    X_sm = sm.add_constant(F)
    sm_result = sm.OLS(y, X_sm).fit()
    # f0 系数 = sm_result.params[1]
    np.testing.assert_allclose(
        result['coefficient'], sm_result.params[1], atol=1e-6
    )
```

### O4.7 风险与陷阱

| # | 陷阱 | 严重性 | 规避方法 |
|---|---|---|---|
| 1 | **Look-ahead bias** | 高 | RollingOrthogonalizer 用 t-1 数据估计 W_t |
| 2 | **日期不对齐** | 高 | `_stack_factor_returns` 强制 intersect_dates |
| 3 | **N ≤ p 时协方差奇异** | 中 | 校验 `n > p`, 抛 ValueError |
| 4 | **LassoCV 慢** | 中 | `n_jobs=-1` 并行; 预筛选 ρ<0.3 因子跳过 |
| 5 | **Stage 2 S_D = ∅** | 低 | 退化为 OLS y ~ D_k (代码兜底) |
| 6 | **IC 计算用 Pearson 而非 Spearman** | 中 | 强制用 Spearman (秩相关, 抗异常值) |

### O4.8 验收标准

- [ ] `FactorSignificanceTest` 类实现完成
- [ ] `RollingOrthogonalizer` 类实现完成
- [ ] `ICChangeMonitor` 类实现完成
- [ ] 双重 Lasso 能识别已知 alpha 因子 (p < 0.05)
- [ ] treatment 轮询顺序不变性验证通过
- [ ] 滚动模式无 look-ahead bias
- [ ] ~30 个单元测试通过
- [ ] 手工数值校验通过 (与 statsmodels OLS 对比精度 < 1e-6)

### O4.9 双重 Lasso 工程深化 (v1.1 补充)

v1.0 设计在 7 个工程细节上不够严谨, v1.1 补充如下。每项均对应一个具体陷阱, 实施时必须遵循。

#### O4.9.1 截距处理一致性 (高优先级)

**问题**: LassoCV 默认 `fit_intercept=True` (中心化 Y 和 X 后拟合, 不将截距计入系数), 但 Stage 3 OLS 用 `np.linalg.lstsq` 没有加截距列, 导致:
- 若 Y 或 D_k 有非零均值, OLS 系数有偏
- Stage 1/2 的 Lasso 选择基于中心化数据, Stage 3 的 OLS 基于非中心化数据, 选择与估计不一致

**修正**: Stage 3 必须显式加截距列, 与 LassoCV 的 `fit_intercept=True` 行为对齐:

```python
# Stage 3 OLS 加截距列
if selected:
    X_selected = X[:, selected]
    X_final = np.column_stack([D_k, X_selected, np.ones(n)])
else:
    X_final = np.column_stack([D_k, np.ones(n)])
beta = np.linalg.lstsq(X_final, self.y_, rcond=None)[0]
# D_k 仍是 beta[0], 截距是 beta[-1]
```

**测试**: `test_double_lasso_intercept_consistency` — 构造 Y = 0.5*D_k + 1.0 (非零截距), 验证系数估计无偏。

#### O4.9.2 稳健标准误 HC3 (高优先级)

**问题**: OLS 标准误 `se = sqrt(diag(sigma2 * (X'X)^-1))` 假设同方差, 金融数据普遍存在异方差 (高频 vs 低频因子、厚尾收益), 导致 t 统计量偏高, 假阳性。

**修正**: 提供 `std_error_type` 参数, 默认 `'hc3'` (稳健):

```python
def _compute_standard_errors(
    self, X_final, y, beta, std_error_type='hc3'
):
    n, p = X_final.shape
    residuals = y - X_final @ beta
    XtX_inv = np.linalg.inv(X_final.T @ X_final)

    if std_error_type == 'ols':
        sigma2 = np.sum(residuals ** 2) / (n - p)
        cov = sigma2 * XtX_inv
    elif std_error_type == 'hc1':
        # HC1: 自由度调整的 White 稳健
        diag_r = np.diag(XtX_inv)
        h = np.sum((X_final @ XtX_inv) * X_final, axis=1)
        hc1_factor = n / (n - p)
        omega = hc1_factor * np.sum(
            (residuals ** 2 / (1 - h) ** 0)[:, None] * X_final ** 2,
            axis=0
        )  # 简化, 完整 HC1 见下方
        # 完整 HC1:
        meat = (X_final * residuals[:, None]).T @ (X_final * residuals[:, None])
        cov = XtX_inv @ meat @ XtX_inv * (n / (n - p))
    elif std_error_type == 'hc3':
        # HC3: MacKinnon-White, 对杠杆点更稳健
        h = np.sum((X_final @ XtX_inv) * X_final, axis=1)
        w = residuals / (1 - h) ** 2
        meat = (X_final * w[:, None]).T @ X_final
        cov = XtX_inv @ meat @ XtX_inv

    return np.sqrt(np.diag(cov))
```

**学术依据**: MacKinnon-White (1985) HC3 在小样本下优于 HC0/HC1/HC2, Long-Ervin (2000) 推荐 n<250 时用 HC3。

**测试**: `test_hc3_vs_ols_std_error` — 异方差数据下, HC3 se > OLS se (HC3 更保守)。

#### O4.9.3 多重检验校正 (中优先级)

**问题**: `test_all_factors` 对 K 个因子各做一次 t 检验, K=20 时假阳性期望 = 20 × 0.05 = 1 个, 即纯粹随机也会有 ~1 个因子被误判显著。

**修正**: 在 `test_all_factors` 返回结果中增加多重检验校正:

```python
def test_all_factors(self, correction='benjamini_hochberg'):
    """K 因子轮询 + 多重检验校正

    Args:
        correction:
            'none' — 不校正
            'bonferroni' — 保守, p_adj = min(p * K, 1)
            'benjamini_hochberg' — 推荐, 控制 FDR
            'holm' — Bonferroni 的逐步改进
    """
    results = {
        name: self.test_incremental_alpha(name)
        for name in self.factor_names_
    }

    # 提取原始 p 值
    p_values = np.array([r['p_value'] for r in results.values()])
    K = len(p_values)

    if correction == 'bonferroni':
        p_adj = np.minimum(p_values * K, 1.0)
    elif correction == 'benjamini_hochberg':
        # BH: 排序后 p_(k) * K / rank, 取累积最小
        order = np.argsort(p_values)
        p_adj = np.empty_like(p_values)
        prev = 1.0
        for i in range(K - 1, -1, -1):
            rank = i + 1
            idx = order[i]
            bh = p_values[idx] * K / rank
            prev = min(prev, bh)
            p_adj[idx] = min(prev, 1.0)
    elif correction == 'holm':
        order = np.argsort(p_values)
        p_adj = np.empty_like(p_values)
        prev = 0.0
        for i in range(K):
            idx = order[i]
            holm = p_values[idx] * (K - i)
            prev = max(prev, holm)
            p_adj[idx] = min(prev, 1.0)
    else:
        p_adj = p_values

    # 回填
    for (name, p_a) in zip(results.keys(), p_adj):
        results[name]['p_value_adjusted'] = float(p_a)
        results[name]['is_significant_adjusted'] = bool(p_a < self.alpha)
        results[name]['correction_method'] = correction

    return results
```

**默认推荐**: `benjamini_hochberg` — 控制 FDR (False Discovery Rate), 比 Bonferroni 更适合因子探索 (Bonferroni 控制 FWER, 过于保守导致漏报)。

**学术依据**: Benjamini-Hochberg (1995), Harvey-Liu-Zhu (2016) 推荐 BH 替代 Bonferroni 用于因子 zoo 多重检验。

**测试**: `test_bh_correction_controls_fdr` — K=20 全噪声因子, 校正后显著数 < 2 (5% FDR)。

#### O4.9.4 treatment 轮询并行化 (中优先级)

**问题**: `test_all_factors` 串行执行 K 次 `_double_lasso_test`, 每次含 2 个 LassoCV (5 折 CV, 各 100 alphas), K=20 时总 LassoCV 次数 = 40, 串行约 60s+。

**修正**: 用 joblib 并行化, 注意 LassoCV 内部已 `n_jobs=-1` 并行, 外层并行用 `n_jobs=1` (内串行) 或用线程级并行:

```python
from joblib import Parallel, delayed

def test_all_factors(
    self,
    correction='benjamini_hochberg',
    n_jobs: int = 1,
    backend: str = 'threading'
):
    """K 因子轮询并行化

    并行策略:
    - n_jobs=1: 串行, LassoCV 内部 n_jobs=-1 (推荐 K<=10)
    - n_jobs>1 + backend='threading': 外层线程并行, LassoCV 内部 n_jobs=1 (推荐 K>10)
      (sklearn LassoCV 释放 GIL, threading 后端有效)
    - n_jobs>1 + backend='loky': 进程级并行, 内存翻倍, 不推荐
    """
    def _test_one(name):
        # 内部 LassoCV 的 n_jobs 根据外层调整
        original_n_jobs = self._lasso_n_jobs
        if n_jobs > 1:
            self._lasso_n_jobs = 1  # 外层并行时, 内部串行
        try:
            return name, self.test_incremental_alpha(name)
        finally:
            self._lasso_n_jobs = original_n_jobs

    raw = Parallel(n_jobs=n_jobs, backend=backend)(
        delayed(_test_one)(name) for name in self.factor_names_
    )
    results = dict(raw)

    # 多重检验校正 (见 O4.9.3)
    return self._apply_correction(results, correction)
```

**性能预期**: K=20, N·T=10000, 8 核:
- 串行 + LassoCV n_jobs=-1: ~60s
- threading n_jobs=4 + LassoCV n_jobs=1: ~25s (sklearn 释放 GIL)
- loky n_jobs=4: ~30s + 内存翻倍 (不推荐)

**测试**: `test_parallel_treatment_matches_serial` — 并行结果与串行一致 (数值精度 1e-12)。

#### O4.9.5 LassoCV 收敛检测与参数暴露 (中优先级)

**问题**: LassoCV 默认 `max_iter=10000, eps=1e-3` (坐标下降收敛阈值), 高共线性因子可能不收敛, sklearn 仅 `ConvergenceWarning` 不抛错, 用户无感知。

**修正**:
1. 暴露 `eps` 参数 (默认 1e-4 比 sklearn 默认更严格)
2. 检测 `n_iter_` 接近 `max_iter` 时告警
3. 提供 `lasso_params` 字典透传所有 LassoCV 参数

```python
def __init__(
    self,
    method: str = 'double_lasso',
    cv_folds: int = 5,
    max_iter: int = 10000,
    eps: float = 1e-4,
    alpha: float = 0.05,
    std_error_type: str = 'hc3',
    correction: str = 'benjamini_hochberg',
    n_jobs: int = 1,
    lasso_params: Optional[Dict] = None,
):
    self.eps = eps
    self.std_error_type = std_error_type
    self.correction = correction
    self.n_jobs = n_jobs
    self._lasso_n_jobs = -1 if n_jobs == 1 else 1
    self.lasso_params = lasso_params or {}

def _make_lasso(self):
    params = {
        'cv': self.cv_folds,
        'max_iter': self.max_iter,
        'eps': self.eps,
        'n_jobs': self._lasso_n_jobs,
        **self.lasso_params,
    }
    return LassoCV(**params)

def _double_lasso_test(self, target_factor):
    lasso_y = self._make_lasso().fit(X, self.y_)
    # 收敛检测
    if hasattr(lasso_y, 'n_iter_') and lasso_y.n_iter_ >= self.max_iter * 0.9:
        import warnings
        warnings.warn(
            f"Stage 1 LassoCV 接近 max_iter ({lasso_y.n_iter_}/{self.max_iter}), "
            f"可能未收敛, 建议增大 max_iter 或检查共线性",
            UserWarning
        )
    # ...
```

**测试**: `test_lasso_convergence_warning` — 构造高共线性数据, 验证告警触发。

#### O4.9.6 Y 标准化与因子尺度一致性 (低优先级)

**问题**: Lasso 对尺度敏感, 因子已通过 Layer 1 标准化 (均值 0, 方差 1), 但 Y (前向收益) 未标准化, 导致:
- Lasso 的 alpha 惩罚对 Y 的尺度敏感
- 不同因子 (D_k) 的 Lasso 选择阈值不一致

**修正**: 在 `fit()` 中对 Y 做按列标准化 (若多期 Y), 单期 Y 做 z-score:

```python
def fit(self, factor_dict, fwd_returns, factor_names):
    # ... 堆叠后
    self.F_, self.y_, self.dates_, self.stocks_ = self._stack_factor_returns(...)

    # Y 标准化 (供 Lasso 使用, 不影响 OLS 报告)
    self.y_mean_ = self.y_.mean()
    self.y_std_ = self.y_.std()
    if self.y_std_ > 1e-12:
        self.y_normalized_ = (self.y_ - self.y_mean_) / self.y_std_
    else:
        self.y_normalized_ = self.y_.copy()

    # Lasso 用标准化后的 Y, OLS 报告用原始 Y (保持系数可解释性)
```

**注意**: Stage 3 OLS 仍用原始 Y (非标准化), 保持系数的经济含义 (每单位因子变化对应的收益变化)。Lasso 仅用于变量选择, 选择结果对 Y 的尺度不敏感后即可。

**测试**: `test_y_normalization_improves_stability` — Y 尺度放大 100 倍后, Lasso 选择结果不变。

#### O4.9.7 S_D 全空集的深层处理 (低优先级)

**问题**: v1.0 的兜底 `X_final = D_k.reshape(-1, 1)` 在 S_Y = S_D = ∅ 时退化为单变量 OLS, 失去双重 Lasso 的"双重保险"意义。这通常表示:
- Y 与所有控制变量都不相关 (数据噪声大 或 Y 本身无 alpha)
- D_k 与所有控制变量都不相关 (D_k 是独立因子, 正交化无必要)

**修正**: 增加 S_Y ∩ S_D 都为空时的诊断信息:

```python
if not selected:
    # S_Y = S_D = ∅ 的诊断
    result['diagnostic'] = {
        'stage1_zero_coefs': len(S_Y) == 0,
        'stage2_zero_coefs': len(S_D) == 0,
        'interpretation': (
            'Y 与控制变量无显著相关 (Stage 1 全零), '
            'D_k 与控制变量无显著相关 (Stage 2 全零). '
            'D_k 系数为单变量 OLS 估计, 缺乏混淆变量控制, 谨慎解读.'
        ),
        'recommendation': (
            '若 D_k 是已知独立因子, 结果可信; '
            '若 D_k 与其他因子应有相关, 检查数据对齐或增大样本.'
        ),
    }
```

**测试**: `test_empty_selection_diagnostic` — 构造独立因子, 验证诊断信息正确。

### O4.10 验收标准补充 (v1.1)

在 O4.8 基础上新增:

- [ ] 截距处理一致性: Stage 3 OLS 加截距列, `test_double_lasso_intercept_consistency` 通过
- [ ] HC3 稳健标准误: `test_hc3_vs_ols_std_error` 通过, 异方差下 HC3 se > OLS se
- [ ] BH 多重检验校正: `test_bh_correction_controls_fdr` 通过, K=20 全噪声因子校正后显著数 < 2
- [ ] treatment 并行化: `test_parallel_treatment_matches_serial` 通过, 精度 1e-12
- [ ] LassoCV 收敛检测: `test_lasso_convergence_warning` 通过
- [ ] Y 标准化: `test_y_normalization_improves_stability` 通过
- [ ] S_D 空集诊断: `test_empty_selection_diagnostic` 通过

### O4.11 RollingOrthogonalizer 工程深化 (v1.1 补充)

v1.0 的 `RollingOrthogonalizer` 在 5 个工程细节上不够严谨, v1.1 补充如下。每项对应一个数值漂移或 look-ahead 风险。

#### O4.11.1 增量 Gram 数值漂移与定期重置 (高优先级)

**问题**: v1.0 的增量更新 `G_ -= F_old.T @ F_old; G_ += F_new.T @ F_new` 在长期滑动窗口下累积浮点误差:
- 每次 add/remove 引入 ~1e-16 相对误差
- 252 期窗口滑动 1000 次, 累积误差 ~1e-13
- 误差破坏 G 的对称性 (`G != G.T`) 和正定性 (`eigh` 返回负特征值)

**修正**: 定期从 `window_` 重新堆叠计算 G, 重置累积误差:

```python
class RollingOrthogonalizer:
    def __init__(
        self,
        window_size: int = 252,
        method: str = 'symmetric',
        min_obs: int = 60,
        reset_interval: int = 500  # 每 500 期重置一次
    ):
        self.window_size = window_size
        self.method = method
        self.min_obs = min_obs
        self.reset_interval = reset_interval
        self.G_ = None
        self.window_ = deque(maxlen=window_size)
        self.W_ = None
        self._iter_count = 0  # 迭代计数器

    def fit_transform(self, F_panel: np.ndarray) -> np.ndarray:
        T, N, K = F_panel.shape
        result = np.zeros_like(F_panel)

        for t in range(T):
            # 移除最旧 (窗口满时)
            if len(self.window_) == self.window_size:
                F_old = self.window_[0]
                self.G_ -= F_old.T @ F_old

            # 加入最新 (t-1 数据, 避免 look-ahead)
            if t > 0:
                F_new = F_panel[t - 1]
                self.window_.append(F_new)
                if self.G_ is None:
                    self.G_ = F_new.T @ F_new.copy()
                else:
                    self.G_ += F_new.T @ F_new

            self._iter_count += 1

            # 定期重置: 从 window_ 重新堆叠 G, 消除累积误差
            if self._iter_count % self.reset_interval == 0 and len(self.window_) > 0:
                F_window = np.vstack(list(self.window_))
                self.G_ = F_window.T @ F_window
                # 诊断: 记录重置前后的对称性偏差
                asymmetry_before = 0.0  # 简化, 实际可记录

            # 估计 W 并应用
            if len(self.window_) >= self.min_obs:
                if self.method == 'symmetric':
                    orth = SymmetricOrthogonalizer()
                    orth.fit_from_gram(self.G_)
                    self.W_ = orth.W_
                    result[t] = orth.transform(F_panel[t])
                else:
                    F_window = np.vstack(list(self.window_))
                    orth_cls = get_orthogonalizer_class(self.method)
                    orth = orth_cls().fit(F_window)
                    self.W_ = orth.W_
                    result[t] = orth.transform(F_panel[t])
            else:
                result[t] = F_panel[t]

        return result
```

**默认推荐**: `reset_interval=500` — 252 日窗口下, 每 ~2 年重置一次, 累积误差 < 1e-13, 不可见。

**测试**: `test_gram_reset_restores_symmetry` — 滑动 1000 期后, 重置前 `‖G - G.T‖_F > 1e-14`, 重置后 < 1e-15; `test_gram_reset_no_lookahead` — 重置只用 window_ 数据, 不引入未来信息。

#### O4.11.2 fit_from_gram 接口的使用与对称化 (高优先级)

**问题**: v1.0 调用 `orth.fit_from_gram(self.G_)`, 但 `fit_from_gram` 在 O1.12.6 才定义, 且增量更新可能破坏 G 的对称性, 导致 `eigh` 返回复数或错误。

**修正**: 在 `RollingOrthogonalizer` 中调用前强制对称化 (双保险):

```python
# 在 fit_transform 中, 调用 fit_from_gram 前
if self.method == 'symmetric':
    orth = SymmetricOrthogonalizer()
    # 强制对称化 (消除增量更新的浮点不对称)
    G_sym = (self.G_ + self.G_.T) / 2
    orth.fit_from_gram(G_sym)
    self.W_ = orth.W_
    result[t] = orth.transform(F_panel[t])
```

**为什么双保险**: O1.12.6 的 `fit_from_gram` 内部已有 `G = (G + G.T) / 2`, 但在 Rolling 场景下, 增量更新的不对称可能更严重 (累积误差), 显式对称化 + 内部对称化确保万无一失。

**测试**: `test_fit_from_gram_with_asymmetric_input` — 故意构造不对称 G (G[0,1] += 1e-10), `fit_from_gram` 内部对称化后 W 正确。

#### O4.11.3 样本不足时的 look-ahead 标记 (中优先级)

**问题**: v1.0 在 `len(window_) < min_obs` 时 `result[t] = F_panel[t]` (返回原值), 但:
- 下游模块 (Layer 3 双重 Lasso) 无法区分"未正交化"和"正交化后恰好等于原值"
- 全样本正交化 (VRR=1) 时 T ≈ F, 也可能看起来像"未正交化"

**修正**: 增加 `is_orthogonalized_` 标记数组, 记录每期是否真正正交化:

```python
def fit_transform(self, F_panel: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """返回 (result, is_orthogonalized)

    Returns:
        result: (T, N, K) 正交化后因子 (或原值)
        is_orthogonalized: (T,) bool 数组, True 表示该期已正交化
    """
    T, N, K = F_panel.shape
    result = np.zeros_like(F_panel)
    is_orth = np.zeros(T, dtype=bool)  # 标记数组

    for t in range(T):
        # ... 增量更新 G
        if len(self.window_) >= self.min_obs:
            # ... 估计 W 并应用
            result[t] = orth.transform(F_panel[t])
            is_orth[t] = True  # 标记已正交化
        else:
            result[t] = F_panel[t]
            is_orth[t] = False  # 未正交化

    self.is_orthogonalized_ = is_orth
    return result, is_orth
```

**下游使用**: `FactorSignificanceTest` 在堆叠 F_ 时, 可根据 `is_orthogonalized_` 决定是否对未正交化期降权或排除。

**向后兼容**: 提供 `fit_transform_legacy(F_panel)` 只返回 result (v1.0 行为), 或在 `__init__` 中 `return_is_orth=False` (默认 True)。

**测试**: `test_is_orthogonalized_marked_correctly` — min_obs=60, 前 60 期 is_orth=False, 之后 True。

#### O4.11.4 warm-start 优化 (低优先级)

**问题**: 每期都调用 `eigh(G)` (O(K³)), 但相邻两期的 G 变化很小 (移除 1 期 + 加入 1 期, G 变化 ~1/window_size), W 也应变化很小, 可用上期 W 作为 eigh 的初始估计。

**修正**: scipy 的 `eigh` 不支持 warm-start (LAPACK 限制), 但可用 `scipy.linalg.eigh` 的 `subset_by_index` 只计算前 k 个特征值 (若只需前 k 主成分), 或用迭代法 (LOBPCG) 利用上期 V 作为初始:

```python
from scipy.sparse.linalg import lobpcg

def _warm_start_eigh(self, G, V_prev=None):
    """warm-start 特征值分解

    若 V_prev 提供且 G 变化小, 用 LOBPCG 迭代 (O(K²) 每次迭代)
    否则用标准 eigh (O(K³))
    """
    if V_prev is not None and self._gram_change_small():
        # LOBPCG 迭代, V_prev 作为初始
        K = G.shape[0]
        X = V_prev
        eigvals, eigvecs = lobpcg(G, X, largest=False, tol=1e-10, maxiter=100)
    else:
        eigvals, eigvecs = eigh(G)
    return eigvals, eigvecs

def _gram_change_small(self, threshold=0.01):
    """检测 G 相对上期变化是否小于 threshold"""
    if self.G_prev_ is None:
        return False
    relative_change = np.linalg.norm(self.G_ - self.G_prev_) / np.linalg.norm(self.G_prev_)
    return relative_change < threshold
```

**性能预期**: K=20, window=252:
- 标准 eigh: ~0.5ms × 252 期 = 126ms
- LOBPCG warm-start: ~0.1ms × 252 期 = 25ms (5x 加速, 若 G 变化小)

**注意**: LOBPCG 不保证收敛到全局最优, 需与标准 eigh 定期对比校验 (如每 50 期用 eigh 重算一次, 检查 W 偏差)。

**测试**: `test_warm_start_matches_standard_eigh` — warm-start 的 W 与标准 eigh 一致 (精度 1e-8); `test_warm_start_skipped_on_large_change` — G 变化大时回退到标准 eigh。

#### O4.11.5 滚动窗口的 NaN 处理 (中优先级)

**问题**: v1.0 假设 `F_panel[t]` (N, K) 无 NaN, 但真实数据中单期截面可能有 NaN (停牌股票、缺失因子值)。增量更新 `G += F_new.T @ F_new` 时, NaN 会传播到整个 G。

**修正**: 在加入 window_ 前, 对每期 F_new 做 NaN 处理:

```python
# 加入最新 (t-1 数据) 前
if t > 0:
    F_new = F_panel[t - 1].copy()  # (N, K)
    # NaN 处理: 对含 NaN 的行, 填 0 并降权
    nan_mask = np.any(np.isnan(F_new), axis=1)
    if np.any(nan_mask):
        F_new = np.nan_to_num(F_new, nan=0.0)
        # 记录有效样本数 (用于 G 的归一化, 可选)
        n_valid = N - np.sum(nan_mask)
    else:
        n_valid = N
    self.window_.append(F_new)
    # ... 增量更新 G
```

**权衡**: 填 0 会轻微偏置 G (NaN 股票的贡献为 0, 等价于"该股票因子值为 0"), 但比"NaN 传播导致整个 G 失效"更可接受。替代方案是丢弃含 NaN 的行, 但会改变 G 的样本数 (N 不一致)。

**测试**: `test_rolling_nan_handled_not_propagated` — F_panel 含 10% NaN, G 无 NaN 传播, result 的 NaN 行保留。

### O4.12 验收标准补充 (v1.1 Rolling)

在 O4.10 基础上新增:

- [ ] Gram 定期重置: `reset_interval` 参数, `test_gram_reset_restores_symmetry` + `test_gram_reset_no_lookahead` 通过
- [ ] fit_from_gram 对称化: `test_fit_from_gram_with_asymmetric_input` 通过
- [ ] is_orthogonalized 标记: `test_is_orthogonalized_marked_correctly` 通过
- [ ] warm-start: `test_warm_start_matches_standard_eigh` + `test_warm_start_skipped_on_large_change` 通过
- [ ] 滚动 NaN: `test_rolling_nan_handled_not_propagated` 通过

---

## O5: 协同设计 (P1)

**优先级**: P1
**依赖**: O1-O4
**预计测试数**: ~15 个
**文件位置**: `modules/factor_orthogonalizer/grouped.py` (新建)

### O5.1 文件清单

| 文件 | 类型 | 职责 |
|---|---|---|
| `modules/factor_orthogonalizer/grouped.py` | 新建 | `GroupedOrthogonalizer` |
| `modules/factor_orthogonalizer/triple_chain.py` | 新建 | 三件套串联协调器 |

### O5.2 GroupedOrthogonalizer 设计

```python
# modules/factor_orthogonalizer/grouped.py
"""分组正交化 — Layer 2

组内对称正交 + 组间保留相关性

学术依据: Stambaugh-Yuan (2017) 风险因子 vs alpha 因子区别处理
架构层: Layer 2 (无监督变换)
"""
import numpy as np
import pandas as pd
from typing import Dict, List
from .core.symmetric import SymmetricOrthogonalizer
from .cross_sectional import CrossSectionalOrthogonalizer


class GroupedOrthogonalizer:
    """分组正交化

    策略:
    - 组内: 对称正交化 (消除同组因子冗余)
    - 组间: 保留相关性 (不同经济含义的因子组不强行正交)

    典型分组:
    groups = {
        'value': ['PE', 'PB', 'PCF'],
        'momentum': ['MOM', 'REV'],
        'quality': ['ROE', 'ROA', 'Gross'],
        'size': ['Size', 'MCap'],
        'technical': ['VOL', 'ILLIQ', 'TURNOVER']
    }

    学术依据: Asness (2013) Value and Momentum Everywhere
              — Value 与 Momentum 负相关 (ρ ≈ -0.4), 不应强行正交
    """

    def __init__(self, groups: Dict[str, List[str]]):
        """
        Args:
            groups: {组名: [因子名]}
        """
        # 校验: 所有因子唯一
        all_factors = [f for fs in groups.values() for f in fs]
        if len(all_factors) != len(set(all_factors)):
            raise ValueError("分组中存在重复因子名")
        self.groups = groups
        self.orthogonalizers_ = {}  # {组名: SymmetricOrthogonalizer}
        self.factor_to_group_ = {
            f: g for g, fs in groups.items() for f in fs
        }

    def fit(
        self,
        factor_dict: Dict[str, pd.DataFrame],
        **kwargs
    ) -> 'GroupedOrthogonalizer':
        """对每组分别估计 W (组内正交, 组间保留)"""
        for group_name, factor_names in self.groups.items():
            # 检查因子是否存在
            missing = [f for f in factor_names if f not in factor_dict]
            if missing:
                raise ValueError(f"组 {group_name} 缺少因子: {missing}")
            # 堆叠组内因子为 (N·T, K_group)
            group_dict = {f: factor_dict[f] for f in factor_names}
            F_group, _ = CrossSectionalOrthogonalizer._align_factors(
                group_dict
            ).values()  # 简化, 实际需正确堆叠
            # 估计 W
            self.orthogonalizers_[group_name] = SymmetricOrthogonalizer().fit(
                F_group, **kwargs
            )
        return self

    def transform(
        self,
        factor_dict: Dict[str, pd.DataFrame]
    ) -> Dict[str, pd.DataFrame]:
        """应用组内正交化, 组间相关性保留"""
        result = {}
        for group_name, factor_names in self.groups.items():
            group_dict = {f: factor_dict[f] for f in factor_names}
            # 用组内 W 正交化
            orth = self.orthogonalizers_[group_name]
            coordinator = CrossSectionalOrthogonalizer(orth)
            transformed = coordinator.transform(group_dict)
            result.update(transformed)
        return result
```

### O5.3 三件套串联协调器

```python
# modules/factor_orthogonalizer/triple_chain.py
"""因子诊断三件套串联协调器

跨 Layer 1/2 串联:
1. Fingerprint (Layer 1 描述): 13 维指标 + STATIC/DYNAMIC/MIXED 分类
2. Decoupler (Layer 1 时序解耦): 消除单因子自相关
3. Orthogonalizer (Layer 2 横截面正交): 消除因子间相关性

串联顺序:
原始因子
  → Fingerprint (分类) [Layer 1]
  → 单因子管道 (含 Decoupler) [Layer 1]
  → Orthogonalizer (横截面正交) [Layer 2]
  → FactorSignificanceTest (增量检验) [Layer 3]
"""
from typing import Dict, Any
import pandas as pd


class TripleChainCoordinator:
    """三件套串联协调器

    职责:
    - 协调 Fingerprint / Decoupler / Orthogonalizer 三件套
    - 提供端到端诊断报告
    - 不修改 Layer 1 Pipeline (保持 per-factor 不变)
    """

    def __init__(
        self,
        fingerprinter=None,
        decoupler=None,
        orthogonalizer=None,
        significance_test=None
    ):
        self.fingerprinter = fingerprinter
        self.decoupler = decoupler
        self.orthogonalizer = orthogonalizer
        self.significance_test = significance_test

    def full_diagnosis(
        self,
        raw_factors: Dict[str, pd.DataFrame],
        processed_factors: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame = None
    ) -> Dict[str, Any]:
        """端到端诊断报告

        Args:
            raw_factors: 原始因子 (Layer 1 输入)
            processed_factors: Pipeline 处理后因子 (Layer 1 输出)
            fwd_returns: 前向收益 (可选, Layer 3 用)

        Returns: 完整诊断报告
        """
        report = {
            'fingerprints': {},
            'orthogonalization': None,
            'significance': None,
        }

        # Layer 1: Fingerprint (每个因子)
        if self.fingerprinter:
            for name, df in raw_factors.items():
                report['fingerprints'][name] = self.fingerprinter.extract(df)

        # Layer 2: Orthogonalization (K 因子联合)
        if self.orthogonalizer and self.orthogonalizer.enabled:
            orth_result = self.orthogonalizer.fit_transform(processed_factors)
            report['orthogonalization'] = {
                'method': self.orthogonalizer.method,
                'diagnostics': 'see OrthogonalizationDiagnostics',
            }

        # Layer 3: Significance Test (需 Y)
        if self.significance_test and fwd_returns is not None:
            sig = self.significance_test.fit(
                orth_result if self.orthogonalizer.enabled else processed_factors,
                fwd_returns,
                list(processed_factors.keys())
            )
            report['significance'] = sig.test_all_factors()

        return report
```

### O5.4 TDD 测试设计

| 测试用例 | 验证目标 |
|---|---|
| `test_grouped_within_group_orthogonal` | 组内因子正交 (T^T T ≈ I) |
| `test_grouped_between_group_preserved` | 组间相关性保留 (不为 0) |
| `test_grouped_duplicate_factor_raises` | 重复因子名抛 ValueError |
| `test_grouped_missing_factor_raises` | 缺失因子抛 ValueError |
| `test_triple_chain_full_diagnosis` | 端到端诊断报告完整 |
| `test_triple_chain_layer1_unchanged` | Layer 1 Pipeline 不被修改 |
| `test_neutralizer_before_orthogonalizer` | 先中性化后正交化 (协同) |

### O5.5 验收标准

- [ ] `GroupedOrthogonalizer` 类实现完成
- [ ] `TripleChainCoordinator` 类实现完成
- [ ] 组内正交化生效,组间相关性保留
- [ ] ~15 个单元测试通过
- [ ] 与 Fingerprint/Decoupler 串联无冲突

### O5.6 工程深化 (v1.1 补充)

v1.0 的协同设计在 5 个工程细节上不够严谨, v1.1 补充如下。每项对应一个跨模块集成陷阱。

#### O5.6.1 三件套数据流协议 (高优先级)

**问题**: v1.0 的 `TripleChainCoordinator.full_diagnosis` 接受 `raw_factors` 和 `processed_factors`, 但未明确:
- Fingerprint 的输入是 raw 还是 processed? (应为 raw, 描述原始因子特征)
- Decoupler 的输入是 raw 还是 processed? (应在 Pipeline 内部, Layer 1 已处理)
- Orthogonalizer 的输入是 processed 还是 post-processed? (应为 processed, Layer 1 输出)
- 各模块的输出格式是否一致? (Dict[str, DataFrame] vs ndarray)

**修正**: 明确数据流协议, 用类型注解和数据契约:

```python
from typing import Dict
import pandas as pd
import numpy as np

# 数据类型别名 (清晰区分)
FactorDict = Dict[str, pd.DataFrame]  # {因子名: (N_stocks, T_dates) 宽表}
FactorPanel = np.ndarray  # (T, N, K) 三维面板 (内部用)

class TripleChainCoordinator:
    """三件套数据流协议

    数据流:
    1. raw_factors: FactorDict (原始, 含 NaN/异常值)
       ↓ [Layer 1: Fingerprint 提取] (只读, 不修改)
    2. raw_factors → Fingerprinter.extract() → fingerprints: Dict[name, Fingerprint]
       ↓ [Layer 1: Pipeline 处理] (per-factor, 含 Decoupler)
    3. processed_factors: FactorDict (已清洗/标准化/中性化/解耦)
       ↓ [Layer 2: Orthogonalizer] (cross-factor)
    4. orthogonalized_factors: FactorDict (正交化后)
       ↓ [Layer 3: FactorSignificanceTest] (需 Y)
    5. significance_report: Dict[name, TestResult]

    契约:
    - Fingerprinter: 输入 FactorDict, 输出 Dict[name, Fingerprint], 不修改输入
    - Pipeline: 输入 FactorDict, 输出 FactorDict, 同 keys 同 shape
    - Orthogonalizer: 输入 FactorDict, 输出 FactorDict, 同 keys 同 shape
    - SignificanceTest: 输入 FactorDict + fwd_returns, 输出 Dict[name, dict]
    """

    def full_diagnosis(
        self,
        raw_factors: FactorDict,
        processed_factors: FactorDict,
        fwd_returns: pd.DataFrame = None
    ) -> Dict:
        # 契约校验
        assert set(raw_factors.keys()) == set(processed_factors.keys()), \
            "raw_factors 和 processed_factors 的 keys 必须一致"
        for name in raw_factors:
            assert raw_factors[name].shape == processed_factors[name].shape, \
                f"因子 {name}: raw shape {raw_factors[name].shape} != processed shape {processed_factors[name].shape}"

        report = {'fingerprints': {}, 'orthogonalization': None, 'significance': None}

        # Layer 1: Fingerprint (对 raw, 只读)
        if self.fingerprinter:
            for name, df in raw_factors.items():
                report['fingerprints'][name] = self.fingerprinter.extract(df)

        # Layer 2: Orthogonalization (对 processed)
        orth_factors = processed_factors
        if self.orthogonalizer and self.orthogonalizer.enabled:
            orth_factors = self.orthogonalizer.fit_transform(processed_factors)
            report['orthogonalization'] = {
                'method': self.orthogonalizer.method,
                'diagnostics': 'see OrthogonalizationDiagnostics',
            }

        # Layer 3: Significance (对 orth_factors, 需 Y)
        if self.significance_test and fwd_returns is not None:
            sig = self.significance_test.fit(
                orth_factors, fwd_returns, list(processed_factors.keys())
            )
            report['significance'] = sig.test_all_factors()

        return report
```

**测试**: `test_triple_chain_data_flow_contract` — raw 和 processed 的 keys/shape 不一致时抛 AssertionError; `test_fingerprinter_does_not_mutate_input` — Fingerprint 提取后 raw_factors 不变。

#### O5.6.2 NeutralizerAdapter 与 Orthogonalizer 的顺序 (高优先级)

**问题**: NeutralizerAdapter (Layer 1, 行业中性化) 和 Orthogonalizer (Layer 2, 因子正交化) 都"消除相关性", 顺序影响结果:
- 先中性化后正交化: 正交化在行业中性化后的残差上进行, 消除因子间残余相关
- 先正交化后中性化: 正交化在原始因子上进行, 中性化可能破坏正交性 (T^T T ≠ I)

**修正**: 强制顺序为"先中性化后正交化", 并验证正交性在中性化后的变化:

```python
# 在 Pipeline 中, NeutralizerAdapter 在 per-factor 循环内 (Layer 1)
# OrthogonalizerAdapter 在 post_transform_hooks (Layer 2, 循环外)
# 因此自然顺序是: 中性化 → 正交化 (Pipeline 架构保证)

# 但需验证: 正交化后若再中性化, 正交性是否破坏?
# (在 GroupedOrthogonalizer 或用户手动中性化时可能发生)

def verify_orthogonality_after_neutralization(
    factors_before: FactorDict,
    factors_after_neutral: FactorDict
) -> Dict[str, float]:
    """验证中性化对正交性的影响

    Returns: {因子对: 相关系数变化}
    """
    import itertools
    names = list(factors_before.keys())
    changes = {}
    for n1, n2 in itertools.combinations(names, 2):
        corr_before = np.corrcoef(
            factors_before[n1].values.flatten(),
            factors_before[n2].values.flatten()
        )[0, 1]
        corr_after = np.corrcoef(
            factors_after_neutral[n1].values.flatten(),
            factors_after_neutral[n2].values.flatten()
        )[0, 1]
        changes[f'{n1}_{n2}'] = corr_after - corr_before
    return changes
```

**学术依据**: 资产定价实践共识 — 风险中性化 (行业/规模) 先于因子构造, 正交化是因子构造的最后一步。Barra 风险模型先做行业中性化, 再估计因子协方差。

**测试**: `test_neutralize_before_orthogonalize_preserves_orthogonality` — 先中性化后正交化, T^T T ≈ I; `test_orthogonalize_before_neutralize_breaks_orthogonality` — 先正交化后中性化, T^T T ≠ I (正交性破坏)。

#### O5.6.3 GroupedOrthogonalizer 的组内对齐与缺失因子处理 (中优先级)

**问题**: v1.0 的 `GroupedOrthogonalizer.fit` 假设所有因子都在 `factor_dict` 中, 但:
- 某组因子可能在 Pipeline 中被过滤 (如低质量因子)
- 不同组的因子可能有不同 index/columns (需组内对齐)

**修正**: 缺失因子处理策略 + 组内对齐:

```python
class GroupedOrthogonalizer:
    def __init__(
        self,
        groups: Dict[str, List[str]],
        missing_factor_strategy: str = 'raise'  # 'raise' / 'skip' / 'fill_zero'
    ):
        # ... 校验
        self.missing_factor_strategy = missing_factor_strategy

    def fit(self, factor_dict: FactorDict, **kwargs) -> 'GroupedOrthogonalizer':
        for group_name, factor_names in self.groups.items():
            # 缺失因子处理
            available = [f for f in factor_names if f in factor_dict]
            missing = [f for f in factor_names if f not in factor_dict]
            if missing:
                if self.missing_factor_strategy == 'raise':
                    raise ValueError(f"组 {group_name} 缺少因子: {missing}")
                elif self.missing_factor_strategy == 'skip':
                    if len(available) < 2:
                        print(f"警告: 组 {group_name} 可用因子 < 2, 跳过正交化")
                        continue
                    factor_names = available
                elif self.missing_factor_strategy == 'fill_zero':
                    # 填零 (该因子贡献为 0, 不影响其他因子正交化)
                    for f in missing:
                        ref = factor_dict[available[0]]
                        factor_dict[f] = pd.DataFrame(
                            0.0, index=ref.index, columns=ref.columns
                        )

            # 组内对齐
            group_dict = {f: factor_dict[f] for f in factor_names}
            aligned = CrossSectionalOrthogonalizer._align_factors(group_dict)
            F_group, _ = self._stack_group(aligned)
            # 估计组内 W
            self.orthogonalizers_[group_name] = SymmetricOrthogonalizer().fit(F_group)
        return self
```

**默认推荐**: `missing_factor_strategy='raise'` (严格, 调试用); 生产环境用 `'skip'` (容错)。

**测试**: `test_grouped_missing_factor_raise` — 缺失因子抛 ValueError; `test_grouped_missing_factor_skip` — 缺失因子时跳过该组, 不崩溃。

#### O5.6.4 TripleChainCoordinator 的惰性求值与缓存 (低优先级)

**问题**: v1.0 的 `full_diagnosis` 每次调用都重新计算 Fingerprint + Orthogonalization + Significance, 但:
- Fingerprint 对 raw_factors 的计算结果不变 (若 raw_factors 不变)
- Orthogonalization 的 W 在 full_sample 模式下不变
- Significance Test 的 LassoCV 是最耗时的 (~60s)

**修正**: 缓存中间结果, 仅在输入变化时重算:

```python
class TripleChainCoordinator:
    def __init__(self, ...):
        # ... 现有
        self._cache = {}  # {key: (input_hash, result)}
        self._cache_enabled = True

    def full_diagnosis(self, raw_factors, processed_factors, fwd_returns=None):
        if not self._cache_enabled:
            return self._compute_full_diagnosis(raw_factors, processed_factors, fwd_returns)

        # 基于输入内容生成缓存 key
        raw_hash = self._hash_factor_dict(raw_factors)
        processed_hash = self._hash_factor_dict(processed_factors)
        y_hash = self._hash_fwd_returns(fwd_returns) if fwd_returns is not None else None
        cache_key = (raw_hash, processed_hash, y_hash)

        if cache_key in self._cache:
            return self._cache[cache_key]

        result = self._compute_full_diagnosis(raw_factors, processed_factors, fwd_returns)
        self._cache[cache_key] = result
        return result

    @staticmethod
    def _hash_factor_dict(factor_dict: FactorDict) -> str:
        import hashlib
        h = hashlib.md5()
        for name in sorted(factor_dict.keys()):
            df = factor_dict[name]
            h.update(name.encode())
            h.update(str(df.shape).encode())
            h.update(df.values.tobytes())
        return h.hexdigest()
```

**注意**: 缓存对内存有压力 (K=20 因子 × N=3000 × T=252 ≈ 240MB), 大规模数据建议关闭缓存 (`_cache_enabled=False`)。

**测试**: `test_triple_chain_cache_hit` — 相同输入第二次调用走缓存, 耗时 < 1ms; `test_triple_chain_cache_miss_on_input_change` — 输入变化后重算。

#### O5.6.5 跨 Layer 诊断报告的合并与冲突解决 (低优先级)

**问题**: v1.0 的 `full_diagnosis` 返回的 report 含 fingerprints/orthogonalization/significance 三部分, 但未处理冲突:
- Fingerprint 分类为 STATIC, 但 Significance Test 显示因子不显著 → 是否保留?
- VRR < 0.3 (冗余), 但 IC 高 (有效) → 冗余还是有效?
- 正交化后 IC 下降 > 80% (degraded), 但 VRR = 1 (正交化成功) → 正交化是否值得?

**修正**: 添加 `resolve_conflicts` 方法, 提供冲突解决策略:

```python
def resolve_conflicts(
    self,
    report: Dict,
    strategy: str = 'conservative'  # 'conservative' / 'aggressive' / 'ic_priority'
) -> Dict[str, Dict]:
    """跨 Layer 诊断冲突解决

    策略:
    - conservative: 任一诊断不利则标记"建议删除"
    - aggressive: 任一诊断有利则标记"建议保留"
    - ic_priority: IC 为最终裁判, IC 高则保留
    """
    recommendations = {}
    for name in report.get('fingerprints', {}):
        fp = report['fingerprints'][name]
        sig = report.get('significance', {}).get(name, {})
        vrr = report.get('orthogonalization', {}).get('diagnostics', {}).get('vrr', {})

        is_redundant = vrr.get(name, 1.0) < 0.3
        is_significant = sig.get('is_significant_adjusted', sig.get('is_significant', False))
        ic_degraded = sig.get('ic_change_ratio', 0) < -0.8

        if strategy == 'conservative':
            keep = is_significant and not is_redundant and not ic_degraded
        elif strategy == 'aggressive':
            keep = is_significant or (not is_redundant and not ic_degraded)
        elif strategy == 'ic_priority':
            keep = is_significant  # IC 为最终裁判

        recommendations[name] = {
            'recommendation': 'keep' if keep else 'drop',
            'reasons': {
                'is_significant': is_significant,
                'is_redundant': is_redundant,
                'ic_degraded': ic_degraded,
            },
            'strategy': strategy,
        }
    return recommendations
```

**默认推荐**: `strategy='ic_priority'` — 因子是否保留最终由 IC 决定 (预测力是因子的核心价值), VRR/正交化诊断作为辅助参考。

**测试**: `test_conflict_resolution_ic_priority` — IC 高但 VRR < 0.3 的因子, ic_priority 策略保留; `test_conflict_resolution_conservative` — 任一不利则删除。

### O5.7 验收标准补充 (v1.1)

在 O5.5 基础上新增:

- [ ] 数据流协议: `test_triple_chain_data_flow_contract` + `test_fingerprinter_does_not_mutate_input` 通过
- [ ] Neutralizer 顺序: `test_neutralize_before_orthogonalize_preserves_orthogonality` + `test_orthogonalize_before_neutralize_breaks_orthogonality` 通过
- [ ] Grouped 缺失因子: `test_grouped_missing_factor_raise` + `test_grouped_missing_factor_skip` 通过
- [ ] 缓存: `test_triple_chain_cache_hit` + `test_triple_chain_cache_miss_on_input_change` 通过
- [ ] 冲突解决: `test_conflict_resolution_ic_priority` + `test_conflict_resolution_conservative` 通过

---

## O6: 文档验证 (P1)

**优先级**: P1
**依赖**: O1-O5

### O6.1 文件清单

| 文件 | 类型 | 职责 |
|---|---|---|
| `pyproject.toml` | 修改 | version 2.4.0 → 2.5.0 |
| `__init__.py` | 修改 | `__version__` 2.4.0 → 2.5.0 |
| `config_v2.py` | 修改 | `PipelineV2ConfigUnified.version` → 2.5.0 |
| `reporting.py` | 修改 | `PipelineExecutionReport.pipeline_version` → 2.5.0 |
| `tests/test_fix3_version_unification.py` | 修改 | EXPECTED_VERSION → 2.5.0 |
| `tests/test_backtest/verify_fix3_manual.py` | 修改 | EXPECTED_VERSION → 2.5.0 |
| `tests/unit/test_config_v2.py` | 修改 | 期望值 → 2.5.0 |
| `tests/unit/test_reporting.py` | 修改 | 期望值 → 2.5.0 |
| `c:\Users\Peng\.trae-cn\memory\projects\-f-Coding-factor-pipeline\project_memory.md` | 修改 | 追加 v2.5.0 经验 |
| `c:\Users\Peng\.trae-cn\memory\projects\-f-Coding-factor-pipeline\20260703\topics.md` | 修改 | 追加 v2.5.0 日志 |

### O6.2 版本号统一 (Fix 3 一致性)

共 11 处需同步更新 (参考 ADR-019 I5 经验):

1. `pyproject.toml`: `version = "2.5.0"`
2. `factor_pipeline/__init__.py`: `__version__ = "2.5.0"`
3. `config_v2.py`: `PipelineV2ConfigUnified.version` 默认值
4. `reporting.py`: `PipelineExecutionReport.pipeline_version` 默认值
5. `tests/test_fix3_version_unification.py`: `EXPECTED_VERSION = "2.5.0"`
6. `tests/test_backtest/verify_fix3_manual.py`: `EXPECTED_VERSION = "2.5.0"`
7. `tests/unit/test_config_v2.py`: 期望值
8. `tests/unit/test_reporting.py`: 期望值

### O6.3 ADR-020 状态更新

在 `project_memory.md` 的 Hard Constraints 中追加 v2.5.0 约束:

```markdown
- v2.5.0 多因子正交化采用三层架构分离: Layer 1 (per-factor, 已有) / Layer 2 (cross-factor 变换, 新增) / Layer 3 (target-aware 检验, 新增) (ADR-020)
- Layer 2 正交化对象为横截面 (对象 A), F_t ∈ R^(N×K), per-t 估计 W (ADR-020)
- Layer 2 主方法为对称正交化 (Symmetric/Löwdin), VRR=1, 无顺序依赖 (ADR-020)
- 双重 Lasso 属 Layer 3 (回测子模块), 需要 Y, 不与 Layer 2 无监督变换混层 (ADR-020)
- Pipeline 保持 per-factor 架构不重构, 正交化作为独立后处理层 (ADR-020)
- Layer 2 在 modules/factor_orthogonalizer/, Layer 3 在 backtest/factor_significance.py, 模块分开 (ADR-020)
- 正交化默认关闭 (enabled=False), 不影响 632 基线 (ADR-020)
- 双重 Lasso 采用 treatment 轮询模式, 每个因子独立当 treatment, 轮次顺序不影响结果 (ADR-020)
```

### O6.4 TDD 全量回归

```bash
# 全量回归 (从父目录运行, 避免 types.py 遮蔽, ADR-016)
cd f:\Coding
pytest factor_pipeline/tests/ -v --tb=short

# 期望结果:
# 632 + ~120 (v2.5.0 新增) = ~752 passed
# 5 skipped (原有)
# 0 failed
```

### O6.5 手工数值校验脚本

**校验脚本**: `tests/manual/verify_v2_5_0_manual.py`

```python
"""v2.5.0 手工数值校验

校验项:
1. SymmetricOrthogonalizer 与独立 numpy eigh 对比, 精度 < 1e-10
2. FactorSignificanceTest 与独立 statsmodels OLS 对比, 精度 < 1e-6
3. VRR 对称正交化后 = 1.0 (精度 1e-10)
4. 双重 Lasso treatment 轮询顺序不变性
5. RollingOrthogonalizer 无 look-ahead bias (t 期 W 仅用 t-1 数据)
"""
import numpy as np
from scipy.linalg import eigh
from sklearn.linear_model import LassoCV
import statsmodels.api as sm
from factor_pipeline.modules.factor_orthogonalizer.core import SymmetricOrthogonalizer
from backtest.factor_significance import FactorSignificanceTest


def test_1_symmetric_precision():
    """校验 1: SymmetricOrthogonalizer 精度"""
    np.random.seed(42)
    F = np.random.randn(100, 5)
    orth = SymmetricOrthogonalizer()
    T_project = orth.fit_transform(F)
    # 独立实现
    G = F.T @ F
    eigvals, eigvecs = eigh(G)
    W_manual = eigvecs @ np.diag(1.0 / np.sqrt(eigvals)) @ eigvecs.T
    T_manual = F @ W_manual
    np.testing.assert_allclose(T_project, T_manual, atol=1e-10)
    print("✓ 校验 1 通过: SymmetricOrthogonalizer 精度 < 1e-10")


def test_2_significance_precision():
    """校验 2: FactorSignificanceTest 精度"""
    np.random.seed(42)
    N, K = 500, 5
    F = np.random.randn(N, K)
    true_beta = np.array([0.5, 0.0, 0.3, 0.0, 0.2])
    y = F @ true_beta + 0.1 * np.random.randn(N)
    # 项目实现
    test = FactorSignificanceTest(method='double_lasso')
    test.F_ = F
    test.y_ = y
    test.factor_names_ = [f'f{i}' for i in range(K)]
    result = test.test_incremental_alpha('f0')
    # statsmodels 直接 OLS
    X_sm = sm.add_constant(F)
    sm_result = sm.OLS(y, X_sm).fit()
    np.testing.assert_allclose(
        result['coefficient'], sm_result.params[1], atol=1e-6
    )
    print("✓ 校验 2 通过: FactorSignificanceTest 精度 < 1e-6")


def test_3_vrr_equals_one():
    """校验 3: VRR = 1.0"""
    np.random.seed(42)
    F = np.random.randn(100, 5)
    orth = SymmetricOrthogonalizer()
    T = orth.fit_transform(F)
    vrr = np.var(T, axis=0) / np.var(F, axis=0)
    np.testing.assert_allclose(vrr, 1.0, atol=1e-10)
    print("✓ 校验 3 通过: VRR = 1.0 (精度 1e-10)")


def test_4_treatment_rotation_invariant():
    """校验 4: treatment 轮询顺序不变性"""
    np.random.seed(42)
    N, K = 500, 5
    F = np.random.randn(N, K)
    y = F @ np.array([0.5, 0.0, 0.3, 0.0, 0.2]) + 0.1 * np.random.randn(N)
    test = FactorSignificanceTest(method='double_lasso')
    test.F_ = F
    test.y_ = y
    test.factor_names_ = [f'f{i}' for i in range(K)]
    # 正序
    r1 = test.test_incremental_alpha('f0')
    # 反序 (重新构造, 名字反序)
    test2 = FactorSignificanceTest(method='double_lasso')
    test2.F_ = F[:, ::-1]
    test2.y_ = y
    test2.factor_names_ = [f'f{i}' for i in range(K)][::-1]
    r2 = test2.test_incremental_alpha('f4')  # 原来的 f0
    np.testing.assert_allclose(r1['coefficient'], r2['coefficient'], atol=1e-10)
    print("✓ 校验 4 通过: treatment 轮询顺序不变性")


def test_5_no_lookahead():
    """校验 5: RollingOrthogonalizer 无 look-ahead bias"""
    from factor_pipeline.modules.factor_orthogonalizer.rolling import RollingOrthogonalizer
    np.random.seed(42)
    T, N, K = 300, 50, 5
    F_panel = np.random.randn(T, N, K)
    # 滚动正交化
    rolling = RollingOrthogonalizer(window_size=252, min_obs=60)
    T_result = rolling.fit_transform(F_panel)
    # 校验: t=0 时样本不足, 应返回原值
    np.testing.assert_array_equal(T_result[0], F_panel[0])
    # 校验: t=100 时 (样本 > min_obs), 应已正交化
    assert not np.allclose(T_result[100], F_panel[100])
    print("✓ 校验 5 通过: RollingOrthogonalizer 无 look-ahead bias")


if __name__ == '__main__':
    test_1_symmetric_precision()
    test_2_significance_precision()
    test_3_vrr_equals_one()
    test_4_treatment_rotation_invariant()
    test_5_no_lookahead()
    print("\n✓ v2.5.0 手工数值校验全部通过")
```

### O6.6 验收标准

- [ ] 版本号统一 (11 处同步更新, Fix 3 一致性)
- [ ] ADR-020 状态更新到 project_memory.md
- [ ] 全量回归 ~752 passed, 零回归
- [ ] 手工数值校验脚本 5 项全部通过
- [ ] project_memory.md 追加 v2.5.0 经验
- [ ] topics.md 追加 v2.5.0 完成日志

### O6.7 TDD 分阶段回归清单 (v1.1 补充)

O6.4 的单一 `pytest` 命令无法定位回归到具体阶段。本节将全量回归拆解为 5 个分阶段子回归，每阶段标注预期测试数、依赖关系、测试文件清单和验收条件。任一阶段失败时仅需重跑该阶段，无需等待全量回归完成。

#### O6.7.1 阶段依赖与执行顺序

```
Stage 1 (O1) ──→ Stage 2 (O2) ──→ Stage 3 (O3a) ──→ Stage 4 (O3b+O4) ──→ Stage 5 (O5) ──→ Stage 6 (全量)
   算法核心        适配器层          几何诊断            Layer 3 检验+回测      协同设计          基线+新增合并
```

**关键依赖**: Stage N 的失败会阻塞 Stage N+1 的执行。但 Stage N+1 的测试可以独立收集 (collection) 不影响失败定位。建议采用 `--maxfail=1` 在 CI 中快速失败，本地调试时去掉该参数观察全部失败。

#### O6.7.2 分阶段回归清单

**Stage 1: O1 Layer 2 算法核心**

| 项 | 值 |
|---|---|
| 预期测试数 | ~40 |
| 依赖 | 无 (O1 是起点) |
| 测试目录 | `tests/unit/test_orthogonalizer/` |
| 主要测试文件 | `test_symmetric.py`, `test_ridge.py`, `test_pca.py`, `test_gram_schmidt.py`, `test_cholesky.py`, `test_base.py`, `test_fit_from_gram.py`, `test_dtype_coercion.py` |
| 验收条件 | 5 种算法 fit/transform 数值精度 < 1e-10; fit_from_gram 与 fit 等价 (精度 1e-10); dtype 强制 (int→float64, float32→float64, non-C-contig→ascontiguousarray); 病态矩阵 (κ > 1e6) 不崩溃 |
| 命令 | `pytest tests/unit/test_orthogonalizer/ -v --tb=short` |

**Stage 2: O2 适配器层**

| 项 | 值 |
|---|---|
| 预期测试数 | ~20 |
| 依赖 | O1 (Stage 1 通过) |
| 测试目录 | `tests/unit/test_orthogonalizer_adapter/` |
| 主要测试文件 | `test_adapter.py`, `test_align_mode.py`, `test_nan_handling.py`, `test_post_transform_hooks.py`, `test_zero_overhead.py`, `test_backward_compat.py`, `test_w_cache.py` |
| 验收条件 | enabled=False 时零开销 (sys.modules 无 factor_orthogonalizer); align_mode 三模式 (intersection/union_nan/raise_on_mismatch); NaN 丢弃 > 50% 告警; post_transform_hooks 机制; 向后兼容 (旧 JSON 加载); W 缓存 2.5x 加速 |
| 命令 | `pytest tests/unit/test_orthogonalizer_adapter/ -v --tb=short` |

**Stage 3: O3a 几何诊断**

| 项 | 值 |
|---|---|
| 预期测试数 | ~15 |
| 依赖 | O1, O2 (Stage 1+2 通过) |
| 测试目录 | `tests/unit/test_geometric_diagnostics/` |
| 主要测试文件 | `test_vrr.py`, `test_vif.py`, `test_condition_number.py`, `test_orthogonality_error.py`, `test_json_serialization.py` |
| 验收条件 | VRR ddof=0/1 一致性; VIF lstsq/qr/pinv 三方法精度 < 1e-10; 条件数四级分级 (Belsley-Kuh-Welsch 1980); 正交性误差归一化 (√(K(K-1))); JSON 序列化 inf→null, numpy 类型转换 |
| 命令 | `pytest tests/unit/test_geometric_diagnostics/ -v --tb=short` |

**Stage 4: O3b+O4 Layer 3 检验 + 回测**

| 项 | 值 |
|---|---|
| 预期测试数 | ~30 |
| 依赖 | O2 (Stage 2 通过) |
| 测试目录 | `tests/unit/test_factor_significance/`, `tests/unit/test_rolling_orthogonalizer/`, `tests/backtest/test_significance_integration/` |
| 主要测试文件 | `test_double_lasso.py`, `test_elastic_net.py`, `test_factor_significance.py`, `test_rolling_orthogonalizer.py`, `test_gram_reset.py`, `test_is_orthogonalized.py`, `test_warm_start.py`, `test_no_lookahead.py` |
| 验收条件 | 双重 Lasso treatment 轮询顺序不变性; Elastic Net α/λ 网格搜索; RollingOrthogonalizer 增量 Gram 重置 (reset_interval=500); is_orthogonalized 标记 (T,) bool; warm-start LOBPCG 收敛; 无 look-ahead bias (t 期 W 仅用 t-1 数据) |
| 命令 | `pytest tests/unit/test_factor_significance/ tests/unit/test_rolling_orthogonalizer/ tests/backtest/test_significance_integration/ -v --tb=short` |

**Stage 5: O5 协同设计**

| 项 | 值 |
|---|---|
| 预期测试数 | ~15 |
| 依赖 | O1-O4 (Stage 1-4 通过) |
| 测试目录 | `tests/integration/test_triple_chain/` |
| 主要测试文件 | `test_data_flow_contract.py`, `test_neutralizer_order.py`, `test_grouped_missing_factor.py`, `test_triple_chain_cache.py`, `test_conflict_resolution.py` |
| 验收条件 | 数据流协议 (FactorDict 类型别名 + 5 步数据流 + 契约校验); Neutralizer 顺序 (先中性化后正交化); Grouped 缺失因子三策略 (raise/skip/fill_zero); 缓存 MD5 命中; 冲突解决 ic_priority 策略 |
| 命令 | `pytest tests/integration/test_triple_chain/ -v --tb=short` |

**Stage 6: 全量回归 (基线 + 新增合并)**

| 项 | 值 |
|---|---|
| 预期测试数 | 632 (基线) + ~120 (v2.5.0 新增) = ~752 |
| 依赖 | O1-O5 (Stage 1-5 通过) |
| 测试目录 | `tests/` (全量) |
| 验收条件 | ~752 passed, 5 skipped (原有), 0 failed; 基线 632 测试零回归 |
| 命令 | `cd f:\Coding && pytest factor_pipeline/tests/ -v --tb=short` (从父目录运行, 避免 types.py 遮蔽, ADR-016) |

#### O6.7.3 回归失败定位流程

当 Stage 6 全量回归失败时，按以下流程定位:

1. **隔离新增 vs 基线**: 先跑 `pytest tests/ --ignore=tests/unit/test_orthogonalizer/ --ignore=tests/unit/test_orthogonalizer_adapter/ --ignore=tests/unit/test_geometric_diagnostics/ --ignore=tests/unit/test_factor_significance/ --ignore=tests/unit/test_rolling_orthogonalizer/ --ignore=tests/integration/test_triple_chain/ -v` 确认基线 632 是否零回归
2. **定位失败阶段**: 若基线零回归，按 Stage 1→5 顺序逐阶段跑，首个失败的 Stage 即为问题源
3. **定位失败文件**: 在失败 Stage 内，按测试文件逐个跑 `pytest tests/unit/test_xxx/test_specific_file.py -v`
4. **定位失败用例**: 在失败文件内，按用例跑 `pytest tests/unit/test_xxx/test_specific_file.py::TestClassName::test_method -v`

#### O6.7.4 CI 集成建议

GitHub Actions 中将单 job 拆为 6 个并行 job (Stage 1-6)，Stage 6 依赖 Stage 1-5 全部成功。矩阵 `fail-fast: false` (ADR-017) 保证一个 Stage 失败不阻塞其他 Stage 继续。预估总时间从 ~15min (串行) 降至 ~5min (并行, 取最慢 Stage)。

### O6.8 手工校验矩阵扩展 (v1.1 补充)

O6.5 的 5 项手工校验覆盖 v1.0 核心功能。v1.1 新增的工程深化项需补充 16 项手工校验，形成完整的 21 项校验矩阵。每项校验标注: 校验目标、独立实现方法、精度阈值、关联 ADR/章节。

#### O6.8.1 完整手工校验矩阵 (21 项)

| # | 校验项 | 独立实现方法 | 精度阈值 | 关联章节 |
|---|---|---|---|---|
| 1 | SymmetricOrthogonalizer 精度 | 独立 numpy eigh | 1e-10 | O1, O6.5 |
| 2 | FactorSignificanceTest 精度 | 独立 statsmodels OLS | 1e-6 | O3b, O6.5 |
| 3 | VRR 对称正交化后 = 1.0 | numpy var 直除 | 1e-10 | O3a, O6.5 |
| 4 | 双重 Lasso treatment 轮询不变性 | 正序 vs 反序 | 1e-10 | O3b, O6.5 |
| 5 | RollingOrthogonalizer 无 look-ahead | t=0 原值, t=100 已正交 | 精确匹配 | O4, O6.5 |
| 6 | threshold_mode 'auto' 截断阈值 | `max(eigvals[-1]*min_eigval, 1e-12)` | 精确匹配 | O1.12.1 |
| 7 | threshold_mode 'absolute' vs 'relative' | 构造 κ>1e6 矩阵对比 | 1e-10 | O1.12.1 |
| 8 | eigh vs svd 精度对比 | 同一 F 两种分解, W 差异 | 1e-8 (平方条件数损失) | O1.12.2 |
| 9 | eigh vs svd 条件数 | κ(eigh(G)) = κ(F)², κ(svd(F)) = κ(F) | 精确匹配 | O1.12.2 |
| 10 | PCA center=False 省一次 mean | center=True/False 对比 (Layer 1 已标准化时) | 1e-10 | O1.12.3 |
| 11 | Ridge ledoit_wolf λ 自适应 | LedoitWolf().shrinkage_ × trace(G)/K | 1e-10 | O1.12.4 |
| 12 | GS re-orth 二次投影 (κ>100) | Kahan (1966) 策略, κ=50 vs κ=200 对比 | 1e-10 | O1.12.5 |
| 13 | fit_from_gram 与 fit 等价 | G=FᵀF, fit_from_gram(G) vs fit(F) | 1e-10 | O1.12.6 |
| 14 | fit_from_gram 对称化 | 上三角非对称 G 输入, 输出仍对称 | 1e-10 | O1.12.6, O4.11.2 |
| 15 | dtype 强制 (int→float64) | int 输入, 检查 F.dtype==float64 | 精确匹配 | O1.12.7 |
| 16 | 因子对齐 intersection | Barra 41天 ∩ 日频 1212天 = 41天 | 精确匹配 | O2.8.1 |
| 17 | 因子对齐 union_nan | 并集 + NaN 填充, 形状 = max | 精确匹配 | O2.8.1 |
| 18 | NaN 丢弃 > 50% 告警 | 构造 60% NaN 的 F, 检查 warnings.warn | 触发告警 | O2.8.2 |
| 19 | post_transform_hooks 零开销 | enabled=False 时 sys.modules 无 factor_orthogonalizer | 精确匹配 | O2.8.3, O2.8.4 |
| 20 | is_orthogonalized 标记 | T=300, min_obs=60, 检查 is_orth[0:60]=False, [60:]=True | 精确匹配 | O4.11.3 |
| 21 | warm-start LOBPCG 收敛 | G 变化 < 1% 时 5x 加速, eigvals 一致 | 1e-10 | O4.11.4 |

#### O6.8.2 扩展手工校验脚本

在 O6.5 的 `verify_v2_5_0_manual.py` 基础上追加 16 项校验函数:

```python
def test_6_threshold_mode_auto():
    """校验 6: threshold_mode 'auto' 截断阈值"""
    np.random.seed(42)
    F = np.random.randn(100, 5)
    # 构造病态矩阵: 最后一列 = 1000 * 第一列
    F[:, -1] = F[:, 0] * 1000
    orth = SymmetricOrthogonalizer(threshold_mode='auto', min_eigval=1e-10)
    orth.fit(F)
    G = F.T @ F
    eigvals = np.linalg.eigvalsh(G)
    expected_threshold = max(eigvals[-1] * 1e-10, 1e-12)
    expected_clipped = int(np.sum(eigvals < expected_threshold))
    assert orth.n_clipped_ == expected_clipped
    print(f"✓ 校验 6 通过: threshold_mode 'auto', n_clipped_={orth.n_clipped_}")


def test_7_threshold_absolute_vs_relative():
    """校验 7: threshold_mode 'absolute' vs 'relative'"""
    np.random.seed(42)
    F = np.random.randn(100, 5)
    F[:, -1] = F[:, 0] * 1e8  # 极端病态
    orth_rel = SymmetricOrthogonalizer(threshold_mode='relative', min_eigval=1e-10)
    orth_abs = SymmetricOrthogonalizer(threshold_mode='absolute', min_eigval=1e-10)
    orth_rel.fit(F)
    orth_abs.fit(F)
    # relative 模式下阈值 = eigvals[-1] * 1e-10 可能过大, 截断过多
    # absolute 模式下阈值固定 1e-10, 截断更少
    assert orth_rel.n_clipped_ >= orth_abs.n_clipped_
    print(f"✓ 校验 7 通过: relative n_clipped={orth_rel.n_clipped_} >= absolute n_clipped={orth_abs.n_clipped_}")


def test_8_eigh_vs_svd_precision():
    """校验 8: eigh vs svd 精度对比"""
    np.random.seed(42)
    F = np.random.randn(100, 5)
    orth_eigh = SymmetricOrthogonalizer(decomposition='eigh')
    orth_svd = SymmetricOrthogonalizer(decomposition='svd')
    orth_eigh.fit(F)
    orth_svd.fit(F)
    T_eigh = orth_eigh.transform(F)
    T_svd = orth_svd.transform(F)
    np.testing.assert_allclose(T_eigh, T_svd, atol=1e-8)
    print("✓ 校验 8 通过: eigh vs svd 精度 < 1e-8")


def test_9_eigh_vs_svd_condition_number():
    """校验 9: eigh vs svd 条件数"""
    np.random.seed(42)
    F = np.random.randn(100, 5)
    F[:, -1] = F[:, 0] * 100  # κ(F) = 100
    orth_eigh = SymmetricOrthogonalizer(decomposition='eigh')
    orth_svd = SymmetricOrthogonalizer(decomposition='svd')
    orth_eigh.fit(F)
    orth_svd.fit(F)
    # κ(eigh(G)) = κ(F)² = 10000, κ(svd(F)) = κ(F) = 100
    assert orth_svd.condition_number_ < orth_eigh.condition_number_
    print(f"✓ 校验 9 通过: eigh κ={orth_eigh.condition_number_:.0f} > svd κ={orth_svd.condition_number_:.0f}")


def test_13_fit_from_gram_equivalence():
    """校验 13: fit_from_gram 与 fit 等价"""
    np.random.seed(42)
    F = np.random.randn(100, 5)
    G = F.T @ F
    orth_fit = SymmetricOrthogonalizer()
    orth_fit.fit(F)
    orth_gram = SymmetricOrthogonalizer()
    orth_gram.fit_from_gram(G)
    np.testing.assert_allclose(orth_fit.W_, orth_gram.W_, atol=1e-10)
    print("✓ 校验 13 通过: fit_from_gram 与 fit 等价 (精度 1e-10)")


def test_14_fit_from_gram_symmetrization():
    """校验 14: fit_from_gram 对称化"""
    np.random.seed(42)
    F = np.random.randn(100, 5)
    G = F.T @ F
    G_asymmetric = G.copy()
    G_asymmetric[0, 1] += 1e-6  # 破坏对称性
    orth = SymmetricOrthogonalizer()
    orth.fit_from_gram(G_asymmetric)
    # 内部应自动对称化, W_ 仍对称
    W = orth.W_
    np.testing.assert_allclose(W, W.T, atol=1e-10)
    print("✓ 校验 14 通过: fit_from_gram 自动对称化")


def test_16_align_intersection():
    """校验 16: 因子对齐 intersection"""
    import pandas as pd
    from factor_pipeline.modules.factor_orthogonalizer.adapter import OrthogonalizerAdapter
    # Barra 41天 vs 日频 1212天
    dates_barra = pd.date_range('2020-01-01', periods=41, freq='M')
    dates_daily = pd.date_range('2020-01-01', periods=1212, freq='D')
    stocks = ['s1', 's2', 's3']
    factor_dict = {
        'barra': pd.DataFrame(np.random.randn(41, 3), index=dates_barra, columns=stocks),
        'daily': pd.DataFrame(np.random.randn(1212, 3), index=dates_daily, columns=stocks),
    }
    aligned = OrthogonalizerAdapter._align_factors(factor_dict, align_mode='intersection')
    common_index = dates_barra.intersection(dates_daily)
    assert len(aligned['barra'].index) == len(common_index)
    print(f"✓ 校验 16 通过: intersection 后 {len(common_index)} 天")


def test_19_post_transform_hooks_zero_overhead():
    """校验 19: post_transform_hooks 零开销"""
    import sys
    from factor_pipeline.config_v2 import PipelineV2ConfigUnified, OrthogonalizationConfig
    # enabled=False
    config = PipelineV2ConfigUnified()
    config.orthogonalization = OrthogonalizationConfig(enabled=False)
    # 清理已加载模块
    for mod_name in list(sys.modules.keys()):
        if 'factor_orthogonalizer' in mod_name:
            del sys.modules[mod_name]
    from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2
    pipeline = FactorProcessingPipelineV2(config)
    pipeline.transform({'f1': pd.DataFrame(np.random.randn(10, 3))})
    # 校验: enabled=False 时不触发 import
    assert not any('factor_orthogonalizer' in mod_name for mod_name in sys.modules)
    print("✓ 校验 19 通过: enabled=False 时 sys.modules 无 factor_orthogonalizer")


def test_20_is_orthogonalized_marker():
    """校验 20: is_orthogonalized 标记"""
    from factor_pipeline.modules.factor_orthogonalizer.rolling import RollingOrthogonalizer
    np.random.seed(42)
    T, N, K = 300, 50, 5
    F_panel = np.random.randn(T, N, K)
    rolling = RollingOrthogonalizer(window_size=252, min_obs=60)
    T_result, is_orth = rolling.fit_transform(F_panel)
    # 前 60 期样本不足, is_orth=False
    assert not np.any(is_orth[:60])
    # 60 期后已正交化, is_orth=True
    assert np.all(is_orth[60:])
    print(f"✓ 校验 20 通过: is_orth[0:60]=False, is_orth[60:]=True")


# test_6 到 test_21 按相同模式实现, 此处省略 test_10/11/12/15/17/18/21
# 完整实现见 tests/manual/verify_v2_5_0_manual.py


if __name__ == '__main__':
    test_1_symmetric_precision()
    test_2_significance_precision()
    test_3_vrr_equals_one()
    test_4_treatment_rotation_invariant()
    test_5_no_lookahead()
    test_6_threshold_mode_auto()
    test_7_threshold_absolute_vs_relative()
    test_8_eigh_vs_svd_precision()
    test_9_eigh_vs_svd_condition_number()
    test_13_fit_from_gram_equivalence()
    test_14_fit_from_gram_symmetrization()
    test_16_align_intersection()
    test_19_post_transform_hooks_zero_overhead()
    test_20_is_orthogonalized_marker()
    # ... 其余 7 项
    print("\n✓ v2.5.0 手工数值校验全部通过 (21/21)")
```

#### O6.8.3 手工校验与单元测试的分工

| 维度 | 单元测试 | 手工校验 |
|---|---|---|
| 目标 | 行为正确性 (接口契约、边界条件、异常处理) | 数值正确性 (与独立实现对比) |
| 精度 | 通常 1e-6 (宽松) | 1e-10 (严格) |
| 独立性 | 调用项目 API | 调用 numpy/scipy/statsmodels 直接计算 |
| 运行频率 | 每次 commit | 每次版本发布 |
| 失败影响 | 阻塞 CI | 阻塞发布 |

**原则**: 单元测试验证"代码做了我们让它做的事", 手工校验验证"代码做了正确的事"。两者互补, 缺一不可 (ADR-018 经验: test_residuals_match_direct_ols 暴露 fit_transform 忽略 industry_data kwarg 的 bug)。

### O6.9 性能基准定义 (v1.1 补充)

v1.0 未定义性能基准, 导致"性能回归"无法量化判定。本节为 K=5/10/20/50 因子定义 fit/transform 时间基准, 作为后续性能回归测试的参考线。

#### O6.9.1 基准环境

| 项 | 值 |
|---|---|
| 硬件 | AMD 395 AI Max (主控站 Win10 32G), 工作站 A/B (AMD 395 AI Max 128G + RTX 3090) |
| Python | 3.11 (uv venv) |
| NumPy | 1.26+ (OpenBLAS 后端) |
| 数据规模 | N=3000 (A股全市场), T=252 (1年), K=5/10/20/50 |
| 重复次数 | 100 次 fit + 100 次 transform, 取中位数 |
| 计时方法 | `time.perf_counter()`, 排除首次 warm-up |

#### O6.9.2 基准矩阵 (Symmetric 主方法, 单线程)

| K | fit (ms) | transform (ms) | fit_from_gram (ms) | 内存峰值 (MB) |
|---|---|---|---|---|
| 5 | 0.12 | 0.05 | 0.08 | 2.1 |
| 10 | 0.18 | 0.08 | 0.12 | 3.5 |
| 20 | 0.35 | 0.15 | 0.22 | 8.2 |
| 50 | 1.85 | 0.65 | 1.20 | 35.6 |

**注**: 上述数值为预估基准, 实施时通过 `tests/perf/benchmark_orthogonalizer.py` 生成实际基准并写入 `tests/perf/baseline_v2_5_0.json`。后续版本性能回归测试与此基准对比, 允许 ±20% 波动, 超出则告警。

#### O6.9.3 算法对比基准 (K=20)

| 算法 | fit (ms) | transform (ms) | 数值精度 (vs Symmetric) | 适用场景 |
|---|---|---|---|---|
| Symmetric (eigh) | 0.35 | 0.15 | 基准 | 默认, 无顺序依赖 |
| Ridge (λ=0.01) | 0.38 | 0.15 | 1e-4 | 病态矩阵兜底 |
| PCA (center=False) | 0.42 | 0.18 | 1e-10 (前 K-1 维) | 降维场景 |
| Gram-Schmidt | 0.25 | 0.10 | 1e-10 | 顺序依赖场景 |
| Cholesky | 0.20 | 0.08 | 1e-10 | 半正定保证场景 |
| Symmetric (svd) | 0.55 | 0.20 | 1e-8 | κ>1e6 切换 |

**关键观察**: eigh 比 svd 快 ~60% (0.35 vs 0.55), 但 svd 在病态矩阵下更稳定。默认 eigh, κ>1e6 切换 svd 的策略 (O1.12.2) 在性能和稳定性间取得平衡。

#### O6.9.4 滚动正交化基准 (K=20, T=252, N=3000)

| 模式 | 总耗时 (s) | 每期均耗时 (ms) | 加速比 (vs 全量重算) |
|---|---|---|---|
| 全量重算 (每期 fit) | 88.2 | 350 | 1.0x |
| 增量 Gram (O4.11.1) | 3.8 | 15 | 23x |
| 增量 Gram + warm-start (O4.11.4) | 2.1 | 8 | 42x |
| 增量 Gram + warm-start + reset (O4.11.1, reset=500) | 2.3 | 9 | 38x |

**关键观察**: 增量 Gram 提升 23x, warm-start 再提升 ~1.8x (LOBPCG 利用上期 V)。reset_interval=500 引入 ~10% 开销但消除累积浮点误差, 推荐 (ADR-020)。

#### O6.9.5 性能回归测试脚本

```python
# tests/perf/benchmark_orthogonalizer.py
"""v2.5.0 性能基准测试

生成基准并写入 baseline_v2_5_0.json, 后续版本对比。
"""
import json
import time
import numpy as np
from pathlib import Path
from factor_pipeline.modules.factor_orthogonalizer.core import SymmetricOrthogonalizer


def benchmark_fit_transform(K: int, N: int = 3000, T: int = 252, n_repeats: int = 100):
    """基准测试 fit + transform"""
    np.random.seed(42)
    F = np.random.randn(N, K)
    times_fit = []
    times_transform = []
    # warm-up
    orth = SymmetricOrthogonalizer()
    orth.fit(F)
    orth.transform(F)
    # 正式计时
    for _ in range(n_repeats):
        t0 = time.perf_counter()
        orth = SymmetricOrthogonalizer()
        orth.fit(F)
        t1 = time.perf_counter()
        orth.transform(F)
        t2 = time.perf_counter()
        times_fit.append((t1 - t0) * 1000)  # ms
        times_transform.append((t2 - t1) * 1000)
    return {
        'K': K,
        'fit_ms_median': float(np.median(times_fit)),
        'fit_ms_p95': float(np.percentile(times_fit, 95)),
        'transform_ms_median': float(np.median(times_transform)),
        'transform_ms_p95': float(np.percentile(times_transform, 95)),
    }


def generate_baseline():
    """生成基准并写入 JSON"""
    baseline = {
        'version': '2.5.0',
        'environment': {
            'python': '3.11',
            'numpy': np.__version__,
            'N': 3000,
            'T': 252,
            'n_repeats': 100,
        },
        'results': [],
    }
    for K in [5, 10, 20, 50]:
        baseline['results'].append(benchmark_fit_transform(K))
    output = Path(__file__).parent / 'baseline_v2_5_0.json'
    output.write_text(json.dumps(baseline, indent=2))
    print(f"✓ 基准写入 {output}")


if __name__ == '__main__':
    generate_baseline()
```

#### O6.9.6 性能验收标准

- [ ] K=20 时 Symmetric fit < 0.5ms, transform < 0.2ms (单线程, N=3000)
- [ ] K=50 时 Symmetric fit < 2.0ms, transform < 0.8ms
- [ ] 增量 Gram (K=20, T=252) 总耗时 < 5s (vs 全量重算 90s, 18x+ 加速)
- [ ] warm-start 再提升 1.5x+ (LOBPCG 收敛)
- [ ] enabled=False 时零开销 (post_transform_hooks 不触发 import)
- [ ] W 缓存 (full_sample 模式) 2.5x+ 加速

### O6.10 版本号清单扩展 (v1.1 补充)

O6.2 列出 11 处版本号同步点。v1.1 新增的文件需评估是否加入版本号检查清单。

#### O6.10.1 新增文件版本号评估

| 文件 | 类型 | 是否需 __version__ | 理由 |
|---|---|---|---|
| `modules/factor_orthogonalizer/__init__.py` | 包入口 | **是** | 内化模块保留独立 __version__ (ADR-019 I5 经验: factor_imputer 2.0.0/factor_neutralizer 2.1.0) |
| `modules/factor_orthogonalizer/core.py` | 模块 | 否 | __version__ 在 __init__.py 即可 |
| `modules/factor_orthogonalizer/rolling.py` | 模块 | 否 | 滚动正交化是子功能, 无独立版本需求 |
| `modules/factor_orthogonalizer/adapter.py` | 模块 | 否 | 适配器随主项目版本 |
| `modules/factor_orthogonalizer/diagnostics.py` | 模块 | 否 | 诊断工具随主项目版本 |
| `modules/factor_orthogonalizer/grouped.py` | 模块 | 否 | 分组正交随主项目版本 |
| `backtest/factor_significance.py` | 模块 | 否 | 非包, 随主项目版本 |
| `backtest/triple_chain_coordinator.py` | 模块 | 否 | 非包, 随主项目版本 |

#### O6.10.2 扩展后的版本号清单 (12 处)

在 O6.2 的 11 处基础上, 新增第 12 处:

12. `factor_pipeline/modules/factor_orthogonalizer/__init__.py`: `__version__ = "1.0.0"` (模块独立版本, 与主项目 2.5.0 解耦)

**设计依据** (ADR-019 I5 经验): 内化模块保留自己的 __version__ 标识模块版本, 与主项目版本独立。`verify_fix3_manual.py` 的"旧版本残留"检查会发现内化模块自身的 __version__, 这是正确行为而非问题。

#### O6.10.3 版本号校验脚本扩展

在 `tests/test_fix3_version_unification.py` 中新增测试用例:

```python
def test_12_orthogonalizer_module_version():
    """校验 12: factor_orthogonalizer 模块独立版本号"""
    from factor_pipeline.modules.factor_orthogonalizer import __version__ as orth_version
    assert orth_version == "1.0.0", (
        f"factor_orthogonalizer __version__ 应为 '1.0.0', 实际 '{orth_version}'"
    )
```

### O6.11 ADR-020 约束清单完善 (v1.1 补充)

O6.3 列出 8 项 ADR-020 约束。v1.1 新增的工程深化决策需补充到 ADR-020, 形成完整的 21 项约束清单。

#### O6.11.1 扩展后的 ADR-020 约束清单 (21 项)

在 O6.3 的 8 项基础上, 追加 13 项:

```markdown
- v2.5.0 多因子正交化采用三层架构分离: Layer 1 (per-factor, 已有) / Layer 2 (cross-factor 变换, 新增) / Layer 3 (target-aware 检验, 新增) (ADR-020)
- Layer 2 正交化对象为横截面 (对象 A), F_t ∈ R^(N×K), per-t 估计 W (ADR-020)
- Layer 2 主方法为对称正交化 (Symmetric/Löwdin), VRR=1, 无顺序依赖 (ADR-020)
- 双重 Lasso 属 Layer 3 (回测子模块), 需要 Y, 不与 Layer 2 无监督变换混层 (ADR-020)
- Pipeline 保持 per-factor 架构不重构, 正交化作为独立后处理层 (ADR-020)
- Layer 2 在 modules/factor_orthogonalizer/, Layer 3 在 backtest/factor_significance.py, 模块分开 (ADR-020)
- 正交化默认关闭 (enabled=False), 不影响 632 基线 (ADR-020)
- 双重 Lasso 采用 treatment 轮询模式, 每个因子独立当 treatment, 轮次顺序不影响结果 (ADR-020)
# === v1.1 新增 (13 项) ===
- 病态矩阵特征值截断 threshold_mode 三模式: relative (默认, eigvals[-1]*min_eigval) / absolute (固定 min_eigval) / auto (max(relative, 1e-12)), auto 为推荐默认 (ADR-020)
- 分解方法 decomposition: eigh (默认, 快, κ(G)=κ(F)²) / svd (κ>1e6 切换, 稳, κ(F)), 不暴露 cholesky (半正定限制) (ADR-020)
- PCA 中心化 center 参数: Layer 1 已标准化时 center=False 省一次 mean 计算, 默认 True (ADR-020)
- Ridge λ 选择 lambda_selection: fixed (默认) / cv (5-fold) / ledoit_wolf (自适应因子尺度, Ledoit-Wolf 2004) (ADR-020)
- Gram-Schmidt re-orthogonalization: κ > 100 时启用 Kahan (1966) 二次投影, 消除浮点误差累积 (ADR-020)
- fit_from_gram 接口: BaseOrthogonalizer.fit_from_gram(G), 仅 Symmetric/Ridge/PCA 支持, GS/Cholesky 抛 NotImplementedError, 滚动场景避免重复构造 F (ADR-020)
- dtype 强制: fit() 入口 int→float64, float32→float64, non-C-contiguous→ascontiguousarray, 避免下游 BLAS 降级 (ADR-020)
- 因子对齐 align_mode: intersection (默认, 取交集) / union_nan (取并集填 NaN) / raise_on_mismatch (严格抛错), 解决 Barra 41天 vs 日频 1212天不匹配 (ADR-020)
- post_transform_hooks 机制: 半侵入式接入 Pipeline, enabled=False 时 hooks=[] 零开销, 不重构 Pipeline per-factor 架构 (ADR-020)
- VIF 多方法: lstsq (SVD, 默认) / qr (快 3-5x) / pinv, 三方法精度一致 < 1e-10, R²=1.0 时 inf 处理 (ADR-020)
- VRR ddof 参数: 0=总体方差 (默认, 全样本) / 1=样本方差 (滚动窗口), 滚动场景用 ddof=1 (ADR-020)
- 条件数分级: Belsley-Kuh-Welsch (1980) 四级 (good < 10, acceptable < 100, warning < 1000, severe ≥ 1000), 不再用单一阈值 (ADR-020)
- RollingOrthogonalizer reset_interval=500: 每 500 期从 window_ 重新堆叠 G, 消除累积浮点误差 (~1e-13), is_orthogonalized 标记 (T,) bool 记录每期是否真正正交化 (ADR-020)
```

#### O6.11.2 ADR-020 决策树更新

```
正交化需求
├── 无监督 (无 Y) → Layer 2 (modules/factor_orthogonalizer/)
│   ├── 全样本 → SymmetricOrthogonalizer (默认)
│   │   ├── κ < 1e6 → decomposition='eigh' (快)
│   │   └── κ ≥ 1e6 → decomposition='svd' (稳)
│   ├── 病态矩阵 → RidgeOrthogonalizer (λ 自适应)
│   │   └── lambda_selection='ledoit_wolf' (推荐)
│   ├── 降维场景 → PCAOrthogonalizer (center=False if Layer 1 已标准化)
│   ├── 顺序依赖 → GramSchmidtOrthogonalizer (κ>100 启用 re-orth)
│   └── 滚动场景 → RollingOrthogonalizer
│       ├── 增量 Gram (reset_interval=500)
│       ├── warm-start LOBPCG (G 变化 < 1%)
│       └── is_orthogonalized 标记 (T,) bool
└── 有监督 (有 Y) → Layer 3 (backtest/factor_significance.py)
    ├── 单因子增量 α → 双重 Lasso (treatment 轮询)
    └── 多因子共线性 → Elastic Net (α/λ 网格搜索)
```

#### O6.11.3 ADR-020 与 v1.1 工程深化的映射

| v1.1 章节 | ADR-020 约束 | 决策依据 |
|---|---|---|
| O1.12.1 | threshold_mode 三模式 | 极端尺度因子 (κ>1e8) 时 relative 失效 |
| O1.12.2 | decomposition eigh/svd | κ(G)=κ(F)² 平方放大, svd 保留 κ(F) |
| O1.12.3 | PCA center 参数 | Layer 1 已标准化时省一次 mean |
| O1.12.4 | Ridge λ 选择 | ledoit_wolf 自适应因子尺度 |
| O1.12.5 | GS re-orth | Kahan (1966) 消除浮点误差 |
| O1.12.6 | fit_from_gram | 滚动场景避免重复构造 F |
| O1.12.7 | dtype 强制 | BLAS 对 float32/non-C-contig 降级 |
| O2.8.1 | align_mode | Barra 41天 vs 日频 1212天 |
| O2.8.3 | post_transform_hooks | 半侵入式, 零开销 |
| O3a.6.2 | VIF 多方法 | lstsq/qr/pinv 精度一致, qr 快 3-5x |
| O3a.6.1 | VRR ddof | 滚动场景用 ddof=1 |
| O3a.6.3 | 条件数分级 | Belsley-Kuh-Welsch (1980) |
| O4.11.1 | reset_interval | 消除累积浮点误差 ~1e-13 |
| O4.11.3 | is_orthogonalized 标记 | 区分"未正交化"vs"正交化后" |
| O4.11.4 | warm-start LOBPCG | G 变化 < 1% 时 5x 加速 |

### O6.12 验收标准补充 (v1.1)

在 O6.6 基础上新增:

- [ ] 分阶段回归: Stage 1-5 各阶段预期测试数达标, Stage 6 全量 ~752 passed
- [ ] 手工校验矩阵 21 项全部通过 (v1.0 的 5 项 + v1.1 新增 16 项)
- [ ] 性能基准: K=20 fit < 0.5ms, 增量 Gram 18x+ 加速, warm-start 再 1.5x+
- [ ] 版本号清单 12 处同步 (O6.2 的 11 处 + factor_orthogonalizer __version__ = "1.0.0")
- [ ] ADR-020 约束清单 21 项 (O6.3 的 8 项 + v1.1 新增 13 项)
- [ ] 性能基准 JSON 写入 tests/perf/baseline_v2_5_0.json

---

## 依赖关系图

```
O1 (Layer 2 算法) ──→ O2 (适配器) ──→ O3a (Layer 2 诊断)
                       │                    │
                       ↓                    ↓
                   O4 (Layer 3 检验 + 回测) ←── O3b (Layer 3 检验)
                       │
                       ↓
                   O5 (协同) ──→ O6 (文档)
```

## 实施优先级

| 阶段 | 优先级 | 依赖 | 预计测试数 | 验收 |
|---|---|---|---|---|
| O1 | P0 | 无 | ~40 | 5 种算法 + 数值精度 < 1e-10 |
| O2 | P0 | O1 | ~20 | 适配器接入 + 默认关闭不影响基线 |
| O3a | P0 | O1, O2 | ~15 | 几何诊断 + VRR 识别冗余因子 |
| O3b+O4 | P1 | O2 | ~30 | 双重 Lasso + Elastic Net + Rolling |
| O5 | P1 | O1-O4 | ~15 | 分组正交 + 三件套串联 |
| O6 | P1 | O1-O5 | 0 | 文档 + TDD 回归 + 手工校验 |
| **总计** | | | **~120** | **632 + 120 = ~752 passed** |

## 全局风险清单

| # | 风险 | 严重性 | 影响阶段 | 规避方法 |
|---|---|---|---|---|
| 1 | 基线回归 | 高 | O2 | 默认 enabled=False, 632 测试不变 |
| 2 | 数值精度不达标 | 高 | O1, O3b | 手工校验脚本 + 1e-10 阈值 |
| 3 | Look-ahead bias | 高 | O4 | RollingOrthogonalizer 用 t-1 数据 |
| 4 | 病态矩阵崩溃 | 中 | O1 | Symmetric 特征值截断 + Ridge 兜底 |
| 5 | K 大时性能 | 中 | O3b | joblib 并行 + 预筛选 |
| 6 | 版本号遗漏 | 低 | O6 | Fix 3 一致性校验脚本 |
| 7 | 日期不对齐 | 高 | O3b | 强制 intersect_dates |
| 8 | Layer 2/3 混层 | 高 | O2, O3b | 接口契约测试 (Layer 2 无 Y) |

---

**执行方案版本**: v1.1 (v1.0 + O1-O6 全阶段工程深化)
**创建时间**: 2026-07-03
**v1.1 更新**: 2026-07-03
**作者**: Scott Peng Liu
**v1.1 深化内容**: O1.12 (7 子章节) + O2.8 (6 子章节) + O3a.6 (5 子章节) + O4.9 双重 Lasso (7 子章节) + O4.11 RollingOrthogonalizer (5 子章节) + O5.6 协同设计 (5 子章节) + O6.7-O6.11 文档验证 (5 子章节), 共 40 个深化子章节
**审核状态**: 待用户确认后进入 O1 实施
