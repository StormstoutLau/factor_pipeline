# -*- coding: utf-8 -*-
"""v3.9.0 回测交易现实性（独立函数；默认不接入引擎）。

依据：DESIGN_SYNTHETIC_VALIDATION_TRACEABILITY.md §7（v1.3）。
顶层依赖：stdlib + numpy；无 IO、无全局状态。
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

__all__ = ["LimitRule", "DEFAULT_LIMIT_RULES", "rule_pct", "limit_price",
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


def _pct_array(board, is_st, date_str):
    return np.asarray([rule_pct(b, bool(s), date_str)
                       for b, s in zip(board, is_st)], dtype=float)


def limit_price(prev_close, pct, side="up"):
    if side not in ("up", "down"):
        raise ValueError("side 必须 ∈ {up, down} (实际 %r)" % (side,))
    sign = 1.0 if side == "up" else -1.0
    return np.round(np.asarray(prev_close, dtype=float) * (1.0 + sign * pct), 2)


@dataclass(frozen=True)
class TradabilityPolicy(object):
    execute_at: str = "next_open"     # next_open | same_close（后者仅测试对照）
    t_plus_1: bool = True
    renormalize: bool = False
    eps: float = _EPS


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
    up = limit_price(prev_close, pct_arr, "up")
    down = limit_price(prev_close, pct_arr, "down")
    can_buy = ~suspended & ~(high >= up - policy.eps)
    can_sell = ~suspended & ~(low <= down + policy.eps)
    return can_buy, can_sell


def apply_tradability(target_w, prev_close, high, low, close, open_, volume,
                      suspended, board, is_st, dates, policy=None):
    """权重推进：返回 (effective_w, report)，report 六键均为 int。"""
    policy = policy or TradabilityPolicy()
    if policy.execute_at not in ("next_open", "same_close"):
        raise ValueError("execute_at 非法: %r" % (policy.execute_at,))
    target_w = np.asarray(target_w, dtype=float)
    if target_w.ndim != 2:
        raise ValueError("target_w 必须为 (T,N) (实际 ndim=%d)" % target_w.ndim)
    T, N = target_w.shape
    arrays = (prev_close, high, low, close, open_, volume, suspended)
    for name, arr in zip(("prev_close", "high", "low", "close", "open_",
                          "volume", "suspended"), arrays):
        if np.shape(arr) != (T, N):
            raise ValueError("%s 形状应为 %r (实际 %r)"
                             % (name, (T, N), np.shape(arr)))
    board = np.asarray(board)
    is_st = np.asarray(is_st, dtype=bool)
    if board.shape != (N,) or is_st.shape != (N,):
        raise ValueError("board/is_st 形状必须为 (%d,)" % N)
    if len(dates) != T:
        raise ValueError("dates 长度应为 %d (实际 %d)" % (T, len(dates)))
    unknown = set(str(b) for b in board) - {"main", "star", "gem", "bse"}
    if unknown:
        raise ValueError("board 含未知值: %r" % (sorted(unknown),))

    effective = np.zeros((T, N))
    pending = np.zeros(N)
    locked_until = np.full(N, -1, dtype=int)
    w_prev = np.zeros(N)
    report = {"blocked_buy": 0, "blocked_sell": 0, "blocked_suspend": 0,
              "t1_locked": 0, "deferred": 0, "carried": 0}

    for t in range(T):
        pct = _pct_array(board, is_st, _as_date_str(dates[t]))
        can_buy, can_sell = can_trade(prev_close[t], high[t], low[t],
                                      volume[t], suspended[t], pct, policy)
        if policy.t_plus_1:
            can_sell = can_sell & (locked_until <= t)
        target = target_w[t]
        susp = np.asarray(suspended[t], dtype=bool)

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
        blocked_buy = buy & ~can_buy & ~susp
        blocked_sell = sell & ~can_sell_now & ~susp
        t1_mask = np.zeros(N, dtype=bool)
        if policy.t_plus_1:
            t1_mask = blocked_sell & (locked_until > t)
            blocked_sell = blocked_sell & ~t1_mask
        blocked_suspend = busy & susp

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
