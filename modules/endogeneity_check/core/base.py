# -*- coding: utf-8 -*-
"""内生性检验器抽象基类.

所有具体检验器 (Oster δ / AET / IFE / Lewbel) 继承此类,
遵循 sklearn-style fit/get_diagnostics 接口.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import pandas as pd


class BaseEndogeneityChecker(ABC):
    """内生性检验器抽象基类.

    所有具体检验器 (Oster δ / AET / IFE / Lewbel) 继承此类,
    遵循 sklearn-style fit/get_diagnostics 接口.
    """

    @abstractmethod
    def fit(
        self,
        factor_data: pd.DataFrame,
        returns: pd.DataFrame,
        controls: Optional[pd.DataFrame] = None,
    ) -> 'BaseEndogeneityChecker':
        """拟合检验器."""
        ...

    @abstractmethod
    def get_diagnostics(self) -> Dict[str, Any]:
        """返回诊断结果 dict."""
        ...

    def get_threat_level(self) -> float:
        """返回内生性威胁等级 τ ∈ [0, 1] (0=无威胁, 1=最高威胁)."""
        diagnostics = self.get_diagnostics()
        return diagnostics.get('threat_tau', 0.0)
