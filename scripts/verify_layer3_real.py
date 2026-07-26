"""Layer 3 真实 A 股数据验证 — FactorHealthDiagnoser on 3 real factors"""
import os, sys, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from factor_pipeline.modules.factor_health import FactorHealthDiagnoser

DATA_ROOT = r"E:\Ashare_data"
N_PERIODS, TOP_N = 231, 100

print("Loading A-share data...")
returns = pd.read_pickle(os.path.join(DATA_ROOT, "market_data", "stock_return.pkl"))
mv = pd.read_csv(os.path.join(DATA_ROOT, "market_data", "market_value.csv"), index_col=0)
if len(returns) > N_PERIODS:
    returns = returns.iloc[-N_PERIODS:]
    mv = mv.iloc[-N_PERIODS:]
latest_mv = mv.iloc[-1]
top_stocks = latest_mv.dropna().sort_values(ascending=False).head(TOP_N).index.tolist()
available = returns.columns.intersection(top_stocks).tolist()
returns = returns[available]

# Build 3 factors
ret_filled = returns.ffill(limit=5)
log_ret = np.log(1 + ret_filled.clip(-0.5, 0.5))
fw = returns.shift(-1)

factors = {
    'momentum_1m': log_ret.rolling(21, min_periods=10).sum().iloc[21:],
    'volatility_1m': returns.rolling(21).std().iloc[21:] * np.sqrt(252),
    'turnover': pd.read_pickle(os.path.join(DATA_ROOT, "price_volume_factors", "UTR_turnover.pkl")).pipe(
        lambda d: d.sort_index() if hasattr(d.index, 'sort_values') else d
    ).reindex(columns=available).reindex(returns.index, method='ffill').iloc[21:],
}

# Align
common_idx = None
for v in factors.values():
    common_idx = v.index if common_idx is None else common_idx.intersection(v.index)
fw = fw.loc[common_idx, available]
for k in factors:
    factors[k] = factors[k].loc[common_idx, available]

print(f"\n{'='*75}")
print(f"Layer 3 Factor Health Diagnosis — Real A-share (3 factors)")
print(f"{'='*75}")

diag = FactorHealthDiagnoser(bandwidth=24, alpha=0.05)

for name in sorted(factors.keys()):
    factor_df = factors[name]
    fwd_df = fw
    result = diag.diagnose(factor_df, fwd_df, return_type='unknown')
    print(f"\n{name}:")
    print(f"  Combined diagnosis:  {result['diagnosis']}")
    print(f"  Premium health:      {result['premium_health']}")
    print(f"  Premium mean:        {result['premium_mean']:.6f}")
    print(f"  Premium std:         {result['premium_std']:.6f}")
    print(f"  Breakpoint detected: {result['has_breakpoint']}")
    if result.get('breakpoint_idx'):
        print(f"  Breakpoint at t=     {result['breakpoint_idx']}")
        print(f"  Pre-BP mean:         {result['mean_premium_pre_bp']:.6f}")
        print(f"  Post-BP mean:        {result['mean_premium_post_bp']:.6f}")
    if result.get('half_life'):
        print(f"  Half-life:           {result['half_life']:.1f} months")
    print(f"  F_max:               {result['chow_max_stat']:.1f}")

print(f"\n{'='*75}")
print("Verification complete.")
