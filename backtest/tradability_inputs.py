# -*- coding: utf-8 -*-
"""P-006/P-021：pandas 面板 → TradabilityInputs + meta（纯函数，无 IO）。

依据：spec/p006-tradability-engine-integration/DESIGN.md §4.6
      spec/p021-tradability-production-enablement/DESIGN.md §4.4 / §6.1
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
    if (df.index.equals(index) and df.columns.equals(columns)
            and isinstance(fill, (float, np.floating)) and np.isnan(fill)
            and (df.dtypes == np.float64).all()):
        return df
    out = df.reindex(index=index, columns=columns)
    return out.fillna(fill).astype(dtype)


def _panel(df, index, columns):
    """DataFrame/Series/ndarray → (T,N) DataFrame；ndarray 需同形。"""
    if isinstance(df, pd.DataFrame):
        if df.index.equals(index) and df.columns.equals(columns):
            return df
        return df.reindex(index=index, columns=columns)
    if isinstance(df, pd.Series):
        return df.to_frame().reindex(index=index, columns=columns)
    arr = np.asarray(df, dtype=float)
    if arr.shape != (len(index), len(columns)):
        raise ValueError("面板形状应为 %r (实际 %r)"
                         % ((len(index), len(columns)), arr.shape))
    return pd.DataFrame(arr, index=index, columns=columns)


def _normalize_panel(df, index, columns):
    """对齐到 (index, columns) 并返回 float ndarray；None → None。"""
    if df is None:
        return None
    return _panel(df, index, columns).to_numpy(dtype=float)


def _suspend_mask(df, index, columns):
    """停牌面板 → (mask, missing)。

    bool 面板：True=停牌（既有契约）；object 面板：仅 'S'=停牌。
    按「原始 df 的 dtypes」逐列判定——bool 面板经 reindex 补缺列/行后整帧
    升型 object，用对齐后的 dtypes 会整体误入 'S' 路径。
    """
    if df is None:
        return (np.zeros((len(index), len(columns)), bool),
                np.ones((len(index), len(columns)), bool))
    raw = df.reindex(index=index, columns=columns)
    missing = raw.isna().to_numpy()
    dtypes = getattr(df, "dtypes", None)
    out = np.zeros(raw.shape, dtype=bool)
    for j, col in enumerate(raw.columns):
        dtype = None if dtypes is None else dtypes.get(col)
        if dtype is not None and pd.api.types.is_bool_dtype(dtype):
            out[:, j] = raw.iloc[:, j].fillna(False).astype(bool).to_numpy()
        else:
            out[:, j] = raw.iloc[:, j].astype(object).eq("S").to_numpy(
                dtype=bool)          # 'R'/None/NaN → 可交易
    return out, missing


def _coverage(mask, eligible):
    denom = int(np.count_nonzero(eligible))
    if denom <= 0:
        return 0.0
    return float(np.count_nonzero(mask & eligible) / denom)


def build_tradability_inputs(close, high, low, open_, volume, suspend, name,
                             adj=None, list_date=None, policy=None,
                             st_overrides=None, limit_up=None,
                             limit_down=None, ref=None,
                             name_codes=None, name_st_lut=None,
                             name_del_lut=None, suspend_mask=None,
                             suspend_missing=None, *,
                             prev_close0=None, adj_prev0=None,
                             name_carry=None, no_limit_override=None,
                             return_counts=False):
    """面板（dates×stocks）→ (TradabilityInputs, meta)，纯函数、无 IO。

    adj 与 ref 至少一个；都 None → ValueError。
    list_date: Series/dict（code → 上市日），用于 IPO 后前 5 个交易日 no_limit。
    st_overrides: DataFrame/list（code, effective_date）公告覆盖表，
        仅用于统计 st_date_unverified，不改变派生状态。
    limit_up/limit_down: 外部限价（stk_limit），须成对；缺格回退自算。

    P-023（keyword-only，默认 None/False → 旧行为逐位不变）：
      prev_close0/adj_prev0/name_carry: 分块首行的上一日关键帧；
      no_limit_override: 全局预计算的 (T,N) bool（builder 仅 &= ~suspend）；
      return_counts: True → 返回 (inputs, counts)；否则 (inputs, meta)。
    """
    if adj is None and ref is None:
        raise ValueError("build_tradability_inputs 需要 adj 或 ref")
    policy = policy or TradabilityPolicy()
    if (limit_up is None) != (limit_down is None):
        raise ValueError("limit_up 与 limit_down 必须成对提供")

    index = close.index
    columns = close.columns
    index_dt = (index if isinstance(index, pd.DatetimeIndex)
                else pd.DatetimeIndex(pd.to_datetime(index)))

    close_a = _frame(close, index, columns, np.nan, float).to_numpy()
    high_a = _frame(high, index, columns, np.nan, float).to_numpy()
    low_a = _frame(low, index, columns, np.nan, float).to_numpy()
    open_a = _frame(open_, index, columns, np.nan, float).to_numpy()
    volume_a = _frame(volume, index, columns, np.nan, float).to_numpy()
    adj_a = _normalize_panel(adj, index, columns)
    limit_up_a = _normalize_panel(limit_up, index, columns)
    limit_down_a = _normalize_panel(limit_down, index, columns)

    if suspend_mask is not None:
        if suspend_missing is None:
            raise ValueError("suspend_mask 与 suspend_missing 必须成对提供")
        suspend_a = np.asarray(suspend_mask, dtype=bool)
        suspend_missing = np.asarray(suspend_missing, dtype=bool)
        if suspend_a.shape != (len(index), len(columns)):
            raise ValueError("suspend_mask 形状应为 %r"
                             % ((len(index), len(columns)),))
        if suspend_missing.shape != suspend_a.shape:
            raise ValueError("suspend_missing 形状应与 suspend_mask 一致")
    elif suspend_missing is not None:
        raise ValueError("suspend_missing 必须与 suspend_mask 成对提供")
    else:
        suspend_a, suspend_missing = _suspend_mask(suspend, index, columns)

    T, N = close_a.shape
    dates_arr = np.array([pd.Timestamp(d).strftime("%Y-%m-%d")
                          for d in index_dt])
    last_filled_name = np.full(N, np.nan, dtype=object)

    boards = np.array([board_of(code) for code in columns])
    board_counts = dict(Counter(boards.tolist()))
    unknown_codes = [str(code) for code, b in zip(columns, boards)
                     if b == "unknown"][:20]

    if name_codes is not None:
        if name_st_lut is None or name_del_lut is None:
            raise ValueError("name_codes 需要 name_st_lut/name_del_lut")
        st_lut_arr = np.asarray(name_st_lut)
        del_lut_arr = np.asarray(name_del_lut)
        if st_lut_arr.ndim != 1 or del_lut_arr.ndim != 1:
            raise ValueError("name_st_lut/name_del_lut 必须为一维")
        if name_codes.shape != (len(index), len(columns)):
            raise ValueError("name_codes 形状应为 %r"
                             % ((len(index), len(columns)),))
        raw = name_codes
        if not (raw.index.equals(index) and raw.columns.equals(columns)):
            raw = raw.reindex(index=index, columns=columns)
        name_missing = raw.isna().to_numpy()
        if name_carry is not None and T > 0:
            carry = np.asarray(name_carry, dtype=np.float32)
            if carry.shape != (N,):
                raise ValueError("name_carry 形状应为 (%d,) (实际 %r)"
                                 % (N, carry.shape))
            codes_np = raw.to_numpy(dtype=np.float32, copy=True)
            invalid = ~np.isfinite(codes_np[0])
            codes_np[0, invalid] = carry[invalid]
            filled = pd.DataFrame(codes_np, index=index, columns=columns) \
                .ffill().to_numpy(dtype=np.float32)
            del codes_np
        else:
            filled = raw.ffill().to_numpy(dtype=np.float32)
        if T > 0:
            last_filled_name = filled[-1].copy()
        valid = np.isfinite(filled)
        idx = np.where(valid, filled, 0).astype(np.int32)
        is_st = np.zeros(valid.shape, dtype=bool)
        is_delisting = np.zeros(valid.shape, dtype=bool)
        if valid.any():
            if int(idx[valid].max()) >= len(st_lut_arr):
                raise ValueError("name_st_lut 长度不足")
            if int(idx[valid].max()) >= len(del_lut_arr):
                raise ValueError("name_del_lut 长度不足")
            is_st[valid] = st_lut_arr[idx[valid]]
            is_delisting[valid] = del_lut_arr[idx[valid]]
    else:
        name_raw = (pd.DataFrame(np.nan, index=index, columns=columns,
                                 dtype=object)
                    if name is None
                    else name.reindex(index=index, columns=columns))
        name_missing = name_raw.isna().to_numpy()
        if name_carry is not None and T > 0:
            carry = np.asarray(name_carry, dtype=object)
            if carry.shape != (N,):
                raise ValueError("name_carry 形状应为 (%d,) (实际 %r)"
                                 % (N, carry.shape))
            raw_np = name_raw.to_numpy(dtype=object, copy=True)
            invalid = pd.isna(raw_np[0])
            raw_np[0, invalid] = carry[invalid]
            name_a = pd.DataFrame(raw_np, index=index, columns=columns) \
                .ffill().fillna("")
            del raw_np
        else:
            name_a = name_raw.ffill().fillna("")
        if T > 0:
            last_filled_name = name_a.iloc[-1].to_numpy(dtype=object)

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
    if no_limit_override is not None:
        no_limit = np.array(no_limit_override, dtype=bool, copy=True)
        if no_limit.shape != (T, N):
            raise ValueError("no_limit_override 形状应为 %r (实际 %r)"
                             % ((T, N), no_limit.shape))
        if list_date is not None:
            no_limit_source = "list_date"
    elif list_date is not None:
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

    if no_limit_override is None:
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
    if prev_close0 is not None:
        prev0 = np.asarray(prev_close0, dtype=float)
        if prev0.shape != (N,):
            raise ValueError("prev_close0 形状应为 (%d,) (实际 %r)"
                             % (N, prev0.shape))
        if T > 0:
            prev[0] = prev0

    # ── 除权参考价 + D2 回退 ──────────────────────────────
    if ref is not None:
        ref_mat = _normalize_panel(ref, index, columns)
    else:
        ref_mat = _ref_from_adj(prev, adj_a, prev_adj=adj_prev0)
    fallback = ~np.isfinite(ref_mat) & np.isfinite(prev) & (prev > 0.0)
    if policy.unknown_policy == "fallback_raw":
        ref_mat = np.where(fallback, prev, ref_mat)
        ref_fallback_cells = int(fallback.sum())
        ref_fallback_days = int(fallback.any(axis=1).sum())
    else:
        ref_fallback_cells = 0
        ref_fallback_days = 0
    adj_source = ("adj" if adj is not None
                  else ("ref_fallback" if ref is not None else "none"))

    # ── 规则 gap（D3）────────────────────────────────────
    pct_mat, gap_mask = _pct_matrix(boards, is_st, is_delisting, dates_arr,
                                    return_gaps=True)
    rule_gap_cells = int(gap_mask.sum())
    rule_gap_days = int(gap_mask.any(axis=1).sum())
    rule_gap_bse_cells = int(np.count_nonzero(gap_mask & (boards == "bse")))
    if np.any(gap_mask & (boards == "bse")):
        rule_gap_reason = "neeq_pre_select"
    elif gap_mask.any():
        rule_gap_reason = "unknown_board"
    else:
        rule_gap_reason = None

    # ── 限价表缺格统计（回退自算）────────────────────────
    if limit_up_a is not None:
        table_missing = ~np.isfinite(limit_up_a) | ~np.isfinite(limit_down_a)
        limit_table_missing_cells = int(np.count_nonzero(table_missing))
        limit_table_source = ("stk_limit_partial"
                              if limit_table_missing_cells
                              else "stk_limit")
    else:
        limit_table_missing_cells = 0
        limit_table_source = "self_computed"

    # ── 一字诊断（D4；降级模式关闭）──────────────────────
    one_word_disabled = policy.mode == "execution_only_open"
    one_word_up = 0
    one_word_down = 0
    eps = policy.eps
    if limit_up_a is not None:
        merged_up = limit_up_a.copy()
        merged_down = limit_down_a.copy()
    else:
        merged_up = merged_down = None
    if limit_up_a is not None or not one_word_disabled:
        for t in range(T):
            up, down, unk = compute_limits(prev[t], pct_mat[t],
                                           ref=ref_mat[t])
            if limit_up_a is not None:
                # 缺格回退自算（D5）；外部格逐格优先（INV-10）
                up = np.where(np.isfinite(limit_up_a[t]), limit_up_a[t], up)
                down = np.where(np.isfinite(limit_down_a[t]),
                                limit_down_a[t], down)
                merged_up[t] = up
                merged_down[t] = down
            if one_word_disabled:
                continue
            judge = ~unk & ~no_limit[t] & ~suspend_a[t]
            same = high_a[t] == low_a[t]
            one_word_up += int(np.count_nonzero(
                judge & same & (np.abs(high_a[t] - up) <= eps)))
            one_word_down += int(np.count_nonzero(
                judge & same & (np.abs(low_a[t] - down) <= eps)))
    limit_up_a, limit_down_a = merged_up, merged_down

    # ── 覆盖率 + 数据分级（D0-D5）────────────────────────
    eligible = np.isfinite(close_a) & ~suspend_a
    high_low_coverage = _coverage(
        np.isfinite(high_a) & np.isfinite(low_a), eligible)
    open_coverage = _coverage(np.isfinite(open_a), eligible)
    if T > 1:
        prev_eligible = eligible.copy()
        prev_eligible[0] = False
        prev_close_coverage = _coverage(np.isfinite(prev), prev_eligible)
    else:
        prev_close_coverage = 0.0

    suspend_missing_cells = int(np.count_nonzero(suspend_missing))
    suspend_missing_days = int(suspend_missing.any(axis=1).sum())
    name_missing_cells = int(np.count_nonzero(name_missing))
    name_missing_days = int(name_missing.any(axis=1).sum())
    adj_missing_days = (T if adj is None else int(np.any(
        ~np.isfinite(adj_a) | (adj_a <= 0.0), axis=1).sum()))
    tiers = []
    if ref_fallback_cells > 0 or adj_source == "ref_fallback":
        tiers.append(1)
    if name_missing_cells > 0:
        tiers.append(2)
    if suspend_missing_cells > 0:
        tiers.append(3)
    if list_date is None or no_limit_source != "list_date":
        tiers.append(4)
    tier = min(tiers) if tiers else 0      # D1 最差（DESIGN §6.2）
    data_tier = "D%d" % tier
    if tier == 0:
        bias_direction = "none"
    elif tier <= 3:
        bias_direction = "optimistic"
    else:
        bias_direction = "conservative"

    missing_fields = []
    if adj is None:
        missing_fields.append("adj")
    if name_missing_cells > 0 or (name is None and name_codes is None):
        missing_fields.append("name")
    if suspend_missing_cells > 0 or (suspend is None and suspend_mask is None):
        missing_fields.append("suspend")
    if list_date is None:
        missing_fields.append("list_date")
    if high_low_coverage < 1.0 or open_coverage < 1.0:
        missing_fields.append("ohlc")

    if adj is None:
        price_basis_detail = "raw_close"
    elif ref_fallback_cells > 0:
        price_basis_detail = "raw_adj_ref_with_fallback"
    else:
        price_basis_detail = "raw_adj_ref_full"

    meta = {
        "board_counts": board_counts,
        "unknown_codes": unknown_codes,
        "st_stock_days": int(is_st.sum()),
        "delisting_stock_days": int(is_delisting.sum()),
        "no_limit_cells": int(no_limit.sum()),
        "no_limit_source": no_limit_source,
        "adj_missing_days": adj_missing_days,
        "one_word_up_cells": one_word_up,
        "one_word_down_cells": one_word_down,
        "st_date_unverified": st_date_unverified,
        "st_calibration_source": st_calibration_source,
        "price_basis": ("raw_close" if adj is None else "raw_adj_ref"),
        "rounding_basis": ("inferred_half_up" if board_counts.get("bse", 0)
                           else "exchange_half_up"),
    }

    diagnostics = {
        "schema_version": 2,
        "mode": policy.mode,
        "one_word_disabled": bool(one_word_disabled),
        "high_low_coverage": high_low_coverage,
        "open_coverage": open_coverage,
        "prev_close_coverage": prev_close_coverage,
        "adj_source": adj_source,
        "data_tier": data_tier,
        "missing_fields": missing_fields,
        "bias_direction": bias_direction,
        "price_basis_detail": price_basis_detail,
        "unknown_policy": policy.unknown_policy,
        "ref_fallback_cells": ref_fallback_cells,
        "ref_fallback_days": ref_fallback_days,
        "name_missing_cells": name_missing_cells,
        "name_missing_days": name_missing_days,
        "suspend_missing_cells": suspend_missing_cells,
        "suspend_missing_days": suspend_missing_days,
        "rule_gap_cells": rule_gap_cells,
        "rule_gap_days": rule_gap_days,
        "rule_gap_reason": rule_gap_reason,
        "limit_table_source": limit_table_source,
        "limit_table_missing_cells": limit_table_missing_cells,
    }

    inputs = TradabilityInputs(
        close=close_a, high=high_a, low=low_a, open_=open_a, volume=volume_a,
        suspended=suspend_a, dates=dates_arr, board=boards, is_st=is_st,
        adj=adj_a, is_delisting=is_delisting, no_limit=no_limit,
        policy=policy, meta=meta, ref=ref_mat,
        limit_up=limit_up_a, limit_down=limit_down_a,
        codes=np.array([str(c) for c in columns], dtype=object),
        diagnostics=diagnostics)
    if return_counts:
        counts = {
            "eligible_cells": int(np.count_nonzero(eligible)),
            "high_low_covered": int(np.count_nonzero(
                np.isfinite(high_a) & np.isfinite(low_a) & eligible)),
            "open_covered": int(np.count_nonzero(
                np.isfinite(open_a) & eligible)),
            "name_missing_cells": name_missing_cells,
            "name_missing_days": name_missing_days,
            "suspend_missing_cells": suspend_missing_cells,
            "suspend_missing_days": suspend_missing_days,
            "ref_fallback_cells": ref_fallback_cells,
            "ref_fallback_days": ref_fallback_days,
            "rule_gap_cells": rule_gap_cells,
            "rule_gap_days": rule_gap_days,
            "rule_gap_bse_cells": rule_gap_bse_cells,
            "one_word_up": one_word_up,
            "one_word_down": one_word_down,
            "limit_table_missing_cells": limit_table_missing_cells,
            "st_date_unverified": st_date_unverified,
            "no_limit_cells": int(no_limit.sum()),
            "st_stock_days": int(is_st.sum()),
            "delisting_stock_days": int(is_delisting.sum()),
            "adj_missing_days": adj_missing_days,
            "last_filled_name": last_filled_name,
        }
        return inputs, counts
    return inputs, meta
