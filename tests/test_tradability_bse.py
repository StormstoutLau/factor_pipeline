# -*- coding: utf-8 -*-
"""P-021 A1：BSE 规则前移 + 规则 gap + 停牌 'S'/bool 双路径。"""
import numpy as np
import pandas as pd
import pytest

from backtest.tradability import (
    _pct_matrix,
    apply_tradability,
    rule_pct,
)
from backtest.tradability_inputs import build_tradability_inputs


# ---------------------------------------------------------------------------
# D3：BSE 2020-07-27 规则前移 + gap
# ---------------------------------------------------------------------------

def test_p021_d3_bse_effective():
    """2020-07-27 起 bse 30% 生效；前一交易日无规则（仍 ValueError）。"""
    assert rule_pct("bse", False, "2020-07-27") == pytest.approx(0.30)
    assert rule_pct("bse", True, "2020-07-27") == pytest.approx(0.30)
    with pytest.raises(ValueError):
        rule_pct("bse", False, "2020-07-24")


def test_p021_d3_bse_gap():
    """直调 _pct_matrix：早期不抛错、gap 全真、pct 全 NaN。"""
    dates = np.array(["2020-01-06", "2020-01-07"])
    pct, gap = _pct_matrix(np.array(["bse"]), np.zeros((2, 1), dtype=bool),
                           None, dates, return_gaps=True)
    assert np.isnan(pct).all()
    assert gap.all()


def test_p021_d3_bse_gap_apply():
    """apply 侧：早期 bse + nonzero target → 不抛错，limit_unknown 计数。"""
    T, N = 2, 1
    case = dict(
        target_w=np.array([[0.0], [0.5]]),
        prev_close=np.full((T, N), 10.0),
        high=np.full((T, N), 10.2),
        low=np.full((T, N), 9.8),
        close=np.full((T, N), 10.0),
        open_=np.full((T, N), 10.0),
        volume=np.full((T, N), 1e6),
        suspended=np.zeros((T, N), dtype=bool),
        board=np.array(["bse"]),
        is_st=np.zeros(N, dtype=bool),
        dates=np.array(["2020-01-06", "2020-01-07"]),
    )
    eff, report = apply_tradability(**case)
    assert report["limit_unknown"] >= 1
    # 库默认 unknown_policy="pass"：未知限价放行（非阻塞）
    assert eff[1, 0] == 0.5


def test_p021_d3_unknown_board():
    """未知板块：不抛错，limit_unknown + meta unknown_codes。"""
    T, N = 2, 1
    case = dict(
        target_w=np.array([[0.0], [0.5]]),
        prev_close=np.full((T, N), 10.0),
        high=np.full((T, N), 10.2),
        low=np.full((T, N), 9.8),
        close=np.full((T, N), 10.0),
        open_=np.full((T, N), 10.0),
        volume=np.full((T, N), 1e6),
        suspended=np.zeros((T, N), dtype=bool),
        board=np.array(["unknown"]),
        is_st=np.zeros(N, dtype=bool),
        dates=np.array(["2024-01-02", "2024-01-03"]),
    )
    _, report = apply_tradability(**case)
    assert report["limit_unknown"] >= 1


# ---------------------------------------------------------------------------
# D5：停牌语义
# ---------------------------------------------------------------------------

def _panels(suspend, n=3, codes=("600000.SH", "000001.SZ")):
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    close = pd.DataFrame(10.0, index=dates, columns=list(codes))
    return dict(close=close, high=close * 1.001, low=close * 0.999,
                open_=close.copy(),
                volume=pd.DataFrame(1e6, index=dates, columns=list(codes)),
                suspend=suspend,
                name=pd.DataFrame("普通", index=dates, columns=list(codes)),
                adj=pd.DataFrame(1.0, index=dates, columns=list(codes)))


def test_p021_d5_suspend_s_only():
    """object 面板：仅 'S' 停牌，'R'/None 可交易。"""
    p = _panels(pd.DataFrame(
        [["S", "R"], ["S", None], ["S", "R"]],
        index=pd.date_range("2024-01-02", periods=3, freq="B"),
        columns=["600000.SH", "000001.SZ"], dtype=object))
    inputs, meta = build_tradability_inputs(**p)
    assert inputs.suspended[:, 0].all()          # 连续 S
    assert not inputs.suspended[:, 1].any()      # R / None 均可交易
    assert isinstance(inputs.suspended, np.ndarray)
    assert inputs.suspended.dtype == np.bool_


def test_p021_d5_suspend_bool_compat():
    """bool 面板 True=停牌，false 可交易（既有契约）。"""
    dates = pd.date_range("2024-01-02", periods=3, freq="B")
    suspend = pd.DataFrame(False, index=dates,
                           columns=["600000.SH", "000001.SZ"])
    suspend.iloc[1, 0] = True
    p = _panels(suspend)
    inputs, _ = build_tradability_inputs(**p)
    assert inputs.suspended[1, 0]
    assert not inputs.suspended[0, 0]


def test_p021_d5_suspend_reindex_dtype():
    """bool 面板缺列经 reindex 升型 object 后，True 仍为停牌（P2-B2）。"""
    dates = pd.date_range("2024-01-02", periods=3, freq="B")
    suspend = pd.DataFrame(False, index=dates, columns=["600000.SH"])
    suspend.iloc[1, 0] = True                     # 缺 000001.SZ 列 → reindex 升型
    p = _panels(suspend)
    inputs, _ = build_tradability_inputs(**p)
    assert inputs.suspended[1, 0]
    assert not inputs.suspended[:, 1].any()
    assert inputs.diagnostics["suspend_missing_cells"] == 3
