# 调研报告 — v3.8.0 多日执行模型 + Regime 容量压力测试

> **日期**: 2026-11-18
> **状态**: 调研完成（三轮；§16 已为 D1-D4 补齐外部锚点，§17 给出架构契约，待设计评审）
> **上游**: [PORTFOLIO_CAPACITY_IMPACT_STRESS](../analysis/PORTFOLIO_CAPACITY_IMPACT_STRESS.md) §7.2-2 / §8、
> PROJECT_STATUS P1#4 / P1#5 / P2#1 / P2#6
> **代码现状**: [verify_capacity_impact.py](../../scripts/verify_capacity_impact.py)（c ∈ {0.1, 0.5, 1.0} 敏感性网格，无实证校准）
> **本次调研聚焦**: ① c 系数实证校准（分钟数据 + OHLC 代理）② α 衰减与执行延迟 ③ regime 容量压力测试
> ④ 移动窗口替代固定样本外 ⑤ 数据新鲜度守卫核销

---

## §0 摘要与关键判断

| 问题 | 判断 | 依据 |
|------|------|------|
| E 盘分钟数据能否校准 c | **能，但只能给出区间与上界，不能给点估计** | 分钟 bar 无逐笔方向，方向分类精度上限 76–81%（Lee-Ready/tick rule 实测量级） |
| 是否需要 OHLC 低频代理 | **需要**，分钟数据只到 2023-03-30，样本 2020-01→2026-01 有 34 个月无分钟覆盖 | 覆盖实测见 §2.1 |
| α 衰减能否估计 | **能**，用日频构造 d=0…10 的持有期收益曲线 | 现有日频数据完整，且可复用 v3.7.0 的 bootstrap |
| S2 固定样本外能否补救 | **改用滚动窗口参数外推**，不是"新样本外"，是"参数稳定性检验" | Inoue-Jin-Rossi (2017)、Rossi-Inoue 窗长稳健检验 |
| 结论形态 | **区间 + 最差 regime + 参数漂移诊断**，禁止单一 c 点估计入报告 | 平方根律本身有反证（CKS 2011） |

**核心方法论立场**：v3.7.0 的教训是「单一路径读数会被口径噪声翻转」。本批必须从一开始就采用**三证据链三角验证 + 多估计量方向一致性 + 最差情形**，并在报告里显式标注哪些量不可识别。不可识别的量宁可留空，不给伪点估计。

---

## §1 问题清单

| ID | 问题 | 现状 | 本批目标 |
|----|------|------|---------|
| Q1 | 平方根冲击系数 c 无实证校准，仅敏感性网格 | `SQRT_C = (0.1, 0.5, 1.0)`，中央 0.5 无出处 | 估计 c 的区间与指数 b（检验 b≈0.5） |
| Q2 | 永久/临时冲击未分离，容量对 c 平方敏感 | `breakeven_aum ∝ (net/impact)^2` | 用 T+1 reversal 估计临时冲击占比 |
| Q3 | 多日执行与 α 衰减未建模，默认单日成交 | 容量按单日 100% 集中成交 | 拆 2–3 日成交 + 延迟 0…10 日 α 衰减曲线 |
| Q4 | 容量只在全样本/两段（S1/S2）测算，无 regime 压力 | `segments` 仅 S1/S2 | 按成交额/波动/涨跌停/极端月分层，取最差 |
| Q5 | S2 样本外止于 2026-01-30，无法更新 | 固定切分 | 滚动窗口参数外推 + 漂移诊断 |
| Q6 | 数据新鲜度守卫未默认执行 | `check_data_contract` 为 opt-in | 研究入口默认前置断言 |

---

## §2 本地数据可行性（实测）

### 2.1 E 盘分钟数据

| 项 | 实测值 | 影响 |
|----|--------|------|
| 路径 / 格式 | `E:\Level 1 Data\YYYY-MM-DD.feather`，每日一文件 | 需 pyarrow 读取 |
| 覆盖区间 | **2014-01-02 → 2023-03-30**，2250 个交易日 | 容量样本 2020-01→2026-01 中覆盖 **39/73 月（53%）**；39 月含尾月 2023-03（数据止于 03-30，非整月），按「有数据即计入」口径（复审 R-F9 复核实测确认） |
| 规模 | 25.6 GB，单日 662k–1.28M 行 | 全量加载不可行，需按股票/月聚合 |
| 字段 | `stock_code, time, open, high, low, close, volume, amount` | 无买卖方向、无逐笔、无盘口 |
| 时间轴 | `time` 为 HHMMSS 整数；241 个标签（09:30…11:30, 13:00…15:00） | 标准日内 240 分钟 |
| 代码 | 个股为纯数字（`1` = 000001）；**混入 2537 个 399xxx 指数** | 必须过滤 |
| 价格 | **未复权原始价**（000001 于 2023-03-30 分钟收盘 12.68，与未复权日收盘一致） | 除权日需剔除或复权 |
| 零成交 | 分钟 volume=0 占比 **3.85%** | 影响有效交易强度与 VWAP 口径 |
| 收盘集合竞价 | 15:00 为独立 bar | 执行价口径需明确是否含收盘竞价 |

**关键限制**：2023-04 之后无分钟数据 → c 的**时间外推无法直接验证**，只能靠 OHLC 代理桥接（§4.1 路径 B）。

### 2.2 日频/月频

- 样本 2020-01 → 2026-01（73 月），日频含 `close` + `adj_factor`，可按除权日对齐；
- S2 样本外止于 2026-01-30，数据不再更新 → Q5 只能做滚动参数外推；
- `mv` 于 2026-01-23 停更、barra 于 2023-05-31 停更 → **容量与执行模型不得依赖 mv/barra**（用成交额 + 日频波动即可）。

### 2.3 依赖缺口

`pyproject.toml` 的 `dependencies` **不含 pyarrow**（`pandas>=2.0` 不强制）。运行环境已装 pyarrow 24.0.0。
读取 feather 若要进仓库代码，需在 `[project.optional-dependencies]` 增加 optional group（第三轮 §16.1 建议命名 `calib`，与第一轮的 `research` 命名并存，最终以 D1 裁决为准），
或在脚本内延迟 import 并给出明确错误提示。**此为待裁决项（§9-D1）**。

---

## §3 外部证据锚点

### 3.1 平方根律与指数 b

- 冲击对参与率的幂律 `impact ∝ p^b`，文献主流 b≈0.5，但**b 不是常数**：Tóth et al. (2011) 与
  Bouchaud et al. 的实证 b 在 0.4–0.7 区间波动。
- **反证必须纳入**：Cont, Kukanov & Stoikov, *The Price Impact of Order Book Events*（arXiv:1011.6402）
  指出平方根关系"**is not robust and is a statistical artifact due to the aggregation of data**"——
  线性冲击模型 + 尺度化即可生成表观 sqrt 律。→ 因此本批**必须做聚合层级敏感性**（分钟 / 日 / 周），
  并同时报告线性模型（现已有 `k*participation`）与 sqrt 模型，不能只报 sqrt。
- *The "double" square-root law*（arXiv:2502.16246，东京交易所）表明 sqrt 律存在机械成分，跨市场可比。

### 3.2 c 的量级锚点

| 来源 | 口径 | 数值 |
|------|------|------|
| JFQA, *Price Impact in Closing/Opening Auctions and Continuous Markets* | 美股，平方根模型，1% ADV | 均值 **17.7 bps**，中位 **8.4 bps**，截面标准差 34.6 bps |
| 中文社区/教程（si-xiaoming、掘金） | `MI = k·σ_d·sqrt(p)`，k 约 **0.1** | k 无实证出处，属经验法则 |
| Almgren et al. (2005)、Gatheral | `Y·σ·sqrt(Q/V)` | Y 典型 0.5–1，随市场/时段变化 |
| arXiv:1610.08767, *Equity Market Impact Modeling: an Empirical Analysis for Chinese Market* | 中国 A 股，172 亿条逐笔 | 自建模型优于 Almgren 模型（可作中国市场的模型选择依据） |
| CME (2025) 平方根模型复盘 | 期货 | 波动率上升期冲击被重新定价，k 非恒定 |

→ **c 不是常数，是本批最重要的先验**。校准目标改为「c 的分布 + 随 regime 的条件依赖」，而非单一数。

### 3.3 低频（OHLC）流动性/价差代理

- **Corwin & Schultz (2012)** 高低价价差估计；**Abdi & Ranaldo (2017)** CHL 估计（RFS 30(12):4437）：
  建议用 **two-day corrected** 版本，比月度修正版估计误差更小。
- **RFS (2023), *When Do Low-Frequency Measures Really Measure Effective Spreads?***：Holden (2009)、
  Fong-Holden-Trzcinka (2017)、CRSP 价差、以及 **consistent 版 CS/AR 估计量**无大系统偏差、
  与高频基准相关性好——这为「用 OHLC 代理桥接 2023-04 之后」提供方法合法性。
- **FEDS 2019-051, *When do low-frequency measures really measure transaction costs?***：`CS_M` 精度最好，
  但**在 s=10bps 时有 38% 的估计恰好为 0**（零截断）→ 必须报告零截断比例并做截断校正，否则低估价差。
- Khovanova & Ødegaard：CS/AR 类估计量对市场结构变化不敏感，适合长样本外推。
- **Amihud (2002)** 非流动性作为冲击的横截面排序变量（不做绝对水平）。

### 3.4 方向分类精度（决定 c 的可识别上限）

- Lee-Ready 正确分类率 **76.4–81.05%**（Nasdaq 专有数据对拍）；tick rule 77.66%（Chakrabarty-Pascual 等）。
- 社区/工程实践报告 Lee-Ready 72–85%。
- **Bulk Volume Classification (BVC, Easley-López de Prado-O'Hara 2012)**：用 bar 收益的正态 CDF 分配买卖量，
  只需 OHLCV/amount，**适配分钟 bar**。虽有偏但可用于估计**方向性冲击的斜率**，且无需逐笔。

→ 结论：c 的估计误差下限被方向分类误差锁定，**只能给区间**；BVC 是本数据条件下最优路径。

### 3.5 α 衰减与 impact 衰减

- arXiv:2502.04284, *On the Effect of Alpha Decay and Transaction Costs on the Multi-Period Optimal
  Trading Strategy*：信号现值与历史值均有预测力，多期 MDP 表述。
- Bachelier 会议论文, *Trading with Concave Price Impact and Impact Decay*：冲击按时间尺度 τ 衰减，
  alpha 按 `−α_t'` 衰减，最优策略下冲击与 alpha 呈线性关系——可用于**联合估计执行节奏**。
- Micro Alphas 术语页 / 社区实践：**IC(h) = IC₀·e^(−λh)**，半衰期 `T½ = ln2/λ`；亦可用幂律 `(1+h)^(−β)`；
  强调必须给**置信带**而非点值。
- Blockcircle（EDGAR alpha half-life）：报告半衰期时必须标注**筛选口径**，否则跨样本不可比。

### 3.6 滚动窗口 OOS

- **Inoue, Jin & Rossi (2017, J. Econometrics 196:55-67)**：参数为时间的平滑函数时，用最小化条件 MSFE
  选择滚动窗长；最优窗长量级 `L ∝ T^(2/3)`。
- **Rossi & Inoue, *Out-of-Sample Forecast Tests Robust to the Choice of Window Size***：检验统计量对窗长
  选择做稳健化，避免"挑窗长"数据窥探。
- Hong, Sun & Wang (2017)：时变预测回归中最优滚动窗长的选择与实现。
- 结论：本批滚动窗**不预设单一窗长**，用 {24, 36, 48, 60} 月多窗长一致性 + 窗长稳健检验。

### 3.7 交易成本与容量（方法参照）

- **Frazzini, Israel & Moskowitz, *Trading Costs of Asset Pricing Anomalies***：用真实成交数据估成本，
  平均市场冲击约 10 bps，结论是学术假设成本高一个数量级、容量低一个数量级——**方向性参照，不可直接套用到 A 股**。
- **Novy-Marx & Velikov (2016), *A Taxonomy of Anomalies and Their Trading Costs***（NBER w20721）：
  用 turnover + ADV + 冲击模型估净收益，成本主要取决于换手。容量量级：size 170B / value 50B / momentum 5B（美股）。
- 对本批的启示：容量结论必须**同时报告换手率敏感性**，并明确 c 的不确定性如何放大 AUM 区间（平方关系）。

### 3.8 A 股制度约束（执行模型必须建模）

- 涨跌停：主板 **10%**，创业板/科创板 **20%**（SSE/SZSE 官方规则，2026 年修订版）；ST 5%（按现行规则）。
- **T+1** 交收 → 当日买入不可卖出，拆单买入后可卖出的最早时点为 T+1。
- 价格笼子 / 市价单只能吃五档（SSE 说明）→ 大单必须拆分为限价单。
- 含义：多日执行模型必须按「每日可成交上限 = min(ADV×参与率上限, 涨跌停可成交量)」约束，并在跌停板
  不可卖出时顺延（不可顺延时按未成交处理，不得假设成交）。

---

## §4 候选方法设计

### 4.1 Q1 — c 系数校准：三条证据链

**路径 A：分钟数据反解（主，覆盖 2020-01…2023-03）**

1. **BVC 分解**：对每只股票、每日、每分钟，
   `V_buy,t = V_t · Φ(r_t / σ_t)`，`V_sell,t = V_t − V_buy,t`，`signed_vol_t = V_buy,t − V_sell,t`；
   `r_t` 为分钟内收益，`σ_t` 为同日分钟收益 RMS（或过去 20 日同时段 RMS）。
2. **日内冲击斜率**：`r_t = λ_i,m · signed_vol_t / ADV_i,m + ε`（分钟级 OLS，股票×月），
   或 HFV 分解（`r_t = λ·OFI_t + ε`，OFI 用 tick-rule 近似），得到 `λ_i,m`。
3. **幂律检验与映射（复审 R-F10 修正：口径自洽）**：对每个参与率档 `p ∈ {0.1%, 0.5%, 1%, 2%, 5%}`——
   ① 幂律直接在分钟级回归：`log|r_t| = a + b·log|signed_t/ADV_i,m| + d·log σ_d + ε`
   （双向聚类稳健标准误），**b_hat 用于检验 sqrt 律是否成立**（b 的 95% CI 是否覆盖 0.5），
   档位冲击 `impact(p) = exp(a)·p^b·σ_d^d`；
   ② 线性响应系数：`r_t = λ_i,m · (signed_amount_t / ADV_amount_i,m) + ε_t`（自变量为无量纲参与率），
   映射 `impact_bps(i,m,p) = λ_i,m · p · 1e4`；
   ③ **口径纪律**：回归自变量与映射式必须同口径，禁止 `λ·p·ADV/Price` 与 `r = λ·signed/ADV`
   混用（前者隐含股数口径的 λ，量纲不自洽，详见 §12.5 复审附注）。
4. **对照组调整**：为剔除市场/行业漂移，用同行业×同规模分位的等权组合日内 VWAP 偏离作为基准扣除。

**路径 B：OHLC 低频代理（覆盖全样本 2020-01…2026-01）**

1. 计算日频 **CS（two-day corrected）** 与 **AR/CHL（two-day corrected）** 有效价差，报告**零截断比例**；
2. 计算 Amihud 非流动性；
3. 在 2020-01…2023-03 的重叠窗口内，把路径 A 的 `impact` 对 `{价差, Amihud, σ_d}` 回归建立映射；
4. 用映射外推 2023-04…2026-01 的 c 区间，并标注为**代理推断（非直接观测）**。

**路径 C：文献先验约束（贝叶斯式收缩）**

以 `c ∈ [0.1, 1.0]`（Almgren 型 Y 的量级）为弱先验，`1% ADV → 8–18 bps`（JFQA 美股锚点）做合理性检验；
若 A/B 路径估计显著越界，优先怀疑估计量偏差而非推翻先验。

**三角验证规则**：只有当 A、B 的**方向与量级**一致时才把 c 写进结论；否则只报三条路径的分歧区间。

### 4.2 Q2 — 永久/临时冲击分离

- 用 T+1 / T+3 价格反转：`reversal_bps = −s·(P_{t+1} − P_t)/P_t`，若显著为正，说明临时冲击占比；
  `permanent ≈ impact − reversal`。
- 分钟数据可进一步用**日内 VWAP 相对收盘的偏离**判断冲击是否在收盘前衰减。
- 输出：`temporary_share` 区间；容量计算中按 `impact = permanent + temporary·(执行天数内衰减系数)` 处理。

### 4.3 Q3 — α 衰减曲线

- 对每个调仓月 t、延迟 `d ∈ {0,1,2,3,5,10}` 交易日：
  组合权重 `w_t`（月频因子），持有期收益 `R_d = mean_{i} w_{t,i} · r_{i, [t+d, t+d+21)}`，超额 `R_d − benchmark`；
- 拟合两条曲线并报告拟合优度：
  - 指数：`R_d/R_0 = exp(−λd)`，`T½ = ln2/λ`；
  - 幂律：`R_d/R_0 = (1+d)^(−β)`；
- **稳健性**：对每个 regime 分层拟合，报告 λ 的 block bootstrap CI 与滚动 12 月 λ_t 的漂移；
- 执行耦合：`净收益(d) = R_d − 冲击成本(执行天数, 参与率)`，给出**最优执行天数 d\***（2–3 日为候选上限）。

### 4.4 Q4 — Regime 容量压力测试

分层维度（各自独立，不做交叉以避免小样本）：

| 维度 | 定义 | 输出 |
|------|------|------|
| 成交额 regime | 全市场日成交额 5 分位（当月均值） | 各 regime 的 p95 参与率 → 容量 |
| 波动 regime | 截面 σ_d 5 分位 | 同上 |
| 涨跌停/停牌 | 组合内触及涨跌停比例分位 | 可执行比例与顺延天数 |
| 极端月 | 2024-02（流动性冲击月）及全样本最差 5 月 | 容量下界 |

**报告口径**：容量 = `min(各 regime 容量)`（压力值）+ 中位（基准值），并注明 c 取值。

### 4.5 Q5 — 移动窗口参数外推

- 窗长 `L ∈ {24, 36, 48, 60}` 月，滚动：用第 `[t−L, t)` 月估计 `c`、`λ`（α 衰减）、`σ` 口径，
  在第 `t` 月计算容量与冲击，形成**参数外推序列**；
- 输出：参数序列、滚动均值 ± bootstrap CI、漂移检验（前后半段差异）；
- 与 CPCV 分工：CPCV 检验**策略**样本外，滚动窗口检验**参数**样本外；两者结论分别报告，不混用。

### 4.6 Q6 — 数据新鲜度守卫

- 复用 `FieldSpec.max_lag` + `_freshness_check`（v3.6.0 已具备），在研究脚本入口默认调用
  `check_data_contract(required=True)`，失败即中止；
- 文档层面核销 PROJECT_STATUS P2 表条目，标注「v3.6.0 已实现，v3.8.0 默认化」。

---

## §5 稳健性与鲁棒性协议（R1–R8，验收必查）

| ID | 协议 | 通过标准 |
|----|------|---------|
| R1 | 多估计量交叉（BVC-lambda / Amihud / CS / AR / 直接反解） | 至少 3 个估计量的 c 区间重叠；方向一致 |
| R2 | 聚合层级敏感性（分钟→日→周） | 三种层级的 b_hat 方向一致；若不一致，结论降级为「不可识别」 |
| R3 | Block bootstrap CI（复用 `effect_size.stationary_bootstrap_indices`） | 所有 c / λ / 容量均给 95% CI，不给点估计 |
| R4 | 参数敏感性（参与率 5 档、σ 口径 日/EWMA/月、窗长 4 档） | 结论在敏感性网格内不变号 |
| R5 | 时间稳定性（滚动 12 月估计） | 漂移幅度与 CI 同时报告，禁止只报终值 |
| R6 | 跨数据源一致性（分钟 vs OHLC 代理 vs 日频） | 重叠期（2020-01…2023-03）三条路径的 c 差异 < 2 倍 |
| R7 | 最差情形优先 | 容量以 min(regime) 为报告主值，中位为参考 |
| R8 | 结论分级标注 | 每个数字标 `[直接观测]` / `[代理推断]` / `[区间]` / `[不可识别]` |

**禁止事项**：不得用单一 seed/单一路径的读数下结论；不得把 c 的点估计代入容量后只报单一 AUM；
不得在无分钟覆盖的月份声称 c 是"观测值"。

---

## §6 与现有实现的对齐

| 现有资产 | 复用方式 |
|---------|---------|
| [verify_capacity_impact.py](../../scripts/verify_capacity_impact.py) | 保留默认口径（c 网格、p95、tier、S1/S2）；新增 `--calibrate` 分支输出校准区间，**默认路径零变更**（分支名复审 R-F6 统一，取 §17.7 的 `--calibrate`） |
| `backtest/effect_size.py` | 复用 `stationary_bootstrap_indices` / `newey_west_se` 做 CI 与 HAC |
| `backtest/overfitting.py` | 复用 `_require_positive_std`（含 v3.7.0 H1 的 ptp 守卫） |
| `backtest/cross_validation.py` | 复用 `PurgedKFold` / `CPCV` 做策略侧 OOS，避免与参数滚动窗口混淆 |
| `backtest/data_contract.py` | Q6 前置守卫；**不新增字段语义** |
| `backtest/multiple_testing_ledger.py` | 若本批产生多规格试验（多参与率/多窗长），登记避免选择性报告 |

**新增内容（预计）**：分钟数据加载与聚合模块（按股票×月流式）、BVC/OFI 估计、α 衰减拟合、regime 压力表、
滚动窗口参数外推。**不 import `backtest/__init__.py`**，不改变既有公共 API。

---

## §7 风险与不可识别边界

| # | 风险 | 处置 |
|---|------|------|
| 1 | 无逐笔方向 → BVC 有偏 | 方向分类精度上限 76–81% 作为误差下界，结论标 `[区间]` |
| 2 | 2023-04 后无分钟数据 | c 的时间外推标 `[代理推断]`；不外推到报告主结论 |
| 3 | c 与 σ 共线（同时放大冲击） | 回归中含 `log σ`，并报告 c 在固定 σ 分位下的条件值 |
| 4 | 容量对 c 平方敏感 | 容量给 c 下/中/上三档对应 AUM，主值取 c 上档（保守） |
| 5 | 分钟数据未复权 | 用 `adj_factor` 变化日识别除权日并剔除；日内收益用同日内价不受影响 |
| 6 | 涨跌停/停牌样本选择偏差 | 仅在「可交易」样本估计，并单独报告不可交易比例 |
| 7 | 极端月样本极少（1 个月） | 只作下界披露，不做统计推断 |
| 8 | 平方根律可能是聚合假象（CKS 2011） | R2 聚合层级敏感性；同时保留线性模型对照 |

---

## §8 建议实施阶段

| 阶段 | 内容 | 验收形态 |
|------|------|---------|
| E0 | 数据前置：分钟加载器（流式）+ 复权对齐 + 新鲜度守卫默认化 | 数据契约 PASS；加载 1 个月 < 60s |
| E1 | BVC + 分钟级冲击斜率 λ（2020-01…2023-03） | λ 面板覆盖率与缺失率报告 |
| E2 | c 校准三角验证（A/B/C 路径）+ R1/R2/R6 | c 区间表 + b_hat CI |
| E3 | T+1 reversal 分离永久/临时冲击 | temporary_share 区间 |
| E4 | α 衰减曲线（d=0…10）+ 最优执行天数 | 半衰期 + CI + d* |
| E5 | regime 压力表（4 维度）+ 最差容量 | min/中位容量表 |
| E6 | 滚动窗口参数外推（4 窗长）+ 漂移诊断 | 参数序列 + 4 窗长一致性 |
| E7 | 容量脚本 v2 接入（`--calibrate`）+ 文档 + 异构复审 | 默认路径 golden 零变化；审计 PASS_WITH_FIXES |

依赖：E0 → E1 → E2∥E3 → E4 → E5 → E6 → E7（E2 与 E3 可并行，共用 λ 面板）。

**测试预期**：新增用例约 40–50 例（BVC 单调性/边界、λ 回归对拍、衰减拟合对拍、regime 分桶完整性、
滚动窗无未来函数、容量区间单调性）。默认路径回归必须 1929 → 1929+（零新增失败）。

---

## §9 待裁决项

| ID | 决策点 | 选项 | 建议 |
|----|--------|------|------|
| D1 | pyarrow 依赖 | A) 新增 optional group（第三轮建议命名 `calib`）；B) 脚本内延迟 import + 明确报错；C) 改读 CSV（不存在） | 第一轮建议 **B**；第三轮 §16.1 修订为 **A（calib extra + find_spec 探测）**，以第三轮为准 |
| D2 | 是否把校准 c 写进默认容量报告 | A) 只作附列；B) 替换默认 c | **A**，默认 c 网格保留，校准值作 `[区间]` 附列 |
| D3 | 滚动窗长主值 | A) 36 月；B) 不设主值，只报 4 窗长一致性 | 第一轮建议 **B**；第三轮 §16.3 修订为 **AveW 等权平均主值 + 4 窗长并列**（Pesaran-Pick 2011；本地 39 个 OOS 点不支持数据驱动选窗），以第三轮为准 |
| D4 | α 衰减持有期 | A) 固定 21 日；B) 与信号半衰期联动 | 第一轮建议 **A**；第三轮 §16.4 修订为 **net(h) 曲线 + 平坦区，默认推荐档 h=20 交易日**（与月频调仓一致；21 日与 20 交易日系同一档位的两种计数，统一为后者），B 留待后续 |

---

## §10 参考文献与证据链接

1. Cont, Kukanov & Stoikov, *The Price Impact of Order Book Events* — arXiv:1011.6402（sqrt 律反证）
2. *The "double" square-root law: Evidence for the mechanical origin of market impact* — arXiv:2502.16246
3. *Equity Market Impact Modeling: an Empirical Analysis for Chinese Market* — arXiv:1610.08767（中国逐笔实证）
4. JFQA, *Price Impact in Closing Auctions, Opening Auctions, and Continuous Markets*
   — 1% ADV 均值 17.7bps / 中位 8.4bps
5. Corwin & Schultz (2012), *A Simple Way to Estimate Bid-Ask Spreads from Daily High and Low Prices*, JF
6. Abdi & Ranaldo (2017), *A Simple Estimation of Bid-Ask Spreads from Daily Close, High, and Low Prices*, RFS 30(12)
7. *When Do Low-Frequency Measures Really Measure Effective Spreads?* — RFS (2023), hhad028
8. *When do low-frequency measures really measure transaction costs?* — FEDS 2019-051（CS_M 零截断 38%）
9. Amihud (2002), *Illiquidity and Stock Returns*
10. Easley, López de Prado & O'Hara (2012), *Bulk Volume Classification*（BVC）
11. Chakrabarty, Pascual et al., *Evaluating Trade Classification Algorithms: BVC vs Tick Rule vs Lee-Ready*
    — 正确率 76.4 / 77.66 / 81.05%
12. arXiv:2502.04284, *On the Effect of Alpha Decay and Transaction Costs on the Multi-Period Optimal Trading Strategy*
13. Bachelier 会议论文, *Trading with Concave Price Impact and Impact Decay — Theory and Evidence*
14. Inoue, Jin & Rossi (2017), *Rolling window selection for out-of-sample forecasting with time-varying parameters*,
    J. Econometrics 196:55-67
15. Rossi & Inoue, *Out-of-Sample Forecast Tests Robust to the Choice of Window Size*
16. Hong, Sun & Wang (2017), *Selection of the Optimal Length of Rolling Window in Time-varying Predictive Regression*
17. Frazzini, Israel & Moskowitz, *Trading Costs of Asset Pricing Anomalies*
18. Novy-Marx & Velikov (2016), *A Taxonomy of Anomalies and Their Trading Costs*, NBER w20721
19. SSE 交易规则（2026 修订）§3.3.13 涨跌幅 10%；SZSE 创业板 20%；T+1 与价格笼子
20. arXiv:2505.17388, *Stochastic Price Dynamics in Response to Order Flow Imbalance: Evidence from CSI 300 Index Futures*（Lambda 定义）

---
---

# 第二轮补充调研 — 学术机制与技术细节

> 追加于 2026-11-18。目的：把第一轮的"方法可行性"推进到"可直接落代码的公式与口径"，
> 并补上第一轮遗漏的**组合级冲击（co-impact）**与**A 股制度时间线**。
> 标注约定：`[已核实-官方]` / `[已核实-论文]` / `[二手来源-待核]` / `[未核实]`。

## §11 冲击模型的三代理论：从 sqrt 到对数，再到 impact surface

### 11.1 第一代：平方根律的机制解释

- **Tóth et al. (2011), arXiv:1105.1694**：把 sqrt 律归因于「**latent liquidity**」——
  大部分日流动性是隐藏的，且在当前价附近线性消失（latent order book 理论）。由此 metaorder 必须
  被拆分才能被"流动性漏斗"吸收，并解释了两个典型事实：订单流符号的长记忆 + 小订单冲击发散。
- **arXiv:2411.13965（TSE 全市场普查）**：结论是 δ = 1/2 **严格普适**，与微观结构细节无关。
  → 与第一轮引用的 CKS (2011)「sqrt 是聚合假象」形成**正面对立**。
  **处置**：本批不裁决理论之争，只做**实证裁决**——在 A 股分钟数据上估计 b 的 CI，
  若 CI 覆盖 0.5 则用 sqrt，若覆盖 1 则用线性，若两者都不覆盖则报告"两端都不支持"并降级。

### 11.2 第二代：对数修正（对本批最重要的技术修正）

**Zarinelli, Treccani, Farmer & Lillo (2014), arXiv:1412.2152, *Beyond the square root***：

| 结论 | 对本批的含义 |
|------|-------------|
| sqrt 公式**只在约 2 个数量级的订单规模内**拟合良好 | 我们的参与率档 0.1%–5%（约 1.7 个数量级）**恰好落在 sqrt 可接受区间**，但外推需谨慎 |
| **对数形式在近 5 个数量级上拟合更好** | 必须把 `impact = a + b·ln(p)` 作为**并列候选模型**，与 sqrt 同台比较 |
| 提出 **"impact surface"**：冲击是 duration × participation 的二元函数 | 多日执行模型必须用二维面（执行天数 × 每日参与率），不能只用单一 p |
| 执行中价格轨迹偏离 VWAP → 存在非 VWAP 执行 | 我们只能用 VWAP 假设，属**方法上界**，需披露 |

**落地**：c 校准的候选模型从 2 个扩到 4 个——
`sqrt`、`linear`、`log`、`power(b 自由)`，用 AIC/BIC + 样本外拟合（跨股票×月）选型，
并强制报告四个模型的 c 区间。**不允许只报 sqrt。**

### 11.3 第三代：LOB 韧性模型（决定多日执行的衰减结构）

- **Obizhaeva & Wang (2013), J. Financial Markets 16(1):1-32**：限价订单簿的 depth + resilience 模型，
  冲击按**指数**衰减，衰减速度由 resilience 参数决定。**最优执行策略不取决于静态深度/价差，
  而取决于韧性**。
- **Gatheral, Schied & Slynko (2012) / arXiv:1204.2716**：transient impact 的零价差版本，
  冲击核为指数衰减；带 drift 信号时的最优策略有显式解。
- **arXiv:2002.09549, *Optimal Signal-Adaptive Trading with Temporary and Transient Price Impact***：
  同时含 temporary + transient 冲击，且信号自适应——与我们的「α 衰减 + 多日执行」结构最接近。

**落地**：多日执行模型的冲击衰减用**指数核** `exp(−t/τ)`，τ 即 resilience 时间尺度；
τ 由分钟数据的**日内冲击衰减**估计（§12.5），而不是外生假设。若 τ 估计不显著，
退化为永久冲击 + 无衰减（保守）。

### 11.4 可直接参数化的工业模型

| 模型 | 结构 | 参数锚点 |
|------|------|---------|
| Almgren et al. (2005) | 永久 `η·σ·(X/V)`；临时 `γ·σ·(X/V)^(3/5)` | γ、η 为"universal coefficients"，随市场变化，需本地校准 `[二手来源-待核]` |
| Kissell-Malamut **I-Star** | `I* = a1·(X/ADV)^a2·σ^a3`；`MI_temp = b1·I*·POV^a4`，`MI_perm = (1−b1)·I*·…` | 官方实现边界 `100≤a1≤1000, 0.1≤a2,a3,a4≤1, 0.7≤b1≤1`（blotter `iStarPostTrade`）；a2≈0.5、a3≈0.75 为**美股大盘股**经验值 `[二手来源-待核]` |
| 现有 `verify_capacity_impact.py` | `c·σ_d·√p` 与 `k·p` | c∈{0.1,0.5,1.0}，k=0.025 |

**I-Star 的价值**：它把「临时 vs 永久」显式拆成 `b1` 与 `1−b1`，正好对应 §4.2 要估计的
`temporary_share`。**建议**：用 I-Star 的结构做参数化外壳，用 A 股分钟数据估计 `b1` 与 `a2`，
而不是照搬美股参数。

---

## §12 精确实现公式与口径（可直接落代码）

### 12.1 Corwin-Schultz (2012) 高低价价差估计

\[
S = \frac{2\left(e^{\alpha}-1\right)}{1+e^{\alpha}},\quad
\alpha = \frac{\sqrt{2\beta}-\sqrt{\beta}}{3-2\sqrt{2}}-\sqrt{\frac{\gamma}{3-2\sqrt{2}}}
\]

其中（`H`/`L` 为日最高/最低）：
- `β = E[(ln(H_t/L_t))² + (ln(H_{t+1}/L_{t+1}))²]`
- `γ = [ln(H_{t,t+1}/L_{t,t+1})]²`，`H_{t,t+1}=max(H_t,H_{t+1})`，`L_{t,t+1}=min(L_t,L_{t+1})`

**必须处理的两个实现细节**（RFS 2023 hhad028 与 Abdi-Ranaldo 明确）：
1. **零区间日**：若某日 `H=L`（分钟数据下对应一字板/全天零成交），按 CS 原文把前一日的高/低价
   "平移"过来使用，而不是丢弃——否则会系统性低估小价差股票的价差。
2. **two-day corrected**：Abdi-Ranaldo 与 RFS 2023 均建议用 **两日修正版**（估计误差更小）。
   **禁止**用月度修正版替代。

### 12.2 Abdi-Ranaldo (2017) CHL 估计（步骤 4 幻觉消除修正）

**乘积型**（v1.0 误写为单对平方差，已修正）：`c_t = ln(P_close_t)`（对数收盘价），
`η_t = (ln H_t + ln L_t)/2`（日内高低中点），
`S² = 4·E[(c_t − η_t)(c_t − η_{t+1})]`，`S = √(max(S², 0))`（相邻日配对、负值截断为 0）。
`[已核实-论文（RFS 30(12), hhx084）]`；hhad028（RFS 2023）实测：**广泛使用的不一致实现**
（含单对平方差类变体）存在随波动率变化的系统性偏差；实现时须对照 AR 原文附录与
hhad028 的「一致实现」版本核验 `[待核→E2 落实]`。

### 12.3 Amihud (2002) 非流动性

`ILLIQ_{i,t} = |r_{i,t}| / Amount_{i,t}`（成交额单位为亿元时需统一量纲）。
**用途限定**：只做横截面排序与回归控制变量，**不做绝对冲击水平**（Goyenko-Holden-Trzcinka 2009：
Amihud 对低频成本的绝对度量能力弱，但排序能力稳定）。

### 12.4 Bulk Volume Classification (BVC)

`V^{buy}_t = V_t · Φ(r_t / σ_t)`，`V^{sell}_t = V_t − V^{buy}_t`，`signed_t = V^{buy}_t − V^{sell}_t`。

**σ_t 口径（关键，决定是否前视）**：
- 禁止用"当日全样本分钟收益 RMS"（含未来信息）；
- 用**过去 N 根 bar**（N∈{20,50}，或 volume clock 的等量 bar）的收益标准差，`N` 在设计中固定并做敏感性；
- 每个 bar 的 `Φ(·)` 自带单调性：`r_t>0` → 买方占比 >0.5，符合直觉，可作为单元测试断言。

**已知偏差**：BVC 假设收益服从正态，厚尾/一字板时退化（`r_t=0` → 各 50%，方向信息为零）。
→ 一字板日必须从冲击估计样本剔除，并单独统计占比（与 §7 风险 #6 一致）。

### 12.5 冲击斜率与衰减的估计方程

**瞬时冲击斜率（股票 i、月 m）**：

`r_t = λ_{i,m} · signed_t / ADV_{i,m} + ε_t`，`t` 为同月内分钟 bar；
HAC 标准误（`newey_west_se`，lag 用 `_resolve_lag` 默认规则）。

**冲击衰减（resilience τ）**：对每次"冲击事件"（`|signed|` 超过分位阈值），
回归 `impact(t+Δ) / impact(t) = exp(−Δ/τ)`，`Δ ∈ {5, 15, 30, 60, 120}` 分钟；
τ 的 bootstrap CI 若不显著（CI 覆盖 0 或 τ 发散）→ 按永久冲击处理。

**映射到参与率档（复审 R-F10 修正：回归式与映射式必须同口径）**：
`impact_bps(i,m,p) = λ_{i,m} · p · 1e4`
（回归自变量 `signed/ADV` 已是无量纲参与率，λ 的单位是「收益率 / 单位参与率」，
冲击对 p 是线性映射，**不应再乘 `ADV/Price`**。若改用股数口径——`r_t = λ'_i,m · signed_shares_t`
（λ' 单位：收益率/股）——映射则为 `λ' · p · ADV_shares / Price`；两种口径二选一，禁止混用。
本设计统一取**金额参与率口径**，与 `amount` 字段及容量模型的 ADV（成交额）对齐）。

**幂律检验独立于 λ**（sqrt 律 b≈0.5 不能从线性 λ 外推得出）：须直接在分钟级回归
`log|r_t| = a + b·log|signed_t/ADV| + d·log σ_d + ε` 上估计（见 §4.1 路径 A-①）；
否则 `impact = λ·p` 下 b≡1，检验失去意义。

### 12.6 块 bootstrap 的块长（修正第一轮的默认值）

第一轮 R3 沿用 `block_size=ceil(sqrt(T))`，**这是工程默认而非统计最优**。补正：
- **Politis & White (2004)** 自动块长：一阶近似
  `b_opt ≈ [(2ρ̂₁²)/(1−ρ̂₁²)²]^(1/3) · N^(1/3)`；
- **Patton, Politis & White (2009) 修正**：替换为重叠块常数 `D=(4/3)·spc`，并做矩估计的偏差修正；
- 实现口径：若数据 `ρ̂₁` 很小（近 iid），`b_opt→1`，退化为 iid bootstrap，与 v3.7.0 的
  `resampling='iid'` 对齐；否则用自动块长，并同时报告 `b ∈ {sqrt(T), Politis-White}` 两种结果的一致性。

**落地**：`effect_size.stationary_bootstrap_indices` 已有 `block_size` 参数，新增一个
`auto_block_size(x)` 辅助函数（纯 numpy，不新增依赖），在 c/λ/容量的 CI 中默认使用。

---

## §13 组合级冲击（co-impact）——第一轮的遗漏项

### 13.1 核心发现

**Bucci, Benzaquen, Lillo & Bouchaud (2020), Quantitative Finance 20(2):193-205,
*Co-impact: crowding effects in institutional trading activity*（arXiv:1804.09565）**：

1. 市场**主要反应"进行中 metaorder 的净订单流"**，并不区分是哪一个机构；
2. 多个 metaorder 同时交易时，**联合冲击（co-impact）取决于 metaorder 的数量与其相互符号相关性**；
3. 冲击曲线随交易量比例 φ 呈**三段**：大 φ → **sqrt**；中 φ → **线性**；φ→0 → **有限截距 I0**；
4. 直接推论：**策略容量是所有市场参与者共享的**——拥挤交易会提高成本、降低容量。

### 13.2 对本批的强制修正

第一轮的容量模型是「逐股票冲击求和」，隐含「我们的订单互不影响、也不与他人共振」的假设。
co-impact 说明该假设在组合层面会**低估**冲击。处置：

| 措施 | 具体做法 |
|------|---------|
| 显式披露 | 报告新增"co-impact 未观测"限制项，禁止声称容量是"独占容量" |
| 敏感性放大 | 引入 `κ ∈ {1.0, 1.5, 2.0}` 冲击放大因子（对应"轻度/中度/拥挤"），容量按 κ 重算 |
| 组合内部对冲 | 若组合同时有买有卖，按**净订单流**而非总成交额计算，降低重复计冲击 |
| 容量口径 | 主值取 `κ=1.5` 的保守档，并在报告中同时给 κ=1.0 作乐观上界 |

**注意**：`κ` 是披露性情景参数，**不是**从数据估计出来的量——必须在 `[区间]`/`[情景]` 分级里
标为**情景假设**，不得与 c 的实证区间混为一谈。

### 13.3 三段 regime 与我们的参与率区间

我们的参与率档 0.1%–5% 横跨「φ→0（有限截距）」到「中 φ（线性）」。
这解释了为什么 sqrt 与 linear 两个模型在我们的网格内都可能"拟合得不错"（§11.2 的 Zarinelli 结论一致）。
→ **模型选择必须按参与率档分别报告**，不允许用全区间单一模型外推到 20% 参与率。

---

## §14 A 股制度时间线（用于 regime 分层与可交易性建模）

| 制度 | 生效 | 内容 | 来源 |
|------|------|------|------|
| 主板涨跌幅 10% | 长期 | `涨跌幅限制价 = 前收盘 × (1±10%)` | SSE 交易规则 §3.3.13 `[已核实-官方]` |
| 科创板 | **2019-07-22** 开市 | 上市前 5 日无涨跌幅，之后 **20%** | SSE 科创板答记者问 `[已核实-官方]` |
| 创业板注册制 | **2020-08-24** | 存量股票 + 相关基金 10%→**20%**；新股前 5 日无涨跌幅 | SZSE 2020-08-21 发布会 `[已核实-官方]` |
| 北交所 | **2021-11-15** 开市 | 涨跌幅 **30%**；新股上市首日无限制 | BSE 交易规则(试行) §3.3.11 `[已核实-官方]` |
| 上交所收盘集合竞价 | **2018-08-20** 起 | 收盘价形成机制变更 | 学术论文（SSE 自然实验）`[已核实-论文]` |
| T+1 交收 | 长期 | 当日买入不可卖出 | 交易所规则 `[已核实-官方]` |
| ST 股 5% | 现行 | 需在设计中二次核验具体规则文本 | `[未核实]` |

### 14.1 直接后果（必须写进实现）

1. **regime 分层不能跨制度断点合并**：创业板 2020-08-24 前后的「20% 涨跌停」样本不可混用，
   否则涨跌停比例、可成交量口径不一致。容量样本 2020-01→2026-01 **恰好横跨该断点**。
2. **一字板识别**：`high == low`（分钟数据下同价 bar 占比）→ 该日不可交易，必须从冲击估计与
   容量可执行样本中剔除，并单独报告占比。
3. **新股前 5 日无涨跌幅**：极端收益会污染 σ 与冲击回归 → 上市不足 60 日的股票剔除
   （与现有 `tradable` 过滤口径对齐，需在设计阶段确认）。
4. **收盘集合竞价**：15:00 bar 含集合竞价，执行价口径需明确「是否允许收盘竞价成交」；
   建议默认不允许（保守），并做敏感性对照。

### 14.2 日内 U 型流动性

- 上交所日内交易与流动性呈 **U 型**（开盘/收盘高，盘中低），价差呈**倒 U 型**，
  10:00–10:30 与 14:00–14:30 为价差谷底 `[已核实-论文]`。
- 含义：多日执行模型的**日内时点选择**应有依据——VWAP/TWAP 在 U 型下并非最优；
  本批先固定「按当日 VWAP 成交」作为基准，把时点优化列为后续项（避免范围膨胀）。

---

## §15 对第一轮方案的技术修正清单（设计阶段必须落实）

| # | 第一轮表述 | 第二轮修正 | 原因 |
|---|-----------|-----------|------|
| M1 | c 校准只比较 sqrt 与 linear | 扩为 **4 模型**（sqrt/linear/log/power），按参与率档分别选型 | Zarinelli 2014：sqrt 仅 2 个数量级内拟合，对数近 5 个数量级 |
| M2 | BVC 的 σ 用"同日分钟收益 RMS" | 改为**过去 N 根 bar**（N∈{20,50}）的滚动 σ，N 做敏感性 | 避免前视偏差 |
| M3 | 块 bootstrap 用 `ceil(sqrt(T))` | 改为 **Politis-White (2004) + Patton-Politis-White (2009) 修正**自动块长，并与 sqrt(T) 对照 | 工程默认非统计最优；v3.7.0 的 P5-5d 教训正是块长效应被噪声淹没 |
| M4 | 容量 = 逐股票冲击求和 | 新增 **co-impact 情景 κ∈{1,1.5,2}**，主值取 κ=1.5，并按净订单流计算 | Bucci et al. 2020：容量是共享的 |
| M5 | CS 估计未提零区间处理 | 明确**零区间日前值平移** + **two-day corrected** + 报告**零截断比例** | RFS 2023 / FEDS 2019-051：否则系统性低估 |
| M6 | regime 分层只按成交额/波动 | 增加**制度断点分层**（创业板 2020-08-24、科创板 2019-07-22、北交所 2021-11-15） | 涨跌幅规则变更导致口径不可比 |
| M7 | 冲击衰减未建模 | 用**指数核 exp(−Δ/τ)** 估计 resilience τ；不显著则退化为永久冲击 | Obizhaeva-Wang (2013)：最优执行取决于 resilience |
| M8 | 逐股票 λ 直接求和进容量 | λ 估计必须**含 HAC 标准误**并报告显著性比例（多少股票×月的 λ 显著） | 不显著的 λ 不应进入容量 |
| M9 | 一字板未显式处理 | 单独识别（`high==low`）并剔除，报告占比 | BVC 在 r=0 时退化 |
| M10 | 容量主值口径 | 明确「主值 = min(regime) + κ=1.5 + c 上档」三元保守组合，并同时给乐观上界 | R7 最差情形优先 |

### 15.1 修正后的模型选型判据（写进设计文档）

```
对每个参与率档 p ∈ {0.1%, 0.5%, 1%, 2%, 5%}：
  候选模型 M ∈ {sqrt: a·p^0.5, linear: a·p, log: a + b·ln p, power: a·p^b}
  以「股票×月」为聚类单元做 5 折交叉验证（按时间切分，禁止随机切）
  选型：CV-RMSE 最小者为主模型；若次优模型与最优的 CV-RMSE 差距 < 10%，并列报告
  区间：取并列模型预测的 [min, max]
```

### 15.2 明确的"不做"清单（防止范围膨胀）

- 不做日内执行时点优化（U 型只作背景披露）；
- 不做 co-impact 的实证估计（无其他机构订单数据，只做情景）；
- 不做分钟数据复权重建（只用日内相对量，除权日剔除）；
- 不把 c 的校准结果替换默认容量口径（§9-D2 与 §16.2 的一致建议，**待最终裁决**，非既成裁决）。

### 15.3 第二轮新增参考文献

21. Tóth et al. (2011), *Anomalous price impact and the critical nature of liquidity in financial markets*
    — arXiv:1105.1694
22. *Does the square-root price impact law belong to the strict universal scalings? A complete survey of TSE*
    — arXiv:2411.13965
23. Zarinelli, Treccani, Farmer & Lillo (2014), *Beyond the square root: Evidence for logarithmic dependence
    of market impact on size and participation rate* — arXiv:1412.2152
24. Obizhaeva & Wang (2013), *Optimal trading strategy and supply/demand dynamics*, J. Financial Markets 16(1):1-32
25. Gatheral, Schied & Slynko, *Drift dependence of optimal trade execution under transient price impact*
    — arXiv:1204.2716
26. *Optimal Signal-Adaptive Trading with Temporary and Transient Price Impact* — arXiv:2002.09549
27. Bucci, Benzaquen, Lillo & Bouchaud (2020), *Co-impact: crowding effects in institutional trading activity*,
    Quantitative Finance 20(2):193-205 — arXiv:1804.09565
28. Politis & White (2004), *Automatic Block-Length Selection for the Dependent Bootstrap*；
    Patton, Politis & White (2009) 修正
29. Kissell & Malamut, *I-Star* 模型（blotter `iStarPostTrade` 参数边界）
30. 北交所《交易规则(试行)》§3.3.11（30% 涨跌幅）
31. *Call auction, continuous trading and closing price formation*（SSE 日内 U 型与收盘集合竞价）

---

## §16 D1-D4 的裁决建议与外部锚点（第三轮）

> 本轮回答「凭什么这么裁」；其中 **D1/D3/D4 的建议在第三轮被修订**（取代 §9 的第一轮建议，
> 修订已在 §9 各行标注），D2 建议不变。每条给出：外部锚点 → 本地证据 → 建议 → 反方风险。
> 若最终裁决与建议不同，§16.5 给出了影响面，设计文档按裁决结果改，不按本节。

### 16.1 D1：pyarrow 依赖方式 → **可选 extra + 能力探测**（强锚点）

**外部锚点**

- pandas 官方安装文档把 feather/parquet 读写列为 **extra（`parquet`, `feather`）**，核心安装在无 pyarrow 时仍可用 —— 主流库对「格式专用依赖」的默认做法是**不强制**。
- Python Packaging User Guide 明确 `[project.optional-dependencies]` 即 packaging extras，用于「只服务于某个特性的依赖」。

**本地证据**

- [pyproject.toml](../../pyproject.toml) L41-L56 已有同一形状的 5 个 extras（`semantic` / `backtest` / `garch` / `optimizer` / `dev`）与 `all` 汇总。
  新增 `calib = ["pyarrow>=14.0.0"]` 属于**沿用既有惯例**，不是引入新机制。
- 仓库已有能力探测的先例：[data_contract.py](../../backtest/data_contract.py) 的 `missing_semantics` 三档（warn / known_gap / block）就是「能力缺失时降级而非崩溃」的同类设计。

**建议**

1. 不放进核心 `dependencies`（否则违反「默认零变更」，且让无 pyarrow 环境无法安装本项目）；
2. 不在模块顶层 `import pyarrow`（否则整个 `backtest` 包在无 pyarrow 时不可用，直接破坏低耦合）；
3. 用 `importlib.util.find_spec("pyarrow")` 做**探测**，与真正 `import` 分离；探测失败抛**单一**自定义异常 `CalibrationUnavailable`，由 runner 捕获后降级；
4. 缺 pyarrow 时自动落到 §17.5 的 L1（OHLC 代理）而非报错退出。

**反方风险**：若把 pyarrow 设为必需，安装体积与 CI 时长上升，且与「默认路径逐位不变」的版本纪律冲突；若用顶层 import，则任何下游只想跑日频容量的人被强制装 600MB 依赖。

### 16.2 D2：校准出的 c 是否替换默认 0.5 → **不替换，只进压力档**（最强锚点）

**外部锚点（这是本轮最重要的发现）**

- *The cost of misspecifying price impact*（arXiv:2306.00599）结论原文：
  > "when considering confidence intervals for a price impact model's concavity, the robust solution is to deploy a more conservative estimate from the upper part of the confidence interval, i.e., use an impact model that is somewhat less concave than the point estimate."

  即：参数存在估计误差时，稳健做法是取**置信区间的保守端**（凹性更弱 → 大单冲击更大），而**不是**用点估计替换先验值。
- *On Parametric Optimal Execution and Machine Learning Surrogates*（arXiv:2204.08581）：
  「Precise calibration of price impact, resilience … is known to be extremely challenging and hence it is critical to understand sensitivity of the strategy to these parameters.」
  → 校准困难是共识，正确产出是**敏感性**而非**点替换**。
- SR 11-7：模型风险包含「模型被误用」，治理要求 documented assumptions + limitations + effective challenge。
  把一次性校准结果直接设为生产默认，正是缺少 effective challenge 的模型变更。

**本地证据**

- [PORTFOLIO_CAPACITY_IMPACT_STRESS.md](../analysis/PORTFOLIO_CAPACITY_IMPACT_STRESS.md) §2.2 已把 `c ∈ {0.1, 0.5, 1.0}` 作为敏感性网格，§8 限制表明确写「c 未用 A 股成交数据校准」；
  即现有报告口径本身就把 c 定位为**假设**，不是估计量。
- §13 的 co-impact 修正又说明容量被系统性高估 —— 在此背景下用一个校准点估计「放松」口径，方向错误。

**建议**（三档并存，禁止点替换）

| 档位 | 定义 | 用途 |
|------|------|------|
| `c_default` | 0.5，**保持不变** | 默认容量口径，与历史报告可比 |
| `c_calib_stress` | 在 c 的 CI 内，取 **p95 参与率处预测冲击最大**的取值（对应「凹性更弱」端） | 压力档，进容量下限 |
| `c_calib_point` | 点估计 | **只出现在校准报告**，不进容量主表 |

再补一条可执行判据：`c_calib_stress = argmax_{c ∈ CI} Impact(c; p95_participation)`。若该值小于 0.5，说明校准结果反而更乐观，此时**仍取 0.5**（保守优先，避免「校准把风险改小」的单向偏差）。

**反方风险**：不替换会让「校准」看起来没落地。缓解办法是把校准产出定义为**区间收窄**（原 0.1–1.0 的三点网格 → 由数据得到的连续 CI），这本身就是可交付成果，不需要改默认值。

### 16.3 D3：滚动窗主值 → **窗长平均（AveW），不设单点主值**（强锚点）

**外部锚点**

- Pesaran & Timmermann (2007, *J. Econometrics* 137(1):134-161)：最优窗长依赖**断点的时点与幅度**；二者未知时窗长不可识别，单窗估计不可靠。
- Pesaran & Pick (2011, *Journal of Business & Economic Statistics* 29(2)；复审 R-F3 修正期刊名)：在不估计断点的情况下，**对多个窗长的预测取平均（AveW）**即可改善 MSFE —— 这是「不选窗、只平均」的理论依据。
- Inoue, Jin & Rossi (2017, *J. Econometrics* 196(1):55-67)：给出最小化二次预测损失的窗长选择法并证明渐近有效性 —— 但它**需要足够的 OOS 损失样本**。

**本地证据（决定性）**

- §2.1 实测：容量样本 2020-01 → 2026-01 仅 **39/73 个月**有完整覆盖。
- 在 39 个 OOS 点上比较 4 个窗长的预测损失，检验功效极低 —— 这与 v3.7.0 复审 P5-5d 的教训同源（T=58 时 L8 vs L20 无统计功效，最终改用极端对照才得到可判读结果）。
- 结论：**本地数据不支持 IJR 式的数据驱动窗长选择**，正好落到 Pesaran-Pick 的适用区间（断点未知、样本有限 → 平均优于选择）。

**建议**

1. 主值 = `equal_weight` 平均 4 个窗长（24/36/48/60 月）的参数估计与外推结果；
2. 四档点估计**并列报告**（供读者看漂移方向），但**不指定主窗**；
3. IJR 自动窗长仅作 `--diagnose-window` 诊断项，**不进主表、不进容量主值**；
4. 报告必须附「窗长间离散度」：若 4 档外推的容量差异 > 30%，标注「参数漂移不可忽略」，容量按最差窗报。

**反方风险**：平均会平滑掉真实的 regime 切换。缓解：同时报「按 §14 制度断点分段的窗长估计」，若断点后估计显著不同，则该 segment 单独出数（分段平均，而非全局平均）。

### 16.4 D4：α 衰减持有期 → **不设单点主值，改报 net(h) 曲线 + 平坦区**（强锚点）

**外部锚点**

- Gârleanu & Pedersen (2013, *JF* 68(6):2309-2340)：最优持仓 = 现有持仓、无成本最优持仓、以及「aim portfolio」的线性组合；**信号均值回复越慢（alpha 衰减越慢），权重越高**。持有期是**内生**结果，不是外生参数。
- Falck, Rej & Thesmar (2022, *Quantitative Finance*, arXiv:2105.01380)：
  ① 持有期越长 → 交易越便宜 → 容量越高；② 因此慢策略吸引更多套利资本，**发表后衰减更快**；③ 每十年适用 haircut 约减半（与 McLean-Pontiff 2016 量级一致）。
  → 持有期与衰减互为因果，单点持有期会把反馈回路截断。
- Novy-Marx & Velikov (2016, NBER w20721 / *RFS*)：按换手分低/中/高三组，成本对高换手策略的侵蚀最严重；
  其后 *Zeroing In on the Expected Returns of Anomalies*（RFS 2023）把「降低再平衡频率（3/6/12 月）」列为标准净收益改进手段。
  → 持有期必须与成本**联合**评估，只看 IC 衰减会系统性选短。

**本地证据**

- 容量模型是**月频**（月末形成、月频调仓），α 衰减可用**日频**估计 —— 两者粒度不匹配，不能对任意 h 都给净收益。

**建议**（把「选持有期」改成「报两条曲线」）

```
alpha_retention(h)  = corr / IC 自相关拟合的几何衰减 ρ^h，h 以交易日计（1/5/10/20/60）
cost(h)             = 由容量模型给出的月频执行成本，仅 h ≈ 20 交易日有对应口径
net(h)              = AUM·α·retention(h) − cost(h)      # 仅 h ∈ {5,10,20} 可算净额
```

1. `h ∈ {1,60}` 只报 `retention`，**不报净额**（无对应成本口径，避免伪精确）；
2. `h ∈ {5,10,20}` 报净额，主值取 `argmax net(h)`，但**必须同时给平坦区**：邻域内与最优差 < 1 个 bootstrap 标准差的 h 全部列出；
3. ρ 不显著异于 1 时，**退化为静态持有**，不做衰减修正（「不显著就不建模」，与 §15.2 不做清单一致）；
4. 与 GP 的衔接写在设计文档里：GP 的部分调整系数 ≈ `(1+a)^{1/2}` 形式，`a` 由 ρ 与成本共同决定 —— 我们暂不实现 GP 最优解，只把 ρ 作为其输入留接口（`DecayModel` 端口）。

**反方风险**：不设主值会让下游「不知道怎么用」。缓解：给出**默认推荐档位**（h=20 交易日，与月频调仓一致）+ 明确「这不是最优持有期，只是与现行口径对齐」。

### 16.5 裁决影响面（供裁决时对照）

| 项 | 建议 | 若裁决相反，受影响文件 | 版本风险 |
|----|------|----------------------|---------|
| D1 | `calib` extra + `find_spec` 探测 | `pyproject.toml`、`calibration/loaders.py`、CI 安装步骤 | 低（仅安装面） |
| D2 | 三档并存，默认 0.5 不变 | `verify_capacity_impact.py` 输出字段、容量报告表头 | **高**（改默认 → 历史报告不可比） |
| D3 | AveW 主值 + 四档并列 | `calibration/rolling.py`、容量报告 §6 分段表 | 中（改变外推数值，但方法可追溯） |
| D4 | retention/cost 双曲线 + 平坦区 | `backtest/execution/core/decay.py`、容量报告新增一节 | 低（新增内容，不改旧口径） |

一句话：**D2 是唯一会改变历史可比性的裁决，建议维持不替换**；其余三项都只是新增口径。

---

## §17 架构契约：高内聚 / 可插拔 / 低耦合（设计阶段必须遵守）

> 本节不是风格偏好，而是**可检查的约束**。每条都给出锚点与验收方式，设计文档直接引用编号 S1-S7。

### 17.1 分层：Functional Core + Imperative Shell（S1）

| 层 | 内容 | 允许依赖 |
|----|------|---------|
| **Core（纯函数）** | 冲击模型预测、价差估计、成交量分类、衰减核 | `numpy` 仅此一个第三方；**禁止** `os/pathlib/open/pyarrow/duckdb/logging` |
| **Shell（有 IO）** | feather/pkl 读取、代理链选择、结果落盘、日志 | 可依赖 Core、pyarrow（可选）、duckdb |
| **Entry（脚本）** | `scripts/verify_capacity_impact.py` 新增 `--calibrate` | 只依赖 Shell |

锚点：Functional Core / Imperative Shell —— 核心无需 mock 即可直测，IO 缺陷被限制在薄壳内。
这与仓库现状一致：`backtest/` 的纯计算模块（`overfitting.py` / `effect_size.py`）本身不碰 IO，IO 都在 `scripts/`。

### 17.2 端口用 `Protocol`，不用基类继承（S2）

沿用仓库既有惯例（[data_contract.py](../../backtest/data_contract.py) L219 的 `FieldReader(Protocol)`、[types.py](../../types.py) L20 的 `PipelineStepProtocol`）。
新增四个端口，全部 **structural typing（PEP 544）** —— 实现方不需要 import 端口所在模块，也不需要继承：

```python
# backtest/execution/ports.py  (Python 3.9 语法，禁用 | 联合类型)
from typing import Protocol, Sequence, Mapping
import numpy as np

class ImpactModel(Protocol):
    name: str
    def predict(self, participation: np.ndarray, sigma: np.ndarray,
                adv: np.ndarray, params: Mapping[str, float]) -> np.ndarray:
        """返回单边冲击，单位 bps。"""
        ...

class SpreadEstimator(Protocol):
    name: str
    def estimate(self, high: np.ndarray, low: np.ndarray,
                 close: np.ndarray) -> np.ndarray:
        """返回相对价差估计（比例，非 bps）。"""
        ...

class VolumeClassifier(Protocol):
    name: str
    def classify(self, ret: np.ndarray, volume: np.ndarray,
                 sigma: np.ndarray) -> np.ndarray:
        """返回买入成交量占比 ∈ [0,1]。"""
        ...

class DecayModel(Protocol):
    name: str
    def retention(self, horizons: Sequence[int]) -> np.ndarray:
        """返回 alpha 保留率 ρ^h。"""
        ...
```

**验收**：`runtime_checkable` 只在装配处（runner）调用一次 `isinstance`，Core 内部不做类型检查（避免运行时开销与隐式耦合）。

### 17.3 注册表：进程内字典，**不用 entry_points**（S3）

仓库已有同形状实现：[registry.py](../../modules/factor_imputer/plugins/registry.py)（`register/get/list_plugins`），新模块照抄这个形状即可：

```python
class ModelRegistry(object):
    def __init__(self):
        self._models = {}
    def register(self, model):
        self._models[model.name] = model
    def get(self, name):
        return self._models[name]
    def names(self):
        return sorted(self._models)
```

**明确不做**：不引入 `importlib.metadata.entry_points`。
理由：entry points 的价值是**跨发行版**发现插件（Python Packaging Guide 的定位），而本场景全部实现都在同一个仓库内；
引入它只会增加打包复杂度、让「安装了哪个版本」与「跑的是哪个实现」之间多一层间接，违反低耦合。

### 17.4 唯一装配点 + 冻结配置（S4）

- 全仓只有 `backtest/execution/runner.py::build_pipeline(config)` 一处 `new` 具体类，其余函数只接收端口参数；
- 配置用 `@dataclass(frozen=True)`（沿用 [data_contract.py](../../backtest/data_contract.py) 的 `FieldSpec` 风格），并计算 `config_hash` 写入输出 JSON —— 保证任何一张容量表都能回溯到「哪套模型 + 哪组参数」。

### 17.5 三级降级与证据等级（S5）

| 级别 | 数据来源 | 可产出 | `evidence_level` |
|------|---------|--------|------------------|
| L0 | E 盘分钟 feather + BVC | 参与率分档的冲击曲线、指数估计 | `minutes` |
| L1 | 日频 OHLC（CS/AR/Amihud） | 价差、非流动性代理、横截面排序 | `ohlc` |
| L2 | 仅日频收益/成交额 | 用默认 c 的容量（现行口径） | `daily` |

**硬约束**：容量报告的每一行必须携带 `evidence_level`；L1/L2 的行**禁止**在标题或结论里出现「已校准」字样。
这与 data_contract 的 `missing_semantics` 三档同构，也满足 SR 11-7 对「假设与局限必须文档化」的要求。

### 17.6 可检查的内聚/耦合验收（S6）

不靠评审主观判断，用四条机械检查：

1. **纯核检查（元测试）**：对 Core 模块做 `inspect.getsource` / AST 扫描，断言不出现 `open(`、`import os`、`import pyarrow`、`import duckdb`；
2. **反向依赖检查**：`grep` 断言 `backtest/execution/core/` 下不出现 `from .runner`、`from ..shell`；
3. **公开面检查**：每个 Core 模块 `__all__` 长度 ≤ 5，且不含 `*`；
4. **默认路径检查**：现有 `python scripts/verify_capacity_impact.py`（无参数）的 JSON 输出与 v3.7.0 逐位一致（快照测试）。

### 17.7 与现有代码的边界（S7）

- **不改** `backtest/__init__.py`（历史约束）；**复审附注（R-F11）**：`import backtest.execution.*` 仍会
  先执行父包 `__init__.py`（其导入 engine/cached_data_loader 等重模块），设计阶段需确认该副作用在
  无 pyarrow 的最小环境下可接受；若不可接受，备选方案是把执行模块放到独立顶层包（如 `execution/`），
  代价是与 §6 的 `backtest/` 归属惯例偏离，需在设计中显式取舍；
- 新代码集中在 `backtest/execution/`：`ports.py`（端口）、`core/impact.py`、`core/spread.py`、`core/decay.py`、`shell/loaders.py`、`shell/runner.py`、`registry.py`；
- `scripts/verify_capacity_impact.py` 只**新增** `--calibrate` / `--evidence-level` 分支，无参数调用路径保持不变；
- `backtest/data_contract.py` 只**默认化**新鲜度断言（Q6 核销），不改检查逻辑。

---

## §18 第三轮参考文献（32-42）

32. Inoue, A., Jin, L. & Rossi, B. (2017), *Rolling window selection for out-of-sample forecasting with time-varying parameters*,
    Journal of Econometrics 196(1):55-67 — doi:10.1016/j.jeconom.2016.03.006
33. Pesaran, M. H. & Timmermann, A. (2007), *Selection of estimation window in the presence of breaks*,
    Journal of Econometrics 137(1):134-161
34. Pesaran, M. H. & Pick, A. (2011), *Forecast combination across estimation windows*,
    Journal of Business & Economic Statistics 29(2)（复审 R-F3 与正文统一）
35. Gârleanu, N. & Pedersen, L. H. (2013), *Dynamic Trading with Predictable Returns and Transaction Costs*,
    Journal of Finance 68(6):2309-2340
36. Falck, A., Rej, A. & Thesmar, D. (2022), *When do systematic strategies decay?*,
    Quantitative Finance, doi:10.1080/14697688.2022.2098810 — arXiv:2105.01380
37. Novy-Marx, R. & Velikov, M. (2016), *A Taxonomy of Anomalies and Their Trading Costs*,
    Review of Financial Studies 29(5), NBER w20721
38. *Zeroing In on the Expected Returns of Anomalies*, Review of Financial Studies (2023) — 降低再平衡频率作为净收益改进手段
39. *The cost of misspecifying price impact* — arXiv:2306.00599（保守端取参的稳健性结论）
40. *On Parametric Optimal Execution and Machine Learning Surrogates* — arXiv:2204.08581（冲击/韧性的校准困难与敏感性）
41. Python Packaging User Guide：`[project.optional-dependencies]` 与 *Creating and discovering plugins*（entry points 的适用边界）；
    pandas Installation 文档（pyarrow 作为 `parquet`/`feather` extra）；PEP 544（Protocol / structural subtyping）
42. Gary Bernhardt, *Functional Core, Imperative Shell*；Alistair Cockburn, *Hexagonal Architecture (Ports & Adapters)*；
    SR 11-7 *Supervisory Guidance on Model Risk Management*（effective challenge / 局限文档化）

---

## §19 异构复审记录（2026-11-18，第三轮文档复审）

> 沿用 v3.5.3/v3.6.0/v3.7.0 框架：5 视角 × 8 探针。对象为本调研文档三轮全部内容（§0-§18）。
> 复审执行方式：全文重读 + 代码锚点 grep 核对 + E 盘实测复核 + 引文与外部检索比对。
> **结论：PASS_WITH_FIXES** —— 11 项发现（R-F1…R-F11），其中 P2 级 3 项（F1/F2/F10）、
> P3 级 8 项；**全部已当场最小修复落盘**，无遗留阻断项。

### 19.1 视角 × 探针矩阵

| 视角 | 探针 | 结果 | 说明 |
|------|------|------|------|
| V1 公式与计量正确性 | P1 公式复算（CS 12.1 / AR 12.2 / BVC 12.4 / 块长 12.6 / 衰减核） | PASS | CS 的 α 与 β/γ 两日定义与原文一致；AR 两日中点结构正确且诚实标注 `[待核]`；块长式与 PW 2004 一致；近 iid 退化正确 |
| | P2 量纲链自洽（回归式 ↔ 映射式） | **FAIL → 已修复（F10）** | §12.5 原式 `r=λ·signed/ADV`（无量纲参与率）与 `impact=λ·p·ADV/Price`（隐含股数口径 λ）混用；且线性 λ 下 b≡1，幂律检验失去意义。已改为金额口径统一 + 幂律独立回归（§4.1-③ / §12.5） |
| V2 引用与出处 | P3 第三轮新增文献逐条比对（ref 32-42） | PASS（1 处修正 → F3） | IJR 2017 / P&T 2007 / GP 2013 / FRT 2022 / NV 2016 的卷期页码均与检索一致；Pesaran-Pick 2011 期刊在正文误写 J. Econometrics（实为 JBES），已统一 |
| | P4 关键引文原文比对（arXiv:2306.00599 等） | PASS | 「less concave than the point estimate」为原文；FRT 2022 三条结论与 QF 页面一致 |
| V3 数据与内部一致性 | P5 E 盘实测复核 | PASS | 实测 2250 文件、首 2014-01-02 / 末 2023-03-30、2020-01→2023-03 窗口 786 文件 / **39 个月**，与 §2.1 全部一致；补注尾月 2023-03 非整月（F9） |
| | P6 章节间矛盾扫描（§9 ↔ §15.2 ↔ §16 ↔ §17） | **FAIL → 已修复（F1/F2/F4-F9）** | 见 19.2 |
| V4 与代码库对齐 | P7 代码锚点核对 | PASS | `SQRT_C=(0.1,0.5,1.0)` / `LINEAR_K=(0.01,0.025,0.05)` / `_resolve_lag` / `stationary_bootstrap_indices` 均存在；pyproject L41-56 五个 extras 属实；`FieldReader(Protocol)` / `PluginRegistry` 先例属实 |
| | P8 架构可实现性（S1-S7 逐条） | PASS（1 附注 → F11） | `import backtest.execution.*` 会先执行父包 `__init__.py` 的重导入（engine/cached_data_loader 等），S7 已补附注与备选方案 |
| V5 决策效度 | （并入 P6/P7：裁决建议的锚点充分性、反方风险对称性、保守方向一致性） | PASS | D2 三档判据中 `argmax Impact(c)` 因冲击对 c 单调而退化为「取 CI 上界」，语义等价、方向保守，可接受；§16.5 影响面表使裁决可回溯 |

### 19.2 发现清单（全部已修复）

| ID | 级别 | 章节 | 缺陷 | 修复 |
|----|------|------|------|------|
| F1 | P2 | §9-D1 ↔ §16.1 | 第一轮建议 B（延迟 import）与第三轮建议 A（calib extra）矛盾且未标注取代关系 | §9-D1 行标注「以第三轮为准」；§16 引言改为「D1/D3/D4 建议被修订」 |
| F2 | P2 | §9-D3 ↔ §16.3 | 第一轮 B（不设主值）与第三轮 AveW 主值矛盾，未标注取代 | 同上，§9-D3 行标注修订依据（Pesaran-Pick；39 个 OOS 点不支持选窗） |
| F3 | P2 | §16.3 / ref 34 | Pesaran & Pick 2011 期刊误写 J. Econometrics，正文与参考文献自相矛盾 | 统一为 JBES 29(2) |
| F10 | P2 | §12.5 / §4.1-3 | 回归式与映射式量纲口径不自洽；且线性 λ 下 b≡1 使 sqrt 律检验失去意义 | 映射改 `λ·p·1e4`（金额口径）；幂律 b 改为分钟级独立回归；两处同步 + 口径纪律条目 |
| F4 | P3 | §15.2 | 「维持 §9-D2 的裁决」把待裁决项写成既成裁决 | 改为「一致建议，待最终裁决」 |
| F5 | P3 | §9-D4 ↔ §16.4 | 21 日与 20 交易日两种计数并存 | §9-D4 行标注统一为 h=20 交易日 |
| F6 | P3 | §6 / §8 ↔ §17.7 | 脚本分支名 `--calibrated` 与 `--calibrate` 不一致 | 统一为 `--calibrate` |
| F7 | P3 | §2.3 ↔ §16.1 | optional group 命名 `research` 与 `calib` 并存 | §2.3 标注两命名并存、以 D1 裁决为准 |
| F8 | P3 | §16.5 ↔ §17.7 | D4 影响面路径 `execution/decay.py` 与布局 `core/decay.py` 不一致 | 统一为 `backtest/execution/core/decay.py` |
| F9 | P3 | §2.1 | 「39/73 月」含尾月 2023-03 非整月（止于 03-30）未注明 | 补注口径；E 盘实测复核确认 39 月计数无误 |
| F11 | P3 | §17.7 / S7 | 「不改 `backtest/__init__.py`」但子包 import 仍会执行父包重导入，与最小环境目标潜在冲突 | S7 补附注 + 独立顶层包备选方案，留设计阶段取舍 |

### 19.3 复审边界

- §2.1 的行数/GB/零成交占比/指数混入数等**文件内容级**实测值为第一轮取证结果，本轮只复核了
  **文件计数与覆盖月数**（P5），未重放 25.6GB 内容级统计 —— 设计阶段 E0 的加载器验收测试会覆盖；
- ref 37 的 RFS 卷期页码（29(5)）未独立核到页级，卷号与 NBER w20721 已确认；
- §11.4 I-Star 参数边界 `[二手来源-待核]` 标注保持，不计入缺陷（文档已自我标注）。
