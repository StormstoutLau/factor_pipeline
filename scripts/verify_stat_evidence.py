# -*- coding: utf-8 -*-
"""统计证据链独立验证（v3.7.0 E7）。

四段自检（不依赖 Stata）：
  dsr       DSR 与独立直算一致 + Monte Carlo 单调/尺寸校准
  pbo       CSCV PBO 纯噪声居中、真技能低于噪声
  curve     联合推断零效应不误报、强效应被检出
  leakage   PurgedKFold / CombinatorialPurgedKFold 边界泄漏探针

用法:
  python scripts/verify_stat_evidence.py --section all --n-sim 200
  python scripts/verify_stat_evidence.py --section dsr --n-sim 500

输出:
  out/stat_evidence_verification.json（可用 --out 覆盖）
退出码: 全部 PASS → 0；任一 FAIL → 1。
"""
import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
from scipy import stats

from factor_pipeline.backtest.cross_validation import (
    CombinatorialPurgedKFold,
    PurgedKFold,
)
from factor_pipeline.backtest.overfitting import (
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
)
from factor_pipeline.backtest.specification_logger import joint_inference

GAMMA = 0.5772156649


def _dsr_reference(returns, n_trials):
    arr = np.asarray(returns, dtype=float)
    t = arr.size
    sr = arr.mean() / arr.std(ddof=1)
    skew = stats.skew(arr, bias=False)
    kurt = stats.kurtosis(arr, fisher=False, bias=False)
    sr0 = math.sqrt(1.0 / (t - 1)) * (
        (1 - GAMMA) * stats.norm.ppf(1 - 1.0 / n_trials)
        + GAMMA * stats.norm.ppf(1 - 1.0 / (n_trials * math.e)))
    denominator = math.sqrt(1 - skew * sr + ((kurt - 1) / 4.0) * sr ** 2)
    return float(stats.norm.cdf((sr - sr0) * math.sqrt(t - 1) / denominator))


def _section_dsr(n_sim, seed):
    rng = np.random.default_rng(seed)
    sample = rng.normal(0.02, 0.05, 58)
    out = deflated_sharpe_ratio(sample, 10)
    reference = _dsr_reference(sample, 10)
    analytic_diff = abs(out["dsr"] - reference)

    null_by_n = {2: [], 10: [], 100: []}
    for _ in range(n_sim):
        series = rng.normal(0.0, 0.05, 58)
        for n_trials in null_by_n:
            null_by_n[n_trials].append(
                deflated_sharpe_ratio(series, n_trials)["dsr"])
    means = {k: float(np.mean(v)) for k, v in null_by_n.items()}
    false_positive = float(np.mean(np.asarray(null_by_n[10]) >= 0.95))
    checks = [
        {
            "name": "dsr_analytic",
            "value": analytic_diff,
            "threshold": 1e-12,
            "passed": analytic_diff <= 1e-12,
        },
        {
            "name": "dsr_monotonic_in_n_trials",
            "value": means,
            "passed": means[2] >= means[10] >= means[100],
        },
        {
            "name": "dsr_null_false_positive_rate",
            "value": false_positive,
            "threshold": 0.15,
            "passed": false_positive <= 0.15,
        },
    ]
    return _wrap("dsr", checks)


def _section_pbo(n_sim, seed):
    rng = np.random.default_rng(seed)
    noise_pbo = []
    skill_pbo = []
    for _ in range(max(50, n_sim // 4)):
        noise = rng.normal(size=(56, 10))
        skilled = noise.copy()
        skilled[:, 0] += 0.8
        noise_pbo.append(
            probability_of_backtest_overfitting(noise, n_blocks=8)["pbo"])
        skill_pbo.append(
            probability_of_backtest_overfitting(skilled, n_blocks=8)["pbo"])
    noise_mean = float(np.mean(noise_pbo))
    skill_mean = float(np.mean(skill_pbo))
    checks = [
        {
            "name": "pbo_noise_centered",
            "value": noise_mean,
            "range": [0.3, 0.7],
            "passed": 0.3 <= noise_mean <= 0.7,
        },
        {
            "name": "pbo_skill_below_noise",
            "value": {"noise": noise_mean, "skill": skill_mean},
            "passed": skill_mean < noise_mean,
        },
    ]
    return _wrap("pbo", checks)


def _section_curve(n_sim, seed):
    rng = np.random.default_rng(seed)
    n_bootstrap = max(200, min(1000, n_sim * 2))
    noise = rng.normal(0.0, 0.05, size=(58, 8))
    null_out = joint_inference(
        noise, effect="mean", n_bootstrap=n_bootstrap, seed=seed)
    null_p = {s["name"]: s["p_value"] for s in null_out["statistics"]}

    effect = rng.normal(0.0, 0.05, size=(58, 8)) + 0.06
    strong_out = joint_inference(
        effect, effect="mean", n_bootstrap=n_bootstrap, seed=seed)
    strong = {s["name"]: s["p_value"] for s in strong_out["statistics"]}

    checks = [
        {
            "name": "joint_inference_null_no_false_positive",
            "value": null_p,
            "passed": all(p > 0.05 for p in null_p.values()),
        },
        {
            "name": "joint_inference_strong_effect_detected",
            "value": strong,
            "passed": (strong["median"] < 0.05
                       and strong["aggregated_z"] < 0.05),
        },
    ]
    return _wrap("curve", checks)


def _section_leakage(n_sim, seed):
    n = 58
    leaks = 0
    checked = 0

    cv = PurgedKFold(n_splits=5, purge=1, embargo=1, label_horizon=1)
    for train, test in cv.split(n):
        checked += 1
        leaks += int(len(np.intersect1d(train, test)))
        for a, b in _segments(test):
            if a > 0 and (a - 1) in train:
                leaks += 1
            if b + 1 < n and (b + 1) in train:
                leaks += 1

    cpcv = CombinatorialPurgedKFold(
        n_groups=6, n_test_groups=2, purge=1, embargo=1, label_horizon=1)
    for train, test, _ in cpcv.split(n):
        checked += 1
        leaks += int(len(np.intersect1d(train, test)))
        for a, b in _segments(test):
            if a > 0 and (a - 1) in train:
                leaks += 1
            if b + 1 < n and (b + 1) in train:
                leaks += 1

    checks = [{
        "name": "purge_embargo_boundary",
        "value": {"splits_checked": checked, "leaks": leaks},
        "passed": leaks == 0,
    }]
    return _wrap("leakage", checks)


def _segments(idx):
    if len(idx) == 0:
        return []
    out = []
    start = prev = int(idx[0])
    for value in idx[1:]:
        cur = int(value)
        if cur == prev + 1:
            prev = cur
            continue
        out.append((start, prev))
        start = prev = cur
    out.append((start, prev))
    return out


def _wrap(name, checks):
    passed = all(item["passed"] for item in checks)
    return {
        "section": name,
        "status": "PASS" if passed else "FAIL",
        "checks": checks,
    }


_SECTIONS = {
    "dsr": _section_dsr,
    "pbo": _section_pbo,
    "curve": _section_curve,
    "leakage": _section_leakage,
}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="v3.7.0 统计证据链独立验证")
    parser.add_argument(
        "--section", default="all",
        choices=("all",) + tuple(_SECTIONS),
        help="验证段（默认 all）")
    parser.add_argument(
        "--n-sim", type=int, default=200, help="Monte Carlo 重复次数")
    parser.add_argument(
        "--seed", type=int, default=20261118, help="随机种子")
    parser.add_argument(
        "--out", default="out/stat_evidence_verification.json",
        help="结果 JSON 路径")
    parser.add_argument(
        "--report-json", default=None,
        help="v3.9.0 统一验证报告路径（默认关闭）")
    args = parser.parse_args(argv)

    if args.n_sim < 10:
        parser.error("--n-sim 必须 >= 10")

    selected = (list(_SECTIONS) if args.section == "all"
                else [args.section])
    results = [_SECTIONS[name](args.n_sim, args.seed) for name in selected]
    report = {
        "generated_at": datetime.now().isoformat(),
        "n_sim": args.n_sim,
        "seed": args.seed,
        "sections": results,
        "status": ("PASS" if all(r["status"] == "PASS" for r in results)
                   else "FAIL"),
    }

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = Path(__file__).resolve().parent.parent / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for item in results:
        print("[%s] %s" % (item["status"], item["section"]))
        for check in item["checks"]:
            print("  - %-42s %s"
                  % (check["name"], "ok" if check["passed"] else "FAIL"))
    print("report: %s" % out_path)

    if args.report_json:
        checks = []
        for section in results:
            for check in section["checks"]:
                checks.append({"id": "%s:%s" % (section["section"], check["name"]),
                               "ok": bool(check["passed"])})
        payload = {
            "tool": "verify_stat_evidence",
            "generated_at": datetime.now().isoformat(),
            "checks": checks,
            "artifacts": [{"path": str(out_path)}],
            "status": ("pass" if report["status"] == "PASS" else "fail"),
        }
        report_path = Path(args.report_json)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print("report-json -> %s" % report_path)

    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
