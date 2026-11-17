# -*- coding: utf-8 -*-
"""E5: Python ↔ Stata 18 计量对拍 (v3.6.0).

设计依据：``docs/private/DESIGN_GOVERNANCE_BASE.md`` §8；
实施依据：``docs/EXECUTION_V3.6.0_GOVERNANCE_BASE.md`` §2.7。

原则（DESIGN §8.1）：
1. 确定性 fixture 重放：Python 导出输入与 bootstrap 索引，Stata 只做确定性计算；
2. 不对齐 RNG；
3. 只用 Stata 内置命令（import delimited / Mata / newey）；
4. rwolf2/multproc 为可选第二参照；
5. 独立于 pytest；Stata 缺失或 --skip-stata 时 SKIP（退出码 0）。

用法::

    python benchmarks/stata_econ_crosscheck.py --case all
    python benchmarks/stata_econ_crosscheck.py --case romano_wolf --stata "...StataMP-64.exe"
    python benchmarks/stata_econ_crosscheck.py --skip-stata --mc
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from factor_pipeline.backtest.multiple_testing import (  # noqa: E402
    HansenSPA,
    WhiteRealityCheck,
    apply_bh_fdr,
    apply_bonferroni,
    apply_by_fdr,
    apply_romano_wolf,
)
from factor_pipeline.backtest.multiple_testing_ledger import (  # noqa: E402
    _holm_adjusted,
)

DEFAULT_STATA = r"C:\Program Files\Stata18\StataMP-64.exe"
CASES = (
    "bh", "by", "bonferroni", "holm",
    "romano_wolf", "white_rc", "hansen_spa",
    "hac", "dsr", "pbo",
)
P1_CASES = ("dsr", "pbo")
TOLERANCE = {
    "bh": 1e-10,
    "by": 1e-10,
    "bonferroni": 1e-12,
    "holm": 1e-12,
    "romano_wolf": 1e-10,
    "white_rc": 1e-10,
    "hansen_spa": 1e-10,
}
M_SIZES = (20, 200, 2000)
ALPHA = 0.05


# ============================================================
# Fixtures
# ============================================================

def build_fixtures(work: Path, n_bootstrap: int, seed: int) -> dict:
    """生成确定性 fixture（CSV）并返回内存副本。"""
    rng = np.random.default_rng(seed)
    fixtures = {"p": {}}
    for m in M_SIZES:
        p = rng.random(m)
        fixtures["p"][m] = p
        pd.DataFrame({"i": np.arange(1, m + 1), "p": p}).to_csv(
            work / ("p_%d.csv" % m), index=False)

    p_rw = rng.random(20)
    boot_rw = rng.random((n_bootstrap, 20))
    fixtures["rw"] = (p_rw, boot_rw)
    pd.DataFrame({"i": np.arange(1, 21), "p": p_rw}).to_csv(
        work / "rw_p.csv", index=False)
    pd.DataFrame(
        boot_rw, columns=["b%d" % (i + 1) for i in range(20)],
    ).to_csv(work / "rw_boot.csv", index=False)

    T, K = 240, 10
    bench = rng.normal(0.0, 0.05, size=T)
    strat = rng.normal(0.0, 0.05, size=(T, K))
    strat[:, 0] += 0.012
    excess = strat - bench[:, None]
    indices = rng.integers(0, T, size=(n_bootstrap, T))
    fixtures["white"] = (np.column_stack([bench, strat]), indices, excess)
    pd.DataFrame(
        excess, columns=["e%d" % (k + 1) for k in range(K)],
    ).to_csv(work / "excess.csv", index=False)
    pd.DataFrame(
        indices, columns=["t%d" % (t + 1) for t in range(T)],
    ).to_csv(work / "boot_idx.csv", index=False)
    return fixtures


def fixture_hash(work: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(work.glob("*.csv")):
        digest.update(path.name.encode("ascii"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


# ============================================================
# Python 侧
# ============================================================

def compute_python(fixtures: dict, n_bootstrap: int) -> dict:
    values = {}
    for m in M_SIZES:
        p = fixtures["p"][m]
        values[("bh", m)] = apply_bh_fdr(p.tolist(), ALPHA)[0]
        values[("by", m)] = apply_by_fdr(p.tolist(), ALPHA)[0]
        values[("bonferroni", m)] = apply_bonferroni(p.tolist(), ALPHA)[0]
        values[("holm", m)] = _holm_adjusted(p.tolist())

    p_rw, boot_rw = fixtures["rw"]
    values["romano_wolf"] = apply_romano_wolf(
        p_rw.tolist(), boot_rw, ALPHA, 1, "stepdown")[0]

    returns, indices, _excess = fixtures["white"]
    values["white_rc"] = WhiteRealityCheck(
        n_bootstrap=n_bootstrap).test(
            returns, benchmark_index=0, alpha=ALPHA,
            bootstrap_indices=indices,
        )["rc_p_value"]
    spa = HansenSPA(n_bootstrap=n_bootstrap).test(
        returns, benchmark_index=0, alpha=ALPHA,
        bootstrap_indices=indices,
    )
    values["hansen_spa"] = (
        spa["spa_p_value"], spa["spa_lc_p_value"], spa["spa_uc_p_value"],
    )
    return values


# ============================================================
# Stata .do 生成
# ============================================================

_MATA_HELPERS = r"""
mata:
void mtest_write(real scalar m, real colvector p) {
    real scalar j, hm, run, fh
    real vector idx, q
    real colvector sp, q_bh, q_by, q_bonf, q_holm

    idx = order(p, 1)
    sp = p[idx]
    hm = sum(1 :/ (1::m))

    q_bh = sp :* m :/ (1::m)
    q_by = q_bh :* hm
    q_bonf = sp :* m
    q_holm = J(m, 1, .)
    run = 0
    for (j=1; j<=m; j++) {
        q_holm[j] = max((run, min(((m-j+1)*sp[j], 1))))
        run = q_holm[j]
    }
    for (j=m-1; j>=1; j--) {
        q_bh[j] = min((q_bh[j], q_bh[j+1]))
        q_by[j] = min((q_by[j], q_by[j+1]))
    }
    for (j=1; j<=m; j++) {
        q_bh[j] = min((q_bh[j], 1))
        q_by[j] = min((q_by[j], 1))
        q_bonf[j] = min((q_bonf[j], 1))
    }

    fh = fopen("out_bh.csv", "a")
    for (j=1; j<=m; j++) fput(fh, sprintf("%9.0f,%9.0f,%21.17f,%21.17f", m, idx[j], p[idx[j]], q_bh[j]))
    fclose(fh)
    fh = fopen("out_by.csv", "a")
    for (j=1; j<=m; j++) fput(fh, sprintf("%9.0f,%9.0f,%21.17f,%21.17f", m, idx[j], p[idx[j]], q_by[j]))
    fclose(fh)
    fh = fopen("out_bonferroni.csv", "a")
    for (j=1; j<=m; j++) fput(fh, sprintf("%9.0f,%9.0f,%21.17f,%21.17f", m, idx[j], p[idx[j]], q_bonf[j]))
    fclose(fh)
    fh = fopen("out_holm.csv", "a")
    for (j=1; j<=m; j++) fput(fh, sprintf("%9.0f,%9.0f,%21.17f,%21.17f", m, idx[j], p[idx[j]], q_holm[j]))
    fclose(fh)
}

void rw_write(real colvector p, real matrix BOOT) {
    real scalar m, nb, b, j, fh
    real vector idx
    real colvector sp, q, kth
    real matrix S

    m = rows(p)
    nb = rows(BOOT)
    idx = order(p, 1)
    sp = p[idx]
    S = J(nb, m, .)
    for (b=1; b<=nb; b++) S[b, 1::m] = sort(BOOT[b, 1::m]', 1)'
    q = J(m, 1, .)
    for (j=1; j<=m; j++) {
        kth = J(nb, 1, .)
        for (b=1; b<=nb; b++) kth[b] = S[b, 1]
        q[j] = mean(kth :<= sp[j])
        if (j > 1) q[j] = max((q[j], q[j-1]))
    }
    fh = fopen("out_rw.csv", "a")
    for (j=1; j<=m; j++) fput(fh, sprintf("%9.0f,%21.17f", idx[j], q[j]))
    fclose(fh)
}

void white_write(real matrix X, real matrix IDX) {
    real scalar T, K, nb, b, fh
    real rowvector fbar, fb, delta
    real colvector stats
    real scalar V, p

    T = rows(X)
    K = cols(X)
    nb = rows(IDX)
    fbar = colsum(X) :/ T
    V = sqrt(T) * max(fbar)
    stats = J(nb, 1, .)
    for (b=1; b<=nb; b++) {
        fb = colsum(X[IDX[b, 1::T]', .]) :/ T
        delta = fb - fbar
        stats[b] = sqrt(T) * max(delta)
    }
    p = mean(stats :>= V)
    fh = fopen("out_white.csv", "w")
    fput(fh, sprintf("%21.17f,%21.17f", p, V))
    fclose(fh)
}

void hansen_write(real matrix X, real matrix IDX) {
    real scalar T, K, nb, b, k, l, L, fh, j
    real rowvector fbar, fb, delta, omega, sd, thr
    real colvector g, g_lc, h1
    real colvector stats, stats_lc, stats_o, stats_o_lc
    real scalar V, V_o, p, p_lc, p_uc, p_o, p_o_lc
    real colvector x, xc
    real scalar g0, om, gl

    T = rows(X)
    K = cols(X)
    nb = rows(IDX)
    fbar = colsum(X) :/ T
    omega = J(1, K, .)
    for (k=1; k<=K; k++) {
        x = X[., k]
        xc = x :- mean(x)
        g0 = sum(xc:^2) / (T - 1)
        L = max((1, floor(4 * (T/100)^(2/9))))
        L = min((L, T - 1))
        om = g0
        for (l=1; l<=L; l++) {
            gl = mean(xc[(l+1)..T] :* xc[1..(T-l)])
            om = om + 2 * (1 - l/(L+1)) * gl
        }
        omega[k] = max((om, 1e-10))
    }
    thr = sqrt(omega :/ T) :* sqrt(2 * log(log(T)))
    h1 = selectindex(fbar :> -thr)
    if (cols(h1) > 0) {
        V = sqrt(T) * max(fbar[h1])
        sd = sqrt(omega)
        V_o = sqrt(T) * max(fbar[h1] :/ sd[h1])
    }
    else {
        V = 0
        sd = sqrt(omega)
        V_o = 0
    }
    stats = J(nb, 1, .)
    stats_lc = J(nb, 1, .)
    stats_o = J(nb, 1, .)
    stats_o_lc = J(nb, 1, .)
    for (b=1; b<=nb; b++) {
        fb = colsum(X[IDX[b, 1::T]', .]) :/ T
        delta = fb - fbar
        if (cols(h1) > 0) {
            stats[b] = sqrt(T) * max(delta[h1])
            stats_o[b] = sqrt(T) * max(delta[h1] :/ sd[h1])
        }
        else {
            stats[b] = 0
            stats_o[b] = 0
        }
        stats_lc[b] = sqrt(T) * max(delta)
        stats_o_lc[b] = sqrt(T) * max(delta :/ sd)
    }
    p = mean(stats :>= V)
    p_lc = mean(stats_lc :>= V)
    p_uc = (V <= 0)
    p_o = mean(stats_o :>= V_o)
    p_o_lc = mean(stats_o_lc :>= V_o)
    p = max((p_uc, p))
    p = min((p_lc, p))
    p_lc = max((p_lc, p))
    p_uc = min((p_uc, p))
    fh = fopen("out_hansen.csv", "w")
    fput(fh, sprintf("%21.17f,%21.17f,%21.17f,%21.17f,%21.17f", p, p_lc, p_uc, p_o, p_o_lc))
    fclose(fh)
}
end
"""


def build_do(cases) -> str:
    lines = ["clear all", "set more off", "capture log close", "",
             _MATA_HELPERS, ""]
    needs_mtest = any(c in cases for c in ("bh", "by", "bonferroni", "holm"))
    needs_rw = "romano_wolf" in cases
    needs_white = any(c in cases for c in ("white_rc", "hansen_spa"))

    if needs_mtest:
        for name in ("bh", "by", "bonferroni", "holm"):
            lines += ['capture erase out_%s.csv' % name,
                      'file open fh using "out_%s.csv", write text' % name,
                      'file write fh "m,i,p,q" _n',
                      "file close fh"]
        for m in M_SIZES:
            lines += [
                'import delimited "p_%d.csv", clear stringcols(_all)' % m,
                "destring _all, replace",
                "ds",
                "local vars `r(varlist)'",
                "putmata P=(p), replace",
                "mata: mtest_write(%d, P)" % m,
                "",
            ]
    if needs_rw:
        lines += [
            'capture erase out_rw.csv',
            'file open fh using "out_rw.csv", write text',
            'file write fh "i,q" _n',
            "file close fh",
            'import delimited "rw_p.csv", clear stringcols(_all)',
            "destring _all, replace",
            "putmata P=(p), replace",
            'import delimited "rw_boot.csv", clear stringcols(_all)',
            "destring _all, replace",
            "ds",
            "local vars `r(varlist)'",
            "putmata BOOT=(`vars'), replace",
            "mata: rw_write(P, BOOT)",
            "",
        ]
    if needs_white:
        lines += [
            'import delimited "excess.csv", clear stringcols(_all)',
            "destring _all, replace",
            "ds",
            "local vars `r(varlist)'",
            "putmata X=(`vars'), replace",
            'import delimited "boot_idx.csv", clear stringcols(_all)',
            "destring _all, replace",
            "ds",
            "local vars `r(varlist)'",
            "putmata IDX=(`vars'), replace",
            "mata: IDX = trunc(IDX) :+ 1",
        ]
        if "white_rc" in cases:
            lines.append("mata: white_write(X, IDX)")
        if "hansen_spa" in cases:
            lines.append("mata: hansen_write(X, IDX)")
        lines.append("")
    return "\n".join(lines)


# ============================================================
# 执行与比较
# ============================================================

def run_stata(exe: str, work: Path, do_name: str):
    proc = subprocess.run(
        [exe, "/e", "do", do_name], cwd=str(work),
        timeout=600, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    log_path = work / (do_name[:-3] + ".log")
    log = log_path.read_text(errors="replace") if log_path.exists() else ""
    if proc.returncode != 0 or re.search(r"^r\(\d+\);", log, re.M):
        tail = "\n".join(log.splitlines()[-30:])
        raise RuntimeError(
            "Stata batch failed (exit=%s)\n%s" % (proc.returncode, tail))
    return log


def stata_version(log: str) -> str:
    match = re.search(r"\b(\d{1,2}\.\d+)\s*$", log, re.M)
    return match.group(1) if match else "unknown"


def _read(work: Path, name: str, header="infer") -> pd.DataFrame:
    return pd.read_csv(work / name, header=header)


def compare_mtest(work: Path, values: dict, cases) -> list:
    rows = []
    mapping = {
        "bh": "out_bh.csv", "by": "out_by.csv",
        "bonferroni": "out_bonferroni.csv", "holm": "out_holm.csv",
    }
    for case, filename in mapping.items():
        if case not in cases:
            continue
        frame = _read(work, filename)
        worst = 0.0
        mismatched = 0
        for m in M_SIZES:
            sub = frame[frame["m"] == m].sort_values("i")
            py = np.asarray(values[(case, m)], dtype=float)
            st = sub["q"].to_numpy(dtype=float)
            if st.shape != py.shape:
                mismatched += abs(st.shape[0] - py.shape[0])
                continue
            diff = float(np.max(np.abs(st - py))) if py.size else 0.0
            worst = max(worst, diff)
            if case == "bh":
                py_rej = np.asarray(apply_bh_fdr(
                    sub["p"].to_numpy(dtype=float).tolist(), ALPHA)[1])
                st_rej = sub["q"].to_numpy(dtype=float) < ALPHA
                mismatched += int(np.sum(py_rej != st_rej))
        tol = TOLERANCE[case]
        verdict = "PASS" if worst <= tol and mismatched == 0 else "FAIL"
        rows.append({
            "case": case, "python": "max|q_py-q_stata|",
            "stata": "m=20/200/2000", "diff": worst,
            "tolerance": tol, "reject_mismatch": mismatched,
            "verdict": verdict,
        })
    return rows


def compare_rw(work: Path, values: dict) -> list:
    frame = _read(work, "out_rw.csv").sort_values("i")
    py = np.asarray(values["romano_wolf"], dtype=float)
    st = frame["q"].to_numpy(dtype=float)
    diff = float(np.max(np.abs(st - py))) if py.size == st.size else float("inf")
    return [{
        "case": "romano_wolf", "python": "max|q_py-q_stata|",
        "stata": "stepdown k=1", "diff": diff,
        "tolerance": TOLERANCE["romano_wolf"],
        "verdict": "PASS" if diff <= TOLERANCE["romano_wolf"] else "FAIL",
    }]


def compare_white(work: Path, values: dict) -> list:
    frame = _read(work, "out_white.csv", header=None)
    st = float(frame.iloc[0, 0])
    py = float(values["white_rc"])
    diff = abs(st - py)
    return [{
        "case": "white_rc", "python": py, "stata": st, "diff": diff,
        "tolerance": TOLERANCE["white_rc"],
        "verdict": "PASS" if diff <= TOLERANCE["white_rc"] else "FAIL",
    }]


def compare_hansen(work: Path, values: dict) -> list:
    frame = _read(work, "out_hansen.csv", header=None)
    cols = list(frame.columns)
    st_consistent = float(frame[cols[0]].iloc[0])
    st_lc = float(frame[cols[1]].iloc[0])
    st_uc = float(frame[cols[2]].iloc[0])
    st_original = float(frame[cols[3]].iloc[0])
    py_consistent, py_lc, py_uc = values["hansen_spa"]
    diff = max(
        abs(st_consistent - py_consistent),
        abs(st_lc - py_lc),
        abs(st_uc - py_uc),
    )
    return [{
        "case": "hansen_spa",
        "python": [py_consistent, py_lc, py_uc],
        "stata": [st_consistent, st_lc, st_uc],
        "diff": diff,
        "tolerance": TOLERANCE["hansen_spa"],
        "original_caliber_p": st_original,
        "original_caliber_diff": abs(st_original - py_consistent),
        "verdict": "PASS" if diff <= TOLERANCE["hansen_spa"] else "FAIL",
    }]


def run_hac(exe: str, skip_stata: bool) -> list:
    script = ROOT / "scripts" / "verify_hac_stata.py"
    cmd = [sys.executable, str(script)]
    if skip_stata:
        cmd.append("--skip-stata")
    else:
        cmd += ["--stata", exe]
    proc = subprocess.run(
        cmd, cwd=str(ROOT), timeout=900,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    tail = "\n".join((proc.stdout or "").splitlines()[-8:])
    convention_diff = "[DIFF]" in (proc.stdout or "")
    if skip_stata:
        verdict = "SKIP"
    elif proc.returncode != 0:
        verdict = "FAIL"
    elif convention_diff:
        verdict = "PASS（既有脚本；L3 约定差）"
    else:
        verdict = "PASS（既有脚本）"
    return [{
        "case": "hac", "python": "scripts/verify_hac_stata.py",
        "stata": "newey (既有脚本)", "diff": None,
        "tolerance": "EXACT/约定差", "verdict": verdict,
        "convention_diff": convention_diff,
        "detail": tail,
    }]


def run_mc(n_bootstrap: int, reps: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    rw_reject = 0
    white_reject = 0
    spa_reject = 0
    for _ in range(reps):
        p = rng.random(20)
        boot = rng.random((n_bootstrap, 20))
        adj, rejected = apply_romano_wolf(p.tolist(), boot, ALPHA, 1, "stepdown")
        rw_reject += int(np.sum(rejected) > 0)

        T, K = 240, 10
        returns = rng.normal(size=(T, K + 1))
        indices = rng.integers(0, T, size=(n_bootstrap, T))
        white = WhiteRealityCheck(n_bootstrap=n_bootstrap).test(
            returns, 0, ALPHA, bootstrap_indices=indices)
        white_reject += int(white["rc_p_value"] < ALPHA)
        spa = HansenSPA(n_bootstrap=n_bootstrap).test(
            returns, 0, ALPHA, bootstrap_indices=indices)
        spa_reject += int(spa["spa_p_value"] < ALPHA)

    return {
        "reps": reps,
        "bootstrap": n_bootstrap,
        "rw_size": rw_reject / reps,
        "white_size": white_reject / reps,
        "spa_size": spa_reject / reps,
        "note": "轻量自检（非 U1 验收；U1 需 1000 reps）",
    }


# ============================================================
# 主流程
# ============================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="Python vs Stata 18 计量对拍")
    parser.add_argument("--case", default="all",
                        choices=("all",) + CASES)
    parser.add_argument("--stata", default=DEFAULT_STATA)
    parser.add_argument("--skip-stata", action="store_true")
    parser.add_argument("--mc", action="store_true")
    parser.add_argument("--mc-reps", type=int, default=200)
    parser.add_argument("--B", type=int, default=500)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--out", default=str(ROOT / "out" / "stata_econ_crosscheck.json"))
    args = parser.parse_args()

    cases = CASES if args.case == "all" else (args.case,)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    stata_available = Path(args.stata).exists() and not args.skip_stata
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "SKIP" if not stata_available else "STATA",
        "stata_path": args.stata,
        "stata_version": None,
        "fixture_hash": None,
        "cases": [],
        "mc": None,
    }

    with tempfile.TemporaryDirectory(prefix="stata_econ_") as work_dir:
        work = Path(work_dir)
        fixtures = build_fixtures(work, args.B, args.seed)
        report["fixture_hash"] = fixture_hash(work)
        values = compute_python(fixtures, args.B)

        rows = []
        if stata_available:
            do_name = "crosscheck.do"
            (work / do_name).write_text(
                build_do(cases), encoding="ascii", newline="\n")
            log = run_stata(args.stata, work, do_name)
            report["stata_version"] = stata_version(log)
            if any(c in cases for c in ("bh", "by", "bonferroni", "holm")):
                rows.extend(compare_mtest(work, values, cases))
            if "romano_wolf" in cases:
                rows.extend(compare_rw(work, values))
            if "white_rc" in cases:
                rows.extend(compare_white(work, values))
            if "hansen_spa" in cases:
                rows.extend(compare_hansen(work, values))
            if "hac" in cases:
                rows.extend(run_hac(args.stata, skip_stata=False))
        else:
            reason = "--skip-stata" if args.skip_stata else "Stata executable not found"
            for case in cases:
                if case in P1_CASES or case == "hac":
                    continue
                rows.append({
                    "case": case, "python": "-", "stata": "-",
                    "diff": None, "tolerance": TOLERANCE.get(case),
                    "verdict": "SKIP", "detail": reason,
                })
            if "hac" in cases:
                rows.extend(run_hac(args.stata, skip_stata=True))

        for case in P1_CASES:
            if case in cases:
                rows.append({
                    "case": case, "python": "-", "stata": "-",
                    "diff": None, "tolerance": None,
                    "verdict": "SKIP", "detail": "P1 未实装（DESIGN §8.2）",
                })
        report["cases"] = rows

        if args.mc:
            report["mc"] = run_mc(args.B, args.mc_reps, args.seed)

    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("| Case | Python | Stata | diff | verdict |")
    print("|------|--------|-------|------|---------|")
    for row in report["cases"]:
        diff = "-" if row["diff"] is None else "%.3e" % row["diff"]
        print("| %s | %s | %s | %s | %s |" % (
            row["case"], row["python"], row["stata"], diff, row["verdict"]))
    print("\nJSON: %s" % out_path)

    return 1 if any(row["verdict"] == "FAIL" for row in report["cases"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
