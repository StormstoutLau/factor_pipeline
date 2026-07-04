# -*- coding: utf-8 -*-
"""v2.6.0 E9 手工校验汇总脚本 (8 项 E1-E8)

校验内容 (8 项):
1. E2: migration_threshold 字段位置修正
2. E3: IC EWMA 时间加权
3. E4: health_penalty 代理指标 + KS 符号修正
4. E5: 正交化搜索空间
5. E6: redundancy_penalty VRR 一致性
6. E7: Layer 3 显著性验证
7. E8: 阈值漂移监测
8. 整体: ADR-004 6 项目标函数对齐
"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


def test_1_e2_migration_threshold_field_location():
    """1. E2: migration_threshold 字段位置修正"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer
    opt = EndToEndThresholdOptimizer(n_trials=1)
    config = opt._params_to_config({'migration_threshold': 0.15})
    assert config.migration_threshold == 0.15
    assert config.monitor.enable_smooth_transition is True
    assert not hasattr(config.monitor, 'migration_threshold'), \
        "MonitorConfig 不应有 migration_threshold 字段"
    print("✓ 1. E2 migration_threshold 字段位置修正")


def test_2_e3_ic_ewma_time_weighting():
    """2. E3: IC EWMA 时间加权"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer
    opt = EndToEndThresholdOptimizer(n_trials=1)

    np.random.seed(42)
    n_stocks, n_periods = 100, 20
    factor_values = np.random.randn(n_stocks, n_periods)
    forward_returns = 0.5 * factor_values + 0.5 * np.random.randn(n_stocks, n_periods)

    ic_equal = opt._compute_ic(factor_values, forward_returns, weighting='equal')
    ic_ewma = opt._compute_ic(factor_values, forward_returns, weighting='ewma', halflife=5)

    # 手工 EWMA
    ics = []
    for t in range(n_periods):
        ic = np.corrcoef(factor_values[:, t], forward_returns[:, t])[0, 1]
        ics.append(ic)
    ics = np.array(ics)
    alpha = 1.0 - np.exp(-np.log(2.0) / 5)
    weights = (1.0 - alpha) ** np.arange(n_periods)[::-1]
    weights /= weights.sum()
    expected_ewma = np.sum(ics * weights)

    assert abs(ic_ewma - expected_ewma) < 1e-6, f"EWMA IC 不一致: {ic_ewma} vs {expected_ewma}"
    print(f"✓ 2. E3 IC EWMA 时间加权 (equal={ic_equal:.4f}, ewma={ic_ewma:.4f})")


def test_3_e4_health_penalty_and_ks_sign():
    """3. E4: health_penalty 代理指标 + KS 符号修正"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer

    opt = EndToEndThresholdOptimizer(
        n_trials=1, lambda_volatility=0.5, lambda_coverage=0.3,
        lambda_fidelity=0.1, lambda_health=0.4,
    )
    # 低健康度 IC
    ic_low_health = np.array([0.10, 0.10, 0.10, 0.10, 0.01, 0.01, 0.01, 0.01])
    assert opt._health_penalty_proxy(ic_low_health) == 0.5

    # 高健康度 IC
    ic_high = np.array([0.05, 0.06, 0.05, 0.06, 0.05, 0.06, 0.05, 0.06])
    assert opt._health_penalty_proxy(ic_high) == 0.0

    # KS 符号修正: before == after 时 distortion = 0
    np.random.seed(42)
    before = np.random.randn(100, 3)
    after_same = before.copy()
    fidelity = opt._ks_distribution_fidelity(before, after_same)
    distortion = 1.0 - fidelity
    assert distortion < 0.01, f"相同分布 distortion 应 < 0.01, 得到 {distortion}"

    print("✓ 3. E4 health_penalty + KS 符号修正")


def test_4_e5_orthogonalization_search_space():
    """4. E5: 正交化搜索空间"""
    from factor_pipeline.optimizer import (
        EndToEndThresholdOptimizer, DEFAULT_SEARCH_SPACE_ORTH,
    )

    # 默认 search_orth=False: 8 维
    opt_default = EndToEndThresholdOptimizer(n_trials=1)
    assert len(opt_default.search_space) == 8

    # search_orth=True: 11 维 (8 + 3 orth_*)
    opt_orth = EndToEndThresholdOptimizer(n_trials=1, search_orth=True)
    assert len(opt_orth.search_space) == 11
    assert 'orth_method' in opt_orth.search_space
    assert 'orth_align_mode' in opt_orth.search_space
    assert 'orth_ridge_lambda' in opt_orth.search_space

    # orth_ridge_lambda 是 log-uniform
    assert opt_orth.search_space['orth_ridge_lambda'].get('log') is True

    # orth_method 是 categorical
    assert opt_orth.search_space['orth_method']['type'] == 'categorical'
    assert 'symmetric' in opt_orth.search_space['orth_method']['choices']

    print(f"✓ 4. E5 正交化搜索空间 (default=8维, orth=11维)")


def test_5_e6_redundancy_penalty_vrr():
    """5. E6: redundancy_penalty VRR 一致性"""
    from factor_pipeline.adapters import OrthogonalizerAdapter
    from factor_pipeline.config_v2 import OrthogonalizationConfig
    from factor_pipeline.pipelines_v2 import PipelineV2Config
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer
    from factor_pipeline.modules.factor_orthogonalizer.core.diagnostics import (
        OrthogonalizationDiagnostics
    )

    rng = np.random.default_rng(42)
    N, T = 100, 10
    f0 = rng.standard_normal((N, T))
    f1 = f0 * 0.95 + rng.standard_normal((N, T)) * 0.05
    f2 = rng.standard_normal((N, T))
    factor_dict = {
        'f0': pd.DataFrame(f0, index=[f's{i:03d}' for i in range(N)],
                           columns=pd.date_range('2020-01-01', periods=T, freq='D')),
        'f1': pd.DataFrame(f1, index=[f's{i:03d}' for i in range(N)],
                           columns=pd.date_range('2020-01-01', periods=T, freq='D')),
        'f2': pd.DataFrame(f2, index=[f's{i:03d}' for i in range(N)],
                           columns=pd.date_range('2020-01-01', periods=T, freq='D')),
    }

    orth_config = OrthogonalizationConfig(enabled=True, method='symmetric', vrr_threshold=0.3)
    adapter = OrthogonalizerAdapter(orth_config)
    adapter.fit(factor_dict)
    config = PipelineV2Config(orthogonalization=orth_config)

    class MockPipeline:
        post_transform_hooks = [adapter]
    pipeline = MockPipeline()

    opt = EndToEndThresholdOptimizer(n_trials=1, lambda_redundancy=0.05)
    penalty_actual = opt._redundancy_penalty(pipeline, config)

    # 手工计算
    diag = adapter.get_diagnostics()
    vrr = OrthogonalizationDiagnostics.compute_vrr(diag['F_stacked'], diag['T_stacked'])
    expected = float(np.mean([max(0.0, 0.3 - v) for v in vrr]))

    assert abs(penalty_actual - expected) < 1e-10
    assert penalty_actual > 0.0, "高冗余场景 penalty 应 > 0"

    # 6 项 ADR-004
    opt6 = EndToEndThresholdOptimizer(
        n_trials=1,
        lambda_volatility=0.5, lambda_coverage=0.3,
        lambda_fidelity=0.1, lambda_health=0.4, lambda_redundancy=0.05,
    )
    ic_array = np.array([0.05, 0.06, 0.04, 0.07, 0.03])
    obj_no_red = opt6._composite_objective(ic_array, 80, 100, redundancy_penalty=0.0)
    obj_with_red = opt6._composite_objective(ic_array, 80, 100, redundancy_penalty=0.5)
    diff = obj_no_red - obj_with_red
    assert abs(diff - 0.05 * 0.5) < 1e-10, f"redundancy 差值不对: {diff}"

    print(f"✓ 5. E6 redundancy_penalty VRR 一致性 (penalty={penalty_actual:.6f})")


def test_6_e7_layer3_significance():
    """6. E7: Layer 3 显著性验证"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer

    opt = EndToEndThresholdOptimizer(n_trials=1)
    rng = np.random.default_rng(42)
    N, T, K = 80, 15, 3
    factor_dict = {
        f'f{k}': pd.DataFrame(
            rng.standard_normal((N, T)),
            index=[f's{i:03d}' for i in range(N)],
            columns=pd.date_range('2020-01-01', periods=T, freq='D'),
        )
        for k in range(K)
    }
    fwd = pd.DataFrame(
        rng.standard_normal((T, N)),
        index=pd.date_range('2020-01-01', periods=T, freq='D'),
        columns=[f's{i:03d}' for i in range(N)],
    )

    best_params = {
        'hard_routing_prob': 0.9, 'merge_alpha': 0.5, 'ks_alpha': 0.05,
        'mixed_winsor_sigma': 3.0, 'transform_aggressiveness': 1.0,
        'classification_threshold_static': 0.7,
        'classification_threshold_dynamic': 0.3,
        'migration_threshold': 0.1,
    }

    report = opt._validate_significance(best_params, factor_dict, fwd)

    assert isinstance(report, dict)
    for key in ['n_significant', 'n_total', 'significance_ratio', 'warning']:
        assert key in report
    assert 0.0 <= report['significance_ratio'] <= 1.0

    # 空 factor_data 异常防护
    report_empty = opt._validate_significance(best_params, {}, fwd)
    assert report_empty['n_significant'] == 0
    assert report_empty['warning'] is not None

    print(f"✓ 6. E7 Layer 3 显著性验证 (ratio={report['significance_ratio']:.2f})")


def test_7_e8_threshold_drift_monitor():
    """7. E8: 阈值漂移监测"""
    from factor_pipeline.backtest.threshold_drift_monitor import ThresholdDriftMonitor

    monitor = ThresholdDriftMonitor(
        best_score=0.05, best_params={},
        halflife=5, decay_threshold=0.2, min_observations=5,
    )

    # 前 5 期无衰减
    for _ in range(5):
        v = monitor.update(0.05)
    assert not v['needs_research']

    # 后 5 期 40% 衰减
    for _ in range(5):
        v = monitor.update(0.03)
    assert v['needs_research']
    assert v['decay_ratio'] < 0.8

    # EWMA 手工
    monitor2 = ThresholdDriftMonitor(
        best_score=0.05, best_params={}, halflife=7, min_observations=1
    )
    scores = [0.05, 0.045, 0.04, 0.038]
    for s in scores:
        monitor2.update(s)
    alpha = 1.0 - np.exp(-np.log(2.0) / 7)
    ewma_manual = scores[0]
    for s in scores[1:]:
        ewma_manual = alpha * s + (1 - alpha) * ewma_manual
    assert abs(monitor2._compute_ewma() - ewma_manual) < 1e-10

    # reset
    monitor2.reset(best_score=0.06, best_params={'b': 2})
    assert monitor2.score_history == []
    assert monitor2.best_score == 0.06

    # get_history 副本
    h = monitor2.get_history()
    h.append(0.99)
    assert len(monitor2.score_history) == 0  # reset 后未更新

    print(f"✓ 7. E8 阈值漂移监测 (decay_ratio={v['decay_ratio']:.4f})")


def test_8_overall_adr004_six_terms():
    """8. 整体: ADR-004 6 项目标函数对齐 (IC-vol-cov-ks-health-redundancy)"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer

    opt = EndToEndThresholdOptimizer(
        n_trials=1,
        lambda_volatility=0.5, lambda_coverage=0.3,
        lambda_fidelity=0.1, lambda_health=0.4, lambda_redundancy=0.05,
    )

    np.random.seed(42)
    # 触发 health_penalty 的 IC 数组
    ic_array = np.array([0.10, 0.10, 0.10, 0.10, 0.01, 0.01, 0.01, 0.01])
    before = np.random.randn(100, 3)
    after = np.random.randn(100, 3) * 3  # 高扭曲
    redundancy_penalty = 0.4

    # 手工计算 6 项
    ic_mean = float(np.nanmean(ic_array))
    vol_penalty = opt._ic_volatility_penalty(ic_array)
    cov_penalty = opt._coverage_penalty(80, 100)
    fidelity = opt._ks_distribution_fidelity(before, after)
    ks_distortion = 1.0 - fidelity
    health_penalty = opt._health_penalty_proxy(ic_array)

    expected = (
        ic_mean
        - 0.5 * vol_penalty
        - 0.3 * cov_penalty
        - 0.1 * ks_distortion
        - 0.4 * health_penalty
        - 0.05 * redundancy_penalty
    )
    actual = opt._composite_objective(
        ic_array, 80, 100, before=before, after=after,
        redundancy_penalty=redundancy_penalty,
    )

    assert abs(actual - expected) < 1e-10, f"6 项目标函数不一致: {actual} vs {expected}"

    # 向后兼容: lambda_redundancy=0 + 不传 redundancy_penalty → v2.5.0 等价
    opt_compat = EndToEndThresholdOptimizer(
        n_trials=1, lambda_health=0.0, lambda_redundancy=0.0,
    )
    obj = opt_compat._composite_objective(ic_array[:5], 80, 100)
    expected_compat = (
        float(np.mean(ic_array[:5]))
        - 0.5 * max(0, np.std(ic_array[:5]) - 0.1)
        - 0.3 * max(0, 0.5 - 80 / 100)
    )
    assert abs(obj - expected_compat) < 1e-10

    print(f"✓ 8. ADR-004 6 项目标函数对齐 (objective={actual:.6f})")


if __name__ == '__main__':
    print("=" * 70)
    print("v2.6.0 E9 手工校验汇总 (8 项 E1-E8)")
    print("=" * 70)
    test_1_e2_migration_threshold_field_location()
    test_2_e3_ic_ewma_time_weighting()
    test_3_e4_health_penalty_and_ks_sign()
    test_4_e5_orthogonalization_search_space()
    test_5_e6_redundancy_penalty_vrr()
    test_6_e7_layer3_significance()
    test_7_e8_threshold_drift_monitor()
    test_8_overall_adr004_six_terms()
    print("\n" + "=" * 70)
    print("✓ 所有 v2.6.0 手工校验通过 (8/8)")
    print("=" * 70)
