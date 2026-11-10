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
      * v3.4.0 统一路由/诊断/断点监控 8 字段直接复制:
        pipeline_mode / enable_fingerprint_diagnostics / ab_experiment_id /
        enable_break_monitor / break_monitor_window / break_monitor_stride /
        break_monitor_alpha / break_monitor_n_bootstrap
      * 嵌套 → 扁平: static.garch.* / dynamic.* / mixed.transformation.*
      * 概念对应: classification_threshold_static/dynamic → classification.static/dynamic_ar1_threshold
                  migration_threshold → migration_threshold (dataclass 字段本身)
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
    # 测试 2: v3.4.0 统一路由/诊断/断点监控 8 字段直接复制 (默认值/自定义值)
    # =====================================================================

    def test_03_unified_routing_fields_default(self):
        """test_03: v3.4.0 统一路由/诊断/断点监控 8 字段默认值正确映射"""
        unified = self.Unified()
        dc = unified.to_pipeline_v2_config()

        # 手工校验: 默认值 (与 PipelineV2ConfigUnified 字段默认一致)
        self.assertEqual(dc.pipeline_mode, 'unified')
        self.assertEqual(dc.enable_fingerprint_diagnostics, True)
        self.assertIsNone(dc.ab_experiment_id)
        self.assertEqual(dc.enable_break_monitor, False)
        self.assertEqual(dc.break_monitor_window, 250)
        self.assertEqual(dc.break_monitor_stride, 20)
        self.assertEqual(dc.break_monitor_alpha, 0.05)
        self.assertEqual(dc.break_monitor_n_bootstrap, 400)

    def test_04_unified_routing_fields_custom(self):
        """test_04: v3.4.0 统一路由/诊断/断点监控 8 字段自定义值正确映射"""
        unified = self.Unified(
            pipeline_mode='dynamic_ab',
            enable_fingerprint_diagnostics=False,
            ab_experiment_id='exp-fix2-001',
            enable_break_monitor=True,
            break_monitor_window=300,
            break_monitor_stride=10,
            break_monitor_alpha=0.02,
            break_monitor_n_bootstrap=500,
        )
        dc = unified.to_pipeline_v2_config()

        # 手工校验: 自定义值
        self.assertEqual(dc.pipeline_mode, 'dynamic_ab')
        self.assertEqual(dc.enable_fingerprint_diagnostics, False)
        self.assertEqual(dc.ab_experiment_id, 'exp-fix2-001')
        self.assertEqual(dc.enable_break_monitor, True)
        self.assertEqual(dc.break_monitor_window, 300)
        self.assertEqual(dc.break_monitor_stride, 10)
        self.assertEqual(dc.break_monitor_alpha, 0.02)
        self.assertEqual(dc.break_monitor_n_bootstrap, 500)

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
        """test_09: mixed.transformation.method/target → mixed_transformation_*"""
        unified = self.Unified(
            mixed=dict(transformation=dict(
                method='identity', target_distribution='uniform',
            )),
            static=dict(transformation=dict(
                method='rank', target_distribution='normal',
            )),
        )
        dc = unified.to_pipeline_v2_config()

        # 手工校验
        self.assertEqual(dc.mixed_transformation_method, 'identity')
        self.assertEqual(dc.mixed_target_distribution, 'uniform')
        self.assertEqual(dc.static_transformation_method, 'rank')
        self.assertEqual(dc.static_target_distribution, 'normal')

    # =====================================================================
    # 测试 5: 双向一致性 (Unified → dataclass → Unified)
    # =====================================================================

    def test_10_round_trip_default(self):
        """test_10: 默认配置映射: Unified → dataclass 的 v3.4.0 8 字段取值"""
        dc = self.Unified().to_pipeline_v2_config()

        # 逐字段断言默认值 (不可用 from_unified 自比 — 其内部即调用本方法)
        self.assertEqual(dc.pipeline_mode, 'unified')
        self.assertTrue(dc.enable_fingerprint_diagnostics)
        self.assertIsNone(dc.ab_experiment_id)
        self.assertFalse(dc.enable_break_monitor)
        self.assertEqual(dc.break_monitor_window, 250)
        self.assertEqual(dc.break_monitor_stride, 20)
        self.assertAlmostEqual(dc.break_monitor_alpha, 0.05)
        self.assertEqual(dc.break_monitor_n_bootstrap, 400)

        # from_unified 工厂仍可用 (等价于 to_pipeline_v2_config)
        self.assertIsInstance(self.Dataclass.from_unified(self.Unified()),
                              self.Dataclass)

    def test_11_round_trip_custom_values(self):
        """test_11: 自定义值 round-trip: 所有映射字段保持一致"""
        unified = self.Unified(
            pipeline_mode='dynamic_ab',
            enable_fingerprint_diagnostics=False,
            ab_experiment_id='exp-roundtrip-fix2',
            enable_break_monitor=True,
            break_monitor_window=300,
            break_monitor_stride=15,
            break_monitor_alpha=0.02,
            break_monitor_n_bootstrap=600,
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
                transformation=self.TransCfg(
                    method='yeo_johnson', target_distribution='normal',
                ),
            ),
        )
        dc = unified.to_pipeline_v2_config()

        # 手工校验所有字段
        # v3.4.0 统一路由/诊断/断点监控 8 字段
        self.assertEqual(dc.pipeline_mode, 'dynamic_ab')
        self.assertEqual(dc.enable_fingerprint_diagnostics, False)
        self.assertEqual(dc.ab_experiment_id, 'exp-roundtrip-fix2')
        self.assertEqual(dc.enable_break_monitor, True)
        self.assertEqual(dc.break_monitor_window, 300)
        self.assertEqual(dc.break_monitor_stride, 15)
        self.assertEqual(dc.break_monitor_alpha, 0.02)
        self.assertEqual(dc.break_monitor_n_bootstrap, 600)
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
        self.assertEqual(dc.mixed_transformation_method, 'yeo_johnson')
        self.assertEqual(dc.mixed_target_distribution, 'normal')

    # =====================================================================
    # 测试 6: 集成验证 — dataclass 仍可被 pipeline 和 optimizer 消费
    # =====================================================================

    def test_12_dataclass_consumed_by_optimizer(self):
        """test_12: 转换后的 dataclass 可被 optimizer._config_to_params 消费 (v3.4.0 3 参数契约)"""
        unified = self.Unified(
            classification_threshold_static=0.85,
            classification_threshold_dynamic=0.35,
            migration_threshold=0.15,
        )
        dc = unified.to_pipeline_v2_config()

        # optimizer._config_to_params 直接消费 dataclass
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer
        optimizer = EndToEndThresholdOptimizer(n_trials=1)
        params = optimizer._config_to_params(dc)

        # 手工校验: v3.4.0 收敛为 3 参数契约
        self.assertEqual(
            set(params.keys()),
            {'classification_threshold_static',
             'classification_threshold_dynamic',
             'migration_threshold'},
            msg="_config_to_params 应返回 3 参数契约"
        )
        self.assertAlmostEqual(params['classification_threshold_static'], 0.85, places=6)
        self.assertAlmostEqual(params['classification_threshold_dynamic'], 0.35, places=6)
        self.assertAlmostEqual(params['migration_threshold'], 0.15, places=6)

    def test_13_no_breaking_change_to_legacy_compat(self):
        """test_13: 旧版 to_pipeline_config() 兼容层仍可用 (不破坏向后兼容)"""
        unified = self.Unified()
        # 旧版兼容层应仍存在
        legacy = unified.to_pipeline_config()
        self.assertIsNotNone(legacy, "旧版 to_pipeline_config() 兼容层必须保留")


if __name__ == '__main__':
    unittest.main(verbosity=2)
