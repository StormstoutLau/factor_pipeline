# -*- coding: utf-8 -*-
"""v3.9.0 合成面板生成器（测试侧，零生产依赖）。

依据：DESIGN_SYNTHETIC_VALIDATION_TRACEABILITY.md §4（v1.3）。
约束：禁止 import backtest.*（避免测试侧反向依赖生产）。
"""
from dataclasses import dataclass
from typing import Tuple

import numpy as np

__all__ = ["PanelSpec", "SyntheticPanel", "build_panel"]

BOARD_NAMES = ("main", "star", "gem", "bse")
INDUSTRY_NAMES = ("tech", "fin", "cons", "med", "energy", "material")

# 与 backtest/tradability.py::DEFAULT_LIMIT_RULES 数值一致（数值副本，禁止 import）
_RULE_ROWS = (
    ("main", False, 0.10, "1996-12-16", None),
    ("main", True, 0.05, "1998-04-22", "2026-07-05"),
    ("main", True, 0.10, "2026-07-06", None),
    ("star", False, 0.20, "2019-07-22", None),
    ("star", True, 0.20, "2019-07-22", None),
    ("gem", False, 0.10, "2009-10-30", "2020-08-23"),
    ("gem", False, 0.20, "2020-08-24", None),
    ("gem", True, 0.05, "2009-10-30", "2020-08-23"),
    ("gem", True, 0.20, "2020-08-24", None),
    ("bse", False, 0.30, "2021-11-15", None),
    ("bse", True, 0.30, "2021-11-15", None),
)


@dataclass(frozen=True)
class PanelSpec(object):
    n_dates: int = 120
    n_stocks: int = 60
    start: str = "2022-01-04"
    seed: int = 20261119
    board_mix: Tuple[Tuple[str, float], ...] = (
        ("main", 0.60), ("star", 0.20), ("gem", 0.15), ("bse", 0.05))
    limit_up_ratio: float = 0.0
    limit_down_ratio: float = 0.0
    suspend_ratio: float = 0.0
    suspend_len: int = 5
    st_ratio: float = 0.0
    factor_missing: float = 0.0
    loaded_lag_days: int = 0
    adj_jump_days: Tuple[int, ...] = ()


@dataclass(frozen=True)
class SyntheticPanel(object):
    spec: PanelSpec
    dates: np.ndarray          # (T,) datetime64[D]
    codes: np.ndarray          # (N,) int64
    board: np.ndarray          # (N,) '<U4'
    is_st: np.ndarray          # (N,) bool
    open: np.ndarray           # (T, N) float64
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    amount: np.ndarray
    factor: np.ndarray
    loaded_at: np.ndarray      # (T, N) datetime64[D]
    industry: np.ndarray       # (N,) '<U8'
    mktcap: np.ndarray         # (N,) float64
    true_limit_hit: np.ndarray  # (T, N) int8
    true_suspend: np.ndarray    # (T, N) bool


def _validate(spec):
    if spec.n_dates < 2:
        raise ValueError("n_dates 必须 >= 2 (实际 %r)" % (spec.n_dates,))
    if spec.n_stocks < 4:
        raise ValueError("n_stocks 必须 >= 4 (实际 %r)" % (spec.n_stocks,))
    total = sum(r for _, r in spec.board_mix)
    if not (0.99 <= total <= 1.01):
        raise ValueError("board_mix 比例和必须 ∈ [0.99, 1.01] (实际 %r)" % (total,))
    if any(name not in BOARD_NAMES for name, _ in spec.board_mix):
        raise ValueError("board_mix 含未知板块 (实际 %r)" % (spec.board_mix,))
    if spec.limit_up_ratio + spec.limit_down_ratio > 0.5:
        raise ValueError("limit_up_ratio + limit_down_ratio 必须 <= 0.5 (实际 %r)"
                         % (spec.limit_up_ratio + spec.limit_down_ratio,))
    if spec.suspend_len >= spec.n_dates:
        raise ValueError("suspend_len 必须 < n_dates (实际 %r >= %r)"
                         % (spec.suspend_len, spec.n_dates))


def _rule_pct(board, is_st, date_str):
    for b, st, pct, start, end in _RULE_ROWS:
        if b != board or bool(st) != bool(is_st):
            continue
        if date_str >= start and (end is None or date_str <= end):
            return pct
    raise ValueError("无涨跌幅规则: board=%s is_st=%s date=%s"
                     % (board, is_st, date_str))


def _business_dates(start, n):
    d = np.datetime64(start, "D")
    out = []
    while len(out) < n:
        if np.is_busday(d):
            out.append(d)
        d = d + np.timedelta64(1, "D")
    return np.array(out, dtype="datetime64[D]")


def _assign_board(spec, n_stocks):
    board = np.array(["main"] * n_stocks, dtype="<U4")
    pos = 0
    for name, ratio in spec.board_mix:
        cnt = min(int(round(ratio * n_stocks)), n_stocks - pos)
        board[pos:pos + cnt] = name
        pos += cnt
    return board


def _assign_st(spec, board, n_stocks, rng):
    is_st = np.zeros(n_stocks, dtype=bool)
    n_st = int(round(spec.st_ratio * n_stocks))
    main_idx = np.flatnonzero(board == "main")
    if n_st > 0 and main_idx.size:
        picked = rng.choice(main_idx, size=min(n_st, main_idx.size), replace=False)
        is_st[picked] = True
    return is_st


def build_panel(spec):
    """按 design §4.2 九步生成；同 spec 两次调用逐位一致。"""
    _validate(spec)
    rng = np.random.default_rng(spec.seed)
    T, N = spec.n_dates, spec.n_stocks

    dates = _business_dates(spec.start, T)
    board = _assign_board(spec, N)
    is_st = _assign_st(spec, board, N, rng)

    close = np.empty((T, N), dtype=float)
    high = np.empty((T, N), dtype=float)
    low = np.empty((T, N), dtype=float)
    open_ = np.empty((T, N), dtype=float)
    volume = np.empty((T, N), dtype=float)
    true_limit_hit = np.zeros((T, N), dtype=np.int8)
    true_suspend = np.zeros((T, N), dtype=bool)

    close[0] = np.round(rng.lognormal(0.0, 0.3, N), 2)
    sigma = rng.uniform(0.008, 0.03, N)

    suspend_mask = np.zeros((T, N), dtype=bool)
    n_susp = int(round(spec.suspend_ratio * N))
    if n_susp > 0:
        max_start = T - spec.suspend_len
        for i in rng.choice(N, size=n_susp, replace=False):
            start = int(rng.integers(1, max_start + 1)) if max_start >= 1 else 1
            suspend_mask[start:start + spec.suspend_len, i] = True

    n_up = int(round(spec.limit_up_ratio * N))
    n_down = int(round(spec.limit_down_ratio * N))
    date_str = [str(d) for d in dates]

    for t in range(T):
        prev = close[t - 1] if t > 0 else close[0]
        if t == 0:
            c = close[0].copy()
        else:
            c = np.round(prev * (1.0 + rng.normal(0.0, sigma, N)), 2)

        up_idx = np.empty(0, dtype=int)
        down_idx = np.empty(0, dtype=int)
        if t > 0 and (n_up or n_down):
            perm = rng.permutation(N)
            up_idx = perm[:n_up]
            down_idx = perm[n_up:n_up + n_down]
            pct = np.array([_rule_pct(board[j], bool(is_st[j]), date_str[t])
                            for j in range(N)])
            if up_idx.size:
                c[up_idx] = np.round(prev[up_idx] * (1.0 + pct[up_idx]), 2)
                true_limit_hit[t, up_idx] = 1
            if down_idx.size:
                c[down_idx] = np.round(prev[down_idx] * (1.0 - pct[down_idx]), 2)
                true_limit_hit[t, down_idx] = -1

        susp = suspend_mask[t]
        if susp.any():
            c[susp] = prev[susp]
            true_limit_hit[t, susp] = 0

        close[t] = c

        u = np.abs(rng.normal(0.0, 0.005, N)) + np.maximum(
            0.002, 0.0155 / np.maximum(c, 1e-6))
        d = np.abs(rng.normal(0.0, 0.005, N)) + np.maximum(
            0.002, 0.0155 / np.maximum(c, 1e-6))
        hi = np.round(c * (1.0 + u), 2)
        lo = np.round(c * (1.0 - d), 2)
        op = np.clip(np.round(c * (1.0 + rng.normal(0.0, 0.003, N)), 2), lo, hi)

        vol = rng.uniform(1e5, 5e6, N)
        lock_idx = np.concatenate([up_idx, down_idx])
        if lock_idx.size:
            hi[lock_idx] = c[lock_idx]
            lo[lock_idx] = c[lock_idx]
            op[lock_idx] = c[lock_idx]
            vol[lock_idx] = rng.uniform(1e5, 1e6, lock_idx.size)
        if susp.any():
            hi[susp] = c[susp]
            lo[susp] = c[susp]
            op[susp] = c[susp]
            vol[susp] = 0.0

        high[t], low[t], open_[t], volume[t] = hi, lo, op, vol
        true_suspend[t, susp] = True

    # 步 3 校验针对主循环产出（"普通日 round2 后 high-low>=0.02"），
    # 须在 adj_jump 缩放（步 6）之前执行——缩放是复权语义，允许破坏网格
    # （审计 H2：检查置于缩放后会使 adj_jump 场景必 raise）。
    bad = ((high - low) < 0.02 - 1e-9) & (true_limit_hit == 0) & ~true_suspend
    if bad.any():
        pos = tuple(int(v) for v in np.argwhere(bad)[0])
        raise ValueError("普通日 round2 后 high-low<0.02 at %s (close=%r)"
                         % (pos, close[pos]))

    # 步 6：adj_jump 前复权缩放（在网格校验之后执行）
    for t in spec.adj_jump_days:
        if 0 <= t < T:
            close[t:] *= 0.5
            open_[t:] *= 0.5
            high[t:] *= 0.5
            low[t:] *= 0.5

    # 因子：未来 H=5 日收益的横截面 z-score + 噪声
    H = min(5, T - 1)
    fwd = np.full((T, N), np.nan)
    if H > 0:
        fwd[:T - H] = close[H:] / close[:T - H] - 1.0
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mu = np.nanmean(fwd, axis=1, keepdims=True)
        sd = np.nanstd(fwd, axis=1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (fwd - mu) / np.where(sd > 0.0, sd, np.nan)
    factor = z + rng.normal(0.0, 0.5, (T, N))
    factor[suspend_mask] = np.nan
    if spec.factor_missing > 0:
        factor[rng.random((T, N)) < spec.factor_missing] = np.nan

    loaded_at = np.repeat(
        dates[:, None] + np.timedelta64(int(spec.loaded_lag_days), "D"), N, axis=1)
    industry = np.array(INDUSTRY_NAMES, dtype="<U8")[rng.integers(0, 6, N)]
    mktcap = close[0] * rng.lognormal(20.0, 1.0, N)
    amount = volume * close

    return SyntheticPanel(
        spec=spec, dates=dates,
        codes=np.arange(N, dtype=np.int64) + 1,
        board=board, is_st=is_st,
        open=open_, high=high, low=low, close=close,
        volume=volume, amount=amount, factor=factor,
        loaded_at=loaded_at, industry=industry, mktcap=mktcap,
        true_limit_hit=true_limit_hit, true_suspend=true_suspend,
    )
