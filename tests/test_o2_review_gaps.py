# -*- coding: utf-8 -*-
"""v3.4.3 O2 独立复审 R-2 覆盖缺口补充测试 (12 例).

对应 docs/audit/2026-11-12-dynamic-separability-audit.md §5.3 R-2 登记的 6 项缺口:
  G1 (4 例): market_cap_data 非空时 CompositeDecoupler 开关组合
  G2 (3 例): threat_level × 开关组合 (threat_level 仅记录, 不参与计算)
  G3 (1 例): decoupler=False 时 diagnose_hidden_effects 抛 DiagnosticContractError
  G4 (2 例): Static/Mixed 管道忽略 'decoupler' 键
  G5 (1 例): enable_ar=False 后 _get_ar_phi_for_diagnosis() 返回 None
  G6 (1 例): AblationRunner L1_neutralizer_off 臂在新语义下 Dynamic 保留 AR

所有用例针对既有实现 (v3.4.3), 预期直接 Green; 失败即真实缺陷。
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

_PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))

from factor_pipeline.adapters import ProcessingAdapter
from factor_pipeline.backtest.ablation_runner import AblationConfig
from factor_pipeline.modules.factor_decoupler import ARDecoupler, CompositeDecoupler
from factor_pipeline.modules.factor_decoupler.diagnostics.hidden_effect import (
    DiagnosticContractError,
)
from factor_pipeline.pipelines_v2 import (
    DynamicFactorPipeline,
    MixedFactorPipeline,
    StaticFactorPipeline,
)


# =============================================================================
# 夹具
# =============================================================================

def _make_panel(n_periods=50, n_stocks=30, seed=23):
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2021-01-31', periods=n_periods, freq='ME')
    stocks = [f'S{i:02d}' for i in range(n_stocks)]
    data = rng.standard_normal((n_periods, n_stocks))
    for t in range(1, n_periods):
        data[t] = 0.5 * data[t - 1] + 0.5 * data[t]
    return pd.DataFrame(data, index=dates, columns=stocks)


def _industry(columns):
    return pd.Series([f'IND{i % 4}' for i in range(len(columns))], index=columns)


def _market_cap(panel, seed=99):
    """市值面板 (日期 × 股票, 正值) — DualNeutralizer Stage 2 使用."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.uniform(10.0, 500.0, size=panel.shape),
        index=panel.index, columns=panel.columns,
    )


def _zscore(data):
    std = ProcessingAdapter(process_type='standardization', method='z_score')
    std.fit(data)
    return std.transform(data)


@pytest.fixture(scope='module')
def panel():
    return _make_panel()


@pytest.fixture(scope='module')
def industry(panel):
    return _industry(panel.columns)


@pytest.fixture(scope='module')
def market_cap(panel):
    return _market_cap(panel)


# =============================================================================
# G1: market_cap_data 非空时四组合 (4 例)
# =============================================================================

class TestMarketCapCombinations:

    def test_g1a_mc_ignored_when_neutralization_off(self, panel, industry, market_cap):
        """G1a: enable_neutralization=False 时 market_cap 不参与, 等价纯 ARDecoupler."""
        dec = CompositeDecoupler(
            industry_data=industry, market_cap_data=market_cap,
            max_ar_order=3, enable_neutralization=False,
        )
        result = dec.fit_transform(panel)

        ar = ARDecoupler(max_order=3, criterion='aic', strength=1.0)
        expected = ar.fit_transform(panel)
        np.testing.assert_allclose(
            result.values, expected.values, equal_nan=True, rtol=1e-12, atol=1e-12,
            err_msg='中性化关闭时市值数据不应影响输出',
        )

    def test_g1b_mc_changes_neutralization_only_path(self, panel, industry, market_cap):
        """G1b: enable_ar=False 时 market_cap 进入 Stage 2 回归, 输出与无市值不同."""
        with_mc = CompositeDecoupler(
            industry_data=industry, market_cap_data=market_cap, enable_ar=False,
        ).fit_transform(panel)
        without_mc = CompositeDecoupler(
            industry_data=industry, market_cap_data=None, enable_ar=False,
        ).fit_transform(panel)

        assert not np.allclose(with_mc.values, without_mc.values), \
            '市值数据应通过 Stage 2 回归影响仅中性化路径的输出'

    def test_g1c_mc_both_off_identity(self, panel, industry, market_cap):
        """G1c: market_cap 非空 + 两开关全关 → identity."""
        dec = CompositeDecoupler(
            industry_data=industry, market_cap_data=market_cap,
            enable_neutralization=False, enable_ar=False,
        )
        result = dec.fit_transform(panel)
        np.testing.assert_allclose(
            result.values, panel.values, equal_nan=True, rtol=0, atol=0,
        )

    def test_g1d_mc_full_on_differs_from_partial(self, panel, industry, market_cap):
        """G1d: 全开 (含市值) 与仅 AR / 仅中性化均不同, 摘要契约完整."""
        dec = CompositeDecoupler(
            industry_data=industry, market_cap_data=market_cap, max_ar_order=3,
        )
        full = dec.fit_transform(panel)
        summary = dec.get_summary()
        assert summary['ar_summary'] is not None
        assert summary['neutralization_summary']

        ar_only = CompositeDecoupler(
            industry_data=industry, market_cap_data=market_cap,
            max_ar_order=3, enable_neutralization=False,
        ).fit_transform(panel)
        neut_only = CompositeDecoupler(
            industry_data=industry, market_cap_data=market_cap, enable_ar=False,
        ).fit_transform(panel)

        assert not np.allclose(full.values, ar_only.values)
        assert not np.allclose(full.values, neut_only.values)


# =============================================================================
# G2: threat_level × 开关组合 (3 例)
# =============================================================================

class TestThreatLevelWithFlags:

    def test_g2a_threat_level_recorded_not_computed(self, panel, industry):
        """G2a: threat_level 仅记录不参与计算 — 输出与 None 逐位一致."""
        dec = CompositeDecoupler(industry_data=industry, max_ar_order=3)
        dec.fit(panel)
        baseline = dec.transform(panel)
        with_tau = dec.transform(panel, threat_level=0.5)

        np.testing.assert_allclose(
            with_tau.values, baseline.values, equal_nan=True, rtol=0, atol=0,
            err_msg='threat_level 不改变默认路径计算结果 (E5 契约: 仅记录)',
        )
        assert dec._threat_level == 0.5, 'threat_level 应被记录供诊断/审计'

    def test_g2b_threat_level_with_skip_stage2(self, panel, industry):
        """G2b: threat_level + skip_stage2=True → 等价仅中性化路径."""
        dec = CompositeDecoupler(industry_data=industry, max_ar_order=3)
        dec.fit(panel)
        skipped = dec.transform(panel, threat_level=0.8, skip_stage2=True)

        neut_only = CompositeDecoupler(
            industry_data=industry, max_ar_order=3, enable_ar=False,
        ).fit_transform(panel)
        np.testing.assert_allclose(
            skipped.values, neut_only.values, equal_nan=True, rtol=0, atol=0,
        )

    def test_g2c_threat_level_ignored_when_neutralization_off(self, panel, industry):
        """G2c: 中性化关闭时 threat_level 被忽略 (设计 §5.1 文档化行为)."""
        dec = CompositeDecoupler(
            industry_data=industry, enable_neutralization=False, max_ar_order=3,
        )
        dec.fit(panel)
        baseline = dec.transform(panel)
        with_tau = dec.transform(panel, threat_level=0.7)

        np.testing.assert_allclose(
            with_tau.values, baseline.values, equal_nan=True, rtol=1e-12, atol=1e-12,
        )
        assert dec._threat_level == 0.7


# =============================================================================
# G3: decoupler=False 时诊断契约 (1 例)
# =============================================================================

class TestDiagnosticContractWithoutAR:

    def test_g3_diagnose_raises_when_ar_disabled(self, panel, industry):
        """G3: decoupler=False (AR 缺失) 时 diagnose_hidden_effects fail-loud."""
        pipeline = DynamicFactorPipeline(
            neutralizer_params={'industry_data': industry},
            module_enabled={'decoupler': False},
        )
        pipeline.fit(panel)
        dec = pipeline._decoupler
        assert dec is not None
        assert dec._ar_decoupler is None

        with pytest.raises(DiagnosticContractError):
            dec.diagnose_hidden_effects(panel, controls=panel)


# =============================================================================
# G4: Static/Mixed 管道忽略 'decoupler' 键 (2 例)
# =============================================================================

def _make_df_with_nan(n_periods=40, n_stocks=10, seed=42):
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2022-01-01', periods=n_periods, freq='ME')
    stocks = [f'S{i:02d}' for i in range(n_stocks)]
    df = pd.DataFrame(rng.standard_normal((n_periods, n_stocks)) * 2.0 + 1.0,
                      index=dates, columns=stocks)
    df.iloc[0, 0] = np.nan
    df.iloc[5, 2] = np.nan
    return df


class TestOtherPipelinesIgnoreDecouplerKey:

    def test_g4a_static_pipeline_ignores_decoupler_key(self):
        """G4a: StaticFactorPipeline 不读取 'decoupler' 键, 输出与默认构造一致."""
        df = _make_df_with_nan()
        default = StaticFactorPipeline().fit_transform(df)
        with_key = StaticFactorPipeline(
            module_enabled={'decoupler': False},
        ).fit_transform(df)

        pd.testing.assert_frame_equal(default, with_key)
        for _, step in StaticFactorPipeline().steps:
            assert step.enabled is True

    def test_g4b_mixed_pipeline_ignores_decoupler_key(self):
        """G4b: MixedFactorPipeline 不读取 'decoupler' 键, 输出与默认构造一致."""
        df = _make_df_with_nan()
        default = MixedFactorPipeline().fit_transform(df)
        with_key = MixedFactorPipeline(
            module_enabled={'decoupler': False},
        ).fit_transform(df)

        pd.testing.assert_frame_equal(default, with_key)


# =============================================================================
# G5: enable_ar=False 后诊断钩子返回 None (1 例)
# =============================================================================

class TestDiagnosisHookWithoutAR:

    def test_g5_ar_phi_hook_returns_none(self, panel, industry):
        """G5: enable_ar=False 拟合后 _get_ar_phi_for_diagnosis() 返回 None."""
        dec = CompositeDecoupler(industry_data=industry, enable_ar=False)
        dec.fit(panel)
        assert dec.is_fitted
        assert dec._get_ar_phi_for_diagnosis() is None


# =============================================================================
# G6: AblationRunner L1 臂新语义 (1 例)
# =============================================================================

class TestAblationL1NeutralizerArmSemantics:

    def test_g6_l1_neutralizer_off_arm_keeps_ar(self, panel, industry):
        """G6: run_l1 的 L1_neutralizer_off 臂 (module_enabled={'neutralizer': False})
        在 v3.4.3 语义下 Dynamic 保留 AR — 消融可单独度量中性化贡献."""
        arm = AblationConfig(
            name='L1_neutralizer_off', layer='L1',
            module_enabled={'neutralizer': False}, baseline_level='B3',
        )
        pipeline = DynamicFactorPipeline(
            module_enabled=arm.module_enabled,
            neutralizer_params={'industry_data': industry},
        )
        result = pipeline.fit_transform(panel)

        assert pipeline._decoupler is not None
        assert pipeline._decoupler._ar_decoupler is not None, \
            'L1 neutralizer 臂必须保留 AR 解耦 (O2 修复目的)'
        assert pipeline._decoupler._enable_neutralization is False
        assert pipeline.get_decoupling_summary()['ar_summary'] is not None
        # 不再退化为 imputer + z-score
        assert not np.allclose(result.values, _zscore(panel).values)
