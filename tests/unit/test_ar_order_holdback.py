# -*- coding: utf-8 -*-
"""PL-08 / ADR-041: AR 阶数选择 hold_back 可比性测试.

覆盖: 有效样本一致 / statsmodels 语义对齐 / 守卫边界 / 索引契约 /
AR(1)-AR(3) 选阶恢复 / 固定阶数 fit 等价 / warm-up 无退化 /
早期截断不变式.
"""
import warnings

import numpy as np
import pandas as pd
import pytest
from statsmodels.tsa.ar_model import AutoReg

from factor_pipeline.modules.factor_decoupler.core.ar_model import (
    ARDecoupler,
    AROrderSelector,
)


def _ar_panel(n_periods, n_stocks, seed, phis):
    """AR(p) 面板; phis = [phi_1, ..., phi_p]."""
    rng = np.random.default_rng(seed)
    p = len(phis)
    arr = np.zeros((n_periods, n_stocks))
    for t in range(p):
        arr[t] = rng.standard_normal(n_stocks)
    for t in range(p, n_periods):
        arr[t] = sum(phis[i] * arr[t - 1 - i] for i in range(p)) \
            + rng.standard_normal(n_stocks)
    return pd.DataFrame(
        arr, index=pd.date_range('2020-01-31', periods=n_periods, freq='ME'),
        columns=[f'S{i:03d}' for i in range(n_stocks)],
    )


def _series(n, seed, phi=0.7):
    rng = np.random.default_rng(seed)
    y = np.zeros(n)
    y[0] = rng.standard_normal()
    for t in range(1, n):
        y[t] = phi * y[t - 1] + rng.standard_normal()
    return pd.Series(y, index=pd.date_range('2020-01-31', periods=n, freq='ME'))


def test_common_effective_sample():
    """T1: 所有阶数的估计样本长度相同 = n - max_order."""
    s = _series(100, 22)
    sel = AROrderSelector(max_order=5)
    lengths = {p: len(sel._fit_ar(s, p).residuals) for p in range(1, 6)}
    assert set(lengths.values()) == {95}, lengths


@pytest.mark.parametrize('p', [1, 2, 3, 4, 5])
def test_matches_statsmodels_hold_back(p):
    """T2: 系数 / llf / sigma2 / n_obs 与 AutoReg(hold_back=H) 一致."""
    s = _series(100, 22)
    sel = AROrderSelector(max_order=5)
    r = sel._fit_ar(s, p)
    m = AutoReg(s.values, lags=p, hold_back=5, trend='c').fit()

    np.testing.assert_allclose(r.coefficients, m.params, atol=1e-10, rtol=0)
    assert r.log_likelihood == pytest.approx(m.llf, abs=1e-10)
    assert r.sigma2 == pytest.approx(m.sigma2, abs=1e-10)
    assert len(r.residuals) == int(m.nobs)
    assert r.aic - m.aic == pytest.approx(-2.0, abs=1e-10)


@pytest.mark.parametrize('order', [1, 3, 5])
def test_guard_rejects_insufficient_effective_sample(order):
    """T3: n_obs = order+5 抛错; order+6 通过."""
    H = 5
    sel = AROrderSelector(max_order=5)
    with pytest.raises(ValueError, match='有效样本不足'):
        sel._fit_ar(_series(H + order + 5, 3), order)
    r = sel._fit_ar(_series(H + order + 6, 3), order)
    assert len(r.residuals) == order + 6


def test_residual_index_starts_at_hold_back():
    """T4: residuals / fitted_values 索引从 H 开始."""
    s = _series(100, 22)
    sel = AROrderSelector(max_order=5)
    r = sel._fit_ar(s, 3)

    assert r.residuals.index[0] == s.index[5]
    assert r.fitted_values.index[0] == s.index[5]
    assert len(r.residuals) == len(s) - 5
    assert len(r.fitted_values) == len(s) - 5


def test_order_selection_low_on_ar1():
    """T5: AR(1) 真值面板选阶均值 <= 2.0."""
    df = _ar_panel(100, 30, 22, [0.7])
    res = AROrderSelector(max_order=5).batch_fit(df)
    orders = np.array([r.order for r in res.values()])
    assert len(res) == 30
    assert orders.mean() <= 2.0


def test_order_selection_recovers_ar2():
    """T6: AR(2) 真值面板选阶均值 ∈ [1.8, 3.2]."""
    df = _ar_panel(120, 30, 11, [0.6, 0.3])
    res = AROrderSelector(max_order=5).batch_fit(df)
    orders = np.array([r.order for r in res.values()])
    assert 1.8 <= orders.mean() <= 3.2


def test_order_selection_recovers_ar3():
    """T7: AR(3) 真值面板选阶均值 ∈ [2.4, 3.8]."""
    df = _ar_panel(120, 30, 5, [0.5, 0.3, 0.2])
    res = AROrderSelector(max_order=5).batch_fit(df)
    orders = np.array([r.order for r in res.values()])
    assert 2.4 <= orders.mean() <= 3.8


@pytest.mark.parametrize('p', [1, 2, 3])
def test_fixed_order_fit_matches_current_formula(p):
    """T8: 固定阶数时 hold_back=p 与旧公式 y[p:] 逐值相同."""
    s = _series(100, 11)
    fit_s = s.iloc[:40]                     # fit 只用前 warmup_obs=40 行
    d = ARDecoupler(max_order=p, min_order=p, warmup_obs=40).fit(
        fit_s.to_frame('S'))
    r = d._results['S']

    y = fit_s.values
    X = np.column_stack([y[p - i:len(y) - i] for i in range(1, p + 1)])
    X = np.column_stack([np.ones(len(y) - p), X])
    beta = np.linalg.lstsq(X, y[p:], rcond=None)[0]

    np.testing.assert_allclose(r.coefficients, beta, atol=0, rtol=0)


def test_no_zero_variance_fit_in_warmup():
    """T9: warm-up 早期无 sigma2=0 / ln(0); t<12 保持 identity."""
    df = _ar_panel(80, 3, 5, [0.7])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        out = ARDecoupler(max_order=5, warmup_obs=40).fit_transform(df)

    bad = [w for w in caught
           if 'divide by zero' in str(w.message)
           or 'invalid value' in str(w.message)]
    assert not bad, [str(w.message) for w in bad]
    assert np.isfinite(out.to_numpy(dtype=float)).all()
    np.testing.assert_array_equal(
        out.iloc[:12].to_numpy(dtype=float),
        df.iloc[:12].to_numpy(dtype=float),
    )


@pytest.mark.parametrize('t', [7, 8, 9, 10, 12])
def test_warmup_early_truncation_invariant(t):
    """T10: 早期截断点仍满足前缀不变式."""
    df = _ar_panel(100, 10, 22, [0.7])
    full = ARDecoupler(max_order=3, warmup_obs=40).fit_transform(df)
    trunc = ARDecoupler(max_order=3, warmup_obs=40).fit_transform(df.iloc[:t])

    a = full.to_numpy(dtype=float)[:t]
    b = trunc.to_numpy(dtype=float)
    assert np.array_equal(np.isnan(a), np.isnan(b))
    both = ~np.isnan(a) & ~np.isnan(b)
    np.testing.assert_allclose(a[both], b[both], atol=1e-12, rtol=0)
