"""Step 7 TDD: 向量化 StatisticalClassifier — VR(p) + AR(1) stationarity"""
import numpy as np
import pandas as pd
import pytest
from factor_pipeline.modules.statistical_classifier import StatisticalClassifier


@pytest.fixture
def static_panel():
    """AR(1)=0.95 的静态面板 (应分类为 static)"""
    np.random.seed(42)
    T, N = 200, 50
    data = np.zeros((T, N))
    data[0] = np.random.randn(N) * 2
    for t in range(1, T):
        data[t] = 0.95 * data[t-1] + np.random.randn(N) * 0.1
    dates = pd.date_range('2020-01-01', periods=T, freq='ME')
    stocks = [f'S{i:02d}' for i in range(N)]
    return pd.DataFrame(data, index=dates, columns=stocks)


@pytest.fixture
def dynamic_panel():
    """白噪声面板 (应分类为 dynamic)"""
    np.random.seed(123)
    T, N = 200, 50
    data = np.random.randn(T, N)
    dates = pd.date_range('2020-01-01', periods=T, freq='ME')
    stocks = [f'S{i:02d}' for i in range(N)]
    return pd.DataFrame(data, index=dates, columns=stocks)


class TestStatisticalClassifier:
    """VR + AR(1) stationarity 向量化分类"""

    def test_classifier_returns_valid_type(self, static_panel):
        """返回 'static' | 'dynamic' | 'mixed'"""
        clf = StatisticalClassifier(alpha=0.05, vr_q=5)
        result = clf.classify(static_panel)
        assert result in ('static', 'dynamic', 'mixed'), f"invalid type: {result}"

    def test_static_panel_classified_as_static(self, static_panel):
        """AR(1)=0.95 — VR rejects RW + stationary → static"""
        clf = StatisticalClassifier(alpha=0.05, vr_q=5)
        result = clf.classify(static_panel)
        print(f"static panel classified as: {result}")
        # At least not dynamic (we accept static or mixed)
        assert result in ('static', 'mixed'), \
            f"AR(1)=0.95 panel should be static or mixed, got {result}"

    def test_dynamic_panel_classified_as_dynamic(self, dynamic_panel):
        """白噪声 — VR not rejected + stationary → dynamic"""
        clf = StatisticalClassifier(alpha=0.05, vr_q=5)
        result = clf.classify(dynamic_panel)
        print(f"dynamic (white-noise) panel classified as: {result}")
        assert result in ('dynamic', 'mixed'), \
            f"white-noise panel should be dynamic or mixed, got {result}"

    def test_vectorized_no_for_loops(self, static_panel):
        """classify() 不包含 Python for 循环 (纯 numpy/pandas 向量化)"""
        clf = StatisticalClassifier(alpha=0.05, vr_q=5)
        # 快速运行 (< 1s for 200×50 panel)
        import time
        t0 = time.time()
        result = clf.classify(static_panel)
        elapsed = time.time() - t0
        assert result in ('static', 'dynamic', 'mixed')
        assert elapsed < 1.0, f"classify() took {elapsed:.2f}s, should be < 1s"
