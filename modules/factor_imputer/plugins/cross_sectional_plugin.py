# -*- coding: utf-8 -*-
"""
截面插补插件
"""

from typing import List

import numpy as np
import pandas as pd

from .base import ImputationPlugin


class CrossSectionalPlugin(ImputationPlugin):
    """截面插补插件"""

    @property
    def name(self) -> str:
        return "cross_sectional"

    @property
    def supported_patterns(self) -> List[str]:
        return ["random", "cross_sectional", "mixed"]

    def __init__(self, method: str = "median"):
        self.method = method
        self._fitted = False

    def fit(self, X: pd.DataFrame, **kwargs) -> "CrossSectionalPlugin":
        """拟合插件"""
        self._fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用截面插补"""
        if not self._fitted:
            raise RuntimeError("插件未拟合，请先调用 fit()")

        result = X.copy()

        for col in X.columns:
            missing_mask = X[col].isnull()
            if missing_mask.any():
                if self.method == "median":
                    fill_value = X[col].median()
                elif self.method == "mean":
                    fill_value = X[col].mean()
                else:
                    fill_value = X[col].median()

                result.loc[missing_mask, col] = fill_value

        return result
