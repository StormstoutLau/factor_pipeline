# EXECUTION — Layer 3 HAC 真实数据验证 (LAYER3_HAC_REAL_DATA)

> **版本**: v1.0 (2026-11-16)
> **流程**: `docs/WORKFLOW_METHODOLOGY.md` §13.8 步骤 5-6
> **上游**: [RESEARCH v1.0](research/RESEARCH_LAYER3_HAC_REAL_DATA.md) / DESIGN v1.0 (private)
> **目标**: 用真实 A 股数据验证 `estimate_with_errors`, 不改生产代码。

## §1 工程事实复核

| # | 事实 | 证据 |
|---|------|------|
| F1 | 日频行情 2020-01-02 → 2026-01-30, 1475×5688 | 实测 |
| F2 | 复权价 = `stock_close × stock_adj`; 000001 adj=109.1694 递增 | 序列核对 |
| F3 | `stock_amount` 为日成交额, 仅横截面排序用 | 实测 |
| F4 | `list_date_df` 5797×1, 列 `list_date` | 实测 |
| F5 | 财务/UTR pickle 不兼容当前 pandas → 不依赖 | 抛错复现 |
| F6 | 退市股 179 只 (末有效 <2025-01-01); 2021+ 上市 1315 只 | 掩码统计 |
| F7 | `estimate_with_errors` 返回 14 键; `premium_mean_se` 为全局 HAC | [factor_health L65-L155](../modules/factor_health/__init__.py#L65-L155) |
| F8 | `diagnose(factor, forward_returns, return_type)` 返回 `premium_mean` (平滑 λ̂ 均值) | [L343-L391](../modules/factor_health/__init__.py#L343-L391) |

## §2 代码 (`scripts/verify_layer3_hac_real.py`)

```python
# -*- coding: utf-8 -*-
"""Layer 3 HAC 真实数据验证 — 4 个量价因子 × PremiumEstimator.estimate_with_errors.

数据: E:\\Ashare_data (日频, 2020-01-02 -> 2026-01-30)
口径: 月末 FM + 下月前瞻收益; 上市满 250 交易日; 横截面 winsorize 1/99 + z-score.
断言: V2 (均值恒等) / V3 (SE 有限且 CI 含点) / V5 (与 diagnose 同号) 硬失败;
      V4 (HAC/iid 同阶) 软判定, 越界记 WARN.
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
MIN_LISTED_DAYS = 250
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

    # V6
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
        f_m = month_end(fac)
        f_p, r_p = cross_section_prep(f_m, ret_m, eligible)
        rows.append(verify_factor(name, f_p, r_p, args.bandwidth, args.alpha))

    header = ('%-15s %13s %13s %8s %8s %7s %5s %5s %10s %s'
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
```

## §3 验收口径

| # | 项 | 判定 |
|---|----|------|
| V1 | 14 键 + 数组长度 | 硬断言 |
| V2 | `premium_mean == nanmean(beta_t)` | 硬断言 (rel 1e-12) |
| V3 | `se` 有限正 + CI 含点 | 硬断言 |
| V4 | `hac_over_iid ∈ [0.3, 3.0]` | **软判定** (越界 → WARN) |
| V5 | 与 `diagnose` 同号 (`|pm| > 2se` 时) | 硬断言 |
| V6 | `n_valid ≥ 60` | 软判定 (WARN) |

> V4/V6 软判定的理由: 真实数据的自相关结构与样本长度不受控, 越界属**发现**而非脚本错误;
> 但仍必须在输出与报告中显式记录, 不得静默。

## §4 退化处理

| 场景 | 行为 |
|------|------|
| 某月有效股票 < 300 | 该月整行置 NaN |
| 因子全 NaN | `n_valid=0` → V2 断言失败并报错 |
| 复权价 NaN (adj 缺失) | 该股该日 NaN, 不进滚动窗口 |
| 最后一月无前瞻收益 | 自动少 1 期 |

## §5 兼容性

| 维度 | 结论 |
|------|------|
| 生产代码 | 零改动 |
| 依赖 | 仅 pandas/numpy (模块内) |
| 缓存 | 不涉及 |
| 版本 | 不升版本 (分析工件) |

## §6 步骤 6 review 记录 (幻觉消除 #2)

| # | 检查项 | 结论 |
|---|--------|------|
| A1 | F1-F8 与 §1 实测一致 | ✅ |
| A2 | `estimate_with_errors` 调用参数与 L65-L68 一致 | ✅ |
| A3 | `diagnose` 返回键 `premium_mean` 存在 | ✅ L381 |
| A4 | `close × adj` 复权口径有序列证据 | ✅ |
| A5 | `month_end` 用 `resample('ME')` (pandas 2.x 别名) | ✅ 环境 pandas 支持 |
| A6 | `clip(axis=0)` 在逐行分位下语义正确 | ✅ 逐月截断 |
| A7 | V4/V6 软判定与 DESIGN §3.5 一致 | ✅ (DESIGN G5 措辞已按此收敛) |
| A8 | 无前视: 因子滚动右对齐 + 收益 shift(-1) | ✅ |

**review 结论**: PASS。
