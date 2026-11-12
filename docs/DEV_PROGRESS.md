# 开发进度总览 (版本 × 模块双维度)

> **版本**: v1.3 (2026-11-12; v1.2 = 2026-11-12; v1.1 = 2026-11-11; v1.0 = 2026-07-27)
> **范围**: 跨会话单一真相源,记录每个版本每个模块的完成状态
> **更新规则**: 每次发版 / 完成任务后更新对应单元格;新增版本时追加列
> **关联文档**: [ARCHITECTURE.md](ARCHITECTURE.md) | [PROJECT_STATUS.md](PROJECT_STATUS.md) | [../CHANGELOG.md](../CHANGELOG.md)

---

## §1 版本路标

```
v1.0.0 (2026-05)    统一编排层 + 顺序校验 (DAG)
v2.0.0 (2026-05)    智能自适应: 指纹诊断 + 自适应分类 + 语义融合
v2.1.0 (2026-07)    架构修复: 软路由 + 阈值校准 + 统一 fit()
v2.2.0 (2026-07)    Backtest 集成: 回测引擎 + 双轨漂移融合
v2.2.x (2026-07)    工程化: 缓存层 / 子包化 / 依赖锁定 / adapters 重构 / 技术债清理
v2.3.0 (2026-07)    CI 矩阵 (GitHub Actions + tox)
v2.4.0 (2026-07)    外部模块内化 (ADR-019)
v2.5.0 (2026-07)    多因子正交化三层架构 (ADR-020)
v2.6.0 (2026-07)    优化器与漂移检测增强 (ADR-021/022/023)
v3.0.0 (2026-07)    T1 指纹 21 维 + T3 CUSUM + T4 KS BH-FDR
v3.1.0 (2026-07)    内生性诊断 v1.0 (E1-E6) + Audit-Driven 修复
v3.2.0 (2026-07)    学术准则驱动管线重构 (P0 固定方法 + P1 Hard Routing)
v3.3.0 (2026-07-15) Layer 3 溢价健康诊断双层体系 (FactorHealthDiagnoser)
v3.3.1 (2026-07-27) 插补模块 P2 完成 (向量化 + e2e + ablation)
v3.3.2 (2026-10-21) 管线级因果性测试 + PL-03 修复 + ADR 编号治理 + 版本号统一
v3.3.3 (2026-10-22) PL-01 去极值逐日横截面 (ADR-037) + 缓存代际 v2.2.1-cache
v3.3.4 (2026-10-22) PL-02 变换逐日截面 rank→正态 (ADR-038) + 缓存代际 v2.2.2-cache
v3.3.5 (2026-11-04) PL-06 Mixed 缩尾逐日截面 3σ (ADR-039) + 缓存代际 v2.2.3-cache
v3.3.6 (2026-11-04) PL-05 Dynamic AR 因果三段式一步预测 (ADR-040) + 缓存代际 v2.2.4-cache
v3.3.7 (2026-11-04) PL-08 AR 阶数选择统一 hold_back 样本 (ADR-041) + 缓存代际 v2.2.5-cache
v3.4.0 (2026-11-10) 因子路由统一化治理 (ADR-042) + 缓存代际 v2.3.0-cache
v3.4.1 (2026-11-11) 非生产路径解耦器弃用 (ADR-043), 子包 1.2.1
v3.4.2 (2026-11-12) 断点监控调度 (ADR-044), 缓存代际不变
v3.4.3 (2026-11-12) Dynamic 组件可分离性 (ADR-045), 缓存代际不变
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ← 当前 v3.4.3
v3.5.0 (远期)       内生性-溢价诊断交互 + 多断点 + 面板稳健估计
```

---

## §2 版本 × 模块进度矩阵

> 图例: ✅ 完成 / ⏳ 进行中 / ⏸ 部分完成 / ❌ 未开始 / — 不适用
>
> v3.4.0 模块影响: `pipelines_v2.py` 改统一横截面秩管道 (ADR-042); `factor_fingerprint/` 新增 `infer_sampling_frequency` 与 `compute_ar1_path`; `backtest/` 新增 `structural_break_monitor`; `optimizer.py` 默认搜索空间清空。详见 [CHANGELOG](../CHANGELOG.md)。
> v3.4.1 模块影响: `factor_decoupler/` 非生产解耦器 (`Optimized*` / `TemporalDecoupler` / `decouple_*`) 弃用 — 保留导入, 构造即 `DeprecationWarning` (ADR-043); 子包版本 1.2.1。
> v3.4.2 模块影响: `backtest/structural_break_monitor.py` 新增 `BreakMonitorScheduler` (daily/weekly/monthly 节拍, 周期键幂等, 失败不推进; ADR-044); 监控统计与管道接口零改动。
> v3.4.3 模块影响: `factor_decoupler/core/dual_neutralizer.py` `CompositeDecoupler` 新增 `enable_neutralization` / `enable_ar`; `pipelines_v2.py` `DynamicFactorPipeline` 新增 `module_enabled['decoupler']` (ADR-045); 默认路径逐位不变。

### §2.1 核心编排层

| 模块 / 文件 | v1.0 | v2.0 | v2.1 | v2.2 | v2.3-2.6 | v3.0 | v3.1 | v3.2 | v3.3 | v3.3.1 |
|---|---|---|---|---|---|---|---|---|---|---|
| `pipeline.py` 顺序校验 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `dag.py` DAG 拓扑 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `config.py` 配置 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `config_v2.py` pydantic | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `pipelines_v2.py` 统一管道 (v3.4.0) | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `adapters.py` 5 个 Adapter | ⏸ | ⏸ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `cache.py` 管线缓存 | — | — | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `optimizer.py` Optuna | — | — | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

### §2.2 处理模块 (Layer 1)

| 模块 | v1.0 | v2.0 | v2.1 | v2.4 内化 | v2.5 正交 | v3.0 指纹 | v3.2 学术重构 | v3.3.1 插补 P2 |
|---|---|---|---|---|---|---|---|---|
| `factor_imputer/` | ⏸ | ⏸ | ⏸ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `factor_adaptive_winsor/` | ⏸ | ⏸ | ⏸ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `factor_neutralizer/` | ⏸ | ⏸ | ⏸ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `factor_orthogonalizer/` | — | — | — | — | ✅ | ✅ | ✅ | ✅ |
| `factor_decoupler/` | — | ⏸ | ⏸ | ✅ | ✅ | ✅ | ✅ | ✅ |

### §2.3 分类与诊断 (Layer 2-3)

| 模块 | v2.0 | v3.0 T1 指纹扩展 | v3.2 StatisticalClassifier | v3.3 Layer 3 健康诊断 |
|---|---|---|---|---|
| `factor_fingerprint/` | ✅ 8 维 | ✅ 21 维 | ✅ | ✅ |
| `statistical_classifier/` | — | — | ✅ VR+DF τ 零循环 | ✅ |
| `factor_health/` | — | — | — | ✅ PremiumEstimator + BreakpointDetector + Diagnoser |

### §2.4 内生性 (v3.1)

| 模块 | v3.1.0 | v3.4.0 |
|---|---|---|
| `endogeneity_check/` | ✅ AET+IFE+Lewbel+Oster | ⏳ 与溢价诊断交互 |
| `endogeneity_estimators/` | ✅ IVX+PF-GMM+Profile-GMM+DOLS | ⏳ 面板 HAC |
| `endogeneity_regularizer/` | ✅ | ✅ |

### §2.5 回测层 (backtest/)

| 模块 | v2.2 | v2.2.1 缓存 | v2.6 漂移 | v3.0 T3 CUSUM | v3.3 |
|---|---|---|---|---|---|
| `engine.py` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `cache_manager.py` | — | ✅ | ✅ | ✅ | ✅ |
| `parallel_runner.py` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `cusum_drift_monitor.py` | — | — | — | ✅ | ✅ |
| `threshold_drift_monitor.py` | — | — | ✅ | ✅ | ✅ |
| `unified_drift.py` | — | — | ✅ | ✅ | ✅ |
| `attribution_analyzer.py` + `granger_attribution/` | — | — | — | — | ✅ |
| `specification_logger/` | — | — | — | — | ✅ |
| `ablation_runner.py` | — | — | — | — | ✅ |

---

## §3 v3.3.1 详细进度 (历史, 2026-07-27)

### §3.1 任务清单

| # | 任务 | 优先级 | 状态 | 测试 |
|---|------|--------|------|------|
| 1 | 修正 1: Little & Rubin §4.3 术语错误 | P0 | ✅ 完成 | 文档核对 |
| 2 | 修正 2: Breiman 2001 多输出 RF 补专门文献 | P0 | ✅ 完成 | 文档核对 |
| 3 | 修正 3: Lopez de Prado §7 章号核实 | P0 | ✅ 完成 | 文档核对 |
| 4 | P2-1: 向量化剩余 for 循环 | P1 | ✅ 完成 | test_shared_model_batch_equivalent_to_per_row |
| 5 | P2-3: 端到端测试 全管线无前视 | P1 | ✅ 完成 | test_imputer_e2e_causal.py (9 项) |
| 6 | P2-4: 消融实验 lookahead_safe ON vs OFF | P1 | ✅ 完成 | test_imputer_ablation_lookahead.py (10 项) |
| 7 | 最终 review: 排除幻觉 + 全量回归 | P0 | ✅ 完成 | 803 passed / 10 skipped / 0 regressions |

### §3.2 文档变更

| 文档 | 变更 |
|------|------|
| `tests/unit/test_imputer_lookahead_fix.py` | 修正学术引用 + 新增批量 predict 等价性测试 |
| `docs/analysis/IMPUTER_LOOKAHEAD_FIX_PLAN.md` | v2.2 → v2.3, P2 状态全部更新为 ✅ |
| `tests/integration/test_imputer_e2e_causal.py` | 新增 4 项测试 (静态扫描 + 严格因果性) |
| `tests/integration/test_imputer_ablation_lookahead.py` | 新增 4 项测试 (IC 范围 + 严格因果性消融) |
| `modules/factor_imputer/core/imputers.py` | `_transform_rf_shared` 向量化 (批量 predict) |
| `docs/ARCHITECTURE.md` | **新建** (架构总览) |
| `docs/DEV_PROGRESS.md` | **新建** (本文档) |
| `docs/EXECUTION_V3.3.1_IMPUTER_P2.md` | **新建** (实施记录) |
| `docs/WORKFLOW_METHODOLOGY.md` | 升级 7 阶段 → 10 步 spec 规范 |
| `CHANGELOG.md` | 新增 v3.3.1 条目 |

### §3.3 测试统计

| 测试集 | 通过 / 总数 |
|--------|------------|
| `test_imputer_lookahead_fix.py` | 33 / 33 |
| `test_imputer_e2e_causal.py` | 9 / 9 |
| `test_imputer_ablation_lookahead.py` | 10 / 10 |
| `test_step3_imputer_ffill_ts.py` | 4 / 4 |
| **全量回归** | **803 passed / 10 skipped / 0 failed** |

---

## §4 待办 (v3.4.0 后)

### §4.0 P1 下一任务

| # | 任务 | 状态 | 依据 |
|---|------|------|------|
| 1 | v3.3.6 冻结模型实证回测 (真实因子 IC/Sharpe vs 旧实现) | 候选 | ADR-040 风险段 (非平稳失配未测) |
| 2 | 非生产路径治理 (`OptimizedARDecoupler` / `TemporalDecoupler`) | 候选 | 审计遗留 (无生产调用) |
| 3 | v3.4.0 遗留选项: MAD 缩尾 (O1) | 候选 | ADR-042 已知遗留 (O2 已由 v3.4.3 关闭, O6 已由 v3.4.2 关闭) |

### §4.1 P2 远期

| # | 任务 | 来源 |
|---|------|------|
| 1 | 内生性-溢价诊断交互 (τ 修正因子) | DESIGN_DISCUSSION_V3.3.0 §6.1 |
| 2 | 多断点支持 (Bai-Perron LWZ) | DESIGN_DISCUSSION_V3.3.0 §6.2 |
| 3 | 面板 HAC 稳健估计 (Newey-West) | DESIGN_DISCUSSION_V3.3.0 §6.3 |
| 4 | 流式处理支持 (v3.0.0 T2) | §3 T2.1-T2.5 |
| 5 | Anderson-Rubin 后验检验 (中性化质量监控) | v3.2.0 Step 8 |

### §4.2 P3 长期

| # | 任务 | 来源 |
|---|------|------|
| 1 | MissingTypeDiagnoser 因果版本 (expanding EM) | IMPUTER_LOOKAHEAD_FIX_PLAN §8.4 |
| 2 | 删除非生产路径死代码 (HierarchicalImputer) | IMPUTER_LOOKAHEAD_FIX_PLAN §8.4 |
| 3 | `types.py` 重命名 (避免遮蔽标准库) | ARCHITECTURE.md §9.1 |

---

## §5 文档索引

| 版本 | 实施文档 | 设计文档 | ADR |
|------|---------|---------|-----|
| v3.4.0 | [EXECUTION_V3.4.0_UNIFIED_ROUTING.md](EXECUTION_V3.4.0_UNIFIED_ROUTING.md) | [analysis/FACTOR_ROUTING_OVERENGINEERING_DESIGN.md](analysis/FACTOR_ROUTING_OVERENGINEERING_DESIGN.md) v1.2 | ADR-042 |
| v3.3.7 | [EXECUTION_V3.3.7_PL08_AR_ORDER_HOLDBACK.md](EXECUTION_V3.3.7_PL08_AR_ORDER_HOLDBACK.md) | [analysis/PL08_AR_ORDER_AIC_COMPARABILITY_DESIGN.md](analysis/PL08_AR_ORDER_AIC_COMPARABILITY_DESIGN.md) | ADR-041 |
| v3.3.6 | [EXECUTION_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md](EXECUTION_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md) | [analysis/PL05_DYNAMIC_AR_LOOKAHEAD_DESIGN.md](analysis/PL05_DYNAMIC_AR_LOOKAHEAD_DESIGN.md) | ADR-040 |
| v3.3.5 | [EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md](EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md) | [analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_DESIGN.md](analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_DESIGN.md) | ADR-039 |
| v3.3.1 | [EXECUTION_V3.3.1_IMPUTER_P2.md](EXECUTION_V3.3.1_IMPUTER_P2.md) | [analysis/IMPUTER_LOOKAHEAD_FIX_PLAN.md](analysis/IMPUTER_LOOKAHEAD_FIX_PLAN.md) v2.3 | — |
| v3.3.0 | [EXECUTION_V3.3.0.md](EXECUTION_V3.3.0.md) | private/DESIGN_DISCUSSION_V3.3.0.md | ADR-028 |
| v3.2.0 | — | — | ADR-027 |
| v3.1.0 | [EXECUTION_V3.1.0.md](EXECUTION_V3.1.0.md) | — | ADR-026 |
| v3.0.0 T4 | [EXECUTION_V3.0.0_T4.md](EXECUTION_V3.0.0_T4.md) | — | ADR-002a |
| v3.0.0 T1 | [EXECUTION_V3.0.0_T1.md](EXECUTION_V3.0.0_T1.md) | — | ADR-024 |
| v2.6.0 | [EXECUTION_V2.6.0.md](EXECUTION_V2.6.0.md) | — | ADR-021/022/023 |
| v2.5.0 | [EXECUTION_V2.5.0.md](EXECUTION_V2.5.0.md) | — | ADR-020 |
| v2.4.0 | [EXECUTION_V2.4.0.md](EXECUTION_V2.4.0.md) | — | ADR-019 |
