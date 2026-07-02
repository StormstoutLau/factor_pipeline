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
import logging

logger = logging.getLogger(__name__)


class FactorType(Enum):
    """因子类型枚举"""
    STATIC = "static"       # 静态因子：高自相关，排序稳定
    DYNAMIC = "dynamic"     # 动态因子：低自相关，新息主导
    MIXED = "mixed"         # 混合因子：介于两者之间
    UNKNOWN = "unknown"     # 无法分类


class FactorFingerprint(NamedTuple):
    """因子指纹：包含所有指纹指标的命名元组"""
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
        }


@dataclass
class FingerprintConfig:
    """指纹提取配置"""
    min_window: int = 24                # 最短计算窗口（期数）
    decay_halflife: int = 12            # 记忆衰退半衰期
    min_obs_per_stock: int = 12         # 每只股票最少有效观测数
    min_stocks: int = 10                # 最少股票数才计算中位数
    min_cv_threshold: float = 0.01      # 变异系数最小阈值（避免常数序列）
    js_bins: int = 20                   # JS散度直方图分箱数
    vol_cluster_lags: int = 12          # 波动率聚集检验滞后阶数
    ar1_max_lag: int = 20               # 半衰期计算最大滞后阶数


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

        # 3. 综合衍生指标
        sd_score = self._derive_sd_score(ar1, rank_ac, half_life, level_diff_ic)
        complexity = self._derive_complexity_need(skew_std, kurt_std, js_mean)
        snr = self._estimate_snr(factor_data)

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
            snr_estimate=snr
        )

        logger.info(f"Fingerprint extracted: AR(1)={ar1:.4f}, RankAC={rank_ac:.4f}, SD_Score={sd_score:.4f}")
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
        """
        # 计算截面标准差序列
        cross_sectional_std = factor_data.std(axis=1).dropna()

        if len(cross_sectional_std) < self.config.vol_cluster_lags * 2:
            return np.nan

        # 平方序列
        squared = cross_sectional_std ** 2

        try:
            from statsmodels.stats.diagnostic import acorr_ljungbox
            lb_result = acorr_ljungbox(squared, lags=self.config.vol_cluster_lags, return_df=True)
            # 返回最小p值（最显著的滞后阶）
            return float(lb_result['lb_pvalue'].min())
        except ImportError:
            # 回退：手动计算Ljung-Box
            return self._manual_ljungbox(squared, self.config.vol_cluster_lags)

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
