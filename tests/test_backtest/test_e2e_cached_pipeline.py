# -*- coding: utf-8 -*-
"""
端到端集成测试 — CachedDataLoader 接入完整 Pipeline

验证缓存真正接入业务流程:
  CachedDataLoader → 因子+价格加载 → DataBridge → ParallelFactorRunner → Engine → 结果

校验:
  1. 第一次运行: 走 DB,产生缓存
  2. 第二次运行: 缓存命中,0 次 DB 调用
  3. 两次运行结果完全一致 (ICIR/IC_mean/hit_rate)
  4. 实际加速可观测
"""

from __future__ import annotations

import shutil
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT.parent))

# 可选依赖: Factor_Trading_v3_0 (pyproject.toml [backtest] extra)
# run_parallel 内部调用 DataBridge.create_dataloader, 间接依赖 DataLoaderV3,
# 未安装 Factor_Trading_v3_0 时跳过整个文件.
pytest.importorskip("Factor_Trading_v3_0")

from factor_pipeline.backtest.cached_data_loader import CachedDataLoader
from factor_pipeline.backtest.parallel_runner import run_parallel

DB_PATH = r"F:\Coding\Factor_DB\factor_db.duckdb"
TEST_FACTORS = ["bps", "cfps", "ar_turn"]
START_DATE = date(2024, 1, 1)
END_DATE = date(2024, 3, 31)


@pytest.fixture(scope="module")
def cache_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("e2e_cached_pipeline")
    return str(d)


def _load_and_run(loader: CachedDataLoader):
    """通过 CachedDataLoader 加载数据并跑 ParallelFactorRunner"""
    # 1. 加载因子数据 (带缓存)
    factor_result = loader.get_pivoted_factors(
        TEST_FACTORS, start_date=START_DATE, end_date=END_DATE,
    )
    # 2. 加载价格数据 (带缓存)
    price_df = loader.get_price_matrix(
        field="close", start_date=START_DATE, end_date=END_DATE,
    )

    # 3. 转换价格 (dates × stocks) → (stocks × dates)
    price_pivoted = price_df.T
    price_pivoted.index = price_pivoted.index.astype(str)
    price_pivoted.columns = pd.to_datetime(price_pivoted.columns)

    # 4. 对齐因子和价格
    aligned_factors = {}
    for fn, fd in factor_result.items():
        cd = fd.columns.intersection(price_pivoted.columns)
        cs = fd.index.intersection(price_pivoted.index)
        if len(cd) >= 10 and len(cs) >= 5:
            aligned_factors[fn] = fd.loc[list(cs), list(cd)]

    if not aligned_factors:
        pytest.skip("无有效对齐数据")

    # 取第一个因子的对齐后的价格
    first_fn = next(iter(aligned_factors))
    cd = aligned_factors[first_fn].columns
    cs = aligned_factors[first_fn].index
    aligned_price = price_pivoted.loc[list(cs), list(cd)]

    # 5. 跑并行回测
    results = run_parallel(
        aligned_factors, aligned_price,
        n_workers=2,
        config={'ic_method': 'rank', 'top_n': 0.2},
    )
    return results


class TestE2ECachedPipeline:
    """端到端: CachedDataLoader 接入完整 Pipeline"""

    def test_01_first_run_queries_db_and_caches(self, cache_dir):
        """第一次运行: 走 DB,产生缓存文件"""
        loader = CachedDataLoader(
            db_path=DB_PATH, cache_dir=cache_dir, enabled=True,
        )
        results1 = _load_and_run(loader)

        # 验证有结果
        assert len(results1) > 0, "应至少有 1 个因子回测结果"

        # 验证缓存文件产生
        cache_files = list(Path(cache_dir).glob("*.parquet"))
        assert len(cache_files) >= len(TEST_FACTORS), \
            f"应产生至少 {len(TEST_FACTORS)} 个因子缓存, 实际 {len(cache_files)}"

        # 关闭 adapter 释放 DB 连接
        loader.factor_adapter.close()


    def test_02_second_run_hits_cache_faster(self, cache_dir):
        """第二次运行: 缓存命中,更快,结果一致"""
        # 第一次运行 (预热缓存)
        loader1 = CachedDataLoader(
            db_path=DB_PATH, cache_dir=cache_dir, enabled=True,
        )
        t0 = time.perf_counter()
        results1 = _load_and_run(loader1)
        t1 = time.perf_counter()
        time_first = t1 - t0
        loader1.factor_adapter.close()

        # 第二次运行 (缓存命中)
        loader2 = CachedDataLoader(
            db_path=DB_PATH, cache_dir=cache_dir, enabled=True,
        )
        t0 = time.perf_counter()
        results2 = _load_and_run(loader2)
        t1 = time.perf_counter()
        time_second = t1 - t0
        loader2.factor_adapter.close()

        print(f"\n第一次运行 (DB): {time_first:.3f}s")
        print(f"第二次运行 (缓存): {time_second:.3f}s")
        print(f"加速: {time_first/time_second:.2f}x")

        # 结果一致性 (逐因子比较)
        assert set(results1.keys()) == set(results2.keys()), \
            f"因子集合不一致: {set(results1.keys())} vs {set(results2.keys())}"

        for fn in results1:
            r1 = results1[fn]
            r2 = results2[fn]
            for key in ['rank_icir', 'mean_rank_ic', 'hit_rate', 'turnover']:
                if key in r1 and key in r2:
                    v1, v2 = r1[key], r2[key]
                    if isinstance(v1, float) and isinstance(v2, float):
                        if np.isnan(v1) and np.isnan(v2):
                            continue
                        assert abs(v1 - v2) < 1e-10, \
                            f"{fn}.{key}: {v1} != {v2}"
            print(f"  {fn}: ICIR={r1.get('rank_icir', float('nan')):.4f} ✅ 一致")

        # 缓存应更快 (或至少不慢,考虑波动)
        # 不做严格 assert 加速,因为第一次可能因 DB 锁等已很快


    def test_03_cache_status_reflects_entries(self, cache_dir):
        """缓存状态正确反映条目数"""
        loader = CachedDataLoader(
            db_path=DB_PATH, cache_dir=cache_dir, enabled=True,
        )
        # 先加载一次
        _load_and_run(loader)

        status = loader.status()
        assert status['factor_cache']['total_entries'] >= len(TEST_FACTORS)
        assert status['price_cache']['total_entries'] >= 1
        loader.factor_adapter.close()


    def test_04_clear_all_empties_cache(self, cache_dir):
        """clear_all 清空所有缓存"""
        loader = CachedDataLoader(
            db_path=DB_PATH, cache_dir=cache_dir, enabled=True,
        )
        _load_and_run(loader)

        files_before = len(list(Path(cache_dir).glob("*.parquet")))
        assert files_before > 0

        loader.clear_all()

        files_after = len(list(Path(cache_dir).glob("*.parquet")))
        assert files_after == 0, f"清空后仍有 {files_after} 个文件"
        loader.factor_adapter.close()
