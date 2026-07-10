# 管线模块审计: 统计原则 vs 数据迁就

**日期**: 2026-07-09
**范围**: Factor Pipeline v3.1.0 完整处理链 (V2 管线 + 所有 adapter)
**问题**: 当前处理是否基于统计学原则，还是在做数据迁就？换一套数据是否需要重新调整参数/顺序？

---

## §1 审计框架

定义两个正交维度：

| 维度 | 定义 | 期望 |
|------|------|------|
| **原则驱动 (Principled)** | 数学恒等式、因果律、统计推断约定。结果不依赖于数据的具体数值分布 | 可迁移到任何市场/数据集 |
| **数据迁就 (Data-hacking)** | 基于当前数据统计特征的启发式决策、静默策略切换。换数据后结果不同 | 不可迁移，需重新校准 |

---

## §2 逐模块审计

### 2.1 Imputer (缺失插补)

| 项 | 值 |
|----|-----|
| 实现 | [adapters.py ImputerAdapter](file:///f:/Coding/factor_pipeline/adapters.py) → `PanelHierarchicalImputer` |
| 策略 | `strategy='auto'` (默认) → CrossSectional(全量中位数) + TimeSeries(ffill) |
| 判断 | **部分迁就 (50/50)** |

**原则部分 (OK)**:
- `ffill` 前向传播仅用过去数据 → 因果律，无前视偏差
- `fillna(0)` 替代 `bfill` → P0-2 已修复

**迁就部分 (问题)**:
- `strategy='auto'` 自动选择 CrossSectional + TimeSeries 组合
- CrossSectional 使用**全量中位数** → 换数据中位数不同 → 插补值不同
- 消融实验中 `imputer_off` 的 ΔSharpe=-7145% (市值中性化后)，说明插补策略对结果影响敏感
- 当前"auto" 的选策略逻辑隐藏在 `PanelHierarchicalImputer` 内部 → 不可审计

**建议**: `strategy='auto'` → `strategy='ffill_only'` (P1)。ffill 是唯一可证明无前视偏差的时序插补策略。

---

### 2.2 Winsorizer (去极值)

| 项 | 值 |
|----|-----|
| 实现 | [transformers.py SmartOutlierDetector](file:///f:/Coding/factor_pipeline/modules/factor_adaptive_winsor/core/transformers.py#L173) |
| 策略 | `method='auto'` → 5 选 1 (`sigmoid_soft`, `quantile`, `adaptive`, `iqr`, `mad`) |
| 判断 | **半迁就 (50/50)** |

```python
# transformers.py L173-L191
def _select_optimal_method(self, data_features):
    if n_samples < 30:           return 'sigmoid_soft'
    if outlier_ratio > 0.15:     return 'quantile'
    elif outlier_ratio > 0.10:   return 'adaptive'
    elif outlier_ratio > 0.05:   return 'iqr'
    else:                        return 'mad'
```

**原则部分**: 所有 5 种方法在统计上都是合理的去极值手段 (MAD/IQR/quantile 基于秩统计量，sigmoid 基于软截断)。

**迁就部分**:
- `outlier_ratio` 阈值 (0.05/0.10/0.15) 是硬编码的 — 没有理论依据
- `method='auto'` 的静默切换 → **同一因子换数据可能走不同缩尾路径** → 消融结果不可比
- 消融实验中 `winsorizer_off` ΔIC=-44.1% (市值中性化后)，但这是 "auto 选了什么" + "无缩尾" 的复合效应，无法拆开

**建议**: P0 → `method='iqr'` (固定) 或 P1 → 显式 override。取消 auto 模式。

---

### 2.3 AdaptiveTransformer (非线性变换)

| 项 | 值 |
|----|-----|
| 实现 | [transformers.py AdaptiveTransformer](file:///f:/Coding/factor_pipeline/modules/factor_adaptive_winsor/core/transformers.py#L487) |
| 策略 | `method='auto'` → 5+1 选 1 (修复后) |
| 判断 | **已修复 — 但仍需条件化 (60/40)** |

**原则部分 (OK)**:
- 6 种方法 (`yeojohnson`, `boxcox`, `quantile`, `power`, `log`, `identity`) 在统计上有清晰的分工
- P1 修复: `is_normal=True` → `identity` (不强制变换正态数据)
- kurtosis 阈值 bug 已修复 (excess kurtosis 对齐)

**迁就部分**:
- `_select_optimal_transform` 的分类决策仍基于 data-dependent 的峰度/偏度
- **StaticPipeline 无条件执行变换** — 不像 MixedPipeline 有 `_diagnose_transform_need()` 条件门控
- momentum_1m 当前约 50% 几率走 identity (修复后) 或 quantile (修复前) → 说明变换对他有边际效应但方向不确定

**对比 MixedPipeline**:

| | StaticPipeline | MixedPipeline |
|--|---------------|---------------|
| transform method | `'auto'` | `'yeo_johnson'` |
| 条件门控 | **无** (永远执行) | **有** (`_diagnose_transform_need`) |
| identity 可能 | 修复后才可能 | 跳过整个 transform 步骤 |

**建议**: P1 → StaticPipeline 增加 `conditional_transform` (与 MixedPipeline 一致)。让 `_diagnose_transform_need()` 在 is_normal 时完全跳过 transform 步骤（不仅是 identity 变换，而是跳过 fit+transform 开销）。

---

### 2.4 Standardization (标准化)

| 项 | 值 |
|----|-----|
| 实现 | [transformers.py AdaptiveStandardizer](file:///f:/Coding/factor_pipeline/modules/factor_adaptive_winsor/core/transformers.py#L848) → [adapters.py ProcessingAdapter](file:///f:/Coding/factor_pipeline/adapters.py#L373) |
| 策略 | `method='z_score'` → 横截面 `(x - row_mean) / row_std` |
| 判断 | **原则驱动 ✓ (P0-3 已修复)** |

**原则部分**:
- 横截面 z-score 是 rank-preserving 的 (`ρ=1.0` 每期验证)
- 不依赖数据特征，仅依赖当期的截面分布 → 无历史偏差
- P0-3 修复: per-stock z-score → cross-sectional z-score

**无迁就风险**。`method='auto'` 时 vote-based 选择 robust/quantile/min_max，但当前默认配置已固定为 `z_score`。

---

### 2.5 Neutralization (中性化)

| 项 | 值 |
|----|-----|
| 实现 | [adapters.py NeutralizerAdapter](file:///f:/Coding/factor_pipeline/adapters.py#L467) |
| 策略 | OLS 回归取残差: `y ~ industry_dummies [+ log_mv]` |
| 判断 | **原则驱动 ✓** |

**原则部分**:
- OLS 残差 = 剥离已知风险暴露，数学上有 BLUE 性质
- 市值中性化 (P0-5) 同样基于 OLS → 无 data-dependent 参数
- 每期独立回归 → 无时序偏差

**无迁就风险**。中性化在数学定义上是纯原则的 — 给定行业/市值暴露定义，残差是唯一满足 `residuals ⟂ exposure` 的线性映射。

---

### 2.6 SOFT 路由 (分类 + 加权)

| 项 | 值 |
|----|-----|
| 实现 | [pipelines_v2.py L1341-L1369](file:///f:/Coding/factor_pipeline/pipelines_v2.py#L1341) |
| 策略 | softmax → `f_out = 0.807 * f_static + 0.189 * f_mixed` |
| 判断 | **数据迁就 ✗** |

这是整个管线中**最大的迁就点**：

1. **分类阈值硬编码**: AR(1)>0.80→Static, AR(1)<0.40→Dynamic, else→Mixed — 三分类阈值没有任何学术引用或实证校准
2. **softmax 权重来自于训练数据**: 分类器 (fingerprint → softmax) 的权重矩阵是在当前数据上拟合的，换数据后权重完全不同
3. **SOFT 路由破坏了可审计性**: `f_out = w1*f1 + w2*f2 + w3*f3` 使管线的输出变成三个不同处理链的加权混合 → 无法逆推出某个中间步骤的贡献
4. **消融实验的 scaler ΔIC=122% 主要来自 SOFT 路由的权重失真**: 无 scaler 时两个管线输出值域差距 25× → 加权和退化为单管线

**建议**: P0 → SOFT → hard routing (选 primary_type 的单管线)。hard routing 是确定的、可审计的、可迁移的。软路由增加的 18.9% mixed 贡献在统计上不显著 (p=0.80)，不值得牺牲可审计性。

---

### 2.7 StaticPipeline 中性化顺序 (P1)

| 项 | 值 |
|----|-----|
| 判断 | **原则驱动但统计上无差异 ✓/✗** |

A/B 测试(48 股 × 1449 期):
- neutralizer → transform (新): IC=-0.0042, Sharpe=-0.0049
- transform → neutralizer (旧): IC=-0.0041, Sharpe=-0.0031
- **p(HAC)=0.80** (不显著)
- 截面 Spearman ρ=0.9958 (近乎可交换)

**结论**: 两种顺序基本等价。保留新顺序基于"先剥离暴露再变换"的原则性，但属**无实证支持的优化**。

---

## §3 整体评分

| 模块 | 原则比重 | 迁就比重 | 迁移性 |
|------|---------|---------|--------|
| Imputer | 50% | 50% | 中 |
| Winsorizer | 50% | 50% | 中 |
| Transformer | 60% | 40% | 中 |
| Standardization | 100% | 0% | **高** |
| Neutralization | 100% | 0% | **高** |
| SOFT routing | 30% | 70% | **低** |
| Pipeline 顺序 | 100% | 0% | **高** |
| HAC/BH-FDR 检验 | 100% | 0% | **高** |

**加权平均 (3 因子典型管线)**: **~68% 原则, ~32% 迁就**

---

## §4 改进路线图

### P0 — 立即

| 变更 | 文件 | 效果 |
|------|------|------|
| `method='auto'` → 所有模块显式 method | adapters.py, transformers.py | 消除静默策略切换 |
| SOFT → hard routing | pipelines_v2.py | 管线可审计 |
| Imputer `strategy='ffill'` 固定 | pipelines_v2.py | 消除全量统计量偏差 |

### P1 — 下一迭代

| 变更 | 文件 | 效果 |
|------|------|------|
| StaticPipeline `conditional_transform` | pipelines_v2.py | 正态数据跳过变换 |
| 分类阈值 AR(1)=0.80 → 学术引用 | pipelines_v2.py, config_v2.py | 阈值有理论支撑 |
| 消融脚本增加 `market_cap_data` 穿透 | scripts/run_ablation_real.py | 市值中性化可消融 |

### P2 — 后续

| 变更 | 文件 | 效果 |
|------|------|------|
| Winsorizer threshold → configurable params | transformers.py, config_v2.py | 阈值可审计 |
| Pipeline 日志记录 intermediate data | 所有 pipeline | 每步骤可追踪 |
| 跨市场验证 (港股/US) | 新脚本 | 实证迁移性 |

---

## §5 结论

**回答**: 当前管线约 68% 基于统计原则，32% 存在数据迁就。这不是一个灾难性的比例 — 大部分核心数学操作 (z-score, OLS 残差, HAC 检验) 是纯原则的。但 32% 的迁就部分集中在**门槛点**: 分类器路由 + auto 模式静默切换。这些门槛点决定了因子走哪条处理链，其 data-dependency 使整个管线的输出对数据敏感。

**关键论点**: 换数据后结果会变 ≠ 一定需要换数据调参。Standardization 和 Neutralization **不**需要换数据调参 — 它们是纯数学变换。Imputer/Winsorizer/Transformer 的 `auto` 模式**会**自动适应新数据 — 但这不是 bug，而是设计意图（自适应）。问题是**自适应层和原则层没有隔离** — 用户无法区分"管线因为数据特征不同而自适应"vs"管线因为策略切换而行为不同"。

**最优先行动**: 将所有 `method='auto'` 替换为固定方法 → 消融实验的结果从"比较 auto 策略"变为"比较确定的方法" → 可复现、可迁移。
