# -*- coding: utf-8 -*-
"""Toda-Yamamoto (1995) 格兰杰因果检验器.

在 VAR(p+d) 基础上对前 p 阶做 Wald 检验,
避免非平稳序列上的伪回归问题.
严格定位为"伪回归初筛过滤器", 非因果证明工具.

数学:
1. ADF 检验确定最高单整阶数 d
2. 估计 VAR(p+d) 模型
3. 对前 p 阶做 Wald 检验 (H0: F 不 Granger-cause R)
4. Wald 统计量 ~ χ²(p)
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from statsmodels.tsa.stattools import adfuller
from statsmodels.tsa.api import VAR


class TodaYamamotoGrangerTester:
    """Toda-Yamamoto (1995) 格兰杰因果检验器.

    在 VAR(p+d) 基础上对前 p 阶做 Wald 检验,
    避免非平稳序列上的伪回归问题.
    严格定位为"伪回归初筛过滤器", 非因果证明工具.

    数学:
    1. ADF 检验确定最高单整阶数 d
    2. 估计 VAR(p+d) 模型
    3. 对前 p 阶做 Wald 检验 (H0: F 不 Granger-cause R)
    4. Wald 统计量 ~ χ²(p)
    """

    def __init__(
        self,
        max_lag: int = 12,
        significance_level: float = 0.05,
        use_bootstrap: bool = False,
        bootstrap_samples: int = 1000,
    ):
        self.max_lag = max_lag
        self.significance_level = significance_level
        self.use_bootstrap = use_bootstrap
        self.bootstrap_samples = bootstrap_samples

    def fit(
        self,
        factor_series: pd.Series,
        return_series: pd.Series,
    ) -> 'TodaYamamotoGrangerTester':
        """估计 VAR(p+d) 并执行 Wald 检验.

        Args:
            factor_series: 因子时序 (T,)
            return_series: 收益时序 (T,)
        """
        # 对齐数据
        aligned = pd.concat([factor_series, return_series], axis=1).dropna()
        aligned.columns = ['factor', 'return']
        self._aligned_data = aligned

        # 短序列降级保护
        if len(aligned) < 20:
            self._d = 0
            self._p = 1
            self._wald_factor_to_return = {
                'wald_statistic': float('nan'),
                'p_value': float('nan'),
                'df': 1,
                'is_significant': False,
                'error': 'insufficient samples (T<20)',
            }
            self._wald_return_to_factor = dict(self._wald_factor_to_return)
            self._var_result = None
            self._bootstrap_result = None
            self._error = 'insufficient samples (T<20)'
            return self

        # Step 1: ADF 检验确定单整阶数 d
        d_factor = self._determine_integration_order(aligned['factor'])
        d_return = self._determine_integration_order(aligned['return'])
        d = max(d_factor, d_return)
        self._d = d

        # Step 2: 选择 VAR 滞后阶数 p (AIC)
        var_data = aligned.values
        var_model = VAR(var_data)
        try:
            lag_order = var_model.select_order(maxlags=self.max_lag)
            p = lag_order.aic if lag_order.aic > 0 else 1
        except Exception:
            p = 1
        self._p = p

        # Step 3: 估计 VAR(p+d) 模型
        total_lag = p + d
        try:
            var_result = var_model.fit(total_lag)
            self._var_result = var_result
        except Exception as e:
            self._error = str(e)
            self._wald_factor_to_return = {
                'wald_statistic': float('nan'),
                'p_value': float('nan'),
                'df': p,
                'is_significant': False,
                'error': str(e),
            }
            self._wald_return_to_factor = dict(self._wald_factor_to_return)
            self._bootstrap_result = None
            return self

        # Step 4: Wald 检验 (对前 p 阶)
        # H0: factor 的前 p 阶滞后对 return 无影响 (factor 不 Granger-cause return)
        self._wald_factor_to_return = self._wald_test(var_result, p, 'factor', 'return')
        # H0: return 的前 p 阶滞后对 factor 无影响 (return 不 Granger-cause factor)
        self._wald_return_to_factor = self._wald_test(var_result, p, 'return', 'factor')

        # Bootstrap 显著性 (可选)
        if self.use_bootstrap:
            self._bootstrap_result = self._bootstrap_significance(aligned, p, d)
        else:
            self._bootstrap_result = None

        return self

    def _determine_integration_order(self, series: pd.Series, max_d: int = 2) -> int:
        """确定序列的单整阶数 d (ADF 检验)."""
        s = series.dropna().values
        for d in range(max_d + 1):
            try:
                adf_stat, p_value, *_ = adfuller(s, autolag='AIC')
                if p_value < 0.05:  # 平稳
                    return d
            except Exception:
                return d
            s = np.diff(s)
            if len(s) < 10:
                return d
        return max_d

    def _wald_test(
        self,
        var_result,
        p: int,
        cause: str,
        effect: str,
    ) -> Dict[str, Any]:
        """Wald 检验: cause 的前 p 阶是否对 effect 有显著影响."""
        try:
            cause_idx = 0 if cause == 'factor' else 1
            effect_idx = 1 if effect == 'return' else 0

            test_result = var_result.test_causality(
                caused=[effect_idx], causing=[cause_idx], kind='wald'
            )
            return {
                'wald_statistic': float(test_result.test_statistic),
                'p_value': float(test_result.pvalue),
                'df': int(test_result.df),
                'is_significant': bool(test_result.pvalue < self.significance_level),
            }
        except Exception as e:
            return {
                'wald_statistic': float('nan'),
                'p_value': float('nan'),
                'df': p,
                'is_significant': False,
                'error': str(e),
            }

    def _bootstrap_significance(
        self,
        data: pd.DataFrame,
        p: int,
        d: int,
    ) -> Dict[str, Any]:
        """Bootstrap 显著性检验 (小样本稳健性, block bootstrap 保持时序结构)."""
        n = len(data)
        boot_stats = []
        block_size = max(p + d + 1, 10)
        n_blocks = max(n // block_size, 1)
        max_start = max(n - block_size, 1)
        for _ in range(self.bootstrap_samples):
            indices = np.random.choice(max_start, n_blocks, replace=True)
            boot_indices = np.concatenate(
                [np.arange(idx, idx + block_size) for idx in indices]
            )
            if len(boot_indices) < n:
                boot_indices = np.concatenate(
                    [boot_indices, np.random.choice(boot_indices, n - len(boot_indices))]
                )
            boot_data = data.iloc[boot_indices[:n]]

            try:
                boot_var = VAR(boot_data.values).fit(p + d)
                boot_test = boot_var.test_causality(
                    caused=[1], causing=[0], kind='wald'
                )
                boot_stats.append(float(boot_test.test_statistic))
            except Exception:
                continue

        if not boot_stats:
            return {'bootstrap_pvalue': float('nan'), 'n_valid': 0}

        original_stat = self._wald_factor_to_return.get('wald_statistic', 0)
        if np.isnan(original_stat):
            bootstrap_pvalue = float('nan')
        else:
            bootstrap_pvalue = float(np.mean(np.array(boot_stats) >= original_stat))

        return {
            'bootstrap_pvalue': bootstrap_pvalue,
            'n_valid': len(boot_stats),
            'bootstrap_mean': float(np.mean(boot_stats)),
            'bootstrap_std': float(np.std(boot_stats)),
        }

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            'integration_order': getattr(self, '_d', 0),
            'selected_lag': getattr(self, '_p', 1),
            'wald_factor_to_return': getattr(self, '_wald_factor_to_return', {}),
            'wald_return_to_factor': getattr(self, '_wald_return_to_factor', {}),
            'f_granger_cause_r': getattr(self, '_wald_factor_to_return', {}).get(
                'is_significant', False
            ),
            'r_granger_cause_f': getattr(self, '_wald_return_to_factor', {}).get(
                'is_significant', False
            ),
            'contemporaneous_causality': 'unidentified',  # 诚实承认
            'bootstrap_result': getattr(self, '_bootstrap_result', None),
            'interpretation': (
                f'Toda-Yamamoto (d={getattr(self, "_d", 0)}, p={getattr(self, "_p", 1)}): '
                f'F→R {"显著" if getattr(self, "_wald_factor_to_return", {}).get("is_significant", False) else "不显著"}, '
                f'R→F {"显著" if getattr(self, "_wald_return_to_factor", {}).get("is_significant", False) else "不显著"}'
            ),
            'warning': '格兰杰因果 ≠ 结构因果 — 仅为伪回归初筛',
        }
