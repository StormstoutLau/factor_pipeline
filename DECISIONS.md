# 决策路线 (Architecture Decision Records)

## 概览

本文档记录 factor_pipeline 项目中的关键架构决策，包括每个决策的背景、备选方案、选择理由和后果。

**决策原则 (Constitution)**:
1. 因子不是静态标签，而是概率分布
2. 管道不是统一流水线，而是精准适配
3. 所有统计判断必须有显著性检验支撑
4. 外部模块不可用时应显式告警，而非静默失败

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

## 路线图

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
- [ ] 在线迁移检测（CUSUM）
- [x] Benjamini-Hochberg FDR 替代 Bonferroni — 已实施 (2026-07-04, ADR-002a, E1-E3 全部完成, 934 passed + 6 skipped + 11 subtests)
  - 核心改动: `pipelines_v2.py:236-457` `_ks_migration_significance` 新增 `correction_method` 参数 (默认 'benjamini_hochberg'), 三路径分流 (BH/Bonferroni/none), 字段隔离
  - 测试: tests/test_pipelines_v2/test_ks_migration_bh.py (13 测试) + tests/manual/test_factor_significance_manual.py TestKSMigrationBHCorrection (3 测试) + verify_v3_0_0_t4_manual.py (8/8 手工校验)
  - 文档: docs/ANALYSIS_V3.0.0.md v1.1 + docs/EXECUTION_V3.0.0_T4.md v1.1
  - 行为变化: BH 比 Bonferroni 宽松, `is_sig` 可能 False→True, 显式 `correction_method='bonferroni'` 可回退