# -*- coding: utf-8 -*-
"""P-006：pandas 面板 → TradabilityInputs + meta（纯函数，无 IO）。

依据：spec/p006-tradability-engine-integration/DESIGN.md §4.6 / §3.3。
"""
from collections import Counter

import numpy as np
import pandas as pd

from .tradability import (TradabilityInputs, TradabilityPolicy, board_of,
                          compute_limits, _pct_matrix, _ref_from_adj)

__all__ = ["build_tradability_inputs"]


def _norm_code(code):
    """代码键归一：剥离交易所后缀并补齐 6 位（'600000.SH'→'600000'，1→'000001'）。"""
    return str(code).split(".")[0].zfill(6)


def _frame(df, index, columns, fill, dtype):
    if df is None:
        return pd.DataFrame(fill, index=index, columns=columns, dtype=dtype)
    out = df.reindex(index=index, columns=columns)
    return out.fillna(fill).astype(dtype)


def build_tradability_inputs(close, high, low, open_, volume, suspend, name,
                             adj, list_date=None, policy=None,
                             st_overrides=None):
    """面板（dates×stocks）→ (TradabilityInputs, meta)，纯函数、无 IO。

    adj 为必填（后复权因子）；缺失 → ValueError（禁止无基准回退）。
    list_date: Series/dict（code → 上市日），用于 IPO 后前 5 个交易日 no_limit。
    st_overrides: DataFrame/list（code, effective_date）公告覆盖表，
        仅用于统计 st_date_unverified，不改变派生状态。
    """
    if adj is None:
        raise ValueError("build_tradability_inputs 需要 adj（后复权因子）")
    index = close.index
    columns = close.columns
    index_dt = (index if isinstance(index, pd.DatetimeIndex)
                else pd.DatetimeIndex(pd.to_datetime(index)))

    close_a = _frame(close, index, columns, np.nan, float).to_numpy()
    high_a = _frame(high, index, columns, np.nan, float).to_numpy()
    low_a = _frame(low, index, columns, np.nan, float).to_numpy()
    open_a = _frame(open_, index, columns, np.nan, float).to_numpy()
    volume_a = _frame(volume, index, columns, np.nan, float).to_numpy()
    suspend_a = _frame(suspend, index, columns, False, bool).to_numpy()
    name_a = _frame(name, index, columns, "", object)
    adj_a = _frame(adj, index, columns, np.nan, float).to_numpy()

    T, N = close_a.shape
    dates_arr = np.array([pd.Timestamp(d).strftime("%Y-%m-%d")
                          for d in index_dt])

    boards = np.array([board_of(code) for code in columns])
    board_counts = dict(Counter(boards.tolist()))
    unknown_codes = [str(code) for code, b in zip(columns, boards)
                     if b == "unknown"][:20]

    name_np = name_a.to_numpy(dtype=object)
    is_st = np.zeros((T, N), dtype=bool)
    is_delisting = np.zeros((T, N), dtype=bool)
    for j in range(N):
        column = name_np[:, j]
        is_st[:, j] = np.fromiter(("ST" in str(v) for v in column),
                                  dtype=bool, count=T)
        is_delisting[:, j] = np.fromiter(("退" in str(v) for v in column),
                                         dtype=bool, count=T)

    no_limit = np.zeros((T, N), dtype=bool)
    no_limit_source = "delisting_only"
    if list_date is not None:
        ld = pd.Series(list_date)
        norm = {}
        for k, v in ld.items():
            norm.setdefault(_norm_code(k), v)      # 首见优先
        used = False
        for j, code in enumerate(columns):
            if code in ld.index:                   # 精确优先（INV-4）
                value = ld.loc[code]
            else:
                nk = _norm_code(code)
                if nk not in norm:                 # 缺失判定与取值为两步
                    continue
                value = norm[nk]
            if pd.isna(value):
                continue
            used = True
            pos = np.flatnonzero(index_dt >= pd.Timestamp(value))
            no_limit[pos[:5], j] = True
        if used:
            no_limit_source = "list_date"

    for j in range(N):
        first = np.flatnonzero(is_delisting[:, j])
        if first.size:
            no_limit[first[0], j] = True
    no_limit &= ~suspend_a

    st_calibration_source = "none"
    st_date_unverified = 0
    if st_overrides is not None:
        st_calibration_source = "coverage_table"
        overrides = pd.DataFrame(st_overrides)
        for _, row in overrides.iterrows():
            code = _norm_code(row.iloc[0])
            matched = [j for j, c in enumerate(columns)
                       if _norm_code(c) == code]
            if not matched:
                continue
            j = matched[0]
            first = np.flatnonzero(is_st[:, j])
            derived = index_dt[first[0]] if first.size else None
            if derived is None or pd.Timestamp(derived) != pd.Timestamp(
                    row.iloc[1]):
                st_date_unverified += 1

    prev = np.full((T, N), np.nan)
    if T > 1:
        prev[1:] = close_a[:-1]
    pct_mat = _pct_matrix(boards, is_st, is_delisting, dates_arr)
    ref_mat = _ref_from_adj(prev, adj_a)
    eps = (policy if policy is not None else TradabilityPolicy()).eps
    one_word_up = 0
    one_word_down = 0
    for t in range(T):
        up, down, unk = compute_limits(prev[t], pct_mat[t], ref=ref_mat[t])
        judge = ~unk & ~no_limit[t] & ~suspend_a[t]
        same = high_a[t] == low_a[t]
        one_word_up += int(np.count_nonzero(
            judge & same & (np.abs(high_a[t] - up) <= eps)))
        one_word_down += int(np.count_nonzero(
            judge & same & (np.abs(low_a[t] - down) <= eps)))

    meta = {
        "board_counts": board_counts,
        "unknown_codes": unknown_codes,
        "st_stock_days": int(is_st.sum()),
        "delisting_stock_days": int(is_delisting.sum()),
        "no_limit_cells": int(no_limit.sum()),
        "no_limit_source": no_limit_source,
        "adj_missing_days": int(np.any(
            ~np.isfinite(adj_a) | (adj_a <= 0.0), axis=1).sum()),
        "one_word_up_cells": one_word_up,
        "one_word_down_cells": one_word_down,
        "st_date_unverified": st_date_unverified,
        "st_calibration_source": st_calibration_source,
        "price_basis": "raw_adj_ref",
        "rounding_basis": ("inferred_half_up" if board_counts.get("bse", 0)
                           else "exchange_half_up"),
    }

    inputs = TradabilityInputs(
        close=close_a, high=high_a, low=low_a, open_=open_a, volume=volume_a,
        suspended=suspend_a, dates=dates_arr, board=boards, is_st=is_st,
        adj=adj_a, is_delisting=is_delisting, no_limit=no_limit,
        policy=policy, meta=meta)
    return inputs, meta
