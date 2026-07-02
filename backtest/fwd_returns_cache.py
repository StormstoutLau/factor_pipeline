# -*- coding: utf-8 -*-
"""
前向收益缓存 — FwdReturnsCache

缓存 fwd_returns ndarray,避免跨 Pipeline run 重复计算。

设计:
  - 接受 compute_fn (callable) 按需计算
  - 缓存键: stock_codes + date_range + field + adjust
  - 数据类型: ndarray → .npy (CacheManager 已支持)
  - 环境变量逃生舱 FACTOR_PIPELINE_CACHE=disabled

Usage:
    cache = FwdReturnsCache(cache_dir="./cache", enabled=True)
    fwd = cache.get_or_compute(
        stock_codes="hash123",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 31),
        field="close",
        adjust="none",
        compute_fn=lambda: engine.compute_fwd_returns(),
    )
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date
from typing import Callable, Optional

import numpy as np

from .cache_manager import CacheKey, CacheManager

logger = logging.getLogger(__name__)


class FwdReturnsCache:
    """前向收益 ndarray 缓存。

    包装 CacheManager,缓存 fwd_returns 计算结果。
    按需计算: 首次调用执行 compute_fn,后续命中缓存直接返回。
    """

    def __init__(
        self,
        cache_dir: str,
        enabled: bool = True,
        code_version: str = "v2.2.0-cache",
    ):
        """初始化前向收益缓存。

        Args:
            cache_dir: 缓存目录 (与其他缓存共享)
            enabled: 是否启用 (受环境变量覆盖)
            code_version: 代码版本号
        """
        self.manager = CacheManager(
            cache_dir=cache_dir, enabled=enabled, code_version=code_version,
        )

    # ── 公开 API ──────────────────────────────

    def get_or_compute(
        self,
        stock_codes: str,
        start_date: Optional[date],
        end_date: Optional[date],
        field: str,
        adjust: str,
        compute_fn: Callable[[], np.ndarray],
    ) -> np.ndarray:
        """获取前向收益 (带缓存)。

        首次调用执行 compute_fn 并缓存结果,后续命中缓存直接返回。

        Args:
            stock_codes: 股票集合哈希 (或标识字符串)
            start_date: 开始日期
            end_date: 结束日期
            field: 价格字段 (通常 "close")
            adjust: 复权方式
            compute_fn: 计算函数,签名 () -> np.ndarray

        Returns:
            np.ndarray, shape (n_dates - 1, n_stocks)
        """
        # 缓存禁用时直接计算
        if not self.manager.enabled:
            logger.info("[FWD_CACHE] disabled, computing directly")
            return compute_fn()

        key = self._make_key(stock_codes, start_date, end_date, field, adjust)

        # 尝试命中缓存
        cached = self.manager.get(key)
        if cached is not None:
            return cached

        # 未命中: 计算并缓存
        fwd = compute_fn()

        # 空数组不缓存
        if fwd is None or fwd.size == 0:
            logger.info("[FWD_CACHE] computed (empty, not cached)")
            return fwd

        # 存入缓存
        source_sig = {
            "stock_codes": stock_codes,
            "start_date": str(start_date) if start_date else "MIN",
            "end_date": str(end_date) if end_date else "MAX",
            "field": field,
            "adjust": adjust,
            "query_type": "fwd_returns",
        }
        self.manager.set(key, fwd, source_signature=source_sig)
        return fwd

    def invalidate(
        self,
        stock_codes: str,
        start_date: Optional[date],
        end_date: Optional[date],
        field: str,
        adjust: str,
    ) -> None:
        """失效指定参数的前向收益缓存。"""
        key = self._make_key(stock_codes, start_date, end_date, field, adjust)
        self.manager.invalidate(key)

    def clear_all(self) -> None:
        """清空所有缓存。"""
        self.manager.clear_all()

    def status(self) -> dict:
        """返回缓存状态。"""
        return self.manager.status()

    # ── 内部方法 ──────────────────────────────

    def _make_key(
        self,
        stock_codes: str,
        start_date: Optional[date],
        end_date: Optional[date],
        field: str,
        adjust: str,
    ) -> CacheKey:
        """构建缓存键。

        namespace: fwd_returns
        identifier: field_adjust_start_end_stockhash
        version: v1
        """
        start_part = str(start_date) if start_date else "MIN"
        end_part = str(end_date) if end_date else "MAX"
        identifier = f"{field}_{adjust}_{start_part}_{end_part}_{stock_codes}"
        return CacheKey(
            namespace="fwd_returns",
            identifier=identifier,
            version="v1",
        )
