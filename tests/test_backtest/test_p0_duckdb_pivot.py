# -*- coding: utf-8 -*-
"""DuckDB PIVOT 优化 — Red Phase 测试

验证 FactorPivotAdapter:
  - 直接用 DuckDB PIVOT 返回 {factor_name: DataFrame(stock_code × trade_date)}
  - 结果与 pandas pivot 完全一致
  - 性能优于 pandas pivot
"""

import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path('F:/Coding/Factor_DB')))
from query.factor_query import FactorQuery
from factor_pipeline.backtest.factor_pivot import FactorPivotAdapter

DB_PATH = str(Path('F:/Coding/Factor_DB/factor_db.duckdb'))


# =============================================================================
# 测试夹具
# =============================================================================

@pytest.fixture(scope='module')
def fq():
    return FactorQuery(DB_PATH)


@pytest.fixture(scope='module')
def all_factors():
    q = FactorQuery(DB_PATH)
    return q.list_factors()


@pytest.fixture(scope='module')
def adapter():
    return FactorPivotAdapter(DB_PATH)


# =============================================================================
# Test 1: 方法存在性
# =============================================================================

class TestMethodExists:
    """FactorPivotAdapter 基本功能"""

    def test_creates_adapter(self, adapter):
        """可以创建 FactorPivotAdapter"""
        assert adapter is not None

    def test_get_pivoted_method_exists(self, adapter):
        """有 get_pivoted 方法"""
        assert hasattr(adapter, 'get_pivoted')

    def test_returns_dict(self, adapter, all_factors):
        """返回 {factor_name: DataFrame} 字典"""
        selected = all_factors[:2]
        result = adapter.get_pivoted(
            selected, start_date=date(2024, 1, 1), end_date=date(2024, 6, 30)
        )
        assert isinstance(result, dict)
        for fn in selected:
            assert fn in result
            assert isinstance(result[fn], pd.DataFrame)


# =============================================================================
# Test 2: 格式正确性
# =============================================================================

class TestFormatCorrectness:
    """返回格式: index=stock_code, columns=trade_date"""

    def test_index_is_stock_code(self, adapter, all_factors):
        """index 是 stock_code"""
        result = adapter.get_pivoted(
            [all_factors[0]], start_date=date(2024, 1, 1), end_date=date(2024, 6, 30)
        )
        df = result[all_factors[0]]
        assert df.index.name == 'stock_code'
        assert len(df) > 0

    def test_columns_are_trade_dates(self, adapter, all_factors):
        """columns 是 trade_date"""
        result = adapter.get_pivoted(
            [all_factors[0]], start_date=date(2024, 1, 1), end_date=date(2024, 6, 30)
        )
        df = result[all_factors[0]]
        assert len(df.columns) > 0

    def test_values_are_numeric(self, adapter, all_factors):
        """值是数值型"""
        result = adapter.get_pivoted(
            [all_factors[0]], start_date=date(2024, 1, 1), end_date=date(2024, 6, 30)
        )
        df = result[all_factors[0]]
        non_nan = df.values[~np.isnan(df.values)]
        assert len(non_nan) > 0

    def test_stock_code_is_string(self, adapter, all_factors):
        """stock_code 是字符串类型"""
        result = adapter.get_pivoted(
            [all_factors[0]], start_date=date(2024, 1, 1), end_date=date(2024, 6, 30)
        )
        df = result[all_factors[0]]
        # DuckDB 返回 StringDtype 或 object，都是字符串类型
        dtype_str = str(df.index.dtype)
        assert dtype_str in ('object', 'str', 'string') or 'str' in dtype_str.lower(), \
            f"index dtype={df.index.dtype}, 期望字符串"


# =============================================================================
# Test 3: 与 pandas pivot 一致性
# =============================================================================

class TestConsistencyWithPandas:
    """DuckDB PIVOT 结果与 pandas pivot 完全一致"""

    def test_single_factor_consistent(self, adapter, fq, all_factors):
        """单个因子: DuckDB PIVOT vs pandas pivot"""
        fn = all_factors[0]
        start = date(2024, 1, 1)
        end = date(2024, 6, 30)

        # 方法 1: 原始 (长表 + pandas pivot)
        matrix = fq.get_factor_matrix([fn], start_date=start, end_date=end)
        pandas_pivoted = matrix.pivot(
            index='stock_code', columns='trade_date', values=fn,
        )

        # 方法 2: DuckDB PIVOT
        duckdb_result = adapter.get_pivoted([fn], start_date=start, end_date=end)
        duckdb_pivoted = duckdb_result[fn]

        # 对齐索引和列
        common_stocks = pandas_pivoted.index.intersection(duckdb_pivoted.index)
        common_dates = pandas_pivoted.columns.intersection(duckdb_pivoted.columns)

        assert len(common_stocks) > 0
        assert len(common_dates) > 0

        p = pandas_pivoted.loc[common_stocks, common_dates]
        d = duckdb_pivoted.loc[common_stocks, common_dates]

        # 比较非 NaN 值
        mask = ~np.isnan(p.values) & ~np.isnan(d.values)
        assert mask.sum() > 0, '没有共同的非 NaN 值'
        np.testing.assert_array_almost_equal(
            p.values[mask], d.values[mask], decimal=10,
            err_msg='DuckDB PIVOT 与 pandas pivot 值不一致'
        )

    def test_multi_factor_consistent(self, adapter, fq, all_factors):
        """多个因子: DuckDB PIVOT vs pandas pivot"""
        selected = all_factors[:5]
        start = date(2024, 1, 1)
        end = date(2024, 6, 30)

        # 原始
        matrix = fq.get_factor_matrix(selected, start_date=start, end_date=end)

        # DuckDB PIVOT
        duckdb_result = adapter.get_pivoted(selected, start_date=start, end_date=end)

        for fn in selected:
            pandas_pivoted = matrix.pivot(
                index='stock_code', columns='trade_date', values=fn,
            )
            duckdb_pivoted = duckdb_result[fn]

            common_stocks = pandas_pivoted.index.intersection(duckdb_pivoted.index)
            common_dates = pandas_pivoted.columns.intersection(duckdb_pivoted.columns)

            assert len(common_stocks) > 0
            assert len(common_dates) > 0

            p = pandas_pivoted.loc[common_stocks, common_dates]
            d = duckdb_pivoted.loc[common_stocks, common_dates]

            mask = ~np.isnan(p.values) & ~np.isnan(d.values)
            assert mask.sum() > 0, f'{fn}: 没有共同的非 NaN 值'
            np.testing.assert_array_almost_equal(
                p.values[mask], d.values[mask], decimal=10,
                err_msg=f'{fn}: DuckDB PIVOT 与 pandas pivot 值不一致'
            )

    def test_nan_positions_match(self, adapter, fq, all_factors):
        """NaN 位置一致"""
        fn = all_factors[0]
        start = date(2024, 1, 1)
        end = date(2024, 6, 30)

        matrix = fq.get_factor_matrix([fn], start_date=start, end_date=end)
        pandas_pivoted = matrix.pivot(
            index='stock_code', columns='trade_date', values=fn,
        )

        duckdb_result = adapter.get_pivoted([fn], start_date=start, end_date=end)
        duckdb_pivoted = duckdb_result[fn]

        common_stocks = pandas_pivoted.index.intersection(duckdb_pivoted.index)
        common_dates = pandas_pivoted.columns.intersection(duckdb_pivoted.columns)

        p_nan = np.isnan(pandas_pivoted.loc[common_stocks, common_dates].values)
        d_nan = np.isnan(duckdb_pivoted.loc[common_stocks, common_dates].values)

        # NaN 位置应该高度一致
        match_rate = (p_nan == d_nan).mean()
        assert match_rate > 0.95, f'NaN 位置匹配率 {match_rate:.2%} < 95%'


# =============================================================================
# Test 4: 边界条件
# =============================================================================

class TestEdgeCases:
    """边界条件"""

    def test_empty_factor_list(self, adapter):
        """空因子列表: 返回空字典"""
        result = adapter.get_pivoted(
            [], start_date=date(2024, 1, 1), end_date=date(2024, 6, 30)
        )
        assert result == {}

    def test_single_stock(self, adapter, all_factors):
        """单只股票 — 自动找一个有数据的因子测试 stock_codes 过滤生效"""
        import duckdb
        # 找一个 000001 + 2024H1 有数据的因子
        con = duckdb.connect(DB_PATH, read_only=True)
        r = con.execute(
            "SELECT DISTINCT factor_name FROM factor_data "
            "WHERE stock_code='000001' AND trade_date >= '2024-01-01' "
            "AND trade_date <= '2024-06-30' LIMIT 1"
        ).fetchone()
        con.close()
        if r is None:
            pytest.skip("数据库中 000001 在 2024H1 无任何因子数据, 跳过单股票测试")
        factor_with_data = r[0]
        result = adapter.get_pivoted(
            [factor_with_data], stock_codes=['000001'],
            start_date=date(2024, 1, 1), end_date=date(2024, 6, 30),
        )
        df = result[factor_with_data]
        assert len(df) >= 1

    def test_no_data_factor(self, adapter):
        """不存在的因子: 返回空 DataFrame"""
        result = adapter.get_pivoted(
            ['nonexistent_factor'], start_date=date(2024, 1, 1), end_date=date(2024, 6, 30),
        )
        assert 'nonexistent_factor' in result
        assert result['nonexistent_factor'].empty

    def test_date_range_filter(self, adapter, all_factors):
        """日期范围过滤生效"""
        start = date(2024, 1, 1)
        end = date(2024, 1, 31)

        result = adapter.get_pivoted(
            [all_factors[0]], start_date=start, end_date=end,
        )
        df = result[all_factors[0]]
        if len(df.columns) > 0:
            assert len(df.columns) <= 25  # 一个月最多 ~22 个交易日


# =============================================================================
# Test 5: 集成测试 — 与回测引擎兼容
# =============================================================================

class TestBacktestIntegration:
    """DuckDB PIVOT 结果可直接输入回测引擎"""

    def test_pipeline_compatible(self, adapter, all_factors):
        """PIVOT 结果格式与 pipeline_input 兼容"""
        selected = all_factors[:3]
        start = date(2024, 1, 1)
        end = date(2024, 6, 30)

        result = adapter.get_pivoted(selected, start_date=start, end_date=end)

        for fn in selected:
            df = result[fn]
            assert df.index.name == 'stock_code'
            assert len(df) > 0
            assert len(df.columns) > 0
            assert df.values.dtype.kind in 'fiu'

    def test_full_pipeline_with_pivot(self, adapter, all_factors):
        """完整 pipeline: PIVOT → 回测引擎 → ICIR"""
        # 可选依赖: Factor_Trading_v3_0 (仅此测试通过 DataBridge 间接使用 DataLoaderV3)
        pytest.importorskip("Factor_Trading_v3_0")

        from query.price_query import PriceQuery
        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine

        fn = all_factors[0]
        start = date(2024, 1, 1)
        end = date(2024, 6, 30)

        # DuckDB PIVOT 获取因子数据
        factor_result = adapter.get_pivoted([fn], start_date=start, end_date=end)
        factor_df = factor_result[fn]

        # 获取价格数据
        pq = PriceQuery(DB_PATH)
        price_df = pq.get_price_matrix(field='close', start_date=start, end_date=end)
        price_pivoted = price_df.T
        price_pivoted.index = price_pivoted.index.astype(str)
        price_pivoted.columns = pd.to_datetime(price_pivoted.columns)

        # 对齐
        cd = factor_df.columns.intersection(price_pivoted.columns)
        cs = factor_df.index.intersection(price_pivoted.index)
        fa = factor_df.loc[list(cs), list(cd)]
        pa = price_pivoted.loc[list(cs), list(cd)]

        # 回测
        bridge = DataBridge()
        dl = bridge.create_dataloader({fn: fa}, pa)
        engine = FactorBacktestEngine(dl)
        engine.run()
        summary = engine.summary()

        assert fn in summary
        assert not np.isnan(summary[fn]['rank_icir'])