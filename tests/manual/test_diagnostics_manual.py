# -*- coding: utf-8 -*-
"""O3a 手工数值校验脚本 — 正交化几何诊断

校验目标: OrthogonalizationDiagnostics 类与独立 numpy/scipy 实现对比, 精度 < 1e-10
对应: EXECUTION_V2.5.0.md O3a.4 手工数值校验方案 (v1.1 修正版)

校验项目 (5 项):
1. VRR — 与独立 np.var 计算对比 + 中心化单位范数 F 的 VRR=1 严格校验
2. 条件数 κ — 与独立 np.linalg.eigvalsh 对比 + 病态矩阵识别
3. VIF — 三方法 (lstsq/qr/pinv) 互相验证 + 与 statsmodels OLS 对比 (可选)
4. 正交性误差 — 与独立 np.linalg.norm 计算 + T^T T = I 校验
5. full_diagnostics — 字段完整性 + redundant/multicollinear 索引正确性

数学注记 (VRR, v1.1 修正):
  文档 O3a.4 原方案 "对称正交化 VRR=1" 基于 "保持方差" 直觉, 实际数学:
  - 对称正交化使 T^T T = I (||T_k||=1), 不是保持单因子方差
  - Var(T_k) ≈ 1/N (mean≈0), Var(F_k)≈1 (randn), 故 VRR ≈ 1/N < 1
  - VRR = 1 仅当 F 列预归一化为单位范数时成立 (中心化 + ||F_k||=1)
  本脚本同时校验两种情况: randn F (VRR≈1/N) 和 unit_norm F (VRR=1).

运行方式:
  pytest:  cd f:/Coding; python -m pytest factor_pipeline/tests/manual/test_diagnostics_manual.py -v
  独立:    cd f:/Coding; python -m factor_pipeline.tests.manual.test_diagnostics_manual
"""
from __future__ import annotations

import json
import numpy as np
import pytest
from scipy.linalg import eigh

from factor_pipeline.modules.factor_orthogonalizer.core.symmetric import (
    SymmetricOrthogonalizer,
)
from factor_pipeline.modules.factor_orthogonalizer.core.diagnostics import (
    OrthogonalizationDiagnostics,
)


# ---------- 工具函数 ----------

def _seed_F(N: int = 100, K: int = 5, seed: int = 42) -> np.ndarray:
    """生成 (N, K) 随机因子矩阵 (固定种子)"""
    rng = np.random.default_rng(seed)
    return rng.standard_normal((N, K))


def _centered_unit_norm_F(N: int = 100, K: int = 5, seed: int = 42) -> np.ndarray:
    """生成列中心化 + 单位范数的 F (用于 VRR=1 严格校验)

    数学:
      中心化: mean(F_k)=0 → Var(F_k) = ||F_k||²/N = 1/N (因 ||F_k||=1)
      对称正交化: T^T T = I → ||T_k||=1, T 也中心化 → Var(T_k) = 1/N
      VRR_k = Var(T_k)/Var(F_k) = (1/N)/(1/N) = 1
    """
    F = _seed_F(N, K, seed)
    F = F - F.mean(axis=0)
    return F / np.linalg.norm(F, axis=0, keepdims=True)


def _collinear_F(N: int = 200, K: int = 3, rho: float = 0.95, seed: int = 42) -> np.ndarray:
    """构造 K 个高相关因子 (rho 越大相关性越高)"""
    rng = np.random.default_rng(seed)
    base = rng.standard_normal((N, 1))
    noise = rng.standard_normal((N, K)) * np.sqrt(1 - rho ** 2)
    return np.sqrt(rho) * base + noise


def _redundant_F(N: int = 200, seed: int = 42) -> np.ndarray:
    """构造 1 个冗余因子 (f2 = 0.99 * f1 + noise)"""
    rng = np.random.default_rng(seed)
    f1 = rng.standard_normal((N, 1))
    f2 = 0.99 * f1 + 0.01 * rng.standard_normal((N, 1))
    return np.hstack([f1, f2])


# =============================================================================
# 1. VRR 手工校验
# =============================================================================

class TestVRRManual:
    """VRR 手工数值校验"""

    def test_vrr_matches_manual_np_var(self):
        """1.1 VRR 与独立 np.var 计算对比 (精度 1e-12)"""
        F = _seed_F(N=100, K=5)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)

        # 项目实现
        vrr_project = OrthogonalizationDiagnostics.compute_vrr(F, T)

        # 手工计算 (独立实现)
        var_F = np.var(F, axis=0, ddof=0)
        var_T = np.var(T, axis=0, ddof=0)
        vrr_manual = var_T / var_F

        np.testing.assert_allclose(vrr_project, vrr_manual, atol=1e-12,
                                   err_msg="VRR 与独立 np.var 计算不一致")

    def test_vrr_unit_norm_equals_one(self):
        """1.2 中心化+单位范数 F 的 VRR=1 (精度 1e-10)

        数学: 中心化 + ||F_k||=1 → Var(F_k)=1/N
              对称正交化 T^T T=I → ||T_k||=1, T 中心化 → Var(T_k)=1/N
              VRR = (1/N)/(1/N) = 1
        """
        F = _centered_unit_norm_F(N=100, K=5)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        vrr = OrthogonalizationDiagnostics.compute_vrr(F, T)
        np.testing.assert_allclose(vrr, 1.0, atol=1e-10,
                                   err_msg=f"中心化单位范数 F 的 VRR 应=1, 实际={vrr}")

    def test_vrr_randn_compresses_to_one_over_N(self):
        """1.3 randn F (未归一化) 的 VRR ≈ 1/N (精度 0.01)

        数学: 对称正交化 T^T T=I → ||T_k||=1 → Var(T_k)≈1/N
              Var(F_k)≈1 (randn 标准正态)
              VRR ≈ 1/N
        """
        N = 100
        F = _seed_F(N=N, K=5)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        vrr = OrthogonalizationDiagnostics.compute_vrr(F, T)
        # VRR 应在 1/N 附近 (允许较大容差, 因 randn 的方差波动)
        np.testing.assert_allclose(vrr, 1.0 / N, atol=0.01,
                                   err_msg=f"randn F 的 VRR 应≈1/N={1.0/N}, 实际={vrr}")

    def test_vrr_ddof_invariance(self):
        """1.4 VRR ddof 不变性 (精度 1e-12)

        数学: VRR = Var(T,ddof)/Var(F,ddof), 分子分母同时乘 N/(N-1), 比值不变.
        """
        F = _seed_F(N=100, K=5)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        vrr_0 = OrthogonalizationDiagnostics.compute_vrr(F, T, ddof=0)
        vrr_1 = OrthogonalizationDiagnostics.compute_vrr(F, T, ddof=1)
        np.testing.assert_allclose(vrr_0, vrr_1, atol=1e-12,
                                   err_msg="VRR ddof 不变性失败")

    def test_vrr_redundant_factor_below_threshold(self):
        """1.5 冗余因子 VRR < 0.3 (识别能力校验)"""
        F = _redundant_F(N=200)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        vrr = OrthogonalizationDiagnostics.compute_vrr(F, T)
        assert vrr[1] < 0.3, f"冗余因子 VRR={vrr[1]} 应 < 0.3"


# =============================================================================
# 2. 条件数 κ 手工校验
# =============================================================================

class TestConditionNumberManual:
    """条件数 κ 手工数值校验"""

    def test_kappa_matches_manual_eigvalsh(self):
        """2.1 κ 与独立 np.linalg.eigvalsh 对比 (精度 1e-10)"""
        F = _seed_F(N=100, K=5)
        kappa_project = OrthogonalizationDiagnostics.compute_condition_number(F)

        # 手工计算
        G = F.T @ F
        eigvals = np.linalg.eigvalsh(G)
        kappa_manual = eigvals[-1] / eigvals[0]

        np.testing.assert_allclose(kappa_project, kappa_manual, atol=1e-10,
                                   err_msg="κ 与独立 eigvalsh 计算不一致")

    def test_kappa_matches_base_orthogonalizer(self):
        """2.2 κ 与 BaseOrthogonalizer.condition_number_ 一致 (精度 1e-10)"""
        F = _seed_F(N=100, K=5)
        orth = SymmetricOrthogonalizer()
        orth.fit(F)
        kappa_base = orth.condition_number_
        kappa_diag = OrthogonalizationDiagnostics.compute_condition_number(F)
        np.testing.assert_allclose(kappa_diag, kappa_base, atol=1e-10,
                                   err_msg="diagnostics.κ 与 base.condition_number_ 不一致")

    def test_kappa_singular_matrix_inf(self):
        """2.3 奇异矩阵 κ = inf (零列)"""
        F = np.array([[1.0, 0.0], [2.0, 0.0], [3.0, 0.0]])
        kappa = OrthogonalizationDiagnostics.compute_condition_number(F)
        assert np.isinf(kappa), f"奇异矩阵 κ 应=inf, 实际={kappa}"

    def test_kappa_severity_thresholds(self):
        """2.4 Belsley-Kuh-Welsch 四级分级阈值边界"""
        sev = OrthogonalizationDiagnostics.condition_number_severity
        # 边界值: 10, 100, 1000
        assert sev(9.999) == 'good'
        assert sev(10.0) == 'acceptable'  # 边界属于下一级
        assert sev(99.999) == 'acceptable'
        assert sev(100.0) == 'warning'
        assert sev(999.999) == 'warning'
        assert sev(1000.0) == 'severe'


# =============================================================================
# 3. VIF 手工校验
# =============================================================================

class TestVIFManual:
    """VIF 手工数值校验"""

    def test_vif_matches_manual_lstsq(self):
        """3.1 VIF 与独立 lstsq OLS 对比 (精度 1e-10)"""
        F = _seed_F(N=100, K=5)
        vif_project = OrthogonalizationDiagnostics.compute_vif(F, method='lstsq')

        # 手工计算 (独立 OLS)
        N, K = F.shape
        vif_manual = np.zeros(K)
        for k in range(K):
            F_others = np.delete(F, k, axis=1)
            F_k = F[:, k]
            X = np.column_stack([np.ones(N), F_others])
            beta, _, _, _ = np.linalg.lstsq(X, F_k, rcond=None)
            F_k_pred = X @ beta
            ss_res = np.sum((F_k - F_k_pred) ** 2)
            ss_tot = np.sum((F_k - np.mean(F_k)) ** 2)
            r2 = 1.0 - ss_res / ss_tot
            vif_manual[k] = 1.0 / (1.0 - r2)

        np.testing.assert_allclose(vif_project, vif_manual, atol=1e-10,
                                   err_msg="VIF 与独立 lstsq 计算不一致")

    def test_vif_three_methods_consistent_well_conditioned(self):
        """3.2 三方法 (lstsq/qr/pinv) 在良好矩阵下一致 (精度 1e-10)"""
        F = _seed_F(N=200, K=4)  # 大 N 良好条件数
        vif_lstsq = OrthogonalizationDiagnostics.compute_vif(F, method='lstsq')
        vif_qr = OrthogonalizationDiagnostics.compute_vif(F, method='qr')
        vif_pinv = OrthogonalizationDiagnostics.compute_vif(F, method='pinv')
        np.testing.assert_allclose(vif_lstsq, vif_qr, atol=1e-10,
                                   err_msg="lstsq vs qr 不一致")
        np.testing.assert_allclose(vif_lstsq, vif_pinv, atol=1e-10,
                                   err_msg="lstsq vs pinv 不一致")

    def test_vif_perfect_collinearity_inf(self):
        """3.3 完美共线 VIF = inf"""
        rng = np.random.default_rng(42)
        f1 = rng.standard_normal(100)
        f2 = 2.0 * f1  # 完美共线
        f3 = rng.standard_normal(100)
        F = np.column_stack([f1, f2, f3])
        vif = OrthogonalizationDiagnostics.compute_vif(F)
        assert np.isinf(vif[0]) or np.isinf(vif[1]), \
            f"完美共线 VIF 应有 inf, 实际={vif}"

    def test_vif_formula_matches_definition(self):
        """3.4 VIF 公式校验: VIF_k = 1/(1-R²_k), R² 用独立计算"""
        F = _collinear_F(N=300, K=4, rho=0.8)
        vif_project = OrthogonalizationDiagnostics.compute_vif(F)

        # 手工 R² 与 VIF 公式
        N, K = F.shape
        for k in range(K):
            F_others = np.delete(F, k, axis=1)
            F_k = F[:, k]
            X = np.column_stack([np.ones(N), F_others])
            # 用正规方程独立求解
            beta = np.linalg.solve(X.T @ X, X.T @ F_k)
            F_k_pred = X @ beta
            ss_res = np.sum((F_k - F_k_pred) ** 2)
            ss_tot = np.sum((F_k - np.mean(F_k)) ** 2)
            r2 = 1.0 - ss_res / ss_tot
            vif_expected = 1.0 / (1.0 - r2)
            np.testing.assert_allclose(vif_project[k], vif_expected, atol=1e-10,
                                       err_msg=f"VIF[{k}] 公式校验失败")


# =============================================================================
# 4. 正交性误差手工校验
# =============================================================================

class TestOrthogonalityErrorManual:
    """正交性误差手工数值校验"""

    def test_orth_error_matches_manual_frobenius(self):
        """4.1 正交性误差与独立 Frobenius 范数计算对比 (精度 1e-12)"""
        F = _seed_F(N=100, K=5)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)

        err_project = OrthogonalizationDiagnostics.compute_orthogonality_error(T)

        # 手工计算
        Sigma = T.T @ T
        off_diag = Sigma - np.diag(np.diag(Sigma))
        err_manual = np.linalg.norm(off_diag, 'fro')

        np.testing.assert_allclose(err_project, err_manual, atol=1e-12,
                                   err_msg="正交性误差与独立计算不一致")

    def test_orth_error_after_symmetric_near_zero(self):
        """4.2 对称正交化后误差 < 1e-10 (T^T T ≈ I)"""
        F = _seed_F(N=100, K=5)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        err = OrthogonalizationDiagnostics.compute_orthogonality_error(T)
        assert err < 1e-10, f"对称正交化后误差={err} 应 < 1e-10"

    def test_orth_error_normalized_matches_manual(self):
        """4.3 normalized 误差 = ‖off‖/‖Σ‖ 与独立计算对比 (精度 1e-12)"""
        F = _collinear_F(N=200, K=4, rho=0.7)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)

        err_project = OrthogonalizationDiagnostics.compute_orthogonality_error(
            T, norm='normalized'
        )

        # 手工计算
        Sigma = T.T @ T
        off_diag = Sigma - np.diag(np.diag(Sigma))
        err_manual = np.linalg.norm(off_diag, 'fro') / np.linalg.norm(Sigma, 'fro')

        np.testing.assert_allclose(err_project, err_manual, atol=1e-12,
                                   err_msg="normalized 误差与独立计算不一致")

    def test_orth_error_max_abs_matches_manual(self):
        """4.4 max_abs 误差 = max|Σ_jk| (j≠k) 与独立计算对比 (精度 1e-12)"""
        F = _seed_F(N=100, K=5)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)

        err_project = OrthogonalizationDiagnostics.compute_orthogonality_error(
            T, norm='max_abs'
        )

        # 手工计算
        Sigma = T.T @ T
        off_diag = Sigma - np.diag(np.diag(Sigma))
        err_manual = np.max(np.abs(off_diag))

        np.testing.assert_allclose(err_project, err_manual, atol=1e-12,
                                   err_msg="max_abs 误差与独立计算不一致")

    def test_TTranspose_T_equals_identity(self):
        """4.5 对称正交化后 T^T T = I (精度 1e-10) — 核心数学性质"""
        F = _seed_F(N=100, K=5)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        I_K = np.eye(5)
        np.testing.assert_allclose(T.T @ T, I_K, atol=1e-10,
                                   err_msg="T^T T ≠ I (对称正交化核心性质失败)")


# =============================================================================
# 5. full_diagnostics + JSON 序列化手工校验
# =============================================================================

class TestFullDiagnosticsManual:
    """full_diagnostics 与 JSON 序列化手工校验"""

    def test_full_diagnostics_field_completeness(self):
        """5.1 full_diagnostics 返回 6 个字段且类型正确"""
        F = _seed_F(N=100, K=5)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        diag = OrthogonalizationDiagnostics.full_diagnostics(F, T)

        expected_keys = {
            'vrr', 'condition_number', 'vif',
            'orthogonality_error', 'redundant_factors', 'multicollinear_factors'
        }
        assert set(diag.keys()) == expected_keys, \
            f"字段不匹配: {set(diag.keys())} vs {expected_keys}"

        # 类型校验
        assert isinstance(diag['vrr'], np.ndarray)
        assert isinstance(diag['condition_number'], float)
        assert isinstance(diag['vif'], np.ndarray)
        assert isinstance(diag['orthogonality_error'], float)
        assert isinstance(diag['redundant_factors'], list)
        assert isinstance(diag['multicollinear_factors'], list)

    def test_full_diagnostics_values_match_individual_methods(self):
        """5.2 full_diagnostics 的值与单独调用各方法一致 (精度 1e-12)"""
        F = _seed_F(N=100, K=5)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)

        diag = OrthogonalizationDiagnostics.full_diagnostics(F, T)
        vrr_solo = OrthogonalizationDiagnostics.compute_vrr(F, T)
        kappa_solo = OrthogonalizationDiagnostics.compute_condition_number(F)
        vif_solo = OrthogonalizationDiagnostics.compute_vif(F)
        orth_err_solo = OrthogonalizationDiagnostics.compute_orthogonality_error(T)

        np.testing.assert_allclose(diag['vrr'], vrr_solo, atol=1e-12)
        np.testing.assert_allclose(diag['condition_number'], kappa_solo, atol=1e-12)
        np.testing.assert_allclose(diag['vif'], vif_solo, atol=1e-12)
        np.testing.assert_allclose(diag['orthogonality_error'], orth_err_solo, atol=1e-12)

    def test_redundant_factors_indices_correct(self):
        """5.3 redundant_factors 索引与 VRR < 0.3 一致"""
        F = _redundant_F(N=200)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        diag = OrthogonalizationDiagnostics.full_diagnostics(F, T)

        vrr = diag['vrr']
        expected_redundant = np.where(vrr < 0.3)[0].tolist()
        assert diag['redundant_factors'] == expected_redundant, \
            f"redundant_factors={diag['redundant_factors']} vs expected={expected_redundant}"
        # 冗余因子 (索引 1) 必须在列表中
        assert 1 in diag['redundant_factors']

    def test_multicollinear_factors_indices_correct(self):
        """5.4 multicollinear_factors 索引与 VIF > 5 一致"""
        F = _collinear_F(N=300, K=4, rho=0.95)
        diag = OrthogonalizationDiagnostics.full_diagnostics(F, F)

        vif = diag['vif']
        expected_mc = np.where(vif > 5)[0].tolist()
        assert diag['multicollinear_factors'] == expected_mc, \
            f"multicollinear_factors={diag['multicollinear_factors']} vs expected={expected_mc}"
        # 共线因子应至少有一个被识别
        assert len(diag['multicollinear_factors']) > 0

    def test_json_serialization_roundtrip(self):
        """5.5 JSON 序列化-反序列化往返一致 (inf → null)"""
        rng = np.random.default_rng(42)
        f1 = rng.standard_normal(100)
        f2 = 2.0 * f1  # 完美共线 → VIF = inf
        f3 = rng.standard_normal(100)
        F = np.column_stack([f1, f2, f3])
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)

        json_str = OrthogonalizationDiagnostics.full_diagnostics_json(F, T)
        # 必须是合法 JSON
        parsed = json.loads(json_str)

        # inf → null
        assert any(v is None for v in parsed['vif']), \
            f"inf VIF 应转为 null: {parsed['vif']}"

        # 字段完整性
        expected_keys = {
            'vrr', 'condition_number', 'vif',
            'orthogonality_error', 'redundant_factors', 'multicollinear_factors'
        }
        assert set(parsed.keys()) == expected_keys

    def test_json_no_inf_nan_strings(self):
        """5.6 JSON 字符串中不出现 Infinity/NaN 字面量 (ECMAScript 兼容)"""
        rng = np.random.default_rng(42)
        f1 = rng.standard_normal(100)
        f2 = 2.0 * f1  # 完美共线
        F = np.column_stack([f1, f2])
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)

        json_str = OrthogonalizationDiagnostics.full_diagnostics_json(F, T)
        # 标准 JSON 不允许 Infinity/NaN 字面量
        assert 'Infinity' not in json_str, f"JSON 含 Infinity 字面量: {json_str}"
        assert 'NaN' not in json_str, f"JSON 含 NaN 字面量: {json_str}"


# =============================================================================
# 主入口
# =============================================================================

if __name__ == '__main__':
    # 独立运行: python -m factor_pipeline.tests.manual.test_diagnostics_manual
    import sys
    sys.exit(pytest.main([__file__, '-v', '--tb=short']))
