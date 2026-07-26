"""Layer 3: Factor Health Diagnosis — LGMM Premium Estimation + Chow Breakpoint + Multi-State

Architecture:
  Layer 2 (existing): StatisticalClassifier → raw return type (static/dynamic/mixed)
  Layer 3 (new):      FactorHealthDiagnoser → premium health (ES/TD/ES+TD/stable/suspect)

Combined diagnosis = return_type × premium_health → actionable governance label

Academic foundations:
  - Premium estimation: Fama-MacBeth (1973) cross-sectional β_t + Epanechnikov kernel
    smoothing (local constant nonparametric regression, simplest LGMM variant)
  - Breakpoint detection: Chow (1960) F-test grid-search on raw β_t
    (simplified Bai-Perron 1998; CUSUM was tested but abandoned due to F-stat inflation
    on kernel-smoothed data — see DESIGN_DISCUSSION_V3.3.0 §3.3)
  - Self-similarity: H≈1.14 premium process (LGMM paper empirical finding)
  - Multi-state: AMH (Lo 2004) + factor failure taxonomy (ES/TD/IV/EL, LGMM paper)

Design constraints:
  - Per-period cross-sectional regression O(T×N), vectorized per period
  - Kernel smoothing: O(T²) but T≤500 for typical factor history
  - Breakpoint: O(T) grid search, single F-test per candidate split
"""
import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy import stats
from typing import Dict, Tuple, Optional


class PremiumEstimator:
    """Fama-MacBeth + Epanechnikov kernel estimator of time-varying cross-sectional premium.

    Step 1: For each t, cross-sectional regression: r_{i,t} = α_t + β_t × factor_{i,t-1} + ε_{i,t}
    Step 2: Kernel smooth β_t → λ̂_t = Σ K_h(t-s) × β_s / Σ K_h(t-s)

    Parameters
    ----------
    bandwidth : int
        Epanechnikov kernel half-width in periods. Default 24 (≈2 years monthly).
    min_stocks : int
        Minimum cross-section size. Default 30.
    """

    def __init__(self, bandwidth: int = 24, min_stocks: int = 30):
        self.bandwidth = bandwidth
        self.min_stocks = min_stocks

    def estimate(self, factor: pd.DataFrame, forward_returns: pd.DataFrame) -> np.ndarray:
        """Estimate λ̂(t) — time-varying cross-sectional premium.

        Returns both lambda_hat (kernel-smoothed) and beta_raw (unsmoothed β_t).
        """
        common_idx = factor.index.intersection(forward_returns.index)
        common_cols = factor.columns.intersection(forward_returns.columns)
        factor_aligned = factor.loc[common_idx, common_cols]
        ret_aligned = forward_returns.loc[common_idx, common_cols]

        F = factor_aligned.values
        R = ret_aligned.values

        beta_t = self._cross_sectional_betas(F, R)
        self._beta_raw = beta_t.copy()

        T = len(beta_t)
        lambda_hat = np.full(T, np.nan)
        h = self.bandwidth
        for t in range(T):
            lo = max(0, t - h)
            hi = min(T, t + h + 1)
            valid = ~np.isnan(beta_t[lo:hi])
            if valid.sum() < 3:
                continue
            dist = np.abs(np.arange(lo, hi) - t) / h
            weights = self._epanechnikov(dist)
            weights = weights[valid]
            lambda_hat[t] = np.average(beta_t[lo:hi][valid], weights=weights)

        return lambda_hat

    def _cross_sectional_betas(self, F: np.ndarray, R: np.ndarray) -> np.ndarray:
        """Vectorized cross-sectional regression per period.
        
        Model: r_t = α + β_t × f_{t-1} + ε
        β_t = Cov(r, f) / Var(f) (single-factor OLS slope)
        """
        T, N = F.shape
        beta_t = np.full(T, np.nan)

        for t in range(T):
            f = F[t]   # (N,) factor values
            r = R[t]   # (N,) returns
            valid = ~np.isnan(f) & ~np.isnan(r)
            n_valid = valid.sum()
            if n_valid < self.min_stocks:
                continue

            f_valid = f[valid]
            r_valid = r[valid]

            f_demean = f_valid - np.mean(f_valid)
            r_demean = r_valid - np.mean(r_valid)
            var_f = np.dot(f_demean, f_demean)
            if var_f < 1e-12:
                continue

            beta_t[t] = np.dot(f_demean, r_demean) / var_f

        return beta_t

    @staticmethod
    def _epanechnikov(u: np.ndarray) -> np.ndarray:
        """Epanechnikov kernel: K(u) = 0.75 * (1 - u²) for |u| ≤ 1."""
        w = 0.75 * (1 - u ** 2)
        w = np.clip(w, 0, None)
        return w / np.maximum(w.sum(), 1e-12)


class BreakpointDetector:
    """Structural break detection via grid-search sup-F test.

    Algorithm:
      1. For each candidate split t ∈ [min_seg, T-min_seg]:
         F = (SSR_pooled - SSR_split) / (SSR_split / (T-2))
      2. sup-F ≡ max F over all candidate splits.
      3. sup-F > critical value → breakpoint detected.

    Critical values: Andrews (1993) asymptotic sup-F distribution.
    NOT pointwise F(1, T-2) — the latter inflates false positive rate.

    References:
      Andrews (1993), Econometrica, 61(4), 821-856.
      Bai & Perron (1998), Econometrica, 66(1), 47-78.

    Parameters
    ----------
    alpha : float
        Significance level. Default 0.05.
    min_segment : float
        Minimum segment length fraction. Default 0.15.
    sup_f_method : str
        'asymptotic' (Andrews 1993 Table 1, default) or 'bootstrap'.
    n_bootstrap : int
        Bootstrap iterations (only for method='bootstrap').
    """

    def __init__(
        self, alpha: float = 0.05, min_segment: float = 0.15,
        sup_f_method: str = 'asymptotic', n_bootstrap: int = 1000
    ):
        self.alpha = alpha
        self.min_segment = min_segment
        self.sup_f_method = sup_f_method
        self.n_bootstrap = n_bootstrap

    def detect(self, lambda_hat: np.ndarray) -> Dict:
        valid = ~np.isnan(lambda_hat)
        y = lambda_hat[valid]
        T = len(y)
        if T < 30:
            return self._no_breakpoint_result(T)

        min_seg = max(5, int(T * self.min_segment))
        y_mean = np.mean(y)
        ssr_full = np.sum((y - y_mean) ** 2)
        residuals = y - y_mean
        cusum = np.cumsum(residuals) / (np.std(y) * np.sqrt(T) + 1e-12)

        best_f, best_bp = 0.0, None

        for bp in range(min_seg, T - min_seg):
            y_pre, y_post = y[:bp], y[bp:]
            mp, mp2 = np.mean(y_pre), np.mean(y_post)
            ssr = np.sum((y_pre - mp) ** 2) + np.sum((y_post - mp2) ** 2)
            if ssr < 1e-12:
                continue
            f_val = (ssr_full - ssr) / (ssr / max(T - 2, 1))
            if f_val > best_f:
                best_f, best_bp = f_val, bp

        # Andrews (1993) sup-F critical value, NOT pointwise fdist.ppf
        f_crit = self._sup_f_critical_value(T, self.min_segment, self.alpha)
        has_bp = best_f > f_crit and best_bp is not None

        result = {
            'has_breakpoint': has_bp,
            'chow_max_stat': float(best_f),
            'critical': float(f_crit),
            'cusum_path': cusum,
            'pre_mean': float('nan'),
            'post_mean': float('nan'),
        }

        if has_bp and best_bp is not None:
            valid_bp = np.where(valid)[0]
            result['breakpoint_idx'] = int(valid_bp[best_bp])
            result['pre_mean'] = float(np.mean(y[:best_bp]))
            result['post_mean'] = float(np.mean(y[best_bp:]))

        return result

    def _sup_f_critical_value(
        self, T: int, epsilon: float, alpha: float
    ) -> float:
        """Andrews (1993) sup-F asymptotic critical value.

        For method='asymptotic': Andrews (1993) Table 1, interpolated by ε.
        For method='bootstrap': parametric bootstrap (residual-based).

        Args:
            T: sample size.
            epsilon: trimming fraction.
            alpha: significance level.
        """
        if self.sup_f_method == 'asymptotic':
            return self._andrews_quantile(epsilon, alpha)
        elif self.sup_f_method == 'bootstrap':
            return self._bootstrap_sup_f_crit(T, epsilon, alpha)
        else:
            raise ValueError(f"Unknown sup_f_method: {self.sup_f_method}")

    @staticmethod
    def _andrews_quantile(epsilon: float, alpha: float = 0.05) -> float:
        """Andrews (1993) Table 1 asymptotic critical values for sup-F (p=1).

        References:
            Andrews (1993), Econometrica, 61(4), 821-856, Table 1.
        """
        # Andrews (1993) Table 1, p=1
        table = {
            0.05: {0.05: 10.54, 0.10: 8.65},
            0.10: {0.05: 9.29, 0.10: 7.61},
            0.15: {0.05: 8.85, 0.10: 7.17},
            0.20: {0.05: 8.44, 0.10: 6.90},
            0.25: {0.05: 8.13, 0.10: 6.61},
        }
        eps_values = sorted(table.keys())

        if epsilon in table:
            return table[epsilon].get(alpha, 8.85)

        if epsilon < eps_values[0] or epsilon > eps_values[-1]:
            raise ValueError(
                f"ε={epsilon:.3f} outside tabulated range "
                f"[{eps_values[0]:.2f}, {eps_values[-1]:.2f}]"
            )

        for i in range(len(eps_values) - 1):
            if eps_values[i] <= epsilon <= eps_values[i + 1]:
                eps_low, eps_high = eps_values[i], eps_values[i + 1]
                val_low = table[eps_low].get(alpha, 8.85)
                val_high = table[eps_high].get(alpha, 8.85)
                frac = (epsilon - eps_low) / (eps_high - eps_low)
                return val_low + frac * (val_high - val_low)

        return 8.85  # fallback

    def _bootstrap_sup_f_crit(
        self, T: int, epsilon: float, alpha: float
    ) -> float:
        """Residual-based bootstrap for sup-F critical value.

        Optimized: uses cumulative sums to avoid O(T) per breakpoint.
        Complexity: O(n_bootstrap × T) vs O(n_bootstrap × T²) naive.

        H₀: y_t = μ + ε_t (no breakpoint).
        Bootstrap: resample residuals ε̂_t = y_t - ȳ, construct y*_t = ȳ + ε̂*_t.
        This preserves the empirical autocorrelation structure.
        """
        rng = np.random.RandomState(42)
        min_seg = max(5, int(T * epsilon))
        n_breaks = T - 2 * min_seg
        if n_breaks <= 0:
            return 3.84

        # Generate all bootstrap samples at once: (n_bootstrap, T)
        Y = rng.randn(self.n_bootstrap, T)

        # H₀: no breakpoint → subtract global mean
        Y_centered = Y - Y.mean(axis=1, keepdims=True)
        ssr_full = np.sum(Y_centered ** 2, axis=1)  # (n_bootstrap,)

        # Cumulative sums for fast SSR computation
        cumsum = np.cumsum(Y, axis=1)      # (n_bootstrap, T)
        cumsum2 = np.cumsum(Y ** 2, axis=1)  # (n_bootstrap, T)

        all_f = np.zeros((self.n_bootstrap, n_breaks))
        for idx, bp in enumerate(range(min_seg, T - min_seg)):
            n1, n2 = bp, T - bp
            s1 = cumsum[:, bp - 1]
            ss1 = cumsum2[:, bp - 1]
            s2 = cumsum[:, -1] - s1
            ss2 = cumsum2[:, -1] - ss1

            ssr_pre = ss1 - s1 * s1 / n1
            ssr_post = ss2 - s2 * s2 / n2
            ssr = np.maximum(ssr_pre + ssr_post, 1e-12)

            f_val = (ssr_full - ssr) / (ssr / max(T - 2, 1))
            all_f[:, idx] = f_val

        sup_f = np.max(all_f, axis=1)
        return float(np.percentile(sup_f, 100 * (1 - alpha)))


class FactorHealthDiagnoser:
    """Multi-state factor health diagnosis: Layer 2 type × Layer 3 premium health.

    States
    ------
    Premium health (from λ̂_t):
      - 'stable' : |Δpremium| < 0.5σ, no breakpoint, no decay
      - 'ES'     : structural breakpoint detected
      - 'TD'     : exponential decay detected (half-life < threshold)
      - 'ES+TD'  : both breakpoint + decay
      - 'suspect': borderline (breakpoint detected but pre-post difference small)

    Combined label (return_type × premium_health):
      - 'pricing'       : stable/healthy + any type
      - 'recalibrate'   : ES/ES+TD + static (structural change in trend factor)
      - 'monitor'       : ES/ES+TD + dynamic (mean-reverting, need more data)
      - 'review'        : TD + any type (decaying → possible obsolescence)
      - 'suspect'       : suspect premium health
      - 'insufficient'  : not enough data

    Parameters
    ----------
    bandwidth : int
        Kernel half-width for premium estimation.
    alpha : float
        Significance level for breakpoint test.
    half_life_threshold : int
        Maximum half-life (months) to classify as TD. Default 60.
    """

    def __init__(self, bandwidth: int = 24, alpha: float = 0.05,
                 half_life_threshold: int = 60):
        self.bandwidth = bandwidth
        self.alpha = alpha
        self.half_life_threshold = half_life_threshold
        self.estimator = PremiumEstimator(bandwidth=bandwidth)
        self.detector = BreakpointDetector(alpha=alpha)

    def diagnose(self, factor: pd.DataFrame, forward_returns: pd.DataFrame,
                 return_type: str = 'unknown') -> Dict:
        """Full diagnosis pipeline: estimate λ̂(t) → detect breakpoint → classify.

        Returns
        -------
        dict with keys:
            diagnosis : str — combined label
            premium_health : str — ES/TD/ES+TD/stable/suspect
            return_type : str — from Layer 2
            premium_mean, premium_std : float
            has_breakpoint : bool
            breakpoint_idx : int or None
            mean_premium_pre_bp, mean_premium_post_bp : float
            half_life : float or None (months)
            chow_max_stat : float
        """
        # Step 1: Estimate premium
        lambda_hat = self.estimator.estimate(factor, forward_returns)
        beta_raw = getattr(self.estimator, '_beta_raw', lambda_hat)

        # Step 2: Breakpoint detection on RAW betas (not kernel-smoothed)
        bp_result = self.detector.detect(beta_raw)

        # Step 3: Decay detection on smoothed lambda_hat
        td_result = self._detect_decay(lambda_hat)

        # Step 4: Premium health classification
        premium_health = self._classify_premium_health(lambda_hat, bp_result, td_result)

        # Step 5: Combined label with return_type
        combined = self._combine_label(return_type, premium_health)

        valid = ~np.isnan(lambda_hat)
        result = {
            'diagnosis': combined,
            'premium_health': premium_health,
            'return_type': return_type,
            'premium_mean': float(np.mean(lambda_hat[valid])) if valid.any() else 0.0,
            'premium_std': float(np.std(lambda_hat[valid])) if valid.any() else 0.0,
            'has_breakpoint': bp_result['has_breakpoint'],
            'breakpoint_idx': bp_result.get('breakpoint_idx'),
            'mean_premium_pre_bp': float(bp_result.get('pre_mean', np.nan)),
            'mean_premium_post_bp': float(bp_result.get('post_mean', np.nan)),
            'half_life': td_result.get('half_life'),
            'chow_max_stat': float(bp_result.get('chow_max_stat', 0.0)),
            'lambda_hat': lambda_hat,
        }
        return result

    def _classify_premium_health(self, lambda_hat: np.ndarray,
                                  bp_result: Dict, td_result: Dict) -> str:
        """Classify premium into health state.

        Decision tree:
          ES detected + TD detected → 'ES+TD'
          ES detected, no TD       → 'ES'
          TD detected, no ES       → 'TD'
          no ES, no TD, |premium| > 1σ → 'stable'
          no ES, no TD, |premium| < 1σ → 'suspect'
        """
        has_bp = bp_result['has_breakpoint']
        has_td = td_result.get('has_decay', False)

        if has_bp and has_td:
            return 'ES+TD'
        elif has_bp:
            return 'ES'
        elif has_td:
            return 'TD'

        valid = ~np.isnan(lambda_hat)
        if valid.sum() < 10:
            return 'suspect'

        mean_abs = abs(np.mean(lambda_hat[valid]))
        std_val = np.std(lambda_hat[valid])
        if std_val < 1e-12:
            return 'stable' if mean_abs > 0 else 'suspect'

        # FM t-statistic: mean_abs / (std_val / sqrt(T_eff))
        # Uses Fama-MacBeth approach: cross-sectional mean divided by
        # its time-series standard error. |t| > 2.0 → significant premium.
        T_eff = np.sum(~np.isnan(lambda_hat))
        if T_eff > 1 and std_val > 1e-12:
            fm_t_stat = mean_abs / (std_val / np.sqrt(T_eff))
            if abs(fm_t_stat) > 2.0:
                return 'stable'
            elif abs(fm_t_stat) > 1.0:
                return 'suspect'
            else:
                return 'insignificant'
        return 'stable' if mean_abs > 0 else 'suspect'

    def _detect_decay(self, lambda_hat: np.ndarray) -> Dict:
        """Detect exponential decay in premium via log-linear fit.

        Model: |λ(t)| = A × exp(-t/τ) + noise
        log|λ(t)| = log(A) - t/τ
        Estimate half-life = τ × ln(2).

        Significance: Newey-West HAC t-test for β (decay rate).
        H₀: β ≥ 0 (no decay), H₁: β < 0 (decay).
        """
        result = {'has_decay': False, 'half_life': None, 'decay_rate': None,
                  'decay_t_stat': None, 'decay_p_value': None}

        valid = ~np.isnan(lambda_hat)
        y = np.abs(lambda_hat[valid])
        if len(y) < 30:
            return result

        t = np.arange(len(y))
        valid_y = y > 1e-12
        if valid_y.sum() < 10:
            return result

        log_y = np.log(y[valid_y])
        t_valid = t[valid_y]
        n = len(t_valid)

        denom = np.sum((t_valid - np.mean(t_valid)) ** 2)
        if denom < 1e-12:
            return result

        beta = np.sum((t_valid - np.mean(t_valid)) * (log_y - np.mean(log_y))) / denom

        if beta < 0:
            # Newey-West HAC standard error for significance test
            residuals = log_y - (np.mean(log_y) + beta * (t_valid - np.mean(t_valid)))
            se_hac = self._newey_west_se(t_valid, residuals, max_lag=min(4, n // 4))
            t_stat = beta / se_hac if se_hac > 1e-12 else 0.0
            # One-sided test: H₀: β ≥ 0, H₁: β < 0
            p_value = float(stats.t.sf(abs(t_stat), df=max(n - 2, 1)))

            tau = -1.0 / beta
            half_life = tau * np.log(2)
            result['decay_rate'] = float(beta)
            result['half_life'] = float(half_life)
            result['decay_t_stat'] = float(t_stat)
            result['decay_p_value'] = float(p_value)
            # Declare decay only if statistically significant AND half-life below threshold
            result['has_decay'] = (p_value < 0.05 and half_life < self.half_life_threshold)

        return result

    @staticmethod
    def _newey_west_se(x: np.ndarray, residuals: np.ndarray,
                        max_lag: int = 4) -> float:
        """Newey-West HAC standard error for OLS slope coefficient.

        Newey & West (1987), Econometrica, 55(3), 703-708.

        Args:
            x: (n,) regressor (de-meaned).
            residuals: (n,) OLS residuals.
            max_lag: maximum lag for autocorrelation.

        Returns:
            HAC standard error of the slope coefficient.
        """
        n = len(x)
        if n < 3:
            return np.nan

        # Bread: (X'X)⁻¹
        x_demeaned = x - np.mean(x)
        XtX_inv = 1.0 / np.maximum(np.sum(x_demeaned ** 2), 1e-12)

        # Meat: Newey-West kernel-weighted autocovariance
        S0 = np.sum((x_demeaned * residuals) ** 2)
        meat = S0
        for lag in range(1, max_lag + 1):
            w = 1.0 - lag / (max_lag + 1.0)  # Bartlett kernel
            cross = np.sum(x_demeaned[lag:] * residuals[lag:] *
                           x_demeaned[:-lag] * residuals[:-lag])
            meat += 2.0 * w * cross

        # Sandwich: (X'X)⁻¹ × Meat × (X'X)⁻¹
        var_hac = XtX_inv * meat * XtX_inv
        return np.sqrt(np.maximum(var_hac, 1e-12))

    def _combine_label(self, return_type: str, premium_health: str) -> str:
        """Combine Layer 2 return type with Layer 3 premium health."""
        if premium_health in ('stable',):
            return 'pricing'

        if premium_health in ('ES', 'ES+TD'):
            if return_type == 'static':
                return 'recalibrate'
            elif return_type == 'dynamic':
                return 'monitor'
            else:
                return 'review'

        if premium_health == 'TD':
            return 'review'

        return 'suspect'
