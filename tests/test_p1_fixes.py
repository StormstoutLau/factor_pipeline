# -*- coding: utf-8 -*-
"""
P1 修复严格测试套件 — TDD Red Phase

P1-5: transition_weights 接入路由层
P1-3: 统一三条管道 fit() 实现风格
P1-4: 适配器回退时发出 Warning

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
#                P1-5: transition_weights 接入路由层
# =============================================================================

class TestTransitionWeightsRouting(unittest.TestCase):
    """
    P1-5: 将 monitor.get_transition_weights() 接入路由层

    当因子处于类型迁移期时，使用指数衰减平滑的过渡权重，
    避免硬切换导致的不连续输出。
    """

    # ------------------------------------------------------------------
    # 手工计算参考数据
    # ------------------------------------------------------------------
    # 模拟迁移历史: STATIC(t-5), STATIC(t-4), MIXED(t-3), MIXED(t-2), DYNAMIC(t-1)
    # 指数衰减: decay=0.7, 越近的权重越高
    #   t-5 (STATIC):  w = 0.7^4 = 0.2401
    #   t-4 (STATIC):  w = 0.7^3 = 0.3430
    #   t-3 (MIXED):   w = 0.7^2 = 0.4900
    #   t-2 (MIXED):   w = 0.7^1 = 0.7000
    #   t-1 (DYNAMIC): w = 0.7^0 = 1.0000
    #   总权重: 0.2401 + 0.3430 + 0.4900 + 0.7000 + 1.0000 = 2.7731
    #   归一化:
    #     STATIC:  (0.2401 + 0.3430) / 2.7731 = 0.5831 / 2.7731 = 0.2103
    #     MIXED:   (0.4900 + 0.7000) / 2.7731 = 1.1900 / 2.7731 = 0.4291
    #     DYNAMIC: 1.0000 / 2.7731 = 0.3606
    MIGRATION_WEIGHTS = {
        'static': 0.2103,
        'mixed': 0.4291,
        'dynamic': 0.3606,
    }

    def setUp(self):
        """设置测试环境"""
        from factor_pipeline.modules.factor_fingerprint import (
            FactorFingerprintMonitor, FactorFingerprint, FactorType, ClassificationResult
        )
        from factor_pipeline.pipelines_v2 import (
            FactorProcessingPipelineV2, PipelineV2Config,
            StaticFactorPipeline, DynamicFactorPipeline, MixedFactorPipeline
        )
        from factor_pipeline.modules.factor_fingerprint import FingerprintConfig, ClassificationConfig, MonitorConfig

        self.dummy_data = pd.DataFrame(
            np.random.randn(60, 10),
            index=pd.date_range('2022-01-01', periods=60, freq='ME'),
            columns=[f'S{i:03d}' for i in range(10)]
        )

        self.static_pipeline = StaticFactorPipeline(neutralizer_params={})
        self.dynamic_pipeline = DynamicFactorPipeline(
            decorrelation_strength=1.0, max_ar_order=3, neutralizer_params={}
        )
        self.mixed_pipeline = MixedFactorPipeline(neutralizer_params={})
        self.static_pipeline.fit(self.dummy_data)
        self.dynamic_pipeline.fit(self.dummy_data)
        self.mixed_pipeline.fit(self.dummy_data)

    # ==================================================================
    # 测试 1: transition_weights 手工计算验证
    # ==================================================================

    def test_15_transition_weights_manual_calc(self):
        """
        [P1-5-01] 手工验证指数衰减过渡权重

        迁移历史: STATIC→STATIC→MIXED→MIXED→DYNAMIC (最近5期)
        decay=0.7, 期望: static=0.2103, mixed=0.4291, dynamic=0.3606

        手工计算:
          t-5 (STATIC):   0.7^4 = 0.2401
          t-4 (STATIC):   0.7^3 = 0.3430
          t-3 (MIXED):    0.7^2 = 0.4900
          t-2 (MIXED):    0.7^1 = 0.7000
          t-1 (DYNAMIC):  0.7^0 = 1.0000
          total = 2.7731
          static  = (0.2401+0.3430)/2.7731 = 0.2103
          mixed   = (0.4900+0.7000)/2.7731 = 0.4291
          dynamic = 1.0000/2.7731 = 0.3606
        """
        from factor_pipeline.modules.factor_fingerprint import FactorFingerprintMonitor, FactorType
        from factor_pipeline.modules.factor_fingerprint import MonitorConfig

        # 启用平滑过渡
        config = MonitorConfig(enable_smooth_transition=True)
        monitor = FactorFingerprintMonitor(config)

        # 手工设置迁移历史
        from factor_pipeline.modules.factor_fingerprint import FactorFingerprint, ClassificationResult, AdaptiveFactorClassifier

        # 模拟5期分类历史
        monitor.classification_history['test_factor'] = [
            ClassificationResult(primary_type=FactorType.STATIC, primary_prob=0.9,
                                 secondary_type=FactorType.MIXED, secondary_prob=0.08,
                                 confidence=0.9, is_hard=False),
            ClassificationResult(primary_type=FactorType.STATIC, primary_prob=0.85,
                                 secondary_type=FactorType.MIXED, secondary_prob=0.12,
                                 confidence=0.85, is_hard=False),
            ClassificationResult(primary_type=FactorType.MIXED, primary_prob=0.6,
                                 secondary_type=FactorType.STATIC, secondary_prob=0.35,
                                 confidence=0.6, is_hard=False),
            ClassificationResult(primary_type=FactorType.MIXED, primary_prob=0.7,
                                 secondary_type=FactorType.DYNAMIC, secondary_prob=0.25,
                                 confidence=0.7, is_hard=False),
            ClassificationResult(primary_type=FactorType.DYNAMIC, primary_prob=0.55,
                                 secondary_type=FactorType.MIXED, secondary_prob=0.40,
                                 confidence=0.55, is_hard=False),
        ]
        monitor.fingerprint_history['test_factor'] = [
            FactorFingerprint(ar1_median=0.9, rank_autocorr=0.8, vol_clustering_pvalue=0.01,
                              half_life=10.0, level_diff_ic_ratio=4.0, skewness_std=0.3,
                              kurtosis_std=0.8, js_divergence_mean=0.05, missing_cv=0.02,
                              coverage_ratio=0.98, sd_score=0.85, complexity_need=0.2, snr_estimate=2.0),
        ] * 5

        fp = FactorFingerprint(ar1_median=0.4, rank_autocorr=0.3, vol_clustering_pvalue=0.5,
                               half_life=3.0, level_diff_ic_ratio=1.5, skewness_std=0.5,
                               kurtosis_std=1.2, js_divergence_mean=0.15, missing_cv=0.05,
                               coverage_ratio=0.95, sd_score=0.4, complexity_need=0.5, snr_estimate=0.8)

        weights = monitor.get_transition_weights('test_factor', fp)

        # 手工计算
        decay = 0.7
        w_manual = {
            FactorType.STATIC: (decay**4 + decay**3),
            FactorType.MIXED: (decay**2 + decay**1),
            FactorType.DYNAMIC: (decay**0),
        }
        total = sum(w_manual.values())
        expected = {t: w / total for t, w in w_manual.items()}

        self.assertAlmostEqual(weights.get(FactorType.STATIC, 0), expected[FactorType.STATIC], delta=0.01)
        self.assertAlmostEqual(weights.get(FactorType.MIXED, 0), expected[FactorType.MIXED], delta=0.01)
        self.assertAlmostEqual(weights.get(FactorType.DYNAMIC, 0), expected[FactorType.DYNAMIC], delta=0.01)
        self.assertAlmostEqual(sum(weights.values()), 1.0, delta=0.001)

        print(f"[PASS] P1-5-01: 迁移权重: {weights}")

    def test_16_no_migration_returns_single_weight(self):
        """
        [P1-5-02] 无迁移时返回单权重 {current_type: 1.0}

        最近3期类型一致 → 无迁移 → 权重 = {current_type: 1.0}
        """
        from factor_pipeline.modules.factor_fingerprint import FactorFingerprintMonitor, FactorType
        from factor_pipeline.modules.factor_fingerprint import MonitorConfig, FactorFingerprint, ClassificationResult

        config = MonitorConfig(enable_smooth_transition=True)
        monitor = FactorFingerprintMonitor(config)

        monitor.classification_history['stable_factor'] = [
            ClassificationResult(primary_type=FactorType.STATIC, primary_prob=0.9,
                                 secondary_type=FactorType.MIXED, secondary_prob=0.08,
                                 confidence=0.9, is_hard=False),
            ClassificationResult(primary_type=FactorType.STATIC, primary_prob=0.92,
                                 secondary_type=FactorType.MIXED, secondary_prob=0.06,
                                 confidence=0.92, is_hard=False),
            ClassificationResult(primary_type=FactorType.STATIC, primary_prob=0.88,
                                 secondary_type=FactorType.MIXED, secondary_prob=0.10,
                                 confidence=0.88, is_hard=False),
        ]
        monitor.fingerprint_history['stable_factor'] = [
            FactorFingerprint(ar1_median=0.9, rank_autocorr=0.8, vol_clustering_pvalue=0.01,
                              half_life=10.0, level_diff_ic_ratio=4.0, skewness_std=0.3,
                              kurtosis_std=0.8, js_divergence_mean=0.05, missing_cv=0.02,
                              coverage_ratio=0.98, sd_score=0.85, complexity_need=0.2, snr_estimate=2.0),
        ] * 3

        fp = FactorFingerprint(ar1_median=0.9, rank_autocorr=0.8, vol_clustering_pvalue=0.01,
                               half_life=10.0, level_diff_ic_ratio=4.0, skewness_std=0.3,
                               kurtosis_std=0.8, js_divergence_mean=0.05, missing_cv=0.02,
                               coverage_ratio=0.98, sd_score=0.85, complexity_need=0.2, snr_estimate=2.0)

        weights = monitor.get_transition_weights('stable_factor', fp)

        self.assertEqual(len(weights), 1)
        self.assertEqual(list(weights.keys())[0], FactorType.STATIC)
        self.assertEqual(list(weights.values())[0], 1.0)

        print(f"[PASS] P1-5-02: 稳定因子权重={weights}")

    def test_17_pipeline_merges_transition_weights(self):
        """
        [P1-5-03] Pipeline 合并分类权重和迁移权重

        当 monitor 检测到迁移时，transform() 使用迁移权重替代分类权重。
        手工验证：迁移权重被正确转换为管道权重字符串键。
        """
        from factor_pipeline.modules.factor_fingerprint import FactorType, ClassificationResult
        from factor_pipeline.pipelines_v2 import (
            FactorProcessingPipelineV2, PipelineV2Config,
            _merge_transition_weights
        )
        from factor_pipeline.modules.factor_fingerprint import FingerprintConfig, ClassificationConfig, MonitorConfig

        # 手工计算
        # 分类权重: {dynamic: 0.55, mixed: 0.40} (归一化后)
        # 迁移权重: {DYNAMIC: 0.36, MIXED: 0.43, STATIC: 0.21}
        # 合并策略: 加权平均 (alpha=0.5)
        #   static:  0.5*0.00 + 0.5*0.21 = 0.105
        #   mixed:   0.5*0.42 + 0.5*0.43 = 0.425
        #   dynamic: 0.5*0.58 + 0.5*0.36 = 0.470
        #   total = 1.0

        cls_weights = {'dynamic': 0.55 / (0.55 + 0.40), 'mixed': 0.40 / (0.55 + 0.40)}
        trans_weights = {
            FactorType.STATIC: 0.21,
            FactorType.MIXED: 0.43,
            FactorType.DYNAMIC: 0.36,
        }

        merged = _merge_transition_weights(cls_weights, trans_weights, alpha=0.5)

        # 手工计算期望
        expected_static = 0.5 * 0.0 + 0.5 * 0.21  # = 0.105
        expected_mixed = 0.5 * cls_weights['mixed'] + 0.5 * 0.43
        expected_dynamic = 0.5 * cls_weights['dynamic'] + 0.5 * 0.36

        self.assertAlmostEqual(merged.get('static', 0), expected_static, delta=0.01)
        self.assertAlmostEqual(merged.get('mixed', 0), expected_mixed, delta=0.01)
        self.assertAlmostEqual(merged.get('dynamic', 0), expected_dynamic, delta=0.01)
        self.assertAlmostEqual(sum(merged.values()), 1.0, delta=0.001)

        print(f"[PASS] P1-5-03: 合并权重: cls={cls_weights}, trans={trans_weights}")
        print(f"          合并结果: {merged}")

    def test_18_transition_disabled_uses_classification_only(self):
        """
        [P1-5-04] 禁用平滑过渡时仅使用分类权重

        enable_smooth_transition=False → 忽略迁移权重
        """
        from factor_pipeline.modules.factor_fingerprint import FactorType, ClassificationResult
        from factor_pipeline.pipelines_v2 import (
            _merge_transition_weights
        )

        cls_weights = {'static': 0.8, 'mixed': 0.2}
        trans_weights = {FactorType.DYNAMIC: 1.0}

        # alpha=0 表示完全忽略迁移权重
        merged = _merge_transition_weights(cls_weights, trans_weights, alpha=0.0)

        self.assertEqual(merged, cls_weights)
        print(f"[PASS] P1-5-04: alpha=0.0 → 仅分类权重: {merged}")


# =============================================================================
#                P1-3: 统一三条管道 fit() 实现风格
# =============================================================================

class TestUnifiedFitPattern(unittest.TestCase):
    """
    P1-3: 统一三条管道的 fit() 实现风格

    当前问题:
    - StaticFactorPipeline.fit(): 使用 fit_transform 链式模式
    - DynamicFactorPipeline.fit(): 手动管理中间数据
    - MixedFactorPipeline.fit(): 不同的中间数据传递方式

    目标:
    - 三条管道都支持 get_intermediate_data() 方法
    - 每条管道都记录 fit 阶段的中间状态
    """

    def setUp(self):
        """设置测试环境"""
        self.data = pd.DataFrame(
            np.random.seed(42) or np.random.randn(50, 15),
            index=pd.date_range('2022-01-01', periods=50, freq='ME'),
            columns=[f'S{i:03d}' for i in range(15)]
        )
        # 添加一些缺失值
        self.data.iloc[0:3, 0:2] = np.nan
        self.data.iloc[10, 3:5] = np.nan
        # 添加一些极值
        self.data.iloc[5, 0] = 50.0
        self.data.iloc[20, 1] = -30.0

    # ==================================================================
    # 测试 1: StaticFactorPipeline fit() 中间状态
    # ==================================================================

    def test_19_static_pipeline_intermediate_data(self):
        """
        [P1-3-01] StaticFactorPipeline 记录中间数据

        期望: fit() 后可通过 get_intermediate_data() 访问每步输出
        """
        from factor_pipeline.pipelines_v2 import StaticFactorPipeline

        pipeline = StaticFactorPipeline(neutralizer_params={})
        pipeline.fit(self.data)

        # 验证中间数据可用
        intermediate = pipeline.get_intermediate_data()
        self.assertIsInstance(intermediate, dict)
        self.assertGreater(len(intermediate), 0,
            msg=f"StaticPipeline 应记录中间数据，实际: {len(intermediate)} 步")

        # 验证每步数据形状正确
        for step_name, step_data in intermediate.items():
            if isinstance(step_data, pd.DataFrame):
                self.assertEqual(step_data.shape, self.data.shape,
                    msg=f"步骤 {step_name} 数据形状应为 {self.data.shape}，实际: {step_data.shape}")

        # 验证步骤顺序
        expected_steps = ['imputer', 'outlier', 'transform', 'neutralize', 'standardize']
        for step in expected_steps:
            self.assertIn(step, intermediate,
                msg=f"StaticPipeline 应包含 {step} 步骤")

        print(f"[PASS] P1-3-01: StaticPipeline 中间数据: {list(intermediate.keys())}")

    def test_20_dynamic_pipeline_intermediate_data(self):
        """
        [P1-3-02] DynamicFactorPipeline 记录中间数据

        期望: fit() 后可通过 get_intermediate_data() 访问每步输出
        """
        from factor_pipeline.pipelines_v2 import DynamicFactorPipeline

        pipeline = DynamicFactorPipeline(
            decorrelation_strength=1.0, max_ar_order=3, neutralizer_params={}
        )
        pipeline.fit(self.data)

        intermediate = pipeline.get_intermediate_data()
        self.assertIsInstance(intermediate, dict)
        self.assertGreater(len(intermediate), 0)

        expected_steps = ['imputation', 'decoupling']
        for step in expected_steps:
            self.assertIn(step, intermediate,
                msg=f"DynamicPipeline 应包含 {step} 步骤")

        print(f"[PASS] P1-3-02: DynamicPipeline 中间数据: {list(intermediate.keys())}")

    def test_21_mixed_pipeline_intermediate_data(self):
        """
        [P1-3-03] MixedFactorPipeline 记录中间数据

        期望: fit() 后可通过 get_intermediate_data() 访问每步输出
        """
        from factor_pipeline.pipelines_v2 import MixedFactorPipeline

        pipeline = MixedFactorPipeline(neutralizer_params={})
        pipeline.fit(self.data)

        intermediate = pipeline.get_intermediate_data()
        self.assertIsInstance(intermediate, dict)
        self.assertGreater(len(intermediate), 0)

        expected_steps = ['imputation', 'outlier']
        for step in expected_steps:
            self.assertIn(step, intermediate,
                msg=f"MixedPipeline 应包含 {step} 步骤")

        print(f"[PASS] P1-3-03: MixedPipeline 中间数据: {list(intermediate.keys())}")

    def test_22_all_pipelines_same_fit_signature(self):
        """
        [P1-3-04] 三条管道 fit() 签名一致

        验证 fit() 接受相同的参数格式。
        """
        from factor_pipeline.pipelines_v2 import (
            StaticFactorPipeline, DynamicFactorPipeline, MixedFactorPipeline
        )

        pipelines = [
            StaticFactorPipeline(neutralizer_params={}),
            DynamicFactorPipeline(max_ar_order=3, neutralizer_params={}),
            MixedFactorPipeline(neutralizer_params={}),
        ]

        for pipeline in pipelines:
            # 相同的 fit 调用方式
            result = pipeline.fit(self.data)
            self.assertIsNotNone(result,
                msg=f"{pipeline.__class__.__name__}.fit() 应返回 self")

            # 验证中间数据可访问
            intermediate = pipeline.get_intermediate_data()
            self.assertIsInstance(intermediate, dict,
                msg=f"{pipeline.__class__.__name__} 中间数据应为 dict")

        print(f"[PASS] P1-3-04: 三条管道 fit() 签名一致")

    def test_23_intermediate_data_consistency(self):
        """
        [P1-3-05] 中间数据一致性检查

        手工验证: StaticPipeline 的 imputation 输出应该缺失率更低
        """
        from factor_pipeline.pipelines_v2 import StaticFactorPipeline

        pipeline = StaticFactorPipeline(neutralizer_params={})
        pipeline.fit(self.data)

        intermediate = pipeline.get_intermediate_data()

        if 'imputation' in intermediate:
            imp_data = intermediate['imputation']
            if isinstance(imp_data, pd.DataFrame):
                missing_before = self.data.isna().sum().sum()
                missing_after = imp_data.isna().sum().sum()
                self.assertLess(missing_after, missing_before,
                    msg=f"插补后缺失值应减少: before={missing_before}, after={missing_after}")
                print(f"[INFO] P1-3-05: 插补前缺失={missing_before}, 插补后缺失={missing_after}")


# =============================================================================
#                P1-4: 适配器回退 Warning
# =============================================================================

class TestAdapterFallbackWarnings(unittest.TestCase):
    """
    P1-4: 适配器回退时发出 Warning

    当前问题: 适配器在找不到外部子模块时静默降级，
    用户不知道数据被"简单中位数"处理了。

    目标: 所有回退路径发出 UserWarning，并在报告中标记降级模式。
    """

    def setUp(self):
        """设置测试数据"""
        self.data = pd.DataFrame(
            np.random.seed(123) or np.random.randn(30, 10),
            index=pd.date_range('2022-01-01', periods=30, freq='ME'),
            columns=[f'S{i:03d}' for i in range(10)]
        )
        self.data.iloc[0:3, 0:2] = np.nan

    # ==================================================================
    # 测试 1: ImputerAdapter 回退警告
    # ==================================================================

    def test_24_imputer_adapter_fallback_warning(self):
        """
        [P1-4-01] ImputerAdapter REQUIRED 依赖缺失时抛 AdapterImportError

        P2.4 更新: factor-imputer 现为 REQUIRED 依赖, 不再静默回退。
        手工验证: 当外部 Imputer 不可用时，构造函数抛 AdapterImportError。
        """
        from factor_pipeline.adapters import ImputerAdapter
        from factor_pipeline.exceptions import AdapterImportError

        # P2.4: REQUIRED 依赖缺失时抛 AdapterImportError, 不再回退
        with self.assertRaises(AdapterImportError, msg="REQUIRED 依赖缺失应抛 AdapterImportError"):
            adapter = ImputerAdapter(
                strategy='auto',
                module_path='../NonExistent/Module',
                import_path='does.not.exist',
                class_name='NonExistentClass'
            )

        print(f"[PASS] P1-4-01: ImputerAdapter REQUIRED 缺失抛 AdapterImportError (P2.4)")

    def test_25_processing_adapter_fallback_warning(self):
        """
        [P1-4-02] ProcessingAdapter REQUIRED 依赖缺失时抛 AdapterImportError

        P2.4 更新: factor-adaptive-winsor 现为 REQUIRED 依赖, 不再静默回退。
        手工验证: 当外部处理器不可用时，构造函数抛 AdapterImportError。
        """
        from factor_pipeline.adapters import ProcessingAdapter
        from factor_pipeline.exceptions import AdapterImportError

        for ptype in ['outlier', 'transformation', 'standardization']:
            with self.subTest(process_type=ptype):
                # P2.4: REQUIRED 依赖缺失时抛 AdapterImportError, 不再回退
                with self.assertRaises(AdapterImportError,
                                       msg=f"{ptype} REQUIRED 依赖缺失应抛 AdapterImportError"):
                    adapter = ProcessingAdapter(
                        process_type=ptype,
                        method='auto',
                        module_path='../NonExistent/Module',
                        import_path='does.not.exist',
                        class_name='NonExistentClass'
                    )

        print(f"[PASS] P1-4-02: ProcessingAdapter 三种子类型 REQUIRED 缺失抛 AdapterImportError (P2.4)")

    def test_26_neutralizer_adapter_fallback_warning(self):
        """
        [P1-4-03] NeutralizerAdapter REQUIRED 依赖缺失时抛 AdapterImportError

        P3.2 更新: factor-neutralizer 现为 REQUIRED 依赖, 不再静默回退。
        手工验证: 当外部 Neutralizer 不可用时，构造函数抛 AdapterImportError。
        """
        from factor_pipeline.adapters import NeutralizerAdapter
        from factor_pipeline.exceptions import AdapterImportError

        # P3.2: REQUIRED 依赖缺失时抛 AdapterImportError, 不再回退
        with self.assertRaises(AdapterImportError, msg="REQUIRED 依赖缺失应抛 AdapterImportError"):
            adapter = NeutralizerAdapter(
                module_path='../NonExistent/Module',
                import_path='does.not.exist',
                class_name='NonExistentClass'
            )

        print(f"[PASS] P1-4-03: NeutralizerAdapter REQUIRED 缺失抛 AdapterImportError (P3.2)")

    def test_27_garch_adapter_fallback_warning(self):
        """
        [P1-4-04] GarchWhiteningAdapter 回退时发出 Warning

        手工验证: 当 arch 包不可用时，应发出 Warning。
        """
        from factor_pipeline.adapters import GarchWhiteningAdapter

        adapter = GarchWhiteningAdapter(p=1, q=1)

        # 模拟 arch 不可用的场景
        original_has_arch = getattr(adapter, '_has_arch', True)
        adapter._has_arch = False

        with self.assertWarns(UserWarning):
            result = adapter.fit_transform(self.data)

        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(result.shape, self.data.shape)

        # 恢复
        adapter._has_arch = original_has_arch

        print(f"[PASS] P1-4-04: GarchWhiteningAdapter 回退警告")

    def test_28_fallback_mode_in_step_stats(self):
        """
        [P1-4-05] 降级模式标记在 StepStats 中

        P3.2 更新: ImputerAdapter/ProcessingAdapter/NeutralizerAdapter 均不再回退 (REQUIRED 依赖)。
        仅 GarchWhiteningAdapter 保留 arch 可选依赖的 fallback。
        手工验证: GarchWhiteningAdapter 的 get_stats() 应包含 fallback_mode 字段。
        """
        from factor_pipeline.adapters import GarchWhiteningAdapter

        adapter = GarchWhiteningAdapter(p=1, q=1)
        # 模拟 arch 不可用
        adapter._has_arch = False
        with self.assertWarns(UserWarning):
            adapter.fit_transform(self.data)

        stats = adapter.get_stats()
        self.assertIn('fallback_mode', stats,
            msg="StepStats 应包含 fallback_mode 字段")

        print(f"[PASS] P1-4-05: GarchWhiteningAdapter StepStats 包含 fallback_mode (P2.4)")


# =============================================================================
#                              测试运行器
# =============================================================================

def run_all_tests():
    """运行所有 P1 修复测试"""
    print("=" * 70)
    print("P1 修复严格测试套件 — TDD Red Phase")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestTransitionWeightsRouting))
    suite.addTests(loader.loadTestsFromTestCase(TestUnifiedFitPattern))
    suite.addTests(loader.loadTestsFromTestCase(TestAdapterFallbackWarnings))

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

    if not result.wasSuccessful():
        print()
        print("测试失败列表 (Red Phase 预期):")
        for test, _ in result.failures + result.errors:
            print(f"  - {test}")

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)