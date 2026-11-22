# -*- coding: utf-8 -*-
"""P-010 粒度偏差探针（只读；复用 out/panel_cache，不改生产代码）。

对照四种口径：
  D  stock×day 等权（现行生产口径，含 cap_month 抽样）
  M  stock×month 等权（DESIGN §5.2 目标口径：p/impact/sigma 月内均值）
  D+mc / M+mc  月聚类 bootstrap CI（现行 _bootstrap_ci 为 iid 行抽样）
并比较 CV：行序连续切折（现行）vs 按月份分组切折。

输出 JSON 到 stdout（也写 %TEMP% 下 p010_granularity.json）。
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = r"F:\Coding\factor_pipeline"
sys.path.insert(0, os.path.dirname(ROOT))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import verify_capacity_impact as v  # noqa: E402
from backtest.execution.config import CalibrationConfig  # noqa: E402
from backtest.execution.core.impact import SqrtImpact, cross_val_rmse  # noqa: E402
from backtest.execution.shell.loaders import MinuteLoader  # noqa: E402
from backtest.execution.shell.panels import (  # noqa: E402
    PARTIAL_MIN_DAYS, SAMPLE_CAP, MinutePanelBuilder, _sample_indices)

N_BOOT = 200
SEED = 20261122


def fit_c(p, y, s):
    return float(SqrtImpact().fit(p, y, s)["c"])


def boot_iid(p, y, s, n_boot=N_BOOT, seed=SEED):
    rng = np.random.default_rng(seed)
    n = p.size
    reps = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        try:
            reps.append(fit_c(p[idx], y[idx], s[idx]))
        except ValueError:
            continue
    if len(reps) < 20:
        return None, None
    return float(np.percentile(reps, 5.0)), float(np.percentile(reps, 95.0))


def boot_month(p, y, s, months, n_boot=N_BOOT, seed=SEED):
    """按月整块重采样（月内行同进同出）。"""
    rng = np.random.default_rng(seed)
    uniq = np.array(sorted(set(months)))
    groups = {m: np.where(months == m)[0] for m in uniq}
    reps = []
    for _ in range(n_boot):
        pick = rng.choice(uniq, size=uniq.size, replace=True)
        idx = np.concatenate([groups[m] for m in pick])
        try:
            reps.append(fit_c(p[idx], y[idx], s[idx]))
        except ValueError:
            continue
    if len(reps) < 20:
        return None, None
    return float(np.percentile(reps, 5.0)), float(np.percentile(reps, 95.0))


def cv_row(p, y, s):
    out = cross_val_rmse([SqrtImpact()], p, y, s, n_folds=5)
    return float(out["sqrt"])


def cv_month(p, y, s, months, n_folds=5):
    """按月份连续分组切折（组内整月进出）。"""
    uniq = np.array(sorted(set(months)))
    blocks = np.array_split(uniq, max(2, min(n_folds, uniq.size)))
    errs = []
    for block in blocks:
        test = np.isin(months, block)
        if not test.any() or test.all():
            continue
        try:
            params = SqrtImpact().fit(p[~test], y[~test], s[~test])
            pred = SqrtImpact().predict(p[test], s[test], params)
            errs.append(float(np.sum((pred - y[test]) ** 2)))
        except ValueError:
            return None
    if not errs:
        return None
    return float(np.sqrt(np.mean(errs)))


def main():
    market = v.build_panels(v.DATA_ROOT)
    cfg = CalibrationConfig(data_root=v.DATA_ROOT)
    loader = MinuteLoader(cfg.minute_root, sigma_bars=cfg.bvc_sigma_bars)
    builder = MinutePanelBuilder(
        cfg, loader=loader, daily=v.daily_ref(market, cfg),
        cache_dir=os.path.join(ROOT, "out", "panel_cache"))

    avail = set(loader.available_months())
    target = [m for m in builder._expected_months() if m in avail]
    usable = []
    for ym in target:
        n_files = builder._file_count(ym)
        want = (builder.daily.days_by_month or {}).get(ym)
        if want and n_files < int(want):
            if n_files < PARTIAL_MIN_DAYS:
                continue
        usable.append(ym)
    cap_month = int(np.ceil(SAMPLE_CAP / float(max(len(usable), 1))))

    builder._samples = []
    for ym in usable:
        agg, _ = builder._load_month(ym)
        start = len(builder._samples)
        builder._month_lambda(ym, agg)
        chunk = builder._samples[start:]
        if len(chunk) > cap_month:
            idx = _sample_indices(
                np.asarray([c[0] for c in chunk], dtype=float),
                np.asarray([c[2] for c in chunk], dtype=float), cap_month)
            builder._samples[start:] = [chunk[int(i)] for i in idx]

    rows = builder._samples
    p = np.asarray([r[0] for r in rows], dtype=float)
    y = np.asarray([r[1] for r in rows], dtype=float)
    s = np.asarray([r[2] for r in rows], dtype=float)
    code = np.asarray([r[3] for r in rows], dtype=np.int64)
    month = np.asarray([r[4] for r in rows], dtype=object)

    # stock×month 聚合（p / y / s 月内均值）
    frame = pd.DataFrame({"p": p, "y": y, "s": s, "code": code,
                          "month": month})
    g = frame.groupby(["month", "code"], sort=True)[["p", "y", "s"]].mean()
    p_m = g["p"].to_numpy(float)
    y_m = g["y"].to_numpy(float)
    s_m = g["s"].to_numpy(float)
    months_m = g.index.get_level_values(0).to_numpy(object)

    c_d = fit_c(p, y, s)
    c_m = fit_c(p_m, y_m, s_m)
    out = {
        "meta": {
            "months": len(usable), "window": [usable[0], usable[-1]],
            "n_rows": int(p.size), "n_stock_month": int(p_m.size),
            "rows_per_stock_month": round(p.size / float(p_m.size), 3),
            "cap_month": cap_month,
        },
        "day": {
            "c": c_d,
            "ci_iid": boot_iid(p, y, s),
            "ci_month": boot_month(p, y, s, month),
            "cv_row": cv_row(p, y, s),
            "cv_month": cv_month(p, y, s, month),
        },
        "month": {
            "c": c_m,
            "ci_iid": boot_iid(p_m, y_m, s_m, seed=SEED + 1),
            "ci_month": boot_month(p_m, y_m, s_m, months_m, seed=SEED + 1),
            "cv_row": cv_row(p_m, y_m, s_m),
            "cv_month": cv_month(p_m, y_m, s_m, months_m),
        },
        "delta_pct": {
            "c_month_vs_day": round((c_m / c_d - 1.0) * 100.0, 3),
            "cv_row_vs_month": None,
        },
    }
    out["delta_pct"]["cv_row_vs_month"] = (
        round((out["month"]["cv_row"] / out["month"]["cv_month"] - 1.0) * 100.0, 3)
        if out["month"]["cv_month"] else None)

    text = json.dumps(out, ensure_ascii=False, indent=2, default=str)
    print(text)
    path = os.path.join(os.environ.get("TEMP", "."), "p010_granularity.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("WROTE", path)


if __name__ == "__main__":
    main()
