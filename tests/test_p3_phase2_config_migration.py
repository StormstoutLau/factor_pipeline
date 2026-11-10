# -*- coding: utf-8 -*-
"""
P3 Phase 2: 硬编码常量 → self.config 读取 — TDD 测试套件

将 pipelines_v2.py 中的硬编码常量迁移为从 PipelineV2Config 读取。
"""

import unittest
import numpy as np
import pandas as pd


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
    """测试 4: 模块级常量清理"""

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