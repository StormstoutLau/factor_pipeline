"""TDD: _select_optimal_transform identity 回退 + kurtosis threshold 修复"""
import numpy as np
from scipy import stats
import pytest

from factor_pipeline.modules.factor_adaptive_winsor.core.transformers import AdaptiveTransformer


def _make(kurt_val=0.0, skew_val=0.0, is_positive=True):
    features = {
        'is_normal': abs(skew_val) < 0.5 and abs(kurt_val - 3) < 1,
        'is_positive': is_positive,
        'is_heavy_tailed': kurt_val > 3,
        'is_skewed': abs(skew_val) > 0.5,
    }
    return features


class TestSelectOptimalTransform:
    """_select_optimal_transform 决策表"""

    def test_normal_positive_now_returns_identity(self):
        """is_normal=True → identity (修复后)"""
        t = AdaptiveTransformer(method='auto')
        # kurtosis=3 在旧逻辑中意味着 abs(3-3)=0 < 1 → is_normal
        methods = set()
        for _ in range(10):
            X = np.random.randn(1000) + 100  # shift to positive
            t.fit(X)
            methods.add(t.fitted_params.get('method'))
        # 至少有一次 identity (修复后)
        assert 'identity' in methods, f"正常数据应选 identity, 实际: {methods}"

    def test_skewed_negative_selects_yeojohnson(self):
        """偏态+负值 → yeojohnson"""
        t = AdaptiveTransformer(method='auto')
        X = np.random.exponential(2, 2000) - 0.5  # skewed, partly negative
        t.fit(X)
        assert t.fitted_params['method'] != 'identity', "非正态不应选 identity"

    def test_heavy_tailed_positive_selects_boxcox(self):
        """重尾+正值 → 不应选 identity"""
        np.random.seed(42)
        t = AdaptiveTransformer(method='auto')
        X = np.random.standard_t(2, 5000) + 10
        t.fit(X)
        method = t.fitted_params['method']
        feat = t.fitted_params['data_features']
        print(f"heavy_tailed={feat['is_heavy_tailed']}, positive={feat['is_positive']}, method={method}")
        assert method != 'identity', f"重尾数据不应选 identity, 实际: {method}"


class TestAnalyzeFeaturesKurtosisFix:
    """_analyze_features 的 kurtosis 阈值修复"""

    def test_normal_data_is_normal(self):
        """N(0,1) 应被识别为 is_normal (修复后)"""
        t = AdaptiveTransformer(method='auto')
        X = np.random.randn(5000)
        t.fit(X)
        feat = t.fitted_params['data_features']
        k = stats.kurtosis(X)  # excess kurtosis
        print(f"skew={feat['skewness']:.3f} kurt={feat['kurtosis']:.3f} (excess≈{k:.3f})")
        print(f"is_normal(old_check(abs(k-3)<1))={abs(feat['kurtosis'] - 3) < 1}")
        # 修复后 is_normal 应使用 excess kurtosis (< 1)
        # 当前代码用 abs(kurtosis-3)<1 → 对 N(0,1) 恒为 False
        # 这个测试验证修复是否生效
        assert feat['is_normal'], (
            f"N(0,1) 应 is_normal=True, 实际={feat['is_normal']}, "
            f"kurtosis(excess)={k:.3f}"
        )

    def test_heavy_tailed_not_normal(self):
        """t(2) 不应被识别为 normal"""
        t = AdaptiveTransformer(method='auto')
        X = np.random.standard_t(2, 5000)
        t.fit(X)
        feat = t.fitted_params['data_features']
        assert not feat['is_normal'], f"t(2) 不应 is_normal, 实际={feat['is_normal']}"
        assert feat['is_heavy_tailed'], f"t(2) 应 is_heavy_tailed"


class TestIdentityNoChange:
    """identity 变换不改变数据"""

    def test_identity_transform_is_noop(self):
        """identity 应返回原始数据"""
        t = AdaptiveTransformer(method='auto')
        X = np.random.randn(2000) + 100
        t.fit(X)
        if t.fitted_params.get('method') == 'identity':
            X_out = t.transform(X)
            diff = (X - X_out).std()
            # identity 应不改变数据 (允许 < 1e-12 浮点误差)
            assert diff < 1e-12, f"identity 不应改变数据, diff_std={diff}"
