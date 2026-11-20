# v3.9.3 调研 — alpha 衰减模型选择（FO-1）

---
id: v393-alpha-decay-model-RESEARCH
type: design
version: 1.3
status: verified
date: 2026-11-20
depends: []
upstream: null
---

> **Feature**: v3.9.3 alpha 衰减模型选择（FO-1：`net(h)` 恒 ≈ `−cost(h)`）
> **创建日期**: 2026-11-20
> **状态**: verified（Step 2 独立 pass 复审通过，2026-11-20，见 §8；异构复审通过，2026-11-20，见 §11）
> **补充调研**: §9（U-1 / U-2 裁决依据，v1.2）｜复核见 §10｜异构复审见 §11（v1.3）
> **Spec 步骤**: Step 1-2（Step 1 产出 + Step 2 复审记录）
> **批次档位**: **T1**（改动路径命中 `backtest/`、`scripts/`、`tests/` → Layer-1；见 `SPEC_PROCESS.md`「批次档位」）
> **对应待办**: [PROGRESS.md P-002](../../docs/PROGRESS.md)（P0）
> **前置批次**: [v3.9.2 校准读数口径修复](../v392-calibration-unit-fix/RESEARCH.md)（已裁决 c / rho / temporary 三项读数口径）
> **上游依据**:
> [v3.9.2 AUDIT.md](../v392-calibration-unit-fix/AUDIT.md) §5（FO-1 失败披露）、
> [v3.9.2 IMPLEMENTATION.md](../v392-calibration-unit-fix/IMPLEMENTATION.md) §8（实测读数）、
> [RESEARCH_V3.8.0_EXECUTION_CAPACITY.md](../../docs/research/RESEARCH_V3.8.0_EXECUTION_CAPACITY.md) §3.5 / §16.4、
> [DESIGN_EXECUTION_CAPACITY_V3.8.0.md](../../docs/private/DESIGN_EXECUTION_CAPACITY_V3.8.0.md) §7 / §10.2
> **实测证据**: [out/v392_calibration.md](../../out/v392_calibration.md) / [out/v392_calibration.json](../../out/v392_calibration.json)（v3.9.2 步骤 9 产出）
> **范围**: 只回答「alpha 衰减应以什么为估计对象、用什么估计量、在 39 月样本下如何判定」；**不实施、不改代码、不重跑校准**
> **执行限制**: 工作区为 untrusted，本步**不执行仓内脚本**；仓内事实来自静态读码 + 已提交校准工件

---

## 1. 调研目标

**核心问题**:

| # | 问题 | 结论落点 |
|---|------|---------|
| Q1 | 当前 `rho` 估计的**对象**错在哪里？「组合日超额 AR(1)」是否等价于 alpha 衰减？ | §3.1 / §4.1 |
| Q2 | 在 39 月、月频调仓、现有日频价格/月频因子的数据条件下，哪种 **alpha 期限结构**估计可复现且单位一致？ | §3.3 / §6.1 |
| Q3 | 函数形式（指数 / 双曲 / 非参）与不确定性处置应如何预注册，才能避免「挑参数让 `net(h)>0`」？ | §4.1 / §6.2 / §6.4 |

**验收对齐**（P-002）：① 39 月校准 `net(h)>0` 对 h∈{5,10,20} 至少一点成立且可复现；② `rho` 估计入选口径写入 DESIGN 并有 E1 证据；③ 默认 SHA 不变。

---

## 2. 调研方法

### 2.1 使用的工具与查询

| 工具 | 用途 | 查询 / 对象 | 结果 |
|------|------|-------------|------|
| Read / Grep | 本仓检索（F2：文件版本 + 行号） | `estimate_rho` / `net_curve` / `cost_by_h` / `compute_ic_decay` / `alpha0` | 命中，见 §3.1 |
| mcp_paper-search（arXiv） | 学术检索 | `optimal holding period signal decay transaction costs` | 命中 2502.04284；其余为物理/信号处理噪声 |
| mcp_paper-search（arXiv） | 学术检索 | `anomaly decay` / `alpha signal decay` | **失败**：返回 CV 异常检测、图信号论文（见 F3） |
| mcp_paper-search（Semantic Scholar） | 学术检索 | `alpha decay` / `When Systematic Strategies Decay` / `zeroing in on the expected returns of anomalies` | **失败**：多次返回空数组（见 F3） |
| mcp_paper-search（Google Scholar） | 学术检索 | `alpha decay estimation signal half-life` 等 3 条 | **失败**：全部返回空数组（见 F3） |
| WebSearch | 通用检索 | `alpha decay half-life IC decay estimation` / `site:arxiv.org alpha decay ...` / 各论文标题 + DOI | 命中；用于 ID 解析与摘要片段 |
| WebFetch | 原件抓取 | arXiv abs 页（2502.04284 / 2105.01380 / 2512.11913）、Semantic API（DOI 元数据）、Cambridge / OUP 页面 | 部分命中；Wiley / SSRN / unpaywall 返回空（见 F3） |

### 2.2 调研范围

- **时间范围**: 2013-2026（经典模型 2013/2016 + 近期 alpha 衰减研究 2021-2026）。
- **领域**: 量化权益组合的 alpha/signal 衰减、交易成本与再平衡频率、异常净收益。
- **排除**: 核物理 alpha 衰变、CV 异常检测、图信号处理（检索噪声）；执行冲击的时间衰减（属 v3.8.0 `impact_decay`，不在本批）。
- **证据分层**（`SPEC_PROCESS.md` §来源分层）：T1 一手（论文/官方） / T2 二手权威 / T3 社区 / T4 转述。

---

## 3. 调研发现

### 3.0 发现总表

| # | 发现 | 主要来源 | 置信度 |
|---|------|---------|--------|
| D1 | 当前 `rho` 是**组合日超额收益的一阶自相关**，衡量的是日频反转/噪声，不是 alpha 的信号持续性 | 仓内代码（E3）+ v3.9.2 实测（E1） | ★★★★★ |
| D2 | alpha 衰减在文献中的对象是**信号均值回归速度**（signal mean reversion / alpha decay），不是组合收益自相关 | Gârleanu & Pedersen 2013（T1）；Ma & Smith 2025（T1） | ★★★★☆ |
| D3 | 已发表的异常衰减是**年/月尺度**的慢衰减（样本外 −26%、发表后 −58%；新发表因子的衰减幅度每年 +5ppt），不能推出「半衰期 0.3 天」 | McLean & Pontiff 2016（T1）；Falck-Rej-Thesmar 2021（T1） | ★★★★☆ |
| D4 | `net(h)` 的符号由**乘子门槛**决定：h=5/10/20 分别需 `m(h) ≥ 0.592 / 0.296 / 0.148`；当前 `rho^20≈1.4e-19`，低于门槛 18 个数量级 | 本仓代数（E3），输入来自 E1 工件 | ★★★★★ |
| D5 | 衰减曲线函数形式不稳定；近期研究（v1→v3 大幅修订）未给出稳健的超指数/双曲优势，支持「指数 + 非参曲线 + CI」的简约口径 | Lee 2025 v3（T1 preprint）；Falck 等 2021 | ★★★★☆ |
| D6 | 成本随再平衡频率近似 `1/h` 放大；净收益是「衰减 × 换手成本」的联合结果，单看 `rho` 显著性会误判 | Novy-Marx & Velikov 2016（T1）；Chen & Velikov 2023（T1） | ★★★★★ |

### 3.1 本仓事实（E3 读码 / E1 工件）

#### 3.1.1 当前实现链

| 环节 | 位置 | 事实 |
|------|------|------|
| 估计量 | [decay.py L15-L43](../../backtest/execution/core/decay.py#L15-L43) | `estimate_rho`：去均值 AR(1) + Newey-West SE；CI 覆盖 1 → 返回 1.0 |
| 保留率 | [decay.py L46-L49](../../backtest/execution/core/decay.py#L46-L49) | `retention(h) = rho**h`，`h` 为**交易日** |
| 净收益 | [decay.py L78-L86](../../backtest/execution/core/decay.py#L78-L86) | `net(h) = aum·alpha0·rho**h − cost(h)`，只输出给定成本的 h |
| 端口 | [ports.py L57-L64](../../backtest/execution/ports.py#L57-L64) | `DecayModel.retention(horizons)` 唯一契约，具体实现只有 `ExponentialDecay` |
| 估计输入 | [panels.py L539-L552](../../backtest/execution/shell/panels.py#L539-L552) | `rho` 由 `ex_d`（组合**日**超额）估；`alpha0 = ex_m.mean()`（**月**频，39 点） |
| 成本 | [panels.py L609-L613](../../backtest/execution/shell/panels.py#L609-L613) | `cost(h)=(20/h)·aum·turnover_m·2·(FEE_BPS+impact_bps)/1e4`；`COST_HORIZONS=(5,10,20)` |
| 装配 | [runner.py L292-L310](../../backtest/execution/shell/runner.py#L292-L310) | runner 用 `rho_series` 重估，`rho<=0 → 1.0`，再算 `net_curve`（v1.3 H3：锚点起点精化，rho 初始化在 L292） |

#### 3.1.2 实测读数（E1，v3.9.2 步骤 9 工件）

| 量 | 值 | 来源 |
|----|----|------|
| `rho`（日频） | 0.1142，95% CI −0.0199 ~ 0.2482 | [out/v392_calibration.md L50](../../out/v392_calibration.md#L50) |
| 隐含半衰期 | `ln2/ln(0.1142) = 0.32` 交易日 | 代数（E3） |
| `alpha0`（月） | 0.002629（aum=1e10 → 26.29M/月） | 同上 L51 |
| `cost(5/10/20)` | 15.57M / 7.783M / 3.891M | 同上 L55-L57 |
| `net(5/10/20)` | −15.57M / −7.783M / −3.891M | 同上（≈ −cost） |
| `rho**5 / 10 / 20` | 1.94e-5 / 3.8e-10 / 1.4e-19 | 代数（E3） |
| 样本 | 39 月（2020-01~2023-03），股票数中位 4454 | 同上 L23-L25 |

#### 3.1.3 单位与量纲（E3 代数）

- `alpha0` 是**月**超额；`h` 是**交易日**；`cost(h)` 是「按 `20/h` 次/月调仓」的**月**成本。
- 现行式形可写为 `net(h)=aum·alpha0·m(h)−cost(h)`，其中 `m(h)` 是「按月 alpha 计的乘子」（现行代码取 `m(h)=rho**h`）。
- 正确口径下 `m(h)` 应等于「每 h 日调仓一次的月毛 alpha / 月持有 alpha」：`m(h)=A(h)/[A(20)·h/20]`；无衰减（alpha 线性累积）时 `m(h)=1`，且 `A(20)=alpha0` → **`m(20)=1` 是构造性的，不是假设**。
- 因此 `m(h)` **不能**用「组合日收益 AR(1) 的 `rho**h`」代替：后者是单日收益对前一日的系数，不是「月 alpha 在 h 日后的剩余比例」。
- 门槛（令 `net=0` 解 `m(h)`；这是**下界**，若 alpha 前置则 `m(h)>1`）：

| h | `cost(h)` | 需要的 `m(h)` | 等价 `rho**h` 的 `rho`（若强行沿用） |
|---|-----------|----------------|--------------------------------------|
| 5 | 15.57M | **≥ 0.592** | ≥ 0.9005（半衰期 ≥ 6.6 交易日） |
| 10 | 7.783M | **≥ 0.296** | ≥ 0.8854（半衰期 ≥ 5.7 交易日） |
| 20 | 3.891M | **≥ 0.148** | ≥ 0.9089（半衰期 ≥ 7.3 交易日） |

> 说明：第三列是「若沿用 `rho**h` 式形」的代数等价；它恰好暴露矛盾——需要 6.6~7.3 天半衰期，而当前估计给出 0.32 天。第三列**不是**推荐口径，仅用于说明现行公式的敏感性。
> 在正确口径下 `m(20)=1 ≥ 0.148` 恒成立，h=20 的净收益只取决于 `alpha0 > cost(20)`；真正的衰减检验在 h=5 / h=10。

#### 3.1.4 既有能力与数据边界

- **IC 衰减已有实现**：[factor_metrics.py L221-L262](../../backtest/factor_metrics.py#L221-L262) `compute_ic_decay(factor, returns, max_lag=12)`，按「`factor[:,t]` 对 `return[:,t+lag+1]`」逐 lag 求 rank IC 均值；输入是 `(股票×期)` 矩阵，**期粒度由调用方决定**。
- **月频因子面板可用**：[verify_capacity_impact.py L101-L128](../../scripts/verify_capacity_impact.py#L101-L128) 构建 5 因子 composite 的月频 `factor` + 月频 `ret`；可直接喂 `compute_ic_decay` 得 1~6 月 IC 曲线。
- **日频价格与权重可用**：[verify_capacity_impact.py L153-L176](../../scripts/verify_capacity_impact.py#L153-L176) `daily_portfolio_excess`；[L179-L233](../../scripts/verify_capacity_impact.py#L179-L233) 装配 `excess_m / excess_d / turnover_m`（**未保留形成期权重**，见 §6.2 约束）。
- **样本量**：39 个月形成期；日频窗口内观测高度重叠，独立观测数接近 39，不是 39×20。

#### 3.1.5 文档链冲突（必须由 DESIGN 裁决）

- [DESIGN_EXECUTION_CAPACITY_V3.8.0.md §7 L330](../../docs/private/DESIGN_EXECUTION_CAPACITY_V3.8.0.md#L330) 写「IC 序列**或**组合收益序列，日频」——两种对象从未裁决。
- 实现选择了组合收益序列；v3.8.1 调研 U3 的「组合月超额 AR(1)」建议也未在设计阶段裁决（v3.9.2 RESEARCH §4.2 已记录）。
- v3.9.2 只修了**频率**（月→日）与负值守卫，**没有修对象**；因此 `net(h)` 仍 ≈ `−cost`（FO-1）。
- 结论：本批必须把「估计对象」写成 DESIGN 的单一裁决，不能继续保留「或」。

### 3.2 外部文献

#### 3.2.1 Gârleanu & Pedersen (2013), *Dynamic Trading with Predictable Returns and Transaction Costs*

- **作者**: Nicolae Gârleanu, Lasse Heje Pedersen
- **出处**: *Journal of Finance* 68(6): 2309-2340；DOI `10.1111/jofi.12080`
- **Layer / 日期**: T1 / 2013-12（读取日 2026-11-20）
- **验证状态**: DOI `10.1111/jofi.12080` 经 **Crossref 解析命中**（Wiley，JF 68(6):2309-2340，2013-12，标题/作者/页码一致）；摘要已逐字读（Crossref 出版商摘要，含 "predictors with slower mean-reversion (alpha decay) get more weight"）；**PDF 全文未读**
- **关键结论**: 收益由「不同均值回归速度的信号」预测时，最优组合是现有组合与「aim portfolio（当前与未来 Markowitz 组合的加权）」的线性组合；**均值回归更慢（alpha 衰减更慢）的预测因子获得更高权重**。
- **相关性**: 直接支持「alpha 衰减 = 信号均值回归速度」这一对象；也说明衰减参数与交易成本共同决定最优换手，而非单独优化 `rho`。

#### 3.2.2 Ma & Smith (2025), *On the Effect of Alpha Decay and Transaction Costs on the Multi-period Optimal Trading Strategy*

- **作者**: Chutian Ma, Paul Smith
- **出处**: arXiv:2502.04284v1（math.OC; q-fin.MF），2025-02-06
- **Layer / 日期**: T1（预印本）/ 2025-02-06（读取日 2026-11-20）
- **验证状态**: **arXiv API（export.arxiv.org）解析命中 v1**（math.OC; q-fin.MF，作者 Chutian Ma / Paul Smith 一致）；摘要逐字读 ✅
- **关键结论**: 用「不仅当前信号值、**过去信号值也有预测力**」来模拟 alpha 衰减；无限期 MDP + 值迭代求最优策略；给出小交易成本下的渐近近似。
- **相关性**: 为「多期信号持续性」提供模型支撑；与本仓「单日收益 AR(1)」形成对照——衰减应体现在**信号对未来收益的预测力**上，而不是组合日收益的自相关。

#### 3.2.3 McLean & Pontiff (2016), *Does Academic Research Destroy Stock Return Predictability?*

- **作者**: R. David McLean, Jeffrey Pontiff
- **出处**: *Journal of Finance* 71(1): 5-32；DOI `10.1111/jofi.12365`
- **Layer / 日期**: T1 / 2016-02（读取日 2026-11-20）
- **验证状态**: DOI 经 **Crossref 解析命中**（Wiley，标题/作者/页码一致）；摘要逐字读 ✅（26% / 58% / 32% 三个数字逐字核对）；**PDF 全文未读**
- **关键结论**: 97 个预测变量的组合收益在样本外低 **26%**、发表后低 **58%**；其中约 32%（58%−26%）归因于发表后的交易。
- **相关性**: 衰减的**时间尺度是年/发表周期**；对 5~20 个交易日窗口，先验应是「衰减很轻」，而不是 0.3 天半衰期。用于设定先验与敏感性区间下限。

#### 3.2.4 Falck, Rej & Thesmar (2021), *Why and how systematic strategies decay*

- **作者**: Antoine Falck, Adam Rej, David Thesmar
- **出处**: arXiv:2105.01380（q-fin.ST），2021-05-04；期刊版本未核
- **Layer / 日期**: T1（预印本）/ 2021-05-04（读取日 2026-11-20）
- **验证状态**: **arXiv API 解析命中 v1**（2021-05-04，q-fin.ST，Antoine Falck / Adam Rej / David Thesmar 一致）；摘要逐字读 ✅（30% / 5ppt / 15% 逐字核对）；期刊出版信息 ⚠️ 未验证
- **关键结论**: 发表年份单独解释 Sharpe 衰减方差的 **30%**，每过一年新发表因子的 **Sharpe 衰减幅度增加 5ppt**；过拟合相关变量再加 15%。
- **相关性**: 支持「衰减主要由发表/套利资本驱动的慢过程」；对本批意味着 39 月样本内不应期待强衰减，除非信号本身很短寿。

#### 3.2.5 Chen & Velikov (2023), *Zeroing In on the Expected Returns of Anomalies*

- **作者**: Andrew Y. Chen, Mihail Velikov
- **出处**: *Journal of Financial and Quantitative Analysis* 58(3): 968-1004；DOI `10.1017/S0022109022000874`
- **Layer / 日期**: T1 / 2023-05（在线 2022-08-12；读取日 2026-11-20）
- **验证状态**: DOI 经 **Crossref 解析命中**（CUP，JFQA 58(3):968-1004，2023-05，在线 2022-08-12；标题/作者/页码一致）；摘要逐字读 ✅（4 / 10 / 20 bps 三档逐字核对）
- **关键结论**: 计入有效买卖价差、发表后效应与 2000 年后交易技术后，204 个异象的平均净收益仅 **4 bps/月**；最强异象约 10 bps；组合方法约 20 bps。
- **相关性**: 净 alpha 对成本极其敏感；支持 `net(h)` 必须与成本口径联合报告。**同时发现仓内文档元数据错配**（见 §5.1 / §5.3）。

#### 3.2.6 Novy-Marx & Velikov (2016), *A Taxonomy of Anomalies and Their Trading Costs*

- **作者**: Robert Novy-Marx, Mihail Velikov
- **出处**: *Review of Financial Studies* 29(1): 104-147；DOI `10.1093/rfs/hhv063`（NBER w20721）
- **Layer / 日期**: T1 / 2016-01（在线 2015-11-10；读取日 2026-11-20）
- **验证状态**: DOI 经 **Crossref 解析命中**（OUP，RFS 29(1):104-147，2016-01，标题/作者一致）；**摘要未读**（Crossref 未存该文摘要），仅用标题与仓内既有引用 → 内容标「标题级」
- **关键结论**: 异象净收益主要由换手驱动；成本估计必须与换手率敏感性一起报告；容量量级因异象差异巨大。
- **相关性**: 直接支撑 `cost(h) ∝ 1/h` 的结构，以及「净收益结论必须带换手敏感性」。

#### 3.2.7 Lee (2025/2026), *Return-Decay Residuals and Tail-Risk Forecasting*（v3）

- **作者**: Chorok Lee
- **出处**: arXiv:2512.11913 v3（v1 2025-12-11；v3 2026-09-26）
- **Layer / 日期**: T1（预印本）/ v3 2026-09-26（读取日 2026-11-20）
- **验证状态**: **arXiv API 解析命中 v3**（2026-09-26 修订；v1 发布于 2025-12-11，q-fin.PM，作者 Chorok Lee）✅；摘要逐字读；**v1 标题与结论已被 v3 大幅修订**
- **关键结论（v3）**: 衰减曲线残差对未来因子尾部损失**没有稳健预测优势**；结果对表示、目标定义与评分规则敏感；多种设定下与简单 Sharpe 基线无显著差异。
- **相关性**: 反对把衰减曲线拟合做得过复杂；支持「指数主口径 + 非参曲线并列 + CI」，并把函数形式差异降级为敏感性分析。
- **版本警告**: 检索片段中的 "Hyperbolic decay fits mechanical factors (R²=0.65)" 属 **v1**；v3 已改写并撤回该结论，**不得**作为超指数衰减的依据。

#### 3.2.8 Firoozye, Tan & Zohren, *Dynamic Portfolio Selection under Transaction Costs and Signal Decay*

- **出处**: SSRN 4425407（DOI `10.2139/ssrn.4425407`）；Written 2023-04-22，Posted 2023-04-28，Last revised 2023-12-26
- **Layer / 日期**: T2 / 读取日 2026-11-20
- **验证状态**: ID 经 **SSRN 检索命中**（标题 + 三作者 + 日期一致）；**摘要与全文仍不可达**（WebFetch 返回空）→ 内容未验证
- **处置**: 仅作线索，**不进入关键结论**。

#### 3.2.9 行业口径（T4，仅线索）

- 社区/工程实践常用 `IC(h)=IC₀·e^(−λh)`、半衰期 `ln2/λ`，并要求给置信带（v3.8.0 RESEARCH §3.5 已引）。
- **不得**作为 T1 方法学证据；本批若采用指数形式，理由来自 §3.2.1 的均值回归模型与 §3.2.7 的简约性，而非该公式本身。

### 3.3 方法族对比

| 方案 | 估计对象 | 数据需求 | 优点 | 缺点 | 判定 |
|------|---------|---------|------|------|------|
| A：组合日收益 AR(1)（现行） | 日收益自相关 | `excess_d` | 已实现、零新增数据 | **对象错配**；混入买卖价差反弹/反转；CI 覆盖 0 时无意义 | **淘汰** |
| B：IC 期限结构 | 信号对未来 h 日收益的 rank 相关 | 月频因子+收益（可直接用 `compute_ic_decay`）；日频需新建日频 composite 与重叠前向收益 | 与「信号预测力」语义一致；复用既有函数 | IC→组合 alpha 需截面离散度与 scale 假设；月频只能识别月尺度 | **佐证**（非主口径） |
| C：形成后累计 alpha 曲线 `A(h)` | 同一组合在 h 日内的累计超额 | 日频价格 + 形成期权重 + 基准 | 直接对应 `net(h)`；无需 IC→alpha 换算；可非参呈现 | 39 个形成期、窗口重叠 → 有效样本小；噪声大 | **主口径（推荐）** |
| D：信号/权重自相关 | 排名/权重持续性 | 因子分数或权重 | 与换手直接相关 | 衡量的是「排序稳定」而非「alpha 剩余」 | 佐证/诊断 |
| E：文献先验半衰期 | 外部先验 | 无 | 稳定、可解释 | 非数据驱动；A 股不可外推 | **兜底**（仅当 C 不可识别） |
| F：多滞后预测回归 | 信号滞后系数 | 较长面板 | 与 Ma & Smith 一致 | 39 月不足以稳定估计多滞后 | 远期 |

---

## 4. 综合分析

### 4.1 关键发现总结

1. **FO-1 的根因不是「rho 太小」，而是「rho 测错了对象」**：组合日超额 AR(1) 描述的是日频反转/微观结构，不是月 alpha 的剩余比例；把它代入 `rho**h` 必然得到 0.3 天半衰期。[置信度 ★★★★★]
2. **alpha 衰减应以「信号/组合 alpha 的期限结构」为对象**：GP 2013 把 alpha decay 定义为信号均值回归速度；Ma & Smith 2025 用多期信号持续性建模；两者都不支持「收益自相关」。[★★★★☆]
3. **先验应是慢衰减**：McLean-Pontiff 的 26%/58% 与 Falck 等的「衰减幅度每年 +5ppt」都在年/月尺度；39 月样本内出现「h=5 就衰减到 0」不符合任何已发表证据。[★★★★☆]
4. **净收益的判定门槛可预先算出**：`m(5)≥0.592`、`m(10)≥0.296`、`m(20)≥0.148`；这把「模型选择」变成可核对的数值命题，而不是事后挑参数。[★★★★★]
5. **函数形式应保持简约**：v3 的衰减曲线研究显示拟合结果对表示与评分敏感、无稳健预测优势；指数 + 非参 + CI 足够，双曲只作敏感性。[★★★★☆]
6. **h=5 的成本惩罚最强**（4× 月成本），因此「短持有期更优」只在衰减极快时成立；若估计为慢衰减，`h*` 大概率落在 10 或 20，且必须报告所有 h 而非只报最优。[★★★★☆]

### 4.2 技术 landscape

- **一手模型**：GP 2013（信号均值回归 + 交易成本 → aim portfolio）；Ma & Smith 2025（多期信号持续性 → MDP 最优策略）。
- **实证衰减**：McLean-Pontiff 2016（发表前后）、Falck 等 2021（发表年份与过拟合）、Chen & Velikov 2023（净收益 4 bps/月）。
- **曲线拟合**：Lee 2025 v3 表明衰减曲线残差无稳健预测力；超指数结论仅存在于已被修订的 v1。
- **本仓现状**：`compute_ic_decay` 已能算月频 IC 曲线；日频 `A(h)` 所需价格/权重已存在，但未装配到 `portfolio` 字典。

### 4.3 研究空白

1. 没有本仓/本样本的 **A 股 39 月 alpha 期限结构**实测（v3.8.0 只做了组合月超额 AR(1)）。
2. 没有「IC 曲线 → 组合 alpha 保留率」的换算规范；直接套用 `IC(h)/IC(0)` 会忽略截面离散度与 h 尺度。
3. 指数 vs 双曲 vs 非参在本样本上无对比证据；只能靠预注册与敏感性分析控制。
4. `net(h)` 目前是点值，没有 CI；「不显著」被当成「无衰减」会系统性高估容量。

---

## 5. 幻觉抑制审查（Step 2 Review）

> Step 1 曾在此留白（「正式验证由 Step 2 独立 pass 执行，不标 ✅」）。**Step 2（2026-11-20）已完成**：8 条外部来源逐条解析（Crossref REST / arXiv API / SSRN 检索）。口径统一为：§3.2 与 §5.2 的 ✅ = **摘要级已读**；**PDF 全文一律不标已验证**。复审过程、门禁与结论见 §8。

### 5.1 文献验证表（F4）

| 引用 | ID | Layer / 版本 / 日期 | 验证方式 | 状态 | 命中 / 差异 |
|------|----|---------------------|---------|------|-------------|
| Gârleanu & Pedersen 2013 | DOI 10.1111/jofi.12080 | T1 / JF 68(6):2309-2340 / 2013-12 | Crossref `works/<doi>` 解析 + 出版商摘要逐字读 | 已验证（ID + 摘要）；PDF 全文未读 | 标题 / 作者 / 页码一致 |
| Ma & Smith 2025 | arXiv:2502.04284v1 | T1（预印本）/ v1 / 2025-02-06 | arXiv API `id_list=` 解析 + 摘要逐字读 | 已验证（ID + 摘要） | 一致 |
| McLean & Pontiff 2016 | DOI 10.1111/jofi.12365 | T1 / JF 71(1):5-32 / 2016-02 | Crossref 解析 + 出版商摘要逐字读 | 已验证（ID + 摘要）；PDF 全文未读 | 一致（Step 1 未记卷期，本步补） |
| Falck, Rej & Thesmar 2021 | arXiv:2105.01380v1 | T1（预印本）/ v1 / 2021-05-04 | arXiv API 解析 + 摘要逐字读 | 已验证（ID + 摘要）；期刊版本未验证 | 一致 |
| Chen & Velikov 2023 | DOI 10.1017/S0022109022000874 | T1 / JFQA 58(3):968-1004 / 2023-05 | Crossref 解析 + 出版商摘要逐字读 | 已验证（ID + 摘要） | **元数据错配（仓内旧文档）**：v3.8.0 RESEARCH L699/L860 写成「RFS 2023」；实为 JFQA |
| Novy-Marx & Velikov 2016 | DOI 10.1093/rfs/hhv063 | T1 / RFS 29(1):104-147 / 2016-01 | Crossref 解析（标题/作者/页码） | **ID 已验证；内容「标题级」**（摘要不可得） | 一致 |
| Lee 2025/2026 | arXiv:2512.11913v3 | T1（预印本）/ v3 2026-09-26（v1 2025-12-11） | arXiv API 解析 + 摘要逐字读 | 已验证（v3 ID + 摘要） | **版本差异**：v1 标题与「双曲 R²=0.65」结论已被 v3 撤回 |
| Firoozye, Tan & Zohren 2023 | SSRN 4425407 / DOI 10.2139/ssrn.4425407 | T2 / 2023-04-22（rev. 2023-12-26） | SSRN 检索页命中 + WebFetch 失败 | **ID 可解析；内容未验证**（摘要/全文不可达） | 标题 / 三作者 / 日期一致 |
| Politis & Romano 1994 | DOI 10.1080/01621459.1994.10476870 | T1 / JASA 89(428):1303-1313 / 1994-12 | Crossref 解析（标题/作者/页码一致） | 已验证（ID） | 一致 |
| Altman & Bland 1995 | DOI 10.1136/bmj.311.7003.485 | T1 / BMJ 311(7003):485 / 1995-08-19 | Crossref 解析（标题/两作者/页码一致） | 已验证（ID） | 一致 |
| Nosek et al. 2018 | DOI 10.1073/pnas.1708274114 | T1 / PNAS 115(11):2600-2606 / 2018-03-13 | Crossref 解析 + 摘要逐字读 | 已验证（ID + 摘要） | 一致 |
| Wasserstein & Lazar 2016 | DOI 10.1080/00031305.2016.1154108 | T1 / TAS 70(2):129-133 / 2016-04 | Crossref 解析（标题/两作者/页码一致） | 已验证（ID） | 一致 |
| Northfield, *Alpha Decay and Optimization* | 无 DOI（northinfo.com/documents/1155.pdf） | **T2/T4** / 读取日 2026-11-20 | WebSearch 摘要片段 | **未验证**（无 ID；仅线索） | 仅用于动机佐证 |

> F4 判据：外部引用 ≥3 条 → 本表即出具形态；「未验证」行不得出现在关键结论中（Firoozye 仅作线索）。

### 5.2 技术声明验证

| 声明 | 来源 | 验证状态 |
|------|------|---------|
| alpha 衰减 = 信号均值回归速度 | GP 2013（出版商摘要逐字：「predictors with slower mean-reversion (alpha decay) get more weight」）；Ma & Smith 2025 摘要 | ✅ 摘要级（双源） |
| 衰减应建模为多期信号持续性 | Ma & Smith 2025 | ✅ 摘要已读 |
| 异象衰减是年尺度慢过程（26% / 58% / 32%） | McLean & Pontiff 2016 | ✅ 摘要级（三个数字逐字核对） |
| 发表年份解释 30% Sharpe 衰减方差、每年 +5ppt、过拟合再加 15% | Falck 等 2021 | ✅ 摘要已读（三个数字逐字核对） |
| 204 异象平均净收益 4 bps/月（最强 10 bps；组合法 20 bps） | Chen & Velikov 2023 | ✅ 摘要已读（三档逐字核对） |
| 成本由换手驱动、需换手敏感性 | Novy-Marx & Velikov 2016 | ⚠️ 标题级（摘要不可得）→ 不承载阻断断言 |
| 衰减曲线残差无稳健预测优势 | Lee 2025 v3 | ✅ 摘要已读 |
| `IC(h)=IC₀e^(−λh)` 是业界常用式 | 行业页面（T4） | ⚠️ 仅线索，不作 T1 |
| 不显著 ≠ 无效应；不得把「未检出衰减」写成「无衰减」 | Altman & Bland 1995；Wasserstein & Lazar 2016 | ✅ T1 双源（ID 已验证） |
| 分析计划与判定规则须在观测结果前预注册（prediction vs postdiction） | Nosek et al. 2018 | ✅ 摘要已读 |
| 弱相依/重叠观测的 CI 应用分块重采样（stationary bootstrap） | Politis & Romano 1994 | ✅ T1（ID 已验证） |
| alpha 衰减速度决定含成本下的最优换手 | Northfield 白皮书 | ⚠️ T2/T4 行业口径，仅动机佐证 |

### 5.3 待修正项

- [ ] **仓内元数据错配（T1 级事实，未修）**：`docs/research/RESEARCH_V3.8.0_EXECUTION_CAPACITY.md` L699 与 L860 将 *Zeroing In on the Expected Returns of Anomalies* 的期刊写成「Review of Financial Studies (2023)」；正确为 **Chen & Velikov, JFQA 58(3):968-1004, 2023, DOI 10.1017/S0022109022000874**。建议单列 T3 文档批订正（本批不改旧文档）。
- [ ] **版本引用纪律**：任何引用 arXiv:2512.11913 的地方必须标 `v3`，禁止沿用 v1 的「双曲衰减 R²=0.65」结论。
- [x] **Step 2 复核（2026-11-20）**：GP 2013 / McLean-Pontiff 2016 已从 Crossref 出版商摘要逐字读取，升为「摘要级」；仍不写「全文已验证」。
- [ ] **E3 锚点待重绑**：`git rev-parse HEAD` = `74a26ea`，但 `backtest/execution/` 在 HEAD 下为**未跟踪目录**（`git status` 显示 `?? backtest/execution/`）；本次锚点只能绑定「工作区快照」，实施前须在提交后重绑 commit hash。
- [x] **指数形式修正（v1.2）**：原拟 `m(h)=exp(λ(20−h))` 与累计 alpha 定义不一致（φ=0.95 时 h=5 高估约 53%，h=1 高估约 70%，见 §9.4.1）；已改为与 AR(1) 强度一致的 `m(h;φ)=(20/h)(1−φ^h)/(1−φ^20)`。
- [ ] **月长约定（U-5）待裁决**：`cost(h)` 硬编码 `20.0`（panels.py L612）、`alpha0` 用日历月均值（L552）、`days_by_month` 仅用于面板覆盖（L183/L193）——三者未统一，见 §9.3.2。
- [x] **归因层级修正（v1.3 异构复审 H1）**：§9.4.1 首条原把 AR(1) 强度/几何累积式形归为 GP 2013 模型设定，超出已读证据层级（本文档对 GP 仅读了出版商摘要，摘要无该式形）→ 已改为「本仓代数（标准几何累积）」，GP 摘要仅作方向支撑（见 §11）。
- [x] **F5 出具形态登记（v1.3 异构复审 H5）**：本档覆盖 Step 1-2（调研 + 复审），无代码 / fixture 改动；F5（红绿记录）属 Step 9 实施文档出具范围——按「不适用时写 N/A + 理由」纪律显式登记为 N/A。

---

## 6. 对设计的输入

### 6.1 可用的技术方案（建议排序）

**S1（主口径，推荐）— 形成后累计 alpha 曲线 `A(h)`**

- 对每个形成期 `t0`（月末），用**形成时权重不再调整**，计算 h=1..60 日的累计超额 `A_t0(h)`；对 39 期取均值/中位数，得 `A(h)`。
- 乘子：`m(h) = A(h) / [A(h_m)·h/h_m]`，其中 `h_m` 为「一个月」的交易日约定（U-5：建议 `h_m=20` 且 `alpha0 := mean A(20)`，使 `m(20)=1` 为构造性）。无衰减（alpha 强度恒定）时 `m(h)=1`；alpha **前置**（强度随 h 递减）时 **`m(h)>1`**；后置（强度递增）时 `m(h)<1`。同时报告累计保留率 `R(h)=A(h)/A(h_m)`（无衰减时 `R(h)=h/h_m`），仅作展示。
- 模型形式（**必须过 `m(20)=1`，且与 AR(1) 强度一致**）：令日 alpha 强度按 `φ^h` 衰减（`0<φ≤1`，φ=1 即无衰减），则

  `m(h;φ) = (h_m/h)·(1−φ^h)/(1−φ^{h_m})`，半衰期 `ln2/ln(1/φ)`。

  这是累计量的正确映射；**不得**用 `exp(λ(h_m−h))` 直接拟合 `m(h)`（φ=0.95 时 h=5 处高估约 53%，见 §9.4.1）。h>20 外推只作展示，不进入验收。
- 不确定性：**按形成期做 stationary bootstrap**（Politis-Romano 1994，期望块长 b=3；敏感性 b=1/6），重采 39 个 `A_t0(·)`；iid bootstrap 作交叉核对。不得把日频重叠窗口当独立样本。
- 判定：对 h=5 / h=10 报告 point + 95% CI。**只有 CI 上界 <1 才可称「衰减（后置）成立」**；CI 覆盖 1 → 采用 `m=1` 作**基准情景（flat alpha），不是上界**；保守容量用 **CI 下界**。禁止写「无衰减」（Altman-Bland 1995：不显著 ≠ 无效应）。`m(20)=1` 不参与检验。
- `net(h)` 一律带 CI，并同时报告非参 `A(h)` 与拟合 `m(h;φ)`。

**S2（佐证）— 月频 IC 期限结构**

- 直接复用 [compute_ic_decay](../../backtest/factor_metrics.py#L221-L262) 于月频 `factor`/`ret`，取 lag 1..6 月，拟合 `IC(k)` 半衰期。
- 只用于**方向一致性**（IC 半衰期与 A(h) 半衰期是否同量级），不直接换算成 `m(h)`——因为 IC→alpha 还差截面离散度与 h 尺度。

**S3（兜底）— 文献先验 + 敏感性网格**

- 当 `A(h)` 无法识别（CI 过宽、符号翻转、样本不足）时，采用文献先验半衰期（如 6/12 个月）跑敏感性，并在输出中标 `decay_source="prior"`；禁止把它写成「估计」。

**淘汰项**

- A（组合日收益 AR(1)）作为主口径：对象错配。
- 权重/信号自相关作为主口径：衡量排序稳定，不是 alpha 剩余。
- 双曲/多参数拟合作为主口径：无稳健证据，且易过拟合。

### 6.2 关键约束

1. **零新增依赖**、Python 3.9 语法、`__all__` 契约不越界（v3.9.2 A-3 教训）。
2. **默认输出 SHA 不变**：新估计只能进入校准/诊断路径，不得改变默认 `out/capacity_impact.json`。
3. **无前视**：`A(h)` 只用形成日之后的收益；形成期权重必须在 `t0` 已知；不得使用全样本均值做归一化后再回填历史。
4. **单位单一**：`alpha0`、`A(h)`、`cost(h)`、`net(h)` 必须同为「月」或同为「期」；DESIGN 需给出量纲表。
5. **h 语义**：`h` 保持交易日；`h_m` 为月长约定，且 `alpha0` 与 `A(h_m)` 必须**同口径**（U-5）；`m(h)` 的定义必须满足 `m(h_m)=1`（构造性），无衰减时 `m(h)=1`。
6. **样本诚实**：39 个形成期是有效独立单元；任何日频重叠窗口的 CI 必须按形成期 block bootstrap，不得按日算独立样本。
7. **预注册**：估计量、函数形式、判定规则（CI 覆盖 1 的处置）在 DESIGN 写死，实施阶段不得改；否则视为 criteria gaming。
8. **输出完整性**：h=5/10/20 全部报告，`h*` 只是摘要；不得只报使 `net>0` 的 h。

### 6.3 风险

| 风险 | 说明 | 缓解 |
|------|------|------|
| 小样本噪声 | 39 期、月 alpha≈0.26%，日噪声大；CI 可能覆盖 1 | block bootstrap；同时报非参与拟合；不把「不显著」写成「无衰减」 |
| 结果被成本主导 | `h=5` 需 `m≥0.592`；即使无衰减（m=1）也仅 10.7M 净收益 | 同时报 `net/cost` 比与 CI；不承诺容量 |
| 选择偏差 | 事后挑函数形式/窗口让 `net>0` | DESIGN 预注册；敏感性附表全公开 |
| 基准污染 | 累计超额若未减市场/等权基准，会混入 beta | 沿用 `daily_portfolio_excess` 的可投资域等权基准 |
| 幸存者/涨跌停 | 形成后不可交易日的收益不可实现 | 沿用 `tradable` 掩码；不可交易日按缺失处理并在证据警告中披露 |
| 文档漂移 | 旧 RESEARCH 的 T1 元数据错误、v1/v3 混用 | §5.3 待修正项；新文档只引 v3 |

### 6.4 未决项登记（四元块）

- **U-1 `m(h)` 的定义与量纲**
  - **判据**: DESIGN 明确写出 `A(h)`、`m(h)`、`R(h)` 三者关系与单位，且 `m(h_m)=1` 为构造性归一；`h_m` 与 `alpha0` 基准由 U-5 决定；量纲表通过 Step 4 Review。
  - **触发条件**: Step 3 设计开工时（必须先裁决再写接口）。
  - **当前倾向**: 采用 S1；`m(h)=A(h)/[A(h_m)·h/h_m]`，`R(h)` 仅作展示；CI 用按形成期 stationary bootstrap（b=3，敏感性 b=1/6）。
  - **证据等级**: E3（代数）+ E1（v3.9.2 工件）+ T1（Politis-Romano 1994，ID 已验证）。

- **U-2 函数形式与「不显著」处置**
  - **判据**: DESIGN 预注册三件事——(i) 累计比形式 `m(h;φ)=(h_m/h)(1−φ^h)/(1−φ^{h_m})`；(ii) 判定「CI 上界 <1 才称衰减；覆盖 1 → `m=1` 基准情景，保守容量用 CI 下界」；(iii) 禁止「无衰减」表述。双曲/非参仅列敏感性。
  - **触发条件**: Step 3；实施后不得更改。
  - **当前倾向**: φ 单参数累计比（过 `m(20)=1`）+ 非参曲线并列；`m=1` 只称「基准情景」，不称上界（§9.4.2 证明前置 alpha 下 `m>1`）。
  - **证据等级**: T1（GP 2013 摘要、Lee v3 摘要、Altman-Bland 1995、Wasserstein-Lazar 2016、Nosek 2018）。

- **U-3 CI 与 `net(h)` 报告形态**
  - **判据**: `net(h)` 输出 `point/lo/hi` 三值，且 CHECKLIST 有对应验收项；CI 构造写明按形成期 block bootstrap。
  - **触发条件**: Step 3 设计 + Step 9 实施。
  - **当前倾向**: 所有 h 报三值；`plateau` 用 `net` 的 bootstrap sd。
  - **证据等级**: E4（方法判断，待实施验证）。

- **U-4 接口与兼容性**
  - **判据**: 保持 `DecayModel.retention(horizons)` 可满足（`ExponentialDecay` 可用 `m(h)` 构造）；新增字段不影响默认 SHA；`__all__` 不越界。
  - **触发条件**: Step 3 设计接口时。
  - **当前倾向**: 内部重定义 `rho` 为 `m(1)` 或新增 `retention_curve` 证据字段；不破坏现有报告键。
  - **证据等级**: E3（读码）。

- **U-5 月长约定与 `alpha0` 基准**
  - **判据**: DESIGN 量纲表写死 `h_m`（固定 20 或实际 `days_by_month`）与 `alpha0` 定义（日历月均值或 `mean A(h_m)`），且 `aum·alpha0`、`A(h_m)`、`cost(h)` 使用同一 `h_m`；默认 SHA 不变。
  - **触发条件**: Step 3 写接口前（与 U-1 同批裁决）。
  - **当前倾向**: 固定 `h_m=20` + `alpha0 := mean A(20)`（改动最小、`m(20)=1` 精确）；若要求与日历月口径可比，改用实际 `days_by_month`（代价：h 网格随月变化）。
  - **证据等级**: E3（`panels.py` L552 日历月 alpha0 / L612 硬编码 20.0 / L183-L193 `days_by_month` 仅用于面板覆盖）。

> 第二轮（v1.2）**新开 U-5 且带触发条件**；U-1/U-2 已获 T1 依据但仍须 DESIGN 写死，判据未变、均带触发条件。

---

## 7. 参考文献

1. Chen, A. Y., & Velikov, M. (2023). Zeroing In on the Expected Returns of Anomalies. *Journal of Financial and Quantitative Analysis*, 58(3), 968-1004. DOI: 10.1017/S0022109022000874.
2. Falck, A., Rej, A., & Thesmar, D. (2021). Why and how systematic strategies decay. arXiv:2105.01380.
3. Gârleanu, N., & Pedersen, L. H. (2013). Dynamic Trading with Predictable Returns and Transaction Costs. *Journal of Finance*, 68(6), 2309-2340. DOI: 10.1111/jofi.12080.
4. Lee, C. (2025/2026). Return-Decay Residuals and Tail-Risk Forecasting: Timing Artifacts, Conditional Inference, and Cross-Market Evidence. arXiv:2512.11913v3（v1 2025-12-11；v3 2026-09-26）.
5. Ma, C., & Smith, P. (2025). On the Effect of Alpha Decay and Transaction Costs on the Multi-period Optimal Trading Strategy. arXiv:2502.04284.
6. McLean, R. D., & Pontiff, J. (2016). Does Academic Research Destroy Stock Return Predictability? *Journal of Finance*, 71(1), 5-32. DOI: 10.1111/jofi.12365.
7. Novy-Marx, R., & Velikov, M. (2016). A Taxonomy of Anomalies and Their Trading Costs. *Review of Financial Studies*, 29(1), 104-147. DOI: 10.1093/rfs/hhv063.
8. Firoozye, N. B., Tan, V. W. C., & Zohren, S. (2023). Dynamic Portfolio Selection under Transaction Costs and Signal Decay. SSRN 4425407（Written 2023-04-22；rev. 2023-12-26；⚠️ 摘要/全文不可达，仅元数据）.
9. Altman, D. G., & Bland, J. M. (1995). Statistics notes: Absence of evidence is not evidence of absence. *BMJ*, 311(7003), 485. DOI: 10.1136/bmj.311.7003.485.
10. Nosek, B. A., Ebersole, C. R., DeHaven, A. C., & Mellor, D. T. (2018). The preregistration revolution. *PNAS*, 115(11), 2600-2606. DOI: 10.1073/pnas.1708274114.
11. Politis, D. N., & Romano, J. P. (1994). The Stationary Bootstrap. *Journal of the American Statistical Association*, 89(428), 1303-1313. DOI: 10.1080/01621459.1994.10476870.
12. Wasserstein, R. L., & Lazar, N. A. (2016). The ASA Statement on p-Values: Context, Process, and Purpose. *The American Statistician*, 70(2), 129-133. DOI: 10.1080/00031305.2016.1154108.
13. Northfield Information Services. *Alpha Decay and Optimization*. 白皮书，无 DOI，https://www.northinfo.com/documents/1155.pdf（⚠️ T2/T4 行业口径，仅线索，不作方法学依据）.

---

## 8. 步骤 2 复审记录（v1.0 → v1.1，2026-11-20）

**复审方式**：① 4 条 DOI 走 Crossref REST（`api.crossref.org/works/<doi>`），按「标题 / 作者 / 年份或页码」三项比对；② 3 条 arXiv ID 走 `export.arxiv.org/api/query?id_list=…`，核对标题、作者、版本与摘要；③ SSRN 4425407 走检索页；④ 仓内锚点逐条 Read 核对（`decay.py` L15-49 / L78-110、`panels.py` L539-552 / L609-613、`runner.py` L292-310、`ports.py` L57-64、`out/v392_calibration.md` L23-25 / L50-57 / L84）；⑤ 门槛代数独立复算。

**独立性声明**：本次复审为**同基座新会话**的独立 pass（RULE-4 标 `自查（单视角）`；RULE-5 要求的异构基座审查在本仓不可用，故不宣称异构收益）。复审者只改验证状态与登记项，不改 D1-D6 结论。

### 8.1 复核通过项

| # | 项 | 复核结果 |
|---|----|---------|
| P1 | 4 条 DOI 字段比对 | GP 68(6):2309-2340（2013-12）/ McLean 71(1):5-32（2016-02）/ Chen 58(3):968-1004（2023-05）/ Novy-Marx 29(1):104-147（2016-01），标题+作者+页码一致 ✅ |
| P2 | 3 条 arXiv | 2502.04284v1（Ma & Smith）/ 2105.01380v1（Falck, Rej & Thesmar）/ 2512.11913v3（Chorok Lee）标题、作者、版本一致 ✅ |
| P3 | 摘要级数字 | McLean 26% / 58% / 32%、Falck 30% / +5ppt / 15%、Chen 4 / 10 / 20 bps 与出版商或 arXiv 摘要**逐字一致** ✅ |
| P4 | 门槛代数 | 15.57/26.29 = **0.592**；7.783/26.29 = **0.296**；3.891/26.29 = **0.148**；等价 `rho` 0.9005 / 0.8854 / 0.9089；半衰期 6.61 / 5.69 / 7.26 交易日 ✅ |
| P5 | v3.9.2 读数 | `rho=0.1142`（CI −0.0199~0.2482）→ 半衰期 `ln2/ln(1/0.1142)=0.32` 交易日；`rho**5/10/20` = 1.94e-5 / 3.77e-10 / 1.42e-19 ✅ |
| P6 | 仓内锚点 | `decay.py` / `panels.py` / `runner.py` / `ports.py` / `out/v392_calibration.md` 全部命中；`runner.py` 实际自 L292 起（文档写 L293-310，落在区间内）；`v392_calibration.md` L84 的「20/h 近似」注记属实 ✅ |

### 8.2 发现与修正

| # | 级别 | 发现 | 修正 |
|---|------|------|------|
| F1 | P2 | §5 原写「本文件**不把任何外部引用标为 ✅**」，但 §3.2 已有多处 ✅（口径自相矛盾） | 统一口径：✅ = **摘要级已读**；PDF 全文一律不标；§5 首段已改写 |
| F2 | P3 | GP / McLean 原写「未读原件」，无法区分「未读摘要」与「未读全文」 | 改为「出版商摘要已逐字读；PDF 全文未读」 |
| F3 | P3 | E3 锚点未绑 commit hash；且 `backtest/execution/` 在 HEAD `74a26ea` 下未跟踪（`?? backtest/execution/`） | 记入 §5.3，实施前须在提交后重绑 |
| F4 | P3 | SSRN 4425407 原标「仅元数据」但未写解析方式 | 补 SSRN 检索命中（标题 / 三作者 / 日期一致）；内容仍标未验证 |
| F5 | P3 | 参考文献 McLean 缺卷期页码 | 补 71(1):5-32 |

### 8.3 门禁（ADR-0008 D4，进 Step 3 前必过）

| 门禁 | 判据 | 结果 |
|------|------|------|
| (a) FALSIFIED 断言改写 | 复查未发现被证伪的方法学断言；F1 属表述冲突，已改写 | **通过** |
| (b) CONFLICT / STEP_GAP_OPEN 仲裁 | §3.1.5 的「IC 序列 或 组合收益序列」冲突已明确移交 Step 3 由 DESIGN 唯一裁决（触发条件已写）；U-1~U-4 全部带触发条件 | **通过（移交 DESIGN）** |
| (c) 阻断性断言双源 | D1 = 代码 E3 + v3.9.2 E1 工件；D4 = 代数 E3 + E1 输入；D2 / D3 / D6 各 ≥2 个 T1 来源；Novy-Marx 内容为单源「标题级」，**不承载阻断断言** | **通过** |
| (d) 假设转 A/B 或 [待定] | 6.2 的 8 条约束 = B 类设计约束；U-1~U-4 = [待定] 且带触发条件 | **通过** |

### 8.4 复审结论

**PASS_WITH_FIXES（已闭环）**：v1.0 → **v1.1**，`status: verified`。D1-D6、S1/S2/S3、8 条约束、U-1~U-4 均维持不变。遗留两项**不阻断 Step 3**：① 仓内 v3.8.0 RESEARCH 的 Chen & Velikov 期刊元数据订正（建议单列 T3 批）；② E3 锚点待提交后重绑 commit。

---

## 9. 补充调研 — U-1 / U-2 裁决依据（v1.2，2026-11-20）

### 9.1 调研问题与通道（F1-F3）

| # | 问题 | 未决项 |
|---|------|--------|
| Q4 | 乘子的分子/分母基准、月长约定、`alpha0` 与 `A(h_m)` 是否同量、CI 如何构造 | U-1（并新开 U-5） |
| Q5 | 指数形式是否与累计定义一致、「CI 覆盖 1 → `m=1`」能否称上界、「不显著」如何表述与预注册 | U-2 |

**通道与降级链（F3）**：
- `mcp_paper-search`（Semantic）`signal decay holding period portfolio turnover transaction costs` → **空数组**（失败）→ 降级 OpenAlex 同义查询 → 返回 GP 工作论文重复项（非目标）；OpenAlex 再查 `alpha decay rebalancing frequency holding period` 与 `optimal holding period stock signals` → **两次空数组** → 降级 WebSearch → 命中 Northfield / Qontigo 行业页（T2/T4）。
- 统计方法四条：WebSearch 命中 BMJ / JASA / PNAS / TAS 页面 → **Crossref 逐条解析 4/4 命中**（§9.2）。
- 未取证：SSRN / Wiley / T&F 全文仍不可达（沿用 §5.1 状态）。

### 9.2 新增来源与仓内事实

| 来源 | ID / 位置 | Layer / 日期 | 用途 |
|------|-----------|--------------|------|
| Politis & Romano 1994 | JASA 89(428):1303-1313；DOI 10.1080/01621459.1994.10476870 | T1 / 1994-12（Crossref 命中，读取日 2026-11-20） | U-1 CI 构造 |
| Altman & Bland 1995 | BMJ 311(7003):485；DOI 10.1136/bmj.311.7003.485 | T1 / 1995-08-19（Crossref 命中） | U-2 表述纪律 |
| Wasserstein & Lazar 2016 | TAS 70(2):129-133；DOI 10.1080/00031305.2016.1154108 | T1 / 2016-04（Crossref 命中） | U-2 表述纪律 |
| Nosek et al. 2018 | PNAS 115(11):2600-2606；DOI 10.1073/pnas.1708274114 | T1 / 2018-03-13（Crossref 命中；摘要已读） | U-2 预注册 |
| Northfield, *Alpha Decay and Optimization* | northinfo.com/documents/1155.pdf（无 DOI） | **T2/T4** / 读取日 2026-11-20 | U-1 动机佐证，不作方法学依据 |
| 仓内：`alpha0` 定义 | `panels.py` L552 `alpha0 = ex_m.mean()`（日历月） | E3 / 工作区快照 `74a26ea` | U-1 / U-5 |
| 仓内：月长常量 | `panels.py` L612 `(20.0 / h)`（硬编码） | E3 / 同上 | U-1 / U-5 |
| 仓内：`days_by_month` | `panels.py` L40-L47 定义，L183/L193 仅用于面板覆盖 | E3 / 同上 | U-5 备选方案 A |

### 9.3 U-1 裁决依据

#### 9.3.1 乘子基准：为什么是「单位时间 alpha 之比」

- 定义 `m(h)=A(h)/[A(h_m)·h/h_m]=[A(h)/h]/[A(h_m)/h_m]`，经济含义 = 「每 h 日调仓一次的单位时间毛 alpha ÷ 月持有基准的单位时间毛 alpha」。
- 备选与淘汰：

| 候选 | 定义 | 问题 | 判定 |
|------|------|------|------|
| 累计保留率 `R(h)=A(h)/A(h_m)` | 累计量比 | 随 h 单调增，直接乘月 alpha 会把「时间累积」误当「保留率」 | 仅展示 |
| 单日强度比 `α(h)/α(0)` | 某一天的强度 | 不覆盖持有期，无法映射 `cost(h)` | 淘汰 |
| 权重/信号自相关 | 排序稳定性 | 测的是换手来源，不是 alpha 剩余 | 诊断（§3.3 D） |

- 文献位置：GP 2013 的 alpha decay 是**信号均值回归速度**（摘要逐字支撑）；Northfield（T2/T4）明确「decay 速度决定含成本下的最优换手」。二者支持「期限结构 + 换手成本联合决策」，但**均未给出 `m(h)` 的归一化式**——本仓式形是内部代数（E3），DESIGN 必须声明为「本仓约定」，不得写成文献结论。

#### 9.3.2 月长约定（新开 U-5）

| 方案 | `h_m` | `alpha0` | `cost(h)` | 评价 |
|------|-------|----------|-----------|------|
| A 实际月长 | `days_by_month(t)` | 日历月均值 | `(h_m/h)·…` | 量纲严格；h 网格随月变化，接口与回归面扩大 |
| **B 固定 20（推荐）** | 20 | **`mean A(20)`** | `(20/h)·…` | 自洽、`m(20)=1` 精确；与日历月 alpha0 差约 0~5%（月长 20~22 日） |
| C 混用（拒绝） | 20 | 日历月均值 | `(20/h)·…` | `m(20)≠1`，构造性归一被破坏，量纲不一致 |

- 结论：B 为本批最小自洽方案；A 作为后续增强（U-5 触发条件）。**若选 B，`alpha0` 由 0.002629 改为 `mean A(20)`，E1 数值基线须在 Step 9 重算**——这是 DESIGN 必须显式登记的派生产物。

#### 9.3.3 CI：按形成期的 stationary bootstrap

- 39 个形成期是独立单元；形成期内日频重叠**不**产生独立样本。
- Politis-Romano（T1）：对弱相依序列做分块重采样，保留局部依赖，得到标准误与置信域。
- 参数（预注册）：期望块长 b=3，敏感性 b=1（iid）/ b=6；重采 1000 次，百分位 CI。
- b 的选择属 E4 方法判断，DESIGN 须写死并公开敏感性。

### 9.4 U-2 裁决依据

#### 9.4.1 形式：累计比，而非 `exp(λ(h_m−h))`

- AR(1) 强度衰减与几何累积（**本仓代数**，标准几何衰减式形；GP 2013 摘要仅支撑「衰减 = 信号均值回归速度」这一**方向**，`A(h)` 式形未经全文核读，异构复审 H1）：日 alpha 强度 ∝ `φ^h`；累计 `A(h)=α₀(1−φ^h)/(1−φ)`。
- 归一化后 `m(h;φ)=(h_m/h)(1−φ^h)/(1−φ^{h_m})`：`m(h_m)=1` 构造性；φ=1 → `m≡1`；φ→0 → `m=h_m/h`（alpha 全在第 1 日）。
- 原拟 `exp(λ(h_m−h))` 只是局部近似，**不是**累计比：φ=0.95 时 h=5 处高估 **53%**（2.158 vs 1.411）、h=1 处高估 **70%**（2.650 vs 1.559）→ 已修正（§5.3）。
- 单参数 φ 符合 Lee v3「复杂形式无稳健优势」的简约性证据；双曲形式只作敏感性。

#### 9.4.2 「上界」不成立（关键修正）

- `net(h)=aum·alpha0·m(h)−cost(h)`，对 `m` 单调递增。
- 强度**前置**（递减）时 `m(h)>1`（h<h_m）；**后置**（递增）时 `m(h)<1`；只有平坦强度 `m=1`。
- 因此「CI 覆盖 1 → `m=1` 是上界」**不成立**：真实为前置则 `m>1`（容量被低估），真实为后置则 `m<1`（容量被高估）。`m=1` 只能叫**零衰减基准情景**。
- 判定规则（预注册）：

| 观测 | 结论 | 容量用法 |
|------|------|----------|
| CI 上界 <1 | 后置衰减成立 | 用 point 或 CI 上界 |
| CI 覆盖 1 | 未检出衰减 | `m=1` 基准；保守容量用 CI 下界 |
| CI 下界 >1 | 前置 alpha 成立 | 用 CI 下界（保守） |

- 表述纪律：Altman-Bland（不显著 ≠ 无效应）+ ASA（CI 不度量原假设为真的支持度）→ **禁止**写「无衰减」「alpha 不衰减」，只能写「未检出衰减」。

#### 9.4.3 预注册（Nosek 2018）

- 在观测 39 月 `A(h)` 结果**之前**，DESIGN 写死：估计量、φ 模型类、判定规则、bootstrap 参数、报告字段。
- 实施阶段若改动任一项，须登记 deviation 并重跑全部读数（防 criteria gaming）；与 §6.2 #7 一致。

#### 9.4.4 与验收 ① 的关系（重要提示）

- 正确口径下 `m(h_m)=1` 构造性成立 ⇒ `net(h_m)=aum·alpha0−cost(h_m)=26.29M−3.89M=+22.4M>0`（E1 输入 + E3 代数）。
- 即：**P-002 验收 ① 在修正口径下几乎恒成立**（只要 `alpha0>0`、成本口径不变）；真正的判别力在 h=5/h=10 的 `m(h)` 与 CI，以及是否出现 `m<1`（后置）。
- 建议 DESIGN 显式写出该推论，并把 h=5/10 报告列为实质验收项；**不改 P-002 原文**（如需修改由用户裁决）。

### 9.5 对裁决的输入（结论）

| 未决项 | 建议裁决 | 依据等级 | 状态 |
|--------|----------|----------|------|
| U-1 | `m(h)=A(h)/[A(h_m)·h/h_m]`；CI = 按形成期 stationary bootstrap（b=3；敏感性 1/6） | E3 + T1（GP / Politis-Romano） | 待 DESIGN 写死 |
| U-2 | φ 单参数累计比；CI 上界 <1 才称衰减；`m=1` 为基准非上界；禁止「无衰减」表述 | T1（GP / Lee v3 / Altman-Bland / ASA / Nosek） | 待 DESIGN 写死 |
| U-5（新） | 固定 `h_m=20` + `alpha0 := mean A(20)` | E3 读码 | 待 DESIGN 裁决 |

**遗留**：方案 A（实际月长）与日历月可比性；`alpha0` 改变对 E1 读数的影响须在 Step 9 重算。

### 9.6 与 §6 的差异（下游注意）

1. §6.1 的 `exp(λ(20−h))` → 改为累计比 `m(h;φ)`；
2. §6.1 的「`m=1` 是上界」→ 改为「基准情景」；
3. 新增 U-5，§6.2 #5 已加同口径约束。

---

## 10. 步骤 2 复审记录（v1.2 增量，2026-11-20）

**复审方式**：4 条新 DOI 走 Crossref 逐条解析（4/4 命中，标题/作者/页码一致）；Northfield 无 ID 保留「未验证」；§9.4.1 代数复算（φ=0.95：`m(5)=1.411`、exp 近似 2.158、高估 53%）；`panels.py` L552 / L612 / L183-L193 读码复核。
**独立性声明**：同基座新会话独立 pass，标 `自查（单视角）`（RULE-4）；不宣称异构。
**门禁**：(a) FALSIFIED 两项（exp 近似、`m=1` 上界）已改写并登记 §5.3；(b) 无新增 CONFLICT，U-5 带触发条件；(c) U-1/U-2 建议均为 E3 代数 + T1 双源；(d) 新增假设全部以 U-5 / 预注册条目携带。**PASS_WITH_FIXES（已闭环）**。
**遗留**：U-5 待 Step 3 裁决；E3 锚点待提交后重绑。

---

## 11. v1.3 异构复审记录（RULE-5 异构基座 pass，2026-11-20）

> **异构声明**: 本 pass 在独立新会话中由与 §1-§10 撰写会话**不同**的模型基座执行——构成 RULE-5 意义上的异构复审，而非「同基座新会话」；基座家族信息以会话记录为准，复审方不自证撰写方基座。
> **单向权限**: 复审只作标记（§11.2 发现表）；修正均为标记后的最小修复落盘，D1-D6 与 §9.5 建议裁决的实质结论未被复审方改写。
> **复审对象**: RESEARCH v1.2 全文（§1-§10）。
> **执行方式**: 全文重读 + 仓内锚点逐条核对 + 11 项引用重解析（8 DOI Crossref + 3 arXiv API，独立于 §8/§10 的解析链）+ 代数独立复算。
> **结论: PASS_WITH_FIXES** —— 5 项发现（H1-H5）：P2 级 1 项（H1）、P3 级 4 项；H1/H3/H5 已最小修复，H2/H4 登记，无遗留阻断项。

### 11.1 视角 × 探针矩阵（沿用 v3.8.0 §19 形态）

| 视角 | 探针 | 结果 | 说明 |
|------|------|------|------|
| V1 公式与计量正确性 | P1 全量代数复算（独立执行） | PASS | 门槛 m≥0.5922/0.2960/0.1480；等价 rho 0.9005/0.8854/0.9089（半衰期 6.62/5.69/7.26 交易日）；rho=0.1142 半衰期 0.3195、rho^5/10/20=1.942e-5/3.773e-10/1.423e-19；φ=0.95：m(5)=1.4105 vs exp 形 2.1585（高估 53.0%）、m(1)=1.5588 vs 2.6500（高估 70.0%）；m(20)=1.000000 构造性成立；φ→0 → m=h_m/h（h=5 → 4）、φ→1 → m≡1；net(20)=26.29−3.891=+22.399M；0.148/1.42e-19≈18.0 个数量级 |
| V2 引用与出处 | P2 11 项引用重解析 | PASS（0 偏差） | GP JF 68(6):2309-2340（摘要含 "slower mean-reversion (alpha decay)"）；McLean-Pontiff JF 71(1):5-32（26%/58%/32% 逐字）；Chen-Velikov JFQA 58(3):968-1004（4/10/20 bps 逐字）；Novy-Marx RFS 29(1):104-147（Crossref 记录确无 abstract 字段，「摘要不可得」声明属实）；Politis-Romano JASA 89(428):1303-1313；Altman-Bland BMJ 311(7003):485；Nosek PNAS 115(11):2600-2606；Wasserstein-Lazar TAS 70(2):129-133；arXiv 2502.04284v1（math.OC+q-fin.MF）｜2105.01380v1（30%/5ppt/15% 逐字）｜2512.11913v3（v1 2025-12-11、v3 2026-09-26，"no robust advantage"） |
| V3 数据与内部一致性 | P3 §3.1.2 实测读数 ↔ E1 工件；§6.1 ↔ §9.5 ↔ §6.3 口径一致 | PASS（1 登记 → H4） | rho/alpha0/cost/net/样本数与 v392_calibration.md L23-57 全一致；半衰期 6.61（§8.1）vs 6.62（本轮全精度）系门槛先舍入（0.592）再取幂所致，两组值各自自洽 |
| V4 与代码库对齐 | P4 E3 锚点逐条核对（decay.py / panels.py / runner.py / ports.py / factor_metrics.py / verify_capacity_impact.py / DESIGN L330） | PASS（2 登记 → H2/H3） | 全部锚点命中且语义一致（含 `compute_ic_decay` 的 `lag+1` 偏移、形成期权重未保留、DESIGN L330「IC 序列或组合收益序列」冲突）；L110 超 EOF、runner rho 初始化在 L292，见 H2/H3 |
| V5 决策效度 | P5 归因层级纪律 + 判定规则保守方向 + 建议裁决可回溯 | FAIL → 已修复（H1） | §9.4.1 首条把 AR(1) 几何累积式形归为 GP 2013 模型设定，超出已读证据层级（Crossref 出版商摘要无此式形）；三态判定规则方向保守、§9.5 建议裁决锚点充分 |

### 11.2 发现清单

| ID | 级别 | 章节 | 缺陷 | 处置 |
|----|------|------|------|------|
| H1 | P2 | §9.4.1 | 「GP 2013 的 AR(1) 信号：…累计 `A(h)=α₀(1−φ^h)/(1−φ)`」把式形归因给 GP，但本文档对 GP 仅读了出版商摘要（摘要无 AR(1)/几何累积式形），违反本档 F4 纪律（摘要级引用只能支撑摘要内陈述） | 已修复：改标「本仓代数（标准几何累积）」，GP 摘要仅作方向支撑；§5.3 同步登记 |
| H2 | P3 | §8（历史记录） | 复审锚点写「decay.py L15-49 / L78-110」，L110 超出文件 EOF（decay.py 实际 107 行） | 不回改历史记录，此处登记；L78-107 实测全命中，该轮结论不受影响 |
| H3 | P3 | §3.1.1 | runner.py 锚点 L293-310：rho 初始化在 L292（区间外一行）；实质内容（估计/守卫/net_curve）均在区间内 | 已修复：锚点精化为 L292-L310 |
| H4 | P3 | §3.1.3 / §8.1 | 半衰期 6.61 vs 6.62：前者由舍入门槛 0.592 取幂，后者为全精度（0.5922）计算 | 登记，无需修正；DESIGN 引用时统一用全精度 6.62/5.69/7.26 |
| H5 | P3 | §5.3 | F1-F4 已出具，F5（红绿记录）无显式 N/A 声明（本档 Step 1-2 无代码改动，F5 属 Step 9 出具） | 已修复：§5.3 补 N/A 登记行 |

### 11.3 复审边界

- 未读任何 PDF 全文（沿本档声明）；GP / Chen / Novy-Marx / McLean 维持「摘要级」，SSRN / Northfield 维持「未验证 / 仅线索」，本轮不自证升级；
- 代数复算为浮点独立执行，不重放 §8/§10 的计算过程；结论一致即判 PASS；
- E3 锚点仍绑定「工作区快照」（`backtest/execution/` 未提交），commit hash 重绑遗留不变（§5.3）；
- 本 pass 不改 §9.5 三条建议裁决与验收①推论的实质内容；是否采纳仍由 Step 3 DESIGN / 用户裁决。

---

**Review 签字**: 独立 pass（同基座 · RULE-4 自查声明）｜v1.1 全量复审 2026-11-20；v1.2 增量复审 2026-11-20｜**异构复审**（RULE-5 异构基座 · 独立新会话 · 见 §11）: v1.3 全量复审 2026-11-20｜结论: PASS_WITH_FIXES → `verified`
