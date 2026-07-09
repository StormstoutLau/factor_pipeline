# -*- coding: utf-8 -*-
"""V3.1.0 E5 — 三层决策正则化测试 (TDD Red 阶段).

硬依赖 E3: EndogeneityRegularizer 接收 E3 的 final_threat_assessment,
基于 final_threat_tau ∈ [0,1] 协调三层正则化:
  L1 预处理层: 调整 DualNeutralizer 中性化强度 (低威胁跳过 Stage 2, 高威胁加额外 β' 检查)
  L2 检验层:   调整 factor_significance 显著性阈值 α (高威胁更严格)
  L3 组合层:   调整 optimizer 因子权重惩罚 (高威胁权重惩罚)

向后兼容:
- DualNeutralizer: threat_level=None, skip_stage2=False → v3.0.0 行为
- optimizer: lambda_endogeneity=0.0 → 惩罚=0, 目标函数与 v2.6.0 一致
- factor_significance: 新方法不替换 double_lasso, 仅 opt-in
"""
import pytest
import numpy as np
import pandas as pd

from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2, PipelineV2Config


# ============================================================
# 测试数据生成
# ============================================================

def _make_factor_panel(n_t=60, n_n=50, seed=0):
    """生成 (T, N) 因子面板."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.standard_normal((n_t, n_n)))


def _make_threat_assessment(tau=0.5, mechanism='MCAR'):
    """构造 E3 final_threat_assessment dict."""
    return {
        'final_threat_tau': float(tau),
        'component_taus': {'oster_delta': float(tau)},
        's1_mechanism': mechanism,
        'recommended_regularization': 'mild' if 0.3 <= tau < 0.7 else (
            'strong' if tau >= 0.7 else 'none'
        ),
    }


# ============================================================
# L1 预处理层: CompositeDecoupler/DualNeutralizer 扩展 (E5-T01 ~ T03, T15)
# ============================================================

class TestL1NeutralizerRegularization:
    """L1 预处理层: 根据 τ 调整中性化强度."""

    def test_E5_T01_l1_low_threat_skip_stage2(self):
        """E5-T01: τ<0.3 → 跳过 Stage 2 (低威胁轻量路径)."""
        from factor_pipeline.modules.endogeneity_regularizer import EndogeneityRegularizer
        reg = EndogeneityRegularizer()
        tau = 0.1  # 低威胁
        # 低威胁 → skip_stage2=True
        config = reg.apply_l1_neutralizer_config(tau)
        assert config['skip_stage2'] is True
        assert config['threat_level'] == 'low'

    def test_E5_T02_l1_medium_threat_full(self):
        """E5-T02: 0.3≤τ<0.7 → 标准三重中性化."""
        from factor_pipeline.modules.endogeneity_regularizer import EndogeneityRegularizer
        reg = EndogeneityRegularizer()
        tau = 0.5  # 中威胁
        config = reg.apply_l1_neutralizer_config(tau)
        assert config['skip_stage2'] is False
        assert config['threat_level'] == 'medium'

    def test_E5_T03_l1_high_threat_extra_check(self):
        """E5-T03: τ≥0.7 → 额外 β' 检查 (高威胁)."""
        from factor_pipeline.modules.endogeneity_regularizer import EndogeneityRegularizer
        reg = EndogeneityRegularizer()
        tau = 0.8  # 高威胁
        config = reg.apply_l1_neutralizer_config(tau)
        assert config['skip_stage2'] is False
        assert config['threat_level'] == 'high'
        assert config.get('extra_beta_check', False) is True

    def test_E5_T15_dual_neutralizer_backward_compat(self):
        """E5-T15: threat_level=None, skip_stage2=False → v3.0.0 行为.

        CompositeDecoupler.transform 默认参数下行为与 v3.0.0 完全一致.
        """
        from factor_pipeline.modules.factor_decoupler.core.dual_neutralizer import (
            CompositeDecoupler, DualNeutralizer,
        )
        # DualNeutralizer.transform 签名向后兼容
        import inspect
        sig = inspect.signature(DualNeutralizer.transform)
        assert 'threat_level' in sig.parameters
        assert 'skip_stage2' in sig.parameters
        # 默认值
        assert sig.parameters['threat_level'].default is None
        assert sig.parameters['skip_stage2'].default is False

        # CompositeDecoupler.transform 同样向后兼容
        sig_c = inspect.signature(CompositeDecoupler.transform)
        assert 'threat_level' in sig_c.parameters
        assert 'skip_stage2' in sig_c.parameters
        assert sig_c.parameters['threat_level'].default is None
        assert sig_c.parameters['skip_stage2'].default is False


# ============================================================
# L2 检验层: factor_significance 扩展 (E5-T04 ~ T08)
# ============================================================

class TestL2SignificanceRegularization:
    """L2 检验层: 根据 τ 调整显著性阈值 α."""

    def test_E5_T04_l2_alpha_adjustment(self):
        """E5-T04: α_i = α_base × (1 - γ × τ_i)."""
        from factor_pipeline.modules.endogeneity_regularizer import EndogeneityRegularizer
        reg = EndogeneityRegularizer(reg_gamma=0.5, alpha_base=0.05)
        tau = 0.5
        expected_alpha = 0.05 * (1.0 - 0.5 * 0.5)  # = 0.0375
        config = reg.apply_l2_significance_config(tau)
        assert abs(config['alpha_adjusted'] - expected_alpha) < 1e-10

    def test_E5_T05_l2_alpha_low_threat(self):
        """E5-T05: τ=0 → α=0.05 (无内生性, 标准阈值)."""
        from factor_pipeline.modules.endogeneity_regularizer import EndogeneityRegularizer
        reg = EndogeneityRegularizer(reg_gamma=0.5, alpha_base=0.05)
        config = reg.apply_l2_significance_config(0.0)
        assert abs(config['alpha_adjusted'] - 0.05) < 1e-10

    def test_E5_T06_l2_alpha_high_threat(self):
        """E5-T06: τ=1 → α=0.025 (高内生性, 严格阈值)."""
        from factor_pipeline.modules.endogeneity_regularizer import EndogeneityRegularizer
        reg = EndogeneityRegularizer(reg_gamma=0.5, alpha_base=0.05)
        config = reg.apply_l2_significance_config(1.0)
        # α = 0.05 × (1 - 0.5 × 1) = 0.025
        assert abs(config['alpha_adjusted'] - 0.025) < 1e-10

    def test_E5_T07_l2_threat_layered_bh_fdr(self):
        """E5-T07: 分层 BH-FDR 生效 (各威胁层独立校正)."""
        from backtest.factor_significance import FactorSignificanceTest
        fst = FactorSignificanceTest()
        # 三层各一个因子
        threat_taus = {'f_low': 0.1, 'f_mid': 0.5, 'f_high': 0.8}
        p_values = {'f_low': 0.01, 'f_mid': 0.02, 'f_high': 0.03}
        result = fst.threat_layered_bh_fdr(
            p_values, threat_taus, alpha_base=0.05, gamma=0.5,
        )
        # 三层各独立 BH-FDR (单因子层 p_adj = p 本身)
        assert 'f_low' in result
        assert 'f_mid' in result
        assert 'f_high' in result
        assert result['f_low']['layer'] == 'low'
        assert result['f_mid']['layer'] == 'medium'
        assert result['f_high']['layer'] == 'high'

    def test_E5_T08_l2_cross_layer_penalty(self):
        """E5-T08: 高威胁层 q-value 乘以惩罚因子 (1 - γ × τ_mean)."""
        from backtest.factor_significance import FactorSignificanceTest
        fst = FactorSignificanceTest()
        # 高威胁层: τ=0.8, γ=0.5 → penalty_factor = 1 - 0.5 × 0.8 = 0.6
        threat_taus = {'f_high': 0.8}
        p_values = {'f_high': 0.02}
        result = fst.threat_layered_bh_fdr(
            p_values, threat_taus, alpha_base=0.05, gamma=0.5,
        )
        # 单因子 BH-FDR: p_adj = 0.02 (单元素无累积 min 调整)
        # 跨层惩罚: 0.02 × 0.6 = 0.012
        expected_penalty = 1.0 - 0.5 * 0.8
        assert abs(result['f_high']['penalty_factor'] - expected_penalty) < 1e-10
        assert abs(result['f_high']['adjusted_p'] - 0.02 * expected_penalty) < 1e-10


# ============================================================
# L3 组合层: optimizer 权重惩罚 (E5-T09 ~ T13)
# ============================================================

class TestL3OptimizerPenalty:
    """L3 组合层: 根据 τ 调整因子权重."""

    def test_E5_T09_l3_weight_penalty(self):
        """E5-T09: w_final = w_raw × (1 - ρ × τ)."""
        from factor_pipeline.modules.endogeneity_regularizer import EndogeneityRegularizer
        reg = EndogeneityRegularizer(reg_strength_rho=0.3)
        tau = 0.5
        w_raw = 1.0
        expected_w = 1.0 * (1.0 - 0.3 * 0.5)  # = 0.85
        config = reg.apply_l3_optimizer_config(tau, w_raw)
        assert abs(config['w_final'] - expected_w) < 1e-10

    def test_E5_T10_l3_no_threat_no_penalty(self):
        """E5-T10: τ=0 → w_final = w_raw (无惩罚)."""
        from factor_pipeline.modules.endogeneity_regularizer import EndogeneityRegularizer
        reg = EndogeneityRegularizer(reg_strength_rho=0.3)
        config = reg.apply_l3_optimizer_config(0.0, 1.0)
        assert abs(config['w_final'] - 1.0) < 1e-10

    def test_E5_T11_l3_high_threat_30pct_penalty(self):
        """E5-T11: τ=1, ρ=0.3 → 30% 惩罚 (w_final = 0.7 × w_raw)."""
        from factor_pipeline.modules.endogeneity_regularizer import EndogeneityRegularizer
        reg = EndogeneityRegularizer(reg_strength_rho=0.3)
        config = reg.apply_l3_optimizer_config(1.0, 1.0)
        assert abs(config['w_final'] - 0.7) < 1e-10

    def test_E5_T12_optimizer_endogeneity_penalty(self):
        """E5-T12: optimizer _endogeneity_penalty 生效.

        penalty = λ × Σ |w_i| × τ_i
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer
        # 直接构造 optimizer 实例 (绕过 optuna 依赖检查)
        opt = EndToEndThresholdOptimizer.__new__(EndToEndThresholdOptimizer)
        opt.lambda_endogeneity = 0.5
        opt.threat_levels = {'f1': 0.8, 'f2': 0.4}
        weights = np.array([0.6, 0.4])
        factor_names = ['f1', 'f2']
        penalty = opt._endogeneity_penalty(weights, factor_names)
        # penalty = 0.5 × (0.6×0.8 + 0.4×0.4) = 0.5 × (0.48 + 0.16) = 0.5 × 0.64 = 0.32
        expected = 0.5 * (0.6 * 0.8 + 0.4 * 0.4)
        assert abs(penalty - expected) < 1e-10

    def test_E5_T13_optimizer_lambda_zero_no_effect(self):
        """E5-T13: λ=0 → 惩罚=0 (向后兼容, 目标函数与 v2.6.0 一致)."""
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer
        opt = EndToEndThresholdOptimizer.__new__(EndToEndThresholdOptimizer)
        opt.lambda_endogeneity = 0.0  # 默认值, 向后兼容
        opt.threat_levels = {'f1': 0.8}
        weights = np.array([0.6])
        penalty = opt._endogeneity_penalty(weights, ['f1'])
        assert penalty == 0.0


# ============================================================
# 硬依赖 E3 + 编排器 (E5-T14, T16, T17)
# ============================================================

class TestEndogeneityRegularizerDependency:
    """EndogeneityRegularizer 编排器: 硬依赖 E3 + 向后兼容."""

    def test_E5_T14_hard_dependency_on_e3(self):
        """E5-T14: E3 未运行时 (threat_assessment=None) E5 报错或降级.

        EndogeneityRegularizer 接收 threat_assessment dict,
        若为 None 或缺少 final_threat_tau → 报错或降级 (返回 None).
        """
        from factor_pipeline.modules.endogeneity_regularizer import EndogeneityRegularizer
        # threat_assessment=None → 应报错或降级
        with pytest.raises((ValueError, TypeError)):
            reg = EndogeneityRegularizer(threat_assessment=None)
            # 或者 apply 方法返回 None (降级)
            reg.apply_l1_neutralizer_config(None)

    def test_E5_T16_pipeline_apply_regularization_disabled(self):
        """E5-T16: enable_endogeneity_regularization=False → 返回 None."""
        config = PipelineV2Config()  # 默认 enable=False
        assert config.enable_endogeneity_regularization is False
        pipeline = FactorProcessingPipelineV2(config)
        # enable=False → 返回 None
        result = pipeline.apply_endogeneity_regularization(
            threat_assessment=_make_threat_assessment(0.5),
        )
        assert result is None

    def test_E5_T17_backward_compat_v3_0_0(self):
        """E5-T17: 不开启时现有配置字段保持默认 (零回归).

        新增字段默认全部 False/0.0, 不影响 v3.0.0 行为.
        """
        config = PipelineV2Config()
        # E5 新增字段默认值
        assert config.enable_endogeneity_regularization is False
        assert config.regularizer_gamma == 0.5
        assert config.regularizer_rho == 0.3
        assert config.lambda_endogeneity == 0.0
        # 不开启时, 实例化正常
        pipeline = FactorProcessingPipelineV2(config)
        assert pipeline is not None
