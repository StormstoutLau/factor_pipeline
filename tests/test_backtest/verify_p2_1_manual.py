# -*- coding: utf-8 -*-
"""
P2-1 手工校验脚本 — 双信号加权融合 (替代 AND 逻辑)

校验项:
  1. 默认 signal_fusion_mode = 'max'
  2. AND 模式: 两信号都显著 → drift_detected
  3. AND 模式: 仅一信号显著 → warning (漏报)
  4. OR 模式: 任一显著 → both_significant=True (但仍需 combined 达阈值)
  5. max 模式: 结构漂移主导 → drift_detected
  6. max 模式: 性能漂移主导 → drift_detected
  7. max 模式: 两信号都弱 → stable
  8. 向后兼容: dual_signal_required=True → 'and' 模式
  9. 向后兼容: dual_signal_required=False → 'or' 模式
  10. 真实场景对比: 仅结构漂移显著, AND 漏报 vs max 正确报告
  11. 真实场景对比: 仅性能漂移显著, AND 漏报 vs max 正确报告
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from factor_pipeline.backtest.unified_drift import UnifiedDriftReporter, DEFAULT_CONFIG


def main():
    print("=" * 72)
    print("P2-1 手工校验 — 双信号加权融合 (替代 AND 逻辑)")
    print("=" * 72)

    failures = []

    # ── 校验 1: 默认 signal_fusion_mode = 'max' ──────────────────
    print("\n[校验 1] 默认 signal_fusion_mode = 'max'")
    reporter = UnifiedDriftReporter()
    actual = reporter.config.get('signal_fusion_mode')
    ok = actual == 'max'
    print(f"  期望: 'max'")
    print(f"  实际: '{actual}'")
    print(f"  结果: {'✓ 通过' if ok else '✗ 失败'}")
    if not ok:
        failures.append("校验 1 失败")

    # ── 校验 2: AND 模式两信号都显著 → drift_detected ────────────
    print("\n[校验 2] AND 模式: 两信号都显著 (40, 40) → drift_detected")
    reporter = UnifiedDriftReporter(config={
        'signal_fusion_mode': 'and',
        'warning_threshold': 10.0, 'drift_threshold': 25.0, 'severe_threshold': 50.0,
        'structure_sig_threshold': 20.0, 'performance_sig_threshold': 20.0,
    })
    # 手工计算: combined = 0.45*40 + 0.35*40 + 0 = 32
    # both_significant = (40>=20) and (40>=20) = True
    # 32 >= 25 (drift_threshold) and both_significant → drift_detected
    expected_combined = 0.45 * 40 + 0.35 * 40 + 0.20 * 0
    verdict = reporter.evaluate(40.0, 40.0, 0.0)
    ok = verdict['level'] == 'drift_detected'
    print(f"  手工 combined = 0.45*40 + 0.35*40 + 0 = {expected_combined}")
    print(f"  程序 combined = {verdict['combined_score']}")
    print(f"  both_significant = True (两信号都 >= 20)")
    print(f"  期望等级: drift_detected (32 >= 25 且 both_sig)")
    print(f"  实际等级: {verdict['level']}")
    print(f"  结果: {'✓ 通过' if ok else '✗ 失败'}")
    if not ok:
        failures.append("校验 2 失败")
    # 数值一致性
    if abs(verdict['combined_score'] - expected_combined) > 1e-6:
        print(f"  ✗ combined 数值不一致: 期望 {expected_combined}, 实际 {verdict['combined_score']}")
        failures.append("校验 2 数值不一致")

    # ── 校验 3: AND 模式仅一信号显著 → warning (漏报) ────────────
    print("\n[校验 3] AND 模式: 仅结构漂移显著 (40, 5) → warning (漏报)")
    reporter = UnifiedDriftReporter(config={
        'signal_fusion_mode': 'and',
        'warning_threshold': 10.0, 'drift_threshold': 25.0, 'severe_threshold': 50.0,
        'structure_sig_threshold': 20.0, 'performance_sig_threshold': 20.0,
    })
    # 手工计算: combined = 0.45*40 + 0.35*5 = 19.75
    # both_significant = (40>=20) and (5>=20) = True and False = False
    # 19.75 >= 10 (warning) 但 both_significant=False → warning (AND 漏报)
    expected_combined = 0.45 * 40 + 0.35 * 5 + 0.20 * 0
    verdict = reporter.evaluate(40.0, 5.0, 0.0)
    ok = verdict['level'] == 'warning'
    print(f"  手工 combined = 0.45*40 + 0.35*5 = {expected_combined}")
    print(f"  程序 combined = {verdict['combined_score']}")
    print(f"  both_significant = False (性能漂移 5 < 20)")
    print(f"  期望等级: warning (19.75 >= 10 但 both_sig=False, 漏报)")
    print(f"  实际等级: {verdict['level']}")
    print(f"  结果: {'✓ 通过' if ok else '✗ 失败'}")
    if not ok:
        failures.append("校验 3 失败")

    # ── 校验 4: OR 模式任一显著 → both_significant=True ──────────
    print("\n[校验 4] OR 模式: 仅结构漂移显著 (40, 5) → both_sig=True, combined=19.75 < 25 → warning")
    reporter = UnifiedDriftReporter(config={
        'signal_fusion_mode': 'or',
        'warning_threshold': 10.0, 'drift_threshold': 25.0, 'severe_threshold': 50.0,
        'structure_sig_threshold': 20.0, 'performance_sig_threshold': 20.0,
    })
    # OR: both_significant = (40>=20) or (5>=20) = True
    # combined = 19.75 < 25 (drift_threshold) → warning
    verdict = reporter.evaluate(40.0, 5.0, 0.0)
    ok = verdict['level'] == 'warning'
    print(f"  combined = {verdict['combined_score']} < 25 (drift_threshold)")
    print(f"  both_significant = True (OR, 结构漂移显著)")
    print(f"  期望等级: warning (combined 未达 drift_threshold)")
    print(f"  实际等级: {verdict['level']}")
    print(f"  结果: {'✓ 通过' if ok else '✗ 失败'}")
    if not ok:
        failures.append("校验 4 失败")

    # ── 校验 5: max 模式结构漂移主导 → drift_detected ────────────
    print("\n[校验 5] max 模式: 结构漂移主导 (40, 5) → drift_detected")
    reporter = UnifiedDriftReporter(config={
        'signal_fusion_mode': 'max',
        'warning_threshold': 10.0, 'drift_threshold': 25.0, 'severe_threshold': 50.0,
        'structure_sig_threshold': 20.0, 'performance_sig_threshold': 20.0,
    })
    # max: dominant = max(40, 5) = 40
    # dominant_threshold = max(20, 20) = 20
    # 40 >= 20 → 主信号显著
    # 等级由 dominant=40 决定: 40 >= 25 (drift) 且 40 < 50 (severe) → drift_detected
    verdict = reporter.evaluate(40.0, 5.0, 0.0)
    ok = verdict['level'] == 'drift_detected'
    print(f"  dominant = max(40, 5) = 40")
    print(f"  dominant_threshold = max(20, 20) = 20")
    print(f"  40 >= 20 → 主信号显著")
    print(f"  等级判定: 40 >= 25 (drift) 且 40 < 50 (severe) → drift_detected")
    print(f"  期望等级: drift_detected")
    print(f"  实际等级: {verdict['level']}")
    print(f"  结果: {'✓ 通过' if ok else '✗ 失败'}")
    if not ok:
        failures.append("校验 5 失败")

    # ── 校验 6: max 模式性能漂移主导 → drift_detected ────────────
    print("\n[校验 6] max 模式: 性能漂移主导 (5, 40) → drift_detected")
    reporter = UnifiedDriftReporter(config={
        'signal_fusion_mode': 'max',
        'warning_threshold': 10.0, 'drift_threshold': 25.0, 'severe_threshold': 50.0,
        'structure_sig_threshold': 20.0, 'performance_sig_threshold': 20.0,
    })
    verdict = reporter.evaluate(5.0, 40.0, 0.0)
    ok = verdict['level'] == 'drift_detected'
    print(f"  dominant = max(5, 40) = 40 >= 20 → drift_detected")
    print(f"  期望等级: drift_detected")
    print(f"  实际等级: {verdict['level']}")
    print(f"  结果: {'✓ 通过' if ok else '✗ 失败'}")
    if not ok:
        failures.append("校验 6 失败")

    # ── 校验 7: max 模式两信号都弱 → stable ──────────────────────
    print("\n[校验 7] max 模式: 两信号都弱 (5, 5) → stable")
    reporter = UnifiedDriftReporter(config={
        'signal_fusion_mode': 'max',
        'warning_threshold': 10.0, 'drift_threshold': 25.0, 'severe_threshold': 50.0,
        'structure_sig_threshold': 20.0, 'performance_sig_threshold': 20.0,
    })
    # dominant = max(5, 5) = 5 < 20 → 主信号未显著
    # combined = 0.45*5 + 0.35*5 = 4 < 10 → stable
    verdict = reporter.evaluate(5.0, 5.0, 0.0)
    ok = verdict['level'] == 'stable'
    print(f"  dominant = 5 < 20 → 主信号未显著")
    print(f"  combined = {verdict['combined_score']} < 10 → stable")
    print(f"  期望等级: stable")
    print(f"  实际等级: {verdict['level']}")
    print(f"  结果: {'✓ 通过' if ok else '✗ 失败'}")
    if not ok:
        failures.append("校验 7 失败")

    # ── 校验 8: 向后兼容 dual_signal_required=True → 'and' ────────
    print("\n[校验 8] 向后兼容: dual_signal_required=True → 'and' 模式")
    reporter = UnifiedDriftReporter(config={
        'dual_signal_required': True,  # 不传 signal_fusion_mode
        'warning_threshold': 10.0, 'drift_threshold': 25.0,
        'structure_sig_threshold': 20.0, 'performance_sig_threshold': 20.0,
    })
    actual_mode = reporter.config.get('signal_fusion_mode')
    ok_mode = actual_mode == 'and'
    print(f"  期望模式: 'and'")
    print(f"  实际模式: '{actual_mode}'")
    # 验证行为: 仅一信号显著 → warning (AND 行为)
    verdict = reporter.evaluate(40.0, 5.0, 0.0)
    ok_behavior = verdict['level'] == 'warning'
    print(f"  行为验证: 仅结构漂移显著 → warning (AND 漏报)")
    print(f"  实际等级: {verdict['level']}")
    print(f"  结果: {'✓ 通过' if (ok_mode and ok_behavior) else '✗ 失败'}")
    if not (ok_mode and ok_behavior):
        failures.append("校验 8 失败")

    # ── 校验 9: 向后兼容 dual_signal_required=False → 'or' ────────
    print("\n[校验 9] 向后兼容: dual_signal_required=False → 'or' 模式")
    reporter = UnifiedDriftReporter(config={
        'dual_signal_required': False,
        'warning_threshold': 10.0, 'drift_threshold': 25.0,
        'structure_sig_threshold': 20.0, 'performance_sig_threshold': 20.0,
    })
    actual_mode = reporter.config.get('signal_fusion_mode')
    ok_mode = actual_mode == 'or'
    print(f"  期望模式: 'or'")
    print(f"  实际模式: '{actual_mode}'")
    print(f"  结果: {'✓ 通过' if ok_mode else '✗ 失败'}")
    if not ok_mode:
        failures.append("校验 9 失败")

    # ── 校验 10: 真实场景 — 仅结构漂移显著, AND vs max ───────────
    print("\n[校验 10] 真实场景: 仅结构漂移显著 (40, 5), AND 漏报 vs max 正确报告")
    cfg = {
        'warning_threshold': 10.0, 'drift_threshold': 25.0, 'severe_threshold': 50.0,
        'structure_sig_threshold': 20.0, 'performance_sig_threshold': 20.0,
    }
    reporter_and = UnifiedDriftReporter(config={**cfg, 'signal_fusion_mode': 'and'})
    reporter_max = UnifiedDriftReporter(config={**cfg, 'signal_fusion_mode': 'max'})

    verdict_and = reporter_and.evaluate(40.0, 5.0, 0.0)
    verdict_max = reporter_max.evaluate(40.0, 5.0, 0.0)

    ok = verdict_and['level'] == 'warning' and verdict_max['level'] == 'drift_detected'
    print(f"  AND 模式: {verdict_and['level']} (漏报, 因 both_sig=False)")
    print(f"  max 模式: {verdict_max['level']} (正确报告, dominant=40 >= 20)")
    print(f"  结果: {'✓ 通过' if ok else '✗ 失败'}")
    if not ok:
        failures.append("校验 10 失败")

    # ── 校验 11: 真实场景 — 仅性能漂移显著, AND vs max ───────────
    print("\n[校验 11] 真实场景: 仅性能漂移显著 (5, 40), AND 漏报 vs max 正确报告")
    verdict_and = reporter_and.evaluate(5.0, 40.0, 0.0)
    verdict_max = reporter_max.evaluate(5.0, 40.0, 0.0)

    ok = verdict_and['level'] == 'warning' and verdict_max['level'] == 'drift_detected'
    print(f"  AND 模式: {verdict_and['level']} (漏报, 因 both_sig=False)")
    print(f"  max 模式: {verdict_max['level']} (正确报告, dominant=40 >= 20)")
    print(f"  结果: {'✓ 通过' if ok else '✗ 失败'}")
    if not ok:
        failures.append("校验 11 失败")

    # ── 校验 12: 数值一致性 — combined_score 公式 ─────────────────
    print("\n[校验 12] 数值一致性: combined_score = 0.45*struct + 0.35*perf + 0.20*turnover")
    reporter = UnifiedDriftReporter()  # 默认权重
    test_cases = [
        (30.0, 20.0, 10.0, 0.45 * 30 + 0.35 * 20 + 0.20 * 10),
        (50.0, 50.0, 50.0, 0.45 * 50 + 0.35 * 50 + 0.20 * 50),
        (0.0, 0.0, 0.0, 0.0),
        (100.0, 0.0, 0.0, 45.0),
    ]
    all_numeric_ok = True
    for s, p, t, expected in test_cases:
        verdict = reporter.evaluate(s, p, t)
        actual = verdict['combined_score']
        diff = abs(actual - expected)
        case_ok = diff < 1e-6
        if not case_ok:
            all_numeric_ok = False
            print(f"  ✗ (s={s}, p={p}, t={t}): 期望 {expected}, 实际 {actual}, 差异 {diff}")
        else:
            print(f"  ✓ (s={s}, p={p}, t={t}): combined={actual} == {expected}")
    print(f"  结果: {'✓ 通过' if all_numeric_ok else '✗ 失败'}")
    if not all_numeric_ok:
        failures.append("校验 12 失败")

    # ── 总结 ──────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    if not failures:
        print(f"P2-1 手工校验全部通过 (12/12)")
        print("=" * 72)
        return 0
    else:
        print(f"P2-1 手工校验失败 ({len(failures)} 项):")
        for f in failures:
            print(f"  - {f}")
        print("=" * 72)
        return 1


if __name__ == "__main__":
    sys.exit(main())
