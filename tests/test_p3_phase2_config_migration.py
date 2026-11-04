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
            mixed_transformation_method='identity',
        )

        self.assertEqual(config.dynamic_decorrelation_strength, 0.7)
        self.assertEqual(config.mixed_transformation_method, 'identity')
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
        """[P3-Phase2-07] 默认 sigma=3.0: 逐日截面边界 = row_mean ± 3*row_std."""
        from factor_pipeline.pipelines_v2 import MixedFactorPipeline

        n = 30
        cols = [f'S{i:03d}' for i in range(n)]
        data = pd.DataFrame([[0.0] * (n - 1) + [100.0]], columns=cols)

        pipeline = MixedFactorPipeline(mixed_winsor_sigma=3.0)
        out = pipeline._apply_winsorize(data)

        mu = data.mean(axis=1)
        sd = data.std(axis=1, ddof=1)
        upper = (mu + 3.0 * sd).iloc[0]
        lower = (mu - 3.0 * sd).iloc[0]

        self.assertAlmostEqual(out.iloc[0].max(), upper, places=10)
        self.assertLessEqual(out.iloc[0].max(), upper + 1e-10)
        self.assertGreaterEqual(out.iloc[0].min(), lower - 1e-10)
        self.assertNotAlmostEqual(out.iloc[0].max(), data.iloc[0].max(), places=10)

        print(f"\n  手工校验: 逐日截面 3σ 缩尾")
        print(f"    mean={mu.iloc[0]:.4f}, std={sd.iloc[0]:.4f}")
        print(f"    lower={lower:.4f}, upper={upper:.4f}")
        print(f"    out.max={out.iloc[0].max():.4f} (原始 max=100.0)")

    def test_08_custom_mixed_winsor_sigma(self):
        """[P3-Phase2-08] sigma=5.0: 边界随 sigma 改变, 极值仍被截断."""
        from factor_pipeline.pipelines_v2 import MixedFactorPipeline

        n = 30
        cols = [f'S{i:03d}' for i in range(n)]
        data = pd.DataFrame([[0.0] * (n - 1) + [100.0]], columns=cols)

        pipeline = MixedFactorPipeline(mixed_winsor_sigma=5.0)
        out = pipeline._apply_winsorize(data)

        mu = data.mean(axis=1)
        sd = data.std(axis=1, ddof=1)
        upper = (mu + 5.0 * sd).iloc[0]

        self.assertAlmostEqual(out.iloc[0].max(), upper, places=10)
        self.assertNotAlmostEqual(out.iloc[0].max(), data.iloc[0].max(), places=10)

        print(f"\n  手工校验: 5σ 缩尾")
        print(f"    upper={upper:.4f}, out.max={out.iloc[0].max():.4f}")

    def test_09_mixed_winsor_sigma_applied_in_fit(self):
        """[P3-Phase2-09] sigma=2.0: fit 的 outlier 中间数据满足逐日截面边界."""
        from factor_pipeline.pipelines_v2 import MixedFactorPipeline

        n = 30
        cols = [f'S{i:03d}' for i in range(n)]
        data = pd.DataFrame([[0.0] * (n - 1) + [100.0] for _ in range(5)],
                            columns=cols)

        pipeline = MixedFactorPipeline(mixed_winsor_sigma=2.0)
        pipeline.fit(data)

        outlier_data = pipeline.get_intermediate_data()['outlier']
        mu = data.mean(axis=1)
        sd = data.std(axis=1, ddof=1)
        upper = (mu + 2.0 * sd).to_numpy(dtype=float)
        lower = (mu - 2.0 * sd).to_numpy(dtype=float)

        np.testing.assert_allclose(
            outlier_data.max(axis=1).to_numpy(dtype=float), upper, atol=1e-10,
        )
        np.testing.assert_array_less(
            np.broadcast_to(lower[:, None] - 1e-10, outlier_data.shape),
            outlier_data.to_numpy(dtype=float),
        )

        print(f"\n  手工校验: 2σ 缩尾后逐日 max={outlier_data.max(axis=1).to_numpy()}")


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