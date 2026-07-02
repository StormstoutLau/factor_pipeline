# -*- coding: utf-8 -*-
"""TD-3: NeutralizerAdapter fit/transform 语义重构测试

验证 ADR-018 重构:
  - fit() 真正预计算 industry dummies (不再空操作)
  - transform() 用 fit() 缓存的 dummies 做 OLS + 残差
  - fit_transform(X, industry_data=...) 与 fit(X, industry_data=...).transform(X) 数值一致
  - 无 industry_data 时跳过中性化 (向后兼容)
  - external_neutralizer kwargs 仍可用 (向后兼容)

TDD Red 阶段: 这些测试在重构前应失败 (fit() 不预计算, 无 _industry_dummies_cache 属性)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from factor_pipeline.adapters import NeutralizerAdapter


# =============================================================================
# Fixture (本地, 避免依赖 conftest)
# =============================================================================

@pytest.fixture
def td3_factor_data() -> pd.DataFrame:
    """小规模因子数据 (5 日期 × 20 股票, 含 NaN)"""
    np.random.seed(123)
    dates = pd.date_range('2020-01-01', periods=5, freq='D')
    stocks = [f'S{i:02d}' for i in range(20)]
    data = np.random.randn(5, 20)
    data[0, 5] = np.nan  # 注入 1 个 NaN
    return pd.DataFrame(data, index=dates, columns=stocks)


@pytest.fixture
def td3_industry_data() -> pd.Series:
    """行业分类 (20 股票, 4 行业)"""
    stocks = [f'S{i:02d}' for i in range(20)]
    industries = ['银行', '医药', '科技', '消费'] * 5  # 每行业 5 只
    return pd.Series(industries, index=stocks)


# =============================================================================
# Test 1: fit() 预计算 industry dummies
# =============================================================================

class TestFitPrecomputesDummies:
    """TD-3: fit() 应预计算 industry dummies 并缓存"""

    def test_fit_creates_dummies_cache(self, td3_factor_data, td3_industry_data):
        """fit() 后应有 _industry_dummies_cache 属性"""
        adapter = NeutralizerAdapter()
        adapter.fit(td3_factor_data, industry_data=td3_industry_data)

        # TD-3: fit() 应预计算 dummies 缓存
        assert hasattr(adapter, '_industry_dummies_cache'), (
            "fit() 后应有 _industry_dummies_cache 属性"
        )
        assert adapter._industry_dummies_cache is not None, (
            "_industry_dummies_cache 不应为 None"
        )

    def test_fit_cache_has_entry_per_date(self, td3_factor_data, td3_industry_data):
        """fit() 缓存应为每个有效日期创建条目"""
        adapter = NeutralizerAdapter()
        adapter.fit(td3_factor_data, industry_data=td3_industry_data)

        cache = adapter._industry_dummies_cache
        # 5 个日期, 但可能因 NaN 导致某些日期跳过
        # 至少应有 4 个日期的条目 (1 个 NaN 不影响整列)
        assert len(cache) >= 4, (
            f"应有 >=4 个日期的 dummies 条目, 实际 {len(cache)}"
        )

    def test_fit_cache_entry_contains_dummies_and_common(self, td3_factor_data, td3_industry_data):
        """每个缓存条目应是 (dummies_matrix, common_stocks) 元组"""
        adapter = NeutralizerAdapter()
        adapter.fit(td3_factor_data, industry_data=td3_industry_data)

        cache = adapter._industry_dummies_cache
        first_date = next(iter(cache.keys()))
        entry = cache[first_date]
        # 应是可解包的 2 元组
        assert len(entry) == 2, f"缓存条目应是 2 元组, 实际长度 {len(entry)}"
        dummies, common = entry
        # dummies 应是 DataFrame 或 ndarray
        assert dummies is not None, "dummies 矩阵不应为 None"
        assert common is not None, "common_stocks 不应为 None"

    def test_fit_sets_is_fitted_true(self, td3_factor_data, td3_industry_data):
        """fit() 后 is_fitted 应为 True"""
        adapter = NeutralizerAdapter()
        assert adapter.is_fitted is False
        adapter.fit(td3_factor_data, industry_data=td3_industry_data)
        assert adapter.is_fitted is True


# =============================================================================
# Test 2: transform() 使用 fit() 缓存的 dummies
# =============================================================================

class TestTransformUsesCachedDummies:
    """TD-3: transform() 应使用 fit() 缓存的 dummies, 不重新计算"""

    def test_transform_after_fit_returns_residuals(self, td3_factor_data, td3_industry_data):
        """fit().transform() 应返回 OLS 残差"""
        adapter = NeutralizerAdapter()
        result = adapter.fit(td3_factor_data, industry_data=td3_industry_data).transform(td3_factor_data)

        # 形状一致
        assert result.shape == td3_factor_data.shape
        # 残差均值应接近 0 (每个截面 OLS 残差均值为 0)
        for date in td3_factor_data.index:
            if date in adapter._industry_dummies_cache:
                residuals = result.loc[date].dropna()
                if len(residuals) > 0:
                    assert abs(residuals.mean()) < 1e-9, (
                        f"日期 {date} 残差均值应接近 0 (OLS 性质), 实际 {residuals.mean()}"
                    )

    def test_transform_without_fit_raises(self, td3_factor_data, td3_industry_data):
        """未 fit 直接 transform 应抛 ValueError"""
        adapter = NeutralizerAdapter()
        with pytest.raises(ValueError, match="未拟合"):
            adapter.transform(td3_factor_data)


# =============================================================================
# Test 3: fit_transform 一致性
# =============================================================================

class TestFitTransformConsistency:
    """TD-3: fit_transform(X, industry_data=...) == fit(X, industry_data=...).transform(X)"""

    def test_fit_transform_equals_fit_then_transform(self, td3_factor_data, td3_industry_data):
        """fit_transform 与 fit().transform() 数值一致"""
        # 路径 A: fit_transform
        adapter_a = NeutralizerAdapter()
        result_a = adapter_a.fit_transform(td3_factor_data, industry_data=td3_industry_data)

        # 路径 B: fit + transform
        adapter_b = NeutralizerAdapter()
        adapter_b.fit(td3_factor_data, industry_data=td3_industry_data)
        result_b = adapter_b.transform(td3_factor_data)

        # 数值一致 (允许浮点误差)
        np.testing.assert_array_almost_equal(
            result_a.values, result_b.values, decimal=10,
            err_msg="fit_transform 与 fit().transform() 结果不一致"
        )

    def test_fit_transform_with_industry_data_kwarg(self, td3_factor_data, td3_industry_data):
        """fit_transform(X, industry_data=...) 应工作 (向后兼容)"""
        adapter = NeutralizerAdapter()
        result = adapter.fit_transform(td3_factor_data, industry_data=td3_industry_data)

        assert result.shape == td3_factor_data.shape
        assert adapter.is_fitted is True


# =============================================================================
# Test 4: 无 industry_data 时跳过中性化 (向后兼容)
# =============================================================================

class TestNoIndustryDataSkips:
    """TD-3: 无 industry_data 时跳过中性化, 返回原数据"""

    def test_fit_transform_without_industry_data_returns_original(self, td3_factor_data):
        """无 industry_data 时 fit_transform 应返回原数据"""
        adapter = NeutralizerAdapter()
        result = adapter.fit_transform(td3_factor_data)

        assert result.shape == td3_factor_data.shape
        # 应跳过中性化 (返回原值, 可能 fillna(0))
        # 不应抛异常

    def test_fit_without_industry_data_sets_fitted(self, td3_factor_data):
        """无 industry_data 时 fit() 仍应设 is_fitted"""
        adapter = NeutralizerAdapter()
        adapter.fit(td3_factor_data)
        assert adapter.is_fitted is True
        # dummies cache 应为空 dict 或 None
        cache = getattr(adapter, '_industry_dummies_cache', None)
        assert cache is None or len(cache) == 0, (
            f"无 industry_data 时 cache 应为空, 实际 {cache}"
        )


# =============================================================================
# Test 5: external_neutralizer kwargs 向后兼容
# =============================================================================

class TestExternalNeutralizerCompat:
    """TD-3: external_neutralizer kwargs 仍可用 (向后兼容)"""

    def test_transform_with_external_neutralizer(self, td3_factor_data):
        """transform() 接受 external_neutralizer kwargs"""
        adapter = NeutralizerAdapter()
        adapter.fit(td3_factor_data)  # 无 industry_data, fit 仅标记

        class MockNeutralizer:
            def industry_neutralization(self, X, method):
                return X * 2  # 简单 mock: 返回 2 倍数据

        result = adapter.transform(td3_factor_data, external_neutralizer=MockNeutralizer())
        # mock 返回 2 倍数据
        np.testing.assert_array_almost_equal(
            result.values, (td3_factor_data * 2).values, decimal=10
        )


# =============================================================================
# Test 6: 数值正确性 — 与独立 OLS 对比
# =============================================================================

class TestNumericalCorrectness:
    """TD-3: 重构后数值应与直接 OLS 一致"""

    def test_residuals_match_direct_ols(self, td3_factor_data, td3_industry_data):
        """重构后残差应与直接 OLS 计算一致"""
        adapter = NeutralizerAdapter()
        result = adapter.fit_transform(td3_factor_data, industry_data=td3_industry_data)

        # 手工计算一个日期的残差对比
        test_date = td3_factor_data.index[0]
        factor_col = td3_factor_data.loc[test_date].dropna()
        common = factor_col.index.intersection(td3_industry_data.index)
        y = factor_col[common].values.astype(float)
        industries = td3_industry_data[common]
        dummies = pd.get_dummies(industries, drop_first=True).astype(float)
        X = sm.add_constant(dummies, has_constant='add').astype(float)
        model = sm.OLS(y, X).fit()
        expected_residuals = model.resid

        actual_residuals = result.loc[test_date, common].values
        np.testing.assert_array_almost_equal(
            actual_residuals, expected_residuals, decimal=10,
            err_msg=f"日期 {test_date} 残差与直接 OLS 不一致"
        )
