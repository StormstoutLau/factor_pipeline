# 开发日志 (Changelog)

## v3.3.6 — PL-05 Dynamic AR 因果性修复: 三段式一步预测 (已实施, 2026-11-04)

### 概览

修复 DEFECT-PL-05: `ARDecoupler.fit` 用全样本 AIC 选阶 + 全样本 OLS，`transform` 用 `fitted_values.reindex().ffill()` 充当一步预测——阶数、系数、预测值三层均依赖未来数据。

**核心产出**:
- `fit` 只用前 `warmup_obs=120` 行估计阶数与系数（冻结模型）
- `transform` 三段式因果一步预测: 冷启动 identity → 固定 `min_order` → 全阶 AIC 每 `stride=10` 行重估 → `t >= warmup_obs` 冻结预测
- 移除 `_results` 列门控与 `fitted_values.reindex().ffill()`；NaN 经滞后自然传播
- `AROrderSelector.fit` 拆出无日志 `_fit_best`，供 warm-up 批量复用
- 新增 10 个单测函数（16 个 pytest 用例）；集成套件摘除 PL-05/PL-07 `xfail`，新增 3 组路由因果性测试
- 新增 **ADR-040**；项目版本 **3.3.6**；缓存 `CODE_VERSION` **v2.2.4-cache**

### 缺陷根因

| # | 根因 | 证据 |
|---|------|------|
| 1 | `fit` 全样本 AIC 选阶 | 阶数随 T 变化，前 t 期阶数依赖 t 之后数据 |
| 2 | `_fit_ar` 全样本 OLS 估系数 | 系数随 T 变化 |
| 3 | `transform` 用 `fitted_values.reindex().ffill()` 当一步预测 | 预测值直接来自全样本拟合（样本内） |
| 4 | `transform` 以 `_results` 存在性整列门控 | 前缀有效观测不足时整列退化为 identity，掩盖早期前视 |

**为何长期未被发现**: 旧输出前导 NaN 使截断前后 NaN 模式一致；样本内残差 `mean_ar1 ≈ 0.0029` 看似"去相关更好"，实为过拟合幻觉（因果实现为 0.0302，仍显著优于原始 0.7025）。

### 实测矩阵 (`T=100, N=30, seed=22, kind='ar_low', t=60, atol=1e-12`)

| 层级 | 对象 | 修复前 | 修复后 |
|------|------|--------|--------|
| pipeline | Dynamic 端到端 | 1653/1800 格 + 8 NaN, 8.045e-01 | **0 / 0 / 0** |
| top | FactorProcessingPipelineV2 | 1650 格, 1.8397 | **0 / 0**（路由全程一致） |
| 诊断 | 违反 / 满足 / 合计 | 1 / 8 / 9（仅 Dynamic FAIL） | **0 / 9 / 9** |
| unit | 新契约测试 | 15 failed / 1 passed (Red) | **16 passed**（10 函数） |
| integration | 截断不变式套件 | 10 passed / 2 xfailed | **15 passed / 0 xfailed** |

**输出与 NaN**（`T=100, N=30, seed=7`，新旧实现同进程对比）:

| 面板 | 对象 | 变化格子 | `max_abs` | `mean_abs` | NaN |
|------|------|---------|-----------|------------|-----|
| iid | AR | 2854/3000 | 3.7255 | 0.2626 | 146 → 0 |
| iid | Dynamic | 2855/3000 | 2.1038 | 0.2287 | 145 → 0 |
| ar70 | AR | 2851/3000 | 4.1873 | 0.3486 | 149 → 0 |
| ar70 | Dynamic | 2852/3000 | 2.7665 | 0.2829 | 148 → 0 |

**质量**（AR(1) φ=0.7, `T=500, N=30, seed=42`, 统计起点第 60 行）: `mean_ar1` 原始 0.7025 / 旧 0.0029 / 新 **0.0302**（K=120）。

**性能**（2500×300）: AR 单步 `0.48s → 2.10–5.23s`（6 次复测中位 ≈2.24s；单次负载离群 6.25s）；Dynamic 全管线（含行业）`33.19s → 39.29s`（+18.4%）。

### 变更文件

| 文件 | 变更 |
|------|------|
| [modules/factor_decoupler/core/ar_model.py](modules/factor_decoupler/core/ar_model.py) | `_fit_best` 拆分; `warmup_obs` + 校验; `fit` 前缀窗口; `transform` 三段式 + `_predict_one_step`; `_WARMUP_REFIT_STRIDE`; docstring |
| [tests/unit/test_ar_decoupler_causality.py](tests/unit/test_ar_decoupler_causality.py) | **新增** 10 个函数 / 16 个用例 |
| [tests/integration/test_pipeline_truncation_invariance.py](tests/integration/test_pipeline_truncation_invariance.py) | 摘除 PL-05/PL-07 xfail; 新增 3-seed 路由测试; 更新登记表 |
| [tests/test_factor_decoupler/test_hidden_effect.py](tests/test_factor_decoupler/test_hidden_effect.py) | φ 断言容差 0.05 → 0.15（n=120 覆盖率 50.3% → 94.8%）; 追加区间断言 |
| [tests/test_fix3_version_unification.py](tests/test_fix3_version_unification.py) / [tests/test_backtest/verify_fix3_manual.py](tests/test_backtest/verify_fix3_manual.py) | 版本锚点 → 3.3.6; 缓存字面量 → v2.2.4-cache |
| [pyproject.toml](pyproject.toml) / [__init__.py](__init__.py) / [config_v2.py](config_v2.py) / [reporting.py](reporting.py) | 版本 → 3.3.6 |
| [backtest/cache_manager.py](backtest/cache_manager.py) | `CODE_VERSION` → v2.2.4-cache |
| [DECISIONS.md](DECISIONS.md) | 新增 ADR-040 + 占用登记 |
| [docs/analysis/PL05_DYNAMIC_AR_LOOKAHEAD_RESEARCH.md](docs/analysis/PL05_DYNAMIC_AR_LOOKAHEAD_RESEARCH.md) / [docs/analysis/PL05_DYNAMIC_AR_LOOKAHEAD_DESIGN.md](docs/analysis/PL05_DYNAMIC_AR_LOOKAHEAD_DESIGN.md) / [docs/EXECUTION_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md](docs/EXECUTION_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md) | 调研/设计/实施文档, 状态更新为已实施 |

### 兼容性与缓存

- **行为变更**: Dynamic 输出约 95% 格子改变；历史 IC/Sharpe 需重算。
- **NaN 语义**: AR 冷启动由 NaN 改为 identity（`t < max(min_order+6, 2)` 不做解耦），输出不再有前导 NaN。
- **参数**: `ARDecoupler` 新增公开参数 `warmup_obs=120`，必须严格大于 `min_obs`；其余参数语义不变。
- **缓存代际**: `v2.2.3-cache` → `v2.2.4-cache`。读取时 `meta.code_version` 不一致即 MISS 并删除旧数据/meta。

### 已知遗留

- `OptimizedARDecoupler` / `TemporalDecoupler` 仍为旧实现（非生产路径，同类缺陷不覆盖）。
- `_fit_ar` 各阶数 `n_obs = n - order` 不同，AIC 跨阶数不可比（statsmodels `hold_back >= maxlag`），登记 `PL-08-candidate`，不纳入本次。
- 指纹路由分类逻辑本身未改；路由因果性仅由 3-seed 测试守卫。
- 冻结模型对非平稳因子的失配风险未做专项回测。

---

## v3.3.5 — PL-06 Mixed 缩尾因果性修复: 逐日截面 3σ (已实施, 2026-11-04)

### 概览

修复 DEFECT-PL-06: `MixedFactorPipeline._compute_winsorize_params` 用 `X.mean(axis=0)` / `X.std(axis=0)` 按股票全历史估计 3σ 边界，`fit` 保存、`transform` 复用——前 t 期边界依赖 t 之后的数据。

**核心产出**:
- 缩尾边界改为**逐日截面 3σ**（`mu = X.mean(axis=1)`, `sd = X.std(axis=1, ddof=1)`, `clip(axis=0)`），`fit()` 无跨期参数
- 删除 `_compute_winsorize_params`；`_winsorize_params` 保留为 `None` 状态标记
- `mixed_winsor_sigma` / `transform_aggressiveness` / optimizer 搜索空间契约不变；无配置迁移
- 新增 11 例单测；重写 `TestMixedWinsorSigma` test_07/08/09；集成套件由 `9 passed / 3 xfailed` 变为 `10 passed / 2 xfailed`
- 新增 **ADR-039**；项目版本 **3.3.5**；缓存 `CODE_VERSION` **v2.2.3-cache**

### 缺陷根因

| # | 根因 | 证据 |
|---|------|------|
| 1 | `_compute_winsorize_params` 按股票（`axis=0`）用全历史 mean/std 估计 3σ | 截断 60/100 期：257/1800 格差异，`max_abs_diff=6.984e-01`，首个发散日 2020-01-31 |
| 2 | `fit` 保存边界、`transform` 复用 | 前 t 期边界依赖未来；`transform` 单独调用同样复用 fit 参数 |
| 3 | 缩尾位于 neutralize / rank 之前 | 通过改变中性化输入间接影响排序；即使后续 rank 也非"无影响" |

**为何长期未被发现**: 截断前后逐日 Spearman 中位 0.999555（最小 0.984872），排序几乎一致；只有值相等的截断不变式能暴露。

### 实测矩阵 (`T=100, N=30, seed=23, kind='skewed', t=60, atol=1e-12`)

| 层级 | 对象 | 修复前 | 修复后 |
|------|------|--------|--------|
| pipeline | Mixed 端到端 | 257/1800 格, 6.984e-01 | **0 / 0** |
| 诊断 | Mixed 行 | FAIL | **PASS** |
| 诊断 | 违反 / 满足 / 合计 | 4 / 5 / 9 | **1 / 8 / 9**（仅 PL-05） |
| pipeline | Dynamic | 1653 格 + 8 NaN, 8.05e-01 | 不变（PL-05） |
| top | FactorProcessingPipelineV2 | 1650 格, 1.84e+00 | 不变（PL-05 + 指纹路由） |

**相对旧实现的全样本输出差异**（同面板，含行业中性化）：561/3000 格，`max_abs=1.0446`，63/100 行；逐日 Spearman 中位 0.999110 / 最小 0.942603。**缩尾触发率**：61/3000（2.03%）→ 77/3000（2.57%）。

**性能**（`T=2500, N=3000`，3 次中位）：`0.281s → 0.184s`（0.175 / 0.184 / 0.193）。

### 变更文件

| 文件 | 变更 |
|------|------|
| [pipelines_v2.py](pipelines_v2.py) | `fit` Step 2 no-op; `_apply_winsorize` 逐日截面; 删除 `_compute_winsorize_params`; 类/方法 docstring |
| [tests/unit/test_mixed_winsorize_cross_sectional.py](tests/unit/test_mixed_winsorize_cross_sectional.py) | **新增** 11 例 |
| [tests/test_p3_phase2_config_migration.py](tests/test_p3_phase2_config_migration.py) | 重写 `TestMixedWinsorSigma.test_07/08/09` |
| [tests/integration/test_pipeline_truncation_invariance.py](tests/integration/test_pipeline_truncation_invariance.py) | 摘除 PL-06 xfail; 更新登记表与 PL-07 reason |
| [tests/test_fix3_version_unification.py](tests/test_fix3_version_unification.py) / [tests/test_backtest/verify_fix3_manual.py](tests/test_backtest/verify_fix3_manual.py) | 版本锚点 → 3.3.5; 缓存字面量 → v2.2.3-cache |
| [pyproject.toml](pyproject.toml) / [__init__.py](__init__.py) / [config_v2.py](config_v2.py) / [reporting.py](reporting.py) | 版本 → 3.3.5 |
| [backtest/cache_manager.py](backtest/cache_manager.py) | `CODE_VERSION` → v2.2.3-cache |
| [DECISIONS.md](DECISIONS.md) | 新增 ADR-039 + 占用登记 |
| [docs/analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md](docs/analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md) / [docs/analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_DESIGN.md](docs/analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_DESIGN.md) / [docs/EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md](docs/EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md) | 调研/设计/实施文档, 状态更新为已实施 |

### 兼容性与缓存

- **行为变更**: 所有 Mixed 输出数值改变；历史 IC/Sharpe 需重算。
- **配置**: 无迁移；`mixed_winsor_sigma` / `transform_aggressiveness` 语义不变。
- **缓存代际**: `v2.2.2-cache` → `v2.2.3-cache`。读取时 `meta.code_version` 不一致即 MISS 并删除旧数据/meta。
- **小截面**: `N<=10` 时 3σ 永不触发（数学性质）；`N=1` / 全 NaN / 零离散度原样返回。不引入数据触发的 pre-test。

### 已知遗留

- PL-05（Dynamic AR `fitted_values`）与 PL-07（顶层指纹路由）仍登记为 `xfail`。
- B（逐日截面 percentile(1,99)）未实施；Mixed 3σ 与 Static percentile 的方法差异登记为已知遗留。
- optimizer 未在输出变更后重新调参，另行评估。

---

## v3.3.4 — PL-02 变换因果性修复: 逐日截面 rank→正态 (已实施, 2026-10-22)

### 概览

修复 DEFECT-PL-02 / PL-04: `ProcessingAdapter(process_type='transformation')` 的 `fit()` 用 `X.values.flatten()` 在全 panel 上估计 λ / offset / 经验 CDF，`auto_optimize=True` 覆盖显式方法，且 `_select_optimal_transform` 依赖全样本 skew/kurt/Shapiro p 选型——前 t 期输出依赖 t 之后的数据。

**核心产出**:
- 变换改为**逐日截面 rank → 目标分布**（默认 Blom 正态分数），`fit()` 无状态，结构上无参数可泄漏
- `auto` → `rank`，删除 `auto_optimize` 与整条选型/拟合链；`quantile` 作为 `rank` 配置别名
- `log` / `boxcox` / `yeojohnson` / `power` 保留为先验参数模式（`lam` / `power_param` 必填，禁止 fit 估计）
- `TransformationConfig` 接线到 Static/Mixed v2 管线；删除 `mixed_conditional_transform` / `mixed_skew_threshold` / `mixed_kurt_threshold`
- Mixed 顺序切为 neutralize → transform（I-INT）
- 新增 32 例单测；集成套件由 `7 passed / 5 xfailed` 变为 `9 passed / 3 xfailed`
- 新增 **ADR-038**；项目版本 **3.3.4**；缓存 `CODE_VERSION` **v2.2.2-cache**

### 缺陷根因 (四层叠加)

| # | 根因 | 证据 |
|---|------|------|
| 1 | `fit()` 用 `X.values.flatten()` 在全 panel 上估计 λ / offset / 经验 CDF | 截断 60/100 期: 1800 格差异, `max_abs_diff=8.51e-04` |
| 2 | `auto_optimize=True` 覆盖显式方法; 选型依赖全样本 skew/kurt/Shapiro p | 方法选择不可复现; Shapiro 子采样未设种子 |
| 3 | Mixed 用全样本 `skew().median()` / `kurtosis().median()` 做条件变换 | 属于 pre-test 式在线切换, 估计量分布不可一致估计 |
| 4 | `TransformationConfig` 未接线到 v2 管线 | 配置名义存在但实际由三个 `mixed_*` 字段独立控制 |

**为何长期未被发现**: 变换是保序的。前视与截断输出的排序一致，Spearman 类指标无感；只有值相等的截断不变式能暴露。

### 实测矩阵 (`T=100, N=30, t=60, atol=1e-12`)

| 层级 | 对象 | 修复前 | 修复后 |
|------|------|--------|--------|
| step | transform auto | 1800 格, 8.51e-04 | **0 格, 0** |
| pipeline | Static | 1800 格, 4.72e-05 | **0 格, 0** |
| pipeline | Mixed | 1800 格, 2.91e-01 | 257 格, 6.98e-01（剩余仅 PL-06 全样本缩尾） |
| pipeline | Dynamic | 1653 格 + 8 NaN, 8.05e-01 | 不变（PL-05，不含变换步骤） |
| top | FactorProcessingPipelineV2 | 1650 格, 1.84e+00 | 不变（PL-05/06 + 指纹路由） |

诊断报告: 违反 2 项 / 满足 7 项 / 合计 9 项（修复前为违反 4 项 / 满足 5 项）。

**性能** (`T=2500, N=3000, t(3), NaN 5%`): `rankdata` 逐行 1.040s（设计基准 1.071s，−2.9%）；`ProcessingAdapter.transform` 1.075s；`normal` 中位列 std 0.9991712；`uniform` 0.5773502（理论 `1/√3`）；helper 与 adapter 输出 `max |diff| = 0`。

### 变更文件

| 文件 | 变更 |
|------|------|
| [modules/factor_adaptive_winsor/core/transformers.py](modules/factor_adaptive_winsor/core/transformers.py) | 模块级 `rank_transform_1d` + 别名常量; `AdaptiveTransformer` 无状态重写; 删除选型链与 `_fit_*` |
| [adapters.py](adapters.py) | PL-02 常量; 构造期方法解析; `fit` no-op; `transform` identity 短路与截面 rank; `get_stats` |
| [config_v2.py](config_v2.py) | `TransformationConfig` 收敛 + `target_distribution`; 删除 `conditional_transform`; 桥接映射 |
| [pipelines_v2.py](pipelines_v2.py) | `PipelineV2Config` 四字段; Static/Mixed 入参; Mixed 顺序; 删除 `_diagnose_transform_need` |
| [demo_v2.py](demo_v2.py) | 删除 2 处 `mixed_conditional_transform=True` |
| [tests/unit/test_transform_rank_cross_sectional.py](tests/unit/test_transform_rank_cross_sectional.py) | **新增** 28 函数 / 32 例 |
| [tests/unit/test_adaptive_transformer_identity.py](tests/unit/test_adaptive_transformer_identity.py) | **重写** 为 rank/先验方法行为测试 (9 例) |
| [tests/integration/test_pipeline_truncation_invariance.py](tests/integration/test_pipeline_truncation_invariance.py) | 摘除 PL-02/PL-04 xfail; 更新登记表与 PL-06/PL-07 reason |
| [tests/test_fix2_config_unification.py](tests/test_fix2_config_unification.py) | `test_09` / `test_11` 改用 `transformation.method/target_distribution` |
| `tests/test_pipelines_v2.py` / `tests/test_p3_phase2_config_migration.py` / `tests/test_adapters/test_module_enabled.py` | 删除已废弃字段; rank 无状态契约 |
| `tests/test_backtest/verify_fix2_manual.py` / `verify_fix3_manual.py` | 字段与版本锚点同步 |
| [tests/test_fix3_version_unification.py](tests/test_fix3_version_unification.py) | `EXPECTED_VERSION` → 3.3.4; 缓存断言 → v2.2.2-cache |
| [pyproject.toml](pyproject.toml) / [__init__.py](__init__.py) / [config_v2.py](config_v2.py) / [reporting.py](reporting.py) | 版本 → 3.3.4 |
| [backtest/cache_manager.py](backtest/cache_manager.py) | `CODE_VERSION` → v2.2.2-cache |
| [DECISIONS.md](DECISIONS.md) | 新增 ADR-038 + 占用登记 |
| [docs/analysis/PL02_TRANSFORM_LOOKAHEAD_RESEARCH.md](docs/analysis/PL02_TRANSFORM_LOOKAHEAD_RESEARCH.md) / [..._DESIGN.md](docs/analysis/PL02_TRANSFORM_LOOKAHEAD_DESIGN.md) | 调研/设计文档, 状态更新为已实施 |

### 兼容性与缓存

- **行为变更**: Static/Mixed 变换输出全部改变（逐日截面 rank，不再池化拟合与自选方法）；依赖旧变换数值的存量结果与缓存失效。
- **配置字段删除**: `PipelineV2Config.mixed_conditional_transform` / `mixed_skew_threshold` / `mixed_kurt_threshold` 与 `MixedPipelineConfig.conditional_transform`、`TransformationConfig.skew_threshold` / `kurt_threshold` 已删除。Pydantic 默认 `extra='ignore'`，旧 JSON/YAML 不会报错，但字段被**静默忽略**——尤其 `conditional_transform=False` 的原意是禁用变换，现在仍会执行 `rank`。原语义需迁移为 `transformation.method='identity'`。
- **显式方法**: `boxcox` / `yeojohnson` 现在必须提供 `lam`，`power` 必须提供 `power_param`；不再自动拟合。旧配置若依赖 auto 拟合，将得到 `ValueError`。
- **缓存代际**: `v2.2.1-cache` → `v2.2.2-cache`。`CacheManager.get_with_meta` 读取时校验 `meta.code_version`，不一致即 MISS 并删除旧数据/meta；首次访问旧缓存自动重建。
- **小截面**: 截面有效观测 `N<10` 回落逐日截面 z-score；`N<2` 原样返回（仅保护，不改变方法语义）。
- **ties**: 平均秩 → 相同输出值；排序不受影响。

### 实施偏差记录 (2026-10-22)

1. `tests/test_adapters/test_module_enabled.py::test_transformation_enabled_ignored_in_processing`：原断言 `fit` 后 `_processor is not None`；rank 无状态后改为断言 `_processor is None` 且 `transform` 确实改变数值，保持“transformation 不可消融”的原意。
2. `tests/test_pipelines_v2.py::test_neutralize_before_transform_reduces_industry_correlation`：旧顺序包含最后一步 OLS 中性化，R² 构造性为 0；新顺序 `neutralize→rank` 因非线性使 R² 轻微抬升（seed=999 实测 0.0057）。阈值由 `+0.005` 调整为 `+0.02`（仍为“行业信号基本消除”上限）。
3. `tests/unit/test_transform_rank_cross_sectional.py` 的有限样本矩断言按精确公式计算（`uniform` std `sqrt((N+1)/(3N))`；`normal` std 取 Blom 分数样本矩），而非极限值 `1/√3` / `1`。
4. `tests/unit/test_adaptive_transformer_identity.py` 的 `normal` std 同样改为 Blom 分数精确样本矩（N=2000 时 `0.9988613`，极限值差 `1.14e-3`）。

---

## v3.3.3 — PL-01 去极值因果性修复: 逐日横截面 (已实施, 2026-10-22)

### 概览

修复 DEFECT-PL-01: `ProcessingAdapter(process_type='outlier')` 的缩尾参数在全 panel 上池化拟合，且 `SmartOutlierDetector(auto_select=True)` 会覆盖显式方法——前 t 期输出依赖 t 之后的数据，同时名义上的 `percentile(1,99)` 实际按全样本特征自选方法执行。

**核心产出**:
- 去极值改为**逐日横截面**：每行只使用当日数据；`fit()` 对 outlier 成为 no-op，结构上无参数可泄漏
- `method='auto'` 构造期解析为 `percentile`；显式方法按声明执行；detector 侧始终 `auto_select=False`
- `percentile` 走向量化快速路径（2500×3000 面板 0.212–0.226s，逐行循环 2.56s）；其他方法逐行复用 detector，保留原截断语义
- 新增 30 项单测；集成套件由 `6 passed / 6 xfailed` 变为 `7 passed / 5 xfailed`（PL-01 摘除 xfail）
- 新增 **ADR-037**；项目版本 **3.3.3**；缓存 `CODE_VERSION` **v2.2.1-cache**（读取时校验代际，旧缓存自愈失效）
- 关联回归: 37 passed / 5 xfailed（新单测 + 集成）；适配器回归 38 passed / 2 skipped；缓存相关 91 passed

### 缺陷根因 (三层叠加)

| # | 根因 | 证据 |
|---|------|------|
| 1 | `fit()` 用 `X.values.flatten()` 在全 panel 上拟合缩尾参数 | 截断 60/100 期: 187 格差异, `max_abs_diff=1.68e-01` |
| 2 | `auto_select=True` 用全 panel 分布特征覆盖显式 `method` | 显式 `percentile` 实际拟合 `mad`, `threshold=2.7725`; 200/200 个变波动率面板截断前后选型不同 |
| 3 | 管线配置的分位/阈值参数未被 adapter 消费 | 修复前经 `to_pipeline_config()` 传入，`fit()` 实例化 detector 时 `TypeError`；修复后不再报错，但字段仍被忽略（后续任务） |

这也是 **ADR-027 的实施缺口**: "所有 `auto` → 固定方法" 与 "Winsorizer percentile(1,99)" 早已决定，但 adapter 层未落实。

**为何长期未被发现**: 缩尾是单调变换。前视与截断输出的逐日 Spearman 中位数 = 1.000，最小值 = 0.9973；排序类指标几乎无感，只有值相等的截断不变式能暴露。

### 实测矩阵 (`T=100, N=30, t=60, atol=1e-12`)

| 层级 | 对象 | 修复前 | 修复后 |
|------|------|--------|--------|
| step | outlier percentile | 187 格, 1.68e-01 | **0 格, 0** |
| step | transform auto | 1800 格, 8.51e-04 | 1800 格, 8.51e-04（PL-02，未修） |
| pipeline | Static | 1800 格, 1.33e-02 | **1800 格, 4.72e-05**（残留仅 PL-02） |
| pipeline | Dynamic | 1653 格 + 8 NaN, 8.05e-01 | 不变（PL-05，不含 outlier 步骤） |
| pipeline | Mixed | 1800 格, 2.91e-01 | 不变（PL-06，使用自身全样本缩尾） |
| top | FactorProcessingPipelineV2 | 1650 格, 1.84e+00 | 不变（PL-07，含指纹路由） |

诊断报告: 违反 4 项 / 满足 5 项（修复前为违反 5 项 / 满足 4 项）。

### 变更文件

| 文件 | 变更 |
|------|------|
| [adapters.py](adapters.py) | outlier 常量 + 构造期解析/校验 + `fit` no-op + `transform` 分支 + 3 个 helper + `get_stats` 字段 |
| [tests/unit/test_outlier_cross_sectional.py](tests/unit/test_outlier_cross_sectional.py) | **新增** 15 项测试（参数化后 30 例）：方法解析 / 边界 / 因果性 / NaN / 小截面 / 零离散 / identity / 统计字段 |
| [tests/integration/test_pipeline_truncation_invariance.py](tests/integration/test_pipeline_truncation_invariance.py) | 移除 PL-01 xfail; 更新缺陷登记表与 PL-04/05/06/07 reason |
| [tests/test_fix3_version_unification.py](tests/test_fix3_version_unification.py) | 版本锚点 → 3.3.3; 缓存断言 → v2.2.1-cache |
| [pyproject.toml](pyproject.toml) / [__init__.py](__init__.py) / [config_v2.py](config_v2.py) / [reporting.py](reporting.py) | 版本 → 3.3.3 |
| `backtest/cache_manager.py` + 4 个缓存默认值 | `CODE_VERSION` → v2.2.1-cache |
| [DECISIONS.md](DECISIONS.md) | 新增 ADR-037 + 占用登记; ADR-029 追加后续测量 |
| [docs/analysis/PL01_OUTLIER_LOOKAHEAD_RESEARCH.md](docs/analysis/PL01_OUTLIER_LOOKAHEAD_RESEARCH.md) / [..._DESIGN.md](docs/analysis/PL01_OUTLIER_LOOKAHEAD_DESIGN.md) | 调研/设计文档, 状态更新为已实施 |

### 兼容性与缓存

- **行为变更**: 去极值输出数值改变（不再池化、不再自选方法），依赖旧缩尾数值的存量结果与缓存失效。
- **缓存代际**: `v2.2.0-cache` → `v2.2.1-cache`。`CacheManager.get_with_meta` 读取时校验 `meta.code_version`，不一致即 MISS 并删除旧数据/meta；`verify` 返回 `code_version mismatch`。首次访问旧缓存会自动重建；缓存版本仍不跟随项目版本。
- **单一来源**: 4 个子缓存默认值改为引用 `cache_manager.CODE_VERSION`，避免多处字面量漂移。
- **接口**: 无公开 API 破坏。`ProcessingAdapter(outlier)` 仍接受原参数；未知方法/非法分位改为构造期 `ValueError`（原为静默覆盖或延迟失败）。
- **小截面**: 行内有效观测 < 3 或零离散度时该行原样返回（不缩尾），与 detector 内部判据一致。

### 评审修订 (2026-10-22)

评审发现初版缓存 bump 只改了 `CODE_VERSION` 常量，但 `CacheManager.get/verify` 从未校验 `meta.code_version`，旧缓存仍会命中并返回修复前的数值。已补：

- `CacheManager.get_with_meta`: 代际不一致 → MISS + 删除旧数据/meta
- `CacheManager.verify`: 代际不一致 → `is_valid=False`
- 新增 `TestCodeVersionGeneration` 3 项单测 + `test_07` 五处默认值一致性测试
- 修正 ADR-037 中配置 `TypeError` 的发生位置（`fit` 而非桥接）、Arnott 等作者名单、性能实测口径

### 已知未修 (保持 xfail 登记)

- **PL-02**: 变换 `fit` 仍全 panel flatten 拟合 λ（8.51e-04）
- **PL-05**: 解耦器 AR 用样本内 `fitted_values` 充当 OOS 预测（8.05e-01, 8 NaN）
- **PL-06**: Mixed 自有 `_compute_winsorize_params` 全样本缩尾（2.91e-01）
- **PL-07**: 顶层叠加残留缺陷 + 指纹路由依赖全样本（1.84e+00）

---

## v3.3.2 — 管线级因果性测试 + 标准化因果性修复 + ADR 编号治理 (已实施, 2026-10-21)

### 概览

接续 Claude 外部评审对新管线级缺陷的指认, 本轮不以"修某个函数"为起点, 而是先建立**可证伪的因果性测量仪器**, 由测试暴露问题清单, 再按实测幅度决定修复顺序。同时清理长期存在的 ADR 编号冲突与未记录的已实施决策。

**核心产出**:
- 新增管线级**截断不变式测试** (12 项, 6 通过 / 6 登记缺陷), 把"无前视"变成可执行判据
- 修复 DEFECT-PL-03: 标准化 `method='auto'` 全样本前视 (实测 6.18e-01 → 0)
- 处置 ADR-030 记录的 Mixin 耦合风险 (发现并修掉一处**布局注释与实现相反**的陷阱)
- ADR 编号治理: 建立登记规则 + 勘误表 + 补记 ADR-030~036 (7 条)
- **版本号统一到 3.3.2**: 4 处声明 (pyproject / `__init__` / config_v2 / reporting) 收敛, 字段级测试改为比对本包 `__version__`
- 关联回归: 80 passed / 6 xfailed / 0 failed

**修正了两项此前的判断** (见下文各节):
1. 外部评审称"Mixed 管线输出不再是单位方差"——**不成立**, 实测为 1.0
2. 此前的分析认为"标准化逐日截面即因果"——**只对 `z_score` 成立**, `'auto'` 走的是 per-column 全样本分支

### 新增: 管线级截断不变式测试

**文件**: [tests/integration/test_pipeline_truncation_invariance.py](tests/integration/test_pipeline_truncation_invariance.py)

**不变式**: 对任意截断点 t, 用 `[0, t]` 数据跑出的 `[0, t]` 期输出, 必须等于全样本 `[0, T]` 跑后截取 `[0, t]` 期的输出。这是"无前视"的操作化定义, 不依赖实现者是否想到某个步骤有前视。

**结构** (三层 + 仪器):

| 层 | 内容 | 作用 |
|----|------|------|
| `TestIsolatedStepInvariance` | 每步单独喂**相同输入**独立测量 | 定位首个违反步骤, 避免上游前视污染下游判定 |
| `TestSubPipelineInvariance` | Static / Dynamic / Mixed 端到端 | 暴露步骤间传播效应 |
| `TestTopLevelInvariance` | `FactorProcessingPipelineV2` 全链路 | 含指纹路由决策的前视 |
| `test_diagnostic_report` | 恒通过的测量表 | 修复前后可对比, 逐行 `n_diff_cells` 应降为 0 |

**缺陷登记机制**: 预期违反的测试标 `xfail(strict=True, raises=AssertionError)`, reason 携带缺陷编号与实测数值。套件保持全绿的同时登记已知缺陷; 缺陷一旦修好, 该测试报 "unexpectedly passing" **强制摘标记**。`raises=AssertionError` 确保 ImportError/KeyError 等仍作为真错误暴露, 不被 xfail 吞掉。

**实测矩阵** (PL-03 修复后, `T=100, N=30, t=60, atol=1e-12`, Python 3.12):

| 层级 | 对象 | 状态 | 差异格 | 最大绝对差 |
|------|------|------|--------|-----------|
| step | imputer `ffill_ts` | PASS | 0 | 0 |
| step | outlier percentile | FAIL (PL-01) | 187 | 1.680e-01 |
| step | neutralize (逐日 OLS) | PASS | 0 | 0 |
| step | transform auto | FAIL (PL-02) | 1800 | 8.506e-04 |
| step | standardize `'auto'` | PASS (已修) | 0 | 0 |
| step | standardize `'z_score'` | PASS | 0 | 0 |
| pipeline | Static | FAIL | 1800 | 1.326e-02 |
| pipeline | Dynamic | FAIL (+8 NaN) | 1653 | 8.045e-01 |
| pipeline | Mixed | FAIL | 1800 | 2.906e-01 |

**结论**: 5 个处理步骤中, 插补 / 中性化 / 标准化(`z_score`)满足因果性; 去极值 / 变换不满足。解耦器 AR 另有结构性缺陷 (PL-05)。

### 修复 1: DEFECT-PL-03 标准化 `'auto'` 全样本前视

**位置**: [adapters.py](adapters.py) `ProcessingAdapter.__init__`

**根因 (两层)**:
1. **分支判定用 method 字面量**: `_cross_sectional_zscore` 仅在 `method == 'z_score'` 时为 True。`StaticFactorPipeline` 传 `'auto'`, 落入 per-column 分支 — `fit()` 在全样本上对每列拟合 `(mean, std)`, `transform()` 套用固定参数 → 前 t 期结果依赖 t 之后样本
2. **`'auto'` 的方法选择本身依赖全样本**: `AdaptiveStandardizer._vote_on_method` 依据 `outlier_ratio / is_heavy_tailed / is_skewed / cv` 投票选出方法 → 第二重前视源, 且同一输入在不同窗口可能选到不同方法

**修复**: `standardization + 'auto'` 于构造期解析为 `'z_score'`, 命中逐日横截面分支。该分支 `fit()` 为 no-op (不存参数), `transform()` 逐期独立计算 `(x - mean_t) / std_t` → **结构上无可泄漏参数**。

| 对象 | 修复前 | 修复后 |
|------|--------|--------|
| `standardize(method='auto')` 单步 | 1800/1800 格差异, 6.18e-01 | **0** |
| `StaticFactorPipeline` 端到端 | 4.03e-01 | **1.33e-02** (降 30 倍) |

**破坏性影响**: `StaticFactorPipeline` 输出数值变更, 此前用它产出的因子值 / IC / Sharpe 需重算。

**测试契约变更** (2 处, 已记入 ADR-029):
`tests/test_adapters/test_module_enabled.py` 与 `tests/test_pipelines_v2.py` 原断言 `result.mean(axis=0) ≈ 0` (列均值)。依据: **列均值 == 0 恰是全样本 per-column 标准化的定义特征**——任何因果变换在数学上都无法满足该等式, 故该断言成立本身就是前视的症状。已改为逐日横截面断言 (行均值 ≈ 0、行标准差 ≈ 1)。

**外部评审结论修正**: 评审称"混合因子偏度 > 2 触发变换时, 标准化参数来自未变换尺度, 输出不再是单位方差"——**不成立**。Mixed 传的是 `'z_score'`, 命中行内重算分支, 完全不读 fit 参数。新增 `test_mixed_pipeline_output_is_unit_variance` 实测逐日截面 std 中位数 ≈ 1.0 予以固定。

### 修复 2: ADR-030 Mixin 耦合风险处置

**位置**: [modules/factor_decoupler/diagnostics/hidden_effect.py](modules/factor_decoupler/diagnostics/hidden_effect.py) · [core/ar_model.py](modules/factor_decoupler/core/ar_model.py) · [core/dual_neutralizer.py](modules/factor_decoupler/core/dual_neutralizer.py)

补记 ADR-030 时核查代码, 发现耦合风险的实际形态**比原记录更严重**:

| # | 形态 | 性质 |
|---|------|------|
| 1 | 探测私有 `_results` → 结构变则返回 `None` → 报 `'AR model not fitted'` | 误报 (模型其实已 fit) |
| 2 | 该分支同时返回 `is_incremental_endogenous=False` | **假阴性: 谎报"无内生性"** |
| 3 | `ARModelResult.coefficients` 注释写 `[phi_1, ..., phi_p, intercept]`, 而 `_fit_ar` 把常数项插在**列首** | **布局陷阱**: 照注释改代码会静默取错 φ, 不报错 |

**处置**:

| 措施 | 实现 |
|------|------|
| φ 提取收拢为显式契约 | 宿主实现 `_get_ar_phi_for_diagnosis()`; Mixin 不再探测任何私有属性 |
| 布局假设单点化 | `AR_COEF_INTERCEPT_INDEX` / `AR_COEF_PHI1_INDEX` 具名常量, 仅在 `ARDecoupler` 钩子内使用 |
| 注释纠偏 | `ARModelResult.coefficients` 注释改为真实布局 `[intercept, phi_1, ..., phi_p]` |
| `CompositeDecoupler` 纯委托 | 钩子只转发内部 `ARDecoupler`, 本类不假设内层结构 |
| **破坏即报错** | 已 fit 却取不到 φ → 抛 `DiagnosticContractError`, 不再静默降级 |
| 语义钉子 | 新增 `TestDiagnosticContract` 8 项 |

**未 fit 仍走软提示** (两阶段分离语义不变, E1-T21 继续通过); 契约收紧只作用于「已 fit 但取不到 φ」这一原本会误报的情形。

### 治理: ADR 编号冲突与补记

**冲突规模** (排查后远大于单个编号): 3 份规划文档各自把 ADR-026 分配给不同决策, 且 v3.1.0 一次性预留 ADR-026~031 共 6 个编号, 与实际占用大面积冲突。

**处置** (详见 [DECISIONS.md](DECISIONS.md) 文首「ADR 编号登记规则与勘误」):
- 建立 3 条登记规则 (编号唯一集中分配 / 规划文档不得预留 / 引用须可检索)
- 勘误表 8 行, 逐条标注「作废 + 改记去向」
- 补记 7 条此前从未写入的 ADR: ADR-030 (E1 隐藏效应) / 031 (E2 P-hacking) / 032 (E3 内生性 S1-S4) / 033 (E4 格兰杰) / 034 (E5 三层正则化) / 035 (E6 估计层) / 036 (消融对照机制)
- 4 处冲突点置入 ⚠️ 勘误注 (EXECUTION_V3.1.0 / EXECUTION_ABLATION_V3.0.0 / audit 报告)

**勘误表自身的一次腐化与修正**: 首版用精确行号 (`:539, :3944`), 但在 DECISIONS.md 顶部插入内容后行号全部失效。已改为只标「文件名 + 出现次数」, 以「声明内容」列为检索键, 消除此类漂移。

**连带修正**:
- 代码注释编号错误: `pipelines_v2.py` 中 E1/E2 原标 `ADR-024` (实际是"指纹 21 维"), 改为 ADR-030 / ADR-031
- `ARCHITECTURE.md` 三处模块 ADR 归属: `endogeneity_check` 原归 ADR-026 (错误归属) → ADR-032; 并修正类名 `Ivx`→`IVXEstimator`、`Regularizer`→`EndogeneityRegularizer` 等
- `WORKFLOW_METHODOLOGY.md`: `ADR-001 至 ADR-025` → `至 ADR-036`

### 统一: 版本号 3.3.2

此前 `pyproject.toml` / `__init__.__version__` 停留在 `2.5.0`, 而本条目按 `3.3.x` 演进, 属上一轮显式记录的遗留缺口。本轮收敛:

| 位置 | 值 |
|------|-----|
| [pyproject.toml](pyproject.toml) | `3.3.2` |
| [__init__.py](__init__.py) | `__version__ = "3.3.2"` |
| [config_v2.py](config_v2.py) | `PipelineV2ConfigUnified.version = "3.3.2"` |
| [reporting.py](reporting.py) | `PipelineExecutionReport.pipeline_version = "3.3.2"` |

**消除重复锚点**: `tests/unit/test_config_v2.py` / `test_reporting.py` / `test_factor_orthogonalizer/test_adapter.py` 原各自持有字面量 (上一轮 `2.5.0` 的漂移正是这样发生的), 现改为比对本包 `factor_pipeline.__version__`; 唯一绝对锚点留在 `tests/test_fix3_version_unification.py` 的 `EXPECTED_VERSION`, 并新增 `test_06_pyproject_version_matches_package` 校验 `pyproject.toml` 与包版本一致。

**不参与统一**: `backtest/cache_manager.py` 的 `CODE_VERSION = "v2.2.0-cache"` 是缓存语义版本, 与项目版本解耦 (v3.3.3 因 PL-01 算法变更 bump 至 `v2.2.1-cache`, 见上); `modules/*` 子包各自维护独立版本 (decoupler 1.2.0 等)。

### 测试结果

| 范围 | 结果 |
|------|------|
| 新增 `test_pipeline_truncation_invariance.py` | 12 项 (6 通过 / 6 xfail 登记缺陷) |
| `test_hidden_effect.py` | 29 passed (原 21 + 契约测试 8) |
| `test_factor_decoupler/` + `test_pipelines_v2` + `test_pipelines_v2/` + `integration/` | **80 passed, 6 xfailed, 0 failed** |
| `unit/` + `demo_notebook` + `integration` (PL-03 阶段) | 262 passed, 2 skipped, 0 failed |
| 适配器 / 管线 / 多维度 / P1 (PL-03 阶段靶向) | 123 passed, 2 skipped, 6 xfailed, 0 failed |
| 版本统一靶向 (`test_fix3_version_unification` + `unit/test_config_v2` + `unit/test_reporting` + `orthogonalizer/test_adapter`) | **62 passed, 0 failed**; 手工校验脚本 5/5 (4 处声明 + pyproject, 缓存独立) |

### 已知遗留

**缺陷登记** (xfail 追踪, 按实测幅度排序):

| 编号 | 缺陷 | 实测 |
|------|------|------|
| DEFECT-PL-01 | `ProcessingAdapter` 去极值 `X.values.flatten()` 全 panel 拟合 → 全样本分位数 | 187 格 / 1.68e-01 |
| DEFECT-PL-05 | 解耦器 `ar_model.transform` 用样本内 `fitted_values` 充当 OOS 预测 | 8.05e-01 + 8 格 NaN 模式差 |
| DEFECT-PL-02 | 变换全 panel 拟合 λ; `'auto'` 选型亦依赖全样本 | 8.51e-04 (普遍但量级小) |

**其它**:
- 标准化 `'robust' / 'min_max' / 'quantile'` 仍走 per-column 全样本分支 (非因果), 三条生产管线均未使用, 已在测试文件登记为"已知未登记"
- ~~版本号漂移~~ **已在本轮消除**: 4 处声明统一为 `3.3.2`, 见上文「统一: 版本号 3.3.2」
- 全量 800+ 套件未完成长跑: `tests/test_backtest/test_p3_phase4_integration.py` 的 optimizer 模拟为主要耗时来源, 需单独安排

### 文档产出

- `DECISIONS.md`: ADR-029 (新增) + ADR 编号登记规则与勘误 + ADR-030~036 (补记) + ADR-030 耦合风险处置小节
- `docs/ARCHITECTURE.md`: ADR 索引与模块归属更新
- `docs/WORKFLOW_METHODOLOGY.md`: ADR 范围、模板占位符 (ADR-0XX) 修正
- `docs/EXECUTION_V3.1.0.md` / `docs/EXECUTION_ABLATION_V3.0.0.md` / `docs/audit/2026-07-08-ablation-code-quality-audit.md`: 勘误注

---

## v3.3.1 — 插补模块 P2 完成 + 学术引用修正 (已实施, 2026-07-27)

### 概览

v3.3.0 完成后, 对插补模块 (`factor_imputer`) 进行 P2 阶段收尾, 包含 3 项学术引用修正 + 3 项 P2 任务 (向量化 + e2e 测试 + 消融实验)。同时新增架构文档 / 进度矩阵 / 工作流方法论升级 (v1.3)。

**核心产出**:
- 3 项学术引用修正 (Little & Rubin 术语 / Breiman 2001 多输出 RF / Lopez de Prado 章号)
- P2-1: `_transform_rf_shared` 向量化 (1 次 predict 替代 N 次循环, 1e-12 精度等价)
- P2-3: 9 项端到端测试 (含静态扫描 + 严格因果性验证)
- P2-4: 10 项消融实验 (含 IC 范围 + 严格因果性消融)
- 全量回归: 803 passed / 10 skipped / 0 regressions

**文档产出**:
- `docs/ARCHITECTURE.md` v1.0 — 项目架构总览 (6 层分层 + 模块边界 + 数据流)
- `docs/DEV_PROGRESS.md` v1.0 — 版本 × 模块双维度进度矩阵
- `docs/EXECUTION_V3.3.1_IMPUTER_P2.md` — 本次会话详细实施记录
- `docs/WORKFLOW_METHODOLOGY.md` v1.3 — 整合 10 步 spec 规范 (调研→设计→实施→验收)

### 修正 1: Little & Rubin §4.3 术语

| 项 | 值 |
|----|-----|
| 问题 | 原引用 "因果填充原则" 非 Little & Rubin (2002) 标准术语 |
| 修正 | 改为 "fill within-unit first, then across-units" + 标注非标准术语 |
| 位置 | [tests/unit/test_imputer_lookahead_fix.py:11-13](tests/unit/test_imputer_lookahead_fix.py#L11-L13) |

### 修正 2: Breiman 2001 多输出 RF 补专门文献

| 项 | 值 |
|----|-----|
| 问题 | Breiman (2001) 未明确讨论 multi-output RF, 作为共享 RF 方案唯一引用不严谨 |
| 修正 | 新增 Segal & Xiao (2011) WIREs DMKD + van der Westhuizen et al. (2023) Geoderma |
| 位置 | [docs/analysis/IMPUTER_LOOKAHEAD_FIX_PLAN.md:520-521](docs/analysis/IMPUTER_LOOKAHEAD_FIX_PLAN.md#L520-L521) |

### 修正 3: Lopez de Prado §7 章号保守引用

| 项 | 值 |
|----|-----|
| 问题 | §7 章号未能从数据库逐章核验 |
| 修正 | 改为 "Chapter on Cross-Validation Methods in Finance" 保守引用 (附 ISBN 978-1-119-44811-0) |
| 位置 | [tests/unit/test_imputer_lookahead_fix.py:15-18](tests/unit/test_imputer_lookahead_fix.py#L15-L18) |

### P2-1: 向量化剩余 for 循环

| 项 | 值 |
|----|-----|
| 实现 | [modules/factor_imputer/core/imputers.py:587-645](modules/factor_imputer/core/imputers.py#L587-L645) |
| 改动 | N 次 predict → 1 次 predict + `missing_mask` 一次性填充 |
| 等价性 | `test_shared_model_batch_equivalent_to_per_row` (1e-12 精度) |
| 保留 for 循环 | KNN walk_forward (因果本质不能向量化) + FactorSpecificImputer missing indicator (单列赋值已 O(T)) |

### P2-3: 端到端测试 (9 项)

| 测试类 | 数量 | 验证内容 |
|--------|------|---------|
| `TestE2ECausalProperty` | 2 | ffill_ts 截断不变性 + 无未来异常值泄漏 |
| `TestE2ELookaheadSafeOnOff` | 2 | lookahead_safe=True/False 两条路径都跑通 |
| `TestE2EAllStrategiesCausal` | 1 | cross_sectional 因果性 (参数化) |
| `TestE2ESourceScan` (新增) | 2 | 静态扫描 adapters.py / imputers.py 无 .bfill() |
| `TestE2EStrictCausality` (新增) | 2 | 严格因果: 截断任意时间点历史不变 + 修改未来数据历史不变 |

### P2-4: 消融实验 (10 项)

| 测试类 | 数量 | 验证内容 |
|--------|------|---------|
| `TestAblationLookaheadSafe` | 3 | ON/OFF 跑通 + 前期填充值不同 + KNN walk_forward vs legacy 差异 |
| `TestAblationAdapterLevel` | 3 | lookahead_safe 透传 + ON/OFF 结果不同 |
| `TestAblationICRange` (新增) | 2 | IC ∈ [-1, 1] (cross_sectional + KNN walk_forward) |
| `TestAblationStrictCausality` (新增) | 2 | ON 满足截断不变性 + OFF 不满足 (验证切换确实改变语义) |

### 测试结果

```
插补相关测试: 52 passed in 5.21s
全量回归: 803 passed / 10 skipped / 0 regressions
```

| 测试文件 | 通过 / 总数 |
|---------|------------|
| `test_imputer_lookahead_fix.py` | 33 / 33 |
| `test_imputer_e2e_causal.py` | 9 / 9 |
| `test_imputer_ablation_lookahead.py` | 10 / 10 |

### 工作流方法论升级 (v1.3)

`docs/WORKFLOW_METHODOLOGY.md` 从 v1.2 升级至 v1.3, 新增 §13 整合 10 步 spec 规范:
- 10 步 ↔ 7 阶段映射表 (调研→设计→实施→验收显式化)
- 三类新工件定义: 调研文档 / 验收 checklist / 跨文档一致性 review
- 双幻觉消除 review (步骤 4 + 步骤 6)
- 工程细节显式检查 (版本 / 依赖 / 兼容 / 接口 / 签名 / 低效操作)
- 适用范围与裁剪规则 (大/中/小任务)
- v3.3.1 回溯适用性 (部分实例, 后续版本应补全步骤 7-8)

---

## v3.3.0 — Layer 3 溢价健康诊断双层体系 (已实施, 2026-07-15)

### 概览

在 v3.2.0 学术准则驱动管线重构基础上，完成 6 项改进任务 + 新增 Layer 3 FactorHealthDiagnoser 模块。实现从"因子分类"到"溢价健康诊断"的完整诊断链路：Layer 2 StatisticalClassifier 解决"因子是什么类型" → Layer 3 FactorHealthDiagnoser 解决"因子是否还在定价"。与 Layer 5 FactorHealthMonitor 互补不合并。

**核心产出**:
- 6 项任务全部完成: L2 Routing 消融修复 + 更多因子测试 + 跨市场验证 + 原则评分 92% + 真实数据全量消融 + Pipeline 日志
- 1 个新模块: `modules/factor_health/` (3 个核心类: PremiumEstimator + BreakpointDetector + FactorHealthDiagnoser)
- 1 项新 ADR: ADR-028 (Layer 3 溢价健康诊断)
- 兼容性分析: FactorHealthDiagnoser vs FactorHealthMonitor — 互补不合并
- 全量回归: 128/128 passed (v3.2.0 基线) + 9/9 Layer 3 TDD 测试
- 真实数据验证: A股 3 因子 (momentum=pricing, volatility=review, turnover=review)

### Task 1: L2 Routing 消融修复 (P0)

| 项 | 值 |
|----|-----|
| 问题 | 硬路由 (Hard routing) 使用 StatisticalClassifier 的 return_type 替代原 softmax 权重，消融实验配置需更新 |
| 修复 | 5 个消融配置全部适配新路由，`run_l2` 方法名修正 |
| 测试 | 5 tests — 5 配置消融全部通过 (B3 IC=-0.0003, Sharpe=0.111) |

### Task 2: 更多因子测试 (P1)

| 项 | 值 |
|----|-----|
| 目的 | 验证 StatisticalClassifier 在更多因子上的分类稳定性 |
| 结果 | 10 因子分类验证通过，分类结果与预期一致 |
| 脚本 | `scripts/test_more_factors.py` |

### Task 3: 跨市场验证 (P1)

| 项 | 值 |
|----|-----|
| 目的 | 验证 StatisticalClassifier 的跨市场迁移性 |
| 结果 | 4 市场 (A股/美股/港股/加密货币) 544 因子 100% 分类一致 |
| 脚本 | `scripts/test_cross_market.py` |

### Task 4: 原则评分 92% (P1)

| 项 | 值 |
|----|-----|
| 改动 | StatisticalClassifier: AR(1) 平稳性从硬编码 0.98 阈值 → Dickey-Fuller τ 检验 (Dickey & Fuller 1979) |
| 改动 | adapters.py: AR check 从硬编码 R²>0.01 → F-test + Bonferroni 校正 (Fisher 1924) |
| 改动 | dead code 清理: adapters.py 移除不可达 `return result` |
| 原则评分 | 68% → ~92% (+24% 原则比重) |
| 测试 | 4 tests — DF 检验正确性 + F-test 正确性 |

### Task 5: 真实数据全量消融 (P1)

| 指标 | 值 |
|------|-----|
| B3 IC_mean | -0.0003 |
| B3 Sharpe | 0.111 |
| winsorizer ΔIC | 显著 |
| scaler ΔIC | 显著 |
| 脚本 | `scripts/run_ablation_real.py` |

### Task 6: Pipeline 日志 (P2)

| 项 | 值 |
|----|-----|
| 新增字段 | `_intermediate_data: Dict[str, Dict[str, pd.DataFrame]]` |
| 新增方法 | `get_intermediate_data()` |
| 改动 | pipelines_v2.py transform 循环收集中间数据 |
| 测试 | 4 tests — 中间数据记录/可访问性/格式正确性 |

### Layer 3: FactorHealthDiagnoser (新模块)

**模块结构**:

| 类 | 职责 | 行数 | 学术依据 |
|----|------|------|---------|
| `PremiumEstimator` | Fama-MacBeth + Epanechnikov 核 → λ̂(t) | ~70 | Fama-MacBeth 1973 + Epanechnikov 1969 |
| `BreakpointDetector` | 网格搜索 Chow F-test 断点检测 | ~70 | Chow 1960 + Bai-Perron 1998 |
| `FactorHealthDiagnoser` | 多状态综合诊断 (pricing/recalibrate/monitor/review/suspect) | ~170 | 综合上述 |

**关键设计决策**:
1. 断点检测用 raw β_t 不用 kernel-smoothed λ̂_t (避免 F 统计量膨胀)
2. 无 Bonferroni 校正 (对 raw betas 过于保守)
3. bandwidth=24 (≈2年月度), half_life_threshold=60 (5年)

**与 FactorHealthMonitor 的兼容性**:

| 维度 | FactorHealthMonitor (已有) | FactorHealthDiagnoser (新增) |
|------|--------------------------|---------------------------|
| 分析视角 | 横截面快照 | 时间序列过程 |
| 核心问题 | "因子现在健康吗？" | "溢价什么时候断的？还在定价吗？" |
| 输入数据 | factor + returns + market_cap + volume | factor + forward_returns + return_type |
| 方法论 | IC/IR/HHI/换手率 启发式阈值 | Fama-MacBeth + Chow F-test + Epanechnikov 核 |
| 输出 | FactorHealthReport (0-100分) | dict (分类标签 + 溢价统计) |

**合并决策**: **不合并，保持独立互补**。两个模块正交 — HealthMonitor 在"因子使用"层面，HealthDiagnoser 在"因子定价"层面。建议顺序使用：HealthMonitor 快速筛选 → 对 flagged 因子用 HealthDiagnoser 深度诊断。

**A股 3 因子真实验证**:

| 因子 | premium_health | combined label | 断点位置 | pre_mean | post_mean |
|------|---------------|----------------|---------|----------|-----------|
| momentum_1m | stable | pricing | 无 | — | — |
| volatility_1m | ES | review | t=44 | -0.0038 | 0.0120 |
| turnover | ES | review | t=133 | -0.00002 | 0.00008 |

### 学术依据

- Fama, E. F., & MacBeth, J. D. (1973). Risk, return, and equilibrium: Empirical tests. *JPE*, 81(3), 607-636.
- Epanechnikov, V. A. (1969). Non-parametric estimation of a multivariate probability density. *Theory of Probability & Its Applications*, 14(1), 153-158.
- Chow, G. C. (1960). Tests of equality between sets of coefficients in two linear regressions. *Econometrica*, 28(3), 591-605.
- Bai, J., & Perron, P. (1998). Estimating and testing linear models with multiple structural changes. *Econometrica*, 66(1), 47-78.
- Dickey, D. A., & Fuller, W. A. (1979). Distribution of the estimators for autoregressive time series with a unit root. *JASA*, 74(366), 427-431.
- Fisher, R. A. (1924). On a distribution yielding the error functions of several well known statistics. *Proceedings of the International Congress of Mathematics*, 2, 805-813.

---

## v3.2.0 — 学术准则驱动管线重构 (已实施, 2026-07-10)

### 概览

系统审计 5 个核心处理模块的统计决策准则，发现 ~32% 依赖硬编码启发式阈值（数据迁就）。基于 15 篇学术文献（Box-Cox 1964 / Shapiro-Wilk 1965 / Bali-Engle-Murray 2016 / Lo-MacKinlay 1988 等）制定严格的统计决策准则，并逐步 TDD 实施。9 阶段执行计划中 P0 三步 + P1 Hard routing 已完成，全量回归 168/168 零回归。

**核心产出**:
- 3 篇分析文档: [academic_literature_decision_criteria.md](docs/analysis/academic_literature_decision_criteria.md) (含 §9 改进方案 + §10 执行顺序 + §11 验收标准) + [principle_vs_hacking_audit.md](docs/analysis/principle_vs_hacking_audit.md) + [ablation_post_fix_analysis.md](docs/analysis/ablation_post_fix_analysis.md) (含 P1 顺序 A/B 测试附录)
- 6 个 commits, 12 files changed, +1098/-185
- 消融实验: P0 三步后重跑，B3 IC=-0.0067, Sharpe=0.0028，winsorizer+scaler 显著 (p_bootstrap=0.016)
- 全量回归: 168/168 passed + 4 warnings (零回归)

### Step 1: Winsorizer `method='percentile'` (1%/99%) — Bali et al. 2016

| 项 | 值 |
|----|-----|
| 学术依据 | Bali, Engle & Murray (2016): "all variables are winsorized at the 1st and 99th percentiles" — JFE/JF/RFS 事实标准 |
| 改动 | `SmartOutlierDetector` 新增 `method='percentile'` → `np.percentile([1, 99])` + `np.clip` |
| 管线 | 三个管线 `method='auto'` → `method='percentile', percentile_lower=1.0, percentile_upper=99.0` |
| MixedPipeline | `_compute_winsorize_params` 从 3σ → `np.nanpercentile(arr, [1, 99], axis=0)` |
| 测试 | 4 tests — fit/clip/preservation/cross-sectional |
| commit | `38966db` |

### Step 2: Transformer Shapiro-Wilk 正态性检验 — Shapiro & Wilk 1965

| 项 | 值 |
|----|-----|
| 学术依据 | Shapiro & Wilk (1965): 形式正态性检验 H₀: normal, α=0.05 |
| 改动 | `_analyze_features`: 启发式 `abs(skew)<0.5 & abs(kurt)<1` → `shapiro(sample).pvalue ≥ 0.05` |
| fallback | Shapiro-Wilk 失败时 (degenerate data) → heuristic fallback |
| 新增字段 | `normality_p_value`, `normality_test` |
| 测试 | 2 新测试 (8 total) — N(0,1)→identity / skewed exp(2)→yeojohnson |
| commit | `480cb3d` |

### Step 3: Imputer `strategy='ffill_ts'` — Little & Rubin 2002

| 项 | 值 |
|----|-----|
| 学术依据 | Little & Rubin (2002) §4.3: "fill within-unit first, then across-units" |
| 改动 | `ImputerAdapter` 内置 `_transform_ffill_ts`: `X.ffill(axis=0)` → `row_median.fillna` → `fillna(0)` |
| 向量化 | O(T×N) pandas/numpy, 零 for 循环 |
| 管线 | 三个管线 `strategy='auto'` → `strategy='ffill_ts'` |
| 测试 | 4 tests — ffill/cross-median/no-nan-preserved |
| commit | `7e6bc08` |

### Step 4: 消融重跑

| 指标 | P0 前 (auto mode) | P0 后 (fixed methods) |
|------|------------------|----------------------|
| B3 IC_mean | -0.0074 | -0.0067 |
| B3 Sharpe | 0.0007 | 0.0028 |
| winsorizer ΔIC | -44.1% (**p=0.026**, 边界显著) | -51.7% (**p=0.016**, **显著**) |
| scaler ΔIC | +122.0% (**p=0.018**) | +128.0% (**p=0.016**, **显著**) |

关键发现: 固定方法后 winsorizer 的显著性从边界提升到正式显著 (p 从 0.026→0.016)，说明消除 auto 策略噪声后信号更干净。

### Step 7: Hard Routing + StatisticalClassifier — Lo & MacKinlay 1988

| 项 | 值 |
|----|-----|
| 学术依据 | Lo & MacKinlay (1988): Variance Ratio test + AR(1) stationarity |
| 新增模块 | `modules/statistical_classifier/` — 向量化面板分类 |
| 路由变更 | SOFT routing (加权混合) → **hard routing** (单管路线性变换) |
| 分类规则 | VR rejects random walk + stationary → static / VR OK + stationary → dynamic / else → mixed |
| 测试 | 4 tests — static→static / dynamic→dynamic / valid-type / speed<1s |
| commit | `add441b` |

### 决策历史

| 决策 | 结论 | 依据 |
|------|------|------|
| P1 StaticPipeline 顺序 | 保留新顺序 (no-revert) | A/B p=0.80 不显著，原则性更好，Spearman ρ=0.9958 近乎等价 |
| 市值中性化 | 集成到 B3 baseline | 市值是 momentum >70% alpha 来源，行业+市值 OLS 双重中性化 |
| SOFT → hard routing | 实施 | 无学术依据，破坏可审计性 |
| Auto → 固定方法 | 实施 | 消融可复现性 > IC 优化 |
| identity 回退 | 实施 | Box-Cox 不强制变换正态数据 |
| kurtosis 阈值 bug | 已修复 | scipy.stats.kurtosis 返回 excess kurtosis (~0 for N(0,1))，原代码错误假设 ~3 |

### Step 8: Anderson-Rubin 后验检验 (P2 监控) — Anderson & Rubin 1949

| 项 | 值 |
|----|-----|
| 学术依据 | Anderson & Rubin (1949), FWL 定理: 中性化后残差应正交于 dummies → R²≈0 |
| 改动 | `NeutralizerAdapter`: 新增 `enable_ar_check` + `_compute_ar_r2()` 静态方法 |
| 实现 | `_neutralize_with_cache` 循环内，OLS 拟合后 `np.linalg.lstsq(X, residuals)` → R² |
| 阈值 | mean R² > 0.01 → WARNING (中性化可能不完整); else → INFO |
| 性能 | O(k³) per period (k≤30 行业), 零额外循环 (复用 OLS residuals) |
| 默认 | `enable_ar_check=False` (向后兼容, 仅监控) |
| 测试 | 3 tests — disabled/enabled/near-zero R² |
| commit | `17447cf` |

### Step 9: 审计文档 v2.0 — 原则评分修正

| 项 | 值 |
|----|-----|
| 文档 | `docs/analysis/principle_vs_hacking_audit_v2.md` |
| 核心 | v1.0 评分 68%→88% (+20% 原则比重) |
| 逐模块 | Imputer 50%→85% / Winsorizer 50%→90% / Transformer 60%→85% / Routing 30%→80% |
| 剩余迁就 | 12%: Transformer 非正态分支 + Routing 0.98 阈值 + AR R² 0.01 阈值 (三者均可消除但 trade-off 合理) |
| 结论 | v3.2.0 为可迁移的学术级管线，每一步有 15 篇核心文献 (1964-2016) 支撑 |

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

---

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