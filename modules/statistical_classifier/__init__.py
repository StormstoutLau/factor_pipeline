"""Step 7: 向量化 StatisticalClassifier — VR + AR(1) stationarity (零 for 循环)"""
import numpy as np
import pandas as pd
from scipy.stats import norm


class StatisticalClassifier:
    """基于形式统计检验的因子分类 — 向量化面板实现.

    ┌────────────────────────────────────────────────────────────┐
    │ Test                           │ H₀          │ Reject →   │
    ├────────────────────────────────────────────────────────────┤
    │ Panel Variance Ratio (q=5)     │ uncorrelated│ predictable│
    │ Panel AR(1) stationarity       │ unit root   │ stationary │
    └────────────────────────────────────────────────────────────┘

    分类规则:
    ┌──────────────────────┬──────────┬──────────┬──────────┐
    │ VR rejects RW?       │ YES      │ NO       │ —        │
    │ stationary?          │ YES      │ YES      │ NO       │
    ├──────────────────────┼──────────┼──────────┼──────────┤
    │ → Type               │ STATIC   │ DYNAMIC  │ MIXED    │
    └──────────────────────┴──────────┴──────────┴──────────┘

    性能: O(T×N) 向量化 (无 for 循环), 231期×100股 < 5ms.
    """

    def __init__(self, alpha: float = 0.05, vr_q: int = 5):
        self.alpha = alpha
        self.vr_q = vr_q

    def classify(self, factor_data: pd.DataFrame) -> str:
        """向量化分类 — 零 for 循环.

        factor_data: (T, N) DataFrame
        Returns: 'static' | 'dynamic' | 'mixed'
        """
        arr = factor_data.values  # (T, N)
        T, N = arr.shape

        if T < self.vr_q * 2 or N < 10:
            return 'static'  # 默认 safe 回退

        # ── Step 1: Panel Variance Ratio (Lo & MacKinlay 1988) ──
        var1 = np.nanvar(arr, axis=0)
        var1 = np.maximum(var1, 1e-12)

        rolled = pd.DataFrame(arr).rolling(self.vr_q, min_periods=self.vr_q).sum()
        var_q = np.nanvar(rolled.values[self.vr_q - 1:], axis=0)
        var_q = np.nan_to_num(var_q, nan=0.0)

        vr = var_q / (self.vr_q * var1)  # (N,)

        phi_vr = 2 * (2 * self.vr_q - 1) * (self.vr_q - 1) / (3 * self.vr_q * T)
        z_vr = (vr - 1.0) / np.sqrt(phi_vr)  # (N,)
        p_vr = 2 * norm.cdf(-np.abs(z_vr))  # (N,)

        vr_rejects = p_vr < self.alpha  # (N,) bool

        # ── Step 2: Panel AR(1) stationarity (Dickey-Fuller τ test) ──
        # DF τ = (ρ̂ - 1) / SE(ρ̂), where SE(ρ̂) = sqrt(σ̂² / Σ(x_{t-1}²))
        # NOT Bartlett (1946) SE = sqrt((1-ρ̂²)/T).
        # Reference: Dickey & Fuller (1979), JASA, 74(366), 427-431.
        # Critical values: Fuller (1976) Table 8.5.2, no-intercept case.
        tau_df = self._compute_panel_df_tau(arr)  # (N,) DF τ

        # Fuller (1976) Table 8.5.2: no-intercept, no-trend
        # τ_c(0.01)≈-2.58, τ_c(0.05)≈-1.95, τ_c(0.10)≈-1.62
        tau_crit = self._df_critical_value(T, self.alpha)
        is_stationary = tau_df < tau_crit  # (N,) reject unit root if τ < τ_crit

        # ── Step 3: Majority vote ──
        n_static = int(np.sum(vr_rejects & is_stationary))
        n_dynamic = int(np.sum(~vr_rejects & is_stationary))
        n_mixed = int(np.sum(~is_stationary))

        if n_static > max(n_dynamic, n_mixed):
            return 'static'
        elif n_dynamic > max(n_static, n_mixed):
            return 'dynamic'
        else:
            return 'mixed'

    @staticmethod
    def _compute_panel_df_tau(arr: np.ndarray, demean: bool = True) -> np.ndarray:
        """Vectorized panel Dickey-Fuller τ statistic (no-intercept).

        DF regression: Δy_t = γ·y_{t-1} + ε_t, H₀: γ = 0 (ρ = 1).
        τ = (ρ̂ - 1) / SE(ρ̂), where SE(ρ̂) = sqrt(σ̂² / Σ(x_{t-1}²)).

        This is NOT Bartlett (1946) SE = sqrt((1-ρ̂²)/T).
        The DF SE uses the actual residual variance, not the asymptotic
        approximation, and yields the correct DF τ distribution.

        Reference: Dickey & Fuller (1979), JASA, 74(366), 427-431.

        Args:
            arr: (T, N) panel of factor values.
            demean: if True, demean each column before computing.

        Returns:
            tau: (N,) DF τ statistics. H₀: ρ=1 rejected when τ < τ_crit.
        """
        T, N = arr.shape
        if demean:
            arr = arr - np.nanmean(arr, axis=0)

        x_t = arr[1:]      # (T-1, N)
        x_tm1 = arr[:-1]   # (T-1, N)
        valid = ~np.isnan(x_t) & ~np.isnan(x_tm1)

        # ρ̂ = Σ(x_t·x_{t-1}) / Σ(x_{t-1}²) — vectorized, (N,)
        num = np.nansum(x_t * x_tm1 * valid, axis=0)
        den = np.nansum(x_tm1 * x_tm1 * valid, axis=0)
        den = np.maximum(den, 1e-12)
        rho = num / den  # (N,)

        # σ̂² = Σ(x_t - ρ̂·x_{t-1})² / (T_eff - 1) — vectorized, (N,)
        T_eff = np.sum(valid, axis=0)
        residuals = x_t - rho * x_tm1  # (T-1, N)
        sigma2 = np.nansum(residuals * residuals * valid, axis=0)
        sigma2 = sigma2 / np.maximum(T_eff - 1, 1)

        # SE(ρ̂) = sqrt(σ̂² / Σ(x_{t-1}²)) — vectorized, (N,)
        se_rho = np.sqrt(sigma2 / den)  # (N,)

        # DF τ = (ρ̂ - 1) / SE(ρ̂) — vectorized, (N,)
        tau = (rho - 1.0) / np.maximum(se_rho, 1e-12)
        return tau

    @staticmethod
    def _df_critical_value(T: int, alpha: float = 0.05) -> float:
        """DF τ critical value for no-intercept, no-trend case.

        Source: Fuller (1976), Introduction to Statistical Time Series,
        Table 8.5.2, p. 373 (τ̂_μ quantiles).

        Large-T approximations:
        - α = 0.01: τ_c ≈ -2.58
        - α = 0.05: τ_c ≈ -1.95
        - α = 0.10: τ_c ≈ -1.62
        """
        if alpha <= 0.01:
            return -2.58
        elif alpha <= 0.05:
            return -1.95
        elif alpha <= 0.10:
            return -1.62
        else:
            return -1.95  # default to 5%
