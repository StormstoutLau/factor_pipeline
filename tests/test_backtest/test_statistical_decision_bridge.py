# -*- coding: utf-8 -*-
"""RESEARCH_NOTES E10 — StatisticalDecisionBridge + StateConditionedPrior 测试 (TDD Red)

测试统计→决策桥接:
- 方案 A (概率映射): (p_value, IC, drift_flag) → softmax 权重 (和为 1)
- 方案 C (OCO): 在线凸优化 + 单纯形投影 (非负且和为 1)
- Q2 soft-update: (μ, σ²) 参数空间在线更新
- 冷启动 O1: 无信息先验 μ=0, σ²=1
- 时间对齐 §4.7.1: 日频 → 月频/季频聚合

规格文档: docs/EXECUTION_RESEARCH_NOTES.md 行 3426-3898

TDD 流程: Red (本文件) → Green (实现) → Review
"""
import pytest
import numpy as np

from factor_pipeline.backtest.statistical_decision_bridge import (
    StatisticalDecisionBridge,
    StateConditionedPrior,
)


# ============================================================
# 辅助函数
# ============================================================

def _make_stats(**overrides) -> dict:
    """构造标准统计输出字典"""
    stats = {
        'p_value': 0.02,
        'ic_mean': 0.05,
        'drift_flag': False,
        'regime': 'bull',
    }
    stats.update(overrides)
    return stats


# ============================================================
# E10 测试: StatisticalDecisionBridge + StateConditionedPrior
# ============================================================

class TestStatisticalDecisionBridge:
    """统计→决策桥接测试 (方案 A 概率映射 + 方案 C OCO + Q2 soft-update)"""

    # ----------------------------------------------------------
    # 1. fit / 冷启动
    # ----------------------------------------------------------

    def test_fit_returns_self(self):
        """fit 返回 self (链式调用)"""
        bridge = StatisticalDecisionBridge(enable=True)
        stats = {'factor_1': _make_stats()}
        result = bridge.fit(stats)
        assert isinstance(result, StatisticalDecisionBridge)

    def test_cold_start_uninformative(self):
        """无信息先验 μ=0, σ²=1"""
        bridge = StatisticalDecisionBridge(
            enable=True, cold_start_prior='uninformative'
        )
        stats = {'factor_1': _make_stats()}
        bridge.fit(stats)
        params = bridge._factor_params['factor_1']
        assert params['mu'] == 0.0
        assert params['sigma_sq'] == 1.0

    # ----------------------------------------------------------
    # 2. Q2 soft-update
    # ----------------------------------------------------------

    def test_update_q2_soft_update(self):
        """Q2 更新后 μ 和 σ² 发生变化"""
        bridge = StatisticalDecisionBridge(enable=True, learning_rate=0.5)
        stats = {'factor_1': _make_stats()}
        bridge.fit(stats)
        old_mu = bridge._factor_params['factor_1']['mu']
        old_sigma_sq = bridge._factor_params['factor_1']['sigma_sq']
        result = bridge.update('factor_1', new_observation=0.5)
        assert result['mu'] != old_mu
        assert result['sigma_sq'] != old_sigma_sq

    def test_update_n_observations_increments(self):
        """更新后 n_obs 递增 +1"""
        bridge = StatisticalDecisionBridge(enable=True)
        stats = {'factor_1': _make_stats()}
        bridge.fit(stats)
        initial = bridge._factor_params['factor_1']['n_obs']
        result = bridge.update('factor_1', 0.05)
        assert result['n_obs'] == initial + 1

    # ----------------------------------------------------------
    # 3. 方案 A: 概率映射
    # ----------------------------------------------------------

    def test_compute_decision_weights_sum_to_one(self):
        """softmax 权重和为 1"""
        bridge = StatisticalDecisionBridge(enable=True)
        stats = {
            'f1': _make_stats(p_value=0.02, ic_mean=0.05),
            'f2': _make_stats(p_value=0.15, ic_mean=-0.02, drift_flag=True),
        }
        bridge.fit(stats)
        weights = bridge.compute_decision_weights()
        assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_compute_decision_weights_significant_factor_higher(self):
        """显著因子 (p 值小, IC 高) 权重更高"""
        bridge = StatisticalDecisionBridge(enable=True)
        stats = {
            'significant': _make_stats(p_value=0.01, ic_mean=0.1),
            'non_significant': _make_stats(p_value=0.5, ic_mean=0.01),
        }
        bridge.fit(stats)
        weights = bridge.compute_decision_weights()
        assert weights['significant'] > weights['non_significant']

    def test_probability_mapping_drift_penalty(self):
        """漂移因子降权: score_with_drift < score_without_drift"""
        bridge = StatisticalDecisionBridge(enable=True)
        score_without = bridge._probability_mapping(
            0.02, 0.05, drift_flag=False
        )
        score_with = bridge._probability_mapping(
            0.02, 0.05, drift_flag=True
        )
        assert score_with < score_without

    def test_probability_mapping_p_value_effect(self):
        """p 值越小得分越高: score(p=0.01) > score(p=0.5)"""
        bridge = StatisticalDecisionBridge(enable=True)
        score_low_p = bridge._probability_mapping(0.01, 0.05, drift_flag=False)
        score_high_p = bridge._probability_mapping(0.5, 0.05, drift_flag=False)
        assert score_low_p > score_high_p

    # ----------------------------------------------------------
    # 4. 方案 C: 在线凸优化 (OCO)
    # ----------------------------------------------------------

    def test_oco_update_simplex_projection(self):
        """OCO 权重在单纯形上 (非负且和为 1)"""
        bridge = StatisticalDecisionBridge(enable=True)
        gradient = {'f1': 0.1, 'f2': -0.2, 'f3': 0.05}
        weights = bridge.oco_update(gradient, eta=0.01)
        assert all(w >= 0 for w in weights.values())
        assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_oco_update_gradient_descent(self):
        """OCO 沿梯度反方向移动: high_gradient 因子权重下降"""
        bridge = StatisticalDecisionBridge(enable=True)
        # f1 梯度远大于 f2 → f1 权重应低于 f2
        gradient = {'f1': 2.0, 'f2': 0.0}
        weights = bridge.oco_update(gradient, eta=0.1)
        assert weights['f1'] < weights['f2']

    # ----------------------------------------------------------
    # 5. 时间对齐 (§4.7.1)
    # ----------------------------------------------------------

    def test_align_time_frequency_daily(self):
        """日频返回最近值"""
        bridge = StatisticalDecisionBridge(enable=True)
        daily_stats = {'f1': [0.1, 0.2, 0.3, 0.4, 0.5]}
        result = bridge._align_time_frequency(daily_stats, decision_freq='D')
        assert result['f1'] == pytest.approx(0.5)

    def test_align_time_frequency_monthly(self):
        """月频返回近 21 日均值"""
        bridge = StatisticalDecisionBridge(enable=True)
        values = [float(i) for i in range(30)]
        daily_stats = {'f1': values}
        result = bridge._align_time_frequency(daily_stats, decision_freq='M')
        expected = float(np.mean(values[-21:]))
        assert result['f1'] == pytest.approx(expected, abs=1e-10)

    # ----------------------------------------------------------
    # 6. 诊断与 enable=False
    # ----------------------------------------------------------

    def test_get_diagnostics_fields(self):
        """诊断含必要字段: n_factors / learning_rate / factor_params"""
        bridge = StatisticalDecisionBridge(enable=True, learning_rate=0.1)
        stats = {'f1': _make_stats()}
        bridge.fit(stats)
        diag = bridge.get_diagnostics()
        assert {'n_factors', 'learning_rate', 'factor_params'} <= set(diag.keys())

    def test_disabled_no_op(self):
        """enable=False 时 compute_decision_weights 返回 {}"""
        bridge = StatisticalDecisionBridge(enable=False)
        stats = {'f1': _make_stats()}
        bridge.fit(stats)
        weights = bridge.compute_decision_weights()
        assert weights == {}

    def test_state_conditioned_prior_dataclass(self):
        """StateConditionedPrior 属性访问正确"""
        prior = StateConditionedPrior(
            factor_name='momentum',
            regime='bull',
            mu_prior=0.05,
            sigma_sq_prior=0.01,
            confidence=0.8,
            n_observations=100,
        )
        assert prior.factor_name == 'momentum'
        assert prior.regime == 'bull'
        assert prior.mu_prior == 0.05
        assert prior.sigma_sq_prior == 0.01
        assert prior.confidence == 0.8
        assert prior.n_observations == 100
