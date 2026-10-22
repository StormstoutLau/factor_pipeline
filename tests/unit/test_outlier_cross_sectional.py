# -*- coding: utf-8 -*-
"""PL-01: ProcessingAdapter 去极值逐日横截面 — TDD 测试.

契约:
- `method='auto'` 解析为 percentile; 显式方法按声明执行
- `fit()` 不存参数; `transform()` 只用当日横截面
- 截断不变式: 全样本前 t 期输出 == [0,t] 独立跑出的输出
- NaN 模式 / index / columns 保持不变
"""
import warnings

import numpy as np
import pandas as pd
import pytest

from factor_pipeline.adapters import ProcessingAdapter


METHODS = [
    'percentile', 'quantile', 'z_score', 'mad', 'iqr', 'adaptive', 'sigmoid_soft',
]


def _panel(T=40, N=10, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.standard_normal((T, N)),
        index=pd.date_range('2020-01-01', periods=T, freq='D'),
        columns=[f's{i}' for i in range(N)],
    )


def _split(df, frac=0.6):
    t = int(len(df) * frac)
    return df, df.iloc[:t], t


def _run_pair(factory, df):
    full, trunc, t = _split(df)
    a = factory()
    a.fit(full)
    out_full = a.transform(full)
    b = factory()
    b.fit(trunc)
    out_trunc = b.transform(trunc)
    return out_full.iloc[:t], out_trunc


def _assert_values_equal(left, right):
    np.testing.assert_allclose(
        left.values, right.values, atol=1e-12, rtol=0, equal_nan=True,
    )
    assert left.index.equals(right.index)
    assert left.columns.equals(right.columns)


def _outlier(method='percentile', **kwargs):
    return ProcessingAdapter(
        process_type='outlier', method=method,
        percentile_lower=1.0, percentile_upper=99.0, **kwargs,
    )


# =============================================================================
# 1. 方法解析
# =============================================================================

class TestMethodResolution:
    def test_auto_resolves_to_percentile(self):
        adapter = _outlier(method='auto')
        assert adapter.method == 'percentile'
        assert adapter.requested_method == 'auto'
        assert adapter._cross_sectional_outlier is True

    @pytest.mark.parametrize('method', METHODS)
    def test_explicit_method_preserved(self, method):
        adapter = _outlier(method=method)
        assert adapter.method == method
        assert adapter.requested_method == method

    def test_invalid_method_raises(self):
        with pytest.raises(ValueError, match='未知 method'):
            _outlier(method='not_a_method')

    @pytest.mark.parametrize('lo,hi', [(99.0, 1.0), (-1.0, 99.0), (1.0, 101.0)])
    def test_invalid_percentiles_raise(self, lo, hi):
        with pytest.raises(ValueError):
            ProcessingAdapter(
                process_type='outlier', method='percentile',
                percentile_lower=lo, percentile_upper=hi,
            )

    def test_decimal_percentile_convention_rejected(self):
        with pytest.raises(ValueError, match='0-1'):
            ProcessingAdapter(
                process_type='outlier', method='percentile',
                percentile_lower=0.01, percentile_upper=0.99,
            )


# =============================================================================
# 2. 因果性 / 截断不变式
# =============================================================================

class TestCausality:
    def test_percentile_bounds_match_manual(self):
        df = _panel(T=5, N=8, seed=1)
        out = _outlier().fit_transform(df)

        lo = np.percentile(df.values, 1, axis=1)
        hi = np.percentile(df.values, 99, axis=1)
        expected = np.clip(df.values, lo[:, None], hi[:, None])
        np.testing.assert_allclose(out.values, expected, atol=1e-12, rtol=0)

    def test_percentile_is_truncation_invariant(self):
        df = _panel(T=60, N=10, seed=2)
        out_full, out_trunc = _run_pair(lambda: _outlier(), df)
        _assert_values_equal(out_full, out_trunc)

    def test_mad_is_truncation_invariant(self):
        df = _panel(T=60, N=12, seed=3)
        out_full, out_trunc = _run_pair(lambda: _outlier(method='mad'), df)
        _assert_values_equal(out_full, out_trunc)

    @pytest.mark.parametrize('method', METHODS)
    def test_all_methods_are_truncation_invariant(self, method):
        df = _panel(T=40, N=12, seed=4)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            out_full, out_trunc = _run_pair(
                lambda: _outlier(method=method), df)
        _assert_values_equal(out_full, out_trunc)

    def test_fit_stores_no_parameters(self):
        adapter = _outlier()
        adapter.fit(_panel())
        assert adapter._processor is None
        assert adapter._column_processors == {}
        assert adapter.is_fitted is True


# =============================================================================
# 3. 边界 / 元数据
# =============================================================================

class TestEdgeCases:
    def test_preserves_nan_and_metadata(self):
        df = _panel(T=20, N=6, seed=5)
        df.iloc[0, 0] = np.nan
        df.iloc[5, :] = np.nan
        df.iloc[7, 1:] = np.nan

        out = _outlier().fit_transform(df)

        assert out.isna().equals(df.isna())
        assert out.index.equals(df.index)
        assert out.columns.equals(df.columns)

    def test_small_rows_unchanged(self):
        df = pd.DataFrame(
            {'A': [1.0], 'B': [2.0]},
            index=pd.date_range('2020-01-01', periods=1),
        )
        out = _outlier().fit_transform(df)
        pd.testing.assert_frame_equal(out, df)

    def test_zero_dispersion_row_unchanged(self):
        df = pd.DataFrame(
            np.ones((5, 4)),
            index=pd.date_range('2020-01-01', periods=5),
            columns=list('ABCD'),
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            out = _outlier(method='mad').fit_transform(df)

        runtime = [w for w in caught if issubclass(w.category, RuntimeWarning)]
        assert runtime == []
        pd.testing.assert_frame_equal(out, df)

    def test_enabled_false_is_identity(self):
        df = _panel()
        adapter = _outlier(method='auto', enabled=False)
        out = adapter.fit_transform(df)

        pd.testing.assert_frame_equal(out, df)
        assert adapter._processor is None
        assert adapter._processor_class is None

    def test_non_dataframe_raises(self):
        adapter = _outlier()
        with pytest.raises(TypeError):
            adapter.fit(pd.Series([1.0, 2.0, 3.0]))

        adapter.fit(_panel(T=10, N=5, seed=6))
        with pytest.raises(TypeError):
            adapter.transform(pd.Series([1.0, 2.0, 3.0]))

    def test_get_stats(self):
        adapter = _outlier(method='auto')
        stats = adapter.get_stats()

        assert stats['method'] == 'percentile'
        assert stats['requested_method'] == 'auto'
        assert stats['outlier_scope'] == 'cross_sectional'
        assert stats['percentile_lower'] == 1.0
        assert stats['percentile_upper'] == 99.0
