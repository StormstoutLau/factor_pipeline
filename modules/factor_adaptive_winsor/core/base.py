# -*- coding: utf-8 -*-
"""
基础接口定义
定义所有核心组件的统一接口
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Union, Optional
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class BaseTransformer(ABC):
    """变换器基类，定义统一接口"""
    
    def __init__(self, **params):
        self.params = params
        self.fitted_params = {}
        self.is_fitted = False
        
    @abstractmethod
    def fit(self, X: Union[pd.Series, pd.DataFrame, np.ndarray]) -> 'BaseTransformer':
        """拟合变换参数"""
        pass
    
    @abstractmethod
    def transform(self, X: Union[pd.Series, pd.DataFrame, np.ndarray]) -> Union[pd.Series, pd.DataFrame, np.ndarray]:
        """应用变换"""
        pass
    
    def fit_transform(self, X: Union[pd.Series, pd.DataFrame, np.ndarray]) -> Union[pd.Series, pd.DataFrame, np.ndarray]:
        """拟合并变换"""
        return self.fit(X).transform(X)
    
    def _to_array(self, X: Union[pd.Series, pd.DataFrame, np.ndarray]) -> np.ndarray:
        """转换为numpy数组"""
        if isinstance(X, pd.Series):
            return X.to_numpy()
        elif isinstance(X, pd.DataFrame):
            return X.to_numpy().flatten()
        else:
            return np.asarray(X)
    
    def _restore_format(self, X: np.ndarray, original: Union[pd.Series, pd.DataFrame]) -> Union[pd.Series, pd.DataFrame]:
        """恢复原始格式"""
        if isinstance(original, pd.Series):
            # 确保返回的是1D数组
            if X.ndim > 1:
                X = X.flatten()
            # 处理标量情况
            if X.size == 1:
                return pd.Series([X.item()], index=original.index, name=original.name)
            return pd.Series(X, index=original.index, name=original.name)
        elif isinstance(original, pd.DataFrame):
            expected_size = original.shape[0] * original.shape[1]
            if X.size == expected_size:
                # 正常情况：直接reshape
                return pd.DataFrame(X.reshape(original.shape),
                                  index=original.index,
                                  columns=original.columns)
            else:
                # 处理大小不匹配的情况
                logger.warning(f"数组大小不匹配: 期望 {expected_size}, 实际 {X.size}，尝试修复")
                if X.size > expected_size:
                    # 截断多余元素
                    X = X.flatten()[:expected_size]
                else:
                    # 填充缺失元素（用0填充）
                    X = np.pad(X.flatten(), (0, expected_size - X.size), mode='constant')
                return pd.DataFrame(X.reshape(original.shape),
                                  index=original.index,
                                  columns=original.columns)
        return X


class BaseDiagnoser(ABC):
    """诊断器基类"""
    
    def __init__(self, **params):
        self.params = params
        self.diagnosis_history = []
    
    @abstractmethod
    def diagnose(self, data: Union[pd.Series, pd.DataFrame]) -> Dict[str, Any]:
        """执行诊断"""
        pass
    
    def get_diagnosis_history(self) -> list:
        """获取诊断历史"""
        return self.diagnosis_history


class BaseEvaluator(ABC):
    """评估器基类"""
    
    def __init__(self, **params):
        self.params = params
        self.evaluation_history = []
    
    @abstractmethod
    def evaluate(self, *args, **kwargs) -> Dict[str, Any]:
        """执行评估"""
        pass
    
    def get_evaluation_history(self) -> list:
        """获取评估历史"""
        return self.evaluation_history


class DataDiagnosis:
    """数据诊断结果数据类"""
    
    def __init__(self):
        self.basic_quality = None
        self.distribution_features = None
        self.outlier_analysis = None
        self.tail_analysis = None
        self.normality_tests = None
        self.multimodality = None
        self.time_series_features = None
        self.completeness = None
        self.overall_quality_score = 0.0
        self.recommendations = []
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'basic_quality': self.basic_quality,
            'distribution_features': self.distribution_features,
            'outlier_analysis': self.outlier_analysis,
            'tail_analysis': self.tail_analysis,
            'normality_tests': self.normality_tests,
            'multimodality': self.multimodality,
            'time_series_features': self.time_series_features,
            'completeness': self.completeness,
            'overall_quality_score': self.overall_quality_score,
            'recommendations': self.recommendations
        }


class TransformationEvaluation:
    """变换评估结果数据类"""
    
    def __init__(self):
        self.quality_improvement = 0.0
        self.distribution_improvement = 0.0
        self.outlier_reduction = 0.0
        self.normality_improvement = 0.0
        self.information_preservation = 0.0
        self.rank_preservation = 0.0
        self.overall_score = 0.0
        self.needs_optimization = False
        self.new_diagnosis = None
        self.optimization_suggestions = []
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'quality_improvement': self.quality_improvement,
            'distribution_improvement': self.distribution_improvement,
            'outlier_reduction': self.outlier_reduction,
            'normality_improvement': self.normality_improvement,
            'information_preservation': self.information_preservation,
            'rank_preservation': self.rank_preservation,
            'overall_score': self.overall_score,
            'needs_optimization': self.needs_optimization,
            'new_diagnosis': self.new_diagnosis,
            'optimization_suggestions': self.optimization_suggestions
        }


class WorkflowResult:
    """工作流程结果数据类"""
    
    def __init__(self):
        self.original_data = None
        self.processed_data = None
        self.transformed_data = None
        self.standardized_data = None
        self.diagnosis_history = []
        self.final_diagnosis = None
        self.processing_log = []
        self.performance_metrics = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'original_data_shape': self.original_data.shape if self.original_data is not None else None,
            'processed_data_shape': self.processed_data.shape if self.processed_data is not None else None,
            'transformed_data_shape': self.transformed_data.shape if self.transformed_data is not None else None,
            'standardized_data_shape': self.standardized_data.shape if self.standardized_data is not None else None,
            'diagnosis_history': [d.to_dict() if hasattr(d, 'to_dict') else d for d in self.diagnosis_history],
            'final_diagnosis': self.final_diagnosis.to_dict() if self.final_diagnosis is not None and hasattr(self.final_diagnosis, 'to_dict') else self.final_diagnosis,
            'processing_log': self.processing_log,
            'performance_metrics': self.performance_metrics
        }
