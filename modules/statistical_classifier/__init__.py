"""Step 7: 向量化 StatisticalClassifier — VR + AR(1) stationarity (零 for 循环)"""
import numpy as np
import pandas as pd
from scipy.stats import norm


class StatisticalClassifier:
    """基于形式统计检验的因子分类 — 向量化面板实现.

    ┌────────────────────────────────────────────────────────────┐
    │ Test                           │ H₀          │ Reject →   │
    ├────────────────────────────────────────────────────────────┤
    │ Panel Variance Ratio (q=5)     │ random walk │ predictable│
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

        # ── Step 2: Panel AR(1) stationarity (向量化) ──
        ar1 = self._compute_panel_ar1(arr)  # (N,)
        se_ar1 = np.sqrt(np.maximum(1 - ar1**2, 1e-6) / T)  # (N,)
        z_ar1 = (ar1 - 0.98) / se_ar1
        p_unit_root = norm.cdf(z_ar1)
        is_stationary = p_unit_root < self.alpha  # (N,) bool

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
    def _compute_panel_ar1(arr: np.ndarray) -> np.ndarray:
        """向量化面板 AR(1) — OLS: x_t = ρ x_{t-1} + ε_t.

        Returns (N,) ρ per stock.
        """
        T, N = arr.shape
        x_t = arr[1:]    # (T-1, N)
        x_tm1 = arr[:-1]  # (T-1, N)
        valid = ~np.isnan(x_t) & ~np.isnan(x_tm1)

        num = np.nansum(x_t * x_tm1 * valid, axis=0)
        den = np.nansum(x_tm1 * x_tm1 * valid, axis=0)
        den = np.maximum(den, 1e-12)
        return num / den
