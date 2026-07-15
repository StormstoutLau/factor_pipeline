# -*- coding: utf-8 -*-
"""状态条件性能矩阵 + 双轨回归 (RESEARCH_NOTES E8 §3.1)

双轨回归:
- Track 1 (R_factor): R_factor,t = α + β' × S_{t-1} + ε_t  (Ferson 2003)
- Track 2 (IC):       IC_t = α + β' × S_{t-1} + ν_t

Newey-West HAC 标准误, BH-FDR 多重检验校正 (复用 T4).

三层维度控制:
- L1 主层: 252 检验 (12 状态 × 21 因子, 全样本)
- L2 次层: 126 检验 (子样本, 半样本验证)
- L3 探索层: <100 检验 (滚动窗口 63 天)
"""
from typing import Dict, Any, Optional, List
import logging

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats as sps

from backtest.multiple_testing import apply_bh_fdr

logger = logging.getLogger(__name__)


class StateConditionedAnalyzer:
    """状态条件性能矩阵 + 双轨回归 (RESEARCH_NOTES §2B.4)

    双轨:
    - R_factor on state (主, Ferson 2003 标准条件因子模型)
    - IC on state (辅, 项目认识论 — 直接检验选股能力状态依赖)

    三层维度控制:
    - L1 主层: 252 检验 (12 × 21, 全样本)
    - L2 次层: 126 检验 (半样本验证)
    - L3 探索层: <100 检验 (滚动窗口)

    BH-FDR 应用于多重检验 (复用 T4).
    """

    def __init__(
        self,
        alpha: float = 0.05,
        correction: str = 'benjamini_hochberg',
        min_obs_per_cell: int = 30,
        n_lags: int = 5,
        enable: bool = False,
    ):
        self.alpha = alpha
        self.correction = correction
        self.min_obs_per_cell = min_obs_per_cell
        self.n_lags = n_lags
        self.enable = enable
        self._factor_returns: Optional[Dict[str, pd.DataFrame]] = None
        self._state_data: Optional[pd.DataFrame] = None
        self._regime_labels: Optional[np.ndarray] = None
        self._fwd_returns: Optional[pd.DataFrame] = None
        self._performance_matrix: Optional[pd.DataFrame] = None
        self._regression_results: Dict[str, Dict] = {}

    def fit(
        self,
        factor_returns: Dict[str, pd.DataFrame],
        state_data: pd.DataFrame,
        regime_labels: np.ndarray,
        fwd_returns: pd.DataFrame,
    ) -> 'StateConditionedAnalyzer':
        """拟合状态条件分析

        Args:
            factor_returns: {因子名: (N_stocks, T_dates) DataFrame}
                stocks 为 index, dates 为 columns
            state_data: (T, 12) 状态变量 (来自 E7 StateDataLoader)
            regime_labels: (T,) 体制标签 (来自 E7 MarkovRegimeIdentifier)
            fwd_returns: (T, N_stocks) 前向收益, dates 为 index, stocks 为 columns

        Returns:
            self (链式调用)
        """
        if not self.enable:
            return self

        self._factor_returns = factor_returns
        self._state_data = state_data
        self._regime_labels = np.asarray(regime_labels)
        self._fwd_returns = fwd_returns
        return self

    def compute_performance_matrix(self, metric: str = 'ic') -> pd.DataFrame:
        """计算因子 × 体制的性能矩阵

        Args:
            metric: 'ic' (Spearman IC 均值) / 'return' (因子多空收益均值)

        Returns:
            DataFrame: index=因子名, columns=体制标签, values=性能指标.
            enable=False 或未 fit 时返回空 DataFrame.
        """
        if self._factor_returns is None:
            return pd.DataFrame()

        regimes = np.unique(self._regime_labels)
        factors = list(self._factor_returns.keys())
        matrix = pd.DataFrame(index=factors, columns=regimes, dtype=float)

        for fname in factors:
            fdata = self._factor_returns[fname]
            for regime in regimes:
                mask = self._regime_labels == regime
                if mask.sum() < self.min_obs_per_cell:
                    matrix.loc[fname, regime] = float('nan')
                    continue
                if metric == 'ic':
                    ic_series = self._compute_ic_series(
                        fdata.iloc[:, mask], self._fwd_returns.iloc[mask],
                    )
                    matrix.loc[fname, regime] = float(ic_series.mean())
                elif metric == 'return':
                    ls_series = self._compute_long_short_return_series(
                        fdata.iloc[:, mask], self._fwd_returns.iloc[mask],
                    )
                    matrix.loc[fname, regime] = float(ls_series.mean())

        self._performance_matrix = matrix
        return matrix

    def _compute_ic_series(
        self,
        factor_values: pd.DataFrame,
        fwd_returns: pd.DataFrame,
    ) -> pd.Series:
        """计算 IC 序列 (Spearman rank IC, 每期一个 IC)

        Args:
            factor_values: (N, T) stocks=index, dates=columns
            fwd_returns: (T, N) dates=index, stocks=columns

        Returns:
            pd.Series: IC 序列, index=dates
        """
        common_dates = factor_values.columns.intersection(fwd_returns.index)
        ic_list = []
        dates_used = []
        for date in common_dates:
            fvals = factor_values[date].dropna()
            if date not in fwd_returns.index:
                continue
            rvals = fwd_returns.loc[date].dropna()
            common_stocks = fvals.index.intersection(rvals.index)
            if len(common_stocks) < 10:
                continue
            ic, _ = sps.spearmanr(
                fvals.loc[common_stocks], rvals.loc[common_stocks],
            )
            ic_list.append(ic)
            dates_used.append(date)
        return pd.Series(ic_list, index=pd.DatetimeIndex(dates_used))

    def _compute_long_short_return_series(
        self,
        factor_values: pd.DataFrame,
        fwd_returns: pd.DataFrame,
    ) -> pd.Series:
        """计算因子多空收益序列 (R_factor)

        对每期: 按因子值排序, 高位做多 (top 20%), 低位做空 (bottom 20%),
        R_factor = mean(r_long) - mean(r_short)

        Args:
            factor_values: (N, T) stocks=index, dates=columns
            fwd_returns: (T, N) dates=index, stocks=columns

        Returns:
            pd.Series: R_factor 序列, index=dates
        """
        common_dates = factor_values.columns.intersection(fwd_returns.index)
        r_list = []
        dates_used = []
        for date in common_dates:
            fvals = factor_values[date].dropna()
            if date not in fwd_returns.index:
                continue
            rvals = fwd_returns.loc[date].dropna()
            common = fvals.index.intersection(rvals.index)
            if len(common) < 10:
                continue
            f_common = fvals.loc[common]
            r_common = rvals.loc[common]
            q80 = f_common.quantile(0.8)
            q20 = f_common.quantile(0.2)
            long_stocks = f_common[f_common >= q80].index
            short_stocks = f_common[f_common <= q20].index
            if len(long_stocks) == 0 or len(short_stocks) == 0:
                continue
            r_factor = (
                r_common.loc[long_stocks].mean()
                - r_common.loc[short_stocks].mean()
            )
            r_list.append(r_factor)
            dates_used.append(date)
        return pd.Series(r_list, index=pd.DatetimeIndex(dates_used))

    def _prepare_regression_data(
        self,
        y: pd.Series,
    ) -> tuple:
        """准备回归数据: 对齐 y 与滞后状态变量

        Args:
            y: 因变量序列 (R_factor 或 IC), index=dates

        Returns:
            (y_aligned, X_aligned) 或 (None, None) 若数据不足
        """
        if y is None or len(y) < self.min_obs_per_cell:
            return None, None

        # 滞后状态变量一期 (避免前视偏差)
        state_lagged = self._state_data.shift(1)

        # 对齐 y 和 state_lagged
        common = y.index.intersection(state_lagged.index)
        y_aligned = y.loc[common]
        X_aligned = state_lagged.loc[common].dropna()
        y_aligned = y_aligned.loc[X_aligned.index]

        if len(y_aligned) < self.min_obs_per_cell:
            return None, None

        return y_aligned, X_aligned

    def factor_return_regression(self, factor_name: str) -> Dict:
        """轨道 1: R_factor on state (Ferson & Schadt 1996 条件绩效评估, JF 51(2), 425-461)

        R_factor,t = alpha + Σ β_k * S_{k,t-1} + ε_t
        Newey-West HAC 标准误

        Args:
            factor_name: 因子名

        Returns:
            Dict 含 alpha/betas/r_squared/alpha_pvalue/beta_pvalues/
            n_observations/n_lags. 数据不足时返回 {'error': ...}.
        """
        if (
            self._factor_returns is None
            or factor_name not in self._factor_returns
        ):
            return {}

        fdata = self._factor_returns[factor_name]
        factor_long_short = self._compute_long_short_return_series(
            fdata, self._fwd_returns,
        )

        y, X = self._prepare_regression_data(factor_long_short)
        if y is None:
            return {'error': 'insufficient observations'}

        X_with_const = sm.add_constant(X)
        try:
            model = sm.OLS(y, X_with_const)
            result = model.fit(
                cov_type='HAC', cov_kwds={'maxlags': self.n_lags},
            )
        except Exception as e:
            logger.warning(f"R_factor 回归失败: {e}")
            return {'error': str(e)}

        return {
            'factor': factor_name,
            'track': 'R_factor_on_state',
            'alpha': float(result.params['const']),
            'alpha_pvalue': float(result.pvalues['const']),
            'alpha_std_error': float(result.bse['const']),
            'betas': {col: float(result.params[col]) for col in X.columns},
            'beta_pvalues': {
                col: float(result.pvalues[col]) for col in X.columns
            },
            'beta_std_errors': {
                col: float(result.bse[col]) for col in X.columns
            },
            'r_squared': float(result.rsquared),
            'n_observations': int(result.nobs),
            'n_lags': self.n_lags,
        }

    def ic_on_state_regression(self, factor_name: str) -> Dict:
        """轨道 2: IC on state (项目认识论)

        IC_t = alpha_IC + Σ γ_k * S_{k,t-1} + ν_t
        Newey-West HAC 标准误

        Args:
            factor_name: 因子名

        Returns:
            Dict 含 alpha_ic/gammas/r_squared/n_observations/n_lags.
            数据不足时返回 {'error': ...}.
        """
        if (
            self._factor_returns is None
            or factor_name not in self._factor_returns
        ):
            return {}

        fdata = self._factor_returns[factor_name]
        ic_series = self._compute_ic_series(fdata, self._fwd_returns)

        y, X = self._prepare_regression_data(ic_series)
        if y is None:
            return {'error': 'insufficient observations'}

        X_with_const = sm.add_constant(X)
        try:
            model = sm.OLS(y, X_with_const)
            result = model.fit(
                cov_type='HAC', cov_kwds={'maxlags': self.n_lags},
            )
        except Exception as e:
            logger.warning(f"IC 回归失败: {e}")
            return {'error': str(e)}

        return {
            'factor': factor_name,
            'track': 'IC_on_state',
            'alpha_ic': float(result.params['const']),
            'alpha_ic_pvalue': float(result.pvalues['const']),
            'alpha_ic_std_error': float(result.bse['const']),
            'gammas': {col: float(result.params[col]) for col in X.columns},
            'gamma_pvalues': {
                col: float(result.pvalues[col]) for col in X.columns
            },
            'r_squared': float(result.rsquared),
            'n_observations': int(result.nobs),
            'n_lags': self.n_lags,
        }

    def test_all_factors(
        self, correction: Optional[str] = None,
    ) -> Dict[str, Dict]:
        """对所有因子执行双轨回归 + BH-FDR 校正

        Args:
            correction: 校正方法 ('benjamini_hochberg' / 'bonferroni' / 'none').
                None 时用 self.correction.

        Returns:
            {factor_name: {'R_factor_on_state': {...}, 'IC_on_state': {...}}}
            + '_global_correction' key (若校正应用)
        """
        if self._factor_returns is None:
            return {}

        corr = correction if correction is not None else self.correction
        results: Dict[str, Any] = {}
        all_p_values: List[float] = []

        for fname in self._factor_returns.keys():
            r_track = self.factor_return_regression(fname)
            ic_track = self.ic_on_state_regression(fname)
            results[fname] = {
                'R_factor_on_state': r_track,
                'IC_on_state': ic_track,
            }
            # 收集 p 值用于 BH-FDR
            if 'beta_pvalues' in r_track:
                all_p_values.extend(r_track['beta_pvalues'].values())
            if 'gamma_pvalues' in ic_track:
                all_p_values.extend(ic_track['gamma_pvalues'].values())

        # BH-FDR 校正 (复用 T4)
        if all_p_values and corr == 'benjamini_hochberg':
            try:
                adj_p, rejected = apply_bh_fdr(all_p_values, alpha=self.alpha)
                results['_global_correction'] = {
                    'method': 'benjamini_hochberg',
                    'n_tests': len(all_p_values),
                    'n_rejected': int(sum(rejected)),
                    'alpha': self.alpha,
                }
            except Exception as e:
                logger.warning(f"BH-FDR 校正失败: {e}")
                results['_global_correction'] = {
                    'method': 'benjamini_hochberg',
                    'n_tests': len(all_p_values),
                    'error': str(e),
                }

        self._regression_results = results
        return results

    def get_diagnostics(self) -> Dict[str, Any]:
        """返回诊断信息

        Returns:
            Dict 含 enabled/fitted/n_factors/n_state_variables/
            n_regimes/n_observations/min_obs_per_cell/n_lags/
            correction/n_regression_results
        """
        if self._factor_returns is None:
            return {'enabled': self.enable, 'fitted': False}
        return {
            'enabled': self.enable,
            'fitted': True,
            'n_factors': len(self._factor_returns),
            'n_state_variables': (
                len(self._state_data.columns)
                if self._state_data is not None
                else 0
            ),
            'n_regimes': (
                len(np.unique(self._regime_labels))
                if self._regime_labels is not None
                else 0
            ),
            'n_observations': (
                len(self._state_data)
                if self._state_data is not None
                else 0
            ),
            'min_obs_per_cell': self.min_obs_per_cell,
            'n_lags': self.n_lags,
            'correction': self.correction,
            'n_regression_results': len(self._regression_results),
        }
