# -*- coding: utf-8 -*-
"""PL-02: AdaptiveTransformer 无状态 rank 与先验参数模式.

旧文件围绕已删除的 `auto` 选型链 (skew/kurt/Shapiro 特征 + identity 回退).
新契约:
- rank 为无状态 PIT 映射, `target_distribution` 控制输出分布
- identity 为 no-op
- 显式方法 (boxcox/yeojohnson/power/log) 只读先验参数, fit 不估计
"""
import numpy as np
import pytest
from scipy.stats import norm

from factor_pipeline.modules.factor_adaptive_winsor.core.transformers import (
    AdaptiveTransformer,
)


def _ranked(target, n=2000, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal(n)
    t = AdaptiveTransformer(method='rank', target_distribution=target)
    t.fit(X)
    return X, t.transform(X)


class TestRankMoments:
    def test_rank_uniform_moments(self):
        """归一化秩: E[u]=0, std→1/√3."""
        _, out = _ranked('uniform')
        assert abs(float(np.mean(out))) < 1e-12
        assert abs(float(np.std(out)) - 1.0 / np.sqrt(3.0)) < 1e-6

    def test_rank_normal_moments(self):
        """Blom 正态分数: 有限样本 std 精确, skew≈0."""
        _, out = _ranked('normal')
        n = len(out)
        scores = norm.ppf((np.arange(1, n + 1) - 0.375) / (n + 0.25))
        assert abs(float(np.std(out)) - float(np.std(scores))) < 1e-12
        assert abs(float(np.mean(out))) < 1e-12
        assert abs(float(np.mean(out ** 3))) < 1e-3


class TestRankNaN:
    def test_rank_nan_preserved(self):
        """NaN 保持且不参与排名."""
        X = np.array([1.0, np.nan, 2.0, 3.0, np.nan, 4.0, 5.0])
        t = AdaptiveTransformer(method='rank')
        t.fit(X)
        out = t.transform(X)
        assert np.isnan(out[1]) and np.isnan(out[4])
        assert np.all(np.isfinite(out[[0, 2, 3, 5, 6]]))
        # 非 NaN 位置的排序与无 NaN 输入一致
        ok = ~np.isnan(X)
        t2 = AdaptiveTransformer(method='rank')
        out2 = t2.fit(X[ok]).transform(X[ok])
        np.testing.assert_allclose(out[ok], out2, atol=1e-12, rtol=0)


class TestIdentity:
    def test_identity_noop(self):
        """identity 返回输入, 不改数值也不复制 NaN."""
        X = np.array([np.nan, -1.0, 0.0, 2.0])
        t = AdaptiveTransformer(method='identity')
        t.fit(X)
        out = t.transform(X)
        np.testing.assert_array_equal(out, X)


class TestPriorParams:
    def test_boxcox_lam_zero_equals_log(self):
        """boxcox(lam=0) == log(x), 不估计 λ."""
        rng = np.random.default_rng(7)
        X = rng.uniform(0.1, 10.0, 500)
        t = AdaptiveTransformer(method='boxcox', lam=0.0)
        t.fit(X)
        out = t.transform(X)
        np.testing.assert_allclose(out, np.log(X), atol=1e-12, rtol=0)

    def test_lam_required_for_boxcox(self):
        with pytest.raises(ValueError, match='lam'):
            AdaptiveTransformer(method='boxcox')


class TestMethodResolution:
    def test_alias_resolution(self):
        auto = AdaptiveTransformer(method='auto')
        assert auto.method == 'rank'
        assert auto.requested_method == 'auto'
        assert auto.target_distribution == 'normal'

        none = AdaptiveTransformer(method='none')
        assert none.method == 'identity'
        assert none.requested_method == 'none'

    def test_invalid_method_raises(self):
        with pytest.raises(ValueError, match='未知'):
            AdaptiveTransformer(method='not_a_method')

    def test_invalid_target_raises(self):
        with pytest.raises(ValueError, match='target_distribution'):
            AdaptiveTransformer(method='rank', target_distribution='cauchy')
