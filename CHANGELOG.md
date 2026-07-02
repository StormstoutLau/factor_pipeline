# 开发日志 (Changelog)

## v2.2.2 — 代码质量修复 7 项 (2026-07-02)

### 概览

针对 Code Wiki 评审发现的 7 项代码质量问题,按推荐顺序逐一修复。全部采用严格 TDD (Red → Green → 手工校验 → 回归测试),每步完成后严格 review。

### Fix 1: self.factors dead-code bug + KS 拆分语义修复 (P0)

- **问题**: `pipelines_v2.py` 中 `self.factors` 在 `fit()` 后未保留,`transform()` 访问时 AttributeError; KS 检验拆分为两步后语义不一致
- **修复**: 在 `fit()` 中保留 `self.factors = factors`,KS 拆分逻辑统一使用 `_ks_migration_significance()`
- **测试**: `tests/test_fix1_self_factors_bug.py` — 4/4 通过

### Fix 5: 硬编码路径改为环境变量配置项 (ADR-012)

- **问题**: `data_bridge.py` 和 `health_bridge.py` 硬编码 `F:/Coding/Factor_Trading_v3.0` 等路径,不可移植
- **修复**: 改用 `os.environ.get("FACTOR_TRADING_PATH", ...)` 等环境变量,默认值保持向后兼容
- **测试**: `tests/test_fix5_hardcoded_paths.py` — 6/6 通过

### Fix 2: 配置系统统一 — 方案 C 桥接层 (ADR-010)

- **问题**: `PipelineV2Config` (dataclass) 与 `PipelineV2ConfigUnified` (Pydantic) 双轨制,字段映射需手动同步
- **修复**: 添加 `to_pipeline_v2_config()` 和 `from_unified()` 桥接方法,4 共享字段直接复制 + 概念对应 + 嵌套→扁平映射
- **测试**: `tests/test_fix2_config_unification.py` — 13/13 通过; 手工校验 8/8

### Fix 3: 版本号统一

- **问题**: `__init__.py` (2.0.0)、`config_v2.py` (2.1.0)、`reporting.py` (2.0.0) 版本号不一致
- **修复**: 3 处源码 + 2 处测试统一到 "2.2.1"
- **测试**: `tests/test_fix3_version_unification.py` — 5/5 通过

### Fix 4: backtest/__init__.py 补全导出

- **问题**: `backtest/__init__.py` 为空文件,用户需写长导入路径
- **修复**: 补全 26 个公开 API 导出 (因子指标、缓存、数据适配、引擎、健康度、运行器)
- **测试**: `tests/test_fix4_backtest_init.py` — 5/5 通过

### Fix 7: core 命名空间碰撞修复 (ADR-011)

- **问题**: `health_bridge.py` 注册 `sys.modules['core']` 指向 Factor_Fingerprint/core,加载后未清理,遮蔽 Factor_DB/core,导致 `test_p0_duckdb_pivot.py` 和 `test_integration_real_data.py` 全量回归时收集错误
- **修复**:
  - `data_bridge.py`: 模块名 `"core.data_v3"` → `"_factor_trading_data_v3"`; 移除 `sys.path.insert(0, Factor_Trading_v3.0)`
  - `health_bridge.py`: 加载完 core.fingerprint/health 后,若 `sys.modules['core']` 仍指向 Factor_Fingerprint/core,删除它
- **测试**: `tests/test_fix7_core_namespace_collision.py` — 6/6 通过; 手工校验 6/6; `test_p0_duckdb_pivot.py` 16/16 恢复

### Fix 6: ADR 状态更新

- **新增**: ADR-010 (配置系统统一)、ADR-011 (core 命名空间隔离)、ADR-012 (外部路径配置化)
- **更新**: ADR-007 风险描述 (core 冲突已由 ADR-011 补全)
- **路线图**: 新增 v2.2.2 章节

### 测试汇总

| 修复 | TDD 测试 | 手工校验 | 回归 |
|------|----------|----------|------|
| Fix 1 | 4/4 | — | 无回归 |
| Fix 5 | 6/6 | — | 无回归 |
| Fix 2 | 13/13 | 8/8 | 41 passed |
| Fix 3 | 5/5 | — | 39 passed |
| Fix 4 | 5/5 | — | 93 passed |
| Fix 7 | 6/6 | 6/6 | 252 passed + 16/16 历史失败恢复 |
| 总计 | 39/39 | 14/14 | 0 新增失败 |

---

## v2.2.1 — 漂移检测与优化器改进 (2026-07-01)

### 概览

针对漂移检测假阳性、优化器 look-ahead bias、因子日期不匹配、双信号融合逻辑保守等问题,完成 5 项改进 (P0-P2) + 1 项决策 (P3-2)。全部采用严格 TDD 开发,每步包含 Red Phase → Green Phase → 手工校验 → 回归测试。

### P0: 关键改进

**P0-1: 滚动窗口 KS + 调松阈值** (`backtest/unified_drift.py`)

- **问题**: 原二分分割 + 固定 KS 阈值导致假阳性率高,5 年数据漂移信号未累积,阈值过高导致全 stable。
- **修复**: 新增 `_compute_rolling_structure_drift()`,采用滚动窗口 (126 天 ≈ 6 个月) 滑动扫描 IC 序列,结合 p 值 (p<0.05) 过滤,取最大漂移分数。调松阈值: warning 30→15, drift 50→30, severe 70→50, structure_sig 30→20。
- **测试**: `tests/test_backtest/test_drift_improvements.py` — 15/15 通过

**P0-2: 优化器 Pipeline-in-the-loop** (`optimizer.py`)

- **问题**: 原优化器 objective 函数只对参数做数学变换,未真正调用 Pipeline 处理因子,优化结果与实际 Pipeline 行为脱节。
- **修复**: objective 函数真正调用 `FactorProcessingPipelineV2.fit() + transform()`,在处理后的因子上计算 IC。新增 `_params_to_config()` 完整 8 参数映射 (hard_routing_prob, merge_alpha, ks_alpha, mixed_winsor_sigma, transform_aggressiveness, classification_threshold_static/dynamic, migration_threshold)。
- **测试**: `tests/test_backtest/test_p0_2_pipeline_in_loop.py` — 5/5 通过

### P1: 因子日期自适应

**P1: per-factor min_dates + reindex 对齐** (`backtest/data_bridge.py` + `backtest/engine.py`)

- **问题**: Barra 因子 41 天 vs 日频因子 1212 天,统一阈值导致 Barra 因子被错误过滤或形状不匹配。
- **修复**:
  - `create_dataloader()` 新增 `min_dates: Dict[str, int]` 参数,per-factor 阈值过滤
  - reindex 对齐: 因子数据 reindex 到 close_df 的 (dates, stocks) 索引,缺失日期填 NaN
  - `engine.py` 空因子场景不抛异常,`run()` 返回空 dict
- **手工校验**: Barra 41 天 reindex 到 close 250 天,有数据期数=41 (完美对齐); 20 因子混合,5 个 Barra 因子全部产出结果
- **测试**: `tests/test_backtest/test_p1_adaptive_min_dates.py` — 7/7 通过 + 8/8 手工校验

### P2: 漂移融合与优化器 CV

**P2-1: 双信号加权融合 — and/or/max 三模式** (`backtest/unified_drift.py`)

- **问题**: 原 AND 逻辑 (dual_signal_required=True) 过于保守,仅一个信号显著时不报告漂移,导致漏报。
- **修复**: 新增 `signal_fusion_mode` 配置,支持三模式:
  - `and`: 两信号都显著才确认 (保守,旧默认)
  - `or`: 任一显著即确认 (激进)
  - `max`: 取主信号与主阈值比较,主信号显著即用主信号分数判定等级 (平衡,新默认)
- **向后兼容**: 用户传 `dual_signal_required` 但未传 `signal_fusion_mode` 时,自动推断 (True→and, False→or)
- **测试**: `tests/test_backtest/test_p2_1_signal_fusion.py` — 11/11 通过 + 12/12 手工校验

**P2-2: 优化器 CV 改进 — _cv_evaluate 接口重写 + optimize() 调用 CV** (`optimizer.py`)

- **问题**: `_cv_evaluate` 存在但未被 `optimize()` 调用 (死代码),且 CV 的 evaluate_fn 只用 test_data 算 IC,未利用 train_data 做 Pipeline fit,存在 look-ahead bias。
- **修复**:
  - `_cv_evaluate` 接口重写: `(factor_values, forward_returns, evaluate_fn)` → `(factor_data, forward_returns, config)`
  - 每个 fold 中 Pipeline 在 train 上 fit,test 上 transform (消除 look-ahead)
  - `optimize()` 的 objective 函数调用 `_cv_evaluate` 替代全量数据评估
  - 新增 `_full_evaluate()` 数据不足时的回退
- **手工校验**: 12/12 通过 (CV folds 生成、Pipeline fit/transform 日期范围、CV 分数=各 fold IC 平均、无 look-ahead bias、数据不足回退、optimize() 调用 CV、Pipeline.fit 调用次数 = n_trials × n_folds、复合目标函数数值一致性、接口向后兼容、空因子数据、transform_aggressiveness 映射)
- **测试**: `tests/test_backtest/test_p2_2_optimizer_cv.py` — 9/9 通过

### P3: 决策记录

**P3-2: 分组并行方案 A/B 对比实验 — 保留方案 A** (ADR-009)

- **背景**: P1 修复的 reindex 对齐引发假设:是否可以取消 `parallel_runner.py` 的按日期分组,统一共享全局 fwd_returns?
- **实验**: 20 个真实因子 (13 Barra 月频 41天 + 7 日频 1212天) A/B 对比
- **结果**:
  - 日频因子: ICIR/IC 完全一致 (diff=0.0)
  - Barra 因子: 差异巨大 (ICIR max diff=0.895, IC max diff=0.148)
  - 性能: 方案 A 44.82s vs 方案 B 137.81s (B 3x 更慢)
- **根因**: 方案 B 将不同频率因子统一到日频,fwd_returns 语义改变 (月收益率预测 → 日收益率预测)
- **决策**: 保留方案 A (按日期分组),不实施方案 B
- **实验脚本**: `tests/test_backtest/experiment_p3_2_ab_comparison.py`

### 测试总结

| 套件 | 测试数 | 通过 | 手工校验 |
|------|--------|------|----------|
| test_drift_improvements.py (P0-1) | 15 | 15 | — |
| test_p0_2_pipeline_in_loop.py (P0-2) | 5 | 5 | — |
| test_p1_adaptive_min_dates.py (P1) | 7 | 7 | 8/8 |
| test_p2_1_signal_fusion.py (P2-1) | 11 | 11 | 12/12 |
| test_p2_2_optimizer_cv.py (P2-2) | 9 | 9 | 12/12 |
| 回归测试 | 565 | 565 | — |
| **总计** | **612** | **612** | **32/32** |

> 2 个预存失败与本次改进无关 (Factor_Decoupler 无行业数据、版本号 2.1.0 vs 2.0.0)

### 经验教训

1. **reindex 对齐 ≠ 语义等价**: P1 的 reindex 解决了 NaN 填充,但不同频率因子的 fwd_returns 语义不同,reindex 不能消除这种差异 (ADR-009)
2. **实验驱动决策**: 方案 B 理论上看似合理,但 A/B 实验揭示了频率语义问题。如果直接实施会引入隐蔽的正确性 bug
3. **性能预期可能反转**: 方案 B 预估 1.3-1.5x 加速,实际 3x 更慢 (NaN 跳过虽快但仍有开销)
4. **死代码陷阱**: P2-2 发现 `_cv_evaluate` 存在但未被调用,优化器实际用全量数据评估,存在 look-ahead bias

---

## v2.2.0 — Backtest 集成 (2026-07-01)

### 回测引擎集成

根据方案 D（peer module + adapter pattern），在 `backtest/` 新增完整回测引擎模块，串联 Pipeline 输出 → 因子回测 → 健康度评估 → 漂移检测。

**新增模块:**

| 模块 | 用途 | 测试 | 状态 |
|------|------|------|------|
| `backtest/factor_metrics.py` | 因子级指标单一真相源 | 30/30 | ✅ 完成 |
| `backtest/data_bridge.py` | Pipeline → DataLoaderV3 适配器 | 10/10 | ✅ 完成 |
| `backtest/engine.py` | 因子回测引擎 | 20/20 | ✅ 完成 |
| `backtest/health_bridge.py` | 回测 → FactorHealthMonitor 适配器 | 13/13 | ✅ 完成 |
| `backtest/unified_drift.py` | 双轨融合漂移判定 | 13/13 | ✅ 完成 |
| `backtest/pipeline_integration.py` | 端到端 Pipeline 集成 | 9/9 | ✅ 完成 |

**配置扩展 (config_v2.py):**

- 新增 `BacktestConfig` 类，包含 IC 方法、多空参数、漂移阈值
- `PipelineV2ConfigUnified` 新增 `backtest` 字段
- JSON 序列化支持

**核心设计:**

- **单一真相源**: `factor_metrics.py` 唯一权威，其他模块不得重复实现
- **适配器模式**: `data_bridge` 适配 Pipeline → DataLoaderV3，`health_bridge` 适配回测 → HealthMonitor
- **双轨漂移融合**: 结构漂移 (Fingerprint) + 性能漂移 (Backtest) → 融合判定
- **不修改外部模块**: 适配器通过 importlib 加载，不改动外部 Fingerprint 代码
- **TDD 严格校验**: 9 次分阶段 TDD，逐指标手工计算验证

**架构图:**
```
  Pipeline 输出
      ↓
  DataBridge (n_stocks, n_dates) → (n_dates, n_stocks)
      ↓
  DataLoaderV3
      ↓
  FactorBacktestEngine → IC/ICIR/Decay/HitRate/Turnover/LS/Spread
      ↓
  HealthMonitorAdapter → 注入 FactorHealthMonitor → 5 维健康评分
      ↓
  UnifiedDriftReporter → 结构+性能+换手率 → 融合漂移判定
```

---

## v2.1.0 — 架构修复 (2026-07-01)

### P0: 关键架构缺陷

**P0-1: 硬路由 → 概率加权软路由** (`pipelines_v2.py`)

- **问题**: `transform()` 使用硬路由，概率阈值开关导致因子类型切换时处理断崖。因子从 STATIC 跳到 DYNAMIC 时，处理流程瞬间改变，产生不可控的分布跳跃。
- **修复**: 新增 `_get_pipeline_weights()` 将 `ClassificationResult` 转换为管道权重字典，`_apply_weighted_transform()` 执行多管道加权混合。高置信度(>0.9)时仍使用硬路由优化性能。
- **测试**: `tests/test_p0_fixes.py::TestSoftRouting` — 8/8 通过
- **影响**: 因子过渡期不再出现断崖，输出是各管道的加权混合。

**P0-2: 阈值校准** (`pipelines_v2.py`)

- **问题**: 分类阈值 `static_threshold=0.80`、`dynamic_threshold=0.40` 硬编码，不考虑数据分布特征。
- **修复**: 新增 `ThresholdCalibrator` 类，支持分位数法（基于数据分布）和市场预设（a_share/us_equity/crypto）。`fit()` 时自动校准阈值。
- **测试**: `tests/test_p0_fixes.py::TestThresholdCalibration` — 6/6 通过

### P1: 高优先级增强

**P1-3: 统一三条管道 `fit()` 模式** (`pipelines_v2.py`)

- **问题**: 三条管道(`StaticFactorPipeline`/`DynamicFactorPipeline`/`MixedFactorPipeline`)的中间数据记录不一致，调试困难。
- **修复**: 在 `_BaseFactorPipeline.__init__()` 添加 `_intermediate_data` 字典，新增 `get_intermediate_data()` 统一接口。三条管道 `fit()` 均记录中间数据。
- **测试**: `tests/test_p1_fixes.py::TestUnifiedFitPattern` — 5/5 通过

**P1-4: 适配器回退 Warning** (`adapters.py`)

- **问题**: 外部子模块不可用时，适配器静默回退到简单方案，用户无法感知数据质量降级。
- **修复**: `PipelineStep` 基类添加 `is_fallback_mode`。`ImputerAdapter`/`ProcessingAdapter`/`NeutralizerAdapter`/`GarchWhiteningAdapter` 在回退时发出 `warnings.warn(UserWarning)`。`get_stats()` 包含 `fallback_mode` 字段。
- **测试**: `tests/test_p1_fixes.py::TestAdapterFallbackWarnings` — 5/5 通过

**P1-5: `transition_weights` 接入路由层** (`pipelines_v2.py`)

- **问题**: `FactorFingerprintMonitor.get_transition_weights()` 返回的指数衰减迁移权重未被使用。
- **修复**: 新增 `_merge_transition_weights()` 融合分类权重和迁移权重。在 `transform()` 中集成 monitor 迁移权重检查。
- **测试**: `tests/test_p1_fixes.py::TestTransitionWeightsRouting` — 4/4 通过

### P2: 中期改进

**P2-6: 迁移显著性检验 — KS 双样本检验** (`pipelines_v2.py`)

- **问题**: `get_transition_weights()` 仅基于最近 3 期类型是否一致判断迁移，不做统计显著性检验，噪声可能导致误报。
- **修复**: 新增 `_ks_migration_significance()` 函数，使用 `scipy.stats.ks_2samp` 对历史/近期因子分布进行双样本 KS 检验。**Bonferroni 多重比较校正**避免假阳性。仅当 KS 显著(p < α/n)时才合并迁移权重。集成到 `transform()` 中。
- **测试**: `tests/test_p2_fixes.py::TestKSMigrationSignificance` — 6/6 通过
- **架构含义**: 迁移检测从"简单启发式"→"统计假设检验"，大幅降低假阳性。

**P2-8: `importlib` 替代 `sys.path`** (`adapters.py`)

- **问题**: `_import_external_class()` 使用 `sys.path.insert(0, ...)` 全局修改 `sys.path`，异常时无法恢复，可能污染后续导入。
- **修复**: 新增 `_temp_sys_path` 上下文管理器，使用 `importlib.import_module` 替代 `__import__`。无论导入成功或失败，`sys.path` 均恢复原状。
- **测试**: `tests/test_p2_fixes.py::TestImportlibRefactor` — 3/5 通过 + 2 skipped

### 测试总结

| 套件 | 测试数 | 通过 | 失败 | 跳过 |
|------|--------|------|------|------|
| test_p0_fixes.py | 14 | 14 | 0 | 0 |
| test_p1_fixes.py | 14 | 14 | 0 | 0 |
| test_p2_fixes.py | 11 | 9 | 0 | 2 |
| 回归测试 | 190 | 185 | 3* | 2 |
| **总计** | **229** | **222** | **3*** | **4** |

> *3 个失败均为既有问题：分类器 mock 数据边界、无行业数据的解耦测试、Imputer 重复列名。与本次修复无关。

---

## v2.0.0 — 智能自适应流水线 (2026-05)

### 新增特性

- 因子指纹诊断层：13 维统计指标自动诊断
- 自适应因子分类：STATIC / DYNAMIC / MIXED 三类自动分流
- 语义-统计融合：自然语言构造规则 + 统计指纹的贝叶斯融合
- 三重中性化：原始值中性化 → AR 建模 → 残差中性化
- GARCH 白化（可选）：高自相关静态因子波动率聚集消除
- 处理顺序调整：静态/混合因子先中性化后标准化
- 持续迁移监测：FactorFingerprintMonitor + FactorHealthMonitor

### 架构演进

```
v1.0: 单一固定流程
原始因子 → 插补 → 去极值 → 变换 → 标准化 → 中性化

v2.0: 智能自适应流程
原始因子 → 指纹提取 → 分类(语义+统计) → 分流处理 → 迁移监测
                ↓
        ┌───────┼───────┐
        ↓       ↓       ↓
    静态管道  动态管道  混合管道

v2.1: 架构修复
软路由 / 阈值校准 / 统一fit模式 / 适配器回退Warning / 迁移权重接入 / KS显著性检验

v2.2: Backtest 集成
Pipeline → DataBridge → DataLoaderV3 → Engine → HealthMonitorAdapter → UnifiedDriftReporter

v2.2.1: 漂移检测与优化器改进
滚动KS / Pipeline-in-the-loop / per-factor min_dates / 三模式融合 / CV消除look-ahead
```

---

## v1.0.0 — 基础流水线 (2025)

### 初始版本

- 固定五步法：插补 → 去极值 → 变换 → 标准化 → 中性化
- 适配器模式封装外部子模块
- sklearn 风格 fit/transform 接口
- PipelineDAG 依赖管理
- PipelineCache 中间结果缓存
- PipelineOrderValidator 处理顺序校验