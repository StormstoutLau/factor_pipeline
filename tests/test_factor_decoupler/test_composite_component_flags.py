# -*- coding: utf-8 -*-
"""v3.4.3 O2: CompositeDecoupler 子组件开关 — 模块级 TDD (T6-T9).

对应设计文档 docs/private/DESIGN_DYNAMIC_COMPONENT_SEPARABILITY.md §5.1/§7;
实施文档 docs/EXECUTION_V3.4.3_DYNAMIC_SEPARABILITY.md §1 E4。

阶段矩阵:
| enable_neutralization | enable_ar | 结果 |
| True  | True  | 三重中性化 (与 v3.4.2 一致) |
| True  | False | Stage 1 + Stage 3 中性化 |
| False | True  | 仅 AR 解耦 |
| False | False | identity |
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

_PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))

from factor_pipeline.modules.factor_decoupler import ARDecoupler, CompositeDecoupler


def _make_panel(n_periods=50, n_stocks=30, seed=11):
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2021-01-31', periods=n_periods, freq='ME')
    stocks = [f'S{i:02d}' for i in range(n_stocks)]
    data = rng.standard_normal((n_periods, n_stocks))
    for t in range(1, n_periods):
        data[t] = 0.5 * data[t - 1] + 0.5 * data[t]
    return pd.DataFrame(data, index=dates, columns=stocks)


def _industry(columns):
    return pd.Series([f'IND{i % 4}' for i in range(len(columns))], index=columns)


@pytest.fixture(scope='module')
def panel():
    return _make_panel()


@pytest.fixture(scope='module')
def industry(panel):
    return _industry(panel.columns)


# =============================================================================
# T6: 两开关全关 → identity
# =============================================================================

def test_both_disabled_identity(panel, industry):
    dec = CompositeDecoupler(
        industry_data=industry,
        enable_neutralization=False,
        enable_ar=False,
    )
    result = dec.fit_transform(panel)

    np.testing.assert_allclose(
        result.values, panel.values, equal_nan=True, rtol=0, atol=0,
        err_msg='两开关全关时 CompositeDecoupler 应为 identity',
    )
    summary = dec.get_summary()
    assert summary['ar_summary'] is None
    assert summary['neutralization_summary'] == {}


# =============================================================================
# T7: 仅 AR → 与 ARDecoupler 逐位一致
# =============================================================================

def test_ar_only_matches_ar_decoupler(panel, industry):
    dec = CompositeDecoupler(
        industry_data=industry,
        max_ar_order=3,
        ar_criterion='aic',
        decorrelation_strength=1.0,
        enable_neutralization=False,
        enable_ar=True,
    )
    result = dec.fit_transform(panel)

    ar = ARDecoupler(max_order=3, criterion='aic', strength=1.0)
    expected = ar.fit_transform(panel)

    np.testing.assert_allclose(
        result.values, expected.values, equal_nan=True, rtol=1e-12, atol=1e-12,
        err_msg='enable_neutralization=False 时应等价于纯 ARDecoupler',
    )
    assert dec._ar_decoupler is not None


# =============================================================================
# T8: 仅中性化 → AR 不构建
# =============================================================================

def test_neutralization_only(panel, industry):
    dec = CompositeDecoupler(
        industry_data=industry,
        enable_neutralization=True,
        enable_ar=False,
    )
    result = dec.fit_transform(panel)

    assert dec._ar_decoupler is None, 'enable_ar=False 不应构建 ARDecoupler'
    summary = dec.get_summary()
    assert summary['ar_summary'] is None
    assert summary['neutralization_summary'], '中性化摘要不应为空'
    assert not np.allclose(result.values, panel.values), '中性化应改变数值'


# =============================================================================
# T9: 全开 + skip_stage2 → 等价于仅中性化
# =============================================================================

def test_skip_stage2_with_flags_on_unchanged(panel, industry):
    full = CompositeDecoupler(industry_data=industry, max_ar_order=3)
    full.fit(panel)
    skipped = full.transform(panel, skip_stage2=True)
    assert full.get_summary()['ar_summary'] is not None, 'fit 仍应拟合 AR 模型'

    neut_only = CompositeDecoupler(
        industry_data=industry, max_ar_order=3,
        enable_neutralization=True, enable_ar=False,
    )
    expected = neut_only.fit_transform(panel)

    np.testing.assert_allclose(
        skipped.values, expected.values, equal_nan=True, rtol=0, atol=0,
        err_msg='skip_stage2 路径应与仅中性化路径一致 (Stage 1 + Stage 3)',
    )
