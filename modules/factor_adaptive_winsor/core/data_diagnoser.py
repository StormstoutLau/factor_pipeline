# -*- coding: utf-8 -*-
"""
数据质量诊断器
提供全面的数据质量评估和特征分析
"""

import pandas as pd
import numpy as np
from scipy import stats
from scipy.signal import find_peaks
from sklearn.cluster import KMeans
from typing import Dict, Any, Union, List, Tuple
import warnings

from .base import BaseDiagnoser, DataDiagnosis

warnings.filterwarnings("ignore")


class DataQualityDiagnoser(BaseDiagnoser):
    """数据质量诊断器 - 全面评估数据特征和质量"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(**(config or {}))
        self.config = config or {}
        
    def diagnose(self, data: Union[pd.Series, pd.DataFrame]) -> DataDiagnosis:
        """全面数据质量诊断"""
        diagnosis = DataDiagnosis()
        
        # 转换为DataFrame格式
        if isinstance(data, pd.Series):
            data = data.to_frame()
        
        # 1. 基础质量检查
        diagnosis.basic_quality = self._check_basic_quality(data)
        
        # 2. 分布特征分析
        diagnosis.distribution_features = self._analyze_distribution(data)
        
        # 3. 极端值分析
        diagnosis.outlier_analysis = self._analyze_outliers(data)
        
        # 4. 尾部特征分析
        diagnosis.tail_analysis = self._analyze_tails(data)
        
        # 5. 正态性检验
        diagnosis.normality_tests = self._test_normality(data)
        
        # 6. 多峰性检测
        diagnosis.multimodality = self._detect_multimodality(data)
        
        # 7. 时间序列特征
        diagnosis.time_series_features = self._analyze_time_series(data)
        
        # 8. 数据完整性
        diagnosis.completeness = self._check_completeness(data)
        
        # 9. 综合质量评分
        diagnosis.overall_quality_score = self._calculate_quality_score(diagnosis)
        
        # 10. 生成建议
        diagnosis.recommendations = self._generate_recommendations(diagnosis)
        
        # 保存诊断历史
        self.diagnosis_history.append(diagnosis)
        
        return diagnosis
    
    def _check_basic_quality(self, data: pd.DataFrame) -> Dict[str, Any]:
        """基础质量检查"""
        quality = {}
        
        for column in data.columns:
            col_data = data[column]
            
            # 基础统计
            total_samples = len(col_data)
            missing_count = col_data.isnull().sum()
            missing_ratio = missing_count / total_samples
            
            # 重复值检测
            duplicate_count = col_data.duplicated().sum()
            duplicate_ratio = duplicate_count / total_samples
            
            # 数据类型
            data_type = str(col_data.dtype)
            
            # 内存使用
            memory_usage = col_data.memory_usage(deep=True)
            
            quality[column] = {
                'total_samples': total_samples,
                'missing_count': missing_count,
                'missing_ratio': missing_ratio,
                'duplicate_count': duplicate_count,
                'duplicate_ratio': duplicate_ratio,
                'data_type': data_type,
                'memory_usage_bytes': memory_usage,
                'memory_usage_mb': memory_usage / (1024 * 1024)
            }
        
        return {
            'per_column': quality,
            'overall': {
                'total_columns': len(data.columns),
                'total_cells': data.size,
                'total_missing': data.isnull().sum().sum(),
                'overall_missing_ratio': data.isnull().sum().sum() / data.size,
                'total_memory_mb': data.memory_usage(deep=True).sum() / (1024 * 1024)
            }
        }
    
    def _analyze_distribution(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分布特征分析"""
        features = {}
        
        for column in data.columns:
            col_data = data[column].dropna()
            if len(col_data) < 2:
                continue
                
            # 基础统计量
            mean_val = col_data.mean()
            median_val = col_data.median()
            std_val = col_data.std()
            var_val = col_data.var()
            
            # 分位数
            q25 = col_data.quantile(0.25)
            q75 = col_data.quantile(0.75)
            iqr = q75 - q25
            
            # 偏度和峰度
            skewness = stats.skew(col_data)
            kurtosis = stats.kurtosis(col_data)
            
            # 变异系数
            if abs(mean_val) > 1e-10:
                cv = std_val / mean_val
            else:
                cv = np.inf
            
            # 范围
            range_val = col_data.max() - col_data.min()
            
            features[column] = {
                'mean': mean_val,
                'median': median_val,
                'std': std_val,
                'variance': var_val,
                'skewness': skewness,
                'kurtosis': kurtosis,
                'cv': cv,
                'range': range_val,
                'min': col_data.min(),
                'max': col_data.max(),
                'q25': q25,
                'q75': q75,
                'iqr': iqr,
                'is_skewed': abs(skewness) > 0.5,
                'is_heavy_tailed': kurtosis > 3.0,
                'is_wide_spread': cv > 1.0
            }
        
        # 整体分布特征
        all_skewness = [f['skewness'] for f in features.values()]
        all_kurtosis = [f['kurtosis'] for f in features.values()]
        
        return {
            'per_column': features,
            'summary': {
                'mean_skewness': np.mean(all_skewness) if all_skewness else 0,
                'mean_kurtosis': np.mean(all_kurtosis) if all_kurtosis else 0,
                'skewed_columns': sum(1 for f in features.values() if f['is_skewed']),
                'heavy_tailed_columns': sum(1 for f in features.values() if f['is_heavy_tailed']),
                'wide_spread_columns': sum(1 for f in features.values() if f['is_wide_spread'])
            }
        }
    
    def _analyze_outliers(self, data: pd.DataFrame) -> Dict[str, Any]:
        """极端值分析"""
        analysis = {}
        
        for column in data.columns:
            col_data = data[column].dropna()
            if len(col_data) < 4:
                continue
            
            # Z-score方法
            z_scores = np.abs(stats.zscore(col_data))
            z_outliers = z_scores > 3
            
            # IQR方法
            q25 = col_data.quantile(0.25)
            q75 = col_data.quantile(0.75)
            iqr = q75 - q25
            lower_bound = q25 - 1.5 * iqr
            upper_bound = q75 + 1.5 * iqr
            iqr_outliers = (col_data < lower_bound) | (col_data > upper_bound)
            
            # MAD方法
            median_val = np.median(col_data)
            mad = np.median(np.abs(col_data - median_val))
            mad_threshold = 3 * mad if mad > 1e-10 else 1e-10
            mad_outliers = np.abs(col_data - median_val) > mad_threshold
            
            # 一致性投票
            consensus_outliers = z_outliers | iqr_outliers | mad_outliers
            
            analysis[column] = {
                'z_score_outlier_ratio': z_outliers.mean(),
                'iqr_outlier_ratio': iqr_outliers.mean(),
                'mad_outlier_ratio': mad_outliers.mean(),
                'consensus_outlier_ratio': consensus_outliers.mean(),
                'outlier_positions': col_data.index[consensus_outliers].tolist(),
                'z_score_threshold': 3,
                'iqr_bounds': (lower_bound, upper_bound),
                'mad_threshold': mad_threshold,
                'has_many_outliers': consensus_outliers.mean() > 0.1,
                'needs_outlier_treatment': consensus_outliers.mean() > 0.05
            }
        
        # 整体极端值分析
        all_ratios = [a['consensus_outlier_ratio'] for a in analysis.values()]
        
        return {
            'per_column': analysis,
            'summary': {
                'mean_outlier_ratio': np.mean(all_ratios) if all_ratios else 0,
                'max_outlier_ratio': np.max(all_ratios) if all_ratios else 0,
                'columns_with_many_outliers': sum(1 for a in analysis.values() if a['has_many_outliers']),
                'columns_need_treatment': sum(1 for a in analysis.values() if a['needs_outlier_treatment'])
            }
        }
    
    def _analyze_tails(self, data: pd.DataFrame) -> Dict[str, Any]:
        """尾部特征分析"""
        analysis = {}
        
        for column in data.columns:
            col_data = data[column].dropna()
            if len(col_data) < 20:
                continue
            
            # 尾部阈值
            tail_fraction = 0.1
            upper_threshold = np.percentile(col_data, 100 * (1 - tail_fraction))
            lower_threshold = np.percentile(col_data, 100 * tail_fraction)
            
            # 提取尾部数据
            upper_tail = col_data[col_data > upper_threshold]
            lower_tail = col_data[col_data < lower_threshold]
            
            # Hill估计器（尾部厚度）
            sorted_data = np.sort(col_data)[::-1]
            k = max(10, len(sorted_data) // 10)
            
            if k >= 2:
                # 防止除零：确保分母不为零
                denom = sorted_data[1:k]
                denom_safe = np.where(denom == 0, 1e-10, denom)
                log_ratio = np.log(sorted_data[:k-1] / denom_safe)
                hill_estimator = np.mean(log_ratio)
                tail_heaviness = max(0.1, min(2.0, hill_estimator))
            else:
                tail_heaviness = 0.5
            
            analysis[column] = {
                'tail_fraction': tail_fraction,
                'upper_threshold': upper_threshold,
                'lower_threshold': lower_threshold,
                'upper_tail_size': len(upper_tail),
                'lower_tail_size': len(lower_tail),
                'tail_heaviness': tail_heaviness,
                'is_heavy_tailed': tail_heaviness > 1.0,
                'tail_asymmetry': abs(len(upper_tail) - len(lower_tail)) / (len(upper_tail) + len(lower_tail)) if (len(upper_tail) + len(lower_tail)) > 0 else 0
            }
        
        return {
            'per_column': analysis,
            'summary': {
                'mean_tail_heaviness': np.mean([a['tail_heaviness'] for a in analysis.values()]) if analysis else 0.5,
                'heavy_tailed_columns': sum(1 for a in analysis.values() if a['is_heavy_tailed'])
            }
        }
    
    def _test_normality(self, data: pd.DataFrame) -> Dict[str, Any]:
        """正态性检验"""
        tests = {}
        
        for column in data.columns:
            col_data = data[column].dropna()
            if len(col_data) < 8:
                continue
            
            column_tests = {}
            
            # Shapiro-Wilk检验（适合小样本）
            try:
                if len(col_data) <= 5000:
                    stat_shapiro, p_shapiro = stats.shapiro(col_data)
                    column_tests['shapiro_wilk'] = {
                        'statistic': stat_shapiro,
                        'p_value': p_shapiro,
                        'is_normal': p_shapiro > 0.05,
                        'sample_appropriate': True
                    }
                else:
                    column_tests['shapiro_wilk'] = {
                        'statistic': None,
                        'p_value': None,
                        'is_normal': False,
                        'sample_appropriate': False,
                        'reason': 'Sample too large'
                    }
            except Exception as e:
                column_tests['shapiro_wilk'] = {
                    'statistic': None, 'p_value': None, 'is_normal': False,
                    'error': str(e), 'sample_appropriate': False
                }
            
            # Jarque-Bera检验（适合大样本）
            try:
                stat_jb, p_jb = stats.jarque_bera(col_data)
                column_tests['jarque_bera'] = {
                    'statistic': stat_jb,
                    'p_value': p_jb,
                    'is_normal': p_jb > 0.05,
                    'sample_appropriate': len(col_data) >= 20
                }
            except Exception as e:
                column_tests['jarque_bera'] = {
                    'statistic': None, 'p_value': None, 'is_normal': False,
                    'error': str(e), 'sample_appropriate': False
                }
            
            # D'Agostino's K²检验
            try:
                stat_dag, p_dag = stats.normaltest(col_data)
                column_tests['dagostino'] = {
                    'statistic': stat_dag,
                    'p_value': p_dag,
                    'is_normal': p_dag > 0.05,
                    'sample_appropriate': len(col_data) >= 8
                }
            except Exception as e:
                column_tests['dagostino'] = {
                    'statistic': None, 'p_value': None, 'is_normal': False,
                    'error': str(e), 'sample_appropriate': False
                }
            
            # 投票决定
            normal_votes = sum(1 for test in column_tests.values() 
                            if test.get('is_normal', False) and test.get('sample_appropriate', False))
            total_votes = sum(1 for test in column_tests.values() if test.get('sample_appropriate', False))
            
            column_tests['consensus'] = {
                'is_normal': normal_votes >= max(1, total_votes // 2 + 1),
                'normal_votes': normal_votes,
                'total_votes': total_votes,
                'confidence': normal_votes / total_votes if total_votes > 0 else 0
            }
            
            tests[column] = column_tests
        
        # 整体正态性总结
        normal_columns = sum(1 for col_tests in tests.values() 
                          if col_tests['consensus']['is_normal'])
        total_columns = len(tests)
        
        return {
            'per_column': tests,
            'summary': {
                'normal_columns': normal_columns,
                'total_columns': total_columns,
                'normality_ratio': normal_columns / total_columns if total_columns > 0 else 0,
                'overall_normality': normal_columns / total_columns > 0.5 if total_columns > 0 else False
            }
        }
    
    def _detect_multimodality(self, data: pd.DataFrame) -> Dict[str, Any]:
        """多峰性检测"""
        detection = {}
        
        for column in data.columns:
            col_data = data[column].dropna()
            if len(col_data) < 20:
                continue
            
            # 基于峰检测的多峰性
            hist, bin_edges = np.histogram(col_data, bins=50)
            peaks, properties = find_peaks(hist, height=np.max(hist) * 0.1, distance=2)
            
            # 基于聚类的多峰性检测
            try:
                # 使用K-means检测多峰
                k_range = range(1, 5)
                inertias = []
                
                for k in k_range:
                    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
                    kmeans.fit(col_data.values.reshape(-1, 1))
                    inertias.append(kmeans.inertia_)
                
                # 肘部法则确定最优聚类数
                if len(inertias) > 2:
                    diffs = np.diff(inertias)
                    second_diffs = np.diff(diffs)
                    optimal_k = np.argmax(second_diffs) + 2 if len(second_diffs) > 0 else 1
                else:
                    optimal_k = 1
                
            except:
                optimal_k = 1
            
            detection[column] = {
                'histogram_peaks': len(peaks),
                'optimal_clusters': optimal_k,
                'is_multimodal': optimal_k > 1 or len(peaks) > 1,
                'n_modes': max(optimal_k, len(peaks)),
                'peak_positions': bin_edges[peaks].tolist() if len(peaks) > 0 else [],
                'needs_clustering': optimal_k > 1
            }
        
        return {
            'per_column': detection,
            'summary': {
                'multimodal_columns': sum(1 for d in detection.values() if d['is_multimodal']),
                'total_columns': len(detection),
                'multimodality_ratio': sum(1 for d in detection.values() if d['is_multimodal']) / len(detection) if detection else 0
            }
        }
    
    def _analyze_time_series(self, data: pd.DataFrame) -> Dict[str, Any]:
        """时间序列特征分析"""
        if not isinstance(data.index, pd.DatetimeIndex):
            return {'error': 'Index is not datetime type'}
        
        features = {}
        
        for column in data.columns:
            col_data = data[column].dropna()
            if len(col_data) < 10:
                continue
            
            # 自相关性
            try:
                autocorr_lag1 = col_data.autocorr(lag=1)
            except:
                autocorr_lag1 = 0
            
            # 趋势性
            try:
                x = np.arange(len(col_data))
                trend_slope, _, _, _, _ = np.linalg.lstsq(x.reshape(-1, 1), col_data.values, rcond=None)
                trend_strength = abs(trend_slope[0])
            except:
                trend_strength = 0
            
            # 季节性（简单检测）
            try:
                if len(col_data) >= 24:  # 至少2个周期
                    seasonal_strength = abs(col_data.diff().autocorr(lag=12))
                else:
                    seasonal_strength = 0
            except:
                seasonal_strength = 0
            
            features[column] = {
                'autocorr_lag1': autocorr_lag1,
                'trend_strength': trend_strength,
                'seasonal_strength': seasonal_strength,
                'has_autocorrelation': abs(autocorr_lag1) > 0.3,
                'has_trend': trend_strength > 0.01,
                'has_seasonality': abs(seasonal_strength) > 0.3
            }
        
        return {
            'per_column': features,
            'summary': {
                'autocorrelated_columns': sum(1 for f in features.values() if f['has_autocorrelation']),
                'trending_columns': sum(1 for f in features.values() if f['has_trend']),
                'seasonal_columns': sum(1 for f in features.values() if f['has_seasonality'])
            }
        }
    
    def _check_completeness(self, data: pd.DataFrame) -> Dict[str, Any]:
        """数据完整性检查"""
        completeness = {}
        
        for column in data.columns:
            col_data = data[column]
            
            # 缺失值分析
            missing_count = col_data.isnull().sum()
            missing_ratio = missing_count / len(col_data)
            
            # 连续缺失值检测
            missing_groups = col_data.isnull().astype(int).groupby(
                (col_data.isnull() != col_data.isnull().shift()).cumsum()
            ).size()
            
            max_consecutive_missing = missing_groups.max() if len(missing_groups) > 0 else 0
            
            completeness[column] = {
                'missing_count': missing_count,
                'missing_ratio': missing_ratio,
                'completeness_ratio': 1 - missing_ratio,
                'max_consecutive_missing': max_consecutive_missing,
                'has_gaps': missing_ratio > 0,
                'has_large_gaps': max_consecutive_missing > 5
            }
        
        return {
            'per_column': completeness,
            'summary': {
                'overall_completeness': 1 - data.isnull().sum().sum() / data.size,
                'columns_with_gaps': sum(1 for c in completeness.values() if c['has_gaps']),
                'columns_with_large_gaps': sum(1 for c in completeness.values() if c['has_large_gaps'])
            }
        }
    
    def _calculate_quality_score(self, diagnosis: DataDiagnosis) -> float:
        """计算综合质量评分"""
        score = 0.0
        weights = {
            'completeness': 0.25,
            'outlier_quality': 0.20,
            'distribution_quality': 0.20,
            'normality_quality': 0.15,
            'multimodality_quality': 0.10,
            'time_series_quality': 0.10
        }
        
        # 完整性评分
        if diagnosis.completeness:
            completeness_score = diagnosis.completeness['summary']['overall_completeness']
            score += weights['completeness'] * completeness_score
        
        # 极端值质量评分
        if diagnosis.outlier_analysis:
            outlier_ratio = diagnosis.outlier_analysis['summary']['mean_outlier_ratio']
            outlier_score = max(0, 1 - outlier_ratio * 5)  # 极端值越少越好
            score += weights['outlier_quality'] * outlier_score
        
        # 分布质量评分
        if diagnosis.distribution_features:
            dist_summary = diagnosis.distribution_features['summary']
            skewed_ratio = dist_summary['skewed_columns'] / max(1, len(diagnosis.distribution_features['per_column']))
            heavy_tail_ratio = dist_summary['heavy_tailed_columns'] / max(1, len(diagnosis.distribution_features['per_column']))
            dist_score = max(0, 1 - (skewed_ratio + heavy_tail_ratio) / 2)
            score += weights['distribution_quality'] * dist_score
        
        # 正态性质量评分
        if diagnosis.normality_tests:
            normality_score = diagnosis.normality_tests['summary']['normality_ratio']
            score += weights['normality_quality'] * normality_score
        
        # 多峰性质量评分
        if diagnosis.multimodality:
            multimodality_ratio = diagnosis.multimodality['summary']['multimodality_ratio']
            multimodality_score = max(0, 1 - multimodality_ratio)  # 单峰更好
            score += weights['multimodality_quality'] * multimodality_score
        
        # 时间序列质量评分（如果有时间索引）
        if diagnosis.time_series_features and 'error' not in diagnosis.time_series_features:
            ts_summary = diagnosis.time_series_features['summary']
            problematic_ratio = (ts_summary['autocorrelated_columns'] + 
                              ts_summary['trending_columns'] + 
                              ts_summary['seasonal_columns']) / max(1, len(diagnosis.time_series_features['per_column']))
            ts_score = max(0, 1 - problematic_ratio / 3)
            score += weights['time_series_quality'] * ts_score
        
        return min(1.0, max(0.0, score))
    
    def _generate_recommendations(self, diagnosis: DataDiagnosis) -> List[str]:
        """生成处理建议"""
        recommendations = []
        
        # 基于完整性的建议
        if diagnosis.completeness:
            overall_completeness = diagnosis.completeness['summary']['overall_completeness']
            if overall_completeness < 0.95:
                recommendations.append("数据存在缺失值，建议进行缺失值填充或插值")
            
            if diagnosis.completeness['summary']['columns_with_large_gaps'] > 0:
                recommendations.append("检测到连续缺失值，建议使用时间序列插值方法")
        
        # 基于极端值的建议
        if diagnosis.outlier_analysis:
            outlier_ratio = diagnosis.outlier_analysis['summary']['mean_outlier_ratio']
            if outlier_ratio > 0.1:
                recommendations.append("数据包含较多极端值，建议使用智能去极值处理")
            elif outlier_ratio > 0.05:
                recommendations.append("数据存在一定极端值，建议使用温和的去极值方法")
        
        # 基于分布特征的建议
        if diagnosis.distribution_features:
            dist_summary = diagnosis.distribution_features['summary']
            if dist_summary['skewed_columns'] > 0:
                recommendations.append("检测到偏态分布，建议使用Yeo-Johnson或Box-Cox变换")
            
            if dist_summary['heavy_tailed_columns'] > 0:
                recommendations.append("检测到重尾分布，建议使用鲁棒标准化方法")
        
        # 基于正态性的建议
        if diagnosis.normality_tests:
            normality_ratio = diagnosis.normality_tests['summary']['normality_ratio']
            if normality_ratio < 0.5:
                recommendations.append("数据整体不符合正态分布，建议进行正态性变换")
        
        # 基于多峰性的建议
        if diagnosis.multimodality:
            multimodality_ratio = diagnosis.multimodality['summary']['multimodality_ratio']
            if multimodality_ratio > 0.3:
                recommendations.append("检测到多峰分布，建议考虑分群处理或聚类预处理")
        
        # 基于时间序列特征的建议
        if diagnosis.time_series_features and 'error' not in diagnosis.time_series_features:
            ts_summary = diagnosis.time_series_features['summary']
            if ts_summary['trending_columns'] > 0:
                recommendations.append("检测到趋势性，建议进行去趋势处理")
            
            if ts_summary['seasonal_columns'] > 0:
                recommendations.append("检测到季节性，建议进行季节性调整")
        
        return recommendations
