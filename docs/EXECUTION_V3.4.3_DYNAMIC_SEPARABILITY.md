# EXECUTION V3.4.3 — DYNAMIC COMPONENT SEPARABILITY (O2)

> **版本**: v1.1 (2026-11-12)
> **设计**: [DESIGN_DYNAMIC_COMPONENT_SEPARABILITY.md](private/DESIGN_DYNAMIC_COMPONENT_SEPARABILITY.md) v1.1
> **调研**: [RESEARCH_DYNAMIC_COMPONENT_SEPARABILITY.md](research/RESEARCH_DYNAMIC_COMPONENT_SEPARABILITY.md) v1.1
> **ADR**: ADR-045
> **裁剪**: 中任务 → 步骤 1-2-3-4-5-6-9-10 (省略 checklist 与一致性 review, 依据 WORKFLOW_METHODOLOGY §13.8)

---

## §0 摘要

修复 O2: `DynamicFactorPipeline` 的 `neutralizer` 开关同时关闭 AR 解耦。
新增独立 `decoupler` 开关, `CompositeDecoupler` 增加 `enable_neutralization` /
`enable_ar` 两个默认 `True` 的构造参数; 默认路径逐位不变。

| 项 | 预期 |
|----|------|
| 生产代码 | `dual_neutralizer.py` +51/−26 (含 docstring); `pipelines_v2.py` +16/−7 |
| 测试 | 新增 2 文件 15 例 + 更新 1 例 |
| 版本 | 3.4.2 → **3.4.3** (6 处锚点) |
| 缓存 | 不变 `v2.3.0-cache` |

---

## §1 任务清单

### E1: CompositeDecoupler 子组件开关

**文件**: `modules/factor_decoupler/core/dual_neutralizer.py`

**E1.1** `__init__` (L354-382) 追加参数并保存:

```python
def __init__(self,
             industry_data: Optional[pd.Series] = None,
             market_cap_data: Optional[pd.DataFrame] = None,
             max_ar_order: int = 5,
             ar_criterion: str = 'aic',
             decorrelation_strength: float = 1.0,
             enable_neutralization: bool = True,
             enable_ar: bool = True):
    ...
    self._enable_neutralization = enable_neutralization
    self._enable_ar = enable_ar
```

**E1.2** `fit` (L384-428): 条件化 Stage 1 与 Stage 2:

```python
if self._enable_neutralization:
    self._dual_neutralizer.fit(X)
    residuals_stage1 = self._dual_neutralizer.transform(X)
else:
    residuals_stage1 = X

if self._enable_ar:
    from .ar_model import ARDecoupler
    self._ar_decoupler = ARDecoupler(...)
    self._ar_decoupler.fit(residuals_stage1)
else:
    self._ar_decoupler = None

self._residuals_stage1 = residuals_stage1
```

**E1.3** `transform` (L444-502): 条件化 Stage 1/2/3:

```python
if self._enable_neutralization:
    residuals_stage1 = self._dual_neutralizer.transform(
        X, threat_level=threat_level, skip_stage2=skip_stage2)
else:
    residuals_stage1 = X

if self._ar_decoupler is None or skip_stage2:
    residuals_ar = residuals_stage1
else:
    residuals_ar = self._ar_decoupler.transform(residuals_stage1)

if self._enable_neutralization:
    residuals_final = self._neutralize_ar_residuals(residuals_ar)
else:
    residuals_final = residuals_ar
```

**复杂度**: O(1) 分支判断; 不新增 IO, 不新增循环。全开路径调用序列与 v3.4.2 完全一致。

### E2: DynamicFactorPipeline 开关映射

**文件**: `pipelines_v2.py`

**E2.1** `__init__` (L785-789) 增加:

```python
self._decoupler_enabled = me.get('decoupler', True)
```

**E2.2** `fit` (L811-828) 替换绑定分支:

```python
if self._neutralizer_enabled or self._decoupler_enabled:
    self._decoupler = CompositeDecoupler(
        industry_data=self.industry_data,
        market_cap_data=self.market_cap_data,
        max_ar_order=self.max_ar_order,
        ar_criterion=self.ar_criterion,
        decorrelation_strength=self.decorrelation_strength,
        enable_neutralization=self._neutralizer_enabled,
        enable_ar=self._decoupler_enabled,
    )
    self._decoupler.fit(X_imputed, **kwargs)
    X_decoupled = self._decoupler.transform(X_imputed, **kwargs)
else:
    self._decoupler = None
    X_decoupled = X_imputed
```

**E2.3** 日志文案: 全关 `"neutralizer/decoupler disabled, 跳过解耦 (identity)"`。

### E3: module_enabled 文档注释

**文件**: `pipelines_v2.py` L513-516 (`PipelineV2Config` dataclass, 非 config_v2.py)

```python
# 格式: {'imputer': False, 'winsorizer': False, 'scaler': False,
#        'neutralizer': False, 'decoupler': False}
# decoupler 仅作用于 Dynamic 管道 (AR 解耦), 其余管道忽略
```

### E4: 测试 (TDD Red → Green)

**新建** `tests/test_dynamic_component_separability.py` (8 例):

| 用例 | 函数 | 断言 |
|------|------|------|
| T1 | `test_default_all_on_bit_identical` | 输出 = `Imputer → CompositeDecoupler(default) → Standardizer` 手工链路 |
| T2 | `test_neutralizer_off_keeps_ar` | 输出 = `Imputer → ARDecoupler → Standardizer` |
| T3 | `test_decoupler_off_keeps_neutralization` | `_ar_decoupler is None`; `ar_summary is None`; `neutralization_summary` 非空 |
| T4 | `test_both_off_identity` | 输出 = imputed; `_decoupler is None` |
| T5 | `test_summary_matrix` | 4 组合摘要契约 |
| T10 | `test_create_pipeline_passes_decoupler_flag` | `_create_pipeline('dynamic')` 属性透传 |
| T12 | `test_composite_signature_defaults` | `inspect.signature` 两开关默认 `True` |
| T13 | `test_neutralizer_off_decoupler_on_skip_stage2_noop` | `skip_stage2` 在仅 AR 时无额外影响 |

**新建** `tests/test_factor_decoupler/test_composite_component_flags.py` (4 例):

| 用例 | 函数 | 断言 |
|------|------|------|
| T6 | `test_both_disabled_identity` | `fit_transform(X)` 与 `X` 逐值相等 |
| T7 | `test_ar_only_matches_ar_decoupler` | 输出 = `ARDecoupler.fit_transform(X)` |
| T8 | `test_neutralization_only` | `_ar_decoupler is None`; `ar_summary is None`; 输出 != X |
| T9 | `test_skip_stage2_with_flags_on_unchanged` | 全开 + `skip_stage2=True` 仍跳过 AR |

**更新** `tests/test_adapters/test_module_enabled.py::test_module_enabled_all_false`:
`me` 增加 `'decoupler': False` (T11)。

### E5: 版本 3.4.3 (6 处)

| 文件 | 位置 |
|------|------|
| `__init__.py` | L58 `__version__` |
| `pyproject.toml` | L7 `version` |
| `config_v2.py` | L371 `version` 默认值 |
| `reporting.py` | L40 `pipeline_version` |
| `tests/test_fix3_version_unification.py` | L12/L34/L41/L49/L58 |
| `tests/test_backtest/verify_fix3_manual.py` | L5 docstring + L21 `EXPECTED_VERSION` |

### E6: 文档与 ADR

`DECISIONS.md` ADR-045 / `CHANGELOG.md` / `README.md` / `docs/PROJECT_STATUS.md` /
`docs/ARCHITECTURE.md` / `docs/DEV_PROGRESS.md`。

---

## §2 工程细节检查 (步骤 5 显式清单)

| 维度 | 检查 | 结论 |
|------|------|------|
| 工程细节 | 全关时 `_decoupler=None`; 仅 AR 时 `_ar_decoupler=None`; 仅中性化时 `ar_summary=None` | 已定义, 测试覆盖 T4/T3/T8 |
| 版本 | Python ≥3.9 (`pyproject.toml:10`), 不使用 `X \| Y` 运行时注解 | ✅ |
| 依赖 | 无新增第三方依赖; `ARDecoupler` 仍在函数内延迟导入 (既有写法) | ✅ |
| 兼容 | 新增参数追加在签名尾部且默认 `True`; 既有位置参数调用不变 | ✅ |
| 接口 | `CompositeDecoupler.__init__` / `DynamicFactorPipeline.__init__` 签名与源码一致 | ✅ |
| 签名 | `transform(X, threat_level=None, skip_stage2=False, **kwargs)` 不变 | ✅ |
| 低效操作 | 分支为 O(1); 无新增循环/IO/copy (全关时反而少两次 transform) | ✅ |

**关键数值不变式**: 两开关全开时 `fit`/`transform` 的调用序列与 v3.4.2 相同, 不含任何新计算。

---

## §3 验收命令

```powershell
python -m pytest tests/test_dynamic_component_separability.py tests/test_factor_decoupler/test_composite_component_flags.py -q
python -m pytest tests/test_adapters/test_module_enabled.py tests/test_pipelines_v2.py tests/test_factor_decoupler tests/test_backtest/test_ablation_runner.py tests/test_endogeneity_regularizer -q
python -m pytest tests/test_fix3_version_unification.py -q
python tests/test_backtest/verify_fix3_manual.py
python -m pytest -q          # 全量基线 (1667 passed / 15 skipped)
```

**通过标准**: 定向全绿; 版本 7 passed + 手工 5/5; 全量 `0 failed` 且 passed ≥ 1667 + 新增用例数。

**实测 (2026-11-12)**: 定向 190 passed; 版本 7 passed + 手工 5/5; 全量
**1682 passed / 15 skipped / 0 failed** (166 warnings, 1794.26s, exit 0)。

---

## §4 文档同步

| 文档 | 内容 |
|------|------|
| `DECISIONS.md` | ADR-045: 组件可分离性修复, 语义变更与迁移写法 |
| `CHANGELOG.md` | v3.4.3 条目: 根因/接口/实测/兼容性 |
| `README.md` | v3.4.3 摘要 + 版本信息 + 历史行 |
| `docs/PROJECT_STATUS.md` | roadmap [x], 最近完成, 执行历史 |
| `docs/ARCHITECTURE.md` | Dynamic 管道组件开关说明 |
| `docs/DEV_PROGRESS.md` | 路标与模块矩阵 |

---

## §5 风险与回滚

见设计文档 §8。回滚 = `git revert`; 无数据迁移; 缓存代际不变。

---

## §6 Review 记录 (步骤 6, v1.1)

| 级别 | 检查项 | 结果 | 修正 |
|------|--------|------|------|
| L1 文件 | 所有被改文件存在; 新测试文件路径可创建 | ✅ | — |
| L2 行号 | E1/E2 引用的行号与 v3.4.2 工作树一致 | ✅ | — |
| L3 关键词 | `enable_neutralization` / `enable_ar` / `_decoupler_enabled` 与设计文档完全同名 | ✅ | — |
| L4 结构 | 代码片段可直接落地; 缩进/签名与源码风格一致 | ✅ | — |
| 偏差检查 | 实施文档新增 T13 (设计文档 T9 的补充) | ⚠️ 设计未列 | 已在 §1 E4 标注为补充用例, 不改变设计目标 |
| 依赖检查 | `ARDecoupler` 导入位置与既有 `fit` 内延迟导入一致 | ✅ | — |
| 回归风险 | `test_module_enabled_all_false` 若不更新将失败 (语义显式化) | ✅ 已列 T11 | — |
| 文档一致性 | 版本锚点 6 处与 `test_fix3_version_unification` 的单一锚点约定一致 | ✅ | — |

**独立只读复核 (Explore subagent, 2026-11-12)**: 结论未发现 P0/P1 幻觉 —— 全部行号、
现有签名、`get_summary()` 的 `ar_summary=None` 分支、`ARDecoupler(max_order/criterion/strength)`
参数名均与源码一致; `test_ablation_runner.py:953-967` 仅断言 `module_enabled` 配置,
不断言数值, 修复不会直接打破该用例。复核给出的 "FAIL" 指**当前仓库尚未实施** (版本仍 3.4.2、
组合器尚无新参数), 与文档计划一致, 不构成文档缺陷。唯一需注意: 消融报告中
`L1_neutralizer_off` 的 Dynamic 数值将变化, 属修复目的, 已在 §5 与设计 §6 标注。
