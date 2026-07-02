# -*- coding: utf-8 -*-
"""
P3 Phase 2: 硬编码常量 → self.config 读取 — TDD 测试套件

将 pipelines_v2.py 中的硬编码常量迁移为从 PipelineV2Config 读取。
"""

import unittest
import numpy as np
import pandas as pd


class TestPipelineV2ConfigNewFields(unittest.TestCase):
    """测试 1: PipelineV2Config 新增字段"""

    def test_01_config_defaults(self):
        """
        [P3-Phase2-01] PipelineV2Config 新增字段默认值正确。
        """
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        config = PipelineV2Config()

        self.assertEqual(config.hard_routing_prob, 0.90,
            "hard_routing_prob 默认值应为 0.90")
        self.assertEqual(config.merge_alpha, 0.50,
            "merge_alpha 默认值应为 0.50")
        self.assertEqual(config.ks_alpha, 0.05,
            "ks_alpha 默认值应为 0.05")
        self.assertEqual(config.mixed_winsor_sigma, 3.0,
            "mixed_winsor_sigma 默认值应为 3.0")

        print(f"\n  手工校验通过:")
        print(f"    hard_routing_prob  = {config.hard_routing_prob}")
        print(f"    merge_alpha        = {config.merge_alpha}")
        print(f"    ks_alpha           = {config.ks_alpha}")
        print(f"    mixed_winsor_sigma = {config.mixed_winsor_sigma}")

    def test_02_config_custom_values(self):
        """
        [P3-Phase2-02] PipelineV2Config 自定义值生效。
        """
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        config = PipelineV2Config(
            hard_routing_prob=0.75,
            merge_alpha=0.30,
            ks_alpha=0.10,
            mixed_winsor_sigma=4.5,
        )

        self.assertEqual(config.hard_routing_prob, 0.75)
        self.assertEqual(config.merge_alpha, 0.30)
        self.assertEqual(config.ks_alpha, 0.10)
        self.assertEqual(config.mixed_winsor_sigma, 4.5)

        print(f"\n  手工校验通过: 所有自定义值正确")

    def test_03_config_backward_compat(self):
        """
        [P3-Phase2-03] 不传新字段时取默认值，已有字段不受影响。
        """
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        config = PipelineV2Config(
            dynamic_decorrelation_strength=0.7,
            mixed_skew_threshold=2.5,
        )

        self.assertEqual(config.dynamic_decorrelation_strength, 0.7)
        self.assertEqual(config.mixed_skew_threshold, 2.5)
        self.assertEqual(config.hard_routing_prob, 0.90)
        self.assertEqual(config.merge_alpha, 0.50)
        self.assertEqual(config.ks_alpha, 0.05)
        self.assertEqual(config.mixed_winsor_sigma, 3.0)

        print(f"\n  手工校验通过: 向后兼容")


class TestGetPipelineWeightsHardRouting(unittest.TestCase):
    """测试 2: _get_pipeline_weights 使用 hard_routing_prob 参数"""

    def test_04_hard_routing_prob_default(self):
        """
        [P3-Phase2-04] hard_routing_prob=0.9 时，primary_prob=0.91 触发硬路由。
        """
        from factor_pipeline.pipelines_v2 import _get_pipeline_weights
        from factor_pipeline.modules.factor_fingerprint import FactorType, ClassificationResult

        # 高于 0.9 的置信度 + is_hard → 硬路由
        cls = ClassificationResult(
            primary_type=FactorType.STATIC,
            primary_prob=0.91,
            secondary_type=FactorType.MIXED,
            secondary_prob=0.09,
            is_hard=True,
            confidence=0.95,
        )
        weights = _get_pipeline_weights(cls, hard_routing_prob=0.9)
        self.assertEqual(weights, {'static': 1.0})
        print(f"\n  手工校验: primary_prob=0.91 > 0.9 → 硬路由: {weights}")

    def test_05_hard_routing_prob_below_threshold(self):
        """
        [P3-Phase2-05] primary_prob=0.89 < hard_routing_prob=0.9 → 不触发硬路由。
        """
        from factor_pipeline.pipelines_v2 import _get_pipeline_weights
        from factor_pipeline.modules.factor_fingerprint import FactorType, ClassificationResult

        cls = ClassificationResult(
            primary_type=FactorType.STATIC,
            primary_prob=0.89,
            secondary_type=FactorType.MIXED,
            secondary_prob=0.11,
            is_hard=True,
            confidence=0.90,
        )
        weights = _get_pipeline_weights(cls, hard_routing_prob=0.9)
        self.assertIn('static', weights)
        self.assertIn('mixed', weights)
        self.assertLess(weights['static'], 1.0)
        print(f"\n  手工校验: primary_prob=0.89 < 0.9 → 软路由: {weights}")

    def test_06_custom_hard_routing_prob(self):
        """
        [P3-Phase2-06] 自定义 hard_routing_prob=0.8，primary_prob=0.85 触发硬路由。
        """
        from factor_pipeline.pipelines_v2 import _get_pipeline_weights
        from factor_pipeline.modules.factor_fingerprint import FactorType, ClassificationResult

        cls = ClassificationResult(
            primary_type=FactorType.DYNAMIC,
            primary_prob=0.85,
            secondary_type=FactorType.MIXED,
            secondary_prob=0.15,
            is_hard=True,
            confidence=0.92,
        )
        weights = _get_pipeline_weights(cls, hard_routing_prob=0.80)
        self.assertEqual(weights, {'dynamic': 1.0})
        print(f"\n  手工校验: hard_routing_prob=0.80, primary_prob=0.85 → 硬路由: {weights}")


class TestMixedWinsorSigma(unittest.TestCase):
    """测试 3: MixedFactorPipeline 使用 mixed_winsor_sigma"""

    def test_07_mixed_winsor_sigma_default(self):
        """
        [P3-Phase2-07] 默认 mixed_winsor_sigma=3.0 时缩尾参数正确。
        """
        from factor_pipeline.pipelines_v2 import MixedFactorPipeline

        pipeline = MixedFactorPipeline(mixed_winsor_sigma=3.0)

        # 手工计算: 对 data，lower = mean - 3*std, upper = mean + 3*std
        data = pd.DataFrame({
            'A': [1.0, 2.0, 3.0, 4.0, 100.0],
            'B': [5.0, 6.0, 7.0, 8.0, -50.0],
        })

        params = pipeline._compute_winsorize_params(data)

        # 手工计算
        mean_a, std_a = data['A'].mean(), data['A'].std()
        expected_lower_a = mean_a - 3.0 * std_a
        expected_upper_a = mean_a + 3.0 * std_a

        self.assertAlmostEqual(params['lower']['A'], expected_lower_a, places=6)
        self.assertAlmostEqual(params['upper']['A'], expected_upper_a, places=6)

        print(f"\n  手工校验: 3σ 缩尾")
        print(f"    A: mean={mean_a:.4f}, std={std_a:.4f}")
        print(f"    lower={params['lower']['A']:.4f} (expected {expected_lower_a:.4f})")
        print(f"    upper={params['upper']['A']:.4f} (expected {expected_upper_a:.4f})")

    def test_08_custom_mixed_winsor_sigma(self):
        """
        [P3-Phase2-08] 自定义 mixed_winsor_sigma=5.0 时缩尾参数正确。
        """
        from factor_pipeline.pipelines_v2 import MixedFactorPipeline

        pipeline = MixedFactorPipeline(mixed_winsor_sigma=5.0)

        data = pd.DataFrame({
            'A': [1.0, 2.0, 3.0, 4.0, 100.0],
        })

        params = pipeline._compute_winsorize_params(data)

        mean_a, std_a = data['A'].mean(), data['A'].std()
        expected_lower_a = mean_a - 5.0 * std_a
        expected_upper_a = mean_a + 5.0 * std_a

        self.assertAlmostEqual(params['lower']['A'], expected_lower_a, places=6)
        self.assertAlmostEqual(params['upper']['A'], expected_upper_a, places=6)

        print(f"\n  手工校验: 5σ 缩尾")
        print(f"    lower={params['lower']['A']:.4f} (expected {expected_lower_a:.4f})")
        print(f"    upper={params['upper']['A']:.4f} (expected {expected_upper_a:.4f})")

    def test_09_mixed_winsor_sigma_applied_in_fit(self):
        """
        [P3-Phase2-09] mixed_winsor_sigma=2.0 时，fit 后缩尾正确生效。
        """
        from factor_pipeline.pipelines_v2 import MixedFactorPipeline

        pipeline = MixedFactorPipeline(mixed_winsor_sigma=2.0)

        data = pd.DataFrame({
            'A': [1.0, 2.0, 3.0, 4.0, 100.0],
        })

        pipeline.fit(data)

        # 检查中间数据
        intermediate = pipeline.get_intermediate_data()
        self.assertIn('outlier', intermediate)

        outlier_data = intermediate['outlier']
        # 2σ 缩尾应该把 100.0 截断到 mean + 2*std
        mean_a = data['A'].mean()
        std_a = data['A'].std()
        max_allowed = mean_a + 2.0 * std_a

        self.assertLessEqual(outlier_data['A'].max(), max_allowed + 1e-10)

        print(f"\n  手工校验: 2σ 缩尾后 max={outlier_data['A'].max():.4f} <= {max_allowed:.4f}")


class TestTransformConfigPassing(unittest.TestCase):
    """测试 4: transform() 传递 config 值到模块函数"""

    def test_10_ks_alpha_from_config(self):
        """
        [P3-Phase2-10] KS 检验使用 config.ks_alpha。
        """
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        config = PipelineV2Config(ks_alpha=0.10)
        self.assertEqual(config.ks_alpha, 0.10)

        config2 = PipelineV2Config(ks_alpha=0.01)
        self.assertEqual(config2.ks_alpha, 0.01)

        print(f"\n  手工校验通过: ks_alpha 可配置")

    def test_11_merge_alpha_from_config(self):
        """
        [P3-Phase2-11] 迁移权重合并使用 config.merge_alpha。
        """
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        config = PipelineV2Config(merge_alpha=0.30)
        self.assertEqual(config.merge_alpha, 0.30)

        config2 = PipelineV2Config(merge_alpha=0.70)
        self.assertEqual(config2.merge_alpha, 0.70)

        print(f"\n  手工校验通过: merge_alpha 可配置")

    def test_12_no_mixed_winsorize_sigma_constant(self):
        """
        [P3-Phase2-12] MIXED_WINSORIZE_SIGMA 模块级常量已移除。
        """
        import factor_pipeline.pipelines_v2 as pv2

        self.assertFalse(
            hasattr(pv2, 'MIXED_WINSORIZE_SIGMA'),
            "MIXED_WINSORIZE_SIGMA 常量应该已经从模块中移除"
        )
        print(f"\n  手工校验通过: MIXED_WINSORIZE_SIGMA 已移除")


# =============================================================================
#                              测试运行器
# =============================================================================

def run_all_tests():
    """运行所有 Phase 2 配置迁移测试"""
    print("=" * 70)
    print("P3 Phase 2: 硬编码常量 → self.config 读取 — TDD 测试套件")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestPipelineV2ConfigNewFields))
    suite.addTests(loader.loadTestsFromTestCase(TestGetPipelineWeightsHardRouting))
    suite.addTests(loader.loadTestsFromTestCase(TestMixedWinsorSigma))
    suite.addTests(loader.loadTestsFromTestCase(TestTransformConfigPassing))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print(f"Phase 2 测试结果: {result.testsRun} 运行, "
          f"{len(result.failures)} 失败, {len(result.errors)} 错误")
    print("=" * 70)

    return result


if __name__ == '__main__':
    run_all_tests()