# -*- coding: utf-8 -*-
"""v3.4.4: AblationRunner decoupler 消融臂测试 (TDD).

规格: docs/EXECUTION_V3.4.4_ABLATION_DECOUPLER_ARM.md §3 (D1-D11)
      + v3.4.5 D12/D13 (run_l2 / run_baselines 市值转发断链)
上游: docs/research/RESEARCH_ABLATION_DECOUPLER_ARM.md
      docs/private/DESIGN_ABLATION_DECOUPLER_ARM.md

核心约束:
  - decoupler 只在 pipeline_mode='dynamic_ab' 下生效 (ADR-042/ADR-045)
  - 参照臂与实验臂必须同模式, 仅 enable_ar 不同
  - 默认 run_l1 的 6 臂 / unified rho 5 键 / 报告 5 列保持不变
"""

import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock

from factor_pipeline.backtest.ablation_runner import (
    AblationConfig,
    AblationResult,
    AblationRunner,
)


# =============================================================================
# 测试数据
# =============================================================================

def _make_factor_data(n_periods=24, n_stocks=15, n_factors=2, seed=42):
    np.random.seed(seed)
    dates = pd.date_range('2022-01-01', periods=n_periods, freq='ME')
    stocks = [f'S{i:03d}' for i in range(n_stocks)]
    factor_data = {}
    for f_idx in range(n_factors):
        data = np.random.randn(n_periods, n_stocks)
        factor_data[f'factor_{f_idx}'] = pd.DataFrame(
            data, index=dates, columns=stocks)
    return factor_data


def _make_ar_factor_data(n_periods=40, n_stocks=30, seed=7):
    """AR(1) 面板: 让 Dynamic 管道的 AR 解耦有可拟合结构."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2020-01-31', periods=n_periods, freq='ME')
    stocks = [f'S{i:03d}' for i in range(n_stocks)]
    eps = rng.standard_normal((n_periods, n_stocks))
    data = np.zeros((n_periods, n_stocks))
    data[0] = eps[0]
    for t in range(1, n_periods):
        data[t] = 0.8 * data[t - 1] + eps[t]
    return {'ar_factor': pd.DataFrame(data, index=dates, columns=stocks)}


def _make_fwd_returns(index, columns, seed=99):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.standard_normal((len(index), len(columns))) * 0.02,
        index=index, columns=columns,
    )


def _make_industry_data(columns, seed=7):
    rng = np.random.default_rng(seed)
    industries = [f'IND_{i}' for i in range(3)]
    return pd.Series(rng.choice(industries, size=len(columns)), index=columns)


def _make_result(name, rho_step, seed=42, layer='L1'):
    rng = np.random.default_rng(seed)
    n = 30
    ic = rng.standard_normal(n) * 0.05 + 0.02
    ls = rng.standard_normal(n) * 0.01 + 0.002
    return AblationResult(
        config=AblationConfig(name=name, layer=layer),
        metrics={
            'ic_mean': float(np.mean(ic)),
            'ic_std': float(np.std(ic, ddof=1)),
            'icir': float(np.mean(ic) / np.std(ic, ddof=1)),
            'sharpe_ls': float(np.mean(ls) / np.std(ls, ddof=1)),
            'sharpe_lo': np.nan,
            'turnover_mean': np.nan,
            'max_drawdown': np.nan,
            'hit_rate': float(np.mean(ic > 0)),
        },
        ic_series=ic,
        ls_return_series=ls,
        rho_step=rho_step,
        ortho_diagnostics={'condition_number': 5.0, 'vrr_mean': 0.9},
        n_factors=1,
        n_periods=n,
        runtime_sec=0.1,
    )


def _capture_run_single(monkeypatch, runner):
    """捕获 run_l1_decoupler / run_l1 的 run_single 入参."""
    captured = []

    def mock_run_single(config, fd, fr, industry_data=None, market_cap_data=None,
                        **kwargs):
        captured.append({
            'config': config,
            'market_cap_data': market_cap_data,
        })
        rho = {step: 1.0 for step in AblationRunner.L1_MODULES}
        return _make_result(config.name, rho, layer=config.layer)

    monkeypatch.setattr(runner, 'run_single', mock_run_single)
    return captured


# =============================================================================
# D1-D3: 臂契约
# =============================================================================

class TestDecouplerArmContract:

    def test_run_l1_decoupler_returns_two_arms(self, monkeypatch):
        """D1: 返回 [L1_dynamic_ref, L1_decoupler_off]."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        captured = _capture_run_single(monkeypatch, runner)

        results = runner.run_l1_decoupler(
            _make_factor_data(), _make_factor_data(),)

        assert len(results) == 2
        assert [r.config.name for r in results] == [
            'L1_dynamic_ref', 'L1_decoupler_off']
        for cap in captured:
            assert cap['config'].layer == 'L1'
            assert cap['config'].baseline_level == 'B3'
            assert cap['config']._is_trivial is False

    def test_ref_arm_routing_is_dynamic(self, monkeypatch):
        """D2: 参照臂 routing_mode='dynamic', module_enabled=None."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        captured = _capture_run_single(monkeypatch, runner)

        runner.run_l1_decoupler(_make_factor_data(), _make_factor_data())

        ref = captured[0]['config']
        assert ref.routing_mode == 'dynamic'
        assert ref.module_enabled is None

    def test_off_arm_disables_decoupler_only(self, monkeypatch):
        """D3: 实验臂仅关闭 decoupler, 仍走 dynamic."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        captured = _capture_run_single(monkeypatch, runner)

        runner.run_l1_decoupler(_make_factor_data(), _make_factor_data())

        off = captured[1]['config']
        assert off.routing_mode == 'dynamic'
        assert off.module_enabled == {'decoupler': False}


# =============================================================================
# D4-D5: 真实 _run_pipeline 注入
# =============================================================================

class TestDecouplerArmPipelineInjection:

    def test_pipeline_mode_injected_dynamic_ab(self):
        """D4: 两臂均注入 pipeline_mode='dynamic_ab'."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        factor_data = _make_factor_data()
        fwd_returns = _make_fwd_returns(
            next(iter(factor_data.values())).index,
            next(iter(factor_data.values())).columns,
        )
        industry = _make_industry_data(
            next(iter(factor_data.values())).columns)
        market_cap = pd.DataFrame(
            1.0, index=next(iter(factor_data.values())).index,
            columns=next(iter(factor_data.values())).columns)

        with patch('factor_pipeline.pipelines_v2.FactorProcessingPipelineV2') as mock_cls:
            mock_instance = MagicMock()
            mock_instance.transform.side_effect = (
                lambda fd: {name: df.copy() for name, df in fd.items()})
            mock_cls.return_value = mock_instance

            runner.run_l1_decoupler(
                factor_data, fwd_returns, industry, market_cap)

        assert mock_cls.call_count == 2
        modes = [c.args[0].pipeline_mode for c in mock_cls.call_args_list]
        assert modes == ['dynamic_ab', 'dynamic_ab']
        # 市值应透传到 fit
        for call in mock_instance.fit.call_args_list:
            assert call.kwargs.get('market_cap_data') is market_cap

    def test_module_enabled_propagates(self):
        """D5: 仅实验臂的 modified_config.module_enabled={'decoupler': False}."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        factor_data = _make_factor_data()
        fwd_returns = _make_fwd_returns(
            next(iter(factor_data.values())).index,
            next(iter(factor_data.values())).columns,
        )

        with patch('factor_pipeline.pipelines_v2.FactorProcessingPipelineV2') as mock_cls:
            mock_instance = MagicMock()
            mock_instance.transform.side_effect = (
                lambda fd: {name: df.copy() for name, df in fd.items()})
            mock_cls.return_value = mock_instance

            runner.run_l1_decoupler(factor_data, fwd_returns)

        configs = [c.args[0] for c in mock_cls.call_args_list]
        assert configs[0].module_enabled is None
        assert configs[1].module_enabled == {'decoupler': False}


# =============================================================================
# D6: 参照复用
# =============================================================================

class TestDecouplerArmRefReuse:

    def test_dynamic_ref_result_reused(self, monkeypatch):
        """D6: 提供参照 → 只跑 1 次, 参照对象 identity 复用."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        captured = _capture_run_single(monkeypatch, runner)
        ref = _make_result(
            'precomputed_ref',
            {step: 1.0 for step in AblationRunner.L1_MODULES})

        results = runner.run_l1_decoupler(
            _make_factor_data(), _make_factor_data(),
            dynamic_ref_result=ref,
        )

        assert len(results) == 2
        assert results[0] is ref
        assert len(captured) == 1
        assert captured[0]['config'].name == 'L1_decoupler_off'


# =============================================================================
# D7-D8: rho_step 采集
# =============================================================================

class TestDecouplerRhoStep:

    def test_rho_step_decoupler_computed(self):
        """D7: dynamic 中间数据 → rho_step['decoupler'] 可测且不恒为 1."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        stocks = [f'S{i:03d}' for i in range(10)]
        periods = [f'T{j}' for j in range(5)]
        rng = np.random.default_rng(42)
        before = pd.DataFrame(
            rng.standard_normal((10, 5)), index=stocks, columns=periods)
        after = (-before).copy()  # 排序反转 → Spearman ≈ -1

        mock_pipe = MagicMock()
        mock_pipe.get_intermediate_data.return_value = {
            'imputation': before,
            'decoupling': after,
        }
        mock_pipeline = MagicMock()
        mock_pipeline.factor_pipelines = {'factor_0': {'dynamic': mock_pipe}}

        rho = runner._collect_rho_steps(
            mock_pipeline, {'factor_0': before}, {'factor_0': after})

        assert 'decoupler' in rho
        assert rho['decoupler'] < 0.5, (
            f"decoupler rho should reflect rank reversal, got {rho['decoupler']}")

    def test_rho_step_decoupler_absent_for_unified(self):
        """D8: 无 'decoupling' 中间数据 → 不输出 decoupler 键."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        stocks = [f'S{i:03d}' for i in range(10)]
        periods = [f'T{j}' for j in range(5)]
        rng = np.random.default_rng(1)
        df = pd.DataFrame(
            rng.standard_normal((10, 5)), index=stocks, columns=periods)

        mock_pipe = MagicMock()
        mock_pipe.get_intermediate_data.return_value = {
            'imputation': df, 'outlier': df, 'transform': df,
            'neutralization': df, 'standardization': df,
        }
        mock_pipeline = MagicMock()
        mock_pipeline.factor_pipelines = {'factor_0': {'static': mock_pipe}}

        rho = runner._collect_rho_steps(
            mock_pipeline, {'factor_0': df}, {'factor_0': df})

        assert 'decoupler' not in rho
        assert set(rho.keys()) == set(AblationRunner.L1_MODULES)


# =============================================================================
# D9: 报告条件列
# =============================================================================

class TestDecouplerReport:

    def test_report_decoupler_column_conditional(self):
        """D9: 有 decoupler 数据 → 表头含该列; 无 → 不含."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        base_rho = {step: 1.0 for step in AblationRunner.L1_MODULES}

        with_dec = base_rho | {'decoupler': 0.9}
        report_with = runner.generate_report(
            [_make_result('L1_dynamic_ref', with_dec)], [])
        assert '| decoupler |' in report_with
        # 语义注脚: 该列含中性化 + AR 的合并变化 (避免误读为纯 AR)
        assert '合并排序' in report_with

        report_without = runner.generate_report(
            [_make_result('L1_imputer_off', base_rho)], [])
        assert '| decoupler |' not in report_without


# =============================================================================
# D10: run_l1 市值转发 (R-1)
# =============================================================================

class TestRunL1MarketCapForwarding:

    def test_run_l1_forwards_market_cap_data(self, monkeypatch):
        """D10: 传入市值 → 6 臂均收到; 未传 → 不注入该关键字."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        factor_data = _make_factor_data()
        fwd_returns = _make_factor_data()
        market_cap = pd.DataFrame(
            np.ones((2, 2)), index=['d1', 'd2'], columns=['S1', 'S2'])

        captured = _capture_run_single(monkeypatch, runner)
        results = runner.run_l1(
            factor_data, fwd_returns, market_cap_data=market_cap)

        assert len(results) == 6
        assert len(captured) == 6
        assert all(c['market_cap_data'] is market_cap for c in captured)

        captured.clear()
        runner.run_l1(factor_data, fwd_returns)
        assert len(captured) == 6
        assert all(c['market_cap_data'] is None for c in captured)

    def test_run_l2_forwards_market_cap_data(self, monkeypatch):
        """D12: run_l2 两臂均转发市值; 未传时不注入该关键字."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        factor_data = _make_factor_data()
        fwd_returns = _make_factor_data()
        market_cap = pd.DataFrame(
            np.ones((2, 2)), index=['d1', 'd2'], columns=['S1', 'S2'])

        captured = _capture_run_single(monkeypatch, runner)
        results = runner.run_l2(
            factor_data, fwd_returns, market_cap_data=market_cap)

        assert len(results) == 2
        assert all(c['market_cap_data'] is market_cap for c in captured)

        captured.clear()
        runner.run_l2(factor_data, fwd_returns)
        assert len(captured) == 2
        assert all(c['market_cap_data'] is None for c in captured)

    def test_run_baselines_forwards_market_cap_data(self, monkeypatch):
        """D13: B0-B3 阶梯均转发市值 (B3 是 L1/L2 参照, 口径须一致)."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        factor_data = _make_factor_data()
        fwd_returns = _make_factor_data()
        market_cap = pd.DataFrame(
            np.ones((2, 2)), index=['d1', 'd2'], columns=['S1', 'S2'])

        captured = _capture_run_single(monkeypatch, runner)
        results = runner.run_baselines(
            factor_data, fwd_returns, market_cap_data=market_cap)

        assert len(results) == 4
        assert all(c['market_cap_data'] is market_cap for c in captured)

        captured.clear()
        runner.run_baselines(factor_data, fwd_returns)
        assert all(c['market_cap_data'] is None for c in captured)


# =============================================================================
# D11: 端到端
# =============================================================================

class TestDecouplerArmEndToEnd:

    def test_run_l1_decoupler_end_to_end(self):
        """D11: 小规模 AR 面板真实运行两臂, IC 非 NaN 且 rho 含 decoupler."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        factor_data = _make_ar_factor_data()
        df = next(iter(factor_data.values()))
        fwd_returns = _make_fwd_returns(df.index, df.columns)
        industry = _make_industry_data(df.columns)

        runner = AblationRunner(PipelineV2Config(), n_bootstrap=100)
        results = runner.run_l1_decoupler(
            factor_data, fwd_returns, industry)

        assert len(results) == 2
        for r in results:
            assert not np.isnan(r.metrics['ic_mean']), (
                f"{r.config.name} ic_mean should not be NaN")
            assert 'decoupler' in r.rho_step, (
                f"{r.config.name} should record decoupler rho_step")
