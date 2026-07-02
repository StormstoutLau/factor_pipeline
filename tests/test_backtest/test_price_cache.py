# -*- coding: utf-8 -*-
"""
PriceMatrixCache 测试 — 价格矩阵 L2 缓存

设计:
  - 首次调用: 走 PriceQuery.get_price_matrix(),存入缓存
  - 再次调用: 命中缓存,跳过 DB 查询
  - source_signature 包含 db_loaded_at_max,用于 staleness 检查
  - 环境变量逃生舱
  - 值与直接查询完全一致
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from factor_pipeline.backtest.cache_manager import CacheManager, CacheKey
from factor_pipeline.backtest.price_cache import PriceMatrixCache


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def cache_dir(tmp_path):
    d = tmp_path / "price_cache"
    d.mkdir()
    return str(d)


@pytest.fixture
def sample_price_matrix():
    """样本价格矩阵 (dates × stocks) — PriceQuery.get_price_matrix 的返回格式"""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    stocks = [f"00000{i}.SZ" for i in range(20)]
    base = 10.0 + rng.normal(0, 0.5, (30, 20)).cumsum(axis=0) * 0.1
    return pd.DataFrame(base, index=dates, columns=stocks)


class FakePriceQuery:
    """模拟 PriceQuery,记录调用次数和参数"""

    def __init__(self, matrix: pd.DataFrame, loaded_at_max: str = "2026-06-30T23:59:00"):
        self._matrix = matrix
        self._loaded_at_max = loaded_at_max
        self.call_count = 0
        self.last_args = None

    def get_price_matrix(self, field="close", stock_codes=None, start_date=None,
                         end_date=None, adjust="none", as_of=None):
        self.call_count += 1
        self.last_args = {
            "field": field, "stock_codes": stock_codes,
            "start_date": start_date, "end_date": end_date,
            "adjust": adjust, "as_of": as_of,
        }
        return self._matrix.copy()

    def get_loaded_at_max(self, table_name="daily_prices"):
        """模拟获取 MAX(loaded_at)"""
        return self._loaded_at_max


# =============================================================================
# 1. 基本 cache miss → hit 流程
# =============================================================================

class TestBasicCacheFlow:

    def test_01_first_call_misses_cache(self, cache_dir, sample_price_matrix):
        """首次调用应走 PriceQuery"""
        fake_pq = FakePriceQuery(sample_price_matrix)
        cache = PriceMatrixCache(fake_pq, cache_dir=cache_dir, enabled=True)

        result = cache.get_price_matrix(
            field="close", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31),
        )

        assert fake_pq.call_count == 1  # 走了 DB
        pd.testing.assert_frame_equal(result, sample_price_matrix)

    def test_02_second_call_hits_cache(self, cache_dir, sample_price_matrix):
        """第二次调用应命中缓存,不查 DB"""
        fake_pq = FakePriceQuery(sample_price_matrix)
        cache = PriceMatrixCache(fake_pq, cache_dir=cache_dir, enabled=True)

        # 第一次: miss
        cache.get_price_matrix(field="close", start_date=date(2024, 1, 1),
                               end_date=date(2024, 1, 31))
        assert fake_pq.call_count == 1

        # 第二次: hit
        result = cache.get_price_matrix(field="close", start_date=date(2024, 1, 1),
                                        end_date=date(2024, 1, 31))
        assert fake_pq.call_count == 1  # 仍为 1,未查 DB
        pd.testing.assert_frame_equal(result, sample_price_matrix)

    def test_03_different_params_separate_cache(self, cache_dir, sample_price_matrix):
        """不同参数产生独立缓存"""
        fake_pq = FakePriceQuery(sample_price_matrix)
        cache = PriceMatrixCache(fake_pq, cache_dir=cache_dir, enabled=True)

        cache.get_price_matrix(field="close", start_date=date(2024, 1, 1),
                               end_date=date(2024, 1, 31))
        cache.get_price_matrix(field="open", start_date=date(2024, 1, 1),
                               end_date=date(2024, 1, 31))

        assert fake_pq.call_count == 2  # 两个不同的查询

        # 再次调用相同参数,都应命中缓存
        cache.get_price_matrix(field="close", start_date=date(2024, 1, 1),
                               end_date=date(2024, 1, 31))
        cache.get_price_matrix(field="open", start_date=date(2024, 1, 1),
                               end_date=date(2024, 1, 31))
        assert fake_pq.call_count == 2  # 未增加


# =============================================================================
# 2. 值一致性
# =============================================================================

class TestValueConsistency:

    def test_01_cached_equals_direct(self, cache_dir, sample_price_matrix):
        """缓存返回值与直接查询完全一致"""
        fake_pq = FakePriceQuery(sample_price_matrix)
        cache = PriceMatrixCache(fake_pq, cache_dir=cache_dir, enabled=True)

        direct = fake_pq.get_price_matrix(field="close")
        fake_pq.call_count = 0  # 重置计数

        cached = cache.get_price_matrix(field="close")

        pd.testing.assert_frame_equal(cached, direct)
        assert fake_pq.call_count == 1  # 第一次 miss

        # 第二次从缓存读
        cached2 = cache.get_price_matrix(field="close")
        pd.testing.assert_frame_equal(cached2, direct)
        assert fake_pq.call_count == 1  # 命中缓存

    def test_02_data_fingerprint_stored(self, cache_dir, sample_price_matrix):
        """缓存 meta 应包含数据指纹"""
        fake_pq = FakePriceQuery(sample_price_matrix)
        cache = PriceMatrixCache(fake_pq, cache_dir=cache_dir, enabled=True)

        cache.get_price_matrix(field="close", start_date=date(2024, 1, 1),
                               end_date=date(2024, 1, 31))

        # 检查 meta.json
        meta_files = list(Path(cache_dir).glob("*.meta.json"))
        assert len(meta_files) == 1
        import json
        with open(meta_files[0], "r", encoding="utf-8") as f:
            meta = json.load(f)
        assert "data_fingerprint" in meta
        assert meta["data_fingerprint"]["shape"] == [30, 20]

    def test_03_source_signature_includes_loaded_at(self, cache_dir, sample_price_matrix):
        """source_signature 应包含 db_loaded_at_max"""
        fake_pq = FakePriceQuery(sample_price_matrix, loaded_at_max="2026-06-30T23:59:00")
        cache = PriceMatrixCache(fake_pq, cache_dir=cache_dir, enabled=True)

        cache.get_price_matrix(field="close")

        meta_files = list(Path(cache_dir).glob("*.meta.json"))
        import json
        with open(meta_files[0], "r", encoding="utf-8") as f:
            meta = json.load(f)
        assert "db_loaded_at_max" in meta["source_signature"]
        assert meta["source_signature"]["db_loaded_at_max"] == "2026-06-30T23:59:00"


# =============================================================================
# 3. 环境变量逃生舱
# =============================================================================

class TestEnvironmentEscape:

    def test_01_env_disabled_bypasses_cache(self, cache_dir, sample_price_matrix):
        """FACTOR_PIPELINE_CACHE=disabled 时每次都走 DB"""
        with mock.patch.dict(os.environ, {"FACTOR_PIPELINE_CACHE": "disabled"}):
            fake_pq = FakePriceQuery(sample_price_matrix)
            cache = PriceMatrixCache(fake_pq, cache_dir=cache_dir, enabled=True)

            cache.get_price_matrix(field="close")
            cache.get_price_matrix(field="close")

            assert fake_pq.call_count == 2  # 每次都走 DB


# =============================================================================
# 4. 失效与刷新
# =============================================================================

class TestInvalidation:

    def test_01_invalidate_forces_refetch(self, cache_dir, sample_price_matrix):
        """invalidate 后下次调用重新查询"""
        fake_pq = FakePriceQuery(sample_price_matrix)
        cache = PriceMatrixCache(fake_pq, cache_dir=cache_dir, enabled=True)

        cache.get_price_matrix(field="close")
        assert fake_pq.call_count == 1

        cache.invalidate(field="close", start_date=None, end_date=None)

        cache.get_price_matrix(field="close")
        assert fake_pq.call_count == 2  # 重新查询

    def test_02_clear_all(self, cache_dir, sample_price_matrix):
        """clear_all 清空所有价格缓存"""
        fake_pq = FakePriceQuery(sample_price_matrix)
        cache = PriceMatrixCache(fake_pq, cache_dir=cache_dir, enabled=True)

        cache.get_price_matrix(field="close")
        cache.get_price_matrix(field="open")
        assert len(list(Path(cache_dir).glob("*.parquet"))) == 2

        cache.clear_all()
        assert len(list(Path(cache_dir).glob("*"))) == 0

        # 重新查询应 miss
        cache.get_price_matrix(field="close")
        assert fake_pq.call_count == 3  # close(1) + open(1) + close重新(1)


# =============================================================================
# 5. 边界情况
# =============================================================================

class TestEdgeCases:

    def test_01_disabled_cache_always_queries(self, cache_dir, sample_price_matrix):
        """enabled=False 时每次走 DB"""
        fake_pq = FakePriceQuery(sample_price_matrix)
        cache = PriceMatrixCache(fake_pq, cache_dir=cache_dir, enabled=False)

        cache.get_price_matrix(field="close")
        cache.get_price_matrix(field="close")

        assert fake_pq.call_count == 2

    def test_02_empty_result_not_cached(self, cache_dir):
        """空结果不缓存"""
        empty_df = pd.DataFrame()
        fake_pq = FakePriceQuery(empty_df)
        cache = PriceMatrixCache(fake_pq, cache_dir=cache_dir, enabled=True)

        cache.get_price_matrix(field="close")
        cache.get_price_matrix(field="close")

        assert fake_pq.call_count == 2  # 空结果不缓存,每次都查
        assert len(list(Path(cache_dir).glob("*"))) == 0

    def test_03_stock_codes_filter_cached_separately(self, cache_dir, sample_price_matrix):
        """不同 stock_codes 产生独立缓存"""
        fake_pq = FakePriceQuery(sample_price_matrix)
        cache = PriceMatrixCache(fake_pq, cache_dir=cache_dir, enabled=True)

        stocks_a = ["000001.SZ", "000002.SZ"]
        stocks_b = ["000003.SZ", "000004.SZ"]

        cache.get_price_matrix(field="close", stock_codes=stocks_a)
        cache.get_price_matrix(field="close", stock_codes=stocks_b)

        assert fake_pq.call_count == 2

        # 相同参数应命中
        cache.get_price_matrix(field="close", stock_codes=stocks_a)
        assert fake_pq.call_count == 2
