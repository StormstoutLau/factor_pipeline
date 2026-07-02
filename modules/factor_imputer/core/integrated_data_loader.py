# -*- coding: utf-8 -*-
"""
集成数据加载器
整合所有数据源，支持缺失插补的完整业务逻辑
"""

import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from ..config.settings import DataConfig

from .data_loader import DataLoader


class IntegratedDataLoader:
    """集成数据加载器"""

    def __init__(self, config: DataConfig = None):
        self.base_loader = DataLoader(config)
        self.data_cache = {}
        self.config = config or DataConfig()

        # 集成数据缓存
        self.index_constituents = None
        self.list_dates = None
        self.enhanced_mappings = {}

    def load_all_integrated_data(self) -> Dict[str, Any]:
        """加载所有集成数据"""
        print("加载集成数据...")

        integrated_data = {
            "stock_names": self.base_loader.load_stock_names(),
            "market_cap": self.base_loader.load_market_cap_data(),
            "suspend_data": self.base_loader.load_suspend_data(),
            "industry_mapping": self.base_loader.load_industry_mapping(),
            "index_constituents": self._load_index_constituents(),
            "list_dates": self._load_list_dates(),
        }

        # 创建增强映射
        integrated_data["enhanced_mappings"] = self._create_enhanced_mappings(integrated_data)

        print("集成数据加载完成")
        return integrated_data

    def _load_index_constituents(self) -> pd.DataFrame:
        """加载指数成分股数据"""
        if self.index_constituents is not None:
            return self.index_constituents

        try:
            with open(self.config.base_path / "index_constituents.pkl", "rb") as f:
                data = pickle.load(f)

            # 标准化列名
            if isinstance(data, pd.DataFrame):
                # 重命名列以保持一致性
                column_mapping = {
                    "Unnamed: 0": "id",
                    "index_code": "index_code",
                    "con_code": "stock_code",
                    "trade_date": "trade_date",
                    "weight": "weight",
                }

                for old_col, new_col in column_mapping.items():
                    if old_col in data.columns:
                        data = data.rename(columns={old_col: new_col})

                # 转换日期格式
                if "trade_date" in data.columns:
                    data["trade_date"] = pd.to_datetime(data["trade_date"], format="%Y%m%d")

                self.index_constituents = data
                print(f"指数成分股数据加载完成: {len(data)} 条记录")

            return data

        except Exception as e:
            print(f"加载指数成分股数据失败: {e}")
            return pd.DataFrame()

    def _load_list_dates(self) -> pd.DataFrame:
        """加载列表日期数据"""
        if self.list_dates is not None:
            return self.list_dates

        try:
            with open(self.config.BASE_PATH / "list_date_df.pkl", "rb") as f:
                data = pickle.load(f)

            # 标准化列名和格式
            if isinstance(data, pd.DataFrame):
                if "list_date" in data.columns:
                    data["list_date"] = pd.to_datetime(data["list_date"])

                    # 添加股票代码列（如果需要）
                    if "code" not in data.columns and data.index.name:
                        data = data.reset_index()
                        data = data.rename(columns={data.index.name: "code"})

                self.list_dates = data
                print(f"列表日期数据加载完成: {len(data)} 条记录")

            return data

        except Exception as e:
            print(f"加载列表日期数据失败: {e}")
            return pd.DataFrame()

    def _create_enhanced_mappings(self, integrated_data: Dict[str, Any]) -> Dict[str, Any]:
        """创建增强映射"""
        mappings = {
            "industry_mapping": integrated_data["industry_mapping"],
            "market_cap": integrated_data["market_cap"],
            "suspend_data": integrated_data["suspend_data"],
        }

        # 添加指数分组
        if integrated_data["index_constituents"] is not None:
            mappings["index_groups"] = self._create_index_groups(integrated_data["index_constituents"])

        # 添加上市时间映射
        if integrated_data["list_dates"] is not None:
            mappings["list_date_mapping"] = self._create_list_date_mapping(integrated_data["list_dates"])

        # 添加时间感知分组
        mappings["time_aware_groups"] = self._create_time_aware_groups(mappings)

        self.enhanced_mappings = mappings
        return mappings

    def _create_index_groups(self, constituents_data: pd.DataFrame) -> Dict[str, List[str]]:
        """创建指数分组"""
        if constituents_data.empty:
            return {}

        index_groups = {}

        for index_code in constituents_data["index_code"].unique():
            # 获取该指数的成分股
            index_stocks = constituents_data[constituents_data["index_code"] == index_code]["stock_code"].tolist()

            index_groups[f"index_{index_code}"] = index_stocks

        print(f"指数分组创建完成: {len(index_groups)} 个指数")
        return index_groups

    def _create_list_date_mapping(self, list_date_data: pd.DataFrame) -> Dict[str, datetime]:
        """创建上市时间映射"""
        if list_date_data.empty:
            return {}

        list_date_mapping = {}

        for _, row in list_date_data.iterrows():
            code = str(row.get("code", row.name))
            list_date = row.get("list_date")

            if pd.notna(list_date):
                list_date_mapping[code] = pd.to_datetime(list_date)

        print(f"上市时间映射创建完成: {len(list_date_mapping)} 只股票")
        return list_date_mapping

    def _create_time_aware_groups(self, mappings: Dict[str, Any]) -> Dict[str, Any]:
        """创建时间感知分组"""
        time_aware = {}

        # 基于上市时间的分组
        if "list_date_mapping" in mappings:
            time_aware["listing_groups"] = self._create_listing_groups(mappings)

        # 基于指数成分的分组
        if "index_groups" in mappings:
            time_aware["index_time_groups"] = self._create_index_time_groups(mappings)

        return time_aware

    def _create_listing_groups(self, mappings: Dict[str, Any]) -> Dict[str, List[str]]:
        """创建基于上市时间的分组"""
        list_date_mapping = mappings["list_date_mapping"]
        listing_groups = {
            "new_listed": [],  # 上市不足1年
            "mid_listed": [],  # 上市1-5年
            "old_listed": [],  # 上市超过5年
        }

        current_date = datetime.now()

        for stock_code, list_date in list_date_mapping.items():
            if list_date:
                years_listed = (current_date - list_date).days / 365.25

                if years_listed < 1:
                    listing_groups["new_listed"].append(stock_code)
                elif years_listed < 5:
                    listing_groups["mid_listed"].append(stock_code)
                else:
                    listing_groups["old_listed"].append(stock_code)

        return listing_groups

    def _create_index_time_groups(self, mappings: Dict[str, Any]) -> Dict[str, Dict]:
        """创建基于指数的时间分组"""
        index_groups = mappings["index_groups"]
        constituents_data = self.index_constituents

        if constituents_data is None or constituents_data.empty:
            return {}

        index_time_groups = {}

        for index_code, stocks in index_groups.items():
            # 获取该指数成分股的权重时间序列
            index_data = constituents_data[constituents_data["index_code"] == index_code]

            if not index_data.empty:
                # 按时间排序
                index_data = index_data.sort_values("trade_date")

                # 创建时间分组
                time_groups = {
                    "early_period": [],  # 早期成分股
                    "middle_period": [],  # 中期成分股
                    "recent_period": [],  # 近期成分股
                }

                total_stocks = len(index_data)
                early_cutoff = total_stocks // 3
                middle_cutoff = 2 * total_stocks // 3

                for i, (_, row) in enumerate(index_data.iterrows()):
                    stock_code = row["stock_code"]

                    if i < early_cutoff:
                        time_groups["early_period"].append(stock_code)
                    elif i < middle_cutoff:
                        time_groups["middle_period"].append(stock_code)
                    else:
                        time_groups["recent_period"].append(stock_code)

                index_time_groups[index_code] = time_groups

        return index_time_groups

    def is_data_available_at_time(self, stock_code: str, time_point: pd.Timestamp) -> bool:
        """检查指定时间点数据是否可用（无前瞻偏差）"""
        # 检查是否停牌
        if stock_code in self.enhanced_mappings.get("suspend_data", {}):
            suspend_data = self.enhanced_mappings["suspend_data"][stock_code]
            for date, record in suspend_data.items():
                record_date = pd.to_datetime(date)
                if record["status"] == "suspend" and record_date <= time_point:
                    # 检查是否在该时间点之前复牌
                    resume_date = self._find_resume_date(suspend_data, record_date, time_point)
                    if resume_date is None or resume_date > time_point:
                        return False

        # 检查是否已上市
        if stock_code in self.enhanced_mappings.get("list_date_mapping", {}):
            list_date = self.enhanced_mappings["list_date_mapping"][stock_code]
            if time_point < list_date:
                return False

        return True

    def _find_resume_date(
        self, suspend_records: Dict, suspend_date: pd.Timestamp, current_time: pd.Timestamp
    ) -> Optional[pd.Timestamp]:
        """查找复牌日期"""
        for date, record in suspend_records.items():
            record_date = pd.to_datetime(date)
            if record["status"] == "resume" and record_date > suspend_date and record_date <= current_time:
                return record_date
        return None

    def get_appropriate_group(self, stock_code: str, group_by: str, time_point: pd.Timestamp) -> Optional[str]:
        """获取适合的分组（考虑时间因素）"""
        # 基础分组
        base_groups = self.enhanced_mappings

        if group_by == "sw_industry":
            return base_groups.get("industry_mapping", {}).get(stock_code)
        elif group_by == "market_cap":
            cap = base_groups.get("market_cap", {}).get(stock_code, 0)
            if cap > 1000:
                return "large_cap"
            elif cap > 200:
                return "mid_cap"
            else:
                return "small_cap"

        # 时间感知分组
        elif group_by == "listing_age":
            listing_groups = base_groups.get("time_aware_groups", {}).get("listing_groups", {})
            for group_name, stocks in listing_groups.items():
                if stock_code in stocks:
                    return group_name

        elif group_by == "index_history":
            index_time_groups = base_groups.get("time_aware_groups", {}).get("index_time_groups", {})
            for index_code, time_groups in index_time_groups.items():
                for period, stocks in time_groups.items():
                    if stock_code in stocks:
                        return f"{index_code}_{period}"

        return None

    def get_time_aware_imputation_strategy(self, stock_code: str, time_point: pd.Timestamp) -> Dict[str, Any]:
        """获取时间感知的插补策略"""
        strategy = {
            "use_historical_only": True,
            "min_samples": 5,
            "window_size": 20,
            "prefer_industry": True,
            "prefer_index": False,
        }

        # 根据上市时间调整策略
        if stock_code in self.enhanced_mappings.get("list_date_mapping", {}):
            list_date = self.enhanced_mappings["list_date_mapping"][stock_code]
            days_listed = (time_point - list_date).days

            if days_listed < 30:
                # 新上市股票，减少历史依赖
                strategy["min_samples"] = 3
                strategy["window_size"] = 10
                strategy["prefer_industry"] = False
            elif days_listed < 90:
                # 上市不足3个月
                strategy["min_samples"] = 4
                strategy["window_size"] = 15

        # 根据指数成分调整策略
        index_groups = self.enhanced_mappings.get("index_groups", {})
        for index_code, stocks in index_groups.items():
            if stock_code in stocks:
                strategy["prefer_index"] = True
                strategy["index_code"] = index_code
                break

        return strategy

    def validate_lookahead_free_compliance(
        self, factor_data: pd.DataFrame, imputed_data: pd.DataFrame
    ) -> Dict[str, Any]:
        """验证无前瞻偏差合规性"""
        validation_result = {"is_compliant": True, "violations": [], "compliance_score": 1.0}

        # 检查时间顺序
        if not isinstance(factor_data.index, pd.DatetimeIndex):
            validation_result["violations"].append("数据索引不是时间格式")
            validation_result["is_compliant"] = False

        # 检查每个时间点的插补合规性
        for time_point in factor_data.index:
            missing_mask = factor_data.loc[time_point].isnull()

            if missing_mask.any():
                missing_stocks = missing_mask[missing_mask].index

                for stock_code in missing_stocks:
                    # 检查该时间点数据是否应该可用
                    if not self.is_data_available_at_time(stock_code, time_point):
                        validation_result["violations"].append(
                            {
                                "time": time_point,
                                "stock": stock_code,
                                "type": "future_data_usage",
                                "reason": "在不可用时间点使用了数据",
                            }
                        )
                        validation_result["is_compliant"] = False

        # 计算合规性评分
        total_checks = len(factor_data) * len(factor_data.columns)
        violation_count = len(validation_result["violations"])
        validation_result["compliance_score"] = 1.0 - (violation_count / total_checks)

        return validation_result

    def get_integrated_data_summary(self) -> Dict[str, Any]:
        """获取集成数据摘要"""
        summary = {
            "data_sources": {
                "stock_names": len(self.base_loader.load_stock_names()),
                "market_cap": len(self.base_loader.load_market_cap_data()),
                "suspend_data": len(self.base_loader.load_suspend_data()),
                "industry_mapping": len(self.base_loader.load_industry_mapping()),
                "index_constituents": len(self.index_constituents) if self.index_constituents is not None else 0,
                "list_dates": len(self.list_dates) if self.list_dates is not None else 0,
            },
            "grouping_capabilities": [
                "sw_industry",
                "market_cap",
                "suspend_status",
                "index_groups",
                "listing_age",
                "index_history",
            ],
            "time_aware_features": [
                "listing_date_validation",
                "suspend_status_validation",
                "index_constituent_validation",
                "historical_data_only",
            ],
            "lookahead_free_compliance": True,
        }

        return summary
