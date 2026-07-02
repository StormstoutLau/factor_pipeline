# -*- coding: utf-8 -*-
"""
P2 修复严格测试套件 — TDD Red Phase

P2-6: 迁移显著性检验 (Kolmogorov-Smirnov)
P2-8: importlib 替代 sys.path
"""

import unittest
import numpy as np
import pandas as pd
from scipy import stats as sp_stats


# ============================================================================
#                    P2-6: 迁移显著性检验 (KS)
# ============================================================================

class TestKSMigrationSignificance(unittest.TestCase):
    """
    P2-6: 迁移显著性检验 (Kolmogorov-Smirnov)

    当前问题: get_transition_weights() 仅基于最近3期类型是否一致
    判断迁移，不做统计显著性检验。这可能导致噪声引起的误报。

    目标: 添加 KS 检验，只有分布显著不同时才确认迁移。
    """

    def setUp(self):
        """设置测试数据"""
        np.random.seed(42)
        n_stocks = 10
        self.dates = pd.date_range('2022-01-01', periods=30, freq='ME')

        # 历史数据 (静态因子特征)
        self.historical_data = pd.DataFrame(
            0.9 * np.random.randn(30, n_stocks) + 0.5,
            index=self.dates,
            columns=[f'S{i:03d}' for i in range(n_stocks)]
        )

        # 近期数据 (同分布 - 无迁移)
        self.recent_same = pd.DataFrame(
            0.9 * np.random.randn(30, n_stocks) + 0.5,
            index=self.dates,
            columns=[f'S{i:03d}' for i in range(n_stocks)]
        )

        # 近期数据 (不同分布 - 有迁移，均值偏移)
        self.recent_shifted = pd.DataFrame(
            0.9 * np.random.randn(30, n_stocks) - 0.5,  # 均值从 +0.5 变为 -0.5
            index=self.dates,
            columns=[f'S{i:03d}' for i in range(n_stocks)]
        )

        # 近期数据 (不同分布 - 方差变化)
        self.recent_volatile = pd.DataFrame(
            2.5 * np.random.randn(30, n_stocks) + 0.5,  # 方差从 0.9 变为 2.5
            index=self.dates,
            columns=[f'S{i:03d}' for i in range(n_stocks)]
        )

    # ==================================================================
    # 测试 1: 同分布 - KS 不显著
    # ==================================================================

    def test_29_ks_same_distribution_not_significant(self):
        """
        [P2-6-01] 同分布数据 KS 检验不显著

        手工验证: 当历史数据和近期数据来自同一分布时，
        KS 检验的 p 值应 > alpha，不拒绝原假设。
        """
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        # 手工计算: 对每列做 KS 检验
        manual_p_values = []
        for col in self.historical_data.columns:
            hist_vals = self.historical_data[col].dropna().values
            recent_vals = self.recent_same[col].dropna().values
            stat, p = sp_stats.ks_2samp(hist_vals, recent_vals)
            manual_p_values.append(p)

        manual_min_p = float(np.min(manual_p_values))
        print(f"\n  手工 KS 检验:")
        print(f"  各列 p 值: {[round(p, 4) for p in manual_p_values[:5]]}...")
        print(f"  最小 p 值: {manual_min_p:.4f}")

        # 程序计算
        is_sig, p_value, details = _ks_migration_significance(
            self.historical_data, self.recent_same, alpha=0.05
        )

        print(f"  程序 is_significant: {is_sig}")
        print(f"  程序 min_p_value: {p_value:.4f}")

        # 同分布不应显著
        self.assertFalse(is_sig,
            msg=f"同分布数据 KS 不应显著 (p={p_value:.4f})")

        # 程序 p 值应与手工计算一致
        self.assertAlmostEqual(p_value, manual_min_p, delta=0.05,
            msg=f"程序 p 值 ({p_value:.4f}) 应与手工最小 p 值 ({manual_min_p:.4f}) 接近")

        print(f"[PASS] P2-6-01: 同分布 KS 不显著，p={p_value:.4f}")

    # ==================================================================
    # 测试 2: 均值偏移 - KS 显著
    # ==================================================================

    def test_30_ks_mean_shift_significant(self):
        """
        [P2-6-02] 均值偏移数据 KS 检验显著

        手工验证: 当近期数据均值明显偏移时，
        KS 检验应拒绝原假设 (p < alpha)。
        """
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        # 手工计算
        manual_p_values = []
        for col in self.historical_data.columns:
            hist_vals = self.historical_data[col].dropna().values
            recent_vals = self.recent_shifted[col].dropna().values
            stat, p = sp_stats.ks_2samp(hist_vals, recent_vals)
            manual_p_values.append(p)

        manual_min_p = float(np.min(manual_p_values))
        print(f"\n  手工 KS 检验 (均值偏移):")
        print(f"  各列 p 值: {[round(p, 4) for p in manual_p_values[:5]]}...")
        print(f"  最小 p 值: {manual_min_p:.6f}")

        is_sig, p_value, details = _ks_migration_significance(
            self.historical_data, self.recent_shifted, alpha=0.05
        )

        print(f"  程序 is_significant: {is_sig}")
        print(f"  程序 min_p_value: {p_value:.6f}")

        # 均值显著偏移时应显著
        self.assertTrue(is_sig,
            msg=f"均值偏移数据 KS 应显著 (p={p_value:.6f})")

        print(f"[PASS] P2-6-02: 均值偏移 KS 显著，p={p_value:.6f}")

    # ==================================================================
    # 测试 3: 方差变化 - KS 显著
    # ==================================================================

    def test_31_ks_variance_change_significant(self):
        """
        [P2-6-03] 方差变化数据 KS 检验显著

        手工验证: 当近期数据方差明显增大时，
        KS 检验应拒绝原假设。
        """
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        manual_p_values = []
        for col in self.historical_data.columns:
            hist_vals = self.historical_data[col].dropna().values
            recent_vals = self.recent_volatile[col].dropna().values
            stat, p = sp_stats.ks_2samp(hist_vals, recent_vals)
            manual_p_values.append(p)

        manual_min_p = float(np.min(manual_p_values))
        print(f"\n  手工 KS 检验 (方差变化):")
        print(f"  各列 p 值: {[round(p, 4) for p in manual_p_values[:5]]}...")
        print(f"  最小 p 值: {manual_min_p:.6f}")

        is_sig, p_value, details = _ks_migration_significance(
            self.historical_data, self.recent_volatile, alpha=0.05
        )

        print(f"  程序 is_significant: {is_sig}")
        print(f"  程序 min_p_value: {p_value:.6f}")

        self.assertTrue(is_sig,
            msg=f"方差变化数据 KS 应显著 (p={p_value:.6f})")

        print(f"[PASS] P2-6-03: 方差变化 KS 显著，p={p_value:.6f}")

    # ==================================================================
    # 测试 4: 单列数据 KS 检验
    # ==================================================================

    def test_32_ks_single_column(self):
        """
        [P2-6-04] 单列数据 KS 检验

        手工验证: 单列因子数据也能正确进行 KS 检验。
        """
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        # 单列数据 (Series)
        hist_series = self.historical_data['S000']
        recent_series = self.recent_shifted['S000']

        is_sig, p_value, details = _ks_migration_significance(
            hist_series, recent_series, alpha=0.05
        )

        # 手工 KS 检验
        stat, manual_p = sp_stats.ks_2samp(
            hist_series.dropna().values,
            recent_series.dropna().values
        )

        print(f"\n  手工 KS: stat={stat:.4f}, p={manual_p:.6f}")
        print(f"  程序: is_sig={is_sig}, p={p_value:.6f}")

        self.assertAlmostEqual(p_value, manual_p, delta=0.01,
            msg=f"单列 p 值应一致: 程序={p_value:.6f}, 手工={manual_p:.6f}")

        print(f"[PASS] P2-6-04: 单列 KS 检验一致")

    # ==================================================================
    # 测试 5: 自定义 alpha 阈值
    # ==================================================================

    def test_33_ks_custom_alpha(self):
        """
        [P2-6-05] 自定义显著性水平

        手工验证: 不同的 alpha 影响 is_significant 判断。
        """
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        # 同分布数据，alpha=0.01 时不应显著
        is_sig_01, p_01, _ = _ks_migration_significance(
            self.historical_data, self.recent_same, alpha=0.01
        )
        # alpha=0.50 时可能显著 (取决于数据)
        is_sig_50, p_50, _ = _ks_migration_significance(
            self.historical_data, self.recent_same, alpha=0.50
        )

        print(f"\n  同分布: alpha=0.01 -> is_sig={is_sig_01}, p={p_01:.4f}")
        print(f"  同分布: alpha=0.50 -> is_sig={is_sig_50}, p={p_50:.4f}")

        # p 值应相同（不受 alpha 影响）
        self.assertAlmostEqual(p_01, p_50, delta=0.001,
            msg="p 值不应受 alpha 影响")

        # 偏移数据，alpha=0.01 时也应显著
        is_sig_shift, p_shift, _ = _ks_migration_significance(
            self.historical_data, self.recent_shifted, alpha=0.01
        )
        self.assertTrue(is_sig_shift,
            msg=f"均值偏移在 alpha=0.01 也应显著 (p={p_shift:.6f})")

        print(f"[PASS] P2-6-05: 自定义 alpha 正确")

    # ==================================================================
    # 测试 6: 空数据边界情况
    # ==================================================================

    def test_34_ks_empty_data(self):
        """
        [P2-6-06] 空数据边界情况

        手工验证: 空数据时不崩溃，返回非显著。
        """
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        empty_df = pd.DataFrame()
        is_sig, p_value, details = _ks_migration_significance(
            empty_df, empty_df, alpha=0.05
        )

        print(f"\n  空数据: is_sig={is_sig}, p={p_value}")

        self.assertFalse(is_sig, msg="空数据应返回非显著")
        self.assertEqual(p_value, 1.0, msg="空数据 p 值应为 1.0")

        print(f"[PASS] P2-6-06: 空数据边界正确处理")


# ============================================================================
#                    P2-8: importlib 替代 sys.path
# ============================================================================

class TestImportlibRefactor(unittest.TestCase):
    """
    P2-8: 动态导入改用 importlib + 上下文管理器

    当前问题: _import_external_class() 使用 sys.path.insert(0, ...)
    全局修改 sys.path，可能导致模块导入污染。

    目标: 使用 importlib.util + 上下文管理器临时添加路径，
    导入完成后自动恢复 sys.path。
    """

    def setUp(self):
        """设置测试数据"""
        pass

    # ==================================================================
    # 测试 7: sys.path 在导入后恢复
    # ==================================================================

    def test_35_sys_path_restored_after_import(self):
        """
        [P2-8-01] 导入后 sys.path 恢复原状

        手工验证: 调用 _import_external_class 后，
        sys.path 应与调用前完全一致。
        """
        import sys
        from factor_pipeline.adapters import _import_external_class

        path_before = list(sys.path)
        path_before_len = len(path_before)

        # 尝试导入一个不存在的模块
        result = _import_external_class(
            '../NonExistent',
            'does.not.exist',
            'NonExistentClass'
        )

        path_after = list(sys.path)

        print(f"\n  sys.path 长度变化: {path_before_len} -> {len(path_after)}")
        print(f"  导入结果: {result}")

        self.assertEqual(len(path_before), len(path_after),
            msg=f"sys.path 长度应保持不变: {path_before_len} vs {len(path_after)}")

        # 验证路径内容一致
        self.assertEqual(path_before, path_after,
            msg="sys.path 内容应完全一致")

        print(f"[PASS] P2-8-01: sys.path 导入后恢复")

    # ==================================================================
    # 测试 8: 成功导入后 sys.path 恢复
    # ==================================================================

    def test_36_sys_path_restored_after_successful_import(self):
        """
        [P2-8-02] 成功导入后 sys.path 恢复

        手工验证: 即使成功导入外部模块，
        sys.path 也应恢复原状。

        v2.4.0 (ADR-019): 5 个处理模块已内化, 改用 Factor_DB 测试
        _import_external_class (Factor_DB 仍为外部数据边界模块)
        """
        import sys
        from factor_pipeline.adapters import _import_external_class
        import os

        path_before = list(sys.path)

        # v2.4.0: 使用 Factor_DB 替代已内化的 Factor_Imputer
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'Factor_DB'
        )

        if os.path.isdir(db_path):
            result = _import_external_class(
                os.path.join('..', 'Factor_DB'),
                'query.factor_query',
                'FactorQuery'
            )
            print(f"\n  导入结果: {result}")
        else:
            print(f"\n  Factor_DB 目录不存在，跳过测试")
            self.skipTest("Factor_DB 不可用")

        path_after = list(sys.path)

        self.assertEqual(len(path_before), len(path_after),
            msg="sys.path 长度应保持不变")
        self.assertEqual(path_before, path_after,
            msg="sys.path 内容应完全一致")

        print(f"[PASS] P2-8-02: 成功导入后 sys.path 恢复")

    # ==================================================================
    # 测试 9: 异常时 sys.path 也恢复
    # ==================================================================

    def test_37_sys_path_restored_on_exception(self):
        """
        [P2-8-03] 导入异常时 sys.path 也恢复

        手工验证: 即使导入过程中抛出异常，
        sys.path 也应恢复原状。
        """
        import sys
        from factor_pipeline.adapters import _import_external_class

        path_before = list(sys.path)
        path_before_len = len(path_before)

        # 尝试导入一个会触发异常的模块路径
        try:
            result = _import_external_class(
                '../NonExistent' * 10,  # 极深的无效路径
                'invalid.module.path',
                'InvalidClass'
            )
        except Exception:
            pass  # 预期可能抛出异常

        path_after = list(sys.path)

        print(f"\n  sys.path 长度: {path_before_len} -> {len(path_after)}")

        self.assertEqual(len(path_before), len(path_after),
            msg="异常后 sys.path 长度应保持不变")
        self.assertEqual(path_before, path_after,
            msg="异常后 sys.path 内容应完全一致")

        print(f"[PASS] P2-8-03: 异常后 sys.path 恢复")

    # ==================================================================
    # 测试 10: 并发安全性基本检查
    # ==================================================================

    def test_38_sys_path_no_leakage(self):
        """
        [P2-8-04] 连续导入无路径泄漏

        手工验证: 连续多次调用 _import_external_class，
        sys.path 不应累积额外路径。
        """
        import sys
        from factor_pipeline.adapters import _import_external_class

        path_before = list(sys.path)
        path_before_len = len(path_before)

        # 连续多次导入
        for _ in range(5):
            _import_external_class(
                '../NonExistent',
                'module.path',
                'SomeClass'
            )

        path_after = list(sys.path)

        print(f"\n  5次导入后 sys.path 长度: {len(path_after)} (原始: {path_before_len})")

        self.assertEqual(len(path_before), len(path_after),
            msg=f"多次导入后 sys.path 不应变化: {path_before_len} vs {len(path_after)}")

        print(f"[PASS] P2-8-04: 连续导入无路径泄漏")

    # ==================================================================
    # 测试 11: 正常导入功能不受影响
    # ==================================================================

    def test_39_import_functionality_preserved(self):
        """
        [P2-8-05] 导入功能不受影响

        手工验证: 重构后仍能正常导入外部模块。

        v2.4.0 (ADR-019): 5 个处理模块已内化, 改用 Factor_DB 测试
        _import_external_class (Factor_DB 仍为外部数据边界模块)
        """
        import os
        from factor_pipeline.adapters import _import_external_class

        # v2.4.0: 使用 Factor_DB 替代已内化的 Factor_Imputer
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'Factor_DB'
        )

        if os.path.isdir(db_path):
            result = _import_external_class(
                os.path.join('..', 'Factor_DB'),
                'query.factor_query',
                'FactorQuery'
            )
            print(f"\n  导入结果: {result}")
            self.assertIsNotNone(result,
                msg="正常导入应返回有效类")
            print(f"[PASS] P2-8-05: 导入功能正常")
        else:
            self.skipTest("Factor_DB 不可用")


# =============================================================================
#                              测试运行器
# =============================================================================

def run_all_tests():
    """运行所有 P2 修复测试"""
    print("=" * 70)
    print("P2 修复严格测试套件 — TDD Red Phase")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestKSMigrationSignificance))
    suite.addTests(loader.loadTestsFromTestCase(TestImportlibRefactor))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print(f"P2 测试结果: {result.testsRun} 运行, "
          f"{len(result.failures)} 失败, {len(result.errors)} 错误, "
          f"{len(getattr(result, 'skipped', []))} 跳过")
    print("=" * 70)

    return result


if __name__ == '__main__':
    run_all_tests()