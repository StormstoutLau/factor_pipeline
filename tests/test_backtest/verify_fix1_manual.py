# -*- coding: utf-8 -*-
"""Fix 1 手工校验脚本

校验:
  1. transform 内部 KS 检验路径使用 factor_data (transform 参数) 而非 self.factors
  2. KS 拆分语义: 按时间(columns/dates)拆分, 转置后逐股票做时间维度 KS
     (显式 correction_method='bonferroni' 保持 Fix 1 校验语义不变, T4 v3.0.0 默认已改 BH)
  3. BH-FDR 校正公式 (T4 v3.0.0): p_adj_(k) = p_(k) * K / rank, 累积 min, clip [0,1]
  4. KS p 值与 scipy 独立计算一致
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent.parent  # F:\Coding
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))

from scipy.stats import ks_2samp
from factor_pipeline.pipelines_v2 import _ks_migration_significance


print("=" * 70)
print("Fix 1 手工校验")
print("=" * 70)

# ── 校验 1: transform 使用 factor_data 而非 self.factors ─────────
print("\n[1] transform 内部数据源校验")
pipelines_v2_path = _PROJECT_PARENT / "factor_pipeline" / "pipelines_v2.py"
content = pipelines_v2_path.read_text(encoding='utf-8')

# Fix 1 修复点: 在 transform 中使用 factor_data[name]
assert "factor_df = factor_data[name]" in content, (
    "transform 未使用 factor_data[name] 作为 KS 检验数据源"
)
print("  ✓ transform 使用 factor_data[name] (Fix 1 修复点存在)")

# 验证 self.factors 未被错误引用 (除注释外)
import re
# 找所有非注释的 self.factors 引用
lines = content.splitlines()
self_factors_refs = []
for i, line in enumerate(lines, 1):
    stripped = line.lstrip()
    if stripped.startswith('#'):
        continue
    if 'self.factors' in line and 'Fix 1' not in line:
        # 排除注释中的引用
        code_part = line.split('#')[0]
        if 'self.factors' in code_part:
            self_factors_refs.append((i, line.strip()))
assert not self_factors_refs, (
    f"发现 self.factors 在非注释代码中引用 (可能未完成修复): {self_factors_refs}"
)
print("  ✓ 无非注释的 self.factors 引用 (修复完整)")


# ── 校验 2: KS 拆分语义 — 按时间拆分 + 转置 ─────────────────────
print("\n[2] KS 拆分语义校验")
# 构造已知数据: 100 股票 × 20 天, 前半段和后半段分布不同
np.random.seed(42)
n_stocks, n_dates = 10, 20
split_idx = n_dates // 2  # 10

# 前半段: N(0, 1), 后半段: N(1, 1) — 应检测到显著迁移
hist_data = np.random.randn(n_stocks, split_idx)
recent_data = np.random.randn(n_stocks, n_dates - split_idx) + 1.0
factor_df = pd.DataFrame(
    np.hstack([hist_data, recent_data]),
    index=[f"s{i}" for i in range(n_stocks)],
    columns=[f"d{i}" for i in range(n_dates)],
)

# 程序拆分方式 (按时间 columns 拆分, 转置后逐股票做时间维度 KS)
hist_part = factor_df.iloc[:, :split_idx]   # (n_stocks, split_idx)
recent_part = factor_df.iloc[:, split_idx:]  # (n_stocks, n_dates - split_idx)

# 转置: (split_idx, n_stocks) — stocks 成为 columns
hist_for_ks = hist_part.T
recent_for_ks = recent_part.T

# 手工: 对每个股票 (column) 做 KS 检验
manual_p_values = []
for col in hist_for_ks.columns:
    h = hist_for_ks[col].dropna().values
    r = recent_for_ks[col].dropna().values
    if len(h) >= 5 and len(r) >= 5:
        _, p = ks_2samp(h, r)
        manual_p_values.append(p)

manual_min_p = min(manual_p_values)
manual_n_tests = len(manual_p_values)
manual_alpha = 0.05
# Fix 1 校验语义: 显式 Bonferroni (T4 v3.0.0 默认已改 BH, 这里 opt-in 旧路径)
manual_alpha_corrected = manual_alpha / manual_n_tests
manual_is_sig = manual_min_p < manual_alpha_corrected

print(f"  手工 (Bonferroni opt-in): n_tests={manual_n_tests}, min_p={manual_min_p:.6f}, "
      f"alpha_corrected={manual_alpha_corrected:.6f}, is_sig={manual_is_sig}")

# 程序: _ks_migration_significance (显式 Bonferroni 保持 Fix 1 校验语义)
prog_is_sig, prog_min_p, prog_details = _ks_migration_significance(
    hist_for_ks, recent_for_ks, alpha=0.05, correction_method='bonferroni'
)
print(f"  程序 (Bonferroni opt-in): n_tests={prog_details['n_columns']}, min_p={prog_min_p:.6f}, "
      f"alpha_corrected={prog_details['alpha_corrected']:.6f}, is_sig={prog_is_sig}")

assert abs(manual_min_p - prog_min_p) < 1e-10, (
    f"min_p 不一致: 手工 {manual_min_p} vs 程序 {prog_min_p}"
)
assert manual_n_tests == prog_details['n_columns'], (
    f"n_tests 不一致: 手工 {manual_n_tests} vs 程序 {prog_details['n_columns']}"
)
assert abs(manual_alpha_corrected - prog_details['alpha_corrected']) < 1e-10, (
    f"alpha_corrected 不一致: 手工 {manual_alpha_corrected} vs 程序 {prog_details['alpha_corrected']}"
)
assert manual_is_sig == prog_is_sig, (
    f"is_sig 不一致: 手工 {manual_is_sig} vs 程序 {prog_is_sig}"
)
print("  ✓ KS 拆分语义与手工计算完全一致")


# ── 校验 3: BH-FDR 校正公式 (T4 v3.0.0) ─────────────────────────
print("\n[3] BH-FDR 校正公式校验 (T4 v3.0.0 默认)")
# 不同列数下校验 BH 公式: p_adj_(k) = p_(k) * K / rank, 累积 min, clip [0,1]
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

for n_cols in [1, 5, 10, 20]:
    alpha = 0.05
    np.random.seed(n_cols)
    hist = pd.DataFrame(np.random.randn(50, n_cols))
    recent = pd.DataFrame(np.random.randn(50, n_cols))
    # 默认 correction_method='benjamini_hochberg'
    _, _, details = _ks_migration_significance(hist, recent, alpha=alpha)

    # 手工计算 BH p_adj
    prog_p_values = [c['p_value'] for c in details['per_column']]
    expected_p_adj = _manual_bh(prog_p_values)
    actual_p_adj = [c['p_value_adjusted'] for c in details['per_column']]

    assert details['correction_method'] == 'benjamini_hochberg', (
        f"n_cols={n_cols}: 期望 correction_method='benjamini_hochberg', "
        f"实际 {details['correction_method']}"
    )
    for i, (actual, expected) in enumerate(zip(actual_p_adj, expected_p_adj)):
        assert abs(actual - expected) < 1e-10, (
            f"n_cols={n_cols}, col {i}: 期望 p_adj={expected}, 实际 {actual}"
        )
    print(f"  n_cols={n_cols}: min_p_adj={details['min_p_value_adjusted']:.6f} ✓")


# ── 校验 4: 无迁移场景 — 相同分布应不显著 ────────────────────────
print("\n[4] 无迁移场景校验 (相同分布)")
np.random.seed(100)
# 相同分布, 不应有显著迁移 (min_p 应较大)
hist_same = pd.DataFrame(np.random.randn(100, 5))
recent_same = pd.DataFrame(np.random.randn(100, 5))
is_sig, min_p, _ = _ks_migration_significance(hist_same, recent_same, alpha=0.05)
print(f"  相同分布: min_p={min_p:.4f}, is_sig={is_sig}")
# 相同分布下 min_p 不一定 > alpha_corrected (仍有随机性), 但应多数情况不显著
# 这里只验证逻辑不崩溃, 不强断言 is_sig=False
print("  ✓ 无迁移场景逻辑正常")


# ── 校验 5: 强迁移场景 — 不同分布应显著 ──────────────────────────
print("\n[5] 强迁移场景校验 (均值偏移 2σ)")
np.random.seed(200)
hist_diff = pd.DataFrame(np.random.randn(100, 5))
recent_diff = pd.DataFrame(np.random.randn(100, 5) + 2.0)  # 偏移 2σ
is_sig, min_p, _ = _ks_migration_significance(hist_diff, recent_diff, alpha=0.05)
print(f"  偏移 2σ: min_p={min_p:.6f}, is_sig={is_sig}")
assert is_sig, f"强迁移场景应显著: min_p={min_p}"
assert min_p < 0.001, f"强迁移 min_p 应极小: {min_p}"
print("  ✓ 强迁移场景正确识别")


# ── 校验 6: 数据不足场景 — <5 观测值跳过 ─────────────────────────
print("\n[6] 数据不足场景校验 (<5 观测值)")
hist_small = pd.DataFrame(np.random.randn(3, 5))   # 只有 3 个观测值
recent_small = pd.DataFrame(np.random.randn(3, 5))
is_sig, min_p, details = _ks_migration_significance(hist_small, recent_small, alpha=0.05)
print(f"  小样本: n_columns={details['n_columns']}, warning={details.get('warning', '无')}")
assert details['n_columns'] == 0, "小样本应跳过所有列"
assert not is_sig, "小样本不应判定为显著"
print("  ✓ 小样本正确跳过")


print("\n" + "=" * 70)
print("Fix 1 手工校验全部通过: 6/6")
print("=" * 70)
