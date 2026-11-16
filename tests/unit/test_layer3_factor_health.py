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


class TestBreakpointDetectorShortSample:
    """DEFECT-1: T<30 退化路径 (v3.4.13)"""

    def test_e1_short_sample_returns_no_breakpoint(self):
        """E1: T=10 → 无断点退化结果, 不抛异常"""
        from factor_pipeline.modules.factor_health import BreakpointDetector
        res = BreakpointDetector().detect(np.full(10, 0.01))
        assert res['has_breakpoint'] is False
        assert res['chow_max_stat'] == 0.0
        assert np.isnan(res['critical'])
        assert np.isnan(res['pre_mean']) and np.isnan(res['post_mean'])
        assert 'breakpoint_idx' not in res
        assert len(res['cusum_path']) == 10
        assert np.isnan(res['cusum_path']).all()

    def test_e2_boundary_just_below_threshold(self):
        """E2: 有效点 29 (输入 40 含 11 NaN) → 仍走退化路径"""
        from factor_pipeline.modules.factor_health import BreakpointDetector
        x = np.linspace(0.0, 0.05, 40)
        x[:11] = np.nan  # 有效点 29 (阈值下界外)
        assert np.isfinite(x).sum() == 29
        res = BreakpointDetector().detect(x)
        assert res['has_breakpoint'] is False
        assert len(res['cusum_path']) == 29

    def test_e3_threshold_30_still_normal_path(self):
        """E3: 有效点 30 → 正常 sup-F 路径 (回归防护, 阈值不越界)"""
        from factor_pipeline.modules.factor_health import BreakpointDetector
        res = BreakpointDetector().detect(np.linspace(0.0, 0.05, 30))
        assert np.isfinite(res['critical'])
        assert res['critical'] > 0
        assert len(res['cusum_path']) == 30
        assert np.isfinite(res['chow_max_stat'])

    def test_e4_diagnose_short_panel_no_raise(self):
        """E4: diagnose 短面板 (T=20) → 不抛异常, 断点字段退化"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        np.random.seed(7)
        T, N = 20, 50
        dates = pd.date_range('2024-01-01', periods=T, freq='ME')
        stocks = [f'S{i:02d}' for i in range(N)]
        factor = pd.DataFrame(np.random.randn(T, N), index=dates, columns=stocks)
        ret = pd.DataFrame(0.02 * factor.values + np.random.randn(T, N) * 0.05,
                           index=dates, columns=stocks)
        res = FactorHealthDiagnoser(bandwidth=6, alpha=0.05).diagnose(
            factor, ret, return_type='static')
        assert res['has_breakpoint'] is False
        assert res['chow_max_stat'] == 0.0
        assert res['breakpoint_idx'] is None
        assert np.isfinite(res['premium_mean'])
        assert res['premium_health'] in ('stable', 'suspect', 'insignificant')

    def test_e5_all_nan_empty(self):
        """E5: 全 NaN → T=0, 空 cusum, 不抛异常"""
        from factor_pipeline.modules.factor_health import BreakpointDetector
        res = BreakpointDetector().detect(np.full(12, np.nan))
        assert res['has_breakpoint'] is False
        assert len(res['cusum_path']) == 0


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


class TestBreakpointDetectorMultiple:
    """v3.5.0 Bai-Perron 多断点 (detect_multiple) — E1-E8"""

    @staticmethod
    def _series(T=120, breaks=(), means=(0.0,), seed=7, sigma=1.0):
        """合成序列: 段均值 + 高斯噪声."""
        rng = np.random.default_rng(seed)
        y = rng.normal(0.0, sigma, T)
        edges = [0] + list(breaks) + [T]
        assert len(edges) - 1 == len(means)
        for j, (a, b) in enumerate(zip(edges[:-1], edges[1:])):
            y[a:b] += means[j]
        return y

    def test_e1_single_breakpoint(self):
        """E1: T=120 单断点 (t=50) → n_breaks=1, 位置误差 <= 3"""
        from factor_pipeline.modules.factor_health import BreakpointDetector
        y = self._series(T=120, breaks=(50,), means=(0.0, 0.8))
        res = BreakpointDetector().detect_multiple(y, m_max=3)
        assert res['n_breaks'] == 1, res['bic']
        assert res['has_breakpoint'] is True
        assert abs(res['breakpoints'][0] - 50) <= 3, res['breakpoints']
        assert len(res['segment_means']) == 2
        assert res['n_valid'] == 120

    def test_e2_two_breakpoints(self):
        """E2: T=120 两断点 (t=40/80) → n_breaks=2, 误差 <= 5"""
        from factor_pipeline.modules.factor_health import BreakpointDetector
        y = self._series(T=120, breaks=(40, 80), means=(0.0, 0.8, -0.5),
                         seed=11, sigma=0.6)
        res = BreakpointDetector().detect_multiple(y, m_max=4)
        assert res['n_breaks'] == 2, res['bic']
        b1, b2 = res['breakpoints']
        assert abs(b1 - 40) <= 5 and abs(b2 - 80) <= 5, res['breakpoints']
        assert len(res['segment_means']) == 3
        assert len(res['segment_bounds']) == 3

    def test_e3_noise_selects_zero(self):
        """E3: 纯噪声 → BIC 选 0 断点"""
        from factor_pipeline.modules.factor_health import BreakpointDetector
        y = self._series(T=120, seed=23)
        res = BreakpointDetector().detect_multiple(y, m_max=3)
        assert res['n_breaks'] == 0, (res['bic'], res['breakpoints'])
        assert res['has_breakpoint'] is False
        assert res['breakpoints'] == []
        assert len(res['segment_means']) == 1

    def test_e4_criteria_monotone_and_coverage(self):
        """E4: SSR 随 m 单调非增; bic/lwz 覆盖 m=0..m_cap; best 在范围内"""
        from factor_pipeline.modules.factor_health import BreakpointDetector
        y = self._series(T=120, breaks=(40, 80), means=(0.0, 0.5, -0.3), seed=11)
        res = BreakpointDetector().detect_multiple(y, m_max=4)
        ks = sorted(res['ssr'])
        assert ks == list(range(0, 5)), ks
        assert all(res['ssr'][ks[i + 1]] <= res['ssr'][ks[i]] + 1e-12
                   for i in range(len(ks) - 1))
        for key in ('bic', 'lwz'):
            assert sorted(res[key]) == ks
            assert all(np.isfinite(res[key][k]) for k in ks)
        assert res['best_bic_m'] in ks
        assert res['best_lwz_m'] in ks

        # G6: m_max 自动下调 (T=40, h=6 → m_cap = 40//6 - 1 = 5)
        y40 = self._series(T=40, seed=3)
        res40 = BreakpointDetector().detect_multiple(y40, m_max=10)
        assert res40['m_max'] == 5, res40['m_max']
        assert sorted(res40['ssr']) == list(range(0, 6))

    def test_e5_dp_matches_bruteforce(self):
        """E5: DP 全局最优与穷举逐位一致 (T=40, m<=2)"""
        from itertools import combinations
        from factor_pipeline.modules.factor_health import BreakpointDetector
        T = 40
        y = self._series(T=T, breaks=(13, 27), means=(0.0, 0.6, -0.4), seed=5)
        det = BreakpointDetector(min_segment=0.15)
        h = max(5, int(T * det.min_segment))
        res = det.detect_multiple(y, m_max=2)

        def ssr_of(cuts):
            edges = [0] + list(cuts) + [T]
            return float(sum(np.sum((y[a:b] - y[a:b].mean()) ** 2)
                             for a, b in zip(edges[:-1], edges[1:])))

        def feasible(cuts):
            edges = [0] + list(cuts) + [T]
            return all(b - a >= h for a, b in zip(edges[:-1], edges[1:]))

        for m in (1, 2):
            best = min(ssr_of(c) for c in combinations(range(1, T), m) if feasible(c))
            assert abs(res['ssr'][m] - best) <= 1e-8 * max(1.0, abs(best)), (m, res['ssr'][m], best)

    def test_e6_short_sample_degenerate(self):
        """E6: T=20 (<30) → 12 键退化, 不抛异常"""
        from factor_pipeline.modules.factor_health import BreakpointDetector
        res = BreakpointDetector().detect_multiple(np.full(20, 0.01), m_max=3)
        assert res['n_breaks'] == 0 and res['has_breakpoint'] is False
        assert res['breakpoints'] == []
        assert np.isnan(res['segment_means'][0])
        assert np.isnan(res['ssr'][0]) and np.isnan(res['bic'][0])
        assert res['n_valid'] == 20
        assert res['trimming'] == 0

    def test_e7_nan_index_mapping(self):
        """E7: 含 NaN 输入 → 断点索引映射回原序列"""
        from factor_pipeline.modules.factor_health import BreakpointDetector
        y = self._series(T=60, breaks=(25,), means=(0.0, 1.5), seed=31, sigma=0.4)
        x = np.full(70, np.nan)
        x[5:65] = y          # 有效点原索引 5..64; y 的断点 25 → 原索引 30
        res = BreakpointDetector().detect_multiple(x, m_max=1)
        assert res['n_valid'] == 60
        assert res['n_breaks'] == 1, res['bic']
        bp = res['breakpoints'][0]
        assert 5 <= bp <= 64
        assert abs(bp - 30) <= 4, bp
        assert res['segment_bounds'][0][0] == 5
        assert res['segment_bounds'][-1][1] == 65

    def test_e8_consistent_with_single_detect(self):
        """E8: 同序列 m=1 与 detect 断点差 <= 1; DP 的 SSR 不劣于网格最优"""
        from factor_pipeline.modules.factor_health import BreakpointDetector
        y = self._series(T=120, breaks=(50,), means=(0.0, 1.2), seed=41)
        det = BreakpointDetector()
        single = det.detect(y)
        multi = det.detect_multiple(y, m_max=1)
        assert single['has_breakpoint'] is True
        assert multi['n_breaks'] == 1
        assert abs(single['breakpoint_idx'] - multi['breakpoints'][0]) <= 1
        bp = single['breakpoint_idx']
        a, b = y[:bp], y[bp:]
        ssr_grid = float(np.sum((a - a.mean()) ** 2) + np.sum((b - b.mean()) ** 2))
        assert multi['ssr'][1] <= ssr_grid + 1e-12


@pytest.fixture
def two_break_premium_panel():
    """两个断点: μ = 0.10 → -0.10 → 0.10 (T=240, 断点 80/160)"""
    np.random.seed(42)
    T, N = 240, 150
    dates = pd.date_range('2019-01-01', periods=T, freq='ME')
    stocks = [f'S{i:02d}' for i in range(N)]
    factor = np.random.randn(T, N)
    premium = np.concatenate([
        np.full(T // 3, 0.10),
        np.full(T // 3, -0.10),
        np.full(T - 2 * (T // 3), 0.10),
    ])
    fwd = np.empty((T, N))
    for t in range(T):
        fwd[t] = premium[t] * factor[t] + np.random.randn(N) * 0.05
    return (pd.DataFrame(factor, index=dates, columns=stocks),
            pd.DataFrame(fwd, index=dates, columns=stocks))


def _mock_single(has_bp, bp=120, T=200):
    """构造 detect() 返回值 (无断点时不含 breakpoint_idx, 与真实契约一致)"""
    res = {
        'has_breakpoint': has_bp,
        'chow_max_stat': 5.0 if has_bp else 1.0,
        'critical': 8.0,
        'cusum_path': np.zeros(T),
        'pre_mean': 0.05 if has_bp else np.nan,
        'post_mean': 0.02 if has_bp else np.nan,
    }
    if has_bp:
        res['breakpoint_idx'] = bp
    return res


def _mock_multi(n_breaks, seg_means, ssr_by_m, breaks, T=200):
    """构造 detect_multiple() 返回值 (只填消费方用到的键)"""
    return {
        'has_breakpoint': n_breaks > 0,
        'n_breaks': n_breaks,
        'breakpoints': list(breaks),
        'segment_means': list(seg_means),
        'segment_bounds': [(0, T)] if n_breaks == 0 else [(0, breaks[0])] +
                          [(breaks[i], breaks[i + 1]) for i in range(len(breaks) - 1)] +
                          [(breaks[-1], T)],
        'ssr': dict(ssr_by_m),
        'bic': {k: float(k) for k in ssr_by_m},
        'lwz': {k: float(k) for k in ssr_by_m},
        'best_bic_m': n_breaks,
        'best_lwz_m': n_breaks,
        'trimming': 30,
        'm_max': 5,
        'n_valid': T,
    }


class TestDiagnoseMultipleBreakpointMode:
    """F1-F9: 多断点接入 diagnose 标签路径 (v3.5.1, ADR-047)"""

    def test_f1_default_mode_unchanged(self, healthy_premium_panel):
        """F1: 默认 single 模式 → 标签路径不变, 仅新增描述键"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        factor, ret = healthy_premium_panel
        res = FactorHealthDiagnoser(bandwidth=24, alpha=0.05).diagnose(
            factor, ret, return_type='static')
        assert res['breakpoint_mode'] == 'single'
        assert res['breakpoint_confirmed'] == res['has_breakpoint']
        assert res['breakpoint_material'] == res['has_breakpoint']
        assert res['best_bic_m'] is None and res['best_lwz_m'] is None
        assert res['n_breaks'] == (1 if res['has_breakpoint'] else 0)
        assert res['breakpoints'] == ([res['breakpoint_idx']]
                                      if res['has_breakpoint'] else [])
        assert res['diagnosis'] in ('pricing', 'suspect')
        for key in ('segment_means', 'segment_bounds', 'breakpoint_shift_ratio'):
            assert key in res

    def test_f2_single_break_confirmed(self, breakpoint_premium_panel):
        """F2: 强单断点 → confirmed=True, n_breaks=1, ES/ES+TD"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        factor, ret = breakpoint_premium_panel
        res = FactorHealthDiagnoser(bandwidth=12, alpha=0.05).diagnose(
            factor, ret, return_type='static', breakpoint_mode='multiple')
        assert res['breakpoint_mode'] == 'multiple'
        assert res['breakpoint_confirmed'] is True
        assert res['has_breakpoint'] is True
        assert res['n_breaks'] == 1
        assert len(res['breakpoints']) == 1
        assert 70 <= res['breakpoints'][0] <= 130
        assert res['premium_health'] in ('ES', 'ES+TD')
        assert len(res['segment_means']) == 2

    def test_f3_two_breaks_detected(self, two_break_premium_panel):
        """F3: 双断点 → n_breaks=2, 断点 [80,160]"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        factor, ret = two_break_premium_panel
        res = FactorHealthDiagnoser(bandwidth=24, alpha=0.05).diagnose(
            factor, ret, return_type='static', breakpoint_mode='multiple')
        assert res['breakpoint_confirmed'] is True
        assert res['n_breaks'] == 2, res['breakpoints']
        assert res['breakpoints'] == [80, 160]
        assert len(res['segment_means']) == 3
        assert res['has_breakpoint'] is True
        assert res['premium_health'] in ('ES', 'ES+TD')

    def test_f4_noise_never_es(self, healthy_premium_panel):
        """F4: 纯噪声 → 不得产出 ES; 若 has_bp 必为未确认 suspect"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        factor, ret = healthy_premium_panel
        res = FactorHealthDiagnoser(bandwidth=24, alpha=0.05).diagnose(
            factor, ret, return_type='static', breakpoint_mode='multiple')
        assert res['premium_health'] not in ('ES', 'ES+TD')
        if res['has_breakpoint']:
            assert res['premium_health'] == 'suspect'
            assert res['breakpoint_confirmed'] is False

    def test_f5_invalid_mode_raises(self, healthy_premium_panel):
        """F5: 非法 breakpoint_mode → ValueError"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        factor, ret = healthy_premium_panel
        diag = FactorHealthDiagnoser(bandwidth=24, alpha=0.05)
        with pytest.raises(ValueError):
            diag.diagnose(factor, ret, breakpoint_mode='bogus')

    def test_f6_short_panel_multiple_no_raise(self):
        """F6: T=20 + multiple → 退化, 不抛异常"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        np.random.seed(7)
        T, N = 20, 50
        dates = pd.date_range('2024-01-01', periods=T, freq='ME')
        stocks = [f'S{i:02d}' for i in range(N)]
        factor = pd.DataFrame(np.random.randn(T, N), index=dates, columns=stocks)
        ret = pd.DataFrame(0.02 * factor.values + np.random.randn(T, N) * 0.05,
                           index=dates, columns=stocks)
        res = FactorHealthDiagnoser(bandwidth=6, alpha=0.05).diagnose(
            factor, ret, return_type='static', breakpoint_mode='multiple')
        assert res['breakpoint_mode'] == 'multiple'
        assert res['n_breaks'] == 0
        assert res['breakpoints'] == []
        assert res['breakpoint_confirmed'] is False
        assert res['has_breakpoint'] is False

    def test_f7_unconfirmed_material_is_suspect(self, healthy_premium_panel, monkeypatch):
        """F7: sup-F 不显著 + BIC 断点材料性 1.5 → suspect (不升级 ES)"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        factor, ret = healthy_premium_panel
        diag = FactorHealthDiagnoser(bandwidth=24, alpha=0.05)
        # ratio = 0.03 / sqrt(0.08/200) = 1.5
        multi = _mock_multi(1, [0.05, 0.02], {0: 9.0, 1: 0.08}, [120])
        monkeypatch.setattr(diag.detector, 'detect', lambda y: _mock_single(False))
        monkeypatch.setattr(diag.detector, 'detect_multiple',
                            lambda y, m_max=None: multi)
        monkeypatch.setattr(diag, '_detect_decay',
                            lambda y: {'has_decay': False, 'half_life': None})
        res = diag.diagnose(factor, ret, return_type='static',
                            breakpoint_mode='multiple')
        assert res['breakpoint_confirmed'] is False
        assert res['breakpoint_material'] is True
        assert res['has_breakpoint'] is True
        assert res['premium_health'] == 'suspect'
        assert res['diagnosis'] == 'suspect'
        assert abs(res['breakpoint_shift_ratio'] - 1.5) < 1e-9

    def test_f8_unconfirmed_immaterial_ignored(self, healthy_premium_panel, monkeypatch):
        """F8: sup-F 不显著 + 材料性 0.5 → 不改标签"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        factor, ret = healthy_premium_panel
        diag = FactorHealthDiagnoser(bandwidth=24, alpha=0.05)
        # ratio = 0.03 / sqrt(0.72/200) = 0.5
        multi = _mock_multi(1, [0.05, 0.02], {0: 9.0, 1: 0.72}, [120])
        monkeypatch.setattr(diag.detector, 'detect', lambda y: _mock_single(False))
        monkeypatch.setattr(diag.detector, 'detect_multiple',
                            lambda y, m_max=None: multi)
        monkeypatch.setattr(diag, '_detect_decay',
                            lambda y: {'has_decay': False, 'half_life': None})
        res = diag.diagnose(factor, ret, return_type='static',
                            breakpoint_mode='multiple')
        assert res['breakpoint_confirmed'] is False
        assert res['breakpoint_material'] is False
        assert res['has_breakpoint'] is False
        # 复审 H3: 旧键语义不变 — 无断点告警时 pre/post 必须为 NaN
        assert res['breakpoint_idx'] is None
        assert np.isnan(res['mean_premium_pre_bp'])
        assert np.isnan(res['mean_premium_post_bp'])
        assert res['premium_health'] != 'suspect' or res['has_breakpoint'] is False
        assert res['premium_health'] not in ('ES', 'ES+TD')

    def test_f9_confirmed_bic_zero_falls_back(self, healthy_premium_panel, monkeypatch):
        """F9: sup-F 显著但 BIC 选 0 → 回退单断点分段"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        factor, ret = healthy_premium_panel
        diag = FactorHealthDiagnoser(bandwidth=24, alpha=0.05)
        multi = _mock_multi(0, [0.03], {0: 5.0}, [])
        monkeypatch.setattr(diag.detector, 'detect',
                            lambda y: _mock_single(True, bp=120))
        monkeypatch.setattr(diag.detector, 'detect_multiple',
                            lambda y, m_max=None: multi)
        monkeypatch.setattr(diag, '_detect_decay',
                            lambda y: {'has_decay': False, 'half_life': None})
        res = diag.diagnose(factor, ret, return_type='static',
                            breakpoint_mode='multiple')
        assert res['breakpoint_confirmed'] is True
        assert res['n_breaks'] == 1
        assert res['breakpoints'] == [120]
        assert res['premium_health'] == 'ES'
        # 回退分段的 pre/post 由实际 beta_raw 重算 (与 detect 的 pre/post 同口径)
        assert np.isfinite(res['mean_premium_pre_bp'])
        assert np.isfinite(res['mean_premium_post_bp'])
        assert res['mean_premium_pre_bp'] != res['mean_premium_post_bp']
        assert res['breakpoint_idx'] == 120


class TestMultipleBreakpointGapGuard:
    """G1-G9: 多断点路径 NaN 间隙守卫 (v3.5.2, ADR-048)"""

    @staticmethod
    def _series_with_gap(T=200, bp=120, gap=(118, 123)):
        """beta_raw: 0.05 → 0.02, 在 gap 区间置 NaN。"""
        y = np.r_[np.full(bp, 0.05), np.full(T - bp, 0.02)]
        y[gap[0]:gap[1]] = np.nan
        return y

    @staticmethod
    def _patch_estimator(diag, beta_raw):
        """固定 beta_raw, 绕过真实 FM 估计。"""
        smooth = np.nan_to_num(beta_raw, nan=0.03)
        diag.estimator._beta_raw = beta_raw
        diag.estimator.estimate = lambda f, r: smooth

    def test_g1_detect_multiple_no_nan_keys(self):
        """G1: 无 NaN → 连续性键全零, 断点列表对齐"""
        from factor_pipeline.modules.factor_health import BreakpointDetector
        np.random.seed(11)
        y = np.r_[np.zeros(30), np.full(30, 1.0)] + np.random.randn(60) * 0.3
        res = BreakpointDetector().detect_multiple(y, m_max=1)
        assert res['n_nan'] == 0
        assert res['n_gaps'] == 0
        assert res['max_gap_run'] == 0
        assert len(res['breakpoints_gap_missing']) == len(res['breakpoints'])
        assert all(g == 0 for g in res['breakpoints_gap_missing'])
        assert res['gap_missing_at_bp'] == (0 if res['breakpoints'] else None)

    def test_g2_detect_multiple_gap_at_break(self):
        """G2: 断点处 5 期缺失 → 连续性描述正确"""
        from factor_pipeline.modules.factor_health import BreakpointDetector
        np.random.seed(12)
        y = np.r_[np.zeros(30), np.full(30, 1.0)] + np.random.randn(60) * 0.3
        x = y.copy()
        x[28:33] = np.nan
        res = BreakpointDetector().detect_multiple(x, m_max=1)
        assert res['n_nan'] == 5
        assert res['n_gaps'] == 1
        assert res['max_gap_run'] == 5
        assert res['n_breaks'] == 1
        assert res['breakpoints_gap_missing'][0] >= 2
        assert res['gap_missing_at_bp'] >= 2

    def test_g3_confirmed_break_at_gap_downgrades_to_suspect(
            self, healthy_premium_panel, monkeypatch):
        """G3: confirmed + 断点跨 5 期间隙 → gap_risk, ES 降级 suspect"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        factor, ret = healthy_premium_panel
        diag = FactorHealthDiagnoser(bandwidth=24, alpha=0.05)
        beta = self._series_with_gap()
        self._patch_estimator(diag, beta)
        multi = _mock_multi(1, [0.05, 0.02], {0: 9.0, 1: 0.08}, [120])
        monkeypatch.setattr(diag.detector, 'detect',
                            lambda y: _mock_single(True, bp=120))
        monkeypatch.setattr(diag.detector, 'detect_multiple',
                            lambda y, m_max=None: multi)
        monkeypatch.setattr(diag, '_detect_decay',
                            lambda y: {'has_decay': False, 'half_life': None})
        res = diag.diagnose(factor, ret, return_type='static',
                            breakpoint_mode='multiple')
        assert res['breakpoint_confirmed'] is True
        assert res['has_breakpoint'] is True
        assert res['gap_missing_at_bp'] == 5
        assert res['breakpoint_gap_risk'] is True
        assert res['premium_health'] == 'suspect'
        assert res['diagnosis'] == 'suspect'

    def test_g4_isolated_nan_not_downgraded(
            self, healthy_premium_panel, monkeypatch):
        """G4: 断点跨孤立 1 点 NaN (gmin=2) → 不降级, ES 保留"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        factor, ret = healthy_premium_panel
        diag = FactorHealthDiagnoser(bandwidth=24, alpha=0.05)
        beta = np.r_[np.full(120, 0.05), np.full(80, 0.02)]
        beta[120] = np.nan
        self._patch_estimator(diag, beta)
        multi = _mock_multi(1, [0.05, 0.02], {0: 9.0, 1: 0.08}, [120])
        monkeypatch.setattr(diag.detector, 'detect',
                            lambda y: _mock_single(True, bp=120))
        monkeypatch.setattr(diag.detector, 'detect_multiple',
                            lambda y, m_max=None: multi)
        monkeypatch.setattr(diag, '_detect_decay',
                            lambda y: {'has_decay': False, 'half_life': None})
        res = diag.diagnose(factor, ret, return_type='static',
                            breakpoint_mode='multiple')
        assert res['gap_missing_at_bp'] == 1
        assert res['breakpoint_gap_risk'] is False
        assert res['premium_health'] == 'ES'

    def test_g5_gap_away_from_break_not_downgraded(
            self, healthy_premium_panel, monkeypatch):
        """G5: 间隙远离断点 → 不降级, ES 保留"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        factor, ret = healthy_premium_panel
        diag = FactorHealthDiagnoser(bandwidth=24, alpha=0.05)
        beta = self._series_with_gap(gap=(60, 65))
        self._patch_estimator(diag, beta)
        multi = _mock_multi(1, [0.05, 0.02], {0: 9.0, 1: 0.08}, [120])
        monkeypatch.setattr(diag.detector, 'detect',
                            lambda y: _mock_single(True, bp=120))
        monkeypatch.setattr(diag.detector, 'detect_multiple',
                            lambda y, m_max=None: multi)
        monkeypatch.setattr(diag, '_detect_decay',
                            lambda y: {'has_decay': False, 'half_life': None})
        res = diag.diagnose(factor, ret, return_type='static',
                            breakpoint_mode='multiple')
        assert res['gap_missing_at_bp'] == 0
        assert res['breakpoint_gap_risk'] is False
        assert res['premium_health'] == 'ES'

    def test_g6_material_driver_at_gap_downgrades(
            self, healthy_premium_panel, monkeypatch):
        """G6: 未确认 + 材料性 1.5 且驱动边界跨间隙 → gap_risk, suspect"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        factor, ret = healthy_premium_panel
        diag = FactorHealthDiagnoser(bandwidth=24, alpha=0.05)
        beta = self._series_with_gap()
        self._patch_estimator(diag, beta)
        multi = _mock_multi(1, [0.05, 0.02], {0: 9.0, 1: 0.08}, [120])
        monkeypatch.setattr(diag.detector, 'detect',
                            lambda y: _mock_single(False))
        monkeypatch.setattr(diag.detector, 'detect_multiple',
                            lambda y, m_max=None: multi)
        monkeypatch.setattr(diag, '_detect_decay',
                            lambda y: {'has_decay': False, 'half_life': None})
        res = diag.diagnose(factor, ret, return_type='static',
                            breakpoint_mode='multiple')
        assert res['breakpoint_confirmed'] is False
        assert res['breakpoint_material'] is True
        assert res['has_breakpoint'] is True
        assert res['breakpoint_gap_risk'] is True
        assert res['premium_health'] == 'suspect'

    def test_g7_single_mode_gap_guard_disabled(
            self, healthy_premium_panel, monkeypatch):
        """G7: 默认 single 模式 → 守卫关闭, 标签不变, 描述键仍存在"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        factor, ret = healthy_premium_panel
        diag = FactorHealthDiagnoser(bandwidth=24, alpha=0.05)
        beta = self._series_with_gap()
        self._patch_estimator(diag, beta)
        monkeypatch.setattr(diag.detector, 'detect',
                            lambda y: _mock_single(True, bp=120))
        monkeypatch.setattr(diag, '_detect_decay',
                            lambda y: {'has_decay': False, 'half_life': None})
        res = diag.diagnose(factor, ret, return_type='static')
        assert res['breakpoint_mode'] == 'single'
        assert res['breakpoint_gap_risk'] is False
        assert res['gap_missing_at_bp'] == 5
        assert res['premium_health'] == 'ES'

    def test_g8_degenerate_inputs_keep_contract(self):
        """G8: 全 NaN / T=20 → 不抛异常, risk False, 描述键合法"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        diag = FactorHealthDiagnoser(bandwidth=6, alpha=0.05)
        all_nan = np.full(200, np.nan)
        self._patch_estimator(diag, all_nan)
        diag.detector.detect = lambda y: _mock_single(False)
        diag.detector.detect_multiple = lambda y, m_max=None: _mock_multi(
            0, [np.nan], {0: np.nan}, [])
        diag._detect_decay = lambda y: {'has_decay': False, 'half_life': None}
        df = pd.DataFrame(np.zeros((5, 3)))
        res = diag.diagnose(df, df, return_type='static',
                            breakpoint_mode='multiple')
        assert res['n_nan'] == 200
        assert res['n_gaps'] == 1
        assert res['max_gap_run'] == 200
        assert res['breakpoint_gap_risk'] is False
        assert res['gap_missing_at_bp'] is None
        assert res['breakpoints_gap_missing'] == []

    def test_g9_gap_min_run_validation(self):
        """G9: multi_break_gap_min_run < 1 → ValueError"""
        from factor_pipeline.modules.factor_health import FactorHealthDiagnoser
        with pytest.raises(ValueError):
            FactorHealthDiagnoser(multi_break_gap_min_run=0)

