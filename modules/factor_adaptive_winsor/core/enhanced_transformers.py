# -*- coding: utf-8 -*-
"""
增强变换器模块
包含从原系统抽取的高级变换方法
"""

import pandas as pd
import numpy as np
from scipy import stats
from scipy.optimize import minimize
from typing import Dict, Any, Union, Tuple
import warnings
import logging

from .base import BaseTransformer

warnings.filterwarnings("ignore")

# 配置日志
logger = logging.getLogger(__name__)

# 检查pyextremes是否可用
try:
    import pyextremes as pe
    HAS_PYEXTREMES = True
except ImportError:
    HAS_PYEXTREMES = False
    logger.warning("pyextremes库未安装，极值分析功能将使用简化实现。"
                   "如需完整功能，请执行: pip install pyextremes")


class GPDTailAnalyzer:
    """广义帕累托分布尾部分析器"""
    
    def __init__(self, tail_fraction=0.1, min_tail_size=20):
        self.tail_fraction = tail_fraction
        self.min_tail_size = min_tail_size
        self.fitted_params = {}
    
    def analyze_tail_features(self, X: np.ndarray) -> Dict:
        """分析尾部特征"""
        X_clean = X[~np.isnan(X)]
        n = len(X_clean)
        
        if n < self.min_tail_size * 2:
            return {'sufficient_data': False}
        
        # 计算尾部阈值
        upper_threshold = np.percentile(X_clean, 100 * (1 - self.tail_fraction))
        lower_threshold = np.percentile(X_clean, 100 * self.tail_fraction)
        
        # 提取尾部数据
        upper_tail = X_clean[X_clean > upper_threshold]
        lower_tail = X_clean[X_clean < lower_threshold]
        
        features = {
            'sufficient_data': True,
            'upper_threshold': upper_threshold,
            'lower_threshold': lower_threshold,
            'upper_tail_size': len(upper_tail),
            'lower_tail_size': len(lower_tail),
            'tail_heaviness': self._estimate_tail_heaviness(X_clean),
            'gpd_fit_quality': self._assess_gpd_fit_quality(upper_tail, lower_tail)
        }
        
        return features
    
    def _estimate_tail_heaviness(self, X: np.ndarray) -> float:
        """估计尾部厚度 (Hill估计器)"""
        sorted_X = np.sort(X)[::-1]  # 降序排列
        k = max(10, len(sorted_X) // 10)  # 使用前10%的数据
        
        if k < 2:
            return 0.5
        
        # Hill估计器
        log_ratio = np.log(sorted_X[:k-1] / sorted_X[1:k])
        hill_estimator = np.mean(log_ratio)
        
        return max(0.1, min(2.0, hill_estimator))  # 限制在合理范围内
    
    def _assess_gpd_fit_quality(self, upper_tail: np.ndarray, lower_tail: np.ndarray) -> Dict:
        """评估GPD拟合质量"""
        quality = {'upper': 0.0, 'lower': 0.0}
        
        if len(upper_tail) >= self.min_tail_size:
            try:
                upper_params = self._fit_gpd(upper_tail)
                quality['upper'] = self._goodness_of_fit(upper_tail, upper_params)
            except Exception as e:
                logger.debug(f"上尾GPD拟合失败: {e}")
                quality['upper'] = 0.0
        
        if len(lower_tail) >= self.min_tail_size:
            try:
                lower_params = self._fit_gpd(-lower_tail)  # 对称处理
                quality['lower'] = self._goodness_of_fit(-lower_tail, lower_params)
            except Exception as e:
                logger.debug(f"下尾GPD拟合失败: {e}")
                quality['lower'] = 0.0
        
        return quality
    
    def _fit_gpd(self, tail_data: np.ndarray) -> Tuple[float, float]:
        """拟合GPD参数 (形状参数xi, 尺度参数sigma) - 高效实现"""
        if len(tail_data) < self.min_tail_size:
            return 0.1, 1.0
        
        # 使用模块级别的HAS_PYEXTREMES标志，避免重复导入
        if HAS_PYEXTREMES:
            try:
                # 使用pyextremes进行高效GPD拟合
                # 1. 智能阈值选择
                threshold = np.min(tail_data) if len(tail_data) < 50 else np.percentile(tail_data, 10)
                
                # 2. 高效GPD拟合
                gpd_fit = pe.GPD(tail_data, threshold=threshold)
                
                if hasattr(gpd_fit, 'params') and len(gpd_fit.params) >= 2:
                    xi, sigma = gpd_fit.params[0], gpd_fit.params[1]
                    
                    # 3. 验证拟合质量
                    if sigma > 0 and not np.isnan(xi) and not np.isnan(sigma):
                        return float(xi), float(sigma)
                
            except Exception as e:
                # pyextremes出错，记录日志后回退到传统实现
                logger.debug(f"pyextremes GPD拟合失败: {e}，使用传统实现")
        else:
            # pyextremes不可用，使用传统实现
            logger.debug("pyextremes不可用，使用传统GPD拟合")
        
        # 优化的传统GPD实现
        def negative_log_likelihood(params):
            xi, sigma = params
            if sigma <= 0:
                return 1e10
            
            n = len(tail_data)
            excess = tail_data - np.min(tail_data)  # 使用最小值作为阈值
            
            if abs(xi) < 1e-6:  # 指数分布情况
                log_likelihood = -n * np.log(sigma) - np.sum(excess) / sigma
            else:
                z = 1 + xi * excess / sigma
                if np.any(z <= 0):
                    return 1e10
                log_likelihood = -n * np.log(sigma) - (1 + 1/xi) * np.sum(np.log(z))
            
            return -log_likelihood
        
        # 改进的初始参数估计
        # excess 在 negative_log_likelihood 内部定义，这里需要重新计算
        excess_for_init = tail_data - np.min(tail_data)
        mean_excess = np.mean(excess_for_init)
        std_excess = np.std(excess_for_init)
        
        # 使用矩估计获得更好的初始值
        if std_excess > 0:
            method_moments = mean_excess / std_excess
            xi_initial = max(0.01, min(0.5, method_moments))
        else:
            xi_initial = 0.1
        
        sigma_initial = std_excess if std_excess > 0 else 1.0
        
        # 使用更稳定的优化方法
        try:
            from scipy.optimize import differential_evolution
            
            # 使用差分进化算法获得全局最优
            result = differential_evolution(
                negative_log_likelihood,
                bounds=[(-0.4, 1.0), (1e-6, std_excess * 2)],
                maxiter=100,
                popsize=15,
                tol=1e-6,
                polish=True
            )
            
            if result.success:
                xi_opt, sigma_opt = result.x[0], result.x[1]
                
                # 使用BFGS进行局部精化
                from scipy.optimize import minimize
                refined = minimize(
                    negative_log_likelihood,
                    [xi_opt, sigma_opt],
                    method='L-BFGS-B',
                    bounds=[(-0.5, 2.0), (1e-8, None)]
                )
                
                if refined.success:
                    return float(refined.x[0]), float(refined.x[1])
                else:
                    return float(xi_opt), float(sigma_opt)
        
        except ImportError:
            pass  # differential_evolution不可用
        except Exception:
            pass  # 全局优化失败，使用局部优化
        
        # 回退到改进的局部优化
        initial_params = [xi_initial, sigma_initial]
        
        # 使用多种优化方法提高成功率
        methods = ['L-BFGS-B', 'Nelder-Mead', 'Powell']
        
        for method in methods:
            try:
                result = minimize(
                    negative_log_likelihood,
                    initial_params,
                    method=method,
                    bounds=[(-0.5, 2.0), (1e-8, None)],
                    options={'maxiter': 500, 'ftol': 1e-8}
                )
                
                if result.success and np.all(np.isfinite(result.x)):
                    return float(result.x[0]), float(result.x[1])
            except Exception as e:
                logger.debug(f"GPD局部优化失败({method}): {e}")
                continue
        
        # 最后的回退方案
        return xi_initial, sigma_initial
    
    def _goodness_of_fit(self, tail_data: np.ndarray, params: Tuple[float, float]) -> float:
        """评估拟合优度"""
        try:
            xi, sigma = params
            
            # Kolmogorov-Smirnov检验
            from scipy.stats import kstest, genpareto
            
            # 标准化数据
            standardized = tail_data / sigma
            
            # 计算理论分布
            if abs(xi) < 1e-6:
                # 指数分布
                from scipy.stats import expon
                ks_stat, p_value = kstest(standardized, expon.cdf)
            else:
                # GPD分布
                ks_stat, p_value = kstest(standardized, lambda x: genpareto.cdf(x, xi))
            
            return max(0.0, p_value)  # 返回p值作为质量指标
            
        except Exception as e:
            logger.debug(f"拟合优度评估失败: {e}")
            return 0.0


class EnhancedRankPreservingScaler(BaseTransformer):
    """增强版排序保持缩放器"""
    
    def __init__(self, method='adaptive_soft_clip', alpha=3.0, beta=0.1, 
                 gpd_enabled=False, **params):
        super().__init__(
            method=method, alpha=alpha, beta=beta, 
            gpd_enabled=gpd_enabled, **params
        )
        self.method = method
        self.alpha = alpha
        self.beta = beta
        self.gpd_enabled = gpd_enabled
        self.gpd_analyzer = GPDTailAnalyzer() if gpd_enabled else None
        
    def fit(self, X: Union[pd.Series, np.ndarray]) -> 'EnhancedRankPreservingScaler':
        """拟合排序保持缩放参数"""
        X_array = self._to_array(X)
        X_clean = X_array[~np.isnan(X_array)]
        
        if len(X_clean) < 3:
            logger.warning("样本数不足，使用默认参数")
            self.fitted_params = {
                'median': np.median(X_clean) if len(X_clean) > 0 else 0,
                'mad': 1.0,
                'iqr': 1.0,
                'skewness': 0,
                'kurtosis': 0,
                'min': np.min(X_clean) if len(X_clean) > 0 else 0,
                'max': np.max(X_clean) if len(X_clean) > 0 else 0
            }
            self.is_fitted = True
            return self
        
        # 计算基础统计量
        self.fitted_params = {
            'median': np.median(X_clean),
            'mad': np.median(np.abs(X_clean - np.median(X_clean))),
            'iqr': np.percentile(X_clean, 75) - np.percentile(X_clean, 25),
            'skewness': stats.skew(X_clean),
            'kurtosis': stats.kurtosis(X_clean),
            'min': np.min(X_clean),
            'max': np.max(X_clean)
        }
        
        # 自动优化参数
        if self.method in ['adaptive_soft_clip', 'auto']:
            self._optimize_parameters(X_clean)
        
        self.is_fitted = True
        return self
    
    def transform(self, X: Union[pd.Series, np.ndarray]) -> Union[pd.Series, np.ndarray]:
        """应用变换"""
        if not self.is_fitted:
            raise ValueError("请先调用fit方法")
        
        X_array = self._to_array(X)
        original_format = X if isinstance(X, (pd.Series, pd.DataFrame)) else None
        
        # 根据方法选择变换
        if self.method == 'adaptive_soft_clip':
            transformed = self._adaptive_soft_clip_transform(X_array)
        elif self.method == 'enhanced_asinh':
            transformed = self._enhanced_asinh_transform(X_array)
        elif self.method == 'adaptive_tanh':
            transformed = self._adaptive_tanh_transform(X_array)
        elif self.method == 'robust_rank_normalize':
            transformed = self._robust_rank_normalize_transform(X_array)
        elif self.method == 'gpd_adaptive':
            transformed = self._gpd_adaptive_transform(X_array)
        else:
            transformed = self._adaptive_soft_clip_transform(X_array)
        
        # 确保排序保持
        if self.method in ['adaptive_soft_clip', 'enhanced_asinh', 'adaptive_tanh']:
            transformed = self._ensure_rank_preservation(X_array, transformed)
        
        if original_format is not None:
            return self._restore_format(transformed, original_format)
        return transformed
    
    def _optimize_parameters(self, X: np.ndarray):
        """自动优化参数"""
        skewness = self.fitted_params['skewness']
        kurtosis = self.fitted_params['kurtosis']
        extreme_ratio = np.mean(np.abs((X - np.mean(X)) / np.std(X)) > 3)
        
        # 根据数据特征调整参数
        if extreme_ratio > 0.1:
            self.alpha = 2.5  # 更严格的截断
            self.beta = 0.05  # 更平滑的过渡
        elif extreme_ratio > 0.05:
            self.alpha = 3.0
            self.beta = 0.1
        else:
            self.alpha = 3.5
            self.beta = 0.2
        
        # 根据偏度调整
        if abs(skewness) > 1.5:
            if self.method == 'adaptive_soft_clip':
                self.method = 'robust_rank_normalize'
    
    def _adaptive_soft_clip_transform(self, X: np.ndarray) -> np.ndarray:
        """自适应软截断变换 - 一阶连续版本"""
        median = self.fitted_params['median']
        mad = self.fitted_params['mad']
        
        # MAD标准化
        z = (X - median) / (mad + 1e-8)
        
        # 自适应软截断函数（C¹连续）
        def adaptive_soft_clip_continuous(z_val, alpha, beta):
            if abs(z_val) <= alpha:
                return z_val  # 线性区域
            else:
                # 使用平滑的过渡函数
                excess = abs(z_val) - alpha
                
                # 改进的软截断函数，保证导数连续
                # 在z=alpha处导数为1
                if beta > 0:
                    # 使用双曲正弦函数族
                    transformed_excess = beta * np.sinh(excess / beta)
                    # 调整系数使导数在连接处为1
                    scale_factor = 1.0 / np.cosh(0)  # cosh(0) = 1
                    transformed_excess *= scale_factor
                else:
                    # 回退到对数函数
                    transformed_excess = beta * np.log1p(excess / beta)
                    # 调整系数
                    scale_factor = 1.0 / (1 + 0)
                    transformed_excess *= scale_factor
                
                return np.sign(z_val) * (alpha + transformed_excess)
        
        # 向量化应用
        vfunc = np.vectorize(adaptive_soft_clip_continuous)
        clipped = vfunc(z, self.alpha, self.beta)
        
        # 逆变换
        return clipped * mad + median
    
    def _enhanced_asinh_transform(self, X: np.ndarray) -> np.ndarray:
        """增强版反双曲正弦变换"""
        median = self.fitted_params['median']
        mad = self.fitted_params['mad']
        skewness = self.fitted_params['skewness']
        
        # 偏度调整的标准化
        if skewness > 0:
            # 正偏：对正向极端值更敏感
            scaled = (X - median) / (mad + 1e-8)
            scaled = np.sign(scaled) * np.power(np.abs(scaled), 0.8)
        else:
            # 负偏：对负向极端值更敏感
            scaled = (X - median) / (mad + 1e-8)
            scaled = np.sign(scaled) * np.power(np.abs(scaled), 1.2)
        
        # 反双曲正弦变换
        transformed = np.arcsinh(scaled)
        
        # 标准化到原始范围
        orig_scale = np.std(X)
        trans_scale = np.std(transformed)
        return transformed * (orig_scale / (trans_scale + 1e-8))
    
    def _adaptive_tanh_transform(self, X: np.ndarray) -> np.ndarray:
        """自适应双曲正切变换"""
        median = self.fitted_params['median']
        iqr = self.fitted_params['iqr']
        
        # IQR标准化
        scaled = (X - median) / (iqr + 1e-8)
        
        # 自适应缩放因子
        kurtosis = self.fitted_params['kurtosis']
        if kurtosis > 3:
            scale_factor = 2.0  # 重尾分布，更强的压缩
        elif kurtosis < 2:
            scale_factor = 1.0  # 轻尾分布，较弱的压缩
        else:
            scale_factor = 1.5  # 中等情况
        
        # 双曲正切变换
        transformed = np.tanh(scaled * scale_factor)
        
        # 调整量级以保持可比性
        return transformed * iqr * 0.5 + median
    
    def _robust_rank_normalize_transform(self, X: np.ndarray) -> np.ndarray:
        """鲁棒排序正态化变换"""
        # 处理NaN值
        valid_mask = ~np.isnan(X)
        if not np.any(valid_mask):
            return X
        
        X_valid = X[valid_mask]
        
        # 计算排序
        ranks = stats.rankdata(X_valid)
        n = len(X_valid)
        
        # 转换为均匀分布
        uniform_values = (ranks - 0.5) / n
        
        # 转换为正态分布
        normal_values = stats.norm.ppf(uniform_values)
        
        # 标准化到原始范围
        result = X.copy()
        result[valid_mask] = normal_values * np.std(X_valid) + np.mean(X_valid)
        
        return result
    
    def _ensure_rank_preservation(self, original: np.ndarray, transformed: np.ndarray) -> np.ndarray:
        """确保排序保持"""
        # 处理NaN值
        valid_mask = ~np.isnan(original) & ~np.isnan(transformed)
        if not np.any(valid_mask):
            return transformed
        
        orig_valid = original[valid_mask]
        trans_valid = transformed[valid_mask]
        
        # 计算原始排序
        orig_ranks = stats.rankdata(orig_valid)
        trans_ranks = stats.rankdata(trans_valid)
        
        # 按原始排序重新排列变换后的值
        sorted_indices = np.argsort(orig_ranks)
        sorted_trans = trans_valid[sorted_indices]
        
        # 重新赋值，保持原始排序
        result = transformed.copy()
        result[valid_mask] = sorted_trans[np.argsort(orig_ranks)]
        
        return result
    
    def _gpd_adaptive_transform(self, X: np.ndarray) -> np.ndarray:
        """GPD自适应变换 - 智能模型选择"""
        if not self.gpd_analyzer:
            return self._adaptive_soft_clip_transform(X)
        
        # 分析尾部特征
        tail_features = self.gpd_analyzer.analyze_tail_features(X)
        
        if not tail_features.get('sufficient_data', False):
            return self._adaptive_soft_clip_transform(X)
        
        # 使用PyExtremes进行智能模型选择
        if HAS_PYEXTREMES:
            try:
                # 提取尾部数据
                upper_threshold = tail_features.get('upper_threshold', np.percentile(X, 90))
                lower_threshold = tail_features.get('lower_threshold', np.percentile(X, 10))
                
                upper_tail = X[X > upper_threshold] - upper_threshold
                lower_tail = lower_threshold - X[X < lower_threshold]
                
                # 智能模型选择
                model_selection = self._select_optimal_extreme_model(X, upper_tail, lower_tail, pe)
                
                if model_selection['success']:
                    return self._apply_selected_model(X, model_selection, pe)
                
            except Exception as e:
                # 模型选择失败，记录日志后回退到传统方法
                logger.debug(f"pyextremes模型选择失败: {e}，使用传统方法")
        else:
            logger.debug("pyextremes不可用，使用传统GPD自适应变换")
        
        # 传统GPD自适应逻辑
        tail_heaviness = tail_features.get('tail_heaviness', 0.5)
        gpd_quality = tail_features.get('gpd_fit_quality', {})
        avg_quality = (gpd_quality.get('upper', 0) + gpd_quality.get('lower', 0)) / 2
        
        if tail_heaviness > 0.8 and avg_quality > 0.7:
            return self._gpd_heavy_tail_transform(X)
        elif tail_heaviness > 0.4 and avg_quality > 0.5:
            return self._gpd_moderate_tail_transform(X)
        elif avg_quality > 0.3:
            return self._gpd_light_tail_transform(X)
        else:
            return self._adaptive_soft_clip_transform(X)
    
    def _select_optimal_extreme_model(self, X: np.ndarray, upper_tail: np.ndarray, 
                                   lower_tail: np.ndarray, pe) -> Dict[str, Any]:
        """使用PyExtremes进行智能极值模型选择"""
        
        model_selection = {
            'success': False,
            'upper_model': None,
            'lower_model': None,
            'upper_score': 0.0,
            'lower_score': 0.0,
            'selected_strategy': None
        }
        
        try:
            # 1. 定义候选模型
            candidate_models = {
                'GPD': pe.GPD,
                'GEV': pe.GEV,  # 广义极值分布
                'Pareto': pe.Pareto,  # 帕累托分布
                'Frechet': pe.Frechet,  # Fréchet分布
                'Weibull': pe.Weibull,  # Weibull分布
                'GenPareto': pe.GenPareto  # 广义帕累托分布
            }
            
            # 2. 上尾部模型选择
            if len(upper_tail) >= 20:  # 最少20个样本
                upper_scores = {}
                upper_fits = {}
                
                for model_name, model_class in candidate_models.items():
                    try:
                        if model_name == 'GEV':
                            # GEV需要块最大值数据
                            blocks = self._create_blocks(X, block_size=max(10, len(X)//50))
                            if len(blocks) >= 10:
                                fit = model_class(blocks)
                            else:
                                continue
                        else:
                            # 其他分布使用尾部数据
                            if model_name == 'Pareto':
                                # 帕累托分布需要正数据
                                if np.any(upper_tail <= 0):
                                    continue
                            fit = model_class(upper_tail)
                        
                        # 计算模型评分
                        score = self._calculate_model_score(fit, upper_tail, model_name)
                        upper_scores[model_name] = score
                        upper_fits[model_name] = fit
                        
                    except Exception:
                        continue
                
                # 选择最佳上尾部模型
                if upper_scores:
                    best_upper_model = max(upper_scores, key=upper_scores.get)
                    model_selection['upper_model'] = best_upper_model
                    model_selection['upper_score'] = upper_scores[best_upper_model]
                    model_selection['upper_fit'] = upper_fits[best_upper_model]
            
            # 3. 下尾部模型选择
            if len(lower_tail) >= 20:
                lower_scores = {}
                lower_fits = {}
                
                for model_name, model_class in candidate_models.items():
                    try:
                        # 对下尾部数据进行对称处理
                        symmetric_tail = lower_tail
                        
                        if model_name == 'Pareto':
                            if np.any(symmetric_tail <= 0):
                                continue
                        
                        fit = model_class(symmetric_tail)
                        score = self._calculate_model_score(fit, symmetric_tail, model_name)
                        lower_scores[model_name] = score
                        lower_fits[model_name] = fit
                        
                    except Exception:
                        continue
                
                # 选择最佳下尾部模型
                if lower_scores:
                    best_lower_model = max(lower_scores, key=lower_scores.get)
                    model_selection['lower_model'] = best_lower_model
                    model_selection['lower_score'] = lower_scores[best_lower_model]
                    model_selection['lower_fit'] = lower_fits[best_lower_model]
            
            # 4. 确定整体策略
            if model_selection['upper_model'] and model_selection['lower_model']:
                avg_score = (model_selection['upper_score'] + model_selection['lower_score']) / 2
                
                if avg_score > 0.8:
                    model_selection['selected_strategy'] = 'dual_extreme'
                elif avg_score > 0.6:
                    model_selection['selected_strategy'] = 'mixed_extreme'
                else:
                    model_selection['selected_strategy'] = 'conservative_extreme'
                
                model_selection['success'] = True
            
        except Exception as e:
            # 模型选择失败
            pass
        
        return model_selection
    
    def _calculate_model_score(self, fit, data: np.ndarray, model_name: str) -> float:
        """计算模型拟合评分"""
        try:
            score = 0.0
            
            # 1. 拟合优度评分 (40%)
            if hasattr(fit, 'aic') and len(data) >= 2:
                aic = fit.aic
                log_n = np.log(len(data))
                if log_n > 0:
                    aic_score = max(0, 1 - aic / (2 * len(data) * log_n))
                    score += 0.4 * aic_score
            
            # 2. Kolmogorov-Smirnov检验评分 (30%)
            try:
                from scipy.stats import kstest
                if hasattr(fit, 'cdf'):
                    ks_stat, ks_p = kstest(data, lambda x: fit.cdf(x))
                    ks_score = ks_p if ks_p > 0.05 else ks_p / 0.05
                    score += 0.3 * min(1.0, ks_score)
            except Exception as e:
                logger.debug(f"KS检验评分计算失败: {e}")
            
            # 3. 参数合理性评分 (20%)
            if hasattr(fit, 'params'):
                params = fit.params
                if model_name == 'GPD':
                    xi, sigma = params[0], params[1]
                    # 形状参数合理性
                    if -0.5 < xi < 2.0 and sigma > 0:
                        param_score = 1.0
                    elif -1.0 < xi < 3.0 and sigma > 0:
                        param_score = 0.7
                    else:
                        param_score = 0.3
                    score += 0.2 * param_score
                else:
                    # 其他模型的参数合理性检查
                    if all(np.isfinite(params)):
                        score += 0.2
            
            # 4. 模型复杂度惩罚 (10%)
            complexity_penalty = {
                'GPD': 0.0,      # 最简单
                'Pareto': 0.05,
                'GenPareto': 0.1,
                'GEV': 0.15,
                'Frechet': 0.2,
                'Weibull': 0.2   # 最复杂
            }
            score *= (1 - complexity_penalty.get(model_name, 0.1))
            
            return min(1.0, max(0.0, score))
            
        except Exception:
            return 0.0
    
    def _create_blocks(self, X: np.ndarray, block_size: int) -> np.ndarray:
        """创建块最大值数据用于GEV拟合"""
        # 处理NaN值
        X_clean = X[~np.isnan(X)]
        if len(X_clean) == 0:
            return np.array([])
        
        n_blocks = len(X_clean) // block_size
        if n_blocks < 10:
            return np.array([])
        
        blocks = X_clean[:n_blocks * block_size].reshape(n_blocks, block_size)
        block_maxima = np.max(blocks, axis=1)
        
        return block_maxima
    
    def _apply_selected_model(self, X: np.ndarray, model_selection: Dict[str, Any], pe) -> np.ndarray:
        """应用选择的极值模型进行变换"""
        transformed = X.copy()
        
        try:
            strategy = model_selection['selected_strategy']
            
            if strategy == 'dual_extreme':
                # 双尾部极值处理
                transformed = self._apply_dual_extreme_transform(X, model_selection)
            elif strategy == 'mixed_extreme':
                # 混合极值处理
                transformed = self._apply_mixed_extreme_transform(X, model_selection)
            else:
                # 保守极值处理
                transformed = self._apply_conservative_extreme_transform(X, model_selection)
            
        except Exception:
            # 回退到传统GPD方法
            transformed = self._gpd_heavy_tail_transform(X)
        
        return transformed
    
    def _apply_dual_extreme_transform(self, X: np.ndarray, model_selection: Dict[str, Any]) -> np.ndarray:
        """双尾部极值变换 - 一阶连续版本"""
        transformed = X.copy()
        
        # 计算阈值和过渡区域
        upper_threshold = np.percentile(X, 90)
        lower_threshold = np.percentile(X, 10)
        
        # 定义过渡区域宽度（5%的数据范围）
        data_range = np.percentile(X, 95) - np.percentile(X, 5)
        transition_width = 0.05 * data_range
        
        upper_transition_start = upper_threshold - transition_width
        lower_transition_end = lower_threshold + transition_width
        
        # 上尾部变换（带平滑过渡）
        upper_mask = X > upper_threshold
        upper_transition_mask = (X > upper_transition_start) & (X <= upper_threshold)
        
        if np.any(upper_mask):
            # 极值区域：使用极值模型
            upper_tail = X[upper_mask] - upper_threshold
            upper_fit = model_selection['upper_fit']
            
            if hasattr(upper_fit, 'ppf'):
                uniform_p = np.linspace(0.01, 0.99, len(upper_tail))
                transformed_tail = upper_fit.ppf(uniform_p)
                transformed[upper_mask] = upper_threshold + transformed_tail
        
        if np.any(upper_transition_mask):
            # 过渡区域：使用平滑混合
            transformed[upper_transition_mask] = self._smooth_upper_transition(
                X[upper_transition_mask], upper_threshold, upper_transition_start,
                model_selection['upper_fit']
            )
        
        # 下尾部变换（带平滑过渡）
        lower_mask = X < lower_threshold
        lower_transition_mask = (X >= lower_threshold) & (X < lower_transition_end)
        
        if np.any(lower_mask):
            # 极值区域：使用极值模型
            lower_tail = lower_threshold - X[lower_mask]
            lower_fit = model_selection['lower_fit']
            
            if hasattr(lower_fit, 'ppf'):
                uniform_p = np.linspace(0.01, 0.99, len(lower_tail))
                transformed_tail = lower_fit.ppf(uniform_p)
                transformed[lower_mask] = lower_threshold - transformed_tail
        
        if np.any(lower_transition_mask):
            # 过渡区域：使用平滑混合
            transformed[lower_transition_mask] = self._smooth_lower_transition(
                X[lower_transition_mask], lower_threshold, lower_transition_end,
                model_selection['lower_fit']
            )
        
        # 中部区域：使用改进的连续排序正态化
        middle_mask = ~upper_mask & ~upper_transition_mask & ~lower_mask & ~lower_transition_mask
        if np.any(middle_mask):
            transformed[middle_mask] = self._continuous_rank_normalize_transform(X[middle_mask])
        
        return transformed
    
    def _smooth_upper_transition(self, X: np.ndarray, threshold: float, 
                               transition_start: float, upper_fit) -> np.ndarray:
        """上尾部平滑过渡函数 - 保证C¹连续"""
        # 计算过渡权重
        transition_range = threshold - transition_start
        if transition_range <= 0:
            return self._continuous_rank_normalize_transform(X)
        
        # 使用平滑的sigmoid权重函数
        t = (X - transition_start) / transition_range  # 归一化到[0,1]
        
        # 平滑权重函数（三阶多项式，保证端点导数为0）
        # w(t) = 3t² - 2t³, 满足: w(0)=0, w(1)=1, w'(0)=0, w'(1)=0
        weight = 3 * t**2 - 2 * t**3
        
        # 计算主体变换值
        middle_values = self._continuous_rank_normalize_transform(X)
        
        # 计算极值变换值
        excess = X - threshold
        if hasattr(upper_fit, 'ppf'):
            # 使用极值模型的线性近似
            try:
                # 在阈值附近进行泰勒展开
                epsilon = 1e-6
                f_0 = upper_fit.ppf(0.5)  # 中位数变换
                f_eps = upper_fit.ppf(0.5 + epsilon)
                derivative = (f_eps - f_0) / epsilon
                
                extreme_values = threshold + f_0 + derivative * excess
            except:
                extreme_values = threshold + excess * 0.5  # 回退到线性
        else:
            extreme_values = threshold + excess * 0.5
        
        # 平滑混合
        return middle_values * (1 - weight) + extreme_values * weight
    
    def _smooth_lower_transition(self, X: np.ndarray, threshold: float, 
                               transition_end: float, lower_fit) -> np.ndarray:
        """下尾部平滑过渡函数 - 保证C¹连续"""
        # 计算过渡权重
        transition_range = transition_end - threshold
        if transition_range <= 0:
            return self._continuous_rank_normalize_transform(X)
        
        # 使用平滑的sigmoid权重函数
        t = (transition_end - X) / transition_range  # 归一化到[0,1]
        
        # 平滑权重函数（三阶多项式）
        weight = 3 * t**2 - 2 * t**3
        
        # 计算主体变换值
        middle_values = self._continuous_rank_normalize_transform(X)
        
        # 计算极值变换值
        excess = threshold - X
        if hasattr(lower_fit, 'ppf'):
            try:
                # 在阈值附近进行泰勒展开
                epsilon = 1e-6
                f_0 = lower_fit.ppf(0.5)
                f_eps = lower_fit.ppf(0.5 + epsilon)
                derivative = (f_eps - f_0) / epsilon
                
                extreme_values = threshold - f_0 - derivative * excess
            except:
                extreme_values = threshold - excess * 0.5
        else:
            extreme_values = threshold - excess * 0.5
        
        # 平滑混合
        return middle_values * (1 - weight) + extreme_values * weight
    
    def _continuous_rank_normalize_transform(self, X: np.ndarray) -> np.ndarray:
        """连续排序正态化变换 - 保证C¹连续"""
        # 处理NaN值
        valid_mask = ~np.isnan(X)
        if not np.any(valid_mask):
            return X
        
        X_valid = X[valid_mask]
        
        # 使用连续的分位数函数代替离散排序
        n = len(X_valid)
        
        # 计算经验分布函数（连续版本）
        from scipy.stats import norm
        
        # 使用核密度估计获得连续分布
        try:
            from scipy.stats import gaussian_kde
            kde = gaussian_kde(X_valid, bw_method='silverman')
            
            # 计算每个点的累积分布值
            x_grid = np.linspace(np.min(X_valid), np.max(X_valid), 1000)
            cdf_values = np.array([kde.integrate_box_1d(-np.inf, x) for x in x_grid])
            
            # 插值获得每个数据点的CDF值
            from scipy.interpolate import interp1d
            cdf_func = interp1d(x_grid, cdf_values, kind='cubic', bounds_error=False, fill_value=(0, 1))
            
            uniform_values = cdf_func(X_valid)
            
        except ImportError:
            # 回退到改进的离散方法
            ranks = stats.rankdata(X_valid)
            uniform_values = (ranks - 0.5) / n
        
        # 确保CDF值在合理范围内
        uniform_values = np.clip(uniform_values, 0.01, 0.99)
        
        # 转换为正态分布
        normal_values = norm.ppf(uniform_values)
        
        # 标准化到原始范围
        result = X.copy()
        result[valid_mask] = normal_values * np.std(X_valid) + np.mean(X_valid)
        
        return result
    
    def _apply_mixed_extreme_transform(self, X: np.ndarray, model_selection: Dict[str, Any]) -> np.ndarray:
        """混合极值变换"""
        # 优先使用得分更高的模型
        if model_selection['upper_score'] > model_selection['lower_score']:
            # 上尾部使用极值模型，下尾部使用GPD
            return self._apply_upper_extreme_lower_gpd(X, model_selection)
        else:
            # 下尾部使用极值模型，上尾部使用GPD
            return self._apply_lower_extreme_upper_gpd(X, model_selection)
    
    def _apply_conservative_extreme_transform(self, X: np.ndarray, model_selection: Dict[str, Any]) -> np.ndarray:
        """保守极值变换"""
        # 仅对最极端的值使用极值模型
        transformed = X.copy()
        
        # 仅处理最极端的5%
        extreme_upper = np.percentile(X, 95)
        extreme_lower = np.percentile(X, 5)
        
        upper_mask = X > extreme_upper
        lower_mask = X < extreme_lower
        
        if np.any(upper_mask) and model_selection['upper_fit']:
            upper_tail = X[upper_mask] - extreme_upper
            upper_fit = model_selection['upper_fit']
            
            if hasattr(upper_fit, 'ppf'):
                uniform_p = np.linspace(0.01, 0.99, len(upper_tail))
                transformed_tail = upper_fit.ppf(uniform_p)
                transformed[upper_mask] = extreme_upper + transformed_tail * 0.5  # 保守缩放
        
        if np.any(lower_mask) and model_selection['lower_fit']:
            lower_tail = extreme_lower - X[lower_mask]
            lower_fit = model_selection['lower_fit']
            
            if hasattr(lower_fit, 'ppf'):
                uniform_p = np.linspace(0.01, 0.99, len(lower_tail))
                transformed_tail = lower_fit.ppf(uniform_p)
                transformed[lower_mask] = extreme_lower - transformed_tail * 0.5  # 保守缩放
        
        # 其他区域使用自适应软截断
        middle_mask = ~upper_mask & ~lower_mask
        if np.any(middle_mask):
            transformed[middle_mask] = self._adaptive_soft_clip_transform(X[middle_mask])
        
        return transformed
    
    def _apply_upper_extreme_lower_gpd(self, X: np.ndarray, model_selection: Dict[str, Any]) -> np.ndarray:
        """上尾部极值模型 + 下尾部GPD"""
        transformed = X.copy()
        
        # 上尾部使用极值模型
        upper_threshold = np.percentile(X, 90)
        upper_mask = X > upper_threshold
        if np.any(upper_mask):
            upper_tail = X[upper_mask] - upper_threshold
            upper_fit = model_selection['upper_fit']
            
            if hasattr(upper_fit, 'ppf'):
                uniform_p = np.linspace(0.01, 0.99, len(upper_tail))
                transformed_tail = upper_fit.ppf(uniform_p)
                transformed[upper_mask] = upper_threshold + transformed_tail
        
        # 下尾部使用GPD
        lower_threshold = np.percentile(X, 10)
        lower_mask = X < lower_threshold
        if np.any(lower_mask):
            lower_tail = lower_threshold - X[lower_mask]
            params = self.gpd_analyzer._fit_gpd(lower_tail)
            transformed[lower_mask] = -self._apply_gpd_transform(
                lower_tail, params, lower_threshold, 'lower'
            )
        
        # 中部区域使用排序正态化
        middle_mask = ~upper_mask & ~lower_mask
        if np.any(middle_mask):
            transformed[middle_mask] = self._robust_rank_normalize_transform(X[middle_mask])
        
        return transformed
    
    def _apply_lower_extreme_upper_gpd(self, X: np.ndarray, model_selection: Dict[str, Any]) -> np.ndarray:
        """下尾部极值模型 + 上尾部GPD"""
        transformed = X.copy()
        
        # 上尾部使用GPD
        upper_threshold = np.percentile(X, 90)
        upper_mask = X > upper_threshold
        if np.any(upper_mask):
            upper_tail = X[upper_mask] - upper_threshold
            params = self.gpd_analyzer._fit_gpd(upper_tail)
            transformed[upper_mask] = self._apply_gpd_transform(
                upper_tail, params, upper_threshold, 'upper'
            )
        
        # 下尾部使用极值模型
        lower_threshold = np.percentile(X, 10)
        lower_mask = X < lower_threshold
        if np.any(lower_mask):
            lower_tail = lower_threshold - X[lower_mask]
            lower_fit = model_selection['lower_fit']
            
            if hasattr(lower_fit, 'ppf'):
                uniform_p = np.linspace(0.01, 0.99, len(lower_tail))
                transformed_tail = lower_fit.ppf(uniform_p)
                transformed[lower_mask] = lower_threshold - transformed_tail
        
        # 中部区域使用排序正态化
        middle_mask = ~upper_mask & ~lower_mask
        if np.any(middle_mask):
            transformed[middle_mask] = self._robust_rank_normalize_transform(X[middle_mask])
        
        return transformed
    
    def _gpd_heavy_tail_transform(self, X: np.ndarray) -> np.ndarray:
        """GPD重尾变换"""
        if not self.gpd_analyzer:
            return self._robust_rank_normalize_transform(X)
        
        transformed = X.copy()
        
        # 获取尾部特征
        tail_features = self.gpd_analyzer.analyze_tail_features(X)
        upper_threshold = tail_features.get('upper_threshold', np.percentile(X, 95))
        lower_threshold = tail_features.get('lower_threshold', np.percentile(X, 5))
        
        # 上尾部GPD变换
        upper_mask = X > upper_threshold
        if np.any(upper_mask):
            upper_tail = X[upper_mask] - upper_threshold
            upper_params = self.gpd_analyzer._fit_gpd(upper_tail)
            transformed[upper_mask] = self._apply_gpd_transform(
                upper_tail, upper_params, upper_threshold, 'upper'
            )
        
        # 下尾部GPD变换
        lower_mask = X < lower_threshold
        if np.any(lower_mask):
            lower_tail = lower_threshold - X[lower_mask]
            lower_params = self.gpd_analyzer._fit_gpd(lower_tail)
            transformed[lower_mask] = -self._apply_gpd_transform(
                lower_tail, lower_params, lower_threshold, 'lower'
            )
        
        # 中部区域使用排序正态化
        middle_mask = ~upper_mask & ~lower_mask
        if np.any(middle_mask):
            middle_data = X[middle_mask]
            transformed[middle_mask] = self._robust_rank_normalize_transform(middle_data)
        
        return transformed
    
    def _gpd_moderate_tail_transform(self, X: np.ndarray) -> np.ndarray:
        """GPD中等尾部变换"""
        if not self.gpd_analyzer:
            return self._enhanced_asinh_transform(X)
        
        transformed = X.copy()
        
        # 获取尾部特征
        tail_features = self.gpd_analyzer.analyze_tail_features(X)
        upper_threshold = tail_features.get('upper_threshold', np.percentile(X, 90))
        lower_threshold = tail_features.get('lower_threshold', np.percentile(X, 10))
        
        # 上尾部软GPD变换
        upper_mask = X > upper_threshold
        if np.any(upper_mask):
            upper_tail = X[upper_mask] - upper_threshold
            # 使用混合方法：GPD + 软截断
            gpd_transformed = self._apply_gpd_transform(
                upper_tail, (0.5, np.std(upper_tail)), upper_threshold, 'upper'
            )
            # 与软截断混合
            soft_clipped = self._adaptive_soft_clip_transform(X[upper_mask])
            transformed[upper_mask] = 0.7 * gpd_transformed + 0.3 * soft_clipped
        
        # 下尾部软GPD变换
        lower_mask = X < lower_threshold
        if np.any(lower_mask):
            lower_tail = lower_threshold - X[lower_mask]
            gpd_transformed = -self._apply_gpd_transform(
                lower_tail, (0.5, np.std(lower_tail)), lower_threshold, 'lower'
            )
            soft_clipped = self._adaptive_soft_clip_transform(X[lower_mask])
            transformed[lower_mask] = 0.7 * gpd_transformed + 0.3 * soft_clipped
        
        # 中部区域使用asinh变换
        middle_mask = ~upper_mask & ~lower_mask
        if np.any(middle_mask):
            transformed[middle_mask] = self._enhanced_asinh_transform(X[middle_mask])
        
        return transformed
    
    def _gpd_light_tail_transform(self, X: np.ndarray) -> np.ndarray:
        """GPD轻尾变换"""
        # 对于轻尾数据，主要使用传统方法，仅在极端值处使用GPD
        transformed = self._adaptive_soft_clip_transform(X)
        
        if not self.gpd_analyzer:
            return transformed
        
        # 仅对最极端的1%数据使用GPD
        extreme_upper = np.percentile(X, 99)
        extreme_lower = np.percentile(X, 1)
        
        extreme_upper_mask = X > extreme_upper
        extreme_lower_mask = X < extreme_lower
        
        if np.any(extreme_upper_mask):
            extreme_tail = X[extreme_upper_mask] - extreme_upper
            if len(extreme_tail) >= 5:  # 至少5个样本
                params = self.gpd_analyzer._fit_gpd(extreme_tail)
                transformed[extreme_upper_mask] = self._apply_gpd_transform(
                    extreme_tail, params, extreme_upper, 'upper'
                )
        
        if np.any(extreme_lower_mask):
            extreme_tail = extreme_lower - X[extreme_lower_mask]
            if len(extreme_tail) >= 5:
                params = self.gpd_analyzer._fit_gpd(extreme_tail)
                transformed[extreme_lower_mask] = -self._apply_gpd_transform(
                    extreme_tail, params, extreme_lower, 'lower'
                )
        
        return transformed
    
    def _apply_gpd_transform(self, tail_data: np.ndarray, params: Tuple[float, float], 
                           threshold: float, tail_type: str) -> np.ndarray:
        """应用GPD变换 - 高效实现"""
        xi, sigma = params
        
        # 使用模块级别的HAS_PYEXTREMES标志
        if HAS_PYEXTREMES:
            try:
                # 使用pyextremes的GPD变换功能
                if hasattr(pe, 'gpd_transform'):
                    # 直接使用pyextremes的变换函数
                    if tail_type == 'upper':
                        return threshold + pe.gpd_transform(tail_data, xi, sigma)
                    else:
                        return threshold - pe.gpd_transform(tail_data, xi, sigma)
                
            except Exception as e:
                # pyextremes出错，记录日志后回退到传统实现
                logger.debug(f"pyextremes GPD变换失败: {e}，使用传统实现")
        else:
            logger.debug("pyextremes不可用，使用传统GPD变换")
        
        # 优化的传统GPD变换实现
        n = len(tail_data)
        
        if abs(xi) < 1e-6:  # 指数分布情况
            # 使用更稳定的指数变换
            # 避免随机数，使用确定性变换
            transformed = -sigma * np.log1p(tail_data / sigma)
        else:
            # 优化的GPD分位数变换
            # 使用确定性分位数而不是随机数
            uniform_p = np.linspace(0.01, 0.99, n)
            
            # 预计算常用项
            if xi != 0:
                inv_xi = 1.0 / xi
                transformed = (sigma / xi) * (np.power(1 - uniform_p, -xi) - 1)
            else:
                transformed = -sigma * np.log(1 - uniform_p)
        
        # 调整量级
        if tail_type == 'upper':
            return threshold + transformed * np.std(tail_data)
        else:
            return threshold - transformed * np.std(tail_data)


class SmartAdaptiveWinsorizer(BaseTransformer):
    """智能自适应去极值器"""
    
    def __init__(self, method='smart_adaptive', max_outlier_frac=0.05, 
                 auto_optimize=True, preserve_tail_info=True):
        super().__init__(
            method=method, max_outlier_frac=max_outlier_frac,
            auto_optimize=auto_optimize, preserve_tail_info=preserve_tail_info
        )
        self.method = method
        self.max_outlier_frac = max_outlier_frac
        self.auto_optimize = auto_optimize
        self.preserve_tail_info = preserve_tail_info
        
    def fit(self, X: Union[pd.Series, np.ndarray]) -> 'SmartAdaptiveWinsorizer':
        """拟合智能阈值"""
        X_array = self._to_array(X)
        X_clean = X_array[~np.isnan(X_array)]
        
        if len(X_clean) < 3:
            logger.warning("样本数不足，使用默认阈值")
            self.thresholds = {
                'lower': np.min(X_clean) - 1 if len(X_clean) > 0 else -1,
                'upper': np.max(X_clean) + 1 if len(X_clean) > 0 else 1,
                'method': 'default',
                'upper_factor': 3.0,
                'lower_factor': 3.0
            }
            self.distribution_features = self._calculate_distribution_features(X_clean) if len(X_clean) > 0 else {}
            self.is_fitted = True
            return self
        
        # 计算分布特征
        dist_features = self._calculate_distribution_features(X_clean)
        
        # 智能阈值计算
        if self.method == 'smart_adaptive':
            thresholds = self._smart_adaptive_thresholds(X_clean, dist_features)
        elif self.method == 'kde_based':
            thresholds = self._kde_based_thresholds(X_clean)
        elif self.method == 'mixture_model':
            thresholds = self._mixture_model_thresholds(X_clean)
        else:
            thresholds = self._smart_adaptive_thresholds(X_clean, dist_features)
        
        self.thresholds = thresholds
        self.distribution_features = dist_features
        
        # 自动优化参数
        if self.auto_optimize:
            self._optimize_thresholds(X_clean, thresholds)
        
        self.is_fitted = True
        return self
    
    def transform(self, X: Union[pd.Series, np.ndarray]) -> Union[pd.Series, np.ndarray]:
        """应用智能去极值"""
        if not self.is_fitted:
            raise ValueError("请先调用fit方法")
        
        X_array = self._to_array(X)
        original_format = X if isinstance(X, (pd.Series, pd.DataFrame)) else None
        
        # 根据方法选择变换
        if self.method == 'smart_adaptive':
            transformed = self._smart_adaptive_transform(X_array)
        elif self.method == 'kde_based':
            transformed = self._kde_based_transform(X_array)
        elif self.method == 'mixture_model':
            transformed = self._mixture_model_transform(X_array)
        else:
            transformed = self._smart_adaptive_transform(X_array)
        
        if original_format is not None:
            return self._restore_format(transformed, original_format)
        return transformed
    
    def _calculate_distribution_features(self, X: np.ndarray) -> Dict:
        """计算分布特征"""
        features = {
            'mean': np.mean(X),
            'median': np.median(X),
            'std': np.std(X),
            'skewness': stats.skew(X),
            'kurtosis': stats.kurtosis(X),
            'iqr': np.percentile(X, 75) - np.percentile(X, 25),
            'range': np.max(X) - np.min(X),
            'cv': np.std(X) / np.mean(X) if np.mean(X) != 0 else np.inf
        }
        
        # 极端值比例
        std_safe = features['std'] if features['std'] > 1e-10 else 1e-10
        z_scores = np.abs((X - features['mean']) / std_safe)
        features['outlier_ratio'] = np.mean(z_scores > 3)
        
        return features
    
    def _smart_adaptive_thresholds(self, X: np.ndarray, features: Dict) -> Dict:
        """智能自适应阈值计算"""
        outlier_ratio = features['outlier_ratio']
        skewness = features['skewness']
        
        # 基于极端值比例调整
        if outlier_ratio > 0.15:
            # 极端值很多，使用更宽松的阈值
            method = 'quantile'
            factor = 1.5
        elif outlier_ratio > 0.1:
            # 极端值较多，使用中等阈值
            method = 'iqr'
            factor = 1.5
        else:
            # 极端值较少，使用严格阈值
            method = 'mad'
            factor = 3.0
        
        # 基于偏度调整
        if abs(skewness) > 1:
            # 偏态分布，使用非对称阈值
            if skewness > 0:
                # 正偏，上界更宽松
                upper_factor = factor * 1.2
                lower_factor = factor * 0.8
            else:
                # 负偏，下界更宽松
                upper_factor = factor * 0.8
                lower_factor = factor * 1.2
        else:
            upper_factor = lower_factor = factor
        
        # 计算阈值
        if method == 'quantile':
            lower = np.percentile(X, self.max_outlier_frac * 50)
            upper = np.percentile(X, 100 - self.max_outlier_frac * 50)
        elif method == 'iqr':
            q25, q75 = np.percentile(X, [25, 75])
            iqr = q75 - q25
            lower = q25 - lower_factor * iqr
            upper = q75 + upper_factor * iqr
        else:  # mad
            median = np.median(X)
            mad = np.median(np.abs(X - median))
            lower = median - lower_factor * mad
            upper = median + upper_factor * mad
        
        return {
            'lower': lower,
            'upper': upper,
            'method': method,
            'upper_factor': upper_factor,
            'lower_factor': lower_factor
        }
    
    def _kde_based_thresholds(self, X: np.ndarray) -> Dict:
        """基于KDE的阈值计算"""
        try:
            from scipy.stats import gaussian_kde
            
            # 计算KDE
            kde = gaussian_kde(X)
            x_range = np.linspace(np.min(X), np.max(X), 1000)
            density = kde(x_range)
            
            # 找到密度最小的点作为阈值
            from scipy.signal import find_peaks
            peaks, _ = find_peaks(-density)  # 负密度找峰谷
            
            if len(peaks) >= 2:
                # 选择最外层的峰谷
                lower_idx = peaks[0]
                upper_idx = peaks[-1]
                lower = x_range[lower_idx]
                upper = x_range[upper_idx]
            else:
                # 回退到分位数方法
                lower = np.percentile(X, 2.5)
                upper = np.percentile(X, 97.5)
            
            return {
                'lower': lower,
                'upper': upper,
                'method': 'kde'
            }
        except:
            # 回退到简单方法
            return self._smart_adaptive_thresholds(X, self._calculate_distribution_features(X))
    
    def _mixture_model_thresholds(self, X: np.ndarray) -> Dict:
        """基于混合模型的阈值计算"""
        try:
            from sklearn.mixture import GaussianMixture
            
            # 拟合双峰混合模型
            gm = GaussianMixture(n_components=2, random_state=42)
            gm.fit(X.reshape(-1, 1))
            
            # 获取组件参数
            means = gm.means_.flatten()
            stds = np.sqrt(gm.covariances_.flatten())
            
            # 选择更极端的组件作为异常值
            if means[0] < means[1]:
                outlier_mean, outlier_std = means[0], stds[0]
                normal_mean, normal_std = means[1], stds[1]
            else:
                outlier_mean, outlier_std = means[1], stds[1]
                normal_mean, normal_std = means[0], stds[0]
            
            # 计算3σ阈值
            if outlier_mean < normal_mean:
                lower = outlier_mean - 3 * outlier_std
                upper = normal_mean + 3 * normal_std
            else:
                lower = normal_mean - 3 * normal_std
                upper = outlier_mean + 3 * outlier_std
            
            return {
                'lower': lower,
                'upper': upper,
                'method': 'mixture'
            }
        except:
            # 回退到简单方法
            return self._smart_adaptive_thresholds(X, self._calculate_distribution_features(X))
    
    def _optimize_thresholds(self, X: np.ndarray, thresholds: Dict):
        """优化阈值"""
        # 简单的优化：确保阈值不会产生过多截断
        lower_mask = X < thresholds['lower']
        upper_mask = X > thresholds['upper']
        total_outliers = np.sum(lower_mask) + np.sum(upper_mask)
        outlier_ratio = total_outliers / len(X)
        
        # 如果极端值比例过高，调整阈值
        if outlier_ratio > self.max_outlier_frac * 2:
            # 收紧阈值
            center = np.median(X)
            range_val = thresholds['upper'] - thresholds['lower']
            new_range = range_val * 0.8
            thresholds['lower'] = center - new_range / 2
            thresholds['upper'] = center + new_range / 2
        
        # 如果极端值比例过低，放宽阈值
        elif outlier_ratio < self.max_outlier_frac * 0.5:
            # 放宽阈值
            center = np.median(X)
            range_val = thresholds['upper'] - thresholds['lower']
            new_range = range_val * 1.2
            thresholds['lower'] = center - new_range / 2
            thresholds['upper'] = center + new_range / 2
    
    def _smart_adaptive_transform(self, X: np.ndarray) -> np.ndarray:
        """智能自适应变换 - C¹连续软截断版本"""
        lower = self.thresholds['lower']
        upper = self.thresholds['upper']
        
        # 完全使用C¹连续的平滑截断，替代硬截断
        transformed = self._smooth_clip_continuous(X, lower, upper)
        
        # 如果需要保持尾部信息，使用增强的软过渡
        if self.preserve_tail_info:
            # 对超出阈值的部分使用增强软过渡
            lower_mask = X < lower
            upper_mask = X > upper
            
            if np.any(lower_mask):
                # 下尾部增强软过渡
                excess = lower - X[lower_mask]
                # 使用改进的指数软过渡，保证C¹连续
                transition_width = (upper - lower) * 0.1
                soft_factor = np.exp(-excess / transition_width)
                transformed[lower_mask] = lower - excess * soft_factor
            
            if np.any(upper_mask):
                # 上尾部增强软过渡
                excess = X[upper_mask] - upper
                transition_width = (upper - lower) * 0.1
                soft_factor = np.exp(-excess / transition_width)
                transformed[upper_mask] = upper + excess * soft_factor
        
        return transformed
    
    def _smooth_clip_continuous(self, X: np.ndarray, lower_bound: float, upper_bound: float) -> np.ndarray:
        """C¹连续的平滑截断函数"""
        range_width = upper_bound - lower_bound
        if range_width <= 0:
            return X
        
        # 计算过渡区域宽度（10%的数据范围）
        transition_width = 0.05 * range_width
        
        # 上边界平滑过渡
        upper_transition_start = upper_bound - transition_width
        upper_mask = X > upper_transition_start
        
        # 使用三阶多项式权重函数，保证C¹连续
        # w(t) = 3t² - 2t³, 满足: w(0)=0, w(1)=1, w'(0)=0, w'(1)=0
        t_upper = np.clip((X[upper_mask] - upper_transition_start) / transition_width, 0, 1)
        weight_upper = 3 * t_upper**2 - 2 * t_upper**3
        
        # 下边界平滑过渡
        lower_transition_end = lower_bound + transition_width
        lower_mask = X < lower_transition_end
        
        t_lower = np.clip((lower_transition_end - X[lower_mask]) / transition_width, 0, 1)
        weight_lower = 3 * t_lower**2 - 2 * t_lower**3
        
        # 构建结果
        result = X.copy()
        
        # 处理上过渡区域
        if np.any(upper_mask):
            # 线性部分值
            linear_values = X[upper_mask]
            # 截断部分值（使用平滑过渡到上边界）
            excess_upper = X[upper_mask] - upper_bound
            # 防止指数溢出
            exp_arg_upper = -excess_upper / transition_width
            exp_arg_upper = np.clip(exp_arg_upper, -709, 709)  # np.log(float_max) ≈ 709
            clipped_values = upper_bound + excess_upper * np.exp(exp_arg_upper)
            # 混合
            result[upper_mask] = linear_values * (1 - weight_upper) + clipped_values * weight_upper
        
        # 处理下过渡区域
        if np.any(lower_mask):
            # 线性部分值
            linear_values = X[lower_mask]
            # 截断部分值（使用平滑过渡到下边界）
            excess_lower = lower_bound - X[lower_mask]
            # 防止指数溢出
            exp_arg_lower = -excess_lower / transition_width
            exp_arg_lower = np.clip(exp_arg_lower, -709, 709)
            clipped_values = lower_bound - excess_lower * np.exp(exp_arg_lower)
            # 混合
            result[lower_mask] = linear_values * (1 - weight_lower) + clipped_values * weight_lower
        
        # 中部区域保持不变
        middle_mask = ~upper_mask & ~lower_mask
        result[middle_mask] = X[middle_mask]
        
        return result
    
    def _kde_based_transform(self, X: np.ndarray) -> np.ndarray:
        """基于KDE的变换"""
        return self._smart_adaptive_transform(X)
    
    def _mixture_model_transform(self, X: np.ndarray) -> np.ndarray:
        """基于混合模型的变换"""
        return self._smart_adaptive_transform(X)
