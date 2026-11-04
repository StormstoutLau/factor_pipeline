# PL-06 Mixed 缩尾前视缺陷 — 设计文档

**版本**: v1.1 (A 选定; B 保留为备选记录, 本次不实施)
**日期**: 2026-10-22
**缺陷编号**: DEFECT-PL-06
**上游调研**: [PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md](PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md) v1.0
**关联决策**: ADR-027 (固定方法) / ADR-037 (逐日截面去极值) / ADR-038 (逐日截面 rank) / 新增 ADR-039
**目标版本**: v3.3.5
**方案状态**: **A (逐日截面 3σ) 已选定**; B (percentile) 与"方法选择器"记录为备选, 不在本次实施
**实施状态**: **已实施 (v3.3.5, 2026-11-04)**; 验收记录见 [EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md](../EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md) §7
**行号说明**: 行号仅作导航, 以类名/函数名/测试名为准

---

## §0 设计摘要

| # | 决策 | 状态 |
|---|------|------|
| D1 | 缩尾边界改为**逐日截面**估计 (`axis=1`), 只使用当日行 | **锁定** |
| D2 | `fit()` 不再保存跨期缩尾参数; 边界在 `transform()` 内按行现算 | **锁定** |
| D3 | 方法选择: **A = 逐日截面 3σ** (保留 `mixed_winsor_sigma`); B = 逐日截面 percentile(1,99) 仅作为备选记录 | **A 已选定; B 不实施** |
| D4 | 小截面语义由方法数学性质决定, 不引入数据触发的 pre-test 切换 | **锁定** |
| D5 | 不改变 Mixed 步骤顺序 (I-INT: winsorize → neutralize → rank) | **锁定** |
| D6 | 输出数值变更 → 版本 v3.3.5、缓存 `v2.2.3-cache`、ADR-039 | **锁定** |
| D7 | 新增单元测试; 摘除 PL-06 的 `xfail`; 更新诊断登记表 | **锁定** |
| D8 | 不新增"方法选择器"; 不删除 `mixed_winsor_sigma` / `transform_aggressiveness` | **锁定** |

**验收目标 (方案 A)**: `test_mixed_pipeline_is_truncation_invariant` 由 257/1800 格差异、`max_abs=6.98e-01` 降为 **0 格 / 0**。

**A 选定的理由**:

1. **最小语义变更**: 保留现有 3σ 方法, 只修估计轴与 fit 状态; 不在缺陷修复中改变缩尾方法。
2. **配置/optimizer 契约不变**: `mixed_winsor_sigma` 与 `transform_aggressiveness` 继续有效, 避免 B 的配置迁移与约 10 个测试/脚本改动。
3. **风险可控**: 只改 `pipelines_v2.py` + 新增单测; 输出变更 561 格 (B 为 612 格), 性能 0.268s (当前 0.512s, 调研探针口径; 真实方法口径见执行文档)。
4. **已知遗留**: Mixed 使用 3σ、Static 使用 percentile(1,99); 方法差异在 ADR-039 中登记, 后续如需统一另开任务。A 不试图在本次修复中解决该差异。

---

## §1 目标与非目标

### 1.1 目标

1. **因果性**: Mixed 缩尾边界只依赖当日截面, 满足截断不变式。
2. **fit no-op**: `fit()` 不产生任何可泄漏的跨期参数。
3. **契约保持**: index / columns / NaN 模式不变; 不新增 NaN; 不改变步骤顺序。
4. **可测试**: 新增直接锁定缩尾数值与小截面行为的单元测试。
5. **可回滚**: 版本与缓存代际明确, 回滚路径清晰。

### 1.2 非目标

| 项 | 归属/说明 |
|----|-----------|
| PL-05 (Dynamic AR 系数/fitted_values) | 独立缺陷 |
| PL-07 (顶层指纹路由) | 独立缺陷 |
| 删除 Mixed 缩尾步骤 | 不做; 调研 §3.4 已论证其非冗余 |
| 重新调参/重新搜索 optimizer | 不做; 输出变更后另行评估 |
| 非 Mixed 管线的缩尾 | 不做 |
| `ProcessingAdapter(outlier)` 的任何改动 | 不做 (PL-01 已修复) |
| 方法选择器 (`mixed_winsor_method`) / A+B 并存 | 不做; 独立能力任务 |
| B 的配置迁移 (`mixed_winsor_sigma` / `transform_aggressiveness` 删除) | 不做; 若未来统一方法, 另开任务 |
| Mixed 缩尾统一走 `ProcessingAdapter(outlier)` | 不做; 架构重构任务 |
| 统一 Mixed 3σ 与 Static percentile 的口径 | 不做; ADR-039 登记为已知差异 |

---

## §2 现状与约束

### 2.1 当前代码路径

| 位置 | 现状 |
|------|------|
| `MixedFactorPipeline.fit` ([pipelines_v2.py L1088-L1140](../../pipelines_v2.py#L1088-L1140)) | 插补 → `_compute_winsorize_params(X)` → `_apply_winsorize(X)` → 中性化 → rank → z-score |
| `MixedFactorPipeline.transform` ([L1142-L1162](../../pipelines_v2.py#L1142-L1162)) | 插补 → `_apply_winsorize(X)` (复用 fit 参数) → 中性化 → rank → z-score |
| `_compute_winsorize_params` ([L1164-L1178](../../pipelines_v2.py#L1164-L1178)) | `X.mean(axis=0)` / `X.std(axis=0)` (ddof=1) → 每只股票全历史的 3σ 边界 |
| `_apply_winsorize` ([L1180-L1184](../../pipelines_v2.py#L1180-L1184)) | `X.clip(lower=lo, upper=hi, axis=1)` |
| `PipelineV2Config.mixed_winsor_sigma` ([L709](../../pipelines_v2.py#L709)) | dataclass 字段, 默认 3.0 |
| `PipelineV2ConfigUnified.mixed_winsor_sigma` / `.transform_aggressiveness` ([config_v2.py L417-L424](../../config_v2.py#L417-L424)) | Pydantic 字段; `to_pipeline_v2_config()` 映射前者 |
| `optimizer.DEFAULT_SEARCH_SPACE` ([optimizer.py L47-L56](../../optimizer.py#L47-L56)) | 搜索 `mixed_winsor_sigma`; `transform_aggressiveness` 仅用于调整它 |

### 2.2 数据契约

- `X: pd.DataFrame`, index = 日期, columns = 股票。
- 截面操作 = `axis=1`; 因此逐日统计量为 `X.mean(axis=1)` / `X.std(axis=1, ddof=1)` / `X.quantile(q, axis=1)`。
- 输出保留 index / columns; NaN 不参与统计, 输出仍为 NaN; 不新增 NaN。
- 单行有效观测 `< 2`、零离散度、全 NaN 行原样返回。
- 小截面行为由方法数学性质决定; 不得引入"先检验再切换"的 pre-test。

### 2.3 既有测试

| 测试 | 当前状态 |
|------|---------|
| `tests/integration/test_pipeline_truncation_invariance.py::test_mixed_pipeline_is_truncation_invariant` | `xfail(strict=True, raises=AssertionError)`, reason 记录 PL-06 / 6.98e-01 |
| `tests/integration/...::test_mixed_pipeline_output_is_unit_variance` | 通过; **测试通过性不变** (断言是逐日 std≈1, 由 z-score 逐行重算保证), 但输出数值本身会因缩尾修复而改变 |
| `tests/test_pipelines_v2.py::test_mixed_pipeline_processing` | 通过; 只检查形状/缺失率 |
| `tests/test_adapters/test_module_enabled.py` | 通过; 对 mixed 管道只断言 `_imputer_enabled` / `_scaler_enabled` (L248-251), **无** `_winsorizer_enabled` 透传断言; 全 identity 测试是全模块关闭场景 |
| 直接锁定 Mixed 缩尾数值的测试 | **存在** `tests/test_p3_phase2_config_migration.py::TestMixedWinsorSigma` (`test_07/08/09`), 但它们锁定的是**旧 per-column 语义** (直接调用 `_compute_winsorize_params`); 实施时需重写为逐日截面语义 |

---

## §3 方案设计

### 3.1 公共设计 (A/B 共用, 锁定)

#### 3.1.1 `fit()` 改为 no-op

```python
# MixedFactorPipeline.fit
if self._winsorizer_enabled:
    logger.info("[MixedPipeline] Applying gentle cross-sectional winsorization...")
    self._winsorize_params = None   # 显式标记: 无跨期参数
    X = self._apply_winsorize(X)
else:
    logger.info("[MixedPipeline] winsorizer disabled, 跳过去极值 (identity)")
    self._winsorize_params = None
```

- 删除 `_compute_winsorize_params` 方法。
- `_winsorize_params` 保留为 `None` 状态标记; 不保留任何 Series/dict 参数。
- `_intermediate_data['outlier']` 仍记录缩尾后的 DataFrame, 行为不变。

#### 3.1.2 `_apply_winsorize` 按行现算

```python
def _apply_winsorize(self, X: pd.DataFrame) -> pd.DataFrame:
    """逐日截面缩尾: 边界只由当日行计算, 无跨期参数."""
    ...  # 方法实现见 §3.2 (方案 A, 已选定)
    return X.clip(lower=lo, upper=hi, axis=0)
```

- `axis=0` 表示 lower/upper 是 index (日期) 对齐的 Series。
- 向量化实现已与逐行循环对拍 (`allclose=True`, 见调研附录 A.2 4e)。

#### 3.1.3 边界语义 (锁定)

| 行状态 | 行为 | 依据 |
|--------|------|------|
| 全 NaN | 原样返回 | `mean/std/quantile` 为 NaN, `clip` 忽略 NaN 边界 |
| 单有效观测 (`N=1`) | 原样返回 | 同上 |
| 零离散度 | 原样返回 | 边界 = 均值, 所有值相等 |
| `N=2` | **取决于方法**: A no-op (`max|z|=0.707<3`); B 两值向中间压缩 | 调研 §3.6 实测 |
| `N≤10` | A: 3σ 永不触发; B: 每行截 min/max | 调研 §3.6 数学推导 |

#### 3.1.4 文档与注释

- `MixedFactorPipeline` 类 docstring 的 "温和去极值(3σ缩尾)" 改为: "逐日截面 3σ 缩尾 (fit 无状态)"。
- `mixed_winsor_sigma` 的 config description 保持 "混合管道缩尾阈值（sigma 倍数）" 不变。
- B 对应的文档变更见 §3.3 (备选记录, 不执行)。

### 3.2 方案 A: 逐日截面 3σ (保留 `mixed_winsor_sigma`)

#### 3.2.1 实现

```python
def _apply_winsorize(self, X: pd.DataFrame) -> pd.DataFrame:
    sigma = self.mixed_winsor_sigma
    mu = X.mean(axis=1)
    sd = X.std(axis=1, ddof=1)
    return X.clip(lower=mu - sigma * sd, upper=mu + sigma * sd, axis=0)
```

- `self.mixed_winsor_sigma` 继续由构造函数/配置传入, 语义不变。
- 不新增常量; `ddof=1` 与 pandas 默认一致, 也与当前 per-column 实现的样本标准差口径一致。

#### 3.2.2 行为与影响

| 项 | 实测值 (T=100, N=30, skewed) |
|----|------------------------------|
| 截断不变式 | 0 / 1800 |
| 缩尾触发率 | 77 / 3000 (2.57%) |
| 相对当前全样本输出差异 | 561 / 3000 格, 63/100 行, `max_abs=1.0446` |
| 逐日 Spearman (vs 当前) | 中位 0.999110, 最小 0.942603 |
| ties | 4 个值 (当前 0) |
| 性能 (2500×3000) | 0.268s (当前 0.512s; 调研探针口径) |
| 小截面 | `N≤10` no-op; `N=2` no-op |

> 性能口径说明: 上表为调研探针的内联计算口径. 实施前对**真实方法**实测为当前 `_compute_winsorize_params` + `_apply_winsorize` = 0.281s、提案等价计算 = 0.200s (见 [EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md](../EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md) §1.2). 两个口径均表明新实现更快, 验收以执行文档为准.

#### 3.2.3 配置面

- `PipelineV2Config.mixed_winsor_sigma` 保留。
- `PipelineV2ConfigUnified.mixed_winsor_sigma` / `transform_aggressiveness` 保留。
- `optimizer.DEFAULT_SEARCH_SPACE` 保留 `mixed_winsor_sigma`。
- **无配置迁移**。

#### 3.2.4 测试要点 (A 专属)

- `sigma` 单调性: `sigma` 越大, 截断格数不增。
- `N=2` no-op; `N=5/10` no-op; `N=11` 起可能触发。
- 零离散度行不变; 单有效观测行不变。
- 缩尾后的值不超过 `mu ± sigma*sd`; 边界仅由当日行决定。

### 3.3 方案 B: 逐日截面 percentile(1,99) (备选记录, 本次不实施)

> **状态**: 仅作为备选方案与迁移清单保留, 供未来"方法统一/方法选择器"任务参考。本文后续的实施步骤、测试与验收**不包含 B**。

#### 3.3.1 实现

```python
def _apply_winsorize(self, X: pd.DataFrame) -> pd.DataFrame:
    lo = X.quantile(0.01, axis=1)
    hi = X.quantile(0.99, axis=1)
    return X.clip(lower=lo, upper=hi, axis=0)
```

#### 3.3.2 配置迁移 (B 的必要工作, 范围较大)

B 与 `mixed_winsor_sigma` 语义不兼容 (percentile 没有 sigma 参数)。若未来选 B, 必须二选一:

| 子方案 | 内容 | 评价 |
|--------|------|------|
| B-1 删除 | 从 `PipelineV2Config` / `PipelineV2ConfigUnified` 删除 `mixed_winsor_sigma`; 从 optimizer 搜索空间与映射中删除; 同步 `transform_aggressiveness` (其唯一作用点是调整 sigma) | **推荐**; 与 PL-02 删除死配置的先例一致 |
| B-2 保留但废弃 | 字段保留、不再消费 | 不推荐; 形成死配置, 与 ADR-027/038 的配置收敛方向冲突 |

**B-1 影响面 (初始核对)**:

| 文件 | 变更 |
|------|------|
| `pipelines_v2.py` | 删除 `PipelineV2Config.mixed_winsor_sigma`; 删除 `MixedFactorPipeline.__init__` 参数/属性; 删除 `_create_pipeline` 传参 |
| `config_v2.py` | 删除 `PipelineV2ConfigUnified.mixed_winsor_sigma` / `transform_aggressiveness`; 删除 `to_pipeline_v2_config()` 映射 |
| `optimizer.py` | 删除搜索空间两项; 删除 `_params_to_config` / `_config_to_params` 中的映射与 aggressiveness 调整逻辑 |
| `tests/test_p3_phase3_optimizer.py` | 搜索空间/映射断言更新 |
| `tests/test_p3_phase2_config_migration.py` | 字段迁移断言更新 |
| `tests/test_p3_config_extension.py` | 字段存在性/默认值断言更新 |
| `tests/test_fix2_config_unification.py` | 映射断言更新 |
| `tests/verify_objective_function.py` / `tests/test_backtest/verify_p0_2_manual.py` / `verify_p2_2_manual.py` / `verify_fix2_manual.py` / `tests/manual/verify_v2_6_0_*` | 手工验证脚本更新 |
| `CODE_WIKI.md` / `CHANGELOG.md` / `DECISIONS.md` | 文档同步 |

> 以上为静态 grep 的初步清单; 实施前需再次全仓 grep `mixed_winsor_sigma|transform_aggressiveness` 复核。

**旧配置兼容**: Pydantic 默认 `extra='ignore'`, 旧 JSON/YAML 中的 `mixed_winsor_sigma` / `transform_aggressiveness` 会被**静默忽略**, 不报错。必须在 CHANGELOG 中写明该行为 (与 PL-02 的配置删除说明同口径)。

#### 3.3.3 行为与影响

| 项 | 实测值 (T=100, N=30, skewed) |
|----|------------------------------|
| 截断不变式 | 0 / 1800 |
| 缩尾触发率 | 200 / 3000 (6.67%) |
| 相对当前全样本输出差异 | 612 / 3000 格, 83/100 行, `max_abs=1.2203` |
| 逐日 Spearman (vs 当前) | 中位 0.998665, 最小 0.918131 |
| ties | 0 (本面板) |
| 性能 (2500×3000) | 0.308s |
| 小截面 | `N≤200` 每行截 min/max; `N=2` 两值向中间压缩; `N=1` no-op |

#### 3.3.4 测试要点 (B 专属)

- `N=30` 行: 最小值/最大值被截到 1%/99% 分位点; 中间值不变。
- `N=2` 行: `[1.0, 2.0]` → `[1.01, 1.99]` (锁定该语义)。
- `N=1` / 全 NaN / 零离散度: 原样返回。
- 分位边界仅由当日行决定; 修改未来行不影响过去行。
- 若执行 B-1: 配置字段删除后, 旧 JSON 静默忽略的迁移行为需单独测试。

### 3.4 A/B 决策记录 (A 已选定)

| 维度 | A: 截面 3σ (选定) | B: 截面 pct(1,99) (备选, 不实施) |
|------|-------------------|-----------------------------------|
| 因果性 | 满足 | 满足 |
| 改动文件 | `pipelines_v2.py` + 测试 | `pipelines_v2.py` + `config_v2.py` + `optimizer.py` + 约 10 个测试/脚本 + 文档 |
| 配置迁移 | 无 | 删除 `mixed_winsor_sigma` / `transform_aggressiveness` (B-1) |
| 与 PL-01/ADR-037 口径 | 部分 (同轴, 不同方法) | 完全一致 |
| 与项目内原始计划 | 不一致 | 一致 (`_compute_winsorize_params` → percentile 1/99) |
| 学术/工业证据 | MSCI FaCS 3 稳健σ (A) | 项目口径 + 学术常见 1%/99% (B, 原文未逐字核验) |
| 小截面 | `N≤10` no-op; `N=2` no-op | `N≤200` 每行截两端; `N=2` 向内压缩 |
| 输出变更 (本面板) | 561 格 | 612 格 |
| 性能 | 0.268s | 0.308s |
| 实施风险 | 低 (单文件) | 中 (配置/optimizer/测试面广) |

**决定**: 本次选 **A**。理由见 §0; B 的迁移清单保留在 §3.3.2, 但不在本任务执行。Mixed 3σ 与 Static percentile 的方法差异登记为已知遗留 (ADR-039), 后续统一另开任务。

---

## §4 测试设计 (TDD)

### 4.1 新增单元测试

建议文件: `tests/unit/test_mixed_winsorize_cross_sectional.py`。

**公共用例 (A 必须通过)**:

| 测试名 | 断言 |
|--------|------|
| `test_fit_does_not_store_cross_period_params` | `fit` 后 `_winsorize_params is None`; 不存在跨期 Series/dict |
| `test_truncation_invariant_on_synthetic_panel` | 全样本 vs 截断的前 t 期输出逐元素相等 (atol=1e-12) |
| `test_future_value_does_not_change_past_rows` | 只修改最后一行, 前面所有行输出不变 |
| `test_nan_rows_unchanged` | 全 NaN / 单有效观测 / 零离散度行原样返回 |
| `test_no_new_nan` | 输出 NaN 模式 == 输入 NaN 模式 |
| `test_winsorizer_disabled_skips_clip` | `module_enabled={'winsorizer': False}` → fit/transform 不做缩尾: `_intermediate_data['outlier'] == _intermediate_data['imputation']` (后续 neutralize/rank/z-score 仍执行, 端到端输出 ≠ 输入, 不可断言全等) |
| `test_metadata_preserved` | index / columns 完全一致 |

**A 专属**:

| 测试名 | 断言 |
|--------|------|
| `test_sigma_monotonicity` | `sigma=2` 的截断格数 ≥ `sigma=3` ≥ `sigma=4` |
| `test_n_le_10_is_noop` | `N=2/5/10` 的行输出 == 输入 |
| `test_bounds_are_row_mean_plus_minus_sigma_std` | 逐行 `mu ± sigma*sd(ddof=1)` 对拍 |
| `test_n11_can_clip` | 构造 `N=11` 的极端行, 至少 1 个值被截断 |

**B 专属 (备选记录, 本次不实施)**:

| 测试名 | 断言 |
|--------|------|
| `test_percentile_clips_min_and_max` | N=30 行: min/max 被截到 1%/99%; 中间值不变 |
| `test_n2_compresses_both_values` | `[1.0, 2.0]` → `[1.01, 1.99]` |
| `test_n1_and_all_nan_unchanged` | `N=1` / 全 NaN 行原样返回 |
| `test_quantile_bounds_are_row_local` | 修改未来行不改变过去行的分位边界 |

> 测试数据策略 (步骤 8 一致性 review 修订): 边界语义 (全 NaN / N=1 / 零离散度 / N≤10 / N=11) 必须用可手算的小面板; 性质类断言 (截断不变式、未来值不影响过去行、NaN 模式、sigma 单调性) 允许使用合成随机面板, 但必须有独立路径或独立不变量断言, 不得用实现同表达式自证。

### 4.2 集成测试变更

1. `tests/integration/test_pipeline_truncation_invariance.py`:
   - 删除 `test_mixed_pipeline_is_truncation_invariant` 的 `xfail`;
   - 缺陷登记表移除 PL-06, 在"已修复"条目追加 PL-06;
   - `test_diagnostic_report` 中 Mixed 行由 FAIL 转为 PASS;
   - 更新 PL-07 的 reason (顶层仍受 PL-05/路由影响; Mixed 不再贡献); PL-05 的 reason 不涉及 PL-06, 不改。
2. 既有靶向套件:
   - `tests/test_pipelines_v2.py`
   - `tests/test_adapters/test_module_enabled.py`
   - `tests/test_p3_phase2_config_migration.py` (**重写** `TestMixedWinsorSigma` 的 test_07/08/09: 删除对 `_compute_winsorize_params` 的调用, 改为锁定逐日截面边界)
   - `tests/integration/test_pipeline_truncation_invariance.py`
   - B 的配置/optimizer 套件不在本次执行 (见 §3.3.2 备选记录)。

### 4.3 回归基线

实施前记录:

```powershell
cd F:\Coding
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/integration/test_pipeline_truncation_invariance.py -q
```

预期: **9 passed / 3 xfailed** (PL-05/06/07 登记)。实施后预期: **10 passed / 2 xfailed** (PL-05/07)。

```powershell
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/test_pipelines_v2.py `
  factor_pipeline/tests/test_adapters/test_module_enabled.py -q
```

预期: 全绿; 记录实际数量。

---

## §5 验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| V1 | Mixed 截断不变式 **0 格 / 0** | 集成测试通过 |
| V2 | 摘除 `xfail` 标记后该测试直接通过 (strict xfail 若未摘除会因转绿而报错, 强制同步) | 集成套件 10 passed / 2 xfailed |
| V3 | 新单测全部通过 (公共 + A 专属) | pytest |
| V4 | NaN 模式与 index/columns 不变 | 单测 |
| V5 | `fit` 后无跨期参数 | 单测 |
| V6 | `winsorizer` 关闭时跳过缩尾 (outlier 中间数据 == imputation 中间数据; 端到端输出不等价于输入) | 单测 |
| V7 | 既有靶向套件全绿 | pytest |
| V8 | 性能不慢于当前实现 (本机基准) | 记录 2500×3000 耗时 |
| V9 | 输出变更幅度与调研一致 (A 561 格; B 612 格仅作备选参考) | 探针复测 |
| V10 | 版本/缓存/ADR/CHANGELOG 同步 | 文档核对 |

---

## §6 兼容性、版本与回滚

### 6.1 版本与缓存

| 项 | 值 |
|----|-----|
| 项目版本 | **v3.3.5** |
| 缓存 `CODE_VERSION` | **`v2.2.3-cache`** |
| ADR | **ADR-039** (占用登记表更新为 "ADR-040 起 未占用") |
| CHANGELOG | v3.3.5 条目: 根因/方案/实测/影响面/迁移说明 |
| 架构文档 | `ARCHITECTURE.md` / `DEV_PROGRESS.md` 版本基线追加 v3.3.5 |

### 6.2 输出与配置兼容性

- **输出数值变更**: 所有 Mixed 结果需重算; 价格/收益缓存也会因 `CODE_VERSION` 粗粒度 bump 而一次性失效 (与 PL-01/PL-02 同口径)。
- **配置 (A)**: 无迁移; `mixed_winsor_sigma` / `transform_aggressiveness` 语义不变。
- **配置 (B, 未实施)**: 若未来选 B, 需删除 `mixed_winsor_sigma` 与 `transform_aggressiveness`; 旧 JSON/YAML 字段会被 Pydantic `extra='ignore'` 静默忽略, CHANGELOG 必须写明迁移说明。本任务不执行该项。

### 6.3 回滚

1. 恢复 `pipelines_v2.py` 的 `_compute_winsorize_params` / per-column `_apply_winsorize`;
2. 恢复 `CODE_VERSION = "v2.2.2-cache"` 与版本 v3.3.4;
3. 恢复 PL-06 的 `xfail` 登记;
4. 删除/重建缓存。

---

## §7 实施步骤 (TDD 顺序)

| 步 | 动作 | 产出 |
|----|------|------|
| 1 | Red: 新增 `tests/unit/test_mixed_winsorize_cross_sectional.py` (公共 + A 专属), 确认失败 | 失败测试 |
| 2 | Green: 修改 `MixedFactorPipeline.fit` / `_apply_winsorize`, 删除 `_compute_winsorize_params` | 单测通过 |
| 3 | 摘除 PL-06 `xfail`, 更新登记表与诊断 reason | 集成 10 passed / 2 xfailed |
| 4 | 回归靶向套件 + 性能复测 + 输出差异复测 | 验收记录 |
| 5 | 版本/缓存/ADR-039/CHANGELOG/架构文档 | 文档同步 |
| 6 | 全仓 grep 复核 `mixed_winsor_sigma|transform_aggressiveness|_winsorize_params`; 最终 review | 无遗漏 |

---

## §8 风险与未决问题

| # | 风险/问题 | 处置 |
|---|----------|------|
| R1 | A 在 `N≤10` 时缩尾 no-op, 小股票池可能"看起来没生效" | 文档化; 单测锁定; 不引入条件切换 |
| R2 | Mixed 3σ 与 Static percentile(1,99) 方法不一致 | ADR-039 登记为已知遗留; 统一另开任务 |
| R3 | 输出变更导致历史 IC/Sharpe 不可比 | CHANGELOG 明示; 缓存 bump; 另行重算 |
| R4 | `_winsorize_params` 是否有仓库外读取 | 仓库内 grep 仅命中 `pipelines_v2.py`; 实施前再复核 |
| R5 | 旧测试 `TestMixedWinsorSigma` 直接调用 `_compute_winsorize_params` | 删除方法会导致 `AttributeError`; 实施时同步重写 test_07/08/09 |
| R6 | optimizer 在输出变更后未重新调参 | 明确不在本任务; 后续单独评估 |
| R7 | 若未来加方法选择器, 需避免数据驱动 auto 选型 | 独立任务; 方法必须是构造期 `Literal`, 不进入 optimizer 搜索 |

---

## §9 代码证据与影响面

### 9.1 必改

| 文件 | 本次变更 (A) |
|------|--------------|
| `pipelines_v2.py` | `fit` / `_apply_winsorize` / 删除 `_compute_winsorize_params` |
| `tests/unit/test_mixed_winsorize_cross_sectional.py` | 新增 (公共 + A 专属) |
| `tests/test_p3_phase2_config_migration.py` | 重写 `TestMixedWinsorSigma` 的 test_07/08/09 (旧 per-column 语义 → 逐日截面语义) |
| `tests/integration/test_pipeline_truncation_invariance.py` | 摘 xfail / 更新登记表 / 更新诊断 reason |
| `CHANGELOG.md` / `DECISIONS.md` / `ARCHITECTURE.md` / `DEV_PROGRESS.md` / `backtest/cache_manager.py` / `pyproject.toml` / `__init__.py` / `reporting.py` | v3.3.5 / `v2.2.3-cache` / ADR-039 |

> B 的配置/optimizer 影响面见 §3.3.2, 本次不执行; 若未来选 B, 需另开任务并重新核对清单。

### 9.2 不改

- `modules/factor_adaptive_winsor/core/transformers.py` (PL-02 已完成, 本缺陷不触碰)
- `adapters.py` (PL-01/PL-02 已完成)
- `modules/factor_decoupler/**` (PL-05)
- `FactorProcessingPipelineV2.fit/transform` 路由 (PL-07)
- Mixed 的步骤顺序与 `module_enabled` 语义

---

## 附录 A: 调研数据引用

所有实测数据、探针脚本、原始输出、文献证据等级与未验证项见
[PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md](PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md) §3 / 附录 A-C。
本文不重复粘贴, 避免两处数值漂移。
