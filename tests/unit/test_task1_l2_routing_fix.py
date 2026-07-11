"""TDD: L2 Routing Ablation Fix — _override_routing rebuilds factor_pipelines"""
import numpy as np
import pandas as pd
import pytest
from factor_pipeline.backtest.ablation_runner import AblationRunner, AblationConfig
from factor_pipeline.pipelines_v2 import PipelineV2Config


def _make_synthetic_data():
    """Create synthetic factor data that triggers different routing."""
    np.random.seed(42)
    T, N = 100, 50
    dates = pd.date_range('2020-01-01', periods=T, freq='ME')
    stocks = [f'S{i:02d}' for i in range(N)]

    # Factor 1: high persistence → static
    f1 = np.zeros((T, N))
    f1[0] = np.random.randn(N)
    for t in range(1, T):
        f1[t] = 0.95 * f1[t-1] + np.random.randn(N) * 0.1

    # Factor 2: white noise → dynamic
    f2 = np.random.randn(T, N)

    factor_data = {
        'static_factor': pd.DataFrame(f1, index=dates, columns=stocks),
        'dynamic_factor': pd.DataFrame(f2, index=dates, columns=stocks),
    }
    fwd_returns = pd.DataFrame(np.random.randn(T, N) * 0.02,
                               index=dates, columns=stocks)
    industry = pd.Series({s: f'I{i % 5}' for i, s in enumerate(stocks)})
    return factor_data, fwd_returns, industry


class TestL2RoutingFix:
    """L2 路由消融在 Hard routing 后的兼容性修复"""

    def test_override_routing_static_creates_pipeline(self):
        """_override_routing='static' → factor_pipelines has static pipeline"""
        factor_data, fwd_returns, industry = _make_synthetic_data()
        runner = AblationRunner(base_config=PipelineV2Config())

        config = AblationConfig(
            name='L2_all_static', layer='L2', routing_mode='static',
            baseline_level='B3',
        )
        result = runner.run_single(config, factor_data, fwd_returns, industry)
        assert result is not None
        assert 'ic_mean' in result.metrics
        assert not np.isnan(result.metrics['ic_mean'])

    def test_override_routing_dynamic_creates_pipeline(self):
        """_override_routing='dynamic' → factor_pipelines has dynamic pipeline"""
        factor_data, fwd_returns, industry = _make_synthetic_data()
        runner = AblationRunner(base_config=PipelineV2Config())

        config = AblationConfig(
            name='L2_all_dynamic', layer='L2', routing_mode='dynamic',
            baseline_level='B3',
        )
        result = runner.run_single(config, factor_data, fwd_returns, industry)
        assert result is not None
        assert 'ic_mean' in result.metrics
        assert not np.isnan(result.metrics['ic_mean'])

    def test_override_routing_mixed_creates_pipeline(self):
        """_override_routing='mixed' → factor_pipelines has mixed pipeline"""
        factor_data, fwd_returns, industry = _make_synthetic_data()
        runner = AblationRunner(base_config=PipelineV2Config())

        config = AblationConfig(
            name='L2_all_mixed', layer='L2', routing_mode='mixed',
            baseline_level='B3',
        )
        result = runner.run_single(config, factor_data, fwd_returns, industry)
        assert result is not None
        assert 'ic_mean' in result.metrics
        assert not np.isnan(result.metrics['ic_mean'])

    def test_override_routing_random_creates_pipeline(self):
        """_override_routing='random' → no crash"""
        factor_data, fwd_returns, industry = _make_synthetic_data()
        runner = AblationRunner(base_config=PipelineV2Config())

        config = AblationConfig(
            name='L2_random_routing', layer='L2', routing_mode='random',
            random_seed=42, baseline_level='B3',
        )
        result = runner.run_single(config, factor_data, fwd_returns, industry)
        assert result is not None
        assert 'ic_mean' in result.metrics
        assert not np.isnan(result.metrics['ic_mean'])

    def test_full_l2_routing_pipeline(self):
        """完整 L2 routing 5 config 全部不崩溃"""
        factor_data, fwd_returns, industry = _make_synthetic_data()
        runner = AblationRunner(base_config=PipelineV2Config())

        b3_config = AblationConfig(name='B3', layer='baseline', baseline_level='B3')
        b3_result = runner.run_single(b3_config, factor_data, fwd_returns, industry)

        l2_results = runner.run_l2(
            factor_data, fwd_returns, industry, b3_full_result=b3_result
        )
        assert len(l2_results) == 5
        for r in l2_results:
            assert 'ic_mean' in r.metrics, f"{r.config.name} should have ic_mean"
            assert not np.isnan(r.metrics['ic_mean']), f"{r.config.name} ic_mean is NaN"
