# -*- coding: utf-8 -*-
"""
P3: engine.py — TDD 测试套件

测试 FactorBacktestEngine 因子回测引擎。
引擎使用 factor_metrics.py 作为指标计算的单一真相源。
"""

import importlib.util
import unittest

import pytest

# 可选依赖: Factor_Trading_v3_0 (pyproject.toml [backtest] extra)
# DataBridge 相关用例依赖 DataLoaderV3；未安装时按类跳过。
# P-006 Step 9：TP6-9~11 使用 FakeDataLoader，不依赖外部包，始终运行。
_HAS_EXTERNAL = importlib.util.find_spec("Factor_Trading_v3_0") is not None
_needs_external = unittest.skipUnless(
    _HAS_EXTERNAL, "Factor_Trading_v3_0 未安装（可选依赖）")

import numpy as np
import pandas as pd


# =============================================================================
# A. 引擎初始化
# =============================================================================

@_needs_external
class TestEngineSetup(unittest.TestCase):
    """测试 A: 引擎初始化"""

    def setUp(self):
        """构造标准测试数据"""
        np.random.seed(42)
        self.n_stocks = 20
        self.n_dates = 60

        stocks = [f's{i:03d}' for i in range(self.n_stocks)]
        dates = pd.date_range('2024-01-01', periods=self.n_dates, freq='B')

        # 价格数据 (n_stocks × n_dates)
        self.price_data = pd.DataFrame(
            np.random.randn(self.n_stocks, self.n_dates) * 2 + 100,
            index=stocks, columns=dates,
        )

        # 因子数据 (n_stocks × n_dates)
        self.factor_data = {
            'factor_a': pd.DataFrame(
                np.random.randn(self.n_stocks, self.n_dates),
                index=stocks, columns=dates,
            ),
            'factor_b': pd.DataFrame(
                np.random.randn(self.n_stocks, self.n_dates),
                index=stocks, columns=dates,
            ),
        }

    def test_01_basic_setup(self):
        """
        [P3-A-01] 基本初始化，传入 DataLoaderV3。

        手工校验: 引擎初始化后，n_dates/n_stocks 与 DataLoaderV3 一致。
        """
        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine

        bridge = DataBridge()
        dl = bridge.create_dataloader(self.factor_data, self.price_data)

        engine = FactorBacktestEngine(dl)
        self.assertEqual(engine.n_dates, self.n_dates)
        self.assertEqual(engine.n_stocks, self.n_stocks)
        self.assertEqual(len(engine.factor_names), 2)

        print(f"\n  手工校验: engine 初始化 OK")
        print(f"    n_dates={engine.n_dates}, n_stocks={engine.n_stocks}")
        print(f"    factors: {engine.factor_names}")

    def test_02_setup_single_factor(self):
        """
        [P3-A-02] 单因子初始化。
        """
        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine

        single_factor = {'f1': self.factor_data['factor_a']}
        bridge = DataBridge()
        dl = bridge.create_dataloader(single_factor, self.price_data)

        engine = FactorBacktestEngine(dl)
        self.assertEqual(len(engine.factor_names), 1)
        self.assertIn('f1', engine.factor_names)

        print(f"\n  手工校验: 单因子 OK: {engine.factor_names}")

    def test_03_setup_no_factors_returns_empty(self):
        """
        [P3-A-03] 无因子时不抛异常, run() 返回空 dict。

        P1 更新: 空因子场景 (所有因子被 min_dates 过滤) 不再抛 ValueError,
        而是 engine.run() 返回空 dict, 让上层决定如何处理。
        """
        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine

        empty_factor = {}
        bridge = DataBridge()
        dl = bridge.create_dataloader(empty_factor, self.price_data)

        # 不抛异常
        engine = FactorBacktestEngine(dl)
        self.assertEqual(len(engine.factor_names), 0)

        # run() 返回空 dict
        results = engine.run()
        self.assertIsInstance(results, dict)
        self.assertEqual(len(results), 0)

        print(f"\n  手工校验: 空因子场景 run() 返回空 dict OK")

    def test_04_setup_with_config(self):
        """
        [P3-A-04] 带配置参数的初始化。
        """
        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine

        bridge = DataBridge()
        dl = bridge.create_dataloader(self.factor_data, self.price_data)

        config = {'top_n': 10, 'ic_method': 'pearson', 'max_lag': 6}
        engine = FactorBacktestEngine(dl, config=config)

        self.assertEqual(engine.config['top_n'], 10)
        self.assertEqual(engine.config['ic_method'], 'pearson')
        self.assertEqual(engine.config['max_lag'], 6)

        print(f"\n  手工校验: config OK: {engine.config}")

    def test_05_fwd_returns_computation(self):
        """
        [P3-A-05] 前向收益率计算：fwd_ret[t] = (close[t+1] - close[t]) / close[t]。

        手工校验: 逐期验证 fwd_ret[t] 与手工计算一致。
        """
        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine

        bridge = DataBridge()
        dl = bridge.create_dataloader(self.factor_data, self.price_data)

        engine = FactorBacktestEngine(dl)

        fwd_ret = engine._compute_fwd_returns()
        # shape: (n_dates - 1, n_stocks)
        self.assertEqual(fwd_ret.shape, (self.n_dates - 1, self.n_stocks))

        # 手工逐期验证
        close = self.price_data.values  # (n_stocks, n_dates)
        for t in range(self.n_dates - 1):
            manual = (close[:, t + 1] - close[:, t]) / close[:, t]
            max_diff = np.max(np.abs(fwd_ret[t] - manual))
            self.assertLess(max_diff, 1e-10,
                f"t={t}: max_diff={max_diff:.2e}")

        print(f"\n  手工校验: fwd_returns shape={fwd_ret.shape}")
        print(f"    逐期验证 max_diff < 1e-10: OK")


# =============================================================================
# B. IC 计算
# =============================================================================

@_needs_external
class TestEngineIC(unittest.TestCase):
    """测试 B: IC 系列指标"""

    def setUp(self):
        np.random.seed(42)
        self.n_stocks = 20
        self.n_dates = 60

        stocks = [f's{i:03d}' for i in range(self.n_stocks)]
        dates = pd.date_range('2024-01-01', periods=self.n_dates, freq='B')

        self.price_data = pd.DataFrame(
            np.random.randn(self.n_stocks, self.n_dates) * 2 + 100,
            index=stocks, columns=dates,
        )

        self.factor_data = {
            'factor_a': pd.DataFrame(
                np.random.randn(self.n_stocks, self.n_dates),
                index=stocks, columns=dates,
            ),
        }

    def _get_engine(self):
        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine
        bridge = DataBridge()
        dl = bridge.create_dataloader(self.factor_data, self.price_data)
        return FactorBacktestEngine(dl)

    def test_06_rank_ic_series(self):
        """
        [P3-B-06] 计算 Rank IC 序列。

        手工校验: 使用 factor_metrics.compute_rank_ic 逐期验证。
        """
        from factor_pipeline.backtest.factor_metrics import compute_rank_ic

        engine = self._get_engine()
        results = engine.run()

        ic_series = results['factor_a']['rank_ic_series']
        self.assertEqual(len(ic_series), self.n_dates - 1)

        # 手工逐期验证
        factor = self.factor_data['factor_a'].values  # (n_stocks, n_dates)
        fwd_ret = engine._compute_fwd_returns()
        for t in range(self.n_dates - 1):
            manual = compute_rank_ic(factor[:, t], fwd_ret[t])
            if np.isnan(manual):
                self.assertTrue(np.isnan(ic_series[t]),
                    f"t={t}: expected NaN, got {ic_series[t]}")
            else:
                self.assertAlmostEqual(ic_series[t], manual, places=10,
                    msg=f"t={t}: engine={ic_series[t]:.6f}, manual={manual:.6f}")

        print(f"\n  手工校验: rank_ic_series 逐期验证 OK")
        print(f"    mean IC={np.nanmean(ic_series):.4f}")

    def test_07_pearson_ic_series(self):
        """
        [P3-B-07] 计算 Pearson IC 序列。

        手工校验: 使用 factor_metrics.compute_pearson_ic 逐期验证。
        """
        from factor_pipeline.backtest.factor_metrics import compute_pearson_ic

        engine = self._get_engine()
        engine.config['ic_method'] = 'pearson'
        results = engine.run()

        ic_series = results['factor_a']['pearson_ic_series']
        self.assertEqual(len(ic_series), self.n_dates - 1)

        # 手工逐期验证
        factor = self.factor_data['factor_a'].values
        fwd_ret = engine._compute_fwd_returns()
        for t in range(self.n_dates - 1):
            manual = compute_pearson_ic(factor[:, t], fwd_ret[t])
            if np.isnan(manual):
                self.assertTrue(np.isnan(ic_series[t]))
            else:
                self.assertAlmostEqual(ic_series[t], manual, places=10,
                    msg=f"t={t}: engine={ic_series[t]:.6f}, manual={manual:.6f}")

        print(f"\n  手工校验: pearson_ic_series 逐期验证 OK")
        print(f"    mean IC={np.nanmean(ic_series):.4f}")

    def test_08_icir(self):
        """
        [P3-B-08] 计算 ICIR。

        手工校验: 使用 factor_metrics.compute_icir 验证。
        """
        from factor_pipeline.backtest.factor_metrics import compute_icir

        engine = self._get_engine()
        results = engine.run()

        rank_icir = results['factor_a']['rank_icir']
        ic_series = results['factor_a']['rank_ic_series']

        manual = compute_icir(ic_series)
        if np.isnan(manual):
            self.assertTrue(np.isnan(rank_icir))
        else:
            self.assertAlmostEqual(rank_icir, manual, places=10)

        print(f"\n  手工校验: ICIR={rank_icir:.4f}, manual={manual:.4f}")

    def test_09_ic_decay(self):
        """
        [P3-B-09] 计算 IC Decay。

        手工校验: 使用 factor_metrics.compute_ic_decay 验证。
        """
        from factor_pipeline.backtest.factor_metrics import compute_ic_decay

        engine = self._get_engine()
        engine.config['max_lag'] = 12
        results = engine.run()

        decay = results['factor_a']['ic_decay']
        self.assertEqual(len(decay), 12)

        # 手工验证
        factor = self.factor_data['factor_a'].values
        fwd_ret = engine._compute_fwd_returns()
        # factor_metrics 约定: factor[:, t] 对应 returns[:, t+1]，需要 padding
        fwd_ret_padded = np.hstack([np.full((fwd_ret.T.shape[0], 1), np.nan), fwd_ret.T])
        manual_decay = compute_ic_decay(factor, fwd_ret_padded, max_lag=12)

        for lag in range(len(decay)):
            if np.isnan(manual_decay[lag]):
                self.assertTrue(np.isnan(decay[lag]))
            else:
                self.assertAlmostEqual(decay[lag], manual_decay[lag], places=10,
                    msg=f"lag={lag}: engine={decay[lag]:.6f}, manual={manual_decay[lag]:.6f}")

        print(f"\n  手工校验: ic_decay OK")
        print(f"    decay[0]={decay[0]:.4f}, decay[11]={decay[11]:.4f}")

    def test_10_hit_rate(self):
        """
        [P3-B-10] 计算 IC 胜率 (Hit Rate)。

        手工校验: 使用 factor_metrics.compute_hit_rate 验证。
        """
        from factor_pipeline.backtest.factor_metrics import compute_hit_rate

        engine = self._get_engine()
        results = engine.run()

        hit_rate = results['factor_a']['hit_rate']
        ic_series = results['factor_a']['rank_ic_series']

        manual = compute_hit_rate(ic_series)
        if np.isnan(manual):
            self.assertTrue(np.isnan(hit_rate))
        else:
            self.assertAlmostEqual(hit_rate, manual, places=10)

        print(f"\n  手工校验: hit_rate={hit_rate:.4f}, manual={manual:.4f}")

    def test_11_multi_factor_ic(self):
        """
        [P3-B-11] 多因子 IC 同时计算。
        """
        engine = self._get_engine()
        # 添加第二个因子
        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine

        multi_factor = {
            'factor_a': self.factor_data['factor_a'],
            'factor_b': pd.DataFrame(
                np.random.randn(self.n_stocks, self.n_dates),
                index=self.factor_data['factor_a'].index,
                columns=self.factor_data['factor_a'].columns,
            ),
        }
        bridge = DataBridge()
        dl = bridge.create_dataloader(multi_factor, self.price_data)
        engine2 = FactorBacktestEngine(dl)

        results = engine2.run()
        self.assertIn('factor_a', results)
        self.assertIn('factor_b', results)

        for name in ['factor_a', 'factor_b']:
            self.assertIn('rank_ic_series', results[name])
            self.assertIn('rank_icir', results[name])
            self.assertEqual(len(results[name]['rank_ic_series']), self.n_dates - 1)

        print(f"\n  手工校验: 多因子 IC OK")
        print(f"    factor_a mean IC={np.nanmean(results['factor_a']['rank_ic_series']):.4f}")
        print(f"    factor_b mean IC={np.nanmean(results['factor_b']['rank_ic_series']):.4f}")


# =============================================================================
# C. 换手率
# =============================================================================

@_needs_external
class TestEngineTurnover(unittest.TestCase):
    """测试 C: 换手率计算"""

    def setUp(self):
        np.random.seed(42)
        self.n_stocks = 20
        self.n_dates = 60

        stocks = [f's{i:03d}' for i in range(self.n_stocks)]
        dates = pd.date_range('2024-01-01', periods=self.n_dates, freq='B')

        self.price_data = pd.DataFrame(
            np.random.randn(self.n_stocks, self.n_dates) * 2 + 100,
            index=stocks, columns=dates,
        )

        self.factor_data = {
            'factor_a': pd.DataFrame(
                np.random.randn(self.n_stocks, self.n_dates),
                index=stocks, columns=dates,
            ),
        }

    def _get_engine(self):
        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine
        bridge = DataBridge()
        dl = bridge.create_dataloader(self.factor_data, self.price_data)
        return FactorBacktestEngine(dl)

    def test_12_turnover_equal_weight(self):
        """
        [P3-C-12] 计算等权换手率。

        手工校验: 使用 factor_metrics.compute_turnover 验证。
        """
        from factor_pipeline.backtest.factor_metrics import compute_turnover

        engine = self._get_engine()
        engine.config['ls_method'] = 'equal_weight'
        results = engine.run()

        turnover = results['factor_a']['turnover']
        self.assertEqual(len(turnover), self.n_dates - 1)

        # 手工验证: 使用 factor_metrics 对等权仓位计算
        factor = self.factor_data['factor_a'].values
        # 等权仓位: 每期仓位 = factor 值的符号 / sum(|sign|)
        positions = np.zeros((self.n_dates, self.n_stocks))
        for t in range(self.n_dates):
            f = factor[:, t]
            valid = ~np.isnan(f)
            if valid.sum() > 0:
                signs = np.sign(f)
                positions[t] = signs / max(np.sum(np.abs(signs)), 1)

        manual_to = compute_turnover(positions)
        for t in range(len(turnover)):
            if np.isnan(manual_to[t]):
                self.assertTrue(np.isnan(turnover[t]))
            else:
                self.assertAlmostEqual(turnover[t], manual_to[t], places=10,
                    msg=f"t={t}: engine={turnover[t]:.6f}, manual={manual_to[t]:.6f}")

        print(f"\n  手工校验: turnover equal_weight OK")
        print(f"    mean turnover={np.nanmean(turnover):.4f}")

    def test_13_turnover_top_n(self):
        """
        [P3-C-13] 计算 top-N 换手率。

        手工校验: 使用 factor_metrics.compute_turnover 验证。
        """
        from factor_pipeline.backtest.factor_metrics import compute_turnover

        engine = self._get_engine()
        engine.config['ls_method'] = 'top_n'
        engine.config['top_n'] = 5
        results = engine.run()

        turnover = results['factor_a']['turnover']
        self.assertEqual(len(turnover), self.n_dates - 1)

        # 手工验证 top-N 仓位
        factor = self.factor_data['factor_a'].values
        positions = np.zeros((self.n_dates, self.n_stocks))
        top_n = 5
        for t in range(self.n_dates):
            f = factor[:, t]
            valid = ~np.isnan(f)
            n_valid = valid.sum()
            if n_valid < top_n * 2:
                continue
            sorted_idx = np.argsort(f)
            pos = np.zeros(self.n_stocks)
            # top N → long, bottom N → short
            pos[sorted_idx[-top_n:]] = 1.0 / top_n
            pos[sorted_idx[:top_n]] = -1.0 / top_n
            positions[t] = pos

        manual_to = compute_turnover(positions)
        for t in range(len(turnover)):
            if np.isnan(manual_to[t]):
                self.assertTrue(np.isnan(turnover[t]))
            else:
                self.assertAlmostEqual(turnover[t], manual_to[t], places=10,
                    msg=f"t={t}: engine={turnover[t]:.6f}, manual={manual_to[t]:.6f}")

        print(f"\n  手工校验: turnover top_n OK")
        print(f"    mean turnover={np.nanmean(turnover):.4f}")

    def test_14_multi_factor_turnover(self):
        """
        [P3-C-14] 多因子换手率同时计算。
        """
        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine

        multi_factor = {
            'factor_a': self.factor_data['factor_a'],
            'factor_b': pd.DataFrame(
                np.random.randn(self.n_stocks, self.n_dates),
                index=self.factor_data['factor_a'].index,
                columns=self.factor_data['factor_a'].columns,
            ),
        }
        bridge = DataBridge()
        dl = bridge.create_dataloader(multi_factor, self.price_data)
        engine = FactorBacktestEngine(dl)

        results = engine.run()
        for name in ['factor_a', 'factor_b']:
            self.assertIn('turnover', results[name])
            self.assertEqual(len(results[name]['turnover']), self.n_dates - 1)

        print(f"\n  手工校验: 多因子 turnover OK")


# =============================================================================
# D. 多空收益
# =============================================================================

@_needs_external
class TestEngineLS(unittest.TestCase):
    """测试 D: 多空收益"""

    def setUp(self):
        np.random.seed(42)
        self.n_stocks = 20
        self.n_dates = 60

        stocks = [f's{i:03d}' for i in range(self.n_stocks)]
        dates = pd.date_range('2024-01-01', periods=self.n_dates, freq='B')

        self.price_data = pd.DataFrame(
            np.random.randn(self.n_stocks, self.n_dates) * 2 + 100,
            index=stocks, columns=dates,
        )

        self.factor_data = {
            'factor_a': pd.DataFrame(
                np.random.randn(self.n_stocks, self.n_dates),
                index=stocks, columns=dates,
            ),
        }

    def _get_engine(self):
        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine
        bridge = DataBridge()
        dl = bridge.create_dataloader(self.factor_data, self.price_data)
        return FactorBacktestEngine(dl)

    def test_15_long_short_returns(self):
        """
        [P3-D-15] 计算多空收益。

        手工校验: 使用 factor_metrics.compute_long_short_returns 验证。
        """
        from factor_pipeline.backtest.factor_metrics import compute_long_short_returns

        engine = self._get_engine()
        engine.config['top_n'] = 0.2  # 20% top/bottom
        results = engine.run()

        ls_returns = results['factor_a']['long_short_returns']
        self.assertEqual(len(ls_returns), self.n_dates - 1)

        # 手工验证
        factor = self.factor_data['factor_a'].values
        fwd_ret = engine._compute_fwd_returns()
        # factor_metrics 约定: factor[:, t] 对应 returns[:, t+1]，需要 padding
        fwd_ret_padded = np.hstack([np.full((fwd_ret.T.shape[0], 1), np.nan), fwd_ret.T])
        manual_ls = compute_long_short_returns(factor, fwd_ret_padded, top_n=0.2)

        for t in range(len(ls_returns)):
            if np.isnan(manual_ls[t]):
                self.assertTrue(np.isnan(ls_returns[t]))
            else:
                self.assertAlmostEqual(ls_returns[t], manual_ls[t], places=10,
                    msg=f"t={t}: engine={ls_returns[t]:.6f}, manual={manual_ls[t]:.6f}")

        print(f"\n  手工校验: long_short_returns OK")
        print(f"    mean LS={np.nanmean(ls_returns):.4f}")

    def test_16_spread(self):
        """
        [P3-D-16] 计算 Spread。

        手工校验: 使用 factor_metrics.compute_spread 验证。
        """
        from factor_pipeline.backtest.factor_metrics import compute_spread

        engine = self._get_engine()
        results = engine.run()

        spread = results['factor_a']['spread']
        ls_returns = results['factor_a']['long_short_returns']

        manual = compute_spread(ls_returns)
        if np.isnan(manual):
            self.assertTrue(np.isnan(spread))
        else:
            self.assertAlmostEqual(spread, manual, places=10)

        print(f"\n  手工校验: spread={spread:.4f}, manual={manual:.4f}")

    def test_17_long_short_fixed_top_n(self):
        """
        [P3-D-17] 固定 top_n 的多空收益。

        手工校验: 使用 factor_metrics.compute_long_short_returns 验证。
        """
        from factor_pipeline.backtest.factor_metrics import compute_long_short_returns

        engine = self._get_engine()
        engine.config['top_n'] = 5  # fixed 5 stocks
        results = engine.run()

        ls_returns = results['factor_a']['long_short_returns']
        factor = self.factor_data['factor_a'].values
        fwd_ret = engine._compute_fwd_returns()
        # factor_metrics 约定: factor[:, t] 对应 returns[:, t+1]，需要 padding
        fwd_ret_padded = np.hstack([np.full((fwd_ret.T.shape[0], 1), np.nan), fwd_ret.T])
        manual_ls = compute_long_short_returns(factor, fwd_ret_padded, top_n=5)

        for t in range(len(ls_returns)):
            if np.isnan(manual_ls[t]):
                self.assertTrue(np.isnan(ls_returns[t]))
            else:
                self.assertAlmostEqual(ls_returns[t], manual_ls[t], places=10)

        print(f"\n  手工校验: long_short (top_n=5) OK")
        print(f"    mean LS={np.nanmean(ls_returns):.4f}")


# =============================================================================
# E. 结果结构
# =============================================================================

@_needs_external
class TestEngineResults(unittest.TestCase):
    """测试 E: 结果结构完整性"""

    def setUp(self):
        np.random.seed(42)
        self.n_stocks = 20
        self.n_dates = 60

        stocks = [f's{i:03d}' for i in range(self.n_stocks)]
        dates = pd.date_range('2024-01-01', periods=self.n_dates, freq='B')

        self.price_data = pd.DataFrame(
            np.random.randn(self.n_stocks, self.n_dates) * 2 + 100,
            index=stocks, columns=dates,
        )

        self.factor_data = {
            'factor_a': pd.DataFrame(
                np.random.randn(self.n_stocks, self.n_dates),
                index=stocks, columns=dates,
            ),
            'factor_b': pd.DataFrame(
                np.random.randn(self.n_stocks, self.n_dates),
                index=stocks, columns=dates,
            ),
        }

    def _get_engine(self):
        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine
        bridge = DataBridge()
        dl = bridge.create_dataloader(self.factor_data, self.price_data)
        return FactorBacktestEngine(dl)

    def test_18_results_structure(self):
        """
        [P3-E-18] 结果结构包含所有必需字段。

        检查: 每个因子结果包含 8 个核心指标。
        """
        engine = self._get_engine()
        results = engine.run()

        required_fields = [
            'rank_ic_series',
            'rank_icir',
            'pearson_ic_series',
            'pearson_icir',
            'ic_decay',
            'hit_rate',
            'turnover',
            'long_short_returns',
            'spread',
        ]

        for name in self.factor_data:
            self.assertIn(name, results)
            for field in required_fields:
                self.assertIn(field, results[name],
                    f"因子 '{name}' 缺少字段 '{field}'")

        print(f"\n  手工校验: 结果结构 OK")
        print(f"    每个因子包含 {len(required_fields)} 个指标")

    def test_19_results_all_factors(self):
        """
        [P3-E-19] 所有因子都产生结果。
        """
        engine = self._get_engine()
        results = engine.run()

        self.assertEqual(len(results), 2)
        for name in ['factor_a', 'factor_b']:
            self.assertIn(name, results)

        print(f"\n  手工校验: {len(results)} 个因子全部有结果")

    def test_20_factor_ranking(self):
        """
        [P3-E-20] 按 ICIR 排序因子。

        手工校验: 排序结果与手动计算一致。
        """
        engine = self._get_engine()
        results = engine.run()

        ranking = engine.rank_by_icir()
        self.assertEqual(len(ranking), 2)

        # 手工验证排序
        icirs = {name: results[name]['rank_icir'] for name in results}
        manual_ranking = sorted(icirs, key=icirs.get, reverse=True)
        self.assertEqual(ranking, manual_ranking)

        print(f"\n  手工校验: 因子排序 OK")
        for i, name in enumerate(ranking):
            print(f"    [{i+1}] {name}: ICIR={results[name]['rank_icir']:.4f}")


# =============================================================================
# F. tradability 接入（P-006 Step 9：TP6-9~11）
# =============================================================================

class _FakeDL:
    """最小 DataLoader 替身（引擎仅消费 n_dates/n_stocks/price_data/factor_data）。"""

    def __init__(self, factor, close):
        self.n_dates, self.n_stocks = close.shape
        self.price_data = {"close": close}
        self.factor_data = {"f": factor}


def _tradability_case():
    from factor_pipeline.backtest.tradability import TradabilityInputs

    T, N = 4, 4
    close = np.full((T, N), 10.0)
    high = np.full((T, N), 10.0)
    low = np.full((T, N), 9.8)
    open_ = np.full((T, N), 10.0)
    volume = np.full((T, N), 1e6)
    suspended = np.zeros((T, N), dtype=bool)
    close[1, 0] = 11.0          # t=1 钉涨停（prev=10 → up=11）
    high[1, 0] = 11.0
    factor = np.tile(np.array([3.0, 2.0, 1.0, 0.0]), (T, 1))
    factor[0] = np.array([1.0, 3.0, 2.0, 0.0])   # t=0 多头在 stock1，t=1 切向 stock0
    dates = np.array(["2026-01-05", "2026-01-06",
                      "2026-01-07", "2026-01-08"])
    inputs = TradabilityInputs(
        close=close, high=high, low=low, open_=open_, volume=volume,
        suspended=suspended, dates=dates, board=np.array(["main"] * N),
        is_st=np.zeros((T, N), dtype=bool), adj=np.ones((T, N)))
    return dict(factor=factor, close=close, high=high, low=low, open_=open_,
                volume=volume, suspended=suspended, dates=dates, inputs=inputs)


def test_tp6_9_engine_calls_tradability():
    """TP6-9：引擎路径调用限价规则，tradability 报告挂载且换手变化。"""
    from factor_pipeline.backtest.engine import FactorBacktestEngine

    case = _tradability_case()
    dl = _FakeDL(case["factor"], case["close"])
    config = {"ls_method": "top_n", "top_n": 1}
    base = FactorBacktestEngine(dl, config=config).run()["f"]
    res = FactorBacktestEngine(
        dl, config=config, tradability_inputs=case["inputs"]).run()["f"]

    assert "tradability" not in base
    block = res["tradability"]
    assert block["report"]["blocked_buy"] >= 1
    assert block["leg_scope"] == "long_only"
    assert block["short_leg_unmodeled"] is True
    assert block["price_basis"] == "raw_adj_ref"
    assert block["turnover_basis"] == "effective_long_only"
    assert not np.array_equal(np.asarray(res["turnover"]),
                              np.asarray(base["turnover"]))

    # 形状负例 / adj 缺失负例 → ValueError（不静默降级）
    from factor_pipeline.backtest.tradability import TradabilityInputs
    bad_shape = TradabilityInputs(
        close=case["close"][:2], high=case["high"], low=case["low"],
        open_=case["open_"], volume=case["volume"],
        suspended=case["suspended"], dates=case["dates"],
        board=case["inputs"].board, is_st=case["inputs"].is_st,
        adj=case["inputs"].adj)
    with pytest.raises(ValueError):
        FactorBacktestEngine(dl, tradability_inputs=bad_shape)
    no_adj = TradabilityInputs(
        close=case["close"], high=case["high"], low=case["low"],
        open_=case["open_"], volume=case["volume"],
        suspended=case["suspended"], dates=case["dates"],
        board=case["inputs"].board, is_st=case["inputs"].is_st, adj=None)
    with pytest.raises(ValueError):
        FactorBacktestEngine(dl, tradability_inputs=no_adj)


def test_tp6_9b_prev_close_derived_from_inputs():
    """Step 10 P2-①：prev_close 必须派生自 tradability_inputs.close（鉴别用例）。"""
    from factor_pipeline.backtest.engine import FactorBacktestEngine
    from factor_pipeline.backtest.tradability import TradabilityInputs

    case = _tradability_case()
    dl = _FakeDL(case["factor"], case["close"])
    config = {"ls_method": "top_n", "top_n": 1}

    # 基准：inputs.close 与 dl.close 相同 → t=1 stock0 触涨停封板
    base = FactorBacktestEngine(
        dl, config=config, tradability_inputs=case["inputs"]).run()["f"]
    assert base["tradability"]["report"]["blocked_buy"] == 1

    # 仅改 inputs.close[0,0]（10→12，与 dl.close 脱钩）→ t=1 判定基准 12，
    # up=13.2 > high=11.0 → 不封板；若引擎误用 dl.close 派生 prev（up=11）则仍封板
    modified = case["close"].copy()
    modified[0, 0] = 12.0
    inputs2 = TradabilityInputs(
        close=modified, high=case["high"], low=case["low"],
        open_=case["open_"], volume=case["volume"],
        suspended=case["suspended"], dates=case["dates"],
        board=case["inputs"].board, is_st=case["inputs"].is_st,
        adj=case["inputs"].adj)
    res = FactorBacktestEngine(
        dl, config=config, tradability_inputs=inputs2).run()["f"]
    assert res["tradability"]["report"]["blocked_buy"] == 0


def test_tp6_10_short_leg_passthrough():
    """TP6-10 / INV-7：空头腿透传，不参与限价推进。"""
    from factor_pipeline.backtest.engine import FactorBacktestEngine
    from factor_pipeline.backtest.tradability import apply_tradability

    case = _tradability_case()
    dl = _FakeDL(case["factor"], case["close"])
    engine = FactorBacktestEngine(
        dl, config={"top_n": 1}, tradability_inputs=case["inputs"])
    res = engine.run()["f"]
    positions = engine._build_positions(case["factor"])

    prev = np.full_like(case["close"], np.nan)
    prev[1:] = case["close"][:-1]
    eff_long, _ = apply_tradability(
        np.clip(positions, 0.0, None), prev, case["high"], case["low"],
        case["close"], case["open_"], case["volume"], case["suspended"],
        case["inputs"].board, case["inputs"].is_st, case["dates"],
        adj=case["inputs"].adj)
    effective = eff_long + np.minimum(positions, 0.0)
    assert np.array_equal(effective[positions < 0], positions[positions < 0])
    assert res["tradability"]["leg_scope"] == "long_only"


def test_tp6_11_default_baseline_unchanged():
    """TP6-11：默认路径（tradability_inputs=None）逐位等于 Step 5 前基线。"""
    from factor_pipeline.backtest.engine import FactorBacktestEngine

    rng = np.random.default_rng(20261123)
    T, N = 12, 6
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.001, 0.02, (T, N)), axis=0))
    factor = rng.normal(0.0, 1.0, (T, N))
    dl = _FakeDL(factor, close)

    engine = FactorBacktestEngine(dl, config={"ls_method": "top_n", "top_n": 2})
    res = engine.run()["f"]
    summary = engine.summary()["f"]

    assert summary["rank_icir"] == -0.25880207857362303
    assert summary["pearson_icir"] == -0.30599173567954446
    assert summary["hit_rate"] == 0.36363636363636365
    assert summary["spread"] == -0.1610540425109819
    assert summary["mean_rank_ic"] == -0.10649350649350647
    assert np.asarray(res["turnover"]).tolist() == [
        1.5, 1.0, 2.0, 1.5, 2.0, 1.0, 1.0, 1.0, 1.0, 1.5, 1.5]
    assert "tradability" not in res


def test_tradability_inputs_validation():
    from factor_pipeline.backtest.engine import FactorBacktestEngine
    from factor_pipeline.backtest.tradability import TradabilityInputs

    case = _tradability_case()
    dl = _FakeDL(case["factor"], case["close"])
    bad_shape = TradabilityInputs(
        close=case["close"][:2], high=case["high"], low=case["low"],
        open_=case["open_"], volume=case["volume"],
        suspended=case["suspended"], dates=case["dates"],
        board=case["inputs"].board, is_st=case["inputs"].is_st,
        adj=case["inputs"].adj)
    with pytest.raises(ValueError):
        FactorBacktestEngine(dl, tradability_inputs=bad_shape)

    no_adj = TradabilityInputs(
        close=case["close"], high=case["high"], low=case["low"],
        open_=case["open_"], volume=case["volume"],
        suspended=case["suspended"], dates=case["dates"],
        board=case["inputs"].board, is_st=case["inputs"].is_st, adj=None)
    with pytest.raises(ValueError):
        FactorBacktestEngine(dl, tradability_inputs=no_adj)


# =============================================================================
#                              测试运行器
# =============================================================================

def run_all_tests():
    print("=" * 70)
    print("P3: engine.py — TDD 测试套件")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestEngineSetup))
    suite.addTests(loader.loadTestsFromTestCase(TestEngineIC))
    suite.addTests(loader.loadTestsFromTestCase(TestEngineTurnover))
    suite.addTests(loader.loadTestsFromTestCase(TestEngineLS))
    suite.addTests(loader.loadTestsFromTestCase(TestEngineResults))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print(f"P3 测试结果: {result.testsRun} 运行, "
          f"{len(result.failures)} 失败, {len(result.errors)} 错误")
    print("=" * 70)

    return result


if __name__ == '__main__':
    run_all_tests()