# v3.3.3 PL-01 去极值因果性修复 — 实施文档

**文档版本**: v1.0
**日期**: 2026-10-22
**缺陷**: DEFECT-PL-01
**设计依据**: [docs/analysis/PL01_OUTLIER_LOOKAHEAD_DESIGN.md](analysis/PL01_OUTLIER_LOOKAHEAD_DESIGN.md)
**调研依据**: [docs/analysis/PL01_OUTLIER_LOOKAHEAD_RESEARCH.md](analysis/PL01_OUTLIER_LOOKAHEAD_RESEARCH.md)
**目标版本**: v3.3.3
**变更性质**: 数值行为变更 (非 API 破坏) + 缓存代际 bump
**实施方式**: 严格 TDD (Red → Green → 回归 → 文档/版本)
**行号说明**: 文中的行号仅作导航, 以类名/函数名/测试名为准 (编辑后会漂移)

---

## §0 实施摘要

| 项 | 内容 |
|---|------|
| 核心改动 | `ProcessingAdapter(process_type='outlier')` 从"全 panel 池化 + auto 选型"改为"逐日横截面 + 固定方法解析" |
| 代码文件 | `adapters.py` (主要); `backtest/cache_manager.py` + 4 个缓存默认值 (缓存代际) |
| 测试文件 | 新增 `tests/unit/test_outlier_cross_sectional.py`; 修改 `tests/integration/test_pipeline_truncation_invariance.py`; 修改 `tests/test_fix3_version_unification.py` |
| 版本同步 | 4 处声明 + 测试锚点 + 缓存 code_version |
| 文档 | ADR-037 / CHANGELOG v3.3.3 / 勘误注 / DEV_PROGRESS / ARCHITECTURE |
| 验收关键 | PL-01 隔离测试 `n_diff_cells=0`, `max_abs_diff=0`; 全方法截断不变式通过 |

**不实施**: PL-02/05/06/07、`OutlierConfig` 接线、`threshold` 语义、rank-normal、时序 expanding 轴。

---

## §1 前置条件与基线

### 1.1 环境

| 项 | 值 |
|---|-----|
| 解释器 | `C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe` (pytest 9.x) |
| 工作目录 | `F:\Coding` (父目录, 避免 `factor_pipeline/types.py` 遮蔽标准库 `types`) |
| Python / pandas | `>=3.9` / `>=2.0.0` (pyproject) |
| 新增依赖 | 无 |

### 1.2 基线 (实施前必须记录)

```powershell
cd F:\Coding
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/integration/test_pipeline_truncation_invariance.py -q
```

预期: 12 项, 6 passed / 6 xfailed (含 PL-01)。若基线不同, 先记录实际值再继续。

```powershell
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/unit/test_adapters_mock.py `
  factor_pipeline/tests/test_adapters/test_module_enabled.py -q
```

预期: **38 passed, 2 skipped**。`test_transform_outlier` 使用 fixture `max|value|=50`; 逐行 MAD 实测输出 max≈2.85, 不会回归。

---

## §2 变更清单

| # | 文件 | 变更 | 风险 |
|---|------|------|------|
| 1 | `adapters.py` | 常量 + `__init__` 解析/校验 + `fit` no-op + `transform` 分支 + 3 个 helper + `get_stats` | 中 |
| 2 | `tests/unit/test_outlier_cross_sectional.py` | **新增** 15 个测试函数 (参数化 30 例) | 低 |
| 3 | `tests/integration/test_pipeline_truncation_invariance.py` | 移除 PL-01 xfail; 更新登记表/reason | 低 |
| 4 | `tests/test_fix3_version_unification.py` | `EXPECTED_VERSION` → 3.3.3; 缓存版本断言 → 2.2.1-cache; 新增 5 处默认值一致性测试 (`test_07`) | 低 |
| 5 | `pyproject.toml` / `__init__.py` / `config_v2.py` / `reporting.py` | 版本 → 3.3.3 | 低 |
| 6 | `backtest/cache_manager.py` + `cached_data_loader.py` + `factor_cache.py` / `fwd_returns_cache.py` / `price_cache.py` | 缓存 `code_version` → `v2.2.1-cache`; 读取时校验代际, 不一致 → MISS + 自愈删除; 子缓存默认值统一引用 `CODE_VERSION` | 中 (一次性缓存重建) |
| 7 | `DECISIONS.md` | ADR-037 + 占用登记 | 低 |
| 8 | `CHANGELOG.md` | v3.3.3 条目 | 低 |
| 9 | `principle_vs_hacking_audit_v2.md` / `academic_literature_decision_criteria.md` | 日期化勘误注, 不改写历史结论 | 低 |
| 10 | `docs/DEV_PROGRESS.md` / `docs/ARCHITECTURE.md` / `docs/WORKFLOW_METHODOLOGY.md` | 版本基线、ADR 范围 | 低 |

---

## §3 代码实施: `adapters.py`

### 3.1 常量 (放在现有常量区, L37-L45 附近)

```python
# PL-01: outlier 逐日横截面
_OUTLIER_METHODS = frozenset({
    'percentile', 'quantile', 'z_score', 'mad', 'iqr', 'adaptive', 'sigmoid_soft',
})
_OUTLIER_DETECTOR_PARAM_KEYS = (
    'percentile_lower', 'percentile_upper', 'max_outlier_frac', 'adaptive_threshold',
)
_MIN_OUTLIER_CROSS_SECTION_OBS = 3
```

- 不加公共导出。
- `_MIN_OUTLIER_CROSS_SECTION_OBS` 与 detector 内部 `<3` 判据一致。

### 3.2 `ProcessingAdapter.__init__` (L320-L350)

在 `__init__` 开头记录原始方法 (先于 PL-03 / PL-01 的 `auto` 解析), 并在 `super().__init__` 之前完成 outlier 解析:

```python
        requested_method = method
        if process_type == 'outlier':
            if method == 'auto':
                method = 'percentile'
            if method not in _OUTLIER_METHODS:
                raise ValueError(
                    f"ProcessingAdapter(outlier): 未知 method={method!r}; "
                    f"合法值: {sorted(_OUTLIER_METHODS)} 或 'auto'"
                )
            percentile_lower = float(params.get('percentile_lower', 1.0))
            percentile_upper = float(params.get('percentile_upper', 99.0))
            self._validate_outlier_percentiles(percentile_lower, percentile_upper)
        else:
            percentile_lower = percentile_upper = None
```

在 `super().__init__(...)` 与现有属性初始化之后:

```python
        self.requested_method = requested_method
        self._cross_sectional_outlier = (process_type == 'outlier')
        if self._cross_sectional_outlier:
            self._outlier_percentile_lower = percentile_lower
            self._outlier_percentile_upper = percentile_upper
            self._outlier_detector_kwargs = {
                key: params[key]
                for key in _OUTLIER_DETECTOR_PARAM_KEYS
                if key in params
            }
        else:
            self._outlier_detector_kwargs = {}
```

新增静态校验方法:

```python
    @staticmethod
    def _validate_outlier_percentiles(lo: float, hi: float) -> None:
        if not (0.0 <= lo < hi <= 100.0):
            raise ValueError(
                f"outlier 分位需满足 0 <= lower < upper <= 100 (0-100 百分数); "
                f"收到 lower={lo}, upper={hi}"
            )
        if hi < 1.0:
            raise ValueError(
                f"outlier percentile_upper={hi} 疑似使用 0-1 小数约定; "
                f"本接口使用 0-100 百分数, 请乘以 100 (如 0.01/0.99 → 1/99)"
            )
```

注意:
- `self.method` 存解析值 (`auto` → `percentile`); `self.requested_method` 存原值。
- `params` 中的 `threshold` / `lower_percentile` / `upper_percentile` 不进入 detector; 不解释其语义 (见 §8 后续任务)。

### 3.3 `fit` (L413-L454)

在 `enabled=False` 分支之后、`processor_params` 之前插入:

```python
        if self._cross_sectional_outlier:
            if not isinstance(X, pd.DataFrame):
                raise TypeError(
                    f"ProcessingAdapter(outlier): 需要 pd.DataFrame, 收到 {type(X).__name__}"
                )
            self._processor = None
            self._column_processors = {}
            self.is_fitted = True
            logger.info(
                "ProcessingAdapter(outlier): 逐日横截面, fit 无参数 (method=%s)",
                self.method,
            )
            return self
```

- 不存任何边界/分位数 → 结构上无泄漏面。
- 类型检查放在 no-op 内, 保持"fit 即校验输入形态"的契约。

### 3.4 `transform` 分支 (L456-L502)

在 `is_fitted` 检查之后、`_cross_sectional_zscore` 分支之前插入:

```python
        if self._cross_sectional_outlier:
            return self._transform_outlier_cross_sectional(X)
```

其余分支 (zscore / standardization per-column / generic per-column) 不变。

### 3.5 新增 helper (放在 `transform` 与 `get_stats` 之间)

```python
    def _transform_outlier_cross_sectional(self, X: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(X, pd.DataFrame):
            raise TypeError(
                f"ProcessingAdapter(outlier): 需要 pd.DataFrame, 收到 {type(X).__name__}"
            )
        if X.index.has_duplicates or X.columns.has_duplicates:
            raise ValueError("ProcessingAdapter(outlier): index/columns 必须唯一")
        if X.empty:
            return X.copy()
        try:
            if self.method == 'percentile':
                return self._transform_outlier_percentile(X)
            return self._transform_outlier_rowwise(X)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "ProcessingAdapter(outlier): 输入必须为数值型 DataFrame"
            ) from exc

    def _transform_outlier_percentile(self, X: pd.DataFrame) -> pd.DataFrame:
        valid = X.notna().sum(axis=1) >= _MIN_OUTLIER_CROSS_SECTION_OBS
        lower = X.quantile(self._outlier_percentile_lower / 100.0, axis=1).where(valid)
        upper = X.quantile(self._outlier_percentile_upper / 100.0, axis=1).where(valid)
        return X.clip(lower=lower, upper=upper, axis=0)

    def _transform_outlier_rowwise(self, X: pd.DataFrame) -> pd.DataFrame:
        values = X.to_numpy(dtype=float, copy=True)
        valid = np.sum(~np.isnan(values), axis=1)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            dispersion = np.nanstd(values, axis=1)
        rows = np.flatnonzero(
            (valid >= _MIN_OUTLIER_CROSS_SECTION_OBS) & (dispersion > 1e-15)
        )
        if rows.size:
            detector = self._processor_class(
                method=self.method,
                auto_select=False,
                **self._outlier_detector_kwargs,
            )
            for i in rows:
                detector.fit(values[i])
                values[i] = detector.transform(values[i])
        return pd.DataFrame(values, index=X.index, columns=X.columns)
```

关键实现说明:

| 点 | 原因 |
|----|------|
| `Series.where(valid)` | 有效值 <3 的行边界置 NaN; `clip` 在 NaN 边界下不改值 |
| `to_numpy(dtype=float, copy=True)` | 输出与输入解耦; NaN 保留; 统一 float64 |
| `np.nanstd` + 警告抑制 | 全 NaN 行会产生 RuntimeWarning; 这些行本就被 `valid<3` 排除 |
| `dispersion > 1e-15` | 零离散度行对 MAD/Z 会产生除零/无意义边界; 原样返回 |
| detector 局部创建 | 不挂 `self`, 避免并发调用共享 `fitted_params`; `fit` 每行覆盖 |
| `auto_select=False` | 唯一允许的方法解析点在 `ProcessingAdapter.__init__` |

### 3.6 `get_stats`

在现有 `stats['method']` 之后插入:

```python
        stats['requested_method'] = self.requested_method
        if self._cross_sectional_outlier:
            stats['outlier_scope'] = 'cross_sectional'
            stats['percentile_lower'] = self._outlier_percentile_lower
            stats['percentile_upper'] = self._outlier_percentile_upper
```

`fitted_params` 仍只对 `_processor` 存在时报告; outlier 截面分支不报告。

### 3.7 兼容性检查

- `transformation` / `standardization` 路径不经过新分支。
- `enabled=False`: `transform` 在分支前返回 X; `fit` 置 `is_fitted=True`; `_processor_class=None` 契约不变。
- `process_type='invalid'`: `_cross_sectional_outlier=False`, 保持原有默认行为。
- `method='auto'` 的非 outlier 类型: 解析逻辑不变。

---

## §4 TDD 测试

### 4.1 Red: 新增 `tests/unit/test_outlier_cross_sectional.py`

先写测试, 确认全部失败 (Import/Attribute/断言)。测试骨架:

```python
# -*- coding: utf-8 -*-
"""PL-01: ProcessingAdapter 去极值逐日横截面 — TDD 测试."""
import numpy as np
import pandas as pd
import pytest

from factor_pipeline.adapters import ProcessingAdapter


def _panel(T=40, N=10, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.standard_normal((T, N)),
        index=pd.date_range('2020-01-01', periods=T, freq='D'),
        columns=[f's{i}' for i in range(N)],
    )


def _split(df, frac=0.6):
    t = int(len(df) * frac)
    return df, df.iloc[:t], t


def _run_pair(adapter_factory, df):
    full, trunc, t = _split(df)
    a = adapter_factory(); a.fit(full); out_full = a.transform(full)
    b = adapter_factory(); b.fit(trunc); out_trunc = b.transform(trunc)
    return out_full.iloc[:t], out_trunc
```

| # | 测试 | 断言 |
|---|------|------|
| 1 | `test_auto_resolves_to_percentile` | `method=='percentile'`, `requested_method=='auto'` |
| 2 | `test_explicit_method_preserved` (params 7 方法) | `adapter.method == m` |
| 3 | `test_percentile_bounds_match_manual` | 5×8 面板输出 == 手工 `np.percentile(row,[1,99])` + clip, `atol=1e-12` |
| 4 | `test_percentile_is_truncation_invariant` | `n_diff_cells=0`, `max_abs_diff=0` |
| 5 | `test_preserves_nan_and_metadata` | NaN 模式不变; index/columns 相等 |
| 6 | `test_small_rows_unchanged` | 1 行 / 2 列 / 全 NaN 行原样 |
| 7 | `test_zero_dispersion_row_unchanged` | 全等值行不变; 无警告 |
| 8 | `test_mad_is_truncation_invariant` | `mad` 逐行路径 0 差异 |
| 9 | `test_all_methods_are_truncation_invariant` | 6 个显式方法参数化 |
| 10 | `test_invalid_method_raises` | `ValueError` |
| 11 | `test_invalid_percentiles_raise` | `lo>=hi` / `hi<1` / `>100` 均 `ValueError` |
| 12 | `test_non_dataframe_raises` | Series/ndarray → `TypeError` |
| 13 | `test_enabled_false_is_identity` | 原样; `_processor is None`; `_processor_class is None` |
| 14 | `test_fit_is_noop` | `_processor is None`; 重复 fit 无状态变化 |
| 15 | `test_get_stats` | `outlier_scope`, `requested_method`, 分位字段 |

关键测试示例:

```python
def test_percentile_bounds_match_manual():
    df = _panel(T=5, N=8, seed=1)
    adapter = ProcessingAdapter(process_type='outlier', method='percentile',
                                percentile_lower=1.0, percentile_upper=99.0)
    out = adapter.fit_transform(df)
    lo = np.percentile(df.values, 1, axis=1)
    hi = np.percentile(df.values, 99, axis=1)
    expected = np.clip(df.values, lo[:, None], hi[:, None])
    np.testing.assert_allclose(out.values, expected, atol=1e-12, rtol=0)


def test_percentile_is_truncation_invariant():
    df = _panel(T=60, N=10, seed=2)
    out_full, out_trunc = _run_pair(
        lambda: ProcessingAdapter(process_type='outlier', method='percentile',
                                  percentile_lower=1.0, percentile_upper=99.0),
        df,
    )
    pd.testing.assert_frame_equal(
        out_full, out_trunc, check_exact=False, atol=1e-12, rtol=0
    )
```

注意:
- `test_all_methods_are_truncation_invariant` 的 `sigmoid_soft` 在 N=10 时 `k=0.5`; 仍应逐值一致。
- 方法参数化时不要用 `method='auto'` (已由测试 1 覆盖)。
- 若 `adaptive`/`sigmoid_soft` 产生 RuntimeWarning, 用 `warnings.catch_warnings` 局部过滤, 不要全局 `simplefilter('ignore')`。

### 4.2 Green: 代码实现

按 §3 顺序落地。每个子步骤后可跑:

```powershell
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/unit/test_outlier_cross_sectional.py -q
```

### 4.3 集成测试: 移除 PL-01 xfail

在 [tests/integration/test_pipeline_truncation_invariance.py L230-L244](../tests/integration/test_pipeline_truncation_invariance.py#L230-L244):

1. 删除 `@pytest.mark.xfail(...)` 装饰器。
2. docstring 改为: "去极值 percentile: 逐日截面 → 应满足"。
3. 运行:

```powershell
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/integration/test_pipeline_truncation_invariance.py -q -s
```

预期: 原 PL-01 项通过; `test_diagnostic_report` 输出中 `outlier percentile` 行 `n_diff_cells=0`, `max_abs_diff=0`。

4. 用诊断报告实测值更新:
   - 模块 docstring 的缺陷登记表 (PL-01 移到"已修复"; PL-04 残留仅 PL-02; PL-06 残留 PL-02 + Mixed winsorizer; PL-07 残留)。
   - PL-04/PL-06/PL-07 的 xfail reason 数值。
   - **不要预填未实测的数字**; 以本次输出为准。
   - 注意: 现有 PL-05 (Dynamic) / PL-06 (Mixed) 的 reason 把 PL-01 计入, 但这两条管线并不经过 `ProcessingAdapter(outlier)` (Dynamic 无 outlier 步; Mixed 用自身 `_compute_winsorize_params`)。更新 reason 时应删去 PL-01 归因, 以诊断实测为准。

### 4.4 回归靶向

```powershell
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/unit/test_outlier_cross_sectional.py `
  factor_pipeline/tests/integration/test_pipeline_truncation_invariance.py `
  factor_pipeline/tests/unit/test_adapters_mock.py `
  factor_pipeline/tests/test_adapters/test_module_enabled.py `
  factor_pipeline/tests/test_pipelines_v2.py `
  factor_pipeline/tests/unit/test_step1_winsorizer_percentile.py `
  factor_pipeline/tests/unit/test_config_v2.py `
  factor_pipeline/tests/unit/test_reporting.py -q
```

预期: 0 failed; 允许已知 xfail (PL-02/04/05/06/07)。

### 4.5 性能验证 (手工, 不入 CI)

复用设计探针 (临时目录, 不提交): T=2500/N=3000。

| 路径 | 门限 | 实测 (填) |
|------|------|-----------|
| `percentile` 快速路径 | ≤0.5s | |
| `mad` 逐行路径 | ≤5s | |

若超门限: 先确认是否被其他步骤干扰; 不直接改设计, 记录后评估 `quantile/iqr` 快速路径。

---

## §5 版本、缓存与文档

### 5.1 版本 → v3.3.3 (5 处)

| 文件 | 变更 |
|------|------|
| `pyproject.toml:7` | `version = "3.3.3"` |
| `__init__.py:58` | `__version__ = "3.3.3"` |
| `config_v2.py:379` | `Field(default="3.3.3", ...)` |
| `reporting.py:40` | `pipeline_version: str = "3.3.3"` |
| `tests/test_fix3_version_unification.py:31` | `EXPECTED_VERSION = "3.3.3"` |

同步更新该测试文件中三处 docstring 的版本描述。

### 5.2 缓存代际 → `v2.2.1-cache`

**理由**: 去极值输出改变, 旧因子缓存不再有效; 若不 bump, 回测会复用旧因子值, 使修复"看起来没生效"。

| 文件 | 变更 |
|------|------|
| `backtest/cache_manager.py:57` | `CODE_VERSION = "v2.2.1-cache"` |
| `backtest/cached_data_loader.py:81` | 默认值 → `"v2.2.1-cache"` |
| `backtest/factor_cache.py:54` | 同上 |
| `backtest/fwd_returns_cache.py:50` | 同上 |
| `backtest/price_cache.py:53` | 同上 |
| `tests/test_fix3_version_unification.py:77-91` | 断言从 `v2.2.0-cache` → `v2.2.1-cache`; docstring 说明"算法变更可 bump, 仍不跟随项目版本" |

注意:
- 同时更新 `tests/test_fix3_version_unification.py` 文件头 docstring 的缓存版本说明, 以及 `test_05` 的 docstring (原写"保持 v2.2.0-cache 不变")。
- `cached_data_loader` 用同一个 `code_version` 构造 price/factor 缓存; 本次会一次性失效价格缓存。可接受 (只重算, 无数据丢失)。
- `tests/test_backtest/verify_fix3_manual.py` 的独立性检查仍通过 (含 `cache`, 且 != 3.3.3)。

### 5.3 ADR-037

在 `DECISIONS.md` 追加 ADR-037, 结构:

```
## ADR-037: 去极值统一为逐日横截面 (DEFECT-PL-01, v3.3.3)
### 背景
- PL-01 两重前视 + auto 覆盖显式方法; 实测 154/187 格, max 1.81e-01
- ADR-027 已在 2026-07 决策固定 percentile(1,99), adapter 未实现
### 决策
- outlier 统一逐日截面; fit no-op
- auto → percentile; auto_select=False
- percentile 向量化; 其他方法逐行复用 detector
### 备选 (拒绝)
- expanding 逐列 / 全样本 / auto 逐日选型 / module 层 axis
### 后果
- Static/legacy/demo 输出改变; 缓存 bump; 消融需重跑
### 测试契约
- PL-01 xfail 移除; 15 项单测; 全方法截断不变式
### 不覆盖
- PL-02/05/06, OutlierConfig/threshold, rank-normal
### 回滚
- 移除新分支, 恢复 xfail
```

同时更新文首「占用现状」表: `| ADR-037 | 去极值统一为逐日横截面 | v3.3.3, 2026-10-22 |`, 并把 `ADR-038 起 | 未占用`。

### 5.4 CHANGELOG v3.3.3

章节:
- 概览 (两重前视 + ADR-027 未实现)
- 根因与实测 (引用调研数字)
- 修复 (逐日截面 + auto 解析 + 快速路径)
- 行为变更 (Static/legacy/demo/缓存)
- 测试结果 (单测/集成/回归/性能)
- 已知遗留 (PL-02/05/06/07; OutlierConfig 桥接; threshold 语义)
- 文档产出 (ADR-037, 勘误)

### 5.5 勘误与状态文档

| 文件 | 处理 |
|------|------|
| `docs/analysis/principle_vs_hacking_audit_v2.md` | 在 §2.2 增加 2026-10-22 勘误注: 当时的 "已修复" 只覆盖 detector 直接实例化; adapter 未传 `auto_select=False`; 已在 ADR-037 修复。**不改写原文** |
| `docs/analysis/academic_literature_decision_criteria.md` | §9.1 增加 "2026-10-22 实施: 逐日截面分支落地; 见 ADR-037" |
| `docs/analysis/PL01_OUTLIER_LOOKAHEAD_RESEARCH.md` | 头部状态 → "已实施 (v3.3.3)" |
| `docs/analysis/PL01_OUTLIER_LOOKAHEAD_DESIGN.md` | 头部状态 → "已实施 (v3.3.3)" |
| `docs/DEV_PROGRESS.md` | 路线图当前标记 → v3.3.3 |
| `docs/ARCHITECTURE.md` | 版本基线追加 v3.3.3; 模块表 outlier 标注"逐日截面" |
| `docs/WORKFLOW_METHODOLOGY.md` | `ADR-001 至 ADR-036` → `至 ADR-037` |

---

## §6 执行顺序 (含检查点)

| 步骤 | 动作 | 检查点 |
|------|------|--------|
| 0 | 记录基线 (§1.2) | 6 xfailed 含 PL-01 |
| 1 | 新增单测 (Red) | 15 项失败 (预期) |
| 2 | §3.1-3.2 常量 + 构造解析 | 测试 1/2/10/11 通过 |
| 3 | §3.3-3.5 fit/transform/helper | 测试 3-9/12-14 通过 |
| 4 | §3.6 get_stats | 测试 15 通过 |
| 5 | 移除 PL-01 xfail | 集成测试通过; 诊断行 0 |
| 6 | 更新登记表/reason | 与诊断输出一致 |
| 7 | 回归靶向 (§4.4) | 0 failed |
| 8 | 性能 (§4.5) | 满足门限 |
| 9 | 版本/缓存 (§5.1-5.2) | 版本测试 + 手工校验 |
| 10 | ADR/CHANGELOG/勘误 (§5.3-5.5) | 文档链接有效 |
| 11 | 验收 checklist | 全项通过 |

---

## §7 验收记录 (实施后填写)

| 指标 | 门限/期望 | 实测 | 状态 |
|------|-----------|------|------|
| 单测 | 15 passed | **30 passed** (15 函数参数化 30 例) | 通过 |
| PL-01 隔离 | `n_diff_cells=0`, `max_abs_diff=0` | **0 / 0** | 通过 |
| 全方法不变式 | 6/6 通过 | **7/7 通过** (含 percentile) | 通过 |
| Static 端到端 | 降至 PL-02 量级 (记录实际) | **1800 格 / 4.72e-05** | 通过 |
| 诊断矩阵 outlier 行 | 0 / 0 | **0 / 0** | 通过 |
| 回归靶向 | 0 failed | **126 passed / 2 skipped / 5 xfailed / 0 failed** | 通过 |
| percentile 性能 | ≤0.5s | **0.226s** (T=2500/N=3000) | 通过 |
| MAD 性能 | ≤5s | **2.888s** (T=2500/N=3000) | 通过 |
| 版本 5 处 | 均 3.3.3 | **5/5 一致** | 通过 |
| 缓存版本 | 5 处均 v2.2.1-cache | **5/5 引用同一常量** | 通过 |
| 缓存代际失效 | 写入 v2.2.0 → 读取 v2.2.1 = MISS + 删除 | **3 passed** (`TestCodeVersionGeneration`) | 通过 |

**补充回归**: `tests/unit` + `tests/test_adapters` + `tests/integration` +
`test_pipelines_v2.py` + 版本/修复测试 = **348 passed / 2 skipped / 5 xfailed / 0 failed**。
缓存相关 6 个测试文件 = **91 passed** (含 `TestCodeVersionGeneration` 3 项与 `test_07` 五处一致性)。
环境阻断项 (CUSUM 模块缺失 / DuckDB 文件锁 / real-data 收集) 已记录在 checklist Gate 4。

---

## §8 风险、回滚与后续

### 8.1 风险

| 风险 | 缓解 |
|------|------|
| Static/legacy 输出变化, 历史结果不可比 | ADR/CHANGELOG 声明; 重跑关键实验 |
| 缓存未失效导致"修复未生效" | §5.2 bump; 验收检查 5 处 |
| `test_transform_outlier` 回归 | 已实测逐行 MAD 将 50 压到 2.85 |
| 逐行路径性能超限 | 记录; 后续评估 `quantile/iqr` 快速路径 |
| 分位单位误用 | 构造期 `hi<1` 拦截 |
| 并发共享 detector | detector 局部创建, 不挂 self |

### 8.2 回滚

1. 还原 `adapters.py` 新分支 (保留 PL-03 修复)。
2. 恢复 PL-01 xfail。
3. 版本/缓存回退到 3.3.2 / v2.2.0-cache (若已发布则保留新版本, 发布回滚说明)。
4. 无数据迁移; 缓存可删除重建。

### 8.3 后续任务

1. `OutlierConfig` 接线 + `to_pipeline_config()` TypeError (独立缺陷)。
2. `threshold` 固定/自适应语义 (独立 ADR)。
3. rank-normal / 时序 expanding 轴评估。
4. 非 percentile 方法向量化 (若性能成为瓶颈)。

---

## §9 交付物

- 代码: `adapters.py` + 5 个缓存版本常量。
- 测试: `tests/unit/test_outlier_cross_sectional.py`; 集成/版本测试修改。
- 文档: ADR-037, CHANGELOG v3.3.3, 勘误注, 状态更新。
- 验收: [CHECKLIST_V3.3.3_PL01_OUTLIER_CAUSALITY.md](CHECKLIST_V3.3.3_PL01_OUTLIER_CAUSALITY.md)。

---

## 附录 A: 常用命令

```powershell
# 单测
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/unit/test_outlier_cross_sectional.py -q

# 集成 + 诊断输出
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/integration/test_pipeline_truncation_invariance.py -q -s

# 版本统一
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe -m pytest `
  factor_pipeline/tests/test_fix3_version_unification.py `
  factor_pipeline/tests/unit/test_config_v2.py `
  factor_pipeline/tests/unit/test_reporting.py -q

# 手工版本/缓存校验
C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe `
  factor_pipeline/tests/test_backtest/verify_fix3_manual.py
```

## 附录 B: 实施自检

- [x] 未修改 `SmartOutlierDetector` 默认 `auto_select=True`。
- [x] 未修改 `transformation` / `standardization` 分支。
- [x] outlier `fit` 不存参数。
- [x] `percentile` 路径无 `_processor`。
- [x] 行循环使用 `auto_select=False`。
- [x] 所有新异常消息包含 `ProcessingAdapter(outlier)` 前缀。
- [x] 无新增依赖。
- [x] 无临时探针脚本进入仓库 (基准脚本置于 `%TEMP%` 并已删除)。
- [x] 文档中无未实测的"预期数字"被写成结论。
