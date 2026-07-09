# -*- coding: utf-8 -*-
"""
Factor Decoupler Diagnostics - 隐藏效应诊断子包 (V3.1.0 E1, §2)

提供时序解耦的 post-hoc 隐藏效应诊断 Mixin, 不侵入 fit/transform 接口.
"""

from .hidden_effect import HiddenEffectDiagnosticMixin

__all__ = ['HiddenEffectDiagnosticMixin']
