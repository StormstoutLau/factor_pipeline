# -*- coding: utf-8 -*-
"""
P2: data_bridge.py — TDD 测试套件

测试 Pipeline → DataLoaderV3 数据适配器。
"""

import unittest

import pytest

# 可选依赖: Factor_Trading_v3_0 (pyproject.toml [backtest] extra)
# 所有测试均通过 DataBridge.create_dataloader 间接依赖 DataLoaderV3,
# 未安装 Factor_Trading_v3_0 时跳过整个文件.
pytest.importorskip("Factor_Trading_v3_0")

import numpy as np
import pandas as pd


# =============================================================================
# A. 格式转换
# =============================================================================

class TestDataBridgeFormat(unittest.TestCase):
    """测试 A: DataFrame → numpy 格式转换"""

    def test_01_transpose_factor_data(self):
        """
        [P2-A-01] Pipeline (stocks×dates) → DataLoaderV3 (dates×stocks)。

        手工计算: Pipeline DataFrame shape (n_stocks, n_dates)
        → 转置后 shape (n_dates, n_stocks)
        """
        from factor_pipeline.backtest.data_bridge import DataBridge

        n_stocks, n_dates = 10, 20
        processed_factors = {
            'factor_a': pd.DataFrame(
                np.random.randn(n_stocks, n_dates),
                index=[f's{i:03d}' for i in range(n_stocks)],
                columns=[f'2024-{m:02d}-01' for m in range(1, n_dates + 1)],
            ),
        }

        bridge = DataBridge()
        factor_arrays = bridge._transpose_factor_data(processed_factors)

        self.assertEqual(len(factor_arrays), 1)
        self.assertIn('factor_a', factor_arrays)

        arr = factor_arrays['factor_a']
        self.assertEqual(arr.shape, (n_dates, n_stocks),
            f"shape 应为 ({n_dates}, {n_stocks})，实际 {arr.shape}")

        # 手工验证: 第 0 行第 0 列 = 原始第 0 列第 0 行
        self.assertAlmostEqual(arr[0, 0], processed_factors['factor_a'].iloc[0, 0])

        print(f"\n  手工校验: transpose OK")
        print(f"    input shape: {(n_stocks, n_dates)}")
        print(f"    output shape: {arr.shape}")

    def test_02_build_price_dataframe(self):
        """
        [P2-A-02] 构建 price DataFrame (dates×stocks) 格式。

        手工计算: Pipeline 输出的 factor 列名即为价格数据的日期索引。
        """
        from factor_pipeline.backtest.data_bridge import DataBridge

        n_stocks, n_dates = 5, 10
        factor = pd.DataFrame(
            np.random.randn(n_stocks, n_dates),
            index=[f's{i:03d}' for i in range(n_stocks)],
            columns=[f'2024-{m:02d}-01' for m in range(1, n_dates + 1)],
        )

        # 模拟价格数据
        price_data = pd.DataFrame(
            np.random.randn(n_stocks, n_dates) * 100 + 100,
            index=factor.index,
            columns=factor.columns,
        )

        bridge = DataBridge()
        close_df = bridge._build_price_dataframe(price_data)

        self.assertEqual(close_df.shape, (n_dates, n_stocks),
            f"shape 应为 ({n_dates}, {n_stocks})，实际 {close_df.shape}")

        # 索引应为日期
        self.assertEqual(list(close_df.index), list(factor.columns))

        # 列应为股票
        self.assertEqual(list(close_df.columns), list(factor.index))

        print(f"\n  手工校验: price DataFrame OK")
        print(f"    shape: {close_df.shape}")

    def test_03_create_dataloader(self):
        """
        [P2-A-03] 从 Pipeline 输出创建 DataLoaderV3。

        手工校验: DataLoaderV3.price_data['close'] shape = (n_dates, n_stocks)
        """
        from factor_pipeline.backtest.data_bridge import DataBridge

        n_stocks, n_dates = 8, 15
        processed_factors = {
            'factor_a': pd.DataFrame(
                np.random.randn(n_stocks, n_dates),
                index=[f's{i:03d}' for i in range(n_stocks)],
                columns=[f'2024-{m:02d}-01' for m in range(1, n_dates + 1)],
            ),
        }

        price_data = pd.DataFrame(
            np.random.randn(n_stocks, n_dates) * 100 + 100,
            index=processed_factors['factor_a'].index,
            columns=processed_factors['factor_a'].columns,
        )

        bridge = DataBridge()
        # P1: 小数据集 (n_dates=15 < 默认 20) 需传 min_dates 避免被过滤
        dl = bridge.create_dataloader(
            processed_factors, price_data, min_dates={'factor_a': 10},
        )

        self.assertEqual(dl.price_data['close'].shape, (n_dates, n_stocks))
        self.assertEqual(dl.n_dates, n_dates)
        self.assertEqual(dl.n_stocks, n_stocks)

        # 因子数据
        self.assertIn('factor_a', dl.factor_data)
        self.assertEqual(dl.factor_data['factor_a'].shape, (n_dates, n_stocks))

        print(f"\n  手工校验: DataLoaderV3 创建成功")
        print(f"    n_dates={dl.n_dates}, n_stocks={dl.n_stocks}")
        print(f"    price close shape: {dl.price_data['close'].shape}")

    def test_04_multi_factor_dataloader(self):
        """
        [P2-A-04] 多个因子正确加载到 DataLoaderV3。
        """
        from factor_pipeline.backtest.data_bridge import DataBridge

        n_stocks, n_dates = 5, 10
        processed_factors = {
            'factor_a': pd.DataFrame(
                np.random.randn(n_stocks, n_dates),
                index=[f's{i:03d}' for i in range(n_stocks)],
                columns=[f'2024-{m:02d}-01' for m in range(1, n_dates + 1)],
            ),
            'factor_b': pd.DataFrame(
                np.random.randn(n_stocks, n_dates),
                index=[f's{i:03d}' for i in range(n_stocks)],
                columns=[f'2024-{m:02d}-01' for m in range(1, n_dates + 1)],
            ),
            'factor_c': pd.DataFrame(
                np.random.randn(n_stocks, n_dates),
                index=[f's{i:03d}' for i in range(n_stocks)],
                columns=[f'2024-{m:02d}-01' for m in range(1, n_dates + 1)],
            ),
        }

        price_data = pd.DataFrame(
            np.random.randn(n_stocks, n_dates) * 100 + 100,
            index=processed_factors['factor_a'].index,
            columns=processed_factors['factor_a'].columns,
        )

        bridge = DataBridge()
        # P1: 小数据集 (n_dates=10 < 默认 20) 需传 min_dates 避免被过滤
        dl = bridge.create_dataloader(
            processed_factors, price_data,
            min_dates={'factor_a': 5, 'factor_b': 5, 'factor_c': 5},
        )

        self.assertEqual(len(dl.factor_data), 3)
        for name in ['factor_a', 'factor_b', 'factor_c']:
            self.assertIn(name, dl.factor_data, f"因子 {name} 缺失")
            self.assertEqual(dl.factor_data[name].shape, (n_dates, n_stocks))

        print(f"\n  手工校验: {len(dl.factor_data)} 个因子全部加载")


# =============================================================================
# B. 形状验证
# =============================================================================

class TestDataBridgeValidation(unittest.TestCase):
    """测试 B: 形状验证"""

    def test_05_validate_shapes_pass(self):
        """
        [P2-B-05] 形状一致时验证通过。
        """
        from factor_pipeline.backtest.data_bridge import DataBridge

        n_stocks, n_dates = 10, 20
        processed_factors = {
            'f1': pd.DataFrame(
                np.random.randn(n_stocks, n_dates),
                index=[f's{i:03d}' for i in range(n_stocks)],
                columns=[f'2024-{m:02d}-01' for m in range(1, n_dates + 1)],
            ),
        }
        price_data = pd.DataFrame(
            np.random.randn(n_stocks, n_dates) * 100 + 100,
            index=processed_factors['f1'].index,
            columns=processed_factors['f1'].columns,
        )

        bridge = DataBridge()
        is_valid, msg = bridge.validate_shapes(processed_factors, price_data)

        self.assertTrue(is_valid, f"应通过验证: {msg}")

        print(f"\n  手工校验: 验证通过: {msg}")

    def test_06_validate_shapes_mismatch_index(self):
        """
        [P2-B-06] 因子和价格的 index (stocks) 不一致时验证失败。
        """
        from factor_pipeline.backtest.data_bridge import DataBridge

        n_stocks, n_dates = 10, 20
        processed_factors = {
            'f1': pd.DataFrame(
                np.random.randn(n_stocks, n_dates),
                index=[f's{i:03d}' for i in range(n_stocks)],
                columns=[f'2024-{m:02d}-01' for m in range(1, n_dates + 1)],
            ),
        }
        price_data = pd.DataFrame(
            np.random.randn(n_stocks + 2, n_dates) * 100 + 100,
            index=[f's{i:03d}' for i in range(n_stocks + 2)],
            columns=processed_factors['f1'].columns,
        )

        bridge = DataBridge()
        is_valid, msg = bridge.validate_shapes(processed_factors, price_data)

        self.assertFalse(is_valid, "股票数量不一致应验证失败")

        print(f"\n  手工校验: 验证失败 (预期): {msg}")

    def test_07_validate_shapes_mismatch_columns(self):
        """
        [P2-B-07] 因子和价格的 columns (dates) 不一致时验证失败。
        """
        from factor_pipeline.backtest.data_bridge import DataBridge

        n_stocks, n_dates = 10, 20
        price_data = pd.DataFrame(
            np.random.randn(n_stocks, n_dates) * 100 + 100,
            index=[f's{i:03d}' for i in range(n_stocks)],
            columns=[f'2024-{m:02d}-01' for m in range(1, n_dates + 1)],
        )
        processed_factors = {
            'f1': pd.DataFrame(
                np.random.randn(n_stocks, n_dates - 5),
                index=price_data.index,
                columns=[f'2024-{m:02d}-01' for m in range(1, n_dates - 4)],
            ),
        }

        bridge = DataBridge()
        is_valid, msg = bridge.validate_shapes(processed_factors, price_data)

        self.assertFalse(is_valid, "日期数量不一致应验证失败")

        print(f"\n  手工校验: 验证失败 (预期): {msg}")

    def test_08_validate_empty_factor_dict(self):
        """
        [P2-B-08] 空因子字典 → 验证失败。
        """
        from factor_pipeline.backtest.data_bridge import DataBridge

        bridge = DataBridge()
        price_data = pd.DataFrame(
            np.random.randn(10, 20) * 100 + 100,
            index=[f's{i:03d}' for i in range(10)],
            columns=[f'2024-{m:02d}-01' for m in range(1, 21)],
        )

        is_valid, msg = bridge.validate_shapes({}, price_data)

        self.assertFalse(is_valid, "空因子字典应验证失败")

        print(f"\n  手工校验: 验证失败 (预期): {msg}")


# =============================================================================
# C. 值一致性
# =============================================================================

class TestDataBridgeFidelity(unittest.TestCase):
    """测试 C: 值保真度"""

    def test_09_value_fidelity(self):
        """
        [P2-C-09] 转换后数值与原始数据完全一致。

        手工验证: 逐元素对比原始 DataFrame 和转换后的 numpy 数组。
        """
        from factor_pipeline.backtest.data_bridge import DataBridge

        np.random.seed(42)
        n_stocks, n_dates = 6, 12
        processed_factors = {
            'f1': pd.DataFrame(
                np.random.randn(n_stocks, n_dates),
                index=[f's{i:03d}' for i in range(n_stocks)],
                columns=[f'2024-{m:02d}-01' for m in range(1, n_dates + 1)],
            ),
        }
        price_data = pd.DataFrame(
            np.random.randn(n_stocks, n_dates) * 100 + 100,
            index=processed_factors['f1'].index,
            columns=processed_factors['f1'].columns,
        )

        bridge = DataBridge()
        # P1: 小数据集 (n_dates=12 < 默认 20) 需传 min_dates 避免被过滤
        dl = bridge.create_dataloader(
            processed_factors, price_data, min_dates={'f1': 5},
        )

        # 逐元素验证因子数据
        f_arr = dl.factor_data['f1']
        f_orig = processed_factors['f1'].values.T  # 转置后对比

        max_diff = np.max(np.abs(f_arr - f_orig))
        self.assertLess(max_diff, 1e-10,
            f"因子数据转换误差 {max_diff:.2e}")

        # 逐元素验证价格数据
        p_arr = dl.price_data['close']
        p_orig = price_data.values.T

        max_diff = np.max(np.abs(p_arr - p_orig))
        self.assertLess(max_diff, 1e-10,
            f"价格数据转换误差 {max_diff:.2e}")

        print(f"\n  手工校验: 值保真度")
        print(f"    factor max_diff={np.max(np.abs(f_arr - f_orig)):.2e}")
        print(f"    price max_diff={np.max(np.abs(p_arr - p_orig)):.2e}")

    def test_10_date_stock_maps(self):
        """
        [P2-C-10] DataLoaderV3 的 date_map 和 stock_map 正确。

        手工校验: date_map['2024-01-01'] = 0, stock_map['s000'] = 0
        """
        from factor_pipeline.backtest.data_bridge import DataBridge

        n_stocks, n_dates = 5, 8
        stocks = [f's{i:03d}' for i in range(n_stocks)]
        dates = [f'2024-{m:02d}-01' for m in range(1, n_dates + 1)]

        processed_factors = {
            'f1': pd.DataFrame(
                np.random.randn(n_stocks, n_dates),
                index=stocks,
                columns=dates,
            ),
        }
        price_data = pd.DataFrame(
            np.random.randn(n_stocks, n_dates) * 100 + 100,
            index=stocks,
            columns=dates,
        )

        bridge = DataBridge()
        dl = bridge.create_dataloader(processed_factors, price_data)

        self.assertEqual(dl.date_map[dates[0]], 0)
        self.assertEqual(dl.date_map[dates[-1]], n_dates - 1)
        self.assertEqual(dl.stock_map[stocks[0]], 0)
        self.assertEqual(dl.stock_map[stocks[-1]], n_stocks - 1)

        print(f"\n  手工校验: date_map & stock_map")
        print(f"    date_map['{dates[0]}'] = {dl.date_map[dates[0]]}")
        print(f"    stock_map['{stocks[0]}'] = {dl.stock_map[stocks[0]]}")


# =============================================================================
#                              测试运行器
# =============================================================================

def run_all_tests():
    print("=" * 70)
    print("P2: data_bridge.py — TDD 测试套件")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestDataBridgeFormat))
    suite.addTests(loader.loadTestsFromTestCase(TestDataBridgeValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestDataBridgeFidelity))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print(f"P2 测试结果: {result.testsRun} 运行, "
          f"{len(result.failures)} 失败, {len(result.errors)} 错误")
    print("=" * 70)

    return result


if __name__ == '__main__':
    run_all_tests()