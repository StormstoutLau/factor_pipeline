# 开发进度总览 (版本 × 模块双维度)

> **版本**: v1.5 (2026-11-17; v1.4 = 2026-11-13; v1.3 = 2026-11-12; v1.2 = 2026-11-12; v1.1 = 2026-11-11; v1.0 = 2026-07-27)
> **范围**: 版本 × 模块进度矩阵（已冻结：待办迁至 [PROGRESS.md](PROGRESS.md)，路标见 [PROJECT_STATUS.md](PROJECT_STATUS.md) §1）
> **更新规则**: 每次发版 / 完成任务后更新对应单元格;新增版本时追加列
> **关联文档**: [ARCHITECTURE.md](ARCHITECTURE.md) | [PROJECT_STATUS.md](PROJECT_STATUS.md) | [../CHANGELOG.md](../CHANGELOG.md)

---

## §1 版本路标

> **已冻结**（as of 2026-11-17 / v3.5.3）：本路标不再更新；当前路线图见 [PROJECT_STATUS.md](PROJECT_STATUS.md) §1。

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
v3.4.4 (2026-11-13) AblationRunner decoupler 消融臂, 缓存代际不变
v3.4.5 (2026-11-13) run_l2 / run_baselines 市值转发断链修复, 缓存代际不变
v3.4.6 (2026-11-13) run_l3 / run_l4_oat 市值口径对齐, 缓存代际不变
v3.4.7 (2026-11-15) L3/L4 旋钮接线审计 (去极值参数化 + 臂集合收敛), 缓存代际不变
v3.4.8 (2026-11-15) 消融 trivial 判定按实跑口径 (无市值退化臂排除 BH 分母), 缓存代际不变
v3.4.9 (2026-11-16) L1/L2 trivial 口径清扫 (ortho / unified 臂退出 BH 分母), 缓存代际不变
v3.4.10 (2026-11-16) HAC 检验 NaN 过滤 (成对 complete-case), 缓存代际不变
v3.4.11 (2026-11-16) 技术债小包 (alpha 清理 + mean_diff 缺失 + MAD 参数化), 缓存代际不变
v3.4.12 (2026-11-16) 面板 HAC / Premium 标准误 (estimate_with_errors), 缓存代际不变
v3.4.13 (2026-11-16) DEFECT-1: BreakpointDetector 短样本退化 (T<30 → 无断点结果), 缓存代际不变
v3.5.0 (2026-11-16) 多断点支持 (Bai-Perron DP + BIC/LWZ + Stata 46/46 对拍, ADR-046), 缓存代际不变
v3.5.1 (2026-11-17) 多断点接入 diagnose 标签路径 (opt-in + sup-F 确认 + 材料性 suspect, ADR-047), 缓存代际不变
v3.5.2 (2026-11-17) 多断点路径 NaN 间隙守卫 (连续性描述 + ES 降级 suspect, ADR-048), 缓存代际不变
v3.5.3 (2026-11-17) sup-F 自相关稳健临界值 (AR(1) sieve bootstrap, ADR-049), 缓存代际不变
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ← 当前 v3.5.3
v3.5.x (远期)       内生性-溢价诊断交互
```

---

## §2 版本 × 模块进度矩阵

> 图例: ✅ 完成 / ⏳ 进行中 / ⏸ 部分完成 / ❌ 未开始 / — 不适用
>
> v3.4.0 模块影响: `pipelines_v2.py` 改统一横截面秩管道 (ADR-042); `factor_fingerprint/` 新增 `infer_sampling_frequency` 与 `compute_ar1_path`; `backtest/` 新增 `structural_break_monitor`; `optimizer.py` 默认搜索空间清空。详见 [CHANGELOG](../CHANGELOG.md)。
> v3.4.1 模块影响: `factor_decoupler/` 非生产解耦器 (`Optimized*` / `TemporalDecoupler` / `decouple_*`) 弃用 — 保留导入, 构造即 `DeprecationWarning` (ADR-043); 子包版本 1.2.1。
> v3.4.2 模块影响: `backtest/structural_break_monitor.py` 新增 `BreakMonitorScheduler` (daily/weekly/monthly 节拍, 周期键幂等, 失败不推进; ADR-044); 监控统计与管道接口零改动。
> v3.4.3 模块影响: `factor_decoupler/core/dual_neutralizer.py` `CompositeDecoupler` 新增 `enable_neutralization` / `enable_ar`; `pipelines_v2.py` `DynamicFactorPipeline` 新增 `module_enabled['decoupler']` (ADR-045); 默认路径逐位不变。
> v3.4.4 模块影响: `backtest/ablation_runner.py` 新增 `run_l1_decoupler` (dynamic_ab 内 AR 开/关两臂); ρ_step 条件采集 + 报告条件列; `run_l1`/`run_single` 修复 `market_cap_data` 转发; 默认 `run_l1` 6 臂契约不变。
> v3.4.5 模块影响: `backtest/ablation_runner.py` 补齐 `run_l2` / `run_baselines` 的 `market_cap_data` 转发 (仅非 None 注入); 臂集合与返回数量不变。
> v3.4.6 模块影响: `backtest/ablation_runner.py` 补齐 `run_l3` / `run_l4_oat` 的 `market_cap_data` 入口 — L3 统一注入 (B3 + 24 臂), L4 选择性注入 (B3 + 18 臂, `neutralization='industry'` 臂跳过), L4 默认口径随数据可用性切换; 臂集合与返回数量不变。
> v3.4.7 模块影响: `pipelines_v2.py` Static 管道去极值参数化 (`static_outlier_method` / 分位点, 默认 percentile 1/99 零行为变更); `backtest/ablation_runner.py` 臂集合重建 (L3 25→7, L4 20→9), outlier 4 臂真实接线, 新增 `_wiring_status` 与报告 `Wiring` 列; L3 CUSUM 6 臂全部 trivial。

> v3.4.8 模块影响: `backtest/ablation_runner.py` `run_l4_oat` 的 trivial 判定改为按实跑口径 — 无市值时 `industry+mktcap` 臂退化为仅行业中性化, 标记 `_is_trivial=True` 并输出一次 WARNING, 不再计入 BH-FDR 分母 (无市值场景 3 trivial / 5 非平凡); 传入外部 `b3_full_result` 且无市值时追加「外部 B3 口径未校验」提示; 生产管线与臂集合零变更。

> v3.4.9 模块影响: `backtest/ablation_runner.py` `run_l2` 的 `L2_unified` 与 B3 同为 unified 口径 → 标 `_is_trivial=True`; `run_l1` 模块臂由 `{module: False}` 整体替换改为 `{**base, module: False}` 合并覆盖, 并按 `base_config.module_enabled` / `orthogonalization.enabled` 实跑口径判定 trivial (默认 base 下仅 `L1_orthogonalizer_off` trivial); 退化臂一次告警 + 外部 B3 提示各 1 条; 生产管线与臂集合零变更。

> v3.4.10 模块影响: `backtest/ablation_runner.py` `ledoit_wolf_hac_test` 入口新增成对联合 `isfinite` 掩码 (complete-case), 带宽与归一化改用清洗后样本; 有效配对 < 3 返回 `(0.0, 1.0)`; `compare` / `compare_all` / bootstrap 零改动; 生产管线与臂集合零变更。

> v3.4.11 模块影响: `backtest/ablation_runner.py` 移除 `ledoit_wolf_hac_test` 未使用的 `alpha`; `mean_diff_hac_statsmodels` 增加成对 complete-case; `pipelines_v2.py` 新增 `static_outlier_adaptive_threshold` / `static_outlier_max_outlier_frac` 并透传到 `ProcessingAdapter` (默认 = detector 默认, 零行为变更); 非生产解耦器数值修复标注不修复 (ADR-043)。

> v3.4.12 模块影响: `modules/factor_health/__init__.py` `PremiumEstimator` 新增 `estimate_with_errors` (逐期 OLS SE + λ̂(t) 局部 Newey-West HAC SE + 溢价均值 HAC SE/CI), 抽出 `_smooth_betas` / `_hac_long_run_variance`; `estimate()` / `diagnose()` / `BreakpointDetector` 数值与标签零变更; 缓存代际不变。

> v3.4.13 模块影响: `modules/factor_health/__init__.py` `BreakpointDetector` 新增 `_no_breakpoint_result(T)` — T<30 时返回 6 键无断点退化结果 (`has_breakpoint=False` / `chow_max_stat=0.0` / `critical=nan` / `cusum_path` 全 NaN / `pre_mean=post_mean=nan`, 不含 `breakpoint_idx`); `detect` 正常路径 (T≥30) 与 `diagnose` 零变更; 修复 DEFECT-1 短样本 `AttributeError`; 缓存代际不变。

> v3.5.0 模块影响: `modules/factor_health/__init__.py` `BreakpointDetector` 新增 `detect_multiple(lambda_hat, m_max=None)` — Bai-Perron 全局最小 SSR (DP, O(m·T²)) + BIC/LWZ 选段数, 13 键输出; 新增 6 私有方法 (`_ssr_prefix` / `_build_ssr_matrix` / `_dp_breaks` / `_bic` / `_lwz` / `_multiple_no_breakpoint_result`); `detect` / `diagnose` / 管线零变更; 新增 `scripts/stata_breakpoint_crosscheck.py` (Stata 官方 regress 对拍 46/46); 缓存代际不变。

> v3.5.1 模块影响: `modules/factor_health/__init__.py` `FactorHealthDiagnoser.diagnose` 新增 opt-in `breakpoint_mode='single'|'multiple'` + `m_max=5`, `__init__` 新增 `multi_break_shift_threshold=1.0`; 新增 `_resolve_breakpoints` / `_single_segment_view` / `_multi_break_materiality`; `_classify_premium_health` 增加 confirmed/material 分支 (未确认材料 → `suspect`); 输出新增 10 键; `detect` / `detect_multiple` / `PremiumEstimator` / 默认 single 标签零变更; 缓存代际不变。

> v3.5.2 模块影响: `modules/factor_health/__init__.py` `BreakpointDetector` 新增 `_gap_runs` / `_gap_missing_at` (静态), `detect_multiple` 新增 5 个连续性描述键 (13→18); `FactorHealthDiagnoser.__init__` 新增 `multi_break_gap_min_run=2`, `_multi_break_materiality` 返回最大位移边界 `driver_k`, `_classify_premium_health` 增加 gap 分支 (ES/ES+TD → suspect), `diagnose` 新增 6 键 (22→28); 默认 single 标签零变更; 分段算法/`detect` 零改动; 缓存代际不变。

> v3.5.3 模块影响: `modules/factor_health/__init__.py` `BreakpointDetector.__init__` 新增 `sup_f_method` / `n_bootstrap` / `random_state`; `_bootstrap_sup_f_crit` 重写为 AR(1) sieve 残差自助 (旧实现为 iid 高斯); 新增 `_sup_f_batch` 向量化; `detect` 传 `y` 并新增 `critical_method` (8 键); `FactorHealthDiagnoser.__init__` 透传三参数, `diagnose` 新增 `chow_critical` / `breakpoint_sup_f_method` (28→30); 默认 asymptotic 路径逐位不变; 缓存代际不变。

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
| `factor_health/` | — | — | — | ✅ PremiumEstimator + BreakpointDetector + Diagnoser; v3.4.12 HAC SE (`estimate_with_errors`); v3.5.0-3 多断点 / 间隙守卫 / AR(1) sieve bootstrap |

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

## §4 待办（已裁决，本表冻结）

> **本表停止维护**（as of 2026-11-17）。存量 11 条已由 **P-011（v3.9.8，2026-11-22）** 逐条裁决，证据见
> [RESEARCH.md](../spec/v398-p011-dev-backlog-triage/RESEARCH.md)（v1.3 verified，含外部锚点 + P-018 设计输入 + 异构复审 22/22 PASS）；
> 当前待办真值源见 [PROGRESS.md](PROGRESS.md)。本表保留历史原文 + 裁决结果备查。

| 原条目（原 §4.0 P1 候选） | P-011 裁决（2026-11-22） | 证据 |
|----------------|------------------------|------|
| v3.3.6 冻结模型实证回测 | **关闭（已交付）** | [PROJECT_STATUS.md](PROJECT_STATUS.md) L174（v3.4.0 → v3.4.12 → 12 因子 → 组合层 / 容量） |
| 非生产路径治理 | **关闭**（ADR-043 弃用） | DECISIONS.md L46 / L2980 |
| v3.4.0 遗留 MAD 缩尾 (O1) | **关闭**（v3.4.11 MAD 参数化，保留可选） | PROJECT_STATUS L175；`analysis/MAD_WINSORIZE_O1_EXPERIMENT.md` |

| 原条目（原 §4.1 / §4.2 远期） | P-011 裁决（2026-11-22） | 证据 |
|--------------------|------------------------|------|
| 内生性-溢价交互 | **转 P-009**（P3） | PROGRESS.md P-009 行 |
| 多断点支持 (Bai-Perron) | **关闭（已交付 v3.5.0，ADR-046）** | DECISIONS.md L49 / L3175；`factor_health/__init__.py` L377 |
| 面板 HAC 稳健估计 | **关闭（已交付 v3.4.12）** | `factor_health/__init__.py` L65 `estimate_with_errors` |
| 流式处理 | **转 P-018**（P3 远期） | PROGRESS.md P-018 行；ANALYSIS_V3.0.0 L19 / L476 |
| Anderson-Rubin | **关闭（已交付 v3.2.0 Step 8）** | `adapters.py` L1013-L1043；`tests/unit/test_step8_ar_posterior_check.py` |
| MissingTypeDiagnoser 因果版 | **不修复**（仅诊断面，P3）。触发条件：`strategy='auto'`（或任何调用 `HierarchicalImputer` 的路径）进入生产，或诊断输出用于交易 / 风控决策时重开 | IMPUTER 计划 L320-L324 / L1112；`pipelines_v2.py` L744 |
| 删除 HierarchicalImputer | **不修复**（前提「永远只用 `ffill_ts`」未成立；已内化且默认配置仍引用） | `config.py` L104-L110；`default_pipeline_config.json` L5-L13；IMPUTER 计划 L1113 |
| `types.py` 重命名 | **不修复**（ADR-016 接受债；tox/CI 已规避）。重审条件：未来引入 `src/` 布局，或「项目根直接 `python -m`」不再受约束时 | ARCHITECTURE L420；tox.ini L25 / L55；DECISIONS L977 / L1050 |

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
