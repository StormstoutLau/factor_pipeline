# -*- coding: utf-8 -*-
"""多因子 × 多年实证扩展 — 12 因子全样本/三分段 + Barra 行业/风格中性化.

数据: E:\\Ashare_data (日频行情 2020-01-02 -> 2026-01-30; Barra 月频 -> 2023-05-31;
      财务因子经 scripts/convert_legacy_pickles.py 转为 parquet).
样本: 月末 FM + 下月前瞻收益; 上市满 250 交易日; 横截面 winsorize 1/99 + z-score;
      有效股票 < 300 的月份整行置 NaN.
统计: PremiumEstimator.estimate_with_errors (v3.4.12) 的 HAC SE + BH-FDR 双 p 口径.
断言: V1/V2/V3/V5/V7/V9 硬失败; V4/V6/V10 软判定 (WARN).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import numpy as np
import pandas as pd
from scipy import stats

from factor_pipeline.modules.factor_health import (
    FactorHealthDiagnoser,
    PremiumEstimator,
)
from verify_layer3_hac_real import build_eligible, cross_section_prep, month_end

DATA_ROOT = r"E:\Ashare_data"
CONVERTED_ROOT = r"E:\Ashare_data\_converted"
MIN_STOCKS = 300
MIN_VALID_PERIODS = 60
ALPHA = 0.05
KEYS = ('lambda_hat', 'lambda_se', 'lambda_ci_low', 'lambda_ci_high',
        'beta_t', 'beta_se', 'premium_mean', 'premium_mean_se',
        'premium_mean_ci_low', 'premium_mean_ci_high',
        'n_periods', 'n_valid', 'hac_lag', 'alpha')

PRICE_FACTORS = ['momentum_1m', 'reversal_1w', 'volatility_1m', 'amihud_1m',
                 'turnover_1m', 'size_mv', 'beta_60d', 'max_ret_1m']
FIN_FACTORS = ['current_ratio', 'debt_ratio', 'LT_debt_ratio', 'ocf_yoy']
ALL_FACTORS = PRICE_FACTORS + FIN_FACTORS
SELF_REFERENTIAL = {'size_mv', 'beta_60d'}      # 与 Barra SIZE/BETA 同源, 不做中性化
SEGMENTS = {
    'S1': ('2020-02-01', '2021-12-31'),
    'S2': ('2022-01-01', '2023-12-31'),
    'S3': ('2024-01-01', '2025-12-31'),
}
NEUT_START, NEUT_END = '2020-02-01', '2023-05-31'


def _load(root, name, csv=False):
    path = Path(root) / 'market_data' / name
    return pd.read_csv(path, index_col=0) if csv else pd.read_pickle(path)


def load_market(root):
    close = _load(root, 'stock_close.pkl')
    adj = _load(root, 'stock_adj.pkl')
    amount = _load(root, 'stock_amount.pkl')
    mv = _load(root, 'market_value.csv', csv=True)
    list_date = _load(root, 'list_date_df.pkl')['list_date']
    for df in (close, adj, amount, mv):
        df.index = pd.to_datetime(df.index)
    cols = close.columns
    adj = adj.reindex(index=close.index, columns=cols)
    amount = amount.reindex(index=close.index, columns=cols)
    mv = mv.reindex(index=close.index, columns=cols)
    list_date = pd.to_datetime(list_date.reindex(cols))
    return close, adj, amount, mv, list_date


def load_financials(root, close):
    """4 个财务因子 (parquet), 日频 → close 索引."""
    specs = {
        'current_ratio': 'construction_factors/current_ratio.parquet',
        'debt_ratio': 'construction_factors/debt_ratio.parquet',
        'LT_debt_ratio': 'construction_factors/LT_debt_ratio.parquet',
        'ocf_yoy': 'construction_factors/ocf_yoy_processed.parquet',
    }
    out, coverage = {}, {}
    for name, rel in specs.items():
        df = pd.read_parquet(Path(root) / rel)
        df.index = pd.to_datetime(df.index)
        df = df.reindex(index=close.index, columns=close.columns)
        df = df.ffill(limit=5)
        out[name] = df
        coverage[name] = int((df.notna().sum() > 0).sum())
    return out, coverage


def load_barra(root):
    """月频 Barra → {(Period, DataFrame[index=code, cols=INDNAME/SIZE/BETA/RESVOL])}."""
    raw = pd.read_pickle(Path(root) / 'market_data' / 'barra_df_tl.pkl')
    out = {}
    for key, rec in raw.items():
        cols = {k: pd.Series(v) for k, v in rec.items() if k != '_id'}
        df = pd.DataFrame(cols)
        df.index = df.index.astype(str)
        out[pd.Timestamp(key).to_period('M')] = df
    return out


def build_price_factors(adj_price, amount, mv):
    """日频右对齐量价因子 (方向: 数值大 = 预期收益高)."""
    log_ret = np.log(adj_price).diff()
    amt = amount.where(amount > 0)
    mkt = log_ret.mean(axis=1)

    beta = log_ret.rolling(60, min_periods=40).cov(mkt)
    beta = beta.div(mkt.rolling(60, min_periods=40).var(), axis=0)

    turnover = amt.div(mv.where(mv > 0))

    return {
        'momentum_1m': log_ret.rolling(21, min_periods=15).sum(),
        'reversal_1w': -log_ret.rolling(5, min_periods=4).sum(),
        'volatility_1m': -log_ret.rolling(21, min_periods=15).std(),
        'amihud_1m': -(log_ret.abs() / amt).rolling(21, min_periods=15).mean() * 1e8,
        'turnover_1m': -turnover.rolling(21, min_periods=15).mean(),
        'size_mv': -np.log(mv.where(mv > 0)),
        'beta_60d': -beta,
        'max_ret_1m': -log_ret.rolling(21, min_periods=15).max(),
    }


def build_monthly_panels(price_daily, fin_daily):
    panels = {k: month_end(v) for k, v in price_daily.items()}
    for k, v in fin_daily.items():
        panels[k] = month_end(v)
    return panels


def bh_fdr(pvals, alpha=ALPHA):
    p = np.asarray(pvals, dtype=float)
    q = np.full(p.shape, np.nan)
    ok = np.isfinite(p)
    if ok.sum() == 0:
        return q, np.zeros(p.shape, dtype=bool)
    pv = p[ok]
    m = len(pv)
    order = np.argsort(pv)
    ranked = pv[order]
    qv = ranked * m / np.arange(1, m + 1)
    qv = np.minimum.accumulate(qv[::-1])[::-1]
    tmp = np.empty(m)
    tmp[order] = np.minimum(qv, 1.0)
    q[ok] = tmp
    return q, np.where(ok, q <= alpha, False)


def verify_factor(name, f, r, bandwidth, alpha, is_financial=False):
    est = PremiumEstimator(bandwidth=bandwidth)
    res = est.estimate_with_errors(f, r, alpha=alpha)

    missing = [k for k in KEYS if k not in res]
    assert not missing, f'{name}: 缺键 {missing}'
    for k in ('lambda_hat', 'lambda_se', 'lambda_ci_low', 'lambda_ci_high',
              'beta_t', 'beta_se'):
        assert len(res[k]) == len(f), f'{name}: {k} 长度不符'

    beta = res['beta_t']
    n_valid = int(np.isfinite(beta).sum())
    pm, se = res['premium_mean'], res['premium_mean_se']
    warns = []

    ref = float(np.nanmean(beta)) if n_valid else np.nan
    assert np.isfinite(pm) and abs(pm - ref) <= 1e-12 * max(1.0, abs(ref)), \
        f'{name}: premium_mean {pm} != nanmean(beta) {ref}'

    assert np.isfinite(se) and se > 0, f'{name}: premium_mean_se 非有限/非正'
    assert res['premium_mean_ci_low'] <= pm <= res['premium_mean_ci_high'], \
        f'{name}: CI 不含点估计'

    naive_se = float(np.nanstd(beta) / np.sqrt(n_valid)) if n_valid else np.nan
    ratio = se / naive_se if naive_se and np.isfinite(naive_se) else np.nan
    if not (np.isfinite(ratio) and 0.3 <= ratio <= 3.0):
        warns.append(f'V4 HAC/iid={ratio:.2f} 越界')

    # 生产缺陷避让: BreakpointDetector.detect 在 T<30 时调用不存在的
    # _no_breakpoint_result (AttributeError)。分段 T≈24 会命中该路径,
    # 故仅在 n_valid>=30 时调用 diagnose (本任务不改生产代码)。
    if n_valid >= 30:
        diag = FactorHealthDiagnoser(bandwidth=bandwidth, alpha=alpha)
        d = diag.diagnose(f, r, return_type='static')
        dpm = d['premium_mean']
        diagnosis = d['diagnosis']
        premium_health = d['premium_health']
    else:
        dpm = np.nan
        diagnosis = 'na'
        premium_health = 'na'
    if abs(pm) > 2 * se and np.isfinite(dpm) and abs(dpm) > 0:
        assert np.sign(pm) == np.sign(dpm), \
            f'{name}: HAC 均值 {pm:.3e} 与 diagnose {dpm:.3e} 异号'

    # 月度覆盖只统计有标签的月份 (末月无前瞻收益, 天然为 0)
    lab_months = r.notna().any(axis=1)
    counts = (f.notna() & r.notna()).sum(axis=1)[lab_months]
    min_count = int(counts.min()) if len(counts) else 0
    if is_financial:
        assert min_count >= MIN_STOCKS, \
            f'{name}: 财务因子月度最小覆盖 {min_count} < {MIN_STOCKS}'
    if n_valid < MIN_VALID_PERIODS:
        warns.append(f'V6 n_valid={n_valid} < {MIN_VALID_PERIODS}')

    t = pm / se if np.isfinite(pm) and np.isfinite(se) else np.nan
    p_norm = 2 * (1 - stats.norm.cdf(abs(t))) if np.isfinite(t) else np.nan
    p_t = 2 * (1 - stats.t.cdf(abs(t), df=max(n_valid - 1, 1))) \
        if np.isfinite(t) else np.nan

    return {
        'factor': name,
        'premium_mean': float(pm),
        'premium_mean_se': float(se),
        't_hac': float(t),
        'p_norm': float(p_norm),
        'p_t': float(p_t),
        'hac_over_iid': float(ratio),
        'ci_low': float(res['premium_mean_ci_low']),
        'ci_high': float(res['premium_mean_ci_high']),
        'n_periods': int(res['n_periods']),
        'n_valid': n_valid,
        'min_month_count': min_count,
        'hac_lag': int(res['hac_lag']),
        'diagnosis': diagnosis,
        'premium_health': premium_health,
        'diagnose_premium_mean': float(dpm),
        'beta_t': [float(x) if np.isfinite(x) else None for x in beta],
        'warnings': warns,
    }


def beta_corr(rows):
    """β_t 序列两两相关 (BH 独立性前提的实测摘要)."""
    names = [r['factor'] for r in rows]
    M = np.array([[np.nan if v is None else v for v in r['beta_t']] for r in rows],
                 dtype=float)
    pairs = []
    abs_vals = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            ok = np.isfinite(M[i]) & np.isfinite(M[j])
            if ok.sum() > 2:
                rho = float(np.corrcoef(M[i][ok], M[j][ok])[0, 1])
                abs_vals.append(abs(rho))
                if abs(rho) > 0.5:
                    pairs.append({'a': names[i], 'b': names[j], 'rho': rho})
    return {
        'mean_abs_rho': float(np.mean(abs_vals)) if abs_vals else np.nan,
        'max_abs_rho': float(np.max(abs_vals)) if abs_vals else np.nan,
        'pairs_abs_gt_0.5': pairs,
    }


def run_sample(panels, ret_m, mask_m, start, end, bandwidth, alpha):
    rows = []
    for name in ALL_FACTORS:
        f = panels[name].loc[start:end].where(mask_m.loc[start:end])
        r = ret_m.loc[start:end]
        f_p, r_p = cross_section_prep(f, r, mask_m.loc[start:end])
        rows.append(verify_factor(name, f_p, r_p, bandwidth, alpha,
                                  is_financial=name in FIN_FACTORS))
    p_norm = [row['p_norm'] for row in rows]
    p_t = [row['p_t'] for row in rows]
    q_norm, rej_norm = bh_fdr(p_norm, alpha)
    q_t, rej_t = bh_fdr(p_t, alpha)
    for i, row in enumerate(rows):
        row['q_norm'] = float(q_norm[i])
        row['q_t'] = float(q_t[i])
        row['reject_norm'] = bool(rej_norm[i])
        row['reject_t'] = bool(rej_t[i])
        # 保守边界: 因子间 β_t 高相关时 BH 偏宽松, 附 Bonferroni 对照
        row['reject_bonf'] = bool(np.isfinite(row['p_norm'])
                                  and row['p_norm'] < alpha / len(rows))
    return rows, beta_corr(rows)


def stability(full_row, seg_rows):
    full_sign = np.sign(full_row['premium_mean'])
    signs = []
    for row in seg_rows:
        signs.append(int(np.sign(row['premium_mean']))
                     if np.isfinite(row['premium_mean']) else 0)
    agree = sum(1 for s in signs if s != 0 and s == full_sign)
    label = 'stable' if agree >= 2 else 'unstable'
    return {'agree': agree, 'seg_signs': signs, 'label': label}


def neutralize_panel(panel, barra, controls=('SIZE', 'BETA', 'RESVOL')):
    """月度截面: f ~ 1 + 行业哑变量 + SIZE + BETA + RESVOL, 取残差再 z-score."""
    out = pd.DataFrame(np.nan, index=panel.index, columns=panel.columns)
    corr_records = []
    for ts, row in panel.iterrows():
        rec = barra.get(ts.to_period('M'))
        if rec is None:
            continue
        cols = row.index.intersection(rec.index)
        if len(cols) < MIN_STOCKS:
            continue
        y = row.reindex(cols).astype(float)
        ctrl = rec.loc[cols]
        frame = pd.DataFrame({'y': y})
        for c in controls:
            frame[c] = pd.to_numeric(ctrl[c], errors='coerce')
        frame['ind'] = ctrl['INDNAME'].astype(str)
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
        if len(frame) < MIN_STOCKS:
            continue
        yv = frame['y'].to_numpy()
        for c in controls:
            rho = np.corrcoef(frame[c].to_numpy(), yv)[0, 1]
            if np.isfinite(rho):
                corr_records.append({'month': str(ts)[:10], 'control': c,
                                     'rho': float(rho), 'stage': 'raw'})
        dummies = pd.get_dummies(frame['ind'], drop_first=True, dtype=float)
        X = np.column_stack([np.ones(len(frame)),
                             dummies.to_numpy(),
                             frame[list(controls)].to_numpy()])
        coef, *_ = np.linalg.lstsq(X, yv, rcond=None)
        resid = yv - X @ coef
        sd = resid.std(ddof=1)
        if not np.isfinite(sd) or sd == 0:
            continue
        out.loc[ts, frame.index] = (resid - resid.mean()) / sd
        r2 = 1.0 - float(np.dot(resid, resid) / np.dot(yv - yv.mean(), yv - yv.mean()))
        for c in controls:
            rho = np.corrcoef(frame[c].to_numpy(), resid)[0, 1]
            if np.isfinite(rho):
                corr_records.append({'month': str(ts)[:10], 'control': c,
                                     'rho': float(rho), 'stage': 'resid',
                                     'r2': r2})
    return out, corr_records


def compare_arms(raw_rows, neut_rows, corr_records):
    raw_map = {r['factor']: r for r in raw_rows}
    out = []
    for row in neut_rows:
        base = raw_map[row['factor']]
        out.append({
            'factor': row['factor'],
            'raw_t': base['t_hac'],
            'neut_t': row['t_hac'],
            'raw_pm': base['premium_mean'],
            'neut_pm': row['premium_mean'],
            'raw_reject': base['reject_norm'],
            'neut_reject': row['reject_norm'],
            'flip': bool(base['reject_norm'] != row['reject_norm']),
            'sign_flip': bool(np.sign(base['premium_mean'])
                              != np.sign(row['premium_mean'])),
        })
    rho = {}
    for stage in ('raw', 'resid'):
        for c in ('SIZE', 'BETA', 'RESVOL'):
            vals = [abs(rec['rho']) for rec in corr_records
                    if rec['control'] == c and rec['stage'] == stage]
            rho['%s_%s' % (stage, c)] = float(np.mean(vals)) if vals else np.nan
    r2 = [rec['r2'] for rec in corr_records if 'r2' in rec]
    rho['mean_r2'] = float(np.mean(r2)) if r2 else np.nan
    return out, rho


def lag_sensitivity(f, r, lags=(1, 2, 3, 4, 6), alpha=ALPHA):
    est = PremiumEstimator(bandwidth=12)
    out = {}
    for q in lags:
        res = est.estimate_with_errors(f, r, alpha=alpha, max_lag=q)
        se = res['premium_mean_se']
        out[str(q)] = float(res['premium_mean'] / se) if se and np.isfinite(se) else np.nan
    return out


def bandwidth_sensitivity(f, r, hs=(6, 12, 24), alpha=ALPHA):
    labels, paths = {}, {}
    for h in hs:
        d = FactorHealthDiagnoser(bandwidth=h, alpha=alpha).diagnose(
            f, r, return_type='static')
        labels[str(h)] = d['diagnosis']
        paths[h] = PremiumEstimator(bandwidth=h).estimate(f, r)
    base = paths[12]
    corr = {}
    for h in hs:
        a, b = paths[h], base
        ok = np.isfinite(a) & np.isfinite(b)
        corr[str(h)] = float(np.corrcoef(a[ok], b[ok])[0, 1]) if ok.sum() > 2 else np.nan
    return {'labels': labels, 'lambda_corr_vs_h12': corr}


def _fmt_row(r):
    return ('%-15s %12.6e %12.6e %6.2f %7.3f %5d %-10s %-4s %s'
            % (r['factor'], r['premium_mean'], r['premium_mean_se'],
               r['t_hac'], r['hac_over_iid'], r['n_valid'],
               r['premium_health'],
               'Y' if r['reject_norm'] else 'n',
               '; '.join(r['warnings']) or '-'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-root', default=DATA_ROOT)
    ap.add_argument('--converted-root', default=CONVERTED_ROOT)
    ap.add_argument('--bandwidth', type=int, default=12)
    ap.add_argument('--alpha', type=float, default=ALPHA)
    ap.add_argument('--json', default=None)
    args = ap.parse_args()

    close, adj, amount, mv, list_date = load_market(args.data_root)
    adj_price = close * adj
    eligible = month_end(build_eligible(close, list_date).astype(float)) > 0
    fin_daily, fin_cov = load_financials(args.converted_root, close)

    price_daily = build_price_factors(adj_price, amount, mv)
    panels = build_monthly_panels(price_daily, fin_daily)

    price_m = month_end(adj_price)
    ret_m = price_m.shift(-1) / price_m - 1.0
    ret_m = ret_m.mask(ret_m.abs() > 1.0)
    mask_m = eligible

    print('=' * 108)
    print('多因子 × 多年实证 — 12 因子, bandwidth=%d, alpha=%.2f'
          % (args.bandwidth, args.alpha))
    print('=' * 108)
    header = ('%-15s %12s %12s %6s %7s %5s %-10s %-4s %s'
              % ('factor', 'premium', 'se', 't', 'SEratio', 'nval',
                 'health', 'BH', 'warnings'))
    print(header)
    print('-' * len(header))

    full_rows, full_corr = run_sample(panels, ret_m, mask_m, None, None,
                                      args.bandwidth, args.alpha)
    print('\n[全样本 2020-02 -> 2025-12]')
    for row in full_rows:
        print(_fmt_row(row))
    print('beta_t 两两 |rho|: mean=%.3f max=%.3f (>0.5 的对: %d); BH 通过 %d, Bonferroni 通过 %d'
          % (full_corr['mean_abs_rho'], full_corr['max_abs_rho'],
             len(full_corr['pairs_abs_gt_0.5']),
             sum(r['reject_norm'] for r in full_rows),
             sum(r['reject_bonf'] for r in full_rows)))

    seg_rows, seg_corr, stab = {}, {}, {}
    for seg, (start, end) in SEGMENTS.items():
        rows, corr = run_sample(panels, ret_m, mask_m, start, end,
                                args.bandwidth, args.alpha)
        seg_rows[seg] = rows
        seg_corr[seg] = corr
        print('\n[%s %s -> %s]' % (seg, start, end))
        for row in rows:
            print(_fmt_row(row))
    seg_map = {s: {r['factor']: r for r in rows} for s, rows in seg_rows.items()}
    for row in full_rows:
        stab[row['factor']] = stability(
            row, [seg_map[s][row['factor']] for s in SEGMENTS])

    # I: Barra 中性化 (2020-02 -> 2023-05)
    barra = load_barra(args.data_root)
    neut_masks = mask_m.loc[NEUT_START:NEUT_END]
    print('\n[中性化区间 %s -> %s, %d 个月]'
          % (NEUT_START, NEUT_END, len(neut_masks)))
    raw_rows, neut_rows, corr_records = [], [], []
    for name in ALL_FACTORS:
        if name in SELF_REFERENTIAL:
            continue
        f = panels[name].loc[NEUT_START:NEUT_END].where(neut_masks)
        r = ret_m.loc[NEUT_START:NEUT_END]
        f_p, r_p = cross_section_prep(f, r, neut_masks)
        raw_rows.append(verify_factor(name, f_p, r_p, args.bandwidth, args.alpha,
                                      is_financial=name in FIN_FACTORS))
        f_n, recs = neutralize_panel(panels[name].loc[NEUT_START:NEUT_END], barra)
        f_n, r_n = cross_section_prep(f_n.where(neut_masks), r, neut_masks)
        neut_rows.append(verify_factor(name, f_n, r_n, args.bandwidth, args.alpha,
                                       is_financial=name in FIN_FACTORS))
        corr_records.extend(recs)
    for rows in (raw_rows, neut_rows):
        q_norm, rej = bh_fdr([x['p_norm'] for x in rows], args.alpha)
        for i, row in enumerate(rows):
            row['q_norm'] = float(q_norm[i])
            row['reject_norm'] = bool(rej[i])
    arms, rho = compare_arms(raw_rows, neut_rows, corr_records)
    print('%-15s %8s %8s %8s %s' % ('factor', 'raw_t', 'neut_t', 'd_t', 'flip'))
    print('-' * 52)
    for row in arms:
        print('%-15s %8.2f %8.2f %8.2f %s'
              % (row['factor'], row['raw_t'], row['neut_t'],
                 row['neut_t'] - row['raw_t'], 'FLIP' if row['flip'] else '-'))
    print('pre/post-neutralization mean |rho|: '
          + ', '.join('%s=%.3f' % (k, v) for k, v in rho.items() if k != 'mean_r2')
          + ', mean_R2=%.3f' % rho['mean_r2'])

    # 敏感性
    lag_sens, bw_sens = {}, {}
    for name in ALL_FACTORS:
        f = panels[name].where(mask_m)
        r = ret_m
        f_p, r_p = cross_section_prep(f, r, mask_m)
        lag_sens[name] = lag_sensitivity(f_p, r_p, alpha=args.alpha)
        bw_sens[name] = bandwidth_sensitivity(f_p, r_p, alpha=args.alpha)

    warns = [w for row in full_rows for w in row['warnings']]
    payload = {
        'meta': {
            'data_root': args.data_root,
            'bandwidth': args.bandwidth,
            'alpha': args.alpha,
            'n_factors': len(ALL_FACTORS),
            'financial_coverage': fin_cov,
            'neutralization_period': [NEUT_START, NEUT_END],
        },
        'full': full_rows,
        'segments': seg_rows,
        'stability': stab,
        'beta_corr': {'full': full_corr, 'segments': seg_corr},
        'neutralization': {'raw': raw_rows, 'neutralized': neut_rows,
                           'compare': arms, 'post_neut_abs_rho': rho},
        'sensitivity': {'lag': lag_sens, 'bandwidth': bw_sens},
        'warnings': warns,
    }
    if args.json:
        Path(args.json).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print('\nJSON -> %s' % args.json)

    print('\n[方向稳定性]')
    for name in ALL_FACTORS:
        s = stab[name]
        print('%-15s agree=%d/3 %-8s seg_signs=%s'
              % (name, s['agree'], s['label'], s['seg_signs']))


if __name__ == '__main__':
    main()
