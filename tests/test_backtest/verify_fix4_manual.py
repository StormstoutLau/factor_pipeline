# -*- coding: utf-8 -*-
"""Fix 4 手工校验脚本

校验:
  1. __all__ 完整覆盖 13 个模块的 26 个公开 API
  2. 每个导出名可通过 __init__ 和子模块两路径导入, 且是同一对象
  3. reload 无循环导入
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent.parent  # F:\Coding
_PROJECT_ROOT = _PROJECT_PARENT / "factor_pipeline"
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))


print("=" * 70)
print("Fix 4 手工校验 — backtest/__init__.py 补全导出")
print("=" * 70)


# ── 手工列出的公开 API 清单 (13 模块 × 26 API) ──────────────────
MODULE_PUBLIC_API = {
    "factor_metrics": ["compute_rank_ic", "compute_pearson_ic", "compute_ic_series",
                       "compute_icir", "compute_ic_decay", "compute_turnover",
                       "compute_long_short_returns", "compute_spread", "compute_hit_rate"],
    "cache_manager": ["CacheManager", "CacheKey", "CacheMeta", "CacheStatus"],
    "factor_cache": ["FactorMatrixCache"],
    "price_cache": ["PriceMatrixCache"],
    "fwd_returns_cache": ["FwdReturnsCache"],
    "cached_data_loader": ["CachedDataLoader"],
    "factor_pivot": ["FactorPivotAdapter"],
    "data_bridge": ["DataBridge"],
    "engine": ["FactorBacktestEngine"],
    "health_bridge": ["HealthMonitorAdapter"],
    "unified_drift": ["UnifiedDriftReporter"],
    "parallel_runner": ["ParallelFactorRunner", "run_parallel"],
    "pipeline_integration": ["PipelineBacktestRunner"],
}

# 展平期望集合
all_expected = set()
for api_list in MODULE_PUBLIC_API.values():
    all_expected.update(api_list)


# ── 校验 1: __all__ 完整性 ──────────────────────────────────────
print("\n[1] __all__ 完整性校验")

import factor_pipeline.backtest as bt
all_exported = set(bt.__all__)

missing = all_expected - all_exported
extra = all_exported - all_expected

print(f"  __all__ 数量: {len(all_exported)}")
print(f"  期望数量: {len(all_expected)}")
assert not missing, f"__all__ 缺失: {missing}"
assert not extra, f"__all__ 多余: {extra}"
print(f"  ✓ __all__ 完全覆盖 {len(all_expected)} 个公开 API, 无缺失无多余")


# ── 校验 2: 导入路径一致性 (init vs submodule) ──────────────────
print("\n[2] 导入路径一致性校验")

mismatch_count = 0
for mod_name, api_list in MODULE_PUBLIC_API.items():
    full_mod = f"factor_pipeline.backtest.{mod_name}"
    mod = importlib.import_module(full_mod)
    for api_name in api_list:
        from_init = getattr(bt, api_name, None)
        from_sub = getattr(mod, api_name, None)
        if from_init is None:
            print(f"  ✗ {api_name}: 无法从 backtest 导入")
            mismatch_count += 1
        elif from_sub is None:
            print(f"  ✗ {api_name}: 在 {full_mod} 中不存在")
            mismatch_count += 1
        elif from_init is not from_sub:
            print(f"  ✗ {api_name}: __init__ 与子模块不是同一对象")
            mismatch_count += 1

assert mismatch_count == 0, f"导入路径不一致: {mismatch_count} 处"
print(f"  ✓ {len(all_expected)} 个 API 的 __init__ 导入与子模块导入完全一致 (同一对象)")


# ── 校验 3: reload 无循环导入 ───────────────────────────────────
print("\n[3] reload 无循环导入校验")

# 记录 reload 前 sys.modules 中 backtest 相关键
before_keys = set(k for k in sys.modules if 'factor_pipeline.backtest' in k)
core_before = set(k for k in sys.modules if k.startswith('core'))

# reload
importlib.reload(bt)

after_keys = set(k for k in sys.modules if 'factor_pipeline.backtest' in k)
core_after = set(k for k in sys.modules if k.startswith('core'))

# reload 后 backtest 模块仍可访问
assert bt.FactorBacktestEngine is not None, "reload 后 FactorBacktestEngine 不可访问"
assert bt.DataBridge is not None, "reload 后 DataBridge 不可访问"
assert bt.HealthMonitorAdapter is not None, "reload 后 HealthMonitorAdapter 不可访问"

# core 相关模块不应因 reload 丢失 (health_bridge 依赖)
lost_core = core_before - core_after
assert not lost_core, f"reload 后 core 模块丢失: {lost_core}"

print(f"  ✓ reload 成功, backtest 模块可访问, core 模块无丢失")
print(f"    backtest 模块数: reload 前 {len(before_keys)} → 后 {len(after_keys)}")
print(f"    core 模块数: reload 前 {len(core_before)} → 后 {len(core_after)}")


# ── 校验 4: 按类别逐项校验 ──────────────────────────────────────
print("\n[4] 按类别逐项校验")

categories = {
    "因子指标 (9)": ["compute_rank_ic", "compute_pearson_ic", "compute_ic_series",
                    "compute_icir", "compute_ic_decay", "compute_turnover",
                    "compute_long_short_returns", "compute_spread", "compute_hit_rate"],
    "缓存 (8)": ["CacheManager", "CacheKey", "CacheMeta", "CacheStatus",
                 "FactorMatrixCache", "PriceMatrixCache", "FwdReturnsCache", "CachedDataLoader"],
    "数据适配 (2)": ["FactorPivotAdapter", "DataBridge"],
    "引擎 (1)": ["FactorBacktestEngine"],
    "健康度与漂移 (2)": ["HealthMonitorAdapter", "UnifiedDriftReporter"],
    "运行器 (3)": ["ParallelFactorRunner", "run_parallel", "PipelineBacktestRunner"],
}

for cat_name, api_list in categories.items():
    for api_name in api_list:
        obj = getattr(bt, api_name, None)
        assert obj is not None, f"{cat_name}: {api_name} 不可访问"
    print(f"  ✓ {cat_name}: {len(api_list)} 项全部可访问")


# ── 校验 5: 总数核对 ────────────────────────────────────────────
print("\n[5] 总数核对")
assert len(bt.__all__) == 25, f"__all__ 数量应为 25, 实际 {len(bt.__all__)}"
print(f"  ✓ __all__ 总数: {len(bt.__all__)} (9+8+2+1+2+3=25)")


print("\n" + "=" * 70)
print("Fix 4 手工校验通过: 5/5")
print("=" * 70)
