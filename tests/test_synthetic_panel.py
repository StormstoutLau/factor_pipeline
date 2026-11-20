# -*- coding: utf-8 -*-
"""v3.9.0 E1（S2）：合成场景库验收（T390-02 ~ T390-06）。"""
import numpy as np
import pandas as pd

from backtest.data_bridge import DataBridge
from backtest.execution.core.classification import detect_limit_lock
from tests.synthetic import SCENARIOS, build_panel


def _arrays(panel):
    return (panel.dates, panel.codes, panel.board, panel.is_st,
            panel.open, panel.high, panel.low, panel.close, panel.volume,
            panel.amount, panel.factor, panel.loaded_at, panel.industry,
            panel.mktcap, panel.true_limit_hit, panel.true_suspend)


def _same(x, y):
    if x.dtype.kind in "fc":
        return np.array_equal(x, y, equal_nan=True)
    return np.array_equal(x, y)


def test_t390_02_deterministic():
    a = build_panel(SCENARIOS["clean"])
    b = build_panel(SCENARIOS["clean"])
    for x, y in zip(_arrays(a), _arrays(b)):
        assert _same(x, y), "non-deterministic array: %r" % (x.dtype,)


def test_t390_03_truth_ratio():
    spec = SCENARIOS["limit_heavy"]
    panel = build_panel(spec)
    n = spec.n_stocks
    n_up = int(round(spec.limit_up_ratio * n))
    n_down = int(round(spec.limit_down_ratio * n))
    for t in range(1, spec.n_dates):
        assert int((panel.true_limit_hit[t] == 1).sum()) == n_up, \
            "up count mismatch at t=%d" % t
        assert int((panel.true_limit_hit[t] == -1).sum()) == n_down, \
            "down count mismatch at t=%d" % t


def test_t390_04_lock_identification():
    panel = build_panel(SCENARIOS["limit_heavy"])
    got = detect_limit_lock(panel.high, panel.low, panel.close,
                            panel.open, panel.volume).reshape(panel.close.shape)
    expected = (panel.true_limit_hit != 0) | panel.true_suspend
    bad = np.argwhere(got != expected)
    assert bad.size == 0, "first mismatch at %s" % (tuple(bad[0]),)
    ordinary = ~expected
    assert not got[ordinary].any(), "普通日被误判为一字板"


def test_t390_05_pit_no_future():
    panel = build_panel(SCENARIOS["stale_factor"])
    # 子样本：PIT 性质与规模无关（既有实现为 O(N·T²) pandas 赋值）
    t_sub = min(40, panel.spec.n_dates)
    i_sub = min(12, len(panel.codes))
    dates = pd.to_datetime(panel.dates[:t_sub])
    codes = panel.codes[:i_sub]
    f_df = pd.DataFrame(panel.factor[:t_sub, :i_sub].T,
                        index=codes, columns=dates)
    l_df = pd.DataFrame(panel.loaded_at[:t_sub, :i_sub].T,
                        index=codes, columns=dates)
    bridge = DataBridge.__new__(DataBridge)
    out = bridge._apply_loaded_at_lag(
        f_df, l_df, use_loaded_at=True, fill_missing="nan")

    for i, code in enumerate(codes):
        visible = out.loc[code].to_numpy(dtype=float)
        for t in range(t_sub):
            if np.isnan(visible[t]):
                continue
            sources = np.flatnonzero(
                np.isfinite(panel.factor[:t_sub, i])
                & (panel.loaded_at[:t_sub, i] <= panel.dates[t]))
            assert sources.size > 0, (
                "future leakage: stock=%r t=%d value=%r" % (code, t, visible[t]))


def test_t390_06_suspend_segment_locked():
    panel = build_panel(SCENARIOS["suspend_gap"])
    idx = np.argwhere(panel.true_suspend)
    assert idx.size > 0, "suspend_gap 场景未产生停牌"
    for t, i in idx:
        assert panel.volume[t, i] == 0.0, "停牌日成交量非 0 at (%d,%d)" % (t, i)
        assert panel.high[t, i] == panel.low[t, i] == panel.close[t, i], \
            "停牌日 h/l/c 不一致 at (%d,%d)" % (t, i)
        if t > 0:
            assert panel.close[t, i] == panel.close[t - 1, i], \
                "停牌日价格跳变 at (%d,%d)" % (t, i)


def test_t390_40_adj_jump_buildable():
    """审计 H2 回归：adj_jump 场景必须可构建（网格校验先于缩放）。"""
    panel = build_panel(SCENARIOS["adj_jump"])
    ret40 = panel.close[40] / panel.close[39] - 1.0
    m = float(np.median(ret40))
    assert -0.52 < m < -0.44, "跳变日收益中位应≈-0.5 (got %r)" % m
    for t, i in np.argwhere(panel.true_limit_hit != 0):
        assert panel.open[t, i] == panel.high[t, i] \
            == panel.low[t, i] == panel.close[t, i], \
            "一字板四价不等 at (%d,%d)" % (t, i)
    for t, i in np.argwhere(panel.true_suspend):
        assert panel.volume[t, i] == 0.0, "缩放后停牌量非 0 at (%d,%d)" % (t, i)
    assert not np.any(np.isnan(panel.close)), "缩放不应引入 NaN"
