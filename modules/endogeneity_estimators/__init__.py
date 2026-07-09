# -*- coding: utf-8 -*-
"""V3.1.0 E6 (§5.10) — 估计层内生性缓解方法.

四种估计器 + 方法选择器, 全部 opt-in, 默认关闭.
与 E5 互补: E6 先估计, E5 再正则化残留威胁.

v1.3 术语严格:
- Profile GMM (Hong-Su-Jiang 2022, 正式术语; NNR+GMM 为别名)
- IVX 指数衰减滤波 (非分数差分)
- Regularized DOLS (Stock-Watson 1993)
- PFGMM (Ghosh-Thoresen 2019, 处理 error-covariate 内生, 非弱 IV)
"""
from .core.base import BaseEndogeneityEstimator
from .core.profile_gmm import ProfileGMMEstimator
from .core.ivx import IVXEstimator
from .core.regularized_dols import RegularizedDOLSEstimator
from .core.pfgmm import PFGMMEstimator
from .core.method_selector import (
    EstimationMethodSelector,
    EndogeneityMethodSelector,  # 向后兼容别名
)

__all__ = [
    'BaseEndogeneityEstimator',
    'ProfileGMMEstimator',
    'IVXEstimator',
    'RegularizedDOLSEstimator',
    'PFGMMEstimator',
    'EstimationMethodSelector',
    'EndogeneityMethodSelector',  # 向后兼容
]
