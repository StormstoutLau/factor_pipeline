# PL-01 去极值因果性修复设计 v1.1

**文档版本**: v1.1 (已实施, v3.3.3)
**日期**: 2026-10-22
**缺陷编号**: DEFECT-PL-01
**关联调研**: [PL01_OUTLIER_LOOKAHEAD_RESEARCH.md](PL01_OUTLIER_LOOKAHEAD_RESEARCH.md) v1.1
**关联决策**: ADR-027 (固定方法管线), ADR-029 (逐日横截面 Z-Score), ADR-037 (已记录)
**目标版本**: v3.3.3 (行为变更 + 新 ADR)
**设计原则**: 只改估计轴与参数解析, 不改截断函数; 结构上消除前视, 而非依赖调用顺序

---

## §0 决策摘要

| # | 决策 | 依据 |
|---|------|------|
| D1 | `ProcessingAdapter(process_type='outlier')` 统一改为**逐日横截面**估计 | 调研 §3/§4/§6; 因子面板的行=日期、列=股票 |
| D2 | `method='auto'` 构造期解析为 `percentile`; 显式方法按声明执行; 始终传 `auto_select=False` | ADR-027; 调研实测 200/200 选型漂移 |
| D3 | `percentile` 走**向量化快速路径** (hard clip); 其他方法**逐行复用** `SmartOutlierDetector` | 保留现有截断语义; 基准: 0.212s vs 2.56s (T=2500,N=3000) |
| D4 | `fit()` 对 outlier 为 **no-op**, 不存任何参数; 边界只在 `transform()` 用当日截面重算 | 与 ADR-029 的 `z_score` 分支同构, 结构上无泄漏面 |
| D5 | 不提供时间序列轴, 不接 `OutlierConfig`, 不扩展 `threshold` 语义 | 控制范围; 见 §10 后续任务 |
| D6 | 无效方法/分位数/非数值输入 **fail loud**; 行内有效值 <3 或零离散度 → 原样返回 | 可审计、可定位 |
| D7 | 版本升至 **v3.3.3**, 新增 **ADR-037** | 输出行为变更, 需独立记录 |

---

## §1 目标与非目标

### 1.1 目标

1. `ProcessingAdapter(outlier)` 对任意截断点 t 满足: 用 `[0,t]` 数据跑出的前 t 期输出 == 全样本跑后截取前 t 期 (逐值相等, 非排序相等)。
2. 显式 `method` 不再被 `auto_select` 覆盖; `auto` 的行为确定且可复现。
3. Static 管线真正执行 ADR-027 决策的 `percentile(1,99)`。
4. 保持现有各方法的截断函数语义 (percentile 硬截断, MAD/IQR/Z/quantile/adaptive 平滑截断, sigmoid_soft 软压缩)。
5. 不破坏 `transformation` / `standardization` / `enabled=False` / `get_stats` 等现有契约。

### 1.2 非目标

| 非目标 | 原因 |
|--------|------|
| 修 DEFECT-PL-02 (变换前视) / PL-05 (AR 样本内预测) / PL-06 (Mixed winsorizer) / PL-07 (顶层) | 独立缺陷, 各有实测登记 |
| 修 `PipelineV2ConfigUnified.to_pipeline_config()` 的 `TypeError` | 相邻但独立; 见调研 §5/附录 B |
| 接 `config_v2.OutlierConfig` / `threshold` 参数 | 属于配置层重构, 不在因果性修复范围 |
| 引入 rank-normal / 时间序列 expanding 轴 | 独立方法论决策; 调研 §6.5 |
| 修改 `SmartOutlierDetector` 的默认行为或 `auto_select` 默认值 | 直接调用方 (单测/外部) 不受影响 |
| 修改 Mixed 管线的 `_compute_winsorize_params` | PL-06 范围 |

---

## §2 现状与约束

### 2.1 当前代码路径

| 位置 | 现状 | 问题 |
|------|------|------|
| [adapters.py L320-L350](../../adapters.py#L320-L350) | `method` 原样存储; 无 outlier 专用分支 | `auto` 直接下沉到 detector |
| [adapters.py L413-L454](../../adapters.py#L413-L454) | `fit` 对 outlier 走 `X.values.flatten()` 全 panel 拟合 | 前视来源 1 |
| [adapters.py L456-L502](../../adapters.py#L456-L502) | `transform` 逐列套用全局边界 | 前视结果传播 |
| [transformers.py L31-L42](../../modules/factor_adaptive_winsor/core/transformers.py#L31-L42) | `SmartOutlierDetector(auto_select=True)` 默认 | 显式方法被覆盖 |
| [transformers.py L64-L67](../../modules/factor_adaptive_winsor/core/transformers.py#L64-L67) | `if self.auto_select: ...` | 前视来源 2 |
| [pipelines_v2.py L888-L890](../../pipelines_v2.py#L888-L890) | Static 传 `percentile(1,99)` | 名义与行为不一致 |
| [config_v2.py L42-L64](../../config_v2.py#L42-L64) | `OutlierConfig` 0-1 小数约定 | 与 detector 0-100 冲突; 本次不接 |

### 2.2 数据契约 (项目约定)

- `X`: `pd.DataFrame`, 行 = 日期, 列 = 股票; 单元格为因子值。
- 同一行的 N 个值构成 t 日横截面; 逐日截面处理只允许使用该行。
- `NaN` 表示缺失; 不得因缩尾改变缺失模式。
- 索引/列名必须保留。

### 2.3 兼容约束

- `ProcessingAdapter` 的**公开构造签名不变**:
  `ProcessingAdapter(process_type='outlier', method='auto', percentile_lower=1.0, percentile_upper=99.0, enabled=None, **params)`。
- `method` 的合法值沿用 detector: `percentile / quantile / z_score / mad / iqr / adaptive / sigmoid_soft` + `auto`。
- `percentile_lower/upper` 保持 **0-100 百分数**约定 (与 detector 一致)。
- `enabled=False` 必须仍是 identity, 且不导入外部依赖 (现有 P3-1 契约)。
- `transformation` / `standardization` 分支行为不变。

---

## §3 设计决策与备选

### D1: 逐日横截面, 而非 expanding / 全样本

| 方案 | 因果性 | 横截面可比 | 行为变化 | 结论 |
|------|--------|-----------|----------|------|
| 逐日截面 | 是 | 是 | 中 | **采用** |
| 逐列 expanding | 是 | 否 (同日不同股票用不同历史) | 大 | 不采用 |
| 全样本池化/逐列 | 否 | — | 无 | 拒绝 |

依据: 调研 §3.2/§4/§6; 生产因子面板用于横截面排序与 IC, 应使用同一日同一把尺子。逐日方案的截断不变式实测 `array_equal=True`。

### D2: `auto` → `percentile`, 显式方法按声明执行

- `auto` 在 `__init__` 解析为 `percentile`, `self.method` 存解析值, `self.requested_method` 存原值 (`auto`) 供审计。
- outlier 分支不再把 `auto_select` 留在默认 True; 行循环路径显式传 `auto_select=False`。
- 备选 `auto → mad` 被拒绝: 与 Static 显式 `percentile(1,99)` 冲突; N=30 时 MAD 抽样波动大 (调研 §1.3)。

### D3: percentile 快速路径 + 其他方法逐行复用

- `percentile`: `X.quantile(q, axis=1)` + `X.clip(..., axis=0)`, 向量化, 硬截断 (与 detector 的 `_apply_percentile_method` 语义一致)。
- 其他方法: 每行调用 `SmartOutlierDetector(method=..., auto_select=False).fit(row).transform(row)`, 完整复用 `_smooth_clip` / `sigmoid_soft`。
- 备选"全部逐行"被拒绝: percentile 是生产路径, 基准 2.56s vs 0.212s (T=2500,N=3000)。
- 备选"全部向量化"被拒绝: 需重新实现 `_smooth_clip` 的 C¹ 语义, 与"只改轴"原则冲突, 且验证成本高于收益。

### D4: `fit()` no-op, 不存参数

与 ADR-029 的 `_cross_sectional_zscore` 分支一致: 没有"全样本参数"可泄漏, 历史输出不会因新数据被重写。`fit()` 只做类型检查并置 `is_fitted=True`。

### D5: 范围控制

- 不新增公开 `scope` 参数; outlier 永远是截面轴。
- 不接 `OutlierConfig`; 不扩展 `threshold`; `params` 中 detector 不识别的键在行循环中被过滤 (避免 TypeError), 但**不解释其语义**。
- 不改变 `SmartOutlierDetector` 的默认 `auto_select=True` (直接调用方保持现状)。

### D6: 边界与失败模式

| 条件 | 行为 |
|------|------|
| `method` 不在合法集合 | `ValueError` (构造期) |
| `percentile_lower/upper` 不满足 `0 <= lo < hi <= 100` | `ValueError` (构造期) |
| `percentile_upper < 1.0` (疑似 0-1 约定误用, 含 0.01/0.99) | `ValueError`, 提示乘以 100 |
| 非 `DataFrame` 输入 | `TypeError` |
| 非数值列 | `TypeError` (包装 pandas 异常) |
| 重复 index 或 columns | `ValueError` |
| 空 DataFrame | 返回 `X.copy()` |
| 行内有效值 < 3 | 该行原样返回 |
| 行内零离散度 (`std==0`) | 该行原样返回 |

### D7: 版本与 ADR

- 目标版本 `v3.3.3`; 按既有统一约定同步 4 处: `pyproject.toml` / `__init__.__version__` / `config_v2.PipelineV2ConfigUnified.version` / `reporting.PipelineExecutionReport.pipeline_version`, 以及测试锚点 `tests/test_fix3_version_unification.py::EXPECTED_VERSION`。
- 拟新增 ADR-037: "去极值统一为逐日横截面 (DEFECT-PL-01)"。
- 修正 `principle_vs_hacking_audit_v2.md` 的"已修复"错误结论; 更新 `academic_literature_decision_criteria.md` 的状态说明。

---

## §4 接口设计

### 4.1 公开接口 (不变)

```python
ProcessingAdapter(
    process_type: str = 'outlier',
    method: str = 'auto',
    enabled: Optional[bool] = None,
    module_path=None, import_path=None, class_name=None,
    **params,
)
```

行为变化仅在 `process_type == 'outlier'` 时生效。

### 4.2 新增内部属性

| 属性 | 类型 | 含义 |
|------|------|------|
| `self.requested_method` | `str` | 调用方原始方法 (`auto` 保留) |
| `self.method` | `str` | 解析后方法 (`auto` → `percentile`) |
| `self._cross_sectional_outlier` | `bool` | 是否走逐日截面分支 |
| `self._outlier_percentile_lower/upper` | `float` | 0-100 约定, 构造期校验 |
| `self._outlier_detector_kwargs` | `dict` | 过滤后的 detector 构造参数 |

### 4.3 新增内部方法

```python
def _resolve_outlier_method(self, method: str) -> str
def _validate_outlier_percentiles(self, lo: float, hi: float) -> None
def _transform_outlier_cross_sectional(self, X: pd.DataFrame) -> pd.DataFrame
def _transform_outlier_percentile(self, X: pd.DataFrame) -> pd.DataFrame
def _transform_outlier_rowwise(self, X: pd.DataFrame) -> pd.DataFrame
```

均为私有, 不承诺外部稳定性。

### 4.4 方法 × 实现映射

| `method` | 估计轴 | 实现路径 | 截断语义 |
|----------|--------|----------|----------|
| `auto` | 解析为 `percentile` | 同下 | 硬截断 |
| `percentile` | 当日行 | 向量化 | `np.clip` 硬截断 |
| `quantile` | 当日行 | 逐行 detector | `_smooth_clip` (2.5%/97.5%) |
| `mad` | 当日行 | 逐行 detector | `_smooth_clip` (自适应阈值) |
| `iqr` | 当日行 | 逐行 detector | `_smooth_clip` (1.5×IQR) |
| `z_score` | 当日行 | 逐行 detector | `_smooth_clip` (自适应阈值) |
| `adaptive` | 当日行 | 逐行 detector | `_smooth_clip` (MAD/分位加权) |
| `sigmoid_soft` | 当日行 | 逐行 detector | sigmoid 软压缩 |

---

## §5 算法与数据流

### 5.1 `__init__`

```python
requested = method
if process_type == 'outlier':
    if method == 'auto':
        method = 'percentile'
    if method not in OUTLIER_METHODS:
        raise ValueError(...)
    validate_percentiles(params.get('percentile_lower', 1.0),
                         params.get('percentile_upper', 99.0))
    self._cross_sectional_outlier = True
else:
    self._cross_sectional_outlier = False

super().__init__(..., method=method, **params)
self.requested_method = requested
self.method = method
```

- `OUTLIER_METHODS = {'percentile','quantile','z_score','mad','iqr','adaptive','sigmoid_soft'}`。
- detector kwargs 只保留 `percentile_lower/percentile_upper/max_outlier_frac/adaptive_threshold`; 其他键 (含 `threshold`/`lower_percentile`/`upper_percentile`) 不传入 detector。
- `enabled` 逻辑不变。

### 5.2 `fit`

```python
if not self.enabled:
    self.is_fitted = True
    return self
if self._cross_sectional_outlier:
    if not isinstance(X, pd.DataFrame):
        raise TypeError(...)
    self._processor = None
    self._column_processors = {}
    self.is_fitted = True
    logger.info("outlier: 逐日截面, fit 无参数 (method=%s)", self.method)
    return self
# 原有 standardization / transformation 分支不变
```

### 5.3 `transform`

分支顺序:

```
enabled? -> identity
is_fitted? -> ValueError
_cross_sectional_zscore? -> 原有
_cross_sectional_outlier? -> 新分支
standardization per-column? -> 原有
generic per-column? -> 原有
```

新分支:

```python
def _transform_outlier_cross_sectional(self, X):
    if not isinstance(X, pd.DataFrame):
        raise TypeError(...)
    if X.index.has_duplicates or X.columns.has_duplicates:
        raise ValueError(...)
    if X.empty:
        return X.copy()
    if self.method == 'percentile':
        return self._transform_outlier_percentile(X)
    return self._transform_outlier_rowwise(X)
```

### 5.4 percentile 快速路径

```python
q_lo = self._outlier_percentile_lower / 100.0
q_hi = self._outlier_percentile_upper / 100.0
valid = X.notna().sum(axis=1) >= 3
lo = X.quantile(q_lo, axis=1).where(valid)
hi = X.quantile(q_hi, axis=1).where(valid)
out = X.clip(lower=lo, upper=hi, axis=0)
return out
```

要点:
- `quantile` 默认 `skipna=True`; NaN 不参与分位。
- `where(valid)` 把无效行的边界置 NaN; `clip` 在 NaN 边界下不改值 (设计探针已验证)。
- NaN 模式保持不变。
- 对 `X` 的数值类型: `quantile` 在非数值列上抛异常; 由外层包装为 `TypeError`。

### 5.5 其他方法逐行路径

```python
values = X.to_numpy(dtype=float, copy=True)
valid = np.sum(~np.isnan(values), axis=1)
with warnings.catch_warnings():
    warnings.simplefilter('ignore', RuntimeWarning)
    disp = np.nanstd(values, axis=1)
rows = np.flatnonzero((valid >= 3) & (disp > 1e-15))

detector = self._processor_class(
    method=self.method, auto_select=False, **self._outlier_detector_kwargs
)
for i in rows:
    detector.fit(values[i])
    values[i] = detector.transform(values[i])
return pd.DataFrame(values, index=X.index, columns=X.columns)
```

要点:
- detector 在 `transform` 内**局部创建**, 不挂到 `self`, 避免跨调用/跨线程共享拟合状态。
- `fit` 内部会 dropna; `transform` 对 NaN 返回 NaN, 缺失模式保持。
- 行内零离散度跳过, 避免 MAD/Z 的除零警告与无意义边界。
- `adaptive`/`sigmoid_soft` 的行级特征只来自该行, 仍是 `F_t` 内信息。

### 5.6 `get_stats`

新增字段:

```python
stats['requested_method'] = self.requested_method
if self._cross_sectional_outlier:
    stats['outlier_scope'] = 'cross_sectional'
    stats['percentile_lower'] = self._outlier_percentile_lower
    stats['percentile_upper'] = self._outlier_percentile_upper
```

`method` 继续报告解析后的方法; `fitted_params` 仅在 `_processor` 存在时报告 (outlier 截面分支不报告)。

---

## §6 工程细节

### 6.1 性能基准 (已验证)

环境: Python 3.12, pandas 2.x, T=2500, N=3000。

| 实现 | 耗时 | 说明 |
|------|------|------|
| 逐行 detector (`percentile`) | ~2.56s | 200 行实测 0.204s 外推 |
| 逐行 detector (`mad`) | ~3.30s | 200 行实测 0.264s 外推 |
| 向量化 quantile+clip | **0.212s** | 全 panel |

设计门限:
- `percentile` 路径 ≤ 0.5s (T=2500,N=3000)。
- 非 percentile 路径 ≤ 5s。
- 实施文档记录实测值; 若超出, 再评估是否将 `quantile`/`iqr` 也做快速路径。

### 6.2 内存与 dtype

- `to_numpy(dtype=float, copy=True)` 对 7.5M 格约 60MB; 与现有 `X.values.flatten()` 同量级。
- 输出统一为 float64; 原整型 DataFrame 会变为 float (缩尾本身需要浮点边界, 可接受)。
- 保留 index/columns 名称与顺序。

### 6.3 pandas 兼容

- `requires-python >=3.9`, `pandas>=2.0.0`; `DataFrame.quantile(axis=1)`、`DataFrame.clip(lower=Series, axis=0)`、`Series.where` 均为稳定 API。
- 不使用 `infer_objects`/`convert_dtypes` 等会改变 dtype 的调用。

### 6.4 日志

- `fit`: 一条 INFO, 说明截面模式与方法。
- `transform`: 一条 DEBUG, 报告 `T/N/跳过行数`; 不逐行打印。
- 不吞异常; 不再使用 `except (ValueError, TypeError, RuntimeError): continue` 的静默降级 (该模式属于旧 per-column 分支, 本次不扩展到新分支)。

### 6.5 线程/重入

- `ProcessingAdapter.transform` 不修改 `self` 的可变拟合状态 (只读解析参数), 局部 detector 每次调用新建。
- 同一 adapter 实例可被并发调用 (前提是 pandas 输入独立)。

---

## §7 兼容性与行为变更

| 对象 | 变更 | 处理 |
|------|------|------|
| `StaticFactorPipeline` | 去极值由全样本 auto 选型 → 逐日 `percentile(1,99)` | ADR-037 + CHANGELOG 显式声明; 历史 IC/Sharpe 重算 |
| `pipeline.py` legacy | `method='mad'` 真正按逐日 MAD 执行 (此前被 auto 覆盖) | 同上 |
| `demo.py` | `auto/mad` 行为按声明执行 | 示例输出变化 |
| `MixedFactorPipeline` | 自身 winsorizer 不变 (PL-06) | 不受影响 |
| `tests/test_pipelines_v2.py` | `method='auto'` 的对照实验改为 percentile | 回归验证 |
| 消融 L1 (`winsorizer_off`) | 开关两侧都变为逐日截面 | 重跑对照 |
| 消融 L4 `outlier_method` | 该字段本就未接线 (仅注入 config) | 本次不修; 文档标注 |
| 缓存 | 去极值输出改变, 旧因子缓存失效 | 缓存代际 `v2.2.0-cache` → `v2.2.1-cache`; 读取时校验 `meta.code_version`, 不一致即 MISS + 自愈删除 (一次性重建) |
| 直接调用 `SmartOutlierDetector` | 默认 `auto_select=True` 不变 | 不受影响 |

**破坏性**: Static/legacy/demo 输出值改变; 不是 API 破坏, 是数值行为变更。

---

## §8 测试设计 (TDD)

### 8.1 新增单测: `tests/unit/test_outlier_cross_sectional.py`

| # | 测试 | 断言 |
|---|------|------|
| 1 | `auto` 解析 | `adapter.method == 'percentile'`; `requested_method == 'auto'` |
| 2 | 显式方法保留 | 7 个方法逐一 `adapter.method == input` |
| 3 | percentile 边界 | 5×10 已知面板, 输出 == 手工 `np.percentile(row,[1,99])` + clip |
| 4 | percentile 截断不变式 | 全样本 vs 前 60%: `n_diff_cells=0`, `max_abs_diff=0` |
| 5 | NaN/元数据 | NaN 模式不变; index/columns 完全相等 |
| 6 | 小样本 | 1 行 / 2 列 / 全 NaN 行不崩且原样返回 |
| 7 | 零离散度 | 全等值行不产生警告, 输出不变 |
| 8 | MAD 截断不变式 | 逐行路径满足 |
| 9 | 全方法截断不变式 | 6 个显式方法参数化 |
| 10 | 无效方法 | `ValueError` (构造期) |
| 11 | 无效分位 | `ValueError`; 0.01/0.99 误用也 `ValueError` |
| 12 | 非 DataFrame | `TypeError` |
| 13 | `enabled=False` | identity; `_processor is None`; `_processor_class is None` |
| 14 | `fit` no-op | `_processor is None`; 重复 fit 无状态变化 |
| 15 | `get_stats` | `outlier_scope='cross_sectional'`, `requested_method`, 分位字段 |

### 8.2 集成测试

- `tests/integration/test_pipeline_truncation_invariance.py`:
  - 删除 `test_outlier_percentile_is_causal` 的 `xfail`;
  - 更新模块 docstring 的缺陷登记表;
  - 更新 `test_diagnostic_report` 实测矩阵;
  - 复核 PL-04/PL-06/PL-07 的 xfail reason 与实测值。
- 新增可选断言: `test_mixed_pipeline_output_is_unit_variance` 保持通过。

### 8.3 回归靶向

```
tests/unit/test_adapters_mock.py
tests/test_adapters/test_module_enabled.py
tests/test_pipelines_v2.py
tests/test_p3_phase2_config_migration.py
tests/unit/test_step1_winsorizer_percentile.py
tests/integration/test_pipeline_truncation_invariance.py
tests/test_factor_orthogonalizer/test_adapter.py
```

### 8.4 性能验证 (手工, 不入 CI)

复用设计探针: T=2500,N=3000, 记录 percentile 快速路径与非 percentile 逐行路径耗时; 写入实施文档。

---

## §9 验收标准

- [ ] `test_outlier_percentile_is_causal` 通过 (无 xfail), `n_diff_cells=0`, `max_abs_diff=0`。
- [ ] 6 个显式方法的截断不变式全部通过。
- [ ] `auto` → `percentile`; 显式方法不再被覆盖 (单测断言)。
- [ ] percentile 输出等于手工逐行分位边界 (1e-12)。
- [ ] NaN 模式、index、columns 完全保留。
- [ ] `enabled=False` identity 与 `_processor_class is None` 契约保持。
- [ ] Static 端到端差异降到 PL-02 量级 (实施后实测并记录)。
- [ ] 靶向回归全绿; 全量套件慢测单独安排。
- [ ] 性能门限满足 (§6.1)。
- [ ] ADR-037 / CHANGELOG v3.3.3 / 版本 4 处同步 / 勘误文档更新。

---

## §10 风险、回滚与后续

### 10.1 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| Static/legacy 输出变化 | 历史 IC/Sharpe 不可比 | ADR/CHANGELOG 声明; 重跑必要实验 |
| 非 percentile 逐行路径慢 | 大面板耗时 ~3.3s/因子 | 仅非生产方法; 记录基准; 必要时后续向量化 |
| 逐行 adaptive 阈值日间变化 | 显式 MAD/Z 方法结果不稳定 | 属方法自身语义; 本次只保证因果性; 后续可讨论固定 threshold |
| 意外传入 0-1 分位 | 极端过度裁剪 | 构造期 ValueError 拦截 |
| 下游依赖 `adapter.method='auto'` | 断言失败 | 保留 `requested_method`; 更新相关测试 |

### 10.2 回滚

- 分支可独立回退: 移除 `_cross_sectional_outlier` 分支与 `auto` 解析, 恢复原 else 分支; 重新加回 PL-01 的 xfail。
- 无数据迁移/缓存格式变更; 缓存代际需 bump (`v2.2.1-cache`) 以触发一次性重建; 回滚成本低。

### 10.3 后续任务 (不在本次)

1. `OutlierConfig` 接线与 0-1/0-100 单位统一 (含 `to_pipeline_config()` 的 TypeError)。
2. `threshold` 语义 (固定阈值 vs 自适应阈值) 的独立 ADR。
3. rank-normal / 时序 expanding 轴的方法论评估。
4. 非 percentile 方法的向量化 (若性能成为瓶颈)。

---

## §11 实施顺序 (供实施文档细化)

1. **Red**: 新增 `tests/unit/test_outlier_cross_sectional.py` (先失败); 将 PL-01 xfail 保留直到代码就绪。
2. **Green-1**: `__init__` 解析/校验/属性; 修 `auto` 覆盖。
3. **Green-2**: `fit` no-op 分支 + percentile 快速路径; 移除 PL-01 xfail。
4. **Green-3**: 其他方法逐行路径 + 边界守卫。
5. **回归**: 靶向测试 + 诊断矩阵更新 + xfail reason 更新。
6. **文档/版本**: ADR-037, CHANGELOG v3.3.3, 版本 4 处同步, 勘误文档, DEV_PROGRESS/ARCHITECTURE 基线。
7. **验收**: 按 §9 checklist 逐项打勾, 记录实测。

---

## §12 参考

- 调研文档: [PL01_OUTLIER_LOOKAHEAD_RESEARCH.md](PL01_OUTLIER_LOOKAHEAD_RESEARCH.md) §1-§7
- [DECISIONS.md ADR-027](../../DECISIONS.md#L1799-L1825), [ADR-029](../../DECISIONS.md#L1934-L1963)
- [adapters.py L320-L502](../../adapters.py#L320-L502)
- [transformers.py L28-L250 / L488-L495](../../modules/factor_adaptive_winsor/core/transformers.py#L28-L250)
- [pipelines_v2.py L888-L890](../../pipelines_v2.py#L888-L890)
- [test_pipeline_truncation_invariance.py L230-L244](../../tests/integration/test_pipeline_truncation_invariance.py#L230-L244)
- [test_step1_winsorizer_percentile.py L53-L66](../../tests/unit/test_step1_winsorizer_percentile.py#L53-L66)

---

## 附录 A: 设计自检

| 检查项 | 结果 |
|--------|------|
| 每条决策可追溯到调研证据 | 是 (D1-D7 对应调研 §1-§6) |
| 公开 API 是否变化 | 否 (仅内部属性/方法) |
| 是否引入新的前视面 | 否 (fit 无参数; transform 只用当日行) |
| 是否保留现有截断语义 | 是 (percentile hard; 其他复用 detector) |
| 是否覆盖小样本/NaN/零离散度 | 是 (§5.4/§5.5) |
| 是否处理 0-1 分位误用 | 是 (构造期 ValueError) |
| 测试是否覆盖验收标准 | 是 (§8 映射 §9) |
| 是否明确非目标 | 是 (§1.2) |
| 是否包含性能基准 | 是 (§6.1) |
| 是否包含回滚方案 | 是 (§10.2) |
