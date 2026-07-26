# -*- coding: utf-8 -*-
"""S2/S3/S4 Oster (2019) δ 稳健性界检验器.

测量需要多大的不可观测混淆才能颠覆因子效应结论.
不声称解决内生性, 只量化内生性威胁.

Oster (2019, JBES, Proposition 2, Eq. 5):
δ = β̃(R̃ − Ṙ) / [(β̇ − β̃)(R_max − R̃)]

where:
  β̃ = beta_controlled (with controls)
  β̇ = beta_uncontrolled (without controls)
  R̃ = R²_controlled
  Ṙ = R²_uncontrolled
  R_max = min(1.3 × R̃, 1.0) (Oster 2019 建议)
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from .base import BaseEndogeneityChecker


class OsterDeltaChecker(BaseEndogeneityChecker):
    """Oster (2019) δ 稳健性界检验器.

    测量需要多大的不可观测混淆才能颠覆因子效应结论.
    不声称解决内生性, 只量化内生性威胁.

    Reference: Oster (2019), "Unobservable Selection and Coefficient
    Stability: Theory and Evidence", Journal of Business & Economic
    Statistics, 37(2), 187-204.
    """

    def __init__(
        self,
        r_max_multiplier: float = 1.3,
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

        Oster (2019, JBES, Proposition 2, Eq. 5):
        δ = β̃(R̃ − Ṙ) / [(β̇ − β̃)(R_max − R̃)]

        Args:
            factor_data: 因子值 (T, N)
            returns: 未来收益 (T, N)
            controls: 可观测控制变量。支持:
                - (T, N, K) 3D array → 自动展平为 (T*N, K)
                - (T, N*K) 2D array → 自动 reshape 为 (T*N, K)
                - (T*N, K) 2D array → 直接使用
        """
        f_flat = factor_data.values.flatten()
        r_flat = returns.values.flatten()
        valid = ~(np.isnan(f_flat) | np.isnan(r_flat))

        f_valid = f_flat[valid]
        r_valid = r_flat[valid]
        T_valid = len(f_valid)

        # ---- 无控制回归: β̇ (beta_uncontrolled) ----
        X_uncontrolled = np.column_stack([np.ones(T_valid), f_valid])
        beta_unc, _, _, _ = np.linalg.lstsq(X_uncontrolled, r_valid, rcond=None)
        alpha_uncontrolled = beta_unc[0]
        beta_uncontrolled = beta_unc[1]

        # Ṙ = R²_uncontrolled (含截距预测)
        r_pred_unc = alpha_uncontrolled + beta_uncontrolled * f_valid
        ss_res_unc = np.sum((r_valid - r_pred_unc) ** 2)
        ss_tot = np.sum((r_valid - np.mean(r_valid)) ** 2)
        r_squared_uncontrolled = 1 - ss_res_unc / max(ss_tot, 1e-10)

        # ---- 含控制回归: β̃ (beta_controlled) ----
        if controls is not None:
            c_valid = self._align_controls(controls, factor_data.shape, valid)
            if c_valid.shape[0] != T_valid:
                raise ValueError(
                    f"Controls row count {c_valid.shape[0]} != "
                    f"valid observations {T_valid}"
                )

            X_controlled = np.column_stack([
                np.ones(T_valid),
                f_valid,
                c_valid,
            ])
            beta_full, _, _, _ = np.linalg.lstsq(X_controlled, r_valid, rcond=None)
            beta_controlled = beta_full[1]

            # R̃ = R²_controlled
            r_pred_c = X_controlled @ beta_full
            ss_res_c = np.sum((r_valid - r_pred_c) ** 2)
            r_squared_controlled = 1 - ss_res_c / max(ss_tot, 1e-10)
        else:
            beta_controlled = beta_uncontrolled
            r_squared_controlled = r_squared_uncontrolled

        # ---- R_max ----
        r_observed = self.r_observed if self.r_observed is not None else r_squared_controlled
        r_max = min(1.0, self.r_max_multiplier * r_observed)

        # ---- Oster δ: Oster (2019) Proposition 2, Eq. 5 ----
        # δ = β̃(R̃ − Ṙ) / [(β̇ − β̃)(R_max − R̃)]
        if r_squared_controlled <= r_squared_uncontrolled + 1e-10:
            # R̃ ≤ Ṙ: 控制变量不增加 R² → 无遗漏变量偏误证据
            delta = 0.0
            threat_tau = 0.0
        else:
            numerator = beta_controlled * (r_squared_controlled - r_squared_uncontrolled)
            denom = (beta_uncontrolled - beta_controlled) * (r_max - r_squared_controlled)
            if abs(denom) < 1e-10:
                delta = float('inf') if beta_controlled > 0 else float('-inf')
                threat_tau = 0.0
            else:
                delta = numerator / denom
                abs_delta = abs(delta)
                if abs_delta > 1:
                    threat_tau = 0.1  # 稳健
                elif abs_delta < self.threat_threshold:
                    threat_tau = 0.9  # 脆弱
                else:
                    threat_tau = 1.0 - abs_delta  # 灰色地带线性映射

        self._delta = float(delta) if np.isfinite(delta) else float('inf')
        self._r_max = float(r_max)
        self._r_observed = float(r_observed)
        self._r_squared_uncontrolled = float(r_squared_uncontrolled)
        self._r_squared_controlled = float(r_squared_controlled)
        self._beta_uncontrolled = float(beta_uncontrolled)
        self._beta_controlled = float(beta_controlled)
        self._threat_tau = float(threat_tau)
        return self

    @staticmethod
    def _align_controls(
        controls: pd.DataFrame,
        factor_shape: tuple,
        valid: np.ndarray,
    ) -> np.ndarray:
        """Align controls to (T_valid, K) 2D array matching flattened valid obs.

        Handles three input formats:
        - (T, N, K) 3D → reshape to (T*N, K), apply valid mask
        - (T, N*K) 2D → reshape to (T*N, K), apply valid mask
        - (T*N, K) 2D → apply valid mask directly
        """
        T, N = factor_shape
        c_arr = controls.values if hasattr(controls, 'values') else np.asarray(controls)

        if c_arr.ndim == 3:
            # (T, N, K) → (T*N, K)
            K = c_arr.shape[2]
            c_flat = c_arr.reshape(T * N, K)
        elif c_arr.shape[0] == T * N:
            # (T*N, K) — already flat
            c_flat = c_arr
        elif c_arr.shape[0] == T:
            # (T, N*K) → (T*N, K)
            K = c_arr.shape[1] // N
            c_flat = c_arr.reshape(T * N, K)
        else:
            raise ValueError(
                f"Cannot align controls shape {c_arr.shape} "
                f"with factor shape {(T, N)}"
            )

        return c_flat[valid]

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            'delta': self._delta,
            'r_max': self._r_max,
            'r_observed': self._r_observed,
            'r_squared_uncontrolled': self._r_squared_uncontrolled,
            'r_squared_controlled': self._r_squared_controlled,
            'beta_uncontrolled': self._beta_uncontrolled,
            'beta_controlled': self._beta_controlled,
            'threat_tau': self._threat_tau,
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