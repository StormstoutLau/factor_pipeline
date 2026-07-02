# -*- coding: utf-8 -*-
"""P0 性能优化: fwd_returns 共享 + 并行化 — Red Phase 测试"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from factor_pipeline.backtest.engine import FactorBacktestEngine


# =============================================================================
# 测试夹具
# =============================================================================

class FakeDataLoader:
    """模拟 DataLoaderV3，提供因子和价格数据"""

    def __init__(self, n_dates=60, n_stocks=100, n_factors=3, seed=42):
        rng = np.random.default_rng(seed)
        self.n_dates = n_dates
        self.n_stocks = n_stocks

        # 价格: 累积对数正态
        log_ret = rng.normal(0.001, 0.02, (n_dates, n_stocks))
        price = 100 * np.exp(np.cumsum(log_ret, axis=0))
        self.price_data = {'close': price}

        # 因子: 随机 + 部分与价格相关
        self.factor_data = {}
        for i in range(n_factors):
            f = rng.normal(0, 1, (n_dates, n_stocks))
            self.factor_data[f'factor_{i}'] = f

    @property
    def factor_names(self):
        return list(self.factor_data.keys())


def make_dataloader(n_dates=60, n_stocks=100, n_factors=3, seed=42):
    return FakeDataLoader(n_dates, n_stocks, n_factors, seed)


# =============================================================================
# Test 1: 引擎接受预计算 fwd_returns
# =============================================================================

class TestPrecomputedFwdReturns:
    """引擎接受预计算的 fwd_returns"""

    def test_accepts_fwd_returns_in_constructor(self):
        """引擎 __init__ 接受 fwd_returns 参数"""
        dl = make_dataloader()
        fwd = np.ones((dl.n_dates - 1, dl.n_stocks))

        engine = FactorBacktestEngine(dl, fwd_returns=fwd)
        assert engine._fwd_returns is not None
        assert engine._fwd_returns.shape == (dl.n_dates - 1, dl.n_stocks)

    def test_uses_precomputed_fwd_returns(self):
        """引擎使用预计算的 fwd_returns，不重新计算"""
        dl = make_dataloader()
        fwd = np.ones((dl.n_dates - 1, dl.n_stocks))

        engine = FactorBacktestEngine(dl, fwd_returns=fwd)
        result = engine._compute_fwd_returns()
        # 应该返回预计算的值，而不是重新计算
        np.testing.assert_array_equal(result, fwd)

    def test_rejects_wrong_shape(self):
        """拒绝形状不匹配的 fwd_returns"""
        dl = make_dataloader()
        fwd_wrong = np.ones((dl.n_dates, dl.n_stocks))  # 错误: 应该是 n_dates-1

        with pytest.raises(ValueError, match='fwd_returns'):
            FactorBacktestEngine(dl, fwd_returns=fwd_wrong)

    def test_results_identical_with_and_without_precomputed(self):
        """预计算 vs 自计算: 结果完全一致"""
        dl = make_dataloader(n_dates=60, n_stocks=100, n_factors=1, seed=42)

        # 自计算
        engine1 = FactorBacktestEngine(dl)
        results1 = engine1.run()

        # 预计算
        fwd = engine1._compute_fwd_returns()
        dl2 = make_dataloader(n_dates=60, n_stocks=100, n_factors=1, seed=42)
        engine2 = FactorBacktestEngine(dl2, fwd_returns=fwd)
        results2 = engine2.run()

        # 逐指标验证
        for fn in dl.factor_names:
            r1 = results1[fn]
            r2 = results2[fn]
            np.testing.assert_array_almost_equal(r1['rank_ic_series'], r2['rank_ic_series'])
            np.testing.assert_array_almost_equal(r1['pearson_ic_series'], r2['pearson_ic_series'])
            np.testing.assert_almost_equal(r1['rank_icir'], r2['rank_icir'])
            np.testing.assert_almost_equal(r1['pearson_icir'], r2['pearson_icir'])
            np.testing.assert_almost_equal(r1['hit_rate'], r2['hit_rate'])
            np.testing.assert_almost_equal(r1['spread'], r2['spread'])


# =============================================================================
# Test 2: fwd_returns 只计算一次
# =============================================================================

class TestFwdReturnsComputedOnce:
    """fwd_returns 在多因子场景下只计算一次"""

    def test_single_engine_computes_once(self):
        """单个引擎评估多个因子: fwd_returns 实际计算只执行一次"""
        dl = make_dataloader(n_dates=60, n_stocks=100, n_factors=3, seed=42)

        # 计数实际计算次数 (for-loop 执行次数)
        compute_count = 0
        original_compute = FactorBacktestEngine._compute_fwd_returns

        def counting_compute(self):
            nonlocal compute_count
            if self._fwd_returns is None:
                compute_count += 1
            return original_compute(self)

        FactorBacktestEngine._compute_fwd_returns = counting_compute

        try:
            engine = FactorBacktestEngine(dl)
            engine.run()
            # 3 个因子，但 fwd_returns 的实际计算 (for-loop) 只执行一次
            assert compute_count == 1, f"预期 1 次实际计算，实际 {compute_count} 次"
        finally:
            FactorBacktestEngine._compute_fwd_returns = original_compute

    def test_multiple_engines_with_shared_fwd(self):
        """多个引擎共享预计算 fwd_returns: 每个引擎都不重新计算"""
        dl1 = make_dataloader(n_dates=60, n_stocks=100, n_factors=1, seed=42)
        dl2 = make_dataloader(n_dates=60, n_stocks=100, n_factors=1, seed=43)

        # 预计算一次
        engine0 = FactorBacktestEngine(dl1)
        fwd = engine0._compute_fwd_returns()

        # 两个引擎共享
        engine1 = FactorBacktestEngine(dl1, fwd_returns=fwd)
        engine2 = FactorBacktestEngine(dl2, fwd_returns=fwd)

        r1 = engine1.run()
        r2 = engine2.run()

        # 两个引擎都应该产生有效结果
        for fn in dl1.factor_names:
            assert not np.isnan(r1[fn]['rank_icir'])
            assert not np.isnan(r2[fn]['rank_icir'])

    def test_fwd_returns_consistent_across_engine_instances(self):
        """不同引擎实例自计算 fwd_returns: 结果应该一致 (相同价格)"""
        dl1 = make_dataloader(n_dates=60, n_stocks=100, n_factors=1, seed=42)
        dl2 = make_dataloader(n_dates=60, n_stocks=100, n_factors=1, seed=42)

        engine1 = FactorBacktestEngine(dl1)
        engine2 = FactorBacktestEngine(dl2)

        fwd1 = engine1._compute_fwd_returns()
        fwd2 = engine2._compute_fwd_returns()

        np.testing.assert_array_equal(fwd1, fwd2)


# =============================================================================
# Test 3: 并行一致性
# =============================================================================

class TestParallelConsistency:
    """并行执行与串行执行结果一致"""

    def test_same_fwd_same_results(self):
        """相同 fwd_returns 产生相同结果"""
        dl = make_dataloader(n_dates=60, n_stocks=100, n_factors=3, seed=42)

        # 预计算 fwd
        engine_prep = FactorBacktestEngine(dl)
        fwd = engine_prep._compute_fwd_returns()

        # 跑两次，应该完全一致
        engine1 = FactorBacktestEngine(dl, fwd_returns=fwd)
        engine2 = FactorBacktestEngine(dl, fwd_returns=fwd)

        r1 = engine1.run()
        r2 = engine2.run()

        for fn in dl.factor_names:
            for key in ['rank_icir', 'pearson_icir', 'hit_rate', 'spread']:
                assert r1[fn][key] == r2[fn][key], \
                    f"{fn}.{key}: {r1[fn][key]} != {r2[fn][key]}"

    def test_icir_stable_across_runs(self):
        """ICIR 在多次运行中稳定 (确定性的)"""
        dl = make_dataloader(n_dates=60, n_stocks=100, n_factors=3, seed=42)

        engine = FactorBacktestEngine(dl)
        fwd = engine._compute_fwd_returns()

        icirs = []
        for _ in range(3):
            engine_i = FactorBacktestEngine(dl, fwd_returns=fwd)
            results = engine_i.run()
            icirs.append([results[fn]['rank_icir'] for fn in dl.factor_names])

        # 所有运行应该完全一致
        for i in range(3):
            for j in range(3):
                np.testing.assert_array_equal(icirs[i], icirs[j])


# =============================================================================
# Test 4: 边界条件
# =============================================================================

class TestEdgeCases:
    """边界条件测试"""

    def test_all_nan_fwd_returns(self):
        """全 NaN 的 fwd_returns 应该被接受 (但不产生有意义的结果)"""
        dl = make_dataloader()
        fwd = np.full((dl.n_dates - 1, dl.n_stocks), np.nan)

        engine = FactorBacktestEngine(dl, fwd_returns=fwd)
        results = engine.run()

        for fn in dl.factor_names:
            assert np.isnan(results[fn]['rank_icir'])

    def test_none_fwd_returns(self):
        """fwd_returns=None 应该触发自计算"""
        dl = make_dataloader()

        engine = FactorBacktestEngine(dl, fwd_returns=None)
        results = engine.run()

        for fn in dl.factor_names:
            assert not np.isnan(results[fn]['rank_icir'])

    def test_partial_nan_fwd_returns(self):
        """部分 NaN 的 fwd_returns 应该正常工作"""
        dl = make_dataloader(n_dates=60, n_stocks=100, n_factors=1, seed=42)
        # 使用随机值 (非恒定)，部分为 NaN — 模拟真实场景
        rng = np.random.default_rng(123)
        fwd = rng.normal(0.001, 0.02, (dl.n_dates - 1, dl.n_stocks))
        fwd[0, :20] = np.nan  # 前 20 只股票第一天为 NaN

        engine = FactorBacktestEngine(dl, fwd_returns=fwd)
        results = engine.run()

        for fn in dl.factor_names:
            # 部分 NaN 不应导致 ICIR 为 NaN (剩余足够数据计算)
            assert not np.isnan(results[fn]['rank_icir'])


# =============================================================================
# Test 5: 新公开方法 compute_fwd_returns
# =============================================================================

class TestPublicFwdReturnsMethod:
    """公开的 compute_fwd_returns 方法"""

    def test_compute_fwd_returns_public(self):
        """compute_fwd_returns() 是公开方法"""
        dl = make_dataloader()
        engine = FactorBacktestEngine(dl)

        fwd = engine.compute_fwd_returns()
        assert fwd.shape == (dl.n_dates - 1, dl.n_stocks)
        assert not np.all(np.isnan(fwd))

    def test_compute_fwd_returns_idempotent(self):
        """多次调用 compute_fwd_returns() 返回相同结果"""
        dl = make_dataloader()
        engine = FactorBacktestEngine(dl)

        fwd1 = engine.compute_fwd_returns()
        fwd2 = engine.compute_fwd_returns()

        np.testing.assert_array_equal(fwd1, fwd2)


# =============================================================================
# Test 6: 共享 fwd_returns 的 summary 一致性
# =============================================================================

class TestSummaryConsistency:
    """summary() 在使用共享 fwd_returns 时的一致性"""

    def test_summary_identical(self):
        """共享 vs 自计算 fwd_returns: summary 完全一致"""
        dl = make_dataloader(n_dates=60, n_stocks=100, n_factors=2, seed=42)

        # 自计算
        engine1 = FactorBacktestEngine(dl)
        engine1.run()
        s1 = engine1.summary()

        # 预计算
        fwd = engine1._compute_fwd_returns()
        dl2 = make_dataloader(n_dates=60, n_stocks=100, n_factors=2, seed=42)
        engine2 = FactorBacktestEngine(dl2, fwd_returns=fwd)
        engine2.run()
        s2 = engine2.summary()

        for fn in dl.factor_names:
            for key in s1[fn]:
                assert s1[fn][key] == s2[fn][key], \
                    f"{fn}.{key}: {s1[fn][key]} != {s2[fn][key]}"

    def test_rank_by_icir_identical(self):
        """共享 vs 自计算 fwd_returns: rank_by_icir 完全一致"""
        dl = make_dataloader(n_dates=60, n_stocks=100, n_factors=3, seed=42)

        engine1 = FactorBacktestEngine(dl)
        ranking1 = engine1.rank_by_icir()

        fwd = engine1._compute_fwd_returns()
        dl2 = make_dataloader(n_dates=60, n_stocks=100, n_factors=3, seed=42)
        engine2 = FactorBacktestEngine(dl2, fwd_returns=fwd)
        ranking2 = engine2.rank_by_icir()

        assert ranking1 == ranking2