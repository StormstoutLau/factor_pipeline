# -*- coding: utf-8 -*-
"""V3.1.0 E6 — 估计层方法测试 (TDD Red 阶段).

四种内生性缓解估计器 + 方法选择器, 全部 opt-in, 默认关闭.

v1.3 术语严格:
- Profile GMM (Hong-Su-Jiang 2022, 正式术语; NNR+GMM 为别名)
- IVX 指数衰减滤波 (非分数差分), z_t = Σ α^{j+1} x_{t-j}
- PFGMM (Ghosh-Thoresen 2019, 处理 error-covariate 内生, 非弱 IV)
- 因子增强 IVX 暂不使用

方法优先级 (§5.10.5): 三层正则化 > Profile GMM > IVX > DOLS > PFGMM
"""
import pytest
import numpy as np
import pandas as pd

from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2, PipelineV2Config


# ============================================================
# 测试数据生成
# ============================================================

def _make_factor_returns(n_t=80, n_n=50, seed=0, beta=0.5, noise=0.3):
    """生成 (T, N) 因子与收益, beta 为真实因子效应."""
    rng = np.random.default_rng(seed)
    f = rng.standard_normal((n_t, n_n))
    r = beta * f + noise * rng.standard_normal((n_t, n_n))
    return pd.DataFrame(f), pd.DataFrame(r)


def _make_persistent_factor_returns(n_t=100, n_n=30, seed=42, rho=0.95, beta=0.3):
    """生成持久因子 (AR(1) ρ≈0.95) + 收益 (预测回归场景)."""
    rng = np.random.default_rng(seed)
    # 持久因子: x_t = ρ x_{t-1} + u_t
    x = np.zeros((n_t, n_n))
    for t in range(1, n_t):
        x[t] = rho * x[t-1] + rng.standard_normal(n_n) * 0.1
    # 预测回归: y_{t+1} = α + β x_t + ε_{t+1}, 内生性: Cov(x_t, ε_{t+1}) ≠ 0
    eps = rng.standard_normal(n_t) * 0.1
    # 制造内生性: eps 与 x 相关
    eps = eps + 0.3 * x[:, 0]
    y = np.zeros((n_t, n_n))
    for t in range(1, n_t):
        y[t] = beta * x[t-1] + eps[t]
    return pd.DataFrame(x), pd.DataFrame(y)


# ============================================================
# 抽象基类 (E6-T01)
# ============================================================

class TestBaseEstimator:
    """BaseEndogeneityEstimator 抽象基类接口."""

    def test_E6_T01_base_estimator_interface(self):
        """E6-T01: 抽象基类 fit/get_diagnostics 接口."""
        from factor_pipeline.modules.endogeneity_estimators.core.base import (
            BaseEndogeneityEstimator,
        )
        # 是抽象基类
        assert hasattr(BaseEndogeneityEstimator, 'fit')
        assert hasattr(BaseEndogeneityEstimator, 'get_diagnostics')
        assert hasattr(BaseEndogeneityEstimator, 'get_residual_threat')
        # 不能直接实例化 (抽象方法)
        with pytest.raises(TypeError):
            BaseEndogeneityEstimator()


# ============================================================
# Profile GMM (E6-T02 ~ T05)
# ============================================================

class TestProfileGMMEstimator:
    """Profile GMM 估计器 (Hong-Su-Jiang 2022, NNR+GMM 融合)."""

    def test_E6_T02_profile_gmm_formal_name(self):
        """E6-T02: 正式术语 'Profile GMM' (v1.3, 非 'NNR+GMM' 为正式)."""
        from factor_pipeline.modules.endogeneity_estimators.core.profile_gmm import (
            ProfileGMMEstimator,
        )
        est = ProfileGMMEstimator()
        f, r = _make_factor_returns()
        est.fit(f, r)
        diag = est.get_diagnostics()
        # 正式术语
        assert 'Profile GMM' in diag['method_formal_name']
        assert diag['method'] == 'profile_gmm'
        # NNR+GMM 为别名 (非正式)
        assert diag.get('method_alias') == 'NNR+GMM'

    def test_E6_T03_profile_gmm_nuclear_norm(self):
        """E6-T03: 核范数正则化 (NNR) 吸收共性结构."""
        from factor_pipeline.modules.endogeneity_estimators.core.profile_gmm import (
            ProfileGMMEstimator,
        )
        est = ProfileGMMEstimator(nuclear_lambda=0.5)
        f, r = _make_factor_returns()
        est.fit(f, r)
        diag = est.get_diagnostics()
        # 软阈值后奇异值应小于原始值 (吸收了共性结构)
        s_orig = np.asarray(diag['singular_values_original'])
        s_soft = np.asarray(diag['singular_values_soft'])
        # 至少有一个奇异值被软阈值缩减
        assert np.any(s_soft < s_orig)
        # absorption_ratio ∈ [0, 1]
        assert 0.0 <= diag['absorption_ratio'] <= 1.0

    def test_E6_T04_profile_gmm_lambda_sensitivity(self):
        """E6-T04: λ 大 → 吸收多, λ 小 → 接近标准 GMM."""
        from factor_pipeline.modules.endogeneity_estimators.core.profile_gmm import (
            ProfileGMMEstimator,
        )
        f, r = _make_factor_returns()
        # 大 λ → 高吸收
        est_high = ProfileGMMEstimator(nuclear_lambda=1.0)
        est_high.fit(f, r)
        # 小 λ → 低吸收
        est_low = ProfileGMMEstimator(nuclear_lambda=0.001)
        est_low.fit(f, r)
        absorption_high = est_high.get_diagnostics()['absorption_ratio']
        absorption_low = est_low.get_diagnostics()['absorption_ratio']
        assert absorption_high >= absorption_low

    def test_E6_T05_profile_gmm_residual_threat(self):
        """E6-T05: 残留威胁 τ ∈ [0, 1]."""
        from factor_pipeline.modules.endogeneity_estimators.core.profile_gmm import (
            ProfileGMMEstimator,
        )
        est = ProfileGMMEstimator()
        f, r = _make_factor_returns()
        est.fit(f, r)
        tau = est.get_residual_threat()
        assert 0.0 <= tau <= 1.0
        assert est.get_diagnostics()['residual_threat_tau'] == tau


# ============================================================
# IVX 指数衰减滤波 (E6-T06 ~ T10)
# ============================================================

class TestIVXEstimator:
    """IVX 估计器 (Kostakis 2015, 指数衰减滤波)."""

    def test_E6_T06_ivx_exponential_filtering_not_fractional(self):
        """E6-T06: 指数衰减滤波 (v1.3: 非分数差分).

        z_t = Σ_{j=0}^{t-1} α^{j+1} × x_{t-j}, α^j 几何衰减.
        """
        from factor_pipeline.modules.endogeneity_estimators.core.ivx import IVXEstimator
        est = IVXEstimator(alpha=0.5)
        f, r = _make_persistent_factor_returns()
        est.fit(f, r)
        diag = est.get_diagnostics()
        # 明确标记为 exponential_filtering (非 fractional_differencing)
        assert diag['filtering_type'] == 'exponential_filtering'
        assert diag['filtering_type'] != 'fractional_differencing'

    def test_E6_T07_ivx_alpha_decay_rate(self):
        """E6-T07: α ∈ (0, 1), z_t = Σ α^{j+1} x_{t-j}."""
        from factor_pipeline.modules.endogeneity_estimators.core.ivx import IVXEstimator
        est = IVXEstimator(alpha=0.3)
        f, r = _make_persistent_factor_returns()
        est.fit(f, r)
        diag = est.get_diagnostics()
        # α ∈ (0, 1)
        assert 0.0 < diag['alpha_decay_rate'] < 1.0

    def test_E6_T08_ivx_persistence_handling(self):
        """E6-T08: ρ > 0.9 → IVX 适用 (持久因子场景)."""
        from factor_pipeline.modules.endogeneity_estimators.core.ivx import IVXEstimator
        est = IVXEstimator()
        # 持久因子 ρ ≈ 0.95
        f, r = _make_persistent_factor_returns(rho=0.95)
        est.fit(f, r)
        diag = est.get_diagnostics()
        # ρ 应较高 (持久)
        assert diag['rho_persistence'] > 0.9
        # IVX 估计成功 (beta 非 NaN)
        assert not np.isnan(diag['beta'])

    def test_E6_T09_ivx_factor_augmented_not_used(self):
        """E6-T09: factor_augmented_ivx_used=False (v1.3: 暂不使用)."""
        from factor_pipeline.modules.endogeneity_estimators.core.ivx import IVXEstimator
        est = IVXEstimator()
        f, r = _make_factor_returns()
        est.fit(f, r)
        diag = est.get_diagnostics()
        assert diag['factor_augmented_ivx_used'] is False

    def test_E6_T10_ivx_bias_reduction(self):
        """E6-T10: IVX β vs OLS β 偏倚减少.

        IVX 通过指数滤波构造工具变量, 减少内生性偏倚.
        """
        from factor_pipeline.modules.endogeneity_estimators.core.ivx import IVXEstimator
        est = IVXEstimator()
        f, r = _make_persistent_factor_returns()
        est.fit(f, r)
        diag = est.get_diagnostics()
        # bias_reduction 字段存在且为非负
        assert 'bias_reduction' in diag
        assert diag['bias_reduction'] >= 0.0

    def test_E6_T10b_ivx_adaptive_alpha_based_on_T(self):
        """E6-T10b: 自适应 α 基于 T (Kostakis 2015 原始公式 α = 1 - c/T^δ).

        v1.3 严格对齐论文: α 应随 T 增大趋近 1 (温和持久).
        非基于 ρ 的启发式 (已废弃).
        """
        from factor_pipeline.modules.endogeneity_estimators.core.ivx import IVXEstimator
        # T=100, c=5.0, δ=0.95 → α = 1 - 5/100^0.95 ≈ 1 - 5/79.43 ≈ 0.937
        est = IVXEstimator()  # 默认 c=5.0, delta=0.95, alpha=None (自适应)
        f, r = _make_persistent_factor_returns(n_t=100)
        est.fit(f, r)
        diag = est.get_diagnostics()
        alpha_used = diag['alpha_decay_rate']
        # 验证 α ≈ 0.937 (容忍浮点误差)
        expected_alpha = 1.0 - 5.0 / (100 ** 0.95)
        assert abs(alpha_used - expected_alpha) < 1e-6, (
            f"α={alpha_used}, 期望={expected_alpha} (1 - 5/100^0.95)"
        )
        # α 应在 (0.9, 1.0) 区间 (T=100 温和滤波)
        assert 0.9 < alpha_used < 1.0
        # 诊断字段 c/delta 暴露
        assert diag['alpha_c_constant'] == 5.0
        assert diag['alpha_delta_exponent'] == 0.95
        # T 更大 → α 更接近 1 (单调性)
        f_large, r_large = _make_persistent_factor_returns(n_t=500)
        est_large = IVXEstimator()
        est_large.fit(f_large, r_large)
        alpha_large = est_large.get_diagnostics()['alpha_decay_rate']
        assert alpha_large > alpha_used, (
            f"T=500 α={alpha_large} 应 > T=100 α={alpha_used} (T 大 → α 更接近 1)"
        )


# ============================================================
# Regularized DOLS (E6-T11 ~ T14)
# ============================================================

class TestRegularizedDOLSEstimator:
    """正则化 DOLS 估计器 (Stock-Watson 1993)."""

    def test_E6_T11_dols_cointegration_required(self):
        """E6-T11: 无协整 → 警告 + 不适用 (DOLS 无意义)."""
        from factor_pipeline.modules.endogeneity_estimators.core.regularized_dols import (
            RegularizedDOLSEstimator,
        )
        est = RegularizedDOLSEstimator()
        # I(0) 数据, 无协整
        rng = np.random.default_rng(0)
        f = pd.DataFrame(rng.standard_normal((80, 30)))
        r = pd.DataFrame(rng.standard_normal((80, 30)))
        est.fit(f, r)
        diag = est.get_diagnostics()
        # 无协整 → 警告 + tau 较高
        if not diag['is_cointegrated']:
            assert diag['warning'] != ''
            assert diag['residual_threat_tau'] > 0.5

    def test_E6_T12_dols_lag_terms(self):
        """E6-T12: 领先/滞后差分项构造正确 (lead-lag 项)."""
        from factor_pipeline.modules.endogeneity_estimators.core.regularized_dols import (
            RegularizedDOLSEstimator,
        )
        est = RegularizedDOLSEstimator(lag_order=3)
        f, r = _make_factor_returns()
        est.fit(f, r)
        diag = est.get_diagnostics()
        assert diag['lag_order'] == 3
        # gamma_lag_coefficients 应为 2*lag_order 个 (j=-p..p, j≠0)
        # 但若不协整可能为空, 此处仅检查字段存在
        assert 'gamma_lag_coefficients' in diag

    def test_E6_T13_dols_elastic_net(self):
        """E6-T13: L1/L2 正则化生效 (Elastic Net)."""
        from factor_pipeline.modules.endogeneity_estimators.core.regularized_dols import (
            RegularizedDOLSEstimator,
        )
        # 启用 L1/L2
        est = RegularizedDOLSEstimator(lag_order=2, lambda_l1=0.1, lambda_l2=0.1)
        f, r = _make_factor_returns()
        est.fit(f, r)
        diag = est.get_diagnostics()
        assert diag['lambda_l1'] == 0.1
        assert diag['lambda_l2'] == 0.1

    def test_E6_T14_dols_r_squared(self):
        """E6-T14: R² 计算正确 (若协整)."""
        from factor_pipeline.modules.endogeneity_estimators.core.regularized_dols import (
            RegularizedDOLSEstimator,
        )
        est = RegularizedDOLSEstimator(lag_order=2)
        f, r = _make_factor_returns()
        est.fit(f, r)
        diag = est.get_diagnostics()
        # 若协整, R² 应存在且 ∈ [0, 1]
        if diag['is_cointegrated']:
            assert 0.0 <= diag['r_squared'] <= 1.0
        else:
            # 无协整时 R² 可能为 NaN
            assert 'r_squared' in diag


# ============================================================
# PFGMM (E6-T15 ~ T19)
# ============================================================

class TestPFGMMEstimator:
    """PFGMM 估计器 (Ghosh-Thoresen 2019, Profiled Focused GMM)."""

    def test_E6_T15_pfgmm_formal_name(self):
        """E6-T15: 正式术语 'PFGMM (Ghosh-Thoresen 2019)'."""
        from factor_pipeline.modules.endogeneity_estimators.core.pfgmm import (
            PFGMMEstimator,
        )
        est = PFGMMEstimator()
        f, r = _make_factor_returns()
        est.fit(f, r)
        diag = est.get_diagnostics()
        assert 'PFGMM' in diag['method_formal_name']
        assert 'Ghosh-Thoresen' in diag['method_formal_name']
        assert diag['method'] == 'pfgmm'

    def test_E6_T16_pfgmm_a_stock_low_applicability(self):
        """E6-T16: A 股适用性低 (降级警告)."""
        from factor_pipeline.modules.endogeneity_estimators.core.pfgmm import (
            PFGMMEstimator,
        )
        est = PFGMMEstimator()
        f, r = _make_factor_returns()
        est.fit(f, r)
        diag = est.get_diagnostics()
        # A 股适用性低
        assert diag['a_stock_applicability'] == 'low'
        assert diag['applicability_warning'] != ''

    def test_E6_T17_pfgmm_scad_penalty(self):
        """E6-T17: SCAD 非凹惩罚 (多维场景启用)."""
        from factor_pipeline.modules.endogeneity_estimators.core.pfgmm import (
            PFGMMEstimator,
        )
        # 多维场景: n_instruments > sparse_dim_threshold (默认 10)
        est = PFGMMEstimator(penalty='scad', lambda_penalty=0.1, sparse_dim_threshold=5)
        # 50 列 > 5 → 启用 SCAD
        f, r = _make_factor_returns(n_n=50)
        est.fit(f, r)
        diag = est.get_diagnostics()
        assert diag['sparse_penalty_active'] is True
        assert 'scad' in diag['penalty'].lower() or diag['penalty'] == 'scad'

    def test_E6_T18_pfgmm_mcp_penalty(self):
        """E6-T18: MCP 非凹惩罚 (多维场景启用)."""
        from factor_pipeline.modules.endogeneity_estimators.core.pfgmm import (
            PFGMMEstimator,
        )
        est = PFGMMEstimator(penalty='mcp', lambda_penalty=0.1, sparse_dim_threshold=5)
        f, r = _make_factor_returns(n_n=50)
        est.fit(f, r)
        diag = est.get_diagnostics()
        assert diag['sparse_penalty_active'] is True
        assert 'mcp' in diag['penalty'].lower() or diag['penalty'] == 'mcp'

    def test_E6_T19_pfgmm_error_covariate_not_weak_iv(self):
        """E6-T19: 处理 error-covariate 内生 (非弱 IV, v1.3).

        PFGMM 处理 error-covariate endogeneity (Corr(X, ε)≠0),
        非"弱工具变量"场景.
        """
        from factor_pipeline.modules.endogeneity_estimators.core.pfgmm import (
            PFGMMEstimator,
        )
        est = PFGMMEstimator()
        f, r = _make_factor_returns()
        est.fit(f, r)
        diag = est.get_diagnostics()
        # 残留威胁 τ ∈ [0, 1]
        tau = est.get_residual_threat()
        assert 0.0 <= tau <= 1.0
        # PFGMM 不声称消除内生性, 仅吸收部分
        assert 'residual_threat_tau' in diag


# ============================================================
# 方法选择器 (E6-T20 ~ T23)
# ============================================================

class TestEndogeneityMethodSelector:
    """估计方法选择器 (§5.10.6 场景矩阵)."""

    def test_E6_T20_method_selector_low_rank(self):
        """E6-T20: 低秩 → 推荐 Profile GMM (共性结构主导)."""
        from factor_pipeline.modules.endogeneity_estimators.core.method_selector import (
            EndogeneityMethodSelector,
        )
        selector = EndogeneityMethodSelector()
        # 低秩数据: 单一因子驱动
        rng = np.random.default_rng(0)
        common = rng.standard_normal((80, 1))
        f = pd.DataFrame(np.tile(common, (1, 30)) + 0.01 * rng.standard_normal((80, 30)))
        r, _ = _make_factor_returns()
        report = {'final_threat_tau': 0.5}
        result = selector.select(report, factor_data=f)
        assert result['recommended_method'] == 'profile_gmm'
        assert 'Profile GMM' in result['reason'] or '低秩' in result['reason']

    def test_E6_T21_method_selector_persistent(self):
        """E6-T21: ρ > 0.9 → 推荐 IVX (持久因子)."""
        from factor_pipeline.modules.endogeneity_estimators.core.method_selector import (
            EndogeneityMethodSelector,
        )
        selector = EndogeneityMethodSelector(rho_threshold=0.9)
        # 持久因子 ρ ≈ 0.95
        f, _ = _make_persistent_factor_returns(rho=0.95)
        report = {'final_threat_tau': 0.5}
        result = selector.select(report, factor_data=f)
        assert result['recommended_method'] == 'ivx'
        assert 'IVX' in result['reason'] or '持久' in result['reason']

    def test_E6_T22_method_selector_low_threat(self):
        """E6-T22: τ < 0.3 → 推荐 none (仅三层正则化)."""
        from factor_pipeline.modules.endogeneity_estimators.core.method_selector import (
            EndogeneityMethodSelector,
        )
        selector = EndogeneityMethodSelector()
        report = {'final_threat_tau': 0.1}
        result = selector.select(report, factor_data=None)
        assert result['recommended_method'] == 'none'
        assert result['should_chain_with_regularization'] is True

    def test_E6_T23_method_selector_default(self):
        """E6-T23: 默认推荐 Profile GMM (通用性最强)."""
        from factor_pipeline.modules.endogeneity_estimators.core.method_selector import (
            EndogeneityMethodSelector,
        )
        selector = EndogeneityMethodSelector()
        # 中威胁, 无低秩, 无持久 → 默认 Profile GMM
        rng = np.random.default_rng(0)
        f = pd.DataFrame(rng.standard_normal((80, 30)))
        report = {'final_threat_tau': 0.5}
        result = selector.select(report, factor_data=f)
        assert result['recommended_method'] == 'profile_gmm'

    def test_E6_T20b_low_rank_priority_over_persistence(self):
        """E6-T20b: 低秩 + 持久 → 仍推荐 Profile GMM (低秩优先于 IVX, §5.10.6 顺序)."""
        from factor_pipeline.modules.endogeneity_estimators.core.method_selector import (
            EstimationMethodSelector,
        )
        selector = EstimationMethodSelector(rho_threshold=0.9)
        # 低秩 + 持久: 单因子 AR(1) 复制 30 列
        rng = np.random.default_rng(0)
        n_t, n_n = 100, 30
        x = np.zeros(n_t)
        for t in range(1, n_t):
            x[t] = 0.95 * x[t-1] + rng.standard_normal() * 0.1
        f = pd.DataFrame(np.tile(x[:, None], (1, n_n)) + 0.01 * rng.standard_normal((n_t, n_n)))
        report = {'final_threat_tau': 0.5}
        result = selector.select(report, factor_data=f)
        # 低秩优先 → profile_gmm (即使 ρ > 0.9)
        assert result['recommended_method'] == 'profile_gmm'
        assert result['is_low_rank'] is True
        # all_methods_ranked 字段存在且顺序正确 (§5.10.5)
        assert result['all_methods_ranked'] == ['profile_gmm', 'ivx', 'dols', 'pfgmm']

    def test_E6_T20c_all_methods_ranked_and_frobenius(self):
        """E6-T20c: all_methods_ranked 字段 + Frobenius 低秩公式验证."""
        from factor_pipeline.modules.endogeneity_estimators.core.method_selector import (
            EstimationMethodSelector,
        )
        selector = EstimationMethodSelector(low_rank_threshold=0.8)
        # 低秩数据: 第一奇异值主导
        rng = np.random.default_rng(0)
        common = rng.standard_normal((80, 1))
        f = pd.DataFrame(np.tile(common, (1, 30)) + 0.01 * rng.standard_normal((80, 30)))
        report = {'final_threat_tau': 0.5}
        result = selector.select(report, factor_data=f)
        # all_methods_ranked 必须存在
        assert 'all_methods_ranked' in result
        assert result['all_methods_ranked'] == ['profile_gmm', 'ivx', 'dols', 'pfgmm']
        # Frobenius 公式: s[0]²/Σs² 应 > 0.8 (单因子主导, 能量集中)
        assert result['is_low_rank'] is True
        # 验证 Frobenius 公式 (非核范数): 手工计算
        X = f.values.astype(float)
        X_c = X - X.mean(axis=0)
        s = np.linalg.svd(X_c, compute_uv=False)
        frob_ratio = float(s[0] ** 2) / float(np.sum(s ** 2))
        nuclear_ratio = float(s[0]) / float(np.sum(s))
        # Frobenius 比 > 核范数比 (平方放大主导奇异值)
        assert frob_ratio > nuclear_ratio
        assert frob_ratio > 0.8

    def test_E6_T20d_endogeneity_report_parameter_name(self):
        """E6-T20d: 参数名 endogeneity_report (spec 对齐, 位置参数兼容)."""
        from factor_pipeline.modules.endogeneity_estimators.core.method_selector import (
            EstimationMethodSelector,
        )
        selector = EstimationMethodSelector()
        report = {'final_threat_tau': 0.1}
        # 位置参数调用 (向后兼容)
        result1 = selector.select(report, factor_data=None)
        assert result1['recommended_method'] == 'none'
        # 关键字参数调用 (spec 对齐)
        result2 = selector.select(endogeneity_report=report, factor_data=None)
        assert result2['recommended_method'] == 'none'
        assert result1 == result2


# ============================================================
# Pipeline 集成 (E6-T24 ~ T26)
# ============================================================

class TestPipelineIntegration:
    """PipelineV2 集成: opt-in 默认关闭."""

    def test_E6_T24_pipeline_estimate_disabled(self):
        """E6-T24: enable_endogeneity_estimators=False → 返回 None."""
        config = PipelineV2Config()  # 默认 enable=False
        assert config.enable_endogeneity_estimators is False
        pipeline = FactorProcessingPipelineV2(config)
        f, r = _make_factor_returns()
        result = pipeline.estimate_with_endogeneity_mitigation(f, r)
        assert result is None

    def test_E6_T25_pipeline_estimate_enabled(self):
        """E6-T25: enable=True → 返回估计结果."""
        config = PipelineV2Config()
        config.enable_endogeneity_estimators = True
        config.enable_profile_gmm = True
        pipeline = FactorProcessingPipelineV2(config)
        f, r = _make_factor_returns()
        result = pipeline.estimate_with_endogeneity_mitigation(f, r)
        assert result is not None
        assert 'method' in result
        assert 'beta' in result

    def test_E6_T26_chain_with_e5_regularization(self):
        """E6-T26: E6 + E5 串联: 先估计后正则化.

        E6 估计器输出的 residual_threat_tau 可作为 E5 的 threat_assessment 输入.
        """
        from factor_pipeline.modules.endogeneity_estimators.core.profile_gmm import (
            ProfileGMMEstimator,
        )
        from factor_pipeline.modules.endogeneity_regularizer import EndogeneityRegularizer
        # Step 1: E6 估计
        est = ProfileGMMEstimator()
        f, r = _make_factor_returns()
        est.fit(f, r)
        residual_tau = est.get_residual_threat()
        # Step 2: E5 基于 residual_tau 正则化
        threat_assessment = {'final_threat_tau': residual_tau}
        reg = EndogeneityRegularizer(threat_assessment=threat_assessment)
        l3_config = reg.apply_l3_optimizer_config(residual_tau, w_raw=1.0)
        assert 'w_final' in l3_config
        assert l3_config['w_final'] <= 1.0  # 有惩罚


# ============================================================
# 鲁棒性 + 向后兼容 (E6-T27, T28)
# ============================================================

class TestRobustnessAndBackwardCompat:
    """鲁棒性 + 向后兼容."""

    def test_E6_T27_nan_handling(self):
        """E6-T27: 含 NaN 数据不崩溃."""
        from factor_pipeline.modules.endogeneity_estimators.core.profile_gmm import (
            ProfileGMMEstimator,
        )
        est = ProfileGMMEstimator()
        f, r = _make_factor_returns()
        # 注入 NaN
        f.iloc[0, 0] = np.nan
        f.iloc[5, 3] = np.nan
        est.fit(f, r)
        diag = est.get_diagnostics()
        # 不崩溃, beta 为有限数或 NaN (但接口正常返回)
        assert 'beta' in diag

    def test_E6_T28_backward_compat_v3_0_0(self):
        """E6-T28: 不开启时 v3.0.0 测试全通过 (新字段默认 False)."""
        config = PipelineV2Config()
        # E6 新增字段默认值
        assert config.enable_endogeneity_estimators is False
        assert config.estimator_method == 'auto'
        assert config.enable_profile_gmm is False
        assert config.enable_ivx is False
        assert config.enable_regularized_dols is False
        assert config.enable_pfgmm is False
        # 不开启时实例化正常
        pipeline = FactorProcessingPipelineV2(config)
        assert pipeline is not None
