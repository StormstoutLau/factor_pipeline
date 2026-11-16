# -*- coding: utf-8 -*-
"""v3.4.7: AblationRunner L3/L4 旋钮接线测试 (TDD).

规格: docs/EXECUTION_V3.4.7_ABLATION_KNOB_WIRING.md §3 (E1-E12)
上游: docs/research/RESEARCH_ABLATION_KNOB_WIRING.md

核心约束:
  - L4 从 20 结果收敛为 9 (B3 + 3 自由度 8 臂), outlier 4 臂真实接线;
  - L3 从 25 结果收敛为 7 (B3 + 6 CUSUM 诊断臂), 全部 trivial + diagnostic;
  - 生产管线默认去极值参数 = v3.4.6 硬编码 (percentile 1/99), 零行为变更.
"""

import copy
import logging

import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch

from factor_pipeline.backtest.ablation_runner import (
    AblationRunner, AblationConfig, AblationResult,
)
from factor_pipeline.backtest.multiple_testing import apply_bh_fdr


# =============================================================================
# 测试数据
# =============================================================================

def _make_factor_data(n_periods=12, n_stocks=8, seed=42):
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2022-01-31', periods=n_periods, freq='ME')
    stocks = [f'S{i:03d}' for i in range(n_stocks)]
    return {'factor_0': pd.DataFrame(
        rng.standard_normal((n_periods, n_stocks)),
        index=dates, columns=stocks)}


def _make_fwd_returns(index, columns, seed=99):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.standard_normal((len(index), len(columns))) * 0.02,
        index=index, columns=columns)


def _make_industry(columns):
    n = len(columns)
    return pd.Series(['IND_A'] * (n // 2) + ['IND_B'] * (n - n // 2),
                     index=columns)


def _make_market_cap(index, columns):
    return pd.DataFrame(
        np.linspace(1e9, 5e10, len(columns))[None, :].repeat(len(index), 0),
        index=index, columns=columns)


def _data():
    factor_data = _make_factor_data()
    index = factor_data['factor_0'].index
    columns = factor_data['factor_0'].columns
    return (factor_data, _make_fwd_returns(index, columns),
            _make_industry(columns))


def _runner():
    from factor_pipeline.pipelines_v2 import PipelineV2Config
    return AblationRunner(PipelineV2Config())


def _capture_run_single(monkeypatch, runner):
    captured = []

    def mock_run_single(config, fd, fr, industry_data=None, **kwargs):
        captured.append({
            'config': config,
            'has_market_cap': 'market_cap_data' in kwargs,
            'market_cap_data': kwargs.get('market_cap_data'),
        })
        return object()

    monkeypatch.setattr(runner, 'run_single', mock_run_single)
    return captured


def _make_layer_result(name, layer, seed=42):
    from factor_pipeline.backtest.ablation_runner import AblationResult
    rng = np.random.default_rng(seed)
    n = 30
    return AblationResult(
        config=AblationConfig(name=name, layer=layer),
        metrics={'ic_mean': 0.02, 'icir': 0.3, 'sharpe_ls': 0.5,
                 'max_drawdown': -0.1, 'hit_rate': 0.5},
        ic_series=rng.standard_normal(n) * 0.05 + 0.02,
        ls_return_series=rng.standard_normal(n) * 0.01 + 0.002,
        rho_step={step: 1.0 for step in AblationRunner.L1_MODULES},
        ortho_diagnostics={'condition_number': float('nan'),
                           'vrr_mean': float('nan')},
        n_factors=1, n_periods=n, runtime_sec=0.0,
    )


# =============================================================================
# E1-E2 / E6: run_l4_oat 臂集合
# =============================================================================

class TestRunL4ArmSet:

    def test_run_l4_oat_returns_9(self, monkeypatch):
        """E1: 9 结果 = B3 + 8 臂 (outlier 4 + missing 1 + neutralization 3)."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()
        captured = _capture_run_single(monkeypatch, runner)

        results = runner.run_l4_oat(factor_data, fwd_returns, industry)

        assert len(results) == 9
        assert len(captured) == 9
        assert sum(1 for c in captured if c['config'].layer == 'L4') == 8

    def test_run_l4_outlier_arm_configs(self, monkeypatch):
        """E2: outlier 4 臂的字段值保持 (注入映射由 E3 覆盖)."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()
        captured = _capture_run_single(monkeypatch, runner)

        runner.run_l4_oat(factor_data, fwd_returns, industry)

        by_name = {c['config'].name: c['config'] for c in captured}
        assert by_name['L4_outlier_method_3sigma'].outlier_method == '3sigma'
        assert by_name['L4_outlier_method_mad'].outlier_method == 'mad'
        assert (by_name['L4_outlier_method_winsorize_1pct'].outlier_method
                == 'winsorize_1pct')
        assert (by_name['L4_outlier_method_winsorize_5pct'].outlier_method
                == 'winsorize_5pct')

    def test_l4_trivial_count(self, monkeypatch):
        """E6: 不传市值 → 3 trivial + 5 non-trivial (v3.4.8 实跑口径)."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()
        captured = _capture_run_single(monkeypatch, runner)

        runner.run_l4_oat(factor_data, fwd_returns, industry)

        l4 = [c['config'] for c in captured if c['config'].layer == 'L4']
        trivial = [c for c in l4 if c._is_trivial]
        assert len(l4) == 8
        assert len(trivial) == 3
        assert {c.name for c in trivial} == {
            'L4_outlier_method_winsorize_1pct',
            'L4_neutralization_industry',
            'L4_neutralization_industry+mktcap',
        }


class TestL4TrivialCaliber:
    """v3.4.8: trivial 按实跑口径判定 (无市值时 industry+mktcap 退化)."""

    _TRIVIAL_NO_MKTCAP = {
        'L4_outlier_method_winsorize_1pct',
        'L4_neutralization_industry',
        'L4_neutralization_industry+mktcap',
    }
    _TRIVIAL_WITH_MKTCAP = {
        'L4_outlier_method_winsorize_1pct',
        'L4_neutralization_industry+mktcap',
    }

    def test_no_mktcap_marks_mktcap_arm_trivial(self, monkeypatch):
        """T1: 无市值 → 退化臂计入 trivial 集合."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()
        captured = _capture_run_single(monkeypatch, runner)

        runner.run_l4_oat(factor_data, fwd_returns, industry)

        trivial = {c['config'].name for c in captured
                   if c['config'].layer == 'L4' and c['config']._is_trivial}
        assert trivial == self._TRIVIAL_NO_MKTCAP

    def test_no_mktcap_emits_degradation_warning(self, monkeypatch, caplog):
        """T2: 无市值 → 恰 1 条退化告警."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()
        _capture_run_single(monkeypatch, runner)
        caplog.set_level(logging.WARNING,
                        logger='factor_pipeline.backtest.ablation_runner')

        runner.run_l4_oat(factor_data, fwd_returns, industry)

        hits = [r for r in caplog.records if '退化为仅行业' in r.getMessage()]
        assert len(hits) == 1

    def test_with_mktcap_trivial_set_unchanged(self, monkeypatch, caplog):
        """T3: 传市值 → trivial 集合不变 (2 个) 且无退化告警."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()
        market_cap = _make_market_cap(factor_data['factor_0'].index,
                                      factor_data['factor_0'].columns)
        captured = _capture_run_single(monkeypatch, runner)
        caplog.set_level(logging.WARNING,
                        logger='factor_pipeline.backtest.ablation_runner')

        runner.run_l4_oat(factor_data, fwd_returns, industry,
                          market_cap_data=market_cap)

        trivial = {c['config'].name for c in captured
                   if c['config'].layer == 'L4' and c['config']._is_trivial}
        assert trivial == self._TRIVIAL_WITH_MKTCAP
        assert not any('退化为仅行业' in r.getMessage() for r in caplog.records)

    def test_external_b3_without_mktcap_emits_caliber_hint(self, monkeypatch, caplog):
        """T4: 外部 B3 + 无市值 → 追加一条口径未校验提示, trivial 判定不变."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()
        captured = _capture_run_single(monkeypatch, runner)
        caplog.set_level(logging.WARNING,
                        logger='factor_pipeline.backtest.ablation_runner')
        external_b3 = AblationResult(
            config=AblationConfig(
                name='B3_full', layer='baseline', baseline_level='B3'),
            metrics={}, ic_series=np.array([]), ls_return_series=np.array([]),
            rho_step={}, ortho_diagnostics={},
            n_factors=1, n_periods=12, runtime_sec=0.0,
        )

        results = runner.run_l4_oat(factor_data, fwd_returns, industry,
                                    b3_full_result=external_b3)

        assert results[0] is external_b3
        assert len([r for r in caplog.records
                    if '外部 B3 口径未校验' in r.getMessage()]) == 1
        assert len([r for r in caplog.records
                    if '退化为仅行业' in r.getMessage()]) == 1
        trivial = [c['config'] for c in captured
                   if c['config'].layer == 'L4' and c['config']._is_trivial]
        assert {c.name for c in trivial} == self._TRIVIAL_NO_MKTCAP


# =============================================================================
# v3.4.9: L1/L2 trivial 口径
# =============================================================================

def _runner_with(base_config):
    """构造指定 base_config 的 runner (v3.4.9)."""
    return AblationRunner(base_config)


class TestL1L2TrivialCaliber:
    """v3.4.9: L1/L2 trivial 按 base_config 实跑口径判定."""

    _TRIVIAL_L1 = {'L1_orthogonalizer_off'}
    _TRIVIAL_L2 = {'L2_unified'}

    def test_run_l1_marks_ortho_arm_trivial(self, monkeypatch):
        """E1: 默认 base 未启用正交化 → 仅 ortho 臂 trivial (6 结果 / 4 非平凡)."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = _runner_with(PipelineV2Config())
        factor_data, fwd_returns, industry = _data()
        captured = _capture_run_single(monkeypatch, runner)

        results = runner.run_l1(factor_data, fwd_returns, industry)

        configs = [c['config'] for c in captured]
        l1 = [c for c in configs if c.layer == 'L1']
        trivial = {c.name for c in l1 if c._is_trivial}
        assert len(results) == 6
        assert len(l1) == 5
        assert trivial == self._TRIVIAL_L1
        assert len(l1) - len(trivial) == 4

    def test_run_l2_marks_unified_arm_trivial(self, monkeypatch):
        """E2: L2_unified 与 B3 同为 unified → trivial (2 结果 / 1 非平凡)."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = _runner_with(PipelineV2Config())
        factor_data, fwd_returns, industry = _data()
        captured = _capture_run_single(monkeypatch, runner)

        results = runner.run_l2(factor_data, fwd_returns, industry)

        configs = [c['config'] for c in captured]
        trivial = {c.name for c in configs if c._is_trivial}
        assert len(results) == 2
        assert trivial == self._TRIVIAL_L2

    def test_run_l1_emits_degradation_warning(self, monkeypatch, caplog):
        """E3: 默认 base → 恰 1 条「与 B3 同口径」告警, 且点名 ortho 臂."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = _runner_with(PipelineV2Config())
        factor_data, fwd_returns, industry = _data()
        _capture_run_single(monkeypatch, runner)
        caplog.set_level(logging.WARNING,
                        logger='factor_pipeline.backtest.ablation_runner')

        runner.run_l1(factor_data, fwd_returns, industry)

        hits = [r for r in caplog.records if '与 B3 同口径' in r.getMessage()]
        assert len(hits) == 1
        assert 'L1_orthogonalizer_off' in hits[0].getMessage()

    def test_run_l1_with_active_ortho_keeps_arm_non_trivial(self, monkeypatch,
                                                            caplog):
        """E4: base 启用正交化 → ortho 臂非平凡且无退化告警."""
        from factor_pipeline.config_v2 import OrthogonalizationConfig
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        base = PipelineV2Config(
            orthogonalization=OrthogonalizationConfig(enabled=True))
        runner = _runner_with(base)
        factor_data, fwd_returns, industry = _data()
        captured = _capture_run_single(monkeypatch, runner)
        caplog.set_level(logging.WARNING,
                        logger='factor_pipeline.backtest.ablation_runner')

        runner.run_l1(factor_data, fwd_returns, industry)

        by_name = {c['config'].name: c['config'] for c in captured}
        assert by_name['L1_orthogonalizer_off']._is_trivial is False
        assert not [r for r in caplog.records
                    if '与 B3 同口径' in r.getMessage()]

    def test_run_l1_merges_base_module_switches(self, monkeypatch, caplog):
        """E5: base 已关 imputer → 该臂 trivial; scaler 臂保留 base 开关."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        base = PipelineV2Config(module_enabled={'imputer': False})
        runner = _runner_with(base)
        factor_data, fwd_returns, industry = _data()
        captured = _capture_run_single(monkeypatch, runner)
        caplog.set_level(logging.WARNING,
                        logger='factor_pipeline.backtest.ablation_runner')

        runner.run_l1(factor_data, fwd_returns, industry)

        by_name = {c['config'].name: c['config'] for c in captured}
        assert by_name['L1_imputer_off']._is_trivial is True
        assert by_name['L1_imputer_off'].module_enabled == {'imputer': False}
        assert by_name['L1_scaler_off']._is_trivial is False
        assert by_name['L1_scaler_off'].module_enabled == {
            'imputer': False, 'scaler': False}
        hits = [r for r in caplog.records if '与 B3 同口径' in r.getMessage()]
        assert len(hits) == 1
        assert 'L1_imputer_off' in hits[0].getMessage()

    def test_external_b3_emits_caliber_hint(self, monkeypatch, caplog):
        """E6: 外部 B3 → run_l1 / run_l2 各 1 条「未校验」, trivial 不变."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = _runner_with(PipelineV2Config())
        factor_data, fwd_returns, industry = _data()
        captured = _capture_run_single(monkeypatch, runner)
        caplog.set_level(logging.WARNING,
                        logger='factor_pipeline.backtest.ablation_runner')
        external_b3 = AblationResult(
            config=AblationConfig(
                name='B3_full', layer='baseline', baseline_level='B3'),
            metrics={}, ic_series=np.array([]), ls_return_series=np.array([]),
            rho_step={}, ortho_diagnostics={},
            n_factors=1, n_periods=12, runtime_sec=0.0,
        )

        results_l1 = runner.run_l1(factor_data, fwd_returns, industry,
                                   b3_full_result=external_b3)

        assert results_l1[0] is external_b3
        assert len([r for r in caplog.records
                    if '未校验' in r.getMessage()]) == 1
        assert {c['config'].name for c in captured
                if c['config']._is_trivial} == self._TRIVIAL_L1

        caplog.clear()
        captured.clear()
        results_l2 = runner.run_l2(factor_data, fwd_returns, industry,
                                   b3_full_result=external_b3)

        assert results_l2[-1] is external_b3
        assert len([r for r in caplog.records
                    if '未校验' in r.getMessage()]) == 1
        assert {c['config'].name for c in captured
                if c['config']._is_trivial} == self._TRIVIAL_L2

    def test_trivial_flags_match_arm_fields(self, monkeypatch):
        """E7: trivial 标记与臂字段一致, 防止判定错位."""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = _runner_with(PipelineV2Config())
        factor_data, fwd_returns, industry = _data()
        captured = _capture_run_single(monkeypatch, runner)

        runner.run_l1(factor_data, fwd_returns, industry)
        runner.run_l2(factor_data, fwd_returns, industry)

        by_name = {c['config'].name: c['config'] for c in captured}
        assert by_name['L1_orthogonalizer_off'].ortho_enabled is False
        assert by_name['L1_orthogonalizer_off']._is_trivial is True
        assert by_name['L2_dynamic'].routing_mode == 'dynamic'
        assert by_name['L2_dynamic']._is_trivial is False


# =============================================================================
# E3-E5: 注入语义
# =============================================================================

class TestL4InjectionSemantics:

    def _make_runner_and_config(self):
        runner = _runner()
        return runner, copy.deepcopy(runner.base_config)

    @pytest.mark.parametrize('arm,method,lower,upper', [
        ('3sigma', 'z_score', None, None),
        ('mad', 'mad', None, None),
        ('winsorize_1pct', 'percentile', 1.0, 99.0),
        ('winsorize_5pct', 'percentile', 5.0, 95.0),
    ])
    def test_l4_outlier_maps_to_static_config(self, arm, method, lower, upper):
        """E3: 臂名 → static_outlier_* 映射."""
        runner, modified_config = self._make_runner_and_config()

        abl_cfg = AblationConfig(name=f'L4_outlier_method_{arm}',
                                 layer='L4', outlier_method=arm)
        runner._apply_l4_overrides(modified_config, abl_cfg)

        assert modified_config.static_outlier_method == method
        if lower is not None:
            assert modified_config.static_outlier_percentile_lower == lower
            assert modified_config.static_outlier_percentile_upper == upper

    def test_l4_unknown_outlier_raises(self):
        """E3b: 未知臂名 → ValueError (不静默降级)."""
        runner, modified_config = self._make_runner_and_config()
        abl_cfg = AblationConfig(name='L4_bad', layer='L4',
                                 outlier_method='not_a_method')
        with pytest.raises(ValueError, match='outlier_method'):
            runner._apply_l4_overrides(modified_config, abl_cfg)

    def test_l4_neutralization_writes_no_config_attr(self):
        """复审收口: industry/industry+mktcap 臂不写任何 config 属性 (含 _l4_neutralization)."""
        runner, modified_config = self._make_runner_and_config()
        original_module_enabled = modified_config.module_enabled

        for arm in ('industry', 'industry+mktcap'):
            cfg = AblationConfig(name=f'L4_neutralization_{arm}',
                                 layer='L4', neutralization=arm)
            runner._apply_l4_overrides(modified_config, cfg)
            assert not hasattr(modified_config, '_l4_neutralization')
            assert modified_config.module_enabled == original_module_enabled

    def test_l4_missing_drop_disables_imputer(self):
        """E4: missing=drop → 关闭 imputer."""
        runner, modified_config = self._make_runner_and_config()

        abl_cfg = AblationConfig(name='L4_missing_method_drop',
                                 layer='L4', missing_method='drop')
        runner._apply_l4_overrides(modified_config, abl_cfg)

        assert modified_config.module_enabled['imputer'] is False

    def test_l4_neutralization_market_cap_rules(self, monkeypatch):
        """E5: industry 臂不带市值; none / industry+mktcap 带."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()
        market_cap = _make_market_cap(factor_data['factor_0'].index,
                                      factor_data['factor_0'].columns)
        captured = _capture_run_single(monkeypatch, runner)

        runner.run_l4_oat(factor_data, fwd_returns, industry,
                          market_cap_data=market_cap)

        by_name = {c['config'].name: c for c in captured}
        assert by_name['L4_neutralization_industry']['has_market_cap'] is False
        assert by_name['L4_neutralization_none']['has_market_cap'] is True
        assert (by_name['L4_neutralization_industry+mktcap']['market_cap_data']
                is market_cap)


# =============================================================================
# E7-E9 / E12: run_l3 诊断臂
# =============================================================================

class TestRunL3DiagnosticArms:

    def test_run_l3_returns_7(self, monkeypatch):
        """E7: 7 结果 = B3 + 6 CUSUM."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()
        captured = _capture_run_single(monkeypatch, runner)

        results = runner.run_l3(factor_data, fwd_returns, industry)

        assert len(results) == 7
        assert len(captured) == 7
        assert sum(1 for c in captured if c['config'].layer == 'L3') == 6

    def test_l3_arms_are_diagnostic_and_trivial(self, monkeypatch):
        """E8: 6 臂全部 _is_trivial=True 且 _wiring_status='diagnostic'."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()
        captured = _capture_run_single(monkeypatch, runner)

        runner.run_l3(factor_data, fwd_returns, industry)

        l3 = [c['config'] for c in captured if c['config'].layer == 'L3']
        assert len(l3) == 6
        for cfg in l3:
            assert cfg._is_trivial is True
            assert cfg._wiring_status == 'diagnostic'

    def test_l3_removed_families_absent(self, monkeypatch):
        """E9: 已删除族不再生成."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()
        captured = _capture_run_single(monkeypatch, runner)

        runner.run_l3(factor_data, fwd_returns, industry)

        names = [c['config'].name for c in captured]
        for prefix in ('L3_ewma_', 'L3_threshold_scale_',
                       'L3_winsorize_', 'L3_correction_'):
            assert not any(n.startswith(prefix) for n in names), prefix

    def test_l3_all_trivial_bh_empty(self):
        """E12: 全部 trivial → BH-FDR 输入为空, 无显著, 比较全部保留."""
        runner = _runner()
        reference = _make_layer_result('B3_full', 'baseline', seed=99)
        results = []
        for i, name in enumerate([
                'L3_cusum_oat_k0.25', 'L3_cusum_oat_k0.5',
                'L3_cusum_oat_k0.75', 'L3_cusum_oat_h4.0',
                'L3_cusum_oat_h5.5', 'L3_cusum_oat_h7.0']):
            r = _make_layer_result(name, 'L3', seed=i)
            r.config._is_trivial = True
            r.config._wiring_status = 'diagnostic'
            results.append(r)

        with patch('factor_pipeline.backtest.ablation_runner.apply_bh_fdr',
                   wraps=apply_bh_fdr) as mock_bh:
            comparisons = runner.compare_all(results, reference)

        assert mock_bh.call_args[0][0] == []
        assert len(comparisons) == 6
        assert all(c._is_trivial for c in comparisons)
        assert not any(c.is_significant for c in comparisons)


# =============================================================================
# E10-E11: 生产管线默认参数
# =============================================================================

class TestPipelineOutlierWiring:

    def test_pipeline_default_outlier_params(self):
        """E10: 默认三元组 = v3.4.6 硬编码 (percentile/1.0/99.0)."""
        from factor_pipeline.pipelines_v2 import (
            PipelineV2Config, StaticFactorPipeline,
        )

        cfg = PipelineV2Config()
        assert cfg.static_outlier_method == 'percentile'
        assert cfg.static_outlier_percentile_lower == 1.0
        assert cfg.static_outlier_percentile_upper == 99.0

        pipe = StaticFactorPipeline()
        outlier_step = dict(pipe.steps)['outlier']
        assert outlier_step.method == 'percentile'
        assert outlier_step._outlier_percentile_lower == 1.0
        assert outlier_step._outlier_percentile_upper == 99.0

    def test_non_percentile_skips_percentiles(self):
        """E11: 非 percentile 方法不传分位参数, adapter 方法正确."""
        from factor_pipeline.pipelines_v2 import StaticFactorPipeline

        pipe = StaticFactorPipeline(outlier_method='mad')
        outlier_step = dict(pipe.steps)['outlier']
        assert outlier_step.method == 'mad'

    def test_create_pipeline_injects_config(self):
        """E10b: _create_pipeline('static') 从 config 注入三字段."""
        from factor_pipeline.pipelines_v2 import (
            PipelineV2Config, FactorProcessingPipelineV2,
        )

        cfg = PipelineV2Config()
        cfg.static_outlier_method = 'mad'
        pipeline = FactorProcessingPipelineV2(cfg)
        pipe = pipeline._create_pipeline('static', neutralizer_params={})
        outlier_step = dict(pipe.steps)['outlier']
        assert outlier_step.method == 'mad'

    # ── v3.4.11: MAD detector 参数透传 ──

    def test_detector_params_default(self):
        """v3.4.11 E3: 默认 adaptive_threshold=True / max_outlier_frac=0.05."""
        from factor_pipeline.pipelines_v2 import (
            PipelineV2Config, StaticFactorPipeline,
        )

        cfg = PipelineV2Config()
        assert cfg.static_outlier_adaptive_threshold is True
        assert cfg.static_outlier_max_outlier_frac == 0.05

        pipe = StaticFactorPipeline(outlier_method='mad')
        outlier_step = dict(pipe.steps)['outlier']
        assert outlier_step._outlier_detector_kwargs == {
            'adaptive_threshold': True,
            'max_outlier_frac': 0.05,
        }

    def test_mad_adaptive_threshold_forwarded(self):
        """v3.4.11 E4: adaptive_threshold=False + 自定义 frac 传到 adapter."""
        from factor_pipeline.pipelines_v2 import StaticFactorPipeline

        pipe = StaticFactorPipeline(
            outlier_method='mad',
            outlier_adaptive_threshold=False,
            outlier_max_outlier_frac=0.02,
        )
        outlier_step = dict(pipe.steps)['outlier']
        assert outlier_step._outlier_detector_kwargs == {
            'adaptive_threshold': False,
            'max_outlier_frac': 0.02,
        }

    def test_create_pipeline_injects_detector_params(self):
        """v3.4.11 E5: _create_pipeline('static') 转发两个 detector 字段."""
        from factor_pipeline.pipelines_v2 import (
            PipelineV2Config, FactorProcessingPipelineV2,
        )

        cfg = PipelineV2Config()
        cfg.static_outlier_method = 'mad'
        cfg.static_outlier_adaptive_threshold = False
        cfg.static_outlier_max_outlier_frac = 0.03
        pipeline = FactorProcessingPipelineV2(cfg)
        pipe = pipeline._create_pipeline('static', neutralizer_params={})
        outlier_step = dict(pipe.steps)['outlier']
        assert outlier_step._outlier_detector_kwargs == {
            'adaptive_threshold': False,
            'max_outlier_frac': 0.03,
        }
