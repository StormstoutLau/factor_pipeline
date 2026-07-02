# -*- coding: utf-8 -*-
"""
FwdReturnsCache 测试 — 前向收益 ndarray 缓存

验证:
  1. 首次调用执行 compute_fn 并缓存
  2. 第二次调用命中缓存,不执行 compute_fn
  3. 不同参数 (日期/股票) 独立缓存
  4. 环境变量逃生舱
  5. clear_all / invalidate
  6. ndarray 值完全一致
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from factor_pipeline.backtest.fwd_returns_cache import FwdReturnsCache


@pytest.fixture
def cache_dir(tmp_path):
    d = tmp_path / "fwd_cache"
    d.mkdir()
    return str(d)


@pytest.fixture
def sample_fwd_returns():
    """样本前向收益: shape (n_dates-1, n_stocks)"""
    rng = np.random.default_rng(42)
    return rng.normal(0.001, 0.02, (59, 100))


class TestBasicCacheFlow:

    def test_01_first_call_executes_compute(self, cache_dir, sample_fwd_returns):
        """首次调用执行 compute_fn"""
        call_count = [0]

        def compute_fn():
            call_count[0] += 1
            return sample_fwd_returns

        cache = FwdReturnsCache(cache_dir=cache_dir, enabled=True)
        result = cache.get_or_compute(
            stock_codes="hash123",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
            field="close",
            adjust="none",
            compute_fn=compute_fn,
        )

        assert call_count[0] == 1
        np.testing.assert_array_equal(result, sample_fwd_returns)

    def test_02_second_call_hits_cache(self, cache_dir, sample_fwd_returns):
        """第二次调用命中缓存,不执行 compute_fn"""
        call_count = [0]

        def compute_fn():
            call_count[0] += 1
            return sample_fwd_returns

        cache = FwdReturnsCache(cache_dir=cache_dir, enabled=True)
        cache.get_or_compute(
            stock_codes="hash123", start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31), field="close", adjust="none",
            compute_fn=compute_fn,
        )
        cache.get_or_compute(
            stock_codes="hash123", start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31), field="close", adjust="none",
            compute_fn=compute_fn,
        )

        assert call_count[0] == 1  # 全部命中

    def test_03_cached_equals_direct(self, cache_dir, sample_fwd_returns):
        """缓存值与直接计算值完全一致"""
        cache = FwdReturnsCache(cache_dir=cache_dir, enabled=True)

        # 第一次: 计算 + 缓存
        direct = cache.get_or_compute(
            stock_codes="h", start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31), field="close", adjust="none",
            compute_fn=lambda: sample_fwd_returns,
        )
        # 第二次: 从缓存读
        cached = cache.get_or_compute(
            stock_codes="h", start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31), field="close", adjust="none",
            compute_fn=lambda: np.zeros_like(sample_fwd_returns),  # 不会执行
        )

        np.testing.assert_array_equal(cached, direct)


class TestDifferentParams:

    def test_01_different_dates_independent(self, cache_dir, sample_fwd_returns):
        """不同日期范围产生独立缓存"""
        call_count = [0]

        def compute_fn():
            call_count[0] += 1
            return sample_fwd_returns

        cache = FwdReturnsCache(cache_dir=cache_dir, enabled=True)
        cache.get_or_compute(
            stock_codes="h", start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31), field="close", adjust="none",
            compute_fn=compute_fn,
        )
        cache.get_or_compute(
            stock_codes="h", start_date=date(2024, 4, 1),  # 不同日期
            end_date=date(2024, 6, 30), field="close", adjust="none",
            compute_fn=compute_fn,
        )

        assert call_count[0] == 2  # 两次都 miss

    def test_02_different_stocks_independent(self, cache_dir, sample_fwd_returns):
        """不同股票集合产生独立缓存"""
        call_count = [0]

        def compute_fn():
            call_count[0] += 1
            return sample_fwd_returns

        cache = FwdReturnsCache(cache_dir=cache_dir, enabled=True)
        cache.get_or_compute(
            stock_codes="hash_A", start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31), field="close", adjust="none",
            compute_fn=compute_fn,
        )
        cache.get_or_compute(
            stock_codes="hash_B",  # 不同股票
            start_date=date(2024, 1, 1), end_date=date(2024, 3, 31),
            field="close", adjust="none", compute_fn=compute_fn,
        )

        assert call_count[0] == 2


class TestEnvironmentEscape:

    def test_01_env_disabled_bypasses_cache(self, cache_dir, sample_fwd_returns):
        """FACTOR_PIPELINE_CACHE=disabled 时全走 compute_fn"""
        call_count = [0]

        def compute_fn():
            call_count[0] += 1
            return sample_fwd_returns

        with mock.patch.dict(os.environ, {"FACTOR_PIPELINE_CACHE": "disabled"}):
            cache = FwdReturnsCache(cache_dir=cache_dir, enabled=True)
            cache.get_or_compute(
                stock_codes="h", start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 31), field="close", adjust="none",
                compute_fn=compute_fn,
            )
            cache.get_or_compute(
                stock_codes="h", start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 31), field="close", adjust="none",
                compute_fn=compute_fn,
            )

            assert call_count[0] == 2  # 全走 compute


class TestInvalidation:

    def test_01_invalidate(self, cache_dir, sample_fwd_returns):
        """invalidate 后重新计算"""
        call_count = [0]

        def compute_fn():
            call_count[0] += 1
            return sample_fwd_returns

        cache = FwdReturnsCache(cache_dir=cache_dir, enabled=True)
        cache.get_or_compute(
            stock_codes="h", start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31), field="close", adjust="none",
            compute_fn=compute_fn,
        )
        assert call_count[0] == 1

        cache.invalidate(
            stock_codes="h", start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31), field="close", adjust="none",
        )

        cache.get_or_compute(
            stock_codes="h", start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31), field="close", adjust="none",
            compute_fn=compute_fn,
        )
        assert call_count[0] == 2  # 失效后重查

    def test_02_clear_all(self, cache_dir, sample_fwd_returns):
        """clear_all 清空所有"""
        cache = FwdReturnsCache(cache_dir=cache_dir, enabled=True)
        cache.get_or_compute(
            stock_codes="h", start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31), field="close", adjust="none",
            compute_fn=lambda: sample_fwd_returns,
        )

        files_before = len(list(Path(cache_dir).glob("*.npy")))
        assert files_before >= 1

        cache.clear_all()

        files_after = len(list(Path(cache_dir).glob("*.npy")))
        assert files_after == 0


class TestEdgeCases:

    def test_01_empty_ndarray_not_cached(self, cache_dir):
        """空 ndarray 不缓存"""
        call_count = [0]

        def compute_fn():
            call_count[0] += 1
            return np.array([])

        cache = FwdReturnsCache(cache_dir=cache_dir, enabled=True)
        cache.get_or_compute(
            stock_codes="h", start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31), field="close", adjust="none",
            compute_fn=compute_fn,
        )

        files = list(Path(cache_dir).glob("*.npy"))
        assert len(files) == 0  # 空数组不缓存

    def test_02_nan_values_cached_correctly(self, cache_dir):
        """含 NaN 的 ndarray 正确缓存和恢复"""
        rng = np.random.default_rng(42)
        fwd = rng.normal(0, 1, (50, 80))
        fwd[0, 0] = np.nan
        fwd[10, 5] = np.nan

        cache = FwdReturnsCache(cache_dir=cache_dir, enabled=True)
        cache.get_or_compute(
            stock_codes="h", start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31), field="close", adjust="none",
            compute_fn=lambda: fwd,
        )

        cached = cache.get_or_compute(
            stock_codes="h", start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31), field="close", adjust="none",
            compute_fn=lambda: np.zeros_like(fwd),  # 不会执行
        )

        np.testing.assert_array_equal(cached, fwd)
        assert np.isnan(cached[0, 0])
        assert np.isnan(cached[10, 5])
