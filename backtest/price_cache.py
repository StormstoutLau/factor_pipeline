# -*- coding: utf-8 -*-
"""
价格矩阵缓存 — PriceMatrixCache

在 PriceQuery.get_price_matrix() 之上增加 L2 磁盘缓存层。

缓存策略:
  - 首次调用: 走 PriceQuery,存入 CacheManager
  - 再次调用: 命中缓存,跳过 DB 查询
  - source_signature 包含 db_loaded_at_max,用于 staleness 追溯
  - 数据指纹校验防止文件篡改

失效策略:
  - 显式 invalidate(field, start_date, end_date)
  - clear_all() 清空所有
  - 环境变量 FACTOR_PIPELINE_CACHE=disabled 全局禁用
  - 不做 TTL 过期（数据不变就不该失效）

Usage:
    pq = PriceQuery("factor_db.duckdb")
    cache = PriceMatrixCache(pq, cache_dir="./cache", enabled=True)
    matrix = cache.get_price_matrix(field="close", start_date=date(2024,1,1))
    # 第一次: 走 DB
    matrix2 = cache.get_price_matrix(field="close", start_date=date(2024,1,1))
    # 第二次: 命中缓存
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd

from .cache_manager import CacheKey, CacheManager

logger = logging.getLogger(__name__)


class PriceMatrixCache:
    """价格矩阵 L2 磁盘缓存。

    包装 PriceQuery.get_price_matrix(),透明缓存结果。
    """

    def __init__(
        self,
        price_query,
        cache_dir: str,
        enabled: bool = True,
        code_version: str = "v2.2.0-cache",
    ):
        """初始化价格矩阵缓存。

        Args:
            price_query: PriceQuery 实例（或兼容接口）
            cache_dir: 缓存目录
            enabled: 是否启用（受环境变量覆盖）
            code_version: 代码版本号
        """
        self.pq = price_query
        self.manager = CacheManager(
            cache_dir=cache_dir, enabled=enabled, code_version=code_version,
        )

    # ── 公开 API ──────────────────────────────

    def get_price_matrix(
        self,
        field: str = "close",
        stock_codes: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        adjust: str = "none",
        as_of: Optional[date] = None,
    ) -> pd.DataFrame:
        """获取价格矩阵（带缓存）。

        首次调用走 PriceQuery,后续调用命中缓存。
        返回格式与 PriceQuery.get_price_matrix 一致: DataFrame(dates × stocks)。

        Args:
            field: 价格字段 (close/open/high/low/volume/amount)
            stock_codes: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            adjust: 复权方式
            as_of: PIT 截止时间

        Returns:
            价格矩阵 DataFrame(index=dates, columns=stocks)
        """
        key = self._make_key(field, stock_codes, start_date, end_date, adjust, as_of)

        # 尝试命中缓存
        cached = self.manager.get(key)
        if cached is not None:
            return cached

        # 缓存未命中,走 PriceQuery
        df = self.pq.get_price_matrix(
            field=field, stock_codes=stock_codes,
            start_date=start_date, end_date=end_date,
            adjust=adjust, as_of=as_of,
        )

        # 空结果不缓存
        if df.empty:
            return df

        # 获取 db_loaded_at_max 用于 source_signature
        db_loaded_at_max = self._get_loaded_at_max()

        # 构建来源签名
        source_sig = {
            "field": field,
            "stock_codes": stock_codes or "ALL",
            "start_date": str(start_date) if start_date else "MIN",
            "end_date": str(end_date) if end_date else "MAX",
            "adjust": adjust,
            "as_of": str(as_of) if as_of else "LATEST",
            "db_loaded_at_max": db_loaded_at_max,
            "query_type": "price_matrix",
        }

        # 存入缓存
        self.manager.set(key, df, source_signature=source_sig)

        return df

    def invalidate(
        self,
        field: str = "close",
        stock_codes: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        adjust: str = "none",
        as_of: Optional[date] = None,
    ) -> None:
        """失效指定参数的缓存。"""
        key = self._make_key(field, stock_codes, start_date, end_date, adjust, as_of)
        self.manager.invalidate(key)

    def clear_all(self) -> None:
        """清空所有缓存。"""
        self.manager.clear_all()

    def status(self) -> dict:
        """返回缓存状态。"""
        return self.manager.status()

    def verify(
        self,
        field: str = "close",
        stock_codes: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        adjust: str = "none",
        as_of: Optional[date] = None,
    ):
        """验证缓存一致性。"""
        key = self._make_key(field, stock_codes, start_date, end_date, adjust, as_of)
        return self.manager.verify(key)

    # ── 内部方法 ──────────────────────────────

    def _make_key(
        self,
        field: str,
        stock_codes: Optional[List[str]],
        start_date: Optional[date],
        end_date: Optional[date],
        adjust: str,
        as_of: Optional[date],
    ) -> CacheKey:
        """构建缓存键。

        namespace: price_matrix
        identifier: field + date_range + stock_hash + adjust + as_of
        version: v1
        """
        stock_part = "ALL" if stock_codes is None else self._hash_stock_codes(stock_codes)
        start_part = str(start_date) if start_date else "MIN"
        end_part = str(end_date) if end_date else "MAX"
        as_of_part = str(as_of) if as_of else "LATEST"
        identifier = f"{field}_{start_part}_{end_part}_{stock_part}_{adjust}_{as_of_part}"
        return CacheKey(
            namespace="price_matrix",
            identifier=identifier,
            version="v1",
        )

    @staticmethod
    def _hash_stock_codes(stock_codes: List[str]) -> str:
        """对股票代码列表生成短哈希。"""
        raw = ",".join(sorted(stock_codes))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]

    def _get_loaded_at_max(self) -> str:
        """从 PriceQuery 获取 MAX(loaded_at)。

        如果 PriceQuery 不支持此方法,返回 "unknown"。
        """
        try:
            if hasattr(self.pq, "get_loaded_at_max"):
                return self.pq.get_loaded_at_max()
        except Exception as e:
            logger.warning(f"获取 loaded_at_max 失败: {e}")
        return "unknown"
