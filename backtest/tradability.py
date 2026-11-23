# -*- coding: utf-8 -*-
"""v3.9.0 回测交易现实性（独立函数；默认不接入引擎）。

依据：DESIGN_SYNTHETIC_VALIDATION_TRACEABILITY.md §7（v1.3）。
顶层依赖：stdlib + numpy；无 IO、无全局状态。
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

__all__ = ["LimitRule", "DEFAULT_LIMIT_RULES", "rule_pct", "limit_price",
           "board_of", "compute_limits", "TradabilityInputs",
           "TradabilityPolicy", "can_trade", "apply_tradability", "CostModel"]

_EPS = 1e-8


@dataclass(frozen=True)
class LimitRule(object):
    board: str
    is_st: bool
    pct: float
    effective_from: str
    effective_to: Optional[str] = None


DEFAULT_LIMIT_RULES = (
    LimitRule("main", False, 0.10, "1996-12-16"),
    LimitRule("main", True, 0.05, "1998-04-22", "2026-07-05"),
    LimitRule("main", True, 0.10, "2026-07-06"),
    LimitRule("star", False, 0.20, "2019-07-22"),
    LimitRule("star", True, 0.20, "2019-07-22"),
    LimitRule("gem", False, 0.10, "2009-10-30", "2020-08-23"),
    LimitRule("gem", False, 0.20, "2020-08-24"),
    LimitRule("gem", True, 0.05, "2009-10-30", "2020-08-23"),
    LimitRule("gem", True, 0.20, "2020-08-24"),
    LimitRule("bse", False, 0.30, "2021-11-15"),
    LimitRule("bse", True, 0.30, "2021-11-15"),
)


def _validate_rules(rules):
    groups = {}  # type: Dict[Tuple[str, bool], List[LimitRule]]
    for rule in rules:
        groups.setdefault((rule.board, bool(rule.is_st)), []).append(rule)
    for key, items in groups.items():
        ordered = sorted(items, key=lambda item: item.effective_from)
        for prev, nxt in zip(ordered, ordered[1:]):
            if prev.effective_to is None or prev.effective_to >= nxt.effective_from:
                raise ValueError("规则表重叠: %r (%s..%s vs %s..)"
                                 % (key, prev.effective_from,
                                    prev.effective_to, nxt.effective_from))


_validate_rules(DEFAULT_LIMIT_RULES)


def _as_date_str(date):
    if isinstance(date, str):
        return date
    return str(np.datetime64(date, "D"))


def rule_pct(board, is_st, date):
    """唯一命中规则；无命中 → ValueError（不静默用默认值）。"""
    date_str = _as_date_str(date)
    for rule in DEFAULT_LIMIT_RULES:
        if rule.board != board or bool(rule.is_st) != bool(is_st):
            continue
        if date_str >= rule.effective_from and (
                rule.effective_to is None or date_str <= rule.effective_to):
            return float(rule.pct)
    raise ValueError("无涨跌幅规则: board=%s is_st=%s date=%s"
                     % (board, is_st, date_str))


_BOARD_CODES = {"main": 0, "star": 1, "gem": 2, "bse": 3}
_BOARD_NAMES = ("main", "star", "gem", "bse")


def _to_cents(x):
    """两位小数 → 整数分（ROUND_HALF_UP）；NaN 位置不参与取整。

    Returns:
        (cents: int64 ndarray, valid: bool ndarray)，形状同输入。
    """
    arr = np.asarray(x, dtype=float)
    flat = np.atleast_1d(arr).astype(float)
    valid = np.isfinite(flat)
    cents = np.zeros(flat.shape, dtype=np.int64)
    cents[valid] = np.floor(flat[valid] * 100.0 + 0.5).astype(np.int64)
    return cents.reshape(arr.shape), valid.reshape(arr.shape)


def board_of(code):
    """单一板块映射（区间口径；未映射 → 'unknown'，禁止默认 main）。

    main: 600/601/603/605、000–004（含 001 CDR）
    gem : 300–309（含 3098–3099 存托凭证）
    star: 688/689（689 为科创板 CDR）
    bse : 43/83/87/92
    """
    text = str(code).split(".")[0].strip()
    if not text.isdigit():
        return "unknown"
    code6 = text.zfill(6)
    if len(code6) != 6:
        return "unknown"
    prefix3 = code6[:3]
    if prefix3 in ("600", "601", "603", "605") or "000" <= prefix3 <= "004":
        return "main"
    if "300" <= prefix3 <= "309":
        return "gem"
    if prefix3 in ("688", "689"):
        return "star"
    if code6[:2] in ("43", "83", "87", "92"):
        return "bse"
    return "unknown"


def limit_price(prev_close, pct, side="up"):
    """涨跌幅限制价格：整数分 ROUND_HALF_UP + 一档三分支。

    以分为单位计算 (pc×(10000±bp)+5000)//10000，禁用 np.round；
    分支：① |limit−prev| < 1 分 → prev ± 1 分；② limit < 1 分 → 1 分。
    NaN 入 → NaN 出；pct ∉ [0,1] → ValueError；标量入参返回 float。
    """
    if side not in ("up", "down"):
        raise ValueError("side 必须 ∈ {up, down} (实际 %r)" % (side,))
    prev_arr = np.asarray(prev_close, dtype=float)
    pct_arr = np.asarray(pct, dtype=float)
    prev_b, pct_b = np.broadcast_arrays(prev_arr, pct_arr)
    pct_finite = np.isfinite(pct_b)
    bad = pct_finite & ((pct_b < 0.0) | (pct_b > 1.0))
    if np.any(bad):
        raise ValueError("pct 必须 ∈ [0, 1] (实际 %r)"
                         % (float(np.asarray(pct_b)[bad].reshape(-1)[0]),))

    pc, prev_ok = _to_cents(prev_b)
    valid = prev_ok & pct_finite
    bp = np.zeros(pct_b.shape, dtype=np.int64)
    bp[pct_finite] = np.floor(
        pct_b[pct_finite] * 10000.0 + 0.5).astype(np.int64)
    scale = 10000 + bp if side == "up" else 10000 - bp
    lc = np.zeros(pc.shape, dtype=np.int64)
    lc[valid] = (pc[valid] * scale[valid] + 5000) // 10000
    step = 1 if side == "up" else -1
    lc = np.where(valid & (np.abs(lc - pc) < 1), pc + step, lc)
    lc = np.where(valid & (lc < 1), 1, lc)

    out = np.where(valid, lc.astype(float) / 100.0, np.nan)
    if np.ndim(prev_arr) == 0 and np.ndim(pct_arr) == 0:
        return float(out)
    return out


def compute_limits(prev_close, pct, ref=None, is_st=None,
                   low_price_st_rule=True):
    """返回 (up, down, unknown)。

    ref: 除权（息）参考价，None 时基准价 = prev_close。
    unknown: prev/pct/ref 非有限、prev<=0、ref<=0；未知板块由调用方并入。
    低价 ST（is_st & prev<0.1 元）：up = prev+1 分，down = max(prev−1 分, 1)。
    """
    prev = np.asarray(prev_close, dtype=float)
    pct_arr = np.asarray(pct, dtype=float)
    if ref is None:
        basis = prev
        unknown = (~np.isfinite(prev) | ~np.isfinite(pct_arr)
                   | (prev <= 0.0))
    else:
        basis = np.asarray(ref, dtype=float)
        unknown = (~np.isfinite(prev) | ~np.isfinite(pct_arr)
                   | (prev <= 0.0) | ~np.isfinite(basis) | (basis <= 0.0))
    unknown = np.asarray(unknown, dtype=bool)

    up = limit_price(basis, pct_arr, "up")
    down = limit_price(basis, pct_arr, "down")

    if is_st is not None and low_price_st_rule:
        st = np.asarray(is_st, dtype=bool)
        pc, pc_ok = _to_cents(prev)
        low = st & pc_ok & (prev > 0.0) & (pc < 10)
        up = np.where(low, (pc + 1).astype(float) / 100.0, up)
        down = np.where(low, np.maximum(pc - 1, 1).astype(float) / 100.0,
                        down)

    up = np.where(unknown, np.nan, up)
    down = np.where(unknown, np.nan, down)
    return up, down, unknown


@dataclass(frozen=True)
class TradabilityPolicy(object):
    execute_at: str = "next_open"     # next_open | same_close（后者仅测试对照）
    t_plus_1: bool = True
    renormalize: bool = False
    eps: float = _EPS


def _pct_matrix(board, is_st, is_delisting, dates):
    """按 (board, ST, 退市) 状态逐日查规则；unknown 板块留 NaN。"""
    board_arr = np.asarray(board)
    T = len(dates)
    N = board_arr.shape[0]
    st = np.asarray(is_st, dtype=bool)
    if st.shape != (T, N):
        raise ValueError("is_st 形状应为 %r (实际 %r)"
                         % ((T, N), st.shape))
    if is_delisting is None:
        dl = np.zeros((T, N), dtype=bool)
    else:
        dl = np.asarray(is_delisting, dtype=bool)
        if dl.shape != (T, N):
            raise ValueError("is_delisting 形状应为 %r (实际 %r)"
                             % ((T, N), dl.shape))
    eff_st = st & ~dl
    codes = np.array([_BOARD_CODES.get(str(b), -1) for b in board_arr],
                     dtype=int)
    pct = np.full((T, N), np.nan)
    for t in range(T):
        date_str = _as_date_str(dates[t])
        state = codes * 2 + eff_st[t].astype(int)
        for raw in np.unique(state):
            code = int(raw)
            if code < 0:
                continue
            pct[t, state == code] = rule_pct(
                _BOARD_NAMES[code // 2], bool(code % 2), date_str)
    return pct


def _ref_from_adj(prev_close, adj):
    """除权参考价：ref[t] = prev[t] × adj[t-1] / adj[t]（half-up 对齐到分）。

    adj 单侧缺失（任一非有限/非正）→ ref=NaN（不回退原始昨收）。
    """
    prev = np.asarray(prev_close, dtype=float)
    adj = np.asarray(adj, dtype=float)
    T, N = prev.shape
    out = np.full((T, N), np.nan)
    if T > 1:
        a0 = adj[:-1]
        a1 = adj[1:]
        ok = np.isfinite(a0) & (a0 > 0.0) & np.isfinite(a1) & (a1 > 0.0)
        ratio = np.full((T - 1, N), np.nan)
        np.divide(a0, a1, out=ratio, where=ok)
        exdiv = ok & (np.abs(ratio - 1.0) > 1e-6)
        raw = np.where(exdiv, prev[1:] * ratio, prev[1:])
        cents, cents_ok = _to_cents(raw)
        aligned = np.where(cents_ok, cents.astype(float) / 100.0, np.nan)
        out[1:] = np.where(ok, aligned, np.nan)
    return out


@dataclass(frozen=True, eq=False)
class TradabilityInputs(object):
    """构建器产出的面板数组 + meta（引擎可选入参）。"""
    close: np.ndarray
    high: np.ndarray
    low: np.ndarray
    open_: np.ndarray
    volume: np.ndarray
    suspended: np.ndarray
    dates: np.ndarray
    board: np.ndarray
    is_st: np.ndarray
    adj: np.ndarray
    is_delisting: np.ndarray = None
    no_limit: np.ndarray = None
    policy: TradabilityPolicy = None
    meta: dict = None


def can_trade(prev_close, high, low, volume, suspended, pct, policy=None):
    """返回 (can_buy, can_sell)。T+1 由 apply_tradability 以状态并入。"""
    policy = policy or TradabilityPolicy()
    prev_close = np.asarray(prev_close, dtype=float)
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    suspended = np.asarray(suspended, dtype=bool)
    if np.ndim(pct) == 0:
        pct_arr = np.full(prev_close.shape, float(pct))
    else:
        pct_arr = np.asarray(pct, dtype=float)
    up, down, unknown = compute_limits(prev_close, pct_arr)
    judge = ~unknown
    can_buy = ~suspended & (~judge | ~(high >= up - policy.eps))
    can_sell = ~suspended & (~judge | ~(low <= down + policy.eps))
    return can_buy, can_sell


def _as_bool_matrix(value, T, N, name):
    arr = np.asarray(value, dtype=bool)
    if arr.shape == (T, N):
        return arr
    if arr.shape == (N,):
        return np.broadcast_to(arr, (T, N))
    raise ValueError("%s 形状必须为 (%d,) 或 (%d,%d) (实际 %r)"
                     % (name, N, T, N, arr.shape))


def apply_tradability(target_w, prev_close, high, low, close, open_, volume,
                      suspended, board, is_st, dates, policy=None,
                      adj=None, is_delisting=None, no_limit=None, ref=None):
    """权重推进：返回 (effective_w, report)，report 九键均为 int。

    新增可选入参（默认 None 时权重推进路径与 v3.9.8 逐位一致）：
      adj / ref:     除权参考价（ref 优先）；adj 单侧缺失 → limit_unknown。
      is_st:         (N,) 或 (T,N)。
      is_delisting:  退市按板块普通档（不套 ST）。
      no_limit:      (T,N) 无涨跌幅限制日（IPO 前 5 日 / 退市整理首日）。
    board 允许 'unknown'：该格限价不可判定，计入 limit_unknown，不抛错。
    """
    policy = policy or TradabilityPolicy()
    if policy.execute_at not in ("next_open", "same_close"):
        raise ValueError("execute_at 非法: %r" % (policy.execute_at,))
    target_w = np.asarray(target_w, dtype=float)
    if target_w.ndim != 2:
        raise ValueError("target_w 必须为 (T,N) (实际 ndim=%d)" % target_w.ndim)
    T, N = target_w.shape
    prev_close = np.asarray(prev_close, dtype=float)
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    open_ = np.asarray(open_, dtype=float)
    volume = np.asarray(volume, dtype=float)
    suspended = np.asarray(suspended, dtype=bool)
    arrays = (prev_close, high, low, close, open_, volume, suspended)
    for name, arr in zip(("prev_close", "high", "low", "close", "open_",
                          "volume", "suspended"), arrays):
        if np.shape(arr) != (T, N):
            raise ValueError("%s 形状应为 %r (实际 %r)"
                             % (name, (T, N), np.shape(arr)))
    board = np.asarray(board)
    if board.shape != (N,):
        raise ValueError("board 形状必须为 (%d,)" % N)
    illegal = set(str(b) for b in board) - {"main", "star", "gem", "bse",
                                            "unknown"}
    if illegal:
        raise ValueError("board 含非法值: %r" % (sorted(illegal),))
    if len(dates) != T:
        raise ValueError("dates 长度应为 %d (实际 %d)" % (T, len(dates)))

    st_mat = _as_bool_matrix(is_st, T, N, "is_st")
    del_mat = (np.zeros((T, N), dtype=bool) if is_delisting is None
               else _as_bool_matrix(is_delisting, T, N, "is_delisting"))
    nolim = (np.zeros((T, N), dtype=bool) if no_limit is None
             else _as_bool_matrix(no_limit, T, N, "no_limit"))
    if ref is not None:
        ref = np.asarray(ref, dtype=float)
        if ref.shape != (T, N):
            raise ValueError("ref 形状应为 %r (实际 %r)"
                             % ((T, N), ref.shape))
    if adj is not None:
        adj = np.asarray(adj, dtype=float)
        if adj.shape != (T, N):
            raise ValueError("adj 形状应为 %r (实际 %r)"
                             % ((T, N), adj.shape))

    if ref is not None:
        ref_mat = ref
    elif adj is not None:
        ref_mat = _ref_from_adj(prev_close, adj)
    else:
        ref_mat = None
    pct_mat = _pct_matrix(board, st_mat, del_mat, dates)

    effective = np.zeros((T, N))
    pending = np.zeros(N)
    locked_until = np.full(N, -1, dtype=int)
    w_prev = np.zeros(N)
    report = {"blocked_buy": 0, "blocked_sell": 0, "blocked_suspend": 0,
              "t1_locked": 0, "deferred": 0, "carried": 0,
              "limit_unknown": 0, "one_word_up": 0, "one_word_down": 0}

    for t in range(T):
        pct_t = pct_mat[t]
        ref_t = None if ref_mat is None else ref_mat[t]
        up, down, unk = compute_limits(prev_close[t], pct_t, ref=ref_t)
        unk = unk | ~np.isfinite(pct_t)
        susp = suspended[t]
        judge = ~unk & ~nolim[t]
        can_buy = ~susp & (~judge | ~(high[t] >= up - policy.eps))
        can_sell = ~susp & (~judge | ~(low[t] <= down + policy.eps))
        if policy.t_plus_1:
            can_sell = can_sell & (locked_until <= t)
        target = target_w[t]

        same_price = high[t] == low[t]
        report["one_word_up"] += int(np.count_nonzero(
            judge & ~susp & same_price & (np.abs(high[t] - up)
                                          <= policy.eps)))
        report["one_word_down"] += int(np.count_nonzero(
            judge & ~susp & same_price & (np.abs(low[t] - down)
                                          <= policy.eps)))

        # 意图反转 → 旧 pending 清零（先于补单）
        desired = target - w_prev
        reversed_ = (pending != 0.0) & (desired != 0.0) & (
            np.sign(pending) != np.sign(desired))
        pending = np.where(reversed_, 0.0, pending)

        # 1) 先补 pending
        fill = np.zeros(N)
        buy_fill = (pending > 0.0) & can_buy
        sell_fill = (pending < 0.0) & can_sell
        fill[buy_fill] = pending[buy_fill]
        fill[sell_fill] = pending[sell_fill]
        if np.any(fill != 0.0):
            report["deferred"] += int(np.count_nonzero(fill))
            pending = pending - fill
            w_eff = w_prev + fill
            locked_until[fill > 0.0] = t + 1
        else:
            w_eff = w_prev.copy()

        # 2) 再处理当日 delta（补成交可能新锁定，卖出权需重算）
        can_sell_now = can_sell
        if policy.t_plus_1:
            can_sell_now = can_sell & (locked_until <= t)
        delta = target - w_eff
        busy = np.abs(delta) > policy.eps
        buy = busy & (delta > 0.0)
        sell = busy & (delta < 0.0)
        blocked_buy = buy & ~can_buy & ~susp & judge
        blocked_sell = sell & ~can_sell_now & ~susp & judge
        t1_mask = np.zeros(N, dtype=bool)
        if policy.t_plus_1:
            t1_mask = blocked_sell & (locked_until > t)
            blocked_sell = blocked_sell & ~t1_mask
        blocked_suspend = busy & susp
        limit_unknown = busy & ~susp & ~nolim[t] & unk

        exec_buy = np.where(buy & can_buy, delta, 0.0)
        exec_sell = np.where(sell & can_sell_now, delta, 0.0)
        w_eff = w_eff + exec_buy + exec_sell
        # pending 存「精确未成交缺口」（target - w_eff），而非逐日累加，
        # 避免连续不可成交日重复累计同一笔意图（design §7.4 第 4 步）。
        pending = target - w_eff
        locked_until[exec_buy > 0.0] = t + 1

        if policy.renormalize:
            gross = float(np.abs(w_eff).sum())
            want = float(np.abs(target).sum())
            if gross > 0.0 and want > 0.0:
                w_eff = w_eff * min(1.0, want / gross)

        report["blocked_buy"] += int(blocked_buy.sum())
        report["blocked_sell"] += int(blocked_sell.sum())
        report["blocked_suspend"] += int(blocked_suspend.sum())
        report["t1_locked"] += int(t1_mask.sum())
        report["limit_unknown"] += int(limit_unknown.sum())
        effective[t] = w_eff
        w_prev = w_eff

    if T:
        report["carried"] = int(np.count_nonzero(
            np.abs(effective[-1] - target_w[-1]) > 1e-12))
    return effective, report


@dataclass(frozen=True)
class CostModel(object):
    commission_bps: float = 2.5
    min_commission: float = 5.0
    stamp_tax_bps: float = 5.0
    transfer_fee_bps: float = 0.1
    slippage_bps: float = 0.0

    def cost(self, buy_notional, sell_notional):
        for value in (buy_notional, sell_notional):
            if not np.isfinite(value) or value < 0:
                raise ValueError("notional 必须为非负有限数 (实际 %r)" % (value,))

        def _commission(notional):
            if notional <= 0.0:
                return 0.0
            return max(self.min_commission,
                       notional * self.commission_bps / 1e4)

        commission = _commission(float(buy_notional)) + _commission(float(sell_notional))
        stamp_tax = float(sell_notional) * self.stamp_tax_bps / 1e4
        transfer_fee = (float(buy_notional) + float(sell_notional)) \
            * self.transfer_fee_bps / 1e4
        slippage = (float(buy_notional) + float(sell_notional)) \
            * self.slippage_bps / 1e4
        total = commission + stamp_tax + transfer_fee + slippage
        return {"commission": commission, "stamp_tax": stamp_tax,
                "transfer_fee": transfer_fee, "slippage": slippage,
                "total": total}
