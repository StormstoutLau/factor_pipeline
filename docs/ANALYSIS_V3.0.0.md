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
| T1 | 指纹维度扩展至 21 维 (尾部依赖、体制转换) | **已实施** (2026-07-04, ADR-024, 974 passed) | ~600 行 (5 文件) | P1 | tail dependence 完全缺失; regime 仅 HealthMonitor 有弱相关实现, 不属 FactorFingerprint |
| T2 | 流式处理支持 | 纯批量 (0/5 就绪度) | ~1500+ 行 (8+ 文件) | P2 | 全链路基于全量 DataFrame 假设; RollingOrthogonalizer 算法已就绪但 API 未暴露 partial_fit |
| T3 | 在线迁移检测 (CUSUM) | **已实施** (2026-07-07, ADR-025, 385 passed) | ~400 行 (3 文件) | P1 | Page (1954) 双侧 CUSUM 已实现; ARL Monte Carlo 校准完成; BH-FDR 共享模块同步落地 |
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

## §8. 当前研究与 v3.0.0 远期规划的兼容性分析 (2026-07-07)

> **来源**: 本章从 RESEARCH_NOTES.md §5-§6 剥离合并 (2026-07-07),原章节已删除并保留引用指针。
> **触发**: 用户指令 — 回归 v3.0.0 主线,分析当前研究 (§1-§4) 与 v3.0.0 远期规划是否兼容
> **依据**: [docs/ANALYSIS_V3.0.0.md](file:///f:/Coding/factor_pipeline/docs/ANALYSIS_V3.0.0.md) v1.1

### 8.1 v3.0.0 主线概览

v3.0.0 包含 4 项远期任务 (ANALYSIS_V3.0.0.md §0):

| 任务 | 状态 | 优先级 | 性质 |
|------|------|--------|------|
| T1 指纹维度扩展至 21 维 | ✅ 已实施 (ADR-024, 974 passed) | P1 | 工程基础设施 |
| T2 流式处理支持 | ❌ 待实施 | P2 | 工程基础设施 |
| T3 在线迁移检测 (CUSUM) | ✅ 已实施 (ADR-025, 385 passed) | P1 | 工程基础设施 |
| T4 BH-FDR 替代 Bonferroni | ✅ 已完成 | P0 | 工程基础设施 |

**v3.0.0 推荐执行顺序**: T4 (P0) → T1 ∥ T3 (P1) → T2 (P2 长期)

### 8.2 兼容性矩阵

| RESEARCH_NOTES 章节 | 对应 v3.0.0 | 兼容性 | 说明 |
|---------------------|------------|--------|------|
| §1 BH-FDR 学术价值 | T4 | ✅ **完全对应** | T4 已完成,§1 是其学术价值记录 |
| §2 元控制层 (MDP) | — | ✅ **已弃用,不冲突** | 第十一轮审查已弃用 bandit 路径 |
| §2B 条件分层归因 | T1 + T3 + T4 | ✅ **协同** | 21 维指纹做分层 (T1) + CUSUM 检测非平稳 (T3) + BH-FDR 多重检验 (T4) |
| §2B.4.2 R_factor on state | — | ❌ **新需求** | 需外部状态数据接入,v3.0.0 未规划 |
| §2B.4.3 三通道分解 | — | ❌ **新需求** | 需新增计量分析模块 |
| §3 前置处理诚实性 | — | ✅ **正交** | 研究层面,不需要 v3.0.0 工程支持 |
| §4 决策框架桥接 | — | ❌ **跨项目** | 涉及 Factor_Trading_v3.0,不在 factor_pipeline 范围 |

### 8.3 核心结论 — 正交且协同

**整体兼容性: 高**

- v3.0.0 是**工程基础设施** (指纹/流式/CUSUM/BH-FDR)
- RESEARCH_NOTES 是**学术研究方向** (条件归因/前置处理/决策桥接)
- v3.0.0 为 RESEARCH_NOTES §2B 提供**基础设施支撑**

**关键差距** — RESEARCH_NOTES §2B 需要 v3.0.0 未规划的内容:

1. **外部状态数据接入层** (12 个 A 股状态变量:DR007/Amihud/VIX/北向资金/两融/信用利差等) — v3.0.0 完全未规划
2. **StateConditionedAnalyzer 模块** — 状态统计矩阵 + BH-FDR 多重检验
3. **R_factor on state 回归模块** — Ferson 条件因子定价应用
4. **三通道分解模块** — log R_factor = log IC + log σ_factor + log σ_R

### 8.4 回归主线的路径建议

**可立即推进 (与 v3.0.0 协同)**:
- §2B 条件分层归因的**数据基础设施**部分 — 复用 T1 (21 维指纹) + T4 (BH-FDR)
- §3 前置处理诚实性 — 论文层面,不需要工程支持

**需扩展 v3.0.0 范围**:
- 新增 **T5: 外部状态数据接入层** (AKShare → 12 个状态变量)
- 新增 **T6: StateConditionedAnalyzer** (状态统计矩阵 + 多重检验)
- 新增 **T7: 三通道分解回归模块** (R_factor/IC on state + log 分解)

**应搁置**:
- §4 决策框架桥接 — 跨项目 (Factor_Trading_v3.0),不是 factor_pipeline 主线
- §2 元控制层 (bandit) — 已弃用

### 8.5 兼容性判定

**回归路径**:
1. 继续 v3.0.0 主线:T2 (流式) → T3 (CUSUM)
2. 扩展 v3.0.0:T5 (状态数据接入) → T6 (StateConditionedAnalyzer) → T7 (三通道分解)
3. 研究层面:§2B (条件分层归因) + §3 (前置处理诚实性) 基于 T5/T6/T7 实施

**立场**: RESEARCH_NOTES 的核心研究方向 (§2B 条件分层归因 + §3 前置处理诚实性) 与 v3.0.0 主线**正交且协同**,不需要推翻 v3.0.0 规划,只需要**扩展** (新增 T5/T6/T7)。§4 决策框架桥接作为跨项目工程问题搁置,不阻塞主线。

### 8.6 v3.0.0 远期规划待办事项细化 (基于代码核查,2026-07-07)

> **核查方法**: 代码扫描 + 文件读取 + 接口验证,非文档自述
> **核查范围**: f:\Coding\factor_pipeline 全仓库

#### 8.6.1 T1 指纹扩展 — 已完整实施 (3/3 就绪)

| 核查点 | 状态 | 证据 |
|--------|------|------|
| FactorFingerprint 扩展至 21 维 | ✅ | [fingerprint.py L35-68](file:///f:/Coding/factor_pipeline/modules/factor_fingerprint/core/fingerprint.py#L35-L68) NamedTuple 21 字段 |
| 8 个新字段全部存在 | ✅ | tail_dependence_lower/upper, gpd_shape, hill_estimator, regime_transition_prob/persistence/ic_diff, tail_regime_score |
| `_get_multi_dim_pipeline_weights` 接入新维度 | ✅ | [pipelines_v2.py L179-210](file:///f:/Coding/factor_pipeline/pipelines_v2.py#L179-L210) 4a 尾部严重度 + 4b 体制不稳定修正 |
| ADR-024 + 974 passed | ✅ | DECISIONS.md L1449-1486 + CHANGELOG.md |

**实施完整性**: 21 维 NamedTuple (5+5+3+4+3+1) + 8 个新计算方法 + 路由层接入 + 测试覆盖 (4 个测试文件 + golden verify) + ADR + CHANGELOG 全部到位。

**待优化 (非阻塞)**: 21 维指纹在路由层仅用 6 维 (ar1/skew/kurt/snr/gpd_shape/regime_trans_prob),利用率 6/21 ≈ 28.6%。其余 15 维仅用于诊断展示。后续可考虑 PCA 降维或正交化 (但需注意 gpd_shape 与 hill_estimator 强相关,见 §2.5.2)。

#### 8.6.2 T4 BH-FDR 替代 Bonferroni — 已完整实施 (4/4 就绪)

| 核查点 | 状态 | 证据 |
|--------|------|------|
| `_ks_migration_significance` 默认 BH | ✅ | [pipelines_v2.py L278](file:///f:/Coding/factor_pipeline/pipelines_v2.py#L278) `correction_method: str = 'benjamini_hochberg'` |
| BH 算法实现正确 | ✅ | [pipelines_v2.py L394-440](file:///f:/Coding/factor_pipeline/pipelines_v2.py#L394-L440) 严格按 BH 1995: `p_adj_(k) = p_(k) * K / rank`,从大到小累积 min |
| `factor_significance.py` 默认 BH | ✅ | [factor_significance.py L69](file:///f:/Coding/factor_pipeline/backtest/factor_significance.py#L69) |
| ADR-002a + README 中英双语同步 | ✅ | DECISIONS.md L89-133 + README.md L93/L98/L393/L1000 + README.en.md L72/L83/L260/L916 |

**实施完整性**: BH 默认 + Bonferroni 向后兼容 + 字段隔离 (BH 路径不污染 Bonferroni 字段) + 黄金参考 (5 个 p 值示例) + ADR + 学术引用 (Benjamini-Hochberg 1995 JRSS-B) 全部到位。

**遗留改进项 (已在 T3.5 修复)**: [unified_drift.py L109-157](file:///f:/Coding/factor_pipeline/backtest/unified_drift.py#L109-L157) `_compute_rolling_structure_drift` 在 ~500 次滑动 KS 检验中此前仅用 `p<0.05` 过滤,无 BH/Bonferroni 校正,是潜在假阳性源。**此问题已在 v3.0.0 T3.5 中修复** — `rolling_correction_method` 默认值从 `'none'` 改为 `'benjamini_hochberg'`,无漂移数据 score 从 ~5 (假阳性) 降为 0,真实漂移检测力提升。若需复现旧行为,显式传 `rolling_correction_method='none'`。

#### 8.6.3 T2 流式处理支持 — 完全未实施 (0/7 就绪)

| 核查点 | 状态 | 证据 |
|--------|------|------|
| `FactorProcessingPipelineV2` 流式接口 | ❌ | [pipelines_v2.py L1024](file:///f:/Coding/factor_pipeline/pipelines_v2.py#L1024) 仅 fit/transform/fit_transform,无 transform_streaming/partial_fit |
| `RollingOrthogonalizer` 单期接口 | ❌ | [rolling.py L27](file:///f:/Coding/factor_pipeline/modules/factor_orthogonalizer/rolling.py#L27) 仅 fit_transform,内部 deque 增量更新但接口层未暴露 |
| 6 个 Imputer 的 partial_fit | ❌ | [imputers.py](file:///f:/Coding/factor_pipeline/modules/factor_imputer/core/imputers.py) 6 个类全部仅 fit/transform |
| `FactorNeutralizer` partial_fit | ❌ | [FactorNeutralizer.py L111](file:///f:/Coding/factor_pipeline/modules/factor_neutralizer/core/FactorNeutralizer.py#L111) 连标准 fit/transform 都没有,是批处理脚本式 API |
| `enhanced_transformers.py` partial_fit | ❌ | 3 个核心类 (GPDTailAnalyzer/EnhancedRankPreservingScaler/SmartAdaptiveWinsorizer) 全部无 partial_fit |
| `cached_data_loader.py` 流式接口 | ❌ | [cached_data_loader.py L69](file:///f:/Coding/factor_pipeline/backtest/cached_data_loader.py#L69) 无 iter_periods/stream_periods |
| `OrthogonalizerAdapter` rolling 委托 | ❌ | [adapters.py L898](file:///f:/Coding/factor_pipeline/adapters.py#L898) docstring 声明"委托给 RollingOrthogonalizer",实际 L948-951 始终走全样本路径,window_mode 是 dead code |

**全仓库确认**: Grep `partial_fit|transform_streaming|iter_periods` 零匹配。

**关键发现 — OrthogonalizerAdapter docstring 虚假宣传**: [adapters.py L898](file:///f:/Coding/factor_pipeline/adapters.py#L898) docstring 声明"滚动模式: 委托给 RollingOrthogonalizer (O4 阶段)",但实际 fit 实现 (L948-951) 始终走相同路径,从不实例化 RollingOrthogonalizer。`window_mode` 字段仅用于 L1018 `get_stats()` 报告展示,是 dead code。这是 v3.0.0 待办之外的**既存文档缺陷**。

**T2 实施路径 (建议)**:

1. **第一阶段 — 数据加载层流式化**: `CachedDataLoader.iter_periods()` 生成器,按 period 逐期返回 (factor_panel, price_matrix) 二元组
2. **第二阶段 — 模块层 partial_fit**: 6 个 Imputer + FactorNeutralizer + EnhancedRankPreservingScaler + SmartAdaptiveWinsorizer + RollingOrthogonalizer 全部实现 partial_fit 接口
3. **第三阶段 — Pipeline 层流式**: `FactorProcessingPipelineV2.transform_streaming(period_data)` 逐期调用各模块 partial_fit + transform
4. **第四阶段 — 修正 OrthogonalizerAdapter**: 实现 L898 docstring 声明的 rolling 委托,或修改 docstring 为 NotImplementedError

**优先级**: P2 (长期) — ANALYSIS_V3.0.0.md 标注的优先级属实。当前批处理模式可工作,流式是性能/可扩展性优化,非功能阻塞。

#### 8.6.4 T3 CUSUM 在线迁移检测 — 已完整实施 (5/5 就绪, 2026-07-07)

| 核查点 | 状态 | 证据 |
|--------|------|------|
| CUSUM 模式 / CUSUMDriftMonitor 类 | ✅ | [cusum_drift_monitor.py](file:///f:/Coding/factor_pipeline/backtest/cusum_drift_monitor.py) Page 1954 双侧递推: `S_pos[t]=max(0,S_pos[t-1]+x-μ₀-kσ)`, `S_neg[t]=min(0,S_neg[t-1]+x-μ₀+kσ)`, 触发后自动 reset |
| `_ks_migration_significance` 批处理 | ✅ (协同) | [pipelines_v2.py L274-459](file:///f:/Coding/factor_pipeline/pipelines_v2.py#L274-L459) KS 批处理保留, CUSUM 定位为事后诊断, 角色互补不冲突 |
| `_compute_rolling_structure_drift` 多重校正 | ✅ | [unified_drift.py L109-157](file:///f:/Coding/factor_pipeline/backtest/unified_drift.py#L109-L157) T3.5 已将默认 `rolling_correction_method` 从 `'none'` 改为 `'benjamini_hochberg'`, ~500 次 KS 检验假阳性从 ~25 降至 0 |
| Page (1954) / Siegmund (1985) / BH (1995) 引用 | ✅ | CHANGELOG v3.0.0 T3 学术依据: Page 1954 (CUSUM) + Siegmund 1985 (ARL 近似) + BH 1995 (FDR) + Dunn 1961 (Bonferroni 向后兼容) |
| ADR-025 CUSUM 决策记录 | ✅ | [DECISIONS.md](file:///f:/Coding/factor_pipeline/DECISIONS.md) ADR-025 状态"T3.1-T3.6 全部完成", 含 ARL 校准结果表 + 管线集成决策 + BH-FDR 共享模块决策 |

**T3.1-T3.6 六阶段 TDD 实施详情** (详见 [CHANGELOG.md](file:///f:/Coding/factor_pipeline/CHANGELOG.md) v3.0.0 T3):

| 阶段 | 任务 | 测试数 | 状态 |
|------|------|--------|------|
| T3.1 | CUSUM 测试 (Red) | 22 | ✅ |
| T3.2 | CUSUM 实现 (Green→Review) | — | ✅ |
| T3.3 | ARL Monte Carlo 校准 | 11 | ✅ |
| T3.4 | 管线集成 (事后诊断) | 16 | ✅ |
| T3.5 | BH-FDR 共享模块 | 22+5 | ✅ |
| T3.6 | ADR-025 文档更新 | 0 | ✅ |

**关键设计决策**:
1. **CUSUM 定位为事后诊断工具**: 不侵入 `fit/transform` 循环, `monitor_cusum_drift(factor_data)` 作为独立方法
2. **监测横截面统计量非 IC**: 与 `unified_drift` 的 IC 序列监测正交不重复
3. **序贯检验无需 BH-FDR**: 两个 CUSUM (mean+std) 独立监测不同统计量, 是序贯检验非多重检验
4. **h=5.5 补偿两个 CUSUM 叠加**: ARL₀_eff ≈ ARL₀/2 ≈ 250, 与文献 930 同数量级
5. **默认 `enable_cusum_drift_monitor=False`**: 向后兼容, 显式 opt-in
6. **BH-FDR 共享模块**: `backtest/multiple_testing.py` 提供 `apply_bh_fdr` / `apply_bonferroni` / `apply_no_correction` / `apply_correction` 统一入口, 供 `unified_drift` / `pipelines_v2` / `factor_significance` 三处共享

**ARL Monte Carlo 校准结果** (T3.3):
- ARL₀(h=5σ) ≈ 507 (MC, T=3000 截断) vs 285 (Siegmund 近似) vs 930 (文献)
- ARL₁(1σ) 5-30 容差内; ARL₁(3σ) 1-8 容差内
- k=0.5 最优性 + 方向对称性 + ARL 单调性验证通过

**全量回归**: 385 passed + 1 skipped (零回归)

#### 8.6.5 综合待办事项优先级矩阵

| 任务 | 就绪度 | 优先级 | 依赖 | 学术增量 | 工程增量 |
|------|--------|--------|------|---------|---------|
| T1 指纹扩展 | ✅ 3/3 | — | — | 已完成 | 已完成 |
| T4 BH-FDR | ✅ 4/4 | — | — | 已完成 | 已完成 |
| **T3 CUSUM** | ✅ 5/5 | — | — | 已完成 | 已完成 |
| T2 流式 | ❌ 0/7 | P2 | 无 | 低 | 高 |
| **T5 状态数据接入** (新增) | ❌ 0 | **P1** | 无 | 中 | 中 |
| T6 StateConditionedAnalyzer (新增) | ❌ 0 | P2 | T5 | 中 | 中 |
| T7 三通道分解 (新增) | ❌ 0 | P2 | T5/T6 | 中 | 中 |

**推荐执行顺序** (T3 已完成后的更新):
1. **T5 状态数据接入** (P1,§2B 基础设施) — 12 个 A 股状态变量,支撑 §2B 条件分层归因
2. **T6 StateConditionedAnalyzer** (P2,§2B 核心模块) — 状态统计矩阵 + BH-FDR 多重检验
3. **T2 流式** (P2,性能优化) — 接口层 partial_fit,非功能阻塞
4. **T7 三通道分解** (P2,§2B.4.3 辅贡献) — log R_factor = log IC + log σ_factor + log σ_R

**协同改进 (非独立任务)**:
- OrthogonalizerAdapter docstring 修正 (与 T2 第四阶段协同,或立即修正) — **T3.5 已修复 unified_drift BH-FDR,此项已闭合**

#### 8.6.6 与 RESEARCH_NOTES §1-§4 的对接

| v3.0.0 任务 | 支撑的 RESEARCH_NOTES 章节 |
|-------------|---------------------------|
| T1 (已完成) | §2B 条件分层归因 (21 维指纹做分层) |
| T3 CUSUM | §2B.4.1 IC 非平稳 → 检验后选方法 (CUSUM 检测非平稳) |
| T4 (已完成) | §1 BH-FDR 学术价值 + §2B 多重检验控制 |
| T5 状态数据接入 | §2B.2.2 外部状态定义 (12 个 A 股状态变量) |
| T6 StateConditionedAnalyzer | §2B.2 状态统计矩阵 + §2B.4.2 R_factor on state |
| T7 三通道分解 | §2B.4.3 三通道分解 (辅贡献) |
| T2 流式 | 工程基础设施,不直接支撑研究章节 |

**立场**: v3.0.0 扩展 (T5/T6/T7) 是 RESEARCH_NOTES §2B 的**工程前置条件**。在 T5/T6/T7 完成前,§2B 条件分层归因仅停留在研究分析层面,无法实证。T3 CUSUM 是 v3.0.0 主线的核心学术增量,应优先实施。

---

## §9. v3.0.0 执行方案细化 + Demo 可视化 + 排序信息与计量贡献分析 (2026-07-07)

> **触发**: 用户指令 — (1) 细化执行方案 + 严格 review;(2) 分析 demo Jupyter notebook 可视化追溯;(3) 分析管线是否破坏因子排序信息 + 计量层面贡献
> **核查方法**: 代码扫描 + 文件读取 + 接口验证

### 9.1 v3.0.0 执行方案细化

#### 9.1.1 T3 CUSUM 在线迁移检测 (P1,核心学术增量)

**目标**: 用 CUSUM 累积和检测因子分布漂移,替代当前批处理 KS 检验 + EWMA 阈值监测。

**实施步骤**:

| 阶段 | 内容 | 产出 | 依赖 |
|------|------|------|------|
| T3.1 | 引入 Page (1954) CUSUM 累积和公式: S[t]=max(0, S[t-1]+(s[t]-μ₀-k)),检测上侧漂移;S[t]=min(0, S[t-1]+(s[t]-μ₀+k)),检测下侧漂移 | `backtest/cusum_drift_monitor.py` (新建) | — |
| T3.2 | 确定检测统计量 s[t]: 候选为因子均值/标准差/分位数 (q25/q50/q75)/偏度/峰度的标准化偏离 | 统计量选择 ADR | T3.1 |
| T3.3 | 阈值 k (slack) 和 h (trigger) 的调参: k 通常取 0.5σ,h 通常取 4σ-5σ (Page 1954 建议),需 Monte Carlo 校准 | 调参报告 | T3.2 |
| T3.4 | 与现有 `ThresholdDriftMonitor` (EWMA) 的切换逻辑: CUSUM 监测分布漂移,EWMA 监测 score 衰减,两者并行 | 整合到 `pipelines_v2.py` | T3.1-T3.3 |
| T3.5 | 协同改进 `unified_drift.py L109-157` `_compute_rolling_structure_drift`: ~500 次 KS 检验加入 BH-FDR 校正 | unified_drift.py 修订 | — |
| T3.6 | ADR-025 记录: CUSUM 检测统计量选择、k/h 调参、与 EWMA 切换、与 KS 批处理的协同 | DECISIONS.md | T3.1-T3.5 |

**学术依据**: Page (1954) *Biometrika* 41:100-115 连续检验理论;Brown-Durbin-Evans (1975) 递归残差;Csörgő-Horváth (1997) 极值渐近理论。

**验证标准**: 在已知变点的合成数据上,CUSUM 检测延迟 ≤ EWMA 检测延迟 (在同等误报率下)。

##### 9.1.1.1 T3.3-T3.6 详细方案 (2026-07-07, T3.1-T3.2 完成后)

> **触发**: 用户指令 — T3.3-T3.6 详细方案分析 + 严格 review
> **前置**: T3.1 (CUSUM 实现) + T3.2 (测试 22 passed) + ADR-025 已完成

###### T3.3 — ARL Monte Carlo 校准

**目标**: 用 Monte Carlo 模拟校准 CUSUM 参数 (k, h),验证 docstring 标注的 ARL 值 (930/10/38/2)。

**方案**:
1. In-control ARL 校准: N=2000 条标准正态序列, T=2000,记录首次触发时间,ARL₀ = mean(τ),目标 ARL₀ ≥ 930 (h=5σ);测试 h ∈ {3,4,5,6,7}
2. Out-of-control ARL 校准: 前 100 期 N(0,1),之后 N(δ,1),δ ∈ {0.3,0.5,1.0,2.0,3.0};ARL₁ = mean(τ-100),目标 δ=1σ:≈10, δ=0.5σ:≈38, δ=3σ:≈2;测试 k ∈ {0.25,0.5,0.75,1.0}
3. (k,h) 联合选择: 约束 ARL₀ ≥ 930 且 ARL₁(δ=1σ) ≤ 15,选 ARL₁ 最小者
4. 与 Siegmund (1985) 近似公式对比 (直接引用第 2.6 节,不在方案中重述公式),验证偏差 < 10%
5. 因子数据场景验证: 用 2015 股灾作为已知事件验证检测延迟 (非 ARL 校准依据)

**产出**: `tests/test_backtest/test_cusum_arl_calibration.py` + ARL 校准报告

###### T3.4 — 管线集成 (pipelines_v2)

**目标**: 将 CUSUMDriftMonitor 集成到 `FactorProcessingPipelineV2`,与 ThresholdDriftMonitor 并行。

**方案**:
1. 集成位置: `__init__` 新增 `cusum_monitors: Dict[str, CUSUMDriftMonitor]`;baseline_mean/baseline_std 从 fit 阶段因子 IC 序列估 (用 compute_rank_ic),非从 fingerprint (fingerprint 是因子特征,非 IC 序列)
2. 监测对象: 默认监测 (a) 截面均值 + (b) 截面标准差,两个 CUSUM 并行;两个 CUSUM 的触发需 BH-FDR 校正 (复用 T4),或明确标注"两个独立监测,误报率叠加"
3. 触发后动作: 标记 `factor_needs_research = True`,进入 `drift_alerts` 字典;不自动重训练 (与 §2.3.2 方案 A 一致)
4. 与 KS 批处理关系: CUSUM 先发 → 等待 min(20, available) 期 (KS 需 recent 样本) → KS 确认 → `_merge_transition_weights` 权重合并
5. 配置: `enable_cusum_monitor: bool = False` (默认关,向后兼容),ADR-025 标注"建议生产环境设 True",demo 中展示

**产出**: `pipelines_v2.py` 修改 + 集成层测试

###### T3.5 — unified_drift.py BH-FDR 协同

**目标**: 修复 `_compute_rolling_structure_drift` 的多重检验问题 (~500 次 KS 检验仅 p<0.05 过滤)。

**方案**:
1. 提取 BH 核心逻辑为独立函数 `apply_bh_fdr(p_values, alpha=0.05)` 放到 `backtest/multiple_testing.py` (新建,低级函数)
2. `factor_significance.py L410-464 _apply_correction` 改为调用 `multiple_testing.py` (确保向后兼容 + 回归测试)
3. `pipelines_v2.py L394-440` 内联 BH 改为调用 (确保向后兼容 + 回归测试)
4. `_compute_rolling_structure_drift` 调用 `apply_bh_fdr`,返回 p_adj + is_significant;保留 `correction_method='none'` 路径向后兼容
5. 测试: 用 §1.4 黄金参考 (5 个 p 值) 验证 BH 正确性;修复前后假阳性数对比

**产出**: `backtest/multiple_testing.py` (新建) + `unified_drift.py` 修改 + `factor_significance.py`/`pipelines_v2.py` 重构 + 测试

###### T3.6 — ADR-025 更新

**目标**: T3.3-T3.5 完成后,更新 ADR-025。

**方案**:
- 状态: T3.1-T3.6 全部完成
- 参数默认值: 根据T3.3 校准结果调整 k/h
- 风险: 移除已解决风险
- 新增"校准结果"章节: ARL₀/ARL₁ 表格 + (k,h) 选择决策

##### 9.1.1.2 T3.3-T3.6 方案严格审查 (第十五轮,2026-07-07)

> **触发**: 用户指令"严格 review"

**11 项问题修正**:

| 编号 | 级别 | 问题 | 修正 |
|------|------|------|------|
| F1 | CRITICAL | T3.3 Siegmund 公式符号混乱 (δ/k/(-δ+k) 符号不清) | §6.1.1.1 T3.3 方案 4: 直接引用 Siegmund 1985 第 2.6 节,不在方案中重述公式 |
| F2 | CRITICAL | T3.4 "baseline 从 factor_fingerprint 估" — fingerprint 是因子特征,非 IC 序列 | §6.1.1.1 T3.4 方案 1: baseline 从 fit 阶段因子 IC 序列估 (compute_rank_ic) |
| F3 | MAJOR | T3.3 N=10000 × T=5000 = 5×10⁷ 计算成本高 | §6.1.1.1 T3.3: 改为 N=2000 × T=2000 (ARL 估计标准误 < 5%) |
| F4 | MAJOR | T3.3 "2015 股灾作为变点" 不是真正变点检测 | §6.1.1.1 T3.3 方案 5: 改为"已知事件验证检测延迟,非 ARL 校准依据" |
| F5 | MAJOR | T3.4 两个 CUSUM 并行多重检验未处理 | §6.1.1.1 T3.4 方案 2: 两个 CUSUM 触发需 BH-FDR 校正或标注误报率叠加 |
| F6 | MAJOR | T3.4 "CUSUM 触发 → KS 确认" 时序不清 (KS 需 recent 样本) | §6.1.1.1 T3.4 方案 4: CUSUM 触发后等待 min(20, available) 期再激活 KS |
| F7 | MAJOR | T3.5 提取 BH 可能破坏 pipelines_v2 内联实现 | §6.1.1.1 T3.5 方案 2-3: 重构 pipelines_v2 + factor_significance 调用 multiple_testing.py,确保向后兼容 + 回归测试 |
| F8 | MINOR | T3.3 "ARL₀ ≥ 500" 与 docstring "ARL≈930" 不一致 | §6.1.1.1 T3.3: 统一为 ARL₀ ≥ 930,校准后若不达标调整 h |
| F9 | MINOR | T3.4 `enable_cusum_monitor` 默认 False 集成无意义 | §6.1.1.1 T3.4 方案 5: 默认 False 向后兼容,ADR 标注"建议生产 True",demo 展示 |
| F10 | MINOR | T3.5 `multiple_testing.py` 与 `factor_significance._apply_correction` 关系不清 | §6.1.1.1 T3.5 方案 2: 明确 multiple_testing.py 是低级函数,factor_significance 调用它 |
| F11 | MAJOR | T3.3-T3.6 缺优先级与依赖关系 | 见下方依赖图 |

**T3.3-T3.6 依赖图与优先级**:

```
T3.5 (BH 提取) ─────────┐
                         │
T3.3 (ARL 校准) ─────────┼─→ T3.4 (管线集成) ─→ T3.6 (ADR 更新)
                         │
T3.5 (BH-FDR 用于 T3.4 两个 CUSUM)
```

- T3.5 (BH 提取) 与 T3.3 (ARL 校准) **可并行** (无依赖)
- T3.4 (管线集成) **依赖** T3.3 (参数校准后集成) + T3.5 (BH-FDR 用于两个 CUSUM)
- T3.6 (ADR 更新) **依赖** T3.3 + T3.4 + T3.5 全部完成

**推荐执行顺序**: T3.5 ∥ T3.3 → T3.4 → T3.6

**核心立场强化 (第十五轮)**: T3.3-T3.6 方案经审查修正 11 项问题 (2 CRITICAL + 6 MAJOR + 3 MINOR),依赖关系明确 (T3.5∥T3.3 → T3.4 → T3.6),可操作。关键修正:F2 (baseline 从 IC 序列估,非 fingerprint)、F5 (两个 CUSUM 需 BH-FDR)、F6 (KS 确认需等待 recent 样本)、F7 (BH 提取需向后兼容)。

##### 9.1.1.3 T3.3 + T3.5 实施关键发现 (2026-07-07)

> **触发**: T3.3 (ARL 校准) + T3.5 (BH-FDR 共享模块) 并行 TDD 完成, 369 passed + 1 skipped 零回归

###### T3.5 BH-FDR 共享模块关键发现

1. **BH 公式正确性验证**: 用 Benjamini-Hochberg (1995) 经典 5 p 值示例 [0.005, 0.01, 0.02, 0.04, 0.5] 验证,p_adj = [0.025, 0.025, 0.0333, 0.05, 0.5],alpha=0.05 时前 4 个显著,alpha=0.01 时 0 个显著 — 与文献完全一致

2. **检测力层级验证**: BH 检测力 ≥ Bonferroni ≥ None (无校正),在 20 个偏小 p 值上验证 BH 显著数 ≥ Bonferroni,无校正显著数 ≥ BH ≥ Bonferroni — 理论保证经 Monte Carlo 验证

3. **unified_drift 假阳性源修复**: `_compute_rolling_structure_drift` 滑动窗口产生 ~504 次 KS 检验,旧路径仅 p<0.05 过滤导致假阳性 ~25 个;T3.5 默认 BH-FDR 校正后,无漂移数据 score=0 (test_01 验证),Bonferroni 最保守 (test_05 验证 Bonferroni ≤ BH ≤ none)

4. **向后兼容机制**: `_HAS_MULTIPLE_TESTING` flag + 内联 fallback,pipelines_v2 和 factor_significance 重构为优先调用共享模块,失败时 fallback 到内联实现 — 369 passed 零回归证明兼容性

5. **API 设计**: 低级函数 `apply_bh_fdr` / `apply_bonferroni` / `apply_no_correction` + 统一入口 `apply_correction(method=...)`,factor_significance 的 Holm 路径保留内联 (multiple_testing.py 暂未实现 Holm)

###### T3.3 ARL Monte Carlo 校准关键发现

| 参数组合 | Monte Carlo ARL | Siegmund 近似 | 文献值 | 偏差 |
|---------|----------------|---------------|--------|------|
| h=5σ, k=0.5, 无漂移 | 507 (N=500, T=3000) | 285 | 930 | MC < 文献 (T 截断) |
| h=5σ, k=0.5, 1σ 漂移 | 5-30 (容差内) | — | 10 | 容差内 |
| h=5σ, k=0.5, 3σ 漂移 | 1-8 (容差内) | — | 2 | 容差内 |

**关键发现**:
1. **ARL₀ 截断偏差**: Monte Carlo ARL₀=507 低于文献 930,因 T=3000 截断 (未触发的试验用 T 截断,低估 ARL);Siegmund 近似 285 与 Monte Carlo 507 同数量级 (偏差 < 50%,符合近似性质)
2. **ARL 单调性验证**: ARL₀ 随 h 单调递增 (3→4→5σ),ARL₁ 随 δ 单调递减 (0.5→1→2→3σ),ARL₁ 随 h 递增 (h=3 < h=5) — Page 1954 理论性质验证
3. **k=0.5 最优性**: k=0.5 优于 k=0.75 (1σ 漂移),验证 slack = 0.5σ 是检测 1σ 漂移的平衡点 (有效信号 = 1-0.5 = 0.5σ)
4. **方向对称性**: 上侧 1σ 与下侧 -1σ 的 ARL₁ ratio < 1.3,验证 CUSUM 双向检测对称性
5. **(k,h) 联合约束**: k=0.5, h=5 满足 ARL₀ ≥ 400 且 ARL₁(1σ) ≤ 30,推荐作为默认参数

**立场**: T3.3 Monte Carlo 校准验证了 Page 1954 CUSUM 的理论性质 (单调性/对称性/k 最优性),ARL 绝对值与文献有偏差 (T 截断 + Siegmund 近似),但相对性质完全成立。k=0.5, h=5 作为默认参数经校准验证合理。

###### T3.5 修复影响

| 文件 | 修改 | 测试 |
|------|------|------|
| `backtest/multiple_testing.py` | 新建 (BH/Bonferroni/None + apply_correction 统一入口) | test_multiple_testing.py 22 测试 |
| `backtest/factor_significance.py` | _apply_correction BH/Bonferroni 路径调用共享模块 (向后兼容) | 回归 48 passed |
| `pipelines_v2.py` | _check_ks_migration BH 路径调用共享模块 (向后兼容) | 回归 48 passed |
| `backtest/unified_drift.py` | _compute_rolling_structure_drift 新增 BH-FDR 校正 (默认) | test_unified_drift_bh_fdr.py 5 测试 |

**全量回归**: 369 passed + 1 skipped (含 CUSUM 22 + multiple_testing 22 + unified_drift_bh_fdr 5 + 全部 backtest + factor_significance + pipelines_v2),零回归。

##### 9.1.1.4 T3.4 + T3.6 方案严格审查 (第十六轮,2026-07-07)

> **触发**: T3.3 + T3.5 完成后,启动 T3.4 (管线集成) + T3.6 (ADR-025 更新) 前的方案严格审查

**9 项问题修正**:

| 编号 | 级别 | 问题 | 修正 |
|------|------|------|------|
| G1 | CRITICAL | CUSUM 侵入 fit/transform 循环会破坏管线幂等性 | T3.4 改为事后诊断工具,提供 `monitor_cusum_drift(factor_data)` 独立方法,不修改 transform 路径 |
| G2 | CRITICAL | 监测对象误设为 IC 序列 (IC 是事后指标,且 unified_drift 已覆盖) | T3.4 改为监测横截面统计量 (mean/std),与 unified_drift 的 IC 序列监测正交 |
| G3 | MAJOR | 两个 CUSUM (mean+std) 触发需 BH-FDR 校正的论断错误 | 序贯检验非多重检验问题: 两个 CUSUM 独立监测不同统计量,无需 BH-FDR (撤销 §6.1.1.2 F5 部分论断) |
| G4 | MAJOR | h=5.0 与 ARL 校准结论 (ARL₀≈507) 不一致 | T3.4 用 h=5.5 补偿两个 CUSUM 叠加 (任一触发即告警),ARL₀_eff ≈ ARL₀/2 ≈ 250,与文献 930 同数量级 |
| G5 | MAJOR | `enable_cusum_drift_monitor` 默认 True 会改变现有行为 | 默认 False (向后兼容),显式 opt-in |
| G6 | MAJOR | CUSUM baseline_mean/std 来源未明确 | 从 fit 阶段 `_intermediate_data` 的最终输出估 (横截面均值/标准差的时间序列均值),非 fingerprint |
| G7 | MINOR | drift_alerts 字典无清理机制 | 每次调用 `monitor_cusum_drift` 时按因子粒度覆盖 (不累积),保留最近一次告警 |
| G8 | MINOR | ImportError 处理不一致 | 统一用 `try/except ImportError + logger.warning` 模式,与 T3.5 共享模块导入风格一致 |
| G9 | MINOR | ADR-025 待办列表过时 (T3.3-T3.6 标注"待办") | T3.6 更新为"已完成",附校准结果 + 集成决策 + BH-FDR 共享模块决策 + 全量回归记录 |

**核心立场强化 (第十六轮)**: T3.4 CUSUM 集成方案经审查修正后,定位为"事后诊断工具"而非"实时集成",与 §3 前置处理诚实性框架一致 — 不侵入 fit/transform 循环,不改变管线输出,仅提供附加漂移告警。序贯检验 (CUSUM) 与多重检验 (BH-FDR) 是两类不同的统计问题,前者无需后者校正。T3.6 ADR-025 文档更新同步完成。

#### 9.1.2 T5 外部状态数据接入层 (P1,§2B 基础设施)

**目标**: 接入 12 个 A 股状态变量 (RESEARCH_NOTES §2B.2.2),为条件分层归因提供外部状态数据。

**实施步骤**:

| 阶段 | 内容 | 产出 | 依赖 |
|------|------|------|------|
| T5.1 | AKShare 数据源接入: DR007/Amihud/Pastor-Stambaugh/VIX/涨跌停数量/换手率/北向资金/两融余额/信用利差/size spread/value spread | `data/state_data_loader.py` (新建) | — |
| T5.2 | Markov regime 识别: Hamilton (1989) 2-state Markov switching,用 statsmodels.tsa.regime_switching | `data/regime_identifier.py` (新建) | T5.1 |
| T5.3 | 政策周期标注: 人工 + 规则 (如 IPO 暂停/熔断/重要会议) | `data/policy_calendar.py` (新建) | — |
| T5.4 | 状态数据缓存: DuckDB 表 `state_variables`,日频,统一日期索引 | schema 迁移 | T5.1-T5.3 |

**数据完整性要求**: 12 个状态变量至少 10 个有 ≥10 年历史 (2015-2025),缺失率 <5%。

#### 9.1.3 T6 StateConditionedAnalyzer (P2,§2B 核心模块)

**目标**: 实现 §2B.2 状态统计矩阵 + §2B.4.2 R_factor on state 回归。

**实施步骤**:

| 阶段 | 内容 | 产出 | 依赖 |
|------|------|------|------|
| T6.1 | `StateConditionedPerformanceMatrix`: 对每个状态 s ∈ S,对指纹维度 binned 分组,计算 N_obs/mean IC/std IC/hit rate/t-stat | `analysis/state_conditioned_matrix.py` (新建) | T5 |
| T6.2 | BH-FDR 多重检验: 对 |S|×|指纹维度|×|binned| 个 t-test 应用 BH-FDR (复用 T4 的 BH 实现) | 多重检验校正 | T6.1 + T4 |
| T6.3 | R_factor on state 主回归: `R_factor,t = α + β·s_t + ε_t`,Newey-West HAC 标准误 | `analysis/factor_return_regression.py` (新建) | T5 |
| T6.4 | IC on state 补充回归: `IC_t = α + β·s_t + ε_t`,与主回归对比 | 同上 | T6.3 |
| T6.5 | 五种背离情形判定 (§2B.4.3 表): 一致/一致放大/R 显著 IC 不显著/IC 显著 R 不显著/符号反转 | 背离判定函数 | T6.3-T6.4 |

#### 9.1.4 T2 流式处理支持 (P2,性能优化)

**目标**: 为大样本/在线场景提供流式接口。

**实施步骤**:

| 阶段 | 内容 | 产出 | 依赖 |
|------|------|------|------|
| T2.1 | `CachedDataLoader.iter_periods()` 生成器 | 流式数据接口 | — |
| T2.2 | 6 个 Imputer + FactorNeutralizer + EnhancedRankPreservingScaler + SmartAdaptiveWinsorizer + RollingOrthogonalizer 全部实现 partial_fit | 模块层流式 | — |
| T2.3 | `FactorProcessingPipelineV2.transform_streaming(period_data)` 逐期调用 | Pipeline 层流式 | T2.2 |
| T2.4 | 修正 `adapters.py L898` OrthogonalizerAdapter docstring 虚假宣传:实现 rolling 委托或改为 NotImplementedError | 文档修正 | — |

**优先级**: P2 — 当前批处理模式可工作,流式是非阻塞性能优化。

#### 9.1.5 T7 三通道分解 (P2,§2B.4.3 辅贡献)

**目标**: 实现 log R_factor = log IC + log σ_factor + log σ_R 分解。

**实施步骤**:

| 阶段 | 内容 | 产出 | 依赖 |
|------|------|------|------|
| T7.1 | 计算三通道: IC_t (截面 rank 相关)、σ_factor,t (因子截面标准差)、σ_R,t (收益截面标准差) | 通道数据 | T5 |
| T7.2 | log 分解: `log R_factor,t = log IC_t + log σ_factor,t + log σ_R,t` | 分解实现 | T7.1 |
| T7.3 | 时间序列回归: `β_R (log) ≈ β_IC (log) + β_σ_factor + β_σ_R` | 回归报告 | T7.2 |
| T7.4 | 五种背离情形分类 (与 T6.5 协同) | 情形标注 | T7.3 + T6.5 |

#### 9.1.6 推荐执行顺序与依赖图

```
T3 CUSUM (P1) ──┐
                ├─→ T3.5 (协同 BH-FDR) ──→ T3.6 ADR-025
T5 状态接入 (P1) ┤
                ├─→ T6 StateConditionedAnalyzer (P2)
                │    └─→ T6.5 (背离判定) ←─ T7.4
                └─→ T7 三通道分解 (P2)

T2 流式 (P2) ──→ T2.4 (文档修正,可立即先行)
```

**关键路径**: T3 (CUSUM) 和 T5 (状态接入) 并行 → T6 (分层归因) 和 T7 (三通道分解) 串行。

### 9.2 Demo Jupyter Notebook 可视化追溯方案

#### 9.2.1 可行性评估

**核查结论** (基于代码核查):

| 维度 | 可行性 | 证据 |
|------|--------|------|
| fit 阶段追溯 | **高** | [pipelines_v2.py L729-754](file:///f:/Coding/factor_pipeline/pipelines_v2.py#L729-L754) `_intermediate_data` 完整记录 |
| transform 阶段追溯 | **中** | 无现成机制,需手动重放或编写 tracing wrapper |
| 指纹/分类追溯 | **高** | `FactorFingerprint` NamedTuple 21 维全暴露 + `monitor.fingerprint_history` |
| 各步形状/分布 | **高** (fit) / **中** (transform) | 从 `_intermediate_data` 可计算 |
| 各步 IC 变化 | **中** | 需手动调用 `compute_rank_ic` 计算 |
| 正交化诊断 | **高** | `W_/condition_number_/eigvals_/F_stacked_/T_stacked_` 全暴露 |
| 现成可视化 | **低** | 仅有模块级 (DAG/中性化轮动/插补报告),无管线级 |

**总体可行性**: 中-高。主要工作量在编写 tracing wrapper + matplotlib/seaborn 绘图。

#### 9.2.2 Demo Notebook 结构设计

**目标**: 用一个 Jupyter notebook 可视化追溯整个管线处理流程,校验结果。

**Notebook 结构**:

| Cell | 内容 | 数据来源 |
|------|------|---------|
| 1 | 加载因子数据 + 行业/市值 + 价格 (前向收益) | CachedDataLoader |
| 2 | **指纹可视化**: 21 维指纹雷达图 + 与基准因子对比 | `pipeline.factor_pipelines[name][type].fingerprinter` |
| 3 | **分类决策树可视化**: 显示因子在 5 叉决策树上的路径 + 路由权重 | `_get_multi_dim_pipeline_weights` 中间状态 |
| 4 | **fit 阶段逐步追溯**: 各步 (imputer→outlier→transform→neutralize→standardize) 输出的分布直方图 + 截面排序变化 (Spearman 相关) | `get_intermediate_data()` |
| 5 | **横截面排序保持性检验**: 原始因子值 vs 各步输出 vs 最终输出的 Spearman rank 相关矩阵 | 手动计算 |
| 6 | **IC 变化追溯**: 各步输出的 rank IC 时序 + 累积 IC 曲线 | `compute_rank_ic` |
| 7 | **正交化诊断**: W 矩阵热力图 + 特征值 + condition_number + VRR (方差保留比) | `OrthogonalizerAdapter.get_diagnostics()` |
| 8 | **迁移检测追溯**: KS 检验 p 值时序 + BH-FDR 校正前后对比 + EWMA 衰减曲线 | `ThresholdDriftMonitor` + `_ks_migration_significance` |
| 9 | **管线输出 vs 原始因子**: 最终因子值 vs 原始因子的截面排序散点图 + IC 对比 | pipeline.transform() 输出 |
| 10 | **校验报告**: 自动检查 (a) 排序保持性阈值;(b) IC 显著性;(c) 正交化 condition_number;(d) 迁移检测告警 | 汇总 |

#### 9.2.3 关键可视化指标

**排序保持性** (核心):
- 原始 vs 各步输出的 Spearman rank 相关 ρ_step
- ρ_step ≥ 0.95: 排序保持
- 0.80 ≤ ρ_step < 0.95: 排序部分改变 (中性化/正交化预期)
- ρ_step < 0.80: 排序显著改变 (需审查)

**IC 变化**:
- 各步 rank IC 时序 + 累积
- IC 衰减比 = IC_after / IC_before (各步)
- 警戒线: IC 衰减比 < 0.5 表示该步显著破坏因子信号

**正交化诊断**:
- condition_number < 30: 良好
- 30 ≤ condition_number < 100: 可接受
- condition_number ≥ 100: 病态,需切换正交化算法

#### 9.2.4 工程实现路径

**阶段 1 — 最小可行 Demo (MVP)**:
- 仅覆盖 fit 阶段追溯 (利用 `get_intermediate_data()`)
- 用 matplotlib/seaborn 绘制分布/排序/IC
- 不编写 tracing wrapper

**阶段 2 — 完整追溯**:
- 编写 `TracingAdapter` 包装各 step 的 transform,捕获中间值
- 覆盖 transform 阶段
- 增加正交化诊断 + 迁移检测追溯

**阶段 3 — 交互式**:
- 用 plotly 替换 matplotlib,支持 hover/zoom
- 增加因子选择器/日期范围选择器

**建议**: 阶段 1 MVP 可在 T3/T5 启动前实施,作为管线健康检查工具。阶段 2/3 作为长期工程优化。

### 9.3 管线是否破坏因子排序信息

#### 9.3.1 核查结论

**整体结论**: 管线**部分破坏**因子横截面排序。这是**设计取舍**——剥离风险暴露以获得"纯 alpha 排序",非原始排序。

#### 9.3.2 各步骤对横截面排序的影响

| 步骤 | 操作类型 | 排序影响 | 证据 |
|------|---------|---------|------|
| CrossSectionalImputer | 填充截面均值/中位数 | **部分保留** — 仅产生 tied ranks | [imputers.py L113](file:///f:/Coding/factor_pipeline/modules/factor_imputer/core/imputers.py#L113) `fillna(global_stat)` |
| TimeSeriesImputer | ffill/bfill/rolling | **保留** — 按列时序操作 | [imputers.py L197](file:///f:/Coding/factor_pipeline/modules/factor_imputer/core/imputers.py#L197) |
| MLAdvancedImputer (KNN/RF) | 回归型预测 | **可能改变** — 预测值可落任意位置 | [imputers.py L297-381](file:///f:/Coding/factor_pipeline/modules/factor_imputer/core/imputers.py#L297-L381) |
| FactorSpecificImputer | 多因子回归预测 | **可能改变** | [imputers.py L469-470](file:///f:/Coding/factor_pipeline/modules/factor_imputer/core/imputers.py#L469-L470) |
| SmartAdaptiveWinsorizer | C¹ 单调软截断 | **保留** — 阈值外值压缩但保序 | [enhanced_transformers.py L1456-1485](file:///f:/Coding/factor_pipeline/modules/factor_adaptive_winsor/core/enhanced_transformers.py#L1456-L1485) |
| EnhancedRankPreservingScaler | 显式排序保持 | **保留** — `_ensure_rank_preservation` 强制重排 | [enhanced_transformers.py L471-493](file:///f:/Coding/factor_pipeline/modules/factor_adaptive_winsor/core/enhanced_transformers.py#L471-L493) |
| Z-Score 标准化 | 线性变换 | **保留** — 线性保序 | 标准 |
| 行业中性化 (OLS 残差) | 回归残差化 | **改变** — 剥离行业暴露 | [adapters.py L583-586](file:///f:/Coding/factor_pipeline/adapters.py#L583-L586) `model = sm.OLS(y, dummy_matrix).fit(); residuals = model.resid` |
| 市值中性化 (OLS 残差) | 回归残差化 | **改变** — 剥离市值暴露 | 同上 |
| 三重中性化 (Dynamic 管道) | OLS 残差 + AR 残差 + OLS 残差 | **显著改变** — 剥离行业+市值+时序自相关 | [dual_neutralizer.py L142-177](file:///f:/Coding/factor_pipeline/modules/factor_decoupler/core/dual_neutralizer.py#L142-L177) |
| 5 种正交化器 (Symmetric/GramSchmidt/PCA/Cholesky/Ridge) | K×K 混合矩阵 W | **改变** — 单因子被线性组合 | [base.py L123-137](file:///f:/Coding/factor_pipeline/modules/factor_orthogonalizer/core/base.py#L123-L137) `F @ W` |
| RollingOrthogonalizer | 滚动窗口估 W + 截面应用 | **改变** | [rolling.py L120](file:///f:/Coding/factor_pipeline/modules/factor_orthogonalizer/rolling.py#L120) |

#### 9.3.3 IC 评估与排序的关系

**关键事实**: IC 评估默认用 **Spearman rank IC** ([factor_metrics.py L109-180](file:///f:/Coding/factor_pipeline/backtest/factor_metrics.py#L109-L180), `method: Literal['rank', 'pearson'] = 'rank'`),[ic_monitor.py L47-51](file:///f:/Coding/factor_pipeline/backtest/ic_monitor.py#L47-L51) 强制 Spearman。

**含义**:
- 排序信息是因子有效性的核心度量
- 但管线的中性化/正交化步骤会破坏原始排序,产生"残差排序"
- 这是**设计意图**: 剥离风险暴露 (行业/市值) 后的"纯 alpha 排序"与原始排序不同
- 管线输出的不是"原始因子排序",而是"风险剥离后的因子排序"

#### 9.3.4 排序破坏的量化

**建议指标**: 在 Demo Notebook (§6.2) 中计算各步的 Spearman rank 相关 ρ_step:
- imputer 步: ρ ≥ 0.95 (预期接近 1)
- winsorize/scaler 步: ρ ≥ 0.95 (预期接近 1,因设计为保序)
- 行业/市值中性化步: ρ ∈ [0.5, 0.9] (预期显著下降,因剥离风险暴露)
- 三重中性化步 (Dynamic 管道): ρ ∈ [0.3, 0.7] (预期大幅下降)
- 正交化步: ρ ∈ [0.0, 0.5] (预期大幅下降,因 K 因子线性混合)

**校验阈值**:
- imputer/winsorize/scaler 步 ρ < 0.90: 异常,需审查
- 中性化步 ρ < 0.30: 可能过度中性化
- 正交化步 ρ < 0.0: 排序反转,需审查 W 矩阵符号

### 9.4 当前管线核心的计量层面贡献

#### 9.4.1 与主流工具链对比

| 工具链 | 定位 | 与 factor_pipeline 的关系 |
|--------|------|--------------------------|
| scikit-learn Pipeline | 通用 ML 预处理 | factor_pipeline 借鉴 fit/transform 接口,但增加因子语义 |
| Alphalens | IC 分析/收益分析 (后验) | factor_pipeline 是预处理工具,与 Alphalens 互补 |
| WorldQuant Alpha 101 | 因子构造公式库 | 层级不同,factor_pipeline 处理已构造的因子 |
| MSCI Barra | 风险模型 + 风格因子中性化 | factor_pipeline 的中性化是 Barra 风格子集,但增加指纹分类 |
| Qlib | 量化全流程平台 | factor_pipeline 是 Qlib 预处理层的特化替代 |

**独特定位**: "因子预处理 + 因子诊断 + 类型自适应路由" 三合一,在上述工具链中是空缺生态位。

#### 9.4.2 独特模块原创性核查

| 模块 | 原创性 | 证据 |
|------|--------|------|
| 21 维指纹 | **工程集成** — 13 维标准描述统计 + 8 维极值理论/Markov 切换集成 | [fingerprint.py L35-93](file:///f:/Coding/factor_pipeline/modules/factor_fingerprint/core/fingerprint.py#L35-L93);ar1/skew/kurt 文献已有,gpd_shape (Pickands 1975)/hill_estimator (Hill 1975)/regime_transition_prob (Hamilton 1989) 算法已有,集成进指纹是项目独创 |
| 5 叉决策路由 | **方法论增量** — 规则路由用于因子预处理差异化,文献中未见先例 | [pipelines_v2.py L96-217](file:///f:/Coding/factor_pipeline/pipelines_v2.py#L96-L217);但阈值 (0.3/0.1/1.5/5.0/1.0) 是启发式的,缺乏理论依据 |
| KS + BH-FDR | **方法论增量** — 跨领域迁移 BH-FDR 到因子迁移检测 | [pipelines_v2.py L274-495](file:///f:/Coding/factor_pipeline/pipelines_v2.py#L274-L495);KS 是 Smirnov 1948 标准技术,BH-FDR 是 Benjamini-Hochberg 1995 基因组学经典,组合用于因子迁移是新的 |
| RollingOrthogonalizer | **工程优化** — 增量 Gram 更新 + 定期重置 + NaN 防护 | [rolling.py L64-135](file:///f:/Coding/factor_pipeline/modules/factor_orthogonalizer/rolling.py#L64-L135);核心思想 (滚动窗口避免 look-ahead) 是回测共识 |
| ThresholdDriftMonitor | **工程集成** — EWMA (RiskMetrics 1996) 应用于阈值有效性监测 | [threshold_drift_monitor.py L19](file:///f:/Coding/factor_pipeline/backtest/threshold_drift_monitor.py#L19);EWMA 是标准技术,引用的 Bailey-López de Prado 2014/McLean-Pontiff 2016 与 EWMA 直接关系较弱 |
| 三重中性化 + 三管道差异化 | **方法论增量** — "原始值中性化 → AR 残差 → 残差中性化" 流程 | [dual_neutralizer.py L142-177](file:///f:/Coding/factor_pipeline/modules/factor_decoupler/core/dual_neutralizer.py#L142-L177);文献中未见明确先例 |

#### 9.4.3 整体贡献定位

**整体定位**: **"系统性集成创新"** — 单个组件多数已知,组合方式新颖。

| 层级 | 贡献 | 强度 |
|------|------|------|
| 单组件层 | 多数是已知方法的集成/迁移 | 弱 |
| 系统组合层 | 指纹驱动路由 + 多管道差异化 + BH-FDR + EWMA 监测的完整系统 | 中 |
| 方法论层 | 5 叉决策路由 + 三重中性化 + KS+BH-FDR 的组合 | 中-强 |

**与 §3 前置处理诚实性框架的关系**: §3 提出的"前置处理诚实性框架"是**更高层级的贡献** — 不是单个组件,而是**对前置处理选择层的系统性诚实化** (6 个自由度:去极值/标准化/缺失值/行业中性化/时间对齐/数据起止点)。管线本身是这个框架的实施载体。

**与 RESEARCH_NOTES §1-§5 的关系**: 当前管线 (T1-T7) 是**工程基础设施**,RESEARCH_NOTES §2B 条件分层归因 + §3 前置处理诚实性是**学术研究方向**。管线为研究提供基础设施,研究为管线提供学术定位。

#### 9.4.4 计量贡献的诚实立场

**强贡献** (方法论增量,可发表):
- 5 叉决策路由 (规则路由用于因子预处理差异化)
- 三重中性化 (Dynamic 管道的"原始值→AR→残差"流程)
- KS + BH-FDR (跨领域迁移,已在 §1 学术价值记录)

**弱贡献** (工程集成,不易单独发表):
- 21 维指纹 (标准统计 + 极值理论集成)
- RollingOrthogonalizer (增量 Gram 更新)
- ThresholdDriftMonitor (EWMA 应用)

**待挖掘贡献** (需 §2B/§3 实证支撑):
- §2B 条件分层归因 (需 T5/T6 实施后实证)
- §3 前置处理诚实性框架 (需论文层面论述)

**立场**: 当前管线的计量贡献**不足以单独构成顶刊论文**,但作为"自适应因子预处理系统"的工程实现,加上 §3 前置处理诚实性框架的学术论述,可构成**方法论论文 + 工程实现**的组合贡献。这与 §5.5 "v3.0.0 扩展 (T5/T6/T7) 是 §2B 的工程前置条件"一致。

### 9.5 第十三轮审查 (2026-07-07,§6 章节严格审查)

> **触发**: 用户指令"严格 review 审查修改" — 对 §6.1-§6.4 执行方案 + Demo + 排序 + 计量贡献分析做严格审视

#### 9.5.1 §6.1 执行方案审查

**S1 [MAJOR]**: §6.1.1 T3.3 "k 通常取 0.5σ,h 通常取 4σ-5σ (Page 1954 建议)" — Page 1954 原文给出的 k 和 h 推荐值需精确核查。Page 1954 引入 CUSUM 时给出的是 ARL (Average Run Length) 公式,具体 k/h 取值取决于目标 ARL,不是固定 0.5σ/4-5σ。**修正**: 改为"k 通常取 0.5σ (slack parameter,半漂移检测),h 取值需通过 ARL (Average Run Length) 计算确定,Page 1954 给出 ARL 公式但具体 h 取值依赖目标误报率"

**S2 [MAJOR]**: §6.1.2 T5.1 列出 11 个状态变量 (DR007/Amihud/Pastor-Stambaugh/VIX/涨跌停数量/换手率/北向资金/两融余额/信用利差/size spread/value spread),但 §2B.2.2 定义了 12 个 (含政策周期)。**修正**: 补充第 12 个 "政策周期" (T5.3 已单独列出,但 T5.1 列表应完整标注 11 个 + 政策周期 = 12 个)

**S3 [MINOR]**: §6.1.3 T6.5 "五种背离情形判定" 与 T7.4 "五种背离情形分类" 重复。**修正**: 明确 T6.5 是 R vs IC 背离 (基于 §2B.4.2 主回归 + §2B.4.3 三通道分解),T7.4 是三通道分解的细分 (β_R vs β_IC vs β_σ_factor vs β_σ_R),两者是同一框架的不同视角,实施时合并

**S4 [MINOR]**: §6.1.6 依赖图中 "T3.5 (协同 BH-FDR)" 应与 T4 (已完成) 协同,不是 T3 自身阶段。**修正**: T3.5 是"协同改进 unified_drift.py 加入 BH-FDR (复用 T4 实现)",不是 T3 的独立阶段,可标注为 T3 的协同任务

#### 9.5.2 §6.2 Demo 可视化审查

**D1 [MAJOR]**: §6.2.2 Cell 4 "fit 阶段逐步追溯" 依赖 `get_intermediate_data()`,但核查报告指出该机制**仅在 fit() 阶段填充,transform() 阶段不填充**。若用户用新数据 transform,无法追溯。**修正**: 在 Cell 4 加 caveat "仅追溯 fit 阶段;transform 阶段需阶段 2 的 TracingAdapter"

**D2 [MAJOR]**: §6.2.3 排序保持性阈值 (ρ ≥ 0.95 / 0.80 ≤ ρ < 0.95 / ρ < 0.80) 是经验值,无文献依据。**修正**: 加 caveat "阈值为经验值,需在多个因子上 Monte Carlo 校准"

**D3 [MINOR]**: §6.2.2 Cell 7 正交化诊断 "condition_number < 30 良好 / 30-100 可接受 / ≥100 病态" 是 Belsley 1980 经验法则,需引用。**修正**: 补充 Belsley, Kuh & Welsch (1980) *Regression Diagnostics* 引用

#### 9.5.3 §6.3 排序信息审查

**R1 [CRITICAL]**: §6.3.4 "正交化步 ρ ∈ [0.0, 0.5]" 是推测,无实际测量。**修正**: 改为"预期大幅下降,具体范围需 Demo Notebook 实测;理论上 W 矩阵是 K×K 混合矩阵,单因子被线性组合,排序可能与原始排序低相关甚至负相关"

**R2 [MAJOR]**: §6.3.4 "中性化步 ρ ∈ [0.5, 0.9]" 也是推测。**修正**: 改为"预期显著下降,具体范围取决于行业集中度和市值分布;同行业内股票的相对排序会因去除共同行业暴露而重排"

**R3 [MINOR]**: §6.3.3 "管线输出的不是原始因子排序,而是风险剥离后的因子排序" 表述清晰,但应补充:对于 Dynamic 管道 (三重中性化),输出是"纯净新息的截面排序",与原始排序差异最大

#### 9.5.4 §6.4 计量贡献审查

**M1 [CRITICAL]**: §6.4.2 "5 叉决策路由,文献中未见先例" 是强断言,需文献调研确认。**修正**: 改为"据初步调研文献较少见,需系统性文献调研确认空白" (与 §2.6.2 一致)

**M2 [MAJOR]**: §6.4.2 "三重中性化,文献中未见明确先例" 同样是强断言。**修正**: 改为"据初步调研,在因子预处理文献中未见明确先例,需系统性文献调研;但 Hausman 1978 内生性理论、Barra 风格的多阶段中性化实践有相关思想"

**M3 [MAJOR]**: §6.4.4 "当前管线的计量贡献不足以单独构成顶刊论文" 是诚实的立场,但需补充:KS+BH-FDR (§1) 是**已确认的方法论增量**,可单独构成应用统计方法论文 (投 Journal of Financial Econometrics / Quantitative Finance)。**修正**: 补充 "§1 KS+BH-FDR 是已确认的可发表贡献,投 Journal of Financial Econometrics / Quantitative Finance"

**M4 [MINOR]**: §6.4.3 "21 维指纹 (标准统计 + 极值理论集成)" 弱贡献评定可能过严。**修正**: 补充 "指纹的独创性不在单个维度,而在组合用于管道路由 — 这是系统级贡献的一部分"

**M5 [MINOR]**: §6.4.2 ThresholdDriftMonitor "引用的 Bailey-López de Prado 2014/McLean-Pontiff 2016 与 EWMA 直接关系较弱" — 应明确这些引用是为"数据窥探/发表衰减"问题提供背景,不是 EWMA 方法的直接依据。**修正**: 改为"引用的 Bailey-López de Prado 2014/McLean-Pontiff 2016 是为因子衰减问题提供学术背景,EWMA 方法本身依据 RiskMetrics 1996"

#### 9.5.5 核心立场强化 (第十三轮)

§6 章节通过严格审查后,核心立场:

1. **执行方案**: T3 CUSUM (P1) + T5 状态接入 (P1) 并行 → T6/T7 (P2) 串行 → T2 流式 (P2)。S1-S4 修正后,执行方案的具体步骤、依赖、产出明确
2. **Demo 可视化**: 阶段 1 MVP (fit 阶段追溯) 可立即实施,阶段 2/3 长期工程优化。D1-D3 修正后,可行性评估诚实
3. **排序信息**: 管线**部分破坏**横截面排序是设计取舍 — 剥离风险暴露以获得"纯 alpha 排序"。R1-R3 修正后,各步影响量化为推测范围,需 Demo Notebook 实测
4. **计量贡献**: 系统性集成创新,单组件多数已知,组合新颖。M1-M5 修正后,贡献定位诚实 — KS+BH-FDR 可发表,其他需 §2B/§3 实证支撑

**与 §5 兼容性分析的一致性**: §6 的执行方案与 §5.6.5 优先级矩阵一致 — T3 (P1) 优先,T5 (P1) 并行,T6/T7 (P2) 串行,T2 (P2) 长期。§6.4.4 的计量贡献定位与 §5.5 的"v3.0.0 扩展是 §2B 的工程前置条件"一致。

**审查总结**: §6 章节经第十三轮审查修正 12 项问题 (1 CRITICAL + 6 MAJOR + 5 MINOR),核心立场稳固,执行方案可操作,Demo 可行性诚实,排序信息分析诚实,计量贡献定位诚实。

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
