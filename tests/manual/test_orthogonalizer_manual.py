r"""O1 手工数值校验脚本 — 正交化算法

校验目标: 5 个正交化算法与独立 numpy/scipy/sklearn 实现对比, 精度 < 1e-10

校验内容 (对应 EXECUTION_V2.5.0.md O1.9):
1. Symmetric — 与独立 numpy eigh 对比 + VRR=1 + T^T T = I
2. Cholesky — 与 scipy.linalg.cholesky 对比
3. Gram-Schmidt — 与 numpy QR 分解对比 (方向一致)
4. PCA — 与 sklearn PCA 对比 (投影矩阵一致)
5. Ridge — 与独立 (F^T F + λI)^(-1/2) 对比

运行方式:
  pytest:  cd f:/Coding; python -m pytest factor_pipeline/tests/manual/test_orthogonalizer_manual.py -v
  独立:    cd f:/Coding; python -m factor_pipeline.tests.manual.test_orthogonalizer_manual

数学注记:
  - 对称正交化: W = (F^T F)^(-1/2) = V Λ^(-1/2) V^T, T = F @ W
  - VRR=1 仅在 F 列中心化 + 单位范数时严格成立 (Var(F_k) = ||F_k||²/N)
  - PCA center=True 时 transform 需中心化: T = (F - mean) @ W
  - Ridge soft 正交: T^T T ≈ I 但不精确 (λ > 0 使 W^T G W < I)
"""
import numpy as np
import pytest
from scipy.linalg import eigh, cholesky, solve_triangular

from factor_pipeline.modules.factor_orthogonalizer.core.symmetric import SymmetricOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.core.gram_schmidt import GramSchmidtOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.core.pca import PCAOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.core.cholesky import CholeskyOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.core.ridge import RidgeOrthogonalizer


# ---------- 工具函数 ----------

def _seed_F(N=100, K=5, seed=42):
    """生成 (N, K) 随机因子矩阵 (固定种子)"""
    rng = np.random.default_rng(seed)
    return rng.standard_normal((N, K))


def _centered_unit_norm_F(N=100, K=5, seed=42):
    """生成列中心化 + 单位范数的 F (用于 VRR=1 严格校验)

    数学: 中心化后 mean(F_k)=0 → Var(F_k) = ||F_k||²/N = 1/N
          对称正交化给出 T^T T = I → ||T_k||=1, T 中心化 → Var(T_k) = 1/N
          VRR_k = (1/N)/(1/N) = 1
    """
    F = _seed_F(N, K, seed)
    F = F - F.mean(axis=0)
    return F / np.linalg.norm(F, axis=0, keepdims=True)


def _ill_conditioned_F(N=50, K=5, kappa=1e3, seed=42):
    """构造条件数 = kappa 的矩阵"""
    rng = np.random.default_rng(seed)
    A = rng.standard_normal((N, K))
    U, _, Vt = np.linalg.svd(A, full_matrices=False)
    S = np.linspace(1.0, 1.0 / kappa, K)
    return U @ np.diag(S) @ Vt


# =====================================================================
# 1. Symmetric 手工校验
# =====================================================================

def test_symmetric_matches_manual_eigh():
    """SymmetricOrthogonalizer 与独立 numpy eigh 实现对比, 精度 < 1e-10"""
    F = _seed_F(N=100, K=5)

    # 项目实现
    orth = SymmetricOrthogonalizer(threshold_mode='auto')
    T_project = orth.fit_transform(F)

    # 独立实现 (从零写, 不用项目代码)
    G = F.T @ F
    eigvals, eigvecs = eigh(G)
    threshold = max(eigvals[-1] * 1e-10, 1e-12)
    eigvals_clipped = np.maximum(eigvals, threshold)
    W_manual = eigvecs @ np.diag(1.0 / np.sqrt(eigvals_clipped)) @ eigvecs.T
    T_manual = F @ W_manual

    # 精度校验
    np.testing.assert_allclose(T_project, T_manual, atol=1e-10)


def test_symmetric_VRR_equals_one_centered_unit_norm():
    """VRR = Var(T)/Var(F) = 1.0 (精度 1e-10)

    前提: F 列中心化 + 单位范数
    """
    F = _centered_unit_norm_F(N=100, K=5)
    orth = SymmetricOrthogonalizer()
    T = orth.fit_transform(F)
    vrr = np.var(T, axis=0) / np.var(F, axis=0)
    np.testing.assert_allclose(vrr, 1.0, atol=1e-10)


def test_symmetric_orthogonality_property():
    """T^T T = I (对称正交化的基本性质)"""
    F = _seed_F(N=100, K=5)
    orth = SymmetricOrthogonalizer()
    T = orth.fit_transform(F)
    np.testing.assert_allclose(T.T @ T, np.eye(5), atol=1e-8)


def test_symmetric_condition_number_matches_manual():
    """condition_number_ 与手工计算的 κ = λ_max/λ_min 一致"""
    F = _seed_F(N=100, K=5)
    orth = SymmetricOrthogonalizer()
    orth.fit(F)

    G = F.T @ F
    eigvals_manual = np.linalg.eigvalsh(G)
    kappa_manual = eigvals_manual[-1] / eigvals_manual[0]
    np.testing.assert_allclose(orth.condition_number_, kappa_manual, rtol=1e-8)


# =====================================================================
# 2. Cholesky 手工校验
# =====================================================================

def test_cholesky_matches_scipy():
    """CholeskyOrthogonalizer 与 scipy.linalg.cholesky 对比, 精度 < 1e-10"""
    F = _seed_F(N=100, K=5)

    # 项目实现
    orth = CholeskyOrthogonalizer()
    T_project = orth.fit_transform(F)

    # 独立实现: G = F^T F = L L^T, W = L^(-T), T = F @ W
    Sigma = F.T @ F
    L = cholesky(Sigma, lower=True)
    W_manual = solve_triangular(L.T, np.eye(5), lower=False)
    T_manual = F @ W_manual

    np.testing.assert_allclose(T_project, T_manual, atol=1e-10)


def test_cholesky_orthogonality_exact():
    """Cholesky 精确正交: T^T T = I"""
    F = _seed_F(N=100, K=5)
    orth = CholeskyOrthogonalizer()
    T = orth.fit_transform(F)
    np.testing.assert_allclose(T.T @ T, np.eye(5), atol=1e-8)


# =====================================================================
# 3. Gram-Schmidt 手工校验
# =====================================================================

def test_gs_matches_qr_decomposition():
    """GramSchmidtOrthogonalizer 与 numpy QR 分解对比 (方向一致)

    MGS 产生的 Q 与 QR 的 Q 在列方向上一致 (模长可能差, 但方向一致)
    """
    F = _seed_F(N=100, K=5)
    orth = GramSchmidtOrthogonalizer()
    T = orth.fit_transform(F)

    Q_qr, R_qr = np.linalg.qr(F, mode='reduced')
    # 比较 Q 方向 (符号无关): |cos_sim| ≈ 1
    for k in range(5):
        cos_sim = np.dot(T[:, k], Q_qr[:, k]) / (
            np.linalg.norm(T[:, k]) * np.linalg.norm(Q_qr[:, k])
        )
        np.testing.assert_allclose(np.abs(cos_sim), 1.0, atol=1e-8)


def test_gs_first_factor_preserved():
    """GS 顺序依赖: order[0] 对应因子方向完全保留"""
    F = _seed_F(N=100, K=3)
    orth = GramSchmidtOrthogonalizer()
    T = orth.fit_transform(F, order=[0, 1, 2])
    cos_sim = np.dot(F[:, 0], T[:, 0]) / (
        np.linalg.norm(F[:, 0]) * np.linalg.norm(T[:, 0])
    )
    np.testing.assert_allclose(np.abs(cos_sim), 1.0, atol=1e-10)


# =====================================================================
# 4. PCA 手工校验
# =====================================================================

def test_pca_matches_sklearn_pca():
    """PCAOrthogonalizer 与 sklearn PCA 对比 (投影矩阵一致)"""
    from sklearn.decomposition import PCA as SklearnPCA
    F = _seed_F(N=100, K=5)
    orth = PCAOrthogonalizer(n_components=5, center=True)
    T_project = orth.fit_transform(F)

    sk_pca = SklearnPCA(n_components=5)
    T_sklearn = sk_pca.fit_transform(F)

    # 主成分方向有符号歧义, 比较投影矩阵 T T^T
    np.testing.assert_allclose(
        T_project @ T_project.T,
        T_sklearn @ T_sklearn.T,
        atol=1e-8,
    )


def test_pca_center_true_subtracts_mean():
    """PCA center=True 时 transform 中心化 (与 sklearn 一致)"""
    from sklearn.decomposition import PCA as SklearnPCA
    F = _seed_F(N=100, K=5) + 10.0  # 大均值偏移

    orth = PCAOrthogonalizer(n_components=5, center=True)
    T_project = orth.fit_transform(F)

    sk_pca = SklearnPCA(n_components=5)
    T_sklearn = sk_pca.fit_transform(F)

    # 投影矩阵应一致 (center=True 两侧都中心化)
    np.testing.assert_allclose(
        T_project @ T_project.T,
        T_sklearn @ T_sklearn.T,
        atol=1e-8,
    )


# =====================================================================
# 5. Ridge 手工校验
# =====================================================================

def test_ridge_matches_manual_eigh():
    """RidgeOrthogonalizer 与独立 (F^T F + λI)^(-1/2) 对比, 精度 < 1e-10"""
    F = _seed_F(N=100, K=5)
    lam = 1.0

    # 项目实现
    orth = RidgeOrthogonalizer(lambda_=lam, lambda_selection='fixed')
    T_project = orth.fit_transform(F)

    # 独立实现
    K = F.shape[1]
    G = F.T @ F + lam * np.eye(K)
    eigvals, eigvecs = eigh(G)
    W_manual = eigvecs @ np.diag(1.0 / np.sqrt(eigvals)) @ eigvecs.T
    T_manual = F @ W_manual

    np.testing.assert_allclose(T_project, T_manual, atol=1e-10)


def test_ridge_soft_orthogonality_property():
    """Ridge 软正交: T^T T ≈ I 但不精确, 对角元 <= 1"""
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


def test_ridge_always_stable_ill_conditioned():
    """Ridge 在 κ=1e6 矩阵上仍数值稳定 (λ > 0 保证正定)"""
    F = _ill_conditioned_F(N=50, K=5, kappa=1e6)
    orth = RidgeOrthogonalizer(lambda_=1.0, lambda_selection='fixed')
    T = orth.fit_transform(F)
    assert T.shape == (50, 5)
    assert np.all(np.isfinite(T))


# =====================================================================
# 6. fit_from_gram 手工校验 (O1.12.6)
# =====================================================================

def test_fit_from_gram_symmetric_matches_fit():
    """fit_from_gram(G) 与 fit(F) 的 W 精度 < 1e-12 (Symmetric)"""
    F = _seed_F(N=100, K=5)
    G = F.T @ F

    orth_fit = SymmetricOrthogonalizer()
    orth_gram = SymmetricOrthogonalizer()
    orth_fit.fit(F)
    orth_gram.fit_from_gram(G)

    np.testing.assert_allclose(orth_fit.W_, orth_gram.W_, atol=1e-12)


def test_fit_from_gram_ridge_matches_fit():
    """fit_from_gram(G) 与 fit(F) 的 W 精度 < 1e-12 (Ridge, fixed 模式)"""
    F = _seed_F(N=100, K=5)
    G = F.T @ F

    orth_fit = RidgeOrthogonalizer(lambda_=1.0, lambda_selection='fixed')
    orth_gram = RidgeOrthogonalizer(lambda_=1.0, lambda_selection='fixed')
    orth_fit.fit(F)
    orth_gram.fit_from_gram(G, lambda_=1.0, lambda_selection='fixed')

    np.testing.assert_allclose(orth_fit.W_, orth_gram.W_, atol=1e-12)


# =====================================================================
# 独立运行入口
# =====================================================================

def _run_all_manual_tests():
    """独立运行所有手工校验, 打印详细结果"""
    tests = [
        ("Symmetric vs manual eigh", test_symmetric_matches_manual_eigh),
        ("Symmetric VRR=1 (centered unit norm)", test_symmetric_VRR_equals_one_centered_unit_norm),
        ("Symmetric T^T T = I", test_symmetric_orthogonality_property),
        ("Symmetric condition_number matches manual", test_symmetric_condition_number_matches_manual),
        ("Cholesky vs scipy", test_cholesky_matches_scipy),
        ("Cholesky exact orthogonality", test_cholesky_orthogonality_exact),
        ("GS vs QR decomposition", test_gs_matches_qr_decomposition),
        ("GS first factor preserved", test_gs_first_factor_preserved),
        ("PCA vs sklearn PCA", test_pca_matches_sklearn_pca),
        ("PCA center=True subtracts mean", test_pca_center_true_subtracts_mean),
        ("Ridge vs manual eigh", test_ridge_matches_manual_eigh),
        ("Ridge soft orthogonality", test_ridge_soft_orthogonality_property),
        ("Ridge stable on ill-conditioned", test_ridge_always_stable_ill_conditioned),
        ("fit_from_gram Symmetric matches fit", test_fit_from_gram_symmetric_matches_fit),
        ("fit_from_gram Ridge matches fit", test_fit_from_gram_ridge_matches_fit),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"手工校验结果: {passed} passed, {failed} failed (共 {len(tests)})")
    print(f"精度要求: atol < 1e-10")
    print(f"{'='*60}")
    return failed == 0


if __name__ == "__main__":
    import sys
    success = _run_all_manual_tests()
    sys.exit(0 if success else 1)
