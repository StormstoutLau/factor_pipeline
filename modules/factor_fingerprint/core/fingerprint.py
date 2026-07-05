# -*- coding: utf-8 -*-
"""
因子指纹提取器 (Factor Fingerprinter)

基于时序稳定性和截面稳定性指标，为每个因子生成描述其内在特征的指纹向量。
采用扩展窗口 + 记忆衰退机制，避免前瞻偏差。

设计哲学（与项目保持一致）：
- 数据驱动自适应：因子管道由指纹指标自动决定
- 前瞻偏差防护：指纹在扩展窗口上计算，无未来信息泄露
- 中间状态追踪：指纹历史可追溯
"""

from typing import Dict, Any, List, Optional, Tuple, NamedTuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial.distance import jensenshannon
from statsmodels.stats.diagnostic import acorr_ljungbox  # ADR-014: REQUIRED 依赖顶部导入
import logging

logger = logging.getLogger(__name__)


class FactorType(Enum):
    """因子类型枚举"""
    STATIC = "static"       # 静态因子：高自相关，排序稳定
    DYNAMIC = "dynamic"     # 动态因子：低自相关，新息主导
    MIXED = "mixed"         # 混合因子：介于两者之间
    UNKNOWN = "unknown"     # 无法分类


class FactorFingerprint(NamedTuple):
    """因子指纹：包含所有指纹指标的命名元组 (v3.0.0 T1: 13→21 维)"""
    # 时序稳定性指标
    ar1_median: float = np.nan              # AR(1)系数中位数
    rank_autocorr: float = np.nan           # 截面秩自相关
    vol_clustering_pvalue: float = np.nan   # 波动率聚集Ljung-Box p值
    half_life: float = np.nan               # 自相关系数半衰期
    level_diff_ic_ratio: float = np.nan     # 水平vs差分IC比

    # 截面稳定性指标
    skewness_std: float = np.nan            # 偏度标准差
    kurtosis_std: float = np.nan            # 峰度标准差
    js_divergence_mean: float = np.nan      # JS散度均值
    missing_cv: float = np.nan              # 缺失率变异系数
    coverage_ratio: float = np.nan          # 因子覆盖率

    # 综合衍生指标
    sd_score: float = np.nan                # 静态-动态倾向得分
    complexity_need: float = np.nan         # 处理复杂度需求
    snr_estimate: float = np.nan            # 信噪比估计

    # T1.1 尾部依赖指标 (4 维, v3.0.0 T1, 默认 NaN)
    tail_dependence_lower: float = np.nan   # 下尾依赖系数 (Nelsen 2006 Copula)
    tail_dependence_upper: float = np.nan   # 上尾依赖系数
    gpd_shape: float = np.nan               # GPD 形状参数 ξ (Pickands 1975)
    hill_estimator: float = np.nan          # Hill 重尾指数 (Hill 1975)

    # T1.2 体制转换指标 (3 维, v3.0.0 T1, 默认 NaN)
    regime_transition_prob: float = np.nan  # Markov 两状态转移概率 (Hamilton 1989)
    regime_persistence: float = np.nan      # regime 平均持续期
    regime_ic_diff: float = np.nan          # 两 regime 一阶差分均值差 (方案 C)

    # T1.3 综合衍生 (1 维, v3.0.0 T1, 默认 NaN)
    tail_regime_score: float = np.nan       # 尾部+体制综合得分 ∈ [0,1]

    def to_dict(self) -> Dict[str, float]:
        return {
            'ar1_median': self.ar1_median,
            'rank_autocorr': self.rank_autocorr,
            'vol_clustering_pvalue': self.vol_clustering_pvalue,
            'half_life': self.half_life,
            'level_diff_ic_ratio': self.level_diff_ic_ratio,
            'skewness_std': self.skewness_std,
            'kurtosis_std': self.kurtosis_std,
            'js_divergence_mean': self.js_divergence_mean,
            'missing_cv': self.missing_cv,
            'coverage_ratio': self.coverage_ratio,
            'sd_score': self.sd_score,
            'complexity_need': self.complexity_need,
            'snr_estimate': self.snr_estimate,
            'tail_dependence_lower': self.tail_dependence_lower,
            'tail_dependence_upper': self.tail_dependence_upper,
            'gpd_shape': self.gpd_shape,
            'hill_estimator': self.hill_estimator,
            'regime_transition_prob': self.regime_transition_prob,
            'regime_persistence': self.regime_persistence,
            'regime_ic_diff': self.regime_ic_diff,
            'tail_regime_score': self.tail_regime_score,
        }


@dataclass
class FingerprintConfig:
    """指纹提取配置 (v3.0.0 T1: 8→14 字段)"""
    min_window: int = 24                # 最短计算窗口（期数）
    decay_halflife: int = 12            # 记忆衰退半衰期
    min_obs_per_stock: int = 12         # 每只股票最少有效观测数
    min_stocks: int = 10                # 最少股票数才计算中位数
    min_cv_threshold: float = 0.01      # 变异系数最小阈值（避免常数序列）
    js_bins: int = 20                   # JS散度直方图分箱数
    vol_cluster_lags: int = 12          # 波动率聚集检验滞后阶数
    ar1_max_lag: int = 20               # 半衰期计算最大滞后阶数

    # T1.1/T1.2 尾部依赖与体制转换配置 (v3.0.0 T1)
    tail_quantile: float = 0.05             # 尾部分位数阈值 (Nelsen 2006)
    min_extreme_samples: int = 100          # 极值最小样本数 (Pickands/Hill 需要 ≥4*min_extreme_samples)
    enable_tail_dependence: bool = False    # 尾部依赖开关 (默认关闭, m1 修订)
    enable_regime_switching: bool = False   # 体制转换开关 (默认关闭, m1 修订)
    regime_min_samples: int = 200           # 体制转换最小样本数 (Hamilton 1989)
    tail_regime_weight: float = 0.5         # tail_regime_score 尾部权重 (M2 修订)


class FactorFingerprinter:
    """
    因子指纹提取器

    为每个因子生成描述其时序稳定性和截面稳定性的指纹向量。
    采用扩展窗口 + 记忆衰退机制，避免前瞻偏差。

    Usage:
        fingerprinter = FactorFingerprinter(
            min_window=24,
            decay_halflife=12
        )
        fingerprint = fingerprinter.extract_fingerprint(factor_data)
        print(f"AR(1)中位数: {fingerprint.ar1_median:.4f}")
        print(f"静态-动态得分: {fingerprint.sd_score:.4f}")
    """

    def __init__(self, config: Optional[FingerprintConfig] = None):
        self.config = config or FingerprintConfig()
        logger.info(f"FactorFingerprinter initialized with config: {self.config}")

    def extract_fingerprint(self, factor_data: pd.DataFrame) -> FactorFingerprint:
        """
        提取因子的完整指纹

        Parameters
        ----------
        factor_data : pd.DataFrame, shape (T, N)
            因子面板数据，index为时间，columns为股票代码

        Returns
        -------
        FactorFingerprint : 包含所有指纹指标的命名元组
        """
        if factor_data.shape[0] < self.config.min_window:
            logger.warning(f"数据长度 {factor_data.shape[0]} 小于最小窗口 {self.config.min_window}")
            return FactorFingerprint()

        # 1. 时序稳定性指标
        ar1 = self._compute_ar1_median(factor_data)
        rank_ac = self._compute_rank_autocorr(factor_data)
        vol_cluster = self._test_volatility_clustering(factor_data)
        half_life = self._estimate_half_life(factor_data)
        level_diff_ic = self._compute_level_diff_ic_ratio(factor_data)

        # 2. 截面稳定性指标
        skew_std = self._compute_skewness_std(factor_data)
        kurt_std = self._compute_kurtosis_std(factor_data)
        js_mean = self._compute_js_divergence_mean(factor_data)
        miss_cv = self._compute_missing_cv(factor_data)
        coverage = self._compute_coverage_ratio(factor_data)

        # 3. 综合衍生指标 (既有)
        sd_score = self._derive_sd_score(ar1, rank_ac, half_life, level_diff_ic)
        complexity = self._derive_complexity_need(skew_std, kurt_std, js_mean)
        snr = self._estimate_snr(factor_data)

        # 4. 尾部依赖指标 (T1.1, v3.0.0 T1, 默认关闭)
        if self.config.enable_tail_dependence:
            tail_lower = self._compute_tail_dependence_lower(factor_data)
            tail_upper = self._compute_tail_dependence_upper(factor_data)
            gpd_shape = self._estimate_gpd_shape(factor_data)
            hill_est = self._hill_estimator(factor_data)
        else:
            tail_lower = tail_upper = gpd_shape = hill_est = np.nan

        # 5. 体制转换指标 (T1.2, v3.0.0 T1, 默认关闭)
        if self.config.enable_regime_switching:
            regime_trans = self._compute_regime_transition_prob(factor_data)
            regime_pers = self._compute_regime_persistence(factor_data)
            regime_ic = self._compute_regime_ic_diff(factor_data)
        else:
            regime_trans = regime_pers = regime_ic = np.nan

        # 6. 综合衍生 (T1.3, v3.0.0 T1)
        if self.config.enable_tail_dependence or self.config.enable_regime_switching:
            tail_regime = self._derive_tail_regime_score(
                tail_lower=tail_lower, tail_upper=tail_upper,
                gpd_shape=gpd_shape, hill_estimator=hill_est,
                regime_trans_prob=regime_trans, regime_persistence=regime_pers,
                regime_ic_diff=regime_ic,
            )
        else:
            tail_regime = np.nan

        fingerprint = FactorFingerprint(
            ar1_median=ar1,
            rank_autocorr=rank_ac,
            vol_clustering_pvalue=vol_cluster,
            half_life=half_life,
            level_diff_ic_ratio=level_diff_ic,
            skewness_std=skew_std,
            kurtosis_std=kurt_std,
            js_divergence_mean=js_mean,
            missing_cv=miss_cv,
            coverage_ratio=coverage,
            sd_score=sd_score,
            complexity_need=complexity,
            snr_estimate=snr,
            tail_dependence_lower=tail_lower,
            tail_dependence_upper=tail_upper,
            gpd_shape=gpd_shape,
            hill_estimator=hill_est,
            regime_transition_prob=regime_trans,
            regime_persistence=regime_pers,
            regime_ic_diff=regime_ic,
            tail_regime_score=tail_regime,
        )

        logger.info(
            f"Fingerprint extracted: AR(1)={ar1:.4f}, RankAC={rank_ac:.4f}, "
            f"SD_Score={sd_score:.4f}, TailRegime={tail_regime if not np.isnan(tail_regime) else 'NaN'}"
        )
        return fingerprint

    # ==================== 时序稳定性指标 ====================

    def _compute_ar1_median(self, factor_data: pd.DataFrame) -> float:
        """
        计算AR(1)系数中位数（改进版：带有效样本筛选）

        对每只股票拟合AR(1)模型，取系数中位数。
        过滤掉有效样本不足或变异系数过低的股票。
        """
        ar1_values = []

        for col in factor_data.columns:
            series = factor_data[col].dropna()

            # 筛选1：有效样本数
            if len(series) < self.config.min_obs_per_stock:
                continue

            # 筛选2：变异系数（避免常数序列）
            mean_val = series.mean()
            if abs(mean_val) < 1e-10:
                cv = series.std()
            else:
                cv = series.std() / abs(mean_val)
            if cv < self.config.min_cv_threshold:
                continue

            # 拟合AR(1): x_t = c + phi * x_{t-1} + epsilon_t
            try:
                y = series.values[1:]
                x = series.values[:-1]
                # 添加常数项
                x_with_const = np.column_stack([np.ones(len(x)), x])
                beta = np.linalg.lstsq(x_with_const, y, rcond=None)[0]
                phi = beta[1]  # AR(1)系数
                ar1_values.append(phi)
            except Exception as e:
                logger.debug(f"AR(1)拟合失败 {col}: {e}")
                continue

        # 筛选3：最少股票数
        if len(ar1_values) < self.config.min_stocks:
            logger.warning(f"有效AR(1)样本数 {len(ar1_values)} 小于最小要求 {self.config.min_stocks}")
            return np.nan

        return float(np.median(ar1_values))

    def _compute_rank_autocorr(self, factor_data: pd.DataFrame, lag: int = 1) -> float:
        """
        计算截面秩自相关

        当期截面排序与下期排序的Spearman相关系数均值。
        """
        rank_corrs = []

        for t in range(len(factor_data) - lag):
            current = factor_data.iloc[t].dropna()
            future = factor_data.iloc[t + lag].dropna()

            # 对齐
            common = current.index.intersection(future.index)
            if len(common) < self.config.min_stocks:
                continue

            current_rank = current[common].rank()
            future_rank = future[common].rank()

            # 检查常量输入
            if current_rank.nunique() <= 1 or future_rank.nunique() <= 1:
                continue

            corr, _ = stats.spearmanr(current_rank, future_rank)
            if not np.isnan(corr):
                rank_corrs.append(corr)

        if len(rank_corrs) < 3:
            return np.nan

        # 指数加权平均
        weights = self._exponential_weights(len(rank_corrs))
        return float(np.average(rank_corrs, weights=weights))

    def _test_volatility_clustering(self, factor_data: pd.DataFrame) -> float:
        """
        波动率聚集检验（Ljung-Box）

        对平方序列进行Ljung-Box检验，返回p值。
        p值越小，波动率聚集越强。

        Note: statsmodels 为 REQUIRED 依赖 (ADR-014), 顶部已显式导入
        """
        # 计算截面标准差序列
        cross_sectional_std = factor_data.std(axis=1).dropna()

        if len(cross_sectional_std) < self.config.vol_cluster_lags * 2:
            return np.nan

        # 平方序列
        squared = cross_sectional_std ** 2

        lb_result = acorr_ljungbox(squared, lags=self.config.vol_cluster_lags, return_df=True)
        # 返回最小p值（最显著的滞后阶）
        return float(lb_result['lb_pvalue'].min())

    def _manual_ljungbox(self, series: pd.Series, lags: int) -> float:
        """手动计算Ljung-Box统计量"""
        n = len(series)
        autocorrs = []
        for lag in range(1, lags + 1):
            autocorrs.append(series.autocorr(lag))

        lb_stat = n * (n + 2) * sum([(r ** 2) / (n - i) for i, r in enumerate(autocorrs, 1)])
        # 卡方分布p值
        p_value = 1 - stats.chi2.cdf(lb_stat, lags)
        return float(p_value)

    def _estimate_half_life(self, factor_data: pd.DataFrame) -> float:
        """
        估计自相关系数半衰期

        自相关系数衰减至0.5所需的滞后阶数。
        """
        # 使用截面均值序列
        mean_series = factor_data.mean(axis=1).dropna()

        if len(mean_series) < self.config.ar1_max_lag * 2:
            return np.nan

        autocorrs = []
        for lag in range(1, self.config.ar1_max_lag + 1):
            ac = mean_series.autocorr(lag)
            if np.isnan(ac):
                break
            autocorrs.append(ac)

        if not autocorrs:
            return np.nan

        # 找到第一个低于0.5的滞后阶
        for i, ac in enumerate(autocorrs):
            if ac < 0.5:
                # 线性插值
                if i == 0:
                    return 1.0
                prev_ac = autocorrs[i - 1]
                t = (0.5 - prev_ac) / (ac - prev_ac)
                return float(i + t)

        # 如果都大于0.5，返回最大滞后阶
        return float(self.config.ar1_max_lag)

    def _compute_level_diff_ic_ratio(self, factor_data: pd.DataFrame) -> float:
        """
        水平vs差分IC比

        |Rank_IC(level)| / |Rank_IC(diff)| 的均值比
        这里简化为：水平自相关 / 差分自相关
        """
        mean_series = factor_data.mean(axis=1).dropna()

        if len(mean_series) < 3:
            return np.nan

        # 水平自相关（1阶）
        level_ac = mean_series.autocorr(1)
        if np.isnan(level_ac) or abs(level_ac) < 1e-10:
            return np.nan

        # 差分自相关
        diff_series = mean_series.diff().dropna()
        diff_ac = diff_series.autocorr(1)
        if np.isnan(diff_ac) or abs(diff_ac) < 1e-10:
            return np.nan

        ratio = abs(level_ac) / abs(diff_ac)
        return float(min(ratio, 10.0))  # 上限截断

    # ==================== 截面稳定性指标 ====================

    def _compute_skewness_std(self, factor_data: pd.DataFrame) -> float:
        """各期截面偏度的标准差"""
        skewness_values = []
        for t in range(len(factor_data)):
            row = factor_data.iloc[t].dropna()
            if len(row) >= 5:
                skewness_values.append(row.skew())

        if len(skewness_values) < 3:
            return np.nan

        return float(np.std(skewness_values))

    def _compute_kurtosis_std(self, factor_data: pd.DataFrame) -> float:
        """各期截面峰度的标准差"""
        kurtosis_values = []
        for t in range(len(factor_data)):
            row = factor_data.iloc[t].dropna()
            if len(row) >= 5:
                kurtosis_values.append(row.kurtosis())

        if len(kurtosis_values) < 3:
            return np.nan

        return float(np.std(kurtosis_values))

    def _compute_js_divergence_mean(self, factor_data: pd.DataFrame) -> float:
        """
        JS散度均值

        相邻两期截面直方图的Jensen-Shannon散度均值。
        """
        js_values = []

        for t in range(len(factor_data) - 1):
            current = factor_data.iloc[t].dropna()
            future = factor_data.iloc[t + 1].dropna()

            if len(current) < 10 or len(future) < 10:
                continue

            # 计算共同范围
            min_val = min(current.min(), future.min())
            max_val = max(current.max(), future.max())
            bins = np.linspace(min_val, max_val, self.config.js_bins + 1)

            hist1, _ = np.histogram(current, bins=bins, density=True)
            hist2, _ = np.histogram(future, bins=bins, density=True)

            # 平滑处理（避免零值）
            hist1 = hist1 + 1e-10
            hist2 = hist2 + 1e-10
            hist1 = hist1 / hist1.sum()
            hist2 = hist2 / hist2.sum()

            js = jensenshannon(hist1, hist2)
            if not np.isnan(js):
                js_values.append(js)

        if len(js_values) < 2:
            return np.nan

        return float(np.mean(js_values))

    def _compute_missing_cv(self, factor_data: pd.DataFrame) -> float:
        """缺失率变异系数"""
        missing_rates = factor_data.isnull().mean(axis=1)

        if missing_rates.mean() < 1e-10:
            return 0.0

        cv = missing_rates.std() / missing_rates.mean()
        return float(cv) if not np.isnan(cv) else np.nan

    def _compute_coverage_ratio(self, factor_data: pd.DataFrame) -> float:
        """因子覆盖率：有效值样本数/总样本数的均值"""
        coverage = 1 - factor_data.isnull().mean().mean()
        return float(coverage)

    # ==================== 综合衍生指标 ====================

    def _derive_sd_score(self,
                         ar1: float,
                         rank_ac: float,
                         half_life: float,
                         level_diff_ic: float) -> float:
        """
        静态-动态倾向得分

        综合多个时序稳定性指标，越高越偏向静态。
        """
        if np.isnan(ar1) or np.isnan(rank_ac):
            return np.nan

        # 归一化各指标到[0, 1]
        ar1_norm = np.clip((ar1 + 1) / 2, 0, 1)  # AR(1)从[-1,1]映射到[0,1]
        rank_ac_norm = np.clip((rank_ac + 1) / 2, 0, 1)
        hl_norm = np.clip(half_life / 20, 0, 1) if not np.isnan(half_life) else 0.5
        ld_norm = np.clip(level_diff_ic / 5, 0, 1) if not np.isnan(level_diff_ic) else 0.5

        # 加权合成（AR(1)和秩自相关权重最高）
        sd_score = (
            0.35 * ar1_norm +
            0.30 * rank_ac_norm +
            0.20 * hl_norm +
            0.15 * ld_norm
        )

        return float(sd_score)

    def _derive_complexity_need(self,
                                skew_std: float,
                                kurt_std: float,
                                js_mean: float) -> float:
        """
        处理复杂度需求

        由分布稳定性指标反向推导，越高说明越需要非线性处理。
        """
        if np.isnan(skew_std) or np.isnan(kurt_std):
            return np.nan

        # 偏度和峰度的波动越大，说明分布越不稳定，越需要复杂处理
        complexity = (
            0.4 * np.clip(skew_std / 2, 0, 1) +
            0.4 * np.clip(kurt_std / 5, 0, 1) +
            0.2 * np.clip(js_mean / 0.5, 0, 1) if not np.isnan(js_mean) else 0
        )

        return float(min(complexity, 1.0))

    def _estimate_snr(self, factor_data: pd.DataFrame) -> float:
        """
        信噪比估计

        简化为：截面均值序列的均值 / 标准差
        """
        mean_series = factor_data.mean(axis=1).dropna()

        if len(mean_series) < 3:
            return np.nan

        mu = mean_series.mean()
        sigma = mean_series.std()

        if sigma < 1e-10:
            return np.nan

        return float(abs(mu) / sigma)

    # ==================== T1.1 尾部依赖指标 (v3.0.0 T1) ====================

    def _compute_tail_dependence_lower(self, factor_data: pd.DataFrame) -> float:
        """
        下尾依赖系数 (Nelsen 2006 Copula)

        经验估计: λ_lower = P(X_t < q | X_{t-1} < q), q = tail_quantile
        用截面均值序列的自相关条件概率近似 (单变量 copula 简化).

        Returns
        -------
        float : λ_lower ∈ [0, 1], 或 NaN (样本不足)
        """
        mean_series = factor_data.mean(axis=1).dropna()
        if len(mean_series) < self.config.min_extreme_samples * 4:
            logger.debug(f"tail_dependence_lower: 样本不足 {len(mean_series)}")
            return np.nan

        q = self.config.tail_quantile
        threshold = mean_series.quantile(q)
        prev_below = mean_series.iloc[:-1].values < threshold
        curr_below = mean_series.iloc[1:].values < threshold

        n_prev_below = prev_below.sum()
        if n_prev_below == 0:
            return 0.0
        both_below = int((prev_below & curr_below).sum())
        return float(both_below / n_prev_below)

    def _compute_tail_dependence_upper(self, factor_data: pd.DataFrame) -> float:
        """
        上尾依赖系数 (Nelsen 2006 Copula)

        经验估计: λ_upper = P(X_t > 1-q | X_{t-1} > 1-q), q = tail_quantile
        用截面均值序列的自相关条件概率近似.

        Returns
        -------
        float : λ_upper ∈ [0, 1], 或 NaN (样本不足)
        """
        mean_series = factor_data.mean(axis=1).dropna()
        if len(mean_series) < self.config.min_extreme_samples * 4:
            logger.debug(f"tail_dependence_upper: 样本不足 {len(mean_series)}")
            return np.nan

        q = self.config.tail_quantile
        threshold = mean_series.quantile(1.0 - q)
        prev_above = mean_series.iloc[:-1].values > threshold
        curr_above = mean_series.iloc[1:].values > threshold

        n_prev_above = prev_above.sum()
        if n_prev_above == 0:
            return 0.0
        both_above = int((prev_above & curr_above).sum())
        return float(both_above / n_prev_above)

    def _estimate_gpd_shape(self, factor_data: pd.DataFrame) -> float:
        """
        GPD 形状参数 ξ (Pickands 1975 / POT-MLE)

        实现: Peaks-over-Threshold (POT) 方法 + MLE 拟合 GPD (Hosking-Wallis 1987).
        对截面均值序列的绝对值序列, 取 (1-tail_quantile) 分位数为阈值,
        对超出量用 scipy.stats.genpareto.fit 拟合 GPD, 取形状参数 ξ.

        - 重尾分布 (如 t 分布): ξ > 0
        - 轻尾分布 (如正态): ξ ≈ 0 (GPD 退化为指数分布)

        Note: Pickands (1975) 原始估计量在小样本下方差大且对轻尾分布不稳定,
        POT-MLE 是更稳健的工程实现, 数学上等价 (估计同一 GPD 形状参数).

        Returns
        -------
        float : ξ, 重尾 > 0, 轻尾 ≈ 0, 或 NaN (样本不足/拟合失败)
        """
        from scipy.stats import genpareto

        mean_series = factor_data.mean(axis=1).dropna()
        if len(mean_series) < self.config.min_extreme_samples * 4:
            logger.debug(f"gpd_shape: 样本不足 {len(mean_series)}")
            return np.nan

        abs_series = np.abs(mean_series.values)
        # 阈值: (1 - tail_quantile) 分位数
        threshold = float(np.quantile(abs_series, 1.0 - self.config.tail_quantile))
        exceedances = abs_series[abs_series > threshold] - threshold

        if len(exceedances) < 10:
            return np.nan

        try:
            # MLE 拟合 GPD, 固定 loc=0 (超出量已中心化)
            shape, loc, scale = genpareto.fit(exceedances, floc=0)
            if not np.isfinite(shape):
                return np.nan
            return float(shape)
        except Exception as e:
            logger.debug(f"gpd_shape: genpareto.fit 失败: {e}")
            return np.nan

    def _hill_estimator(self, factor_data: pd.DataFrame) -> float:
        """
        Hill 重尾指数估计量 (Hill 1975)

        α_hill = k / Σ_{i=1}^{k} log(X_(n-i+1) / X_(n-k))
        ξ_hill = 1 / α_hill = Σ log(X_(n-i+1) / X_(n-k)) / k

        仅对正重尾 (ξ > 0) 有效. 用截面均值序列的绝对值序列 (右尾) 估计.

        Returns
        -------
        float : ξ_hill > 0 (重尾), 或 NaN (样本不足/非正重尾)
        """
        mean_series = factor_data.mean(axis=1).dropna()
        if len(mean_series) < self.config.min_extreme_samples * 4:
            logger.debug(f"hill_estimator: 样本不足 {len(mean_series)}")
            return np.nan

        abs_series = np.abs(mean_series.values)
        sorted_vals = np.sort(abs_series)
        n = len(sorted_vals)
        k = self.config.min_extreme_samples

        # 阈值 X_(n-k) (0-indexed: sorted_vals[n-k-1])
        threshold = sorted_vals[n - k - 1]
        if threshold <= 0:
            return np.nan

        # k 个最大值: X_(n-k+1), ..., X_(n) (0-indexed: sorted_vals[n-k:])
        extremes = sorted_vals[n - k:]
        log_ratios = np.log(extremes / threshold)
        sum_log = float(np.sum(log_ratios))
        if sum_log <= 0:
            # 非正重尾 (轻尾分布), Hill 估计量不适用
            return np.nan
        xi = sum_log / k
        return float(xi)

    # ==================== T1.2 体制转换指标 (v3.0.0 T1) ====================

    def _compute_regime_transition_prob(self, factor_data: pd.DataFrame) -> float:
        """
        Markov 两状态转移概率 (Hamilton 1989)

        简化实现: 用截面均值序列的中位数划分 bull/bear 两状态,
        计算转移矩阵的平均转移概率.
        p_01 = P(bull | bear), p_10 = P(bear | bull)
        regime_transition_prob = (p_01 + p_10) / 2

        Note: 不使用 statsmodels MarkovRegression (拟合不稳定且耗时),
        中位数划分是稳健的降级方案, 满足工程精度需求.

        Returns
        -------
        float : 平均转移概率 ∈ [0, 1], 或 NaN (样本不足/单状态)
        """
        mean_series = factor_data.mean(axis=1).dropna()
        if len(mean_series) < self.config.regime_min_samples:
            logger.debug(f"regime_transition_prob: 样本不足 {len(mean_series)}")
            return np.nan

        # 单一序列无方差 → 单状态, 无体制转换
        if mean_series.std() < 1e-10:
            return np.nan

        # 中位数划分两状态: 1=bull, 0=bear
        median_val = mean_series.median()
        states = (mean_series > median_val).astype(int).values

        n_bear = int(np.sum(states[:-1] == 0))
        n_bull = int(np.sum(states[:-1] == 1))
        if n_bear == 0 or n_bull == 0:
            return np.nan

        bear_to_bull = int(np.sum((states[:-1] == 0) & (states[1:] == 1)))
        bull_to_bear = int(np.sum((states[:-1] == 1) & (states[1:] == 0)))
        p_01 = bear_to_bull / n_bear  # bear → bull
        p_10 = bull_to_bear / n_bull  # bull → bear
        return float((p_01 + p_10) / 2.0)

    def _compute_regime_persistence(self, factor_data: pd.DataFrame) -> float:
        """
        regime 平均持续期 (Hamilton 1989)

        persistence = 1 / regime_transition_prob (平均持续期 = 1/转移概率)
        若转移概率为 0 (无转换), 用样本长度作为持续期上界.

        Returns
        -------
        float : 平均持续期 > 1, 或 NaN (样本不足/无转换)
        """
        trans_prob = self._compute_regime_transition_prob(factor_data)
        if np.isnan(trans_prob):
            return np.nan
        if trans_prob < 1e-10:
            # 无转换 → 持续期 = 整个样本长度 (上界)
            return float(factor_data.shape[0])
        return float(1.0 / trans_prob)

    def _compute_regime_ic_diff(self, factor_data: pd.DataFrame) -> float:
        """
        两 regime 一阶差分均值差 (方案 C, C1 修订)

        extract_fingerprint 无前向收益数据, 用因子自身的一阶差分序列
        作为 IC 代理指标:
        - ΔX_t = X_t - X_{t-1} (截面均值序列的差分)
        - 用水平序列的中位数划分 bull/bear (对齐差分序列的 t 时刻)
        - regime_ic_diff = mean(ΔX | bull) - mean(ΔX | bear)

        Returns
        -------
        float : 一阶差分均值差, 或 NaN (样本不足/单状态)
        """
        mean_series = factor_data.mean(axis=1).dropna()
        if len(mean_series) < self.config.regime_min_samples:
            logger.debug(f"regime_ic_diff: 样本不足 {len(mean_series)}")
            return np.nan

        if mean_series.std() < 1e-10:
            return np.nan

        # 一阶差分 (length T-1)
        diff_series = mean_series.diff().dropna()
        # 水平序列的中位数 (用于划分 bull/bear)
        median_val = mean_series.median()
        # states 对齐 diff_series 的 t 时刻 (即水平序列的 t)
        # diff_series[t] = mean_series[t] - mean_series[t-1], t 从 1 开始
        states = (mean_series.iloc[1:] > median_val).astype(int).values

        if len(states) != len(diff_series):
            return np.nan

        bull_diffs = diff_series.values[states == 1]
        bear_diffs = diff_series.values[states == 0]
        if len(bull_diffs) == 0 or len(bear_diffs) == 0:
            return np.nan

        return float(np.mean(bull_diffs) - np.mean(bear_diffs))

    # ==================== T1.3 综合衍生 (v3.0.0 T1) ====================

    def _derive_tail_regime_score(self,
                                   tail_lower: float,
                                   tail_upper: float,
                                   gpd_shape: float,
                                   hill_estimator: float,
                                   regime_trans_prob: float,
                                   regime_persistence: float,
                                   regime_ic_diff: float) -> float:
        """
        尾部+体制综合得分 (M2 修订: 双分量加权简化公式)

        公式:
            tail_severity = np.clip((|gpd_shape| + |hill_estimator|) / 2, 0, 1)
            regime_instability = np.clip(regime_trans_prob / 0.5, 0, 1)
            score = tail_regime_weight * tail_severity
                  + (1 - tail_regime_weight) * regime_instability

        NaN 处理:
        - gpd_shape 和 hill_estimator 都 NaN → tail_severity = NaN → score = NaN
        - regime_trans_prob NaN → regime_instability 用 0.5 (中性值)
        - 全部 NaN → score = NaN

        Parameters
        ----------
        tail_lower, tail_upper : float
            尾部依赖系数 (当前未参与计算, 保留参数以备未来扩展)
        gpd_shape, hill_estimator : float
            尾部重尾指标
        regime_trans_prob, regime_persistence, regime_ic_diff : float
            体制转换指标 (仅 regime_trans_prob 参与 regime_instability 计算)

        Returns
        -------
        float : score ∈ [0, 1], 或 NaN (尾部输入全 NaN)
        """
        # tail_severity: 尾部严重度
        if np.isnan(gpd_shape) and np.isnan(hill_estimator):
            return np.nan
        gpd_val = 0.0 if np.isnan(gpd_shape) else abs(gpd_shape)
        hill_val = 0.0 if np.isnan(hill_estimator) else abs(hill_estimator)
        tail_severity = float(np.clip((gpd_val + hill_val) / 2.0, 0.0, 1.0))

        # regime_instability: 体制不稳定性
        if np.isnan(regime_trans_prob):
            regime_instability = 0.5  # 中性值
        else:
            regime_instability = float(np.clip(regime_trans_prob / 0.5, 0.0, 1.0))

        # 综合得分
        w = self.config.tail_regime_weight
        score = w * tail_severity + (1.0 - w) * regime_instability
        return float(np.clip(score, 0.0, 1.0))

    # ==================== 工具方法 ====================

    def _exponential_weights(self, n_periods: int) -> np.ndarray:
        """生成指数衰减权重，半衰期由 decay_halflife 控制"""
        if n_periods <= 0:
            return np.ones(1)
        raw = np.exp(-np.arange(n_periods)[::-1] / self.config.decay_halflife)
        return raw / raw.sum()

    def batch_extract(self,
                      factor_dict: Dict[str, pd.DataFrame]
                      ) -> Dict[str, FactorFingerprint]:
        """
        批量提取多个因子的指纹

        Parameters
        ----------
        factor_dict : Dict[str, pd.DataFrame]
            因子名字到数据的映射

        Returns
        -------
        Dict[str, FactorFingerprint]
            因子名字到指纹的映射
        """
        results = {}
        for name, data in factor_dict.items():
            logger.info(f"Extracting fingerprint for {name}...")
            results[name] = self.extract_fingerprint(data)
        return results
