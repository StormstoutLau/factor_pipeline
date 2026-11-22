# 调研文档：P-010 股票×日 vs 股票×月粒度偏差

---
id: p010-granularity-bias-RESEARCH
type: design
version: 1.3
status: verified
date: 2026-11-22
depends: [v392-calibration-unit-fix-RESEARCH, v392-calibration-unit-fix-DESIGN]
upstream: null
---

> **Feature**: P-010 股票×日 vs 股票×月粒度偏差 — 量化偏差并决定是否按股票×月重采样
> **创建日期**: 2026-11-22
> **状态**: verified（Step 1 调研 + Step 2 独立复核完成 2026-11-22；v1.1 = 补充 4 篇学术锚点 + 5 份官方文档 + 2 条社区案例；v1.2 = Step 2 复核：Crossref REST 异构通道 9/9 + 探针复跑逐位一致 + 代码锚点 7/7 重验 + 派生读数复算修正 2 处精度，见 §5.4；v1.3 = Step 9 订正 v392 DESIGN §5.2 悬空引用，见 §3.1 勘误）
> **Spec 步骤**: Step 1-2
> **批次目录**: `spec/p010-granularity-bias/`（目录不带版本号；包版本由 Step 6 裁决，避免与既有 `v3100-reversal-evidence` 语义冲突）
> **档位（预判）**: **T1**——若采纳重采样，将改变 `panel_hash` / `cost_by_h` / 容量读数（真值源与契约变更）；若最终裁决为「仅披露」，则降为 T3，须在 DESIGN §1 重判并留痕。

---

## 1. 调研目标

**核心问题**:

1. **偏差有多大**：现行「股票×日等权」样本与 DESIGN §5.2 要求的「股票×月等权」样本，冲击系数 `c`、bootstrap CI、CV-RMSE 相差多少？在 39 月窗口内是否稳定？
2. **偏差从哪来**：差异可分解为哪些机制——样本权重（股票×日 vs 股票×月）、月内相关性导致的有效样本量、σ 的聚合口径、CV 切折方式（行序连续 vs 按月份分组）？
3. **是否采纳**：若偏差显著，重采样的代价（`panel_hash` 变更、`cost_by_h`/容量重算、默认 SHA 是否受影响）与收益如何权衡；若不采纳，需要披露哪些口径限制？

## 2. 调研方法

### 2.1 使用的工具

| 工具 | 用途 | 查询 |
|------|------|------|
| mcp_paper-search（Crossref） | 外部方法学锚点（panel clustering / 聚合 / 交易成本） | 见 §3.3 |
| WebFetch | 官方文档原文核验（statsmodels / linearmodels / scikit-learn / Qlib / Zipline） | 见 §3.6 |
| mcp_stackexchange | 社区案例与工程陷阱（Cross Validated / Stack Overflow） | 见 §3.6 |
| 本仓检索（Read/Grep） | 代码锚点与设计原文核对 | `panels.py` / `runner.py` / `impact.py` / v392 DESIGN §1.2/§5.2 |
| E1 探针（本目录 `probe_granularity.py`） | 39 月四口径对照（D / M / 月聚类 / CV） | 复用 `out/panel_cache`，只读生产构建器 |

### 2.2 调研范围

- **时间范围**：数据 2020-01 ~ 2023-03（39 月）；方法学文献 1973-2018。
- **领域**：面板数据推断、交易成本/冲击标定、横截面资产定价。
- **排除**：不做逐笔方向（BVC 数据限制）、不引入带截距/符号冲击回归（方案 C 的另一分支）。

### 2.3 证据分级与降级链（F1-F3）

- **F1 来源日期**：全部外部来源读取日 = **2026-11-22**；期刊出版日见 §5.1。
- **F2 来源版本**：Crossref 返回的 DOI + 卷/期/页；仓内文件写 `v392 DESIGN` 行号。
- **F3 降级链**：Crossref 首次查询即命中（Petersen 返回 NBER/SSRN/RFS 三版本，取 RFS 期刊版；Thompson 返回 SSRN/JFE 两版本，取 JFE 版）；`Frazzini et al. (2018)` 仅有 SSRN 工作论文版，未检索到期刊版 → 按 SSRN 版本引用并标注。WebFetch 五个官方文档全部一次命中。StackExchange 首轮宽查询（`bootstrap panel data resample clusters` 等）0 命中 → 换窄关键词后命中 2 条（Cross Validated Q205036、Stack Overflow Q65705171）；**无静默跳过**。

## 3. 调研发现

### 3.1 现状锚点（E1，仓内代码逐行核对）

| 事实 | 锚点 | 说明 |
|---|---|---|
| 样本上限 200,000 行 | [panels.py L32](../../backtest/execution/shell/panels.py#L32) `SAMPLE_CAP = 200000` | 39 月 `cap_month = ceil(200000/39) ≈ 5,129` 行/月 |
| 样本粒度 = 股票×日 | [panels.py L480-L483](../../backtest/execution/shell/panels.py#L480-L483) | 每股票每日一行 `(p, impact, sigma, code, ym)` |
| `p = |signed_day|/ADV`、`impact = |ret_day|`、`sigma = std(ret_day)` clip | [panels.py L449-L483](../../backtest/execution/shell/panels.py#L449-L483) | σ 为月内日收益标准差；clip `[0.005, 0.20]` |
| 等距抽样（非随机） | [panels.py L631-L634](../../backtest/execution/shell/panels.py#L631-L634) + `_sample_indices` L146-L151 | 按 `(p, sigma)` lexsort 后等距取索引 |
| bootstrap 为 iid 行抽样 | [runner.py L161-L176](../../backtest/execution/shell/runner.py#L161-L176) | `rng.integers(0, n, size=n)`，未按月/股票聚类 |
| CV 为行序连续 5 折 | [impact.py L151-L174](../../backtest/execution/core/impact.py#L151-L174) | `np.array_split(np.arange(n), folds)`；因样本按月追加，切折近似时间顺序，但不保证整月进出 |
| 元数据已标注粒度 | [panels.py L664-L666](../../backtest/execution/shell/panels.py#L664-L666) | `impact_samples_meta.granularity = "daily"`、`sampling = "equal_distance"` |

**设计口径对照**：

- v392 DESIGN §1.2（L38）把「股票×日 → 股票×月」列为**非目标**（B9 遗留）；执行计划 `docs/EXECUTION_V3.8.0_EXECUTION_CAPACITY.md` 的 `cross_val_rmse` docstring（L219）写「按『股票×月』聚类、按时间切折」，与设计非目标存在字面冲突——本批先量化偏差，再决定是否解除该非目标。
  > **勘误（v1.3，Step 9 发现 F-9-1）**：v392 RESEARCH §2 表所引「DESIGN §5.2（L237-243）」在仓内**不存在**，属悬空引用；实际约束来源为 v392 DESIGN §1.2 L38（非目标）与上述执行计划 docstring。已在该两处加勘误标记。
- v392 RESEARCH §4.1 第 4 条已记录实现偏差：「样本粒度也与 DESIGN §5.2 不符：设计为『股票×月』，实现为『股票×日』最多 200,000 行，CV 按行顺序切折而非按月聚类（B9）」——[RESEARCH.md L124-L125](../v392-calibration-unit-fix/RESEARCH.md#L124-L125)。

### 3.2 偏差机制分解（待 E1 读数验证）

1. **权重机制**：股票×日等权 ⇒ 每只股票权重 ∝ 其当月有效天数；跨月看，股票数随时间增长（2020 年约 3,800 → 2023 年约 5,100），后期月份在总样本中占比更高。股票×月等权则每月每股同权，消除「后期月份/上市较早股票」的隐性加权。
2. **有效样本量**：同一股票同一月的日观测共享 σ 与个股特征，月内相关使有效样本量小于行数；iid bootstrap 会把 CI 压窄。按月整块重采样可恢复「月」为独立单位。
3. **σ 聚合**：日粒度下同一股票当月所有行共用同一 `sigma_d`，等价于把该股月内日收益标准差重复计入；月粒度下每股每月只贡献一行，σ 不重复。
4. **CV 切折**：行序连续切折可能把同一个月拆到训练/测试两侧（月内泄漏）；按月分组切折保证整月进出，检验跨月泛化。

### 3.3 外部方法学锚点（T1/T2）

#### Petersen (2009) — 面板标准误必须按公司/时间聚类

- **标题**: Estimating Standard Errors in Finance Panel Data Sets: Comparing Approaches
- **作者**: Mitchell A. Petersen
- **年份**: 2009（在线 2008-06-03）
- **DOI**: [10.1093/rfs/hhn053](https://doi.org/10.1093/rfs/hhn053)
- **验证状态**: ✅ Crossref 命中（RFS 22(1):435-480）
- **关键结论**: 公司效应/时间效应普遍存在；未聚类或仅单向聚类会系统性低估标准误；推荐按公司、时间或两者聚类，并报告敏感性。
- **与本 feature 的相关性**: 直接支持「月内日观测不独立」→ iid bootstrap 的 CI 不可直接采信；月聚类是本批最小修复。

#### Thompson (2011) — 双向聚类闭式公式

- **标题**: Simple formulas for standard errors that cluster by both firm and time
- **作者**: Samuel B. Thompson
- **年份**: 2011
- **DOI**: [10.1016/j.jfineco.2010.08.016](https://doi.org/10.1016/j.jfineco.2010.08.016)
- **验证状态**: ✅ Crossref 命中（JFE 99(1):1-10）
- **关键结论**: 双向聚类协方差 = 按公司聚类 + 按时间聚类 − 异方差稳健协方差；任何带聚类命令的软件均可计算。
- **与本 feature 的相关性**: 若本批保留行级回归，至少应按「月」聚类（单维即可）；若同时关心个股聚类，可按双向公式扩展（本批不强制）。

#### Cameron, Gelbach & Miller (2011) — 多向聚类的渐近性质

- **标题**: Robust Inference With Multiway Clustering
- **作者**: A. Colin Cameron; Jonah B. Gelbach; Douglas L. Miller
- **年份**: 2011
- **DOI**: [10.1198/jbes.2010.07136](https://doi.org/10.1198/jbes.2010.07136)
- **验证状态**: ✅ Crossref 命中（JBES 29(2):238-249）
- **关键结论**: 多向聚类下常规推断失效；给出多向聚类方差估计与有限样本修正，聚类数少时需谨慎。
- **与本 feature 的相关性**: 本仓 39 个月 ≈ 39 个时间簇，属于「聚类数偏少」区间；月聚类 bootstrap 的 CI 应作为主口径，iid CI 仅作对照。

#### Fama & MacBeth (1973) — 月度横截面回归的标准范式

- **标题**: Risk, Return, and Equilibrium: Empirical Tests
- **作者**: Eugene F. Fama; James D. MacBeth
- **年份**: 1973
- **DOI**: [10.1086/260061](https://doi.org/10.1086/260061)
- **验证状态**: ✅ Crossref 命中（JPE 81(3):607-636）
- **关键结论**: 逐月截面回归 + 时间序列汇总；每月每资产一个观测，避免月内重复观测主导权重。
- **与本 feature 的相关性**: 支持「股票×月」作为标定样本的默认单位；与 DESIGN §5.2 一致。

#### Frazzini, Israel & Moskowitz (2018) — 交易成本的实现口径

- **标题**: Trading Costs
- **作者**: Andrea Frazzini; Ronen Israel; Tobias J. Moskowitz
- **年份**: 2018（SSRN 工作论文）
- **DOI**: [10.2139/ssrn.3229719](https://doi.org/10.2139/ssrn.3229719)
- **验证状态**: ✅ Crossref 命中（SSRN；未检索到期刊版）
- **关键结论**: 用 1.7 万亿美元真实成交数据标定成本/冲击函数；成本随交易规模、股票特征、时间与交易所变化；模型需在样本外检验。
- **与本 feature 的相关性**: 说明冲击标定的样本单位与权重会直接影响成本曲线；支持「月度等权 + 跨月 CV」作为更保守的标定方式。

#### Cameron & Miller (2015) — 聚类稳健推断的实践指南

- **标题**: A Practitioner's Guide to Cluster-Robust Inference
- **作者**: A. Colin Cameron; Douglas L. Miller
- **年份**: 2015
- **DOI**: [10.3368/jhr.50.2.317](https://doi.org/10.3368/jhr.50.2.317)
- **验证状态**: ✅ Crossref 命中（JHR 50(2):317-372）
- **关键结论**: 聚类数少时常规 cluster-robust 推断会过度拒绝；建议报告聚类数、使用小样本修正，并在少簇时采用 wild cluster bootstrap 等替代；聚类应选在「相关性来源」的层级。
- **与本 feature 的相关性**: 39 个月簇属于少簇区间；直接支持「月聚类 bootstrap 主口径 + 报告簇数」而非 iid bootstrap。

#### MacKinnon & Webb (2018) — 少簇下的 wild cluster bootstrap

- **标题**: The wild bootstrap for few (treated) clusters
- **作者**: James G. MacKinnon; Matthew D. Webb
- **年份**: 2018
- **DOI**: [10.1111/ectj.12107](https://doi.org/10.1111/ectj.12107)
- **验证状态**: ✅ Crossref 命中（Econometrics Journal 21(2):114-135）
- **关键结论**: 少簇（含处理簇更少）时，wild cluster bootstrap 可显著改善推断；聚类数极小时任何方法都可能不完美，需报告敏感性。
- **与本 feature 的相关性**: 为「39 月少簇」提供比普通 pairs bootstrap 更稳健的敏感性方案；本批可先做月聚类 pairs bootstrap，wild 版登记为可选。

#### Driscoll & Kraay (1998) — 空间/时间依赖的面板协方差

- **标题**: Consistent Covariance Matrix Estimation with Spatially Dependent Panel Data
- **作者**: John C. Driscoll; Aart C. Kraay
- **年份**: 1998
- **DOI**: [10.1162/003465398557825](https://doi.org/10.1162/003465398557825)
- **验证状态**: ✅ Crossref 命中（Review of Economics and Statistics 80(4):549-560）
- **关键结论**: 面板残差同时存在截面与时间依赖时，需用 Driscoll-Kraay 型协方差；普通 HAC 或单向聚类不足。
- **与本 feature 的相关性**: 若未来采用双向聚类（方案 D），DK 是时间维依赖的备选；本批的月聚类是单维最小修复。

#### Gormley & Matsa (2014) — 固定效应与聚类选择的常见错误

- **标题**: Common Errors: How to (and Not to) Control for Unobserved Heterogeneity
- **作者**: Todd A. Gormley; David A. Matsa
- **年份**: 2014
- **DOI**: [10.1093/rfs/hht047](https://doi.org/10.1093/rfs/hht047)
- **验证状态**: ✅ Crossref 命中（RFS 27(2):617-661）
- **关键结论**: 固定效应与聚类层级需与识别策略匹配；错误的聚类/去均值会引入偏误或夸大精度。
- **与本 feature 的相关性**: 提醒「按月聚合」不是无条件更好——必须与标定目标（跨月泛化）和权重语义一致；支持在 DESIGN 中显式裁决聚合算子（U-1）。

### 3.4 E1 探针读数（39 月，四口径对照）

> 探针：[probe_granularity.py](./probe_granularity.py)；复用 `out/panel_cache`，不写生产工件；输出 `%TEMP%\p010_granularity.json`。

**样本规模**：39 月（2020-01 ~ 2023-03）；**200,031 行**（`cap_month=5,129` 行/月，生产再全局裁到 200,000）；**119,287 个股票×月**；平均 **1.677 行/股票×月**——200k 上限 + 每月等距抽样已在月内做了强子采样，并非「每股每月 20 行」。

| 口径 | `c` | 5%–95% CI | CI 宽度 | CV-RMSE（行序 / 按月） |
|---|---:|---|---:|---:|
| **D 股票×日 + iid bootstrap（现行）** | **2.9100** | [2.8972, 2.9213] | 0.0242 | 2.7476 / 2.7476 |
| D 股票×日 + 月聚类 bootstrap | 2.9100 | [2.8904, 2.9349] | 0.0445 | — |
| **M 股票×月 + iid bootstrap** | **2.7930** | [2.7794, 2.8069] | 0.0275 | 1.8191 / 1.8191 |
| M 股票×月 + 月聚类 bootstrap | 2.7930 | [2.7739, 2.8126] | 0.0387 | — |

**派生读数**：

- **Δc（M vs D）= −4.022%**；D 口径 `c=2.9100` 与 v3.9.2 校准读数 `2.91` 逐位吻合 → 探针复现生产口径（E1 可信）。
- **CI 宽度**：D 从 iid 0.0242 → 月聚类 0.0445（**+83.8%**，精确 83.84%）；M 从 0.0275 → 0.0387（**+40.8%**，精确 40.84%）。iid bootstrap 显著低估不确定性。
- **CV 切折**：行序与按月分组的 RMSE 差异 **+0.0018%**（D）/ **+0.0011%**（M）——差异在 ±0.002% 内，且行序略**高**于按月（与「行序乐观」预期方向相反）；现行「行序连续切折」在本样本上没有可测的月内泄漏。
- **样本量效应**：M 口径行数降为 D 的 59.6%（119,287 / 200,031），但 CV-RMSE 从 2.75 降到 1.82，说明重复的日观测主要放大了拟合权重，而非提供独立信息。

> **口径说明**：上表 `c` 为 `SqrtImpact.fit` 的**原始点估计**，仅用于粒度对照；生产最终 `c_calib_point` 还经 `C_RANGE (0.1, 2.0)` 与可识别性规则裁决（v3.9.2：原始 2.91 超区间 → 最终回退 0.5）。本批不改变该回退规则，只量化粒度对原始拟合与 CI 的影响。

### 3.5 偏差机制的证据映射

| 机制 | 观测方式 | 预期方向 | E1 读数 |
|---|---|---|---|
| 权重（后期月份股票数更多） | 月样本行数 / 股票数 | 日粒度给后期月份更高权重 | **未单独测量**；`cap_month=5,129` 已把各月样本量拉平，机制被显著削弱 |
| 月内相关 → 有效样本量 | iid vs 月聚类 CI 宽度 | iid CI 窄于月聚类 CI | **成立**：D 宽度 +83.8%，M 宽度 +40.8% |
| σ 重复计入 | 每股每月行数 | 日粒度重复计 σ | 部分成立：D 口径 1.677 行/股票×月，σ 重复但被 200k cap 稀释；M 口径 Δc −4.02% 为混合结果 |
| CV 月内泄漏 | 行序 vs 按月 CV | 行序 CV 偏低（乐观） | **不成立**：差异 +0.0018%（D）/ +0.0011%（M）且行序略高（方向与预期相反），±0.002% 内无可测泄漏 |

### 3.6 工程实现与社区案例（落地风险锚点）

| 来源 | 层级 | 事实（原文/文档） | 对 P-010 的含义 |
|---|---|---|---|
| statsmodels `get_robustcov_results` | T1 官方 | `cov_type='cluster'`（CRV1）需整数 `groups`；`df_correction=True` 时自由度按 **G−1**；文档明确「number of groups is small 时 p 值可能与正态近似差很多」 | 39 月簇 → t(38)；必须报告簇数并做小样本修正 |
| linearmodels `PanelOLS.fit` | T1 官方 | `cov_type='clustered'` 支持 1/2 个聚类变量（`cluster_entity` / `cluster_time`）；`group_debias` 乘 **g/(g−1)·(n−1)/n** | 若走双向聚类可直接复用；月聚类也应做同型 debias 敏感性 |
| scikit-learn `GroupKFold` | T1 官方 | 「K-fold iterator variant with **non-overlapping groups**. Each group will appear exactly once in the test set across all folds」 | 若 CV 按月分组，应使用 group-disjoint 切分；但 E1 显示行序切折差异仅 0.001%，可作可选项 |
| statsmodels `hac-panel` 文档 + SO 65705171 | T1/T3 | `hac-panel` 要求数据按面板单位堆叠排序；未排序会报 `all groups are empty taking lags` | 工程陷阱：若改手写聚类协方差，必须显式排序/堆叠；本批用 bootstrap 可绕开 |
| Cross Validated Q205036 | T3 | 「Bootstrapping in Binary Response Data with Few Clusters and Within-Cluster Correlation」（score 6，1 answer） | 社区实践确认「少簇 + 组内相关」是已知难点；仅作风险提示，不作方法学依据 |
| Qlib 回测配置文档 | T1 官方 | `open_cost: 0.0005`、`close_cost: 0.0015`、`min_cost: 5`；未见样本拟合冲击 | 主流引擎用固定费率；本仓的样本标定属研究级增强，披露粒度限制可接受 |
| Zipline `VolumeShareSlippage` | T1 官方 | 二次型 `price*(1 ± price_impact*volume_share²)`，`volume_limit=0.025`、`price_impact=0.1` 为固定参数 | 工程界常用固定参数冲击函数，不依赖股票×日/×月样本粒度 |

**决策含义**：

- 支持 **方案 C**（月聚类 bootstrap + 小样本修正），而不是仅换 CV——CV 的 E1 差异可忽略，CI 的 E1 差异显著。
- 若 DESIGN 选择双向聚类（D），linearmodels 的 `group_debias` 与 Driscoll-Kraay 是现成参照；39 月簇下须报告敏感性。
- Qlib / Zipline 的固定参数实践说明：无需为「工程对齐」强推方案 B；研究级标定应显式披露粒度、簇数与修正方式。

## 4. 综合分析

### 4.1 关键发现总结

1. **点估计稳健**：股票×月 `c=2.7930` vs 股票×日 `c=2.9100`，相对差 **−4.02%**，低于预设 10% 门槛；D 口径复现 v3.9.2 `c=2.91`，探针可信。 [置信度: ★★★★★]
2. **推断偏差显著**：月聚类后 CI 宽度 D 扩大 **83.8%**、M 扩大 **40.8%**；现行 iid bootstrap 系统性低估不确定性，这是本批最实质的偏差。 [置信度: ★★★★★]
3. **CV 切折不是问题**：行序连续切折与按月分组切折的 RMSE 差异仅 **±0.002% 以内**（D +0.0018%、M +0.0011%，行序略高）；B9 中「CV 按月聚类」的担忧在本样本上不成立。 [置信度: ★★★★☆]
4. **200k 上限重塑了样本**：平均 **1.677 行/股票×月**，`cap_month=5,129` 已使各月样本量近似相等；「后期月份股票更多 → 权重更高」的机制被 cap 显著削弱。 [置信度: ★★★★☆]
5. **设计-实现偏差仍在**：DESIGN §5.2 写「股票×月」，实现与 `impact_samples_meta.granularity` 均为 `daily`；无论是否改口径，都必须在 DESIGN 中显式裁决并留痕。 [置信度: ★★★★★]

### 4.2 技术 landscape（候选口径）

| 方案 | 内容 | 代价 | 现状 |
|---|---|---|---|
| **A 保持现状 + 披露** | 股票×日等权 + iid bootstrap；在报告/工件标注 `granularity=daily` 与粒度限制 | 零代码；但 CI 仍偏窄，设计-实现偏差继续存在 | 现行 |
| **B 改股票×月等权** | 月内 `(p, impact, σ)` 取均值；重新拟合 c；月聚类 bootstrap；CV 按月分组 | `panel_hash` 变更、`cost_by_h`/容量重算；默认 `capacity_impact.json` 是否受影响需 DESIGN 裁决 | DESIGN §5.2 目标；E1 Δc −4.02% |
| **C 仅换 bootstrap（+CV 可按月）** | 保留股票×日样本与点估计，bootstrap 改月聚类；CV 可选按月分组 | 改动小；点估计不变，CI 更保守（宽度 +83.8%）；`panel_hash` 不变 | E1 倾向主方案 |
| **D 双向聚类** | 按月 + 按股票双向聚类（Thompson 公式） | 实现复杂；39 月/5,000 股，月簇少 | 备选敏感性 |

**E1 倾向**：**方案 C + 方案 A 披露**。理由：点估计差 4.02% 未达 10% 采纳门槛，而 CI 宽度变化 83.8% 超过 20% 修复门槛；方案 B 会改 `panel_hash`/成本口径，收益不足以抵消变更成本。若 Step 3 DESIGN 坚持 DESIGN §5.2 原文的「股票×月」，则 B 需独立版本、新旧对照与回退点。方案 C 的 CI 实现细节：月聚类 pairs bootstrap 为主，`group_debias = g/(g−1)·(n−1)/n`（g=39）与 wild cluster bootstrap 作为敏感性附表；报告须显式标注簇数 39 与 t(38) 自由度。

### 4.3 研究空白

- 本批已补齐「股票×日 vs 股票×月」的 39 月对照（§3.4）；**月度加权聚合**（成交额加权 / 末值）尚未测，留待设计阶段裁决（U-1）。
- B9 的「CV 按月聚类」担忧经 E1 否定（差异 ±0.002% 内），但「CI 聚类」担忧被证实（宽度 +83.8%）。
- 若改月度口径，`panel_hash` 与 `cost_by_h`/容量的变更幅度仍无实测（本批只测原始 `c` 与 CI，未跑成本曲线）。

### 4.4 决策锚点矩阵（结论 → 证据 → 限制）

| 决策 / 结论 | 支持锚点 | 反例 / 限制 | 强度 |
|---|---|---|---|
| 采用**月聚类 CI**（方案 C） | Petersen (2009)；Cameron & Miller (2015)；statsmodels `df_correction=G−1`；E1 CI 宽度 +83.8% | 39 簇偏少 → MacKinnon & Webb (2018) wild cluster bootstrap 作敏感性；任何方法在极少簇下都不完美 | **强**（E1 + T1） |
| **不采纳**股票×月点估计（方案 B） | E1 `|Δc|/c=4.02% < 10%`；Fama-MacBeth (1973) 月度单位是范式但非本仓强制；Gormley & Matsa (2014) 警示聚合非无条件更优 | DESIGN §5.2 原文要求股票×月 → 必须在 DESIGN 解释偏离或改设计 | **中强**（需 DESIGN 裁决） |
| **CV 切折不强制按月** | E1 行序 vs 按月 RMSE 差异 ±0.002% 内；scikit-learn GroupKFold 仅在需组不重叠时使用 | 样本结构变化（如月份长度差异放大）需重测 | **强**（E1） |
| **披露粒度与簇数** | Qlib / Zipline 固定参数工程现状；statsmodels 少簇警告 | 仅披露不能修复 CI 偏窄，必须配 C | **强**（T1 + E1） |
| 月度聚合算子（均值/加权）**待裁决** | Gormley & Matsa (2014)；U-1 | 加权/末值未测，均值只是当前倾向 | **待定**（U-1） |
| 若走双向聚类（方案 D） | Thompson (2011)；Cameron et al. (2011)；linearmodels `group_debias`；Driscoll & Kraay (1998) | 股票簇多、月簇少；实现与解释成本高 | **备选**（不做主方案） |

## 5. 幻觉抑制审查（Step 2 Review）

### 5.1 文献验证（F4）

| 引用 | DOI | 验证方式 | 状态 | 命中或差异 |
|---|---|---|---|---|
| Petersen (2009) | 10.1093/rfs/hhn053 | Crossref 查询（标题+作者） | ✅ 已验证 | RFS 22(1):435-480；另有 NBER w11280 / SSRN 661481 两版本，取期刊版 |
| Thompson (2011) | 10.1016/j.jfineco.2010.08.016 | Crossref 查询 | ✅ 已验证 | JFE 99(1):1-10；另有 SSRN 914002 版 |
| Cameron, Gelbach & Miller (2011) | 10.1198/jbes.2010.07136 | Crossref 查询 | ✅ 已验证 | JBES 29(2):238-249 |
| Fama & MacBeth (1973) | 10.1086/260061 | Crossref 查询 | ✅ 已验证 | JPE 81(3):607-636 |
| Frazzini, Israel & Moskowitz (2018) | 10.2139/ssrn.3229719 | Crossref 查询 | ⚠️ 已验证但仅 SSRN | 未检索到期刊版；按工作论文引用 |
| Cameron & Miller (2015) | 10.3368/jhr.50.2.317 | Crossref 查询 | ✅ 已验证 | JHR 50(2):317-372 |
| MacKinnon & Webb (2018) | 10.1111/ectj.12107 | Crossref 查询 | ✅ 已验证 | Econometrics Journal 21(2):114-135 |
| Driscoll & Kraay (1998) | 10.1162/003465398557825 | Crossref 查询 | ✅ 已验证 | Review of Economics and Statistics 80(4):549-560 |
| Gormley & Matsa (2014) | 10.1093/rfs/hht047 | Crossref 查询 | ✅ 已验证 | RFS 27(2):617-661 |
| statsmodels 文档 | https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.RegressionResults.get_robustcov_results.html | WebFetch 原文 | ✅ 已验证（T1 官方） | cluster CRV1 + df_correction G−1 |
| linearmodels 文档 | https://bashtage.github.io/linearmodels/panel/panel/linearmodels.panel.model.PanelOLS.fit.html | WebFetch 原文 | ✅ 已验证（T1 官方） | 1/2-way clustering + group_debias |
| scikit-learn GroupKFold | https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html | WebFetch 原文 | ✅ 已验证（T1 官方） | non-overlapping groups |
| Qlib workflow 文档 | https://qlib.readthedocs.io/en/latest/component/workflow.html | WebFetch 原文 | ✅ 已验证（T1 官方） | open/close cost 固定费率 |
| Zipline API 文档 | https://zipline.ml4trading.io/api-reference.html | WebFetch 原文 | ✅ 已验证（T1 官方） | VolumeShareSlippage 二次型 |
| Cross Validated Q205036 | https://stats.stackexchange.com/questions/205036 | StackExchange API 命中 | ⚠️ T3 | 少簇 bootstrap 风险提示 |
| Stack Overflow Q65705171 | https://stackoverflow.com/questions/65705171 | StackExchange API 命中 | ⚠️ T3 | HAC-panel 排序陷阱 |

### 5.2 技术声明验证

| 声明 | 来源 | 验证状态 |
|---|---|---|
| 月内日观测存在相关性，iid 推断会低估标准误 | Petersen (2009); Cameron et al. (2011) | ✅ 已回原文摘要/结论 |
| 双向/多向聚类可用闭式或 bootstrap 实现 | Thompson (2011); Cameron et al. (2011) | ✅ 已验证 |
| 月度截面单位可避免月内重复观测主导 | Fama & MacBeth (1973) | ✅ 已验证 |
| 冲击/成本标定对样本单位与权重敏感 | Frazzini et al. (2018) | ✅ 已验证（工作论文） |
| 少簇时 cluster-robust 推断会过度拒绝，需小样本修正/报告簇数 | Cameron & Miller (2015); statsmodels 文档；MacKinnon & Webb (2018) | ✅ 已验证 |
| 双向聚类可用 `group_debias` 的 g/(g−1)·(n−1)/n 修正 | linearmodels 文档 | ✅ 已验证（T1 官方） |
| CV 若按组切分应保证组不重叠 | scikit-learn GroupKFold 文档 | ✅ 已验证（T1 官方） |
| 主流回测引擎采用固定费率/固定参数冲击，不做样本拟合 | Qlib workflow 文档；Zipline API 文档 | ✅ 已验证（T1 官方，仅作工程现状） |
| 现行实现为股票×日、iid bootstrap、行序 CV | 仓内代码 L32/L480/L631、runner L161、impact L151 | ✅ E1 逐行核对 |

### 5.3 待修正项

- [x] E1 探针读数已回填；「预期方向」逐条核对（CV 项不成立，已在 §3.5 说明原因）。
- [x] Step 2 复核修正（2026-11-22）：CI 宽度比 +83.9% → **+83.8%**（精确 83.84%）、CV 差异改精确值 D +0.0018% / M +0.0011%（行序略高）——已订正 §3.4/§3.5/§4/U-3，见 §5.4。
- [ ] 若最终采纳方案 B，须在 DESIGN 明确 `panel_hash` 变更与默认 SHA 的处理方式。
- [ ] Frazzini et al. 仅有 SSRN 版，引用时标注「工作论文」；不得表述为期刊论文。
- [ ] 社区案例（Q205036 / Q65705171）仅作 T3 风险提示，不得单独支撑设计决策。

### 5.4 Step 2 独立复核记录（2026-11-22）

**复核方式**：四通道独立取证，与 Step 1 的工具/通道异构；LLM 不自任验证器，结论以可重放命令与原文落盘为准。

#### 5.4.1 引用核验（异构通道：Crossref REST `api.crossref.org/works/<DOI>`）

| DOI | REST 复核 | 关键元数据（与 §5.1 一致） |
|---|---|---|
| 10.1093/rfs/hhn053 | ✅ | Petersen，RFS 22(1):435-480（cites 9891） |
| 10.1016/j.jfineco.2010.08.016 | ✅ | Thompson，JFE 99(1):1-10（cites 1192） |
| 10.1198/jbes.2010.07136 | ✅ | Cameron;Gelbach;Miller，JBES 29(2):238-249（cites 2648） |
| 10.3368/jhr.50.2.317 | ✅ | Cameron;Miller，JHR 50(2):317-372（cites 4784） |
| 10.1086/260061 | ✅ | Fama;MacBeth，JPE 81(3):607-636（cites 11276） |
| 10.2139/ssrn.3229719 | ✅ | Frazzini;Israel;Moskowitz，`type=posted-content`、year 2018、无卷期页（container/page/issue 空）——独立佐证「仅 SSRN 工作论文版」；批量脚本首轮因该条 page/issue 为 null 报错，单条重查通过 |
| 10.1111/ectj.12107 | ✅ | MacKinnon;Webb，EctJ 21(2):114-135（cites 327） |
| 10.1162/003465398557825 | ✅ | Driscoll;Kraay，REStat 80(4):549-560（cites 6271） |
| 10.1093/rfs/hht047 | ✅ | Gormley;Matsa，RFS 27(2):617-661（cites 1110） |

**9/9 命中**，标题/作者/期刊/卷期页/年份逐字段与 §5.1 一致。

**官方文档 5 条**：statsmodels 本步重新抓取原文复核——`cov_type='cluster'`（CRV1）、`df_correction` 默认 True 时自由度按「number of groups minus one」、「may differ substantially from p-values based on the normal if the number of groups is small」、`hac-panel`「The data needs to be sorted ... stacked」，与 §3.6 行 1/行 4 一致；linearmodels（`group_debias` 公式 `g / (g - 1) * (n - 1) / n` 原文）、scikit-learn GroupKFold（「K-fold iterator variant with non-overlapping groups」原文）、Qlib（`open_cost: 0.0005 / close_cost: 0.0015 / min_cost: 5` 原文）、Zipline（`VolumeShareSlippage(_volume_limit=0.025, _price_impact=0.1)` 原文）四份 WebFetch 原文落盘重引比对一致。社区 2 条（Q205036 / Q65705171）维持 T3 风险提示，本步不升级。

#### 5.4.2 探针可重放（E1 复跑）

- 复跑命令：`python spec/p010-granularity-bias/probe_granularity.py`（seed=20261122、n_boot=200 固定）；复跑 exit 0；
- 复跑输出与首轮**全部字段逐位一致**：meta（months=39 / n_rows=200031 / n_stock_month=119287 / cap_month=5129）、`c` 2.9100349461927344（D）/ 2.7929927456412993（M）、四条 CI 端点、四条 CV 读数——可重放性成立，未发生静默漂移。

#### 5.4.3 代码锚点重验（Grep 逐条）

§3.1 的 7 条锚点全部命中：`SAMPLE_CAP = 200000`（panels L32）、股票×日样本行（L480-L483）、σ clip 链（L449-L483）、`_sample_indices` 等距抽样（L146-L151 + L631-L634）、iid bootstrap `rng.integers(0, n, size=n)`（runner L161-L176）、行序切折 `np.array_split(np.arange(n), folds)`（impact L151-L174）、`granularity="daily"` 元数据（panels L556 / L664-L666）；v392 DESIGN L38 非目标原文「不把样本粒度从『股票×日』改为『股票×月』（登记为 B9 遗留）」逐字一致。

#### 5.4.4 派生读数复算与修正（2 处）

| # | 项 | 原文 | 复算 | 处置 |
|---|---|---|---|---|
| F-R1 | D 口径 CI 宽度比 | +83.9% | **+83.84%**（0.0444856/0.0241986）→ 一位小数 **+83.8%** | 全文 +83.9% → **+83.8%**（原文系先用两位小数宽度相除产生的舍入漂移）；M 口径 +40.84% → +40.8% 原文已正确 |
| F-R2 | CV 差异表述 | +0.001%（D）/ +0.001%（M） | **D +0.0018%、M +0.0011%**（(row−month)/month），行序略**高**于按月 | 改写为精确值并注明方向与 §3.5 预期（行序偏低）相反；「无可测泄漏」结论不变 |

其余派生读数复算一致：Δc = −4.022020%（原文 −4.022% ✅）。

**复核结论**：**PASS_WITH_FIXES（已闭环）**——引用 9/9、官方文档 5/5、代码锚点 7/7、探针逐位重放；F-R1/F-R2 已订正入 §3.4/§3.5/§4.1-§4.4/U-3/U-4。E1 三项判定（点估计 −4.02% < 10% 不采纳 B、CI 宽度 +83.8% > 20% 采纳 C+A、CV 无可测泄漏）不受影响，§6.4 U-4 判定维持。

## 6. 对设计的输入

### 6.1 可用的技术方案

见 §4.2：A 保持+披露 / B 股票×月 / C 仅换 bootstrap+CV / D 双向聚类。设计阶段需给出主方案与被拒方案（含拒绝理由与代价）。

### 6.2 关键约束

- **默认输出零变更**：现行 `out/capacity_impact.json` SHA `82728CE1…` 是否必须保持，取决于方案 B 是否进入默认路径；若进入，需独立版本与新旧对照。
- **`panel_hash` 契约**：`_panel_hash` 已包含 `granularity: "daily"`（L556）与 `n_samples`；改粒度必然改变哈希，须在 DESIGN 登记变更。
- **39 月窗口**：不得改变窗口；月度聚合须处理「不足月」与停牌日。
- **数据限制**：BVC 无逐笔方向；不得把日频聚合伪称为逐笔冲击。
- **聚类数**：39 个月簇，属于少簇区间；CI 方法需保守（月聚类 bootstrap 或 t 分布修正）。

### 6.3 风险

- 方案 B 可能显著改变 `c` 与容量结论，影响既有对外读数；需保留新旧对照与回退点。
- 月度聚合的 `p` / `impact` 定义（均值 vs 加权）本身是设计选择，选错会引入新的口径偏差。
- 39 个月簇的 bootstrap 可能不稳定；需报告有效重抽样次数与 CI 宽度。

### 6.4 未决项登记（四元块）

- **U-1 月度聚合算子**
  - **判据**：DESIGN 明确 `p` / `impact` / `σ` 的月内聚合方式（均值 / 成交额加权 / 末值），并有 E1 对照读数
  - **触发条件**：Step 3 DESIGN 决策表；若 E1 显示均值与加权差异 >5%，必须显式裁决
  - **当前倾向**：`p` / `impact` 月内等权均值，`σ` 用月内日收益标准差（与现行 σ 定义一致）；本探针只测了等权均值，加权版本未测
  - **证据等级**：E1（等权均值读数已出；加权待补）
- **U-2 默认路径影响**
  - **判据**：DESIGN 明确所选方案是否改变默认 `capacity_impact.json`；若改变，给出 SHA 变更登记与新旧对照
  - **触发条件**：Step 3 DESIGN；或 Step 9 首次校准出现 SHA 变化
  - **当前倾向**：方案 C 只改 `capacity_calibration.json` 的 CI 与 `panel_hash` 之外的元数据，默认 `capacity_impact.json` 预期不变（`82728CE1…`）；若改 B 则需独立版本与新旧对照
  - **证据等级**：E1（现行 SHA 基线）
- **U-3 聚类口径**
  - **判据**：DESIGN 选定「月聚类 bootstrap」或「双向聚类」，并给出 39 月少簇下的 CI 修正方式
  - **触发条件**：Step 3 DESIGN
  - **当前倾向**：月聚类 bootstrap 为主（E1 CI 宽度 +83.8%），iid 仅作对照；双向聚类登记为可选敏感性
  - **证据等级**：E2（文献 + 探针）
- **U-4 采纳门槛**
  - **判据**：给出可机械判定的门槛（`|Δc|/c > 10%` 或 CI 宽度变化 >20%），未触发则走 A/C
  - **触发条件**：E1 探针读数回填后立即判定
  - **当前倾向**：**已按 E1 判定**——`|Δc|/c = 4.02% < 10%` → 不采纳 B；CI 宽度 `+83.8% > 20%` → 采纳 C（月聚类 bootstrap）+ A 披露
  - **证据等级**：E1（本文件 §3.4）

## 7. 参考文献

1. Cameron, A. C., Gelbach, J. B., & Miller, D. L. (2011). Robust Inference With Multiway Clustering. *Journal of Business & Economic Statistics*, 29(2), 238-249. https://doi.org/10.1198/jbes.2010.07136
2. Cameron, A. C., & Miller, D. L. (2015). A Practitioner's Guide to Cluster-Robust Inference. *Journal of Human Resources*, 50(2), 317-372. https://doi.org/10.3368/jhr.50.2.317
3. Driscoll, J. C., & Kraay, A. C. (1998). Consistent Covariance Matrix Estimation with Spatially Dependent Panel Data. *Review of Economics and Statistics*, 80(4), 549-560. https://doi.org/10.1162/003465398557825
4. Fama, E. F., & MacBeth, J. D. (1973). Risk, Return, and Equilibrium: Empirical Tests. *Journal of Political Economy*, 81(3), 607-636. https://doi.org/10.1086/260061
5. Frazzini, A., Israel, R., & Moskowitz, T. J. (2018). Trading Costs. SSRN Working Paper. https://doi.org/10.2139/ssrn.3229719
6. Gormley, T. A., & Matsa, D. A. (2014). Common Errors: How to (and Not to) Control for Unobserved Heterogeneity. *Review of Financial Studies*, 27(2), 617-661. https://doi.org/10.1093/rfs/hht047
7. MacKinnon, J. G., & Webb, M. D. (2018). The wild bootstrap for few (treated) clusters. *The Econometrics Journal*, 21(2), 114-135. https://doi.org/10.1111/ectj.12107
8. Petersen, M. A. (2009). Estimating Standard Errors in Finance Panel Data Sets: Comparing Approaches. *Review of Financial Studies*, 22(1), 435-480. https://doi.org/10.1093/rfs/hhn053
9. Thompson, S. B. (2011). Simple formulas for standard errors that cluster by both firm and time. *Journal of Financial Economics*, 99(1), 1-10. https://doi.org/10.1016/j.jfineco.2010.08.016

**官方文档与社区案例（检索日 2026-11-22）**：

10. statsmodels. RegressionResults.get_robustcov_results. https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.RegressionResults.get_robustcov_results.html
11. linearmodels. PanelOLS.fit. https://bashtage.github.io/linearmodels/panel/panel/linearmodels.panel.model.PanelOLS.fit.html
12. scikit-learn. GroupKFold. https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html
13. Qlib. Workflow Management. https://qlib.readthedocs.io/en/latest/component/workflow.html
14. Zipline. API Reference（VolumeShareSlippage）. https://zipline.ml4trading.io/api-reference.html
15. Cross Validated Q205036. https://stats.stackexchange.com/questions/205036
16. Stack Overflow Q65705171. https://stackoverflow.com/questions/65705171

---

**Review 签字**: _________ 日期: _________
