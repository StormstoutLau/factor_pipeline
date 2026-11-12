# Project Status — 项目状态与待办追踪

> **更新日期**: 2026-11-12
> **用途**: 跨会话的单一真相源 (Single Source of Truth)，所有待办写在这里，其他文档只引用不重复。
> **更新规则**: 每次发版后划掉已完成项 + 新增下一版本待办。

---

## §1. 版本路基 (Roadmap)

```
v1.0.0 (2026-05)    统一编排层 + 顺序校验
v2.0.0 (2026-05)    智能自适应：指纹诊断 + 自适应分类 + 语义融合
v2.1.0 (2026-07)    架构修复：软路由 + 阈值校准 + 统一 fit()
v2.2.0 (2026-07)    Backtest 集成：回测引擎 + 双轨漂移融合
v2.2.1 (2026-07)    L2 磁盘缓存层 (ADR-008)
v2.2.2 (2026-07)    漂移检测与优化器改进
v2.2.3 (2026-07)    外部模块子包化 (ADR-013)
v2.2.4 (2026-07)    依赖锁定 (ADR-014)
v2.2.5 (2026-07)    adapters 重构 (ADR-015)
v2.2.6 (2026-07)    技术债清理 (ADR-016)
v2.3.0 (2026-07)    CI 矩阵 (ADR-017)
v2.4.0 (2026-07)    外部模块内化 (ADR-019)
v2.5.0 (2026-07)    多因子正交化三层架构 (ADR-020)
v2.6.0 (2026-07)    优化器与漂移检测增强 (ADR-021/022/023)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
v3.0.0 T4 (2026-07) KS BH-FDR 替代 Bonferroni (ADR-002a)      [x]
v3.0.0 T1 (2026-07) 指纹维度扩展至 21 维 (ADR-024)              [x]
v3.0.0 T3 (2026-07) CUSUM 在线漂移检测 (ADR-025)               [x]
v3.1.0     (2026-07) 内生性诊断 v1.0 (E1-E6, DESIGN_DISCUSSION)  [x]
v3.1.0          (2026-07) Audit-Driven Code Quality Remediation    [x]
v3.1.0          (2026-07) P2+ 断言恒真式 + 设计约束 + 端到端        [x]
v3.2.0     (2026-07) 学术准则驱动管线重构 (P0 固定方法 + P1 Hard Routing) [x]
v3.3.0 (2026-07-15) Layer 3 溢价健康诊断双层体系 (FactorHealthDiagnoser) [x]
v3.3.1 (2026-07-27) 插补模块 P2 完成 (向量化 + e2e + ablation)                [x]
v3.3.2 (2026-10-21) 管线级因果性测试 + PL-03 修复 + 版本号统一                 [x]
v3.3.3 (2026-10-22) PL-01 去极值逐日横截面 (ADR-037)                           [x]
v3.3.4 (2026-10-22) PL-02 变换逐日截面 rank→正态 (ADR-038)                    [x]
v3.3.5 (2026-11-04) PL-06 Mixed 缩尾逐日截面 3σ (ADR-039)                      [x]
v3.3.6 (2026-11-04) PL-05 Dynamic AR 因果三段式一步预测 (ADR-040)              [x]
v3.3.7 (2026-11-04) PL-08 AR 阶数选择统一 hold_back 样本 (ADR-041)             [x]
v3.4.0 (2026-11-10) 因子路由统一化治理 — 统一横截面秩管道 (ADR-042)             [x]
v3.4.1 (2026-11-11) 非生产路径解耦器弃用 (ADR-043)                            [x]
v3.4.2 (2026-11-12) 断点监控调度 — 节拍器 (ADR-044)                           [x]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ← 当前在 v3.4.2
v3.4.x (候选)     非生产路径解耦器数值修复 (可选, 当前仅告警)                  [ ]
v3.5.0 (远期)     内生性-溢价诊断交互 + 多断点支持 + 面板稳健估计               [ ]
```

---

## §2. 当前待办 (v3.4.2 完成后)

### 🔴 P0 — 阻塞/误导

| # | 任务 | 状态 |
|---|------|------|
| — | _(当前无 P0 阻塞项)_ | ✅ |

### ✅ 最近完成 — 因子路由统一化治理 + 非生产路径弃用 + 断点调度 (v3.4.0 / v3.4.1 / v3.4.2)

| 版本 | 任务 | 变更 | ADR | 关键实测 |
|------|------|------|-----|---------|
| v3.4.2 | 断点监控调度 (O6) | 新增 `BreakMonitorScheduler`: daily/weekly/monthly 节拍, 周期键幂等, 失败不推进; 数值型/tz-aware 输入拒绝; `StructuralBreakMonitor` 类零改动 | ADR-044 | 调度器 22 passed; 调度器 + 断点监控 + 版本统一 + 统一路由 57 passed; 手工校验 5/5 |
| v3.4.1 | 非生产路径解耦器弃用 | `OptimizedARDecoupler` / `OptimizedCompositeDecoupler` / `TemporalDecoupler` / `decouple_*` 保留导入 + 构造 `DeprecationWarning`; 子包 1.2.1 | ADR-043 | 弃用契约 4 passed; 版本统一 + AR 因果性 27 passed; 解耦器/AR 阶数 51 passed; 手工校验 5/5 |
| v3.4.0 | 路由过度工程化治理 | 统一横截面秩管道默认替代三路指纹路由; 删 3 路由函数 + 5 配置字段; 指纹降级只读诊断; StructuralBreakMonitor; dynamic_ab 整臂 A/B | ADR-042 | T1-T14 + B1-B6 全绿; 审计 PASS (0 P0/P1); 真实数据 A/B 秩相关 ρ≥0.999999、ΔIC 不显著, 基线标签-执行错位 2/2 — 见 [实证报告](analysis/V3.4.0_UNIFIED_ROUTING_EMPIRICAL_AB.md) |
| v3.3.7 | PL-08 | AR 阶数选择统一 hold_back 样本 + 有效样本守卫 | ADR-041 | AR(1) 选阶均值 4.800 → 1.233; `n_obs` 99..95 → 95×5; 输出 93%–96% 变化; 截断 11 点 0/0 |
| v3.3.6 | PL-05 / PL-07 | Dynamic AR 三段式因果一步预测; 顶层随上游转绿 | ADR-040 | Dynamic 截断 1653/1800 + 8 NaN → 0/0/0; 顶层 1650/1.8397 → 0/0/0 |
| v3.3.5 | PL-06 | Mixed 缩尾逐日截面 3σ | ADR-039 | 257/1800, 6.98e-01 → 0/0 |
| v3.3.4 | PL-02 / PL-04 | 变换逐日截面 rank→正态 | ADR-038 | 8.51e-04 (1800 格) → 0 |
| v3.3.3 | PL-01 | 去极值逐日横截面 percentile | ADR-037 | 1.68e-01 (187 格) → 0 |
| v3.3.2 | PL-03 | 标准化 auto→z_score 逐日行内 | — | 6.18e-01 (1800 格) → 0 |
| v3.3.1 | — | 插补 P2 (向量化 + e2e + ablation) | — | — |

> 当前缺陷登记: **无 known-xfail**; 历史因果性修复链 (v3.3.1–v3.3.7) 全部闭环, 见下方 P1 表与 git 历史。

### 🟠 P1 — 下一任务 (先后顺序)

| # | 任务 | 状态 | 依据 |
|---|------|------|------|
| 1 | 冻结模型实证回测 (真实因子 IC/Sharpe 与旧实现对比) | ⏸ 部分完成 (v3.4.0 A/B: 2 因子/2023 已做; 多年多因子待扩) | ADR-040 风险段 + [v3.4.0 实证报告](analysis/V3.4.0_UNIFIED_ROUTING_EMPIRICAL_AB.md) |
| 2 | v3.4.0 遗留选项: MAD 缩尾 (O1) / Dynamic 组件解耦 (O2) | 候选 | ADR-042 已知遗留 (O6 已由 v3.4.2 关闭) |

### 📦 历史: v3.3.0 已实施 — Layer 3 溢价健康诊断双层体系

> **设计文档**: [docs/private/DESIGN_DISCUSSION_V3.3.0.md](private/DESIGN_DISCUSSION_V3.3.0.md)
> **实施文档**: [docs/EXECUTION_V3.3.0.md](../EXECUTION_V3.3.0.md)
> **完成日期**: 2026-07-15

- [x] **Task 1**: L2 Routing 消融修复 (P0) — 5 tests, 5 消融配置全部通过
- [x] **Task 2**: 更多因子测试 (P1) — 10 因子分类验证
- [x] **Task 3**: 跨市场验证 (P1) — 4 市场 544 因子 100% 一致
- [x] **Task 4**: 原则评分 92% (P1) — Dickey-Fuller τ + F-test + Bonferroni
- [x] **Task 5**: 真实数据全量消融 (P1) — B3 IC=-0.0003, Sharpe=0.111
- [x] **Task 6**: Pipeline 日志 (P2) — `_intermediate_data` + `get_intermediate_data()`
- [x] **Layer 3 FactorHealthDiagnoser**: PremiumEstimator + BreakpointDetector + FactorHealthDiagnoser
- [x] 9/9 TDD 测试 + 128/128 全量回归 + A股 3 因子真实验证
- [x] 兼容性分析: FactorHealthDiagnoser vs FactorHealthMonitor — **互补不合并**
- [x] 设计文档: [DESIGN_DISCUSSION_V3.3.0.md](private/DESIGN_DISCUSSION_V3.3.0.md) (260行, 7章)
- [x] 实施文档: [EXECUTION_V3.3.0.md](../EXECUTION_V3.3.0.md) (11章, 附录)
- [x] 文档 Review: 严格 Review 通过 (9 项问题, 全部修复)
- [x] 代码修复: 模块 docstring CUSUM→Chow F-test 修正

### 🟡 P2 — 远期

| # | 任务 | 状态 | 来源 |
|---|------|------|------|
| — | 内生性-溢价诊断交互 (τ 修正因子) | [ ] | DESIGN_DISCUSSION_V3.3.0 §6.1 |
| — | 多断点支持 (Bai-Perron LWZ) | [ ] | DESIGN_DISCUSSION_V3.3.0 §6.2 |
| — | 面板 HAC 稳健估计 (Newey-West) | [ ] | DESIGN_DISCUSSION_V3.3.0 §6.3 |
| — | 流式处理支持 (v3.0.0 T2) | [ ] | §3 T2.1-T2.5 |
| — | Anderson-Rubin 后验检验 (中性化质量监控) | [ ] | v3.2.0 Step 8 |

---

### v3.1.0 消融实验 (已有) — 保留历史参考

> **完成日期**: 2026-07-09

- [x] **P2-1**: Neutralizer/Imputer 未传 `enabled` 给 `super().__init__()` — PipelineStep 加 enabled 参数, 3 个 Adapter 透传
- [x] **P2-2**: bootstrap CI 仅对 IC 差，未对 Sharpe 差计算 — compare() 新增 Sharpe bootstrap CI + p_value_bootstrap_sharpe
- [x] **P2-3**: bootstrap p 值公式文字描述不一致 — circular_block_bootstrap docstring 加中心化公式 (Hall & Wilson 1991)
- [x] **P3-1**: `_processor_class is None` 未在测试中验证 — 新增 test_enabled_false_processor_class_is_none
- [x] **P3-2**: transformation ignores `enabled` 行为未验证 — 新增 test_transformation_enabled_ignored_in_processing

### 🟡 P1 — 源码 TODO

> **位置**: [modules/factor_decoupler/core/unified_decoupler.py:L264](file:///f:/Coding/factor_pipeline/modules/factor_decoupler/core/unified_decoupler.py#L264)
> **完成日期**: 2026-07-09

- [x] `method_selection='fingerprint'` 分支回退到 `ar1_median` — _select_method_by_fingerprint 用 5 维指纹 (ar1/half_life/skew/kurt/vol_cluster) 综合评分选择

### 🟢 P2 — Demo Jupyter Notebook

> **设计文档**: [docs/ANALYSIS_V3.0.0.md §9.2](docs/ANALYSIS_V3.0.0.md) (完整 10-cell 规格)
> **完成日期**: 2026-07-09

- [x] 阶段 1 MVP: 10-cell notebook — 指纹雷达图 / 分类决策树 / 分布直方图 / Spearman 排序 / IC 追溯 / W 热力图 / 迁移检测 / 输出对比 / 校验报告
- [x] Cell 11 消融实验贡献度: ablation_results.json 加载 + 水平条形图 (IC/Sharpe 双向), 13 tests

---

## §3. 远期规划

### v3.0.0 T2 — 流式处理支持

> **位置**: [DECISIONS.md:L1896](file:///f:/Coding/factor_pipeline/DECISIONS.md#L1896)
> **状态**: 📋 下一轮执行 (5 sub-tasks: T2.1-T2.5, ~1500+ 行)

- [ ] T2.1: `CachedDataLoader.iter_periods()` 生成器 (数据加载层流式化)
- [ ] T2.2: 6 Imputer + Neutralizer + EnhancedRankPreservingScaler + SmartAdaptiveWinsorizer `partial_fit()` (模块层流式)
- [ ] T2.3: RollingOrthogonalizerAdapter 流式激活 `hook.update(X_t)`
- [ ] T2.4: `FactorProcessingPipelineV2.transform_streaming(period_data)` 主入口
- [ ] T2.5: CUSUM 流式协同 (逐期 update)

> **难度评估**: 高 (全链路改造, 8+ 文件, 流式 vs 批量等价性测试)

---

### RESEARCH_NOTES 学术工程 (E1-E10)

> **规格文档**: [docs/EXECUTION_RESEARCH_NOTES.md](docs/EXECUTION_RESEARCH_NOTES.md) (~4000行)
> **预计耗时**: ~20h

#### Phase 1 — P1（可并行，~4h）

> **完成日期**: 2026-07-09

- [x] **R1 PowerCurveAnalyzer**: BH-FDR 检测力曲线对比 (Bonferroni/Holm/none), ≥10 测试
- [x] **R2 Romano-Wolf**: Stepdown 多重检验对比, ≥9 测试
- [x] **R3 White RC + Hansen SPA**: 数据窥探偏差防御, ≥12 测试

#### Phase 2 — P2（串行，~8h）

> **完成日期**: 2026-07-09

- [x] **R4 FingerprintPerformanceLogger** (依赖 T1 ✅): 21维指纹+6表现+3管道权重 DB 存储, ≥14 测试
- [x] **R5 AttributionAnalyzer** (依赖 R4): 三层归因 (L1指纹/L2方差/L3交互+BH-FDR), ≥11 测试
- [x] **R7 StateDataLoader + RegimeIdentifier**: 12个A股状态变量 + Markov 两状态, ≥15 测试
- [x] **R8 StateConditionedPerformanceMatrix** (依赖 R7): 因子×体制性能 + Ferson 双轨回归+HAC, ≥12 测试
- [x] **R9 ThreeChannelDecomposition** (依赖 R8): 四通道序列 + 5种发散模式, ≥12 测试

#### Phase 3 — P3（条件触发，~4h）

> **完成日期**: 2026-07-09

- [x] **R6 DriftAwareBandit** (依赖 R4+T3): 漂移感知 Contextual Bandit — BanditMCSandbox MC 验证沙箱, ≥11 测试
- [x] **R10 StatisticalDecisionBridge** (依赖 R8): 概率映射 + 在线凸优化 + Q2 soft-update, ≥15 测试

---

### 消融对照机制 v3.0.0 工程增强

> **规格文档**: [docs/EXECUTION_ABLATION_V3.0.0.md](docs/EXECUTION_ABLATION_V3.0.0.md) (2211行)
> **注意**: 源码和测试已完成，Tier 1+2 修复已完成，仅 Tier 3 收尾 (见 §2)。

- [ ] 消融 Tier 3 (5 项, 见 §2)

---

## §4. 发版文档同步清单

> **每次发版必须更新以下文件**，对照勾选防止遗漏。

| 文档 | 更新内容 | v3.4.0 发版 (v3.4.1/v3.4.2 见注) |
|------|---------|--------|
| [CHANGELOG.md](file:///f:/Coding/factor_pipeline/CHANGELOG.md) | 新版本条目 (根因/实测/兼容性/遗留) | ✅ |
| [CODE_WIKI.md](file:///f:/Coding/factor_pipeline/CODE_WIKI.md) | 版本号 + 架构变更 | ⏸ 本次为内部路由治理, 无公开 API 变更 |
| [DECISIONS.md](file:///f:/Coding/factor_pipeline/DECISIONS.md) | ADR-042 + 占用表 + 路线图 | ✅ |
| [EXECUTION_V3.4.0_UNIFIED_ROUTING.md](EXECUTION_V3.4.0_UNIFIED_ROUTING.md) | 实施文档 v1.3 (含 §14 落库回填) | ✅ |
| [FACTOR_ROUTING_OVERENGINEERING_RESEARCH.md](analysis/FACTOR_ROUTING_OVERENGINEERING_RESEARCH.md) / [DESIGN](analysis/FACTOR_ROUTING_OVERENGINEERING_DESIGN.md) | 调研 v1.1 / 设计 v1.2 | ✅ |
| [CHECKLIST_V3.4.0_UNIFIED_ROUTING.md](audit/CHECKLIST_V3.4.0_UNIFIED_ROUTING.md) / [审计报告](audit/2026-11-10-code-quality-audit.md) | 验收 checklist v1.3 + 步骤 10 审计 PASS | ✅ |
| [V3.4.0_UNIFIED_ROUTING_EMPIRICAL_AB.md](analysis/V3.4.0_UNIFIED_ROUTING_EMPIRICAL_AB.md) | 真实数据 A/B 实证 (2 因子/2023) | ✅ |
| [README.md](file:///f:/Coding/factor_pipeline/README.md) | 版本信息 + 版本历史 | ✅ |
| [PROJECT_STATUS.md](file:///f:/Coding/factor_pipeline/docs/PROJECT_STATUS.md) / [DEV_PROGRESS.md](DEV_PROGRESS.md) | §1 路标 + §2 待办 + §5 执行记录 / 模块矩阵标签 | ✅ |

> **v3.4.1 (2026-11-11) 同步**: CHANGELOG / DECISIONS (ADR-043) / ARCHITECTURE / DEV_PROGRESS / README / PROJECT_STATUS 已更新; CODE_WIKI 无公开 API 变更 (仅新增构造告警), 未改动。
>
> **v3.4.2 (2026-11-12) 同步**: CHANGELOG / DECISIONS (ADR-044) / 实施文档 v1.0 / ARCHITECTURE / DEV_PROGRESS / README / PROJECT_STATUS 已更新; CODE_WIKI 仍未同步 (历史欠账, 待单独收口)。

---

## §5. 执行历史

| 日期 | Commit | 内容 |
|------|--------|------|
| 2026-11-12 | f532fd7 | feat(backtest): v3.4.2 断点监控调度器 BreakMonitorScheduler (ADR-044) |
| 2026-11-11 | e54658c | refactor(decoupler): v3.4.1 非生产路径解耦器弃用 (ADR-043) |
| 2026-11-10 | 1b5a144 | feat(pipeline): v3.4.0 统一横截面秩管道替代三路指纹路由 (ADR-042) |
| 2026-11-04 | 7c089f4 | fix(pipeline): v3.3.6 PL-05 Dynamic AR 因果三段式一步预测 (ADR-040) |
| 2026-11-04 | d04cdc1 | fix(pipeline): v3.3.5 PL-06 Mixed 缩尾逐日截面 3σ (ADR-039) |
| 2026-10-22 | 4794c6e | fix(pipeline): v3.3.4 PL-02 变换逐日截面 rank→正态 + 配置统一 |
| 2026-10-22 | 1718348 | fix(pipeline): v3.3.3 PL-01 去极值逐日横截面 + 缓存代际校验 |
| 2026-07-15 | bcf2cdc | docs(v3.3.0): architecture docs, ADR-028, changelog for Layer 3 FactorHealthDiagnoser |
| 2026-07-15 | ca7960c | feat(layer3): FactorHealthDiagnoser — LGMM premium + Bai-Perron breakpoint + multi-state diagnosis |
| 2026-07-15 | d135827 | feat(task5+6): 真实A股全量消融 + Pipeline中间数据日志 (4/4 tests) |
| 2026-07-15 | 5fb2516 | feat(task3+4): 跨市场验证 (4市场全dynamic一致性=0) + 12%迁就消除 (DF test + F-test) |
| 2026-07-15 | c40c8ec | feat(task2): 更多因子测试 — 10因子 StatisticalClassifier 分类验证 |
| 2026-07-15 | d28082a | feat(task1): P0 L2 Routing 消融修复 — 5 tests (TDD), 127/127 回归, 真实消融 L2 全部通过 |
| 2026-07-10 | add441b | feat(v3.2.0 Step 4+7): 消融重跑 + Hard Routing (StatisticalClassifier) |
| 2026-07-10 | 7e6bc08 | feat(v3.2.0 Step 3): Imputer ffill_ts 固定 (TDD) |
| 2026-07-10 | 480cb3d | feat(v3.2.0 Step 2): Transformer Shapiro-Wilk 形式检验 |
| 2026-07-10 | 38966db | feat(v3.2.0 Step 1): Winsorizer 1%/99% percentile (Bali 2016) (TDD) |
| 2026-07-10 | 2a4f181 | docs: 改进方案向量化审计 — 消除 for 循环 |
| 2026-07-10 | 85b4e45 | docs: 改进方案 — 9步执行顺序 + 代码级方案 |
| 2026-07-10 | 08264f2 | docs: 学术文献统计决策准则 — 5模块逐项分析 |
| 2026-07-09 | afb6fea | fix(v3.1.0): 消融 Tier 3 收尾 (5项) + unified_decoupler fingerprint 集成 |
| 2026-07-09 | b9066dc | docs: 文档残留学债修复 + 创建 PROJECT_STATUS.md 统一待办视图 |
| 2026-07-09 | 7993a93 | docs(v3.1.0): 项目文档同步 — CHANGELOG/DECISIONS/CODE_WIKI/README.en |
| 2026-07-09 | 6192edb | test(v3.1.0): audit P2+ 修复 — 22 非平凡测试 + 11 spec 反向对齐 |
| 2026-07-09 | 9ae1047 | feat(v3.1.0): RESEARCH_NOTES E1-E10 + V3.1.0 E1-E6 实施 + audit P0/P1 修复 |
| 2026-07-07 | 53f6cc0 | feat(v3.0.0 T3): CUSUM 在线漂移检测 + BH-FDR 共享模块 |
| 2026-07-04 | 218d166 | feat(v3.0.0 T1): 指纹维度扩展至 21 维 |
| 2026-07-04 | 92bf8ea | feat(v3.0.0 T4): KS 迁移检测 BH-FDR 替代 Bonferroni |
| 2026-07-04 | 0d23994 | feat(v2.6.0): 优化器与漂移检测增强 |
