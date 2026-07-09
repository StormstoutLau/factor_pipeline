# -*- coding: utf-8 -*-
"""三通道分解 (RESEARCH_NOTES E9 §3.1)

log|R_factor| ≈ log|IC| + log(σ_factor) + log(σ_R)

三个通道:
- IC 通道: 因子选股能力
- σ_factor 通道: 因子截面分散度
- σ_R 通道: 收益截面分散度

五种发散模式:
- A 一致 / B 放大 / C 仅 R (Moreira-Muir) / D 仅 IC (Lewellen-Nagel-Shanken) / E 符号翻转 (Lewellen-Nagel)

异方差检验: White (1980)
"""
from typing import Dict, Any, Optional, Tuple, List
import logging

import numpy as np
import pandas as pd
from scipy import stats as sps
import statsmodels.api as sm

logger = logging.getLogger(__name__)


class ThreeChannelDecomposition:
    """三通道分解 (RESEARCH_NOTES §2B.4.3)

    log|R_factor| ≈ log|IC| + log(σ_factor) + log(σ_R)

    三个通道:
    - IC 通道: 因子选股能力
    - σ_factor 通道: 因子截面分散度
    - σ_R 通道: 收益截面分散度

    五种发散模式:
    - A 一致 / B 放大 / C 仅 R (Moreira-Muir) / D 仅 IC (Lewellen-Nagel-Shanken) / E 符号翻转 (Lewellen-Nagel)

    异方差检验: White (1980)
    """

    PATTERN_NAMES: Dict[str, str] = {
        'A': 'consistent',
        'B': 'amplified',
        'C': 'R_only_moreira_muir',
        'D': 'IC_only_lewellen_nagel_shanken',
        'E': 'sign_flip_lewellen_nagel',
    }

    def __init__(
        self,
        enable: bool = False,
        heteroskedasticity_test: str = 'white',
        min_observations: int = 60,
    ):
        self.enable = enable
        self.heteroskedasticity_test = heteroskedasticity_test
        self.min_observations = min_observations
        self._factor_returns: Optional[Dict[str, pd.DataFrame]] = None
        self._fwd_returns: Optional[pd.DataFrame] = None
        self._regime_labels: Optional[np.ndarray] = None
        self._decomposition_results: Dict[str, Dict] = {}

    def fit(
        self,
        factor_returns: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        regime_labels: Optional[np.ndarray] = None,
    ) -> 'ThreeChannelDecomposition':
        """拟合三通道分解

        Args:
            factor_returns: {因子名: (N_stocks, T_dates) DataFrame}
            fwd_returns: (T, N_stocks) 前向收益
            regime_labels: (T,) 体制标签 (可选, 用于体制内分解)

        Returns:
            self (链式调用)
        """
        if not self.enable:
            return self

        self._factor_returns = factor_returns
        self._fwd_returns = fwd_returns
        self._regime_labels = regime_labels
        return self

    def _compute_channel_series(
        self,
        factor_name: str,
    ) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
        """计算四通道序列: (R_factor, IC, σ_factor, σ_R)

        Args:
            factor_name: 因子名

        Returns:
            (R_factor, IC, σ_factor, σ_R) 四个 pd.Series, index 对齐
        """
        fdata = self._factor_returns[factor_name]
        common_dates = fdata.columns.intersection(self._fwd_returns.index)

        r_list, ic_list, sf_list, sr_list, dates = [], [], [], [], []
        for date in common_dates:
            fvals = fdata[date].dropna()
            if date not in self._fwd_returns.index:
                continue
            rvals = self._fwd_returns.loc[date].dropna()
            common = fvals.index.intersection(rvals.index)
            if len(common) < 10:
                continue
            f_common = fvals.loc[common]
            r_common = rvals.loc[common]

            # R_factor: 高位做多, 低位做空
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

            # IC: Spearman rank
            ic, _ = sps.spearmanr(f_common, r_common)

            # σ_factor: 因子截面标准差
            sigma_f = float(f_common.std())

            # σ_R: 收益截面标准差
            sigma_r = float(r_common.std())

            r_list.append(r_factor)
            ic_list.append(ic)
            sf_list.append(sigma_f)
            sr_list.append(sigma_r)
            dates.append(date)

        index = pd.DatetimeIndex(dates)
        return (
            pd.Series(r_list, index=index),
            pd.Series(ic_list, index=index),
            pd.Series(sf_list, index=index),
            pd.Series(sr_list, index=index),
        )

    def decompose(self, factor_name: str) -> Dict[str, pd.Series]:
        """执行三通道分解

        log|R_factor| ≈ log|IC| + log(σ_factor) + log(σ_R)

        Args:
            factor_name: 因子名

        Returns:
            Dict 含 9 个序列: R_factor, IC, sigma_factor, sigma_R,
            log_R, log_IC, log_sigma_factor, log_sigma_R, log_residual.
            enable=False 时返回 {}.
        """
        if not self.enable or self._factor_returns is None:
            return {}

        if factor_name not in self._factor_returns:
            return {}

        r, ic, sf, sr = self._compute_channel_series(factor_name)

        # 对数变换 (取绝对值, 加小常数避免 log(0))
        eps = 1e-10
        log_r = np.log(np.abs(r) + eps)
        log_ic = np.log(np.abs(ic) + eps)
        log_sf = np.log(sf + eps)
        log_sr = np.log(sr + eps)

        # 残差 (三通道无法解释的部分)
        log_residual = log_r - log_ic - log_sf - log_sr

        result = {
            'R_factor': r,
            'IC': ic,
            'sigma_factor': sf,
            'sigma_R': sr,
            'log_R': log_r,
            'log_IC': log_ic,
            'log_sigma_factor': log_sf,
            'log_sigma_R': log_sr,
            'log_residual': log_residual,
        }

        self._decomposition_results[factor_name] = result
        return result

    def classify_divergence_pattern(
        self, factor_name: str,
    ) -> Dict[str, Any]:
        """分类发散模式 (A/B/C/D/E)

        Args:
            factor_name: 因子名

        Returns:
            Dict 含 factor/pattern/pattern_name/trends/interpretation
        """
        if not self.enable or self._factor_returns is None:
            return {
                'factor': factor_name,
                'pattern': 'unclassified',
                'pattern_name': 'unclassified',
            }

        series = self.decompose(factor_name)
        if not series:
            return {
                'factor': factor_name,
                'pattern': 'unclassified',
                'pattern_name': 'unclassified',
            }

        r = series['R_factor']
        ic = series['IC']
        sf = series['sigma_factor']
        sr = series['sigma_R']

        # 计算各通道的归一化趋势 (slope / residual_std, 信号噪声比)
        def _trend(s: pd.Series) -> float:
            """归一化趋势: slope / detrended_residual_std

            用 detrended residual std 归一化, 避免趋势本身膨胀 std.
            """
            x = np.arange(len(s))
            if len(s) < 10:
                return 0.0
            values = s.values
            slope, intercept = np.polyfit(x, values, 1)
            residuals = values - (slope * x + intercept)
            residual_std = float(np.std(residuals))
            if residual_std < 1e-10:
                return 0.0
            return float(slope / residual_std)

        r_norm = _trend(r)
        ic_norm = _trend(ic)
        sf_norm = _trend(sf)
        sr_norm = _trend(sr)

        # 阈值
        threshold = 0.1

        # 分类逻辑
        r_up = r_norm > threshold
        ic_up = ic_norm > threshold
        ic_down = ic_norm < -threshold
        sf_up = sf_norm > threshold
        sr_up = sr_norm > threshold

        if r_up and ic_up and sf_up and sr_up:
            pattern = 'A'  # 一致
        elif r_up and not ic_up and sf_up:
            pattern = 'B'  # 放大
        elif r_up and not ic_up and sr_up and not sf_up:
            pattern = 'C'  # 仅 R (Moreira-Muir)
        elif not r_up and ic_up:
            pattern = 'D'  # 仅 IC (Lewellen-Nagel-Shanken)
        elif r_up and ic_down:
            pattern = 'E'  # 符号翻转 (Lewellen-Nagel)
        else:
            pattern = 'unclassified'

        return {
            'factor': factor_name,
            'pattern': pattern,
            'pattern_name': self.PATTERN_NAMES.get(pattern, 'unclassified'),
            'trends': {
                'R_factor': r_norm,
                'IC': ic_norm,
                'sigma_factor': sf_norm,
                'sigma_R': sr_norm,
            },
            'interpretation': self._interpret_pattern(pattern),
        }

    def _interpret_pattern(self, pattern: str) -> str:
        """发散模式解释"""
        interpretations = {
            'A': '一致模式: R/IC/σ 同向变化, 标准因子模型成立',
            'B': '放大模式: R > IC, σ_factor 主导, 因子分散度膨胀',
            'C': '仅 R 模式 (Moreira-Muir 2017): R 变化但 IC 不变, 风险补偿主导',
            'D': '仅 IC 模式 (Lewellen-Nagel-Shanken): IC 变化但 R 不变, 因子误设定',
            'E': '符号翻转模式 (Lewellen-Nagel 2006): R 与 IC 反向, 条件可预测性反转',
            'unclassified': '未分类: 通道趋势组合不属于已知模式',
        }
        return interpretations.get(pattern, '未知模式')

    def test_heteroskedasticity(
        self, factor_name: str,
    ) -> Dict[str, Any]:
        """异方差检验 (White 1980)

        对 log|R| - log|IC| - log(σ_factor) - log(σ_R) 残差做 White 检验.

        Args:
            factor_name: 因子名

        Returns:
            Dict 含 factor/white_statistic/white_pvalue/is_heteroskedastic/test
        """
        if not self.enable or self._factor_returns is None:
            return {
                'factor': factor_name,
                'white_pvalue': 1.0,
                'is_heteroskedastic': False,
                'test': 'white',
            }

        series = self.decompose(factor_name)
        if not series:
            return {
                'factor': factor_name,
                'white_pvalue': 1.0,
                'is_heteroskedastic': False,
                'test': 'white',
            }

        residual = series['log_residual']

        # White 检验: 残差的方差是否随时间变化
        x = np.arange(len(residual))
        X = sm.add_constant(np.column_stack([x, x ** 2]))
        white_stat = 0.0
        white_pvalue = 1.0
        try:
            model = sm.OLS(residual.values, X).fit()
            n = len(residual)
            r_squared = model.rsquared
            white_stat = n * r_squared
            white_pvalue = float(sps.chi2.sf(white_stat, df=2))
        except Exception as e:
            logger.warning(f"White 检验失败: {e}")
            white_pvalue = 1.0

        return {
            'factor': factor_name,
            'white_statistic': float(white_stat),
            'white_pvalue': white_pvalue,
            'is_heteroskedastic': bool(white_pvalue < 0.05),
            'test': 'white',
        }

    def get_diagnostics(self) -> Dict[str, Any]:
        """返回诊断信息

        Returns:
            Dict 含 enabled/fitted/n_factors/n_decompositions/
            min_observations/heteroskedasticity_test
        """
        if self._factor_returns is None:
            return {
                'enabled': self.enable,
                'fitted': False,
                'heteroskedasticity_test': self.heteroskedasticity_test,
            }
        return {
            'enabled': self.enable,
            'fitted': True,
            'n_factors': len(self._factor_returns),
            'n_decompositions': len(self._decomposition_results),
            'min_observations': self.min_observations,
            'heteroskedasticity_test': self.heteroskedasticity_test,
        }
