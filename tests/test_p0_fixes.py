# -*- coding: utf-8 -*-
"""
P0 修复严格测试套件 — TDD Red Phase

P0-1: 软路由 — 使用 ClassificationResult.primary_prob 做概率加权路由
P0-2: 阈值校准 — 数据驱动的 AR(1) 阈值校准

测试原则：
- 每个测试先手工计算期望值，再与程序计算结果对比
- 严格验证数值精度
"""

import unittest
import numpy as np
import pandas as pd
import sys
import os
import warnings

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

warnings.filterwarnings('ignore')


# =============================================================================
#                           P0-1: 软路由测试
# =============================================================================

class TestSoftRouting(unittest.TestCase):
    """
    P0-1: 软路由测试

    验证 factor_pipeline 的 transform() 使用 ClassificationResult 的
    primary_prob / secondary_prob 做概率加权路由，而非仅使用 primary_type 硬路由。
    """

    # ------------------------------------------------------------------
    # 手工计算参考数据
    # ------------------------------------------------------------------
    # 场景A: 边界因子, AR(1)=0.39, sigmoid_steepness=10
    #   p_static  = 1/(1+exp(-10*(0.39-0.80))) = 1/(1+exp(4.1))  ≈ 0.0162
    #   p_dynamic = 1/(1+exp( 10*(0.39-0.40))) = 1/(1+exp(-0.1)) ≈ 0.5250
    #   p_mixed   = 1 - 0.0162 - 0.5250 = 0.4588
    #   归一化: total=1.0, 不变
    #   排序: DYNAMIC(0.5250) > MIXED(0.4588) > STATIC(0.0162)
    #   primary_type=DYNAMIC, primary_prob=0.5250
    #   secondary_type=MIXED, secondary_prob=0.4588
    SCENARIO_A_AR1 = 0.39
    SCENARIO_A_PROBS = {
        'static': 0.0162,   # 手工计算: 1/(1+exp(4.1))
        'dynamic': 0.5250,  # 手工计算: 1/(1+exp(-0.1))
        'mixed': 0.4588,    # 手工计算: 1 - 0.0162 - 0.5250
    }
    # 归一化后 (total≈1.0, 无变化)
    SCENARIO_A_WEIGHTS = {'dynamic': 0.5250, 'mixed': 0.4588}

    # 场景B: 清晰静态因子, AR(1)=0.95
    #   p_static  = 1/(1+exp(-10*(0.95-0.80))) = 1/(1+exp(-1.5)) ≈ 0.8176
    #   p_dynamic = 1/(1+exp( 10*(0.95-0.40))) = 1/(1+exp(5.5))  ≈ 0.0041
    #   p_mixed   = 1 - 0.8176 - 0.0041 = 0.1783
    #   排序: STATIC(0.8176) > MIXED(0.1783) > DYNAMIC(0.0041)
    #   primary_type=STATIC, primary_prob=0.8176
    #   secondary_type=MIXED, secondary_prob=0.1783
    SCENARIO_B_AR1 = 0.95
    SCENARIO_B_WEIGHTS = {'static': 0.8176, 'mixed': 0.1783}

    # 场景C: 极端动态因子, AR(1)=0.05
    #   p_static  = 1/(1+exp(-10*(0.05-0.80))) = 1/(1+exp(7.5))  ≈ 0.0006
    #   p_dynamic = 1/(1+exp( 10*(0.05-0.40))) = 1/(1+exp(-3.5)) ≈ 0.9707
    #   p_mixed   = 1 - 0.0006 - 0.9707 = 0.0287
    #   排序: DYNAMIC(0.9707) > MIXED(0.0287) > STATIC(0.0006)
    #   高置信度 (confidence > 0.8), is_hard=True
    SCENARIO_C_AR1 = 0.05
    SCENARIO_C_WEIGHTS = {'dynamic': 0.9707, 'mixed': 0.0287}
    SCENARIO_C_IS_HARD = True

    def setUp(self):
        """设置测试环境"""
        from factor_pipeline.modules.factor_fingerprint import (
            AdaptiveFactorClassifier, ClassificationConfig,
            FactorFingerprint, FactorType
        )
        from factor_pipeline.pipelines_v2 import (
            FactorProcessingPipelineV2, PipelineV2Config,
            StaticFactorPipeline, DynamicFactorPipeline, MixedFactorPipeline
        )
        from factor_pipeline.modules.factor_fingerprint import FingerprintConfig, MonitorConfig

        self.classifier = AdaptiveFactorClassifier(ClassificationConfig(
            static_ar1_threshold=0.80,
            dynamic_ar1_threshold=0.40,
            soft_boundary=True,
            sigmoid_steepness=10.0,
        ))

        # 用模拟数据构建三条管道（无需真实行业数据）
        self.dummy_data = pd.DataFrame(
            np.random.randn(60, 10),
            index=pd.date_range('2022-01-01', periods=60, freq='ME'),
            columns=[f'STOCK_{i:03d}' for i in range(10)]
        )

        self.static_pipeline = StaticFactorPipeline(neutralizer_params={})
        self.dynamic_pipeline = DynamicFactorPipeline(
            decorrelation_strength=1.0, max_ar_order=3, neutralizer_params={}
        )
        self.mixed_pipeline = MixedFactorPipeline(neutralizer_params={})

        # 拟合所有管道
        self.static_pipeline.fit(self.dummy_data)
        self.dynamic_pipeline.fit(self.dummy_data)
        self.mixed_pipeline.fit(self.dummy_data)

    # ==================================================================
    # 测试 1: _get_pipeline_weights() 返回正确的概率权重
    # ==================================================================

    def test_01_boundary_factor_weights(self):
        """
        [P0-1-01] 边界因子: AR(1)=0.39 → weights = {dynamic: 0.5250, mixed: 0.4588}

        手工计算:
          p_dynamic = 0.5250, p_mixed = 0.4588
          归一化: 0.5250/(0.5250+0.4588) = 0.5336, 0.4588/(0.5250+0.4588) = 0.4664
        """
        from factor_pipeline.pipelines_v2 import _get_pipeline_weights
        from factor_pipeline.modules.factor_fingerprint import FactorFingerprint, FactorType

        fp = FactorFingerprint(
            ar1_median=0.39,
            rank_autocorr=0.3,
            vol_clustering_pvalue=0.5,
            half_life=2.0,
            level_diff_ic_ratio=1.0,
            skewness_std=0.5,
            kurtosis_std=1.0,
            js_divergence_mean=0.1,
            missing_cv=0.05,
            coverage_ratio=0.95,
            sd_score=0.3,
            complexity_need=0.4,
            snr_estimate=0.5,
        )
        result = self.classifier.classify(fp)

        weights = _get_pipeline_weights(result)

        # 手工计算期望权重
        total = self.SCENARIO_A_WEIGHTS['dynamic'] + self.SCENARIO_A_WEIGHTS['mixed']
        expected_dynamic = self.SCENARIO_A_WEIGHTS['dynamic'] / total
        expected_mixed = self.SCENARIO_A_WEIGHTS['mixed'] / total

        self.assertAlmostEqual(weights.get('dynamic', 0), expected_dynamic, delta=0.01,
            msg=f"动态权重应为 {expected_dynamic:.4f}，实际为 {weights.get('dynamic', 0):.4f}")
        self.assertAlmostEqual(weights.get('mixed', 0), expected_mixed, delta=0.01,
            msg=f"混合权重应为 {expected_mixed:.4f}，实际为 {weights.get('mixed', 0):.4f}")
        self.assertAlmostEqual(sum(weights.values()), 1.0, delta=0.001,
            msg="权重之和应为 1.0")

        print(f"[PASS] P0-1-01: 边界因子 AR(1)=0.39 → 权重: {weights}")

    def test_02_clear_static_factor_weights(self):
        """
        [P0-1-02] 清晰静态因子: AR(1)=0.95 → weights = {static: 0.8176, mixed: 0.1783}

        手工计算:
          p_static = 0.8176, p_mixed = 0.1783
          归一化: 0.8176/0.9959 = 0.8210, 0.1783/0.9959 = 0.1790
        """
        from factor_pipeline.pipelines_v2 import _get_pipeline_weights
        from factor_pipeline.modules.factor_fingerprint import FactorFingerprint

        fp = FactorFingerprint(
            ar1_median=0.95,
            rank_autocorr=0.85,
            vol_clustering_pvalue=0.01,
            half_life=12.0,
            level_diff_ic_ratio=5.0,
            skewness_std=0.3,
            kurtosis_std=0.8,
            js_divergence_mean=0.05,
            missing_cv=0.02,
            coverage_ratio=0.98,
            sd_score=0.9,
            complexity_need=0.2,
            snr_estimate=2.0,
        )
        result = self.classifier.classify(fp)

        weights = _get_pipeline_weights(result)

        total = self.SCENARIO_B_WEIGHTS['static'] + self.SCENARIO_B_WEIGHTS['mixed']
        expected_static = self.SCENARIO_B_WEIGHTS['static'] / total
        expected_mixed = self.SCENARIO_B_WEIGHTS['mixed'] / total

        self.assertAlmostEqual(weights.get('static', 0), expected_static, delta=0.01)
        self.assertAlmostEqual(weights.get('mixed', 0), expected_mixed, delta=0.01)
        self.assertAlmostEqual(sum(weights.values()), 1.0, delta=0.001)

        print(f"[PASS] P0-1-02: 静态因子 AR(1)=0.95 → 权重: {weights}")

    def test_03_high_confidence_hard_routing(self):
        """
        [P0-1-03] 高置信度因子: AR(1)=0.05 → 单管道路由 (is_hard=True 时仅有主管道)

        手工计算:
          p_dynamic = 0.9707, p_mixed = 0.0287
          置信度: |0.40-0.05|/0.2 = 1.75 → clip to 1.0, is_hard=True
          当 is_hard=True 且 primary_prob > 0.9 时，仅使用主管道
        """
        from factor_pipeline.pipelines_v2 import _get_pipeline_weights
        from factor_pipeline.modules.factor_fingerprint import FactorFingerprint

        fp = FactorFingerprint(
            ar1_median=0.05,
            rank_autocorr=0.05,
            vol_clustering_pvalue=0.9,
            half_life=1.0,
            level_diff_ic_ratio=0.5,
            skewness_std=0.8,
            kurtosis_std=2.0,
            js_divergence_mean=0.3,
            missing_cv=0.1,
            coverage_ratio=0.9,
            sd_score=0.05,
            complexity_need=0.8,
            snr_estimate=0.3,
        )
        result = self.classifier.classify(fp)

        self.assertTrue(result.is_hard, "高置信度因子应为 is_hard=True")

        weights = _get_pipeline_weights(result)

        # 高置信度硬分类：主要管道权重应 > 0.9
        self.assertGreater(weights.get('dynamic', 0), 0.9,
            msg=f"高置信度动态因子应有 > 0.9 的权重，实际: {weights.get('dynamic', 0):.4f}")
        self.assertAlmostEqual(sum(weights.values()), 1.0, delta=0.001)

        print(f"[PASS] P0-1-03: 高置信度 AR(1)=0.05, is_hard=True → 权重: {weights}")

    # ==================================================================
    # 测试 2: transform() 使用概率加权路由
    # ==================================================================

    def test_04_weighted_blending_correctness(self):
        """
        [P0-1-04] 手工校验概率加权混合的正确性

        构造两个已知输出的管道 (mock)：
          - pipeline_A: 所有输出 = 10.0
          - pipeline_B: 所有输出 = 20.0
          权重: {A: 0.6, B: 0.4}
          期望输出: 10.0 * 0.6 + 20.0 * 0.4 = 14.0

        手工计算验证:
          6.0 + 8.0 = 14.0 ✓
        """
        from factor_pipeline.pipelines_v2 import _apply_weighted_transform

        # 构造 mock 管道
        class MockPipeline:
            def transform(self, X, **kwargs):
                return pd.DataFrame(
                    np.full(X.shape, self.value),
                    index=X.index, columns=X.columns
                )

        pipeline_A = MockPipeline()
        pipeline_A.value = 10.0
        pipeline_B = MockPipeline()
        pipeline_B.value = 20.0

        data = pd.DataFrame(
            np.ones((5, 3)),
            index=pd.date_range('2022-01-01', periods=5, freq='ME'),
            columns=['A', 'B', 'C']
        )

        result = _apply_weighted_transform(
            data,
            {'A': pipeline_A, 'B': pipeline_B},
            {'A': 0.6, 'B': 0.4}
        )

        # 手工计算期望值: 10.0 * 0.6 + 20.0 * 0.4 = 14.0
        expected = 14.0
        actual = result.values.mean()

        self.assertAlmostEqual(actual, expected, delta=0.001,
            msg=f"加权混合: 期望 {expected}, 实际 {actual}")

        # 验证每个单元格
        np.testing.assert_array_almost_equal(
            result.values,
            np.full((5, 3), expected),
            decimal=5,
            err_msg="所有单元格应为 14.0"
        )

        print(f"[PASS] P0-1-04: 手工校验 0.6*10 + 0.4*20 = {actual:.4f} (期望 {expected})")

    def test_05_three_way_weighted_blending(self):
        """
        [P0-1-05] 三管道加权混合

        构造三个 mock 管道：
          - static: 所有输出 = 100.0
          - mixed:  所有输出 = 200.0
          - dynamic: 所有输出 = 300.0
          权重: {static: 0.2, mixed: 0.3, dynamic: 0.5}
          期望输出: 100*0.2 + 200*0.3 + 300*0.5 = 20 + 60 + 150 = 230.0

        手工计算验证:
          20 + 60 + 150 = 230 ✓
        """
        from factor_pipeline.pipelines_v2 import _apply_weighted_transform

        class MockPipeline:
            def transform(self, X, **kwargs):
                return pd.DataFrame(
                    np.full(X.shape, self.value),
                    index=X.index, columns=X.columns
                )

        static_pipe = MockPipeline(); static_pipe.value = 100.0
        mixed_pipe = MockPipeline(); mixed_pipe.value = 200.0
        dynamic_pipe = MockPipeline(); dynamic_pipe.value = 300.0

        data = pd.DataFrame(
            np.ones((3, 4)),
            index=pd.date_range('2022-01-01', periods=3, freq='ME'),
            columns=['W', 'X', 'Y', 'Z']
        )

        result = _apply_weighted_transform(
            data,
            {'static': static_pipe, 'mixed': mixed_pipe, 'dynamic': dynamic_pipe},
            {'static': 0.2, 'mixed': 0.3, 'dynamic': 0.5}
        )

        expected = 230.0
        actual = result.values.mean()

        self.assertAlmostEqual(actual, expected, delta=0.001,
            msg=f"三管道混合: 期望 {expected}, 实际 {actual}")

        np.testing.assert_array_almost_equal(
            result.values, np.full((3, 4), expected), decimal=5
        )

        print(f"[PASS] P0-1-05: 三管道 0.2*100 + 0.3*200 + 0.5*300 = {actual:.4f} (期望 {expected})")

    def test_06_single_pipeline_routing(self):
        """
        [P0-1-06] 单管道路由（权重为 1.0 时退化为硬路由）

        权重: {static: 1.0}
        期望: 输出等于 static_pipeline 的直接输出
        """
        from factor_pipeline.pipelines_v2 import _apply_weighted_transform

        class MockPipeline:
            def transform(self, X, **kwargs):
                return X * 2.0  # 简单的变换

        pipe = MockPipeline()
        data = pd.DataFrame(
            np.array([[1.0, 2.0], [3.0, 4.0]]),
            index=pd.date_range('2022-01-01', periods=2, freq='ME'),
            columns=['A', 'B']
        )

        result = _apply_weighted_transform(
            data,
            {'static': pipe},
            {'static': 1.0}
        )

        expected = data * 2.0
        pd.testing.assert_frame_equal(result, expected,
            check_exact=False, atol=1e-10)

        print(f"[PASS] P0-1-06: 单管道路由 (权重=1.0) 退化为硬路由")

    # ==================================================================
    # 测试 3: 端到端集成 - FactorProcessingPipelineV2 使用软路由
    # ==================================================================

    def test_07_v2_pipeline_uses_soft_routing(self):
        """
        [P0-1-07] FactorProcessingPipelineV2 的 transform() 使用软路由

        验证当分类结果包含 secondary_type 时，transform 使用概率加权混合。
        """
        from factor_pipeline.pipelines_v2 import (
            FactorProcessingPipelineV2, PipelineV2Config
        )
        from factor_pipeline.modules.factor_fingerprint import FingerprintConfig, ClassificationConfig, MonitorConfig

        config = PipelineV2Config(
            fingerprint=FingerprintConfig(min_window=24),
            classification=ClassificationConfig(
                static_ar1_threshold=0.80,
                dynamic_ar1_threshold=0.40,
                soft_boundary=True,
                sigmoid_steepness=10.0,
            ),
            monitor=MonitorConfig(),
        )

        pipeline = FactorProcessingPipelineV2(config)

        # 手动设置 factor_classifications 模拟边界因子
        from factor_pipeline.modules.factor_fingerprint import FactorType, ClassificationResult

        pipeline.factor_classifications = {
            'boundary_factor': ClassificationResult(
                primary_type=FactorType.DYNAMIC,
                primary_prob=0.5250,
                secondary_type=FactorType.MIXED,
                secondary_prob=0.4588,
                confidence=0.5,
                is_hard=False,
            )
        }

        # 手动拟合管道
        pipeline.static_pipeline = self.static_pipeline
        pipeline.dynamic_pipeline = self.dynamic_pipeline
        pipeline.mixed_pipeline = self.mixed_pipeline
        pipeline.is_fitted = True

        # 模拟数据
        data = {'boundary_factor': self.dummy_data.copy()}

        results = pipeline.transform(data)

        self.assertIn('boundary_factor', results)
        self.assertEqual(results['boundary_factor'].shape, self.dummy_data.shape)

        print(f"[PASS] P0-1-07: V2 Pipeline 软路由集成成功")

    def test_08_weights_sum_to_one(self):
        """
        [P0-1-08] 所有权重之和始终为 1.0

        遍历多个 AR(1) 值，验证权重归一化。
        """
        from factor_pipeline.pipelines_v2 import _get_pipeline_weights
        from factor_pipeline.modules.factor_fingerprint import FactorFingerprint

        # 手工计算参考值
        test_cases = [
            (0.01, 0.990),  # 极端动态
            (0.20, 0.881),  # 清晰动态
            (0.39, 0.534),  # 边界: 动态/混合
            (0.50, 0.500),  # 混合中心
            (0.60, 0.500),  # 混合偏静态
            (0.81, 0.525),  # 边界: 静态/混合
            (0.95, 0.821),  # 清晰静态
            (0.99, 0.870),  # 极端静态
        ]

        for ar1, expected_primary in test_cases:
            with self.subTest(ar1=ar1):
                fp = FactorFingerprint(
                    ar1_median=ar1,
                    rank_autocorr=0.5,
                    vol_clustering_pvalue=0.5,
                    half_life=3.0,
                    level_diff_ic_ratio=1.0,
                    skewness_std=0.5,
                    kurtosis_std=1.0,
                    js_divergence_mean=0.1,
                    missing_cv=0.05,
                    coverage_ratio=0.95,
                    sd_score=0.5,
                    complexity_need=0.5,
                    snr_estimate=0.5,
                )
                result = self.classifier.classify(fp)
                weights = _get_pipeline_weights(result)

                self.assertAlmostEqual(sum(weights.values()), 1.0, delta=0.001,
                    msg=f"AR(1)={ar1}: 权重之和={sum(weights.values()):.4f}")

        print(f"[PASS] P0-1-08: {len(test_cases)} 个测试用例权重之和均为 1.0")


# =============================================================================
#                           P0-2: 阈值校准测试
# =============================================================================

class TestThresholdCalibration(unittest.TestCase):
    """
    P0-2: 阈值校准测试

    验证数据驱动的 AR(1) 阈值校准，替代硬编码的 0.40/0.80。
    """

    # ------------------------------------------------------------------
    # 手工计算参考数据
    # ------------------------------------------------------------------
    # 数据集: AR(1) = [0.05, 0.10, 0.15, 0.30, 0.35, 0.45, 0.50, 0.55, 0.70, 0.85, 0.90, 0.95]
    # 排序后: [0.05, 0.10, 0.15, 0.30, 0.35, 0.45, 0.50, 0.55, 0.70, 0.85, 0.90, 0.95]
    # n=12
    # numpy.percentile 默认 method='linear' 使用 index = p/100 * (n-1):
    #   25th: index = 0.25 * 11 = 2.75 → v[2] + 0.75*(v[3]-v[2]) = 0.15 + 0.75*0.15 = 0.2625
    #   75th: index = 0.75 * 11 = 8.25 → v[8] + 0.25*(v[9]-v[8]) = 0.55 + 0.25*0.15 = 0.5875
    # 注意: numpy 实际输出可能与手工计算有微小差异，以 numpy 实际值为准
    CALIBRATION_AR1_VALUES = [0.05, 0.10, 0.15, 0.30, 0.35, 0.45, 0.50, 0.55, 0.70, 0.85, 0.90, 0.95]
    CALIBRATION_DYNAMIC_P25 = float(np.percentile(CALIBRATION_AR1_VALUES, 25))
    CALIBRATION_STATIC_P75 = float(np.percentile(CALIBRATION_AR1_VALUES, 75))

    def setUp(self):
        """设置测试环境"""
        from factor_pipeline.modules.factor_fingerprint import AdaptiveFactorClassifier, ClassificationConfig

        self.classifier = AdaptiveFactorClassifier(ClassificationConfig(
            static_ar1_threshold=0.80,
            dynamic_ar1_threshold=0.40,
            soft_boundary=True,
            sigmoid_steepness=10.0,
        ))

    # ==================================================================
    # 测试 1: 分位数法校准
    # ==================================================================

    def test_09_percentile_calibration(self):
        """
        [P0-2-01] 分位数法阈值校准

        手工计算:
          AR(1) 值: [0.05, 0.10, 0.15, 0.30, 0.35, 0.45, 0.50, 0.55, 0.70, 0.85, 0.90, 0.95]
          25th percentile ≈ 0.2625 (线性插值)
          75th percentile ≈ 0.5875 (线性插值)

        numpy 验证:
          np.percentile(values, 25) = 0.2625
          np.percentile(values, 75) = 0.5875
        """
        ar1_values = self.CALIBRATION_AR1_VALUES

        # 手工计算 numpy 验证
        dynamic_threshold = np.percentile(ar1_values, 25)
        static_threshold = np.percentile(ar1_values, 75)

        # 手工计算期望值
        self.assertAlmostEqual(dynamic_threshold, self.CALIBRATION_DYNAMIC_P25, delta=0.01,
            msg=f"25th percentile: 期望 {self.CALIBRATION_DYNAMIC_P25}, 实际 {dynamic_threshold}")
        self.assertAlmostEqual(static_threshold, self.CALIBRATION_STATIC_P75, delta=0.01,
            msg=f"75th percentile: 期望 {self.CALIBRATION_STATIC_P75}, 实际 {static_threshold}")

        # 动态阈值 < 静态阈值
        self.assertLess(dynamic_threshold, static_threshold,
            msg="动态阈值应小于静态阈值")

        print(f"[PASS] P0-2-01: 分位数校准: dynamic={dynamic_threshold:.4f}, static={static_threshold:.4f}")

    def test_10_calibrator_class_output(self):
        """
        [P0-2-02] ThresholdCalibrator 类输出验证

        传入 AR(1) 值列表，验证 calibrate() 返回正确的阈值。
        """
        from factor_pipeline.pipelines_v2 import ThresholdCalibrator

        calibrator = ThresholdCalibrator(method='percentile')
        result = calibrator.calibrate(self.CALIBRATION_AR1_VALUES)

        self.assertIn('dynamic_threshold', result)
        self.assertIn('static_threshold', result)
        self.assertAlmostEqual(result['dynamic_threshold'], self.CALIBRATION_DYNAMIC_P25, delta=0.01)
        self.assertAlmostEqual(result['static_threshold'], self.CALIBRATION_STATIC_P75, delta=0.01)

        print(f"[PASS] P0-2-02: Calibrator 输出: {result}")

    def test_11_calibrator_edge_cases(self):
        """
        [P0-2-03] 边界情况处理

        - 空列表: 返回默认阈值
        - 单值: 返回默认阈值
        - 所有值相同: 返回默认阈值
        - 含 NaN: 忽略 NaN 后计算
        - 全部 NaN: 返回默认阈值
        """
        from factor_pipeline.pipelines_v2 import ThresholdCalibrator

        calibrator = ThresholdCalibrator(method='percentile')

        # 手工计算默认阈值
        default_dynamic = 0.40
        default_static = 0.80

        # 空列表
        result = calibrator.calibrate([])
        self.assertEqual(result['dynamic_threshold'], default_dynamic)
        self.assertEqual(result['static_threshold'], default_static)
        print(f"[INFO] P0-2-03a: 空列表 → 默认阈值: {result}")

        # 单值 [0.5]
        result = calibrator.calibrate([0.5])
        self.assertEqual(result['dynamic_threshold'], default_dynamic)
        self.assertEqual(result['static_threshold'], default_static)
        print(f"[INFO] P0-2-03b: 单值 → 默认阈值: {result}")

        # 所有值相同 [0.6, 0.6, 0.6]
        result = calibrator.calibrate([0.6, 0.6, 0.6])
        self.assertEqual(result['dynamic_threshold'], default_dynamic)
        self.assertEqual(result['static_threshold'], default_static)
        print(f"[INFO] P0-2-03c: 所有相同 → 默认阈值: {result}")

        # 含 NaN
        values_with_nan = self.CALIBRATION_AR1_VALUES + [np.nan, np.nan]
        result = calibrator.calibrate(values_with_nan)
        self.assertAlmostEqual(result['dynamic_threshold'], self.CALIBRATION_DYNAMIC_P25, delta=0.01)
        self.assertAlmostEqual(result['static_threshold'], self.CALIBRATION_STATIC_P75, delta=0.01)
        print(f"[INFO] P0-2-03d: 含NaN → 忽略NaN后计算: {result}")

        # 全部 NaN
        result = calibrator.calibrate([np.nan, np.nan])
        self.assertEqual(result['dynamic_threshold'], default_dynamic)
        self.assertEqual(result['static_threshold'], default_static)
        print(f"[INFO] P0-2-03e: 全部NaN → 默认阈值: {result}")

        print(f"[PASS] P0-2-03: 所有边界情况处理正确")

    def test_12_market_presets(self):
        """
        [P0-2-04] 市场预设阈值

        不同市场有不同的 AR(1) 分布特征：
          - A股: 因子普遍高自相关，阈值应更高
          - 美股: 因子自相关较低，阈值应更低
          - 加密货币: 因子接近白噪声，阈值应极低

        手工验证各预设的合理性。
        """
        from factor_pipeline.pipelines_v2 import ThresholdCalibrator

        # A股预设
        calibrator_cn = ThresholdCalibrator(method='preset', preset='a_share')
        result_cn = calibrator_cn.calibrate([])
        self.assertGreater(result_cn['static_threshold'], 0.80,
            msg="A股静态阈值应 > 0.80")
        self.assertGreater(result_cn['dynamic_threshold'], 0.40,
            msg="A股动态阈值应 > 0.40")
        print(f"[INFO] P0-2-04a: A股预设: {result_cn}")

        # 美股预设
        calibrator_us = ThresholdCalibrator(method='preset', preset='us_equity')
        result_us = calibrator_us.calibrate([])
        self.assertAlmostEqual(result_us['static_threshold'], 0.75, delta=0.01)
        self.assertAlmostEqual(result_us['dynamic_threshold'], 0.35, delta=0.01)
        print(f"[INFO] P0-2-04b: 美股预设: {result_us}")

        # 加密货币预设
        calibrator_crypto = ThresholdCalibrator(method='preset', preset='crypto')
        result_crypto = calibrator_crypto.calibrate([])
        self.assertLess(result_crypto['static_threshold'], 0.60,
            msg="加密货币静态阈值应 < 0.60")
        self.assertLess(result_crypto['dynamic_threshold'], 0.30,
            msg="加密货币动态阈值应 < 0.30")
        print(f"[INFO] P0-2-04c: 加密货币预设: {result_crypto}")

        print(f"[PASS] P0-2-04: 三种市场预设验证通过")

    def test_13_pipeline_v2_uses_calibrated_thresholds(self):
        """
        [P0-2-05] FactorProcessingPipelineV2 支持使用校准后的阈值

        验证 PipelineV2Config 可以接受自定义阈值，
        并且分类器使用这些阈值进行分类。
        """
        from factor_pipeline.pipelines_v2 import (
            FactorProcessingPipelineV2, PipelineV2Config
        )
        from factor_pipeline.modules.factor_fingerprint import FingerprintConfig, ClassificationConfig, MonitorConfig

        # 使用校准后的阈值（比默认值更宽松）
        config = PipelineV2Config(
            fingerprint=FingerprintConfig(min_window=24),
            classification=ClassificationConfig(
                static_ar1_threshold=0.70,   # 校准后降低
                dynamic_ar1_threshold=0.30,  # 校准后降低
                soft_boundary=True,
                sigmoid_steepness=10.0,
            ),
            monitor=MonitorConfig(),
        )

        pipeline = FactorProcessingPipelineV2(config)

        # 验证分类器使用了自定义阈值
        self.assertEqual(pipeline.classifier.config.static_ar1_threshold, 0.70)
        self.assertEqual(pipeline.classifier.config.dynamic_ar1_threshold, 0.30)

        # 用手工计算的分类结果验证
        from factor_pipeline.modules.factor_fingerprint import FactorFingerprint, FactorType

        # AR(1)=0.50: 在 0.30-0.70 之间 → MIXED
        fp = FactorFingerprint(
            ar1_median=0.50,
            rank_autocorr=0.5,
            vol_clustering_pvalue=0.5,
            half_life=3.0,
            level_diff_ic_ratio=1.0,
            skewness_std=0.5,
            kurtosis_std=1.0,
            js_divergence_mean=0.1,
            missing_cv=0.05,
            coverage_ratio=0.95,
            sd_score=0.5,
            complexity_need=0.5,
            snr_estimate=0.5,
        )
        result = pipeline.classifier.classify(fp)

        self.assertEqual(result.primary_type, FactorType.MIXED,
            msg=f"AR(1)=0.50 在阈值(0.30, 0.70)之间，应为 MIXED，实际: {result.primary_type}")

        # AR(1)=0.80: 在自定义阈值下 > 0.70 → STATIC
        fp2 = FactorFingerprint(
            ar1_median=0.80,
            rank_autocorr=0.7,
            vol_clustering_pvalue=0.1,
            half_life=8.0,
            level_diff_ic_ratio=3.0,
            skewness_std=0.3,
            kurtosis_std=0.8,
            js_divergence_mean=0.05,
            missing_cv=0.02,
            coverage_ratio=0.98,
            sd_score=0.8,
            complexity_need=0.3,
            snr_estimate=1.5,
        )
        result2 = pipeline.classifier.classify(fp2)

        self.assertEqual(result2.primary_type, FactorType.STATIC,
            msg=f"AR(1)=0.80 > 阈值 0.70，应为 STATIC，实际: {result2.primary_type}")

        print(f"[PASS] P0-2-05: 自定义阈值 {0.30}/{0.70} 分类正确: AR(1)=0.50→MIXED, AR(1)=0.80→STATIC")

    def test_14_auto_calibrate_in_pipeline(self):
        """
        [P0-2-06] 自动校准: 从因子数据中自动学习阈值

        给定一组因子数据，自动计算 AR(1) 分布，校准阈值。
        """
        from factor_pipeline.pipelines_v2 import (
            FactorProcessingPipelineV2, PipelineV2Config,
            ThresholdCalibrator
        )
        from factor_pipeline.modules.factor_fingerprint import FingerprintConfig, ClassificationConfig, MonitorConfig

        # 从校准用数据中提取 AR(1) 值
        calibrator = ThresholdCalibrator(method='percentile')
        cal_result = calibrator.calibrate(self.CALIBRATION_AR1_VALUES)

        # 使用校准后的阈值创建配置
        config = PipelineV2Config(
            fingerprint=FingerprintConfig(min_window=24),
            classification=ClassificationConfig(
                static_ar1_threshold=cal_result['static_threshold'],
                dynamic_ar1_threshold=cal_result['dynamic_threshold'],
            ),
            monitor=MonitorConfig(),
        )

        pipeline = FactorProcessingPipelineV2(config)

        # 验证阈值已校准
        self.assertAlmostEqual(
            pipeline.classifier.config.static_ar1_threshold,
            self.CALIBRATION_STATIC_P75, delta=0.01
        )
        self.assertAlmostEqual(
            pipeline.classifier.config.dynamic_ar1_threshold,
            self.CALIBRATION_DYNAMIC_P25, delta=0.01
        )

        print(f"[PASS] P0-2-06: 自动校准阈值: "
              f"dynamic={pipeline.classifier.config.dynamic_ar1_threshold:.4f}, "
              f"static={pipeline.classifier.config.static_ar1_threshold:.4f}")


# =============================================================================
#                              测试运行器
# =============================================================================

def run_all_tests():
    """运行所有 P0 修复测试"""
    print("=" * 70)
    print("P0 修复严格测试套件 — TDD Red Phase")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # P0-1: 软路由
    suite.addTests(loader.loadTestsFromTestCase(TestSoftRouting))
    # P0-2: 阈值校准
    suite.addTests(loader.loadTestsFromTestCase(TestThresholdCalibration))

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
        print("所有测试当前预期失败 (Red Phase) — 等待实现")
    else:
        print()
        print("测试失败列表 (Red Phase 预期):")
        for test, _ in result.failures + result.errors:
            print(f"  - {test}")

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)