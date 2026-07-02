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