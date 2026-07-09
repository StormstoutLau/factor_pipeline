# -*- coding: utf-8 -*-
"""
ABLATION E1: 5 模块 enabled 开关测试 (TDD)

规格: docs/EXECUTION_ABLATION_V3.0.0.md §1 (E1)
验收: Imputer 保留 NaN / Winsorizer/Scaler/Neutralizer 返回 X 原样 / Orthogonalizer 已有
"""

import pytest
import pandas as pd
import numpy as np

from factor_pipeline.adapters import (
    ImputerAdapter,
    ProcessingAdapter,
    NeutralizerAdapter,
)


# =============================================================================
# E1-T1: ImputerAdapter enabled 开关
# =============================================================================

class TestImputerEnabled:
    """ImputerAdapter enabled 开关测试"""

    def test_default_enabled_is_true(self):
        """构造时不传 enabled → enabled=True"""
        adapter = ImputerAdapter(strategy='median')
        assert adapter.enabled is True

    def test_enabled_false_fit_is_identity(self):
        """enabled=False → fit 不拟合内部 imputer, is_fitted=True"""
        adapter = ImputerAdapter(strategy='median', enabled=False)
        df = pd.DataFrame({'A': [1.0, np.nan, 3.0], 'B': [4.0, 5.0, np.nan]})
        result = adapter.fit(df)
        assert result is adapter
        assert adapter.is_fitted is True
        assert adapter._imputer is None

    def test_enabled_false_transform_preserves_nan(self):
        """enabled=False → transform 保留 NaN (identity)"""
        adapter = ImputerAdapter(strategy='median', enabled=False)
        df = pd.DataFrame({'A': [1.0, np.nan, 3.0], 'B': [4.0, 5.0, np.nan]})
        adapter.fit(df)
        result = adapter.transform(df)
        # identity: 保留 NaN
        assert result.isnull().sum().sum() == df.isnull().sum().sum()
        pd.testing.assert_frame_equal(result, df)

    def test_enabled_false_no_external_dependency(self):
        """enabled=False → 构造时不导入外部模块 (_imputer_class=None)"""
        adapter = ImputerAdapter(strategy='median', enabled=False)
        assert adapter._imputer_class is None


# =============================================================================
# E1-T2: ProcessingAdapter (Winsorizer/Scaler) enabled 开关
# =============================================================================

class TestProcessingAdapterEnabled:
    """ProcessingAdapter enabled 开关测试"""

    def test_outlier_enabled_false_identity(self):
        """outlier enabled=False → transform 返回原样 (不截断)"""
        adapter = ProcessingAdapter(process_type='outlier', method='auto', enabled=False)
        df = pd.DataFrame({'A': [1.0, 100.0, 3.0], 'B': [4.0, 5.0, 6.0]})
        adapter.fit(df)
        result = adapter.transform(df)
        pd.testing.assert_frame_equal(result, df)

    def test_standardization_enabled_false_identity(self):
        """standardization enabled=False → transform 返回原样 (不标准化)"""
        adapter = ProcessingAdapter(process_type='standardization', method='auto', enabled=False)
        df = pd.DataFrame({'A': [1.0, 2.0, 3.0], 'B': [4.0, 5.0, 6.0]})
        adapter.fit(df)
        result = adapter.transform(df)
        pd.testing.assert_frame_equal(result, df)

    def test_transformation_ignores_enabled(self):
        """transformation 类型 enabled 永远 True (不消融)"""
        adapter = ProcessingAdapter(process_type='transformation', method='auto', enabled=False)
        assert adapter.enabled is True

    def test_outlier_default_enabled_is_true(self):
        """outlier 默认 enabled=True"""
        adapter = ProcessingAdapter(process_type='outlier', method='auto')
        assert adapter.enabled is True

    def test_enabled_false_fit_skips_inner(self):
        """enabled=False → fit 不初始化 _processor"""
        adapter = ProcessingAdapter(process_type='outlier', method='auto', enabled=False)
        df = pd.DataFrame({'A': [1.0, 2.0, 3.0]})
        adapter.fit(df)
        assert adapter._processor is None


# =============================================================================
# E1-T3: NeutralizerAdapter enabled 开关
# =============================================================================

class TestNeutralizerEnabled:
    """NeutralizerAdapter enabled 开关测试"""

    def test_default_enabled_is_true(self):
        """默认 enabled=True"""
        adapter = NeutralizerAdapter(neutralization_type='industry')
        assert adapter.enabled is True

    def test_enabled_false_identity(self):
        """enabled=False → transform 返回原样 (不中性化)"""
        adapter = NeutralizerAdapter(neutralization_type='industry', enabled=False)
        df = pd.DataFrame({'A': [1.0, 2.0, 3.0], 'B': [4.0, 5.0, 6.0]})
        adapter.fit(df)
        result = adapter.transform(df)
        pd.testing.assert_frame_equal(result, df)

    def test_enabled_false_fit_skips(self):
        """enabled=False → fit 不拟合中性化模型"""
        adapter = NeutralizerAdapter(neutralization_type='industry', enabled=False)
        df = pd.DataFrame({'A': [1.0, 2.0, 3.0], 'B': [4.0, 5.0, 6.0]})
        adapter.fit(df)
        assert adapter._neutralizer is None
        assert adapter.is_fitted is True


# =============================================================================
# E1-T4: 管线级 module_enabled 透传 (规格 §1.7 E1-T4)
# =============================================================================

from factor_pipeline.pipelines_v2 import (
    StaticFactorPipeline,
    DynamicFactorPipeline,
    MixedFactorPipeline,
    PipelineV2Config,
    FactorProcessingPipelineV2,
)


def _make_factor_df(n_periods=40, n_stocks=10, seed=42, with_nan=True):
    """生成小规模合成因子数据 (含 NaN)"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2022-01-01', periods=n_periods, freq='ME')
    stocks = [f'S{i:02d}' for i in range(n_stocks)]
    data = rng.standard_normal((n_periods, n_stocks)) * 2.0 + 1.0  # 非零均值, 非单位方差
    df = pd.DataFrame(data, index=dates, columns=stocks)
    if with_nan:
        df.iloc[0, 0] = np.nan
        df.iloc[5, 2] = np.nan
    return df


class TestPipelineModuleEnabled:
    """管线级 module_enabled 透传测试 (E1-T4)"""

    def test_module_enabled_none_default_behavior(self):
        """module_enabled=None → 全部启用, 与既有行为一致 (输出被标准化)"""
        df = _make_factor_df(with_nan=True)
        pipeline = StaticFactorPipeline(module_enabled=None)
        result = pipeline.fit_transform(df)
        # 全启用: NaN 被插补, 标准化后均值≈0
        assert result.isnull().sum().sum() == 0, "imputer 启用应填充所有 NaN"
        col_means = result.mean(axis=0)
        assert np.allclose(col_means, 0, atol=1e-8), "标准化后列均值应≈0"

    def test_module_enabled_imputer_false(self):
        """module_enabled={'imputer': False} → 输出保留 NaN"""
        df = _make_factor_df(with_nan=True)
        nan_before = df.isnull().sum().sum()
        assert nan_before > 0, "测试前置: 输入应有 NaN"
        pipeline = StaticFactorPipeline(module_enabled={'imputer': False})
        result = pipeline.fit_transform(df)
        # imputer 关闭 → NaN 保留
        nan_after = result.isnull().sum().sum()
        assert nan_after > 0, "imputer=False 应保留 NaN"
        # 验证 imputer adapter enabled=False
        imputer_step = dict(pipeline.steps)['imputer']
        assert imputer_step.enabled is False

    def test_module_enabled_all_false(self):
        """module_enabled 全 False → 输出 = 输入 (全 identity)

        使用 DynamicFactorPipeline (无 transformation 步骤):
        imputer off → 保留 NaN; neutralizer off → 跳过解耦; scaler off → 跳过标准化
        """
        df = _make_factor_df(with_nan=True)
        me = {'imputer': False, 'winsorizer': False,
              'scaler': False, 'neutralizer': False}
        pipeline = DynamicFactorPipeline(module_enabled=me)
        result = pipeline.fit_transform(df)
        # 全 identity: NaN 保留
        assert result.isnull().sum().sum() == df.isnull().sum().sum()
        # 全 identity: 非NaN值不变
        mask = ~df.isnull()
        np.testing.assert_allclose(result.values[mask], df.values[mask])
        # scaler off → std 不被强制为 1
        assert not np.allclose(result.std(axis=0), 1.0, atol=1e-6)

    def test_create_pipeline_passes_module_enabled(self):
        """_create_pipeline 透传 module_enabled 到各管道构造器"""
        config = PipelineV2Config(module_enabled={'imputer': False, 'scaler': False})
        pipeline_v2 = FactorProcessingPipelineV2(config)
        me = config.module_enabled
        # static 管道: imputer + scaler 应关闭
        static_pipe = pipeline_v2._create_pipeline('static', {}, me)
        steps_dict = dict(static_pipe.steps)
        assert steps_dict['imputer'].enabled is False, "static imputer 应关闭"
        assert steps_dict['standardize'].enabled is False, "static scaler 应关闭"
        # winsorizer/neutralizer 默认启用
        assert steps_dict['outlier'].enabled is True, "winsorizer 未指定 → 启用"
        # dynamic 管道: imputer + scaler 应关闭
        dynamic_pipe = pipeline_v2._create_pipeline('dynamic', {}, me)
        assert dynamic_pipe._imputer_enabled is False
        assert dynamic_pipe._scaler_enabled is False
        # mixed 管道: imputer + scaler 应关闭
        mixed_pipe = pipeline_v2._create_pipeline('mixed', {}, me)
        assert mixed_pipe._imputer_enabled is False
        assert mixed_pipe._scaler_enabled is False


# =============================================================================
# E1-T5: 向后兼容回归 (规格 §1.7 E1-T5)
# =============================================================================

class TestBackwardCompat:
    """向后兼容回归测试 (E1-T5)"""

    def test_existing_pipeline_config_no_module_enabled(self):
        """PipelineV2Config 无 module_enabled 字段 → 默认 None → 全启用"""
        config = PipelineV2Config()
        assert config.module_enabled is None, "默认 module_enabled 应为 None"
        # 构造管道不传 module_enabled → 全启用
        static_pipe = StaticFactorPipeline()
        steps_dict = dict(static_pipe.steps)
        assert steps_dict['imputer'].enabled is True
        assert steps_dict['outlier'].enabled is True
        assert steps_dict['neutralize'].enabled is True
        assert steps_dict['standardize'].enabled is True

    def test_existing_tests_pass(self):
        """既有 StaticFactorPipeline/DynamicFactorPipeline/MixedFactorPipeline 测试不破坏"""
        df = _make_factor_df(n_periods=50, n_stocks=15, with_nan=False)
        # 既有构造方式 (不传 module_enabled) 应正常工作
        for cls, kwargs in [
            (StaticFactorPipeline, {}),
            (DynamicFactorPipeline, {}),
            (MixedFactorPipeline, {}),
        ]:
            pipeline = cls(**kwargs)
            result = pipeline.fit_transform(df)
            assert result.shape == df.shape, f"{cls.__name__} 输出形状应与输入一致"
            assert pipeline.is_fitted is True, f"{cls.__name__} 应标记为已拟合"
