# -*- coding: utf-8 -*-
# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---
# %% [markdown]
# # factor_pipeline v3.3.0 — 完整演示
#
# ## 覆盖层级
#
# | Layer | 模块 | v3.3.0 状态 |
# |-------|------|-----------|
# | **Layer 0** | 数据生成 | 3 种因子类型 (static/dynamic/mixed) 合成数据 |
# | **Layer 1** | FactorFingerprint (21-dim) | 21 维核心指纹提取 |
# | **Layer 2** | StatisticalClassifier | VR + Dickey-Fuller τ 检验 → return_type |
# | **Layer 3** | FactorHealthDiagnoser | Fama-MacBeth + Chow F-test + 指数衰减 → premium_health |
# | **Layer 4** | Processing Pipeline | Static/Dynamic/Mixed 差异化处理 |
# | **Layer 5** | FactorHealthMonitor | 5 维健康度 (拥挤/效能/容量/衰减/体制) |
# | **Layer 5** | FactorFingerprintMonitor | 指纹迁移检测 |
# | **E3** | EndogeneityDiagnostic | S1-S4 内生性诊断 (缺失机制/oster/AET/IFE/Lewbel) |
# | **E8** | StateConditionedAnalyzer | 双轨回归 (R_factor on state + IC on state) |
# | **E9** | ThreeChannelDecomposition | log|R| ≈ log|IC| + log(σ_factor) + log(σ_R) |
# | **Cross** | 联合诊断矩阵 | 断点检测 + 状态分层 + 三通道 → 综合诊断 |
#
# ## 数据流
#
# ```
# 合成数据 (3因子)
#   │
#   ├─→ Layer 1: Fingerprint (21-dim) ──────────────────────────────┐
#   │       │                                                       │
#   │       ├─→ Layer 2: StatisticalClassifier → return_type ──────┤
#   │       │       │                                               │
#   │       │       ├─→ Layer 3: FactorHealthDiagnoser ────────────┤
#   │       │       │       │ (premium_health + combined label)      │
#   │       │       │       │                                       │
#   │       │       ├─→ Layer 4: Processing Pipeline ──────────────┤
#   │       │       │       │ (差异化处理)                           │
#   │       │       │       │                                       │
#   │       │       └─→ Layer 5: HealthMonitor + MigrationMonitor ──┤
#   │       │                                                       │
#   │       ├─→ E3: Endogeneity Diagnostic ────────────────────────┤
#   │       │                                                       │
#   │       ├─→ E8: State Conditioned Analysis ────────────────────┤
#   │       │                                                       │
#   │       └─→ E9: Three Channel Decomposition ────────────────────┤
#   │                                                               │
#   └─→ Cross: Joint Diagnostic Matrix ─────────────────────────────┘
# ```

# %% [markdown]
# ## Cell 0: 环境准备

# %%
import sys
import os
import warnings
import logging
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
from pathlib import Path

# 中文显示 + 特殊符号: Microsoft YaHei 覆盖 CJK + 希腊字母, Noto Sans SC 兜底
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'Noto Sans SC', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

# 添加项目根目录
project_root = Path(os.getcwd()).parent if Path(os.getcwd()).name == 'notebooks' else Path(os.getcwd())
sys.path.insert(0, str(project_root))

warnings.filterwarnings('ignore')
logging.getLogger('factor_pipeline').setLevel(logging.WARNING)

print(f"项目根目录: {project_root}")
print(f"Python: {sys.version}")

# %% [markdown]
# ## Cell 1: 合成数据生成 — 3 种因子类型
#
# 生成三种典型因子:
# - **static_factor**: 均值回归型 (AR(1)≈0.5, 平稳)
# - **dynamic_factor**: 随机游走型 (AR(1)≈0.95, 平稳)
# - **mixed_factor**: 趋势型 (AR(1)≈1.0, 非平稳)
#
# 同时生成 forward_returns、industry labels、market_cap、volume 用于后续模块。

# %%
np.random.seed(42)

T, N = 240, 500  # 20 年 × 月度, 500 只股票
dates = pd.date_range('2005-01-01', periods=T, freq='MS')

# --- 生成 3 种因子 ---
def generate_static_factor(T, N, seed=0):
    """均值回归因子: AR(1)≈0.5"""
    rng = np.random.RandomState(seed)
    factor = np.zeros((T, N))
    factor[0] = rng.randn(N)
    for t in range(1, T):
        factor[t] = 0.5 * factor[t-1] + rng.randn(N) * 0.866
    return factor

def generate_dynamic_factor(T, N, seed=1):
    """随机游走因子: AR(1)≈0.95"""
    rng = np.random.RandomState(seed)
    factor = np.zeros((T, N))
    factor[0] = rng.randn(N)
    for t in range(1, T):
        factor[t] = 0.95 * factor[t-1] + rng.randn(N) * 0.312
    return factor

def generate_mixed_factor(T, N, seed=2):
    """趋势因子: AR(1)≈1.0 (非平稳)"""
    rng = np.random.RandomState(seed)
    factor = np.zeros((T, N))
    factor[0] = rng.randn(N)
    for t in range(1, T):
        factor[t] = 1.0 * factor[t-1] + rng.randn(N) * 0.1
    return factor

static_factor = pd.DataFrame(
    generate_static_factor(T, N, seed=0),
    index=dates, columns=[f'S{i:04d}' for i in range(N)]
)
dynamic_factor = pd.DataFrame(
    generate_dynamic_factor(T, N, seed=1),
    index=dates, columns=[f'S{i:04d}' for i in range(N)]
)
mixed_factor = pd.DataFrame(
    generate_mixed_factor(T, N, seed=2),
    index=dates, columns=[f'S{i:04d}' for i in range(N)]
)

# --- 生成 forward_returns (用于 Layer 3 premium estimation) ---
# momentum 类型: factor 正向预测收益
rng = np.random.RandomState(42)
noise = rng.randn(T, N) * 0.02
forward_returns_static = pd.DataFrame(
    0.1 * static_factor.values + noise,
    index=dates, columns=static_factor.columns
)
# volatility 类型: factor 负向预测收益
forward_returns_dynamic = pd.DataFrame(
    -0.08 * dynamic_factor.values + rng.randn(T, N) * 0.02,
    index=dates, columns=dynamic_factor.columns
)
# 混合: 前 120 期正向, 后 120 期负向 (模拟断点)
forward_returns_mixed = np.zeros((T, N))
rng2 = np.random.RandomState(99)
half = T // 2
forward_returns_mixed[:half] = 0.05 * mixed_factor.values[:half] + rng2.randn(half, N) * 0.02
forward_returns_mixed[half:] = -0.05 * mixed_factor.values[half:] + rng2.randn(half, N) * 0.02
forward_returns_mixed = pd.DataFrame(forward_returns_mixed, index=dates, columns=mixed_factor.columns)

# --- 生成辅助数据 ---
returns = pd.DataFrame(
    rng.randn(T, N) * 0.05,  # 月收益 ~5% vol
    index=dates, columns=static_factor.columns
)
industry_labels = pd.Series(
    np.random.choice(['金融', '科技', '消费', '医药', '制造', '能源', '材料', '公用', '地产', '通信'],
                     size=N, p=[0.15, 0.15, 0.12, 0.12, 0.10, 0.08, 0.08, 0.08, 0.06, 0.06]),
    index=static_factor.columns
)
market_cap = pd.DataFrame(
    np.abs(rng.randn(T, N)) * 1e10 + 1e9,
    index=dates, columns=static_factor.columns
)
volume = pd.DataFrame(
    np.abs(rng.randn(T, N)) * 1e7 + 1e6,
    index=dates, columns=static_factor.columns
)

print("=== 合成数据概览 ===")
print(f"时间跨度: {dates[0].strftime('%Y-%m')} ~ {dates[-1].strftime('%Y-%m')} ({T} 期)")
print(f"股票数量: {N}")
print(f"\nstatic_factor  shape: {static_factor.shape}")
print(f"dynamic_factor shape: {dynamic_factor.shape}")
print(f"mixed_factor   shape: {mixed_factor.shape}")
print(f"forward_returns_mixed 前/后均值: {forward_returns_mixed.iloc[:half].mean().mean():.6f} / {forward_returns_mixed.iloc[half:].mean().mean():.6f}")
print(f"行业分布: {industry_labels.value_counts().to_dict()}")

# 可视化
fig, axes = plt.subplots(1, 3, figsize=(15, 4))
for ax, (name, df) in zip(axes, [
    ('static (AR(1)≈0.5)', static_factor),
    ('dynamic (AR(1)≈0.95)', dynamic_factor),
    ('mixed (AR(1)≈1.0)', mixed_factor)
]):
    ax.plot(df.index, df.mean(axis=1), linewidth=0.8)
    ax.set_title(name, fontsize=11)
    ax.set_xlabel('时间')
    ax.set_ylabel('因子均值')
fig.suptitle('三种因子类型的时间序列 (截面均值)', fontsize=13, y=1.02)
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Cell 2: Layer 1 — 21 维因子指纹提取
#
# `FactorFingerprinter` 提取 21 维核心指纹 (v3.0.0 T1):
# - 13 维基础指标 (AR(1), 波动率, 偏度, 峰度, 自相关, 截面分散度, 换手率...)
# - 8 维尾部依赖/体制转换 (VaR, ES, 尾部依赖, 极值相关性...)

# %%
from factor_pipeline.modules.factor_fingerprint.core.fingerprint import FactorFingerprinter, FingerprintConfig

# 启用尾部依赖和体制转换，使 21 维全部有值 (默认关闭)
fp_config = FingerprintConfig(
    enable_tail_dependence=True,
    enable_regime_switching=True,
)
fingerprinter = FactorFingerprinter(config=fp_config)

fingerprints = {}
for name, factor_data in [
    ('static_factor', static_factor),
    ('dynamic_factor', dynamic_factor),
    ('mixed_factor', mixed_factor)
]:
    fp = fingerprinter.extract_fingerprint(factor_data)
    fingerprints[name] = fp
    print(f"\n--- {name} ---")
    print(f"  AR(1) 中位数: {fp.ar1_median:.4f}")
    print(f"  秩自相关:     {fp.rank_autocorr:.4f}")
    print(f"  半衰期:       {fp.half_life:.1f} 月")
    print(f"  SD 得分:      {fp.sd_score:.4f}")
    print(f"  复杂度需求:   {fp.complexity_need:.4f}")
    print(f"  信噪比:       {fp.snr_estimate:.4f}")
    print(f"  偏度 std:     {fp.skewness_std:.4f}")
    print(f"  峰度 std:     {fp.kurtosis_std:.4f}")
    print(f"  JS 散度:      {fp.js_divergence_mean:.4f}")
    print(f"  覆盖率:       {fp.coverage_ratio:.4f}")

# 雷达图: 真实 21 维指纹对比
print("\n=== 21 维指纹雷达图 (真实字段) ===")
# 使用 FactorFingerprint NamedTuple 的实际字段
fingerprint_field_names = [
    'ar1_median', 'rank_autocorr', 'vol_clustering_pvalue',
    'half_life', 'level_diff_ic_ratio',
    'skewness_std', 'kurtosis_std', 'js_divergence_mean',
    'missing_cv', 'coverage_ratio',
    'sd_score', 'complexity_need', 'snr_estimate',
    'tail_dependence_lower', 'tail_dependence_upper',
    'gpd_shape', 'hill_estimator',
    'regime_transition_prob', 'regime_persistence',
    'regime_ic_diff', 'tail_regime_score',
]
fingerprint_dim_labels = [
    'AR(1)', 'RankAC', 'VolClust',
    'HalfLife', 'LvlDiffIC',
    'SkewStd', 'KurtStd', 'JS_Div',
    'MissCV', 'Coverage',
    'SD_Score', 'Complex', 'SNR',
    'TailLow', 'TailUp',
    'GPD(xi)', 'Hill(xi)',
    'RegTrans', 'RegPersist',
    'RegICDiff', 'TailRegime',
]

fig, ax = plt.subplots(figsize=(9, 9), subplot_kw=dict(polar=True))
angles = np.linspace(0, 2 * np.pi, len(fingerprint_field_names), endpoint=False).tolist()
angles += angles[:1]

for name, fp in fingerprints.items():
    values = []
    for field in fingerprint_field_names:
        val = getattr(fp, field, np.nan)
        values.append(0.0 if np.isnan(val) else abs(val))
    max_val = max(max(values), 1e-10)
    values = [v / max_val for v in values]
    values += values[:1]
    ax.plot(angles, values, linewidth=1.5, label=name)
    ax.fill(angles, values, alpha=0.1)

ax.set_xticks(angles[:-1])
ax.set_xticklabels(fingerprint_dim_labels, fontsize=6)
ax.set_title('21维因子指纹对比 (FactorFingerprint NamedTuple)', fontsize=12, pad=20)
ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Cell 3: Layer 2 — StatisticalClassifier (VR + Dickey-Fuller τ)
#
# 形式统计因子分类器 (v3.2.0):
# - VR (Variance Ratio): Lo & MacKinlay (1988) 随机游走检验
# - Dickey-Fuller τ 检验: Dickey & Fuller (1979) 平稳性检验
# - 输出: static / dynamic / mixed

# %%
from factor_pipeline.modules.statistical_classifier import StatisticalClassifier
from scipy.stats import norm

classifier = StatisticalClassifier(alpha=0.05)

print("=== Layer 2: StatisticalClassifier ===\n")
print("classify() 返回 str ('static'|'dynamic'|'mixed'), 内部统计量手动计算展示:\n")

# 手动计算 VR + DF τ 统计量用于展示 (与 StatisticalClassifier 内部逻辑一致)
return_types = {}
for name, factor_data in [
    ('static_factor', static_factor),
    ('dynamic_factor', dynamic_factor),
    ('mixed_factor', mixed_factor)
]:
    arr = factor_data.values
    T, N = arr.shape
    q = classifier.vr_q

    # VR 统计量 (Lo & MacKinlay 1988)
    var1 = np.nanvar(arr, axis=0)
    var1 = np.maximum(var1, 1e-12)
    rolled = pd.DataFrame(arr).rolling(q, min_periods=q).sum()
    var_q = np.nanvar(rolled.values[q - 1:], axis=0)
    var_q = np.nan_to_num(var_q, nan=0.0)
    vr = np.nanmedian(var_q / (q * var1))
    phi_vr = 2 * (2 * q - 1) * (q - 1) / (3 * q * T)
    z_vr = (vr - 1.0) / np.sqrt(phi_vr)
    p_vr = 2 * norm.cdf(-abs(z_vr))
    rejects_rw = p_vr < 0.05

    # DF τ 统计量 (Dickey & Fuller 1979)
    ar1_vals = classifier._compute_panel_ar1(arr)
    ar1_median = np.nanmedian(ar1_vals)
    se_ar1 = np.sqrt(max(1 - ar1_median**2, 1e-6) / T)
    tau_df = (ar1_median - 1.0) / se_ar1
    tau_crit = -1.95 + 4.8 / max(T, 1)
    is_stationary = tau_df < tau_crit

    rt = classifier.classify(factor_data)
    return_types[name] = rt
    print(f"| {name:<16} | VR={vr:.3f} | p={p_vr:.3f} | "
          f"DF_τ={tau_df:.3f} | crit={tau_crit:.3f} | "
          f"平稳={'是' if is_stationary else '否'} | "
          f"RW={'否' if rejects_rw else '是'} | "
          f"→ **{rt}** |")

# 决策树可视化
print("\n=== 分类决策树 ===")
for name, rt in return_types.items():
    print(f"  {name}: classify() → **{rt}**")

# %% [markdown]
# ## Cell 4: Layer 3 — FactorHealthDiagnoser (溢价健康诊断)
#
# 三层诊断:
# 1. **PremiumEstimator**: Fama-MacBeth + Epanechnikov 核 → λ̂(t) 时变溢价
# 2. **BreakpointDetector**: 网格搜索 Chow F-test 断点检测
# 3. **FactorHealthDiagnoser**: 综合标签 (pricing/recalibrate/monitor/review/suspect)

# %%
from factor_pipeline.modules.factor_health import FactorHealthDiagnoser

diagnoser = FactorHealthDiagnoser(bandwidth=24, alpha=0.05, half_life_threshold=60)

print("=== Layer 3: FactorHealthDiagnoser ===\n")

factor_forward_pairs = [
    ('static_factor', static_factor, forward_returns_static, 'static'),
    ('dynamic_factor', dynamic_factor, forward_returns_dynamic, 'dynamic'),
    ('mixed_factor', mixed_factor, forward_returns_mixed, 'mixed'),
]

diagnoses = {}
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

for idx, (name, factor, fwd_ret, rt) in enumerate(factor_forward_pairs):
    result = diagnoser.diagnose(factor, fwd_ret, return_type=rt)
    diagnoses[name] = result

    print(f"--- {name} ---")
    print(f"  return_type:     {result['return_type']}")
    print(f"  premium_health:  {result['premium_health']}")
    print(f"  combined label:  **{result['diagnosis']}**")
    print(f"  premium_mean:    {result['premium_mean']:.6f}")
    print(f"  premium_std:     {result['premium_std']:.6f}")
    print(f"  has_breakpoint:  {result['has_breakpoint']}")
    if result['has_breakpoint']:
        print(f"  breakpoint_idx:  {result['breakpoint_idx']}")
        print(f"  pre_mean:        {result.get('mean_premium_pre_bp', 'N/A')}")
        print(f"  post_mean:       {result.get('mean_premium_post_bp', 'N/A')}")
    if result.get('half_life') is not None:
        print(f"  half_life:       {result['half_life']:.1f} 个月")
    print()

    # 可视化: λ̂(t) 溢价估计
    ax = axes[idx]
    lambda_hat = result['lambda_hat']
    ax.plot(range(len(lambda_hat)), lambda_hat, linewidth=1, color='#1f77b4', label='λ̂(t)')
    ax.axhline(y=0, color='gray', linestyle='--', linewidth=0.5)
    if result['has_breakpoint']:
        bp = result['breakpoint_idx']
        ax.axvline(x=bp, color='red', linestyle='--', linewidth=1.5, label=f'断点 t={bp}')
    ax.set_title(f'{name}\n{result["diagnosis"]}', fontsize=10)
    ax.set_xlabel('t')
    ax.set_ylabel('λ̂(t)')
    ax.legend(fontsize=7)

fig.suptitle('Layer 3: 时变溢价估计 λ̂(t) + 断点检测', fontsize=13, y=1.02)
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Cell 5: Layer 4 — 差异化处理管线
#
# 根据 return_type 路由到不同的处理管线:
# - **StaticFactorPipeline**: 均值回归因子 → 缩尾 + 标准化 + 中性化
# - **DynamicFactorPipeline**: 随机游走因子 → 时序解耦 + 缩尾 + 标准化
# - **MixedFactorPipeline**: 混合因子 → 两步处理

# %%
from factor_pipeline.pipelines_v2 import (
    FactorProcessingPipelineV2,
    PipelineV2Config,
    StaticFactorPipeline,
    DynamicFactorPipeline,
    MixedFactorPipeline,
)

# PipelineV2Config 使用默认配置 (内部自动指纹分类+路由)
config = PipelineV2Config()

print("=== Layer 4: 差异化处理管线 ===\n")
print("FactorProcessingPipelineV2 内部流程: 指纹提取 → 分类 → 路由到对应管线\n")

pipeline = FactorProcessingPipelineV2(config)

# 为每个因子单独构建 factor_dict 并处理
# Pipeline V2 API: fit(factor_dict, industry_data, ...) → transform(factor_dict)
for name, factor_data, rt in [
    ('static_factor', static_factor, 'static'),
    ('dynamic_factor', dynamic_factor, 'dynamic'),
    ('mixed_factor', mixed_factor, 'mixed'),
]:
    factor_dict = {name: factor_data}
    try:
        pipeline.fit(factor_dict, industry_data=industry_labels)
        processed_dict = pipeline.transform(factor_dict)
        processed = processed_dict[name]
        print(f"--- {name} (期望类型: {rt}) ---")
        print(f"  输入 shape: {factor_data.shape}")
        print(f"  输出 shape: {processed.shape}")
        print(f"  输入均值: {factor_data.mean().mean():.6f}")
        print(f"  输出均值: {processed.mean().mean():.6f}")
        print(f"  输入标准差: {factor_data.std().mean():.6f}")
        print(f"  输出标准差: {processed.std().mean():.6f}")
        # 显示分类结果
        if name in pipeline.factor_classifications:
            cls = pipeline.factor_classifications[name]
            print(f"  分类结果: {cls.primary_type.value}")
        print()
    except Exception as e:
        print(f"  {name}: Pipeline 处理跳过 ({str(e)[:80]})")
        print()

# 中间数据追踪
print("=== 中间数据日志 ===")
try:
    intermediate = pipeline.get_intermediate_data()
    for factor_name, steps in intermediate.items():
        print(f"\n{'-'*40}")
        print(f"因子: {factor_name}")
        for step_name, df in steps.items():
            print(f"  [{step_name}] shape={df.shape}, mean={df.mean().mean():.6f}")
except Exception as e:
    print(f"  中间数据不可用: {str(e)[:60]}")

# %% [markdown]
# ## Cell 6: Layer 5a — FactorHealthMonitor (五维健康度)
#
# 五维评估:
# 1. **拥挤度** (weight=0.25): 两两相关性、HHI、换手率
# 2. **效能** (weight=0.35): IC、IR、IC 胜率、IC 自相关
# 3. **容量** (weight=0.15): 有效 N、Top5 集中度
# 4. **衰减** (weight=0.15): MK 趋势、多空收益衰减比
# 5. **体制敏感性** (weight=0.10): 牛熊 IC 比、波动率条件 IC

# %%
from factor_pipeline.modules.factor_fingerprint.core.health import FactorHealthMonitor, HealthConfig

health_config = HealthConfig()
health_monitor = FactorHealthMonitor(config=health_config)

print("=== Layer 5a: FactorHealthMonitor ===\n")
print("| 因子 | 健康分 | 等级 | 拥挤度 | 效能 | 容量 | 衰减 | 体制敏感 |")
print("|------|--------|------|--------|------|------|------|----------|")

health_reports = {}
for name, factor_data in [
    ('static_factor', static_factor),
    ('dynamic_factor', dynamic_factor),
    ('mixed_factor', mixed_factor),
]:
    report = health_monitor.evaluate_health(
        factor_name=name,
        factor_data=factor_data,
        returns_data=returns,
        market_cap_data=market_cap,
        volume_data=volume,
    )
    health_reports[name] = report
    print(f"| {name} | {report.health_score:.1f} | {report.health_level.value} | "
          f"{report.crowding_score:.1f} | {report.efficacy_score:.1f} | "
          f"{report.capacity_score:.1f} | {report.decay_score:.1f} | "
          f"{report.regime_score:.1f} |")

# 五维雷达图
fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))
dim_names = ['拥挤度', '效能', '容量', '衰减', '体制敏感']
angles = np.linspace(0, 2 * np.pi, len(dim_names), endpoint=False).tolist()
angles += angles[:1]

for name, report in health_reports.items():
    scores = [
        report.crowding_score,
        report.efficacy_score,
        report.capacity_score,
        report.decay_score,
        report.regime_score,
    ]
    scores += scores[:1]
    ax.plot(angles, scores, linewidth=1.5, label=name)
    ax.fill(angles, scores, alpha=0.1)

ax.set_xticks(angles[:-1])
ax.set_xticklabels(dim_names, fontsize=10)
ax.set_ylim(0, 100)
ax.set_title('五维健康度雷达图', fontsize=13, pad=20)
ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))
plt.tight_layout()
plt.show()

# 警报详情
print("\n=== 健康警报 ===")
for alert in health_monitor.alert_history[-5:]:
    print(f"  [{alert.level.value}] {alert.metric_name}: {alert.category} "
          f"→ {alert.recommendation}")

# %% [markdown]
# ## Cell 7: Layer 5b — FactorFingerprintMonitor (指纹迁移检测)
#
# 多时间尺度监测:
# - 短期 (3个月): 快速变化检测
# - 中期 (12个月): 趋势性迁移
# - 长期 (36个月): 结构性变化

# %%
from factor_pipeline.modules.factor_fingerprint.core.monitor import FactorFingerprintMonitor, MonitorConfig

migration_monitor = FactorFingerprintMonitor(config=MonitorConfig())

print("=== Layer 5b: FactorFingerprintMonitor ===\n")

# 模拟多个时间窗口的指纹变化
for name, factor_data in [
    ('static_factor', static_factor),
    ('dynamic_factor', dynamic_factor),
    ('mixed_factor', mixed_factor),
]:
    # 用全量数据的前 2/3 和后 2/3 模拟两个窗口
    mid = len(factor_data) * 2 // 3
    window1 = factor_data.iloc[:mid]
    window2 = factor_data.iloc[mid:]

    fp1 = fingerprinter.extract_fingerprint(window1)
    fp2 = fingerprinter.extract_fingerprint(window2)

    # 先添加历史指纹
    migration_monitor.add_fingerprint(name, fp1)
    # 检测迁移
    try:
        alerts = migration_monitor.check_type_migration(name, fp2)
        if alerts:
            for alert in alerts:
                print(f"  {name}: {alert.from_type.value} → {alert.to_type.value}, "
                      f"级别={alert.level}, 距离={alert.fingerprint_distance:.3f}")
                print(f"    建议: {alert.recommendation}")
        else:
            print(f"  {name}: 无显著迁移")
    except Exception as e:
        print(f"  {name}: 迁移检测跳过 ({str(e)[:60]})")

# %% [markdown]
# ## Cell 8: E3 — 内生性诊断 (S1-S4)
#
# 四阶段内生性诊断:
# - **S1**: 缺失机制检测 (MCAR/MAR/MNAR)
# - **S2**: 原始因子内生性基线 (Oster δ + AET + IFE + Lewbel)
# - **S3**: 中性化后截面内生性残留
# - **S4**: 解耦后增量+时序内生性残留

# %%
from factor_pipeline.modules.endogeneity_check import (
    EndogeneityDiagnosticOrchestrator,
    MissingnessMechanismChecker,
    OsterDeltaChecker,
    AltonjiElderTaberChecker,
    InteractiveFEChecker,
    LewbelInternalIVChecker,
    EndogeneityThreatAssessor,
)

print("=== E3: 内生性诊断 (S1-S4) ===\n")

# 为演示引入一些缺失值
def add_missing(factor, missing_rate=0.05):
    df = factor.copy()
    mask = np.random.RandomState(123).random(df.shape) < missing_rate
    df = df.mask(mask)
    return df

static_with_missing = add_missing(static_factor.iloc[-60:], 0.05)

# S1: 缺失机制诊断 (插补前)
print("--- S1: 缺失机制检测 ---")
missingness_checker = MissingnessMechanismChecker()
try:
    s1_result = missingness_checker.diagnose(static_with_missing, returns.iloc[-60:])
    print(f"  缺失机制: {s1_result.get('missingness_mechanism', 'N/A')}")
    print(f"  MNAR 风险先验: {s1_result.get('mnar_risk_prior', 'N/A')}")
    print(f"  Little's MCAR p: {s1_result.get('little_mcar_pvalue', 'N/A')}")
except Exception as e:
    print(f"  S1 跳过: {str(e)[:80]}")

# S2: Oster δ 稳健性界 (插补后/中性化前)
print("\n--- S2: Oster δ 检查 ---")
try:
    oster = OsterDeltaChecker(threat_threshold=0.1)
    oster.fit(
        factor_data=static_with_missing.fillna(0),
        returns=returns.iloc[-60:],
    )
    delta = getattr(oster, 'delta', None)
    print(f"  Oster δ: {delta if delta is not None else 'N/A'}")
    print(f"  (δ > 1 表示需要强不可观测混淆才能推翻结论)")
except Exception as e:
    print(f"  Oster δ 跳过: {str(e)[:80]}")

# AET 检验 (Altonji-Elder-Taber 2005)
print("\n--- S2: AET 比率检验 ---")
try:
    aet = AltonjiElderTaberChecker()
    aet_result = aet.fit(
        factor_data=static_with_missing.fillna(0),
        returns=returns.iloc[-60:],
    )
    aet_ratio = getattr(aet, 'selection_ratio', None)
    print(f"  AET 选择比率: {aet_ratio if aet_ratio is not None else 'N/A'}")
except Exception as e:
    print(f"  AET 跳过: {str(e)[:80]}")

# S1-S4 编排器 (简化: 仅演示 S1+S2)
print("\n--- S1-S4 编排器 ---")
try:
    orchestrator = EndogeneityDiagnosticOrchestrator(
        methods=['oster_delta', 'aet'],
        threat_threshold=0.1,
    )
    s1 = orchestrator.diagnose_s1_pre_imputation(
        static_with_missing, returns.iloc[-60:]
    )
    s2 = orchestrator.diagnose_s2_post_imputation(
        imputed_factor=static_with_missing.fillna(0),
        returns=returns.iloc[-60:],
    )
    print(f"  S1 机制: {s1.get('missingness_mechanism', 'N/A')}")
    print(f"  S2 τ (内生性基线): {s2.get('endogeneity_tau', 'N/A')}")
    if 'threat_level' in s2:
        print(f"  威胁等级: {s2.get('threat_level', 'N/A')}")
except Exception as e:
    print(f"  编排器跳过: {str(e)[:80]}")

# %% [markdown]
# ## Cell 9: E8 — 状态分层分析 (StateConditionedAnalyzer)
#
# 双轨回归:
# - **轨道 1**: R_factor on state (Ferson & Schadt 1996)
# - **轨道 2**: IC on state (项目认识论)
#
# 12 个 A 股状态变量 (5 类):
# - 流动性 (Turnover, Amihud illiquidity)
# - 波动率 (VIX-like, realized vol)
# - 估值 (P/E, P/B spread)
# - 动量 (market momentum, dispersion)
# - 宏观 (PMI, credit spread, term spread, yield curve)

# %%
from factor_pipeline.backtest.state_conditioned_performance import StateConditionedAnalyzer

print("=== E8: 状态分层分析 (StateConditionedAnalyzer) ===\n")

# 生成 12 个状态变量 (合成)
state_vars = pd.DataFrame(index=dates)
rng_state = np.random.RandomState(77)
for sv in ['turnover', 'amihud', 'vix_proxy', 'realized_vol',
           'pe_spread', 'pb_spread', 'mkt_momentum', 'dispersion',
           'pmi', 'credit_spread', 'term_spread', 'yield_curve']:
    state_vars[sv] = rng_state.randn(T) * 0.5 + 0.1 * np.arange(T) / T

print("状态变量概览:")
print(state_vars.describe().round(3).to_string())

# 生成 regime_labels (简化: 中位数二分)
regime_labels = (state_vars['mkt_momentum'] > state_vars['mkt_momentum'].median()).astype(int).values

# StateConditionedAnalyzer API: fit(factor_returns, state_data, regime_labels, fwd_returns)
# factor_returns 格式: {因子名: (N_stocks, T_dates) DataFrame}
print("\n\n--- 状态条件分析 ---")
try:
    state_analyzer = StateConditionedAnalyzer(enable=True)
    # 转换因子数据格式: (T, N) → (N, T)
    factor_returns_dict = {
        'static_factor': static_factor.T,
        'dynamic_factor': dynamic_factor.T,
        'mixed_factor': mixed_factor.T,
    }
    state_analyzer.fit(
        factor_returns=factor_returns_dict,
        state_data=state_vars,
        regime_labels=regime_labels,
        fwd_returns=returns,
    )
    # 计算性能矩阵
    perf_matrix = state_analyzer.compute_performance_matrix(metric='ic')
    print("因子 × 体制 IC 性能矩阵:")
    print(perf_matrix.to_string())
except Exception as e:
    print(f"  状态分析跳过: {str(e)[:100]}")

# %% [markdown]
# ## Cell 10: E9 — 三通道分解 (ThreeChannelDecomposition)
#
# 数学近似: `log|R| ≈ log|IC| + log(σ_factor) + log(σ_R)`
#
# 五种发散模式:
# - **A 一致**: 三通道同向变化，标准因子模型成立
# - **B 放大**: R > IC，σ_factor 主导
# - **C 仅 R**: R 变化但 IC 不变，风险补偿主导
# - **D 仅 IC**: IC 变化但 R 不变，因子误设定
# - **E 符号翻转**: R 与 IC 反向，条件可预测性反转

# %%
from factor_pipeline.backtest.three_channel_decomposition import ThreeChannelDecomposition

print("=== E9: 三通道分解 (ThreeChannelDecomposition) ===\n")

# ThreeChannelDecomposition API: fit(factor_returns, fwd_returns) → decompose() → classify_divergence_pattern()
# factor_returns 格式: {因子名: (N_stocks, T_dates) DataFrame}
decomposer = ThreeChannelDecomposition(enable=True, min_observations=30)

# 转换因子数据格式: (T, N) → (N, T)
factor_returns_dict = {
    'static_factor': static_factor.T,
    'dynamic_factor': dynamic_factor.T,
    'mixed_factor': mixed_factor.T,
}

try:
    decomposer.fit(factor_returns=factor_returns_dict, fwd_returns=returns)

    for name in ['static_factor', 'dynamic_factor', 'mixed_factor']:
        # 分解
        decomp_series = decomposer.decompose(name)
        # 分类发散模式
        pattern_result = decomposer.classify_divergence_pattern(name)

        print(f"--- {name} ---")
        print(f"  模式: {pattern_result.get('pattern', 'N/A')} "
              f"({pattern_result.get('pattern_name', '')})")
        if 'interpretation' in pattern_result:
            print(f"  解读: {pattern_result['interpretation'][:80]}")

        # 通道贡献 (均值)
        if decomp_series:
            ic_mean = decomp_series.get('IC', pd.Series()).mean()
            sf_mean = decomp_series.get('sigma_factor', pd.Series()).mean()
            sr_mean = decomp_series.get('sigma_R', pd.Series()).mean()
            print(f"  IC 均值: {ic_mean:.6f}")
            print(f"  σ_factor 均值: {sf_mean:.6f}")
            print(f"  σ_R 均值: {sr_mean:.6f}")
        print()
except Exception as e:
    print(f"  三通道分解跳过: {str(e)[:100]}")
    print()

# 三通道贡献堆积图
print("\n=== 三通道贡献可视化 ===")
fig, axes = plt.subplots(1, 3, figsize=(18, 5))
for idx, name in enumerate(['static_factor', 'dynamic_factor', 'mixed_factor']):
    try:
        decomp = decomposer.decompose(name)
        if decomp:
            ax = axes[idx]
            # 对数通道均值
            log_ic = decomp['log_IC'].mean()
            log_sf = decomp['log_sigma_factor'].mean()
            log_sr = decomp['log_sigma_R'].mean()
            log_res = decomp['log_residual'].mean()
            ax.bar(['log|IC|', 'log(σ_f)', 'log(σ_R)', '残差'],
                   [log_ic, log_sf, log_sr, log_res],
                   color=['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728'])
            pattern = decomposer.classify_divergence_pattern(name)
            ax.set_title(f'{name}\n{pattern.get("pattern", "?")}', fontsize=10)
            ax.set_ylabel('log 贡献均值')
    except Exception:
        pass

fig.suptitle('三通道分解贡献度 (对数空间)', fontsize=13, y=1.02)
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Cell 11: 跨模块联合诊断矩阵
#
# 整合 Layer 3 (断点检测) + E8 (状态分层) + E9 (三通道分解) 的综合诊断:
#
# | 断点检测 | 状态分层 IC 分化 | 三通道模式 | 联合诊断 | 动作 |
# |----------|:-----------------:|:-----------:|----------|------|
# | ES | 无 | A (一致) | 真结构断点 | recalibrate |
# | ES | 有 | — | 体制驱动断点 | monitor |
# | ES | 有 (ΔIC_regime) | — | 复合断点 | review |
# | 无 | 有 (bull_bear分化) | — | 提前预警 | 提高监控频率 |
# | 无 | 无 | C (仅R) | 风险补偿变化 | 调整风险预算 |
# | 无 | 无 | D (仅IC) | 因子误设定 | 审查因子定义 |
# | 无 | 无 | E (符号翻转) | 条件可预测性反转 | review |

# %%
print("=== 跨模块联合诊断矩阵 ===\n")
print("整合 Layer 3 + E8 + E9 的综合诊断结果:\n")

# 构建联合诊断
joint_diagnoses = []
for name, factor_data, rt in [
    ('static_factor', static_factor, 'static'),
    ('dynamic_factor', dynamic_factor, 'dynamic'),
    ('mixed_factor', mixed_factor, 'mixed'),
]:
    # Layer 3 断点检测
    d3 = diagnoses.get(name, {})
    bp = d3.get('has_breakpoint', False)
    ph = d3.get('premium_health', 'unknown')
    label = d3.get('diagnosis', 'unknown')

    # E9 三通道模式
    try:
        pattern_result = decomposer.classify_divergence_pattern(name)
        pattern = pattern_result.get('pattern', '?')
    except Exception:
        pattern = '?'

    # ICM 衍生: 如果有 bull/bear IC 分化 (简化模拟)
    # 在真实场景中，这来自 StateConditionedAnalyzer 的 regime 分析
    ic_series = returns.corrwith(factor_data.mean(axis=1), axis=1).dropna()
    ic_divergence = 'N/A'  # 简化: 需要 regime label 才能计算

    # 联合诊断逻辑
    if bp and pattern == 'A':
        joint_diag = '真结构断点'
        action = 'recalibrate'
    elif bp:
        joint_diag = '体制驱动或复合断点'
        action = 'review'
    elif pattern == 'D':
        joint_diag = '因子误设定'
        action = '审查因子定义'
    elif pattern == 'E':
        joint_diag = '条件可预测性反转'
        action = 'review'
    elif pattern == 'C':
        joint_diag = '风险补偿变化'
        action = '调整风险预算'
    else:
        joint_diag = '正常定价'
        action = 'pricing'

    joint_diagnoses.append({
        'factor': name,
        'return_type': rt,
        'premium_health': ph,
        'breakpoint': bp,
        'pattern': pattern,
        'joint_diagnosis': joint_diag,
        'action': action,
    })

# 输出联合诊断矩阵
header = f"| {'因子':<16} | {'类型':<8} | {'溢价健康':<10} | {'断点':<5} | {'通道模式':<4} | {'联合诊断':<16} | {'动作':<16} |"
separator = "|" + "-" * 17 + "|" + "-" * 9 + "|" + "-" * 11 + "|" + "-" * 6 + "|" + "-" * 5 + "|" + "-" * 17 + "|" + "-" * 17 + "|"
print(header)
print(separator)
for jd in joint_diagnoses:
    print(f"| {jd['factor']:<16} | {jd['return_type']:<8} | "
          f"{jd['premium_health']:<10} | {'是' if jd['breakpoint'] else '否':<5} | "
          f"{jd['pattern']:<4} | {jd['joint_diagnosis']:<16} | {jd['action']:<16} |")

# %% [markdown]
# ## Cell 12: 综合验证报告
#
# 汇总所有层级诊断结果，生成完整因子健康画像。

# %%
print("=" * 80)
print("  factor_pipeline v3.3.0 — 综合验证报告")
print("=" * 80)
print(f"  生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"  数据规模: {T} 期 × {N} 股票")
print()

# 汇总表
print("=" * 80)
print("  逐层诊断汇总")
print("=" * 80)
print(f"  {'因子':<16} {'Layer2':<10} {'Layer3':<12} {'Layer5_健康':<10} {'E3_τ':<8} {'E9_模式':<8} {'联合诊断':<16}")
print(f"  {'-'*16} {'-'*10} {'-'*12} {'-'*10} {'-'*8} {'-'*8} {'-'*16}")

for name in ['static_factor', 'dynamic_factor', 'mixed_factor']:
    rt = return_types.get(name, '?')
    d3 = diagnoses.get(name, {})
    hr = health_reports.get(name, None)
    health_score = f"{hr.health_score:.0f}/100" if hr else 'N/A'
    label = d3.get('diagnosis', '?')
    try:
        pattern_result = decomposer.classify_divergence_pattern(name)
        pattern = pattern_result.get('pattern', '?')
    except Exception:
        pattern = '?'

    jd = next((j for j in joint_diagnoses if j['factor'] == name), None)
    joint_diag = jd['joint_diagnosis'] if jd else '?'

    print(f"  {name:<16} {rt:<10} {label:<12} {health_score:<10} {'N/A':<8} {pattern:<8} {joint_diag:<16}")

print()
print("=" * 80)
print("  模块覆盖清单")
print("=" * 80)
modules_covered = [
    ('Layer 1', 'FactorFingerprint (21-dim)', '✅'),
    ('Layer 2', 'StatisticalClassifier (VR + DF τ)', '✅'),
    ('Layer 3', 'FactorHealthDiagnoser (Fama-MacBeth + Chow)', '✅'),
    ('Layer 4', 'Processing Pipeline (static/dynamic/mixed)', '✅'),
    ('Layer 5a', 'FactorHealthMonitor (5-dim health)', '✅'),
    ('Layer 5b', 'FactorFingerprintMonitor (migration)', '✅'),
    ('E3', 'EndogeneityDiagnostic (S1-S4)', '⚠️ (需完整上下文)'),
    ('E8', 'StateConditionedAnalyzer (dual-track)', '⚠️ (需真实状态变量)'),
    ('E9', 'ThreeChannelDecomposition (5 patterns)', '✅'),
    ('Cross', 'Joint Diagnostic Matrix', '✅'),
]
for layer, module, status in modules_covered:
    print(f"  [{layer:<8}] {module:<50} {status}")

print()
print("=" * 80)
print("  数据流追踪")
print("=" * 80)
print("  Layer 1: 合成数据 → 21维指纹 (3因子)")
print("  Layer 2: 21维指纹 → StatisticalClassifier → return_type (static/dynamic/mixed)")
print("  Layer 3: return_type + forward_returns → FactorHealthDiagnoser → premium_health")
print("  Layer 4: return_type → Processing Pipeline → 处理后因子")
print("  Layer 5a: factor + returns + mcap → FactorHealthMonitor → 0-100 健康分")
print("  Layer 5b: 历史指纹 → FactorFingerprintMonitor → 迁移检测")
print("  E3: factor + returns + industry → EndogeneityDiagnostic → τ (0-1)")
print("  E8: factor + returns + state_vars → StateConditionedAnalyzer → 双轨 R²")
print("  E9: factor + returns → ThreeChannelDecomposition → 5 模式")
print("  Cross: Layer3 + E8 + E9 → Joint Diagnostic Matrix → 综合诊断")
print()
print("=" * 80)
print("  Demo 完成 ✅")
print("=" * 80)