# -*- coding: utf-8 -*-
"""SpecificationCurve — 规格曲线分析 (V3.1.0 E2, §3).

Specification curve (Simonsohn et al. 2020) 将所有合理规格的结果汇总,
展示效应在不同规格下的稳健性. 本类提供独立的曲线计算接口,
与 SpecificationLogger.get_specification_curve 互补.

学术依据:
- Simonsohn, U., Simmons, J. P., & Nelson, L. D. (2020). "Specification
  Curve Analysis." Nature Human Behaviour 4:1208-1214.
"""
from typing import Dict, Any, List, Optional
import numpy as np


class SpecificationCurve:
    """规格曲线分析器 — 汇总所有规格结果的稳健性.

    接收一组记录 (来自 SpecificationLogger), 计算:
    - median_effect: 中位效应
    - consistency: 效应方向一致性 (high / medium / low)
    - specifications: 规格列表
    """

    def __init__(self, records: Optional[List[Dict[str, Any]]] = None):
        self.records = records or []

    def analyze(self) -> Dict[str, Any]:
        """计算规格曲线分析结果."""
        if not self.records:
            return {
                'specifications': [],
                'results': [],
                'p_values': [],
                'median_effect': float('nan'),
                'consistency': 'undefined',
            }

        results = [r.get('result', {}).get('ic', float('nan')) for r in self.records]
        p_values = [r.get('result', {}).get('p_value', float('nan')) for r in self.records]

        valid_results = [r for r in results if not (isinstance(r, float) and np.isnan(r))]
        if not valid_results:
            consistency = 'undefined'
        else:
            pos_ratio = sum(1 for r in valid_results if r > 0) / len(valid_results)
            consistency = 'high' if pos_ratio > 0.8 or pos_ratio < 0.2 else (
                'medium' if pos_ratio > 0.6 or pos_ratio < 0.4 else 'low'
            )

        return {
            'specifications': self.records,
            'results': results,
            'p_values': p_values,
            'median_effect': float(np.nanmedian(results)) if results else float('nan'),
            'consistency': consistency,
        }
