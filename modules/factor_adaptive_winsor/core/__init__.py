# -*- coding: utf-8 -*-
"""
因子预处理核心模块
提供基础接口、变换器和诊断器
"""

from .base import BaseTransformer, BaseDiagnoser, BaseEvaluator, DataDiagnosis, TransformationEvaluation, WorkflowResult
from .data_diagnoser import DataQualityDiagnoser
from .transformers import (
    SmartOutlierDetector,
    AdaptiveTransformer,
    AdaptiveStandardizer
)
from .enhanced_transformers import (
    GPDTailAnalyzer,
    EnhancedRankPreservingScaler,
    SmartAdaptiveWinsorizer
)
from .evaluators import EffectEvaluator, FinalValidator
from .config import (
    DEFAULT_QUALITY_WEIGHTS,
    COMPAT_QUALITY_WEIGHTS,
    QUALITY_THRESHOLDS,
    DIAGNOSIS_THRESHOLDS,
    MIN_DATA_POINTS,
)

# 互操作性适配层
from .interop import (
    to_qlib_format,
    qlib_winsorize,
    to_alphalens_format,
    alphalens_preprocess,
    compare_with_scipy,
)

__all__ = [
    'BaseTransformer',
    'BaseDiagnoser', 
    'BaseEvaluator',
    'DataDiagnosis',
    'TransformationEvaluation',
    'WorkflowResult',
    'DataQualityDiagnoser',
    'SmartOutlierDetector',
    'AdaptiveTransformer',
    'AdaptiveStandardizer',
    'GPDTailAnalyzer',
    'EnhancedRankPreservingScaler',
    'SmartAdaptiveWinsorizer',
    'EffectEvaluator',
    'FinalValidator',
    'DEFAULT_QUALITY_WEIGHTS',
    'COMPAT_QUALITY_WEIGHTS',
    'QUALITY_THRESHOLDS',
    'DIAGNOSIS_THRESHOLDS',
    'MIN_DATA_POINTS',
    # 互操作性
    'to_qlib_format',
    'qlib_winsorize',
    'to_alphalens_format',
    'alphalens_preprocess',
    'compare_with_scipy',
]
