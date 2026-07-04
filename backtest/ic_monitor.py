"""IC 变化监控 (Layer 3)

正交化前后 IC 对比, 监控正交化是否损害因子预测力

指标:
- IC_before: 正交化前因子 IC (Spearman 秩相关)
- IC_after: 正交化后因子 IC
- IC_change_ratio: (IC_after - IC_before) / |IC_before|
- 阈值: |IC_change_ratio| > 0.8 → 正交化损害预测力

架构层: Layer 3 (有监督, 需 Y)
"""
from __future__ import annotations

from typing import Dict

import numpy as np
from scipy.stats import spearmanr


class ICChangeMonitor:
    """IC 变化监控

    用途: 正交化后验证因子预测力是否损失
    - IC_change_ratio 接近 0: 正交化未损害预测力
    - |IC_change_ratio| > 0.8: 正交化严重损害预测力 (is_degraded=True)
    """

    # IC 下降阈值 (|ratio| > 此值时 is_degraded=True)
    DEGRADATION_THRESHOLD = 0.8

    @staticmethod
    def compute_ic(
        factor: np.ndarray,
        fwd_returns: np.ndarray,
    ) -> float:
        """计算单因子 IC (Spearman 秩相关)

        Args:
            factor: (N,) 因子值
            fwd_returns: (N,) 前向收益

        Returns: IC 标量 [-1, 1]
        """
        # 移除 NaN (Spearman 不接受 NaN)
        mask = ~(np.isnan(factor) | np.isnan(fwd_returns))
        f_clean = factor[mask]
        r_clean = fwd_returns[mask]
        if len(f_clean) < 3:
            return 0.0
        rho, _ = spearmanr(f_clean, r_clean)
        return float(rho)

    @classmethod
    def compare_ic(
        cls,
        factor_before: np.ndarray,
        factor_after: np.ndarray,
        fwd_returns: np.ndarray,
    ) -> Dict[str, float]:
        """对比正交化前后 IC

        Args:
            factor_before: (N,) 正交化前因子值
            factor_after: (N,) 正交化后因子值
            fwd_returns: (N,) 前向收益

        Returns:
            {
                'ic_before': float,
                'ic_after': float,
                'ic_change': float,
                'ic_change_ratio': float,
                'is_degraded': bool,  # |ratio| > 0.8
            }
        """
        ic_before = cls.compute_ic(factor_before, fwd_returns)
        ic_after = cls.compute_ic(factor_after, fwd_returns)
        ic_change = ic_after - ic_before
        if abs(ic_before) > 1e-12:
            ic_change_ratio = ic_change / abs(ic_before)
        else:
            # IC_before 接近 0 时, 比率无意义
            ic_change_ratio = 0.0
        return {
            'ic_before': ic_before,
            'ic_after': ic_after,
            'ic_change': ic_change,
            'ic_change_ratio': ic_change_ratio,
            'is_degraded': bool(abs(ic_change_ratio) > cls.DEGRADATION_THRESHOLD),
        }
