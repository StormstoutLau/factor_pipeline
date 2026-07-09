# -*- coding: utf-8 -*-
"""
插补器实现
实现各种因子缺失插补方法
"""

import warnings
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from .base import BaseImputer, ImputationResult, ImputationStrategy


class HierarchicalImputer(BaseImputer):
    """分层插补器 - 统一接口管理多种插补策略"""

    def __init__(self, strategy="auto", **params):
        super().__init__(**params)
        self.strategy = strategy
        self.imputers = {
            "cross_sectional": CrossSectionalImputer(),
            "time_series": TimeSeriesImputer(),
            "panel_hierarchical": PanelHierarchicalImputer(),
            "ml_advanced": MLAdvancedImputer(),
            "factor_specific": FactorSpecificImputer(),
        }
        self.selected_imputer = None

    def fit(self, X: pd.DataFrame, missing_info: Dict[str, Any] = None) -> "HierarchicalImputer":
        """选择并拟合最优插补器"""
        if missing_info is None:
            missing_info = self.detect_missing_type(X)

        # 选择插补策略
        self.selected_imputer = self._select_imputer(X, missing_info)

        # 拟合选定的插补器
        if self.selected_imputer:
            self.selected_imputer.fit(X, missing_info)
            self.is_fitted = True

        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用插补"""
        if not self.is_fitted or self.selected_imputer is None:
            raise ValueError("插补器未拟合或选择失败")

        return self.selected_imputer.transform(X)

    def _select_imputer(self, X: pd.DataFrame, missing_info: Dict[str, Any]) -> BaseImputer:
        """根据缺失信息选择最优插补器"""
        missing_pattern = missing_info.get("missing_pattern", "random")
        missing_type = missing_info.get("missing_type", "MCAR")
        missing_rate = missing_info.get("overall_rate", 0)

        if self.strategy != "auto":
            return self.imputers.get(self.strategy)

        # 自动选择逻辑
        if missing_pattern == "cross_sectional":
            return self.imputers["cross_sectional"]
        elif missing_pattern == "time_series":
            return self.imputers["time_series"]
        elif missing_rate > 0.3:
            return self.imputers["ml_advanced"]
        elif missing_type == "MNAR":
            return self.imputers["factor_specific"]
        else:
            return self.imputers["panel_hierarchical"]


class CrossSectionalImputer(BaseImputer):
    """截面插补器 - 基于截面统计量的插补"""

    def __init__(self, method="median", group_by=None, **params):
        super().__init__(**params)
        self.method = method
        self.group_by = group_by
        self.group_stats = {}

    def fit(self, X: pd.DataFrame, missing_info: Dict[str, Any] = None) -> "CrossSectionalImputer":
        """计算截面统计量"""
        if self.group_by is None:
            # 全局统计量
            if self.method == "median":
                self.global_stat = X.median()
            elif self.method == "mean":
                self.global_stat = X.mean()
            elif self.method == "winsorized_mean":
                self.global_stat = self._winsorized_mean(X)
            else:
                self.global_stat = X.median()
        else:
            # 分组统计量
            self.group_stats = self._calculate_group_stats(X)

        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用截面插补"""
        X_imputed = X.copy()

        if self.group_by is None:
            # 使用全局统计量
            X_imputed = X_imputed.fillna(self.global_stat)
        else:
            # 使用分组统计量
            for group_name, group_stat in self.group_stats.items():
                group_mask = self._get_group_mask(X, group_name)
                X_imputed.loc[group_mask] = X_imputed.loc[group_mask].fillna(group_stat)

        return X_imputed

    def _winsorized_mean(self, X: pd.DataFrame, limits=(0.05, 0.05)) -> pd.Series:
        """计算缩尾均值"""
        winsorized_data = X.clip(lower=X.quantile(limits[0]), upper=X.quantile(1 - limits[1]), axis=1)
        return winsorized_data.mean()

    def _calculate_group_stats(self, X: pd.DataFrame) -> Dict[str, pd.Series]:
        """计算分组统计量"""
        group_stats = {}

        # 这里假设有分组信息，实际应用中需要传入
        # 简化实现：按市值分组（如果有市值信息）
        if "market_cap" in X.columns:
            large_cap_mask = X["market_cap"] > X["market_cap"].quantile(0.7)
            mid_cap_mask = (X["market_cap"] > X["market_cap"].quantile(0.3)) & (
                X["market_cap"] <= X["market_cap"].quantile(0.7)
            )
            small_cap_mask = X["market_cap"] <= X["market_cap"].quantile(0.3)

            if self.method == "median":
                group_stats["large_cap"] = X[large_cap_mask].median()
                group_stats["mid_cap"] = X[mid_cap_mask].median()
                group_stats["small_cap"] = X[small_cap_mask].median()
            else:
                group_stats["large_cap"] = X[large_cap_mask].mean()
                group_stats["mid_cap"] = X[mid_cap_mask].mean()
                group_stats["small_cap"] = X[small_cap_mask].mean()

        return group_stats

    def _get_group_mask(self, X: pd.DataFrame, group_name: str) -> pd.Series:
        """获取分组掩码"""
        if "market_cap" in X.columns:
            if group_name == "large_cap":
                return X["market_cap"] > X["market_cap"].quantile(0.7)
            elif group_name == "mid_cap":
                return (X["market_cap"] > X["market_cap"].quantile(0.3)) & (
                    X["market_cap"] <= X["market_cap"].quantile(0.7)
                )
            elif group_name == "small_cap":
                return X["market_cap"] <= X["market_cap"].quantile(0.3)

        return pd.Series([True] * len(X), index=X.index)


class TimeSeriesImputer(BaseImputer):
    """时序插补器 - 基于时间序列的插补"""

    def __init__(self, method="ffill", window=5, **params):
        super().__init__(**params)
        self.method = method
        self.window = window
        self.asset_stats = {}

    def fit(self, X: pd.DataFrame, missing_info: Dict[str, Any] = None) -> "TimeSeriesImputer":
        """计算时序统计量"""
        if self.method == "rolling_mean":
            # 计算滚动均值
            self.asset_stats = {}
            for asset in X.columns:
                self.asset_stats[asset] = X[asset].rolling(window=self.window, min_periods=1).mean()
        elif self.method == "exponential_smoothing":
            # 计算指数平滑
            self.asset_stats = {}
            for asset in X.columns:
                self.asset_stats[asset] = X[asset].ewm(span=self.window).mean()

        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用时序插补"""
        X_imputed = X.copy()

        if self.method == "ffill":
            # 前向填充
            X_imputed = X_imputed.ffill()
            # 如果还有缺失，用后向填充
            X_imputed = X_imputed.bfill()
        elif self.method == "rolling_mean":
            # 滚动均值填充
            for asset in X.columns:
                if asset in self.asset_stats:
                    X_imputed[asset] = X_imputed[asset].fillna(self.asset_stats[asset])
        elif self.method == "exponential_smoothing":
            # 指数平滑填充
            for asset in X.columns:
                if asset in self.asset_stats:
                    X_imputed[asset] = X_imputed[asset].fillna(self.asset_stats[asset])

        return X_imputed


class PanelHierarchicalImputer(BaseImputer):
    """面板分层插补器 - 结合截面和时序信息"""

    def __init__(self, cross_sectional_weight=0.6, time_series_weight=0.4, **params):
        super().__init__(**params)
        self.cross_sectional_weight = cross_sectional_weight
        self.time_series_weight = time_series_weight
        self.cs_imputer = CrossSectionalImputer()
        self.ts_imputer = TimeSeriesImputer()

    def fit(self, X: pd.DataFrame, missing_info: Dict[str, Any] = None) -> "PanelHierarchicalImputer":
        """拟合两个子插补器"""
        self.cs_imputer.fit(X, missing_info)
        self.ts_imputer.fit(X, missing_info)
        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用分层插补"""
        # 分别获取截面和时序插补结果
        cs_imputed = self.cs_imputer.transform(X)
        ts_imputed = self.ts_imputer.transform(X)

        # 加权组合
        missing_mask = X.isnull()
        combined_imputed = X.copy()

        # 只对缺失位置进行插补
        combined_imputed[missing_mask] = (
            self.cross_sectional_weight * cs_imputed[missing_mask] + self.time_series_weight * ts_imputed[missing_mask]
        )

        return combined_imputed


class MLAdvancedImputer(BaseImputer):
    """机器学习高级插补器"""

    def __init__(self, method="knn", n_neighbors=5, **params):
        super().__init__(**params)
        self.method = method
        self.n_neighbors = n_neighbors
        self.models = {}
        self.scalers = {}

    def fit(self, X: pd.DataFrame, missing_info: Dict[str, Any] = None) -> "MLAdvancedImputer":
        """训练机器学习模型"""
        if self.method == "knn":
            self._fit_knn(X)
        elif self.method == "random_forest":
            self._fit_random_forest(X)

        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用机器学习插补"""
        X_imputed = X.copy()

        if self.method == "knn":
            X_imputed = self._transform_knn(X_imputed)
        elif self.method == "random_forest":
            X_imputed = self._transform_random_forest(X_imputed)

        return X_imputed

    def _fit_knn(self, X: pd.DataFrame):
        """拟合KNN插补器"""
        # 对每个资产拟合KNN
        for asset in X.columns:
            asset_data = X[asset].dropna()
            if len(asset_data) > self.n_neighbors:
                # 使用其他资产作为特征
                other_assets = [col for col in X.columns if col != asset]
                features = X[other_assets].loc[asset_data.index].ffill().bfill()

                if not features.empty:
                    self.scalers[asset] = StandardScaler()
                    scaled_features = self.scalers[asset].fit_transform(features)

                    self.models[asset] = NearestNeighbors(n_neighbors=self.n_neighbors)
                    self.models[asset].fit(scaled_features)

    def _transform_knn(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用KNN插补"""
        for asset in X.columns:
            if asset in self.models and asset in self.scalers:
                missing_mask = X[asset].isnull()
                if missing_mask.any():
                    # 获取缺失位置的特征
                    other_assets = [col for col in X.columns if col != asset]
                    features = X[other_assets].ffill().bfill()
                    missing_features = features.loc[missing_mask]

                    if not missing_features.empty:
                        scaled_features = self.scalers[asset].transform(missing_features)
                        distances, indices = self.models[asset].kneighbors(scaled_features)

                        # 使用K近邻的平均值填充
                        for i, (dist, idx) in enumerate(zip(distances, indices)):
                            neighbor_values = X[asset].iloc[idx].values
                            # 距离加权平均
                            weights = 1 / (dist + 1e-10)
                            weighted_value = np.sum(neighbor_values * weights) / np.sum(weights)
                            X.loc[missing_mask[missing_mask].index[i], asset] = weighted_value

        return X

    def _fit_random_forest(self, X: pd.DataFrame):
        """拟合随机森林插补器"""
        for asset in X.columns:
            asset_data = X[asset].dropna()
            if len(asset_data) > 10:
                # 使用其他资产和时间特征作为特征
                other_assets = [col for col in X.columns if col != asset]
                features = X[other_assets].loc[asset_data.index].ffill().bfill()

                if not features.empty:
                    # 添加时间特征
                    if isinstance(X.index, pd.DatetimeIndex):
                        time_features = pd.DataFrame(
                            {
                                "year": asset_data.index.year,
                                "month": asset_data.index.month,
                                "day": asset_data.index.day,
                                "dayofweek": asset_data.index.dayofweek,
                            },
                            index=asset_data.index,
                        )
                        features = pd.concat([features, time_features], axis=1)

                    self.scalers[asset] = StandardScaler()
                    scaled_features = self.scalers[asset].fit_transform(features)

                    self.models[asset] = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42)
                    self.models[asset].fit(scaled_features, asset_data.values)

    def _transform_random_forest(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用随机森林插补"""
        for asset in X.columns:
            if asset in self.models and asset in self.scalers:
                missing_mask = X[asset].isnull()
                if missing_mask.any():
                    # 获取缺失位置的特征
                    other_assets = [col for col in X.columns if col != asset]
                    features = X[other_assets].ffill().bfill()
                    missing_features = features.loc[missing_mask]

                    if not missing_features.empty:
                        # 添加时间特征
                        if isinstance(X.index, pd.DatetimeIndex):
                            time_features = pd.DataFrame(
                                {
                                    "year": missing_features.index.year,
                                    "month": missing_features.index.month,
                                    "day": missing_features.index.day,
                                    "dayofweek": missing_features.index.dayofweek,
                                },
                                index=missing_features.index,
                            )
                            missing_features = pd.concat([missing_features, time_features], axis=1)

                        scaled_features = self.scalers[asset].transform(missing_features)
                        predicted_values = self.models[asset].predict(scaled_features)

                        X.loc[missing_mask[missing_mask].index, asset] = predicted_values

        return X


class FactorSpecificImputer(BaseImputer):
    """因子专属插补器 - 处理特定因子类型的缺失"""

    def __init__(self, factor_type="auto", **params):
        super().__init__(**params)
        self.factor_type = factor_type
        self.regression_models = {}
        self.missing_indicators = {}

    def fit(self, X: pd.DataFrame, missing_info: Dict[str, Any] = None) -> "FactorSpecificImputer":
        """拟合因子专属模型"""
        # 识别因子类型
        if self.factor_type == "auto":
            self.factor_type = self._identify_factor_type(X)

        # 根据因子类型选择处理方法
        if self.factor_type in ["fundamental", "valuation"]:
            self._fit_fundamental_imputer(X)
        elif self.factor_type == "technical":
            self._fit_technical_imputer(X)
        elif self.factor_type == "macro":
            self._fit_macro_imputer(X)
        else:
            self._fit_generic_imputer(X)

        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用因子专属插补"""
        X_imputed = X.copy()

        # 创建缺失指示变量
        for asset in X.columns:
            missing_mask = X[asset].isnull()
            if missing_mask.any():
                indicator_name = f"{asset}_missing"
                X_imputed[indicator_name] = missing_mask.astype(int)
                self.missing_indicators[asset] = indicator_name

        # 根据因子类型应用插补
        if self.factor_type in ["fundamental", "valuation"]:
            X_imputed = self._transform_fundamental(X_imputed)
        elif self.factor_type == "technical":
            X_imputed = self._transform_technical(X_imputed)
        elif self.factor_type == "macro":
            X_imputed = self._transform_macro(X_imputed)
        else:
            X_imputed = self._transform_generic(X_imputed)

        return X_imputed

    def _identify_factor_type(self, X: pd.DataFrame) -> str:
        """识别因子类型"""
        # 简化的因子类型识别逻辑
        # 实际应用中需要更复杂的规则

        # 基于数据特征判断
        if isinstance(X.index, pd.DatetimeIndex):
            freq = pd.infer_freq(X.index)
            if freq and "D" in freq:
                return "technical"  # 日频数据可能是技术因子
            elif freq and "M" in freq:
                return "fundamental"  # 月频数据可能是基本面因子

        return "generic"

    def _fit_fundamental_imputer(self, X: pd.DataFrame):
        """拟合基本面因子插补器"""
        # 使用相关因子进行回归插补
        for asset in X.columns:
            other_assets = [col for col in X.columns if col != asset]

            if len(other_assets) > 0:
                # 使用其他因子作为特征
                features = X[other_assets].ffill().bfill()
                target = X[asset].dropna()

                if len(target) > 10 and not features.empty:
                    common_index = target.index.intersection(features.index)
                    if len(common_index) > 10:
                        X_features = features.loc[common_index]
                        y_target = target.loc[common_index]

                        # 线性回归
                        model = LinearRegression()
                        model.fit(X_features, y_target)
                        self.regression_models[asset] = model

    def _fit_technical_imputer(self, X: pd.DataFrame):
        """拟合技术因子插补器"""
        # 技术因子通常使用时序方法
        pass

    def _fit_macro_imputer(self, X: pd.DataFrame):
        """拟合宏观因子插补器"""
        # 宏观因子使用指数平滑
        pass

    def _fit_generic_imputer(self, X: pd.DataFrame):
        """拟合通用插补器"""
        pass

    def _transform_fundamental(self, X: pd.DataFrame) -> pd.DataFrame:
        """基本面因子插补变换"""
        for asset, model in self.regression_models.items():
            missing_mask = X[asset].isnull()
            if missing_mask.any():
                other_assets = [col for col in X.columns if col != asset and not col.endswith("_missing")]
                features = X[other_assets].ffill().bfill()
                missing_features = features.loc[missing_mask]

                if not missing_features.empty:
                    predicted_values = model.predict(missing_features)
                    X.loc[missing_mask[missing_mask].index, asset] = predicted_values

        return X

    def _transform_technical(self, X: pd.DataFrame) -> pd.DataFrame:
        """技术因子插补变换"""
        # 使用前向填充和滚动均值
        for asset in X.columns:
            if not asset.endswith("_missing"):
                X[asset] = X[asset].ffill().fillna(X[asset].rolling(window=5, min_periods=1).mean())

        return X

    def _transform_macro(self, X: pd.DataFrame) -> pd.DataFrame:
        """宏观因子插补变换"""
        # 使用指数平滑
        for asset in X.columns:
            if not asset.endswith("_missing"):
                X[asset] = X[asset].ffill().fillna(X[asset].ewm(span=10).mean())

        return X

    def _transform_generic(self, X: pd.DataFrame) -> pd.DataFrame:
        """通用插补变换"""
        # 使用简单的前向填充
        for asset in X.columns:
            if not asset.endswith("_missing"):
                X[asset] = X[asset].ffill().bfill()

        return X


class MissingImputationModule:
    """缺失插补模块 - 统一管理接口"""

    def __init__(self, default_strategy="auto"):
        self.default_strategy = default_strategy
        self.imputation_history = []

    def impute(self, factor_data: pd.DataFrame, diagnosis: Dict[str, Any] = None) -> ImputationResult:
        """执行缺失插补"""
        result = ImputationResult()
        result.original_data = factor_data.copy()

        # 检测缺失
        if diagnosis is None:
            from .missing_diagnoser import MissingTypeDiagnoser

            diagnoser = MissingTypeDiagnoser()
            diagnosis = diagnoser.diagnose(factor_data)

        missing_rate = diagnosis["missing_rate"]["overall_rate"]

        if missing_rate == 0:
            # 无缺失，直接返回
            result.imputed_data = factor_data.copy()
            result.imputation_strategy = "none"
            return result

        # 选择插补策略
        strategy = self._select_strategy(diagnosis)

        # 执行插补
        imputer = HierarchicalImputer(strategy=strategy)
        imputed_data = imputer.fit_transform(factor_data, diagnosis)

        # 验证插补质量
        quality_metrics = self._assess_imputation_quality(factor_data, imputed_data)

        # 填充结果
        result.imputed_data = imputed_data
        result.imputation_strategy = strategy
        result.imputation_quality = quality_metrics
        result.processing_log.append(f"使用策略: {strategy}")
        result.processing_log.append(f"缺失率: {missing_rate:.4f}")

        # 保存历史
        self.imputation_history.append(result.to_dict())

        return result

    def _select_strategy(self, diagnosis: Dict[str, Any]) -> str:
        """选择插补策略"""
        missing_pattern = diagnosis["missing_pattern"]
        missing_type = diagnosis["missing_type"]
        missing_rate = diagnosis["missing_rate"]["overall_rate"]

        # 基于决策矩阵选择策略
        if missing_pattern == "cross_sectional":
            return "cross_sectional"
        elif missing_pattern == "time_series":
            return "time_series"
        elif missing_rate > 0.3:
            return "ml_advanced"
        elif missing_type == "MNAR":
            return "factor_specific"
        else:
            return "panel_hierarchical"

    def _assess_imputation_quality(self, original_data: pd.DataFrame, imputed_data: pd.DataFrame) -> Dict[str, Any]:
        """评估插补质量"""
        missing_mask = original_data.isnull()
        imputed_values = imputed_data[missing_mask]

        quality_metrics = {
            "imputation_count": missing_mask.sum().sum(),
            "imputation_stats": {
                "mean": imputed_values.mean().mean() if not imputed_values.empty else 0,
                "std": imputed_values.std().mean() if not imputed_values.empty else 0,
                "min": imputed_values.min().min() if not imputed_values.empty else 0,
                "max": imputed_values.max().max() if not imputed_values.empty else 0,
            },
            "data_completeness": (
                1 - imputed_data.isnull().sum().sum() / imputed_data.shape[0] / imputed_data.shape[1]
            ),
            "distribution_similarity": self._calculate_distribution_similarity(original_data, imputed_data),
        }

        return quality_metrics

    def _calculate_distribution_similarity(self, original_data: pd.DataFrame, imputed_data: pd.DataFrame) -> float:
        """计算分布相似度"""
        # 只比较非缺失部分
        original_valid = original_data.dropna()
        imputed_valid = imputed_data.loc[original_valid.index, original_valid.columns]

        if original_valid.empty or imputed_valid.empty:
            return 0.0

        # 计算相关系数
        correlations = []
        for col in original_valid.columns:
            if col in imputed_valid.columns:
                corr = np.corrcoef(original_valid[col], imputed_valid[col])[0, 1]
                if not np.isnan(corr):
                    correlations.append(corr)

        return np.mean(correlations) if correlations else 0.0
