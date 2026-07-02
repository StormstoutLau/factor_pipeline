# -*- coding: utf-8 -*-
"""
CacheManager 核心测试 — L2 磁盘缓存骨架

设计原则（优先级）:
  P0 可调试性 > P1 正确性 > P2 性能

测试覆盖:
  1. 基本 set/get 流程
  2. .meta.json 透明度（完整字段可读回）
  3. 环境变量逃生舱（FACTOR_PIPELINE_CACHE=disabled）
  4. 数据指纹校验（head/tail hash + nan_ratio）
  5. 失效策略（显式 invalidate / stale 检测）
  6. verify 一致性检查
  7. status 可观测性
  8. 日志透明度
  9. parquet 元数据保真（freq 丢失防御）
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

# 模块可能尚不存在,Red Phase 预期 ImportError
from factor_pipeline.backtest.cache_manager import (
    CacheManager,
    CacheKey,
    CacheMeta,
    CacheStatus,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def cache_dir(tmp_path):
    """独立缓存目录,测试结束自动清理"""
    d = tmp_path / "cache"
    d.mkdir()
    return str(d)


@pytest.fixture
def manager(cache_dir):
    """默认启用的 CacheManager"""
    return CacheManager(cache_dir=cache_dir, enabled=True)


@pytest.fixture
def sample_df():
    """样本 DataFrame (n_stocks × n_dates)"""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    stocks = [f"00000{i}.SZ" for i in range(10)]
    return pd.DataFrame(
        rng.normal(0, 1, (10, 20)),
        index=stocks,
        columns=dates,
    )


@pytest.fixture
def sample_array():
    """样本 numpy 数组 (前向收益)"""
    rng = np.random.default_rng(7)
    return rng.normal(0.001, 0.02, (19, 10))


# =============================================================================
# 1. 基本流程
# =============================================================================

class TestCacheManagerBasic:
    """CacheManager 基本创建与 set/get"""

    def test_01_create_manager(self, cache_dir):
        """能够创建 CacheManager 实例"""
        m = CacheManager(cache_dir=cache_dir, enabled=True)
        assert m.cache_dir == cache_dir
        assert m.enabled is True

    def test_02_set_then_get_dataframe(self, manager, sample_df):
        """set DataFrame 后 get 应返回相同数据"""
        key = CacheKey(
            namespace="price_matrix",
            identifier="close_2024_01",
            version="v1",
        )
        manager.set(key, sample_df)
        result = manager.get(key)
        assert result is not None
        pd.testing.assert_frame_equal(result, sample_df, check_freq=False)

    def test_03_get_miss_returns_none(self, manager):
        """未缓存的 key 应返回 None"""
        key = CacheKey(
            namespace="price_matrix",
            identifier="nonexistent",
            version="v1",
        )
        assert manager.get(key) is None

    def test_04_set_then_get_ndarray(self, manager, sample_array):
        """支持 numpy 数组缓存"""
        key = CacheKey(
            namespace="fwd_returns",
            identifier="group_A",
            version="v1",
        )
        manager.set(key, sample_array)
        result = manager.get(key)
        assert result is not None
        np.testing.assert_array_almost_equal(result, sample_array)

    def test_05_cache_key_uniqueness(self, manager, sample_df):
        """不同 identifier 产生不同缓存"""
        k1 = CacheKey("price", "close", "v1")
        k2 = CacheKey("price", "open", "v1")
        manager.set(k1, sample_df)
        df2 = sample_df * 2
        manager.set(k2, df2)
        r1 = manager.get(k1)
        r2 = manager.get(k2)
        pd.testing.assert_frame_equal(r1, sample_df, check_freq=False)
        pd.testing.assert_frame_equal(r2, df2, check_freq=False)


# =============================================================================
# 2. .meta.json 透明度
# =============================================================================

class TestMetaJsonTransparency:
    """每个缓存文件旁附 .meta.json,记录完整来源信息"""

    def test_01_meta_file_exists(self, manager, sample_df, cache_dir):
        """set 后应生成 .meta.json 文件"""
        key = CacheKey("price", "close", "v1")
        manager.set(key, sample_df)

        cache_files = list(Path(cache_dir).glob("*.parquet"))
        assert len(cache_files) == 1
        meta_files = list(Path(cache_dir).glob("*.meta.json"))
        assert len(meta_files) == 1

    def test_02_meta_contains_required_fields(self, manager, sample_df, cache_dir):
        """meta.json 必须包含设计要求的所有字段"""
        key = CacheKey(
            namespace="price_matrix",
            identifier="close_2024",
            version="v2.2.0",
        )
        source_sig = {
            "sql": "SELECT close FROM daily_prices WHERE ...",
            "params": {"start": "2024-01-01", "end": "2024-12-31"},
            "db_loaded_at_max": "2026-06-30T23:59:00",
            "row_count": 10,
            "col_count": 20,
        }
        manager.set(key, sample_df, source_signature=source_sig)

        meta_files = list(Path(cache_dir).glob("*.meta.json"))
        with open(meta_files[0], "r", encoding="utf-8") as f:
            meta = json.load(f)

        # 必须包含的字段
        required = {
            "cache_key", "created_at", "source_signature",
            "data_fingerprint", "code_version", "namespace", "identifier",
        }
        assert required.issubset(meta.keys()), f"缺少字段: {required - meta.keys()}"
        assert meta["namespace"] == "price_matrix"
        assert meta["identifier"] == "close_2024"
        assert meta["source_signature"]["db_loaded_at_max"] == "2026-06-30T23:59:00"

    def test_03_meta_data_fingerprint(self, manager, sample_df, cache_dir):
        """meta.json 中的 data_fingerprint 必须包含 head/tail hash"""
        key = CacheKey("price", "close", "v1")
        manager.set(key, sample_df)

        meta_files = list(Path(cache_dir).glob("*.meta.json"))
        with open(meta_files[0], "r", encoding="utf-8") as f:
            meta = json.load(f)

        fp = meta["data_fingerprint"]
        assert "head_hash" in fp
        assert "tail_hash" in fp
        assert "nan_ratio" in fp
        assert "shape" in fp
        assert fp["shape"] == [10, 20]

    def test_04_meta_roundtrip_after_reread(self, manager, sample_df):
        """get 命中时应能读回 meta 信息"""
        key = CacheKey("price", "close", "v1")
        manager.set(key, sample_df)

        result, meta = manager.get_with_meta(key)
        assert result is not None
        assert isinstance(meta, CacheMeta)
        assert meta.namespace == "price"
        assert meta.identifier == "close"


# =============================================================================
# 3. 环境变量逃生舱
# =============================================================================

class TestEnvironmentEscape:
    """FACTOR_PIPELINE_CACHE=disabled 全局禁用,最高优先级"""

    def test_01_env_disabled_prevents_set_get(self, cache_dir, sample_df):
        """环境变量 disabled 时,set/get 均不生效"""
        with mock.patch.dict(os.environ, {"FACTOR_PIPELINE_CACHE": "disabled"}):
            m = CacheManager(cache_dir=cache_dir, enabled=True)
            key = CacheKey("price", "close", "v1")
            m.set(key, sample_df)
            # set 应被忽略
            assert m.get(key) is None
            # 不应生成任何文件
            assert len(list(Path(cache_dir).glob("*"))) == 0

    def test_02_env_enabled_allows_cache(self, cache_dir, sample_df):
        """环境变量 enabled 时正常工作"""
        with mock.patch.dict(os.environ, {"FACTOR_PIPELINE_CACHE": "enabled"}):
            m = CacheManager(cache_dir=cache_dir, enabled=True)
            key = CacheKey("price", "close", "v1")
            m.set(key, sample_df)
            assert m.get(key) is not None

    def test_03_env_unset_falls_back_to_init_flag(self, cache_dir, sample_df):
        """环境变量未设置时,fallback 到 enabled 参数"""
        # 确保环境变量不存在
        env = {k: v for k, v in os.environ.items() if k != "FACTOR_PIPELINE_CACHE"}
        with mock.patch.dict(os.environ, env, clear=True):
            m = CacheManager(cache_dir=cache_dir, enabled=False)
            key = CacheKey("price", "close", "v1")
            m.set(key, sample_df)
            assert m.get(key) is None

            m2 = CacheManager(cache_dir=cache_dir, enabled=True)
            m2.set(key, sample_df)
            assert m2.get(key) is not None


# =============================================================================
# 4. 数据指纹校验
# =============================================================================

class TestDataFingerprint:
    """数据指纹:head/tail hash + nan_ratio,防止数据被篡改"""

    def test_01_fingerprint_stable_for_same_data(self, manager, sample_df):
        """相同数据应产生相同指纹"""
        key = CacheKey("price", "close", "v1")
        manager.set(key, sample_df)
        _, meta1 = manager.get_with_meta(key)

        # 清空后重新 set 相同数据
        manager.invalidate(key)
        manager.set(key, sample_df)
        _, meta2 = manager.get_with_meta(key)

        assert meta1.data_fingerprint == meta2.data_fingerprint

    def test_02_fingerprint_differs_for_different_data(self, manager, sample_df):
        """不同数据应产生不同指纹"""
        key = CacheKey("price", "close", "v1")
        manager.set(key, sample_df)
        _, meta1 = manager.get_with_meta(key)

        manager.invalidate(key)
        df2 = sample_df * 10
        manager.set(key, df2)
        _, meta2 = manager.get_with_meta(key)

        assert meta1.data_fingerprint != meta2.data_fingerprint

    def test_03_corrupted_cache_file_returns_none(self, manager, sample_df, cache_dir):
        """缓存文件被篡改时,get 应返回 None 而非错误数据"""
        key = CacheKey("price", "close", "v1")
        manager.set(key, sample_df)

        # 篡改 parquet 文件
        parquet_files = list(Path(cache_dir).glob("*.parquet"))
        with open(parquet_files[0], "ab") as f:
            f.write(b"CORRUPTED_BYTES")

        # get 应该检测到损坏并返回 None
        result = manager.get(key)
        assert result is None


# =============================================================================
# 5. 失效策略
# =============================================================================

class TestInvalidate:
    """显式 invalidate + clear_all"""

    def test_01_invalidate_single_key(self, manager, sample_df):
        """invalidate 单个 key"""
        key = CacheKey("price", "close", "v1")
        manager.set(key, sample_df)
        assert manager.get(key) is not None

        manager.invalidate(key)
        assert manager.get(key) is None

    def test_02_invalidate_removes_both_files(self, manager, sample_df, cache_dir):
        """invalidate 应同时删除 parquet 和 meta.json"""
        key = CacheKey("price", "close", "v1")
        manager.set(key, sample_df)
        assert len(list(Path(cache_dir).glob("*"))) == 2  # parquet + meta

        manager.invalidate(key)
        assert len(list(Path(cache_dir).glob("*"))) == 0

    def test_03_clear_all(self, manager, sample_df, cache_dir):
        """clear_all 清空所有缓存"""
        for i in range(3):
            manager.set(CacheKey("price", f"close_{i}", "v1"), sample_df)
        assert len(list(Path(cache_dir).glob("*.parquet"))) == 3

        manager.clear_all()
        assert len(list(Path(cache_dir).glob("*"))) == 0

    def test_04_invalidate_nonexistent_key_no_error(self, manager):
        """invalidate 不存在的 key 不应报错"""
        key = CacheKey("price", "nonexistent", "v1")
        manager.invalidate(key)  # 不应抛异常


# =============================================================================
# 6. verify 一致性检查
# =============================================================================

class TestVerify:
    """verify: 检查缓存文件与 meta 是否一致"""

    def test_01_verify_valid_cache(self, manager, sample_df):
        """有效缓存的 verify 应返回 OK"""
        key = CacheKey("price", "close", "v1")
        manager.set(key, sample_df)

        status = manager.verify(key)
        assert status.is_valid is True
        assert status.reason == "OK"

    def test_02_verify_missing_meta(self, manager, sample_df, cache_dir):
        """meta.json 缺失时 verify 应报告 invalid"""
        key = CacheKey("price", "close", "v1")
        manager.set(key, sample_df)

        # 删除 meta.json
        meta_files = list(Path(cache_dir).glob("*.meta.json"))
        meta_files[0].unlink()

        status = manager.verify(key)
        assert status.is_valid is False
        assert "meta" in status.reason.lower()

    def test_03_verify_corrupted_data(self, manager, sample_df, cache_dir):
        """数据被篡改时 verify 应报告 fingerprint mismatch"""
        key = CacheKey("price", "close", "v1")
        manager.set(key, sample_df)

        # 覆盖 parquet 为不同数据
        parquet_files = list(Path(cache_dir).glob("*.parquet"))
        df2 = sample_df * 100
        df2.to_parquet(parquet_files[0])

        status = manager.verify(key)
        assert status.is_valid is False
        assert "fingerprint" in status.reason.lower() or "mismatch" in status.reason.lower()


# =============================================================================
# 7. status 可观测性
# =============================================================================

class TestStatus:
    """status: 返回缓存统计信息"""

    def test_01_empty_status(self, manager):
        """空缓存的 status"""
        s = manager.status()
        assert s["total_entries"] == 0
        assert s["total_size_bytes"] == 0
        assert s["entries"] == []

    def test_02_status_after_set(self, manager, sample_df):
        """set 后 status 应显示条目"""
        key = CacheKey("price", "close", "v1")
        manager.set(key, sample_df)

        s = manager.status()
        assert s["total_entries"] == 1
        assert len(s["entries"]) == 1
        entry = s["entries"][0]
        assert entry["namespace"] == "price"
        assert entry["identifier"] == "close"
        assert entry["size_bytes"] > 0
        assert "created_at" in entry

    def test_03_status_multiple_entries(self, manager, sample_df):
        """多个条目的 status"""
        for i in range(3):
            manager.set(CacheKey("price", f"c{i}", "v1"), sample_df)
        s = manager.status()
        assert s["total_entries"] == 3
        assert len(s["entries"]) == 3


# =============================================================================
# 8. 日志透明度
# =============================================================================

class TestLogging:
    """每次缓存操作应记录透明日志"""

    def test_01_log_hit(self, manager, sample_df, caplog):
        """HIT 日志"""
        key = CacheKey("price", "close", "v1")
        manager.set(key, sample_df)

        with caplog.at_level(logging.INFO, logger="factor_pipeline.backtest.cache_manager"):
            manager.get(key)

        hit_logs = [r for r in caplog.records if "HIT" in r.message]
        assert len(hit_logs) >= 1
        log_msg = hit_logs[0].message
        assert "price" in log_msg or "close" in log_msg

    def test_02_log_miss(self, manager, caplog):
        """MISS 日志"""
        key = CacheKey("price", "nonexistent", "v1")

        with caplog.at_level(logging.INFO, logger="factor_pipeline.backtest.cache_manager"):
            manager.get(key)

        miss_logs = [r for r in caplog.records if "MISS" in r.message]
        assert len(miss_logs) >= 1

    def test_03_log_invalidate(self, manager, sample_df, caplog):
        """invalidate 日志"""
        key = CacheKey("price", "close", "v1")
        manager.set(key, sample_df)

        with caplog.at_level(logging.INFO, logger="factor_pipeline.backtest.cache_manager"):
            manager.invalidate(key)

        inv_logs = [r for r in caplog.records if "INVALIDATE" in r.message]
        assert len(inv_logs) >= 1


# =============================================================================
# 9. parquet 元数据保真
# =============================================================================

class TestParquetFidelity:
    """parquet 不保留 DatetimeIndex.freq,需防御"""

    def test_01_freq_preserved_via_meta(self, manager, sample_df):
        """freq 通过 meta 恢复"""
        assert sample_df.columns.freq == "B"  # Business day

        key = CacheKey("price", "close", "v1")
        manager.set(key, sample_df, index_freq="B")

        result = manager.get(key)
        assert result is not None
        # freq 应通过 meta 恢复
        assert result.columns.freq == "B"

    def test_02_no_freq_stored_remains_none(self, manager):
        """原始数据无 freq 时,get 后 freq 为 None(不伪造)"""
        # 构造无 freq 的 DataFrame
        rng = np.random.default_rng(99)
        dates = pd.DatetimeIndex(["2024-01-01", "2024-01-02", "2024-01-03"])
        stocks = ["000001.SZ", "000002.SZ"]
        df_no_freq = pd.DataFrame(rng.normal(0, 1, (2, 3)), index=stocks, columns=dates)
        assert df_no_freq.columns.freq is None  # 确认无 freq

        key = CacheKey("price", "close", "v1")
        manager.set(key, df_no_freq)  # 数据无 freq，未显式传入

        result = manager.get(key)
        assert result is not None
        assert result.columns.freq is None  # 诚实记录，不伪造


# =============================================================================
# 10. 边界情况
# =============================================================================

class TestEdgeCases:
    """边界情况"""

    def test_01_empty_dataframe(self, manager):
        """空 DataFrame 不应崩溃"""
        key = CacheKey("price", "empty", "v1")
        empty_df = pd.DataFrame()
        manager.set(key, empty_df)
        # 空 DataFrame 可能选择不缓存,或缓存但 get 返回空
        # 关键: 不应抛异常

    def test_02_disabled_manager_no_op(self, cache_dir, sample_df):
        """enabled=False 时所有操作都是 no-op"""
        m = CacheManager(cache_dir=cache_dir, enabled=False)
        key = CacheKey("price", "close", "v1")
        m.set(key, sample_df)
        assert m.get(key) is None
        assert len(list(Path(cache_dir).glob("*"))) == 0

    def test_03_cache_key_string_repr(self):
        """CacheKey 有可读的字符串表示"""
        key = CacheKey("price_matrix", "close_2024", "v1")
        s = str(key)
        assert "price_matrix" in s
        assert "close_2024" in s

    def test_04_concurrent_set_same_key(self, manager, sample_df):
        """同一 key 多次 set 应覆盖(最后写入胜出)"""
        key = CacheKey("price", "close", "v1")
        df1 = sample_df
        df2 = sample_df * 2

        manager.set(key, df1)
        manager.set(key, df2)  # 覆盖

        result = manager.get(key)
        pd.testing.assert_frame_equal(result, df2, check_freq=False)

        # 只应有一个 parquet 文件(覆盖而非追加)
        cache_files = list(Path(manager.cache_dir).glob("*.parquet"))
        assert len(cache_files) == 1
