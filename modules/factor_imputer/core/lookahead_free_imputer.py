# -*- coding: utf-8 -*-
"""
无前瞻偏差插补器
严格按照"无前瞻插补"标准流程实现
"""

import warnings
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from .base import BaseImputer


class LookaheadFreeImputer(BaseImputer):
    """无前瞻偏差插补器 - 严格遵循时序规则"""

    def __init__(
        self,
        cross_sectional_method="group_median",
        time_series_method="rolling_ffill",
        model_method="rolling_rf",
        window_size=20,
        min_samples=5,
        group_by=None,
        **params,
    ):
        super().__init__(**params)
        self.cross_sectional_method = cross_sectional_method
        self.time_series_method = time_series_method
        self.model_method = model_method
        self.window_size = window_size
        self.min_samples = min_samples
        self.group_by = group_by
        self.group_mappings = {}
        self.rolling_models = {}
        self.missing_indicators = {}

    def fit(self, X: pd.DataFrame, missing_info: Dict[str, Any] = None) -> "LookaheadFreeImputer":
        """拟合插补器（无前瞻偏差）"""
        # 清理旧模型，避免内存泄漏
        self.rolling_models.clear()
        self.group_mappings.clear()

        # 确保数据按时间排序
        if not isinstance(X.index, pd.DatetimeIndex):
            warnings.warn("数据索引不是时间格式，可能导致前瞻偏差")

        # 创建分组映射
        if self.group_by:
            self.group_mappings = self._create_group_mappings(X)

        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用无前瞻偏差插补"""
        # 确保数据按时间排序
        X_sorted = X.sort_index()
        X_imputed = X_sorted.copy()

        # 按时间顺序逐点处理
        for i, time_point in enumerate(X_sorted.index):
            # 获取当前时间点及之前的历史数据
            historical_data = X_sorted.loc[:time_point]

            # 处理当前时间点的缺失值
            missing_mask = X_sorted.loc[time_point].isnull()
            if missing_mask.any():
                imputed_values = self._impute_time_point(historical_data, time_point, missing_mask)
                X_imputed.loc[time_point, missing_mask] = imputed_values

        # 添加缺失指示变量
        X_imputed = self._add_missing_indicators(X, X_imputed)

        return X_imputed

    def _impute_time_point(
        self, historical_data: pd.DataFrame, time_point: pd.Timestamp, missing_mask: pd.Series
    ) -> pd.Series:
        """对单个时间点进行无前瞻偏差插补"""
        missing_assets = missing_mask[missing_mask].index
        imputed_values = pd.Series(index=missing_assets, dtype=float)

        for asset in missing_assets:
            # 1. 尝试时序插补
            ts_value = self._time_series_impute(historical_data[asset], time_point)
            if ts_value is not None:
                imputed_values[asset] = ts_value
                continue

            # 2. 尝试截面插补
            cs_value = self._cross_sectional_impute(historical_data, time_point, asset)
            if cs_value is not None:
                imputed_values[asset] = cs_value
                continue

            # 3. 尝试模型插补
            model_value = self._model_impute(historical_data, time_point, asset)
            if model_value is not None:
                imputed_values[asset] = model_value
                continue

            # 4. 最后回退到简单方法
            imputed_values[asset] = self._fallback_impute(historical_data[asset])

        return imputed_values

    def _time_series_impute(self, asset_series: pd.Series, current_time: pd.Timestamp) -> Optional[float]:
        """时序插补 - 只使用历史数据"""
        # 获取当前时间点之前的数据
        historical_series = asset_series.loc[:current_time].dropna()

        if len(historical_series) == 0:
            return None

        if self.time_series_method == "rolling_ffill":
            # 前向填充
            return historical_series.iloc[-1]

        elif self.time_series_method == "rolling_mean":
            # 滚动均值
            if len(historical_series) >= self.min_samples:
                window = min(self.window_size, len(historical_series))
                return historical_series.tail(window).mean()

        elif self.time_series_method == "rolling_median":
            # 滚动中位数
            if len(historical_series) >= self.min_samples:
                window = min(self.window_size, len(historical_series))
                return historical_series.tail(window).median()

        elif self.time_series_method == "exponential_smoothing":
            # 指数平滑
            if len(historical_series) >= 2:
                alpha = 2.0 / (self.window_size + 1)  # 自适应alpha
                ewm_mean = historical_series.ewm(alpha=alpha, adjust=False).mean()
                return ewm_mean.iloc[-1]

        return None

    def _cross_sectional_impute(
        self, historical_data: pd.DataFrame, current_time: pd.Timestamp, target_asset: str
    ) -> Optional[float]:
        """截面插补 - 每期独立计算组内统计量"""
        # 获取当前时间点的截面数据（只看历史）
        current_cross_section = historical_data.loc[current_time]

        if current_cross_section.empty:
            return None

        # 获取非缺失的资产
        available_assets = current_cross_section.dropna().index

        if len(available_assets) < self.min_samples:
            return None

        if self.cross_sectional_method == "group_median":
            # 分组中位数
            group_name = self._get_asset_group(target_asset)
            if group_name:
                group_assets = [a for a in available_assets if self._get_asset_group(a) == group_name]
                if len(group_assets) >= self.min_samples:
                    group_values = current_cross_section[group_assets]
                    return group_values.median()

        elif self.cross_sectional_method == "group_mean":
            # 分组均值
            group_name = self._get_asset_group(target_asset)
            if group_name:
                group_assets = [a for a in available_assets if self._get_asset_group(a) == group_name]
                if len(group_assets) >= self.min_samples:
                    group_values = current_cross_section[group_assets]
                    return group_values.mean()

        elif self.cross_sectional_method == "cross_sectional_median":
            # 截面中位数
            return current_cross_section[available_assets].median()

        elif self.cross_sectional_method == "cross_sectional_mean":
            # 截面均值
            return current_cross_section[available_assets].mean()

        return None

    def _model_impute(
        self, historical_data: pd.DataFrame, current_time: pd.Timestamp, target_asset: str
    ) -> Optional[float]:
        """模型插补 - 滚动训练 + 单步预测"""
        if self.model_method == "rolling_rf":
            return self._rolling_rf_impute(historical_data, current_time, target_asset)
        elif self.model_method == "rolling_knn":
            return self._rolling_knn_impute(historical_data, current_time, target_asset)
        return None

    def _rolling_rf_impute(
        self, historical_data: pd.DataFrame, current_time: pd.Timestamp, target_asset: str
    ) -> Optional[float]:
        """滚动随机森林插补"""
        # 获取历史数据
        target_series = historical_data[target_asset].dropna()

        if len(target_series) < self.window_size:
            return None

        # 准备训练数据（只使用历史数据）
        other_assets = [col for col in historical_data.columns if col != target_asset]

        # 构建特征矩阵
        X_train = []
        y_train = []

        for time_point in target_series.index:
            if time_point == current_time:
                continue  # 不使用当前时间点

            # 获取该时间点的特征
            features = []
            for asset in other_assets:
                if asset in historical_data.columns:
                    value = historical_data.loc[time_point, asset]
                    if pd.isna(value):
                        # 使用历史均值填充
                        hist_values = historical_data[asset].loc[:time_point].dropna()
                        value = hist_values.mean() if len(hist_values) > 0 else 0
                    features.append(value)

            if len(features) == len(other_assets):
                X_train.append(features)
                y_train.append(target_series[time_point])

        if len(X_train) < self.min_samples:
            return None

        # 训练模型
        X_train = np.array(X_train)
        y_train = np.array(y_train)

        try:
            rf = RandomForestRegressor(n_estimators=50, max_depth=5, random_state=42)
            rf.fit(X_train, y_train)

            # 预测当前时间点
            current_features = []
            for asset in other_assets:
                if asset in historical_data.columns:
                    value = historical_data.loc[current_time, asset]
                    if pd.isna(value):
                        # 使用历史均值填充
                        hist_values = historical_data[asset].loc[:current_time].dropna()
                        value = hist_values.mean() if len(hist_values) > 0 else 0
                    current_features.append(value)

            if len(current_features) == len(other_assets):
                prediction = rf.predict([current_features])[0]
                return prediction

        except Exception as e:
            warnings.warn(f"滚动RF插补失败: {e}")

        return None

    def _rolling_knn_impute(
        self, historical_data: pd.DataFrame, current_time: pd.Timestamp, target_asset: str
    ) -> Optional[float]:
        """滚动KNN插补"""
        # 获取历史数据
        target_series = historical_data[target_asset].dropna()

        if len(target_series) < self.window_size:
            return None

        # 准备训练数据
        other_assets = [col for col in historical_data.columns if col != target_asset]

        X_train = []
        y_train = []

        for time_point in target_series.index:
            if time_point == current_time:
                continue

            features = []
            for asset in other_assets:
                if asset in historical_data.columns:
                    value = historical_data.loc[time_point, asset]
                    if pd.isna(value):
                        hist_values = historical_data[asset].loc[:time_point].dropna()
                        value = hist_values.mean() if len(hist_values) > 0 else 0
                    features.append(value)

            if len(features) == len(other_assets):
                X_train.append(features)
                y_train.append(target_series[time_point])

        if len(X_train) < self.min_samples:
            return None

        # 训练KNN
        X_train = np.array(X_train)
        y_train = np.array(y_train)

        try:
            # 标准化
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)

            # KNN回归
            knn = NearestNeighbors(n_neighbors=min(5, len(X_train)))
            knn.fit(X_train_scaled)

            # 预测当前时间点
            current_features = []
            for asset in other_assets:
                if asset in historical_data.columns:
                    value = historical_data.loc[current_time, asset]
                    if pd.isna(value):
                        hist_values = historical_data[asset].loc[:current_time].dropna()
                        value = hist_values.mean() if len(hist_values) > 0 else 0
                    current_features.append(value)

            if len(current_features) == len(other_assets):
                current_features_scaled = scaler.transform([current_features])
                distances, indices = knn.kneighbors(current_features_scaled)

                # 距离加权平均
                weights = 1 / (distances[0] + 1e-10)
                weighted_values = y_train[indices[0]]
                prediction = np.sum(weighted_values * weighted_values) / np.sum(weights)
                return prediction

        except Exception as e:
            warnings.warn(f"滚动KNN插补失败: {e}")

        return None

    def _fallback_impute(self, asset_series: pd.Series) -> float:
        """回退插补方法"""
        # 使用历史均值
        historical_values = asset_series.dropna()
        if len(historical_values) > 0:
            return historical_values.mean()
        else:
            return 0.0

    def _add_missing_indicators(self, original_data: pd.DataFrame, imputed_data: pd.DataFrame) -> pd.DataFrame:
        """添加缺失指示变量控制MNAR"""
        result_data = imputed_data.copy()

        for asset in original_data.columns:
            missing_mask = original_data[asset].isnull()
            if missing_mask.any():
                indicator_name = f"{asset}_missing"
                result_data[indicator_name] = missing_mask.astype(int)
                self.missing_indicators[asset] = indicator_name

        return result_data

    def _create_group_mappings(self, X: pd.DataFrame) -> Dict[str, List[str]]:
        """创建分组映射"""
        mappings = {}

        if self.group_by == "industry":
            # 简化实现：随机分组
            industries = ["tech", "finance", "consumer", "industrial", "healthcare"]
            for asset in X.columns:
                industry = np.random.choice(industries)
                if industry not in mappings:
                    mappings[industry] = []
                mappings[industry].append(asset)

        elif self.group_by == "market_cap":
            # 按市值分组（简化）
            assets = X.columns
            n_assets = len(assets)

            large_cap = assets[: n_assets // 3]
            mid_cap = assets[n_assets // 3 : 2 * n_assets // 3]
            small_cap = assets[2 * n_assets // 3 :]

            mappings["large_cap"] = list(large_cap)
            mappings["mid_cap"] = list(mid_cap)
            mappings["small_cap"] = list(small_cap)

        elif self.group_by == "momentum":
            # 按动量分组（简化）
            assets = X.columns
            n_assets = len(assets)

            high_momentum = assets[: n_assets // 3]
            medium_momentum = assets[n_assets // 3 : 2 * n_assets // 3]
            low_momentum = assets[2 * n_assets // 3 :]

            mappings["high_momentum"] = list(high_momentum)
            mappings["medium_momentum"] = list(medium_momentum)
            mappings["low_momentum"] = list(low_momentum)

        return mappings

    def _get_asset_group(self, asset: str) -> Optional[str]:
        """获取资产所属分组"""
        for group_name, group_assets in self.group_mappings.items():
            if asset in group_assets:
                return group_name
        return None

    def validate_lookahead_free(self, original_data: pd.DataFrame, imputed_data: pd.DataFrame) -> Dict[str, Any]:
        """验证无前瞻偏差"""
        validation_result = {"is_lookahead_free": True, "violations": [], "validation_details": {}}

        # 检查时间顺序
        if not isinstance(original_data.index, pd.DatetimeIndex):
            validation_result["violations"].append("数据索引不是时间格式")
            validation_result["is_lookahead_free"] = False

        # 检查是否使用了未来信息
        missing_mask = original_data.isnull()

        for time_point in original_data.index:
            missing_assets = missing_mask.loc[time_point][missing_mask.loc[time_point]].index

            for asset in missing_assets:
                imputed_value = imputed_data.loc[time_point, asset]

                # 检查插补值是否异常接近未来值
                future_data = original_data.loc[time_point + pd.Timedelta(days=1) :, asset]

                if len(future_data) > 0:
                    future_mean = future_data.mean()
                    if not pd.isna(future_mean):
                        relative_diff = abs(imputed_value - future_mean) / (abs(future_mean) + 1e-10)

                        if relative_diff < 0.05:  # 异常接近
                            validation_result["violations"].append(
                                {
                                    "time": time_point,
                                    "asset": asset,
                                    "type": "future_information_leakage",
                                    "relative_diff": relative_diff,
                                }
                            )
                            validation_result["is_lookahead_free"] = False

        # 检查缺失指示变量
        for asset in original_data.columns:
            indicator_name = f"{asset}_missing"
            if indicator_name not in imputed_data.columns:
                validation_result["violations"].append(f"缺少缺失指示变量: {indicator_name}")
                validation_result["is_lookahead_free"] = False

        validation_result["validation_details"] = {
            "total_checks": len(original_data.columns) * len(original_data.index),
            "violations_found": len(validation_result["violations"]),
            "missing_indicators_added": len(self.missing_indicators),
        }

        return validation_result


class LookaheadFreeImputationPipeline:
    """无前瞻偏差插补流水线"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.imputer = LookaheadFreeImputer(**self.config)
        self.validation_results = []

    def fit_transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """拟合并变换"""
        # 拟合插补器
        self.imputer.fit(X)

        # 应用插补
        imputed_data = self.imputer.transform(X)

        # 验证无前瞻偏差
        validation = self.imputer.validate_lookahead_free(X, imputed_data)
        self.validation_results.append(validation)

        if not validation["is_lookahead_free"]:
            warnings.warn("检测到前瞻偏差违规，请检查插补方法")

        return imputed_data

    def get_validation_report(self) -> Dict[str, Any]:
        """获取验证报告"""
        if not self.validation_results:
            return {"message": "无验证记录"}

        latest_validation = self.validation_results[-1]

        return {
            "is_lookahead_free": latest_validation["is_lookahead_free"],
            "violations": latest_validation["violations"],
            "details": latest_validation["validation_details"],
            "recommendations": self._generate_recommendations(latest_validation),
        }

    def _generate_recommendations(self, validation: Dict[str, Any]) -> List[str]:
        """生成改进建议"""
        recommendations = []

        if validation["is_lookahead_free"]:
            recommendations.append("✅ 插补方法符合无前瞻偏差要求")
        else:
            recommendations.append("❌ 检测到前瞻偏差违规")

            for violation in validation["violations"]:
                if isinstance(violation, dict):
                    if violation["type"] == "future_information_leakage":
                        recommendations.append("- 建议减小插补窗口大小")
                        recommendations.append("- 避免使用全局统计量")
                else:
                    recommendations.append(f"- {violation}")

        return recommendations
