# -*- coding: utf-8 -*-
"""
因子矩阵缓存 — FactorMatrixCache

在 FactorPivotAdapter.get_pivoted() 之上增加 L2 磁盘缓存层。

设计:
  - 每个因子独立缓存（不同因子有不同日期范围/股票覆盖）
  - 支持部分命中：仅查询未缓存的因子
  - source_signature 包含 db_loaded_at_max,用于 staleness 追溯
  - 数据指纹校验防止文件篡改

失效策略:
  - 显式 invalidate(factor_name, start_date, end_date)
  - clear_all() 清空所有
  - 环境变量 FACTOR_PIPELINE_CACHE=disabled 全局禁用
  - 不做 TTL 过期（数据不变就不该失效）

Usage:
    adapter = FactorPivotAdapter('factor_db.duckdb')
    cache = FactorMatrixCache(adapter, cache_dir='./cache', enabled=True)
    result = cache.get_pivoted(['PE', 'PB'], start_date=date(2024,1,1))
    # 第一次: 走 DB
    result2 = cache.get_pivoted(['PE', 'PB'], start_date=date(2024,1,1))
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


class FactorMatrixCache:
    """因子矩阵 L2 磁盘缓存。

    包装 FactorPivotAdapter.get_pivoted(),透明缓存每个因子的结果。
    支持部分命中：当请求多个因子时，仅查询未缓存的因子。
    """

    def __init__(
        self,
        adapter,
        cache_dir: str,
        enabled: bool = True,
        code_version: str = "v2.2.0-cache",
    ):
        """初始化因子矩阵缓存。

        Args:
            adapter: FactorPivotAdapter 实例（或兼容接口）
                需提供 get_pivoted(factor_names, stock_codes, start_date, end_date)
                可选提供 get_loaded_at_max(factor_name) 用于 staleness 追溯
            cache_dir: 缓存目录
            enabled: 是否启用（受环境变量覆盖）
            code_version: 代码版本号
        """
        self.adapter = adapter
        self.manager = CacheManager(
            cache_dir=cache_dir, enabled=enabled, code_version=code_version,
        )

    # ── 公开 API ──────────────────────────────

    def get_pivoted(
        self,
        factor_names: List[str],
        stock_codes: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, pd.DataFrame]:
        """获取 pivoted 因子数据（带缓存）。

        支持部分命中: 当请求多个因子时，仅未缓存的因子走 adapter，
        已缓存的因子直接从磁盘读取。

        Args:
            factor_names: 因子名称列表
            stock_codes: 股票代码列表 (None 表示全部)
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            {factor_name: DataFrame(stock_code × trade_date)}
            不存在的因子不出现在返回字典中
        """
        # 空因子列表直接返回,不走 DB
        if not factor_names:
            return {}

        # 缓存禁用时,全部走 adapter
        if not self.manager.enabled:
            return self.adapter.get_pivoted(
                factor_names, stock_codes=stock_codes,
                start_date=start_date, end_date=end_date,
            )

        # 逐因子检查缓存
        result: Dict[str, pd.DataFrame] = {}
        missing_factors: List[str] = []

        for fn in factor_names:
            key = self._make_key(fn, stock_codes, start_date, end_date)
            cached = self.manager.get(key)
            if cached is not None:
                result[fn] = cached
            else:
                missing_factors.append(fn)

        # 仅查询未命中的因子
        if missing_factors:
            fresh = self.adapter.get_pivoted(
                missing_factors, stock_codes=stock_codes,
                start_date=start_date, end_date=end_date,
            )

            # 获取 db_loaded_at_max 用于 source_signature
            db_loaded_at_max = self._get_loaded_at_max()

            for fn in missing_factors:
                if fn not in fresh:
                    # 因子不存在于 DB,跳过（不缓存,不返回）
                    continue
                df = fresh[fn]
                if df.empty:
                    # 空 DataFrame 不缓存,但仍返回
                    result[fn] = df
                    continue

                # 存入缓存
                key = self._make_key(fn, stock_codes, start_date, end_date)
                source_sig = {
                    "factor_name": fn,
                    "stock_codes": stock_codes or "ALL",
                    "start_date": str(start_date) if start_date else "MIN",
                    "end_date": str(end_date) if end_date else "MAX",
                    "db_loaded_at_max": db_loaded_at_max,
                    "query_type": "factor_pivot",
                }
                self.manager.set(key, df, source_signature=source_sig)
                result[fn] = df

        return result

    def invalidate(
        self,
        factor_name: str,
        stock_codes: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> None:
        """失效指定因子的缓存。

        Args:
            factor_name: 因子名称
            stock_codes: 股票代码列表 (None 表示全部)
            start_date: 开始日期
            end_date: 结束日期
        """
        key = self._make_key(factor_name, stock_codes, start_date, end_date)
        self.manager.invalidate(key)

    def clear_all(self) -> None:
        """清空所有缓存。"""
        self.manager.clear_all()

    def status(self) -> dict:
        """返回缓存状态。"""
        return self.manager.status()

    def verify(
        self,
        factor_name: str,
        stock_codes: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ):
        """验证指定因子缓存一致性。"""
        key = self._make_key(factor_name, stock_codes, start_date, end_date)
        return self.manager.verify(key)

    # ── 内部方法 ──────────────────────────────

    def _make_key(
        self,
        factor_name: str,
        stock_codes: Optional[List[str]],
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> CacheKey:
        """构建单因子缓存键。

        namespace: factor_matrix
        identifier: factor_name + date_range + stock_hash
        version: v1
        """
        stock_part = "ALL" if stock_codes is None else self._hash_stock_codes(stock_codes)
        start_part = str(start_date) if start_date else "MIN"
        end_part = str(end_date) if end_date else "MAX"
        identifier = f"{factor_name}_{start_part}_{end_part}_{stock_part}"
        return CacheKey(
            namespace="factor_matrix",
            identifier=identifier,
            version="v1",
        )

    @staticmethod
    def _hash_stock_codes(stock_codes: List[str]) -> str:
        """对股票代码列表生成短哈希。"""
        raw = ",".join(sorted(stock_codes))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]

    def _get_loaded_at_max(self, factor_name: Optional[str] = None) -> str:
        """从 adapter 获取 MAX(loaded_at)。

        如果 adapter 不支持此方法,返回 "unknown"。
        """
        try:
            if hasattr(self.adapter, "get_loaded_at_max"):
                return self.adapter.get_loaded_at_max(factor_name)
        except Exception as e:
            logger.warning(f"获取 loaded_at_max 失败: {e}")
        return "unknown"
