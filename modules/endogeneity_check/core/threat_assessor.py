# -*- coding: utf-8 -*-
"""内生性威胁评估器 — 跨层正则化的上游输入 (§5 依赖此类).

基于 Oster δ / AET / IFE / Lewbel 四方法综合评估因子内生性威胁等级,
输出 τ ∈ [0, 1] 供 E5 三层正则化使用.

融合策略: 加权平均 (Oster δ 权重最高, AET 次之, IFE/Lewbel 按需).

S1 → S2 上下文衔接 (v1.3 修正: 逻辑衔接, 非数值乘法/非数值差分):
S1 的缺失机制诊断结果 (MCAR/MAR/MNAR) 逻辑指导 S2 的正则化策略,
而非对 base_tau 做数值乘法. final_tau 保持为 base_tau 本身.
"""
import numpy as np
from typing import Dict, Any, Optional


class EndogeneityThreatAssessor:
    """内生性威胁评估器 — 跨层正则化的上游输入 (§5 依赖此类).

    基于 Oster δ / AET / IFE / Lewbel 四方法综合评估因子内生性威胁等级,
    输出 τ ∈ [0, 1] 供 E5 三层正则化使用.

    融合策略: 加权平均 (Oster δ 权重最高, AET 次之, IFE/Lewbel 按需).
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        final_threshold: float = 0.3,
    ):
        self.weights = weights or {
            'oster_delta': 0.4,
            'aet': 0.3,
            'ife': 0.2,
            'lewbel': 0.1,
        }
        self.final_threshold = final_threshold

    def assess(
        self,
        checker_results: Dict[str, Dict[str, Any]],
        s1_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, float]:
        """综合评估最终内生性威胁等级 τ_i.

        Args:
            checker_results: 各检验器的 get_diagnostics() 结果
                            {'oster_delta': {...}, 'aet': {...}, ...}
            s1_context: S1 缺失机制诊断报告 (上下文衔接, 非数值乘法).
                        含 'missingness_mechanism' (MCAR/MAR/MNAR) 与
                        'mnar_risk_prior' 等字段. S1 的机制标签**逻辑指导**
                        S2 的正则化推荐策略 (非对 τ 做数值乘法).

        Returns:
            {
                'final_threat_tau': float,    # ∈ [0, 1], 供 E5 使用
                'component_taus': Dict[str, float],
                's1_mechanism': str,          # S1 上下文 (MCAR/MAR/MNAR/unknown)
                's1_context_note': str,       # S1→S2 逻辑衔接说明
                'recommended_regularization': str,  # 'none' / 'mild' / 'strong'
            }
        """
        component_taus = {}
        weighted_sum = 0.0
        weight_total = 0.0

        for method, result in checker_results.items():
            tau = result.get('threat_tau', 0.5)
            weight = self.weights.get(method, 0.0)
            component_taus[method] = float(tau)
            weighted_sum += tau * weight
            weight_total += weight

        base_tau = weighted_sum / max(weight_total, 1e-10)

        # S1 → S2 上下文衔接 (v1.3 修正: 逻辑衔接, 非数值乘法/非数值差分).
        # S1 的缺失机制诊断结果 (MCAR/MAR/MNAR) 逻辑指导 S2 的正则化策略,
        # 而非对 base_tau 做数值乘法. final_tau 保持为 base_tau 本身.
        final_tau = float(np.clip(base_tau, 0.0, 1.0))

        s1_mechanism = (s1_context or {}).get('missingness_mechanism', 'unknown')
        if final_tau < 0.3:
            recommendation = 'none'
        elif final_tau < 0.7:
            recommendation = 'mild'
        else:
            recommendation = 'strong'

        # S1 机制标签逻辑指导推荐策略 (离散策略选择, 非 τ 数值调整):
        # - MCAR: 缺失随机, S2 baseline 可信, 不调整推荐
        # - MAR:  缺失依赖可观测变量, S2 baseline 取决于控制变量充分性, 提示但不升级
        # - MNAR: 缺失依赖不可观测, S2 baseline 存在选择偏差风险, 推荐上调一级
        if s1_mechanism == 'MNAR':
            if recommendation == 'none':
                recommendation = 'mild'
            elif recommendation == 'mild':
                recommendation = 'strong'
            s1_context_note = (
                'MNAR: 缺失依赖不可观测, S2 baseline τ 存在选择偏差风险, '
                '推荐正则化策略上调一级 (逻辑衔接, 非 τ 数值乘法)'
            )
        elif s1_mechanism == 'MAR':
            s1_context_note = (
                'MAR: 缺失依赖可观测变量, S2 baseline τ 的可信度取决于控制变量充分性'
            )
        elif s1_mechanism == 'MCAR':
            s1_context_note = 'MCAR: 缺失随机, S2 baseline τ 可信'
        else:
            s1_context_note = 'S1 机制未知, S2 baseline τ 无上下文调整'

        return {
            'final_threat_tau': final_tau,
            'component_taus': component_taus,
            's1_mechanism': s1_mechanism,
            's1_context_note': s1_context_note,
            'recommended_regularization': recommendation,
        }
