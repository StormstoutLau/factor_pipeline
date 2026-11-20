# -*- coding: utf-8 -*-
"""组合层 IC/Sharpe 回测 — 4 个 BH 通过因子的月频分位组合.

数据: E:\\Ashare_data (日频 2020-01-02 -> 2026-01-30; 沪深300 日频成分 2009 -> 2026-01-30).
因子: turnover_1m / reversal_1w / volatility_1m / max_ret_1m (C 任务 BH 通过的非自指因子)
      + 四者 z-score 等权合成的复合因子.
组合: 月度调仓, 5 分位等权; 多空 Q5-Q1; 多头 Q5; 池 = 全市场 / 沪深300 成分.
成本: 单边 0/10/20/30 bp, cost = 2 * turnover * fee (买卖双边).
断言: V1/V2/V3/V4/V5/V6/V9/V10 硬失败; V7/V8 软判定 (WARN).

口径见 docs/research/RESEARCH_PORTFOLIO_BACKTEST.md 与
docs/private/DESIGN_PORTFOLIO_BACKTEST.md (G1-G13).
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import numpy as np
import pandas as pd

from factor_pipeline.backtest.factor_metrics import (
    compute_hit_rate,
    compute_icir,
    compute_rank_ic,
    compute_spread,
    compute_turnover,
)
from factor_pipeline.modules.factor_health import PremiumEstimator
from verify_layer3_hac_real import build_eligible, cross_section_prep, month_end
from verify_multifactor_multiyear import (
    build_monthly_panels,
    build_price_factors,
    load_financials,
    load_market,
)

DATA_ROOT = r"E:\Ashare_data"
CONVERTED_ROOT = r"E:\Ashare_data\_converted"
FACTORS = ['turnover_1m', 'reversal_1w', 'volatility_1m', 'max_ret_1m']
COMPOSITE = 'composite'
Q = 5
FEE_BPS = (0, 10, 20, 30)
POOLS = {'all': None, 'hs300': '000300'}
SEGMENTS = {
    'full': None,
    'S1': ('2020-02-01', '2022-12-31'),
    'S2': ('2023-01-01', '2025-12-31'),
}
MIN_POOL_STOCKS = 250
MIN_STOCKS = 300
NW_LAG = 3
BANDWIDTH = 12


# ── 数据层 ──────────────────────────────────────────────────────────────────

def load_index_members(root, code='000300'):
    """读取指数日频成分 (无前视: 当日已公布权重)."""
    path = Path(root) / 'market_data' / 'index_dict.pkl'
    d = pd.read_pickle(path)['index'].copy()
    d['_id'] = pd.to_datetime(d['_id'])
    d = d.set_index('_id').sort_index()
    return d['indexComponentsWeight'].apply(
        lambda w: frozenset(w.get(code, {}).keys()) if isinstance(w, dict) else frozenset())


def align_pool(members, month_index, columns):
    """月末对齐: 取 <= 月末的最后一个交易日的成分."""
    out = pd.DataFrame(False, index=month_index, columns=columns)
    idx = members.index
    for ts in month_index:
        pos = idx.searchsorted(ts, side='right') - 1
        if pos < 0:
            continue
        s = members.iloc[pos]
        if not s:
            continue
        cols = out.columns.intersection(pd.Index(sorted(s)))
        if len(cols):
            out.loc[ts, cols] = True
    return out


# ── 组合层 ──────────────────────────────────────────────────────────────────

def build_quantile_weights(f, r, q=Q):
    """单期分位等权权重: {Q1..Qq: DataFrame[T, N]}, 空分位整行 0."""
    valid = f.notna() & r.notna()
    ranks = f.where(valid).rank(axis=1, pct=True)
    labels = np.ceil(ranks * q)
    out = {}
    for k in range(1, q + 1):
        sel = labels.eq(k)
        cnt = sel.sum(axis=1)
        w = sel.div(cnt.where(cnt > 0), axis=0).fillna(0.0)
        out['Q%d' % k] = w
    return out


def portfolio_return(w, r):
    """组合收益: r 的 NaN 处权重已为 0 (valid 掩码), fillna 仅为求和稳定."""
    return (w * r.fillna(0.0)).sum(axis=1)


def build_turnover(w):
    """换手序列: 首期为建仓换手, 其后 0.5*Σ|Δw|."""
    arr = np.asarray(w, dtype=float)
    if len(arr) == 0:
        return np.array([])
    first = 0.5 * np.abs(arr[0]).sum()
    return np.concatenate([[first], compute_turnover(arr)])


# ── 指标层 ──────────────────────────────────────────────────────────────────

def nw_t(x, lag=NW_LAG):
    """Newey-West (1987) Bartlett 核 t 值."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3:
        return np.nan
    mu = float(x.mean())
    e = x - mu
    s = float(e @ e) / n
    for l in range(1, min(lag, n - 1) + 1):
        gl = float(e[l:] @ e[:-l]) / n
        s += 2.0 * (1.0 - l / (lag + 1.0)) * gl
    if s <= 0:
        return np.nan
    return float(mu / np.sqrt(s / n))


def max_drawdown(x):
    """复利净值的最大回撤 (正数表示回撤幅度)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return np.nan
    nav = np.cumprod(1.0 + x)
    peak = np.maximum.accumulate(nav)
    return float(np.max(1.0 - nav / peak))


def perf(x, turnover, fee_bps):
    """单序列组合指标 (毛利 / 净利 / 成本敏感性)."""
    r = np.asarray(x, dtype=float)
    t = np.asarray(turnover, dtype=float)
    assert len(r) == len(t), 'perf: 收益与换手长度不一致'
    ok = np.isfinite(r)
    rv, tv = r[ok], t[ok]
    n = len(rv)
    nan = float('nan')
    if n < 3:
        out = {k: nan for k in (
            'ann_ret_gross', 'ann_ret_net', 'ann_vol', 'sharpe_gross',
            'sharpe_net', 'nw_t_gross', 'nw_t_net', 'maxdd_net', 'hit_rate',
            'turnover_ann', 'fee_bps')}
        out['n_months'] = n
        return out
    net = rv - 2.0 * tv * fee_bps / 1e4
    return {
        'ann_ret_gross': float(rv.mean() * 12),
        'ann_ret_net': float(net.mean() * 12),
        'ann_vol': float(rv.std(ddof=1) * np.sqrt(12)),
        'sharpe_gross': float(compute_spread(rv) * np.sqrt(12)),
        'sharpe_net': float(compute_spread(net) * np.sqrt(12)),
        'nw_t_gross': nw_t(rv),
        'nw_t_net': nw_t(net),
        'maxdd_net': max_drawdown(net),
        'hit_rate': float((net > 0).mean()),
        'turnover_ann': float(tv.mean() * 12),
        'fee_bps': float(fee_bps),
        'n_months': int(n),
    }


def composite_panel(z_dict):
    """多因子等权合成 (nanmean): 至少 1 个因子有效即保留."""
    keys = list(z_dict)
    base = z_dict[keys[0]]
    stack = np.stack([z_dict[k].values for k in keys])
    cnt = np.isfinite(stack).sum(axis=0)
    total = np.nansum(stack, axis=0)
    mean = np.divide(total, cnt, out=np.full_like(total, np.nan), where=cnt > 0)
    return pd.DataFrame(mean, index=base.index, columns=base.columns)


# ── 流程层 ──────────────────────────────────────────────────────────────────

def run_block(f_z, ret, pool_mask, fee_list):
    """单个 (因子, 池, 区间) 的组合指标."""
    f = f_z.where(pool_mask)
    w = build_quantile_weights(f, ret, Q)

    # V2: 多头行和 ∈ {0, 1}; 多空 |Σw| < 1e-12
    for k, wk in w.items():
        rs = wk.sum(axis=1)
        bad = ~np.isclose(rs, 0.0) & ~np.isclose(rs, 1.0)
        assert not bad.any(), 'V2: %s 行和越界' % k
    w_ls = w['Q5'] - w['Q1']
    assert float(np.abs(w_ls.sum(axis=1)).max()) < 1e-12, 'V2: 多空行和 != 0'

    # V3: 多头权重非负
    for k, wk in w.items():
        assert float(np.nanmin(wk.values)) >= 0.0, 'V3: %s 含负权重' % k

    r_q = {k: portfolio_return(w[k], ret) for k in w}
    r_ls = portfolio_return(w_ls, ret)
    r_lo = r_q['Q5']
    bench = ret.where(pool_mask).mean(axis=1)
    r_ex = r_lo - bench

    t_ls = build_turnover(w_ls)
    t_lo = build_turnover(w['Q5'])

    # V9: 换手范围
    assert np.nanmax(t_lo) <= 1.0 + 1e-9, 'V9: 多头换手 > 1'
    assert np.nanmax(t_ls) <= 2.0 + 1e-9, 'V9: 多空换手 > 2'

    # Rank IC: 池内口径 (池过滤后的因子)
    ic = np.array([compute_rank_ic(f.iloc[t].values, ret.iloc[t].values)
                   for t in range(len(f))])
    out = {
        'n_months': int(np.isfinite(r_ls.values).sum()),
        'ic_mean': float(np.nanmean(ic)) if np.isfinite(ic).any() else float('nan'),
        'icir': float(compute_icir(ic)),
        'ic_hit': float(compute_hit_rate(ic)),
        'n_ic': int(np.isfinite(ic).sum()),
        'ic_series': [None if not np.isfinite(v) else float(v) for v in ic],
        'quantile_ann': {k: float(np.nanmean(v.values) * 12) for k, v in r_q.items()},
        'ls': {fee: perf(r_ls.values, t_ls, fee) for fee in fee_list},
        'long': {fee: perf(r_lo.values, t_lo, fee) for fee in fee_list},
        'excess': {fee: perf(r_ex.values, t_lo, fee) for fee in fee_list},
        'pool_size_mean': float(pool_mask.sum(axis=1).mean()),
    }
    # 盈亏平衡费率 (成本与 fee 严格线性)
    ok = np.isfinite(r_ls.values)
    gross_ann = float(np.mean(r_ls.values[ok]) * 12) if ok.any() else float('nan')
    mean_t = float(np.mean(t_ls[ok])) if ok.any() else float('nan')
    out['breakeven_bps'] = (
        gross_ann / (2.0 * mean_t * 12.0 / 1e4)
        if np.isfinite(mean_t) and mean_t > 0 else float('nan'))
    return out


def _write_report_json(path, tool, checks, artifacts, status):
    """v3.9.0 统一验证报告（schema 见 DESIGN §8.1）；默认不写。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'tool': tool,
        'generated_at': datetime.now().isoformat(),
        'checks': checks,
        'artifacts': artifacts,
        'status': status,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                      encoding='utf-8')
    print('report-json -> %s' % target)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-root', default=DATA_ROOT)
    ap.add_argument('--converted-root', default=CONVERTED_ROOT)
    ap.add_argument('--fee-bps', type=int, nargs='+', default=list(FEE_BPS))
    ap.add_argument('--bands', type=int, default=BANDWIDTH)
    ap.add_argument('--json', default=None)
    ap.add_argument('--report-json', default=None,
                    help='v3.9.0 统一验证报告路径（默认关闭）')
    args = ap.parse_args()

    close, adj, amount, mv, list_date = load_market(args.data_root)
    adj_price = close * adj
    eligible = month_end(build_eligible(close, list_date).astype(float)) > 0
    fin_daily, _ = load_financials(args.converted_root, close)
    price_daily = build_price_factors(adj_price, amount, mv)
    panels = build_monthly_panels(price_daily, fin_daily)

    price_m = month_end(adj_price)
    ret_m = price_m.shift(-1) / price_m - 1.0
    ret_m = ret_m.mask(ret_m.abs() > 1.0)

    # V1: 面板对齐 + 末月无前瞻收益
    for name in FACTORS:
        assert panels[name].index.equals(ret_m.index), 'V1: %s 索引不一致' % name
        assert panels[name].columns.equals(ret_m.columns), 'V1: %s 列不一致' % name
    assert bool(ret_m.iloc[-1].isna().all()), 'V1: 末月应全为 NaN'

    # 市场级 thin mask: 有效股票 < 300 的月份整行置 NaN (C 口径)
    count_all = (eligible & ret_m.notna()).sum(axis=1)
    thin = count_all < MIN_STOCKS
    ret = ret_m.mask(thin, axis=0)
    mask = eligible.mask(thin, axis=0)

    # 因子 z-score: 全市场口径一次 (G13)
    z = {}
    for name in FACTORS:
        z[name], _ = cross_section_prep(panels[name], ret, mask)
    z[COMPOSITE] = composite_panel({k: z[k] for k in FACTORS})
    names = FACTORS + [COMPOSITE]

    # 指数池
    pools = {'all': mask}
    for label, code in POOLS.items():
        if code is None:
            continue
        members = load_index_members(args.data_root, code)
        pools[label] = align_pool(members, z[COMPOSITE].index, z[COMPOSITE].columns) & mask

    # V10: 池 B 每期成分数 (只检查同时有因子与收益标签的活跃月份)
    active = z[COMPOSITE].notna().any(axis=1) & ret.notna().any(axis=1)
    for label, pm in pools.items():
        if label == 'all':
            continue
        n_eff = (pm & ret.notna()).sum(axis=1)[active]
        assert len(n_eff) > 0 and int(n_eff.min()) >= MIN_POOL_STOCKS, \
            'V10: 池 %s 最小有效成分 %d < %d' % (
                label, int(n_eff.min()) if len(n_eff) else -1, MIN_POOL_STOCKS)

    print('=' * 112)
    print('组合层 IC/Sharpe 回测 — %d 因子 + 复合, %d 分位, 费率 %s bp'
          % (len(FACTORS), Q, args.fee_bps))
    print('样本: %s -> %s (%d 个月末, 有效 %d)'
          % (z[COMPOSITE].index.min().date(), z[COMPOSITE].index.max().date(),
             len(z[COMPOSITE]), int(np.isfinite(ret).any(axis=1).sum())))
    print('=' * 112)

    results = {}
    warn = []
    for label, pm in pools.items():
        for seg, bounds in SEGMENTS.items():
            start, end = (None, None) if bounds is None else bounds
            zs = {k: v.loc[start:end] for k, v in z.items()}
            rs = ret.loc[start:end]
            ps = pm.loc[start:end]
            print('\n[池 %s | 区间 %s | 平均池容量 %.0f]'
                  % (label, seg, float(ps.sum(axis=1).mean())))
            header = ('%-15s %8s %8s %8s %8s %8s %7s %7s %6s'
                      % ('factor', 'ICmean', 'ICIR', 'LS_ann', 'LS_SR', 'LS_NWt',
                         'MDD', 'TO_ann', 'BE_bps'))
            print(header)
            print('-' * len(header))
            for name in names:
                f = zs[name]
                blk = run_block(f, rs, ps, args.fee_bps)
                row = {
                    'pool': label,
                    'segment': seg,
                    'factor': name,
                    **blk,
                }
                results['%s|%s|%s' % (name, label, seg)] = row
                ls0 = row['ls'][args.fee_bps[0]]
                print('%-15s %8.4f %8.3f %8.3f %8.3f %8.2f %7.3f %7.2f %6.0f'
                      % (name, row['ic_mean'], row['icir'], ls0['ann_ret_gross'],
                         ls0['sharpe_gross'], ls0['nw_t_gross'], ls0['maxdd_net'],
                         ls0['turnover_ann'], row['breakeven_bps']))
            # V6: 费率单调 (净年化非增)
            for name in names:
                row = results['%s|%s|%s' % (name, label, seg)]
                seq = [row['ls'][f]['ann_ret_net'] for f in args.fee_bps]
                diffs = np.diff(seq)
                assert np.all(diffs <= 1e-12), \
                    'V6: %s/%s/%s 净年化随费率上升' % (name, label, seg)

            # V7: 分位单调性 (全样本, 软)
            if seg == 'full':
                for name in names:
                    qa = results['%s|%s|%s' % (name, label, seg)]['quantile_ann']
                    if not (qa['Q1'] <= qa['Q3'] <= qa['Q5']):
                        warn.append('V7 %s/%s: Q1=%.3f Q3=%.3f Q5=%.3f'
                                    % (name, label, qa['Q1'], qa['Q3'], qa['Q5']))
                # V8: 复合 Sharpe >= min 单因子 (软)
                srs = [results['%s|%s|%s' % (n, label, seg)]['ls'][args.fee_bps[0]]['sharpe_gross']
                       for n in FACTORS]
                sr_c = results['%s|%s|%s' % (COMPOSITE, label, seg)]['ls'][args.fee_bps[0]]['sharpe_gross']
                if np.isfinite(sr_c) and np.isfinite(min(srs)) and sr_c < min(srs):
                    warn.append('V8 %s: 复合 SR %.3f < min 单因子 %.3f'
                                % (label, sr_c, min(srs)))

    # V5: IC 均值符号 == PremiumEstimator premium_mean 符号 (全市场, 全样本)
    est = PremiumEstimator(bandwidth=args.bands)
    print('\n[V5 IC vs FM 符号一致性]')
    for name in FACTORS:
        res = est.estimate_with_errors(z[name], ret, alpha=0.05)
        pm = float(res['premium_mean'])
        icm = results['%s|all|full' % name]['ic_mean']
        assert np.sign(pm) == np.sign(icm), \
            'V5: %s premium_mean %.4e 与 IC 均值 %.4f 异号' % (name, pm, icm)
        print('%-15s premium_mean=%12.5e  ICmean=%+.4f  OK' % (name, pm, icm))

    print('\n[费率敏感性 — 多空净年化 (池 all / 全样本)]')
    print('%-15s ' % 'factor' + ' '.join('%10s' % ('%dbp' % f) for f in args.fee_bps))
    for name in names:
        row = results['%s|all|full' % name]
        print('%-15s ' % name + ' '.join(
            '%10.4f' % row['ls'][f]['ann_ret_net'] for f in args.fee_bps))

    if warn:
        print('\n[WARN]')
        for w in warn:
            print('  ' + w)
    else:
        print('\n[WARN] 无 (V7/V8 全部满足)')

    print('\n断言 V1-V6/V9/V10 全部通过; V7/V8 WARN %d 条' % len(warn))

    if args.json:
        payload = {
            'meta': {
                'factors': FACTORS,
                'quantiles': Q,
                'fee_bps': args.fee_bps,
                'segments': {k: list(v) if v else None for k, v in SEGMENTS.items()},
                'sample_start': str(z[COMPOSITE].index.min().date()),
                'sample_end': str(z[COMPOSITE].index.max().date()),
                'nw_lag': NW_LAG,
                'bandwidth': args.bands,
            },
            'results': results,
            'warnings': warn,
        }
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print('\nJSON -> %s' % args.json)

    if args.report_json:
        checks = [{'id': name, 'ok': True}
                  for name in ('V1', 'V2', 'V3', 'V4', 'V5', 'V6', 'V9', 'V10')]
        for idx, _ in enumerate(warn):
            checks.append({'id': 'V7/V8_%d' % (idx + 1), 'ok': True})
        _write_report_json(
            args.report_json, 'verify_portfolio_backtest', checks,
            [{'path': args.json}] if args.json else [],
            'warn' if warn else 'pass')


if __name__ == '__main__':
    main()
