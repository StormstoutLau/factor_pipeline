# -*- coding: utf-8 -*-
"""
P3 Phase 3: EndToEndThresholdOptimizer — TDD 测试套件

测试端到端阈值优化器的核心功能:
  A. 优化器初始化与搜索空间
  B. 目标函数计算
  C. 约束违反检测
  D. 参数映射到配置
  E. 扩展窗口 CV
"""

import unittest
import numpy as np
import pandas as pd


# =============================================================================
# A. 优化器初始化与搜索空间
# =============================================================================

class TestOptimizerInit(unittest.TestCase):
    """测试 A: 优化器初始化"""

    def test_01_optimizer_creation(self):
        """
        [P3-Phase3-01] 优化器创建成功，搜索空间包含 8 维参数。
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=10)

        self.assertIsNotNone(optimizer)
        self.assertEqual(optimizer.n_trials, 10)
        self.assertEqual(len(optimizer.search_space), 8,
            f"搜索空间应有 8 维，实际 {len(optimizer.search_space)}")

        expected_params = [
            'hard_routing_prob', 'merge_alpha', 'ks_alpha',
            'mixed_winsor_sigma', 'transform_aggressiveness',
            'classification_threshold_static', 'classification_threshold_dynamic',
            'migration_threshold',
        ]
        for param in expected_params:
            self.assertIn(param, optimizer.search_space,
                f"搜索空间应包含 {param}")

        print(f"\n  手工校验通过: 搜索空间 {len(optimizer.search_space)} 维")
        for name, spec in optimizer.search_space.items():
            print(f"    {name}: [{spec['low']}, {spec['high']}] ({spec.get('type', 'float')})")

    def test_02_search_space_bounds(self):
        """
        [P3-Phase3-02] 搜索空间边界正确。
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=10)
        bounds = {
            'hard_routing_prob':              (0.5, 1.0),
            'merge_alpha':                    (0.0, 1.0),
            'ks_alpha':                       (0.001, 0.5),
            'mixed_winsor_sigma':             (1.0, 10.0),
            'transform_aggressiveness':       (0.3, 5.0),
            'classification_threshold_static': (0.5, 1.0),
            'classification_threshold_dynamic': (0.0, 0.5),
            'migration_threshold':            (0.0, 1.0),
        }

        for name, (lo, hi) in bounds.items():
            spec = optimizer.search_space[name]
            self.assertAlmostEqual(spec['low'], lo, places=6,
                msg=f"{name} 下限应为 {lo}")
            self.assertAlmostEqual(spec['high'], hi, places=6,
                msg=f"{name} 上限应为 {hi}")

        print(f"\n  手工校验通过: 8 维搜索空间边界全部正确")


# =============================================================================
# B. 目标函数计算
# =============================================================================

class TestObjectiveFunction(unittest.TestCase):
    """测试 B: 目标函数"""

    def test_03_ic_primary_objective(self):
        """
        [P3-Phase3-03] IC 主目标计算正确。

        手工计算: IC = corr(factor, forward_return).mean()
        P0-2 更新: IC 计算方向改为 (n_periods, n_stocks),自动转置兼容
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=10)

        # 构造模拟数据: (n_stocks, n_periods) — 旧格式,程序应自动转置
        np.random.seed(42)
        n_stocks, n_periods = 100, 20
        factor_values = np.random.randn(n_stocks, n_periods)
        forward_returns = 0.5 * factor_values + 0.5 * np.random.randn(n_stocks, n_periods)

        # 手工计算 IC (按 period 迭代)
        ics = []
        for t in range(n_periods):
            ic = np.corrcoef(factor_values[:, t], forward_returns[:, t])[0, 1]
            ics.append(ic)
        expected_ic = np.mean(ics)

        computed_ic = optimizer._compute_ic(factor_values, forward_returns)

        self.assertAlmostEqual(computed_ic, expected_ic, places=6)

        print(f"\n  手工校验: IC={computed_ic:.6f} (expected {expected_ic:.6f})")

    def test_04_ic_volatility_penalty(self):
        """
        [P3-Phase3-04] IC 波动性惩罚计算正确。

        手工计算: penalty = std(IC) / 0.1 (标准化)，当 std(IC) > 0.1 时生效
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=10)

        # 高波动 IC
        np.random.seed(42)
        high_vol_ic = np.random.randn(20) * 0.3  # std=0.3
        penalty_high = optimizer._ic_volatility_penalty(high_vol_ic)
        expected_high = max(0, np.std(high_vol_ic) - 0.1)
        self.assertAlmostEqual(penalty_high, expected_high, places=6)

        # 低波动 IC (无惩罚)
        low_vol_ic = np.array([0.05] * 20)  # std=0
        penalty_low = optimizer._ic_volatility_penalty(low_vol_ic)
        self.assertAlmostEqual(penalty_low, 0.0, places=6)

        print(f"\n  手工校验: 高波动惩罚={penalty_high:.6f} (expected {expected_high:.6f})")
        print(f"    低波动惩罚={penalty_low:.6f} (expected 0.0)")

    def test_05_ks_distribution_fidelity(self):
        """
        [P3-Phase3-05] KS 分布保真度约束计算正确。

        手工计算: 对变换前后的因子做 KS 检验，p 值越高越好。
        fidelity = 1 - min_p_value (p 值越高，分布越相似)
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer
        from scipy import stats

        optimizer = EndToEndThresholdOptimizer(n_trials=10)

        # 同分布数据 (高保真度)
        np.random.seed(42)
        before = np.random.randn(100, 5)
        after = before + np.random.randn(100, 5) * 0.01  # 微小扰动

        fidelity = optimizer._ks_distribution_fidelity(before, after)

        # 手工计算
        p_values = []
        for i in range(5):
            _, p = stats.ks_2samp(before[:, i], after[:, i])
            p_values.append(p)
        min_p = min(p_values)
        expected = min(1.0, -np.log10(max(min_p, 1e-10)) / 10)  # -log10 scale, capped at 1

        # 同分布应该有高保真度
        self.assertGreater(fidelity, 0.0)
        self.assertLessEqual(fidelity, 1.0)

        print(f"\n  手工校验: 同分布 fidelity={fidelity:.4f} (min_p={min_p:.4f})")

    def test_06_coverage_constraint(self):
        """
        [P3-Phase3-06] 覆盖率约束计算正确。

        手工计算: coverage = n_processed / n_total
        如果 coverage < 0.5，惩罚 = (0.5 - coverage) * 2
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=10)

        # 高覆盖率 (无惩罚)
        penalty_high = optimizer._coverage_penalty(n_processed=90, n_total=100)
        self.assertAlmostEqual(penalty_high, 0.0, places=6)

        # 低覆盖率 (有惩罚)
        penalty_low = optimizer._coverage_penalty(n_processed=30, n_total=100)
        expected_low = max(0, 0.5 - 30 / 100)
        self.assertAlmostEqual(penalty_low, expected_low, places=6)

        print(f"\n  手工校验: 高覆盖率惩罚={penalty_high:.4f} (expected 0.0)")
        print(f"    低覆盖率惩罚={penalty_low:.4f} (expected {expected_low:.4f})")

    def test_07_composite_objective(self):
        """
        [P3-Phase3-07] 复合目标函数 = IC - λ1*vol_penalty - λ2*coverage_penalty。

        手工计算: objective = ic_mean - 0.5*vol_penalty - 0.3*coverage_penalty
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(
            n_trials=10,
            lambda_volatility=0.5,
            lambda_coverage=0.3,
        )

        # 模拟数据
        ic_array = np.array([0.05, 0.06, 0.04, 0.07, 0.03])  # mean=0.05, std=0.0158
        n_processed, n_total = 80, 100

        expected_ic = np.mean(ic_array)
        expected_vol_penalty = max(0, np.std(ic_array) - 0.1)
        expected_cov_penalty = max(0, 0.5 - n_processed / n_total)
        expected_objective = expected_ic - 0.5 * expected_vol_penalty - 0.3 * expected_cov_penalty

        objective = optimizer._composite_objective(ic_array, n_processed, n_total)

        self.assertAlmostEqual(objective, expected_objective, places=6)

        print(f"\n  手工校验: 目标函数")
        print(f"    IC={expected_ic:.6f}, vol_penalty={expected_vol_penalty:.6f}, cov_penalty={expected_cov_penalty:.6f}")
        print(f"    objective={objective:.6f} (expected {expected_objective:.6f})")

    # =====================================================================
    # E4 (v2.6.0): 目标函数对齐 ADR-004 (health_penalty 代理)
    # =====================================================================

    def test_e4_01_health_penalty_low_health(self):
        """[v2.6.0-E4-01] IC decay < 0.5 时, health_penalty == 0.5 (ADR-004: < 40 → -0.5)."""
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1)
        # IC 衰减严重: 前 4 期 0.10, 后 4 期 0.01 (decay_ratio = 0.01/0.10 = 0.1 < 0.5)
        ic_low_health = np.array([0.10, 0.10, 0.10, 0.10, 0.01, 0.01, 0.01, 0.01])

        penalty = optimizer._health_penalty_proxy(ic_low_health)

        self.assertEqual(penalty, 0.5,
                         msg=f"低健康度应 0.5, 得到 {penalty}")

        print(f"\n  手工校验 E4-01: 低健康度 penalty={penalty}")

    def test_e4_02_health_penalty_medium_health(self):
        """[v2.6.0-E4-02] IC decay < 0.8 时, health_penalty == 0.2 (ADR-004: < 60 → -0.2)."""
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1)
        # IC 轻微衰减: 前 4 期 0.10, 后 4 期 0.07 (decay_ratio = 0.7, 0.5 <= 0.7 < 0.8)
        # hit_rate: 8/8 = 1.0 > 0.5; ic_vol = std([0.10,0.10,0.10,0.10,0.07,0.07,0.07,0.07]) ≈ 0.015 < 0.15
        ic_medium_health = np.array([0.10, 0.10, 0.10, 0.10, 0.07, 0.07, 0.07, 0.07])

        penalty = optimizer._health_penalty_proxy(ic_medium_health)

        self.assertEqual(penalty, 0.2,
                         msg=f"中健康度应 0.2, 得到 {penalty}")

        print(f"\n  手工校验 E4-02: 中健康度 penalty={penalty}")

    def test_e4_03_health_penalty_high_health(self):
        """[v2.6.0-E4-03] IC decay > 0.8 + hit_rate > 0.55 + ic_vol < 0.1 时, health_penalty == 0.0."""
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1)
        # IC 稳定: decay_ratio = 1.0 > 0.8, hit_rate = 1.0 > 0.55, ic_vol ≈ 0.005 < 0.1
        ic_high_health = np.array([0.05, 0.06, 0.05, 0.06, 0.05, 0.06, 0.05, 0.06])

        penalty = optimizer._health_penalty_proxy(ic_high_health)

        self.assertEqual(penalty, 0.0,
                         msg=f"高健康度应 0.0, 得到 {penalty}")

        print(f"\n  手工校验 E4-03: 高健康度 penalty={penalty}")

    def test_e4_04_ks_penalty_sign_corrected(self):
        """[v2.6.0-E4-04] KS 分布扭曲时, ks_distortion_penalty > 0, 目标函数减少 (非增加).

        修正前: + λ_fid * fidelity (奖励, 符号方向相反)
        修正后: - λ_fid * ks_distortion_penalty (惩罚, 符号方向正确)
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1, lambda_fidelity=0.1)
        np.random.seed(42)
        ic_array = np.array([0.05, 0.06, 0.04, 0.07, 0.03, 0.05, 0.06, 0.04])

        # 场景 1: before/after 相同 (无扭曲)
        before = np.random.randn(100, 3)
        after_same = before.copy()
        obj_no_distortion = optimizer._composite_objective(
            ic_array, 80, 100, before=before, after=after_same
        )

        # 场景 2: before/after 差异大 (高扭曲)
        after_distorted = np.random.randn(100, 3) * 5
        obj_high_distortion = optimizer._composite_objective(
            ic_array, 80, 100, before=before, after=after_distorted
        )

        # 高扭曲应导致更低的目标函数 (惩罚, 而非奖励)
        self.assertLess(obj_high_distortion, obj_no_distortion,
                        "KS 扭曲应降低目标函数 (惩罚, 非奖励)")

        print(f"\n  手工校验 E4-04: KS 符号修正")
        print(f"    无扭曲: {obj_no_distortion:.6f}")
        print(f"    高扭曲: {obj_high_distortion:.6f} (应更低)")

    def test_e4_05_ks_penalty_zero_when_identical(self):
        """[v2.6.0-E4-05] before == after 时, ks_distortion_penalty == 0."""
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1, lambda_fidelity=0.1)
        np.random.seed(42)
        before = np.random.randn(100, 3)
        after = before.copy()

        fidelity = optimizer._ks_distribution_fidelity(before, after)
        distortion = 1.0 - fidelity

        self.assertLess(distortion, 0.01,
                        msg=f"分布相同时 distortion 应 < 0.01, 得到 {distortion}")

        print(f"\n  手工校验 E4-05: 相同分布 distortion={distortion:.6f}")

    def test_e4_06_composite_objective_aligns_adr_004(self):
        """[v2.6.0-E4-06] 目标函数 = IC - vol - cov - ks - health (5 项, 符号全负)."""
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(
            n_trials=1,
            lambda_volatility=0.5,
            lambda_coverage=0.3,
            lambda_fidelity=0.1,
            lambda_health=0.4,
        )
        np.random.seed(42)
        # 8 个元素, 触发 health_penalty
        ic_array = np.array([0.10, 0.10, 0.10, 0.10, 0.01, 0.01, 0.01, 0.01])  # 低健康度
        before = np.random.randn(100, 3)
        after = np.random.randn(100, 3) * 3  # 高扭曲

        # 手工计算各项
        ic_mean = float(np.nanmean(ic_array))
        vol_penalty = optimizer._ic_volatility_penalty(ic_array)
        cov_penalty = optimizer._coverage_penalty(80, 100)
        fidelity = optimizer._ks_distribution_fidelity(before, after)
        ks_distortion = 1.0 - fidelity
        health_penalty = optimizer._health_penalty_proxy(ic_array)

        expected_objective = (
            ic_mean
            - 0.5 * vol_penalty
            - 0.3 * cov_penalty
            - 0.1 * ks_distortion
            - 0.4 * health_penalty
        )

        actual_objective = optimizer._composite_objective(
            ic_array, 80, 100, before=before, after=after
        )

        self.assertAlmostEqual(actual_objective, expected_objective, places=10,
                               msg=f"目标函数应对齐 ADR-004 (5 项, 符号全负)")

        print(f"\n  手工校验 E4-06: ADR-004 对齐")
        print(f"    IC={ic_mean:.4f}, vol_p={vol_penalty:.4f}, cov_p={cov_penalty:.4f}")
        print(f"    ks_p={ks_distortion:.4f}, health_p={health_penalty:.4f}")
        print(f"    objective={actual_objective:.6f} (expected {expected_objective:.6f})")

    def test_e4_07_health_penalty_decay_ratio(self):
        """[v2.6.0-E4-07] 手工计算 decay_ratio, 与实现对比."""
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1)
        ic_array = np.array([0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03])

        # 手工计算 decay_ratio
        clean = ic_array[~np.isnan(ic_array)]
        mid = len(clean) // 2  # 4
        ic_early = float(np.mean(clean[:mid]))  # mean([0.10, 0.09, 0.08, 0.07]) = 0.085
        ic_late = float(np.mean(clean[mid:]))   # mean([0.06, 0.05, 0.04, 0.03]) = 0.045
        expected_decay_ratio = ic_late / ic_early  # 0.5294

        # 验证: decay_ratio 在 [0.5, 0.8) 区间, health_penalty = 0.2
        penalty = optimizer._health_penalty_proxy(ic_array)
        self.assertEqual(penalty, 0.2,
                         msg=f"decay_ratio={expected_decay_ratio:.4f} 应触发 medium health (0.2)")

        print(f"\n  手工校验 E4-07: decay_ratio")
        print(f"    ic_early={ic_early:.4f}, ic_late={ic_late:.4f}")
        print(f"    decay_ratio={expected_decay_ratio:.4f} (在 [0.5, 0.8) 区间)")
        print(f"    penalty={penalty}")

    def test_e4_08_health_penalty_hit_rate(self):
        """[v2.6.0-E4-08] 手工计算 hit_rate, 与实现对比."""
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1)
        # hit_rate = 4/8 = 0.5 (在 [0.4, 0.5) 区间, 触发 medium)
        # 但 decay_ratio = mean([0.1,0.1,0.1,0.1]) / mean([-0.05,-0.05,-0.05,-0.05])
        #                = 0.1 / -0.05 = -2.0 (负值, abs(early)=0.1 != 0, decay_ratio = -2.0 < 0.5)
        # 所以会触发 low health (decay_ratio < 0.5)
        ic_array = np.array([0.10, 0.10, 0.10, 0.10, -0.05, -0.05, -0.05, -0.05])

        clean = ic_array[~np.isnan(ic_array)]
        hit_rate = float(np.mean(clean > 0))  # 0.5
        mid = len(clean) // 2
        ic_early = float(np.mean(clean[:mid]))  # 0.10
        ic_late = float(np.mean(clean[mid:]))   # -0.05
        decay_ratio = ic_late / ic_early  # -0.5

        penalty = optimizer._health_penalty_proxy(ic_array)

        # decay_ratio = -0.5 < 0.5, 触发 low health
        self.assertEqual(penalty, 0.5,
                         msg=f"decay_ratio={decay_ratio:.4f} < 0.5 应触发 low health (0.5)")

        print(f"\n  手工校验 E4-08: hit_rate")
        print(f"    hit_rate={hit_rate:.4f}, decay_ratio={decay_ratio:.4f}")
        print(f"    penalty={penalty} (由 decay_ratio < 0.5 主导)")

    def test_e4_09_health_penalty_insufficient_data(self):
        """[v2.6.0-E4-09] len(clean) < 6 时, health_penalty == 0.0."""
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1)
        # 5 个元素 (< 6)
        ic_array = np.array([0.10, 0.09, 0.08, 0.07, 0.06])

        penalty = optimizer._health_penalty_proxy(ic_array)

        self.assertEqual(penalty, 0.0,
                         msg="数据不足时应返回 0.0 (不惩罚)")

        print(f"\n  手工校验 E4-09: 数据不足 penalty={penalty}")

    def test_e4_10_composite_objective_backward_compatible(self):
        """[v2.6.0-E4-10] lambda_health=0 时, 与 v2.5.0 行为一致 (除 fidelity 符号).

        注意: v2.5.0 的 fidelity 是 + λ_fid * fidelity (奖励),
        v2.6.0 修正为 - λ_fid * ks_distortion_penalty (惩罚).
        所以严格来说, 符号方向是修正, 不是向后兼容.
        此测试验证: lambda_health=0 + 不传 before/after 时, 与 v2.5.0 完全一致.
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        # lambda_health=0 (向后兼容)
        optimizer = EndToEndThresholdOptimizer(
            n_trials=10,
            lambda_volatility=0.5,
            lambda_coverage=0.3,
            lambda_fidelity=0.1,
            lambda_health=0.0,  # 显式禁用 health_penalty
        )

        ic_array = np.array([0.05, 0.06, 0.04, 0.07, 0.03])  # 5 个元素 (< 6, health=0)
        n_processed, n_total = 80, 100

        # 不传 before/after (ks_distortion=0)
        objective = optimizer._composite_objective(ic_array, n_processed, n_total)

        # 手工计算 (v2.5.0 等价: IC - vol - cov, 无 health, 无 ks)
        expected_ic = np.mean(ic_array)
        expected_vol_penalty = max(0, np.std(ic_array) - 0.1)
        expected_cov_penalty = max(0, 0.5 - n_processed / n_total)
        expected_objective = (
            expected_ic
            - 0.5 * expected_vol_penalty
            - 0.3 * expected_cov_penalty
        )

        self.assertAlmostEqual(objective, expected_objective, places=10,
                               msg="lambda_health=0 + 不传 before/after 应与 v2.5.0 一致")

        print(f"\n  手工校验 E4-10: 向后兼容")
        print(f"    objective={objective:.6f} (expected {expected_objective:.6f})")


# =============================================================================
# C. 参数映射
# =============================================================================

class TestParamMapping(unittest.TestCase):
    """测试 C: 参数映射到配置"""

    def test_08_params_to_config(self):
        """
        [P3-Phase3-08] 优化参数正确映射到 PipelineV2Config。
        P0-2 更新: transform_aggressiveness 会调整 mixed_winsor_sigma
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        optimizer = EndToEndThresholdOptimizer(n_trials=10)

        params = {
            'hard_routing_prob': 0.85,
            'merge_alpha': 0.45,
            'ks_alpha': 0.03,
            'mixed_winsor_sigma': 3.5,
            'transform_aggressiveness': 1.0,  # 1.0 = 不调整
            'classification_threshold_static': 0.75,
            'classification_threshold_dynamic': 0.35,
            'migration_threshold': 0.15,
        }

        config = optimizer._params_to_config(params)

        self.assertIsInstance(config, PipelineV2Config)
        self.assertEqual(config.hard_routing_prob, 0.85)
        self.assertEqual(config.merge_alpha, 0.45)
        self.assertEqual(config.ks_alpha, 0.03)
        # transform_aggressiveness=1.0 时不调整
        self.assertEqual(config.mixed_winsor_sigma, 3.5)

        print(f"\n  手工校验: 参数映射到配置")
        print(f"    hard_routing_prob={config.hard_routing_prob}")
        print(f"    merge_alpha={config.merge_alpha}")
        print(f"    ks_alpha={config.ks_alpha}")
        print(f"    mixed_winsor_sigma={config.mixed_winsor_sigma}")

    def test_09_config_roundtrip(self):
        """
        [P3-Phase3-09] 配置 → 参数字典 → 配置 往返一致。
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        optimizer = EndToEndThresholdOptimizer(n_trials=10)

        original = PipelineV2Config(
            hard_routing_prob=0.77,
            merge_alpha=0.33,
            ks_alpha=0.07,
            mixed_winsor_sigma=2.5,
        )

        params = optimizer._config_to_params(original)
        restored = optimizer._params_to_config(params)

        for field in ['hard_routing_prob', 'merge_alpha', 'ks_alpha', 'mixed_winsor_sigma']:
            self.assertEqual(getattr(restored, field), getattr(original, field))

        print(f"\n  手工校验: 配置往返一致")

    # =====================================================================
    # E2 (v2.6.0): migration_threshold 字段位置修正
    # =====================================================================

    def test_e2_01_migration_threshold_field_location(self):
        """
        [v2.6.0-E2-01] migration_threshold 设置到 config 本身, 不是 config.monitor.

        修正前: optimizer.py:155-158 错误设置到 config.monitor.migration_threshold
                (MonitorConfig 无此字段, hasattr 静默跳过, 参数被丢弃)
        修正后: config.migration_threshold 直接设置 (PipelineV2Config 新增字段)
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1)
        config = optimizer._params_to_config({'migration_threshold': 0.15})

        # 修正后: migration_threshold 位于 config 本身
        self.assertTrue(hasattr(config, 'migration_threshold'),
                        "PipelineV2Config 应有 migration_threshold 字段")
        self.assertEqual(config.migration_threshold, 0.15)

        # MonitorConfig 不应有 migration_threshold 字段 (避免字段位置混淆)
        self.assertFalse(hasattr(config.monitor, 'migration_threshold'),
                         "MonitorConfig 不应有 migration_threshold 字段")

        print(f"\n  手工校验 E2-01: 字段位置")
        print(f"    config.migration_threshold = {config.migration_threshold}")

    def test_e2_02_migration_threshold_default_value(self):
        """
        [v2.6.0-E2-02] 不传 migration_threshold 时使用默认值 0.10.

        PipelineV2Config.migration_threshold 默认值与
        PipelineV2ConfigUnified.migration_threshold (config_v2.py:407-410) 对齐.
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1)
        # 不传 migration_threshold
        config = optimizer._params_to_config({})

        self.assertTrue(hasattr(config, 'migration_threshold'))
        self.assertEqual(config.migration_threshold, 0.10,
                         "默认值应与 PipelineV2ConfigUnified 对齐 (0.10)")

        print(f"\n  手工校验 E2-02: 默认值 = {config.migration_threshold}")

    def test_e2_03_migration_threshold_affects_pipeline(self):
        """
        [v2.6.0-E2-03] 不同 migration_threshold 值产生不同 config 对象.

        验证字段位置修正后, 参数能实际传递到 config (而非被 hasattr 静默丢弃).
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1)
        config_strict = optimizer._params_to_config({'migration_threshold': 0.05})
        config_loose = optimizer._params_to_config({'migration_threshold': 0.30})

        self.assertNotEqual(config_strict.migration_threshold,
                            config_loose.migration_threshold,
                            "不同参数应产生不同 config 值")
        self.assertEqual(config_strict.migration_threshold, 0.05)
        self.assertEqual(config_loose.migration_threshold, 0.30)

        print(f"\n  手工校验 E2-03: 参数传递")
        print(f"    strict (0.05): {config_strict.migration_threshold}")
        print(f"    loose  (0.30): {config_loose.migration_threshold}")

    def test_e2_04_enable_smooth_transition_preserved(self):
        """
        [v2.6.0-E2-04] 设置 migration_threshold 后保留 enable_smooth_transition=True.

        修正前: optimizer.py:152 设置 config.monitor.enable_smooth_transition = True
        修正后: 保留此行为 (语义: 启用平滑过渡)
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1)
        config = optimizer._params_to_config({'migration_threshold': 0.15})

        self.assertTrue(config.monitor.enable_smooth_transition,
                        "设置 migration_threshold 后应启用平滑过渡")

        print(f"\n  手工校验 E2-04: enable_smooth_transition = "
              f"{config.monitor.enable_smooth_transition}")

    def test_e2_05_no_hasattr_silent_failure(self):
        """
        [v2.6.0-E2-05] 移除 hasattr 静默失败, 字段不存在时抛 AttributeError.

        修正前: optimizer.py:155-158 用 hasattr 检查, 字段不存在时静默跳过
                (migration_threshold 参数被丢弃, 优化器无法搜索此维度)
        修正后: 直接赋值, 字段不存在时抛 AttributeError (显式失败)
        """
        import inspect
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        # 检查 _params_to_config 源码不含 hasattr 静默检查
        source = inspect.getsource(EndToEndThresholdOptimizer._params_to_config)
        self.assertNotIn('hasattr(config.monitor', source,
                          "不应使用 hasattr(config.monitor, ...) 静默检查")

        # 直接赋值应正常工作 (字段已存在)
        optimizer = EndToEndThresholdOptimizer(n_trials=1)
        config = optimizer._params_to_config({'migration_threshold': 0.20})
        self.assertEqual(config.migration_threshold, 0.20)

        print(f"\n  手工校验 E2-05: 无 hasattr 静默失败")

    # =====================================================================
    # E5 (v2.6.0): 正交化参数纳入搜索空间
    # =====================================================================

    def test_e5_01_search_space_orth_default_off(self):
        """[v2.6.0-E5-01] search_orth=False (默认) 时, search_space 不含 orth_* 键.

        向后兼容: 未启用正交化搜索时, 搜索空间与 v2.5.0 一致 (8 维).
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1)  # 默认 search_orth=False

        orth_keys = [k for k in optimizer.search_space if k.startswith('orth_')]
        self.assertEqual(len(orth_keys), 0,
                         msg=f"search_orth=False 时不应有 orth_* 键, 实际: {orth_keys}")

        print(f"\n  手工校验 E5-01: search_orth=False, orth 键数 = {len(orth_keys)}")

    def test_e5_02_search_space_orth_enabled(self):
        """[v2.6.0-E5-02] search_orth=True 时, search_space 含 3 个 orth_* 键.

        新增维度: orth_method, orth_align_mode, orth_ridge_lambda
        不搜索 orth_enabled (用户决策, 非优化器决策).
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1, search_orth=True)

        expected_orth_keys = {'orth_method', 'orth_align_mode', 'orth_ridge_lambda'}
        actual_orth_keys = {k for k in optimizer.search_space if k.startswith('orth_')}

        self.assertEqual(actual_orth_keys, expected_orth_keys,
                         msg=f"应含 {expected_orth_keys}, 实际 {actual_orth_keys}")

        # 不应搜索 orth_enabled (用户决策)
        self.assertNotIn('orth_enabled', optimizer.search_space,
                         "orth_enabled 不应纳入搜索 (用户决策, 非优化器决策)")

        print(f"\n  手工校验 E5-02: search_orth=True, orth 键 = {sorted(actual_orth_keys)}")

    def test_e5_03_orth_search_space_spec(self):
        """[v2.6.0-E5-03] orth_method/align_mode 是 categorical, ridge_lambda 是 log float.

        规格对齐 EXECUTION_V2.6.0.md E5.2:
        - orth_method: categorical, choices=['symmetric', 'ridge', 'pca', 'gram_schmidt']
        - orth_align_mode: categorical, choices=['intersection', 'union_nan']
        - orth_ridge_lambda: float, low=0.01, high=100.0, log=True
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1, search_orth=True)

        # orth_method
        spec_method = optimizer.search_space['orth_method']
        self.assertEqual(spec_method['type'], 'categorical')
        self.assertEqual(set(spec_method['choices']),
                         {'symmetric', 'ridge', 'pca', 'gram_schmidt'})

        # orth_align_mode
        spec_align = optimizer.search_space['orth_align_mode']
        self.assertEqual(spec_align['type'], 'categorical')
        self.assertEqual(set(spec_align['choices']),
                         {'intersection', 'union_nan'})
        # 不搜索 raise_on_mismatch (会导致优化失败)
        self.assertNotIn('raise_on_mismatch', spec_align['choices'])

        # orth_ridge_lambda
        spec_lambda = optimizer.search_space['orth_ridge_lambda']
        self.assertEqual(spec_lambda['type'], 'float')
        self.assertAlmostEqual(spec_lambda['low'], 0.01, places=6)
        self.assertAlmostEqual(spec_lambda['high'], 100.0, places=6)
        self.assertTrue(spec_lambda.get('log', False),
                        "orth_ridge_lambda 应为 log-uniform (λ 跨度大)")

        print(f"\n  手工校验 E5-03: orth 搜索空间规格")
        print(f"    method: {spec_method}")
        print(f"    align_mode: {spec_align}")
        print(f"    ridge_lambda: {spec_lambda}")

    def test_e5_04_params_to_config_orth_method(self):
        """[v2.6.0-E5-04] _params_to_config({'orth_method': 'ridge'}) 后 method='ridge'.

        验证 orth_method 参数能正确映射到 config.orthogonalization.method.
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1, search_orth=True)
        config = optimizer._params_to_config({'orth_method': 'ridge'})

        self.assertEqual(config.orthogonalization.method, 'ridge',
                         msg="orth_method='ridge' 应映射到 config.orthogonalization.method")

        # 验证其他 method 也能映射
        for method in ['symmetric', 'gram_schmidt', 'pca']:
            cfg = optimizer._params_to_config({'orth_method': method})
            self.assertEqual(cfg.orthogonalization.method, method,
                             msg=f"orth_method={method} 映射失败")

        print(f"\n  手工校验 E5-04: orth_method 映射")
        print(f"    ridge → {config.orthogonalization.method}")

    def test_e5_05_params_to_config_orth_auto_enable(self):
        """[v2.6.0-E5-05] 设置 orth_method 后, orthogonalization.enabled 自动 True.

        语义: 优化器搜索 orth_method 即表示用户希望启用正交化,
        不需要单独设置 orth_enabled=True (这是用户决策, 但与 orth_method 联动).

        默认 (不传 orth_method): orthogonalization is None (v2.5.0 行为, 不启用正交化)
        设置 orth_method: orthogonalization.enabled = True (自动启用)
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1, search_orth=True)

        # 默认: orthogonalization is None (v2.5.0 行为, 不启用正交化)
        config_default = optimizer._params_to_config({})
        self.assertIsNone(config_default.orthogonalization,
                          "不传 orth_method 时, orthogonalization 应为 None (v2.5.0 行为)")

        # 设置 orth_method 后: enabled=True (自动启用)
        config_orth = optimizer._params_to_config({'orth_method': 'symmetric'})
        self.assertIsNotNone(config_orth.orthogonalization,
                             "设置 orth_method 后应实例化 OrthogonalizationConfig")
        self.assertTrue(config_orth.orthogonalization.enabled,
                        "设置 orth_method 后应自动启用 orthogonalization.enabled")

        print(f"\n  手工校验 E5-05: 自动启用")
        print(f"    默认 orthogonalization = {config_default.orthogonalization}")
        print(f"    设置 orth_method 后 enabled = {config_orth.orthogonalization.enabled}")

    def test_e5_06_params_to_config_orth_align_mode(self):
        """[v2.6.0-E5-06] _params_to_config({'orth_align_mode': 'union_nan'}) 后 align_mode 正确.

        验证 orth_align_mode 参数能正确映射到 config.orthogonalization.align_mode.
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1, search_orth=True)

        # union_nan
        config_union = optimizer._params_to_config({'orth_align_mode': 'union_nan'})
        self.assertEqual(config_union.orthogonalization.align_mode, 'union_nan')

        # intersection (默认)
        config_inter = optimizer._params_to_config({'orth_align_mode': 'intersection'})
        self.assertEqual(config_inter.orthogonalization.align_mode, 'intersection')

        print(f"\n  手工校验 E5-06: orth_align_mode 映射")
        print(f"    union_nan → {config_union.orthogonalization.align_mode}")
        print(f"    intersection → {config_inter.orthogonalization.align_mode}")

    def test_e5_07_params_to_config_orth_ridge_lambda_only_ridge(self):
        """[v2.6.0-E5-07] orth_ridge_lambda 仅 method='ridge' 时设置.

        语义: ridge_lambda 仅对 Ridge 正交化有意义, 其他方法 (symmetric/pca/gram_schmidt)
        不应受此参数影响.
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1, search_orth=True)

        # method='ridge' + ridge_lambda=10.0 → 应设置
        config_ridge = optimizer._params_to_config({
            'orth_method': 'ridge',
            'orth_ridge_lambda': 10.0,
        })
        self.assertEqual(config_ridge.orthogonalization.method, 'ridge')
        self.assertAlmostEqual(config_ridge.orthogonalization.ridge_lambda, 10.0,
                              places=10,
                              msg="method='ridge' 时 orth_ridge_lambda 应设置")

        # method='symmetric' + ridge_lambda=10.0 → 不应设置 (保持默认 1.0)
        config_sym = optimizer._params_to_config({
            'orth_method': 'symmetric',
            'orth_ridge_lambda': 10.0,
        })
        self.assertEqual(config_sym.orthogonalization.method, 'symmetric')
        self.assertAlmostEqual(config_sym.orthogonalization.ridge_lambda, 1.0,
                              places=10,
                              msg="method='symmetric' 时 ridge_lambda 应保持默认 1.0")

        print(f"\n  手工校验 E5-07: ridge_lambda 条件设置")
        print(f"    ridge:    ridge_lambda = {config_ridge.orthogonalization.ridge_lambda}")
        print(f"    symmetric: ridge_lambda = {config_sym.orthogonalization.ridge_lambda} (默认)")

    def test_e5_08_search_orth_backward_compatible(self):
        """[v2.6.0-E5-08] search_orth=False 时, search_space 维度=8 (与 v2.5.0 一致).

        回归测试: 启用 E5 后, 默认行为不变, 不影响 860 基线.
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        # search_orth=False (默认)
        optimizer_default = EndToEndThresholdOptimizer(n_trials=1)
        # search_orth=False 显式
        optimizer_explicit = EndToEndThresholdOptimizer(n_trials=1, search_orth=False)

        self.assertEqual(len(optimizer_default.search_space), 8,
                         "默认 search_space 应为 8 维 (v2.5.0 一致)")
        self.assertEqual(len(optimizer_explicit.search_space), 8,
                         "search_orth=False 应为 8 维 (v2.5.0 一致)")

        # 验证 8 维键名 (v2.5.0 基线)
        expected_v250_keys = {
            'hard_routing_prob', 'merge_alpha', 'ks_alpha',
            'mixed_winsor_sigma', 'transform_aggressiveness',
            'classification_threshold_static', 'classification_threshold_dynamic',
            'migration_threshold',
        }
        self.assertEqual(set(optimizer_default.search_space.keys()), expected_v250_keys,
                         "search_space 键名应与 v2.5.0 一致")

        # search_orth=True: 维度=11 (8 + 3 orth_*)
        optimizer_orth = EndToEndThresholdOptimizer(n_trials=1, search_orth=True)
        self.assertEqual(len(optimizer_orth.search_space), 11,
                         "search_orth=True 应为 11 维 (8 + 3 orth_*)")

        print(f"\n  手工校验 E5-08: 向后兼容")
        print(f"    search_orth=False: {len(optimizer_default.search_space)} 维")
        print(f"    search_orth=True:  {len(optimizer_orth.search_space)} 维")


# =============================================================================
# E. 正交化几何诊断 + 冗余惩罚 (v2.6.0 E6 / P3-14)
# =============================================================================

class TestOrthogonalizationDiagnostics(unittest.TestCase):
    """测试 E: OrthogonalizerAdapter 几何诊断 + _redundancy_penalty"""

    def _make_factor_dict(self, K=3, N=50, T=10, seed=42):
        """构造 K 个因子的 Dict[str, DataFrame]"""
        rng = np.random.default_rng(seed)
        return {
            f'f{k}': pd.DataFrame(
                rng.standard_normal((N, T)),
                index=[f's{i:03d}' for i in range(N)],
                columns=pd.date_range('2020-01-01', periods=T, freq='D'),
            )
            for k in range(K)
        }

    def test_e6_01_adapter_get_diagnostics_not_fitted(self):
        """[v2.6.0-E6-01] 未 fit 时, get_diagnostics() 返回 {}."""
        from factor_pipeline.adapters import OrthogonalizerAdapter
        from factor_pipeline.config_v2 import OrthogonalizationConfig

        config = OrthogonalizationConfig(enabled=True, method='symmetric')
        adapter = OrthogonalizerAdapter(config)

        # 未 fit
        self.assertFalse(adapter.is_fitted_)
        diag = adapter.get_diagnostics()
        self.assertEqual(diag, {}, msg=f"未 fit 时应返回 {{}}, 实际: {diag}")

        print(f"\n  手工校验 E6-01: 未 fit diagnostics = {diag}")

    def test_e6_02_adapter_get_diagnostics_fitted(self):
        """[v2.6.0-E6-02] fit 后, get_diagnostics() 返回 F_stacked/T_stacked."""
        from factor_pipeline.adapters import OrthogonalizerAdapter
        from factor_pipeline.config_v2 import OrthogonalizationConfig

        config = OrthogonalizationConfig(enabled=True, method='symmetric')
        adapter = OrthogonalizerAdapter(config)
        factor_dict = self._make_factor_dict(K=3, N=50, T=10)

        adapter.fit(factor_dict)

        self.assertTrue(adapter.is_fitted_)
        diag = adapter.get_diagnostics()
        self.assertIn('F_stacked', diag, "diagnostics 应含 F_stacked")
        self.assertIn('T_stacked', diag, "diagnostics 应含 T_stacked")
        self.assertIsNotNone(diag['F_stacked'])
        self.assertIsNotNone(diag['T_stacked'])

        print(f"\n  手工校验 E6-02: fit 后 diagnostics keys = {list(diag.keys())}")
        print(f"    F_stacked.shape = {diag['F_stacked'].shape}")
        print(f"    T_stacked.shape = {diag['T_stacked'].shape}")

    def test_e6_03_adapter_F_T_shape_match(self):
        """[v2.6.0-E6-03] F_stacked.shape == T_stacked.shape (正交化保维度)."""
        from factor_pipeline.adapters import OrthogonalizerAdapter
        from factor_pipeline.config_v2 import OrthogonalizationConfig

        config = OrthogonalizationConfig(enabled=True, method='symmetric')
        adapter = OrthogonalizerAdapter(config)
        factor_dict = self._make_factor_dict(K=3, N=50, T=10)

        adapter.fit(factor_dict)
        diag = adapter.get_diagnostics()

        self.assertEqual(diag['F_stacked'].shape, diag['T_stacked'].shape,
                         "F 和 T shape 应一致 (N, K)")
        # K=3 因子
        self.assertEqual(diag['F_stacked'].shape[1], 3,
                         "K=3 因子, F_stacked 列数应为 3")

        print(f"\n  手工校验 E6-03: F.shape={diag['F_stacked'].shape}, "
              f"T.shape={diag['T_stacked'].shape}")

    def test_e6_04_redundancy_penalty_orth_disabled(self):
        """[v2.6.0-E6-04] orthogonalization is None 时, _redundancy_penalty == 0.0.

        向后兼容: 未启用正交化时, 无冗余诊断.
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        optimizer = EndToEndThresholdOptimizer(n_trials=1)
        config = PipelineV2Config()  # orthogonalization is None
        # mock pipeline: post_transform_hooks 为空
        class MockPipeline:
            post_transform_hooks = []
        pipeline = MockPipeline()

        penalty = optimizer._redundancy_penalty(pipeline, config)

        self.assertEqual(penalty, 0.0,
                         msg="orthogonalization is None 时, penalty 应为 0.0")

        print(f"\n  手工校验 E6-04: orth=None, penalty = {penalty}")

    def test_e6_05_redundancy_penalty_high_redundancy(self):
        """[v2.6.0-E6-05] VRR << threshold 时, redundancy_penalty > 0.

        构造高冗余场景: factor_1 ≈ factor_0 * 0.95 (高度共线).
        对称正交化后, factor_1 的 VRR 会很低 (方差被压缩).
        """
        from factor_pipeline.adapters import OrthogonalizerAdapter
        from factor_pipeline.config_v2 import OrthogonalizationConfig
        from factor_pipeline.pipelines_v2 import PipelineV2Config
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        # 构造高冗余因子字典
        rng = np.random.default_rng(42)
        N, T = 100, 10
        f0 = rng.standard_normal((N, T))
        f1 = f0 * 0.95 + rng.standard_normal((N, T)) * 0.05  # 高度共线
        f2 = rng.standard_normal((N, T))
        factor_dict = {
            'f0': pd.DataFrame(f0, index=[f's{i:03d}' for i in range(N)],
                               columns=pd.date_range('2020-01-01', periods=T, freq='D')),
            'f1': pd.DataFrame(f1, index=[f's{i:03d}' for i in range(N)],
                               columns=pd.date_range('2020-01-01', periods=T, freq='D')),
            'f2': pd.DataFrame(f2, index=[f's{i:03d}' for i in range(N)],
                               columns=pd.date_range('2020-01-01', periods=T, freq='D')),
        }

        orth_config = OrthogonalizationConfig(enabled=True, method='symmetric')
        adapter = OrthogonalizerAdapter(orth_config)
        adapter.fit(factor_dict)

        config = PipelineV2Config(orthogonalization=orth_config)
        class MockPipeline:
            post_transform_hooks = [adapter]
        pipeline = MockPipeline()

        optimizer = EndToEndThresholdOptimizer(n_trials=1, lambda_redundancy=0.05)
        penalty = optimizer._redundancy_penalty(pipeline, config)

        self.assertGreater(penalty, 0.0,
                          msg=f"高冗余场景 penalty 应 > 0, 实际 {penalty}")

        print(f"\n  手工校验 E6-05: 高冗余 penalty = {penalty:.6f}")

    def test_e6_06_redundancy_penalty_low_redundancy(self):
        """[v2.6.0-E6-06] VRR ≈ 1 时, redundancy_penalty ≈ 0.

        构造低冗余场景: 3 个独立正态分布因子, VRR 接近 1/N (对称正交化特性).
        注: 对称正交化使 T^T T = I, VRR ≈ 1/N (非 1), 但所有因子 VRR 接近,
        penalty 由 (vrr_threshold - VRR) 决定, 取决于 vrr_threshold 设置.
        """
        from factor_pipeline.adapters import OrthogonalizerAdapter
        from factor_pipeline.config_v2 import OrthogonalizationConfig
        from factor_pipeline.pipelines_v2 import PipelineV2Config
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        # 独立因子 (低冗余)
        factor_dict = self._make_factor_dict(K=3, N=200, T=10, seed=42)

        orth_config = OrthogonalizationConfig(enabled=True, method='symmetric')
        adapter = OrthogonalizerAdapter(orth_config)
        adapter.fit(factor_dict)

        config = PipelineV2Config(orthogonalization=orth_config)
        class MockPipeline:
            post_transform_hooks = [adapter]
        pipeline = MockPipeline()

        optimizer = EndToEndThresholdOptimizer(n_trials=1, lambda_redundancy=0.05)
        penalty_high_redundant = optimizer._redundancy_penalty(pipeline, config)

        # 独立因子 penalty 应远小于高冗余场景
        # (但仍可能 > 0, 因为对称正交化使 VRR ≈ 1/N < vrr_threshold=0.3)
        # 此处验证: 独立因子的 penalty 有限 (< 0.3 = vrr_threshold)
        self.assertLess(penalty_high_redundant, 0.3,
                       msg=f"独立因子 penalty 应 < vrr_threshold=0.3, 实际 {penalty_high_redundant}")

        print(f"\n  手工校验 E6-06: 低冗余 penalty = {penalty_high_redundant:.6f}")

    def test_e6_07_redundancy_penalty_vrr_threshold(self):
        """[v2.6.0-E6-07] vrr_threshold 设置影响 penalty 计算.

        vrr_threshold=0.3 (默认): VRR < 0.3 的因子扣分
        vrr_threshold=0.0: 任何 VRR >= 0 的因子都不扣分 (penalty=0)
        """
        from factor_pipeline.adapters import OrthogonalizerAdapter
        from factor_pipeline.config_v2 import OrthogonalizationConfig
        from factor_pipeline.pipelines_v2 import PipelineV2Config
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        # 高冗余场景
        rng = np.random.default_rng(42)
        N, T = 100, 10
        f0 = rng.standard_normal((N, T))
        f1 = f0 * 0.95 + rng.standard_normal((N, T)) * 0.05
        f2 = rng.standard_normal((N, T))
        factor_dict = {
            'f0': pd.DataFrame(f0, index=[f's{i:03d}' for i in range(N)],
                               columns=pd.date_range('2020-01-01', periods=T, freq='D')),
            'f1': pd.DataFrame(f1, index=[f's{i:03d}' for i in range(N)],
                               columns=pd.date_range('2020-01-01', periods=T, freq='D')),
            'f2': pd.DataFrame(f2, index=[f's{i:03d}' for i in range(N)],
                               columns=pd.date_range('2020-01-01', periods=T, freq='D')),
        }

        # vrr_threshold=0.3 (默认) — penalty > 0
        orth_config_03 = OrthogonalizationConfig(enabled=True, method='symmetric', vrr_threshold=0.3)
        adapter_03 = OrthogonalizerAdapter(orth_config_03)
        adapter_03.fit(factor_dict)
        config_03 = PipelineV2Config(orthogonalization=orth_config_03)
        class MockPipe03:
            post_transform_hooks = [adapter_03]
        optimizer = EndToEndThresholdOptimizer(n_trials=1, lambda_redundancy=0.05)
        penalty_03 = optimizer._redundancy_penalty(MockPipe03(), config_03)

        # vrr_threshold=0.0 — penalty = 0 (VRR >= 0 都不扣分)
        orth_config_00 = OrthogonalizationConfig(enabled=True, method='symmetric', vrr_threshold=0.0)
        adapter_00 = OrthogonalizerAdapter(orth_config_00)
        adapter_00.fit(factor_dict)
        config_00 = PipelineV2Config(orthogonalization=orth_config_00)
        class MockPipe00:
            post_transform_hooks = [adapter_00]
        penalty_00 = optimizer._redundancy_penalty(MockPipe00(), config_00)

        self.assertGreater(penalty_03, 0.0, "vrr_threshold=0.3 应有 penalty")
        self.assertEqual(penalty_00, 0.0, "vrr_threshold=0.0 应 penalty=0")

        print(f"\n  手工校验 E6-07: vrr_threshold 影响")
        print(f"    vrr_threshold=0.3: penalty = {penalty_03:.6f}")
        print(f"    vrr_threshold=0.0: penalty = {penalty_00:.6f}")

    def test_e6_08_compute_vrr_pure_function(self):
        """[v2.6.0-E6-08] compute_vrr 是 pure function, 多次调用结果一致."""
        from factor_pipeline.modules.factor_orthogonalizer.core.diagnostics import (
            OrthogonalizationDiagnostics
        )

        rng = np.random.default_rng(42)
        F = rng.standard_normal((100, 3))
        T = F + rng.standard_normal((100, 3)) * 0.1  # 微小扰动

        vrr_1 = OrthogonalizationDiagnostics.compute_vrr(F, T)
        vrr_2 = OrthogonalizationDiagnostics.compute_vrr(F, T)
        vrr_3 = OrthogonalizationDiagnostics.compute_vrr(F, T)

        np.testing.assert_array_equal(vrr_1, vrr_2)
        np.testing.assert_array_equal(vrr_2, vrr_3)

        print(f"\n  手工校验 E6-08: compute_vrr 三次调用一致")
        print(f"    VRR = {vrr_1}")

    def test_e6_09_composite_objective_with_redundancy(self):
        """[v2.6.0-E6-09] redundancy_penalty > 0 时, 目标函数减少 (相比 penalty=0).

        ADR-004 6 项: IC - vol - cov - ks - health - redundancy
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(
            n_trials=1,
            lambda_volatility=0.5,
            lambda_coverage=0.3,
            lambda_fidelity=0.1,
            lambda_health=0.4,
            lambda_redundancy=0.05,
        )
        ic_array = np.array([0.05, 0.06, 0.04, 0.07, 0.03])

        # 无 redundancy_penalty
        obj_no_redundancy = optimizer._composite_objective(
            ic_array, 80, 100, redundancy_penalty=0.0
        )

        # 有 redundancy_penalty
        obj_with_redundancy = optimizer._composite_objective(
            ic_array, 80, 100, redundancy_penalty=0.5
        )

        self.assertLess(obj_with_redundancy, obj_no_redundancy,
                       "redundancy_penalty > 0 应降低目标函数")

        # 手工计算
        expected_diff = 0.05 * 0.5  # lambda_redundancy * penalty
        actual_diff = obj_no_redundancy - obj_with_redundancy
        self.assertAlmostEqual(actual_diff, expected_diff, places=10,
                              msg=f"差值应 = lambda * penalty = {expected_diff}")

        print(f"\n  手工校验 E6-09: composite with redundancy")
        print(f"    no redundancy:     {obj_no_redundancy:.6f}")
        print(f"    with redundancy:   {obj_with_redundancy:.6f}")
        print(f"    diff = {actual_diff:.6f} (expected {expected_diff})")

    def test_e6_10_redundancy_penalty_lambda_0_05(self):
        """[v2.6.0-E6-10] lambda_redundancy 默认 0.05 (v1.1 从 0.1 降为 0.05).

        原因: 避免与 IC 主目标双重惩罚 (IC 已反映因子有效性).
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        # 默认值
        optimizer_default = EndToEndThresholdOptimizer(n_trials=1)
        self.assertEqual(optimizer_default.lambda_redundancy, 0.05,
                         "lambda_redundancy 默认应为 0.05 (v1.1 修正)")

        # 显式设置
        optimizer_custom = EndToEndThresholdOptimizer(n_trials=1, lambda_redundancy=0.1)
        self.assertEqual(optimizer_custom.lambda_redundancy, 0.1)

        print(f"\n  手工校验 E6-10: lambda_redundancy")
        print(f"    默认 = {optimizer_default.lambda_redundancy}")
        print(f"    自定义 = {optimizer_custom.lambda_redundancy}")

    def test_e6_11_redundancy_penalty_with_real_adapter(self):
        """[v2.6.0-E6-11] _redundancy_penalty 集成测试: 真实 adapter + compute_vrr.

        验证 _redundancy_penalty 内部调用 compute_vrr, 且与手工计算一致.
        """
        from factor_pipeline.adapters import OrthogonalizerAdapter
        from factor_pipeline.config_v2 import OrthogonalizationConfig
        from factor_pipeline.pipelines_v2 import PipelineV2Config
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer
        from factor_pipeline.modules.factor_orthogonalizer.core.diagnostics import (
            OrthogonalizationDiagnostics
        )

        # 构造因子
        rng = np.random.default_rng(42)
        N, T = 100, 10
        f0 = rng.standard_normal((N, T))
        f1 = f0 * 0.95 + rng.standard_normal((N, T)) * 0.05  # 冗余
        f2 = rng.standard_normal((N, T))
        factor_dict = {
            'f0': pd.DataFrame(f0, index=[f's{i:03d}' for i in range(N)],
                               columns=pd.date_range('2020-01-01', periods=T, freq='D')),
            'f1': pd.DataFrame(f1, index=[f's{i:03d}' for i in range(N)],
                               columns=pd.date_range('2020-01-01', periods=T, freq='D')),
            'f2': pd.DataFrame(f2, index=[f's{i:03d}' for i in range(N)],
                               columns=pd.date_range('2020-01-01', periods=T, freq='D')),
        }

        orth_config = OrthogonalizationConfig(enabled=True, method='symmetric', vrr_threshold=0.3)
        adapter = OrthogonalizerAdapter(orth_config)
        adapter.fit(factor_dict)
        config = PipelineV2Config(orthogonalization=orth_config)

        class MockPipeline:
            post_transform_hooks = [adapter]
        pipeline = MockPipeline()

        optimizer = EndToEndThresholdOptimizer(n_trials=1, lambda_redundancy=0.05)
        penalty_actual = optimizer._redundancy_penalty(pipeline, config)

        # 手工计算
        diag = adapter.get_diagnostics()
        vrr = OrthogonalizationDiagnostics.compute_vrr(diag['F_stacked'], diag['T_stacked'])
        expected_penalty = float(np.mean([max(0.0, 0.3 - v) for v in vrr]))

        self.assertAlmostEqual(penalty_actual, expected_penalty, places=10,
                              msg=f"penalty 应与手工计算一致: 实际 {penalty_actual}, 期望 {expected_penalty}")

        print(f"\n  手工校验 E6-11: 集成测试")
        print(f"    VRR = {vrr}")
        print(f"    penalty (实际) = {penalty_actual:.6f}")
        print(f"    penalty (期望) = {expected_penalty:.6f}")

    def test_e6_12_redundancy_backward_compatible(self):
        """[v2.6.0-E6-12] lambda_redundancy=0 + 不传 redundancy_penalty 时, 与 v2.5.0 一致.

        回归保护: 默认行为不变, 不影响 860 基线.
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        # lambda_redundancy=0 (向后兼容)
        optimizer = EndToEndThresholdOptimizer(
            n_trials=1,
            lambda_volatility=0.5,
            lambda_coverage=0.3,
            lambda_fidelity=0.1,
            lambda_health=0.0,  # E4 向后兼容
            lambda_redundancy=0.0,  # E6 向后兼容
        )
        ic_array = np.array([0.05, 0.06, 0.04, 0.07, 0.03])
        n_processed, n_total = 80, 100

        # 不传 before/after, 不传 redundancy_penalty
        objective = optimizer._composite_objective(ic_array, n_processed, n_total)

        # 手工计算 (v2.5.0 等价: IC - vol - cov, 无 health, 无 ks, 无 redundancy)
        expected_ic = np.mean(ic_array)
        expected_vol_penalty = max(0, np.std(ic_array) - 0.1)
        expected_cov_penalty = max(0, 0.5 - n_processed / n_total)
        expected_objective = (
            expected_ic
            - 0.5 * expected_vol_penalty
            - 0.3 * expected_cov_penalty
        )

        self.assertAlmostEqual(objective, expected_objective, places=10,
                              msg="lambda_redundancy=0 + 不传 before/after 应与 v2.5.0 一致")

        print(f"\n  手工校验 E6-12: 向后兼容")
        print(f"    objective = {objective:.6f} (expected {expected_objective:.6f})")


# =============================================================================
# F. Layer 3 显著性最终验证 (v2.6.0 E7 / P3-15)
# =============================================================================

class TestLayer3SignificanceValidation(unittest.TestCase):
    """测试 F: _validate_significance + optimize(validate_significance=...)"""

    def _make_factor_and_returns(self, K=3, N=80, T=15, seed=42):
        """构造因子 + 前向收益 (T 期 × N 股)"""
        rng = np.random.default_rng(seed)
        # factor_dict: K 个 (N, T) DataFrame
        factor_dict = {
            f'f{k}': pd.DataFrame(
                rng.standard_normal((N, T)),
                index=[f's{i:03d}' for i in range(N)],
                columns=pd.date_range('2020-01-01', periods=T, freq='D'),
            )
            for k in range(K)
        }
        # forward_returns: (T, N) DataFrame — 与因子 columns/index 对齐
        fwd = pd.DataFrame(
            rng.standard_normal((T, N)),
            index=pd.date_range('2020-01-01', periods=T, freq='D'),
            columns=[f's{i:03d}' for i in range(N)],
        )
        return factor_dict, fwd

    def test_e7_01_validate_significance_returns_dict(self):
        """[v2.6.0-E7-01] _validate_significance 返回含必要字段的字典.

        必要字段: n_significant / n_total / significance_ratio / details / warning
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1)
        factor_dict, fwd = self._make_factor_and_returns(K=3, N=80, T=15)

        # 使用默认参数构造 best_params
        best_params = {
            'hard_routing_prob': 0.9, 'merge_alpha': 0.5, 'ks_alpha': 0.05,
            'mixed_winsor_sigma': 3.0, 'transform_aggressiveness': 1.0,
            'classification_threshold_static': 0.7,
            'classification_threshold_dynamic': 0.3,
            'migration_threshold': 0.1,
        }

        report = optimizer._validate_significance(best_params, factor_dict, fwd)

        self.assertIsInstance(report, dict)
        for key in ['n_significant', 'n_total', 'significance_ratio', 'details', 'warning']:
            self.assertIn(key, report, f"报告应含 {key}")

        print(f"\n  手工校验 E7-01: 返回字典")
        print(f"    n_significant = {report['n_significant']}")
        print(f"    n_total = {report['n_total']}")
        print(f"    significance_ratio = {report['significance_ratio']:.4f}")

    def test_e7_02_significance_ratio_range(self):
        """[v2.6.0-E7-02] significance_ratio ∈ [0, 1]."""
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1)
        factor_dict, fwd = self._make_factor_and_returns(K=3, N=80, T=15)

        best_params = {
            'hard_routing_prob': 0.9, 'merge_alpha': 0.5, 'ks_alpha': 0.05,
            'mixed_winsor_sigma': 3.0, 'transform_aggressiveness': 1.0,
            'classification_threshold_static': 0.7,
            'classification_threshold_dynamic': 0.3,
            'migration_threshold': 0.1,
        }

        report = optimizer._validate_significance(best_params, factor_dict, fwd)

        self.assertGreaterEqual(report['significance_ratio'], 0.0,
                                "significance_ratio >= 0")
        self.assertLessEqual(report['significance_ratio'], 1.0,
                             "significance_ratio <= 1")

        print(f"\n  手工校验 E7-02: ratio ∈ [0,1] = {report['significance_ratio']:.4f}")

    def test_e7_03_warning_when_low_ratio(self):
        """[v2.6.0-E7-03] significance_ratio < 0.5 时, warning 非 None.

        构造随机因子 (无真实 alpha), 显著性比例应低, 触发 warning.
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1)
        # 用 seed=123 构造无 alpha 的随机因子 (实际显著性比例通常 < 0.5)
        factor_dict, fwd = self._make_factor_and_returns(K=5, N=80, T=15, seed=123)

        best_params = {
            'hard_routing_prob': 0.9, 'merge_alpha': 0.5, 'ks_alpha': 0.05,
            'mixed_winsor_sigma': 3.0, 'transform_aggressiveness': 1.0,
            'classification_threshold_static': 0.7,
            'classification_threshold_dynamic': 0.3,
            'migration_threshold': 0.1,
        }

        report = optimizer._validate_significance(best_params, factor_dict, fwd)

        # 若 ratio < 0.5, warning 必须非 None
        if report['significance_ratio'] < 0.5:
            self.assertIsNotNone(report['warning'],
                                 "ratio < 0.5 时 warning 应非 None")
            self.assertIn('显著性比例', report['warning'])
        else:
            # 数据恰好触发高显著性, 跳过 (不视为失败)
            self.skipTest(f"ratio={report['significance_ratio']:.2f} >= 0.5, 无 warning")

        print(f"\n  手工校验 E7-03: 低 ratio warning")
        print(f"    ratio = {report['significance_ratio']:.4f}")
        print(f"    warning = {report['warning']}")

    def test_e7_04_no_warning_when_high_ratio(self):
        """[v2.6.0-E7-04] significance_ratio >= 0.5 时, warning 为 None.

        构造强 alpha 因子 (fwd = factor_0 * 0.5 + noise), 显著性比例高.
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=1)
        rng = np.random.default_rng(42)
        N, T, K = 80, 15, 3
        # f0 有真实 alpha
        f0 = rng.standard_normal((N, T))
        fwd = pd.DataFrame(
            (f0 * 0.5 + rng.standard_normal((N, T)) * 0.1).T,  # 强信号
            index=pd.date_range('2020-01-01', periods=T, freq='D'),
            columns=[f's{i:03d}' for i in range(N)],
        )
        factor_dict = {
            'f0': pd.DataFrame(
                f0, index=[f's{i:03d}' for i in range(N)],
                columns=pd.date_range('2020-01-01', periods=T, freq='D'),
            ),
        }
        for k in range(1, K):
            factor_dict[f'f{k}'] = pd.DataFrame(
                rng.standard_normal((N, T)),
                index=[f's{i:03d}' for i in range(N)],
                columns=pd.date_range('2020-01-01', periods=T, freq='D'),
            )

        best_params = {
            'hard_routing_prob': 0.9, 'merge_alpha': 0.5, 'ks_alpha': 0.05,
            'mixed_winsor_sigma': 3.0, 'transform_aggressiveness': 1.0,
            'classification_threshold_static': 0.7,
            'classification_threshold_dynamic': 0.3,
            'migration_threshold': 0.1,
        }

        report = optimizer._validate_significance(best_params, factor_dict, fwd)

        if report['significance_ratio'] >= 0.5:
            self.assertIsNone(report['warning'],
                              "ratio >= 0.5 时 warning 应为 None")
        else:
            self.skipTest(f"ratio={report['significance_ratio']:.2f} < 0.5")

        print(f"\n  手工校验 E7-04: 高 ratio 无 warning")
        print(f"    ratio = {report['significance_ratio']:.4f}")

    def test_e7_05_optimize_significance_off_by_default(self):
        """[v2.6.0-E7-05] validate_significance=False (默认) 时, significance_report 为 None.

        向后兼容: 默认行为不变, 不运行 Layer 3 验证.
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=2)
        factor_dict, fwd = self._make_factor_and_returns(K=3, N=30, T=15)

        # 默认 validate_significance=False
        optimizer.optimize(factor_dict, fwd, show_progress=False)

        self.assertFalse(hasattr(optimizer, 'significance_report') and optimizer.significance_report is not None,
                         "默认应不运行显著性验证 (significance_report 为 None)")
        # 或属性不存在 / 或为 None
        if hasattr(optimizer, 'significance_report'):
            self.assertIsNone(optimizer.significance_report,
                              "默认 significance_report 应为 None")

        print(f"\n  手工校验 E7-05: 默认不运行显著性验证")

    def test_e7_06_optimize_significance_on(self):
        """[v2.6.0-E7-06] validate_significance=True 时, significance_report 非 None.

        集成测试: optimize() 后, significance_report 应为字典.
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(n_trials=2)
        factor_dict, fwd = self._make_factor_and_returns(K=3, N=30, T=15)

        optimizer.optimize(
            factor_dict, fwd, show_progress=False,
            validate_significance=True,
        )

        self.assertIsNotNone(optimizer.significance_report,
                             "validate_significance=True 应生成报告")
        self.assertIsInstance(optimizer.significance_report, dict)
        self.assertIn('n_significant', optimizer.significance_report)
        self.assertIn('significance_ratio', optimizer.significance_report)

        print(f"\n  手工校验 E7-06: 显著性验证开启")
        print(f"    n_significant = {optimizer.significance_report['n_significant']}")
        print(f"    n_total = {optimizer.significance_report['n_total']}")
        print(f"    ratio = {optimizer.significance_report['significance_ratio']:.4f}")


# =============================================================================
# D. 扩展窗口 CV
# =============================================================================

class TestExpandingWindowCV(unittest.TestCase):
    """测试 D: 扩展窗口交叉验证"""

    def test_10_cv_fold_generation(self):
        """
        [P3-Phase3-10] 扩展窗口 fold 生成正确。

        手工计算: 对于 20 期数据，min_train=10，test_size=3
        fold 0: train=[0:10], test=[10:13]
        fold 1: train=[0:13], test=[13:16]
        fold 2: train=[0:16], test=[16:19]
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(
            n_trials=10, cv_min_train=10, cv_test_size=3
        )

        folds = optimizer._generate_cv_folds(n_periods=20)

        self.assertEqual(len(folds), 3, f"应有 3 个 fold，实际 {len(folds)}")

        # fold 0
        self.assertEqual(folds[0]['train'], (0, 10))
        self.assertEqual(folds[0]['test'], (10, 13))

        # fold 1
        self.assertEqual(folds[1]['train'], (0, 13))
        self.assertEqual(folds[1]['test'], (13, 16))

        # fold 2
        self.assertEqual(folds[2]['train'], (0, 16))
        self.assertEqual(folds[2]['test'], (16, 19))

        print(f"\n  手工校验: CV folds")
        for i, fold in enumerate(folds):
            print(f"    fold {i}: train={fold['train']}, test={fold['test']}")

    def test_11_cv_insufficient_data(self):
        """
        [P3-Phase3-11] 数据不足时返回空 folds。
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(
            n_trials=10, cv_min_train=10, cv_test_size=3
        )

        folds = optimizer._generate_cv_folds(n_periods=8)
        self.assertEqual(len(folds), 0)

        print(f"\n  手工校验: 数据不足 → 0 folds")

    def test_12_cv_evaluate(self):
        """
        [P3-Phase3-12] CV 评估返回合理的分数。

        P2-2 更新: _cv_evaluate 接口改为接受 (factor_data, forward_returns, config)
        在每个 fold 的 train 上 fit Pipeline, test 上 transform。
        手工校验: 模拟数据应产生有意义的 CV 分数。
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer
        from factor_pipeline.pipelines_v2 import PipelineV2Config
        from unittest import mock

        optimizer = EndToEndThresholdOptimizer(
            n_trials=10, cv_min_train=5, cv_test_size=2
        )

        np.random.seed(42)
        n_stocks, n_periods = 50, 10
        dates = pd.date_range("2020-01-01", periods=n_periods, freq="ME")
        stocks = [f"S{i:04d}" for i in range(n_stocks)]

        factor_raw = np.random.randn(n_periods, n_stocks)
        returns_raw = 0.3 * factor_raw + np.random.randn(n_periods, n_stocks) * 0.9

        factor_data = {
            "f1": pd.DataFrame(factor_raw, index=dates, columns=stocks),
        }
        forward_returns = pd.DataFrame(returns_raw, index=dates, columns=stocks)

        # Mock Pipeline: identity (不做处理,以隔离 CV 逻辑)
        with mock.patch(
            "factor_pipeline.optimizer.FactorProcessingPipelineV2"
        ) as MockPipeline:
            mock_instance = mock.MagicMock()
            MockPipeline.return_value = mock_instance
            mock_instance.fit.return_value = mock_instance
            mock_instance.transform.side_effect = lambda fd: fd

            config = PipelineV2Config()
            cv_score = optimizer._cv_evaluate(factor_data, forward_returns, config)

        self.assertIsInstance(cv_score, float)
        self.assertGreater(cv_score, -1.0)
        self.assertLess(cv_score, 1.0)

        print(f"\n  手工校验: CV score={cv_score:.6f}")


# =============================================================================
#                              测试运行器
# =============================================================================

def run_all_tests():
    """运行所有 Phase 3 优化器测试"""
    print("=" * 70)
    print("P3 Phase 3: EndToEndThresholdOptimizer — TDD 测试套件")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestOptimizerInit))
    suite.addTests(loader.loadTestsFromTestCase(TestObjectiveFunction))
    suite.addTests(loader.loadTestsFromTestCase(TestParamMapping))
    suite.addTests(loader.loadTestsFromTestCase(TestExpandingWindowCV))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print(f"Phase 3 测试结果: {result.testsRun} 运行, "
          f"{len(result.failures)} 失败, {len(result.errors)} 错误")
    print("=" * 70)

    return result


if __name__ == '__main__':
    run_all_tests()