"""Task 3: 跨市场验证 — 同一管线在 4 市场运行 StatisticalClassifier

验证 v3.2.0 "学术级可迁移管线" 声明:
  相同的数学操作 (1%/99% 缩尾, Shapiro-Wilk, VR, OLS) 在不同市场产生一致的合理分类.

数据: JKP global factor returns (Jensen, Kelly & Pedersen 2021, global_factor_data.com)
市场: chn (A-share), usa (US), developed (全球发达), hkg (港股)
因子: 153 个异常因子 (JKP all_factors_monthly_vw_cap)

运行: python scripts/test_cross_market.py
"""
import numpy as np
import pandas as pd
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from factor_pipeline.modules.statistical_classifier import StatisticalClassifier

DATA_ROOT = r"D:\Article\Working paper\LGMM\LGMM 8.0\data\jkp"
MARKETS = ['chn', 'usa', 'developed', 'hkg']

JKP_CATEGORIES = {
    # Factor name → expected pipeline type (based on economic properties)
    # Momentum/value/carry factors should be static (trend-persistent returns)
    # Reversal/low-risk factors tend to be dynamic (mean-reverting in returns)
    # Size/issuance/growth factors often mixed (cross-sectional variation)
}


def load_jkp_market(market_code):
    """Load JKP factor data for one market, pivot to (T, N) panel."""
    fname = f"[{market_code}]_[all_factors]_[monthly]_[vw_cap].csv"
    folder = f"{market_code}_all_factors_monthly_vw_cap"
    path = os.path.join(DATA_ROOT, folder, fname)

    if not os.path.exists(path):
        print(f"  WARNING: {path} not found")
        return None

    df = pd.read_csv(path, parse_dates=['date'])
    pivoted = df.pivot_table(index='date', columns='name', values='ret')

    # Remove factors with < 60 months of data or >30% NaN
    T = len(pivoted)
    valid_factors = []
    for col in pivoted.columns:
        n_valid = pivoted[col].notna().sum()
        if n_valid >= 60 and n_valid >= T * 0.7:
            valid_factors.append(col)

    pivoted = pivoted[valid_factors].ffill(limit=1).dropna(axis=1, thresh=int(T * 0.5))
    return pivoted


def classify_factor_returns(df, market_name):
    """Classify each JKP factor return series using StatisticalClassifier."""
    clf = StatisticalClassifier(alpha=0.05, vr_q=5)
    results = []

    for factor_name in df.columns:
        series = df[factor_name].dropna()
        if len(series) < 60:
            continue
        # Reshape to (T, 1) panel — StatisticalClassifier expects panel format
        # JKP data is already market-level factor returns (1 series per factor)
        # We create (T, 10) bootstrap panels for robust classification
        panel = _bootstrap_panel(series)
        try:
            ptype = clf.classify(panel)
        except Exception:
            ptype = 'mixed'

        arr = panel.values
        T, N = arr.shape
        ar1_vals = []
        for j in range(N):
            col = arr[:, j]
            valid = ~np.isnan(col)
            idx = np.where(valid)[0]
            if len(idx) < 22:
                continue
            pairs = [(idx[i], idx[i+1]) for i in range(len(idx)-1)
                     if idx[i+1] - idx[i] == 1]
            if len(pairs) < 20:
                continue
            x_t = np.array([col[j] for _, j in pairs])
            x_tm1 = np.array([col[i] for i, _ in pairs])
            num = np.sum(x_t * x_tm1)
            den = np.sum(x_tm1 * x_tm1)
            ar1_vals.append(num / den if den > 1e-12 else 0)
        mean_ar1 = np.mean(ar1_vals) if ar1_vals else 0

        results.append({
            'market': market_name,
            'factor': factor_name,
            'type': ptype,
            'mean_ar1': mean_ar1,
            'T': len(series),
        })
    return results


def _bootstrap_panel(series, n_bootstrap=10):
    """Create (T, N) panel from single factor return series via bootstrap."""
    vals = series.values
    vals = vals[~np.isnan(vals)]
    T = len(vals)
    rng = np.random.default_rng(42)
    # Bootstrap: resample with replacement to create N parallel series
    panels = []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, T, size=T)
        panels.append(vals[idx])
    # Also include the original
    panels.append(vals)
    arr = np.column_stack(panels)
    return pd.DataFrame(arr, index=series.index[-len(arr):])


def cross_market_analysis(all_results):
    """Analyze classification consistency across markets."""
    print("\n" + "=" * 90)
    print("跨市场 StatisticalClassifier 分类一致性")
    print("=" * 90)

    # Build market × factor type matrix
    market_types = {}
    for r in all_results:
        m = r['market']
        if m not in market_types:
            market_types[m] = {'static': 0, 'dynamic': 0, 'mixed': 0, 'total': 0}
        market_types[m][r['type']] = market_types[m].get(r['type'], 0) + 1
        market_types[m]['total'] += 1

    print(f"\n{'Market':<14} {'#Factors':>8} {'static':>8} {'dynamic':>8} {'mixed':>8}")
    print("-" * 50)
    for m in MARKETS:
        if m in market_types:
            mt = market_types[m]
            print(f"{m:<14} {mt['total']:>8} "
                  f"{mt['static']:>8} {mt['dynamic']:>8} {mt['mixed']:>8}")

    # Find common factors across markets
    print("\n--- 跨市场共通因子分类 ---")

    common_factors = None
    for m in MARKETS:
        m_factors = set(r['factor'] for r in all_results if r['market'] == m)
        common_factors = m_factors if common_factors is None else common_factors & m_factors

    if not common_factors:
        print("  (无 4 市场共通因子)")
        # Try pairwise
        common_factors = set()
        for i in range(len(MARKETS)):
            for j in range(i+1, len(MARKETS)):
                mi, mj = MARKETS[i], MARKETS[j]
                fi = set(r['factor'] for r in all_results if r['market'] == mi)
                fj = set(r['factor'] for r in all_results if r['market'] == mj)
                pairwise = fi & fj
                if len(pairwise) > 5:
                    print(f"  {mi}×{mj}: {len(pairwise)} 共通因子")
                    common_factors |= pairwise if len(common_factors) == 0 else (
                        common_factors & pairwise)

    if common_factors:
        # Show classification for each common factor
        print(f"\n{'Factor':<30}", end="")
        for m in MARKETS:
            print(f" {' ' + m:>10}", end="")
        print("  Consensus")
        print("-" * 95)

        consistent = 0
        for fac in sorted(common_factors)[:20]:
            print(f"{fac:<30}", end="")
            types = []
            for m in MARKETS:
                t = next((r['type'] for r in all_results
                          if r['market'] == m and r['factor'] == fac), 'N/A')
                print(f" {t:>10}", end="")
                types.append(t)
            consensus = types[0] if len(set(types)) == 1 else 'mixed'
            if len(set(types)) == 1:
                consistent += 1
                print(f"  ✓ ({consensus})")
            else:
                print(f"  ~ ({', '.join(set(types))})")

        print(f"\n  跨市场完全一致: {consistent}/{len(common_factors)}")

    # Statistical classifier stability
    print("\n--- 分类稳定性 ---")
    for m in MARKETS:
        types = [r['type'] for r in all_results if r['market'] == m]
        if types:
            pct_mixed = sum(1 for t in types if t == 'mixed') / len(types) * 100
            pct_static = sum(1 for t in types if t == 'static') / len(types) * 100
            print(f"  {m}: {pct_static:.0f}% static, {pct_mixed:.0f}% mixed, "
                  f"{len(types)} factors total")

    return len(common_factors)


if __name__ == '__main__':
    all_results = []

    for m in MARKETS:
        print(f"\nLoading {m.upper()}...")
        df = load_jkp_market(m)
        if df is None:
            continue
        print(f"  Shape: {df.shape}")
        results = classify_factor_returns(df, m)
        all_results.extend(results)
        # Market summary
        types = [r['type'] for r in results]
        print(f"  Classification: static={types.count('static')}, "
              f"dynamic={types.count('dynamic')}, mixed={types.count('mixed')}")

    cross_market_analysis(all_results)
