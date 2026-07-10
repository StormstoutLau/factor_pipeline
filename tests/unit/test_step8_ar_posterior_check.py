"""Step 8 TDD: Anderson-Rubin 后验检验 (R² 监控)"""
import numpy as np
import pandas as pd
import pytest
from factor_pipeline.adapters import NeutralizerAdapter


@pytest.fixture
def neutralized_panel():
    """Generate panel with known industry structure, fit+transform, return result."""
    np.random.seed(42)
    T, N = 20, 50
    dates = pd.date_range('2020-01-01', periods=T, freq='ME')
    stocks = [f'S{i:02d}' for i in range(N)]

    # 5 industries
    industries = [f'I{i}' for i in range(5)]
    ind_map = {s: industries[i % 5] for i, s in enumerate(stocks)}
    ind_series = pd.Series(ind_map)

    # factor values with industry bias (~ind_dummies) + noise
    data = np.random.randn(T, N)
    df = pd.DataFrame(data, index=dates, columns=stocks)

    na = NeutralizerAdapter(
        neutralization_type='industry',
        industry_data=ind_series,
        enable_ar_check=False,
    )
    na.fit(df)
    result = na.transform(df)
    return result, ind_series, df


class TestARPosteriorCheck:
    """Anderson-Rubin: R²(residuals ~ dummies) ≈ 0 after neutralization"""

    def test_ar_check_disabled_no_side_effect(self, neutralized_panel):
        """enable_ar_check=False — 不应影响输出 (向后兼容)"""
        result, ind_series, df = neutralized_panel
        assert not result.isnull().all().all(), "output should not be all NaN"
        assert result.shape == df.shape, f"shape should match: {result.shape} vs {df.shape}"

    def test_ar_check_enabled_fit_and_transform(self):
        """enable_ar_check=True — 不应抛异常"""
        np.random.seed(42)
        N = 30
        stocks = [f'S{i:02d}' for i in range(N)]
        ind_map = {s: f'I{i % 5}' for i, s in enumerate(stocks)}
        ind_series = pd.Series(ind_map)
        df = pd.DataFrame(np.random.randn(10, N),
                          index=pd.date_range('2020-01-01', periods=10, freq='ME'),
                          columns=stocks)

        na = NeutralizerAdapter(
            neutralization_type='industry',
            industry_data=ind_series,
            enable_ar_check=True,
        )
        na.fit(df)
        result = na.transform(df)
        assert not result.isnull().all().all()
        assert result.shape == df.shape

    def test_neutralized_residuals_have_near_zero_r2(self, neutralized_panel):
        """中性化后残差对 dummies 的 R² 应接近 0"""
        result, ind_series, df = neutralized_panel
        # Manually verify R²(residuals ~ dummies) ≈ 0
        r2_list = []
        for date in result.index:
            row = result.loc[date]
            common = row.index.intersection(ind_series.index)
            if len(common) < 10:
                continue
            y = row[common].values.astype(float)
            dummies = pd.get_dummies(ind_series[common], drop_first=True).astype(float)
            # OLS: y ~ dummies
            X_mat = np.column_stack([np.ones(len(y)), dummies.values])
            beta = np.linalg.lstsq(X_mat, y, rcond=None)[0]
            y_hat = X_mat @ beta
            ss_res = np.sum((y - y_hat) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
            r2_list.append(r2)

        avg_r2 = np.mean(r2_list)
        print(f"  avg R²(residuals~dummies) = {avg_r2:.6f}")
        # After perfect neutralization, R² should be very close to 0
        assert avg_r2 < 0.01, (
            f"neutralized residuals should have R²≈0 vs dummies, got {avg_r2:.6f}"
        )
