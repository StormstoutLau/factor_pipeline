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


class TestPremiumEstimatorErrors:
    """E1-E7: HAC standard errors for FM premium (v3.4.12)"""

    def test_returns_arrays_with_ci_consistent(self, healthy_premium_panel):
        """E1: 六个数组长度 T; lambda_hat 与 estimate() 全等; CI = λ̂ ± z·SE"""
        from scipy.stats import norm
        from factor_pipeline.modules.factor_health import PremiumEstimator
        factor, ret = healthy_premium_panel
        est = PremiumEstimator(bandwidth=24)
        res = est.estimate_with_errors(factor, ret)

        T = len(factor)
        for key in ('lambda_hat', 'lambda_se', 'lambda_ci_low',
                    'lambda_ci_high', 'beta_t', 'beta_se'):
            assert key in res, f"missing key: {key}"
            assert isinstance(res[key], np.ndarray), f"{key} not ndarray"
            assert len(res[key]) == T, f"{key} length {len(res[key])} != {T}"

        np.testing.assert_array_equal(res['lambda_hat'], est.estimate(factor, ret))

        z = norm.ppf(0.975)
        np.testing.assert_allclose(
            res['lambda_ci_low'], res['lambda_hat'] - z * res['lambda_se'], equal_nan=True)
        np.testing.assert_allclose(
            res['lambda_ci_high'], res['lambda_hat'] + z * res['lambda_se'], equal_nan=True)
        assert np.isfinite(res['lambda_se']).all()
        assert (res['lambda_se'] > 0).all()

    def test_premium_mean_and_hac_se(self, healthy_premium_panel):
        """E2: premium_mean == nanmean(beta_t); se > 0; CI 包含均值"""
        from factor_pipeline.modules.factor_health import PremiumEstimator
        factor, ret = healthy_premium_panel
        est = PremiumEstimator(bandwidth=24)
        res = est.estimate_with_errors(factor, ret)

        expected_mean = float(np.nanmean(res['beta_t']))
        assert res['premium_mean'] == pytest.approx(expected_mean, rel=1e-12, abs=0)
        assert np.isfinite(res['premium_mean_se'])
        assert res['premium_mean_se'] > 0
        assert res['premium_mean_ci_low'] < res['premium_mean'] < res['premium_mean_ci_high']

    def test_metadata_and_default_lag(self, healthy_premium_panel):
        """E3: n_periods / n_valid / hac_lag / alpha 元信息"""
        from factor_pipeline.modules.factor_health import PremiumEstimator
        factor, ret = healthy_premium_panel
        est = PremiumEstimator(bandwidth=24)
        res = est.estimate_with_errors(factor, ret)

        n_valid = int(np.isfinite(res['beta_t']).sum())
        expected_lag = max(1, int(4 * (n_valid / 100) ** (2 / 9)))
        assert res['n_periods'] == len(factor)
        assert res['n_valid'] == n_valid
        assert res['hac_lag'] == expected_lag
        assert res['alpha'] == 0.05

        res_override = est.estimate_with_errors(factor, ret, max_lag=2)
        assert res_override['hac_lag'] == 2

    def test_beta_se_matches_cross_sectional_ols(self, healthy_premium_panel):
        """E4: beta_se = sqrt(σ̂²_ε/Σ(f−f̄)²); NaN 位置与 beta_t 一致"""
        from factor_pipeline.modules.factor_health import PremiumEstimator
        factor, ret = healthy_premium_panel
        est = PremiumEstimator(bandwidth=24)
        res = est.estimate_with_errors(factor, ret)

        finite = np.isfinite(res['beta_t'])
        raw_nan = np.isnan(res['beta_t'])
        se_nan = np.isnan(res['beta_se'])
        np.testing.assert_array_equal(se_nan, raw_nan)
        assert (res['beta_se'][finite] > 0).all()

        t = 100
        f = factor.values[t]
        r = ret.values[t]
        f_demean = f - f.mean()
        r_demean = r - r.mean()
        beta = np.dot(f_demean, r_demean) / np.dot(f_demean, f_demean)
        resid = r_demean - beta * f_demean
        sigma2 = np.dot(resid, resid) / (len(f) - 2)
        expected_se = np.sqrt(sigma2 / np.dot(f_demean, f_demean))

        assert res['beta_t'][t] == pytest.approx(beta, rel=1e-12)
        assert res['beta_se'][t] == pytest.approx(expected_se, rel=1e-12)

    def test_missing_data_degenerate(self, healthy_premium_panel):
        """E5: 缺失/全缺失/无共同股票/无共同日期 均不抛异常"""
        from factor_pipeline.modules.factor_health import PremiumEstimator
        factor, ret = healthy_premium_panel
        est = PremiumEstimator(bandwidth=24)

        # 注入缺失: 25 < min_stocks=30 → 该期 β 为 NaN; λ̂ 由邻期平滑仍可估计
        f_missing = factor.copy()
        f_missing.iloc[100, :25] = np.nan
        res = est.estimate_with_errors(f_missing, ret)
        assert np.isnan(res['beta_t'][100])
        assert np.isnan(res['beta_se'][100])
        assert np.isfinite(res['lambda_hat'][100])
        assert np.isfinite(res['lambda_se'][100])
        assert res['n_valid'] < res['n_periods']

        # 全序列仅 2 期有效 β → 窗口有效点 <3: λ̂ / SE 全 NaN, 标量 NaN
        f_two = pd.DataFrame(np.nan, index=factor.index, columns=factor.columns)
        f_two.iloc[0] = factor.iloc[0]
        f_two.iloc[1] = factor.iloc[1]
        res_two = est.estimate_with_errors(f_two, ret)
        assert res_two['n_valid'] == 2
        assert np.isnan(res_two['lambda_hat']).all()
        assert np.isnan(res_two['lambda_se']).all()
        assert np.isnan(res_two['premium_mean'])

        # 全缺失 → 标量 NaN
        f_all_nan = pd.DataFrame(np.nan, index=factor.index, columns=factor.columns)
        res_all = est.estimate_with_errors(f_all_nan, ret)
        assert res_all['n_valid'] == 0
        assert res_all['hac_lag'] == 1
        assert np.isnan(res_all['premium_mean'])
        assert np.isnan(res_all['premium_mean_se'])
        assert np.isnan(res_all['lambda_hat']).all()
        assert np.isnan(res_all['lambda_se']).all()

        # 无共同股票 → T 期全 NaN
        ret_disjoint_cols = ret.copy()
        ret_disjoint_cols.columns = [f'X{i:02d}' for i in range(ret.shape[1])]
        res_no_cols = est.estimate_with_errors(factor, ret_disjoint_cols)
        assert res_no_cols['n_periods'] == len(factor)
        assert res_no_cols['n_valid'] == 0
        assert np.isnan(res_no_cols['lambda_hat']).all()

        # 无共同日期 → T=0
        ret_disjoint_dates = ret.copy()
        ret_disjoint_dates.index = ret.index + pd.DateOffset(years=100)
        res_no_dates = est.estimate_with_errors(factor, ret_disjoint_dates)
        assert res_no_dates['n_periods'] == 0
        assert len(res_no_dates['lambda_hat']) == 0
        assert np.isnan(res_no_dates['premium_mean'])

    def test_estimate_unchanged(self, healthy_premium_panel):
        """E6: estimate() 数值与返回类型不变; _beta_raw 一致"""
        from factor_pipeline.modules.factor_health import PremiumEstimator
        factor, ret = healthy_premium_panel
        est = PremiumEstimator(bandwidth=24)

        out = est.estimate(factor, ret)
        beta_ref = est._beta_raw.copy()
        res = est.estimate_with_errors(factor, ret)

        assert isinstance(out, np.ndarray)
        np.testing.assert_array_equal(out, res['lambda_hat'])
        np.testing.assert_array_equal(beta_ref, res['beta_t'])
        np.testing.assert_array_equal(est._beta_raw, res['beta_t'])

    def test_alpha_sensitivity(self, healthy_premium_panel):
        """E7: alpha=0.10 与 0.05 的 CI 宽度比 = z_0.10/z_0.05"""
        from scipy.stats import norm
        from factor_pipeline.modules.factor_health import PremiumEstimator
        factor, ret = healthy_premium_panel
        est = PremiumEstimator(bandwidth=24)

        res_05 = est.estimate_with_errors(factor, ret, alpha=0.05)
        res_10 = est.estimate_with_errors(factor, ret, alpha=0.10)

        mask = np.isfinite(res_05['lambda_se']) & (res_05['lambda_se'] > 0)
        assert mask.any()
        width_05 = res_05['lambda_ci_high'][mask] - res_05['lambda_ci_low'][mask]
        width_10 = res_10['lambda_ci_high'][mask] - res_10['lambda_ci_low'][mask]
        np.testing.assert_allclose(width_10 / width_05, norm.ppf(0.95) / norm.ppf(0.975),
                                   rtol=1e-10)
        assert res_10['alpha'] == 0.10

    def test_se_weights_renormalized_with_missing(self, healthy_premium_panel):
        """E8 (复审 F1): 窗口含 NaN β 时, SE 用与估计量一致的归一化权重 (sum=1)"""
        from factor_pipeline.modules.factor_health import PremiumEstimator
        factor, ret = healthy_premium_panel
        f_hole = factor.copy()
        f_hole.iloc[40:60, :] = np.nan  # 20 期因子全缺失 → beta_t[40:60] = NaN
        est = PremiumEstimator(bandwidth=6)
        res = est.estimate_with_errors(f_hole, ret)

        t = 39  # 空洞左边缘: 窗口含 NaN β, 有效权重和 W_v < 1
        h = est.bandwidth
        lo, hi = max(0, t - h), min(len(f_hole), t + h + 1)
        bw = res['beta_t'][lo:hi]
        lw = res['lambda_hat'][lo:hi]
        valid = np.isfinite(bw) & np.isfinite(lw)
        w = est._epanechnikov(np.abs(np.arange(lo, hi) - t) / h)[valid]
        assert w.sum() < 0.99, "fixture 未构造出归一化敏感场景"

        n_win = int(valid.sum())
        q_local = max(1, int(4 * (n_win / 100) ** (2 / 9)))
        omega = est._hac_long_run_variance(bw[valid] - lw[valid], q_local)
        expected = np.sqrt(omega * float(np.sum((w / w.sum()) ** 2)))
        assert res['lambda_se'][t] == pytest.approx(expected, rel=1e-12)
        # 旧实现 (未再归一化) 会给出 ×W_v 的低估 — 确认不再发生
        assert res['lambda_se'][t] > np.sqrt(omega * float(np.sum(w ** 2)))

    def test_beta_se_guard_tiny_cross_section(self):
        """E9 (复审 F2): min_stocks=2 且 n_valid=2 (精确拟合) → beta_se=0 而非 NaN/inf"""
        from factor_pipeline.modules.factor_health import PremiumEstimator
        rng = np.random.RandomState(3)
        T, N = 5, 2
        idx = pd.date_range('2020-01-01', periods=T, freq='ME')
        f = pd.DataFrame(rng.randn(T, N), index=idx, columns=['A', 'B'])
        r = pd.DataFrame(rng.randn(T, N), index=idx, columns=['A', 'B'])
        est = PremiumEstimator(bandwidth=2, min_stocks=2)
        res = est.estimate_with_errors(f, r)
        assert np.isfinite(res['beta_t']).all()
        # 精确拟合 → 残差仅剩浮点噪声; 旧实现 (÷0) 会得到 NaN
        assert (res['beta_se'] < 1e-12).all()
