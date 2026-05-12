# -*- coding: utf-8 -*-
"""
因子处理统一流水线 (Factor Processing Pipeline)
整合 Factor_Imputer_v2.0 + Factor_AdaptiveWinsor + Factor_Neutralizer_v2.0
GitHub: https://github.com/StormstoutLau/factor_pipeline
确保处理顺序: 插补 → 去极值/变换/标准化 → 中性化
"""

from .pipeline import FactorProcessingPipeline, PipelineStep, PipelineOrderValidator
from .adapters import ImputerAdapter, ProcessingAdapter, NeutralizerAdapter
from .config import PipelineConfig

__version__ = "1.0.0"

__all__ = [
    'FactorProcessingPipeline',
    'PipelineStep',
    'PipelineOrderValidator',
    'ImputerAdapter',
    'ProcessingAdapter',
    'NeutralizerAdapter',
    'PipelineConfig',
]
