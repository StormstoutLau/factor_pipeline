# -*- coding: utf-8 -*-
"""
P2-2: 优化器完整参数映射 + CV 改进 — TDD 测试套件

核心改进:
  1. _cv_evaluate 真正被 optimize() 调用 (当前是死代码)
  2. CV 每个 fold 中 Pipeline 在 train 上 fit, test 上 transform (消除 look-ahead)
  3. CV 分数是各 fold 的平均

设计原则:
  - Pipeline 只能见到 train 数据 (无 look-ahead bias)
  - train 和 test 在时间上无重叠
  - 数据不足时回退到全量评估
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from factor_pipeline.optimizer import EndToEndThresholdOptimizer


# =============================================================================
# 辅助: 构造模拟数据
# =============================================================================

def _make_factor_data(
    n_factors: int = 2,
    n_periods: int = 30,
    n_stocks: int = 50,
    seed: int = 42,
) -> tuple:
    """构造模拟因子数据和前向收益。

    Returns:
        factor_data: Dict[str, pd.DataFrame]  (n_periods × n_stocks)
        fwd_returns: pd.DataFrame  (n_periods × n_stocks)
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n_periods, freq="ME")
    stocks = [f"S{i:04d}" for i in range(n_stocks)]

    factor_data = {}
    for i in range(n_factors):
        factor_data[f"f{i}"] = pd.DataFrame(
            rng.normal(0, 1, (n_periods, n_stocks)), index=dates, columns=stocks,
        )

    fwd_returns = pd.DataFrame(
        rng.normal(0.001, 0.02, (n_periods, n_stocks)), index=dates, columns=stocks,
    )
    return factor_data, fwd_returns


def _skip_if_no_optuna():
    """如果 optuna 未安装则跳过"""
    try:
        import optuna  # noqa: F401
    except ImportError:
        pytest.skip("optuna 未安装")


# =============================================================================
# 测试类 1: CV 评估中 Pipeline 在 train 上 fit, test 上 transform
# =============================================================================

class TestCVPipelineFitTransform:
    """验证 _cv_evaluate 正确地在 train 上 fit, test 上 transform"""

    def test_01_cv_evaluate_fits_pipeline_on_train_only(self):
        """
        [P2-2-01] _cv_evaluate 应在 train 数据上 fit Pipeline

        手工校验: 构造 30 期数据, cv_min_train=10, cv_test_size=5
          fold 0: train=[0:10], test=[10:15]
          fold 1: train=[0:15], test=[15:20]
          fold 2: train=[0:20], test=[20:25]
          fold 3: train=[0:25], test=[25:30]
        Pipeline.fit 应被调用 4 次,每次只用 train 范围的数据
        """
        _skip_if_no_optuna()

        factor_data, fwd_returns = _make_factor_data(
            n_factors=1, n_periods=30, n_stocks=20, seed=42,
        )

        opt = EndToEndThresholdOptimizer(
            n_trials=1, cv_min_train=10, cv_test_size=5, random_seed=42,
        )

        # 记录每次 fit 调用的数据日期范围
        fit_date_ranges = []

        with mock.patch(
            "factor_pipeline.optimizer.FactorProcessingPipelineV2"
        ) as MockPipeline:
            mock_instance = mock.MagicMock()
            MockPipeline.return_value = mock_instance
            mock_instance.fit.return_value = mock_instance
            # transform 返回 test 数据本身 (不做处理)
            mock_instance.transform.side_effect = lambda fd: fd

            # 捕获 fit 调用的数据
            def capture_fit(fd, **kwargs):
                for name, df in fd.items():
                    fit_date_ranges.append((df.index[0], df.index[-1]))
                return mock_instance
            mock_instance.fit.side_effect = capture_fit

            from factor_pipeline.pipelines_v2 import PipelineV2Config
            config = PipelineV2Config()
            opt._cv_evaluate(factor_data, fwd_returns, config)

            # Pipeline 应被多次实例化和 fit (每个 fold 一次)
            assert mock_instance.fit.call_count >= 1, \
                f"Pipeline.fit 应被调用至少 1 次, 实际 {mock_instance.fit.call_count}"

            # 每个 fit 的数据都应该是 train 范围
            # fold 0: train=[0:10], 即日期 2020-01-31 到 2020-10-31
            dates = list(factor_data.values())[0].index
            expected_train_ends = [dates[9], dates[14], dates[19], dates[24]]
            actual_train_ends = [r[1] for r in fit_date_ranges]

            # 至少第一个 fold 的 train 结束日期应正确
            assert actual_train_ends[0] == expected_train_ends[0], \
                f"fold 0 train 结束日期应为 {expected_train_ends[0]}, " \
                f"实际 {actual_train_ends[0]}"

    def test_02_cv_evaluate_transforms_on_test_only(self):
        """
        [P2-2-02] _cv_evaluate 应在 test 数据上 transform Pipeline

        手工校验: fold 0 的 test=[10:15], transform 应只用 test 范围数据
        """
        _skip_if_no_optuna()

        factor_data, fwd_returns = _make_factor_data(
            n_factors=1, n_periods=30, n_stocks=20, seed=42,
        )

        opt = EndToEndThresholdOptimizer(
            n_trials=1, cv_min_train=10, cv_test_size=5, random_seed=42,
        )

        transform_date_ranges = []

        with mock.patch(
            "factor_pipeline.optimizer.FactorProcessingPipelineV2"
        ) as MockPipeline:
            mock_instance = mock.MagicMock()
            MockPipeline.return_value = mock_instance
            mock_instance.fit.return_value = mock_instance

            def capture_transform(fd, **kwargs):
                for name, df in fd.items():
                    transform_date_ranges.append((df.index[0], df.index[-1]))
                return fd
            mock_instance.transform.side_effect = capture_transform

            from factor_pipeline.pipelines_v2 import PipelineV2Config
            config = PipelineV2Config()
            opt._cv_evaluate(factor_data, fwd_returns, config)

            # transform 应被调用 (每个 fold 一次)
            assert mock_instance.transform.call_count >= 1, \
                f"Pipeline.transform 应被调用至少 1 次"

            # 第一个 fold 的 test 范围: [10:15]
            dates = list(factor_data.values())[0].index
            expected_test_start = dates[10]
            expected_test_end = dates[14]

            actual_test_start = transform_date_ranges[0][0]
            actual_test_end = transform_date_ranges[0][1]

            assert actual_test_start == expected_test_start, \
                f"fold 0 test 起始日期应为 {expected_test_start}, " \
                f"实际 {actual_test_start}"
            assert actual_test_end == expected_test_end, \
                f"fold 0 test 结束日期应为 {expected_test_end}, " \
                f"实际 {actual_test_end}"

    def test_03_cv_train_test_no_temporal_overlap(self):
        """
        [P2-2-03] train 和 test 在时间上无重叠

        手工校验: 每个 fold 的 train_end <= test_start
        """
        _skip_if_no_optuna()

        factor_data, fwd_returns = _make_factor_data(
            n_factors=1, n_periods=30, n_stocks=20, seed=42,
        )

        opt = EndToEndThresholdOptimizer(
            n_trials=1, cv_min_train=10, cv_test_size=5, random_seed=42,
        )

        folds = opt._generate_cv_folds(n_periods=30)

        assert len(folds) == 4, f"应有 4 个 fold, 实际 {len(folds)}"

        for i, fold in enumerate(folds):
            train_start, train_end = fold['train']
            test_start, test_end = fold['test']
            assert train_end <= test_start, \
                f"fold {i}: train_end={train_end} 应 <= test_start={test_start}"
            assert test_end > test_start, \
                f"fold {i}: test_end={test_end} 应 > test_start={test_start}"


# =============================================================================
# 测试类 2: CV 分数计算
# =============================================================================

class TestCVScoreComputation:
    """验证 CV 分数是各 fold 的平均"""

    def test_04_cv_score_is_average_of_folds(self):
        """
        [P2-2-04] CV 分数是各 fold IC 的平均

        手工校验: 构造已知数据,每个 fold 的 IC 可手工计算
          - 因子 = 前向收益的纯线性函数 → IC ≈ 1.0
          - CV 分数应接近各 fold IC 的平均
        """
        _skip_if_no_optuna()

        rng = np.random.default_rng(42)
        n_periods, n_stocks = 30, 50
        dates = pd.date_range("2020-01-01", periods=n_periods, freq="ME")
        stocks = [f"S{i:04d}" for i in range(n_stocks)]

        # 因子 = 收益 + 噪声 (高 IC)
        raw = rng.normal(0, 1, (n_periods, n_stocks))
        fwd_returns = pd.DataFrame(raw * 0.01, index=dates, columns=stocks)
        factor_data = {
            "f1": pd.DataFrame(raw + rng.normal(0, 0.1, (n_periods, n_stocks)),
                               index=dates, columns=stocks),
        }

        opt = EndToEndThresholdOptimizer(
            n_trials=1, cv_min_train=10, cv_test_size=5, random_seed=42,
        )

        # Mock Pipeline: 不做处理 (identity)
        with mock.patch(
            "factor_pipeline.optimizer.FactorProcessingPipelineV2"
        ) as MockPipeline:
            mock_instance = mock.MagicMock()
            MockPipeline.return_value = mock_instance
            mock_instance.fit.return_value = mock_instance
            mock_instance.transform.side_effect = lambda fd: fd

            from factor_pipeline.pipelines_v2 import PipelineV2Config
            config = PipelineV2Config()
            cv_score = opt._cv_evaluate(factor_data, fwd_returns, config)

            # 手工计算各 fold 的 IC
            folds = opt._generate_cv_folds(n_periods)
            manual_ics = []
            for fold in folds:
                _, train_end = fold['train']
                test_start, test_end = fold['test']
                f_test = factor_data["f1"].iloc[test_start:test_end]
                r_test = fwd_returns.iloc[test_start:test_end]
                # 计算 cross-sectional IC (按 period)
                ics = []
                for t in range(f_test.shape[0]):
                    f_t = f_test.iloc[t].values
                    r_t = r_test.iloc[t].values
                    valid = ~(np.isnan(f_t) | np.isnan(r_t))
                    if valid.sum() >= 5:
                        ics.append(np.corrcoef(f_t[valid], r_t[valid])[0, 1])
                manual_ics.append(np.mean(ics))

            expected_score = float(np.mean(manual_ics))

            assert isinstance(cv_score, float), \
                f"CV 分数应为 float, 实际 {type(cv_score)}"
            assert abs(cv_score - expected_score) < 0.15, \
                f"CV 分数 {cv_score:.6f} 应接近手工平均 {expected_score:.6f}"

    def test_05_cv_evaluate_returns_float(self):
        """
        [P2-2-05] _cv_evaluate 返回 float 类型
        """
        _skip_if_no_optuna()

        factor_data, fwd_returns = _make_factor_data(
            n_factors=1, n_periods=30, n_stocks=20, seed=42,
        )

        opt = EndToEndThresholdOptimizer(
            n_trials=1, cv_min_train=10, cv_test_size=5, random_seed=42,
        )

        with mock.patch(
            "factor_pipeline.optimizer.FactorProcessingPipelineV2"
        ) as MockPipeline:
            mock_instance = mock.MagicMock()
            MockPipeline.return_value = mock_instance
            mock_instance.fit.return_value = mock_instance
            mock_instance.transform.side_effect = lambda fd: fd

            from factor_pipeline.pipelines_v2 import PipelineV2Config
            config = PipelineV2Config()
            score = opt._cv_evaluate(factor_data, fwd_returns, config)

            assert isinstance(score, float), \
                f"返回值应为 float, 实际 {type(score)}"


# =============================================================================
# 测试类 3: optimize() 使用 CV
# =============================================================================

class TestOptimizeUsesCV:
    """验证 optimize() 真正使用 CV 而非全量数据"""

    def test_06_optimize_calls_cv_evaluate(self):
        """
        [P2-2-06] optimize() 应调用 _cv_evaluate

        手工校验: Mock _cv_evaluate, 验证它被调用
        """
        _skip_if_no_optuna()

        factor_data, fwd_returns = _make_factor_data(
            n_factors=2, n_periods=30, n_stocks=20, seed=42,
        )

        opt = EndToEndThresholdOptimizer(
            n_trials=3, cv_min_train=10, cv_test_size=5, random_seed=42,
        )

        with mock.patch.object(
            opt, '_cv_evaluate', return_value=0.05,
        ) as mock_cv:
            opt.optimize(factor_data, fwd_returns, show_progress=False)

            # _cv_evaluate 应被调用 (每个 trial 一次)
            assert mock_cv.call_count >= 1, \
                f"_cv_evaluate 应被调用至少 1 次, 实际 {mock_cv.call_count}"

    def test_07_optimize_pipeline_fit_multiple_times(self):
        """
        [P2-2-07] optimize() 中 Pipeline.fit 应被多次调用 (每个 fold 一次)

        手工校验: n_trials=2, cv folds=4 → fit 至少被调用 2*4=8 次
        (如果没有 CV, 每个 trial 只 fit 1 次, 2 trials 只 fit 2 次)
        """
        _skip_if_no_optuna()

        factor_data, fwd_returns = _make_factor_data(
            n_factors=1, n_periods=30, n_stocks=20, seed=42,
        )

        opt = EndToEndThresholdOptimizer(
            n_trials=2, cv_min_train=10, cv_test_size=5, random_seed=42,
        )

        with mock.patch(
            "factor_pipeline.optimizer.FactorProcessingPipelineV2"
        ) as MockPipeline:
            mock_instance = mock.MagicMock()
            MockPipeline.return_value = mock_instance
            mock_instance.fit.return_value = mock_instance
            mock_instance.transform.side_effect = lambda fd: fd

            opt.optimize(factor_data, fwd_returns, show_progress=False)

            # 有 CV: fit 调用次数 >= n_trials * n_folds
            # 无 CV: fit 调用次数 = n_trials
            n_folds = len(opt._generate_cv_folds(30))
            min_expected_calls = 2 * n_folds  # 至少 2 trials × n_folds
            assert mock_instance.fit.call_count >= min_expected_calls, \
                f"Pipeline.fit 应被调用至少 {min_expected_calls} 次 " \
                f"(2 trials × {n_folds} folds), " \
                f"实际 {mock_instance.fit.call_count}"


# =============================================================================
# 测试类 4: 数据不足回退 + 无 look-ahead
# =============================================================================

class TestCVFallbackAndNoLookAhead:
    """验证 CV 回退和无 look-ahead bias"""

    def test_08_cv_insufficient_data_fallback(self):
        """
        [P2-2-08] 数据不足时回退到全量评估

        手工校验: n_periods=8 < cv_min_train(10) + cv_test_size(5) = 15
          → 无 CV folds → 使用全量数据 (Pipeline fit 1 次)
        """
        _skip_if_no_optuna()

        factor_data, fwd_returns = _make_factor_data(
            n_factors=1, n_periods=8, n_stocks=20, seed=42,
        )

        opt = EndToEndThresholdOptimizer(
            n_trials=1, cv_min_train=10, cv_test_size=5, random_seed=42,
        )

        # 无 folds
        folds = opt._generate_cv_folds(n_periods=8)
        assert len(folds) == 0, "8 期数据应产生 0 个 fold"

        with mock.patch(
            "factor_pipeline.optimizer.FactorProcessingPipelineV2"
        ) as MockPipeline:
            mock_instance = mock.MagicMock()
            MockPipeline.return_value = mock_instance
            mock_instance.fit.return_value = mock_instance
            mock_instance.transform.side_effect = lambda fd: fd

            from factor_pipeline.pipelines_v2 import PipelineV2Config
            config = PipelineV2Config()
            score = opt._cv_evaluate(factor_data, fwd_returns, config)

            # 数据不足 → 回退到全量 → Pipeline fit 1 次
            assert mock_instance.fit.call_count == 1, \
                f"数据不足回退应 fit 1 次, 实际 {mock_instance.fit.call_count}"
            assert isinstance(score, float)

    def test_09_cv_no_look_ahead_bias(self):
        """
        [P2-2-09] CV 评估无 look-ahead bias

        手工校验: 构造 train 和 test 分布明显不同的数据
          - train 期: 因子与收益正相关 (IC > 0)
          - test 期: 因子与收益负相关 (IC < 0)
          - 如果有 look-ahead (全量 fit), Pipeline 会 "看到" test 数据
          - 正确的 CV: Pipeline 只在 train 上 fit, test 上 IC 应为负
          - 全量 fit: IC 会被 train 的正相关 "拉高"

        验证: CV 分数应低于全量评估分数 (因为 test 期 IC 为负)
        """
        _skip_if_no_optuna()

        rng = np.random.default_rng(42)
        n_periods, n_stocks = 30, 50
        dates = pd.date_range("2020-01-01", periods=n_periods, freq="ME")
        stocks = [f"S{i:04d}" for i in range(n_stocks)]

        # train 期 (前 15 期): 因子与收益正相关
        # test 期 (后 15 期): 因子与收益负相关
        raw_factor = rng.normal(0, 1, (n_periods, n_stocks))
        returns = np.zeros((n_periods, n_stocks))
        returns[:15] = raw_factor[:15] * 0.5 + rng.normal(0, 0.1, (15, n_stocks))
        returns[15:] = -raw_factor[15:] * 0.5 + rng.normal(0, 0.1, (15, n_stocks))

        factor_data = {
            "f1": pd.DataFrame(raw_factor, index=dates, columns=stocks),
        }
        fwd_returns = pd.DataFrame(returns, index=dates, columns=stocks)

        opt = EndToEndThresholdOptimizer(
            n_trials=1, cv_min_train=10, cv_test_size=5, random_seed=42,
        )

        # Mock Pipeline: identity (不做处理,以隔离 CV 逻辑)
        with mock.patch(
            "factor_pipeline.optimizer.FactorProcessingPipelineV2"
        ) as MockPipeline:
            mock_instance = mock.MagicMock()
            MockPipeline.return_value = mock_instance
            mock_instance.fit.return_value = mock_instance
            mock_instance.transform.side_effect = lambda fd: fd

            from factor_pipeline.pipelines_v2 import PipelineV2Config
            config = PipelineV2Config()

            # CV 评估 (只在 train 上 fit, test 上评估)
            cv_score = opt._cv_evaluate(factor_data, fwd_returns, config)

            # 全量评估 (用全量数据 fit + transform)
            full_factor = factor_data["f1"].T.values  # (n_stocks, n_periods)
            full_returns = fwd_returns.T.values
            full_score = opt._compute_ic(full_factor, full_returns)

            # CV 分数应低于全量分数 (因为 test 期 IC 为负,全量评估会被拉高)
            assert cv_score < full_score, \
                f"CV 分数 {cv_score:.6f} 应低于全量分数 {full_score:.6f} " \
                f"(无 look-ahead: CV 不会 '看到' test 数据的负 IC)"
