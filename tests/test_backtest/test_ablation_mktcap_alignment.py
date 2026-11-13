# -*- coding: utf-8 -*-
"""v3.4.6: AblationRunner L3/L4 市值口径对齐测试 (TDD).

规格: docs/EXECUTION_V3.4.6_ABLATION_MKTCAP_ALIGNMENT.md §3 (E1-E7)
上游: docs/research/RESEARCH_ABLATION_MKTCAP_ALIGNMENT.md

核心约束:
  - run_l3: B3 + 24 臂统一注入市值 (与参照同口径)
  - run_l4_oat: 普通臂注入, 但 neutralization='industry' 臂必须跳过
    (管线收到市值会自动切 industry_marketcap — RESEARCH F6/F8)
  - 未传市值时行为与 v3.4.5 逐位一致 (默认 neutralization=industry)
"""

import numpy as np
import pandas as pd

from factor_pipeline.backtest.ablation_runner import AblationRunner


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


def _make_market_cap(index, columns):
    return pd.DataFrame(
        np.linspace(1e9, 5e10, len(columns))[None, :].repeat(len(index), 0),
        index=index, columns=columns)


def _capture_run_single(monkeypatch, runner):
    """捕获 run_single 入参, 并区分「未传关键字」与「传 None」."""
    captured = []

    def mock_run_single(config, fd, fr, industry_data=None, **kwargs):
        captured.append({
            'config': config,
            'has_key': 'market_cap_data' in kwargs,
            'market_cap_data': kwargs.get('market_cap_data'),
        })
        return object()

    monkeypatch.setattr(runner, 'run_single', mock_run_single)
    return captured


def _runner():
    from factor_pipeline.pipelines_v2 import PipelineV2Config
    return AblationRunner(PipelineV2Config())


def _data():
    factor_data = _make_factor_data()
    index = factor_data['factor_0'].index
    columns = factor_data['factor_0'].columns
    return (factor_data, _make_fwd_returns(index, columns),
            pd.Series(['IND_A'] * 4 + ['IND_B'] * 4, index=columns))


# =============================================================================
# E1-E2: run_l3
# =============================================================================

class TestRunL3MarketCap:

    def test_run_l3_forwards_market_cap_to_all_arms(self, monkeypatch):
        """E1: 25 个臂 (B3 + 24) 全部带同一市值对象."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()
        market_cap = _make_market_cap(factor_data['factor_0'].index,
                                      factor_data['factor_0'].columns)

        captured = _capture_run_single(monkeypatch, runner)
        results = runner.run_l3(
            factor_data, fwd_returns, industry, market_cap_data=market_cap)

        assert len(results) == 25
        assert len(captured) == 25
        assert all(c['has_key'] for c in captured)
        assert all(c['market_cap_data'] is market_cap for c in captured)

    def test_run_l3_omits_market_cap_when_absent(self, monkeypatch):
        """E2: 未传市值时不注入关键字 (保持既有 monkeypatch 签名兼容)."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()

        captured = _capture_run_single(monkeypatch, runner)
        runner.run_l3(factor_data, fwd_returns, industry)

        assert len(captured) == 25
        assert not any(c['has_key'] for c in captured)

    def test_run_l3_b3_reference_receives_market_cap(self, monkeypatch):
        """E7a: 不传 b3_full_result 时, B3 参照同样带市值."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()
        market_cap = _make_market_cap(factor_data['factor_0'].index,
                                      factor_data['factor_0'].columns)

        captured = _capture_run_single(monkeypatch, runner)
        runner.run_l3(
            factor_data, fwd_returns, industry, market_cap_data=market_cap)

        b3 = [c for c in captured if c['config'].name == 'B3_full']
        assert len(b3) == 1
        assert b3[0]['market_cap_data'] is market_cap


# =============================================================================
# E3-E7: run_l4_oat
# =============================================================================

class TestRunL4MarketCap:

    def test_run_l4_forwards_market_cap_to_non_neutralization_arms(
            self, monkeypatch):
        """E3: 非中性化自由度 (outlier/scaler/missing/time_align/data_window) 均带市值."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()
        market_cap = _make_market_cap(factor_data['factor_0'].index,
                                      factor_data['factor_0'].columns)

        captured = _capture_run_single(monkeypatch, runner)
        results = runner.run_l4_oat(
            factor_data, fwd_returns, industry, market_cap_data=market_cap)

        assert len(results) == 20
        prefixes = ('L4_outlier_method_', 'L4_scaler_method_',
                    'L4_missing_method_', 'L4_time_align_')
        arms = [c for c in captured
                if c['config'].name.startswith(prefixes)
                or c['config'].name.startswith('L4_data_window_')]
        assert len(arms) == 16
        assert all(c['market_cap_data'] is market_cap for c in arms)

    def test_run_l4_neutralization_industry_arm_skips_market_cap(
            self, monkeypatch):
        """E4: 'industry' 臂跳过市值; 'industry+mktcap' 与 'none' 臂注入."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()
        market_cap = _make_market_cap(factor_data['factor_0'].index,
                                      factor_data['factor_0'].columns)

        captured = _capture_run_single(monkeypatch, runner)
        runner.run_l4_oat(
            factor_data, fwd_returns, industry, market_cap_data=market_cap)

        by_name = {c['config'].name: c for c in captured}
        assert by_name['L4_neutralization_industry']['has_key'] is False
        assert by_name['L4_neutralization_industry+mktcap'][
            'market_cap_data'] is market_cap
        assert by_name['L4_neutralization_none'][
            'market_cap_data'] is market_cap

    def test_run_l4_default_neutralization_switches_with_market_cap(
            self, monkeypatch):
        """E5: 传市值时默认口径切到 industry+mktcap 并标记为 trivial."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()
        market_cap = _make_market_cap(factor_data['factor_0'].index,
                                      factor_data['factor_0'].columns)

        captured = _capture_run_single(monkeypatch, runner)
        runner.run_l4_oat(
            factor_data, fwd_returns, industry, market_cap_data=market_cap)

        by_name = {c['config'].name: c for c in captured}
        assert by_name['L4_neutralization_industry+mktcap'][
            'config']._is_trivial is True
        assert by_name['L4_neutralization_industry'][
            'config']._is_trivial is False

    def test_run_l4_without_market_cap_keeps_legacy_defaults(self, monkeypatch):
        """E6: 不传市值 → 行为与 v3.4.5 一致 (默认 industry trivial)."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()

        captured = _capture_run_single(monkeypatch, runner)
        runner.run_l4_oat(factor_data, fwd_returns, industry)

        assert not any(c['has_key'] for c in captured)
        by_name = {c['config'].name: c for c in captured}
        assert by_name['L4_neutralization_industry']['config']._is_trivial is True
        assert by_name['L4_neutralization_industry+mktcap'][
            'config']._is_trivial is False

    def test_run_l4_b3_reference_receives_market_cap(self, monkeypatch):
        """E7b: L4 的 B3 参照同样带市值."""
        runner = _runner()
        factor_data, fwd_returns, industry = _data()
        market_cap = _make_market_cap(factor_data['factor_0'].index,
                                      factor_data['factor_0'].columns)

        captured = _capture_run_single(monkeypatch, runner)
        runner.run_l4_oat(
            factor_data, fwd_returns, industry, market_cap_data=market_cap)

        b3 = [c for c in captured if c['config'].name == 'B3_full']
        assert len(b3) == 1
        assert b3[0]['market_cap_data'] is market_cap
