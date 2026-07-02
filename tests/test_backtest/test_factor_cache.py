# -*- coding: utf-8 -*-
"""
FactorMatrixCache 测试 — 因子矩阵 L2 缓存

设计:
  - 每个因子独立缓存（不同因子有不同日期范围/股票覆盖）
  - 支持部分命中：仅查询未缓存的因子
  - source_signature 包含 db_loaded_at_max
  - 返回 {factor_name: DataFrame(stock_code × trade_date)}
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

from factor_pipeline.backtest.factor_cache import FactorMatrixCache


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def cache_dir(tmp_path):
    d = tmp_path / "factor_cache"
    d.mkdir()
    return str(d)


@pytest.fixture
def sample_factor_data():
    """样本因子数据: {factor_name: DataFrame(stock_code × trade_date)}"""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    stocks = [f"00000{i}.SZ" for i in range(20)]
    return {
        "PE": pd.DataFrame(rng.normal(0, 1, (20, 30)), index=stocks, columns=dates),
        "PB": pd.DataFrame(rng.normal(0, 1, (20, 30)), index=stocks, columns=dates),
        "ROE": pd.DataFrame(rng.normal(0, 1, (20, 30)), index=stocks, columns=dates),
    }


class FakeFactorPivotAdapter:
    """模拟 FactorPivotAdapter，记录调用次数"""

    def __init__(self, factor_data: dict, loaded_at_max: str = "2026-06-30T23:59:00"):
        self._data = factor_data
        self._loaded_at_max = loaded_at_max
        self.call_count = 0
        self.queried_factors = []  # 记录每次查询了哪些因子

    def get_pivoted(self, factor_names, stock_codes=None, start_date=None, end_date=None):
        self.call_count += 1
        self.queried_factors.append(list(factor_names))
        return {fn: self._data[fn].copy() for fn in factor_names if fn in self._data}

    def get_loaded_at_max(self, factor_name=None):
        return self._loaded_at_max


# =============================================================================
# 1. 基本 cache miss → hit 流程
# =============================================================================

class TestBasicCacheFlow:

    def test_01_first_call_queries_all(self, cache_dir, sample_factor_data):
        """首次调用查询所有因子"""
        fake = FakeFactorPivotAdapter(sample_factor_data)
        cache = FactorMatrixCache(fake, cache_dir=cache_dir, enabled=True)

        result = cache.get_pivoted(["PE", "PB"], start_date=date(2024, 1, 1),
                                    end_date=date(2024, 1, 31))

        assert fake.call_count == 1
        assert set(result.keys()) == {"PE", "PB"}

    def test_02_second_call_all_hit(self, cache_dir, sample_factor_data):
        """第二次调用全部命中缓存"""
        fake = FakeFactorPivotAdapter(sample_factor_data)
        cache = FactorMatrixCache(fake, cache_dir=cache_dir, enabled=True)

        cache.get_pivoted(["PE", "PB"], start_date=date(2024, 1, 1),
                          end_date=date(2024, 1, 31))
        assert fake.call_count == 1

        result = cache.get_pivoted(["PE", "PB"], start_date=date(2024, 1, 1),
                                    end_date=date(2024, 1, 31))
        assert fake.call_count == 1  # 全部命中，未查 DB
        assert set(result.keys()) == {"PE", "PB"}

    def test_03_partial_hit_queries_only_missing(self, cache_dir, sample_factor_data):
        """部分命中：仅查询未缓存的因子"""
        fake = FakeFactorPivotAdapter(sample_factor_data)
        cache = FactorMatrixCache(fake, cache_dir=cache_dir, enabled=True)

        # 先缓存 PE
        cache.get_pivoted(["PE"], start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))
        assert fake.call_count == 1

        # 再请求 PE + PB，PE 命中，PB miss
        result = cache.get_pivoted(["PE", "PB"], start_date=date(2024, 1, 1),
                                    end_date=date(2024, 1, 31))
        assert fake.call_count == 2  # 只查询了 PB
        assert fake.queried_factors[-1] == ["PB"]  # 最后一次只查了 PB
        assert set(result.keys()) == {"PE", "PB"}


# =============================================================================
# 2. 值一致性
# =============================================================================

class TestValueConsistency:

    def test_01_cached_equals_direct(self, cache_dir, sample_factor_data):
        """缓存值与直接查询完全一致"""
        fake = FakeFactorPivotAdapter(sample_factor_data)
        cache = FactorMatrixCache(fake, cache_dir=cache_dir, enabled=True)

        direct = fake.get_pivoted(["PE", "PB"], start_date=date(2024, 1, 1),
                                   end_date=date(2024, 1, 31))
        fake.call_count = 0

        cached = cache.get_pivoted(["PE", "PB"], start_date=date(2024, 1, 1),
                                    end_date=date(2024, 1, 31))

        for fn in ["PE", "PB"]:
            pd.testing.assert_frame_equal(cached[fn], direct[fn], check_freq=False)

    def test_02_source_signature_per_factor(self, cache_dir, sample_factor_data):
        """每个因子有独立的 meta.json 包含 source_signature"""
        fake = FakeFactorPivotAdapter(sample_factor_data, loaded_at_max="2026-06-30T00:00:00")
        cache = FactorMatrixCache(fake, cache_dir=cache_dir, enabled=True)

        cache.get_pivoted(["PE", "PB"], start_date=date(2024, 1, 1),
                          end_date=date(2024, 1, 31))

        # 应有 2 个 meta.json（PE 和 PB 各一个）
        meta_files = list(Path(cache_dir).glob("*.meta.json"))
        assert len(meta_files) == 2

        import json
        for mf in meta_files:
            with open(mf, "r", encoding="utf-8") as f:
                meta = json.load(f)
            assert "db_loaded_at_max" in meta["source_signature"]
            assert meta["source_signature"]["db_loaded_at_max"] == "2026-06-30T00:00:00"
            assert meta["namespace"] == "factor_matrix"


# =============================================================================
# 3. 环境变量逃生舱
# =============================================================================

class TestEnvironmentEscape:

    def test_01_env_disabled_bypasses_cache(self, cache_dir, sample_factor_data):
        """FACTOR_PIPELINE_CACHE=disabled 时每次走 DB"""
        with mock.patch.dict(os.environ, {"FACTOR_PIPELINE_CACHE": "disabled"}):
            fake = FakeFactorPivotAdapter(sample_factor_data)
            cache = FactorMatrixCache(fake, cache_dir=cache_dir, enabled=True)

            cache.get_pivoted(["PE"], start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))
            cache.get_pivoted(["PE"], start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))

            assert fake.call_count == 2


# =============================================================================
# 4. 失效与刷新
# =============================================================================

class TestInvalidation:

    def test_01_invalidate_single_factor(self, cache_dir, sample_factor_data):
        """invalidate 单个因子"""
        fake = FakeFactorPivotAdapter(sample_factor_data)
        cache = FactorMatrixCache(fake, cache_dir=cache_dir, enabled=True)

        cache.get_pivoted(["PE", "PB"], start_date=date(2024, 1, 1),
                          end_date=date(2024, 1, 31))
        assert fake.call_count == 1

        # 失效 PE
        cache.invalidate("PE", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))

        # 再请求 PE + PB，PE miss，PB hit
        cache.get_pivoted(["PE", "PB"], start_date=date(2024, 1, 1),
                          end_date=date(2024, 1, 31))
        assert fake.call_count == 2  # 只重查了 PE
        assert fake.queried_factors[-1] == ["PE"]

    def test_02_clear_all(self, cache_dir, sample_factor_data):
        """clear_all 清空所有因子缓存"""
        fake = FakeFactorPivotAdapter(sample_factor_data)
        cache = FactorMatrixCache(fake, cache_dir=cache_dir, enabled=True)

        cache.get_pivoted(["PE", "PB", "ROE"], start_date=date(2024, 1, 1),
                          end_date=date(2024, 1, 31))
        assert len(list(Path(cache_dir).glob("*.parquet"))) == 3

        cache.clear_all()
        assert len(list(Path(cache_dir).glob("*"))) == 0


# =============================================================================
# 5. 边界情况
# =============================================================================

class TestEdgeCases:

    def test_01_disabled_always_queries(self, cache_dir, sample_factor_data):
        """enabled=False 时每次走 DB"""
        fake = FakeFactorPivotAdapter(sample_factor_data)
        cache = FactorMatrixCache(fake, cache_dir=cache_dir, enabled=False)

        cache.get_pivoted(["PE"], start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))
        cache.get_pivoted(["PE"], start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))

        assert fake.call_count == 2

    def test_02_empty_factor_list(self, cache_dir, sample_factor_data):
        """空因子列表返回空字典"""
        fake = FakeFactorPivotAdapter(sample_factor_data)
        cache = FactorMatrixCache(fake, cache_dir=cache_dir, enabled=True)

        result = cache.get_pivoted([], start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))
        assert result == {}
        assert fake.call_count == 0  # 未查询

    def test_03_different_date_ranges_separate(self, cache_dir, sample_factor_data):
        """不同日期范围产生独立缓存"""
        fake = FakeFactorPivotAdapter(sample_factor_data)
        cache = FactorMatrixCache(fake, cache_dir=cache_dir, enabled=True)

        cache.get_pivoted(["PE"], start_date=date(2024, 1, 1), end_date=date(2024, 1, 15))
        cache.get_pivoted(["PE"], start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))

        assert fake.call_count == 2  # 不同日期范围

        # 相同日期范围应命中
        cache.get_pivoted(["PE"], start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))
        assert fake.call_count == 2

    def test_04_factor_not_in_db_returns_empty(self, cache_dir, sample_factor_data):
        """查询不存在的因子不缓存，返回空 DataFrame"""
        fake = FakeFactorPivotAdapter({})  # 空数据库
        cache = FactorMatrixCache(fake, cache_dir=cache_dir, enabled=True)

        result = cache.get_pivoted(["NONEXISTENT"], start_date=date(2024, 1, 1),
                                    end_date=date(2024, 1, 31))
        # 不应崩溃，可能返回空 dict 或 {NONEXISTENT: empty DataFrame}
        assert "NONEXISTENT" not in result or result["NONEXISTENT"].empty
