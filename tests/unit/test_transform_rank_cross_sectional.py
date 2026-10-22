# -*- coding: utf-8 -*-
"""PL-02: ProcessingAdapter 变换逐日截面 rank — TDD 测试.

契约:
- `method='auto'` 解析为 `rank`; 别名 `none/box_cox/yeo_johnson/quantile` 映射到实现名
- `fit()` 无状态; `transform()` 逐日截面 rank → 目标分布
- 截断不变式: 全样本前 t 期输出 == [0,t] 独立跑出的输出
- NaN 模式 / index / columns 保持不变
- `N<10` 回落截面 z-score; `N<2` 原样返回
"""
import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm, rankdata

from factor_pipeline.adapters import (
    ProcessingAdapter,
    _MIN_RANK_CROSS_SECTION_OBS,
    _TRANSFORMATION_ALIASES as ADAPTER_ALIASES,
    _TRANSFORMATION_METHODS as ADAPTER_METHODS,
)
from factor_pipeline.modules.factor_adaptive_winsor.core.transformers import (
    AdaptiveTransformer,
    TRANSFORMATION_METHOD_ALIASES as TRANSFORMATION_ALIASES,
    TRANSFORMATION_METHODS,
    rank_transform_1d,
)


def _panel(T=30, N=12, seed=0):
    """N=12 >= _MIN_RANK_CROSS_SECTION_OBS, 避免小样本回落干扰对拍."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.standard_t(3, size=(T, N)),
        index=pd.date_range('2020-01-01', periods=T, freq='D'),
        columns=[f's{i:02d}' for i in range(N)],
    )


def _split(df, frac=0.6):
    t = int(len(df) * frac)
    return df, df.iloc[:t], t


def _rank(target='normal'):
    return ProcessingAdapter(
        process_type='transformation', method='rank',
        target_distribution=target,
    )


def _identity():
    return ProcessingAdapter(process_type='transformation', method='identity')


def _manual_normal(row):
    ok = ~np.isnan(row)
    ranks = rankdata(row[ok], method='average')
    n = int(ok.sum())
    out = np.full(row.shape, np.nan)
    out[ok] = norm.ppf((ranks - 0.375) / (n + 0.25))
    return out


def _manual_uniform(row):
    ok = ~np.isnan(row)
    ranks = rankdata(row[ok], method='average')
    n = int(ok.sum())
    out = np.full(row.shape, np.nan)
    out[ok] = (2.0 * ranks - n - 1.0) / n
    return out


# =============================================================================
# 1. 方法解析与别名
# =============================================================================

class TestMethodResolution:
    def test_auto_resolves_to_rank(self):
        adapter = ProcessingAdapter(process_type='transformation', method='auto')
        assert adapter.method == 'rank'
        assert adapter.requested_method == 'auto'
        assert adapter._cross_sectional_rank is True
        assert adapter._identity_transformation is False

    def test_alias_consistency(self):
        assert ADAPTER_ALIASES == TRANSFORMATION_ALIASES
        assert ADAPTER_METHODS == TRANSFORMATION_METHODS

    @pytest.mark.parametrize('alias,expected', [
        ('auto', 'rank'),
        ('none', 'identity'),
        ('quantile', 'rank'),
        ('box_cox', 'boxcox'),
        ('yeo_johnson', 'yeojohnson'),
    ])
    def test_alias_mapping(self, alias, expected):
        adapter = ProcessingAdapter(
            process_type='transformation', method=alias,
            lam=0.5 if expected in ('boxcox', 'yeojohnson') else None,
        )
        assert adapter.method == expected
        assert adapter.requested_method == alias

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError):
            ProcessingAdapter(process_type='transformation', method='does_not_exist')

    def test_invalid_target_raises(self):
        with pytest.raises(ValueError):
            ProcessingAdapter(
                process_type='transformation', method='rank',
                target_distribution='foo',
            )
        with pytest.raises(ValueError):
            AdaptiveTransformer(method='rank', target_distribution='foo')


# =============================================================================
# 2. 数学正确性
# =============================================================================

class TestNumeric:
    def test_normal_matches_manual(self):
        df = _panel(T=30, N=12, seed=11)
        adapter = _rank('normal')
        adapter.fit(df)
        out = adapter.transform(df)
        for dt in df.index:
            expected = _manual_normal(df.loc[dt].to_numpy())
            np.testing.assert_allclose(
                out.loc[dt].to_numpy(), expected, atol=1e-12, rtol=0, equal_nan=True,
            )

    def test_uniform_matches_manual(self):
        df = _panel(T=30, N=12, seed=12)
        adapter = _rank('uniform')
        adapter.fit(df)
        out = adapter.transform(df)
        for dt in df.index:
            expected = _manual_uniform(df.loc[dt].to_numpy())
            np.testing.assert_allclose(
                out.loc[dt].to_numpy(), expected, atol=1e-12, rtol=0, equal_nan=True,
            )

    def test_uniform_moments(self):
        df = _panel(T=60, N=200, seed=13)
        adapter = _rank('uniform')
        adapter.fit(df)
        out = adapter.transform(df)
        # 有限样本精确矩 (pandas .std 默认 ddof=1): sqrt((N+1)/(3N))
        expected_std = np.sqrt((df.shape[1] + 1.0) / (3.0 * df.shape[1]))
        assert np.allclose(out.mean(axis=1), 0.0, atol=1e-12)
        assert np.allclose(out.std(axis=1), expected_std, atol=1e-12)

    def test_normal_moments(self):
        df = _panel(T=60, N=200, seed=14)
        adapter = _rank('normal')
        adapter.fit(df)
        out = adapter.transform(df)
        n = df.shape[1]
        scores = norm.ppf(
            (np.arange(1, n + 1) - 0.375) / (n + 0.25)
        )
        assert np.allclose(
            out.std(axis=1), scores.std(ddof=1), atol=1e-12,
        )
        assert np.all(np.abs(out.skew(axis=1)) < 0.15)

    def test_ties_average(self):
        row = np.array([1.0, 1.0, 2.0, 2.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
        df = pd.DataFrame(
            [row],
            index=pd.date_range('2020-01-01', periods=1),
            columns=[f's{i:02d}' for i in range(len(row))],
        )
        adapter = _rank('normal')
        adapter.fit(df)
        out = adapter.transform(df)
        np.testing.assert_allclose(
            out.iloc[0].to_numpy(), _manual_normal(row),
            atol=1e-12, rtol=0, equal_nan=True,
        )


# =============================================================================
# 3. 因果性
# =============================================================================

class TestCausality:
    def test_truncation_invariance(self):
        df = _panel(T=30, N=12, seed=15)
        full, trunc, t = _split(df)

        a = _rank('normal')
        a.fit(full)
        out_full = a.transform(full)

        b = _rank('normal')
        b.fit(trunc)
        out_trunc = b.transform(trunc)

        pd.testing.assert_frame_equal(
            out_full.iloc[:t], out_trunc, check_exact=True, check_names=False,
        )

    def test_truncation_invariance_uniform(self):
        df = _panel(T=30, N=12, seed=16)
        full, trunc, t = _split(df)

        a = _rank('uniform')
        a.fit(full)
        out_full = a.transform(full)
        b = _rank('uniform')
        b.fit(trunc)
        out_trunc = b.transform(trunc)

        pd.testing.assert_frame_equal(
            out_full.iloc[:t], out_trunc, check_exact=True, check_names=False,
        )

    def test_nan_preserved(self):
        df = _panel(T=25, N=12, seed=17)
        df = df.mask(np.random.default_rng(99).random(df.shape) < 0.1)
        adapter = _rank('normal')
        adapter.fit(df)
        out = adapter.transform(df)

        assert out.index.equals(df.index)
        assert out.columns.equals(df.columns)
        pd.testing.assert_frame_equal(df.isna(), out.isna())

    def test_transform_is_stateless(self):
        df = _panel(T=20, N=12, seed=18)
        adapter = _rank('normal')
        adapter.fit(df)
        o1 = adapter.transform(df)
        o2 = adapter.transform(df)
        pd.testing.assert_frame_equal(o1, o2, check_exact=True)
        assert adapter._processor is None
        assert adapter.fitted_params == {}

    def test_adapter_equals_1d(self):
        df = _panel(T=20, N=12, seed=19)
        adapter = _rank('normal')
        adapter.fit(df)
        out = adapter.transform(df)
        for dt in df.index:
            expected = rank_transform_1d(df.loc[dt].to_numpy(), 'normal')
            np.testing.assert_allclose(
                out.loc[dt].to_numpy(), expected, atol=0, rtol=0, equal_nan=True,
            )


# =============================================================================
# 4. 边界与小样本
# =============================================================================

class TestBoundary:
    def test_small_n_fallback(self):
        cols = [f's{i:02d}' for i in range(12)]
        idx = pd.date_range('2020-01-01', periods=1)

        # N=9 -> 截面 z-score
        row9 = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0] + [np.nan] * 3)
        df9 = pd.DataFrame([row9], index=idx, columns=cols)
        adapter = _rank('normal')
        adapter.fit(df9)
        out9 = adapter.transform(df9)
        s = pd.Series(row9[:9])
        expected9 = ((s - s.mean()) / s.std()).to_numpy()
        np.testing.assert_allclose(out9.iloc[0].to_numpy()[:9], expected9, atol=1e-12)
        assert np.isnan(out9.iloc[0].to_numpy()[9:]).all()

        # N=10 -> rank
        row10 = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0] + [np.nan] * 2)
        df10 = pd.DataFrame([row10], index=idx, columns=cols)
        out10 = adapter.transform(df10)
        np.testing.assert_allclose(
            out10.iloc[0].to_numpy(), _manual_normal(row10),
            atol=1e-12, rtol=0, equal_nan=True,
        )

        # N=1 -> 原样
        row1 = np.array([3.5] + [np.nan] * 11)
        df1 = pd.DataFrame([row1], index=idx, columns=cols)
        out1 = adapter.transform(df1)
        assert out1.iloc[0, 0] == 3.5
        assert np.isnan(out1.iloc[0].to_numpy()[1:]).all()

    def test_non_dataframe_raises(self):
        adapter = _rank('normal')
        with pytest.raises(TypeError):
            adapter.fit(np.zeros((5, 12)))
        adapter.fit(_panel(T=5, N=12))
        with pytest.raises(TypeError):
            adapter.transform(np.zeros((5, 12)))

    def test_duplicate_axis_raises(self):
        df = _panel(T=5, N=12, seed=20)
        dup = df.copy()
        dup.index = ['2020-01-01'] * len(dup)
        adapter = _rank('normal')
        with pytest.raises(ValueError):
            adapter.fit(dup)

        adapter.fit(df)
        dup_cols = df.copy()
        dup_cols.columns = ['s00'] * dup_cols.shape[1]
        with pytest.raises(ValueError):
            adapter.transform(dup_cols)

    def test_empty_returns_copy(self):
        df = pd.DataFrame(index=pd.DatetimeIndex([]), columns=['a', 'b'])
        adapter = _rank('normal')
        adapter.fit(df)
        out = adapter.transform(df)
        assert out.empty
        assert out is not df

    def test_prior_param_required(self):
        with pytest.raises(ValueError):
            AdaptiveTransformer(method='boxcox')
        with pytest.raises(ValueError):
            AdaptiveTransformer(method='yeojohnson')
        with pytest.raises(ValueError):
            AdaptiveTransformer(method='power')
        # 显式传入后合法
        AdaptiveTransformer(method='boxcox', lam=0.5)
        AdaptiveTransformer(method='yeojohnson', lam=0.5)
        AdaptiveTransformer(method='power', power_param=0.5)


# =============================================================================
# 5. identity 与先验方法
# =============================================================================

class TestIdentityAndPrior:
    def test_identity_short_circuit(self):
        df = _panel(T=15, N=12, seed=21)
        adapter = _identity()
        adapter.fit(df)
        out = adapter.transform(df)
        pd.testing.assert_frame_equal(out, df, check_exact=True)
        assert adapter._processor is None
        assert adapter._processor_class is not None
        assert adapter.fitted_params == {}

    def test_identity_keeps_processor_class(self):
        adapter = _identity()
        assert adapter._processor_class is not None

    def test_yj_lambda_one_equals_identity(self):
        x = np.array([-3.0, -1.0, -0.25, 0.0, 0.5, 1.0, 2.0, 5.0])
        t = AdaptiveTransformer(method='yeojohnson', lam=1.0)
        t.fit(x)
        np.testing.assert_allclose(t.transform(x), x, atol=1e-12, rtol=0)

    def test_yj_lambda_two_neg_branch(self):
        x = np.array([-2.0, -0.5])
        t = AdaptiveTransformer(method='yeojohnson', lam=2.0)
        t.fit(x)
        np.testing.assert_allclose(
            t.transform(x), -np.log(1.0 - x), atol=1e-12, rtol=0,
        )

    def test_boxcox_lambda_zero_equals_log(self):
        x = np.array([0.5, 1.0, 2.0, 10.0])
        t = AdaptiveTransformer(method='boxcox', lam=0.0)
        t.fit(x)
        np.testing.assert_allclose(t.transform(x), np.log(x), atol=1e-12, rtol=0)

    def test_log_negative_raises(self):
        t = AdaptiveTransformer(method='log', offset=0.0)
        x = np.array([-1.0, 1.0, 2.0])
        t.fit(x)
        with pytest.raises(ValueError):
            t.transform(x)

    def test_adaptive_transformer_rejects_dataframe_for_rank(self):
        df = _panel(T=5, N=12, seed=22)
        t = AdaptiveTransformer(method='rank')
        t.fit(df)
        with pytest.raises(TypeError):
            t.transform(df)


# =============================================================================
# 6. get_stats
# =============================================================================

class TestStats:
    def test_get_stats(self):
        df = _panel(T=10, N=12, seed=23)
        adapter = _rank('uniform')
        adapter.fit(df)
        stats = adapter.get_stats()
        assert stats['transform_scope'] == 'cross_sectional'
        assert stats['target_distribution'] == 'uniform'
        assert stats['requested_method'] == 'rank'
        assert stats['method'] == 'rank'
        assert _MIN_RANK_CROSS_SECTION_OBS == 10
