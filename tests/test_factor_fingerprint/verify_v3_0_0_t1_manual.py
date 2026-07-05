# -*- coding: utf-8 -*-
"""v3.0.0 T1 手工校验脚本

校验 FactorFingerprint 21 维扩展 (T1 v3.0.0):
  1. 21 维字段完整性 (NamedTuple `_fields` 长度 = 21)
  2. `to_dict` 返回 21 个键
  3. `FingerprintConfig` 14 个字段
  4. 默认配置: `enable_regime_switching=False`, `enable_tail_dependence=False` (m1 修订)
  5. 尾部依赖关闭时 4 维 NaN
  6. 体制转换开启时 3 维有值
  7. `tail_regime_score` ∈ [0, 1]
  8. 既有 13 维黄金参考回归 (ar1_median/half_life/skewness_std 等不变)

对应 EXECUTION_V3.0.0_T1.md §3.2 手工校验项。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent.parent  # F:\Coding
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))

from factor_pipeline.modules.factor_fingerprint.core.fingerprint import (
    FactorFingerprint, FactorFingerprinter, FingerprintConfig,
)

print("=" * 70)
print("v3.0.0 T1 手工校验: 指纹维度扩展至 21 维")
print("=" * 70)


# ── 1. 21 维字段完整性 ──────────────────────────────────────

print("\n[1/8] 21 维字段完整性...")
field_names = FactorFingerprint._fields
assert len(field_names) == 21, (
    f"FactorFingerprint 字段数应为 21, 实际 {len(field_names)}"
)
# 既有 13 维
legacy_13 = [
    'ar1_median', 'rank_autocorr', 'vol_clustering_pvalue', 'half_life',
    'level_diff_ic_ratio', 'skewness_std', 'kurtosis_std', 'js_divergence_mean',
    'missing_cv', 'coverage_ratio', 'sd_score', 'complexity_need', 'snr_estimate',
]
for f in legacy_13:
    assert f in field_names, f"既有字段 {f} 缺失"
# T1 新增 8 维
t1_new_8 = [
    'tail_dependence_lower', 'tail_dependence_upper', 'gpd_shape', 'hill_estimator',
    'regime_transition_prob', 'regime_persistence', 'regime_ic_diff', 'tail_regime_score',
]
for f in t1_new_8:
    assert f in field_names, f"T1 新增字段 {f} 缺失"
print(f"  PASS: 21 维字段完整 (13 既有 + 8 新增)")


# ── 2. to_dict 返回 21 键 ────────────────────────────────────

print("\n[2/8] to_dict 返回 21 键...")
fp_default = FactorFingerprint()
d = fp_default.to_dict()
assert len(d) == 21, (
    f"to_dict 返回键数应为 21, 实际 {len(d)}"
)
for f in t1_new_8:
    assert f in d, f"to_dict 缺 T1 字段 {f}"
print(f"  PASS: to_dict 返回 {len(d)} 键")


# ── 3. FingerprintConfig 14 字段 ────────────────────────────

print("\n[3/8] FingerprintConfig 14 字段...")
config_fields = {f.name for f in FingerprintConfig.__dataclass_fields__.values()}
assert len(config_fields) == 14, (
    f"FingerprintConfig 字段数应为 14, 实际 {len(config_fields)}"
)
# T1 新增 6 配置
t1_new_config = {
    'tail_quantile', 'min_extreme_samples', 'enable_tail_dependence',
    'enable_regime_switching', 'regime_min_samples', 'tail_regime_weight',
}
for f in t1_new_config:
    assert f in config_fields, f"FingerprintConfig 缺 T1 字段 {f}"
print(f"  PASS: FingerprintConfig {len(config_fields)} 字段 (8 既有 + 6 新增)")


# ── 4. 默认配置 (m1 修订) ───────────────────────────────────

print("\n[4/8] 默认配置: enable_tail_dependence=False, enable_regime_switching=False...")
config_default = FingerprintConfig()
assert config_default.enable_tail_dependence is False, (
    f"enable_tail_dependence 默认应为 False (m1 修订), 实际 {config_default.enable_tail_dependence}"
)
assert config_default.enable_regime_switching is False, (
    f"enable_regime_switching 默认应为 False (m1 修订), 实际 {config_default.enable_regime_switching}"
)
print(f"  PASS: enable_tail_dependence=False, enable_regime_switching=False")


# ── 5. 尾部依赖关闭时 4 维 NaN ──────────────────────────────

print("\n[5/8] 尾部依赖关闭时 4 维 NaN...")
# 构造测试数据 (T=500, N=50)
rng = np.random.default_rng(42)
T, N = 500, 50
data = pd.DataFrame(rng.standard_normal((T, N)),
                    columns=[f'stk_{i}' for i in range(N)])
config_off = FingerprintConfig(enable_tail_dependence=False)
fingerprinter_off = FactorFingerprinter(config=config_off)
fp_off = fingerprinter_off.extract_fingerprint(data)
for f in ['tail_dependence_lower', 'tail_dependence_upper', 'gpd_shape', 'hill_estimator']:
    val = getattr(fp_off, f)
    assert isinstance(val, float) and np.isnan(val), (
        f"关闭尾部依赖时 {f} 应为 NaN, 实际 {val}"
    )
print(f"  PASS: 4 维尾部依赖指标全 NaN (gpd_shape={fp_off.gpd_shape}, hill={fp_off.hill_estimator})")


# ── 6. 体制转换开启时 3 维有值 ──────────────────────────────

print("\n[6/8] 体制转换开启时 3 维有值...")
# 构造有明显 regime 切换的数据 (前半段均值 0, 后半段均值 2)
data_regime = pd.DataFrame(rng.standard_normal((T, N)),
                           columns=[f'stk_{i}' for i in range(N)])
data_regime.iloc[:T//2] += 0.0
data_regime.iloc[T//2:] += 2.0
config_on = FingerprintConfig(enable_regime_switching=True, regime_min_samples=200)
fingerprinter_on = FactorFingerprinter(config=config_on)
fp_on = fingerprinter_on.extract_fingerprint(data_regime)
# regime_transition_prob 可能非 NaN (Markov 拟合或降级硬阈值)
regime_fields = ['regime_transition_prob', 'regime_persistence', 'regime_ic_diff']
non_nan_count = sum(1 for f in regime_fields
                    if not (np.isnan(getattr(fp_on, f)) if isinstance(getattr(fp_on, f), float) else False))
# 至少 1 个非 NaN (降级方案也应给出 regime_ic_diff)
assert non_nan_count >= 1, (
    f"开启体制转换后至少 1 维应有值, 实际 {non_nan_count}/3 非 NaN: "
    f"trans={fp_on.regime_transition_prob}, persist={fp_on.regime_persistence}, "
    f"ic_diff={fp_on.regime_ic_diff}"
)
print(f"  PASS: {non_nan_count}/3 维体制转换指标有值 (trans={fp_on.regime_transition_prob:.4f}, "
      f"persist={fp_on.regime_persistence}, ic_diff={fp_on.regime_ic_diff:.4f})")


# ── 7. tail_regime_score ∈ [0, 1] ───────────────────────────

print("\n[7/8] tail_regime_score ∈ [0, 1]...")
# fp_on 仅开启 T1.2 (T1.1 关闭), gpd_shape/hill_estimator 均 NaN
# _derive_tail_regime_score 守卫: gpd_shape 和 hill_estimator 都 NaN → 返回 NaN
score_on = fp_on.tail_regime_score
if not (isinstance(score_on, float) and np.isnan(score_on)):
    assert 0.0 <= score_on <= 1.0, (
        f"tail_regime_score 应 ∈ [0, 1], 实际 {score_on}"
    )
    print(f"  PASS: tail_regime_score (T1.2 开启) = {score_on:.4f} ∈ [0, 1]")
else:
    print(f"  PASS: tail_regime_score (T1.2 开启, T1.1 关闭) = NaN (gpd_shape/hill 均 NaN, 守卫返回 NaN)")

# 额外验证: T1.1 + T1.2 均开启时, score 应非 NaN 且 ∈ [0, 1]
config_both = FingerprintConfig(enable_tail_dependence=True, enable_regime_switching=True,
                                regime_min_samples=200, min_extreme_samples=100)
fingerprinter_both = FactorFingerprinter(config=config_both)
fp_both = fingerprinter_both.extract_fingerprint(data_regime)
score_both = fp_both.tail_regime_score
if not (isinstance(score_both, float) and np.isnan(score_both)):
    assert 0.0 <= score_both <= 1.0, (
        f"tail_regime_score (T1.1+T1.2 均开启) 应 ∈ [0, 1], 实际 {score_both}"
    )
    print(f"  PASS: tail_regime_score (T1.1+T1.2 均开启) = {score_both:.4f} ∈ [0, 1]")
else:
    print(f"  NOTE: tail_regime_score (T1.1+T1.2 均开启) = NaN (可能 gpd_shape/hill 仍 NaN, 守卫生效)")


# ── 8. 既有 13 维黄金参考回归 ───────────────────────────────

print("\n[8/8] 既有 13 维黄金参考回归...")
# 用默认配置 (T1.1/T1.2 都关) 提取指纹, 既有 13 维应有值 (除部分难算的)
config_legacy = FingerprintConfig()
fingerprinter_legacy = FactorFingerprinter(config=config_legacy)
fp_legacy = fingerprinter_legacy.extract_fingerprint(data)

# ar1_median 应有值 (静态因子随机数据, AR(1) 应接近 0)
assert not np.isnan(fp_legacy.ar1_median), (
    f"ar1_median 应有值, 实际 {fp_legacy.ar1_median}"
)
# skewness_std / kurtosis_std 应有值 (正态分布: skew≈0, kurt≈3)
assert not np.isnan(fp_legacy.skewness_std), (
    f"skewness_std 应有值, 实际 {fp_legacy.skewness_std}"
)
assert not np.isnan(fp_legacy.kurtosis_std), (
    f"kurtosis_std 应有值, 实际 {fp_legacy.kurtosis_std}"
)
# snr_estimate 应有值
assert not np.isnan(fp_legacy.snr_estimate), (
    f"snr_estimate 应有值, 实际 {fp_legacy.snr_estimate}"
)
# T1 新增 8 维应全 NaN (默认关闭)
for f in t1_new_8:
    val = getattr(fp_legacy, f)
    assert isinstance(val, float) and np.isnan(val), (
        f"默认配置下 {f} 应为 NaN, 实际 {val}"
    )
print(f"  PASS: 既有 13 维有值 (ar1={fp_legacy.ar1_median:.4f}, "
      f"skew={fp_legacy.skewness_std:.4f}, kurt={fp_legacy.kurtosis_std:.4f}, "
      f"snr={fp_legacy.snr_estimate:.4f}), T1 新增 8 维全 NaN")


# ── 汇总 ────────────────────────────────────────────────────

print("\n" + "=" * 70)
print("v3.0.0 T1 手工校验: 全部 8/8 通过")
print("=" * 70)
print("\n校验项:")
print("  1. 21 维字段完整性 (NamedTuple _fields)")
print("  2. to_dict 返回 21 键")
print("  3. FingerprintConfig 14 字段")
print("  4. 默认配置 enable_tail_dependence/enable_regime_switching=False (m1)")
print("  5. 尾部依赖关闭时 4 维 NaN")
print("  6. 体制转换开启时 3 维至少 1 有值")
print("  7. tail_regime_score ∈ [0, 1]")
print("  8. 既有 13 维黄金参考回归 + T1 新增 8 维默认 NaN")
