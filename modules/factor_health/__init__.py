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
    """Structural break detection via grid-search Chow-type F-test (simplified Bai-Perron).

    Algorithm:
      1. For each candidate split t ∈ [min_seg, T-min_seg]:
         F = (SSR_pooled - SSR_split) / (SSR_split / (T-2))
      2. max F > F_crit(α, 1, T-2) × Bonferroni → breakpoint at argmax F.

    Parameters
    ----------
    alpha : float
        Significance level. Default 0.05.
    min_segment : float
        Minimum segment length fraction. Default 0.15.
    """

    def __init__(self, alpha: float = 0.05, min_segment: float = 0.15):
        self.alpha = alpha
        self.min_segment = min_segment

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

        from scipy.stats import f as fdist
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

        f_crit = fdist.ppf(1 - self.alpha, 1, max(T - 2, 1))
        has_bp = best_f > f_crit and best_bp is not None

        result = {
            'has_breakpoint': has_bp,
            'max_stat': float(best_f),
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

    def _no_breakpoint_result(self, T: int) -> Dict:
        return {
            'has_breakpoint': False, 'breakpoint_idx': None,
            'max_stat': 0.0, 'critical': 0.0,
            'cusum_path': np.zeros(T),
            'pre_mean': float('nan'), 'post_mean': float('nan'),
        }


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
            cusum_max_stat : float
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
            'cusum_max_stat': float(bp_result.get('max_stat', 0.0)),
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

        return 'stable' if mean_abs > std_val * 0.5 else 'suspect'

    def _detect_decay(self, lambda_hat: np.ndarray) -> Dict:
        """Detect exponential decay in premium via log-linear fit.

        Model: |λ(t)| = A × exp(-t/τ) + noise
        log|λ(t)| = log(A) - t/τ
        Estimate half-life = τ × ln(2).
        """
        result = {'has_decay': False, 'half_life': None, 'decay_rate': None}

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

        denom = np.sum((t_valid - np.mean(t_valid)) ** 2)
        if denom < 1e-12:
            return result

        beta = np.sum((t_valid - np.mean(t_valid)) * (log_y - np.mean(log_y))) / denom

        if beta < 0:
            tau = -1.0 / beta
            half_life = tau * np.log(2)
            result['decay_rate'] = float(beta)
            result['half_life'] = float(half_life)
            result['has_decay'] = half_life < self.half_life_threshold

        return result

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
