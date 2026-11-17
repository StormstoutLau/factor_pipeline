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
