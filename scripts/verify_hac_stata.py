# -*- coding: utf-8 -*-
"""HAC 标准误独立验证 — Python vs Stata 18 newey (v3.4.12 复审)

三层精确对拍 + 一层 Monte Carlo:
  L1  premium_mean / premium_mean_se  ↔  newey beta, lag(q) 的 _b/_se[_cons]
  L2  beta_se                         ↔  statsby by(t): regress r f 的 _se[f]
  L3  Omega_t (lambda_se 的成分)      ↔  newey u, lag(q_local), Omega = SE² × n
  L4  lambda_se 复合近似 √(Ω·Σw²)     ↔  Monte Carlo (经验 sd vs 平均 SE, --mc)

用法:
  python scripts/verify_hac_stata.py                 # L1-L3 (需本机 Stata 18)
  python scripts/verify_hac_stata.py --skip-stata --mc   # 仅 L4 Monte Carlo
  python scripts/verify_hac_stata.py --stata <exe>   # 指定 Stata 可执行文件

口径说明: Stata newey 不自动选阶, 滞后阶数由 Python 侧显式传入
(q = max(1, int(4*(n/100)^(2/9))), Newey-West 1994 形式), 保证两侧同带宽.
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pandas as pd

from factor_pipeline.modules.factor_health import PremiumEstimator

DEFAULT_STATA = r"C:\Program Files\Stata18\StataMP-64.exe"
CASES = (10, 60, 100, 140, 190)


def build_panel(seed=42, T=200, N=50, premium=0.02, noise=0.05):
    """与 tests/unit 夹具同族的稳定溢价面板 (无缺失, 主路径)."""
    rng = np.random.RandomState(seed)
    idx = pd.date_range('2020-01-01', periods=T, freq='ME')
    cols = ['S%02d' % i for i in range(N)]
    F = pd.DataFrame(rng.randn(T, N), index=idx, columns=cols)
    R = pd.DataFrame(premium * F.values + rng.randn(T, N) * noise,
                     index=idx, columns=cols)
    return F, R


def export_fixtures(work: Path, F, R, est, res):
    """导出 L1-L3 的对拍夹具 (CSV) 并记录 Python 侧期望值."""
    T = len(F)
    valid = np.isfinite(res['beta_t'])
    beta_valid = res['beta_t'][valid]
    qg = int(res['hac_lag'])
    pd.DataFrame({'t': np.arange(1, len(beta_valid) + 1),
                  'beta': beta_valid}).to_csv(work / 'beta.csv', index=False)

    rows = []
    for t in range(T):
        f = F.values[t]
        r = R.values[t]
        m = np.isfinite(f) & np.isfinite(r)
        for fi, ri in zip(f[m], r[m]):
            rows.append((t + 1, fi, ri))
    pd.DataFrame(rows, columns=['t', 'f', 'r']).to_csv(
        work / 'panel_long.csv', index=False)

    meta = []
    for t0 in CASES:
        h = est.bandwidth
        lo, hi = max(0, t0 - h), min(T, t0 + h + 1)
        bw = res['beta_t'][lo:hi]
        lw = res['lambda_hat'][lo:hi]
        m = np.isfinite(bw) & np.isfinite(lw)
        resid = bw[m] - lw[m]
        n_win = int(m.sum())
        q_local = max(1, int(4 * (n_win / 100) ** (2 / 9)))
        omega = est._hac_long_run_variance(resid, q_local)
        pd.DataFrame({'s': np.arange(1, n_win + 1), 'u': resid}).to_csv(
            work / ('w%d.csv' % t0), index=False)
        meta.append({'case': 'w%d' % t0, 't': t0, 'n': n_win, 'q': q_local,
                     'omega_python': float(omega)})
    return {'q_global': qg, 'cases': meta}


def write_do(work: Path, fx):
    qg = fx['q_global']
    lines = ['version 18', 'set more off', '',
             '* L1: premium mean HAC SE',
             'import delimited "beta.csv", clear',
             'tsset t',
             'newey beta, lag(%d)' % qg,
             'gen double mean_est = _b[_cons]',
             'gen double mean_se = _se[_cons]',
             'keep mean_est mean_se',
             'duplicates drop',
             'export delimited "out_mean.csv", replace',
             '',
             '* L2: per-period cross-sectional OLS SE',
             'import delimited "panel_long.csv", clear',
             'statsby b=_b[f] se=_se[f], by(t) clear: regress r f',
             'export delimited "out_beta_se.csv", replace',
             '',
             '* L3: Omega_t from window residuals']
    for c in fx['cases']:
        lines += [
            'import delimited "%s.csv", clear' % c['case'],
            'tsset s',
            'newey u, lag(%d)' % c['q'],
            'gen double omega_hat = _se[_cons]^2 * %d' % c['n'],
            'gen str8 case = "%s"' % c['case'],
            'keep omega_hat case',
            'duplicates drop',
            'export delimited "out_%s.csv", replace' % c['case'],
            '']
    (work / 'verify_hac.do').write_text('\n'.join(lines), encoding='ascii')


def run_stata(exe: str, work: Path):
    proc = subprocess.run([exe, '/e', 'do', 'verify_hac.do'], cwd=str(work),
                          timeout=600, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    log_path = work / 'verify_hac.log'
    log = log_path.read_text(errors='replace') if log_path.exists() else ''
    failed = proc.returncode != 0 or re.search(r'^r\(\d+\);', log, re.M)
    if failed:
        print('--- Stata log tail ---')
        print('\n'.join(log.splitlines()[-40:]))
        raise SystemExit('Stata batch failed (exit=%s)' % proc.returncode)


def _verdict(ratio):
    if ratio is None or not np.isfinite(ratio):
        return 'MISSING'
    d = abs(ratio - 1.0)
    if d < 1e-6:
        return 'EXACT'
    if d < 1e-3:
        return 'CLOSE(约定差?)'
    return 'DIFF'


def compare(work: Path, res, fx):
    print('=' * 78)
    print('L1  premium_mean / premium_mean_se  vs  newey intercept')
    print('=' * 78)
    out = pd.read_csv(work / 'out_mean.csv')
    mean_p, mean_s = res['premium_mean'], res['premium_mean_se']
    se_p = out['mean_se'].iloc[0]
    se_s = out['mean_est'].iloc[0]
    est_s = out['mean_est'].iloc[0]
    print('  mean  python=%.12g  stata=%.12g  ratio=%.10f  [%s]' % (
        mean_p, est_s, est_s / mean_p, _verdict(est_s / mean_p)))
    print('  SE    python=%.12g  stata=%.12g  ratio=%.10f  [%s]' % (
        mean_s, se_p, se_p / mean_s, _verdict(se_p / mean_s)))

    print('=' * 78)
    print('L2  beta_se (200 期)  vs  statsby regress _se[f]')
    print('=' * 78)
    out = pd.read_csv(work / 'out_beta_se.csv')
    out = out.sort_values('t')
    b_py = res['beta_t'][np.isfinite(res['beta_t'])]
    se_py = res['beta_se'][np.isfinite(res['beta_t'])]
    b_st = out['b'].values
    se_st = out['se'].values
    n = min(len(b_py), len(b_st))
    rb = np.max(np.abs(b_st[:n] / b_py[:n] - 1))
    rs = np.max(np.abs(se_st[:n] / se_py[:n] - 1))
    print('  max |ratio-1|  beta: %.3e  [%s]   se: %.3e  [%s]' % (
        rb, _verdict(1 + rb), rs, _verdict(1 + rs)))

    print('=' * 78)
    print('L3  Omega_t  vs  newey(u) SE^2 * n')
    print('=' * 78)
    for c in fx['cases']:
        out = pd.read_csv(work / ('out_%s.csv' % c['case']))
        om_st = float(out['omega_hat'].iloc[0])
        om_py = c['omega_python']
        ratio = om_st / om_py
        print('  %s (t=%3d, n=%2d, q=%d)  python=%.10g  stata=%.10g  ratio=%.10f  [%s]' % (
            c['case'], c['t'], c['n'], c['q'], om_py, om_st, ratio, _verdict(ratio)))


def run_mc(n_reps=400, T=200, N=50, seed=11):
    """L4: lambda_se 复合近似的有效性 — 经验波动 vs 平均 SE."""
    rng = np.random.RandomState(seed)
    est = PremiumEstimator(bandwidth=24)
    idx = pd.date_range('2020-01-01', periods=T, freq='ME')
    cols = ['S%02d' % i for i in range(N)]
    lam = np.full((n_reps, T), np.nan)
    lse = np.full((n_reps, T), np.nan)
    pm = np.full(n_reps, np.nan)
    pse = np.full(n_reps, np.nan)
    for m in range(n_reps):
        u = 0.0
        beta_true = np.empty(T)
        for t in range(T):
            u = 0.3 * u + 0.01 * rng.randn()  # AR(1) beta, rho=0.3
            beta_true[t] = 0.02 + u
        Fv = rng.randn(T, N)
        Rv = beta_true[:, None] * Fv + 0.05 * rng.randn(T, N)
        res = est.estimate_with_errors(
            pd.DataFrame(Fv, index=idx, columns=cols),
            pd.DataFrame(Rv, index=idx, columns=cols))
        lam[m] = res['lambda_hat']
        lse[m] = res['lambda_se']
        pm[m] = res['premium_mean']
        pse[m] = res['premium_mean_se']

    t0 = T // 2
    sd_lam = float(np.nanstd(lam[:, t0]))
    se_lam = float(np.nanmean(lse[:, t0]))
    sd_pm = float(np.std(pm))
    se_pm = float(np.mean(pse))
    print('=' * 78)
    print('L4  Monte Carlo (%d reps, AR(1) rho=0.3, T=%d, N=%d)' % (n_reps, T, N))
    print('=' * 78)
    print('  premium_mean   经验sd=%.6g  平均SE=%.6g  SE/sd=%.4f' % (
        sd_pm, se_pm, se_pm / sd_pm))
    print('  lambda_hat[%d]  经验sd=%.6g  平均SE=%.6g  SE/sd=%.4f' % (
        t0, sd_lam, se_lam, se_lam / sd_lam))
    print('  (SE/sd ≈ 1 → SE 口径正确; lambda 的复合近似在 0.8–1.25 内即视为可用)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stata', default=DEFAULT_STATA)
    ap.add_argument('--skip-stata', action='store_true')
    ap.add_argument('--mc', action='store_true')
    args = ap.parse_args()

    F, R = build_panel()
    est = PremiumEstimator(bandwidth=24)
    res = est.estimate_with_errors(F, R)

    if not args.skip_stata:
        work = Path(tempfile.mkdtemp(prefix='stata_hac_'))
        print('Stata workdir:', work)
        fx = export_fixtures(work, F, R, est, res)
        write_do(work, fx)
        run_stata(args.stata, work)
        compare(work, res, fx)
    if args.mc:
        run_mc()


if __name__ == '__main__':
    main()
