# -*- coding: utf-8 -*-
"""I1-I3：仓位构建 / 前向收益 / 换手界。"""
import numpy as np

from backtest.engine import FactorBacktestEngine
from backtest.factor_metrics import compute_turnover

from .registry import Invariant, register


def _engine(panel):
    eng = FactorBacktestEngine.__new__(FactorBacktestEngine)
    eng.config = {"ls_method": "top_n", "top_n": 0.2}
    return eng


def _positions(panel):
    return _engine(panel)._build_positions(panel.factor)


def check_i1(panel):
    pos = _positions(panel)
    bad = np.argwhere(np.isnan(panel.factor) & (pos != 0.0))
    if bad.size:
        t, i = int(bad[0][0]), int(bad[0][1])
        return False, "first_bad=(%d,%d) expected=0 actual=%r" % (t, i, pos[t, i])
    return True, "NaN 股票仓位全为 0（%d 个 NaN 单元）" % int(np.isnan(panel.factor).sum())


def check_i2(panel):
    T, N = panel.close.shape
    eng = FactorBacktestEngine.__new__(FactorBacktestEngine)
    eng.n_dates, eng.n_stocks = T, N
    eng._close = panel.close
    eng._fwd_returns = None
    base = eng.compute_fwd_returns()

    t = max(1, T // 2)
    close2 = panel.close.copy()
    close2[t + 1:] = close2[t] * 1.5
    eng2 = FactorBacktestEngine.__new__(FactorBacktestEngine)
    eng2.n_dates, eng2.n_stocks = T, N
    eng2._close = close2
    eng2._fwd_returns = None
    alt = eng2.compute_fwd_returns()

    same = (base[:t] == alt[:t]) | (np.isnan(base[:t]) & np.isnan(alt[:t]))
    bad = np.argwhere(~same)
    if bad.size:
        r, c = int(bad[0][0]), int(bad[0][1])
        return False, "first_diff_t=%d col=%d" % (r, c)
    return True, "扰动未来后 fwd[:%d] 逐位不变" % t


def check_i3(panel):
    tr = compute_turnover(_positions(panel))
    lo, hi = float(np.nanmin(tr)), float(np.nanmax(tr))
    if lo < -1e-12:
        return False, "min=%.6f < 0" % lo
    if hi > 2.0 + 1e-9:
        return False, "max=%.6f > 2" % hi
    return True, "turnover ∈ [%.4f, %.4f]" % (lo, hi)


register(Invariant("I1_positions_valid_domain", "backtest.engine", "invariant",
                   "clean", check_i1))
register(Invariant("I2_fwd_returns_no_lookahead", "backtest.engine", "invariant",
                   "clean", check_i2))
register(Invariant("I3_turnover_bound", "backtest.factor_metrics", "bound",
                   "clean", check_i3))
