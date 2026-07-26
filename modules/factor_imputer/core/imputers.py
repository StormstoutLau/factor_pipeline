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

    def __init__(self, strategy="auto", lookahead_safe: bool = True, **params):
        super().__init__(**params)
        self.strategy = strategy
        # P1-1 (§5.4): lookahead_safe 透传给所有子插补器.
        # 默认 True (生产路径强制因果), False 走 legacy 全样本路径 (DEPRECATED).
        self.lookahead_safe = lookahead_safe
        self.imputers = {
            "cross_sectional": CrossSectionalImputer(lookahead_safe=lookahead_safe),
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
    """截面插补器 - 基于截面统计量的插补

    P1-2 (§5.3) 双重修复:
    - axis 语义: 原 X.median() 默认 axis=0 (时间序列), 类名暗示 axis=1 (截面)
    - lookahead_safe: True → expanding/rolling 因果版本; False → legacy 全样本 (DEPRECATED)
    """

    def __init__(self, method="median", group_by=None,
                 lookahead_safe: bool = True,
                 window: Optional[int] = None,  # None=expanding, int=rolling
                 min_periods: int = 5,
                 **params):
        super().__init__(**params)
        self.method = method
        self.group_by = group_by
        # P1-2: lookahead_safe 控制因果 vs legacy
        self.lookahead_safe = lookahead_safe
        self.window = window
        self.min_periods = min_periods
        self.group_stats = {}
        # legacy 全样本统计量 (仅 lookahead_safe=False 时使用)
        self.global_stat = None

    def fit(self, X: pd.DataFrame, missing_info: Dict[str, Any] = None) -> "CrossSectionalImputer":
        """计算截面统计量"""
        if self.group_by is None:
            # legacy 全样本统计量 (仅 lookahead_safe=False 时使用)
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
        """应用截面插补.

        P1-2: 根据 lookahead_safe 分发到因果 / legacy 路径.
        """
        if not self.lookahead_safe:
            return self._transform_legacy(X)
        return self._transform_causal(X)

    def _transform_causal(self, X: pd.DataFrame) -> pd.DataFrame:
        """因果版本: t 时刻用 [0, t] 区间统计量填 t 时刻缺失.

        - window=None: expanding (用 [0, t] 全部历史, 跨时间聚合 per asset)
        - window=int: rolling (用 [t-W+1, t] 窗口)

        注: expanding/rolling 默认 axis=0 (跨时间 per asset).
        真正的截面因果 (axis=1, 跨资产) 见 _transform_causal_cross_sectional.
        """
        X_imputed = X.copy()

        if self.window is None:
            # expanding: 用 [0, t] 全部历史
            if self.method == "median":
                stats_t = X.expanding(min_periods=self.min_periods).median()
            elif self.method == "mean":
                stats_t = X.expanding(min_periods=self.min_periods).mean()
            else:
                stats_t = X.expanding(min_periods=self.min_periods).median()
        else:
            # rolling: 用 [t-W+1, t]
            if self.method == "median":
                stats_t = X.rolling(window=self.window, min_periods=self.min_periods).median()
            elif self.method == "mean":
                stats_t = X.rolling(window=self.window, min_periods=self.min_periods).mean()
            else:
                stats_t = X.rolling(window=self.window, min_periods=self.min_periods).median()

        # 用当期统计量填当期缺失
        missing_mask = X.isnull()
        X_imputed[missing_mask] = stats_t[missing_mask]

        # 前期仍未填的 (开头 min_periods 期) → 0
        X_imputed = X_imputed.fillna(0)

        return X_imputed

    def _transform_legacy(self, X: pd.DataFrame) -> pd.DataFrame:
        """原全样本路径 — DEPRECATED, 含前视偏差.

        保留仅为向后兼容, 生产路径不应调用.
        """
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
        """计算时序统计量.

        P0-5 向量化: 用 DataFrame 级 rolling/ewm 替代按资产循环.
        保持结果等价 (见 test_rolling_mean_equivalent_to_loop /
        test_ewm_equivalent_to_loop).
        """
        if self.method == "rolling_mean":
            # 向量化: 一次 rolling 整个 DataFrame
            self.asset_stats = X.rolling(window=self.window, min_periods=1).mean()
        elif self.method == "exponential_smoothing":
            # 向量化: 一次 ewm 整个 DataFrame
            self.asset_stats = X.ewm(span=self.window).mean()

        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用时序插补.

        P0-5 向量化: 用 DataFrame.fillna 替代按资产循环.
        """
        X_imputed = X.copy()

        if self.method == "ffill":
            X_imputed = X_imputed.ffill()
            # P0-2 audit fix: bfill leaks future data, use ffill+0 instead
            # Any remaining NaN (start of series with no prior) fills with 0
            X_imputed = X_imputed.fillna(0)
        elif self.method == "rolling_mean":
            # 向量化: DataFrame.fillna 接收 DataFrame 参数
            # 只填充 asset_stats 中存在的列, 避免意外覆盖
            common_cols = X_imputed.columns.intersection(self.asset_stats.columns)
            X_imputed[common_cols] = X_imputed[common_cols].fillna(self.asset_stats[common_cols])
        elif self.method == "exponential_smoothing":
            common_cols = X_imputed.columns.intersection(self.asset_stats.columns)
            X_imputed[common_cols] = X_imputed[common_cols].fillna(self.asset_stats[common_cols])

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
    """机器学习高级插补器

    P1-3 (§5.2.1): walk_forward=True 时, KNN 在 transform 时按 t 切片训练,
    仅用 [0, t-1] 数据 (因果).
    P1-4 (§5.2.3 方案 A): shared_model=True 时, RF 训练一个 multi-output
    模型, 所有资产共用 (避免内存爆炸).
    """

    def __init__(self, method="knn", n_neighbors=5,
                 walk_forward: bool = True,
                 shared_model: bool = True,
                 **params):
        super().__init__(**params)
        self.method = method
        self.n_neighbors = n_neighbors
        # P1-3: walk_forward 默认 True, KNN 按缺失点 t 切片训练 (因果)
        self.walk_forward = walk_forward
        # P1-4: shared_model 默认 True, RF 共享 multi-output 模型
        self.shared_model = shared_model
        self.models = {}
        self.scalers = {}
        # shared_model 模式下保存训练时的列顺序 (用于 transform 时特征对齐)
        self._shared_feature_cols = None
        self._shared_target_cols = None

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
            if self.walk_forward:
                X_imputed = self._transform_knn_walk_forward(X_imputed)
            else:
                X_imputed = self._transform_knn(X_imputed)
        elif self.method == "random_forest":
            if self.shared_model and 'shared' in self.models:
                X_imputed = self._transform_rf_shared(X_imputed)
            else:
                X_imputed = self._transform_random_forest(X_imputed)

        return X_imputed

    def _fit_knn(self, X: pd.DataFrame):
        """拟合KNN插补器 (legacy, walk_forward=False 时使用)"""
        for asset in X.columns:
            asset_data = X[asset].dropna()
            if len(asset_data) > self.n_neighbors:
                other_assets = [col for col in X.columns if col != asset]
                # P0 fix: bfill → fillna(0) 消除前视偏差
                features = X[other_assets].loc[asset_data.index].ffill().fillna(0)

                if not features.empty:
                    self.scalers[asset] = StandardScaler()
                    scaled_features = self.scalers[asset].fit_transform(features)

                    self.models[asset] = NearestNeighbors(n_neighbors=self.n_neighbors)
                    self.models[asset].fit(scaled_features)

    def _transform_knn(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用KNN插补 (legacy, walk_forward=False)"""
        for asset in X.columns:
            if asset in self.models and asset in self.scalers:
                missing_mask = X[asset].isnull()
                if missing_mask.any():
                    other_assets = [col for col in X.columns if col != asset]
                    # P0 fix: bfill → fillna(0) 消除前视偏差
                    features = X[other_assets].ffill().fillna(0)
                    missing_features = features.loc[missing_mask]

                    if not missing_features.empty:
                        scaled_features = self.scalers[asset].transform(missing_features)
                        distances, indices = self.models[asset].kneighbors(scaled_features)

                        for i, (dist, idx) in enumerate(zip(distances, indices)):
                            # 修复 KNN 索引 bug: idx 是 asset_data (dropna) 的位置,
                            # 需映射回 X 的位置
                            asset_data = X[asset].dropna()
                            neighbor_idx_in_X = asset_data.index[idx].values
                            neighbor_values = X[asset].loc[neighbor_idx_in_X].values
                            weights = 1 / (dist + 1e-10)
                            weighted_value = np.sum(neighbor_values * weights) / np.sum(weights)
                            X.loc[missing_mask[missing_mask].index[i], asset] = weighted_value

        return X

    def _transform_knn_walk_forward(self, X: pd.DataFrame) -> pd.DataFrame:
        """walk-forward KNN: 每个缺失点 t 用 [0, t-1] 数据训练 (因果).

        P1-3 (§5.2.1): 对每个缺失点 (asset, t), 训练 KNN:
        - 训练数据: X 中 [0, t-1] 行, 且 asset 列非 NaN 的行
        - 特征: other_assets 在这些行的值 (ffill+0 填充)
        - 查询: other_assets 在 t 时刻的值
        - 预测: K 近邻加权平均

        注: 此实现因果, 但每个缺失点都重新训练 KNN, 成本较高.
        """
        for asset in X.columns:
            missing_mask = X[asset].isnull()
            if not missing_mask.any():
                continue

            other_assets = [col for col in X.columns if col != asset]
            if not other_assets:
                continue

            # 按时间顺序处理缺失点
            missing_times = X.index[missing_mask].tolist()
            for t in missing_times:
                # 训练数据: [0, t-1] 中 asset 非 NaN 的行
                train_mask = (X.index < t) & X[asset].notna()
                train_data = X.loc[train_mask]
                if len(train_data) < self.n_neighbors:
                    # 训练数据不足, 用 0 填充
                    X.loc[t, asset] = 0.0
                    continue

                # 训练特征: other_assets 在 train_data 中的值 (ffill+0)
                train_features = train_data[other_assets].ffill().fillna(0)
                train_target = train_data[asset].values

                # 查询特征: other_assets 在 t 时刻的值
                # 注意: 只用 [0, t] 的数据 (因果), t 时刻的 other_assets 可用
                query_features = X.loc[:t, other_assets].ffill().fillna(0).iloc[[-1]]

                # 训练 KNN
                scaler = StandardScaler()
                scaled_train = scaler.fit_transform(train_features)
                scaled_query = scaler.transform(query_features)

                knn = NearestNeighbors(n_neighbors=self.n_neighbors)
                knn.fit(scaled_train)

                distances, indices = knn.kneighbors(scaled_query)
                neighbor_values = train_target[indices[0]]
                weights = 1 / (distances[0] + 1e-10)
                weighted_value = np.sum(neighbor_values * weights) / np.sum(weights)
                X.loc[t, asset] = weighted_value

        return X

    def _fit_random_forest(self, X: pd.DataFrame):
        """拟合随机森林插补器.

        P1-4: shared_model=True 时训练一个 multi-output RF (所有资产共用).
        shared_model=False 时每资产独立 RF (legacy, 内存爆炸).
        """
        if self.shared_model:
            self._fit_random_forest_shared(X)
        else:
            self._fit_random_forest_legacy(X)

    def _fit_random_forest_shared(self, X: pd.DataFrame):
        """共享 multi-output RF: 所有资产作为多输出目标.

        P1-4 (§5.2.3 方案 A): 用行全集 (所有资产都非 NaN 的行) 训练一个 RF.
        内存: O(1) 模型数, 远低于 legacy 的 O(N_assets).
        """
        # 找到所有资产都非 NaN 的行作为训练集
        complete_rows = X.dropna()
        if len(complete_rows) < 10:
            return

        # 特征: 其他资产 + 时间特征
        # 但 multi-output 时, 特征应是"外部信息" (时间), 而非其他资产
        # (否则不同 asset 的"其他资产"定义不同)
        # 简化: 用时间特征作为唯一特征, 所有资产作为多输出目标
        if not isinstance(X.index, pd.DatetimeIndex):
            # 非 DatetimeIndex: 用行号作为特征
            features = pd.DataFrame(
                {'row_idx': np.arange(len(complete_rows))},
                index=complete_rows.index
            )
        else:
            features = pd.DataFrame(
                {
                    "year": complete_rows.index.year,
                    "month": complete_rows.index.month,
                    "day": complete_rows.index.day,
                    "dayofweek": complete_rows.index.dayofweek,
                },
                index=complete_rows.index,
            )

        # 保存特征列和目标列顺序 (用于 transform)
        self._shared_feature_cols = features.columns.tolist()
        self._shared_target_cols = X.columns.tolist()

        # 目标: 所有资产 (multi-output)
        targets = complete_rows[X.columns]

        # 训练共享 RF
        self.scalers['shared'] = StandardScaler()
        scaled_features = self.scalers['shared'].fit_transform(features)

        self.models['shared'] = RandomForestRegressor(
            n_estimators=100, max_depth=10, random_state=42
        )
        self.models['shared'].fit(scaled_features, targets.values)

    def _fit_random_forest_legacy(self, X: pd.DataFrame):
        """legacy RF: 每资产独立模型 (DEPRECATED, 内存爆炸)."""
        for asset in X.columns:
            asset_data = X[asset].dropna()
            if len(asset_data) > 10:
                other_assets = [col for col in X.columns if col != asset]
                # P0 fix: bfill → fillna(0) 消除前视偏差
                features = X[other_assets].loc[asset_data.index].ffill().fillna(0)

                if not features.empty:
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
        """应用随机森林插补 (legacy, 每资产独立)."""
        for asset in X.columns:
            if asset in self.models and asset in self.scalers:
                missing_mask = X[asset].isnull()
                if missing_mask.any():
                    other_assets = [col for col in X.columns if col != asset]
                    # P0 fix: bfill → fillna(0) 消除前视偏差
                    features = X[other_assets].ffill().fillna(0)
                    missing_features = features.loc[missing_mask]

                    if not missing_features.empty:
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

    def _transform_rf_shared(self, X: pd.DataFrame) -> pd.DataFrame:
        """共享 RF 预测: 一次预测所有资产的缺失 (multi-output)."""
        if 'shared' not in self.models or 'shared' not in self.scalers:
            return X
        if self._shared_target_cols is None:
            return X

        # 找所有缺失位置
        missing_mask = X[self._shared_target_cols].isnull()
        if not missing_mask.any().any():
            return X

        # 对每个有缺失的行, 构造特征并预测所有资产
        missing_rows = X.index[missing_mask.any(axis=1)]
        if len(missing_rows) == 0:
            return X

        for t in missing_rows:
            # 构造特征: 时间特征 (与 _fit_random_forest_shared 一致)
            if not isinstance(X.index, pd.DatetimeIndex):
                features = pd.DataFrame(
                    {'row_idx': [X.index.get_loc(t)]},
                    index=[t]
                )
            else:
                ts = X.index[X.index == t]
                features = pd.DataFrame(
                    {
                        "year": [ts.year[0]],
                        "month": [ts.month[0]],
                        "day": [ts.day[0]],
                        "dayofweek": [ts.dayofweek[0]],
                    },
                    index=[t]
                )

            # 标准化并预测
            scaled = self.scalers['shared'].transform(features)
            predicted = self.models['shared'].predict(scaled)  # shape: (1, n_targets)

            # 只填缺失位置, 不覆盖已有值
            for j, asset in enumerate(self._shared_target_cols):
                if pd.isna(X.loc[t, asset]):
                    X.loc[t, asset] = predicted[0, j]

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
                # P0 fix (v2.1): bfill → fillna(0) 消除前视偏差 (IMPUTER_LOOKAHEAD_FIX_PLAN.md §5.1)
                # bfill 用未来值填充 → t 时刻 features 泄漏未来. 改为 ffill+0 保证因果.
                features = X[other_assets].ffill().fillna(0)
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
                # P0 fix (v2.1): bfill → fillna(0) 消除前视偏差 (IMPUTER_LOOKAHEAD_FIX_PLAN.md §5.1)
                # bfill 用未来值填充 → t 时刻 features 泄漏未来. 改为 ffill+0 保证因果.
                features = X[other_assets].ffill().fillna(0)
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
                X[asset] = X[asset].ffill().fillna(0)

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
