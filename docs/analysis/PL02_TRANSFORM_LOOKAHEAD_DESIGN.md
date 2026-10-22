# PL-02 变换步骤前视缺陷 — 设计文档

**版本**: v1.1 (v1.0 + 实施状态 + §5.3.2 uniform 尺度契约限定)
**日期**: 2026-10-22
**缺陷编号**: DEFECT-PL-02
**上游调研**: [PL02_TRANSFORM_LOOKAHEAD_RESEARCH.md](PL02_TRANSFORM_LOOKAHEAD_RESEARCH.md) v1.10
**关联决策**: ADR-027 (固定方法) / ADR-029 (逐日截面 Z-Score) / ADR-037 (逐日截面去极值) / ADR-038 (本文决策)
**目标版本**: v3.3.4
**实施状态**: 已实施 (v3.3.4, 2026-10-22); 验收记录见 [EXECUTION_V3.3.4_PL02_TRANSFORM_CAUSALITY.md](../EXECUTION_V3.3.4_PL02_TRANSFORM_CAUSALITY.md) §7

---

## §0 决策摘要

| # | 决策 | 依据 |
|---|------|------|
| D1 | 变换统一为**逐日截面 rank→正态** (Blom), 输出分布由 `target_distribution` 控制 | 调研 §3.6 / §3.7.3 |
| D2 | `auto` 在构造期解析为 `rank`; **删除** `auto_optimize` 与自动选型链 (`_select_optimal_transform` / `_analyze_features`) | 调研 §3.6.4 T1/T2/T5 |
| D3 | `log` / `yeojohnson` / `boxcox` / `power` **保留但改为先验参数模式**: `lam` / `power_param` 必须显式传入, `offset` 默认 0.0; 禁止 `fit` 估计 | 调研 §4.1; 用户决策 |
| D4 | `quantile` **在配置层作为 `rank` 的别名**, 实现层删除 `_fit_quantile` / `_apply_quantile` | 调研 §3.7.2; 两者同为 PIT, quantile 无法先验化 |
| D5 | Mixed 删除 `conditional_transform` / `skew_threshold` / `kurt_threshold`, 改由 `transformation.method` 统一控制 | 调研 §3.8; 用户决策 D |
| D6 | `TransformationConfig` **接线到 v2 管线** (`StaticFactorPipeline` / `MixedFactorPipeline`) | 调研 §6.2; 用户决策 |
| D7 | 配置名映射: `none→identity` / `box_cox→boxcox` / `yeo_johnson→yeojohnson` / `quantile→rank`; `requested_method` 保留原值 | T6 |
| D8 | rank 无状态: `fit` 只做类型检查, `transform` 逐日截面; **N<10** 回落截面 z-score; 截断不变性结构成立 | 调研 §3.7.4; §5.3.3 |
| D9 | Mixed 步骤顺序切换为 **imputer → winsorize → neutralize → rank → z-score**, 不留旧路径开关 | 调研 §3.6.1 |

**行为变更**: Static / Mixed 的所有变换输出改变; 缓存代际 bump; 历史 IC/Sharpe 需重算.

---

## §1 目标与非目标

### 1.1 目标

1. **因果性**: 变换输出只依赖当日截面, 满足截断不变式 `F([0,t])[t] ≡ F(全样本)[t]`.
2. **消除方法选择的不可复现性**: 删除 Shapiro 子采样与全样本 skew/kurt 驱动的选型.
3. **显式方法生效**: 显式 `method` 不再被 `auto_optimize` 覆盖.
4. **配置真实生效**: `TransformationConfig` 接入 v2 管线, 配置与行为一致.
5. **关闭 PL-04**: Static 端到端残留 (4.720212e-05) 随 PL-02 关闭.
6. **配置面收敛**: Static 与 Mixed 共用一套 `transformation.method`.

### 1.2 非目标

| 项 | 归属 | 说明 |
|----|------|------|
| Mixed 全样本缩尾 `_compute_winsorize_params` | PL-06 | 独立缺陷; 改顺序后仍在 neutralize 之前 |
| Dynamic AR 样本内 `fitted_values` | PL-05 | 独立缺陷 |
| 顶层指纹路由依赖全样本 | PL-07 | 独立缺陷 |
| `EnhancedRankPreservingScaler` 的两处 rank | 登记, 不清理 | 调研 §3.7.2; 死代码 |
| `StandardizationConfig.method='rank'` | 登记, 不清理 | 死配置, 实例化即抛 `ValueError` |
| 旧 `transform` 路径的逐列维度 | 登记, 不修 | 调研 §3.7.1; 对逐元素方法无影响 |
| 因子级 `identity` 配置 | 不做 | 维持管线级 `method='identity'` |
| 类名 `AdaptiveTransformer` | 不改 | 避免大面积重命名 |

---

## §2 现状与约束

### 2.1 当前代码路径

| 位置 | 现状 |
|------|------|
| `ProcessingAdapter.__init__` ([adapters.py L329-L395](../../adapters.py#L329-L395)) | transformation 分支无特殊处理; `enabled` 强制 `True` |
| `ProcessingAdapter.fit` ([L508-L521](../../adapters.py#L508-L521)) | `X.values.flatten()` 全 panel 池化拟合 |
| `ProcessingAdapter.transform` ([L563-L575](../../adapters.py#L563-L575)) | `for col in X.columns` 逐列 (按股票时序) 应用 |
| `AdaptiveTransformer.__init__` ([transformers.py L501](../../modules/factor_adaptive_winsor/core/transformers.py#L501)) | `method='auto'`, `auto_optimize=True`, `target_distribution='normal'` |
| `AdaptiveTransformer.fit` ([L530-L533](../../modules/factor_adaptive_winsor/core/transformers.py#L530-L533)) | `if self.method == 'auto' or self.auto_optimize:` → 全样本选型 |
| `_analyze_features` ([L589-L621](../../modules/factor_adaptive_winsor/core/transformers.py#L589-L621)) | 全样本 skew/kurt/Shapiro; 子采样未设种子 |
| `_select_optimal_transform` ([L623-L635](../../modules/factor_adaptive_winsor/core/transformers.py#L623-L635)) | 依赖 `is_normal` / `is_heavy_tailed` |
| `StaticFactorPipeline.steps` ([pipelines_v2.py L887-L906](../../pipelines_v2.py#L887-L906)) | `method='auto'` |
| `MixedFactorPipeline.fit/transform` ([L1099-L1148](../../pipelines_v2.py#L1099-L1148)) | 条件变换在 neutralize 之前; fit 用未缩尾 X |
| `PipelineV2Config` ([L680-L709](../../pipelines_v2.py#L680-L709)) | `mixed_conditional_transform` / `mixed_skew_threshold` / `mixed_kurt_threshold` |
| `TransformationConfig` ([config_v2.py L66-L78](../../config_v2.py#L66-L78)) | `method` + `skew_threshold` + `kurt_threshold`; 仅 legacy 读取 |

### 2.2 数据契约 (项目约定)

- `X: pd.DataFrame`, **index = 日期, columns = 股票**.
- 截面操作 = `axis=1` (行); 时序操作 = `axis=0` (列).
- 输出必须保留 `index` / `columns` / NaN 模式 (NaN 不参与 rank, 输出仍为 NaN).
- 单位数 N 取**当日有效样本数** `X.notna().sum(axis=1)`.

### 2.3 兼容约束

| 约束 | 处置 |
|------|------|
| `config.py L121` 传 `method='auto', auto_optimize=True` | `auto` 解析为 `rank`; `auto_optimize` 键进入 `BaseTransformer.params`, 不报错 (不再是显式签名参数) |
| `PipelineV2ConfigUnified.to_pipeline_config()` 把 `static.transformation` 给 legacy | 字段收敛后仍可 `model_dump()`, legacy 侧未知键进 `params` |
| `PipelineV2Config` 的 `mixed_conditional_transform` 等 3 字段 | 删除; `to_pipeline_v2_config()` 同步改映射 |
| `test_fix2_config_unification.py` 的 test_09 | 重写: 断言 `mixed.transformation.method` 映射 |
| `test_adaptive_transformer_identity.py` | 整个文件重写为 rank 行为测试 |
| `demo_v2.py` L182/L220 传 `mixed_conditional_transform=True` | 删参数 |
| 缓存 | `CODE_VERSION` `v2.2.1-cache` → `v2.2.2-cache` |

---

## §3 设计决策

### D1: 逐日截面 rank→正态

| 方案 | 因果 | 横截面可比 | 信息损失 | 结论 |
|------|------|-----------|----------|------|
| 逐日截面 rank→正态 | 是 | 是 | 中 (Pearson 0.30–0.83) | **采用** |
| 逐日截面 rank→均匀 | 是 | 是 | 中 | 保留为 `target_distribution='uniform'` |
| 逐列 expanding 参数 | 是 | 否 | — | 不采用 |
| 全样本池化 (现状) | 否 | — | — | 拒绝 |

依据: 调研 §3.4 (矩精确归一: `skew=0`, `κ_ex=−1.2`, `std→1/√3`) / §3.6 (Blom 事实标准) / §3.8 (ORQ 对任意分布有效).

### D2: `auto` → `rank`, 删除选型链

- `__init__` 解析: `method='auto'` → `'rank'`; `self.method` 存解析值, `self.requested_method` 存原值.
- 删除 `auto_optimize` 参数; 删除 `_analyze_features` / `_select_optimal_transform`.
- 备选"保留 `auto_optimize` 但默认 False"被拒绝: 参数保留却无效果, 属于 shim; 且 T5 (可复现性) 仍会被 `_analyze_features` 的未设种子子采样破坏.

**影响面**: `config.py L121` 的 `auto_optimize=True` 变为无效键 (进入 `self.params`). 不报错, 但需在 CHANGELOG 说明.

### D3: 显式方法改为先验参数模式

| `method` | 必填先验参数 | 缺失时行为 |
|----------|-------------|-----------|
| `identity` | 无 | — |
| `rank` | 无 | — |
| `log` | `offset: float = 0.0` | 默认 0.0 (假设正值); `transform` 时若 `X + offset <= 0` 抛 `ValueError` |
| `boxcox` | `lam: float` | `ValueError` (构造期) |
| `yeojohnson` | `lam: float` | `ValueError` (构造期) |
| `power` | `power_param: float` | `ValueError` (构造期) |

- 参数校验在 `__init__` 完成, 不等到 `fit`.
- `fit` 对这些方法只校验先验参数存在性, 不估计任何参数 (`fitted_params` 只存 `method` 与先验值).
- 备选"逐日截面拟合 λ" 被拒绝: 调研 §3.2 表明 regime 不显著, 逐日 λ 只增加噪声; 且 §1.2 实测逐日 λ 波动大.
- 备选"扩展窗口拟合" 被拒绝: 同上; 且引入窗口状态.

### D4: `quantile` 在配置层作为 `rank` 别名

| 层 | 处置 |
|----|------|
| 配置层 `TransformationConfig.method` | 保留 `'quantile'` 字面量, 解析为 `'rank'` |
| `ProcessingAdapter` | `method='quantile'` → `'rank'` |
| `AdaptiveTransformer` | 删除 `_fit_quantile` / `_apply_quantile` |
| 日志 | `requested_method='quantile'` 可用于审计 |

理由: `quantile` 与 `rank` 同为经验 CDF 映射; `quantile` 依赖全样本分位网格 (`n_quantiles ≤ 1000`) 且无法先验化; rank 在所有维度更优 (无状态、无网格截断、tie 精确). 保留别名避免旧配置崩溃, 但不再提供独立行为.

### D5: Mixed 用 `transformation.method` 控制

- 删除 `MixedFactorPipeline.__init__` 的 `conditional_transform` / `skew_threshold` / `kurt_threshold`.
- 新增 `transformation_params` 入参, 含 `method` 与 `target_distribution`.
- 删除 `_diagnose_transform_need`.
- `False` 语义由 `method='identity'` 承担.
- 备选"保留 `conditional_transform`, True=rank/False=identity" 被拒绝: 参数名与语义不符, 且与 Static 形成两套配置.

### D6: `TransformationConfig` 接线

- `StaticFactorPipeline.__init__` 新增 `transformation_params: Optional[Dict] = None`.
- `MixedFactorPipeline.__init__` 新增 `transformation_params: Optional[Dict] = None`.
- `FactorProcessingPipelineV2._create_pipeline` 传入 `self.config.static_transformation_*` / `mixed_transformation_*`.
- 字段收敛: `TransformationConfig` 只保留 `method` 与 `target_distribution`; 删除 `skew_threshold` / `kurt_threshold`.

### D7: 名称映射

| 配置层 | 实现层 |
|--------|--------|
| `auto` | `rank` |
| `none` | `identity` |
| `rank` | `rank` |
| `identity` | `identity` |
| `log` | `log` |
| `box_cox` | `boxcox` |
| `yeo_johnson` | `yeojohnson` |
| `power` | `power` |
| `quantile` | `rank` |

映射在 `ProcessingAdapter.__init__` 与 `AdaptiveTransformer.__init__` **两处**执行 (直接调用方也受保护). 未知方法在构造期抛 `ValueError`.

### D8: rank 无状态

`fit` 只校验输入类型并置 `is_fitted=True`; 不存任何统计量. `transform` 逐日截面计算.

### D9: Mixed 顺序

```
fit:       imputer → winsorize → neutralize → rank(fit=no-op) → z-score(fit)
transform: imputer → winsorize → neutralize → rank           → z-score
```

同时修正现有 fit/transform 口径不一致 (当前 fit 用未缩尾 X 拟合 transformer, transform 用已缩尾 X).

---

## §4 接口设计

### 4.1 `AdaptiveTransformer`

```python
class AdaptiveTransformer(BaseTransformer):
    def __init__(
        self,
        method: str = 'rank',
        target_distribution: Literal['uniform', 'normal'] = 'normal',
        lam: Optional[float] = None,
        offset: float = 0.0,
        power_param: Optional[float] = None,
    ):
```

| 属性 | 类型 | 含义 |
|------|------|------|
| `method` | `str` | 解析后方法 |
| `requested_method` | `str` | 调用方原值 |
| `target_distribution` | `str` | `normal` / `uniform` |
| `lam` | `Optional[float]` | boxcox / yeojohnson 先验 |
| `offset` | `float` | log 先验, 默认 0.0 |
| `power_param` | `Optional[float]` | power 先验 |

**删除**: `auto_optimize`, `_analyze_features`, `_select_optimal_transform`, `_fit_yeojohnson`, `_fit_boxcox`, `_fit_quantile`, `_fit_power`, `_fit_log`.

**保留**: `_apply_yeojohnson`, `_apply_boxcox`, `_apply_power`, `_apply_log` (改为读取先验参数).

### 4.2 `ProcessingAdapter`

```python
ProcessingAdapter(
    process_type: str = 'outlier',
    method: str = 'auto',
    enabled: Optional[bool] = None,
    module_path=None, import_path=None, class_name=None,
    **params,
)
```

| 新增属性 | 类型 | 含义 |
|----------|------|------|
| `_cross_sectional_rank` | `bool` | `process_type == 'transformation'` 且解析后 `method == 'rank'` |
| `_identity_transformation` | `bool` | `process_type == 'transformation'` 且解析后 `method == 'identity'` |
| `target_distribution` | `str` | 从 `params` 提取, 默认 `'normal'` |

| 新增方法 | 签名 |
|----------|------|
| `_transform_rank_cross_sectional` | `(self, X: pd.DataFrame) -> pd.DataFrame` |

**不变**: `_cross_sectional_outlier` / `_cross_sectional_zscore` 分支与其优先级.

**模块级常量**:

```python
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
```

### 4.3 `TransformationConfig`

```python
class TransformationConfig(BaseModel):
    method: Literal[
        'auto', 'rank', 'identity', 'none', 'log',
        'box_cox', 'yeo_johnson', 'power', 'quantile',
    ] = Field(default='rank', description="变换方法")
    target_distribution: Literal['uniform', 'normal'] = \
        Field(default='normal', description="PIT 目标分布")
```

**删除**: `skew_threshold`, `kurt_threshold`.

### 4.4 管线配置

```python
@dataclass
class PipelineV2Config:
    ...
    static_transformation_method: str = 'rank'
    static_target_distribution: str = 'normal'
    mixed_transformation_method: str = 'rank'
    mixed_target_distribution: str = 'normal'
    ...
```

**删除**: `mixed_conditional_transform`, `mixed_skew_threshold`, `mixed_kurt_threshold`.

---

## §5 算法与数据流

### 5.1 rank 核心算法

输入 `values: np.ndarray` (1-D) 与 `target: str`.

```python
import numpy as np
from scipy.stats import norm, rankdata

def rank_transform_1d(values, target='normal'):
    out = np.full(values.shape, np.nan)
    ok = ~np.isnan(values)
    n = int(ok.sum())
    if n < 2:
        return out
    ranks = rankdata(values[ok], method='average')
    if target == 'normal':
        u = (ranks - 0.375) / (n + 0.25)      # Blom
        out[ok] = norm.ppf(u)
    else:
        u = (2.0 * ranks - n - 1.0) / n        # 归一化秩
        out[ok] = u
    return out
```

**性质** (数学):
- `mean(u) = 0.5` 精确 (Blom);
- `target='uniform'`: `E[u]=0`, `std→1/√3`, 端点 `±(N−1)/N`;
- `target='normal'`: std ≈ 1, 端点 `Φ⁻¹(0.625/(N+0.25))`;
- NaN 输入 → NaN 输出, 且不参与排名;
- `rankdata(method='average')` 是**唯一**的 ties 规则, 与 `ProcessingAdapter` 共用同一函数.

### 5.2 `ProcessingAdapter` 分支顺序

**`fit`**:

```
1. not enabled                         → is_fitted=True, return
2. _cross_sectional_outlier           → 类型检查 + no-op
3. _cross_sectional_zscore             → 类型检查 + no-op
4. _identity_transformation            → 类型检查 + no-op            [新增]
5. _cross_sectional_rank               → 类型检查 + no-op            [新增]
6. process_type == 'standardization'   → 逐列 processor.fit
7. else                                → X.values.flatten() fit (现状)
```

**`transform`**:

```
1. not enabled                         → return X
2. not is_fitted                       → ValueError
3. _cross_sectional_outlier           → _transform_outlier_cross_sectional
4. _cross_sectional_zscore             → 行均值/行标准差
5. _identity_transformation            → return X                     [新增]
6. _cross_sectional_rank               → _transform_rank_cross_sectional    [新增]
7. process_type == 'standardization'   → 逐列 processor
8. else                                → 逐列 processor (现状)
```

`_identity_transformation` 与 `_cross_sectional_rank` 必须排在 else 之前.
否则 `fit` 会执行 `X.values.flatten()` (T×N 临时数组, T=2500/N=3000 时约 60 MB), `transform` 会逐列调用 processor —— 对 no-op 变换是无谓开销.

### 5.3 identity 与 rank 分支

**identity**:

```python
# __init__
self._identity_transformation = (
    process_type == 'transformation' and method == 'identity'
)
```

`fit`: 仅做 `isinstance(X, pd.DataFrame)` 检查, `is_fitted=True`, 不实例化 processor.
`transform`: 直接 `return X`.

理由: `identity` 是恒等映射, 走 else 分支会触发 flatten fit + 2600 次逐列 `AdaptiveTransformer.transform` 调用.

**rank**: 见 §5.3.1.

#### 5.3.1 `_transform_rank_cross_sectional`

```python
def _transform_rank_cross_sectional(self, X: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(X, pd.DataFrame):
        raise TypeError(...)
    if X.index.has_duplicates or X.columns.has_duplicates:
        raise ValueError(...)
    if X.empty:
        return X.copy()

    arr = X.to_numpy(dtype=float)
    out = np.empty_like(arr)
    n_valid = np.isfinite(arr).sum(axis=1)

    for i in range(arr.shape[0]):
        row = arr[i]
        if n_valid[i] < 2:
            out[i] = row        # N<2 无法排名, 原样返回
            continue
        if n_valid[i] < _MIN_RANK_CROSS_SECTION_OBS:      # 10, 见 §5.3.3
            mu = np.nanmean(row)
            sd = np.nanstd(row, ddof=1)
            out[i] = (row - mu) / sd if np.isfinite(sd) and sd > 0 else row
        else:
            out[i] = rank_transform_1d(row, self.target_distribution)

    return pd.DataFrame(out, index=X.index, columns=X.columns)
```

- **单一算法**: 每个截面都调用 `rank_transform_1d`, 无第二套向量化实现.
- **纯函数**: 不写任何实例状态, `transform` 可并发调用.

#### 5.3.2 N 下限的性质与取值

- **确定性保护**: 回落条件只依赖截面样本量 `N`, 不依赖任何分布统计量. 这不属于 §3.8 否掉的 pre-test 式在线切换 —— `N` 在 t 时刻完全可观测, 且与因子取值无关.
- **管线内等价**: rank 之后仍有逐日截面 z-score, 因此"N<阈值时回落 z-score"与"回落 identity"在完整管线内**最终结果相同** (`z-score(z-score(x)) ≡ z-score(x)`).
- **单独使用的尺度契约 (仅 normal)**: 回落 z-score 的目的是在单独使用 `ProcessingAdapter` 时保持"输出 std≈1"的契约. 该契约**只对 `target_distribution='normal'` 成立**: `uniform` 的 rank 输出 std 趋近 `1/√3`, 与回落的 `std=1` 不同尺度 (实测 ddof=1: N=5 回落 `std=1.0`; N=10 uniform rank `std=0.60553`). 因此 `uniform` 目标在独立使用时, 输出尺度会按当日 N 在 rank / z-score 之间跳变; 生产管线由后续逐日 z-score 统一, 不受影响. 若独立使用 `uniform` 且要求尺度一致, 调用方应对输出再做逐日 z-score.
- **阈值取值**: 见 §5.3.3.
- **零离散度 / 全 NaN**: `sd` 非有限或 `<= 0` 时原样返回该截面; `N<2` 无法排名, 也原样返回 (避免 `nanmean`/`nanstd` 的空切片警告).

#### 5.3.3 阈值取 10

调研 §3.6.5 曾估计 `N=30` (Blom 端点 `Φ⁻¹(0.625/30.25) ≈ −2.04`). 设计定为 **10**, 理由:

| N | Blom 端点 | rank 可用输出数 | 评价 |
|---|-----------|----------------|------|
| 30 | −2.04 | 30 | 保护过强, 早期截面全部切换 |
| 10 | −1.55 | 10 | **采用**; 仍单调有效, 切换面更小 |
| 5 | −1.18 | 5 | 输出取值过少 |

- N=10 时 rank 仍是有效单调映射 (10 个不同输出值), 端点 −1.55 窄于正态但后续 z-score 会统一尺度.
- 阈值越低, 发生"rank / z-score 日间切换"的截面越少.
- `N<2` 在 `rank_transform_1d` 内已由 `if n < 2: return out` 兜底.

常量: `_MIN_RANK_CROSS_SECTION_OBS = 10`.

### 5.4 ties 处理与审计

- ties 由 `rankdata(method='average')` 统一处理: 相同值得到相同平均秩, 因而输出值相同, **排序保序**.
- 不做运行时 ties 日志, 也不在热路径里额外计算 ties 比例 (会增加约 50% 耗时).
- **审计方式**: `rank` 是严格单调映射, 输出中的重复值**一一对应**输入的 ties. 调用方可直接对输出做 `X.nunique(axis=1)` 自查. `ret_1d` 的 12.27% ties 会原样保留为相同输出值, 这是该方法语义的一部分, 不是缺陷 (调研 §3.4.5).
- 若未来需要告警, 应作为独立的离线诊断, 不进入 `transform`.

### 5.5 `__init__` 解析 (两处)

`ProcessingAdapter`:
```python
if process_type == 'transformation':
    method = _TRANSFORMATION_ALIASES.get(method, method)
    if method not in _TRANSFORMATION_METHODS:
        raise ValueError(...)
    self._cross_sectional_rank = (method == 'rank')
    target_distribution = params.get('target_distribution', 'normal')
```

`_TRANSFORMATION_ALIASES = {'auto': 'rank', 'none': 'identity', 'box_cox': 'boxcox', 'yeo_johnson': 'yeojohnson', 'quantile': 'rank'}`

### 5.6 `AdaptiveTransformer.fit` / `transform`

```python
def fit(self, X):
    # 先验参数校验已在 __init__ 完成
    self.fitted_params = {'method': self.method}
    self.is_fitted = True
    return self

def transform(self, X):
    if not self.is_fitted:
        raise ValueError(...)
    if self.method == 'identity':
        return X
    if self.method == 'rank':
        if isinstance(X, pd.DataFrame):
            raise TypeError(
                "AdaptiveTransformer(method='rank') 的截面语义必须经由 "
                "ProcessingAdapter._cross_sectional_rank 使用; "
                "直接传 DataFrame 会被 BaseTransformer._to_array 展平为全局池化"
            )
        arr = self._to_array(X)
        out = rank_transform_1d(arr, self.target_distribution)
        return self._restore_format(out, X) if isinstance(X, pd.Series) else out
    ... # log / boxcox / yeojohnson / power 走 _apply_*
```

**注意**: `BaseTransformer._to_array` 对 DataFrame 执行 `flatten()`, 因此
`AdaptiveTransformer.transform` 的 rank 分支**必须拒绝 DataFrame**; 截面语义只由
`ProcessingAdapter._cross_sectional_rank` 承担 (按行处理). 两者不可混用.

### 5.7 管线顺序

**Static** (不变, 仅方法替换):
```
imputer → outlier(percentile, axis=1) → neutralize → rank(axis=1) → z-score(axis=1)
```

**Mixed** (顺序变更):
```
imputer → winsorize(axis=1, 全样本参数, PL-06) → neutralize → rank(axis=1) → z-score(axis=1)
```

### 5.8 配置解析链

```
PipelineV2ConfigUnified.static.transformation.method
  → to_pipeline_v2_config().static_transformation_method
  → FactorProcessingPipelineV2._create_pipeline('static')
  → StaticFactorPipeline(transformation_params={'method': ..., 'target_distribution': ...})
  → ProcessingAdapter(process_type='transformation', method=...)
  → AdaptiveTransformer(method=...)
```

Mixed 同构.

**legacy 路径**: `PipelineV2ConfigUnified.to_pipeline_config()` 把
`static.transformation.model_dump()` 写入 `StepConfig.params`, 因此 `method` 默认值
从 `auto` 变为 `rank` 会同时改变 legacy `FactorProcessingPipeline` 的行为 — 这是 D2 的
预期结果, 不是旁路泄漏. `target_distribution` 作为已知键传入 `AdaptiveTransformer`.

---

## §6 工程细节

### 6.1 性能基准 (实测)

环境: Python 3.12, T=2500, N=3000, NaN 5%, `t(3)` 分布.

| 实现 | 耗时 | max abs diff |
|------|------|-------------|
| `rankdata` 逐行 (**最终实现**) | 1.071 s | 基准 |
| pandas 向量化 `X.rank(axis=1)` + `norm.ppf` | 1.104 s | 0.0 |
| pandas 逐行 `Series.rank` + numpy 赋值 | 1.130 s | 0.0 |
| pandas 向量化 uniform | 0.976 s | — |

三者数值**完全一致** (`max diff = 0.0`). 选 `rankdata` 逐行: 唯一算法、无 pandas 广播陷阱、性能最优.

输出统计 (中位列): `normal` std = 0.9989543; `uniform` std = 0.5773950 (理论 `1/√3 = 0.5773503`).

对比 PL-01: percentile 快速路径 0.212 s / 非 percentile 逐行 2.56 s (同口径). rank 处于同一量级.

### 6.2 dtype 与内存

- 输入 `float32` / `float64` → `to_numpy(dtype=float)` 统一转为 `float64`. 输出统一 `float64`.
- 中间对象: `arr` (`to_numpy` 副本) + `out` (输出), 均为 T×N float64. T=2500, N=3000 时约 120 MB 峰值. 逐行处理不产生额外的 T×N 中间对象.
- 不复制 `X` 以外的额外长时间存活对象.

### 6.3 日志

| 事件 | 级别 | 频率 |
|------|------|------|
| N<10 回落 | `warning` | 每次 `transform` 一条 (汇总条数: `%d 个截面 N<10`) |
| 方法解析 | `info` | 每次构造一条 |

### 6.4 线程/重入

- `_cross_sectional_rank` 不写任何实例状态, 可并发调用 `transform`.
- `AdaptiveTransformer` 的 `fitted_params` 在 `fit` 后只读, 并发安全.

---

## §7 兼容性与行为变更

| 对象 | 变更 | 处理 |
|------|------|------|
| `StaticFactorPipeline` | `auto` → `rank`; 参数由全样本 MLE → 无状态截面 | ADR-038 + CHANGELOG; 历史 IC/Sharpe 重算 |
| `MixedFactorPipeline` | 顺序 transform→neutralize 改为 neutralize→transform; 条件变换 → 固定 rank | 同上 |
| `PipelineV2Config` | 删除 3 字段, 新增 4 字段 | `to_pipeline_v2_config()` 同步 |
| `TransformationConfig` | 删除 2 字段, 新增 `target_distribution` | `model_dump()` 输出变化 |
| `config.py` legacy | `auto_optimize=True` 变无效键 | CHANGELOG 标注 |
| `demo_v2.py` | 删除 `mixed_conditional_transform` | 示例输出变化 |
| 缓存 | 输出数值改变 | `v2.2.1-cache` → `v2.2.2-cache` |
| `test_adaptive_transformer_identity.py` | 全部失效 | 重写 |
| `test_fix2_config_unification.py::test_09` | 断言字段改变 | 重写 |
| `tests/integration/test_pipeline_truncation_invariance.py` | PL-02/PL-04 xfail 应通过 | 移除 xfail |

**破坏性**: 数值行为变更 + 配置字段删除. 不是 API 破坏 (构造签名除 `auto_optimize` 外兼容).

---

## §8 测试设计 (TDD)

### 8.1 新增单测: `tests/unit/test_transform_rank_cross_sectional.py`

| # | 测试 | 断言 |
|---|------|------|
| 1 | `auto` 解析 | `adapter.method=='rank'`, `requested_method=='auto'` |
| 2 | 别名映射 | `none→identity`, `box_cox→boxcox`, `yeo_johnson→yeojohnson`, `quantile→rank` |
| 3 | 未知方法 | 构造期 `ValueError` |
| 4 | 手工对拍 (normal) | 30×12 面板 (N≥10 避免回落), 输出 == 手工 `Φ⁻¹((rank−3/8)/(n+1/4))` (1e-12) |
| 5 | 手工对拍 (uniform) | 30×12 面板, 输出 == `(2R−n−1)/n` |
| 6 | 截断不变式 | 全样本 vs 前 60%: `n_diff=0`, `max_abs_diff=0` |
| 7 | NaN 保持 | NaN 位置不变; 有效值个数不变 |
| 8 | N<10 回落 | 单个截面 9 个有效值 → 截面 z-score; 10 个 → rank; 1 个 → 原样 |
| 9 | ties 处理 | 含重复值, 输出与 `method='average'` 手工一致 |
| 10 | 非 DataFrame | `TypeError` |
| 11 | 重复 index/columns | `ValueError` |
| 12 | 空 DataFrame | 返回 `copy()` |
| 13 | 目标分布非法 | `ValueError` |
| 14 | 先验参数缺失 | `method='boxcox'` 无 `lam` → `ValueError` |
| 15 | 输出无状态 | 连续两次 `transform` 同一输入得到相同输出; 实例上无新增数值属性 |
| 16 | 单实现对拍 | adapter 输出 == 逐行 `rank_transform_1d` 的输出 (`max diff = 0`) |
| 17 | identity 短路 | `method='identity'`: `fit` 后 `_processor is None`; `transform` 输出等于输入 (`assert_frame_equal`) |
| 18 | identity 不 flatten | `fit` 期间不产生 `X.values.flatten()` (以 mock 断言 `AdaptiveTransformer` 未被实例化) |

### 8.2 截断不变式 (集成)

`tests/integration/test_pipeline_truncation_invariance.py`:
- 移除 PL-02 / PL-04 的 `xfail`;
- 保留 PL-06 / PL-07;
- 更新模块 docstring 的缺陷登记表与实测矩阵.

### 8.3 回归靶向

```
tests/unit/test_transform_rank_cross_sectional.py        (新)
tests/unit/test_outlier_cross_sectional.py
tests/test_adapters/test_module_enabled.py
tests/test_pipelines_v2.py
tests/test_fix2_config_unification.py
tests/unit/test_config_v2.py
tests/integration/test_pipeline_truncation_invariance.py
```

### 8.4 性能验证 (手工, 不入 CI)

按 §6.1 口径复跑, 写入实施文档.

---

## §9 验收标准

- [ ] `test_pipeline_truncation_invariance.py` 的 PL-02 / PL-04 测试通过 (无 xfail), `n_diff=0`.
- [ ] 5×6 面板的手工对拍通过 (normal 与 uniform 各一).
- [ ] `auto` → `rank`; 显式 `method` 不再被覆盖 (单测断言).
- [ ] 先验参数缺失时构造期 `ValueError`.
- [ ] NaN 模式 / index / columns 完全保留.
- [ ] `identity` 与 `rank` 均不走 else 分支: `fit` 不执行 `X.values.flatten()`, `transform` 不逐列调用 processor.
- [ ] N<10 回落截面 z-score, 且日志只报条数.
- [ ] Static / Mixed 均从 `TransformationConfig` 读取方法.
- [ ] 配置名映射全覆盖且未知方法被拒.
- [ ] 缓存代际 bump; `meta.code_version` 不一致时 MISS + 自愈删除.
- [ ] 靶向回归全绿.
- [ ] ADR-038 / CHANGELOG v3.3.4 / 版本 4 处同步.

---

## §10 风险、回滚与后续

### 10.1 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| Static/Mixed 输出变化 | 历史 IC/Sharpe 不可比 | ADR/CHANGELOG; 重跑实验 |
| rank 丢失量纲 | 下游若依赖原始单位不可用 | `identity` opt-out; 文档声明 |
| ties 12.27% (`ret_1d`) | 大量相等值 | `average` 保序; 日志提示 |
| 配置字段删除 | 旧配置文件反序列化失败 | 版本化配置; 提供迁移说明 |
| `auto_optimize` 失效 | legacy 调用方以为仍生效 | CHANGELOG 显式说明 |
| Mixed 顺序变更 | 历史 Mixed 因子不可比 | 缓存 bump; 重跑 |

### 10.2 回滚

- 代码可独立回退: 恢复 `AdaptiveTransformer` 的选型链与 `ProcessingAdapter` 的 else 分支; 恢复 Mixed 顺序; 重新加回 PL-02/PL-04 xfail.
- 配置字段删除需同步回滚 (dataclass + Pydantic + demo + 测试).
- 缓存代际需再 bump 以触发重建.

### 10.3 后续任务 (不在本次)

1. PL-06: Mixed `_compute_winsorize_params` 逐日截面化.
2. PL-05: Dynamic AR `fitted_values` 因果化.
3. PL-07: 指纹路由因果化.
4. 死 rank 代码清理 (调研 §3.7.2 登记项).
5. 旧 transform 路径的逐列维度 (调研 §3.7.1 潜伏缺陷) 的统一修复.

---

## §11 实施顺序 (供实施文档细化)

1. **Red**: 新增 `tests/unit/test_transform_rank_cross_sectional.py`; 保留 PL-02/PL-04 xfail.
2. **Green-1**: `AdaptiveTransformer` 重写 (解析 / 先验校验 / 删除选型链 / rank 分支).
3. **Green-2**: `ProcessingAdapter` 新增 `_cross_sectional_rank` 分支与映射表.
4. **Green-3**: `TransformationConfig` 收敛 + `PipelineV2Config` 字段 + `_create_pipeline` 接线.
5. **Green-4**: `StaticFactorPipeline` / `MixedFactorPipeline` 入参与顺序; 删除 `_diagnose_transform_need`.
6. **Green-5**: 移除 PL-02/PL-04 xfail; 更新诊断矩阵.
7. **回归**: 靶向测试 + 重写 `test_adaptive_transformer_identity.py` 与 `test_fix2_config_unification.py::test_09`.
8. **文档/版本**: ADR-038, CHANGELOG v3.3.4, 版本 4 处同步, 缓存 bump, demo_v2.
9. **验收**: 按 §9 checklist 逐项打勾.

---

## §12 参考

上游调研 [PL02_TRANSFORM_LOOKAHEAD_RESEARCH.md](PL02_TRANSFORM_LOOKAHEAD_RESEARCH.md) §3.6–§3.8 与 §8 (参考文献 1–31).

关键外部依据:
- Peterson & Cavanaugh (2019), JAS 47(13-15):2312–2327, DOI 10.1080/02664763.2019.1630372 (ORQ).
- Leeb & Pötscher (2006), AoS 34(5):2554–2591, DOI 10.1214/009053606000000821.
- McCaw et al., Biometrics, DOI 10.1111/biom.13214 (D-INT / I-INT).
- RNOmni CRAN 文档 (`k=0.375`, `ties.method='average'`).
- Qlib `CSRankNorm`.

---

## 附录 A: 设计自检

| # | 检查项 | 结论 |
|---|--------|------|
| 1 | 每个决策是否引用上游调研? | 是 (§3 D1-D9) |
| 2 | 是否引入未实测的数字? | 否; §6.1 为本设计新增实测 (1.144s / 1.130s / 0.0) |
| 3 | 是否覆盖截断不变式的结构性论证? | 是 (D8; 调研 §3.7.4) |
| 4 | 是否声明非目标与范围边界? | 是 (§1.2) |
| 5 | 是否给出回滚路径? | 是 (§10.2) |
| 6 | 是否与 PL-01 设计同构? | 是 (§4/§5/§8 结构对齐) |
| 7 | 是否处理 fit/transform 口径 (T7)? | 是 (D9) |
| 8 | 是否处理缓存代际? | 是 (§7) |
| 9 | 是否处理名称映射 (T6)? | 是 (D7) |
| 10 | 是否处理可复现性 (T5)? | 是 (D2 删除未设种子的选型链) |
| 11 | 是否有未决项? | 无. N 下限已定为 10 (§5.3.3); 上游 §3.7.6 的 4 项全部落定 (D6 / §5.2 / §5.3.2 / §5.4) |
| 12 | `fit` 分支是否覆盖? | 是 (§5.2 `fit` 表); `identity` 与 `rank` 均为 no-op, 不触发 flatten |
| 13 | 是否区分"入口强制 DataFrame"与"transform 强制"? | 是: 截面语义由 `ProcessingAdapter` 承担 (§5.3.1), `AdaptiveTransformer.transform` 拒绝 DataFrame (§5.6) |
