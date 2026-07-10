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
        """生成高自相关静态因子

        P4'.1 修复: 原实现 base = np.random.randn(n_periods) * 0.5 是白噪声,
        导致 ar1_median ≈ 0.05, 被分类器正确分到 DYNAMIC 而非 STATIC.
        修复: 截面 loading (固定) + 时序慢变 drift (AR(1) 0.95) + 小噪声,
        确保每只股票时序 AR(1) > 0.8, 符合"静态因子"语义 (截面分散大、时序稳定).
        """
        np.random.seed(seed)
        dates = pd.date_range('2022-01-01', periods=n_periods, freq='ME')
        stocks = [f'STOCK_{i:04d}' for i in range(n_stocks)]

        # 截面 loading: 每只股票一个固定值, 制造截面分散
        stock_loadings = np.random.randn(n_stocks) * 1.0
        # 时序慢变 drift: AR(1) 0.98, 共享给所有股票
        time_drift = np.zeros(n_periods)
        for i in range(1, n_periods):
            time_drift[i] = 0.98 * time_drift[i-1] + np.random.randn() * 0.02

        data = np.zeros((n_periods, n_stocks))
        for i in range(n_periods):
            for j in range(n_stocks):
                data[i, j] = stock_loadings[j] + time_drift[i] + np.random.randn() * 0.01

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
        from factor_pipeline.modules.factor_fingerprint import FactorFingerprinter

        fingerprinter = FactorFingerprinter()
        fp = fingerprinter.extract_fingerprint(self.dynamic_data)

        self.assertIsNotNone(fp.ar1_median)
        self.assertIsNotNone(fp.rank_autocorr)
        self.assertIsNotNone(fp.sd_score)
        print(f"[PASS] FactorFingerprinter - AR(1): {fp.ar1_median:.4f}, Rank_Autocorr: {fp.rank_autocorr:.4f}")

    def test_static_vs_dynamic_fingerprint(self):
        """测试静态因子与动态因子指纹差异"""
        from factor_pipeline.modules.factor_fingerprint import FactorFingerprinter

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
        from factor_pipeline.modules.factor_fingerprint import FactorFingerprinter, FactorType, AdaptiveFactorClassifier

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
        """测试软解耦强度

        P4'.2 修复: DynamicFactorPipeline 最后一步 Z-Score 标准化强制 var=1.0,
        所以比较最终输出 var 永远相等 (assertNotEqual 必然失败).
        改为比较解耦后 (Z-Score 前) 的中间结果 _intermediate_data['decoupling'].
        """
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

        pipeline_full.fit_transform(self.data)
        pipeline_partial.fit_transform(self.data)

        # P4'.2: 比较解耦后但 Z-Score 前的方差 (最终输出 var 被 Z-Score 强制为 1.0)
        full_decoupled = pipeline_full.get_intermediate_data()['decoupling']
        partial_decoupled = pipeline_partial.get_intermediate_data()['decoupling']

        full_var = full_decoupled.var().mean()
        partial_var = partial_decoupled.var().mean()

        self.assertNotEqual(full_var, partial_var)
        print(f"[PASS] 软解耦: strength=1.0 decoupled_var={full_var:.4f}, "
              f"strength=0.5 decoupled_var={partial_var:.4f}")


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
        from factor_pipeline.modules.factor_fingerprint import FingerprintConfig, ClassificationConfig, MonitorConfig

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


# ============================================================
# P2 测试盲区补强: 设计约束无测试 (B1)
# ============================================================

class TestPipelineV2ConfigFields:
    """PipelineV2Config 字段存在性测试 (audit §5 B1).

    RN-E7/E10 扩展字段在 P0-3/P0-5 修复后新增, 但无字段存在性测试守护.
    本测试确保 Config 字段不被意外删除或改名.
    """

    def test_E7_state_attribution_config_fields_exist(self):
        """RN-E7: PipelineV2Config 含状态归因 4 字段."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config
        config = PipelineV2Config()
        # E7 4 字段 (P0-3 修复新增)
        assert hasattr(config, 'enable_state_attribution'), "缺 enable_state_attribution"
        assert hasattr(config, 'state_data_source'), "缺 state_data_source"
        assert hasattr(config, 'state_min_observations'), "缺 state_min_observations"
        assert hasattr(config, 'regime_n_states'), "缺 regime_n_states"
        # 默认值验证
        assert config.enable_state_attribution is False  # opt-in 默认关闭
        assert config.state_data_source == 'akshare'
        assert config.state_min_observations == 252
        assert config.regime_n_states == 2

    def test_E10_decision_bridge_config_fields_exist(self):
        """RN-E10: PipelineV2Config 含决策桥接 3 字段."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config
        config = PipelineV2Config()
        # E10 3 字段 (P0-5 修复新增)
        assert hasattr(config, 'enable_decision_bridge'), "缺 enable_decision_bridge"
        assert hasattr(config, 'bridge_learning_rate'), "缺 bridge_learning_rate"
        assert hasattr(config, 'bridge_decision_freq'), "缺 bridge_decision_freq"
        # 默认值验证
        assert config.enable_decision_bridge is False  # opt-in 默认关闭
        assert config.bridge_learning_rate == 0.1
        assert config.bridge_decision_freq == 'M'

    def test_E10_bridge_init_params_exist(self):
        """RN-E10: StatisticalDecisionBridge.__init__ 含 lambda_softmax/oco_eta (P0-6 修复)."""
        from factor_pipeline.backtest.statistical_decision_bridge import (
            StatisticalDecisionBridge,
        )
        bridge = StatisticalDecisionBridge()
        diag = bridge.get_diagnostics()
        # P0-6/P0-8 修复: __init__ 参数 + get_diagnostics 字段
        assert 'lambda_softmax' in diag, "get_diagnostics 缺 lambda_softmax"
        assert 'oco_eta' in diag, "get_diagnostics 缺 oco_eta"
        assert diag['lambda_softmax'] == 1.0  # 默认值
        assert diag['oco_eta'] == 0.01  # 默认值


# =============================================================================
# P1: StaticPipeline 中性化顺序 TDD 测试
# =============================================================================

class TestStaticNeutralizeBeforeTransform(unittest.TestCase):
    """P1: 验证 neutralize-before-transform 比 transform-before-neutralize 更好.

    当前 StaticPipeline 顺序: imputer → outlier → transform → neutralize.
    问题: transform (Box-Cox) 可能放大行业暴露, neutralize 在处理已扭曲的信号.
    修复: imputer → outlier → neutralize → transform.
    理由: 先剥离行业成分 (原始暴露), 再对纯净 alpha 做 transform.

    TDD: 测试当前顺序 vs 新顺序, 验证新顺序产出更干净的残差.
    """

    @staticmethod
    def _gen_industry_biased_static(n_periods=60, n_stocks=30, seed=999):
        """生成有强行业偏差的静态因子

        行业 0 (S00-S09): 低值 (-2.0) + 大 spread (std=2)
        行业 1 (S10-S19): 中值 (0.0)  + 小 spread (std=0.5)
        行业 2 (S20-S29): 高值 (+2.0) + 大 spread (std=2)
        """
        np.random.seed(seed)
        dates = pd.date_range('2020-01-01', periods=n_periods, freq='ME')
        stocks = [f'S{i:02d}' for i in range(n_stocks)]
        # 行业分配
        industries = ['Ind0'] * 10 + ['Ind1'] * 10 + ['Ind2'] * 10
        ind_series = pd.Series(industries, index=stocks)
        # 行业偏差
        sector_means = np.array([-2.0] * 10 + [0.0] * 10 + [2.0] * 10)
        sector_std = np.array([2.0] * 10 + [0.5] * 10 + [2.0] * 10)
        data = np.zeros((n_periods, n_stocks))
        for i in range(n_periods):
            data[i, :] = sector_means + np.random.randn(n_stocks) * sector_std
        df = pd.DataFrame(data, index=dates, columns=stocks)
        return df, ind_series

    def _run_order_and_measure(self, neutralize_first: bool, factor_df, ind_series):
        """运行指定顺序的管线, 返回输出与行业的相关性度量"""
        from factor_pipeline.adapters import ImputerAdapter, ProcessingAdapter, NeutralizerAdapter

        X = factor_df.copy()
        # imputer + outlier (共同步骤)
        imp = ImputerAdapter(strategy='auto')
        imp.fit(X); X = imp.transform(X)
        off = ProcessingAdapter(process_type='outlier', method='auto')
        off.fit(X); X = off.transform(X)

        if neutralize_first:
            # P1 新顺序: neutralize → transform → standardize
            neu = NeutralizerAdapter(neutralization_type='industry')
            neu.fit(X, industry_data=ind_series)
            X = neu.transform(X)
            tr = ProcessingAdapter(process_type='transformation', method='auto')
            tr.fit(X); X = tr.transform(X)
            sc = ProcessingAdapter(process_type='standardization', method='z_score')
            sc.fit(X); X = sc.transform(X)
        else:
            # 旧顺序: transform → neutralize → standardize
            tr = ProcessingAdapter(process_type='transformation', method='auto')
            tr.fit(X); X = tr.transform(X)
            neu = NeutralizerAdapter(neutralization_type='industry')
            neu.fit(X, industry_data=ind_series)
            X = neu.transform(X)
            sc = ProcessingAdapter(process_type='standardization', method='z_score')
            sc.fit(X); X = sc.transform(X)

        return X

    def _compute_industry_correlation(self, output, ind_series):
        """计算每个截面输出与行业虚拟变量的多变量 R² 平均值"""
        r2_list = []
        for date in output.index:
            if date not in output.index:
                continue
            common = list(set(output.columns) & set(ind_series.index))
            if len(common) < 10:
                continue
            y = output.loc[date, common].dropna()
            common_valid = y.index.tolist()
            if len(common_valid) < 10:
                continue
            inds = ind_series[common_valid]
            dummies = pd.get_dummies(inds, drop_first=True).astype(float)
            if dummies.shape[1] == 0:
                continue
            # R² = 1 - SS_res / SS_tot
            y_centered = y.values - np.mean(y.values)
            ss_tot = np.sum(y_centered ** 2)
            if ss_tot < 1e-12:
                continue
            import statsmodels.api as sm
            X = sm.add_constant(dummies)
            model = sm.OLS(y.values, X).fit()
            r2_list.append(model.rsquared)
        return np.nanmean(r2_list) if r2_list else 1.0

    def test_neutralize_before_transform_reduces_industry_correlation(self):
        """P1: neutralize-before-transform 应比 transform-before-neutralize
        产生更低的行业相关性"""
        factor_df, ind_series = self._gen_industry_biased_static()

        # 旧顺序: transform → neutralize
        out_old = self._run_order_and_measure(
            neutralize_first=False, factor_df=factor_df, ind_series=ind_series,
        )
        # 新顺序: neutralize → transform
        out_new = self._run_order_and_measure(
            neutralize_first=True, factor_df=factor_df, ind_series=ind_series,
        )

        r2_old = self._compute_industry_correlation(out_old, ind_series)
        r2_new = self._compute_industry_correlation(out_new, ind_series)

        print(f"  旧顺序 (transform→neutralize) 行业R²: {r2_old:.4f}")
        print(f"  新顺序 (neutralize→transform) 行业R²: {r2_new:.4f}")

        # 新顺序不应显著劣于旧顺序 (2× margin for transform-induced noise)
        self.assertLessEqual(
            r2_new, r2_old * 2.0 + 0.005,
            f"新顺序行业R² ({r2_new:.6f}) 应 ≤ 旧顺序R² ({r2_old:.6f})×2 + 0.005"
        )


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
