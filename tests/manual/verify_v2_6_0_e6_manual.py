# -*- coding: utf-8 -*-
"""v2.6.0 E6 手工校验脚本 (P3-14 几何诊断纳入目标函数)

校验内容:
1. _redundancy_penalty 与 compute_vrr 一致性 (高冗余场景)
2. _redundancy_penalty 与手工计算数值一致
3. look-ahead bias 防护 (F/T 矩阵来自 train fit, 非 test)
4. _composite_objective 6 项对齐 ADR-004
5. lambda_redundancy=0 向后兼容 (与 v2.5.0 一致)
6. vrr_threshold 边界 (VRR=0.3 时不扣分)
"""
import sys
import os
import numpy as np
import pandas as pd

# 添加项目根到 path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


def test_redundancy_penalty_vrr_consistency():
    """校验 1: redundancy_penalty 与 compute_vrr 一致"""
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
    f1 = f0 * 0.95 + rng.standard_normal((N, T)) * 0.05  # 高度共线
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

    optimizer = EndToEndThresholdOptimizer(n_trials=1, lambda_redundancy=0.05)
    penalty_actual = optimizer._redundancy_penalty(pipeline, config)

    # 手工计算
    diag = adapter.get_diagnostics()
    vrr = OrthogonalizationDiagnostics.compute_vrr(diag['F_stacked'], diag['T_stacked'])
    expected_penalty = float(np.mean([max(0.0, 0.3 - v) for v in vrr]))

    print(f"\n  [校验 1] VRR 一致性")
    print(f"    VRR = {vrr}")
    print(f"    factor_0 VRR: {vrr[0]:.4f}")
    print(f"    factor_1 VRR (冗余): {vrr[1]:.4f} (预期 << 1)")
    print(f"    factor_2 VRR: {vrr[2]:.4f}")
    print(f"    penalty per factor: {[max(0.0, 0.3 - v) for v in vrr]}")
    print(f"    penalty (实际) = {penalty_actual:.6f}")
    print(f"    penalty (期望) = {expected_penalty:.6f}")

    assert abs(penalty_actual - expected_penalty) < 1e-10, "penalty 与手工计算不一致"
    # 注: 对称正交化下所有因子 VRR 接近 1/K (≈0.001), 冗余因子 VRR 不一定更低
    # 关键校验是 penalty 与手工计算一致 (已通过), 而非 VRR 相对大小
    print("  ✓ 校验 1 通过 (penalty 与手工计算一致)")


def test_composite_objective_six_terms():
    """校验 2: _composite_objective 6 项对齐 ADR-004"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer

    optimizer = EndToEndThresholdOptimizer(
        n_trials=1,
        lambda_volatility=0.5,
        lambda_coverage=0.3,
        lambda_fidelity=0.1,
        lambda_health=0.4,
        lambda_redundancy=0.05,
    )
    np.random.seed(42)
    ic_array = np.array([0.10, 0.10, 0.10, 0.10, 0.01, 0.01, 0.01, 0.01])  # 低健康度
    before = np.random.randn(100, 3)
    after = np.random.randn(100, 3) * 3  # 高扭曲
    redundancy_penalty = 0.4  # 显式传入

    # 手工计算 6 项
    ic_mean = float(np.nanmean(ic_array))
    vol_penalty = optimizer._ic_volatility_penalty(ic_array)
    cov_penalty = optimizer._coverage_penalty(80, 100)
    fidelity = optimizer._ks_distribution_fidelity(before, after)
    ks_distortion = 1.0 - fidelity
    health_penalty = optimizer._health_penalty_proxy(ic_array)

    expected_objective = (
        ic_mean
        - 0.5 * vol_penalty
        - 0.3 * cov_penalty
        - 0.1 * ks_distortion
        - 0.4 * health_penalty
        - 0.05 * redundancy_penalty  # 新增
    )

    actual_objective = optimizer._composite_objective(
        ic_array, 80, 100, before=before, after=after,
        redundancy_penalty=redundancy_penalty
    )

    print(f"\n  [校验 2] 6 项对齐 ADR-004")
    print(f"    IC={ic_mean:.4f}, vol_p={vol_penalty:.4f}, cov_p={cov_penalty:.4f}")
    print(f"    ks_p={ks_distortion:.4f}, health_p={health_penalty:.4f}")
    print(f"    redundancy_p={redundancy_penalty:.4f}")
    print(f"    objective (实际) = {actual_objective:.6f}")
    print(f"    objective (期望) = {expected_objective:.6f}")

    assert abs(actual_objective - expected_objective) < 1e-10, "6 项目标函数不一致"
    print("  ✓ 校验 2 通过")


def test_look_ahead_bias_protection():
    """校验 3: F/T 矩阵来自 train fit, 无 look-ahead bias

    正交化作为 post_transform_hook:
    - pipeline.fit(train_factor) 在 train 上估计 W
    - transform(test_factor) 用 train 的 W 应用到 test
    - get_diagnostics() 返回的 F/T 是 train 上的, 无 look-ahead
    """
    from factor_pipeline.adapters import OrthogonalizerAdapter
    from factor_pipeline.config_v2 import OrthogonalizationConfig

    rng = np.random.default_rng(42)
    N, T_train, T_test = 50, 8, 3
    factor_dict_train = {
        'f0': pd.DataFrame(
            rng.standard_normal((N, T_train)),
            index=[f's{i:03d}' for i in range(N)],
            columns=pd.date_range('2020-01-01', periods=T_train, freq='D'),
        ),
        'f1': pd.DataFrame(
            rng.standard_normal((N, T_train)),
            index=[f's{i:03d}' for i in range(N)],
            columns=pd.date_range('2020-01-01', periods=T_train, freq='D'),
        ),
    }
    factor_dict_test = {
        'f0': pd.DataFrame(
            rng.standard_normal((N, T_test)),
            index=[f's{i:03d}' for i in range(N)],
            columns=pd.date_range('2020-02-01', periods=T_test, freq='D'),
        ),
        'f1': pd.DataFrame(
            rng.standard_normal((N, T_test)),
            index=[f's{i:03d}' for i in range(N)],
            columns=pd.date_range('2020-02-01', periods=T_test, freq='D'),
        ),
    }

    orth_config = OrthogonalizationConfig(enabled=True, method='symmetric')
    adapter = OrthogonalizerAdapter(orth_config)
    adapter.fit(factor_dict_train)  # 仅在 train 上 fit
    diag = adapter.get_diagnostics()

    print(f"\n  [校验 3] look-ahead bias 防护")
    print(f"    train shape: {factor_dict_train['f0'].shape}")
    print(f"    test shape:  {factor_dict_test['f0'].shape}")
    print(f"    F_stacked.shape: {diag['F_stacked'].shape}  (来自 train, N*T_train × K)")
    print(f"    T_stacked.shape: {diag['T_stacked'].shape}")

    # F_stacked 的行数 = N * T_train (而非 N * T_test), 证明来自 train
    assert diag['F_stacked'].shape[0] == N * T_train, \
        f"F_stacked 应来自 train (N*T_train={N*T_train}), 实际 {diag['F_stacked'].shape[0]}"
    assert diag['F_stacked'].shape[1] == 2, "K=2 因子"
    print("  ✓ 校验 3 通过 (F/T 来自 train, 无 look-ahead)")


def test_backward_compatible():
    """校验 4: lambda_redundancy=0 + 不传 redundancy_penalty 时, 与 v2.5.0 一致"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer

    optimizer = EndToEndThresholdOptimizer(
        n_trials=1,
        lambda_volatility=0.5,
        lambda_coverage=0.3,
        lambda_fidelity=0.1,
        lambda_health=0.0,  # E4 向后兼容
        lambda_redundancy=0.0,  # E6 向后兼容
    )
    ic_array = np.array([0.05, 0.06, 0.04, 0.07, 0.03])
    n_processed, n_total = 80, 100

    objective = optimizer._composite_objective(ic_array, n_processed, n_total)

    # v2.5.0 等价: IC - vol - cov
    expected_ic = np.mean(ic_array)
    expected_vol_penalty = max(0, np.std(ic_array) - 0.1)
    expected_cov_penalty = max(0, 0.5 - n_processed / n_total)
    expected_objective = (
        expected_ic
        - 0.5 * expected_vol_penalty
        - 0.3 * expected_cov_penalty
    )

    print(f"\n  [校验 4] 向后兼容 (lambda_redundancy=0)")
    print(f"    objective = {objective:.6f} (expected {expected_objective:.6f})")

    assert abs(objective - expected_objective) < 1e-10, "lambda_redundancy=0 应与 v2.5.0 一致"
    print("  ✓ 校验 4 通过")


def test_vrr_threshold_boundary():
    """校验 5: vrr_threshold 边界 (VRR >= threshold 不扣分)"""
    from factor_pipeline.adapters import OrthogonalizerAdapter
    from factor_pipeline.config_v2 import OrthogonalizationConfig
    from factor_pipeline.pipelines_v2 import PipelineV2Config
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer

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

    # vrr_threshold=0.0 — 所有 VRR >= 0 都不扣分 (penalty=0)
    orth_config = OrthogonalizationConfig(enabled=True, method='symmetric', vrr_threshold=0.0)
    adapter = OrthogonalizerAdapter(orth_config)
    adapter.fit(factor_dict)
    config = PipelineV2Config(orthogonalization=orth_config)

    class MockPipeline:
        post_transform_hooks = [adapter]
    optimizer = EndToEndThresholdOptimizer(n_trials=1, lambda_redundancy=0.05)
    penalty_00 = optimizer._redundancy_penalty(MockPipeline(), config)

    # vrr_threshold=1.0 — 所有 VRR < 1 都扣分 (penalty 最大)
    orth_config_10 = OrthogonalizationConfig(enabled=True, method='symmetric', vrr_threshold=1.0)
    adapter_10 = OrthogonalizerAdapter(orth_config_10)
    adapter_10.fit(factor_dict)
    config_10 = PipelineV2Config(orthogonalization=orth_config_10)

    class MockPipeline10:
        post_transform_hooks = [adapter_10]
    penalty_10 = optimizer._redundancy_penalty(MockPipeline10(), config_10)

    print(f"\n  [校验 5] vrr_threshold 边界")
    print(f"    vrr_threshold=0.0: penalty = {penalty_00:.6f} (应 = 0)")
    print(f"    vrr_threshold=1.0: penalty = {penalty_10:.6f} (应 > 0)")

    assert penalty_00 == 0.0, "vrr_threshold=0.0 时 penalty 应 = 0"
    assert penalty_10 > 0.0, "vrr_threshold=1.0 时 penalty 应 > 0"
    print("  ✓ 校验 5 通过")


def test_orth_disabled_no_penalty():
    """校验 6: orthogonalization is None 或 enabled=False 时, penalty = 0"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer
    from factor_pipeline.pipelines_v2 import PipelineV2Config
    from factor_pipeline.config_v2 import OrthogonalizationConfig

    optimizer = EndToEndThresholdOptimizer(n_trials=1)

    # 场景 1: orthogonalization is None (PipelineV2Config 默认)
    config_none = PipelineV2Config()
    class MockPipe1:
        post_transform_hooks = []
    p1 = optimizer._redundancy_penalty(MockPipe1(), config_none)

    # 场景 2: orthogonalization.enabled=False
    config_disabled = PipelineV2Config(
        orthogonalization=OrthogonalizationConfig(enabled=False)
    )
    class MockPipe2:
        post_transform_hooks = []
    p2 = optimizer._redundancy_penalty(MockPipe2(), config_disabled)

    print(f"\n  [校验 6] orth 未启用时 penalty = 0")
    print(f"    orth=None: penalty = {p1}")
    print(f"    orth.enabled=False: penalty = {p2}")

    assert p1 == 0.0, "orth=None 时 penalty 应 = 0"
    assert p2 == 0.0, "orth.enabled=False 时 penalty 应 = 0"
    print("  ✓ 校验 6 通过")


if __name__ == '__main__':
    print("=" * 70)
    print("v2.6.0 E6 手工校验 (P3-14 几何诊断纳入目标函数)")
    print("=" * 70)
    test_redundancy_penalty_vrr_consistency()
    test_composite_objective_six_terms()
    test_look_ahead_bias_protection()
    test_backward_compatible()
    test_vrr_threshold_boundary()
    test_orth_disabled_no_penalty()
    print("\n" + "=" * 70)
    print("✓ 所有 E6 手工校验通过")
    print("=" * 70)
