# -*- coding: utf-8 -*-
"""
性能优化模块单元测试

测试 timed 装饰器、缓存、批量处理和基准测试功能。
"""

import pytest
import time
import pandas as pd
import numpy as np

from factor_pipeline.performance import (
    timed,
    SimpleCache,
    cached,
    batch_process,
    benchmark,
)


class TestTimedDecorator:
    """计时装饰器测试"""
    
    def test_timed_execution(self):
        """测试计时功能"""
        @timed("test_step")
        def slow_function():
            time.sleep(0.01)
            return 42
        
        result = slow_function()
        assert result == 42
    
    def test_timed_with_exception(self):
        """测试异常时的计时"""
        @timed("failing_step")
        def failing_function():
            raise ValueError("测试错误")
        
        with pytest.raises(ValueError):
            failing_function()


class TestSimpleCache:
    """简单缓存测试"""
    
    def test_basic_operations(self):
        """测试基本操作"""
        cache = SimpleCache(max_size=3)
        
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        assert "key1" in cache
    
    def test_missing_key(self):
        """测试缺失键"""
        cache = SimpleCache()
        assert cache.get("missing") is None
        assert "missing" not in cache
    
    def test_lru_eviction(self):
        """测试 LRU 淘汰"""
        cache = SimpleCache(max_size=2)
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.get("key1")  # 访问 key1，增加计数
        cache.set("key3", "value3")  # 应该淘汰 key2
        
        assert cache.get("key1") == "value1"
        assert cache.get("key2") is None  # 被淘汰
        assert cache.get("key3") == "value3"
    
    def test_clear(self):
        """测试清空"""
        cache = SimpleCache()
        cache.set("key1", "value1")
        cache.clear()
        
        assert cache.get("key1") is None
        assert len(cache._cache) == 0


class TestCachedDecorator:
    """缓存装饰器测试"""
    
    def test_caching(self):
        """测试缓存功能"""
        cache = SimpleCache()
        call_count = 0
        
        @cached(cache)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2
        
        result1 = expensive_function(5)
        result2 = expensive_function(5)
        
        assert result1 == 10
        assert result2 == 10
        assert call_count == 1  # 只调用一次
    
    def test_cache_with_different_args(self):
        """测试不同参数的缓存"""
        cache = SimpleCache()
        
        @cached(cache)
        def compute(x):
            return x ** 2
        
        assert compute(2) == 4
        assert compute(3) == 9
        assert compute(2) == 4  # 从缓存读取


class TestBatchProcess:
    """批量处理测试"""
    
    def test_batch_by_rows(self):
        """测试按行分批"""
        data = pd.DataFrame(np.random.randn(100, 5))
        
        def processor(df):
            return df * 2
        
        result = batch_process(data, processor, batch_size=30, axis=0)
        
        assert result.shape == data.shape
        pd.testing.assert_frame_equal(result, data * 2)
    
    def test_batch_by_columns(self):
        """测试按列分批"""
        data = pd.DataFrame(np.random.randn(10, 100))
        
        def processor(df):
            return df + 1
        
        result = batch_process(data, processor, batch_size=30, axis=1)
        
        assert result.shape == data.shape
        pd.testing.assert_frame_equal(result, data + 1)


class TestBenchmark:
    """基准测试工具测试"""
    
    def test_benchmark_basic(self):
        """测试基本基准测试"""
        def simple_func():
            time.sleep(0.001)
            return 42
        
        stats = benchmark(simple_func, n_runs=3, warmup=1)
        
        assert 'mean_ms' in stats
        assert 'std_ms' in stats
        assert 'min_ms' in stats
        assert 'max_ms' in stats
        assert 'median_ms' in stats
        assert stats['n_runs'] == 3
        assert stats['mean_ms'] > 0
    
    def test_benchmark_with_args(self):
        """测试带参数的基准测试"""
        def add_func(a, b):
            return a + b
        
        stats = benchmark(add_func, 2, 3, n_runs=2, warmup=0)
        
        assert stats['n_runs'] == 2
        assert stats['mean_ms'] >= 0
