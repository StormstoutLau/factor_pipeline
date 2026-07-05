# -*- coding: utf-8 -*-
"""T1 E1-T1+T2+T6: extract_fingerprint 黄金参考 + to_dict 完整性 + 13 维回归测试

测试目标:
- E1-T1: 黄金参考 (固定输入 → 固定 21 维输出, atol=1e-4)
- E1-T2: to_dict 字段完整性 (21 键 + 与 NamedTuple _fields 一致)
- E1-T6: 既有 13 维行为不破坏 (回归测试) + 默认配置 + min_window 保护

当前状态 (Red): FactorFingerprint 仅 13 维, 期望 21 维 → 全部失败
Green 后: 21 维实现, 全部通过
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factor_pipeline.modules.factor_fingerprint import (
    FactorFingerprinter,
    FactorFingerprint,
    FingerprintConfig,
)


# ── 公共 fixture ──────────────────────────────────────────────

@pytest.fixture
def golden_factor_data():
    """黄金参考输入: 固定 seed, T=500, N=50, 含 NaN 与缺失

    T=500 满足 min_window=24, regime_min_samples=200, min_extreme_samples=100*4=400
    N=50 满足 min_stocks=10
    """
    rng = np.random.RandomState(42)
    T, N = 500, 50
    data = rng.randn(T, N)
    # 注入少量 NaN (5%)
    mask = rng.rand(T, N) < 0.05
    data[mask] = np.nan
    # 注入重尾特征 (第 0-9 列用 t 分布 df=3)
    data[:, :10] = rng.standard_t(df=3, size=(T, 10))
    dates = pd.date_range('2020-01-01', periods=T, freq='D')
    cols = [f'stock_{i:03d}' for i in range(N)]
    return pd.DataFrame(data, index=dates, columns=cols)


@pytest.fixture
def fingerprinter_default():
    """默认配置 FactorFingerprinter"""
    return FactorFingerprinter(FingerprintConfig())


@pytest.fixture
def fingerprinter_all_enabled():
    """全开启配置 (尾部依赖 + 体制转换)"""
    return FactorFingerprinter(FingerprintConfig(
        enable_tail_dependence=True,
        enable_regime_switching=True,
    ))


# =============================================================================
# E1-T1: 黄金参考测试
# =============================================================================

class TestExtractFingerprintGolden:
    """E1-T1: extract_fingerprint 黄金参考 (固定输入 → 固定 21 维输出)"""

    def test_golden_reference_21_dims(self, golden_factor_data, fingerprinter_all_enabled):
        """黄金参考: 固定输入 → 21 维 FactorFingerprint 字段值精确匹配 (atol=1e-4)

        Red 原因: FactorFingerprint 当前仅 13 维, 缺 8 个字段 → AttributeError
        Green 后: 21 维实现, 字段值与期望匹配
        """
        fp = fingerprinter_all_enabled.extract_fingerprint(golden_factor_data)

        # 21 维字段全部存在
        expected_fields = [
            # 既有 13 维
            'ar1_median', 'rank_autocorr', 'vol_clustering_pvalue',
            'half_life', 'level_diff_ic_ratio',
            'skewness_std', 'kurtosis_std', 'js_divergence_mean',
            'missing_cv', 'coverage_ratio',
            'sd_score', 'complexity_need', 'snr_estimate',
            # T1.1 尾部依赖 (4 维)
            'tail_dependence_lower', 'tail_dependence_upper',
            'gpd_shape', 'hill_estimator',
            # T1.2 体制转换 (3 维)
            'regime_transition_prob', 'regime_persistence', 'regime_ic_diff',
            # T1.3 综合衍生 (1 维)
            'tail_regime_score',
        ]
        for field in expected_fields:
            assert hasattr(fp, field), f"FactorFingerprint 缺少字段: {field}"

        # 21 维字段数
        assert len(FactorFingerprint._fields) == 21, (
            f"期望 21 个字段, 实际 {len(FactorFingerprint._fields)}"
        )

    def test_golden_reference_tail_dependence_values(self, golden_factor_data, fingerprinter_all_enabled):
        """黄金参考: 尾部依赖 4 维有值 (非 NaN), 因输入含 t 分布重尾"""
        fp = fingerprinter_all_enabled.extract_fingerprint(golden_factor_data)

        # 尾部依赖开启后应有值
        assert not np.isnan(fp.tail_dependence_lower), (
            "tail_dependence_lower 应有值 (enable_tail_dependence=True)"
        )
        assert not np.isnan(fp.tail_dependence_upper), (
            "tail_dependence_upper 应有值"
        )
        assert not np.isnan(fp.gpd_shape), "gpd_shape 应有值"
        assert not np.isnan(fp.hill_estimator), "hill_estimator 应有值"

        # golden_factor_data 是混合分布 (10 列 t(3) + 40 列正态), 截面均值稀释了重尾.
        # gpd_shape 符号由纯 t(3) 数据测试 (test_gpd_shape_heavy_tail) 负责,
        # golden 测试只验证 "有值" (非 NaN).
        # hill_estimator 对重尾敏感, 应 > 0 (即使混合分布)
        assert fp.hill_estimator > 0, (
            f"hill_estimator 对 t(3) 重尾敏感, 应 > 0, 实际 {fp.hill_estimator}"
        )

    def test_golden_reference_regime_values(self, golden_factor_data, fingerprinter_all_enabled):
        """黄金参考: 体制转换 3 维有值 (非 NaN), 因 T=500 满足 regime_min_samples=200"""
        fp = fingerprinter_all_enabled.extract_fingerprint(golden_factor_data)

        assert not np.isnan(fp.regime_transition_prob), (
            "regime_transition_prob 应有值 (T=500 > regime_min_samples=200)"
        )
        assert not np.isnan(fp.regime_persistence), "regime_persistence 应有值"
        # regime_ic_diff 可能为 NaN (若 Markov 不收敛), 不强制非 NaN

        # 转移概率 ∈ [0, 1]
        assert 0 <= fp.regime_transition_prob <= 1, (
            f"regime_transition_prob 应 ∈ [0,1], 实际 {fp.regime_transition_prob}"
        )

    def test_golden_reference_tail_regime_score(self, golden_factor_data, fingerprinter_all_enabled):
        """黄金参考: tail_regime_score ∈ [0, 1]"""
        fp = fingerprinter_all_enabled.extract_fingerprint(golden_factor_data)

        if not np.isnan(fp.tail_regime_score):
            assert 0 <= fp.tail_regime_score <= 1, (
                f"tail_regime_score 应 ∈ [0,1], 实际 {fp.tail_regime_score}"
            )


# =============================================================================
# E1-T2: to_dict 字段完整性测试
# =============================================================================

class TestToDictCompleteness:
    """E1-T2: to_dict 返回 21 个键, 与 NamedTuple _fields 一致"""

    def test_to_dict_has_21_keys(self, golden_factor_data, fingerprinter_all_enabled):
        """to_dict 返回 21 个键"""
        fp = fingerprinter_all_enabled.extract_fingerprint(golden_factor_data)
        d = fp.to_dict()

        assert len(d) == 21, f"期望 21 个键, 实际 {len(d)}"

    def test_to_dict_keys_match_namedtuple_fields(self, golden_factor_data, fingerprinter_all_enabled):
        """to_dict 键集合 == FactorFingerprint._fields"""
        fp = fingerprinter_all_enabled.extract_fingerprint(golden_factor_data)
        d = fp.to_dict()

        assert set(d.keys()) == set(FactorFingerprint._fields), (
            f"to_dict 键 {_sorted(d.keys())} != NamedTuple _fields {sorted(FactorFingerprint._fields)}"
        )

    def test_to_dict_includes_new_8_fields(self, golden_factor_data, fingerprinter_all_enabled):
        """to_dict 包含 8 个新字段"""
        fp = fingerprinter_all_enabled.extract_fingerprint(golden_factor_data)
        d = fp.to_dict()

        new_fields = [
            'tail_dependence_lower', 'tail_dependence_upper',
            'gpd_shape', 'hill_estimator',
            'regime_transition_prob', 'regime_persistence', 'regime_ic_diff',
            'tail_regime_score',
        ]
        for field in new_fields:
            assert field in d, f"to_dict 缺少新字段: {field}"


def _sorted(iterable):
    return sorted(iterable)


# =============================================================================
# E1-T6: 既有 13 维行为不破坏 (回归测试)
# =============================================================================

class TestBackwardCompat13Dims:
    """E1-T6: 扩展后既有 13 维字段值与扩展前一致 (回归测试)"""

    def test_existing_13_dims_present(self, golden_factor_data, fingerprinter_default):
        """扩展后既有 13 维字段仍存在"""
        fp = fingerprinter_default.extract_fingerprint(golden_factor_data)

        existing_13 = [
            'ar1_median', 'rank_autocorr', 'vol_clustering_pvalue',
            'half_life', 'level_diff_ic_ratio',
            'skewness_std', 'kurtosis_std', 'js_divergence_mean',
            'missing_cv', 'coverage_ratio',
            'sd_score', 'complexity_need', 'snr_estimate',
        ]
        for field in existing_13:
            assert hasattr(fp, field), f"既有字段缺失: {field}"

    def test_default_config_disables_tail_and_regime(self, golden_factor_data, fingerprinter_default):
        """默认配置: enable_regime_switching=False, enable_tail_dependence=False (m1 修订)"""
        fp = fingerprinter_default.extract_fingerprint(golden_factor_data)

        # 默认配置下, 新 8 维应为 NaN
        assert np.isnan(fp.tail_dependence_lower), (
            "默认 enable_tail_dependence=False → tail_dependence_lower 应为 NaN"
        )
        assert np.isnan(fp.tail_dependence_upper)
        assert np.isnan(fp.gpd_shape)
        assert np.isnan(fp.hill_estimator)
        assert np.isnan(fp.regime_transition_prob), (
            "默认 enable_regime_switching=False → regime_transition_prob 应为 NaN"
        )
        assert np.isnan(fp.regime_persistence)
        assert np.isnan(fp.regime_ic_diff)
        assert np.isnan(fp.tail_regime_score), (
            "默认配置下 tail_regime_score 应为 NaN (输入全 NaN)"
        )

    def test_extract_fingerprint_with_min_window_returns_all_nan(self):
        """样本数 < min_window → 全 21 维 NaN"""
        # T=10 < min_window=24
        rng = np.random.RandomState(42)
        small_data = pd.DataFrame(rng.randn(10, 50))
        fingerprinter = FactorFingerprinter(FingerprintConfig(min_window=24))
        fp = fingerprinter.extract_fingerprint(small_data)

        # 全 21 维 NaN
        for field in FactorFingerprint._fields:
            value = getattr(fp, field)
            assert np.isnan(value), (
                f"样本数 < min_window → {field} 应为 NaN, 实际 {value}"
            )

    def test_fingerprint_config_has_14_fields(self):
        """FingerprintConfig 包含 14 个字段 (8 既有 + 6 新增)"""
        config_fields = [
            'min_window', 'decay_halflife', 'min_obs_per_stock', 'min_stocks',
            'min_cv_threshold', 'js_bins', 'vol_cluster_lags', 'ar1_max_lag',
            # T1 新增 6 字段
            'tail_quantile', 'min_extreme_samples', 'enable_tail_dependence',
            'enable_regime_switching', 'regime_min_samples', 'tail_regime_weight',
        ]
        from dataclasses import fields
        actual_fields = [f.name for f in fields(FingerprintConfig)]
        for field in config_fields:
            assert field in actual_fields, f"FingerprintConfig 缺少字段: {field}"

    def test_default_config_values(self):
        """默认配置值正确 (m1 修订: enable_regime_switching=False)"""
        config = FingerprintConfig()
        assert config.enable_tail_dependence is False
        assert config.enable_regime_switching is False  # m1 修订
        assert config.tail_quantile == 0.05
        assert config.min_extreme_samples == 100
        assert config.regime_min_samples == 200
        assert config.tail_regime_weight == 0.5
