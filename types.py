# -*- coding: utf-8 -*-
"""
核心类型定义模块

定义流水线相关的协议、TypedDict 和类型别名，
为整个 factor_pipeline 提供统一的类型系统。
"""

from typing import Protocol, runtime_checkable, TypedDict, Any, Optional
from dataclasses import dataclass
import pandas as pd
import numpy as np


# =============================================================================
# 协议定义
# =============================================================================

@runtime_checkable
class PipelineStepProtocol(Protocol):
    """流水线步骤协议 - 所有步骤必须实现此接口"""
    name: str
    step_type: str
    is_fitted: bool
    
    def fit(self, X: pd.DataFrame, **kwargs: Any) -> 'PipelineStepProtocol':
        """拟合步骤参数"""
        ...
    
    def transform(self, X: pd.DataFrame, **kwargs: Any) -> pd.DataFrame:
        """应用步骤变换"""
        ...
    
    def fit_transform(self, X: pd.DataFrame, **kwargs: Any) -> pd.DataFrame:
        """拟合并变换"""
        ...
    
    def get_stats(self) -> dict[str, Any]:
        """获取步骤统计信息"""
        ...


# =============================================================================
# TypedDict 定义
# =============================================================================

class StepStats(TypedDict, total=False):
    """步骤统计信息"""
    name: str
    step_type: str
    is_fitted: bool
    params: dict[str, Any]
    execution_time_ms: float
    input_shape: tuple[int, int]
    output_shape: tuple[int, int]
    missing_rate_before: float
    missing_rate_after: float
    error: Optional[str]


class StepExecutionRecord(TypedDict, total=False):
    """步骤执行记录"""
    timestamp: float
    step_name: str
    step_type: str
    input_shape: tuple[int, int]
    output_shape: tuple[int, int]
    input_missing_rate: float
    output_missing_rate: float
    execution_time_ms: float
    error: Optional[str]


class PipelineExecutionSummary(TypedDict, total=False):
    """流水线执行摘要"""
    pipeline_name: str
    pipeline_version: str
    start_time: float
    end_time: float
    total_duration_ms: float
    steps: list[StepExecutionRecord]
    factor_count: int
    classification_results: Optional[dict[str, Any]]


class NeutralizationSummary(TypedDict, total=False):
    """中性化摘要"""
    stage1: dict[str, float]
    stage2: dict[str, float]
    method: str
    industry_count: int
    stock_count: int


class ARModelSummary(TypedDict, total=False):
    """AR模型摘要"""
    order: int
    aic: float
    bic: float
    coefficients: list[float]
    residual_std: float


# =============================================================================
# 类型别名
# =============================================================================

FactorData = dict[str, pd.DataFrame]
"""因子数据字典：因子名 -> DataFrame"""

IndustryData = pd.Series
"""行业数据：index为股票代码，值为行业分类"""

MarketCapData = pd.DataFrame
"""市值数据：shape为(T, N)"""

FactorDescriptions = dict[str, str]
"""因子描述字典：因子名 -> 自然语言描述"""


# =============================================================================
# 数据类
# =============================================================================

@dataclass
class StepOutput:
    """步骤变换输出（包含数据和统计信息）"""
    data: pd.DataFrame
    stats: StepStats
    duration_ms: float
    success: bool = True
    error: Optional[str] = None

    def __post_init__(self):
        if not self.success and self.error is None:
            self.error = "Unknown error"


@dataclass
class PipelineOutput:
    """流水线完整输出"""
    data: pd.DataFrame
    summary: PipelineExecutionSummary
    step_results: list[StepOutput]
    success: bool = True
