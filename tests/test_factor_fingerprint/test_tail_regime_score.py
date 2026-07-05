# -*- coding: utf-8 -*-
"""T1 E1-T5: tail_regime_score 综合得分测试

测试目标:
- _derive_tail_regime_score (M2 修订: 简化双分量加权公式)

公式 (M2 修订):
    tail_severity = np.clip((|gpd_shape| + |hill_estimator|) / 2, 0, 1)
    regime_instability = np.clip(regime_trans_prob / 0.5, 0, 1)
    score = tail_regime_weight * tail_severity + (1 - tail_regime_weight) * regime_instability

当前状态 (Red): _derive_tail_regime_score 方法不存在 → 全部失败
Green 后: 方法实现, 全部通过
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


# =============================================================================
# E1-T5: tail_regime_score 综合得分测试
# =============================================================================

class TestTailRegimeScore:
    """E1-T5: tail_regime_score 综合得分测试 (M2 修订: 双分量加权)"""

    def test_all_nan_inputs_returns_nan(self):
        """所有输入 NaN → tail_regime_score=NaN"""
        fp = FactorFingerprint(
            # 既有 13 维 (填 0 避免干扰)
            ar1_median=0.5, rank_autocorr=0.3, vol_clustering_pvalue=0.5,
            half_life=5.0, level_diff_ic_ratio=1.0,
            skewness_std=0.5, kurtosis_std=3.0, js_divergence_mean=0.1,
            missing_cv=0.1, coverage_ratio=0.95,
            sd_score=0.5, complexity_need=0.5, snr_estimate=1.0,
            # T1 新 8 维全 NaN
            tail_dependence_lower=np.nan,
            tail_dependence_upper=np.nan,
            gpd_shape=np.nan,
            hill_estimator=np.nan,
            regime_transition_prob=np.nan,
            regime_persistence=np.nan,
            regime_ic_diff=np.nan,
            tail_regime_score=np.nan,  # 占位, 实际由 _derive_tail_regime_score 计算
        )
        # 直接调用 _derive_tail_regime_score
        fingerprinter = FactorFingerprinter(FingerprintConfig())
        score = fingerprinter._derive_tail_regime_score(
            tail_lower=np.nan, tail_upper=np.nan,
            gpd_shape=np.nan, hill_estimator=np.nan,
            regime_trans_prob=np.nan, regime_persistence=np.nan,
            regime_ic_diff=np.nan,
        )
        assert np.isnan(score), "所有输入 NaN → tail_regime_score 应为 NaN"

    def test_normal_inputs_returns_in_01(self):
        """正常输入 → tail_regime_score ∈ [0, 1]"""
        fingerprinter = FactorFingerprinter(FingerprintConfig())
        score = fingerprinter._derive_tail_regime_score(
            tail_lower=0.1, tail_upper=0.2,
            gpd_shape=0.3, hill_estimator=0.4,
            regime_trans_prob=0.1, regime_persistence=10.0,
            regime_ic_diff=0.05,
        )
        assert not np.isnan(score), "正常输入 → tail_regime_score 应有值"
        assert 0 <= score <= 1, (
            f"tail_regime_score 应 ∈ [0,1], 实际 {score}"
        )

    def test_heavy_tail_high_score(self):
        """重尾 + 体制不稳定 → tail_regime_score > 0.5"""
        fingerprinter = FactorFingerprinter(FingerprintConfig(tail_regime_weight=0.5))
        score = fingerprinter._derive_tail_regime_score(
            tail_lower=0.3, tail_upper=0.3,
            gpd_shape=0.8, hill_estimator=0.8,  # 重尾
            regime_trans_prob=0.4, regime_persistence=2.5,  # 体制不稳定
            regime_ic_diff=0.1,
        )
        assert not np.isnan(score)
        assert score > 0.5, (
            f"重尾 + 体制不稳定 → tail_regime_score > 0.5, 实际 {score}"
        )

    def test_light_tail_low_score(self):
        """轻尾 + 体制稳定 → tail_regime_score < 0.5"""
        fingerprinter = FactorFingerprinter(FingerprintConfig(tail_regime_weight=0.5))
        score = fingerprinter._derive_tail_regime_score(
            tail_lower=0.01, tail_upper=0.01,
            gpd_shape=0.05, hill_estimator=0.05,  # 轻尾
            regime_trans_prob=0.02, regime_persistence=50.0,  # 体制稳定
            regime_ic_diff=0.01,
        )
        assert not np.isnan(score)
        assert score < 0.5, (
            f"轻尾 + 体制稳定 → tail_regime_score < 0.5, 实际 {score}"
        )

    def test_tail_regime_weight_controls_balance(self):
        """tail_regime_weight 控制尾部与体制的权重平衡"""
        # weight=1.0: 完全用尾部
        fp_full_tail = FactorFingerprinter(FingerprintConfig(tail_regime_weight=1.0))
        score_full_tail = fp_full_tail._derive_tail_regime_score(
            tail_lower=0.3, tail_upper=0.3,
            gpd_shape=0.8, hill_estimator=0.8,  # 重尾
            regime_trans_prob=0.02, regime_persistence=50.0,  # 体制稳定 (但被忽略)
            regime_ic_diff=0.01,
        )

        # weight=0.0: 完全用体制
        fp_full_regime = FactorFingerprinter(FingerprintConfig(tail_regime_weight=0.0))
        score_full_regime = fp_full_regime._derive_tail_regime_score(
            tail_lower=0.3, tail_upper=0.3,
            gpd_shape=0.8, hill_estimator=0.8,  # 重尾 (但被忽略)
            regime_trans_prob=0.4, regime_persistence=2.5,  # 体制不稳定
            regime_ic_diff=0.1,
        )

        # weight=1.0 重尾 → 高分 (因 tail_severity 高)
        assert score_full_tail > 0.5, (
            f"weight=1.0 + 重尾 → 高分, 实际 {score_full_tail}"
        )
        # weight=0.0 体制不稳定 → 高分 (因 regime_instability 高)
        assert score_full_regime > 0.5, (
            f"weight=0.0 + 体制不稳定 → 高分, 实际 {score_full_regime}"
        )

    def test_partial_nan_uses_05_default(self):
        """部分输入 NaN → 该分量用 0.5 中性值"""
        fingerprinter = FactorFingerprinter(FingerprintConfig(tail_regime_weight=0.5))
        # gpd_shape 有值, regime_trans_prob 为 NaN
        score = fingerprinter._derive_tail_regime_score(
            tail_lower=np.nan, tail_upper=np.nan,
            gpd_shape=0.8, hill_estimator=0.8,  # 重尾
            regime_trans_prob=np.nan,  # NaN → regime_instability 用 0.5
            regime_persistence=np.nan,
            regime_ic_diff=np.nan,
        )
        # tail_severity = (0.8 + 0.8) / 2 = 0.8, regime_instability = 0.5
        # score = 0.5 * 0.8 + 0.5 * 0.5 = 0.65
        assert not np.isnan(score)
        assert abs(score - 0.65) < 0.01, (
            f"部分 NaN → score = 0.5*0.8 + 0.5*0.5 = 0.65, 实际 {score}"
        )
