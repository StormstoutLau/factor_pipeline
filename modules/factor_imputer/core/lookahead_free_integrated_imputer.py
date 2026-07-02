# -*- coding: utf-8 -*-
"""
无前瞻偏差集成插补器
整合所有数据源，严格避免前瞻偏差
"""

import warnings
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from .base import BaseImputer
from .integrated_data_loader import IntegratedDataLoader


class LookaheadFreeIntegratedImputer(BaseImputer):
    """无前瞻偏差集成插补器"""

    def __init__(self, group_by="sw_industry", time_aware=True, validate_compliance=True, **params):
        super().__init__(**params)
        self.group_by = group_by
        self.time_aware = time_aware
        self.validate_compliance = validate_compliance

        # 集成数据加载器
        self.integrated_loader = IntegratedDataLoader()
        self.integrated_data = None

        # 缓存
        self.group_cache = {}
        self.strategy_cache = {}
        self.compliance_cache = {}

    def fit(self, X: pd.DataFrame, missing_info: Dict[str, Any] = None) -> "LookaheadFreeIntegratedImputer":
        """拟合集成插补器"""
        print("拟合无前瞻偏差集成插补器...")

        # 加载集成数据
        self.integrated_data = self.integrated_loader.load_all_integrated_data()

        # 验证数据时间顺序
        if not isinstance(X.index, pd.DatetimeIndex):
            warnings.warn("数据索引不是时间格式，可能导致前瞻偏差")

        # 预计算分组映射
        self._precompute_group_mappings(X)

        self.is_fitted = True
        print("集成插补器拟合完成")
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用无前瞻偏差集成插补"""
        if not self.is_fitted:
            raise ValueError("插补器尚未拟合，请先调用fit方法")

        print("执行无前瞻偏差集成插补...")

        # 确保数据按时间排序
        X_sorted = X.sort_index()
        X_imputed = X_sorted.copy()

        # 按时间顺序逐点处理
        for i, time_point in enumerate(X_sorted.index):
            if i % 100 == 0:
                print(f"处理进度: {i+1}/{len(X_sorted)} ({(i+1)/len(X_sorted)*100:.1f}%)")

            # 获取当前时间点及之前的历史数据
            historical_data = X_sorted.loc[:time_point]

            # 处理当前时间点的缺失值
            missing_mask = X_sorted.loc[time_point].isnull()
            if missing_mask.any():
                imputed_values = self._impute_time_point_integrated(historical_data, time_point, missing_mask)
                X_imputed.loc[time_point, missing_mask] = imputed_values

        # 添加缺失指示变量
        X_imputed = self._add_integrated_missing_indicators(X, X_imputed)

        # 验证合规性
        if self.validate_compliance:
            compliance_result = self._validate_compliance(X, X_imputed)
            if not compliance_result["is_compliant"]:
                warnings.warn(f"检测到前瞻偏差违规: {len(compliance_result['violations'])} 项")

        print("集成插补完成")
        return X_imputed

    def _precompute_group_mappings(self, X: pd.DataFrame) -> None:
        """预计算分组映射"""
        print("预计算分组映射...")

        enhanced_mappings = self.integrated_data["enhanced_mappings"]

        # 基础分组
        if self.group_by == "sw_industry":
            self.group_cache["industry"] = enhanced_mappings["industry_mapping"]
        elif self.group_by == "market_cap":
            self.group_cache["market_cap"] = enhanced_mappings["market_cap"]
        elif self.group_by == "index_groups":
            self.group_cache["index"] = enhanced_mappings["index_groups"]

        # 时间感知分组
        if self.time_aware:
            self.group_cache["listing_groups"] = enhanced_mappings.get("time_aware_groups", {}).get(
                "listing_groups", {}
            )
            self.group_cache["index_time_groups"] = enhanced_mappings.get("time_aware_groups", {}).get(
                "index_time_groups", {}
            )

        print(f"分组映射预计算完成: {list(self.group_cache.keys())}")

    def _impute_time_point_integrated(
        self, historical_data: pd.DataFrame, time_point: pd.Timestamp, missing_mask: pd.Series
    ) -> pd.Series:
        """集成的时间点插补"""
        missing_assets = missing_mask[missing_mask].index
        imputed_values = pd.Series(index=missing_assets, dtype=float)

        for asset in missing_assets:
            # 检查数据可用性
            if not self.integrated_loader.is_data_available_at_time(asset, time_point):
                # 数据不可用，不进行插补
                imputed_values[asset] = np.nan
                continue

            # 获取时间感知策略
            strategy = self.integrated_loader.get_time_aware_imputation_strategy(asset, time_point)

            # 1. 尝试时序插补（时间感知）
            ts_value = self._time_series_impute_integrated(historical_data[asset], time_point, strategy)
            if ts_value is not None:
                imputed_values[asset] = ts_value
                continue

            # 2. 尝试截面插补（集成分组）
            cs_value = self._cross_sectional_impute_integrated(historical_data, time_point, asset, strategy)
            if cs_value is not None:
                imputed_values[asset] = cs_value
                continue

            # 3. 尝试指数插补
            index_value = self._index_based_impute(historical_data, time_point, asset, strategy)
            if index_value is not None:
                imputed_values[asset] = index_value
                continue

            # 4. 回退方法
            imputed_values[asset] = self._fallback_impute_integrated(historical_data[asset], strategy)

        return imputed_values

    def _time_series_impute_integrated(
        self, asset_series: pd.Series, time_point: pd.Timestamp, strategy: Dict[str, Any]
    ) -> Optional[float]:
        """时间感知的时序插补"""
        # 获取当前时间点之前的数据
        historical_series = asset_series.loc[:time_point].dropna()

        if len(historical_series) < strategy["min_samples"]:
            return None

        window_size = strategy["window_size"]

        # 根据上市时间调整方法
        if strategy.get("use_historical_only", True):
            # 只使用历史数据的标准方法
            if len(historical_series) >= window_size:
                return historical_series.tail(window_size).mean()
            else:
                return historical_series.mean()

        return None

    def _cross_sectional_impute_integrated(
        self, historical_data: pd.DataFrame, time_point: pd.Timestamp, target_asset: str, strategy: Dict[str, Any]
    ) -> Optional[float]:
        """集成分组截面插补"""
        current_cross_section = historical_data.loc[time_point]
        available_assets = current_cross_section.dropna().index

        if len(available_assets) < strategy["min_samples"]:
            return None

        # 优先使用行业分组
        if strategy.get("prefer_industry", True):
            industry = self.integrated_loader.get_appropriate_group(target_asset, "sw_industry", time_point)
            if industry:
                industry_assets = [
                    asset
                    for asset in available_assets
                    if self.integrated_loader.get_appropriate_group(asset, "sw_industry", time_point) == industry
                ]

                if len(industry_assets) >= strategy["min_samples"]:
                    return current_cross_section[industry_assets].median()

        # 优先使用指数分组
        if strategy.get("prefer_index", False):
            index_code = strategy.get("index_code")
            if index_code and index_code in self.group_cache.get("index", {}):
                index_assets = self.group_cache["index"][index_code]
                available_index_assets = [asset for asset in available_assets if asset in index_assets]

                if len(available_index_assets) >= strategy["min_samples"]:
                    return current_cross_section[available_index_assets].median()

        # 回退到一般截面插补
        return current_cross_section[available_assets].median()

    def _index_based_impute(
        self, historical_data: pd.DataFrame, time_point: pd.Timestamp, target_asset: str, strategy: Dict[str, Any]
    ) -> Optional[float]:
        """基于指数成分的插补"""
        if not strategy.get("prefer_index", False):
            return None

        index_code = strategy.get("index_code")
        if not index_code:
            return None

        # 获取指数成分股的历史表现
        index_stocks = self.group_cache.get("index", {}).get(index_code, [])
        if not index_stocks:
            return None

        # 筛选可用的指数成分股
        available_index_stocks = []
        for stock in index_stocks:
            if (
                stock in historical_data.columns
                and self.integrated_loader.is_data_available_at_time(stock, time_point)
                and pd.notna(historical_data.loc[time_point, stock])
            ):
                available_index_stocks.append(stock)

        if len(available_index_stocks) < strategy["min_samples"]:
            return None

        # 使用指数成分股的中位数
        index_values = historical_data.loc[:time_point, available_index_stocks]

        # 计算目标资产在指数中的相对表现
        if target_asset in index_stocks:
            # 如果目标资产是指数成分，使用指数成分统计
            return index_values.mean().mean()
        else:
            # 如果不是指数成分，使用最相似的指数成分
            return index_values.mean().median()

    def _fallback_impute_integrated(self, asset_series: pd.Series, strategy: Dict[str, Any]) -> float:
        """集成回退插补方法"""
        historical_values = asset_series.dropna()

        if len(historical_values) > 0:
            # 根据策略调整回退方法
            if strategy.get("use_historical_only", True):
                return historical_values.mean()
            else:
                # 使用更保守的方法
                return historical_values.median()

        return 0.0

    def _add_integrated_missing_indicators(
        self, original_data: pd.DataFrame, imputed_data: pd.DataFrame
    ) -> pd.DataFrame:
        """添加集成缺失指示变量"""
        result_data = imputed_data.copy()

        # 1. 基础缺失指示变量
        for asset in original_data.columns:
            missing_mask = original_data[asset].isnull()
            if missing_mask.any():
                indicator_name = f"{asset}_missing"
                result_data[indicator_name] = missing_mask.astype(int)

        # 2. 停牌指示变量
        suspend_data = self.integrated_data["suspend_data"]
        for asset in original_data.columns:
            if asset in suspend_data:
                suspend_indicator_name = f"{asset}_suspended"
                suspend_indicator = []

                for time_point in original_data.index:
                    is_suspended = not self.integrated_loader.is_data_available_at_time(asset, time_point)
                    suspend_indicator.append(1 if is_suspended else 0)

                result_data[suspend_indicator_name] = suspend_indicator

        # 3. 上市时间指示变量
        list_date_mapping = self.integrated_data.get("list_date_mapping", {})
        for asset in original_data.columns:
            if asset in list_date_mapping:
                listing_indicator_name = f"{asset}_not_listed"
                listing_indicator = []

                for time_point in original_data.index:
                    list_date = list_date_mapping[asset]
                    not_listed = time_point < list_date
                    listing_indicator.append(1 if not_listed else 0)

                result_data[listing_indicator_name] = listing_indicator

        # 4. 指数成分指示变量
        index_groups = self.integrated_data.get("enhanced_mappings", {}).get("index_groups", {})
        for index_code, stocks in index_groups.items():
            index_indicator_name = f"index_{index_code}_member"
            index_indicator = []

            for time_point in original_data.index:
                # 检查该时间点哪些股票是指数成分
                current_stocks = []
                for asset in original_data.columns:
                    if asset in stocks and self.integrated_loader.is_data_available_at_time(asset, time_point):
                        current_stocks.append(asset)

                # 简化处理：如果有任何成分股数据，标记为1
                index_indicator.append(1 if len(current_stocks) > 0 else 0)

            result_data[index_indicator_name] = index_indicator

        return result_data

    def _validate_compliance(self, original_data: pd.DataFrame, imputed_data: pd.DataFrame) -> Dict[str, Any]:
        """验证无前瞻偏差合规性"""
        cache_key = f"{len(original_data)}_{len(original_data.columns)}"

        if cache_key in self.compliance_cache:
            return self.compliance_cache[cache_key]

        validation_result = self.integrated_loader.validate_lookahead_free_compliance(original_data, imputed_data)

        # 缓存结果
        self.compliance_cache[cache_key] = validation_result

        return validation_result

    def get_imputation_report(self, original_data: pd.DataFrame, imputed_data: pd.DataFrame) -> Dict[str, Any]:
        """获取插补报告"""
        report = {
            "data_info": {
                "shape": original_data.shape,
                "time_range": (original_data.index.min(), original_data.index.max()),
                "missing_rate": original_data.isnull().sum().sum() / original_data.shape[0] / original_data.shape[1],
            },
            "imputation_summary": {
                "total_imputed": imputed_data.isnull().sum().sum(),
                "imputation_rate": 1
                - imputed_data.isnull().sum().sum() / imputed_data.shape[0] / imputed_data.shape[1],
                "indicators_added": len(
                    [
                        col
                        for col in imputed_data.columns
                        if "_missing" in col or "_suspended" in col or "_not_listed" in col or "_member" in col
                    ]
                ),
            },
            "compliance_result": self._validate_compliance(original_data, imputed_data),
            "data_sources_used": list(self.integrated_data.keys()) if self.integrated_data else [],
            "grouping_method": self.group_by,
            "time_aware_enabled": self.time_aware,
        }

        return report

    def get_integrated_summary(self) -> Dict[str, Any]:
        """获取集成系统摘要"""
        if self.integrated_data:
            return self.integrated_loader.get_integrated_data_summary()
        else:
            return {"message": "数据未加载，请先调用fit方法"}
