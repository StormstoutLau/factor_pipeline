# -*- coding: utf-8 -*-
"""内生性正则化协调器 (§5 三层决策, 硬依赖 E3).

基于 E3 的 final_threat_tau, 协调三层正则化:
  L1 预处理层: 调整 DualNeutralizer 中性化强度
  L2 检验层:   调整 factor_significance 显著性阈值 α
  L3 组合层:   调整 optimizer 因子权重惩罚

关键: 三层都依赖 final_threat_tau, E3 未实施时此类无法独立运行
(报错或降级, 见 E5-T14).
"""
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class EndogeneityRegularizer:
    """内生性正则化协调器 (§5 三层决策, 硬依赖 E3).

    基于 E3 的 final_threat_tau, 协调三层正则化:
      L1 预处理层: 调整 DualNeutralizer 中性化强度
      L2 检验层:   调整 factor_significance 显著性阈值 α
      L3 组合层:   调整 optimizer 因子权重惩罚

    关键: 三层都依赖 final_threat_tau, E3 未实施时此类无法运行.

    Args:
        threat_assessment: E3 EndogeneityDiagnosticOrchestrator.get_final_threat_assessment()
                          返回的 dict, 含 'final_threat_tau'. None 表示 E3 未运行.
        skip_stage2_threshold: L1 跳过 Stage 2 的 τ 阈值 (默认 0.3)
        extra_check_threshold: L1 额外 β' 检查的 τ 阈值 (默认 0.7)
        reg_strength_rho: L3 组合层惩罚强度 ρ (默认 0.3)
        reg_gamma: L2 检验层 α 调整强度 γ (默认 0.5)
        alpha_base: 基础显著性水平 (默认 0.05)
    """

    def __init__(
        self,
        threat_assessment: Optional[Dict[str, Any]] = None,
        skip_stage2_threshold: float = 0.3,
        extra_check_threshold: float = 0.7,
        reg_strength_rho: float = 0.3,
        reg_gamma: float = 0.5,
        alpha_base: float = 0.05,
    ):
        self.threat_assessment = threat_assessment
        self.skip_stage2_threshold = skip_stage2_threshold
        self.extra_check_threshold = extra_check_threshold
        self.reg_strength_rho = reg_strength_rho
        self.reg_gamma = reg_gamma
        self.alpha_base = alpha_base

    def _resolve_tau(self, tau: Optional[float]) -> float:
        """解析 τ: 优先用参数 tau, 否则从 threat_assessment 提取.

        两者都为 None 时报错 (E5-T14: 硬依赖 E3).
        """
        if tau is not None:
            return float(tau)
        if self.threat_assessment is not None:
            return float(self.threat_assessment.get('final_threat_tau', 0.0))
        # E3 未运行 (threat_assessment=None) 且未提供 tau → 报错
        raise ValueError(
            "E5 硬依赖 E3: threat_assessment=None 且未提供 tau 参数. "
            "请先运行 E3 EndogeneityDiagnosticOrchestrator.get_final_threat_assessment(), "
            "或直接传入 tau 值."
        )

    def apply_l1_neutralizer_config(
        self,
        tau: Optional[float] = None,
    ) -> Dict[str, Any]:
        """L1 预处理层正则化: 根据 τ 调整中性化强度.

        - τ < 0.3 (低威胁): 跳过 Stage 2 (轻量路径, 避免 AR 信息损失)
        - 0.3 ≤ τ < 0.7 (中威胁): 标准三重中性化
        - τ ≥ 0.7 (高威胁): 标准三重中性化 + 额外 β' 检查

        Args:
            tau: 内生性威胁等级 τ ∈ [0, 1]. None 时从 threat_assessment 提取.

        Returns:
            {
                'threat_level': 'low'/'medium'/'high',
                'skip_stage2': bool,
                'extra_beta_check': bool,
                'tau': float,
            }
        """
        threat_tau = self._resolve_tau(tau)

        if threat_tau < self.skip_stage2_threshold:
            level = 'low'
            skip = True
            extra = False
        elif threat_tau >= self.extra_check_threshold:
            level = 'high'
            skip = False
            extra = True
        else:
            level = 'medium'
            skip = False
            extra = False

        logger.info(
            f'L1 正则化: τ={threat_tau:.2f}, level={level}, '
            f'skip_stage2={skip}, extra_beta_check={extra}'
        )
        return {
            'threat_level': level,
            'skip_stage2': skip,
            'extra_beta_check': extra,
            'tau': float(threat_tau),
        }

    def apply_l2_significance_config(
        self,
        tau: Optional[float] = None,
    ) -> Dict[str, Any]:
        """L2 检验层正则化: 根据 τ 调整显著性阈值 α.

        数学: α_i = α_base × (1 - γ × τ_i)
        - τ=0 (无内生性): α_i = 0.05 (标准)
        - τ=0.5 (中内生性): α_i = 0.0375 (略严格)
        - τ=1 (高内生性): α_i = 0.025 (严格)

        Args:
            tau: 内生性威胁等级 τ ∈ [0, 1]. None 时从 threat_assessment 提取.

        Returns:
            {
                'alpha_adjusted': float,
                'alpha_base': float,
                'gamma': float,
                'tau': float,
            }
        """
        threat_tau = self._resolve_tau(tau)
        alpha_adjusted = self.alpha_base * (1.0 - self.reg_gamma * threat_tau)
        alpha_adjusted = float(max(alpha_adjusted, 0.001))  # 下限保护

        logger.info(
            f'L2 正则化: τ={threat_tau:.2f}, α={alpha_adjusted:.4f} '
            f'(base={self.alpha_base}, γ={self.reg_gamma})'
        )
        return {
            'alpha_adjusted': alpha_adjusted,
            'alpha_base': self.alpha_base,
            'gamma': float(self.reg_gamma),
            'tau': float(threat_tau),
        }

    def apply_l3_optimizer_config(
        self,
        tau: Optional[float] = None,
        w_raw: float = 1.0,
    ) -> Dict[str, Any]:
        """L3 组合层正则化: 根据 τ 调整因子权重.

        数学: w_final = w_raw × (1 - ρ × τ)
        - τ=0 (无内生性): w_final = w_raw (无惩罚)
        - τ=0.5 (中内生性): w_final = 0.85 × w_raw (15% 惩罚, ρ=0.3)
        - τ=1 (高内生性): w_final = 0.7 × w_raw (30% 惩罚, ρ=0.3)

        Args:
            tau: 内生性威胁等级 τ ∈ [0, 1]. None 时从 threat_assessment 提取.
            w_raw: 原始因子权重.

        Returns:
            {
                'w_final': float,
                'w_raw': float,
                'penalty': float,
                'rho': float,
                'tau': float,
            }
        """
        threat_tau = self._resolve_tau(tau)
        penalty = self.reg_strength_rho * threat_tau
        w_final = float(w_raw) * (1.0 - penalty)

        logger.info(
            f'L3 正则化: τ={threat_tau:.2f}, w_raw={w_raw:.4f}, '
            f'w_final={w_final:.4f} (ρ={self.reg_strength_rho})'
        )
        return {
            'w_final': float(w_final),
            'w_raw': float(w_raw),
            'penalty': float(penalty),
            'rho': float(self.reg_strength_rho),
            'tau': float(threat_tau),
        }

    def _extra_beta_check(self, dual_neutralizer) -> Dict[str, Any]:
        """高威胁因子的额外 β' 显著性检查 (L1).

        当 τ ≥ extra_check_threshold 时调用, 检查 DualNeutralizer 的
        Stage 2 系数 β' 是否显著, 防止高内生性因子穿透中性化.

        Args:
            dual_neutralizer: DualNeutralizer 或 CompositeDecoupler 实例

        Returns:
            {
                'checked': bool,           # 是否实际执行了检查
                'coefficients': Optional[dict],  # Stage 2 系数 (若有)
                'summary': Optional[dict],       # 中性化摘要 (若有)
            }
        """
        result: Dict[str, Any] = {
            'checked': False,
            'coefficients': None,
            'summary': None,
        }

        if hasattr(dual_neutralizer, '_second_stage_coefficients'):
            coeffs = getattr(dual_neutralizer, '_second_stage_coefficients')
            result['coefficients'] = (
                coeffs if isinstance(coeffs, dict) else {'value': float(coeffs)}
            )
            result['checked'] = True
            logger.info(f"额外 β' 检查: 系数={coeffs}")

        if hasattr(dual_neutralizer, 'get_neutralization_summary'):
            try:
                summary = dual_neutralizer.get_neutralization_summary()
                result['summary'] = summary
                result['checked'] = True
                logger.info(f"中性化摘要: {summary}")
            except Exception as e:
                logger.warning(f"get_neutralization_summary 调用失败: {e}")

        return result
