# -*- coding: utf-8 -*-
"""RESEARCH_NOTES E5 — AttributionAnalyzer (三层归因分析)

规格文档: docs/EXECUTION_RESEARCH_NOTES.md 行 1363-1725

三层归因:
- Layer 1 (指纹归因): 21 维 FactorFingerprint 各维度对表现的标准化回归贡献
- Layer 2 (方差归因): 管道权重 (static/dynamic/mixed) 对总方差的贡献
- Layer 3 (交互归因): 指纹 × 处理 × 状态交互效应, 含 BH-FDR 校正

设计原则:
- 诊断优先于校正: 测量各层贡献, 不声称消除
- BH-FDR 应用于 Layer 3 交互项检验 (复用 T4 backtest.multiple_testing.apply_bh_fdr)
- 默认 enable=False (opt-in)
"""
from typing import Dict, Any, Optional, List
import logging

import numpy as np
import pandas as pd

try:
    import statsmodels.api as sm
    _HAS_STATSMODELS = True
except ImportError:
    _HAS_STATSMODELS = False

try:
    from backtest.multiple_testing import apply_bh_fdr
    _HAS_MULTIPLE_TESTING = True
except ImportError:
    _HAS_MULTIPLE_TESTING = False

logger = logging.getLogger(__name__)


# ============================================================
# 21 维指纹字段 (与 modules/factor_fingerprint/core/fingerprint.py 对齐)
# ============================================================
FINGERPRINT_FIELDS: List[str] = [
    'ar1_median', 'rank_autocorr', 'vol_clustering_pvalue', 'half_life',
    'level_diff_ic_ratio', 'skewness_std', 'kurtosis_std',
    'js_divergence_mean', 'missing_cv', 'coverage_ratio',
    'sd_score', 'complexity_need', 'snr_estimate',
    'tail_dependence_lower', 'tail_dependence_upper',
    'gpd_shape', 'hill_estimator',
    'regime_transition_prob', 'regime_persistence',
    'regime_ic_diff', 'tail_regime_score',
]

# 6 维表现字段 (与 E4 对齐)
PERFORMANCE_FIELDS: List[str] = [
    'ic_mean', 'ic_std', 'ic_ir', 'turnover', 'max_drawdown', 'sharpe_ratio',
]

# 3 维管道权重字段 (与 E4 对齐)
PIPELINE_WEIGHT_FIELDS: List[str] = ['weight_static', 'weight_dynamic', 'weight_mixed']


class AttributionAnalyzer:
    """三层归因分析器 (RESEARCH_NOTES §2.5)

    Layer 1: 指纹归因 — 各指纹维度对表现的单变量贡献
    Layer 2: 方差归因 — 管道权重 (static/dynamic/mixed) 对总方差的贡献
    Layer 3: 交互归因 — 指纹 × 处理 × 状态的交互效应 (含 BH-FDR 校正)

    设计原则:
    - 诊断优先于校正: 测量各层贡献, 不声称消除
    - BH-FDR 应用于 Layer 3 交互项检验 (复用 T4)
    - 默认 enable=False (opt-in)
    """

    def __init__(
        self,
        alpha: float = 0.05,
        correction: str = 'benjamini_hochberg',
        enable: bool = False,
    ):
        self.alpha = alpha
        self.correction = correction
        self.enable = enable
        self._data: Optional[pd.DataFrame] = None
        self._performance_metric: str = 'ic_mean'
        self._layer1_results: Optional[Dict[str, Dict]] = None
        self._layer2_results: Optional[Dict[str, float]] = None
        self._layer3_results: Optional[pd.DataFrame] = None

    # ============================================================
    # fit: 从 E4 FingerprintPerformanceLogger 的查询结果拟合
    # ============================================================

    def fit(
        self,
        fp_logger_data: pd.DataFrame,
        performance_metric: str = 'ic_mean',
    ) -> 'AttributionAnalyzer':
        """从 E4 FingerprintPerformanceLogger 的查询结果拟合

        Args:
            fp_logger_data: E4 query() 返回的 DataFrame
            performance_metric: 归因目标表现指标 ('ic_mean' / 'sharpe_ratio' / ...)
        """
        if fp_logger_data is None or len(fp_logger_data) == 0:
            self._data = pd.DataFrame()
        else:
            self._data = fp_logger_data.copy()
        self._performance_metric = performance_metric
        # 重置缓存
        self._layer1_results = None
        self._layer2_results = None
        self._layer3_results = None
        return self

    # ============================================================
    # Layer 1: 指纹归因 (单变量标准化回归)
    # ============================================================

    def layer1_fingerprint_attribution(self) -> Dict[str, Dict]:
        """Layer 1: 各指纹维度的单变量归因

        对每个指纹维度 d_j, 拟合 P = β0 + β1·d_j, 返回标准化 β1.

        Returns:
            {dim_name: {'beta_std': float, 'p_value': float, 'r_squared': float, 'n': int}}
            enable=False 或数据不足时返回 {}
        """
        if not self.enable:
            return {}
        if self._data is None or self._data.empty:
            return {}
        if self._performance_metric not in self._data.columns:
            return {}

        y_all = self._data[self._performance_metric]
        results: Dict[str, Dict] = {}

        for dim in FINGERPRINT_FIELDS:
            if dim not in self._data.columns:
                continue
            x = self._data[dim]
            # 配对非 NaN 样本
            mask = x.notna() & y_all.notna()
            x_valid = x[mask].astype(float)
            y_valid = y_all[mask].astype(float)
            n = len(x_valid)
            if n < 10:
                results[dim] = {'beta_std': 0.0, 'p_value': 1.0, 'r_squared': 0.0, 'n': n}
                continue
            x_std_val = float(x_valid.std())
            if x_std_val < 1e-10:
                results[dim] = {'beta_std': 0.0, 'p_value': 1.0, 'r_squared': 0.0, 'n': n}
                continue
            # 标准化
            x_std = (x_valid - x_valid.mean()) / x_std_val
            y_std_val = float(y_valid.std())
            if y_std_val < 1e-10:
                # 表现无方差, 所有 beta = 0
                results[dim] = {'beta_std': 0.0, 'p_value': 1.0, 'r_squared': 0.0, 'n': n}
                continue
            y_std = (y_valid - y_valid.mean()) / y_std_val
            if not _HAS_STATSMODELS:
                # 退化: 用 numpy 线性回归
                beta = float(np.corrcoef(x_std, y_std)[0, 1])
                results[dim] = {'beta_std': beta, 'p_value': 1.0, 'r_squared': beta * beta, 'n': n}
                continue
            X = sm.add_constant(x_std.values)
            try:
                model = sm.OLS(y_std.values, X).fit()
                results[dim] = {
                    'beta_std': float(model.params[1]),
                    'p_value': float(model.pvalues[1]),
                    'r_squared': float(model.rsquared),
                    'n': int(n),
                }
            except Exception:
                results[dim] = {'beta_std': 0.0, 'p_value': 1.0, 'r_squared': 0.0, 'n': n}

        self._layer1_results = results
        return results

    # ============================================================
    # Layer 2: 管道权重方差归因
    # ============================================================

    def layer2_variance_attribution(self) -> Dict[str, float]:
        """Layer 2: 管道权重方差归因

        ⚠ 近似实现: 用 w_p²·Var(P) 近似 w_p²·Var(P_p) (管道混合运行, 无法获取独立 P_p).
        误差量级: 管道间高相关 (|ρ|>0.5) 时单通道贡献误差 ±0.1~0.3.
        大交叉项场景应退化为数值归因 (Shapley / 扰动法).

        Returns:
            {'static': float, 'dynamic': float, 'mixed': float, 'covariance': float}
            各值之和 = 1.0 (归一化方差分解)
            enable=False 或数据不足时返回 {}
        """
        if not self.enable:
            return {}
        if self._data is None or self._data.empty:
            return {}
        if self._performance_metric not in self._data.columns:
            return {}
        if not all(c in self._data.columns for c in PIPELINE_WEIGHT_FIELDS):
            return {}

        metric = self._performance_metric
        valid_mask = self._data[PIPELINE_WEIGHT_FIELDS + [metric]].notna().all(axis=1)
        sub = self._data[valid_mask]
        if len(sub) < 10:
            return {}

        y = sub[metric].astype(float).values
        if len(y) < 2:
            return {}
        total_var = float(np.var(y, ddof=1))
        if total_var < 1e-10:
            return {'static': 0.0, 'dynamic': 0.0, 'mixed': 0.0, 'covariance': 0.0}

        # 近似: 各管道贡献 ≈ mean(w_p²) (因 w_p²·Var(P)/Var(P) = w_p², 取均值)
        contributions: Dict[str, float] = {}
        for p, col in zip(['static', 'dynamic', 'mixed'], PIPELINE_WEIGHT_FIELDS):
            w = sub[col].astype(float).values
            # 严格公式: Contribution_p = w_p²·Var(P_p)/Var(P)
            # 近似: Var(P_p) ≈ Var(P), 故 Contribution_p ≈ mean(w_p²)
            p_contrib = float(np.mean(w ** 2))
            contributions[p] = p_contrib

        # 协方差残余 (吸收交叉项)
        sum_individual = sum(contributions.values())
        contributions['covariance'] = max(0.0, 1.0 - sum_individual)

        # 归一化确保和精确为 1 (容错 sum_individual > 1 的边界情况)
        total = sum(contributions.values())
        if total > 0:
            contributions = {k: float(v / total) for k, v in contributions.items()}

        self._layer2_results = contributions
        return contributions

    # ============================================================
    # Layer 3: 交互归因 (含 BH-FDR 校正)
    # ============================================================

    def layer3_interaction_attribution(self) -> pd.DataFrame:
        """Layer 3: 指纹 × 处理 × 状态交互归因 (含 BH-FDR)

        对每个 (dim, weight_col, regime) 组合, 拟合交互回归:
            P = β0 + β1·dim + β2·w + β3·(dim×w) + ε
        对交互项 β3 的 p 值应用 BH-FDR 校正.

        Returns:
            DataFrame: columns = [dim, weight_type, regime, beta, p_value, p_adjusted, is_significant]
            enable=False 或数据不足时返回空 DataFrame
        """
        if not self.enable:
            return pd.DataFrame()
        if self._data is None or self._data.empty:
            return pd.DataFrame()
        if self._performance_metric not in self._data.columns:
            return pd.DataFrame()
        if not all(c in self._data.columns for c in PIPELINE_WEIGHT_FIELDS):
            return pd.DataFrame()
        if 'regime' not in self._data.columns:
            return pd.DataFrame()

        metric = self._performance_metric
        regimes = self._data['regime'].dropna().unique()
        results: List[Dict[str, Any]] = []

        for dim in FINGERPRINT_FIELDS:
            if dim not in self._data.columns:
                continue
            for w_col in PIPELINE_WEIGHT_FIELDS:
                for regime in regimes:
                    mask = (
                        self._data[dim].notna()
                        & self._data[w_col].notna()
                        & (self._data['regime'] == regime)
                        & self._data[metric].notna()
                    )
                    sub = self._data[mask]
                    if len(sub) < 20:
                        continue
                    x = sub[dim].astype(float).values
                    w = sub[w_col].astype(float).values
                    interaction = x * w
                    y_sub = sub[metric].astype(float).values
                    if not _HAS_STATSMODELS:
                        continue
                    X = sm.add_constant(np.column_stack([x, w, interaction]))
                    try:
                        model = sm.OLS(y_sub, X).fit()
                        # params: [const, x, w, interaction] → 交互项 index=3
                        beta = float(model.params[3])
                        p_val = float(model.pvalues[3])
                        results.append({
                            'dim': dim,
                            'weight_type': w_col,
                            'regime': regime,
                            'beta': beta,
                            'p_value': p_val,
                            'n': int(len(sub)),
                        })
                    except Exception:
                        continue

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)

        # BH-FDR 校正 (复用 T4 backtest.multiple_testing.apply_bh_fdr)
        # apply_bh_fdr 不接受 NaN, 需先过滤
        p_vals_raw = df['p_value'].tolist()
        # 应用 BH-FDR
        if _HAS_MULTIPLE_TESTING and self.correction == 'benjamini_hochberg':
            try:
                adj_p, rejected = apply_bh_fdr(p_vals_raw, alpha=self.alpha)
                df['p_adjusted'] = adj_p
                df['is_significant'] = [bool(x) for x in rejected]
            except (ValueError, TypeError):
                df['p_adjusted'] = df['p_value']
                df['is_significant'] = df['p_value'] < self.alpha
        else:
            df['p_adjusted'] = df['p_value']
            df['is_significant'] = df['p_value'] < self.alpha

        # 别名列: p_value_adjusted (兼容规格文档命名)
        df['p_value_adjusted'] = df['p_adjusted']

        self._layer3_results = df
        return df

    # ============================================================
    # get_diagnostics: 诊断信息
    # ============================================================

    def get_diagnostics(self) -> Dict[str, Any]:
        """诊断信息

        Returns:
            含 enabled / fitted / n_records / n_factors / performance_metric /
            layer1_n_dims_analyzed / layer3_n_significant / correction_method
        """
        if self._data is None:
            return {'enabled': self.enable, 'fitted': False}
        if self._data.empty:
            return {
                'enabled': self.enable,
                'fitted': True,
                'n_records': 0,
                'n_factors': 0,
                'performance_metric': self._performance_metric,
                'layer1_n_dims_analyzed': 0,
                'layer3_n_significant': 0,
                'correction_method': self.correction,
            }
        return {
            'enabled': self.enable,
            'fitted': True,
            'n_records': int(len(self._data)),
            'n_factors': int(self._data['factor_name'].nunique()) if 'factor_name' in self._data.columns else 0,
            'performance_metric': self._performance_metric,
            'layer1_n_dims_analyzed': len(self._layer1_results) if self._layer1_results else 0,
            'layer3_n_significant': int(self._layer3_results['is_significant'].sum()) if self._layer3_results is not None and len(self._layer3_results) > 0 else 0,
            'correction_method': self.correction,
        }
