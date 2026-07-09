# -*- coding: utf-8 -*-
"""V3.1.0 E4 — 格兰杰检验 (Toda-Yamamoto 1995) 测试 (TDD Red 阶段).

Toda-Yamamoto 方法:
1. ADF 检验确定最高单整阶数 d
2. 估计 VAR(p+d) 模型
3. 对前 p 阶做 Wald 检验 (H0: 因子不 Granger-cause 收益)
4. Wald 统计量 ~ χ²(p)
5. contemporaneous_causality='unidentified' (诚实承认同期因果不可识别)

定位: "伪回归初筛过滤器", 非因果证明工具.
"""
import pytest
import numpy as np
import pandas as pd

from factor_pipeline.backtest.granger_attribution import TodaYamamotoGrangerTester
from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2, PipelineV2Config


# ============================================================
# 测试数据生成工具
# ============================================================

def _make_granger_series(n=300, seed=0, lag=1, beta=0.5, noise=0.5):
    """生成 (factor, return) 时序, return 依赖 factor 的 lag 阶滞后."""
    rng = np.random.default_rng(seed)
    f = rng.standard_normal(n)
    r = np.empty(n)
    r[:lag] = rng.standard_normal(lag)
    for t in range(lag, n):
        r[t] = beta * f[t - lag] + noise * rng.standard_normal()
    return pd.Series(f, name='factor'), pd.Series(r, name='return')


def _make_independent_series(n=300, seed=1, noise=0.5):
    """生成无时序关系的 (factor, return)."""
    rng = np.random.default_rng(seed)
    f = rng.standard_normal(n)
    r = rng.standard_normal(n) * noise
    return pd.Series(f, name='factor'), pd.Series(r, name='return')


def _make_random_walk(n=300, seed=2):
    """生成单位根序列 (随机游走)."""
    rng = np.random.default_rng(seed)
    steps = rng.standard_normal(n)
    s = np.cumsum(steps)
    return pd.Series(s, name='series')


def _make_stationary(n=300, seed=3):
    """生成平稳序列."""
    rng = np.random.default_rng(seed)
    return pd.Series(rng.standard_normal(n), name='series')


# ============================================================
# ADF 单整阶数检验 (E4-T01 ~ T02)
# ============================================================

class TestADFIntegrationOrder:
    """ADF 检验确定单整阶数 d."""

    def test_E4_T01_adf_stationary(self):
        """E4-T01: 平稳序列 → d=0."""
        tester = TodaYamamotoGrangerTester()
        s = _make_stationary(n=200, seed=11)
        d = tester._determine_integration_order(s, max_d=2)
        assert d == 0

    def test_E4_T02_adf_unit_root(self):
        """E4-T02: 单位根序列 → d=1."""
        tester = TodaYamamotoGrangerTester()
        s = _make_random_walk(n=300, seed=12)
        d = tester._determine_integration_order(s, max_d=2)
        assert d >= 1


# ============================================================
# VAR 滞后阶选择 (E4-T03)
# ============================================================

class TestVARLagSelection:
    """VAR(p) AIC 滞后阶选择."""

    def test_E4_T03_var_lag_selection_aic(self):
        """E4-T03: AIC 选择滞后阶 p."""
        f, r = _make_granger_series(n=200, seed=21, lag=2, beta=0.6)
        tester = TodaYamamotoGrangerTester(max_lag=8)
        tester.fit(f, r)
        diag = tester.get_diagnostics()
        assert 'selected_lag' in diag
        assert diag['selected_lag'] >= 1


# ============================================================
# Wald 检验 (E4-T04 ~ T06)
# ============================================================

class TestWaldCausality:
    """Wald 检验 F→R / R→F."""

    def test_E4_T04_wald_significant(self):
        """E4-T04: 因子先于收益 → F Granger-cause R 显著."""
        # 强滞后关系: r[t] = 0.7 * f[t-1] + noise
        f, r = _make_granger_series(n=300, seed=31, lag=1, beta=0.7, noise=0.3)
        tester = TodaYamamotoGrangerTester(max_lag=6, significance_level=0.05)
        tester.fit(f, r)
        diag = tester.get_diagnostics()
        assert diag['f_granger_cause_r'] is True

    def test_E4_T05_wald_not_significant(self):
        """E4-T05: 无时序关系 → 不显著."""
        f, r = _make_independent_series(n=300, seed=32, noise=0.5)
        tester = TodaYamamotoGrangerTester(max_lag=6, significance_level=0.05)
        tester.fit(f, r)
        diag = tester.get_diagnostics()
        assert diag['f_granger_cause_r'] is False

    def test_E4_T06_bidirectional_granger(self):
        """E4-T06: 双向反馈 → F→R 和 R→F 都显著."""
        rng = np.random.default_rng(33)
        n = 400
        f = np.empty(n)
        r = np.empty(n)
        f[0] = rng.standard_normal()
        r[0] = rng.standard_normal()
        # 双向: f[t] 依赖 r[t-1], r[t] 依赖 f[t-1]
        for t in range(1, n):
            f[t] = 0.6 * r[t - 1] + 0.3 * rng.standard_normal()
            r[t] = 0.6 * f[t - 1] + 0.3 * rng.standard_normal()
        f_s = pd.Series(f, name='factor')
        r_s = pd.Series(r, name='return')
        tester = TodaYamamotoGrangerTester(max_lag=6, significance_level=0.05)
        tester.fit(f_s, r_s)
        diag = tester.get_diagnostics()
        assert diag['f_granger_cause_r'] is True
        assert diag['r_granger_cause_f'] is True


# ============================================================
# 同期因果 (E4-T07)
# ============================================================

class TestContemporaneousCausality:
    """同期因果不可识别 (诚实标记)."""

    def test_E4_T07_contemporaneous_unidentified(self):
        """E4-T07: 同期因果 → 'unidentified'."""
        f, r = _make_granger_series(n=200, seed=41, lag=1, beta=0.5)
        tester = TodaYamamotoGrangerTester()
        tester.fit(f, r)
        diag = tester.get_diagnostics()
        assert diag['contemporaneous_causality'] == 'unidentified'


# ============================================================
# Bootstrap (E4-T08 ~ T09)
# ============================================================

class TestBootstrap:
    """Block bootstrap 显著性检验."""

    def test_E4_T08_bootstrap_pvalue(self):
        """E4-T08: Bootstrap p 值 ∈ [0, 1]."""
        f, r = _make_granger_series(n=200, seed=51, lag=1, beta=0.5)
        tester = TodaYamamotoGrangerTester(
            max_lag=4, use_bootstrap=True, bootstrap_samples=50,
        )
        tester.fit(f, r)
        diag = tester.get_diagnostics()
        boot = diag['bootstrap_result']
        assert boot is not None
        if not np.isnan(boot['bootstrap_pvalue']):
            assert 0.0 <= boot['bootstrap_pvalue'] <= 1.0

    def test_E4_T09_bootstrap_block_structure(self):
        """E4-T09: Block bootstrap 保持时序结构 (n_valid > 0)."""
        f, r = _make_granger_series(n=200, seed=52, lag=1, beta=0.5)
        tester = TodaYamamotoGrangerTester(
            max_lag=4, use_bootstrap=True, bootstrap_samples=30,
        )
        tester.fit(f, r)
        diag = tester.get_diagnostics()
        boot = diag['bootstrap_result']
        assert boot is not None
        assert boot['n_valid'] > 0


# ============================================================
# Pipeline 集成 (E4-T10 ~ T14)
# ============================================================

class TestPipelineIntegration:
    """FactorProcessingPipelineV2.check_granger_causality 集成."""

    def test_E4_T10_pipeline_check_disabled(self):
        """E4-T10: enable_granger_attribution=False → 返回 None."""
        config = PipelineV2Config()
        assert config.enable_granger_attribution is False
        pipeline = FactorProcessingPipelineV2(config)
        f, r = _make_granger_series(n=200, seed=61, lag=1, beta=0.5)
        result = pipeline.check_granger_causality(f, r)
        assert result is None

    def test_E4_T11_pipeline_check_enabled(self):
        """E4-T11: enable_granger_attribution=True → 返回诊断 dict."""
        config = PipelineV2Config(enable_granger_attribution=True)
        pipeline = FactorProcessingPipelineV2(config)
        f, r = _make_granger_series(n=200, seed=62, lag=1, beta=0.5)
        result = pipeline.check_granger_causality(f, r)
        assert result is not None
        assert isinstance(result, dict)

    def test_E4_T12_short_series_guard(self):
        """E4-T12: T<20 → 降级处理 (不崩溃)."""
        config = PipelineV2Config(enable_granger_attribution=True)
        pipeline = FactorProcessingPipelineV2(config)
        rng = np.random.default_rng(63)
        f = pd.Series(rng.standard_normal(15), name='factor')
        r = pd.Series(rng.standard_normal(15), name='return')
        # 不崩溃即可
        result = pipeline.check_granger_causality(f, r)
        # 短序列可能返回 None 或降级 dict, 关键是不抛异常
        assert result is None or isinstance(result, dict)

    def test_E4_T13_nan_handling(self):
        """E4-T13: 含 NaN 不崩溃."""
        config = PipelineV2Config(enable_granger_attribution=True)
        pipeline = FactorProcessingPipelineV2(config)
        rng = np.random.default_rng(64)
        f = pd.Series(rng.standard_normal(200), name='factor')
        r = pd.Series(rng.standard_normal(200), name='return')
        f.iloc[10:15] = np.nan
        r.iloc[20:25] = np.nan
        result = pipeline.check_granger_causality(f, r)
        assert result is None or isinstance(result, dict)

    def test_E4_T14_backward_compat_v3_0_0(self):
        """E4-T14: 不开启时 v3.0.0 配置字段保持默认 (向后兼容)."""
        config = PipelineV2Config()
        assert config.enable_granger_attribution is False
        assert config.granger_max_lag == 12
        assert config.granger_use_toda_yamamoto is True
        assert config.granger_use_bootstrap is False
        # 可实例化 (零回归)
        pipeline = FactorProcessingPipelineV2(config)
        assert pipeline is not None
