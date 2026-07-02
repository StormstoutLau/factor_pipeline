# -*- coding: utf-8 -*-
"""
P4: 集成测试 — Factor_DB 20个真实因子全流程跑通

从 Factor_DB 拉取真实因子数据，经过:
  数据准备 → 指纹提取 → 多维分类 → 管道处理 → 回测引擎 → 健康评估 → 漂移检测

记录所有崩溃点。
"""

import sys
import traceback
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

# factor_pipeline (祖父目录: f:\Coding)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Factor_DB (没有根 __init__.py，直接导入子模块)
sys.path.insert(0, str(Path('F:/Coding/Factor_DB')))
from query.factor_query import FactorQuery
from query.price_query import PriceQuery

# factor_pipeline
from factor_pipeline.backtest.data_bridge import DataBridge
from factor_pipeline.backtest.engine import FactorBacktestEngine
from factor_pipeline.backtest.unified_drift import UnifiedDriftReporter
from factor_pipeline.backtest.health_bridge import HealthMonitorAdapter


# =============================================================================
# 配置
# =============================================================================

DB_PATH = str(Path('F:/Coding/Factor_DB/factor_db.duckdb'))
N_FACTORS = 20
DATE_START = date(2020, 1, 1)
DATE_END = date(2024, 12, 31)

crash_log = []
success_log = []


def log_crash(stage: str, factor_name: str, error: Exception):
    msg = f"[CRASH] {stage} | {factor_name} | {type(error).__name__}: {error}"
    crash_log.append(msg)
    print(msg)


def log_success(stage: str, factor_name: str, detail: str = ''):
    msg = f"[OK] {stage} | {factor_name} | {detail}"
    success_log.append(msg)
    print(msg)


# =============================================================================
# Step 1: 连接数据库，列出可用因子
# =============================================================================

print("=" * 70)
print("Step 1: 连接 Factor_DB，列出可用因子")
print("=" * 70)

try:
    fq = FactorQuery(DB_PATH)
    pq = PriceQuery(DB_PATH)
    print(f"  连接成功: {DB_PATH}")
except Exception as e:
    print(f"  FATAL: 数据库连接失败: {e}")
    sys.exit(1)

try:
    all_factors = fq.list_factors()
    print(f"  可用因子总数: {len(all_factors)}")
    print(f"  前 30 个: {all_factors[:30]}")
except Exception as e:
    log_crash("list_factors", "ALL", e)
    sys.exit(1)

# 选择 20 个因子
selected_factors = all_factors[:N_FACTORS]
print(f"\n  选择前 {N_FACTORS} 个因子: {selected_factors}")


# =============================================================================
# Step 2: 查询因子宽表数据
# =============================================================================

print("\n" + "=" * 70)
print("Step 2: 查询因子宽表数据")
print("=" * 70)

try:
    factor_matrix = fq.get_factor_matrix(
        selected_factors,
        start_date=DATE_START,
        end_date=DATE_END,
    )
    print(f"  因子矩阵 shape: {factor_matrix.shape}")
    print(f"  列: {list(factor_matrix.columns)[:10]}...")
    print(f"  日期范围: {factor_matrix['trade_date'].min()} ~ {factor_matrix['trade_date'].max()}")
except Exception as e:
    log_crash("get_factor_matrix", "ALL", e)
    traceback.print_exc()
    sys.exit(1)


# =============================================================================
# Step 3: 查询价格数据
# =============================================================================

print("\n" + "=" * 70)
print("Step 3: 查询价格数据")
print("=" * 70)

try:
    price_matrix = pq.get_price_matrix(
        field='close',
        start_date=DATE_START,
        end_date=DATE_END,
    )
    print(f"  价格矩阵 shape: {price_matrix.shape}")
    print(f"  价格矩阵列: {list(price_matrix.columns)}")
    print(f"  价格矩阵 index name: {price_matrix.index.name}")
except Exception as e:
    log_crash("get_price_matrix", "ALL", e)
    traceback.print_exc()
    # 价格数据缺失不应阻止测试，尝试用因子数据构造
    price_matrix = None
    print("  WARNING: 价格数据获取失败，将用因子数据构造虚拟价格")


# =============================================================================
# Step 4: 转换为 Pipeline 输入格式
# =============================================================================

print("\n" + "=" * 70)
print("Step 4: 转换为 Pipeline 输入格式")
print("=" * 70)

# 因子矩阵: (trade_date, stock_code, factor_1, factor_2, ...)
# 需要转换为: Dict[str, pd.DataFrame] (index=stock, columns=date)

pipeline_input = {}
for factor_name in selected_factors:
    try:
        if factor_name not in factor_matrix.columns:
            log_crash("pivot", factor_name, ValueError(f"列 {factor_name} 不存在"))
            continue

        # 透视: (trade_date, stock_code, factor_value) → (stock_code, trade_date)
        pivoted = factor_matrix.pivot(
            index='stock_code',
            columns='trade_date',
            values=factor_name,
        )
        # 仅保留至少有 20 个非空值的日期
        valid_dates = pivoted.columns[pivoted.notna().sum() >= 20]
        if len(valid_dates) < 20:
            log_crash("pivot", factor_name, ValueError(f"非空日期不足: {len(valid_dates)}"))
            continue

        pivoted = pivoted[valid_dates]
        pipeline_input[factor_name] = pivoted
        log_success("pivot", factor_name, f"shape={pivoted.shape}")

    except Exception as e:
        log_crash("pivot", factor_name, e)
        traceback.print_exc()

print(f"\n  成功转换的因子数: {len(pipeline_input)}")

if len(pipeline_input) == 0:
    print("  FATAL: 没有因子成功转换！")
    sys.exit(1)


# =============================================================================
# Step 5: 运行回测引擎
# =============================================================================

print("\n" + "=" * 70)
print("Step 5: 运行回测引擎")
print("=" * 70)

# 构造价格数据
# price_matrix 已是宽表: index=trade_date, columns=stock_codes
# 转置为 stocks × dates 格式供 DataBridge 使用
if price_matrix is not None:
    price_pivoted = price_matrix.T  # (stock_codes, trade_dates)
    price_pivoted.index = price_pivoted.index.astype(str)
    price_pivoted.columns = pd.to_datetime(price_pivoted.columns)
    print(f"  价格数据转置后 shape: {price_pivoted.shape}")
else:
    # 虚拟价格: 用因子数据构造
    price_pivoted = pd.DataFrame(
        np.random.lognormal(0, 0.02, (100, 60)),
        index=[f'STOCK_{i:04d}' for i in range(100)],
        columns=pd.date_range('2020-01-01', '2024-12-31', freq='ME'),
    )

bridge = DataBridge()
engine_results = {}

for factor_name in pipeline_input:
    try:
        factor_df = pipeline_input[factor_name]

        # 对齐因子和价格的日期 + 股票
        common_dates = factor_df.columns.intersection(price_pivoted.columns)
        common_stocks = factor_df.index.intersection(price_pivoted.index)

        if len(common_dates) < 20:
            log_crash("engine", factor_name, ValueError(f"共同日期不足: {len(common_dates)}"))
            continue
        if len(common_stocks) < 5:
            log_crash("engine", factor_name, ValueError(f"共同股票不足: {len(common_stocks)}"))
            continue

        factor_aligned = factor_df.loc[list(common_stocks), list(common_dates)]
        price_aligned = price_pivoted.loc[list(common_stocks), list(common_dates)]

        # 创建 DataLoaderV3
        dl = bridge.create_dataloader({factor_name: factor_aligned}, price_aligned)

        # 运行回测
        engine = FactorBacktestEngine(dl)
        engine.run()
        summary = engine.summary()

        # summary[factor_name] 包含该因子的所有标量指标
        engine_results[factor_name] = summary[factor_name]
        icir = summary[factor_name].get('rank_icir', np.nan)
        ic_mean = summary[factor_name].get('mean_rank_ic', np.nan)
        log_success("engine", factor_name,
                    f"ICIR={icir:.3f}, IC_mean={ic_mean:.4f}, "
                    f"dates={len(common_dates)}, stocks={len(common_stocks)}")

    except Exception as e:
        log_crash("engine", factor_name, e)
        traceback.print_exc()

print(f"\n  成功回测的因子数: {len(engine_results)}")


# =============================================================================
# Step 6: 健康度评估
# =============================================================================

print("\n" + "=" * 70)
print("Step 6: 健康度评估")
print("=" * 70)

health_adapter = HealthMonitorAdapter()
health_reports = {}

for factor_name in engine_results:
    try:
        # build_report_from_engine(factor_name, engine_result_dict)
        report = health_adapter.build_report_from_engine(
            factor_name, engine_results[factor_name]
        )
        health_reports[factor_name] = report
        log_success("health", factor_name,
                    f"health_score={report.health_score:.1f}")
    except Exception as e:
        log_crash("health", factor_name, e)
        traceback.print_exc()

print(f"\n  成功评估的因子数: {len(health_reports)}")


# =============================================================================
# Step 7: 漂移检测
# =============================================================================

print("\n" + "=" * 70)
print("Step 7: 漂移检测")
print("=" * 70)

drift_reporter = UnifiedDriftReporter()
drift_results = {}

for factor_name in engine_results:
    try:
        result_dict = engine_results[factor_name]
        verdict = drift_reporter.evaluate_from_engine(factor_name, result_dict)
        drift_results[factor_name] = verdict
        log_success("drift", factor_name,
                    f"level={verdict['level']}, combined={verdict['combined_score']:.1f}")
    except Exception as e:
        log_crash("drift", factor_name, e)
        traceback.print_exc()


# =============================================================================
# Step 8: 汇总报告
# =============================================================================

print("\n" + "=" * 70)
print("Step 8: 汇总报告")
print("=" * 70)

total = len(selected_factors)
pivoted = len(pipeline_input)
backtested = len(engine_results)
health_checked = len(health_reports)
drift_checked = len(drift_results)

print(f"\n  因子总数: {total}")
print(f"  成功透视: {pivoted} ({pivoted/total*100:.0f}%)")
print(f"  成功回测: {backtested} ({backtested/total*100:.0f}%)")
print(f"  健康评估: {health_checked} ({health_checked/total*100:.0f}%)")
print(f"  漂移检测: {drift_checked} ({drift_checked/total*100:.0f}%)")

# 崩溃点汇总
print(f"\n  崩溃点总数: {len(crash_log)}")
if crash_log:
    print("\n  --- 崩溃点明细 ---")
    for msg in crash_log:
        print(f"  {msg}")
else:
    print("  无崩溃点！全流程通过！")

# ICIR 排名
if engine_results:
    print("\n  --- ICIR 排名 (Top 10) ---")
    icir_ranking = []
    for name, res in engine_results.items():
        icir = res.get('rank_icir', np.nan)
        if not np.isnan(icir):
            icir_ranking.append((name, icir))
    icir_ranking.sort(key=lambda x: x[1], reverse=True)
    for i, (name, icir) in enumerate(icir_ranking[:10]):
        print(f"  {i+1:2d}. {name:20s} ICIR={icir:.4f}")

# 漂移级别分布
if drift_results:
    print("\n  --- 漂移级别分布 ---")
    level_counts = {}
    for name, v in drift_results.items():
        level = v['level']
        level_counts[level] = level_counts.get(level, 0) + 1
    for level, count in sorted(level_counts.items()):
        print(f"  {level}: {count} 个因子")

print("\n" + "=" * 70)
print("集成测试完成")
print("=" * 70)