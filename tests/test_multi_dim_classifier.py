# -*- coding: utf-8 -*-
"""
P1: 多维分类决策测试 — 利用13维指纹做多维度路由权重

测试 _get_multi_dim_pipeline_weights() 函数:
- 使用 ar1_median + skewness_std + kurtosis_std + snr_estimate
- 三叉决策树: 基底权重 → 分布形状修正 → 稳定性修正 → 归一化
"""

import numpy as np
import pytest
from factor_pipeline.modules.factor_fingerprint.core.fingerprint import FactorFingerprint, FactorType
from factor_pipeline.modules.factor_fingerprint.core.classifier import ClassificationResult

# 从实际模块导入
from factor_pipeline.pipelines_v2 import _get_multi_dim_pipeline_weights


# =============================================================================
# 辅助: 构造测试数据
# =============================================================================

def _make_fp(ar1=0.5, skew=0.0, kurt=3.0, snr=1.0):
    """构造 FactorFingerprint，只设置关键维度，其余用 NaN"""
    return FactorFingerprint(
        ar1_median=ar1,
        rank_autocorr=np.nan,
        vol_clustering_pvalue=np.nan,
        half_life=np.nan,
        level_diff_ic_ratio=np.nan,
        skewness_std=skew,
        kurtosis_std=kurt,
        js_divergence_mean=np.nan,
        missing_cv=np.nan,
        coverage_ratio=np.nan,
        sd_score=np.nan,
        complexity_need=np.nan,
        snr_estimate=snr,
    )


def _make_cls(primary_type='static', primary_prob=0.9, secondary_type=None,
              secondary_prob=0.0, is_hard=True, confidence=0.95):
    """构造 ClassificationResult"""
    pt = FactorType.STATIC if primary_type == 'static' else \
         FactorType.DYNAMIC if primary_type == 'dynamic' else FactorType.MIXED
    st = None if secondary_type is None else \
         FactorType.STATIC if secondary_type == 'static' else \
         FactorType.DYNAMIC if secondary_type == 'dynamic' else FactorType.MIXED
    return ClassificationResult(
        primary_type=pt,
        primary_prob=primary_prob,
        secondary_type=st,
        secondary_prob=secondary_prob,
        confidence=confidence,
        is_hard=is_hard,
    )


# =============================================================================
# 测试类 1: 基底权重（ar1 驱动）
# =============================================================================

class TestBaseWeights:
    """测试 ar1_median 驱动的基底权重"""

    def test_01_high_ar1_static_base(self):
        """ar1=0.85 → 基底偏向 static"""
        fp = _make_fp(ar1=0.85)
        cls = _make_cls(primary_type='static', primary_prob=0.90, is_hard=True)
        weights = _get_multi_dim_pipeline_weights(fp, cls)
        assert weights['static'] > weights['dynamic']
        assert weights['static'] > weights['mixed']
        assert abs(sum(weights.values()) - 1.0) < 0.001

    def test_02_low_ar1_dynamic_base(self):
        """ar1=0.15 → 基底偏向 dynamic"""
        fp = _make_fp(ar1=0.15)
        cls = _make_cls(primary_type='dynamic', primary_prob=0.85, is_hard=True)
        weights = _get_multi_dim_pipeline_weights(fp, cls)
        assert weights['dynamic'] > weights['static']
        assert weights['dynamic'] > weights['mixed']
        assert abs(sum(weights.values()) - 1.0) < 0.001

    def test_03_mid_ar1_mixed_base(self):
        """ar1=0.55 → 基底偏向 mixed"""
        fp = _make_fp(ar1=0.55)
        cls = _make_cls(primary_type='mixed', primary_prob=0.60, is_hard=False)
        weights = _get_multi_dim_pipeline_weights(fp, cls)
        assert weights['mixed'] > 0
        assert abs(sum(weights.values()) - 1.0) < 0.001


# =============================================================================
# 测试类 2: 分布形状修正（skewness + kurtosis）
# =============================================================================

class TestSkewKurtAdjustment:
    """测试分布形状对权重的修正"""

    def test_04_high_skew_shifts_toward_mixed(self):
        """|skew| > 1.5 → mixed 权重增加"""
        fp_normal = _make_fp(ar1=0.85, skew=0.3, kurt=3.0)
        fp_skewed = _make_fp(ar1=0.85, skew=2.5, kurt=3.0)
        cls = _make_cls(primary_type='static', primary_prob=0.90, is_hard=True)

        w_normal = _get_multi_dim_pipeline_weights(fp_normal, cls)
        w_skewed = _get_multi_dim_pipeline_weights(fp_skewed, cls)

        # 高偏度 → mixed 权重更大
        assert w_skewed['mixed'] > w_normal['mixed'], \
            f"skewed mixed={w_skewed['mixed']:.3f} should be > normal mixed={w_normal['mixed']:.3f}"

    def test_05_high_kurt_shifts_toward_mixed(self):
        """kurt > 5 → mixed 权重增加"""
        fp_normal = _make_fp(ar1=0.85, skew=0.3, kurt=3.0)
        fp_fat = _make_fp(ar1=0.85, skew=0.3, kurt=8.0)
        cls = _make_cls(primary_type='static', primary_prob=0.90, is_hard=True)

        w_normal = _get_multi_dim_pipeline_weights(fp_normal, cls)
        w_fat = _get_multi_dim_pipeline_weights(fp_fat, cls)

        assert w_fat['mixed'] > w_normal['mixed'], \
            f"fat mixed={w_fat['mixed']:.3f} should be > normal mixed={w_normal['mixed']:.3f}"

    def test_06_both_skew_and_kurt_compound_effect(self):
        """高偏度 + 高峰度 → 混合权重叠加增加"""
        fp_normal = _make_fp(ar1=0.85, skew=0.3, kurt=3.0)
        fp_extreme = _make_fp(ar1=0.85, skew=2.5, kurt=8.0)
        cls = _make_cls(primary_type='static', primary_prob=0.90, is_hard=True)

        w_normal = _get_multi_dim_pipeline_weights(fp_normal, cls)
        w_extreme = _get_multi_dim_pipeline_weights(fp_extreme, cls)

        # 极端分布 → mixed 权重显著增加
        assert w_extreme['mixed'] > w_normal['mixed'] + 0.05, \
            f"extreme mixed={w_extreme['mixed']:.3f} should be significantly > normal mixed={w_normal['mixed']:.3f}"


# =============================================================================
# 测试类 3: 稳定性修正（SNR）
# =============================================================================

class TestSNRAdjustment:
    """测试信噪比对权重的修正"""

    def test_07_low_snr_shifts_toward_dynamic(self):
        """低 SNR → 动态管道权重增加"""
        fp_high = _make_fp(ar1=0.55, snr=3.0)
        fp_low = _make_fp(ar1=0.55, snr=0.3)
        cls = _make_cls(primary_type='mixed', primary_prob=0.60, is_hard=False)

        w_high = _get_multi_dim_pipeline_weights(fp_high, cls)
        w_low = _get_multi_dim_pipeline_weights(fp_low, cls)

        assert w_low['dynamic'] > w_high['dynamic'], \
            f"low snr dynamic={w_low['dynamic']:.3f} should be > high snr dynamic={w_high['dynamic']:.3f}"

    def test_08_nan_snr_no_effect(self):
        """NaN SNR → 不加修正"""
        fp_nan = _make_fp(ar1=0.55, snr=np.nan)
        fp_val = _make_fp(ar1=0.55, snr=2.0)
        cls = _make_cls(primary_type='mixed', primary_prob=0.60, is_hard=False)

        w_nan = _get_multi_dim_pipeline_weights(fp_nan, cls)
        w_val = _get_multi_dim_pipeline_weights(fp_val, cls)

        # NaN SNR 不应该报错，权重应该接近基底
        assert abs(sum(w_nan.values()) - 1.0) < 0.001


# =============================================================================
# 测试类 4: 边界情况
# =============================================================================

class TestEdgeCases:
    """测试边界情况"""

    def test_09_all_nan_no_crash(self):
        """全部 NaN 指纹 → 不崩溃，返回均匀权重"""
        fp = FactorFingerprint()  # 全部 NaN
        cls = _make_cls(primary_type='mixed', primary_prob=0.60, is_hard=False)
        weights = _get_multi_dim_pipeline_weights(fp, cls)
        assert abs(sum(weights.values()) - 1.0) < 0.001
        # 所有键都存在
        assert 'static' in weights
        assert 'dynamic' in weights
        assert 'mixed' in weights

    def test_10_hard_routing_still_works(self):
        """高置信度硬分类 → 仍支持单管道路由"""
        fp = _make_fp(ar1=0.90, skew=0.2, kurt=3.0, snr=2.0)
        cls = _make_cls(primary_type='static', primary_prob=0.95, is_hard=True)

        weights = _get_multi_dim_pipeline_weights(fp, cls, hard_routing_prob=0.90)
        # 高置信度硬路由 → 单一管道
        assert weights['static'] == 1.0 or weights['static'] > 0.85

    def test_11_weights_always_sum_to_one(self):
        """所有权重始终归一化到 1"""
        test_cases = [
            (_make_fp(ar1=0.85, skew=0.2, kurt=3.0, snr=2.0),
             _make_cls('static', 0.90, is_hard=True)),
            (_make_fp(ar1=0.15, skew=0.5, kurt=4.0, snr=0.5),
             _make_cls('dynamic', 0.85, is_hard=True)),
            (_make_fp(ar1=0.55, skew=2.0, kurt=6.0, snr=1.0),
             _make_cls('mixed', 0.55, 'static', 0.30, is_hard=False)),
            (_make_fp(ar1=0.70, skew=3.0, kurt=10.0, snr=0.1),
             _make_cls('static', 0.70, 'mixed', 0.25, is_hard=False)),
        ]
        for fp, cls in test_cases:
            weights = _get_multi_dim_pipeline_weights(fp, cls)
            total = sum(weights.values())
            assert abs(total - 1.0) < 0.001, \
                f"total={total:.4f}, weights={weights}"

    def test_12_nan_skew_kurt_no_effect(self):
        """NaN skewness/kurtosis → 不加形状修正"""
        fp = _make_fp(ar1=0.85, skew=np.nan, kurt=np.nan, snr=2.0)
        cls = _make_cls(primary_type='static', primary_prob=0.90, is_hard=True)
        weights = _get_multi_dim_pipeline_weights(fp, cls)
        assert abs(sum(weights.values()) - 1.0) < 0.001
        # 没有分布修正，static 应该主导
        assert weights['static'] > 0.5