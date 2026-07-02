# -*- coding: utf-8 -*-
"""
统一缓存数据加载器 — CachedDataLoader

将 FactorMatrixCache + PriceMatrixCache 封装为单一入口,
业务代码一处替换即可启用 L2 磁盘缓存。

设计:
  - 统一管理 cache_dir 和 enabled 状态
  - 接口兼容: get_pivoted_factors() / get_price_matrix() 与原始接口一致
  - 默认工厂使用真实 FactorPivotAdapter + PriceQuery,可注入 Fake 用于测试
  - 环境变量逃生舱 FACTOR_PIPELINE_CACHE=disabled 一键禁用
  - 统一管理 API: status() / clear_all() / invalidate_factor() / invalidate_price()

Usage (生产环境):
    loader = CachedDataLoader(
        db_path="factor_db.duckdb",
        cache_dir="./cache",
        enabled=True,
    )
    factor_data = loader.get_pivoted_factors(["PE", "PB"], start_date, end_date)
    price_data = loader.get_price_matrix(field="close", start_date, end_date)

Usage (测试环境):
    loader = CachedDataLoader(
        db_path="dummy.duckdb",
        cache_dir=tmp,
        factor_adapter_factory=lambda db: FakeFactorPivotAdapter(...),
        price_query_factory=lambda db: FakePriceQuery(...),
    )
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from .cache_manager import CacheManager
from .factor_cache import FactorMatrixCache
from .price_cache import PriceMatrixCache

logger = logging.getLogger(__name__)


# =============================================================================
# 默认工厂函数
# =============================================================================

def _default_factor_adapter_factory(db_path: str):
    """默认 FactorPivotAdapter 工厂。延迟导入避免循环依赖。"""
    from .factor_pivot import FactorPivotAdapter
    return FactorPivotAdapter(db_path)


def _default_price_query_factory(db_path: str):
    """默认 PriceQuery 工厂。延迟导入 Factor_DB 模块。"""
    # P1.2: Factor_DB 已 pip install -e ., 直接导入替代 sys.path hack
    from Factor_DB.query.price_query import PriceQuery
    return PriceQuery(db_path)


# =============================================================================
# CachedDataLoader
# =============================================================================

class CachedDataLoader:
    """统一缓存数据加载器。

    封装 FactorMatrixCache + PriceMatrixCache,提供单一入口。
    业务代码通过此类替换原始的 FactorPivotAdapter + PriceQuery。
    """

    def __init__(
        self,
        db_path: str,
        cache_dir: str,
        enabled: bool = True,
        code_version: str = "v2.2.0-cache",
        factor_adapter_factory: Optional[Callable[[str], Any]] = None,
        price_query_factory: Optional[Callable[[str], Any]] = None,
    ):
        """初始化缓存数据加载器。

        Args:
            db_path: DuckDB 数据库路径
            cache_dir: 缓存目录
            enabled: 是否启用缓存（受环境变量覆盖）
            code_version: 代码版本号
            factor_adapter_factory: 因子适配器工厂函数 (db_path) → adapter
                默认使用 FactorPivotAdapter
            price_query_factory: 价格查询器工厂函数 (db_path) → PriceQuery
                默认使用 PriceQuery
        """
        self.db_path = db_path
        self.cache_dir = cache_dir
        self._init_enabled = enabled
        self.code_version = code_version

        # 创建底层 adapter / query
        f_factory = factor_adapter_factory or _default_factor_adapter_factory
        p_factory = price_query_factory or _default_price_query_factory
        self.factor_adapter = f_factory(db_path)
        self.price_query = p_factory(db_path)

        # 创建两个缓存层,共享同一个 cache_dir
        self.factor_cache = FactorMatrixCache(
            self.factor_adapter, cache_dir=cache_dir,
            enabled=enabled, code_version=code_version,
        )
        self.price_cache = PriceMatrixCache(
            self.price_query, cache_dir=cache_dir,
            enabled=enabled, code_version=code_version,
        )

    # ── 启用状态 ──────────────────────────────

    @property
    def enabled(self) -> bool:
        """是否启用缓存（环境变量优先级最高）。"""
        # 两个底层缓存共享同一个 CacheManager 逻辑,任一即可
        return self.factor_cache.manager.enabled

    # ── 公开 API: 数据加载 ──────────────────────────────

    def get_pivoted_factors(
        self,
        factor_names: List[str],
        stock_codes: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, pd.DataFrame]:
        """获取 pivoted 因子数据（带缓存）。

        透明委托给 FactorMatrixCache,支持部分命中。

        Args:
            factor_names: 因子名称列表
            stock_codes: 股票代码列表 (None 表示全部)
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            {factor_name: DataFrame(stock_code × trade_date)}
        """
        return self.factor_cache.get_pivoted(
            factor_names, stock_codes=stock_codes,
            start_date=start_date, end_date=end_date,
        )

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

        透明委托给 PriceMatrixCache。

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
        return self.price_cache.get_price_matrix(
            field=field, stock_codes=stock_codes,
            start_date=start_date, end_date=end_date,
            adjust=adjust, as_of=as_of,
        )

    # ── 统一管理 API ──────────────────────────────

    def status(self) -> dict:
        """返回两个缓存的合并状态。

        Returns:
            {"factor_cache": {...}, "price_cache": {...}}
        """
        return {
            "factor_cache": self.factor_cache.status(),
            "price_cache": self.price_cache.status(),
        }

    def clear_all(self) -> None:
        """清空所有缓存（因子 + 价格）。

        注意: 两个缓存共享同一个 cache_dir,只需调用一次 clear_all。
        """
        # 由于共享 cache_dir,任一 clear_all 即可清空全部
        self.factor_cache.clear_all()

    def invalidate_factor(
        self,
        factor_name: str,
        stock_codes: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> None:
        """失效指定因子的缓存。"""
        self.factor_cache.invalidate(
            factor_name, stock_codes=stock_codes,
            start_date=start_date, end_date=end_date,
        )

    def invalidate_price(
        self,
        field: str = "close",
        stock_codes: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        adjust: str = "none",
        as_of: Optional[date] = None,
    ) -> None:
        """失效指定参数的价格缓存。"""
        self.price_cache.invalidate(
            field=field, stock_codes=stock_codes,
            start_date=start_date, end_date=end_date,
            adjust=adjust, as_of=as_of,
        )

    def verify_factor(
        self,
        factor_name: str,
        stock_codes: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ):
        """验证指定因子缓存一致性。"""
        return self.factor_cache.verify(
            factor_name, stock_codes=stock_codes,
            start_date=start_date, end_date=end_date,
        )

    def verify_price(
        self,
        field: str = "close",
        stock_codes: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        adjust: str = "none",
        as_of: Optional[date] = None,
    ):
        """验证价格缓存一致性。"""
        return self.price_cache.verify(
            field=field, stock_codes=stock_codes,
            start_date=start_date, end_date=end_date,
            adjust=adjust, as_of=as_of,
        )
