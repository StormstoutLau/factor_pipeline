# -*- coding: utf-8 -*-
"""SpecificationLogger 包 (V3.1.0 E2, §3 P-hacking 防御 L1-L2).

L1 (事前设计): PreRegistration — 在看到数据前承诺模型规格.
L2 (事中记录): SpecificationLogger — append-only 记录所有运行规格.
L3 (事后校正): apply_by_fdr (backtest/multiple_testing.py) — BY-FDR 依赖稳健.

学术依据:
- Nosek et al. (2018). "The preregistration revolution." PNAS 115(11):2600-2606.
- Simonsohn et al. (2020). "Specification Curve Analysis." NHB 4:1208-1214.
- Benjamini & Yekutieli (2001). "The control of the false discovery rate
  in multiple testing under dependency." Annals of Statistics 29(4):1165-1188.
"""
from .spec_log import SpecificationLogger, _make_json_serializable
from .pre_registration import PreRegistration
from .spec_curve import SpecificationCurve

__all__ = [
    'SpecificationLogger',
    'PreRegistration',
    'SpecificationCurve',
    '_make_json_serializable',
]
