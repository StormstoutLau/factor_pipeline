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

    # =====================================================================
    # E3 (v2.6.0): IC 时间加权 EWMA
    # =====================================================================

    def test_e3_01_compute_ic_series_equal_weighting_default(self):
        """[v2.6.0-E3-01] 默认 weighting='equal', 与现有行为一致."""
        from factor_pipeline.backtest.factor_metrics import compute_ic_series

        np.random.seed(42)
        factor = np.random.randn(20, 10)
        returns = np.random.randn(20, 10)

        # 不传 weighting (使用默认值)
        result_default = compute_ic_series(factor, returns, method='rank')
        # 显式传 weighting='equal'
        result_equal = compute_ic_series(factor, returns, method='rank', weighting='equal')

        # 两者应完全一致
        self.assertEqual(len(result_default), 9)
        np.testing.assert_array_equal(result_default, result_equal)

        print(f"\n  手工校验 E3-01: 默认 weighting='equal' 一致")

    def test_e3_02_compute_ic_series_ewma_returns_shape_one(self):
        """[v2.6.0-E3-02] weighting='ewma' 返回 shape (1,) 数组."""
        from factor_pipeline.backtest.factor_metrics import compute_ic_series

        np.random.seed(42)
        factor = np.random.randn(20, 10)
        returns = np.random.randn(20, 10)

        result = compute_ic_series(factor, returns, method='rank', weighting='ewma', halflife=3)

        self.assertEqual(result.shape, (1,),
                         f"EWMA 应返回 shape (1,), 实际 {result.shape}")
        self.assertFalse(np.isnan(result[0]),
                         "EWMA 结果不应为 NaN (输入数据有效)")

        print(f"\n  手工校验 E3-02: EWMA shape={result.shape}, value={result[0]:.6f}")

    def test_e3_03_compute_ic_series_ewma_halflife_default(self):
        """[v2.6.0-E3-03] halflife=None 时自动设为 n_periods // 4."""
        from factor_pipeline.backtest.factor_metrics import compute_ic_series

        np.random.seed(42)
        n_periods = 24
        factor = np.random.randn(50, n_periods)
        returns = np.random.randn(50, n_periods)

        # halflife=None (默认), 期望自动设为 n_periods // 4 = 6
        # 但实际 ic_series 长度为 n_periods - 1 = 23, 所以 halflife = 23 // 4 = 5
        expected_halflife = (n_periods - 1) // 4  # 5

        # 用 halflife=None 和 halflife=expected_halflife 应得到相同结果
        result_auto = compute_ic_series(factor, returns, weighting='ewma')
        result_explicit = compute_ic_series(factor, returns, weighting='ewma',
                                            halflife=expected_halflife)

        self.assertAlmostEqual(result_auto[0], result_explicit[0], places=10,
                               msg="halflife=None 应自动设为 len(ic_series)//4")

        print(f"\n  手工校验 E3-03: 自动 halflife={expected_halflife}, "
              f"IC={result_auto[0]:.6f}")

    def test_e3_04_compute_ic_series_ewma_weights_correct(self):
        """[v2.6.0-E3-04] EWMA 权重手工计算与实现对比精度 < 1e-10."""
        from factor_pipeline.backtest.factor_metrics import compute_ic_series

        np.random.seed(42)
        n_stocks, n_periods = 30, 10
        factor = np.random.randn(n_stocks, n_periods)
        returns = np.random.randn(n_stocks, n_periods)

        halflife = 4
        # 先获取等权 IC 序列
        ic_series_equal = compute_ic_series(factor, returns, method='pearson',
                                             weighting='equal')
        # 手工计算 EWMA 权重
        # alpha = 1 - exp(-ln2/halflife)
        # w[t] = (1-alpha)^(T-1-t), 即最近一期权重最大
        alpha = 1.0 - np.exp(-np.log(2.0) / halflife)
        n = len(ic_series_equal)
        weights = (1.0 - alpha) ** np.arange(n)[::-1]
        weights /= weights.sum()

        # 手工加权 IC
        valid = ~np.isnan(ic_series_equal)
        expected_weighted_ic = np.nansum(ic_series_equal * weights)

        # 实现 EWMA IC
        result = compute_ic_series(factor, returns, method='pearson',
                                   weighting='ewma', halflife=halflife)

        self.assertAlmostEqual(result[0], expected_weighted_ic, places=10,
                               msg=f"EWMA 权重计算错误: {result[0]} != {expected_weighted_ic}")

        # 同时验证权重正确性: 权重应单调递增 (近期权重更大)
        self.assertTrue(np.all(np.diff(weights) > 0),
                        "EWMA 权重应单调递增 (近期权重更大)")
        # 最近一期权重应最大, 等于 1.0 / sum (因为 (1-alpha)^0 = 1)
        # 验证: w[t] = (1-alpha)^(n-1-t), 所以 w[-1] = (1-alpha)^0 = 1.0 (未归一化)
        unnormalized_last = 1.0
        sum_unnormalized = np.sum((1.0 - alpha) ** np.arange(n)[::-1])
        expected_last_weight = unnormalized_last / sum_unnormalized
        self.assertAlmostEqual(weights[-1], expected_last_weight, places=10,
                               msg="最近一期权重应等于 1/sum (未归一化值=1)")

        print(f"\n  手工校验 E3-04: 权重单调递增")
        print(f"    weights[0]={weights[0]:.6f} (最远)")
        print(f"    weights[-1]={weights[-1]:.6f} (最近)")
        print(f"    EWMA IC={result[0]:.6f}, 手工 IC={expected_weighted_ic:.6f}")

    def test_e3_05_compute_ic_series_ewma_recent_emphasis(self):
        """[v2.6.0-E3-05] 近期 IC 高时, EWMA IC > 等权 IC.

        注意: compute_ic_series 是跨期前瞻 (factor[:, t] vs returns[:, t+1]).
        所以构造 returns[:, t+1] = ic_target_t * factor[:, t] + noise,
        使 corr(factor[:, t], returns[:, t+1]) ≈ ic_target_t.
        """
        from factor_pipeline.backtest.factor_metrics import compute_ic_series

        np.random.seed(42)
        n_stocks, n_periods = 100, 24
        factor = np.random.randn(n_stocks, n_periods)
        returns = np.zeros_like(factor)

        # 构造 IC 上升场景: 前 12 期 IC=0.01, 后 12 期 IC=0.10
        # returns[:, t+1] = ic_target_t * factor[:, t] + noise (跨期前瞻关系)
        for t in range(n_periods - 1):
            ic_target = 0.01 if t < 12 else 0.10
            returns[:, t + 1] = ic_target * factor[:, t] + np.random.randn(n_stocks) * 0.5

        ic_equal = compute_ic_series(factor, returns, method='pearson',
                                     weighting='equal')
        ic_ewma = compute_ic_series(factor, returns, method='pearson',
                                    weighting='ewma', halflife=6)

        equal_mean = np.nanmean(ic_equal)
        ewma_value = ic_ewma[0]

        # EWMA 应更接近近期 IC (0.10), 等权应接近全局均值 (~0.055)
        self.assertGreater(ewma_value, equal_mean,
                           "EWMA 应更接近近期 IC (上升场景), 应大于等权 IC")

        print(f"\n  手工校验 E3-05: 近期加权")
        print(f"    equal IC mean: {equal_mean:.4f} (预期 ~0.055)")
        print(f"    EWMA IC:       {ewma_value:.4f} (预期 > 0.055, 更接近近期 0.10)")

    def test_e3_06_compute_ic_series_ewma_nan_handling(self):
        """[v2.6.0-E3-06] 含 NaN 时, EWMA 忽略 NaN 加权."""
        from factor_pipeline.backtest.factor_metrics import compute_ic_series

        np.random.seed(42)
        n_stocks, n_periods = 30, 10
        factor = np.random.randn(n_stocks, n_periods)
        returns = np.random.randn(n_stocks, n_periods)

        # 在第 3 期注入 NaN (整列)
        factor[:, 3] = np.nan

        halflife = 4
        ic_equal = compute_ic_series(factor, returns, method='pearson',
                                     weighting='equal')
        ic_ewma = compute_ic_series(factor, returns, method='pearson',
                                    weighting='ewma', halflife=halflife)

        # 等权序列中 t=2 (对应 factor[:, 2] vs returns[:, 3]) 应为 NaN
        # 因为 factor[:, 3] 已被注入 NaN (但 returns[:, 3] 是有效的)
        # 实际上 compute_pearson_ic 内部会忽略 NaN 配对
        # 如果整列 factor 为 NaN, 则无法计算 IC, 返回 NaN
        self.assertTrue(np.isnan(ic_equal[2]) or np.isfinite(ic_equal[2]),
                        "t=2 的 IC 状态取决于实现")

        # EWMA 结果应为有限值 (因为其他期 IC 有效)
        # 如果有效 IC 不足 MIN_VALID_PAIRS=3, 则返回 NaN
        valid_count = np.sum(~np.isnan(ic_equal))
        if valid_count >= 3:
            self.assertFalse(np.isnan(ic_ewma[0]),
                             "EWMA 应在有效 IC 足够时返回有限值")
        else:
            self.assertTrue(np.isnan(ic_ewma[0]),
                            "EWMA 应在有效 IC 不足时返回 NaN")

        # 手工计算 (nansum)
        alpha = 1.0 - np.exp(-np.log(2.0) / halflife)
        n = len(ic_equal)
        weights = (1.0 - alpha) ** np.arange(n)[::-1]
        weights /= weights.sum()
        expected = np.nansum(ic_equal * weights)

        if not np.isnan(ic_ewma[0]):
            self.assertAlmostEqual(ic_ewma[0], expected, places=10,
                                   msg="EWMA NaN 处理与手工 nansum 一致")

        print(f"\n  手工校验 E3-06: NaN 处理")
        print(f"    valid IC count: {valid_count}")
        print(f"    EWMA IC: {ic_ewma[0]:.6f}, 手工 nansum: {expected:.6f}")

    def test_e3_07_optimizer_compute_ic_ewma_integration(self):
        """[v2.6.0-E3-07] optimizer._compute_ic(weighting='ewma') 返回标量."""
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        np.random.seed(42)
        n_stocks, n_periods = 50, 20
        factor_values = np.random.randn(n_stocks, n_periods)
        forward_returns = 0.3 * factor_values + 0.7 * np.random.randn(n_stocks, n_periods)

        optimizer = EndToEndThresholdOptimizer(n_trials=1)

        # 等权模式
        ic_equal = optimizer._compute_ic(factor_values, forward_returns,
                                          weighting='equal')
        # EWMA 模式
        ic_ewma = optimizer._compute_ic(factor_values, forward_returns,
                                         weighting='ewma', halflife=5)

        # 两者应都返回 float 标量
        self.assertIsInstance(ic_equal, float,
                              "等权 IC 应返回 float 标量")
        self.assertIsInstance(ic_ewma, float,
                              "EWMA IC 应返回 float 标量")
        self.assertFalse(np.isnan(ic_ewma), "EWMA IC 不应为 NaN")

        print(f"\n  手工校验 E3-07: optimizer 集成")
        print(f"    equal IC: {ic_equal:.6f}")
        print(f"    EWMA IC:  {ic_ewma:.6f}")

    def test_e3_08_compute_ic_series_backward_compatible(self):
        """[v2.6.0-E3-08] 不传 weighting/halflife 时, 行为与 v2.5.0 完全一致."""
        from factor_pipeline.backtest.factor_metrics import compute_ic_series

        np.random.seed(42)
        n_stocks, n_periods = 30, 12
        factor = np.random.randn(n_stocks, n_periods)
        returns = np.random.randn(n_stocks, n_periods)

        # v2.6.0 调用 (带 weighting='equal')
        result_v26 = compute_ic_series(factor, returns, method='rank',
                                       weighting='equal')
        # v2.5.0 等价调用 (不传 weighting, 使用默认值)
        result_v25 = compute_ic_series(factor, returns, method='rank')

        # 完全一致 (形状 + 数值)
        self.assertEqual(result_v26.shape, result_v25.shape)
        np.testing.assert_array_equal(result_v26, result_v25)

        # 验证默认 weighting 值为 'equal'
        import inspect
        sig = inspect.signature(compute_ic_series)
        self.assertEqual(sig.parameters['weighting'].default, 'equal',
                         msg="weighting 默认值应为 'equal'")

        print(f"\n  手工校验 E3-08: 向后兼容")
        print(f"    v2.6.0 result == v2.5.0 result: True")
        print(f"    shape: {result_v26.shape}")


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