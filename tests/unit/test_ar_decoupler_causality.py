# -*- coding: utf-8 -*-
"""PL-05 ARDecoupler 因果性测试.

覆盖: 前缀估计 / 多截断点不变式 / 一步预测公式 / 冷启动 identity /
NaN 契约 / 列门控 / 参数校验 / 软混合 / 元数据.
"""
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from factor_pipeline.modules.factor_decoupler.core.ar_model import (
    AROrderSelector,
    ARDecoupler,
)


def _panel(n_periods=100, n_stocks=5, seed=7, phi=0.7):
    """AR(1) 面板 (index=日期, columns=股票)."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2020-01-31', periods=n_periods, freq='ME')
    cols = [f'S{i:03d}' for i in range(n_stocks)]
    arr = np.zeros((n_periods, n_stocks))
    arr[0] = rng.standard_normal(n_stocks)
    for t in range(1, n_periods):
        arr[t] = phi * arr[t - 1] + rng.standard_normal(n_stocks)
    return pd.DataFrame(arr, index=dates, columns=cols)


def test_fit_uses_only_prefix():
    """fit 只读前 warmup_obs 行: 改变其后数据不影响 _results."""
    df = _panel(200, 5, seed=3)
    base = ARDecoupler(max_order=3, warmup_obs=60).fit(df)
    ref = {
        c: (base._results[c].order,
            np.asarray(base._results[c].coefficients).copy())
        for c in base._results
    }

    mutated = df.copy()
    mutated.iloc[60:] += 1000.0
    other = ARDecoupler(max_order=3, warmup_obs=60).fit(mutated)

    assert set(other._results) == set(ref)
    for c, (order, coef) in ref.items():
        assert other._results[c].order == order
        np.testing.assert_allclose(
            np.asarray(other._results[c].coefficients), coef, atol=0, rtol=0)


@pytest.mark.parametrize('t', [10, 15, 25, 30, 45, 60, 80])
def test_truncation_invariant_multi_cut(t):
    """全样本输出前 t 行 == 截断面板输出 (逐元素)."""
    df = _panel(100, 10, seed=22)
    full = ARDecoupler(max_order=3, warmup_obs=40).fit_transform(df)
    trunc = ARDecoupler(max_order=3, warmup_obs=40).fit_transform(df.iloc[:t])

    a = full.to_numpy(dtype=float)[:t]
    b = trunc.to_numpy(dtype=float)
    assert np.array_equal(np.isnan(a), np.isnan(b))
    both = ~np.isnan(a) & ~np.isnan(b)
    np.testing.assert_allclose(a[both], b[both], atol=1e-12, rtol=0)


def test_one_step_prediction_matches_hand_calc():
    """冻结期输出 == series - (c0 + Σ c_i·y_{t-i}) (独立算式)."""
    df = _panel(60, 3, seed=5, phi=0.6)
    d = ARDecoupler(max_order=2, min_order=1, warmup_obs=40).fit(df)
    out = d.transform(df)

    for col in df.columns:
        res = d._results[col]
        c = np.asarray(res.coefficients).flatten()
        p = res.order
        vals = df[col].to_numpy(dtype=float)
        for t in range(40, 60):
            yhat = c[0] + sum(c[i + 1] * vals[t - 1 - i] for i in range(p))
            assert out[col].iloc[t] == pytest.approx(vals[t] - yhat, abs=1e-12)


def test_cold_start_is_identity():
    """t < min_order+6 → 输出 == 输入."""
    df = _panel(60, 4, seed=11, phi=0.5)
    out = ARDecoupler(max_order=3, min_order=1).fit_transform(df)
    early = 1 + 6
    np.testing.assert_array_equal(
        out.iloc[:early].to_numpy(dtype=float),
        df.iloc[:early].to_numpy(dtype=float))


def test_fitted_columns_add_no_nan():
    """无 NaN 输入 → 无 NaN 输出."""
    df = _panel(100, 6, seed=13, phi=0.6)
    out = ARDecoupler(max_order=3).fit_transform(df)
    assert not np.isnan(out.to_numpy(dtype=float)).any()


def test_missing_results_column_not_blanket_identity():
    """_results 缺失不代表整列 identity: 早期仍固定低阶解耦, t≥K 才 identity."""
    df = _panel(100, 3, seed=17, phi=0.0)
    rng = np.random.default_rng(99)
    col = df.columns[0]
    df.iloc[:40, 0] = np.nan
    df.iloc[3:20, 0] = rng.standard_normal(17)   # 前 40 行仅 17 个有效值

    d = ARDecoupler(max_order=1, min_order=1, min_obs=20, warmup_obs=40).fit(df)
    assert col not in d._results

    out = d.transform(df)
    t = 12
    assert out[col].iloc[t] != df[col].iloc[t]
    np.testing.assert_array_equal(
        out[col].iloc[40:].to_numpy(dtype=float),
        df[col].iloc[40:].to_numpy(dtype=float))


def test_warmup_must_exceed_min_obs():
    with pytest.raises(ValueError, match='warmup_obs'):
        ARDecoupler(min_obs=20, warmup_obs=20)


def test_strength_soft_mix():
    """out(s) == (1-s)·series + s·out(1.0)."""
    df = _panel(80, 3, seed=21, phi=0.6)
    out_full = ARDecoupler(max_order=2, strength=1.0).fit_transform(df)
    out_half = ARDecoupler(max_order=2, strength=0.5).fit_transform(df)
    expected = 0.5 * df.to_numpy(dtype=float) + 0.5 * out_full.to_numpy(dtype=float)
    np.testing.assert_allclose(
        out_half.to_numpy(dtype=float), expected, atol=1e-12, rtol=0)


def test_warmup_refit_uses_only_prefix():
    """所有拟合调用的样本长度 <= warmup_obs, 且存在短前缀调用."""
    df = _panel(80, 3, seed=23, phi=0.6)
    lengths = []
    orig_fit_ar = AROrderSelector._fit_ar

    def spy(self, series, order):
        lengths.append(len(series.dropna()))
        return orig_fit_ar(self, series, order)

    with patch.object(AROrderSelector, '_fit_ar', spy):
        ARDecoupler(max_order=3, warmup_obs=40).fit_transform(df)

    assert lengths, "未发生任何拟合"
    assert max(lengths) <= 40, f"拟合窗口超过 warmup_obs: {max(lengths)}"
    assert min(lengths) < 40, "warm-up 未使用短前缀, 无法证明逐步扩展"


def test_metadata_preserved():
    df = _panel(80, 3, seed=25)
    out = ARDecoupler(max_order=2, warmup_obs=40).fit_transform(df)
    assert out.index.equals(df.index)
    assert out.columns.equals(df.columns)
