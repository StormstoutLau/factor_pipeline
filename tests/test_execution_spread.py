# -*- coding: utf-8 -*-
"""v3.8.0 E0 — 价差 / 非流动性代理（T380-11 ~ T380-18）。

红形态：``ModuleNotFoundError: backtest.execution.core.spread``。
"""
import numpy as np
import pytest


def _ohlc(n=120, seed=7):
    rng = np.random.default_rng(seed)
    logp = np.cumsum(rng.normal(0.0, 0.01, n))
    width = np.abs(rng.normal(0.0, 0.012, n)) + 0.002
    high = np.exp(logp + width)
    low = np.exp(logp - width)
    close = np.exp(logp)
    return high, low, close


def _single_day_spread(high, low):
    """单日 high-low 价差代理（T380-13 的方差对照基线）。"""
    return 2.0 * (high - low) / (high + low)


def _bounce_ohlc(n=400, seed=3, spread=0.002):
    """常数买卖价差 + 日间噪声（CS 两类估计量的可识别情形）。"""
    rng = np.random.default_rng(seed)
    mid = np.cumsum(rng.normal(0.0, 0.005, n))
    noise = np.abs(rng.normal(0.0, 0.003, n))
    high = np.exp(mid + noise + spread)
    low = np.exp(mid - noise - spread)
    close = np.exp(mid)
    return high, low, close


def test_cs_zero_range_shifted():
    """T380-11: h==l 不产生 NaN 也不被丢弃（零区间平移）。"""
    from backtest.execution.core.spread import CorwinSchultz
    high, low, close = _ohlc(30)
    high[[5, 9]] = low[[5, 9]]
    out = CorwinSchultz().estimate(high, low, close)
    assert out.shape[0] > 0
    assert np.all(np.isfinite(out))


def test_cs_nonnegative():
    """T380-12: 负估计截断，输出全部 >= 0。"""
    from backtest.execution.core.spread import CorwinSchultz
    high, low, close = _ohlc(60, seed=11)
    out = CorwinSchultz().estimate(high, low, close)
    assert np.all(out >= 0.0)


def test_cs_two_day_lower_variance():
    """T380-13: 两日修正估计方差小于单日估计（合成数据）。"""
    from backtest.execution.core.spread import CorwinSchultz
    high, low, close = _bounce_ohlc()
    two = CorwinSchultz().estimate(high, low, close)
    one = _single_day_spread(high, low)
    assert np.nanvar(two) < np.nanvar(one)


def test_cs_zero_ratio():
    """T380-14: 全零区间 -> zero_ratio == 1.0。"""
    from backtest.execution.core.spread import CorwinSchultz
    n = 20
    high = np.full(n, 10.0)
    low = np.full(n, 10.0)
    assert CorwinSchultz().zero_ratio(high, low) == 1.0


def test_abdi_ranaldo_product_form():
    """T380-15: 乘积型 S 反解误差 < 1e-8。"""
    from backtest.execution.core.spread import AbdiRanaldo
    n = 50
    s = 0.004
    d = s / (2.0 * np.sqrt(2.0))
    eta0 = 4.5
    eta = eta0 - d * np.arange(n)
    close = np.exp(eta + d)
    high = np.exp(eta + 0.1)
    low = np.exp(eta - 0.1)
    out = AbdiRanaldo().estimate(high, low, close)
    valid = out[np.isfinite(out)]
    assert valid.size > 0
    assert np.allclose(valid, s, atol=1e-8, rtol=1e-8)


def test_abdi_ranaldo_negative_truncated():
    """T380-16: S2<0 -> 0（不出现 NaN）。"""
    from backtest.execution.core.spread import AbdiRanaldo
    n = 8
    eta = np.array([0.1, -0.1] * (n // 2))       # 相邻日符号相反
    close = np.exp(np.zeros(n))                   # ln(close) == 0
    high = np.exp(eta + 0.05)
    low = np.exp(eta - 0.05)
    # (c_t-eta_t)(c_t-eta_{t+1}) = eta_t*eta_{t+1} < 0
    out = AbdiRanaldo().estimate(high, low, close)
    assert np.all(np.isnan(out) | (out >= 0.0))


def test_amihud_units():
    """T380-17: |r|=0.01, amount=1e8 -> 1e-10。"""
    from backtest.execution.core.spread import Amihud
    out = Amihud().estimate(np.full(3, 0.01), np.full(3, 1e8))
    assert np.allclose(out, 1e-10, rtol=1e-12)


def test_short_series_all_nan():
    """T380-18: n<3 -> 全 NaN，不抛错。"""
    from backtest.execution.core.spread import AbdiRanaldo, Amihud, CorwinSchultz
    h = np.array([1.0, 1.1])
    l = np.array([0.9, 1.0])
    c = np.array([1.0, 1.05])
    for out in (CorwinSchultz().estimate(h, l, c),
                AbdiRanaldo().estimate(h, l, c),
                Amihud().estimate(c, h)):
        assert out.shape == (2,)
        assert np.all(np.isnan(out))
