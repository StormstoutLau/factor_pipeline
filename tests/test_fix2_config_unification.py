# -*- coding: utf-8 -*-
"""
Fix 2: 配置系统统一 (方案 C) — TDD 测试

验证 PipelineV2ConfigUnified (Pydantic) 与 PipelineV2Config (dataclass)
之间的转换桥接正确性。

核心问题:
  - PipelineV2ConfigUnified (Pydantic, 21 顶层字段) — 用于配置持久化/加载/回测集成
  - PipelineV2Config (dataclass, 18 字段) — 用于 optimizer 和 pipeline 运行时
  - 两者无转换桥接, 仅 4 个共享字段直接对应

方案 C:
  - 添加 to_pipeline_v2_config() 方法: Unified → dataclass
  - 添加 from_unified() 类方法: dataclass ← Unified (备选入口)
  - 字段映射:
      * 4 共享字段直接复制: hard_routing_prob, merge_alpha, ks_alpha, mixed_winsor_sigma
      * 嵌套 → 扁平: static.garch.* / dynamic.* / mixed.transformation.*
      * 概念对应: classification_threshold_static/dynamic → classification.static/dynamic_ar1_threshold
                  migration_threshold → monitor.migration_threshold (or similarity_threshold)
"""

import unittest
import sys
from pathlib import Path

# 将项目父目录 (F:\Coding) 加入 sys.path, 使 factor_pipeline 可作为包导入
_PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))

# 将外部依赖加入 sys.path
for ext in ["F:/Coding/Factor_Fingerprint", "F:/Coding/Factor_Decoupler"]:
    if ext not in sys.path:
        sys.path.insert(0, ext)


class TestFix2ConfigUnification(unittest.TestCase):
    """Fix 2: 配置系统统一桥接测试"""

    def setUp(self):
        from factor_pipeline.config_v2 import (
            PipelineV2ConfigUnified,
            StaticPipelineConfig, DynamicPipelineConfig, MixedPipelineConfig,
            GarchConfig, TransformationConfig,
        )
        from factor_pipeline.pipelines_v2 import PipelineV2Config
        from factor_pipeline.modules.factor_fingerprint import (
            FingerprintConfig, ClassificationConfig, MonitorConfig,
        )
        self.Unified = PipelineV2ConfigUnified
        self.Dataclass = PipelineV2Config
        self.StaticCfg = StaticPipelineConfig
        self.DynamicCfg = DynamicPipelineConfig
        self.MixedCfg = MixedPipelineConfig
        self.GarchCfg = GarchConfig
        self.TransCfg = TransformationConfig
        self.FingerprintConfig = FingerprintConfig
        self.ClassificationConfig = ClassificationConfig
        self.MonitorConfig = MonitorConfig

    # =====================================================================
    # 测试 1: 转换方法存在性
    # =====================================================================

    def test_01_to_pipeline_v2_config_method_exists(self):
        """test_01: PipelineV2ConfigUnified.to_pipeline_v2_config() 方法存在"""
        unified = self.Unified()
        self.assertTrue(
            hasattr(unified, 'to_pipeline_v2_config'),
            "PipelineV2ConfigUnified 必须实现 to_pipeline_v2_config() 方法"
        )
        result = unified.to_pipeline_v2_config()
        self.assertIsInstance(result, self.Dataclass)

    def test_02_from_unified_classmethod_exists(self):
        """test_02: PipelineV2Config.from_unified() 类方法存在"""
        self.assertTrue(
            hasattr(self.Dataclass, 'from_unified'),
            "PipelineV2Config 必须实现 from_unified() 类方法"
        )
        unified = self.Unified()
        result = self.Dataclass.from_unified(unified)
        self.assertIsInstance(result, self.Dataclass)

    # =====================================================================
    # 测试 2: 4 个共享字段直接复制 (默认值)
    # =====================================================================

    def test_03_shared_four_fields_default(self):
        """test_03: 4 个共享字段默认值正确映射"""
        unified = self.Unified()
        dc = unified.to_pipeline_v2_config()

        # 手工校验: 默认值
        # hard_routing_prob = 0.90
        # merge_alpha = 0.50
        # ks_alpha = 0.05
        # mixed_winsor_sigma = 3.0
        self.assertAlmostEqual(dc.hard_routing_prob, 0.90, places=6)
        self.assertAlmostEqual(dc.merge_alpha, 0.50, places=6)
        self.assertAlmostEqual(dc.ks_alpha, 0.05, places=6)
        self.assertAlmostEqual(dc.mixed_winsor_sigma, 3.0, places=6)

    def test_04_shared_four_fields_custom(self):
        """test_04: 4 个共享字段自定义值正确映射"""
        unified = self.Unified(
            hard_routing_prob=0.75,
            merge_alpha=0.30,
            ks_alpha=0.01,
            mixed_winsor_sigma=2.5,
        )
        dc = unified.to_pipeline_v2_config()

        # 手工校验: 自定义值
        self.assertAlmostEqual(dc.hard_routing_prob, 0.75, places=6)
        self.assertAlmostEqual(dc.merge_alpha, 0.30, places=6)
        self.assertAlmostEqual(dc.ks_alpha, 0.01, places=6)
        self.assertAlmostEqual(dc.mixed_winsor_sigma, 2.5, places=6)

    # =====================================================================
    # 测试 3: 概念对应字段映射
    # =====================================================================

    def test_05_classification_thresholds_mapped(self):
        """test_05: classification_threshold_static/dynamic → classification.static/dynamic_ar1_threshold"""
        unified = self.Unified(
            classification_threshold_static=0.85,
            classification_threshold_dynamic=0.35,
        )
        dc = unified.to_pipeline_v2_config()

        # 手工校验: 概念对应字段
        self.assertAlmostEqual(
            dc.classification.static_ar1_threshold, 0.85, places=6,
            msg="classification_threshold_static 应映射到 classification.static_ar1_threshold"
        )
        self.assertAlmostEqual(
            dc.classification.dynamic_ar1_threshold, 0.35, places=6,
            msg="classification_threshold_dynamic 应映射到 classification.dynamic_ar1_threshold"
        )

    def test_06_migration_threshold_is_unified_only(self):
        """test_06: migration_threshold 是 Unified-only 字段, 转换时不报错

        MonitorConfig 实际字段: short/medium/long_threshold + migration_consecutive
        + enable_smooth_transition. 无单一 migration_threshold 字段.
        Unified.migration_threshold 转换时跳过 (与 optimizer.py hasattr 行为一致).
        Unified.enable_monitoring → monitor.enable_smooth_transition 概念对应.
        """
        unified = self.Unified(migration_threshold=0.15, enable_monitoring=True)
        # 转换不应报错
        dc = unified.to_pipeline_v2_config()

        # monitor 保持默认字段值 (migration_threshold 无处映射)
        # 但 enable_smooth_transition 应从 enable_monitoring 映射
        self.assertEqual(
            dc.monitor.enable_smooth_transition, True,
            "enable_monitoring 应映射到 monitor.enable_smooth_transition"
        )
        # MonitorConfig 应有 short/medium/long_threshold 字段 (默认值)
        self.assertTrue(hasattr(dc.monitor, 'short_threshold'))
        self.assertTrue(hasattr(dc.monitor, 'long_threshold'))

    # =====================================================================
    # 测试 4: 嵌套 → 扁平字段映射
    # =====================================================================

    def test_07_static_garch_fields_mapped(self):
        """test_07: static.garch.* → static_enable_garch/static_garch_p/q/vol/min_obs"""
        unified = self.Unified(
            static=self.StaticCfg(garch=self.GarchCfg(
                enabled=True, p=2, q=2, vol='EGarch', min_obs=100,
            ))
        )
        dc = unified.to_pipeline_v2_config()

        # 手工校验
        self.assertEqual(dc.static_enable_garch, True)
        self.assertEqual(dc.static_garch_p, 2)
        self.assertEqual(dc.static_garch_q, 2)
        self.assertEqual(dc.static_garch_vol, 'EGarch')
        self.assertEqual(dc.static_garch_min_obs, 100)

    def test_08_dynamic_fields_mapped(self):
        """test_08: dynamic.decorrelation_strength/max_ar_order/ar_criterion → dynamic_*"""
        unified = self.Unified(
            dynamic=self.DynamicCfg(
                decorrelation_strength=0.8,
                max_ar_order=8,
                ar_criterion='bic',
            )
        )
        dc = unified.to_pipeline_v2_config()

        # 手工校验
        self.assertAlmostEqual(dc.dynamic_decorrelation_strength, 0.8, places=6)
        self.assertEqual(dc.dynamic_max_ar_order, 8)
        self.assertEqual(dc.dynamic_ar_criterion, 'bic')

    def test_09_mixed_fields_mapped(self):
        """test_09: mixed.conditional_transform + transformation.skew/kurt → mixed_*"""
        unified = self.Unified(
            mixed=self.MixedCfg(
                conditional_transform=False,
                transformation=self.TransCfg(
                    skew_threshold=1.5, kurt_threshold=4.0,
                ),
            )
        )
        dc = unified.to_pipeline_v2_config()

        # 手工校验
        self.assertEqual(dc.mixed_conditional_transform, False)
        self.assertAlmostEqual(dc.mixed_skew_threshold, 1.5, places=6)
        self.assertAlmostEqual(dc.mixed_kurt_threshold, 4.0, places=6)

    # =====================================================================
    # 测试 5: 双向一致性 (Unified → dataclass → Unified)
    # =====================================================================

    def test_10_round_trip_default(self):
        """test_10: 默认配置 round-trip: Unified → dataclass → 比对 4 共享字段"""
        unified_orig = self.Unified()
        dc = unified_orig.to_pipeline_v2_config()

        # 反向: 从 dataclass 重建 Unified (用 from_unified 应等价于 to_pipeline_v2_config)
        dc2 = self.Dataclass.from_unified(unified_orig)
        # 两个 dataclass 应该字段相同 (4 共享字段)
        self.assertAlmostEqual(dc.hard_routing_prob, dc2.hard_routing_prob, places=6)
        self.assertAlmostEqual(dc.merge_alpha, dc2.merge_alpha, places=6)
        self.assertAlmostEqual(dc.ks_alpha, dc2.ks_alpha, places=6)
        self.assertAlmostEqual(dc.mixed_winsor_sigma, dc2.mixed_winsor_sigma, places=6)

    def test_11_round_trip_custom_values(self):
        """test_11: 自定义值 round-trip: 所有映射字段保持一致"""
        unified = self.Unified(
            hard_routing_prob=0.80,
            merge_alpha=0.40,
            ks_alpha=0.02,
            mixed_winsor_sigma=2.8,
            classification_threshold_static=0.82,
            classification_threshold_dynamic=0.38,
            migration_threshold=0.12,
            static=self.StaticCfg(garch=self.GarchCfg(
                enabled=True, p=1, q=1, vol='Garch', min_obs=60,
            )),
            dynamic=self.DynamicCfg(
                decorrelation_strength=0.9,
                max_ar_order=6,
                ar_criterion='hqic',
            ),
            mixed=self.MixedCfg(
                conditional_transform=True,
                transformation=self.TransCfg(
                    skew_threshold=2.0, kurt_threshold=5.0,
                ),
            ),
        )
        dc = unified.to_pipeline_v2_config()

        # 手工校验所有字段
        # 4 共享字段
        self.assertAlmostEqual(dc.hard_routing_prob, 0.80, places=6)
        self.assertAlmostEqual(dc.merge_alpha, 0.40, places=6)
        self.assertAlmostEqual(dc.ks_alpha, 0.02, places=6)
        self.assertAlmostEqual(dc.mixed_winsor_sigma, 2.8, places=6)
        # 概念对应字段
        self.assertAlmostEqual(dc.classification.static_ar1_threshold, 0.82, places=6)
        self.assertAlmostEqual(dc.classification.dynamic_ar1_threshold, 0.38, places=6)
        # 嵌套 → 扁平
        self.assertEqual(dc.static_enable_garch, True)
        self.assertEqual(dc.static_garch_p, 1)
        self.assertEqual(dc.static_garch_q, 1)
        self.assertEqual(dc.static_garch_vol, 'Garch')
        self.assertEqual(dc.static_garch_min_obs, 60)
        self.assertAlmostEqual(dc.dynamic_decorrelation_strength, 0.9, places=6)
        self.assertEqual(dc.dynamic_max_ar_order, 6)
        self.assertEqual(dc.dynamic_ar_criterion, 'hqic')
        self.assertEqual(dc.mixed_conditional_transform, True)
        self.assertAlmostEqual(dc.mixed_skew_threshold, 2.0, places=6)
        self.assertAlmostEqual(dc.mixed_kurt_threshold, 5.0, places=6)

    # =====================================================================
    # 测试 6: 集成验证 — dataclass 仍可被 pipeline 和 optimizer 消费
    # =====================================================================

    def test_12_dataclass_consumed_by_optimizer(self):
        """test_12: 转换后的 dataclass 可被 optimizer 消费"""
        unified = self.Unified(
            hard_routing_prob=0.78,
            merge_alpha=0.35,
            ks_alpha=0.03,
            mixed_winsor_sigma=2.7,
        )
        dc = unified.to_pipeline_v2_config()

        # 模拟 optimizer._config_to_params 消费 dataclass
        params = {
            'hard_routing_prob': dc.hard_routing_prob,
            'merge_alpha': dc.merge_alpha,
            'ks_alpha': dc.ks_alpha,
            'mixed_winsor_sigma': dc.mixed_winsor_sigma,
            'classification_threshold_static': dc.classification.static_ar1_threshold,
            'classification_threshold_dynamic': dc.classification.dynamic_ar1_threshold,
        }

        # 手工校验: 参数应与原始 Unified 一致
        self.assertAlmostEqual(params['hard_routing_prob'], 0.78, places=6)
        self.assertAlmostEqual(params['merge_alpha'], 0.35, places=6)
        self.assertAlmostEqual(params['ks_alpha'], 0.03, places=6)
        self.assertAlmostEqual(params['mixed_winsor_sigma'], 2.7, places=6)

    def test_13_no_breaking_change_to_legacy_compat(self):
        """test_13: 旧版 to_pipeline_config() 兼容层仍可用 (不破坏向后兼容)"""
        unified = self.Unified()
        # 旧版兼容层应仍存在
        legacy = unified.to_pipeline_config()
        self.assertIsNotNone(legacy, "旧版 to_pipeline_config() 兼容层必须保留")


if __name__ == '__main__':
    unittest.main(verbosity=2)
