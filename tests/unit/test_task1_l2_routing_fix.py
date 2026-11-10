"""TDD: L2 Routing Ablation — 统一管道 2 臂模式映射 (v3.4.0 ADR-042)

run_l2 收缩为 2 臂 (L2_unified + L2_dynamic); routing_mode 在 _run_pipeline
中于管道实例化前注入 modified_config.pipeline_mode ('unified' | 'dynamic_ab').
"""
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock

from factor_pipeline.backtest.ablation_runner import AblationRunner, AblationConfig
from factor_pipeline.pipelines_v2 import PipelineV2Config


def _make_synthetic_data():
    """Create synthetic factor data (dates × stocks, 2 factors)."""
    np.random.seed(42)
    T, N = 100, 50
    dates = pd.date_range('2020-01-01', periods=T, freq='ME')
    stocks = [f'S{i:02d}' for i in range(N)]

    # Factor 1: high persistence (AR1)
    f1 = np.zeros((T, N))
    f1[0] = np.random.randn(N)
    for t in range(1, T):
        f1[t] = 0.95 * f1[t-1] + np.random.randn(N) * 0.1

    # Factor 2: white noise
    f2 = np.random.randn(T, N)

    factor_data = {
        'static_factor': pd.DataFrame(f1, index=dates, columns=stocks),
        'dynamic_factor': pd.DataFrame(f2, index=dates, columns=stocks),
    }
    fwd_returns = pd.DataFrame(np.random.randn(T, N) * 0.02,
                               index=dates, columns=stocks)
    industry = pd.Series({s: f'I{i % 5}' for i, s in enumerate(stocks)})
    return factor_data, fwd_returns, industry


def _capture_injected_pipeline_mode(routing_mode):
    """直接调 _run_pipeline (patch 构造点), 返回注入后的 modified_config."""
    factor_data, fwd_returns, industry = _make_synthetic_data()
    runner = AblationRunner(base_config=PipelineV2Config())

    with patch('factor_pipeline.pipelines_v2.FactorProcessingPipelineV2') as mock_cls:
        mock_instance = MagicMock()
        # transform 返回输入副本, 保证 _collect_rho_steps 可安全消费
        mock_instance.transform.side_effect = (
            lambda fd: {name: df.copy() for name, df in fd.items()}
        )
        mock_cls.return_value = mock_instance

        config = AblationConfig(
            name=f'L2_{routing_mode}', layer='L2', routing_mode=routing_mode,
            baseline_level='B3',
        )
        runner._run_pipeline(config, factor_data, fwd_returns, industry)

    return mock_cls.call_args[0][0]


class TestL2RoutingFix:
    """L2 路由消融 2 臂 (v3.4.0 ADR-042): 模式映射 + run_l2 计数"""

    def test_unified_mode_maps_to_unified_pipeline_mode(self):
        """routing_mode='unified' → pipeline_mode='unified' (统一横截面秩管道)"""
        modified_config = _capture_injected_pipeline_mode('unified')
        assert modified_config.pipeline_mode == 'unified'

    def test_dynamic_mode_maps_to_dynamic_ab_pipeline_mode(self):
        """routing_mode='dynamic' → pipeline_mode='dynamic_ab' (整臂 A/B 动态管道)"""
        modified_config = _capture_injected_pipeline_mode('dynamic')
        assert modified_config.pipeline_mode == 'dynamic_ab'

    def test_run_l2_returns_2_results(self):
        """完整 run_l2 → 2 臂 (L2_unified + L2_dynamic), 无 full 臂"""
        factor_data, fwd_returns, industry = _make_synthetic_data()
        runner = AblationRunner(base_config=PipelineV2Config())

        l2_results = runner.run_l2(factor_data, fwd_returns, industry)
        assert len(l2_results) == 2
        names = [r.config.name for r in l2_results]
        assert 'L2_unified' in names
        assert 'L2_dynamic' in names
        for r in l2_results:
            assert 'ic_mean' in r.metrics, f"{r.config.name} should have ic_mean"
            assert not np.isnan(r.metrics['ic_mean']), f"{r.config.name} ic_mean is NaN"
