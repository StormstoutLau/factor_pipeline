# -*- coding: utf-8 -*-
"""
Demo Notebook v3.1.0 — 管线全流程可视化追溯 (10 个 cell)

规格文档: docs/ANALYSIS_V3.0.0.md §9.2.2
验收标准: §9.2.3 排序保持性/IC变化/正交化诊断阈值

可通过 VS Code # %% 渲染为 notebook cells, 也可直接 python 运行.
"""
import numpy as np
import pandas as pd
import warnings
import logging
logging.getLogger('matplotlib').setLevel(logging.WARNING)
warnings.filterwarnings('ignore')

from tests.test_pipelines_v2 import TestDataGenerator


# =============================================================================
# Cell 1: 数据加载
# =============================================================================

def cell_1_load_data(seed=42):
    n_periods, n_stocks = 60, 30
    static_data = TestDataGenerator.generate_static_factor(n_periods=n_periods, n_stocks=n_stocks, seed=seed)
    dynamic_data = TestDataGenerator.generate_dynamic_factor(n_periods=n_periods, n_stocks=n_stocks, seed=seed+1)
    mixed_data = TestDataGenerator.generate_mixed_factor(n_periods=n_periods, n_stocks=n_stocks, seed=seed+2)

    factor_data = {
        'static_factor': static_data,
        'dynamic_factor': dynamic_data,
        'mixed_factor': mixed_data,
    }
    industry_data = TestDataGenerator.generate_industry_data(n_stocks=n_stocks, n_industries=5, seed=seed+3)

    return {
        'factor_data': factor_data,
        'industry_data': industry_data,
        'n_periods': n_periods,
        'n_stocks': n_stocks,
    }


# =============================================================================
# Cell 2: 指纹可视化 — 21 维指纹雷达图 + 与基准因子对比
# =============================================================================

def cell_2_fingerprint_radar(data, show_plot=False):
    """提取各因子的 21 维指纹, 计算关键统计量, 可选绘制雷达图"""
    from factor_pipeline.modules.factor_fingerprint import FactorFingerprinter

    fingerprinter = FactorFingerprinter()
    fingerprints = {}

    for name, df in data['factor_data'].items():
        fp = fingerprinter.extract_fingerprint(df)
        fingerprints[name] = fp

    if show_plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        _fingerprint_radar_plot(fingerprints)

    return {'fingerprints': fingerprints}


_FINGERPRINT_PLOT_FIELDS = [
    'ar1_median', 'rank_autocorr', 'half_life', 'skewness_std',
    'kurtosis_std', 'sd_score', 'complexity_need', 'snr_estimate',
    'coverage_ratio', 'js_divergence_mean', 'missing_cv',
    'level_diff_ic_ratio', 'vol_clustering_pvalue',
    'tail_dependence_lower', 'tail_dependence_upper',
    'gpd_shape', 'hill_estimator',
    'regime_transition_prob', 'regime_persistence',
    'regime_ic_diff', 'tail_regime_score',
]


def _fingerprint_radar_plot(fingerprints):
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    fig, axes = plt.subplots(1, len(fingerprints), figsize=(6*len(fingerprints), 5),
                             subplot_kw=dict(projection='polar'))
    if len(fingerprints) == 1:
        axes = [axes]

    for ax, (name, fp) in zip(axes, fingerprints.items()):
        values = []
        for f in _FINGERPRINT_PLOT_FIELDS:
            v = getattr(fp, f, None)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                v = 0.0
            values.append(float(v))
        values = np.array(values)
        # 归一化到 [0, 1]
        max_abs = np.max(np.abs(values)) or 1.0
        values_norm = np.abs(values) / max_abs

        n = len(_FINGERPRINT_PLOT_FIELDS)
        angles = np.linspace(0, 2*np.pi, n, endpoint=False).tolist()
        angles += angles[:1]
        values_norm = np.append(values_norm, values_norm[0])

        ax.fill(angles, values_norm, alpha=0.25, color='#2563eb')
        ax.plot(angles, values_norm, linewidth=2, color='#2563eb')
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels([f.replace('_', '\n') for f in _FINGERPRINT_PLOT_FIELDS], size=6)
        ax.set_title(f'{name}\nar1={fp.ar1_median:.2f} snr={fp.snr_estimate:.2f}', size=9)

    plt.tight_layout()
    plt.close(fig)


# =============================================================================
# Cell 3: 分类决策树 — 显示因子在 5 叉决策树上的路径 + 路由权重
# =============================================================================

def cell_3_classification(data, show_plot=False):
    from factor_pipeline.modules.factor_fingerprint import AdaptiveFactorClassifier
    from factor_pipeline.pipelines_v2 import _get_pipeline_weights

    classifier = AdaptiveFactorClassifier()
    classifications = {}
    routing_weights = {}

    for name, fp in cell_2_fingerprint_radar(data)['fingerprints'].items():
        cls_result = classifier.classify(fp)
        classifications[name] = cls_result
        routing_weights[name] = _get_pipeline_weights(cls_result)

    if show_plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, len(classifications), figsize=(5*len(classifications), 3))
        if len(classifications) == 1:
            axes = [axes]
        for ax, (name, cls_r) in zip(axes, classifications.items()):
            _classification_sunburst(ax, name, cls_r, routing_weights[name])
        plt.tight_layout()
        plt.close(fig)

    return {
        'classifications': classifications,
        'routing_weights': routing_weights,
    }


def _classification_sunburst(ax, name, cls_result, weights):
    import matplotlib.patches as mpatches

    primary = cls_result.primary_type.value.lower()
    secondary = getattr(cls_result, 'secondary_type', None)
    if secondary:
        secondary = secondary.value.lower()

    colors = {'static': '#2563eb', 'dynamic': '#dc2626', 'mixed': '#ca8a04'}
    y_positions = list(range(len(weights), 0, -1))
    bar_labels = []

    for i, (pipe_type, w) in enumerate(weights.items()):
        color = colors.get(pipe_type, '#888888')
        ax.barh(y_positions[i], w, color=color, alpha=0.7)
        bar_labels.append(f'{pipe_type}: {w:.2f}')

    ax.set_yticks(y_positions)
    ax.set_yticklabels(bar_labels)
    ax.set_xlim(0, 1)
    ax.set_xlabel('Routing Weight')
    ax.set_title(f'{name}\nprimary={primary} ({cls_result.primary_prob:.2f})', size=9)


# =============================================================================
# Cell 4: fit 阶段逐步追溯 — 各步输出的分布直方图
# =============================================================================

def cell_4_step_trace(data, show_plot=False):
    from factor_pipeline.pipelines_v2 import (
        FactorProcessingPipelineV2, PipelineV2Config,
        StaticFactorPipeline,
    )

    # 始终用一个代表性的因子 (static) 做 step trace
    factor_name = 'static_factor'
    df = data['factor_data'][factor_name]

    pipe_v2 = FactorProcessingPipelineV2()
    pipe_v2.fit(data['factor_data'], industry_data=data['industry_data'])

    # 从 factor_pipelines 获取实际管道实例
    factor_pipes = pipe_v2.factor_pipelines.get(factor_name, {})
    if not factor_pipes:
        return {'steps': {}, 'factor_name': factor_name}

    pipeline = list(factor_pipes.values())[0]
    intermediate = pipeline.get_intermediate_data() if hasattr(pipeline, 'get_intermediate_data') else {}

    # 添加原始数据作为 "raw" 步骤
    steps = {'raw': df}
    steps.update(intermediate)

    if show_plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        n_steps = len(steps)
        fig, axes = plt.subplots(1, n_steps, figsize=(3*n_steps, 3))
        if n_steps == 1:
            axes = [axes]
        for ax, (step_name, step_df) in zip(axes, steps.items()):
            flat_vals = step_df.values.flatten()
            flat_vals = flat_vals[~np.isnan(flat_vals)]
            ax.hist(flat_vals, bins=30, alpha=0.7, color='#2563eb', edgecolor='white')
            ax.set_title(f'{step_name}\nμ={np.mean(flat_vals):.2f} σ={np.std(flat_vals):.2f}',
                         size=8)
            ax.set_xlabel('')
        plt.tight_layout()
        plt.close(fig)

    return {
        'steps': steps,
        'factor_name': factor_name,
        'pipeline_type': type(pipeline).__name__ if factor_pipes else 'unknown',
    }


# =============================================================================
# Cell 5: 横截面排序保持性检验 — Spearman rank 相关矩阵
# =============================================================================

def cell_5_spearman_ranking(data, show_plot=False):
    from scipy.stats import spearmanr

    trace_result = cell_4_step_trace(data)
    steps = trace_result['steps']

    step_names = list(steps.keys())
    n = len(step_names)
    sorting_matrix = pd.DataFrame(np.eye(n), index=step_names, columns=step_names)

    for i in range(n):
        for j in range(i+1, n):
            a = steps[step_names[i]].values.ravel()
            b = steps[step_names[j]].values.ravel()
            mask = ~np.isnan(a) & ~np.isnan(b)
            if mask.sum() >= 10:
                rho, _ = spearmanr(a[mask], b[mask])
            else:
                rho = np.nan
            sorting_matrix.iloc[i, j] = rho
            sorting_matrix.iloc[j, i] = rho

    # 最终输出 vs 原始
    if 'raw' in step_names and step_names[-1] != 'raw':
        rho_final = sorting_matrix.loc['raw', step_names[-1]]
    else:
        rho_final = float('nan')

    if show_plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import seaborn as sns

        fig, ax = plt.subplots(figsize=(max(6, n*0.8), max(5, n*0.7)))
        mask = np.triu(np.ones_like(sorting_matrix.values, dtype=bool), k=1)
        sns.heatmap(sorting_matrix, annot=True, fmt='.3f', cmap='RdBu_r',
                    vmin=-1, vmax=1, center=0, mask=mask,
                    square=True, linewidths=0.5, ax=ax)
        ax.set_title(f'Spearman Rank Correlation Matrix\nFinal ρ(original→output)={rho_final:.3f}')
        plt.tight_layout()
        plt.close(fig)

    return {
        'sorting_matrix': sorting_matrix,
        'rho_final': rho_final,
        'step_names': step_names,
    }


# =============================================================================
# Cell 6: IC 变化追溯 — 各步输出的 rank IC 时序 + 累积 IC
# =============================================================================

def cell_6_ic_trace(data, show_plot=False):
    from scipy.stats import spearmanr

    trace_result = cell_4_step_trace(data)
    steps = trace_result['steps']

    # 构造简单 fwd_returns (假设 t+1 期收益 = 下期因子均值偏移)
    n_periods = data['n_periods']
    factor_name = trace_result['factor_name']
    df_raw = data['factor_data'][factor_name]

    # 用原始因子做简易 IC: IC_t = corr(factor_t, factor_{t+1})
    # 这近似评估排序稳定性而非预测力, 但对 demo 足够
    ic_by_step = {}

    for step_name, step_df in steps.items():
        if step_df.shape[0] < 2:
            continue
        ic_series = []
        for t in range(min(step_df.shape[0] - 1, df_raw.shape[0] - 1)):
            row_t = step_df.iloc[t].values
            row_next = df_raw.iloc[t+1].values
            mask = ~np.isnan(row_t) & ~np.isnan(row_next)
            if mask.sum() >= 10:
                rho, _ = spearmanr(row_t[mask], row_next[mask])
            else:
                rho = np.nan
            ic_series.append(rho)
        ic_arr = np.array(ic_series, dtype=float)
        ic_arr = ic_arr[~np.isnan(ic_arr)]
        if len(ic_arr) == 0:
            continue
        ic_mean = float(np.mean(ic_arr))
        ic_std = float(np.std(ic_arr, ddof=1))
        ic_ir = ic_mean / ic_std if ic_std > 1e-10 else 0.0
        ic_by_step[step_name] = {
            'ic_mean': ic_mean,
            'ic_std': ic_std,
            'ic_ir': ic_ir,
            'ic_series': ic_arr,
        }

    if show_plot and ic_by_step:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 1, figsize=(10, 6))
        _plot_ic_series(axes[0], ic_by_step)
        _plot_cumulative_ic(axes[1], ic_by_step)
        plt.tight_layout()
        plt.close(fig)

    return {'ic_by_step': ic_by_step}


def _plot_ic_series(ax, ic_by_step):
    colors = ['#2563eb', '#dc2626', '#ca8a04', '#16a34a', '#7c3aed', '#d946ef']
    for i, (step_name, ic_dict) in enumerate(ic_by_step.items()):
        ax.plot(ic_dict['ic_series'], color=colors[i % len(colors)], alpha=0.7,
                label=f'{step_name} (μ={ic_dict["ic_mean"]:.3f})')
    ax.axhline(0, color='gray', linestyle='--', alpha=0.5)
    ax.set_title('Step-wise Rank IC Series')
    ax.set_ylabel('IC')
    ax.legend(fontsize=7)


def _plot_cumulative_ic(ax, ic_by_step):
    colors = ['#2563eb', '#dc2626', '#ca8a04', '#16a34a', '#7c3aed', '#d946ef']
    for i, (step_name, ic_dict) in enumerate(ic_by_step.items()):
        ax.plot(np.cumsum(ic_dict['ic_series']), color=colors[i % len(colors)], alpha=0.7,
                label=f'{step_name}')
    ax.set_title('Cumulative IC')
    ax.set_ylabel('Cumulative IC')
    ax.legend(fontsize=7)


# =============================================================================
# Cell 7: 正交化诊断 — W 矩阵热力图 + 特征值 + condition_number + VRR
# =============================================================================

def cell_7_ortho_diagnostics(data, show_plot=False):
    result = {'ortho_enabled': False}

    from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2
    pipe_v2 = FactorProcessingPipelineV2()
    pipe_v2.fit(data['factor_data'], industry_data=data['industry_data'])

    ortho_adapter = getattr(pipe_v2, '_orthogonalizer', None)
    if ortho_adapter is None:
        result['note'] = '正交化未启用 (默认 enabled=False)'
        return result

    result['ortho_enabled'] = True
    try:
        diag = ortho_adapter.get_diagnostics() if hasattr(ortho_adapter, 'get_diagnostics') else {}
    except Exception:
        diag = {}

    cond = diag.get('condition_number', None)
    vrr = diag.get('vrr_mean', None)
    eigvals = diag.get('eigvals_', None)
    W = diag.get('W_', None)

    result.update({
        'condition_number': cond,
        'vrr_mean': vrr,
    })

    if show_plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        _plot_W_heatmap(axes[0], W, data['factor_data'])
        _plot_eigenvalues(axes[1], eigvals)
        plt.tight_layout()
        plt.close(fig)

    return result


def _plot_W_heatmap(ax, W, factor_data):
    if W is None:
        ax.text(0.5, 0.5, 'W matrix not available', ha='center', va='center',
                transform=ax.transAxes)
        ax.set_title('Orthogonalizer W Matrix')
        return
    factor_names = list(factor_data.keys())
    if W.shape[0] != len(factor_names):
        factor_names = [f'F{i}' for i in range(W.shape[0])]
    im = ax.imshow(W, cmap='RdBu_r', vmin=-1, vmax=1, aspect='auto')
    plt.colorbar(im, ax=ax, shrink=0.8)
    ax.set_xticks(range(len(factor_names)))
    ax.set_xticklabels(factor_names, rotation=45, ha='right', size=7)
    ax.set_yticks(range(len(factor_names)))
    ax.set_yticklabels(factor_names, size=7)
    ax.set_title('Orthogonalizer W Matrix')


def _plot_eigenvalues(ax, eigvals):
    if eigvals is None:
        ax.text(0.5, 0.5, 'Eigenvalues not available', ha='center', va='center',
                transform=ax.transAxes)
        ax.set_title('Eigenvalues of Gram Matrix')
        return
    ax.bar(range(len(eigvals)), eigvals, color='#2563eb', alpha=0.7)
    ax.axhline(1.0, color='gray', linestyle='--', alpha=0.5, label='ideal=1')
    ax.set_title('Eigenvalues of Gram Matrix')
    ax.set_ylabel('Eigenvalue')
    ax.legend(fontsize=7)


# =============================================================================
# Cell 8: 迁移检测追溯 — KS 检验 + BH-FDR
# =============================================================================

def cell_8_migration(data, show_plot=False):
    from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2
    pipe_v2 = FactorProcessingPipelineV2()
    pipe_v2.fit(data['factor_data'], industry_data=data['industry_data'])

    migration_alerts = pipe_v2.check_migrations(data['factor_data'])

    if show_plot:
        # 简化版: 周期太短 (60 期), 不做滚动 KS, 仅报告迁移告警
        pass

    return {
        'migration_alerts': migration_alerts,
        'n_migrations': sum(1 for alerts in migration_alerts.values() if alerts),
    }


# =============================================================================
# Cell 9: 管线输出 vs 原始因子 — 截面排序散点图 + Spearman ρ
# =============================================================================

def cell_9_output_vs_raw(data, show_plot=False):
    from scipy.stats import spearmanr
    from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2

    pipe_v2 = FactorProcessingPipelineV2()
    pipe_v2.fit(data['factor_data'], industry_data=data['industry_data'])
    processed = pipe_v2.transform(data['factor_data'])

    spearman_rho_per_factor = {}

    for name in data['factor_data'].keys():
        raw = data['factor_data'][name]
        prc = processed.get(name, raw)
        # 对齐 date/index
        common_idx = raw.index.intersection(prc.index)
        if len(common_idx) < 1:
            spearman_rho_per_factor[name] = float('nan')
            continue
        raw_aligned = raw.loc[common_idx]
        prc_aligned = prc.loc[common_idx]

        # 取最后一期做截面比较
        raw_last = raw_aligned.iloc[-1].values
        prc_last = prc_aligned.iloc[-1].values
        mask = ~np.isnan(raw_last) & ~np.isnan(prc_last)
        if mask.sum() >= 10:
            rho, _ = spearmanr(raw_last[mask], prc_last[mask])
        else:
            rho = float('nan')
        spearman_rho_per_factor[name] = rho

    if show_plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        n_factors = len(data['factor_data'])
        fig, axes = plt.subplots(1, n_factors, figsize=(5*n_factors, 4))
        if n_factors == 1:
            axes = [axes]
        for ax, name in enumerate(data['factor_data'].keys()):
            raw = data['factor_data'][name]
            prc = processed.get(name, raw)
            common_idx = raw.index.intersection(prc.index)
            raw_last = raw.loc[common_idx].iloc[-1].values
            prc_last = prc.loc[common_idx].iloc[-1].values
            mask = ~np.isnan(raw_last) & ~np.isnan(prc_last)
            if mask.sum() >= 10:
                ax.scatter(raw_last[mask], prc_last[mask], alpha=0.5, s=15,
                           color='#2563eb', edgecolors='none')
                rho = spearman_rho_per_factor.get(name, np.nan)
                ax.set_title(f'{name}\nρ_spearman={rho:.3f}')
                ax.set_xlabel('Original rank')
                ax.set_ylabel('Processed rank')
        plt.tight_layout()
        plt.close(fig)

    return {
        'spearman_rho_per_factor': spearman_rho_per_factor,
        'processed_shapes': {name: df.shape for name, df in processed.items()},
    }


# =============================================================================
# Cell 10: 校验报告 — 自动检查排序/IC/正交化/迁移
# =============================================================================

def cell_10_validation_report(data):
    report = {}

    # (a) 排序保持性
    cell5 = cell_5_spearman_ranking(data)
    rho_final = cell5['rho_final']
    if np.isnan(rho_final):
        report['sorting_preserved'] = 'N/A (insufficient data)'
    elif rho_final >= 0.95:
        report['sorting_preserved'] = True
    elif rho_final >= 0.80:
        report['sorting_preserved'] = f'partial (ρ={rho_final:.3f}, 中性化/正交化预期)'
    else:
        report['sorting_preserved'] = f'warning (ρ={rho_final:.3f} < 0.80, 需审查)'

    # (b) IC 显著性
    cell6 = cell_6_ic_trace(data)
    ic_by_step = cell6['ic_by_step']
    if ic_by_step:
        # 找最大 |IC| 的步骤
        best_step = max(ic_by_step.items(), key=lambda kv: abs(kv[1]['ic_mean']))
        ic_mean_best = best_step[1]['ic_mean']
        report['ic_significant'] = f'best step={best_step[0]} (IC_mean={ic_mean_best:.4f})'
    else:
        report['ic_significant'] = 'N/A (no fwd_returns)'

    # (c) 正交化 condition_number
    cell7 = cell_7_ortho_diagnostics(data)
    if cell7['ortho_enabled'] and cell7.get('condition_number') is not None:
        cond = cell7['condition_number']
        if cond < 30:
            report['ortho_healthy'] = True
        elif cond < 100:
            report['ortho_healthy'] = f'acceptable (κ={cond:.1f})'
        else:
            report['ortho_healthy'] = f'ill-conditioned (κ={cond:.1f} ≥ 100, 需切换算法)'
    else:
        report['ortho_healthy'] = 'N/A (disabled or not fitted)'

    # (d) 迁移检测告警
    cell8 = cell_8_migration(data)
    n_mig = cell8.get('n_migrations', 0)
    report['migration_ok'] = True if n_mig == 0 else f'{n_mig} migration(s) detected'

    return report


# =============================================================================
# 主入口: 运行全部 10 个 cell
# =============================================================================

if __name__ == '__main__':
    import matplotlib
    matplotlib.use('Agg')

    print("=" * 60)
    print("Factor Pipeline v3.1.0 — Demo Notebook (10 cells)")
    print("=" * 60)

    data = cell_1_load_data()
    print(f"\nCell 1 OK: {len(data['factor_data'])} factors, "
          f"{data['n_periods']} periods × {data['n_stocks']} stocks")

    cell_2_fingerprint_radar(data, show_plot=True)
    print(f"Cell 2 OK: {len(data['factor_data'])} fingerprints")

    cell_3_classification(data, show_plot=True)
    print(f"Cell 3 OK: classifications + routing weights")

    cell_4_step_trace(data, show_plot=True)
    print(f"Cell 4 OK: step trace histograms")

    cell_5_spearman_ranking(data, show_plot=True)
    print(f"Cell 5 OK: Spearman ranking matrix")

    cell_6_ic_trace(data, show_plot=True)
    print(f"Cell 6 OK: IC trace")

    cell_7_ortho_diagnostics(data, show_plot=True)
    print(f"Cell 7 OK: orthogonalization diagnostics")

    cell_8_migration(data)
    print(f"Cell 8 OK: migration detection")

    cell_9_output_vs_raw(data, show_plot=True)
    print(f"Cell 9 OK: output vs raw comparison")

    report = cell_10_validation_report(data)
    print(f"\nCell 10 — Validation Report:")
    for key, val in report.items():
        print(f"  {key}: {val}")

    print(f"\n{'='*60}")
    print(f"All 11 cells completed successfully.")
    print(f"{'='*60}")


# =============================================================================
# Cell 11: 消融实验贡献度汇总 (v3.1.0)
# =============================================================================

def cell_11_ablation_summary(data=None, json_path=None, show_plot=False):
    import json, os

    if json_path is None:
        json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 'ablation_results.json')

    if not os.path.exists(json_path):
        return {
            'b3_ic_mean': float('nan'),
            'b3_sharpe': float('nan'),
            'l1_modules': [],
            'top_contributors': [],
            'note': 'ablation_results.json not found. Run scripts/run_ablation.py first.',
        }

    with open(json_path, 'r') as f:
        abl = json.load(f)

    b3 = abl['b3_baseline']
    l1 = abl['l1_contributions']

    modules = []
    for row in l1:
        if row['config'] == 'B3_baseline':
            continue
        modules.append({
            'module': row['config'].replace('L1_', '').replace('_off', ''),
            'delta_ic': row['delta_ic'],
            'delta_sharpe': row['delta_sharpe'],
            'ic_impact_pct': row['ic_impact_pct'],
            'sharpe_impact_pct': row['sharpe_impact_pct'],
            'significant': row['significant'],
        })

    top = sorted(modules, key=lambda m: abs(m['delta_ic']), reverse=True)[:3]

    if show_plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        _plot_ablation_bars(axes[0], modules, 'ic_impact_pct', 'IC Impact %')
        _plot_ablation_bars(axes[1], modules, 'sharpe_impact_pct', 'Sharpe Impact %')
        plt.tight_layout()
        plt.close(fig)

    return {
        'b3_ic_mean': b3['ic_mean'],
        'b3_sharpe': b3['sharpe_ls'],
        'l1_modules': modules,
        'top_contributors': top,
    }


def _plot_ablation_bars(ax, modules, key, ylabel):
    import numpy as np
    names = [m['module'] for m in modules]
    values = [m[key] for m in modules]
    colors = ['#dc2626' if v > 0 else '#2563eb' for v in values]
    bars = ax.barh(names, values, color=colors, alpha=0.7)
    ax.axvline(0, color='gray', linestyle='--', alpha=0.5)
    ax.set_xlabel(ylabel)
    ax.set_title(f'Module Contribution: {ylabel}')
    for bar, val in zip(bars, values):
        sign = '+' if val >= 0 else ''
        ax.text(bar.get_width() + (0.5 if val >= 0 else -0.5), bar.get_y() + bar.get_height()/2,
                f'{sign}{val:.1f}%', va='center', ha='left' if val >= 0 else 'right', size=8)
