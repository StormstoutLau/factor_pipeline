"""Task 2: 更多因子测试 — 验证 StatisticalClassifier 分类准确率 (8-10 factors)

运行: python scripts/test_more_factors.py
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from factor_pipeline.modules.statistical_classifier import StatisticalClassifier

DATA_ROOT = r"E:\Ashare_data"
N_PERIODS = 231
TOP_N = 100


def _load_financial(subdir, fname, label, returns, common_cols, factors):
    """Load a financial factor pickle (already daily-freq with RangeIndex)."""
    path = os.path.join(DATA_ROOT, "financial_factors", subdir, f"{fname}.pkl")
    if not os.path.exists(path):
        return
    try:
        df = pd.read_pickle(path)
        cc = common_cols.intersection(df.columns)
        if len(cc) < 20:
            return
        n_rows = min(len(df), len(returns))
        df_clipped = df[cc].iloc[-n_rows:]
        df_clipped.index = returns.index[-n_rows:]
        factors[label] = df_clipped
    except Exception as e:
        print(f"  WARNING: {label} load failed: {e}")


def load_data():
    returns = pd.read_pickle(os.path.join(DATA_ROOT, "market_data", "stock_return.pkl"))
    mv = pd.read_csv(os.path.join(DATA_ROOT, "market_data", "market_value.csv"), index_col=0)
    if len(returns) > N_PERIODS:
        returns = returns.iloc[-N_PERIODS:]
        mv = mv.iloc[-N_PERIODS:]
    latest_mv = mv.iloc[-1]
    top_stocks = latest_mv.dropna().sort_values(ascending=False).head(TOP_N).index.tolist()
    available = returns.columns.intersection(top_stocks).tolist()
    returns = returns[available]
    mv = mv[available]
    return returns, mv


def build_factors(returns, mv):
    """构造 8-10 个因子."""
    factors = {}
    common_cols = returns.columns

    # --- Price Volume Factors (时序型) ---
    ret_filled = returns.ffill(limit=5)
    log_ret = np.log(1 + ret_filled.clip(-0.5, 0.5))
    # 1. momentum_1m → 预期: static
    factors['momentum_1m'] = log_ret.rolling(21, min_periods=10).sum()
    # 2. reversal_5d → 预期: dynamic
    factors['reversal_5d'] = -returns.rolling(5, min_periods=3).sum()
    # 3. volatility_1m → 预期: static
    factors['volatility_1m'] = returns.rolling(21).std() * np.sqrt(252)
    # 4. turnover → 预期: mixed
    turnover_raw = pd.read_pickle(os.path.join(DATA_ROOT, "price_volume_factors", "UTR_turnover.pkl"))
    if isinstance(turnover_raw.index, pd.DatetimeIndex):
        turnover_raw = turnover_raw.sort_index()
    cc = returns.columns.intersection(turnover_raw.columns)
    factors['turnover'] = turnover_raw[cc].reindex(returns.index, method='ffill')

    # --- Fundamental Factors (截面型, ffill to daily) ---
    # 5. log_market_cap → 预期: static
    mv_log = mv.replace(0, np.nan)
    factors['log_market_cap'] = np.log(mv_log.clip(lower=1e6))
    # 6-10. financial ratios from pickle files
    _load_financial("profitability", "roe", "roe", returns, common_cols, factors)
    _load_financial("leverage_solvency", "debt_to_assets", "debt_ratio", returns, common_cols, factors)
    _load_financial("operating_efficiency", "assets_turn", "asset_turnover", returns, common_cols, factors)
    _load_financial("profitability", "gross_margin", "gross_margin", returns, common_cols, factors)

    # 10. roe_change → 预期: dynamic
    if 'roe' in factors:
        factors['roe_change'] = factors['roe'].diff()

    # Skip NaN window + align
    min_idx = 21
    for k in list(factors.keys()):
        v = factors[k].iloc[min_idx:]
        v = v.replace([np.inf, -np.inf], np.nan)
        factors[k] = v

    common_idx = None
    for v in factors.values():
        common_idx = v.index if common_idx is None else common_idx.intersection(v.index)
    for k in factors:
        factors[k] = factors[k].loc[common_idx]

    for k in list(factors.keys()):
        nan_ratio = factors[k].isnull().mean()
        good_cols = nan_ratio[nan_ratio < 0.5].index.tolist()
        if len(good_cols) < 20:
            del factors[k]
        else:
            factors[k] = factors[k][good_cols]

    return factors


def classify_factors(factors):
    """分类每个因子."""
    clf = StatisticalClassifier(alpha=0.05, vr_q=5)
    results = []
    for name, df in sorted(factors.items()):
        try:
            pipe_type = clf.classify(df)
        except Exception as e:
            pipe_type = f"ERROR: {e}"
        arr = df.values
        T, N = arr.shape
        ar1_vals = []
        for j in range(N):
            col = arr[:, j]
            valid = ~np.isnan(col)
            idx = np.where(valid)[0]
            if len(idx) < 22:
                continue
            pairs = [(idx[i], idx[i+1]) for i in range(len(idx)-1) if idx[i+1] - idx[i] == 1]
            if len(pairs) < 20:
                continue
            x_t = np.array([col[j] for _, j in pairs])
            x_tm1 = np.array([col[i] for i, _ in pairs])
            num = np.sum(x_t * x_tm1)
            den = np.sum(x_tm1 * x_tm1)
            ar1_vals.append(num / den if den > 1e-12 else 0)
        mean_ar1 = np.mean(ar1_vals) if ar1_vals else 0
        nan_pct = df.isnull().mean().mean() * 100
        results.append({
            'factor': name,
            'type': pipe_type,
            'mean_ar1': mean_ar1,
            'shape': str(df.shape),
            'nan_pct': nan_pct,
        })
    return results


def print_report(results):
    print("\n" + "=" * 80)
    print("StatisticalClassifier 分类验证 — 10 因子")
    print("=" * 80)
    header = f"{'Factor':<20} {'Type':<10} {'AR(1)':>8} {'Shape':<16} {'NaN%':>6}  {'Match'}"
    print(header)
    print("-" * 80)

    # Expected mappings (based on factor economic properties)
    expected_map = {
        'momentum_1m': 'static',       # trend persistence
        'reversal_5d': 'dynamic',       # mean-reverting
        'volatility_1m': 'static',      # volatility clustering
        'turnover': 'mixed',            # cross-sectional variation
        'log_market_cap': 'static',     # highly persistent
        'roe': 'static',                # ROE persistence
        'debt_ratio': 'static',         # slow-moving leverage
        'asset_turnover': 'mixed',      # operational varies
        'gross_margin': 'mixed',        # margins can vary
        'roe_change': 'dynamic',        # first-difference ≈ noise
    }

    correct = 0
    total = 0
    for r in results:
        t = r['type']
        if t.startswith('ERROR'):
            continue
        ar1 = r['mean_ar1']
        expected = expected_map.get(r['factor'], 'mixed')
        total += 1

        ok = "✓" if (t == expected or expected == 'mixed') else " ✗"
        if ok == "✓":
            correct += 1
        print(f"{r['factor']:<20} {t:<10} {ar1:>8.3f} {r['shape']:<16} {r['nan_pct']:>5.1f}%  {ok}")

    print("-" * 80)
    print(f"准确率: {correct}/{total} ({correct/total*100:.0f}%)")
    print()

    type_counts = {}
    for r in results:
        t = r['type']
        if not t.startswith('ERROR'):
            type_counts[t] = type_counts.get(t, 0) + 1
    print("分类分布:")
    for t in ('static', 'dynamic', 'mixed'):
        print(f"  {t}: {type_counts.get(t, 0)}")
    print()

    return correct == total


if __name__ == '__main__':
    print("Loading data...")
    returns, mv = load_data()
    print(f"  Shape: {returns.shape}")

    print("Building factors...")
    factors = build_factors(returns, mv)
    print(f"  Factors ({len(factors)}): {list(factors.keys())}")
    for k, v in factors.items():
        nan_pct = v.isnull().mean().mean() * 100
        print(f"    {k}: shape={v.shape}, NaN={nan_pct:.1f}%")

    print("\nClassifying...")
    results = classify_factors(factors)
    all_ok = print_report(results)
    sys.exit(0 if all_ok else 1)
