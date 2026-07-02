# -*- coding: utf-8 -*-
"""
P5: unified_drift.py — TDD 测试套件

测试 UnifiedDriftReporter 双轨融合漂移判定。
融合结构漂移（Fingerprint）和性能漂移（Backtest）两个维度的漂移信号。
"""

import unittest
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd


# =============================================================================
# A. 融合漂移计算
# =============================================================================

class TestUnifiedDriftCompute(unittest.TestCase):
    """测试 A: 融合漂移计算"""

    def setUp(self):
        np.random.seed(42)

    def test_01_compute_structure_drift(self):
        """
        [P5-A-01] 计算结构漂移分数。

        手工校验: 基于 IC 序列的 KS 统计量变化。
        IC 序列分为前后两段，计算 KS 距离。
        """
        from factor_pipeline.backtest.unified_drift import UnifiedDriftReporter

        # 前段 IC: 均值 0.05, 标准差 0.02
        ic_early = np.array([0.05, 0.04, 0.06, 0.03, 0.07, 0.04, 0.05, 0.06])
        # 后段 IC: 均值 0.02, 标准差 0.02（明显漂移）
        ic_late = np.array([0.02, 0.01, 0.03, 0.00, 0.02, 0.01, 0.03, 0.02])

        reporter = UnifiedDriftReporter()
        drift_score = reporter._compute_structure_drift(ic_early, ic_late)

        # 手工计算 KS 统计量
        from scipy.stats import ks_2samp
        ks_stat, _ = ks_2samp(ic_early, ic_late)
        expected = ks_stat * 100  # 百分比

        self.assertAlmostEqual(drift_score, expected, places=10)
        self.assertGreater(drift_score, 0)  # 有漂移

        print(f"\n  手工校验: structure_drift OK")
        print(f"    drift_score={drift_score:.2f}, ks_stat={ks_stat:.4f}")

    def test_02_compute_performance_drift(self):
        """
        [P5-A-02] 计算性能漂移分数。

        手工校验: 基于 ICIR 变化率。
        drift = max(0, (1 - icir_late / icir_early)) * 100
        """
        from factor_pipeline.backtest.unified_drift import UnifiedDriftReporter

        icir_early = 0.80
        icir_late = 0.40  # 减半

        reporter = UnifiedDriftReporter()
        drift_score = reporter._compute_performance_drift(icir_early, icir_late)

        expected = max(0, (1 - 0.40 / 0.80)) * 100  # = 50.0
        self.assertAlmostEqual(drift_score, expected, places=10)
        self.assertAlmostEqual(drift_score, 50.0, places=10)

        print(f"\n  手工校验: performance_drift OK")
        print(f"    drift_score={drift_score:.2f}")

    def test_03_compute_performance_drift_no_change(self):
        """
        [P5-A-03] 性能无变化时漂移分数为 0。

        手工校验: icir 不变 → drift=0。
        """
        from factor_pipeline.backtest.unified_drift import UnifiedDriftReporter

        reporter = UnifiedDriftReporter()
        drift_score = reporter._compute_performance_drift(0.80, 0.80)

        self.assertAlmostEqual(drift_score, 0.0, places=10)

        print(f"\n  手工校验: performance_drift 无变化 → {drift_score:.2f}")

    def test_04_compute_turnover_drift(self):
        """
        [P5-A-04] 计算换手率漂移。

        手工校验: 基于换手率变化率。
        drift = max(0, (turnover_late / turnover_early - 1)) * 100
        """
        from factor_pipeline.backtest.unified_drift import UnifiedDriftReporter

        turnover_early = 0.15
        turnover_late = 0.30  # 翻倍

        reporter = UnifiedDriftReporter()
        drift_score = reporter._compute_turnover_drift(turnover_early, turnover_late)

        expected = max(0, (0.30 / 0.15 - 1)) * 100  # = 100.0
        self.assertAlmostEqual(drift_score, expected, places=10)

        print(f"\n  手工校验: turnover_drift OK")
        print(f"    drift_score={drift_score:.2f}")


# =============================================================================
# B. 融合判定
# =============================================================================

class TestUnifiedDriftVerdict(unittest.TestCase):
    """测试 B: 融合判定"""

    def setUp(self):
        np.random.seed(42)

    def test_05_verdict_stable(self):
        """
        [P5-B-05] 低漂移 → stable。

        手工校验: 所有漂移分数 < 阈值 → stable。
        """
        from factor_pipeline.backtest.unified_drift import UnifiedDriftReporter

        reporter = UnifiedDriftReporter(config={
            'structure_weight': 0.5,
            'performance_weight': 0.3,
            'turnover_weight': 0.2,
            'warning_threshold': 30,
            'drift_threshold': 50,
            'severe_threshold': 70,
        })

        verdict = reporter.evaluate(
            structure_drift=10.0,
            performance_drift=10.0,
            turnover_drift=10.0,
        )

        self.assertEqual(verdict['level'], 'stable')
        self.assertLess(verdict['combined_score'], 30)

        print(f"\n  手工校验: stable OK")
        print(f"    combined_score={verdict['combined_score']:.1f}, level={verdict['level']}")

    def test_06_verdict_warning(self):
        """
        [P5-B-06] 中等漂移 → warning。

        手工校验: 加权分数在 warning_threshold 和 drift_threshold 之间。
        """
        from factor_pipeline.backtest.unified_drift import UnifiedDriftReporter

        reporter = UnifiedDriftReporter(config={
            'structure_weight': 0.5,
            'performance_weight': 0.3,
            'turnover_weight': 0.2,
            'warning_threshold': 30,
            'drift_threshold': 50,
            'severe_threshold': 70,
        })

        verdict = reporter.evaluate(
            structure_drift=40.0,
            performance_drift=30.0,
            turnover_drift=20.0,
        )

        expected = 0.5 * 40 + 0.3 * 30 + 0.2 * 20  # = 33.0
        self.assertAlmostEqual(verdict['combined_score'], expected, places=10)
        self.assertEqual(verdict['level'], 'warning')

        print(f"\n  手工校验: warning OK")
        print(f"    combined_score={verdict['combined_score']:.1f}, level={verdict['level']}")

    def test_07_verdict_drift_detected(self):
        """
        [P5-B-07] 高漂移 → drift_detected。

        手工校验: 加权分数在 drift_threshold 和 severe_threshold 之间。
        """
        from factor_pipeline.backtest.unified_drift import UnifiedDriftReporter

        reporter = UnifiedDriftReporter(config={
            'structure_weight': 0.5,
            'performance_weight': 0.3,
            'turnover_weight': 0.2,
            'warning_threshold': 30,
            'drift_threshold': 50,
            'severe_threshold': 70,
        })

        verdict = reporter.evaluate(
            structure_drift=60.0,
            performance_drift=50.0,
            turnover_drift=40.0,
        )

        expected = 0.5 * 60 + 0.3 * 50 + 0.2 * 40  # = 53.0
        self.assertAlmostEqual(verdict['combined_score'], expected, places=10)
        self.assertEqual(verdict['level'], 'drift_detected')

        print(f"\n  手工校验: drift_detected OK")
        print(f"    combined_score={verdict['combined_score']:.1f}, level={verdict['level']}")

    def test_08_verdict_severe(self):
        """
        [P5-B-08] 极高漂移 → severe_drift。

        手工校验: 加权分数 >= severe_threshold。
        """
        from factor_pipeline.backtest.unified_drift import UnifiedDriftReporter

        reporter = UnifiedDriftReporter(config={
            'structure_weight': 0.5,
            'performance_weight': 0.3,
            'turnover_weight': 0.2,
            'warning_threshold': 30,
            'drift_threshold': 50,
            'severe_threshold': 70,
        })

        verdict = reporter.evaluate(
            structure_drift=80.0,
            performance_drift=70.0,
            turnover_drift=60.0,
        )

        expected = 0.5 * 80 + 0.3 * 70 + 0.2 * 60  # = 73.0
        self.assertAlmostEqual(verdict['combined_score'], expected, places=10)
        self.assertEqual(verdict['level'], 'severe_drift')

        print(f"\n  手工校验: severe_drift OK")
        print(f"    combined_score={verdict['combined_score']:.1f}, level={verdict['level']}")


# =============================================================================
# C. 引擎数据集成
# =============================================================================

class TestUnifiedDriftEngineIntegration(unittest.TestCase):
    """测试 C: 引擎数据集成"""

    def setUp(self):
        np.random.seed(42)

    def test_09_from_engine_results(self):
        """
        [P5-C-09] 从引擎结果中提取漂移数据。

        手工校验: 将 IC 序列分为前后两段，计算结构漂移和性能漂移。
        """
        from factor_pipeline.backtest.unified_drift import UnifiedDriftReporter

        # 模拟引擎结果
        n_total = 60
        ic_series = np.concatenate([
            np.random.normal(0.05, 0.02, n_total // 2),
            np.random.normal(0.02, 0.02, n_total // 2),
        ])

        engine_results = {
            'rank_ic_series': ic_series,
            'rank_icir': 0.50,
            'turnover': np.random.uniform(0.10, 0.20, n_total - 1),
        }

        reporter = UnifiedDriftReporter()
        drift_data = reporter._extract_drift_data(engine_results)

        self.assertIn('structure_drift', drift_data)
        self.assertIn('performance_drift', drift_data)
        self.assertIn('turnover_drift', drift_data)

        # 结构漂移应该 > 0（前后段 IC 均值不同）
        self.assertGreater(drift_data['structure_drift'], 0)

        print(f"\n  手工校验: 引擎数据提取 OK")
        for k, v in drift_data.items():
            print(f"    {k}: {v:.2f}")

    def test_10_from_engine_results_short_series(self):
        """
        [P5-C-10] IC 序列过短时 → 所有漂移为 0。

        手工校验: n < 20 时，置信度不足，返回 0。
        """
        from factor_pipeline.backtest.unified_drift import UnifiedDriftReporter

        engine_results = {
            'rank_ic_series': np.array([0.05, 0.03, 0.04]),
            'rank_icir': 0.50,
            'turnover': np.array([0.15, 0.12]),
        }

        reporter = UnifiedDriftReporter()
        drift_data = reporter._extract_drift_data(engine_results)

        self.assertAlmostEqual(drift_data['structure_drift'], 0.0, places=10)
        self.assertAlmostEqual(drift_data['performance_drift'], 0.0, places=10)
        self.assertAlmostEqual(drift_data['turnover_drift'], 0.0, places=10)

        print(f"\n  手工校验: 短序列 → 全部 0.0 OK")

    def test_11_evaluate_from_engine(self):
        """
        [P5-C-11] 从引擎结果直接评估漂移。

        手工校验: 端到端流程，engine_results → drift_data → evaluate → verdict。
        """
        from factor_pipeline.backtest.unified_drift import UnifiedDriftReporter

        n_total = 60
        ic_series = np.concatenate([
            np.random.normal(0.05, 0.02, n_total // 2),
            np.random.normal(0.02, 0.02, n_total // 2),
        ])

        engine_results = {
            'rank_ic_series': ic_series,
            'rank_icir': 0.50,
            'turnover': np.random.uniform(0.10, 0.20, n_total - 1),
        }

        reporter = UnifiedDriftReporter()
        verdict = reporter.evaluate_from_engine('factor_a', engine_results)

        self.assertEqual(verdict['factor_name'], 'factor_a')
        self.assertIn('level', verdict)
        self.assertIn('combined_score', verdict)
        self.assertIn('structure_drift', verdict)
        self.assertIn('performance_drift', verdict)
        self.assertIn('turnover_drift', verdict)

        print(f"\n  手工校验: 端到端评估 OK")
        print(f"    factor: {verdict['factor_name']}")
        print(f"    level: {verdict['level']}")
        print(f"    combined_score: {verdict['combined_score']:.1f}")
        print(f"    structure_drift: {verdict['structure_drift']:.1f}")
        print(f"    performance_drift: {verdict['performance_drift']:.1f}")
        print(f"    turnover_drift: {verdict['turnover_drift']:.1f}")


# =============================================================================
# D. 批量评估
# =============================================================================

class TestUnifiedDriftBatch(unittest.TestCase):
    """测试 D: 批量评估"""

    def setUp(self):
        np.random.seed(42)
        self.n_total = 60

    def test_12_batch_evaluate(self):
        """
        [P5-D-12] 批量评估多个因子。

        手工校验: 每个因子独立评估，结果包含所有因子。
        """
        from factor_pipeline.backtest.unified_drift import UnifiedDriftReporter

        multi_results = {}
        for i in range(3):
            ic_series = np.concatenate([
                np.random.normal(0.05, 0.02, self.n_total // 2),
                np.random.normal(0.02 + 0.01 * i, 0.02, self.n_total // 2),
            ])
            multi_results[f'factor_{i}'] = {
                'rank_ic_series': ic_series,
                'rank_icir': 0.50 + 0.1 * i,
                'turnover': np.random.uniform(0.10, 0.20, self.n_total - 1),
            }

        reporter = UnifiedDriftReporter()
        verdicts = reporter.batch_evaluate(multi_results)

        self.assertEqual(len(verdicts), 3)
        for i in range(3):
            name = f'factor_{i}'
            self.assertIn(name, verdicts)
            self.assertEqual(verdicts[name]['factor_name'], name)

        print(f"\n  手工校验: 批量评估 OK")
        for name, v in verdicts.items():
            print(f"    {name}: level={v['level']}, score={v['combined_score']:.1f}")

    def test_13_summary_report(self):
        """
        [P5-D-13] 生成漂移摘要报告。

        手工校验: 摘要包含因子数、各等级分布、最高漂移因子。
        """
        from factor_pipeline.backtest.unified_drift import UnifiedDriftReporter

        multi_results = {}
        for i in range(5):
            ic_series = np.concatenate([
                np.random.normal(0.05, 0.02, self.n_total // 2),
                np.random.normal(0.02 + 0.01 * i, 0.03, self.n_total // 2),
            ])
            multi_results[f'factor_{i}'] = {
                'rank_ic_series': ic_series,
                'rank_icir': 0.50 + 0.05 * i,
                'turnover': np.random.uniform(0.10, 0.20, self.n_total - 1),
            }

        reporter = UnifiedDriftReporter()
        summary = reporter.summary_report(multi_results)

        self.assertIn('total_factors', summary)
        self.assertIn('level_distribution', summary)
        self.assertIn('top_drift_factor', summary)
        self.assertIn('top_drift_score', summary)
        self.assertIn('average_drift_score', summary)

        self.assertEqual(summary['total_factors'], 5)

        print(f"\n  手工校验: 摘要报告 OK")
        for k, v in summary.items():
            print(f"    {k}: {v}")


# =============================================================================
#                              测试运行器
# =============================================================================

def run_all_tests():
    print("=" * 70)
    print("P5: unified_drift.py — TDD 测试套件")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestUnifiedDriftCompute))
    suite.addTests(loader.loadTestsFromTestCase(TestUnifiedDriftVerdict))
    suite.addTests(loader.loadTestsFromTestCase(TestUnifiedDriftEngineIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestUnifiedDriftBatch))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print(f"P5 测试结果: {result.testsRun} 运行, "
          f"{len(result.failures)} 失败, {len(result.errors)} 错误")
    print("=" * 70)

    return result


if __name__ == '__main__':
    run_all_tests()