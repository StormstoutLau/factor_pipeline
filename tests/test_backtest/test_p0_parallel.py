# -*- coding: utf-8 -*-
"""P0 并行化 — Red Phase 测试"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from factor_pipeline.backtest.parallel_runner import ParallelFactorRunner, run_parallel


# =============================================================================
# 测试夹具
# =============================================================================

def make_factor_data(n_factors=6, n_stocks=100, n_dates=60, seed=42):
    """生成模拟因子数据"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2020-01-01', periods=n_dates, freq='B')
    stocks = [f'STOCK_{i:04d}' for i in range(n_stocks)]

    factor_data = {}
    for i in range(n_factors):
        data = rng.normal(0, 1, (n_stocks, n_dates))
        factor_data[f'factor_{i}'] = pd.DataFrame(
            data, index=stocks, columns=dates,
        )

    return factor_data


def make_price_data(n_stocks=100, n_dates=60, seed=42):
    """生成模拟价格数据"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2020-01-01', periods=n_dates, freq='B')
    stocks = [f'STOCK_{i:04d}' for i in range(n_stocks)]

    log_ret = rng.normal(0.001, 0.02, (n_stocks, n_dates))
    price = 100 * np.exp(np.cumsum(log_ret, axis=1))
    return pd.DataFrame(price, index=stocks, columns=dates)


# =============================================================================
# Test 1: 基本功能
# =============================================================================

class TestParallelRunnerBasic:
    """并行运行器基本功能"""

    def test_creates_runner(self):
        """可以创建 ParallelFactorRunner"""
        runner = ParallelFactorRunner(n_workers=2)
        assert runner.n_workers == 2

    def test_default_workers(self):
        """默认 workers 数"""
        runner = ParallelFactorRunner()
        assert runner.n_workers >= 1

    def test_run_parallel_function(self):
        """run_parallel 便捷函数可用"""
        factor_data = make_factor_data(n_factors=3)
        price_data = make_price_data()

        results = run_parallel(factor_data, price_data, n_workers=2)
        assert len(results) == 3
        for fn in factor_data:
            assert fn in results
            assert 'rank_icir' in results[fn]
            assert not np.isnan(results[fn]['rank_icir'])


# =============================================================================
# Test 2: 串行 vs 并行一致性
# =============================================================================

class TestSerialParallelConsistency:
    """串行结果与并行结果完全一致"""

    def test_results_identical_6_factors_2_workers(self):
        """6 个因子，2 个 worker: 结果一致"""
        factor_data = make_factor_data(n_factors=6)
        price_data = make_price_data()

        # 串行
        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine

        bridge = DataBridge()
        serial_results = {}
        for fn in factor_data:
            dl = bridge.create_dataloader({fn: factor_data[fn]}, price_data)
            engine = FactorBacktestEngine(dl)
            engine.run()
            serial_results[fn] = engine.summary()[fn]

        # 并行
        parallel_results = run_parallel(factor_data, price_data, n_workers=2)

        # 逐因子对比
        for fn in factor_data:
            s = serial_results[fn]
            p = parallel_results[fn]
            for key in ['rank_icir', 'pearson_icir', 'mean_rank_ic']:
                assert s[key] == p[key], \
                    f"{fn}.{key}: serial={s[key]}, parallel={p[key]}"

    def test_results_identical_3_factors_1_worker(self):
        """3 个因子，1 个 worker: 结果一致 (退化情况)"""
        factor_data = make_factor_data(n_factors=3)
        price_data = make_price_data()

        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine

        bridge = DataBridge()
        serial_results = {}
        for fn in factor_data:
            dl = bridge.create_dataloader({fn: factor_data[fn]}, price_data)
            engine = FactorBacktestEngine(dl)
            engine.run()
            serial_results[fn] = engine.summary()[fn]

        parallel_results = run_parallel(factor_data, price_data, n_workers=1)

        for fn in factor_data:
            s = serial_results[fn]
            p = parallel_results[fn]
            for key in ['rank_icir', 'pearson_icir', 'mean_rank_ic']:
                assert s[key] == p[key]


# =============================================================================
# Test 3: 日期范围分组
# =============================================================================

class TestDateRangeGrouping:
    """不同日期范围的因子被正确分组"""

    def test_factors_with_different_dates(self):
        """因子有不同日期范围: 同组内共享 fwd_returns"""
        n_stocks = 100
        n_dates_long = 60
        n_dates_short = 30

        rng = np.random.default_rng(42)
        stocks = [f'STOCK_{i:04d}' for i in range(n_stocks)]

        # 长日期因子
        dates_long = pd.date_range('2020-01-01', periods=n_dates_long, freq='B')
        factor_long = pd.DataFrame(
            rng.normal(0, 1, (n_stocks, n_dates_long)),
            index=stocks, columns=dates_long,
        )

        # 短日期因子 (与长日期有重叠)
        dates_short = pd.date_range('2020-01-15', periods=n_dates_short, freq='B')
        factor_short = pd.DataFrame(
            rng.normal(0, 1, (n_stocks, n_dates_short)),
            index=stocks, columns=dates_short,
        )

        # 价格数据覆盖全部日期 (长日期范围)
        price = pd.DataFrame(
            100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, (n_stocks, n_dates_long)), axis=1)),
            index=stocks, columns=dates_long,
        )

        factor_data = {
            'factor_long': factor_long,
            'factor_short': factor_short,
        }

        # 串行
        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine

        bridge = DataBridge()
        serial_results = {}
        for fn, fd in factor_data.items():
            cd = fd.columns.intersection(price.columns)
            cs = fd.index.intersection(price.index)
            fa = fd.loc[list(cs), list(cd)]
            pa = price.loc[list(cs), list(cd)]
            dl = bridge.create_dataloader({fn: fa}, pa)
            engine = FactorBacktestEngine(dl)
            engine.run()
            serial_results[fn] = engine.summary()[fn]

        # 并行
        parallel_results = run_parallel(factor_data, price, n_workers=2)

        for fn in factor_data:
            s = serial_results[fn]
            p = parallel_results[fn]
            for key in ['rank_icir', 'pearson_icir', 'mean_rank_ic']:
                assert s[key] == p[key], \
                    f"{fn}.{key}: serial={s[key]}, parallel={p[key]}"


# =============================================================================
# Test 4: 边界条件
# =============================================================================

class TestParallelEdgeCases:
    """并行化边界条件"""

    def test_single_factor(self):
        """单个因子也能并行运行"""
        factor_data = make_factor_data(n_factors=1)
        price_data = make_price_data()

        results = run_parallel(factor_data, price_data, n_workers=2)
        assert len(results) == 1
        assert not np.isnan(results['factor_0']['rank_icir'])

    def test_workers_exceed_factors(self):
        """workers 数 > 因子数: 正常降级"""
        factor_data = make_factor_data(n_factors=2)
        price_data = make_price_data()

        results = run_parallel(factor_data, price_data, n_workers=8)
        assert len(results) == 2

    def test_empty_factor_data(self):
        """空因子数据: 抛出异常"""
        with pytest.raises(ValueError):
            run_parallel({}, make_price_data(), n_workers=2)

    def test_idempotent(self):
        """多次运行结果一致"""
        factor_data = make_factor_data(n_factors=4)
        price_data = make_price_data()

        r1 = run_parallel(factor_data, price_data, n_workers=2)
        r2 = run_parallel(factor_data, price_data, n_workers=2)

        for fn in factor_data:
            for key in ['rank_icir', 'pearson_icir', 'mean_rank_ic']:
                assert r1[fn][key] == r2[fn][key]


# =============================================================================
# Test 5: 性能相关
# =============================================================================

class TestParallelPerformance:
    """并行化性能相关测试"""

    def test_all_factors_processed(self):
        """所有因子都被处理，无遗漏"""
        factor_data = make_factor_data(n_factors=10)
        price_data = make_price_data()

        results = run_parallel(factor_data, price_data, n_workers=3)
        assert len(results) == 10
        for fn in factor_data:
            assert fn in results

    def test_no_duplicate_results(self):
        """没有重复结果"""
        factor_data = make_factor_data(n_factors=5)
        price_data = make_price_data()

        results = run_parallel(factor_data, price_data, n_workers=2)
        assert len(results) == len(factor_data)
        assert sorted(results.keys()) == sorted(factor_data.keys())

    @pytest.mark.skipif(
        sys.platform == 'win32',
        reason="TD-2 (ADR-016): Windows multiprocessing 默认用 spawn 方法, "
               "进程启动开销显著 (每个子进程需重新导入所有模块), "
               "小数据量下并行必然慢于串行 (实测 4.5s vs 0.7s). "
               "Linux fork 方法无此问题. 功能正确性由 test_all_factors_processed "
               "和 test_no_duplicate_results 覆盖."
    )
    def test_parallel_is_not_slower_than_serial(self):
        """并行不应比串行慢超过 5x (小数据量下进程启动开销显著)

        TD-2: Windows 下 skip — spawn 方法进程启动开销使该断言不可靠.
        Linux fork 方法下并行有真实优势, 保留测试.
        """
        factor_data = make_factor_data(n_factors=8, n_stocks=80, n_dates=40)
        price_data = make_price_data(n_stocks=80, n_dates=40)

        # 串行计时
        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine

        bridge = DataBridge()
        t0 = time.perf_counter()
        for fn in factor_data:
            dl = bridge.create_dataloader({fn: factor_data[fn]}, price_data)
            engine = FactorBacktestEngine(dl)
            engine.run()
        t_serial = time.perf_counter() - t0

        # 并行计时
        t0 = time.perf_counter()
        run_parallel(factor_data, price_data, n_workers=2)
        t_parallel = time.perf_counter() - t0

        # 小数据量下进程启动开销显著，放宽到 5x
        # 真实大数据量下并行优势明显（见手工校验）
        assert t_parallel < t_serial * 5, \
            f"并行 {t_parallel:.1f}s > 串行 {t_serial:.1f}s × 5"


# =============================================================================
# Test 6: Runner 类方法
# =============================================================================

class TestRunnerMethods:
    """ParallelFactorRunner 类方法"""

    def test_runner_run_method(self):
        """runner.run() 方法可用"""
        factor_data = make_factor_data(n_factors=4)
        price_data = make_price_data()

        runner = ParallelFactorRunner(n_workers=2)
        results = runner.run(factor_data, price_data)
        assert len(results) == 4

    def test_runner_with_config(self):
        """runner.run() 接受 config"""
        factor_data = make_factor_data(n_factors=3)
        price_data = make_price_data()

        runner = ParallelFactorRunner(n_workers=2)
        results = runner.run(factor_data, price_data, config={'top_n': 0.3})
        assert len(results) == 3
        for fn in results:
            assert not np.isnan(results[fn]['rank_icir'])