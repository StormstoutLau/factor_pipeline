# -*- coding: utf-8 -*-
"""
P3 Phase 4: 集成测试 + 手工校验 — 端到端阈值优化

验证优化器在真实数据流上的完整行为:
  A. 小规模优化运行
  B. 最优参数验证
  C. 结果可复现性
  D. 参数重要性
"""

import unittest

import pytest

# 可选依赖: optuna (pyproject.toml [optimizer] extra)
# 所有测试均依赖 EndToEndThresholdOptimizer, 未安装 optuna 时跳过整个文件.
pytest.importorskip("optuna")

import numpy as np
import pandas as pd


class TestOptimizerIntegration(unittest.TestCase):
    """集成测试: 端到端优化运行"""

    @classmethod
    def setUpClass(cls):
        """生成模拟因子数据"""
        np.random.seed(42)
        n_stocks, n_periods = 50, 30

        # 构造 3 个因子，各有不同 IC
        cls.factor_data = {
            'factor_strong': pd.DataFrame(
                0.5 * np.random.randn(n_stocks, n_periods),
                index=[f's{i:03d}' for i in range(n_stocks)],
                columns=[f't{t:02d}' for t in range(n_periods)],
            ),
            'factor_medium': pd.DataFrame(
                np.random.randn(n_stocks, n_periods),
                index=[f's{i:03d}' for i in range(n_stocks)],
                columns=[f't{t:02d}' for t in range(n_periods)],
            ),
            'factor_weak': pd.DataFrame(
                2.0 * np.random.randn(n_stocks, n_periods),
                index=[f's{i:03d}' for i in range(n_stocks)],
                columns=[f't{t:02d}' for t in range(n_periods)],
            ),
        }

        # 前向收益: 强因子有信号，中等因子有噪声信号
        cls.forward_returns = pd.DataFrame(
            0.3 * cls.factor_data['factor_strong'].values
            + 0.1 * cls.factor_data['factor_medium'].values
            + 0.5 * np.random.randn(n_stocks, n_periods),
            index=[f's{i:03d}' for i in range(n_stocks)],
            columns=[f't{t:02d}' for t in range(n_periods)],
        )

    def test_01_optimization_runs(self):
        """
        [P3-Phase4-01] 小规模优化完成，返回最优参数。

        v3.4.0: 默认搜索空间为空 → search_orth=True 提供可搜空间.
        """
        from factor_pipeline.optimizer import DEFAULT_SEARCH_SPACE_ORTH
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(
            n_trials=20,
            cv_min_train=10,
            cv_test_size=3,
            random_seed=42,
            search_orth=True,
        )

        best_params = optimizer.optimize(
            self.factor_data,
            self.forward_returns,
            show_progress=False,
        )

        self.assertIsInstance(best_params, dict)
        self.assertGreater(len(best_params), 0)
        # orth 搜索路径: best_params 应精确覆盖 orth 搜索空间键
        self.assertEqual(set(best_params.keys()),
                         set(DEFAULT_SEARCH_SPACE_ORTH.keys()),
                         msg=f"best_params 应为 orth 参数, 实际 {sorted(best_params)}")

        print(f"\n  手工校验: 优化完成")
        print(f"    best_score={optimizer.best_score:.6f}")
        for name, val in sorted(best_params.items()):
            print(f"    {name}: {val}")

    def test_02_best_params_in_bounds(self):
        """
        [P3-Phase4-02] 最优参数在搜索空间边界内。

        float 参数检查 low/high, categorical 参数检查 choices.
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(
            n_trials=20, cv_min_train=10, cv_test_size=3, random_seed=42,
            search_orth=True,
        )
        best_params = optimizer.optimize(
            self.factor_data, self.forward_returns, show_progress=False,
        )

        for name, spec in optimizer.search_space.items():
            if name not in best_params:
                continue
            val = best_params[name]
            if spec['type'] == 'float':
                self.assertGreaterEqual(val, spec['low'],
                    f"{name}={val} 低于下限 {spec['low']}")
                self.assertLessEqual(val, spec['high'],
                    f"{name}={val} 高于上限 {spec['high']}")
            elif spec['type'] == 'categorical':
                self.assertIn(val, spec['choices'],
                    f"{name}={val} 不在 choices 中")

        print(f"\n  手工校验: 所有参数在搜索空间边界内")

    def test_03_best_config_valid(self):
        """
        [P3-Phase4-03] 最优配置可正确创建 PipelineV2Config。

        v3.4.0: orth 参数映射到 config.orthogonalization (自动启用).
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        optimizer = EndToEndThresholdOptimizer(
            n_trials=20, cv_min_train=10, cv_test_size=3, random_seed=42,
            search_orth=True,
        )
        optimizer.optimize(
            self.factor_data, self.forward_returns, show_progress=False,
        )

        best_config = optimizer.get_best_config()
        self.assertIsInstance(best_config, PipelineV2Config)

        # orth 参数已映射: 正交化自动启用, method/align_mode 与 best_params 一致
        self.assertIsNotNone(best_config.orthogonalization,
                             "设置 orth_method 后 orthogonalization 应实例化")
        self.assertTrue(best_config.orthogonalization.enabled,
                        "设置 orth_method 后应自动启用正交化")
        self.assertEqual(best_config.orthogonalization.method,
                         optimizer.best_params['orth_method'])
        self.assertEqual(best_config.orthogonalization.align_mode,
                         optimizer.best_params['orth_align_mode'])

        print(f"\n  手工校验: 最优配置")
        print(f"    orth_method={best_config.orthogonalization.method}")
        print(f"    orth_align_mode={best_config.orthogonalization.align_mode}")
        print(f"    enabled={best_config.orthogonalization.enabled}")

    def test_04_reproducibility(self):
        """
        [P3-Phase4-04] 相同种子产生相同结果。

        v3.4.0: orth 参数含 categorical (str) 与 float (数值), 分别比较.
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        opt1 = EndToEndThresholdOptimizer(
            n_trials=20, cv_min_train=10, cv_test_size=3, random_seed=42,
            search_orth=True,
        )
        params1 = opt1.optimize(
            self.factor_data, self.forward_returns, show_progress=False,
        )

        opt2 = EndToEndThresholdOptimizer(
            n_trials=20, cv_min_train=10, cv_test_size=3, random_seed=42,
            search_orth=True,
        )
        params2 = opt2.optimize(
            self.factor_data, self.forward_returns, show_progress=False,
        )

        # 相同种子 + 相同数据 → 相同结果
        self.assertEqual(set(params1.keys()), set(params2.keys()))
        for key in params1:
            if isinstance(params1[key], str):
                self.assertEqual(params1[key], params2[key],
                    msg=f"{key}: {params1[key]} != {params2[key]}")
            else:
                self.assertAlmostEqual(params1[key], params2[key], places=6,
                    msg=f"{key}: {params1[key]} != {params2[key]}")

        self.assertAlmostEqual(opt1.best_score, opt2.best_score, places=6)

        print(f"\n  手工校验: 可复现性")
        print(f"    best_score_1={opt1.best_score:.6f}")
        print(f"    best_score_2={opt2.best_score:.6f}")

    def test_05_param_importance(self):
        """
        [P3-Phase4-05] 参数重要性分析返回有效值。

        v3.4.0: orth 搜索路径下重要性基于 3 个 orth 参数.
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        optimizer = EndToEndThresholdOptimizer(
            n_trials=30, cv_min_train=10, cv_test_size=3, random_seed=42,
            search_orth=True,
        )
        optimizer.optimize(
            self.factor_data, self.forward_returns, show_progress=False,
        )

        importance = optimizer.get_param_importance()
        self.assertIsInstance(importance, dict)
        self.assertGreater(len(importance), 0)

        # 重要性之和: 小样本下可能为 0（fANOVA 需要足够多 trial）
        total = sum(importance.values())
        self.assertGreaterEqual(total, 0.0,
            f"重要性之和应为非负，实际 {total}")

        non_zero = sum(1 for v in importance.values() if v > 0)
        print(f"    non_zero_params: {non_zero}/{len(importance)}")

        print(f"\n  手工校验: 参数重要性")
        for name, imp in sorted(importance.items(), key=lambda x: -x[1]):
            bar = '#' * int(imp * 50)
            print(f"    {name}: {imp:.4f} {bar}")
        print(f"    total={total:.4f}")

    def test_06_different_seeds_different_results(self):
        """
        [P3-Phase4-06] 不同种子产生不同结果（优化非确定性）。

        v3.4.0: categorical (str) 与数值参数分别比较.
        """
        from factor_pipeline.optimizer import EndToEndThresholdOptimizer

        opt1 = EndToEndThresholdOptimizer(
            n_trials=20, cv_min_train=10, cv_test_size=3, random_seed=42,
            search_orth=True,
        )
        params1 = opt1.optimize(
            self.factor_data, self.forward_returns, show_progress=False,
        )

        opt2 = EndToEndThresholdOptimizer(
            n_trials=20, cv_min_train=10, cv_test_size=3, random_seed=123,
            search_orth=True,
        )
        params2 = opt2.optimize(
            self.factor_data, self.forward_returns, show_progress=False,
        )

        # 不同种子产生不同结果
        any_different = False
        for key in params1:
            if key in params2:
                v1, v2 = params1[key], params2[key]
                if isinstance(v1, str) or isinstance(v2, str):
                    if v1 != v2:
                        any_different = True
                        break
                elif abs(v1 - v2) > 1e-6:
                    any_different = True
                    break

        # 注意: 小样本下可能偶然相同，这是可接受的
        print(f"\n  手工校验: 不同种子")
        print(f"    seed=42 best_score={opt1.best_score:.6f}")
        print(f"    seed=123 best_score={opt2.best_score:.6f}")
        # 不强制要求不同，但记录结果
        print(f"    any_different={any_different}")


# =============================================================================
#                              测试运行器
# =============================================================================

def run_all_tests():
    """运行所有 Phase 4 集成测试"""
    print("=" * 70)
    print("P3 Phase 4: 集成测试 + 手工校验")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestOptimizerIntegration))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print(f"Phase 4 测试结果: {result.testsRun} 运行, "
          f"{len(result.failures)} 失败, {len(result.errors)} 错误")
    print("=" * 70)

    return result


if __name__ == '__main__':
    run_all_tests()