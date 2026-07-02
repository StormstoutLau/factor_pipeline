# -*- coding: utf-8 -*-
"""
PipelineCache 单元测试

测试范围:
1. 缓存写入和读取
2. 缓存 miss（首次调用）
3. 缓存 hit（相同数据）
4. 数据变化导致缓存 miss
5. 参数变化导致缓存 miss
6. 缓存禁用
7. 缓存清理
8. data_hash 一致性
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np
import tempfile
import shutil

# 添加项目根目录到路径
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_cache_dir():
    """临时缓存目录"""
    path = tempfile.mkdtemp(prefix="pipeline_cache_test_")
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def cache(temp_cache_dir):
    """启用的缓存实例"""
    from factor_pipeline.cache import PipelineCache
    return PipelineCache(cache_dir=temp_cache_dir, enabled=True)


@pytest.fixture
def cache_disabled(temp_cache_dir):
    """禁用的缓存实例"""
    from factor_pipeline.cache import PipelineCache
    return PipelineCache(cache_dir=temp_cache_dir, enabled=False)


@pytest.fixture
def sample_df():
    """标准测试 DataFrame"""
    np.random.seed(42)
    dates = pd.date_range('2020-01-01', periods=100, freq='D')
    stocks = [f'STOCK_{i:03d}' for i in range(50)]
    data = np.random.randn(100, 50)
    data[10, 5] = np.nan  # 添加一些缺失值
    return pd.DataFrame(data, index=dates, columns=stocks)


@pytest.fixture
def different_df():
    """不同的测试 DataFrame"""
    np.random.seed(99)
    dates = pd.date_range('2020-01-01', periods=100, freq='D')
    stocks = [f'STOCK_{i:03d}' for i in range(50)]
    data = np.random.randn(100, 50) * 2
    return pd.DataFrame(data, index=dates, columns=stocks)


# =============================================================================
# 1. 基本缓存读写
# =============================================================================

class TestCacheBasic:
    """测试基本的缓存读写操作"""

    def test_cache_miss_on_first_call(self, cache, sample_df):
        """首次调用应该返回 None（缓存 miss）"""
        result = cache.get("test_step", "factor_a", {}, sample_df)
        assert result is None, "首次调用应该是缓存 miss"

    def test_cache_hit_after_set(self, cache, sample_df):
        """写入后读取应该命中缓存"""
        cache.set("test_step", "factor_a", {}, sample_df, sample_df)
        result = cache.get("test_step", "factor_a", {}, sample_df)
        assert result is not None, "写入后应该命中缓存"
        # parquet 不保留 DatetimeIndex.freq，只比较值
        pd.testing.assert_frame_equal(
            result, sample_df, check_freq=False
        )

    def test_cache_miss_with_different_step_name(self, cache, sample_df):
        """不同步骤名应该 miss"""
        cache.set("step_a", "factor_a", {}, sample_df, sample_df)
        result = cache.get("step_b", "factor_a", {}, sample_df)
        assert result is None, "不同步骤名应该 miss"

    def test_cache_miss_with_different_factor_name(self, cache, sample_df):
        """不同因子名应该 miss"""
        cache.set("step_a", "factor_a", {}, sample_df, sample_df)
        result = cache.get("step_a", "factor_b", {}, sample_df)
        assert result is None, "不同因子名应该 miss"


# =============================================================================
# 2. 数据变化导致缓存失效
# =============================================================================

class TestCacheDataChange:
    """测试数据变化时缓存正确失效"""

    def test_cache_miss_with_different_data(self, cache, sample_df, different_df):
        """不同输入数据应该 miss"""
        cache.set("test_step", "factor_a", {}, sample_df, sample_df)
        result = cache.get("test_step", "factor_a", {}, different_df)
        assert result is None, "不同数据应该 miss"

    def test_cache_hit_with_same_data(self, cache, sample_df):
        """相同数据应该命中"""
        cache.set("test_step", "factor_a", {}, sample_df, sample_df)

        # 第二次调用相同数据
        result = cache.get("test_step", "factor_a", {}, sample_df.copy())
        assert result is not None, "相同数据应该命中"

    def test_cache_miss_after_data_modification(self, cache, sample_df):
        """修改数据后应该 miss"""
        cache.set("test_step", "factor_a", {}, sample_df, sample_df)

        modified = sample_df.copy()
        modified.iloc[0, 0] = 999.0  # 修改一个值

        result = cache.get("test_step", "factor_a", {}, modified)
        assert result is None, "修改数据后应该 miss"


# =============================================================================
# 3. 参数变化导致缓存失效
# =============================================================================

class TestCacheParamsChange:
    """测试参数变化时缓存正确失效"""

    def test_cache_miss_with_different_params(self, cache, sample_df):
        """不同参数应该 miss"""
        cache.set("test_step", "factor_a", {"method": "mad"}, sample_df, sample_df)
        result = cache.get("test_step", "factor_a", {"method": "iqr"}, sample_df)
        assert result is None, "不同参数应该 miss"

    def test_cache_miss_with_additional_params(self, cache, sample_df):
        """新增参数应该 miss"""
        cache.set("test_step", "factor_a", {"method": "mad"}, sample_df, sample_df)
        result = cache.get("test_step", "factor_a", {"method": "mad", "threshold": 3.0}, sample_df)
        assert result is None, "新增参数应该 miss"

    def test_cache_hit_with_same_params(self, cache, sample_df):
        """相同参数应该命中"""
        params = {"method": "mad", "threshold": 3.0, "auto_select": True}
        cache.set("test_step", "factor_a", params, sample_df, sample_df)
        result = cache.get("test_step", "factor_a", dict(params), sample_df)
        assert result is not None, "相同参数应该命中"

    def test_cache_hit_with_params_different_order(self, cache, sample_df):
        """参数顺序不同但值相同应该命中"""
        cache.set("test_step", "factor_a", {"a": 1, "b": 2}, sample_df, sample_df)
        result = cache.get("test_step", "factor_a", {"b": 2, "a": 1}, sample_df)
        assert result is not None, "参数顺序不同但值相同应该命中"


# =============================================================================
# 4. 缓存禁用
# =============================================================================

class TestCacheDisabled:
    """测试缓存禁用时的行为"""

    def test_get_returns_none_when_disabled(self, cache_disabled, sample_df):
        """禁用时 get 永远返回 None"""
        cache_disabled.set("test_step", "factor_a", {}, sample_df, sample_df)
        result = cache_disabled.get("test_step", "factor_a", {}, sample_df)
        assert result is None, "禁用时应该返回 None"

    def test_set_does_not_write_when_disabled(self, cache_disabled, temp_cache_dir):
        """禁用时不应该写入文件"""
        import os
        df = pd.DataFrame({"a": [1, 2, 3]})
        cache_disabled.set("test_step", "factor_a", {}, df, df)
        parquet_files = [f for f in os.listdir(temp_cache_dir) if f.endswith('.parquet')]
        assert len(parquet_files) == 0, "禁用时不应该写文件"


# =============================================================================
# 5. 缓存清理
# =============================================================================

class TestCacheClear:
    """测试缓存清理功能"""

    def test_clear_removes_all_files(self, cache, temp_cache_dir, sample_df):
        """清理后所有缓存文件应该被删除"""
        import os
        cache.set("step_a", "factor_a", {}, sample_df, sample_df)
        cache.set("step_b", "factor_b", {}, sample_df, sample_df)

        parquet_files_before = [f for f in os.listdir(temp_cache_dir) if f.endswith('.parquet')]
        assert len(parquet_files_before) > 0, "应该有缓存文件"

        cache.clear()

        parquet_files_after = [f for f in os.listdir(temp_cache_dir) if f.endswith('.parquet')]
        assert len(parquet_files_after) == 0, "清理后不应有缓存文件"

    def test_clear_on_empty_cache(self, cache):
        """空缓存清理不应该报错"""
        cache.clear()  # 不应该抛出异常


# =============================================================================
# 6. data_hash 一致性
# =============================================================================

class TestDataHash:
    """测试 data_hash 的一致性"""

    def test_same_data_produces_same_hash(self, cache, sample_df):
        """相同数据应该产生相同 hash"""
        h1 = cache._data_hash(sample_df)
        h2 = cache._data_hash(sample_df.copy())
        assert h1 == h2, "相同数据应该产生相同 hash"

    def test_different_data_produces_different_hash(self, cache, sample_df, different_df):
        """不同数据应该产生不同 hash"""
        h1 = cache._data_hash(sample_df)
        h2 = cache._data_hash(different_df)
        assert h1 != h2, "不同数据应该产生不同 hash"

    def test_hash_is_stable_across_instances(self, temp_cache_dir, sample_df):
        """相同数据的 hash 在不同实例间应该一致"""
        from factor_pipeline.cache import PipelineCache
        c1 = PipelineCache(cache_dir=temp_cache_dir)
        c2 = PipelineCache(cache_dir=temp_cache_dir)
        assert c1._data_hash(sample_df) == c2._data_hash(sample_df)


# =============================================================================
# 7. 缓存目录自动创建
# =============================================================================

class TestCacheDirCreation:
    """测试缓存目录自动创建"""

    def test_cache_dir_created_automatically(self, temp_cache_dir):
        """缓存目录应该自动创建"""
        import os
        sub_dir = os.path.join(temp_cache_dir, "subdir", "nested")
        from factor_pipeline.cache import PipelineCache
        cache = PipelineCache(cache_dir=sub_dir, enabled=True)
        assert os.path.exists(sub_dir), "缓存目录应该自动创建"
        cache.clear()
        shutil.rmtree(sub_dir, ignore_errors=True)


# =============================================================================
# 8. DataFrame 读写保真
# =============================================================================

class TestCacheFidelity:
    """测试缓存读写的数据保真性"""

    def test_roundtrip_preserves_data(self, cache, sample_df):
        """写入后读出的数据应该完全一致"""
        cache.set("test_step", "factor_a", {}, sample_df, sample_df)
        result = cache.get("test_step", "factor_a", {}, sample_df)
        # parquet 不保留 DatetimeIndex.freq，只比较值
        pd.testing.assert_frame_equal(result, sample_df, check_freq=False)

    def test_roundtrip_preserves_nan(self, cache, sample_df):
        """NaN 值应该被正确保留"""
        cache.set("test_step", "factor_a", {}, sample_df, sample_df)
        result = cache.get("test_step", "factor_a", {}, sample_df)
        # 检查 NaN 是否被保留
        assert result.isnull().sum().sum() == sample_df.isnull().sum().sum(), \
            "NaN 数量应该一致"

    def test_roundtrip_preserves_dtypes(self, cache, sample_df):
        """数据类型应该被保留"""
        cache.set("test_step", "factor_a", {}, sample_df, sample_df)
        result = cache.get("test_step", "factor_a", {}, sample_df)
        assert result.dtypes.equals(sample_df.dtypes), "dtypes 应该一致"

    def test_roundtrip_preserves_index(self, cache, sample_df):
        """索引应该被保留"""
        cache.set("test_step", "factor_a", {}, sample_df, sample_df)
        result = cache.get("test_step", "factor_a", {}, sample_df)
        # parquet 不保留 DatetimeIndex.freq，比较值而非元数据
        assert (result.index == sample_df.index).all(), \
            f"索引值不一致"
        pd.testing.assert_index_equal(result.columns, sample_df.columns)