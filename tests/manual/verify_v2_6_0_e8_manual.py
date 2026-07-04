# -*- coding: utf-8 -*-
"""v2.6.0 E8 手工校验脚本 (P3-12' 阈值漂移监测)

校验内容:
1. 衰减检测: 前 5 期 best_score, 后 5 期衰减 → 触发
2. EWMA 手工计算与实现对比
3. 自定义 decay_threshold 边界
4. reset 行为
5. min_observations 保护
"""
import sys
import os
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


def test_decay_detection():
    """校验 1: 衰减检测"""
    from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor

    monitor = ThresholdDriftMonitor(
        best_score=0.05, best_params={},
        halflife=5, decay_threshold=0.2, min_observations=5,
    )

    # 前 5 期: 无衰减
    for _ in range(5):
        verdict = monitor.update(0.05)
    assert not verdict['needs_research'], "无衰减时不应触发"

    # 后 5 期: 衰减到 0.03 (40% 衰减)
    for _ in range(5):
        verdict = monitor.update(0.03)
    assert verdict['needs_research'], "衰减 > 20% 应触发"
    assert verdict['decay_ratio'] < 0.8, f"decay_ratio 应 < 0.8, 得到 {verdict['decay_ratio']}"

    print(f"\n  [校验 1] 衰减检测")
    print(f"    best_score: {verdict['best_score']:.4f}")
    print(f"    ewma_score: {verdict['ewma_score']:.4f}")
    print(f"    decay_ratio: {verdict['decay_ratio']:.4f}")
    print(f"    needs_research: {verdict['needs_research']}")
    print("  ✓ 校验 1 通过")


def test_ewma_manual_computation():
    """校验 2: EWMA 手工计算与实现对比"""
    from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor

    monitor = ThresholdDriftMonitor(
        best_score=0.05, best_params={},
        halflife=7, min_observations=1,
    )

    scores = [0.05, 0.045, 0.04, 0.038, 0.042, 0.035]
    for s in scores:
        monitor.update(s)

    # 手工 EWMA
    alpha = 1.0 - np.exp(-np.log(2.0) / 7)
    ewma_manual = scores[0]
    for s in scores[1:]:
        ewma_manual = alpha * s + (1 - alpha) * ewma_manual

    ewma_actual = monitor._compute_ewma()

    print(f"\n  [校验 2] EWMA 计算")
    print(f"    scores = {scores}")
    print(f"    alpha = {alpha:.6f}")
    print(f"    EWMA (实际) = {ewma_actual:.10f}")
    print(f"    EWMA (手工) = {ewma_manual:.10f}")
    assert abs(ewma_actual - ewma_manual) < 1e-10
    print("  ✓ 校验 2 通过")


def test_decay_threshold_boundary():
    """校验 3: 自定义 decay_threshold 边界"""
    from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor

    # decay_threshold=0.3 (允许 30% 衰减)
    monitor = ThresholdDriftMonitor(
        best_score=0.05, best_params={},
        halflife=3, decay_threshold=0.3, min_observations=3,
    )

    # 前 3 期 best_score, 后 5 期 25% 衰减 (0.05 → 0.0375)
    for _ in range(3):
        monitor.update(0.05)
    for _ in range(5):
        verdict = monitor.update(0.0375)

    # 25% < 30% 阈值, 不触发
    print(f"\n  [校验 3] decay_threshold 边界")
    print(f"    decay_threshold = 0.3 (允许 30%)")
    print(f"    decay_ratio = {verdict['decay_ratio']:.4f}")
    print(f"    needs_research = {verdict['needs_research']}")
    assert not verdict['needs_research'], "25% < 30%, 不应触发"
    print("  ✓ 校验 3 通过")


def test_reset_behavior():
    """校验 4: reset 行为"""
    from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor

    monitor = ThresholdDriftMonitor(
        best_score=0.05, best_params={'a': 1},
        halflife=5,
    )
    for s in [0.05, 0.04, 0.03]:
        monitor.update(s)

    # reset
    monitor.reset(best_score=0.06, best_params={'b': 2})

    # 验证 reset 后状态
    assert monitor.score_history == [], "history 应清空"
    assert monitor.best_score == 0.06
    assert monitor.best_params == {'b': 2}

    # 推入新评分, 应基于新 best_score 判定
    for _ in range(5):
        verdict = monitor.update(0.06)  # 等于新 best_score
    assert not verdict['needs_research'], "reset 后无衰减不应触发"

    print(f"\n  [校验 4] reset 行为")
    print(f"    reset 后 best_score = {monitor.best_score}")
    print(f"    reset 后 best_params = {monitor.best_params}")
    print(f"    history = {monitor.score_history}")
    print("  ✓ 校验 4 通过")


def test_min_observations_protection():
    """校验 5: min_observations 保护"""
    from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor

    monitor = ThresholdDriftMonitor(
        best_score=0.05, best_params={},
        halflife=5, min_observations=5,
    )

    # 推入 4 个严重衰减评分 (< min_observations=5)
    for _ in range(4):
        verdict = monitor.update(0.001)  # 严重衰减

    assert not verdict['needs_research'], "观测不足时不应触发"
    assert 'reason' in verdict, "应提供 reason"
    assert '观测数不足' in verdict['reason']

    print(f"\n  [校验 5] min_observations 保护")
    print(f"    n_observations = {verdict['n_observations']}")
    print(f"    reason = {verdict['reason']}")
    print("  ✓ 校验 5 通过")


def test_get_history_returns_copy():
    """校验 6: get_history 返回副本"""
    from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor

    monitor = ThresholdDriftMonitor(
        best_score=0.05, best_params={},
        halflife=5,
    )
    monitor.update(0.05)
    monitor.update(0.04)

    history = monitor.get_history()
    history.append(0.99)  # 修改副本

    assert len(monitor.score_history) == 2, "内部 history 不应被修改"
    assert len(history) == 3, "副本应反映修改"

    print(f"\n  [校验 6] get_history 副本")
    print(f"    副本 (修改后) = {history}")
    print(f"    内部 = {monitor.score_history}")
    print("  ✓ 校验 6 通过")


if __name__ == '__main__':
    print("=" * 70)
    print("v2.6.0 E8 手工校验 (P3-12' 阈值漂移监测)")
    print("=" * 70)
    test_decay_detection()
    test_ewma_manual_computation()
    test_decay_threshold_boundary()
    test_reset_behavior()
    test_min_observations_protection()
    test_get_history_returns_copy()
    print("\n" + "=" * 70)
    print("✓ 所有 E8 手工校验通过")
    print("=" * 70)
