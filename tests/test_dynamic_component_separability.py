# -*- coding: utf-8 -*-
"""v3.4.3 O2: Dynamic 组件可分离性 — 管线级 TDD (T1-T5, T10-T13).

对应设计文档 docs/private/DESIGN_DYNAMIC_COMPONENT_SEPARABILITY.md §7;
实施文档 docs/EXECUTION_V3.4.3_DYNAMIC_SEPARABILITY.md §1 E4。

缺陷: module_enabled={'neutralizer': False} 会同时关闭 AR 解耦。
修复契约:
- neutralizer=False 仅关闭中性化, AR 解耦保留;
- 新增 decoupler 开关 (默认 True) 独立控制 AR 解耦;
- 两开关全开时输出与 v3.4.2 逐位一致。
"""
import inspect
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

_PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))

from factor_pipeline.adapters import ImputerAdapter, ProcessingAdapter
from factor_pipeline.modules.factor_decoupler import ARDecoupler, CompositeDecoupler
from factor_pipeline.pipelines_v2 import (
    DynamicFactorPipeline,
    FactorProcessingPipelineV2,
    PipelineV2Config,
)


# =============================================================================
# 夹具
# =============================================================================

def _make_panel(n_periods=60, n_stocks=30, seed=7):
    """合成动态因子面板 (无 NaN, 便于逐位比较)."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2020-01-31', periods=n_periods, freq='ME')
    stocks = [f'S{i:02d}' for i in range(n_stocks)]
    data = rng.standard_normal((n_periods, n_stocks))
    # 注入时序自相关, 使 AR 解耦有实际作用
    for t in range(1, n_periods):
        data[t] = 0.6 * data[t - 1] + 0.4 * data[t]
    return pd.DataFrame(data, index=dates, columns=stocks)


def _make_industry(stocks):
    return pd.Series(
        [f'IND{i % 5}' for i in range(len(stocks))],
        index=stocks,
    )


def _impute(data):
    imputer = ImputerAdapter(strategy='ffill_ts')
    imputer.fit(data)
    return imputer.transform(data)


def _standardize(data):
    std = ProcessingAdapter(process_type='standardization', method='z_score')
    std.fit(data)
    return std.transform(data)


def _make_pipeline(industry, module_enabled=None):
    return DynamicFactorPipeline(
        max_ar_order=2,
        ar_criterion='aic',
        neutralizer_params={'industry_data': industry},
        module_enabled=module_enabled,
    )


@pytest.fixture(scope='module')
def panel():
    return _make_panel()


@pytest.fixture(scope='module')
def industry(panel):
    return _make_industry(panel.columns)


# =============================================================================
# T1: 默认全开 — 与手工链路逐位一致
# =============================================================================

class TestDefaultAllOn:

    def test_default_all_on_bit_identical(self, panel, industry):
        """默认全开: 输出 = Imputer → CompositeDecoupler(默认) → Standardizer."""
        expected = _standardize(
            CompositeDecoupler(
                industry_data=industry, max_ar_order=2, ar_criterion='aic',
            ).fit_transform(_impute(panel))
        )
        result = _make_pipeline(industry).fit_transform(panel)
        np.testing.assert_allclose(
            result.values, expected.values, equal_nan=True, rtol=0, atol=0,
            err_msg='默认全开路径应与 v3.4.2 三重中性化链路逐位一致',
        )


# =============================================================================
# T2: neutralizer=False — AR 解耦保留
# =============================================================================

class TestNeutralizerSeparated:

    def test_neutralizer_off_keeps_ar(self, panel, industry):
        """neutralizer=False 时输出 = Imputer → ARDecoupler → Standardizer."""
        imputed = _impute(panel)
        ar = ARDecoupler(max_order=2, criterion='aic', strength=1.0)
        expected = _standardize(ar.fit_transform(imputed))

        pipeline = _make_pipeline(industry, {'neutralizer': False})
        result = pipeline.fit_transform(panel)

        np.testing.assert_allclose(
            result.values, expected.values, equal_nan=True, rtol=1e-12, atol=1e-12,
            err_msg='neutralizer=False 必须保留 AR 解耦, 不得退化为 imputer+z-score',
        )
        # AR 组件确实被拟合
        assert pipeline._decoupler is not None
        assert pipeline._decoupler._ar_decoupler is not None
        assert pipeline.get_decoupling_summary()['ar_summary'] is not None


# =============================================================================
# T3: decoupler=False — 中性化保留
# =============================================================================

class TestDecouplerSeparated:

    def test_decoupler_off_keeps_neutralization(self, panel, industry):
        """decoupler=False 时跳过 AR, 但中性化仍执行."""
        pipeline = _make_pipeline(industry, {'decoupler': False})
        result = pipeline.fit_transform(panel)

        assert pipeline._decoupler is not None
        assert pipeline._decoupler._ar_decoupler is None, \
            'decoupler=False 不应构建 ARDecoupler'
        summary = pipeline.get_decoupling_summary()
        assert summary['ar_summary'] is None
        assert summary['neutralization_summary'], '中性化摘要不应为空'

        # 中性化确实改变了数值 (不是 identity)
        assert not np.allclose(result.values, _standardize(_impute(panel)).values)


# =============================================================================
# T4: 两开关全关 — identity
# =============================================================================

class TestBothOff:

    def test_both_off_identity(self, panel, industry):
        """两开关全关: 解耦步骤为 identity."""
        pipeline = _make_pipeline(
            industry, {'neutralizer': False, 'decoupler': False},
        )
        result = pipeline.fit_transform(panel)
        expected = _standardize(_impute(panel))

        assert pipeline._decoupler is None
        assert pipeline.get_decoupling_summary() == {}
        np.testing.assert_allclose(
            result.values, expected.values, equal_nan=True, rtol=0, atol=0,
        )


# =============================================================================
# T5: 摘要矩阵 (4 组合)
# =============================================================================

class TestSummaryMatrix:

    @pytest.mark.parametrize('me,expect_ar,expect_neut', [
        (None, True, True),
        ({'neutralizer': False}, True, False),
        ({'decoupler': False}, False, True),
        ({'neutralizer': False, 'decoupler': False}, False, False),
    ])
    def test_summary_matrix(self, panel, industry, me, expect_ar, expect_neut):
        """ar_summary 仅在 AR 开启时非 None; 全关时摘要为 {}."""
        pipeline = _make_pipeline(industry, me)
        pipeline.fit(panel)
        summary = pipeline.get_decoupling_summary()

        if expect_ar:
            assert summary.get('ar_summary') is not None
        else:
            assert summary.get('ar_summary') is None

        if expect_neut:
            assert summary.get('neutralization_summary')
        else:
            assert summary.get('neutralization_summary') in ({}, None)


# =============================================================================
# T10: _create_pipeline 透传 decoupler 开关
# =============================================================================

class TestPipelineFactory:

    def test_create_pipeline_passes_decoupler_flag(self):
        """_create_pipeline('dynamic') 透传 neutralizer/decoupler 开关."""
        pipeline_v2 = FactorProcessingPipelineV2(PipelineV2Config())
        pipe = pipeline_v2._create_pipeline(
            'dynamic', {}, {'neutralizer': False, 'decoupler': True},
        )
        assert pipe._neutralizer_enabled is False
        assert pipe._decoupler_enabled is True

        pipe2 = pipeline_v2._create_pipeline(
            'dynamic', {}, {'neutralizer': True, 'decoupler': False},
        )
        assert pipe2._neutralizer_enabled is True
        assert pipe2._decoupler_enabled is False


# =============================================================================
# T12: 构造参数默认值
# =============================================================================

class TestSignatureDefaults:

    def test_composite_signature_defaults(self):
        """CompositeDecoupler 两个新开关默认 True (向后兼容)."""
        params = inspect.signature(CompositeDecoupler.__init__).parameters
        assert params['enable_neutralization'].default is True
        assert params['enable_ar'].default is True


# =============================================================================
# T13: skip_stage2 在仅 AR 时仍跳过 AR
# =============================================================================

class TestSkipStage2:

    def test_skip_stage2_still_skips_ar_when_neutralizer_off(self, panel, industry):
        """neutralizer=False + decoupler=True 时, skip_stage2 仍跳过 AR → identity."""
        pipeline = _make_pipeline(industry, {'neutralizer': False})
        pipeline.fit(panel)
        result = pipeline.transform(panel, skip_stage2=True)
        expected = _standardize(_impute(panel))

        np.testing.assert_allclose(
            result.values, expected.values, equal_nan=True, rtol=1e-12, atol=1e-12,
            err_msg='skip_stage2 应跳过 AR; 中性化关闭时解耦步骤退化为 identity',
        )
