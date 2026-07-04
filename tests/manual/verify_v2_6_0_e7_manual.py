# -*- coding: utf-8 -*-
"""v2.6.0 E7 手工校验脚本 (P3-15 Layer 3 显著性最终验证)

校验内容:
1. _validate_significance 返回字典结构 (含必要字段)
2. significance_ratio ∈ [0, 1]
3. warning 逻辑: ratio < 0.5 时非 None, ratio >= 0.5 时为 None
4. optimize(validate_significance=False) 默认不运行 (向后兼容)
5. optimize(validate_significance=True) 生成报告
6. 异常处理: Pipeline 失败时返回错误报告
"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


def _make_factor_and_returns(K=3, N=80, T=15, seed=42):
    """构造因子 + 前向收益"""
    rng = np.random.default_rng(seed)
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
    return factor_dict, fwd


def test_validate_significance_dict_structure():
    """校验 1: 返回字典含必要字段"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer

    optimizer = EndToEndThresholdOptimizer(n_trials=1)
    factor_dict, fwd = _make_factor_and_returns(K=3, N=80, T=15)

    best_params = {
        'hard_routing_prob': 0.9, 'merge_alpha': 0.5, 'ks_alpha': 0.05,
        'mixed_winsor_sigma': 3.0, 'transform_aggressiveness': 1.0,
        'classification_threshold_static': 0.7,
        'classification_threshold_dynamic': 0.3,
        'migration_threshold': 0.1,
    }

    report = optimizer._validate_significance(best_params, factor_dict, fwd)

    print(f"\n  [校验 1] 字典结构")
    print(f"    keys = {list(report.keys())}")
    assert isinstance(report, dict)
    for key in ['n_significant', 'n_total', 'significance_ratio', 'details', 'warning']:
        assert key in report, f"报告应含 {key}"
    print(f"    n_significant = {report['n_significant']}")
    print(f"    n_total = {report['n_total']}")
    print(f"    significance_ratio = {report['significance_ratio']:.4f}")
    print("  ✓ 校验 1 通过")


def test_significance_ratio_range():
    """校验 2: significance_ratio ∈ [0, 1]"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer

    optimizer = EndToEndThresholdOptimizer(n_trials=1)
    factor_dict, fwd = _make_factor_and_returns(K=3, N=80, T=15)

    best_params = {
        'hard_routing_prob': 0.9, 'merge_alpha': 0.5, 'ks_alpha': 0.05,
        'mixed_winsor_sigma': 3.0, 'transform_aggressiveness': 1.0,
        'classification_threshold_static': 0.7,
        'classification_threshold_dynamic': 0.3,
        'migration_threshold': 0.1,
    }

    report = optimizer._validate_significance(best_params, factor_dict, fwd)

    print(f"\n  [校验 2] ratio ∈ [0, 1]")
    print(f"    ratio = {report['significance_ratio']:.4f}")
    assert 0.0 <= report['significance_ratio'] <= 1.0
    print("  ✓ 校验 2 通过")


def test_warning_logic():
    """校验 3: warning 逻辑 (ratio < 0.5 时非 None)"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer

    optimizer = EndToEndThresholdOptimizer(n_trials=1)
    # 用 K=5 随机因子 (无真实 alpha), ratio 通常 < 0.5
    factor_dict, fwd = _make_factor_and_returns(K=5, N=80, T=15, seed=123)

    best_params = {
        'hard_routing_prob': 0.9, 'merge_alpha': 0.5, 'ks_alpha': 0.05,
        'mixed_winsor_sigma': 3.0, 'transform_aggressiveness': 1.0,
        'classification_threshold_static': 0.7,
        'classification_threshold_dynamic': 0.3,
        'migration_threshold': 0.1,
    }

    report = optimizer._validate_significance(best_params, factor_dict, fwd)

    print(f"\n  [校验 3] warning 逻辑")
    print(f"    ratio = {report['significance_ratio']:.4f}")
    print(f"    warning = {report['warning']}")
    if report['significance_ratio'] < 0.5:
        assert report['warning'] is not None, "ratio < 0.5 时 warning 必须非 None"
        assert '显著性比例' in report['warning']
        print("  ✓ 校验 3 通过 (warning 触发)")
    else:
        assert report['warning'] is None, "ratio >= 0.5 时 warning 必须为 None"
        print("  ✓ 校验 3 通过 (warning 未触发, ratio 偶然 >= 0.5)")


def test_optimize_default_off():
    """校验 4: optimize() 默认不运行显著性验证 (向后兼容)"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer

    optimizer = EndToEndThresholdOptimizer(n_trials=2)
    factor_dict, fwd = _make_factor_and_returns(K=3, N=30, T=15)

    optimizer.optimize(factor_dict, fwd, show_progress=False)

    print(f"\n  [校验 4] 默认 validate_significance=False")
    print(f"    significance_report = {optimizer.significance_report}")
    assert optimizer.significance_report is None, "默认应不运行验证"
    print("  ✓ 校验 4 通过")


def test_optimize_with_significance():
    """校验 5: optimize(validate_significance=True) 生成报告"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer

    optimizer = EndToEndThresholdOptimizer(n_trials=2)
    factor_dict, fwd = _make_factor_and_returns(K=3, N=30, T=15)

    optimizer.optimize(
        factor_dict, fwd, show_progress=False,
        validate_significance=True,
    )

    print(f"\n  [校验 5] validate_significance=True")
    print(f"    significance_report = {type(optimizer.significance_report)}")
    print(f"    n_significant = {optimizer.significance_report['n_significant']}")
    print(f"    n_total = {optimizer.significance_report['n_total']}")
    print(f"    ratio = {optimizer.significance_report['significance_ratio']:.4f}")
    assert optimizer.significance_report is not None, "应生成报告"
    assert isinstance(optimizer.significance_report, dict)
    assert 'n_significant' in optimizer.significance_report
    assert 'significance_ratio' in optimizer.significance_report
    print("  ✓ 校验 5 通过")


def test_exception_handling():
    """校验 6: Pipeline 失败时返回错误报告 (不抛异常)"""
    from factor_pipeline.optimizer import EndToEndThresholdOptimizer

    optimizer = EndToEndThresholdOptimizer(n_trials=1)

    # 构造空 factor_data (会触发 Pipeline 处理后无因子)
    best_params = {
        'hard_routing_prob': 0.9, 'merge_alpha': 0.5, 'ks_alpha': 0.05,
        'mixed_winsor_sigma': 3.0, 'transform_aggressiveness': 1.0,
        'classification_threshold_static': 0.7,
        'classification_threshold_dynamic': 0.3,
        'migration_threshold': 0.1,
    }

    # 空 factor_dict
    empty_factor_dict = {}
    rng = np.random.default_rng(42)
    fwd = pd.DataFrame(
        rng.standard_normal((15, 30)),
        index=pd.date_range('2020-01-01', periods=15, freq='D'),
        columns=[f's{i:03d}' for i in range(30)],
    )

    report = optimizer._validate_significance(best_params, empty_factor_dict, fwd)

    print(f"\n  [校验 6] 异常处理")
    print(f"    report = {report}")
    assert isinstance(report, dict)
    # 应返回 {n_significant:0, n_total:0, warning: '...'}
    assert report['n_significant'] == 0
    assert report['n_total'] == 0
    assert report['warning'] is not None
    print("  ✓ 校验 6 通过")


if __name__ == '__main__':
    print("=" * 70)
    print("v2.6.0 E7 手工校验 (P3-15 Layer 3 显著性最终验证)")
    print("=" * 70)
    test_validate_significance_dict_structure()
    test_significance_ratio_range()
    test_warning_logic()
    test_optimize_default_off()
    test_optimize_with_significance()
    test_exception_handling()
    print("\n" + "=" * 70)
    print("✓ 所有 E7 手工校验通过")
    print("=" * 70)
