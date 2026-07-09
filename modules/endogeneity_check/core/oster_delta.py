# -*- coding: utf-8 -*-
"""S2/S3/S4 Oster (2019) δ 稳健性界检验器.

测量需要多大的不可观测混淆才能颠覆因子效应结论.
不声称解决内生性, 只量化内生性威胁.

注 (v1.3 修正): Oster (2019) 方法的标准称呼为 "Oster's δ" / "Oster bounds" /
"coefficient stability analysis" (Stata psacalc 命令).
本文档统一使用 "Oster δ" 术语 (非 "ITCV").
R_max = min(1, 1.3 × R̃) (v1.3 修正: 1.3 倍数, 非 2.75).
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from .base import BaseEndogeneityChecker


class OsterDeltaChecker(BaseEndogeneityChecker):
    """Oster (2019) δ 稳健性界检验器.

    测量需要多大的不可观测混淆才能颠覆因子效应结论.
    不声称解决内生性, 只量化内生性威胁.

    注 (v1.3 修正): Oster (2019) 方法的标准称呼为 "Oster's δ" / "Oster bounds" /
    "coefficient stability analysis" (Stata psacalc 命令).
    本文档统一使用 "Oster δ" 术语 (非 "ITCV").
    R_max = min(1, 1.3 × R̃) (v1.3 修正: 1.3 倍数, 非 2.75).
    """

    def __init__(
        self,
        r_max_multiplier: float = 1.3,   # v1.3: 1.3 (非 2.75)
        r_observed: Optional[float] = None,
        threat_threshold: float = 0.1,
    ):
        self.r_max_multiplier = r_max_multiplier
        self.r_observed = r_observed
        self.threat_threshold = threat_threshold

    def fit(
        self,
        factor_data: pd.DataFrame,
        returns: pd.DataFrame,
        controls: Optional[pd.DataFrame] = None,
    ) -> 'OsterDeltaChecker':
        """估计 Oster δ 稳健性界.

        Args:
            factor_data: 因子值 (T, N)
            returns: 未来收益 (T, N)
            controls: 可观测控制变量 (T, N, K), 可选
        """
        f_flat = factor_data.values.flatten()
        r_flat = returns.values.flatten()
        valid = ~(np.isnan(f_flat) | np.isnan(r_flat))

        # 无控制回归: β̂_uncontrolled
        beta_uncontrolled, _, _, _ = np.linalg.lstsq(
            np.column_stack([np.ones(valid.sum()), f_flat[valid]]),
            r_flat[valid], rcond=None
        )
        beta_uncontrolled = beta_uncontrolled[1]

        r_pred = beta_uncontrolled * f_flat[valid]
        ss_res = np.sum((r_flat[valid] - r_pred) ** 2)
        ss_tot = np.sum((r_flat[valid] - np.mean(r_flat[valid])) ** 2)
        r_squared_uncontrolled = 1 - ss_res / max(ss_tot, 1e-10)

        # 含控制回归: β̂_controlled (β̃)
        if controls is not None:
            c_flat = controls.values.reshape(-1, controls.shape[-1]) if controls.ndim == 3 else controls.values
            c_valid = c_flat[valid] if c_flat.shape[0] == f_flat.shape[0] else c_flat
            X_controlled = np.column_stack([
                np.ones(valid.sum()),
                f_flat[valid],
                c_valid[:valid.sum()] if c_valid.shape[0] >= valid.sum() else c_valid,
            ])
            beta_full, _, _, _ = np.linalg.lstsq(X_controlled, r_flat[valid], rcond=None)
            beta_controlled = beta_full[1]
            r_pred_c = X_controlled @ beta_full
            ss_res_c = np.sum((r_flat[valid] - r_pred_c) ** 2)
            r_squared_controlled = 1 - ss_res_c / max(ss_tot, 1e-10)
        else:
            beta_controlled = beta_uncontrolled
            r_squared_controlled = r_squared_uncontrolled

        # R_max = min(1, 1.3 × R̃) (v1.3 修正: 1.3 倍数, 非 2.75)
        r_observed = self.r_observed if self.r_observed is not None else r_squared_controlled
        r_max = min(1.0, self.r_max_multiplier * r_observed)

        # Oster δ: 设 β* = 0 (检验"混淆能否将效应降至零")
        beta_star = 0.0
        denom = beta_controlled - beta_uncontrolled
        if abs(denom) < 1e-10:
            delta = float('inf')
            threat_tau = 0.0
        else:
            delta = (beta_controlled - beta_star) / denom
            abs_delta = abs(delta)
            if abs_delta > 1:
                threat_tau = 0.1  # 稳健
            elif abs_delta < self.threat_threshold:
                threat_tau = 0.9  # 脆弱
            else:
                threat_tau = 1.0 - abs_delta  # 灰色地带线性映射

        self._delta = float(delta) if delta != float('inf') else float('inf')
        self._r_max = float(r_max)
        self._r_observed = float(r_observed)
        self._beta_uncontrolled = float(beta_uncontrolled)
        self._beta_controlled = float(beta_controlled)
        self._threat_tau = float(threat_tau)
        return self

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            'delta': self._delta,
            'r_max': self._r_max,                    # min(1, 1.3 × R̃)
            'r_observed': self._r_observed,
            'beta_uncontrolled': self._beta_uncontrolled,
            'beta_controlled': self._beta_controlled,
            'threat_tau': self._threat_tau,          # τ ∈ [0, 1]
            'threat_level': (
                'low' if abs(self._delta) > 1
                else 'high' if abs(self._delta) < self.threat_threshold
                else 'medium'
            ),
            'interpretation': (
                f'Oster δ={self._delta:.3f}, R_max=min(1, 1.3×{self._r_observed:.3f})={self._r_max:.3f}. '
                f'需要 |δ|>1 的不可观测混淆才能颠覆结论.'
            ),
        }

    def get_threat_level(self) -> float:
        return self._threat_tau
