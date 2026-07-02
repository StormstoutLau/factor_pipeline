# -*- coding: utf-8 -*-
"""
插件基类模块
提供插补插件的标准接口
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

import pandas as pd


class ImputationPlugin(ABC):
    """插补插件基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """插件名称"""
        pass

    @property
    @abstractmethod
    def supported_patterns(self) -> List[str]:
        """支持的缺失模式"""
        pass

    @abstractmethod
    def fit(self, X: pd.DataFrame, **kwargs) -> "ImputationPlugin":
        """拟合插件"""
        pass

    @abstractmethod
    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用插补"""
        pass

    def fit_transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """拟合并变换"""
        return self.fit(X, **kwargs).transform(X)
