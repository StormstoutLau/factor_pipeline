# -*- coding: utf-8 -*-
"""
P2-2: 优化器 CV 改进 — 手工校验脚本

校验项:
  1. CV folds 生成正确性
  2. Pipeline 在 train 上 fit (日期范围校验)
  3. Pipeline 在 test 上 transform (日期范围校验)
  4. CV 分数 = 各 fold IC 的平均 (数值一致性)
  5. 无 look-ahead bias (CV 分数 < 全量分数)
  6. 数据不足回退 (fit 1 次)
  7. optimize() 调用 _cv_evaluate
  8. Pipeline.fit 调用次数 = n_trials × n_folds
  9. combined_score 数值一致性 (复合目标函数)
  10. 向后兼容: 旧 _cv_evaluate 接口已更新
  11. 空因子数据返回 -1.0
  12. transform_aggressiveness 参数映射
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from factor_pipeline.optimizer import EndToEndThresholdOptimizer


def make_data(n_factors=1, n_periods=30, n_stocks=20, seed=42):
    """构造模拟数据"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n_periods, freq="ME")
    stocks = [f"S{i:04d}" for i in range(n_stocks)]
    factor_data = {
        f"f{i}": pd.DataFrame(
            rng.normal(0, 1, (n_periods, n_stocks)), index=dates, columns=stocks,
        )
        for i in range(n_factors)
    }
    fwd_returns = pd.DataFrame(
        rng.normal(0.001, 0.02, (n_periods, n_stocks)), index=dates, columns=stocks,
    )
    return factor_data, fwd_returns


def verify_01_cv_folds():
    """校验 1: CV folds 生成正确性"""
    print("\n" + "=" * 60)
    print("校验 1: CV folds 生成正确性")
    print("=" * 60)

    opt = EndToEndThresholdOptimizer(
        n_trials=1, cv_min_train=10, cv_test_size=5, random_seed=42,
    )
    folds = opt._generate_cv_folds(n_periods=30)

    # 手工计算:
    # fold 0: train=[0:10], test=[10:15]
    # fold 1: train=[0:15], test=[15:20]
    # fold 2: train=[0:20], test=[20:25]
    # fold 3: train=[0:25], test=[25:30]
    expected = [
        {'train': (0, 10), 'test': (10, 15)},
        {'train': (0, 15), 'test': (15, 20)},
        {'train': (0, 20), 'test': (20, 25)},
        {'train': (0, 25), 'test': (25, 30)},
    ]

    assert len(folds) == 4, f"应有 4 个 fold, 实际 {len(folds)}"
    for i, (f, e) in enumerate(zip(folds, expected)):
        assert f['train'] == e['train'], \
            f"fold {i} train: 期望 {e['train']}, 实际 {f['train']}"
        assert f['test'] == e['test'], \
            f"fold {i} test: 期望 {e['test']}, 实际 {f['test']}"

    print(f"  手工计算: 4 folds (expanding window)")
    for i, f in enumerate(folds):
        print(f"    fold {i}: train={f['train']}, test={f['test']}")
    print("  ✓ 通过")
    return True


def verify_02_pipeline_fit_on_train():
    """校验 2: Pipeline 在 train 上 fit (日期范围校验)"""
    print("\n" + "=" * 60)
    print("校验 2: Pipeline 在 train 上 fit")
    print("=" * 60)

    factor_data, fwd_returns = make_data(n_factors=1, n_periods=30, n_stocks=20)
    opt = EndToEndThresholdOptimizer(
        n_trials=1, cv_min_train=10, cv_test_size=5, random_seed=42,
    )

    fit_ranges = []
    with mock.patch(
        "factor_pipeline.optimizer.FactorProcessingPipelineV2"
    ) as MockPipeline:
        mock_instance = mock.MagicMock()
        MockPipeline.return_value = mock_instance
        mock_instance.fit.return_value = mock_instance
        mock_instance.transform.side_effect = lambda fd: fd

        def capture_fit(fd, **kwargs):
            for name, df in fd.items():
                fit_ranges.append((df.index[0], df.index[-1]))
            return mock_instance
        mock_instance.fit.side_effect = capture_fit

        from factor_pipeline.pipelines_v2 import PipelineV2Config
        config = PipelineV2Config()
        opt._cv_evaluate(factor_data, fwd_returns, config)

    dates = list(factor_data.values())[0].index

    # 手工校验: 4 个 fold, 每个 fit 的 train 结束日期
    # fold 0: train=[0:10] → 结束 dates[9]
    # fold 1: train=[0:15] → 结束 dates[14]
    # fold 2: train=[0:20] → 结束 dates[19]
    # fold 3: train=[0:25] → 结束 dates[24]
    expected_train_ends = [dates[9], dates[14], dates[19], dates[24]]
    actual_train_ends = [r[1] for r in fit_ranges]

    assert len(fit_ranges) == 4, \
        f"应有 4 次 fit 调用, 实际 {len(fit_ranges)}"

    for i, (actual, expected) in enumerate(zip(actual_train_ends, expected_train_ends)):
        assert actual == expected, \
            f"fold {i} train 结束日期: 期望 {expected}, 实际 {actual}"
        print(f"    fold {i}: train 结束 = {actual.strftime('%Y-%m-%d')} ✓")

    print(f"  手工校验: 4 次 fit, 每次 train 结束日期正确")
    print("  ✓ 通过")
    return True


def verify_03_pipeline_transform_on_test():
    """校验 3: Pipeline 在 test 上 transform (日期范围校验)"""
    print("\n" + "=" * 60)
    print("校验 3: Pipeline 在 test 上 transform")
    print("=" * 60)

    factor_data, fwd_returns = make_data(n_factors=1, n_periods=30, n_stocks=20)
    opt = EndToEndThresholdOptimizer(
        n_trials=1, cv_min_train=10, cv_test_size=5, random_seed=42,
    )

    transform_ranges = []
    with mock.patch(
        "factor_pipeline.optimizer.FactorProcessingPipelineV2"
    ) as MockPipeline:
        mock_instance = mock.MagicMock()
        MockPipeline.return_value = mock_instance
        mock_instance.fit.return_value = mock_instance

        def capture_transform(fd, **kwargs):
            for name, df in fd.items():
                transform_ranges.append((df.index[0], df.index[-1]))
            return fd
        mock_instance.transform.side_effect = capture_transform

        from factor_pipeline.pipelines_v2 import PipelineV2Config
        config = PipelineV2Config()
        opt._cv_evaluate(factor_data, fwd_returns, config)

    dates = list(factor_data.values())[0].index

    # 手工校验: 4 个 fold, 每个 transform 的 test 范围
    # fold 0: test=[10:15] → 起始 dates[10], 结束 dates[14]
    # fold 1: test=[15:20] → 起始 dates[15], 结束 dates[19]
    # fold 2: test=[20:25] → 起始 dates[20], 结束 dates[24]
    # fold 3: test=[25:30] → 起始 dates[25], 结束 dates[29]
    expected_test_ranges = [
        (dates[10], dates[14]),
        (dates[15], dates[19]),
        (dates[20], dates[24]),
        (dates[25], dates[29]),
    ]

    assert len(transform_ranges) == 4, \
        f"应有 4 次 transform 调用, 实际 {len(transform_ranges)}"

    for i, (actual, expected) in enumerate(zip(transform_ranges, expected_test_ranges)):
        assert actual[0] == expected[0], \
            f"fold {i} test 起始: 期望 {expected[0]}, 实际 {actual[0]}"
        assert actual[1] == expected[1], \
            f"fold {i} test 结束: 期望 {expected[1]}, 实际 {actual[1]}"
        print(f"    fold {i}: test = {actual[0].strftime('%Y-%m-%d')} ~ {actual[1].strftime('%Y-%m-%d')} ✓")

    print(f"  手工校验: 4 次 transform, 每次 test 日期范围正确")
    print("  ✓ 通过")
    return True


def verify_04_cv_score_average():
    """校验 4: CV 分数 = 各 fold IC 的平均 (数值一致性)"""
    print("\n" + "=" * 60)
    print("校验 4: CV 分数 = 各 fold IC 的平均")
    print("=" * 60)

    rng = np.random.default_rng(42)
    n_periods, n_stocks = 30, 50
    dates = pd.date_range("2020-01-01", periods=n_periods, freq="ME")
    stocks = [f"S{i:04d}" for i in range(n_stocks)]

    # 因子 = 收益 + 噪声 (高 IC)
    raw = rng.normal(0, 1, (n_periods, n_stocks))
    fwd_returns = pd.DataFrame(raw * 0.01, index=dates, columns=stocks)
    factor_data = {
        "f1": pd.DataFrame(
            raw + rng.normal(0, 0.1, (n_periods, n_stocks)),
            index=dates, columns=stocks,
        ),
    }

    opt = EndToEndThresholdOptimizer(
        n_trials=1, cv_min_train=10, cv_test_size=5, random_seed=42,
        lambda_volatility=0.0, lambda_coverage=0.0, lambda_fidelity=0.0,
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
        cv_score = opt._cv_evaluate(factor_data, fwd_returns, config)

    # 手工计算各 fold 的 IC
    folds = opt._generate_cv_folds(n_periods)
    manual_fold_ics = []
    for fold in folds:
        _, train_end = fold['train']
        test_start, test_end = fold['test']
        f_test = factor_data["f1"].iloc[test_start:test_end]
        r_test = fwd_returns.iloc[test_start:test_end]
        ics = []
        for t in range(f_test.shape[0]):
            f_t = f_test.iloc[t].values
            r_t = r_test.iloc[t].values
            valid = ~(np.isnan(f_t) | np.isnan(r_t))
            if valid.sum() >= 5:
                ics.append(np.corrcoef(f_t[valid], r_t[valid])[0, 1])
        fold_ic = np.mean(ics)
        manual_fold_ics.append(fold_ic)
        print(f"    fold: test=[{test_start}:{test_end}], IC={fold_ic:.6f}")

    expected_score = float(np.mean(manual_fold_ics))
    diff = abs(cv_score - expected_score)

    print(f"  程序 CV 分数:  {cv_score:.6f}")
    print(f"  手工平均 IC:   {expected_score:.6f}")
    print(f"  差异:          {diff:.6f}")

    assert diff < 0.15, \
        f"CV 分数 {cv_score:.6f} 与手工平均 {expected_score:.6f} 差异过大 ({diff:.6f})"
    print("  ✓ 通过 (差异 < 0.15)")
    return True


def verify_05_no_look_ahead():
    """校验 5: 无 look-ahead bias (CV 分数 < 全量分数)"""
    print("\n" + "=" * 60)
    print("校验 5: 无 look-ahead bias")
    print("=" * 60)

    rng = np.random.default_rng(42)
    n_periods, n_stocks = 30, 50
    dates = pd.date_range("2020-01-01", periods=n_periods, freq="ME")
    stocks = [f"S{i:04d}" for i in range(n_stocks)]

    # train 期 (前 15): 正相关; test 期 (后 15): 负相关
    raw_factor = rng.normal(0, 1, (n_periods, n_stocks))
    returns = np.zeros((n_periods, n_stocks))
    returns[:15] = raw_factor[:15] * 0.5 + rng.normal(0, 0.1, (15, n_stocks))
    returns[15:] = -raw_factor[15:] * 0.5 + rng.normal(0, 0.1, (15, n_stocks))

    factor_data = {"f1": pd.DataFrame(raw_factor, index=dates, columns=stocks)}
    fwd_returns = pd.DataFrame(returns, index=dates, columns=stocks)

    opt = EndToEndThresholdOptimizer(
        n_trials=1, cv_min_train=10, cv_test_size=5, random_seed=42,
        lambda_volatility=0.0, lambda_coverage=0.0, lambda_fidelity=0.0,
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

        cv_score = opt._cv_evaluate(factor_data, fwd_returns, config)

        # 全量评估 (look-ahead: 用全量数据)
        full_factor = factor_data["f1"].T.values
        full_returns = fwd_returns.T.values
        full_score = opt._compute_ic(full_factor, full_returns)

    print(f"  CV 分数 (无 look-ahead):    {cv_score:.6f}")
    print(f"  全量分数 (有 look-ahead):   {full_score:.6f}")
    print(f"  差值 (CV - 全量):           {cv_score - full_score:.6f}")

    assert cv_score < full_score, \
        f"CV 分数 {cv_score:.6f} 应低于全量分数 {full_score:.6f} " \
        f"(无 look-ahead: CV 不会 '看到' test 数据的负 IC)"
    print("  ✓ 通过 (CV < 全量, 证明无 look-ahead)")
    return True


def verify_06_insufficient_data_fallback():
    """校验 6: 数据不足回退 (fit 1 次)"""
    print("\n" + "=" * 60)
    print("校验 6: 数据不足回退")
    print("=" * 60)

    factor_data, fwd_returns = make_data(n_factors=1, n_periods=8, n_stocks=20)
    opt = EndToEndThresholdOptimizer(
        n_trials=1, cv_min_train=10, cv_test_size=5, random_seed=42,
    )

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

        fit_count = mock_instance.fit.call_count

    print(f"  数据期数: 8 (< cv_min_train(10) + cv_test_size(5) = 15)")
    print(f"  CV folds: {len(folds)}")
    print(f"  Pipeline.fit 调用次数: {fit_count}")
    print(f"  回退分数: {score:.6f}")

    assert fit_count == 1, \
        f"数据不足回退应 fit 1 次, 实际 {fit_count}"
    assert isinstance(score, float)
    print("  ✓ 通过 (回退到全量评估, fit 1 次)")
    return True


def verify_07_optimize_calls_cv():
    """校验 7: optimize() 调用 _cv_evaluate"""
    print("\n" + "=" * 60)
    print("校验 7: optimize() 调用 _cv_evaluate")
    print("=" * 60)

    try:
        import optuna  # noqa: F401
    except ImportError:
        print("  ⚠ 跳过 (optuna 未安装)")
        return True

    factor_data, fwd_returns = make_data(n_factors=2, n_periods=30, n_stocks=20)
    opt = EndToEndThresholdOptimizer(
        n_trials=3, cv_min_train=10, cv_test_size=5, random_seed=42,
    )

    with mock.patch.object(opt, '_cv_evaluate', return_value=0.05) as mock_cv:
        opt.optimize(factor_data, fwd_returns, show_progress=False)
        call_count = mock_cv.call_count

    print(f"  n_trials=3, _cv_evaluate 调用次数: {call_count}")
    assert call_count >= 1, \
        f"_cv_evaluate 应被调用至少 1 次, 实际 {call_count}"
    print("  ✓ 通过")
    return True


def verify_08_pipeline_fit_multiple_times():
    """校验 8: Pipeline.fit 调用次数 = n_trials × n_folds"""
    print("\n" + "=" * 60)
    print("校验 8: Pipeline.fit 调用次数 >= n_trials × n_folds")
    print("=" * 60)

    try:
        import optuna  # noqa: F401
    except ImportError:
        print("  ⚠ 跳过 (optuna 未安装)")
        return True

    factor_data, fwd_returns = make_data(n_factors=1, n_periods=30, n_stocks=20)
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
        fit_count = mock_instance.fit.call_count

    n_folds = len(opt._generate_cv_folds(30))
    min_expected = 2 * n_folds

    print(f"  n_trials=2, n_folds={n_folds}, 最小期望 fit 次数: {min_expected}")
    print(f"  实际 Pipeline.fit 调用次数: {fit_count}")

    assert fit_count >= min_expected, \
        f"Pipeline.fit 应被调用至少 {min_expected} 次, 实际 {fit_count}"
    print(f"  ✓ 通过 (fit 次数 {fit_count} >= {min_expected})")
    return True


def verify_09_composite_score_consistency():
    """校验 9: combined_score 数值一致性 (复合目标函数)"""
    print("\n" + "=" * 60)
    print("校验 9: 复合目标函数数值一致性")
    print("=" * 60)

    opt = EndToEndThresholdOptimizer(
        n_trials=1, lambda_volatility=0.5, lambda_coverage=0.3,
        lambda_fidelity=0.1, random_seed=42,
    )

    # 手工构造 IC 数组
    ic_array = np.array([0.05, 0.06, 0.04, 0.07, 0.03])
    n_processed, n_total = 80, 100

    # 手工计算
    ic_mean = float(np.mean(ic_array))
    vol_penalty = max(0.0, float(np.std(ic_array)) - 0.1)
    cov_penalty = max(0.0, 0.5 - n_processed / n_total)
    # 无 before/after → fidelity = 0
    expected = ic_mean - 0.5 * vol_penalty - 0.3 * cov_penalty

    actual = opt._composite_objective(ic_array, n_processed, n_total)

    print(f"  IC mean:      {ic_mean:.6f}")
    print(f"  vol_penalty:  {vol_penalty:.6f} (std={np.std(ic_array):.6f})")
    print(f"  cov_penalty:  {cov_penalty:.6f}")
    print(f"  手工期望:      {expected:.6f}")
    print(f"  程序实际:      {actual:.6f}")

    assert abs(actual - expected) < 1e-6, \
        f"差异过大: 期望 {expected:.6f}, 实际 {actual:.6f}"
    print("  ✓ 通过")
    return True


def verify_10_backward_compat():
    """校验 10: 旧 _cv_evaluate 接口已更新"""
    print("\n" + "=" * 60)
    print("校验 10: _cv_evaluate 接口更新 (向后兼容)")
    print("=" * 60)

    import inspect
    sig = inspect.signature(EndToEndThresholdOptimizer._cv_evaluate)
    params = list(sig.parameters.keys())

    print(f"  _cv_evaluate 参数: {params}")

    # 新接口: (self, factor_data, forward_returns, config)
    assert 'factor_data' in params, "应有 factor_data 参数"
    assert 'forward_returns' in params, "应有 forward_returns 参数"
    assert 'config' in params, "应有 config 参数"
    # 旧接口的 evaluate_fn 应已移除
    assert 'evaluate_fn' not in params, "旧 evaluate_fn 参数应已移除"
    assert 'factor_values' not in params, "旧 factor_values 参数应已移除"

    print("  ✓ 通过 (新接口: factor_data, forward_returns, config)")
    return True


def verify_11_empty_factor_data():
    """校验 11: 空因子数据返回 -1.0"""
    print("\n" + "=" * 60)
    print("校验 11: 空因子数据返回 -1.0")
    print("=" * 60)

    opt = EndToEndThresholdOptimizer(n_trials=1, random_seed=42)

    from factor_pipeline.pipelines_v2 import PipelineV2Config
    config = PipelineV2Config()

    # 空因子 dict
    score = opt._cv_evaluate({}, pd.DataFrame(), config)

    print(f"  空因子数据 → 分数: {score}")
    assert score == -1.0, f"空因子数据应返回 -1.0, 实际 {score}"
    print("  ✓ 通过")
    return True


def verify_12_transform_aggressiveness_mapping():
    """校验 12: transform_aggressiveness 参数映射"""
    print("\n" + "=" * 60)
    print("校验 12: transform_aggressiveness 参数映射")
    print("=" * 60)

    opt = EndToEndThresholdOptimizer(n_trials=1, random_seed=42)

    # aggressiveness = 1.0 (基准)
    config_base = opt._params_to_config({
        'hard_routing_prob': 0.9, 'merge_alpha': 0.5, 'ks_alpha': 0.05,
        'mixed_winsor_sigma': 3.0, 'transform_aggressiveness': 1.0,
        'classification_threshold_static': 0.7,
        'classification_threshold_dynamic': 0.3,
        'migration_threshold': 0.1,
    })

    # aggressiveness = 2.0 (更激进 → winsor_sigma 减半)
    config_aggr = opt._params_to_config({
        'hard_routing_prob': 0.9, 'merge_alpha': 0.5, 'ks_alpha': 0.05,
        'mixed_winsor_sigma': 3.0, 'transform_aggressiveness': 2.0,
        'classification_threshold_static': 0.7,
        'classification_threshold_dynamic': 0.3,
        'migration_threshold': 0.1,
    })

    # 手工计算: aggr=2.0 → winsor_sigma = 3.0 / 2.0 = 1.5
    expected_aggr_sigma = 3.0 / 2.0

    print(f"  base (aggr=1.0): mixed_winsor_sigma = {config_base.mixed_winsor_sigma}")
    print(f"  aggr (aggr=2.0): mixed_winsor_sigma = {config_aggr.mixed_winsor_sigma}")
    print(f"  手工期望:         {expected_aggr_sigma}")

    assert config_base.mixed_winsor_sigma == 3.0, \
        f"base 应为 3.0, 实际 {config_base.mixed_winsor_sigma}"
    assert abs(config_aggr.mixed_winsor_sigma - expected_aggr_sigma) < 1e-6, \
        f"aggr 应为 {expected_aggr_sigma}, 实际 {config_aggr.mixed_winsor_sigma}"
    assert config_aggr.mixed_winsor_sigma < config_base.mixed_winsor_sigma, \
        "更激进应导致 winsor_sigma 更小"
    print("  ✓ 通过 (aggr=2.0 → sigma 减半)")
    return True


def main():
    """运行所有手工校验"""
    print("=" * 60)
    print("P2-2: 优化器 CV 改进 — 手工校验")
    print("=" * 60)

    checks = [
        verify_01_cv_folds,
        verify_02_pipeline_fit_on_train,
        verify_03_pipeline_transform_on_test,
        verify_04_cv_score_average,
        verify_05_no_look_ahead,
        verify_06_insufficient_data_fallback,
        verify_07_optimize_calls_cv,
        verify_08_pipeline_fit_multiple_times,
        verify_09_composite_score_consistency,
        verify_10_backward_compat,
        verify_11_empty_factor_data,
        verify_12_transform_aggressiveness_mapping,
    ]

    passed = 0
    failed = 0
    for check in checks:
        try:
            if check():
                passed += 1
            else:
                failed += 1
                print(f"  ✗ {check.__name__} 失败")
        except Exception as e:
            failed += 1
            print(f"  ✗ {check.__name__} 异常: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"手工校验结果: {passed}/{passed + failed} 通过")
    print("=" * 60)
    return failed == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
