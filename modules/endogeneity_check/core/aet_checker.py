# -*- coding: utf-8 -*-
"""Altonji-Elder-Taber (2005) 选择比例检验器.

比较嵌套模型的系数变化, 推断不可观测控制的选择比例.
需要 M0 ⊂ M1 ⊂ M2 三级嵌套控制.

数学公式:
    Selection Ratio = (β* - β1) / (β1 - β0)
其中 β0 = 无控制, β1 = 部分控制, β* = 全控制.
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List
from .base import BaseEndogeneityChecker


class AltonjiElderTaberChecker(BaseEndogeneityChecker):
    """Altonji-Elder-Taber (2005) 选择比例检验器.

    比较嵌套模型的系数变化, 推断不可观测控制的选择比例.
    需要 M0 ⊂ M1 ⊂ M2 三级嵌套控制.
    """

    def __init__(self, threat_threshold: float = 1.0):
        self.threat_threshold = threat_threshold

    def fit(
        self,
        factor_data: pd.DataFrame,
        returns: pd.DataFrame,
        controls: Optional[pd.DataFrame] = None,
        nested_controls: Optional[List[List[int]]] = None,
    ) -> 'AltonjiElderTaberChecker':
        f_flat = factor_data.values.flatten()
        r_flat = returns.values.flatten()
        valid = ~(np.isnan(f_flat) | np.isnan(r_flat))

        # β0: 无控制
        X0 = np.column_stack([np.ones(valid.sum()), f_flat[valid]])
        beta0, *_ = np.linalg.lstsq(X0, r_flat[valid], rcond=None)
        beta0 = beta0[1]

        if nested_controls is None or controls is None:
            self._selection_ratio = float('nan')
            self._threat_tau = 0.5
            return self

        c_flat = controls.values.reshape(-1, controls.shape[-1]) if controls.ndim == 3 else controls.values
        m1_cols = nested_controls[1] if len(nested_controls) > 1 else list(range(c_flat.shape[1]))
        X1 = np.column_stack([
            np.ones(valid.sum()),
            f_flat[valid],
            c_flat[:valid.sum(), m1_cols] if len(m1_cols) > 0 else np.empty((valid.sum(), 0)),
        ])
        beta1, *_ = np.linalg.lstsq(X1, r_flat[valid], rcond=None)
        beta1 = beta1[1]

        m2_cols = nested_controls[2] if len(nested_controls) > 2 else list(range(c_flat.shape[1]))
        X2 = np.column_stack([
            np.ones(valid.sum()),
            f_flat[valid],
            c_flat[:valid.sum(), m2_cols] if len(m2_cols) > 0 else np.empty((valid.sum(), 0)),
        ])
        beta_star, *_ = np.linalg.lstsq(X2, r_flat[valid], rcond=None)
        beta_star = beta_star[1]

        denom = beta1 - beta0
        if abs(denom) < 1e-10:
            self._selection_ratio = float('inf')
            self._threat_tau = 0.1
        else:
            self._selection_ratio = (beta_star - beta1) / denom
            abs_sr = abs(self._selection_ratio)
            # |SR| 小 → 选择比例小 → 稳健 (低威胁); |SR| 大 → 脆弱 (高威胁)
            # threat_tau 随 |SR| 单调递增: |SR|=0 → 0, |SR|≥1 → 1
            self._threat_tau = float(min(1.0, abs_sr))

        self._beta0 = float(beta0)
        self._beta1 = float(beta1)
        self._beta_star = float(beta_star)
        return self

    def get_diagnostics(self) -> Dict[str, Any]:
        sr = getattr(self, '_selection_ratio', float('nan'))
        return {
            'selection_ratio': sr,
            'beta0_uncontrolled': getattr(self, '_beta0', float('nan')),
            'beta1_partial_control': getattr(self, '_beta1', float('nan')),
            'beta_star_full_control': getattr(self, '_beta_star', float('nan')),
            'threat_tau': getattr(self, '_threat_tau', 0.5),
            'interpretation': (
                f'AET selection ratio={sr:.3f}' if np.isfinite(sr) else 'AET selection ratio=inf (稳健)'
            ),
        }

    def get_threat_level(self) -> float:
        return getattr(self, '_threat_tau', 0.5)
