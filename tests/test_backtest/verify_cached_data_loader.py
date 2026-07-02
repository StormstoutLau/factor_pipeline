# -*- coding: utf-8 -*-
"""
Phase 4 手工校验: CachedDataLoader 真实 DB 端到端加速对比

校验维度:
  1. 默认工厂能与真实 Factor_DB 连接
  2. 第一次运行: 走 DB,产生缓存文件
  3. 第二次运行: 全部命中缓存,加速显著
  4. 两次运行结果值完全一致 (因子 + 价格)
  5. status() 正确反映缓存状态
  6. 环境变量逃生舱有效
  7. 与 FactorBacktestEngine 端到端集成,两次结果完全一致
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

# 项目根
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT.parent))

from factor_pipeline.backtest.cached_data_loader import CachedDataLoader
from factor_pipeline.backtest.data_bridge import DataBridge
from factor_pipeline.backtest.engine import FactorBacktestEngine

# =============================================================================
# 配置
# =============================================================================

DB_PATH = r"F:\Coding\Factor_DB\factor_db.duckdb"
CACHE_DIR = Path(__file__).resolve().parent / "_verify_cached_loader"
TEST_FACTORS = ["bps", "cfps", "ar_turn"]
START_DATE = date(2024, 1, 1)
END_DATE = date(2024, 3, 31)


def main():
    print("=" * 80)
    print("Phase 4 手工校验: CachedDataLoader 真实 DB 端到端加速对比")
    print("=" * 80)
    print(f"DB: {DB_PATH}")
    print(f"Cache dir: {CACHE_DIR}")
    print(f"Factors: {TEST_FACTORS}")
    print(f"Date range: {START_DATE} ~ {END_DATE}")
    print()

    # 清理旧缓存
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
    CACHE_DIR.mkdir(parents=True)

    # =============================================================================
    # 校验 1: 默认工厂连接真实 DB
    # =============================================================================
    print("-" * 80)
    print("校验 1: 默认工厂连接真实 Factor_DB")
    print("-" * 80)

    loader = CachedDataLoader(
        db_path=DB_PATH,
        cache_dir=str(CACHE_DIR),
        enabled=True,
    )
    print(f"  factor_adapter 类型: {type(loader.factor_adapter).__name__}")
    print(f"  price_query 类型: {type(loader.price_query).__name__}")
    print(f"  factor_cache 类型: {type(loader.factor_cache).__name__}")
    print(f"  price_cache 类型: {type(loader.price_cache).__name__}")
    print(f"  enabled = {loader.enabled}")
    assert loader.enabled is True
    print(f"\n✅ 校验 1 通过: 默认工厂成功创建真实 adapter/query + 缓存层")
    print()

    # =============================================================================
    # 校验 2: 第一次运行 — 走 DB,产生缓存
    # =============================================================================
    print("-" * 80)
    print("校验 2: 第一次运行 — 走 DB,产生缓存")
    print("-" * 80)

    t0 = time.perf_counter()
    factor_result_run1 = loader.get_pivoted_factors(
        TEST_FACTORS, start_date=START_DATE, end_date=END_DATE,
    )
    t1 = time.perf_counter()
    factor_time_run1 = t1 - t0

    t0 = time.perf_counter()
    price_result_run1 = loader.get_price_matrix(
        field="close", start_date=START_DATE, end_date=END_DATE,
    )
    t1 = time.perf_counter()
    price_time_run1 = t1 - t0

    print(f"  因子查询 (第一次, MISS): {factor_time_run1:.3f}s")
    print(f"    返回因子数: {len(factor_result_run1)}")
    for fn, df in factor_result_run1.items():
        nan_ratio = float(np.isnan(df.values).sum() / df.size) if df.size > 0 else 0.0
        print(f"    {fn}: shape={df.shape}, nan_ratio={nan_ratio:.4f}")

    print(f"  价格查询 (第一次, MISS): {price_time_run1:.3f}s")
    print(f"    价格矩阵 shape: {price_result_run1.shape}")

    # 检查缓存文件产生
    parquet_files = list(CACHE_DIR.glob("*.parquet"))
    meta_files = list(CACHE_DIR.glob("*.meta.json"))
    print(f"\n  缓存文件: {len(parquet_files)} parquet, {len(meta_files)} meta.json")
    assert len(parquet_files) >= len(TEST_FACTORS) + 1, \
        f"期望至少 {len(TEST_FACTORS) + 1} 个 parquet (因子 + 价格), 实际 {len(parquet_files)}"
    print(f"\n✅ 校验 2 通过: 第一次运行走 DB,产生 {len(parquet_files)} 个缓存文件")
    print()

    # =============================================================================
    # 校验 3: 第二次运行 — 全部命中缓存,加速显著
    # =============================================================================
    print("-" * 80)
    print("校验 3: 第二次运行 — 全部命中缓存,加速显著")
    print("-" * 80)

    t0 = time.perf_counter()
    factor_result_run2 = loader.get_pivoted_factors(
        TEST_FACTORS, start_date=START_DATE, end_date=END_DATE,
    )
    t1 = time.perf_counter()
    factor_time_run2 = t1 - t0

    t0 = time.perf_counter()
    price_result_run2 = loader.get_price_matrix(
        field="close", start_date=START_DATE, end_date=END_DATE,
    )
    t1 = time.perf_counter()
    price_time_run2 = t1 - t0

    print(f"  因子查询 (第二次, HIT): {factor_time_run2:.3f}s (vs 第一次 {factor_time_run1:.3f}s)")
    print(f"  价格查询 (第二次, HIT): {price_time_run2:.3f}s (vs 第一次 {price_time_run1:.3f}s)")

    factor_speedup = factor_time_run1 / factor_time_run2 if factor_time_run2 > 0 else float("inf")
    price_speedup = price_time_run1 / price_time_run2 if price_time_run2 > 0 else float("inf")
    total_run1 = factor_time_run1 + price_time_run1
    total_run2 = factor_time_run2 + price_time_run2
    total_speedup = total_run1 / total_run2 if total_run2 > 0 else float("inf")

    print(f"\n  因子加速: {factor_speedup:.2f}x")
    print(f"  价格加速: {price_speedup:.2f}x")
    print(f"  总加速: {total_speedup:.2f}x ({total_run1:.3f}s → {total_run2:.3f}s)")

    assert factor_time_run2 < factor_time_run1, "缓存应更快"
    assert price_time_run2 < price_time_run1, "缓存应更快"
    print(f"\n✅ 校验 3 通过: 第二次运行全部命中缓存,总加速 {total_speedup:.2f}x")
    print()

    # =============================================================================
    # 校验 4: 两次运行结果值完全一致
    # =============================================================================
    print("-" * 80)
    print("校验 4: 两次运行结果值完全一致")
    print("-" * 80)

    # 因子值一致性 (排序后比较,因 DuckDB PIVOT 不保证行序)
    print("  因子值一致性 (排序后比较):")
    for fn in TEST_FACTORS:
        d1 = factor_result_run1[fn].sort_index(axis=0).sort_index(axis=1)
        d2 = factor_result_run2[fn].sort_index(axis=0).sort_index(axis=1)
        try:
            pd.testing.assert_frame_equal(d1, d2, check_freq=False)
            print(f"    {fn}: ✅ 完全一致 shape={d1.shape}")
        except AssertionError as e:
            print(f"    {fn}: ❌ 不一致: {e}")
            raise

    # 价格值一致性
    print("  价格值一致性:")
    try:
        pd.testing.assert_frame_equal(
            price_result_run1, price_result_run2, check_freq=False,
        )
        print(f"    ✅ 完全一致 shape={price_result_run1.shape}")
    except AssertionError as e:
        print(f"    ❌ 不一致: {e}")
        raise

    print(f"\n✅ 校验 4 通过: 两次运行结果值完全一致")
    print()

    # =============================================================================
    # 校验 5: status() 正确反映缓存状态
    # =============================================================================
    print("-" * 80)
    print("校验 5: status() 正确反映缓存状态")
    print("-" * 80)

    status = loader.status()
    assert "factor_cache" in status
    assert "price_cache" in status
    print(f"  factor_cache 条目数: {status['factor_cache']['total_entries']}")
    print(f"  price_cache 条目数: {status['price_cache']['total_entries']}")
    print(f"  factor_cache 总大小: {status['factor_cache']['total_size_bytes'] / 1024:.1f} KB")
    print(f"  price_cache 总大小: {status['price_cache']['total_size_bytes'] / 1024:.1f} KB")

    assert status["factor_cache"]["total_entries"] >= len(TEST_FACTORS)
    assert status["price_cache"]["total_entries"] >= 1
    print(f"\n✅ 校验 5 通过: status() 正确反映因子+价格缓存状态")
    print()

    # =============================================================================
    # 校验 6: 环境变量逃生舱
    # =============================================================================
    print("-" * 80)
    print("校验 6: 环境变量逃生舱 FACTOR_PIPELINE_CACHE=disabled")
    print("-" * 80)

    os.environ["FACTOR_PIPELINE_CACHE"] = "disabled"
    try:
        assert loader.enabled is False, "env=disabled 时 enabled 应为 False"
        # 此时查询应绕过缓存,直接走 DB
        t0 = time.perf_counter()
        loader.get_pivoted_factors(TEST_FACTORS, start_date=START_DATE, end_date=END_DATE)
        t1 = time.perf_counter()
        env_disabled_time = t1 - t0
        print(f"  env=disabled 因子查询耗时: {env_disabled_time:.3f}s (应接近第一次 {factor_time_run1:.3f}s)")
        # 应该走 DB,所以耗时接近第一次
        assert env_disabled_time > factor_time_run2, "env=disabled 应比缓存命中慢"
        print(f"  ✅ env=disabled 比 cache HIT 慢,确认绕过缓存走 DB")
    finally:
        del os.environ["FACTOR_PIPELINE_CACHE"]

    print(f"\n✅ 校验 6 通过: 环境变量逃生舱有效")
    print()

    # =============================================================================
    # 校验 7: 与 FactorBacktestEngine 端到端集成
    # =============================================================================
    print("-" * 80)
    print("校验 7: 与 FactorBacktestEngine 端到端集成,两次结果完全一致")
    print("-" * 80)

    def run_engine_with_loader(ld: CachedDataLoader, fn: str):
        """通过 CachedDataLoader 加载数据并跑引擎"""
        factor_result = ld.get_pivoted_factors([fn], start_date=START_DATE, end_date=END_DATE)
        price_df = ld.get_price_matrix(field="close", start_date=START_DATE, end_date=END_DATE)

        # 转换价格 (dates × stocks) → (stocks × dates)
        price_pivoted = price_df.T
        price_pivoted.index = price_pivoted.index.astype(str)
        price_pivoted.columns = pd.to_datetime(price_pivoted.columns)

        # 对齐
        fd = factor_result[fn]
        cd = fd.columns.intersection(price_pivoted.columns)
        cs = fd.index.intersection(price_pivoted.index)
        fa = fd.loc[list(cs), list(cd)]
        pa = price_pivoted.loc[list(cs), list(cd)]

        bridge = DataBridge()
        dl = bridge.create_dataloader({fn: fa}, pa)
        engine = FactorBacktestEngine(dl)
        engine.run()
        return engine.summary()[fn]

    # 第一个因子跑引擎 (此时缓存已全部命中,因为校验 2 已经预热)
    fn = TEST_FACTORS[0]
    t0 = time.perf_counter()
    summary_run1 = run_engine_with_loader(loader, fn)
    t1 = time.perf_counter()
    engine_time_run1 = t1 - t0

    t0 = time.perf_counter()
    summary_run2 = run_engine_with_loader(loader, fn)
    t1 = time.perf_counter()
    engine_time_run2 = t1 - t0

    print(f"  因子 {fn} 引擎运行 (缓存命中):")
    print(f"    第一次: {engine_time_run1:.3f}s, ICIR={summary_run1.get('rank_icir', float('nan')):.4f}")
    print(f"    第二次: {engine_time_run2:.3f}s, ICIR={summary_run2.get('rank_icir', float('nan')):.4f}")

    # 引擎结果应完全一致
    for key in ["rank_icir", "mean_rank_ic", "hit_rate", "turnover"]:
        v1 = summary_run1.get(key, float("nan"))
        v2 = summary_run2.get(key, float("nan"))
        if isinstance(v1, float) and isinstance(v2, float):
            if np.isnan(v1) and np.isnan(v2):
                continue
            assert abs(v1 - v2) < 1e-10, f"{key}: {v1} != {v2}"
            print(f"    {key}: ✅ 一致 ({v1:.6f})")
        else:
            assert v1 == v2, f"{key}: {v1} != {v2}"

    print(f"\n✅ 校验 7 通过: 引擎端到端集成成功,两次结果完全一致")
    print()

    # =============================================================================
    # 清理
    # =============================================================================
    if hasattr(loader.factor_adapter, "close"):
        loader.factor_adapter.close()

    print("=" * 80)
    print("🎉 Phase 4 手工校验全部通过!")
    print("=" * 80)
    print(f"  校验 1: 默认工厂连接真实 DB ✅")
    print(f"  校验 2: 第一次运行走 DB,产生缓存 ✅")
    print(f"  校验 3: 第二次运行全部命中缓存,总加速 {total_speedup:.2f}x ✅")
    print(f"  校验 4: 两次运行结果值完全一致 ✅")
    print(f"  校验 5: status() 正确反映缓存状态 ✅")
    print(f"  校验 6: 环境变量逃生舱有效 ✅")
    print(f"  校验 7: 引擎端到端集成,两次结果完全一致 ✅")
    print()
    print(f"性能汇总:")
    print(f"  因子查询: {factor_time_run1:.3f}s → {factor_time_run2:.3f}s ({factor_speedup:.2f}x)")
    print(f"  价格查询: {price_time_run1:.3f}s → {price_time_run2:.3f}s ({price_speedup:.2f}x)")
    print(f"  总查询: {total_run1:.3f}s → {total_run2:.3f}s ({total_speedup:.2f}x)")
    print()
    print(f"缓存目录: {CACHE_DIR}")
    print(f"缓存文件数: {len(list(CACHE_DIR.glob('*')))}")


if __name__ == "__main__":
    main()
