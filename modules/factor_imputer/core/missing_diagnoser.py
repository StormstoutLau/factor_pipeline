# -*- coding: utf-8 -*-
"""
缺失类型诊断器
专门诊断因子数据的缺失类型、模式和机制
"""

import warnings
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from .base import BaseDiagnoser, MissingDiagnosisResult, MissingPattern, MissingType


class MissingTypeDiagnoser(BaseDiagnoser):
    """缺失类型诊断器"""

    def __init__(self, **params):
        super().__init__(**params)
        self.statistical_tests = {
            "little_mcar_test": True,
            "missing_pattern_test": True,
            "correlation_analysis": True,
            "temporal_analysis": True,
        }

    def diagnose(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        执行完整的缺失诊断

        Parameters:
        -----------
        data : pd.DataFrame
            因子数据，行为时间，列为资产

        Returns:
        --------
        diagnosis : Dict[str, Any]
            完整的诊断结果
        """
        result = MissingDiagnosisResult()

        # 1. 基础缺失信息
        missing_info = self._analyze_missing_basic(data)

        # 2. 缺失模式分析
        pattern_analysis = self._analyze_missing_pattern(data)

        # 3. 缺失机制检测
        mechanism_analysis = self._detect_missing_mechanism(data)

        # 4. 时序结构分析
        temporal_analysis = self._analyze_temporal_structure(data)

        # 5. 截面结构分析
        cross_sectional_analysis = self._analyze_cross_sectional_structure(data)

        # 6. 质量评估
        quality_assessment = self._assess_data_quality(data, missing_info)

        # 7. 生成建议
        recommendations = self._generate_recommendations(missing_info, pattern_analysis, mechanism_analysis)

        # 填充结果
        result.missing_type = mechanism_analysis["missing_type"]
        result.missing_pattern = pattern_analysis["dominant_pattern"]
        result.missing_rate = missing_info
        result.temporal_structure = temporal_analysis
        result.cross_sectional_structure = cross_sectional_analysis
        result.recommendations = recommendations
        result.overall_quality_score = quality_assessment["overall_score"]
        result.mechanism_analysis = mechanism_analysis  # v3.1.0 E3 S1: 暴露 mcar_test p_value

        # 保存诊断历史
        self.diagnosis_history.append(result.to_dict())

        return result.to_dict()

    def _analyze_missing_basic(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析基础缺失信息"""
        total_elements = data.shape[0] * data.shape[1]
        missing_elements = data.isnull().sum().sum()

        # 整体缺失率
        overall_missing_rate = missing_elements / total_elements

        # 按时间点缺失率
        time_missing_rate = data.isnull().mean(axis=1)

        # 按资产缺失率
        asset_missing_rate = data.isnull().mean(axis=0)

        # 缺失分布统计
        missing_distribution = {
            "complete_cases": data.dropna().shape[0],
            "complete_assets": data.dropna(axis=1).shape[1],
            "missing_by_time": time_missing_rate.describe().to_dict(),
            "missing_by_asset": asset_missing_rate.describe().to_dict(),
        }

        return {
            "overall_rate": overall_missing_rate,
            "total_missing": missing_elements,
            "total_elements": total_elements,
            "time_missing_rate": time_missing_rate.to_dict(),
            "asset_missing_rate": asset_missing_rate.to_dict(),
            "distribution": missing_distribution,
            "severity_level": self._classify_missing_severity(overall_missing_rate),
        }

    def _analyze_missing_pattern(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析缺失模式"""
        missing_mask = data.isnull()

        # 1. 检测块状缺失
        block_analysis = self._detect_missing_blocks(missing_mask)

        # 2. 检测时序缺失模式
        temporal_pattern = self._detect_temporal_missing_pattern(missing_mask)

        # 3. 检测截面缺失模式
        cross_sectional_pattern = self._detect_cross_sectional_pattern(missing_mask)

        # 4. 检测随机缺失模式
        random_pattern = self._detect_random_missing_pattern(missing_mask)

        # 确定主导模式
        pattern_scores = {
            MissingPattern.BLOCK.value: block_analysis["score"],
            MissingPattern.TIME_SERIES.value: temporal_pattern["score"],
            MissingPattern.CROSS_SECTIONAL.value: cross_sectional_pattern["score"],
            MissingPattern.RANDOM.value: random_pattern["score"],
        }

        dominant_pattern = max(pattern_scores, key=pattern_scores.get)

        return {
            "dominant_pattern": dominant_pattern,
            "pattern_scores": pattern_scores,
            "block_analysis": block_analysis,
            "temporal_pattern": temporal_pattern,
            "cross_sectional_pattern": cross_sectional_pattern,
            "random_pattern": random_pattern,
        }

    def _detect_missing_mechanism(self, data: pd.DataFrame) -> Dict[str, Any]:
        """检测缺失机制"""
        missing_mask = data.isnull()

        # 1. Little's MCAR检验 (EM-based χ²)
        mcar_test = self._little_mcar_test(data.values)

        # 2. 观察数据与缺失模式的相关性
        correlation_analysis = self._missing_data_correlation(data, missing_mask)

        # 3. 时序依赖性分析
        temporal_dependency = self._temporal_missing_dependency(data, missing_mask)

        # 综合判断缺失机制
        mechanism_score = self._calculate_mechanism_score(mcar_test, correlation_analysis, temporal_dependency)

        missing_type = self._determine_missing_type(mechanism_score)

        return {
            "missing_type": missing_type,
            "mcar_test": mcar_test,
            "correlation_analysis": correlation_analysis,
            "temporal_dependency": temporal_dependency,
            "mechanism_score": mechanism_score,
            "confidence": self._calculate_confidence(mechanism_score),
        }

    def _analyze_temporal_structure(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析时序结构"""
        if not isinstance(data.index, pd.DatetimeIndex):
            return {"has_time_index": False}

        # 时间频率分析
        frequency_analysis = self._analyze_time_frequency(data)

        # 连续缺失分析
        consecutive_analysis = self._analyze_consecutive_missing(data)

        # 季节性缺失分析
        seasonal_analysis = self._analyze_seasonal_missing(data)

        # 趋势性缺失分析
        trend_analysis = self._analyze_missing_trend(data)

        return {
            "has_time_index": True,
            "frequency_analysis": frequency_analysis,
            "consecutive_analysis": consecutive_analysis,
            "seasonal_analysis": seasonal_analysis,
            "trend_analysis": trend_analysis,
        }

    def _analyze_cross_sectional_structure(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析截面结构"""
        # 资产相似性分析
        similarity_analysis = self._analyze_asset_similarity(data)

        # 截面缺失聚集性分析
        clustering_analysis = self._analyze_missing_clustering(data)

        # 行业/市值分组分析（如果有元数据）
        group_analysis = self._analyze_group_structure(data)

        return {
            "similarity_analysis": similarity_analysis,
            "clustering_analysis": clustering_analysis,
            "group_analysis": group_analysis,
        }

    def _detect_missing_blocks(self, missing_mask: pd.DataFrame) -> Dict[str, Any]:
        """检测块状缺失"""
        # 使用连通分量分析检测缺失块
        from scipy.ndimage import label

        # 将缺失掩码转换为二值数组
        missing_array = missing_mask.values.astype(int)

        # 标记连通区域
        labeled_array, num_features = label(missing_array)

        # 计算每个块的大小
        block_sizes = []
        for i in range(1, num_features + 1):
            block_size = np.sum(labeled_array == i)
            block_sizes.append(block_size)

        max_block_size = max(block_sizes) if block_sizes else 0
        total_missing = np.sum(missing_array)

        # 计算块状缺失得分
        block_score = max_block_size / total_missing if total_missing > 0 else 0

        return {
            "num_blocks": num_features,
            "max_block_size": max_block_size,
            "block_sizes": block_sizes,
            "score": block_score,
            "is_block_missing": block_score > 0.1,
        }

    def _detect_temporal_missing_pattern(self, missing_mask: pd.DataFrame) -> Dict[str, Any]:
        """检测时序缺失模式"""
        # 计算每个时间点的缺失率
        time_missing_rate = missing_mask.mean(axis=1)

        # 检测连续高缺失率时段
        consecutive_high_missing = 0
        max_consecutive_high = 0

        for rate in time_missing_rate:
            if rate > 0.5:  # 阈值可调整
                consecutive_high_missing += 1
                max_consecutive_high = max(max_consecutive_high, consecutive_high_missing)
            else:
                consecutive_high_missing = 0

        # 计算时序缺失得分
        temporal_score = max_consecutive_high / len(time_missing_rate)

        return {
            "max_consecutive_high_missing": max_consecutive_high,
            "time_missing_rate": time_missing_rate.describe().to_dict(),
            "score": temporal_score,
            "is_temporal_missing": temporal_score > 0.05,
        }

    def _detect_cross_sectional_pattern(self, missing_mask: pd.DataFrame) -> Dict[str, Any]:
        """检测截面缺失模式"""
        # 计算每个资产的缺失率
        asset_missing_rate = missing_mask.mean(axis=0)

        # 计算缺失率的熵
        entropy = -np.sum(asset_missing_rate * np.log(asset_missing_rate + 1e-10))

        # 检测同时缺失的资产对
        simultaneous_missing = self._detect_simultaneous_missing(missing_mask)

        # 计算截面缺失得分
        cross_sectional_score = 1 - (entropy / np.log(len(asset_missing_rate)))

        return {
            "asset_missing_entropy": entropy,
            "simultaneous_missing": simultaneous_missing,
            "score": cross_sectional_score,
            "is_cross_sectional_missing": cross_sectional_score > 0.3,
        }

    def _detect_random_missing_pattern(self, missing_mask: pd.DataFrame) -> Dict[str, Any]:
        """检测随机缺失模式"""
        # 计算缺失位置的随机性
        total_missing = missing_mask.sum().sum()

        if total_missing == 0:
            return {"score": 0, "is_random_missing": False}

        # 使用卡方检验检验缺失的随机性
        expected_missing_per_cell = total_missing / (missing_mask.shape[0] * missing_mask.shape[1])

        # 计算实际缺失分布与期望分布的差异
        observed_missing = missing_mask.values.flatten()
        expected_distribution = np.full_like(observed_missing, expected_missing_per_cell)

        # 卡方统计量
        observed_missing = observed_missing.astype(int)
        chi2_stat = np.sum((observed_missing - expected_distribution) ** 2 / (expected_distribution + 1e-10))

        # 随机性得分（卡方值越小越随机）
        random_score = 1 / (1 + chi2_stat)

        return {
            "chi2_statistic": chi2_stat,
            "expected_missing_per_cell": expected_missing_per_cell,
            "score": random_score,
            "is_random_missing": random_score > 0.7,
        }

    def _little_mcar_test(self, data: np.ndarray) -> Dict[str, Any]:
        """Little (1988) MCAR test: EM-based chi-squared test.

        Little, R. J. A. (1988). "A Test of Missing Completely at Random
        for Multivariate Data with Missing Values."
        JASA, 83(404), 1198-1202.

        Algorithm:
        1. EM estimation of μ̂, Σ̂
        2. Group observations by missingness pattern (optimized: pattern grouping)
        3. For each pattern g, d²_g = n_g · (ȳ_g - μ̂_g)′ Σ̂_g⁻¹ (ȳ_g - μ̂_g)
        4. d² = Σ_g d²_g ~ χ²(Σ_g k_g - k) under MCAR

        Args:
            data: (T, N) numpy array with NaN for missing values.

        Returns:
            dict with 'statistic', 'p_value', 'df', 'patterns', 'is_mcar'
        """
        from scipy.stats import chi2

        T, N = data.shape
        if N < 2:
            return {'statistic': np.nan, 'p_value': np.nan, 'df': 0, 'patterns': 0, 'is_mcar': False}

        # Step 1: EM estimation of μ, Σ
        mu, sigma = self._em_estimate(data)

        # Step 2: Identify missingness patterns (optimized: group by pattern)
        patterns = self._group_by_missingness(data)

        if len(patterns) < 2:
            return {'statistic': 0.0, 'p_value': 1.0, 'df': 0, 'patterns': 1, 'is_mcar': True}

        # Step 3: d² statistic
        d2 = 0.0
        total_df = 0
        for mask_tuple, indices in patterns.items():
            if len(indices) < 2:
                continue
            group_data = data[indices]
            nan_mask = np.array(mask_tuple)  # True = NaN (missing)
            observed_cols = np.where(~nan_mask)[0]  # not NaN
            if len(observed_cols) == 0:
                continue

            mu_g = mu[observed_cols]
            sigma_g = sigma[np.ix_(observed_cols, observed_cols)]

            # Group mean of observed variables
            y_bar_g = np.nanmean(group_data[:, observed_cols], axis=0)

            # Mahalanobis distance
            try:
                sigma_inv = np.linalg.inv(sigma_g)
                diff = y_bar_g - mu_g
                d2 += len(indices) * diff @ sigma_inv @ diff
            except np.linalg.LinAlgError:
                d2 += 0  # Skip singular covariance

            total_df += len(observed_cols)

        total_df -= N  # Subtract total parameters
        total_df = max(total_df, 1)

        p_value = float(1 - chi2.cdf(d2, total_df))
        return {
            'statistic': float(d2),
            'p_value': p_value,
            'df': total_df,
            'patterns': len(patterns),
            'is_mcar': p_value > 0.05,
        }

    def _em_estimate(
        self, data: np.ndarray, max_iter: int = 100, tol: float = 1e-6
    ):
        """EM algorithm for multivariate normal mean and covariance
        with missing data. Optimized with missingness pattern grouping.

        Complexity: O(max_iter × P × N³) where P = number of distinct
        missingness patterns (typically P << T).

        Args:
            data: (T, N) numpy array with NaN for missing values.
            max_iter: maximum EM iterations.
            tol: convergence tolerance for mean change.

        Returns:
            mu: (N,) estimated mean vector.
            sigma: (N, N) estimated covariance matrix.
        """
        T, N = data.shape
        # Initialize with complete-case estimates
        mu = np.nanmean(data, axis=0)
        # Handle all-NaN columns
        mu = np.where(np.isnan(mu), 0.0, mu)
        sigma = np.ma.cov(np.ma.masked_invalid(data), rowvar=False).data
        sigma = np.nan_to_num(sigma, nan=0.0, posinf=0.0, neginf=0.0)

        # 识别缺失模式 → 分组 (优化: 避免逐观测求逆)
        pattern_groups = self._group_by_missingness(data)

        for iteration in range(max_iter):
            mu_old = mu.copy()

            # E-step: 按模式分组计算，非逐观测
            data_imputed = data.copy()
            for mask_tuple, indices in pattern_groups.items():
                nan_mask = np.array(mask_tuple)  # True = NaN (missing)
                observed = ~nan_mask  # True = observed (not NaN)
                missing = nan_mask   # True = missing (NaN)

                if not observed.any() or not missing.any():
                    continue

                sigma_oo = sigma[np.ix_(observed, observed)]
                sigma_mo = sigma[np.ix_(missing, observed)]

                try:
                    sigma_oo_inv = np.linalg.inv(sigma_oo)
                    beta = sigma_mo @ sigma_oo_inv  # 一次求逆，全体复用
                except np.linalg.LinAlgError:
                    beta = np.zeros((missing.sum(), observed.sum()))

                # 对所有同模式观测批量计算
                group_data = data[indices]
                diff = group_data[:, observed] - mu[observed]  # (n_group, n_obs)
                imputed = mu[missing] + diff @ beta.T  # (n_group, n_miss)
                data_imputed[np.ix_(indices, np.where(missing)[0])] = imputed

            # M-step: update μ, Σ
            mu_new = np.mean(data_imputed, axis=0)
            sigma_new = np.cov(data_imputed, rowvar=False)

            # 收敛检查
            if np.max(np.abs(mu_new - mu_old)) < tol:
                mu, sigma = mu_new, sigma_new
                break
            mu, sigma = mu_new, sigma_new

        return mu, sigma

    @staticmethod
    def _group_by_missingness(data: np.ndarray) -> dict:
        """Group observations by missingness pattern.

        Maps each distinct missingness pattern (tuple of booleans) to
        the indices of observations sharing that pattern.

        Args:
            data: (T, N) numpy array with NaN values.

        Returns:
            dict mapping pattern tuple → numpy array of indices.
        """
        pattern_map = {}
        mask = np.isnan(data)
        for i in range(data.shape[0]):
            pattern = tuple(mask[i].tolist())
            if pattern not in pattern_map:
                pattern_map[pattern] = []
            pattern_map[pattern].append(i)
        return {k: np.array(v) for k, v in pattern_map.items()}

    def _missing_data_correlation(self, data: pd.DataFrame, missing_mask: pd.DataFrame) -> Dict[str, Any]:
        """分析观察数据与缺失模式的相关性"""
        # 计算每个资产的缺失指示变量
        missing_indicators = missing_mask.astype(int)

        # 计算观察数据与缺失指示变量的相关性
        correlations = {}

        for asset in data.columns:
            asset_data = data[asset].dropna()
            asset_missing = missing_indicators[asset].loc[asset_data.index]

            if len(asset_data) > 10:
                correlation = np.corrcoef(asset_data, asset_missing)[0, 1]
                correlations[asset] = correlation

        # 计算平均绝对相关性
        avg_abs_correlation = np.mean([abs(c) for c in correlations.values()])

        return {
            "correlations": correlations,
            "avg_abs_correlation": avg_abs_correlation,
            "max_correlation": max([abs(c) for c in correlations.values()]) if correlations else 0,
        }

    def _temporal_missing_dependency(self, data: pd.DataFrame, missing_mask: pd.DataFrame) -> Dict[str, Any]:
        """分析时序缺失依赖性"""
        if not isinstance(data.index, pd.DatetimeIndex):
            return {"has_temporal_dependency": False}

        # 计算滞后缺失相关性
        lag_correlations = {}

        for lag in [1, 2, 5, 10]:  # 不同的滞后阶数
            if lag < len(data):
                current_missing = missing_mask.iloc[:, 0].values[lag:]
                lagged_missing = missing_mask.iloc[:, 0].values[:-lag]

                correlation = np.corrcoef(current_missing, lagged_missing)[0, 1]
                lag_correlations[f"lag_{lag}"] = correlation

        # 判断是否存在时序依赖
        max_lag_correlation = max([abs(c) for c in lag_correlations.values()])

        return {
            "lag_correlations": lag_correlations,
            "max_lag_correlation": max_lag_correlation,
            "has_temporal_dependency": max_lag_correlation > 0.3,
        }

    def _calculate_mechanism_score(
        self, mcar_test: Dict, correlation_analysis: Dict, temporal_dependency: Dict
    ) -> Dict[str, float]:
        """计算缺失机制得分"""
        scores = {
            "mcar_score": 1.0 if mcar_test.get("is_mcar", False) else 0.0,
            "mar_score": min(correlation_analysis.get("avg_abs_correlation", 0) * 2, 1.0),
            "mnar_score": temporal_dependency.get("max_lag_correlation", 0),
        }

        return scores

    def _determine_missing_type(self, mechanism_score: Dict[str, float]) -> str:
        """确定缺失类型"""
        if mechanism_score["mcar_score"] > 0.7:
            return MissingType.MCAR.value
        elif mechanism_score["mar_score"] > mechanism_score["mnar_score"]:
            return MissingType.MAR.value
        else:
            return MissingType.MNAR.value

    def _calculate_confidence(self, mechanism_score: Dict[str, float]) -> float:
        """计算判断置信度"""
        max_score = max(mechanism_score.values())
        second_max_score = sorted(mechanism_score.values())[-2]

        confidence = (max_score - second_max_score) / max_score if max_score > 0 else 0
        return confidence

    def _classify_missing_severity(self, missing_rate: float) -> str:
        """分类缺失严重程度"""
        if missing_rate < 0.05:
            return "low"
        elif missing_rate < 0.20:
            return "moderate"
        elif missing_rate < 0.50:
            return "high"
        else:
            return "severe"

    def _identify_missing_patterns(self, missing_mask: pd.DataFrame) -> List[pd.DataFrame]:
        """识别不同的缺失模式"""
        # 将缺失掩码转换为字符串模式
        patterns = missing_mask.apply(lambda row: "".join(row.astype(str).values), axis=1)
        unique_patterns = patterns.unique()

        pattern_masks = []
        for pattern in unique_patterns:
            mask = patterns == pattern
            pattern_masks.append(mask)

        return pattern_masks

    def _detect_simultaneous_missing(self, missing_mask: pd.DataFrame) -> Dict[str, Any]:
        """检测同时缺失的资产对"""
        # 计算资产间的缺失重叠
        missing_overlap = missing_mask.T.dot(missing_mask)

        # 找出重叠最多的资产对
        max_overlap = 0
        max_pair = None

        for i in range(len(missing_overlap.columns)):
            for j in range(i + 1, len(missing_overlap.columns)):
                overlap = missing_overlap.iloc[i, j]
                if overlap > max_overlap:
                    max_overlap = overlap
                    max_pair = (missing_overlap.columns[i], missing_overlap.columns[j])

        return {"max_overlap": max_overlap, "max_pair": max_pair, "overlap_matrix": missing_overlap}

    def _analyze_time_frequency(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析时间频率"""
        try:
            freq = pd.infer_freq(data.index)
            return {"inferred_frequency": freq, "is_regular": freq is not None}
        except (ValueError, TypeError):
            return {"inferred_frequency": "unknown", "is_regular": False}

    def _analyze_consecutive_missing(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析连续缺失"""
        missing_mask = data.isnull()

        consecutive_stats = {}
        for asset in data.columns:
            max_consecutive = 0
            current_consecutive = 0

            for is_missing in missing_mask[asset]:
                if is_missing:
                    current_consecutive += 1
                    max_consecutive = max(max_consecutive, current_consecutive)
                else:
                    current_consecutive = 0

            consecutive_stats[asset] = max_consecutive

        return {
            "max_consecutive_missing": max(consecutive_stats.values()),
            "by_asset": consecutive_stats,
            "avg_consecutive_missing": np.mean(list(consecutive_stats.values())),
        }

    def _analyze_seasonal_missing(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析季节性缺失"""
        if not isinstance(data.index, pd.DatetimeIndex):
            return {"has_seasonal_pattern": False}

        # 按月份分析缺失模式
        monthly_missing = data.isnull().groupby(data.index.month).mean()

        # 检测季节性模式
        monthly_std = monthly_missing.std().mean()

        return {
            "monthly_missing_rate": monthly_missing.mean().to_dict(),
            "monthly_std": monthly_std,
            "has_seasonal_pattern": monthly_std > 0.1,
        }

    def _analyze_missing_trend(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析缺失趋势"""
        time_missing_rate = data.isnull().mean(axis=1)

        # 计算缺失率的时间趋势
        x = np.arange(len(time_missing_rate))
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, time_missing_rate)

        return {
            "trend_slope": slope,
            "trend_r_squared": r_value**2,
            "trend_p_value": p_value,
            "has_trend": p_value < 0.05,
        }

    def _analyze_asset_similarity(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析资产相似性"""
        # 计算资产间的相关性
        correlation_matrix = data.corr()

        # 提取上三角矩阵
        upper_triangle = correlation_matrix.where(np.triu(np.ones(correlation_matrix.shape), k=1).astype(bool))

        correlations = upper_triangle.stack().values

        return {
            "mean_correlation": np.mean(correlations),
            "std_correlation": np.std(correlations),
            "min_correlation": np.min(correlations),
            "max_correlation": np.max(correlations),
            "correlation_distribution": {
                "q25": np.percentile(correlations, 25),
                "q50": np.percentile(correlations, 50),
                "q75": np.percentile(correlations, 75),
            },
        }

    def _analyze_missing_clustering(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析缺失聚集性"""
        missing_mask = data.isnull()

        # 计算缺失的Moran's I（空间自相关）
        # 这里使用简化的方法
        missing_rate = missing_mask.mean(axis=1)

        # 计算缺失率的空间自相关
        lag_missing_rate = missing_rate.shift(1).fillna(missing_rate)
        moran_i = np.corrcoef(missing_rate, lag_missing_rate)[0, 1]

        return {"morans_i": moran_i, "is_clustered": moran_i > 0.1}

    def _analyze_group_structure(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析分组结构（如果有元数据）"""
        # 这里是占位符，实际应用中需要传入分组信息
        return {"has_group_info": False, "group_analysis": None}

    def _assess_data_quality(self, data: pd.DataFrame, missing_info: Dict[str, Any]) -> Dict[str, Any]:
        """评估数据质量"""
        overall_score = 1.0

        # 根据缺失率调整得分
        missing_rate = missing_info["overall_rate"]
        if missing_rate > 0.5:
            overall_score -= 0.5
        elif missing_rate > 0.2:
            overall_score -= 0.3
        elif missing_rate > 0.05:
            overall_score -= 0.1

        # 根据缺失模式调整得分
        severity = missing_info["severity_level"]
        if severity == "severe":
            overall_score -= 0.3
        elif severity == "high":
            overall_score -= 0.2
        elif severity == "moderate":
            overall_score -= 0.1

        overall_score = max(0, overall_score)

        return {
            "overall_score": overall_score,
            "missing_penalty": 1.0 - overall_score,
            "quality_level": self._classify_quality_level(overall_score),
        }

    def _classify_quality_level(self, score: float) -> str:
        """分类质量等级"""
        if score >= 0.9:
            return "excellent"
        elif score >= 0.8:
            return "good"
        elif score >= 0.7:
            return "fair"
        elif score >= 0.6:
            return "poor"
        else:
            return "very_poor"

    def _generate_recommendations(
        self, missing_info: Dict[str, Any], pattern_analysis: Dict[str, Any], mechanism_analysis: Dict[str, Any]
    ) -> List[str]:
        """生成处理建议"""
        recommendations = []

        missing_rate = missing_info["overall_rate"]
        missing_type = mechanism_analysis["missing_type"]
        dominant_pattern = pattern_analysis["dominant_pattern"]

        # 基于缺失率的建议
        if missing_rate < 0.05:
            recommendations.append("缺失率较低，可使用简单插补方法如删除或均值填充")
        elif missing_rate < 0.20:
            recommendations.append("缺失率中等，建议使用截面分组中位数或时序插补")
        else:
            recommendations.append("缺失率较高，建议使用机器学习插补或考虑数据重构")

        # 基于缺失类型的建议
        if missing_type == MissingType.MCAR.value:
            recommendations.append("MCAR缺失，可安全使用统计插补方法")
        elif missing_type == MissingType.MAR.value:
            recommendations.append("MAR缺失，建议使用基于模型的插补方法")
        else:
            recommendations.append("MNAR缺失，建议使用缺失指示变量或专业处理方法")

        # 基于缺失模式的建议
        if dominant_pattern == MissingPattern.CROSS_SECTIONAL.value:
            recommendations.append("截面缺失模式，推荐使用行业分组截面中位数插补")
        elif dominant_pattern == MissingPattern.TIME_SERIES.value:
            recommendations.append("时序缺失模式，推荐使用前向填充或滚动窗口插补")
        elif dominant_pattern == MissingPattern.BLOCK.value:
            recommendations.append("块状缺失模式，需要特殊处理或考虑数据源问题")

        return recommendations
