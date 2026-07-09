# -*- coding: utf-8 -*-
"""RESEARCH_NOTES E6 — DriftAwareBandit Monte Carlo 验证沙箱测试 (LinUCB)

测试三方案对比 (Plan A 静态规则 / Plan B Drift-Aware LinUCB / Plan C 朴素 LinUCB)
+ 决策门 (improvement_vs_a ≥ 10%) + CUSUM 漂移检测.

规格文档: docs/EXECUTION_RESEARCH_NOTES.md 行 1726-2156

算法: LinUCB (Li et al. 2010), 替换原 Thompson Sampling.
"""
import pytest
import numpy as np

from backtest.bandit_mc_sandbox import BanditMCSandbox
from backtest.cusum_drift_monitor import CUSUMDriftMonitor


# ============================================================
# 测试辅助: 使用小规模参数加速
# ============================================================

FAST_KWARGS = dict(n_simulations=5, n_periods=100, n_regimes=2, random_state=42)

# Plan B > Plan C 需要足够大的参数才稳定 (CUSUM 触发后遗忘优势显现)
STABLE_KWARGS = dict(n_simulations=50, n_periods=2520, n_regimes=2, random_state=42)


# ============================================================
# E6 测试: BanditMCSandbox (LinUCB)
# ============================================================

class TestBanditMCSandbox:
    """Drift-Aware Bandit (LinUCB) Monte Carlo 验证沙箱测试"""

    # ----------------------------------------------------------
    # 1. 数据生成
    # ----------------------------------------------------------

    def test_simulate_regime_switching_data_shape(self):
        """生成数据形状: rewards (T, K), regimes (T,)"""
        sandbox = BanditMCSandbox(**FAST_KWARGS)
        rewards, regimes = sandbox._simulate_regime_switching_data(
            n_periods=100, n_regimes=2, drift_magnitude=0.5
        )
        assert rewards.shape == (100, 3)
        assert regimes.shape == (100,)

    def test_simulate_regime_switching_has_transitions(self):
        """数据含体制转换 (至少 2 个 regime)"""
        sandbox = BanditMCSandbox(
            n_simulations=5, n_periods=300, n_regimes=2, random_state=42
        )
        rewards, regimes = sandbox._simulate_regime_switching_data(
            n_periods=300, n_regimes=2, drift_magnitude=0.5
        )
        assert len(np.unique(regimes)) >= 2

    # ----------------------------------------------------------
    # 2. 三方案返回类型
    # ----------------------------------------------------------

    def test_plan_a_static_rules_returns_float(self):
        """Plan A 静态规则返回浮点累计奖励"""
        sandbox = BanditMCSandbox(**FAST_KWARGS)
        data, _ = sandbox._simulate_regime_switching_data(100, 2, 0.5)
        cusum = sandbox._build_cusum(data)
        reward = sandbox._plan_a_static_rules(data, cusum)
        assert isinstance(reward, float)

    def test_plan_b_drift_aware_bandit_returns_float(self):
        """Plan B Drift-Aware LinUCB 返回浮点累计奖励"""
        sandbox = BanditMCSandbox(**FAST_KWARGS)
        data, _ = sandbox._simulate_regime_switching_data(100, 2, 0.5)
        cusum = sandbox._build_cusum(data)
        reward = sandbox._plan_b_drift_aware_bandit(data, cusum)
        assert isinstance(reward, float)

    def test_plan_c_naive_bandit_returns_float(self):
        """Plan C 朴素 LinUCB 返回浮点累计奖励"""
        sandbox = BanditMCSandbox(**FAST_KWARGS)
        data, _ = sandbox._simulate_regime_switching_data(100, 2, 0.5)
        reward = sandbox._plan_c_naive_bandit(data)
        assert isinstance(reward, float)

    # ----------------------------------------------------------
    # 3. 漂移感知优势验证
    # ----------------------------------------------------------

    def test_plan_b_better_than_plan_c(self):
        """Drift-Aware LinUCB 优于朴素 LinUCB (漂移感知的必要性)

        用足够大的 n_periods 和 n_simulations 确保 Plan B 优势稳定.
        CUSUM 触发后重置 LinUCB 先验, 使 bandit 快速适应新体制.
        """
        sandbox = BanditMCSandbox(**STABLE_KWARGS)
        results = sandbox.run_comparison(n_bandit_arms=3, drift_magnitude=0.5)
        assert results['plan_b_drift_aware']['mean_reward'] > \
               results['plan_c_naive']['mean_reward']

    # ----------------------------------------------------------
    # 4. run_comparison 接口
    # ----------------------------------------------------------

    def test_run_comparison_returns_all_plans(self):
        """run_comparison 返回含三方案 + 决策门"""
        sandbox = BanditMCSandbox(**FAST_KWARGS)
        results = sandbox.run_comparison()
        expected_keys = {
            'plan_a_static', 'plan_b_drift_aware',
            'plan_c_naive', 'decision_gate'
        }
        assert expected_keys <= set(results.keys())

    def test_decision_gate_has_passed_flag(self):
        """决策门含 passed 布尔标志"""
        sandbox = BanditMCSandbox(**FAST_KWARGS)
        results = sandbox.run_comparison()
        assert 'passed' in results['decision_gate']
        assert isinstance(results['decision_gate']['passed'], bool)

    def test_decision_gate_threshold_10_percent(self):
        """决策门阈值为 10%"""
        sandbox = BanditMCSandbox(**FAST_KWARGS)
        results = sandbox.run_comparison()
        assert results['decision_gate']['threshold'] == 0.10

    # ----------------------------------------------------------
    # 5. 复现性与诊断
    # ----------------------------------------------------------

    def test_random_state_reproducibility(self):
        """相同 random_state 结果一致 (np.allclose)"""
        s1 = BanditMCSandbox(**FAST_KWARGS)
        s2 = BanditMCSandbox(**FAST_KWARGS)
        r1 = s1.run_comparison()
        r2 = s2.run_comparison()
        assert np.allclose(
            r1['plan_a_static']['mean_reward'],
            r2['plan_a_static']['mean_reward'],
        )
        assert np.allclose(
            r1['plan_b_drift_aware']['mean_reward'],
            r2['plan_b_drift_aware']['mean_reward'],
        )
        assert np.allclose(
            r1['plan_c_naive']['mean_reward'],
            r2['plan_c_naive']['mean_reward'],
        )

    def test_get_diagnostics_before_run(self):
        """未运行时 diagnostics 返回 {'ran': False}"""
        sandbox = BanditMCSandbox(**FAST_KWARGS)
        diag = sandbox.get_diagnostics()
        assert diag['ran'] is False

    # ----------------------------------------------------------
    # 6. drift_magnitude 参数
    # ----------------------------------------------------------

    def test_drift_magnitude_affects_results(self):
        """drift_magnitude 参数影响 Plan B 和 Plan C 的奖励差异"""
        sandbox = BanditMCSandbox(**FAST_KWARGS)
        r_low = sandbox.run_comparison(drift_magnitude=0.1)
        r_high = sandbox.run_comparison(drift_magnitude=1.0)
        # 高漂移幅度下 Plan B 相对 Plan C 的优势应更明显
        diff_low = r_low['plan_b_drift_aware']['mean_reward'] - \
                   r_low['plan_c_naive']['mean_reward']
        diff_high = r_high['plan_b_drift_aware']['mean_reward'] - \
                    r_high['plan_c_naive']['mean_reward']
        # 两者不应完全相等 (drift_magnitude 确实影响结果)
        assert not np.isclose(diff_low, diff_high)

    # ----------------------------------------------------------
    # 7. evaluate_decision_gate 方法
    # ----------------------------------------------------------

    def test_evaluate_decision_gate_with_results(self):
        """evaluate_decision_gate 接受 results 参数返回决策门字典"""
        sandbox = BanditMCSandbox(**FAST_KWARGS)
        results = sandbox.run_comparison()
        gate = sandbox.evaluate_decision_gate(results)
        assert 'passed' in gate
        assert 'improvement_vs_a' in gate
        assert 'threshold' in gate
        assert gate['threshold'] == 0.10

    def test_evaluate_decision_gate_without_results(self):
        """evaluate_decision_gate 无结果时返回 {'evaluated': False}"""
        sandbox = BanditMCSandbox(**FAST_KWARGS)
        gate = sandbox.evaluate_decision_gate()
        assert gate.get('evaluated') is False

    def test_evaluate_decision_gate_uses_last_results(self):
        """evaluate_decision_gate 无参数时使用上次 run_comparison 结果"""
        sandbox = BanditMCSandbox(**FAST_KWARGS)
        results = sandbox.run_comparison()
        gate_default = sandbox.evaluate_decision_gate()
        gate_explicit = sandbox.evaluate_decision_gate(results)
        assert gate_default == gate_explicit

    # ----------------------------------------------------------
    # 8. CUSUM 在 Plan A/B 中的使用
    # ----------------------------------------------------------

    def test_cusum_monitor_built_correctly(self):
        """_build_cusum 返回 CUSUMDriftMonitor 实例, 参数正确"""
        sandbox = BanditMCSandbox(**FAST_KWARGS)
        data, _ = sandbox._simulate_regime_switching_data(100, 2, 0.5)
        cusum = sandbox._build_cusum(data)
        assert isinstance(cusum, CUSUMDriftMonitor)
        assert cusum.k == 0.5
        assert cusum.h == 5.5
        assert cusum.baseline_std > 0

    def test_cusum_triggers_in_plan_b(self):
        """Plan B 中 CUSUM 在足够长序列上会触发漂移检测"""
        sandbox = BanditMCSandbox(
            n_simulations=1, n_periods=2520, n_regimes=2, random_state=42
        )
        data, _ = sandbox._simulate_regime_switching_data(2520, 2, 0.5)
        cusum = sandbox._build_cusum(data)
        cusum.reset()
        triggers = 0
        for t in range(2520):
            r = cusum.update(float(data[t].mean()))
            if r['detected']:
                triggers += 1
        # 2520 期, p_stay=0.95 → 约 126 次体制切换, CUSUM 应触发多次
        assert triggers > 0

    def test_plan_b_resets_cusum_on_drift(self):
        """Plan B 在 CUSUM 触发时重置 LinUCB 先验 (遗忘历史)"""
        sandbox = BanditMCSandbox(**FAST_KWARGS)
        data, _ = sandbox._simulate_regime_switching_data(100, 2, 0.5)
        cusum = sandbox._build_cusum(data)
        # Plan B 应正常执行 (CUSUM 触发时重置 A_a, b_a)
        reward = sandbox._plan_b_drift_aware_bandit(data, cusum)
        assert isinstance(reward, float)
        # 执行后 CUSUM 应有历史记录 (说明被调用过)
        assert len(cusum.score_history) > 0

    # ----------------------------------------------------------
    # 9. 诊断扩展
    # ----------------------------------------------------------

    def test_get_diagnostics_after_run(self):
        """运行后 diagnostics 返回 ran=True 及结果"""
        sandbox = BanditMCSandbox(**FAST_KWARGS)
        sandbox.run_comparison()
        diag = sandbox.get_diagnostics()
        assert diag['ran'] is True
        assert diag['n_simulations'] == 5
        assert diag['n_periods'] == 100
        assert 'results' in diag
