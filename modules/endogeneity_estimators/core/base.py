# -*- coding: utf-8 -*-
"""E6 估计器抽象基类 (§5.10).

所有内生性缓解估计器继承此基类, 统一接口:
  - fit(factor_data, returns, controls=None): 拟合
  - get_diagnostics(): 返回诊断 dict
  - get_residual_threat(): 返回残留威胁 τ ∈ [0, 1]

残留威胁 τ 的语义:
  估计器吸收部分内生性后, 残留的威胁等级.
  τ=0 表示内生性完全消除, τ=1 表示估计器无效果.
  E5 三层正则化基于此 τ 进一步调整.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


class BaseEndogeneityEstimator(ABC):
    """内生性缓解估计器抽象基类.

    子类必须实现:
      - _fit_impl(factor_data, returns, controls): 核心拟合逻辑
      - get_diagnostics(): 返回诊断 dict (至少含 'beta', 'method', 'residual_threat_tau')
      - get_residual_threat(): 返回残留威胁 τ ∈ [0, 1]

    通用预处理 (NaN 处理等) 在 fit() 中统一完成, 子类只需实现 _fit_impl.
    """

    def __init__(self):
        self._diagnostics: Dict[str, Any] = {}
        self._fitted: bool = False

    def fit(
        self,
        factor_data: pd.DataFrame,
        returns: pd.DataFrame,
        controls: Optional[pd.DataFrame] = None,
    ) -> 'BaseEndogeneityEstimator':
        """拟合估计器.

        通用预处理: 对齐索引、NaN 填充 (列均值), 然后委托给 _fit_impl.

        Args:
            factor_data: 因子数据 (T, N)
            returns: 收益数据 (T, N)
            controls: 控制变量 (可选, (T, K))

        Returns:
            self
        """
        # 对齐索引
        factor_data = factor_data.copy()
        returns = returns.copy()
        if controls is not None:
            controls = controls.copy()

        # NaN 处理: 列均值填充 (不崩溃, E6-T27)
        factor_data = factor_data.fillna(factor_data.mean())
        returns = returns.fillna(returns.mean())
        if controls is not None:
            controls = controls.fillna(controls.mean())

        # 若全 NaN 列 → 填 0
        factor_data = factor_data.fillna(0.0)
        returns = returns.fillna(0.0)
        if controls is not None:
            controls = controls.fillna(0.0)

        self._fit_impl(factor_data, returns, controls)
        self._fitted = True
        return self

    @abstractmethod
    def _fit_impl(
        self,
        factor_data: pd.DataFrame,
        returns: pd.DataFrame,
        controls: Optional[pd.DataFrame] = None,
    ) -> None:
        """子类实现的核心拟合逻辑 (预处理后调用)."""
        pass

    @abstractmethod
    def get_diagnostics(self) -> Dict[str, Any]:
        """返回诊断 dict.

        必须包含:
          - 'method': 方法标识 (如 'profile_gmm')
          - 'beta': 估计系数
          - 'residual_threat_tau': 残留威胁 τ ∈ [0, 1]
        """
        pass

    @abstractmethod
    def get_residual_threat(self) -> float:
        """返回残留威胁 τ ∈ [0, 1].

        τ=0: 内生性完全消除
        τ=1: 估计器无效果
        """
        pass

    def _clamp_tau(self, tau: float) -> float:
        """将 τ 钳制到 [0, 1] 区间."""
        return float(np.clip(tau, 0.0, 1.0))
