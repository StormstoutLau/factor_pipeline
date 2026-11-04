# -*- coding: utf-8 -*-
"""PL-06: Mixed 缩尾逐日截面 3σ — TDD 测试.

契约:
- fit 不保存跨期参数 (`_winsorize_params is None`)
- 边界只由当日行计算: mu = X.mean(axis=1), sd = X.std(axis=1, ddof=1)
- 输出保留 index/columns/NaN; 单有效观测/零离散度/全 NaN 行原样返回
- N<=10 的 3σ 永不触发; N=11 起可触发
- 截断不变式: 全样本前 t 期输出 == [0,t] 独立跑出的输出
"""
import numpy as np
import pandas as pd

from factor_pipeline.pipelines_v2 import MixedFactorPipeline


def _panel(n_periods=60, n_stocks=30, seed=7):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.lognormal(mean=0.0, sigma=1.0, size=(n_periods, n_stocks)),
        index=pd.date_range('2020-01-31', periods=n_periods, freq='ME'),
        columns=[f'S{i:03d}' for i in range(n_stocks)],
    )


def _industry(n_stocks=30, n_industries=4):
    stocks = [f'S{i:03d}' for i in range(n_stocks)]
    labels = [f'IND_{i % n_industries}' for i in range(n_stocks)]
    return pd.Series(labels, index=stocks, name='industry')


def _pipe(sigma=3.0, module_enabled=None, with_industry=True):
    kwargs = {}
    if with_industry:
        kwargs['neutralizer_params'] = {'industry_data': _industry()}
    return MixedFactorPipeline(
        mixed_winsor_sigma=sigma,
        module_enabled=module_enabled,
        **kwargs,
    )


def _changed_cells(a: pd.DataFrame, b: pd.DataFrame) -> int:
    va = a.to_numpy(dtype=float)
    vb = b.to_numpy(dtype=float)
    with np.errstate(invalid='ignore'):
        diff = np.abs(va - vb)
    return int(np.sum(np.isfinite(diff) & (diff > 1e-12)))


# =============================================================================
# 公共用例
# =============================================================================

def test_fit_does_not_store_cross_period_params():
    X = _panel(n_periods=60, n_stocks=30, seed=7)
    pipe = _pipe()
    pipe.fit(X)
    assert pipe._winsorize_params is None


def test_truncation_invariant_on_synthetic_panel():
    X = _panel(n_periods=60, n_stocks=30, seed=11)
    t = 36
    out_full = _pipe().fit_transform(X)
    out_trunc = _pipe().fit_transform(X.iloc[:t])
    pd.testing.assert_frame_equal(
        out_full.iloc[:t], out_trunc, atol=1e-12, rtol=0,
    )


def test_future_value_does_not_change_past_rows():
    X = _panel(n_periods=20, n_stocks=30, seed=13)
    X2 = X.copy()
    X2.iloc[-1] = X2.iloc[-1] * 100.0
    pipe = _pipe(with_industry=False)
    out1 = pipe._apply_winsorize(X)
    out2 = pipe._apply_winsorize(X2)
    pd.testing.assert_frame_equal(
        out1.iloc[:-1], out2.iloc[:-1], atol=1e-12, rtol=0,
    )


def test_nan_rows_unchanged():
    idx = pd.date_range('2020-01-31', periods=3, freq='ME')
    cols = [f'S{i:03d}' for i in range(10)]
    X = pd.DataFrame(np.nan, index=idx, columns=cols)
    X.iloc[1, 0] = 5.0          # N=1
    X.iloc[2, :] = 1.0          # 零离散度
    pipe = _pipe(with_industry=False)
    out = pipe._apply_winsorize(X)
    pd.testing.assert_frame_equal(out, X, atol=1e-12, rtol=0)


def test_no_new_nan():
    X = _panel(n_periods=10, n_stocks=30, seed=17)
    X.iloc[2, 3] = np.nan
    X.iloc[5, :] = np.nan
    pipe = _pipe(with_industry=False)
    out = pipe._apply_winsorize(X)
    np.testing.assert_array_equal(
        out.isna().to_numpy(), X.isna().to_numpy(),
    )


def test_winsorizer_disabled_skips_clip():
    X = _panel(n_periods=60, n_stocks=30, seed=19)
    pipe = _pipe(module_enabled={'winsorizer': False})
    pipe.fit_transform(X)
    pd.testing.assert_frame_equal(
        pipe._intermediate_data['outlier'],
        pipe._intermediate_data['imputation'],
        atol=1e-12, rtol=0,
    )


def test_metadata_preserved():
    X = _panel(n_periods=10, n_stocks=30, seed=23)
    pipe = _pipe(with_industry=False)
    out = pipe._apply_winsorize(X)
    assert out.index.equals(X.index)
    assert out.columns.equals(X.columns)


# =============================================================================
# A 专属
# =============================================================================

def test_sigma_monotonicity():
    X = _panel(n_periods=20, n_stocks=30, seed=29)
    counts = []
    for sigma in (2.0, 3.0, 4.0):
        pipe = _pipe(sigma=sigma, with_industry=False)
        out = pipe._apply_winsorize(X)
        counts.append(_changed_cells(out, X))
    assert counts[0] >= counts[1] >= counts[2], counts


def test_n_le_10_is_noop():
    idx = pd.date_range('2020-01-31', periods=3, freq='ME')
    cols = [f'S{i:03d}' for i in range(10)]
    X = pd.DataFrame(np.nan, index=idx, columns=cols)
    X.iloc[0, :2] = [0.0, 100.0]                 # N=2
    X.iloc[1, :5] = [0.0, 0.0, 0.0, 0.0, 100.0]  # N=5
    X.iloc[2, :] = [0.0] * 9 + [100.0]           # N=10
    pipe = _pipe(with_industry=False)
    out = pipe._apply_winsorize(X)
    pd.testing.assert_frame_equal(out, X, atol=1e-12, rtol=0)


def test_bounds_are_row_mean_plus_minus_sigma_std():
    X = _panel(n_periods=15, n_stocks=30, seed=31)
    pipe = _pipe(sigma=3.0, with_industry=False)
    out = pipe._apply_winsorize(X)
    # 独立路径 (numpy) 重建边界, 避免用 pandas 同表达式自证
    arr = X.to_numpy(dtype=float)
    mu = np.nanmean(arr, axis=1)
    sd = np.nanstd(arr, axis=1, ddof=1)
    expected = np.clip(arr,
                       (mu - 3.0 * sd)[:, None],
                       (mu + 3.0 * sd)[:, None])
    pd.testing.assert_frame_equal(
        out, pd.DataFrame(expected, index=X.index, columns=X.columns),
        atol=1e-12, rtol=0,
    )


def test_n11_can_clip():
    idx = pd.date_range('2020-01-31', periods=1, freq='ME')
    cols = [f'S{i:03d}' for i in range(11)]
    X = pd.DataFrame([[0.0] * 10 + [100.0]], index=idx, columns=cols)
    pipe = _pipe(with_industry=False)
    out = pipe._apply_winsorize(X)
    assert not np.allclose(
        out.to_numpy(dtype=float), X.to_numpy(dtype=float),
        atol=1e-12, rtol=0,
    )
