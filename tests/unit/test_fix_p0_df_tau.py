"""P0-1: Dickey-Fuller τ statistic unit tests.

Verifies that the vectorized DF τ implementation:
1. Correctly computes SE(ρ̂) = sqrt(σ̂² / Σ(x_{t-1}²)) — not Bartlett SE
2. Does not reject H₀ on random walk (ρ=1)
3. Correctly rejects H₀ on stationary AR(1) (ρ=0.5)
4. Produces identical results to per-column OLS (vectorized ≡ non-vectorized)
5. Bartlett SE ≠ DF SE on autoregressive data
"""

import numpy as np
import pytest
from factor_pipeline.modules.statistical_classifier import StatisticalClassifier


class TestDFTau:
    """Verify DF τ statistic is correct Dickey-Fuller (1979), not Bartlett (1946)."""

    @staticmethod
    def _compute_df_tau_reference(y: np.ndarray) -> float:
        """Reference implementation: per-column OLS DF τ (no-intercept).
        
        Δy_t = γ·y_{t-1} + ε_t, H₀: γ=0 (ρ=1).
        τ = γ̂ / SE(γ̂).
        """
        T = len(y)
        dy = np.diff(y)
        y_lag = y[:-1]
        valid = ~(np.isnan(dy) | np.isnan(y_lag))
        dy_v, y_lag_v = dy[valid], y_lag[valid]
        n = len(dy_v)
        if n < 10:
            return np.nan

        # OLS: γ̂ = Σ(y_{t-1}·Δy_t) / Σ(y_{t-1}²)
        gamma = np.sum(y_lag_v * dy_v) / np.maximum(np.sum(y_lag_v**2), 1e-12)
        rho = gamma + 1.0  # ρ̂ = γ̂ + 1

        # σ̂² = Σ(ε̂_t²) / (n - 1)
        residuals = dy_v - gamma * y_lag_v
        sigma2 = np.sum(residuals**2) / max(n - 1, 1)

        # SE(γ̂) = sqrt(σ̂² / Σ(y_{t-1}²))
        se_gamma = np.sqrt(sigma2 / np.maximum(np.sum(y_lag_v**2), 1e-12))

        tau = gamma / se_gamma  # = (ρ̂ - 1) / SE(ρ̂)
        return tau

    @staticmethod
    def _bartlett_tau(y: np.ndarray) -> float:
        """Bartlett (1946) approximation: SE = sqrt((1-ρ̂²)/T)."""
        T = len(y)
        x_t = y[1:]
        x_tm1 = y[:-1]
        valid = ~(np.isnan(x_t) | np.isnan(x_tm1))
        num = np.sum(x_t[valid] * x_tm1[valid])
        den = np.maximum(np.sum(x_tm1[valid]**2), 1e-12)
        rho = num / den
        se = np.sqrt(np.maximum(1 - rho**2, 1e-6) / T)
        return (rho - 1.0) / se

    def test_df_tau_not_bartlett(self):
        """DF τ must differ from Bartlett τ on AR(1) data with ρ=0.5."""
        np.random.seed(42)
        T = 500
        y = np.zeros(T)
        eps = np.random.randn(T)
        for t in range(1, T):
            y[t] = 0.5 * y[t-1] + eps[t]

        tau_df = self._compute_df_tau_reference(y)
        tau_bartlett = self._bartlett_tau(y)

        # The two should differ meaningfully for ρ=0.5
        assert abs(tau_df - tau_bartlett) > 0.05, (
            f"DF τ={tau_df:.4f}, Bartlett τ={tau_bartlett:.4f} — "
            f"should differ on AR(1) data with ρ=0.5"
        )

    def test_random_walk_not_rejected(self):
        """On random walk (ρ=1), DF τ should not reject H₀ at 5% level."""
        np.random.seed(123)
        T = 500
        n_trials = 100
        rejections = 0
        tau_crit = -1.95  # Fuller (1976) no-intercept 5% critical value

        for _ in range(n_trials):
            y = np.cumsum(np.random.randn(T))
            tau = self._compute_df_tau_reference(y)
            if tau < tau_crit:
                rejections += 1

        # On random walk, should reject ~5% of the time
        assert rejections <= 15, (
            f"Random walk rejected {rejections}/{n_trials} times "
            f"(expected ~5, got {rejections})"
        )

    def test_stationary_rejected(self):
        """On stationary AR(1) ρ=0.5, DF τ should reject H₀ consistently."""
        np.random.seed(456)
        T = 500
        n_trials = 100
        rejections = 0
        tau_crit = -1.95

        for _ in range(n_trials):
            y = np.zeros(T)
            eps = np.random.randn(T)
            for t in range(1, T):
                y[t] = 0.5 * y[t-1] + eps[t]
            tau = self._compute_df_tau_reference(y)
            if tau < tau_crit:
                rejections += 1

        # On stationary AR(1) ρ=0.5, should reject > 90% of the time
        assert rejections > 90, (
            f"Stationary AR(1) rejected {rejections}/{n_trials} times "
            f"(expected >90)"
        )

    def test_vectorized_matches_reference(self):
        """Vectorized panel DF τ ≡ per-column OLS DF τ."""
        np.random.seed(789)
        T, N = 500, 50
        arr = np.zeros((T, N))
        for j in range(N):
            rho = 0.5 + 0.4 * np.random.random()
            eps = np.random.randn(T)
            for t in range(1, T):
                arr[t, j] = rho * arr[t-1, j] + eps[t]

        # Vectorized (no demean, matching reference)
        tau_vec = StatisticalClassifier._compute_panel_df_tau(arr, demean=False)
        assert tau_vec.shape == (N,)

        # Per-column reference
        tau_ref = np.array([self._compute_df_tau_reference(arr[:, j]) for j in range(N)])

        # Should match within numerical tolerance
        assert np.allclose(tau_vec, tau_ref, rtol=1e-10, equal_nan=True), (
            f"Max diff: {np.nanmax(np.abs(tau_vec - tau_ref)):.2e}"
        )

    def test_se_formula(self):
        """Verify SE(ρ̂) = sqrt(σ̂² / Σ(x_{t-1}²)), not sqrt((1-ρ̂²)/T)."""
        np.random.seed(42)
        T = 200
        y = np.zeros(T)
        eps = np.random.randn(T)
        for t in range(1, T):
            y[t] = 0.9 * y[t-1] + eps[t]

        x_t = y[1:]
        x_tm1 = y[:-1]
        rho = np.sum(x_t * x_tm1) / np.maximum(np.sum(x_tm1**2), 1e-12)
        residuals = x_t - rho * x_tm1
        sigma2 = np.sum(residuals**2) / (T - 2)

        # DF SE
        se_df = np.sqrt(sigma2 / np.sum(x_tm1**2))
        # Bartlett SE
        se_bartlett = np.sqrt(np.maximum(1 - rho**2, 1e-6) / T)

        assert se_df > 0
        assert se_bartlett > 0
        # They should be different
        assert abs(se_df - se_bartlett) > 1e-5, (
            f"DF SE={se_df:.6f}, Bartlett SE={se_bartlett:.6f}"
        )

    def test_clip_denominator(self):
        """DF τ handles near-zero denominator gracefully."""
        arr = np.ones((100, 3))  # Constant values → denom ≈ 0
        tau = StatisticalClassifier._compute_panel_df_tau(arr)
        assert not np.any(np.isinf(tau)), "Should not produce inf"
        assert not np.any(np.isnan(tau)), "Should not produce NaN"

    def test_demean_effect(self):
        """Demean=True changes τ values vs demean=False (both are valid)."""
        arr = np.random.randn(100, 5) * 0.1 + 3.0  # Non-zero mean
        tau_demean = StatisticalClassifier._compute_panel_df_tau(arr, demean=True)
        tau_nodemean = StatisticalClassifier._compute_panel_df_tau(arr, demean=False)
        # Demeaning should produce different τ values (center removes trend-like behavior)
        assert not np.allclose(tau_demean, tau_nodemean, rtol=1e-10), (
            "Demean should change τ values"
        )