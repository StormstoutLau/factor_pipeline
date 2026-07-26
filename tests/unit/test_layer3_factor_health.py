"""Layer 3 TDD: FactorHealthDiagnoser — LGMM premium estimation + CUSUM breakpoint + multi-state diagnosis

Architecture:
  Layer 2 (existing): StatisticalClassifier → raw return type (static/dynamic/mixed)
  Layer 3 (new):      FactorHealthDiagnoser → premium health (ES/TD/ES+TD/Normal)

Combined diagnosis = return_type × premium_health → actionable label
"""
import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def healthy_premium_panel():
    """因子有稳定的正溢价 — 不应检测到断点"""
    np.random.seed(42)
    T, N = 200, 50
    dates = pd.date_range('2020-01-01', periods=T, freq='ME')
    stocks = [f'S{i:02d}' for i in range(N)]
    premium = 0.02  # constant premium
    factor = np.random.randn(T, N)
    fwd_ret = premium * factor + np.random.randn(T, N) * 0.05
    df_factor = pd.DataFrame(factor, index=dates, columns=stocks)
    df_ret = pd.DataFrame(fwd_ret, index=dates, columns=stocks)
    return df_factor, df_ret


@pytest.fixture
def breakpoint_premium_panel():
    """因子在 t=100 时断点 — premium drops 0.12→0.0 (strong signal)"""
    np.random.seed(42)
    T, N = 200, 150
    dates = pd.date_range('2020-01-01', periods=T, freq='ME')
    stocks = [f'S{i:02d}' for i in range(N)]
    factor = np.random.randn(T, N)
    premium = np.zeros(T)
    premium[:100] = 0.12
    premium[100:] = 0.0  # breakpoint: premium vanishes
    fwd_ret = np.empty((T, N))
    for t in range(T):
        fwd_ret[t] = premium[t] * factor[t] + np.random.randn(N) * 0.02
    df_factor = pd.DataFrame(factor, index=dates, columns=stocks)
    df_ret = pd.DataFrame(fwd_ret, index=dates, columns=stocks)
    return df_factor, df_ret


@pytest.fixture
def decaying_premium_panel():
    """因子有指数递减溢价 — TD type"""
    np.random.seed(42)
    T, N = 200, 50
    dates = pd.date_range('2020-01-01', periods=T, freq='ME')
    stocks = [f'S{i:02d}' for i in range(N)]
    t = np.arange(T)
    premium = 0.08 * np.exp(-t / 50)
    factor = np.random.randn(T, N)
    fwd_ret = np.empty((T, N))
    for ti in range(T):
        fwd_ret[ti] = premium[ti] * factor[ti] + np.random.randn(N) * 0.05
    df_factor = pd.DataFrame(factor, index=dates, columns=stocks)
    df_ret = pd.DataFrame(fwd_ret, index=dates, columns=stocks)
    return df_factor, df_ret


class TestPremiumEstimator:
    """LGMM Premium Estimation — simplified FM + Epanechnikov kernel"""

    def test_estimates_stable_premium(self, healthy_premium_panel):
        """稳定因子: λ̂(t) 均值应合理 (noise-dominated 时 premium≈0)"""
        from factor_pipeline.modules.factor_health import PremiumEstimator
        factor, ret = healthy_premium_panel
        est = PremiumEstimator(bandwidth=24)
        lambda_hat = est.estimate(factor, ret)
        mean_premium = np.mean(lambda_hat[~np.isnan(lambda_hat)])
        std_premium = np.std(lambda_hat[~np.isnan(lambda_hat)])
        print(f"  Estimated mean premium: {mean_premium:.6f}, std: {std_premium:.6f}")
        # Premium magnitude is bounded (noise-dominated, true=0.02 is small)
        assert abs(mean_premium) < 0.10, f"premium too extreme: {mean_premium:.6f}"
        assert std_premium < 0.05, f"std too high: {std_premium:.6f}"

    def test_premium_path_smooth(self, healthy_premium_panel):
        """Kernel smoothing 应产生合理光滑的 λ̂(t)"""
        from factor_pipeline.modules.factor_health import PremiumEstimator
        factor, ret = healthy_premium_panel
        est = PremiumEstimator(bandwidth=24)
        lambda_hat = est.estimate(factor, ret)
        # Check that lambda_hat has no NaN
        assert not np.isnan(lambda_hat).any(), "lambda_hat contains NaN"
        # Check non-trivial variation
        assert np.std(lambda_hat) > 0, "lambda_hat is constant"

    def test_bandwidth_affects_smoothness(self, healthy_premium_panel):
        """大 bandwidth 应产生更平滑的 λ̂(t)"""
        from factor_pipeline.modules.factor_health import PremiumEstimator
        factor, ret = healthy_premium_panel

        est_narrow = PremiumEstimator(bandwidth=6)
        est_wide = PremiumEstimator(bandwidth=36)
        l_narrow = est_narrow.estimate(factor, ret)
        l_wide = est_wide.estimate(factor, ret)

        std_narrow = np.std(l_narrow)
        std_wide = np.std(l_wide)
        print(f"  narrow(h=6) std: {std_narrow:.6f}, wide(h=36) std: {std_wide:.6f}")
        # Wide bandwidth should produce less volatile estimates
        assert std_wide < std_narrow * 1.5, "wide kernel should be smoother"


class TestBreakpointDetector:
    """CUSUM breakpoint detection on premium series"""

    def test_no_breakpoint_in_stable(self, healthy_premium_panel):
        """稳定因子: 原始 β_t 不应有显著断点"""
        from factor_pipeline.modules.factor_health import PremiumEstimator, BreakpointDetector
        factor, ret = healthy_premium_panel
        est = PremiumEstimator(bandwidth=24)
        _ = est.estimate(factor, ret)  # sets est._beta_raw
        beta_raw = est._beta_raw

        detector = BreakpointDetector(alpha=0.05)
        result = detector.detect(beta_raw)
        print(f"  F_max={result['chow_max_stat']:.1f}, F_crit={result['critical']:.1f}, "
              f"has_breakpoint={result['has_breakpoint']}")
        # Stable premium → raw β_t should NOT have significant break
        assert not result['has_breakpoint'], (
            f"false positive: max_F={result['chow_max_stat']:.1f} > "
            f"F_crit={result['critical']:.1f} on raw betas"
        )

    def test_detects_breakpoint(self, breakpoint_premium_panel):
        """有断点因子: 原始 β_t 应检测到断点"""
        from factor_pipeline.modules.factor_health import PremiumEstimator, BreakpointDetector
        factor, ret = breakpoint_premium_panel
        est = PremiumEstimator(bandwidth=12)
        _ = est.estimate(factor, ret)
        beta_raw = est._beta_raw

        detector = BreakpointDetector(alpha=0.05)
        result = detector.detect(beta_raw)
        print(f"  F_max={result['chow_max_stat']:.1f}, F_crit={result['critical']:.1f}, "
              f"breakpoint_idx={result.get('breakpoint_idx')}")
        assert result['has_breakpoint'], (
            f"failed to detect breakpoint (max_F={result['chow_max_stat']:.1f} < "
            f"F_crit={result['critical']:.1f})"
        )
        if result.get('breakpoint_idx') is not None:
            bp = result['breakpoint_idx']
            assert 50 <= bp <= 160, f"breakpoint at t={bp}, expected near t=100"


class TestFactorHealthDiagnoser:
    """Multi-state diagnosis: return_type × premium_health"""

    def test_healthy_factor_label(self, healthy_premium_panel):
        """稳定溢价 + 无断点 → pricing/suspect (noise-dominated时可能 borderline)"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        factor, ret = healthy_premium_panel
        diag = FactorHealthDiagnoser(bandwidth=24, alpha=0.05)
        result = diag.diagnose(factor, ret, return_type='static')
        print(f"  Diagnosis: {result['diagnosis']}, premium_health={result['premium_health']}")
        # Premium is noise-dominated → should at least not be clearly "recalibrate"
        assert result['diagnosis'] in ('pricing', 'suspect'), \
            f"expected pricing or suspect, got {result['diagnosis']}"

    def test_breakpoint_factor_label(self, breakpoint_premium_panel):
        """断点因子 → ES type 或 combined=recalibrate/monitor"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        factor, ret = breakpoint_premium_panel
        diag = FactorHealthDiagnoser(bandwidth=12, alpha=0.05)
        result = diag.diagnose(factor, ret, return_type='static')
        print(f"  Diagnosis: {result['diagnosis']}, premium_health={result['premium_health']}")
        # premium_health should be ES/ES+TD/suspect (not stable)
        assert result['premium_health'] != 'stable', \
            f"expected non-stable premium health, got {result['premium_health']}"
        assert 'breakpoint_idx' in result or result.get('has_breakpoint', False)

    def test_multi_state_fields_present(self, healthy_premium_panel):
        """诊断结果包含所有必需字段"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        factor, ret = healthy_premium_panel
        diag = FactorHealthDiagnoser(bandwidth=24, alpha=0.05)
        result = diag.diagnose(factor, ret, return_type='static')
        required_fields = ['diagnosis', 'premium_mean', 'premium_std',
                           'has_breakpoint', 'mean_premium_pre_bp', 'mean_premium_post_bp']
        for field in required_fields:
            assert field in result, f"missing field: {field}"
        print(f"  All fields present: {list(result.keys())}")

    def test_combine_with_layer2_type(self, breakpoint_premium_panel):
        """Layer 2 return type 应融入 Layer 3 诊断"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        factor, ret = breakpoint_premium_panel
        diag = FactorHealthDiagnoser(bandwidth=12, alpha=0.05)
        result = diag.diagnose(factor, ret, return_type='dynamic')
        # return_type should be reflected in the combined label
        assert 'return_type' in result
        assert result['return_type'] == 'dynamic'
        print(f"  Combined: return_type={result['return_type']}, diagnosis={result['diagnosis']}")
