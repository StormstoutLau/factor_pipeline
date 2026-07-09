# -*- coding: utf-8 -*-
"""隐藏效应诊断 Mixin 测试 (V3.1.0 E1, §2)

TDD Red 阶段: 测试先于实现.

覆盖 §1.8 的 21 个测试 (E1-T01 ~ E1-T21):
1. Mixin 非侵入性
2. diagnose_hidden_effects 返回 4 键
3. 增量内生性检测 (有内生 / 无内生 / 无控制)
4. 信息损失 (signal_lost / noise_removed / 无收益)
5. 平稳性 vs 内生性 (ADF 通过 / 失败 / 陷阱警告)
6. 方法敏感性 (high / low)
7. 管线集成 (disabled / enabled)
8. 继承关系 (Composite / AR)
9. IC 计算 (Spearman)
10. NaN 处理
11. 向后兼容 v3.0.0
12. 两阶段分离 (必须先 fit)
"""
import inspect
import numpy as np
import pandas as pd
import pytest

from factor_pipeline.modules.factor_decoupler import (
    CompositeDecoupler,
    ARDecoupler,
)
from factor_pipeline.modules.factor_decoupler.diagnostics.hidden_effect import (
    HiddenEffectDiagnosticMixin,
)
from factor_pipeline.pipelines_v2 import (
    FactorProcessingPipelineV2,
    PipelineV2Config,
)


# ============================================================
# 测试数据生成器
# ============================================================

def _make_factor_data(n_periods=120, n_stocks=30, seed=42, ar_coef=0.5):
    """生成 AR(1) 因子数据 (T, N)"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2020-01-01', periods=n_periods, freq='ME')
    stocks = [f'S{i:03d}' for i in range(n_stocks)]
    data = np.zeros((n_periods, n_stocks))
    for j in range(n_stocks):
        data[0, j] = rng.standard_normal()
        for t in range(1, n_periods):
            data[t, j] = ar_coef * data[t - 1, j] + rng.standard_normal()
    return pd.DataFrame(data, index=dates, columns=stocks)


def _make_endogenous_controls(factor_data, phi=0.5, seed=7):
    """构造与因子强相关的控制变量 (制造增量内生性)"""
    rng = np.random.default_rng(seed)
    # 控制变量 = 因子的线性组合 + 小噪声 → cov(η, ΔX) ≠ 0
    controls = factor_data * 0.8 + rng.standard_normal(factor_data.shape) * 0.01
    return controls


def _make_clean_controls(factor_data, seed=9):
    """构造与因子无关的控制变量 (无内生性)"""
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.standard_normal(factor_data.shape),
        index=factor_data.index,
        columns=factor_data.columns,
    )


def _make_returns_linked_to_factor(factor_data, seed=11):
    """构造与因子相关的未来收益 (用于 IC 诊断)"""
    rng = np.random.default_rng(seed)
    # returns = factor (信号) + 噪声
    return factor_data + rng.standard_normal(factor_data.shape) * 0.5


def _fit_composite(factor_data, **kwargs):
    """构造并拟合一个 CompositeDecoupler"""
    decoupler = CompositeDecoupler(max_ar_order=1, **kwargs)
    decoupler.fit(factor_data)
    return decoupler


def _fit_ar(factor_data, **kwargs):
    """构造并拟合一个 ARDecoupler"""
    decoupler = ARDecoupler(max_order=1, min_order=1, **kwargs)
    decoupler.fit(factor_data)
    return decoupler


class _StubIdentityDecoupler(HiddenEffectDiagnosticMixin):
    """测试桩: identity transform, 已拟合. 用于隔离 _diagnose_method_sensitivity 逻辑.

    在方法敏感性 'high' 测试中, 需要三方法 (AR/diff/HP) IC 一致 (cv < 0.2).
    真实 CompositeDecoupler 的 AR(1) 会完美拟合线性趋势导致残差为纯噪声 (ar_ic≈0),
    使三方法 IC 不可能一致. 用 identity stub 可控制 ar_ic = corr(factor, returns),
    配合时间不变的截面信号 (线性趋势) 实现三方法 IC 一致.
    """
    def __init__(self):
        self.is_fitted = True

    def transform(self, factor_data):
        return factor_data


# ============================================================
# E1-T01: Mixin 非侵入性
# ============================================================

class TestMixinNotInvasive:
    """E1-T01: Mixin 不修改 fit/transform 签名"""

    def test_mixin_not_invasive(self):
        # Mixin 自身不应定义 fit / transform (不侵入宿主类)
        assert not hasattr(HiddenEffectDiagnosticMixin, 'fit')
        assert not hasattr(HiddenEffectDiagnosticMixin, 'transform')
        # diagnose_hidden_effects 应该是 Mixin 提供的唯一新公共方法
        assert hasattr(HiddenEffectDiagnosticMixin, 'diagnose_hidden_effects')


# ============================================================
# E1-T02: diagnose_hidden_effects 返回 4 键
# ============================================================

class TestDiagnoseReturnsFourKeys:
    """E1-T02: 返回 dict 含 4 个诊断键"""

    def test_diagnose_returns_four_keys(self):
        factor_data = _make_factor_data(n_periods=80, n_stocks=20)
        controls = _make_clean_controls(factor_data)
        returns = _make_returns_linked_to_factor(factor_data)
        decoupler = _fit_composite(factor_data)
        result = decoupler.diagnose_hidden_effects(factor_data, controls, returns)
        expected_keys = {
            'incremental_endogeneity',
            'information_loss',
            'stationarity_vs_endogeneity',
            'method_sensitivity',
        }
        assert set(result.keys()) == expected_keys


# ============================================================
# E1-T03 ~ E1-T05: 增量内生性诊断
# ============================================================

class TestIncrementalEndogeneity:
    """E1-T03/T04/T05: 增量内生性诊断"""

    def test_incremental_endogeneity_detected(self):
        """E1-T03: 已知内生数据 → is_incremental_endogenous=True"""
        factor_data = _make_factor_data(n_periods=120, n_stocks=30, ar_coef=0.6)
        controls = _make_endogenous_controls(factor_data)  # 与因子强相关
        decoupler = _fit_composite(factor_data)
        result = decoupler.diagnose_hidden_effects(factor_data, controls)
        inc = result['incremental_endogeneity']
        assert inc['is_incremental_endogenous'] is True

    def test_incremental_endogeneity_clean(self):
        """E1-T04: 无内生数据 → is_incremental_endogenous=False"""
        factor_data = _make_factor_data(n_periods=120, n_stocks=30, ar_coef=0.5)
        controls = _make_clean_controls(factor_data)  # 与因子无关
        decoupler = _fit_composite(factor_data)
        result = decoupler.diagnose_hidden_effects(factor_data, controls)
        inc = result['incremental_endogeneity']
        assert inc['is_incremental_endogenous'] is False

    def test_incremental_no_controls(self):
        """E1-T05: controls=None → 返回 NaN + 诊断信息"""
        factor_data = _make_factor_data()
        decoupler = _fit_composite(factor_data)
        result = decoupler.diagnose_hidden_effects(factor_data, controls=None)
        inc = result['incremental_endogeneity']
        assert np.isnan(inc['cov_eta_delta_X'])
        assert inc['is_incremental_endogenous'] is False
        assert 'diagnostic' in inc


# ============================================================
# E1-T06 ~ E1-T08: 信息损失诊断
# ============================================================

class TestInformationLoss:
    """E1-T06/T07/T08: 信息损失 (IC 衰减)"""

    def test_information_loss_signal_lost(self):
        """E1-T06: AR 解耦丢失信号 → interpretation='signal_lost'"""
        # 构造: returns = factor (强信号), AR 解耦后残差与 returns 弱相关
        rng = np.random.default_rng(42)
        n_periods, n_stocks = 120, 30
        dates = pd.date_range('2020-01-01', periods=n_periods, freq='ME')
        stocks = [f'S{i:03d}' for i in range(n_stocks)]
        # 因子: 强 AR(1) 0.9 — AR 残差会丢失大部分水平信号
        data = np.zeros((n_periods, n_stocks))
        for j in range(n_stocks):
            for t in range(1, n_periods):
                data[t, j] = 0.9 * data[t - 1, j] + rng.standard_normal() * 0.1
        factor_data = pd.DataFrame(data, index=dates, columns=stocks)
        # returns 与原始因子强相关 (水平值信号)
        returns = factor_data + rng.standard_normal(factor_data.shape) * 0.05

        decoupler = _fit_composite(factor_data)
        result = decoupler.diagnose_hidden_effects(factor_data, returns=returns)
        info = result['information_loss']
        assert info['interpretation'] == 'signal_lost'

    def test_information_loss_noise_removed(self):
        """E1-T07: AR 解耦去噪 → interpretation='noise_removed'"""
        # 构造: returns 与 AR 残差(新息)强相关, 与原始因子也基本同向
        rng = np.random.default_rng(123)
        n_periods, n_stocks = 120, 30
        dates = pd.date_range('2020-01-01', periods=n_periods, freq='ME')
        stocks = [f'S{i:03d}' for i in range(n_stocks)]
        # 残差(新息)信号
        innovations = rng.standard_normal((n_periods, n_stocks))
        # 因子 = 累积新息 (随机游走, AR 接近 1)
        factor_vals = np.cumsum(innovations, axis=0)
        factor_data = pd.DataFrame(factor_vals, index=dates, columns=stocks)
        # returns 与新息强相关 → AR 解耦保留信号
        returns = pd.DataFrame(
            innovations + rng.standard_normal((n_periods, n_stocks)) * 0.05,
            index=dates, columns=stocks,
        )
        decoupler = _fit_composite(factor_data)
        result = decoupler.diagnose_hidden_effects(factor_data, returns=returns)
        info = result['information_loss']
        assert info['interpretation'] == 'noise_removed'

    def test_information_loss_no_returns(self):
        """E1-T08: returns=None → NaN + 诊断信息"""
        factor_data = _make_factor_data()
        decoupler = _fit_composite(factor_data)
        result = decoupler.diagnose_hidden_effects(factor_data, returns=None)
        info = result['information_loss']
        assert np.isnan(info['ic_before'])
        assert np.isnan(info['ic_after'])
        assert info['interpretation'] == 'no returns provided'


# ============================================================
# E1-T09 ~ E1-T11: 平稳性 vs 内生性
# ============================================================

class TestStationarityVsEndogeneity:
    """E1-T09/T10/T11: ADF 检验 + 内生性陷阱警告"""

    def test_stationarity_adf_passes(self):
        """E1-T09: 平稳序列 → adf_passes=True"""
        # AR(1) 0.3 → 平稳序列, ADF 应通过
        factor_data = _make_factor_data(n_periods=120, n_stocks=30, ar_coef=0.3)
        decoupler = _fit_composite(factor_data)
        result = decoupler.diagnose_hidden_effects(factor_data)
        stat = result['stationarity_vs_endogeneity']
        assert stat['adf_passes'] is True

    def test_stationarity_adf_fails(self):
        """E1-T10: 单位根序列 → adf_passes=False"""
        # 随机游走 (AR=1.0) → 单位根, ADF 应失败
        rng = np.random.default_rng(5)
        n_periods, n_stocks = 120, 30
        dates = pd.date_range('2020-01-01', periods=n_periods, freq='ME')
        stocks = [f'S{i:03d}' for i in range(n_stocks)]
        data = np.cumsum(rng.standard_normal((n_periods, n_stocks)), axis=0)
        factor_data = pd.DataFrame(data, index=dates, columns=stocks)
        decoupler = _fit_composite(factor_data)
        result = decoupler.diagnose_hidden_effects(factor_data)
        stat = result['stationarity_vs_endogeneity']
        assert stat['adf_passes'] is False

    def test_stationarity_warning_trap(self):
        """E1-T11: ADF 通过 + 内生 → 警告 'ADF 通过 ≠ 内生性消除'"""
        # 平稳序列 + 与因子强相关的控制变量 → 内生性陷阱
        factor_data = _make_factor_data(n_periods=120, n_stocks=30, ar_coef=0.3)
        controls = _make_endogenous_controls(factor_data)
        decoupler = _fit_composite(factor_data)
        result = decoupler.diagnose_hidden_effects(factor_data, controls=controls)
        stat = result['stationarity_vs_endogeneity']
        assert stat['adf_passes'] is True
        assert stat['endogeneity_present'] is True
        assert 'ADF 通过 ≠ 内生性消除' in stat['warning']


# ============================================================
# E1-T12 ~ E1-T13: 方法敏感性
# ============================================================

class TestMethodSensitivity:
    """E1-T12/T13: AR / 差分 / HP 滤波 IC 一致性"""

    def test_method_sensitivity_high(self):
        """E1-T12: 三方法 IC 一致 → consistency='high'"""
        # 构造: 线性趋势 factor_t = slope * t + tiny_noise, returns = slope (截面分散, 时间不变).
        # 截面信号 (slope) 时间不变 → 三方法都保留同一截面排序 → IC 一致.
        # 用 identity stub 控制 ar_ic = corr(factor, returns) ≈ 1.0,
        # diff_ic = corr(slope, slope) ≈ 1.0, hp_ic (HP趋势) = corr(slope*t, slope) ≈ 1.0.
        rng = np.random.default_rng(42)
        n_periods, n_stocks = 120, 30
        dates = pd.date_range('2020-01-01', periods=n_periods, freq='ME')
        stocks = [f'S{i:03d}' for i in range(n_stocks)]
        slope = rng.standard_normal(n_stocks)
        t_arr = np.arange(n_periods).reshape(-1, 1)
        factor_vals = slope * t_arr + rng.standard_normal((n_periods, n_stocks)) * 0.001
        factor_data = pd.DataFrame(factor_vals, index=dates, columns=stocks)
        returns = pd.DataFrame(
            np.tile(slope, (n_periods, 1))
            + rng.standard_normal((n_periods, n_stocks)) * 0.001,
            index=dates, columns=stocks,
        )
        decoupler = _StubIdentityDecoupler()
        result = decoupler.diagnose_hidden_effects(factor_data, returns=returns)
        ms = result['method_sensitivity']
        assert ms['consistency'] == 'high'

    def test_method_sensitivity_low(self):
        """E1-T13: 三方法 IC 差异大 → consistency='low'"""
        # 构造: 强 AR(1) 水平信号 — AR 残差丢失信号, 差分/HP 行为不同 → IC 差异大
        rng = np.random.default_rng(99)
        n_periods, n_stocks = 120, 30
        dates = pd.date_range('2020-01-01', periods=n_periods, freq='ME')
        stocks = [f'S{i:03d}' for i in range(n_stocks)]
        data = np.zeros((n_periods, n_stocks))
        for j in range(n_stocks):
            for t in range(1, n_periods):
                data[t, j] = 0.95 * data[t - 1, j] + rng.standard_normal() * 0.05
        factor_data = pd.DataFrame(data, index=dates, columns=stocks)
        # returns 与水平值强相关 (AR 解耦会丢信号, 但 diff/HP 部分保留)
        returns = pd.DataFrame(
            factor_data.values + rng.standard_normal((n_periods, n_stocks)) * 0.02,
            index=dates, columns=stocks,
        )
        decoupler = _fit_composite(factor_data)
        result = decoupler.diagnose_hidden_effects(factor_data, returns=returns)
        ms = result['method_sensitivity']
        assert ms['consistency'] == 'low'


# ============================================================
# E1-T14 ~ E1-T15: 管线集成
# ============================================================

class TestPipelineIntegration:
    """E1-T14/T15: PipelineV2 集成"""

    def test_pipeline_diagnose_disabled(self):
        """E1-T14: enable=False → 返回 None"""
        config = PipelineV2Config(enable_hidden_effect_diagnosis=False)
        pipeline = FactorProcessingPipelineV2(config)
        factor_data = _make_factor_data()
        result = pipeline.diagnose_hidden_effects(factor_data)
        assert result is None

    def test_pipeline_diagnose_enabled(self):
        """E1-T15: enable=True → 返回诊断 dict"""
        config = PipelineV2Config(enable_hidden_effect_diagnosis=True)
        pipeline = FactorProcessingPipelineV2(config)
        factor_data = _make_factor_data(n_periods=80, n_stocks=15)
        # 直接注入一个已拟合的解耦器 (避免完整 fit 流程, 聚焦委托逻辑)
        decoupler = _fit_composite(factor_data)
        pipeline.decoupler = decoupler
        result = pipeline.diagnose_hidden_effects(factor_data)
        assert isinstance(result, dict)
        assert 'incremental_endogeneity' in result


# ============================================================
# E1-T16 ~ E1-T17: 继承关系
# ============================================================

class TestInheritance:
    """E1-T16/T17: CompositeDecoupler / ARDecoupler 继承 Mixin"""

    def test_composite_decoupler_inherits_mixin(self):
        """E1-T16: CompositeDecoupler 实例有 diagnose_hidden_effects 方法"""
        decoupler = CompositeDecoupler()
        assert isinstance(decoupler, HiddenEffectDiagnosticMixin)
        assert callable(getattr(decoupler, 'diagnose_hidden_effects', None))

    def test_ar_decoupler_inherits_mixin(self):
        """E1-T17: ARDecoupler 实例有 diagnose_hidden_effects 方法"""
        decoupler = ARDecoupler()
        assert isinstance(decoupler, HiddenEffectDiagnosticMixin)
        assert callable(getattr(decoupler, 'diagnose_hidden_effects', None))


# ============================================================
# E1-T18: IC 计算 (Spearman)
# ============================================================

class TestICComputationSpearman:
    """E1-T18: IC 计算用 Spearman 秩相关"""

    def test_ic_computation_spearman(self):
        factor_data = _make_factor_data(n_periods=60, n_stocks=20)
        returns = _make_returns_linked_to_factor(factor_data)
        decoupler = _fit_composite(factor_data)
        ic = decoupler._compute_cross_sectional_ic_mean(factor_data, returns)
        # 正相关 (returns 含 factor 信号) → IC > 0
        assert not np.isnan(ic)
        assert ic > 0


# ============================================================
# E1-T19: NaN 处理
# ============================================================

class TestNaNHandling:
    """E1-T19: 含 NaN 数据不崩溃"""

    def test_nan_handling(self):
        factor_data = _make_factor_data(n_periods=80, n_stocks=20)
        # 注入 NaN
        factor_data.iloc[5, 3] = np.nan
        factor_data.iloc[10, 7] = np.nan
        controls = _make_clean_controls(factor_data)
        controls.iloc[8, 2] = np.nan
        returns = _make_returns_linked_to_factor(factor_data)
        returns.iloc[12, 5] = np.nan
        decoupler = _fit_composite(factor_data)
        # 不应抛异常
        result = decoupler.diagnose_hidden_effects(factor_data, controls, returns)
        assert 'incremental_endogeneity' in result
        assert 'information_loss' in result


# ============================================================
# E1-T20: 向后兼容 v3.0.0
# ============================================================

class TestBackwardCompatV300:
    """E1-T20: 不开启时 v3.0.0 行为不变"""

    def test_backward_compat_v3_0_0(self):
        # 默认 config 不开启诊断
        config = PipelineV2Config()
        assert config.enable_hidden_effect_diagnosis is False
        # 现有 fit/transform 接口签名未变 (无新参数)
        fit_sig = inspect.signature(FactorProcessingPipelineV2.fit)
        assert 'factor_data' in fit_sig.parameters
        # CompositeDecoupler fit/transform 接口未变
        comp_fit_sig = inspect.signature(CompositeDecoupler.fit)
        assert 'X' in comp_fit_sig.parameters
        # 默认 config 创建管线不报错
        pipeline = FactorProcessingPipelineV2(config)
        assert pipeline is not None


# ============================================================
# E1-T21: 两阶段分离 (必须先 fit)
# ============================================================

class TestDiagnoseRequiresFitFirst:
    """E1-T21: 未 fit 时 diagnose 返回 'model not fitted' 提示"""

    def test_diagnose_requires_fit_first(self):
        factor_data = _make_factor_data(n_periods=60, n_stocks=15)
        decoupler = CompositeDecoupler()  # 未 fit
        result = decoupler.diagnose_hidden_effects(factor_data)
        # 各诊断应含 'model not fitted' 提示
        assert 'model not fitted' in result['incremental_endogeneity']['diagnostic']
        assert 'model not fitted' in result['information_loss']['diagnostic']
        assert 'model not fitted' in result['stationarity_vs_endogeneity']['diagnostic']
        assert 'model not fitted' in result['method_sensitivity']['diagnostic']
