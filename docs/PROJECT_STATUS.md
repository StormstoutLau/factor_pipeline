# Project Status — 项目状态与待办追踪

> **更新日期**: 2026-07-09
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
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ← 当前在 v3.2.0
v3.2.0 P2  (远期)  AR 后验检验 + 审计文档 v2.0                         [ ]
v3.0.0 T2  (远期)  流式处理支持                                         [ ]
```

---

## §2. 当前待办 (v3.2.0 完成后)

### 🔴 P0 — 阻塞/误导

| # | 任务 | 状态 |
|---|------|------|
| — | _(当前无 P0 阻塞项)_ | ✅ |

### v3.2.0 已实施 — 学术准则驱动重构 (6 steps)

> **审计文档**: [docs/analysis/principle_vs_hacking_audit.md](docs/analysis/principle_vs_hacking_audit.md)
> **决策文档**: [docs/analysis/academic_literature_decision_criteria.md](docs/analysis/academic_literature_decision_criteria.md)
> **完成日期**: 2026-07-10

- [x] **Step 1**: Winsorizer `method='percentile'` (1%/99%) — Bali et al. 2016 行业标准
- [x] **Step 2**: Transformer Shapiro-Wilk 形式正态性检验 — Shapiro & Wilk 1965
- [x] **Step 3**: Imputer `strategy='ffill_ts'` — Little & Rubin 2002
- [x] **Step 4**: 消融重跑 — winsorizer+scaler 显著 (p_bootstrap=0.016)
- [x] **Step 5**: 全量回归 — 168/168 passed ✅
- [x] **Step 7**: Hard Routing + StatisticalClassifier (VR + AR(1)) — Lo & MacKinlay 1988

### 🟡 P2 — 远期

| # | 任务 | 状态 |
|---|------|------|
| Step 8 | Anderson-Rubin 后验检验 (中性化质量监控) | [ ] |
| Step 9 | 审计文档 v2.0 (修正原则评分 → ~90%) | [ ] |
| — | 跨市场验证 (港股/US) | [ ] |
| — | Pipeline 日志记录 intermediate data | [ ] |

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

| 文档 | 更新内容 | v3.2.0 |
|------|---------|--------|
| [CHANGELOG.md](file:///f:/Coding/factor_pipeline/CHANGELOG.md) | 新版本条目 | ✅ |
| [README.md](file:///f:/Coding/factor_pipeline/README.md) | 版本摘要 + 版本信息块 + 版本历史表 | ✅ |
| [README.en.md](file:///f:/Coding/factor_pipeline/README.en.md) | 同上（英文） | ✅ |
| [CODE_WIKI.md](file:///f:/Coding/factor_pipeline/CODE_WIKI.md) | 版本号 + 架构变更 | ✅ |
| [DECISIONS.md](file:///f:/Coding/factor_pipeline/DECISIONS.md) | 新 ADR + 路线图 `[ ]`→`[x]` | ✅ |
| [PROJECT_STATUS.md](file:///f:/Coding/factor_pipeline/docs/PROJECT_STATUS.md) | §2 划掉已完成 + §5 追加执行记录 | 本文档 |

---

## §5. 执行历史

| 日期 | Commit | 内容 |
|------|--------|------|
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
