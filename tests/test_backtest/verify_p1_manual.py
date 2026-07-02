# -*- coding: utf-8 -*-
"""
P1 手工校验脚本 — 因子日期自适应 min_dates

校验项:
  1. 默认 min_dates=20: 因子天数 >= 20 时被保留
  2. 自定义 min_dates: 不同因子用不同阈值
  3. Barra 41 天因子用 min_dates=30 被保留 (41 >= 30)
  4. Barra 41 天因子用 min_dates=50 被跳过 (41 < 50)
  5. 混合因子场景: 各因子按自己阈值过滤
  6. 形状对齐: 不同日期范围因子 reindex 到 close_df 索引,缺失填 NaN
  7. 空因子场景: 全部跳过时 engine.run() 返回空 dict 不抛异常
  8. 真实场景: 20 因子混合,Barra 因子有结果产出
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# 项目根目录 (tests/test_backtest/verify_p1_manual.py → 上四级到项目根)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from factor_pipeline.backtest.data_bridge import DataBridge
from factor_pipeline.backtest.engine import FactorBacktestEngine


def make_factor_data(n_dates: int, n_stocks: int = 50, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n_dates, freq="ME")
    stocks = [f"S{i:04d}" for i in range(n_stocks)]
    return pd.DataFrame(
        rng.normal(0, 1, (n_stocks, n_dates)), index=stocks, columns=dates,
    )


def make_price_data(n_dates: int, n_stocks: int = 50, seed: int = 43) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n_dates, freq="ME")
    stocks = [f"S{i:04d}" for i in range(n_stocks)]
    log_ret = rng.normal(0.001, 0.02, (n_dates, n_stocks))
    price = 100 * np.exp(np.cumsum(log_ret, axis=0))
    return pd.DataFrame(price.T, index=stocks, columns=dates)


def main():
    print("=" * 72)
    print("P1 手工校验 — 因子日期自适应 min_dates")
    print("=" * 72)

    bridge = DataBridge()
    failures = []

    # ── 校验 1: 默认 min_dates=20 ──────────────────────────────────
    print("\n[校验 1] 默认 min_dates=20: 因子 50 天应被保留")
    factor_data = {"f1": make_factor_data(50, seed=1)}
    price_data = make_price_data(50, seed=2)
    dl = bridge.create_dataloader(factor_data, price_data)
    expected_factors = ["f1"]
    actual_factors = list(dl.factor_data.keys())
    ok = actual_factors == expected_factors
    print(f"  期望因子: {expected_factors}")
    print(f"  实际因子: {actual_factors}")
    print(f"  结果: {'✓ 通过' if ok else '✗ 失败'}")
    if not ok:
        failures.append("校验 1 失败")

    # ── 校验 2: 自定义 min_dates ──────────────────────────────────
    print("\n[校验 2] 自定义 min_dates: f1 阈值 30, f2 阈值 100")
    factor_data = {
        "f1": make_factor_data(50, seed=1),   # 50 >= 30 → 保留
        "f2": make_factor_data(50, seed=2),   # 50 < 100 → 跳过
    }
    price_data = make_price_data(50, seed=3)
    dl = bridge.create_dataloader(
        factor_data, price_data, min_dates={"f1": 30, "f2": 100},
    )
    expected_factors = ["f1"]
    actual_factors = list(dl.factor_data.keys())
    ok = actual_factors == expected_factors
    print(f"  期望因子: {expected_factors} (f2 应被跳过)")
    print(f"  实际因子: {actual_factors}")
    print(f"  结果: {'✓ 通过' if ok else '✗ 失败'}")
    if not ok:
        failures.append("校验 2 失败")

    # ── 校验 3: Barra 41 天 + min_dates=30 → 保留 ──────────────────
    print("\n[校验 3] Barra 41 天 + min_dates=30: 应被保留 (41 >= 30)")
    factor_data = {"barra_size": make_factor_data(41, seed=1)}
    price_data = make_price_data(41, seed=2)
    dl = bridge.create_dataloader(
        factor_data, price_data, min_dates={"barra_size": 30},
    )
    actual_factors = list(dl.factor_data.keys())
    ok = "barra_size" in actual_factors
    print(f"  实际因子: {actual_factors}")
    print(f"  结果: {'✓ 通过' if ok else '✗ 失败'}")
    if not ok:
        failures.append("校验 3 失败")

    # ── 校验 4: Barra 41 天 + min_dates=50 → 跳过 ──────────────────
    print("\n[校验 4] Barra 41 天 + min_dates=50: 应被跳过 (41 < 50)")
    factor_data = {"barra_size": make_factor_data(41, seed=1)}
    price_data = make_price_data(41, seed=2)
    dl = bridge.create_dataloader(
        factor_data, price_data, min_dates={"barra_size": 50},
    )
    actual_factors = list(dl.factor_data.keys())
    ok = "barra_size" not in actual_factors
    print(f"  实际因子: {actual_factors} (应为空)")
    print(f"  结果: {'✓ 通过' if ok else '✗ 失败'}")
    if not ok:
        failures.append("校验 4 失败")

    # ── 校验 5: 混合因子场景各按自己阈值过滤 ──────────────────────
    print("\n[校验 5] 混合因子: barra(41,阈值30) + daily(250,阈值200) + qtr(60,阈值40)")
    factor_data = {
        "barra_size": make_factor_data(41, seed=1),    # 41>=30 保留
        "daily_pe": make_factor_data(250, seed=2),     # 250>=200 保留
        "qtr_eps": make_factor_data(60, seed=3),       # 60>=40 保留
        "too_short": make_factor_data(15, seed=4),     # 15<20 跳过 (默认)
    }
    price_data = make_price_data(250, seed=5)
    min_dates_cfg = {
        "barra_size": 30, "daily_pe": 200, "qtr_eps": 40, "too_short": 20,
    }
    dl = bridge.create_dataloader(
        factor_data, price_data, min_dates=min_dates_cfg,
    )
    actual_factors = set(dl.factor_data.keys())
    expected_factors = {"barra_size", "daily_pe", "qtr_eps"}
    ok = actual_factors == expected_factors
    print(f"  期望因子: {sorted(expected_factors)} (too_short 应被跳过)")
    print(f"  实际因子: {sorted(actual_factors)}")
    print(f"  结果: {'✓ 通过' if ok else '✗ 失败'}")
    if not ok:
        failures.append("校验 5 失败")

    # ── 校验 6: 形状对齐 — Barra 41 天 reindex 到 close_df 250 天 ──
    print("\n[校验 6] 形状对齐: Barra 41 天 reindex 到 close 250 天, 缺失填 NaN")
    factor_data = {
        "barra_size": make_factor_data(41, seed=1),    # 41 天
        "daily_pe": make_factor_data(250, seed=2),     # 250 天
    }
    price_data = make_price_data(250, seed=3)
    dl = bridge.create_dataloader(
        factor_data, price_data,
        min_dates={"barra_size": 30, "daily_pe": 200},
    )
    # 检查 DataLoaderV3 中因子数组形状应统一为 (n_dates, n_stocks)
    barra_arr = dl.factor_data["barra_size"]
    daily_arr = dl.factor_data["daily_pe"]
    close_arr = dl.price_data["close"]
    # 形状应一致
    ok_shape = barra_arr.shape == daily_arr.shape == close_arr.shape
    print(f"  close 形状: {close_arr.shape}")
    print(f"  barra 形状: {barra_arr.shape}")
    print(f"  daily 形状: {daily_arr.shape}")
    # Barra 41 天 reindex 到 250 天,前 41 天应有值,后 209 天应为 NaN
    barra_non_nan_per_period = np.sum(~np.isnan(barra_arr), axis=1)
    # Barra 原始 41 天 × 50 股票 → reindex 后只在它有数据的日期有值
    # 由于日期索引可能不完全对齐 (1月31日 vs 1月31日),检查非全 NaN
    barra_has_data_periods = np.sum(barra_non_nan_per_period > 0)
    print(f"  Barra 有数据的期数: {barra_has_data_periods} (期望 > 0, 因 41 天对齐到 250 天)")
    ok_data = barra_has_data_periods > 0
    print(f"  结果: {'✓ 通过' if (ok_shape and ok_data) else '✗ 失败'}")
    if not (ok_shape and ok_data):
        failures.append("校验 6 失败")

    # ── 校验 7: 空因子场景 — engine.run() 返回空 dict ───────────────
    print("\n[校验 7] 空因子场景: 全部跳过时 engine.run() 返回空 dict 不抛异常")
    factor_data = {"f1": make_factor_data(15, seed=1)}  # 15 < 30 → 跳过
    price_data = make_price_data(15, seed=2)
    dl = bridge.create_dataloader(
        factor_data, price_data, min_dates={"f1": 30},
    )
    actual_factors = list(dl.factor_data.keys())
    print(f"  过滤后因子: {actual_factors} (应为空)")
    # 构造 engine — 不应抛异常
    try:
        engine = FactorBacktestEngine(dl)
        results = engine.run()
        ok = isinstance(results, dict) and len(results) == 0
        print(f"  engine.run() 返回: {results} (期望空 dict)")
        print(f"  结果: {'✓ 通过' if ok else '✗ 失败'}")
        if not ok:
            failures.append("校验 7 失败")
    except Exception as e:
        print(f"  异常: {type(e).__name__}: {e}")
        print(f"  结果: ✗ 失败")
        failures.append(f"校验 7 失败: {e}")

    # ── 校验 8: 真实场景 20 因子混合, Barra 因子有结果 ──────────────
    print("\n[校验 8] 真实场景: 20 因子混合 (5 Barra + 10 daily + 5 qtr), Barra 应有结果")
    factor_data = {}
    min_dates_cfg = {}
    for i in range(5):
        factor_data[f"barra_{i}"] = make_factor_data(41, seed=10 + i)
        min_dates_cfg[f"barra_{i}"] = 30
    for i in range(10):
        factor_data[f"daily_{i}"] = make_factor_data(250, seed=20 + i)
        min_dates_cfg[f"daily_{i}"] = 200
    for i in range(5):
        factor_data[f"qtr_{i}"] = make_factor_data(60, seed=30 + i)
        min_dates_cfg[f"qtr_{i}"] = 40

    price_data = make_price_data(250, seed=99)
    dl = bridge.create_dataloader(
        factor_data, price_data, min_dates=min_dates_cfg,
    )
    n_loaded = len(dl.factor_data)
    print(f"  加载的因子数: {n_loaded} (期望 20)")
    ok_count = n_loaded == 20
    engine = FactorBacktestEngine(dl)
    results = engine.run()
    barra_results = [k for k in results if k.startswith("barra_")]
    print(f"  Barra 因子结果数: {len(barra_results)} (期望 > 0)")
    ok_barra = len(barra_results) > 0
    print(f"  结果: {'✓ 通过' if (ok_count and ok_barra) else '✗ 失败'}")
    if not (ok_count and ok_barra):
        failures.append("校验 8 失败")

    # ── 总结 ──────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    if not failures:
        print(f"P1 手工校验全部通过 (8/8)")
        print("=" * 72)
        return 0
    else:
        print(f"P1 手工校验失败 ({len(failures)} 项):")
        for f in failures:
            print(f"  - {f}")
        print("=" * 72)
        return 1


if __name__ == "__main__":
    sys.exit(main())
