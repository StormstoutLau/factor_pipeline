# -*- coding: utf-8 -*-
"""
P6: pipeline_integration.py — TDD 测试套件

测试 PipelineBacktestRunner 端到端集成。
"""

import unittest

import pytest

# 可选依赖: Factor_Trading_v3_0 (pyproject.toml [backtest] extra)
# PipelineBacktestRunner.run() 通过 DataBridge.create_dataloader 间接依赖 DataLoaderV3,
# 未安装 Factor_Trading_v3_0 时跳过整个文件.
pytest.importorskip("Factor_Trading_v3_0")

import numpy as np
import pandas as pd


class TestPipelineIntegration(unittest.TestCase):
    """测试 P6: Pipeline 集成"""

    def setUp(self):
        np.random.seed(42)
        self.n_stocks = 20
        self.n_dates = 60

        stocks = [f's{i:03d}' for i in range(self.n_stocks)]
        dates = pd.date_range('2024-01-01', periods=self.n_dates, freq='B')

        self.price_data = pd.DataFrame(
            np.random.randn(self.n_stocks, self.n_dates) * 2 + 100,
            index=stocks, columns=dates,
        )

        self.processed_factors = {
            'factor_a': pd.DataFrame(
                np.random.randn(self.n_stocks, self.n_dates),
                index=stocks, columns=dates,
            ),
            'factor_b': pd.DataFrame(
                np.random.randn(self.n_stocks, self.n_dates),
                index=stocks, columns=dates,
            ),
        }

    def test_01_runner_basic(self):
        """
        [P6-01] 基本端到端流程。

        手工校验: run() 返回所有预期字段。
        """
        from factor_pipeline.backtest.pipeline_integration import PipelineBacktestRunner

        runner = PipelineBacktestRunner()
        results = runner.run(self.processed_factors, self.price_data)

        self.assertIn('engine_results', results)
        self.assertIn('factor_ranking', results)
        self.assertIn('health_reports', results)
        self.assertIn('drift_verdicts', results)
        self.assertIn('drift_summary', results)

        # 引擎结果包含2个因子
        self.assertEqual(len(results['engine_results']), 2)
        self.assertIn('factor_a', results['engine_results'])
        self.assertIn('factor_b', results['engine_results'])

        # 因子排序
        self.assertEqual(len(results['factor_ranking']), 2)

        print(f"\n  手工校验: 端到端流程 OK")
        print(f"    factors: {len(results['engine_results'])}")
        print(f"    ranking: {results['factor_ranking']}")

    def test_02_runner_with_config(self):
        """
        [P6-02] 带配置的端到端流程。

        手工校验: config 中的 ic_method 等参数传递到引擎。
        """
        from factor_pipeline.backtest.pipeline_integration import PipelineBacktestRunner
        from factor_pipeline.config_v2 import BacktestConfig

        config = BacktestConfig(
            ic_method='pearson',
            top_n=0.1,
            max_lag=6,
        )
        runner = PipelineBacktestRunner(config)
        results = runner.run(self.processed_factors, self.price_data)

        # 检查 pearson IC 系列存在
        engine_results = results['engine_results']['factor_a']
        self.assertIn('pearson_ic_series', engine_results)

        print(f"\n  手工校验: 配置传递 OK")
        print(f"    ic_method=pearson, top_n=0.1, max_lag=6")

    def test_03_runner_with_pipeline_config(self):
        """
        [P6-03] 传入 PipelineV2ConfigUnified。

        手工校验: 从 PipelineV2ConfigUnified 中提取 backtest 子配置。
        """
        from factor_pipeline.backtest.pipeline_integration import PipelineBacktestRunner
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified, BacktestConfig

        bt_config = BacktestConfig(
            ic_method='rank',
            top_n=0.3,
            enable_drift_detection=True,
            enable_health_check=True,
        )
        pipeline_config = PipelineV2ConfigUnified(
            name='test_pipeline',
            backtest=bt_config,
        )

        runner = PipelineBacktestRunner(pipeline_config)
        results = runner.run(self.processed_factors, self.price_data)

        self.assertIn('drift_verdicts', results)
        self.assertIn('health_reports', results)

        print(f"\n  手工校验: PipelineV2ConfigUnified OK")
        print(f"    drift enabled: {len(results['drift_verdicts'])} factors")
        print(f"    health reports: {len(results['health_reports'])} factors")

    def test_04_runner_quick_mode(self):
        """
        [P6-04] 快速评估模式（仅引擎指标）。

        手工校验: run_quick() 仅返回引擎指标，不执行健康度和漂移。
        """
        from factor_pipeline.backtest.pipeline_integration import PipelineBacktestRunner

        runner = PipelineBacktestRunner()
        results = runner.run_quick(self.processed_factors, self.price_data)

        self.assertIn('factor_a', results)
        self.assertIn('rank_ic_series', results['factor_a'])
        self.assertIn('rank_icir', results['factor_a'])

        print(f"\n  手工校验: 快速模式 OK")
        print(f"    factor_a ICIR={results['factor_a']['rank_icir']:.4f}")

    def test_05_runner_data_validation(self):
        """
        [P6-05] 数据验证失败时抛出 ValueError。

        手工校验: 空因子字典应抛出异常。
        """
        from factor_pipeline.backtest.pipeline_integration import PipelineBacktestRunner

        runner = PipelineBacktestRunner()
        with self.assertRaises(ValueError):
            runner.run({}, self.price_data)

        print(f"\n  手工校验: 数据验证抛出 ValueError OK")

    def test_06_runner_summary(self):
        """
        [P6-06] 生成摘要报告。

        手工校验: summary() 返回格式化字符串。
        """
        from factor_pipeline.backtest.pipeline_integration import PipelineBacktestRunner

        runner = PipelineBacktestRunner()
        results = runner.run(self.processed_factors, self.price_data)
        summary = runner.summary(results)

        self.assertIn('因子回测评估摘要', summary)
        self.assertIn('factor_a', summary)
        self.assertIn('factor_b', summary)

        print(f"\n  手工校验: 摘要报告 OK")
        print(summary)

    def test_07_config_backtest_defaults(self):
        """
        [P6-07] BacktestConfig 默认值。

        手工校验: 所有默认值符合预期。
        """
        from factor_pipeline.config_v2 import BacktestConfig

        bt = BacktestConfig()
        self.assertEqual(bt.ic_method, 'rank')
        self.assertAlmostEqual(bt.top_n, 0.2)
        self.assertEqual(bt.ls_method, 'top_n')
        self.assertEqual(bt.max_lag, 12)
        self.assertTrue(bt.enable_drift_detection)
        self.assertAlmostEqual(bt.drift_warning_threshold, 30.0)
        self.assertAlmostEqual(bt.drift_detect_threshold, 50.0)
        self.assertAlmostEqual(bt.drift_severe_threshold, 70.0)
        self.assertTrue(bt.enable_health_check)

        print(f"\n  手工校验: BacktestConfig 默认值 OK")
        print(f"    ic_method={bt.ic_method}, top_n={bt.top_n}")
        print(f"    thresholds: {bt.drift_warning_threshold}/{bt.drift_detect_threshold}/{bt.drift_severe_threshold}")

    def test_08_pipeline_config_includes_backtest(self):
        """
        [P6-08] PipelineV2ConfigUnified 包含 backtest 字段。

        手工校验: 默认配置包含 BacktestConfig。
        """
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified, BacktestConfig

        config = PipelineV2ConfigUnified()
        self.assertIsNotNone(config.backtest)
        self.assertIsInstance(config.backtest, BacktestConfig)

        print(f"\n  手工校验: PipelineV2ConfigUnified 包含 backtest 字段 OK")

    def test_09_config_json_roundtrip(self):
        """
        [P6-09] BacktestConfig JSON 序列化/反序列化。

        手工校验: 序列化后反序列化，值一致。
        """
        import json
        from factor_pipeline.config_v2 import BacktestConfig

        bt = BacktestConfig(
            ic_method='pearson',
            top_n=0.15,
            max_lag=8,
        )
        json_str = bt.model_dump_json()
        bt2 = BacktestConfig.model_validate_json(json_str)

        self.assertEqual(bt2.ic_method, 'pearson')
        self.assertAlmostEqual(bt2.top_n, 0.15)
        self.assertEqual(bt2.max_lag, 8)

        print(f"\n  手工校验: JSON 往返 OK")
        print(f"    original: {bt.ic_method}, {bt.top_n}, {bt.max_lag}")
        print(f"    restored: {bt2.ic_method}, {bt2.top_n}, {bt2.max_lag}")


# =============================================================================
#                              测试运行器
# =============================================================================

def run_all_tests():
    print("=" * 70)
    print("P6: pipeline_integration.py — TDD 测试套件")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestPipelineIntegration))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print(f"P6 测试结果: {result.testsRun} 运行, "
          f"{len(result.failures)} 失败, {len(result.errors)} 错误")
    print("=" * 70)

    return result


if __name__ == '__main__':
    run_all_tests()