# -*- coding: utf-8 -*-
"""v2.6.0 E8 / P3-12' TDD 测试: ThresholdDriftMonitor (阈值漂移监测)

测试列表 (10 测试):
1. test_threshold_drift_monitor_init - 初始化字段正确
2. test_update_insufficient_observations - 观测数 < 5 时, needs_research=False
3. test_update_no_decay - current_score ≈ best_score 时, needs_research=False
4. test_update_significant_decay - 衰减 > 20% 时, needs_research=True
5. test_ewma_computation - EWMA 手工计算与实现对比 (精度 < 1e-10)
6. test_ewma_recent_emphasis - 近期评分低时, EWMA < 等权均值
7. test_decay_threshold_custom - decay_threshold=0.3 时, 衰减 25% 不触发
8. test_reset_clears_history - reset() 后 score_history 为空
9. test_get_history_returns_copy - get_history() 返回副本
10. test_integration_with_optimizer - optimizer.optimize() 后可用 best_score
"""
import unittest
import numpy as np


class TestThresholdDriftMonitor(unittest.TestCase):
    """E8: ThresholdDriftMonitor 测试"""

    def test_e8_01_threshold_drift_monitor_init(self):
        """[v2.6.0-E8-01] 初始化后, 字段正确."""
        from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor

        monitor = ThresholdDriftMonitor(
            best_score=0.05,
            best_params={'hard_routing_prob': 0.9},
            halflife=63,
            decay_threshold=0.2,
            min_observations=5,
        )

        self.assertEqual(monitor.best_score, 0.05)
        self.assertEqual(monitor.best_params, {'hard_routing_prob': 0.9})
        self.assertEqual(monitor.halflife, 63)
        self.assertEqual(monitor.decay_threshold, 0.2)
        self.assertEqual(monitor.min_observations, 5)
        self.assertEqual(monitor.score_history, [])

        print(f"\n  手工校验 E8-01: 初始化")
        print(f"    best_score = {monitor.best_score}")
        print(f"    halflife = {monitor.halflife}")
        print(f"    decay_threshold = {monitor.decay_threshold}")

    def test_e8_02_update_insufficient_observations(self):
        """[v2.6.0-E8-02] 观测数 < min_observations 时, needs_research=False."""
        from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor

        monitor = ThresholdDriftMonitor(
            best_score=0.05, best_params={},
            halflife=5, min_observations=5,
        )

        # 4 次更新 (< 5)
        for _ in range(4):
            verdict = monitor.update(0.01)  # 严重衰减, 但观测不足

        self.assertFalse(verdict['needs_research'],
                         "观测数 < 5 时 needs_research 应为 False")
        self.assertIn('reason', verdict, "观测不足时应提供 reason")
        self.assertEqual(verdict['n_observations'], 4)

        print(f"\n  手工校验 E8-02: 观测不足")
        print(f"    n_observations = {verdict['n_observations']}")
        print(f"    needs_research = {verdict['needs_research']}")
        print(f"    reason = {verdict.get('reason')}")

    def test_e8_03_update_no_decay(self):
        """[v2.6.0-E8-03] current_score ≈ best_score 时, needs_research=False."""
        from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor

        monitor = ThresholdDriftMonitor(
            best_score=0.05, best_params={},
            halflife=5, decay_threshold=0.2, min_observations=3,
        )

        # 5 次更新, 每次等于 best_score (无衰减)
        for _ in range(5):
            verdict = monitor.update(0.05)

        self.assertFalse(verdict['needs_research'],
                         "无衰减时 needs_research 应为 False")
        # decay_ratio ≈ 1.0 (无衰减)
        self.assertAlmostEqual(verdict['decay_ratio'], 1.0, places=6)

        print(f"\n  手工校验 E8-03: 无衰减")
        print(f"    decay_ratio = {verdict['decay_ratio']:.4f}")
        print(f"    needs_research = {verdict['needs_research']}")

    def test_e8_04_update_significant_decay(self):
        """[v2.6.0-E8-04] 衰减 > 20% 时, needs_research=True."""
        from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor

        monitor = ThresholdDriftMonitor(
            best_score=0.05, best_params={},
            halflife=3, decay_threshold=0.2, min_observations=3,
        )

        # 前 3 期: best_score
        for _ in range(3):
            monitor.update(0.05)
        # 后 5 期: 衰减到 0.03 (40% 衰减)
        for _ in range(5):
            verdict = monitor.update(0.03)

        self.assertTrue(verdict['needs_research'],
                        "衰减 > 20% 时 needs_research 应为 True")
        self.assertLess(verdict['decay_ratio'], 0.8,
                        f"decay_ratio 应 < 0.8, 实际 {verdict['decay_ratio']}")

        print(f"\n  手工校验 E8-04: 显著衰减")
        print(f"    decay_ratio = {verdict['decay_ratio']:.4f}")
        print(f"    needs_research = {verdict['needs_research']}")
        print(f"    reason = {verdict.get('reason')}")

    def test_e8_05_ewma_computation(self):
        """[v2.6.0-E8-05] EWMA 手工计算与实现对比 (精度 < 1e-10)."""
        from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor

        monitor = ThresholdDriftMonitor(
            best_score=0.05, best_params={},
            halflife=5, min_observations=1,
        )

        # 推入 4 个评分
        scores = [0.05, 0.04, 0.045, 0.042]
        for s in scores:
            monitor.update(s)

        # 手工计算 EWMA
        alpha = 1.0 - np.exp(-np.log(2.0) / 5)
        ewma_manual = scores[0]
        for s in scores[1:]:
            ewma_manual = alpha * s + (1 - alpha) * ewma_manual

        ewma_actual = monitor._compute_ewma()

        self.assertAlmostEqual(ewma_actual, ewma_manual, places=10,
                               msg=f"EWMA 实际 {ewma_actual} vs 手工 {ewma_manual}")

        print(f"\n  手工校验 E8-05: EWMA 计算")
        print(f"    scores = {scores}")
        print(f"    alpha = {alpha:.6f}")
        print(f"    EWMA (实际) = {ewma_actual:.10f}")
        print(f"    EWMA (手工) = {ewma_manual:.10f}")

    def test_e8_06_ewma_recent_emphasis(self):
        """[v2.6.0-E8-06] 近期评分低时, EWMA < 等权均值 (EWMA 偏向近期)."""
        from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor

        monitor = ThresholdDriftMonitor(
            best_score=0.05, best_params={},
            halflife=3, min_observations=1,
        )

        # 前 3 期高, 后 3 期低
        scores = [0.08, 0.08, 0.08, 0.02, 0.02, 0.02]
        for s in scores:
            monitor.update(s)

        ewma = monitor._compute_ewma()
        equal_weight_mean = np.mean(scores)

        self.assertLess(ewma, equal_weight_mean,
                        f"近期低分时 EWMA ({ewma:.4f}) 应 < 等权均值 ({equal_weight_mean:.4f})")

        print(f"\n  手工校验 E8-06: EWMA 近期偏向")
        print(f"    scores = {scores}")
        print(f"    EWMA = {ewma:.4f} (应更低)")
        print(f"    等权均值 = {equal_weight_mean:.4f}")

    def test_e8_07_decay_threshold_custom(self):
        """[v2.6.0-E8-07] decay_threshold=0.3 时, 衰减 25% 不触发 (25% < 30%)."""
        from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor

        monitor = ThresholdDriftMonitor(
            best_score=0.05, best_params={},
            halflife=3, decay_threshold=0.3, min_observations=3,
        )

        # 前 3 期 best_score, 后 5 期衰减 25% (0.05 → 0.0375)
        for _ in range(3):
            monitor.update(0.05)
        for _ in range(5):
            verdict = monitor.update(0.0375)

        # 衰减 25% < 30% 阈值, 不触发
        # 但 EWMA 会受 best_score 初值影响, 实际 decay_ratio 可能略高
        # 关键: needs_research 应为 False (25% < 30%)
        self.assertFalse(verdict['needs_research'],
                         f"decay_threshold=0.3 时, 25% 衰减不应触发, "
                         f"decay_ratio={verdict['decay_ratio']}")

        print(f"\n  手工校验 E8-07: 自定义阈值")
        print(f"    decay_threshold = 0.3")
        print(f"    decay_ratio = {verdict['decay_ratio']:.4f}")
        print(f"    needs_research = {verdict['needs_research']}")

    def test_e8_08_reset_clears_history(self):
        """[v2.6.0-E8-08] reset() 后, score_history 为空且 best_score 更新."""
        from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor

        monitor = ThresholdDriftMonitor(
            best_score=0.05, best_params={'a': 1},
            halflife=5,
        )
        # 推入几个评分
        for s in [0.05, 0.04, 0.03]:
            monitor.update(s)
        self.assertEqual(len(monitor.score_history), 3)

        # reset
        monitor.reset(best_score=0.06, best_params={'b': 2})

        self.assertEqual(monitor.score_history, [], "reset 后 history 应为空")
        self.assertEqual(monitor.best_score, 0.06, "best_score 应更新")
        self.assertEqual(monitor.best_params, {'b': 2}, "best_params 应更新")

        print(f"\n  手工校验 E8-08: reset")
        print(f"    score_history = {monitor.score_history}")
        print(f"    best_score = {monitor.best_score}")

    def test_e8_09_get_history_returns_copy(self):
        """[v2.6.0-E8-09] get_history() 返回副本, 修改不影响内部."""
        from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor

        monitor = ThresholdDriftMonitor(
            best_score=0.05, best_params={},
            halflife=5,
        )
        monitor.update(0.05)
        monitor.update(0.04)

        history = monitor.get_history()
        self.assertEqual(len(history), 2)

        # 修改副本
        history.append(0.99)

        # 内部 history 应不受影响
        self.assertEqual(len(monitor.score_history), 2,
                         "get_history() 返回副本, 内部不应被修改")

        print(f"\n  手工校验 E8-09: get_history 副本")
        print(f"    history (副本) = {history}")
        print(f"    内部 score_history = {monitor.score_history}")

    def test_e8_10_integration_with_optimizer(self):
        """[v2.6.0-E8-10] 集成测试: optimizer.optimize() 后, ThresholdDriftMonitor 可用 best_score."""
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer
        from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor
        import pandas as pd

        optimizer = EndToEndThresholdOptimizer(n_trials=2)

        # 构造小规模因子数据
        rng = np.random.default_rng(42)
        N, T = 30, 15
        factor_data = {
            'f0': pd.DataFrame(
                rng.standard_normal((N, T)),
                index=[f's{i:03d}' for i in range(N)],
                columns=pd.date_range('2020-01-01', periods=T, freq='D'),
            ),
        }
        forward_returns = pd.DataFrame(
            rng.standard_normal((T, N)),
            index=pd.date_range('2020-01-01', periods=T, freq='D'),
            columns=[f's{i:03d}' for i in range(N)],
        )

        optimizer.optimize(factor_data, forward_returns, show_progress=False)

        # 用 best_score 初始化 monitor
        monitor = ThresholdDriftMonitor(
            best_score=optimizer.best_score,
            best_params=optimizer.best_params,
            halflife=5,
        )

        # 模拟衰减场景
        for _ in range(5):
            verdict = monitor.update(optimizer.best_score * 0.5)  # 50% 衰减

        self.assertTrue(verdict['needs_research'],
                        "50% 衰减应触发 needs_research")

        print(f"\n  手工校验 E8-10: 集成测试")
        print(f"    best_score = {optimizer.best_score:.6f}")
        print(f"    decay_ratio = {verdict['decay_ratio']:.4f}")
        print(f"    needs_research = {verdict['needs_research']}")


if __name__ == '__main__':
    unittest.main()
