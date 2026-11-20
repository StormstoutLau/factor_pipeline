# -*- coding: utf-8 -*-
"""v3.9.0 E4（S5）：交易现实性验收（T390-27 ~ T390-35）。"""
import numpy as np
import pytest

from backtest.tradability import (
    CostModel,
    LimitRule,
    _validate_rules,
    apply_tradability,
    can_trade,
    limit_price,
    rule_pct,
)


def _case(T=3, N=1, dates=None):
    dates = dates or np.array(
        ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"][:T])
    return {
        "target_w": np.zeros((T, N)),
        "prev_close": np.full((T, N), 10.0),
        "high": np.full((T, N), 10.2),
        "low": np.full((T, N), 9.8),
        "close": np.full((T, N), 10.0),
        "open_": np.full((T, N), 10.0),
        "volume": np.full((T, N), 1e6),
        "suspended": np.zeros((T, N), dtype=bool),
        "board": np.array(["main"] * N),
        "is_st": np.zeros(N, dtype=bool),
        "dates": dates,
    }


def _run(case, policy=None):
    return apply_tradability(
        case["target_w"], case["prev_close"], case["high"], case["low"],
        case["close"], case["open_"], case["volume"], case["suspended"],
        case["board"], case["is_st"], case["dates"], policy)


def test_t390_27_limit_up_blocks_buy():
    case = _case()
    case["target_w"][1, 0] = 0.5
    case["high"][1, 0] = 11.0  # main 非 ST 涨停价
    eff, report = _run(case)
    assert eff[1, 0] == eff[0, 0] == 0.0
    assert report["blocked_buy"] >= 1


def test_t390_28_limit_down_blocks_sell():
    case = _case()
    case["target_w"][0, 0] = 0.5
    case["target_w"][1, 0] = 0.0
    case["low"][1, 0] = 9.0
    eff, report = _run(case)
    assert eff[0, 0] == 0.5
    assert eff[1, 0] == 0.5
    assert report["blocked_sell"] >= 1


def test_t390_29_suspend_freezes_position():
    case = _case()
    case["target_w"][0, 0] = 0.5
    case["target_w"][1, 0] = 0.0
    case["suspended"][1, 0] = True
    eff, report = _run(case)
    assert eff[1, 0] == 0.5
    assert report["blocked_suspend"] >= 1


def test_t390_30_t_plus_1_lock():
    case = _case(T=3)
    case["target_w"][0, 0] = 0.5
    case["high"][0, 0] = 11.0          # 首日涨停 → 挂起
    case["target_w"][1, 0] = 0.0       # 次日开板：补成交后同日报卖 → T+1 拒绝
    eff, report = _run(case)
    assert report["deferred"] >= 1     # 买侧补成交（次日卖出缺口另计）
    assert report["t1_locked"] >= 1
    assert eff[1, 0] == 0.5
    assert eff[2, 0] == 0.0


def test_t390_31_rule_versioning():
    assert rule_pct("main", True, "2026-07-03") == pytest.approx(0.05)
    assert rule_pct("main", True, "2026-07-05") == pytest.approx(0.05)
    assert rule_pct("main", True, "2026-07-06") == pytest.approx(0.10)
    assert rule_pct("gem", True, "2020-08-23") == pytest.approx(0.05)
    assert rule_pct("gem", True, "2020-08-24") == pytest.approx(0.20)
    assert rule_pct("star", False, "2022-01-04") == pytest.approx(0.20)
    assert rule_pct("bse", False, "2022-01-04") == pytest.approx(0.30)


def test_t390_32_limit_price_rounding():
    assert limit_price(10.00, 0.10, "up") == pytest.approx(11.00)
    assert limit_price(10.00, 0.10, "down") == pytest.approx(9.00)
    assert limit_price(3.33, 0.10, "up") == pytest.approx(3.66)
    assert limit_price(3.33, 0.10, "down") == pytest.approx(3.00)
    with pytest.raises(ValueError):
        limit_price(10.0, 0.10, "sideways")


def test_t390_33_cost_separation():
    model = CostModel()
    buy_only = model.cost(1e6, 0.0)
    sell_only = model.cost(0.0, 1e6)
    assert buy_only["stamp_tax"] == 0.0
    assert sell_only["stamp_tax"] == pytest.approx(500.0)   # 5bp × 1e6
    assert buy_only["transfer_fee"] == pytest.approx(10.0)  # 0.1bp × 1e6
    assert sell_only["total"] - buy_only["total"] == pytest.approx(500.0)
    assert buy_only["commission"] == pytest.approx(250.0)   # 2.5bp
    with pytest.raises(ValueError):
        model.cost(-1.0, 0.0)
    with pytest.raises(ValueError):
        model.cost(float("nan"), 0.0)


def test_t390_34_deferred_fill_after_two_limits():
    case = _case(T=3)
    case["target_w"][:, 0] = 0.5
    case["high"][0, 0] = 11.0
    case["high"][1, 0] = 11.0
    eff, report = _run(case)
    assert report["blocked_buy"] == 2
    assert report["deferred"] == 1
    assert eff[1, 0] == 0.0
    assert eff[2, 0] == 0.5


def test_t390_35_rule_miss_and_overlap():
    with pytest.raises(ValueError):
        rule_pct("main", False, "1990-01-01")
    with pytest.raises(ValueError):
        rule_pct("gem", False, "2001-01-01")
    overlap = (
        LimitRule("main", False, 0.10, "2020-01-01", "2021-12-31"),
        LimitRule("main", False, 0.20, "2021-06-01"),
    )
    with pytest.raises(ValueError):
        _validate_rules(overlap)
