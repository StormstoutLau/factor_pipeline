# -*- coding: utf-8 -*-
"""v3.0.0 T4 手工校验脚本

校验 _ks_migration_significance 的 BH-FDR 实现 (T4 v3.0.0):
  1. BH 黄金参考: p=[0.01, 0.04, 0.03, 0.20, 0.50], K=5
     → p_adj=[0.05, 0.0667, 0.0667, 0.25, 0.50], min_p_adj=0.05
  2. BH 公式 vs 手工计算 (随机数据, 多个 K 值)
  3. Bonferroni 向后兼容 (显式 opt-in 旧路径)
  4. None 路径无校正
  5. 三路径字段隔离 (无字段污染)
  6. 保护路径不破坏 (空数据/无公共列/数据不足)
  7. BH 检测力 >= Bonferroni (10 列, BH 3 vs Bonferroni 1)
  8. 参数校验 (非法 correction_method 抛 ValueError)

对应 EXECUTION_V3.0.0_T4.md §3.4 T4-V1 手工校验项。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent.parent  # F:\Coding
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))

from factor_pipeline.pipelines_v2 import _ks_migration_significance
import factor_pipeline.pipelines_v2 as pv2


print("=" * 70)
print("v3.0.0 T4 手工校验: BH-FDR 替代 Bonferroni")
print("=" * 70)


# ── 工具函数 ──────────────────────────────────────────────────

def _manual_bh(p_values):
    """手工 BH 校正, 返回 p_adj 数组"""
    p_arr = np.asarray(p_values, dtype=float)
    K = len(p_arr)
    order = np.argsort(p_arr)
    p_adj = np.empty_like(p_arr)
    prev = 1.0
    for i in range(K - 1, -1, -1):
        rank = i + 1
        idx = order[i]
        bh = p_arr[idx] * K / rank
        prev = min(prev, bh)
        p_adj[idx] = min(prev, 1.0)
    return p_adj


def _run_with_p_values(target_p, correction_method='benjamini_hochberg'):
    """通过 monkeypatch scipy.stats.ks_2samp 返回指定 p 值序列"""
    call_state = {'idx': 0}
    def fake_ks_2samp(a, b):
        p = target_p[call_state['idx'] % len(target_p)]
        call_state['idx'] += 1
        return 0.5, float(p)
    original = pv2._scipy_stats.ks_2samp
    pv2._scipy_stats.ks_2samp = fake_ks_2samp
    try:
        hist = pd.DataFrame(
            np.random.RandomState(42).randn(100, len(target_p)),
            columns=[f'f{i}' for i in range(len(target_p))]
        )
        recent = pd.DataFrame(
            np.random.RandomState(43).randn(100, len(target_p)),
            columns=[f'f{i}' for i in range(len(target_p))]
        )
        return _ks_migration_significance(
            hist, recent, alpha=0.05, correction_method=correction_method
        )
    finally:
        pv2._scipy_stats.ks_2samp = original


# ── 校验 1: BH 黄金参考 ──────────────────────────────────────
print("\n[1] BH 黄金参考校验")
target_p = [0.01, 0.04, 0.03, 0.20, 0.50]
is_sig, min_p, details = _run_with_p_values(target_p, 'benjamini_hochberg')

expected_p_adj = [0.05, 0.0667, 0.0667, 0.25, 0.50]
actual_p_adj = [c['p_value_adjusted'] for c in details['per_column']]
np.testing.assert_allclose(actual_p_adj, expected_p_adj, atol=1e-4)
np.testing.assert_allclose(details['min_p_value_adjusted'], 0.05, atol=1e-10)
np.testing.assert_allclose(min_p, 0.01, atol=1e-10)
assert is_sig is False, f"is_sig 期望 False (0.05 < 0.05 不成立), 实际 {is_sig}"
print(f"  p_adj={actual_p_adj} ✓")
print(f"  min_p_adj={details['min_p_value_adjusted']:.4f} ✓")
print(f"  is_sig={is_sig} ✓")


# ── 校验 2: BH 公式 vs 手工计算 (随机数据) ────────────────────
print("\n[2] BH 公式 vs 手工计算 (多个 K 值)")
for K in [1, 3, 5, 10, 20, 50]:
    np.random.seed(K)
    target_p = list(np.random.uniform(0.001, 0.5, K))
    is_sig, min_p, details = _run_with_p_values(target_p, 'benjamini_hochberg')

    prog_p_values = [c['p_value'] for c in details['per_column']]
    expected_p_adj = _manual_bh(prog_p_values)
    actual_p_adj = [c['p_value_adjusted'] for c in details['per_column']]
    np.testing.assert_allclose(actual_p_adj, expected_p_adj, atol=1e-10)
    np.testing.assert_allclose(
        details['min_p_value_adjusted'], float(np.min(expected_p_adj)), atol=1e-10
    )
    print(f"  K={K}: min_p_adj={details['min_p_value_adjusted']:.4f} ✓")


# ── 校验 3: Bonferroni 向后兼容 ───────────────────────────────
print("\n[3] Bonferroni 向后兼容校验")
target_p = [0.01, 0.04, 0.03, 0.20, 0.50]
is_sig, min_p, details = _run_with_p_values(target_p, 'bonferroni')

assert 'alpha_corrected' in details
assert 'bonferroni_correction' in details
assert details['bonferroni_correction'] is True
assert abs(details['alpha_corrected'] - 0.01) < 1e-10  # 0.05/5
assert 'min_p_value_adjusted' not in details
assert 'correction_method' not in details
for c in details['per_column']:
    assert 'p_value_adjusted' not in c
print(f"  alpha_corrected={details['alpha_corrected']:.4f} ✓")
print(f"  bonferroni_correction={details['bonferroni_correction']} ✓")
print(f"  BH 字段未污染 Bonferroni 路径 ✓")


# ── 校验 4: None 路径无校正 ───────────────────────────────────
print("\n[4] None 路径无校正校验")
target_p = [0.01, 0.04, 0.03, 0.20, 0.50]
is_sig, min_p, details = _run_with_p_values(target_p, 'none')

assert is_sig is True  # min_p=0.01 < alpha=0.05
assert details['correction_method'] == 'none'
assert 'alpha_corrected' not in details
assert 'min_p_value_adjusted' not in details
assert 'bonferroni_correction' not in details
for c in details['per_column']:
    assert 'p_value_adjusted' not in c
print(f"  is_sig={is_sig} (min_p=0.01 < alpha=0.05) ✓")
print(f"  correction_method='none' ✓")


# ── 校验 5: 三路径字段隔离 ────────────────────────────────────
print("\n[5] 三路径字段隔离校验")
target_p = [0.01, 0.04, 0.03, 0.20, 0.50]
for method in ['benjamini_hochberg', 'bonferroni', 'none']:
    _, _, details = _run_with_p_values(target_p, method)
    if method == 'benjamini_hochberg':
        assert 'min_p_value_adjusted' in details
        assert 'correction_method' in details
        assert 'alpha_corrected' not in details
        assert 'bonferroni_correction' not in details
    elif method == 'bonferroni':
        assert 'alpha_corrected' in details
        assert 'bonferroni_correction' in details
        assert 'min_p_value_adjusted' not in details
        assert 'correction_method' not in details
    else:  # none
        assert 'correction_method' in details
        assert 'alpha_corrected' not in details
        assert 'min_p_value_adjusted' not in details
        assert 'bonferroni_correction' not in details
    print(f"  {method}: 字段隔离正确 ✓")


# ── 校验 6: 保护路径不破坏 ────────────────────────────────────
print("\n[6] 保护路径不破坏校验")
# 空数据
empty = pd.DataFrame()
is_sig, min_p, details = _ks_migration_significance(empty, empty, alpha=0.05)
assert is_sig is False
assert min_p == 1.0
assert details['warning'] == 'empty data'
print("  空数据: ✓")

# 无公共列
hist = pd.DataFrame(np.random.randn(100, 3), columns=['a', 'b', 'c'])
recent = pd.DataFrame(np.random.randn(100, 3), columns=['x', 'y', 'z'])
is_sig, min_p, details = _ks_migration_significance(hist, recent, alpha=0.05)
assert is_sig is False
assert min_p == 1.0
assert details['warning'] == 'no common columns'
print("  无公共列: ✓")

# 数据不足
hist = pd.DataFrame(np.random.randn(3, 2), columns=['a', 'b'])
recent = pd.DataFrame(np.random.randn(3, 2), columns=['a', 'b'])
is_sig, min_p, details = _ks_migration_significance(hist, recent, alpha=0.05)
assert is_sig is False
assert min_p == 1.0
assert details['warning'] == 'insufficient data'
print("  数据不足: ✓")


# ── 校验 7: BH 检测力 >= Bonferroni ───────────────────────────
print("\n[7] BH 检测力 >= Bonferroni 校验")
target_p = [0.001, 0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.10, 0.30, 0.50]
_, _, details_bonf = _run_with_p_values(target_p, 'bonferroni')
bonf_sig_count = sum(
    1 for c in details_bonf['per_column']
    if c['p_value'] < details_bonf['alpha_corrected']
)
_, _, details_bh = _run_with_p_values(target_p, 'benjamini_hochberg')
bh_sig_count = sum(
    1 for c in details_bh['per_column']
    if c['p_value_adjusted'] < 0.05
)
assert bonf_sig_count == 1, f"Bonferroni 期望 1 个显著, 实际 {bonf_sig_count}"
assert bh_sig_count == 3, f"BH 期望 3 个显著, 实际 {bh_sig_count}"
assert bh_sig_count >= bonf_sig_count
print(f"  Bonferroni: {bonf_sig_count} 个显著 ✓")
print(f"  BH: {bh_sig_count} 个显著 ✓")
print(f"  BH 检测数 >= Bonferroni ✓")


# ── 校验 8: 参数校验 ──────────────────────────────────────────
print("\n[8] 参数校验")
hist = pd.DataFrame(np.random.randn(100, 5))
recent = pd.DataFrame(np.random.randn(100, 5))
# 非法字符串应抛 ValueError
invalid_methods = ['bh', 'fdr', 'Bonferroni', '', 'None', 'holm', 'BY']
for invalid_method in invalid_methods:
    try:
        _ks_migration_significance(
            hist, recent, alpha=0.05, correction_method=invalid_method
        )
        raise AssertionError(
            f"期望 ValueError (非法 correction_method={invalid_method!r})"
        )
    except (ValueError, TypeError) as e:
        print(f"  非法值 {invalid_method!r}: 抛出 {type(e).__name__} ✓")
# 合法值不抛异常
for valid_method in ['benjamini_hochberg', 'bonferroni', 'none']:
    _ks_migration_significance(
        hist, recent, alpha=0.05, correction_method=valid_method
    )
print(f"  合法值 'benjamini_hochberg'/'bonferroni'/'none': 不抛异常 ✓")


print("\n" + "=" * 70)
print("v3.0.0 T4 手工校验全部通过: 8/8")
print("=" * 70)
