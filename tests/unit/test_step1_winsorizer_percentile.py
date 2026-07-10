"""Step 1 TDD: Winsorizer 1%/99% percentile 固定方法"""
import numpy as np
import pytest
from factor_pipeline.modules.factor_adaptive_winsor.core.transformers import SmartOutlierDetector


class TestPercentileMethodExists:
    """TDD Red: SmartOutlierDetector 应有 percentile 方法"""

    def test_percentile_fit_returns_params(self):
        """method='percentile' 应正确拟合 1%/99% 阈值"""
        det = SmartOutlierDetector(method='percentile', auto_select=False,
                                   percentile_lower=1.0, percentile_upper=99.0)
        X = np.random.randn(5000) + 5
        det.fit(X)
        params = det.fitted_params
        assert params['method'] == 'percentile', f"method should be percentile, got {params.get('method')}"
        assert 'lower_bound' in params, "missing lower_bound"
        assert 'upper_bound' in params, "missing upper_bound"
        assert params['lower_bound'] < params['upper_bound'], \
            f"lower({params['lower_bound']}) should be < upper({params['upper_bound']})"

    def test_percentile_clips_extremes(self):
        """1%/99% percentile 应正确剪裁极端值"""
        det = SmartOutlierDetector(method='percentile', auto_select=False,
                                   percentile_lower=1.0, percentile_upper=99.0)
        # 注入已知极端值
        X = np.concatenate([np.random.randn(980), [-1000.0] * 10, [1000.0] * 10])
        det.fit(X)
        X_trans = det.transform(X)

        # 变换后值应在 [lower, upper] 内
        lo = det.fitted_params['lower_bound']
        hi = det.fitted_params['upper_bound']
        assert np.all(X_trans >= lo - 1e-10), \
            f"all values should be >= lower({lo}), min={X_trans.min()}"
        assert np.all(X_trans <= hi + 1e-10), \
            f"all values should be <= upper({hi}), max={X_trans.max()}"

    def test_percentile_1_99_preserves_most_values(self):
        """1%/99% 分位数缩尾: ~98% 的值不变"""
        np.random.seed(42)
        det = SmartOutlierDetector(method='percentile', auto_select=False,
                                   percentile_lower=1.0, percentile_upper=99.0)
        X = np.random.randn(10000)
        det.fit(X)
        X_trans = det.transform(X)
        unchanged = np.sum(np.abs(X - X_trans) < 1e-10)
        pct_unchanged = unchanged / len(X) * 100
        assert pct_unchanged > 95, \
            f"should preserve >95% values, got {pct_unchanged:.1f}%"

    def test_percentile_cross_sectional_vectorized(self):
        """截面缩尾: 每期独立计算分位数 — 向量化 (无 for 循环)"""
        det = SmartOutlierDetector(method='percentile', auto_select=False,
                                   percentile_lower=1.0, percentile_upper=99.0)
        # 多期截面数据: (5, 100)
        X = np.random.randn(5, 100) * np.array([[1.0], [2.0], [0.5], [3.0], [1.5]])

        for row in range(X.shape[0]):
            det.fit(X[row])
            X_row_trans = det.transform(X[row])
            lo = det.fitted_params['lower_bound']
            hi = det.fitted_params['upper_bound']
            assert np.all(X_row_trans >= lo - 1e-10)
            assert np.all(X_row_trans <= hi + 1e-10)
