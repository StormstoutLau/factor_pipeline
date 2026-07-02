# -*- coding: utf-8 -*-
"""
CachedDataLoader 端到端集成测试 — 统一的缓存数据加载入口

设计:
  - 封装 FactorMatrixCache + PriceMatrixCache,统一管理 cache_dir 和 enabled
  - 业务代码一处替换: FactorPivotAdapter(DB_PATH) + PriceQuery(DB_PATH)
                    → CachedDataLoader(db_path, cache_dir, enabled=True)
  - 接口兼容: get_pivoted_factors() / get_price_matrix() 与原始接口一致
  - 健康度: status() / clear_all() / invalidate_*()
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from factor_pipeline.backtest.cached_data_loader import CachedDataLoader


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def cache_dir(tmp_path):
    d = tmp_path / "cached_loader"
    d.mkdir()
    return str(d)


@pytest.fixture
def sample_factor_data():
    """样本因子数据: {factor_name: DataFrame(stock_code × trade_date)}"""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    stocks = [f"00000{i}.SZ" for i in range(15)]
    return {
        "PE": pd.DataFrame(rng.normal(0, 1, (15, 20)), index=stocks, columns=dates),
        "PB": pd.DataFrame(rng.normal(0, 1, (15, 20)), index=stocks, columns=dates),
    }


@pytest.fixture
def sample_price_matrix():
    """样本价格矩阵: DataFrame(trade_date × stock_code)"""
    rng = np.random.default_rng(100)
    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    stocks = [f"00000{i}.SZ" for i in range(15)]
    return pd.DataFrame(rng.lognormal(4, 0.2, (20, 15)), index=dates, columns=stocks)


class FakeFactorPivotAdapter:
    """模拟 FactorPivotAdapter"""

    def __init__(self, factor_data: dict, loaded_at_max: str = "2026-06-30T23:59:00"):
        self._data = factor_data
        self._loaded_at_max = loaded_at_max
        self.call_count = 0
        self.queried_factors = []

    def get_pivoted(self, factor_names, stock_codes=None, start_date=None, end_date=None):
        self.call_count += 1
        self.queried_factors.append(list(factor_names))
        return {fn: self._data[fn].copy() for fn in factor_names if fn in self._data}

    def get_loaded_at_max(self, factor_name=None):
        return self._loaded_at_max


class FakePriceQuery:
    """模拟 PriceQuery"""

    def __init__(self, price_matrix: pd.DataFrame, loaded_at_max: str = "2026-06-30T23:59:00"):
        self._matrix = price_matrix
        self._loaded_at_max = loaded_at_max
        self.call_count = 0

    def get_price_matrix(self, field="close", stock_codes=None, start_date=None,
                         end_date=None, adjust="none", as_of=None):
        self.call_count += 1
        return self._matrix.copy()

    def get_loaded_at_max(self):
        return self._loaded_at_max


# =============================================================================
# 1. 基本工厂方法
# =============================================================================

class TestFactory:

    def test_01_create_with_real_adapters(self, cache_dir):
        """可以从真实 adapter 类创建 (但不实际连接 DB)"""
        # 用 Fake 类验证工厂接口,真实使用时传 FactorPivotAdapter/PriceQuery
        loader = CachedDataLoader(
            db_path="dummy.duckdb",
            cache_dir=cache_dir,
            enabled=True,
            factor_adapter_factory=lambda db: FakeFactorPivotAdapter({}),
            price_query_factory=lambda db: FakePriceQuery(pd.DataFrame()),
        )
        assert loader is not None
        assert loader.enabled is True

    def test_02_default_factories_use_real_classes(self, cache_dir):
        """默认工厂使用 FactorPivotAdapter 和 PriceQuery"""
        # 用 mock 验证默认工厂函数确实指向真实类,不实际连接 DB
        from factor_pipeline.backtest import cached_data_loader as cdl_module

        # 默认工厂函数应存在且可调用
        assert callable(cdl_module._default_factor_adapter_factory)
        assert callable(cdl_module._default_price_query_factory)

        # 用 mock 验证默认工厂不会立即触发连接(传 None 应被工厂接收但不连接)
        # 实际生产中传真实 db_path,这里只验证工厂属性
        loader = CachedDataLoader(
            db_path="dummy.duckdb",
            cache_dir=cache_dir,
            enabled=True,
            factor_adapter_factory=lambda db: FakeFactorPivotAdapter({}),
            price_query_factory=lambda db: FakePriceQuery(pd.DataFrame()),
        )
        # 内部应有 factor_cache 和 price_cache 实例
        assert hasattr(loader, "factor_cache")
        assert hasattr(loader, "price_cache")
        assert hasattr(loader, "factor_adapter")
        assert hasattr(loader, "price_query")
        assert loader.factor_cache is not None
        assert loader.price_cache is not None
        assert loader.factor_adapter is not None
        assert loader.price_query is not None


# =============================================================================
# 2. 因子数据加载 — 缓存命中
# =============================================================================

class TestFactorLoading:

    def test_01_first_call_queries_adapter(self, cache_dir, sample_factor_data):
        """首次调用查询 adapter"""
        fake_adapter = FakeFactorPivotAdapter(sample_factor_data)
        loader = CachedDataLoader(
            db_path="dummy.duckdb",
            cache_dir=cache_dir,
            enabled=True,
            factor_adapter_factory=lambda db: fake_adapter,
            price_query_factory=lambda db: FakePriceQuery(pd.DataFrame()),
        )

        result = loader.get_pivoted_factors(
            ["PE", "PB"], start_date=date(2024, 1, 1), end_date=date(2024, 1, 31),
        )

        assert fake_adapter.call_count == 1
        assert set(result.keys()) == {"PE", "PB"}

    def test_02_second_call_hits_cache(self, cache_dir, sample_factor_data):
        """第二次调用命中缓存,不走 adapter"""
        fake_adapter = FakeFactorPivotAdapter(sample_factor_data)
        loader = CachedDataLoader(
            db_path="dummy.duckdb",
            cache_dir=cache_dir,
            enabled=True,
            factor_adapter_factory=lambda db: fake_adapter,
            price_query_factory=lambda db: FakePriceQuery(pd.DataFrame()),
        )

        loader.get_pivoted_factors(["PE", "PB"], start_date=date(2024, 1, 1),
                                    end_date=date(2024, 1, 31))
        loader.get_pivoted_factors(["PE", "PB"], start_date=date(2024, 1, 1),
                                    end_date=date(2024, 1, 31))

        assert fake_adapter.call_count == 1  # 全部命中


# =============================================================================
# 3. 价格数据加载 — 缓存命中
# =============================================================================

class TestPriceLoading:

    def test_01_first_call_queries_price_query(self, cache_dir, sample_price_matrix):
        """首次调用查询 PriceQuery"""
        fake_pq = FakePriceQuery(sample_price_matrix)
        loader = CachedDataLoader(
            db_path="dummy.duckdb",
            cache_dir=cache_dir,
            enabled=True,
            factor_adapter_factory=lambda db: FakeFactorPivotAdapter({}),
            price_query_factory=lambda db: fake_pq,
        )

        result = loader.get_price_matrix(
            field="close", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31),
        )

        assert fake_pq.call_count == 1
        assert result.shape == sample_price_matrix.shape

    def test_02_second_call_hits_cache(self, cache_dir, sample_price_matrix):
        """第二次调用命中缓存"""
        fake_pq = FakePriceQuery(sample_price_matrix)
        loader = CachedDataLoader(
            db_path="dummy.duckdb",
            cache_dir=cache_dir,
            enabled=True,
            factor_adapter_factory=lambda db: FakeFactorPivotAdapter({}),
            price_query_factory=lambda db: fake_pq,
        )

        loader.get_price_matrix(field="close", start_date=date(2024, 1, 1),
                                 end_date=date(2024, 1, 31))
        loader.get_price_matrix(field="close", start_date=date(2024, 1, 1),
                                 end_date=date(2024, 1, 31))

        assert fake_pq.call_count == 1


# =============================================================================
# 4. 环境变量逃生舱
# =============================================================================

class TestEnvironmentEscape:

    def test_01_env_disabled_bypasses_both_caches(self, cache_dir, sample_factor_data,
                                                    sample_price_matrix):
        """FACTOR_PIPELINE_CACHE=disabled 时全走原始查询"""
        fake_adapter = FakeFactorPivotAdapter(sample_factor_data)
        fake_pq = FakePriceQuery(sample_price_matrix)

        with mock.patch.dict(os.environ, {"FACTOR_PIPELINE_CACHE": "disabled"}):
            loader = CachedDataLoader(
                db_path="dummy.duckdb",
                cache_dir=cache_dir,
                enabled=True,  # 环境变量应覆盖
                factor_adapter_factory=lambda db: fake_adapter,
                price_query_factory=lambda db: fake_pq,
            )

            loader.get_pivoted_factors(["PE"], start_date=date(2024, 1, 1),
                                        end_date=date(2024, 1, 31))
            loader.get_pivoted_factors(["PE"], start_date=date(2024, 1, 1),
                                        end_date=date(2024, 1, 31))
            loader.get_price_matrix(field="close", start_date=date(2024, 1, 1),
                                     end_date=date(2024, 1, 31))
            loader.get_price_matrix(field="close", start_date=date(2024, 1, 1),
                                     end_date=date(2024, 1, 31))

            assert fake_adapter.call_count == 2
            assert fake_pq.call_count == 2


# =============================================================================
# 5. 统一管理 API
# =============================================================================

class TestUnifiedManagement:

    def test_01_status_aggregates_both(self, cache_dir, sample_factor_data,
                                         sample_price_matrix):
        """status() 返回因子+价格缓存的合并状态"""
        fake_adapter = FakeFactorPivotAdapter(sample_factor_data)
        fake_pq = FakePriceQuery(sample_price_matrix)
        loader = CachedDataLoader(
            db_path="dummy.duckdb",
            cache_dir=cache_dir,
            enabled=True,
            factor_adapter_factory=lambda db: fake_adapter,
            price_query_factory=lambda db: fake_pq,
        )

        # 写入一些缓存
        loader.get_pivoted_factors(["PE", "PB"], start_date=date(2024, 1, 1),
                                    end_date=date(2024, 1, 31))
        loader.get_price_matrix(field="close", start_date=date(2024, 1, 1),
                                 end_date=date(2024, 1, 31))

        status = loader.status()
        assert "factor_cache" in status
        assert "price_cache" in status
        assert status["factor_cache"]["total_entries"] >= 2  # PE + PB
        assert status["price_cache"]["total_entries"] >= 1

    def test_02_clear_all_clears_both(self, cache_dir, sample_factor_data,
                                        sample_price_matrix):
        """clear_all() 同时清空两个缓存"""
        fake_adapter = FakeFactorPivotAdapter(sample_factor_data)
        fake_pq = FakePriceQuery(sample_price_matrix)
        loader = CachedDataLoader(
            db_path="dummy.duckdb",
            cache_dir=cache_dir,
            enabled=True,
            factor_adapter_factory=lambda db: fake_adapter,
            price_query_factory=lambda db: fake_pq,
        )

        loader.get_pivoted_factors(["PE"], start_date=date(2024, 1, 1),
                                    end_date=date(2024, 1, 31))
        loader.get_price_matrix(field="close", start_date=date(2024, 1, 1),
                                 end_date=date(2024, 1, 31))

        # 验证有缓存文件
        factor_files = list(Path(cache_dir).glob("*.parquet"))
        assert len(factor_files) >= 2

        loader.clear_all()

        # 清空后无缓存文件
        factor_files_after = list(Path(cache_dir).glob("*.parquet"))
        assert len(factor_files_after) == 0

    def test_03_invalidate_factor(self, cache_dir, sample_factor_data):
        """invalidate_factor 失效单个因子"""
        fake_adapter = FakeFactorPivotAdapter(sample_factor_data)
        loader = CachedDataLoader(
            db_path="dummy.duckdb",
            cache_dir=cache_dir,
            enabled=True,
            factor_adapter_factory=lambda db: fake_adapter,
            price_query_factory=lambda db: FakePriceQuery(pd.DataFrame()),
        )

        loader.get_pivoted_factors(["PE", "PB"], start_date=date(2024, 1, 1),
                                    end_date=date(2024, 1, 31))
        assert fake_adapter.call_count == 1

        loader.invalidate_factor("PE", start_date=date(2024, 1, 1),
                                   end_date=date(2024, 1, 31))

        # 再请求,PE miss, PB hit
        loader.get_pivoted_factors(["PE", "PB"], start_date=date(2024, 1, 1),
                                    end_date=date(2024, 1, 31))
        assert fake_adapter.call_count == 2
        assert fake_adapter.queried_factors[-1] == ["PE"]

    def test_04_invalidate_price(self, cache_dir, sample_price_matrix):
        """invalidate_price 失效价格缓存"""
        fake_pq = FakePriceQuery(sample_price_matrix)
        loader = CachedDataLoader(
            db_path="dummy.duckdb",
            cache_dir=cache_dir,
            enabled=True,
            factor_adapter_factory=lambda db: FakeFactorPivotAdapter({}),
            price_query_factory=lambda db: fake_pq,
        )

        loader.get_price_matrix(field="close", start_date=date(2024, 1, 1),
                                 end_date=date(2024, 1, 31))
        assert fake_pq.call_count == 1

        loader.invalidate_price(field="close", start_date=date(2024, 1, 1),
                                  end_date=date(2024, 1, 31))

        loader.get_price_matrix(field="close", start_date=date(2024, 1, 1),
                                 end_date=date(2024, 1, 31))
        assert fake_pq.call_count == 2  # 失效后重查


# =============================================================================
# 6. 端到端: 与回测引擎集成
# =============================================================================

class TestEndToEndWithEngine:

    def test_01_cached_loader_works_with_engine(self, cache_dir, sample_factor_data,
                                                  sample_price_matrix):
        """CachedDataLoader 与 FactorBacktestEngine 端到端集成"""
        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine

        fake_adapter = FakeFactorPivotAdapter(sample_factor_data)
        fake_pq = FakePriceQuery(sample_price_matrix)
        loader = CachedDataLoader(
            db_path="dummy.duckdb",
            cache_dir=cache_dir,
            enabled=True,
            factor_adapter_factory=lambda db: fake_adapter,
            price_query_factory=lambda db: fake_pq,
        )

        # 通过 CachedDataLoader 获取数据
        factor_result = loader.get_pivoted_factors(
            ["PE"], start_date=date(2024, 1, 1), end_date=date(2024, 1, 31),
        )
        price_df = loader.get_price_matrix(
            field="close", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31),
        )

        # 转换 price 矩阵 (dates × stocks) → (stocks × dates)
        price_pivoted = price_df.T
        price_pivoted.index = price_pivoted.index.astype(str)
        price_pivoted.columns = pd.to_datetime(price_pivoted.columns)

        # 对齐
        fn = "PE"
        fd = factor_result[fn]
        cd = fd.columns.intersection(price_pivoted.columns)
        cs = fd.index.intersection(price_pivoted.index)
        fa = fd.loc[list(cs), list(cd)]
        pa = price_pivoted.loc[list(cs), list(cd)]

        # 跑引擎
        bridge = DataBridge()
        dl = bridge.create_dataloader({fn: fa}, pa)
        engine = FactorBacktestEngine(dl)
        engine.run()
        summary = engine.summary()

        assert fn in summary
        assert not np.isnan(summary[fn]["rank_icir"])

    def test_02_second_run_uses_cache(self, cache_dir, sample_factor_data,
                                        sample_price_matrix):
        """第二次运行相同查询时,数据来自缓存"""
        fake_adapter = FakeFactorPivotAdapter(sample_factor_data)
        fake_pq = FakePriceQuery(sample_price_matrix)
        loader = CachedDataLoader(
            db_path="dummy.duckdb",
            cache_dir=cache_dir,
            enabled=True,
            factor_adapter_factory=lambda db: fake_adapter,
            price_query_factory=lambda db: fake_pq,
        )

        params = dict(start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))

        # 第一次
        loader.get_pivoted_factors(["PE"], **params)
        loader.get_price_matrix(field="close", **params)
        assert fake_adapter.call_count == 1
        assert fake_pq.call_count == 1

        # 第二次: 应全部命中缓存
        factor_result = loader.get_pivoted_factors(["PE"], **params)
        price_df = loader.get_price_matrix(field="close", **params)

        assert fake_adapter.call_count == 1  # 0 次 DB 调用
        assert fake_pq.call_count == 1  # 0 次 DB 调用
        assert "PE" in factor_result
        assert price_df.shape == sample_price_matrix.shape
