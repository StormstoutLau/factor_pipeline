# -*- coding: utf-8 -*-
"""I6-I7：PIT 可见性 / ffill 等价。"""
import numpy as np
import pandas as pd

from backtest.data_bridge import DataBridge

from .registry import Invariant, register


def _filtered_subset(panel, fill_missing, t_sub=24, n_sub=8):
    """取子样本（PIT 性质与规模无关；既有实现为 O(N·T²) pandas 赋值）。"""
    t_sub = min(t_sub, panel.spec.n_dates)
    n_sub = min(n_sub, len(panel.codes))
    dates = pd.to_datetime(panel.dates[:t_sub])
    codes = panel.codes[:n_sub]
    f_df = pd.DataFrame(panel.factor[:t_sub, :n_sub].T,
                        index=codes, columns=dates)
    l_df = pd.DataFrame(panel.loaded_at[:t_sub, :n_sub].T,
                        index=codes, columns=dates)
    bridge = DataBridge.__new__(DataBridge)
    out = bridge._apply_loaded_at_lag(
        f_df, l_df, use_loaded_at=True, fill_missing=fill_missing)
    return out, t_sub, n_sub


def check_i6(panel):
    out, T, N = _filtered_subset(panel, "nan")
    dates = panel.dates[:T]
    for i in range(N):
        code = panel.codes[i]
        visible = out.loc[code].to_numpy(dtype=float)
        src_ok = np.isfinite(panel.factor[:T, i])
        loaded = panel.loaded_at[:T, i]
        order = np.argsort(loaded, kind="stable")
        loaded_sorted = loaded[order]
        cum = np.cumsum(src_ok[order])
        counts = np.searchsorted(loaded_sorted, dates, side="right")
        available = np.zeros(T, dtype=bool)
        nz = counts > 0
        available[nz] = cum[counts[nz] - 1] > 0
        leak = np.flatnonzero(~np.isnan(visible) & ~available)
        if leak.size:
            t = int(leak[0])
            return False, "first_bad=(%r,%d) value=%r 无可见来源" % (
                int(code), t, visible[t])
    return True, "PIT 可见性成立（子样本 %d 只 × %d 期）" % (N, T)


def check_i7(panel):
    # 子样本：等价性与规模无关（既有实现为 O(N·T²) pandas 赋值）
    T, N = min(24, panel.spec.n_dates), min(8, len(panel.codes))
    rng = np.random.default_rng(7)
    dates = pd.to_datetime(panel.dates[:T])
    factor = rng.normal(size=(N, T))
    codes = panel.codes[:N]
    f_df = pd.DataFrame(factor, index=codes, columns=dates)
    l_df = pd.DataFrame(np.tile(panel.dates[:T], (N, 1)),
                        index=codes, columns=dates)
    bridge = DataBridge.__new__(DataBridge)
    a = bridge._apply_loaded_at_lag(f_df, l_df, True, "nan")
    b = bridge._apply_loaded_at_lag(f_df, l_df, True, "ffill")
    same = (a.to_numpy() == b.to_numpy())
    same |= np.isnan(a.to_numpy()) & np.isnan(b.to_numpy())
    bad = np.argwhere(~same)
    if bad.size:
        return False, "首个不等位置=%s" % (tuple(int(v) for v in bad[0]),)
    return True, "无缺失输入下 'nan' 与 'ffill' 逐位一致"


register(Invariant("I6_pit_visible", "backtest.data_bridge", "invariant",
                   "stale_factor", check_i6))
register(Invariant("I7_ffill_equivalence", "backtest.data_bridge",
                   "equivalence", "clean", check_i7))
