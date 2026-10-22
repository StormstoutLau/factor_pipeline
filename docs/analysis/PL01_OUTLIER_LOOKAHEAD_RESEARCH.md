# PL-01 去极值前视缺陷调研 v1.1

**文档版本**: v1.1 (已实施, v3.3.3 / ADR-037)
**日期**: 2026-10-21 (调研), 2026-10-22 (实施)
**缺陷编号**: DEFECT-PL-01
**实施状态**: 已按本文结论实现: 逐日横截面 + `auto→percentile` + `auto_select=False`. 隔离测试 187 格/1.68e-01 → 0; Static 端到端 1.33e-02 → 4.72e-05. 详见设计文档 / CHANGELOG v3.3.3.
**调研范围**: `adapters.py` `ProcessingAdapter(process_type='outlier')` + `factor_adaptive_winsor` 的 `SmartOutlierDetector` + 三条生产管线的去极值路径
**调研方法**: 源码逐行核对 + 截断不变式实测 + 学术数据库检索 (Crossref/OpenAlex) + 工业实现与社区文档检索
**核心原则**: t 时刻的输出只能使用 `F_t` (t 时刻及以前可观测的信息); 对因子面板, 同一交易日内的横截面信息属于 `F_t`, 未来交易日不属于

**证据等级**:
- **A**: 直接读到原文/摘要/官方方法论文档, 可核对
- **B**: 搜索结果摘要或二手实现说明, 未读到原文对应段落
- **C**: 项目内部文档/代码, 可逐行核对
- **U**: 未能验证, 明确标注, 不作为论据

---

## §0 摘要 (TL;DR)

PL-01 不是单点 bug, 而是三个相互叠加的问题:

| # | 问题 | 性质 | 实测 |
|---|------|------|------|
| 1 | `fit()` 用 `X.values.flatten()` 在**全 panel** 上池化拟合缩尾参数 (具体方法由 `auto` 选型决定) | 前视: 前 t 期缩尾边界依赖 t 之后的数据 | 截断 60/100 期: 154 格差异, max 1.808e-01 (探针面板实际 auto→MAD; 项目测试登记 187 格 / 1.680e-01) |
| 2 | `SmartOutlierDetector(auto_select=True)` 覆盖显式 `method` | **第二重前视**: 方法选择依赖全样本分布特征 | 显式 `method='percentile'` 实际拟合为 `mad`; 200/200 个变波动率面板在截断前后选到不同方法 |
| 3 | 用户参数 (`threshold`, `percentile_lower/upper`) 未被真正消费 | 配置-行为不一致: 名义 1%/99%, 探针面板上实际拟合自适应 MAD 阈值 2.772 | `fitted_params['threshold']=2.7725`, 非配置的 3.0 |

**结论**:
1. 生产路径 `StaticFactorPipeline` 的去极值**并非** ADR-027 决策的 `percentile(1,99)`, 而是每轮由全样本特征自选的 `mad/adaptive/iqr/...`。ADR-027 "所有 auto → 固定方法" 在 adapter 层未实现。
2. 修复方向有充分的学术与工业证据支持: **因子面板按交易日逐截面缩尾** (`winsorize by date / cross-section`), 不是对整块 panel 展平, 也不是对每只股票的全历史单独缩尾。
3. 该缺陷长期未被发现, 是因为缩尾是**单调**变换, 排序类指标几乎不受影响: 前视与截断输出的逐日 Spearman 中位数 = 1.000, 最小值 = 0.9973。截断不变式 (值相等) 是比 IC/排序更灵敏的探测器。

---

## §1 缺陷复现与范围

### 1.1 代码路径

| 位置 | 行为 | 性质 |
|------|------|------|
| [adapters.py L413-454](../../adapters.py#L413-L454) | `fit` 进入 else 分支, `flat_data = X.values.flatten()` 后 `processor.fit(flat_data)` | 全 panel 池化, 跨日期混样 |
| [adapters.py L444-445](../../adapters.py#L444-L445) | `X.values.flatten()` 去掉 NaN 后拟合 | 边界 = 全样本分位数/MAD |
| [adapters.py L490-502](../../adapters.py#L490-L502) | `transform` 逐列 (`for col in X.columns`) 套用同一组全局边界 | 历史值随未来样本变化 |
| [transformers.py L31-42](../../modules/factor_adaptive_winsor/core/transformers.py#L31-L42) | `SmartOutlierDetector(method='auto', auto_select=True, ...)` | 默认开启自动选型 |
| [transformers.py L64-67](../../modules/factor_adaptive_winsor/core/transformers.py#L64-L67) | `if self.auto_select: selected_method = self._select_optimal_method(...)` | **显式 method 被静默覆盖** |
| [transformers.py L179-197](../../modules/factor_adaptive_winsor/core/transformers.py#L179-L197) | 依据 `n_samples / consensus_outlier_ratio / skewness` 5 选 1 | 选型依赖全样本特征 |
| [transformers.py L488-495](../../modules/factor_adaptive_winsor/core/transformers.py#L488-L495) | `percentile` 方法: `np.percentile` + `np.clip` | 若按行调用则天然因果 |
| [pipelines_v2.py L888-890](../../pipelines_v2.py#L888-L890) | Static 显式传 `method='percentile', percentile_lower=1.0, percentile_upper=99.0` | 意图正确, 但被 `auto_select` 覆盖 |
| [pipelines_v2.py L1150-1169](../../pipelines_v2.py#L1150-L1169) | Mixed 自己的 `_compute_winsorize_params`: 逐列 `mean/std` 全样本, `clip(axis=1)` | **PL-06**, 不在 PL-01 范围 |

关键事实: `ProcessingAdapter.fit` 把 `method` 与 `percentile_lower/upper` 传给 detector, 但**没有传 `auto_select=False`**。`SmartOutlierDetector` 的构造函数默认 `auto_select=True`, 因此在 `fit()` 内显式 `method` 被忽略。

### 1.2 实测

**探针环境**: Python 3.12, 项目源码未改动; 探针脚本位于系统临时目录, 不进入仓库。

| 测量 | 构造 | 结果 |
|------|------|------|
| 显式方法是否生效 | `ProcessingAdapter(outlier, method='percentile', 1/99)`, T=100/N=30/seed=7 | `adapter.method='percentile'`, 但 `processor.fitted_params['method']='mad'`, `threshold=2.7725` |
| 截断不变式 (实际 auto→MAD 路径) | 同上, 全样本 vs 前 60 期 | 154 格差异, max 1.808e-01 |
| 若 percentile 真正生效, 池化边界会怎样漂移 | 同一 panel 展平后计算 1%/99% | full=(-2.4956, 1.9540), trunc=(-2.5413, 1.8006); 仅作示意, 非上述 154 格的来源 |
| 自动选型稳定性 | 200 个波动率从 0.1 升到 3.0 的合成面板, 全样本 vs 前 60% | **200/200 选型改变**; 全样本 `adaptive` 196 / `quantile` 4, 截断后 `iqr` 200 |
| 排序指标敏感性 | 全样本 vs 截断, 前 60 期逐日 | Spearman 中位数 1.000, 最小 0.99733 (17/60 天 <1); Pearson 最小 0.99869 |
| 池化 vs 逐日缩尾 | 同一变波动率面板 | 池化边界在低波动期裁 0.0%, 高波动期裁 9.5%; 逐日缩尾两段均 6.7% |
| 逐日方案因果性 | 对前 60 期逐日计算分位并 clip | 与全样本前 60 期输出**完全相等** (`array_equal=True`) |
| 逐日 vs 逐列 expanding | 同一面板 | `max_abs_diff=4.474`, `mean_abs_diff=0.059` (两方案不等价) |
| 配置桥接是否可用 | `PipelineV2ConfigUnified().to_pipeline_config()` → `FactorProcessingPipeline` | **失败**: `TypeError: SmartOutlierDetector.__init__() got an unexpected keyword argument 'threshold'` |

**解释**:
- 池化参数 (无论 percentile 还是 MAD) 都把"横截面离散度"和"时间序列尺度"混在一起。当横截面波动率随时间变化时, 池化边界由高波动期主导: 低波动期几乎不裁, 高波动期过度裁。这不仅是前视问题, 也是**统计语义错误**。
- 自动选型对窗口极端敏感: 同一数据只要改变样本终点, 方法就从 `adaptive` 变为 `iqr`。这使结果不可复现, 且方法切换本身依赖未来样本。
- 排序指标几乎看不出问题, 解释了为什么因子 IC 回测没有暴露该缺陷; 但值域变化会传导到后续 neutralization / standardization / 组合权重。

### 1.3 小样本截面的事实

N=30 时 1%/99% 分位的实际行为 (2000 次标准正态截面模拟):

| 方法 | 平均裁剪比例 | 中位裁剪比例 | 备注 |
|------|-------------|-------------|------|
| 1%/99% 分位 | 6.7% | 6.7% | 上下各约 1 个观测; 较近一侧边界距最近极值平均 0.067σ |
| 3×1.4826×MAD | 1.0% | 0.0% | MAD 在 N=30 时抽样波动大, 部分截面 MAD 偏小导致多裁 |

结论: 在 N=30 的截面上, 1%/99% 并不是"几乎不裁", 而是稳定裁掉约 2 个名字; 这与工业界"1%/99%"的直觉一致。N 越小, 分位边界越贴近极值 (N=10 时距离 0.027σ), 但仍保持因果性。

---

## §2 判据: 什么是"因果的去极值"

对 (T, N) 因子面板 (行=日期, 列=股票), 记 `F_t` 为 t 日收盘后可观测的信息。要求:

```
outlier(x_{i,t}) = f( {x_{j,t} : j in universe_t}, 历史参数(若需要) )
```

- **逐日截面缩尾**: 只使用同日 `{x_{j,t}}` → 天然满足 `F_t`, 且历史输出不会因新数据而被重写。
- **逐列 expanding 缩尾**: 股票 i 使用自己的 `{x_{i,s}, s<=t}` → 也满足 `F_t`, 但同一日不同股票使用不同历史窗口, 与"横截面可比"的目标不一致。
- **全样本池化/逐列全样本**: 使用 `s>t` 的数据 → 违反。

这与 ADR-029 已确立的标准化原则同构: 逐日横截面 Z-Score 之所以无前视, 是因为 `fit` 不存参数, `transform` 只用当日截面重算。PL-01 的正确形态也应如此。

---

## §3 学术证据

### 3.1 前视/泄漏的界定

| 文献 | 与本缺陷的关系 | 证据 |
|------|----------------|------|
| Banz & Breen (1986), *Sample-Dependent Results Using Accounting and Market Data: Some Evidence*, JF, DOI 10.1111/j.1540-6261.1986.tb04548.x | 经典"样本依赖/前视"证据: 使用事后修订的 COMPUSTAT 数据会改变组合收益与结论 | **A** (摘要原文: "may introduce a look-ahead bias and an ex-post-selection bias") |
| Kaufman, Rosset, Perlich, Stitelman (2012), *Leakage in Data Mining*, ACM TKDD, DOI 10.1145/2382577.2382579 | 泄漏的一般定义: 引入"不应合法可用于挖掘"的目标信息; 提出 learn-predict separation | **A** (摘要原文) |
| Kapoor & Narayanan (2023), *Leakage and the reproducibility crisis in machine-learning-based science*, Patterns, DOI 10.1016/j.patter.2023.100804 | 8 类泄漏分类; 泄漏在 17 个领域、294 篇论文中造成过度乐观结论 | **A** (摘要原文) |
| Arnott, Harvey & Markowitz (2019), *A Backtesting Protocol in the Era of Machine Learning*, JFDS, DOI 10.3905/jfds.2019.1.064 | 回测协议; 强调研究流程中的信息隔离 | **A** (Crossref 元数据; 摘要为 SSRN 版) |
| Lo & MacKinlay (1990), *Data-Snooping Biases in Tests of Financial Asset Pricing Models* | 数据窥探偏差; 与"用全样本选择方法/参数"同源 | **A** (NBER w3001 摘要) |

**适用性说明**: 上述文献不直接讨论"缩尾边界"这一具体实现, 但它们确立了判据: 任何在 t 时刻使用了 t 之后信息的预处理都属于泄漏/前视。PL-01 的 `flatten()` 与 `auto_select` 满足该定义。

### 3.2 "逐日截面 1%/99%" 的学术与工业实践

| 来源 | 陈述 | 证据 |
|------|------|------|
| Green, Hand & Zhang (2017), *The Characteristics that Provide Independent Information about Average U.S. Monthly Stock Returns*, RFS 30(12):4389-4436, DOI 10.1093/rfs/hhx019 | 特征在每月横截面上 1%/99% 缩尾后标准化 | **B**: 复现文档称 "characteristics were first winsorized at the 1st and 99th percentiles"; arXiv:2508.14986 称 "cross-sectionally winsorize each predictor at the 1st and 99th cross-sectional percentiles, as in Green, Hand, and Zhang (2017)"。未读到原文该句, 故标 B |
| Kagkadis, Nolte, Nolte & Vasilas (2024), *Factor Timing with Portfolio Characteristics*, RAPS 14(1):84-118, DOI 10.1093/rapstu/raad010 | "We also winsorize characteristics cross-sectionally at a 99% confidence level" | **B** (出版商页面摘要片段) |
| Bongaerts, Kang & van Dijk (2026), *Revisiting Asset Pricing Models: The Case for an Intangibles Factor*, Financial Management 55(2):187-208, DOI 10.1111/fima.70001 | "individual firm characteristics within each portfolio are winsorized at the 1% and 99% levels" | **B** (Wiley 页面片段) |
| Bali, Engle & Murray (2016), *Empirical Asset Pricing: The Cross Section of Stock Returns* | 系统讨论 winsorization vs truncation; 多数实证资产定价研究选择 winsorization | **A** (Quant SE 答案引用 p.6 原文; Wiley StatsRef 概述文章 DOI 10.1002/9781118445112.stat07954, 不是书籍本身)。项目文档中"cross-sectional distributions"逐字引文**未能独立验证**, 见附录 C |
| MSCI FaCS Methodology (Bonne et al., 2018) | Barra 因子构建: 先剔除极端值, 再将剩余值 winsorize 到稳健均值 ± 3 个稳健标准差; 稳健均值/标准差迭代确定 | **A** (官方 PDF 原文) |
| DolphinDB, *Implementing a Multi-Factor Risk Model* (CNE6/Barra) | 风格因子预处理使用 MAD 去极值; 输入表按"记录日期、股票代码、原始因子"组织 | **A** (官方教程原文; 逐日截面由"record date + stock code"结构可推) |
| 华泰金工《因子合成方法实证分析》(2019-01-04, BigQuant 转载) | "设第 T 期某因子在所有个股上的暴露度向量为 Di, DM 为该向量中位数..." | **B** (转载页片段) |
| Portfolio Optimizer 文档, *Factors* | `PERCENTILE`: 1st/99th 固定分位; `MAD`: median ± 3×1.4826×MAD (MSCI Barra convention) | **B** (文档片段) |

**综合**: 本次检索到的学术与工业实践共同指向: **在每一个截面内部**定义极端值, 而不是在"整块面板"上定义。1%/99% 与 3×MAD (或 3σ) 是两种主流参数化; 前者是固定分位, 后者是稳健尺度。

### 3.3 稳健统计与分位数

| 文献 | 用途 | 证据 |
|------|------|------|
| Hampel (1974), *The Influence Curve and its Role in Robust Estimation*, JASA 69(346):383-393, DOI 10.1080/01621459.1974.10482962 | MAD 与稳健估计的经典来源 | **A** (Crossref 元数据) |
| Rousseeuw & Croux (1993), *Alternatives to the Median Absolute Deviation*, JASA 88(424):1273-1283, DOI 10.1080/01621459.1993.10476408 | MAD 的有限样本效率与替代尺度估计 (S_n/Q_n) | **A** (Crossref 元数据) |
| Hyndman & Fan (1996), *Sample Quantiles in Statistical Packages*, The American Statistician 50(4):361-365, DOI 10.1080/00031305.1996.10473566 | 样本分位数有多种定义; 小样本下分位边界的行为依赖定义 | **A** (Crossref 元数据) |

**为什么 1.4826**: 对正态分布, `MAD = 0.6745σ`, 故 `σ ≈ 1.4826 × MAD`。这是尺度一致性常数, 不是"3 倍标准差"本身; 3×1.4826×MAD ≈ 3σ (正态下)。项目若采用 MAD, 必须显式写常数, 避免"3 MAD"与"3σ"混淆。

### 3.4 与"无前视"直接相关的工程论文

| 来源 | 陈述 | 证据 |
|------|------|------|
| arXiv:2603.14288, *Beyond Prompting: Autonomous Factor Investing via Agentic AI* | "Cross-sectional preprocessing (such as ranking, z-scoring, and winsorization) is performed date by date, so each day is transformed using only same-day cross-sectional information rather than full-sample moments... preventing accidental look-ahead through panel-level operations." | **A** (HTML 原文, 已下载核对) |

这是与 PL-01 **逐字对应**的方法论陈述, 但属 2026 年预印本, 不能作为权威依据; 它的价值在于确认"panel-level operations"是已知的前视来源。

---

## §4 社区与工业实现

| 来源 | 做法 | 证据 |
|------|------|------|
| Swoopr, *Backtesting a Portfolio Optimization Process* | "Lookahead bias... even indirectly, through normalizing factors or data winsorization using the full-sample distribution" | **B** (行业博客搜索片段) — 与本缺陷同名 |
| QuantConnect Research Guide | 前视偏差的常见来源 (财务数据可用时点) | **B** (文档片段) |
| Quant SE Q43498, *Rolling Winsorization for Time-Series* (2019) | 用户对单资产时间序列提出 2 年 expanding 窗口缩尾; 回答强调先判断异常值性质 | **A** (API 全文)。说明: 时间序列场景用 rolling/expanding, 与截面场景不同轴 |
| Quant SE A43511 (skoestlmeier) | 引用 Bali et al. (2016): winsorization vs truncation 的选择取决于极值是否来自不同分布; 结果对选择敏感时应警惕 | **A** (API 全文) |
| finlab 文档 | `factor.cs.winsorize(0.05, 0.95)`: `cs` = cross-sectional | **B** (文档片段) |
| skelfresearch `sigc` 文档 | `winsor(x, p)` 归入 Cross-Sectional operators | **B** (文档片段) |
| qfeaturelib (PyPI) | `cs_robust_zscore`, `cs_rank` 等 "operations across all assets at each time point" | **B** (文档片段) |
| QuantArmy 教程 | 逐日 winsorize 1%/99% + median/MAD 的 cross-sectional z-score | **B** (教程片段) |

**社区共识的边界**:
- 因子面板 (同一日多股票可比) → 逐日截面。
- 单资产时间序列 (波动率、收益序列) → rolling/expanding。
- "对整块 panel 展平"在**本次检索到的**社区实现中未见到; 它既不是截面轴, 也不是时间轴。

---

## §5 项目内部矛盾 (文档 vs 代码)

| 文档声明 | 代码事实 | 影响 |
|----------|----------|------|
| [DECISIONS.md ADR-027 L1807-L1825](../../DECISIONS.md#L1807-L1825): "采用学术准则驱动的固定方法管线, 消除所有 `auto` 模式"; "Winsorizer `percentile(1,99)` ✅" | `ProcessingAdapter` 未传 `auto_select=False`; 显式 `method` 被覆盖 | ADR-027 在 adapter 层**未实现** |
| [principle_vs_hacking_audit_v2.md L43-L60](principle_vs_hacking_audit_v2.md#L43-L60): Winsorizer "已修复 ✓", 代码示例 `SmartOutlierDetector(method='percentile', ...)` | 示例缺少 `auto_select=False`; 实际拟合为 `mad` | "已修复"结论**不成立** |
| [academic_literature_decision_criteria.md L358-L385](academic_literature_decision_criteria.md#L358-L385): 建议 `ProcessingAdapter(..., method='percentile', ..., cross_sectional=True)` | `ProcessingAdapter` 无 `cross_sectional` 参数; 该设计**从未实施** | 方案文档与实现脱节 |
| [test_step1_winsorizer_percentile.py L53-L66](../../tests/unit/test_step1_winsorizer_percentile.py#L53-L66): 测试名 "截面缩尾: 每期独立计算分位数 — 向量化 (无 for 循环)" | 测试用手写 for 循环逐行 `fit/transform`; **未测试 adapter** | 意图是逐日截面, 但只验证了 detector 单行调用 |
| [config_v2.py L42-L64](../../config_v2.py#L42-L64): `OutlierConfig.lower_percentile=0.01` (0-1 小数) | detector 用 `percentile_lower=1.0` (0-100 百分数); [config_v2.py L456-L473](../../config_v2.py#L456-L473) 的 `to_pipeline_config()` 把 `threshold/lower_percentile/upper_percentile` 原样透传, detector 不接受 → **TypeError** (实测) | 配置桥接**不可用**, 且单位约定冲突; 与 PL-01 相邻但独立 |
| [config.py L114-L115](../../config.py#L114-L115): legacy pipeline 配置 `{'method': 'auto', 'auto_select': True}` | 同样受自动选型影响 | 旧路径也不是固定方法 |
| [ADR-029 L1934-L1963](../../DECISIONS.md#L1934-L1963): PL-01 不在 ADR-029 范围 | 本次调研确认其独立性与优先级 | 需要独立 ADR |

**新发现**: `StaticFactorPipeline` 名义上使用 `percentile(1,99)`, 但 `auto_select` 会按全样本特征重选方法; 在探针面板上实际拟合为 `mad` (阈值自适应到 2.772), 换一批数据可能选到 `adaptive/quantile/iqr`。因此 PL-01 的修复不仅是"改轴", 还会把 Static 的输出从"auto 选型"改为"固定 1%/99%"。这是**预期行为变更**, 必须在 ADR/CHANGELOG 中显式声明。

---

## §6 候选方案评估

### 6.1 方案

| 方案 | 描述 | 因果性 | 与文献/工业一致性 | 行为变化 | 复杂度 |
|------|------|--------|-------------------|----------|--------|
| **A. 逐日截面 (推荐)** | 每日用当日 N 只股票的横截面计算边界并 clip | 是 (结构上) | 高 (1%/99% 或 3×MAD per date) | 中: Static 由 auto 选型 (探针为 MAD) → 固定 percentile; 所有方法改为截面轴 | 低-中: `quantile(axis=1)` / `median(axis=1)` + `clip(axis=0)` |
| B. 逐列 expanding | 股票 i 用 `[0,t]` 历史计算边界 | 是 | 中 (时间序列场景) | 大: 同日不同股票边界不同 | 中-高: 逐列 expanding 分位 |
| C. 保持全样本 | 现状 | **否** | 低 | 无 | 无 |
| D. 仅 percentile 改逐日, 其他方法保持逐列全样本 | 局部修补 | **否** (显式 MAD/IQR 仍前视) | 低 | 小 | 低 |

**A vs B 的实测差异**: 同一变波动率面板, `max_abs_diff=4.474`, `mean_abs_diff=0.059`, 两方案不可互换。A 的语义是"同一日所有股票用同一把尺子", 与因子横截面比较、IC、分层回测的目标一致; B 的语义是"每只股票与自己的历史比", 更适合单资产时序信号。

### 6.2 方法选型 (auto 的处置)

| 选项 | 评价 |
|------|------|
| `auto` → `percentile(1,99)` (推荐) | 与 ADR-027、Static 管线意图、Bali et al. / Green et al. 实践一致; 无除法, 小样本稳定; 参数显式可审计 |
| `auto` → `mad` (3×1.4826) | 更稳健于重尾, 但 N=30 时 MAD 抽样波动大, 且平滑截断语义更复杂; 与 Static 显式配置冲突 |
| `auto` 保持自适应 (逐日选型) | 虽可做到逐日因果, 但方法日间切换, 结果不可复现, 且与 ADR-027 "消除 auto" 冲突 |
| 保留 `auto` 但记录选型 | 仍不可复现; 不推荐 |

**建议**: `auto` 在 `ProcessingAdapter` 构造期解析为 `percentile`, 并始终传 `auto_select=False`; 显式 `mad/iqr/z_score/quantile/adaptive/sigmoid_soft` 全部按截面轴执行。这样:
- `auto` 的行为确定且可审计;
- Static 的 `percentile(1,99)` 真正生效;
- legacy `pipeline.py` 的 `method='mad'` 也真正按 MAD 执行 (此前同样被覆盖);
- `config.py` 的 `auto_select=True` 不再具有绕过能力 (或在 adapter 层强制关闭)。

### 6.3 实现策略

| 策略 | 优点 | 缺点 |
|------|------|------|
| A1. 逐行循环调用 detector `fit/transform` | 完全复用现有方法语义 (含 `_smooth_clip`、`sigmoid_soft`), 改动最小, 正确性最易保证 | O(T) Python 循环; 与项目"向量化"方向不一致 |
| A2. adapter 内向量化计算边界 + `np.clip` | 快; 与 `_cross_sectional_zscore` 分支同构 | 需为每种方法实现边界; `_smooth_clip` 的 C¹ 平滑语义需另行向量化 |
| A3. 给 `SmartOutlierDetector` 增加 `axis='cross_section'` | 模块层统一, 可单测 | 模块改动面大; 影响其他调用方 |

**建议**: 设计阶段在 A2 与 A1 之间做基准测试后定夺。原则是"只改估计轴, 不改截断函数": `percentile` 保持 hard clip, `mad/iqr/z_score/quantile/adaptive` 保持现有 smooth clip 语义 (逐行计算 `result_std`)。若 A2 能逐行复现现有 `_smooth_clip` 公式, 优先 A2; 否则 A1 作为正确性基线, 再逐步向量化。

### 6.4 仍需在设计阶段决定的问题

| # | 问题 | 选项 | 备注 |
|---|------|------|------|
| Q1 | `percentile_lower/upper` 单位 | 保持 0-100 (detector 现状) / 统一为 0-1 (config 现状) | 建议保持 0-100, 在 config 接线时转换; 本次不改 config |
| Q2 | `threshold` 参数 | 显式传入并关闭 `adaptive_threshold` / 保持自适应 | 若要"参数可审计", 应关闭自适应; 但会改变 explicit MAD 的行为 |
| Q3 | 小截面保护 | `<3` 有效值 → 原样返回 / 警告 | 与 detector 现有 `<3` 跳过逻辑一致 |
| Q4 | 平滑截断 | 保留 `_smooth_clip` / 改为 hard clip | 建议保留, 避免非因果性变更 |
| Q5 | 是否提供时间序列轴 | 不提供 / `scope='expanding'` | 建议本次不提供; 生产管线均为因子面板 |
| Q6 | `OutlierConfig` 接线 | 本次不接 / 顺带修 | 建议单列后续任务: 当前 `to_pipeline_config()` 会因 `threshold/lower_percentile/upper_percentile` 键不被 detector 接受而 TypeError; 修 PL-01 时不要让它继续恶化即可 |

### 6.5 未纳入的替代方案 (范围外, 但需记录)

| 方案 | 与 PL-01 的关系 | 评价 |
|------|-----------------|------|
| 秩变换 / rank-normal (`Phi^-1((rank-0.5)/N)`) | 可完全替代缩尾, 对极值不敏感, 且单调保序 | MSCI Barra USE4 (Menchero et al. 2011) 与 Gu, Kelly & Xiu (2020) 在重尾因子中倾向 rank-normal (见 Portfolio Optimizer 文档, B 级)。它不是 PL-01 的修复, 而是**独立的分布变换决策**; 若采用, 需单列 ADR |
| Truncation (删失) | 与缩尾并列的极值处理 | Bali et al. (2016) 指出两者选择取决于极值是否来自不同分布; 删失会丢失样本, 本项目未采用 |
| 下游稳健回归 (Huber) | 处理极值对回归的影响 | 属建模层, 不能替代输入层缩尾; 与 PL-01 正交 |

**结论**: PL-01 的最小修复不应改变"缩尾"这一处理类型, 只修正其估计轴与参数解析。是否改用 rank-normal 属后续方法论决策。

---

## §7 验收标准草案 (供设计/实施文档细化)

1. **核心不变式**: `test_outlier_percentile_is_causal` 去掉 `xfail`, 全样本 vs 截断输出 `n_diff_cells=0`, `max_abs_diff=0`。
2. **方法覆盖**: `percentile / mad / iqr / z_score / quantile` 逐一通过截断不变式; `adaptive / sigmoid_soft` 至少验证单步因果性。
3. **方法解析**: 显式 `method` 必须被 detector 拟合为同名方法; `auto` 解析为 `percentile`; 断言 `fitted_params['method']`。
4. **参数生效**: 给定已知 panel, 1%/99% 边界等于手工 `np.percentile(row, [1,99])`; 显式 threshold 生效。
5. **小样本/NaN**: 行内有效值 <3 不崩; NaN 不参与分位计算且保持 NaN。
6. **传播效应**: Static 端到端差异降到 PL-02 量级 (设计阶段设定阈值); PL-04/PL-06/PL-07 的 xfail reason 更新。
7. **回归**: 适配器/管线/消融相关测试全绿; 全量套件的已知慢测单独安排。
8. **性能**: 对 T=2500, N=3000 的面板, 去极值步骤耗时不显著高于现状 (设计阶段定基准)。
9. **文档**: ADR 记录行为变更 (含 Static 由 MAD → percentile); 修正 `principle_vs_hacking_audit_v2.md` 的"已修复"错误结论; CHANGELOG 记录破坏性影响。

---

## §8 影响面与回滚

| 影响面 | 说明 |
|--------|------|
| `StaticFactorPipeline` | 去极值由"全样本 auto 选型" (探针为 MAD) 变为"逐日截面 percentile(1,99)" → 输出值改变, 历史 IC/Sharpe 需重算 |
| `pipeline.py` legacy / `demo.py` | 显式 `mad/auto` 终于按声明执行; 结果改变 |
| 消融实验 | `L1_winsorizer_off` 的 ΔIC 语义变为"纯关闭缩尾", 需重跑 |
| Mixed 管线 | 其自身 winsorizer (PL-06) 未变; 但上游若共用 ProcessingAdapter 则受影响 |
| 回滚 | adapter 分支可独立回退 (新增 `_cross_sectional_outlier` 路径, 不改 detector 默认); 回退后恢复全样本行为, 但 PL-01 重新出现 |

---

## §9 参考来源

**学术 (A/B 已注明)**
1. Banz, R. W., & Breen, W. J. (1986). Sample-Dependent Results Using Accounting and Market Data: Some Evidence. *Journal of Finance*. https://doi.org/10.1111/j.1540-6261.1986.tb04548.x
2. Kaufman, S., Rosset, S., Perlich, C., & Stitelman, O. (2012). Leakage in Data Mining: Formulation, Detection, and Avoidance. *ACM TKDD* 6(4). https://doi.org/10.1145/2382577.2382579
3. Kapoor, S., & Narayanan, A. (2023). Leakage and the reproducibility crisis in machine-learning-based science. *Patterns*. https://doi.org/10.1016/j.patter.2023.100804
4. Arnott, R., Harvey, C. R., & Markowitz, H. (2019). A Backtesting Protocol in the Era of Machine Learning. *JFDS* 1(1):64-74. https://doi.org/10.3905/jfds.2019.1.064
5. Lo, A. W., & MacKinlay, A. C. (1989, NBER w3001; 1990 RFS). Data-Snooping Biases in Tests of Financial Asset Pricing Models. https://doi.org/10.3386/w3001
6. Green, J., Hand, J. R. M., & Zhang, X. F. (2017). The Characteristics that Provide Independent Information about Average U.S. Monthly Stock Returns. *RFS* 30(12):4389-4436. https://doi.org/10.1093/rfs/hhx019 (方法细节为 B 级)
7. Kagkadis, A., Nolte, I., Nolte, S., & Vasilas, N. (2024). Factor Timing with Portfolio Characteristics. *RAPS* 14(1):84-118. https://doi.org/10.1093/rapstu/raad010 (B)
8. Bongaerts, D., Kang, X., & van Dijk, M. (2026). Revisiting Asset Pricing Models: The Case for an Intangibles Factor. *Financial Management* 55(2):187-208. https://doi.org/10.1111/fima.70001 (B)
9. Bali, T., Engle, R., & Murray, S. (2016). *Empirical Asset Pricing: The Cross Section of Stock Returns*. Wiley. (via Quant SE 引文, A; 概述文章 DOI 10.1002/9781118445112.stat07954)
10. Hampel, F. R. (1974). The Influence Curve and its Role in Robust Estimation. *JASA* 69(346):383-393. https://doi.org/10.1080/01621459.1974.10482962
11. Rousseeuw, P. J., & Croux, C. (1993). Alternatives to the Median Absolute Deviation. *JASA* 88(424):1273-1283. https://doi.org/10.1080/01621459.1993.10476408
12. Hyndman, R. J., & Fan, Y. (1996). Sample Quantiles in Statistical Packages. *The American Statistician* 50(4):361-365. https://doi.org/10.1080/00031305.1996.10473566
13. Bonne, G., Roisenberg, L., Aylur Subramanian, R., & Melas, D. (2018). *MSCI FaCS Methodology*. https://www.msci.com/downloads/web/msci-com/research-and-insights/blog-post/are-growth-and-value-indexes-still-in-style/MSCI-FaCS-Methodology.pdf
14. arXiv:2603.14288. *Beyond Prompting: Autonomous Factor Investing via Agentic AI*. https://arxiv.org/html/2603.14288 (预印本, 仅作方法学佐证)

**工业/社区**
15. DolphinDB. *Implementing a Multi-Factor Risk Model*. https://docs.dolphindb.com/en/Tutorials/multi_factor_risk_model.html
16. 华泰金工 (2019-01-04). *因子合成方法实证分析*. BigQuant 转载: https://bigquant.com/wiki/doc/jsUTAPMovV (B)
17. Portfolio Optimizer. *Factors*. https://silviobaratto.github.io/optimizer/guide/factors/ (B)
18. Quant SE Q43498 / A43511. *Rolling Winsorization for Time-Series*. https://quant.stackexchange.com/questions/43498/rolling-winsorization-for-time-series (A via API)
19. Swoopr. *Backtesting a Portfolio Optimization Process*. https://www.getswoopr.com/portfolio-management/portfolio-optimization/backtesting-a-portfolio-optimization-process/ (B)
20. finlab 文档. https://finlab.finance/docs/en/reference/dataframe/ (B)
21. skelfresearch sigc 文档. https://docs.skelfresearch.com/sigc/operators/cross-sectional/ (B)
22. qfeaturelib PyPI. https://pypi.org/project/qfeaturelib/ (B)
23. QuantArmy. *LLM signals and rigorous backtesting*. https://quantarmy.com/langchain/en/modulo-09/ (B)

**项目内部 (C)**
24. `DECISIONS.md` ADR-027 (L1799-L1825), ADR-029 (L1934-L1963)
25. `docs/analysis/principle_vs_hacking_audit_v2.md` L43-L60
26. `docs/analysis/academic_literature_decision_criteria.md` L358-L385
27. `tests/unit/test_step1_winsorizer_percentile.py` L53-L66
28. `tests/integration/test_pipeline_truncation_invariance.py` L230-L244
29. `docs/EXECUTION_ABLATION_V3.0.0.md` 中 `L1_winsorizer_off` 与 `rho_ref['winsorizer']=0.95`

---

## 附录 A: 检索记录

| 工具 | 查询/用途 | 结果 |
|------|-----------|------|
| `mcp_paper-search_search_crossref` | Banz & Breen; Kaufman; Lo & MacKinlay; Green et al.; Hampel; Rousseeuw & Croux; Hyndman & Fan; Arnott; Kagkadis; Bongaerts; Bali et al. | 均取得 DOI/元数据 |
| `mcp_paper-search_search_openalex` | 同一批标题 + winsorization/leakage 主题 | Banz & Breen、Kaufman、Kapoor & Narayanan、Lo & MacKinlay 等摘要 |
| `mcp_paper-search_search_semantic` / `mcp_research-tools_semantic_scholar_search` | 主题检索 | 返回空 / 429, 未作为证据 |
| `WebSearch` | 工业实践、中文券商、前视偏差 | 取得 MSCI/DolphinDB/华泰/Swoopr/finlab 等 |
| `mcp_stackexchange_search_questions` + `get_answers` | Quant SE winsorization | Q43498 全文与 A43511 全文 |
| `WebFetch` | MSCI FaCS PDF、DolphinDB、Portfolio Optimizer、arXiv:2603.14288 | MSCI/arXiv 原文核对; DolphinDB/Portfolio Optimizer 页面有截断, 关键句用搜索片段补足 |

**失败记录**:
- `mcp_english-search_search_web` 连续两次返回 404, 改用内置 `WebSearch`。
- Quant SE 网页直连被 Cloudflare 拦截, 改用 StackExchange API。
- Semantic Scholar API 返回 429/空, 改用 Crossref/OpenAlex。

---

## 附录 B: 探针结果 (原始)

```
[A] 显式 method='percentile'
adapter.method            = percentile
processor.fitted method   = mad
fitted_params             = {'method': 'mad', 'median': -0.16898,
                             'mad': 0.68570, 'threshold': 2.77247}

[B] 全 panel 展平分位数: 全样本 vs 前 60%
full  1/99 bounds = [-2.49559587  1.95397429]
trunc 1/99 bounds = [-2.54133922  1.80056593]

[C] 当前 adapter 输出: 全样本 vs 截断后前 60 期
n_diff_cells  = 154
max_abs_diff  = 0.1807948853817427

[D] 逐日截面 N=30 时 1%/99% 分位的实际裁剪量 (2000 个截面)
1/99 percentile: mean clipped frac = 0.067, median = 0.067
3*1.4826*MAD   : mean clipped frac = 0.010, median = 0.000

[E] N=10/20/30/50/100 时 1/99 分位较近一侧边界与最近极值的平均差距
    (metric = mean(min(lo - min, max - hi)), 标准正态)
N= 10: 0.027
N= 20: 0.047
N= 30: 0.067
N= 50: 0.098
N=100: 0.191

[A2] auto 选型: 200 个变波动率面板中截断前后方法改变 = 200
    full  : {'adaptive': 196, 'quantile': 4}
    trunc : {'iqr': 200}

[B2] 波动率从 0.1 升到 3.0 的面板
global bounds = (-3.773, 3.641)
global 裁剪比例: 前 20 期 0.000, 后 20 期 0.095
逐日裁剪比例: 前 20 期 0.067, 后 20 期 0.067

[C2] 逐日截面 vs 逐列 expanding: max|diff| = 4.474, mean|diff| = 0.059
[D2] 逐日截面: 前 60 期输出与全样本前 60 期完全一致 = True

[排序敏感性] 逐日 Spearman: min=0.997330 median=1.000000 (<1 的天数=17/60)
             逐日 Pearson : min=0.998694 median=0.999676
             总差异格数 = 154

[配置桥接]
OutlierConfig dump: {'method': 'auto', 'threshold': 3.0,
                     'lower_percentile': 0.01, 'upper_percentile': 0.99}
PIPELINE_FAILED: TypeError
SmartOutlierDetector.__init__() got an unexpected keyword argument 'threshold'
```

---

## 附录 C: 未验证/不确定事项

| # | 事项 | 状态 | 处理 |
|---|------|------|------|
| U1 | Bali et al. (2016) 原文是否逐字写 "cross-sectional distributions" | **未验证** | 项目旧文档的逐字引文不作为论据; 改用已核对的 winsorization/truncation 段落与 Green et al./RAPS 的横截面证据 |
| U2 | Green, Hand & Zhang (2017) 原文的缩尾轴 | **未读到原文** | 标 B, 依赖复现文档与 arXiv 引用; 设计文档不应把"原文逐字"作为唯一依据 |
| U3 | MSCI FaCS 的 "3σ" 是否按日截面计算 | PDF 只说 "robust mean/std... applied to coverage universe", 未逐字说 per date | 标 A 的仅有"用稳健均值/标准差缩尾"; 逐日截面由 Barra 模型结构与 DolphinDB 教程佐证 (B) |
| U4 | 1%/99% 在 N=30 的 6.7% 裁剪比例是否可接受 | 取决于研究目标 | 设计阶段给出 `min_names`/方法选择; 本研究只提供事实 |
| U5 | 修复后 Static 的 IC/Sharpe 变化幅度 | 需实数据/回测 | 实施后测量, 不在调研阶段承诺 |
| U6 | `adaptive`/`sigmoid_soft` 在逐日截面下的数值稳定性 | 未测 | 设计阶段单测覆盖 |
