# -*- coding: utf-8 -*-
"""
P3-2: 分组并行 A/B 对比实验

验证方案 B (统一日期范围 + 全局共享 fwd_returns) 与方案 A (按日期分组)
的 IC 结果一致性。

数据源: Factor_DB 20 个真实因子 (含 Barra 41天 + 日频 250天混合场景)

输出:
  - 方案 A 的 ICIR/IC_mean (基准)
  - 方案 B 的 ICIR/IC_mean
  - 一致性对比 (max_diff)
  - 性能对比 (耗时)
"""

from __future__ import annotations

import sys
import time
import traceback
from datetime import date
from pathlib import Path
from typing import Dict, Any

import numpy as np
import pandas as pd

# factor_pipeline
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from factor_pipeline.backtest.data_bridge import DataBridge
from factor_pipeline.backtest.engine import FactorBacktestEngine
from factor_pipeline.backtest.parallel_runner import ParallelFactorRunner

# Factor_DB
sys.path.insert(0, str(Path('F:/Coding/Factor_DB')))
from query.factor_query import FactorQuery
from query.price_query import PriceQuery


# =============================================================================
# 配置
# =============================================================================

DB_PATH = str(Path('F:/Coding/Factor_DB/factor_db.duckdb'))
N_FACTORS = 20
DATE_START = date(2020, 1, 1)
DATE_END = date(2024, 12, 31)


# =============================================================================
# 数据加载 (复用 test_integration_real_data.py 的逻辑)
# =============================================================================

def load_data():
    """加载 20 个真实因子和价格数据"""
    print("=" * 70)
    print(f"Step 1: 加载 {N_FACTORS} 个真实因子数据")
    print("=" * 70)

    fq = FactorQuery(DB_PATH)
    pq = PriceQuery(DB_PATH)

    all_factors = fq.list_factors()
    print(f"  可用因子总数: {len(all_factors)}")

    selected_factors = all_factors[:N_FACTORS]
    print(f"  选择前 {N_FACTORS} 个: {selected_factors}")

    # 因子矩阵
    factor_matrix = fq.get_factor_matrix(
        selected_factors,
        start_date=DATE_START,
        end_date=DATE_END,
    )
    print(f"  因子矩阵 shape: {factor_matrix.shape}")

    # 价格矩阵
    price_matrix = pq.get_price_matrix(
        field='close',
        start_date=DATE_START,
        end_date=DATE_END,
    )
    print(f"  价格矩阵 shape: {price_matrix.shape}")

    # 转换为 Pipeline 输入格式: Dict[str, pd.DataFrame] (index=stock, columns=date)
    pipeline_input = {}
    for factor_name in selected_factors:
        if factor_name not in factor_matrix.columns:
            continue
        pivoted = factor_matrix.pivot(
            index='stock_code',
            columns='trade_date',
            values=factor_name,
        )
        valid_dates = pivoted.columns[pivoted.notna().sum() >= 20]
        if len(valid_dates) < 20:
            continue
        pipeline_input[factor_name] = pivoted[valid_dates]

    # 价格转置为 (stocks, dates)
    price_pivoted = price_matrix.T
    price_pivoted.index = price_pivoted.index.astype(str)
    price_pivoted.columns = pd.to_datetime(price_pivoted.columns)

    print(f"  成功加载因子数: {len(pipeline_input)}")
    print(f"  价格 shape: {price_pivoted.shape}")

    # 打印每个因子的日期数 (用于分组分析)
    print("\n  --- 因子日期数分布 ---")
    date_counts = {name: df.shape[1] for name, df in pipeline_input.items()}
    for name, n in sorted(date_counts.items(), key=lambda x: x[1]):
        print(f"    {name:25s}: {n:4d} 天")

    return pipeline_input, price_pivoted


# =============================================================================
# 方案 A: 按日期分组 + 组内共享 (当前实现)
# =============================================================================

def run_scheme_a(factor_data, price_data):
    """方案 A: 使用 ParallelFactorRunner (按日期分组)"""
    print("\n" + "=" * 70)
    print("Step 2: 方案 A — 按日期分组 + 组内共享 (当前实现)")
    print("=" * 70)

    runner = ParallelFactorRunner(n_workers=4)
    t0 = time.time()
    results = runner.run(factor_data, price_data, config={'top_n': 0.2})
    elapsed = time.time() - t0

    print(f"  方案 A 耗时: {elapsed:.2f}s")
    print(f"  成功回测因子数: {len(results)}")
    return results, elapsed


# =============================================================================
# 方案 B: 统一日期范围 + 全局共享 fwd_returns (临时实现)
# =============================================================================

def run_scheme_b(factor_data, price_data):
    """方案 B: 统一日期范围 + 全局共享 fwd_returns

    核心改动:
      1. 不分组,所有因子共享同一个 fwd_returns (基于完整 price_data)
      2. worker 内部不裁剪 price_data,让 data_bridge 的 reindex 处理对齐
    """
    print("\n" + "=" * 70)
    print("Step 3: 方案 B — 统一日期范围 + 全局共享 fwd_returns")
    print("=" * 70)

    t0 = time.time()

    # 1. 全局计算 fwd_returns (基于完整 price_data)
    bridge = DataBridge()

    # 用第一个因子获取股票集合,但用完整 price_data 计算 fwd
    # 关键: fwd_returns 基于 price_data 的完整日期范围
    cs = price_data.index
    cd = price_data.columns

    # 构造一个 "虚拟因子" 仅用于触发 fwd_returns 计算
    # 实际上我们直接用 price_data 创建 DataLoaderV3
    dummy_factor = {next(iter(factor_data)): factor_data[next(iter(factor_data))]}
    pa_full = price_data.loc[list(cs), list(cd)]
    dl_full = bridge.create_dataloader(dummy_factor, pa_full)
    engine_full = FactorBacktestEngine(dl_full)
    fwd_global = engine_full.compute_fwd_returns()
    print(f"  全局 fwd_returns shape: {fwd_global.shape}")
    print(f"  fwd_returns 计算耗时: {time.time() - t0:.2f}s")

    # 2. 所有因子共享 fwd_global,串行回测 (模拟并行,只验证正确性)
    t1 = time.time()
    results = {}
    for factor_name, factor_df in factor_data.items():
        try:
            # 方案 B 关键: 不裁剪 price_data 到因子日期范围
            # 让 data_bridge 的 reindex 处理对齐
            cs_factor = factor_df.index.intersection(price_data.index)
            fa = factor_df.loc[list(cs_factor), :]
            pa = price_data.loc[list(cs_factor), :]

            dl = bridge.create_dataloader({factor_name: fa}, pa)

            # 共享 fwd_global: 形状检查
            n_dates = dl.n_dates
            n_stocks = dl.n_stocks
            shared_fwd = None
            if fwd_global.shape == (n_dates - 1, n_stocks):
                shared_fwd = fwd_global
            else:
                # 形状不匹配 (股票数不同) → 回退自计算
                pass

            engine = FactorBacktestEngine(
                dl, config={'top_n': 0.2}, fwd_returns=shared_fwd,
            )
            engine.run()
            summary = engine.summary()
            results[factor_name] = summary[factor_name]

        except Exception as e:
            print(f"  [FAIL] {factor_name}: {e}")

    elapsed = time.time() - t0
    print(f"  方案 B 总耗时: {elapsed:.2f}s (含 fwd 计算 {time.time()-t0:.2f}s + 回测 {time.time()-t1:.2f}s)")
    print(f"  成功回测因子数: {len(results)}")
    return results, elapsed


# =============================================================================
# 一致性对比
# =============================================================================

def compare_results(results_a, results_b):
    """对比方案 A 和 B 的结果一致性"""
    print("\n" + "=" * 70)
    print("Step 4: A/B 结果一致性对比")
    print("=" * 70)

    common_factors = set(results_a.keys()) & set(results_b.keys())
    print(f"  共同因子数: {len(common_factors)}")

    if not common_factors:
        print("  ⚠ 无共同因子,无法对比")
        return

    print(f"\n  {'因子':25s} {'A-ICIR':>10s} {'B-ICIR':>10s} {'diff':>10s}  "
          f"{'A-IC':>10s} {'B-IC':>10s} {'diff':>10s}")
    print("  " + "-" * 95)

    icir_diffs = []
    ic_diffs = []
    for name in sorted(common_factors):
        a = results_a[name]
        b = results_b[name]
        a_icir = a.get('rank_icir', np.nan)
        b_icir = b.get('rank_icir', np.nan)
        a_ic = a.get('mean_rank_ic', np.nan)
        b_ic = b.get('mean_rank_ic', np.nan)

        icir_diff = abs(a_icir - b_icir) if not (np.isnan(a_icir) or np.isnan(b_icir)) else np.nan
        ic_diff = abs(a_ic - b_ic) if not (np.isnan(a_ic) or np.isnan(b_ic)) else np.nan

        if not np.isnan(icir_diff):
            icir_diffs.append(icir_diff)
        if not np.isnan(ic_diff):
            ic_diffs.append(ic_diff)

        a_icir_str = f"{a_icir:.4f}" if not np.isnan(a_icir) else "NaN"
        b_icir_str = f"{b_icir:.4f}" if not np.isnan(b_icir) else "NaN"
        a_ic_str = f"{a_ic:.6f}" if not np.isnan(a_ic) else "NaN"
        b_ic_str = f"{b_ic:.6f}" if not np.isnan(b_ic) else "NaN"
        d_icir_str = f"{icir_diff:.6f}" if not np.isnan(icir_diff) else "NaN"
        d_ic_str = f"{ic_diff:.8f}" if not np.isnan(ic_diff) else "NaN"

        print(f"  {name:25s} {a_icir_str:>10s} {b_icir_str:>10s} {d_icir_str:>10s}  "
              f"{a_ic_str:>10s} {b_ic_str:>10s} {d_ic_str:>10s}")

    print("\n  --- 一致性统计 ---")
    if icir_diffs:
        print(f"  ICIR diff: max={max(icir_diffs):.8f}, mean={np.mean(icir_diffs):.8f}")
    if ic_diffs:
        print(f"  IC   diff: max={max(ic_diffs):.8f}, mean={np.mean(ic_diffs):.8f}")

    # 一致性判定
    tolerance = 1e-6
    icir_consistent = all(d < tolerance for d in icir_diffs) if icir_diffs else False
    ic_consistent = all(d < tolerance for d in ic_diffs) if ic_diffs else False

    print(f"\n  ICIR 一致性 (容差 {tolerance}): {'✓ 通过' if icir_consistent else '✗ 失败'}")
    print(f"  IC   一致性 (容差 {tolerance}): {'✓ 通过' if ic_consistent else '✗ 失败'}")

    if icir_consistent and ic_consistent:
        print("\n  ✓ 方案 B 与方案 A 结果一致,可以安全替换")
    else:
        print("\n  ⚠ 方案 B 与方案 A 存在差异,需进一步分析")


# =============================================================================
# 主函数
# =============================================================================

def main():
    print("=" * 70)
    print("P3-2: 分组并行 A/B 对比实验")
    print("=" * 70)

    # 加载数据
    factor_data, price_data = load_data()

    if not factor_data:
        print("FATAL: 无因子数据")
        return

    # 方案 A
    results_a, time_a = run_scheme_a(factor_data, price_data)

    # 方案 B
    results_b, time_b = run_scheme_b(factor_data, price_data)

    # 一致性对比
    compare_results(results_a, results_b)

    # 性能对比
    print("\n" + "=" * 70)
    print("Step 5: 性能对比")
    print("=" * 70)
    print(f"  方案 A 耗时: {time_a:.2f}s")
    print(f"  方案 B 耗时: {time_b:.2f}s")
    print(f"  加速比: {time_a / time_b:.2f}x" if time_b > 0 else "")

    print("\n" + "=" * 70)
    print("实验完成")
    print("=" * 70)


if __name__ == '__main__':
    main()
