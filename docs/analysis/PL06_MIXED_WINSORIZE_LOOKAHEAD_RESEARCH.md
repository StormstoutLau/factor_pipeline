# PL-06 Mixed 缩尾前视缺陷调研

**文档版本**: v1.0
**日期**: 2026-10-22
**缺陷编号**: DEFECT-PL-06
**目标版本**: 待设计文档确定 (建议 v3.3.5)
**调研范围**: `MixedFactorPipeline` 自有缩尾 (`_compute_winsorize_params` / `_apply_winsorize`), 配置 `mixed_winsor_sigma`, `EndToEndThresholdOptimizer` 耦合
**调研方法**: 源码逐行核对 + 截断不变式探针 + 候选方案对拍 + 项目内文献复用 + OpenAlex/Crossref 部分检索
**后续 (2026-11-04)**: 设计文档 v1.1 选定 **方案 A (逐日截面 3σ)**; 方案 B (percentile 1,99) 保留为备选记录, 本次不实施。**已实施 (v3.3.5, 2026-11-04)**, 验收记录见 [EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md](../EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md) §7。
**核心原则**: t 时刻的输出只能使用 `F_t` (t 时刻及以前可观测的信息); 对因子面板 (index=日期, columns=股票), 同一交易日内的横截面信息属于 `F_t`, 未来交易日不属于

**证据等级**:
- **A**: 直接读到原文/摘要/官方方法论文档, 可核对
- **B**: 搜索结果摘要、二手文献或项目内文档转引, 未读到原文对应段落
- **C**: 项目内部代码/文档, 可逐行核对
- **U**: 未能验证, 明确标注, 不作为论据

---

## §0 摘要 (TL;DR)

PL-06 是 **Mixed 管线自有缩尾参数的全样本估计**:

| # | 事实 | 性质 | 实测 |
|---|------|------|------|
| 1 | `_compute_winsorize_params` 用 `X.mean(axis=0)` / `X.std(axis=0)` 计算**每只股票全历史**的 3σ 边界 | 前视: 前 t 期缩尾边界依赖 t 之后的数据 | 截断 60/100 期: 257 格差异 / 1800 格, `max_abs_diff=6.984124662957469e-01`, 首个发散日 = **2020-01-31** (第 1 期) |
| 2 | `fit` 计算并保存边界, `transform` 直接复用 | 边界一经全样本估计即固定, 不会随新数据重算 | 同上 |
| 3 | 该步骤位于 `neutralize` 与 `rank` 之前 | 缩尾通过改变中性化输入间接影响排序; 即使后续是 rank, 也非"无影响" | 基线截断前后逐日 Spearman 中位数 0.999555, 最小 0.984872, 31/60 行 < 1 |

**结论**:

1. 三种因果候选 —— **逐日截面 3σ**、**逐日截面 percentile(1,99)**、**完全移除缩尾** —— 在项目测试面板上截断不变式均为 **0 格 / 0**。这证明 PL-06 是 Mixed 当前唯一的残留缺陷, 且方法选择不影响"因果性"本身, 只影响输出语义。
2. 方案 A (逐日截面 3σ) 改动最小: 只改 `pipelines_v2.py` 的两个私有方法, `mixed_winsor_sigma` 配置与 optimizer 契约保持有效; 工业上 MSCI FaCS 也采用 "稳健均值 ± 3 个稳健标准差" 的缩尾 (A, PL-01 调研已核验官方 PDF)。
3. 方案 B (逐日截面 percentile(1,99)) 与 PL-01/ADR-037 的缩尾口径一致, 也符合项目内《学术文献决策准则》对 `_compute_winsorize_params` 的原始计划; 但会使 `mixed_winsor_sigma` (以及 optimizer 中仅用于调整它的 `transform_aggressiveness`) 成为死配置, 需要配置面清理, 范围大于本缺陷。**注意**: 该项目内文档引用的 Bali et al. (2016) "cross-sectional distributions" 逐字引文, PL-01 调研已标记为**未独立验证**, 本调研不把它当作强论据。
4. **小截面事实** (本次实测): 截面 3σ 在 `N ≤ 10` 时**永不触发** (数学上最大标准分 `(N-1)/√N < 3`); 截面 percentile(1,99) 在 `N ≤ 200` 时**每行恰好截掉最小值和最大值各 1 个**, 实际截断率是 `2/N` 而非名义上的 1%。二者在小截面上的行为差异必须在设计文档中明确。

---

## §1 缺陷复现与范围

### 1.1 代码路径

| 位置 | 行为 | 性质 |
|------|------|------|
| [`MixedFactorPipeline.fit`](../../pipelines_v2.py#L1088-L1140) | 插补 → `_compute_winsorize_params(X)` → `_apply_winsorize(X)` → 中性化 → rank → z-score | 缩尾参数在 fit 内由当前输入全样本估计 |
| [`MixedFactorPipeline.transform`](../../pipelines_v2.py#L1142-L1162) | 插补 → `_apply_winsorize(X)` (复用 fit 参数) → ... | 参数固定; 对训练窗口之后的 transform 不构成新前视, 但 fit+transform 整体在截断测试中不等价 |
| [`_compute_winsorize_params`](../../pipelines_v2.py#L1164-L1178) | `mean = X.mean(axis=0)`; `std = X.std(axis=0)` (pandas 默认 `ddof=1`); `lo/hi = mean ± sigma*std` | **按列 (每股) 全时序**; 前视根因 |
| [`_apply_winsorize`](../../pipelines_v2.py#L1180-L1184) | `X.clip(lower=lo, upper=hi, axis=1)` | `axis=1` 按列匹配边界, 与上一步的 per-column 参数一致 |
| [`mixed_winsor_sigma`](../../config_v2.py#L417-L420) | `Field(default=3.0, ge=1.0, le=10.0)` | 当前唯一的缩尾强度配置 |
| [`DEFAULT_SEARCH_SPACE`](../../optimizer.py#L45-L54) | 搜索 `mixed_winsor_sigma ∈ [1, 10]` | 优化器耦合 |
| [`_params_to_config`](../../optimizer.py#L156-L211) | `transform_aggressiveness` 通过 `mixed_winsor_sigma / aggressiveness` 间接生效 | 若删除 sigma, 该参数也失去作用点 |

### 1.2 实测

**面板**: `T=100, N=30, seed=23, kind='skewed'` (对数正态, 与集成测试 `test_mixed_pipeline_is_truncation_invariant` 完全一致), 截断点 `t=60`, 容差 `atol=1e-12`。

| 指标 | 基线 (当前代码) |
|------|----------------|
| 差异格子数 / 总格子数 | **257 / 1800** |
| 有差异的行数 / 总行数 | **31 / 60** |
| `max_abs_diff` | **6.984124662957469e-01** |
| NaN 模式不一致 | 0 |
| 首个发散日期 | **2020-01-31** (面板第 1 期) |

> 注: ADR-037 记录的 `2.91e-01` 是 PL-02 修复前的数值; PL-02 (rank 变换) 落地后, 同一测试的实测值变为 `6.98e-01`。本表是当前基线, 取代旧记录。

**候选方案** (同一面板, 同一截断点, 仅替换缩尾实现):

| 方案 | 差异格子 | `max_abs_diff` | NaN 不一致 |
|------|---------|----------------|-----------|
| A: 逐日截面 3σ | **0 / 1800** | 0 | 0 |
| B: 逐日截面 percentile(1,99) | **0 / 1800** | 0 | 0 |
| D: 移除缩尾 | **0 / 1800** | 0 | 0 |

三者在 `fit` 后都不再保存任何跨期参数, 因此结构上不可能把未来信息带入前 t 期。

### 1.3 生产路径映射

| 管线 | 缩尾实现 | 是否受 PL-06 影响 |
|------|---------|------------------|
| `StaticFactorPipeline` | `ProcessingAdapter(process_type='outlier')` → 逐日截面 percentile (PL-01/ADR-037) | 否 |
| `DynamicFactorPipeline` | 无缩尾步骤 | 否 |
| `MixedFactorPipeline` | 自有 `_compute_winsorize_params` (per-column 3σ) | **是** |

Mixed 不在 `fit` 中调用 `ProcessingAdapter(outlier)`, 因此 PL-01 的修复没有覆盖它。这也解释了为什么 PL-01 修复后 Mixed 的登记值只从 `2.91e-01` 变为 `6.98e-01` (PL-02 改变了后续变换), 而没有归零。

### 1.4 与其余缺陷的关系

| 缺陷 | 关系 |
|------|------|
| PL-01 | 同类根因 (全样本估计缩尾边界), 但宿主不同; 修复口径可作为先例 |
| PL-02 | 改变了 Mixed 的后续变换 (rank), 使本缺陷的实测值从 2.91e-01 变为 6.98e-01 |
| PL-05 | Dynamic 的 AR 系数/fitted_values, 与本缺陷无代码交集 |
| PL-07 | 顶层路由依赖全样本; 只有在 PL-05/PL-06 修复后, 才能把顶层残差归因于路由本身 |

### 1.5 为什么此前没有暴露

缩尾是**单调**变换, 单独看它不会改变排序。它之所以仍能影响最终输出, 是因为 Mixed 的顺序是:

```
imputer → winsorize → neutralize → rank → z-score
```

缩尾改变了中性化的输入, 中性化 (逐日 OLS) 再把差异传播到残差, 最后 rank 才会出现排序差异。本次实测:

- 截断前后 (基线) 逐日 Spearman: 中位数 **0.999555**, 最小 **0.984872**, **31/60** 行 < 1。
- 若只比较缩尾后的原始值, 排序差异会更小; 但与 PL-01 的结论一致, 排序类指标不是灵敏的探测器, **值相等的截断不变式**才是。

---

## §2 判据: 什么是"因果的缩尾"

### 2.1 操作化定义

对任意 `t`, 记 `F([0,t])` 为用 `[0,t]` 数据拟合并变换的管线。要求:

```
F([0,t] 数据)[0,t] ≡ F([0,T] 数据)[0,t]      (逐元素, 容差 0)
```

等价地, 第 `i` 期的缩尾边界只能由第 `i` 期及以前的观测决定。

### 2.2 理想的结构性质

`fit()` 不保存任何跨期参数; 缩尾边界在 `transform()` 内按当日行现算。与 ADR-037 (outlier) / ADR-029 (standardization) 的 "fit no-op" 同构。

### 2.3 数据契约

- `X: pd.DataFrame`, index = 日期, columns = 股票。
- 截面操作 = `axis=1`; 因此"逐日截面统计量"是 `X.mean(axis=1)` / `X.std(axis=1)`。
- 输出保留 index / columns; NaN 不参与统计, 输出仍为 NaN; 不得新增 NaN。
- 单行有效观测 `< 2` 或标准差为 0 时, 该行应原样返回。实测 pandas `clip` 对 NaN 边界 (单有效观测) 和零离散度 (边界 = 均值) 均自然保持原值, 无需显式分支。

### 2.4 小截面语义

缩尾参数必须只在可观测的当日截面上计算; **不允许**像 PL-02 那样引入"先检验再切换"的 pre-test 逻辑 (Leeb & Pötscher, 2006/2008)。因此小截面行为应由方法本身的数学性质决定, 而不是由数据触发的条件分支决定。

---

## §3 候选方案评估

### 3.1 方案 A: 逐日截面 3σ (保留 `mixed_winsor_sigma`)

```python
mu = X.mean(axis=1)
sd = X.std(axis=1, ddof=1)
X.clip(lower=mu - sigma * sd, upper=mu + sigma * sd, axis=0)
```

`fit` 置 `_winsorize_params = None` (或删除该属性), `transform` 每次现算。

**实测 (T=100, N=30, skewed)**:

| 指标 | 数值 |
|------|------|
| 截断不变式 | **0 / 1800** |
| 缩尾触发格数 (fit 输入) | **77 / 3000 (2.57%)**, 73/100 行 |
| 相对当前的全样本输出差异 | 561 / 3000 格, 63/100 行; `max_abs=1.0446` |
| 逐日 Spearman (vs 当前) | 中位数 0.999110, 最小 0.942603, 63/100 行 < 1 |
| 缩尾后 rank 的 ties | 4 个值 (当前 0) |
| 性能 (T=2500, N=3000, 3 次中位数) | **0.268s** (当前 0.512s) |
| 小截面 | `N ≤ 10` 永不触发; `N=11` 起可能触发 |

**优点**: 改动最小; 配置/optimizer 契约不变; 3σ 是稳健统计中的常见阈值, 且有 MSCI FaCS "稳健均值 ± 3 稳健标准差" 的工业先例 (A); 对异常值的处理可解释; 性能优于当前 per-column 实现。
**缺点**: 与项目《学术文献决策准则》中"Mixed → percentile(1,99)"的原始计划不一致; `N ≤ 10` 时完全无效 (数学性质, 不是 bug, 但需文档化); 仍保留一个可被 optimizer 调整的自由参数。

### 3.2 方案 B: 逐日截面 percentile(1,99) (对齐 PL-01/ADR-037)

```python
lo = X.quantile(0.01, axis=1)
hi = X.quantile(0.99, axis=1)
X.clip(lower=lo, upper=hi, axis=0)
```

**实测 (T=100, N=30, skewed)**:

| 指标 | 数值 |
|------|------|
| 截断不变式 | **0 / 1800** |
| 缩尾触发格数 | **200 / 3000 (6.67%)**, 100/100 行 |
| 相对当前的全样本输出差异 | 612 / 3000 格, 83/100 行; `max_abs=1.2203` |
| 逐日 Spearman (vs 当前) | 中位数 0.998665, 最小 0.918131, 83/100 行 < 1 |
| 缩尾后 rank 的 ties | 0 |
| 性能 (T=2500, N=3000) | 0.308s |
| 小截面 | 见 §3.6; `N ≤ 200` 时每行固定截掉 min/max |

**优点**: 与 PL-01/ADR-037 的口径完全一致; 与项目内《学术文献决策准则》的原始计划一致 (C); 学术论文普遍采用截面 1%/99% (B; 具体原文未逐字核验, 见附录 C); 无自由参数, 输出可复现; 缩尾后不引入 ties (本面板)。
**缺点**: 使 `mixed_winsor_sigma` 成为死配置; optimizer 的 `mixed_winsor_sigma` 搜索项与 `transform_aggressiveness` 的唯一作用点同时失效; 需要配置迁移与 optimizer 搜索空间调整, 范围明显大于"修复前视"; 小截面上名义 1% 与实际 `1/N` 的偏差更大 (§3.6)。

### 3.3 方案 C: 按股票 expanding/rolling 缩尾 (拒绝)

对每只股票只用其历史窗口估计均值和标准差。该方案因果, 但:

- 与项目"因子面板按交易日做截面处理"的统一口径不一致;
- 需要引入时间变化参数 (window/expanding), 增加新的配置面;
- ADR-037 已在同类决策中明确拒绝该方向 (备选 B);
- 计算成本高于逐日截面。

**结论**: 不选。

### 3.4 方案 D: 移除 Mixed 缩尾 (拒绝为默认, 但可论证)

Mixed 后续已经是 rank 变换, 缩尾对"单行排序"本身是单调的。但本次实测表明它**不是冗余步骤**:

| 指标 | 移除 vs 当前 |
|------|--------------|
| 全样本输出差异 | 485 / 3000 格, 39/100 行; `max_abs=1.7394` |
| 逐日 Spearman | 中位数 1.000000, 最小 0.806007, 39/100 行 < 1 |

原因是缩尾位于**中性化之前**: 它改变中性化的输入, 从而改变残差和最终排序。移除缩尾会改变 `mixed_winsor_sigma` 的全部语义, 并使 optimizer 的搜索项失效; 也放弃了"温和去极值"这一设计意图。**结论**: 不选; 若未来确要简化, 应作为独立决策, 不与本缺陷修复捆绑。

### 3.5 方案对比

| 维度 | A: 截面 3σ | B: 截面 pct(1,99) | C: per-stock 扩展 | D: 移除 |
|------|-----------|-------------------|------------------|---------|
| 截断不变式 | 0 | 0 | 0 (预期) | 0 |
| 与项目口径一致 | 部分 (截面) | 完全 (PL-01/ADR-037) | 否 | — |
| 与学术/工业惯例 | 部分 (MSCI FaCS 3 稳健σ, A) | 高 (项目口径 + 学术常见 1%/99%, 原文未逐字核验) | 低 | — |
| 配置面影响 | 无 | 删除/废弃 sigma + optimizer 调整 | 新增窗口参数 | 删除 sigma |
| 小截面行为 | `N ≤ 10` 无效 | 每行固定截 min/max | 依赖窗口 | — |
| 输出变更 | 561 格 | 612 格 | 未测 | 485 格 |
| 性能 | 0.268s | 0.308s | 更高 | 最低 |
| 推荐 | **默认候选** | **对齐候选** | 拒绝 | 拒绝 |

### 3.6 3σ 与 percentile 的小截面事实 (本次实测)

**3σ 的数学上限**: 对 `N` 个观测、样本标准差 `sd` (ddof=1), 单点标准分绝对值最大为 `(N-1)/√N` (当其余 `N-1` 个值相等时取得)。解 `(N-1)/√N > 3`:

| N | 最大 \|z\| | 3σ 是否可能触发 |
|---|-----------|-----------------|
| 5 | 1.789 | 否 |
| 10 | 2.846 | 否 |
| 11 | 3.015 | 是 |
| 30 | 5.295 | 是 |

因此 **`N ≤ 10` 时逐日截面 3σ 是 no-op**。这不是实现缺陷, 而是 3σ 阈值与小截面的数学关系; 设计文档必须写明。

**percentile 的名义值 vs 实际截断**: 线性插值分位数在 `N ≤ 200` 时, 1% 分位点落在最小值与次小值之间, 99% 分位点落在最大值与次大值之间, 因此**每行恰好截掉 1 个最小值 + 1 个最大值**, 实际截断率为 `2/N`:

| N | pct(1,99) 实际截断率 | 每行截断数 |
|---|---------------------|-----------|
| 5 | 40.00% | 2 |
| 10 | 20.00% | 2 |
| 30 | 6.67% | 2 |
| 100 | 2.00% | 2 |
| 300 | 2.00% | 6 |
| 1000 | 2.00% | 20 |

> 实测 (T=60, 每行 N 个观测, 共 60 行): `N=5` 120/300; `N=10` 120/600; `N=30` 120/1800; `N=100` 120/6000; `N=300` 360/18000; `N=1000` 1200/60000。

**N=2 的边界行为** (实测): `pct(1,99)` 的两个分位点落在两个值之间, 会把**两个值都向中间压缩**: 行 `[1.0, 2.0]` → `[1.01, 1.99]`。3σ 在 `N=2` 时 no-op (最大 `|z|=0.707 < 3`)。单有效观测行 (`N=1`) 两者都原样返回。设计文档若选 B, 必须明确 `N=2` 的语义并写测试。

**含义**: 在小截面上, "1%/99%" 的标签具有误导性; 它等价于"截掉当日的极值"。如果设计目标是"温和缩尾", 方案 A 的 3σ 在小截面上更温和 (N≤10 完全不动作), 方案 B 在小截面上更激进 (每行必截两端, N=2 时两端都压缩)。生产面板通常 `N` 很大 (百至千), 两者都会收敛到预期的尾部比例。

### 3.7 输出影响与 ties

- A 引入 4 个 ties (本面板); B 不引入 ties; 当前实现 0 ties。差异来自 3σ 边界可能同时截断多个值, 使它们相等。
- 相对当前实现, A/B 的全样本输出差异分别为 561/612 格 (共 3000 格), 逐日 Spearman 中位数 0.9991/0.9987。**任何方案都会使存量 Mixed 输出与缓存失效**, 需要版本与缓存代际 bump。

---

## §4 学术与工业证据

> 本次外部检索工具不稳定 (见附录 B), 以下引用主要复用项目内已核实的文献结论, 并标注证据等级。未读原文的条目不作为强论据。

| 主题 | 来源 | 结论 | 等级 |
|------|------|------|------|
| 缩尾 vs 删失的选择 | Bali, Engle & Murray (2016), *Empirical Asset Pricing* | 系统讨论 winsorization vs truncation; 多数实证资产定价研究选择 winsorization | **A** (PL-01 调研经 Quant SE 引文与 Wiley StatsRef 概述核验; 书中"cross-sectional distributions"逐字引文**未验证**, 项目内文档的转引不作为强论据) |
| 稳健缩尾的经典尺度 | Hampel (1974), JASA; Rousseeuw & Croux (1993), JASA | MAD/稳健尺度是尾部截断的经典工具 | **A** (Crossref 元数据) |
| 分位数定义的小样本差异 | Hyndman & Fan (1996), *The American Statistician* | 样本分位数有多种定义; 小样本下分位边界依赖定义 | **A** (Crossref 元数据) |
| 3σ 型缩尾的工业实践 | MSCI FaCS Methodology (Bonne et al., 2018) | Barra 因子构建: 剔除极端值后 winsorize 到**稳健均值 ± 3 个稳健标准差** | **A** (PL-01 调研核验官方 PDF) |
| 前视与数据泄漏 | Banz & Breen (1986); Kaufman et al. (2012); Kapoor & Narayanan (2023) | 样本依赖/前视偏差与预处理泄漏会污染评估结论 | **A** (PL-01/PL-02 调研已核验摘要/原文) |
| 预处理选择对结论的影响 | Arnott, Harvey & Markowitz (2019) | 因子定义与预处理选择可显著改变结论 | **A** (PL-01 调研经 Crossref/SSRN 核验) |
| 截面 vs 时序口径 | ADR-037 (项目决策) | 因子面板统一采用逐日横截面估计, 拒绝 per-stock expanding | **C** |
| Mixed 的原始计划 | 《学术文献决策准则》§9.1 | 明确计划 `_compute_winsorize_params` → `percentile(1,99)` | **C** |
| 固定方法/禁止自适应选型 | ADR-027 | 所有 `auto` → 固定方法; Winsorizer `percentile(1,99)` | **C** |

**证据小结**:

1. "逐日截面"这一轴的选择有充分的学术与项目内证据, 无争议。
2. "3σ vs 1%/99%" 没有唯一正确答案: 两者都是稳健缩尾的合法实现。**A 方向**有 MSCI FaCS 的 "稳健均值 ± 3 稳健σ" 工业先例 (A); **B 方向**有项目内 ADR-027/《学术文献决策准则》的计划与 PL-01 口径一致性 (C), 以及学术论文中常见的 1%/99% 惯例 (B, 具体原文未逐字核验)。项目内文档曾计划 1%/99%, 但当时未考虑 `mixed_winsor_sigma` 的 optimizer 契约与小截面行为。
3. 本调研不把"未复核的原文"当作强论据; 设计文档若选择 B, 应以项目内计划与 PL-01 口径一致性为主要理由, 而不是声称 3σ 无学术依据; 若选择 A, 应以最小改动、保留 optimizer 契约与 MSCI FaCS 先例为主要理由, 并明确小截面 no-op 的语义。

---

## §5 项目内部约束与矛盾

### 5.1 与 PL-01/ADR-037 的口径

- PL-01 的结论是: **因子面板按交易日逐截面缩尾**, 拒绝 per-stock 全历史与全 panel 展平。
- PL-06 的当前实现恰好是 PL-01 明确拒绝的 "per-stock 全历史" 口径 (按列 `mean/std`)。
- 因此, 即使不做方法变更, 只把轴改为逐日截面, 也已经是与 PL-01 对齐的修复。

### 5.2 配置与 optimizer 耦合

```
PipelineV2Config.mixed_winsor_sigma (3.0, [1,10])
  → MixedFactorPipeline.mixed_winsor_sigma
  → _compute_winsorize_params

DEFAULT_SEARCH_SPACE['mixed_winsor_sigma'] ∈ [1,10]
  → _params_to_config()
  → mixed_winsor_sigma / transform_aggressiveness
```

- 方案 A 保持整条链路有效。
- 方案 B 需要同时处理 `mixed_winsor_sigma` 与 `transform_aggressiveness` (后者在 optimizer 中唯一作用就是调整前者), 并同步大量测试 (`test_p3_phase3_optimizer.py`, `verify_objective_function.py`, `verify_p2_2_manual.py` 等)。这是本缺陷范围之外的配置面清理。

### 5.3 步骤顺序

Mixed 的顺序由 PL-02 的 I-INT 决策固定为:

```
imputer → winsorize → neutralize → rank → z-score
```

缩尾不是 rank 的直接前置步骤, 中间隔着中性化。因此:

- 不能以 "rank 对单调变换不变" 为由直接删除缩尾;
- 也不能把缩尾移到 rank 之后 (会改变设计语义, 且 rank 后缩尾会制造大量 ties)。

### 5.4 既有测试

- `tests/integration/test_pipeline_truncation_invariance.py::test_mixed_pipeline_is_truncation_invariant` 当前 `xfail(strict=True)`, reason 记录 PL-06 / 6.98e-01。
- `test_mixed_pipeline_output_is_unit_variance` 不受影响 (z-score 逐行重算)。
- `tests/test_pipelines_v2.py::test_mixed_pipeline_processing` 只检查形状与缺失率, 不锁定缩尾数值。
- `tests/test_adapters/test_module_enabled.py` 只检查 `winsorizer` 开关的构造透传, 不锁定数值。
- 当前**没有**直接测试 Mixed 缩尾数值的用例; 实施时需要新增。

---

## §6 对设计/实施的约束

### 6.1 必须满足

| # | 约束 |
|---|------|
| C1 | 缩尾边界只使用当日横截面; `fit` 不保存跨期参数 |
| C2 | 输出保留 index / columns; NaN 不参与统计且输出仍为 NaN; 不新增 NaN |
| C3 | 单行有效观测 `< 2`、零离散度、全 NaN 行原样返回 (pandas `clip` 已满足, 需测试锁定); 若选 B, `N=2` 的行为需显式定义 (实测为两值向中间压缩, 不能沿用 3σ 的"小截面 no-op"假设) |
| C4 | 不引入数据触发的条件切换 (pre-test); 小截面行为由方法数学性质决定 |
| C5 | 若选 A, `mixed_winsor_sigma` 语义不变; 若选 B, 必须给出配置迁移方案 |
| C6 | 输出数值变更 → 版本与缓存代际 bump; 历史 Mixed 结果需重算 |
| C7 | 不改变 Mixed 的步骤顺序 (I-INT) |
| C8 | 不触碰 PL-05/PL-07 |

### 6.2 验收标准草案

1. `test_mixed_pipeline_is_truncation_invariant` 摘除 `xfail`, **0 格 / 0**。
2. 新增单元测试 (建议 `tests/unit/test_mixed_winsorize_cross_sectional.py`), 至少覆盖:
   - 逐日截面统计量的正确性 (与逐行循环对拍);
   - 截断不变式 (全样本 vs 截断);
   - `fit` 不保存跨期参数 (`_winsorize_params` 为 `None` 或不存在);
   - NaN / 单有效观测 / 零离散度行原样返回;
   - `mixed_winsor_sigma` 的单调性 (sigma 越大, 截断越少);
   - `winsorizer` 关闭时步骤级 identity (`outlier` 中间数据 == `imputation` 中间数据; 端到端仍执行后续步骤);
   - 小截面语义 (`N ≤ 10` 的 3σ no-op, 或 B 方案下的 min/max 行为)。
3. 集成诊断报告: Mixed 行由 `FAIL` 转为 `PASS`; PL-05/PL-07 仍为 `FAIL` (预期)。
4. 既有靶向测试全绿, 特别是 `test_mixed_pipeline_processing` 与 `test_mixed_pipeline_output_is_unit_variance`。
5. 性能记录: 目标不慢于当前 per-column 实现 (探针口径 A 0.268s vs 当前 0.512s; 真实方法口径 0.281s → 0.200s, 见设计/实施文档)。

### 6.3 兼容性

- **输出变更**: 所有方案都会改变存量 Mixed 输出 (A: 561 格, B: 612 格, D: 485 格; 本面板)。缓存必须 bump。
- **配置**: 方案 A 无迁移; 方案 B 需要删除/废弃 `mixed_winsor_sigma`, 并处理 `transform_aggressiveness`。
- **版本**: 建议 v3.3.5; 缓存 `CODE_VERSION` 建议 `v2.2.3-cache` (待设计文档确认)。
- **文档**: ADR-039, CHANGELOG v3.3.5, ARCHITECTURE/DEV_PROGRESS 版本基线。

### 6.4 范围边界

| 项 | 归属 |
|----|------|
| PL-05 (Dynamic AR) | 不在本任务 |
| PL-07 (顶层路由) | 不在本任务 |
| optimizer 重新调参/重新搜索 | 不在本任务 |
| 删除缩尾步骤 | 不在本任务 |
| 移除/重写 `transform_aggressiveness` | 仅在选 B 时作为必要迁移处理 |
| 非 Mixed 管线的缩尾 | 不在本任务 |

---

## §7 未决问题 (留给设计文档)

1. **A vs B**: 选逐日截面 3σ (最小改动、保留 sigma、与 optimizer 契约一致), 还是 percentile(1,99) (与 PL-01/ADR-027 及项目内原计划一致, 但需配置面清理)?
2. 若选 A, 是否在 `get_stats`/docstring 中显式声明 "`N ≤ 10` 时 3σ 不动作"?
3. 若选 B, `mixed_winsor_sigma` 是删除还是保留为 deprecated? `transform_aggressiveness` 如何处理? optimizer 搜索空间如何调整? 这些是否需要单独的配置迁移任务?
4. `_winsorize_params` 属性是删除, 还是保留为 `None` 以兼容潜在外部读取? (当前仓库内无外部读取)
5. 版本/缓存代际的最终取值。
6. 是否需要为本缺陷补一份 ADR-039, 或在 ADR-037 上追加"Mixed 同口径"修订?

---

## §8 参考文献

> 证据等级见文首。A 级条目的摘要/元数据已在 PL-01/PL-02 调研中核验; 本次未重新访问原文。

1. Bali, T. G., Engle, R. F., & Murray, S. (2016). *Empirical Asset Pricing: The Cross Section of Stock Returns*. Wiley. (A: winsorization vs truncation; "cross-sectional distributions" 逐字引文 U)
2. Hampel, F. R. (1974). The Influence Curve and its Role in Robust Estimation. *JASA*, 69(346), 383–393. https://doi.org/10.1080/01621459.1974.10482962 (A)
3. Rousseeuw, P. J., & Croux, C. (1993). Alternatives to the Median Absolute Deviation. *JASA*, 88(424), 1273–1283. https://doi.org/10.1080/01621459.1993.10476408 (A)
4. Hyndman, R. J., & Fan, Y. (1996). Sample Quantiles in Statistical Packages. *The American Statistician*, 50(4), 361–365. https://doi.org/10.1080/00031305.1996.10473566 (A)
5. Bonne, G., et al. (2018). *MSCI FaCS Methodology*. MSCI 官方方法论文档. (A: 稳健均值 ± 3 稳健标准差缩尾; PL-01 调研核验官方 PDF)
6. Banz, R. W., & Breen, W. J. (1986). Sample-Dependent Results Using Accounting and Market Data: Some Evidence. *Journal of Finance*. https://doi.org/10.1111/j.1540-6261.1986.tb04548.x (A: 摘要原文, PL-01 核验)
7. Kaufman, S., Rosset, S., Perlich, C., & Stitelman, O. (2012). Leakage in Data Mining: Formulation, Detection, and Avoidance. *ACM TKDD*, 6(4). https://doi.org/10.1145/2382577.2382579 (A: 摘要原文, PL-01 核验)
8. Kapoor, S., & Narayanan, A. (2023). Leakage and the reproducibility crisis in machine-learning-based science. *Patterns*. https://doi.org/10.1016/j.patter.2023.100804 (A: 预印本/摘要原文, PL-01/PL-02 核验)
9. Arnott, R. D., Harvey, C. R., & Markowitz, H. (2019). A Backtesting Protocol in the Era of Machine Learning. *Journal of Financial Data Science*, 1(1), 64–74. https://doi.org/10.3905/jfds.2019.1.064 (A: Crossref/SSRN, PL-01 核验)
10. Leeb, H., & Pötscher, B. M. (2006). Can One Estimate the Conditional Distribution of Post-Model-Selection Estimators? *Annals of Statistics*, 34(5), 2554–2591. https://doi.org/10.1214/009053606000000821 (A: 摘要原文, PL-02 核验)
11. Leeb, H., & Pötscher, B. M. (2008). Can One Estimate the Unconditional Distribution of Post-Model-Selection Estimators? *Econometric Theory*, 24(2), 338–376. https://doi.org/10.1017/s0266466608080158 (B: 标题 + Crossref 元数据, PL-02 核验)
12. 项目内文档: `docs/analysis/academic_literature_decision_criteria.md` §2.3 / §9.1; `DECISIONS.md` ADR-027 / ADR-037 / ADR-038; `docs/analysis/PL01_OUTLIER_LOOKAHEAD_RESEARCH.md`; `docs/analysis/PL02_TRANSFORM_LOOKAHEAD_RESEARCH.md`. (C)

---

## 附录 A: 探针脚本与原始输出

### A.1 复现方式

- 解释器: `C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe`
- 工作目录: `F:\Coding`; `PYTHONPATH=F:\Coding`
- 面板: `T=100, N=30, seed=23, kind='skewed'`; 截断 `t=60`; `atol=1e-12`
- 探针脚本临时存放于 `%TEMP%\pl06_probe.py` (不在仓库内), 核心逻辑如下:

```python
def panel(n_periods=100, n_stocks=30, seed=23, kind='skewed'):
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2020-01-31', periods=n_periods, freq='ME')
    stocks = [f'S{i:03d}' for i in range(n_stocks)]
    arr = rng.lognormal(mean=0.0, sigma=1.1, size=(n_periods, n_stocks))
    return pd.DataFrame(arr, index=dates, columns=stocks)

# 当前实现
mean = X.mean(axis=0); std = X.std(axis=0)
X.clip(lower=mean - sigma * std, upper=mean + sigma * std, axis=1)

# 方案 A
mu = X.mean(axis=1); sd = X.std(axis=1, ddof=1)
X.clip(lower=mu - sigma * sd, upper=mu + sigma * sd, axis=0)

# 方案 B
lo = X.quantile(0.01, axis=1); hi = X.quantile(0.99, axis=1)
X.clip(lower=lo, upper=hi, axis=0)
```

### A.2 原始输出 (2026-10-22)

```
=== 1. 基线: 当前 pipeline 截断不变式 ===
{'n_diff': 257, 'n_nan': 0, 'max_abs': 0.6984124662957469,
 'n_total': 1800, 'n_rows_diff': 31, 'first_bad': '2020-01-31'}
baseline per-day spearman: median= 0.999555 min= 0.984872 n_rows_lt_1= 31 / 60

=== 2. 候选方案截断不变式 ===
cs3  {'n_diff': 0, 'n_nan': 0, 'max_abs': 0.0, 'first_bad': None}
pct  {'n_diff': 0, 'n_nan': 0, 'max_abs': 0.0, 'first_bad': None}
none {'n_diff': 0, 'n_nan': 0, 'max_abs': 0.0, 'first_bad': None}

=== 3. 缩尾触发率 (fit 输入 = imputed, T=100, N=30) ===
current per-column full-sample 3sigma: (61, 45, 3000)
cross-sectional 3sigma          : (77, 73, 3000)
cross-sectional pct(1,99)       : (200, 100, 3000)

=== 4. 全样本输出差异 (方案 vs 当前) ===
cs3  {'n_diff': 561, 'max_abs': 1.044599719599574, 'n_rows_diff': 63}
pct  {'n_diff': 612, 'max_abs': 1.2203382234951228, 'n_rows_diff': 83}
none {'n_diff': 485, 'max_abs': 1.7394401869039493, 'n_rows_diff': 39}

=== 4b. 逐日 Spearman 分布 (方案 vs 当前) ===
cs3  median= 0.999110 min= 0.942603 n_rows_lt_1= 63 / 100
pct  median= 0.998665 min= 0.918131 n_rows_lt_1= 83 / 100
none median= 1.000000 min= 0.806007 n_rows_lt_1= 39 / 100

=== 4c. cs3 vs pct 直接差异 ===
{'n_diff': 394, 'max_abs': 1.044599719599574, 'n_rows_diff': 70}

=== 4d. clip 边界含 NaN 时的行为 ===
std= [0.7071067811865476, 0.0, 0.0, nan]
cs3: [[nan, 1.0, 2.0], [0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [nan, nan, 5.0]]
pct: [[nan, 1.01, 1.99], [0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [nan, nan, 5.0]]

=== 4e. 向量化 clip(axis=0) vs 逐行循环 对拍 ===
allclose= True

=== 5. 缩尾后 rank 的 ties 变化 ===
current tied_value_count= 0
cs3     tied_value_count= 4
pct     tied_value_count= 0

=== 6. 性能 (T=2500, N=3000, 3 次中位数) ===
current per-column runs= [0.512, 0.526, 0.497] median= 0.512s
cs3                runs= [0.285, 0.268, 0.239] median= 0.268s
pct                runs= [0.323, 0.308, 0.305] median= 0.308s

=== 7b. N 扫描: cs3 / pct(1,99) 触发格数 / 总格数 (T=60) ===
N=    5  cs3=0/300      (0.0000%)  pct=120/300    (40.0000%)
N=    8  cs3=0/480      (0.0000%)  pct=120/480    (25.0000%)
N=   10  cs3=0/600      (0.0000%)  pct=120/600    (20.0000%)
N=   11  cs3=1/660      (0.1515%)  pct=120/660    (18.1818%)
N=   15  cs3=15/900     (1.6667%)  pct=120/900    (13.3333%)
N=   20  cs3=32/1200    (2.6667%)  pct=120/1200   (10.0000%)
N=   30  cs3=46/1800    (2.5556%)  pct=120/1800   (6.6667%)
N=   50  cs3=76/3000    (2.5333%)  pct=120/3000   (4.0000%)
N=  100  cs3=135/6000   (2.2500%)  pct=120/6000   (2.0000%)
N=  300  cs3=327/18000  (1.8167%)  pct=360/18000  (2.0000%)
N= 1000  cs3=1082/60000 (1.8033%)  pct=1200/60000 (2.0000%)

=== 7c. sigma 敏感性 (T=100, N=30) ===
sigma=1.0 389/3000 (12.9667%)
sigma=1.5 245/3000 ( 8.1667%)
sigma=2.0 167/3000 ( 5.5667%)
sigma=2.5 115/3000 ( 3.8333%)
sigma=3.0  77/3000 ( 2.5667%)
sigma=4.0  29/3000 ( 0.9667%)
pct=(0.5, 99.5) 200/3000 (6.6667%)
pct=(1.0, 99.0) 200/3000 (6.6667%)
pct=(5.0, 95.0) 400/3000 (13.3333%)
```

> 注: `N` 扫描使用 `T=60` 面板, 与主实验 `T=100` 的触发格数不能直接横向比较; 表中比例是每行归一化后的结果。性能为单机单进程、3 次重复的中位数, 不作为跨机器基准。

---

## 附录 B: MCP 检索记录与失败说明

| 时间 | 工具 | 查询 | 结果 |
|------|------|------|------|
| 2026-10-22 | `mcp_paper-search_search_semantic` | "cross-sectional winsorization asset pricing factor 1st 99th percentile" | 返回 `[]` |
| 2026-10-22 | `mcp_paper-search_search_semantic` | "look-ahead bias data preprocessing financial machine learning" | 返回 `[]` |
| 2026-10-22 | `mcp_english-search_search_web` | "winsorize factor cross-sectional 1st 99th percentile each month Bali Engle Murray" | HTTP 404 |
| 2026-10-22 | `mcp_english-search_search_web` | "winsorization before ranking cross-sectional factor preprocessing ties robust" | HTTP 404 |
| 2026-10-22 | `mcp_paper-search_search_openalex` | "winsorization cross-sectional asset pricing factor preprocessing" | 返回结果与缩尾方法无直接相关 |
| 2026-10-22 | `mcp_paper-search_search_crossref` | "winsorization cross-section factor returns outliers asset pricing" | 返回结果与缩尾方法无直接相关 |

**处理**: 停止继续重试失败的检索工具; 文献部分改为复用项目内已核实文档 (`academic_literature_decision_criteria.md`, PL-01/PL-02 调研, ADR-027/037/038), 并标注证据等级。未复核的原文结论不作为强论据。

---

## 附录 C: 未验证/不确定事项

| 项 | 状态 | 处置 |
|----|------|------|
| Bali, Engle & Murray (2016) 原文的 1%/99% 表述 | 未读原文; PL-01 明确标记 `cross-sectional distributions` 逐字引文为**未验证** (U) | 设计文档引用时标注"项目内转引, 未逐字核验"; 不作为 B 方案的强论据 |
| "3σ 是经典阈值"的文献表述 | Hampel (1974)/Rousseeuw & Croux (1993) 核验的是 MAD/稳健尺度, 未逐字给出 3σ; MSCI FaCS 官方 PDF 明确采用"稳健均值 ± 3 稳健标准差" (A) | A 方案的 3σ 依据以 MSCI FaCS 工业实践 + 经典稳健统计框架为主, 不声称学术原文逐字支持 |
| 生产面板的典型截面 N 与偏度 | 未统计 | 设计文档不应假设 N=30; 小截面结论按数学性质陈述 |
| 方案 B 的配置迁移完整影响面 | 仅核对 optimizer 与部分测试 | 若设计选 B, 需单独列出迁移清单 |
| `transform_aggressiveness` 的其他作用点 | 只读 optimizer 映射 | 若选 B, 实施前需全仓 grep 复核 |
| 其他管线/脚本是否读取 `_winsorize_params` | 仓库内 grep 仅命中 `pipelines_v2.py` | 实施前再全仓复核一次 |
