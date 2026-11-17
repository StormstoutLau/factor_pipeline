# 多因子治理体系深度优化路线图

> **日期**: 2026-11-17
> **范围**: `PipelineV2` 治理链（L0-L5 + E1-E10）、统计证据链、模型风险治理
> **依据**: 代码回溯（[pipelines_v2.py](../../pipelines_v2.py) / [optimizer.py](../../optimizer.py) / `backtest/` / `modules/`）+ 学术标准 + 业界实践
> **配套**: [内生性-溢价诊断交互分析](ENDOGENEITY_PREMIUM_GOVERNANCE_ANALYSIS.md) §7.5 可比性契约 / [数据缺口诊断](DATA_GAPS_DIAGNOSIS.md) / [数据层治理复审](DATA_LAYER_GOVERNANCE_REVIEW.md)
> **状态**: 方案已定稿（含第三轮复审修正，见 §15）；P0 四项已登记 PROJECT_STATUS，P1/P2 待排期；数据层治理拆分与 A 股口径修正见 [数据层治理复审](DATA_LAYER_GOVERNANCE_REVIEW.md)（专项 A/B 另立，版本暂定）

---

## §1 结论摘要

**当前框架不是缺组件，而是缺契约与闭环。**

- 治理件基本齐备（E1-E10、多重检验、断点、健康度、消融、规格日志、指纹监控），
  但默认只启用「单因子预处理 + 指纹监控」，其余全部 opt-in 且手动调用；
- 治理信号分散在多个 dict，没有统一记录；
- 统计证据链缺三块关键拼图：**样本外协议（purged CV/CPCV）、过拟合校正（DSR/PBO）、
  统一多重检验台账**；
- 没有模型分级、独立验证、变更管理——缺 SR 11-7 式模型风险治理。

**优化主轴**: 数据契约 → 统计证据链 → 模型风险治理，而不是继续增加因子模型。

**三期**: P0 治理底座（4 件）→ P1 统计证据链（6 件）→ P2 运营闭环（4 件）。

---

## §2 现状差距（代码核对）

| 维度 | 已有 | 缺口 | 后果 |
|------|------|------|------|
| 数据契约 | 加载器、`CacheKey` 指纹 | 新鲜度守卫、point-in-time 校验、universe 快照 | 样本漂移不可察觉（mv 停更 5 日即实例） |
| 处理契约 | arm 全局开关、中间数据、消融开关 | 统一 `GovernanceRecord`、golden master 强制 | 升级后不可比、不可重放 |
| 统计证据 | HAC SE、BH/Bonferroni/BY/Romano-Wolf/White RC/Hansen SPA、双重 Lasso、sup-F/Bai-Perron | **未接线**；无统一分母；无 DSR/PBO；无 purged CV | p 值可被"挑变体"污染；全样本回测高估 |
| 组合/容量 | 容量压力测试、多头端研究 | 未成为上线门禁 | 研究结论与生产决策脱节 |
| 监控 | 指纹迁移、结构突变、CUSUM、IC/阈值漂移 | 默认关、无调度、无 runbook | 告警不闭环 |
| 决策治理 | SpecificationLogger、决策桥 | 无模型清单/分级/独立验证/变更管理 | 无法审计"为什么上线" |
| 内生性 | E3 τ 生产完整、E5 三层 | 消费端分散（已有 3 处） | 重复惩罚/口径不一 |

**默认路径事实**（[pipelines_v2.py L1183-L1192](../../pipelines_v2.py#L1183-L1192)）：
`pipeline_mode='unified'` → 全部因子走 Static；`dynamic_ab` → 全部走 Dynamic；
分类器只产诊断标签、不参与路由（v3.4.0 ADR-042）。

---

## §3 目标架构：六层 + 三条横切

```
L5 模型风险治理  FactorRegistry / Tiering / 独立验证 / 签核 / 变更管理
L4 监控与响应    漂移 / 断点 / IC / 容量 / 告警路由 / Runbook / 自动降级
L3 组合与执行    权重 / 容量 / 冲击成本 / 执行约束 / 容量门禁
L2 统计证据      多重检验 / HAC / 样本外 / DSR / PBO / 断点 / 敏感性
L1 处理契约      arm label / config hash / invariants / golden master
L0 数据契约      freshness / point-in-time / universe snapshot / lineage
────────────────────────────────────────────────────────────
横切 A: 实验登记（预注册 / 规格曲线 / 试验次数台账）
横切 B: 审计链（code commit / config / data hash / seed）
横切 C: 独立性（开发 / 验证 / 审批角色分离）
```

**设计原则**:

1. **单一真相源**: 所有治理结论落 `GovernanceRecord`，报告只引用 record id；
2. **默认零变更**: 新增治理一律 opt-in，默认路径逐位不变；
3. **分级治理**: 按 Tier 决定治理强度，避免全量跑全套；
4. **证据链可审计**: 每个结论可回答「哪份数据、哪版代码、跑了多少次、校正后 p/q、OOS 多少、容量多少、谁验证」。

---

## §4 核心对象

### 4.1 `GovernanceRecord`

```
record_id            # 确定性 hash(code_commit, config, data_snapshot, factor, stage, seed)
batch_id             # 批次标识（同批因子共享 family 与 holdout）
parent_id            # 父 record（组合层 record 指向单因子 record）
experiment_id        # 实验/研究项目标识（跨批次聚合）
factor_id
stage                # S1/S2/S3/S4 或 'final' 或 'portfolio'
arm                  # 'static' | 'dynamic' | 'mixed'
pipeline_version     # 语义版本
config_hash
construction_code_hash  # 因子构造代码版本（防同因子不同构造混淆）
data_snapshot        # 各字段最后满覆盖日 + 文件指纹
universe_version     # 池快照 hash
universe_bias        # 池构造偏差口径（point_in_time / current_snapshot_backfilled / unknown；数据层复审 H2）
sample_window        # start/end
split_id             # train/valid/test 切分 + embargo（无则 'in_sample'）
holdout_locked_at    # holdout 锁定时间戳（S0 登记时写入，后续不可更改）
benchmark_id         # 基准口径（等权池/指数 + 停牌口径）
price_convention     # 价格复权口径（hfq / raw+adj_factor；禁 qfq 防回归；数据层复审 H3）
return_convention    # forward return 构造（月末 close-to-close / 复权 / 停牌与涨跌停处理；数据层复审 H7）
tradable_convention  # ST/停牌/涨停过滤口径（枚举 + 代理口径披露）
cost_model           # fee_bps / 单双边 / 冲击模型版本
sign_convention      # 因子方向（数值大 = 预期收益高）
seed
tau                  # E3 威胁分（如有）
health_score         # FactorHealthMonitor
premium_health       # stable/ES/TD/ES+TD/suspect/insignificant
diagnosis            # pricing/monitor/recalibrate/review/suspect
p_value / q_value / n_trials / test_family
effect_size / ci     # 效应量（λ̂ 均值 / IC 均值 / Sharpe）+ 置信区间
dsr / pbo / oos_metric
capacity_estimate    # 容量点估计与口径
drift_alerts         # 监控告警快照
gate_status          # G0-G5 逐项通过/失败
mode                 # 'research' | 'production'（研究可空 G4/G5，生产必填）
reviewer / timestamp(UTC) / evidence_uri
env_fingerprint      # 包版本 / BLAS / 线程数（可复现性）
```

> 口径强制项（复审补充）：`benchmark_id`、`price_convention`、`return_convention`、`tradable_convention`、
> `cost_model`、`sign_convention`、`split_id`、`universe_bias` 为必填；缺任一项 record 不得入库。
> （`price_convention`/`universe_bias` 为数据层复审新增，枚举见 DESIGN §5.7；`universe_bias` 缺省 `unknown`。）
> 第三轮复审新增必填：`batch_id`、`experiment_id`、`construction_code_hash`、
> `holdout_locked_at`（S0 登记时写入）、`mode`；`effect_size`/`ci` 在 S3 及以后阶段必填；
> 组合层与复检 record 的 `parent_id` 必填。
> `store` 为 append-only（不覆盖历史），与 PROJECT_STATUS 通过 record_id 互相引用。

### 4.2 `FactorCard`

面向人与下游系统的因子卡：构造定义、样本区间、数据依赖、已知失效模式、
容量口径、最近一次治理结论、Owner、Tier。

### 4.3 `GateResult`

```
gate(G0-G5), passed(bool), reasons[], evidence_refs[], action(block/downgrade/allow)
```

---

## §5 三期方案

### P0 治理底座（不改因子逻辑，先行）

#### P0-1 `GovernanceRecord` + 存储

- **目标**: 统一治理记录，消除信号孤岛；
- **实现**: 新增 `backtest/governance.py`（`GovernanceRecord` / `GovernanceStore`）；
  存储复用 `backtest/fingerprint_performance_logger.py` 的 DuckDB 模式，JSONL 兜底；
- **接入点**: 新增 emit 钩子（`PipelineV2.fit` 末尾 + 研究脚本出口），
  **不依赖 `SpecificationLogger` 开关**（其默认关闭）；`_log_spec` 仅复用其输出格式；
- **验收**:
  - 往返序列化/反序列化一致；schema 版本与缺字段校验；
  - record_id 确定性（同输入同 id）；
  - 默认路径零变更（不传 store 时行为不变）；
  - 单测覆盖：正常/缺字段/旧版本 schema。

#### P0-2 数据契约守卫

- **目标**: 让"同样本"可验证，避免静默 stale；
- **实现**: 新增 `backtest/data_contract.py`，`check_data_contract(root, sample_end, max_lag=1)`；
  - 字段：price/adj/amount/volume/mv/suspend/return（+ open/high/low/name 可选）；
    **数据层复审 H1 修正**：volume/suspend/open/high/low/return/name 文件**已存在**（`stock_*`），
    仅 `load_market` 未加载——属"接入"而非"数据缺口"；suspend 为 'S'/'R' 事件表需重建逐日状态，
    name 为历史名称面板可推导 ST 代理；契约词汇/枚举见 DESIGN §5.7；
  - 判定：各字段「最后满覆盖日 ≥ 样本末 − N 交易日」，**默认 N=1**（按字段可配；
    mv 容忍 ≤1 交易日，price/amount 要求当日）；
  - PIT：`list_date ≤ 当日`；universe 快照 hash；缺失率阈值；
    （公告日/成分股生效日若数据不可得，降级为披露项而非阻断项）
  - 模式：`strict` 抛错 / `warn` 告警（**strict 默认关闭**，否则违背默认零变更）；
- **验收**:
  - 复现 mv 停更场景（2026-01-23 vs 2026-01-30，缺口 5 个交易日）→ **必须失败**；
  - 正常数据 → 通过；误报率 0（对现有全样本）；
  - 研究脚本前置调用（至少接入容量/多头端脚本）。
- **数据层治理拆分（数据层复审）**: 契约词汇/枚举/检测接口并入本批次（GR-2）；
  数据接入层（DataPortal/多源 reader/字段字典/lineage）另立**专项 A**（数据多已存在，可先行，不被 B 阻塞）；
  真实数据缺口（barra/行业换源、历史成分、公告日）另立**专项 B**（外部采购周期不可控）。
  详见 [数据层治理复审 §4](DATA_LAYER_GOVERNANCE_REVIEW.md)。

#### P0-3 Golden master 回归基线

- **目标**: 保证升级不改默认口径；
- **实现**: `backtest/golden_master.py` + `tests/golden/` 小样本 parquet；
  - 基线：默认 `unified` Static 管道的 4 因子 + composite，逐月输出；
  - 比较：1e-10 容差；配置变更时输出差异报告；
  - 环境：记录并固定 BLAS/线程（容差内允许浮点重排差异，禁止跨环境 bitwise 断言）；
- **验收**:
  - 默认路径 0 差异；
  - 故意改一个参数（如 percentile 1/99→2/98）→ 必须报差异；
  - 接入 CI/回归脚本。

#### P0-4 多重检验台账

- **目标**: 统一分母，消除"只报最优变体"；
- **实现**: `backtest/multiple_testing_ledger.py`；
  - 记录 `family_id / variant_id / factor / spec_hash / metric / p / q / n_trials / decision`；
  - 复用 `backtest/multiple_testing.py` 的 BH/Bonferroni/BY/Romano-Wolf/White RC/Hansen SPA；
  - 输出 Markdown/JSON 报告；
- **口径先行（复审补充）**:
  - `family_id` = 研究问题 × 因子池 × 变体集合的预注册分组，禁止事后按结果重新分组；
  - **预注册时点：必须在 S0 登记时完成（早于任何数据处理与结果观察）**，不得在 S1/S2/S3 看到数据后调整；
  - `n_trials` 含全部已执行试验（含调试/失败/中途放弃），不得只计"进入报告的变体"；
  - **批次级 family**：同批（`batch_id`）所有因子必须纳入同一 family 或显式声明子 family 划分依据；
- **验收**:
  - BH 场景：与参考实现（`backtest/multiple_testing.apply_bh_fdr`）在 q 值与显著掩码上一致（≤1e-12）；
    其它方法（Romano-Wolf/White RC/Hansen SPA）输出**校正 p 而非 q**，按各自口径对账，不得混用；
  - 报告必须含 `n_trials` 与 `family_id`；
  - 未登记变体不得进入结论。

### P1 统计证据链

1. **样本外协议**: purged K-fold / CPCV + embargo；holdout 一次性锁定（复用 `enforce_test_set_once`）；
   **锁定时点：S0 登记时写入 `holdout_locked_at`，后续阶段不得更改**；
   **跨批次隔离：不同 `batch_id` 不得共用同一 holdout 窗口，或采用 CPCV 多路径避免复用**；
2. **DSR + PBO**: 组合层报告 Deflated Sharpe Ratio 的**显著性概率**（阈值预注册，示例 >0.95）；
   策略搜索报告 **PBO（由 CSCV 估计的回测过拟合概率）**，阈值预注册（示例 <0.1）；
3. **L2 多重检验升级**: 默认 BH-FDR（q 值）；重要结论加 Romano-Wolf / White RC /
   Hansen SPA（**FWER 校正 p 值**，与 FDR q 分开报告）；可选接入
   Giglio-Liao-Xiu 的 factor-model-adjusted 检验；
4. **规格曲线**: 扩展 `SpecificationLogger`，输出 spec curve 与联合推断；
   **S3 证据包必须附 spec curve（或声明为何只跑单一规格），防 forking paths**；
5. **效应量强制**: S3 证据包必须含效应量（λ̂ 均值 / IC 均值 / Sharpe）+ 置信区间，
   不得只报 p/q 值（学术标准：p 值 + 效应量 + CI 三件套）；
6. **组合层多重检验**: 将 K 个因子组合本身视为新检验，S4 组合评估需登记为独立 variant
   进入同一 family 或新 family，不得跳过校正。

**门禁**: 不通过 G2 的因子不得进入 L3。

### P2 运营与组合闭环

1. **容量/执行门禁**: 把容量研究变成 G3.5 硬约束（p95 参与率、容量上限、执行天数）；
2. **模型分级 + 独立验证 + challenger**: Tier 1 因子独立复算 + 影子组合；
3. **监控调度 + Runbook**: `BreakMonitorScheduler` 接入管线；告警分级/去重/owner/自动降级；
4. **变更管理**: 治理规则版本化、回滚、历史重放。

### §5.5 新因子接入 SOP（S0-S6）

> 第三轮复审补充：原方案「定义了判据，但没有定义作业流程」。本节给出一批未处理因子的规范接入流程；
> 阶段-门禁映射按 L1 修正（S4 对应 **G3.5 组合准入**，而非 G3 稳健性）。

| 阶段 | 动作 | 对应门禁 | 必备产物 |
|------|------|---------|---------|
| S0 登记 | 建立 FactorCard；登记 `batch_id`/`experiment_id`；**预注册 family 与检验轨（FDR/FWER）**；**锁定 holdout 并写入 `holdout_locked_at`**；声明 `construction_code_hash` 与口径强制项 | —（登记前置） | FactorCard + 预注册记录 |
| S1 数据 | 运行数据契约检查；披露已知缺口（mv 停更 / barra 与行业 2023-06 后断档） | G0 | 数据契约报告 |
| S2 处理 | 按全局 arm 运行管道（unified→Static / dynamic_ab→Dynamic）；记录 config hash 与不变量 | G1 | GovernanceRecord(stage=S2) |
| S3 统计证据 | HAC/FM + 多重检验校正（按预注册轨）；OOS；DSR/PBO；断点/中性化/子区间稳健性；**附 spec curve、效应量 + CI**；**剔除幻影清仓月**；2023-06 后无风格/行业控制须披露 | G2 + G3 | 证据包 |
| S4 组合评估 | 与现有池相关性/冗余、增量 α、权重方案、容量/冲击成本；**组合登记为独立 variant 进多重检验校正** | **G3.5** | 组合准入报告 |
| S5 风险与上线 | Tier 分级；独立验证/复算；监控接入、Runbook、回滚方案 | G4 + G5 | 验证报告 + 运维清单 |
| S6 运行期 | 漂移/断点/IC/容量监控；按 §5.6 触发复检 | L4 | 告警与处置记录 |

**关键规则**:

1. **S0 是唯一预注册时点**: family、检验轨、holdout、阈值（DSR/PBO 等）必须在 S0 定稿，早于任何数据处理与结果观察（L2 修正）；
2. **批次级 family**: 同批因子全部纳入同一 family，或显式声明子 family 划分依据；不同批次不得共用同一 holdout 窗口（或采用 CPCV 多路径）；
3. **研究/生产分支（B9）**: 研究态（`mode='research'`）可止于 S3/S4，G4/G5 可空；进入生产必须走完 S5 且字段全必填；
4. **数据缺口披露（B5）**: S1 发现已知缺口（mv 2026-01-23 停更、barra/行业 2023-07-31 后断档）必须写入 record `data_snapshot` 并在证据包披露，不得静默使用 stale 数据；
5. **幻影月剔除（B6）**: S3 换手/分位统计必须剔除末月幻影清仓（ret.shift(-1) 缺失 → w=0 → |Δw|=1.0），与容量压力测试口径一致；
6. **治理不改因子值（C2）**: L2 及以上只产证据与决策，不回写因子值；唯一例外是 L1 正交化 hook（opt-in，属处理契约层）；内生性正则化（`apply_endogeneity_regularization`）只输出配置建议，需显式应用；
7. **可比性**: S2 必须满足 [可比性契约 C1-C7](ENDOGENEITY_PREMIUM_GOVERNANCE_ANALYSIS.md#L211-L277)（同臂/同样本/同分母/同不变量/同版本，一次只改一层，默认零变更）。

### §5.6 因子生命周期（退役 / 复检 / 传播）

> 第三轮复审补充（B1/B2/B3/B7）：原方案只覆盖「准入」，未覆盖「退出与再进入」。

1. **退役/下线（B1）**:
   - 触发: G2/G3 复检失败、监控告警超期未闭环、数据源永久缺失、容量不再满足目标 AUM；
   - 动作: record 标记 `retired`（append-only，不删历史），移出组合，FactorCard 同步状态；
   - **冷却期与再申请**: 退役因子须经过冷却期（时长预注册，示例 ≥1 季度）方可再申请；再申请走完整 S0-S5，不得复用旧 holdout（已被消费）；
2. **监控 → 复检触发（B2）**:
   - 指纹迁移 / 结构断点 / IC 衰减超预注册阈值 / 容量击穿 → 自动创建复检任务（新 record，`parent_id` 指向原 record）；
   - 复检使用新数据窗口，不得回改原 record 结论；
   - 告警必须有 owner 与处置时限（与 §10 反模式 7 一致）；
3. **成本模型更新传播（B7）**:
   - `cost_model` 版本变更（fee/冲击模型）时，必须枚举受影响的全部 record 并重估容量/净超额结论；
   - 重估结果写新 record（`parent_id` 引用旧 record），旧 record 保留供审计；
4. **构造版本变更（B3）**: `construction_code_hash` 变化视为新因子变体，重新登记进 family，不得沿用旧 record 的统计结论。

---

## §6 门禁决策矩阵

| Gate | 通过条件 | 证据 | 失败动作 |
|------|---------|------|---------|
| G0 数据 | 各字段最后满覆盖日 ≥ 样本末 − 1 交易日（按字段可配）；PIT 通过或降级披露；universe 快照存在 | 数据契约报告 | 阻断，不出数 |
| G1 处理 | arm label；config hash；**因子输出不变量**：截面均值≈0、方差≈1、NaN 率；**组合权重不变量**：行和 ∈{0,1} | `GovernanceRecord` | 回滚或重跑 |
| G2 统计 | FDR 轨 q<0.05 **或** FWER 轨校正 p<0.05（预注册其一）；OOS 同向；DSR 显著性概率 >0.95（预注册）；PBO<0.1（预注册，由 CSCV 估计） | 证据包 | 降级为 monitor，不进组合 |
| G3 稳健 | 子区间同向；断点/中性化通过；**2023-06 后无风格/行业控制时必须显式披露**（纯稳健性，不含组合构建/容量准入） | 稳健性报告 | 降级为 monitor 或标注 |
| G3.5 组合准入 | 与现有池相关性/冗余 ≤ 预注册阈值；增量 α 显著（经多重检验校正）；权重方案不变量通过；容量/冲击成本满足目标 AUM（p95 参与率、容量上限、执行天数） | 组合准入报告 | 不得进入组合（可留研究池） |
| G4 风险 | Tier 分级；独立验证或等效独立复算；challenger | 验证报告 | 不得上线 |
| G5 上线 | 监控接入；Runbook；回滚方案 | 运维清单 | 不得上线 |

> 门禁只约束**上线/生产决策**，不阻塞研究计算；研究态与生产态字段分离
> （`mode='research'` 可留空 G4/G5，`mode='production'` 必填全部）。
> G3 为纯稳健性门禁；组合构建与容量准入属 **G3.5**（第三轮复审 L1 修正，见 §15）。

---

## §7 学术标准映射

| 学术要求 | 标准做法 | 本仓库现状 | 升级动作 |
|---------|---------|-----------|---------|
| FM 回归 EIV/序列相关 | Shanken 修正 / HAC | `PremiumEstimator.estimate_with_errors` | 接入 L2 报告，默认 HAC CI |
| 多重检验 FWER/FDR | BH/Bonferroni/BY/Romano-Wolf/White RC/Hansen SPA | 模块齐全但未接线 | P0-4 台账，统一分母 |
| 遗漏因子稳健的多重检验 | Giglio-Liao-Xiu (2021) | 无 | P1 可选升级 |
| 回测过拟合/选择偏差 | Deflated Sharpe（显著性概率，Bailey & LdP 2014）；PBO（由 CSCV 估计） | 仅文档引用，无实现 | P1 实现，作为 G2 门禁（概率阈值预注册） |
| 样本外与信息泄漏 | Purged K-Fold / CPCV + embargo | DECISIONS 标"远期" | P1 实现 |
| 结构性断点 | sup-F / Bai-Perron / AR(1) sieve | 已实现 (v3.5.0-v3.5.3) | 保留，作为 G3 证据 |
| 遗漏变量敏感性 | Oster (2019) / AET (2005) | 已实现（默认关） | 保留；补充符号反转警告 |
| 规格搜索偏差 | Specification curve (Simonsohn 2020) | `SpecificationLogger` 雏形 | P1 扩展 |
| 因子可复现基准 | Chen & Zimmermann (2022) | 无 | 仅作**方法参照**（美股数据，不做 A 股数值对账） |
| 可复现性 | code/config/data/seed 四元组 | `CacheKey` 部分具备 | 写入每条 record |

---

## §8 业界实践映射（SR 11-7 三支柱）

| SR 11-7 要求 | 本方案落地 |
|-------------|-----------|
| Model inventory | `FactorRegistry` + `GovernanceRecord` |
| Independent validation | 独立验证脚本/角色；challenger 与影子组合 |
| Ongoing monitoring | L4 告警 + 定期重估 + 触发式复核 |
| Change management | 版本、回滚、重放；变更前后 golden master 对账 |
| Model tiering | Tier 1-3，按资金暴露/复杂度/可解释性分级 |
| Model card | `FactorCard` |
| Data lineage | 数据快照 + 转换链 + record id |
| Alert fatigue | 告警分级、去重、owner、runbook |

**核心**: 前沿实践的落点是**证据链**，不是工具数量。

---

## §9 与内生性-溢价交互的关系

- 交互只是 G3/G4 的一个证据项，**不应先于治理底座落地**；
- τ 统一写入 `GovernanceRecord`，策略层**只消费一次**（明确 E5 与标签层分工），避免第 4 个消费者；
- 阶段口径（S2/S3/S4）由 record 的 `stage` 字段强制绑定，解决阶段错配；
  落地时需提供 `validate_stage_alignment(record, tau_stage)`：不一致直接拒绝写入；
- 交互的可比性要求见 [分析文档 §7.5](ENDOGENEITY_PREMIUM_GOVERNANCE_ANALYSIS.md#L211-L277)。

---

## §10 反模式（明确不做）

1. 不恢复逐因子 Static/Dynamic 路由——破坏可比性；
2. 不引入未校准硬阈值（如 τ>0.7 直接降级）；
3. 不在治理底座完成前上 ML 因子/复杂组合——无法归因；
4. 不全量治理——按 Tier 分级，否则成本爆炸；
5. 不堆指标——DSR/PBO 依赖假设，必须报告假设与试验次数；
6. 不把"独立验证"形式化——同一人开发+验证无效；
7. 不让告警无主——每条告警必须有 owner 与 runbook。

---

## §11 验收与度量

| 指标 | 目标 |
|------|------|
| `GovernanceRecord` 覆盖率 | 100%（所有研究报告与决策；**记录全覆盖 ≠ 全强度治理**，Tier 决定治理深度） |
| `n_trials` / `q_value` 报告率 | 100% |
| Golden master 通过率 | 100%（默认路径） |
| 数据契约拦截率 | 真实缺口 100% 拦截，误报 0 |
| G2 通过率 | 按季度统计，作为因子准入基线 |
| 告警闭环率 | 100% 有 owner 与处置记录 |

---

## §12 参考

- Oster (2019), *JBES* 37(2):187-204; Altonji, Elder & Taber (2005), *JPE*.
- Bai (2009), *Econometrica* 77:1229-1279; Shanken (1992), *RFS*.
- Harvey, Liu & Zhu (2016), *RFS* 29(1):5-68.
- Bailey & López de Prado (2014), *JPM* 40(5):94-107 (Deflated Sharpe).
- Bailey et al. (2017), *J. Computational Finance* (PBO).
- Giglio, Liao & Xiu (2021), *RFS* 34(7):3456-3496.
- Simonsohn, Simmons & Nelson (2020), *Nature Human Behaviour* (specification curve).
- Chen & Zimmermann (2022), *Critical Finance Review* (Open Source Asset Pricing).
- López de Prado (2018), *Advances in Financial Machine Learning* (purged CV).
- Federal Reserve / OCC, SR 11-7 (Model Risk Management).
- 项目内: [可比性契约](ENDOGENEITY_PREMIUM_GOVERNANCE_ANALYSIS.md#L211-L277) /
  [数据缺口诊断](DATA_GAPS_DIAGNOSIS.md) / [容量压力测试](PORTFOLIO_CAPACITY_IMPACT_STRESS.md)。

---

## §13 独立复审修订记录（2026-11-17）

复审范围：逻辑断言合理性、自洽性、学术严格度、盲区。方法：代码逐段复核 + 文献口径核对。
结论：方案方向成立，发现 3 处 P0（门禁失效）、6 处 P1（学术/表述）、10 项盲区，已全部修订。

### P0（门禁失效）

| # | 发现 | 处置 |
|---|------|------|
| F1 | freshness 阈值「样本末 − 5 交易日」恰好放过当前 mv 缺口（1-23 → 1-30 恰 5 日），P0-2 验收"复现缺口→失败"不成立 | 默认 N=1（按字段可配；price/amount 要求当日）；验收改为"当前 5 日缺口必须被拦截"（§5 P0-2、§6 G0） |
| F2 | G2 的 `DSR>0` 与 `PBO<0.5` 学术上过弱/过宽；`PBO/CSCV` 把估计方法当并列指标 | DSR 改为显著性概率 >0.95（预注册）；PBO<0.1（预注册，由 CSCV 估计）（§5 P1、§6 G2、§7） |
| F3 | G2 把 FDR q 与 FWER p 混用（Romano-Wolf/White RC 输出校正 p，不是 q） | 改为「FDR 轨 q<0.05 或 FWER 轨校正 p<0.05，预注册选其一，分开报告」（§5 P0-4、§5 P1、§6 G2） |

### P1（学术严格度/表述）

| # | 发现 | 处置 |
|---|------|------|
| F4 | P0-1 接入点 `_log_spec` 在 `enable_specification_logger=False` 时不产出，不能作默认接入点 | 改为新增 emit 钩子，与 SpecificationLogger 解耦（§5 P0-1） |
| F5 | P0-4 要求与手工 BH「逐位一致」过严且未区分其它方法 | BH 场景与参考实现对账；Romano-Wolf 等按各自校正 p 口径，不混用（§5 P0-4） |
| F6 | Chen-Zimmermann 作「因子可复现基准」易误导为数值对账 | 改为「仅作方法参照（美股数据，不做 A 股数值对账）」（§7） |
| F7 | G1 不变量把因子截面 z 与组合权重行和混为一谈 | 拆为「因子输出不变量」与「组合权重不变量」（§6 G1） |
| F8 | `return_type` 断言过强：研究脚本显式传 `'static'`，`recalibrate→review` 可达 | 已同步修正分析文档 §6 代价表与 §8.1 B5 |
| F9 | 「无生产级组合权重优化」过强：`EndToEndThresholdOptimizer` 优化的是管道阈值/参数，不是组合权重 | 已同步修正分析文档 §7.1 L3 行；补 `optimize()` 代码核对 |

### 盲区（已补入 record 字段或门禁）

| # | 补充 |
|---|------|
| B1 | `benchmark_id`（等权池/指数 + 停牌口径）入 record |
| B2 | `return_convention`（T+1/复权/停牌与涨跌停处理）入 record |
| B3 | `tradable_convention` + `cost_model`（fee/单双边/冲击模型版本）入 record |
| B4 | `sign_convention`（因子方向）入 record，防符号翻转 |
| B5 | `split_id`（train/valid/test + embargo）入 record |
| B6 | `family_id` 预注册分组、`n_trials` 含全部已执行试验（§5 P0-4） |
| B7 | PIT 规则：公告日/成分股生效日不可得时降级为披露项（§5 P0-2、§6 G0） |
| B8 | 独立性的等效实现：独立复算/第二实现/golden master 对账（§6 G4） |
| B9 | 研究态与生产态字段分离（§6 注）；strict 默认关闭（§5 P0-2） |
| B10 | `env_fingerprint`（包/BLAS/线程）与 append-only 存证（§4.1）；golden master 禁跨环境 bitwise 断言（§5 P0-3） |

### 门禁补充

- G3 增加「2023-06 后无风格/行业控制时必须显式披露」（§6 G3）；
- §9 增加 `validate_stage_alignment(record, tau_stage)` 要求；
- §11 注明「记录全覆盖 ≠ 全强度治理」。

### 复审结论

**修订后方案可作为执行基线**；本次仅文档修订，未改生产代码。
遗留需实证校准的参数：DSR 概率阈值（示例 0.95）、PBO 阈值（示例 0.1）、freshness 各字段容忍天数，
均须在 P0/P1 实施时预注册，不得直接沿用示例值。

---

## §14 二次独立复核（2026-11-17）

**方法**：逐项核验 §13 声称修订是否真实落地（19/19 项对照正文）；grep 全文档库扫描残留旧口径；
通读修订后正文检查内部自洽；与 PROJECT_STATUS GR 表交叉核对。

**结果**：

| 核验项 | 结果 |
|--------|------|
| §13 修订落地（F1-F9 / B1-B10 / 门禁补充） | **19/19 逐项落地确认**（§4.1 / §5 / §6 / §7 / §9 / §11 均含对应内容） |
| 路线图内部自洽（P0-2 ↔ G0 / P0-4 ↔ G2 / P1 ↔ G2 / §11 ↔ P0-2） | 一致 |
| PROJECT_STATUS GR-1~GR-4 验收口径 ↔ 路线图 | 一致（max_lag=1 / 口径强制项 / append-only / BH 对账与 FWER 分离均已同步） |

**发现并修正的跨文档残留（2 处）**：

| # | 发现 | 处置 |
|---|------|------|
| R1 | [数据缺口诊断 §5](DATA_GAPS_DIAGNOSIS.md) P1 行仍写「−5 交易日」，与修订后 N=1 口径矛盾（同一规则两份文档两个阈值） | 已改为默认 N=1 并注明原口径恰好放过 mv 5 日缺口、以路线图 §5 P0-2 为准 |
| R2 | [内生性分析 §7.5](ENDOGENEITY_PREMIUM_GOVERNANCE_ANALYSIS.md) C5/S0 仍写「逐位一致」，与路线图 §5 P0-3「1e-10 容差 + 禁跨环境 bitwise」存在口径差 | 已统一为「同环境 1e-10 容差，跨环境禁 bitwise」并互链 |

**二次复核结论**：**通过**。修订后方案（含全部跨文档口径）已自洽，可作为 GR-1 至 GR-4 的执行基线。
本复核仅文档修订，未改生产代码。

---

## §15 第三轮复审记录：管线 × 治理关系分析（2026-11-17）

**复审对象**: 上一轮「单因子管线 × 多因子治理关系与新因子接入流程」分析（含 SOP S0-S6 建议）。
**方法**: 逻辑断言复核 + 学术口径核对 + 盲区扫描 + 自洽性检查。
**结论**: 分析主体断言成立（治理基座与单因子管线是「契约 + 证据 + 门禁」关系而非替代；已约定/缺口清单成立），
但发现 2 处逻辑错误、5 处学术缺口、9 项盲区、2 处自洽性澄清，已全部写入本路线图。

### 逻辑错误（L）

| # | 发现 | 处置 |
|---|------|------|
| L1 | SOP 把 S4（组合评估）映射到 G3，但 G3 是稳健性门禁，不是组合构建 | 新增 **G3.5 组合准入**门禁（§6）；S4 映射 G3.5（§5.5）；容量硬约束由 G3 移至 G3.5（§5 P2） |
| L2 | 预注册时点写「S3 之前」，允许看到数据后调整，违背预注册定义 | 改为 **S0 登记时定稿，早于任何数据处理与结果观察**（§5 P0-4、§5.5 规则 1） |

### 学术缺口（A）

| # | 发现 | 处置 |
|---|------|------|
| A1 | holdout 锁定时点未定义；跨批次复用 holdout 造成信息泄漏 | S0 写入 `holdout_locked_at`；不同批次不得共用 holdout 或采用 CPCV 多路径（§5 P1-1、§4.1） |
| A2 | 只报 p/q，无效应量与置信区间 | S3 证据包强制效应量 + CI（p 值 + 效应量 + CI 三件套）（§5 P1-5、§4.1） |
| A3 | spec curve 可选，无法防 forking paths | S3 必附 spec curve 或声明单一规格理由（§5 P1-4） |
| A4 | K 因子组合本身是新检验，原方案未要求校正 | S4 组合登记为独立 variant 进 family（§5 P1-6、§5.5 S4） |
| A5 | 预注册的学术定义（先于任何数据观察）未在原方案显式声明 | P0-4 口径先行与 §5.5 规则 1 显式声明（与 L2 同源） |

### 盲区（B，第三轮编号，独立于 §13 B1-B10）

| # | 盲区 | 处置 |
|---|------|------|
| B1 | 无因子退役/下线流程 | §5.6-1: 退役触发、冷却期与再申请（走完整 S0-S5，不得复用旧 holdout） |
| B2 | 无监控 → 复检触发器 | §5.6-2: 告警超阈值 → 新 record 复检（`parent_id` 引用原 record），不回改旧结论 |
| B3 | 同因子不同构造版本混淆风险 | `construction_code_hash` 必填（§4.1）；构造变更视为新变体（§5.6-4） |
| B4 | 批次级多重检验分母未定义 | 同批同 family 或显式子 family 依据（§5 P0-4、§5.5 规则 2） |
| B5 | SOP 未规定已知数据缺口如何处置 | S1 必须披露 mv/barra/行业缺口入 record 与证据包（§5.5 规则 4） |
| B6 | 幻影清仓月污染换手/分位统计 | S3 必须剔除幻影月，与容量压力测试口径一致（§5.5 规则 5） |
| B7 | 成本模型更新不传播到既有结论 | §5.6-3: cost_model 版本变更 → 枚举受影响 record 重估，新 record 引用旧 record |
| B8 | 「治理不改因子值」与正交化例外的边界不清 | §5.5 规则 6: L2+ 不回写因子值；正交化 hook 属 L1（opt-in）；内生性正则化只输出配置建议需显式应用 |
| B9 | 研究/生产两态门禁要求未分支 | `mode` 字段（§4.1）；研究可止于 S3/S4 留空 G4/G5，生产必走 S5（§5.5 规则 3、§6 注） |

### 自洽性澄清（C）

| # | 澄清 | 处置 |
|---|------|------|
| C1 | 「默认零变更」与「SOP 强制项」表面矛盾 | 治理组件仍 opt-in、默认计算路径不变；SOP 强制项约束**登记与生产决策**（缺必填字段不得入库、不过门禁不得上线），不强制所有研究计算跑全套（§3 原则 2、§5.5 规则 3、§6 注） |
| C2 | 「治理层不改因子值」断言需限定边界 | L2 及以上只产证据/决策；唯一改值 hook 是 L1 正交化（opt-in，属处理契约）；`apply_endogeneity_regularization` 只返回配置 dict 不自动应用（§5.5 规则 6；与[分析文档 §7.1](ENDOGENEITY_PREMIUM_GOVERNANCE_ANALYSIS.md)一致） |

### 上一轮分析经复审确认正确的部分

- 治理基座与单因子管线是「契约 + 证据 + 门禁」关系，不是替代或并行的第二条管线；
- 默认路径事实（`pipeline_mode` 全局决定 arm、分类器只诊断不路由）引用正确；
- 可比性契约 C1-C7 与 SOP 阶段划分兼容，无冲突；
- 「定义了判据，但没有定义作业流程」的缺口判断成立，由 §5.5/§5.6 补齐。

**第三轮复审结论**: 修正与补充已全部写入路线图（§4.1 / §5 P0-4 / §5 P1 / §5 P2 / §5.5 / §5.6 / §6）；
本轮仅文档修订，未改生产代码。PROJECT_STATUS GR-1/GR-4 验收口径已同步新增必填字段与预注册时点。
