# -*- coding: utf-8 -*-
"""
P4: health_bridge.py — TDD 测试套件

测试 HealthMonitorAdapter 将回测引擎结果注入 FactorHealthMonitor。
适配器不改动外部 FactorHealthMonitor 代码。
"""

import sys
import unittest
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

# P1.2: Factor_Fingerprint 已 pip install -e ., 无需 sys.path hack
# from factor_pipeline.modules.factor_fingerprint.core.health import FactorHealthMonitor, ...


# =============================================================================
# A. 适配器初始化
# =============================================================================

class TestAdapterSetup(unittest.TestCase):
    """测试 A: 适配器初始化"""

    def test_01_create_adapter(self):
        """
        [P4-A-01] 创建 HealthMonitorAdapter。

        手工校验: 适配器内部持有 FactorHealthMonitor 实例。
        """
        from factor_pipeline.backtest.health_bridge import HealthMonitorAdapter

        adapter = HealthMonitorAdapter()
        self.assertIsNotNone(adapter.health_monitor)
        self.assertIsNotNone(adapter.config)

        print(f"\n  手工校验: adapter 创建 OK")
        print(f"    health_monitor type: {type(adapter.health_monitor).__name__}")

    def test_02_create_adapter_with_custom_config(self):
        """
        [P4-A-02] 带自定义配置创建适配器。
        """
        from factor_pipeline.backtest.health_bridge import HealthMonitorAdapter
        from factor_pipeline.modules.factor_fingerprint.core.health import HealthConfig

        config = HealthConfig(
            efficacy_icir_threshold=0.50,
            crowding_corr_threshold=0.30,
        )
        adapter = HealthMonitorAdapter(config=config)

        self.assertEqual(adapter.config.efficacy_icir_threshold, 0.50)
        self.assertEqual(adapter.config.crowding_corr_threshold, 0.30)

        print(f"\n  手工校验: 自定义配置 OK")
        print(f"    icir_threshold={adapter.config.efficacy_icir_threshold}")

    def test_03_create_adapter_with_existing_monitor(self):
        """
        [P4-A-03] 注入已有 FactorHealthMonitor 实例。
        """
        from factor_pipeline.backtest.health_bridge import HealthMonitorAdapter
        from factor_pipeline.modules.factor_fingerprint.core.health import FactorHealthMonitor, HealthConfig

        monitor = FactorHealthMonitor(HealthConfig(efficacy_icir_threshold=0.60))
        adapter = HealthMonitorAdapter(health_monitor=monitor)

        self.assertIs(adapter.health_monitor, monitor)
        self.assertEqual(adapter.config.efficacy_icir_threshold, 0.60)

        print(f"\n  手工校验: 注入已有 monitor OK")


# =============================================================================
# B. 引擎结果 → 效能指标映射
# =============================================================================

class TestEfficacyMapping(unittest.TestCase):
    """测试 B: 引擎结果 → 效能指标映射"""

    def setUp(self):
        np.random.seed(42)
        self.engine_results = {
            'factor_a': {
                'rank_ic_series': np.array([0.05, 0.03, -0.02, 0.04, 0.06,
                                            0.02, 0.01, 0.03, -0.01, 0.04,
                                            0.05, 0.02, 0.03, 0.04, 0.01]),
                'rank_icir': 0.85,
                'pearson_ic_series': np.array([0.04, 0.02, -0.03, 0.05, 0.05,
                                               0.01, 0.02, 0.04, -0.02, 0.03,
                                               0.04, 0.03, 0.02, 0.05, 0.02]),
                'pearson_icir': 0.72,
                'ic_decay': np.array([0.04, 0.03, 0.02, 0.01, 0.00]),
                'hit_rate': 0.733,
                'turnover': np.array([0.15, 0.12, 0.18, 0.14, 0.11,
                                      0.13, 0.16, 0.14, 0.12, 0.15,
                                      0.13, 0.11, 0.14, 0.15]),
                'long_short_returns': np.array([0.01, 0.02, -0.01, 0.03, 0.02,
                                                -0.01, 0.01, 0.02, 0.01, 0.03,
                                                -0.01, 0.02, 0.01, 0.02]),
                'spread': 0.42,
            }
        }

    def test_04_map_efficacy_metrics(self):
        """
        [P4-B-04] 引擎结果 → 效能指标字典。

        手工校验: 映射后的字段名和值与 engine_results 一致。
        """
        from factor_pipeline.backtest.health_bridge import HealthMonitorAdapter

        adapter = HealthMonitorAdapter()
        efficacy = adapter._map_efficacy_metrics(self.engine_results['factor_a'])

        # 检查所有必需字段
        required = ['ic_ir', 'ic_win_rate', 'rolling_ic_mean', 'ic_autocorr']
        for field in required:
            self.assertIn(field, efficacy, f"缺少字段: {field}")

        # 手工校验值
        self.assertAlmostEqual(efficacy['ic_ir'], 0.85, places=10)
        self.assertAlmostEqual(efficacy['ic_win_rate'], 0.733, places=3)

        # rolling_ic_mean = 最近 window=12 期的均值
        ic_series = self.engine_results['factor_a']['rank_ic_series']
        ic_clean = ic_series[~np.isnan(ic_series)]
        expected_rolling_mean = np.mean(ic_clean[-12:])
        self.assertAlmostEqual(efficacy['rolling_ic_mean'], expected_rolling_mean, places=10)

        print(f"\n  手工校验: efficacy 映射 OK")
        for k, v in efficacy.items():
            print(f"    {k}: {v:.4f}")

    def test_05_map_efficacy_metrics_incomplete(self):
        """
        [P4-B-05] 不完整的引擎结果 → 优雅降级。

        手工校验: 缺失字段返回 NaN，不抛异常。
        """
        from factor_pipeline.backtest.health_bridge import HealthMonitorAdapter

        adapter = HealthMonitorAdapter()
        incomplete = {'rank_icir': 0.50}  # 只有 ICIR
        efficacy = adapter._map_efficacy_metrics(incomplete)

        self.assertAlmostEqual(efficacy['ic_ir'], 0.50)
        self.assertTrue(np.isnan(efficacy['ic_win_rate']))
        self.assertTrue(np.isnan(efficacy['rolling_ic_mean']))
        self.assertTrue(np.isnan(efficacy['ic_autocorr']))

        print(f"\n  手工校验: 不完全数据降级 OK")
        for k, v in efficacy.items():
            print(f"    {k}: {v}")

    def test_06_map_crowding_metrics(self):
        """
        [P4-B-06] 引擎结果 → 拥挤度指标映射。

        手工校验: turnover 映射到 crowding_metrics。
        """
        from factor_pipeline.backtest.health_bridge import HealthMonitorAdapter

        adapter = HealthMonitorAdapter()
        crowding = adapter._map_crowding_metrics(self.engine_results['factor_a'])

        self.assertIn('turnover', crowding)
        expected_turnover = np.nanmean(self.engine_results['factor_a']['turnover'])
        self.assertAlmostEqual(crowding['turnover'], expected_turnover, places=10)

        print(f"\n  手工校验: crowding 映射 OK")
        print(f"    turnover: {crowding['turnover']:.4f}")

    def test_07_map_decay_metrics(self):
        """
        [P4-B-07] 引擎结果 → 衰减指标映射。

        手工校验: ic_decay 和 spread 映射到 decay_metrics。
        """
        from factor_pipeline.backtest.health_bridge import HealthMonitorAdapter

        adapter = HealthMonitorAdapter()
        decay = adapter._map_decay_metrics(self.engine_results['factor_a'])

        self.assertIn('long_short_decay_ratio', decay)
        self.assertIn('ic_decay_mean', decay)
        self.assertAlmostEqual(decay['ic_decay_mean'],
            np.nanmean(self.engine_results['factor_a']['ic_decay']), places=10)

        print(f"\n  手工校验: decay 映射 OK")
        for k, v in decay.items():
            print(f"    {k}: {v:.4f}")


# =============================================================================
# C. 构建健康报告
# =============================================================================

class TestReportBuilding(unittest.TestCase):
    """测试 C: 构建健康报告"""

    def setUp(self):
        np.random.seed(42)
        self.engine_results = {
            'factor_a': {
                'rank_ic_series': np.array([0.05, 0.03, -0.02, 0.04, 0.06,
                                            0.02, 0.01, 0.03, -0.01, 0.04,
                                            0.05, 0.02, 0.03, 0.04, 0.01]),
                'rank_icir': 0.85,
                'pearson_ic_series': np.array([0.04, 0.02, -0.03, 0.05, 0.05]),
                'pearson_icir': 0.72,
                'ic_decay': np.array([0.04, 0.03, 0.02, 0.01, 0.00]),
                'hit_rate': 0.733,
                'turnover': np.array([0.15, 0.12, 0.18, 0.14, 0.11]),
                'long_short_returns': np.array([0.01, 0.02, -0.01, 0.03, 0.02]),
                'spread': 0.42,
            }
        }

    def test_08_build_single_report(self):
        """
        [P4-C-08] 从引擎结果构建单个因子的健康报告。

        手工校验: 报告包含 5 维得分和指标。
        """
        from factor_pipeline.backtest.health_bridge import HealthMonitorAdapter

        adapter = HealthMonitorAdapter()
        report = adapter.build_report_from_engine(
            factor_name='factor_a',
            engine_results=self.engine_results['factor_a'],
        )

        self.assertEqual(report.factor_name, 'factor_a')
        self.assertIsInstance(report.timestamp, datetime)

        # 检查 5 维得分
        self.assertGreaterEqual(report.crowding_score, 0.0)
        self.assertLessEqual(report.crowding_score, 100.0)
        self.assertGreaterEqual(report.efficacy_score, 0.0)
        self.assertLessEqual(report.efficacy_score, 100.0)

        # 检查效能指标
        self.assertIn('ic_ir', report.efficacy_metrics)
        self.assertAlmostEqual(report.efficacy_metrics['ic_ir'], 0.85, places=10)
        self.assertIn('ic_win_rate', report.efficacy_metrics)

        # 检查拥挤度指标
        self.assertIn('turnover', report.crowding_metrics)

        # 检查衰减指标
        self.assertIn('long_short_decay_ratio', report.decay_metrics)

        print(f"\n  手工校验: 报告构建 OK")
        print(f"    factor: {report.factor_name}")
        print(f"    health_score: {report.health_score:.1f}")
        print(f"    health_level: {report.health_level.value}")
        print(f"    crowding: {report.crowding_score:.1f}")
        print(f"    efficacy: {report.efficacy_score:.1f}")
        print(f"    capacity: {report.capacity_score:.1f}")
        print(f"    decay: {report.decay_score:.1f}")
        print(f"    regime: {report.regime_score:.1f}")

    def test_09_build_batch_reports(self):
        """
        [P4-C-09] 批量构建多个因子的健康报告。

        手工校验: 每个因子都有独立报告。
        """
        from factor_pipeline.backtest.health_bridge import HealthMonitorAdapter

        # 第二个因子
        engine_results = {
            'factor_a': self.engine_results['factor_a'],
            'factor_b': {
                'rank_ic_series': np.array([0.02, 0.01, 0.03, 0.01, 0.02]),
                'rank_icir': 0.45,
                'pearson_icir': 0.38,
                'ic_decay': np.array([0.02, 0.01, 0.01]),
                'hit_rate': 0.60,
                'turnover': np.array([0.25, 0.22, 0.28, 0.24, 0.21]),
                'long_short_returns': np.array([0.005, 0.01, -0.005, 0.01]),
                'spread': 0.25,
            }
        }

        adapter = HealthMonitorAdapter()
        reports = adapter.build_batch_reports(engine_results)

        self.assertEqual(len(reports), 2)
        self.assertIn('factor_a', reports)
        self.assertIn('factor_b', reports)

        # factor_a 应该比 factor_b 健康
        self.assertGreater(
            reports['factor_a'].health_score,
            reports['factor_b'].health_score,
        )

        print(f"\n  手工校验: 批量报告 OK")
        for name, r in reports.items():
            print(f"    {name}: score={r.health_score:.1f}, level={r.health_level.value}")

    def test_10_report_with_alerts(self):
        """
        [P4-C-10] 低效能因子触发警报。

        手工校验: ICIR 低于阈值时触发 WARNING 警报。
        """
        from factor_pipeline.backtest.health_bridge import HealthMonitorAdapter
        from factor_pipeline.modules.factor_fingerprint.core.health import HealthConfig

        # 低效能因子
        poor_results = {
            'rank_ic_series': np.array([0.01, -0.02, 0.01, -0.01, 0.02]),
            'rank_icir': 0.15,  # 低于默认阈值 0.30
            'pearson_icir': 0.12,
            'ic_decay': np.array([0.01, 0.00, -0.01]),
            'hit_rate': 0.40,
            'turnover': np.array([0.30, 0.35, 0.40, 0.38, 0.42]),
            'long_short_returns': np.array([0.002, -0.003, 0.001, -0.002]),
            'spread': 0.10,
        }

        adapter = HealthMonitorAdapter()
        report = adapter.build_report_from_engine(
            factor_name='weak_factor',
            engine_results=poor_results,
        )

        # 应该触发警报
        self.assertGreater(len(report.alerts), 0)
        alert_categories = [a.category for a in report.alerts]
        self.assertIn('efficacy', alert_categories)

        print(f"\n  手工校验: 警报触发 OK")
        print(f"    health_score: {report.health_score:.1f}")
        print(f"    health_level: {report.health_level.value}")
        for alert in report.alerts:
            print(f"    ALERT [{alert.category}]: {alert.metric_name}={alert.metric_value:.3f} "
                  f"({alert.direction} {alert.threshold:.3f})")


# =============================================================================
# D. 指标注入（不改动外部模块）
# =============================================================================

class TestMetricInjection(unittest.TestCase):
    """测试 D: 指标注入 — 不改动外部 HealthMonitor"""

    def test_11_inject_vs_native_consistency(self):
        """
        [P4-D-11] 注入的 ICIR 与 HealthMonitor 内部计算一致。

        手工校验: 适配器注入的 ic_ir = engine_results['rank_icir']。
        """
        from factor_pipeline.backtest.health_bridge import HealthMonitorAdapter

        engine_results = {
            'rank_ic_series': np.array([0.05, 0.03, -0.02, 0.04, 0.06]),
            'rank_icir': 0.85,
            'pearson_icir': 0.72,
            'ic_decay': np.array([0.04, 0.03, 0.02]),
            'hit_rate': 0.80,
            'turnover': np.array([0.15, 0.12, 0.18, 0.14]),
            'long_short_returns': np.array([0.01, 0.02, -0.01, 0.03]),
            'spread': 0.42,
        }

        adapter = HealthMonitorAdapter()
        report = adapter.build_report_from_engine(
            factor_name='test_factor',
            engine_results=engine_results,
        )

        # 注入的 ICIR 应该等于 engine 的 rank_icir
        self.assertAlmostEqual(
            report.efficacy_metrics['ic_ir'],
            engine_results['rank_icir'],
            places=10,
        )

        # 注入的 IC 胜率应该等于 engine 的 hit_rate
        self.assertAlmostEqual(
            report.efficacy_metrics['ic_win_rate'],
            engine_results['hit_rate'],
            places=10,
        )

        print(f"\n  手工校验: 注入一致性 OK")
        print(f"    ic_ir: engine={engine_results['rank_icir']:.4f} = report={report.efficacy_metrics['ic_ir']:.4f}")
        print(f"    ic_win_rate: engine={engine_results['hit_rate']:.4f} = report={report.efficacy_metrics['ic_win_rate']:.4f}")

    def test_12_no_external_module_mutation(self):
        """
        [P4-D-12] 适配器不改动外部 FactorHealthMonitor 的代码。

        手工校验: 原始 HealthMonitor 的 evaluate_health 方法签名不变。
        """
        import importlib, inspect, types, sys
        from pathlib import Path

        _fpkg_path = Path("F:/Coding/Factor_Fingerprint")

        # 临时注册 core 为 package，使 health.py 中的 from .fingerprint 能解析
        _old_core = sys.modules.get('core', None)
        _core_pkg = types.ModuleType('core')
        _core_pkg.__path__ = [str(_fpkg_path / "core")]
        _core_pkg.__package__ = 'core'
        sys.modules['core'] = _core_pkg

        _fp_spec = importlib.util.spec_from_file_location(
            "core.fingerprint", str(_fpkg_path / "core" / "fingerprint.py"))
        _fp_mod = importlib.util.module_from_spec(_fp_spec)
        _fp_mod.__package__ = 'core'
        sys.modules['core.fingerprint'] = _fp_mod
        _fp_spec.loader.exec_module(_fp_mod)

        _h_spec = importlib.util.spec_from_file_location(
            "core.health", str(_fpkg_path / "core" / "health.py"))
        _h_mod = importlib.util.module_from_spec(_h_spec)
        _h_mod.__package__ = 'core'
        sys.modules['core.health'] = _h_mod
        _h_spec.loader.exec_module(_h_mod)

        FactorHealthMonitor = _h_mod.FactorHealthMonitor

        sig = inspect.signature(FactorHealthMonitor.evaluate_health)
        params = list(sig.parameters.keys())
        expected = ['self', 'factor_name', 'factor_data', 'returns_data',
                     'market_cap_data', 'volume_data']
        for p in expected:
            self.assertIn(p, params, f"缺少参数: {p}")

        monitor = FactorHealthMonitor()
        self.assertIsNotNone(monitor)

        # 恢复
        if _old_core is not None:
            sys.modules['core'] = _old_core
        else:
            # P1.3 修复: 若初始无 core 模块, 清理掉注册的临时 core 包,
            # 避免污染后续测试的 sys.modules['core']
            sys.modules.pop('core', None)
            sys.modules.pop('core.fingerprint', None)
            sys.modules.pop('core.health', None)

        print(f"\n  手工校验: 外部模块未改动 OK")
        print(f"    evaluate_health 签名: {params}")

    def test_13_empty_engine_results(self):
        """
        [P4-D-13] 空引擎结果 → 返回中性报告。

        手工校验: 所有得分为 50.0，级别为 WATCH。
        """
        from factor_pipeline.backtest.health_bridge import HealthMonitorAdapter
        from factor_pipeline.modules.factor_fingerprint.core.health import HealthAlertLevel

        adapter = HealthMonitorAdapter()
        report = adapter.build_report_from_engine(
            factor_name='empty_factor',
            engine_results={},
        )

        self.assertEqual(report.factor_name, 'empty_factor')
        self.assertEqual(report.health_score, 50.0)
        self.assertEqual(report.crowding_score, 50.0)
        self.assertEqual(report.efficacy_score, 50.0)
        self.assertEqual(report.capacity_score, 50.0)
        self.assertEqual(report.decay_score, 50.0)
        self.assertEqual(report.regime_score, 50.0)

        print(f"\n  手工校验: 空结果中性报告 OK")
        print(f"    health_score: {report.health_score:.1f}")


# =============================================================================
#                              测试运行器
# =============================================================================

def run_all_tests():
    print("=" * 70)
    print("P4: health_bridge.py — TDD 测试套件")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestAdapterSetup))
    suite.addTests(loader.loadTestsFromTestCase(TestEfficacyMapping))
    suite.addTests(loader.loadTestsFromTestCase(TestReportBuilding))
    suite.addTests(loader.loadTestsFromTestCase(TestMetricInjection))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print(f"P4 测试结果: {result.testsRun} 运行, "
          f"{len(result.failures)} 失败, {len(result.errors)} 错误")
    print("=" * 70)

    return result


if __name__ == '__main__':
    run_all_tests()