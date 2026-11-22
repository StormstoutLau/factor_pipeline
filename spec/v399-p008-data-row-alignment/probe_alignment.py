# -*- coding: utf-8 -*-
"""P-008 调研探针：39 月分钟 vs 日频覆盖核对（只读）。

口径：分钟侧 = 单日文件经 `_keep_mask` 过滤后的唯一 stock_code 数；
日频侧 = 单日 stock_close 非空列数。输出 JSON 到 --out（默认系统临时目录），
不写仓库、不修改任何数据文件。

用法：
    python spec/v399-p008-data-row-alignment/probe_alignment.py \
        --out %TEMP%\\p008_alignment.json
"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.feather as feather

MINUTE_ROOT = Path(r"E:\Level 1 Data")
DAILY_CLOSE = r"E:\Ashare_data\market_data\stock_close.pkl"
START, END = "2020-01", "2023-03"


def keep_mask(codes):
    return ((codes >= 1) & (codes < 1000000)
            & ~((codes >= 390000) & (codes < 400000)))


def minute_codes(path):
    tab = feather.read_table(path, columns=["stock_code"])
    codes = tab.column("stock_code").to_numpy()
    return tab.num_rows, {format(int(c), "06d")
                          for c in np.unique(codes[keep_mask(codes)])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(
        Path(tempfile.gettempdir()) / "p008_alignment.json"))
    args = ap.parse_args()

    files = [p for p in sorted(MINUTE_ROOT.glob("*.feather"))
             if START <= p.stem[:7] <= END]
    close = pd.read_pickle(DAILY_CLOSE)
    close.index = pd.to_datetime(close.index)
    sub = close.loc["2020-01-01":"2023-03-31"]
    daily_sets = {d.strftime("%Y-%m-%d"): set(row.dropna().index)
                  for d, row in sub.iterrows()}

    t0 = time.time()
    rows = []
    for i, path in enumerate(files):
        day = path.stem
        n_rows, mset = minute_codes(path)
        dset = daily_sets.get(day, set())
        rows.append({
            "date": day, "month": day[:7], "min_rows": int(n_rows),
            "min_stocks": len(mset), "daily_stocks": len(dset),
            "both": len(mset & dset), "min_only": len(mset - dset),
            "daily_only": len(dset - mset),
        })
        if (i + 1) % 200 == 0:
            print("scanned", i + 1, "files", round(time.time() - t0, 1), "s")

    df = pd.DataFrame(rows)
    min_days = set(df["date"])
    daily_days = set(daily_sets)
    months = []
    for ym, g in df.groupby("month"):
        n_daily = sum(1 for d in daily_days if d[:7] == ym)
        months.append({
            "month": ym, "min_days": int(len(g)), "daily_days": int(n_daily),
            "day_diff": int(len(g) - n_daily),
            "min_stock_days": int(g["min_stocks"].sum()),
            "daily_stock_days": int(g["daily_stocks"].sum()),
            "stock_day_diff_pct": round(
                float(g["min_stocks"].sum() - g["daily_stocks"].sum())
                / max(float(g["daily_stocks"].sum()), 1.0) * 100.0, 4),
            "both": int(g["both"].sum()), "min_only": int(g["min_only"].sum()),
            "daily_only": int(g["daily_only"].sum()),
        })

    df["diff_pct"] = (df["min_stocks"] - df["daily_stocks"]) \
        / df["daily_stocks"].clip(lower=1) * 100.0
    outliers = df[df["diff_pct"].abs() > 5.0].sort_values("diff_pct")

    min_all, daily_all = set(), set().union(*daily_sets.values())
    for path in files:
        _, mset = minute_codes(path)
        min_all |= mset
    only_daily = sorted(daily_all - min_all)

    result = {
        "window": [START, END],
        "minute_files": len(files),
        "daily_days_in_window": int(len(sub)),
        "matched_days": len(min_days & daily_days),
        "minute_only_days": sorted(min_days - daily_days),
        "daily_only_days": sorted(daily_days - min_days),
        "months": months,
        "outlier_days_gt5pct": outliers.to_dict(orient="records"),
        "code_universe": {
            "minute_unique": len(min_all),
            "daily_unique": len(daily_all),
            "intersection": len(min_all & daily_all),
            "daily_only": len(only_daily),
            "minute_only": len(min_all - daily_all),
            "daily_only_prefix": dict(Counter(c[:1] for c in only_daily)),
        },
        "totals": {
            "min_stock_days": int(df["min_stocks"].sum()),
            "daily_stock_days": int(df["daily_stocks"].sum()),
            "both": int(df["both"].sum()),
            "min_only": int(df["min_only"].sum()),
            "daily_only": int(df["daily_only"].sum()),
        },
        "elapsed_s": round(time.time() - t0, 1),
    }
    Path(args.out).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in (
        "window", "minute_files", "daily_days_in_window", "matched_days",
        "daily_only_days", "totals", "code_universe", "elapsed_s")},
        ensure_ascii=False, indent=2))
    print("OUT", args.out)


if __name__ == "__main__":
    main()
