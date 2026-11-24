# -*- coding: utf-8 -*-
"""P-023 内存证据脚本：M-1 / M-2 / M-3 可复现读数。

用法：
    python scripts/verify_tradability_memory.py --data-root E:\\Ashare_data \
        --out out/tradability_memory_p023.json
    python scripts/verify_tradability_memory.py --skip-spawn   # 仅 M-1/M-2
"""
import argparse
import json
import os
import subprocess
import sys
import time
import tracemalloc

import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_PARENT = os.path.dirname(_ROOT)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from backtest.engine import FactorBacktestEngine  # noqa: E402
from backtest.tradability_loader import (  # noqa: E402
    TradabilitySpec, _PANEL_CACHE)

__all__ = ["build_report", "child_run", "main"]

DEFAULTS = {"panel_dir": "market_data", "chunk_days": 60,
            "run_index": 1}


def _rss_mb():
    try:
        import psutil
        return round(psutil.Process().memory_info().rss
                     / (1024.0 * 1024.0), 1)
    except ImportError:
        return None


def _cache_mb():
    """常驻 name/suspend 紧凑记录（float/raw 不计，plan 不缓存）。"""
    name_bytes = suspend_bytes = 0
    for key, rec in _PANEL_CACHE.items():
        if rec.kind == "name":
            name_bytes += int(np.asarray(rec.data).nbytes)
            for arr in (rec.aux[1], rec.aux[2]):
                name_bytes += int(np.asarray(arr).nbytes)
        elif rec.kind == "suspend":
            suspend_bytes += int(np.asarray(rec.data[0]).nbytes)
            suspend_bytes += int(np.asarray(rec.data[1]).nbytes)
    mb = 1024.0 * 1024.0
    return {"name_mb": round(name_bytes / mb, 1),
            "suspend_mb": round(suspend_bytes / mb, 1),
            "total_mb": round((name_bytes + suspend_bytes) / mb, 1)}


class _FakeDL(object):
    def __init__(self, factor, close):
        self.n_dates, self.n_stocks = close.shape
        self.price_data = {"close": close}
        self.factor_data = {"f1": factor}


def _universe(data_root, panel_dir, dates_limit=None, codes_limit=None):
    path = os.path.join(data_root, panel_dir, "stock_close.pkl")
    if not os.path.exists(path):
        raise FileNotFoundError("缺少面板: %s" % path)
    frame = pd.read_pickle(path)
    dates = pd.DatetimeIndex(pd.to_datetime(frame.index))
    codes = [str(c) for c in frame.columns]
    if dates_limit:
        dates = dates[:int(dates_limit)]
    if codes_limit:
        codes = codes[:int(codes_limit)]
    return dates, codes


def build_report(data_root, panel_dir="market_data", dates_limit=None,
                 codes_limit=None, chunk_days=60, run_index=1):
    """M-1/M-2：plan 预扫 + 首轮全部分块 build（无 float 整幅缓存）。"""
    dates, codes = _universe(data_root, panel_dir, dates_limit, codes_limit)
    spec = TradabilitySpec(data_root=data_root, panel_dir=panel_dir,
                           max_dates_per_chunk=int(chunk_days))
    rows = []
    tracemalloc.start()
    t0 = time.perf_counter()
    plan = spec.build_plan(dates, codes)
    t_plan = time.perf_counter()
    for chunk in plan.iter_chunks():
        t1 = time.perf_counter()
        plan.build_chunk(chunk)
        rows.append({"chunk": int(chunk.start), "dates": int(chunk.stop
                                                            - chunk.start),
                     "build_s": round(time.perf_counter() - t1, 6),
                     "apply_s": None})
    t_build = time.perf_counter()
    peak = tracemalloc.get_traced_memory()[1] / (1024.0 * 1024.0)
    tracemalloc.stop()
    plan.finalize()
    return {
        "meta": {
            "data_root": data_root,
            "panel_dir": panel_dir,
            "n_dates": int(len(dates)),
            "n_codes": int(len(codes)),
            "chunk_days": int(chunk_days),
            "run_index": int(run_index),
            "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": plan.mode,
        },
        "m1": {
            "plan_s": round(t_plan - t0, 6),
            "build_all_chunks_s": round(t_build - t_plan, 6),
            "total_s": round(t_build - t0, 6),
        },
        "m2": {"tracemalloc_peak_mb": round(peak, 1)},
        "m3": None,
        "m4": _cache_mb(),
        "m6": {"rss_after_mb": _rss_mb()},
        "rows": rows,
    }


def child_run(data_root, panel_dir="market_data", dates_limit=None,
              codes_limit=None, chunk_days=60):
    """M-3 子进程：build_plan + 单因子流式 run。"""
    dates, codes = _universe(data_root, panel_dir, dates_limit, codes_limit)
    spec = TradabilitySpec(data_root=data_root, panel_dir=panel_dir,
                           max_dates_per_chunk=int(chunk_days))
    plan = spec.build_plan(dates, codes)
    T, N = len(dates), len(codes)
    close = np.ones((T, N))
    factor = np.tile(np.linspace(-1.0, 1.0, N), (T, 1))
    engine = FactorBacktestEngine(_FakeDL(factor, close),
                                  config={"top_n": 0.2},
                                  tradability_plan=plan)
    engine.run()
    return 0


def _spawn_peak(cmd):
    try:
        import psutil
    except ImportError:
        raise RuntimeError("M-3 需要 psutil；可安装或使用 --skip-spawn")
    proc = psutil.Popen(cmd, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
    peak = 0
    try:
        while proc.poll() is None:
            try:
                peak = max(peak, proc.memory_info().rss)
            except psutil.Error:
                break
            time.sleep(0.05)
        return_code = proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
    return {
        "peak_rss_mb": round(peak / (1024.0 * 1024.0), 1),
        "returncode": int(return_code),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="P-023 tradability worker 内存证据（M-1/M-2/M-3）")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--panel-dir", default=DEFAULTS["panel_dir"])
    parser.add_argument("--out", default=os.path.join(
        "out", "tradability_memory_p023.json"))
    parser.add_argument("--dates-limit", type=int, default=None)
    parser.add_argument("--codes-limit", type=int, default=None)
    parser.add_argument("--chunk-days", type=int,
                        default=DEFAULTS["chunk_days"])
    parser.add_argument("--run-index", type=int, default=DEFAULTS["run_index"])
    parser.add_argument("--skip-spawn", action="store_true")
    parser.add_argument("--child", action="store_true")
    args = parser.parse_args(argv)

    if args.child:
        rc = child_run(args.data_root, args.panel_dir, args.dates_limit,
                       args.codes_limit, args.chunk_days)
        print(json.dumps({"status": "child-done", "returncode": rc}))
        return rc
    try:
        report = build_report(args.data_root, args.panel_dir,
                              args.dates_limit, args.codes_limit,
                              args.chunk_days, args.run_index)
        if not args.skip_spawn:
            cmd = [sys.executable, os.path.abspath(__file__),
                   "--data-root", args.data_root,
                   "--panel-dir", args.panel_dir,
                   "--chunk-days", str(args.chunk_days),
                   "--child"]
            if args.dates_limit:
                cmd += ["--dates-limit", str(args.dates_limit)]
            if args.codes_limit:
                cmd += ["--codes-limit", str(args.codes_limit)]
            report["m3"] = _spawn_peak(cmd)
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)},
                         ensure_ascii=False))
        return 2
    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"status": "ok", "out": args.out,
                      "m1": report["m1"], "m2": report["m2"],
                      "m3": report["m3"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
