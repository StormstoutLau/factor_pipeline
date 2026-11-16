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
        return self._smooth_betas(beta_t)

    def estimate_with_errors(
        self, factor: pd.DataFrame, forward_returns: pd.DataFrame,
        alpha: float = 0.05, max_lag: Optional[int] = None,
    ) -> Dict:
        """Estimate λ̂(t) with Newey-West HAC standard errors.

        逐期: SE(λ̂_t) ≈ sqrt(Ω_t · Σ_s w_s²), Ω_t 为窗口内残差
        u_s = β_s − λ̂_s 的 HAC 长期方差 (局部常数核近似).
        均值: SE(λ̄) = sqrt(Ω_β / T_valid).
        有效点 <3 或 Ω<0 → 对应 SE=NaN; 零方差序列 SE=0.

        Returns
        -------
        dict with keys:
            lambda_hat / lambda_se / lambda_ci_low / lambda_ci_high : ndarray (T,)
            beta_t / beta_se : ndarray (T,)
            premium_mean / premium_mean_se / premium_mean_ci_low /
            premium_mean_ci_high : float
            n_periods / n_valid / hac_lag : int (hac_lag 为全局/均值带宽)
            alpha : float
        """
        common_idx = factor.index.intersection(forward_returns.index)
        common_cols = factor.columns.intersection(forward_returns.columns)
        F = factor.loc[common_idx, common_cols].values
        R = forward_returns.loc[common_idx, common_cols].values

        beta_t, beta_se = self._cross_sectional_betas_and_se(F, R)
        self._beta_raw = beta_t.copy()
        lambda_hat = self._smooth_betas(beta_t)

        T = len(beta_t)
        z = float(norm.ppf(1.0 - alpha / 2.0))

        valid_beta = np.isfinite(beta_t)
        n_valid = int(valid_beta.sum())
        if max_lag is not None:
            q_global = max(1, int(max_lag))
        else:
            q_global = max(1, int(4 * (n_valid / 100) ** (2 / 9)))

        lambda_se = np.full(T, np.nan)
        h = self.bandwidth
        for t in range(T):
            if not np.isfinite(lambda_hat[t]):
                continue
            lo = max(0, t - h)
            hi = min(T, t + h + 1)
            beta_win = beta_t[lo:hi]
            lam_win = lambda_hat[lo:hi]
            valid = np.isfinite(beta_win) & np.isfinite(lam_win)
            n_win = int(valid.sum())
            if n_win < 3:
                continue
            dist = np.abs(np.arange(lo, hi) - t) / h
            weights = self._epanechnikov(dist)[valid]
            # v3.4.12 复审修正 F1: 与 np.average 的实际归一化一致 (设计口径 sum=1).
            # 窗口含 NaN β 时, 未再归一化的 Σw² 会把 SE 低估 ×W_v.
            weights = weights / weights.sum()
            resid = beta_win[valid] - lam_win[valid]
            q_local = q_global if max_lag is not None else max(
                1, int(4 * (n_win / 100) ** (2 / 9))
            )
            omega = self._hac_long_run_variance(resid, q_local)
            if np.isfinite(omega) and omega >= 0:
                lambda_se[t] = np.sqrt(omega * float(np.sum(weights ** 2)))

        if n_valid >= 3:
            beta_valid = beta_t[valid_beta]
            premium_mean = float(np.mean(beta_valid))
            omega_beta = self._hac_long_run_variance(beta_valid, q_global)
            premium_mean_se = (
                float(np.sqrt(omega_beta / n_valid))
                if np.isfinite(omega_beta) and omega_beta >= 0 else np.nan
            )
        else:
            premium_mean = np.nan
            premium_mean_se = np.nan

        return {
            'lambda_hat': lambda_hat,
            'lambda_se': lambda_se,
            'lambda_ci_low': lambda_hat - z * lambda_se,
            'lambda_ci_high': lambda_hat + z * lambda_se,
            'beta_t': beta_t,
            'beta_se': beta_se,
            'premium_mean': premium_mean,
            'premium_mean_se': premium_mean_se,
            'premium_mean_ci_low': premium_mean - z * premium_mean_se,
            'premium_mean_ci_high': premium_mean + z * premium_mean_se,
            'n_periods': T,
            'n_valid': n_valid,
            'hac_lag': int(q_global),
            'alpha': float(alpha),
        }

    def _smooth_betas(self, beta_t: np.ndarray) -> np.ndarray:
        """Epanechnikov kernel smoothing of β_t → λ̂(t)."""
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
        """Vectorized cross-sectional regression per period (slope only)."""
        return self._cross_sectional_betas_and_se(F, R)[0]

    def _cross_sectional_betas_and_se(
        self, F: np.ndarray, R: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Vectorized cross-sectional regression per period.
        
        Model: r_t = α + β_t × f_{t-1} + ε
        β_t = Cov(r, f) / Var(f) (single-factor OLS slope)
        """
        T, N = F.shape
        beta_t = np.full(T, np.nan)
        beta_se = np.full(T, np.nan)

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

            beta = np.dot(f_demean, r_demean) / var_f
            resid = r_demean - beta * f_demean
            # v3.4.12 复审修正 F2: max(...,1) 守卫 min_stocks<=2 的配置 (精确拟合 → SE=0)
            sigma2 = np.dot(resid, resid) / max(n_valid - 2, 1)

            beta_t[t] = beta
            beta_se[t] = np.sqrt(max(sigma2, 0.0) / var_f)

        return beta_t, beta_se

    @staticmethod
    def _hac_long_run_variance(x: np.ndarray, max_lag: int) -> float:
        """Newey & West (1987) long-run variance, Bartlett kernel.

        Ω = γ0 + 2 Σ_{l=1}^{q} (1 − l/(q+1)) γ_l, γ_l = (1/n) Σ x̃_t x̃_{t−l}

        注: 纯 NW(1987) 渐近形式, 不含 Stata `newey` 默认的 n/(n−k) 自由度修正
        (差异 O(k/n); 已由 scripts/verify_hac_stata.py 对拍确认仅此一约定差).
        """
        x = np.asarray(x, dtype=float)
        x = x[np.isfinite(x)]
        n = len(x)
        if n < 3:
            return np.nan
        q = max(0, min(int(max_lag), n - 1))
        x_demean = x - np.mean(x)
        omega = float(np.dot(x_demean, x_demean) / n)
        for lag in range(1, q + 1):
            weight = 1.0 - lag / (q + 1.0)
            gamma_l = float(np.dot(x_demean[lag:], x_demean[:-lag]) / n)
            omega += 2.0 * weight * gamma_l
        return omega

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

    def _no_breakpoint_result(self, T: int) -> Dict:
        """有效点 <30 的退化结果: 不做 sup-F 网格搜索, 直接判无断点。

        T<30 时 `min_segment` 允许的候选切分过少, Andrews (1993) sup-F 渐近
        临界值不适用, 检验无意义; 返回与正常路径同构的 6 键结果 (cusum 全 NaN,
        不含 `breakpoint_idx`), 供 `diagnose` 与下游安全消费。

        注: v3.4.12 及之前该分支调用未定义的方法 → AttributeError (DEFECT-1),
        v3.4.13 补齐。
        """
        n = max(int(T), 0)
        return {
            'has_breakpoint': False,
            'chow_max_stat': 0.0,
            'critical': float('nan'),
            'cusum_path': np.full(n, np.nan),
            'pre_mean': float('nan'),
            'post_mean': float('nan'),
        }

    # ── Bai-Perron 多断点 (v3.5.0, ADR-046) ──────────────────────────────

    def detect_multiple(self, lambda_hat: np.ndarray,
                        m_max: int = None) -> Dict:
        """Bai-Perron 多断点: 全局最小 SSR + BIC/LWZ 选段数 (只读诊断)。

        模型与 `detect` 同族 (纯均值分段):
            y_t = μ_j + ε_t,  t ∈ (T_{j-1}, T_j],  j = 1..m+1

        估计: 动态规划求全局最小 SSR (Bai & Perron 1998, §3.2);
        选段数: BIC (Yao 1988) 主, LWZ (Liu-Wu-Zidek 1997; c0=0.1, δ0=0.1) 对照。

        Parameters
        ----------
        lambda_hat : np.ndarray
            待检测序列 (可含 NaN; NaN 会被剔除, 断点索引映射回原序列)。
        m_max : int, optional
            最大断点数。默认 5 (Bai & Perron 2003 常用上界)。实际生效上界为
            `min(m_max, T//h - 1)`, 以输出键 `m_max` 为准。

        Returns
        -------
        dict
            13 键: has_breakpoint / n_breaks / breakpoints / segment_means /
            segment_bounds / ssr / bic / lwz / best_bic_m / best_lwz_m /
            trimming / m_max / n_valid。

        Notes
        -----
        - 与 `detect` 完全独立: 后者单断点网格搜索, 本方法不改其行为;
        - T<30 或 `(m_max+1)*h > T` 时返回退化结果 (不抛异常);
        - `has_breakpoint` 由 BIC 选定段数决定 (n_breaks > 0), 不做 sup-F
          临界值判定 — 未硬编码 Bai-Perron 临界值表, 见 ADR-046。
        """
        y_all = np.asarray(lambda_hat, dtype=float).ravel()
        valid = ~np.isnan(y_all)
        y = y_all[valid]
        T = int(len(y))
        m_max = 5 if m_max is None else max(int(m_max), 0)

        if T < 30:
            return self._multiple_no_breakpoint_result(T, m_max)

        h = max(5, int(T * self.min_segment))
        m_cap = min(m_max, T // h - 1)
        if m_cap < 0:
            return self._multiple_no_breakpoint_result(T, m_max)

        cs, cs2 = self._ssr_prefix(y)
        ssr_mat = self._build_ssr_matrix(cs, cs2, T, h)

        ssr_by_m: Dict[int, float] = {0: float(ssr_mat[0, T])}
        brk_by_m: Dict[int, list] = {0: []}
        for k in range(1, m_cap + 1):
            val, brks = self._dp_breaks(ssr_mat, T, h, k)
            ssr_by_m[k] = val
            brk_by_m[k] = brks

        flat = (not np.isfinite(ssr_by_m[0])) or ssr_by_m[0] < 1e-12
        if flat:
            bic = {k: float('nan') for k in ssr_by_m}
            lwz = {k: float('nan') for k in ssr_by_m}
            best_bic, best_lwz = 0, 0
        else:
            bic = {k: self._bic(v, T, k) for k, v in ssr_by_m.items()}
            lwz = {k: self._lwz(v, T, k) for k, v in ssr_by_m.items()}
            best_bic = int(min(bic, key=lambda k: bic[k]))
            best_lwz = int(min(lwz, key=lambda k: lwz[k]))

        idx_map = np.where(valid)[0]
        breaks = brk_by_m[best_bic]
        bounds = [0] + list(breaks) + [T]
        seg_means = [float(np.mean(y[a:b]))
                     for a, b in zip(bounds[:-1], bounds[1:])]
        seg_bounds = [(int(idx_map[a]), int(idx_map[b - 1]) + 1)
                      for a, b in zip(bounds[:-1], bounds[1:])]

        return {
            'has_breakpoint': bool(best_bic > 0),
            'n_breaks': int(best_bic),
            'breakpoints': [int(idx_map[b]) for b in breaks],
            'segment_means': seg_means,
            'segment_bounds': seg_bounds,
            'ssr': ssr_by_m,
            'bic': bic,
            'lwz': lwz,
            'best_bic_m': best_bic,
            'best_lwz_m': best_lwz,
            'trimming': int(h),
            'm_max': int(m_cap),
            'n_valid': T,
        }

    @staticmethod
    def _ssr_prefix(y: np.ndarray):
        """前缀和 (长度 T+1, 首元素 0): ssr(i,j) = Σy² - (Σy)²/(j-i)."""
        cs = np.concatenate(([0.0], np.cumsum(y)))
        cs2 = np.concatenate(([0.0], np.cumsum(y * y)))
        return cs, cs2

    @staticmethod
    def _build_ssr_matrix(cs: np.ndarray, cs2: np.ndarray,
                          T: int, h: int) -> np.ndarray:
        """预计算 ssr_mat[i, j] = 区间 (i, j] 的 SSR; 段长 < h 为 inf."""
        mat = np.full((T + 1, T + 1), np.inf)
        for i in range(T + 1 - h):
            j = np.arange(i + h, T + 1)
            n = (j - i).astype(float)
            s = cs[j] - cs[i]
            s2 = cs2[j] - cs2[i]
            mat[i, j] = np.maximum(s2 - s * s / n, 0.0)
        return mat

    def _dp_breaks(self, ssr_mat: np.ndarray, T: int, h: int, k: int):
        """DP: k 个断点 (k+1 段) 的全局最小 SSR 与断点集 (1-based 段结束)。"""
        cost = np.full((k + 1, T + 1), np.inf)
        arg = np.full((k + 1, T + 1), -1, dtype=int)
        cost[0, :] = ssr_mat[0, :]
        for kk in range(1, k + 1):
            for jj in range((kk + 1) * h, T + 1):
                lo, hi = kk * h, jj - h
                if hi < lo:
                    continue
                cand = cost[kk - 1, lo:hi + 1] + ssr_mat[lo:hi + 1, jj]
                pos = int(np.argmin(cand))
                cost[kk, jj] = cand[pos]
                arg[kk, jj] = lo + pos
        if not np.isfinite(cost[k, T]):
            return float('inf'), []
        breaks = []
        jj = T
        for kk in range(k, 0, -1):
            ii = int(arg[kk, jj])
            breaks.append(ii)
            jj = ii
        breaks.reverse()
        return float(cost[k, T]), breaks

    @staticmethod
    def _bic(ssr: float, T: int, k: int) -> float:
        """Yao (1988) BIC: ln(SSR/T) + (k+1)*ln(T)/T (每段 1 个均值参数)."""
        if not np.isfinite(ssr) or ssr <= 0:
            return float('nan')
        return float(np.log(ssr / T) + (k + 1) * np.log(T) / T)

    @staticmethod
    def _lwz(ssr: float, T: int, k: int) -> float:
        """LWZ: ln(SSR/T) + (k+1)*c0*ln(T)^(2+δ0)/T, c0=0.1, δ0=0.1.

        Liu, Wu & Zidek (1997); 实现口径同 Bai & Perron (2003) §5.2。
        """
        if not np.isfinite(ssr) or ssr <= 0:
            return float('nan')
        ln_t = np.log(T)
        return float(np.log(ssr / T) + (k + 1) * 0.1 * ln_t ** 2.1 / T)

    @staticmethod
    def _multiple_no_breakpoint_result(T: int, m_max: int) -> Dict:
        """多断点退化结果 (T<30 或 trimming 不可行): 显式标记未计算。"""
        nan = float('nan')
        return {
            'has_breakpoint': False,
            'n_breaks': 0,
            'breakpoints': [],
            'segment_means': [nan],
            'segment_bounds': [],
            'ssr': {0: nan},
            'bic': {0: nan},
            'lwz': {0: nan},
            'best_bic_m': 0,
            'best_lwz_m': 0,
            'trimming': 0,
            'm_max': int(m_max),
            'n_valid': max(int(T), 0),
        }

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
