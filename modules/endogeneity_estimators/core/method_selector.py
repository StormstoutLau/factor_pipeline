# -*- coding: utf-8 -*-
"""内生性估计方法选择器 (§5.10.6 场景矩阵).

基于 E3 诊断报告 (final_threat_tau) 和因子数据特征 (持久性、低秩),
按 §5.10.6 场景矩阵推荐合适的内生性缓解估计方法.

方法优先级 (§5.10.5):
  三层正则化 > Profile GMM > IVX > DOLS > PFGMM

选择逻辑 (v1.3 对齐 spec, 顺序: 低秩 → IVX → 低威胁 → 默认):
  1. 低秩 (共性结构主导) → 'profile_gmm' (NNR 吸收共性, §5.10.6-B)
  2. ρ > rho_threshold (持久因子) → 'ivx' (IVX 指数滤波, §5.10.6-C)
  3. τ < low_threat_threshold → 'none' (仅三层正则化, §5.10.6-A)
  4. 默认 → 'profile_gmm' (通用性最强)

注: 文件名 method_selector.py (spec 建议名为 selector.py, 实际实现保留 method_selector.py).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


class EstimationMethodSelector:
    """估计方法选择器 (§5.10.6 场景化方法选择矩阵).

    基于 E3 的诊断结果 (final_threat_tau + S2/S4 诊断特征),
    按 §5.10.6 场景矩阵选择首选估计方法.

    优先级 (§5.10.5): 三层正则化 > Profile GMM > IVX > DOLS > PFGMM

    Args:
        rho_threshold: 持久性阈值, ρ 高于此值时推荐 IVX (默认 0.9)
        low_rank_threshold: 低秩判定阈值, 第一奇异值能量占比高于此值时判定低秩 (默认 0.8)
    """

    def __init__(
        self,
        rho_threshold: float = 0.9,
        low_rank_threshold: float = 0.8,
    ):
        self.rho_threshold = float(rho_threshold)
        self.low_rank_threshold = float(low_rank_threshold)

    def select(
        self,
        endogeneity_report: Dict[str, Any],
        factor_data: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """根据 E3 诊断结果选择估计方法.

        Args:
            endogeneity_report: E3 EndogeneityDiagnosticOrchestrator.
                                get_final_threat_assessment() 返回的 dict,
                                至少含 'final_threat_tau'.
            factor_data: 因子数据 (T, N), 用于持久性和低秩检测. None 时跳过.

        Returns:
            {
                'recommended_method': str,         # 'profile_gmm'/'ivx'/'dols'/'pfgmm'/'none'
                'reason': str,
                'all_methods_ranked': list,        # 按优先级排序 ['profile_gmm','ivx','dols','pfgmm']
                'should_chain_with_regularization': bool,
                'threat_tau': float,
                'rho_persistence': Optional[float] (若 factor_data 提供),
                'is_low_rank': bool (若 factor_data 提供),
            }
        """
        final_tau = float(endogeneity_report.get('final_threat_tau', 0.0))
        final_tau = float(np.clip(final_tau, 0.0, 1.0))

        # 场景判断 (§5.10.6)
        rho = self._estimate_persistence(factor_data)
        is_low_rank = self._check_low_rank(factor_data)

        # 按优先级排序的方法列表 (§5.10.5)
        methods_ranked: List[str] = ['profile_gmm', 'ivx', 'dols', 'pfgmm']

        # ── 场景 B: 低秩 (共性结构主导) → Profile GMM ──
        if is_low_rank:
            return {
                'recommended_method': 'profile_gmm',
                'reason': (
                    f'因子矩阵低秩 (共性结构主导), '
                    f'Profile GMM (NNR+GMM) 吸收共性 (§5.10.6-B), τ={final_tau:.3f}'
                ),
                'all_methods_ranked': methods_ranked,
                'should_chain_with_regularization': final_tau > 0.3,
                'threat_tau': final_tau,
                'rho_persistence': rho,
                'is_low_rank': is_low_rank,
            }

        # ── 场景 C: 持久因子 (接近单位根) → IVX ──
        if rho is not None and rho > self.rho_threshold:
            return {
                'recommended_method': 'ivx',
                'reason': (
                    f'因子持久 (ρ={rho:.3f} > {self.rho_threshold}), '
                    f'IVX 指数滤波 (§5.10.6-C), τ={final_tau:.3f}'
                ),
                'all_methods_ranked': methods_ranked,
                'should_chain_with_regularization': final_tau > 0.3,
                'threat_tau': final_tau,
                'rho_persistence': rho,
                'is_low_rank': is_low_rank,
            }

        # ── 场景 A: 通用低威胁 → 仅三层正则化 ──
        if final_tau < 0.3:
            return {
                'recommended_method': 'none',
                'reason': (
                    f'低威胁 (τ={final_tau:.3f} < 0.3), '
                    f'仅三层正则化即可 (§5.10.6-A)'
                ),
                'all_methods_ranked': methods_ranked,
                'should_chain_with_regularization': True,
                'threat_tau': final_tau,
                'rho_persistence': rho,
                'is_low_rank': is_low_rank,
            }

        # ── 默认: Profile GMM (通用性最强) ──
        return {
            'recommended_method': 'profile_gmm',
            'reason': (
                f'默认推荐 Profile GMM (通用性最强, τ={final_tau:.3f}, '
                f'ρ={rho if rho is None else f"{rho:.3f}"}, low_rank={is_low_rank})'
            ),
            'all_methods_ranked': methods_ranked,
            'should_chain_with_regularization': True,
            'threat_tau': final_tau,
            'rho_persistence': rho,
            'is_low_rank': is_low_rank,
        }

    def _estimate_persistence(self, factor_data) -> Optional[float]:
        """估计因子持久性 ρ (AR1 系数, 截面均值序列的自相关)."""
        if factor_data is None:
            return None
        try:
            x = factor_data.mean(axis=1).dropna().values
            if len(x) < 5:
                return None
            return float(np.corrcoef(x[:-1], x[1:])[0, 1])
        except Exception:
            return None

    def _check_low_rank(self, factor_data) -> bool:
        """检查因子矩阵是否低秩 (第一奇异值能量占比占主导).

        数学 (v1.3 对齐 spec): s[0]² / Σ(s_i²) > low_rank_threshold
        (Frobenius 能量比, 非核范数比 s[0]/Σs)
        """
        if factor_data is None:
            return False
        try:
            X = factor_data.values.astype(float)
            X_centered = X - X.mean(axis=0)
            s = np.linalg.svd(X_centered, compute_uv=False)
            if len(s) == 0:
                return False
            total_energy = float(np.sum(s ** 2))
            if total_energy < 1e-10:
                return False
            # 第一奇异值能量占比 (Frobenius)
            top_ratio = float(s[0] ** 2) / total_energy
            return top_ratio > self.low_rank_threshold
        except Exception:
            return False


# 向后兼容别名 (spec 主类名为 EstimationMethodSelector,
# 早期代码使用 EndogeneityMethodSelector)
EndogeneityMethodSelector = EstimationMethodSelector
