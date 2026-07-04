# v3.0.0 远期规划 — 方案分析报告 v1.1

> **版本**: v1.1 (2026-07-04)
> **范围**: v3.0.0 远期路线图 4 项任务的深度核查
> **基础**: DECISIONS.md L1542-1547 (v3.0.0 远期清单)
> **前置**: v2.6.0 E1-E9 全部完成 (918 passed + 6 skipped + 11 subtests)
> **方法**: 与 v2.6.0 ANALYSIS 同样的深度核查流程 — 问题分析 / 任务拆解 / 风险评估 / 学术依据校验
> **v1.1 修订**: 根据 review (3 MAJOR + 5 MINOR + 4 NIT + 3 论文标题补全) 系统性修订, 详见末尾修订日志

---

## 0. 摘要

v3.0.0 包含 4 项远期任务, 深度核查后发现:

| # | 任务 | 当前状态 | 改动量估算 | 优先级 | 关键发现 |
|---|------|---------|-----------|--------|---------|
| T1 | 指纹维度扩展至 20+ (尾部依赖、体制转换) | 13 维, 0/2 新维度类别实现 | ~600 行 (5 文件) | P1 | tail dependence 完全缺失; regime 仅 HealthMonitor 有弱相关实现, 不属 FactorFingerprint |
| T2 | 流式处理支持 | 纯批量 (0/5 就绪度) | ~1500+ 行 (8+ 文件) | P2 | 全链路基于全量 DataFrame 假设; RollingOrthogonalizer 算法已就绪但 API 未暴露 partial_fit |
| T3 | 在线迁移检测 (CUSUM) | KS 批处理 + EWMA 流式 (非 CUSUM) | ~400 行 (3 文件) | P1 | ThresholdDriftMonitor.update() 已是流式接口, 可扩展为 CUSUM; Page (1954) 未引用 |
| T4 | Benjamini-Hochberg FDR 替代 Bonferroni | factor_significance.py 已默认 BH; KS 迁移路径仍用 Bonferroni | ~130 行 (8 文件) | P0 | 默认生效的 bonferroni 路径仅 1 函数 (~20 行); factor_significance.py 已完整支持 BH, E7 已用 BH |

**4 项任务依赖关系**:
- T4 (BH-FDR) 独立, 改动最小 → 优先实施
- T3 (CUSUM) 独立, 但与 T2 流式协同 (真正流式 CUSUM 需流式管道)
- T1 (指纹扩展) 独立, 可与 T3/T4 并行
- T2 (流式) 是其他任务的基础设施, 应作为长期改造分阶段推进

**推荐执行顺序**: T4 (P0) → T1 ∥ T3 (P1) → T2 (P2 长期)

---

## 1. T1: 指纹维度扩展至 20+ (尾部依赖、体制转换)

### 1.1 问题分析

**当前状态**: 13 维指纹, 定义于 [modules/factor_fingerprint/core/fingerprint.py:34-70](file:///f:/Coding/factor_pipeline/modules/factor_fingerprint/core/fingerprint.py)

| 类别 | 维度数 | 字段 |
|------|--------|------|
| 时序稳定性 | 5 | ar1_median / rank_autocorr / vol_clustering_pvalue / half_life / level_diff_ic_ratio |
| 截面稳定性 | 5 | skewness_std / kurtosis_std / js_divergence_mean / missing_cv / coverage_ratio |
| 综合衍生 | 3 | sd_score / complexity_need / snr_estimate |

**目标**: 扩展至 20+, 即新增至少 7 维, 重点为:
- **尾部依赖 (tail dependence)**: 完全缺失 (全仓库 `tail_depend|copula|gpd|hill.estimator` 搜索 0 命中)
- **体制转换 (regime switching)**: 无 Markov/HMM/Hamilton 实现; HealthMonitor 有 `_evaluate_regime` (health.py:1373) 但属独立维度, 不属 FactorFingerprint

**关键发现**:
1. `_get_multi_dim_pipeline_weights` (pipelines_v2.py:96-179) 名为"多维"但实际只用 4 维 (skewness_std / kurtosis_std / snr_estimate + 间接 ar1_median), 其余 9 维未在路由权重中使用 → 扩展空间充足
2. 现有 13 维量纲不统一 (有的 [0,1], 有的 [0,+∞)), 但已有标准化模式 `_derive_sd_score` (fingerprint.py:425-452): `np.clip(x / 上界, 0, 1)` + 加权合成 → 新维度应遵循此模式
3. 仓库无 `FingerprintAdapter` 类 (全仓库搜索 0 命中), 指纹通过 `FactorProcessingPipelineV2` 直接持有 `FactorFingerprinter` 实例接入 (pipelines_v2.py:908)

### 1.2 任务拆解

**T1.1 尾部依赖维度 (新增 4 维)**
- `tail_dependence_lower`: 下尾依赖系数, 基于 Copula (Clauset 2009)
- `tail_dependence_upper`: 上尾依赖系数
- `gpd_shape`: GPD 形状参数 ξ (Pickands 1975), 反映重尾程度
- `hill_estimator`: Hill 估计量 (Hill 1975), 重尾指数

**实施位置**: [modules/factor_fingerprint/core/fingerprint.py](file:///f:/Coding/factor_pipeline/modules/factor_fingerprint/core/fingerprint.py)
- 扩展 `FactorFingerprint` NamedTuple (L34-70)
- 在 `extract_fingerprint` (L107) 追加计算步骤
- 新增 `_compute_tail_dependence` / `_estimate_gpd_shape` / `_hill_estimator` 私有方法
- 同步更新 `to_dict` (L55-70) 和 `FingerprintConfig` (L73-83, 新增分位数阈值、最小样本配置)

**T1.2 体制转换维度 (新增 3 维)**
- `regime_transition_prob`: Markov 两状态转移概率 (Hamilton 1989, "A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle")
- `regime_persistence`: regime 平均持续期
- `regime_ic_diff`: 两 regime 间 IC 差异 (bull - bear)

**实施位置**: 同 T1.1
- 复用 `health.py:_split_bull_bear` (L1452) 和 `_compute_ic_series` (L833) 的思路, 但避免与 HealthMonitor 重复 (DECISIONS.md:140 已警示 regime 敏感性缺失问题)
- 新增 `_compute_regime_transition` 私有方法
- 依赖: statsmodels Markov switching (已有 statsmodels REQUIRED 依赖)

**T1.3 综合衍生维度 (新增 1 维)**
- `tail_regime_score`: 尾部+体制综合得分, 遵循 `_derive_sd_score` 模式归一化到 [0,1]

**T1.4 路由层接入**
- 更新 `_get_multi_dim_pipeline_weights` (pipelines_v2.py:96-179), 为新维度设定经验阈值
- 更新 `AdaptiveFactorClassifier` (classifier.py), 可选纳入新维度
- 全量回归: 确保 860 基线不受影响 (新增维度默认 None, 不破坏旧路径)

### 1.3 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| 尾部估计在小样本下不稳定 (GPD/Hill 需 ≥ 100 个极值点) | 高 | 设置 `min_extreme_samples=100` 配置, 不足时返回 NaN |
| Markov 拟合可能不收敛 (EM 算法局部最优) | 中 | 添加收敛检查, 不收敛时返回 NaN + 降级为硬阈值 bull/bear 划分 |
| 新维度数值范围跨度大 (GPD shape ∈ (-0.5, +∞)) | 中 | 严格遵循 `_derive_sd_score` clip 归一化模式 |
| 扩展后 13→20 维破坏现有分类器 (仅用 ar1) | 低 | 新维度默认 None, 分类器向后兼容; 仅 `_get_multi_dim_pipeline_weights` 可选接入 |
| Copula 拟合计算成本高 (O(N²)) | 中 | 仅在 `FingerprintConfig.enable_tail_dependence=True` 时计算, 默认关闭 |
| Markov 拟合需要 mle + 数值优化, 可能引入 statsmodels 重依赖 | 低 | statsmodels 已是 REQUIRED 依赖 (ADR-014), 无新依赖 |

### 1.4 学术依据

| 维度 | 学术依据 | 状态 |
|------|---------|------|
| 尾部依赖 (Copula) | Nelsen (2006) An Introduction to Copulas | 待引入 |
| GPD 极值理论 | Pickands (1975) Statistical inference using extreme order statistics | 待引入 |
| Hill 估计量 | Hill (1975) A simple general approach to inference about the tail of a distribution | 待引入 |
| Markov 体制转换 | Hamilton (1989) A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle | 待引入 |
| CUSUM (与 T1.2 协同) | Page (1954) Continuous Inspection Schemes | 待引入 (T3 共享) |

---

## 2. T2: 流式处理支持

### 2.1 问题分析

**当前状态**: 纯批量模式, 流式就绪度 0-3/5

| 维度 | 现状 | 就绪度 |
|------|------|--------|
| Pipeline 主流程 | 纯批量 `fit/transform` (pipelines_v2.py:935, 1050) | 0/5 |
| RollingOrthogonalizer | 已有增量 Gram 算法 (rolling.py:84-110), 但 API 接受全量 `(T,N,K)` | 3/5 |
| Winsor/Imputer | 全部仅 `fit`, 无 `partial_fit` (6 个 imputer 全无) | 1/5 |
| Neutralizer | 无状态函数式调用 (FactorNeutralizer.py:658) | 1/5 (最易改造) |
| cache/cached_data_loader | 已有 `start_date`/`end_date` 参数, 但返回物化 DataFrame | 2/5 |
| Factor_DB | 支持日期范围查询, 无原生流式游标 | 2/5 |
| 数据格式 | 宽表 `Dict[str, DataFrame]`, 全量入参 | 2/5 |
| post_transform_hooks | 全量 factor_dict 处理, rolling 路径仅 docstring 声明未实现 (adapters.py:898) | 1/5 |

**关键瓶颈**: 整个 API 链路 (factor_cache → DataLoader → Pipeline → hooks) 基于"一次性全量 DataFrame"假设。流式改造不是单点改造, 而是全链路改造。

### 2.2 任务拆解 (分阶段)

**T2.1 数据加载层流式化 (基础设施)**
- 新增 `iter_periods(start, end, step)` 生成器, 包装 `cached_data_loader.get_pivoted_factors`
- 文件: [backtest/cached_data_loader.py](file:///f:/Coding/factor_pipeline/backtest/cached_data_loader.py)
- 接口: `def iter_periods(self, factor_names, start_date, end_date, step='D') -> Iterator[Dict[str, pd.DataFrame]]`

**T2.2 组件层 partial_fit 接口**
- 为 `Neutralizer` 添加 `partial_fit(X_t)` (最易, 无状态)
- 为 `AdaptiveWinsor` / `Imputer` 添加 `partial_fit(X_t)`, 内部用 Welford 在线算法 / EWMA
- 文件: [modules/factor_neutralizer/core/FactorNeutralizer.py](file:///f:/Coding/factor_pipeline/modules/factor_neutralizer/core/FactorNeutralizer.py) 等

**T2.3 正交化层流式激活**
- 让 `OrthogonalizerAdapter` 在 `window_mode='rolling'` 时实际委托给 `RollingOrthogonalizer` (当前是 docstring 声明未实现, adapters.py:898)
- 暴露 `hook.update(X_t) -> X_t_orth` 单期接口
- 文件: [adapters.py](file:///f:/Coding/factor_pipeline/adapters.py), [modules/factor_orthogonalizer/rolling.py](file:///f:/Coding/factor_pipeline/modules/factor_orthogonalizer/rolling.py)

**T2.4 Pipeline 主流程流式入口**
- 新增 `FactorProcessingPipelineV2.transform_streaming(factor_iter)` 入口
- 内部维护各组件状态, 按期驱动
- 文件: [pipelines_v2.py](file:///f:/Coding/factor_pipeline/pipelines_v2.py)

**T2.5 CUSUM 流式协同 (与 T3 共享)**
- ThresholdDriftMonitor.update() 已是流式接口, 可直接接入

### 2.3 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| 全链路改造回归风险高 | 高 | 分阶段实施, 每阶段全量回归; 流式接口与批量接口并存 (默认批量) |
| 在线估计器 (Welford/EWMA) 与批量估计器数值不一致 | 高 | 添加数值一致性测试, 精度 < 1e-10 |
| 流式 CUSUM 状态维护复杂 (S[t] 累积) | 中 | 严格遵循 Page (1954) reset 规则 |
| 内存释放: 流式不应累积全量历史 | 中 | 用 deque(maxlen=window) 限制内存 |
| API 兼容性: 新增流式接口不应破坏现有批量接口 | 高 | 默认批量, 流式需显式 opt-in |
| 测试基础设施: 需要流式 vs 批量等价性测试 | 中 | 新增 test_streaming_equivalence.py |

### 2.4 学术依据

| 主题 | 学术依据 | 状态 |
|------|---------|------|
| 在线均值/方差估计 | Welford (1962) Note on a method for calculating corrected sums of squares and products | 待引入 |
| EWMA 时间加权 | Roberts (1959) Control Chart Tests Based on Geometric Moving Averages | 已引入 (v2.6.0 E3) |
| 滑动窗口正交化增量 Gram | Golub & Van Loan (2013) Matrix Computations 4th ed. | 已引入 (v2.5.0 O4.11) |

---

## 3. T3: 在线迁移检测 (CUSUM)

### 3.1 问题分析

**当前状态**: KS 批处理 + EWMA 流式 (非 CUSUM)

| 组件 | 位置 | 性质 |
|------|------|------|
| KS 迁移检测 | [pipelines_v2.py:236-359](file:///f:/Coding/factor_pipeline/pipelines_v2.py) `_ks_migration_significance` | **批处理**: 一次 transform 内对半切分 KS |
| 滚动窗口 KS | [backtest/unified_drift.py:109-157](file:///f:/Coding/factor_pipeline/backtest/unified_drift.py) `_compute_rolling_structure_drift` | **批处理**: 全序列扫描, 非增量; 滚动窗口循环内多次 KS 检验无多重比较校正 (M3 修正, 潜在 BH 迁移候选) |
| EWMA 性能衰减监测 | [backtest/threshold_drift_monitor.py:65-124](file:///f:/Coding/factor_pipeline/backtest/threshold_drift_monitor.py) `update` | **真流式**, 但监测的是 score 性能衰减 (回测指标退化), 非因子分布漂移; CUSUM 扩展应区分两类监测目标 |

**关键发现**:
1. CUSUM 在 DECISIONS.md 中仅作远期占位出现 3 次 (L79, L1373, L1546), 无 Page (1954) / Brown-Durbin-Evans (1975) 学术引用
2. 全仓库无 `scipy.signal.cusum` / `statsmodels.*diagnostic` breaks 引用
3. `ThresholdDriftMonitor.update()` 已是流式接口, 数学上可扩展为 CUSUM: 维护 `S[t] = max(0, S[t-1] + (s[t] - best_score - k))`, 触发 `S[t] > h`
4. 现有 `score_history: List[float]` (threshold_drift_monitor.py:58) 便于回填校验
5. KS 检验结构上不适合单期增量 (需两样本对照), CUSUM 是替代方案

### 3.2 任务拆解

**T3.1 CUSUM 监测器实现**
- 新增 `CUSUMDriftMonitor` 类 (或扩展 ThresholdDriftMonitor 添加 `mode='cusum'`)
- 数学: `S[t] = max(0, S[t-1] + (x[t] - mu_0 - k))`, 触发 `S[t] > h`
- 参数: `k` (allowance, 参考漂移量), `h` (decision threshold)
- reset 逻辑: 触发后 `S[t] = 0`
- 文件: [backtest/threshold_drift_monitor.py](file:///f:/Coding/factor_pipeline/backtest/threshold_drift_monitor.py) (扩展) 或新建 `backtest/cusum_drift_monitor.py`

**T3.2 与现有 KS 迁移检测协同**
- CUSUM 监测因子分布漂移 (基于指纹距离或 IC 序列)
- KS 保留作为 batch 模式回填校验
- 文件: [pipelines_v2.py](file:///f:/Coding/factor_pipeline/pipelines_v2.py) `_ks_migration_significance`

**T3.3 学术引用补全**
- 新增 ADR: ADR-024 CUSUM 在线变点检测
- 引用: Page (1954) / Brown-Durbin-Evans (1975) CUSUMSQ "Techniques for Testing the Constancy of Regression Relationships over Time" / Csörgő-Horváth (1997) Limit Theorems in Change-Point Analysis

**T3.4 流式协同 (依赖 T2)**
- 真正流式 CUSUM 需要流式管道 (T2.4)
- 当前可在批量 transform 内部模拟流式 (内部循环 t)

### 3.3 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| CUSUM 参数 (k, h) 选择敏感 | 高 | 提供自适应参数选择 (基于历史 IC 波动率), 或提供 Page (1954) 推荐默认值 |
| CUSUM 触发后 reset 可能漏报连续漂移 | 中 | 双侧 CUSUM (上下界), 或 reset 后立即重新初始化 |
| CUSUM vs EWMA 选择困难 | 中 | 提供 `mode='ewma'/'cusum'/'both'`, 用户可选 |
| 与现有 KS 检测冲突 (双系统) | 中 | CUSUM 用于流式预警, KS 用于 batch 校验, 角色互补 |
| 小样本下 CUSUM 假阳性高 | 中 | 设置 `min_observations=5` 保护 (沿用 ThresholdDriftMonitor 模式) |

### 3.4 学术依据

| 主题 | 学术依据 | 状态 |
|------|---------|------|
| CUSUM 序贯检验 | Page (1954) Continuous Inspection Schemes | 待引入 |
| CUSUMSQ 残差异方差检验 | Brown-Durbin-Evans (1975) Techniques for Testing the Constancy of Regression Relationships over Time | 待引入 |
| 变点分析极限理论 | Csörgő-Horváth (1997) Limit Theorems in Change-Point Analysis | 待引入 |
| CUSUM 在金融应用 | Andreou-Ghysels (2002) Detecting Multiple Breaks in Financial Market Volatility Dynamics (待进一步核实精确标题) | 待引入 |

---

## 4. T4: Benjamini-Hochberg FDR 替代 Bonferroni

### 4.1 问题分析

**当前状态**: BH 已部分实施, Bonferroni 残留 1 处

| 位置 | 校正方法 | 状态 |
|------|---------|------|
| [backtest/factor_significance.py:69](file:///f:/Coding/factor_pipeline/backtest/factor_significance.py) `correction` 默认值 | **BH** (默认) | ✅ 已迁移 |
| [backtest/factor_significance.py:410-458](file:///f:/Coding/factor_pipeline/backtest/factor_significance.py) `_apply_correction` 4 选项 (方法定义 L410, 4 选项分支 L421-458) | none / bonferroni / **benjamini_hochberg** / holm | ✅ 已支持 |
| [optimizer.py:834, L895](file:///f:/Coding/factor_pipeline/optimizer.py) `_validate_significance` (L834, v2.6.0 E7) / BH 参数 (L895) | **BH** | ✅ 已用 BH |
| [pipelines_v2.py:333, 344](file:///f:/Coding/factor_pipeline/pipelines_v2.py) `_ks_migration_significance` | **Bonferroni** (`alpha / n_tests`) | ❌ 待迁移 |

**关键发现**:
1. 实际改动仅 1 个函数 (`_ks_migration_significance`, ~20 行核心代码)
2. factor_significance.py 已完整支持 BH, E7 路径已用 BH
3. 全仓库 `bonferroni` 命中 35 行, 但默认生效的 bonferroni 路径仅 `pipelines_v2.py:333,344` 一处 (其余为测试/文档/选项)
4. 改动量估算: ~130 行 (核心代码 ~20 行 + 测试 ~40 行 + 文档 ~70 行), 涉及 8-9 个文件
5. unified_drift.py 滚动窗口循环内多次 KS 检验 (`_compute_rolling_structure_drift`, L109-157) 无多重比较校正, 是潜在的 BH 迁移候选 (M3 修正, 不再表述为"启发式融合")
6. factor_fingerprint 13 维指纹不存在多重比较 (大部分为描述性统计量, 非假设检验)

### 4.2 任务拆解

**T4.1 KS 迁移检测 BH 校正**
- 文件: [pipelines_v2.py](file:///f:/Coding/factor_pipeline/pipelines_v2.py) `_ks_migration_significance` (L236-359, M1 修正统一行号)
- 改动: `alpha_corrected = alpha / n_tests` → BH 步骤 (排序 p, `p*K/rank`, 累积 min)
- 接口扩展: `bonferroni_correction: True` → `correction_method='benjamini_hochberg'`
- 判定: `min(p_adj) < alpha`

**T4.2 测试更新**
- 文件: [tests/test_backtest/verify_fix1_manual.py](file:///f:/Coding/factor_pipeline/tests/test_backtest/verify_fix1_manual.py) (L7, L125-126)
- 改动: 校验 3 的 Bonferroni 公式改为 BH 公式
- 文件: [tests/manual/test_factor_significance_manual.py](file:///f:/Coding/factor_pipeline/tests/manual/test_factor_significance_manual.py) (L369-488)
- 改动: 已有 BH 测试, 新增 KS 迁移路径的 BH 测试

**T4.3 文档更新**
- [DECISIONS.md:51-86](file:///f:/Coding/factor_pipeline/DECISIONS.md) ADR-002: 状态改为"已演进", 新增 ADR-002a 或追加决策段
- [DECISIONS.md:1547](file:///f:/Coding/factor_pipeline/DECISIONS.md) TODO 勾选 `[x]`
- [CHANGELOG.md](file:///f:/Coding/factor_pipeline/CHANGELOG.md): 新增条目
- [CODE_WIKI.md:135, 1515](file:///f:/Coding/factor_pipeline/CODE_WIKI.md): 更新 KS 迁移路径描述
- [README.md:239](file:///f:/Coding/factor_pipeline/README.md) / [README.en.md:181](file:///f:/Coding/factor_pipeline/README.en.md): 改"Bonferroni 校正"为"BH FDR 校正"

**T4.4 ADR-002a 决策记录**
- 新增 ADR-002a: KS 迁移检测校正方法迁移 Bonferroni → BH
- 学术依据: Benjamini-Hochberg (1995) / Harvey-Liu-Zhu (2016)

### 4.3 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| BH 比 Bonferroni 宽松, 提高迁移检测敏感度 (更多迁移被确认) | 中 | 回归测试 Q3 验证集, 确认迁移率上升在可接受范围 |
| 接口扩展 `bonferroni_correction: bool` → `correction_method: str` 破坏向后兼容 | 中 | 保留 `bonferroni_correction` 参数作为 deprecated alias, 默认走 BH |
| BH 需要排序所有 p 值, 接口需返回所有 p_adj | 低 | 当前返回 `(is_significant, min_p_value, details)`, 扩展为返回 `min(p_adj)` |
| ADR-002 静默修改 vs 新增 ADR-002a | 低 | 推荐新增 ADR-002a, 保留 ADR-002 历史记录 |
| unified_drift.py 滚动窗口多次 KS 检验是否纳入 BH 迁移 | 低 | 当前不迁移 (T4 仅 KS 迁移路径), 单独立项评估; M3 修正后明确为潜在 BH 迁移候选 |

### 4.4 学术依据

| 主题 | 学术依据 | 状态 |
|------|---------|------|
| FDR 控制 | Benjamini-Hochberg (1995) Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing | 已在 factor_significance.py 引入, KS 路径待迁移 |
| 多重检验在金融 | Harvey-Liu-Zhu (2016) … and the Cross-Section of Expected Returns | 已在 EXECUTION_V2.5.0.md 引用 |
| Bonferroni 保守性 | Bonferroni (1936) Teoria statistica delle classi e calcolo delle probabilità | 已引入 (将被取代) |

---

## 5. 综合风险评估

| 风险类别 | 等级 | 影响任务 | 缓解措施 |
|----------|------|---------|---------|
| 全链路改造回归风险 | 高 | T2 | 分阶段实施, 每阶段全量回归, 流式/批量并存 |
| 小样本估计不稳定 (尾部/体制) | 高 | T1 | min_samples 配置保护, 不足时返回 NaN |
| CUSUM/BH 参数敏感 | 高 | T3, T4 | 自适应参数选择 + 回归测试 |
| 学术依据缺失 (Page/Hamilton/Nelsen) | 中 | T1, T3 | 实施时补 ADR + 引用 |
| 跨任务协同 (T2+T3) 复杂度 | 中 | T2, T3 | T3 先实现 batch 内部模拟流式, T2 完成后激活真流式 |
| 文档与代码状态脱节 (v2.6.0 教训) | 中 | 全部 | 实施前强制对照代码状态 (DECISIONS.md vs 实际) |

---

## 6. 推荐执行顺序与优先级

### 6.1 优先级矩阵

| 任务 | 优先级 | 改动量 | 收益 | 风险 | 依赖 |
|------|--------|--------|------|------|------|
| T4 BH-FDR | **P0** | ~130 行 (小) | 明确 (放宽假阳性控制) | 低 (回归测试可控) | 无 |
| T1 指纹扩展 | **P1** | ~600 行 (中) | 高 (诊断维度+7) | 中 (小样本不稳定) | 无 |
| T3 CUSUM | **P1** | ~400 行 (中) | 高 (流式变点检测) | 中 (参数敏感) | T2 (流式协同, 软依赖) |
| T2 流式 | **P2** | ~1500+ 行 (大) | 高 (基础设施) | 高 (全链路改造) | 无 (但 T3 真流式需 T2) |

### 6.2 推荐执行顺序

**阶段 1 (P0, 立即可做)**: T4 BH-FDR
- 改动最小, 收益明确, 无依赖
- 估算: 1-2 个 E 阶段 (类似 v2.6.0 E2 规模)

**阶段 2 (P1, 可并行)**: T1 指纹扩展 ∥ T3 CUSUM
- T1 与 T3 无依赖, 可并行实施
- T1 估算: 3-4 个 E 阶段 (尾部依赖 + 体制转换 + 路由接入 + 测试)
- T3 估算: 2-3 个 E 阶段 (CUSUM 实现 + KS 协同 + ADR)

**阶段 3 (P2, 长期)**: T2 流式处理
- 全链路改造, 分 5 个子阶段 (T2.1-T2.5)
- 估算: 5-8 个 E 阶段
- 与 T3 协同: T2.4 完成后激活 T3 真流式

### 6.3 与 v2.6.0 的衔接

v2.6.0 完成的 6 项目标函数 + Layer 3 显著性 + ThresholdDriftMonitor 为 v3.0.0 提供:
- **T3 基础设施**: ThresholdDriftMonitor.update() 是 CUSUM 扩展的最佳起点
- **T4 已部分完成**: factor_significance.py 已默认 BH, E7 已用 BH
- **T1 路由接入点**: `_get_multi_dim_pipeline_weights` 已识别只用 4 维, 扩展空间充足
- **T2 增量算法**: RollingOrthogonalizer 增量 Gram 已实现 (v2.5.0 O4.11), 待 API 暴露

---

## 7. 待确认事项

1. **T1 尾部依赖实现深度**: 完整 Copula 拟合 (Nelsen 2006) vs 简化 GPD shape (Pickands 1975)? 后者改动量更小
2. **T1 体制转换模型选择**: Hamilton (1989) Markov 两状态 vs 硬阈值 bull/bear 划分? 前者更严格但复杂
3. **T2 流式改造范围**: 全链路 (T2.1-T2.5) vs 仅正交化层 (T2.3)? 后者可作为最小可行版
4. **T3 CUSUM 实现方式**: 扩展 ThresholdDriftMonitor 添加 `mode='cusum'` vs 新建 `CUSUMDriftMonitor` 类?
5. **T4 BH 迁移是否新增 ADR-002a**: 推荐 ADR-002a (保留 ADR-002 历史), 用户确认
6. **v3.0.0 是否拆分为多个小版本**: T4 可作为 v2.7.0 (改动小), T1+T3 作为 v2.8.0, T2 作为 v3.0.0?

---

## 附录 A: 关键文件路径速查

### T1 指纹扩展
- [modules/factor_fingerprint/core/fingerprint.py](file:///f:/Coding/factor_pipeline/modules/factor_fingerprint/core/fingerprint.py) — 指纹核心, 扩展首选
- [modules/factor_fingerprint/core/classifier.py](file:///f:/Coding/factor_pipeline/modules/factor_fingerprint/core/classifier.py) — 分类器 (仅用 ar1)
- [modules/factor_fingerprint/core/health.py](file:///f:/Coding/factor_pipeline/modules/factor_fingerprint/core/health.py) — 含 `_evaluate_regime` (L1373, 体制敏感性, 非体制转换)
- [pipelines_v2.py](file:///f:/Coding/factor_pipeline/pipelines_v2.py) — `_get_multi_dim_pipeline_weights` (L96)

### T2 流式处理
- [pipelines_v2.py](file:///f:/Coding/factor_pipeline/pipelines_v2.py) — Pipeline 主流程
- [pipeline.py](file:///f:/Coding/factor_pipeline/pipeline.py) — v1.0 Pipeline
- [adapters.py](file:///f:/Coding/factor_pipeline/adapters.py) — OrthogonalizerAdapter (rolling 路径 docstring 声明未实现 L898)
- [modules/factor_orthogonalizer/rolling.py](file:///f:/Coding/factor_pipeline/modules/factor_orthogonalizer/rolling.py) — RollingOrthogonalizer (增量 Gram)
- [backtest/cached_data_loader.py](file:///f:/Coding/factor_pipeline/backtest/cached_data_loader.py) — 数据加载
- [modules/factor_imputer/core/imputers.py](file:///f:/Coding/factor_pipeline/modules/factor_imputer/core/imputers.py) — 6 个 imputer 全无 partial_fit
- [modules/factor_neutralizer/core/FactorNeutralizer.py](file:///f:/Coding/factor_pipeline/modules/factor_neutralizer/core/FactorNeutralizer.py) — Neutralizer (无状态, 最易改造)
- [modules/factor_adaptive_winsor/core/enhanced_transformers.py](file:///f:/Coding/factor_pipeline/modules/factor_adaptive_winsor/core/enhanced_transformers.py) — Winsor (需在线估计器)

### T3 CUSUM
- [pipelines_v2.py](file:///f:/Coding/factor_pipeline/pipelines_v2.py) — KS 迁移检测主入口 (L236-359, M1 修正统一行号)
- [backtest/unified_drift.py](file:///f:/Coding/factor_pipeline/backtest/unified_drift.py) — 滚动 KS (多次检验无校正, M3 修正) + EWMA 平滑
- [backtest/threshold_drift_monitor.py](file:///f:/Coding/factor_pipeline/backtest/threshold_drift_monitor.py) — EWMA 性能衰减流式监测, CUSUM 扩展起点
- [modules/factor_fingerprint/core/monitor.py](file:///f:/Coding/factor_pipeline/modules/factor_fingerprint/core/monitor.py) — 指纹历史 + enable_smooth_transition

### T4 BH-FDR
- [pipelines_v2.py:236-359](file:///f:/Coding/factor_pipeline/pipelines_v2.py) — `_ks_migration_significance` (待迁移, M1 修正统一行号)
- [backtest/factor_significance.py:410-458](file:///f:/Coding/factor_pipeline/backtest/factor_significance.py) — `_apply_correction` (M2 修正行号, 已默认 BH)
- [optimizer.py:834, L895](file:///f:/Coding/factor_pipeline/optimizer.py) — E7 已用 BH (m1 精确化行号)
- [DECISIONS.md:51-86](file:///f:/Coding/factor_pipeline/DECISIONS.md) — ADR-002 (待追加 ADR-002a)

---

## 附录 B: 学术依据完整清单

### 待引入 (v3.0.0 新增)
| 引用 | 任务 | 用途 |
|------|------|------|
| Page (1954) Continuous Inspection Schemes | T3 | CUSUM 序贯检验 |
| Brown-Durbin-Evans (1975) Techniques for Testing the Constancy of Regression Relationships over Time | T3 | CUSUMSQ 残差异方差检验 |
| Csörgő-Horváth (1997) Limit Theorems in Change-Point Analysis | T3 | 变点分析极限理论 |
| Andreou-Ghysels (2002) Detecting Multiple Breaks in Financial Market Volatility Dynamics (待进一步核实精确标题) | T3 | CUSUM 金融应用 |
| Hamilton (1989) A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle | T1 | Markov 体制转换 |
| Nelsen (2006) An Introduction to Copulas | T1 | 尾部依赖 Copula |
| Pickands (1975) Statistical Inference Using Extreme Order Statistics | T1 | GPD 极值理论 |
| Hill (1975) A Simple General Approach to Inference About the Tail of a Distribution | T1 | Hill 估计量 |
| Welford (1962) Note on a Method for Calculating Corrected Sums of Squares and Products | T2 | 在线均值/方差估计 |
| Benjamini-Hochberg (1995) Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing | T4 | FDR 控制 (部分已引入) |
| Harvey-Liu-Zhu (2016) … and the Cross-Section of Expected Returns | T4 | 多重检验在金融 (已引入) |

### 已引入 (v2.5.0/v2.6.0)
| 引用 | 任务 | 状态 |
|------|------|------|
| Belloni-Chernozhukov-Hansen (2014) PDS Lasso | T4 共享 | 已引入 (v2.5.0 Layer 3) |
| Roberts (1959) EWMA | T3 共享 | 已引入 (v2.6.0 E3) |
| Golub & Van Loan (2013) Matrix Computations | T2 共享 | 已引入 (v2.5.0 O4.11) |
| Bailey-López de Prado (2014) | T3 共享 | 已引入 (v2.6.0 E8) |

---

**文档版本**: v1.1
**完成日期**: 2026-07-04
**v1.0 → v1.1 修订**: 根据 review (架构 + 学术) 系统性修订

---

## 附录 C: v1.0 → v1.1 修订日志

### 架构 review 修订 (3 MAJOR + 5 MINOR + 4 NIT)

| 编号 | 级别 | 问题 | 修订位置 | 修订内容 |
|------|------|------|---------|---------|
| M1 | MAJOR | `_ks_migration_significance` 行号在文档中不一致 (§3.1 写 236-340, §4.1 写 315-359, 实际 236-359) | §0, §3.1, §4.1, §4.2 T4.1, 附录 A T3/T4 | 统一为 `pipelines_v2.py:236-359`, 涉及 5 处 |
| M2 | MAJOR | `_apply_correction` 行号错误 (文档 430-443, 实际方法定义 L410, 4 选项分支 L421-458) | §4.1 表格, 附录 A T4 | 改为 `factor_significance.py:410-458`, 并标注方法定义与分支位置 |
| M3 | MAJOR | unified_drift.py "启发式融合, 非 BH 目标范围" 表述不准确, 实际 `_compute_rolling_structure_drift` (L109-157) 在滚动窗口循环内执行多次 KS 检验且无多重比较校正 | §3.1 表格, §4.1 关键发现 #5, §4.3 风险表, 附录 A T3 | 明确指出"滚动窗口循环内多次 KS 检验无多重比较校正, 是潜在的 BH 迁移候选" |
| m1 | MINOR | optimizer.py 引用仅写 L895 | §4.1 表格, 附录 A T4 | 精确化为 `L834 (_validate_significance), L895 (BH 参数)` |
| m2 | MINOR | "rolling stub" 表述口语化 | §2.1 流式就绪度表, §2.2 T2.3, 附录 A T2 | 改为 "docstring 声明未实现" |
| m3 | MINOR | "实际生效代码仅一处" 表述不严谨 | §0 摘要表 T4, §4.1 关键发现 #3 | 改为 "默认生效的 bonferroni 路径仅一处" |
| m4 | MINOR | "0/2 新维度" 表述歧义 (维度 vs 维度类别) | §0 摘要表 T1 | 改为 "0/2 新维度类别" |
| m5 | MINOR | CUSUM 扩展未区分"性能衰减监测" vs "分布漂移监测" | §3.1 表格 EWMA 行 | 明确标注 EWMA 监测的是 score 性能衰减 (回测指标退化), CUSUM 扩展应区分两类监测目标 |
| n4 | NIT | T3 依赖标 "可选" 不够明确 | §6.1 优先级矩阵 | 改为 "软依赖" |

### 学术 review 修订 (3 INCORRECT + 1 NEEDS_VERIFICATION)

| 引用 | 问题 | 修订内容 |
|------|------|---------|
| Hamilton (1989) | 缺少 "and the Business Cycle" | 补全为 "A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle" (§1.4 学术依据表, §1.2 T1.2, 附录 B) |
| Brown-Durbin-Evans (1975) | 缺少 "over Time" | 补全为 "Techniques for Testing the Constancy of Regression Relationships over Time" (§3.3 T3.3, §3.4 学术依据表, 附录 B) |
| Benjamini-Hochberg (1995) | 缺少副标题 "A Practical and Powerful Approach to Multiple Testing" | 补全为 "Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing" (§4.4 学术依据表, 附录 B) |
| Andreou-Ghysels (2002) | 标题精确性存疑 | 标注 "待进一步核实精确标题" (§3.4 学术依据表, 附录 B) |
| Pickands (1975) | 标题首字母未大写 | 规范化为 "Statistical Inference Using Extreme Order Statistics" (附录 B) |
| Hill (1975) | 标题首字母未大写 | 规范化为 "A Simple General Approach to Inference About the Tail of a Distribution" (附录 B) |
| Welford (1962) | 标题不完整 | 补全为 "Note on a Method for Calculating Corrected Sums of Squares and Products" (附录 B) |

### 修订统计

- **MAJOR 修复**: 3/3 (M1, M2, M3)
- **MINOR 修复**: 5/5 (m1, m2, m3, m4, m5)
- **NIT 修复**: 1/4 (n4, n1/n2/n3 为非文档级问题)
- **学术标题补全**: 4 处 (Hamilton / Brown-Durbin-Evans / Benjamini-Hochberg / Andreou-Ghysels 标注待核实)
- **学术标题规范化**: 3 处 (Pickands / Hill / Welford 补全标题)
- **总修订位置**: ~16 处文档行

### v1.1 与 v1.0 一致性

- 任务范围 (4 项) 不变: T1/T2/T3/T4
- 优先级矩阵不变: T4 P0 / T1+T3 P1 / T2 P2
- 推荐执行顺序不变: T4 → T1 ∥ T3 → T2 (长期)
- 改动量估算不变: T1 ~600 / T2 ~1500+ / T3 ~400 / T4 ~130
- 学术依据核心引用不变 (仅标题补全)
- v1.1 仅修正表述准确性, 未改变任何方案决策

**下一步**: v3.0.0 ANALYSIS v1.1 完成, 等待用户确认是否进入 T4 (P0) 执行方案设计 (类似 v2.6.0 EXECUTION 阶段)
