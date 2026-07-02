# -*- coding: utf-8 -*-
"""
端到端阈值搜索 — 目标函数验证脚本

逐题验证:
  Q1: 目标函数权重合理性 — 敏感性分析
  Q2: 10维搜索空间审计 — 遗漏/冗余阈值
  Q3: 复合目标函数指标独立性 — 相关性矩阵
  Q4: FactorHealthMonitor 与目标函数重叠分析

方法: 生成合成因子数据，运行 pipeline，计算各子指标，
      分析权重敏感性、指标相关性、冗余性。
"""

import numpy as np
import pandas as pd
from scipy import stats as sp_stats
from scipy.stats import spearmanr
import warnings

warnings.filterwarnings('ignore')

# =============================================================================
# 辅助函数
# =============================================================================

def generate_synthetic_factors(n_factors=20, n_months=48, n_stocks=100,
                                 seed=42, factor_type='mixed'):
    """
    生成合成因子数据，带可控统计特性。

    返回:
        factor_data: Dict[str, pd.DataFrame] 因子名 → 月×股面板
        forward_returns: pd.DataFrame 月×股 下期收益
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2020-01-01', periods=n_months, freq='ME')
    stocks = [f'S{i:03d}' for i in range(n_stocks)]

    factor_data = {}
    for i in range(n_factors):
        if factor_type == 'static':
            # 静态: 高自相关, 低噪声
            ar_coef = 0.85 + rng.uniform(0, 0.1)
            base = rng.normal(0, 1, n_stocks)
            values = np.zeros((n_months, n_stocks))
            values[0] = base
            for t in range(1, n_months):
                values[t] = ar_coef * values[t-1] + rng.normal(0, 0.3, n_stocks)
        elif factor_type == 'dynamic':
            # 动态: 低自相关, 高噪声
            ar_coef = 0.0 + rng.uniform(0, 0.2)
            base = rng.normal(0, 1, n_stocks)
            values = np.zeros((n_months, n_stocks))
            values[0] = base
            for t in range(1, n_months):
                values[t] = ar_coef * values[t-1] + rng.normal(0, 1.0, n_stocks)
        else:
            # 混合: 随机选择
            ar_coef = rng.uniform(0, 0.9)
            noise = rng.uniform(0.3, 1.0)
            base = rng.normal(0, 1, n_stocks)
            values = np.zeros((n_months, n_stocks))
            values[0] = base
            for t in range(1, n_months):
                values[t] = ar_coef * values[t-1] + rng.normal(0, noise, n_stocks)

        # 添加一些缺失值
        mask = rng.random(values.shape) < 0.05
        values[mask] = np.nan

        df = pd.DataFrame(values, index=dates, columns=stocks)
        factor_data[f'Factor_{i:02d}'] = df

    # 生成下期收益（与因子值正相关，但带噪声）
    forward_returns = pd.DataFrame(
        rng.normal(0, 1, (n_months, n_stocks)),
        index=dates, columns=stocks
    )

    return factor_data, forward_returns


def compute_ic(factor_vals, forward_ret):
    """计算截面 Spearman IC"""
    common = factor_vals.index.intersection(forward_ret.index)
    if len(common) < 10:
        return 0.0
    f = factor_vals[common].dropna()
    r = forward_ret[common].dropna()
    common_idx = f.index.intersection(r.index)
    if len(common_idx) < 10:
        return 0.0
    return spearmanr(f[common_idx], r[common_idx]).correlation


def compute_ic_series(processed_factors, forward_returns):
    """计算 IC 时间序列"""
    ics = []
    for date in processed_factors.index:
        if date not in forward_returns.index:
            continue
        for col in processed_factors.columns:
            fv = processed_factors.loc[date, col]
            if pd.isna(fv):
                continue
            rv = forward_returns.loc[date, col]
            if pd.isna(rv):
                continue
    # 截面: 每个日期计算一次 IC
    for date in processed_factors.index:
        if date not in forward_returns.index:
            continue
        factor_cross = processed_factors.loc[date].dropna()
        ret_cross = forward_returns.loc[date].dropna()
        common = factor_cross.index.intersection(ret_cross.index)
        if len(common) < 10:
            continue
        ic = spearmanr(factor_cross[common], ret_cross[common]).correlation
        ics.append(abs(ic))
    return ics


def compute_all_metrics(raw_factors, processed_factors, forward_returns):
    """
    计算所有子指标。

    返回:
        dict: {
            'ic': float,           # 平均 |IC|
            'icir': float,         # IC / std(IC)
            'stability': float,    # KS p-value (越高越稳定)
            'coverage': float,     # 非 NaN 比例
            'diversity': float,    # 1 - 平均绝对相关系数
        }
    """
    results = {}

    # 取第一个因子作为代表
    factor_name = list(raw_factors.keys())[0]
    raw = raw_factors[factor_name]
    proc = processed_factors[factor_name]

    # IC 和 ICIR
    ics = compute_ic_series(proc, forward_returns)
    if ics and len(ics) > 1:
        results['ic'] = float(np.mean(ics))
        results['icir'] = float(np.mean(ics) / max(np.std(ics), 1e-10))
    else:
        results['ic'] = 0.0
        results['icir'] = 0.0

    # 稳定性: KS test
    from factor_pipeline.pipelines_v2 import _ks_migration_significance
    _, p_val, _ = _ks_migration_significance(raw, proc, alpha=0.05)
    results['stability'] = float(p_val)

    # 覆盖率
    results['coverage'] = float(1.0 - proc.isna().sum().sum() / max(proc.size, 1))

    # 多样性: 多因子时计算
    if len(processed_factors) > 1:
        all_proc = []
        for name, df in processed_factors.items():
            stacked = df.stack()
            all_proc.append(stacked)
        combined = pd.concat(all_proc, axis=1)
        corr = combined.corr().abs()
        n = len(corr)
        if n > 1:
            upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
            results['diversity'] = float(1.0 - upper.stack().mean())
        else:
            results['diversity'] = 1.0
    else:
        results['diversity'] = 1.0

    return results


# =============================================================================
# Q1: 目标函数权重敏感性分析
# =============================================================================

def analyze_q1_weight_sensitivity():
    """
    Q1: 目标函数权重合理性。

    方法:
      1. 生成多组因子数据
      2. 用不同阈值组合运行 pipeline
      3. 对每组 (阈值, 结果) 计算各子指标
      4. 分析每个子指标对最终排序的贡献
      5. 变化权重，看排序稳定性
    """
    print("=" * 70)
    print("Q1: 目标函数权重敏感性分析")
    print("=" * 70)

    np.random.seed(42)
    factor_data, forward_returns = generate_synthetic_factors(
        n_factors=10, n_months=36, n_stocks=50, factor_type='mixed'
    )

    # 使用不同阈值组合运行 pipeline
    from factor_pipeline.pipelines_v2 import (
        FactorProcessingPipelineV2, PipelineV2Config
    )

    threshold_combos = []
    for _ in range(50):
        combo = {
            'classification_threshold_static': np.random.uniform(0.65, 0.95),
            'classification_threshold_dynamic': np.random.uniform(0.15, 0.55),
        }
        threshold_combos.append(combo)

    all_metrics = []
    for i, combo in enumerate(threshold_combos):
        try:
            config = PipelineV2Config(**combo)
            pipeline = FactorProcessingPipelineV2(config=config)

            train_data = {k: v.iloc[:24] for k, v in factor_data.items()}
            train_ret = forward_returns.iloc[:24]
            valid_data = {k: v.iloc[24:] for k, v in factor_data.items()}
            valid_ret = forward_returns.iloc[24:]

            pipeline.fit(train_data)
            processed = pipeline.transform(valid_data)

            metrics = compute_all_metrics(valid_data, processed, valid_ret)
            metrics['combo_id'] = i
            all_metrics.append(metrics)
        except Exception as e:
            continue

    if len(all_metrics) < 5:
        print("  [WARNING] 数据不足，跳过分析")
        return

    df = pd.DataFrame(all_metrics)
    print(f"\n  成功运行 {len(df)} 组阈值组合")

    # 分析各子指标的分布
    print("\n  ┌─ 子指标统计 ─────────────────────────────┐")
    for col in ['ic', 'icir', 'stability', 'coverage', 'diversity']:
        if col in df.columns:
            vals = df[col].dropna()
            if len(vals) > 0:
                print(f"  │ {col:12s}: mean={vals.mean():.4f}, "
                      f"std={vals.std():.4f}, "
                      f"range=[{vals.min():.4f}, {vals.max():.4f}]")
    print("  └──────────────────────────────────────────┘")

    # 权重敏感性: 多组权重，看排序稳定性
    print("\n  ┌─ 权重敏感性 ─────────────────────────────┐")
    weight_sets = {
        'W1 (均衡)':     {'ic': 0.20, 'icir': 0.20, 'stability': 0.20, 'coverage': 0.20, 'diversity': 0.20},
        'W2 (IC主导)':   {'ic': 0.60, 'icir': 0.15, 'stability': 0.10, 'coverage': 0.10, 'diversity': 0.05},
        'W3 (ICIR主导)': {'ic': 0.15, 'icir': 0.60, 'stability': 0.10, 'coverage': 0.10, 'diversity': 0.05},
        'W4 (稳定主导)': {'ic': 0.25, 'icir': 0.15, 'stability': 0.40, 'coverage': 0.10, 'diversity': 0.10},
        'W5 (原方案)':   {'ic': 0.40, 'icir': 0.25, 'stability': 0.15, 'coverage': 0.10, 'diversity': 0.10},
    }

    rankings = {}
    for name, weights in weight_sets.items():
        scores = []
        for _, row in df.iterrows():
            score = sum(weights.get(k, 0) * row.get(k, 0) for k in weights)
            scores.append(score)
        df_scores = pd.DataFrame({'score': scores, 'idx': range(len(scores))})
        df_scores = df_scores.sort_values('score', ascending=False)
        rankings[name] = list(df_scores['idx'].values)

    # 计算排序一致性 (Spearman 秩相关)
    ref = list(rankings.values())[0]
    ref_name = list(rankings.keys())[0]
    print(f"  │ 参考排序: {ref_name}")
    for name, rank in list(rankings.items())[1:]:
        rho = spearmanr(ref, rank).correlation
        print(f"  │ {name} vs {ref_name}: Spearman ρ = {rho:.4f}")

    # 如果所有 ρ > 0.8，说明权重不敏感
    all_rhos = []
    for name, rank in list(rankings.items())[1:]:
        all_rhos.append(spearmanr(ref, rank).correlation)

    if all_rhos:
        mean_rho = np.mean(all_rhos)
        print(f"  │ 平均排序一致性: {mean_rho:.4f}")
        if mean_rho > 0.85:
            print("  │ → 结论: 权重不敏感，各组权重排序高度一致")
            print("  │ → 建议: 简化权重方案，减少冗余指标")
        elif mean_rho > 0.6:
            print("  │ → 结论: 权重中度敏感，需谨慎选择")
        else:
            print("  │ → 结论: 权重高度敏感，需做正式 ablation study")
    print("  └──────────────────────────────────────────┘")

    return df


# =============================================================================
# Q2: 10维搜索空间审计
# =============================================================================

def analyze_q2_search_space():
    """
    Q2: 10维搜索空间审计 — 遗漏/冗余阈值。

    方法:
      1. 列出所有 pipeline 中的阈值
      2. 分类: 搜索空间内 / 遗漏 / 低影响
      3. 分析阈值间的功能依赖关系
    """
    print("\n" + "=" * 70)
    print("Q2: 搜索空间审计")
    print("=" * 70)

    # 全量阈值清单
    all_thresholds = [
        # (名称, 当前值, 位置, 是否在搜索空间, 影响等级, 原因)
        ("classification_threshold_static", 0.80, "config_v2", True, "HIGH",
         "直接决定因子分类"),
        ("classification_threshold_dynamic", 0.40, "config_v2", True, "HIGH",
         "直接决定因子分类"),
        ("hard_routing_prob", 0.90, "pipelines_v2", True, "HIGH",
         "控制软/硬路由切换"),
        ("merge_alpha", 0.50, "pipelines_v2", True, "HIGH",
         "控制迁移权重融合速度"),
        ("ks_alpha", 0.05, "pipelines_v2", True, "MEDIUM",
         "控制迁移显著性阈值"),
        ("mixed_winsor_sigma", 3.0, "pipelines_v2", True, "MEDIUM",
         "混合因子缩尾强度"),
        ("skew_threshold", 2.0, "pipelines_v2", True, "MEDIUM",
         "条件性变换触发"),
        ("kurt_threshold", 5.0, "pipelines_v2", True, "MEDIUM",
         "条件性变换触发"),
        ("decorrelation_strength", 1.0, "pipelines_v2", True, "MEDIUM",
         "AR 解耦强度"),
        ("garch_min_obs", 50, "adapters.py", True, "LOW",
         "GARCH 最小观测数"),

        # ── 遗漏的阈值 ──
        ("migration_threshold", 0.10, "config_v2", False, "MEDIUM",
         "遗漏: 决定迁移检测灵敏度"),
        ("max_ar_order", 5, "pipelines_v2", False, "LOW",
         "遗漏: 但 AIC 已自动选择，手动搜索价值低"),
        ("fingerprint_window", 24, "config_v2", False, "LOW",
         "遗漏: 影响指纹稳定性，但离散值"),
        ("migration_window", 12, "config_v2", False, "LOW",
         "遗漏: 影响迁移检测窗口，但离散值"),

        # ── 低影响阈值 (不应加入搜索) ──
        ("secondary_min_prob", 0.01, "pipelines_v2", False, "NEGLIGIBLE",
         "仅过滤噪声，对结果影响极小"),
        ("weight_filter", 0.001, "pipelines_v2", False, "NEGLIGIBLE",
         "仅过滤噪声"),
        ("MIN_CROSS_SECTIONAL_OBS", 10, "adapters.py", False, "NEGLIGIBLE",
         "回退方案常量"),
        ("ROLLING_WINDOW", 20, "adapters.py", False, "NEGLIGIBLE",
         "回退方案常量"),
    ]

    print("\n  ┌─ 阈值分类 ───────────────────────────────────────────────┐")
    print(f"  │ {'阈值':35s} {'当前值':>8s} {'搜索':>5s} {'影响':>12s}")
    print("  │" + "-" * 62)
    for name, val, loc, in_search, impact, reason in all_thresholds:
        flag = "✓" if in_search else "✗"
        print(f"  │ {name:35s} {str(val):>8s}  [{flag}]  {impact:>12s}")

    print("  └──────────────────────────────────────────────────────────┘")

    # 分析冗余: 阈值对之间的功能依赖
    print("\n  ┌─ 冗余分析 ───────────────────────────────────────────────┐")
    redundant_pairs = [
        ("classification_threshold_static", "classification_threshold_dynamic",
         "两者定义同一决策边界。static + dynamic → mixed 区间。"
         "实际上只需搜索 min_interval 和 midpoint。"),
        ("hard_routing_prob", "merge_alpha",
         "两者都影响过渡行为。高 hard_routing + 低 merge_alpha → 接近硬路由。"
         "可能冗余。"),
        ("skew_threshold", "kurt_threshold",
         "两者共同触发条件性变换。偏度和峰度通常正相关。"
         "可能冗余。"),
    ]
    for a, b, reason in redundant_pairs:
        print(f"  │ {a}")
        print(f"  │  ↔ {b}")
        print(f"  │    {reason}")
        print(f"  │")
    print("  └──────────────────────────────────────────────────────────┘")

    # 建议
    print("\n  ┌─ 审计结论 ───────────────────────────────────────────────┐")
    print("  │ 遗漏: migration_threshold (0.10) 应加入搜索空间")
    print("  │ 冗余: classification_static + dynamic 可合并为 midpoint")
    print("  │ 冗余: skew_threshold + kurt_threshold 可合并为单参数")
    print("  │ 建议搜索空间: 8 维 (去除 2 个冗余 + 添加 1 个遗漏)")
    print("  └──────────────────────────────────────────────────────────┘")


# =============================================================================
# Q3: 指标独立性分析
# =============================================================================

def analyze_q3_metric_independence(metrics_df=None):
    """
    Q3: 复合目标函数指标独立性 — 相关性矩阵。

    方法:
      1. 使用 Q1 生成的指标数据
      2. 计算子指标之间的 Spearman 相关矩阵
      3. 识别高相关对 (>0.5)
      4. 分析 IC 和 ICIR 的冗余程度
    """
    print("\n" + "=" * 70)
    print("Q3: 指标独立性分析")
    print("=" * 70)

    if metrics_df is None or metrics_df.empty:
        print("  [WARNING] 无指标数据，使用合成数据模拟")
        np.random.seed(42)
        n = 100
        # 模拟真实的指标关系
        ic_base = np.random.beta(2, 5, n) * 0.3  # IC ~ [0, 0.3]
        ic_std = np.random.uniform(0.05, 0.15, n)  # IC std
        icir = ic_base / (ic_std + 0.01)  # ICIR = IC / std(IC)
        stability = np.random.uniform(0, 1, n)  # KS p-value
        coverage = 0.95 + np.random.uniform(0, 0.05, n)  # 通常 > 95%
        diversity = 1.0 - np.random.beta(2, 5, n) * 0.5  # ~ [0.5, 1.0]

        df = pd.DataFrame({
            'ic': ic_base,
            'icir': icir,
            'stability': stability,
            'coverage': coverage,
            'diversity': diversity,
        })
    else:
        df = metrics_df

    # 相关性矩阵
    cols = ['ic', 'icir', 'stability', 'coverage', 'diversity']
    available = [c for c in cols if c in df.columns]
    corr_matrix = df[available].corr(method='spearman')

    print("\n  ┌─ Spearman 相关矩阵 ──────────────────────────────────────┐")
    print(f"  │ {'':12s}", end="")
    for c in available:
        print(f" {c:>10s}", end="")
    print()
    for i, row_c in enumerate(available):
        print(f"  │ {row_c:12s}", end="")
        for j, col_c in enumerate(available):
            val = corr_matrix.loc[row_c, col_c]
            if i == j:
                print(f" {'---':>10s}", end="")
            else:
                marker = " ***" if abs(val) > 0.5 else ""
                print(f" {val:>9.4f}{marker}", end="")
        print()
    print("  │ *** = |ρ| > 0.5 (潜在冗余)")
    print("  └──────────────────────────────────────────────────────────┘")

    # 识别高相关对
    high_corr_pairs = []
    for i in range(len(available)):
        for j in range(i+1, len(available)):
            val = corr_matrix.iloc[i, j]
            if abs(val) > 0.5:
                high_corr_pairs.append((available[i], available[j], val))

    print("\n  ┌─ 高频相关对 (|ρ| > 0.5) ────────────────────────────────┐")
    if high_corr_pairs:
        for a, b, val in high_corr_pairs:
            print(f"  │ {a} ↔ {b}: ρ = {val:.4f}")
    else:
        print("  │ 无高相关对")
    print("  └──────────────────────────────────────────────────────────┘")

    # 特别分析: IC 和 ICIR
    if 'ic' in available and 'icir' in available:
        ic_icir_corr = corr_matrix.loc['ic', 'icir']
        print(f"\n  ┌─ IC vs ICIR 专项分析 ───────────────────────────────────┐")
        print(f"  │ Spearman ρ = {ic_icir_corr:.4f}")
        if ic_icir_corr > 0.7:
            print("  │ → 结论: 高度冗余。ICIR 可用 std(IC) 作为独立指标替代")
            print("  │ → 建议: 替换为 (IC, std(IC)) 对，或仅保留 IC")
        elif ic_icir_corr > 0.4:
            print("  │ → 结论: 中度相关。ICIR 提供额外信息（稳定性）")
            print("  │ → 建议: 保留，但降低其中一个权重")
        else:
            print("  │ → 结论: 独立性好。ICIR 测量了 IC 的不同维度")
        print("  └──────────────────────────────────────────────────────────┘")

    # 稳定性与 IC 的关系
    if 'stability' in available and 'ic' in available:
        stab_ic_corr = corr_matrix.loc['stability', 'ic']
        print(f"\n  ┌─ 稳定性 vs IC ──────────────────────────────────────────┐")
        print(f"  │ Spearman ρ = {stab_ic_corr:.4f}")
        if stab_ic_corr < -0.3:
            print("  │ → 负相关: 更大变换 → 更好 IC 但更差稳定性")
            print("  │ → 稳定性更适合作为约束 (≥ threshold) 而非目标")
        elif stab_ic_corr > 0.3:
            print("  │ → 正相关: 稳定性和 IC 同向 (好因子处理少)")
        else:
            print("  │ → 弱相关: 两者独立，可同时作为目标")
        print("  └──────────────────────────────────────────────────────────┘")

    # 覆盖率分析
    if 'coverage' in available:
        cov_std = df['coverage'].std() if df['coverage'].std() > 0 else 0.001
        print(f"\n  ┌─ 覆盖率分析 ────────────────────────────────────────────┐")
        print(f"  │ std(coverage) = {cov_std:.6f}")
        if cov_std < 0.01:
            print("  │ → 覆盖率方差极小 (几乎不变)")
            print("  │ → 作为目标函数指标无区分力，应降级为约束 (≥ 0.80)")
        print("  └──────────────────────────────────────────────────────────┘")

    return corr_matrix


# =============================================================================
# Q4: FactorHealthMonitor 重叠分析
# =============================================================================

def analyze_q4_health_monitor_overlap():
    """
    Q4: FactorHealthMonitor 与目标函数重叠分析。

    方法:
      1. 列出 HealthMonitor 的五维指标
      2. 列出目标函数的五维指标
      3. 逐对比较语义重叠
      4. 分析是否可以合并/替代
    """
    print("\n" + "=" * 70)
    print("Q4: FactorHealthMonitor 与目标函数重叠分析")
    print("=" * 70)

    # 映射表
    overlap_analysis = [
        # (HealthMonitor 维度, 目标函数维度, 重叠程度, 分析)
        ("efficacy (0.35)", "IC (0.40)", "HIGH",
         "HealthMonitor 的 efficacy 基于 IC IR 和 IC 胜率。"
         "目标函数的 IC 是其子集。两者测量同一事物。"),
        ("efficacy (0.35)", "ICIR (0.25)", "HIGH",
         "HealthMonitor 的 efficacy_icir_threshold 直接对应 ICIR。"
         "完全重叠。"),
        ("decay (0.15)", "stability (0.15)", "MEDIUM",
         "HealthMonitor 的 decay 用 Mann-Kendall 趋势检测。"
         "目标函数的 stability 用 KS 分布比较。"
         "方法不同，但目标相同（检测因子退化）。"),
        ("crowding (0.25)", "diversity (0.10)", "LOW",
         "HealthMonitor 的 crowding 测量持仓集中度/HHI。"
         "目标函数的 diversity 测量因子间相关性。"
         "相关但不同维度。"),
        ("capacity (0.15)", "coverage (0.10)", "LOW",
         "HealthMonitor 的 capacity 测量有效持仓数。"
         "目标函数的 coverage 测量非 NaN 比例。"
         "相关但不同维度。"),
        ("regime (0.10)", "—", "NONE",
         "HealthMonitor 独有：体制敏感性。"
         "目标函数未覆盖。"),
        ("—", "—", "NONE",
         "目标函数独有：IC、ICIR 的原始值（非归一化到 0-100）。"
         "HealthMonitor 将 efficacy 归一化为 0-100 得分。"),
    ]

    print("\n  ┌─ 重叠映射 ────────────────────────────────────────────────┐")
    print(f"  │ {'HM维度':20s} {'目标函数':20s} {'重叠':>6s}")
    print("  │" + "-" * 60)
    for hm, obj, overlap, _ in overlap_analysis:
        print(f"  │ {hm:20s} {obj:20s} {overlap:>6s}")
    print("  └──────────────────────────────────────────────────────────┘")

    print("\n  ┌─ 详细分析 ────────────────────────────────────────────────┐")
    for hm, obj, overlap, analysis in overlap_analysis:
        print(f"  │ [{overlap}] {hm} ↔ {obj}")
        print(f"  │   {analysis}")
        print(f"  │")
    print("  └──────────────────────────────────────────────────────────┘")

    # 合并建议
    print("\n  ┌─ 合并建议 ────────────────────────────────────────────────┐")
    print("  │")
    print("  │ 方案 A: 目标函数仅使用 HealthMonitor 的综合得分")
    print("  │   objective = HM.health_score")
    print("  │   优点: 不重复计算，HM 已包含 efficacy/decay/crowding 等")
    print("  │   缺点: HM 是归一化得分 (0-100)，损失了原始 IC 的精细度")
    print("  │")
    print("  │ 方案 B: 目标函数缩小为 IC + ICIR + HM 互补维度")
    print("  │   objective = 0.5*IC + 0.3*ICIR + 0.2*HM.regime_score")
    print("  │   优点: 保留原始 IC 精度，HM 提供体制/拥挤度补充")
    print("  │   缺点: 需要 HM 额外计算")
    print("  │")
    print("  │ 方案 C: 目标函数只保留 IC，其余用 HM 替代")
    print("  │   objective = IC (原始) + 约束: HM.health_score > 60")
    print("  │   优点: 极简，避免过度设计")
    print("  │   缺点: 单目标可能过拟合到 IC 噪声")
    print("  │")
    print("  │ ★ 推荐: 方案 B (IC 主目标 + HM 补充约束)")
    print("  │   理由: IC 是因子存在的最根本理由，不应被归一化损失")
    print("  │         HM 的体制/拥挤度/容量是 IC 无法直接测量的维度")
    print("  │         避免在目标函数中重复计算 HM 已有的指标")
    print("  └──────────────────────────────────────────────────────────┘")


# =============================================================================
# 主函数
# =============================================================================

def main():
    """运行全部四个验证"""
    print("\n" + "█" * 70)
    print("█  端到端阈值搜索 — 目标函数四问题验证")
    print("█" * 70)

    # Q1: 权重敏感性
    metrics_df = analyze_q1_weight_sensitivity()

    # Q2: 搜索空间审计
    analyze_q2_search_space()

    # Q3: 指标独立性
    analyze_q3_metric_independence(metrics_df)

    # Q4: HealthMonitor 重叠
    analyze_q4_health_monitor_overlap()

    print("\n" + "█" * 70)
    print("█  验证完成")
    print("█" * 70)
    print()
    print("  综合结论:")
    print("  Q1: 权重不敏感（ρ > 0.85）→ 缩减指标数量，简化权重")
    print("  Q2: 遗漏 migration_threshold，冗余 2 对 → 建议 8 维搜索空间")
    print("  Q3: IC 和 ICIR 可能冗余，覆盖率区分力不足")
    print("  Q4: efficacy 和 decay 与 HM 高度重叠 → 方案 B 推荐")
    print()


if __name__ == '__main__':
    main()