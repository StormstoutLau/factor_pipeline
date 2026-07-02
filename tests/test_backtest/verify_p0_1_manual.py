# -*- coding: utf-8 -*-
"""
P0-1 手工校验: 滚动窗口 KS vs 二分法 + 调松阈值效果

手工计算流程:
  1. 构造已知漂移的 IC 序列 (前段均值 0.05, 后段均值 0.0)
  2. 手工计算二分法 KS 分数
  3. 手工计算滚动窗口 KS 分数 (逐位置扫描)
  4. 程序计算同样结果,对比一致性
  5. 验证调松阈值后,中等漂移能被检出
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.stats import ks_2samp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from factor_pipeline.backtest.unified_drift import (
    UnifiedDriftReporter, DEFAULT_CONFIG,
)


def manual_half_split_ks(ic_series: np.ndarray) -> float:
    """手工二分法 KS: 前 50% vs 后 50%"""
    mid = len(ic_series) // 2
    early = ic_series[:mid]
    late = ic_series[mid:]
    ks_stat, _ = ks_2samp(early, late)
    return ks_stat * 100


def manual_rolling_ks(ic_series: np.ndarray, window: int = 63,
                      p_threshold: float = 0.05) -> float:
    """手工滚动窗口 KS: 逐位置扫描,取最大分数 (经 p 值过滤)"""
    max_score = 0.0
    n = len(ic_series)
    for i in range(window, n - window + 1):
        early = ic_series[i - window:i]
        late = ic_series[i:i + window]
        ks_stat, p_value = ks_2samp(early, late)
        if p_value < p_threshold:
            score = ks_stat * 100
            if score > max_score:
                max_score = score
    return max_score


def main():
    print("=" * 70)
    print("P0-1 手工校验: 滚动窗口 KS + 调松阈值")
    print("=" * 70)

    # ── 1. 构造已知漂移数据 ──────────────────────────
    rng = np.random.default_rng(42)
    # 前 189 天稳定, 后 63 天漂移
    part1 = rng.normal(0.05, 0.02, 189)
    part2 = rng.normal(0.0, 0.03, 63)
    ic_series = np.concatenate([part1, part2])
    print(f"\n1. IC 序列长度: {len(ic_series)}")
    print(f"   前 189 天均值: {part1.mean():.4f}, 标准差: {part1.std():.4f}")
    print(f"   后 63 天均值: {part2.mean():.4f}, 标准差: {part2.std():.4f}")

    # ── 2. 手工计算 ──────────────────────────
    print("\n2. 手工计算:")
    manual_half = manual_half_split_ks(ic_series)
    print(f"   二分法 KS: {manual_half:.4f}")

    manual_rolling = manual_rolling_ks(ic_series, window=63)
    print(f"   滚动窗口 KS (window=63, p<0.05): {manual_rolling:.4f}")

    # ── 3. 程序计算 ──────────────────────────
    print("\n3. 程序计算:")
    reporter = UnifiedDriftReporter()
    prog_rolling = reporter._compute_rolling_structure_drift(
        ic_series, window=63,
    )
    print(f"   程序滚动窗口 KS: {prog_rolling:.4f}")

    # ── 4. 一致性校验 ──────────────────────────
    print("\n4. 一致性校验:")
    diff = abs(manual_rolling - prog_rolling)
    print(f"   |手工 - 程序| = {diff:.6f}")
    assert diff < 1e-10, f"不一致! 手工={manual_rolling}, 程序={prog_rolling}"
    print("   ✅ 一致 (差异 < 1e-10)")

    # ── 5. 滚动 vs 二分法优势验证 ──────────────────────────
    print("\n5. 滚动 vs 二分法优势:")
    mid = len(ic_series) // 2
    prog_half = reporter._compute_structure_drift(
        ic_series[:mid], ic_series[mid:],
    )
    print(f"   二分法 KS: {prog_half:.4f}")
    print(f"   滚动窗口 KS: {prog_rolling:.4f}")
    print(f"   滚动是否更高: {prog_rolling > prog_half}")

    # ── 6. 调松阈值效果验证 ──────────────────────────
    print("\n6. 调松阈值效果:")
    print(f"   DEFAULT_CONFIG: warning={DEFAULT_CONFIG['warning_threshold']}, "
          f"drift={DEFAULT_CONFIG['drift_threshold']}, "
          f"severe={DEFAULT_CONFIG['severe_threshold']}")
    print(f"   structure_sig_threshold={DEFAULT_CONFIG['structure_sig_threshold']}, "
          f"performance_sig_threshold={DEFAULT_CONFIG['performance_sig_threshold']}")

    # 模拟中等漂移场景
    rng2 = np.random.default_rng(42)
    part1 = rng2.normal(0.05, 0.02, 126)
    part2 = rng2.normal(0.02, 0.03, 126)
    ic_mild = np.concatenate([part1, part2])

    engine_result = {
        'rank_ic_series': ic_mild,
        'turnover': np.full(252, 0.3),
        'rank_icir': 0.5,
    }
    verdict = reporter.evaluate_from_engine("test_factor", engine_result)
    print(f"\n   中等漂移场景:")
    print(f"   level={verdict['level']}, score={verdict['combined_score']:.2f}")
    print(f"   structure_drift={verdict['structure_drift']:.2f}, "
          f"performance_drift={verdict['performance_drift']:.2f}")
    assert verdict['level'] != 'stable', \
        f"中等漂移应被检出, 但 level=stable"
    print("   ✅ 中等漂移被检出 (非 stable)")

    # ── 7. 真实 5 年场景验证 ──────────────────────────
    print("\n7. 5 年真实场景:")
    rng3 = np.random.default_rng(42)
    part1 = rng3.normal(0.04, 0.025, 756)
    part2 = rng3.normal(0.01, 0.035, 504)
    ic_5y = np.concatenate([part1, part2])

    engine_result = {
        'rank_ic_series': ic_5y,
        'turnover': np.full(1260, 0.3),
        'rank_icir': 0.3,
    }
    verdict = reporter.evaluate_from_engine("test_factor_5y", engine_result)
    print(f"   level={verdict['level']}, score={verdict['combined_score']:.2f}")
    print(f"   structure_drift={verdict['structure_drift']:.2f}, "
          f"performance_drift={verdict['performance_drift']:.2f}")
    assert verdict['level'] != 'stable', \
        f"5 年微弱漂移应被检出"
    print("   ✅ 5 年微弱漂移被检出")

    # ── 8. 滚动窗口 p 值过滤效果 ──────────────────────────
    print("\n8. p 值过滤效果 (稳定序列不应误报):")
    rng4 = np.random.default_rng(42)
    ic_stable = rng4.normal(0.05, 0.02, 252)
    stable_score = reporter._compute_rolling_structure_drift(
        ic_stable, window=63,
    )
    print(f"   稳定序列滚动 KS 分数: {stable_score:.4f}")
    assert stable_score < 15.0, \
        f"稳定序列不应被判定为漂移, score={stable_score}"
    print("   ✅ 稳定序列未被误报 (分数 < 15.0)")

    print("\n" + "=" * 70)
    print("P0-1 手工校验全部通过")
    print("=" * 70)


if __name__ == "__main__":
    main()
