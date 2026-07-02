# -*- coding: utf-8 -*-
"""
变换器模块
提供智能去极值、自适应变换和标准化功能
"""

import pandas as pd
import numpy as np
from scipy import stats
from scipy.optimize import minimize_scalar, OptimizeResult
from sklearn.preprocessing import PowerTransformer, QuantileTransformer
from typing import Dict, Any, Union, Optional, Tuple, Literal, cast
import warnings
import logging

from .base import BaseTransformer

logger = logging.getLogger(__name__)
from .enhanced_transformers import (
    GPDTailAnalyzer,
    EnhancedRankPreservingScaler,
    SmartAdaptiveWinsorizer
)

warnings.filterwarnings("ignore")


class SmartOutlierDetector(BaseTransformer):
    """智能去极值检测器 - 根据数据特征自适应选择方法"""
    
    def __init__(self, method='auto', auto_select=True, max_outlier_frac=0.05, 
                 adaptive_threshold=True):
        super().__init__(
            method=method, auto_select=auto_select, 
            max_outlier_frac=max_outlier_frac, adaptive_threshold=adaptive_threshold
        )
        self.method = method
        self.auto_select = auto_select
        self.max_outlier_frac = max_outlier_frac
        self.adaptive_threshold = adaptive_threshold
        
    def fit(self, X: Union[pd.Series, pd.DataFrame, np.ndarray]) -> 'SmartOutlierDetector':
        """拟合去极值参数"""
        X_array = self._to_array(X)
        X_clean = X_array[~np.isnan(X_array)]
        
        if len(X_clean) < 3:
            logger.warning("样本数不足，跳过去极值处理")
            self.fitted_params = {
                'method': 'identity',
                'data_features': {'std': 0, 'mean': 0},
                'lower_bound': -np.inf,
                'upper_bound': np.inf
            }
            self.is_fitted = True
            return self
        
        # 数据特征分析
        data_features = self._analyze_data_features(X_clean)
        
        # 选择去极值方法
        if self.auto_select:
            selected_method = self._select_optimal_method(data_features)
        else:
            selected_method = self.method
        
        # 计算去极值参数
        if selected_method == 'quantile':
            params = self._fit_quantile_method(X_clean)
        elif selected_method == 'z_score':
            params = self._fit_z_score_method(X_clean)
        elif selected_method == 'mad':
            params = self._fit_mad_method(X_clean)
        elif selected_method == 'iqr':
            params = self._fit_iqr_method(X_clean)
        elif selected_method == 'adaptive':
            params = self._fit_adaptive_method(X_clean, data_features)
        elif selected_method == 'sigmoid_soft':
            params = self._fit_sigmoid_soft_method(X_clean, data_features)
        else:
            raise ValueError(f"未知的去极值方法: {selected_method}")
        
        self.fitted_params = {
            'method': selected_method,
            'data_features': data_features,
            **params
        }
        
        self.is_fitted = True
        return self
    
    def transform(self, X: Union[pd.Series, pd.DataFrame, np.ndarray]) -> Union[pd.Series, pd.DataFrame, np.ndarray]:
        """应用去极值变换"""
        if not self.is_fitted:
            raise ValueError("请先调用fit方法")
        
        X_array = self._to_array(X)
        original_format = X if isinstance(X, (pd.Series, pd.DataFrame)) else None
        
        method = self.fitted_params['method']
        
        # 处理可能的异常方法名或未知方法
        valid_methods = ['identity', 'quantile', 'z_score', 'mad', 'iqr', 'adaptive', 'sigmoid_soft']
        if method not in valid_methods:
            method = 'identity'
        
        if method == 'identity':
            transformed = X_array
        elif method == 'quantile':
            transformed = self._apply_quantile_method(X_array)
        elif method == 'z_score':
            transformed = self._apply_z_score_method(X_array)
        elif method == 'mad':
            transformed = self._apply_mad_method(X_array)
        elif method == 'iqr':
            transformed = self._apply_iqr_method(X_array)
        elif method == 'adaptive':
            transformed = self._apply_adaptive_method(X_array)
        elif method == 'sigmoid_soft':
            transformed = self._apply_sigmoid_soft_method(X_array)
        else:
            # 最后的回退
            transformed = X_array
        
        if original_format is not None:
            return self._restore_format(transformed, original_format)
        return transformed
    
    def _analyze_data_features(self, X: np.ndarray) -> Dict[str, Any]:
        """分析数据特征"""
        features = {}
        
        # 基础统计
        features['n_samples'] = len(X)
        features['mean'] = np.mean(X)
        features['median'] = np.median(X)
        features['std'] = np.std(X)
        features['mad'] = np.median(np.abs(X - np.median(X)))
        features['skewness'] = stats.skew(X)
        features['kurtosis'] = stats.kurtosis(X)
        
        # 极端值比例
        std_safe = features['std'] if features['std'] > 1e-10 else 1e-10
        z_scores = np.abs((X - features['mean']) / std_safe)
        features['z_outlier_ratio'] = np.mean(z_scores > 3)
        
        # 分位数
        q25, q75 = np.percentile(X, [25, 75])
        iqr = q75 - q25
        lower_bound = q25 - 1.5 * iqr
        upper_bound = q75 + 1.5 * iqr
        iqr_outliers = (X < lower_bound) | (X > upper_bound)
        features['iqr_outlier_ratio'] = np.mean(iqr_outliers)
        
        # MAD极端值
        mad_outliers = np.abs(X - features['median']) > 3 * features['mad']
        features['mad_outlier_ratio'] = np.mean(mad_outliers)
        
        # 综合极端值比例
        features['consensus_outlier_ratio'] = np.mean([
            features['z_outlier_ratio'],
            features['iqr_outlier_ratio'],
            features['mad_outlier_ratio']
        ])
        
        # 分布特征
        features['is_heavy_tailed'] = features['kurtosis'] > 3
        features['is_skewed'] = abs(features['skewness']) > 0.5
        features['is_wide_spread'] = features['std'] / abs(features['mean']) > 1 if features['mean'] != 0 else False
        
        return features
    
    def _select_optimal_method(self, data_features: Dict) -> str:
        """选择最优去极值方法"""
        n_samples = data_features['n_samples']
        outlier_ratio = data_features['consensus_outlier_ratio']
        skewness = data_features['skewness']
        
        # 小样本使用sigmoid软压缩
        if n_samples < 30:
            return 'sigmoid_soft'
        
        # 根据极端值比例选择
        if outlier_ratio > 0.15:
            return 'quantile'
        elif outlier_ratio > 0.1:
            return 'adaptive'
        elif outlier_ratio > 0.05:
            return 'iqr'
        else:
            return 'mad'  # MAD方法对重尾分布更鲁棒
    
    def _fit_quantile_method(self, X: np.ndarray) -> Dict[str, Any]:
        """拟合分位数方法"""
        lower_quantile = self.max_outlier_frac / 2
        upper_quantile = 1 - self.max_outlier_frac / 2
        
        lower_bound = np.percentile(X, 100 * lower_quantile)
        upper_bound = np.percentile(X, 100 * upper_quantile)
        
        return {
            'lower_bound': lower_bound,
            'upper_bound': upper_bound,
            'lower_quantile': lower_quantile,
            'upper_quantile': upper_quantile
        }
    
    def _fit_z_score_method(self, X: np.ndarray) -> Dict[str, Any]:
        """拟合Z-score方法"""
        mean_val = np.mean(X)
        std_val = np.std(X)
        
        # 自适应阈值
        if self.adaptive_threshold:
            z_scores = np.abs((X - mean_val) / std_val)
            threshold = np.percentile(z_scores, 100 * (1 - self.max_outlier_frac))
            threshold = max(2.0, min(4.0, threshold))  # 限制在合理范围
        else:
            threshold = 3.0
        
        return {
            'mean': mean_val,
            'std': std_val,
            'threshold': threshold
        }
    
    def _fit_mad_method(self, X: np.ndarray) -> Dict[str, Any]:
        """拟合MAD方法"""
        median_val = np.median(X)
        mad_val = np.median(np.abs(X - median_val))
        
        # 自适应阈值
        if self.adaptive_threshold:
            mad_scores = np.abs(X - median_val) / mad_val
            threshold = np.percentile(mad_scores, 100 * (1 - self.max_outlier_frac))
            threshold = max(2.0, min(4.0, threshold))
        else:
            threshold = 3.0
        
        return {
            'median': median_val,
            'mad': mad_val,
            'threshold': threshold
        }
    
    def _fit_iqr_method(self, X: np.ndarray) -> Dict[str, Any]:
        """拟合IQR方法"""
        q25, q75 = np.percentile(X, [25, 75])
        iqr = q75 - q25
        
        # 自适应系数
        if self.adaptive_threshold:
            # 基于极端值比例调整系数
            outlier_ratio = self.max_outlier_frac
            if outlier_ratio > 0.1:
                coefficient = 2.0  # 更宽松的边界
            elif outlier_ratio > 0.05:
                coefficient = 1.5  # 标准边界
            else:
                coefficient = 1.0  # 更严格的边界
        else:
            coefficient = 1.5
        
        lower_bound = q25 - coefficient * iqr
        upper_bound = q75 + coefficient * iqr
        
        return {
            'q25': q25,
            'q75': q75,
            'iqr': iqr,
            'coefficient': coefficient,
            'lower_bound': lower_bound,
            'upper_bound': upper_bound
        }
    
    def _fit_adaptive_method(self, X: np.ndarray, features: Dict[str, Any]) -> Dict[str, Any]:
        """拟合自适应方法"""
        # 结合多种方法的优势
        quantile_params = self._fit_quantile_method(X)
        mad_params = self._fit_mad_method(X)
        
        # 根据数据特征加权
        if features['is_heavy_tailed']:
            # 重尾分布，更依赖MAD
            weight_mad = 0.7
            weight_quantile = 0.3
        elif features['is_skewed']:
            # 偏态分布，更依赖分位数
            weight_mad = 0.3
            weight_quantile = 0.7
        else:
            # 平衡情况
            weight_mad = 0.5
            weight_quantile = 0.5
        
        # 加权边界
        lower_bound = (weight_mad * (features['median'] - mad_params['threshold'] * mad_params['mad']) + 
                     weight_quantile * quantile_params['lower_bound'])
        upper_bound = (weight_mad * (features['median'] + mad_params['threshold'] * mad_params['mad']) + 
                     weight_quantile * quantile_params['upper_bound'])
        
        return {
            'lower_bound': lower_bound,
            'upper_bound': upper_bound,
            'weight_mad': weight_mad,
            'weight_quantile': weight_quantile,
            'median': features['median'],
            'mad': mad_params['mad']
        }
    
    def _fit_sigmoid_soft_method(self, X: np.ndarray, features: Dict[str, Any]) -> Dict[str, Any]:
        """拟合sigmoid软压缩方法 - 适用于小样本"""
        median_val = np.median(X)
        mad_val = np.median(np.abs(X - median_val))
        
        # 小样本自适应参数
        n_samples = len(X)
        if n_samples < 15:
            # 极小样本，更温和的压缩
            k = 0.5
            threshold = 2.0
        else:
            # 小样本，标准压缩
            k = 1.0
            threshold = 2.5
        
        return {
            'median': median_val,
            'mad': mad_val,
            'k': k,
            'threshold': threshold
        }
    
    def _smooth_clip(self, X: np.ndarray, lower_bound: float, upper_bound: float, 
                    transition_width: float = 0.05) -> np.ndarray:
        """平滑截断函数，保证C¹连续性"""
        range_width = upper_bound - lower_bound
        if range_width <= 0:
            return X
        
        # 计算过渡区域宽度
        transition = transition_width * range_width
        
        # 上边界平滑过渡
        upper_transition_start = upper_bound - transition
        upper_mask = X > upper_transition_start
        upper_factor = np.where(
            X > upper_bound,
            0.0,  # 完全超出边界
            0.5 * (1 + np.tanh((upper_bound - X) / transition * 2))  # 过渡区
        )
        
        # 下边界平滑过渡
        lower_transition_end = lower_bound + transition
        lower_mask = X < lower_transition_end
        lower_factor = np.where(
            X < lower_bound,
            0.0,  # 完全超出边界
            0.5 * (1 + np.tanh((X - lower_bound) / transition * 2))  # 过渡区
        )
        
        # 组合结果
        result = X.copy()
        
        # 处理上边界
        result[upper_mask] = (
            upper_bound * upper_factor[upper_mask] + 
            X[upper_mask] * (1 - upper_factor[upper_mask])
        )
        
        # 处理下边界
        result[lower_mask] = (
            lower_bound * lower_factor[lower_mask] + 
            X[lower_mask] * (1 - lower_factor[lower_mask])
        )
        
        # 软截断极端值（超出过渡区的部分）- 避免硬截断导致的Q-Q图尾部横线
        # 对于完全超出边界的值，使用更平滑的渐近处理而不是硬截断
        extreme_lower = result < lower_bound
        extreme_upper = result > upper_bound
        
        # 安全计算标准差，避免为0
        result_std = np.std(result)
        if result_std < 1e-10:
            result_std = 1e-10  # 使用最小值避免除零
        
        if extreme_lower.any():
            # 对下极端值使用指数衰减
            excess = lower_bound - result[extreme_lower]
            decay_factor = np.exp(-excess / (result_std * 0.1))
            result[extreme_lower] = lower_bound - (result_std * 0.05) * decay_factor
            
        if extreme_upper.any():
            # 对上极端值使用指数衰减
            excess = result[extreme_upper] - upper_bound
            decay_factor = np.exp(-excess / (result_std * 0.1))
            result[extreme_upper] = upper_bound + (result_std * 0.05) * decay_factor
        
        return result
    
    def _apply_quantile_method(self, X: np.ndarray) -> np.ndarray:
        """应用分位数方法"""
        lower_bound = self.fitted_params['lower_bound']
        upper_bound = self.fitted_params['upper_bound']
        
        return self._smooth_clip(X, lower_bound, upper_bound)
    
    def _apply_z_score_method(self, X: np.ndarray) -> np.ndarray:
        """应用Z-score方法"""
        mean_val = self.fitted_params['mean']
        std_val = self.fitted_params['std']
        threshold = self.fitted_params['threshold']
        
        lower_bound = mean_val - threshold * std_val
        upper_bound = mean_val + threshold * std_val
        
        return self._smooth_clip(X, lower_bound, upper_bound)
    
    def _apply_mad_method(self, X: np.ndarray) -> np.ndarray:
        """应用MAD方法"""
        median_val = self.fitted_params['median']
        mad_val = self.fitted_params['mad']
        threshold = self.fitted_params['threshold']
        
        lower_bound = median_val - threshold * mad_val
        upper_bound = median_val + threshold * mad_val
        
        return self._smooth_clip(X, lower_bound, upper_bound)
    
    def _apply_iqr_method(self, X: np.ndarray) -> np.ndarray:
        """应用IQR方法"""
        lower_bound = self.fitted_params['lower_bound']
        upper_bound = self.fitted_params['upper_bound']
        
        return self._smooth_clip(X, lower_bound, upper_bound)
    
    def _apply_adaptive_method(self, X: np.ndarray) -> np.ndarray:
        """应用自适应方法"""
        lower_bound = self.fitted_params['lower_bound']
        upper_bound = self.fitted_params['upper_bound']
        
        return self._smooth_clip(X, lower_bound, upper_bound)
    
    def _apply_sigmoid_soft_method(self, X: np.ndarray) -> np.ndarray:
        """应用sigmoid软压缩方法"""
        median_val = self.fitted_params['median']
        mad_val = self.fitted_params['mad']
        k = self.fitted_params['k']
        threshold = self.fitted_params['threshold']
        
        # 标准化
        z = (X - median_val) / (mad_val + 1e-8)
        
        # sigmoid软压缩函数 - 数值稳定版本
        def sigmoid_soft(z_val, k, threshold):
            """sigmoid软压缩函数 - 保证导数连续，数值稳定"""
            if abs(z_val) <= threshold:
                return z_val  # 在阈值内保持原值
            else:
                # 使用修正的sigmoid函数，确保导数连续
                excess = abs(z_val) - threshold
                # 调整参数使导数在阈值处等于1
                adjusted_k = k * 2  # 调整系数保证导数连续
                
                # 数值稳定实现：避免大数溢出
                if adjusted_k * excess > 709:  # np.log(float_max) ≈ 709
                    # 大数情况：log((1+exp(x))/2) ≈ x - log(2)
                    compressed = threshold + (1 / adjusted_k) * (adjusted_k * excess - np.log(2))
                else:
                    compressed = threshold + (1 / adjusted_k) * np.log(
                        (1 + np.exp(adjusted_k * excess)) / 2
                    )
                return np.sign(z_val) * compressed
        
        # 向量化应用
        vfunc = np.vectorize(sigmoid_soft)
        compressed_z = vfunc(z, k, threshold)
        
        # 逆标准化
        return compressed_z * mad_val + median_val


class AdaptiveTransformer(BaseTransformer):
    """自适应变换器 - 基于诊断结果自动选择变换方法"""
    
    def __init__(self, method='auto', auto_optimize=True, target_distribution: Literal['uniform', 'normal'] = 'normal', power_param=None):
        super().__init__(
            method=method, auto_optimize=auto_optimize, 
            target_distribution=target_distribution
        )
        self.method = method
        self.auto_optimize = auto_optimize
        self.target_distribution = target_distribution
        self.power_param = power_param
        
    def fit(self, X: Union[pd.Series, pd.DataFrame, np.ndarray]) -> 'AdaptiveTransformer':
        """拟合变换参数"""
        X_array = self._to_array(X)
        X_clean = X_array[~np.isnan(X_array)]
        
        if len(X_clean) < 3:
            logger.warning("样本数不足，跳过变换")
            self.fitted_params = {
                'method': 'identity',
                'data_features': {'skewness': 0, 'kurtosis': 0},
                'success': False
            }
            self.is_fitted = True
            return self
        
        # 分析数据特征
        data_features = self._analyze_features(X_clean)
        
        # 选择变换方法
        if self.method == 'auto' or self.auto_optimize:
            selected_method = self._select_optimal_transform(data_features)
        else:
            selected_method = self.method
        
        # 拟合变换参数
        if selected_method == 'yeojohnson':
            params = self._fit_yeojohnson(X_clean)
        elif selected_method == 'boxcox':
            params = self._fit_boxcox(X_clean)
        elif selected_method == 'quantile':
            params = self._fit_quantile(X_clean)
        elif selected_method == 'power':
            params = self._fit_power(X_clean)
        elif selected_method == 'log':
            params = self._fit_log(X_clean)
        else:
            raise ValueError(f"未知的变换方法: {selected_method}")
        
        self.fitted_params = {
            'method': selected_method,
            'data_features': data_features,
            **params
        }
        
        self.is_fitted = True
        return self
    
    def transform(self, X: Union[pd.Series, pd.DataFrame, np.ndarray]) -> Union[pd.Series, pd.DataFrame, np.ndarray]:
        """应用变换"""
        if not self.is_fitted:
            raise ValueError("请先调用fit方法")
        
        X_array = self._to_array(X)
        original_format = X if isinstance(X, (pd.Series, pd.DataFrame)) else None
        
        method = self.fitted_params['method']
        
        if method == 'identity' or not self.fitted_params.get('success', True):
            transformed = X_array
        elif method == 'yeojohnson':
            transformed = self._apply_yeojohnson(X_array)
        elif method == 'boxcox':
            transformed = self._apply_boxcox(X_array)
        elif method == 'quantile':
            transformed = self._apply_quantile(X_array)
        elif method == 'power':
            transformed = self._apply_power(X_array)
        elif method == 'log':
            transformed = self._apply_log(X_array)
        else:
            raise ValueError(f"未知的变换方法: {method}")
        
        if original_format is not None:
            return self._restore_format(transformed, original_format)
        return transformed
    
    def _analyze_features(self, X: np.ndarray) -> Dict[str, Any]:
        """分析数据特征"""
        features = {}
        
        # 基础统计
        features['mean'] = np.mean(X)
        features['median'] = np.median(X)
        features['std'] = np.std(X)
        features['min'] = np.min(X)
        features['max'] = np.max(X)
        features['skewness'] = stats.skew(X)
        features['kurtosis'] = stats.kurtosis(X)
        
        # 分布特征
        features['is_normal'] = abs(features['skewness']) < 0.5 and abs(features['kurtosis'] - 3) < 1
        features['is_positive'] = np.all(X >= 0)
        features['is_heavy_tailed'] = features['kurtosis'] > 3
        features['is_skewed'] = abs(features['skewness']) > 0.5
        
        return features
    
    def _select_optimal_transform(self, features: Dict[str, Any]) -> str:
        """选择最优变换方法"""
        if not features['is_normal']:
            if not features['is_positive']:
                return 'yeojohnson'  # Yeo-Johnson可以处理负值
            elif features['is_heavy_tailed']:
                return 'boxcox'  # Box-Cox对重尾效果好
            elif features['is_skewed']:
                return 'log' if features['is_positive'] else 'yeojohnson'
            else:
                return 'quantile'  # 分位数变换通用性强
        else:
            return 'power'  # 幂变换对接近正态的数据效果好
    
    def _fit_yeojohnson(self, X: np.ndarray) -> Dict[str, Any]:
        """拟合Yeo-Johnson变换"""
        try:
            # 检查数据有效性
            X_clean = X[~np.isnan(X)]
            if len(X_clean) < 2:
                logger.warning("Yeo-Johnson变换: 有效样本不足，跳过变换")
                return {'transformer': None, 'success': False}
            
            # 检查数据是否全部相同
            if np.allclose(X_clean, X_clean[0]):
                logger.warning("Yeo-Johnson变换: 数据为常数，跳过变换")
                return {'transformer': None, 'success': False}
            
            transformer = PowerTransformer(method='yeo-johnson', standardize=False)
            transformer.fit(X_clean.reshape(-1, 1))
            
            return {
                'transformer': transformer,
                'success': True
            }
        except Exception as e:
            logger.warning(f"Yeo-Johnson变换拟合失败: {e}")
            return {
                'transformer': None,
                'success': False
            }
    
    def _fit_boxcox(self, X: np.ndarray) -> Dict[str, Any]:
        """拟合Box-Cox变换"""
        try:
            # 检查数据有效性
            X_clean = X[~np.isnan(X)]
            if len(X_clean) < 2:
                logger.warning("Box-Cox变换: 有效样本不足，跳过变换")
                return {'transformer': None, 'offset': 0, 'success': False}
            
            # 检查数据是否全部相同
            if np.allclose(X_clean, X_clean[0]):
                logger.warning("Box-Cox变换: 数据为常数，跳过变换")
                return {'transformer': None, 'offset': 0, 'success': False}
            
            # Box-Cox需要正数
            if np.any(X_clean <= 0):
                offset = -np.min(X_clean) + 1e-8
            else:
                offset = 0
            
            transformer = PowerTransformer(method='box-cox', standardize=False)
            transformer.fit((X_clean + offset).reshape(-1, 1))
            
            return {
                'transformer': transformer,
                'offset': offset,
                'success': True
            }
        except Exception as e:
            logger.warning(f"Box-Cox变换拟合失败: {e}")
            return {
                'transformer': None,
                'offset': 0,
                'success': False
            }
    
    def _fit_quantile(self, X: np.ndarray) -> Dict[str, Any]:
        """拟合分位数变换"""
        try:
            # 检查数据有效性
            X_clean = X[~np.isnan(X)]
            if len(X_clean) < 2:
                logger.warning("分位数变换: 有效样本不足，跳过变换")
                return {'transformer': None, 'success': False}
            
            # 检查数据是否全部相同
            if np.allclose(X_clean, X_clean[0]):
                logger.warning("分位数变换: 数据为常数，跳过变换")
                return {'transformer': None, 'success': False}
            
            transformer = QuantileTransformer(
                output_distribution=cast(Literal['uniform', 'normal'], self.target_distribution),
                n_quantiles=min(1000, len(X_clean)),
                random_state=42
            )
            transformer.fit(X_clean.reshape(-1, 1))
            
            return {
                'transformer': transformer,
                'success': True
            }
        except Exception as e:
            logger.warning(f"分位数变换拟合失败: {e}")
            return {
                'transformer': None,
                'success': False
            }
    
    def _fit_power(self, X: np.ndarray) -> Dict[str, Any]:
        """拟合幂变换"""
        try:
            # 检查数据有效性
            X_clean = X[~np.isnan(X)]
            if len(X_clean) < 3:
                logger.warning("幂变换: 有效样本不足，跳过变换")
                return {'power_param': 1.0, 'success': False}
            
            # 检查数据是否全部相同
            if np.allclose(X_clean, X_clean[0]):
                logger.warning("幂变换: 数据为常数，跳过变换")
                return {'power_param': 1.0, 'success': False}
            
            # 寻找最优幂参数
            def objective(power):
                transformed = np.sign(X_clean) * np.power(np.abs(X_clean), power)
                # 计算偏度
                skewness = abs(stats.skew(transformed))
                return skewness
            
            result: OptimizeResult = minimize_scalar(objective, bounds=(-2, 2), method='bounded')
            
            return {
                'power_param': result.x,
                'success': result.success
            }
        except Exception as e:
            logger.warning(f"幂变换拟合失败: {e}")
            return {
                'power_param': 1.0,
                'success': False
            }
    
    def _fit_log(self, X: np.ndarray) -> Dict[str, Any]:
        """拟合对数变换"""
        try:
            # 检查数据有效性
            X_clean = X[~np.isnan(X)]
            if len(X_clean) < 1:
                logger.warning("对数变换: 有效样本不足，跳过变换")
                return {'offset': 0, 'success': False}
            
            # 对数变换需要正数
            if np.any(X_clean <= 0):
                offset = -np.min(X_clean) + 1e-8
            else:
                offset = 0
            
            return {
                'offset': offset,
                'success': True
            }
        except Exception as e:
            logger.warning(f"对数变换拟合失败: {e}")
            return {
                'offset': 0,
                'success': False
            }
    
    def _apply_yeojohnson(self, X: np.ndarray) -> np.ndarray:
        """应用Yeo-Johnson变换"""
        if not self.fitted_params['success']:
            return X
        
        transformer = self.fitted_params['transformer']
        try:
            transformed = transformer.transform(X.reshape(-1, 1)).flatten()
            return transformed
        except:
            return X
    
    def _apply_boxcox(self, X: np.ndarray) -> np.ndarray:
        """应用Box-Cox变换"""
        if not self.fitted_params['success']:
            return X
        
        transformer = self.fitted_params['transformer']
        offset = self.fitted_params['offset']
        
        try:
            X_shifted = X + offset
            transformed = transformer.transform(X_shifted.reshape(-1, 1)).flatten()
            return transformed
        except:
            return X
    
    def _apply_quantile(self, X: np.ndarray) -> np.ndarray:
        """应用分位数变换"""
        if not self.fitted_params['success']:
            return X
        
        transformer = self.fitted_params['transformer']
        try:
            transformed = transformer.transform(X.reshape(-1, 1)).flatten()
            return transformed
        except:
            return X
    
    def _apply_power(self, X: np.ndarray) -> np.ndarray:
        """应用幂变换"""
        if not self.fitted_params['success']:
            return X
        
        power = self.fitted_params['power_param']
        try:
            transformed = np.sign(X) * np.power(np.abs(X), power)
            return transformed
        except:
            return X
    
    def _apply_log(self, X: np.ndarray) -> np.ndarray:
        """应用对数变换"""
        if not self.fitted_params['success']:
            return X
        
        offset = self.fitted_params['offset']
        try:
            transformed = np.log(X + offset)
            return transformed
        except:
            return X


class AdaptiveStandardizer(BaseTransformer):
    """自适应标准化器 - 基于统计量投票选择标准化方法"""
    
    def __init__(self, method='auto', fallback_enabled=True, robust_threshold=0.1):
        super().__init__(
            method=method, fallback_enabled=fallback_enabled, 
            robust_threshold=robust_threshold
        )
        self.method = method
        self.fallback_enabled = fallback_enabled
        self.robust_threshold = robust_threshold
        
    def fit(self, X: Union[pd.Series, pd.DataFrame, np.ndarray]) -> 'AdaptiveStandardizer':
        """拟合标准化参数"""
        X_array = self._to_array(X)
        X_clean = X_array[~np.isnan(X_array)]
        
        if len(X_clean) < 2:
            logger.warning("样本数不足，使用默认标准化参数")
            self.fitted_params = {
                'method': 'z_score',
                'data_features': {'mean': 0, 'std': 1, 'median': 0, 'mad': 1},
                'mean': 0,
                'std': 1,
                'valid': True,
                'fallback_enabled': self.fallback_enabled
            }
            self.is_fitted = True
            return self
        
        # 分析数据特征
        data_features = self._analyze_standardization_features(X_clean)
        
        # 选择标准化方法
        if self.method == 'auto':
            selected_method = self._vote_on_method(data_features)
        else:
            selected_method = self.method
        
        # 计算标准化参数
        if selected_method == 'z_score':
            params = self._fit_z_score(X_clean)
        elif selected_method == 'robust':
            params = self._fit_robust(X_clean)
        elif selected_method == 'min_max':
            params = self._fit_min_max(X_clean)
        elif selected_method == 'quantile':
            params = self._fit_quantile_uniform(X_clean)
        else:
            raise ValueError(f"未知的标准化方法: {selected_method}")
        
        self.fitted_params = {
            'method': selected_method,
            'data_features': data_features,
            **params
        }
        
        self.is_fitted = True
        return self
    
    def transform(self, X: Union[pd.Series, pd.DataFrame, np.ndarray]) -> Union[pd.Series, pd.DataFrame, np.ndarray]:
        """应用标准化变换"""
        if not self.is_fitted:
            raise ValueError("请先调用fit方法")
        
        X_array = self._to_array(X)
        original_format = X if isinstance(X, (pd.Series, pd.DataFrame)) else None
        
        method = self.fitted_params['method']
        
        # 处理可能的异常方法名
        if method not in ['z_score', 'robust', 'min_max', 'quantile']:
            method = 'z_score'
        
        if method == 'z_score':
            transformed = self._apply_z_score(X_array)
        elif method == 'robust':
            transformed = self._apply_robust(X_array)
        elif method == 'min_max':
            transformed = self._apply_min_max(X_array)
        elif method == 'quantile':
            transformed = self._apply_quantile(X_array)
        else:
            raise ValueError(f"未知的标准化方法: {method}")
        
        if original_format is not None:
            return self._restore_format(transformed, original_format)
        return transformed
    
    def _analyze_standardization_features(self, X: np.ndarray) -> Dict[str, Any]:
        """分析标准化相关特征"""
        features = {}
        
        # 基础统计
        features['mean'] = np.mean(X)
        features['median'] = np.median(X)
        features['std'] = np.std(X)
        features['mad'] = np.median(np.abs(X - np.median(X)))
        features['min'] = np.min(X)
        features['max'] = np.max(X)
        
        # 极端值比例
        z_scores = np.abs((X - features['mean']) / features['std'])
        features['outlier_ratio'] = np.mean(z_scores > 3)
        
        # 分布特征
        features['skewness'] = stats.skew(X)
        features['kurtosis'] = stats.kurtosis(X)
        features['is_heavy_tailed'] = features['kurtosis'] > 3
        features['is_skewed'] = abs(features['skewness']) > 0.5
        
        # 范围特征
        features['range'] = features['max'] - features['min']
        features['cv'] = features['std'] / abs(features['mean']) if features['mean'] != 0 else np.inf
        
        return features
    
    def _vote_on_method(self, features: Dict[str, Any]) -> str:
        """基于统计量投票选择标准化方法"""
        votes = {}
        
        # 基于极端值比例投票
        if features['outlier_ratio'] > self.robust_threshold:
            votes['robust'] = votes.get('robust', 0) + 2
        else:
            votes['z_score'] = votes.get('z_score', 0) + 1
        
        # 基于分布特征投票
        if features['is_heavy_tailed']:
            votes['robust'] = votes.get('robust', 0) + 2
            votes['quantile'] = votes.get('quantile', 0) + 1
        else:
            votes['z_score'] = votes.get('z_score', 0) + 2
        
        # 基于偏度投票
        if features['is_skewed']:
            votes['quantile'] = votes.get('quantile', 0) + 1
        else:
            votes['z_score'] = votes.get('z_score', 0) + 1
        
        # 基于变异系数投票
        if features['cv'] > 1.0:
            votes['robust'] = votes.get('robust', 0) + 1
        else:
            votes['z_score'] = votes.get('z_score', 0) + 1
        
        # 选择得票最高的方法
        if not votes:
            return 'z_score'
        
        return max(votes.keys(), key=lambda k: votes[k])
    
    def _fit_z_score(self, X: np.ndarray) -> Dict[str, Any]:
        """拟合Z-score标准化"""
        mean_val = np.mean(X)
        std_val = np.std(X)
        
        return {
            'mean': mean_val,
            'std': std_val,
            'valid': std_val > 0
        }
    
    def _fit_robust(self, X: np.ndarray) -> Dict[str, Any]:
        """拟合鲁棒标准化"""
        median_val = np.median(X)
        mad_val = np.median(np.abs(X - median_val))
        
        return {
            'median': median_val,
            'mad': mad_val,
            'valid': mad_val > 0
        }
    
    def _fit_min_max(self, X: np.ndarray) -> Dict[str, Any]:
        """拟合最小-最大标准化"""
        min_val = np.min(X)
        max_val = np.max(X)
        range_val = max_val - min_val
        
        return {
            'min': min_val,
            'max': max_val,
            'range': range_val,
            'valid': range_val > 0
        }
    
    def _fit_quantile_uniform(self, X: np.ndarray) -> Dict[str, Any]:
        """拟合分位数均匀标准化"""
        # 使用QuantileTransformer
        transformer = QuantileTransformer(
            output_distribution='uniform',
            n_quantiles=min(1000, len(X)),
            random_state=42
        )
        transformer.fit(X.reshape(-1, 1))
        
        return {
            'transformer': transformer,
            'n_quantiles': transformer.n_quantiles_,
            'valid': True
        }
    
    def _apply_z_score(self, X: np.ndarray) -> np.ndarray:
        """应用Z-score标准化"""
        if not self.fitted_params['valid']:
            if self.fallback_enabled:
                return self._fallback_standardization(X)
            else:
                raise ValueError("标准差为0且不允许回退")
        
        mean_val = self.fitted_params['mean']
        std_val = self.fitted_params['std']
        
        return (X - mean_val) / std_val
    
    def _apply_robust(self, X: np.ndarray) -> np.ndarray:
        """应用鲁棒标准化"""
        if not self.fitted_params['valid']:
            if self.fallback_enabled:
                return self._fallback_standardization(X)
            else:
                raise ValueError("MAD为0且不允许回退")
        
        median_val = self.fitted_params['median']
        mad_val = self.fitted_params['mad']
        
        return (X - median_val) / mad_val
    
    def _apply_min_max(self, X: np.ndarray) -> np.ndarray:
        """应用最小-最大标准化"""
        if not self.fitted_params['valid']:
            if self.fallback_enabled:
                return self._fallback_standardization(X)
            else:
                raise ValueError("范围为0且不允许回退")
        
        min_val = self.fitted_params['min']
        max_val = self.fitted_params['max']
        range_val = self.fitted_params['range']
        
        return (X - min_val) / range_val
    
    def _apply_quantile(self, X: np.ndarray) -> np.ndarray:
        """应用分位数标准化"""
        if not self.fitted_params['valid']:
            if self.fallback_enabled:
                return self._fallback_standardization(X)
            else:
                raise ValueError("分位数变换失败且不允许回退")
        
        transformer = self.fitted_params['transformer']
        try:
            transformed = transformer.transform(X.reshape(-1, 1)).flatten()
            return transformed
        except:
            return self._fallback_standardization(X)
    
    def _fallback_standardization(self, X: np.ndarray) -> np.ndarray:
        """回退标准化方法"""
        try:
            # 简单的Z-score标准化
            mean_val = np.mean(X)
            std_val = np.std(X)
            
            if std_val > 1e-8:
                return (X - mean_val) / std_val
            else:
                # 如果标准差为0，返回零
                return np.zeros_like(X)
        except:
            return X
