# -*- coding: utf-8 -*-
"""P-022 收口证据脚本：U-7 月度覆盖 / U-8 close 对拍 / R-3 健康度-漂移敏感性。

用法：
    python scripts/verify_tradability_closeout.py --data-root E:\\Ashare_data \
        --out out/tradability_closeout.json
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_PARENT = os.path.dirname(_ROOT)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from backtest.engine import FactorBacktestEngine  # noqa: E402
from backtest.tradability_loader import TradabilitySpec  # noqa: E402
from backtest.tradability_inputs import _suspend_mask  # noqa: E402

__all__ = ["u7_coverage", "u8_mismatch", "r3_sensitivity", "build_report"]


class _FakeDL(object):
    def __init__(self, factor, close):
        self.n_dates, self.n_stocks = close.shape
        self.price_data = {"close": close}
        self.factor_data = {"f1": factor}


def _read_panel(data_root, panel_dir, name):
    path = os.path.join(data_root, panel_dir, "stock_%s.pkl" % name)
    if not os.path.exists(path):
        return None
    frame = pd.read_pickle(path)
    if not isinstance(frame.index, pd.DatetimeIndex):
        try:
            frame.index = pd.to_datetime(frame.index)
        except (ValueError, TypeError):
            pass
    return frame


def _align(frame, dates, codes):
    if frame is None:
        return None
    if isinstance(frame, pd.Series):
        frame = frame.to_frame()
    return frame.reindex(index=dates, columns=codes)


def _load_price_panel(path, dates, codes):
    """读取独立价格面板；支持 (dates×codes) 或转置 (codes×dates)。"""
    low = str(path).lower()
    if low.endswith((".pkl", ".pickle")):
        frame = pd.read_pickle(path)
    else:
        frame = pd.read_csv(path, index_col=0)
    if not isinstance(frame.index, pd.DatetimeIndex):
        try:
            frame.index = pd.to_datetime(frame.index)
        except (ValueError, TypeError):
            frame.index = pd.to_datetime(frame.index, errors="coerce")
    if not frame.index.isin(dates).any() and frame.columns.isin(dates).any():
        frame = frame.T
        if not isinstance(frame.index, pd.DatetimeIndex):
            frame.index = pd.to_datetime(frame.index)
    return frame.reindex(index=dates, columns=codes)


def u7_coverage(close, high, low, open_, suspend, min_coverage=0.99):
    """逐月覆盖率（与 loader 同口径：eligible=finite(close)&~suspend）。"""
    dates, codes = close.index, list(close.columns)
    close_a = close.to_numpy(dtype=float)
    high_a = (high.reindex(index=dates, columns=codes).to_numpy(dtype=float)
              if high is not None else np.full(close_a.shape, np.nan))
    low_a = (low.reindex(index=dates, columns=codes).to_numpy(dtype=float)
             if low is not None else np.full(close_a.shape, np.nan))
    open_a = (open_.reindex(index=dates, columns=codes).to_numpy(dtype=float)
              if open_ is not None else np.full(close_a.shape, np.nan))
    susp_a, _ = _suspend_mask(suspend, dates, codes)
    eligible_all = np.isfinite(close_a) & ~susp_a

    rows = []
    for (y, m) in sorted(set((d.year, d.month) for d in dates)):
        mask = (dates.year == y) & (dates.month == m)
        k = int(mask.sum())
        if k < 2:
            continue
        el = eligible_all[mask]
        denom = int(np.count_nonzero(el))
        if denom == 0:
            rows.append({"month": "%04d-%02d" % (y, m), "days": k,
                         "high_low": 0.0, "open": 0.0, "prev": 0.0,
                         "eligible_cells": 0, "mode": "off"})
            continue
        hl = float(np.count_nonzero(
            (np.isfinite(high_a[mask]) & np.isfinite(low_a[mask])) & el)
            / denom)
        op = float(np.count_nonzero(np.isfinite(open_a[mask]) & el) / denom)
        prev = np.full((k, close_a.shape[1]), np.nan)
        prev[1:] = close_a[mask][:-1]
        prev_el = el.copy()
        prev_el[0] = False
        pv = float(np.count_nonzero(np.isfinite(prev) & prev_el)
                   / max(1, int(np.count_nonzero(prev_el))))
        mode = ("off" if (op < min_coverage or pv < min_coverage) else
                "full" if hl >= min_coverage else "execution_only_open")
        rows.append({"month": "%04d-%02d" % (y, m), "days": k,
                     "high_low": round(hl, 6), "open": round(op, 6),
                     "prev": round(pv, 6), "eligible_cells": denom,
                     "mode": mode})
    worst = {k: {"min": round(min(r[k] for r in rows), 6),
                 "max": round(max(r[k] for r in rows), 6)}
             for k in ("high_low", "open", "prev")}
    below = {k: [r["month"] for r in rows if r[k] < min_coverage]
             for k in ("high_low", "open", "prev")}
    modes = {m: sum(1 for r in rows if r["mode"] == m)
             for m in ("full", "execution_only_open", "off")}
    return {"months": rows, "worst": worst, "below_099": below,
            "modes": modes}


def u8_mismatch(inputs_close, price_close):
    """close 对拍计数；同源时 mismatch=0。"""
    a = np.asarray(inputs_close, dtype=float)
    b = np.asarray(price_close, dtype=float)
    if a.shape != b.shape:
        raise ValueError("close 形状不一致: %r vs %r" % (a.shape, b.shape))
    mism = int(np.count_nonzero(~np.isclose(a, b, equal_nan=True)))
    total = int(a.size)
    return {"cells_total": total, "mismatch_cells": mism,
            "mismatch_ratio": mism / float(total) if total else 0.0}


def _turnover_drift(t):
    if len(t) < 2:
        return 0.0
    mid = len(t) // 2
    early = np.nanmean(t[:mid])
    late = np.nanmean(t[mid:])
    if np.isnan(early) or np.isnan(late) or abs(early) < 1e-10:
        return 0.0
    return float(max(0, (late / early - 1)) * 100)


def r3_sensitivity(close, spec):
    """3 因子 turnover → 健康度/漂移敏感性。"""
    dates, codes = close.index, list(close.columns)
    close_a = close.to_numpy(dtype=float)
    factors = {
        "mom20": close.pct_change(20, fill_method=None),
        "rev5": -close.pct_change(5, fill_method=None),
        "vol20": -close.pct_change(fill_method=None).rolling(20).std(),
    }
    inputs, meta = spec.build(dates, codes)
    rows = []
    cfg = {"ic_method": "rank", "top_n": 0.2, "ls_method": "top_n",
           "max_lag": 12}
    for name, fac in factors.items():
        off = FactorBacktestEngine(
            _FakeDL(fac.to_numpy(dtype=float), close_a),
            config=cfg).run()["f1"]
        on = FactorBacktestEngine(
            _FakeDL(fac.to_numpy(dtype=float), close_a),
            config=cfg, tradability_inputs=inputs).run()["f1"]
        t_off = np.asarray(off["turnover"], dtype=float)
        t_on = np.asarray(on["turnover"], dtype=float)
        m_off, m_on = float(np.nanmean(t_off)), float(np.nanmean(t_on))
        d_off, d_on = _turnover_drift(t_off), _turnover_drift(t_on)
        c_off = float(np.clip((m_off - 1.0) / (0.0 - 1.0) * 100, 0, 100))
        c_on = float(np.clip((m_on - 1.0) / (0.0 - 1.0) * 100, 0, 100))
        rows.append({
            "factor": name, "turnover_mean_off": m_off,
            "turnover_mean_on": m_on,
            "turnover_delta_pct": ((m_on / m_off - 1) * 100
                                   if m_off else None),
            "turnover_drift_off": d_off, "turnover_drift_on": d_on,
            "crowding_score_off": c_off, "crowding_score_on": c_on,
            "health_score_delta": 0.25 * (c_on - c_off),
            "crowding_alert_off": bool(m_off > 0.80),
            "crowding_alert_on": bool(m_on > 0.80),
            "combined_drift_delta": 0.20 * (d_on - d_off),
            "icir_identical": bool(np.isclose(
                off.get("rank_icir", np.nan), on.get("rank_icir", np.nan),
                equal_nan=True)),
            "ls_identical": bool(np.allclose(
                np.asarray(off.get("long_short_returns")),
                np.asarray(on.get("long_short_returns")), equal_nan=True)),
        })
    mode = inputs.policy.mode if inputs is not None else "off"
    return {"mode": mode, "factors": rows}


def build_report(data_root, panel_dir="market_data", only=None,
                 min_coverage=0.99, price_panel=None):
    wanted = set(only) if only else {"u7", "u8", "r3"}
    close = _read_panel(data_root, panel_dir, "close")
    if close is None:
        raise ValueError("缺少 stock_close.pkl")
    dates, codes = close.index, list(close.columns)
    high = _align(_read_panel(data_root, panel_dir, "high"), dates, codes)
    low = _align(_read_panel(data_root, panel_dir, "low"), dates, codes)
    open_ = _align(_read_panel(data_root, panel_dir, "open"), dates, codes)
    suspend = _align(_read_panel(data_root, panel_dir, "suspend"),
                     dates, codes)
    out = {}
    if "u7" in wanted:
        out["u7"] = u7_coverage(close, high, low, open_, suspend,
                                min_coverage=min_coverage)
    if "u8" in wanted:
        if price_panel:
            price = _load_price_panel(price_panel, dates, codes)
            out["u8"] = u8_mismatch(close.to_numpy(dtype=float),
                                    price.to_numpy(dtype=float))
            out["u8"]["basis"] = "external_panel"
        else:
            out["u8"] = u8_mismatch(close.to_numpy(dtype=float),
                                    close.to_numpy(dtype=float))
            out["u8"]["basis"] = "same_panel"
    if "r3" in wanted:
        spec = TradabilitySpec(data_root=data_root, panel_dir=panel_dir,
                               mode="auto", min_coverage=min_coverage)
        out["r3"] = r3_sensitivity(close, spec)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="P-022 tradability 收口证据")
    ap.add_argument("--data-root", default=r"E:\Ashare_data")
    ap.add_argument("--panel-dir", default="market_data")
    ap.add_argument("--out", default="out/tradability_closeout.json")
    ap.add_argument("--only", default="u7,u8,r3",
                    help="逗号分隔：u7,u8,r3")
    ap.add_argument("--price-panel", default=None,
                    help="U-8 独立价格面板（pkl/csv；dates×codes 或转置）")
    args = ap.parse_args(argv)
    only = [x.strip() for x in args.only.split(",") if x.strip()]
    report = build_report(args.data_root, args.panel_dir, only=only,
                          price_panel=args.price_panel)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print("WROTE", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
