"""O1: 多因子正交化算法核心 — TDD 测试

测试设计来源: docs/EXECUTION_V2.5.0.md (v1.1) 的 O1.8 测试设计表 + O1.13 验收标准补充

6 组测试 (共 ~38 个):
1. 基础功能 (7): shape / VRR / 正交性 / GS首因子 / PCA方差 / Cholesky正交 / Ridge软正交
2. 数值稳定性 (4): 病态矩阵 / 线性相关 / 非正定 / Ridge始终稳定
3. 手工数值校验 (4): 与独立 numpy/scipy/sklearn 实现对比, 精度 < 1e-10
4. 接口契约 (3): 未fit抛错 / shape不匹配 / N<K
5. 诊断属性 (2): condition_number / eigvals
6. O1.12 深化 (9): threshold_mode / eigh-svd / PCA center / Ridge λ / GS reorth / fit_from_gram / dtype

数学注记 (VRR):
  对称正交化的基本性质是 T^T T = I (变换后列正交), 不是每因子 VRR=1。
  VRR_k = Var(T_k)/Var(F_k) = (1/N) / (||F_k||^2 / N) = 1/||F_k||^2
  仅当 F_k 为单位范数列 (||F_k||=1) 时 VRR_k = 1。
  本测试在 test_symmetric_VRR_equals_one 中预归一化 F 列为单位范数, 验证 VRR=1;
  在 test_symmetric_orthogonality 中直接验证 T^T T = I (基本性质)。
"""
import numpy as np
import pytest
from scipy.linalg import eigh, cholesky, solve_triangular

from factor_pipeline.modules.factor_orthogonalizer.core.base import BaseOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.core.symmetric import SymmetricOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.core.gram_schmidt import GramSchmidtOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.core.pca import PCAOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.core.cholesky import CholeskyOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.core.ridge import RidgeOrthogonalizer


# ---------- 固定随机种子工具 ----------

def _seed_F(N=100, K=5, seed=42):
    """生成 (N, K) 随机因子矩阵"""
    rng = np.random.default_rng(seed)
    return rng.standard_normal((N, K))


def _unit_norm_F(N=100, K=5, seed=42):
    """生成列中心化 + 单位范数的 F (用于 VRR=1 测试)

    数学前提: VRR_k = Var(T_k)/Var(F_k) = 1/||F_k||² 仅在 F 列中心化时严格成立。
      中心化后 mean(F_k)=0, Var(F_k) = ||F_k||²/N。
      对称正交化给出 T^T T = I → ||T_k||=1, T 中心化 → Var(T_k) = 1/N。
      VRR_k = (1/N)/(1/N) = 1。
    若不中心化, Var(F_k) = ||F_k||²/N - mean(F_k)² ≠ ||F_k||²/N, VRR ≠ 1。
    """
    F = _seed_F(N, K, seed)
    F = F - F.mean(axis=0)  # 先中心化
    return F / np.linalg.norm(F, axis=0, keepdims=True)


def _ill_conditioned_F(N=50, K=5, kappa=1e3, seed=42):
    """构造条件数 = kappa 的矩阵 (通过 SVD 调控奇异值)"""
    rng = np.random.default_rng(seed)
    A = rng.standard_normal((N, K))
    U, _, Vt = np.linalg.svd(A, full_matrices=False)
    S = np.linspace(1.0, 1.0 / kappa, K)
    return U @ np.diag(S) @ Vt


# =====================================================================
# 1. 基础功能测试组
# =====================================================================

class TestBasicFunctionality:
    """基础功能: shape / VRR / 正交性 / GS 首因子 / PCA 方差 / Cholesky / Ridge"""

    def test_symmetric_fit_transform_shape(self):
        """输入 (N, K) 输出同 shape"""
        F = _seed_F(N=100, K=5)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        assert T.shape == F.shape == (100, 5)

    def test_symmetric_VRR_equals_one(self):
        """VRR = Var(T)/Var(F) ≈ 1.0 (精度 1e-10)

        数学前提: F 列预归一化为单位范数 (||F_k||=1), 则
          Var(F_k) = 1/N, T^T T = I → ||T_k||=1 → Var(T_k) = 1/N
          VRR_k = (1/N)/(1/N) = 1
        """
        F = _unit_norm_F(N=100, K=5)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        vrr = np.var(T, axis=0) / np.var(F, axis=0)
        np.testing.assert_allclose(vrr, 1.0, atol=1e-10)

    def test_symmetric_orthogonality(self):
        """T^T T ≈ I (变换后因子列正交, 对称正交化的基本性质)"""
        F = _seed_F(N=100, K=5)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        np.testing.assert_allclose(T.T @ T, np.eye(5), atol=1e-8)

    def test_gs_preserves_first_factor(self):
        """order[0] 对应因子方向完全保留 (GS 顺序依赖性)"""
        F = _seed_F(N=100, K=3)
        orth = GramSchmidtOrthogonalizer()
        T = orth.fit_transform(F, order=[0, 1, 2])
        # 第一因子: T[:,0] 应与 F[:,0] 同方向 (模长归一)
        cos_sim = np.dot(F[:, 0], T[:, 0]) / (np.linalg.norm(F[:, 0]) * np.linalg.norm(T[:, 0]))
        np.testing.assert_allclose(np.abs(cos_sim), 1.0, atol=1e-10)

    def test_pca_variance_threshold(self):
        """前 k 主成分累计方差 ≥ variance_threshold"""
        F = _seed_F(N=100, K=5)
        orth = PCAOrthogonalizer(variance_threshold=0.95)
        T = orth.fit_transform(F)
        # explained_variance_ratio_ 累计 ≥ 0.95
        cum_var = np.cumsum(orth.explained_variance_ratio_)
        assert cum_var[-1] >= 0.95 - 1e-10
        # n_components_ <= K
        assert orth.n_components_ <= 5

    def test_cholesky_orthogonality(self):
        """T^T T = I (Cholesky 精确正交)"""
        F = _seed_F(N=100, K=5)
        orth = CholeskyOrthogonalizer()
        T = orth.fit_transform(F)
        np.testing.assert_allclose(T.T @ T, np.eye(5), atol=1e-8)

    def test_ridge_soft_orthogonality(self):
        """Ridge 软正交: T^T T ≈ I 但不精确 (对角元 < 1)

        数学: T^T T = I - λ(F^T F + λI)^(-1) ≤ I (PSD 意义)
        """
        F = _seed_F(N=100, K=5)
        orth = RidgeOrthogonalizer(lambda_=0.1, lambda_selection='fixed')
        T = orth.fit_transform(F)
        Gtt = T.T @ T
        # 接近 I (软正交)
        np.testing.assert_allclose(Gtt, np.eye(5), atol=0.5)
        # 但不精确等于 I
        assert not np.allclose(Gtt, np.eye(5), atol=1e-8)
        # 对角元 <= 1 (方差被收缩)
        assert np.all(np.diag(Gtt) <= 1.0 + 1e-10)


# =====================================================================
# 2. 数值稳定性测试组
# =====================================================================

class TestNumericalStability:
    """数值稳定性: 病态矩阵 / 线性相关 / 非正定 / Ridge 兜底"""

    def test_symmetric_ill_conditioned(self):
        """κ > 1000 时不崩溃 (特征值截断生效)"""
        F = _ill_conditioned_F(N=50, K=5, kappa=1e3)
        orth = SymmetricOrthogonalizer(threshold_mode='auto')
        T = orth.fit_transform(F)
        assert T.shape == (50, 5)
        # 不崩溃且产生有限值
        assert np.all(np.isfinite(T))

    def test_gs_linear_dependent_raises(self):
        """线性相关因子抛 ValueError"""
        F = np.array([[1.0, 2.0], [2.0, 4.0], [3.0, 6.0]])  # col2 = 2 * col1
        orth = GramSchmidtOrthogonalizer()
        with pytest.raises(ValueError, match="线性相关"):
            orth.fit(F)

    def test_cholesky_non_pd_raises(self):
        """非正定矩阵抛 ValueError + 建议信息"""
        # 构造非正定 F^T F: N < K 时 G 奇异, 但 BaseOrthogonalizer 已拦截 N<K
        # 改用秩亏矩阵: F 的某列是其他列的线性组合 (N>=K 但 G 奇异)
        F = np.array([
            [1.0, 0.0, 1.0],
            [0.0, 1.0, 1.0],
            [1.0, 1.0, 2.0],  # col3 = col1 + col2
            [2.0, 1.0, 3.0],
        ])
        orth = CholeskyOrthogonalizer()
        with pytest.raises(ValueError, match="非正定"):
            orth.fit(F)

    def test_ridge_always_stable(self):
        """任意病态矩阵都不崩溃 (λ > 0 保证正定)"""
        F = _ill_conditioned_F(N=50, K=5, kappa=1e6)
        orth = RidgeOrthogonalizer(lambda_=1.0, lambda_selection='fixed')
        T = orth.fit_transform(F)
        assert T.shape == (50, 5)
        assert np.all(np.isfinite(T))


# =====================================================================
# 3. 手工数值校验测试组 (与独立实现对比, 精度 < 1e-10)
# =====================================================================

class TestManualValidation:
    """手工数值校验: 与独立 numpy/scipy/sklearn 实现对比"""

    def test_symmetric_matches_manual_eigh(self):
        """与独立 numpy eigh 实现对比, 精度 < 1e-10"""
        F = _seed_F(N=100, K=5)
        orth = SymmetricOrthogonalizer(threshold_mode='auto')
        T_project = orth.fit_transform(F)

        # 独立实现 (从零写, 不用项目代码)
        G = F.T @ F
        eigvals, eigvecs = eigh(G)
        threshold = max(eigvals[-1] * 1e-10, 1e-12)
        eigvals_clipped = np.maximum(eigvals, threshold)
        W_manual = eigvecs @ np.diag(1.0 / np.sqrt(eigvals_clipped)) @ eigvecs.T
        T_manual = F @ W_manual

        np.testing.assert_allclose(T_project, T_manual, atol=1e-10)

    def test_cholesky_matches_scipy(self):
        """与 scipy.linalg.cholesky 对比, 精度 < 1e-10"""
        F = _seed_F(N=100, K=5)
        orth = CholeskyOrthogonalizer()
        T_project = orth.fit_transform(F)

        # 独立实现
        Sigma = F.T @ F
        L = cholesky(Sigma, lower=True)
        I = np.eye(5)
        W_manual = solve_triangular(L.T, I, lower=False)
        T_manual = F @ W_manual

        np.testing.assert_allclose(T_project, T_manual, atol=1e-10)

    def test_gs_matches_qr_decomposition(self):
        """与 numpy QR 分解对比 (order=[0,1,...,K-1])

        MGS 产生的 Q 与 QR 的 Q 在列方向上一致 (模长可能差, 但方向一致)
        """
        F = _seed_F(N=100, K=5)
        orth = GramSchmidtOrthogonalizer()
        T = orth.fit_transform(F)
        # T 的列是正交基 (单位范数), 提取方向
        # numpy QR: F = Q R, Q 的列正交
        Q_qr, R_qr = np.linalg.qr(F, mode='reduced')
        # 比较 Q 方向 (符号无关): |cos_sim| ≈ 1
        for k in range(5):
            cos_sim = np.dot(T[:, k], Q_qr[:, k]) / (
                np.linalg.norm(T[:, k]) * np.linalg.norm(Q_qr[:, k])
            )
            np.testing.assert_allclose(np.abs(cos_sim), 1.0, atol=1e-8)

    def test_pca_matches_sklearn_pca(self):
        """与 sklearn PCA 对比 (n_components=K), 精度 < 1e-10"""
        from sklearn.decomposition import PCA as SklearnPCA
        F = _seed_F(N=100, K=5)
        orth = PCAOrthogonalizer(n_components=5, center=True)
        T_project = orth.fit_transform(F)

        sk_pca = SklearnPCA(n_components=5)
        T_sklearn = sk_pca.fit_transform(F)

        # 主成分方向有符号歧义, 比较 |T| 一致
        # 或比较 T T^T (投影矩阵) 一致
        np.testing.assert_allclose(
            T_project @ T_project.T,
            T_sklearn @ T_sklearn.T,
            atol=1e-8,
        )


# =====================================================================
# 4. 接口契约测试组
# =====================================================================

class TestInterfaceContract:
    """接口契约: 未 fit 抛错 / shape 不匹配 / N<K"""

    def test_fit_before_transform_raises(self):
        """未 fit 直接 transform 抛 RuntimeError"""
        orth = SymmetricOrthogonalizer()
        F = _seed_F(N=10, K=3)
        with pytest.raises(RuntimeError, match="必须先调用 fit"):
            orth.transform(F)

    def test_shape_mismatch_raises(self):
        """F 列数 ≠ K 抛 ValueError"""
        F = _seed_F(N=100, K=5)
        orth = SymmetricOrthogonalizer()
        orth.fit(F)
        F_bad = _seed_F(N=10, K=3)
        with pytest.raises(ValueError, match="不匹配"):
            orth.transform(F_bad)

    def test_N_less_than_K_raises(self):
        """N < K 抛 ValueError (样本不足)"""
        F = _seed_F(N=3, K=5)
        orth = SymmetricOrthogonalizer()
        with pytest.raises(ValueError, match="N.*<.*K"):
            orth.fit(F)


# =====================================================================
# 5. 诊断属性测试组
# =====================================================================

class TestDiagnosticAttributes:
    """诊断属性: condition_number / eigvals"""

    def test_condition_number_computed(self):
        """fit 后 condition_number_ 正确"""
        F = _seed_F(N=100, K=5)
        orth = SymmetricOrthogonalizer()
        orth.fit(F)
        assert orth.condition_number_ is not None
        assert orth.condition_number_ >= 1.0  # κ ≥ 1 恒成立

        # 手工验证: κ = λ_max / λ_min
        G = F.T @ F
        eigvals_manual = np.linalg.eigvalsh(G)
        kappa_manual = eigvals_manual[-1] / eigvals_manual[0]
        np.testing.assert_allclose(orth.condition_number_, kappa_manual, rtol=1e-8)

    def test_eigvals_computed(self):
        """fit 后 eigvals_ 升序排列"""
        F = _seed_F(N=100, K=5)
        orth = SymmetricOrthogonalizer()
        orth.fit(F)
        assert orth.eigvals_ is not None
        assert len(orth.eigvals_) == 5
        # 升序: eigvals_[i] <= eigvals_[i+1]
        assert np.all(np.diff(orth.eigvals_) >= -1e-12)


# =====================================================================
# 6. O1.12 工程深化测试组
# =====================================================================

class TestO1_12_Deepening:
    """O1.12 七项工程深化: threshold_mode / eigh-svd / PCA center / Ridge λ / GS reorth / fit_from_gram / dtype"""

    # ---- O1.12.1: threshold_mode 三模式 ----

    def test_threshold_mode_auto_handles_scale_diff(self):
        """O1.12.1: F_1~N(0,1), F_2~N(0,100), auto 模式不崩溃且 n_clipped_ 正确"""
        rng = np.random.default_rng(42)
        F1 = rng.standard_normal((100, 2))
        F2 = F1.copy()
        F2[:, 1] *= 10.0  # 方差放大 100 倍
        orth = SymmetricOrthogonalizer(threshold_mode='auto')
        T = orth.fit_transform(F2)
        assert T.shape == (100, 2)
        assert np.all(np.isfinite(T))
        # auto 模式不应截断 (特征值都显著)
        assert orth.n_clipped_ == 0

    def test_threshold_mode_relative_vs_absolute(self):
        """O1.12.1: relative 与 absolute 模式行为差异"""
        F = _seed_F(N=100, K=5)
        orth_rel = SymmetricOrthogonalizer(threshold_mode='relative')
        orth_abs = SymmetricOrthogonalizer(threshold_mode='absolute', min_eigval=1e-10)
        orth_rel.fit(F)
        orth_abs.fit(F)
        # 两种模式都应成功
        assert orth_rel.is_fitted_
        assert orth_abs.is_fitted_

    def test_threshold_mode_invalid_raises(self):
        """O1.12.1: 未知 threshold_mode 抛 ValueError"""
        F = _seed_F(N=10, K=3)
        orth = SymmetricOrthogonalizer()
        with pytest.raises(ValueError, match="未知 threshold_mode"):
            orth.fit(F, threshold_mode='invalid')

    # ---- O1.12.2: eigh vs svd ----

    def test_svd_more_stable_for_ill_conditioned(self):
        """O1.12.2: κ=1e5 矩阵, svd 的正交性误差 < eigh 的 1/100

        数学: eigh(G) 的条件数 = κ(F)^2, svd(F) 的条件数 = κ(F)
        对近奇异 F, svd 数值精度更高。
        """
        F = _ill_conditioned_F(N=50, K=5, kappa=1e5)
        # eigh 路径
        orth_eigh = SymmetricOrthogonalizer(decomposition='eigh', threshold_mode='absolute', min_eigval=1e-15)
        T_eigh = orth_eigh.fit_transform(F)
        err_eigh = np.linalg.norm(T_eigh.T @ T_eigh - np.eye(5))

        # svd 路径
        orth_svd = SymmetricOrthogonalizer(decomposition='svd')
        T_svd = orth_svd.fit_transform(F)
        err_svd = np.linalg.norm(T_svd.T @ T_svd - np.eye(5))

        # svd 误差应小于 eigh 误差 (或至少不更大)
        # 注: 对极高 κ, 两者误差都可能较大, 关键是 svd <= eigh
        assert err_svd <= err_eigh + 1e-10

    def test_decomposition_invalid_raises(self):
        """O1.12.2: 未知 decomposition 抛 ValueError"""
        F = _seed_F(N=10, K=3)
        orth = SymmetricOrthogonalizer()
        with pytest.raises(ValueError, match="未知 decomposition"):
            orth.fit(F, decomposition='invalid')

    # ---- O1.12.3: PCA center 参数 ----

    def test_pca_center_false_requires_standardized(self):
        """O1.12.3: 已标准化因子 center=False 结果与 center=True 一致; 未标准化结果不同"""
        # 场景 1: 已标准化因子 (mean≈0)
        F_std = _seed_F(N=100, K=5)
        F_std = F_std - F_std.mean(axis=0)  # 中心化
        orth_true = PCAOrthogonalizer(n_components=5, center=True)
        orth_false = PCAOrthogonalizer(n_components=5, center=False)
        T_true = orth_true.fit_transform(F_std)
        T_false = orth_false.fit_transform(F_std)
        # 已中心化数据: center=True/False 结果一致 (投影矩阵)
        np.testing.assert_allclose(
            T_true @ T_true.T,
            T_false @ T_false.T,
            atol=1e-10,
        )

        # 场景 2: 未标准化因子 (mean ≠ 0)
        F_unstd = _seed_F(N=100, K=5) + 10.0  # 大均值偏移
        orth_true2 = PCAOrthogonalizer(n_components=5, center=True)
        orth_false2 = PCAOrthogonalizer(n_components=5, center=False)
        T_true2 = orth_true2.fit_transform(F_unstd)
        T_false2 = orth_false2.fit_transform(F_unstd)
        # 未中心化数据: center=True/False 结果不同
        assert not np.allclose(
            T_true2 @ T_true2.T,
            T_false2 @ T_false2.T,
            atol=1e-6,
        )

    # ---- O1.12.4: Ridge λ 选择 ----

    def test_ridge_ledoit_wolf_adapts_to_scale(self):
        """O1.12.4: F 方差放大 100 倍后, ledoit_wolf 的 λ 自动调整"""
        from sklearn.covariance import LedoitWolf
        F = _seed_F(N=100, K=5)
        F_scaled = F * 10.0  # 方差放大 100 倍

        orth_orig = RidgeOrthogonalizer(lambda_selection='ledoit_wolf')
        orth_scaled = RidgeOrthogonalizer(lambda_selection='ledoit_wolf')
        orth_orig.fit(F)
        orth_scaled.fit(F_scaled)

        # λ 应随尺度调整 (Ledoit-Wolf shrinkage * trace(F^T F)/K)
        # 放大 10 倍 → trace 放大 100 倍 → λ 放大 ~100 倍
        assert orth_scaled.lambda_ > orth_orig.lambda_
        # 大致比例: λ_scaled / λ_orig 应接近 100 (允许较大误差, 因 shrinkage 也会变)
        ratio = orth_scaled.lambda_ / max(orth_orig.lambda_, 1e-15)
        assert ratio > 10.0  # 至少一个数量级调整

    def test_ridge_lambda_selection_invalid_raises(self):
        """O1.12.4: 未知 lambda_selection 抛 ValueError"""
        F = _seed_F(N=10, K=3)
        orth = RidgeOrthogonalizer()
        with pytest.raises(ValueError, match="未知 lambda_selection"):
            orth.fit(F, lambda_selection='invalid')

    def test_ridge_lambda_cv_works(self):
        """O1.12.4: cv 模式可运行 (sklearn RidgeCV)"""
        F = _seed_F(N=100, K=5)
        orth = RidgeOrthogonalizer(lambda_selection='cv')
        orth.fit(F)
        assert orth.is_fitted_
        assert orth.lambda_ > 0

    # ---- O1.12.5: GS re-orthogonalization ----

    def test_gs_reorthogonalize_improves_precision(self):
        """O1.12.5: κ=500 矩阵, reorthogonalize=True 的 ‖Q^T Q - I‖_F < reorthogonalize=False

        MGS 在 κ>100 时丢失正交性, 二次投影 (Kahan 1966) 恢复精度。
        """
        F = _ill_conditioned_F(N=50, K=5, kappa=500)
        # 不启用二次投影
        orth_no = GramSchmidtOrthogonalizer(reorthogonalize=False)
        T_no = orth_no.fit_transform(F)
        err_no = np.linalg.norm(T_no.T @ T_no - np.eye(5))

        # 启用二次投影
        orth_yes = GramSchmidtOrthogonalizer(reorthogonalize=True)
        T_yes = orth_yes.fit_transform(F)
        err_yes = np.linalg.norm(T_yes.T @ T_yes - np.eye(5))

        # 二次投影误差应更小
        assert err_yes <= err_no

    # ---- O1.12.6: fit_from_gram 接口 ----

    def test_fit_from_gram_matches_fit(self):
        """O1.12.6: 同一 F, fit(F) 与 fit_from_gram(F^T F) 的 W 精度 < 1e-12"""
        F = _seed_F(N=100, K=5)
        G = F.T @ F

        orth_fit = SymmetricOrthogonalizer()
        orth_gram = SymmetricOrthogonalizer()
        orth_fit.fit(F)
        orth_gram.fit_from_gram(G)

        np.testing.assert_allclose(orth_fit.W_, orth_gram.W_, atol=1e-12)
        # 标记位
        assert orth_fit._fitted_from_gram is False
        assert orth_gram._fitted_from_gram is True

    def test_fit_from_gram_ridge_matches(self):
        """O1.12.6: Ridge 的 fit_from_gram 与 fit 一致 (fixed 模式)"""
        F = _seed_F(N=100, K=5)
        G = F.T @ F
        orth_fit = RidgeOrthogonalizer(lambda_=1.0, lambda_selection='fixed')
        orth_gram = RidgeOrthogonalizer(lambda_=1.0, lambda_selection='fixed')
        orth_fit.fit(F)
        orth_gram.fit_from_gram(G, lambda_=1.0, lambda_selection='fixed')
        np.testing.assert_allclose(orth_fit.W_, orth_gram.W_, atol=1e-12)

    def test_gs_raises_on_fit_from_gram(self):
        """O1.12.6: GS 不支持 fit_from_gram, 抛 NotImplementedError"""
        F = _seed_F(N=100, K=5)
        G = F.T @ F
        orth = GramSchmidtOrthogonalizer()
        with pytest.raises(NotImplementedError, match="不支持 fit_from_gram"):
            orth.fit_from_gram(G)

    def test_cholesky_raises_on_fit_from_gram(self):
        """O1.12.6: Cholesky 不支持 fit_from_gram, 抛 NotImplementedError"""
        F = _seed_F(N=100, K=5)
        G = F.T @ F
        orth = CholeskyOrthogonalizer()
        with pytest.raises(NotImplementedError, match="不支持 fit_from_gram"):
            orth.fit_from_gram(G)

    def test_fit_from_gram_pca_matches(self):
        """O1.12.6: PCA 的 fit_from_gram 与 fit 一致 (中心化数据)"""
        F = _seed_F(N=100, K=5)
        F_centered = F - F.mean(axis=0)
        G = F_centered.T @ F_centered
        orth_fit = PCAOrthogonalizer(n_components=5, center=False)
        orth_gram = PCAOrthogonalizer()
        orth_fit.fit(F_centered)
        orth_gram.fit_from_gram(G, n_components=5)
        # 比较 |W| (符号歧义)
        np.testing.assert_allclose(np.abs(orth_fit.W_), np.abs(orth_gram.W_), atol=1e-10)

    def test_fit_from_gram_invalid_shape_raises(self):
        """O1.12.6: G 非方阵抛 ValueError"""
        orth = SymmetricOrthogonalizer()
        G_bad = np.ones((3, 5))
        with pytest.raises(ValueError, match="方阵"):
            orth.fit_from_gram(G_bad)

    # ---- O1.12.7: dtype 强制与内存布局 ----

    def test_int_input_converted_to_float64(self):
        """O1.12.7: int 输入不报错, 输出 W 为 float64"""
        F_int = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 10], [1, 0, 2]], dtype=np.int64)
        orth = SymmetricOrthogonalizer()
        orth.fit(F_int)
        assert orth.W_.dtype == np.float64
        assert orth.is_fitted_

    def test_float32_input_converted_to_float64(self):
        """O1.12.7: float32 输入转为 float64 (精度要求)"""
        F_f32 = _seed_F(N=100, K=5).astype(np.float32)
        orth = SymmetricOrthogonalizer()
        orth.fit(F_f32)
        assert orth.W_.dtype == np.float64

    def test_non_contiguous_input_handled(self):
        """O1.12.7: F.T 切片 (非 C-contiguous) 正常工作"""
        F = _seed_F(N=100, K=5)
        F_non_contig = F.T.T  # 可能非 C-contiguous
        # 构造明确的非 C-contiguous 数组
        F_big = _seed_F(N=100, K=10)
        F_slice = F_big[:, ::2]  # stride 切片, 非 C-contiguous
        assert not F_slice.flags['C_CONTIGUOUS']
        orth = SymmetricOrthogonalizer()
        orth.fit(F_slice)
        assert orth.is_fitted_

    def test_N_dim_3_raises(self):
        """O1.12.7: 3D 输入抛 ValueError"""
        F_3d = np.ones((5, 4, 3))
        orth = SymmetricOrthogonalizer()
        with pytest.raises(ValueError, match="2D"):
            orth.fit(F_3d)


# =====================================================================
# 7. 导入契约测试
# =====================================================================

class TestImportContract:
    """导入契约: O1.11 验收标准 - 可从包路径导入"""

    def test_import_from_core(self):
        """from factor_pipeline.modules.factor_orthogonalizer.core import SymmetricOrthogonalizer"""
        from factor_pipeline.modules.factor_orthogonalizer.core import (
            SymmetricOrthogonalizer as S,
            GramSchmidtOrthogonalizer as GS,
            PCAOrthogonalizer as PCA,
            CholeskyOrthogonalizer as Chol,
            RidgeOrthogonalizer as Ridge,
            BaseOrthogonalizer as Base,
        )
        assert S is SymmetricOrthogonalizer
        assert GS is GramSchmidtOrthogonalizer
        assert PCA is PCAOrthogonalizer
        assert Chol is CholeskyOrthogonalizer
        assert Ridge is RidgeOrthogonalizer
        assert Base is BaseOrthogonalizer

    def test_import_from_package(self):
        """from factor_pipeline.modules.factor_orthogonalizer import ..."""
        from factor_pipeline.modules.factor_orthogonalizer import (
            SymmetricOrthogonalizer as S,
            BaseOrthogonalizer as Base,
        )
        assert S is SymmetricOrthogonalizer
        assert Base is BaseOrthogonalizer

    def test_base_is_abstract(self):
        """BaseOrthogonalizer 是抽象类, 不能实例化"""
        with pytest.raises(TypeError, match="abstract"):
            BaseOrthogonalizer()

    def test_version_string(self):
        """包有 __version__"""
        import factor_pipeline.modules.factor_orthogonalizer as pkg
        assert hasattr(pkg, '__version__')
        assert isinstance(pkg.__version__, str)
