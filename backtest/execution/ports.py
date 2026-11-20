# -*- coding: utf-8 -*-
"""v3.8.0 执行/容量模块端口契约（纯契约，无实现、无 IO）。

设计依据：DESIGN_EXECUTION_CAPACITY_V3.8.0.md §4；
实施依据：EXECUTION_V3.8.0_EXECUTION_CAPACITY.md §2.1。
本模块不 import 任何 ``backtest.*``，避免与父包形成环。
"""
from typing import Mapping, Protocol, Sequence, runtime_checkable

import numpy as np

__all__ = ["CalibrationUnavailable", "ImpactModel", "SpreadEstimator",
           "VolumeClassifier", "DecayModel"]


class CalibrationUnavailable(RuntimeError):
    """分钟级校准所需的可选依赖或数据缺失。"""


@runtime_checkable
class ImpactModel(Protocol):
    """参与率 -> 单边冲击（率，非 bps）。"""

    name: str

    def predict(self, participation: np.ndarray, sigma: np.ndarray,
                params: Mapping[str, float]) -> np.ndarray:
        ...

    def fit(self, participation: np.ndarray, impact: np.ndarray,
            sigma: np.ndarray) -> Mapping[str, float]:
        ...


@runtime_checkable
class SpreadEstimator(Protocol):
    """日频 OHLC -> 相对有效价差（比例）。"""

    name: str

    def estimate(self, high: np.ndarray, low: np.ndarray,
                 close: np.ndarray) -> np.ndarray:
        ...


@runtime_checkable
class VolumeClassifier(Protocol):
    """分钟 bar -> 买入量占比 ∈ [0, 1]。"""

    name: str

    def classify(self, ret: np.ndarray, volume: np.ndarray,
                 sigma: np.ndarray) -> np.ndarray:
        ...


@runtime_checkable
class DecayModel(Protocol):
    """持有期（交易日） -> alpha 保留率。"""

    name: str

    def retention(self, horizons: Sequence[int]) -> np.ndarray:
        ...
