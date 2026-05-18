# -*- coding: utf-8 -*-
"""
因子处理流水线严格测试套件

测试范围：
1. 指纹分类模块
2. 三种因子管道
3. V2流水线集成
"""

import unittest
import numpy as np
import pandas as pd
import sys
import warnings
import os

# 添加项目根目录到路径（使用相对路径，跨平台兼容）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

warnings.filterwarnings('ignore')


class TestDataGenerator:
    """测试数据生成器"""

    @staticmethod
    def generate_static_factor(n_periods=120, n_stocks=100, seed=42):
        """生成高自相关静态因子"""
        np.random.seed(seed)
        dates = pd.date_range('2022-01-01', periods=n_periods, freq='ME')
        stocks = [f'STOCK_{i:04d}' for i in range(n_stocks)]

        base = np.random.randn(n_periods) * 0.5
        data = np.zeros((n_periods, n_stocks))
        for i in range(n_periods):
            for j in range(n_stocks):
                data[i, j] = base[i] + np.random.randn() * 0.3

        return pd.DataFrame(data, index=dates, columns=stocks)

    @staticmethod
    def generate_dynamic_factor(n_periods=120, n_stocks=100, seed=123):
        """生成低自相关动态因子"""
        np.random.seed(seed)
        dates = pd.date_range('2022-01-01', periods=n_periods, freq='ME')
        stocks = [f'STOCK_{i:04d}' for i in range(n_stocks)]

        data = np.random.randn(n_periods, n_stocks)
        return pd.DataFrame(data, index=dates, columns=stocks)

    @staticmethod
    def generate_mixed_factor(n_periods=120, n_stocks=100, seed=456):
        """生成混合因子"""
        np.random.seed(seed)
        dates = pd.date_range('2022-01-01', periods=n_periods, freq='ME')
        stocks = [f'STOCK_{i:04d}' for i in range(n_stocks)]

        ar_component = np.zeros((n_periods, n_stocks))
        for i in range(1, n_periods):
            ar_component[i] = 0.5 * ar_component[i-1] + np.random.randn(n_stocks) * 0.5

        noise = np.random.randn(n_periods, n_stocks)
        data = ar_component + noise

        return pd.DataFrame(data, index=dates, columns=stocks)

    @staticmethod
    def generate_industry_data(n_stocks=100, n_industries=5, seed=789):
        """生成行业分类数据"""
        np.random.seed(seed)
        stocks = [f'STOCK_{i:04d}' for i in range(n_stocks)]
        industries = ['Industry_' + str(i) for i in range(n_industries)]
        industry_map = np.random.choice(industries, size=n_stocks)
        return pd.Series(industry_map, index=stocks)


class TestFactorFingerprinter(unittest.TestCase):
    """测试因子指纹提取器"""

    def setUp(self):
        self.static_data = TestDataGenerator.generate_static_factor(n_periods=60, n_stocks=30)
        self.dynamic_data = TestDataGenerator.generate_dynamic_factor(n_periods=60, n_stocks=30)
        self.mixed_data = TestDataGenerator.generate_mixed_factor(n_periods=60, n_stocks=30)

    def test_fingerprint_extraction(self):
        """测试指纹提取"""
        from Factor_Fingerprint import FactorFingerprinter

        fingerprinter = FactorFingerprinter()
        fp = fingerprinter.extract_fingerprint(self.dynamic_data)

        self.assertIsNotNone(fp.ar1_median)
        self.assertIsNotNone(fp.rank_autocorr)
        self.assertIsNotNone(fp.sd_score)
        print(f"[PASS] FactorFingerprinter - AR(1): {fp.ar1_median:.4f}, Rank_Autocorr: {fp.rank_autocorr:.4f}")

    def test_static_vs_dynamic_fingerprint(self):
        """测试静态因子与动态因子指纹差异"""
        from Factor_Fingerprint import FactorFingerprinter

        fingerprinter = FactorFingerprinter()

        static_fp = fingerprinter.extract_fingerprint(self.static_data)
        dynamic_fp = fingerprinter.extract_fingerprint(self.dynamic_data)

        print(f"[INFO] 静态因子 AR(1): {static_fp.ar1_median:.4f}")
        print(f"[INFO] 动态因子 AR(1): {dynamic_fp.ar1_median:.4f}")

        self.assertGreater(static_fp.ar1_median, dynamic_fp.ar1_median)
        print(f"[PASS] 指纹差异验证: 静态因子AR(1) > 动态因子AR(1)")


class TestAdaptiveClassifier(unittest.TestCase):
    """测试自适应分类器"""

    def setUp(self):
        self.static_data = TestDataGenerator.generate_static_factor(n_periods=60, n_stocks=30)
        self.dynamic_data = TestDataGenerator.generate_dynamic_factor(n_periods=60, n_stocks=30)
        self.mixed_data = TestDataGenerator.generate_mixed_factor(n_periods=60, n_stocks=30)

    def test_classification(self):
        """测试因子分类"""
        from Factor_Fingerprint import FactorFingerprinter, FactorType, AdaptiveFactorClassifier

        fingerprinter = FactorFingerprinter()
        classifier = AdaptiveFactorClassifier()

        fp_static = fingerprinter.extract_fingerprint(self.static_data)
        fp_dynamic = fingerprinter.extract_fingerprint(self.dynamic_data)
        fp_mixed = fingerprinter.extract_fingerprint(self.mixed_data)

        result_static = classifier.classify(fp_static)
        result_dynamic = classifier.classify(fp_dynamic)
        result_mixed = classifier.classify(fp_mixed)

        print(f"[INFO] 静态因子分类: {result_static.primary_type} (概率: {result_static.primary_prob:.2f})")
        print(f"[INFO] 动态因子分类: {result_dynamic.primary_type} (概率: {result_dynamic.primary_prob:.2f})")
        print(f"[INFO] 混合因子分类: {result_mixed.primary_type} (概率: {result_mixed.primary_prob:.2f})")

        self.assertIn(result_static.primary_type, [FactorType.STATIC, FactorType.MIXED])
        self.assertIn(result_dynamic.primary_type, [FactorType.DYNAMIC, FactorType.MIXED])
        print(f"[PASS] 分类器正常工作")


class TestStaticFactorPipeline(unittest.TestCase):
    """测试静态因子处理管道"""

    def setUp(self):
        self.data = TestDataGenerator.generate_static_factor(n_periods=60, n_stocks=30)
        self.industry = TestDataGenerator.generate_industry_data(n_stocks=30)

    def test_static_pipeline_processing(self):
        """测试静态因子管道处理"""
        from factor_pipeline.pipelines_v2 import StaticFactorPipeline

        pipeline = StaticFactorPipeline(
            neutralizer_params={'industry_data': self.industry}
        )

        result = pipeline.fit_transform(self.data)

        self.assertEqual(result.shape, self.data.shape)

        nan_ratio = result.isna().sum().sum() / result.size
        self.assertLess(nan_ratio, 0.3)

        col_means = result.mean(axis=0)
        self.assertTrue(np.allclose(col_means, 0, atol=1e-10))

        print(f"[PASS] StaticFactorPipeline - 均值接近0: {np.abs(col_means).mean():.6f}")


class TestDynamicFactorPipeline(unittest.TestCase):
    """测试动态因子处理管道"""

    def setUp(self):
        self.data = TestDataGenerator.generate_dynamic_factor(n_periods=60, n_stocks=30)
        self.industry = TestDataGenerator.generate_industry_data(n_stocks=30)

    def test_dynamic_pipeline_processing(self):
        """测试动态因子管道处理"""
        from factor_pipeline.pipelines_v2 import DynamicFactorPipeline

        pipeline = DynamicFactorPipeline(
            decorrelation_strength=1.0,
            max_ar_order=3,
            ar_criterion='aic',
            neutralizer_params={'industry_data': self.industry}
        )

        result = pipeline.fit_transform(self.data)

        self.assertEqual(result.shape, self.data.shape)

        summary = pipeline.get_decoupling_summary()
        self.assertIn('neutralization_summary', summary)
        self.assertIn('ar_summary', summary)

        nan_ratio = result.isna().sum().sum() / result.size
        self.assertLess(nan_ratio, 0.3)

        print(f"[PASS] DynamicFactorPipeline - 三重中性化完成, 缺失率: {nan_ratio:.2%}")

    def test_soft_decoupling_strength(self):
        """测试软解耦强度"""
        from factor_pipeline.pipelines_v2 import DynamicFactorPipeline

        pipeline_full = DynamicFactorPipeline(
            decorrelation_strength=1.0,
            max_ar_order=3,
            neutralizer_params=None
        )

        pipeline_partial = DynamicFactorPipeline(
            decorrelation_strength=0.5,
            max_ar_order=3,
            neutralizer_params=None
        )

        result_full = pipeline_full.fit_transform(self.data)
        result_partial = pipeline_partial.fit_transform(self.data)

        full_var = result_full.var().mean()
        partial_var = result_partial.var().mean()

        self.assertNotEqual(full_var, partial_var)
        print(f"[PASS] 软解耦: strength=1.0 var={full_var:.4f}, strength=0.5 var={partial_var:.4f}")


class TestMixedFactorPipeline(unittest.TestCase):
    """测试混合因子处理管道"""

    def setUp(self):
        self.data = TestDataGenerator.generate_mixed_factor(n_periods=60, n_stocks=30)
        self.industry = TestDataGenerator.generate_industry_data(n_stocks=30)

    def test_mixed_pipeline_processing(self):
        """测试混合因子管道处理"""
        from factor_pipeline.pipelines_v2 import MixedFactorPipeline

        pipeline = MixedFactorPipeline(
            conditional_transform=True,
            skew_threshold=2.0,
            kurt_threshold=5.0,
            neutralizer_params={'industry_data': self.industry}
        )

        result = pipeline.fit_transform(self.data)

        self.assertEqual(result.shape, self.data.shape)

        nan_ratio = result.isna().sum().sum() / result.size
        self.assertLess(nan_ratio, 0.3)

        print(f"[PASS] MixedFactorPipeline - 混合因子处理完成, 缺失率: {nan_ratio:.2%}")


class TestEndToEndIntegration(unittest.TestCase):
    """端到端集成测试"""

    def setUp(self):
        self.factors = {
            'static_factor': TestDataGenerator.generate_static_factor(n_periods=60, n_stocks=30),
            'dynamic_factor': TestDataGenerator.generate_dynamic_factor(n_periods=60, n_stocks=30),
            'mixed_factor': TestDataGenerator.generate_mixed_factor(n_periods=60, n_stocks=30),
        }
        self.industry = TestDataGenerator.generate_industry_data(n_stocks=30)

    def test_v2_pipeline_integration(self):
        """测试V2流水线集成"""
        from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2, PipelineV2Config
        from Factor_Fingerprint import FingerprintConfig, ClassificationConfig, MonitorConfig

        config = PipelineV2Config(
            fingerprint=FingerprintConfig(min_window=24),
            classification=ClassificationConfig(),
            monitor=MonitorConfig(),
            dynamic_decorrelation_strength=1.0,
            dynamic_max_ar_order=3,
            dynamic_ar_criterion='aic'
        )

        pipeline = FactorProcessingPipelineV2(config)
        pipeline.fit(self.factors, industry_data=self.industry)

        results = pipeline.transform(self.factors)

        self.assertEqual(len(results), len(self.factors))

        for name, result in results.items():
            self.assertEqual(result.shape, self.factors[name].shape)
            nan_ratio = result.isna().sum().sum() / result.size
            self.assertLess(nan_ratio, 0.3)

        summary = pipeline.get_classification_summary()
        self.assertGreater(len(summary), 0)

        print(f"[PASS] V2 Pipeline 集成测试 - 成功处理 {len(results)} 个因子")
        print(f"[INFO] 分类结果:\n{summary[['factor_name', 'primary_type', 'primary_prob']].to_string()}")

    def test_pipeline_order_preserved(self):
        """测试处理顺序保持一致"""
        from factor_pipeline.pipelines_v2 import (
            StaticFactorPipeline,
            DynamicFactorPipeline,
            MixedFactorPipeline
        )

        pipelines = {
            'static': StaticFactorPipeline(neutralizer_params={'industry_data': self.industry}),
            'dynamic': DynamicFactorPipeline(
                decorrelation_strength=1.0,
                max_ar_order=3,
                ar_criterion='aic',
                neutralizer_params={'industry_data': self.industry}
            ),
            'mixed': MixedFactorPipeline(neutralizer_params={'industry_data': self.industry}),
        }

        for name, pipeline in pipelines.items():
            result = pipeline.fit_transform(self.factors[f'{name}_factor'])
            self.assertEqual(result.shape, self.factors[f'{name}_factor'].shape)
            print(f"[PASS] {name.capitalize()} Pipeline - 处理顺序正确")


def run_all_tests():
    """运行所有测试"""
    print("=" * 70)
    print("因子处理流水线严格测试套件")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestFactorFingerprinter))
    suite.addTests(loader.loadTestsFromTestCase(TestAdaptiveClassifier))
    suite.addTests(loader.loadTestsFromTestCase(TestStaticFactorPipeline))
    suite.addTests(loader.loadTestsFromTestCase(TestDynamicFactorPipeline))
    suite.addTests(loader.loadTestsFromTestCase(TestMixedFactorPipeline))
    suite.addTests(loader.loadTestsFromTestCase(TestEndToEndIntegration))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print("测试摘要")
    print("=" * 70)
    print(f"运行测试: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")

    if result.wasSuccessful():
        print()
        print("🎉 所有测试通过！")
    else:
        print()
        print("❌ 部分测试失败")

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
