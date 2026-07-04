r"""O2 手工数值校验脚本 — Layer 2 适配器层

校验内容:
1. Adapter fit + CrossSectionalOrthogonalizer transform 与独立实现对比 (精度 < 1e-10)
2. stack_factors_cross_section 堆叠顺序正确性
3. align_factors 三种模式行为正确性
4. W 缓存命中时 transform 结果不变
5. Pipeline.post_transform_hooks 半侵入式接入正确性
6. 旧 JSON 加载向后兼容
7. 零开销: enabled=False 不导入 core

运行方式:
    cd f:\Coding
    python -m factor_pipeline.tests.manual.test_adapter_manual
"""
import json
import sys
import warnings

import numpy as np
import pandas as pd

from factor_pipeline.adapters import OrthogonalizerAdapter
from factor_pipeline.config_v2 import (
    OrthogonalizationConfig,
    PipelineV2ConfigUnified,
)
from factor_pipeline.modules.factor_orthogonalizer.cross_sectional import (
    CrossSectionalOrthogonalizer,
)
from factor_pipeline.modules.factor_orthogonalizer.core.symmetric import (
    SymmetricOrthogonalizer,
)
from factor_pipeline.modules.factor_orthogonalizer.utils.stacking import (
    align_factors,
    stack_factors_cross_section,
)


# ---------- 工具函数 ----------

def _make_factor_dict(K=3, N=50, T=10, seed=42):
    rng = np.random.default_rng(seed)
    return {
        f'f{k}': pd.DataFrame(
            rng.standard_normal((N, T)),
            index=[f's{i:03d}' for i in range(N)],
            columns=pd.date_range('2020-01-01', periods=T, freq='D'),
        )
        for k in range(K)
    }


# ---------- 手工校验测试 ----------

def test_adapter_matches_manual_eigh():
    """Adapter fit_transform 与独立 eigh 实现对比 (精度 < 1e-10)

    独立实现:
    1. 堆叠 (N·T, K)
    2. G = F^T F
    3. eigh(G) → V, Λ
    4. W = V Λ^(-1/2) V^T
    5. T_stacked = F @ W
    6. 拆分回 (N, T, K)
    """
    factor_dict = _make_factor_dict(K=3, N=40, T=8, seed=7)
    adapter = OrthogonalizerAdapter(
        OrthogonalizationConfig(enabled=True, method='symmetric')
    )
    result = adapter.fit_transform(factor_dict)

    # 独立实现
    F_stacked, names, idx, cols = stack_factors_cross_section(factor_dict)
    G = F_stacked.T @ F_stacked
    eigvals, V = np.linalg.eigh(G)
    # 对称正交化: W = V Λ^(-1/2) V^T
    # 截断负/零特征值
    eigvals_clipped = np.where(eigvals > 1e-10, eigvals, 1e-10)
    Lambda_inv_sqrt = np.diag(1.0 / np.sqrt(eigvals_clipped))
    W_manual = V @ Lambda_inv_sqrt @ V.T
    T_manual = F_stacked @ W_manual

    # 对比 adapter 输出 (堆叠)
    K = len(names)
    N, T = len(idx), len(cols)
    T_adapter = np.zeros((N * T, K))
    for k, name in enumerate(names):
        T_adapter[:, k] = result[name].values.reshape(-1)

    np.testing.assert_allclose(
        T_adapter, T_manual, atol=1e-10,
        err_msg="Adapter 输出与独立 eigh 实现不一致"
    )
    print(f"  Adapter vs manual eigh: max_diff = {np.max(np.abs(T_adapter - T_manual)):.2e}")


def test_stack_factors_order():
    """stack_factors_cross_section 堆叠顺序正确性

    堆叠顺序: (stock_0_date_0, stock_0_date_1, ..., stock_1_date_0, ...)
    即 F.values.reshape(-1) 按行优先 (C order)
    """
    factor_dict = _make_factor_dict(K=2, N=3, T=4, seed=1)
    F_stacked, names, idx, cols = stack_factors_cross_section(factor_dict)

    # 验证: F_stacked[n*T + t, k] == factor_dict[fk].iloc[n, t]
    for n in range(3):
        for t in range(4):
            for k in range(2):
                expected = factor_dict[names[k]].iloc[n, t]
                actual = F_stacked[n * 4 + t, k]
                assert abs(actual - expected) < 1e-15, (
                    f"堆叠顺序错误: n={n}, t={t}, k={k}, "
                    f"expected={expected}, actual={actual}"
                )
    print(f"  堆叠顺序正确: (N·T, K) = {F_stacked.shape}")


def test_align_intersection_drops_mismatch():
    """intersection 模式取交集"""
    df1 = pd.DataFrame(
        np.random.randn(5, 3),
        index=['a', 'b', 'c', 'd', 'e'],
        columns=['d1', 'd2', 'd3'],
    )
    df2 = pd.DataFrame(
        np.random.randn(4, 3),
        index=['b', 'c', 'd', 'f'],  # 共有 b,c,d
        columns=['d1', 'd2', 'd3'],
    )
    aligned = align_factors({'f1': df1, 'f2': df2}, 'intersection')
    assert len(aligned['f1'].index) == 3, f"intersection 应保留 3 行, 实际 {len(aligned['f1'].index)}"
    assert list(aligned['f1'].index) == ['b', 'c', 'd']
    print(f"  intersection: 5∩4 = {len(aligned['f1'].index)} 行")


def test_align_union_nan_fills_missing():
    """union_nan 模式取并集, 缺失填 NaN"""
    df1 = pd.DataFrame(
        np.random.randn(3, 2),
        index=['a', 'b', 'c'],
        columns=['d1', 'd2'],
    )
    df2 = pd.DataFrame(
        np.random.randn(2, 2),
        index=['b', 'd'],  # 共有 b, 缺 a,c, 新增 d
        columns=['d1', 'd2'],
    )
    aligned = align_factors({'f1': df1, 'f2': df2}, 'union_nan')
    # 并集: a, b, c, d (4 行)
    assert len(aligned['f1'].index) == 4
    assert len(aligned['f2'].index) == 4
    # f2 在 a, c 行应为 NaN
    assert aligned['f2'].loc['a', 'd1'] != aligned['f2'].loc['a', 'd1']  # NaN
    assert aligned['f2'].loc['c', 'd1'] != aligned['f2'].loc['c', 'd1']  # NaN
    # f2 在 b 行应有值
    assert aligned['f2'].loc['b', 'd1'] == aligned['f2'].loc['b', 'd1']
    print(f"  union_nan: 3∪2 = {len(aligned['f1'].index)} 行, NaN 已填充")


def test_w_caching_in_full_sample_mode():
    """full_sample 模式 W 缓存: transform 后 W 不变"""
    factor_dict = _make_factor_dict(K=3, N=40, T=8, seed=3)
    adapter = OrthogonalizerAdapter(
        OrthogonalizationConfig(enabled=True, method='symmetric', window_mode='full_sample')
    )
    adapter.fit(factor_dict)
    W_after_fit = adapter._orthogonalizer.W_.copy()

    # 多次 transform, W 应不变
    _ = adapter.transform(factor_dict)
    W_after_t1 = adapter._orthogonalizer.W_.copy()
    _ = adapter.transform(factor_dict)
    W_after_t2 = adapter._orthogonalizer.W_.copy()

    np.testing.assert_array_equal(W_after_fit, W_after_t1)
    np.testing.assert_array_equal(W_after_fit, W_after_t2)
    print(f"  W 缓存命中: 3 次 transform 后 W 不变, shape={W_after_fit.shape}")


def test_nan_in_transform_preserved():
    """transform 时含 NaN 的行输出仍为 NaN"""
    factor_dict = _make_factor_dict(K=2, N=30, T=8, seed=5)
    adapter = OrthogonalizerAdapter(
        OrthogonalizationConfig(enabled=True, method='symmetric')
    )
    adapter.fit(factor_dict)

    test_dict = {k: v.copy() for k, v in factor_dict.items()}
    test_dict['f0'].iloc[0, 0] = np.nan
    result = adapter.transform(test_dict)

    # NaN 行应传播到所有因子的同一 (stock, date)
    for name in result:
        val = result[name].iloc[0, 0]
        assert np.isnan(val), f"{name} 在 NaN 行应为 NaN, 实际 {val}"
    print("  NaN 传播正确: 所有因子在 NaN 行输出 NaN")


def test_old_config_json_backward_compatible():
    """旧 JSON (无 orthogonalization) 加载后默认 enabled=False"""
    old_json = {
        "name": "old_pipeline",
        "version": "2.4.0",
        "description": "v2.4.0 旧配置",
        "static": {"garch": {"enabled": False}},
    }
    config = PipelineV2ConfigUnified(**old_json)
    assert config.orthogonalization.enabled is False
    assert config.orthogonalization.method == 'symmetric'
    assert config.orthogonalization.align_mode == 'intersection'
    # 旧 version 字段保留 (不强制升级)
    assert config.version == "2.4.0"
    print(f"  旧 JSON 加载成功: ortho.enabled={config.orthogonalization.enabled}, version={config.version}")


def test_disabled_adapter_no_import():
    """enabled=False 时不导入 factor_orthogonalizer.core

    注: 此测试会临时移除已加载的 core 模块以验证零导入, 必须在 finally
    中恢复 sys.modules, 否则会破坏后续测试的 class identity (is 检查).
    """
    # 快照 core 模块状态
    core_prefix = 'factor_pipeline.modules.factor_orthogonalizer.core'
    saved = {
        k: sys.modules[k]
        for k in list(sys.modules)
        if k.startswith(core_prefix)
    }
    # 移除已加载的 core 模块
    for k in list(sys.modules):
        if k.startswith(core_prefix):
            del sys.modules[k]
    try:
        adapter = OrthogonalizerAdapter(
            OrthogonalizationConfig(enabled=False)
        )
        imported = [
            k for k in sys.modules
            if k.startswith(core_prefix)
        ]
        assert len(imported) == 0, f"enabled=False 不应导入 core, 发现: {imported}"
        assert adapter._orthogonalizer_class is None
        assert adapter.is_fitted_ is False
        print("  零开销验证: enabled=False 时 core 未被导入")
    finally:
        # 恢复 core 模块 (避免破坏后续测试的 class identity)
        for k in list(sys.modules):
            if k.startswith(core_prefix) and k not in saved:
                del sys.modules[k]
        sys.modules.update(saved)


def test_pipeline_hooks_empty_when_disabled():
    """默认配置下 Pipeline.post_transform_hooks == []"""
    from factor_pipeline.pipelines_v2 import (
        FactorProcessingPipelineV2,
        PipelineV2Config,
    )
    config = PipelineV2Config()
    pipeline = FactorProcessingPipelineV2(config)
    assert pipeline.post_transform_hooks == []
    print(f"  Pipeline hooks 为空 (enabled=False), len={len(pipeline.post_transform_hooks)}")


def test_pipeline_hook_registered_when_enabled():
    """enabled=True 时 Pipeline.post_transform_hooks 含 OrthogonalizerAdapter"""
    from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2
    from factor_pipeline.config_v2 import (
        OrthogonalizationConfig,
        PipelineV2ConfigUnified,
    )
    # 构造 enabled=True 的 unified config
    unified = PipelineV2ConfigUnified(
        orthogonalization=OrthogonalizationConfig(enabled=True)
    )
    runtime = unified.to_pipeline_v2_config()
    pipeline = FactorProcessingPipelineV2(runtime)
    assert len(pipeline.post_transform_hooks) == 1
    hook = pipeline.post_transform_hooks[0]
    assert hook.enabled is True
    assert hook.method == 'symmetric'
    print(f"  Pipeline hooks 注册成功: 1 个 OrthogonalizerAdapter, method={hook.method}")


def test_to_pipeline_v2_config_passes_orthogonalization():
    """to_pipeline_v2_config 透传 orthogonalization 对象"""
    unified = PipelineV2ConfigUnified(
        orthogonalization=OrthogonalizationConfig(
            enabled=True, method='ridge', ridge_lambda=2.5
        )
    )
    runtime = unified.to_pipeline_v2_config()
    assert runtime.orthogonalization is not None
    assert runtime.orthogonalization.enabled is True
    assert runtime.orthogonalization.method == 'ridge'
    assert runtime.orthogonalization.ridge_lambda == 2.5
    print(
        f"  透传成功: method={runtime.orthogonalization.method}, "
        f"lambda={runtime.orthogonalization.ridge_lambda}"
    )


def test_cross_sectional_orthogonalizer_matches_manual():
    """CrossSectionalOrthogonalizer 与手动 F_t @ W 对比"""
    factor_dict = _make_factor_dict(K=3, N=40, T=8, seed=11)
    F_stacked, names, idx, cols = stack_factors_cross_section(factor_dict)

    # 手动 fit SymmetricOrthogonalizer
    ortho = SymmetricOrthogonalizer()
    ortho.fit(F_stacked)
    W = ortho.W_

    # CrossSectionalOrthogonalizer
    cs = CrossSectionalOrthogonalizer(ortho)
    result = cs.transform(factor_dict)

    # 手动计算每期 T_t = F_t @ W
    for t_idx, date in enumerate(cols):
        for n_idx, stock in enumerate(idx):
            f_vec = np.array([factor_dict[n].loc[stock, date] for n in names])
            t_manual = f_vec @ W
            for k, name in enumerate(names):
                t_actual = result[name].loc[stock, date]
                assert abs(t_manual[k] - t_actual) < 1e-10, (
                    f"{stock}@{date} {name}: manual={t_manual[k]}, actual={t_actual}"
                )
    print(f"  CrossSectional vs manual: {len(idx)*len(cols)*len(names)} 点全部匹配 (atol=1e-10)")


# ---------- 独立运行入口 ----------

def _run_all_manual_tests():
    """独立运行所有手工校验, 打印详细结果"""
    tests = [
        ("Adapter vs manual eigh", test_adapter_matches_manual_eigh),
        ("stack_factors 堆叠顺序", test_stack_factors_order),
        ("align intersection", test_align_intersection_drops_mismatch),
        ("align union_nan", test_align_union_nan_fills_missing),
        ("W 缓存 (full_sample)", test_w_caching_in_full_sample_mode),
        ("NaN transform 传播", test_nan_in_transform_preserved),
        ("旧 JSON 向后兼容", test_old_config_json_backward_compatible),
        ("零开销 (disabled)", test_disabled_adapter_no_import),
        ("Pipeline hooks 空 (disabled)", test_pipeline_hooks_empty_when_disabled),
        ("Pipeline hook 注册 (enabled)", test_pipeline_hook_registered_when_enabled),
        ("to_pipeline_v2_config 透传", test_to_pipeline_v2_config_passes_orthogonalization),
        ("CrossSectional vs manual", test_cross_sectional_orthogonalizer_matches_manual),
    ]
    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1
    print(f"\n手工校验结果: {passed} passed, {failed} failed (共 {len(tests)} 项)")
    return failed == 0


if __name__ == "__main__":
    import sys
    success = _run_all_manual_tests()
    sys.exit(0 if success else 1)
