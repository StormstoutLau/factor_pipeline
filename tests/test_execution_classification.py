# -*- coding: utf-8 -*-
"""v3.8.0 E1 — BVC 与一字板识别（T380-19 ~ T380-26）。

红形态：``ModuleNotFoundError: backtest.execution.core.classification``。
"""
import numpy as np


def test_normal_cdf_values():
    """T380-19: Phi(0)=0.5, Phi(1.96)≈0.975（容差 1e-3）。"""
    from backtest.execution.core.classification import normal_cdf
    out = normal_cdf(np.array([0.0, 1.96]))
    assert np.isclose(out[0], 0.5, atol=1e-12)
    assert np.isclose(out[1], 0.975, atol=1e-3)


def test_normal_cdf_monotonic():
    """T380-20: Phi 严格递增。"""
    from backtest.execution.core.classification import normal_cdf
    x = np.linspace(-4.0, 4.0, 41)
    out = normal_cdf(x)
    assert np.all(np.diff(out) > 0.0)


def test_bvc_zero_return():
    """T380-21: ret==0 -> 买入占比 0.5。"""
    from backtest.execution.core.classification import BVC
    out = BVC().classify(np.zeros(5), np.ones(5), np.full(5, 0.01))
    assert np.allclose(out, 0.5)


def test_bvc_nonpositive_sigma():
    """T380-22: sigma<=0 -> 0.5，且不产生 inf/nan。"""
    from backtest.execution.core.classification import BVC
    out = BVC().classify(
        np.array([0.01, -0.01, 0.0]),
        np.ones(3), np.array([0.0, -0.02, 0.0]))
    assert np.all(np.isfinite(out))
    assert np.allclose(out, 0.5)


def test_bvc_bounds():
    """T380-23: 输出买入占比 ∈ [0, 1]。"""
    from backtest.execution.core.classification import BVC
    rng = np.random.default_rng(5)
    ret = rng.normal(0.0, 0.01, 500)
    out = BVC().classify(ret, np.ones(500), np.full(500, 0.01))
    assert np.all(out >= 0.0)
    assert np.all(out <= 1.0)


def test_rolling_sigma_no_lookahead():
    """T380-24: 扰动未来 bar，历史 sigma 逐位不变。"""
    from backtest.execution.core.classification import rolling_sigma
    rng = np.random.default_rng(9)
    ret = rng.normal(0.0, 0.01, 120)
    s1 = rolling_sigma(ret, 20)
    perturbed = ret.copy()
    perturbed[-5:] = 1.0
    s2 = rolling_sigma(perturbed, 20)
    assert np.array_equal(s1[:-5], s2[:-5], equal_nan=True)
    assert not np.allclose(s1[-5:], s2[-5:])


def test_limit_lock_high_low_equal():
    """T380-25: h==l -> 命中。"""
    from backtest.execution.core.classification import detect_limit_lock
    high = np.array([10.0, 10.0, 11.0])
    low = np.array([10.0, 10.0, 10.5])
    close = np.array([10.0, 10.0, 10.8])
    open_ = np.array([10.0, 9.9, 10.6])
    volume = np.array([100.0, 0.0, 200.0])
    out = detect_limit_lock(high, low, close, open_, volume)
    assert np.array_equal(out, np.array([True, True, False]))


def test_limit_lock_zero_volume():
    """T380-26: volume==0 且 o=c=h=l -> 命中。"""
    from backtest.execution.core.classification import detect_limit_lock
    high = np.array([10.0, 12.0])
    low = np.array([10.0, 11.0])
    close = np.array([10.0, 11.5])
    open_ = np.array([10.0, 11.2])
    volume = np.array([0.0, 50.0])
    out = detect_limit_lock(high, low, close, open_, volume)
    assert np.array_equal(out, np.array([True, False]))


def test_limit_lock_zero_volume_requires_low_equal():
    """H2（步骤 10 审计修复）：v==0 且 o=c=h 但 l<h 不命中（spec 要求 o=c=h=l）。"""
    from backtest.execution.core.classification import detect_limit_lock
    high = np.array([10.0, 10.0])
    low = np.array([9.5, 10.0])
    close = np.array([10.0, 10.0])
    open_ = np.array([10.0, 10.0])
    volume = np.array([0.0, 0.0])
    out = detect_limit_lock(high, low, close, open_, volume)
    assert not bool(out[0])  # l<h 的零量异常 bar 不命中
    assert bool(out[1]) is True  # o=c=h=l=10 且 v=0 -> 命中
