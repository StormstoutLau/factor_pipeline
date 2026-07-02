# -*- coding: utf-8 -*-
"""
数据加载器
分析pkl数据结构并提供兼容接口
"""

import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd

from ..config.settings import DataConfig


class DataLoader:
    """数据加载器"""

    def __init__(self, config: DataConfig = None):
        self.data_cache = {}
        self.config = config or DataConfig()

    def load_stock_names(self) -> Dict[str, str]:
        """加载股票名称数据"""
        if "stock_names" not in self.data_cache:
            try:
                with open(self.config.stock_names_path, "rb") as f:
                    data = pickle.load(f)

                # 分析数据结构并标准化
                stock_names = self._parse_stock_names(data)
                self.data_cache["stock_names"] = stock_names

            except Exception as e:
                print(f"加载股票名称数据失败: {e}")
                self.data_cache["stock_names"] = {}

        return self.data_cache["stock_names"]

    def load_market_cap_data(self) -> Dict[str, float]:
        """加载市值数据"""
        if "market_cap" not in self.data_cache:
            try:
                with open(self.config.market_cap_path, "rb") as f:
                    data = pickle.load(f)

                # 分析数据结构并标准化
                market_cap = self._parse_market_cap_data(data)
                self.data_cache["market_cap"] = market_cap

            except Exception as e:
                print(f"加载市值数据失败: {e}")
                self.data_cache["market_cap"] = {}

        return self.data_cache["market_cap"]

    def load_suspend_data(self) -> Dict[str, Dict]:
        """加载停牌数据"""
        if "suspend_data" not in self.data_cache:
            try:
                with open(self.config.suspend_data_path, "rb") as f:
                    data = pickle.load(f)

                # 分析数据结构并标准化
                suspend_data = self._parse_suspend_data(data)
                self.data_cache["suspend_data"] = suspend_data

            except Exception as e:
                print(f"加载停牌数据失败: {e}")
                self.data_cache["suspend_data"] = {}

        return self.data_cache["suspend_data"]

    def load_industry_mapping(self) -> Dict[str, str]:
        """加载行业映射数据"""
        if "industry_mapping" not in self.data_cache:
            try:
                with open(self.config.industry_path, "rb") as f:
                    data = pickle.load(f)

                # 分析数据结构并标准化
                industry_mapping = self._parse_industry_mapping(data)
                self.data_cache["industry_mapping"] = industry_mapping

            except Exception as e:
                print(f"加载行业映射数据失败: {e}")
                self.data_cache["industry_mapping"] = {}

        return self.data_cache["industry_mapping"]

    def _parse_stock_names(self, data) -> Dict[str, str]:
        """解析股票名称数据结构"""
        stock_names = {}

        # 情况1: DataFrame格式
        if isinstance(data, pd.DataFrame):
            if "code" in data.columns and "name" in data.columns:
                # 标准格式：code, name列
                stock_names = dict(zip(data["code"], data["name"]))
            elif len(data.columns) == 2:
                # 两列格式，假设第一列是代码，第二列是名称
                stock_names = dict(zip(data.iloc[:, 0], data.iloc[:, 1]))
            else:
                # 多列格式，使用索引作为代码
                for idx, row in data.iterrows():
                    stock_names[str(idx)] = str(row.iloc[0]) if len(row) > 0 else str(idx)

        # 情况2: 字典格式
        elif isinstance(data, dict):
            stock_names = {str(k): str(v) for k, v in data.items()}

        # 情况3: Series格式
        elif isinstance(data, pd.Series):
            stock_names = {str(idx): str(val) for idx, val in data.items()}

        # 情况4: 列表格式
        elif isinstance(data, (list, tuple)):
            if len(data) > 0 and isinstance(data[0], (list, tuple)):
                # 二维列表
                stock_names = {str(item[0]): str(item[1]) if len(item) > 1 else str(item[0]) for item in data}
            else:
                # 一维列表，使用值作为名称
                stock_names = {str(item): str(item) for item in data}

        print(f"股票名称数据解析完成，共 {len(stock_names)} 只股票")
        return stock_names

    def _parse_market_cap_data(self, data) -> Dict[str, float]:
        """解析市值数据结构"""
        market_cap = {}

        # 情况1: DataFrame格式
        if isinstance(data, pd.DataFrame):
            if "code" in data.columns and "market_value" in data.columns:
                # 标准格式：code, market_value列
                market_cap = dict(zip(data["code"], data["market_value"]))
            elif "ts_code" in data.columns and "total_mv" in data.columns:
                # Tushare格式：ts_code, total_mv列
                market_cap = dict(zip(data["ts_code"], data["total_mv"]))
            elif len(data.columns) == 2:
                # 两列格式
                market_cap = dict(zip(data.iloc[:, 0], data.iloc[:, 1]))
            else:
                # 多列格式，假设第一列是代码，最后一列是市值
                market_cap = dict(zip(data.iloc[:, 0], data.iloc[:, -1]))

        # 情况2: 字典格式
        elif isinstance(data, dict):
            market_cap = {str(k): float(v) for k, v in data.items()}

        # 情况3: Series格式
        elif isinstance(data, pd.Series):
            market_cap = {str(idx): float(val) for idx, val in data.items()}

        # 情况4: 多时间点市值数据
        elif isinstance(data, pd.DataFrame) and "date" in data.columns:
            # 取最新时间的市值
            latest_data = data.sort_values("date").iloc[-1]
            for col in data.columns:
                if col not in ["date", "code", "ts_code"]:
                    # 假设列名是股票代码
                    market_cap[str(col)] = float(latest_data[col])

        print(f"市值数据解析完成，共 {len(market_cap)} 只股票")
        return market_cap

    def _parse_suspend_data(self, data) -> Dict[str, Dict]:
        """解析停牌数据结构"""
        suspend_data = {}

        # 情况1: DataFrame格式
        if isinstance(data, pd.DataFrame):
            if "code" in data.columns and "suspend_date" in data.columns:
                # 标准格式：code, suspend_date, resume_date
                for idx, row in data.iterrows():
                    code = str(row["code"])
                    if code not in suspend_data:
                        suspend_data[code] = {}

                    suspend_date = str(row["suspend_date"])
                    resume_date = str(row["resume_date"]) if pd.notna(row.get("resume_date")) else None

                    suspend_data[code][suspend_date] = {"status": "suspend", "reason": row.get("reason", "未知")}

                    if resume_date:
                        suspend_data[code][resume_date] = {"status": "resume", "reason": row.get("reason", "复牌")}

            elif "ts_code" in data.columns:
                # Tushare格式
                for idx, row in data.iterrows():
                    code = str(row["ts_code"])
                    if code not in suspend_data:
                        suspend_data[code] = {}

                    suspend_date = str(row["suspend_date"])
                    suspend_data[code][suspend_date] = {
                        "status": "suspend",
                        "reason": row.get("suspend_reason", "未知"),
                    }

        # 情况2: 字典格式
        elif isinstance(data, dict):
            for code, records in data.items():
                code = str(code)
                suspend_data[code] = {}

                if isinstance(records, dict):
                    # 标准字典格式
                    for date, record in records.items():
                        date = str(date)
                        if isinstance(record, dict):
                            suspend_data[code][date] = record
                        else:
                            suspend_data[code][date] = {
                                "status": "suspend" if "suspend" in str(record).lower() else "resume",
                                "reason": str(record),
                            }

                elif isinstance(records, (list, tuple)):
                    # 列表格式
                    for record in records:
                        if isinstance(record, dict):
                            date = str(record.get("date", ""))
                            suspend_data[code][date] = record

        # 情况3: 多时间点停牌状态DataFrame
        elif isinstance(data, pd.DataFrame) and "date" in data.columns:
            # 宽表格式：日期为索引，股票代码为列
            for col in data.columns:
                if col not in ["date"]:
                    code = str(col)
                    suspend_data[code] = {}

                    for idx, row in data.iterrows():
                        date = str(row["date"])
                        status = row[col]

                        if pd.notna(status) and status != 0:
                            suspend_data[code][date] = {"status": "suspend", "reason": "停牌"}

        print(f"停牌数据解析完成，共 {len(suspend_data)} 只股票有停牌记录")
        return suspend_data

    def _parse_industry_mapping(self, data) -> Dict[str, str]:
        """解析行业映射数据结构"""
        industry_mapping = {}

        # 情况1: DataFrame格式
        if isinstance(data, pd.DataFrame):
            if "code" in data.columns and "industry" in data.columns:
                # 标准格式：code, industry列
                industry_mapping = dict(zip(data["code"], data["industry"]))
            elif "ts_code" in data.columns and "industry_name" in data.columns:
                # Tushare格式：ts_code, industry_name列
                industry_mapping = dict(zip(data["ts_code"], data["industry_name"]))
            elif "symbol" in data.columns and "sw_name" in data.columns:
                # 申万格式：symbol, sw_name列
                industry_mapping = dict(zip(data["symbol"], data["sw_name"]))
            elif len(data.columns) == 2:
                # 两列格式
                industry_mapping = dict(zip(data.iloc[:, 0], data.iloc[:, 1]))
            else:
                # 多列格式，假设第一列是代码，第二列是行业
                industry_mapping = dict(zip(data.iloc[:, 0], data.iloc[:, 1]))

        # 情况2: 字典格式
        elif isinstance(data, dict):
            industry_mapping = {str(k): str(v) for k, v in data.items()}

        # 情况3: Series格式
        elif isinstance(data, pd.Series):
            industry_mapping = {str(idx): str(val) for idx, val in data.items()}

        # 情况4: 多级行业分类
        elif isinstance(data, pd.DataFrame) and "level" in data.columns:
            # 多级行业分类，取一级分类
            level1_data = data[data["level"] == 1]
            industry_mapping = dict(zip(level1_data["code"], level1_data["industry"]))

        print(f"行业映射数据解析完成，共 {len(industry_mapping)} 只股票")
        return industry_mapping

    def get_data_structure_info(self) -> Dict[str, Any]:
        """获取数据结构信息"""
        info = {}

        try:
            with open(self.config.stock_names_path, "rb") as f:
                data = pickle.load(f)
                info["stock_name"] = {
                    "type": type(data).__name__,
                    "shape": (
                        data.shape if hasattr(data, "shape") else len(data) if hasattr(data, "__len__") else "unknown"
                    ),
                    "columns": list(data.columns) if hasattr(data, "columns") else "no columns",
                }
        except (OSError, pickle.PickleError):
            info["stock_name"] = {"error": "cannot load file"}

        try:
            with open(self.config.market_cap_path, "rb") as f:
                data = pickle.load(f)
                info["market_cap"] = {
                    "type": type(data).__name__,
                    "shape": (
                        data.shape if hasattr(data, "shape") else len(data) if hasattr(data, "__len__") else "unknown"
                    ),
                    "columns": list(data.columns) if hasattr(data, "columns") else "no columns",
                }
        except (OSError, pickle.PickleError):
            info["market_cap"] = {"error": "cannot load file"}

        try:
            with open(self.config.suspend_data_path, "rb") as f:
                data = pickle.load(f)
                info["suspend_data"] = {
                    "type": type(data).__name__,
                    "shape": (
                        data.shape if hasattr(data, "shape") else len(data) if hasattr(data, "__len__") else "unknown"
                    ),
                    "columns": list(data.columns) if hasattr(data, "columns") else "no columns",
                }
        except (OSError, pickle.PickleError):
            info["suspend_data"] = {"error": "cannot load file"}

        try:
            with open(self.config.industry_path, "rb") as f:
                data = pickle.load(f)
                info["industry_mapping"] = {
                    "type": type(data).__name__,
                    "shape": (
                        data.shape if hasattr(data, "shape") else len(data) if hasattr(data, "__len__") else "unknown"
                    ),
                    "columns": list(data.columns) if hasattr(data, "columns") else "no columns",
                }
        except (OSError, pickle.PickleError):
            info["industry_mapping"] = {"error": "cannot load file"}

        return info

    def clear_cache(self):
        """清空缓存"""
        self.data_cache.clear()
        print("数据缓存已清空")
