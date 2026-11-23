# -*- coding: utf-8 -*-
"""P-021 C 批：tradability 内部一致性对拍（离线脚本，不依赖 token）。

对拍口径：
  ref_adj = _ref_from_adj(prev_close, adj)            # 本仓实现
  ref_ret = close / (1 + stock_return / 100)          # 数据源收益反推
逐板块统计有限格一致率，并校验 BSE 2020-07-27 规则边界。

用法：
  python scripts/verify_tradability_consistency.py --data-root E:\\Ashare_data
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.dirname(_ROOT))     # flat layout: factor_pipeline 包父目录

from backtest.tradability import _ref_from_adj, board_of, rule_pct  # noqa: E402


def _read(root, name):
    path = os.path.join(root, "market_data", "stock_%s.pkl" % name)
    if not os.path.exists(path):
        return None
    return pd.read_pickle(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\Ashare_data")
    parser.add_argument("--output", default="out/tradability_consistency.json")
    parser.add_argument("--rtol", type=float, default=1e-3)
    parser.add_argument("--atol", type=float, default=0.005)
    args = parser.parse_args()

    close = _read(args.data_root, "close")
    adj = _read(args.data_root, "adj")
    ret = _read(args.data_root, "return")
    if close is None or adj is None or ret is None:
        raise SystemExit("缺少面板：close/adj/return 均为必需")

    dates = close.index.intersection(adj.index).intersection(ret.index)
    codes = close.columns.intersection(adj.columns).intersection(ret.columns)
    close = close.loc[dates, codes]
    adj = adj.loc[dates, codes]
    ret = ret.loc[dates, codes]

    prev = close.shift(1)
    ref_adj = _ref_from_adj(prev.to_numpy(dtype=float),
                            adj.to_numpy(dtype=float))
    ref_ret = close.to_numpy(dtype=float) / (
        1.0 + ret.to_numpy(dtype=float) / 100.0)

    boards = np.array([board_of(c) for c in codes])
    finite = np.isfinite(ref_adj) & np.isfinite(ref_ret) & (ref_ret > 0)
    close_ok = np.isclose(ref_adj, ref_ret, rtol=args.rtol, atol=args.atol,
                          equal_nan=False)
    by_board = {}
    for board in sorted(set(boards.tolist())):
        mask = np.broadcast_to((boards == board)[None, :], finite.shape)
        denom = int(np.count_nonzero(finite & mask))
        hit = int(np.count_nonzero(finite & mask & close_ok))
        by_board[board] = {"cells": denom, "match": hit,
                           "rate": (hit / denom) if denom else None}

    mism = np.argwhere(finite & ~close_ok)[:20]
    mismatch_samples = [
        {"date": str(dates[i])[:10], "code": str(codes[j]),
         "ref_adj": float(ref_adj[i, j]), "ref_ret": float(ref_ret[i, j])}
        for i, j in mism]

    # BSE 规则边界（2020-07-27 前无规则、当日 30%）
    try:
        bse_new = rule_pct("bse", False, "2020-07-27")
    except ValueError:
        bse_new = None
    try:
        bse_old = rule_pct("bse", False, "2020-07-24")
    except ValueError:
        bse_old = None

    report = {
        "data_root": args.data_root,
        "n_dates": int(len(dates)),
        "n_codes": int(len(codes)),
        "finite_cells": int(np.count_nonzero(finite)),
        "overall_rate": (float(np.count_nonzero(finite & close_ok)
                               / np.count_nonzero(finite))
                         if np.any(finite) else None),
        "by_board": by_board,
        "bse_rule": {"2020-07-27": bse_new, "2020-07-24": bse_old},
        "mismatch_samples": mismatch_samples,
        "tolerance": {"rtol": args.rtol, "atol": args.atol},
    }
    out_dir = os.path.dirname(os.path.abspath(args.output))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in
                      ("n_dates", "n_codes", "finite_cells",
                       "overall_rate", "bse_rule")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
