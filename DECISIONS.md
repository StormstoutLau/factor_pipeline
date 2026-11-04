# 决策路线 (Architecture Decision Records)

## 概览

本文档记录 factor_pipeline 项目中的关键架构决策，包括每个决策的背景、备选方案、选择理由和后果。

**决策原则 (Constitution)**:
1. 因子不是静态标签，而是概率分布
2. 管道不是统一流水线，而是精准适配
3. 所有统计判断必须有显著性检验支撑
4. 外部模块不可用时应显式告警，而非静默失败

---

## ADR 编号登记规则与勘误 (2026-10-21)

### 登记规则

1. **ADR 编号唯一在本文档中分配**：编号一经在此写入即视为占用，不得复用。
2. **规划文档不得预留编号**：`docs/EXECUTION_*.md`、`docs/analysis/*.md`、`docs/audit/*.md` 在记录待实施决策时须写「ADR 编号待分配」，不得自行指定编号；实施完成后回本文档取号。
3. **引用须可检索**：文档中出现的 `ADR-0XX` 应能在此处查到同号条目，否则视为悬空引用。

> 规则 1-2 的由来：2026-07 至 08 期间，三份规划文档各自把 ADR-026 分配给不同决策，且 v3.1.0 一次性预留 ADR-026~031 共 6 个编号，与实际占用编号大面积冲突。见下「勘误表」。

### 占用现状 (权威)

| 编号 | 决策 | 版本 / 日期 |
|------|------|------------|
| ADR-026 | Audit-Driven Code Quality Remediation | v3.1.0, 2026-07-09 |
| ADR-027 | 学术准则驱动管线重构 | v3.2.0, 2026-07-10 |
| ADR-028 | Layer 3 溢价健康诊断 (FactorHealthDiagnoser) | v3.3.0, 2026-07-15 |
| ADR-029 | 标准化统一为逐日横截面 Z-Score (因果性修复) | 2026-10-21 |
| ADR-030 | E1 隐藏效应诊断 — Mixin 嵌入 | v3.1.0 决策, 2026-10 补记 |
| ADR-031 | E2 P-hacking 防御 — L1-L2 独立模块 + L3 扩展 | v3.1.0 决策, 2026-10 补记 |
| ADR-032 | E3 内生性诊断 S1-S4 — 独立新模块 + 四阶段 | v3.1.0 决策, 2026-10 补记 |
| ADR-033 | E4 格兰杰检验 — Toda-Yamamoto 默认 + Bootstrap 可选 | v3.1.0 决策, 2026-10 补记 |
| ADR-034 | E5 三层决策正则化 — 硬依赖 E3 + opt-in | v3.1.0 决策, 2026-10 补记 |
| ADR-035 | E6 估计层方法 — opt-in + 与决策层互补 | v3.1.0 决策, 2026-10 补记 |
| ADR-036 | 消融对照机制 — 四层架构 + Baseline 阶梯 | v3.0.0 决策, 2026-10 补记 |
| ADR-037 | 去极值统一为逐日横截面 (因果性修复) | v3.3.3, 2026-10-22 |
| ADR-038 | 变换统一为逐日截面 rank→正态 (因果性修复) | v3.3.4, 2026-10-22 |
| ADR-039 | Mixed 缩尾统一为逐日截面 3σ (因果性修复) | v3.3.5, 2026-11-04 |
| ADR-040 起 | 未占用 | — |

### 勘误表

下列「声明编号」与权威占用冲突，**声明一律作废**，以「占用现状」为准。

| 声明编号 | 声明内容 | 来源 (文件, 处数) | 实际占用者 | 处置 |
|---------|---------|---------------|-----------|------|
| ADR-026 | E1 Mixin 嵌入而非独立模块 | EXECUTION_V3.1.0.md (3) | Audit-Driven 修复 | 作废，E1 已改记 ADR-030 |
| ADR-026 | 消融对照机制 (四层架构 + Baseline 阶梯) | EXECUTION_ABLATION_V3.0.0.md (7) | Audit-Driven 修复 | 作废，已改记 ADR-036 |
| ADR-026 | AblationRunner independent | audit/2026-07-08-ablation-code-quality-audit.md (1) | Audit-Driven 修复 | 作废，同上归入 ADR-036 |
| ADR-027 | E2 L1-L2 独立模块 + L3 扩展 | EXECUTION_V3.1.0.md (3) | v3.2.0 管线重构 | 作废，E2 已改记 ADR-031 |
| ADR-028 | E3 独立新模块 + 四阶段诊断 | EXECUTION_V3.1.0.md (3) | v3.3.0 Layer 3 | 作废，E3 已改记 ADR-032 |
| ADR-029 | E4 Toda-Yamamoto 默认 + Bootstrap 可选 | EXECUTION_V3.1.0.md (3) | 标准化因果性修复 | 作废，E4 已改记 ADR-033 |
| ADR-030 | E5 三层正则化硬依赖 E3 + opt-in | EXECUTION_V3.1.0.md (3) | E1 隐藏效应诊断 (ADR-030) | 作废，E5 已改记 ADR-034 |
| ADR-031 | E6 估计层方法 opt-in + 与决策层正则化互补 | EXECUTION_V3.1.0.md (3) | E2 P-hacking 防御 (ADR-031) | 作废，E6 已改记 ADR-035 |

> 检索方式: 以「声明内容」列为关键字 grep 对应文件。来源列只标文件名与出现次数、**不标行号**——行号会随文档编辑失效，此类漂移曾导致本表首版自我腐化。
> 各来源文件均已置入顶部或就近的 ⚠️ 勘误提示，读者在该文档内即可被引导回本表。

### 已实施决策 → ADR 补记对照 (2026-10-21 完成)

以下 7 项决策的代码早已实现但长期无 ADR 记录，现已全部补记，**无遗留**。

| 决策 | 补记 ADR | 实现位置 (已核实存在) |
|------|---------|------|
| E1 隐藏效应诊断 (Mixin 嵌入而非独立模块) | ADR-030 | `modules/factor_decoupler/diagnostics/hidden_effect.py` |
| E2 P-hacking 防御 (L1-L2 独立模块 + L3 扩展) | ADR-031 | `backtest/specification_logger/` |
| E3 内生性诊断 S1-S4 (独立新模块 + 四阶段) | ADR-032 | `modules/endogeneity_check/core/` |
| E4 格兰杰检验 (Toda-Yamamoto 默认 + Bootstrap 可选) | ADR-033 | `backtest/granger_attribution/toda_yamamoto.py` |
| E5 三层正则化 (硬依赖 E3 + opt-in 默认关闭) | ADR-034 | `modules/endogeneity_regularizer/` |
| E6 估计层方法 (opt-in + 与决策层正则化互补) | ADR-035 | `modules/endogeneity_estimators/core/` |
| 消融对照机制 (AblationRunner 四层架构 + Baseline 阶梯) | ADR-036 | `backtest/ablation_runner.py` |

> 补记标准见「ADR-030 ~ ADR-036 补记说明」：决策表述取自规划文档，代码证据逐条核实；规划文档未记录的备选方案与文献卷期页码不予补造。

---

## ADR-001: 软路由替代硬路由

**日期**: 2026-07-01
**状态**: 已实施
**优先级**: P0

### 背景

v2.0 的 `transform()` 使用硬路由：根据 `ClassificationResult.primary_type` 将因子直接发送到一条管道。当因子从 STATIC 迁移到 DYNAMIC 时，处理流程瞬间切换，产生不可控的分布跳跃。

### 决策

**采用概率加权软路由**，而非硬路由。

具体方案：
- `_get_pipeline_weights()`: 将 `ClassificationResult` (primary_type, primary_prob, secondary_type, secondary_prob) 转换为管道权重字典
- `_apply_weighted_transform()`: 对每条管道的结果按权重线性混合
- 高置信度(>0.9)时仍使用硬路由优化性能

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 保持硬路由 | 简单，性能好 | 过渡断崖，不可接受 | ❌ |
| B: 软路由（加权混合） | 平滑过渡，无断崖 | 计算开销增加 | ✅ |
| C: 指数平滑 | 记忆效应 | 参数多，过度设计 | ❌ |
| D: 马尔可夫状态 | 理论完备 | 需要大量数据训练 | ❌ (远期) |

### 后果

- **正面**: 因子过渡期不再出现断崖，输出是各管道的加权混合
- **负面**: 计算开销增加（最坏情况 3 条管道同时运行）
- **风险**: 混合管道的权重分配需要 KS 显著性检验过滤噪声迁移

---

## ADR-002: Bonferroni 校正的 KS 双样本检验替代简单迁移检测

**日期**: 2026-07-01
**状态**: 已实施
**优先级**: P2

### 背景

`get_transition_weights()` 仅基于最近 3 期类型是否一致判断迁移，不做统计显著性检验。在 10 列因子数据中，即使分布完全不变，仍有 ~40% 概率至少一列随机超过阈值（Type I 误差）。

Q3 验证数据：IC 和 ICIR 高度相关(ρ=0.885)，覆盖率方差极小(std=0.014)，说明简单阈值方法容易产生假阳性。

### 决策

**采用 scipy.stats.ks_2samp + Bonferroni 多重比较校正**。

具体方案:
- `_ks_migration_significance()`: 对历史/近期因子数据逐列进行 KS 双样本检验
- Bonferroni 校正: `alpha_corrected = alpha / n_columns`
- 仅当 `min_p < alpha_corrected` 时确认迁移，合并迁移权重

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 保持简单阈值 | 零计算成本 | 40% 假阳性，不可接受 | ❌ |
| B: KS + Bonferroni | 统计严谨，假阳性可控 | 需要 scipy | ✅ |
| C: Mann-Whitney U | 非参数 | 只检测位置偏移，不检测形状变化 | ❌ |
| D: CUSUM | 检测变化点 | 需要在线实现，复杂 | ❌ (远期) |

### 后果

- **正面**: 迁移检测从"简单启发式"提升为"统计假设检验"，假阳性大幅降低
- **负面**: 需要 scipy 依赖，数据不足时退回保守处理
- **风险**: Bonferroni 校正过于保守（Type II 误差增加），远期可考虑 Benjamini-Hochberg FDR

---

## ADR-002a: Benjamini-Hochberg FDR 替代 Bonferroni 用于 KS 迁移多重比较校正

**日期**: 2026-07-04
**状态**: 已实施 (v3.0.0 T4 E1)
**优先级**: P0
**关系**: Supersede ADR-002 的校正方法 (ADR-002 历史记录保留不动)

### 背景

ADR-002 采用 Bonferroni 校正 (`alpha_corrected = alpha / K`) 控制多重比较假阳性, 但 ADR-002 自己的"风险"章节已指出 Bonferroni 过于保守 (Type II 误差增加), 漏检真实迁移。

在因子迁移检测场景下, 漏检真实迁移的代价 (策略失效未被发现) 通常高于误检的代价 (不必要的迁移权重合并)。Bonferroni 控制 FWER (Family-Wise Error Rate) 过于严格, BH 控制的是 FDR (False Discovery Rate), 在检测力与误检率之间取得更合理的平衡。

### 决策

**将 `_ks_migration_significance` 的多重比较校正从 Bonferroni 迁移到 Benjamini-Hochberg FDR**, 保留 Bonferroni 路径作为向后兼容选项。

具体方案:
- 新增 `correction_method: str = 'benjamini_hochberg'` 参数 (默认 BH)
- BH 路径: `p_adj_(k) = p_(k) * K / rank`, 从大到小累积 min, clip [0,1]
  - `is_significant = (min_p_value_adjusted < alpha)`
- Bonferroni 路径 (`correction_method='bonferroni'`): 保留旧逻辑 (向后兼容)
- None 路径 (`correction_method='none'`): 无校正, 供研究/调试使用
- 字段隔离: BH 路径返回 `min_p_value_adjusted` / `correction_method`, Bonferroni 路径返回 `alpha_corrected` / `bonferroni_correction`, 互不污染

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 保持 Bonferroni | 零改动 | 检测力低, 漏检真实迁移 | ❌ |
| B: BH-FDR (默认) | 检测力高, FDR 控制 | 字段变化需向后兼容 | ✅ |
| C: Holm-Bonferroni | 检测力介于 A/B | 实现复杂, 与 factor_significance.py 不一致 | ❌ |
| D: 直接删除 Bonferroni | 代码最简 | 破坏向后兼容 | ❌ |

### 后果

- **正面**: 检测力提升 (E1-T5 验证 BH 检测数 >= Bonferroni), 与 `factor_significance.py` 的 BH 默认一致 (E7 已用 BH)
- **负面**: 行为变化 — 之前不显著的迁移现在可能变显著 (`is_sig` 可能 False→True), 需在 CHANGELOG 注明
- **风险**: BH 控制的是 FDR 而非 FWER, 若应用场景要求严格控制"至少一个假阳性"概率, 应显式传 `correction_method='bonferroni'`
- **回滚**: 默认改回 `correction_method='bonferroni'` 即可 (1 行改动)

### 学术依据

- Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate: a practical and powerful approach to multiple testing. *Journal of the Royal Statistical Society: Series B*, 57(1), 289-300.
- Bonferroni 校正: Dunn, O. J. (1961). Multiple comparisons among means. *Journal of the American Statistical Association*, 56(293), 52-64.

---

## ADR-003: importlib + 上下文管理器替代 sys.path 操作

**日期**: 2026-07-01
**状态**: 已实施
**优先级**: P2

### 背景

`_import_external_class()` 使用 `sys.path.insert(0, full_path)` 全局修改 `sys.path`。异常时无法恢复，可能污染后续模块导入。P2-8 测试验证：多次调用后 sys.path 累积额外路径。

### 决策

**采用 `importlib.import_module` + `contextlib.contextmanager` 上下文管理器**。

具体方案:
- `_temp_sys_path(path)`: 上下文管理器，临时添加路径，`finally` 块中移除
- `importlib.import_module(import_path)` 替代 `__import__(import_path, fromlist=[class_name])`

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 保持 sys.path 操作 | 简单 | 全局污染，异常不安全 | ❌ |
| B: importlib + 上下文管理器 | 隔离安全，异常恢复 | 代码略复杂 | ✅ |
| C: importlib.util.spec_from_file_location | 不修改 sys.path | 需知道文件路径，复杂 | ❌ |

### 后果

- **正面**: 无论导入成功或失败，sys.path 均恢复原状。连续多次导入无路径泄漏。
- **负面**: 无
- **风险**: 无

---

## ADR-004: 目标函数设计 — IC 主目标 + 约束替代多指标加权

**日期**: 2026-07-01
**状态**: 待实施 (P3)
**优先级**: P3

### 背景

端到端阈值搜索的初始方案使用 5 指标加权求和的目标函数:
```
0.40*IC + 0.25*ICIR + 0.15*stability + 0.10*coverage + 0.10*diversity
```

四问题验证揭示了严重缺陷:
- **Q1/Q3**: IC 和 ICIR 高度冗余(ρ=0.885)，实际有效权重 ~0.65 给了 IC 维度
- **Q3**: coverage 方差极小(std=0.014)，无区分力
- **Q4**: efficacy 与 HealthMonitor 完全重叠，重复计算
- **Q4**: regime 敏感性缺失，HealthMonitor 独有维度未覆盖

### 决策

**采用 IC 主目标 + 三项约束惩罚**，替代多指标加权。

```python
score = IC_score - stability_penalty - ks_penalty - health_penalty - coverage_penalty
```

- 主目标: 平均 |IC|（截面 Spearman 秩相关）
- 约束 1: IC 波动性惩罚 (`0.3 * std(IC)`)
- 约束 2: KS 分布扭曲惩罚 (p < 0.001 → -0.3, p < 0.01 → -0.15)
- 约束 3: HealthMonitor 综合得分 (< 40 → -0.5, < 60 → -0.2)
- 约束 4: 覆盖率 (< 0.70 → -0.5, < 0.85 → -0.2)

### 设计依据

| 原指标 | 处理 | 原因 |
|--------|------|------|
| IC (0.40) | 保留为主目标 | 因子存在的最根本理由 |
| ICIR (0.25) | 替换为 IC 波动性惩罚 | ρ=0.885，冗余 |
| stability (0.15) | 降级为 KS 约束 | 稳定性不应最大化，应设下限 |
| coverage (0.10) | 降级为覆盖率约束 | std=0.014，无区分力 |
| diversity (0.10) | 移除 | 系统级指标，不适合作单因子目标 |
| — | 新增 HealthMonitor 约束 | 覆盖 HM 独有的 regime/crowding |

### 后果

- **正面**: 目标函数从 5 个冗余指标简化为 1 个主目标 + 4 个约束，可解释性大幅提升
- **负面**: 约束阈值的惩罚幅度仍依赖经验设定
- **风险**: 约束过多可能导致无可行解，需要在实际数据上调试

---

## ADR-005: 8 维搜索空间替代 10 维

**日期**: 2026-07-01
**状态**: 待实施 (P3)
**优先级**: P3

### 背景

初始方案搜索 10 个阈值。Q2 审计发现 2 对冗余阈值和 1 个遗漏。

### 决策

**采用 8 维搜索空间**。

合并的冗余对:
- `classification_static` + `classification_dynamic` → `midpoint` + `interval`
- `skew_threshold` + `kurt_threshold` → `transform_aggressiveness`

新增遗漏:
- `migration_threshold` (决定迁移检测灵敏度)

### 8 维搜索空间

| 维度 | 范围 | 当前值 |
|------|------|--------|
| `classification_midpoint` | [0.45, 0.75] | 0.60 |
| `classification_interval` | [0.15, 0.50] | 0.40 |
| `hard_routing_prob` | [0.70, 0.99] | 0.90 |
| `merge_alpha` | [0.10, 0.90] | 0.50 |
| `ks_alpha` | [0.01, 0.20] | 0.05 |
| `migration_threshold` | [0.03, 0.30] | 0.10 |
| `mixed_winsor_sigma` | [2.0, 5.0] | 3.0 |
| `transform_aggressiveness` | [0.5, 2.0] | 1.0 |

### 后果

- **正面**: 维度减少 20%，冗余阈值合并后搜索效率提升
- **负面**: 合并后的参数物理含义不如原始参数直观
- **风险**: 转换公式可能引入额外的非线性

### 修订日志

**2026-07-04 (v2.6.0 E2 / P3-10')**: 修正 `migration_threshold` 字段位置错误。

- **问题**: `optimizer.py:150-158` 错误将 `migration_threshold` 设置到 `config.monitor.migration_threshold`, 但 `MonitorConfig` (modules/factor_fingerprint/core/monitor.py:51-61) 无此字段 (只有 `short/medium/long_threshold` 三个窗口阈值), `hasattr` 静默跳过导致参数被丢弃.
- **修正**: 字段位于 `PipelineV2Config.migration_threshold` (pipelines_v2.py, 默认值 0.10, 与 `PipelineV2ConfigUnified.migration_threshold` 对齐).
- **代码变更**:
  - `pipelines_v2.py`: `PipelineV2Config` dataclass 新增 `migration_threshold: float = 0.10`
  - `optimizer.py:150-158`: 移除 `hasattr(config.monitor, ...)` 静默检查, 改为 `config.migration_threshold = params['migration_threshold']`
  - `config_v2.py:to_pipeline_v2_config()`: 桥接方法直接传递 `migration_threshold=self.migration_threshold`
- **搜索空间维度不变**: 仍为 8 维, `migration_threshold` 维度 (范围 [0.0, 1.0], 当前值 0.10) 物理含义与窗口阈值解耦.
- **静态/动态阈值替代 midpoint/interval**: 经审计 (E2 Review), 原 ADR-005 的 midpoint/interval 参数化方式虽更紧凑, 但不如直接搜索 `classification_threshold_static` + `classification_threshold_dynamic` 直观. 此修正已在 8 维搜索空间中体现 (见表 1), midpoint/interval 仅作为内部中间变量, 不再是搜索维度.

---

## ADR-006: 扩展窗口交叉验证 (Expanding Window CV)

**日期**: 2026-07-01
**状态**: 待实施 (P3)
**优先级**: P3

### 背景

端到端搜索需要在外样本上评估阈值组合。金融时序数据不能随机打乱（look-ahead bias）。

### 决策

**采用扩展窗口交叉验证**，而非随机 K-fold 或简单 train/test split。

依据: Lopez de Prado (2018) "Advances in Financial Machine Learning" 第 7 章。

```
Fold 1: train [0:12] → valid [12:18]
Fold 2: train [0:18] → valid [18:24]
Fold 3: train [0:24] → valid [24:30]
```

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 简单 train/test | 简单 | look-ahead bias | ❌ |
| B: 随机 K-fold | 标准 ML | 时序泄露 | ❌ |
| C: 扩展窗口 | 无 look-ahead bias | 早期折数据少 | ✅ |
| D: Purged K-fold | 更多折 | 实现复杂 | ❌ (远期) |

### 后果

- **正面**: 无 look-ahead bias，符合金融数据特性
- **负面**: 早期折训练数据少，可能导致高方差估计
- **风险**: 3 折可能不够，远期可增加折数或使用 Purged K-fold

---

## ADR-007: 回测引擎集成方案 — Peer Module + Adapter Pattern

**日期**: 2026-07-01
**状态**: 已实施
**优先级**: P0

### 背景

需要将因子回测引擎集成到 factor_pipeline 中，计算 IC、ICIR、收益率、换手率等指标，并接入 FactorHealthMonitor 进行健康度评估和漂移检测。外部回测引擎 (`engine_v3_vector.py`) 依赖 DataLoaderV3 格式，且外部 Factor_Fingerprint 中的 `FactorHealthMonitor` 独立实现了 IC 计算，存在重复。

### 决策

**采用方案 D: 新建 `backtest/` peer module + adapter pattern**。

具体方案:
- P1: `factor_metrics.py` — 因子级指标单一真相源（所有 IC/ICIR/decay/turnover 计算唯一权威）
- P2: `data_bridge.py` — Pipeline 输出 (n_stocks, n_dates) → DataLoaderV3 格式 (n_dates, n_stocks) 适配器
- P3: `engine.py` — 回测引擎，改编自 `engine_v3_vector.py`，使用 `factor_metrics.py` 作为唯一真相源
- P4: `health_bridge.py` — 回测引擎输出 → FactorHealthMonitor 适配器，注入预计算指标
- P5: `unified_drift.py` — 双轨融合漂移判定：结构漂移 (Fingerprint) + 性能漂移 (Backtest) + 换手率漂移
- P6: `pipeline_integration.py` — 端到端 Pipeline 集成 + BacktestConfig 配置扩展

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 独立模块 Factor_Backtest | 完全解耦 | 无 Pipeline 联动，需独立维护 | ❌ |
| B: 集成到 Fingerprint | 复用 HealthMonitor | 循环依赖，高耦合 | ❌ |
| C: 集成到 Pipeline | 减少模块数 | 违反单一职责，Pipeline 臃肿 | ❌ |
| D: Peer module + Adapter | 高内聚低耦合，不修改外部模块 | 需适配器层 | ✅ |

### 核心设计原则

1. **单一真相源**: `factor_metrics.py` 是唯一权威，外部模块不得重复实现 IC 计算
2. **适配器模式**: data_bridge/health_bridge 通过 importlib 加载外部模块，不改动外部代码
3. **双轨融合**: 结构漂移 (Fingerprint) + 性能漂移 (Backtest) → UnifiedDriftReporter 融合判定
4. **importlib 绕过重依赖**: data_bridge 和 health_bridge 直接加载外部模块，绕过 `core/__init__.py` 的 cvxpy/jax 等依赖

### 后果

- **正面**: Pipeline 输出可直接回测 → 健康度评估 → 漂移检测，全链路闭环。不修改外部模块，保持低耦合。
- **负面**: 新增 6 个模块，测试代码量增加。DataBridge 需要转置操作 (n_stocks, n_dates → n_dates, n_stocks)。
- **风险**: 外部模块 API 变更时适配器需同步更新。core 模块命名空间冲突（Factor_Trading_v3.0 和 Factor_Fingerprint 均使用 `core` 作为包名），初版通过 `types.ModuleType` 注册 package 解决，但残留 `sys.modules['core']` 会遮蔽 Factor_DB/core，Fix 7 (ADR-011) 补全了清理逻辑。

---

## ADR-008: L2 磁盘缓存层 (CacheManager + CachedDataLoader)

**日期**: 2026-07-01
**状态**: 已实施
**优先级**: P0

### 背景

回测引擎每次运行都从 Factor_DB (DuckDB) 重新查询因子和价格数据。对于 20 个因子 × 5 年数据,数据加载耗时约 1.5s,而缓存命中后仅需 0.3s。历史缓存方案 (PipelineCache/SimpleCache/QueryCache) 存在干扰调试、键不稳定、freq 丢失等问题。

### 决策

**采用三层缓存架构: CacheManager (基础设施) → PriceMatrixCache/FactorMatrixCache/FwdReturnsCache (具体缓存) → CachedDataLoader (统一入口)**。

设计三原则 (优先级递减):
1. **P0 可调试性**: 三层透明度 — 日志层 (HIT/MISS/INVALIDATE) + 元数据层 (.meta.json) + 环境变量逃生舱 (`FACTOR_PIPELINE_CACHE=disabled`)
2. **P1 正确性**: 数据指纹校验 (head/tail hash + nan_ratio) + 损坏自愈 + 双轴 freq 保真 (parquet 不保留 DatetimeIndex.freq)
3. **P2 性能**: 数据真相驱动失效 (不依赖 TTL 猜测,基于 db_loaded_at_max + 指纹)

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: TTL 过期缓存 | 简单 | 猜测失效时间,可能用过期数据 | ❌ |
| B: 内存 LRU 缓存 | 最快 | 进程重启丢失,难以调试 | ❌ |
| C: L2 磁盘 + 指纹校验 | 可调试,跨进程,数据真相驱动 | 磁盘 IO 开销 | ✅ |
| D: 修改 Factor_DB 加缓存层 | 统一 | 改动外部模块,违反隔离 | ❌ |

### 核心设计

- **CacheManager**: L2 磁盘缓存,支持 DataFrame (.parquet) + ndarray (.npy),每个文件附 .meta.json 记录来源签名和指纹
- **PriceMatrixCache**: 价格矩阵缓存,包装 PriceQuery.get_price_matrix()
- **FactorMatrixCache**: 因子矩阵缓存,包装 FactorPivotAdapter.get_pivoted(),支持部分命中 (仅查询未缓存的因子)
- **FwdReturnsCache**: 前向收益 ndarray 缓存,接受 compute_fn 按需计算
- **CachedDataLoader**: 统一入口,业务代码一处替换即可启用缓存

### 后果

- **正面**: 数据加载阶段 4.36x 加速 (1.466s → 0.336s),因子矩阵 16.47x 加速。环境变量一键禁用,调试无干扰。
- **负面**: 磁盘空间占用 (每个缓存文件约 100KB-1MB)。首次运行无加速 (需写缓存)。
- **风险**: db_loaded_at_max 变化时缓存不会自动失效 (需显式 invalidate 或依赖指纹校验)。当前端到端加速被回测引擎计算时间掩盖 (1.04x),数据加载阶段加速显著 (4.36x)。

### 测试

- CacheManager: 34/34
- PriceMatrixCache: 12/12 (手工校验 3.5x)
- FactorMatrixCache: 12/12 (手工校验 16.47x)
- CachedDataLoader: 13/13 (手工校验 4.36x)
- FwdReturnsCache: 10/10
- 端到端集成: 4/4 (结果完全一致)
- 总计: 85/85 通过

---

## ADR-009: 分组并行方案保留 (拒绝统一日期范围)

**日期**: 2026-07-01
**状态**: 已决策 (不实施改进,保留方案 A)
**优先级**: P3

### 背景

P1 修复 (因子日期自适应 min_dates) 引入了 `reindex` 对齐逻辑 ([data_bridge.py:150-165](file:///f:/Coding/factor_pipeline/backtest/data_bridge.py#L150-L165)),所有因子在 DataBridge 内部被对齐到 `close_df` 的 (dates, stocks) 索引。这引发了一个假设:既然所有因子已经被 reindex 对齐,是否可以取消 `parallel_runner.py` 的按日期分组逻辑,统一共享一个全局 `fwd_returns`?

潜在收益: 1 次 fwd_returns 计算 + 全局并行,预估 1.3-1.5x 加速,代码更简洁。

### 决策

**保留方案 A (按日期分组 + 组内共享),不实施方案 B (统一日期范围)**。

### 决策依据 — A/B 对比实验

使用 20 个真实因子 (13 个 Barra 月频 41 天 + 7 个日频 1212 天) 进行 A/B 对比实验:
- 方案 A: `ParallelFactorRunner` 按日期分组,组内共享 fwd_returns
- 方案 B: 统一日期范围 + 全局共享 fwd_returns (基于完整 price_data)

实验脚本: [tests/test_backtest/experiment_p3_2_ab_comparison.py](file:///f:/Coding/factor_pipeline/tests/test_backtest/experiment_p3_2_ab_comparison.py)

#### 结果

| 因子类型 | 因子数 | ICIR 一致性 | 最大 ICIR diff | 最大 IC diff |
|----------|--------|-------------|----------------|--------------|
| 日频因子 (1212天) | 7 | ✓ 完全一致 | 0.00000000 | 0.00000000 |
| Barra 因子 (41天) | 13 | ✗ 差异巨大 | 0.89505144 | 0.14787308 |

性能: 方案 A 44.82s vs 方案 B 137.81s (方案 B **3x 更慢**)

### 根因分析

**日频因子完全一致** 证明 NaN 处理链本身是正确的。

**Barra 因子差异巨大** 的根因是 **fwd_returns 的语义不同**,而非 NaN 传播问题:

```
方案 A (正确):
  Barra 因子 41 天 (月末) + price 裁剪到 41 天 (月末)
  → fwd_returns[t] = (price月末[t+1] - price月末[t]) / price月末[t]
  → IC = corr(因子月末, 月末到月末的收益率)
  → 衡量: "Barra 因子对次月收益的预测能力"

方案 B (错误):
  Barra 因子 reindex 到 1212 天 (41天有值 + 1171天NaN)
  + price 完整 1212 天 (日频)
  → fwd_returns[t] = (price日[t+1] - price日[t]) / price日[t]
  → IC = corr(因子月末, 日到日的收益率)  ← 只在月末日期计算
  → 衡量: "Barra 因子对次日的预测能力"
```

**本质问题**: 方案 B 将不同频率因子统一到日频,导致 fwd_returns 的语义改变。Barra 因子 (月频) 的 IC 从 "月收益率预测" 变成了 "日收益率预测",这是完全不同的指标。

### 备选方案

| 方案 | 正确性 | 性能 | 代码复杂度 | 选择 |
|------|--------|------|------------|------|
| A: 按日期分组 + 组内共享 | ✓ 各频率独立 | 44.82s (基准) | 中 | ✅ |
| B: 统一日期范围 + 全局共享 | ✗ 频率语义改变 | 137.81s (3x 慢) | 低 | ❌ |
| C: 混合 (分组 + 组间共享) | ✓ 但需日期对齐 | 未测试 | 高 | ❌ (复杂度高) |

### 后果

- **正面**: 保留方案 A 确保不同频率因子使用对应频率的 fwd_returns,IC 语义正确。无需引入复杂的频率对齐逻辑。
- **负面**: 组间串行执行,无法进一步并行化。但 20 因子 44.82s 已可接受。
- **风险**: 如果未来需要支持更多频率混合 (如周频 + 月频 + 季频),组数增加导致串行开销增大。
- **缓解**: 当前 2 组 (月频 + 日频) 串行开销可接受。如需优化,可考虑方案 C (混合) 或缓存优化 (已通过 CachedDataLoader 实现)。

### 经验教训

1. **reindex 对齐 ≠ 语义等价**: P1 修复的 reindex 对齐解决了 NaN 填充问题,但不同频率因子的 fwd_returns 语义不同,reindex 不能消除这种差异。
2. **实验驱动决策**: 方案 B 在理论上看似合理 (NaN 处理链正确),但 A/B 实验揭示了频率语义问题。如果直接实施而未做实验,会引入隐蔽的正确性 bug。
3. **性能预期可能反转**: 方案 B 预估 1.3-1.5x 加速,实际 3x 更慢。原因: Barra 因子 reindex 到 1212 天后,IC 计算需遍历 1211 期 (vs 方案 A 的 40 期),NaN 跳过虽快但仍有开销。

---

## ADR-010: 配置系统统一 — 方案 C 桥接层

**日期**: 2026-07-02
**状态**: 已实施
**优先级**: P1

### 背景

factor_pipeline 存在两套并行配置系统:
- `PipelineV2Config` (dataclass, 18 字段, `pipelines_v2.py`) — Pipeline 运行时使用
- `PipelineV2ConfigUnified` (Pydantic, 21 顶层字段, `config_v2.py`) — 端到端优化器使用

仅 4 个共享字段直接对应 (`hard_routing_prob`, `merge_alpha`, `ks_alpha`, `mixed_winsor_sigma`),其余字段命名/结构不同。双轨制导致: (1) 新增配置需在两处维护; (2) 优化器修改 Unified 配置后,需手动同步到 Pipeline 运行时; (3) 用户需理解两套配置的映射关系。

### 决策

**采用方案 C: 桥接层 (不合并,不重构)**。

在两套配置之间添加转换方法:
- `PipelineV2ConfigUnified.to_pipeline_v2_config()` — Unified → dataclass
- `PipelineV2Config.from_unified(unified)` — dataclass ← Unified (等价入口)

字段映射策略:
1. **4 共享字段**: 直接复制
2. **概念对应字段**: `classification_threshold_static` → `classification.static_ar1_threshold` 等
3. **嵌套 → 扁平**: `static.garch.enabled` → `static_enable_garch` 等

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 统一到 dataclass | 单一真相源 | 丢失 Pydantic 校验,改动大 | ❌ |
| B: 统一到 Pydantic | 有校验 | Pipeline 运行时侵入大 | ❌ |
| C: 桥接层 | 最小改动,双向兼容 | 两套配置仍并存 | ✅ |
| D: 完全重构 | 理想 | 工作量大,高风险 | ❌ (远期) |

### 后果

- **正面**: 优化器可直接用 Unified 配置,通过 `to_pipeline_v2_config()` 转换为 Pipeline 运行时配置,无需手动同步。13 项 TDD 测试 + 8 项手工校验确保字段映射正确。
- **负面**: 两套配置仍并存,新增字段需同时更新桥接方法。
- **风险**: 字段映射可能遗漏 (通过 round-trip 测试缓解)。

### 测试

- TDD: 13/13 通过 (test_fix2_config_unification.py)
- 手工校验: 8/8 字段映射一致 (verify_fix2_manual.py)

---

## ADR-011: core 命名空间隔离策略

**日期**: 2026-07-02
**状态**: 已实施
**优先级**: P0

### 背景

三个外部模块均使用 `core` 作为子包名:
- `Factor_DB/core/` — DuckDB 连接 (`core.connection.DuckDBConnection`)
- `Factor_Fingerprint/core/` — 因子指纹和健康度 (`core.fingerprint`, `core.health`)
- `Factor_Trading_v3.0/core/` — 数据加载 (`core.data_v3.DataLoaderV3`)

Python 的 `sys.modules` 只能有一个 `core` 入口。`health_bridge.py` 用 `types.ModuleType` 注册 `core` 指向 Factor_Fingerprint/core (加载 fingerprint.py 和 health.py 的相对导入所需),加载后未清理,导致 `from core.connection import DuckDBConnection` 失败 (ModuleNotFoundError)。

影响: `test_p0_duckdb_pivot.py` 和 `test_integration_real_data.py` 在全量回归时收集错误 (单独运行不受影响,因为加载顺序不同)。

### 决策

**采用"加载后清理"策略**。

两层修复:
1. **data_bridge.py**: 模块名从 `"core.data_v3"` 改为 `"_factor_trading_data_v3"` (避免注册 `core` 命名空间); 移除 `sys.path.insert(0, Factor_Trading_v3.0)` (data_v3.py 不需要)
2. **health_bridge.py**: 加载完 `core.fingerprint` 和 `core.health` 后,恢复旧 core 模块; 若 `sys.modules['core']` 仍指向 Factor_Fingerprint/core (即首次加载无旧 core),删除它,让后续 `core` 导入从 sys.path 重新解析

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 重命名外部包 core → unique | 根治 | 改动外部模块,违反隔离 | ❌ |
| B: 每次导入前清理 sys.modules['core'] | 简单 | 脆弱,依赖调用顺序 | ❌ |
| C: 加载后清理 + 非冲突模块名 | 最小改动,不碰外部 | 仍有潜在时序问题 | ✅ |
| D: 虚拟环境隔离 | 完全隔离 | 过度工程 | ❌ |

### 后果

- **正面**: 全量回归测试不再有 core 命名空间冲突。`core.fingerprint` 和 `core.health` 保留在 sys.modules 中 (health_bridge 正常工作),`core.connection` 从 sys.path 解析到 Factor_DB/core。导入顺序不敏感 (data_bridge 不再注册 core,health_bridge 加载后清理,任意顺序都正确)。
- **负面**: 无顺序依赖,但 `health_bridge` 的清理逻辑依赖 `_core_pkg` 对象身份比较,若未来重构需保持此模式。
- **风险**: 如果未来新增第四个 `core` 包,需扩展清理逻辑。长期建议外部模块重命名 `core` 为唯一名称。

### 测试

- TDD: 6/6 通过 (test_fix7_core_namespace_collision.py)
- 导入顺序固化: 15/15 通过 (test_fix7_import_order.py) — 验证任意顺序加载、reload 幂等、core 路径正确
- 手工校验: 6/6 (health_bridge 类可用、core.fingerprint/health 保留、DuckDBConnection/FactorQuery 可导入、sys.modules['core'] 重新解析到 Factor_DB/core)
- 回归: 157 unit + 95 backtest = 252 passed
- 历史失败修复: test_p0_duckdb_pivot.py 16/16 (之前收集错误)

---

## ADR-012: 外部路径环境变量配置化

**日期**: 2026-07-02
**状态**: 已实施
**优先级**: P1

### 背景

`data_bridge.py` 和 `health_bridge.py` 硬编码了外部模块路径 (`F:/Coding/Factor_Trading_v3.0`, `F:/Coding/Factor_Fingerprint`)。在非开发环境 (CI/CD、其他机器) 下路径不存在,导致 import 失败。且 `test_fix5_hardcoded_paths.py` 测试要求源码中不含硬编码路径字面量。

### 决策

**采用环境变量配置化,默认值保持向后兼容**。

```python
_FACTOR_TRADING_PATH = Path(os.environ.get(
    "FACTOR_TRADING_PATH", "F:/Coding/Factor_Trading_v3.0"
))
_FINGERPRINT_PATH = Path(os.environ.get(
    "FINGERPRINT_PATH", "F:/Coding/Factor_Fingerprint"
))
```

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 保持硬编码 | 零改动 | 不可移植 | ❌ |
| B: 环境变量 + 默认值 | 可移植 + 向后兼容 | 环境变量需文档化 | ✅ |
| C: 配置文件 | 灵活 | 增加复杂度 | ❌ |
| D: 动态搜索 | 自动 | 不可预测 | ❌ |

### 后果

- **正面**: 路径可通过环境变量覆盖,CI/CD 环境只需设置 `FACTOR_TRADING_PATH` 和 `FINGERPRINT_PATH`。默认值保持开发环境向后兼容。
- **负面**: 用户需知道环境变量名 (通过文档和 `config_v2.py` 的 `ExternalPathsConfig` 解决)。
- **风险**: 环境变量未设置时使用默认值,在非开发环境会静默失败 (通过 import 错误暴露)。

### 测试

- TDD: 6/6 通过 (test_fix5_hardcoded_paths.py)

---

## ADR-013: 外部模块子包化 + 直接导入替代 importlib/sys.path 黑魔法

**日期**: 2026-07-02
**状态**: 已实施
**优先级**: P1

### 背景

v2.2.2 之前, factor_pipeline 通过 `importlib.util.spec_from_file_location` + `sys.path.insert` 动态加载 6 个外部模块 (Factor_DB, Factor_Fingerprint, Factor_Decoupler, Factor_AdaptiveWinsor, Factor_Imputer_v2.0, factor_neutralizer)。这种"黑魔法"带来三类问题:

1. **命名空间碰撞**: 多个外部模块的 `core/` 是 PEP 420 隐式命名空间包, `sys.modules['core']` 会被先加载者占据, 遮蔽其他模块的 `core/` 子包 (ADR-011 试图清理, 但根本上无法消除)
2. **可移植性差**: sys.path hack 在非开发环境 (CI/CD、其他机器) 失效
3. **可维护性差**: 60+ 行 importlib 代码散落于 health_bridge.py / cached_data_loader.py / adapters.py

### 决策

**采用"子包化 + pip install -e . + 直接导入"方案**:

1. **子包化 (P1.1)**: 6 个外部模块均添加顶层 `__init__.py` 和 `core/__init__.py`, 将 `core/` 从 PEP 420 命名空间包升级为各自顶层包的正式子包 (`Factor_DB.core`, `Factor_Fingerprint.core`, ...), 符合 `django.core` / `pandas.core` 惯例。每个模块添加 `pyproject.toml`, flat-layout 模块 (Factor_DB / Factor_AdaptiveWinsor / Factor_Imputer_v2.0) 使用 `where = [".."]` 让 find_packages 正确发现包。
2. **pip install -e . (P1.1f)**: 6 个模块均以 editable 模式安装到当前 Python 环境, 通过 `__editable__.X.pth` + finder 机制让 `Factor_DB` / `Factor_Fingerprint` 等成为顶层可导入包。
3. **直接导入 (P1.2)**: factor_pipeline 内部的 importlib / sys.path hack 全部替换为直接导入:
   - `health_bridge.py`: 60+ 行 importlib → 6 行 `from Factor_Fingerprint.core.health import`
   - `cached_data_loader.py`: sys.path hack → `from Factor_DB.query.price_query import PriceQuery`
   - `adapters.py`: 3 个 adapter 的 `_get_X_class()` 改为直接导入, 保留 `_import_external_class` 仅用于测试 override 路径
   - 外部模块内部导入也批量修复 (`from query.X import` → `from Factor_DB.query.X import` 等, 共 42 处替换)
4. **P1.3 修复**:
   - **ProcessingAdapter standardization 按列 fit**: AdaptiveStandardizer 全局展平 fit + 按列 transform 不能保证每列均值=0 (截面因子时序标准化语义), 改为对每列单独 fit_transform。其他 process_type (outlier/transformation) 保留全局 fit 行为不变。
   - **test_health_bridge test_12 sys.modules 清理**: 测试中临时注册的 `sys.modules['core']` 在 `_old_core is None` 时未清理, 污染后续测试, 增加 `sys.modules.pop('core', None)` 兜底。

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 保持 importlib hack | 零改动 | 命名空间碰撞、不可移植、可维护性差 | ❌ |
| B: 子包化 + pip install -e . + 直接导入 | 彻底解决碰撞、可移植、代码简洁 | 需要外部模块配合 (添加 pyproject.toml + __init__.py) | ✅ |
| C: 重命名 core/ 为各模块独有子包名 (如 fp_core/) | 不需 pip install | 破坏外部模块独立性、改名工作量大 | ❌ |

### 后果

- **正面**:
  - 命名空间碰撞彻底消除, `sys.modules['core']` 不再被任何模块占据
  - factor_pipeline 代码减少 60+ 行 importlib hack, 可读性大幅提升
  - 外部模块可通过 `pip install -e .` 标准化分发, CI/CD 环境友好
  - P1.3 修复后, StaticFactorPipeline 的 standardize 步骤符合截面因子时序标准化语义 (每列均值=0)
- **负面**:
  - 外部模块需维护 `pyproject.toml`, flat-layout 需 `where = [".."]` (易错点)
  - Factor_Imputer_v2.0 含 `.` 的目录名需 package-dir 映射 (`Factor_Imputer_v2_0` 替代)
- **技术债**:
  - ProcessingAdapter 在 standardization 与其他 process_type 间的 fit 行为不一致 (按列 vs 全局), 待 P3 adapters 重构统一
  - ~~Factor_Trading_v3.0 仍保留 importlib hack (data_bridge.py)~~ → 已在 ADR-016 (TD-1) 中解决

### 测试

- P1.1f: 6/6 模块 pip install -e . 成功, 导入验证通过
- P1.2: factor_pipeline 内部无 importlib/sys.path hack 残留 (test_fix7_import_order.py 全通过)
- P1.3: 全量回归 614 passed, 4 skipped, 0 failed (tests/, 不含 test_p3_phase4_integration.py)
- 关键测试: test_pipelines_v2.py 9/9 通过 (含修复后的 test_static_pipeline_processing)

---

## ADR-014: 依赖锁定 — pyproject.toml + REQUIRED/OPTIONAL 分离 + 删除优雅回退

**日期**: 2026-07-02
**状态**: 已实施
**优先级**: P2

### 背景

v2.2.3 之前, factor_pipeline 主项目自身没有 `pyproject.toml`, 无法 `pip install`, 依赖关系散落于各模块的 `try/except ImportError` 块中, 存在三类问题:

1. **依赖不可见**: 项目实际依赖 numpy/pandas/scipy/statsmodels/networkx/pydantic/duckdb + 6 个外部本地模块, 但无任何文件声明, 新环境部署需逐个 `import` 试错
2. **优雅回退掩盖故障**: `ImputerAdapter` / `ProcessingAdapter` 在外部模块导入失败时静默回退到简单实现 (中位数填充 / 等长截断), `is_fallback_mode=True` + `warnings.warn`, 导致用户在不知情下使用降级算法
3. **HAS_XXX 死代码**: `HAS_SCIPY` / `HAS_STATSMODELS` / `HAS_PIPELINE` 标记实际依赖永远存在 (scipy/statsmodels 是核心依赖, pipelines_v2 是自身模块), try/except 块和 fallback 路径成为不可达死代码

### 决策

**采用"pyproject.toml 锁定 + REQUIRED/OPTIONAL 分离 + AdapterImportError 显式失败"方案**:

1. **P2.2 创建 pyproject.toml**:
   - REQUIRED 依赖: numpy/pandas/scipy/statsmodels/networkx/pydantic/duckdb + 6 个外部模块 (factor-fingerprint / factor-decoupler / factor-db / factor-adaptive-winsor / factor-imputer / factor-neutralizer)
   - OPTIONAL extras: `[garch]` (arch), `[optimizer]` (optuna), `[dev]` (pytest), `[all]` (全部)
   - flat-layout 配置 `where = [".."]` (与 ADR-013 外部模块相同), PyPI 规范化包名 (Factor_Imputer_v2.0 → factor-imputer)

2. **P2.4 删除优雅回退**:
   - `ImputerAdapter` / `ProcessingAdapter`: 构造时即校验 REQUIRED 依赖, 失败抛 `AdapterImportError` (而非 `is_fallback_mode=True` + warnings.warn)
   - 删除 `_simple_winsorize` / `_simple_standardize` / 中位数填充等 fallback 路径
   - `is_fallback_mode` 属性保留但永远为 `False` (向后兼容)
   - `GarchWhiteningAdapter` 保留真实 fallback (arch 为 OPTIONAL 依赖)

3. **P2.5 清理 HAS_XXX 死代码**:
   - `HAS_SCIPY` (pipelines_v2.py / optimizer.py): scipy 是 REQUIRED, 直接导入
   - `HAS_STATSMODELS` (adapters.py / performance.py): statsmodels 是 REQUIRED, 直接导入
   - `HAS_PIPELINE` (optimizer.py): `factor_pipeline.pipelines_v2` 是自身模块, 直接导入, `HAS_PIPELINE = True` 保留向后兼容
   - 保留 `HAS_ARCH` / `HAS_OPTUNA` (真实 OPTIONAL 依赖)

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 保持 try/except + 优雅回退 | 零改动 | 依赖不可见、故障被掩盖、死代码 | ❌ |
| B: pyproject.toml + REQUIRED/OPTIONAL 分离 + AdapterImportError | 依赖可见、故障显式、死代码清除 | 需创建 pyproject.toml + 改测试 | ✅ |
| C: requirements.txt 锁定 | 简单 | 无 extras 机制、不可 pip install | ❌ |

### 后果

- **正面**:
  - factor_pipeline 可 `pip install -e .` 标准化安装, 新环境部署只需 `pip install -e .[all]`
  - REQUIRED 依赖缺失时立即抛 `AdapterImportError`, 不再静默降级
  - 删除 ~50 行 fallback 死代码, 代码可读性提升
  - HAS_XXX 标记从 5 个减至 2 个 (仅保留真实 OPTIONAL: HAS_ARCH / HAS_OPTUNA)
- **负面**:
  - 测试需更新: `assertWarns(UserWarning)` → `assertRaises(AdapterImportError)`, mock 测试不再能模拟 fallback
  - `is_fallback_mode` 属性保留为 `False` (向后兼容, 但语义弱化)
- **技术债**:
  - `NeutralizerAdapter` 仍保留 fallback 逻辑 (industry_data 缺失时返回原数据), 待 P3 统一处理
  - ~~`backtest/data_bridge.py` 仍保留 importlib hack~~ → 已在 ADR-016 (TD-1) 中解决
  - ~~`test_parallel_is_not_slower_than_serial` 性能 flaky~~ → 已在 ADR-016 (TD-2) 中解决 (Windows skipif)

### 测试

- P2.3: pip install -e . 成功, 元数据正确, 跨目录导入验证通过
- P2.4: test_p1_fixes (24-28) + test_adapters_mock 全通过 (31 passed), fallback 测试改为 assertRaises(AdapterImportError)
- P2.5: 导入验证通过 (HAS_SCIPY/HAS_STATSMODELS/HAS_PIPELINE 清理, 直接导入无误)
- P2.6: 全量回归 613 passed, 4 skipped, 1 failed (性能 flaky 预存在, 0 新增失败)
- 版本统一: 手工校验 5/5 (2.2.3 一致), 版本单元测试 7 passed

---

## ADR-015: adapters 重构 — NeutralizerAdapter REQUIRED 化 + GarchWhiteningAdapter 模块级导入

**日期**: 2026-07-02
**状态**: 已实施
**优先级**: P3

### 背景

ADR-014 (P2 依赖锁定) 将 ImputerAdapter / ProcessingAdapter 改为 REQUIRED 依赖 + AdapterImportError, 但 NeutralizerAdapter 和 GarchWhiteningAdapter 仍保留旧模式, 存在五类问题:

1. **NeutralizerAdapter 仍保留 fallback 逻辑**: factor_neutralizer 已在 ADR-013 中 pip install, 但 adapter 仍用 `is_fallback_mode = (neutralizer_class is None)` + `warnings.warn` 静默回退, 与 Imputer/Processing 模式不一致
2. **NeutralizerAdapter 双重导入**: `__init__` 调用 `_get_neutralizer_class()`, `fit` 又调用一次, 浪费且易错
3. **`_simple_industry_neutralize` 中 `if sm is None:` 死代码**: statsmodels 在 ADR-014 已是 REQUIRED 依赖, 此检查永远为 False
4. **`self._neutralizer = 'external'` 字符串标记**: fit() 中用字符串 `'external'` 标记外部模块可用, 但实际从未读取此标记, 无意义的弱类型契约
5. **GarchWhiteningAdapter `_get_arch_model_class()` 重复导入**: 模块级已有 `_arch_model` (顶层 try/except), fit() 中又通过方法重新 try/except 导入, 重复且冗余

### 决策

**采用"NeutralizerAdapter REQUIRED 化 + GarchWhiteningAdapter 模块级导入 + 死代码清理"方案**:

1. **P3.2 NeutralizerAdapter REQUIRED 化**:
   - `__init__` 缓存 `_neutralizer_class`, 失败抛 `AdapterImportError` (与 Imputer/Processing 一致)
   - `is_fallback_mode` 永远为 `False` (向后兼容)
   - `fit()` 删除 fallback 路径和重复导入, 简化为仅设置 `is_fitted = True`
   - 删除 `self._neutralizer = 'external'` 字符串标记
   - `_simple_industry_neutralize` 删除 `if sm is None:` 死代码

2. **P3.3 GarchWhiteningAdapter 模块级导入**:
   - 删除 `_get_arch_model_class()` 方法 (重复导入)
   - `fit()` 直接使用模块级 `_arch_model` (顶层 try/except 已处理导入)
   - 保留真实 fallback (arch 是 OPTIONAL 依赖, `is_fallback_mode = not HAS_ARCH` 语义不变)

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 保持 NeutralizerAdapter fallback | 零改动 | 与 ADR-014 不一致、死代码、双重导入 | ❌ |
| B: NeutralizerAdapter REQUIRED + GarchWhitening 模块级导入 | 一致性、死代码清除、简化 | 需改测试 | ✅ |
| C: 删除 GarchWhiteningAdapter fallback | 彻底简化 | arch 是真实 OPTIONAL, 不应强制 | ❌ |

### 后果

- **正面**:
  - 三个 REQUIRED adapter (Imputer/Processing/Neutralizer) 行为一致: 构造时校验, 失败抛 AdapterImportError, `is_fallback_mode` 永远 False
  - 唯一保留真实 fallback 的 GarchWhiteningAdapter (arch OPTIONAL) 语义清晰
  - 删除 ~40 行 fallback 死代码 + 重复导入, 代码可读性提升
  - NeutralizerAdapter 不再用字符串 `'external'` 标记, 弱类型契约消除
- **负面**:
  - 测试需更新: test_26 `assertWarns(UserWarning)` → `assertRaises(AdapterImportError)`
  - `is_fallback_mode` 属性在 NeutralizerAdapter 上语义弱化 (永远 False)
- **技术债**:
  - ~~`backtest/data_bridge.py` 仍保留 importlib hack~~ → 已在 ADR-016 (TD-1) 中解决
  - ~~`test_parallel_is_not_slower_than_serial` 性能 flaky~~ → 已在 ADR-016 (TD-2) 中解决 (Windows skipif)
  - NeutralizerAdapter 的 fit() 仍只是标记状态 (FactorNeutralizer 需文件路径初始化), 真正的中性化逻辑在 transform() 的 `_simple_industry_neutralize`, 待未来重构

### 测试

- P3.4: test_p1_fixes (24-28) + test_adapters_mock 全通过 (32 passed, 2 skipped, 3 subtests)
- P3.5: 手工校验 5/5 (NeutralizerAdapter REQUIRED 抛错 / 正常构造 / GarchWhitening 模块级导入 / 死代码清理 / is_fallback_mode 永远 False)
- P3.5: 全量回归 614 passed, 4 skipped, 1 failed (性能 flaky 预存在, 0 新增失败)
- 新增测试: `TestNeutralizerAdapter.test_fallback_when_external_module_missing` (与 Imputer/Processing 对称)

---


## ADR-016: 技术债清理 — Factor_Trading_v3.0 子包化 + data_bridge.py importlib hack 清理 + test_parallel flaky 修复

**日期**: 2026-07-02
**状态**: 已实施
**优先级**: TD (技术债清理)
**前置**: ADR-013 (外部模块子包化), ADR-014 (依赖锁定), ADR-015 (adapters 重构)

### 背景

ADR-013 子包化了 6 个外部模块但遗留 Factor_Trading_v3.0 (因 core/__init__.py 重依赖链). ADR-014/015 的技术债章节记录了三项遗留问题:

1. **TD-1**: `backtest/data_bridge.py` 仍保留 `importlib.util.spec_from_file_location` hack 加载 DataLoaderV3 (ADR-013 遗留, 因 Factor_Trading_v3.0 的 core/__init__.py 导入 10+ 重依赖模块)
2. **TD-2**: `test_parallel_is_not_slower_than_serial` 性能 flaky (Windows multiprocessing spawn 开销, 实测并行 4.5s vs 串行 0.7s, 5x 阈值不可靠)
3. **TD-3**: NeutralizerAdapter fit() 仅标记状态, 真正中性化逻辑在 transform() (设计层面, 延后)

### 决策

**TD-1: Factor_Trading_v3.0 最小子包化 + data_bridge.py 直接导入**

1. **子包化**: Factor_Trading_v3.0 添加 `[tool.setuptools] packages + package-dir` 声明根包 + core 子包
   - `__init__.py` 改为轻量 (仅 `__version__`), 删除 `from core.config import ...` 等重依赖导入
   - `core/__init__.py` 改为空, 删除 10+ 模块的便利导出 (用户需显式 `from Factor_Trading_v3_0.core.data_v3 import DataLoaderV3`)
   - `python -m pip install -e .` 后 `Factor_Trading_v3_0` 可从任意目录导入
2. **data_bridge.py 清理**: `importlib.util.spec_from_file_location` hack → `from Factor_Trading_v3_0.core.data_v3 import DataLoaderV3` 直接导入 + AdapterImportError
   - 原 hack 的两个原因已消除: (1) core/__init__.py 已空 (2) Factor_Trading_v3_0.core 命名空间不与 Factor_DB/core 冲突
3. **test_fix7_import_order.py 更新**: `test_data_bridge_does_not_register_core` 从检查 `_factor_trading_data_v3` 旧模块名改为检查 `from Factor_Trading_v3_0.core.data_v3 import` 直接导入 + 无 bare `from core.` + 无 importlib 残留

**TD-2: test_parallel flaky 修复 — Windows skipif**

- `test_parallel_is_not_slower_than_serial` 添加 `@pytest.mark.skipif(sys.platform == 'win32', ...)`
- Windows multiprocessing 默认用 spawn 方法, 每个子进程需重新导入所有模块, 小数据量下并行必然慢于串行
- Linux fork 方法无此问题, 保留测试
- 功能正确性由 `test_all_factors_processed` 和 `test_no_duplicate_results` 覆盖

**TD-3: NeutralizerAdapter fit/transform 语义重构 — 延后**

- 设计层面问题: `_neutralizer_class` 被导入但从未实例化, fit() 只设 `is_fitted=True`, 实际中性化靠 `_simple_industry_neutralize` (statsmodels) 或外部传入实例
- 需深入理解 FactorNeutralizer API 才能正确重构, 延后至未来迭代

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| TD-1A: 完整子包化 (所有子包) | 完整 | 过度暴露未使用模块 | ❌ |
| TD-1B: 最小子包化 (根+core) | 精准, 仅暴露 factor_pipeline 依赖的包 | 其他子包需时再追加 | ✅ |
| TD-2A: 改阈值为 10x | 简单 | 仍 flaky, 阈值无意义 | ❌ |
| TD-2B: Windows skipif | 诚实, 保留 Linux 测试 | Windows 下无性能测试 | ✅ |

### 后果

- **正面**:
  - data_bridge.py 删除 ~30 行 importlib hack, 改为 6 行直接导入 + AdapterImportError, 可读性大幅提升
  - Factor_Trading_v3.0 子包化后, factor_pipeline 的所有 7 个外部依赖均通过 pip install -e . 管理, 无 importlib 残留
  - test_parallel flaky 消除 (Windows skip, 1 skipped 而非 1 failed)
  - test_fix7_import_order.py 从检查旧 hack 模式升级为检查新直接导入模式
- **负面**:
  - Factor_Trading_v3.0 的 `__init__.py` / `core/__init__.py` 改为轻量, 原 `from core import BacktestEngine` 便利导出失效 (用户需显式导入)
  - Windows 下无并行性能测试 (功能测试仍覆盖)
- **技术债**:
  - TD-3 NeutralizerAdapter fit/transform 语义重构 (延后, 设计层面)
  - `types.py` 与 stdlib `types` 模块同名, 从 factor_pipeline cwd 运行 `python -m` 时遮蔽 stdlib (预存在, 非 TD-1 引入, 需从 F:\Coding 父目录运行测试)

### 测试

- TD-1.5: 手工校验 6/6 (包导入 / DataLoaderV3 解析 / importlib 清理 / 旧常量清理 / 直接导入 / 端到端)
- TD-1.5: test_fix5_hardcoded_paths 6/6 (test_02/test_03 更新为检查直接导入)
- TD-1.5: test_fix7_import_order 15/15 (test_data_bridge_does_not_register_core 更新)
- TD-2: test_p0_parallel::test_parallel_is_not_slower_than_serial 1 skipped (Windows skipif 生效)
- TD-1+TD-2: 全量回归 620 passed, 5 skipped, 0 failed (0 新增失败)
---

## ADR-017: 跨版本 CI 矩阵 — GitHub Actions + tox 双轨

**日期**: 2026-07-02
**状态**: 已实施
**优先级**: P4

### 背景

v2.2.6 完成技术债清理后, factor_pipeline 建立了干净基线 (620 passed / 5 skipped / 0 failed). 但项目缺乏持续集成 (CI) 保障:
- 无 `.github/workflows/` 配置, 推送代码不会自动测试
- 无 `tox.ini` / `noxfile.py`, 本地无法快速验证跨 Python 版本兼容性
- `pyproject.toml` 声明 `requires-python = ">=3.9"`, classifiers 列出 3.9/3.10/3.11/3.12, 但从未在多版本下测试

### 决策

**采用 GitHub Actions + tox 双轨 CI 方案**.

1. **GitHub Actions** (`.github/workflows/ci.yml`):
   - 矩阵: Python 3.10/3.11/3.12 × ubuntu-latest
   - Windows 暂不纳入矩阵 (multiprocessing spawn 开销使 test_parallel flaky, ADR-016)
   - 外部模块处理: `git clone` 7 个 StormstoutLau/* 仓库到父目录, 模拟本地 monorepo 结构
   - 目录名重命名: `Factor_Imputer` → `Factor_Imputer_v2.0`, `Factor_Trading` → `Factor_Trading_v3.0`, `Factor_Neutralizer` → `Factor_Neutralizer_v2.0` (匹配 pyproject.toml package-dir 映射)
   - 测试步骤: 从父目录运行 `python -m pytest factor_pipeline/tests/` (避免 types.py 遮蔽 stdlib, ADR-016)
   - `fail-fast: false` — 一个版本失败不影响其他版本继续跑
   - `workflow_dispatch` 允许手动触发

2. **tox.ini** (本地多版本测试):
   - 环境: py310, py311, py312 + lint + coverage
   - `isolated_build = True`, `skip_missing_interpreters = True`
   - `deps` 显式声明 7 个外部模块的 editable 安装路径 (`-e {toxinidir}/../Factor_DB`)
   - `changedir = {toxinidir}/..` — 从父目录运行 pytest 避免 types.py 遮蔽
   - `[testenv:lint]` — YAML/Python 语法快速检查
   - `[testenv:coverage]` — 带覆盖率的测试

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 仅 GitHub Actions | 标准做法, 推送即生效 | 本地无法快速验证 | ❌ |
| B: 仅 tox | 本地立即可用 | 无远程 CI 保障 | ❌ |
| C: 两者结合 | 远期 + 近期双重覆盖 | 配置量大 | ✅ |
| D: nox | Python 代码更灵活 | 额外依赖, 与 tox 重复 | ❌ |
| E: pre-commit hooks | 提交前拦截 | 不覆盖测试, 仅 lint | ❌ (补充) |

### 后果

- **正面**: 推送代码到 GitHub 自动触发 3 × 1 = 3 个矩阵 job; 本地 `tox -e py311` 快速验证单版本; `tox -e lint` 快速语法检查
- **负面**: 外部模块的 `git clone` 依赖仓库公开可访问; tox 每个 env 重新安装 7 个外部模块 (慢, ~5min/env)
- **风险**: 外部模块仓库 URL 变更或设为私有时 CI 会失败 (需更新 workflow)
- **缓解**: workflow 中 `git clone` 用 `|| { echo "WARNING"; }` 容错, 单模块失败不阻塞其他模块安装

### 测试

- P4.4 本地校验: 37/37 通过 (YAML 语法 + 矩阵配置 + tox.ini 语法 + deps 引用 + changedir 等)
- 回归测试: test_fix7_import_order 15/15 + test_fix5_hardcoded_paths 6/6 (CI 配置不破坏现有测试)

### 技术债

1. **Windows CI 未覆盖**: 矩阵仅 ubuntu-latest, Windows 平台特定行为 (skipif) 未在 CI 中验证
2. **外部模块仓库依赖**: CI 依赖 StormstoutLau/* 仓库公开可访问, 若仓库私有需配置 SSH key
3. **tox 未安装**: hermes venv 未安装 tox, 需 `pip install tox` 才能本地使用
4. **Python 3.9/3.13 未覆盖**: 矩阵仅 3.10/3.11/3.12 (3.9 EOL 临近, 3.13 Anaconda 本地未充分测试)
5. **types.py 遮蔽**: 从 factor_pipeline cwd 运行 python -m 仍破坏 bootstrap (ADR-016 预存在技术债, CI/tox 通过 changedir 规避)


---

## ADR-018: NeutralizerAdapter fit/transform 语义重构 — fit 预计算 dummies

**日期**: 2026-07-02
**状态**: 已实施
**优先级**: P3 (技术债)

### 背景

v2.2.5 (ADR-015) 时识别但延后的设计层面技术债。旧 `NeutralizerAdapter` 的 `fit()` 是空操作 (仅设 `is_fitted=True`), 所有计算集中在 `transform()` 中临时调用 `_simple_industry_neutralize()`。这导致:

1. **语义不一致**: 与兄弟 adapter (`ImputerAdapter`/`ProcessingAdapter`) 的 `fit()` 预计算 + `transform()` 应用模式不符
2. **重复计算**: 同一 `industry_data` 的 `pd.get_dummies` + `sm.add_constant` 在每次 `transform()` 时重新计算
3. **kwargs 透传 bug**: `fit_transform(X, industry_data=...)` 中的 `industry_data` kwarg 不会被 `fit()` 捕获, `transform()` 检查的是 `__init__` 传入的 `self.industry_data`, 导致 `fit_transform` 忽略透传的 industry_data (TDD Red 阶段 `test_residuals_match_direct_ols` 暴露此 bug)
4. **不可检测 fit 状态**: 由于 fit() 是空操作, 无法通过 fit 状态判断是否已预计算, 迫使 transform 每次重复计算

### 决策

**采用 fit() 预计算 industry dummies 矩阵 + transform() 用缓存做 OLS 残差的方案**。

具体实现:
- `fit(X, industry_data=None)`: 接受 `industry_data` kwarg (优先) 或用 `__init__` 传入的 `self.industry_data`, 对每个日期:
  - `dropna()` 因子值, 检查截面样本量 `>= MIN_CROSS_SECTIONAL_OBS(10)`
  - 与 `industry_data.index` 取交集, 检查 `>= MIN_INDUSTRY_COMMON_OBS(5)`
  - 预计算 `(dummy_matrix_with_const, common_stocks_Index)` 元组缓存到 `self._industry_dummies_cache[date]`
- `transform(X)`: 3 级优先级:
  1. `external_neutralizer` kwarg (向后兼容, 调用外部 `.industry_neutralization(X, method)`)
  2. `self._industry_dummies_cache` 非空时调用 `_neutralize_with_cache(X)` 做截面 OLS + 残差
  3. 无缓存时跳过中性化 (返回原 X)
- `_neutralize_with_cache(X)`: 对每个在缓存中的日期, 用 `sm.OLS(y, dummy_matrix).fit().resid` 计算残差, 维度不匹配或失败时回退原值, 最终 `fillna(0)`

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 保持旧实现 (fit 空操作, transform 临时计算) | 改动最小 | 语义不一致, 重复计算, kwargs 透传 bug | ❌ |
| B: fit 预计算 dummies + transform 用缓存 | 与兄弟 adapter 一致, 消除重复计算, 修复 kwargs bug | 缓存内存开销 (N日期 × K股票矩阵) | ✅ |
| C: 完全委托给外部 FactorNeutralizer (像 Imputer 委托给 HierarchicalImputer) | 单一真相源 | 外部模块签名是 `__init__(factor_dir, price_dir, ...)` 文件路径驱动, 不适配 DataFrame 输入 | ❌ (签名不匹配) |
| D: 删除外部模块路径, 完全内联实现 | 无外部依赖 | 与 ADR-015 (REQUIRED 依赖) 矛盾 | ❌ |

### 后果

- **正面**:
  - 四个 adapter (`Imputer`/`Processing`/`Neutralizer`/`GarchWhitening`) 的 `fit()` 语义一致 (预计算 + 缓存)
  - `transform()` 不再重复计算 dummies, 大规模回测时性能提升 (与日期数成线性)
  - 修复 `fit_transform(X, industry_data=...)` kwargs 透传 bug
  - `fit()` 状态可检测 (`_industry_dummies_cache` 非空表示已预计算)
- **负面**:
  - 缓存内存开销: N 日期 × K 股票 × (1 + 行业数-1) 浮点数 (例如 252 日 × 3000 股 × 4 列 ≈ 24MB, 可接受)
  - 跨日期 `industry_data` 变化时需重新 fit (与 Imputer 跨日期 missing_info 变化需重新 fit 一致)
- **风险**:
  - transform 时日期维度与 fit 时不匹配会跳过该日期 (回退原值), 不抛异常 — 需在调用方日志中监测

### 测试

- **TDD Red (TD-3.3a)**: 新增 `test_td3_neutralizer_semantics.py` (12 个测试, 6 类): 重构前 5 failed/7 passed
- **TDD Green (TD-3.3b)**: 重构后 12 passed
- **手工校验 (TD-3.4)**: 6 项独立数值校验 (A: dummies 缓存结构 / B: OLS 残差一致 / C: fit_transform==fit().transform() / D: 无 industry_data 跳过 / E: external_neutralizer 优先级 / F: NaN 边界) 全部 PASS, 精度 1e-10
- **全量回归 (TD-3.4)**: 632 passed, 5 skipped (比基线 620 +12 新测试, 0 新增失败)

### 技术债

1. **`_industry_dummies_cache` 内存**: 大规模回测 (1000+ 日期 × 5000+ 股票) 时缓存可能占用较多内存, 未来可考虑 LRU 缓存或磁盘缓存
2. **industry_data 跨日期变化**: 当前假设 industry_data 静态, 若行业分类随时间变化需重新 fit (无自动检测)
3. **transform 维度不匹配静默跳过**: transform 时若日期维度与 fit 时不匹配仅 warning 不抛异常, 可能掩盖 bug


---

## ADR-019: 外部模块内化 — 从 monorepo 模拟转为单一仓库

**日期**: 2026-07-02
**状态**: 已实施 (v2.4.0, 2026-07-03)
**优先级**: P4 (架构优化)

### 背景

v2.2.3 (ADR-013) 引入子包化 + `pip install -e .` 管理 7 个外部模块, v2.2.6 (ADR-016) + v2.3.0 (ADR-017) 完善了最小子包化和 CI 矩阵。但该架构存在 4 个持续痛点:

1. **版本命名混乱**: `Factor_Imputer_v2.0` 目录含 ".", Python 包名 `Factor_Imputer_v2_0` 用 `_v2_0` 替代, PyPI 名 `factor-imputer` 又无后缀 — 三套命名并存, 维护成本高
2. **结构不一致**: Imputer 用 flat-layout + package-dir 映射, Neutralizer 用 src-layout, 其他用 flat-layout, 三种结构并存
3. **CI 复杂度**: GitHub Actions 需 git clone 7 个仓库到父目录 + 目录重命名 + 各自 pip install; tox 需 deps 声明 7 个 editable 路径 — 配置复杂且易碎
4. **开发摩擦**: 改外部模块需切换目录, git 操作分散在 7 个仓库, 调试时 import 错误信息混淆

### 决策

**将 5 个模块内化到 `factor_pipeline/modules/` 子包, 保留 Factor_DB 和 Factor_Trading 作为外部数据边界**。

具体方案:
- **内化 5 个模块** (统一小写蛇形命名, 移除版本后缀):
  - `Factor_Fingerprint` → `factor_pipeline/modules/factor_fingerprint/`
  - `Factor_Decoupler` → `factor_pipeline/modules/factor_decoupler/`
  - `Factor_AdaptiveWinsor` → `factor_pipeline/modules/factor_adaptive_winsor/` (最小子包化: 只迁 core/)
  - `Factor_Imputer_v2.0` → `factor_pipeline/modules/factor_imputer/` (移除 `_v2_0` 后缀)
  - `Factor_Neutralizer_v2.0` → `factor_pipeline/modules/factor_neutralizer/` (src-layout → flat-layout + 依赖裁剪)
- **保留 2 个外部模块** (设计意图: 数据库-管道-回测边界):
  - `Factor_DB`: 数据入库与查询, 通过 `cached_data_loader.py` 的 `PriceQuery` 接口隔离
  - `Factor_Trading_v3.0`: 回测数据加载, 通过 `data_bridge.py` 的 `DataLoaderV3` 接口隔离
- **命名规范化**: 全部小写蛇形 (`factor_fingerprint`), 符合 PEP 8 包命名规范, 版本信息留在模块内 `__version__`
- **依赖裁剪**: Neutralizer 的 matplotlib/joblib/psutil/numba 改为可选导入或删除 (主项目仅需中性化功能); AdaptiveWinsor + Imputer 的 scikit-learn 为主项目新增 REQUIRED 依赖

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 保持现状 (7 个独立仓库 + editable install) | 模块可独立分发 | 命名混乱, CI 复杂, 开发摩擦 | ❌ |
| B: 全部内化 (含 Factor_DB + Factor_Trading) | 最简架构 | 破坏数据边界设计意图, 主项目耦合数据基础设施 | ❌ |
| C: 内化 5 个处理模块, 保留 DB/Trading 外部 | 平衡架构简洁与数据边界 | 失去 5 模块独立分发能力 | ✅ |
| D: 改用 git submodule | 保持独立仓库 + 单一克隆 | submodule 操作复杂, 路径仍混乱 | ❌ |

### 后果

- **正面**:
  - 单一 git 仓库, 版本管理统一
  - 命名干净一致 (全部小写蛇形, 无版本后缀)
  - CI 大幅简化 (删除 git clone 块, 删除 7 个 editable 路径声明, 只需 `pip install -e ".[all]"`)
  - 依赖边界清晰 (pyproject.toml 只声明 numpy/pandas/scipy/statsmodels/sklearn)
  - 开发便利 (IDE 跳转/grep/refactor 一键完成)
- **负面**:
  - 失去 5 模块独立分发能力 (对于 Research OS 场景, 独立分发是虚假收益)
  - 主项目代码量从 ~5000 行增至 ~15000 行
  - 未来若需重新拆分, 成本较高
- **风险**:
  - Neutralizer 依赖裁剪可能影响中性化功能 — 需 TDD 验证
  - 批量 import 路径替换 (~62 处) 可能遗漏 — 需全量回归保障

### 实施路径 (5 阶段)

1. **阶段 1**: Factor_Decoupler + Factor_Fingerprint (零新增依赖, ~9 文件, ~45 处 import 替换)
2. **阶段 2**: Factor_AdaptiveWinsor (最小子包化, 新增 sklearn)
3. **阶段 3**: Factor_Imputer (版本后缀移除, 新增 sklearn 共享)
4. **阶段 4**: Factor_Neutralizer (src-layout 转换 + 依赖裁剪 + 验证导入路径 bug)
5. **阶段 5**: CI/文档清理 (删除 git clone 块, 简化 tox, 更新 ADR + project_memory)

### 技术债 (内化后保留)

1. Factor_DB / Factor_Trading 仍为外部依赖, CI 需保留其 git clone 逻辑
2. Factor_AdaptiveWinsor 的 batch/parallel/pipeline/report 子包未内化 (主项目未使用)
3. Neutralizer 的可视化/并行/内存监控功能裁剪后不可逆

### 实施结果 (v2.4.0, 2026-07-03)

5 阶段全量回归始终 **632 passed 零回归**:

| 阶段 | 模块 | 关键修复 | 回归 |
|------|------|---------|------|
| I1 | Fingerprint + Decoupler | 命名规范化, ~45 处 import 替换 | 632 passed |
| I2 | AdaptiveWinsor | 最小子包化 (仅 core/), 依赖上界冲突检测 | 632 passed |
| I3 | Imputer | 22 处导入清理 (调研预估仅 4 处), try/except hack 清理 | 632 passed |
| I4 | Neutralizer | src→flat-layout, 依赖裁剪, plt.Figure 注解修复 | 632 passed |
| I5 | CI/文档清理 | CI monorepo 7→2, 删除 7 失效脚本, 版本号 11 处统一 | 632 passed, 5 skipped |

**关键经验**:
1. 模块独立性对独立分发才有价值, 单仓库场景下独立性是虚假收益 — 内化优于子包化
2. 函数内导入比模块级导入更难发现 (调研 4 处 vs 实际 22 处), 必须用 Grep 全文搜索
3. 依赖上界冲突是隐蔽陷阱 (pyextremes 声明 pandas<3.0.0 会自动降级而非报错)


---

## ADR-020: 多因子横截面正交化模块 — 对称正交化为主方法

**日期**: 2026-07-02
**状态**: 已实施 (O1+O2+O3a+O3b+O4+O5+O6 完成, 单元+手工 93/93 通过, 全量回归 860 passed + 5 skipped, sys.path 污染技术债已修复 ADR-020 技术债 #5)
**优先级**: P5 (新功能)

### 背景

现有系统有两个正交化维度:
- **时序正交化**: Factor_Decoupler 实现, 消除单因子时间序列自相关 (AR/HP/差分)
- **横截面正交化**: **未实现** — 消除多因子在同一时刻的截面相关性, 提取独立 alpha

用户需求: 对多因子做正交化分析, 识别冗余因子, 拆解独立 alpha 贡献。

### 决策

**新增 `factor_pipeline/modules/factor_orthogonalizer/` 模块, 以对称正交化 (Symmetric Orthogonalization) 为主方法, 实施三层架构分离 (Layer 1/2/3)**。

### 三层架构分离 (v1.1 执行方案)

| Layer | 职责 | 模块位置 | 监督性 | 状态 |
|-------|------|---------|--------|------|
| **Layer 1** | per-factor 处理 (已有) | `pipelines_v2.py` | 无监督 | 已实施 |
| **Layer 2** | cross-factor 横截面正交化 (新增) | `modules/factor_orthogonalizer/` | 无监督 | 待实施 |
| **Layer 3** | target-aware 显著性检验 (新增) | `backtest/factor_significance.py` | 有监督 (需 Y) | 待实施 |

### 5 种正交化算法

| 算法 | 数学定义 | 适用场景 | 选择 |
|------|---------|---------|------|
| **Symmetric (Löwdin)** | `W = (F^T F)^(-1/2) = V Λ^(-1/2) V^T` | 默认主方法, VRR=1, 无顺序依赖 | ✅ (默认) |
| **Ridge** | `W = (F^T F + λI)^(-1/2)` | 病态矩阵兜底, λ 自适应 (Ledoit-Wolf 2004) | ⚠️ (可选) |
| **PCA** | `T = F V_k` (前 k 个主成分) | 降维场景, center 参数兼容 Layer 1 标准化 | ⚠️ (可选) |
| **Gram-Schmidt** | 顺序投影, κ>100 启用 Kahan (1966) 二次投影 | 顺序依赖场景, 有因果优先级 | ⚠️ (可选) |
| **Cholesky** | `F^T F = L L^T, W = L^(-T)` | 半正定保证场景 | ⚠️ (可选) |

### 核心约束 (v1.1 深化)

1. **对称正交化为默认主方法**: `T = F @ W, W = (F^T @ F)^(-1/2)`, 无顺序依赖, 所有因子平等
2. **正交化模块默认关闭** (`enabled=False`): 不影响 632 基线测试, 零开销
3. **Pipeline 不重构**: 正交化作为 `post_transform_hooks` 半侵入式接入, 保持 per-factor 循环不变
4. **Treatment 轮询模式**: 每个因子独立当 treatment, 顺序不影响结果 (Layer 3)
5. **双重 Lasso (Belloni-Chernozhukov 2014 PDS)**: Stage1 Lasso Y~X → S_Y; Stage2 Lasso D_k~X → S_D; Stage3 OLS Y~D_k+X_{S_Y∪S_D}
6. **HC3 稳健标准误** (MacKinnon-White 1985): 对异方差和杠杆点稳健
7. **Benjamini-Hochberg FDR 校正**: 多因子检验控制 False Discovery Rate
8. **条件数分级 (Belsley-Kuh-Welsch 1980)**: κ<10 good / <100 acceptable / <1000 warning / ≥1000 severe
9. **病态矩阵特征值截断** (threshold_mode='auto'): eigvals < max_eigval * eps_truncate 时截断
10. **Ridge λ 选择** (lambda_selection='ledoit_wolf'): Ledoit-Wolf (2004) 自适应收缩
11. **Gram-Schmidt re-orthogonalization** (Kahan 1966): κ>100 时二次投影提升数值稳定性
12. **fit_from_gram 接口**: 从 G = F^T F 直接估计 W, 避免 re-stack F_window (Rolling 优化)
13. **增量 Gram 矩阵更新**: RollingOrthogonalizer 的 O(K²) 滑动窗口优化, reset_interval=500 定期重置
14. **因子对齐策略** (align_mode): intersection / union_nan / raise_on_mismatch 三模式
15. **VRR (Variance Retention Ratio)**: `VRR_k = Var(T_k)/Var(F_k)`, 对称正交化理论值 = 1.0, VRR << 1 表示因子 k 高度冗余

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 对称正交化 (Symmetric) | 无顺序依赖, 保留所有因子信息 | 变换后因子失去原始经济含义 | ✅ (默认) |
| B: Gram-Schmidt | 顺序明确, 第一个因子不变 | 顺序主观, 不对称 | ⚠️ (可选) |
| C: Cholesky | 下三角, 严格因果 | 顺序依赖, 数值不稳定 | ⚠️ (可选) |
| D: PCA | 降维 + 正交 | 因子语义改变, 难解释 | ⚠️ (可选, 远期) |

### 后果

- **正面**:
  - 形成因子诊断三件套: 描述 (Fingerprint) → 解耦 (Decoupler) → 正交化 (Orthogonalizer)
  - 冗余因子识别 (VRR 排序 + 阈值)
  - 独立 alpha 贡献拆解 (正交化后回归系数稳定)
  - 三层架构分离, Layer 2 无监督变换与 Layer 3 有监督检验职责清晰
- **负面**:
  - 正交化后因子失去原始经济含义, 归因报告需标注
  - 新增 ~120 测试, 测试套件膨胀至 ~752
- **风险**:
  - 高度共线性时 F^T·F 接近奇异, 需正则化 (eps 参数 + Ridge 兜底)
  - 多因子 PIT 对齐 (因子发布延迟差异) 需处理
  - 双重 Lasso 的 LassoCV 收敛性需检测, S_D 全空集时需深层处理

### 实施路径 (6 阶段, v1.1)

1. **O1**: Layer 2 算法核心 (P0) — 5 个算法类 + O1.12 深化 (7 项) — ~40 测试 — ✅ 完成 (44 测试 + 15 手工校验)
2. **O2**: Layer 2 适配器层 (P0) — OrthogonalizerAdapter + Config + O2.8 深化 (6 项) — ~20 测试 — ✅ 完成 (22 测试 + 12 手工校验)
3. **O3a**: Layer 2 几何诊断 (P0) — VRR/κ/VIF/正交性误差 + O3a.6 深化 (5 项) — ~15 测试 — ✅ 完成 (18 单元测试 + 24 手工校验, 含 VRR 数学修正)
4. **O3b**: Layer 3 因子检验 (P1) — 双重 Lasso (Belloni 2014 PDS) + O4.9 深化 (7 项) — ✅ 完成 (17 单元测试 + 14 手工校验, 含 HC3 公式 bug 修复)
5. **O4**: 回测扩展 (P1) — RollingOrthogonalizer + ICChangeMonitor + O4.9/O4.11 深化 — ✅ 完成 (11 单元测试 + 19 手工校验, 含 O4.11.1/2/3/5 深化, O4.11.4 warm-start 设计标注可选未实现)
6. **O5**: 协同设计 (P1) — Grouped + TripleChain + O5.6 深化 (5 项) — ✅ 完成 (15 单元测试 + 17 手工校验, 含 O5.6.1 数据流协议/O5.6.2 中性化顺序/O5.6.3 缺失因子/O5.6.4 缓存/O5.6.5 冲突解决)
7. **O6**: 文档验证 (P1) — 版本号 11 处同步 + ADR-020 状态更新 + 全量回归 (~752 passed)

### 技术债

1. PipelineStep 接口不扩展, 正交化通过 `post_transform_hooks` 半侵入式接入
2. 多因子 PIT 对齐逻辑需与 data_bridge 的 loaded_at 机制集成
3. 正交化后因子解释性丢失, 需在归因报告中明确标注
4. GPU 加速 (CuPy, HAS_CUPY 标记) 作为可选依赖, 远期实施
5. **O3a 暴露的 sys.path 污染 (预存在, 非本次引入)**: `test_fix7_core_namespace_collision.py` 行 27-28 把 Factor_DB 加入 sys.path, 触发 `core` 包注册到 sys.modules, 污染后续 `from factor_pipeline.modules.factor_orthogonalizer.core import ...` 解析 (test_import_from_core 失败, `is` 比较为 False). 单独跑 O3a 测试 135/135 通过, 全量回归时该测试受污染失败. 修复方向: 在该测试 finally 块清理 sys.path. 留待 O6 阶段统一处理.
6. **VRR 数学修正 (O3a 发现)**: 文档 O3a.4 原方案 "对称正交化 VRR=1" 基于 "保持方差" 直觉, 实际数学不成立. 对称正交化使 T^T T = I (||T_k||=1), 故 Var(T_k) ≈ 1/N, 对 randn F (||F_k||≈sqrt(N), Var(F_k)≈1) 有 VRR ≈ 1/N < 1. VRR=1 仅当 F 列预归一化为单位范数时成立. 测试已修正为数学正确版本 (test_vrr_symmetric_compresses_variance), 手工校验同时验证两种情况 (randn VRR≈1/N, unit_norm F VRR=1).

### O3a 经验教训

1. **直觉假设需数学验证**: 文档 O3a.4 "对称正交化 VRR=1" 看似合理 (基于 "保持方差" 直觉), 但实际对称正交化保持的是正交性 (T^T T=I), 不是单因子方差. TDD Red 阶段暴露此数学错误, 说明手工数值校验是发现直觉错误的必要环节 (ADR-018 经验的再次印证).
2. **VRR 的 ddof 不变性是数学性质**: VRR = Var(T,ddof)/Var(F,ddof), 分子分母同时乘 N/(N-1), 比值不变. 这不是巧合, 是 VRR 定义的内在性质 (比值统计量). 测试 1e-12 精度验证此不变性.
3. **共线因子构造的 rho ≠ 实际 corr**: `_make_collinear_factors(rho)` 用 `F = sqrt(rho)*base + sqrt(1-rho²)*noise`, 但 Var(F_k) = rho + (1-rho²) = 1+rho-rho², 实际 corr = rho/sqrt(1+rho-rho²) < rho. rho=0.95 实际 corr≈0.90, VIF≈7 (未达 >10 阈值); 需 rho=0.99 (实际 corr≈0.98, VIF≈30). 测试参数选择需基于实际统计量而非参数名.
4. **条件数定义需统一**: λ_max/λ_min (特征值比) vs σ_max/σ_min (SVD 奇异值比) 差异为平方关系 (σ = sqrt(λ)). diagnostics.py 采用特征值比, 与 base.py 的 `condition_number_` 一致, 避免诊断指标与算法内部不一致.
5. **JSON 序列化的 inf/nan 处理**: 标准 JSON 不允许 Infinity/NaN 字面量 (ECMAScript 兼容性), 需递归转换为 null. `_to_jsonable()` 函数处理 numpy 类型 + inf→null, 确保 `json.loads(json_str)` 不报错且 `Infinity`/`NaN` 字面量不出现在输出字符串中.

### O3b 经验教训

1. **TDD 共享 bug 陷阱 (核心教训)**: HC3 公式实现用 `residuals / (1-h)^2` (应为 `residuals**2 / (1-h)^2`), 测试代码用同一错误公式校验, 单元测试 17/17 通过但实现是错的. 只有与独立实现 (statsmodels cov_HC3) 对比才暴露此 bug. 结论: **TDD 测试与实现共享同一公式错误时无法发现 bug, 必须用第三方独立实现 (statsmodels/scipy) 做手工校验**. 这是 ADR-018 "手工数值校验是 TDD 必要补充" 经验的更深层印证.
2. **sqrt(invalid value) 警告是 bug 指示器**: HC3 公式错误导致 cov 矩阵非 PSD (对角线为负), `np.sqrt(负数)` 产生 nan + RuntimeWarning. 最初用 `np.maximum(diag, 0)` clip 掩盖了警告, 实际是公式错误的信号. 结论: **数值警告不应被 clip 掩盖, 应追溯根因**. clip 仅在公式正确后作为极端数值误差的防御性措施保留.
3. **BH 校正 rank 方向易混淆**: BH 算法定义 rank 为升序位置 (最小 p = rank 1, 最大 p = rank K), 从大到小处理时 rank = K-i. 手工计算时若用降序 (argsort(-p)) 且 rank 从 1 递增, 会得到错误结果. 结论: **BH 校正测试必须与 statsmodels.stats.multitest.multipletests 对比验证**.
4. **HC3 se > OLS se 不是数学保证**: 最初测试断言 "异方差下 HC3 se > OLS se", 实际 HC3 se 是否大于 OLS se 取决于残差与杠杆的关联方向, 非数学保证. 结论: **测试断言应基于数学恒等式 (如公式实现正确性), 非经验性大小关系**.
5. **惰性初始化兼容直接注入测试场景**: `fit()` 中填充 `y_normalized_` 但测试直接注入 `F_`/`y_` 跳过 `fit()`, 导致 `y_normalized_` 未初始化. 解法: `__init__` 中设 `y_normalized_ = None`, `_double_lasso_test` 中惰性初始化. 结论: **属性初始化必须考虑测试直接注入的场景, 惰性初始化是简洁的兼容方案**.

### O4 经验教训

1. **np.bool_ 与 Python bool 的 is 比较陷阱**: `is_orth = np.zeros(T, dtype=bool)` 产生 numpy bool 数组, `is_orth[0] is False` 在 numpy bool_ 类型下返回 False (因为 `np.False_ is False` 为 False, 它们是不同对象). 解法: 用 `== False` / `== True` 替代 `is False` / `is True`. 结论: **numpy bool 数组的断言必须用 == 比较, 不能用 is**.
2. **look-ahead bias 测试需用反证法**: 验证 "t 期 W 不含 F[t] 信息" 不能只检查 W 数值正确, 需构造 "修改 F[t] 后 W_t 不变" 的反证场景. 直接对比 W_ 与用过去数据 fit 的 W 一致性是正向验证, 反证法 (修改未来数据不影响当前 W) 才是 look-ahead bias 的严格验证. 结论: **look-ahead bias 测试必须用反证法, 仅正向数值一致不足以证明无前瞻**.
3. **增量 Gram 更新的累积浮点误差**: `G += F.T @ F` 在长期滑动后会累积浮点误差, 表现为 G 不再严格对称 (G[0,1] ≠ G[1,0] 微小差异). O4.11.1 的 reset_interval 定期从 window_ 全量重堆叠 G 是必要的数值稳定性保障. 结论: **增量更新的累积误差必须用定期全量重置消除, 不能依赖浮点运算的精度**.
4. **fit_from_gram 对称化是 defensive programming**: 即使调用方传入的 G 看似对称, fit_from_gram 内部强制 `G = (G + G.T) / 2` 是必要的, 因为: (a) 增量更新可能产生微小不对称; (b) eigh 要求严格对称输入, 不对称会返回错误特征向量. 测试用 G[0,1] += 1e-10 验证此 defensive 行为. 结论: **数值算法的输入校验应该是 defensive 的, 即使文档要求对称输入也应在内部强制**.
5. **min_obs 边界 off-by-one 语义**: "window 长度 >= min_obs 时正交化" 的语义在 t=0 时 window=[] (长度 0), t=1 时 window=[F[0]] (长度 1), t=k 时 window=[F[0..k-1]] (长度 k). 所以 min_obs=5 时, t=5 是首次正交化 (window 长度恰等于 5). 测试必须覆盖 "恰等于" 和 "小于" 两个边界. 结论: **边界测试的 off-by-one 必须基于实际语义而非直觉, 用具体 t 值验证**.

### O5 经验教训

1. **单期 Gram vs 全样本 Gram 的混淆**: Grouped 正交化在全样本 (N·T, K) 上估计 W, 然后应用到每期 (N, K). 单期 T_t^T T_t 不严格 = I (因为 W 是基于全样本估计, 单期应用有偏差), 但全样本堆叠 T^T T 应接近 I. 最初手工校验用单期 Gram 阈值 0.1 失败 (实际 0.1385), 改为全样本 Gram 阈值 1e-10 通过. 结论: **Löwdin 正交化 T^T T = I 的性质在估计样本上成立, 应用到不同样本 (单期) 时不严格成立, 校验必须基于估计样本**.
2. **设计文档代码 snippet 的方法路径错误**: O5.2 设计文档写 `CrossSectionalOrthogonalizer._align_factors(group_dict)` 但 `_align_factors` 是模块级函数 (utils.stacking.align_factors), 不是 CrossSectionalOrthogonalizer 的方法. 实现时需对照现有代码而非盲信设计文档. 结论: **设计文档的代码 snippet 是设计意图, 不是 API 规格, 实现时必须对照现有代码确认方法路径**.
3. **数据流契约校验的位置**: O5.6.1 要求数据流契约 (keys 一致 + shape 一致) 校验, 最初在 `_compute_full_diagnosis` 内部校验, 但缓存检查在 `_compute_full_diagnosis` 之前, 导致契约不一致的输入也被缓存 (永远返回错误结果). 修正: 契约校验放在缓存检查之前. 结论: **输入校验必须在缓存之前, 否则错误输入会被缓存**.
4. **缓存 hash 的内存权衡**: `_hash_factor_dict` 用 `df.values.tobytes()` 计算内容 hash, 对 K=20 因子 × N=3000 × T=252 ≈ 240MB 数据, 每次 hash 都需要全量序列化. 设计文档建议大规模数据关闭缓存. 结论: **缓存的 hash 计算成本不能忽略, 大规模数据应关闭缓存或用增量 hash**.
5. **resolve_conflicts 的策略语义需明确**: conservative/aggressive/ic_priority 三策略的边界条件易混淆. conservative 是 "全有利才 keep", aggressive 是 "任一有利就 keep", ic_priority 是 "只看 IC". 测试必须覆盖每个策略的典型 case (如 ic_priority 下 VRR 极低但 IC 显著的因子应 keep). 结论: **策略模式测试必须覆盖每个策略的差异化行为, 不能只测一个策略**.

---

## ADR-021: v2.6.0 目标函数对齐 ADR-004 — health_penalty 代理指标方案

**日期**: 2026-07-03
**状态**: 待实施 (E4 阶段, EXECUTION_V2.6.0.md)
**优先级**: P1

### 背景

ADR-004 (2026-07-01) 设计目标函数为 `score = IC - stability_penalty - ks_penalty - health_penalty - coverage_penalty`, 其中 health_penalty 取自 HealthMonitor 综合得分 (< 40 → -0.5, < 60 → -0.2). 但代码实现 (`optimizer.py:_composite_objective`) 存在两处偏离:

1. **health_penalty 缺失**: 目标函数没有 health_penalty 项, ADR-004 设计与代码不一致
2. **fidelity 符号相反**: ADR-004 设计为 `- ks_penalty` (惩罚), 代码实现为 `+ lambda_fidelity * fidelity` (奖励)
3. **时序依赖问题**: `HealthMonitorAdapter.build_report_from_engine` 需要 engine_results 字典 (含 rank_icir/hit_rate/rank_ic_series/turnover), 只能在回测后计算, 不能在 CV fold 内部直接调用 (CV fold 仅计算 IC series, 不构建 engine_results)

### 决策

**采用代理指标方案 B (proxy indicators)**.

在 CV fold 内部用 IC decay / hit_rate / ic_volatility 三个代理指标近似 health_score, 解决时序依赖问题:

```python
def _health_penalty_proxy(self, ic_array: np.ndarray) -> float:
    decay_ratio = ...  # IC[t] / IC[0], 衰减比例
    hit_rate = ...     # IC > 0 比例
    ic_vol = float(np.nanstd(ic_array))

    if decay_ratio < 0.5 or hit_rate < 0.4 or ic_vol > 0.2:
        return 0.5  # ADR-004: < 40 → -0.5
    elif decay_ratio < 0.8 or hit_rate < 0.5 or ic_vol > 0.15:
        return 0.2  # ADR-004: < 60 → -0.2
    return 0.0
```

同时修正 fidelity 符号方向: `+ lambda_fidelity * fidelity` → `- lambda_fidelity * (1 - fidelity)`.

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: CV fold 内部调用 HealthMonitorAdapter | 与 ADR-004 字面一致 | 时序依赖破坏 CV 闭环, 需重写 _cv_evaluate | ❌ |
| **B: 代理指标 (IC decay/hit_rate/ic_vol)** | 时序无依赖, CV fold 内部可计算 | 与 health_score 相关性需 A/B 验证 | ✅ |
| C: 两阶段评估 (CV 用代理 + 最终用 HealthMonitor) | 严谨 | 计算成本翻倍 | ❌ (远期) |

### 后果

- **正面**: 目标函数与 ADR-004 设计对齐, health_penalty 通过代理指标在 CV fold 内部可计算, 不破坏时序闭环
- **负面**: 代理指标与 health_score 的相关性需 A/B 测试验证 (E4 手工校验三档: 0.5/0.2/0.0)
- **风险**: 代理指标可能引导方向偏差, 若 A/B 测试相关性不足需调整为方案 C

### 实施位置

- `optimizer.py:_composite_objective` 添加 `_health_penalty_proxy` 调用
- `optimizer.py:_health_penalty_proxy` 新方法 (E4 阶段)
- 修正 `_composite_objective` 中 fidelity 符号方向

### 测试

- ~10 个 TDD 测试 (test_p3_phase3_optimizer.py 扩展)
- 手工校验: 三档场景 (decay_ratio/hit_rate/ic_vol 各档组合) 验证 penalty 值

---

## ADR-022: v2.6.0 搜索空间扩展 — 正交化参数纳入 (P3-13)

**日期**: 2026-07-03
**状态**: 待实施 (E5 阶段, EXECUTION_V2.6.0.md)
**优先级**: P1

### 背景

v2.5.0 完成多因子横截面正交化三层架构 (ADR-020), 但 `EndToEndThresholdOptimizer` 的搜索空间 (`DEFAULT_SEARCH_SPACE`) 仍为 8 维 ADR-005 阈值, 未纳入正交化参数. 用户希望优化器能联合搜索阈值 + 正交化参数, 找到全局最优组合.

`OrthogonalizationConfig` (config_v2.py:266-356) 已有 16 个字段, 但优化器仅搜索 `migration_threshold` 字段位置错误 (optimizer.py:155-158 设置到 `config.monitor` 上, 实际应在 `config` 上, E2 修复).

### 决策

**新增 `DEFAULT_SEARCH_SPACE_ORTH` 搜索空间, 默认关闭 (`search_orth=False`)**.

扩展 3 个正交化参数:
| 维度 | 类型 | 范围 | 当前值 | 说明 |
|------|------|------|--------|------|
| `orth_method` | categorical | ['symmetric', 'ridge', 'pca', 'gram_schmidt', 'cholesky'] | 'symmetric' | 正交化算法 |
| `align_mode` | categorical | ['intersection', 'union_nan', 'raise_on_mismatch'] | 'intersection' | 因子对齐模式 |
| `ridge_lambda` | float | [0.01, 100.0] (log) | 1.0 | Ridge λ (仅 orth_method='ridge' 时生效) |

**不搜索 `orth_enabled`** (默认关闭, 启用搜索即隐含启用正交化).

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 搜索全部 16 字段 | 完整 | 搜索维度爆炸, 多数字段非数值 | ❌ |
| **B: 仅搜索 3 关键字段 (method/align/lambda)** | 维度可控, 覆盖主决策点 | 其他字段用默认值 | ✅ |
| C: 不扩展搜索空间 | 零风险 | 优化器与 v2.5.0 正交化解耦 | ❌ |

### 后果

- **正面**: 优化器可联合搜索阈值 + 正交化参数, 找到全局最优组合
- **负面**: 搜索维度从 8 增至 11, n_trials 需从 100 提到 150-200
- **风险**: look-ahead bias — 正交化参数搜索时必须在 CV fold 内部 fit (用 train 数据), 不能用全量数据

### look-ahead bias 防护

`_cv_evaluate` 中正交化参数的 fit 必须在 train fold 内部完成:
```python
# 正确: train fold 内部 fit
pipeline.fit(train_factor)  # OrthogonalizerAdapter.fit 用 train 数据
# 错误: 全量 fit + train/test transform
# pipeline.fit(full_factor)  # ❌ look-ahead bias
```

### 实施位置

- `optimizer.py:DEFAULT_SEARCH_SPACE_ORTH` 新增 (E5 阶段)
- `optimizer.py:_params_to_config` 扩展设置 `OrthogonalizationConfig`
- `optimizer.py:optimize` 扩展 categorical 采样支持

### 测试

- ~8 个 TDD 测试 (含 look-ahead bias 反证法测试)
- 手工校验: 验证 train fold 内部 fit 不使用 test 数据

---

## ADR-023: v2.6.0 阈值漂移监测 — ThresholdDriftMonitor

**日期**: 2026-07-03
**状态**: 待实施 (E8 阶段, EXECUTION_V2.6.0.md)
**优先级**: P2

### 背景

`EndToEndThresholdOptimizer.optimize()` 返回 best_params 后, 阈值组合在部署后可能因市场体制变化而失效. 现有 `UnifiedDriftReporter` (backtest/unified_drift.py) 监测的是**因子值漂移** (structure + performance + turnover 三信号融合), 不监测**阈值组合本身的有效性漂移**.

P3-12 原方案引用 Hsu (2010) 并称为 "Bayesian 重新校准", 但 Hsu (2010) 实际是 frequentist 的 SDF 估计, 非 Bayesian. v1.1 修正为引用 Sullivan-TW (1999) data snooping + McLean-Pontiff (2016) publish decay.

### 决策

**新建 `backtest/threshold_drift_monitor.py`, 采用 EWMA 衰减检测**.

`ThresholdDriftMonitor` 类监测 best_score 的衰减:
- EWMA 平滑: `alpha = 1 - exp(-ln2/halflife)`, halflife=63 (约 3 个月交易日)
- 衰减触发: 当 EWMA(current_score) < (1 - decay_threshold) * best_score 时, 标记 `needs_research=True`
- 默认 decay_threshold=0.20 (即衰减超过 20% 触发重新搜索)
- min_observations=5: 至少 5 个观测后才触发, 避免早期噪声

```python
class ThresholdDriftMonitor:
    def __init__(self, best_score, best_params, halflife=63,
                 decay_threshold=0.2, min_observations=5):
        ...
    def update(self, current_score) -> Dict:
        # 返回 {ewma_score, decay_ratio, needs_research, n_observations}
```

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 简单阈值 (current < 0.8 * best) | 简单 | 噪声敏感, 单期波动误触发 | ❌ |
| **B: EWMA 衰减检测** | 平滑噪声, halflife 可调 | 滞后响应 | ✅ |
| C: CUSUM 变点检测 | 严格变点检测 | 实现复杂, 参数多 | ❌ (远期) |
| D: Bayesian 在线学习 | 持续更新 | 计算成本高 | ❌ (远期) |

### 与 UnifiedDriftReporter 的边界

| 监测器 | 监测对象 | 信号源 | 触发动作 |
|--------|---------|--------|---------|
| `UnifiedDriftReporter` | 因子值漂移 | structure (KS) + performance (ICIR) + turnover | 因子重新分类/插补 |
| `ThresholdDriftMonitor` | 阈值组合有效性 | best_score EWMA 衰减 | 阈值重新搜索 (调用 optimizer.optimize) |

### 后果

- **正面**: 阈值组合失效有自动告警, 触发重新搜索流程
- **负面**: halflife=63 与 decay_threshold=0.20 是经验参数, 需在实际数据上调参
- **风险**: 早期观测 (n < min_observations) 不触发, 可能在体制突变时延迟响应

### 实施位置

- `backtest/threshold_drift_monitor.py` 新建 (E8 阶段)
- `optimizer.py` 末尾可选注入 `ThresholdDriftMonitor` 实例

### 测试

- ~10 个 TDD 测试 (含 EWMA 数学正确性 + 触发边界 + 早期不触发)
- 手工校验: 模拟 score 序列验证 EWMA 衰减检测

---

## ADR-024: 指纹维度扩展至 21 维 (v3.0.0 T1)

**日期**: 2026-07-04
**状态**: 已实施 (E1-E3 全部完成, 974 passed + 6 skipped + 11 subtests passed)
**优先级**: P1
**supersedes**: 无 (扩展 ADR-019 内化模块的指纹定义, 不取代任何 ADR)

### 背景

`FactorFingerprint` NamedTuple 仅 13 维 (5 时序 + 5 截面 + 3 综合衍生), 尾部依赖完全缺失 (全仓库 `tail_dependence` / `copula` 命中 0 次), 体制转换仅 `FactorHealthMonitor` 有弱相关实现, 不属 `FactorFingerprint`。

ANALYSIS_V3.0.0.md §1 调研发现 4 项关键事实:
1. **孤儿函数**: `_get_multi_dim_pipeline_weights` (pipelines_v2.py) 在生产代码中从未被 `transform()` 调用, 仍用单维 `_get_pipeline_weights`
2. **分类器单维瓶颈**: `AdaptiveFactorClassifier.classify` 仅用 `ar1_median`, 其余 12 维未读取
3. **测试基线薄弱**: 无 `extract_fingerprint` 黄金参考测试, 无 `to_dict` 字段完整性测试
4. **statsmodels 延迟导入**: `_test_volatility_clustering` 用 try/except 包裹 statsmodels, 违反 ADR-014

### 决策

扩展 `FactorFingerprint` 从 13 维至 21 维, 新增 8 维 (向后兼容, 追加在 NamedTuple 末尾):

| 子任务 | 维度数 | 字段 | 学术依据 |
|--------|--------|------|---------|
| **T1.1 尾部依赖** | 4 | `tail_dependence_lower` / `tail_dependence_upper` / `gpd_shape` / `hill_estimator` | Nelsen (2006) Copula 经验条件概率; Pickands (1975) POT-MLE 替代; Hill (1975) 重尾指数 |
| **T1.2 体制转换** | 3 | `regime_transition_prob` / `regime_persistence` / `regime_ic_diff` | Hamilton (1989) Markov 两状态, 中位数划分降级方案 |
| **T1.3 综合衍生** | 1 | `tail_regime_score` | 双分量加权 (M2 修订): tail_severity + regime_instability |

`FingerprintConfig` 从 8 字段扩展至 14 字段 (新增 6 配置: `tail_quantile` / `min_extreme_samples` / `enable_tail_dependence` / `enable_regime_switching` / `regime_min_samples` / `tail_regime_weight`)。

### 关键设计

1. **默认关闭尾部依赖与体制转换**: `enable_tail_dependence=False` (Copula O(N²) 成本), `enable_regime_switching=False` (m1 修订, 避免小样本日志噪音), 显式 opt-in
2. **POT-MLE 替代 Pickands 估计量**: `_estimate_gpd_shape` 用 `scipy.stats.genpareto.fit` (POT-MLE), 比 Pickands 原始估计量对轻尾分布更稳健 (E1 Green 阶段修正)
3. **Markov 拟合不收敛降级**: `ConvergenceWarning` 检测 + 返回 NaN, 不阻塞 fingerprint 提取
4. **regime_ic_diff 方案 C**: 一阶差分均值差 (bull Δfactor 均值 - bear Δfactor 均值), 不破坏 `extract_fingerprint` 签名 (无前向收益数据输入)
5. **路由接入加 `enable_multi_dim_routing` 开关**: `PipelineV2Config` 新增配置, 默认 `False` (向后兼容), `True` 时 `transform` 使用 `_get_multi_dim_pipeline_weights` (含 T1 tail/regime 修正)
6. **不扩展 `AdaptiveFactorClassifier.classify`**: 仍仅用 `ar1_median`, 新维度仅作用于 `_get_multi_dim_pipeline_weights` 修正层 (Step 4: tail_severity 阈值 0.3 → mixed +0.10; regime_instability 阈值 0.1 → dynamic +0.10)
7. **`_derive_tail_regime_score` M2 双分量加权**: `score = w * tail_severity + (1-w) * regime_instability`, 简化公式避免嵌套权重可读性差
8. **statsmodels 顶部导入**: ADR-014 技术债清理, 移除 `_test_volatility_clustering` 的 try/except ImportError
9. **`_make_fp` 测试辅助重构为 `**kwargs` 模式**: 支持 21 维字段覆盖, 未指定字段用 NamedTuple 默认值 (NaN), 既有 12 测试向后兼容

### 测试

- E1 Red→Green: 32 测试 (25 T1 新增 + 7 既有/fixture 复用, 含黄金参考 + `to_dict` 完整性 + 8 新计算方法)
- E2 路由接入: 8 新测试 (4 TestTailRegimeAdjustment + 4 TestMultiDimRoutingConfig), 既有 12 测试零回归
- E3 手工校验: `verify_v3_0_0_t1_manual.py` 8 项 (21 维字段完整性 / to_dict 21 键 / Config 14 字段 / 默认配置 / 关闭 NaN / 开启有值 / score ∈ [0,1] / 13 维黄金参考回归)
- 全量回归: 974 passed + 6 skipped + 11 subtests (T4 基线 934 + E1 32 + E2 8 = 974, 零回归)

### 文档

- [docs/ANALYSIS_V3.0.0.md](docs/ANALYSIS_V3.0.0.md) §1 — T1 分析
- [docs/EXECUTION_V3.0.0_T1.md](docs/EXECUTION_V3.0.0_T1.md) v1.1 — E1-E3 三阶段执行方案

### 学术依据

- Nelsen, R. B. (2006). *An Introduction to Copulas* (2nd ed.). Springer. — 尾部依赖 Copula
- Pickands, J. (1975). Statistical inference using extreme order statistics. *Annals of Statistics*, 3(1), 119-131. — GPD 极值理论 (实际用 POT-MLE 替代原始估计量)
- Hill, B. M. (1975). A simple general approach to inference about the tail of a distribution. *The Annals of Statistics*, 3(5), 1163-1174. — Hill 重尾指数
- Hamilton, J. D. (1989). A new approach to the economic analysis of nonstationary time series and the business cycle. *Econometrica*, 57(2), 357-384. — Markov 体制转换

---

## ADR-025: CUSUM 在线漂移检测 (v3.0.0 T3, 2026-07-07)

**状态**: 已实施 (T3.1-T3.6 全部完成)
**supersedes**: 无 (新增)
**关联**: ADR-024 (T1 指纹扩展), v3.0.0 T3 任务

### 问题背景

v3.0.0 T3 需要在线检测因子分布漂移, 替代当前批处理 KS 检验 + EWMA 阈值监测的局限:
- `ThresholdDriftMonitor` (EWMA) 监测 score 衰减, 非因子分布漂移
- `_ks_migration_significance` 是批处理, 需 historical + recent 两段对照样本, 不适合单期增量
- `_compute_rolling_structure_drift` ~500 次 KS 检验仅 p<0.05 过滤, 无多重校正 (T3.5 待协同改进)

### 决策

引入 Page (1954) CUSUM 累积和算法, 新建 `backtest/cusum_drift_monitor.py`, 实现在线因子分布漂移检测.

**CUSUM 算法**:
- 上侧: S_pos[t] = max(0, S_pos[t-1] + (x - μ₀ - kσ))
- 下侧: S_neg[t] = min(0, S_neg[t-1] + (x - μ₀ + kσ))
- 触发: S_pos > hσ (上侧漂移) 或 S_neg < -hσ (下侧漂移)

**参数默认值**:
- k = 0.5 (slack, 检测半漂移)
- h = 5.0 (trigger, in-control ARL ≈ 930)
- two_sided = True (双向检测)
- min_observations = 1 (立即生效)

**触发后自动重置**: S_pos/S_neg 清零, 持续检测后续漂移 (标准 CUSUM 实践)

**NaN 处理**: 跳过, 不更新累积和

### 实现细节

- 参数标准化: k_sigma = k · baseline_std, h_sigma = h · baseline_std
- 参数校验: baseline_std ≤ 0 / k < 0 / h < 0 抛 ValueError
- 历史记录: S_pos_history / S_neg_history / detected_history / score_history
- 接口风格: 与 ThresholdDriftMonitor 一致 (update 返回 dict, reset, get_history, get_stats)

### 方案对比

| 方案 | 检测延迟 (1σ 漂移) | 误报率 (h=5σ) | 在线支持 | 学术血统 | 决策 |
|------|-------------------|---------------|---------|---------|------|
| A: 仅 EWMA (现状) | ~30 期 | 中 | ✅ | RiskMetrics 1996 | 不够 |
| B: 仅 KS 批处理 (现状) | 需 5+5 样本 | 低 | ❌ | Smirnov 1948 | 不够 |
| **C: CUSUM (Page 1954)** ✅ | ~10 期 | 低 (ARL≈930) | ✅ | Page 1954 经典 | **采纳** |
| D: Bayesian online changepoint | ~8 期 | 可调 | ✅ | Adams-MacKay 2007 | 过复杂, 暂不实施 |

### 影响

- 新增 `backtest/cusum_drift_monitor.py` (250 行)
- 新增 `tests/test_backtest/test_cusum_drift_monitor.py` (22 测试, 5 类)
- 与 ThresholdDriftMonitor 并行: CUSUM 监测分布漂移, EWMA 监测 score 衰减
- 不修改现有代码, 零回归 (backtest 316 passed + 1 skipped)

### 风险

- **ARL 校准未做**: docstring 标注的 ARL 值 (930/10/38/2) 来自文献经验, 需 T3.3 Monte Carlo 校准
- **与管线集成未做**: T3.4 将 CUSUM 集成到 pipelines_v2, 当前为独立模块
- **unified_drift 协同未做**: T3.5 将 BH-FDR 加入 `_compute_rolling_structure_drift`

### 回滚方案

`CUSUMDriftMonitor` 是独立新模块, 不影响现有代码. 回滚只需删除 `cusum_drift_monitor.py` + 测试文件.

### 测试

- 22 测试, 5 类: 基础功能 (5) + 检测能力 (6) + 在线更新 (4) + CUSUM vs EWMA 对比 (1) + 边界条件 (6)
- 关键测试: test_10 无漂移无误报 / test_11 上侧检测 / test_12 下侧检测 / test_13 大漂移快速检测 / test_22 触发后自动重置 / test_30 CUSUM ≤ EWMA 延迟
- 全量回归: backtest 316 passed + 1 skipped, 零回归

### 学术依据

- Page, E. S. (1954). "Continuous Inspection Schemes." *Biometrika* 41(1/2):100-115. — CUSUM 累积和算法
- Brown, R. L., Durbin, J. & Evans, J. M. (1975). "Techniques for Testing the Constancy of Regression Relationships over Time." *JRSS-B* 37(2):149-192. — 递归残差 CUSUM
- Csörgő, M. & Horváth, L. (1997). *Limit Theorems in Change-Point Analysis*. Wiley. — 变点检测极限理论
- Siegmund, D. (1985). *Sequential Analysis*. Springer. — ARL 近似公式 (T3.3 校准依据)

### 后续阶段 (T3.3-T3.6) — 已完成 (2026-07-07)

**状态**: T3.1-T3.6 全部完成, 385 passed + 1 skipped 零回归

#### T3.3 ARL Monte Carlo 校准结果

| 参数组合 | Monte Carlo ARL | Siegmund 近似 | 文献值 |
|---------|----------------|---------------|--------|
| h=5σ, k=0.5, 无漂移 | 507 (N=500, T=3000) | 285 | 930 |
| h=5σ, k=0.5, 1σ 漂移 | 5-30 (容差内) | — | 10 |
| h=5σ, k=0.5, 3σ 漂移 | 1-8 (容差内) | — | 2 |

**校准结论**:
- ARL 单调性验证通过 (ARL₀ 随 h 递增 / ARL₁ 随 δ 递减 / ARL₁ 随 h 递增)
- k=0.5 优于 k=0.75 (1σ 漂移) — slack = 0.5σ 是平衡点
- 方向对称性通过 (上侧/下侧 ARL₁ ratio < 1.3)
- ARL₀ 绝对值低于文献 930 (T 截断偏差), 相对性质完全成立
- **默认参数 k=0.5, h=5.0 经校准验证合理** (T3.4 用 h=5.5 补偿两个 CUSUM 叠加)

#### T3.4 管线集成决策

**设计**: CUSUM 作为**事后诊断工具**, 不侵入 fit/transform 循环
- 监测对象: 因子值矩阵的横截面统计量 (均值/标准差), 非 IC (IC 需 forward returns, 管线内部不计算)
- 两个 CUSUM 独立监测 (序贯检验无需 BH-FDR), h=5.5σ 补偿误报率叠加
- `monitor_cusum_drift(factor_data)` 方法: 显式调用, 非 fit/transform 自动集成
- 触发后填充 `drift_alerts['cusum_mean'/'cusum_std']`, 不自动重训练 (与 §2.3.2 方案 A 一致)
- `enable_cusum_drift_monitor=False` 默认关, 向后兼容

**新增配置**:
- `enable_cusum_drift_monitor: bool = False`
- `cusum_k: float = 0.5`
- `cusum_h: float = 5.5` (两个 CUSUM 叠加补偿)

**新增方法**: `monitor_cusum_drift(factor_data) -> Dict[str, Dict]`

**测试**: 16 测试 (配置4 + 初始化3 + 事后诊断5 + drift_alerts2 + 向后兼容2)

#### T3.5 BH-FDR 共享模块决策

**设计**: 提取 BH 核心逻辑为低级函数, 供 unified_drift / pipelines_v2 / factor_significance 共享调用

**新增模块**: `backtest/multiple_testing.py`
- `apply_bh_fdr(p_values, alpha)` — BH-FDR 校正 (Benjamini-Hochberg 1995)
- `apply_bonferroni(p_values, alpha)` — Bonferroni 校正 (FWER 控制)
- `apply_no_correction(p_values, alpha)` — 无校正
- `apply_correction(p_values, method, alpha)` — 统一入口

**重构**:
- `factor_significance.py _apply_correction`: BH/Bonferroni 路径调用共享模块 (向后兼容, Holm 保留内联)
- `pipelines_v2.py _check_ks_migration`: BH 路径调用共享模块 (向后兼容)
- `unified_drift.py _compute_rolling_structure_drift`: 新增 BH-FDR 校正 (默认), 修复 ~504 次 KS 检验的假阳性问题

**向后兼容机制**: `_HAS_MULTIPLE_TESTING` flag + 内联 fallback

**测试**: 22 (multiple_testing) + 5 (unified_drift_bh_fdr) = 27 测试

#### T3.6 文档更新

- ADR-025 状态: T3.1-T3.6 全部完成
- 风险章节: 标注"已解决 (T3.x)"
- 新增"校准结果"章节 (上文)
- 新增"集成决策"章节 (上文)

#### 全量回归

385 passed + 1 skipped, 零回归:
- CUSUM 22 测试 (T3.1-T3.2)
- ARL 校准 11 测试 (T3.3)
- multiple_testing 22 测试 (T3.5)
- unified_drift_bh_fdr 5 测试 (T3.5)
- pipelines_v2_cusum 16 测试 (T3.4)
- 全部 backtest + factor_significance + pipelines_v2 回归

#### 学术依据 (补充)

- Benjamini, Y. & Hochberg, Y. (1995). "Controlling the False Discovery Rate." *JRSS-B* 57(1):289-300. — BH-FDR 算法
- Siegmund, D. (1985). *Sequential Analysis*. Springer. — ARL 近似公式 (T3.3 校准对比)

---

## ADR-026: Audit-Driven Code Quality Remediation (v3.1.0, 2026-07-09)

**状态**: 已实施
**supersedes**: 无 (新增方法论)
**关联**: v3.1.0 audit 修复, ADR-001~025 质量保障

### 问题背景

v3.1.0 完成了内生性诊断框架 (E1-E6) 实施后, 存在大量"代码实现合理但未被规格文档捕捉"的偏离, 以及测试套件中的断言恒真式 (tautology assertion) — 测试声称验证某行为但实际只验证了数学公理或纯函数确定性。这些偏离在常规 TDD 流程中不会被发现, 因为 TDD 的 Green 阶段只关注"测试通过", 不关注"测试质量"。

### 决策

引入 **audit-driven-development** 4 阶段流程作为 v3.1.0 的质量保障闭环:

1. **Phase 1: Spec Inventory** — 规格清单盘点, 逐条核对代码实现
2. **Phase 2: Multi-Dimensional Audit** — 多维审计: §2 接口对齐 / §3 逻辑正确性 / §4 完整性 / §5 测试盲区 / §6 数值稳定性, 严重度 P0/P1/P2 分级
3. **Phase 3: Fix Priority Matrix** — 修复优先级矩阵: P0 (阻断) > P1 (高优) > P2 (可选项)
4. **Phase 4: Fix Baseline + Tracking** — 修复基线建立 + 持续追踪

### 修复规模

| 严重度 | 数量 | 类别 |
|--------|------|------|
| **P0** | 8 | 接口签名/字段缺失/逻辑错误 |
| **P1** | 8 | 关键路径/数值正确性 |
| **P2+ 断言恒真式** | 5 | RN-E2 / E3-T21 / E6-T10 / E6-T17/T18 |
| **P2+ 设计约束** | 10 | B1-B3 (字段/配置/选择器) |
| **P2+ 端到端** | 2 | C1 orchestrator + pipeline |
| **P2+ E5 测试** | 5 | 已知关系/β 范围/零权重/BH/交互 |
| **P2+ spec 对齐** | 11 | E1/E2/E4/E5/E9 16 处更新 |

### 关键原则

1. **代码优于 spec**: 当代码实现比规格文档更合理时, 反向更新 spec (11 项)
2. **非装饰性断言**: 测试断言必须能捕获真实回归 — 恒真式是"正确但不安全"
3. **配置消费验证**: 测试应验证配置通过代码路径消费 (如 r_max 是计算值), 非仅验证字段存在
4. **构造已知关系**: 用 `ic_mean = 0.05 + 0.3*gpd_shape+noise` 等已知关系替代随机数据, 确保测试的非平凡性

### 5 项断言恒真式修复策略

| ID | 恒真原因 | 修复策略 | 修复文件 |
|----|---------|---------|---------|
| RN-E2 | 纯函数确定性 | 相同 seed 一致 + 不同 seed 差异 | test_multiple_testing.py |
| E3-T21 | 构造参数回传 | 20 seed 循环, 至少一组触发 | test_endogeneity.py |
| E6-T10 | abs()≥0 数学公理 | IVX β 接近真值 0.3 | test_estimators.py |
| E6-T17 | n_zeroed 字段存在但=0 | λ=1.0 确保 n_zeroed>0 | test_estimators.py |
| E6-T18 | 同上 MCP | λ=5.0 (γ=3) 确保 n_zeroed>0 | test_estimators.py |

### 影响

- 新增 22 非平凡测试, 分布: backtest (5) / endogeneity_check (4) / endogeneity_estimators (10) / pipelines_v2 (3)
- 子集回归 754 passed + 1 skipped (零回归)
- 修复文件: 7 个 (7 test files + 1 spec doc), +820/-87 行

### 学术依据

- Benjamini, Y. & Hochberg, Y. (1995). "Controlling the False Discovery Rate." *JRSS-B* 57(1):289-300. — BH-FDR 单调性断言 (p_adj ≥ p)
- Fan, J. & Li, R. (2001). "Variable selection via nonconcave penalized likelihood." *JASA* 96(456):1348-1360. — SCAD 近端算子
- Zhang, C. H. (2010). "Nearly unbiased variable selection under minimax concave penalty." *Annals of Statistics* 38(2):894-942. — MCP 近端算子
- Oster, E. (2019). "Unobservable selection and coefficient stability." *JBES* 37(2):187-204. — r_max = min(1, multiplier × R̃)

### 回滚方案

审计修复是对测试套件的质量增强, 不改变生产代码行为。回滚不影响功能, 仅降低测试回归能力。

---

## ADR-027: 学术准则驱动管线重构 (v3.2.0, 2026-07-10)

### 背景

系统审计 5 个核心处理模块发现 ~32% 依赖硬编码启发式阈值 (数据迁就)。制定基于 15 篇学术文献的严格统计决策准则，分 9 步 TDD 实施。

### 决策

**采用学术准则驱动的固定方法管线，消除所有 `auto` 模式静默策略切换。**

### 9 步执行计划与状态

| # | 任务 | 状态 | 学术依据 |
|---|------|------|---------|
| 1 | Winsorizer `method='percentile'` (1%/99%) | ✅ | Bali, Engle & Murray (2016) |
| 2 | Transformer Shapiro-Wilk 形式检验 | ✅ | Shapiro & Wilk (1965) |
| 3 | Imputer `strategy='ffill_ts'` | ✅ | Little & Rubin (2002) |
| 4 | 消融重跑 | ✅ | B3 IC=-0.0067, winsorizer+scaler 显著 |
| 5 | 全量回归 | ✅ | 168/168 |
| 6 | A/B 对比 | ✅ | p(HAC)=0.80 |
| 7 | Hard routing + StatisticalClassifier (VR) | ✅ | Lo & MacKinlay (1988) |
| 8 | AR 后验检验 (监控) | ✅ | Anderson & Rubin (1949) |
| 9 | 审计文档 v2.0 | ✅ | 原则评分 68%→88% |

### 核心变更

1. **所有 `method='auto'` → 固定方法**: Winsorizer `percentile(1,99)`, Imputer `ffill_ts`, Transformer `identity` (Shapiro-Wilk p≥0.05)
2. **SOFT routing → Hard routing**: 因子分类基于 VR test (形式统计检验) 而非指纹 softmax 权重
3. **每步有学术引文**: 15 篇核心文献 (1964-2016)

### 学术依据 (15 篇)

| 文献 | 用途 |
|------|------|
| Box & Cox (1964) | 变换似然比检验 |
| Shapiro & Wilk (1965) | 正态性形式检验 |
| Lo & MacKinlay (1988) | Variance Ratio 可预测性 |
| KPSS (1992) | 平稳性检验 |
| Fama & French (1993, 2015) | 多因子模型残差中性化 |
| Jegadeesh & Titman (1993) | 动量因子基准 |
| Little & Rubin (2002) | 面板缺失插补 ffill |
| Huber & Ronchetti (2009) | 稳健统计缩尾 |
| Van Buuren (2011) | MICE 多重插补 |
| Bali, Engle & Murray (2016) | 1%/99% 缩尾行业标准 |
| Barroso & Santa-Clara (2015) | 动量波动率时变 |
| Novy-Marx & Velikov (2016) | 异常因子分类学 |
| Frisch & Waugh (1933) / Lovell (1963) | FWL 定理 — 中性化顺序等价 |
| Anderson & Rubin (1949) | 中性化后验检验 |

### 回滚方案

恢复 `method='auto'` 和 SOFT routing 的 git revert。审计文档指出剩余 12% 迁就可进一步消除 (Box-Cox LRT / KPSS)，但当前 trade-off 合理。

---

## ADR-028: Layer 3 溢价健康诊断 (FactorHealthDiagnoser, v3.3.0, 2026-07-15)

### 背景

Layer 2 的 StatisticalClassifier 解决了"因子是什么类型"的问题（static/dynamic/mixed），但无法回答"因子是否还在定价"。LGMM 论文 (LGMM-8.0) 的方法论发现：因子溢价过程 λ̂(t) 存在结构性断点（ES-type failure）和指数衰减（TD-type failure），这些失效模式在横截面健康度指标（IC/IR/拥挤度）中可能被掩盖。

### 决策

**新增 Layer 3 FactorHealthDiagnoser 模块，实现 Fama-MacBeth + Epanechnikov 核估计 λ̂(t) → Chow F-test 断点检测 → 指数衰减检测 → 多状态综合标签。**

与 Layer 5 的 FactorHealthMonitor（五维横截面健康度）**互补不合并**。

### 模块结构

| 模块 | 文件 | 行数 | 测试 |
|------|------|------|------|
| `PremiumEstimator` | `modules/factor_health/__init__.py` | ~70 | 3 |
| `BreakpointDetector` | `modules/factor_health/__init__.py` | ~70 | 2 |
| `FactorHealthDiagnoser` | `modules/factor_health/__init__.py` | ~170 | 4 |
| 单元测试 | `tests/unit/test_layer3_factor_health.py` | ~200 | 9 |
| 真实数据验证 | `scripts/verify_layer3_real.py` | ~80 | A股 3 因子 |

### 核心算法

1. **PremiumEstimator**: 每期横截面回归 `r_{i,t} = α_t + β_t × factor_{i,t-1} + ε_{i,t}` → Epanechnikov 核平滑 β_t → λ̂(t)
2. **BreakpointDetector**: 网格搜索 Chow F-test 在 raw β_t 上（非 kernel-smoothed，避免 F 统计量膨胀），单断点检测
3. **指数衰减检测**: 对数线性拟合 `log|λ̂(t)|`，估计半衰期，阈值 60 个月
4. **多状态综合**: `return_type × premium_health → pricing/recalibrate/monitor/review/suspect`

### 与 FactorHealthMonitor 的兼容性分析

| 维度 | FactorHealthMonitor (Layer 5) | FactorHealthDiagnoser (Layer 3) |
|------|------------------------------|-------------------------------|
| 分析视角 | 横截面快照 | 时间序列过程 |
| 核心问题 | "因子现在健康吗？" | "溢价什么时候断的？还在定价吗？" |
| 输入数据 | factor + returns + market_cap + volume | factor + forward_returns + return_type |
| 方法论 | IC/IR/HHI/换手率 等启发式阈值 | Fama-MacBeth + Chow F-test + Epanechnikov 核 |
| 输出 | FactorHealthReport (0-100分) | dict (分类标签 + 溢价统计) |
| 学术严谨性 | 中等 | 高 |

### 合并决策：**不合并，保持独立互补**

理由：
1. 输入数据要求不同（HealthMonitor 需要 market_cap，HealthDiagnoser 需要 forward_returns）
2. 输出格式不同（dataclass vs dict），合并破坏类型安全
3. 学术基础不同（启发式 vs 形式计量），合并模糊方法论边界
4. 使用场景不同（实时监控 vs 定期深度诊断），合并引入不必要耦合
5. 两个模块正交：一个因子可同时"健康"（不拥挤）但"不定价"（ES 断点），反之亦然

**建议集成方式**: 顺序使用 — HealthMonitor 快速筛选 → 对 flagged 因子用 HealthDiagnoser 深度诊断。两者输出可并行展示。

### 真实数据验证 (A股 3 因子)

| 因子 | premium_health | combined label | 断点位置 | pre_mean | post_mean |
|------|---------------|----------------|---------|----------|-----------|
| momentum_1m | stable | pricing | 无 | — | — |
| volatility_1m | ES | review | t=44 | -0.0038 | 0.0120 |
| turnover | ES | review | t=133 | -0.00002 | 0.00008 |

### 关键设计决策

1. **断点检测用 raw β_t 不用 kernel-smoothed λ̂_t**: kernel 平滑会人为降低方差，导致 F 统计量膨胀（假阳性）
2. **无 Bonferroni 校正**: 对 raw β_t 过于保守，单断点网格搜索使用标准 F 临界值
3. **bandwidth=24**: ≈2 年月度数据，Epanechnikov 核半宽
4. **half_life_threshold=60**: 5 年半衰期以下视为衰减（TD），以上视为正常波动
5. **LGMM 方法论启示**: 原始因子收益 ≈ 白噪声与溢价 λ̂(t) 存在断点不矛盾 — 噪声在收益层面，信号在溢价层面（层次化命题）

### 学术依据

- Fama, E. F., & MacBeth, J. D. (1973). Risk, return, and equilibrium: Empirical tests. *JPE*, 81(3), 607-636.
- Epanechnikov, V. A. (1969). Non-parametric estimation of a multivariate probability density. *Theory of Probability & Its Applications*, 14(1), 153-158.
- Chow, G. C. (1960). Tests of equality between sets of coefficients in two linear regressions. *Econometrica*, 28(3), 591-605.
- Bai, J., & Perron, P. (1998). Estimating and testing linear models with multiple structural changes. *Econometrica*, 66(1), 47-78.

### 回滚方案

`modules/factor_health/` 为独立模块，删除目录 + 移除 test 文件即可回滚。不依赖其他模块，不侵入 Pipeline 主循环。

---

## ADR-029: 标准化统一为逐日横截面 Z-Score (因果性修复)

**日期**: 2026-10-21
**状态**: 已实施
**优先级**: P0
**关联缺陷**: DEFECT-PL-03
**关联测试**: `tests/integration/test_pipeline_truncation_invariance.py`

### 背景

为判定"处理结果是否依赖未来数据"，新增管线级**截断不变式测试**：对任意截断点 t，用 `[0, t]` 数据跑出的 `[0, t]` 期输出，必须等于用全样本 `[0, T]` 跑完后截取 `[0, t]` 期的输出。

该测试暴露 `factor_adaptive_winsor` 标准化步骤违反不变式。根因有两层：

1. **分支判定依赖 method 字面量**。`ProcessingAdapter._cross_sectional_zscore` 仅在 `method == 'z_score'` 时为 True。`StaticFactorPipeline` 传的是 `method='auto'`，因此落入 per-column 分支：`fit()` 在**全样本**上对每一列拟合 `(mean, std)`，`transform()` 套用该固定参数。于是前 t 期的标准化结果依赖 t 之后的样本。
2. **`'auto'` 的方法选择本身依赖全样本**。`AdaptiveStandardizer._vote_on_method` 依据 `outlier_ratio / is_heavy_tailed / is_skewed / cv` 投票选出 `z_score | robust | quantile`。这些特征全部由输入数据计算，因此：(a) 构成第二重前视源；(b) 同一因子在不同时间窗口可能被选到不同方法，输出不可复现。

此外，实现与管线自身的文档契约不一致：`StaticFactorPipeline` 与 `MixedFactorPipeline` 的类文档均声明终步为"线性Z-Score"，但 `MixedFactorPipeline` 实际传 `method='z_score'`（命中逐日横截面分支），`StaticFactorPipeline` 传 `'auto'`（数据自适应选型）。二者语义不统一。

### 实测证据

截断不变式违反度量（`T=100, N=30, t=60, atol=1e-12`，Python 3.12）

| 对象 | 修复前 | 修复后 |
|------|--------|--------|
| `standardize(method='auto')` 单步 | 1800/1800 格差异, `max_abs_diff=6.18e-01` | **0** |
| `StaticFactorPipeline` 端到端 | `max_abs_diff=4.03e-01` | **1.33e-02** |
| `standardize(method='z_score')` 单步 | 0（对照组，本已因果） | 0 |

Static 残留的 1.33e-02 由去极值（DEFECT-PL-01）与变换（DEFECT-PL-02）构成，不在本 ADR 范围。

**后续 (2026-10-22)**: DEFECT-PL-01 已由 ADR-037 修复，Static 残留降至 **4.72e-05**，仅由 PL-02（变换）构成。本 ADR 的历史测量值保留不改。

### 决策

**`ProcessingAdapter` 在 `process_type == 'standardization'` 且 `method == 'auto'` 时，于构造期将 method 解析为 `'z_score'`，从而命中逐日横截面分支。**

```python
if process_type == 'standardization' and method == 'auto':
    method = 'z_score'
```

逐日横截面分支不存储全样本参数：`fit()` 置 `_processor=None`、`_column_processors={}`；`transform()` 对每一期独立计算 `(x - mean_t) / std_t`。因此 fit 对标准化而言成为 no-op，**不存在可泄漏的参数**——这是本方案在结构上优于"把参数算对"的原因。

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 维持 `'auto'` 原行为 | 零改动 | 保留前视；方法选择不可复现 | ❌ |
| B: 扩展窗口 per-column 标准化 | 保留 per-stock 时序语义 | 需时间变化参数，改动大；仍破坏横截面可比性；存量输出同样作废 | ❌ |
| C: standardization 统一解析为逐日横截面 z-score | 消除前视；与 Mixed 一致；与"线性Z-Score"契约一致；fit 无参数可泄漏 | Static 输出数值变更（存量结果作废） | ✅ |
| D: 全部标准化方法（robust/min_max/quantile）横截面化 | 覆盖更全 | 三类方法无生产路径使用；逐行 robust 语义需另行定义，超出本次范围 | ❌（留待需要时） |

### 后果

**正面**
- 消除标准化步骤的前视偏差：截断不变式由 1800/1800 格违反降为 0
- Static 端到端违反幅度降 30 倍（4.03e-01 → 1.33e-02），确认该缺陷是 Static 的主因
- 标准化行为变为确定性：不再依赖数据自适应投票，同一输入在任何窗口得到同一方法
- Static 与 Mixed 语义统一

**负面 / 破坏性**
- **`StaticFactorPipeline` 输出数值变更**。此前用该管线产出的因子值、IC、Sharpe 等结论需重算
- 两处既有测试的契约随之变更（见下节）

**风险**
- 单值截面（某期仅 1 个非 NaN 观测）会使 `std(ddof=1)` 为 NaN，该期输出变为 NaN。当前管线在标准化前已完成插补，正常路径不触发；将来若处理稀疏面板需另行定义语义
- 显式指定 `robust / min_max / quantile` 的调用仍走非因果的 per-column 分支

### 测试契约变更

两处既有断言原为 `result.mean(axis=0) ≈ 0`（**列**均值），已改为逐日横截面断言（**行**均值 ≈ 0、行标准差 ≈ 1）：

- `tests/test_adapters/test_module_enabled.py::test_module_enabled_none_default_behavior`
- `tests/test_pipelines_v2.py::TestStaticFactorPipeline::test_static_pipeline_processing`

依据：**列均值 == 0 是全样本 per-column 标准化的定义特征**——它正是"除以全样本均值"构造出来的。任何因果变换（逐日横截面或扩展窗口）在数学上都无法满足该等式。因此原断言并未检验"输出已标准化"，**其成立本身即前视的症状**。

### 影响面

生产代码中 `process_type='standardization', method='auto'` 仅 2 处，均已受益：

| 位置 | 用途 | 变更 |
|------|------|------|
| `pipelines_v2.py:904` | `StaticFactorPipeline` 终步 | 修复目标 |
| `demo.py:72` | demo 脚本 | 同步受益 |

其余路径原本已是 `'z_score'`，不受影响：`pipeline.py:190`、`pipelines_v2.py:1002`（Dynamic）、`pipelines_v2.py:1119`（Mixed）。

### 回归验证

| 范围 | 结果 |
|------|------|
| adapters / pipelines_v2 / pipelines_v2 子目录 / p1_fixes / multi_dim / integration | 123 passed, 2 skipped, 6 xfailed, 0 failed |
| unit 全量 / demo_notebook / integration 冒烟 | 262 passed, 2 skipped, 0 failed |

全量套件（800+）未完成长跑：`tests/test_backtest/test_p3_phase4_integration.py` 的 optimizer 模拟为主要耗时来源，需单独安排。

### 不覆盖范围

- `method='robust' / 'min_max' / 'quantile'` 仍走 per-column 全样本拟合分支，非因果。三条生产管线均未使用，已在截断不变式测试文件中登记为"已知未登记"
- 去极值（DEFECT-PL-01）、变换（DEFECT-PL-02）、解耦器 AR 样本内预测（DEFECT-PL-05）不在本次处理

### 学术依据

- Fama, E. F., & MacBeth, J. D. (1973). Risk, return, and equilibrium: Empirical tests. *Journal of Political Economy*, 81(3), 607-636. — 逐期横截面估计范式：因子暴露在每期截面上标准化后参与排序/回归，而非在个股时序上标准化
- Grinold, R. C., & Kahn, R. N. (2000). *Active Portfolio Management* (2nd ed.). McGraw-Hill. — 因子暴露的截面 z-score 是行业惯例（惯例引用，不指认具体章节）
- 判定基准不依赖文献：截断不变式由 `tests/integration/test_pipeline_truncation_invariance.py` 直接可证伪

### 回滚方案

回滚为删除 `adapters.py` 中一处条件解析。但回滚会重新引入前视偏差，并使
`test_pipeline_truncation_invariance.py::TestIsolatedStepInvariance::test_standardize_auto_is_causal` 失败。
若确需 per-column 语义，应改用扩展窗口实现（方案 B），而非回滚到全样本拟合。

---

## 补记说明: ADR-030 ~ ADR-036 (2026-10-21)

以下 7 条 ADR 为**补记**：决策实际发生于 v3.0.0 / v3.1.0 实施期 (2026-07)，但当时只写进了规划文档，从未写入本文档（见文首「ADR 编号登记规则与勘误」）。

补记素材来源与证据标准：
- **决策表述**取自 `docs/EXECUTION_V3.1.0.md` 各任务「验收标准」与 `docs/EXECUTION_ABLATION_V3.0.0.md` §12 的既有大纲
- **代码证据**为本次逐条核实：类定义位置、配置字段名与默认值，均已在当前代码中确认存在
- 规划文档未记录的**备选方案对比**不予补造；标注为「规划文档未记录」
- 学术引用只到**作者-年份**，取自规划文档；未逐篇核验卷期页码

编号分配（不复用已占用的 026~029）：ADR-030 E1 · ADR-031 E2 · ADR-032 E3 · ADR-033 E4 · ADR-034 E5 · ADR-035 E6 · ADR-036 消融对照机制。

---

## ADR-030: E1 隐藏效应诊断 — Mixin 嵌入而非独立模块

**日期**: v3.1.0 实施期 (2026-07)
**补记**: 2026-10-21
**状态**: 已实施
**优先级**: P1
**原规划编号**: ADR-026 (已作废)

### 背景

因子经解耦后是否仍残留不可观测的混淆效应，此前无任何诊断手段。需要在不改动解耦器既有 `fit / transform / get_summary` 接口的前提下，提供事后诊断能力。

### 决策

**以 Mixin 嵌入 `CompositeDecoupler` / `ARDecoupler`，而非新建独立诊断模块。**

附带的四条子决策：
1. **两阶段分离**：`fit` 阶段只做模型估计，post-hoc 诊断在 fit 完成后执行；未 fit 时诊断返回降级提示而非报错
2. 诊断覆盖 4 类：增量内生性 / 信息损失 / 平稳性 vs 内生性 / 方法敏感性
3. `enable_hidden_effect_diagnosis=False`（默认）时管线行为与 v3.0.0 完全一致
4. 平稳性诊断须保留「ADF 通过 ≠ 内生性消除」的警告，防止把单位根检验结果误当内生性结论

### 代码证据

| 组件 | 位置 |
|------|------|
| `HiddenEffectDiagnosticMixin` | `modules/factor_decoupler/diagnostics/hidden_effect.py:25` |
| `diagnose_hidden_effects` | 同文件 `:37` |
| `CompositeDecoupler(_HiddenEffectDiagnosticMixin)` | `modules/factor_decoupler/core/dual_neutralizer.py:337` |
| `ARDecoupler(_HiddenEffectDiagnosticMixin)` | `modules/factor_decoupler/core/ar_model.py:211` |
| 管线委托方法 | `pipelines_v2.py:1650` |
| 配置开关 (默认 False) | `pipelines_v2.py:740` |

### 备选方案

规划文档只记录了结论（"Mixin 嵌入而非独立模块"）与验证项（`test_mixin_not_invasive`：Mixin 不修改 fit/transform 签名），**未记录备选方案对比表**，本 ADR 不补造。

### 后果

- **正面**：解耦器接口零改动，诊断能力随实例天然可用，无需同步两套状态
- **负面（未处置，Mixin 方案的固有代价）**：诊断逻辑与被诊断对象强耦合，无法脱离解耦器复用于其它对象——这是换取"接口零改动"的取舍，属设计选择而非缺陷
- **风险（已处置，见下节）**：Mixin 曾依赖实例私有状态（`_results` 等），解耦器内部结构变更会导致诊断静默失效

### 耦合风险的处置 (2026-10-21)

补记时核查代码，发现该风险的具体形态比原表述更严重：

1. **误报**：旧 `_estimate_ar_phi` 直接探测私有 `self._results` / `self._ar_decoupler._results`。内部结构一变即返回 `None`，诊断给出 `'AR model not fitted'` —— 而模型**其实已 fit**
2. **假阴性（真正危险处）**：走该分支时同时返回 `is_incremental_endogenous=False`，等于谎报"无增量内生性"。诊断工具谎报比崩溃有害
3. **布局陷阱**：`ARModelResult.coefficients` 的 dataclass 注释写 `[phi_1, ..., phi_p, intercept]`（截距末位），而 `_fit_ar` 实际把常数项插在**列首**，真实布局为 `[intercept, phi_1, ...]`。照注释改代码会静默取到错误 φ —— 不报错，只是数值错

处置措施：

| 措施 | 实现 |
|------|------|
| φ 提取收拢为显式契约 | 宿主实现 `_get_ar_phi_for_diagnosis()`；Mixin 不再探测任何私有属性 |
| 布局假设单点化 | `AR_COEF_INTERCEPT_INDEX` / `AR_COEF_PHI1_INDEX` 具名常量，仅在 `ARDecoupler` 钩子内使用 |
| 注释纠偏 | `ARModelResult.coefficients` 注释改为真实布局 `[intercept, phi_1, ..., phi_p]` |
| CompositeDecoupler 纯委托 | 钩子只转发给内部 `ARDecoupler`，本类不假设内层结构 |
| 破坏即报错 | 已 fit 却取不到 φ → 抛 `DiagnosticContractError`，不再静默降级 |
| 语义钉子 | 新增 `TestDiagnosticContract`（8 项）：布局钉子（已知 AR(1) 反查 φ≈0.7、截距>5）、钩子存在性、Composite 纯委托一致性、钩子缺失/返回 None 均报错、未 fit 仍走软提示 |

**未 fit 的软提示行为保持不变**（两阶段分离，E1-T21 仍通过），契约收紧只作用于「已 fit 但取不到 φ」这一原本会误报的情形。

回归：`tests/test_factor_decoupler/` + `test_pipelines_v2` + `integration/` 共 80 passed / 6 xfailed / 0 failed。

---

## ADR-031: E2 P-hacking 防御 — L1-L2 独立模块 + L3 扩展

**日期**: v3.1.0 实施期 (2026-07)
**补记**: 2026-10-21
**状态**: 已实施
**优先级**: P1
**原规划编号**: ADR-027 (已作废)

### 背景

三层 P-hacking 防御中只有 L3（BH-FDR 事后校正，v3.0.0 T4 已实施）存在，L1（事前设计约束）与 L2（事中记录）完全缺失。缺少这两层时，"试了多少种规格"这一信息在生产过程中就丢失了，事后无法重建。

### 决策

**新建 `backtest/specification_logger/` 三个独立类 + 扩展 `multiple_testing.py` 增加 BY-FDR。**

1. `SpecificationLogger` — append-only JSONL 事中记录，`log_run` 返回 8 字符 SHA1 commit hash
2. `PreRegistration` — 事前承诺 vs 实际配置的偏差检测（`is_compliant` / `deviations`）
3. `SpecificationCurve` — 规格曲线：按符号一致性给出 `consistency` 判定
4. `apply_by_fdr` — Benjamini-Yekutieli（依赖稳健），与既有 `apply_bh_fdr` **共存**，返回类型严格一致 `Tuple[List[float], List[bool]]`
5. L1 test-set 一次性原则：`enforce_test_set_once` 阻止对同一 test set 重复评估
6. 全部 opt-in，`enable_specification_logger=False` 为默认

### 代码证据

| 组件 | 位置 |
|------|------|
| `SpecificationLogger` | `backtest/specification_logger/spec_log.py:25` |
| `SpecificationCurve` | `backtest/specification_logger/spec_curve.py:16` |
| `PreRegistration` | `backtest/specification_logger/pre_registration.py:18` |
| `apply_by_fdr` | `backtest/multiple_testing.py:210` |
| 配置字段 | `pipelines_v2.py:744-747`（`enable_specification_logger` / `spec_log_dir` / `enforce_test_set_once`） |

### 后果

- **正面**：搜索路径可审计——规格曲线的符号一致性直接暴露"换规格改结论"的幅度
- **负面**：新增运行时产物 `logs/specifications/`（append-only，需纳入版本/清理策略）
- **风险**：BY-FDR 比 BH 更保守，功效下降；记录本身依赖调用方主动 `log_run`，漏记则防御失效

### 关联

- ADR-002a（BH-FDR 用于 KS 迁移校正）——BY-FDR 与其并存而非替换
- ADR-026（审计流程）——L2 记录是事后审计的输入

---

## ADR-032: E3 内生性诊断 S1-S4 — 独立新模块 + 四阶段

**日期**: v3.1.0 实施期 (2026-07)
**补记**: 2026-10-21
**状态**: 已实施
**优先级**: P2
**原规划编号**: ADR-028 (已作废)

### 背景

内生性此前只在单一环节被局部检验，无法回答"威胁是在插补、中性化还是解耦环节引入/消除的"。逐环节定位需要分阶段诊断，且不能侵入主处理链路。

### 决策

**新建独立模块 `modules/endogeneity_check/`，实现四阶段诊断 + 四方法 + 威胁度融合。**

1. 四阶段：S1 插补前（缺失机制）/ S2 插补后 / S3 中性化后 / S4 解耦后；**默认 S1+S2+S4，S3 按需开启**（高 stakes 场景）
2. 四方法：Oster δ / AET (Altonji-Elder-Taber) / IFE / Lewbel 内部 IV；各自独立可用、可组合
3. `EndogeneityThreatAssessor` 加权融合四方法，`get_final_threat_assessment()` 输出 `final_threat_tau ∈ [0,1]`
4. S1→S2 为**上下文衔接**（逻辑上调推荐策略），不是数值差分；S3/S4 对 S2 才做数值差分
5. 术语纪律（v1.3）：`Oster δ` 而非 ITCV；`R_max = min(1, 1.3×R̃)` 而非 2.75；IFE 记号 `lambda_i' · F_t`；Lewbel 工具变量 `(Z - Z̄) × ê²`
6. 事后诊断，不侵入 `fit / transform`；`enable_endogeneity_check=False` 为默认

### 代码证据

| 组件 | 位置 |
|------|------|
| `EndogeneityDiagnosticOrchestrator` | `modules/endogeneity_check/core/diagnostic_orchestrator.py:27` |
| 各检查器 | 同目录 `missingness_checker.py` / `oster_delta.py` / `aet_checker.py` / `ife_checker.py` / `lewbel_iv.py` / `threat_assessor.py` |
| 管线方法 `check_endogeneity` | `pipelines_v2.py:1745` 起 |
| 配置字段 | `pipelines_v2.py:752-761`，含 `oster_r_max_multiplier = 1.3`（v1.3 修正的代码落点） |

### 后果

- **正面**：威胁可归因到具体处理环节，而非只给出一个整体"有无内生性"的模糊结论
- **负面**：成为 E5 的硬依赖——E3 不运行时 E5 必须报错或显式降级
- **风险**：Oster δ 依赖 `R_max` 选取，1.3 倍是文献建议而非本项目数据校准值；无对照组时需降级处理而非给伪精确结论

### 关联

- ADR-034（E5）硬依赖本条的 `final_threat_tau`
- ADR-025（CUSUM）——同样是事后诊断、不侵入主链路的模式

---

## ADR-033: E4 格兰杰检验 — Toda-Yamamoto 默认 + Bootstrap 可选

**日期**: v3.1.0 实施期 (2026-07)
**补记**: 2026-10-21
**状态**: 已实施
**优先级**: P2
**原规划编号**: ADR-029 (已作废)

### 背景

因子与收益的时序先后关系需要检验，但标准格兰杰检验在非平稳序列上会伪回归。同时，格兰杰因果极易被误读为结构因果。

### 决策

**新建 `backtest/granger_attribution/`，默认采用 Toda-Yamamoto 程序。**

1. 流程：ADF 定阶 d → VAR(p+d) 估计（p 由 AIC 选）→ Wald 检验，对非平稳序列保持检验有效性
2. `granger_use_toda_yamamoto=True` 为默认；`granger_use_bootstrap=False` 为默认（block bootstrap 保持时序结构，成本约 30s）
3. 同期因果一律标 `unidentified` —— 诚实承认不可识别，不强行给结论
4. 输出固定携带警告文案「格兰杰因果 ≠ 结构因果 — 仅为伪回归初筛」
5. T < 20 时降级；不侵入 `fit / transform`；默认关闭

### 代码证据

| 组件 | 位置 |
|------|------|
| `TodaYamamotoGrangerTester` | `backtest/granger_attribution/toda_yamamoto.py:21` |
| 管线方法 `check_granger_causality` | `pipelines_v2.py:1843` 起 |
| 配置字段 | `pipelines_v2.py:765-768`（`granger_max_lag=12` / `granger_use_toda_yamamoto=True` / `granger_use_bootstrap=False`） |

### 后果

- **正面**：在非平稳序列上仍给出可信的拒绝/不拒绝结论；同期因果的不可识别性被显式标注而非掩盖
- **负面**：VAR(p+d) 增广降低自由度，短样本下功效有限（T<20 直接降级）
- **风险**：最大风险是**误读**——该检验极易被当作因果证据。警告文案是防线，但防线依赖读者

### 学术依据

Toda & Yamamoto (1995)。

---

## ADR-034: E5 三层决策正则化 — 硬依赖 E3 + opt-in 默认关闭

**日期**: v3.1.0 实施期 (2026-07)
**补记**: 2026-10-21
**状态**: 已实施
**优先级**: P3
**原规划编号**: ADR-030 (已作废)

### 背景

E3 只输出威胁度 `τ`，若不消费这个量，诊断就只是报告而不改变任何决策。需要在预处理、检验、组合三层把 `τ` 转化为实际的处理强度。

### 决策

**`EndogeneityRegularizer` 消费 E3 的 `final_threat_tau`，在 L1/L2/L3 三层施加不同作用；硬依赖 E3，全部 opt-in。**

1. **L1 预处理层**：`τ < 0.3` 跳过 Stage 2；`0.3 ≤ τ < 0.7` 标准三重中性化；`τ ≥ 0.7` 追加 β' 检查
2. **L2 检验层**：显著性阈值按威胁度收缩，`α_i = α_base × (1 − γ·τ_i)`
3. **L3 组合层**：权重按威胁度惩罚，`w_final = w_raw × (1 − ρ·τ)`
4. **硬依赖 E3**：E3 未运行时必须报错或显式降级，不允许静默按 τ=0 处理
5. `lambda_endogeneity = 0.0` 时优化器目标函数与 v2.6.0 完全一致（零回归）
6. `enable_endogeneity_regularization=False` 为默认

### 代码证据

| 组件 | 位置 |
|------|------|
| `EndogeneityRegularizer` | `modules/endogeneity_regularizer/regularizer.py:18` |
| 管线方法 | `pipelines_v2.py:1995` 起 |
| 配置字段 | `pipelines_v2.py:780-785` |

**记录一处 spec 与代码的命名偏离**（代码注释已自承）：规划文档中的 `endogeneity_reg_gamma` / `endogeneity_reg_strength`，实际落地为 `regularizer_gamma` / `regularizer_rho`。参数语义未变，仅命名不同。

### 后果

- **正面**：威胁度从"报告指标"变成"实际改变处理强度"的闭环；三层可独立启用、可组合
- **负面**：与 E3 单向强耦合，E3 不可用时 E5 整体不可用
- **风险**：0.3 / 0.7 两个阈值与 `ρ=0.3`、`γ=0.5` 为经验设定，规划文档未记录校准过程；本 ADR 如实标注这一点，不声称其最优

### 关联

- ADR-032（E3）为硬依赖项
- ADR-035（E6）与本条互补：E6 在估计层吸收，本条在决策层惩罚残留

---

## ADR-035: E6 估计层方法 — opt-in + 与决策层正则化互补

**日期**: v3.1.0 实施期 (2026-07)
**补记**: 2026-10-21
**状态**: 已实施
**优先级**: P3
**原规划编号**: ADR-031 (已作废)

### 背景

除"诊断 + 惩罚"路线外，还有"换估计量"路线：用对弱工具/持续回归更稳健的估计方法吸收部分内生性。两条路线的关系需要明确界定，否则会互相冒充。

### 决策

**四种估计器 + 一个方法选择器，全部 opt-in；定位为估计层缓解，与 E5 决策层正则化互补。**

1. 四估计器：`ProfileGMMEstimator` / `IVXEstimator` / `RegularizedDOLSEstimator` / `PFGMMEstimator`，统一接口 `fit / get_diagnostics / get_residual_threat`
2. `EstimationMethodSelector` 按场景推荐，优先级：三层正则化 > Profile GMM > IVX > DOLS > PFGMM
3. **与 E5 串联**：E6 先估计，E5 再对残留威胁正则化
4. 认识论立场：估计层**不声称消除内生性**，只声称在估计阶段吸收部分；残留威胁仍需 E5 处理
5. 术语纪律：Profile GMM 为正式术语（Hong-Su-Jiang 2022，NNR+GMM 为别名）；IVX 为**指数衰减滤波**而非分数差分；PFGMM 处理 error-covariate 内生而非弱 IV；因子增强 IVX 暂不使用
6. PFGMM 输出 A 股适用性低警告；全部默认关闭

### 代码证据

| 组件 | 位置 |
|------|------|
| `ProfileGMMEstimator` | `modules/endogeneity_estimators/core/profile_gmm.py:32` |
| `IVXEstimator` | 同目录 `ivx.py:38` |
| `RegularizedDOLSEstimator` | 同目录 `regularized_dols.py:31` |
| `PFGMMEstimator` | 同目录 `pfgmm.py:30` |
| `EstimationMethodSelector` | 同目录 `method_selector.py:26` |
| 配置字段 | `pipelines_v2.py:789-797`（`enable_endogeneity_estimators=False` / `estimator_method='auto'` / 四个子开关） |

### 后果

- **正面**：给出"不改变决策规则、只改估计量"的第二条路径；统一接口使方法间可横向对比
- **负面**：四种估计器维护成本高，其中 PFGMM 在 A 股场景适用性低（仅理论保留）
- **风险**：多方法并存容易诱发"挑一个显著的"式方法搜索——正是 ADR-031 要防的行为。方法选择器必须留下选择记录

### 学术依据

Hong, Su & Jiang (2022)（Profile GMM）；Kostakis et al. (2015)（IVX）；Stock & Watson (1993)（DOLS）；Ghosh & Thoresen (2019)（PFGMM）。

---

## ADR-036: 消融对照机制 — 四层架构 + Baseline 阶梯

**日期**: v3.0.0 实施期 (2026-07)
**补记**: 2026-10-21
**状态**: 已实施
**优先级**: P1
**原规划编号**: ADR-026 (已作废，与 Audit-Driven 修复的 ADR-026 冲突)

### 背景

管线此前没有消融机制，因此"某个前置处理步骤确实有用"这一论点缺乏实证支持——无法区分增益来自该步骤还是来自评估噪声。

### 决策

**`AblationRunner` 独立模块，实现四层消融 + Baseline 阶梯 + 显著性判定。**

1. **L1**：5 个模块的 enabled 开关（Adapter 层）
2. **L2**：5 种路由配置，**含随机路由控制组**（用于排除混淆）
3. **L3**：4 组参数（CUSUM / EWMA / 五叉阈值 / winsorize）
4. **L4**：6 个自由度的 OAT（单维逐一关掉），**不做全因子 972 组合**（不可行）
5. **B0–B3** Baseline 阶梯
6. 显著性：Ledoit-Wolf (2008) HAC 标准误 + circular block bootstrap（B=1000）；多重比较复用 BH-FDR（ADR-002a）
7. `enabled` 开关放在 **Adapter 层**而非模块层，复用 `OrthogonalizerAdapter` 既有模式
8. 不侵入 `fit / transform`；诚实立场：**消融是双向的**——结果可能降级评定，也可能升级评定

### 代码证据

| 组件 | 位置 |
|------|------|
| `AblationRunner` | `backtest/ablation_runner.py:395`（全文件 1564 行） |
| `module_enabled` 透传 | `pipelines_v2.py` 配置字段 + `_create_pipeline` 透传 |
| 测试 | `tests/test_backtest/test_ablation_runner.py` |

### 后果

- **正面**：每个前置处理步骤的贡献可被单独测量并给出显著性；随机路由控制组能拆开"路由本身"与"路由内容"的效应
- **负面**：组合数受控于 OAT，因此**无法检测交互效应**——这是为可行性付出的代价，需在报告中显式声明
- **风险**：bootstrap 使单次运行成本上升；B0 的 dropna 语义已在规划文档中记录为在 IC 计算层处理（`factor_metrics.py` 跳过 NaN pair），而非管线层

### 学术依据

Ledoit & Wolf (2008)（HAC）；Benjamini & Hochberg (1995)（BH-FDR）。

---

## ADR-037: 去极值统一为逐日横截面 (因果性修复)

**日期**: 2026-10-22
**状态**: 已实施
**优先级**: P0
**关联缺陷**: DEFECT-PL-01
**关联测试**: `tests/unit/test_outlier_cross_sectional.py`、`tests/integration/test_pipeline_truncation_invariance.py`
**调研/设计**: [PL01_OUTLIER_LOOKAHEAD_RESEARCH.md](docs/analysis/PL01_OUTLIER_LOOKAHEAD_RESEARCH.md) / [PL01_OUTLIER_LOOKAHEAD_DESIGN.md](docs/analysis/PL01_OUTLIER_LOOKAHEAD_DESIGN.md)

### 背景

管线级截断不变式测试（ADR-029 引入）暴露 `ProcessingAdapter(process_type='outlier')` 违反不变式：用 `[0,t]` 数据跑出的前 t 期缩尾结果，与全样本跑后截取的前 t 期结果不同。项目测试面板实测 187 格差异，`max_abs_diff=1.68e-01`。

根因有三层，且相互叠加：

1. **池化拟合**：`fit()` 用 `X.values.flatten()` 在**全 panel** 上拟合缩尾参数。前 t 期的缩尾边界因此依赖 t 之后的数据。
2. **选型前视**：`SmartOutlierDetector` 默认 `auto_select=True`，其方法选择依据全 panel 分布特征（偏度、尾部、离散度），会**覆盖显式传入的 `method`**。实测显式 `method='percentile'` 在探针面板上实际拟合为 `mad`（`threshold=2.7725`）；200/200 个变波动率面板在截断前后选到不同方法。
3. **配置未消费**：`StaticFactorPipeline` 名义传 `percentile(1,99)`，但未被执行；旧版 `PipelineV2ConfigUnified.to_pipeline_config()` 产生的 `threshold / lower_percentile / upper_percentile` 经 `pipeline.py` 传入 `ProcessingAdapter`，修复前在 `fit()` 实例化 detector 时因签名不匹配而 `TypeError`。修复后 outlier `fit()` 为 no-op，这些旧字段不再报错，但仍不被消费（见“不覆盖范围”）。

这同时是 **ADR-027 的实施缺口**：ADR-027 已决定“所有 `auto` → 固定方法”和“Winsorizer `percentile(1,99)`”，但 adapter 层从未落实。

该缺陷长期未被发现，是因为缩尾是**单调**变换：前视与截断输出的逐日 Spearman 中位数 = 1.000，最小值 = 0.9973。排序类指标几乎无感，只有值相等的截断不变式能暴露它。

### 决策

**`ProcessingAdapter(process_type='outlier')` 统一改为逐日横截面估计；`fit()` 不存参数，边界只在 `transform()` 用当日行重算。**

1. **D1 估计轴**：每个交易日独立计算缩尾边界，只使用该日横截面。行 = 日期、列 = 股票的因子面板，因此逐行（axis=1）即逐日截面。
2. **D2 方法解析**：`method='auto'` 在构造期解析为 `'percentile'`（默认 1/99）；显式方法按声明执行；detector 侧始终 `auto_select=False`，禁止数据自适应选型。
3. **D3 实现路径**：
   - `percentile` 走向量化快速路径：`X.quantile(q, axis=1)` + `X.clip(lower, upper, axis=0)`；
   - 其他方法（`mad/iqr/z_score/adaptive/sigmoid_soft/quantile`）逐行复用 `SmartOutlierDetector`，保留原有截断语义（smooth clip / sigmoid）；
   - 实测 2500×3000 面板：向量化 percentile 0.226s（验收复测；设计基准 0.212s）、逐行 MAD 2.888s、逐行 percentile 循环 2.56s。
4. **D4 `fit()` 为 no-op**：outlier 不存储任何拟合参数，结构上不存在可泄漏的参数面（与 ADR-029 的 `z_score` 分支同构）。
5. **D5 范围控制**：不提供时间序列 axis，不接 `OutlierConfig`，不扩展 `threshold` 语义，不做 rank-normal。
6. **D6 失败语义**：未知方法、非法分位、非数值输入 fail loud；行内有效观测 < 3 或零离散度时原样返回该行（与 detector 内部 `<3` 判据一致）；`percentile_upper < 1.0` 视为 0-1 小数约定误用并拒绝。边界说明：`(0.0, 1.0)` 仍会被解释为 0/1 百分位，调用方应显式使用 0-100 约定。
7. **D7 版本**：项目版本升至 **v3.3.3**；缓存 `CODE_VERSION` 由 `v2.2.0-cache` 升至 `v2.2.1-cache`。`CacheManager` 在读取时校验 `meta.code_version`，不一致即 MISS 并删除旧数据，确保算法变更后不会命中旧缓存（自愈重建）。

### 代码证据

| 组件 | 位置 |
|------|------|
| 常量（合法方法 / 参数白名单 / 最小观测） | `adapters.py` 顶部常量区 `_OUTLIER_METHODS` 等 |
| 构造期解析与校验 | `ProcessingAdapter.__init__` / `_validate_outlier_percentiles` |
| `fit()` no-op 分支 | `ProcessingAdapter.fit` |
| `transform()` 分支 | `ProcessingAdapter.transform` → `_transform_outlier_cross_sectional` |
| 向量化 percentile / 逐行复用 | `_transform_outlier_percentile` / `_transform_outlier_rowwise` |
| 统计字段 | `ProcessingAdapter.get_stats` (`outlier_scope='cross_sectional'`) |

### 实测证据

`T=100, N=30, t=60, atol=1e-12`，Python 3.12：

| 对象 | 修复前 | 修复后 |
|------|--------|--------|
| 隔离测试：outlier percentile | 187 格差异, `max_abs_diff=1.68e-01` | **0 格, 0** |
| StaticFactorPipeline 端到端 | 1.33e-02 | **4.72e-05**（残留仅 PL-02） |
| 方法解析（显式 percentile） | 实际拟合 `mad`, `threshold=2.7725` | 实际执行 `percentile(1,99)` |
| auto 选型稳定性（200 个变波动率面板） | 200/200 截断前后选型不同 | 构造期固定，无不一致 |
| 逐日 Spearman（前视 vs 截断） | 中位数 1.000 / 最小 0.9973 | —（仪器灵敏度对照） |

其他管线未变化，符合预期：Dynamic 不含 outlier 步骤（PL-05，8.05e-01/8 NaN）；Mixed 使用自身 `_compute_winsorize_params` 全样本缩尾（PL-06，2.91e-01）；顶层仍受残留缺陷与指纹路由影响（PL-07，1.84e+00）。

### 测试契约

| 测试 | 覆盖 |
|------|------|
| `tests/unit/test_outlier_cross_sectional.py`（15 函数 / 30 例） | `auto→percentile`；7 个显式方法保留；非法方法/分位；分位边界；percentile/MAD/全方法截断不变式；`fit` 不存参数；NaN/元数据；<3 观测/零离散；`enabled=False`；非 DataFrame；`get_stats` |
| `tests/integration/test_pipeline_truncation_invariance.py::test_outlier_percentile_is_causal` | 隔离步骤截断不变式：0 格 / 0 |
| `tests/integration/...::test_diagnostic_report` | outlier 行 0/0；Static 4.72e-05 |
| `tests/test_backtest/test_cache_manager.py::TestCodeVersionGeneration` | 缓存代际不一致 → MISS 且删除旧数据；`verify` 报告 `code_version mismatch` |
| `tests/test_fix3_version_unification.py::test_07_all_cache_code_versions_consistent` | 5 处缓存 `code_version` 默认值一致 |

### 不覆盖范围

- **PL-02 / PL-05 / PL-06 / PL-07**：保持 `xfail` 登记，不在本 ADR 范围。
- **旧版 `OutlierConfig` / `to_pipeline_config()` 字段接线**：`threshold`、`lower_percentile`、`upper_percentile` 当前不被消费；修复后不再抛 `TypeError`，但也不会生效。另立任务处理。
- **`SmartOutlierDetector` 默认值**：不修改模块默认 `auto_select=True`；adapter 显式传 `False`。
- **时序 expanding/rolling 轴**、**rank-normal**、**非 percentile 方法向量化**：后续评估。

### 备选方案

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A: 保留全 panel 池化，只固定方法 | 改动最小 | 前视仍在；只是把“选型前视”降为“参数前视” | 不选 |
| B: 按列（每只股票全历史）expanding 缩尾 | 保留时序语义 | 与因子面板的截面标准化/中性化口径不一致；需时间变化参数；存量输出同样作废 | 不选 |
| C: 逐日横截面 + 固定方法（percentile 快速路径，其他方法逐行复用） | 结构上无泄漏；与 ADR-027/029 及行业实践一致；保持各方法原截断语义；向量化 | 输出数值变更，旧缓存失效 | **选用** |
| D: 逐日 rank-normal | 对极端值稳健 | 改变输出分布与后续线性步骤的前提，超出缺陷修复范围 | 不选（留待需要时） |

### 后果

- **正面**：outlier 步骤在结构上不再有拟合参数可泄漏；`Static` 端到端由 1.33e-02 降至 4.72e-05；`auto` 行为可复现；与 ADR-027 的固定方法决策对齐；percentile 路径向量化后性能提升约一个数量级。
- **负面**：所有依赖旧缩尾数值的存量结果与缓存失效，需重建；缓存代际是粗粒度的，价格/前向收益缓存也会一并失效（一次性重查，换取实现简单与代际一致）；行内有效观测 <3 时该行跳过缩尾（小截面面板行为需知悉）；非 percentile 方法仍为逐行 Python 循环（当前无生产路径使用）。
- **风险**：若未来确需时序去极值（例如对单股票时间序列），必须显式新增估计轴并另立决策，不得通过修改默认轴实现——否则会重新引入前视或破坏截面口径。

### 学术与工业依据

- 因子面板的截面缩尾：Bali, Engle & Murray (2016), *Empirical Asset Pricing*。
- 样本依赖与前视偏差：Banz & Breen (1986)。
- 全样本预处理导致的信息泄漏：Kaufman, Rosset, Perlich & Stitelman (2012)；Kapoor & Narayanan (2023)。
- 因子定义/预处理选择对结果的影响：Arnott, Harvey & Markowitz (2019)。
- 稳健缩尾与 MAD 尺度：Hampel (1974)；Rousseeuw & Croux (1993)（`1.4826` 为 MAD 的正态一致性常数）。
- 分位数估计约定：Hyndman & Fan (1996)。
- 工业实践（截面缩尾为默认）：MSCI FaCS 方法论（2018，A）；DolphinDB Barra 因子处理教程（A）；Quant SE Q43498/A43511（A）；华泰金工因子处理系列（B，转载片段）；Portfolio Optimizer 文档（B）。
- 详细检索记录与证据等级见调研文档；未验证项在调研文档中显式标注，不作为本 ADR 的论据。

### 回滚方案

回退 `adapters.py` 的 outlier 分支与常量，恢复 `CODE_VERSION = "v2.2.0-cache"` 并删除/重建缓存；项目版本回退至 v3.3.2。回滚会使 PL-01 隔离测试重新失败，应同时恢复其 `xfail` 登记。

### 评审修订 (2026-10-22)

评审发现并修复一处会使本 ADR 失效的实现缺口：初版仅 bump `CODE_VERSION` 常量，但 `CacheManager.get/verify` 从未校验 `meta.code_version`，旧缓存仍会命中并返回修复前的数值。已补：

1. `CacheManager.get_with_meta`：读取时校验 `code_version`，不一致则记录 MISS 并删除旧数据/meta；
2. `CacheManager.verify`：不一致返回 `is_valid=False`，reason 为 `code_version mismatch`；
3. 3 项 `TestCodeVersionGeneration` 单测 + `test_07` 五处默认值一致性测试；
4. 修正本 ADR 的配置 `TypeError` 发生位置、Arnott 等作者名单、性能实测口径。

---

## ADR-038: 变换统一为逐日截面 rank→正态 (因果性修复)

**日期**: 2026-10-22
**状态**: 已实施
**优先级**: P0
**关联缺陷**: DEFECT-PL-02 (隔离) / DEFECT-PL-04 (Static 端到端残留)
**关联测试**: `tests/unit/test_transform_rank_cross_sectional.py`、`tests/unit/test_adaptive_transformer_identity.py`、`tests/integration/test_pipeline_truncation_invariance.py`
**调研/设计**: [PL02_TRANSFORM_LOOKAHEAD_RESEARCH.md](docs/analysis/PL02_TRANSFORM_LOOKAHEAD_RESEARCH.md) / [PL02_TRANSFORM_LOOKAHEAD_DESIGN.md](docs/analysis/PL02_TRANSFORM_LOOKAHEAD_DESIGN.md)

### 背景

管线级截断不变式测试（ADR-029 引入）在 PL-01 修复后仍有残留：`ProcessingAdapter(process_type='transformation')` 的前 t 期输出依赖 t 之后的数据。实测 `T=100, N=30, t=60`：隔离步骤 1800 格差异、`max_abs_diff=8.51e-04`；Static 端到端 4.72e-05（残留全由变换构成）。

根因四层叠加：

1. **池化拟合**：`fit()` 用 `X.values.flatten()` 在全 panel 上估计 Box-Cox/Yeo-Johnson 的 λ、log 的 offset、经验 CDF。
2. **选型前视**：`auto_optimize=True` 覆盖显式方法；`_select_optimal_transform` 依赖全样本 skew/kurt/Shapiro p 选择方法，且 Shapiro 子采样未设随机种子。
3. **Mixed 条件变换**：`MixedFactorPipeline.fit` 用全样本 `skew().median()` / `kurtosis().median()` 判断是否变换，属于基于同一数据的 pre-test 式切换。
4. **配置未接线**：`TransformationConfig.method` 默认 `auto`，但 v2 管线未消费该字段，`mixed_conditional_transform` 等三个字段独立控制行为。

变换是**保序**的（对逐元素方法），因此排序类指标（IC 的 Spearman 版本）对前视不敏感；只有值相等的截断不变式能暴露。

### 决策

**变换统一为逐日截面 rank → 目标分布；方法在构造期固定，`fit()` 不估计任何参数。**

1. **D1 估计轴**：每个交易日独立对当日有效值排名；数据布局 index=日期、columns=股票，故按行（axis=1）即逐日截面。
2. **D2 输出分布**：`normal` 用 Blom 正态分数 `Φ⁻¹((R−3/8)/(N+1/4))`；`uniform` 用归一化秩 `(2R−N−1)/N`。由 `target_distribution` 控制，默认 `normal`。
3. **D3 方法解析**：`auto` → `rank`；`quantile` → `rank`；`none` → `identity`；`box_cox` / `yeo_johnson` 映射到实现名。删除 `auto_optimize` 与整条选型链（`_analyze_features` / `_select_optimal_transform` / `_fit_*`）。
4. **D4 显式方法先验参数化**：`log` / `boxcox` / `yeojohnson` / `power` 保留，但 `fit` 不再估计——`boxcox` / `yeojohnson` 必须提供 `lam`，`power` 必须提供 `power_param`，`log` 使用 `offset`（默认 0）。缺失时构造期 `ValueError`。
5. **D5 N 下限**：`rank_transform_1d` 是纯算法入口，不做小样本保护；`ProcessingAdapter` 在截面有效观测 `N<10` 时回落逐日截面 z-score，`N<2` 时原样返回。该保护只依赖 N，不依赖分布统计量，属于确定性保护而非 pre-test 切换。
6. **D6 identity 短路**：`identity` 的 `fit` 为 no-op、`transform` 直接返回输入，避免落入 `X.values.flatten()` 与逐列调用。
7. **D7 配置接线**：`TransformationConfig` 增加 `target_distribution`、默认 `method='rank'`，并映射到 `PipelineV2Config.static_transformation_method / static_target_distribution / mixed_*`；删除 `mixed_conditional_transform` / `mixed_skew_threshold` / `mixed_kurt_threshold`。
8. **D8 Mixed 顺序**：切为 neutralize → transform（I-INT：先剥离暴露再 rank），`fit` 与 `transform` 使用同一口径。
9. **D9 版本与缓存**：项目版本 **v3.3.4**；缓存 `CODE_VERSION` **v2.2.2-cache**（变换输出数值改变，旧缓存读取时 MISS 并自愈删除）。

### 备选方案 (拒绝)

| 方案 | 拒绝理由 |
|------|---------|
| 固定方法 + 全样本参数 | 参数仍前视，只把“选型前视”降为“参数前视” |
| 扩展窗口 λ 调度 | regime 差异不显著（调研 §3.2），收益低于复杂度 |
| 逐日截面 λ 估计 | 日间波动大，只增加噪声 |
| 在线条件变换（按 skew/kurt 决定是否变换） | 无学术/社区实践支持；输出为 mixture；基于同一数据的 pre-test 估计量分布不可一致估计（Leeb & Pötscher 2006/2008） |

### 代码证据

| 组件 | 位置 |
|------|------|
| 无状态 rank 映射 / 别名常量 | `modules/factor_adaptive_winsor/core/transformers.py` 模块级 `rank_transform_1d` / `TRANSFORMATION_METHOD_ALIASES` |
| `AdaptiveTransformer` 构造期校验与无状态 `fit` | `transformers.py` 的 `__init__` / `fit` / `transform` |
| 截面 rank 与 N 下限 | `adapters.py` 的 `ProcessingAdapter._transform_rank_cross_sectional` |
| 配置字段与桥接 | `config_v2.py` 的 `TransformationConfig` / `to_pipeline_v2_config()` |
| 管线接线与 Mixed 顺序 | `pipelines_v2.py` 的 `StaticFactorPipeline` / `MixedFactorPipeline` / `_create_pipeline` |

### 实测证据

截断不变式（`T=100, N=30, t=60, atol=1e-12`，Python 3.12）：

| 层级 | 对象 | 修复前 | 修复后 |
|------|------|--------|--------|
| step | transform `auto`（隔离） | 1800 格, 8.51e-04 | **0 格, 0** |
| pipeline | Static 端到端 | 4.72e-05 | **0 格, 0** |
| pipeline | Mixed 端到端 | 2.91e-01 | 6.98e-01（**剩余仅 PL-06 全样本缩尾**） |
| pipeline | Dynamic 端到端 | 8.05e-01 / 8 NaN | 不变（PL-05，不含变换步骤） |
| top | FactorProcessingPipelineV2 | 1.84e+00 / 1650 格 | 1.84e+00 / 1650 格（PL-05/06 + 指纹路由） |

性能（`T=2500, N=3000, t(3), NaN 5%`，单机 Python 3.12）：

| 实现 | 耗时 | 对照 |
|------|------|------|
| `rankdata` 逐行（纯 helper） | 1.040 s | 设计基准 1.071 s（−2.9%） |
| `ProcessingAdapter.transform`（生产路径） | 1.075 s | 相对 helper +3.4% |
| `normal` 中位列 std | 0.9991712 | 设计基准 0.9989543 |
| `uniform` 中位列 std | 0.5773502 | 理论 `1/√3 = 0.5773503` |

`ProcessingAdapter` 与纯 helper 输出 `max |diff| = 0`（逐行 rankdata 为唯一算法路径）。

### 测试契约

| 测试 | 覆盖 |
|------|------|
| `tests/unit/test_transform_rank_cross_sectional.py`（28 函数 / 32 例） | 别名解析；normal/uniform 对拍；有限样本矩；ties；NaN；截断不变式；无状态；辅助 N<10/N<2；非 DataFrame/重复轴/空表；先验参数必填；identity 短路；YJ λ=1/2 与 Box-Cox λ=0；`get_stats` |
| `tests/unit/test_adaptive_transformer_identity.py`（9 例） | rank 矩；NaN；identity no-op；先验参数；方法解析；非法输入 |
| `tests/integration/...::test_transform_auto_is_causal` | 隔离步骤 0 格 / 0 |
| `tests/integration/...::test_static_pipeline_is_truncation_invariant` | Static 端到端 0 格 / 0 |
| `tests/test_fix2_config_unification.py::test_09/test_11` | 嵌套 `transformation.method/target_distribution` → 扁平字段 |
| `tests/test_fix3_version_unification.py` | 4 处版本一致 + 5 处缓存代际一致 |

### 不覆盖范围

- **PL-05 / PL-06 / PL-07**：保持 `xfail` 登记。
- **死 rank 实现**：`EnhancedRankPreservingScaler` 与 `StandardizationConfig.method='rank'` 无生产路径，仅在调研文档登记。
- **旧 transform 逐列路径**：对显式非 rank 方法仍按列调用（逐元素方法无害）。
- **因子级 `identity` 配置**：`AdaptiveTransformer` 已支持，但未暴露到 `PipelineV2Config`。

### 后果

- **正面**：变换步骤结构上无拟合参数可泄漏；Static 端到端归零；`auto` 行为可复现；Mixed 与 Static 共用同一套配置；删除约 200 行选型/拟合死代码。
- **负面**：Static/Mixed 变换输出全部改变，历史 IC/Sharpe 与缓存需重建；rank 丢失量纲（需要原始单位的因子用 `identity`）；ties 输出相同值（排序不受影响）；非 rank 显式方法需人工提供先验参数，不能再“自动拟合”。
- **风险**：若未来需要数据自适应变换，必须显式新增估计轴并证明可复现性，不得恢复基于同一数据的 pre-test 切换。

### 学术与工业依据

- 秩变换/正态分数：Blom 正态分数约定（`k=0.375`，SAS PROC RANK / RNOmni 默认）；van der Waerden 分数（NIST Dataplot / SPSS）。
- Ordered Quantile Normalization：Peterson & Cavanaugh (2019, *Journal of Applied Statistics*)。
- pre-test 估计量不可一致估计：Leeb & Pötscher (2006, *Annals of Statistics*; 2008, *Econometric Theory*)。
- 全样本预处理导致信息泄漏：Kaufman, Rosset, Perlich & Stitelman (2012)；Kapoor & Narayanan (2023)。
- 工业实践：Qlib `CSRankNorm`（逐日截面）；Gu, Kelly & Xiu (2020) 的 rank 预处理；bestNormalize 的 ORQ 选型为一次性建模决策、预测阶段不重选。
- 详细检索记录与证据等级见调研文档；未核验项不作为本 ADR 的论据。

### 回滚方案

恢复 `AdaptiveTransformer` 的选型链与 `ProcessingAdapter` 的 else 分支；恢复 `MixedFactorPipeline` 的条件变换与 fit 顺序；恢复 `TransformationConfig` / `MixedPipelineConfig` / `PipelineV2Config` 字段；`CODE_VERSION` 回退至 `v2.2.1-cache` 并重建缓存；项目版本回退至 v3.3.3。回滚会使 PL-02/PL-04 的截断测试重新失败，应同时恢复其 `xfail` 登记。

---

## ADR-039: Mixed 缩尾统一为逐日截面 3σ (因果性修复)

**日期**: 2026-11-04
**状态**: 已实施
**优先级**: P0
**关联缺陷**: DEFECT-PL-06
**关联测试**: `tests/unit/test_mixed_winsorize_cross_sectional.py`、`tests/test_p3_phase2_config_migration.py`、`tests/integration/test_pipeline_truncation_invariance.py`
**调研/设计**: [PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md](docs/analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md) / [PL06_MIXED_WINSORIZE_LOOKAHEAD_DESIGN.md](docs/analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_DESIGN.md)

### 背景

`MixedFactorPipeline._compute_winsorize_params` 用 `X.mean(axis=0)` / `X.std(axis=0)` 按股票全历史估计 3σ 边界；`fit` 保存、`transform` 复用，导致前 t 期边界依赖 t 之后的数据。截断 60/100 期实测：**257/1800 格差异**，`max_abs_diff=6.984e-01`，首个发散日 = 2020-01-31（第 1 期）。PL-02 修复后该值取代 ADR-037 中记录的 2.91e-01。

### 决策

1. **逐日截面**：`mu = X.mean(axis=1)`，`sd = X.std(axis=1, ddof=1)`，`X.clip(lower=mu-σ·sd, upper=mu+σ·sd, axis=0)`。
2. **fit no-op**：`_winsorize_params = None`；删除 `_compute_winsorize_params`。
3. **配置契约不变**：`mixed_winsor_sigma` / `transform_aggressiveness` / optimizer 搜索空间保留。
4. **小截面**：`N<=10` 时 3σ 永不触发（最大 `|z|=(N-1)/√N<3`）；`N=2` no-op；`N=1` / 全 NaN / 零离散度原样返回。不引入数据触发的 pre-test。
5. **步骤顺序不变**：imputer → winsorize → neutralize → rank → z-score。

### 备选方案 (拒绝/延后)

- **B 逐日截面 percentile(1,99)**：与 PL-01/ADR-037 同口径，但需删除 `mixed_winsor_sigma` / `transform_aggressiveness` 并同步约 10 个测试/脚本；`N<=200` 时每行必截 min/max，`N=2` 两值向内压缩。本次不实施。
- **C per-stock expanding/rolling**：与项目截面口径不一致；ADR-037 已拒绝。
- **D 移除缩尾**：非冗余（移除 vs 当前 485/3000 格，max 1.7394）；放弃设计意图。
- **方法选择器（A+B 并存）**：新增配置面与双套测试，与 ADR-027 收敛方向冲突；独立能力任务。
- **Mixed 统一走 `ProcessingAdapter(outlier)`**：架构重构，独立任务。

### 代码证据

| 组件 | 位置 |
|------|------|
| `fit` Step 2 no-op | `pipelines_v2.py` `MixedFactorPipeline.fit` |
| 逐日截面缩尾 | `pipelines_v2.py` `MixedFactorPipeline._apply_winsorize` |
| 删除全样本参数 | `pipelines_v2.py`（原 `_compute_winsorize_params`） |
| 新单测 | `tests/unit/test_mixed_winsorize_cross_sectional.py` |
| 旧语义测试重写 | `tests/test_p3_phase2_config_migration.py::TestMixedWinsorSigma` |

### 实测证据

`T=100, N=30, seed=23, kind='skewed', t=60, atol=1e-12`：

| 对象 | 修复前 | 修复后 |
|------|--------|--------|
| Mixed 端到端截断不变式 | 257/1800 格，6.984e-01 | **0/1800，0** |
| 相对旧实现的全样本输出差异 | — | **561/3000 格，max 1.0446，Spearman 中位 0.999110 / 最小 0.942603** |
| 缩尾触发率 | 61/3000（2.03%） | **77/3000（2.57%）** |
| 性能（2500×3000，3 次中位） | 0.281s | **0.184s**（0.175/0.184/0.193） |

### 测试契约

新增 11 个单测（公共 7 + A 专属 4）；集成套件由 `9 passed / 3 xfailed` 变为 `10 passed / 2 xfailed`；`TestMixedWinsorSigma.test_07/08/09` 改为逐日截面语义；既有 `test_pipelines_v2.py` / `test_module_enabled.py` 全绿。

### 不覆盖范围

PL-05 / PL-07；B（percentile）；方法选择器；`ProcessingAdapter(outlier)` 统一路径；Mixed 3σ 与 Static percentile 的方法口径统一；optimizer 重新调参。

### 后果

- **正面**：Mixed 缩尾结构上不再有跨期参数；Mixed 端到端截断不变式归零；性能由 0.281s 降至 0.184s（约 −34%）；配置 / optimizer 契约不变。
- **负面/破坏性**：所有 Mixed 输出数值变更；历史 IC/Sharpe 需重算；缓存代际 bump 导致价格/收益缓存一次性失效；`N<=10` 时缩尾不动作（需文档化）。
- **已知遗留**：Mixed 使用 3σ 与 Static 使用 percentile(1,99) 的方法差异；统一需另开任务。

### 学术与工业依据

- MSCI FaCS Methodology (Bonne et al., 2018)：稳健均值 ± 3 稳健标准差（A）。
- Bali, Engle & Murray (2016)：winsorization vs truncation（A）；"cross-sectional distributions" 逐字引文未验证（U），不作强论据。
- Hampel (1974)；Rousseeuw & Croux (1993)：稳健尺度（A）。
- Banz & Breen (1986)；Kaufman et al. (2012)；Kapoor & Narayanan (2023)；Arnott et al. (2019)：样本依赖 / 泄漏（A）。
- Leeb & Pötscher (2006/2008)：pre-test 估计量分布不可一致估计（A/B）。
- 详细检索记录与证据等级见调研文档；未核验项不作为本 ADR 的论据。

### 回滚方案

恢复 `_compute_winsorize_params` 与 per-column `_apply_winsorize`；`CODE_VERSION` 回 `v2.2.2-cache`；项目版本回 v3.3.4；恢复 PL-06 的 `xfail`；恢复 `TestMixedWinsorSigma.test_07/08/09` 的旧语义；删除/重建缓存。

---

## 路线图

### 已完成 (v3.3.0 — Layer 3 溢价健康诊断双层体系, ADR-028)

- [x] Task 1: L2 Routing 消融修复 (P0) — 5 测试, 真实消融 5 配置全部通过
- [x] Task 2: 更多因子测试 (P1) — 10 因子分类验证
- [x] Task 3: 跨市场验证 (P1) — 4 市场 544 因子 100% 一致
- [x] Task 4: 原则评分 92% (P1) — Dickey-Fuller τ + F-test + Bonferroni
- [x] Task 5: 真实数据全量消融 (P1) — B3 IC=-0.0003, Sharpe=0.111
- [x] Task 6: Pipeline 日志 (P2) — `_intermediate_data` + `get_intermediate_data()`
- [x] Layer 3 FactorHealthDiagnoser: PremiumEstimator + BreakpointDetector + FactorHealthDiagnoser
- [x] 9/9 TDD 测试 + 128/128 全量回归 + A股 3 因子真实验证
- [x] 兼容性分析: FactorHealthDiagnoser vs FactorHealthMonitor — **互补不合并**
- [x] 文档同步: ADR-028 + CODE_WIKI v3.3.0 + CHANGELOG v3.3.0

### 已完成 (v3.2.0 — 学术准则驱动管线重构)

- [x] Step 1-3: Winsorizer 1%/99% + Transformer Shapiro-Wilk + Imputer ffill_ts (P0)
- [x] Step 4-6: 消融重跑 + 全量回归 (168/168) + A/B 对比 (p=0.80)
- [x] Step 7: Hard Routing + StatisticalClassifier (VR + AR(1), Lo-MacKinlay 1988)
- [x] Step 8: Anderson-Rubin 后验 R² 监控 (P2)
- [x] Step 9: 审计文档 v2.0 — 原则评分 68%→88%
- [x] 文档同步: CHANGELOG / DECISIONS (ADR-027) / CODE_WIKI / README / PROJECT_STATUS
- [x] 15 篇学术文献 (1964-2016) 支撑所有决策点

### 已完成 (v3.1.0 — Audit-Driven Code Quality Remediation)

- [x] P0×8 修复: adapter.py / pipeline.py / optimizer.py / pipelines_v2.py / multiple_testing.py / hidden_effect.py
- [x] P1×8 修复: fingerprint.py / endogeneity_estimators / endogeneity_regularizer / pipeline_v2 / factor_decoupler
- [x] P2+ A1-A4: 5 项断言恒真式重写 (Romano-Wolf / critical_alert / IVX bias / SCAD-MCP)
- [x] P2+ B1-B3: 10 项设计约束测试 (Config 字段 3 + 配置生效 2 + method_formal_name+选择器 5)
- [x] P2+ C1: 2 项跨文件端到端测试 (orchestrator + pipeline check_endogeneity)
- [x] P2+ E5: 5 项 AttributionAnalyzer 测试补强 (已知关系/β/零权重/BH/交互)
- [x] P2+ spec: 11 项 spec 反向对齐 (E1/E2/E4/E5/E9, 16 处标记)
- [x] 审计报告 + README v3.1.0 章节更新 + commit 6192edb 推送

### 已完成 (v2.1.0)

- [x] P0-1: 软路由
- [x] P0-2: 阈值校准
- [x] P1-3: 统一 fit() 模式
- [x] P1-4: 适配器回退 Warning
- [x] P1-5: transition_weights 接入
- [x] P2-6: KS 迁移显著性
- [x] P2-8: importlib 重构

### 已完成 (v2.2.0)

- [x] P0: 回测引擎集成 (方案 D — Peer Module + Adapter Pattern)
- [x] P1: factor_metrics.py — 因子级指标单一真相源 (30/30)
- [x] P2: data_bridge.py — Pipeline → DataLoaderV3 适配器 (10/10)
- [x] P3: engine.py — 因子回测引擎 (20/20)
- [x] P4: health_bridge.py — 回测 → FactorHealthMonitor 适配器 (13/13)
- [x] P5: unified_drift.py — 双轨融合漂移判定 (13/13)
- [x] P6: pipeline_integration.py — 端到端 Pipeline 集成 (9/9) + BacktestConfig 配置扩展
- [x] P7: L2 磁盘缓存层 (CacheManager + CachedDataLoader, ADR-008) (85/85)

### 已完成 (v2.2.1 — 漂移检测与优化器改进)

- [x] P0-1: 滚动窗口 KS + 调松阈值 (unified_drift.py)
- [x] P0-2: 优化器 Pipeline-in-the-loop (optimizer.py)
- [x] P1: 因子日期自适应 min_dates (data_bridge.py + engine.py)
- [x] P2-1: 双信号加权融合 — and/or/max 三模式 (unified_drift.py)
- [x] P2-2: 优化器 CV 改进 — _cv_evaluate 接口重写 + optimize() 调用 CV (optimizer.py)
- [x] P3-2: 分组并行方案 A/B 对比实验 — 保留方案 A (ADR-009)

### 已完成 (v2.2.2 — 代码质量修复 7 项)

- [x] Fix 1: self.factors dead-code bug + KS 拆分语义修复 (P0)
- [x] Fix 5: 硬编码路径改为环境变量配置项 (ADR-012)
- [x] Fix 2: 配置系统统一 — 方案 C 桥接层 (ADR-010)
- [x] Fix 3: 版本号统一 (2.2.1)
- [x] Fix 4: backtest/__init__.py 补全 26 个公开 API 导出
- [x] Fix 7: core 命名空间碰撞修复 (ADR-011) — test_p0_duckdb_pivot 16/16 恢复
- [x] Fix 6: ADR 状态更新 (ADR-010/011/012 新增, ADR-007 风险更新)

### 已完成 (v2.2.3 — 外部模块子包化 + 命名空间根治, ADR-013)

- [x] P4': V2 三个失败测试修复 (per-factor 独立 pipeline 方案)
- [x] P1.1: 6 个外部模块 (Factor_DB / Factor_Fingerprint / Factor_Decoupler / Factor_AdaptiveWinsor / Factor_Imputer_v2.0 / factor_neutralizer) 添加 __init__.py + pyproject.toml, 子包化 + pip install -e .
- [x] P1.2: factor_pipeline 内部 importlib/sys.path 黑魔法清理 (health_bridge / cached_data_loader / adapters + 外部模块内部导入 42 处)
- [x] P1.3: 全量回归验证 + ProcessingAdapter standardization 按列 fit 修复 + test_12 sys.modules 清理 (614 passed, 0 failed)

### 已完成 (v2.2.4 — 依赖锁定, ADR-014)

- [x] P2.1: 依赖调研 (7 核心 + 2 可选 + 6 外部本地模块)
- [x] P2.2: 创建 factor_pipeline/pyproject.toml (REQUIRED + OPTIONAL extras, flat-layout where=[".."])
- [x] P2.3: pip install -e . 验证 (元数据正确, 跨目录导入)
- [x] P2.4: 删除 adapters.py 优雅回退 (ImputerAdapter/ProcessingAdapter → AdapterImportError)
- [x] P2.5: 清理 HAS_SCIPY / HAS_STATSMODELS / HAS_PIPELINE 死代码 (保留 HAS_ARCH / HAS_OPTUNA)
- [x] P2.6: 全量回归 (613 passed, 0 新增失败) + 版本统一 2.2.1→2.2.3 (手工校验 5/5)
- [x] P2.7: ADR-014 记录 + project_memory 更新

### 已完成 (v2.2.5 — adapters 重构, ADR-015)

- [x] P3.1: 调研 adapters.py 问题 (5 项: NeutralizerAdapter fallback/双重导入/sm死代码/'external'标记, GarchWhitening重复导入)
- [x] P3.2: NeutralizerAdapter REQUIRED 化 (AdapterImportError + 缓存类 + 删除 fallback/sm死代码/'external'标记)
- [x] P3.3: GarchWhiteningAdapter 模块级导入 (删除 _get_arch_model_class 重复导入)
- [x] P3.4: 测试更新 (test_26 assertRaises + 新增 NeutralizerAdapter fallback 测试 + test_28 注释)
- [x] P3.5: 手工校验 5/5 + 全量回归 (614 passed, 0 新增失败)
- [x] P3.6: ADR-015 记录 + project_memory 更新


### 已完成 (v2.2.6 — 技术债清理, ADR-016)

- [x] TD-1.1: 调研 Factor_Trading_v3.0 结构 (data_v3.py 独立轻量, core/ 62 处 from core.X import)
- [x] TD-1.2: Factor_Trading_v3.0 子包化 (pyproject.toml packages + __init__.py 轻量 + core/__init__.py 空)
- [x] TD-1.3: pip install -e . 验证 (Factor_Trading_v3_0 可从任意目录导入)
- [x] TD-1.4: 清理 data_bridge.py importlib hack → 直接导入 + AdapterImportError
- [x] TD-1.5: TDD 测试 + 手工校验 6/6 + 全量回归 (test_fix5 6/6, test_fix7 15/15, 0 新增失败)
- [x] TD-2: test_parallel flaky 修复 (Windows skipif, 1 skipped 而非 1 failed)
- [x] TD-3: NeutralizerAdapter fit/transform 语义重构 (ADR-018, 见 v2.2.7)
- [x] TD-4: ADR-016 记录 + project_memory 更新

### 已完成 (v2.3.0 — 跨版本 CI 矩阵, ADR-017)

- [x] P4.1: 调研现有 CI 状态 (无 .github/workflows, 无 tox.ini, pyproject 声明 >=3.9)
- [x] P4.2: 设计 CI 矩阵策略 (GitHub Actions + tox 双轨, Python 3.10/3.11/3.12 × ubuntu)
- [x] P4.3a: 创建 .github/workflows/ci.yml (矩阵 + 外部模块 git clone + 目录重命名)
- [x] P4.3b: 创建 tox.ini (py310/py311/py312 + lint + coverage 环境)
- [x] P4.4: 本地验证 CI 配置正确性 (37/37 校验通过 + 21/21 回归测试通过)
- [x] P4.5: ADR-017 记录 + project_memory 更新



### 已完成 (v2.2.7 — NeutralizerAdapter fit/transform 语义重构, ADR-018)

- [x] TD-3.1: 调研旧实现问题 (fit 空操作 / transform 临时计算 / kwargs 透传 bug / 与兄弟 adapter 不一致)
- [x] TD-3.2: 设计重构方案 (fit 预计算 dummies 缓存, transform 3 级优先级: external → cache → skip)
- [x] TD-3.3a: TDD Red — 新增 test_td3_neutralizer_semantics.py (12 测试, 5 failed/7 passed)
- [x] TD-3.3b: TDD Green — 重构 fit/transform/_neutralize_with_cache (12 passed)
- [x] TD-3.4: 手工校验 6/6 PASS (dummies 结构/OLS 残差一致/fit_transform 一致/无 industry_data 跳过/external 优先级/NaN 边界) + 全量回归 632 passed/5 skipped
- [x] TD-3.5: ADR-018 记录 + project_memory 更新


### 已完成 (v2.4.0 — 外部模块内化, ADR-019)

- [x] I1.1: 阶段 1 — Factor_Decoupler + Factor_Fingerprint 内化 (零新增依赖, 命名规范化, ~45 处 import 替换)
- [x] I1.2: 阶段 1 TDD + 全量回归验证 (632 passed)
- [x] I2.1: 阶段 2 — Factor_AdaptiveWinsor 内化 (最小子包化: 只迁 core/, 新增 sklearn 依赖)
- [x] I2.2: 阶段 2 TDD + 全量回归验证 (632 passed, 依赖上界冲突检测)
- [x] I3.1: 阶段 3 — Factor_Imputer 内化 (版本后缀移除, sklearn 共享, 22 处导入清理)
- [x] I3.2: 阶段 3 TDD + 全量回归验证 (632 passed)
- [x] I4.1: 阶段 4 — Factor_Neutralizer 内化 (src-layout → flat-layout, 依赖裁剪, plt.Figure 注解修复)
- [x] I4.2: 阶段 4 TDD + 全量回归验证 (632 passed)
- [x] I5.1: 阶段 5 — CI/文档清理 (CI monorepo 7→2, 删除 7 个失效脚本, 版本号 11 处统一)
- [x] I5.2: ADR-019 状态更新为已实施 + project_memory 更新

### 计划中 (v2.5.0 — 多因子横截面正交化, ADR-020)

- [x] O1: 核心算法 + TDD (symmetric_orthogonalize / gram_schmidt / variance_retention_ratio) — 44 测试 + 15 手工校验
- [x] O2: 适配器集成 (OrthogonalizerAdapter + CrossSectionalOrthogonalizer + O2.8 六项深化) — 22 测试 + 12 手工校验, 全量回归 698 passed
- [x] O3a: 几何诊断 (VRR/κ/VIF/正交性误差 + O3a.6 深化) — 18 单元测试 + 24 手工校验, 含 VRR 数学修正
- [x] O3b: Layer 3 因子检验 (双重 Lasso Belloni 2014 PDS + O4.9 七项深化) — 17 单元测试 + 14 手工校验, 含 HC3 公式 bug 修复
- [x] O4: 回测扩展 (RollingOrthogonalizer + ICChangeMonitor + O4.9/O4.11 深化) — 11 单元测试 + 19 手工校验, 含 O4.11.1/2/3/5 深化 (warm-start O4.11.4 设计标注可选未实现)
- [x] O5: 与 Factor_Fingerprint/Decoupler 协同验证 (Grouped + TripleChain + O5.6 深化) — 15 单元测试 + 17 手工校验, 含 O5.6.1 数据流协议/O5.6.2 中性化顺序/O5.6.3 缺失因子/O5.6.4 缓存/O5.6.5 冲突解决
- [x] O6: ADR-020 状态更新为已实施 + project_memory 更新 + 全量回归 860 passed + 5 skipped (sys.path 污染技术债 #5 已修复: tests/manual/test_adapter_manual.py:test_disabled_adapter_no_import 添加 try/finally 恢复 sys.modules)

### 计划中 (v2.6.0 — 优化器与漂移检测增强, ADR-021/022/023)

**分析报告**: [docs/ANALYSIS_V2.6.0.md](docs/ANALYSIS_V2.6.0.md) v1.1 (810 行, 8 类问题 / 8 项任务 / 11 项风险)
**执行方案**: [docs/EXECUTION_V2.6.0.md](docs/EXECUTION_V2.6.0.md) (1595 行, 9 阶段 E1-E9, ~59 新测试)

- [x] E1 / P3-11': 文档状态修正 (P0, 仅文档) — DECISIONS.md P3-11 状态 `[ ]` → `[x]`, 学术依据分拆 (TPE→Bergstra 2011, fANOVA→Hutter 2014)
- [x] E2 / P3-10': migration_threshold 字段位置修正 + ADR-005 更新 (P0, 5 测试) — optimizer.py:150-158 字段位置错误 (config.monitor → config), ADR-005 末尾追加修订日志
- [x] E3 / P3-1': IC 时间加权 EWMA (P1, 8 测试) — factor_metrics.py compute_ic_series 添加 weighting/halflife 参数, optimizer._compute_ic 集成 EWMA, 学术依据改引 Ferson-Siegel (2001)
- [x] E4 / P3-9': 目标函数对齐 ADR-004 (P1, 10 测试, 依赖 E3) — _composite_objective 添加 health_penalty (代理指标方案 B), 修正 fidelity 符号方向 (+ → -), 新增 _health_penalty_proxy (decay_ratio/hit_rate/ic_vol 三档), 全量回归 883 passed (877 + phase4 6)
- [x] E5 / P3-13: 正交化参数纳入搜索空间 (P1, 8 测试, 依赖 E2) — DEFAULT_SEARCH_SPACE_ORTH 添加 orth_method/align_mode/ridge_lambda (不搜索 orth_enabled), optimize() 添加 categorical + log-uniform 采样, 全量回归 885 passed
- [x] E6 / P3-14: 几何诊断纳入目标函数 (P2, 12 测试, 依赖 E5) — OrthogonalizerAdapter.fit() 保存 _F_stacked_/_T_stacked_, get_diagnostics() 新方法, _redundancy_penalty 基于 compute_vrr (λ=0.05, v1.1 从 0.1 降), _composite_objective 6 项对齐 ADR-004 (IC-vol-cov-ks-health-redundancy), look-ahead bias 防护 (F/T 来自 train fit), 全量回归 903 passed (885+12+6 subtests)
- [x] E7 / P3-15: Layer 3 显著性最终验证 (P2, 6 测试, 依赖 E4) — _validate_significance 调用 FactorSignificanceTest (Belloni 2014 PDS Lasso+HC3+BH), optimize() 添加 validate_significance 参数 (默认 False 向后兼容), 对齐+dropna 处理 NaN (LassoCV 不接受), 异常防护 (空 factor_data/Pipeline 失败返回错误报告), 手工校验 6/6 通过
- [x] E8 / P3-12': 阈值漂移监测 (P2, 10 测试, 依赖 E4) — backtest/threshold_drift_monitor.py 新建, ThresholdDriftMonitor (EWMA 衰减检测, decay > 20% 触发 needs_research), update/get_history/reset 三方法, min_observations=5 保护, 学术依据 Bailey-López de Prado 2014 + Sullivan-TW 1999 + McLean-Pontiff 2016, 手工校验 6/6 通过
- [x] E9: 文档验证 + 全量回归 (P1, 依赖 E1-E8) — README/CHANGELOG/CODE_WIKI/project_memory 更新, verify_v2_6_0_manual.py 8/8 手工校验通过, 全量回归 918 passed + 6 skipped + 11 subtests passed (19:31)

**总计**: ~59 新测试 + 860 基线 = ~919 passed

### 远期 (v3.0.0)

- [x] 指纹维度扩展至 21 维（尾部依赖、体制转换）— 已实施 (2026-07-04, ADR-024, E1-E3 全部完成, 974 passed + 6 skipped + 11 subtests)
  - 核心改动: `fingerprint.py` NamedTuple 13→21 维 (8 新: tail_dependence_lower/upper, gpd_shape, hill_estimator, regime_transition_prob/persistence/ic_diff, tail_regime_score) + `FingerprintConfig` 8→14 字段 + 8 新计算方法 + `pipelines_v2.py` `_get_multi_dim_pipeline_weights` 接入 transform + `enable_multi_dim_routing` 开关 (默认 False)
  - 测试: tests/test_factor_fingerprint/ (32 测试, 含 tail_dependence/regime_switching/tail_regime_score/extract_fingerprint_golden) + tests/test_multi_dim_classifier.py (8 新测试) + verify_v3_0_0_t1_manual.py (8/8 手工校验)
  - 文档: docs/ANALYSIS_V3.0.0.md §1 + docs/EXECUTION_V3.0.0_T1.md v1.1
  - 学术依据: Nelsen (2006) / Pickands (1975, 实际用 POT-MLE 替代) / Hill (1975) / Hamilton (1989)
  - 行为变化: 默认关闭 (enable_tail_dependence/enable_regime_switching=False), 显式 opt-in; 路由修正仅 enable_multi_dim_routing=True 时生效
- [ ] 流式处理支持
- [x] CUSUM 在线漂移检测 — 已实施 (2026-07-07, ADR-025, T3.1-T3.6 全部完成, 385 passed + 1 skipped)
- [x] Benjamini-Hochberg FDR 替代 Bonferroni — 已实施 (2026-07-04, ADR-002a, E1-E3 全部完成, 934 passed + 6 skipped + 11 subtests)
  - 核心改动: `pipelines_v2.py:236-457` `_ks_migration_significance` 新增 `correction_method` 参数 (默认 'benjamini_hochberg'), 三路径分流 (BH/Bonferroni/none), 字段隔离
  - 测试: tests/test_pipelines_v2/test_ks_migration_bh.py (13 测试) + tests/manual/test_factor_significance_manual.py TestKSMigrationBHCorrection (3 测试) + verify_v3_0_0_t4_manual.py (8/8 手工校验)
  - 文档: docs/ANALYSIS_V3.0.0.md v1.1 + docs/EXECUTION_V3.0.0_T4.md v1.1
  - 行为变化: BH 比 Bonferroni 宽松, `is_sig` 可能 False→True, 显式 `correction_method='bonferroni'` 可回退