"""Task 6 TDD: Pipeline 中间数据日志 — transform 后可访问每步中间输出"""
import numpy as np
import pandas as pd
import pytest
from factor_pipeline.pipelines_v2 import PipelineV2Config, FactorProcessingPipelineV2


@pytest.fixture
def small_panel():
    np.random.seed(42)
    T, N = 30, 20
    data = np.random.randn(T, N)
    dates = pd.date_range('2020-01-02', periods=T, freq='B')
    stocks = [f'S{i:02d}' for i in range(N)]
    df = pd.DataFrame(data, index=dates, columns=stocks)
    fwd = pd.DataFrame(np.random.randn(T, N) * 0.02, index=dates, columns=stocks)
    ind = pd.Series({s: f'I{i % 5}' for i, s in enumerate(stocks)})
    return {'test_factor': df}, fwd, ind


class TestIntermediateDataLogging:
    """Pipeline._intermediate_data 提供每步中间输出"""

    def test_intermediate_data_empty_before_fit(self):
        """fit 前 intermediate_data 应为空"""
        cfg = PipelineV2Config()
        pipe = FactorProcessingPipelineV2(cfg)
        # Before fit, _intermediate_data should exist but be empty
        assert hasattr(pipe, '_intermediate_data')
        assert pipe._intermediate_data == {}

    def test_intermediate_data_populated_after_transform(self, small_panel):
        """transform 后 intermediate_data 包含每个因子的处理步骤"""
        factor_data, fwd, ind = small_panel
        cfg = PipelineV2Config()
        pipe = FactorProcessingPipelineV2(cfg)
        pipe.fit(factor_data, industry_data=ind)
        result = pipe.transform(factor_data)

        imd = pipe._intermediate_data
        assert 'test_factor' in imd, f"should have test_factor in intermediate, got: {list(imd.keys())}"
        factor_steps = imd['test_factor']
        assert isinstance(factor_steps, dict), f"expected dict of steps, got {type(factor_steps)}"
        # At minimum should have imputation/outlier/decoupling/neutralization/scaling steps
        print(f"  Steps recorded: {list(factor_steps.keys())}")
        assert len(factor_steps) >= 1, f"should have >=1 steps, got {len(factor_steps)}: {list(factor_steps.keys())}"

    def test_intermediate_data_shapes_match(self, small_panel):
        """中间输出形状应匹配输入"""
        factor_data, fwd, ind = small_panel
        cfg = PipelineV2Config()
        pipe = FactorProcessingPipelineV2(cfg)
        pipe.fit(factor_data, industry_data=ind)
        result = pipe.transform(factor_data)

        imd = pipe._intermediate_data
        for step_name, step_df in imd['test_factor'].items():
            assert isinstance(step_df, pd.DataFrame), \
                f"step {step_name} should be DataFrame, got {type(step_df)}"
            assert step_df.shape[0] == factor_data['test_factor'].shape[0], \
                f"step {step_name} rows mismatch: {step_df.shape[0]} vs {factor_data['test_factor'].shape[0]}"

    def test_get_intermediate_data_returns_copy(self, small_panel):
        """get_intermediate_data() 返回副本，修改不影响内部状态"""
        factor_data, fwd, ind = small_panel
        cfg = PipelineV2Config()
        pipe = FactorProcessingPipelineV2(cfg)
        pipe.fit(factor_data, industry_data=ind)
        pipe.transform(factor_data)

        imd = pipe.get_intermediate_data()
        assert 'test_factor' in imd
        # Modify returned copy
        imd['test_factor'] = None
        # Internal state unchanged
        assert pipe._intermediate_data['test_factor'] is not None
