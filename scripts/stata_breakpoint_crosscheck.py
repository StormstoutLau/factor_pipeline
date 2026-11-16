# -*- coding: utf-8 -*-
"""v3.5.0 多断点 Stata 对拍校验.

对拍三级 (全部走 Stata 官方 regress, 见 RESEARCH §4):
  L1  单断点 sup-F: Stata 逐点 `regress y d; test d` vs Python `detect()`
  L2  m=0/1/2 全局最小 SSR + 断点集: Stata 循环 `regress y d1 [d2]` 读 `e(rss)`
      vs Python `detect_multiple` 的 DP
  L3  BIC / LWZ: 用 Stata 侧 SSR 计算准则值 vs Python

样本: syn0 (纯噪声) / syn1 (单断点) / syn2 (两断点) / real (A 股 β_t, 可 --skip-real)

用法:
    python scripts/stata_breakpoint_crosscheck.py
    python scripts/stata_breakpoint_crosscheck.py --skip-real
    python scripts/stata_breakpoint_crosscheck.py --stata-path "C:\\Program Files\\Stata18\\StataMP-64.exe"

Stata 缺失时打印 SKIP 并退出码 0。
"""
import argparse
import glob
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import numpy as np

from factor_pipeline.modules.factor_health import BreakpointDetector

STATA_CANDIDATES = [
    r'C:\Program Files\Stata19\StataMP-64.exe',
    r'C:\Program Files\Stata18\StataMP-64.exe',
    r'C:\Program Files\Stata17\StataMP-64.exe',
    r'C:\Program Files\Stata18\StataSE-64.exe',
    r'C:\Program Files\Stata17\StataSE-64.exe',
]
DATA_ROOT = r'E:\Ashare_data'
CONVERTED_ROOT = r'E:\Ashare_data\_converted'
MIN_SEGMENT = 0.15


# ── 样本 ────────────────────────────────────────────────────────────────────

def _synth(T=120, breaks=(), means=(0.0,), seed=7, sigma=1.0):
    rng = np.random.default_rng(seed)
    y = rng.normal(0.0, sigma, T)
    edges = [0] + list(breaks) + [T]
    for j, (a, b) in enumerate(zip(edges[:-1], edges[1:])):
        y[a:b] += means[j]
    return y


def build_samples(skip_real=False, data_root=DATA_ROOT,
                  converted_root=CONVERTED_ROOT):
    """返回 {name: (y, m_max, run_l1)}."""
    out = {
        'syn0': (_synth(T=120, seed=23), 2, False),
        'syn1': (_synth(T=120, breaks=(50,), means=(0.0, 0.8), seed=7), 2, True),
        'syn2': (_synth(T=120, breaks=(40, 80), means=(0.0, 0.8, -0.5),
                       seed=11, sigma=0.6), 2, False),
    }
    if not skip_real:
        y = load_real_beta(data_root, converted_root)
        if y is not None:
            out['real'] = (y, 2, False)
    return out


def load_real_beta(data_root, converted_root):
    """真实 A 股: turnover_1m 的 β_t 序列 (C 任务同口径)."""
    try:
        from verify_layer3_hac_real import build_eligible, cross_section_prep, month_end
        from verify_multifactor_multiyear import (
            build_monthly_panels, build_price_factors, load_financials, load_market,
        )
        from factor_pipeline.modules.factor_health import PremiumEstimator

        close, adj, amount, mv, list_date = load_market(data_root)
        adj_price = close * adj
        eligible = month_end(build_eligible(close, list_date).astype(float)) > 0
        fin, _ = load_financials(converted_root, close)
        panels = build_monthly_panels(build_price_factors(adj_price, amount, mv), fin)
        price_m = month_end(adj_price)
        ret_m = price_m.shift(-1) / price_m - 1.0
        ret_m = ret_m.mask(ret_m.abs() > 1.0)
        thin = (eligible & ret_m.notna()).sum(axis=1) < 300
        ret = ret_m.mask(thin, axis=0)
        mask = eligible.mask(thin, axis=0)
        f, _ = cross_section_prep(panels['turnover_1m'], ret, mask)
        est = PremiumEstimator(bandwidth=12)
        est.estimate(f, ret)
        beta = np.asarray(est._beta_raw, dtype=float)
        beta = beta[np.isfinite(beta)]
        print('[real] turnover_1m β_t: T=%d' % len(beta))
        return beta
    except Exception as exc:  # 数据缺失时降级, 不影响合成样本对拍
        print('[real] SKIP (加载失败: %s)' % exc)
        return None


# ── Python 侧结果 ───────────────────────────────────────────────────────────

def python_side(y, m_max):
    det = BreakpointDetector(min_segment=MIN_SEGMENT)
    T = len(y)
    h = max(5, int(T * MIN_SEGMENT))
    out = {'T': T, 'h': h}

    single = det.detect(y)
    out['L1_F'] = float(single['chow_max_stat'])
    out['L1_BP'] = single.get('breakpoint_idx')

    cs, cs2 = det._ssr_prefix(y)
    mat = det._build_ssr_matrix(cs, cs2, T, h)
    multi = det.detect_multiple(y, m_max=m_max)
    for k in range(0, m_max + 1):
        if k == 0:
            val, brks = float(mat[0, T]), []
        else:
            val, brks = det._dp_breaks(mat, T, h, k)
        out['L2_SSR_%d' % k] = float(val)
        out['L2_BRK_%d' % k] = [int(b) for b in brks]
        out['L3_BIC_%d' % k] = det._bic(val, T, k)
        out['L3_LWZ_%d' % k] = det._lwz(val, T, k)
    out['multi'] = multi
    return out


# ── Stata 侧 ────────────────────────────────────────────────────────────────

def build_do(csv_name, T, h, m_max, run_l1):
    """生成 .do 文本 (所有循环边界在 Python 侧算成明文数字)."""
    lines = [
        'clear all',
        'set more off',
        'import delimited "%s", clear' % csv_name,
        'local T = _N',
        'local lnT = ln(`T\')',
        'gen byte d1 = 0',
        'gen byte d2 = 0',
        'quietly regress y',
        'local ssr0 = e(rss)',
        '',
        '* L2 m=1: 循环 regress 穷举',
        'local bestSSR = 1e300',
        'local bestB1 = 0',
        'forvalues b1 = %d/%d {' % (h, T - h - 1),
        '    quietly replace d1 = t > `b1\'',
        '    quietly regress y d1',
        '    if e(rss) < `bestSSR\' {',
        '        local bestSSR = e(rss)',
        '        local bestB1 = `b1\'',
        '    }',
        '}',
        'local ssr1 = `bestSSR\'',
        'display "L2_SSR_1=" %20.12f `ssr1\'',
        'display "L2_BRK_1=" `bestB1\'',
        '',
        '* L2 m=2: 双层循环',
        'local bestSSR = 1e300',
        'local bestB1 = 0',
        'local bestB2 = 0',
        'forvalues b1 = %d/%d {' % (h, T - 2 * h),
        '    quietly replace d1 = t > `b1\'',
        '    local lo = `b1\' + %d' % h,
        '    forvalues b2 = `lo\'/%d {' % (T - h - 1),
        '        quietly replace d2 = t > `b2\'',
        '        quietly regress y d1 d2',
        '        if e(rss) < `bestSSR\' {',
        '            local bestSSR = e(rss)',
        '            local bestB1 = `b1\'',
        '            local bestB2 = `b2\'',
        '        }',
        '    }',
        '}',
        'local ssr2 = `bestSSR\'',
        'display "L2_SSR_2=" %20.12f `ssr2\'',
        'display "L2_BRK_2=" `bestB1\' "," `bestB2\'',
        'display "L2_SSR_0=" %20.12f `ssr0\'',
        'display "L2_BRK_0="',
        '',
        '* L3: BIC / LWZ',
        'forvalues m = 0/%d {' % m_max,
        '    local ssr = `ssr`m\'\'',
        '    local bic = ln(`ssr\'/`T\') + (`m\'+1)*`lnT\'/`T\'',
        '    local lwz = ln(`ssr\'/`T\') + (`m\'+1)*0.1*(`lnT\')^2.1/`T\'',
        '    display "L3_BIC_`m\'=" %20.12f `bic\'',
        '    display "L3_LWZ_`m\'=" %20.12f `lwz\'',
        '}',
    ]
    if run_l1:
        lines += [
            '',
            '* L1: 单断点 sup-F (官方 regress + test)',
            'local bestF = -1',
            'local bestBP = 0',
            'forvalues bp = %d/%d {' % (h, T - h - 1),
            '    quietly replace d1 = t > `bp\'',
            '    quietly regress y d1',
            '    quietly test d1',
            '    local f = r(F)',
            '    if `f\' > `bestF\' {',
            '        local bestF = `f\'',
            '        local bestBP = `bp\'',
            '    }',
            '}',
            'display "L1_F=" %20.12f `bestF\'',
            'display "L1_BP=" `bestBP\'',
        ]
    lines.append('display "DONE_OK"')
    return '\n'.join(lines) + '\n'


def run_stata(stata_path, workdir, do_name, timeout=600):
    log_path = Path(workdir) / (Path(do_name).stem + '.log')
    if log_path.exists():
        log_path.unlink()
    proc = subprocess.run(
        [stata_path, '/e', 'do', do_name],
        cwd=str(workdir), timeout=timeout,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if not log_path.exists():
        raise RuntimeError(
            'Stata 未生成日志 (exit=%s): %s' % (
                proc.returncode, proc.stderr.decode('utf-8', 'replace')[:400]))
    return log_path.read_text(encoding='utf-8', errors='replace')


def parse_log(text):
    out = {}
    # 注意: 用 [ \t]* 而非 \s*, 后者会跨行吃掉空值行 (L2_BRK_0=)
    for key, val in re.findall(r'^([A-Z][A-Z0-9_]*)=[ \t]*(.*)$', text, re.M):
        val = val.strip()
        if key.startswith('L2_BRK_'):
            out[key] = [int(v) for v in val.split(',') if v.strip()]
        else:
            try:
                out[key] = float(val)
            except ValueError:
                out[key] = val
    out['_done'] = 'DONE_OK' in text
    return out


# ── 对比 ────────────────────────────────────────────────────────────────────

def rel_err(a, b):
    if a is None or b is None:
        return float('nan')
    a, b = float(a), float(b)
    if not (np.isfinite(a) and np.isfinite(b)):
        return float('nan')
    denom = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / denom


def compare(name, py, st, m_max):
    rows = []

    def add(item, pv, sv, ok, err=None, abs_err=None):
        rows.append({'sample': name, 'item': item, 'python': pv,
                     'stata': sv, 'rel_err': err, 'abs_err': abs_err,
                     'ok': bool(ok)})

    if 'L1_F' in st:
        # 相对 1e-7: Stata regress 与 numpy 前缀和的 OLS 浮点路径不同
        err = rel_err(py['L1_F'], st['L1_F'])
        add('L1_F', py['L1_F'], st['L1_F'], err < 1e-7, err)
        ok_bp = py['L1_BP'] == st.get('L1_BP')
        add('L1_BP', py['L1_BP'], st.get('L1_BP'), ok_bp)

    for k in range(0, m_max + 1):
        err = rel_err(py['L2_SSR_%d' % k], st.get('L2_SSR_%d' % k))
        add('L2_SSR_%d' % k, py['L2_SSR_%d' % k], st.get('L2_SSR_%d' % k),
            err < 1e-6, err)
        if k > 0:
            py_b = sorted(py['L2_BRK_%d' % k])
            st_b = sorted(st.get('L2_BRK_%d' % k, []))
            add('L2_BRK_%d' % k, py_b, st_b, py_b == st_b)

    for k in range(0, m_max + 1):
        for key in ('BIC', 'LWZ'):
            pv = py['L3_%s_%d' % (key, k)]
            sv = st.get('L3_%s_%d' % (key, k))
            # 准则值可接近 0 → 用绝对误差 (1e-8) 而非相对误差
            ae = (abs(pv - sv)
                  if isinstance(pv, float) and isinstance(sv, float) else None)
            add('L3_%s_%d' % (key, k), pv, sv,
                ae is not None and ae < 1e-8, rel_err(pv, sv), ae)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stata-path', default=None)
    ap.add_argument('--skip-real', action='store_true')
    ap.add_argument('--json', default=None)
    args = ap.parse_args()

    stata = args.stata_path
    if stata is None:
        for cand in STATA_CANDIDATES:
            if Path(cand).exists():
                stata = cand
                break
        if stata is None:
            hits = glob.glob(r'C:\Program Files\Stata*\Stata*-64.exe')
            stata = hits[0] if hits else None
    if stata is None or not Path(stata).exists():
        print('SKIP: 未找到 Stata (尝试过 %s)' % ', '.join(STATA_CANDIDATES))
        return 0
    print('Stata: %s' % stata)

    samples = build_samples(skip_real=args.skip_real)
    workdir = Path(tempfile.gettempdir()) / 'stata_bp_crosscheck'
    workdir.mkdir(parents=True, exist_ok=True)

    all_rows = []
    for name, (y, m_max, run_l1) in samples.items():
        T = len(y)
        h = max(5, int(T * MIN_SEGMENT))
        csv_path = workdir / ('%s.csv' % name)
        np.savetxt(csv_path, np.column_stack([np.arange(1, T + 1), y]),
                   delimiter=',', header='t,y', comments='', fmt='%.17g')
        do_name = '%s.do' % name
        (workdir / do_name).write_text(
            build_do(csv_path.name, T, h, m_max, run_l1), encoding='utf-8')

        py = python_side(y, m_max)
        log = run_stata(stata, workdir, do_name)
        st = parse_log(log)
        if not st.get('_done'):
            print('\n[%s] FAIL: Stata 未跑完, 日志尾部:\n%s'
                  % (name, '\n'.join(log.splitlines()[-12:])))
            return 1

        rows = compare(name, py, st, m_max)
        all_rows.extend(rows)
        bad = [r for r in rows if not r['ok']]
        print('\n[%s] T=%d h=%d m_max=%d  %s'
              % (name, T, h, m_max, 'PASS' if not bad else
                 'FAIL(%d)' % len(bad)))
        for r in rows:
            if r['abs_err'] is not None:
                err = '  abs=%.2e' % r['abs_err']
            elif r['rel_err'] is not None:
                err = '  rel=%.2e' % r['rel_err']
            else:
                err = ''
            print('  %-12s py=%-26s st=%-26s %s%s'
                  % (r['item'], _fmt(r['python']), _fmt(r['stata']),
                     'OK' if r['ok'] else 'MISMATCH', err))

    bad_all = [r for r in all_rows if not r['ok']]
    print('\n' + '=' * 78)
    print('对拍汇总: %d 项, PASS %d, FAIL %d'
          % (len(all_rows), len(all_rows) - len(bad_all), len(bad_all)))
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(
            json.dumps({'rows': all_rows, 'fail': len(bad_all)},
                       ensure_ascii=False, indent=2), encoding='utf-8')
        print('JSON -> %s' % args.json)
    return 0 if not bad_all else 1


def _fmt(v):
    if isinstance(v, list):
        return str(v)
    if isinstance(v, float):
        return '%.10g' % v
    return str(v)


if __name__ == '__main__':
    sys.exit(main())
