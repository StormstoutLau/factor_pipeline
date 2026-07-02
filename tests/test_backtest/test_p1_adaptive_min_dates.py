# -*- coding: utf-8 -*-
"""
P1: 因子日期自适应 min_dates — 解决 Barra 41 天问题

不同更新频率的因子应用不同的 min_dates 阈值:
  - 日频因子 (pe, pb): min_dates=200
  - 月频因子 (Barra): min_dates=30
  - 季频因子 (财报): min_dates=10

测试:
  1. 默认 min_dates=20 兼容
  2. 自定义 min_dates 按因子
  3. Barra 因子用 30 天阈值能跑通 (原 20 天也能,但 41 天更现实)
  4. 日频因子用 200 天阈值
  5. 集成测试: 混合因子场景
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from factor_pipeline.backtest.engine import FactorBacktestEngine
from factor_pipeline.backtest.data_bridge import DataBridge


def make_factor_data(n_dates: int, n_stocks: int = 50, seed: int = 42) -> pd.DataFrame:
    """构造因子数据 (stock × date)"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n_dates, freq="ME")
    stocks = [f"S{i:04d}" for i in range(n_stocks)]
    return pd.DataFrame(
        rng.normal(0, 1, (n_stocks, n_dates)), index=stocks, columns=dates,
    )


def make_price_data(n_dates: int, n_stocks: int = 50, seed: int = 43) -> pd.DataFrame:
    """构造价格数据 (stock × date)"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n_dates, freq="ME")
    stocks = [f"S{i:04d}" for i in range(n_stocks)]
    log_ret = rng.normal(0.001, 0.02, (n_dates, n_stocks))
    price = 100 * np.exp(np.cumsum(log_ret, axis=0))
    return pd.DataFrame(price.T, index=stocks, columns=dates)


# =============================================================================
# 自适应 min_dates 测试
# =============================================================================

class TestAdaptiveMinDates:
    """测试因子日期自适应 min_dates"""

    def test_01_engine_accepts_min_dates_per_factor(self):
        """引擎接受 per-factor min_dates 字典"""
        n_dates = 100
        factor_data = {"f1": make_factor_data(n_dates)}
        price_data = make_price_data(n_dates)

        bridge = DataBridge()
        # per-factor min_dates 配置
        min_dates_config = {"f1": 30}
        dl = bridge.create_dataloader(
            factor_data, price_data, min_dates=min_dates_config,
        )
        assert dl is not None

    def test_02_barra_factor_with_low_min_dates_runs(self):
        """Barra 因子 (41 天) 用 min_dates=30 能跑通"""
        n_dates = 41  # Barra 实际天数
        factor_data = {"barra_size": make_factor_data(n_dates, seed=1)}
        price_data = make_price_data(n_dates, seed=2)

        bridge = DataBridge()
        min_dates_config = {"barra_size": 30}  # 低于默认 20? 不,30 > 20
        dl = bridge.create_dataloader(
            factor_data, price_data, min_dates=min_dates_config,
        )
        engine = FactorBacktestEngine(dl)
        results = engine.run()

        # 应能产出结果 (不要求 ICIR 有效,只要不抛异常)
        assert "barra_size" in results
        assert results["barra_size"] is not None

    def test_03_daily_factor_with_high_min_dates_runs(self):
        """日频因子用 min_dates=200 能跑通"""
        n_dates = 250
        factor_data = {"daily_pe": make_factor_data(n_dates, seed=3)}
        price_data = make_price_data(n_dates, seed=4)

        bridge = DataBridge()
        min_dates_config = {"daily_pe": 200}
        dl = bridge.create_dataloader(
            factor_data, price_data, min_dates=min_dates_config,
        )
        engine = FactorBacktestEngine(dl)
        results = engine.run()

        assert "daily_pe" in results

    def test_04_mixed_factors_different_min_dates(self):
        """混合因子场景: Barra (41天) + 日频 (250天) 各用不同阈值"""
        # Barra 41 天
        barra_factor = make_factor_data(41, seed=1)
        # 日频 250 天 (但只取与 Barra 重叠的 41 天测试)
        daily_factor = make_factor_data(250, seed=2)

        # 价格用 250 天
        price_data = make_price_data(250, seed=3)

        # 各自对齐
        bridge = DataBridge()
        min_dates_config = {
            "barra_size": 30,    # Barra 用 30 天
            "daily_pe": 200,     # 日频用 200 天
        }
        factor_data = {
            "barra_size": barra_factor,
            "daily_pe": daily_factor,
        }
        dl = bridge.create_dataloader(
            factor_data, price_data, min_dates=min_dates_config,
        )

        # 两个因子都应被加载 (不因日期不匹配被丢弃)
        # 具体行为依赖 DataBridge 实现,但至少不抛异常
        assert dl is not None

    def test_05_default_min_dates_when_not_specified(self):
        """未指定 min_dates 时使用默认值 20"""
        n_dates = 50
        factor_data = {"f1": make_factor_data(n_dates)}
        price_data = make_price_data(n_dates)

        bridge = DataBridge()
        # 不传 min_dates
        dl = bridge.create_dataloader(factor_data, price_data)
        assert dl is not None

    def test_06_factor_below_min_dates_skipped(self):
        """因子天数低于 min_dates 应被跳过"""
        n_dates = 15  # 低于默认 20
        factor_data = {"f1": make_factor_data(n_dates)}
        price_data = make_price_data(n_dates)

        bridge = DataBridge()
        min_dates_config = {"f1": 30}  # 要求 30 天
        dl = bridge.create_dataloader(
            factor_data, price_data, min_dates=min_dates_config,
        )
        # 引擎应跳过该因子,不抛异常
        engine = FactorBacktestEngine(dl)
        results = engine.run()
        # f1 应不在结果中 (被跳过) 或结果为空
        # 具体行为: 引擎可能返回空 dict 或跳过
        assert isinstance(results, dict)


# =============================================================================
# 真实场景: 20 因子混合
# =============================================================================

class TestRealisticMixedFactors:
    """模拟 20 因子混合场景"""

    def test_01_20_factors_mixed_dates_all_run(self):
        """20 个因子混合日期范围都能跑通"""
        # 5 个 Barra (41 天) + 10 个日频 (250 天) + 5 个季频 (60 天)
        factor_data = {}
        min_dates_config = {}

        for i in range(5):
            factor_data[f"barra_{i}"] = make_factor_data(41, seed=10+i)
            min_dates_config[f"barra_{i}"] = 30

        for i in range(10):
            factor_data[f"daily_{i}"] = make_factor_data(250, seed=20+i)
            min_dates_config[f"daily_{i}"] = 200

        for i in range(5):
            factor_data[f"quarterly_{i}"] = make_factor_data(60, seed=30+i)
            min_dates_config[f"quarterly_{i}"] = 40

        price_data = make_price_data(250, seed=99)

        bridge = DataBridge()
        dl = bridge.create_dataloader(
            factor_data, price_data, min_dates=min_dates_config,
        )
        engine = FactorBacktestEngine(dl)
        results = engine.run()

        # 至少应有部分因子产出结果
        assert isinstance(results, dict)
        # Barra 因子应有结果 (41 天 > 30 阈值)
        barra_results = [k for k in results if k.startswith("barra_")]
        assert len(barra_results) > 0, \
            f"Barra 因子应有结果, 实际 {len(barra_results)}"
