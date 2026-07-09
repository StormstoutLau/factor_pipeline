# 开发日志 (Changelog)

## v3.1.0 — Audit-Driven Code Quality Remediation (已实施, 2026-07-09)

执行 audit-driven-development 4 阶段流程: P0×8 + P1×8 + P2+×15 (断言恒真式重写 5 + 设计约束测试 10 + 端到端 2 + E5 测试补强 5) + spec 反向对齐 11 项。子集回归 754 passed + 1 skipped (零回归, E1-E10 + V3.1.0 E1-E6 范围)。

**断言恒真式重写 (A1-A4, 5 测试)**:
- RN-E2 Romano-Wolf: 相同 random_state bootstrap 一致 + 不同 random_state 差异
- E3-T21 critical_alert: 20 seed 循环非平凡触发
- E6-T10 IVX bias: IVX β 比 OLS β 更接近真值 0.3
- E6-T17/T18 SCAD/MCP: λ=1.0/5.0 时 n_zeroed>0 + λ 敏感性对照

**设计约束测试 (B1-B3, 10 测试)**:
- B1 Config 字段存在性 (3) / B2 配置生效 oster_r_max_multiplier+alert_threshold (2) / B3 method_formal_name+选择器逻辑 (5)

**E5 测试补强 (5 测试)**:
- 已知关系识别 (gpd_shape→ic_mean, β=0.3) / β 范围 (|β|≤1) / 零权重零贡献 / BH 单调性 (p_adj≥p) / 显著交互 (构造 β=2.0)

**spec 反向对齐 (11 项)**: E1 签名 / E2 stepdown / E4 log+SQL / E5 Layer2 / E9 _trend

**审计报告**: [docs/audit/2026-07-08-research-notes-v3.1.0-code-quality-audit.md](docs/audit/2026-07-08-research-notes-v3.1.0-code-quality-audit.md)
**commit**: 6192edb (7 files, +820/-87)

---

## v3.0.0 T3 — CUSUM 在线漂移检测 + BH-FDR 共享模块 (已实施, 2026-07-07)

### 概览

实施 v3.0.0 远期规划 T3 任务: Page (1954) CUSUM 算法实现 + ARL Monte Carlo 校准 + 管线集成 + BH-FDR 共享模块 + ADR-025 文档同步。T3.1-T3.6 全部完成, 385 passed + 1 skipped 零回归 (比 v3.0.0 T1 的 974 多 76 个 backtest 测试中的 76 个相关项, 累计 385 backtest + modules 测试)。

**核心产出**:
- 2 个新模块: `backtest/cusum_drift_monitor.py` (CUSUM 算法) + `backtest/multiple_testing.py` (BH-FDR 共享模块)
- 1 项新 ADR: ADR-025 (CUSUM 在线漂移检测, 含 T3.1-T3.6 全部校准结果 + 集成决策)
- 全量回归: 385 passed + 1 skipped (零回归, 含 CUSUM 22 + ARL 11 + multiple_testing 22 + unified_drift_bh_fdr 5 + pipelines_v2_cusum 16 + 全部 backtest 既有测试)
- 手工校验: T3.3 ARL Monte Carlo (k=0.5, h=5.0 默认参数经校准验证合理) + T3.5 BH 黄金参考 [0.005, 0.01, 0.02, 0.04, 0.5] → p_adj=[0.025, 0.025, 0.0333, 0.05, 0.5] 与文献一致

### T3.1-T3.6 六阶段 TDD 实施详情

| 阶段 | 任务 | 测试数 | 状态 | 关键变更 |
|------|------|--------|------|---------|
| **T3.1** | CUSUM 测试 (Red) | 22 | ✅ | 5 类测试: 基础功能(5) + 检测能力(6) + 在线更新(4) + CUSUM vs EWMA 对比(1) + 边界条件(6) |
| **T3.2** | CUSUM 实现 (Green→Review) | — | ✅ | `CUSUMDriftMonitor` Page 1954 双侧递推: S_pos[t]=max(0, S_pos[t-1]+x-μ₀-kσ), S_neg[t]=min(0, S_neg[t-1]+x-μ₀+kσ); 触发后自动重置 S=0; NaN 跳过; 参数校验 (std≤0/k<0/h<0 抛 ValueError) |
| **T3.3** | ARL Monte Carlo 校准 | 11 | ✅ | 6 类测试: In-control ARL(3) + Out-of-control ARL(4) + k 选择(1) + 联合约束(1) + Siegmund 对比(1) + 方向对称性(1)。ARL₀(h=5σ)≈507 (MC, T=3000 截断) vs 285 (Siegmund) vs 930 (文献); ARL₁(1σ) 5-30 容差内; ARL₁(3σ) 1-8 容差内; k=0.5 最优性 + 方向对称性 + ARL 单调性验证 |
| **T3.4** | 管线集成 (事后诊断) | 16 | ✅ | 5 类测试: 配置开关(4) + 监测器初始化(3) + 事后诊断(5) + drift_alerts(2) + 向后兼容(2)。`PipelineV2Config` 新增 `enable_cusum_drift_monitor` (默认 False) + `cusum_k=0.5` + `cusum_h=5.5` (补偿两个 CUSUM 叠加); `monitor_cusum_drift(factor_data)` 方法监测横截面均值/标准差, 不侵入 fit/transform 循环 |
| **T3.5** | BH-FDR 共享模块 | 22+5 | ✅ | 5 类测试: BH 正确性(11) + Bonferroni(3) + 无校正(2) + 对比(2) + 边界(4); `apply_bh_fdr`/`apply_bonferroni`/`apply_no_correction`/`apply_correction` 统一入口; `_HAS_MULTIPLE_TESTING` flag + 内联 fallback 向后兼容; `unified_drift._compute_rolling_structure_drift` 修复 ~504 次 KS 检验假阳性 (默认 BH-FDR); `factor_significance._apply_correction` 与 `pipelines_v2._check_ks_migration` 重构为调用共享模块 |
| **T3.6** | ADR-025 文档更新 | 0 | ✅ | DECISIONS.md ADR-025 状态从"T3.1-T3.2 已实施"更新为"T3.1-T3.6 全部完成", 附 ARL 校准结果表 + 管线集成决策 + BH-FDR 共享模块决策 + 全量回归记录 |

### 关键设计决策

1. **CUSUM 定位为事后诊断工具**: 不侵入 `fit/transform` 循环, 不改变管线输出, 仅提供附加漂移告警。`monitor_cusum_drift(factor_data)` 作为独立方法, 与 §3 前置处理诚实性框架一致 (第十六轮审查 G1 修正)
2. **监测横截面统计量非 IC**: CUSUM 监测横截面均值/标准差, 与 `unified_drift` 的 IC 序列监测正交, 不重复 (第十六轮审查 G2 修正)
3. **序贯检验无需 BH-FDR**: 两个 CUSUM (mean+std) 独立监测不同统计量, 是序贯检验非多重检验问题, 无需 BH-FDR 校正 (第十六轮审查 G3 修正, 撤销第十五轮 F5 部分论断)
4. **h=5.5 补偿两个 CUSUM 叠加**: 默认 h=5.5 (而非 ARL 校准的 h=5.0), 因两个 CUSUM 任一触发即告警, ARL₀_eff ≈ ARL₀/2 ≈ 250, 与文献 930 同数量级 (第十六轮审查 G4 修正)
5. **默认 `enable_cusum_drift_monitor=False`**: 向后兼容, 显式 opt-in (第十六轮审查 G5 修正)
6. **BH-FDR 共享模块低级函数 + 统一入口**: `apply_bh_fdr`/`apply_bonferroni`/`apply_no_correction` 三个低级函数 + `apply_correction(method=...)` 统一入口, 供 `unified_drift` / `pipelines_v2` / `factor_significance` 三处共享
7. **`_HAS_MULTIPLE_TESTING` flag + 内联 fallback**: 共享模块导入失败时 fallback 到内联实现, 保证零回归
8. **Holm 路径保留内联**: `multiple_testing.py` 暂未实现 Holm, `factor_significance._apply_correction` 的 Holm 路径保留内联实现
9. **`unified_drift` 默认 BH-FDR**: `_compute_rolling_structure_drift` 默认 `rolling_correction_method='benjamini_hochberg'`, `correction_method='none'` 保留旧路径向后兼容
10. **baseline_mean/std 从 fit 阶段估**: 从 `_intermediate_data` 最终输出的横截面均值/标准差的时间序列均值估, 非 fingerprint (第十六轮审查 G6 修正)

### 行为变化警示 (BREAKING-ISH)

**默认行为不变** (`enable_cusum_drift_monitor=False`, `rolling_correction_method='benjamini_hochberg'` 是新默认但有 `'none'` 向后兼容路径)。仅当显式开启时行为变化:

- `enable_cusum_drift_monitor=True`: 启用 CUSUM 事后诊断, `monitor_cusum_drift()` 填充 `drift_alerts` 字典
- `unified_drift._compute_rolling_structure_drift` 默认从 `none` 改为 `benjamini_hochberg`: 无漂移数据 score 从 ~5 (假阳性) 降为 0; 真实漂移检测力提升 (BH ≤ none 显著数)。若需复现旧行为, 显式传 `rolling_correction_method='none'`

### 学术依据

- Page, E. S. (1954). Continuous inspection schemes. *Biometrika*, 41(1/2), 100-115. — CUSUM 双侧递推
- Siegmund, D. (1985). *Sequential Analysis*. Springer. — ARL 近似公式 (T3.3 Monte Carlo 校准对比依据)
- Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate: a practical and powerful approach to multiple testing. *JRSS Series B*, 57(1), 289-300. — BH-FDR 校正
- Dunn, O. J. (1961). Multiple comparisons among means. *JASA*, 56(293), 52-64. — Bonferroni 校正 (保留向后兼容)

---

## v3.0.0 T1 — 指纹维度扩展至 21 维 (已实施, 2026-07-04)

### 概览

将 `FactorFingerprint` 从 13 维扩展至 21 维, 新增 8 维 (尾部依赖 4 + 体制转换 3 + 综合衍生 1), 并将孤儿函数 `_get_multi_dim_pipeline_weights` 接入 `transform()` 生产路径 (含 `enable_multi_dim_routing` 配置开关, 默认 False 向后兼容)。E1-E3 三阶段 TDD 全部完成, 974 passed + 6 skipped + 11 subtests passed (零回归, 比 v3.0.0 T4 的 934 多 40 个新测试)。

**核心产出**:
- [docs/ANALYSIS_V3.0.0.md](docs/ANALYSIS_V3.0.0.md) §1 — T1 深度核查 (13 维现状 / 4 项关键事实 / T1.1-T1.4 方案)
- [docs/EXECUTION_V3.0.0_T1.md](docs/EXECUTION_V3.0.0_T1.md) v1.1 — T1 执行方案 (E1-E3 三阶段, v1.1 含 1 CRITICAL + 3 MAJOR + 4 MINOR + 4 NIT 修订)
- 1 项新 ADR: ADR-024 (指纹维度扩展至 21 维)
- 全量回归: 974 passed + 6 skipped + 11 subtests passed (零回归, 比 v3.0.0 T4 的 934 多 40 个新测试)
- 手工校验: verify_v3_0_0_t1_manual.py 8/8 通过 (E3 新增)

### E1-E3 三阶段 TDD 实施详情

| 阶段 | 任务 | 测试数 | 状态 | 关键变更 |
|------|------|--------|------|---------|
| **E1** | 指纹核心扩展 (Red→Green→Review) | 32 | ✅ | `FactorFingerprint` NamedTuple 13→21 维 (8 新字段默认 NaN), `FingerprintConfig` 8→14 字段, `to_dict` 13→21 键, `extract_fingerprint` 追加阶段 4-5-6, 8 新私有计算方法 (`_compute_tail_dependence_lower/upper`, `_estimate_gpd_shape` POT-MLE, `_hill_estimator`, `_compute_regime_transition_prob/persistence/ic_diff`, `_derive_tail_regime_score` M2 双分量加权), ADR-014 技术债清理 (statsmodels 顶部导入) |
| **E2** | 路由层接入 + 测试更新 | 8 | ✅ | `PipelineV2Config` 新增 `enable_multi_dim_routing` (默认 False), `_get_multi_dim_pipeline_weights` 追加 Step 4 T1 修正 (tail_severity 阈值 0.3 → mixed +0.10; regime_instability 阈值 0.1 → dynamic +0.10), `transform()` 接入开关, `_make_fp` 重构为 **kwargs 模式支持 21 维, 新增 TestTailRegimeAdjustment (4) + TestMultiDimRoutingConfig (4) |
| **E3** | 文档同步 + 全量回归 | 0 | ✅ | ADR-024 写入 DECISIONS.md, CHANGELOG/CODE_WIKI/README/README.en 同步, ANALYSIS_V3.0.0.md T1 状态改已实施, verify_v3_0_0_t1_manual.py 8/8 手工校验, 全量回归 974 passed + 6 skipped + 11 subtests |

### 8 维新维度 (T1.1 + T1.2 + T1.3)

| 子任务 | 维度数 | 字段 | 学术依据 | 默认开关 |
|--------|--------|------|---------|---------|
| **T1.1 尾部依赖** | 4 | `tail_dependence_lower` / `tail_dependence_upper` / `gpd_shape` / `hill_estimator` | Nelsen (2006) Copula; Pickands (1975, 实际用 POT-MLE `scipy.stats.genpareto.fit` 替代); Hill (1975) | `enable_tail_dependence=False` |
| **T1.2 体制转换** | 3 | `regime_transition_prob` / `regime_persistence` / `regime_ic_diff` | Hamilton (1989) Markov 两状态, 不收敛降级为硬阈值 | `enable_regime_switching=False` (m1 修订) |
| **T1.3 综合衍生** | 1 | `tail_regime_score` | M2 双分量加权: `w * tail_severity + (1-w) * regime_instability` | 依赖 T1.1/T1.2 任一开启 |

### 关键设计决策

1. **默认关闭尾部依赖与体制转换**: `enable_tail_dependence=False` (Copula O(N²) 成本), `enable_regime_switching=False` (m1 修订, 避免小样本日志噪音), 显式 opt-in
2. **POT-MLE 替代 Pickands 估计量**: `_estimate_gpd_shape` 用 `scipy.stats.genpareto.fit` (POT-MLE), 比 Pickands 原始估计量对轻尾分布更稳健 (E1 Green 阶段修正, Pickands 对正态分布返回 2.356 不稳定)
3. **regime_ic_diff 方案 C**: 一阶差分均值差 (bull Δfactor 均值 - bear Δfactor 均值), 不破坏 `extract_fingerprint` 签名 (无前向收益数据输入)
4. **路由接入加 `enable_multi_dim_routing` 开关**: 默认 False (向后兼容), True 时 `transform` 使用 `_get_multi_dim_pipeline_weights` (含 T1 tail/regime 修正)
5. **不扩展 `AdaptiveFactorClassifier.classify`**: 仍仅用 `ar1_median`, 新维度仅作用于 `_get_multi_dim_pipeline_weights` 修正层
6. **`_derive_tail_regime_score` M2 双分量加权**: 简化公式避免嵌套权重可读性差
7. **statsmodels 顶部导入**: ADR-014 技术债清理, 移除 `_test_volatility_clustering` 的 try/except ImportError
8. **`_make_fp` 测试辅助重构为 `**kwargs` 模式**: 支持 21 维字段覆盖, 既有 12 测试向后兼容

### 行为变化警示 (BREAKING-ISH)

**默认行为不变** (所有新维度默认关闭, NamedTuple 8 新字段默认 NaN, `enable_multi_dim_routing` 默认 False)。仅当显式开启 `enable_tail_dependence=True` / `enable_regime_switching=True` / `enable_multi_dim_routing=True` 时, 行为才变化:

- `extract_fingerprint` 返回的 NamedTuple 从 13 维扩展至 21 维 (8 新字段默认 NaN, 既有 13 维不变)
- `to_dict` 返回 21 键 (既有 13 键不变)
- `transform()` 在 `enable_multi_dim_routing=True` 时使用多维路由 (含 T1 tail/regime 修正), 否则走旧路径

### 学术依据

- Nelsen, R. B. (2006). *An Introduction to Copulas* (2nd ed.). Springer. — 尾部依赖 Copula 经验条件概率
- Pickands, J. (1975). Statistical inference using extreme order statistics. *Annals of Statistics*, 3(1), 119-131. — GPD 极值理论 (实际用 POT-MLE 替代原始估计量)
- Hill, B. M. (1975). A simple general approach to inference about the tail of a distribution. *The Annals of Statistics*, 3(5), 1163-1174. — Hill 重尾指数
- Hamilton, J. D. (1989). A new approach to the economic analysis of nonstationary time series and the business cycle. *Econometrica*, 57(2), 357-384. — Markov 体制转换

---

## v3.0.0 T4 — KS 迁移检测 BH-FDR 替代 Bonferroni (已实施, 2026-07-04)

### 概览

将 `_ks_migration_significance` 的多重比较校正从保守的 Bonferroni 迁移到 Benjamini-Hochberg FDR, 与 `factor_significance.py` 的 BH 默认一致 (E7 已用 BH)。核心改动仅 1 个函数 (~20 行核心代码), 但提升因子迁移检测的检测力, 减少 Type II 误差 (漏检真实迁移)。

**核心产出**:
- [docs/ANALYSIS_V3.0.0.md](docs/ANALYSIS_V3.0.0.md) v1.1 — v3.0.0 4 项远期任务深度核查 (T1-T4)
- [docs/EXECUTION_V3.0.0_T4.md](docs/EXECUTION_V3.0.0_T4.md) v1.1 — T4 执行方案 (E1-E3 三阶段)
- 1 项新 ADR: ADR-002a (supersede ADR-002 校正方法, ADR-002 历史保留)
- 全量回归: 934 passed + 6 skipped + 11 subtests passed (零回归, 比 v2.6.0 的 918 多 16 个新测试)
- 手工校验: verify_fix1_manual.py 6/6 通过 (E2 修订), verify_v3_0_0_t4_manual.py 通过 (E3 新增)

### E1-E3 三阶段 TDD 实施详情

| 阶段 | 任务 | 测试数 | 状态 | 关键变更 |
|------|------|--------|------|---------|
| **E1** | BH 核心实现 (Red→Green→Review) | 13 | ✅ | `_ks_migration_significance` 新增 `correction_method` 参数 (默认 'benjamini_hochberg'), 三路径分流 (BH/Bonferroni/none), 字段隔离 (BH: min_p_value_adjusted/correction_method; Bonferroni: alpha_corrected/bonferroni_correction), ADR-002a 写入 DECISIONS.md |
| **E2** | 测试更新 | 3 | ✅ | verify_fix1_manual.py 校验 3 改为 BH 公式校验, test_factor_significance_manual.py 新增 TestKSMigrationBHCorrection 类 (3 测试: BH 黄金参考/BH 宽松性/Bonferroni 向后兼容) |
| **E3** | 文档同步 + 全量回归 | 0 | ✅ | CHANGELOG/CODE_WIKI/README 同步, verify_v3_0_0_t4_manual.py 手工校验, 全量回归 934 passed + 6 skipped + 11 subtests |

### 关键设计决策

1. **默认改 BH, 保留 Bonferroni 向后兼容**: `correction_method='bonferroni'` 显式 opt-in 旧路径, 字段全部保留
2. **三路径字段隔离**: BH 路径不污染 Bonferroni 字段, 反之亦然, 避免 details 字典字段混淆
3. **None 路径供研究/调试**: `correction_method='none'` 无校正, 直接 `min_p < alpha`
4. **黄金参考**: p=[0.01, 0.04, 0.03, 0.20, 0.50], K=5 → p_adj=[0.05, 0.0667, 0.0667, 0.25, 0.50], min_p_value_adjusted=0.05
5. **行为变化**: BH 比 Bonferroni 宽松, 之前不显著的迁移现在可能变显著 (`is_sig` 可能 False→True), 这是 T4 核心目的

### 行为变化警示 (BREAKING-ISH)

**默认 `correction_method` 从 Bonferroni 改为 BH**, `is_sig` 可能从 False 变为 True (BH 检测力更高)。若应用场景要求严格控制 FWER (至少一个假阳性概率), 应显式传 `correction_method='bonferroni'`。

### 学术依据

- Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate: a practical and powerful approach to multiple testing. *Journal of the Royal Statistical Society: Series B*, 57(1), 289-300.
- Dunn, O. J. (1961). Multiple comparisons among means. *JASA*, 56(293), 52-64. (Bonferroni 校正, 保留向后兼容)

---

## v2.6.0 — 优化器与漂移检测增强 (已实施, 2026-07-03/04)

### 概览

基于 v2.5.0 三层架构 (Layer 1 / Layer 2 正交化 / Layer 3 显著性) 完成, 推进 ADR-004 (目标函数) / ADR-005 (搜索空间) / ADR-006 (扩展窗口 CV) 三项设计契约在优化器层面的完整闭环. **E1-E9 9 阶段 TDD 全部完成**, 918 passed + 6 skipped + 11 subtests passed (零回归, 比 v2.5.0 的 860 多 58 个新测试).

**核心产出**:
- [docs/ANALYSIS_V2.6.0.md](docs/ANALYSIS_V2.6.0.md) v1.1 (810 行) — 深度核查 8 类问题 / 8 项任务 / 11 项风险 / 9 篇文献核查
- [docs/EXECUTION_V2.6.0.md](docs/EXECUTION_V2.6.0.md) (1595 行) — 9 个执行阶段 (E1-E9), ~59 新测试 + 860 基线 = ~919 passed
- 3 项新 ADR: ADR-021 (health_penalty 代理) / ADR-022 (正交化搜索) / ADR-023 (ThresholdDriftMonitor)
- 全量回归: 918 passed + 6 skipped + 11 subtests passed (1171.44s, 19:31)
- 手工校验: verify_v2_6_0_manual.py 8/8 通过 (E1-E8 汇总)

### E1-E9 9 阶段 TDD 实施详情

| 阶段 | 任务 | 测试数 | 状态 | 关键变更 |
|------|------|--------|------|---------|
| **E1** | P3-11' 文档状态修正 | 0 | ✅ | DECISIONS.md P3-11 `[ ]` → `[x]`, 学术依据分拆 (TPE→Bergstra 2011, fANOVA→Hutter 2014) |
| **E2** | P3-10' migration_threshold 字段位置 + ADR-005 | 5 | ✅ | optimizer.py:150-158 字段位置错误 (config.monitor → config), ADR-005 末尾追加修订日志 |
| **E3** | P3-1' IC 时间加权 EWMA | 8 | ✅ | factor_metrics.py compute_ic_series 添加 weighting/halflife 参数, optimizer._compute_ic 集成 EWMA, 学术依据改引 Ferson-Siegel (2001) |
| **E4** | P3-9' 目标函数对齐 ADR-004 (ADR-021) | 10 | ✅ | _composite_objective 添加 health_penalty (代理指标方案 B), 修正 fidelity 符号方向 (+ → -), 新增 _health_penalty_proxy (decay_ratio/hit_rate/ic_vol 三档), 全量回归 883 passed |
| **E5** | P3-13 正交化参数纳入搜索空间 (ADR-022) | 8 | ✅ | DEFAULT_SEARCH_SPACE_ORTH 添加 orth_method/align_mode/ridge_lambda (不搜索 orth_enabled), optimize() 添加 categorical + log-uniform 采样, 全量回归 885 passed |
| **E6** | P3-14 几何诊断纳入目标函数 | 12 | ✅ | OrthogonalizerAdapter.fit() 保存 _F_stacked_/_T_stacked_, get_diagnostics() 新方法, _redundancy_penalty 基于 compute_vrr (λ=0.05, v1.1 从 0.1 降), _composite_objective 6 项对齐 ADR-004, look-ahead bias 防护, 全量回归 903 passed |
| **E7** | P3-15 Layer 3 显著性最终验证 | 6 | ✅ | _validate_significance 调用 FactorSignificanceTest (Belloni 2014 PDS Lasso+HC3+BH), optimize() 添加 validate_significance 参数 (默认 False 向后兼容), 对齐+dropna 处理 NaN, 异常防护 |
| **E8** | P3-12' 阈值漂移监测 (ADR-023) | 10 | ✅ | backtest/threshold_drift_monitor.py 新建, ThresholdDriftMonitor (EWMA 衰减检测, decay > 20% 触发 needs_research), update/get_history/reset 三方法, min_observations=5 保护 |
| **E9** | 文档验证 + 全量回归 | 0 | ✅ | verify_v2_6_0_manual.py 8/8 手工校验通过, 全量回归 918 passed + 6 skipped + 11 subtests passed, 文档全部更新 (README/CHANGELOG/CODE_WIKI/DECISIONS) |

### 关键设计决策

1. **lambda_redundancy=0.05** (v1.1 从 0.1 降): 避免与 IC 主目标双重惩罚
2. **_validate_significance 对齐+dropna**: LassoCV 不接受 NaN, 需在调用前处理
3. **空 factor_data 异常防护**: _validate_significance 返回错误报告而非抛异常
4. **ThresholdDriftMonitor EWMA**: `alpha = 1 - exp(-ln2/halflife)`, decay_ratio = ewma/best_score
5. **validate_significance 默认 False**: 向后兼容, 仅最终验证 (计算成本约束)
6. **正交化作为 post_transform_hook**: 随 pipeline.fit(train_factor) 在 train 上估计 W, 防止 look-ahead bias

### 分析阶段 (ANALYSIS_V2.6.0.md v1.0 → v1.1)

**v1.0 → v1.1 深度核查发现 4 项错误**:
1. **Cohen-Coval-Pastor (2005) 误推荐**: v1.0 推荐 "Judging Fund Managers by the Company They Keep" 作为 P3-1 IC 时间加权学术依据, 实际该论文讨论基金持仓相似度, 与 EWMA 无关. v1.1 撤回, 改引 Ferson-Siegel (2001).
2. **migration_threshold "字段缺失" 误判**: v1.0 报告 MonitorConfig 缺 migration_threshold 字段, 实际 `PipelineV2ConfigUnified.migration_threshold` 字段已存在 (config_v2.py:407-410, 默认 0.10). v1.1 修正为"字段位置错误" — optimizer.py:155-158 错误设置到 `config.monitor` 上.
3. **FactorSignificanceTest 未集成遗漏**: v1.0 未发现 `backtest/factor_significance.py` 已完整实现 (Belloni 2014 PDS + HC3 + BH) 但 optimizer.py 未调用. v1.1 新增 P3-15 任务.
4. **health_penalty 时序问题未识别**: v1.0 未识别 `HealthMonitorAdapter.build_report_from_engine` 的 engine_results 时序依赖 (只能在回测后计算, 不能在 CV fold 内部直接调用). v1.1 新增时序问题描述 + 3 种实现方案, 推荐代理指标方案 (B).

**8 类问题汇总**:
| 类别 | 问题 | 解决阶段 |
|------|------|---------|
| 文档状态 | P3-11 已实施但 DECISIONS 标 `[ ]` | E1 |
| 字段位置 | migration_threshold 设置到 config.monitor 而非 config | E2 |
| 目标函数 | 缺 health_penalty + fidelity 符号相反 | E4 |
| 搜索空间 | 未纳入 v2.5.0 正交化参数 | E5 |
| 几何诊断 | 未将 VRR 纳入目标函数 | E6 |
| 显著性 | FactorSignificanceTest 已实现未集成 | E7 |
| 漂移监测 | 阈值组合有效性漂移无监测 | E8 |
| 学术依据 | P3-1 误引 Dimson/Moreira-Muir, P3-12 误引 Hsu 2010 | E3/E8 |

### 执行方案 (EXECUTION_V2.6.0.md, 9 阶段)

| 阶段 | 任务 | 优先级 | 依赖 | 测试数 | 关键变更 |
|------|------|--------|------|--------|---------|
| **E1** | P3-11' 文档状态修正 | P0 | 无 | 0 (仅文档) | DECISIONS.md |
| **E2** | P3-10' migration_threshold 字段位置 + ADR-005 | P0 | 无 | ~5 | optimizer.py:150-158, DECISIONS.md |
| **E3** | P3-1' IC 时间加权 EWMA | P1 | 无 | ~8 | factor_metrics.py, optimizer.py |
| **E4** | P3-9' 目标函数对齐 ADR-004 (health_penalty 代理) | P1 | E3 | ~10 | optimizer.py (_composite_objective) |
| **E5** | P3-13 正交化参数纳入搜索空间 | P1 | E2 | ~8 | optimizer.py (DEFAULT_SEARCH_SPACE_ORTH) |
| **E6** | P3-14 几何诊断 (compute_vrr) + Adapter 扩展 | P2 | E5 | ~12 | adapters.py, optimizer.py |
| **E7** | P3-15 Layer 3 显著性最终验证 | P2 | E4 | ~6 | optimizer.py (_validate_significance) |
| **E8** | P3-12' 阈值漂移监测 (ThresholdDriftMonitor) | P2 | E4 | ~10 | backtest/threshold_drift_monitor.py (新建) |
| **E9** | 文档验证 + 全量回归 | P1 | E1-E8 | 8 项手工校验 | README/CHANGELOG/CODE_WIKI/DECISIONS |

**推荐执行顺序**: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9 (E1/E2/E3 可并行)

### 关键设计决策

1. **health_penalty 代理指标方案 (ADR-021)**: 用 IC decay/hit_rate/ic_vol 三档近似 health_score, 解决 HealthMonitorAdapter 仅能在回测后计算的时序依赖
2. **正交化搜索默认关闭 (ADR-022)**: `search_orth=False` 保持基线行为, 启用后搜索 orth_method/align_mode/ridge_lambda 三维度, 不搜索 orth_enabled
3. **FactorSignificanceTest 仅最终验证 (E7)**: 计算成本控制, 不参与每 trial 评估
4. **fidelity 符号修正 (E4)**: ADR-004 设计为惩罚 (`- ks_penalty`), 代码当前是奖励 (`+ lambda_fidelity * fidelity`), 需修正符号方向
5. **ThresholdDriftMonitor (ADR-023)**: EWMA 衰减检测, halflife=63, decay > 20% 触发 `needs_research=True`
6. **look-ahead bias 防护 (E5)**: 正交化参数搜索时必须在 CV fold 内部 fit (用 train 数据)

### 学术依据修正

| 任务 | v1.0 误引 | v1.1 修正 | 原因 |
|------|----------|----------|------|
| P3-1 IC 时间加权 | Cohen-Coval-Pastor (2005) | Ferson-Siegel (2001) | Cohen-Coval 讨论基金持仓相似度, 与 EWMA 无关 |
| P3-1 IC 时间加权 | Dimson/Moreira-Muir | Barroso-Santa-Clara (2015) | Dimson 是 beta 估计, Moreira-Muir 是 risk premium |
| P3-12 阈值漂移 | Hsu (2010) 误称 Bayesian | Sullivan-TW (1999) + McLean-Pontiff (2016) | Hsu (2010) 实际是 frequentist SDF |
| P3-11 参数重要性 | — | Bergstra (2011) TPE + Hutter (2014) fANOVA | 拆分原引用 |

### 风险与回退

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| health_penalty 代理与 health_score 相关性不足 | 中 | 目标函数引导偏差 | E4 手工校验 + A/B 测试 |
| 正交化搜索维度增加致 n_trials 不足 | 中 | 优化不收敛 | n_trials 从 100 提到 150-200 |
| FactorSignificanceTest 计算成本超预期 | 低 | E7 集成测试超时 | 仅最终验证, 不每 trial 评估 |
| fidelity 符号修正改变历史 best_score | 中 | 与 v2.5.0 best_score 不可比 | 文档标注 + 重新运行优化 |

**8 阶段独立回退方案**: 各阶段文件变更隔离, 失败可独立回退 (详见 EXECUTION_V2.6.0.md:1555-1566)

---

## v2.5.0 — 多因子正交化三层架构 (2026-07-03)

### 概览

实施 ADR-020: 多因子横截面正交化模块, 采用**三层架构分离** (Layer 1 per-factor / Layer 2 cross-factor 正交化 / Layer 3 target-aware 检验)。6 阶段 (O1-O6) 全部完成, 严格 TDD (Red → Green → 手工校验 → 回归测试), 每阶段严格 review。全量回归 860 passed + 5 skipped, 零回归 (比 v2.4.0 的 632 多 228 个测试)。

### O1: 算法核心 (阶段 1)

- **新增**: `modules/factor_orthogonalizer/core/` 5 种正交化器
  - `SymmetricOrthogonalizer` (Löwdin 1950): 默认主方法, `W = (F^T F)^(-1/2)`, VRR=1, 无顺序依赖
  - `RidgeOrthogonalizer`: 病态矩阵兜底, λ 自适应 (Ledoit-Wolf 2004)
  - `PCAOrthogonalizer`: 降维场景, center 参数兼容 Layer 1 标准化
  - `GramSchmidtOrthogonalizer`: 顺序依赖场景, κ>100 启用 Kahan (1966) 二次投影
  - `CholeskyOrthogonalizer`: 半正定保证场景
- **接口**: `BaseOrthogonalizer.fit_from_gram(G)` — 仅 Symmetric/Ridge/PCA 支持, 滚动场景避免重复构造 F
- **数值稳定**: dtype 强制 (int→float64, float32→float64), threshold_mode 三模式 (relative/absolute/auto), decomposition 选择 (eigh 默认 / svd κ>1e6 切换)
- **测试**: 44 单元测试 + 15 手工校验, 精度 < 1e-10

### O2: 适配器层 (阶段 2)

- **新增**: `OrthogonalizerAdapter` (在 `adapters.py`) + `CrossSectionalOrthogonalizer` (在 `modules/factor_orthogonalizer/cross_sectional.py`)
- **半侵入式接入**: `post_transform_hooks` 机制, `enabled=False` 时 `hooks=[]` 零开销, 不重构 Pipeline per-factor 架构
- **因子对齐**: `align_mode` 三模式 — `intersection` (默认, 取交集) / `union_nan` (取并集填 NaN) / `raise_on_mismatch` (严格抛错), 解决 Barra 41天 vs 日频 1212天不匹配
- **NaN 处理**: fit 时 dropna + 高比例 NaN 告警, transform 时 NaN 保留
- **W 缓存**: 全样本模式缓存 W, transform 时直接应用
- **测试**: 22 单元测试 + 12 手工校验, 全量回归 698 passed

### O3a: 几何诊断 (阶段 3a)

- **新增**: `modules/factor_orthogonalizer/diagnostics.py` — VRR/κ/VIF/正交性误差
- **VRR (方差保留比例)**: `VRR_k = Var(T_k)/Var(F_k)`, VRR << 1 表示因子 k 高度冗余; `ddof` 参数 (0=总体方差默认 / 1=样本方差滚动场景)
- **VIF 多方法**: `lstsq` (SVD, 默认) / `qr` (快 3-5x) / `pinv`, 三方法精度一致 < 1e-10, R²=1.0 时 inf 处理
- **条件数分级**: Belsley-Kuh-Welsch (1980) 四级 (good < 10, acceptable < 100, warning < 1000, severe ≥ 1000)
- **测试**: 18 单元测试 + 24 手工校验, 含 VRR 数学修正 (F 中心化 + 单位范数时 VRR=1)

### O3b: Layer 3 因子检验 (阶段 3b)

- **新增**: `backtest/factor_significance.py` — `FactorSignificanceTest`
- **双重 Lasso** (Belloni-Chernozhukov 2014 PDS): treatment 轮询模式, 每个因子独立当 treatment, 轮次顺序不影响结果
- **稳健标准误**: HC3 (默认) / HC1 / OLS, `cov_type` 参数选择
- **多重检验校正**: BH (Benjamini-Hochberg) FDR 控制 / Bonferroni 保守校正
- **Elastic Net**: α/λ 网格搜索, 处理多因子共线性
- **测试**: 17 单元测试 + 14 手工校验, 含 HC3 公式 bug 修复

### O4: 回测扩展 (阶段 4)

- **新增**: `modules/factor_orthogonalizer/rolling.py` — `RollingOrthogonalizer`
- **增量 Gram**: `window_` 滚动窗口 + `G_` 增量更新 (加入新 / 移除旧), 避免每期重复构造 F
- **reset_interval=500**: 每 500 期从 window_ 重新堆叠 G, 消除累积浮点误差 (~1e-13)
- **is_orthogonalized 标记**: `(T,)` bool 数组, 记录每期是否真正正交化 (区分"未正交化"vs"正交化后")
- **无 look-ahead bias**: 用 `[t-window, t-1]` 数据估计 W_t, 应用到 F_t
- **ICChangeMonitor**: 正交化前后 IC 变化监控
- **测试**: 11 单元测试 + 19 手工校验

### O5: 协同验证 (阶段 5)

- **新增**: `modules/factor_orthogonalizer/grouped.py` + `triple_chain.py`
- **GroupedOrthogonalizer**: 分组正交化 (按行业/板块等)
- **TripleChainCoordinator**: Factor_Fingerprint (描述) → Factor_Decoupler (时序解耦) → Orthogonalizer (横截面正交化) 三件套串联
- **数据流协议**: O5.6.1 明确三件套数据流, O5.6.2 中性化顺序, O5.6.3 缺失因子处理, O5.6.4 缓存, O5.6.5 冲突解决
- **测试**: 15 单元测试 + 17 手工校验

### O6: 文档验证 (阶段 6)

- **版本号统一**: 8 处同步为 2.5.0 (pyproject.toml / __init__.py / config_v2.py / reporting.py + 4 测试文件)
- **ADR-020 状态更新**: DECISIONS.md 中 "实施中" → "已实施"
- **project_memory.md**: 追加 21 项 ADR-020 约束清单 (8 基础 + 13 v1.1 工程深化) + 5 条 v2.5.0 经验
- **手工校验脚本**: `tests/manual/verify_v2_5_0_manual.py` 5/5 通过
  1. SymmetricOrthogonalizer 精度 < 1e-10 (与独立 numpy eigh 对比)
  2. FactorSignificanceTest 精度 < 1e-6 (与独立 statsmodels OLS 对比)
  3. VRR = 1.0 (精度 1e-10)
  4. treatment 轮询顺序不变性 (正序 vs 反序)
  5. RollingOrthogonalizer 无 look-ahead bias (t=0 原值, t=100 已正交)
- **全量回归**: 860 passed + 5 skipped + 0 failed

### 技术债修复

- **问题**: `tests/manual/test_adapter_manual.py:test_disabled_adapter_no_import` 无 try/finally 保护 `del sys.modules[m]`, 导致后续 `test_import_from_core` 重新导入时类对象 id 改变, `assert S is SymmetricOrthogonalizer` 失败
- **诊断**: 比较 `id(class)` (collection 时绑定) 与 `id(sys.modules[module].class)` (运行时获取), 不相等即模块对象被替换
- **修复**: 添加 try/finally 恢复 sys.modules, 与 `tests/test_factor_orthogonalizer/test_adapter.py` 安全版本一致

### 测试汇总

| 阶段 | 单元测试 | 手工校验 | 累计全量回归 |
|------|---------|---------|------------|
| O1 算法核心 | 44 | 15 | 676 passed |
| O2 适配器 | 22 | 12 | 698 passed |
| O3a 几何诊断 | 18 | 24 | 716 passed |
| O3b Layer 3 | 17 | 14 | 733 passed |
| O4 回测扩展 | 11 | 19 | 744 passed |
| O5 协同验证 | 15 | 17 | 759 passed |
| O6 文档验证 | 0 | 5 | **860 passed + 5 skipped** |
| **合计** | **127** | **106** | — |

### 经验教训

- **sys.modules 删除后未恢复是 class identity (is 检查) 失败的隐蔽根因**: 测试中 `del sys.modules[k]` 删除模块后, 后续测试重新导入会创建新模块对象 (新 id), 但 collection 时模块顶部 `from ... import Class` 绑定的是旧模块对象的类, 导致 `assert S is SymmetricOrthogonalizer` 失败
- **tests/manual/ 目录会被 pytest 默认收集**: manual 测试必须与正式测试同等严格地清理 sys.modules
- **诊断模块对象替换的方法**: 比较 `id(class)` (collection 时绑定) 与 `id(sys.modules[module].class)` (运行时获取), 若不相等则模块对象已被替换
- **v2.5.0 三层架构分离避免了单层混层陷阱**: 双重 Lasso 属 Layer 3 (需 Y), 不与 Layer 2 无监督变换混层, 正交化作为独立后处理层不重构 Pipeline per-factor 架构

---

## v2.4.0 — 外部模块内化 (2026-07-03)

### 概览

将 5 个处理模块 (Factor_Fingerprint / Factor_Decoupler / Factor_AdaptiveWinsor / Factor_Imputer / Factor_Neutralizer) 从外部独立仓库内化到 `factor_pipeline/modules/` 子包,保留 Factor_DB 和 Factor_Trading 作为外部数据边界。5 阶段全量回归始终 632 passed 零回归。全部采用严格 TDD (Red → Green → 手工校验 → 回归测试),每阶段完成后严格 review。

### I1: Factor_Fingerprint + Factor_Decoupler 内化 (阶段 1)

- **问题**: 两个模块零新增依赖,但 import 路径分散,命名不规范 (Factor_Fingerprint vs factor_fingerprint)
- **修复**: 内化到 `modules/factor_fingerprint/` 和 `modules/factor_decoupler/`,统一小写蛇形命名,~45 处 import 替换
- **测试**: 全量回归 632 passed, 0 新增失败

### I2: Factor_AdaptiveWinsor 内化 (阶段 2)

- **问题**: 模块含 batch/parallel/pipeline/report 等未使用子包,全量内化引入冗余依赖
- **修复**: 最小子包化策略 — 只迁 core/ 子集 (3 个类),新增 scikit-learn REQUIRED 依赖
- **测试**: 全量回归 632 passed, 0 新增失败
- **手工校验**: 依赖上界冲突检测 (pyextremes 声明 pandas<3.0.0 会自动降级,需预检)

### I3: Factor_Imputer 内化 (阶段 3)

- **问题**: 目录名含 "." (Factor_Imputer_v2.0) 需 PyPI 规范化,函数内 try/except + sys.path hack 双重导入模式隐蔽
- **修复**: 移除 `_v2_0` 版本后缀,Grep 全文搜索发现 22 处导入 (调研预估仅 4 处),清理 try/except + sys.path hack 为单一相对导入
- **测试**: test_p2_fixes.py 使用 Factor_Imputer 作为测试目标自动跳过 (正确行为,非回归)
- **回归**: 632 passed, 0 新增失败

### I4: Factor_Neutralizer 内化 (阶段 4)

- **问题**: src-layout 结构,重依赖 (matplotlib/joblib/psutil/numba),38 方法但主项目只需类可导入
- **修复**: src-layout → flat-layout,重依赖改 try/except 可选导入 + HAS_XXX 标记,添加 `from __future__ import annotations` 解决 plt.Figure 类型注解导入时求值问题
- **测试**: 旧包卸载后新路径导入验证通过,全量回归 632 passed
- **手工校验**: `from factor_pipeline.modules.factor_neutralizer.core import FactorNeutralizer` 导入正常

### I5: CI/文档清理 (阶段 5)

- **问题**: CI monorepo 模拟仍 clone 7 个外部模块,历史批量修复脚本失效,版本号不统一
- **修复**:
  - CI monorepo 模拟从 7 个外部模块缩减为 2 个 (Factor_DB/Factor_Trading)
  - 删除 7 个失效批量修复脚本 (fix_external_imports / fix_factoradaptivewinsor_internal_imports / 等)
  - 版本号统一 11 处 (pyproject.toml + __init__.py + config_v2.py + reporting.py + 4 个测试文件 + 2 个校验脚本)
- **测试**: verify_fix3_manual.py "旧版本残留"检查发现内化模块自身 __version__ (正确行为,非问题)
- **回归**: 632 passed, 5 skipped, 0 failed

### 测试汇总

| 阶段 | 模块 | 回归测试 | 手工校验 |
|------|------|----------|----------|
| I1 | Fingerprint + Decoupler | 632 passed | — |
| I2 | AdaptiveWinsor | 632 passed | 依赖上界检测 |
| I3 | Imputer | 632 passed | 导入路径验证 |
| I4 | Neutralizer | 632 passed | 导入验证 + 路径检查 |
| I5 | CI/文档清理 | 632 passed, 5 skipped | 版本号 11 处统一 |
| **总计** | 5 模块内化 | **632 passed 零回归** | — |

### 经验教训

1. **模块独立性对独立分发才有价值**: 单仓库场景下独立性是虚假收益,内化优于子包化 (ADR-019)
2. **命名一致性是长期维护成本的关键驱动因素**: 目录名/Python 包名/PyPI 名三套命名并存时,每个新开发者/CI 配置都要付出认知成本
3. **依赖上界冲突是隐蔽陷阱**: pyextremes 声明 `pandas>=1.0.0,<3.0.0`,pip install 会自动降级 pandas 3.0.3→2.3.3 而非报错,悄悄破坏 backtest 模块
4. **函数内导入比模块级导入更难发现**: 调研发现 4 处模块级绝对导入,实际 Grep 发现 22 处 (含 16 处函数内 try/except + sys.path hack 双重导入)
5. **plt.Figure 类型注解在导入时求值是隐蔽陷阱**: 无 `from __future__ import annotations` 时,`plt=None` 会导致类型注解在类定义阶段 AttributeError

---

## v2.3.0 — 跨版本 CI 矩阵 (2026-07-02)

### 概览

建立双轨 CI (GitHub Actions 远程 + tox 本地),覆盖 Python 3.10/3.11/3.12 × ubuntu-latest 矩阵,保障跨版本兼容性。CI 配置文件脚本校验 37/37 通过。

### P4.1: CI 现状调研

- **问题**: 无 .github/workflows,无 tox.ini,pyproject 声明 >=3.9 (3.9 EOL 临近)
- **调研**: 确认主项目依赖 (numpy/pandas/scipy/statsmodels/sklearn) 全部支持 3.10-3.12

### P4.2: CI 矩阵策略设计

- **决策**: GitHub Actions + tox 双轨,Python 3.10/3.11/3.12 × ubuntu-latest
- **Windows 排除**: spawn 方法进程启动开销使小数据量并行性能测试不可靠 (ADR-016)
- **fail-fast: false**: 一个 Python 版本失败不阻塞其他版本继续跑

### P4.3a: GitHub Actions workflow

- **文件**: `.github/workflows/ci.yml`
- **设计**: 矩阵 + 外部模块 git clone + 目录重命名 (匹配 pyproject.toml package-dir 映射)
- **校验**: YAML 语法 + 矩阵维度 + 步骤顺序脚本校验

### P4.3b: tox.ini 双轨本地 CI

- **文件**: `tox.ini`
- **设计**: py310/py311/py312 + lint + coverage 环境
- **deps 字段**: 声明 editable 安装路径 (-e {toxinidir}/../Factor_DB),每 env 独立安装外部模块保证隔离性
- **changedir**: 设为 {toxinidir}/.. 从父目录运行 pytest,避免 types.py 遮蔽 stdlib

### P4.4: 本地验证 CI 配置正确性

- **脚本校验**: 37/37 校验通过 (YAML 语法 + INI 语法 + 矩阵维度 + 步骤顺序)
- **回归测试**: 21/21 通过
- **关键校验**: CI 配置文件必须用脚本校验语法正确性,不能假设配置生效

### 测试汇总

| 校验项 | 数量 | 状态 |
|--------|------|------|
| YAML 语法校验 | 12/12 | ✅ |
| INI 语法校验 | 8/8 | ✅ |
| 矩阵维度校验 | 5/5 | ✅ |
| 步骤顺序校验 | 7/7 | ✅ |
| 回归测试 | 21/21 | ✅ |
| **总计** | **37/37 + 21/21** | ✅ |

### 经验教训

1. **双轨 CI 优于单轨**: 远程 (GitHub Actions) 保障推送质量,本地 (tox) 快速验证跨版本兼容性
2. **CI 配置文件必须脚本校验**: 不能假设配置生效,P4.4 37/37 校验通过证明
3. **tox changedir 解决 types.py 遮蔽**: 从父目录运行 pytest 避免 cwd 内 types.py 遮蔽 stdlib types 模块
4. **Windows spawn 方法开销**: 小数据量并行性能测试在 Windows 不可靠,应 skipif 而非改阈值

---

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