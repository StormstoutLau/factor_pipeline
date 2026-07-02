# -*- coding: utf-8 -*-
"""
backtest 子包 — 回测引擎与数据适配层

公开 API:
  - 缓存: CachedDataLoader, FactorMatrixCache, PriceMatrixCache, FwdReturnsCache, CacheManager
  - 引擎: FactorBacktestEngine, DataBridge, FactorPivotAdapter
  - 桥接: HealthMonitorAdapter, UnifiedDriftReporter
  - 运行器: ParallelFactorRunner, PipelineBacktestRunner, run_parallel
  - 因子指标: compute_rank_ic, compute_pearson_ic, compute_ic_series, compute_icir,
              compute_ic_decay, compute_turnover, compute_long_short_returns,
              compute_spread, compute_hit_rate
"""

# 因子指标 (纯函数, 无外部依赖)
from .factor_metrics import (
    compute_rank_ic,
    compute_pearson_ic,
    compute_ic_series,
    compute_icir,
    compute_ic_decay,
    compute_turnover,
    compute_long_short_returns,
    compute_spread,
    compute_hit_rate,
)

# 缓存管理
from .cache_manager import (
    CacheManager,
    CacheKey,
    CacheMeta,
    CacheStatus,
)
from .factor_cache import FactorMatrixCache
from .price_cache import PriceMatrixCache
from .fwd_returns_cache import FwdReturnsCache
from .cached_data_loader import CachedDataLoader

# 数据适配
from .factor_pivot import FactorPivotAdapter
from .data_bridge import DataBridge

# 回测引擎
from .engine import FactorBacktestEngine

# 健康度与漂移
from .health_bridge import HealthMonitorAdapter
from .unified_drift import UnifiedDriftReporter

# 并行与集成运行器
from .parallel_runner import (
    ParallelFactorRunner,
    run_parallel,
)
from .pipeline_integration import PipelineBacktestRunner


__all__ = [
    # 因子指标
    'compute_rank_ic',
    'compute_pearson_ic',
    'compute_ic_series',
    'compute_icir',
    'compute_ic_decay',
    'compute_turnover',
    'compute_long_short_returns',
    'compute_spread',
    'compute_hit_rate',
    # 缓存
    'CacheManager',
    'CacheKey',
    'CacheMeta',
    'CacheStatus',
    'FactorMatrixCache',
    'PriceMatrixCache',
    'FwdReturnsCache',
    'CachedDataLoader',
    # 数据适配
    'FactorPivotAdapter',
    'DataBridge',
    # 引擎
    'FactorBacktestEngine',
    # 健康度与漂移
    'HealthMonitorAdapter',
    'UnifiedDriftReporter',
    # 运行器
    'ParallelFactorRunner',
    'run_parallel',
    'PipelineBacktestRunner',
]
