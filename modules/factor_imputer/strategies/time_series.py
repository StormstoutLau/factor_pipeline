# -*- coding: utf-8 -*-
"""
时序插补策略
基于时间序列特征的插补方法
"""

import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from scipy import stats

try:
    from sklearn.linear_model import LinearRegression
except ImportError:
    LinearRegression = None

from ..core.base import BaseImputer


class TimeSeriesStrategy(BaseImputer):
    """时序插补器 - 基于时间序列特征的插补"""

    def __init__(self, method="linear", window=20, **params):
        super().__init__(**params)
        self.method = method
        self.window = window
        self.time_series_params = {}

    def fit(self, X: pd.DataFrame, missing_info: Dict[str, Any] = None) -> "TimeSeriesStrategy":
        """拟合时序插补参数"""
        self.time_series_params = self._analyze_time_series(X)
        self.is_fitted = True
        return self

    def _analyze_time_series(self, X: pd.DataFrame) -> Dict[str, Any]:
        """分析时间序列特征"""
        params = {}

        for col in X.columns:
            series = X[col].dropna()

            if len(series) > 1:
                # 计算自相关系数
                autocorr = series.autocorr(lag=1) if hasattr(series, "autocorr") else 0

                # 计算滚动统计量
                rolling_median = series.rolling(window=min(10, len(series)), min_periods=1).median()

                params[col] = {
                    "autocorr": autocorr,
                    "rolling_median": rolling_median,
                    "global_median": series.median(),
                    "mad": (series - series.median()).abs().median(),
                }

        return params

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用时序插补"""
        X_imputed = X.copy()

        for col in X.columns:
            series = X_imputed[col].copy()

            if series.isnull().any():
                if self.method == "linear":
                    series = self._linear_interpolation(series)
                elif self.method == "forward_fill":
                    series = series.ffill()
                elif self.method == "backward_fill":
                    series = series.bfill()
                elif self.method == "rolling":
                    series = self._rolling_imputation(series)

                X_imputed[col] = series

        return X_imputed

    def _linear_interpolation(self, series: pd.Series) -> pd.Series:
        """线性插值"""
        return series.interpolate(method="linear", limit_direction="both")

    def _rolling_imputation(self, series: pd.Series) -> pd.Series:
        """滚动均值插补"""
        rolling_mean = series.rolling(window=self.window, min_periods=1).mean()
        return series.fillna(rolling_mean)

    def fit_transform(self, X: pd.DataFrame, missing_info: Dict[str, Any] = None) -> pd.DataFrame:
        """拟合并变换"""
        return self.fit(X, missing_info).transform(X)
