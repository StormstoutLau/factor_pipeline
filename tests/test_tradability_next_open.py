# -*- coding: utf-8 -*-
"""P-021 A2：next_open 执行时点 + 诊断块 + D6 降级成交语义。"""
import numpy as np

from backtest.tradability import (
    TradabilityPolicy,
    apply_tradability,
    apply_tradability_with_diagnostics,
)


def _case(T=3, N=1, target=None):
    return dict(
        target_w=(np.zeros((T, N)) if target is None
                  else np.asarray(target, dtype=float).reshape(T, N)),
        prev_close=np.full((T, N), 10.0),
        high=np.full((T, N), 10.2),
        low=np.full((T, N), 9.8),
        close=np.full((T, N), 10.0),
        open_=np.full((T, N), 10.0),
        volume=np.full((T, N), 1e6),
        suspended=np.zeros((T, N), dtype=bool),
        board=np.array(["main"] * N),
        is_st=np.zeros(N, dtype=bool),
        dates=np.array(["2026-01-05", "2026-01-06",
                        "2026-01-07", "2026-01-08"][:T]),
    )


def _apply(case, policy):
    return apply_tradability_with_diagnostics(
        policy=policy, adj=np.ones_like(case["prev_close"]), **case)


def test_p021_d1_signal_shifted():
    """D1：信号后移 1 日，t+1 开盘成交；t=0 不建仓。"""
    case = _case(T=3, target=[[0.5], [0.0], [0.0]])
    eff, _, _ = _apply(case, TradabilityPolicy(execute_at="next_open"))
    assert eff[0, 0] == 0.0
    assert eff[1, 0] == 0.5
    assert eff[2, 0] == 0.0            # t=2 执行 target_w[1]=0 → 平仓


def test_p021_d1_last_signal_dropped():
    """D1：末信号丢弃；carried 对后移目标计数。"""
    case = _case(T=3, target=[[0.0], [0.0], [0.6]])
    eff, report, _ = _apply(case, TradabilityPolicy(execute_at="next_open"))
    assert np.all(eff == 0.0)
    assert report["carried"] == 0       # carried 对后移目标（末信号已丢弃）


def test_p021_d1_open_predicate():
    """D1：执行价取 open；盘中触及涨停止损但不拦单。"""
    case = _case(T=3, target=[[0.5], [0.0], [0.0]])
    case["open_"][1, 0] = 11.0          # t=1 开盘即涨停 → 拦截
    case["high"][1, 0] = 11.0
    _, report, diag = _apply(case, TradabilityPolicy(
        execute_at="next_open"))
    assert report["blocked_buy"] == 1
    assert diag["exec_up_touch_cells"] >= 1
    assert diag["execution_timing"] == "t_plus_1_open"

    case2 = _case(T=3, target=[[0.5], [0.0], [0.0]])
    case2["high"][1, 0] = 11.0          # 仅盘中触及，open 正常 → 可成交
    eff2, report2, _ = _apply(case2, TradabilityPolicy(
        execute_at="next_open"))
    assert report2["blocked_buy"] == 0
    assert eff2[1, 0] == 0.5


def test_p021_d1_open_nan_blocks():
    """D1：执行价 open 非有限 → 阻塞 + exec_price_missing_cells。"""
    case = _case(T=3, target=[[0.5], [0.0], [0.0]])
    case["open_"][1, 0] = np.nan
    eff, report, diag = _apply(case, TradabilityPolicy(
        execute_at="next_open"))
    assert eff[1, 0] == 0.0
    assert report["blocked_buy"] == 1
    assert diag["exec_price_missing_cells"] == 1


def test_p021_d1_same_close_nan_not_blocked():
    """INV-5：same_close 对 NaN high/low 仍放行（不因 missing_exec 回归）。"""
    case = _case(T=2, target=[[0.0], [0.5]])
    case["high"][:] = np.nan
    case["low"][:] = np.nan
    eff, report, diag = apply_tradability_with_diagnostics(
        policy=TradabilityPolicy(), adj=np.ones_like(case["prev_close"]),
        **case)
    assert report["blocked_buy"] == 0
    assert eff[1, 0] == 0.5
    assert diag["exec_price_missing_cells"] == 0
    assert diag["execution_timing"] == "same_close"


def test_p021_apply_three_tuple_contract():
    """接口：3 元组 + report 9 键全 int + diagnostics schema_version=2。"""
    case = _case(T=2, target=[[0.5], [0.0]])
    eff, report, diag = _apply(case, TradabilityPolicy(
        execute_at="next_open", unknown_policy="fallback_raw"))
    assert eff.shape == (2, 1)
    assert len(report) == 9
    assert all(type(v) is int for v in report.values())
    assert diag["schema_version"] == 2
    assert diag["mode"] == "full"
    assert diag["one_word_disabled"] is False


def test_p021_wrapper_two_tuple_unchanged():
    """兼容：apply_tradability 仍返回 2 元组。"""
    case = _case(T=2, target=[[0.5], [0.0]])
    out = apply_tradability(adj=np.ones_like(case["prev_close"]), **case)
    assert len(out) == 2
    assert isinstance(out[1]["blocked_buy"], int)


def test_p021_mode_execution_only_open():
    """D6：execution_only_open 与 next_open 同构；一字关闭并披露。"""
    case = _case(T=3, target=[[0.5], [0.0], [0.0]])
    case["high"][:] = 10.0              # 一字缺 high/low 差异
    case["low"][:] = 10.0
    eff, report, diag = _apply(case, TradabilityPolicy(
        execute_at="next_open", mode="execution_only_open"))
    assert eff[1, 0] == 0.5
    assert report["one_word_up"] == 0
    assert report["one_word_down"] == 0
    assert diag["one_word_disabled"] is True
    assert diag["mode"] == "execution_only_open"


def test_p021_policy_validation():
    """I-1：policy 枚举非法 / 模式组合非法 → ValueError。"""
    import pytest

    case = _case(T=2, target=[[0.0], [0.0]])
    adj = np.ones_like(case["prev_close"])
    for policy in (TradabilityPolicy(execute_at="bad"),
                   TradabilityPolicy(unknown_policy="bad"),
                   TradabilityPolicy(mode="bad"),
                   TradabilityPolicy(execute_at="same_close",
                                     mode="execution_only_open")):
        with pytest.raises(ValueError):
            apply_tradability_with_diagnostics(policy=policy, adj=adj, **case)


def test_p021_mode_off_noop():
    """D6：mode=off 不改权重、report 全 0；diagnostics 仅 2 键（DESIGN §4.2）。"""
    case = _case(T=2, target=[[0.5], [0.5]])
    eff, report, diag = _apply(case, TradabilityPolicy(mode="off"))
    assert np.all(eff == case["target_w"])
    assert sum(report.values()) == 0
    assert diag == {"mode": "off", "schema_version": 2}


def test_p021_unknown_policy_block():
    """D2：unknown_policy=block → 未知限价不成交。"""
    case = _case(T=2, target=[[0.0], [0.5]])
    case["board"] = np.array(["unknown"])
    eff, report, _ = _apply(case, TradabilityPolicy(mode="full",
                                                    unknown_policy="block"))
    assert eff[1, 0] == 0.0
    assert report["limit_unknown"] >= 1

    case2 = _case(T=2, target=[[0.0], [0.5]])
    case2["board"] = np.array(["unknown"])
    eff2, _, _ = _apply(case2, TradabilityPolicy(
        unknown_policy="pass"))
    assert eff2[1, 0] == 0.5            # pass：未知放行
