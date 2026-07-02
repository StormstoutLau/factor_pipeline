# -*- coding: utf-8 -*-
"""
P3: engine.py — TDD 测试套件

测试 FactorBacktestEngine 因子回测引擎。
引擎使用 factor_metrics.py 作为指标计算的单一真相源。
"""

import unittest
import numpy as np
import pandas as pd


# =============================================================================
# A. 引擎初始化
# =============================================================================

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