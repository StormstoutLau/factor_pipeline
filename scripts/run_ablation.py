# -*- coding: utf-8 -*-
"""
消融实验运行脚本 — 生成合成数据 + 全四级消融 + 模块贡献度分析

规格: docs/EXECUTION_ABLATION_V3.0.0.md
产出: 消融报告 (Markdown) + 模块贡献度 JSON
"""
import sys, os, json, warnings, time
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _PROJECT_ROOT)

from tests.test_pipelines_v2 import TestDataGenerator
from factor_pipeline.pipelines_v2 import PipelineV2Config, FactorProcessingPipelineV2
from factor_pipeline.backtest.ablation_runner import AblationRunner


def generate_factor_data(n_periods=120, n_stocks=50, seed=42):
    rng = np.random.default_rng(seed)
    factor_data = {
        'static_factor': TestDataGenerator.generate_static_factor(n_periods, n_stocks, seed),
        'dynamic_factor': TestDataGenerator.generate_dynamic_factor(n_periods, n_stocks, seed + 1),
        'mixed_factor': TestDataGenerator.generate_mixed_factor(n_periods, n_stocks, seed + 2),
    }
    industry_data = TestDataGenerator.generate_industry_data(n_stocks, 5, seed + 3)
    fwd_returns = pd.DataFrame(
        rng.standard_normal((n_periods, n_stocks)) * 0.02 + 0.005,
        index=factor_data['static_factor'].index,
        columns=factor_data['static_factor'].columns,
    )
    return factor_data, fwd_returns, industry_data


def run_full_ablation(factor_data, fwd_returns, industry_data=None):
    base_config = PipelineV2Config()
    runner = AblationRunner(base_config, alpha=0.05, n_bootstrap=200, random_seed=42)

    print("1/2 Running Baselines (B0-B3)...")
    t0 = time.time()
    baselines = runner.run_baselines(factor_data, fwd_returns, industry_data)
    b3 = baselines[-1]
    print(f"   B0→B3 done: IC={b3.metrics.get('ic_mean',np.nan):.4f}, "
          f"Sharpe={b3.metrics.get('sharpe_ls',np.nan):.2f} ({time.time()-t0:.1f}s)")

    print("2/2 Running L1 Component Ablation (5 modules)...")
    t0 = time.time()
    l1_results = runner.run_l1(factor_data, fwd_returns, industry_data, b3_full_result=b3)
    l1_comps = runner.compare_all(l1_results, b3)
    print(f"   L1 done: {len(l1_results)} configs, {len(l1_comps)} comparisons ({time.time()-t0:.1f}s)")

    return {
        'baselines': baselines,
        'l1_results': l1_results, 'l1_comparisons': l1_comps,
    }


def analyze_contributions(results):
    """分析各模块对 IC 和 Sharpe 的贡献度"""
    b3_ic = results['baselines'][-1].metrics.get('ic_mean', 0.0)
    b3_sharpe = results['baselines'][-1].metrics.get('sharpe_ls', 0.0)

    def _impact(comp):
        delta_ic = comp.delta_ic / (abs(b3_ic) + 1e-10)
        delta_sharpe = comp.delta_sharpe / (abs(b3_sharpe) + 1e-10)
        return delta_ic, delta_sharpe, comp.is_significant

    contributions = []

    # L1 组件消融
    for c in results['l1_comparisons']:
        di, ds, sig = _impact(c)
        contributions.append({
            'layer': 'L1', 'config': c.experiment, 'reference': c.reference,
            'delta_ic': c.delta_ic, 'delta_sharpe': c.delta_sharpe,
            'ic_impact_pct': round(di * 100, 1), 'sharpe_impact_pct': round(ds * 100, 1),
            'significant': sig, 'p_hac': round(c.p_value_hac, 4),
        })

    return pd.DataFrame(contributions), b3_ic, b3_sharpe


def print_module_ranking(df_contrib):
    l1 = df_contrib.sort_values('delta_ic', key=abs, ascending=False)
    print("\n  L1 模块贡献度排名 (按 |ΔIC| 降序):")
    print(f"  {'模块':<30} {'ΔIC':>8} {'ΔSharpe':>8} {'IC影响%':>8} {'显著':>4}")
    print(f"  {'-'*62}")
    for _, row in l1.iterrows():
        name = row['config'].replace('L1_', '')
        print(f"  {name:<30} {row['delta_ic']:>8.4f} {row['delta_sharpe']:>8.4f} "
              f"{row['ic_impact_pct']:>7.1f}% {'**' if row['significant'] else '':>4}")


def main():
    print("=" * 62)
    print("Factor Pipeline v3.1.0 — Ablation Experiment")
    print("=" * 62)

    print("\nGenerating synthetic factor data (120 periods x 50 stocks)...")
    factor_data, fwd_returns, industry_data = generate_factor_data(120, 50, seed=42)

    print(f"\n3 factors: {list(factor_data.keys())}")
    print(f"Shapes: {', '.join(f'{k}={v.shape}' for k, v in factor_data.items())}")

    results = run_full_ablation(factor_data, fwd_returns, industry_data)

    print("\n" + "=" * 62)
    print("Contributions Analysis")
    print("=" * 62)

    df_contrib, b3_ic, b3_sharpe = analyze_contributions(results)
    print(f"\nB3 Baseline: IC_mean={b3_ic:.4f}, Sharpe={b3_sharpe:.4f}")
    print(f"L1 comparisons: {len(results['l1_comparisons'])} "
          f"({sum(1 for c in results['l1_comparisons'] if c.is_significant)} significant)")

    print_module_ranking(df_contrib)

    # 保存结果
    out_dir = os.path.join(_PROJECT_ROOT, 'notebooks')
    os.makedirs(out_dir, exist_ok=True)

    ablation_summary = {
        'b3_baseline': {'ic_mean': float(b3_ic), 'sharpe_ls': float(b3_sharpe)},
        'l1_contributions': [
            {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
             for k, v in row.items()}
            for _, row in df_contrib.iterrows()
        ],
    }
    with open(os.path.join(out_dir, 'ablation_results.json'), 'w') as f:
        json.dump(ablation_summary, f, indent=2, ensure_ascii=False)
    print(f"Contributions DataFrame: {len(df_contrib)} rows")
    print("ALL DONE")
    return df_contrib, ablation_summary


if __name__ == '__main__':
    df_contrib, summary = main()
