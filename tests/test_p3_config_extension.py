# -*- coding: utf-8 -*-
"""
P3 Phase 1: 配置扩展 — 测试套件

v3.4.0 ADR (暂用号 ADR-042): PipelineV2ConfigUnified 统一路由/诊断/断点监控 8 字段契约。

字段契约:
  1. pipeline_mode                = 'unified'   Literal['unified', 'dynamic_ab']
  2. enable_fingerprint_diagnostics = True
  3. ab_experiment_id             = None        Optional[str]
  4. enable_break_monitor         = False
  5. break_monitor_window         = 250  (ge=60)
  6. break_monitor_stride         = 20   (ge=1)
  7. break_monitor_alpha          = 0.05 (0 < x < 0.5)
  8. break_monitor_n_bootstrap    = 400  (ge=50)
"""

import unittest
import json
import tempfile
import os
import sys


class TestConfigExtensionDefaultValues(unittest.TestCase):
    """测试 1: 默认值校验"""

    def test_01_default_values(self):
        """
        [P3-Phase1-01] 默认值正确。

        手工校验: 构造默认 config，验证每个统一路由/诊断/断点监控字段的值。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified

        config = PipelineV2ConfigUnified()

        # 统一路由/诊断/断点监控字段默认值
        self.assertEqual(config.pipeline_mode, 'unified',
            "pipeline_mode 默认值应为 'unified'")
        self.assertEqual(config.enable_fingerprint_diagnostics, True,
            "enable_fingerprint_diagnostics 默认值应为 True")
        self.assertIsNone(config.ab_experiment_id,
            "ab_experiment_id 默认值应为 None")
        self.assertEqual(config.enable_break_monitor, False,
            "enable_break_monitor 默认值应为 False")
        self.assertEqual(config.break_monitor_window, 250,
            "break_monitor_window 默认值应为 250")
        self.assertEqual(config.break_monitor_stride, 20,
            "break_monitor_stride 默认值应为 20")
        self.assertEqual(config.break_monitor_alpha, 0.05,
            "break_monitor_alpha 默认值应为 0.05")
        self.assertEqual(config.break_monitor_n_bootstrap, 400,
            "break_monitor_n_bootstrap 默认值应为 400")

        # 已有字段不受影响
        self.assertEqual(config.classification_threshold_static, 0.80)
        self.assertEqual(config.classification_threshold_dynamic, 0.40)
        self.assertEqual(config.migration_threshold, 0.10)
        self.assertEqual(config.migration_window, 12)
        self.assertEqual(config.fingerprint_window, 24)

        print(f"\n  手工校验通过:")
        print(f"    pipeline_mode                = {config.pipeline_mode}")
        print(f"    enable_fingerprint_diagnostics = {config.enable_fingerprint_diagnostics}")
        print(f"    ab_experiment_id             = {config.ab_experiment_id}")
        print(f"    enable_break_monitor         = {config.enable_break_monitor}")
        print(f"    break_monitor_window         = {config.break_monitor_window}")
        print(f"    break_monitor_stride         = {config.break_monitor_stride}")
        print(f"    break_monitor_alpha          = {config.break_monitor_alpha}")
        print(f"    break_monitor_n_bootstrap    = {config.break_monitor_n_bootstrap}")

    def test_02_custom_values(self):
        """
        [P3-Phase1-02] 自定义值生效。

        手工校验: 传入自定义值，验证字段被正确设置。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified

        config = PipelineV2ConfigUnified(
            pipeline_mode='dynamic_ab',
            enable_fingerprint_diagnostics=False,
            ab_experiment_id='exp-2026-001',
            enable_break_monitor=True,
            break_monitor_window=300,
            break_monitor_stride=10,
            break_monitor_alpha=0.02,
            break_monitor_n_bootstrap=500,
        )

        self.assertEqual(config.pipeline_mode, 'dynamic_ab')
        self.assertEqual(config.enable_fingerprint_diagnostics, False)
        self.assertEqual(config.ab_experiment_id, 'exp-2026-001')
        self.assertEqual(config.enable_break_monitor, True)
        self.assertEqual(config.break_monitor_window, 300)
        self.assertEqual(config.break_monitor_stride, 10)
        self.assertEqual(config.break_monitor_alpha, 0.02)
        self.assertEqual(config.break_monitor_n_bootstrap, 500)

        print(f"\n  手工校验通过: 所有自定义值正确")
        print(f"    pipeline_mode                = {config.pipeline_mode} (expected dynamic_ab)")
        print(f"    enable_fingerprint_diagnostics = {config.enable_fingerprint_diagnostics} (expected False)")
        print(f"    ab_experiment_id             = {config.ab_experiment_id} (expected exp-2026-001)")
        print(f"    enable_break_monitor         = {config.enable_break_monitor} (expected True)")
        print(f"    break_monitor_window         = {config.break_monitor_window} (expected 300)")
        print(f"    break_monitor_stride         = {config.break_monitor_stride} (expected 10)")
        print(f"    break_monitor_alpha          = {config.break_monitor_alpha} (expected 0.02)")
        print(f"    break_monitor_n_bootstrap    = {config.break_monitor_n_bootstrap} (expected 500)")


class TestConfigExtensionConstraints(unittest.TestCase):
    """测试 2: 字段约束"""

    def test_03_pipeline_mode_literal_bounds(self):
        """
        [P3-Phase1-03] pipeline_mode Literal 约束。

        手工校验: 非法模式应抛出 ValidationError; 两个合法模式应通过。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified
        from pydantic import ValidationError

        # 非法模式
        with self.assertRaises(ValidationError):
            PipelineV2ConfigUnified(pipeline_mode='hard_routing')

        # 合法模式应通过
        config_unified = PipelineV2ConfigUnified(pipeline_mode='unified')
        self.assertEqual(config_unified.pipeline_mode, 'unified')
        config_ab = PipelineV2ConfigUnified(pipeline_mode='dynamic_ab')
        self.assertEqual(config_ab.pipeline_mode, 'dynamic_ab')

        print(f"\n  手工校验通过: pipeline_mode Literal 约束正确")
        print(f"    'unified': OK, 'dynamic_ab': OK")
        print(f"    非法模式: ValidationError (正确)")

    def test_04_break_monitor_window_bounds(self):
        """
        [P3-Phase1-04] break_monitor_window 下界约束 (ge=60)。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            PipelineV2ConfigUnified(break_monitor_window=59)

        config_lo = PipelineV2ConfigUnified(break_monitor_window=60)
        self.assertEqual(config_lo.break_monitor_window, 60)
        config_hi = PipelineV2ConfigUnified(break_monitor_window=1000)
        self.assertEqual(config_hi.break_monitor_window, 1000)

        print(f"\n  手工校验通过: break_monitor_window ge=60 约束正确")
        print(f"    下限 60: OK, 1000: OK")
        print(f"    低于 60: ValidationError (正确)")

    def test_05_break_monitor_stride_bounds(self):
        """
        [P3-Phase1-05] break_monitor_stride 下界约束 (ge=1)。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            PipelineV2ConfigUnified(break_monitor_stride=0)

        config_lo = PipelineV2ConfigUnified(break_monitor_stride=1)
        self.assertEqual(config_lo.break_monitor_stride, 1)
        config_hi = PipelineV2ConfigUnified(break_monitor_stride=100)
        self.assertEqual(config_hi.break_monitor_stride, 100)

        print(f"\n  手工校验通过: break_monitor_stride ge=1 约束正确")
        print(f"    下限 1: OK, 100: OK")
        print(f"    0: ValidationError (正确)")

    def test_06_break_monitor_alpha_bounds(self):
        """
        [P3-Phase1-06] break_monitor_alpha 开区间约束 (0 < x < 0.5)。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified
        from pydantic import ValidationError

        # 0 与 0.5 均为开区间端点, 应拒绝
        with self.assertRaises(ValidationError):
            PipelineV2ConfigUnified(break_monitor_alpha=0.0)
        with self.assertRaises(ValidationError):
            PipelineV2ConfigUnified(break_monitor_alpha=0.5)

        config_lo = PipelineV2ConfigUnified(break_monitor_alpha=0.001)
        self.assertEqual(config_lo.break_monitor_alpha, 0.001)
        config_hi = PipelineV2ConfigUnified(break_monitor_alpha=0.499)
        self.assertEqual(config_hi.break_monitor_alpha, 0.499)

        print(f"\n  手工校验通过: break_monitor_alpha (0, 0.5) 开区间约束正确")
        print(f"    0.001: OK, 0.499: OK")
        print(f"    0.0 / 0.5: ValidationError (正确)")

    def test_07_break_monitor_n_bootstrap_bounds(self):
        """
        [P3-Phase1-07] break_monitor_n_bootstrap 下界约束 (ge=50)。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            PipelineV2ConfigUnified(break_monitor_n_bootstrap=49)

        config_lo = PipelineV2ConfigUnified(break_monitor_n_bootstrap=50)
        self.assertEqual(config_lo.break_monitor_n_bootstrap, 50)
        config_hi = PipelineV2ConfigUnified(break_monitor_n_bootstrap=1000)
        self.assertEqual(config_hi.break_monitor_n_bootstrap, 1000)

        print(f"\n  手工校验通过: break_monitor_n_bootstrap ge=50 约束正确")
        print(f"    下限 50: OK, 1000: OK")
        print(f"    低于 50: ValidationError (正确)")


class TestConfigExtensionSerialization(unittest.TestCase):
    """测试 3: 序列化/反序列化"""

    def test_08_json_roundtrip(self):
        """
        [P3-Phase1-08] JSON 序列化往返。

        手工校验:  config → JSON → config，统一路由/诊断/断点监控字段值不变。
        """
        from factor_pipeline.config_v2 import (
            PipelineV2ConfigUnified,
            save_config_to_json,
            load_config_from_json
        )

        original = PipelineV2ConfigUnified(
            name="test_p3",
            pipeline_mode='dynamic_ab',
            enable_fingerprint_diagnostics=False,
            ab_experiment_id='exp-roundtrip-001',
            enable_break_monitor=True,
            break_monitor_window=300,
            break_monitor_stride=15,
            break_monitor_alpha=0.02,
            break_monitor_n_bootstrap=600,
        )

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        ) as f:
            tmp_path = f.name

        try:
            save_config_to_json(original, tmp_path)

            # 手工检查 JSON 内容
            with open(tmp_path, 'r', encoding='utf-8') as f:
                json_content = json.load(f)
            print(f"\n  JSON 内容:")
            print(f"    pipeline_mode: {json_content.get('pipeline_mode')}")
            print(f"    enable_fingerprint_diagnostics: {json_content.get('enable_fingerprint_diagnostics')}")
            print(f"    ab_experiment_id: {json_content.get('ab_experiment_id')}")
            print(f"    enable_break_monitor: {json_content.get('enable_break_monitor')}")
            print(f"    break_monitor_window: {json_content.get('break_monitor_window')}")
            print(f"    break_monitor_stride: {json_content.get('break_monitor_stride')}")
            print(f"    break_monitor_alpha: {json_content.get('break_monitor_alpha')}")
            print(f"    break_monitor_n_bootstrap: {json_content.get('break_monitor_n_bootstrap')}")

            self.assertEqual(json_content['pipeline_mode'], 'dynamic_ab')
            self.assertEqual(json_content['enable_fingerprint_diagnostics'], False)
            self.assertEqual(json_content['ab_experiment_id'], 'exp-roundtrip-001')
            self.assertEqual(json_content['enable_break_monitor'], True)
            self.assertEqual(json_content['break_monitor_window'], 300)
            self.assertEqual(json_content['break_monitor_stride'], 15)
            self.assertEqual(json_content['break_monitor_alpha'], 0.02)
            self.assertEqual(json_content['break_monitor_n_bootstrap'], 600)

            # 反序列化
            loaded = load_config_from_json(tmp_path)
            self.assertEqual(loaded.pipeline_mode, original.pipeline_mode)
            self.assertEqual(loaded.enable_fingerprint_diagnostics,
                             original.enable_fingerprint_diagnostics)
            self.assertEqual(loaded.ab_experiment_id, original.ab_experiment_id)
            self.assertEqual(loaded.enable_break_monitor, original.enable_break_monitor)
            self.assertEqual(loaded.break_monitor_window, original.break_monitor_window)
            self.assertEqual(loaded.break_monitor_stride, original.break_monitor_stride)
            self.assertEqual(loaded.break_monitor_alpha, original.break_monitor_alpha)
            self.assertEqual(loaded.break_monitor_n_bootstrap,
                             original.break_monitor_n_bootstrap)

            print(f"\n  手工校验通过: JSON 往返一致")
        finally:
            os.unlink(tmp_path)

    def test_09_model_dump_includes_new_fields(self):
        """
        [P3-Phase1-09] model_dump() 包含统一路由/诊断/断点监控字段。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified

        config = PipelineV2ConfigUnified(
            pipeline_mode='dynamic_ab',
            enable_fingerprint_diagnostics=False,
            ab_experiment_id='exp-dump-001',
            enable_break_monitor=True,
            break_monitor_window=300,
            break_monitor_stride=15,
            break_monitor_alpha=0.02,
            break_monitor_n_bootstrap=600,
        )

        dumped = config.model_dump()

        self.assertIn('pipeline_mode', dumped)
        self.assertIn('enable_fingerprint_diagnostics', dumped)
        self.assertIn('ab_experiment_id', dumped)
        self.assertIn('enable_break_monitor', dumped)
        self.assertIn('break_monitor_window', dumped)
        self.assertIn('break_monitor_stride', dumped)
        self.assertIn('break_monitor_alpha', dumped)
        self.assertIn('break_monitor_n_bootstrap', dumped)

        self.assertEqual(dumped['pipeline_mode'], 'dynamic_ab')
        self.assertEqual(dumped['enable_fingerprint_diagnostics'], False)
        self.assertEqual(dumped['ab_experiment_id'], 'exp-dump-001')
        self.assertEqual(dumped['enable_break_monitor'], True)
        self.assertEqual(dumped['break_monitor_window'], 300)
        self.assertEqual(dumped['break_monitor_stride'], 15)
        self.assertEqual(dumped['break_monitor_alpha'], 0.02)
        self.assertEqual(dumped['break_monitor_n_bootstrap'], 600)

        print(f"\n  手工校验通过: model_dump() 包含全部统一路由/诊断/断点监控字段")


class TestConfigExtensionBackwardCompat(unittest.TestCase):
    """测试 4: 向后兼容"""

    def test_10_existing_configs_still_work(self):
        """
        [P3-Phase1-10] 已有字段不受影响。

        手工校验: 只使用已有字段构造 config，验证统一路由/诊断/断点监控字段取默认值。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified

        # 模拟 v2.0 的构造方式
        config = PipelineV2ConfigUnified(
            name="legacy_pipeline",
            classification_threshold_static=0.78,
            classification_threshold_dynamic=0.38,
            migration_threshold=0.12,
            fingerprint_window=36,
        )

        # 已有字段应正确
        self.assertEqual(config.name, "legacy_pipeline")
        self.assertEqual(config.classification_threshold_static, 0.78)
        self.assertEqual(config.classification_threshold_dynamic, 0.38)
        self.assertEqual(config.migration_threshold, 0.12)
        self.assertEqual(config.fingerprint_window, 36)

        # 统一路由/诊断/断点监控字段应取默认值
        self.assertEqual(config.pipeline_mode, 'unified')
        self.assertEqual(config.enable_fingerprint_diagnostics, True)
        self.assertIsNone(config.ab_experiment_id)
        self.assertEqual(config.enable_break_monitor, False)
        self.assertEqual(config.break_monitor_window, 250)
        self.assertEqual(config.break_monitor_stride, 20)
        self.assertEqual(config.break_monitor_alpha, 0.05)
        self.assertEqual(config.break_monitor_n_bootstrap, 400)

        print(f"\n  手工校验通过: 向后兼容")
        print(f"    已有字段: 自定义值正确")
        print(f"    统一路由/诊断/断点监控字段: 默认值正确")

    def test_11_sub_configs_unaffected(self):
        """
        [P3-Phase1-11] 子配置不受影响。

        手工校验: StaticPipelineConfig/DynamicPipelineConfig 等子配置
        的字段仍可正常访问。
        """
        from factor_pipeline.config_v2 import (
            PipelineV2ConfigUnified,
            StaticPipelineConfig,
            DynamicPipelineConfig,
            GarchConfig,
        )

        config = PipelineV2ConfigUnified(
            static=StaticPipelineConfig(
                garch=GarchConfig(enabled=True, p=2, q=1)
            ),
            dynamic=DynamicPipelineConfig(
                decorrelation_strength=0.7,
                max_ar_order=8,
            ),
        )

        # 子配置字段
        self.assertTrue(config.static.garch.enabled)
        self.assertEqual(config.static.garch.p, 2)
        self.assertEqual(config.static.garch.q, 1)
        self.assertEqual(config.dynamic.decorrelation_strength, 0.7)
        self.assertEqual(config.dynamic.max_ar_order, 8)

        print(f"\n  手工校验通过: 子配置不受影响")
        print(f"    static.garch.enabled = {config.static.garch.enabled}")
        print(f"    static.garch.p = {config.static.garch.p}")
        print(f"    dynamic.decorrelation_strength = {config.dynamic.decorrelation_strength}")
        print(f"    dynamic.max_ar_order = {config.dynamic.max_ar_order}")

    def test_12_to_pipeline_config_compat(self):
        """
        [P3-Phase1-12] to_pipeline_config() 兼容层仍可用。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified

        config = PipelineV2ConfigUnified(
            name="compat_test",
            pipeline_mode='dynamic_ab',
            enable_break_monitor=True,
        )

        # 兼容层转换不应报错
        try:
            legacy = config.to_pipeline_config()
            self.assertIsNotNone(legacy)
            self.assertEqual(legacy.name, "compat_test")
            self.assertEqual(len(legacy.steps), 5)
            print(f"\n  手工校验通过: to_pipeline_config() 兼容层正常")
            print(f"    legacy.name = {legacy.name}")
            print(f"    legacy.steps = {len(legacy.steps)}")
        except Exception as e:
            self.fail(f"to_pipeline_config() 失败: {e}")


# =============================================================================
#                              测试运行器
# =============================================================================

def run_all_tests():
    """运行所有 Phase 1 配置扩展测试"""
    print("=" * 70)
    print("P3 Phase 1: 配置扩展 — 测试套件")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestConfigExtensionDefaultValues))
    suite.addTests(loader.loadTestsFromTestCase(TestConfigExtensionConstraints))
    suite.addTests(loader.loadTestsFromTestCase(TestConfigExtensionSerialization))
    suite.addTests(loader.loadTestsFromTestCase(TestConfigExtensionBackwardCompat))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print(f"Phase 1 测试结果: {result.testsRun} 运行, "
          f"{len(result.failures)} 失败, {len(result.errors)} 错误")
    print("=" * 70)

    return result


if __name__ == '__main__':
    run_all_tests()
