# -*- coding: utf-8 -*-
"""
基础接口定义 - 因子缺失插补模块
扩展Factor_Processing_v2.0的base.py，添加缺失插补相关接口
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd


class MissingType(Enum):
    """缺失类型枚举"""

    MCAR = "MCAR"  # 完全随机缺失
    MAR = "MAR"  # 随机缺失
    MNAR = "MNAR"  # 非随机缺失


class MissingPattern(Enum):
    """缺失模式枚举"""

    CROSS_SECTIONAL = "cross_sectional"  # 截面缺失
    TIME_SERIES = "time_series"  # 时序缺失
    BLOCK = "block"  # 块状缺失
    RANDOM = "random"  # 随机缺失


class ImputationStrategy(Enum):
    """插补策略枚举"""

    CROSS_SECTIONAL_MEDIAN = "cross_sectional_median"
    FORWARD_FILL = "forward_fill"
    ROLLING_MEAN = "rolling_mean"
    KNN = "knn"
    RANDOM_FOREST = "random_forest"
    FACTOR_REGRESSION = "factor_regression"
    MNAR_DUMMY = "mnar_dummy"


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


class BaseImputer(ABC):
    """插补器基类，定义统一接口"""

    def __init__(self, **params):
        self.params = params
        self.fitted_params = {}
        self.is_fitted = False
        self.missing_info = {}
        self.bias_guard = None

    @abstractmethod
    def fit(self, X: pd.DataFrame, missing_info: Dict[str, Any] = None) -> "BaseImputer":
        """
        拟合插补参数

        Parameters:
        -----------
        X : pd.DataFrame
            输入数据，行为时间，列为资产
        missing_info : Dict[str, Any]
            缺失信息，包含缺失类型、模式等

        Returns:
        --------
        self : BaseImputer
        """
        pass

    @abstractmethod
    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        应用插补

        Parameters:
        -----------
        X : pd.DataFrame
            需要插补的数据

        Returns:
        --------
        X_imputed : pd.DataFrame
            插补后的数据
        """
        pass

    def fit_transform(self, X: pd.DataFrame, missing_info: Dict[str, Any] = None) -> pd.DataFrame:
        """拟合并插补"""
        return self.fit(X, missing_info).transform(X)

    def detect_missing_type(self, X: pd.DataFrame) -> Dict[str, Any]:
        """
        检测缺失类型和模式

        Parameters:
        -----------
        X : pd.DataFrame
            输入数据

        Returns:
        --------
        missing_info : Dict[str, Any]
            包含缺失类型、模式、比例等信息
        """
        missing_info = {
            "missing_rate": self._calculate_missing_rate(X),
            "missing_pattern": self._detect_missing_pattern(X),
            "missing_mechanism": self._detect_missing_mechanism(X),
            "temporal_structure": self._detect_temporal_structure(X),
            "cross_sectional_structure": self._detect_cross_sectional_structure(X),
        }
        return missing_info

    def _calculate_missing_rate(self, X: pd.DataFrame) -> Dict[str, float]:
        """计算缺失率"""
        total_elements = X.shape[0] * X.shape[1]
        missing_elements = X.isnull().sum().sum()
        overall_rate = missing_elements / total_elements

        # 按时间点计算缺失率
        time_missing_rate = X.isnull().mean(axis=1)

        # 按资产计算缺失率
        asset_missing_rate = X.isnull().mean(axis=0)

        return {
            "overall": overall_rate,
            "by_time": time_missing_rate.to_dict(),
            "by_asset": asset_missing_rate.to_dict(),
            "max_time": time_missing_rate.max(),
            "max_asset": asset_missing_rate.max(),
            "min_time": time_missing_rate.min(),
            "min_asset": asset_missing_rate.min(),
        }

    def _detect_missing_pattern(self, X: pd.DataFrame) -> str:
        """检测缺失模式"""
        # 检测块状缺失
        missing_blocks = self._detect_missing_blocks(X)
        if missing_blocks["has_blocks"]:
            return MissingPattern.BLOCK.value

        # 检测时序缺失
        temporal_missing = self._detect_temporal_missing_pattern(X)
        if temporal_missing["is_temporal"]:
            return MissingPattern.TIME_SERIES.value

        # 检测截面缺失
        cross_sectional_missing = self._detect_cross_sectional_missing_pattern(X)
        if cross_sectional_missing["is_cross_sectional"]:
            return MissingPattern.CROSS_SECTIONAL.value

        return MissingPattern.RANDOM.value

    def _detect_missing_mechanism(self, X: pd.DataFrame) -> str:
        """检测缺失机制（简化版本）"""
        # 这里使用简化的启发式方法
        # 实际应用中可能需要更复杂的统计检验

        missing_rate = X.isnull().sum().sum() / (X.shape[0] * X.shape[1])

        if missing_rate < 0.05:
            return MissingType.MCAR.value
        elif missing_rate < 0.20:
            return MissingType.MAR.value
        else:
            return MissingType.MNAR.value

    def _detect_temporal_structure(self, X: pd.DataFrame) -> Dict[str, Any]:
        """检测时序结构"""
        return {
            "has_time_index": isinstance(X.index, pd.DatetimeIndex),
            "time_frequency": self._infer_frequency(X),
            "consecutive_missing": self._detect_consecutive_missing(X),
        }

    def _detect_cross_sectional_structure(self, X: pd.DataFrame) -> Dict[str, Any]:
        """检测截面结构"""
        return {
            "asset_count": X.shape[1],
            "time_count": X.shape[0],
            "similarity_structure": self._detect_similarity_structure(X),
        }

    def _detect_missing_blocks(self, X: pd.DataFrame) -> Dict[str, Any]:
        """检测块状缺失"""
        missing_mask = X.isnull()

        # 查找连续的缺失块
        block_size = 0
        max_block_size = 0

        for i in range(X.shape[0]):
            for j in range(X.shape[1]):
                if missing_mask.iloc[i, j]:
                    block_size += 1
                else:
                    max_block_size = max(max_block_size, block_size)
                    block_size = 0

        return {"has_blocks": max_block_size > max(X.shape) * 0.1, "max_block_size": max_block_size}

    def _detect_temporal_missing_pattern(self, X: pd.DataFrame) -> Dict[str, Any]:
        """检测时序缺失模式"""
        time_missing_rate = X.isnull().mean(axis=1)

        # 检查是否有连续的时间段缺失率较高
        consecutive_high_missing = 0
        for rate in time_missing_rate:
            if rate > 0.5:
                consecutive_high_missing += 1
            else:
                consecutive_high_missing = 0

        return {"is_temporal": consecutive_high_missing > 3, "consecutive_high_missing": consecutive_high_missing}

    def _detect_cross_sectional_missing_pattern(self, X: pd.DataFrame) -> Dict[str, Any]:
        """检测截面缺失模式"""
        asset_missing_rate = X.isnull().mean(axis=0)

        # 检查是否有大量资产在同一时间点缺失
        cross_sectional_entropy = -np.sum(asset_missing_rate * np.log(asset_missing_rate + 1e-10))

        return {"is_cross_sectional": cross_sectional_entropy < 2.0, "entropy": cross_sectional_entropy}

    def _infer_frequency(self, X: pd.DataFrame) -> str:
        """推断数据频率"""
        if not isinstance(X.index, pd.DatetimeIndex):
            return "unknown"

        try:
            freq = pd.infer_freq(X.index)
            return freq if freq else "unknown"
        except (ValueError, TypeError):
            return "unknown"

    def _detect_consecutive_missing(self, X: pd.DataFrame) -> Dict[str, Any]:
        """检测连续缺失"""
        missing_mask = X.isnull()
        consecutive_counts = {}

        for asset in X.columns:
            max_consecutive = 0
            current_consecutive = 0

            for is_missing in missing_mask[asset]:
                if is_missing:
                    current_consecutive += 1
                    max_consecutive = max(max_consecutive, current_consecutive)
                else:
                    current_consecutive = 0

            consecutive_counts[asset] = max_consecutive

        return {"max_consecutive": max(consecutive_counts.values()), "by_asset": consecutive_counts}

    def _detect_similarity_structure(self, X: pd.DataFrame) -> Dict[str, Any]:
        """检测相似性结构"""
        # 计算资产间的相关性
        correlation_matrix = X.corr()

        # 计算相关性的统计特征
        upper_triangle = correlation_matrix.where(np.triu(np.ones(correlation_matrix.shape), k=1).astype(bool)).stack()

        return {
            "mean_correlation": upper_triangle.mean(),
            "std_correlation": upper_triangle.std(),
            "min_correlation": upper_triangle.min(),
            "max_correlation": upper_triangle.max(),
        }


class MissingDiagnosisResult:
    """缺失诊断结果数据类"""

    def __init__(self):
        self.missing_type = None
        self.missing_pattern = None
        self.missing_rate = {}
        self.temporal_structure = {}
        self.cross_sectional_structure = {}
        self.recommendations = []
        self.overall_quality_score = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "missing_type": self.missing_type,
            "missing_pattern": self.missing_pattern,
            "missing_rate": self.missing_rate,
            "temporal_structure": self.temporal_structure,
            "cross_sectional_structure": self.cross_sectional_structure,
            "recommendations": self.recommendations,
            "overall_quality_score": self.overall_quality_score,
        }


class ImputationResult:
    """插补结果数据类"""

    def __init__(self):
        self.original_data = None
        self.imputed_data = None
        self.imputation_strategy = None
        self.imputation_quality = {}
        self.bias_validation = {}
        self.processing_log = []
        self.performance_metrics = {}

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "original_data_shape": self.original_data.shape if self.original_data is not None else None,
            "imputed_data_shape": self.imputed_data.shape if self.imputed_data is not None else None,
            "imputation_strategy": self.imputation_strategy,
            "imputation_quality": self.imputation_quality,
            "bias_validation": self.bias_validation,
            "processing_log": self.processing_log,
            "performance_metrics": self.performance_metrics,
        }
