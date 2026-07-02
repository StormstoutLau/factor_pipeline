# -*- coding: utf-8 -*-
"""
并行因子回测运行器 — ParallelFactorRunner

将因子回测引擎的评估任务分配到多个进程并行执行。
每个 worker 进程独立创建 DataBridge 和 FactorBacktestEngine，
共享预计算的 fwd_returns（按日期范围分组）。

设计原则:
  - 因子间完全独立，天然适合并行化
  - 按日期范围分组，同组内共享 fwd_returns
  - Worker 函数必须在模块级别定义（Windows pickling 要求）
  - 结果与串行执行完全一致
"""

from __future__ import annotations

import logging
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# Worker 函数（模块级别，支持 Windows pickling）
# =============================================================================

def _run_worker(args: tuple) -> Dict[str, Dict[str, float]]:
    """Worker 进程入口: 对一组因子执行回测评估。

    Args:
        args: (factor_names, factor_data, price_data, fwd_returns, config)

    Returns:
        {factor_name: {metric: value, ...}, ...}
    """
    factor_names, factor_data, price_data, fwd_returns, config = args

    # Worker 进程内重新导入（Windows spawn 需要）
    from factor_pipeline.backtest.data_bridge import DataBridge
    from factor_pipeline.backtest.engine import FactorBacktestEngine

    bridge = DataBridge()
    results = {}

    for fn in factor_names:
        fd = factor_data[fn]
        cd = fd.columns.intersection(price_data.columns)
        cs = fd.index.intersection(price_data.index)
        fa = fd.loc[list(cs), list(cd)]
        pa = price_data.loc[list(cs), list(cd)]

        dl = bridge.create_dataloader({fn: fa}, pa)

        # 共享 fwd_returns 仅在形状匹配时使用，否则自计算
        n_dates = len(cd)
        n_stocks = len(cs)
        shared_fwd = None
        if fwd_returns is not None and fwd_returns.shape == (n_dates - 1, n_stocks):
            shared_fwd = fwd_returns

        engine = FactorBacktestEngine(dl, config=config, fwd_returns=shared_fwd)
        engine.run()
        results[fn] = engine.summary()[fn]

    return results


# =============================================================================
# ParallelFactorRunner
# =============================================================================

class ParallelFactorRunner:
    """并行因子回测运行器。

    将因子列表分配到多个 worker 进程并行评估。
    按日期范围分组的因子共享预计算的 fwd_returns。

    Usage:
        runner = ParallelFactorRunner(n_workers=4)
        results = runner.run(factor_data, price_data, config={'top_n': 0.2})

    便捷函数:
        results = run_parallel(factor_data, price_data, n_workers=4)
    """

    def __init__(self, n_workers: Optional[int] = None):
        """初始化并行运行器。

        Args:
            n_workers: worker 进程数。默认: CPU 核心数
        """
        self.n_workers = n_workers or max(1, os.cpu_count() or 4)

    # ── 公开 API ──────────────────────────────────

    def run(
        self,
        factor_data: Dict[str, pd.DataFrame],
        price_data: pd.DataFrame,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, float]]:
        """并行运行因子回测。

        Args:
            factor_data: {factor_name: DataFrame(index=stocks, columns=dates)}
            price_data: DataFrame(index=stocks, columns=dates)
            config: 回测引擎配置字典

        Returns:
            {factor_name: {metric: value, ...}, ...}

        Raises:
            ValueError: factor_data 为空时
        """
        if not factor_data:
            raise ValueError("factor_data 不能为空")

        # 按日期范围分组
        date_groups = self._group_by_dates(factor_data)
        n_groups = len(date_groups)
        logger.info(
            f"因子分组: {len(factor_data)} 个因子 → {n_groups} 个日期组, "
            f"{self.n_workers} workers"
        )

        # 逐组执行（不同日期范围不能共享 fwd_returns）
        all_results = {}
        for n_dates, factors in sorted(date_groups.items()):
            logger.debug(f"  日期组 {n_dates}天: {len(factors)} 个因子")

            # 预计算 fwd_returns（同组共享）
            fwd = self._compute_fwd_for_group(factors[0], factor_data, price_data)

            # 并行执行该组的所有因子
            group_results = self._run_group(
                factors, factor_data, price_data, fwd, config,
            )
            all_results.update(group_results)

        logger.info(f"并行评估完成: {len(all_results)} 个因子")
        return all_results

    # ── 内部方法 ──────────────────────────────────

    def _group_by_dates(
        self, factor_data: Dict[str, pd.DataFrame]
    ) -> Dict[int, List[str]]:
        """按日期数量分组因子。

        Returns:
            {n_dates: [factor_name, ...], ...}
        """
        groups: Dict[int, List[str]] = {}
        for fn, fd in factor_data.items():
            key = len(fd.columns)
            groups.setdefault(key, []).append(fn)
        return groups

    def _compute_fwd_for_group(
        self,
        first_fn: str,
        factor_data: Dict[str, pd.DataFrame],
        price_data: pd.DataFrame,
    ) -> np.ndarray:
        """为日期组预计算 fwd_returns。

        Args:
            first_fn: 组内第一个因子名称（用于获取日期范围）
            factor_data: 全部因子数据
            price_data: 价格数据

        Returns:
            np.ndarray, shape (n_dates - 1, n_stocks)
        """
        from factor_pipeline.backtest.data_bridge import DataBridge
        from factor_pipeline.backtest.engine import FactorBacktestEngine

        fd = factor_data[first_fn]
        cd = fd.columns.intersection(price_data.columns)
        cs = fd.index.intersection(price_data.index)
        fa = fd.loc[list(cs), list(cd)]
        pa = price_data.loc[list(cs), list(cd)]

        bridge = DataBridge()
        dl = bridge.create_dataloader({first_fn: fa}, pa)
        engine = FactorBacktestEngine(dl)
        return engine.compute_fwd_returns()

    def _run_group(
        self,
        factors: List[str],
        factor_data: Dict[str, pd.DataFrame],
        price_data: pd.DataFrame,
        fwd: np.ndarray,
        config: Optional[Dict[str, Any]],
    ) -> Dict[str, Dict[str, float]]:
        """并行执行一个日期组内的所有因子。

        Args:
            factors: 因子名称列表
            factor_data: 全部因子数据
            price_data: 价格数据
            fwd: 预计算的前向收益
            config: 回测配置

        Returns:
            {factor_name: {metric: value, ...}, ...}
        """
        n_workers = min(self.n_workers, len(factors))
        chunks = self._split_factors(factors, n_workers)

        worker_args = [
            (chunk, factor_data, price_data, fwd, config)
            for chunk in chunks
        ]

        # 使用 ProcessPoolExecutor（CPU 密集型）
        # 若进程启动失败（如 Windows 环境限制），降级为串行
        try:
            results = self._run_with_processes(worker_args, n_workers)
        except Exception as e:
            logger.warning(f"ProcessPoolExecutor 失败: {e}，降级为串行执行")
            results = self._run_serial(worker_args)

        return results

    def _run_with_processes(
        self, worker_args: list, n_workers: int,
    ) -> Dict[str, Dict[str, float]]:
        """使用 ProcessPoolExecutor 执行。"""
        # Windows: 使用 spawn context 避免 pickle 问题
        ctx = multiprocessing.get_context('spawn')
        with ProcessPoolExecutor(max_workers=n_workers, mp_context=ctx) as ex:
            futures = [ex.submit(_run_worker, args) for args in worker_args]
            results: Dict[str, Dict[str, float]] = {}
            for future in futures:
                results.update(future.result())
        return results

    def _run_serial(
        self, worker_args: list,
    ) -> Dict[str, Dict[str, float]]:
        """串行执行（降级方案）。"""
        results: Dict[str, Dict[str, float]] = {}
        for args in worker_args:
            results.update(_run_worker(args))
        return results

    @staticmethod
    def _split_factors(factors: List[str], n_chunks: int) -> List[List[str]]:
        """将因子列表均匀分配到 n_chunks 个组。

        Examples:
            _split_factors(['a','b','c','d','e'], 3) → [['a','b'], ['c','d'], ['e']]
            _split_factors(['a','b'], 5) → [['a'], ['b'], [], [], []]
        """
        n = len(factors)
        if n <= n_chunks:
            return [[f] for f in factors] + [[] for _ in range(n_chunks - n)]

        k, m = divmod(n, n_chunks)
        chunks = []
        start = 0
        for i in range(n_chunks):
            size = k + (1 if i < m else 0)
            chunks.append(factors[start:start + size])
            start += size
        return chunks


# =============================================================================
# 便捷函数
# =============================================================================

def run_parallel(
    factor_data: Dict[str, pd.DataFrame],
    price_data: pd.DataFrame,
    n_workers: Optional[int] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, float]]:
    """便捷函数: 并行运行因子回测。

    Args:
        factor_data: {factor_name: DataFrame(index=stocks, columns=dates)}
        price_data: DataFrame(index=stocks, columns=dates)
        n_workers: worker 进程数
        config: 回测配置

    Returns:
        {factor_name: {metric: value, ...}, ...}
    """
    runner = ParallelFactorRunner(n_workers=n_workers)
    return runner.run(factor_data, price_data, config=config)