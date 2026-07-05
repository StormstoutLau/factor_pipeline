# -*- coding: utf-8 -*-
"""T1 E1-T3: 尾部依赖 4 维维度测试

测试目标:
- tail_dependence_lower / tail_dependence_upper (Nelsen 2006 Copula)
- gpd_shape (Pickands 1975)
- hill_estimator (Hill 1975)

当前状态 (Red): 4 个新计算方法不存在 → AttributeError/TypeError
Green 后: 方法实现, 全部通过
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factor_pipeline.modules.factor_fingerprint import (
    FactorFingerprinter,
    FingerprintConfig,
)


@pytest.fixture
def heavy_tail_data():
    """重尾数据: t 分布 df=3, T=500, N=30 (满足 min_extreme_samples=100*4=400)"""
    rng = np.random.RandomState(42)
    T, N = 500, 30
    data = rng.standard_t(df=3, size=(T, N))
    dates = pd.date_range('2020-01-01', periods=T, freq='D')
    cols = [f'stock_{i:03d}' for i in range(N)]
    return pd.DataFrame(data, index=dates, columns=cols)


@pytest.fixture
def normal_data():
    """正态分布数据: 轻尾, T=500, N=30"""
    rng = np.random.RandomState(42)
    T, N = 500, 30
    data = rng.randn(T, N)
    dates = pd.date_range('2020-01-01', periods=T, freq='D')
    cols = [f'stock_{i:03d}' for i in range(N)]
    return pd.DataFrame(data, index=dates, columns=cols)


@pytest.fixture
def small_data():
    """小样本数据: T=100, 不满足 min_extreme_samples=100*4=400"""
    rng = np.random.RandomState(42)
    T, N = 100, 30
    data = rng.standard_t(df=3, size=(T, N))
    dates = pd.date_range('2020-01-01', periods=T, freq='D')
    cols = [f'stock_{i:03d}' for i in range(N)]
    return pd.DataFrame(data, index=dates, columns=cols)


# =============================================================================
# E1-T3: 尾部依赖维度测试
# =============================================================================

class TestTailDependenceDimensions:
    """E1-T3: 尾部依赖 4 维维度测试"""

    def test_tail_dependence_lower_disabled_returns_nan(self, heavy_tail_data):
        """enable_tail_dependence=False → tail_dependence_lower=NaN"""
        config = FingerprintConfig(enable_tail_dependence=False)
        fingerprinter = FactorFingerprinter(config)
        fp = fingerprinter.extract_fingerprint(heavy_tail_data)

        assert np.isnan(fp.tail_dependence_lower), (
            "enable_tail_dependence=False → tail_dependence_lower 应为 NaN"
        )

    def test_tail_dependence_lower_normal_case(self, heavy_tail_data):
        """正常计算: 重尾分布 → tail_dependence_lower > 0"""
        config = FingerprintConfig(enable_tail_dependence=True, min_extreme_samples=50)
        fingerprinter = FactorFingerprinter(config)
        fp = fingerprinter.extract_fingerprint(heavy_tail_data)

        assert not np.isnan(fp.tail_dependence_lower), (
            "enable_tail_dependence=True + 充足样本 → tail_dependence_lower 应有值"
        )
        assert 0 <= fp.tail_dependence_lower <= 1, (
            f"tail_dependence_lower 应 ∈ [0,1], 实际 {fp.tail_dependence_lower}"
        )

    def test_tail_dependence_upper_normal_case(self, heavy_tail_data):
        """正常计算: 重尾分布 → tail_dependence_upper > 0"""
        config = FingerprintConfig(enable_tail_dependence=True, min_extreme_samples=50)
        fingerprinter = FactorFingerprinter(config)
        fp = fingerprinter.extract_fingerprint(heavy_tail_data)

        assert not np.isnan(fp.tail_dependence_upper), (
            "enable_tail_dependence=True + 充足样本 → tail_dependence_upper 应有值"
        )
        assert 0 <= fp.tail_dependence_upper <= 1, (
            f"tail_dependence_upper 应 ∈ [0,1], 实际 {fp.tail_dependence_upper}"
        )

    def test_gpd_shape_heavy_tail(self, heavy_tail_data):
        """t 分布 (df=3) → gpd_shape > 0 (重尾)"""
        config = FingerprintConfig(enable_tail_dependence=True, min_extreme_samples=50)
        fingerprinter = FactorFingerprinter(config)
        fp = fingerprinter.extract_fingerprint(heavy_tail_data)

        assert not np.isnan(fp.gpd_shape), "gpd_shape 应有值"
        assert fp.gpd_shape > 0, (
            f"t 分布 (df=3) 重尾 → gpd_shape > 0, 实际 {fp.gpd_shape}"
        )

    def test_gpd_shape_normal_distribution(self, normal_data):
        """正态分布 → gpd_shape ≈ 0 (轻尾)

        正态分布尾部指数 ξ ≈ 0, GPD 退化为指数分布
        """
        config = FingerprintConfig(enable_tail_dependence=True, min_extreme_samples=50)
        fingerprinter = FactorFingerprinter(config)
        fp = fingerprinter.extract_fingerprint(normal_data)

        assert not np.isnan(fp.gpd_shape), "gpd_shape 应有值"
        # 正态分布 gpd_shape 应接近 0 (容差较大, 因 Pickands 估计量有方差)
        assert abs(fp.gpd_shape) < 0.5, (
            f"正态分布 gpd_shape ≈ 0 (|ξ| < 0.5), 实际 {fp.gpd_shape}"
        )

    def test_hill_estimator_heavy_tail(self, heavy_tail_data):
        """t 分布 (df=3) → hill_estimator > 0 (重尾)"""
        config = FingerprintConfig(enable_tail_dependence=True, min_extreme_samples=50)
        fingerprinter = FactorFingerprinter(config)
        fp = fingerprinter.extract_fingerprint(heavy_tail_data)

        assert not np.isnan(fp.hill_estimator), "hill_estimator 应有值"
        assert fp.hill_estimator > 0, (
            f"t 分布 (df=3) 重尾 → hill_estimator > 0, 实际 {fp.hill_estimator}"
        )

    def test_hill_estimator_insufficient_samples(self, small_data):
        """样本数 < min_extreme_samples*4 → hill_estimator=NaN"""
        # T=100, min_extreme_samples=100 → 需 400 样本 → 不满足
        config = FingerprintConfig(
            enable_tail_dependence=True,
            min_extreme_samples=100,  # 需 100*4=400 样本
        )
        fingerprinter = FactorFingerprinter(config)
        fp = fingerprinter.extract_fingerprint(small_data)

        assert np.isnan(fp.hill_estimator), (
            "样本数 < min_extreme_samples*4 → hill_estimator 应为 NaN"
        )

    def test_gpd_shape_insufficient_samples(self, small_data):
        """样本数 < min_extreme_samples*4 → gpd_shape=NaN"""
        config = FingerprintConfig(
            enable_tail_dependence=True,
            min_extreme_samples=100,
        )
        fingerprinter = FactorFingerprinter(config)
        fp = fingerprinter.extract_fingerprint(small_data)

        assert np.isnan(fp.gpd_shape), (
            "样本数 < min_extreme_samples*4 → gpd_shape 应为 NaN"
        )
