# -*- coding: utf-8 -*-
"""组合层多头端落地研究 — Q5 多头为何没有超额, 哪些形态能保留 alpha.

背景 (docs/analysis/PORTFOLIO_BACKTEST_VERIFICATION.md):
    全市场 Q5 等权多头年化 ~15.2%, 但相对同权池超额仅 +0.9% (NW t 0.37);
    多空 SR 0.77-1.05 的收益几乎全部来自 Q1 空头腿; 沪深300 内失效.

本脚本回答三个问题:
    Q1 多头端超额是否只是"小市值/流动性"暴露? (sizeNeu / exSmall30 / CW)
    Q2 加入形成期可实施性约束 (停牌/ST/涨停) 后还剩多少? (tradable)
    Q3 不做多头选股、只做"负面剔除"(持有非最差 20%/30%) 能否吃到空头腿 alpha?

数据: E:\\Ashare_data (日频 2020-01-02 -> 2026-01-30)
      stock_suspend ('S' 停牌) / stock_name (含 ST) / stock_high / stock_return
      / stock_ind (行业, 2009-01-05 -> 2023-06-13) / market_value
口径: 月末 z-score (1/99 winsorize) 合成 4 因子; 分位/负面剔除月频调仓;
      基准 = 同一可投资域的同权或市值加权收益; 成本 = 2 * turnover * fee.
校验: V1 权重行和 / V2 可交易变体持仓零违规 / V3 负面剔除不含 Q1 /
      V4 与既有 Q5_EW 对账 / V5 费用单调.
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

from verify_layer3_hac_real import build_eligible, cross_section_prep, month_end
from verify_multifactor_multiyear import (
    build_price_factors,
    load_market,
)
from verify_portfolio_backtest import (
    FACTORS,
    MIN_STOCKS,
    NW_LAG,
    align_pool,
    build_quantile_weights,
    build_turnover,
    composite_panel,
    load_index_members,
    max_drawdown,
    nw_t,
    perf,
)

DATA_ROOT = r"E:\Ashare_data"
Q = 5
FEE_BPS = (0, 10, 20, 30)
FEE_REF = 10
POOLS = {'all': None, 'hs300': '000300'}
SEGMENTS = {
    'full': (None, None),
    'S1': ('2020-02-01', '2022-12-31'),
    'S2': ('2023-01-01', '2025-12-31'),
}
MIN_POOL_STOCKS = 250
CHINEXT_REFORM = pd.Timestamp('2020-08-24')
# 既有报告 (PORTFOLIO_BACKTEST_VERIFICATION.md) 复合因子 Q5_EW:
#   毛年化 16.89%, 10bp 净年化 15.62%, 净超额 +1.34% / NW t 0.48
RECON = {'ann_gross': 0.16894, 'ann_net10': 0.1562,
         'excess_net10': 0.01338, 'excess_t_net10': 0.48}


# ── 可实施性数据 ────────────────────────────────────────────────────────────

def load_implementability(root, close):
    """停牌 / ST / 涨停 / 行业 / 市值 / 流动性 (日频, 对齐 close 网格)."""
    md = Path(root) / 'market_data'
    cols, dates = close.columns, close.index

    suspend = pd.read_pickle(md / 'stock_suspend.pkl')
    suspend.index = pd.to_datetime(suspend.index)
    is_sus = suspend.reindex(index=dates, columns=cols).eq('S')

    name = pd.read_pickle(md / 'stock_name.pkl')
    name.index = pd.to_datetime(name.index)
    name = name.reindex(index=dates, columns=cols)
    # ST / *ST / 退市整理期 (异构复审 P3: 名称含'退'非'ST' 月均 29 只)
    is_st = name.apply(
        lambda s: s.fillna('').str.contains('ST|退', regex=True))

    raw_ret = pd.read_pickle(md / 'stock_return.pkl')
    raw_ret.index = pd.to_datetime(raw_ret.index)
    raw_ret = raw_ret.reindex(index=dates, columns=cols)
    high = pd.read_pickle(md / 'stock_high.pkl')
    high.index = pd.to_datetime(high.index)
    high = high.reindex(index=dates, columns=cols)

    # 涨停阈值: 主板/B股 10%, 创业板 2020-08-24 起 20%, 科创板 20%, 北交所 30%
    # (复审 P3: 面板无 B 股; 北交所前缀 43/83/87/92 — 精确映射替代旧 '4'/'8'/'9' 一刀切)
    thr = np.full((len(dates), len(cols)), 10.0)
    early = np.asarray(dates < CHINEXT_REFORM)
    for j, code in enumerate(cols):
        p2 = code[:2]
        if p2 in ('43', '83', '87', '92'):
            thr[:, j] = 30.0
        elif p2 in ('90', '20'):
            thr[:, j] = 10.0
        elif p2 == '68':
            thr[:, j] = 20.0
        elif p2 == '30':
            thr[early, j] = 10.0
            thr[~early, j] = 20.0
    thr = pd.DataFrame(thr, index=dates, columns=cols)
    # 收盘钉在最高价 + 涨幅达阈值附近 → 视为涨停买不进
    is_lu = (raw_ret >= thr - 0.3) & (close >= high * 0.999)

    ind = pd.read_pickle(md / 'stock_ind.pkl')
    ind.index = pd.to_datetime(ind.index)
    ind = ind.sort_index()
    ind = ind[~ind.index.duplicated(keep='last')]
    return {'suspend': is_sus, 'st': is_st, 'limit_up': is_lu, 'ind': ind}


def last_trading_days(daily_index, panel_index):
    """日历月末标签 -> 该月最后一个真实交易日 (面板 resample 标签为日历月末)."""
    s = pd.Series(daily_index, index=daily_index.to_period('M'))
    last = s.groupby(level=0).max()
    days = panel_index.to_period('M').map(last)
    return pd.DatetimeIndex(days)


def formation_facts(daily, panel_index, columns, close_index):
    """把日频事实对齐到月末形成日 (当月最后一个真实交易日)."""
    days = last_trading_days(close_index, panel_index)
    out = {}
    for key, df in daily.items():
        if key == 'ind':
            continue
        snap = df.loc[days].reindex(columns=columns).fillna(False)
        snap.index = panel_index
        out[key] = snap
    ind = (daily['ind']
           .reindex(index=days, method='ffill')
           .reindex(columns=columns))
    ind.index = panel_index
    out['ind'] = ind
    return out


# ── 组合构造 ────────────────────────────────────────────────────────────────

def _normalize(sel, cap=None):
    w = sel.astype(float)
    if cap is not None:
        w = w * cap.where(cap > 0)
    den = w.sum(axis=1).replace(0.0, np.nan)
    return w.div(den, axis=0).fillna(0.0)


def weights_top_quantile(f, ret, universe, q=Q, cap=None):
    """f 最高 1/q 分位, 等权或市值加权."""
    valid = f.notna() & ret.notna() & universe
    ranks = f.where(valid).rank(axis=1, pct=True)
    sel = ranks > 1.0 - 1.0 / q
    return _normalize(sel, cap if cap is not None else None)


def weights_top_n(f, ret, universe, n, cap=None):
    valid = f.notna() & ret.notna() & universe
    ranks = f.where(valid).rank(axis=1, ascending=False)
    sel = ranks <= n
    return _normalize(sel, cap if cap is not None else None)


def weights_exclude_bottom(f, ret, universe, frac=1.0 / Q, cap=None):
    """负面剔除: 剔除 f 最低 frac 分位, 其余等权/市值加权."""
    valid = f.notna() & ret.notna() & universe
    ranks = f.where(valid).rank(axis=1, pct=True)
    sel = ranks > frac
    return _normalize(sel, cap if cap is not None else None)


def weights_industry_neutral(f, ret, universe, ind_m, q=Q):
    """行业内分位选前 1/q, 行业内等权; 行业权重随池分布 (相对中性)."""
    valid = f.notna() & ret.notna() & universe
    rank = pd.DataFrame(np.nan, index=f.index, columns=f.columns)
    for ts in f.index:
        v = valid.loc[ts]
        if not bool(v.any()):
            continue
        row = f.loc[ts].where(v)
        grp = ind_m.loc[ts].reindex(f.columns)
        rank.loc[ts] = row.groupby(grp).rank(pct=True)
    sel = rank > 1.0 - 1.0 / q
    return _normalize(sel)


def residualize(f, x_panel, universe):
    """横截面 OLS: f = a + b*x + eps, 返回残差 (规模/流动性中性因子)."""
    out = pd.DataFrame(np.nan, index=f.index, columns=f.columns)
    for ts in f.index:
        y = f.loc[ts]
        x = x_panel.loc[ts]
        ok = (y.notna() & x.notna() & universe.loc[ts]).values
        if ok.sum() < 100:
            continue
        yv, xv = y.values[ok], x.values[ok]
        X = np.column_stack([np.ones_like(xv), xv])
        beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
        out.loc[ts, ok] = yv - X @ beta
    return out


# ── 评价 ────────────────────────────────────────────────────────────────────

def bench_ew(universe, ret):
    return ret.where(universe).mean(axis=1)


def bench_vw(universe, ret, cap):
    w = cap.where(universe & ret.notna() & (cap > 0))
    w = w.div(w.sum(axis=1).replace(0.0, np.nan), axis=0).fillna(0.0)
    return (w * ret.fillna(0.0)).sum(axis=1)


def eval_portfolio(w, ret, bench, fees, label):
    r = (w * ret.fillna(0.0)).sum(axis=1)
    t = build_turnover(w)
    bench = bench.reindex(r.index)
    ex = r - bench
    ok = np.isfinite(r.values) & np.isfinite(bench.values)
    n = int(ok.sum())
    nan = float('nan')
    long_metrics = {str(f): perf(r.values, t, f) for f in fees}
    n_hold = (w > 0).sum(axis=1)
    n_hold = n_hold[n_hold > 0]
    out = {
        'label': label,
        'n_months': n,
        'n_hold_mean': float(n_hold.mean()) if len(n_hold) else nan,
        'bench_ann': float(np.nanmean(bench.values[ok]) * 12) if n else nan,
        'bench_vol': float(np.nanstd(bench.values[ok], ddof=1) * np.sqrt(12))
        if n > 2 else nan,
        'ann_ret_gross': long_metrics[str(fees[0])]['ann_ret_gross'],
        'excess_ann_gross': float(np.nanmean(ex.values[ok]) * 12) if n else nan,
        'excess_vol': float(np.nanstd(ex.values[ok], ddof=1) * np.sqrt(12))
        if n > 2 else nan,
        'ir_gross': nan,
        'excess_nw_t': nw_t(ex.values[ok]),
        'long': long_metrics,
        'excess_ann_net': {},
        'excess_nw_t_net': {},
    }
    if n > 2 and out['excess_vol'] > 0:
        out['ir_gross'] = float(out['excess_ann_gross'] / out['excess_vol'])
    out['bench_sharpe'] = (
        float(out['bench_ann'] / out['bench_vol'])
        if np.isfinite(out['bench_vol']) and out['bench_vol'] > 0 else nan)
    out['bench_mdd'] = max_drawdown(bench.values[ok])
    ex_valid = ex.values[ok]
    out['excess_ar1'] = (
        float(np.corrcoef(ex_valid[:-1], ex_valid[1:])[0, 1])
        if n > 3 else nan)
    out['excess_nw_t_lag6'] = nw_t(ex_valid, lag=6)
    out['excess_nw_t_lag12'] = nw_t(ex_valid, lag=12)
    out['excess_series'] = [float(v) if np.isfinite(v) else None
                            for v in ex.values]
    for fee in fees:
        net = ex_valid - 2.0 * t[ok] * fee / 1e4
        out['excess_ann_net'][str(fee)] = float(np.nanmean(net) * 12)
        out['excess_nw_t_net'][str(fee)] = nw_t(net)
    return out


def holdings_diagnostics(w, facts, mv_rank, amt_rank, amt_m, universe):
    """持仓结构: 违规份额 / 市值与流动性分位 / 成交额容量比."""
    if w.empty:
        return {}
    rows = []
    for ts in w.index:
        row = w.loc[ts]
        if row.sum() <= 0:
            continue
        held_amt = amt_m.loc[ts].where(row > 0)
        pool_amt = amt_m.loc[ts].where(universe.loc[ts])
        ratio = (float(held_amt.median() / pool_amt.median())
                 if pool_amt.median() and np.isfinite(pool_amt.median()) else np.nan)
        rows.append({
            'n_hold': float((row > 0).sum()),
            'st': float((row * facts['st'].loc[ts]).sum()),
            'suspend': float((row * facts['suspend'].loc[ts]).sum()),
            'limit_up': float((row * facts['limit_up'].loc[ts]).sum()),
            'mv_pct': float((row * mv_rank.loc[ts]).sum()),
            'amt_pct': float((row * amt_rank.loc[ts]).sum()),
            'small30': float((row * (mv_rank.loc[ts] <= 0.3)).sum()),
            'amt_med_ratio': ratio,
        })
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    return {k: float(df[k].mean()) for k in df.columns}


# ── 流程 ────────────────────────────────────────────────────────────────────

def build_variants():
    """变体定义: kind / 参数 / 适用池 / 区间."""
    core_segments = ('full', 'S1', 'S2')
    return [
        # 基线
        dict(name='Q5_EW', kind='qtop', q=5, weight='ew', pools=('all', 'hs300'),
             segments=core_segments, diag=True),
        dict(name='Q5_CW', kind='qtop', q=5, weight='vw', pools=('all', 'hs300'),
             segments=core_segments),
        # 可实施性
        dict(name='Q5_EW_tradable', kind='qtop', q=5, weight='ew', tradable=True,
             pools=('all', 'hs300'), segments=core_segments, diag=True),
        dict(name='Q5_CW_tradable', kind='qtop', q=5, weight='vw', tradable=True,
             pools=('all',), segments=('full',)),
        # 集中度
        dict(name='Q10_EW', kind='qtop', q=10, weight='ew', pools=('all', 'hs300'),
             segments=core_segments),
        dict(name='Top100_EW', kind='topn', n=100, weight='ew', pools=('all',),
             segments=('full',)),
        # 规模/风格中性
        dict(name='Q5_EW_exSmall30', kind='qtop', q=5, weight='ew', ex_small=0.3,
             pools=('all',), segments=('full',)),
        dict(name='Q5_EW_sizeNeu', kind='qtop', q=5, weight='ew', size_neutral=True,
             pools=('all', 'hs300'), segments=('full',)),
        dict(name='Q5_EW_liqNeu', kind='qtop', q=5, weight='ew', liq_neutral=True,
             pools=('all',), segments=('full',)),
        dict(name='Q5_EW_exIlliq30', kind='qtop', q=5, weight='ew', ex_illiq=0.3,
             pools=('all',), segments=('full',)),
        dict(name='Q5_EW_indNeu', kind='qtop', q=5, weight='ew', ind_neutral=True,
             pools=('all',), segments=('S1',)),   # 行业数据止于 2023-06
        # 负面剔除
        dict(name='exQ1_EW', kind='exbottom', frac=0.2, weight='ew',
             pools=('all', 'hs300'), segments=core_segments, diag=True),
        dict(name='exQ1_EW_tradable', kind='exbottom', frac=0.2, weight='ew',
             tradable=True, pools=('all', 'hs300'), segments=core_segments,
             diag=True),
        dict(name='exQ1_CW', kind='exbottom', frac=0.2, weight='vw',
             pools=('all', 'hs300'), segments=('full', 'S1', 'S2')),
        dict(name='exQ1_sizeNeu', kind='exbottom', frac=0.2, weight='ew',
             size_neutral=True, pools=('all',), segments=('full',)),
        dict(name='exQ1_liqNeu', kind='exbottom', frac=0.2, weight='ew',
             liq_neutral=True, pools=('all',), segments=('full',)),
        dict(name='exBottom30_EW', kind='exbottom', frac=0.3, weight='ew',
             pools=('all',), segments=('full',)),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-root', default=DATA_ROOT)
    ap.add_argument('--fee-bps', type=int, nargs='+', default=list(FEE_BPS))
    ap.add_argument('--json', default=str(ROOT / 'out' / 'long_side_research.json'))
    args = ap.parse_args()
    fees = args.fee_bps

    close, adj, amount, mv, list_date = load_market(args.data_root)
    adj_price = close * adj
    eligible = month_end(build_eligible(close, list_date).astype(float)) > 0
    price_daily = build_price_factors(adj_price, amount, mv)
    panels = {k: month_end(v) for k, v in price_daily.items()}
    price_m = month_end(adj_price)
    ret_m = (price_m.shift(-1) / price_m - 1.0).mask(lambda d: d.abs() > 1.0)

    count_all = (eligible & ret_m.notna()).sum(axis=1)
    thin = count_all < MIN_STOCKS
    ret = ret_m.mask(thin, axis=0)
    mask = eligible.mask(thin, axis=0)

    # 因子 z-score 与既有报告完全一致 (G13: 全市场口径一次)
    z = {}
    for name in FACTORS:
        z[name], _ = cross_section_prep(panels[name], ret, mask)
    z['composite'] = composite_panel({k: z[k] for k in FACTORS})
    factor = z['composite']
    fidx, fcols = factor.index, factor.columns

    # 可实施性事实 (月末形成日)
    impl = load_implementability(args.data_root, close)
    facts = formation_facts({k: impl[k] for k in ('suspend', 'st', 'limit_up', 'ind')},
                            fidx, fcols, close.index)
    tradable = ~(facts['st'] | facts['suspend'] | facts['limit_up'])

    mv_m = month_end(mv).reindex(index=fidx, columns=fcols)
    log_mv = np.log(mv_m.where(mv_m > 0))
    mv_rank = mv_m.where(mask).rank(axis=1, pct=True)
    amt_daily = amount.where(amount > 0).rolling(21, min_periods=10).mean()
    amt_m = month_end(amt_daily).reindex(index=fidx, columns=fcols)
    amt_rank = amt_m.where(mask).rank(axis=1, pct=True)
    log_amt = np.log(amt_m.where(amt_m > 0))
    size_ok = mv_rank > 0.3
    liq_ok = amt_rank > 0.3

    # 因子变体面板
    factor_variants = {
        'base': factor,
        'size_neu': residualize(factor, log_mv, mask),
        'liq_neu': residualize(factor, log_amt, mask),
    }

    # 池
    pools = {'all': mask}
    for label, code in POOLS.items():
        if code is None:
            continue
        members = load_index_members(args.data_root, code)
        pools[label] = align_pool(members, fidx, fcols) & mask

    # V10: 池容量
    active = factor.notna().any(axis=1) & ret.notna().any(axis=1)
    for label, pm in pools.items():
        neff = (pm & ret.notna()).sum(axis=1)[active]
        assert len(neff) > 0 and int(neff.min()) >= MIN_POOL_STOCKS, \
            'V10: 池 %s 最小有效成分 %d' % (label, int(neff.min()))

    print('=' * 118)
    print('组合层多头端落地研究 — 4 因子复合, 月频, 费率 %s bp' % list(fees))
    print('样本 %s -> %s (%d 个月末), 池 %s'
          % (fidx.min().date(), fidx.max().date(), len(fidx), list(pools)))
    print('=' * 118)

    results, diag, quantiles = {}, {}, {}
    for spec in build_variants():
        name = spec['name']
        if spec.get('tradable'):
            uni_extra = tradable
        elif spec.get('ex_small'):
            uni_extra = size_ok
        elif spec.get('ex_illiq'):
            uni_extra = liq_ok
        else:
            uni_extra = pd.DataFrame(True, index=fidx, columns=fcols)
        if spec.get('size_neutral'):
            fpanel = factor_variants['size_neu']
        elif spec.get('liq_neutral'):
            fpanel = factor_variants['liq_neu']
        else:
            fpanel = factor_variants['base']

        for pool_label in spec['pools']:
            base_pool = pools[pool_label]
            uni = base_pool & uni_extra
            for seg in spec['segments']:
                start, end = SEGMENTS[seg]
                sl = slice(start, end)
                f = fpanel.loc[sl]
                r = ret.loc[sl]
                u = uni.loc[sl]
                cap = mv_m.loc[sl]
                cap_ok = cap.where(u & (cap > 0))

                if spec['kind'] == 'qtop':
                    if spec.get('ind_neutral'):
                        w = weights_industry_neutral(
                            f, r, u, facts['ind'].loc[sl], q=spec['q'])
                    else:
                        w = weights_top_quantile(
                            f, r, u, q=spec['q'],
                            cap=cap_ok if spec['weight'] == 'vw' else None)
                elif spec['kind'] == 'topn':
                    w = weights_top_n(
                        f, r, u, spec['n'],
                        cap=cap_ok if spec['weight'] == 'vw' else None)
                else:
                    w = weights_exclude_bottom(
                        f, r, u, frac=spec.get('frac', 1.0 / Q),
                        cap=cap_ok if spec['weight'] == 'vw' else None)

                # V1: 权重行和 ∈ {0, 1}, 非负
                rs = w.sum(axis=1)
                assert bool(((np.isclose(rs, 0.0) | np.isclose(rs, 1.0)).all())), \
                    'V1: %s/%s/%s 行和越界' % (name, pool_label, seg)
                assert float(w.values.min()) >= -1e-12, 'V1: 负权重'

                # V2: 可交易变体持仓零违规
                if spec.get('tradable') and bool((w > 0).any().any()):
                    held = w > 0
                    for key in ('st', 'suspend', 'limit_up'):
                        bad = (held & facts[key].loc[sl]).sum().sum()
                        assert bad == 0, \
                            'V2: %s/%s/%s 持仓含 %s %d 处' % (
                                name, pool_label, seg, key, int(bad))

                # V3: 负面剔除不含最差分位
                if spec['kind'] == 'exbottom':
                    valid = f.notna() & r.notna() & u
                    rk = f.where(valid).rank(axis=1, pct=True)
                    bad = ((w > 0) & (rk <= spec.get('frac', 1.0 / Q))).sum().sum()
                    assert bad == 0, \
                        'V3: %s/%s/%s 含被剔除标的 %d 处' % (
                            name, pool_label, seg, int(bad))

                # 基准: 同一可投资域
                if spec['weight'] == 'vw':
                    bench = bench_vw(u, r, cap)
                else:
                    bench = bench_ew(u, r)

                key = '%s|%s|%s' % (name, pool_label, seg)
                results[key] = eval_portfolio(w, r, bench, fees, name)
                results[key].update({
                    'pool': pool_label, 'segment': seg, 'variant': name,
                    'universe_mean': float(u.sum(axis=1).mean()),
                    'weight': spec['weight'],
                })
                if spec.get('diag'):
                    diag['%s|%s|%s' % (name, pool_label, seg)] = \
                        holdings_diagnostics(w, facts, mv_rank.loc[sl],
                                             amt_rank.loc[sl], amt_m.loc[sl], u)

    # 分位年化 (基线上下文)
    for pool_label, pm in pools.items():
        wq = build_quantile_weights(factor.where(pm), ret, Q)
        quantiles[pool_label] = {
            k: float((wq[k] * ret.fillna(0.0)).sum(axis=1).mean() * 12)
            for k in wq}

    # 池的违规结构 (对照)
    pool_diag = {}
    for pool_label, pm in pools.items():
        pb = pm.eq(True)
        d = {}
        for key in ('st', 'suspend', 'limit_up'):
            d[key] = float((facts[key] & pb).sum().sum() / pb.values.sum())
        d['small30'] = float(((mv_rank <= 0.3) & pb).sum().sum() / pb.values.sum())
        d['mv_pct'] = float(mv_rank.where(pb).mean(axis=1).mean())
        d['amt_pct'] = float(amt_rank.where(pb).mean(axis=1).mean())
        pool_diag[pool_label] = d

    # V4: 与既有报告对账 (复合因子 Q5_EW, 全市场全样本)
    recon = results['Q5_EW|all|full']
    l10 = recon['long'][str(FEE_REF)]
    checks = {
        'ann_gross': (recon['ann_ret_gross'], RECON['ann_gross'], 0.002),
        'ann_net10': (l10['ann_ret_net'], RECON['ann_net10'], 0.002),
        'excess_net10': (recon['excess_ann_net'][str(FEE_REF)],
                         RECON['excess_net10'], 0.002),
        'excess_t_net10': (recon['excess_nw_t_net'][str(FEE_REF)],
                           RECON['excess_t_net10'], 0.05),
    }
    print('\n[V4 对账 — 复合因子 Q5_EW | all | full]')
    recon_warn = []
    for key, (got, ref, tol) in checks.items():
        flag = 'OK' if abs(got - ref) <= tol else 'WARN'
        print('  %-15s 本脚本 %+.4f  既有报告 %+.4f  差 %+.4f  %s'
              % (key, got, ref, got - ref, flag))
        if flag == 'WARN':
            recon_warn.append('V4 %s 偏差 %.4f' % (key, got - ref))

    # 打印: 全样本变体表
    for pool_label in pools:
        print('\n' + '=' * 122)
        print('[池 %s] 全样本变体对比 — 基准为同一可投资域' % pool_label)
        print('=' * 122)
        hdr = ('%-20s %7s %8s %8s %8s %7s %7s %6s %8s %7s %6s %6s'
               % ('variant', 'n_hold', 'long_ann', 'bench', 'ex_ann',
                  'ex_IR', 'ex_t', 'ex_t10', 'ex10bp', 'MDD', 'TO', 'SR10'))
        print(hdr)
        print('-' * len(hdr))
        for spec in build_variants():
            if pool_label not in spec['pools'] or 'full' not in spec['segments']:
                continue
            row = results['%s|%s|full' % (spec['name'], pool_label)]
            l10 = row['long'][str(FEE_REF)]
            print('%-20s %7.0f %8.4f %8.4f %+8.4f %7.3f %7.2f %6.2f %+8.4f %7.3f %6.2f %6.3f'
                  % (row['variant'], row['n_hold_mean'], row['ann_ret_gross'],
                     row['bench_ann'], row['excess_ann_gross'], row['ir_gross'],
                     row['excess_nw_t'], row['excess_nw_t_net'][str(FEE_REF)],
                     row['excess_ann_net'][str(FEE_REF)],
                     l10['maxdd_net'], l10['turnover_ann'],
                     l10['sharpe_net']))

    print('\n[分位年化 — 复合因子, 全样本]')
    for pool_label, qa in quantiles.items():
        print('  池 %-6s ' % pool_label +
              '  '.join('%s %+.4f' % (k, v) for k, v in qa.items()))

    print('\n[持仓结构 — 违规份额 / 市值与流动性分位]')
    for label, d in diag.items():
        if not d or not label.endswith('full'):
            continue
        name, pool_label = label.split('|')[0], label.split('|')[1]
        print('  %-22s %-6s n=%4.0f  ST %.2f%%  停牌 %.2f%%  涨停 %.2f%%  '
              '小市值30 %.1f%%  市值分位 %.3f  流动性分位 %.3f  成交额比 %.2f'
              % (name, pool_label, d['n_hold'],
                 d['st'] * 100, d['suspend'] * 100, d['limit_up'] * 100,
                 d['small30'] * 100, d['mv_pct'], d['amt_pct'],
                 d.get('amt_med_ratio', np.nan)))
    for pool_label, d in pool_diag.items():
        print('  [池 %-18s]       ST %.2f%%  停牌 %.2f%%  涨停 %.2f%%  '
              '小市值30 %.1f%%  市值分位 %.3f  流动性分位 %.3f'
              % (pool_label, d['st'] * 100, d['suspend'] * 100,
                 d['limit_up'] * 100, d['small30'] * 100, d['mv_pct'], d['amt_pct']))

    print('\n[子区间稳健性 — 多头超额 / NW t]')
    seg_rows = [s for s in build_variants()
                if 'S1' in s['segments'] and s['pools'][0] == 'all']
    print('%-20s ' % 'variant' + ' '.join(
        '%22s' % ('%s: ex / t' % seg) for seg in ('S1', 'S2')))
    for spec in seg_rows:
        name = spec['name']
        cells = []
        for seg in ('S1', 'S2'):
            if seg not in spec['segments']:
                cells.append('%22s' % '-')
                continue
            row = results['%s|all|%s' % (name, seg)]
            cells.append('%22s' % ('%+.4f / %.2f' % (
                row['excess_ann_gross'], row['excess_nw_t'])))
        print('%-20s ' % name + ' '.join(cells))

    print('\n[成本敏感性 — 净超额年化 (全市场全样本)]')
    core = ['Q5_EW', 'Q5_EW_tradable', 'Q5_CW', 'Q5_EW_liqNeu',
            'Q5_EW_exIlliq30', 'exQ1_EW', 'exQ1_EW_tradable',
            'exQ1_liqNeu']
    print('%-20s ' % 'variant' + ' '.join('%9s' % ('%dbp' % f) for f in fees))
    for name in core:
        row = results['%s|all|full' % name]
        print('%-20s ' % name + ' '.join(
            '%+9.4f' % row['excess_ann_net'][str(f)] for f in fees))

    # V5: 费用单调 (净超额随费率非增)
    for key, row in results.items():
        seq = [row['excess_ann_net'][str(f)] for f in fees]
        assert np.all(np.diff(seq) <= 1e-12), 'V5: %s 净超额随费率上升' % key

    if recon_warn:
        print('\n[WARN] ' + '; '.join(recon_warn))
    print('\n断言 V1-V3/V5/V10 通过; V4 对账 %s'
          % ('全部在容差内' if not recon_warn else '存在偏差'))

    # JSON
    payload = {
        'meta': {
            'factors': FACTORS,
            'quantiles': Q,
            'fee_bps': list(fees),
            'segments': {k: list(v) if v[0] else None
                         for k, v in SEGMENTS.items()},
            'sample_start': str(fidx.min().date()),
            'sample_end': str(fidx.max().date()),
            'n_months': len(fidx),
            'nw_lag': NW_LAG,
            'pools': list(pools),
            'recon': {k: {'got': float(got), 'ref': float(ref),
                          'tol': float(tol)}
                      for k, (got, ref, tol) in checks.items()},
        },
        'results': {k: {kk: vv for kk, vv in v.items()}
                    for k, v in results.items()},
        'quantiles': quantiles,
        'diagnostics': diag,
        'pool_diagnostics': pool_diag,
        'warnings': recon_warn,
    }
    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding='utf-8')
    print('JSON -> %s' % out)


if __name__ == '__main__':
    main()
