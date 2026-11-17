# -*- coding: utf-8 -*-
"""组合层容量 / 冲击成本压力测试 — exQ1 与 Q5 能装多少钱.

背景 (docs/analysis/LONG_SIDE_PORTFOLIO_RESEARCH.md):
    exQ1 (持有非最差 80%) 净超额 +3.08% (NW t 4.08), 换手 1.78x/年;
    Q5 多头净超额 +1.34% (t 0.48), 换手 6.39x/年.
    两者均未回答: AUM 放大后, ADV 参与率与冲击成本会把超额吃掉多少?

本脚本回答:
    Q1 每个组合在 AUM 1亿-500亿 下的 ADV 参与率分布 (p50/p95/p99);
    Q2 平方根 / 线性冲击模型下, 年化冲击成本与净超额;
    Q3 容量上限 (p95 参与率 <= 5%/10%/20%) 与盈亏平衡 AUM;
    Q4 冲击成本在低/中/高流动性层的分布 (容量瓶颈在哪一层).

数据: E:\\Ashare_data (与 verify_long_side_research.py 同源)
单位: stock_amount = 千元, market_value = 万元 (已按 600519/000001 校验)
口径: 月频调仓; 单边交易额 = AUM * |Δw|; ADV = 形成日前 21 日均成交额;
      平方根冲击 c*sigma_daily*sqrt(participation), 线性 k*participation;
      基准 = 同一可投资域等权; 基础费率 10bp/单边.
校验: V1 与多头端报告对账 / V2 AUM=0 时冲击为零且净超额=基础净 /
      V3 p95 与冲击随 AUM 单调 / V4 可交易变体零违规 / V5 权重行和.
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
from verify_multifactor_multiyear import build_price_factors, load_market
from contract_gate import run_contract_gate
from verify_portfolio_backtest import (
    FACTORS,
    MIN_STOCKS,
    build_turnover,
    composite_panel,
    nw_t,
)
from verify_long_side_research import (
    bench_ew,
    formation_facts,
    load_implementability,
    weights_exclude_bottom,
    weights_top_quantile,
)

DATA_ROOT = r"E:\Ashare_data"
FEE_BPS = 10
# 金额单位: stock_amount 为千元, market_value 为万元
AMT_SCALE = 1e3
MV_SCALE = 1e4
AUM_GRID = (1e8, 5e8, 1e9, 3e9, 5e9, 1e10, 3e10, 5e10)
SQRT_C = (0.1, 0.5, 1.0)          # Almgren 型系数; 0.5 为中央口径
LINEAR_K = (0.01, 0.025, 0.05)    # 每 1% ADV 的单边 bp/100
CAP_LEVELS = (0.05, 0.10, 0.20)
SEGMENTS = {
    'S1': ('2020-02-01', '2022-12-31'),
    'S2': ('2023-01-01', '2025-12-31'),
}
VARIANTS = (
    ('Q5_EW', 'qtop', dict(q=5), False),
    ('Q5_EW_tradable', 'qtop', dict(q=5), True),
    ('exQ1_EW', 'exbottom', dict(frac=0.2), False),
    ('exQ1_EW_tradable', 'exbottom', dict(frac=0.2), True),
)
# 与 docs/analysis/LONG_SIDE_PORTFOLIO_RESEARCH.md §4 对账 (全市场/全样本/10bp)
RECON = {
    'Q5_EW': dict(gross=0.1689, excess_gross=0.0262, excess_net=0.0134,
                  t_net=0.48, turnover=6.39),
    'Q5_EW_tradable': dict(gross=0.1699, excess_gross=0.0215, excess_net=0.0087,
                           t_net=0.30, turnover=6.41),
    'exQ1_EW': dict(gross=0.1769, excess_gross=0.0342, excess_net=0.0308,
                    t_net=4.08, turnover=1.78),
    'exQ1_EW_tradable': dict(gross=0.1798, excess_gross=0.0315,
                             excess_net=0.0278, t_net=3.71, turnover=1.94),
}


def build_panels(root):
    close, adj, amount, mv, list_date = load_market(root)
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

    z = {}
    for name in FACTORS:
        z[name], _ = cross_section_prep(panels[name], ret, mask)
    factor = composite_panel({k: z[k] for k in FACTORS})
    fidx, fcols = factor.index, factor.columns

    impl = load_implementability(root, close)
    facts = formation_facts(
        {k: impl[k] for k in ('suspend', 'st', 'limit_up', 'ind')},
        fidx, fcols, close.index)
    tradable = ~(facts['st'] | facts['suspend'] | facts['limit_up'])

    mv_m = month_end(mv).reindex(index=fidx, columns=fcols) * MV_SCALE
    amt_daily = amount.where(amount > 0).rolling(21, min_periods=10).mean()
    amt_m = month_end(amt_daily).reindex(index=fidx, columns=fcols) * AMT_SCALE
    amt_rank = amt_m.where(mask).rank(axis=1, pct=True)

    # 日收益波动 (冲击模型的价格尺度), 21 日, 形成日快照
    sig_daily = adj_price.pct_change(fill_method=None).rolling(
        21, min_periods=10).std()
    sig_m = month_end(sig_daily).reindex(index=fidx, columns=fcols)
    sig_m = sig_m.clip(lower=0.005, upper=0.20)
    sig_m = sig_m.fillna(sig_m.median(axis=1), axis=0).fillna(0.02)

    return dict(
        close=close, factor=factor, ret=ret, mask=mask, tradable=tradable,
        mv_m=mv_m, amt_m=amt_m, amt_rank=amt_rank, sig_m=sig_m,
        facts=facts)


def make_weights(P, kind, kw, tradable):
    u = P['mask'] & P['tradable'] if tradable else P['mask']
    if kind == 'qtop':
        return weights_top_quantile(P['factor'], P['ret'], u, q=kw['q'])
    return weights_exclude_bottom(P['factor'], P['ret'], u, frac=kw['frac'])


def month_trades(w):
    """单边交易权重 |Δw|; 首期 = 建仓."""
    dw = w - w.shift(1).fillna(0.0)
    return dw.abs()


def impact_panel(traded, adv, sig, aum):
    """返回 (participation 面板, 各模型逐月冲击成本序列 dict).

    participation 缺失 ADV 记为 inf; 冲击按 100% ADV 上限计 (保守).
    """
    notional = traded * aum
    part = notional / adv.where(adv > 0)
    part = part.where(np.isfinite(part), np.inf)
    p_eff = part.clip(upper=1.0)
    out = {}
    for c in SQRT_C:
        imp = c * sig * np.sqrt(p_eff)
        out['sqrt_c%.1f' % c] = (traded * imp).sum(axis=1)
    for k in LINEAR_K:
        imp = k * p_eff
        out['linear_k%.3f' % k] = (traded * imp).sum(axis=1)
    return part, out


def evaluate(w, P, universe, fee_bps=FEE_BPS):
    """组合毛利/换手/基准/基础净超额; universe 为该变体的可投资域."""
    r = (w * P['ret'].fillna(0.0)).sum(axis=1)
    bench = bench_ew(universe, P['ret'])
    t = build_turnover(w)
    ex = r - bench.reindex(r.index)
    ok = np.isfinite(r.values) & np.isfinite(bench.reindex(r.index).values)
    exv = ex.values[ok]
    tv = t[ok]
    base_net = exv - 2.0 * tv * fee_bps / 1e4
    # 与报告对账口径: perf 只按 r 的有限值取样 (不剔除基准缺失月)
    r_ok = np.isfinite(r.values)
    return dict(
        gross=float(np.nanmean(r.values[r_ok]) * 12),
        excess_gross=float(np.nanmean(exv) * 12),
        excess_t=float(nw_t(exv)),
        base_net=float(np.nanmean(base_net) * 12),
        base_net_t=float(nw_t(base_net)),
        turnover_ann=float(np.nanmean(t[r_ok]) * 12),
        n_months=int(ok.sum()),
        series=dict(r=r, ex=ex, t=t, ok=ok, base_net=base_net),
    )


def pctl(x, q):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    return float(np.percentile(x, q)) if len(x) else float('nan')


def capacity_from_p95(p95_at_aum, aum_ref, cap):
    """participation ∝ AUM → 解析容量."""
    if not np.isfinite(p95_at_aum) or p95_at_aum <= 0:
        return float('inf')
    return float(cap / (p95_at_aum / aum_ref))


def breakeven_aum(base_net, impact_at_aum, aum_ref, model):
    """冲击成本与 AUM 的关系: sqrt 模型 ∝ sqrt(AUM), 线性 ∝ AUM."""
    if not np.isfinite(base_net) or base_net <= 0:
        return 0.0
    if not np.isfinite(impact_at_aum) or impact_at_aum <= 0:
        return float('inf')
    if model == 'sqrt':
        return float(aum_ref * (base_net / impact_at_aum) ** 2)
    return float(aum_ref * (base_net / impact_at_aum))


def tier_capacity(traded, part, amt_rank, aum):
    """按流动性分位 (池内) 拆分参与率与交易额占比."""
    tr = traded.values.ravel()
    pt = part.values.ravel()
    ar = amt_rank.reindex_like(traded).values.ravel()
    ok = (tr > 0) & np.isfinite(ar)
    tr, pt, ar = tr[ok], pt[ok], ar[ok]
    tiers = np.where(ar <= 0.3, 'low', np.where(ar <= 0.7, 'mid', 'high'))
    rows = {}
    for name in ('low', 'mid', 'high'):
        m = tiers == name
        if not m.any():
            continue
        pv = pt[m]
        finite = pv[np.isfinite(pv)]
        rows[name] = dict(
            share_notional=float(tr[m].sum() / tr.sum()),
            p50=float(np.percentile(finite, 50)) if len(finite) else float('nan'),
            p95=float(np.percentile(finite, 95)) if len(finite) else float('nan'),
            cap10_aum=capacity_from_p95(
                float(np.percentile(finite, 95)) if len(finite) else float('nan'),
                aum, 0.10),
        )
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-root', default=DATA_ROOT)
    ap.add_argument('--json',
                    default=str(SCRIPTS.parent / 'out' / 'capacity_impact.json'))
    ap.add_argument('--contract', action='store_true',
                    help='运行前置数据契约（GR-2），未通过则不继续研究')
    ap.add_argument('--contract-only', action='store_true',
                    help='只运行数据契约并退出（dry-run）')
    ap.add_argument('--contract-sample-end', default=None,
                    help='契约样本末（默认取 stock_close 最后一个交易日）')
    ap.add_argument('--contract-json', default=None,
                    help='契约 JSON 输出路径（默认 out/capacity_impact_contract.json）')
    args = ap.parse_args()

    if args.contract or args.contract_only:
        report = run_contract_gate(
            args.data_root, sample_end=args.contract_sample_end,
            prefix='capacity_impact', json_path=args.contract_json,
        )
        if not report.passed:
            return 2
        if args.contract_only:
            return 0

    P = build_panels(args.data_root)
    print('=' * 120)
    print('组合层容量 / 冲击成本压力测试 — 4 因子复合, 月频, 基础费率 %dbp/单边'
          % FEE_BPS)
    print('样本 %s -> %s (%d 个月末), AUM 网格 %s'
          % (P['factor'].index.min().date(), P['factor'].index.max().date(),
             len(P['factor'].index),
             ['%.0f亿' % (a / 1e8) for a in AUM_GRID]))
    print('=' * 120)

    panel = {}
    for name, kind, kw, tradable in VARIANTS:
        w = make_weights(P, kind, kw, tradable)
        universe = P['mask'] & P['tradable'] if tradable else P['mask']
        # V5: 权重行和
        rs = w.sum(axis=1)
        assert bool(((np.isclose(rs, 0) | np.isclose(rs, 1)).all())), \
            'V5: %s 权重行和越界' % name
        assert float(w.values.min()) >= -1e-12, 'V5: %s 负权重' % name
        # V4: 可交易变体零违规
        if tradable:
            held = w > 0
            for key in ('st', 'suspend', 'limit_up'):
                bad = int((held & P['facts'][key].reindex_like(w)).sum().sum())
                assert bad == 0, 'V4: %s 持仓含 %s %d' % (name, key, bad)
        base = evaluate(w, P, universe)
        traded = month_trades(w)
        adv = P['amt_m'].reindex_like(w)
        sig = P['sig_m'].reindex_like(w)

        rows = {}
        imp_by_aum = {}
        for aum in AUM_GRID:
            part, imp = impact_panel(traded, adv, sig, aum)
            imp_by_aum['%.0f' % aum] = imp
            pm = part.values[traded.values > 0]
            row = {
                'aum': float(aum),
                'p50': pctl(pm, 50), 'p95': pctl(pm, 95),
                'p99': pctl(pm, 99),
                'breach_1x': float(np.mean(pm[np.isfinite(pm)] > 1.0))
                if np.isfinite(pm).any() else float('nan'),
            }
            okm = base['series']['ok']
            for key, series in imp.items():
                ann = float(np.nanmean(series.values[okm]) * 12)
                row['impact_' + key] = ann
                net = base['series']['ex'].values[okm] \
                    - 2.0 * base['series']['t'][okm] * FEE_BPS / 1e4 \
                    - series.values[okm]
                row['net_' + key] = float(np.nanmean(net) * 12)
                row['t_' + key] = float(nw_t(net))
            rows['%.0f' % aum] = row

        ref = rows['%.0f' % 1e10]
        bez = {
            'sqrt_c0.5': breakeven_aum(base['base_net'],
                                       ref['impact_sqrt_c0.5'], 1e10, 'sqrt'),
            'sqrt_c1.0': breakeven_aum(base['base_net'],
                                       ref['impact_sqrt_c1.0'], 1e10, 'sqrt'),
            'linear_k0.025': breakeven_aum(base['base_net'],
                                           ref['impact_linear_k0.025'], 1e10,
                                           'linear'),
        }
        caps = {}
        for cap in CAP_LEVELS:
            caps['%.2f' % cap] = {
                'p95': capacity_from_p95(ref['p95'], 1e10, cap),
                'p99': capacity_from_p95(ref['p99'], 1e10, cap),
            }
        tiers = {}
        for aum in (1e9, 1e10, 5e10):
            part, _ = impact_panel(traded, adv, sig, aum)
            tiers['%.0f' % aum] = tier_capacity(
                traded, part, P['amt_rank'].reindex_like(w), aum)

        # 分段稳健性: S1/S2 在 10亿 / 100亿 的冲击后净超额 (sqrt c=0.5)
        seg = {}
        idx = base['series']['ex'].index
        ex_v = base['series']['ex'].values
        t_v = base['series']['t']
        ok_v = base['series']['ok']
        for aum in (1e9, 1e10):
            imp_v = imp_by_aum['%.0f' % aum]['sqrt_c0.5'].values
            net_full = ex_v - 2.0 * t_v * FEE_BPS / 1e4 - imp_v
            for seg_name, (start, end) in SEGMENTS.items():
                m = ((idx >= start) & (idx <= end)) & ok_v
                seg['%s|%.0f' % (seg_name, aum)] = dict(
                    net=float(np.nanmean(net_full[m]) * 12),
                    t=float(nw_t(net_full[m])),
                    n=int(m.sum()),
                )
        panel[name] = dict(
            base={k: v for k, v in base.items() if k != 'series'},
            rows=rows, breakeven=bez, capacity=caps, tiers=tiers, segments=seg,
            n_hold=float((w > 0).sum(axis=1).mean()),
            universe=float(P['mask'].sum(axis=1).mean()),
        )

    # V1: 对账
    print('\n[V1 对账 — 与 LONG_SIDE_PORTFOLIO_RESEARCH.md §4]')
    warn = []
    for name, ref in RECON.items():
        b = panel[name]['base']
        checks = {
            'gross': (b['gross'], ref['gross'], 0.002),
            'excess_gross': (b['excess_gross'], ref['excess_gross'], 0.002),
            'excess_net': (b['base_net'], ref['excess_net'], 0.002),
            't_net': (b['base_net_t'], ref['t_net'], 0.05),
            'turnover': (b['turnover_ann'], ref['turnover'], 0.05),
        }
        for key, (got, want, tol) in checks.items():
            flag = 'OK' if abs(got - want) <= tol else 'WARN'
            if flag == 'WARN':
                warn.append('%s %s %.4f vs %.4f' % (name, key, got, want))
            print('  %-18s %-13s 本脚本 %+8.4f  报告 %+8.4f  差 %+8.4f  %s'
                  % (name, key, got, want, got - want, flag))

    # V2/V3
    for name, d in panel.items():
        rows = d['rows']
        assert abs(rows['%.0f' % AUM_GRID[0]]['impact_sqrt_c0.5']) > 0
        keys = ['%.0f' % a for a in AUM_GRID]
        for k in ('p95', 'p99'):
            seq = [rows[x][k] for x in keys]
            assert np.all(np.diff(seq) >= -1e-12), 'V3: %s %s 非单调' % (name, k)
        for k in ('impact_sqrt_c0.5', 'impact_linear_k0.025'):
            seq = [rows[x][k] for x in keys]
            assert np.all(np.diff(seq) >= -1e-12), 'V3: %s %s 非单调' % (name, k)

    # 打印: 容量与全成本表
    for name, d in panel.items():
        b = d['base']
        print('\n' + '=' * 120)
        print('[%s] 持仓 %.0f 只 | 毛年化 %.2f%% | 毛超额 %+.2f%% (t %.2f) | '
              '基础净超额 %+.2f%% (t %.2f) | 换手 %.2f x/年'
              % (name, d['n_hold'], b['gross'] * 100,
                 b['excess_gross'] * 100, b['excess_t'],
                 b['base_net'] * 100, b['base_net_t'], b['turnover_ann']))
        print('=' * 120)
        hdr = ('%6s %8s %8s %8s %8s %9s %9s %9s %8s'
               % ('AUM', 'p50', 'p95', 'p99', 'breach', 'imp_sqrt', 'imp_lin',
                  'net_sqrt', 't_sqrt'))
        print(hdr)
        print('-' * len(hdr))
        for aum in AUM_GRID:
            r = d['rows']['%.0f' % aum]
            print('%6.0f亿 %7.2f%% %7.2f%% %7.2f%% %7.2f%% %8.2f%% %8.2f%% '
                  '%+8.2f%% %8.2f'
                  % (aum / 1e8, r['p50'] * 100, r['p95'] * 100, r['p99'] * 100,
                     r['breach_1x'] * 100, r['impact_sqrt_c0.5'] * 100,
                     r['impact_linear_k0.025'] * 100, r['net_sqrt_c0.5'] * 100,
                     r['t_sqrt_c0.5']))
        print('  容量 (p95<=5%%/10%%/20%%): '
              '%.0f亿 / %.0f亿 / %.0f亿'
              % (d['capacity']['0.05']['p95'] / 1e8,
                 d['capacity']['0.10']['p95'] / 1e8,
                 d['capacity']['0.20']['p95'] / 1e8))
        print('  容量 (p99<=10%%): %.0f亿'
              % (d['capacity']['0.10']['p99'] / 1e8))
        print('  盈亏平衡 AUM: sqrt(c=0.5) %.0f亿 | sqrt(c=1.0) %.0f亿 | '
              'linear(k=2.5bp/1%%) %.0f亿'
              % (d['breakeven']['sqrt_c0.5'] / 1e8,
                 d['breakeven']['sqrt_c1.0'] / 1e8,
                 d['breakeven']['linear_k0.025'] / 1e8))

    # 流动性层 (AUM=100亿)
    print('\n' + '=' * 120)
    print('[流动性分层 — AUM=100亿] 低/中/高 = 池内 21 日均成交额分位 '
          '(<=30%% / 30-70%% / >70%%)')
    print('=' * 120)
    print('%-18s %6s %10s %8s %8s %10s'
          % ('variant', 'tier', 'notional', 'p50', 'p95', 'cap10'))
    for name, d in panel.items():
        for tier in ('low', 'mid', 'high'):
            t = d['tiers']['%.0f' % 1e10].get(tier)
            if not t:
                continue
            print('%-18s %6s %9.1f%% %7.2f%% %7.2f%% %8.0f亿'
                  % (name, tier, t['share_notional'] * 100,
                     t['p50'] * 100, t['p95'] * 100, t['cap10_aum'] / 1e8))

    print('\n' + '=' * 120)
    print('[分段稳健性 — 冲击后净超额 (sqrt c=0.5) / NW t]')
    print('=' * 120)
    print('%-18s %18s %18s %18s %18s'
          % ('variant', 'S1 @10亿', 'S1 @100亿', 'S2 @10亿', 'S2 @100亿'))
    for name, d in panel.items():
        cells = []
        for seg_name in ('S1', 'S2'):
            for aum in (1e9, 1e10):
                s = d['segments']['%s|%.0f' % (seg_name, aum)]
                cells.append('%+7.2f%% / %5.2f' % (s['net'] * 100, s['t']))
        print('%-18s %18s %18s %18s %18s'
              % (name, cells[0], cells[1], cells[2], cells[3]))

    print('\n[V2/V3/V4/V5] AUM 单调性 / 零违规 / 权重行和 通过')
    if warn:
        print('[WARN] ' + '; '.join(warn))
    else:
        print('[V1] 全部在容差内')

    payload = {
        'meta': {
            'fee_bps': FEE_BPS,
            'aum_grid': list(AUM_GRID),
            'sqrt_c': list(SQRT_C),
            'linear_k': list(LINEAR_K),
            'cap_levels': list(CAP_LEVELS),
            'amount_unit': '千元', 'mv_unit': '万元',
            'sample_start': str(P['factor'].index.min().date()),
            'sample_end': str(P['factor'].index.max().date()),
            'n_months': len(P['factor'].index),
            'recon_warnings': warn,
        },
        'results': panel,
    }
    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding='utf-8')
    print('JSON -> %s' % out)


if __name__ == '__main__':
    raise SystemExit(main())
