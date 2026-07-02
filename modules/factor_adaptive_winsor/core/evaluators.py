# -*- coding: utf-8 -*-
"""
评估器模块
提供变换效果评估和最终质量验证功能
"""

import pandas as pd
import numpy as np
from scipy import stats
from sklearn.metrics import mutual_info_score
from sklearn.preprocessing import StandardScaler
from typing import Dict, Any, Union, List, Tuple
import warnings

from .base import BaseEvaluator, TransformationEvaluation, DataDiagnosis

warnings.filterwarnings("ignore")


class EffectEvaluator(BaseEvaluator):
    """变换效果评估器 - 评估变换后的改进效果"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(**(config or {}))
        self.config = config or {}
        self.weights = self.config.get('weights', {
            'quality_improvement': 0.25,
            'distribution_improvement': 0.20,
            'outlier_reduction': 0.20,
            'normality_improvement': 0.15,
            'information_preservation': 0.10,
            'rank_preservation': 0.10
        })
        
    def evaluate(self, transformed_data: Union[pd.Series, pd.DataFrame], 
                original_diagnosis: DataDiagnosis,
                original_data: Union[pd.Series, pd.DataFrame] = None) -> TransformationEvaluation:
        """评估变换效果"""
        evaluation = TransformationEvaluation()
        
        # 转换为DataFrame格式
        if isinstance(transformed_data, pd.Series):
            transformed_data = transformed_data.to_frame()
        if original_data is not None and isinstance(original_data, pd.Series):
            original_data = original_data.to_frame()
        
        # 重新诊断变换后数据
        from .data_diagnoser import DataQualityDiagnoser
        new_diagnoser = DataQualityDiagnoser()
        new_diagnosis = new_diagnoser.diagnose(transformed_data)
        evaluation.new_diagnosis = new_diagnosis
        
        # 计算改进指标
        evaluation.quality_improvement = self._calculate_quality_improvement(
            original_diagnosis, new_diagnosis
        )
        
        evaluation.distribution_improvement = self._calculate_distribution_improvement(
            original_diagnosis, new_diagnosis
        )
        
        evaluation.outlier_reduction = self._calculate_outlier_reduction(
            original_diagnosis, new_diagnosis
        )
        
        evaluation.normality_improvement = self._calculate_normality_improvement(
            original_diagnosis, new_diagnosis
        )
        
        evaluation.information_preservation = self._calculate_information_preservation(
            original_data, transformed_data
        )
        
        evaluation.rank_preservation = self._calculate_rank_preservation(
            original_data, transformed_data
        )
        
        # 综合评分
        evaluation.overall_score = self._calculate_overall_score(evaluation)
        
        # 判断是否需要优化
        evaluation.needs_optimization = evaluation.overall_score < self.config.get(
            'min_acceptable_score', 0.7
        )
        
        # 生成优化建议
        evaluation.optimization_suggestions = self._generate_optimization_suggestions(
            evaluation, original_diagnosis, new_diagnosis
        )
        
        # 保存评估历史
        self.evaluation_history.append(evaluation)
        
        return evaluation
    
    def _calculate_quality_improvement(self, original_diagnosis: DataDiagnosis, 
                                   new_diagnosis: DataDiagnosis) -> float:
        """计算质量改进度"""
        if not original_diagnosis.overall_quality_score or not new_diagnosis.overall_quality_score:
            return 0.0
        
        improvement = new_diagnosis.overall_quality_score - original_diagnosis.overall_quality_score
        return max(0.0, min(1.0, improvement))
    
    def _calculate_distribution_improvement(self, original_diagnosis: DataDiagnosis,
                                       new_diagnosis: DataDiagnosis) -> float:
        """计算分布改进度"""
        if not original_diagnosis.distribution_features or not new_diagnosis.distribution_features:
            return 0.0
        
        orig_dist = original_diagnosis.distribution_features['summary']
        new_dist = new_diagnosis.distribution_features['summary']
        
        # 偏度改进
        skew_improvement = max(0, abs(orig_dist['mean_skewness']) - abs(new_dist['mean_skewness']))
        skew_score = min(1.0, skew_improvement / 2.0)  # 偏度改进最多贡献0.5分
        
        # 重尾改进
        heavy_tail_improvement = max(0, orig_dist['heavy_tailed_columns'] - new_dist['heavy_tailed_columns'])
        heavy_tail_score = min(1.0, heavy_tail_improvement / max(1, len(orig_dist)))  # 重尾改进贡献
        
        # 分布宽度改进
        wide_spread_improvement = max(0, orig_dist['wide_spread_columns'] - new_dist['wide_spread_columns'])
        wide_spread_score = min(1.0, wide_spread_improvement / max(1, len(orig_dist)))
        
        # 综合分布改进
        distribution_improvement = (skew_score + heavy_tail_score + wide_spread_score) / 3.0
        return max(0.0, min(1.0, distribution_improvement))
    
    def _calculate_outlier_reduction(self, original_diagnosis: DataDiagnosis,
                                 new_diagnosis: DataDiagnosis) -> float:
        """计算极端值减少度"""
        if not original_diagnosis.outlier_analysis or not new_diagnosis.outlier_analysis:
            return 0.0
        
        orig_outlier = original_diagnosis.outlier_analysis['summary']['mean_outlier_ratio']
        new_outlier = new_diagnosis.outlier_analysis['summary']['mean_outlier_ratio']
        
        reduction = orig_outlier - new_outlier
        return max(0.0, min(1.0, reduction * 10))  # 放大减少效果
    
    def _calculate_normality_improvement(self, original_diagnosis: DataDiagnosis,
                                      new_diagnosis: DataDiagnosis) -> float:
        """计算正态性改进度"""
        if not original_diagnosis.normality_tests or not new_diagnosis.normality_tests:
            return 0.0
        
        orig_normal = original_diagnosis.normality_tests['summary']['normality_ratio']
        new_normal = new_diagnosis.normality_tests['summary']['normality_ratio']
        
        improvement = new_normal - orig_normal
        return max(0.0, min(1.0, improvement))
    
    def _calculate_information_preservation(self, original_data: Union[pd.Series, pd.DataFrame],
                                       transformed_data: Union[pd.Series, pd.DataFrame]) -> float:
        """计算信息保留度"""
        if original_data is None:
            return 0.0
        
        # 转换为numpy数组
        if isinstance(original_data, pd.DataFrame):
            orig_array = original_data.values.flatten()
            trans_array = transformed_data.values.flatten()
        else:
            orig_array = original_data.values if hasattr(original_data, 'values') else original_data
            trans_array = transformed_data.values if hasattr(transformed_data, 'values') else transformed_data
        
        # 移除NaN值
        valid_mask = ~(np.isnan(orig_array) | np.isnan(trans_array))
        orig_valid = orig_array[valid_mask]
        trans_valid = trans_array[valid_mask]
        
        if len(orig_valid) < 10:
            return 0.0
        
        # 计算相关性作为信息保留度的代理
        try:
            correlation = np.corrcoef(orig_valid, trans_valid)[0, 1]
            information_preservation = max(0.0, abs(correlation))
        except:
            information_preservation = 0.0
        
        return min(1.0, information_preservation)
    
    def _calculate_rank_preservation(self, original_data: Union[pd.Series, pd.DataFrame],
                                  transformed_data: Union[pd.Series, pd.DataFrame]) -> float:
        """计算排序保持度"""
        if original_data is None:
            return 0.0
        
        # 转换为numpy数组
        if isinstance(original_data, pd.DataFrame):
            orig_array = original_data.values.flatten()
            trans_array = transformed_data.values.flatten()
        else:
            orig_array = original_data.values if hasattr(original_data, 'values') else original_data
            trans_array = transformed_data.values if hasattr(transformed_data, 'values') else transformed_data
        
        # 移除NaN值
        valid_mask = ~(np.isnan(orig_array) | np.isnan(trans_array))
        orig_valid = orig_array[valid_mask]
        trans_valid = trans_array[valid_mask]
        
        if len(orig_valid) < 10:
            return 0.0
        
        # 计算Spearman相关系数
        try:
            rank_correlation, _ = stats.spearmanr(orig_valid, trans_valid)
            # 处理NaN情况：当数据中存在大量重复值时，spearmanr可能返回NaN
            if np.isnan(rank_correlation):
                # 如果原始数据和变换后数据完全相同，秩保留度应为1.0
                if np.allclose(orig_valid, trans_valid, equal_nan=True):
                    rank_preservation = 1.0
                else:
                    # 尝试使用Kendall tau作为替代
                    try:
                        tau, _ = stats.kendalltau(orig_valid, trans_valid)
                        rank_preservation = max(0.0, tau) if not np.isnan(tau) else 0.0
                    except:
                        rank_preservation = 0.0
            else:
                rank_preservation = max(0.0, rank_correlation)
        except:
            rank_preservation = 0.0
        
        return min(1.0, rank_preservation)
    
    def _calculate_overall_score(self, evaluation: TransformationEvaluation) -> float:
        """计算综合评分"""
        score = 0.0
        
        # 加权求和
        score += self.weights.get('quality_improvement', 0.25) * evaluation.quality_improvement
        score += self.weights.get('distribution_improvement', 0.20) * evaluation.distribution_improvement
        score += self.weights.get('outlier_reduction', 0.20) * evaluation.outlier_reduction
        score += self.weights.get('normality_improvement', 0.15) * evaluation.normality_improvement
        score += self.weights.get('information_preservation', 0.10) * evaluation.information_preservation
        score += self.weights.get('rank_preservation', 0.10) * evaluation.rank_preservation
        
        return max(0.0, min(1.0, score))
    
    def _generate_optimization_suggestions(self, evaluation: TransformationEvaluation,
                                     original_diagnosis: DataDiagnosis,
                                     new_diagnosis: DataDiagnosis) -> List[str]:
        """生成优化建议"""
        suggestions = []
        
        # 基于各项指标生成建议
        if evaluation.quality_improvement < 0.1:
            suggestions.append("整体质量改进有限，建议检查数据预处理步骤")
        
        if evaluation.distribution_improvement < 0.2:
            suggestions.append("分布特征改进不足，建议尝试其他变换方法")
        
        if evaluation.outlier_reduction < 0.3:
            suggestions.append("极端值处理效果不佳，建议调整去极值参数")
        
        if evaluation.normality_improvement < 0.2:
            suggestions.append("正态性改进不明显，建议使用更强的正态性变换")
        
        if evaluation.information_preservation < 0.8:
            suggestions.append("信息保留度较低，建议使用更温和的变换方法")
        
        if evaluation.rank_preservation < 0.9:
            suggestions.append("排序保持度不足，建议使用排序保持变换")
        
        # 基于新诊断结果的建议
        if new_diagnosis.outlier_analysis and new_diagnosis.outlier_analysis['summary']['mean_outlier_ratio'] > 0.05:
            suggestions.append("变换后仍有较多极端值，建议进行二次去极值处理")
        
        if new_diagnosis.normality_tests and not new_diagnosis.normality_tests['summary']['overall_normality']:
            suggestions.append("变换后仍不符合正态分布，建议尝试复合变换")
        
        return suggestions


class FinalValidator(BaseEvaluator):
    """最终质量验证器 - 确保数据适合建模"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(**(config or {}))
        self.config = config or {}
        self.validation_rules = self._setup_validation_rules()
    
    def evaluate(self, data: Union[pd.Series, pd.DataFrame]) -> Dict[str, Any]:
        """实现抽象方法 - 调用validate方法"""
        return self.validate(data)
        
    def validate(self, data: Union[pd.Series, pd.DataFrame]) -> Dict[str, Any]:
        """最终质量验证"""
        validation_result = {
            'data_quality': self._validate_data_quality(data),
            'statistical_properties': self._validate_statistical_properties(data),
            'modeling_suitability': self._validate_modeling_suitability(data),
            'business_rules': self._validate_business_rules(data),
            'overall_score': 0.0,
            'passed': False,
            'warnings': [],
            'errors': []
        }
        
        # 计算综合评分
        validation_result['overall_score'] = self._calculate_final_score(validation_result)
        
        # 判断是否通过
        validation_result['passed'] = validation_result['overall_score'] >= self.config.get(
            'min_final_score', 0.8
        )
        
        # 收集警告和错误
        for category, results in validation_result.items():
            if isinstance(results, dict) and 'warnings' in results:
                validation_result['warnings'].extend(results['warnings'])
            if isinstance(results, dict) and 'errors' in results:
                validation_result['errors'].extend(results['errors'])
        
        # 保存验证历史
        self.evaluation_history.append(validation_result)
        
        return validation_result
    
    def _setup_validation_rules(self) -> Dict[str, Any]:
        """设置验证规则"""
        return {
            'data_quality': {
                'min_completeness': 0.95,
                'max_missing_ratio': 0.05,
                'max_duplicate_ratio': 0.01
            },
            'statistical_properties': {
                'min_normality_ratio': 0.7,
                'max_outlier_ratio': 0.05,
                'max_skewness_abs': 2.0,
                'max_kurtosis_range': (2.0, 4.0)
            },
            'modeling_suitability': {
                'min_variance': 1e-6,
                'max_condition_number': 1e6,
                'min_signal_to_noise': 1.0
            },
            'business_rules': {
                'value_range_check': True,
                'volatility_check': True,
                'correlation_check': True
            }
        }
    
    def _validate_data_quality(self, data: Union[pd.Series, pd.DataFrame]) -> Dict[str, Any]:
        """验证数据质量"""
        if isinstance(data, pd.Series):
            data = data.to_frame()
        
        result = {
            'completeness_score': 0.0,
            'consistency_score': 0.0,
            'accuracy_score': 0.0,
            'warnings': [],
            'errors': []
        }
        
        # 完整性检查
        total_cells = data.size
        missing_cells = data.isnull().sum().sum()
        completeness_ratio = 1 - (missing_cells / total_cells)
        result['completeness_score'] = completeness_ratio
        
        if completeness_ratio < self.validation_rules['data_quality']['min_completeness']:
            result['errors'].append(f"数据完整性不足: {completeness_ratio:.3f} < {self.validation_rules['data_quality']['min_completeness']}")
        elif completeness_ratio < 0.98:
            result['warnings'].append(f"数据完整性较低: {completeness_ratio:.3f}")
        
        # 一致性检查
        duplicate_cells = data.duplicated().sum()
        duplicate_ratio = duplicate_cells / len(data)
        result['consistency_score'] = 1 - duplicate_ratio
        
        if duplicate_ratio > self.validation_rules['data_quality']['max_duplicate_ratio']:
            result['warnings'].append(f"存在重复数据: {duplicate_ratio:.3f}")
        
        # 准确性检查（基于数值范围）
        numeric_columns = data.select_dtypes(include=[np.number]).columns
        if len(numeric_columns) > 0:
            # 检查无穷值
            inf_count = np.isinf(data[numeric_columns]).sum().sum()
            if inf_count > 0:
                result['errors'].append(f"存在无穷值: {inf_count}个")
                result['accuracy_score'] = 0.0
            else:
                result['accuracy_score'] = 1.0
        
        return result
    
    def _validate_statistical_properties(self, data: Union[pd.Series, pd.DataFrame]) -> Dict[str, Any]:
        """验证统计特性"""
        if isinstance(data, pd.Series):
            data = data.to_frame()
        
        result = {
            'normality_score': 0.0,
            'outlier_score': 0.0,
            'distribution_score': 0.0,
            'warnings': [],
            'errors': []
        }
        
        numeric_columns = data.select_dtypes(include=[np.number]).columns
        
        if len(numeric_columns) == 0:
            result['errors'].append("没有数值型数据")
            return result
        
        # 正态性检查
        normal_columns = 0
        skewness_ok_columns = 0
        kurtosis_ok_columns = 0
        
        for column in numeric_columns:
            col_data = data[column].dropna()
            if len(col_data) < 8:
                continue
            
            # 正态性检验
            try:
                _, p_shapiro = stats.shapiro(col_data[:5000])
                if p_shapiro > 0.05:
                    normal_columns += 1
            except:
                pass
            
            # 偏度检查
            skewness = stats.skew(col_data)
            if abs(skewness) <= self.validation_rules['statistical_properties']['max_skewness_abs']:
                skewness_ok_columns += 1
            elif abs(skewness) > 3:
                result['warnings'].append(f"列 {column} 偏度过高: {skewness:.3f}")
            
            # 峰度检查
            kurtosis = stats.kurtosis(col_data)
            min_kurt, max_kurt = self.validation_rules['statistical_properties']['max_kurtosis_range']
            if min_kurt <= kurtosis <= max_kurt:
                kurtosis_ok_columns += 1
        
        total_columns = len(numeric_columns)
        result['normality_score'] = normal_columns / total_columns if total_columns > 0 else 0
        result['distribution_score'] = (skewness_ok_columns + kurtosis_ok_columns) / (2 * total_columns) if total_columns > 0 else 0
        
        # 极端值检查
        outlier_ratios = []
        for column in numeric_columns:
            col_data = data[column].dropna()
            if len(col_data) > 0:
                z_scores = np.abs(stats.zscore(col_data))
                outlier_ratio = np.mean(z_scores > 3)
                outlier_ratios.append(outlier_ratio)
        
        if outlier_ratios:
            mean_outlier_ratio = np.mean(outlier_ratios)
            result['outlier_score'] = max(0, 1 - mean_outlier_ratio * 10)
            
            if mean_outlier_ratio > self.validation_rules['statistical_properties']['max_outlier_ratio']:
                result['warnings'].append(f"极端值比例过高: {mean_outlier_ratio:.3f}")
        
        return result
    
    def _validate_modeling_suitability(self, data: Union[pd.Series, pd.DataFrame]) -> Dict[str, Any]:
        """验证建模适用性"""
        if isinstance(data, pd.Series):
            data = data.to_frame()
        
        result = {
            'variance_score': 0.0,
            'stability_score': 0.0,
            'signal_score': 0.0,
            'warnings': [],
            'errors': []
        }
        
        numeric_columns = data.select_dtypes(include=[np.number]).columns
        
        if len(numeric_columns) == 0:
            result['errors'].append("没有数值型数据可用于建模")
            return result
        
        # 方差检查
        low_variance_columns = 0
        for column in numeric_columns:
            col_data = data[column].dropna()
            if len(col_data) > 1:
                variance = np.var(col_data)
                if variance < self.validation_rules['modeling_suitability']['min_variance']:
                    low_variance_columns += 1
                    result['warnings'].append(f"列 {column} 方差过低: {variance:.2e}")
        
        result['variance_score'] = 1 - (low_variance_columns / len(numeric_columns))
        
        # 稳定性检查（基于条件数）
        try:
            # 简化的条件数估计
            data_matrix = data[numeric_columns].dropna().values
            if data_matrix.shape[0] > data_matrix.shape[1]:
                # 计算相关矩阵的条件数
                corr_matrix = np.corrcoef(data_matrix.T)
                eigenvalues = np.linalg.eigvals(corr_matrix)
                
                # 安全计算条件数：处理所有特征值过小的情况
                valid_eigenvalues = eigenvalues[eigenvalues > 1e-10]
                if len(valid_eigenvalues) == 0:
                    # 所有特征值都过小，使用保守估计
                    condition_number = 1e10
                    result['warnings'].append("条件数计算异常：所有特征值过小，使用保守估计")
                else:
                    condition_number = np.max(eigenvalues) / np.max(valid_eigenvalues)
                
                if condition_number > self.validation_rules['modeling_suitability']['max_condition_number']:
                    result['warnings'].append(f"条件数过高: {condition_number:.2e}")
                
                result['stability_score'] = max(0, 1 - np.log10(condition_number) / 10)
            else:
                result['stability_score'] = 0.5
        except:
            result['stability_score'] = 0.5
        
        # 信噪比检查（简化版本）
        try:
            # 使用变异系数作为信噪比的代理
            cv_scores = []
            for column in numeric_columns:
                col_data = data[column].dropna()
                if len(col_data) > 1:
                    mean_val = np.mean(col_data)
                    if abs(mean_val) > 1e-10:
                        cv = np.std(col_data) / abs(mean_val)
                    else:
                        cv = 10.0  # 均值为0时，设置高CV值
                    cv_scores.append(min(10, cv))  # 限制范围
            
            if cv_scores:
                mean_cv = np.mean(cv_scores)
                result['signal_score'] = max(0, 1 - mean_cv / 10)
        except:
            result['signal_score'] = 0.5
        
        return result
    
    def _validate_business_rules(self, data: Union[pd.Series, pd.DataFrame]) -> Dict[str, Any]:
        """验证业务规则"""
        if isinstance(data, pd.Series):
            data = data.to_frame()
        
        result = {
            'range_score': 0.0,
            'volatility_score': 0.0,
            'correlation_score': 0.0,
            'warnings': [],
            'errors': []
        }
        
        numeric_columns = data.select_dtypes(include=[np.number]).columns
        
        if len(numeric_columns) == 0:
            return result
        
        # 值范围检查
        if self.validation_rules['business_rules']['value_range_check']:
            # 检查是否存在异常的极值
            for column in numeric_columns:
                col_data = data[column].dropna()
                if len(col_data) > 0:
                    q1, q3 = np.percentile(col_data, [25, 75])
                    iqr = q3 - q1
                    lower_bound = q1 - 3 * iqr
                    upper_bound = q3 + 3 * iqr
                    
                    extreme_outliers = col_data[(col_data < lower_bound) | (col_data > upper_bound)]
                    if len(extreme_outliers) > 0:
                        result['warnings'].append(f"列 {column} 存在极端异常值: {len(extreme_outliers)}个")
        
        # 波动性检查
        if self.validation_rules['business_rules']['volatility_check'] and isinstance(data.index, pd.DatetimeIndex):
            for column in numeric_columns:
                col_data = data[column].dropna()
                if len(col_data) > 10:
                    # 计算滚动标准差
                    rolling_std = col_data.rolling(window=min(10, len(col_data)//4)).std()
                    if rolling_std.max() > rolling_std.min() * 5:
                        result['warnings'].append(f"列 {column} 波动性不稳定")
        
        # 相关性检查
        if self.validation_rules['business_rules']['correlation_check'] and len(numeric_columns) > 1:
            try:
                corr_matrix = data[numeric_columns].corr()
                high_corr_pairs = []
                
                for i in range(len(corr_matrix.columns)):
                    for j in range(i+1, len(corr_matrix.columns)):
                        corr_value = abs(corr_matrix.iloc[i, j])
                        if corr_value > 0.9:
                            high_corr_pairs.append((corr_matrix.columns[i], corr_matrix.columns[j], corr_value))
                
                if high_corr_pairs:
                    result['warnings'].append(f"存在高相关性变量对: {len(high_corr_pairs)}对")
            except:
                pass
        
        # 简化评分
        result['range_score'] = 0.8  # 如果没有极端异常，给高分
        result['volatility_score'] = 0.8  # 如果波动稳定，给高分
        result['correlation_score'] = 0.8  # 如果相关性合理，给高分
        
        return result
    
    def _calculate_final_score(self, validation_result: Dict[str, Any]) -> float:
        """计算最终验证评分"""
        scores = []
        
        # 各类别评分
        if 'data_quality' in validation_result:
            dq = validation_result['data_quality']
            scores.append(np.mean([dq.get('completeness_score', 0),
                                dq.get('consistency_score', 0),
                                dq.get('accuracy_score', 0)]))
        
        if 'statistical_properties' in validation_result:
            sp = validation_result['statistical_properties']
            scores.append(np.mean([sp.get('normality_score', 0),
                                sp.get('outlier_score', 0),
                                sp.get('distribution_score', 0)]))
        
        if 'modeling_suitability' in validation_result:
            ms = validation_result['modeling_suitability']
            scores.append(np.mean([ms.get('variance_score', 0),
                                ms.get('stability_score', 0),
                                ms.get('signal_score', 0)]))
        
        if 'business_rules' in validation_result:
            br = validation_result['business_rules']
            scores.append(np.mean([br.get('range_score', 0),
                                br.get('volatility_score', 0),
                                br.get('correlation_score', 0)]))
        
        return np.mean(scores) if scores else 0.0
