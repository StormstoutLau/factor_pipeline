# -*- coding: utf-8 -*-
"""V3.1.0 E5 (§5) — 三层决策正则化.

硬依赖 E3: EndogeneityRegularizer 接收 E3 的 final_threat_assessment,
基于 final_threat_tau ∈ [0,1] 协调三层正则化:
  L1 预处理层: 调整 DualNeutralizer 中性化强度
  L2 检验层:   调整 factor_significance 显著性阈值 α
  L3 组合层:   调整 optimizer 因子权重惩罚

向后兼容: 默认 enable=False/opt-in, 不影响 v3.0.0 行为.
"""
from .regularizer import EndogeneityRegularizer

__all__ = ['EndogeneityRegularizer']
