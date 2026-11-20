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
from datetime import datetime
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
        adj_price=adj_price, facts=facts)


def make_weights(P, kind, kw, tradable):
    u = P['mask'] & P['tradable'] if tradable else P['mask']
    if kind == 'qtop':
        return weights_top_quantile(P['factor'], P['ret'], u, q=kw['q'])
    return weights_exclude_bottom(P['factor'], P['ret'], u, frac=kw['frac'])


def month_trades(w):
    """单边交易权重 |Δw|; 首期 = 建仓."""
    dw = w - w.shift(1).fillna(0.0)
    return dw.abs()


def degraded_evidence(cfg):
    """分钟层跳过/失败时的证据等级（不回 'minutes'）。

    与 loaders.resolve_evidence_level 的区别：后者只判数据可用性，
    这里判「本次实际算到了哪一层」——分钟面板缺失时不得声称 minutes。
    """
    return 'ohlc' if Path(getattr(cfg, 'data_root', '')).is_dir() else 'daily'


def daily_portfolio_excess(P, w):
    """日频超额 = 组合日收益 − 可投资域等权日收益（W7）。"""
    price = P['adj_price']
    r = price.pct_change(fill_method=None)
    wd = w.reindex(r.index, method='ffill').reindex(columns=r.columns)
    wd = wd.fillna(0.0)
    rp = (wd * r.fillna(0.0)).sum(axis=1)
    ub = P['mask'].fillna(False).reindex(r.index, method='ffill')
    ub = ub.reindex(columns=r.columns).fillna(False)
    rb = r.where(ub).mean(axis=1)
    return (rp - rb).dropna()


def daily_ref(P, cfg):
    """构造 panels.DailyRef（月频 ADV / 行业 / 规模 / 交易日数）。"""
    from backtest.execution.shell.panels import DailyRef
    mv_rank = np.ceil(P['mv_m'].rank(axis=1, pct=True) * 5.0).clip(1, 5)
    days = P['close'].groupby(P['close'].index.strftime('%Y-%m')).size()
    return DailyRef(
        adv=P['amt_m'],
        universe=P['mask'].fillna(False) & P['ret'].notna(),
        industry=P['facts']['ind'],
        mv_rank=mv_rank,
        days_by_month=dict((str(k), int(v)) for k, v in days.items()))


def formation_decay_curve(P, w, h_max=60):
    """形成期 t0 冻结权重的后验累计超额 A_{t0}(h)，h=1..h_max。

    权重取 t0 快照后在**整个 h 窗口内不再调整**（DESIGN §2 D1「之后不再调整」）。
    不得复用 daily_portfolio_excess 的前向填充序列——它在下一形成日切换为新月
    权重，h 超过单月交易日数（约 21 日）后混入后续月权重，违反冻结语义（复审 I-1）。
    基准 rb（可投资域等权）与权重无关，全局计算一次；NaN 日按
    daily_portfolio_excess 同一 dropna 口径剔除（不计入 h 计数）。
    形成日 t0 当日的收益不计入（无前视，side="right"）。
    样本末端不足 h 日的形成期以 NaN 补齐（不缩短窗口、不用部分和）。
    """
    price = P['adj_price']
    r = price.pct_change(fill_method=None)
    ub = P['mask'].fillna(False).reindex(r.index, method='ffill')
    ub = ub.reindex(columns=r.columns).fillna(False)
    rb = r.where(ub).mean(axis=1)
    r0 = r.fillna(0.0)
    index = r.index
    rows = []
    for t0 in w.index:
        start = int(index.searchsorted(t0, side="right"))
        seg = r0.iloc[start:start + int(h_max)]
        wv = w.loc[t0].reindex(seg.columns).fillna(0.0)   # 冻结快照
        rp = seg.mul(wv, axis=1).sum(axis=1)
        ex = (rp - rb.reindex(seg.index)).dropna()
        row = np.full(int(h_max), np.nan)
        vals = ex.to_numpy()
        if vals.size:
            row[:vals.size] = np.cumsum(vals)
        rows.append(row)
    return rows


def build_portfolio_panels(P, cfg, kind='exQ1_EW_tradable', aum_ref=1e10):
    """市场数据装配（W7）：权重 / 交易额 / 参与率 / regime / 窗口容量 / 超额。"""
    spec = dict((name, (k, kw, tr)) for name, k, kw, tr in VARIANTS)[kind]
    w = make_weights(P, spec[0], spec[1], spec[2])
    universe = P['mask'] & P['tradable'] if spec[2] else P['mask']
    base = evaluate(w, P, universe)
    traded = month_trades(w)
    adv = P['amt_m'].reindex_like(w)
    part = (traded * aum_ref) / adv.where(adv > 0)
    part = part.where(part > 0)

    amt_total = adv.sum(axis=1).dropna()
    bucket = pd.qcut(amt_total.rank(method='first'), 5,
                     labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'])
    regimes = {}
    for name in ('Q1', 'Q2', 'Q3', 'Q4', 'Q5'):
        rows = bucket.index[bucket == name]
        vals = part.reindex(rows).to_numpy().ravel()
        vals = vals[np.isfinite(vals)]
        if vals.size:
            regimes[name] = float(np.percentile(vals, 95))

    months = list(part.index)
    window_capacity = {}
    for width in cfg.windows:
        points = []
        for i in range(max(0, len(months) - int(width) + 1)):
            vals = part.iloc[i:i + int(width)].to_numpy().ravel()
            vals = vals[np.isfinite(vals)]
            if vals.size:
                points.append(float(np.percentile(vals, 95)))
        if points:
            window_capacity[str(int(width))] = float(np.median(points))

    traded_v = traded.to_numpy()
    adv_v = adv.reindex_like(traded).to_numpy()
    ok = np.isfinite(traded_v) & np.isfinite(adv_v) & (adv_v > 0)
    p_all = ((traded_v[ok] * aum_ref) / adv_v[ok])
    p_all = p_all[np.isfinite(p_all)]
    sigma_v = P['sig_m'].reindex_like(traded).to_numpy()
    sigma_v = sigma_v[np.isfinite(sigma_v)]
    turns = pd.Series(np.asarray(base['series']['t'], dtype=float),
                      index=w.index)
    return {
        'aum_ref': float(aum_ref),
        'excess_m': base['series']['ex'].dropna(),
        'excess_d': daily_portfolio_excess(P, w),
        'turnover_m': turns.dropna(),
        'regime_p95': regimes,
        'window_capacity': window_capacity,
        'notional': (traded_v * aum_ref)[ok],
        'adv': adv_v[ok],
        'p_cost': float(np.median(p_all)) if p_all.size else None,
        'sigma_port': float(np.median(sigma_v)) if sigma_v.size else None,
        'a_by_period': formation_decay_curve(P, w),
        'a_h_max': 60,
    }


def attach_panel_meta(result, minute, daily_panels, cfg):
    """把 panels / lambda_stats / impact_samples / impact_curve 挂到 result（S3）。"""
    from backtest.execution.core.impact import (LinearImpact, LogImpact,
                                                PowerImpact, SqrtImpact)
    cov = minute.get('coverage')
    result = dict(result or {})
    result['panels'] = dict(result.get('panels') or {})
    result['panels'].update({
        'evidence_level': result.get('evidence_level'),
        'coverage': cov.as_dict() if hasattr(cov, 'as_dict') else cov,
        'panel_hash': minute.get('panel_hash'),
        'window_capacity': daily_panels.get('window_capacity') or {},
    })
    result['lambda_stats'] = minute.get('lambda_stats')
    result['impact_samples'] = minute.get('impact_samples_meta')
    fit = minute.get('impact_fit') or {}
    models = dict((m.name, m) for m in (SqrtImpact(), LinearImpact(),
                                        LogImpact(), PowerImpact()))
    model = models.get(fit.get('primary'))
    if model is not None and fit.get('params'):
        grid = np.array([0.001, 0.005, 0.01, 0.02, 0.05])
        sigma_ref = float(minute.get('sigma_median') or 0.02)
        sigma_arr = np.full(grid.size, sigma_ref, dtype=float)
        curve = model.predict(grid, sigma_arr, fit['params'])
        result['impact_curve'] = {
            'p': grid.tolist(),
            'impact_bps': (np.asarray(curve, dtype=float) * 1e4).tolist()}
    result['decay'] = dict(result.get('decay') or {})
    result['decay']['alpha0'] = daily_panels.get('alpha0')
    result['decay']['cost_by_h'] = daily_panels.get('cost_by_h') or {}
    merged = list(result.get('evidence_warnings') or [])
    for item in ((minute.get('evidence_warnings') or [])
                 + (daily_panels.get('evidence_warnings') or [])):
        if item not in merged:
            merged.append(item)
    result['evidence_warnings'] = merged
    return result


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


def _write_report_json(path, tool, checks, artifacts):
    """v3.9.0 统一验证报告（schema 见 DESIGN §8.1）；默认不写。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'tool': tool,
        'generated_at': datetime.now().isoformat(),
        'checks': checks,
        'artifacts': artifacts,
        'status': ('pass' if all(item['ok'] for item in checks) else 'fail'),
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                      encoding='utf-8')
    print('report-json -> %s' % target)


def _fmt(value):
    """浮点展示：非有限 -> NaN，缺失 -> NA。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 'NA'
    if not np.isfinite(v):
        return 'NaN'
    return '%.6g' % v


def _decay_curve_md(payload):
    """衰减曲线 md（口径 / m / net / verdict / bootstrap / warnings 六节）。"""
    h_m = payload.get('h_m')
    horizons = [int(h) for h in payload.get('horizons') or []]
    lines = [
        '# v3.9.3 alpha 衰减曲线（FO-1）', '',
        '> 由 `verify_capacity_impact.py --calibrate --decay-curve-json` '
        '生成；默认路径不产出。',
        '> `m(20)=1` 为构造性归一 → 验收①（net(h)>0 至少一点）在修正口径下'
        '几乎恒成立（DESIGN §10.3）；判别力在 h=5/10。', '',
        '## 1. 口径', '',
        '- h_m = %s 交易日；形成期数 n_periods = %s'
        % (h_m, payload.get('n_periods')),
        '- alpha0_anchored = A(%s) = %s（主值，锚定口径）'
        % (h_m, _fmt(payload.get('alpha0_anchored'))),
        '- alpha0_calendar = %s（日历月均值，对照；量纲不同，不作主值）'
        % _fmt(payload.get('alpha0_calendar')),
        '- phi = %s（phi_status = %s，decay_source = %s）；'
        '先验半衰期 126 交易日（并列 252 日 = %.10f）'
        % (_fmt(payload.get('phi')), payload.get('phi_status'),
           payload.get('decay_source'), 2.0 ** (-1.0 / 252.0)),
        '- horizons = %s' % horizons, '',
        '## 2. m(h) 三值（m(h_m)=1 构造性）', '',
        '| h | point | lo | hi | n_h |', '|---|---|---|---|---|']
    n_by_h = payload.get('n_by_h') or {}
    m_items = payload.get('m') or {}
    for h in horizons:
        item = m_items.get(str(h)) or {}
        lines.append('| %d | %s | %s | %s | %s |'
                     % (h, _fmt(item.get('point')), _fmt(item.get('lo')),
                        _fmt(item.get('hi')), n_by_h.get(str(h))))
    lines += ['', '### 2.1 A(h) 点估计 / 中位数（DR-7）', '',
              '| h | point | median | lo | hi | n_h |',
              '|---|---|---|---|---|---|']
    a_items = payload.get('a') or {}
    for h in horizons:
        item = a_items.get(str(h)) or {}
        lines.append('| %d | %s | %s | %s | %s | %s |'
                     % (h, _fmt(item.get('point')), _fmt(item.get('median')),
                        _fmt(item.get('lo')), _fmt(item.get('hi')),
                        n_by_h.get(str(h))))
    lines += ['', '### 2.2 bootstrap 敏感性（m 的 lo / hi）', '',
              '| h | b=1 lo | b=1 hi | b=6 lo | b=6 hi |',
              '|---|---|---|---|---|']
    sens = payload.get('m_sensitivity') or {}
    for h in horizons:
        one = (sens.get('1') or {}).get(str(h)) or {}
        six = (sens.get('6') or {}).get(str(h)) or {}
        lines.append('| %d | %s | %s | %s | %s |'
                     % (h, _fmt(one.get('lo')), _fmt(one.get('hi')),
                        _fmt(six.get('lo')), _fmt(six.get('hi'))))
    lines += ['', '## 3. net(h) 三值（元/期；AUM 取面板 aum_ref）', '',
              '| h | point | lo | hi |', '|---|---|---|---|']
    net_items = payload.get('net') or {}
    for h in horizons:
        item = net_items.get(str(h)) or {}
        lines.append('| %d | %s | %s | %s |'
                     % (h, _fmt(item.get('point')), _fmt(item.get('lo')),
                        _fmt(item.get('hi'))))
    lines += ['', '## 4. verdict', '',
              '- posterior = 后置衰减（m<1 且 CI 上界<1）',
              '- flat = 未检出衰减（CI 覆盖 1）',
              '- anterior = 前置 alpha（m>1 且 CI 下界>1）',
              '- unidentified = 曲线不可识别（A(h_m)<=0 或 CI 缺失）',
              '',
              '> 表述纪律：**未检出衰减 ≠ 无衰减**（I-7）。', '',
              '| h | verdict |', '|---|---|']
    verdict = payload.get('verdict') or {}
    for h in sorted(int(k) for k in verdict):
        lines.append('| %d | %s |' % (h, verdict.get(str(h))))
    boot = payload.get('boot') or {}
    lines += ['', '## 5. bootstrap', '',
              '- block = %s；reps = %s；sensitivity = %s；seed = %s'
              % (boot.get('block'), boot.get('reps'),
                 boot.get('sensitivity'), boot.get('seed')),
              '- CI 只按形成期重采（INV-8），期内日重叠不产生独立样本', '',
              '## 6. evidence_warnings', '']
    warnings = payload.get('evidence_warnings') or []
    lines += ['- %s' % w for w in warnings] if warnings else ['- （无）']
    return '\n'.join(lines) + '\n'


def write_decay_curve(path, payload):
    """写 out/v393_decay_curve.json + 同名 .md；payload 为 None 时跳过。"""
    if not payload:
        return []
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                      encoding='utf-8')
    md = target.with_suffix('.md')
    md.write_text(_decay_curve_md(payload), encoding='utf-8')
    return [str(target), str(md)]


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
    # v3.8.0 E7 新增分支（默认路径零变更）
    ap.add_argument('--calibrate', action='store_true',
                    help='运行 v3.8.0 执行/容量校准，输出 out/capacity_calibration.json')
    ap.add_argument('--evidence-level',
                    choices=('auto', 'minutes', 'ohlc', 'daily'),
                    default='auto', help='强制/诊断证据等级（默认 auto）')
    ap.add_argument('--diagnose-window', action='store_true',
                    help='诊断滚动窗长（IJR 自动窗长仅诊断，不参与主值）')
    ap.add_argument('--calibration-json', default=None,
                    help='校准 JSON 路径（默认 out/capacity_calibration.json）')
    ap.add_argument('--report-json', default=None,
                    help='v3.9.0 统一验证报告路径（默认关闭）')
    # v3.9.3 新增（默认关闭，不改变默认路径）
    ap.add_argument('--decay-curve-json', default=None,
                    help='校准路径额外写出 alpha 衰减曲线工件（默认不写）')
    # v3.8.1 新增（默认关闭，不改变默认路径）
    ap.add_argument('--no-minute', action='store_true',
                    help='跳过分钟层（仅日频校准）')
    ap.add_argument('--panel-cache', action='store_true',
                    help='启用 out/panel_cache 分钟聚合缓存')
    ap.add_argument('--force-coverage', action='store_true',
                    help='覆盖度门禁失败仍继续（留痕 warning）')
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

    if args.calibrate or args.diagnose_window:
        if str(SCRIPTS.parent) not in sys.path:
            sys.path.insert(0, str(SCRIPTS.parent))
        from backtest.execution.config import CalibrationConfig
        from backtest.execution.shell.loaders import (MinuteLoader,
                                                      resolve_evidence_level)
        from backtest.execution.shell.panels import (MinutePanelBuilder,
                                                     assemble_panels,
                                                     build_daily_panels,
                                                     coverage_gate,
                                                     force_coverage_warning)
        from backtest.execution.shell.report import write_report
        from backtest.execution.shell.runner import run_calibration

        cfg = CalibrationConfig(data_root=args.data_root)
        forced = None if args.evidence_level == 'auto' else args.evidence_level
        if args.diagnose_window:
            print('诊断: 解析证据等级 = %s' % resolve_evidence_level(cfg))
            print('诊断: 候选窗长 = %s（IJR 自动窗长仅诊断，不参与主值）'
                  % (list(cfg.windows),))
            if not args.calibrate:
                return 0

        minute = {'evidence_warnings': ['分钟层跳过: --no-minute（证据等级降级）']}
        if args.no_minute:
            print('[minute] --no-minute：跳过分钟层面板')
            evidence = forced or degraded_evidence(cfg)
            panels = assemble_panels(minute, {'evidence_warnings': []},
                                     evidence)
        else:
            market = build_panels(args.data_root)
            loader = MinuteLoader(cfg.minute_root,
                                  sigma_bars=cfg.bvc_sigma_bars)
            cache_dir = (str(SCRIPTS.parent / 'out' / 'panel_cache')
                         if args.panel_cache else None)
            builder = MinutePanelBuilder(cfg, loader=loader,
                                         daily=daily_ref(market, cfg),
                                         cache_dir=cache_dir)
            minute = builder.build()
            ok, messages = coverage_gate(minute.get('coverage') or {})
            if not ok:
                for message in messages:
                    print('[coverage] %s' % message)
                if not args.force_coverage:
                    return 2
                minute.setdefault('evidence_warnings', []).append(
                    force_coverage_warning(messages))
                print('[coverage] --force-coverage：门禁失败放行（留痕）')
            portfolio = build_portfolio_panels(market, cfg)
            daily_panels = build_daily_panels(
                cfg, market, portfolio, impact_fit=minute.get('impact_fit'))
            evidence = (forced or ('minutes' if minute.get('panel_hash')
                                   else degraded_evidence(cfg)))
            panels = assemble_panels(minute, daily_panels, evidence)

        result = run_calibration(
            cfg, capacity_fn=capacity_from_p95,
            breakeven_fn=breakeven_aum, panels=panels)
        if not args.no_minute:
            result = attach_panel_meta(result, minute, daily_panels, cfg)
        else:
            result['evidence_warnings'] = list(
                result.get('evidence_warnings') or []
            ) + list(minute.get('evidence_warnings') or [])
        json_path = args.calibration_json or str(
            SCRIPTS.parent / 'out' / 'capacity_calibration.json')
        md_path = str(Path(json_path).with_suffix('.md'))
        written = write_report(result, json_path, md_path)
        print('evidence_level = %s' % result['evidence_level'])
        print('校准报告: %s' % ', '.join(written))
        if args.decay_curve_json:
            from backtest.execution.shell.runner import assemble_decay_curve
            written_curve = write_decay_curve(
                args.decay_curve_json, assemble_decay_curve(panels))
            if written_curve:
                print('衰减曲线: %s' % ', '.join(written_curve))
        if args.report_json:
            checks = [{'id': 'calibrate', 'ok': True},
                      {'id': 'evidence_level',
                       'ok': bool(result.get('evidence_level'))}]
            if args.no_minute:
                checks.append({'id': 'coverage', 'ok': True, 'skipped': True,
                               'detail': '--no-minute'})
            else:
                ok, messages = coverage_gate(minute.get('coverage') or {})
                checks.append({'id': 'coverage', 'ok': bool(ok),
                               'detail': '; '.join(messages)})
            _write_report_json(args.report_json, 'verify_capacity_impact',
                               checks, [{'path': str(json_path)}])
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
    if args.report_json:
        _write_report_json(args.report_json, 'verify_capacity_impact',
                           [{'id': 'V1', 'ok': True},
                            {'id': 'V2', 'ok': True},
                            {'id': 'V3', 'ok': True},
                            {'id': 'V4', 'ok': True},
                            {'id': 'V5', 'ok': True}],
                           [{'path': str(out)}])


if __name__ == '__main__':
    raise SystemExit(main())
