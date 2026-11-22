# -*- coding: utf-8 -*-
"""P-008 数据行数对齐：离线三方分解审计（只读）。

设计依据：v399-p008-data-row-alignment DESIGN §3.3/§4.3；
实施依据：同批 IMPLEMENTATION §3.2/§4.3。
本模块只在 ``--alignment-audit`` 分支按需 import，默认路径零引用（INV-9）。
"""
import json
from pathlib import Path

import numpy as np

from ..ports import CalibrationUnavailable
from .loaders import _keep_mask, has_pyarrow

__all__ = ["audit_alignment", "write_alignment_report"]


def _dstr(value):
    """日期归一为 ``YYYY-MM-DD``（D-398-6）。"""
    return str(value)[:10]


def _pct(a, b):
    if not b:
        return None
    return round((float(a) - float(b)) / float(b) * 100.0, 2)


def _daily_side(close, lo_m, hi_m):
    """窗口内日频逐日非空码（int32 数组）+ 码域并集。

    窗口按**月份**判定（与 ``MinuteLoader.available_months`` 同口径）。
    """
    by_day, universe = {}, set()
    for pos, idx in enumerate(close.index):
        day = _dstr(idx)
        if not (lo_m <= day[:7] <= hi_m):
            continue
        row = close.iloc[pos]
        codes = np.asarray([int(str(c)) for c in row.index[row.notna()]],
                           dtype=np.int32)
        by_day[day] = codes
        universe.update(int(c) for c in codes)
    return by_day, universe


def _minute_side(loader, lo_m, hi_m):
    """窗口内分钟逐日唯一码（int32 数组）+ 零成交码。"""
    if not has_pyarrow():
        raise CalibrationUnavailable("pyarrow 未安装（pip install .[calib]）")
    import pyarrow.feather as feather
    root = getattr(loader, "root", None)
    if root is None or not Path(root).is_dir():
        raise CalibrationUnavailable("分钟数据根不可用: %s" % root)
    by_day, zero_by_day = {}, {}
    for path in sorted(Path(root).glob("*.feather")):
        day = _dstr(path.stem)
        if not (lo_m <= day[:7] <= hi_m):
            continue
        table = feather.read_table(str(path),
                                   columns=["stock_code", "amount"])
        frame = table.to_pandas()
        frame = frame.loc[_keep_mask(frame["stock_code"].to_numpy())]
        if frame.empty:
            by_day[day] = np.empty(0, dtype=np.int32)
            zero_by_day[day] = np.empty(0, dtype=np.int32)
            continue
        codes = np.unique(frame["stock_code"].to_numpy(np.int64))
        by_day[day] = codes.astype(np.int32)
        sums = frame.groupby("stock_code")["amount"].sum()
        zero_by_day[day] = np.asarray(
            [int(code) for code, value in sums.items()
             if float(value) == 0.0], dtype=np.int32)
    return by_day, zero_by_day


def _identity_failed(totals):
    """双口径恒等式独立守卫（DESIGN §7）；True = 残差非 0，报告不可采信。

    独立重算 totals 五项口径，不复用分解循环内的 residual 中间量。
    """
    residual_matched = (totals["A_matched"] + totals["C"]
                        - totals["minute_only"]
                        - (totals["daily_matched"] - totals["minute"]))
    residual_full = (totals["A_full"] + totals["C"] + totals["D"]
                     - totals["minute_only"]
                     - (totals["daily_full"] - totals["minute"]))
    return bool(residual_matched or residual_full)


def audit_alignment(cfg, loader, close, start=None, end=None):
    """39 月分钟↔日频行数三方分解（只读）。

    Args:
        cfg: CalibrationConfig（取窗口口径）
        loader: MinuteLoader（提供 root）
        close: 日频收盘矩阵（index=交易日，columns=股票代码）
        start/end: 可选窗口覆盖（默认 cfg.minute_start / minute_end）

    Returns:
        dict: window / scope / totals / code_universe / identity /
              months / outlier_days / missing_minute_days
    """
    lo = _dstr(start or cfg.minute_start)[:7]
    hi = _dstr(end or cfg.minute_end)[:7]
    daily_by_day, daily_universe = _daily_side(close, lo, hi)
    minute_by_day, _zero = _minute_side(loader, lo, hi)
    minute_universe = set()
    for codes in minute_by_day.values():
        minute_universe.update(int(c) for c in codes)

    minute_dates = set(minute_by_day)
    daily_dates = sorted(daily_by_day)
    matched_dates = [d for d in daily_dates if d in minute_dates]
    missing_dates = [d for d in daily_dates if d not in minute_dates]
    months = sorted({d[:7] for d in daily_dates}
                    | {d[:7] for d in minute_dates})

    month_rows = []
    totals = dict(minute=0, daily_full=0, daily_matched=0, both=0,
                  minute_only=0, daily_only_full=0, daily_only_matched=0,
                  A_matched=0, A_full=0, C=0, D=0, zero_pairs=0)
    outlier_days = []
    for ym in months:
        m_dates = [d for d in daily_dates if d[:7] == ym]
        m_matched = [d for d in m_dates if d in minute_dates]
        m_minute_only_dates = [d for d in minute_dates if d[:7] == ym]
        minute_rows = sum(len(minute_by_day[d])
                          for d in m_minute_only_dates)
        daily_matched = sum(len(daily_by_day[d]) for d in m_matched)
        daily_full = sum(len(daily_by_day[d]) for d in m_dates)
        both = b = daily_only_matched = a_matched = c_part = d_part = 0
        for day in m_matched:
            m_set = set(int(c) for c in minute_by_day.get(day, ()))
            d_set = set(int(c) for c in daily_by_day[day])
            both += len(m_set & d_set)
            b += len(m_set - d_set)
            only = d_set - m_set
            a_day = len([c for c in only if c not in minute_universe])
            a_matched += a_day
            daily_only_matched += len(only)
            c_part += len(only) - a_day
            daily_n = len(d_set)
            minute_n = len(m_set)
            if daily_n:
                dev = (minute_n - daily_n) / float(daily_n) * 100.0
                if abs(dev) > 5.0:
                    outlier_days.append({"date": day, "minute": minute_n,
                                         "daily": daily_n,
                                         "diff_pct": round(dev, 2)})
        a_missing = d_part = 0
        for day in m_dates:
            if day in minute_dates:
                continue
            m_set = set(int(c) for c in minute_by_day.get(day, ()))
            d_set = set(int(c) for c in daily_by_day[day])
            only = d_set - m_set
            a_missing += len([c for c in only if c not in minute_universe])
            d_part += len([c for c in only if c in minute_universe])
        # 分钟有、日频无的日子：该日全部分钟码计入 B（保持恒等式）
        for day in m_minute_only_dates:
            if day not in daily_by_day:
                b += len(minute_by_day[day])
        zero = sum(len(_zero.get(d, ())) for d in m_minute_only_dates)
        a_full = a_matched + a_missing
        month_rows.append({
            "month": ym, "minute": int(minute_rows),
            "daily_matched": int(daily_matched),
            "daily_full": int(daily_full),
            "both": int(both), "minute_only": int(b),
            "daily_only_matched": int(daily_only_matched),
            "daily_only_full": int(daily_only_matched + d_part),
            "A_matched": int(a_matched), "A_full": int(a_full),
            "C": int(c_part), "D": int(d_part),
            "diff_matched_pct": _pct(minute_rows, daily_matched),
            "diff_full_pct": _pct(minute_rows, daily_full),
            "zero_pairs": int(zero)})
        totals["minute"] += int(minute_rows)
        totals["daily_full"] += int(daily_full)
        totals["daily_matched"] += int(daily_matched)
        totals["both"] += int(both)
        totals["minute_only"] += int(b)
        totals["daily_only_full"] += int(daily_only_matched + d_part)
        totals["daily_only_matched"] += int(daily_only_matched)
        totals["A_matched"] += int(a_matched)
        totals["A_full"] += int(a_full)
        totals["C"] += int(c_part)
        totals["D"] += int(d_part)
        totals["zero_pairs"] += int(zero)

    residual_matched = (totals["A_matched"] + totals["C"]
                        - totals["minute_only"]
                        - (totals["daily_matched"] - totals["minute"]))
    residual_full = (totals["A_full"] + totals["C"] + totals["D"]
                     - totals["minute_only"]
                     - (totals["daily_full"] - totals["minute"]))
    daily_only_codes = sorted(daily_universe - minute_universe)
    prefix = {}
    for code in daily_only_codes:
        key = str(int(code))[0]
        prefix[key] = prefix.get(key, 0) + 1
    missing_minute_days = [
        {"date": day, "daily": int(len(daily_by_day[day]))}
        for day in missing_dates]

    return {
        "window": [lo, hi],
        "scope": {"matched_days": len(matched_dates),
                  "daily_days": len(daily_dates),
                  "minute_days": len(minute_dates)},
        "totals": totals,
        "code_universe": {
            "minute": len(minute_universe),
            "daily": len(daily_universe),
            "daily_only": len(daily_only_codes),
            "minute_only": len(minute_universe - daily_universe),
            "daily_only_prefix": dict(sorted(prefix.items()))},
        "identity": {
            "matched": "%d + %d - %d = %d"
            % (totals["A_matched"], totals["C"], totals["minute_only"],
               totals["daily_matched"] - totals["minute"]),
            "full": "%d + %d + %d - %d = %d"
            % (totals["A_full"], totals["C"], totals["D"],
               totals["minute_only"],
               totals["daily_full"] - totals["minute"]),
            "residual": int(residual_matched),
            "residual_full": int(residual_full)},
        "months": month_rows,
        "outlier_days": sorted(outlier_days, key=lambda x: x["date"]),
        "missing_minute_days": missing_minute_days,
    }
    if _identity_failed(totals):
        payload["alignment_identity_failed"] = True
    return payload


def _render_alignment_md(payload):
    """只从 payload 渲染（D-398-5）。"""
    totals = payload.get("totals") or {}
    scope = payload.get("scope") or {}
    uni = payload.get("code_universe") or {}
    ident = payload.get("identity") or {}
    lines = ["# P-008 数据行数对齐审计", "",
             "- 窗口: `%s` ~ `%s`"
             % tuple((payload.get("window") or ["?", "?"])[:2]),
             "- 匹配日 / 日频交易日 / 分钟交易日: %s / %s / %s"
             % (scope.get("matched_days"), scope.get("daily_days"),
                scope.get("minute_days")),
             "", "## 三方分解", "",
             "| 口径 | 分钟 | 日频 | both | B | daily_only | A（匹配日） | A（全窗口） | C | D | 残差 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
             "| 匹配日 | %s | %s | %s | %s | %s | %s | - | %s | - | %s |"
             % (totals.get("minute"), totals.get("daily_matched"),
                totals.get("both"), totals.get("minute_only"),
                totals.get("daily_only_matched"), totals.get("A_matched"),
                totals.get("C"), ident.get("residual")),
             "| 全窗口 | %s | %s | %s | %s | %s | - | %s | %s | %s | %s |"
             % (totals.get("minute"), totals.get("daily_full"),
                totals.get("both"), totals.get("minute_only"),
                totals.get("daily_only_full"), totals.get("A_full"),
                totals.get("C"), totals.get("D"), ident.get("residual_full")),
             ""]
    if payload.get("alignment_identity_failed"):
        lines += ["> **⚠ 恒等式校验失败（alignment_identity_failed）**："
                  "双口径残差非 0，本报告不可采信。", ""]
    lines += ["- 恒等式（匹配日）：`%s`" % ident.get("matched"),
              "- 恒等式（全窗口）：`%s`" % ident.get("full"),
              "- 残差（匹配日）: **%s**" % ident.get("residual"),
              "- 残差（全窗口）: **%s**" % ident.get("residual_full"),
              "", "## 码域", "",
              "- 分钟 %s / 日频 %s / 日频独有 %s / 分钟独有 %s"
              % (uni.get("minute"), uni.get("daily"), uni.get("daily_only"),
                 uni.get("minute_only")),
              "- 日频独有码首位: %s" % (uni.get("daily_only_prefix") or {}),
              "", "## 日级异常（|差异| > 5%）", "",
              "| 日期 | 分钟 | 日频 | 差异 |", "|---|---:|---:|---:|"]
    outliers = payload.get("outlier_days") or []
    lines += ["| %s | %s | %s | %+.2f%% |"
              % (o["date"], o["minute"], o["daily"], o["diff_pct"])
              for o in outliers] if outliers else ["| （无） | - | - | - |"]
    lines += ["", "## 缺失分钟日", ""]
    missing = payload.get("missing_minute_days") or []
    lines += ["- %s（日频 %s）" % (m["date"], m["daily"]) for m in missing] \
        if missing else ["- （无）"]
    lines += ["", "## 逐月", "",
              "| 月份 | 分钟 | 日频（匹配日） | 差异（匹配日） | 日频（全窗口） | 差异（全窗口） | 零成交 |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for row in payload.get("months") or []:
        lines.append("| %s | %s | %s | %s | %s | %s | %s |"
                     % (row["month"], row["minute"], row["daily_matched"],
                        _fmt_pct(row.get("diff_matched_pct")),
                        row["daily_full"],
                        _fmt_pct(row.get("diff_full_pct")),
                        row.get("zero_pairs")))
    return "\n".join(lines) + "\n"


def _fmt_pct(value):
    return "n/a" if value is None else "%+.2f%%" % float(value)


def write_alignment_report(payload, json_path):
    """写 JSON + 同名 .md；返回落盘路径列表。"""
    target = Path(json_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    md = target.with_suffix(".md")
    md.write_text(_render_alignment_md(payload), encoding="utf-8")
    return [str(target), str(md)]
