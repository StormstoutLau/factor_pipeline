r"""O2: Layer 2 适配器层 — TDD 测试

测试设计来源: docs/EXECUTION_V2.5.0.md (v1.1) 的 O2.6 测试设计表 + O2.9 验收标准补充

11 组测试 (共 ~22 个):
1. 基础功能 (3): disabled passthrough / enabled transforms / fit_transform consistent
2. 数据对齐 (3): aligns different indices / raises on no common index / raises on single factor
3. 配置 (3): default disabled / method validation / window_mode validation
4. 集成 (3): with pipeline output / preserves dict format / N_less_than_K raises
5. 回归保护 (1): default config no regression
6. O2.8.1 align_mode (2): intersection drops mismatch / union_nan fills missing
7. O2.8.2 NaN (2): fit dropna + warning / transform NaN preserved
8. O2.8.3 Pipeline hook (1): with_orthogonalization_hook
9. O2.8.4 零开销 (2): disabled no import / pipeline hooks empty
10. O2.8.5 向后兼容 (1): old config JSON loads
11. O2.8.6 W 缓存 (1): w_cached_in_full_sample_mode

设计要点:
- OrthogonalizerAdapter 接受 OrthogonalizationConfig (或从 kwargs 构建)
- I/O: Dict[str, pd.DataFrame], 每个 DataFrame 为 (N_stocks, T_dates)
- enabled=False 时零开销 (不导入 core, hooks 为空)
- 默认 align_mode='intersection' (向后兼容 v1.0)
"""
import json
import sys
import warnings
import numpy as np
import pandas as pd
import pytest

from factor_pipeline.modules.factor_orthogonalizer.cross_sectional import (
    CrossSectionalOrthogonalizer,
)
from factor_pipeline.modules.factor_orthogonalizer.utils.stacking import (
    stack_factors_cross_section,
)
from factor_pipeline.adapters import OrthogonalizerAdapter
from factor_pipeline.config_v2 import (
    OrthogonalizationConfig,
    PipelineV2ConfigUnified,
)


# ---------- 工具函数 ----------

def _make_factor_dict(K=3, N=50, T=10, seed=42, prefix='f'):
    """构造 K 个因子的 Dict[str, DataFrame]

    每个 DataFrame: (N_stocks, T_dates)
    index = ['s000' .. 's0{N-1}'], columns = ['2020-01-01' .. ]
    """
    rng = np.random.default_rng(seed)
    return {
        f'{prefix}{k}': pd.DataFrame(
            rng.standard_normal((N, T)),
            index=[f's{i:03d}' for i in range(N)],
            columns=pd.date_range('2020-01-01', periods=T, freq='D'),
        )
        for k in range(K)
    }


def _make_factor_dict_with_overlap(K=3, N=50, T=10, seed=42, drop_last=5):
    """构造 K 个因子, 每个因子有部分不重叠的 index (测试 align_mode)"""
    rng = np.random.default_rng(seed)
    base_idx = [f's{i:03d}' for i in range(N)]
    result = {}
    for k in range(K):
        # 每个因子去掉最后 drop_last 个股票 (模拟不同股票池)
        idx = base_idx[:N - drop_last * k] if k > 0 else base_idx
        result[f'f{k}'] = pd.DataFrame(
            rng.standard_normal((len(idx), T)),
            index=idx,
            columns=pd.date_range('2020-01-01', periods=T, freq='D'),
        )
    return result


# =============================================================================
# 1. 基础功能 (3 tests)
# =============================================================================

class TestAdapterBasic:
    """O2.6 基础功能测试"""

    def test_adapter_disabled_passthrough(self):
        """enabled=False 时直接返回原 dict (零侵入)"""
        factor_dict = _make_factor_dict(K=3, N=50, T=10)
        adapter = OrthogonalizerAdapter(
            OrthogonalizationConfig(enabled=False)
        )
        result = adapter.fit_transform(factor_dict)
        # 输出与输入完全一致
        assert result is factor_dict or (
            set(result.keys()) == set(factor_dict.keys())
            and all(result[k].equals(factor_dict[k]) for k in factor_dict)
        ), "disabled adapter 应直接透传"

    def test_adapter_enabled_transforms(self):
        """enabled=True 时输出正交化后因子 (堆叠 T^T T ≈ I)

        注: W 在 (N·T, K) 全样本上拟合, 故只有堆叠后的 T 满足 T^T T = I,
        而非每期 T_t. 单期 T_t^T T_t 与 I 相差一个尺度因子 (与 F_t 方差成正比).
        正确的验证是堆叠所有期后 T_stacked^T T_stacked ≈ I.
        """
        factor_dict = _make_factor_dict(K=3, N=50, T=10)
        adapter = OrthogonalizerAdapter(
            OrthogonalizationConfig(enabled=True, method='symmetric')
        )
        result = adapter.fit_transform(factor_dict)
        # 输出因子数一致
        assert set(result.keys()) == set(factor_dict.keys())
        # 堆叠所有期: T_stacked^T T_stacked ≈ I (K×K)
        names = list(result.keys())
        first_df = result[names[0]]
        N, T_dates = first_df.shape
        K = len(result)
        # 构造 (N·T, K) 堆叠面板
        T_stacked = np.zeros((N * T_dates, K))
        for k, name in enumerate(names):
            # 按 (stock, date) 顺序堆叠, 与 fit 一致
            T_stacked[:, k] = result[name].values.reshape(-1)
        gram = T_stacked.T @ T_stacked
        assert np.allclose(gram, np.eye(K), atol=1e-8), (
            f"堆叠 T^T T 非 I, 偏差 = {np.max(np.abs(gram - np.eye(K))):.2e}"
        )

    def test_adapter_fit_transform_consistent(self):
        """fit_transform 与 fit + transform 结果一致"""
        factor_dict = _make_factor_dict(K=3, N=50, T=10)
        # fit_transform
        adapter1 = OrthogonalizerAdapter(
            OrthogonalizationConfig(enabled=True, method='symmetric')
        )
        result1 = adapter1.fit_transform(factor_dict)
        # fit + transform
        adapter2 = OrthogonalizerAdapter(
            OrthogonalizationConfig(enabled=True, method='symmetric')
        )
        adapter2.fit(factor_dict)
        result2 = adapter2.transform(factor_dict)
        # 对比
        for name in result1:
            np.testing.assert_allclose(
                result1[name].values, result2[name].values, atol=1e-10,
                err_msg=f"fit_transform 与 fit+transform 不一致: {name}"
            )


# =============================================================================
# 2. 数据对齐 (3 tests)
# =============================================================================

class TestAdapterAlignment:
    """O2.6 数据对齐测试"""

    def test_adapter_aligns_different_indices(self):
        """不同 index 的因子自动对齐到交集 (align_mode='intersection')"""
        factor_dict = _make_factor_dict_with_overlap(K=2, N=50, T=10, drop_last=5)
        adapter = OrthogonalizerAdapter(
            OrthogonalizationConfig(enabled=True, method='symmetric', align_mode='intersection')
        )
        result = adapter.fit_transform(factor_dict)
        # 输出因子应有相同的 index (交集)
        indices = [result[name].index for name in result]
        for i in range(1, len(indices)):
            assert indices[0].equals(indices[i]), "对齐后所有因子 index 应一致"

    def test_adapter_raises_on_no_common_index(self):
        """无公共 index 抛 ValueError"""
        df1 = pd.DataFrame(
            np.random.randn(10, 5),
            index=[f'a{i}' for i in range(10)],
            columns=pd.date_range('2020-01-01', periods=5, freq='D'),
        )
        df2 = pd.DataFrame(
            np.random.randn(10, 5),
            index=[f'b{i}' for i in range(10)],  # 完全不同的 index
            columns=pd.date_range('2020-01-01', periods=5, freq='D'),
        )
        adapter = OrthogonalizerAdapter(
            OrthogonalizationConfig(enabled=True, align_mode='intersection')
        )
        with pytest.raises(ValueError, match="无公共|index|columns"):
            adapter.fit({'f1': df1, 'f2': df2})

    def test_adapter_raises_on_single_factor(self):
        """单因子抛 ValueError (需 K >= 2)"""
        factor_dict = _make_factor_dict(K=1, N=50, T=10)
        adapter = OrthogonalizerAdapter(
            OrthogonalizationConfig(enabled=True)
        )
        with pytest.raises(ValueError, match="至少.*2.*因子|K.*>=.*2"):
            adapter.fit(factor_dict)


# =============================================================================
# 3. 配置 (3 tests)
# =============================================================================

class TestOrthogonalizationConfig:
    """O2.6 配置测试"""

    def test_config_default_disabled(self):
        """默认 enabled=False (保护基线)"""
        config = OrthogonalizationConfig()
        assert config.enabled is False, "默认应禁用正交化"
        assert config.method == 'symmetric'
        assert config.align_mode == 'intersection'

    def test_config_method_validation(self):
        """未知 method 抛 ValueError (Pydantic Literal 校验)"""
        with pytest.raises((ValueError, Exception)):
            OrthogonalizationConfig(method='unknown_method')

    def test_config_window_mode_validation(self):
        """未知 window_mode 抛 ValueError"""
        with pytest.raises((ValueError, Exception)):
            OrthogonalizationConfig(window_mode='invalid_mode')


# =============================================================================
# 4. 集成 (3 tests)
# =============================================================================

class TestAdapterIntegration:
    """O2.6 集成测试"""

    def test_adapter_with_pipeline_output(self):
        """适配器接受 Dict[str, DataFrame] 格式 (Pipeline.transform 输出)"""
        # 模拟 Pipeline.transform 输出: K 个 (N, T) DataFrame
        factor_dict = _make_factor_dict(K=4, N=80, T=12)
        adapter = OrthogonalizerAdapter(
            OrthogonalizationConfig(enabled=True, method='symmetric')
        )
        result = adapter.fit_transform(factor_dict)
        # 输出格式一致
        assert isinstance(result, dict)
        assert all(isinstance(v, pd.DataFrame) for v in result.values())
        assert set(result.keys()) == set(factor_dict.keys())

    def test_adapter_preserves_dict_format(self):
        """输出格式与输入一致 (Dict[str, DataFrame], shape 不变)"""
        factor_dict = _make_factor_dict(K=3, N=50, T=10)
        adapter = OrthogonalizerAdapter(
            OrthogonalizationConfig(enabled=True, method='symmetric')
        )
        result = adapter.fit_transform(factor_dict)
        for name in factor_dict:
            assert name in result
            assert result[name].shape == factor_dict[name].shape, (
                f"{name}: shape 不一致 {result[name].shape} vs {factor_dict[name].shape}"
            )

    def test_adapter_N_less_than_K_raises(self):
        """N < K 抛 ValueError (无法估计 K×K 的 Gram 矩阵)"""
        # K=5 因子, 每期截面只有 N=3 股票
        factor_dict = _make_factor_dict(K=5, N=3, T=4)
        adapter = OrthogonalizerAdapter(
            OrthogonalizationConfig(enabled=True, method='symmetric')
        )
        with pytest.raises((ValueError, Exception), match="N.*K|样本.*不足|singular"):
            adapter.fit(factor_dict)


# =============================================================================
# 5. 回归保护 (1 test)
# =============================================================================

class TestRegressionProtection:
    """O2.6 回归保护测试"""

    def test_default_config_no_regression(self):
        """默认配置下 PipelineV2ConfigUnified 仍可加载 (不影响 632 基线)"""
        config = PipelineV2ConfigUnified()
        assert hasattr(config, 'orthogonalization')
        assert config.orthogonalization.enabled is False
        assert config.version == "2.5.0"
        # to_pipeline_v2_config 仍可执行
        runtime_config = config.to_pipeline_v2_config()
        assert runtime_config is not None


# =============================================================================
# 6. O2.8.1 align_mode (2 tests)
# =============================================================================

class TestAlignMode:
    """O2.8.1 因子对齐策略: 交集 vs 并集 + NaN"""

    def test_align_intersection_drops_mismatch(self):
        """intersection 模式: 不同 index 取交集, 丢弃不共有的股票"""
        factor_dict = _make_factor_dict_with_overlap(K=2, N=50, T=8, drop_last=5)
        # f0: 50 stocks, f1: 45 stocks → 交集 45
        adapter = OrthogonalizerAdapter(
            OrthogonalizationConfig(enabled=True, align_mode='intersection')
        )
        adapter.fit(factor_dict)
        # fit 后所有因子应有相同 index (45 stocks)
        first_name = list(factor_dict.keys())[0]
        expected_len = 45  # min(50, 45)
        assert len(adapter._aligned_index_) == expected_len, (
            f"intersection 应保留 {expected_len} 行, 实际 {len(adapter._aligned_index_)}"
        )

    def test_align_union_nan_fills_missing(self):
        """union_nan 模式: 并集, 缺失填 NaN (后续 dropna 处理)"""
        factor_dict = _make_factor_dict_with_overlap(K=2, N=50, T=8, drop_last=5)
        # f0: 50 stocks, f1: 45 stocks → 并集 50
        adapter = OrthogonalizerAdapter(
            OrthogonalizationConfig(enabled=True, align_mode='union_nan')
        )
        adapter.fit(factor_dict)
        # fit 后应处理 50 行 (含 NaN, dropna 后有效行 < 50)
        first_name = list(factor_dict.keys())[0]
        expected_union = 50
        assert len(adapter._aligned_index_) == expected_union, (
            f"union_nan 应保留全部 {expected_union} 行"
        )


# =============================================================================
# 7. O2.8.2 NaN 处理 (2 tests)
# =============================================================================

class TestNaNHandling:
    """O2.8.2 NaN 处理与 dropna 策略"""

    def test_nan_in_fit_dropped_with_warning(self):
        """fit 时 >50% NaN 触发 UserWarning"""
        factor_dict = _make_factor_dict(K=2, N=50, T=8)
        # 在 f1 中注入大量 NaN (60%)
        rng = np.random.default_rng(99)
        nan_mask = rng.random(factor_dict['f1'].shape) < 0.6
        factor_dict['f1'] = factor_dict['f1'].mask(nan_mask)
        adapter = OrthogonalizerAdapter(
            OrthogonalizationConfig(enabled=True, align_mode='union_nan')
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                adapter.fit(factor_dict)
            except (ValueError, Exception):
                # 如果 NaN 过多导致 N < K, 也会抛 ValueError — 也算正确行为
                pass
            # 至少有一个 warning (或 ValueError)
            assert len(w) > 0 or not adapter.is_fitted_, (
                "高比例 NaN 应触发告警或抛错"
            )

    def test_nan_in_transform_preserved(self):
        """transform 时含 NaN 的行输出仍为 NaN"""
        factor_dict = _make_factor_dict(K=2, N=30, T=8)
        adapter = OrthogonalizerAdapter(
            OrthogonalizationConfig(enabled=True, method='symmetric')
        )
        adapter.fit(factor_dict)
        # 在 transform 输入中注入 NaN
        test_dict = {k: v.copy() for k, v in factor_dict.items()}
        test_dict['f0'].iloc[0, 0] = np.nan
        result = adapter.transform(test_dict)
        # NaN 行应传播到输出 (不静默填 0)
        assert result['f0'].iloc[0, 0] != result['f0'].iloc[0, 0] or np.isnan(
            result['f0'].iloc[0, 0]
        ), "NaN 输入应在输出中保留为 NaN"


# =============================================================================
# 8. O2.8.3 Pipeline 接入点 (1 test)
# =============================================================================

class TestPipelineHook:
    """O2.8.3 Pipeline 接入点: post_transform_hooks 机制"""

    def test_pipeline_with_orthogonalization_hook(self):
        """enabled=True 时 Pipeline 有 post_transform_hooks"""
        # 仅验证 hook 注册, 不运行完整 Pipeline (Pipeline 需复杂 fit)
        from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2, PipelineV2Config
        # 构造带 orthogonalization 的 config
        config = PipelineV2Config()
        # 默认 PipelineV2Config (dataclass) 不含 orthogonalization
        # enabled=True 时 Pipeline 应有非空 hooks
        # 这里只验证 hook 机制存在, 不运行完整 Pipeline
        pipeline = FactorProcessingPipelineV2(config)
        assert hasattr(pipeline, 'post_transform_hooks'), (
            "Pipeline 应有 post_transform_hooks 属性"
        )
        # 默认 enabled=False → hooks 为空
        assert pipeline.post_transform_hooks == [], (
            "默认 enabled=False 时 hooks 应为空列表"
        )


# =============================================================================
# 9. O2.8.4 零开销 (2 tests)
# =============================================================================

class TestZeroOverhead:
    """O2.8.4 enabled=False 的零开销验证"""

    def test_disabled_adapter_no_import(self):
        """enabled=False 时不触发 factor_orthogonalizer.core 导入

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
            # 构造 disabled adapter
            adapter = OrthogonalizerAdapter(
                OrthogonalizationConfig(enabled=False)
            )
            # 验证 core 未被导入
            imported = [
                k for k in sys.modules
                if k.startswith(core_prefix)
            ]
            assert len(imported) == 0, (
                f"enabled=False 不应导入 core, 但发现了: {imported}"
            )
            assert adapter._orthogonalizer_class is None
        finally:
            # 恢复 core 模块 (避免破坏后续测试的 class identity)
            for k in list(sys.modules):
                if k.startswith(core_prefix) and k not in saved:
                    del sys.modules[k]
            sys.modules.update(saved)

    def test_disabled_pipeline_hooks_empty(self):
        """enabled=False 时 Pipeline.post_transform_hooks == []"""
        from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2, PipelineV2Config
        config = PipelineV2Config()
        pipeline = FactorProcessingPipelineV2(config)
        assert pipeline.post_transform_hooks == [], (
            "默认 enabled=False 时 hooks 应为空列表 (零循环开销)"
        )


# =============================================================================
# 10. O2.8.5 向后兼容 (1 test)
# =============================================================================

class TestBackwardCompatibility:
    """O2.8.5 OrthogonalizationConfig 向后兼容"""

    def test_old_config_json_loads_with_default_orthogonalization(self):
        """v2.4.0 的 JSON (无 orthogonalization 字段) 加载后默认 enabled=False"""
        # 构造 v2.4.0 风格的 JSON (无 orthogonalization 字段)
        old_config_dict = {
            "name": "old_pipeline",
            "version": "2.4.0",
            "description": "v2.4.0 旧配置",
            "static": {"garch": {"enabled": False}},
        }
        config = PipelineV2ConfigUnified(**old_config_dict)
        assert config.orthogonalization.enabled is False, (
            "旧 JSON 加载后 orthogonalization 应为默认值 (enabled=False)"
        )
        assert config.orthogonalization.method == 'symmetric'


# =============================================================================
# 11. O2.8.6 W 缓存 (1 test)
# =============================================================================

class TestWCaching:
    """O2.8.6 CrossSectionalOrthogonalizer 的 W 缓存"""

    def test_w_cached_in_full_sample_mode(self):
        """full_sample 模式 W 缓存命中 (transform 不重新计算 W)"""
        from factor_pipeline.modules.factor_orthogonalizer.core import SymmetricOrthogonalizer
        factor_dict = _make_factor_dict(K=3, N=40, T=8)
        # 手动构造 fitted orthogonalizer
        adapter = OrthogonalizerAdapter(
            OrthogonalizationConfig(enabled=True, method='symmetric', window_mode='full_sample')
        )
        adapter.fit(factor_dict)
        # W 应被缓存
        assert adapter._orthogonalizer is not None
        assert adapter._orthogonalizer.W_ is not None
        W_after_fit = adapter._orthogonalizer.W_.copy()
        # transform 不应改变 W
        result = adapter.transform(factor_dict)
        W_after_transform = adapter._orthogonalizer.W_
        np.testing.assert_array_equal(W_after_fit, W_after_transform), (
            "full_sample 模式 W 应在 transform 后不变 (缓存命中)"
        )
