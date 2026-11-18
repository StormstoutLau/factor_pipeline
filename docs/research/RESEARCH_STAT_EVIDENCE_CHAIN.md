# RESEARCH 统计证据链 — P1 六项 (样本外 / DSR+PBO / L2 升级 / 规格曲线 / 效应量 / 组合层)

> **版本**: v1.2 (2026-11-18；v1.0 = 步骤 1-2 初稿；v1.1 = 独立复审 F1-F10 修正，见 §12；
> v1.2 = 设计阶段边界 purge 修正回填 dev=58，见 §13)
> **流程**: `docs/WORKFLOW_METHODOLOGY.md` §13.8 — 中任务（步骤 1-2-3-4-5-6-9-10；
> 步骤 1-2 产出本文件，步骤 3 设计在 `docs/private/`）
> **范围**: 多因子治理路线图 §5 P1 六项（L203-L220）；目标版本 **v3.7.0（候选）**
> **上游**: [路线图 §5 P1](../analysis/MULTIFACTOR_GOVERNANCE_ROADMAP.md#L203-L220) /
> [§6 G2 门禁](../analysis/MULTIFACTOR_GOVERNANCE_ROADMAP.md#L275-L288) /
> [§7 学术映射](../analysis/MULTIFACTOR_GOVERNANCE_ROADMAP.md#L291-L304) /
> [PROJECT_STATUS P1-A](../PROJECT_STATUS.md)
> **调研工具**: Crossref REST / 本地代码回溯（Grep + Read）/ 既有实测文档
> **说明**: Semantic Scholar 本机返回空（与 `RESEARCH_GOVERNANCE_BASE.md` 一致），
> 学术元数据以 Crossref + 既有调研（已回原文）为准；书籍页码与未能逐式取证的条目标 ⚠️。
> **本阶段只做调研**，不改生产代码、不改默认管线行为。

---

## §1 调研问题清单

| # | 问题 | 对应 P1 项 | 判定标准 |
|---|------|-----------|---------|
| Q1 | 样本外协议选 purged K-fold 还是 CPCV？purge/embargo 多宽？多路径如何聚合？ | ① | 月频 T=71 面板可运行；无标签泄漏；路径数/折界可复现 |
| Q2 | holdout 一次性锁定如何从「警告」升级为「阻断」？跨 batch 如何隔离？ | ① | S0 写入即锁；二次使用/跨 batch 复用被拒绝 |
| Q3 | DSR 的输入口径（逐期 SR、γ3/γ4、N/Ne、V[SR_n]）与阈值如何定？ | ② | 与 Bailey-LdP (2014) 公式一致；概率语义；阈值预注册 |
| Q4 | PBO/CSCV 的 S 如何选？T 不整除 S 怎么办？指标口径？ | ② | T=71 下可行 S 集合明确；结果可复现；敏感性可披露 |
| Q5 | L2 多重检验如何升级？FDR q 与 FWER p 如何分轨？GLX 是否纳入？ | ③ | 同一 family 不混用；分列报告；GLX 限制显式披露 |
| Q6 | 规格曲线如何做联合推断？现有日志缺什么数据？ | ④ | S3 能输出 curve + joint p，或声明单一规格理由 |
| Q7 | 效应量 + CI 强制到什么粒度？λ/IC/Sharpe 各用什么 CI？ | ⑤ | S3 记录强制 effect_metric/effect_size/ci；CI 与 p 口径一致 |
| Q8 | 组合层 K 个组合如何登记为独立 variant？归入哪个 family？ | ⑥ | S4 组合不跳过校正；分母可追溯 |
| Q9 | 月频 T=71、Barra 2023-07 后断档对上述方法有何硬约束？ | 全部 | 明确「可行 / 受限 / 不可行」并给替代方案 |
| Q10 | 现有代码哪些可直接复用、哪些语义缺陷必须绕开？ | 全部 | 每条有文件行号 + 处置 |

---

## §2 学术文献调研

### 2.1 样本外协议：purged K-fold / CPCV + embargo

| 文献 | 出处 / DOI | 关键定义 | 状态 |
|------|-----------|---------|------|
| López de Prado (2018) | *Advances in Financial Machine Learning*, Wiley, Ch.7（purged CV）/ Ch.12（CPCV） | 标签区间与测试折重叠的训练样本必须 purge；测试折后加 embargo；CPCV 用 `C(N,k)` 条路径生成 OOS 分布 | ⚠️ 书籍无 DOI，章节定位为通行引用 |
| Bergmeir & Benítez (2012) | *Information Sciences* 191:192-213 | 时间序列交叉验证在「模型仅用过去信息」时的可用条件 | ⚠️ 本次未逐项查 Crossref，仅作方法背景 |

**口径定义（月频、1 期标签）**：

- 标签：`r_t = P_{t+1}/P_t − 1`，标签区间 `(t, t+1]`；测试折覆盖 `[a, b]`。
- **Purge**：训练样本 `t` 的标签区间与测试折标签区间重叠则剔除。对 1 期标签，严格半开区间下
  `t=a−1` 的标签止于 `a`，与测试标签并集 `(a, b+1]` 不重叠（半开区间），理论 purge 可为 0；
  但 `r_{a−1}` 与 `r_a` 共用价格 `P_a`，且特征可能跨期，**保守实现取 1 期**。
  该口径必须在设计阶段固定并写单测（[待定] E2）。
- **Embargo**：测试折终点 `b` 之后剔除 `h` 期（月频 `h=1`），防止序列相关泄漏。
- **CPCV**：`T` 分 `N` 个连续组，取 `k` 组为测试、其余为训练（训练集再 purge/embargo）；
  路径数 `C(N,k)`；每条路径把 OOS 段拼接为一条净值曲线。
  与 walk-forward 不同，CPCV 允许「用未来数据训练、过去数据测试」，只用于**评估**，
  不用于实盘信号；报告必须披露这一点。
- **多路径聚合**：路径间不独立（训练集重叠），不能把 `C(N,k)` 条路径当独立样本做 t 检验；
  应报告路径分布（中位数/分位）或按路径分别做 DSR/PBO，聚合口径 [待定]（E2）。

**陷阱**：

1. purge 去的是**标签重叠**，不自动处理特征窗口重叠；若特征用 12 月窗口，需单独评估。
2. 月频只有 71 个标签（开发样本 58，扣 holdout 并含 2024-12 边界 purge，见 §13），CPCV 的 `N` 不宜过大：`N=6` 裁到 54 后每组 9 期，
   已接近下限；`N=5`（裁到 50，每组 10 期）是更保守的备选。
3. CPCV 路径数增长快（`C(10,2)=45`），需与计算预算、报告可读性平衡。

### 2.2 DSR（Deflated Sharpe Ratio）

| 文献 | 出处 / DOI | 关键公式 | 状态 |
|------|-----------|---------|------|
| Bailey & López de Prado (2014) | *Journal of Portfolio Management* 40(5):94-107, DOI 10.3905/jpm.2014.40.5.094 | 见下 | ✅ Crossref + 原文公式 |

```
DSR = Φ( (SR̂ − SR0) · √(T−1) / √(1 − γ3·SR̂ + ((γ4−1)/4)·SR̂²) )

SR0 = √V[SR_n] · ( (1−γ)·Φ⁻¹(1−1/N) + γ·Φ⁻¹(1−1/(N·e)) )
γ   = 0.5772156649（Euler-Mascheroni）
```

**口径陷阱**（与 `RESEARCH_GOVERNANCE_BASE.md` §2.2 一致，本次补充月频换算）：

1. `SR̂` 与 `SR0` 是**逐期（per-bar）Sharpe**，不是年化。月频年化 SR 需除以 `√12`：
   组合层年化 SR 0.94 → 逐期 0.271；0.77-1.05 → 0.222-0.303。
2. `γ4` 是**非超额峰度**（正态 = 3）；`γ3` 是偏度。
3. DSR 输出是**概率**（真实 SR 超过 SR0 的置信度），不是 p 值；门禁阈值预注册（示例 >0.95）。
4. `N` 是**独立试验数**；试验相关时需用有效试验数 `Ne` 或做 `N` 敏感性。
   `N` 必须来自台账 `n_trials`（全部已执行试验），不能只数「进入报告的变体」。
5. `V[SR_n]` 是各试验 Sharpe 的截面方差；未知时可用零假设抽样方差 `1/(T−1)` 作最小 deflator，
   或用试验集内 trial SR 的经验方差（是否更保守取决于试验集离散度，不必然）；
   两种口径需在设计中二选一并披露。
6. `T` 是**评估样本**的收益期数（开发样本，锁定 holdout 扣除并做 1 期边界 purge 后为 58；未锁定 holdout 的
   回顾批次为 71），不是年数；`T` 小 → 分母大 → DSR 天然偏低，弱因子可能不通过，
   这是**诚实结果**，不得事后调阈值。评估样本不得包含已锁定 holdout 的月份
   （见 §2.3 陷阱 7 与 §7 U11）。
7. `SR0` 用 `Φ⁻¹(1−1/N)` 与 `Φ⁻¹(1−1/(N·e))`，不是 `1−1/(2N)`。
8. DSR 与 PSR（Probabilistic Sharpe Ratio）共用分母，但 `SR0` 的来源不同：
   DSR 用 `N` 个试验的极值分布，PSR 用外部基准 `SR*`。`N=1` 时 `Φ⁻¹(1−1/N)=−∞`，
   `SR0→−∞`、`DSR≡1`，估计完全退化，不能当作 PSR 使用。

### 2.3 PBO（Probability of Backtest Overfitting）/ CSCV

| 文献 | 出处 / DOI | 关键定义 | 状态 |
|------|-----------|---------|------|
| Bailey, Borwein, López de Prado & Zhu (2017) | *Journal of Computational Finance* 20(4):39-69, DOI 10.21314/JCF.2016.322 | CSCV 组合对称交叉验证；IS 最优策略的 OOS 相对秩 `ω`；`λ=log(ω/(1−ω))`；`PBO=P(λ≤0)` | ✅ Crossref + 原文公式 |

**算法**：

1. 把 `T` 期切成 `S` 个**连续**等长块（保持时序/自相关结构）。
2. 枚举 `C(S, S/2)` 个对称切分：一半为 IS，另一半为 OOS。
3. 每个切分内，按 IS 绩效选出最优策略 `n*`；计算它在 OOS 的**相对秩**
   `ω = rank_OOS(n*) / (N+1)`（并列取平均秩）。
4. `λ = log(ω/(1−ω))`；`PBO = #(λ≤0) / #splits`，即 OOS 落到中位数以下的频率。

**门禁阈值**：预注册（路线图示例 `PBO<0.1`，不是 0.5）；阈值与 `S` 一起在 S0 固定。

**口径陷阱**：

1. `S` 必须为偶数；原文假设 `T` 可被 `S` 整除。**可行 S 集合是场景化的**：
   ① 全样本 T=71（素数）→ 裁到 70 → 可行 `S ∈ {2,10,14}`（`S=70` 的 `C(70,35)` 不可计算）；
   ② **扣 12 月锁定 holdout 与 1 期边界 purge 后开发样本 T=58 → 裁到 56 → 可行 `S ∈ {2,4,8,14}`**
   （`S=28` 的组合数 4×10⁷ 不可计算；`S=10` 需另裁到 50）。
   `S=8/12` 在 T=70 下无法等分，必须采用余数策略（末块不等长/丢弃余数）或改用可整除的 `S`。
2. `N` 必须是**完整试验集**（含失败试验），不能只放候选赢家；否则 PBO 系统性偏低。
   `N` 条策略可以高度相关（如同一因子的不同池），PBO 仍定义在搜索集上，
   但报告需披露相关性，不能把它当独立试验数。
   **不要把同一策略的不同费率/成本假设当独立策略**：`fee=0` 在 IS 中必然占优，
   会系统性低估 PBO；费率应固定或作为稳健性维度分层报告。
3. IS/OOS 必须用**同一绩效指标**（常用 Sharpe）；不能 IS 用 IC、OOS 用收益。
4. PBO 评估的是**搜索过程**，不是获胜策略本身；低 PBO 不替代 DSR/多重检验。
5. 对 `S`、`N`、`T` 敏感；`S` 必须预注册并做敏感性（本仓建议：开发样本裁到 56 后
   `S=8` 主（每块 7 期）、`S=14` 敏感（每块 4 期）；若坚持 `S=10` 需裁到 50，损失 9 个月；
   `S=12` 在开发样本需裁到 48，仅作稳健性附录）。
6. CSCV 的块必须连续；随机打乱会破坏自相关结构，结果不可用。
7. **评估样本与 holdout 隔离**：CSCV/DSR 只能使用开发样本；已锁定 holdout 的月份必须
   整段剔除——在 holdout 上计算任何评估量即视为烧掉 holdout（§7 U11）。

### 2.4 规格曲线（Specification Curve）与联合推断

| 文献 | 出处 / DOI | 关键定义 | 状态 |
|------|-----------|---------|------|
| Simonsohn, Simmons & Nelson (2020) | *Nature Human Behaviour* 4(11):1208-1214, DOI 10.1038/s41562-020-0912-z | 汇总全部「合理规格」；按效应大小排序展示；对整条曲线做联合推断 | ✅ Crossref；联合检验统计量细节 ⚠️ 未逐式取证 |

**要求**：

- **规格全集**：所有合理规格（如 3 种中性化 × 2 种缩尾 × 2 个样本窗）都必须纳入，
  不能只报显著规格；缺失规格 = 选择性报告。
- **描述性输出**：中位效应、方向一致比例、曲线图/表。
- **联合推断**：零假设「所有规格均无效应」；常用做法是对结果/处理变量做置换
  （或按时间/股票 cluster bootstrap），每次重算整条曲线，统计量取中位效应或
  「显著且方向正确的规格占比」，`joint p = 置换分布中 ≥ 观测统计量的比例`。
  具体统计量与置换层级需回原文推断章节复核（§7 待核实 U2）。
- **数据要求**：每条规格必须有**同一批样本上的逐期收益/IC 序列**，否则无法做置换；
  仅存 `p_value` 与 `ic` 摘要不够（见 §4 C1）。
- **S3 强制**：S3 证据包必须附 spec curve；若只跑单一规格，需书面声明理由
  （路线图 §5 P1-4），否则视为 forking paths 未披露。
- **陷阱**：规格网格必须在看结果前固定（或至少全量枚举）；不同规格用不同样本期
  属于另一个维度，需显式声明；联合显著不等于每个规格都显著。

### 2.5 L2 多重检验升级与 GLX

| 文献 | 出处 / DOI | 关键点 | 状态 |
|------|-----------|-------|------|
| Benjamini & Hochberg (1995) | *JRSS-B* 57(1):289-300 | BH step-up，控制 FDR | ✅ 通行定义 |
| Romano & Wolf (2005) | *Econometrica* 73(4):1237-1282, DOI 10.1111/j.1468-0262.2005.00615.x | bootstrap stepdown，控制 FWER；输出校正 p | ✅ Crossref |
| White (2000) | *Econometrica* 68(5):1097-1126 | Reality Check，data snooping | ✅ 通行定义 |
| Hansen (2005) | *JBES* 23(4):365-380, DOI 10.1198/073500105000000063 | SPA，studentize + recentering | ✅ Crossref |
| Giglio, Liao & Xiu (2021) | *Review of Financial Studies* 34(7):3456-3496, DOI 10.1093/rfs/hhaa111（"Thousands of Alpha Tests"） | 因子模型调整的 alpha 多重检验；处理遗漏因子/弱因子 | ✅ Crossref 复核（2026-11-18，页码 3456-3496）；实现细节 ⚠️ 未逐式取证 |
| Harvey, Liu & Zhu (2016) | *RFS* 29(1):5-68 | 多重检验下 `t>3` 报告基准 | ✅ 通行定义 |

**分轨原则**（路线图 §6 G2 / 复审 F3）：

- FDR 轨：BH/BY 输出 **q 值**；FWER 轨：Bonferroni/Holm/Romano-Wolf/White/Hansen 输出
  **校正 p 或联合 p**。两者不得混用、不得互相替代。
- 同一 family 预注册选一轨；报告分列 `q_value` 与 `adjusted_p`。
- GLX 是**可选升级**：需要因子模型（Barra 或自建）。本仓 Barra 2023-07-31 后断档，
  全样本 GLX 不可行；只能限定 2020-01→2023-05 子样本，或用 4 因子自建模型并披露。
  默认路径**不启用 GLX**。

### 2.6 效应量与置信区间

| 文献 | 出处 / DOI | 用途 | 状态 |
|------|-----------|------|------|
| Newey & West (1987) | *Econometrica* 55(3):703-708 | HAC 标准误（λ̂ 均值） | ⚠️ 页码通行引用，DOI 未逐项核 |
| Lo (2002) | *Financial Analysts Journal* 58(4):36-52, DOI 10.2469/faj.v58.n4.2453 | Sharpe 的统计标准误；自相关下的修正 | ✅ Crossref |
| Bailey & López de Prado (2012) | *Journal of Risk* 15(2):3-44, DOI 10.21314/JOR.2012.255 | Sharpe 有效前沿 / 最小跟踪记录长度 | ✅ Crossref |
| Politis & Romano (1994) | *JASA* 89(428):1303-1313, DOI 10.1080/01621459.1994.10476870 | stationary bootstrap，用于 IC/Sharpe 的 CI | ✅ Crossref |
| Nosek et al. (2018) | *PNAS* 115(11):2600-2606, DOI 10.1073/pnas.1708274114 | 预注册与一次性 holdout | ✅ Crossref |

**三件套要求**：p/q + 效应量 + CI，缺一不可。三条口径：

| 效应量 | 推荐 CI | 本仓基座 |
|--------|---------|---------|
| `lambda_mean`（FM 溢价均值） | HAC（Newey-West） | `PremiumEstimator.estimate_with_errors`（已 Stata 对拍） |
| `ic_mean`（Rank IC 均值） | HAC 或 stationary bootstrap | 需新写（IC 序列逐月） |
| `sharpe`（组合/因子 SR） | Lo (2002) SE 或 stationary bootstrap | 需新写 |

**陷阱**：

1. CI 必须与效应量同口径、同抽样单位；不能对时序溢价用截面 HC3。
2. `FactorSignificanceTest` 的 CI 用 `1.96·SE` 正态近似，p 值却用 t 分布（§4 C16）；
   小样本下两者不一致，不能直接作为 S3 强制 CI。
3. Sharpe 在非正态/自相关下，正态近似 CI 偏窄；优先 bootstrap 或 Lo 修正。

### 2.7 预注册与 holdout 一次性

- 预注册（Nosek 2018）：规格、阈值、指标、样本窗在**看数据前**固定；变更需记录偏离。
- holdout 一次性：同一 holdout 窗口只能评估一次；跨 batch 复用等于二次窥探。
- 路线图要求：S0 写入 `holdout_locked_at`，后续不得更改；不同 `batch_id` 不得共用
  同一 holdout 窗口，或改用 CPCV 多路径避免复用。
- 现有实现只对「同因子 + 同 test_set_id + run_type='final'」给警告（§4 C3），
  无全局锁、无跨 batch 校验、无时间顺序校验。

---

## §3 社区与工程实践调研

### 3.1 实现对照

| 方案 | 提供内容 | 许可证/依赖 | 本仓结论 |
|------|---------|------------|---------|
| mlfinlab（Hudson & Thames） | PurgedKFold、CombinatorialPurgedKFold、CSCV/PBO 估计 | 商业许可（开源版本受限） | ❌ 不引入；仅作语义对照（E4） |
| scikit-learn `TimeSeriesSplit` | 时间序列切分 | BSD | ⚠️ 无 purge/embargo，单独不够用 |
| statsmodels `multipletests` | BH/Bonferroni/Holm | BSD | ✅ 本仓已有等价实现，无需引入 |
| `pypbo`（R） | CSCV/PBO | GPL 生态 | ⚠️ 语言不通；只作算法参照 |
| 零散 `deflated_sharpe` 片段 | DSR | 口径不一（N/V[SR] 处理差异大） | ❌ 不复制；按原文自实现 |

**结论**：新增实现全部用 `numpy/scipy/pandas`，不新增依赖；DSR/PBO 用原文公式 +
独立 Monte Carlo + 现有 Stata 对拍框架做三重验证。

### 3.2 本仓适配候选（设计输入，非决策）

| 能力 | 候选落点 | 理由 |
|------|---------|------|
| purged K-fold / CPCV / holdout 注册表 | 新模块 `backtest/cross_validation.py`（候选） | 与现有 engine/factor_metrics 解耦，纯计算可测 |
| DSR / PBO(CSCV) | 新模块 `backtest/overfitting.py`（候选） | 输入是收益矩阵/试验 SR 向量，不依赖数据层 |
| 规格曲线联合推断 | 扩展 `backtest/specification_logger/` | 复用 append-only 思路，但需 schema v2 |
| 组合层 variant 登记 | `multiple_testing_ledger` 接线 | `TrialRecord.stage` 已有；`FamilySpec` 需增 stage 或一致性校验 |
| 证据字段与门禁校验 | `backtest/governance.py` | `dsr/pbo/oos_metric/effect_*` 字段已预留 |
| 独立对拍 | `benchmarks/stata_econ_crosscheck.py` | `P1_CASES=("dsr","pbo")` 已是 SKIP 占位 |

### 3.3 接线点（S0 → G2 → S4）

| 阶段 | 动作 | 落点 |
|------|------|------|
| S0 | 预注册 family/holdout；写 `holdout_locked_at` | `PreRegistration` + holdout 注册表 → `GovernanceRecord` |
| S1-S2 | 数据快照、arm/config | 既有 |
| S3 | 效应量 + CI + spec curve + q/p | `GovernanceRecord` + ledger + spec logger |
| G2 | q/p 分轨 + DSR 概率 + PBO + OOS 同向 | `gate_status["G2"]`（当前只记录，无代码评估器） |
| S4 | 组合登记为独立 variant，进同一/新 family | ledger `stage="portfolio"`（需校验） |

### 3.4 计算预算（估算，E4）

- DSR：`O(N)`，N≤数百，可忽略。
- PBO：`C(S,S/2)` 个切分 × `N×T` 绩效计算；开发样本裁到 56：`S=8` → C(8,4)=70 × N×56，
  `S=14` → C(14,7)=3432 × N×56，N≤100 时均在秒级内。
- CPCV：15 条路径 × 组合/因子评估；与现有回测同量级。
- 规格曲线置换：`B=1000` × 全规格重算；若每条规格只算 IC/收益均值，`58×N_spec×B`
  （开发样本）在秒级；若每条规格重跑完整回测，需缓存中间结果。
- 以上为复杂度估算，设计/实施阶段以实测为准。

---

## §4 本仓库代码核对

> 锚点均为当前 HEAD（v3.6.0）实测行号；方法：Grep + Read。

| # | 文件:行 | 现状 | 缺口/风险 |
|---|---------|------|----------|
| C1 | [spec_log.py L40](../../backtest/specification_logger/spec_log.py#L40) | `log_run` append-only JSONL；8 位 SHA1（timestamp 不参与哈希） | 无 schema 版本/命名空间/签名；8 位哈希碰撞风险；仅存 `ic`/`p_value` 摘要，**无逐规格收益序列** |
| C2 | [spec_log.py L76](../../backtest/specification_logger/spec_log.py#L76) | `get_specification_curve` 返回 specifications/results/p_values/median_effect/consistency | 无联合推断；缺失 `ic`/`p_value` 静默变 NaN；不能区分「未跑该规格」与「结果缺失」 |
| C3 | [spec_log.py L106](../../backtest/specification_logger/spec_log.py#L106) | `enforce_test_set_once` 检查同因子 + 同 `test_set_id` + `run_type='final'` | **只返回 warning，不阻断**；无全局锁；无跨 batch/跨因子校验；无时间顺序校验 |
| C4 | [spec_log.py L134](../../backtest/specification_logger/spec_log.py#L134) | `_load_records` 逐行 JSON 解析，坏行静默跳过 | 无校验和；无文件锁；并发写可能交错 |
| C5 | [spec_curve.py L28](../../backtest/specification_logger/spec_curve.py#L28) | `SpecificationCurve.analyze` 与 C2 逻辑重复 | 两处实现易漂移；同样只做中位数/方向一致性 |
| C6 | [pre_registration.py L30](../../backtest/specification_logger/pre_registration.py#L30) | `commit` 写 JSONL，8 位 SHA1；timestamp 参与哈希 | 同一 spec 重复提交得到不同 hash；无命名空间/版本 |
| C7 | [pre_registration.py L53](../../backtest/specification_logger/pre_registration.py#L53) | `verify_compliance` 只比较 committed_spec 的键 | actual 多键被忽略；committed 值为 `None` 时缺省也通过；无时间顺序/阈值方向校验 |
| C8 | [multiple_testing_ledger.py L91-L101](../../backtest/multiple_testing_ledger.py#L91-L101) | `FamilySpec` 有 `n_trials_expected`、`holdout_id` | 无 `stage` 字段；不校验 batch 全因子是否纳入；`holdout_id` 仅存不校验 |
| C9 | [multiple_testing_ledger.py L571](../../backtest/multiple_testing_ledger.py#L571) | `apply` 按预注册轨校验方法；L613-L638 三分母（n_trials/n_testable/n_hypotheses） | 分母逻辑可复用；组合 variant 需人工登记；无 stage/holdout 一致性检查 |
| C10 | [multiple_testing_ledger.py L772-L785](../../backtest/multiple_testing_ledger.py#L772-L785) | `_persist_result` 用 family fingerprint + method + alpha + confirmatory ids 生成 `result_id` 去重 | 可复用；但只纳入 confirmatory，portfolio 组合需正确设 kind/stage |
| C11 | [governance.py L371-L372](../../backtest/governance.py#L371-L372) | `split_id`、`holdout_locked_at` 字段存在；后者仅做时间归一化 | `split_id` 为自由字符串；`holdout_locked_at` 无注册表/唯一性校验 |
| C12 | [governance.py L399-L401](../../backtest/governance.py#L399-L401) | `dsr`、`pbo`、`oos_metric` 结果字段已预留 | 无范围校验（DSR/PBO 应在 [0,1]）；`oos_metric` 为自由 dict |
| C13 | [governance.py L491-L522](../../backtest/governance.py#L491-L522) | CI 顺序、分母单调、S0 必填 `holdout_locked_at`、S3/FINAL/PORTFOLIO 必填 effect_metric/effect_size/ci 且 p/q/adjusted_p 至少一项 | 已有硬校验；但 `dsr/pbo` 不在必填项；G2 无代码评估器（`gate_status` 只是记录 payload） |
| C14 | [governance.py L539-L542](../../backtest/governance.py#L539-L542) | portfolio/recheck/retired 必须有 `parent_id` | 无法强制「组合进 family 校正」 |
| C15 | [multiple_testing.py L52/L113/L204/L581/L808/L876](../../backtest/multiple_testing.py#L52) | BH/Bonferroni/BY/Romano-Wolf/White RC/Hansen SPA 计算核齐全；类在 L957/L1240 | 可直接复用；无 GLX |
| C16 | [factor_significance.py L260-L283](../../backtest/factor_significance.py#L260-L283) | 双重/弹性网 alpha 检验；HC3 SE；CI 用 `1.96·SE`，p 值用 t 分布 | CI 与 p 口径不一致；HC3 非时序 HAC，不适合溢价均值 CI |
| C17 | [factor_health/__init__.py L65](../../modules/factor_health/__init__.py#L65) | `estimate_with_errors` 返回 `premium_mean` + HAC SE + CI | 可直接作为 `lambda_mean` 效应量/CI 基座 |
| C18 | [stata_econ_crosscheck.py L50-L55](../../benchmarks/stata_econ_crosscheck.py#L50-L55) | `CASES` 含 `dsr`/`pbo`，`P1_CASES=("dsr","pbo")`；L623-L629 固定 SKIP「P1 未实装」 | 现成扩展点：实现后可接独立对拍/MC |
| C19 | 测试覆盖 | `test_specification_logger.py` 19 项（日志/曲线/预注册/一次性/BY/管线钩子）；`test_multiple_testing_ledger.py` 11 个测试函数（三分母/轨道/去重，T23/T24 参数化） | **无 DSR/PBO/CPCV/purge/embargo 测试** |

**Grep 结论**：`backtest/` 下无 DSR/PBO/CSCV/purged/embargo 实现；命中仅为
`governance.py` 字段名、`stata_econ_crosscheck.py` 用例名、`threshold_drift_monitor.py`
文献引用。与路线图 §7「仅文档引用，无实现」一致。

---

## §5 数据事实与可行性

| # | 事实 | 证据 |
|---|------|------|
| F1 | 月频面板 73 个月末，**有标签 71 个月**（2020-02 → 2025-12） | [PORTFOLIO_BACKTEST_VERIFICATION §头部](../analysis/PORTFOLIO_BACKTEST_VERIFICATION.md) |
| F2 | 12 因子 × 三分段；BH 通过 4 个非自指因子；组合层 4 因子 + 复合 × 2 池 × 4 费率 | 同上 / [MULTIFACTOR_MULTIYEAR_VERIFICATION](../analysis/MULTIFACTOR_MULTIYEAR_VERIFICATION.md) |
| F3 | 全市场多空年化 SR 0.77-1.05，复合 0.94；沪深300 池内失效 | 同上 |
| F4 | Barra 止于 2023-05-31、行业止于 2023-06-13；2023-07-31 后不可做风格/行业中性化 | [PROJECT_STATUS L108](../PROJECT_STATUS.md#L108) |
| F5 | `market_value.csv` 止于 2026-01-23；仅末月 `turnover_1m` 分母 stale，末月不进绩效 | 同上 |
| F6 | **T 整除约束场景化**：全样本 71（素数）→ 裁到 70 → 可行 `S ∈ {2,10,14}`；**扣 12 月 holdout 与 1 期边界 purge 后开发样本 58 → 裁到 56 → 可行 `S ∈ {2,4,8,14}`**（`S=10` 需另裁到 50）；`S=70/28/56` 的组合数不可计算 | 本次算术核对 |
| F7 | CPCV `k=2`：全样本 71 → 裁到 66（`N=6`，每组 11 月）；**开发样本 58 → 裁到 54（`N=6`，每组 9 月，接近噪声下限）**；备选 `N=5` 裁到 50；均 15 条路径；purge/embargo 各 1 期 | 本次推算 |
| F8 | 月频逐期 SR = 年化 SR / √12：复合 0.94 → 0.271；单因子 0.77-1.05 → 0.222-0.303 | 本次换算 |
| F9 | 12 个月 holdout → 剩余 59 个标签；**再扣 1 期边界 purge（2024-12）→ dev=58**（v1.2，见 §13）；跨 batch 隔离需全局注册表 | 本次推算 + 设计修正 |
| F10 | 组合层规格网格（2 池 × 4 费率 = 8）已在验证脚本中枚举；PBO 的 N 候选：组合层 5 策略 × 2 池 = 10（费率固定/分层，不进入 N），因子层 12 因子 × 规格网格（需预注册） | [verify_portfolio_backtest.py](../../scripts/verify_portfolio_backtest.py) |

**可行性结论**：

| 能力 | 结论 | 依据 |
|------|------|------|
| CPCV / purged K-fold | ✅ 可行 | 开发样本 58 → 裁到 54（N=6、k=2、15 路径；备选 N=5）；purge/embargo 各 1 期 |
| DSR | ⚠️ 可计算，但**检验力低** | 逐期 SR≈0.27、开发样本 T=58；弱因子可能 DSR<0.95，属诚实结果 |
| PBO/CSCV | ✅ 可行，S 受限 | 开发样本 58 → 裁到 56：S=8 主（每块 7 期）、S=14 敏感（每块 4 期）；S=10 需另裁到 50；S=12 不可行 |
| 规格曲线描述统计 | ✅ 可行 | 现有 logger 可扩展 |
| 规格曲线联合推断 | ⚠️ 需补数据 | 必须持久化逐规格收益/IC 序列；现有摘要不够 |
| GLX | ⚠️ 受限 | Barra 断档；只能子样本或自建 4 因子模型 |
| 效应量 + CI | ✅ 可行 | λ 用 `PremiumEstimator`；IC/SR 需新写 HAC/bootstrap |

---

## §6 调研结论与设计约束

### 6.1 可直接复用

1. `multiple_testing` 的 BH/BY/Bonferroni/Romano-Wolf/White/Hansen 计算核（C15）；
2. `MultipleTestingLedger` 的三分母、轨道校验、`result_id` 去重（C9/C10）；
3. `GovernanceRecord` 的 `effect_metric/effect_size/ci` 字段与 S0/S3 必填校验，
   以及 `dsr/pbo/oos_metric` 预留字段（C11-C13；`dsr/pbo` 当前非必填）；
4. `PremiumEstimator.estimate_with_errors` 的 HAC 效应量/CI（C17）；
5. `SpecificationLogger` 的 append-only 思路（不复用其哈希与 schema，C1）；
6. `stata_econ_crosscheck` 的 `P1_CASES` 占位与 fixture 对拍模式（C18）。

### 6.2 必须修正或绕开的语义

| # | 问题 | 处置建议 |
|---|------|---------|
| D1 | 规格日志只存摘要，无法联合推断 | schema v2：新增 `spec_id`、`returns`/`ic_series` 持久化（或旁路 parquet）；保留旧字段兼容 |
| D2 | 两处均用 8 位 SHA1；`PreRegistration` 还把 timestamp 入哈希，身份不稳定 | 改用 SHA256 + canonical payload（对齐 `governance`）；timestamp 移出哈希 |
| D3 | `enforce_test_set_once` 只警告、按因子隔离 | 改为全局 holdout 注册表（键：窗口 hash + universe + batch），重复使用**拒绝**；S0 写入 `holdout_locked_at` |
| D4 | `PreRegistration.verify_compliance` 漏检多键 / `None` 缺省 / 时间顺序 | 双向键比较 + 提交时间早于运行时间 + 阈值方向校验 |
| D5 | `FamilySpec` 无 stage；组合 variant 可能漏登记 | 增加 `stage` 或校验 `TrialRecord.stage` 与 family 一致；S4 组合必须显式 family |
| D6 | `governance` 无 `dsr/pbo` 范围校验，G2 无代码评估器 | 增加 `[0,1]` 校验；G2 评估器可先做「计算并记录」，不自动阻断 |
| D7 | `FactorSignificanceTest` CI 用 1.96 而 p 用 t；HC3 非 HAC | 不修改该模块；S3 强制 CI 改用 `PremiumEstimator`/bootstrap |
| D8 | PBO/CPCV 的 T 不整除 S/N，且评估样本须扣除锁定 holdout 与 1 期边界 purge（T=58） | 预注册「开发样本裁到 56：S=8 主 / S=14 敏感；CPCV 裁到 54：N=6」；余数策略写进设计与单测 |
| D9 | DSR 的 N 与台账 `n_trials` 可能不一致 | 以 ledger `n_trials` 作为 `N` 的保守上界；另报 `Ne` 或 `N` 敏感性并披露 |

### 6.3 明确不做

1. 不引入 mlfinlab / pypbo 等依赖；不复制口径不明的 DSR 片段；
2. 不做自动策略搜索/自动调参；DSR/PBO 只做**评估与门禁证据**；
3. 不在 Barra 断档期强行做全样本 GLX；
4. 不改变默认管线行为：新能力默认关闭/显式调用，保持既有 golden 与回归零变更；
5. 不把 DSR/PBO 当作唯一门禁；必须与 q/p、OOS 同向、效应量/CI 联合使用；
6. 不在 holdout 上反复评估；不为通过门禁而事后调整阈值或 S。

### 6.4 步骤 3 设计输入清单

| # | 设计项 | 需拍板的内容 |
|---|--------|-------------|
| E1 | 模块边界 | `cross_validation.py` / `overfitting.py` 是否新建；是否复用 engine |
| E2 | 样本外协议 | purged K-fold vs CPCV；N/k；purge/embargo 宽度；路径聚合口径 |
| E3 | holdout 锁 | 注册表存储（JSONL/DuckDB）；键设计；拒绝语义；迁移策略 |
| E4 | DSR | 评估样本=开发样本（holdout 剔除）；N/Ne 取值；V[SR_n] 口径与 γ3/γ4 估计式；逐期 SR 换算；阈值 0.95 的适用范围 |
| E5 | PBO | 评估样本=开发样本；S 主值/敏感性；T 裁剪与余数策略；N 的完整试验集定义 |
| E6 | 规格曲线 | schema v2 字段；联合检验统计量与置换层级（置换次数 B 与 seed 预注册）；S3 强制/豁免规则 |
| E7 | 效应量/CI | 三口径的 CI 方法；`effect_metric` 白名单扩展；报告格式 |
| E8 | 组合层 | 组合 variant 的 `variant_id`/`kind`/`stage`；family 归属规则 |
| E9 | 治理门禁 | G2 评估器是否落地；DSR/PBO 必填阶段；失败动作（block/downgrade） |
| E10 | 验证 | MC 真值（已知 SR/过拟合）；Stata 对拍扩展；golden 零变更回归；TDD 清单 |

---

## §7 待核实项与风险

| # | 项 | 原因 | 处置 |
|---|----|------|------|
| U1 | AFML Ch.7/Ch.12 页码与原文措辞 | 书籍无 DOI，未逐页取证 | 只引章节与算法，不引页码；设计时以原文 PDF 复核 |
| U2 | 规格曲线联合检验的精确统计量/置换层级 | 本次只核到 DOI 与摘要级定义 | 设计前回原文推断章节复核；未取证前标 ⚠️ |
| U3 | GLX 的检验统计量与实现细节 | 未逐式取证 | 默认不启用；若启用，限定子样本并披露 |
| U4 | PBO/CPCV 的余数策略（T 不整除 S/N） | 原文假设可整除，社区实现不一 | 设计阶段二选一（裁剪 vs 不等长末块）并单测；开发样本 58 → 56（PBO）/54（CPCV） |
| U5 | DSR 的 `Ne` 估计与 `V[SR_n]` 口径 | 试验相关时无唯一解 | 主口径 + 敏感性并披露；`n_trials` 作保守上界 |
| U6 | CPCV 路径聚合口径 | 路径不独立 | 报告分布而非单点；聚合规则写入设计 |
| U7 | holdout 注册表持久化位置 | 现有 JSONL 与 DuckDB 并存 | 设计阶段定；优先复用 ledger 的 DuckDB 连接 |
| U8 | 组合 variant 的 family 归属 | 路线图允许「同一 family 或新 family」 | 设计阶段定规则：同批组合进新 family，跨批进同 family 需预注册 |
| U9 | T=71 下 DSR 的检验力 | 弱因子可能不通过 | 不调阈值；报告「概率 + N 敏感性 + 不通过」为诚实结论 |
| U10 | 规格网格的事前固定 | 事后枚举会引入 forking paths | 设计阶段写死网格；执行时只允许预注册偏离 |
| U11 | DSR/PBO/spec curve 与锁定 holdout 的样本隔离 | 评估量若含 holdout 月份即烧掉 holdout | 三者仅用开发样本（T=58，含边界 purge）；holdout 只做一次性终评并写入 `oos_metric`（§12 F1、§13） |
| U12 | γ3/γ4 在月频 T=58 下的样本估计噪声 | 高阶矩小样本估计不稳 | 设计固定估计式（样本偏度；γ4 用非超额峰度）+ γ4 边界/NaN 的处置；必要时报告正态退化灵敏度（§12 F9） |

---

## §8 步骤 2 review 记录（调研文档自检）

**方法**：逐项回源（代码行号/签名/实测数字）；文献元数据与 Crossref/原文对照；
社区结论只保留可操作项，不引用无法核实的数值。

| # | 检查项 | 方法 | 结果 |
|---|--------|------|------|
| R1 | 代码行号锚点（spec_log/spec_curve/pre_registration/ledger/governance/multiple_testing/factor_significance/factor_health/stata） | Grep + Read | 全部吻合（见 §4） |
| R2 | 「无 DSR/PBO/CPCV 实现」 | 全仓 Grep | 成立；仅字段名/用例名/文献引用 |
| R3 | 文献 DOI（DSR/PBO/spec curve/GLX/Lo/SEF/Politis-Romano/Nosek） | Crossref | 8/8 命中；页面/卷期一致 |
| R4 | 数据事实（71 个标签、SR 区间、Barra/mv 断档） | 既有实测文档 + 算术核对 | 吻合；T=71 整除约束为本次新发现 |
| R5 | 月频 SR 换算（年化 → 逐期） | 算术 | 0.94/√12=0.271；0.77-1.05 → 0.222-0.303 |
| R6 | 测试覆盖 | 读测试文件 | 19 + 11 项均为基础能力；无 DSR/PBO/CPCV 测试 |
| R7 | 「S=8/10/12 敏感」可行性 | 算术 | **证伪**：S 必须偶数，71 无偶数因子；70 的偶数因子为 10/14；8/12 不可等分 → 改为 S=10 主、14 敏感 |
| R8 | 「purge 1 期」严格性 | 区间推导 | 1 期标签严格重叠可为 0；保守取 1，需设计固定 |

**发现并修正（3 处）**：

| # | 问题 | 修正 |
|---|------|------|
| F1 | 初稿设想的 PBO `S=8/10/12` 敏感性在 T=71 下不可行 | 改为 `S=10` 主、`S=14` 敏感；§5 F6 / §6.2 D8 已回填 |
| F2 | 「purge 1 期」对 1 期标签并非严格必要 | §2.1 改为「严格重叠可为 0，保守取 1，设计阶段固定口径并单测」 |
| F3 | 「SpecificationLogger 可直接做联合推断」不成立 | §4 C1/C2、§6.2 D1 已改为「需 schema v2 + 逐规格序列」 |

**结论**：调研文档无幻觉级错误；可作为步骤 3 设计的依据。未取证项集中在书籍页码、
规格曲线联合检验细节、GLX 实现细节，已在 §7 标注。

---

## §9 步骤 2 门禁与证据等级（SPEC_PROCESS v1.7.2）

### 9.1 Step 2 门禁四项

| 门禁 | 状态 | 证据 |
|------|------|------|
| (a) FALSIFIED 断言已改写并记入修订记录 | ✅ | §8 F1「S=8/10/12」→「S=10/14」；F2 purge 口径；F3 spec logger 联合推断 |
| (b) CONFLICT / STEP_GAP_OPEN 已仲裁 | ✅ 无 OPEN | PBO 整除约束属数据约束而非文献冲突；DSR 概率语义 vs p 值已在 §2.2 澄清 |
| (c) 阻断性断言双源 | ⚠️ 部分 | DSR/PBO 公式：原文 PDF + 既有调研文档（T1+T1）；spec curve 联合检验仅摘要级（T2），已标 U2；GLX 仅元数据（T2），已标 U3 |
| (d) 假设区已转 A/B 或显式 [待定] | ✅ | U4-U8 均为 [待定]；U9 为风险披露；无未标注的隐含假设 |

### 9.2 F1-F5 出具形态

| 字段 | 出具 |
|------|------|
| **F1 来源日期** | 外部来源读取日 = **2026-11-18**；文献年份/卷期见 §2；内部文件写 v3.6.0 + 行号（§4） |
| **F2 来源版本** | 文献：期刊卷期/DOI；内部：`factor_pipeline 3.6.0` + 行号；无留空 |
| **F3 降级链** | `Semantic Scholar 返回空 → Crossref REST + 既有调研（含原文公式复核）→ DOI 命中 8/8；未取证 = 书籍页码（U1）、spec curve 联合检验细节（U2）、GLX 实现（U3）` |
| **F4 引用验证表** | §2 各表已列引用/DOI/关键定义/状态；核验读数：Crossref 命中 8/8，元数据错配 0，未验证 3 条（U1-U3） |
| **F5 先失败记录** | **N/A**：本批为文档（Layer-0），无代码/fixture 改动；F5 只约束步骤 9 有代码改动时 |

### 9.3 证据等级自评

| 结论 | 等级 | 说明 |
|------|------|------|
| 代码行号/签名/默认值（§4） | E1 | 读码可重放（Grep/Read） |
| 文献 DOI/卷期（§2） | E1 | Crossref 元数据 |
| DSR/PBO 公式（§2.2/§2.3） | E1 | 原文 PDF + 既有调研双源 |
| 数据事实（§5） | E1/E2 | 既有实测文档 + 本次算术核对 |
| 计算预算（§3.4） | E4 | 复杂度估算，未实测 |
| 社区实现结论（§3.1） | E4 | 判断陈述，仅作工程线索 |

---

## §10 调研结论

1. **六项能力均有明确学术口径，但本仓全部缺失或仅有雏形**：DSR/PBO/CPCV/purge/embargo
   零实现；规格日志只有摘要；holdout 只警告；组合层未接 ledger；效应量字段已预留但未强制。
2. **数据约束比方法选择更关键**：月频 71 个标签；扣 12 月锁定 holdout 与 1 期边界 purge 后
   开发样本 T=58 → 裁到 56，PBO 的 S 取 {8 主 / 14 敏感}（S=10 需另裁到 50）；DSR 检验力天然有限，
   弱因子可能不通过，这是应披露的诚实结果，不是实现缺陷。
3. **规格曲线联合推断是最大数据缺口**：现有 logger 只存 `ic`/`p_value` 摘要，
   必须升级 schema 持久化逐规格序列，否则只能做描述统计，不能做联合检验。
4. **holdout 一次性必须从「警告」升级为「全局锁 + 跨 batch 校验」**；
   现有 `enforce_test_set_once` 的因子级检查不足以满足路线图要求。
5. **建议实施顺序**：样本外协议/ holdout 锁 → DSR/PBO → L2 双轨接线 → 规格曲线 v2 →
   效应量/CI 强制 → 组合层 ledger 接线；每步默认关闭/显式调用，保持既有回归零变更。
6. **下一步（步骤 3）**：在 `docs/private/DESIGN_STAT_EVIDENCE_CHAIN.md` 中按 §6.4
   的 E1-E10 逐项拍板；先解决 U2/U4/U5/U7/U8 五个 [待定]，再进入 EXECUTION。

### 10.1 推荐口径（设计输入，非最终决策）

| 项 | 推荐 |
|----|------|
| 样本外 | 12 个月 holdout 独立锁定（最近月段，一次性终评）；CPCV 在开发样本（58 → 裁到 54，`N=6, k=2`，15 路径；备选 `N=5`）+ purge/embargo 各 1 期；purged K-fold 作单路径基线 |
| DSR | 评估样本=开发样本（T=58）；`N` 取 ledger `n_trials`（保守上界）；`V[SR_n]=1/(T−1)` 主口径；阈值 0.95 仅用于 G2 证据，不单独阻断 |
| PBO | 评估样本=开发样本 58 → 裁到 56；`S=8` 主（每块 7 期）、`S=14` 敏感；`S=10` 需另裁到 50；组合层 `N=10`（5 策略 × 2 池，费率作稳健性维度） |
| 规格曲线 | schema v2 持久化逐规格序列；S3 强制附 curve 或书面声明单一规格 |
| 效应量/CI | λ 用 `PremiumEstimator`；IC/SR 用 stationary bootstrap；CI 与 p 同口径 |
| 组合层 | 同批组合预注册为新 family，组合 variant 为 confirmatory；跨批复用同 family 需预注册 |

---

## §11 检索与复现记录

```powershell
# 1) 确认无实现
Grep -i "deflated|probabilistic_sharpe|\bpbo\b|cscv|combinatorial.?purged|purged.?kfold|\bembargo\b" -g "*.py"

# 2) 关键接口行号
Grep -n "def (log_run|get_specification_curve|enforce_test_set_once|analyze|commit|verify_compliance)" backtest/specification_logger
Grep -n "def (apply|report|_persist_result)|n_hypotheses|n_testable" backtest/multiple_testing_ledger.py
Grep -n "dsr|pbo|oos_metric|holdout_locked_at|split_id" backtest/governance.py

# 3) 数据事实来源
Read docs/analysis/PORTFOLIO_BACKTEST_VERIFICATION.md
Read docs/PROJECT_STATUS.md (L108)
```

Crossref 查询（2026-11-18）：`10.3905/jpm.2014.40.5.094`、`10.21314/JCF.2016.322`、
`10.1038/s41562-020-0912-z`、`10.1093/rfs/hhaa111`、`10.2469/faj.v58.n4.2453`、
`10.21314/JOR.2012.255`、`10.1080/01621459.1994.10476870`、`10.1073/pnas.1708274114`。

---

## §12 独立复审记录（2026-11-18）

> 复审范围：逻辑一致性 / 算术正确性 / 学术口径 / 代码锚点 / 盲区。
> 方法：独立重算（区间推导、因子分解、组合数、√12 换算）+ 本会话读码复核 +
> Crossref 抽检（GLX / DSR 两条 DOI，2026-11-18）。
> 结论：**PASS_WITH_FIXES** — 0 推翻；P0 1 项、P1 3 项、P2 4 项全部修正；
> 盲区 3 项登记（U11 / U12 / E6 增补）；§8 F1 的「S=8 不可行」结论在扣 holdout
> 场景下部分反转（本节 F2；§8 原文按 append-only 保留，以本节为准）。

### 12.1 发现与处置

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| F1 | **P0** | 内部矛盾：v1.0 的 10.1 同时推荐「12 月 holdout 锁定」与「PBO T 裁到 70（全样本）」——若 DSR/PBO/CSCV 在含 holdout 的 71 月上计算，评估行为即消耗 holdout，违反路线图 P1-①「S0 锁定、一次性」原则 | 确立「DSR/PBO/spec curve 只用开发样本（T=59），holdout 只做一次性终评并写 `oos_metric`」；§2.2 陷阱 6、§2.3 增陷阱 7、§7 U11、E4/E5、§3.4、§5、§10、10.1 同步修正 |
| F2 | P1 | S 集合场景化重算：开发样本 59（素数）→ 裁到 56 → 可行 `S ∈ {2,4,8,14}`；原「S=8 不可行」仅在 T=70 场景成立；扣 holdout 场景下 S=8（每块 7 期）优于 S=14（每块 4 期噪声大）；S=10 需另裁到 50（损失 9 月） | §2.3 陷阱 1/5、§5 F6、可行性表、D8、§10-2、10.1 改写 |
| F3 | P1 | CPCV 整除约束同样场景化：开发样本 59 → 裁到 54（`N=6`，每组 9 月，接近 §2.1 陷阱 2 的噪声下限；备选 `N=5` 裁到 50）；原文「每组约 12 个月」仅适用全样本裁 66 | §2.1 陷阱 2、§5 F7、可行性表、10.1 改写 |
| F4 | P1 | purge 区间记号错误：测试折样本 `a..b` 的标签并集是 `(a, b+1]` 而非 `(a, b]`（结论「purge 理论可为 0」不变） | §2.1 已改 |
| F5 | P2 | `V[SR_n]` 经验方差「更保守」不严格（不必然 ≥ `1/(T−1)`） | §2.2 陷阱 5 表述软化 |
| F6 | P2 | `N=1` 时 DSR 退化方向未写明（`Φ⁻¹(1−1/N)=−∞` → `SR0→−∞` → `DSR≡1`） | §2.2 陷阱 8 已改 |
| F7 | P2 | §3.4 预算「252 × N×71」与裁剪口径不一致 | 已改为 C(8,4)=70 / C(14,7)=3432 × N×56；spec curve 行 71→59 |
| F8 | P2 | GLX 页码本稿 3456-3486 与路线图 §12 的 3456-3496 冲突 | Crossref 复核（2026-11-18）：**3456-3496 正确**（"Thousands of Alpha Tests"，RFS 34(7)）；本稿已改，路线图无需动 |
| F9 | 盲区 | γ3/γ4 月频小样本估计噪声与边界处置未定 | §7 U12 登记并入 E4 |
| F10 | 盲区 | spec curve 置换检验的 B 与 seed 未要求预注册 | §6.4 E6 增补 |

### 12.2 核对通过项（独立重放）

| 项 | 方法 | 结果 |
|----|------|------|
| T=71/59 为素数；70=2×5×7、56=2³×7、50=2×5²、54=2×3³ | 手算因子分解 | 吻合（F1/F2/F3 的算术基础） |
| C(10,5)=252、C(6,2)=15、C(8,4)=70、C(14,7)=3432 | 手算 | 吻合 |
| 0.94/√12=0.271、0.77/√12=0.222、1.05/√12=0.303 | 手算 | 吻合 |
| 71−12=59（holdout 后开发样本） | 手算 | 吻合 |
| purge 半开区间推导 | 手推 | 结论不变；记号修正（F4） |
| DOI 抽检：GLX `10.1093/rfs/hhaa111`、DSR `10.3905/jpm.2014.40.5.094` | Crossref REST（2026-11-18） | 2/2 命中；GLX 页码修正（F8），DSR JPM 40(5):94-107 确认 |
| 代码锚点 C1-C19 | 本会话 Read/Grep 重放 | 全部吻合（spec_log L40/76/106/134、pre_registration L30/53、ledger L91-101/571/613-638/772-785、governance L371-372/399-401/491-522/539-542、multiple_testing 函数表、factor_significance L260-283/366-415、factor_health L65、stata L50-55/623-629） |
| C3/C7 语义表述（警告不阻断 / 键比较缺口） | 读码 | 与 spec_log.py L106-132、pre_registration.py L53-76 一致 |

### 12.3 复审后遗留

- U1-U3 维持 [待核实]（书籍页码 / spec curve 联合检验细节 / GLX 实现），设计前须回原文；
- U11 是 F1 的设计侧落点：DESIGN 必须定义开发样本掩码（dev_mask）与 holdout 剔除接口；
- S 的最终推荐（S=8 主 vs 坚持 S=10 裁到 50）属 E5 拍板项，本稿给出两条路径的代价；
- F2 对 §8 F1 构成场景化反转：§8 原文保留（append-only），以本节为准。

---

## §13 v1.2 设计阶段修正回填（2026-11-18）

> 来源：步骤 3 设计（`docs/private/DESIGN_STAT_EVIDENCE_CHAIN.md`）与步骤 4 复审（其 §21）发现的边界泄漏问题；
> 本节为 append-only 回填注记，§12 历史记录不改。

| # | 修正 | 理由 |
|---|------|------|
| C1 | **dev=59 → 58，新增 2024-12 边界 purge**：holdout=2025-01…2025-12；标签 2024-12 的收益 `r=P_{2025-01}/P_{2024-12}−1` 需要价格 `P_{2025-01}`（holdout 起点价格），计算即触碰 holdout 数据 | 与 §2.1「共用价格保守 purge」同一原理延伸到 dev/holdout 边界；`dev_mask` 只保留 `date < start` 再剔 `purge=1` 期 |
| C2 | 下游 T 全部同步：DSR T=58；PBO 58→56（起点 2020-04，S=8 主/14 敏感）；CPCV 58→54（起点 2020-06，N=6）；规格曲线置换 58 期 | §5 F6/F7/F9、§2.2 陷阱 6、§2.3 陷阱 1②、§3.4、可行性表、D8、U4/U11/U12、§10-2、10.1 已回填 |
| C3 | 58 不是素数（58=2×29）——「开发样本为素数」的表述随之失效；整除分析只依赖「裁到可整除的最近长度」，结论不变 | §2.3 陷阱 1② 已去掉素数表述 |
| C4 | 本稿正文其余数字（全样本 71、裁 66 组 11 月、SR 换算、N=10 等）不受影响 | 复核通过 |

**同步状态**：设计文档 v1.1（§21 复审 PASS_WITH_FIXES）为当前权威口径；本稿 v1.2 与其一致。
下游实现（步骤 5 EXECUTION v3.7.0）一律以设计 §0 D13 为准：holdout 2025-01…2025-12、gap 2024-12、dev 2020-02…2024-11（58 期）。
