# -*- coding: utf-8 -*-
"""
真实A股数据消融实验脚本 — 基于 E:/Ashare_data + E:/因子研究

数据源:
- E:/Ashare_data/market_data/stock_return.pkl — 日频收益 (fwd_returns)
- E:/Ashare_data/market_data/market_value.csv — 市值 (股票筛选)
- E:/Ashare_data/market_data/stock_ind.pkl — 行业分类
- E:/Ashare_data/price_volume_factors/UTR_turnover.pkl — 月频换手率

因子构造 (从 stock_return 自建, 避免财务数据季度频率对齐问题):
- momentum_1m: 21日累计收益 (时序动量)
- volatility_1m: 21日滚动波动率 (时序波动)
- turnover_factor: 月频换手率 (前向填充到日频)

消融参数:
- 504 个交易日 (~2年), Top300 市值股票
- B0-B3 基线 + L1 5模块消融
- Ledoit-Wolf HAC + Circular Block Bootstrap (500次)
"""
import sys, os, json, warnings, time
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd
from scipy import stats as sp_stats

_PROJECT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJECT)

from factor_pipeline.pipelines_v2 import PipelineV2Config, FactorProcessingPipelineV2
from factor_pipeline.backtest.ablation_runner import AblationRunner


DATA_ROOT = r"E:\Ashare_data"
N_PERIODS = 252  # ~1 year daily
TOP_N = 100       # Top 100 stocks
SEED = 42


def load_real_data():
    print("Loading A-share daily data...")

    # 1. 日频收益
    returns = pd.read_pickle(os.path.join(DATA_ROOT, 'market_data', 'stock_return.pkl'))
    returns.index = pd.to_datetime(returns.index)
    returns = returns.sort_index()
    print(f"  stock_return: {returns.shape} ({returns.index[0].strftime('%Y-%m-%d')} → "
          f"{returns.index[-1].strftime('%Y-%m-%d')})")

    # 2. 市值 (筛选 Top N)
    mv = pd.read_csv(os.path.join(DATA_ROOT, 'market_data', 'market_value.csv'), index_col=0)
    mv.index = pd.to_datetime(mv.index)
    mv = mv.sort_index()

    # 取最后一天市值
    common_idx = returns.index.intersection(mv.index)
    returns = returns.loc[common_idx]
    mv = mv.loc[common_idx]

    # 用最后 N_PERIODS 天, Top N 股票 (按最新市值)
    if len(returns) > N_PERIODS:
        returns = returns.iloc[-N_PERIODS:]
        mv = mv.iloc[-N_PERIODS:]

    latest_mv = mv.iloc[-1]
    top_stocks = latest_mv.dropna().sort_values(ascending=False).head(TOP_N).index.tolist()
    available = returns.columns.intersection(top_stocks).tolist()
    returns = returns[available]
    print(f"  Selected: {len(returns)} periods × {len(available)} stocks (Top {TOP_N} by market cap)")

    # 3. 构造因子
    print("Constructing factors...")

    # momentum_1m: 21日累计对数收益
    # 收益数据有大量NaN (停牌/未上市), 用 forward-fill 后计算
    ret_filled = returns.ffill(limit=5)  # 最多前向填充5天
    log_ret = np.log(1 + ret_filled.clip(-0.5, 0.5))  # clip 防极端值
    mom = log_ret.rolling(21, min_periods=10).sum().iloc[21:]
    mom = mom.replace([np.inf, -np.inf], np.nan)

    # volatility_1m: 21日滚动年化波动率
    vol = returns.rolling(21).std().iloc[21:] * np.sqrt(252)

    # turnover: 加载月频换手率, 前向填充到日频
    turnover_raw = pd.read_pickle(os.path.join(DATA_ROOT, 'price_volume_factors', 'UTR_turnover.pkl'))
    if isinstance(turnover_raw.index, pd.DatetimeIndex):
        turnover_raw = turnover_raw.sort_index()
    # reindex 到日频并前向填充
    common_cols = returns.columns.intersection(turnover_raw.columns)
    turnover_daily = turnover_raw[common_cols].reindex(returns.index, method='ffill')
    turnover_daily = turnover_daily.iloc[21:]  # skip NaN window

    # 对齐时间
    mom = mom.loc[turnover_daily.index.intersection(vol.index)].copy()
    vol = vol.loc[mom.index].copy()
    turnover_daily = turnover_daily.loc[mom.index].copy()

    factor_data = {
        'momentum_1m': mom,
        'volatility_1m': vol,
        'turnover': turnover_daily,
    }
    print(f"  Factors: {list(factor_data.keys())}")
    for k, v in factor_data.items():
        nan_pct = v.isnull().mean().mean() * 100
        print(f"    {k}: shape={v.shape}, NaN={nan_pct:.1f}%")

    # 4. fwd_returns: 下一日收益 (shift -1)
    # 注意: returns 已经截断到 N_PERIODS, factor_data 是 iloc[21:]
    # 需要对 fwd_returns 做相同截断
    fwd_returns = returns.shift(-1)
    common_dates = mom.index.intersection(fwd_returns.index)
    fwd_returns = fwd_returns.loc[common_dates]
    factor_data = {k: v.loc[common_dates] for k, v in factor_data.items()}

    # 5. 行业数据 (只取最后一行, 避免加载 3510×5344 全量)
    print("Loading industry data (last row only)...")
    import pickle as _pkl
    with open(os.path.join(DATA_ROOT, 'market_data', 'stock_ind.pkl'), 'rb') as _f:
        ind_raw = _pkl.load(_f)
    if isinstance(ind_raw, pd.DataFrame):
        last_ind = ind_raw.iloc[-1]
    else:
        last_ind = ind_raw
    # intersect with factor stocks
    common = fwd_returns.columns.intersection(last_ind.index)
    industry_data = last_ind.loc[common] if len(common) > 0 else None
    if industry_data is not None and not isinstance(industry_data, pd.Series):
        industry_data = pd.Series(industry_data.values, index=common)

    factor_data = {k: v[common] for k, v in factor_data.items()}
    fwd_returns = fwd_returns[common]

    print(f"\nFinal shapes after alignment:")
    print(f"  factor_data: {', '.join(f'{k}={v.shape}' for k, v in factor_data.items())}")
    print(f"  fwd_returns: {fwd_returns.shape}")
    print(f"  industry_data: {industry_data.shape if industry_data is not None else 'None'}")
    print(f"  Periods: {len(common_dates)} days")
    print(f"  Stocks: {len(common)}")

    return factor_data, fwd_returns, industry_data


def run_ablation(factor_data, fwd_returns, industry_data):
    base_config = PipelineV2Config()
    runner = AblationRunner(base_config, alpha=0.05, n_bootstrap=500, random_seed=SEED)

    print("\n1/3 Running Baselines (B0-B3)...")
    t0 = time.time()
    baselines = runner.run_baselines(factor_data, fwd_returns, industry_data)
    b3 = baselines[-1]
    print(f"   B3: IC_mean={b3.metrics.get('ic_mean',np.nan):.4f}, "
          f"ICIR={b3.metrics.get('ic_ir',np.nan):.2f}, "
          f"Sharpe={b3.metrics.get('sharpe_ls',np.nan):.2f} ({time.time()-t0:.0f}s)")

    # 报告 B0-B3 阶梯
    for b, label in zip(baselines, ['B0_raw', 'B1_imputer', 'B2_static', 'B3_full']):
        print(f"   {label}: IC={b.metrics.get('ic_mean',0):.4f}, "
              f"Sharpe={b.metrics.get('sharpe_ls',0):.3f}, "
              f"MaxDD={b.metrics.get('max_drawdown',0):.3f}")

    print("\n2/3 Running L1 Component Ablation (5 modules)...")
    t0 = time.time()
    l1_results = runner.run_l1(factor_data, fwd_returns, industry_data, b3_full_result=b3)
    l1_comps = runner.compare_all(l1_results, b3)
    print(f"   {len(l1_results)} configs, {len(l1_comps)} comparisons "
          f"({sum(1 for c in l1_comps if c.is_significant)} significant) ({time.time()-t0:.0f}s)")

    print("\n3/3 Running L2 Routing Ablation...")
    t0 = time.time()
    try:
        l2_results = runner.run_l2(factor_data, fwd_returns, industry_data, b3_full_result=b3)
        l2_comps = runner.compare_all(l2_results, b3)
        print(f"   L2: {len(l2_results)} configs ({time.time()-t0:.0f}s)")
    except Exception as e:
        print(f"   L2 skipped: {e}")
        l2_results, l2_comps = [], []

    return {
        'baselines': baselines,
        'b3': b3,
        'l1_results': l1_results, 'l1_comparisons': l1_comps,
        'l2_results': l2_results, 'l2_comparisons': l2_comps,
    }


def analyze_and_save(results, factor_data, fwd_returns, industry_data):
    b3 = results['b3']

    print("\n" + "=" * 64)
    print("Contributions Analysis")
    print("=" * 64)
    print(f"\nBaseline B3: IC_mean={b3.metrics.get('ic_mean',0):.4f}, "
          f"ICIR={b3.metrics.get('ic_ir',np.nan):.2f}, "
          f"Sharpe={b3.metrics.get('sharpe_ls',0):.4f}")
    print(f"MaxDD={b3.metrics.get('max_drawdown',np.nan):.4f}, "
          f"HitRate={b3.metrics.get('hit_rate',np.nan):.4f}")

    # L1 贡献度排名
    print("\nL1 模块贡献度 (vs B3 full pipeline):")
    print(f"  {'模块':<24} {'ΔIC':>8} {'ΔSharpe':>8} {'IC%':>7} {'Sharpe%':>8} {'p_HAC':>7} {'p_Boot':>7} {'显著':>4}")
    print(f"  {'-'*75}")

    contributions = []
    for c in results['l1_comparisons']:
        if c._is_trivial:
            continue
        name = c.experiment.replace('L1_', '').replace('_off', '')
        ic_pct = c.delta_ic / (abs(b3.metrics.get('ic_mean', 0.001)) + 1e-10) * 100
        sr_pct = c.delta_sharpe / (abs(b3.metrics.get('sharpe_ls', 0.001)) + 1e-10) * 100
        sig = '**' if c.is_significant else '  '
        print(f"  {name:<24} {c.delta_ic:>8.4f} {c.delta_sharpe:>8.4f} "
              f"{ic_pct:>6.1f}% {sr_pct:>7.1f}% {c.p_value_hac:>7.4f} {c.p_value_bootstrap:>7.4f} {sig:>4}")
        contributions.append({
            'module': name,
            'delta_ic': float(c.delta_ic),
            'delta_sharpe': float(c.delta_sharpe),
            'ic_impact_pct': round(ic_pct, 1),
            'sharpe_impact_pct': round(sr_pct, 1),
            'p_value_hac': float(c.p_value_hac),
            'p_value_bootstrap': float(c.p_value_bootstrap),
            'is_significant': c.is_significant,
        })

    # L2 路由消融
    if results['l2_comparisons']:
        print(f"\nL2 路由消融 ({len(results['l2_comparisons'])} 比较):")
        print(f"  {'配置':<30} {'ΔIC':>8} {'ΔSharpe':>8} {'显著':>4}")
        for c in results['l2_comparisons']:
            if c._is_trivial:
                continue
            print(f"  {c.experiment:<30} {c.delta_ic:>8.4f} {c.delta_sharpe:>8.4f} "
                  f"{'**' if c.is_significant else '  ':>4}")

    # 保存结果
    out_dir = os.path.join(_PROJECT, 'notebooks')
    os.makedirs(out_dir, exist_ok=True)

    summary = {
        'data_info': {
            'n_periods': list(factor_data.values())[0].shape[0],
            'n_stocks': list(factor_data.values())[0].shape[1],
            'n_factors': len(factor_data),
            'factor_names': list(factor_data.keys()),
            'has_industry': industry_data is not None,
        },
        'b3_baseline': {k: float(v) for k, v in b3.metrics.items() if not np.isnan(v)},
        'l1_contributions': contributions,
        'l1_n_significant': sum(1 for c in contributions if c['is_significant']),
        'l2_n_comparisons': len(results['l2_comparisons']),
    }

    with open(os.path.join(out_dir, 'ablation_real_results.json'), 'w') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Markdown 报告 (catch NaN in string formatting)
    try:
        report = AblationRunner.generate_report(
            list(results['baselines']) + list(results['l1_results']),
            list(results['l1_comparisons']),
        )
        with open(os.path.join(out_dir, 'ablation_real_report.md'), 'w', encoding='utf-8') as f:
            f.write(report)
    except Exception as e:
        print(f"   Report generation skipped (formatting issue): {e}")

    print(f"\nSaved: notebooks/ablation_real_results.json + notebooks/ablation_real_report.md")

    # 与合成数据对比
    syn_path = os.path.join(out_dir, 'ablation_results.json')
    if os.path.exists(syn_path):
        with open(syn_path) as f:
            syn = json.load(f)
        print("\n" + "=" * 64)
        print("Synthetic vs Real Data Comparison")
        print("=" * 64)
        print(f"  {'Module':<24} {'Syn ΔIC':>8} {'Real ΔIC':>8} {'Syn p':>7} {'Real p':>7}")
        syn_map = {c['config'].replace('L1_', '').replace('_off', ''): c
                   for c in syn['l1_contributions']
                   if c['config'] != 'B3_baseline'}
        for c in contributions:
            s = syn_map.get(c['module'], {})
            syn_di = s.get('delta_ic', 0)
            syn_p = s.get('p_hac', 1)
            print(f"  {c['module']:<24} {syn_di:>8.4f} {c['delta_ic']:>8.4f} "
                  f"{syn_p:>7.4f} {c['p_value_hac']:>7.4f}")

    return summary


def main():
    print("=" * 64)
    print("Factor Pipeline v3.1.0 — Real A-Share Ablation")
    print("=" * 64)

    factor_data, fwd_returns, industry_data = load_real_data()
    results = run_ablation(factor_data, fwd_returns, industry_data)
    summary = analyze_and_save(results, factor_data, fwd_returns, industry_data)

    print("\n" + "=" * 64)
    print("ALL DONE")
    print("=" * 64)
    return summary


if __name__ == '__main__':
    summary = main()
