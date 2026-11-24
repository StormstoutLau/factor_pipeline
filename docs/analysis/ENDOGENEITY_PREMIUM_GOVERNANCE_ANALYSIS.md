# 内生性-溢价诊断交互：可行性分析与当前多因子治理体系核对

> **日期**: 2026-11-17
> **对象**: `FactorHealthDiagnoser`（Layer 3 溢价健康） × `EndogeneityDiagnosticOrchestrator`（E3 τ）
> **触发**: P2 待办「内生性-溢价诊断交互 (τ 修正因子)」（DESIGN_DISCUSSION_V3.3.0 §6.1）
> **方法**: 代码逐段回溯（`pipelines_v2.py` / `factor_health` / `endogeneity_check` / `optimizer` / `backtest`）+ 文献与社区实践对照
> **结论**: **目的成立，但当前不具备「按设计规则直接上线」的条件**。
> 两个硬前置：① 阶段口径不匹配（默认静态路径无 S4，S3 默认关闭）；② 0.7/0.3 阈值与降级规则从未校准。
> 另：当前多因子治理体系是**工具箱而非强制执行系统**——E 系列与高级监控全部 opt-in，
> Layer 2/3 标签不在管线内，组合层无生产实现。

---

## §1 结论摘要

| 问题 | 结论 |
|------|------|
| 交互要解决什么 | 防止遗漏变量污染 λ̂(t)，把「内生性驱动的假溢价/假断点」误判为真实溢价结构 |
| 处理对象 | **诊断标签**（`diagnosis`），不是因子数值；不改变 λ̂，也不改变因子矩阵 |
| 插入点 | `_combine_label(return_type, premium_health)` 之后、`diagnose` 返回之前 |
| 工程可行性 | 接口齐备但未接线：`diagnose` 无 τ 入参；E3 与 Layer 3 是两个独立入口 |
| **阶段可行性** | **不匹配**：默认 `pipeline_mode='unified'` → Static 管道（无解耦）→ 只有 S2/S3 可选；`final_threat_tau` 是 S4；S3 默认关闭 |
| 规则可行性 | 不具备：0.3/0.7 在 E3 中是正则化强度分档，不是标签降级校准；无真实 τ 分布、无判别力验证 |
| 收益性质 | 治理保守性 / 一致性，不是统计精度 |
| 代价 | τ 的第 4 处消费（E5 已有 L1/L2/L3）、误降级风险、契约与口径维护 |
| 最终判断 | **先探针校准，后决定是否落地**；若落地，只做「提示」不做硬降级 |

---

## §2 交互的目的

Layer 3 用 `PremiumEstimator` 估截面溢价 λ̂(t)，再检测断点/衰减并输出治理标签
（`pricing / monitor / recalibrate / review / suspect`）。问题在于 **λ̂ 是估计量**：
若因子与遗漏变量相关，λ̂(t) 会把遗漏变量的溢价变化算到因子头上。

| 失败模式 | 机制 | 后果 |
|---------|------|------|
| 假溢价 | 遗漏变量同时驱动因子与收益 | 因子被标 `pricing`，实为代理变量 |
| 假断点 | 遗漏变量的溢价发生结构变化 | `BreakpointDetector` 把「别人的断点」判成因子的 |
| 假衰减/假稳定 | 同上，作用于 TD 检测 | `review` / `pricing` 标签失真 |

交互的目的因此是：**把 E3 的内生性威胁 τ 作为治理标签的敏感性修正**，而不是重新估计溢价。
它还修补一个治理不一致——τ 已驱动 E5 三层正则化（L1 中性化 / L2 显著性 α / L3 权重），
但标签层完全无视 τ，可能出现「标签写 pricing、权重却被 τ 打折」。

设计文档原文（[§6.1](../private/DESIGN_DISCUSSION_V3.3.0.md#L211-L222)）：

> τ > 0.7 → 降级标签 (pricing → monitor, recalibrate → review)；τ < 0.3 → 保持原标签；
> 标注为「远期」「待验证」。

注意：**0.3-0.7 灰区在设计规则中未定义**。

---

## §3 处理对象与流水线顺序（代码事实）

### 3.1 执行链

```
原始因子
  └─ S1 缺失机制 (MCAR/MAR/MNAR)                 ← 标签，非 τ；enable_missingness_diagnosis 默认 False
  └─ 插补 → S2 τ 基线 (插补后/中性化前)           ← Oster + AET (默认方法)
  └─ 中性化 → S3 τ 残留 (可选)                   ← enable_s3_neutralization_check 默认 False
  └─ 解耦 → S4 τ 最终 = final_threat_tau          ← 仅 Dynamic 管道有解耦
        ↓
  Layer 2 return_type (static/dynamic)          ← StatisticalClassifier 已不在 fit/transform 中调用
        ↓
  Layer 3: λ̂(t) → 断点 → 衰减 → premium_health
        ↓
  _combine_label(return_type, premium_health) → diagnosis
        ↓  ★ 待插入: τ 修正
  E5 三层正则化 (L1/L2/L3)                       ← 已消费 τ，但默认关闭且仅输出配置
```

### 3.2 处理对象

**不是因子数值，而是标签**：交互不改变 λ̂、不改因子矩阵，只改 `diagnosis` 字段，
并落 `endogeneity_tau` / `label_downgraded` 审计键。插入点在
[`_combine_label`](../../modules/factor_health/__init__.py#L1236-L1252) 之后；
`diagnose` 当前签名无 τ 入参（[L799-L801](../../modules/factor_health/__init__.py#L799-L801)）。

### 3.3 关键：阶段口径不匹配（本次核对的新发现）

| 实际执行管道 | 步骤 | 可用的 E3 阶段 |
|-------------|------|---------------|
| **默认 `pipeline_mode='unified'` → Static** | 插补 → 去极值 → 中性化 → rank 变换 → 标准化 | **S2**（插补后）或 **S3**（中性化后，默认关）；**无 S4** |
| `dynamic_ab` → Dynamic | 插补 → CompositeDecoupler（中性化 + AR 残差）→ z_score | S2 / S3 / **S4** |
| Mixed（非默认） | 插补 → 3σ 缩尾 → 中性化 → rank → z_score | S2 / S3；无 S4 |

`final_threat_tau` 来自 S4（解耦后）。默认生产路径没有解耦，因此：
- 若拿 S4 τ 配 Static 管道输出 → **阶段错配**；
- 若用 S2 τ → 它是**中性化前**的威胁，而标签是在中性化后因子上诊断的，语义不一致；
- 唯一匹配的是 S3，但 `enable_s3_neutralization_check=False` 默认不产出。

**结论**：不是「加一个参数」那么简单，必须先定义「标签诊断输入阶段 ↔ τ 阶段」的绑定规则，
并在默认静态路径上补 S3（或明确改用 S2 并披露语义差异）。

---

## §4 学术依据

| 机制 | 文献 | 仓库落点 | 支持强度 |
|------|------|---------|---------|
| 遗漏变量偏误与系数稳定性（δ、R² 变动、比例选择） | Oster (2019, JBES 37:187-204) | `OsterDeltaChecker` | 方法直接对应；但对象是**因果处理效应**，用于因子溢价属类比 |
| 以可观测选择强度推断不可观测选择 | Altonji, Elder & Taber (2005, JPE) | `AltonjiElderTaberChecker` | 启发式，非正式识别 |
| 交互固定效应吸收多维不可观测结构 | Bai (2009, Econometrica 77:1229-1279) | `InteractiveFEChecker`（默认关） | 直接对应；但无法区分「内生性断点」与「真溢价断点」——正是缺口 |
| 无外部工具变量时用异方差识别 | Lewbel (2012, JBES 30:67-80) | `LewbelInternalIVChecker`（默认关） | 直接对应 |
| 两阶段/ Fama-MacBeth 的变量误差偏误 | Shanken (1992, RFS) | `PremiumEstimator` 的 λ̂ 本身受 EIV 影响 | 支持「λ̂ 不可靠，需敏感性修正」 |
| 风险溢价的结构性断点真实存在 | "Have risk premia vanished?" (JFE 2022, 145(2):553-576)；Fed FEDS 2024-037 | `BreakpointDetector` 的业务前提 | 支持「断点值得测」，不直接支持 τ 映射 |
| 多重检验与因子动物园 | Harvey, Liu & Zhu (2016, RFS 29:5-68) | 项目多重检验链 | 支持「高威胁因子应更保守」 |
| **δ 的局限** | "The Effect of Omitted Variables on the Sign of Regression Coefficients" (arXiv 2208.00552) | 对 `OsterDeltaChecker` 的警示 | **关键反证**：δ 大不代表符号稳定 |

**判读**：方向有依据，规则无校准。τ 是「偏误风险评分」，不是偏误估计；
把它当硬门槛，是把「风险」当「事实」。Oster δ 的符号反转批评尤其说明：
高 τ 不能推出「溢价无效」。

---

## §5 社区案例

| 社区方案 | 做了什么 | 与本交互的差距 |
|---------|---------|---------------|
| Alphalens | IC、分位收益、换手、tear sheet | 无内生性/断点耦合，只做预测力 |
| Qlib | IC/风险分析/回测 | 因子评估与风险模型分离，无单因子内生性标签 |
| 因子动物园复现（HLZ、Hou-Xue-Zhang、Chen-Zimmermann 等） | 统一 t 门槛、复现率 | 用**全局**多重检验门槛，不做**单因子**内生性修正 |
| 实务风险模型（Barra 系） | 风格/行业暴露与风险分解 | 与溢价诊断分属两套流程 |

即：**没有现成的开源范式可抄**。这既是差异化空间，也意味着规则必须在本项目内验证。

---

## §6 收益 vs 代价

| 收益 | 代价 |
|------|------|
| 阻止高 τ 因子的假 `pricing` 标签流入治理决策 | **重复消费**：τ 已驱动 E5 的 L1/L2/L3，再加标签层是第 4 处；同一信号多次使用 → 过度保守 |
| 与 E5 接线一致，边际成本低（τ 已算，映射 O(1)） | **阈值未校准**：0.3/0.7 是 `recommendation ∈ {none,mild,strong}` 的分档（[threat_assessor L82-L87](../../modules/endogeneity_check/core/threat_assessor.py#L82-L87)），不是标签降级阈值；灰区未定义 |
| 可审计：τ + 降级标记落盘 | **标签吸收态**：monitor/review/suspect 无法再降；实际只有 pricing→monitor、recalibrate→review 两条边 |
| 可利用 S2/S3/S4 轨迹（`s4_minus_s2`、`critical_alert`）做分层治理 | **依赖 return_type**：`recalibrate` 需 `static`；`pipelines_v2` 已不调用 StatisticalClassifier（[L1183](../../pipelines_v2.py#L1183)），管线不产出该字段；研究脚本显式传 `'static'` 时分支可达，未传时默认 `unknown` → 规则实际只对 pricing 生效 |
| 默认 Oster+AET 只需「因子+收益」，不受行业断档影响 | IFE/Lewbel 需 controls（行业），2023-06 后不可用；「完整版」受限 |
| 默认 `None` 零变更，opt-in 风险低 | **契约成本**：`diagnose` 现 30 键，新增需同步测试/文档；诊断变为依赖外部状态的函数 |
| | **概念风险**：高 τ 不等于溢价无效，硬降级可能误杀 |

---

## §7 当前多因子治理体系核对（代码回溯）

### 7.1 默认状态总表

| 层 | 组件 | 默认状态 | 是否在 `PipelineV2.fit/transform` 自动执行 |
|----|------|---------|------------------------------------------|
| L0 数据 | 插补 `ffill_ts` | **开** | ✅（所有管道第一步） |
| L0 数据 | 数据新鲜度守卫 | **无实现** | ❌（P2 待办） |
| L1 预处理 | 去极值 percentile 1/99 | **开** | ✅ Static/Mixed；Dynamic 无 |
| L1 预处理 | 中性化（行业/市值） | **开**（需传入 industry/market_cap） | ✅ Static/Mixed；Dynamic 在解耦器内 |
| L1 预处理 | rank→normal 变换 | **开** | ✅ Static/Mixed；Dynamic 不做（保护时序） |
| L1 预处理 | 标准化 | **开** | ✅ 三条管道 |
| L1.5 跨因子 | 正交化 `post_transform_hooks` | **关**（`orthogonalization=None`） | ❌ 仅 opt-in |
| L1.5 跨因子 | 解耦（AR 残差） | **默认路径没有** | 仅 `dynamic_ab` 模式 / 直接使用 Dynamic 管道 |
| L2 检验 | `FactorSignificanceTest`（双重 Lasso） | 未接线 | ❌ 独立 `backtest/` 模块 |
| L2 检验 | 多重检验（BH/Bonferroni/BY/Romano-Wolf/White RC/Hansen SPA） | 未接线 | ❌ 独立模块 |
| L2 检验 | `PremiumEstimator.estimate_with_errors`（HAC SE） | 未接线 | ❌ 脚本/演示调用 |
| L2/L3 标签 | `FactorHealthDiagnoser` | 未接线 | ❌ 仅脚本与 demo；`pipelines_v2` 已停用 StatisticalClassifier |
| L3 组合 | `EndToEndThresholdOptimizer`（optuna） | 默认搜索空间为空 → 弃用警告；需 optuna | ❌ 独立 |
| L3 组合 | 组合权重优化器（均值-方差/风险预算类） | **不存在**；现有 `EndToEndThresholdOptimizer` 只优化**管道阈值/参数**（含权重惩罚项） | ❌ 组合权重构造在研究脚本中 |
| L4 监控 | `FactorFingerprintMonitor`（迁移阈值 0.10） | **开** | ✅ `fit` 后 `add_fingerprint` |
| L4 监控 | 结构突变 `StructuralBreakMonitor` | **关** | ❌ `monitor_structural_breaks` 手动 |
| L4 监控 | CUSUM 漂移 | **关** | ❌ `monitor_cusum_drift` 手动 |
| L4 监控 | IC 变化 / 阈值漂移 / 统一漂移 / 状态归因 | 未接线 | ❌ 独立模块 |
| L5 研究治理 | `SpecificationLogger`（p-hacking） | **关** | ❌ opt-in |
| L5 研究治理 | 指纹性能日志（DuckDB） | **关** | ❌ opt-in |
| L5 研究治理 | `AblationRunner` | 独立 | ❌ 研究工具 |
| E1 隐藏效应 | `diagnose_hidden_effects` | **关** | ❌ opt-in |
| E2 p-hacking | `enable_specification_logger=False` | **关** | ❌ |
| E3 内生性 | `enable_endogeneity_check=False` | **关** | ❌ `check_endogeneity` 手动 |
| E4 格兰杰 | `enable_granger_attribution=False` | **关** | ❌ |
| E5 三层正则化 | `enable_endogeneity_regularization=False`；λ=0 | **关** | ❌ 只返回配置 dict，需调用方应用 |
| E6 估计层 | `enable_endogeneity_estimators=False` | **关** | ❌ |
| E7 状态归因 | `enable_state_attribution=False` | **关** | ❌ |
| E10 决策桥 | `enable_decision_bridge=False` | **关** | ❌ |

### 7.2 默认路径的精确顺序

- **Static（默认 `unified`）**：`imputer → outlier → neutralize → transform(rank→normal) → standardize`
  （[L739-L763](../../pipelines_v2.py#L739-L763)；GARCH 白化默认关）
- **Dynamic（`dynamic_ab`）**：`imputer → CompositeDecoupler(中性化 + AR 残差) → z_score`
  （[L829-L894](../../pipelines_v2.py#L829-L894)）
- **Mixed（非默认）**：`imputer → 3σ 缩尾 → neutralize → rank → z_score`
  （[L937-L1011](../../pipelines_v2.py#L937-L1011)）

> v3.4.0 ADR-042 后，**执行管道由 `pipeline_mode` 唯一决定**，
> 指纹分类只产诊断标签、不再路由（[L1183-L1192](../../pipelines_v2.py#L1183-L1192)）。

### 7.3 治理体系的四个结构性缺口

1. **默认路径没有多因子交互**：每因子独立管道；正交化默认关；
   冗余/共线性只在 optuna 优化器的复合目标里（`redundancy_penalty`），而该优化器默认搜索空间为空。
2. **Layer 2/3 诊断不在管线内**：`FactorHealthDiagnoser` 只被脚本/demo 调用；
   `StatisticalClassifier` 已从 fit/transform 移除，`return_type` 常为 `unknown`。
3. **治理信号分散、无统一契约**：τ、health_score、premium label、significance p 值、drift alert
   各自是独立 dict，没有「一个因子一张治理卡」的汇总对象；E5 是唯一的跨信号耦合，且只输出配置。
4. **默认关闭 + 手动调度**：E 系列、break/CUSUM、spec logger 全部 opt-in；
   没有默认调度器（`BreakMonitorScheduler` 存在但未接入 `PipelineV2`）。

### 7.4 与交互的关系

- 交互会**新增第 4 个 τ 消费者**（E5 的 L1/L2/L3 已消费）；
- 交互的插入点在 Layer 3，但 Layer 3 本身不在默认管线内 → 交互在默认生产路径上**不会被触发**；
- 若不先统一治理信号契约，交互只会增加一个孤立的标签修正，无法进入决策链。

### 7.5 可比性契约（治理升级门禁）

**前提澄清**: 当前**不存在**按因子分流 Static/Dynamic。
`pipeline_mode='unified'`（默认）→ 全部因子走 Static；`dynamic_ab` → 全部走 Dynamic；
分类器只产诊断标签、不参与路由（v3.4.0 ADR-042，[L1183-L1192](../../pipelines_v2.py#L1183-L1192)）。
可比性由「全局同一 arm」保证，而不是逐因子对齐。

**关键区分**: 三条管道最终都做逐日截面 `z_score`（[adapters.py L554/L598](../../adapters.py#L554-L598)），
**尺度可比**；但 Static 的 rank 变换抹掉时序动态、Dynamic 保留时序并做 AR 解耦——
**同尺度 ≠ 同信号**。因此"看起来可比"不等于"可以混用"。

#### 7.5.1 五条硬规则

| # | 规则 | 要求 |
|---|------|------|
| C1 | **同臂** | 一个多因子组合内所有因子必须走同一 pipeline arm；禁止 Static/Dynamic 混搭。必须混时按 arm 拆 sleeve，各自治理/归因，组合层只汇总权重 |
| C2 | **同样本** | 统一日期轴、股票池、收益口径、缺失处理；比较必须用配对共同样本，禁止"各自全样本均值差" |
| C3 | **同分母** | 所有 arm / variant 都进入多重检验分母（BH/Bonferroni/Romano-Wolf/White RC/Hansen SPA），禁止只报跑赢的变体 |
| C4 | **同不变量** | 每次输出断言截面均值≈0、方差≈1、NaN 率、权重行和、IC 符号一致性；任一失败视为口径漂移，不是"新发现" |
| C5 | **同版本** | `code commit + config hash + 数据快照指纹 + seed` 四元组写入产物；升级前跑 golden-master 对账（同环境 1e-10 容差，跨环境禁 bitwise 断言；见[路线图 §5 P0-3](MULTIFACTOR_GOVERNANCE_ROADMAP.md)） |

#### 7.5.2 两条工程规则

| # | 规则 | 要求 |
|---|------|------|
| C6 | **一次只改一层** | pipeline arm / L2 检验 / L3 组合 / 治理规则四层不得同时改；用 `module_enabled` + `AblationRunner` 分层消融 |
| C7 | **默认零变更** | 治理升级一律以 opt-in 开关加入，默认路径逐位不变，增量单独度量 |

#### 7.5.3 升级协议

| 步 | 动作 | 门禁 |
|----|------|------|
| S0 | 冻结基线：commit + config hash + 数据快照 + golden outputs | 默认路径与基线一致（同环境 1e-10 容差） |
| S1 | 写可比契约：同臂 / 同样本 / 同指标 / 同分母 | 契约入文档并通过评审 |
| S2 | 分层消融：L1 → L2 → L3 → 治理规则，一次一层 | 每层单独报告增量 |
| S3 | 配对比较：共同样本 + block bootstrap CI + effect size | 不只报 p 值 |
| S4 | 噪音预算：arm / sample / seed / data 四个方差分量 | 治理增量 > 预注册 MDE |
| S5 | 不变量断言 + 漂移监控 | 任一不变量失败即回滚 |
| S6 | 产物写 arm label 与规则版本；旧规则可重放 | 无 arm label 的产物不入库 |

#### 7.5.4 可复用件与缺口

| 目的 | 现有件 |
|------|--------|
| 防逐因子混搭 | `pipeline_mode` 全局开关 |
| 记录执行事实 | `FactorRoutingRecord` + `_log_spec`（execution pipe / 指纹 / 样本区间） |
| 审计与重放 | `get_intermediate_data()` |
| 分层消融 | `module_enabled` + `AblationRunner` |
| 数据/配置指纹 | `CacheKey` / `CacheManager` |
| 多 arm 统一分母 | `backtest/multiple_testing.py` |
| 预注册与防挑结果 | `SpecificationLogger`（spec curve + test-set-once） |
| 分布漂移监控 | `FactorFingerprintMonitor`（迁移阈值 0.10） |
| 配对置信区间 | `ablation_runner.circular_block_bootstrap` |
| 多因子增量 | `FactorSignificanceTest`（双重 Lasso 增量 α） |

**缺口**（升级前建议补）：
① 统一 `GovernanceRecord`（因子 / arm / 阶段 S2-S4 / τ / health / premium label /
significance / drift / 版本，一个对象汇总）；② 数据新鲜度守卫（已在 P2 登记）——
否则"同样本"无法保证。

#### 7.5.5 禁止事项

- 禁止在同一多因子组合内混用 Static / Dynamic；
- 禁止恢复逐因子路由（分类器只作诊断）；
- 禁止只报最优变体、或让不同 arm 使用不同的多重检验分母；
- 禁止同时修改 pipeline arm 与治理规则；
- 禁止产物不带 arm label / 规则版本就进入比较或入库。

---

## §8 判断与建议

### 8.1 是否具备执行条件

**不具备「直接上线」条件；具备「做可行性研究」条件。**

阻塞项按优先级：

| # | 阻塞 | 说明 |
|---|------|------|
| B1 | **阶段口径** | 默认静态路径无 S4；S3 默认关；必须定义并实现「标签输入阶段 ↔ τ 阶段」绑定 |
| B2 | **阈值校准** | 0.3/0.7 不是标签降级阈值；灰区未定义 |
| B3 | **判别力未验证** | 无真实 τ 分布；无内生性已知 DGP 的降级正确率/误降级率 |
| B4 | **重复消费** | 与 E5 的分工未定义 |
| B5 | **触发面** | 生产管线已不产出 `return_type`（StatisticalClassifier 停用）；研究脚本显式传 `'static'` 时 `recalibrate→review` 可达，未传时默认 `unknown` 该分支不可达 |

### 8.2 建议路径

1. **探针（不改生产代码）**
   - 4 因子跑 E3，输出 S2/S3/S4 的 τ 分布与 0.3/0.7 触发率；
   - 构造内生性已知 DGP（真信号 + 遗漏变量载荷），测高 τ 组溢价是否显著更不稳定、
     降级正确率 / 误降级率；
   - 若 τ 全落在 <0.3 或 >0.7，规则无区分度 → 结论「不实现」，与 §6.2 多断点同样处置。
2. **只在证据达标后落地**，且最小形态：
   - 输出 `endogeneity_tau` + `endogeneity_flag`，**保留原 `diagnosis`**（提示而非硬降级）；
   - 若必须降级，只保留 `pricing → monitor` 一条边；
   - `tau_stage` 显式声明并与 `diagnose` 输入阶段校验，不匹配报错；
   - 与 E5 分工：权重层惩罚、标签层披露，避免双重打折；
   - opt-in、默认零变更、键数 30→32 同步契约测试。
3. **体系层前置（可选但更根本）**
   - 先建一个 `GovernanceRecord`（因子名 / 阶段 / τ / health / premium label / significance / drift），
     把分散信号汇总后再谈「交互」；否则只是在孤岛上加一条规则。
4. **治理升级门禁**
   - 任何多因子治理升级先执行 §7.5 可比性契约（同臂 / 同样本 / 同分母 + 分层消融 + golden master）；
   - 禁止在同一组合内混用 Static / Dynamic；禁止恢复逐因子路由；
   - 升级产物必须带 arm label 与规则版本，否则不进入比较或入库。

---

## §9 核对方法与证据

- 配置默认值：`PipelineV2Config`（[L458-L605](../../pipelines_v2.py#L458-L605)）
- 管道步骤：Static（[L739-L763](../../pipelines_v2.py#L739-L763)）、Dynamic（[L829-L894](../../pipelines_v2.py#L829-L894)）、Mixed（[L937-L1011](../../pipelines_v2.py#L937-L1011)）
- 执行模式：`pipeline_mode` 唯一决定（[L1183-L1192](../../pipelines_v2.py#L1183-L1192)）
- E3 四阶段：`EndogeneityDiagnosticOrchestrator`（[L73-L181](../../modules/endogeneity_check/core/diagnostic_orchestrator.py#L73-L181)）
- E5 三层：`apply_endogeneity_regularization`（[L1990-L2051](../../pipelines_v2.py#L1990-L2051)）
- 组合惩罚：`_endogeneity_penalty` / `_composite_objective`（[optimizer.py L391-L446](../../optimizer.py#L391-L446)）
- 健康度五维：`HealthConfig`（[health.py L64-L90](../../modules/factor_fingerprint/core/health.py#L64-L90)）
- 回测默认：`top_n=0.2 / rank IC / ls_method=top_n`（[engine.py L42-L47](../../backtest/engine.py#L42-L47)）
- 诊断标签映射：`_combine_label`（[factor_health L1236-L1252](../../modules/factor_health/__init__.py#L1236-L1252)）
- 数据约束：barra 止于 2023-05-31、行业止于 2023-06-13（[数据缺口诊断](DATA_GAPS_DIAGNOSIS.md)）

**文献**:

- Oster, E. (2019). Unobservable Selection and Coefficient Stability. *JBES*, 37(2), 187-204.
- Altonji, Elder & Taber (2005). Selection on Observed and Unobserved Variables. *JPE*.
- Bai, J. (2009). Panel Data Models With Interactive Fixed Effects. *Econometrica*, 77, 1229-1279.
- Lewbel, A. (2012). Using Heteroscedasticity to Identify and Estimate Mismeasured and Endogenous Regressor Models. *JBES*, 30(1), 67-80.
- Shanken, J. (1992). On the Estimation of Beta-Pricing Models. *RFS*.
- Harvey, Liu & Zhu (2016). …and the Cross-Section of Expected Returns. *RFS*, 29(1), 5-68.
- "Have risk premia vanished?" *JFE* (2022), 145(2), 553-576.
- Federal Reserve FEDS 2024-037, "Factor Selection and Structural Breaks".
- "The Effect of Omitted Variables on the Sign of Regression Coefficients" (arXiv 2208.00552).

---

## §10 实现盘点：内生性诊断在流水线中的落点（2026-11-24 复核）

> 口径：只统计仓内可运行代码；测试 / demo / 研究脚本不计为生产接线。

### 10.1 已实现（组件层，可用但全部 opt-in）

| 能力 | 落点 | 默认 | 生产调用方 |
|------|------|------|-----------|
| E3 四阶段（S1 缺失机制 / S2 基线 τ / S3 中性化后残留（可选）/ S4 解耦后最终 τ） | `EndogeneityDiagnosticOrchestrator`（[L27](../../modules/endogeneity_check/core/diagnostic_orchestrator.py#L27)） | `enable_endogeneity_check=False`（[L546](../../pipelines_v2.py#L546)） | 仅 `check_endogeneity()` 手动（[L1814-L1925](../../pipelines_v2.py#L1814-L1925)）+ 测试 / demo |
| τ 汇总与正则化推荐 | `EndogeneityThreatAssessor.assess()`：`final_threat_tau` / `component_taus` / `s1_mechanism` / `recommended_regularization`（none <0.3 / mild <0.7 / strong ≥0.7，[L82-L87](../../modules/endogeneity_check/core/threat_assessor.py#L82-L87)） | — | E3 内部 |
| E5 三层正则化 | `EndogeneityRegularizer`：L1 `skip_stage2<0.3` / `extra_check≥0.7`（[L93-L97](../../modules/endogeneity_regularizer/regularizer.py#L93-L97)）、L2 α=α_base(1−γτ)、γ=0.5（[L140](../../modules/endogeneity_regularizer/regularizer.py#L140)）、L3 w=w_raw(1−ρτ)、ρ=0.3（[L180](../../modules/endogeneity_regularizer/regularizer.py#L180)） | `enable_endogeneity_regularization=False`（[L574](../../pipelines_v2.py#L574)） | 仅 `apply_endogeneity_regularization()` 手动（[L2069-L2129](../../pipelines_v2.py#L2069-L2129)），硬依赖 E3 |
| 显著性检验消费 τ | `FactorSignificanceTest(threat_taus=…)`（[L536](../../backtest/factor_significance.py#L536) / [L566](../../backtest/factor_significance.py#L566) / [L585](../../backtest/factor_significance.py#L585)） | 需调用方显式传 | 未见生产调用 |
| 优化器消费 τ | `_endogeneity_penalty`（[L391-L419](../../optimizer.py#L391-L419)）；`lambda_endogeneity` 默认 0（[L113](../../optimizer.py#L113)） | 关闭 | 未见生产传 `threat_levels` |
| E6 估计层（Profile GMM / IVX / DOLS / PFGMM + selector） | `estimate_with_endogeneity_mitigation()`（[L2132](../../pipelines_v2.py#L2132)） | `enable_endogeneity_estimators=False`（[L583](../../pipelines_v2.py#L583)） | 手动 |
| 治理记录字段位 | `GovernanceRecord.tau`（[L395](../../backtest/governance.py#L395)）、`stage`（[L365](../../backtest/governance.py#L365)）、`premium_health`（[L397](../../backtest/governance.py#L397)）、`diagnosis`（[L398](../../backtest/governance.py#L398)） | 字段存在、非必填 | `build()`（[L425](../../backtest/governance.py#L425)）仅测试调用，生产无 emit |
| Layer 3 溢价健康 | `FactorHealthDiagnoser.diagnose()`（[L799](../../modules/factor_health/__init__.py#L799)）+ `_combine_label`（[L1236-L1252](../../modules/factor_health/__init__.py#L1236-L1252)） | 独立模块 | 仅脚本 / demo；`pipelines_v2` 无引用 |

### 10.2 未实现（交互与接线缺口）

1. **τ → premium label 交互完全未接线**：`diagnose()` 签名无 τ / endogeneity 参数（[L799-L803](../../modules/factor_health/__init__.py#L799-L803)）；`_combine_label(return_type, premium_health)` 只做二维映射（[L1236-L1252](../../modules/factor_health/__init__.py#L1236-L1252)）；输出无 `endogeneity_tau` / `endogeneity_flag` / `tau_stage`。
2. **E3 / E5 / E6 均不进入 `fit/transform`**：三个入口都是显式方法，`fit`（[L1191](../../pipelines_v2.py#L1191)）/`transform`（[L1319](../../pipelines_v2.py#L1319)）无调用；仓内非测试调用方只有 `notebooks/demo_v3_3_0.py`。
3. **E3 → `GovernanceRecord` 无生产 emit**，且字段契约不匹配：`premium_health` 声明为 `Optional[float]`（[L397](../../backtest/governance.py#L397)），而 Layer 3 输出字符串标签（ES / TD / ES+TD / stable / suspect / insignificant）——接线前需先改契约。
4. **`return_type` 无生产来源**：`pipelines_v2` 已停用 `StatisticalClassifier`；生产 `diagnose()` 实际只能拿到 `'unknown'`（脚本显式传 `'static'`）。→ §8.1 B5 仍成立。
5. **无 τ 分布 / 判别力证据**：仓内无真实数据 E3 全链路读数；0.3 / 0.7 仅用于「正则化推荐」与 E5 L1，**从未针对标签降级校准**（无已知 DGP 的降级正确率 / 误降级率）。→ B2 / B3 仍成立。
6. **阶段口径未绑定**：默认 `unified`/Static 路径无解耦，S4 输入不存在；无 `tau_stage` 与 `diagnose` 输入阶段校验。→ B1 仍成立。

### 10.3 结论

- **是「部分实现」**：组件层（E3 四阶段、E5 三层、E6 估计层、治理字段位、τ 消费点）基本齐备；系统层（自动调度、τ→标签交互、治理记录落库、生产 `return_type`）均未实现。
- P-009 路径不变：先跑**只读探针**（不接线）产出 τ 分布 + DGP 判别力；证据达标后再按 §8.2 最小形态落地（`endogeneity_tau` + `endogeneity_flag`、保留原 `diagnosis`、opt-in、键数 30→32）。
- 若 τ 集中在 <0.3 或 >0.7，规则无区分度 → 与多断点同理判「不实现」。

---

## §11 τ 加权融合：敏感性、参数设定与学术依据（2026-11-24）

> **2026-11-24 冻结**：本节加权融合已定位为 `heuristic summary v1`，不作为决策基座；裁决与执行状态见 §13 与 [SESSION.md](../../spec/p027-tau-fusion-freeze/SESSION.md)。

### 11.1 代码事实：固定权重线性合成

```
τ_phase = clip( Σ_{m∈M_enabled} w_m·τ_m / Σ w_m , 0, 1 )
w = {oster_delta: 0.4, aet: 0.3, ife: 0.2, lewbel: 0.1}
```

- 权重硬编码于 [`EndogeneityThreatAssessor.__init__`](../../modules/endogeneity_check/core/threat_assessor.py#L31-L36)；orchestrator 无参构造（[L63](../../modules/endogeneity_check/core/diagnostic_orchestrator.py#L63)），`PipelineV2Config` 无权重字段 → **用户不可配置**。
- `M_enabled` 由 `endogeneity_methods` 与 IFE / Lewbel 开关决定（[L547-L549](../../pipelines_v2.py#L547-L549)、[L1855-L1865](../../pipelines_v2.py#L1855-L1865)），分母按实际启用方法归一化（[L74-L79](../../modules/endogeneity_check/core/threat_assessor.py#L74-L79)）。
- 缺失/失败的检查器以 `0.5` 兜底（[L68](../../modules/endogeneity_check/core/threat_assessor.py#L68)）；各 checker 自身也有 0.5 默认。
- 对外 final τ 取 S4（[L180](../../modules/endogeneity_check/core/diagnostic_orchestrator.py#L180)）；若调用方未传 `decoupled_factor`，S4 回退用 `imputed_factor`（[L1912](../../pipelines_v2.py#L1912)）→ final τ 实际等于 S2 τ。
- 报告只保留 `component_taus` / `checker_results`，**不记录权重及其版本**。

### 11.2 敏感性读数

**① 有效权重随开关漂移（同一因子、同一数据，τ 口径不同）**

| 配置 | 有效权重 |
|------|---------|
| 默认 `oster + aet` | oster **0.571** / aet **0.429** |
| `+ IFE` | 0.444 / 0.333 / ife 0.222 |
| `+ IFE + Lewbel` | 0.400 / 0.300 / 0.200 / 0.100 |
| 仅 `oster` | 1.000 |

启用 IFE/Lewbel 会把 oster 的有效权重从 0.571 压到 0.400（−30%），因此 **τ 不能跨配置比较**。

**② 档位翻转（默认权重，阈值 0.3 / 0.7）**

| (τ_oster, τ_aet) | 合成 τ | 档位 | 单方法结论 |
|---|---|---|---|
| (0.9, 0.1) | 0.557 | mild | oster-only → strong |
| (1.0, 0.2) | 0.657 | mild | oster-only → strong |
| (0.1, 0.9) | 0.443 | mild | aet-only → strong |
| (0.9, 0.9) | 0.900 | strong | — |
| (0.2, 0.2) | 0.200 | none | — |

强威胁被弱分量「补偿」：只要加权和 <4.9（即 0.4τ_o+0.3τ_a<0.7），即使 oster=1.0 也只能给 mild。

**③ 秩反转**：A(0.9, 0.1)、B(0.5, 0.5)。默认权重 τ_A=0.557>0.500；权重改为 (0.5, 0.5) 时并列 0.50；改为 (0.2, 0.8) 时 τ_A=0.26<0.50 → A/B 排序翻转。仅当某因子在所有分量上占优时排序才权重无关。

**④ 不确定度未传播**：若 SE(τ_o)=SE(τ_a)=0.10 且独立，则 SE(τ)=0.071；阈值 0.7 附近 ±1.96 SE≈±0.14 → 档位翻转在统计上不可分辨。当前输出无 CI。

**⑤ 不连续点**：Oster 在 |δ|→1 处 τ 从 ≈0 跳到 0.1（[L126-L132](../../modules/endogeneity_check/core/oster_delta.py#L126-L132)）；分母≈0 时 τ=0.0，而 |δ|=∞ 按规则应为 0.1，边界不一致（[L121-L123](../../modules/endogeneity_check/core/oster_delta.py#L121-L123)）。

### 11.3 参数设定问题

1. **权重不可配置、无版本、未入报告** → 权重变更后历史 τ 不可复现、不可审计。
2. **有效权重随开关漂移** → τ 的语义依赖配置，跨批次比较无意义。
3. **0.5 兜底把「未知」当「中等威胁」** → 样本不足/估计失败会静默拉向中位，且与真实 0.5 不可区分。
4. **死参数**：`EndogeneityThreatAssessor.final_threshold`（[L29](../../modules/endogeneity_check/core/threat_assessor.py#L29)）从未使用；orchestrator `_alert_threshold`（[L65](../../modules/endogeneity_check/core/diagnostic_orchestrator.py#L65)）从未使用；config `endogeneity_alert_threshold`（[L553](../../pipelines_v2.py#L553)）未被 `check_endogeneity` 消费（实际传的是 `oster_threat_threshold`，[L1859](../../pipelines_v2.py#L1859)）。`critical_alert` 实际由 S4>S2 / S4>S3 决定（[L169-L176](../../modules/endogeneity_check/core/diagnostic_orchestrator.py#L169-L176)），与阈值无关。
5. **分量量纲不可比**：Oster 是分段映射（0.1/0.9 跳变）、AET 是 |SR| 截断、IFE 是 1−吸收率、Lewbel 是相对 β 偏差——算术平均把它们当等距基数处理。
6. **无不确定度传播 / 无 CI**，阈值附近决策脆弱。
7. **0.3 / 0.7 与权重未联合标定**：阈值是固定常数，权重变化会直接改变档位分布。

### 11.4 学术依据判定

- **方法层有依据**：Oster (2019) δ 与 R_max=1.3R̃；Altonji–Elder–Taber (2005) selection ratio；Bai (2009) 交互固定效应；Lewbel (2012) 异方差内部 IV。
- **融合层无直接统计准则**：四个 τ 回答四个不同问题，**不是同一潜变量的重复测量** → 无共同似然，Akaike/BIC 权重不适用；无重复估计，inverse-variance 权重不适用；τ 不是概率，线性 opinion pool（Genest & Zidek 1986）的校准前提也不成立。
- 可援引的是**复合指标方法学**：OECD/JRC *Handbook on Constructing Composite Indicators*（2008）、Saisana–Saltelli–Tarantola (2005, JRSS-A)、Paruolo–Saisana–Saltelli (2013, JRSS-A)、Greco et al. (2019, *Social Indicators Research*)。其共同要求是：权重显式声明、必须做敏感性/稳健性分析、明确聚合规则的补偿性。当前权重未声明、无敏感性、聚合完全补偿 → **只能定性为工程启发式，不构成统计推断**。
- 与风险治理口径冲突：加权平均允许「高 Oster + 低 AET」互相抵消，而治理语义通常是**最坏威胁主导**。

### 11.5 建议

1. **短期（零代码）**：把 0.4/0.3/0.2/0.1 登记为「先验权重 v1」，报告输出 `weights_version` + 有效权重；显式声明 τ 不可跨配置比较。
2. **P-009 探针纳入权重敏感性**：Dirichlet 权重扰动 + 4 个角点配置，报告 τ 区间、档位翻转率、Spearman 秩相关、阈值穿越率；对分量 τ 做 bootstrap CI。
3. **聚合规则**：默认改非补偿口径（`max` 或 any-rule：任一分量 ≥0.7 → strong、任一 ≥0.3 → mild），或保留加权平均但仅作展示、不作决策输入。
4. **若坚持加权平均**：权重须用已知 DGP 的外部准则（溢价不稳定性 AUC / 决策损失）标定，并与 0.3/0.7 联合标定；在标定完成前不新增消费者（Layer 3 交互）。

---

## §12 因子内生性：学术脉络与可用手段调研（2026-11-24）

### 12.1 先分清「内生性」的六种来源

| # | 类型 | 因子语境下的机制 | 现有覆盖 |
|---|------|-----------------|---------|
| 1 | 遗漏变量 (OVB) | 未观测的风格 / 行业 / 宏观因子使 premium 高估或符号反转 | ✅ Oster δ + AET |
| 2 | 测量误差 (EIV) | 两遍法把**估计的 β** 当作回归元 → 系数衰减、SE 失真（generated regressor） | ⚠️ 仅 Lewbel 内部 IV；无 Shanken 修正 |
| 3 | 反向因果 / 同时性 | 市值、换手率、估值受过去收益影响；因子构造使用同期或未来信息 | ❌ 无专门检验（E4 Granger 只做归因） |
| 4 | 选择偏差 / 数据窥探 | 从数百个候选因子中挑显著（factor zoo、p-hacking） | ⚠️ 多重检验 + spec logger 在 L2/L5，不在 E3 |
| 5 | 交互效应 / 动态面板 | 时变 β 与潜在状态共变（条件因子模型） | ✅ IFE |
| 6 | 缺失选择 | 缺失非随机（MNAR），插补引入选择偏差 | ✅ S1（默认关） |

**关键**：E3 覆盖 1/2/5/6，**不覆盖 3/4**；后两类分别要靠构造期审计与多重检验/预注册，不能靠 E5 正则化。

### 12.2 学术脉络（问题 → 代表文献 → 手段）

| 问题 | 代表研究 | 核心手段 |
|------|---------|---------|
| OVB 敏感性 | Altonji–Elder–Taber (2005)；Oster (2019) | 选择比例 / δ 与 R_max 边界；报告**区间**而非单点 |
| EIV / 两遍法偏差 | Shanken (1992)；Shanken & Zhou (2007)；Kan & Robotti (2009)；Ang–Liu–Schwarz (2020) | Shanken 修正；联合 GMM/ML；个股 vs 组合的权衡 |
| 高维选择与选择后推断 | Belloni–Chernozhukov–Hansen (2014)；Feng–Giglio–Xiu (2020)；Giglio–Liao–Xiu (2021) | Post-Double-Selection Lasso；对遗漏因子稳健的多重检验 |
| 双重稳健 / 正交矩 | Chernozhukov et al. (2018) | Double/Debiased ML；Neyman 正交 |
| 收缩 / 贝叶斯先验 | Kozak–Nagel–Santosh (2020)；Harvey–Liu (2021) | SDF 系数收缩；Lucky Factors bootstrap |
| 潜因子 / 交互效应 | Bai (2009)；Kelly–Pruitt–Su (2019) | 交互固定效应；IPCA（用 characteristics 作工具） |
| 异方差内部 IV | Lewbel (2012) | 无需外部工具的内部 IV |
| 残差化 / 正交化 | Blitz–Huij–Martens (2011) | 对风险因子取残差（residual momentum） |
| 多重检验 / 可复制性 | Harvey–Liu–Zhu (2016)；Hou–Xue–Zhang (2020)；Chordia–Goyal–Saretto (2020) | t 阈值、BH/Bonferroni、复制与样本外 |
| ML 资产定价 | Gu–Kelly–Xiu (2020) | 正则化非线性预测，需严格样本外 |

### 12.3 实践手段：按流水线阶段分层

| 阶段 | 手段 | 作用 | 局限 |
|------|------|------|------|
| 构造期 | point-in-time / 滞后一期；行业+市值+风格中性化；rank/zscore；缩尾 | 从源头消除同期性与异常值驱动 | 不能修复未观测混杂 |
| 构造期 | 组合排序代替个股回归 | 降低 β 的 EIV | 组合压缩 β 离散度，未必然提高 premium 效率（Ang et al. 2020） |
| 诊断期 | Oster / AET / IFE / Lewbel；多重检验；规格日志 | 识别威胁、控制数据窥探 | 诊断不等于修复 |
| 估计期 | Shanken EIV 修正；IV/GMM/IVX/DOLS/PFGMM；IPCA；面板 FE/IFE | 修正偏差、识别因果 | 需有效工具/强假设 |
| 估计期 | Post-Double-Selection Lasso；DML | 高维混杂下的有效推断 | 依赖选择一致性；不能保证无 OVB |
| 正则化 | Ridge / Lasso / ElasticNet | 降方差、变量选择、稳权重 | **有偏**；不识别因果 |
| 正则化 | 贝叶斯收缩 / 层次先验 | 稳定 SDF 权重、改善样本外 | 先验敏感；需标定 |
| 组合层 | 暴露/行业/换手约束 | 控制非预期暴露 | 不改变 premium 估计 |
| 治理期 | 报告 bounds + 敏感性 + holdout + 复制 + 非补偿规则 | 让结论可审计 | 不提升点估计精度 |

### 12.4 关键澄清：正则化不能「修复」内生性

1. **Lasso / ElasticNet / PDS** 处理的是「高维 + 选择偏差」：Feng–Giglio–Xiu 明确指出简单 LASSO 选出的模型不稳定、仍受遗漏变量偏误影响，必须用 double-selection 才能做有效选择后推断。
2. **Ridge / 贝叶斯收缩** 是 bias–variance 权衡：降低方差的同时引入收缩偏差，不消除 OVB/EIV。
3. **E5 的 L2/L3 不是统计正则化**：`α ← α_base(1−γτ)`、`w ← w_raw(1−ρτ)` 没有目标函数、没有理论保证，只是启发式调参；不能作为「内生性已处理」的证据。
4. **唯一能「识别」偏差的手段**是 IV/GMM（需有效工具）、面板 FE/IFE、DML 的正交矩、或 Oster 式**部分识别边界**；其余手段只能缓解或披露。
5. **约束型手段**（暴露中性、换手约束）属于组合风险控制，不是因子内生性的 remedy。

### 12.5 当前 pipeline 的覆盖与缺口

| 手段 | 状态 | 落点 |
|------|------|------|
| 行业/市值中性化 | ✅ 默认开（需数据） | `adapters.NeutralizerAdapter` |
| 因子正交化 | ✅ opt-in | `modules/factor_orthogonalizer` |
| Oster / AET / IFE / Lewbel | ✅ opt-in | E3 |
| 三层正则化 | ⚠️ 启发式，无标定 | E5 |
| GMM / IVX / DOLS / PFGMM | ✅ opt-in | E6 |
| Post-Double-Selection Lasso | ✅ 独立模块，未接线 | `backtest/factor_significance.py` |
| 多重检验（BH/Bonferroni/BY/RW/White RC/Hansen SPA） | ✅ 独立模块 | `multiple_testing.py` |
| 规格日志 / holdout | ✅ opt-in | `specification_logger` / `cross_validation` |
| **Shanken EIV 修正** | ❌ | `PremiumEstimator.estimate_with_errors` 仅 HAC |
| **IPCA** | ❌ | — |
| **DML** | ❌ | PDS 是近亲，不等于 DML |
| **贝叶斯收缩 / 层次先验** | ❌ | — |
| **反向因果专门检验** | ❌ | E4 Granger 仅归因 |
| **组合暴露约束** | ❌ | — |
| **权重敏感性 / 非补偿聚合** | ❌ | §11 |

### 12.6 建议路线

1. **零代码（探针）**：P-009 前置探针增加三项对照——① Oster bounds 与点估计并列；② Shanken 修正 vs 未修正 t 值（离线脚本）；③ 正交化前后 premium / τ 稳定性。先回答「偏差有多大」，再决定是否上线修正。
2. **低风险（可选开关）**：在 `PremiumEstimator.estimate_with_errors` 增加 Shanken (1992) EIV 修正，默认关、零新增依赖；这是两遍法的标准做法，收益明确、风险可控。
3. **中风险（接线）**：把已实现的 Post-Double-Selection Lasso 用于 factor zoo 增量检验，替代「逐因子单独显著性」；仍不进入默认 `fit/transform`。
4. **研究分支（不急）**：IPCA、贝叶斯收缩、DML 需要新依赖或新数据结构，先立研究批次，不并入主线。
5. **治理口径**：报告 component τ + Oster bounds + 权重敏感性；采用非补偿决策规则；明确 E5 是启发式而非「内生性修复」。
6. **反向因果**：先做构造期审计（point-in-time、滞后、同期数据检查），再考虑 IV；不要用 E5 惩罚项代替识别策略。

### 12.7 适用性复核与补全顺序（2026-11-24）

**Shanken 修正不适用于当前 `PremiumEstimator`**：

- 当前架构是「每期横截面回归 `r_{i,t}=α_t+β_t·f_{i,t−1}+ε` → β_t 即溢价 → 核平滑为 λ̂(t)」（[PremiumEstimator.estimate](../../modules/factor_health/__init__.py#L30-L60)），**不存在**「先用估计 β 做第二遍截面回归」的 two-pass 结构。
- Shanken (1992) 修正的对象是 two-pass beta-pricing 中「估计 β 作为回归元」的 generated-regressor 偏差；当前路径没有该环节，直接套用属于错配。
- 当前真正的 EIV 风险是**因子/暴露的测量误差**（attenuation bias）；可行 remedy 是 IV（外部或 Lewbel 内部）、测量误差建模、误差方差已知时的衰减校正、组合排序/rank 降噪。选哪一种需先做适用性审计。
- 若未来新增「估计 β → 第二遍截面回归」的路径，再引入 Shanken 修正。

**补全顺序（三波，全部松耦合）**：

| 波次 | 项目 | 形态 | 风险 | 前置 |
|------|------|------|------|------|
| **Wave 0 适用性审计** | EIV remedy 选择、反向因果可检验边界、IPCA/DML/贝叶斯收缩的数据与依赖评估 | T3 研究备忘录，零代码 | 低 | 无 |
| **Wave 1 低风险可选模块** | ① P-027 Stage 0b 报告字段；② EIV remedy（若审计判定可行）；③ 反向因果诊断（lead-lag / pre-trend / PIT 审计，仅诊断）；④ P-027 Stage 1 权重敏感性 | 独立入口 + 默认关开关 | 低-中 | Wave 0 裁决 |
| **Wave 2 研究分支** | IPCA、DML、贝叶斯收缩 | 独立 research 批次，不接生产 | 中-高（新依赖/数据） | Wave 0 评估 + 独立立项 |

**松耦合约束（每个模块必须满足）**：

1. 独立入口（函数/类），不修改 `fit/transform` 默认路径；
2. 配置开关默认关，命名空间独立；
3. 不新增 τ 消费者，不进入 P-009 / Layer 3；
4. 零新增运行时依赖（Wave 2 若必须新增，单独立项并披露）；
5. 独立单测 + 默认 SHA 逐位不变；
6. 诊断类模块明确写「不构成因果识别」，除非 IV 有效性已检验。

**结论**：可以先补，但顺序是「先审计适用性 → 再补低风险模块 → 最后研究分支」，而不是把 IPCA/DML/贝叶斯收缩一次性接进来；任何模块都不得反向成为 τ 的决策依据。

**P-028 审计结论（2026-11-24）**：Shanken 修正不适用；外部 IV / Lewbel 截面化 / 衰减校正均不具备当前条件；推荐 Wave 1 采用「披露 + 构造变体敏感性」，不做硬修正。详见 [SESSION.md](../../spec/p028-eiv-applicability-audit/SESSION.md)。**Wave 1 实测**：4 因子 × 6 构造变体，4/4 判定构造敏感；rank→normal 效应 +124%~+244%，amihud 在缩尾/市值/行业中性化下均敏感。详见 [EIV_SENSITIVITY_P028.md](EIV_SENSITIVITY_P028.md)。

**参考文献（补充）**

- Altonji, Elder & Taber (2005). *JPE* 113(1), 151-184.
- Ang, Liu & Schwarz (2020). Using Stocks or Portfolios in Tests of Factor Models. *JFQA* 55(3), 709-750.
- Bai (2009). *Econometrica* 77(4), 1229-1279.
- Belloni, Chernozhukov & Hansen (2014). *REStud* 81(2), 608-650.
- Blitz, Huij & Martens (2011). Residual Momentum. *JEF* 18(3), 506-521.
- Chordia, Goyal & Saretto (2020). *RFS* 33(5), 2134-2179.
- Chernozhukov et al. (2018). *Econometrics Journal* 21(1), C1-C68.
- Feng, Giglio & Xiu (2020). *JF* 75(3), 1327-1370.
- Giglio, Liao & Xiu (2021). *RFS* 34(7), 3456-3496.
- Gu, Kelly & Xiu (2020). *RFS* 33(5), 2223-2273.
- Harvey & Liu (2021). Lucky Factors. *JFE* 141(2), 413-435.
- Harvey, Liu & Zhu (2016). *RFS* 29(1), 5-68.
- Hou, Xue & Zhang (2020). *RFS* 33(5), 2019-2133.
- Kan & Robotti (2009). *JF* 64(6), 2617-2649.
- Kelly, Pruitt & Su (2019). *JFE* 134(3), 501-524.
- Kozak, Nagel & Santosh (2020). *JFE* 135(2), 271-292.
- Lewbel (2012). *JBES* 30(1), 67-80.
- Oster (2019). *JBES* 37(2), 187-204.
- Shanken (1992). *RFS* 5(1), 1-33.
- Shanken & Zhou (2007). *JFE* 84(1), 40-86.

---

## §13 路线裁决：τ 融合的冻结、探针与降级（2026-11-24，用户批准）

> **执行状态（2026-11-24）**：Stage 0 文档冻结已完成（[SESSION.md](../../spec/p027-tau-fusion-freeze/SESSION.md) v1.1）；**Stage 1 探针**已执行：G1 16.7% / G2 翻转 18.8% / G3 p=0.317，三项全失败 → **Stage 2 判定：τ 仅展示、E5 experimental、P-009 关闭为「不实现」**（[TAU_FUSION_STAGE1_P027.md](TAU_FUSION_STAGE1_P027.md)）。Stage 0 代码字段（`weights_version` / `effective_weights` / `s4_input_stage` / `stage_fallback` / `experimental`）**T1 已实施并验证**（[IMPLEMENTATION](../../spec/p027-stage0b-disclosure-fields/IMPLEMENTATION.md) / [CHECKLIST](../../spec/p027-stage0b-disclosure-fields/CHECKLIST.md) v1.1 accepted：定向 5 passed、两模块 55 passed、全量回归 2274 passed / 0 failed；包版本 **3.11.2**）；P-027 转为 `done`。

### 13.1 裁决依据

- §11：加权平均权重硬编码、有效权重随方法开关漂移、补偿型聚合、无不确定度传播；0.3 / 0.7 未与权重联合标定。
- §12：四个分量回答不同问题，不是同一潜变量的重复测量；无共同似然、无重复估计、τ 非概率 → 加权融合**不具备统计估计意义上的学术基座**。
- 风险面：E3 / E5 / E6 全部 opt-in（`enable_*=False`），τ 当前仅被 E5、优化器（λ=0）和显著性检验消费，尚未进入默认生产路径 → **有冻结空间，不需要紧急改默认**。

**裁决**：τ 定位为「启发式摘要」，不作为新增决策层的基座；P-009 不启动，E5 标注 experimental；先用只读探针设门槛，证据达标后再谈标定或接线。

### 13.2 三阶段门

| 阶段 | 动作 | 产出 | 通过条件 |
|------|------|------|---------|
| **Stage 0 冻结（现在）** | ① τ 文档定位为 `heuristic summary v1`；② 冻结权重 `0.4/0.3/0.2/0.1`，报告输出 `weights_version` + `effective_weights`；③ E5 标注 experimental，不得表述为「内生性已修正」；④ S4 回退显式标记（未传 `decoupled_factor` 时用 `imputed_factor`，[L1912](../../pipelines_v2.py#L1912)）；⑤ 禁止新增 τ 消费者；⑥ 默认行为零变更 | 文档 + 报告字段 | 不改变任何默认输出 |
| **Stage 1 探针（零生产接线）** | 在 4+ 真实因子上：分量 τ 分布；Oster bounds；Shanken 修正 vs 未修正 t；Dirichlet 权重扰动（1000 次）+ 4 角点；档位翻转率 / Spearman 秩相关；τ 与「溢价不稳定性」的外部关联 | 探针报告（先定版门槛再跑） | G1-G3 全满足（见 13.3） |
| **Stage 2 裁决** | 通过 → 官方标量改为**非补偿** `max` 或 any-rule，加权平均降为展示，并重标定 0.3 / 0.7；不通过 → τ 仅展示，E5 L2/L3 决策语义降级/弃用，P-009 关闭为「不实现」 | 决策记录 + 必要代码 | 仅证据达标才接线 |

### 13.3 预注册门槛（Stage 1 前定版）

- **G1 聚合一致性**：加权平均与 `max` 规则的档位（none / mild / strong）一致率 ≥ 90%。
- **G2 权重稳健性**：Dirichlet 扰动下档位翻转率 ≤ 10%，且 τ 的 Spearman 秩相关 ≥ 0.90。
- **G3 外部效度**：按 τ 高低分组，高 τ 组的溢价不稳定性（如滚动 premium 符号翻转率 / ES-TD 概率 / 断点概率）显著更高（预注册单侧检验 + bootstrap CI）。
- 三条全满足 → Stage 2 判定「标量可用于监控」；任一不满足 → τ 不得进入决策路径。

### 13.4 三条硬规则

1. **不把加权平均当决策依据**。需要标量时用 `max` 或 any-rule（任一分量 ≥0.7 → strong；任一 ≥0.3 → mild），避免任意权重与补偿性。
2. **不校准不决策**。权重与 0.3 / 0.7 阈值必须用外部准则（溢价不稳定性 / 决策损失）标定；未标定前只作展示。
3. **不新增消费者**。P-009 / Layer 3 交互在 Stage 2 通过前不启动；E5 保持 opt-in。

### 13.5 被拒路线

| 路线 | 拒绝理由 |
|------|---------|
| 保留加权平均并调权重 | 无标签可校准，易过拟合；推迟到有外部准则 |
| 直接删除 τ / E5 | 过度；分量诊断仍有信息价值，且默认已关 |
| 贝叶斯潜变量模型 | 需联合似然 / 先验设定，当前数据与理论不支持 |
| 先做 P-009 交互 | 在无基座的标量上再加规则，放大不可审计性 |

### 13.6 Stage 0 代码清单（P-027 实施时执行，本次不写代码）

| # | 改动 | 目的 |
|---|------|------|
| 1 | `final_assessment` / S2-S4 报告补 `weights_version='v1'`、`effective_weights` | 权重可追溯、跨配置不可比显式化 |
| 2 | S4 报告补 `s4_input_stage` / `stage_fallback` 标记 | 区分「解耦后」与「回退到插补后」 |
| 3 | E5 文档与输出标注 `experimental=True` / heuristic 文案 | 防止被当作内生性修复证据 |
| 4 | 默认值零变更 | 保护既有证据逐位不变 |

### 13.7 P-009 准入条件

P-009 仅当以下条件**同时**满足才启动：

1. P-027 Stage 2 判定「标量可用」；
2. G1-G3 全满足，且聚合规则已定为非补偿；
3. 0.3 / 0.7 阈值已用外部准则标定；
4. `tau_stage` 与 `diagnose` 输入阶段完成绑定与校验。

否则 P-009 关闭为「不实现」，与多断点同处置；本裁决登记为 **P-027**（[PROGRESS.md](../PROGRESS.md)）。

**2026-11-24 判定**：Stage 1 的 G1/G2/G3 全失败 → P-009 关闭为「不实现」，不启动交互；τ 仅展示，E5 保持 experimental。
