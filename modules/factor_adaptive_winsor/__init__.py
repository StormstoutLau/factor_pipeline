# -*- coding: utf-8 -*-
"""Factor_AdaptiveWinsor - C¹连续自适应软截断因子预处理库

首个提供三区域（主体/过渡/尾部）C¹连续自适应去极值的因子预处理工具。
公共 API 由 core/ 子包提供，此处统一 re-export。
"""

from .core import (
    BaseTransformer,
    BaseDiagnoser,
    AdaptiveTransformer,
    AdaptiveStandardizer,
    SmartAdaptiveWinsorizer,
    SmartOutlierDetector,
    DataQualityDiagnoser,
)

__version__ = "0.1.0"
__all__ = [
    'BaseTransformer',
    'BaseDiagnoser',
    'AdaptiveTransformer',
    'AdaptiveStandardizer',
    'SmartAdaptiveWinsorizer',
    'SmartOutlierDetector',
    'DataQualityDiagnoser',
]
