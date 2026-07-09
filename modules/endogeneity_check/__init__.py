# -*- coding: utf-8 -*-
"""v3.1.0 E3 (§1): 内生性检验 S1-S4 — 独立新模块.

四阶段诊断:
  S1 插补前 — 缺失机制 (MCAR/MAR/MNAR), 输出分类标签 + mnar_risk_prior
  S2 插补后/中性化前 — 原始因子内生性基线, 输出连续 τ ∈ [0,1]
  S3 中性化后/解耦前 — 截面内生性残留 (可选), 输出连续 τ
  S4 解耦后 — 增量+时序内生性残留, 输出最终 τ_i

四方法:
  - Oster δ (2019) — R_max = min(1, 1.3 × R̃) (v1.3, 非 2.75)
  - AET (Altonji-Elder-Taber 2005) — 选择比例检验
  - IFE (Bai 2009) — lambda_i' * F_t 标准记号
  - Lewbel (2012) — Z_internal = (Z - Z̄) × ê²

S1 → S2 上下文衔接 (逻辑衔接, 非数值乘法/非数值差分);
S3-S2, S4-S3, S4-S2 是数值差分 (连续 τ 之间).
"""
from .core.base import BaseEndogeneityChecker
from .core.missingness_checker import MissingnessMechanismChecker
from .core.oster_delta import OsterDeltaChecker
from .core.aet_checker import AltonjiElderTaberChecker
from .core.ife_checker import InteractiveFEChecker
from .core.lewbel_iv import LewbelInternalIVChecker
from .core.threat_assessor import EndogeneityThreatAssessor
from .core.diagnostic_orchestrator import EndogeneityDiagnosticOrchestrator

__all__ = [
    'BaseEndogeneityChecker',
    'MissingnessMechanismChecker',
    'OsterDeltaChecker',
    'AltonjiElderTaberChecker',
    'InteractiveFEChecker',
    'LewbelInternalIVChecker',
    'EndogeneityThreatAssessor',
    'EndogeneityDiagnosticOrchestrator',
]
