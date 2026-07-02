# -*- coding: utf-8 -*-
"""
P1: factor_metrics.py — TDD 测试套件

测试因子级指标计算函数，每项包含手工计算校验。
所有函数为纯计算，输入 numpy arrays，输出 float 或 np.ndarray。
"""

import unittest
import numpy as np
from scipy import stats


# =============================================================================
# A. Rank IC
# =============================================================================

class TestRankIC(unittest.TestCase):
    """测试 R1: compute_rank_ic"""

    def test_01_rank_ic_perfect_positive(self):
        """
        [P1-R1-01] 完美正相关 → Rank IC = 1.0。

        手工计算: factor = [1, 2, 3, 4, 5], return = [1, 2, 3, 4, 5]
        Spearman rank correlation = 1.0
        """
        from factor_pipeline.backtest.factor_metrics import compute_rank_ic

        factor = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        fwd_ret = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        result = compute_rank_ic(factor, fwd_ret)

        expected = 1.0
        self.assertAlmostEqual(result, expected, places=10)

        print(f"\n  手工校验: rank_ic={result:.6f} (expected {expected})")

    def test_02_rank_ic_perfect_negative(self):
        """
        [P1-R1-02] 完美负相关 → Rank IC = -1.0。

        手工计算: factor = [1, 2, 3, 4, 5], return = [5, 4, 3, 2, 1]
        Spearman rank correlation = -1.0
        """
        from factor_pipeline.backtest.factor_metrics import compute_rank_ic

        factor = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        fwd_ret = np.array([5.0, 4.0, 3.0, 2.0, 1.0])

        result = compute_rank_ic(factor, fwd_ret)

        expected = -1.0
        self.assertAlmostEqual(result, expected, places=10)

        print(f"\n  手工校验: rank_ic={result:.6f} (expected {expected})")

    def test_03_rank_ic_known_dataset(self):
        """
        [P1-R1-03] 已知数据集手工验证。

        手工计算: scipy.stats.spearmanr
        factor = [1, 3, 2, 5, 4], return = [2, 1, 4, 3, 5]
        """
        from factor_pipeline.backtest.factor_metrics import compute_rank_ic

        np.random.seed(42)
        factor = np.array([1.0, 3.0, 2.0, 5.0, 4.0])
        fwd_ret = np.array([2.0, 1.0, 4.0, 3.0, 5.0])

        result = compute_rank_ic(factor, fwd_ret)

        expected, _ = stats.spearmanr(factor, fwd_ret)
        self.assertAlmostEqual(result, expected, places=10,
            msg=f"rank_ic={result} != scipy.stats.spearmanr={expected}")

        print(f"\n  手工校验: rank_ic={result:.6f} (scipy.spearmanr={expected:.6f})")

    def test_04_rank_ic_with_nan(self):
        """
        [P1-R1-04] 包含 NaN 值时正确跳过。

        factor = [1, 2, NaN, 4, 5], return = [1, 2, 3, 4, NaN]
        仅有效配对: (1,1), (2,2), (4,4) → rank_ic = 1.0
        """
        from factor_pipeline.backtest.factor_metrics import compute_rank_ic

        factor = np.array([1.0, 2.0, np.nan, 4.0, 5.0])
        fwd_ret = np.array([1.0, 2.0, 3.0, 4.0, np.nan])

        result = compute_rank_ic(factor, fwd_ret)

        expected = 1.0
        self.assertAlmostEqual(result, expected, places=10)

        print(f"\n  手工校验: rank_ic={result:.6f} (expected {expected})")

    def test_05_rank_ic_insufficient_data(self):
        """
        [P1-R1-05] 不足 3 个有效配对 → 返回 NaN。

        factor = [1, NaN, NaN, NaN, 5], return = [1, NaN, NaN, NaN, NaN]
        仅 1 个有效配对
        """
        from factor_pipeline.backtest.factor_metrics import compute_rank_ic

        factor = np.array([1.0, np.nan, np.nan, np.nan, 5.0])
        fwd_ret = np.array([1.0, np.nan, np.nan, np.nan, np.nan])

        result = compute_rank_ic(factor, fwd_ret)

        self.assertTrue(np.isnan(result),
            f"不足 3 个有效配对应返回 NaN，实际 {result}")

        print(f"\n  手工校验: 不足数据 → NaN: {np.isnan(result)}")

    def test_06_rank_ic_random(self):
        """
        [P1-R1-06] 随机数据 vs scipy.stats.spearmanr 一致性。

        手工计算: 100 个随机值，scipy 验证。
        """
        from factor_pipeline.backtest.factor_metrics import compute_rank_ic

        np.random.seed(123)
        n = 100
        factor = np.random.randn(n)
        fwd_ret = 0.3 * factor + 0.7 * np.random.randn(n)

        result = compute_rank_ic(factor, fwd_ret)
        expected, _ = stats.spearmanr(factor, fwd_ret)

        self.assertAlmostEqual(result, expected, places=10)

        print(f"\n  手工校验: rank_ic={result:.6f} (scipy.spearmanr={expected:.6f})")


# =============================================================================
# B. Pearson IC
# =============================================================================

class TestPearsonIC(unittest.TestCase):
    """测试 R2: compute_pearson_ic"""

    def test_07_pearson_ic_vs_numpy(self):
        """
        [P1-R2-07] Pearson IC = numpy.corrcoef。

        手工计算: np.corrcoef(factor, return)[0,1]
        """
        from factor_pipeline.backtest.factor_metrics import compute_pearson_ic

        np.random.seed(42)
        n = 50
        factor = np.random.randn(n)
        fwd_ret = 0.4 * factor + 0.6 * np.random.randn(n)

        result = compute_pearson_ic(factor, fwd_ret)
        expected = np.corrcoef(factor, fwd_ret)[0, 1]

        self.assertAlmostEqual(result, expected, places=10)

        print(f"\n  手工校验: pearson_ic={result:.6f} (np.corrcoef={expected:.6f})")

    def test_08_pearson_ic_with_nan(self):
        """
        [P1-R2-08] 包含 NaN 时正确跳过。
        """
        from factor_pipeline.backtest.factor_metrics import compute_pearson_ic

        factor = np.array([1.0, 2.0, np.nan, 4.0, 5.0])
        fwd_ret = np.array([1.0, 2.0, 3.0, 4.0, np.nan])

        result = compute_pearson_ic(factor, fwd_ret)

        expected = np.corrcoef([1.0, 2.0, 4.0], [1.0, 2.0, 4.0])[0, 1]
        self.assertAlmostEqual(result, expected, places=10)

        print(f"\n  手工校验: pearson_ic={result:.6f} (expected {expected:.6f})")


# =============================================================================
# C. IC Series
# =============================================================================

class TestICSeries(unittest.TestCase):
    """测试 R3: compute_ic_series"""

    def test_09_ic_series_rank(self):
        """
        [P1-R3-09] Rank IC 序列计算正确。

        手工计算: 对每期 (factor[:, t], return[:, t+1]) 计算 spearmanr。
        """
        from factor_pipeline.backtest.factor_metrics import compute_ic_series

        np.random.seed(42)
        n_stocks, n_periods = 20, 10
        factor = np.random.randn(n_stocks, n_periods)
        returns = np.random.randn(n_stocks, n_periods)

        result = compute_ic_series(factor, returns, method='rank')

        # 手工计算
        expected = np.zeros(n_periods - 1)
        for t in range(n_periods - 1):
            valid = ~(np.isnan(factor[:, t]) | np.isnan(returns[:, t + 1]))
            if valid.sum() >= 3:
                expected[t], _ = stats.spearmanr(
                    factor[valid, t], returns[valid, t + 1]
                )
            else:
                expected[t] = np.nan

        for t in range(n_periods - 1):
            if not np.isnan(expected[t]):
                self.assertAlmostEqual(result[t], expected[t], places=10,
                    msg=f"t={t}: {result[t]} != {expected[t]}")

        print(f"\n  手工校验: IC series length={len(result)}")
        print(f"    mean IC={np.nanmean(result):.6f}")

    def test_10_ic_series_pearson(self):
        """
        [P1-R3-10] Pearson IC 序列计算正确。
        """
        from factor_pipeline.backtest.factor_metrics import compute_ic_series

        np.random.seed(42)
        factor = np.random.randn(20, 10)
        returns = np.random.randn(20, 10)

        result = compute_ic_series(factor, returns, method='pearson')

        expected = np.zeros(9)
        for t in range(9):
            valid = ~(np.isnan(factor[:, t]) | np.isnan(returns[:, t + 1]))
            if valid.sum() >= 3:
                expected[t] = np.corrcoef(
                    factor[valid, t], returns[valid, t + 1]
                )[0, 1]

        for t in range(9):
            if not np.isnan(expected[t]):
                self.assertAlmostEqual(result[t], expected[t], places=10)

        print(f"\n  手工校验: Pearson IC series mean={np.nanmean(result):.6f}")


# =============================================================================
# D. ICIR
# =============================================================================

class TestICIR(unittest.TestCase):
    """测试 R4: compute_icir"""

    def test_11_icir_known_series(self):
        """
        [P1-R4-11] ICIR = mean(IC) / std(IC)。

        手工计算: IC = [0.05, 0.06, 0.04, 0.07, 0.03]
        mean = 0.05, std = 0.0158, ICIR = 3.162
        """
        from factor_pipeline.backtest.factor_metrics import compute_icir

        ic_series = np.array([0.05, 0.06, 0.04, 0.07, 0.03])

        result = compute_icir(ic_series)

        expected = np.mean(ic_series) / np.std(ic_series, ddof=1)
        self.assertAlmostEqual(result, expected, places=6)

        print(f"\n  手工校验: ICIR={result:.6f} (expected {expected:.6f})")

    def test_12_icir_constant_ic(self):
        """
        [P1-R4-12] 常数 IC → std=0 → ICIR = inf → 返回 NaN。

        手工计算: IC = [0.05, 0.05, 0.05], std=0
        """
        from factor_pipeline.backtest.factor_metrics import compute_icir

        ic_series = np.array([0.05, 0.05, 0.05])

        result = compute_icir(ic_series)

        self.assertTrue(np.isnan(result) or np.isinf(result),
            f"常数 IC 应返回 NaN 或 inf，实际 {result}")

        print(f"\n  手工校验: 常数 IC → {result}")

    def test_13_icir_with_nan(self):
        """
        [P1-R4-13] 包含 NaN 的 IC 序列。

        IC = [0.05, NaN, 0.04, NaN, 0.03]
        mean = 0.04, std = 0.01, ICIR = 4.0
        """
        from factor_pipeline.backtest.factor_metrics import compute_icir

        ic_series = np.array([0.05, np.nan, 0.04, np.nan, 0.03])

        result = compute_icir(ic_series)

        clean = ic_series[~np.isnan(ic_series)]
        expected = np.mean(clean) / np.std(clean, ddof=1)
        self.assertAlmostEqual(result, expected, places=6)

        print(f"\n  手工校验: ICIR={result:.6f} (expected {expected:.6f})")

    def test_14_icir_insufficient_data(self):
        """
        [P1-R4-14] 少于 3 个有效值 → NaN。
        """
        from factor_pipeline.backtest.factor_metrics import compute_icir

        result = compute_icir(np.array([0.05, np.nan]))

        self.assertTrue(np.isnan(result),
            f"不足 3 个有效值应返回 NaN，实际 {result}")

        print(f"\n  手工校验: 不足数据 → NaN: {np.isnan(result)}")


# =============================================================================
# E. IC Decay
# =============================================================================

class TestICDecay(unittest.TestCase):
    """测试 R5: compute_ic_decay"""

    def test_15_ic_decay_lag1(self):
        """
        [P1-R5-15] IC decay lag=1 对应的 IC。

        手工计算: 使用 factor[:, t] 和 return[:, t+1] 的 IC。
        """
        from factor_pipeline.backtest.factor_metrics import compute_ic_decay

        np.random.seed(42)
        factor = np.random.randn(20, 20)
        returns = np.random.randn(20, 20)

        result = compute_ic_decay(factor, returns, max_lag=3)

        # 手工计算 lag=1
        ic_lag1 = []
        for t in range(19):
            valid = ~(np.isnan(factor[:, t]) | np.isnan(returns[:, t + 1]))
            if valid.sum() >= 3:
                ic, _ = stats.spearmanr(factor[valid, t], returns[valid, t + 1])
                ic_lag1.append(ic)

        expected_lag1 = np.mean(ic_lag1)
        self.assertAlmostEqual(result[0], expected_lag1, places=6)

        print(f"\n  手工校验: decay[0]={result[0]:.6f} (expected {expected_lag1:.6f})")

    def test_16_ic_decay_lag2(self):
        """
        [P1-R5-16] IC decay lag=2: factor[:, t] → return[:, t+2]。

        手工计算: 使用 factor[:, t] 和 return[:, t+2] 的 IC。
        """
        from factor_pipeline.backtest.factor_metrics import compute_ic_decay

        np.random.seed(42)
        factor = np.random.randn(20, 20)
        returns = np.random.randn(20, 20)

        result = compute_ic_decay(factor, returns, max_lag=5)

        # 手工计算 lag=2
        ic_lag2 = []
        for t in range(18):
            valid = ~(np.isnan(factor[:, t]) | np.isnan(returns[:, t + 2]))
            if valid.sum() >= 3:
                ic, _ = stats.spearmanr(factor[valid, t], returns[valid, t + 2])
                ic_lag2.append(ic)

        expected_lag2 = np.mean(ic_lag2)
        self.assertAlmostEqual(result[1], expected_lag2, places=6)

        print(f"\n  手工校验: decay[1]={result[1]:.6f} (expected {expected_lag2:.6f})")

    def test_17_ic_decay_length(self):
        """
        [P1-R5-17] 输出长度 = max_lag。

        max_lag=6 → 输出长度 = 6
        """
        from factor_pipeline.backtest.factor_metrics import compute_ic_decay

        np.random.seed(42)
        factor = np.random.randn(20, 30)
        returns = np.random.randn(20, 30)

        result = compute_ic_decay(factor, returns, max_lag=6)

        self.assertEqual(len(result), 6,
            f"输出长度应为 6，实际 {len(result)}")

        print(f"\n  手工校验: decay length={len(result)} (expected 6)")

    def test_18_ic_decay_insufficient_data(self):
        """
        [P1-R5-18] 数据不足 max_lag 时，返回最大可用长度。

        n_periods=5, max_lag=10 → 输出长度 = 4（5-1=4 期可用）
        """
        from factor_pipeline.backtest.factor_metrics import compute_ic_decay

        np.random.seed(42)
        factor = np.random.randn(20, 5)
        returns = np.random.randn(20, 5)

        result = compute_ic_decay(factor, returns, max_lag=10)

        self.assertEqual(len(result), 4,
            f"输出长度应为 4，实际 {len(result)}")

        print(f"\n  手工校验: 不足数据 → decay length={len(result)} (expected 4)")


# =============================================================================
# F. Turnover
# =============================================================================

class TestTurnover(unittest.TestCase):
    """测试 R6: compute_turnover"""

    def test_19_turnover_identical(self):
        """
        [P1-R6-19] 完全相同的仓位 → 换手率 = 0。

        手工计算: positions = [[1,0,0], [1,0,0], [1,0,0]]
        turnover = mean(|w_t - w_{t-1}|) / 2 = 0
        """
        from factor_pipeline.backtest.factor_metrics import compute_turnover

        positions = np.array([
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
        ])

        result = compute_turnover(positions)

        self.assertAlmostEqual(np.mean(result), 0.0, places=10)

        print(f"\n  手工校验: turnover={np.mean(result):.6f} (expected 0.0)")

    def test_20_turnover_full_rotation(self):
        """
        [P1-R6-20] 完全旋转 → 换手率 = 1.0。

        手工计算: positions = [[1,0], [0,1]]
        turnover = |1-0| + |0-1| = 2, / 2 = 1.0
        """
        from factor_pipeline.backtest.factor_metrics import compute_turnover

        positions = np.array([
            [1.0, 0.0],
            [0.0, 1.0],
        ])

        result = compute_turnover(positions)

        expected = 1.0
        self.assertAlmostEqual(result[0], expected, places=10)

        print(f"\n  手工校验: turnover[0]={result[0]:.6f} (expected {expected})")

    def test_21_turnover_partial(self):
        """
        [P1-R6-21] 部分换手。

        手工计算: positions = [[0.5, 0.3, 0.2], [0.3, 0.5, 0.2]]
        turnover = |0.5-0.3| + |0.3-0.5| + |0.2-0.2| = 0.4, / 2 = 0.2
        """
        from factor_pipeline.backtest.factor_metrics import compute_turnover

        positions = np.array([
            [0.5, 0.3, 0.2],
            [0.3, 0.5, 0.2],
        ])

        result = compute_turnover(positions)

        expected = 0.2
        self.assertAlmostEqual(result[0], expected, places=10)

        print(f"\n  手工校验: turnover[0]={result[0]:.6f} (expected {expected})")

    def test_22_turnover_random(self):
        """
        [P1-R6-22] 随机仓位 vs 手工计算一致性。

        手工计算: turnover[t] = sum(|pos[t] - pos[t-1]|) / 2
        """
        from factor_pipeline.backtest.factor_metrics import compute_turnover

        np.random.seed(42)
        n_dates, n_stocks = 10, 5
        positions = np.random.rand(n_dates, n_stocks)
        # 归一化使每行和为 1
        positions = positions / positions.sum(axis=1, keepdims=True)

        result = compute_turnover(positions)

        # 手工计算
        expected = np.zeros(n_dates - 1)
        for t in range(1, n_dates):
            expected[t - 1] = np.sum(np.abs(positions[t] - positions[t - 1])) / 2.0

        for t in range(n_dates - 1):
            self.assertAlmostEqual(result[t], expected[t], places=10,
                msg=f"t={t}: {result[t]} != {expected[t]}")

        print(f"\n  手工校验: 10 期平均 turnover={np.mean(result):.6f}")


# =============================================================================
# G. Long-Short Returns
# =============================================================================

class TestLongShortReturns(unittest.TestCase):
    """测试 R7: compute_long_short_returns"""

    def test_23_ls_returns_known(self):
        """
        [P1-R7-23] 多空收益计算正确。

        手工计算: factor = [1,2,3,4,5], top_n=0.4 → long=[4,5], short=[1,2]
        return = [0.01, 0.02, 0.03, 0.04, 0.05]
        ls_ret = mean([0.04,0.05]) - mean([0.01,0.02]) = 0.045 - 0.015 = 0.03
        """
        from factor_pipeline.backtest.factor_metrics import compute_long_short_returns

        factor = np.array([
            [1.0, 2.0, 3.0, 4.0, 5.0],    # t=0: sorted ascending
            [2.0, 1.0, 4.0, 3.0, 5.0],    # t=1: sorted → [1,2,3,4,5]
            [3.0, 2.0, 1.0, 5.0, 4.0],    # t=2: not used in assertions
        ]).T  # shape (5, 3): 5 stocks × 3 periods

        # 手工计算:
        # t=0: factor=[1,2,3,4,5], ret=[0.01,0.02,0.03,0.04,0.05]
        #   long=[4,5]→ret=0.045, short=[1,2]→ret=0.015, ls=0.03
        # t=1: factor=[2,1,4,3,5], ret=[0.02,0.01,0.04,0.03,0.05]
        #   sorted→[1,0,3,2,4], long=[4,5]→ret=0.045, short=[1,2]→ret=0.015, ls=0.03
        returns = np.array([
            [0.00, 0.00, 0.00, 0.00, 0.00],  # t=0
            [0.01, 0.02, 0.03, 0.04, 0.05],  # t=1 → forward for t=0
            [0.02, 0.01, 0.04, 0.03, 0.05],  # t=2 → forward for t=1
        ]).T  # shape (5, 3)

        result = compute_long_short_returns(factor, returns, top_n=2)

        # 手工计算 t=0: factor=[1,2,3,4,5], ret=[0.01,0.02,0.03,0.04,0.05]
        # long=[4,5] → ret=0.045, short=[1,2] → ret=0.015, ls=0.03
        self.assertAlmostEqual(result[0], 0.03, places=10)

        # t=1: factor=[2,1,4,3,5], ret=[0.02,0.01,0.04,0.03,0.05]
        # long=[4,5] → ret=0.045, short=[1,2] → ret=0.015, ls=0.03
        self.assertAlmostEqual(result[1], 0.03, places=10)

        print(f"\n  手工校验: ls_returns={result} (expected [0.03, 0.03])")

    def test_24_ls_returns_top_pct(self):
        """
        [P1-R7-24] top_n 为 float → 按比例选股。

        top_n=0.4, n=10 → 取 top 4 和 bottom 4
        """
        from factor_pipeline.backtest.factor_metrics import compute_long_short_returns

        np.random.seed(42)
        factor = np.random.randn(10, 5)
        returns = np.random.randn(10, 5) * 0.01

        # top_n=0.4 → 4 stocks each side
        result = compute_long_short_returns(factor, returns, top_n=0.4)

        self.assertEqual(len(result), 4)  # n_periods - 1

        print(f"\n  手工校验: ls_returns length={len(result)} (expected 4)")

    def test_25_ls_returns_neutral(self):
        """
        [P1-R7-25] 无区分度的因子 → 多空收益接近 0。

        手工计算: 所有因子值相同 → 随机选股 → 多空收益差 ≈ 0
        """
        from factor_pipeline.backtest.factor_metrics import compute_long_short_returns

        factor = np.ones((20, 10))
        returns = np.random.randn(20, 10) * 0.01

        result = compute_long_short_returns(factor, returns, top_n=0.2)

        # 因子值相同 → 选股几乎随机 → 多空收益接近 0
        mean_ls = np.mean(result)
        self.assertLess(abs(mean_ls), 0.05,
            f"无区分度因子多空收益应接近 0，实际 {mean_ls:.6f}")

        print(f"\n  手工校验: 中性因子 ls_mean={mean_ls:.6f} (expected ~0)")


# =============================================================================
# H. Spread
# =============================================================================

class TestSpread(unittest.TestCase):
    """测试 R8: compute_spread"""

    def test_26_spread_known(self):
        """
        [P1-R8-26] spread = mean(ls_ret) / std(ls_ret)。

        手工计算: ls_ret = [0.01, 0.02, 0.01, 0.02, 0.01]
        mean = 0.014, std = 0.00548, spread = 2.556
        """
        from factor_pipeline.backtest.factor_metrics import compute_spread

        ls_returns = np.array([0.01, 0.02, 0.01, 0.02, 0.01])

        result = compute_spread(ls_returns)

        expected = np.mean(ls_returns) / np.std(ls_returns, ddof=1)
        self.assertAlmostEqual(result, expected, places=6)

        print(f"\n  手工校验: spread={result:.6f} (expected {expected:.6f})")

    def test_27_spread_insufficient_data(self):
        """
        [P1-R8-27] 少于 3 个值 → NaN。
        """
        from factor_pipeline.backtest.factor_metrics import compute_spread

        result = compute_spread(np.array([0.01, 0.02]))

        self.assertTrue(np.isnan(result),
            f"不足 3 个值应返回 NaN，实际 {result}")

        print(f"\n  手工校验: 不足数据 → NaN: {np.isnan(result)}")


# =============================================================================
# I. Hit Rate
# =============================================================================

class TestHitRate(unittest.TestCase):
    """测试 R9: compute_hit_rate"""

    def test_28_hit_rate_all_positive(self):
        """
        [P1-R9-28] 全部正 IC → hit_rate = 1.0。

        手工计算: IC = [0.01, 0.02, 0.03, 0.04, 0.05]
        hit_rate = 5/5 = 1.0
        """
        from factor_pipeline.backtest.factor_metrics import compute_hit_rate

        ic_series = np.array([0.01, 0.02, 0.03, 0.04, 0.05])

        result = compute_hit_rate(ic_series)

        expected = 1.0
        self.assertAlmostEqual(result, expected, places=10)

        print(f"\n  手工校验: hit_rate={result:.6f} (expected {expected})")

    def test_29_hit_rate_mixed(self):
        """
        [P1-R9-29] 混合正负 IC。

        手工计算: IC = [0.01, -0.02, 0.03, -0.04, 0.05]
        hit_rate = 3/5 = 0.6
        """
        from factor_pipeline.backtest.factor_metrics import compute_hit_rate

        ic_series = np.array([0.01, -0.02, 0.03, -0.04, 0.05])

        result = compute_hit_rate(ic_series)

        expected = 0.6
        self.assertAlmostEqual(result, expected, places=10)

        print(f"\n  手工校验: hit_rate={result:.6f} (expected {expected})")

    def test_30_hit_rate_with_nan(self):
        """
        [P1-R9-30] 包含 NaN 的 IC 序列。

        手工计算: IC = [0.01, NaN, -0.03, NaN, 0.05]
        hit_rate = 2/3 = 0.6667
        """
        from factor_pipeline.backtest.factor_metrics import compute_hit_rate

        ic_series = np.array([0.01, np.nan, -0.03, np.nan, 0.05])

        result = compute_hit_rate(ic_series)

        expected = 2.0 / 3.0
        self.assertAlmostEqual(result, expected, places=6)

        print(f"\n  手工校验: hit_rate={result:.6f} (expected {expected:.6f})")


# =============================================================================
#                              测试运行器
# =============================================================================

def run_all_tests():
    """运行所有 factor_metrics 测试"""
    print("=" * 70)
    print("P1: factor_metrics.py — TDD 测试套件")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestRankIC))
    suite.addTests(loader.loadTestsFromTestCase(TestPearsonIC))
    suite.addTests(loader.loadTestsFromTestCase(TestICSeries))
    suite.addTests(loader.loadTestsFromTestCase(TestICIR))
    suite.addTests(loader.loadTestsFromTestCase(TestICDecay))
    suite.addTests(loader.loadTestsFromTestCase(TestTurnover))
    suite.addTests(loader.loadTestsFromTestCase(TestLongShortReturns))
    suite.addTests(loader.loadTestsFromTestCase(TestSpread))
    suite.addTests(loader.loadTestsFromTestCase(TestHitRate))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print(f"P1 测试结果: {result.testsRun} 运行, "
          f"{len(result.failures)} 失败, {len(result.errors)} 错误")
    print("=" * 70)

    return result


if __name__ == '__main__':
    run_all_tests()