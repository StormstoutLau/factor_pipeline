# -*- coding: utf-8 -*-
"""
Factor Decoupler - 时间序列解耦模块

对动态因子进行时序去自相关，提取纯净的新息成分。
采用双重中性化设计：原始值中性化 → 提取残差 → 残差中性化。

设计哲学（与 Factor_Pipeline 项目保持一致）：
- sklearn 风格接口：fit/transform/fit_transform
- 数据驱动自适应：AR阶数由AIC/BIC自动选择
- 前瞻偏差防护：严格避免未来信息泄露
- 学术级校验：验证中性化效果和残差独立性

支持的解耦方法：
- 'ar' : AR模型残差（自适应阶数选择）
- 'difference' : 一阶差分
- 'hp_filter' : Hodrick-Prescott滤波
- 'auto' : 自动选择最优方法

GitHub: https://github.com/StormstoutLau/factor_pipeline
"""

from .core.decoupler_base import BaseDecoupler, DecouplerConfig
from .core.ar_model import ARDecoupler, AROrderSelector
from .core.dual_neutralizer import DualNeutralizer, CompositeDecoupler
from .core.optimized import (
    OptimizedDualNeutralizer,
    OptimizedARDecoupler,
    OptimizedCompositeDecoupler
)
from .core.unified_decoupler import (
    TemporalDecoupler,
    decouple_ar,
    decouple_difference,
    decouple_hp,
    decouple_auto
)
__version__ = "1.2.0"
__all__ = [
    'BaseDecoupler',
    'DecouplerConfig',
    'ARDecoupler',
    'AROrderSelector',
    'DualNeutralizer',
    'CompositeDecoupler',
    'OptimizedDualNeutralizer',
    'OptimizedARDecoupler',
    'OptimizedCompositeDecoupler',
    'TemporalDecoupler',
    'decouple_ar',
    'decouple_difference',
    'decouple_hp',
    'decouple_auto',
]
