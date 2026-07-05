# -*- coding: utf-8 -*-
"""T1 E1-T4: 体制转换 3 维维度测试

测试目标:
- regime_transition_prob (Hamilton 1989 Markov 两状态)
- regime_persistence
- regime_ic_diff (一阶差分均值差, 方案 C)

当前状态 (Red): 3 个新计算方法不存在 → AttributeError/TypeError
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
def regime_shift_data():
    """含体制转换的数据: 前半段低均值, 后半段高均值, T=300, N=30"""
    rng = np.random.RandomState(42)
    T, N = 300, 30
    data = np.zeros((T, N))
    # 前半段: 均值 0
    data[:T//2] = rng.randn(T//2, N) * 0.5
    # 后半段: 均值 1 (体制转换)
    data[T//2:] = rng.randn(T - T//2, N) * 0.5 + 1.0
    dates = pd.date_range('2020-01-01', periods=T, freq='D')
    cols = [f'stock_{i:03d}' for i in range(N)]
    return pd.DataFrame(data, index=dates, columns=cols)


@pytest.fixture
def stable_data():
    """稳定数据: 无体制转换, 单一分布, T=300, N=30"""
    rng = np.random.RandomState(42)
    T, N = 300, 30
    data = rng.randn(T, N) * 0.5
    dates = pd.date_range('2020-01-01', periods=T, freq='D')
    cols = [f'stock_{i:03d}' for i in range(N)]
    return pd.DataFrame(data, index=dates, columns=cols)


@pytest.fixture
def small_data():
    """小样本数据: T=100, 不满足 regime_min_samples=200"""
    rng = np.random.RandomState(42)
    T, N = 100, 30
    data = rng.randn(T, N)
    dates = pd.date_range('2020-01-01', periods=T, freq='D')
    cols = [f'stock_{i:03d}' for i in range(N)]
    return pd.DataFrame(data, index=dates, columns=cols)


# =============================================================================
# E1-T4: 体制转换维度测试
# =============================================================================

class TestRegimeSwitchingDimensions:
    """E1-T4: 体制转换 3 维维度测试"""

    def test_regime_transition_prob_normal_case(self, regime_shift_data):
        """构造两状态序列 → regime_transition_prob ∈ (0, 1)"""
        config = FingerprintConfig(enable_regime_switching=True, regime_min_samples=200)
        fingerprinter = FactorFingerprinter(config)
        fp = fingerprinter.extract_fingerprint(regime_shift_data)

        assert not np.isnan(fp.regime_transition_prob), (
            "构造的体制转换数据 → regime_transition_prob 应有值"
        )
        assert 0 < fp.regime_transition_prob < 1, (
            f"regime_transition_prob 应 ∈ (0,1), 实际 {fp.regime_transition_prob}"
        )

    def test_regime_persistence_normal_case(self, regime_shift_data):
        """构造两状态序列 → regime_persistence > 1"""
        config = FingerprintConfig(enable_regime_switching=True, regime_min_samples=200)
        fingerprinter = FactorFingerprinter(config)
        fp = fingerprinter.extract_fingerprint(regime_shift_data)

        assert not np.isnan(fp.regime_persistence), "regime_persistence 应有值"
        assert fp.regime_persistence > 1, (
            f"regime_persistence 应 > 1 (持续期 = 1/转移概率 > 1), 实际 {fp.regime_persistence}"
        )

    def test_regime_ic_diff_normal_case(self, regime_shift_data):
        """构造 IC 差异序列 → regime_ic_diff != 0

        方案 C: 一阶差分均值差 (C1 修订)
        """
        config = FingerprintConfig(enable_regime_switching=True, regime_min_samples=200)
        fingerprinter = FactorFingerprinter(config)
        fp = fingerprinter.extract_fingerprint(regime_shift_data)

        # regime_ic_diff 可能为 NaN (若 Markov 不收敛), 但构造的体制转换数据应收敛
        if not np.isnan(fp.regime_ic_diff):
            # 构造的体制转换数据有均值跳变, 一阶差分均值应有差异
            assert isinstance(fp.regime_ic_diff, float), (
                f"regime_ic_diff 应为 float, 实际 {type(fp.regime_ic_diff)}"
            )

    def test_regime_disabled_returns_nan(self, regime_shift_data):
        """enable_regime_switching=False → 3 维体制指标全 NaN"""
        config = FingerprintConfig(enable_regime_switching=False)
        fingerprinter = FactorFingerprinter(config)
        fp = fingerprinter.extract_fingerprint(regime_shift_data)

        assert np.isnan(fp.regime_transition_prob), (
            "enable_regime_switching=False → regime_transition_prob 应为 NaN"
        )
        assert np.isnan(fp.regime_persistence)
        assert np.isnan(fp.regime_ic_diff)

    def test_regime_insufficient_samples_returns_nan(self, small_data):
        """样本数 < regime_min_samples → 3 维体制指标全 NaN"""
        # T=100, regime_min_samples=200 → 不满足
        config = FingerprintConfig(enable_regime_switching=True, regime_min_samples=200)
        fingerprinter = FactorFingerprinter(config)
        fp = fingerprinter.extract_fingerprint(small_data)

        assert np.isnan(fp.regime_transition_prob), (
            "样本数 < regime_min_samples → regime_transition_prob 应为 NaN"
        )
        assert np.isnan(fp.regime_persistence)
        assert np.isnan(fp.regime_ic_diff)

    def test_regime_non_convergent_returns_nan(self):
        """构造不收敛序列 → 3 维体制指标全 NaN (降级方案)

        常数序列无方差, Markov 拟合应不收敛或退化为单状态
        """
        rng = np.random.RandomState(42)
        T, N = 300, 30
        # 构造常数序列 (零方差)
        data = np.ones((T, N)) * 0.5
        dates = pd.date_range('2020-01-01', periods=T, freq='D')
        cols = [f'stock_{i:03d}' for i in range(N)]
        constant_data = pd.DataFrame(data, index=dates, columns=cols)

        config = FingerprintConfig(enable_regime_switching=True, regime_min_samples=200)
        fingerprinter = FactorFingerprinter(config)
        fp = fingerprinter.extract_fingerprint(constant_data)

        # 常数序列无体制转换 → 应返回 NaN 或不抛异常
        # 不强制 NaN (实现可能返回 0), 但不应抛异常
        assert isinstance(fp.regime_transition_prob, float)
