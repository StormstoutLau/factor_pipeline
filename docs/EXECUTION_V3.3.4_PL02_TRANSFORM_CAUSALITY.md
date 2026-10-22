# v3.3.4 PL-02 变换因果性修复 — 实施文档

**文档版本**: v1.0
**日期**: 2026-10-22
**缺陷**: DEFECT-PL-02
**设计依据**: [docs/analysis/PL02_TRANSFORM_LOOKAHEAD_DESIGN.md](analysis/PL02_TRANSFORM_LOOKAHEAD_DESIGN.md) v1.0
**调研依据**: [docs/analysis/PL02_TRANSFORM_LOOKAHEAD_RESEARCH.md](analysis/PL02_TRANSFORM_LOOKAHEAD_RESEARCH.md) v1.10
**目标版本**: v3.3.4
**变更性质**: 数值行为变更 + 配置字段删除 (`auto_optimize` 参数移除)
**实施方式**: 严格 TDD (Red → Green → 回归 → 文档/版本)
**行号说明**: 文中行号仅作导航, 以类名/函数名/测试名为准 (编辑后会漂移)

---

## §0 实施摘要

| 项 | 内容 |
|---|------|
| 核心改动 | 变换从"全 panel 池化 + `auto` 选型"改为"逐日截面 rank→正态 + 构造期固定方法" |
| 代码文件 | `modules/factor_adaptive_winsor/core/transformers.py`; `adapters.py`; `config_v2.py`; `pipelines_v2.py`; `demo_v2.py` |
| 测试文件 | 新增 `tests/unit/test_transform_rank_cross_sectional.py`; 重写 `tests/unit/test_adaptive_transformer_identity.py`; 修改 `tests/test_fix2_config_unification.py`; 修改 `tests/integration/test_pipeline_truncation_invariance.py`; 修改 `tests/test_fix3_version_unification.py` |
| 版本同步 | 4 处声明 + 测试锚点 + 缓存 `code_version` |
| 文档 | ADR-038 / CHANGELOG v3.3.4 |
| 验收关键 | PL-02 与 PL-04 的 xfail 摘除后测试通过; `n_diff_cells=0`, `max_abs_diff=0` |

**不实施**: PL-05/06/07; `EnhancedRankPreservingScaler` 的两处死实现; `StandardizationConfig.method='rank'` 死配置; 旧 transform 逐列路径的潜伏缺陷; 因子级 `identity` 配置; 类名重命名.

---

## §1 前置条件与基线

### 1.1 环境

| 项 | 值 |
|---|-----|
| 解释器 | `C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe` |
| 工作目录 | `F:\Coding` (父目录, 避免 `factor_pipeline/types.py` 遮蔽标准库 `types`) |
| Python / pandas / scipy | `>=3.9` / `>=2.0.0` / 现有版本 |
| 新增依赖 | **无** (`scipy.stats.rankdata` / `norm` 已在用) |
| 删除依赖 | 无 (`sklearn PowerTransformer` 不再被变换路径使用, 但其他模块仍可能引用) |

### 1.2 基线 (实施前必须记录)

```powershell
cd F:\Coding
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/integration/test_pipeline_truncation_invariance.py -q
```

预期: **7 passed / 5 xfailed** (PL-02/04/05/06/07 登记). 若不符, 先记录实际值.

```powershell
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/unit/test_adapters_mock.py `
  factor_pipeline/tests/test_adapters/test_module_enabled.py -q
```

预期: **38 passed, 2 skipped**.

```powershell
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/test_pipelines_v2.py `
  factor_pipeline/tests/test_fix2_config_unification.py `
  factor_pipeline/tests/unit/test_config_v2.py -q
```

预期: 全绿. 记录实际数量, 实施后对齐.

修复后集成套件预期: **9 passed / 3 xfailed** (摘除 PL-02 与 PL-04).

---

## §2 变更清单

| # | 文件 | 变更 | 风险 |
|---|------|------|------|
| 1 | `modules/factor_adaptive_winsor/core/transformers.py` | 模块级 `rank_transform_1d` + 别名常量; `AdaptiveTransformer` 重写 (先验参数 / 删除选型链 / rank 分支) | 高 |
| 2 | `adapters.py` | 常量; `__init__` 方法解析; `fit`/`transform` 的 rank/identity 分支; `_transform_rank_cross_sectional` | 高 |
| 3 | `config_v2.py` | `TransformationConfig` 字段收敛; `MixedPipelineConfig.conditional_transform` 删除; `to_pipeline_v2_config()` 映射改 | 中 |
| 4 | `pipelines_v2.py` | `PipelineV2Config` 字段; Static/Mixed 入参; Mixed 顺序; 删除 `_diagnose_transform_need`; `_create_pipeline` | 高 |
| 5 | `demo_v2.py` | 删除 2 处 `mixed_conditional_transform=True` | 低 |
| 6 | `tests/unit/test_transform_rank_cross_sectional.py` | **新增** 24 个测试 | 低 |
| 7 | `tests/unit/test_adaptive_transformer_identity.py` | **重写** 为 rank/先验方法行为测试 | 低 |
| 8 | `tests/test_fix2_config_unification.py` | `test_09` 重写; `test_11` (嵌套→扁平全字段) 改用 `transformation.method/target_distribution` | 低 |
| 9 | `tests/test_pipelines_v2.py` | `test_mixed_pipeline_processing` 删除 `conditional_transform` / `skew_threshold` / `kurt_threshold` 三个构造参数 | 低 |
| 10 | `tests/test_p3_phase2_config_migration.py` | `test_03` 的 `mixed_skew_threshold=2.5` 改为 `mixed_transformation_method='identity'` | 低 |
| 11 | `tests/test_backtest/verify_fix2_manual.py` | 三字段改用 `transformation.method` / `target_distribution` (L49-51, L77-79, L128-130) | 低 |
| 12 | `tests/integration/test_pipeline_truncation_invariance.py` | 摘除 PL-02/PL-04 xfail; 更新登记表; 修 PL-06 reason | 低 |
| 13 | `tests/test_fix3_version_unification.py` | `EXPECTED_VERSION` → 3.3.4; 缓存版本 → 2.2.2-cache (3 处) | 低 |
| 14 | `pyproject.toml` / `__init__.py` / `config_v2.py` / `reporting.py` | 版本 → 3.3.4 | 低 |
| 15 | `backtest/cache_manager.py` | `CODE_VERSION` → `v2.2.2-cache` | 中 (一次性重建) |
| 16 | `DECISIONS.md` / `CHANGELOG.md` | ADR-038 / v3.3.4 条目 | 低 |

---

## §3 代码实施

### 3.1 `transformers.py`

#### 3.1.1 模块级常量与函数 (放在 `AdaptiveTransformer` 之前)

```python
# PL-02: 变换方法解析与截面 rank
TRANSFORMATION_METHOD_ALIASES = {
    'auto': 'rank',
    'none': 'identity',
    'box_cox': 'boxcox',
    'yeo_johnson': 'yeojohnson',
    'quantile': 'rank',
}
TRANSFORMATION_METHODS = frozenset(
    {'rank', 'identity', 'log', 'boxcox', 'yeojohnson', 'power'}
)

_RANK_BLOM_K = 3.0 / 8.0      # Blom 偏移
_RANK_BLOM_D = 1.0 / 4.0      # Blom 分母修正


def rank_transform_1d(values: np.ndarray, target: str = 'normal') -> np.ndarray:
    """无状态 PIT 映射: 1-D 秩 -> 目标分布. NaN 保持 NaN 且不参与排名."""
    out = np.full(values.shape, np.nan, dtype=float)
    ok = ~np.isnan(values)
    n = int(ok.sum())
    if n < 2:
        return out
    ranks = stats.rankdata(values[ok], method='average')
    if target == 'normal':
        out[ok] = stats.norm.ppf((ranks - _RANK_BLOM_K) / (n + _RANK_BLOM_D))
    elif target == 'uniform':
        out[ok] = (2.0 * ranks - n - 1.0) / n
    else:
        raise ValueError(f"未知 target_distribution: {target!r}; 合法值: 'normal' / 'uniform'")
    return out
```

- `stats` 是文件顶部已导入的 `scipy.stats`.
- 不加公共导出 (`__all__` 未定义于该文件).

#### 3.1.2 `AdaptiveTransformer.__init__`

```python
def __init__(self, method: str = 'rank',
             target_distribution: Literal['uniform', 'normal'] = 'normal',
             lam: Optional[float] = None,
             offset: float = 0.0,
             power_param: Optional[float] = None):
    requested = method
    method = TRANSFORMATION_METHOD_ALIASES.get(method, method)
    if method not in TRANSFORMATION_METHODS:
        raise ValueError(
            f"未知的变换方法: {requested!r}; 合法值: "
            f"{sorted(TRANSFORMATION_METHODS)} 或 "
            f"{sorted(TRANSFORMATION_METHOD_ALIASES)}"
        )
    if target_distribution not in ('normal', 'uniform'):
        raise ValueError(
            f"未知 target_distribution: {target_distribution!r}; 合法值: 'normal' / 'uniform'"
        )
    if method in ('boxcox', 'yeojohnson') and lam is None:
        raise ValueError(f"method={method!r} 需要先验参数 lam (禁止 fit 估计)")
    if method == 'power' and power_param is None:
        raise ValueError("method='power' 需要先验参数 power_param (禁止 fit 估计)")

    super().__init__(
        method=method,
        target_distribution=target_distribution,
    )
    self.requested_method = requested
    self.method = method
    self.target_distribution = target_distribution
    self.lam = lam
    self.offset = float(offset)
    self.power_param = power_param
```

**删除**: `auto_optimize` 参数与属性, `_analyze_features`, `_select_optimal_transform`,
`_fit_yeojohnson`, `_fit_boxcox`, `_fit_quantile`, `_fit_power`, `_fit_log`.

#### 3.1.3 `fit`

```python
def fit(self, X):
    """无状态: 先验参数已在 __init__ 校验, 不估计任何统计量."""
    self.fitted_params = {'method': self.method}
    self.is_fitted = True
    return self
```

#### 3.1.4 `transform`

```python
def transform(self, X):
    if not self.is_fitted:
        raise ValueError("请先调用fit方法")

    if self.method == 'identity':
        return X

    if self.method == 'rank':
        if isinstance(X, pd.DataFrame):
            raise TypeError(
                "AdaptiveTransformer(method='rank') 是截面语义, "
                "必须经由 ProcessingAdapter._cross_sectional_rank 使用; "
                "直接传 DataFrame 会被 BaseTransformer._to_array 展平为全局池化"
            )
        arr = self._to_array(X)
        out = rank_transform_1d(arr, self.target_distribution)
        if isinstance(X, pd.Series):
            return self._restore_format(out, X)
        return out

    original_format = X if isinstance(X, pd.Series) else None
    X_array = self._to_array(X)
    if self.method == 'yeojohnson':
        transformed = self._apply_yeojohnson(X_array)
    elif self.method == 'boxcox':
        transformed = self._apply_boxcox(X_array)
    elif self.method == 'power':
        transformed = self._apply_power(X_array)
    elif self.method == 'log':
        transformed = self._apply_log(X_array)
    else:
        raise ValueError(f"未知的变换方法: {self.method}")

    if original_format is not None:
        return self._restore_format(transformed, original_format)
    return transformed
```

**注意**: `original_format` 不再接受 `pd.DataFrame` (rank 已拒绝; 其余方法经
adapter 逐列调用时只传 Series). 若直接调用方传 DataFrame 给非 rank 方法,
`_to_array` 会 flatten, 与历史行为一致, 不额外处理.

**N 下限只在 adapter 层**: `rank_transform_1d` 本身不做 N<10 回落;
`AdaptiveTransformer` 是纯算法入口, 截面保护由
`ProcessingAdapter._transform_rank_cross_sectional` 承担.

#### 3.1.5 四个 `_apply_*` (改为读取先验参数)

```python
def _apply_log(self, X: np.ndarray) -> np.ndarray:
    shifted = X + self.offset
    valid = shifted[~np.isnan(shifted)]
    if np.any(valid <= 0):
        raise ValueError(
            f"log 变换: X + offset 含非正值 (offset={self.offset}); "
            "请提供更大的 offset"
        )
    return np.log(shifted)


def _apply_boxcox(self, X: np.ndarray) -> np.ndarray:
    valid = X[~np.isnan(X)]
    if np.any(valid <= 0):
        raise ValueError("boxcox 变换: 需要严格正值")
    lam = self.lam
    if abs(lam) < 1e-12:
        return np.log(X)
    return (np.power(X, lam) - 1.0) / lam


def _apply_yeojohnson(self, X: np.ndarray) -> np.ndarray:
    lam = self.lam
    out = np.full(X.shape, np.nan, dtype=float)
    pos = (X >= 0) & ~np.isnan(X)
    neg = (X < 0) & ~np.isnan(X)
    with np.errstate(invalid='ignore', over='ignore', divide='ignore'):
        if abs(lam) < 1e-12:
            out[pos] = np.log1p(X[pos])
        else:
            out[pos] = (np.power(X[pos] + 1.0, lam) - 1.0) / lam
        if abs(lam - 2.0) < 1e-12:
            out[neg] = -np.log1p(-X[neg])
        else:
            out[neg] = -(
                np.power(1.0 - X[neg], 2.0 - lam) - 1.0
            ) / (2.0 - lam)
    return out


def _apply_power(self, X: np.ndarray) -> np.ndarray:
    return np.sign(X) * np.power(np.abs(X), self.power_param)
```

**YJ 公式依据** (调研 §3.3.1 实测): λ=1 时 `pos` 分支恒等, `neg` 分支为
`−((1−x)¹−1)/1 = x`, 故 λ=1 ≡ identity; λ=2 时 `neg` 分支为 `−log(1−x)`,
**不是** `signed_log1p`. 该实现与 scikit-learn `PowerTransformer` 的
`standardize=False` 数值一致 (测试 12 对拍).

#### 3.1.6 `get_stats`

在 `AdaptiveTransformer` 已有 `get_stats` (若继承基类无额外字段, 可省略).
`ProcessingAdapter.get_stats` 会读 `self._processor.fitted_params`, rank 分支
`_processor is None`, 不触发.

---

### 3.2 `adapters.py`

#### 3.2.1 常量 (接在 PL-01 常量之后, L56 附近)

```python
# PL-02: transformation 方法解析与截面 rank
_TRANSFORMATION_ALIASES = {
    'auto': 'rank',
    'none': 'identity',
    'box_cox': 'boxcox',
    'yeo_johnson': 'yeojohnson',
    'quantile': 'rank',
}
_TRANSFORMATION_METHODS = frozenset(
    {'rank', 'identity', 'log', 'boxcox', 'yeojohnson', 'power'}
)
_MIN_RANK_CROSS_SECTION_OBS = 10
```

与 `transformers.py` 的两份常量由测试 `test_alias_consistency` 断言一致.

#### 3.2.2 `ProcessingAdapter.__init__`

在 PL-03 的 standardization 解析之后、`super().__init__` 之前插入:

```python
if process_type == 'transformation':
    method = _TRANSFORMATION_ALIASES.get(method, method)
    if method not in _TRANSFORMATION_METHODS:
        raise ValueError(
            f"ProcessingAdapter(transformation): 未知 method={requested_method!r}; "
            f"合法值: {sorted(_TRANSFORMATION_METHODS)} 或 "
            f"{sorted(_TRANSFORMATION_ALIASES)}"
        )
    target_distribution = params.get('target_distribution', 'normal')
    if target_distribution not in ('normal', 'uniform'):
        raise ValueError(
            f"ProcessingAdapter(transformation): 未知 "
            f"target_distribution={target_distribution!r}"
        )
else:
    target_distribution = None
```

在现有属性赋值区 (L373-L380 附近) 追加:

```python
self._identity_transformation = (
    process_type == 'transformation' and method == 'identity'
)
self._cross_sectional_rank = (
    process_type == 'transformation' and method == 'rank'
)
self.target_distribution = target_distribution
```

**注意**: `params` 仍含 `target_distribution`, 经 `super().__init__(..., **params)`
进入 `self.params`, 由 `fit` 传给 `AdaptiveTransformer(**processor_params)`.
`lam` / `offset` / `power_param` 同理.

#### 3.2.3 `fit`

在 `_cross_sectional_outlier` 与 `_cross_sectional_zscore` 分支之后、
standardization 逐列分支之前插入:

```python
# PL-02: identity / rank 均无状态, 不做 flatten fit
if self._identity_transformation or self._cross_sectional_rank:
    if not isinstance(X, pd.DataFrame):
        raise TypeError(
            f"ProcessingAdapter(transformation, method={self.method}): "
            f"需要 pd.DataFrame, 收到 {type(X).__name__}"
        )
    if X.index.has_duplicates or X.columns.has_duplicates:
        raise ValueError(
            "ProcessingAdapter(transformation): index/columns 必须唯一"
        )
    self._processor = None
    self._column_processors = {}
    self.is_fitted = True
    logger.info(
        "ProcessingAdapter(transformation, method=%s): 无状态, fit 为 no-op",
        self.method,
    )
    return self
```

#### 3.2.4 `transform`

在 `_cross_sectional_zscore` 分支之后、standardization 逐列分支之前插入:

```python
# PL-02: identity 短路 (与 enabled=False 语义一致, 不复制)
if self._identity_transformation:
    return X

# PL-02: 逐日截面 rank
if self._cross_sectional_rank:
    return self._transform_rank_cross_sectional(X)
```

#### 3.2.5 新增 `_transform_rank_cross_sectional`

放在 `_transform_outlier_rowwise` 之后、`get_stats` 之前:

```python
def _transform_rank_cross_sectional(self, X: pd.DataFrame) -> pd.DataFrame:
    """逐日截面 rank -> target_distribution (PL-02).

    无状态: 每个截面只使用当日有效值. 截断不变式结构成立.
    """
    if not isinstance(X, pd.DataFrame):
        raise TypeError(
            f"ProcessingAdapter(transformation, method='rank'): "
            f"需要 pd.DataFrame, 收到 {type(X).__name__}"
        )
    if X.index.has_duplicates or X.columns.has_duplicates:
        raise ValueError(
            "ProcessingAdapter(transformation, method='rank'): index/columns 必须唯一"
        )
    if X.empty:
        return X.copy()

    # 延迟导入: 保持 mock 路径不受影响
    from factor_pipeline.modules.factor_adaptive_winsor.core.transformers import (
        rank_transform_1d,
    )

    arr = X.to_numpy(dtype=float)
    out = np.empty_like(arr)
    n_valid = np.isfinite(arr).sum(axis=1)

    for i in range(arr.shape[0]):
        row = arr[i]
        if n_valid[i] < 2:
            # N<2 无法排名; 原样返回, 避免 nanmean/nanstd 的空切片警告
            out[i] = row
            continue
        if n_valid[i] < _MIN_RANK_CROSS_SECTION_OBS:
            mu = np.nanmean(row)
            sd = np.nanstd(row, ddof=1)
            if np.isfinite(sd) and sd > 0:
                out[i] = (row - mu) / sd
            else:
                out[i] = row
        else:
            out[i] = rank_transform_1d(row, self.target_distribution)

    n_small = int(
        ((n_valid >= 2) & (n_valid < _MIN_RANK_CROSS_SECTION_OBS)).sum()
    )
    n_degenerate = int((n_valid < 2).sum())
    if n_small:
        logger.warning(
            "PL-02 rank: %d 个截面 N<%d, 回落截面 z-score",
            n_small, _MIN_RANK_CROSS_SECTION_OBS,
        )
    if n_degenerate:
        logger.warning(
            "PL-02 rank: %d 个截面 N<2, 原样返回", n_degenerate,
        )

    return pd.DataFrame(out, index=X.index, columns=X.columns)
```

#### 3.2.6 `get_stats`

在 `_cross_sectional_outlier` 分支之后追加:

```python
if self._cross_sectional_rank:
    stats['transform_scope'] = 'cross_sectional'
    stats['target_distribution'] = self.target_distribution
```

#### 3.2.7 兼容性检查

- `enabled` 对 transformation 仍强制 `True` (PL-01 的 ABLATION E1 契约不变).
- `_processor_class` 在 `__init__` 仍会导入 `AdaptiveTransformer` (非 mock 路径);
  identity/rank 分支不实例化它, 但导入本身保留, 以免破坏 `AdaptersImportError` 契约.
- 若 `enabled=False` 且 transformation: 仍走 `fit` 的 `not self.enabled` 早退
  (`is_fitted=True`, `_processor=None`), 与现状一致.

---

### 3.3 `config_v2.py`

#### 3.3.1 `TransformationConfig`

```python
class TransformationConfig(BaseModel):
    """变换步骤配置"""

    method: Literal[
        'auto', 'rank', 'identity', 'none', 'log',
        'box_cox', 'yeo_johnson', 'power', 'quantile',
    ] = Field(default='rank', description="变换方法")
    target_distribution: Literal['uniform', 'normal'] = \
        Field(default='normal', description="PIT 目标分布")
```

**删除**: `skew_threshold`, `kurt_threshold`.

#### 3.3.2 `MixedPipelineConfig`

删除 `conditional_transform` 字段 (L185-L188). 保留 `mild_winsorization`.

#### 3.3.3 `to_pipeline_v2_config()`

- 更新 docstring 的字段映射说明 (L489-L493).
- 替换 L527-L530:

```python
# 变换配置 (嵌套 → 扁平)
static_transformation_method=self.static.transformation.method,
static_target_distribution=self.static.transformation.target_distribution,
mixed_transformation_method=self.mixed.transformation.method,
mixed_target_distribution=self.mixed.transformation.target_distribution,
```

#### 3.3.4 `to_pipeline_config()`

L463 的 `params=self.static.transformation.model_dump()` 不变. 注意 `model_dump()`
现在输出 `{'method': ..., 'target_distribution': ...}`; legacy `AdaptiveTransformer`
接受这两个键. `method='auto'` 不再出现在默认配置中 (默认 `'rank'`).

---

### 3.4 `pipelines_v2.py`

#### 3.4.1 `PipelineV2Config` (L680-L709)

删除:

```python
mixed_conditional_transform: bool = True
mixed_skew_threshold: float = 2.0
mixed_kurt_threshold: float = 5.0
```

新增:

```python
# PL-02: 变换配置 (Static / Mixed 共用一套)
static_transformation_method: str = 'rank'
static_target_distribution: str = 'normal'
mixed_transformation_method: str = 'rank'
mixed_target_distribution: str = 'normal'
```

#### 3.4.2 `StaticFactorPipeline.__init__`

```python
def __init__(self,
             neutralizer_params: Optional[Dict] = None,
             transformation_params: Optional[Dict] = None,
             enable_garch: bool = False,
             garch_params: Optional[Dict] = None,
             module_enabled: Optional[Dict[str, bool]] = None):
    super().__init__()
    me = module_enabled or {}
    tp = transformation_params or {}
    transform_method = tp.get('method', 'rank')
    transform_target = tp.get('target_distribution', 'normal')
    transform_extra = {
        k: v for k, v in tp.items()
        if k not in ('method', 'target_distribution')
    }
    self.steps = [
        ('imputer', ImputerAdapter(strategy='ffill_ts', enabled=me.get('imputer', True))),
        ('outlier', ProcessingAdapter(process_type='outlier', method='percentile',
                                      percentile_lower=1.0, percentile_upper=99.0,
                                      enabled=me.get('winsorizer', True))),
        ('neutralize', NeutralizerAdapter(enabled=me.get('neutralizer', True),
                                          **(neutralizer_params or {}))),
        ('transform', ProcessingAdapter(process_type='transformation',
                                        method=transform_method,
                                        target_distribution=transform_target,
                                        **transform_extra)),
    ]
    ...
```

`transform_extra` 用于传递 `lam` / `offset` / `power_param` 等先验参数.

#### 3.4.3 `MixedFactorPipeline.__init__`

```python
def __init__(self,
             mixed_winsor_sigma: float = 3.0,
             transformation_params: Optional[Dict] = None,
             neutralizer_params: Optional[Dict] = None,
             module_enabled: Optional[Dict[str, bool]] = None):
    super().__init__()
    self.mixed_winsor_sigma = mixed_winsor_sigma
    self._transformation_params = transformation_params or {}
    self.neutralizer_params = neutralizer_params or {}
    self._transformer = None
    ...
```

**删除**: `conditional_transform`, `skew_threshold`, `kurt_threshold`, `_needs_transform`.

**保留**: `self.neutralizer_params`, `self._transformer = None`, 以及 `module_enabled`
派生的 `_imputer_enabled` / `_winsorizer_enabled` / `_neutralizer_enabled` /
`_scaler_enabled` (原逻辑不动).

#### 3.4.4 `MixedFactorPipeline.fit` (顺序 + 口径)

```python
def fit(self, X: pd.DataFrame, **kwargs) -> 'MixedFactorPipeline':
    self._intermediate_data = {}

    # Step 1: 插补
    self._imputer = ImputerAdapter(strategy='ffill_ts', enabled=self._imputer_enabled)
    self._imputer.fit(X, **kwargs)
    X = self._imputer.transform(X, **kwargs)
    self._intermediate_data['imputation'] = X.copy()

    # Step 2: 温和缩尾 (PL-06 未修, 仍为全样本参数)
    if self._winsorizer_enabled:
        self._winsorize_params = self._compute_winsorize_params(X)
        X = self._apply_winsorize(X)
    else:
        self._winsorize_params = None
    self._intermediate_data['outlier'] = X.copy()

    # Step 3: 中性化 (I-INT: 先剥离暴露)
    self._neutralizer = NeutralizerAdapter(enabled=self._neutralizer_enabled,
                                           **self.neutralizer_params)
    self._neutralizer.fit(X, **kwargs)
    X = self._neutralizer.transform(X, **kwargs)
    self._intermediate_data['neutralize'] = X.copy()

    # Step 4: 变换 (fit 与 transform 使用同一输入)
    tp = self._transformation_params
    extra = {k: v for k, v in tp.items()
             if k not in ('method', 'target_distribution')}
    self._transformer = ProcessingAdapter(
        process_type='transformation',
        method=tp.get('method', 'rank'),
        target_distribution=tp.get('target_distribution', 'normal'),
        **extra,
    )
    self._transformer.fit(X, **kwargs)
    X = self._transformer.transform(X, **kwargs)
    self._intermediate_data['transform'] = X.copy()

    # Step 5: 标准化
    self._standardizer = ProcessingAdapter(process_type='standardization',
                                           method='z_score',
                                           enabled=self._scaler_enabled)
    self._standardizer.fit(X, **kwargs)

    self.is_fitted = True
    return self
```

#### 3.4.5 `MixedFactorPipeline.transform`

```python
def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
    super().transform(X, **kwargs)

    X = self._imputer.transform(X, **kwargs)
    if self._winsorizer_enabled:
        X = self._apply_winsorize(X)
    X = self._neutralizer.transform(X, **kwargs)
    X = self._transformer.transform(X, **kwargs)
    X = self._standardizer.transform(X, **kwargs)
    return X
```

#### 3.4.6 删除 `_diagnose_transform_need`

删除 L1172-L1176 的方法. 同步删除类 docstring 中"条件性做非线性变换"的表述,
改为"固定 rank 变换".

#### 3.4.7 `_create_pipeline`

```python
if pipe_type == 'static':
    return StaticFactorPipeline(
        neutralizer_params=neutralizer_params,
        transformation_params={
            'method': self.config.static_transformation_method,
            'target_distribution': self.config.static_target_distribution,
        },
        enable_garch=self.config.static_enable_garch,
        garch_params={...} if self.config.static_enable_garch else None,
        module_enabled=module_enabled,
    )
...
elif pipe_type == 'mixed':
    return MixedFactorPipeline(
        mixed_winsor_sigma=self.config.mixed_winsor_sigma,
        transformation_params={
            'method': self.config.mixed_transformation_method,
            'target_distribution': self.config.mixed_target_distribution,
        },
        neutralizer_params=neutralizer_params,
        module_enabled=module_enabled,
    )
```

### 3.5 `demo_v2.py`

删除 L182 与 L220 的 `mixed_conditional_transform=True`.

---

## §4 TDD 测试

### 4.1 Red: 新增 `tests/unit/test_transform_rank_cross_sectional.py`

```python
"""PL-02: 变换逐日截面 rank 的因果性与边界."""
import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm, rankdata

from factor_pipeline.adapters import (
    ProcessingAdapter,
    _TRANSFORMATION_ALIASES as ADAPTER_ALIASES,
    _TRANSFORMATION_METHODS as ADAPTER_METHODS,
)
from factor_pipeline.modules.factor_adaptive_winsor.core.transformers import (
    AdaptiveTransformer, rank_transform_1d,
    TRANSFORMATION_ALIASES, TRANSFORMATION_METHODS,
)


def _panel(n_periods=30, n_stocks=12, seed=0):
    """N=12 >= _MIN_RANK_CROSS_SECTION_OBS, 避免小样本回落干扰对拍."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.standard_t(3, size=(n_periods, n_stocks)),
        index=pd.date_range('2020-01-01', periods=n_periods, freq='D'),
        columns=[f's{i:02d}' for i in range(n_stocks)],
    )
```

**面板尺寸约束**: 手工对拍与截断不变式必须用 `n_stocks >= 10`, 否则会触发
N<10 的截面 z-score 回落, 与 rank 期望值不符.

| # | 测试函数 | 断言 |
|---|---------|------|
| 1 | `test_auto_resolves_to_rank` | `adapter.method == 'rank'`; `requested_method == 'auto'` |
| 2 | `test_alias_consistency` | `ADAPTER_ALIASES == TRANSFORMATION_ALIASES`; `ADAPTER_METHODS == TRANSFORMATION_METHODS` |
| 3 | `test_alias_mapping` | `none→identity`, `box_cox→boxcox`, `yeo_johnson→yeojohnson`, `quantile→rank` |
| 4 | `test_unknown_method_raises` | `ValueError` (构造期) |
| 5 | `test_normal_matches_manual` | 30×12 面板, 逐日 == `norm.ppf((rankdata(row)-0.375)/(n+0.25))`, `atol=1e-12` |
| 6 | `test_uniform_matches_manual` | 30×12 面板, 逐日 == `(2R-n-1)/n`, `atol=1e-12` |
| 7 | `test_truncation_invariance` | 全样本 vs 前 60%: `np.array_equal` (含 NaN) |
| 8 | `test_nan_preserved` | NaN 位置一致; 有效值个数一致 |
| 9 | `test_small_n_fallback` | 单个截面 9 个有效值 → 截面 z-score; 10 个 → rank; 1 个 → 原样 |
| 10 | `test_ties_average` | 含重复值, 输出与手工 `rankdata(method='average')` 一致 |
| 11 | `test_non_dataframe_raises` | `TypeError` (fit 与 transform) |
| 12 | `test_duplicate_axis_raises` | `ValueError` |
| 13 | `test_empty_returns_copy` | `X.empty` → 返回等值新对象 |
| 14 | `test_invalid_target_raises` | `target_distribution='foo'` → `ValueError` |
| 15 | `test_prior_param_required` | `boxcox`/`yeojohnson` 无 `lam`; `power` 无 `power_param` → `ValueError` |
| 16 | `test_transform_is_stateless` | 连续两次 transform 输出相同; 实例无新增数值属性 |
| 17 | `test_adapter_equals_1d` | adapter 输出 == 逐行 `rank_transform_1d` (`max diff == 0`) |
| 18 | `test_identity_short_circuit` | `method='identity'`: `_processor is None`; `assert_frame_equal(out, X)` |
| 19 | `test_identity_keeps_processor_class` | identity 下 `_processor_class is not None` (导入契约保留), 但 `_processor is None` |
| 20 | `test_yj_lambda_one_equals_identity` | `yeojohnson(lam=1.0)` 输出 == 输入 (`atol=1e-12`) |
| 21 | `test_yj_lambda_two_neg_branch` | 负值区 `lam=2` == `-log(1-x)` |
| 22 | `test_log_negative_raises` | `offset=0` + 负值 → `ValueError` |
| 23 | `test_adaptive_transformer_rejects_dataframe_for_rank` | `AdaptiveTransformer(method='rank').transform(df)` → `TypeError` |
| 24 | `test_get_stats` | rank adapter: `transform_scope='cross_sectional'`, `target_distribution` |

### 4.2 Green: 代码实现

按 §3 顺序落地. 每完成 3.1 / 3.2 后跑:

```powershell
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/unit/test_transform_rank_cross_sectional.py -q
```

### 4.3 集成测试: 摘除 PL-02 / PL-04 xfail

`tests/integration/test_pipeline_truncation_invariance.py`:

1. 删除 `test_transform_auto_is_causal` 上的 `@pytest.mark.xfail` (L258-L263).
   测试体保留 (断言 `method='auto'` 的 adapter 截断不变).
2. 删除 `test_static_pipeline_is_truncation_invariant` 上的 `@pytest.mark.xfail` (L306-L310).
3. 更新模块 docstring 的缺陷登记表:
   - 移除 `DEFECT-PL-02` 与 `DEFECT-PL-04` 行;
   - 在"已修复"追加 PL-02 条目 (实测: PL-02 8.51e-04 → 0; PL-04 4.72e-05 → 0);
   - `DEFECT-PL-06` 的 reason 去掉 `+ PL-02(变换)`, 改为仅全样本缩尾;
   - `DEFECT-PL-06` 的测试 docstring 去掉"使 |skew|>2 触发条件变换".
4. 预期结果: **9 passed / 3 xfailed**.

### 4.4 重写 `tests/unit/test_adaptive_transformer_identity.py`

新文件内容围绕 rank 与先验方法:

| # | 测试 | 断言 |
|---|------|------|
| 1 | `rank_uniform_moments` | `mean≈0`, `std≈1/√3` (容差 1e-6) |
| 2 | `rank_normal_moments` | `std≈1`; `skew≈0` |
| 3 | `rank_nan` | NaN 保持 |
| 4 | `identity_noop` | `method='identity'` 返回输入 |
| 5 | `prior_params` | `boxcox(lam=0)` == `log(x)` (x>0, `atol=1e-12`) |
| 6 | `method_resolution` | `auto→rank`, `none→identity` |

### 4.5 配置相关测试的改写 (4 个文件)

**`tests/test_fix2_config_unification.py`**

- `test_09` (L202-216) 重写:

```python
def test_09(self):
    """mixed.transformation.method/target → mixed_transformation_*"""
    unified = PipelineV2ConfigUnified(
        mixed=dict(transformation=dict(
            method='identity', target_distribution='uniform',
        )),
        static=dict(transformation=dict(
            method='rank', target_distribution='normal',
        )),
    )
    dc = unified.to_pipeline_v2_config()
    self.assertEqual(dc.mixed_transformation_method, 'identity')
    self.assertEqual(dc.mixed_target_distribution, 'uniform')
    self.assertEqual(dc.static_transformation_method, 'rank')
    self.assertEqual(dc.static_target_distribution, 'normal')
```

- `test_11` (L253-282): 删除 `conditional_transform=True` 与 `transformation=TransCfg(skew_threshold=..., kurt_threshold=...)`,
  改为 `transformation=dict(method='yeo_johnson', target_distribution='normal')` 并在断言段替换为:

```python
self.assertEqual(dc.mixed_transformation_method, 'yeo_johnson')
self.assertEqual(dc.mixed_target_distribution, 'normal')
```

**`tests/test_pipelines_v2.py`**

`test_mixed_pipeline_processing` (L270-275) 删除三个参数:

```python
pipeline = MixedFactorPipeline(
    neutralizer_params={'industry_data': self.industry},
)
```

**`tests/test_p3_phase2_config_migration.py`**

`test_03` (L64-74):

```python
config = PipelineV2Config(
    dynamic_decorrelation_strength=0.7,
    mixed_transformation_method='identity',
)
...
self.assertEqual(config.mixed_transformation_method, 'identity')
```

**`tests/test_backtest/verify_fix2_manual.py`**

L49-51 / L77-79 / L128-130 的三字段改为 `transformation.method` /
`target_distribution`, 并对应断言 `dc.mixed_transformation_method` /
`dc.mixed_target_distribution`.

### 4.6 回归靶向

```
tests/unit/test_transform_rank_cross_sectional.py
tests/unit/test_adaptive_transformer_identity.py
tests/unit/test_outlier_cross_sectional.py
tests/test_adapters/test_module_enabled.py
tests/unit/test_adapters_mock.py
tests/test_pipelines_v2.py
tests/test_p1_fixes.py
tests/test_p0_fixes.py
tests/test_fix2_config_unification.py
tests/test_p3_phase2_config_migration.py
tests/unit/test_config_v2.py
tests/integration/test_pipeline_truncation_invariance.py
tests/test_fix3_version_unification.py
```

`tests/test_p1_fixes.py` 与 `tests/test_p0_fixes.py` 不做代码改动, 只作为回归 (它们用关键字构造管线, 断言 `assertIn` 而非集合相等).

### 4.7 性能验证 (手工, 不入 CI)

```powershell
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -c "import numpy as np, pandas as pd, time; from scipy.stats import norm, rankdata; ..."
```

按设计 §6.1 口径 (T=2500, N=3000, NaN 5%, `t(3)`) 复跑, 记录:
- `rankdata` 逐行耗时 (设计基线 1.071 s)
- `normal` 输出 std (设计基线 0.9989543)
- `uniform` 输出 std (设计基线 0.5773950)

偏差 > 20% 需记录原因.

---

## §5 版本、缓存与文档

### 5.1 版本 → v3.3.4 (5 处)

| 文件 | 位置 | 旧值 → 新值 |
|------|------|------------|
| `pyproject.toml` | `[project] version` | `3.3.3` → `3.3.4` |
| `factor_pipeline/__init__.py` | `__version__` | `3.3.3` → `3.3.4` |
| `config_v2.py` | `PipelineV2ConfigUnified.version` | `3.3.3` → `3.3.4` |
| `reporting.py` | `PipelineExecutionReport.pipeline_version` | `3.3.3` → `3.3.4` |
| `tests/test_fix3_version_unification.py` | `EXPECTED_VERSION` | `3.3.3` → `3.3.4` |

### 5.2 缓存代际 → `v2.2.2-cache`

| 文件 | 变更 |
|------|------|
| `backtest/cache_manager.py` | `CODE_VERSION = "v2.2.1-cache"` → `"v2.2.2-cache"` |
| `tests/test_fix3_version_unification.py` | `test_05` 与 `test_07` 的字面量 `"v2.2.1-cache"` → `"v2.2.2-cache"` (3 处) |

子缓存 (`cached_data_loader` / `factor_cache` / `fwd_returns_cache` / `price_cache`)
默认值已引用 `CODE_VERSION`, 不需改. 一致性由 `test_07` 覆盖.

**语义**: 变换输出数值改变 → 旧因子缓存必须失效, 读取时 `meta.code_version` 不一致
即 MISS + 自愈删除 (PL-01 已实现的机制, 本次只 bump 常量).

### 5.3 ADR-038

```markdown
## ADR-038: 变换统一为逐日截面 rank→正态 (DEFECT-PL-02, v3.3.4)

### 背景
`ProcessingAdapter(process_type='transformation')` 的 fit 用 `X.values.flatten()`
在全 panel 上估计 λ / offset / 经验 CDF; `auto_optimize=True` 覆盖显式方法;
`_select_optimal_transform` 依赖全样本 skew/kurt/Shapiro p, 且 Shapiro 子采样
未设随机种子. 前 t 期输出依赖 t 之后的数据.

### 决策
1. 变换固定为 `rank` (逐日截面 → Blom 正态分数 `Φ⁻¹((R−3/8)/(N+1/4))`);
   输出分布由 `target_distribution` 控制 (`normal` / `uniform`).
2. `auto` 解析为 `rank`; 删除 `auto_optimize` 与自动选型链.
3. `log` / `boxcox` / `yeojohnson` / `power` 保留, 但改为**先验参数模式**
   (`lam` / `power_param` 必填, `offset` 默认 0.0), 禁止 fit 估计.
4. `quantile` 作为 `rank` 的配置别名; 实现层删除.
5. `TransformationConfig` 接线到 Static/Mixed v2 管线; 删除
   `mixed_conditional_transform` / `mixed_skew_threshold` / `mixed_kurt_threshold`.
6. Mixed 顺序切为 neutralize → transform (I-INT).

### 备选 (拒绝)
- 固定方法 + 全样本参数: 参数仍前视.
- 扩展窗口 λ 调度: regime 不显著 (调研 §3.2), 收益低于复杂度.
- 逐日截面 λ: 日间波动大, 只增噪声.
- 在线条件变换 (按 skew/kurt 决定是否变换): 无学术/社区实践支持;
  输出为 mixture; pre-test 估计量分布不可一致估计 (Leeb & Pötscher 2006/2008).

### 后果
- Static / Mixed 变换输出全部改变; 历史 IC/Sharpe 需重算.
- rank 丢失量纲; 需要原始单位的因子用 `method='identity'`.
- ties 保留为相同输出值 (ret_1d 实测 12.27%); 排序不受影响.
- 缓存代际 `v2.2.1-cache` → `v2.2.2-cache`.

### 测试契约
T1 (显式方法生效) / T2 (auto 构造期固定) / T3 (截断不变式) /
T5 (可复现性) / T6 (名称映射) / T7 (Mixed fit/transform 口径) / T8 (端到端).

### 不覆盖
PL-05 / PL-06 / PL-07; 死 rank 实现 (`EnhancedRankPreservingScaler`,
`StandardizationConfig.method='rank'`); 旧 transform 逐列路径.

### 回滚
恢复 `AdaptiveTransformer` 选型链与 `ProcessingAdapter` else 分支; 恢复 Mixed
顺序; 配置字段回滚; 缓存再 bump.
```

### 5.4 CHANGELOG v3.3.4

按现有格式 (概览 / 缺陷根因 / 实测矩阵 / 核心产出) 写入; 实测矩阵沿用
`T=100, N=30, t=60, atol=1e-12` 口径:

| 层级 | 对象 | 修复前 | 修复后 |
|------|------|--------|--------|
| step | transform auto | 1800 格, 8.51e-04 | **0 格, 0** (待实测) |
| pipeline | Static | 1800 格, 4.72e-05 | **0 格, 0** (待实测) |
| pipeline | Mixed | 1800 格, 2.91e-01 | **剩余仅 PL-06** (待实测) |

"待实测"必须在实施后填入真实值, 不得预填.

---

## §6 执行顺序 (含检查点)

| 步 | 动作 | 检查点 |
|----|------|--------|
| 0 | 跑 §1.2 基线, 记录实际值 | 基线写入本文档 §7 |
| 1 | 新增 `test_transform_rank_cross_sectional.py` | **Red**: 全部失败 (除导入类) |
| 2 | 改 `transformers.py` (§3.1) | 测试 1-6, 14-23 转绿 |
| 3 | 改 `adapters.py` (§3.2) | 测试 7-13, 17-19, 24 转绿 |
| 4 | 改 `config_v2.py` (§3.3) | `test_09` 转绿 |
| 5 | 改 `pipelines_v2.py` + `demo_v2.py` (§3.4-3.5) + 4 个配置测试 (§4.5) | `test_pipelines_v2.py` / `test_fix2_config_unification.py` / `test_p3_phase2_config_migration.py` 全绿 |
| 6 | 摘 PL-02/PL-04 xfail | 集成套件 9 passed / 3 xfailed |
| 7 | 重写 `test_adaptive_transformer_identity.py` | 全绿 |
| 8 | 版本 5 处 + 缓存 bump | `test_fix3_version_unification.py` 全绿 |
| 9 | 跑 §4.6 回归 + §4.7 性能 | 记录实测 |
| 10 | ADR-038 / CHANGELOG / §7 验收记录 | 文档一致 |

---

## §7 验收记录 (实施后填写)

| 项 | 预期 | 实测 | 状态 |
|----|------|------|------|
| 集成套件 | 9 passed / 3 xfailed | | |
| PL-02 隔离 `max_abs_diff` | 0 | | |
| PL-04 Static `max_abs_diff` | 0 | | |
| PL-06 Mixed `max_abs_diff` | 仍 > 0 (缩尾) | | |
| 新单测 | 24 passed | | |
| 适配器回归 | 38 passed / 2 skipped | | |
| 版本测试 | 全绿 | | |
| rank 性能 (T2500×N3000) | ≈1.07 s | | |
| `normal` std | 0.9989543 | | |
| `uniform` std | 0.5773950 | | |

---

## §8 风险、回滚与后续

### 8.1 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| Static/Mixed 输出变化 | 历史 IC/Sharpe 不可比 | ADR-038 + CHANGELOG; 重跑 |
| 配置字段删除 | 旧 YAML/JSON 反序列化失败 | `MixedPipelineConfig.conditional_transform` 删除属破坏性变更; 迁移说明写入 CHANGELOG |
| `auto_optimize` 传参 | `AdaptiveTransformer(auto_optimize=True)` → `TypeError` | 只出现在 `config.py L121`; 同步删除该键 |
| rank 丢量纲 | 需要原始单位的因子不可用 | `method='identity'` opt-out |
| ties 12.27% | 大量相等值 | `average` 保序; 文档声明 |

### 8.2 回滚

1. `git revert` 本提交 (代码 + 配置 + 测试为一个原子提交).
2. 缓存代际再 bump (`v2.2.3-cache`) 以触发重建.
3. 恢复 `tests/integration/test_pipeline_truncation_invariance.py` 的 PL-02/PL-04 xfail.

### 8.3 后续任务

1. PL-06: Mixed `_compute_winsorize_params` 逐日截面化.
2. PL-05: Dynamic AR `fitted_values` 因果化.
3. PL-07: 指纹路由因果化.
4. 死 rank 代码清理 (`EnhancedRankPreservingScaler`, `StandardizationConfig.method='rank'`).
5. 旧 transform 逐列路径的统一修复 (调研 §3.7.1 潜伏缺陷).

---

## §9 交付物

| 类型 | 文件 |
|------|------|
| 代码 | `transformers.py` / `adapters.py` / `config_v2.py` / `pipelines_v2.py` / `demo_v2.py` / `cache_manager.py` |
| 测试 | 新增 1 / 重写 1 / 修改 3 |
| 文档 | ADR-038 / CHANGELOG v3.3.4 / 本文件 / 设计 v1.0 / 调研 v1.10 |
| 版本 | 5 处声明 + 缓存 `v2.2.2-cache` |

---

## 附录 A: 常用命令

```powershell
cd F:\Coding
$PY = "C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe"

# 全量靶向
& $PY -m pytest `
  factor_pipeline/tests/unit/test_transform_rank_cross_sectional.py `
  factor_pipeline/tests/unit/test_adaptive_transformer_identity.py `
  factor_pipeline/tests/unit/test_outlier_cross_sectional.py `
  factor_pipeline/tests/test_adapters/test_module_enabled.py `
  factor_pipeline/tests/unit/test_adapters_mock.py `
  factor_pipeline/tests/test_pipelines_v2.py `
  factor_pipeline/tests/test_fix2_config_unification.py `
  factor_pipeline/tests/unit/test_config_v2.py `
  factor_pipeline/tests/integration/test_pipeline_truncation_invariance.py `
  factor_pipeline/tests/test_fix3_version_unification.py -q

# 仅集成
& $PY -m pytest factor_pipeline/tests/integration/test_pipeline_truncation_invariance.py -q
```

---

## 附录 B: 实施自检

| # | 检查项 | 结论 |
|---|--------|------|
| 1 | 是否按 TDD 顺序 (Red → Green → 回归)? | 是 (§6) |
| 2 | 是否所有新增数字都有来源? | 是; §5.4 的"待实测"已显式标注 |
| 3 | 是否覆盖 `fit` 与 `transform` 两个分支? | 是 (§3.2.3 / §3.2.4) |
| 4 | `identity` 是否短路? | 是 (§3.2.4) |
| 5 | 是否明确 `auto_optimize` 的处置? | 是 (§3.1.2 / §8.1) |
| 6 | 是否明确配置字段的删除与新增? | 是 (§3.3 / §3.4.1) |
| 7 | 是否处理缓存代际? | 是 (§5.2) |
| 8 | 是否处理版本 5 处同步? | 是 (§5.1) |
| 9 | 是否保留 PL-06 xfail? | 是 (§4.3) |
| 10 | 性能基线是否有实测来源? | 是 (设计 §6.1) |
| 11 | 是否覆盖所有引用待删字段的测试? | 是 (§4.5, 4 个文件; §4.6 回归含 `test_p0/p1_fixes`) |
| 12 | 是否有位置参数调用会被签名变更破坏? | 否 (grep 确认全部为关键字调用) |
| 13 | `rank_transform_1d` 是否处理全 NaN / N<2? | 是 (`n<2` 返回全 NaN; adapter 在 N<2 时原样返回) |
