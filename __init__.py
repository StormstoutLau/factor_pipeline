# -*- coding: utf-8 -*-
"""
因子处理统一流水线 (Factor Processing Pipeline)
整合 Factor_Imputer_v2.0 + Factor_AdaptiveWinsor + Factor_Neutralizer_v2.0
GitHub: https://github.com/StormstoutLau/factor_pipeline
确保处理顺序: 插补 → 去极值/变换/标准化 → 中性化

v2.0 新增：
- 因子指纹前置诊断层
- 语义-统计融合分类
- 三条差异化处理管道（静态/动态/混合）
- 可选 GARCH 白化
- 持续迁移监测
"""

from .types import (
    PipelineStepProtocol,
    StepStats,
    StepExecutionRecord,
    PipelineExecutionSummary,
    NeutralizationSummary,
    ARModelSummary,
    FactorData,
    IndustryData,
    MarketCapData,
    FactorDescriptions,
    StepOutput,
    PipelineOutput,
)

from .pipeline import FactorProcessingPipeline, PipelineOrderValidator
from .adapters import (
    PipelineStep,
    ImputerAdapter,
    ProcessingAdapter,
    NeutralizerAdapter,
    GarchWhiteningAdapter,
)
from .config import PipelineConfig, StepType, StepConfig, VALID_STEP_ORDERS

# v2.0 新增导出
try:
    from .pipelines_v2 import (
        FactorProcessingPipelineV2,
        PipelineV2Config,
        StaticFactorPipeline,
        DynamicFactorPipeline,
        MixedFactorPipeline,
    )
    _V2_AVAILABLE = True
except ImportError as _e:
    _V2_AVAILABLE = False
    logger.debug(f"v2 模块不可用: {_e}")

__version__ = "2.0.0"

__all__ = [
    # 类型系统
    'PipelineStepProtocol',
    'StepStats',
    'StepExecutionRecord',
    'PipelineExecutionSummary',
    'NeutralizationSummary',
    'ARModelSummary',
    'FactorData',
    'IndustryData',
    'MarketCapData',
    'FactorDescriptions',
    'StepOutput',
    'PipelineOutput',
    # v1.0 核心
    'FactorProcessingPipeline',
    'PipelineOrderValidator',
    'PipelineStep',
    'ImputerAdapter',
    'ProcessingAdapter',
    'NeutralizerAdapter',
    'GarchWhiteningAdapter',
    'PipelineConfig',
    'StepType',
    'StepConfig',
    'VALID_STEP_ORDERS',
    # v2.0 智能流水线（条件导出）
    'FactorProcessingPipelineV2',
    'PipelineV2Config',
    'StaticFactorPipeline',
    'DynamicFactorPipeline',
    'MixedFactorPipeline',
]


def check_v2_availability() -> bool:
    """检查 v2.0 智能流水线是否可用（依赖 Factor_Fingerprint 和 Factor_Decoupler）"""
    return _V2_AVAILABLE
