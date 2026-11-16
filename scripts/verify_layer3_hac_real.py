# -*- coding: utf-8 -*-
"""Layer 3 HAC 真实数据验证 — 4 个量价因子 × PremiumEstimator.estimate_with_errors.

数据: E:\\Ashare_data (日频, 2020-01-02 -> 2026-01-30)
口径: 月末 FM + 下月前瞻收益; 上市满 250 交易日; 横截面 winsorize 1/99 + z-score.
断言: V2 (均值恒等) / V3 (SE 有限且 CI 含点) / V5 (与 diagnose 同号) 硬失败;
      V4 (HAC/iid 同阶) / V6 (n_valid) 软判定, 越界记 WARN.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pandas as pd

from factor_pipeline.modules.factor_health import (
    FactorHealthDiagnoser,
    PremiumEstimator,
)

DATA_ROOT = r"E:\Ashare_data"
MIN_STOCKS = 300
MIN_VALID_PERIODS = 60
KEYS = ('lambda_hat', 'lambda_se', 'lambda_ci_low', 'lambda_ci_high',
        'beta_t', 'beta_se', 'premium_mean', 'premium_mean_se',
        'premium_mean_ci_low', 'premium_mean_ci_high',
        'n_periods', 'n_valid', 'hac_lag', 'alpha')


def _load(root, name, csv=False):
    path = Path(root) / 'market_data' / name
    return pd.read_csv(path, index_col=0) if csv else pd.read_pickle(path)


def load_market(root):
    close = _load(root, 'stock_close.pkl')
    adj = _load(root, 'stock_adj.pkl')
    amount = _load(root, 'stock_amount.pkl')
    list_date = _load(root, 'list_date_df.pkl')['list_date']
    for df in (close, adj, amount):
        df.index = pd.to_datetime(df.index)
    cols = close.columns
    adj = adj.reindex(index=close.index, columns=cols)
    amount = amount.reindex(index=close.index, columns=cols)
    list_date = pd.to_datetime(list_date.reindex(cols))
    return close, adj, amount, list_date


def build_factors(adj_price, amount):
    """日频滚动 (右对齐, 只用 <=t), 全部取经济正向."""
    log_ret = np.log(adj_price).diff()
    amt = amount.where(amount > 0)
    return {
        'momentum_1m': log_ret.rolling(21, min_periods=15).sum(),
        'reversal_1w': -log_ret.rolling(5, min_periods=4).sum(),
        'volatility_1m': -log_ret.rolling(21, min_periods=15).std(),
        'amihud_1m': -(log_ret.abs() / amt).rolling(21, min_periods=15).mean() * 1e8,
    }


def month_end(df, how='last'):
    return getattr(df.resample('ME'), how)()


def build_eligible(close, list_date):
    """上市满 250 交易日 (≈365 自然日) 掩码.

    面板起点前已上市的老股直接 eligible; 面板内上市的新股按 list_date + 365 天.
    不可仅用 close.notna().cumsum(), 否则会把面板起点整体后移一年, 误伤老股.
    """
    dates = close.index
    threshold = (list_date + pd.Timedelta(days=365)).values
    eligible = dates.values[:, None] >= threshold[None, :]
    return pd.DataFrame(eligible, index=dates, columns=close.columns)


def cross_section_prep(factor_m, ret_m, mask_m):
    f = factor_m.where(mask_m)
    r = ret_m.where(mask_m)
    r = r.mask(r.abs() > 1.0)
    lo = f.quantile(0.01, axis=1)
    hi = f.quantile(0.99, axis=1)
    f = f.clip(lower=lo, upper=hi, axis=0)
    mu = f.mean(axis=1)
    sd = f.std(axis=1).replace(0.0, np.nan)
    f = f.sub(mu, axis=0).div(sd, axis=0)
    count = (f.notna() & r.notna()).sum(axis=1)
    thin = count < MIN_STOCKS
    return f.mask(thin, axis=0), r.mask(thin, axis=0)


def verify_factor(name, f, r, bandwidth, alpha):
    est = PremiumEstimator(bandwidth=bandwidth)
    res = est.estimate_with_errors(f, r, alpha=alpha)

    # V1: 14 键 + 长度
    missing = [k for k in KEYS if k not in res]
    assert not missing, f'{name}: 缺键 {missing}'
    for k in ('lambda_hat', 'lambda_se', 'lambda_ci_low', 'lambda_ci_high',
              'beta_t', 'beta_se'):
        assert len(res[k]) == len(f), f'{name}: {k} 长度不符'

    beta = res['beta_t']
    n_valid = int(np.isfinite(beta).sum())
    pm, se = res['premium_mean'], res['premium_mean_se']

    # V2: 均值恒等
    ref = float(np.nanmean(beta)) if n_valid else np.nan
    assert np.isfinite(pm) and abs(pm - ref) <= 1e-12 * max(1.0, abs(ref)), \
        f'{name}: premium_mean {pm} != nanmean(beta) {ref}'

    # V3: SE 有限且 CI 含点
    assert np.isfinite(se) and se > 0, f'{name}: premium_mean_se 非有限/非正'
    assert res['premium_mean_ci_low'] <= pm <= res['premium_mean_ci_high'], \
        f'{name}: CI 不含点估计'

    # V4 (软): HAC / iid 同阶
    naive_se = float(np.nanstd(beta) / np.sqrt(n_valid))
    ratio = se / naive_se if naive_se > 0 else np.nan
    warn = [] if 0.3 <= ratio <= 3.0 else [f'V4 比值 {ratio:.2f} 越界 [0.3, 3.0]']

    # V5: 与 diagnose 同号 (0 附近跳过)
    diag = FactorHealthDiagnoser(bandwidth=bandwidth, alpha=alpha)
    d = diag.diagnose(f, r, return_type='static')
    dpm = d['premium_mean']
    if abs(pm) > 2 * se and abs(dpm) > 0:
        assert np.sign(pm) == np.sign(dpm), \
            f'{name}: HAC 均值 {pm:.3e} 与 diagnose {dpm:.3e} 异号'

    # V6 (软)
    if n_valid < MIN_VALID_PERIODS:
        warn.append(f'V6 n_valid={n_valid} < {MIN_VALID_PERIODS}')

    return {
        'factor': name,
        'premium_mean': float(pm),
        'premium_mean_se': float(se),
        't_hac': float(pm / se),
        'naive_se': naive_se,
        't_naive': float(pm / naive_se) if naive_se > 0 else np.nan,
        'hac_over_iid': float(ratio),
        'ci_low': float(res['premium_mean_ci_low']),
        'ci_high': float(res['premium_mean_ci_high']),
        'n_periods': int(res['n_periods']),
        'n_valid': n_valid,
        'hac_lag': int(res['hac_lag']),
        'diagnosis': d['diagnosis'],
        'premium_health': d['premium_health'],
        'diagnose_premium_mean': float(dpm),
        'warnings': warn,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-root', default=DATA_ROOT)
    ap.add_argument('--bandwidth', type=int, default=12)
    ap.add_argument('--alpha', type=float, default=0.05)
    ap.add_argument('--json', default=None)
    args = ap.parse_args()

    close, adj, amount, list_date = load_market(args.data_root)
    adj_price = close * adj
    eligible = month_end(build_eligible(close, list_date).astype(float)) > 0

    factors = build_factors(adj_price, amount)
    price_m = month_end(adj_price)
    ret_m = price_m.shift(-1) / price_m - 1.0

    rows = []
    for name, fac in factors.items():
        f_p, r_p = cross_section_prep(month_end(fac), ret_m, eligible)
        rows.append(verify_factor(name, f_p, r_p, args.bandwidth, args.alpha))

    header = ('%-15s %13s %13s %8s %8s %7s %5s %5s %-10s %s'
              % ('factor', 'premium_mean', 'se', 't_hac', 't_naive',
                 'SEratio', 'T', 'nval', 'premium_health', 'warnings'))
    print('=' * len(header))
    print('Layer 3 HAC 真实数据验证 — %s, bandwidth=%d'
          % (Path(args.data_root).name, args.bandwidth))
    print('=' * len(header))
    print(header)
    print('-' * len(header))
    for r in rows:
        print('%-15s %13.6e %13.6e %8.2f %8.2f %7.3f %5d %5d %-10s %s'
              % (r['factor'], r['premium_mean'], r['premium_mean_se'],
                 r['t_hac'], r['t_naive'], r['hac_over_iid'],
                 r['n_periods'], r['n_valid'], r['premium_health'],
                 '; '.join(r['warnings']) or '-'))

    if args.json:
        Path(args.json).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        print('\nJSON -> %s' % args.json)


if __name__ == '__main__':
    main()
