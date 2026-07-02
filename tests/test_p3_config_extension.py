# -*- coding: utf-8 -*-
"""
P3 Phase 1: 配置扩展 — TDD 测试套件

扩展 PipelineV2ConfigUnified 为端到端阈值搜索提供可调参数支持。

新增字段:
  1. hard_routing_prob          = 0.90  [0.5, 1.0]
  2. merge_alpha                = 0.50  [0.0, 1.0]
  3. ks_alpha                   = 0.05  [0.001, 0.5]
  4. mixed_winsor_sigma         = 3.0   [1.0, 10.0]
  5. transform_aggressiveness   = 1.0   [0.3, 5.0]
  6. enable_smooth_transition   = True  (已存在但需确认)
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

        手工校验: 构造默认 config，验证每个新字段的值。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified

        config = PipelineV2ConfigUnified()

        # 新字段默认值
        self.assertEqual(config.hard_routing_prob, 0.90,
            "hard_routing_prob 默认值应为 0.90")
        self.assertEqual(config.merge_alpha, 0.50,
            "merge_alpha 默认值应为 0.50")
        self.assertEqual(config.ks_alpha, 0.05,
            "ks_alpha 默认值应为 0.05")
        self.assertEqual(config.mixed_winsor_sigma, 3.0,
            "mixed_winsor_sigma 默认值应为 3.0")
        self.assertEqual(config.transform_aggressiveness, 1.0,
            "transform_aggressiveness 默认值应为 1.0")

        # 已有字段不受影响
        self.assertEqual(config.classification_threshold_static, 0.80)
        self.assertEqual(config.classification_threshold_dynamic, 0.40)
        self.assertEqual(config.migration_threshold, 0.10)
        self.assertEqual(config.migration_window, 12)
        self.assertEqual(config.fingerprint_window, 24)

        print(f"\n  手工校验通过:")
        print(f"    hard_routing_prob        = {config.hard_routing_prob}")
        print(f"    merge_alpha              = {config.merge_alpha}")
        print(f"    ks_alpha                 = {config.ks_alpha}")
        print(f"    mixed_winsor_sigma       = {config.mixed_winsor_sigma}")
        print(f"    transform_aggressiveness = {config.transform_aggressiveness}")

    def test_02_custom_values(self):
        """
        [P3-Phase1-02] 自定义值生效。

        手工校验: 传入自定义值，验证字段被正确设置。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified

        config = PipelineV2ConfigUnified(
            hard_routing_prob=0.75,
            merge_alpha=0.30,
            ks_alpha=0.10,
            mixed_winsor_sigma=4.5,
            transform_aggressiveness=2.0,
        )

        self.assertEqual(config.hard_routing_prob, 0.75)
        self.assertEqual(config.merge_alpha, 0.30)
        self.assertEqual(config.ks_alpha, 0.10)
        self.assertEqual(config.mixed_winsor_sigma, 4.5)
        self.assertEqual(config.transform_aggressiveness, 2.0)

        print(f"\n  手工校验通过: 所有自定义值正确")
        print(f"    hard_routing_prob        = {config.hard_routing_prob} (expected 0.75)")
        print(f"    merge_alpha              = {config.merge_alpha} (expected 0.30)")
        print(f"    ks_alpha                 = {config.ks_alpha} (expected 0.10)")
        print(f"    mixed_winsor_sigma       = {config.mixed_winsor_sigma} (expected 4.5)")
        print(f"    transform_aggressiveness = {config.transform_aggressiveness} (expected 2.0)")


class TestConfigExtensionConstraints(unittest.TestCase):
    """测试 2: 字段约束"""

    def test_03_hard_routing_prob_bounds(self):
        """
        [P3-Phase1-03] hard_routing_prob 边界约束。

        手工校验: 越界值应抛出 ValidationError。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified
        from pydantic import ValidationError

        # 低于下限
        with self.assertRaises(ValidationError):
            PipelineV2ConfigUnified(hard_routing_prob=0.4)

        # 高于上限
        with self.assertRaises(ValidationError):
            PipelineV2ConfigUnified(hard_routing_prob=1.1)

        # 边界值应通过
        config_lo = PipelineV2ConfigUnified(hard_routing_prob=0.5)
        self.assertEqual(config_lo.hard_routing_prob, 0.5)
        config_hi = PipelineV2ConfigUnified(hard_routing_prob=1.0)
        self.assertEqual(config_hi.hard_routing_prob, 1.0)

        print(f"\n  手工校验通过: 边界约束正确")
        print(f"    下限 0.5: OK, 上限 1.0: OK")
        print(f"    低于 0.5: ValidationError (正确)")
        print(f"    高于 1.0: ValidationError (正确)")

    def test_04_merge_alpha_bounds(self):
        """
        [P3-Phase1-04] merge_alpha 边界约束。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            PipelineV2ConfigUnified(merge_alpha=-0.1)
        with self.assertRaises(ValidationError):
            PipelineV2ConfigUnified(merge_alpha=1.1)

        config = PipelineV2ConfigUnified(merge_alpha=0.0)
        self.assertEqual(config.merge_alpha, 0.0)
        config = PipelineV2ConfigUnified(merge_alpha=1.0)
        self.assertEqual(config.merge_alpha, 1.0)

        print(f"\n  手工校验通过: merge_alpha [0.0, 1.0] 约束正确")

    def test_05_ks_alpha_bounds(self):
        """
        [P3-Phase1-05] ks_alpha 边界约束。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            PipelineV2ConfigUnified(ks_alpha=0.0005)
        with self.assertRaises(ValidationError):
            PipelineV2ConfigUnified(ks_alpha=0.6)

        config = PipelineV2ConfigUnified(ks_alpha=0.001)
        self.assertEqual(config.ks_alpha, 0.001)
        config = PipelineV2ConfigUnified(ks_alpha=0.5)
        self.assertEqual(config.ks_alpha, 0.5)

        print(f"\n  手工校验通过: ks_alpha [0.001, 0.5] 约束正确")

    def test_06_mixed_winsor_sigma_bounds(self):
        """
        [P3-Phase1-06] mixed_winsor_sigma 边界约束。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            PipelineV2ConfigUnified(mixed_winsor_sigma=0.5)
        with self.assertRaises(ValidationError):
            PipelineV2ConfigUnified(mixed_winsor_sigma=11.0)

        config = PipelineV2ConfigUnified(mixed_winsor_sigma=1.0)
        self.assertEqual(config.mixed_winsor_sigma, 1.0)
        config = PipelineV2ConfigUnified(mixed_winsor_sigma=10.0)
        self.assertEqual(config.mixed_winsor_sigma, 10.0)

        print(f"\n  手工校验通过: mixed_winsor_sigma [1.0, 10.0] 约束正确")

    def test_07_transform_aggressiveness_bounds(self):
        """
        [P3-Phase1-07] transform_aggressiveness 边界约束。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            PipelineV2ConfigUnified(transform_aggressiveness=0.2)
        with self.assertRaises(ValidationError):
            PipelineV2ConfigUnified(transform_aggressiveness=6.0)

        config = PipelineV2ConfigUnified(transform_aggressiveness=0.3)
        self.assertEqual(config.transform_aggressiveness, 0.3)
        config = PipelineV2ConfigUnified(transform_aggressiveness=5.0)
        self.assertEqual(config.transform_aggressiveness, 5.0)

        print(f"\n  手工校验通过: transform_aggressiveness [0.3, 5.0] 约束正确")


class TestConfigExtensionSerialization(unittest.TestCase):
    """测试 3: 序列化/反序列化"""

    def test_08_json_roundtrip(self):
        """
        [P3-Phase1-08] JSON 序列化往返。

        手工校验:  config → JSON → config，新字段值不变。
        """
        from factor_pipeline.config_v2 import (
            PipelineV2ConfigUnified,
            save_config_to_json,
            load_config_from_json
        )

        original = PipelineV2ConfigUnified(
            name="test_p3",
            hard_routing_prob=0.85,
            merge_alpha=0.45,
            ks_alpha=0.03,
            mixed_winsor_sigma=3.5,
            transform_aggressiveness=1.5,
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
            print(f"    hard_routing_prob: {json_content.get('hard_routing_prob')}")
            print(f"    merge_alpha: {json_content.get('merge_alpha')}")
            print(f"    ks_alpha: {json_content.get('ks_alpha')}")
            print(f"    mixed_winsor_sigma: {json_content.get('mixed_winsor_sigma')}")
            print(f"    transform_aggressiveness: {json_content.get('transform_aggressiveness')}")

            self.assertEqual(json_content['hard_routing_prob'], 0.85)
            self.assertEqual(json_content['merge_alpha'], 0.45)
            self.assertEqual(json_content['ks_alpha'], 0.03)
            self.assertEqual(json_content['mixed_winsor_sigma'], 3.5)
            self.assertEqual(json_content['transform_aggressiveness'], 1.5)

            # 反序列化
            loaded = load_config_from_json(tmp_path)
            self.assertEqual(loaded.hard_routing_prob, original.hard_routing_prob)
            self.assertEqual(loaded.merge_alpha, original.merge_alpha)
            self.assertEqual(loaded.ks_alpha, original.ks_alpha)
            self.assertEqual(loaded.mixed_winsor_sigma, original.mixed_winsor_sigma)
            self.assertEqual(loaded.transform_aggressiveness, original.transform_aggressiveness)

            print(f"\n  手工校验通过: JSON 往返一致")
        finally:
            os.unlink(tmp_path)

    def test_09_model_dump_includes_new_fields(self):
        """
        [P3-Phase1-09] model_dump() 包含新字段。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified

        config = PipelineV2ConfigUnified(
            hard_routing_prob=0.77,
            merge_alpha=0.33,
            ks_alpha=0.07,
            mixed_winsor_sigma=2.5,
            transform_aggressiveness=0.8,
        )

        dumped = config.model_dump()

        self.assertIn('hard_routing_prob', dumped)
        self.assertIn('merge_alpha', dumped)
        self.assertIn('ks_alpha', dumped)
        self.assertIn('mixed_winsor_sigma', dumped)
        self.assertIn('transform_aggressiveness', dumped)

        self.assertEqual(dumped['hard_routing_prob'], 0.77)
        self.assertEqual(dumped['merge_alpha'], 0.33)
        self.assertEqual(dumped['ks_alpha'], 0.07)
        self.assertEqual(dumped['mixed_winsor_sigma'], 2.5)
        self.assertEqual(dumped['transform_aggressiveness'], 0.8)

        print(f"\n  手工校验通过: model_dump() 包含全部新字段")


class TestConfigExtensionBackwardCompat(unittest.TestCase):
    """测试 4: 向后兼容"""

    def test_10_existing_configs_still_work(self):
        """
        [P3-Phase1-10] 已有字段不受影响。

        手工校验: 只使用已有字段构造 config，验证新字段取默认值。
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

        # 新字段应取默认值
        self.assertEqual(config.hard_routing_prob, 0.90)
        self.assertEqual(config.merge_alpha, 0.50)
        self.assertEqual(config.ks_alpha, 0.05)
        self.assertEqual(config.mixed_winsor_sigma, 3.0)
        self.assertEqual(config.transform_aggressiveness, 1.0)

        print(f"\n  手工校验通过: 向后兼容")
        print(f"    已有字段: 自定义值正确")
        print(f"    新字段: 默认值正确")

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
            hard_routing_prob=0.88,
            merge_alpha=0.55,
        )

        # 兼容层转换不应报错
        try:
            legacy = config.to_pipeline_config()
            self.assertIsNotNone(legacy)
            self.assertEqual(legacy.name, "compat_test")
            print(f"\n  手工校验通过: to_pipeline_config() 兼容层正常")
            print(f"    legacy.name = {legacy.name}")
        except Exception as e:
            self.fail(f"to_pipeline_config() 失败: {e}")


# =============================================================================
#                              测试运行器
# =============================================================================

def run_all_tests():
    """运行所有 Phase 1 配置扩展测试"""
    print("=" * 70)
    print("P3 Phase 1: 配置扩展 — TDD 测试套件")
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