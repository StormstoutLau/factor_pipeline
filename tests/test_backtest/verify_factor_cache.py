# -*- coding: utf-8 -*-
"""
Phase 3 手工校验: FactorMatrixCache 多因子缓存一致性

校验维度:
  1. 直接查询 vs 缓存查询: 值完全一致（多因子）
  2. 部分命中: 仅查询未缓存的因子
  3. meta.json 透明度: source_signature 包含 db_loaded_at_max
  4. 性能对比: 缓存命中 vs 直接查询
  5. 环境变量逃生舱: FACTOR_PIPELINE_CACHE=disabled 全走 DB
  6. 失效与刷新: invalidate 单因子后重查
  7. 不同日期范围: 独立缓存
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

# 添加项目根目录到 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
# 同时添加 F:\Coding 以便导入 factor_pipeline 包
sys.path.insert(0, str(PROJECT_ROOT.parent))

from factor_pipeline.backtest.factor_cache import FactorMatrixCache
from factor_pipeline.backtest.factor_pivot import FactorPivotAdapter

# =============================================================================
# 配置
# =============================================================================

DB_PATH = r"F:\Coding\Factor_DB\factor_db.duckdb"
CACHE_DIR = Path(__file__).resolve().parent / "_verify_factor_cache"
# 使用 DB 中真实存在的因子（bps/cfps/ar_turn 有 2020-2026 数据）
TEST_FACTORS = ["bps", "cfps", "ar_turn"]
EXTRA_FACTOR = "basic_eps_yoy"  # 用于部分命中测试
START_DATE = date(2024, 1, 1)
END_DATE = date(2024, 3, 31)  # Q1 2024,控制数据量

# 计数器,用于追踪 adapter 调用
class CountingAdapter:
    """包装 FactorPivotAdapter,记录调用次数和查询的因子"""

    def __init__(self, adapter):
        self._adapter = adapter
        self.call_count = 0
        self.queried_factors = []

    def get_pivoted(self, factor_names, stock_codes=None, start_date=None, end_date=None):
        self.call_count += 1
        self.queried_factors.append(list(factor_names))
        return self._adapter.get_pivoted(
            factor_names, stock_codes=stock_codes,
            start_date=start_date, end_date=end_date,
        )

    def get_loaded_at_max(self, factor_name=None):
        return self._adapter.get_loaded_at_max(factor_name) if hasattr(self._adapter, "get_loaded_at_max") else "unknown"

    def close(self):
        if hasattr(self._adapter, "close"):
            self._adapter.close()


def get_db_loaded_at_max(adapter):
    """从 DuckDB 直接查询 loaded_at_max"""
    try:
        if hasattr(adapter, "_adapter"):
            conn = adapter._adapter.conn
        else:
            conn = adapter.conn
        result = conn.execute("SELECT MAX(loaded_at)::VARCHAR FROM factor_data").fetchone()
        return result[0] if result else "unknown"
    except Exception as e:
        print(f"  [WARN] 获取 loaded_at_max 失败: {e}")
        return "unknown"


def main():
    print("=" * 80)
    print("Phase 3 手工校验: FactorMatrixCache 多因子缓存一致性")
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

    # 初始化 adapter
    raw_adapter = FactorPivotAdapter(DB_PATH)
    adapter = CountingAdapter(raw_adapter)
    db_loaded_at_max = get_db_loaded_at_max(adapter)
    print(f"[INFO] db_loaded_at_max = {db_loaded_at_max}")
    print()

    # =============================================================================
    # 校验 1: 直接查询 vs 缓存查询 — 值完全一致
    # =============================================================================
    print("-" * 80)
    print("校验 1: 直接查询 vs 缓存查询 — 值完全一致（多因子）")
    print("-" * 80)

    # 直接查询（绕过缓存）
    direct_result = raw_adapter.get_pivoted(
        TEST_FACTORS, start_date=START_DATE, end_date=END_DATE,
    )
    print(f"直接查询得到 {len(direct_result)} 个因子:")
    for fn, df in direct_result.items():
        nan_ratio = float(np.isnan(df.values).sum() / df.size) if df.size > 0 else 0.0
        print(f"  {fn}: shape={df.shape}, nan_ratio={nan_ratio:.4f}")

    # 缓存查询（第一次: MISS → SET）
    cache = FactorMatrixCache(adapter, cache_dir=str(CACHE_DIR), enabled=True)
    adapter.call_count = 0
    adapter.queried_factors = []

    t0 = time.perf_counter()
    cached_result = cache.get_pivoted(
        TEST_FACTORS, start_date=START_DATE, end_date=END_DATE,
    )
    t1 = time.perf_counter()
    print(f"\n第一次缓存查询 (MISS → SET): call_count={adapter.call_count}, 耗时={t1-t0:.3f}s")
    print(f"  queried_factors = {adapter.queried_factors}")

    # 值一致性校验（排序后比较,因为 DuckDB PIVOT GROUP BY 不保证行序）
    print("\n值一致性校验 (排序后比较,因 DuckDB PIVOT 不保证行序):")
    all_consistent = True
    for fn in TEST_FACTORS:
        if fn not in direct_result or fn not in cached_result:
            print(f"  {fn}: ❌ 缺失 (direct={fn in direct_result}, cached={fn in cached_result})")
            all_consistent = False
            continue
        d = direct_result[fn].sort_index(axis=0).sort_index(axis=1)
        c = cached_result[fn].sort_index(axis=0).sort_index(axis=1)
        try:
            pd.testing.assert_frame_equal(c, d, check_freq=False)
            print(f"  {fn}: ✅ 完全一致 shape={c.shape}")
        except AssertionError as e:
            print(f"  {fn}: ❌ 不一致: {e}")
            all_consistent = False

    assert all_consistent, "值一致性校验失败"
    print("\n✅ 校验 1 通过: 缓存值与直接查询完全一致")
    print()

    # =============================================================================
    # 校验 2: 部分命中 — 仅查询未缓存的因子
    # =============================================================================
    print("-" * 80)
    print("校验 2: 部分命中 — 仅查询未缓存的因子")
    print("-" * 80)

    # 当前 TEST_FACTORS 都已缓存。新增一个未缓存的因子 EXTRA_FACTOR。
    extra_factor = EXTRA_FACTOR
    print(f"\n额外因子: {extra_factor}")

    # 部分命中: TEST_FACTORS (全命中) + extra_factor (MISS)
    mixed_factors = TEST_FACTORS + [extra_factor]
    adapter.call_count = 0
    adapter.queried_factors = []

    t0 = time.perf_counter()
    mixed_result = cache.get_pivoted(
        mixed_factors, start_date=START_DATE, end_date=END_DATE,
    )
    t1 = time.perf_counter()

    print(f"部分命中查询: call_count={adapter.call_count}, 耗时={t1-t0:.3f}s")
    print(f"  queried_factors = {adapter.queried_factors}")
    print(f"  返回因子数 = {len(mixed_result)}")

    # 关键断言: 只查询了 1 次,且只查了 extra_factor
    assert adapter.call_count == 1, f"期望 call_count=1, 实际={adapter.call_count}"
    assert adapter.queried_factors[-1] == [extra_factor], \
        f"期望 queried=[{extra_factor}], 实际={adapter.queried_factors[-1]}"
    print(f"\n✅ 校验 2 通过: 部分命中时仅查询未缓存的因子 [{extra_factor}]")

    # 校验 extra_factor 的值也与直接查询一致（排序后比较）
    if extra_factor in mixed_result:
        direct_extra = raw_adapter.get_pivoted(
            [extra_factor], start_date=START_DATE, end_date=END_DATE,
        )
        if extra_factor in direct_extra:
            try:
                d = direct_extra[extra_factor].sort_index(axis=0).sort_index(axis=1)
                c = mixed_result[extra_factor].sort_index(axis=0).sort_index(axis=1)
                pd.testing.assert_frame_equal(c, d, check_freq=False)
                print(f"  ✅ {extra_factor} 值与直接查询一致")
            except AssertionError as e:
                print(f"  ❌ {extra_factor} 值不一致: {e}")
                raise
    print()

    # =============================================================================
    # 校验 3: meta.json 透明度 — source_signature 包含 db_loaded_at_max
    # =============================================================================
    print("-" * 80)
    print("校验 3: meta.json 透明度 — source_signature 包含 db_loaded_at_max")
    print("-" * 80)

    meta_files = list(CACHE_DIR.glob("*.meta.json"))
    print(f"meta.json 文件数: {len(meta_files)} (期望 >= {len(TEST_FACTORS)})")
    assert len(meta_files) >= len(TEST_FACTORS), \
        f"期望至少 {len(TEST_FACTORS)} 个 meta.json, 实际={len(meta_files)}"

    # 检查每个 meta.json
    for mf in sorted(meta_files):
        with open(mf, "r", encoding="utf-8") as f:
            meta = json.load(f)

        # 必须字段
        assert meta["namespace"] == "factor_matrix", \
            f"namespace 错误: {meta['namespace']}"
        assert "db_loaded_at_max" in meta["source_signature"], \
            f"source_signature 缺少 db_loaded_at_max"
        assert meta["source_signature"]["query_type"] == "factor_pivot", \
            f"query_type 错误: {meta['source_signature']['query_type']}"
        assert "factor_name" in meta["source_signature"], \
            f"source_signature 缺少 factor_name"

        # 指纹字段
        assert "head_hash" in meta["data_fingerprint"], "data_fingerprint 缺少 head_hash"
        assert "tail_hash" in meta["data_fingerprint"], "data_fingerprint 缺少 tail_hash"
        assert "nan_ratio" in meta["data_fingerprint"], "data_fingerprint 缺少 nan_ratio"
        assert "shape" in meta["data_fingerprint"], "data_fingerprint 缺少 shape"

        fn = meta["source_signature"]["factor_name"]
        print(f"  ✅ {fn}: namespace={meta['namespace']}, "
              f"loaded_at={meta['source_signature']['db_loaded_at_max'][:19]}, "
              f"shape={meta['data_fingerprint']['shape']}, "
              f"head={meta['data_fingerprint']['head_hash'][:8]}")

    print(f"\n✅ 校验 3 通过: 所有 meta.json 字段完整,source_signature 含 db_loaded_at_max")
    print()

    # =============================================================================
    # 校验 4: 性能对比 — 缓存命中 vs 直接查询
    # =============================================================================
    print("-" * 80)
    print("校验 4: 性能对比 — 缓存命中 vs 直接查询")
    print("-" * 80)

    # 直接查询 3 次
    direct_times = []
    for i in range(3):
        t0 = time.perf_counter()
        raw_adapter.get_pivoted(TEST_FACTORS, start_date=START_DATE, end_date=END_DATE)
        t1 = time.perf_counter()
        direct_times.append(t1 - t0)
    direct_avg = sum(direct_times) / len(direct_times)
    print(f"直接查询 ({len(TEST_FACTORS)} 因子 × 3 次): avg={direct_avg:.3f}s, "
          f"times={[f'{t:.3f}' for t in direct_times]}")

    # 缓存命中 3 次
    cached_times = []
    adapter.call_count = 0
    for i in range(3):
        t0 = time.perf_counter()
        cache.get_pivoted(TEST_FACTORS, start_date=START_DATE, end_date=END_DATE)
        t1 = time.perf_counter()
        cached_times.append(t1 - t0)
    cached_avg = sum(cached_times) / len(cached_times)
    print(f"缓存命中 ({len(TEST_FACTORS)} 因子 × 3 次): avg={cached_avg:.3f}s, "
          f"times={[f'{t:.3f}' for t in cached_times]}")
    print(f"  call_count={adapter.call_count} (期望=0, 全部命中)")

    speedup = direct_avg / cached_avg if cached_avg > 0 else float("inf")
    print(f"\n加速比: {speedup:.2f}x (direct={direct_avg:.3f}s → cached={cached_avg:.3f}s)")

    assert adapter.call_count == 0, f"缓存命中时期望 call_count=0, 实际={adapter.call_count}"
    assert cached_avg < direct_avg, f"缓存应更快: cached={cached_avg} >= direct={direct_avg}"
    print(f"\n✅ 校验 4 通过: 缓存命中 0 次 DB 调用,加速 {speedup:.2f}x")
    print()

    # =============================================================================
    # 校验 5: 环境变量逃生舱 — FACTOR_PIPELINE_CACHE=disabled 全走 DB
    # =============================================================================
    print("-" * 80)
    print("校验 5: 环境变量逃生舱 — FACTOR_PIPELINE_CACHE=disabled")
    print("-" * 80)

    os.environ["FACTOR_PIPELINE_CACHE"] = "disabled"
    try:
        adapter.call_count = 0
        cache.get_pivoted(TEST_FACTORS, start_date=START_DATE, end_date=END_DATE)
        cache.get_pivoted(TEST_FACTORS, start_date=START_DATE, end_date=END_DATE)
        assert adapter.call_count == 2, f"env=disabled 时期望 call_count=2, 实际={adapter.call_count}"
        print(f"env=disabled 时两次查询 call_count={adapter.call_count} (期望=2, 全走 DB)")
        print(f"✅ 校验 5 通过: 环境变量逃生舱有效")
    finally:
        del os.environ["FACTOR_PIPELINE_CACHE"]
    print()

    # =============================================================================
    # 校验 6: 失效与刷新 — invalidate 单因子后重查
    # =============================================================================
    print("-" * 80)
    print("校验 6: 失效与刷新 — invalidate 单因子后重查")
    print("-" * 80)

    # 当前所有因子都已缓存。invalidate bps
    adapter.call_count = 0
    adapter.queried_factors = []

    cache.invalidate("bps", start_date=START_DATE, end_date=END_DATE)
    print(f"invalidate(bps) 完成")

    # 再请求所有因子: bps miss, 其他 hit
    t0 = time.perf_counter()
    refresh_result = cache.get_pivoted(
        TEST_FACTORS, start_date=START_DATE, end_date=END_DATE,
    )
    t1 = time.perf_counter()

    print(f"刷新查询: call_count={adapter.call_count}, 耗时={t1-t0:.3f}s")
    print(f"  queried_factors = {adapter.queried_factors}")

    assert adapter.call_count == 1, f"期望 call_count=1, 实际={adapter.call_count}"
    assert adapter.queried_factors[-1] == ["bps"], \
        f"期望 queried=['bps'], 实际={adapter.queried_factors[-1]}"

    # 校验刷新后的 bps 值仍与直接查询一致（排序后比较）
    try:
        d = direct_result["bps"].sort_index(axis=0).sort_index(axis=1)
        c = refresh_result["bps"].sort_index(axis=0).sort_index(axis=1)
        pd.testing.assert_frame_equal(c, d, check_freq=False)
        print(f"  ✅ 刷新后 bps 值与直接查询一致")
    except AssertionError as e:
        print(f"  ❌ 刷新后 PE 值不一致: {e}")
        raise

    print(f"\n✅ 校验 6 通过: invalidate 单因子后仅重查该因子,值一致")
    print()

    # =============================================================================
    # 校验 7: 不同日期范围 — 独立缓存
    # =============================================================================
    print("-" * 80)
    print("校验 7: 不同日期范围 — 独立缓存")
    print("-" * 80)

    # 记录当前缓存文件数
    files_before = len(list(CACHE_DIR.glob("*.parquet")))
    print(f"当前缓存文件数: {files_before}")

    # 用不同日期范围查询 bps
    adapter.call_count = 0
    new_start = date(2024, 6, 1)
    new_end = date(2024, 6, 30)
    cache.get_pivoted(["bps"], start_date=new_start, end_date=new_end)
    assert adapter.call_count == 1, f"期望 call_count=1 (新日期范围 MISS), 实际={adapter.call_count}"

    files_after = len(list(CACHE_DIR.glob("*.parquet")))
    print(f"新日期范围查询后缓存文件数: {files_after} (期望 > {files_before})")
    assert files_after > files_before, f"新日期范围应产生新缓存文件"

    # 相同日期范围再查: 应命中
    adapter.call_count = 0
    cache.get_pivoted(["bps"], start_date=new_start, end_date=new_end)
    assert adapter.call_count == 0, f"期望 call_count=0 (相同日期范围 HIT), 实际={adapter.call_count}"

    print(f"相同日期范围再查: call_count={adapter.call_count} (期望=0, 命中)")
    print(f"\n✅ 校验 7 通过: 不同日期范围产生独立缓存")
    print()

    # =============================================================================
    # 清理
    # =============================================================================
    adapter.close()
    print("=" * 80)
    print("🎉 Phase 3 手工校验全部通过!")
    print("=" * 80)
    print(f"  校验 1: 值一致性 (多因子) ✅")
    print(f"  校验 2: 部分命中 ✅")
    print(f"  校验 3: meta.json 透明度 ✅")
    print(f"  校验 4: 性能对比 ({speedup:.2f}x 加速) ✅")
    print(f"  校验 5: 环境变量逃生舱 ✅")
    print(f"  校验 6: 失效与刷新 ✅")
    print(f"  校验 7: 不同日期范围独立缓存 ✅")
    print()
    print(f"缓存目录: {CACHE_DIR}")
    print(f"缓存文件数: {len(list(CACHE_DIR.glob('*')))}")


if __name__ == "__main__":
    main()
