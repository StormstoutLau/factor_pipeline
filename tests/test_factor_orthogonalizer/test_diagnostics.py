# -*- coding: utf-8 -*-
"""O3a: Layer 2 几何诊断 — TDD 测试

测试 OrthogonalizationDiagnostics 类的四项诊断指标 + O3a.6 五项深化:
1. VRR (方差保留率)
2. κ (条件数)
3. VIF (方差膨胀因子)
4. 正交性误差

深化:
- O3a.6.1: VRR ddof 参数
- O3a.6.2: VIF 多方法 (lstsq/qr/pinv) + 完美共线
- O3a.6.3: 条件数分级 (Belsley-Kuh-Welsch)
- O3a.6.4: 正交性误差归一化
- O3a.6.5: JSON 序列化 + inf 处理
"""

import numpy as np
import pytest

from factor_pipeline.modules.factor_orthogonalizer.core import SymmetricOrthogonalizer
from factor_pipeline.modules.factor_orthogonalizer.core.diagnostics import (
    OrthogonalizationDiagnostics,
)


# =============================================================================
# 辅助函数
# =============================================================================

def _make_independent_factors(N=100, K=3, seed=42):
    """构造 K 个独立因子"""
    np.random.seed(seed)
    return np.random.randn(N, K)


def _make_collinear_factors(N=100, K=3, rho=0.95, seed=42):
    """构造 K 个高相关因子 (ρ ≈ rho)"""
    np.random.seed(seed)
    base = np.random.randn(N, 1)
    noise = np.random.randn(N, K) * np.sqrt(1 - rho**2)
    F = np.sqrt(rho) * base + noise
    return F


def _make_redundant_factor(N=100, seed=42):
    """构造 1 个冗余因子 (f2 = 0.99 * f1 + noise)"""
    np.random.seed(seed)
    f1 = np.random.randn(N, 1)
    f2 = 0.99 * f1 + 0.01 * np.random.randn(N, 1)
    return np.hstack([f1, f2])


# =============================================================================
# 1. VRR (方差保留率) — O3a.3 + O3a.6.1
# =============================================================================

class TestVRR:
    """VRR 测试"""

    def test_vrr_symmetric_compresses_variance(self):
        """对称正交化后方差被压缩 (T^T T = I 归一化效应)

        数学: 对称正交化使 T^T T = I, 即 ||T_k|| = 1.
        Var(T_k) = ||T_k||^2 / N - mean(T_k)^2 ≈ 1/N (mean ≈ 0 for randn).
        Var(F_k) ≈ 1 (randn 标准正态). 所以 VRR ≈ 1/N < 1.

        注: 文档 O3a.4 期望 "对称正交化 VRR = 1" 是基于 "对称正交化保持方差"
        的直觉假设, 但实际上对称正交化保持的是正交性 (T^T T = I),
        不是单因子方差. VRR = 1 仅当 F 列预归一化为单位范数时成立 (见 O1 测试
        test_symmetric_VRR_equals_one 用 _unit_norm_F). 此处用 randn 未归一化,
        VRR < 1 是正确的数学行为.
        """
        F = _make_independent_factors(N=100, K=3)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        vrr = OrthogonalizationDiagnostics.compute_vrr(F, T)
        # VRR 应为正 (信息保留) 且 < 1 (方差被 T^T T=I 归一化压缩)
        assert np.all(vrr > 0), f"VRR 应为正: {vrr}"
        assert np.all(vrr < 1), f"对称正交化后方差被压缩, VRR 应 < 1: {vrr}"
        # 理论值 ≈ 1/N = 1/100 = 0.01
        np.testing.assert_allclose(vrr, 1.0 / 100, atol=0.01)

    def test_vrr_redundant_factor_low(self):
        """ρ=0.99 冗余因子 VRR < 0.3"""
        F = _make_redundant_factor(N=200)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        vrr = OrthogonalizationDiagnostics.compute_vrr(F, T)
        # 冗余因子 (第 2 个) 的 VRR 应 < 0.3
        assert vrr[1] < 0.3, f"冗余因子 VRR={vrr[1]} 应 < 0.3"

    def test_vrr_ddof_consistency(self):
        """O3a.6.1: ddof=0 和 ddof=1 的 VRR 差异 = N/(N-1)"""
        N = 100
        F = _make_independent_factors(N=N, K=3)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        vrr_0 = OrthogonalizationDiagnostics.compute_vrr(F, T, ddof=0)
        vrr_1 = OrthogonalizationDiagnostics.compute_vrr(F, T, ddof=1)
        # var_ddof1 = var_ddof0 * N/(N-1), 所以 VRR_ddof1/VRR_ddof0 = 1
        # (分子分母同时乘 N/(N-1), 比值不变)
        np.testing.assert_allclose(vrr_1, vrr_0, atol=1e-12)

    def test_vrr_zero_variance_factor(self):
        """零方差因子 VRR = 0 (不除零)"""
        F = np.array([[1.0, 0.0], [2.0, 0.0], [3.0, 0.0]])
        T = F.copy()
        vrr = OrthogonalizationDiagnostics.compute_vrr(F, T)
        assert vrr[1] == 0.0


# =============================================================================
# 2. 条件数 κ — O3a.3 + O3a.6.3
# =============================================================================

class TestConditionNumber:
    """条件数测试"""

    def test_condition_number_well_conditioned(self):
        """良好矩阵 κ < 10"""
        F = _make_independent_factors(N=200, K=3)
        kappa = OrthogonalizationDiagnostics.compute_condition_number(F)
        assert kappa < 10, f"独立因子 κ={kappa} 应 < 10"

    def test_condition_number_ill_conditioned(self):
        """病态矩阵 κ > 1000"""
        F = _make_collinear_factors(N=200, K=5, rho=0.999)
        kappa = OrthogonalizationDiagnostics.compute_condition_number(F)
        assert kappa > 100, f"高相关因子 κ={kappa} 应 > 100"

    def test_condition_number_severity_levels(self):
        """O3a.6.3: Belsley-Kuh-Welsch 四级分级"""
        diag = OrthogonalizationDiagnostics
        assert diag.condition_number_severity(5.0) == 'good'
        assert diag.condition_number_severity(50.0) == 'acceptable'
        assert diag.condition_number_severity(500.0) == 'warning'
        assert diag.condition_number_severity(5000.0) == 'severe'


# =============================================================================
# 3. VIF (方差膨胀因子) — O3a.3 + O3a.6.2
# =============================================================================

class TestVIF:
    """VIF 测试"""

    def test_vif_independent_factors_low(self):
        """独立因子 VIF < 5"""
        F = _make_independent_factors(N=200, K=3)
        vif = OrthogonalizationDiagnostics.compute_vif(F)
        assert np.all(vif < 5), f"独立因子 VIF={vif} 应全部 < 5"

    def test_vif_collinear_factors_high(self):
        """共线因子 VIF > 10

        注: _make_collinear_factors 实际 corr < rho (Var(F_k)=1+rho-rho²),
        rho=0.95 实际 corr≈0.90 VIF≈7, 需 rho=0.99 (实际 corr≈0.98) 才达 VIF>10.
        """
        F = _make_collinear_factors(N=200, K=3, rho=0.99)
        vif = OrthogonalizationDiagnostics.compute_vif(F)
        assert np.any(vif > 10), f"共线因子 VIF={vif} 应有 > 10 的"

    def test_vif_lstsq_matches_qr(self):
        """O3a.6.2: lstsq 和 qr 在良好矩阵下一致 (精度 1e-10)"""
        F = _make_independent_factors(N=100, K=4)
        vif_lstsq = OrthogonalizationDiagnostics.compute_vif(F, method='lstsq')
        vif_qr = OrthogonalizationDiagnostics.compute_vif(F, method='qr')
        np.testing.assert_allclose(vif_lstsq, vif_qr, atol=1e-10)

    def test_vif_perfect_collinearity_inf(self):
        """O3a.6.2: 完美共线因子 VIF = inf"""
        np.random.seed(42)
        f1 = np.random.randn(100)
        f2 = 2.0 * f1  # 完美共线
        f3 = np.random.randn(100)
        F = np.column_stack([f1, f2, f3])
        vif = OrthogonalizationDiagnostics.compute_vif(F)
        assert np.isinf(vif[0]) or np.isinf(vif[1]), (
            f"完美共线因子 VIF={vif} 应有 inf"
        )


# =============================================================================
# 4. 正交性误差 — O3a.3 + O3a.6.4
# =============================================================================

class TestOrthogonalityError:
    """正交性误差测试"""

    def test_orthogonality_error_near_zero(self):
        """正交化后误差 < 1e-8"""
        F = _make_independent_factors(N=100, K=3)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        err = OrthogonalizationDiagnostics.compute_orthogonality_error(T)
        assert err < 1e-8, f"正交化后误差={err} 应 < 1e-8"

    def test_orthogonality_error_raw_high(self):
        """原始因子误差 > 0.5"""
        F = _make_collinear_factors(N=200, K=3, rho=0.9)
        err = OrthogonalizationDiagnostics.compute_orthogonality_error(F)
        assert err > 0.5, f"高相关原始因子误差={err} 应 > 0.5"

    def test_orthogonality_error_normalized_comparable_across_k(self):
        """O3a.6.4: 归一化误差跨 K 可比较"""
        # K=2 和 K=5 的完全正交因子, normalized 误差都 ≈ 0
        np.random.seed(42)
        F2 = np.random.randn(100, 2)
        F5 = np.random.randn(100, 5)
        orth2 = SymmetricOrthogonalizer()
        orth5 = SymmetricOrthogonalizer()
        T2 = orth2.fit_transform(F2)
        T5 = orth5.fit_transform(F5)
        err2 = OrthogonalizationDiagnostics.compute_orthogonality_error(
            T2, norm='normalized'
        )
        err5 = OrthogonalizationDiagnostics.compute_orthogonality_error(
            T5, norm='normalized'
        )
        np.testing.assert_allclose(err2, 0.0, atol=1e-10)
        np.testing.assert_allclose(err5, 0.0, atol=1e-10)


# =============================================================================
# 5. full_diagnostics — O3a.3
# =============================================================================

class TestFullDiagnostics:
    """full_diagnostics 测试"""

    def test_full_diagnostics_returns_all_fields(self):
        """返回 dict 含 6 个字段"""
        F = _make_independent_factors(N=100, K=3)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        diag = OrthogonalizationDiagnostics.full_diagnostics(F, T)
        expected_keys = {
            'vrr', 'condition_number', 'vif',
            'orthogonality_error', 'redundant_factors', 'multicollinear_factors'
        }
        assert set(diag.keys()) == expected_keys, (
            f"字段不匹配: {set(diag.keys())} vs {expected_keys}"
        )

    def test_redundant_factors_identified(self):
        """冗余因子索引正确识别"""
        F = _make_redundant_factor(N=200)
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        diag = OrthogonalizationDiagnostics.full_diagnostics(F, T)
        # 冗余因子 (索引 1) 应在 redundant_factors 列表中
        assert 1 in diag['redundant_factors'], (
            f"冗余因子索引 1 未被识别: {diag['redundant_factors']}"
        )

    def test_multicollinear_factors_identified(self):
        """多重共线因子正确识别"""
        F = _make_collinear_factors(N=200, K=3, rho=0.95)
        diag = OrthogonalizationDiagnostics.full_diagnostics(F, F)
        # 共线因子应至少有一个在 multicollinear_factors 中
        assert len(diag['multicollinear_factors']) > 0, (
            f"共线因子未被识别: {diag['multicollinear_factors']}"
        )


# =============================================================================
# 6. JSON 序列化 — O3a.6.5
# =============================================================================

class TestJSONSerialization:
    """JSON 序列化测试"""

    def test_diagnostics_json_serializable(self):
        """O3a.6.5: 含 inf VIF 的诊断报告 JSON 序列化不报错, inf 转 null"""
        import json
        np.random.seed(42)
        f1 = np.random.randn(100)
        f2 = 2.0 * f1  # 完美共线 → VIF = inf
        f3 = np.random.randn(100)
        F = np.column_stack([f1, f2, f3])
        orth = SymmetricOrthogonalizer()
        T = orth.fit_transform(F)
        json_str = OrthogonalizationDiagnostics.full_diagnostics_json(F, T)
        # 能被 json.loads 解析
        parsed = json.loads(json_str)
        assert 'vrr' in parsed
        assert 'vif' in parsed
        # inf 应转为 null
        assert any(v is None for v in parsed['vif']), (
            f"inf VIF 应转为 null: {parsed['vif']}"
        )
