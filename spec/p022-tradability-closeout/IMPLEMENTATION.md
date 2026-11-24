# 实施文档：P-022 tradability 收口包

---
id: p022-tradability-closeout-IMPLEMENTATION
type: design
version: 1.2
status: verified
date: 2026-11-23
depends: [p022-tradability-closeout-DESIGN, p022-tradability-closeout-RESEARCH]
upstream: null
---

> **Feature**: P-022（P-2 内存 / U-7 阈值 / U-8 阈值 / R-3 敏感性）
> **创建日期**: 2026-11-23
> **状态**: verified（Step 5 完成；Step 6 独立只读复审 PASS_WITH_FIXES 已处置，记录见 §9；Step 9/10 记录见 §9.1/§9.2）
> **Spec 步骤**: Step 5-6
> **基于设计**: [DESIGN.md](./DESIGN.md)（v1.2 verified）
> **基于调研**: [RESEARCH.md](./RESEARCH.md)（v1.2 verified）
> **档位**: **T1** ｜ **包版本**: 3.10.0 → **3.10.1** ｜ **新依赖**: **无**

---

## 1. 实施概述

按 DESIGN D1-D9 分 **A1-A5** 五步实施，每步先写测试（TDD）：

- **A1 loader**：紧凑 name/suspend 缓存 + `_PanelRecord` + `_slice` 同对象快路径 + 首次加载顺序。
- **A2 builder**：可选紧凑参数 + `_frame`/`_normalize_panel` 零拷贝快路径 + `missing_fields` 修正。
- **A3 热路径**：`_pct_row` 单源化 + apply 按行 + `compute_turnover` 单行缓冲。
- **A4 引擎/并行**：`effective` 按行原地累加 + worker 载荷子集。
- **A5 收口**：`scripts/verify_tradability_closeout.py` + 版本 3.10.1 + CHANGELOG + 文档回填。

**硬边界**：`tradability_inputs=None` / `tradability_spec=None` 旧路径逐位不变；启用路径同一输入的 `report/meta/diagnostics/turnover` 逐位不变；`report` 9 键 / `meta` 13 键冻结；零新增运行时依赖；Python>=3.9 / pandas>=2.0 / numpy>=1.22。

---

## 2. 工程细节

### 2.1 技术栈与版本

| 组件 | 版本/约束 | 验证 |
|---|---|---|
| Python | `>=3.9`（`pyproject.toml:10`） | 不使用 `X \| None`；用 `Optional[...]` |
| numpy | `>=1.22`（`pyproject.toml:27`） | `np.subtract(out=)`/`np.ix_` 均稳定 API |
| pandas | `>=2.0`（`pyproject.toml:28`） | `factorize`/`ffill`/`reindex`/`dtype` 均 2.0 已有 |
| pyarrow | 既有可选（`calib` extra） | 本批不涉及 |
| pytest | 既有 `dev` extra | 不新增 |

**结论**：零新增依赖 → PyPI 查询 N/A（理由：无新增）。

### 2.2 版本落点（6 处）

| 文件 | 现值 | 改为 |
|---|---|---|
| `pyproject.toml:7` | 3.10.0 | **3.10.1** |
| `__init__.py:58` | 3.10.0 | **3.10.1** |
| `config_v2.py:371` | 3.10.0 | **3.10.1** |
| `reporting.py:40` | 3.10.0 | **3.10.1** |
| `tests/test_fix3_version_unification.py:34` | 3.10.0 | **3.10.1** |
| `tests/test_backtest/verify_fix3_manual.py:21` | 3.10.0 | **3.10.1** |

### 2.3 文件结构（改动面）

```
backtest/tradability_loader.py     # 改：_PanelRecord + 紧凑缓存 + 加载顺序 + _slice 快路径
backtest/tradability_inputs.py     # 改：可选紧凑参数 + _frame 快路径 + missing_fields
backtest/tradability.py            # 改：_pct_row 单源 + apply 按行
backtest/engine.py                 # 改：effective 按行原地累加
backtest/factor_metrics.py         # 改：compute_turnover 单行缓冲
backtest/parallel_runner.py        # 改：worker_args 因子子集
scripts/verify_tradability_closeout.py  # 新：U-7/U-8/R-3 证据
tests/test_tradability_p022.py     # 新：紧凑/零拷贝/逐位/载荷/脚本
tests/test_tradability_loader.py   # 改：缓存结构断言（不破坏既有 6 例）
tests/test_tradability_pipeline.py # 改：逐位基线 fixture（若需）
pyproject.toml / __init__.py / config_v2.py / reporting.py / CHANGELOG.md  # 3.10.1
docs/PROGRESS.md / docs/PROJECT_STATUS.md  # 台账
```

---

## 3. 模块实施

### 3.1 `backtest/tradability_loader.py`

#### 3.1.1 `_PanelRecord`

```python
class _PanelRecord(object):
    __slots__ = ("kind", "index", "columns", "data", "aux")
    # kind: "float" | "name" | "suspend" | "raw"
    # data: DataFrame | ndarray(float32 codes) | (mask, missing) | DataFrame
    # aux:  name → (uniques, st_lut, del_lut)；其余 None
```

- `_PANEL_CACHE[key] = _PanelRecord(...)`；key 不变 `(data_root, panel_dir, name)`。
- 新增访问器：`_panel_df(rec)`（float/raw 返回 DataFrame）、`_panel_columns(rec)`、`_panel_index(rec)`。
- `build` 中 L62/L65/L84/L88-L90/L108/L144 的 DataFrame 直用改为访问器（P2-6）。

#### 3.1.2 `_read_panel` 紧凑化

```python
def _read_panel(self, name):
    key = (self.data_root, self.panel_dir, name)
    rec = _PANEL_CACHE.get(key)
    if rec is not None:
        return rec
    path = ...
    if not os.path.exists(path):
        return None
    frame = pd.read_pickle(path)
    frame = _normalize_index(frame)          # 既有 P-021 逻辑
    rec = self._compact(name, frame)          # 见下
    _PANEL_CACHE[key] = rec
    return rec
```

`_compact`：

- `name`：
  1. 若 `frame` 无 object 列或唯一值 > 2^24 → `kind="raw"`（回退，保证正确性）。
  2. `flat = frame.to_numpy(dtype=object).ravel()`；`codes, uniques = pd.factorize(flat, sort=False)`。
  3. `st_lut = np.array(["ST" in str(u) for u in uniques], bool)`；`del_lut = np.array(["退" in str(u) for u in uniques], bool)`。
  4. `codes_f = codes.astype(np.float32); codes_f[codes < 0] = np.nan; codes_f = codes_f.reshape(frame.shape)`。
  5. `del frame, flat, codes`；`gc.collect()`。
  6. `kind="name"`，`data=codes_f`，`aux=(uniques, st_lut, del_lut)`。
- **峰值边界（P3）**：`del/gc` 降低的是解码后的**常驻**；单面板解码瞬时（frame 567 MB + flat/codes ≈134 MB + codes_f 34 MB）仍约 0.7 GB，计入 M-6 一次性高水位。
- `suspend`：
  1. 若任一列 `pd.api.types.is_bool_dtype` → `kind="raw"`（DESIGN P2-5）。
  2. `mask = frame.astype(object).eq("S").to_numpy(dtype=bool)`；`missing = frame.isna().to_numpy(dtype=bool)`。
  3. `del frame`；`gc.collect()`；`kind="suspend"`，`data=(mask, missing)`。
- 其余（close/high/low/open/volume/adj）：`kind="float"`，`data=frame`（float64 保持）。

#### 3.1.3 首次加载顺序（DESIGN P1-2）

`build` 开头先预读并紧凑化 `name`、`suspend`，再读 `close` 与其余 float 面板：

```python
for n in ("name", "suspend"):
    self._read_panel(n)
close_rec = self._read_panel("close")
...
```

#### 3.1.4 `_slice` 快路径（统一返回 `(data, aux)`）

```python
@staticmethod
def _slice(rec, index, codes):
    """所有 kind 统一返回 (data, aux)：
    float/raw → (DataFrame, None)
    name      → (DataFrame(float32 codes), (uniques, st_lut, del_lut))
    suspend   → ((mask, missing), None)
    """
    if rec is None:
        return None, None
    idx = pd.Index(codes)
    full = rec.index.equals(index) and rec.columns.equals(idx)
    if rec.kind in ("float", "raw"):
        data = rec.data if full else rec.data.reindex(index=index, columns=idx)
        return data, None
    if rec.kind == "name":
        if full:
            codes_f = rec.data
        else:
            codes_f = _take_codes(rec.data, rec.index, rec.columns, index, idx)
        return (pd.DataFrame(codes_f, index=index, columns=idx, copy=False),
                rec.aux)
    # suspend
    if full:
        return (rec.data[0], rec.data[1]), None
    return (_take_bool(rec.data[0], rec.index, rec.columns, index, idx, False),
            _take_bool(rec.data[1], rec.index, rec.columns, index, idx, True)), None
```

- `_take_codes`：按行列位置 `np.ix_`；缺失行/列填 `np.nan`（码缺失）；返回 ndarray。
- `_take_bool(mask, ..., fill)`：缺失填 `fill`（mask→False、missing→True）。
- 全量命中时 float/raw 返回原 DataFrame 同对象；name 返回包装同一 `codes_f` 数组的新 DataFrame（`copy=False`）；suspend 返回原 `(mask, missing)` 同对象。

#### 3.1.5 `build` 传参

- float 面板：`df, _ = self._slice(rec, index, codes)`；`df.to_numpy(dtype=float)`。
- name：
  - `kind="name"`：`name_df, aux = self._slice(name_rec, index, codes)`；传 `name=None, name_codes=name_df, name_st_lut=aux[1], name_del_lut=aux[2]`。
  - `kind="raw"`（回退）：`name_df, _ = self._slice(...)`；传 `name=name_df, name_codes=None`。
- suspend：
  - `kind="suspend"`：`(mask, missing), _ = self._slice(...)`；传 `suspend=None, suspend_mask=mask, suspend_missing=missing`。
  - `kind="raw"`（含 bool 列）：`suspend_df, _ = self._slice(...)`；传 `suspend=suspend_df, suspend_mask=None`，由 builder 走原 `_suspend_mask`。
- 无面板：对应参数保持 `None`。
- `close` 记录用 `_panel_df/_panel_columns`；`codes_found` 等逻辑不变。
- `meta/diagnostics` 键与值不变。

### 3.2 `backtest/tradability_inputs.py`

#### 3.2.1 签名（DESIGN §5.1）

```python
def build_tradability_inputs(
    close, high, low, open_, volume, suspend, name,
    adj=None, list_date=None, policy=None, st_overrides=None,
    limit_up=None, limit_down=None, ref=None,
    name_codes=None, name_st_lut=None, name_del_lut=None,
    suspend_mask=None, suspend_missing=None,
):
```

#### 3.2.2 快路径

- `_frame`：
  ```python
  if (df is not None and df.index.equals(index)
          and df.columns.equals(columns)
          and isinstance(fill, (float, np.floating)) and np.isnan(fill)
          and (df.dtypes == np.float64).all()):
      return df
  ```
  其余原逻辑。**负例**：`fill=0`/`fill=""`、int/float32/object dtype、行列不一致 → 必须走原路径（`test_p022_frame_fastpath_negative`）。
- `_panel`/`_normalize_panel`：对齐且**全 float64** → 直接 `to_numpy()`（视图）；其他 dtype 走 `_panel` 原逻辑。

#### 3.2.3 name 紧凑路径

```python
if name_codes is not None:
    raw = name_codes.reindex(index=index, columns=columns) \
        if not (name_codes.index.equals(index)
                and name_codes.columns.equals(columns)) else name_codes
    name_missing = raw.isna().to_numpy()
    filled = raw.ffill().to_numpy(dtype=np.float32)
    valid = np.isfinite(filled)
    if valid.any():
        idx = np.where(valid, filled, 0).astype(np.int32)
        if int(idx[valid].max()) >= len(np.asarray(name_st_lut)):
            raise ValueError("name_st_lut 长度不足")
        if int(idx[valid].max()) >= len(np.asarray(name_del_lut)):
            raise ValueError("name_del_lut 长度不足")
    else:
        idx = np.where(valid, filled, 0).astype(np.int32)
    is_st = np.zeros(valid.shape, bool)
    is_delisting = np.zeros(valid.shape, bool)
    if valid.any():
        is_st[valid] = np.asarray(name_st_lut)[idx[valid]]
        is_delisting[valid] = np.asarray(name_del_lut)[idx[valid]]
else:
    # 现行 object 路径（逐列 str 判断）保持不变
```

- **先切片后 ffill**：`reindex` 在 `ffill` 之前；窗口首日不继承窗口外名称。
- LUT 长度校验：`len(lut) == max(idx)+1` 不强制；越界会在 `idx[valid]` 时报 `IndexError`，改为显式 `ValueError`（校验 `idx.max() < len(lut)`）。
- `missing_fields`：见 §3.2.5。

#### 3.2.4 suspend 紧凑路径

```python
if suspend_mask is not None:
    suspend_a = np.asarray(suspend_mask, dtype=bool)
    suspend_missing = np.asarray(suspend_missing, dtype=bool)
    if suspend_a.shape != (T, N) or suspend_missing.shape != (T, N):
        raise ValueError(...)
else:
    suspend_a, suspend_missing = _suspend_mask(suspend, index, columns)
```

#### 3.2.5 `missing_fields` 修正

```python
if name_missing_cells > 0 or (name is None and name_codes is None):
    missing_fields.append("name")
if suspend_missing_cells > 0 or (suspend is None and suspend_mask is None):
    missing_fields.append("suspend")
```

#### 3.2.6 其余不变

- `prev/ref/pct/limits/one_word/no_limit/meta/diagnostics` 逻辑逐行保留；只替换数据来源。
- `TradabilityInputs` 字段顺序/默认值不变。

### 3.3 `backtest/tradability.py`

#### 3.3.1 `_pct_row`（单源）

```python
def _pct_row(codes, st_row, del_row, date_str):
    """单日规则百分比；返回 (pct_row, gap_row)。"""
    N = codes.shape[0]
    pct = np.full(N, np.nan)
    gaps = np.zeros(N, dtype=bool)
    state = codes * 2 + (np.asarray(st_row, bool) & ~np.asarray(del_row, bool)).astype(int)
    for raw in np.unique(state):
        code = int(raw)
        if code < 0:
            gaps[state == code] = True
            continue
        value = rule_pct_or_nan(_BOARD_NAMES[code // 2], bool(code % 2), date_str)
        mask = state == code
        if np.isfinite(value):
            pct[mask] = value
        else:
            gaps[mask] = True
    return pct, gaps
```

- `_pct_matrix` 改为先算 `codes`，再逐日调用 `_pct_row` 堆叠；输出与原实现逐位一致（INV-15）。
- `apply` 中：
  ```python
  codes = np.array([_BOARD_CODES.get(str(b), -1) for b in board], dtype=int)
  ...
  if limit_up is None:
      pct_row, _ = _pct_row(codes, st_mat[t], del_mat[t],
                            _as_date_str(dates[t]))
      up, down, unk = compute_limits(prev_close[t], pct_row, ref=ref_t)
      unk = unk | ~np.isfinite(pct_row)
  else:
      up, down = limit_up[t], limit_down[t]
      unk = ~np.isfinite(up) | ~np.isfinite(down)
  ```
- **ref 不变**：`ref` 提供时按行取；否则整幅 `_ref_from_adj`（P1-1）。
- **限价表分支（P1-2）**：仅当 `limit_up is None` 时计算 `pct_row` 并 `unk |= ~np.isfinite(pct_row)`；`limit_up is not None` 时保持 `pct_mat=None`、不并 pct 未知，只按外部限价表行判定。

#### 3.3.2 apply 其余

- `target_all`/`effective`/diagnostics/report 逻辑不变。
- 移除 `pct_mat = _pct_matrix(...)` 的整幅分配与 `pct_mat[t]` 取值。

### 3.4 `backtest/engine.py`

```python
effective = effective_long
for t in range(self.n_dates):
    effective[t] += np.minimum(positions[t], 0.0)
```

- 不修改 `positions`；`effective_long` 为 apply 返回的新数组。
- 其余 `turnover = compute_turnover(effective)` 与块构造不变。

### 3.5 `backtest/factor_metrics.py`

```python
def compute_turnover(positions):
    if positions.shape[0] < 2:
        return np.array([])
    dtype = positions.dtype
    turnover = np.empty(positions.shape[0] - 1, dtype=dtype)
    buf = np.empty(positions.shape[1], dtype=dtype)
    for t in range(1, positions.shape[0]):
        np.subtract(positions[t], positions[t - 1], out=buf)
        np.abs(buf, out=buf)
        turnover[t - 1] = 0.5 * np.sum(buf)
    return turnover
```

- `buf`/`turnover` 与输入同 dtype（float32 入参不会被升到 float64）；`positions` 契约仍为 2D ndarray。
- 输入 `positions` 不修改；结果与旧实现逐位一致（INV-12）。

### 3.6 `backtest/parallel_runner.py`

```python
worker_args = [
    ({fn: factor_data[fn] for fn in chunk},
     price_data, fwd, config, self.tradability_spec)
    for chunk in chunks
]
```

- `_run_worker` 签名不变；`factor_names` 即 chunk。
- `_run_serial` 复用同一 `worker_args`，行为一致。
- 空 chunk → `{}`，worker 返回 `{}`（既有行为）。

### 3.7 `scripts/verify_tradability_closeout.py`

- CLI：`--data-root`、`--panel-dir market_data`、`--out out/tradability_closeout.json`、`--only u7,u8,r3`。
- `u7_coverage(dates, codes, ...)`：按 loader 同口径（eligible = finite(close) & ~suspend；prev 排除 t=0）逐月输出 `{month, days, high_low, open, prev, eligible_cells, mode}` + `worst` + `below_099`。
- `u8_mismatch(close, price_close)`：`count_nonzero(~isclose(inputs.close, price_close, equal_nan=True))`；默认 `price_close` 由 `stock_close.pkl` 转置（同源基线），支持 `--price-panel` 指定外部源。
- `r3_sensitivity(...)`：生成 `mom20/rev5/vol20` 三因子，`FakeDL` + `FactorBacktestEngine`（off/on），输出 turnover 均值/漂移/crowding/alert/health Δ/combined Δ/ICIR-LS 一致性。
- 输出 JSON 键集合固定；函数可被测试导入（`build_report(...)`）。

### 3.8 版本/文档

- 6 处版本锚点改 3.10.1。
- CHANGELOG 新增 v3.10.1 条目（内存布局/执行路径优化；U-7/U-8/R-3 裁决；逐位不变）。
- PROGRESS P-022 行回填；PROJECT_STATUS 路线图 + §2。

---

## 4. 接口契约

| 接口 | 契约 |
|---|---|
| `TradabilitySpec.build(dates, codes)` | 返回 `(inputs|None, meta)`；`meta` 13 键不变；上下文字段不变 |
| `build_tradability_inputs(...)` | 旧 13 位置参数兼容；新增 5 个可选关键字 |
| `TradabilityInputs` | 字段顺序/类型不变；数组允许为缓存视图（只读约定） |
| `apply_tradability_with_diagnostics` | 签名/返回不变；`report` 9 键、diagnostics 键集合不变 |
| `compute_turnover` | 签名/返回不变；逐位一致 |
| `_run_worker(args)` | 6 元组不变；`factor_data` 可为本 chunk 子集 |

---

## 5. 兼容性与回退

| 项 | 兼容策略 |
|---|---|
| 旧调用 `build_tradability_inputs` | 新参数默认 None → 走原路径 |
| `name`/`suspend` 特殊面板 | 含 bool 列/唯一值过多 → 回退 `kind="raw"`，行为不变 |
| 缓存视图被下游修改 | 只读约定 + INV-9；如需写，调用方先 copy |
| 回退点 | A1 可单独回退 loader；A2 builder 参数独立；A3/A4 为局部代码，可逐文件回退；脚本/版本无运行时耦合 |

---

## 6. 错误场景

| # | 场景 | 处置 |
|---|---|---|
| E-1 | `name_codes` 形状非 `(T,N)` | `ValueError` |
| E-2 | `name_st_lut/name_del_lut` 非一维或长度不足 | `ValueError` |
| E-3 | `suspend_mask` 与 `suspend_missing` 未成对 | `ValueError` |
| E-4 | `_PanelRecord.kind` 未知 | `ValueError` |
| E-5 | name 唯一值 > 2^24 | 回退 `kind="raw"` + `logger.warning` |
| E-6 | `compute_turnover` T<2 | 返回空数组（既有） |
| E-7 | `_pct_row` 未知板块 | `codes=-1` → gap（既有） |
| E-8 | 空 chunk | 返回 `{}`（既有） |

---

## 7. INV 实施映射

| INV | 落点 | 测试 |
|---|---|---|
| INV-1 | 默认路径未改 | TP6-11 + 全量 |
| INV-2 | 紧凑 loader/builder 输出 | `test_p022_report_meta_bitwise` |
| INV-3 | 未改键集合 | 既有键断言 |
| INV-4 | 新参数尾部可选 | `test_p022_builder_legacy_positional` |
| INV-5 | §3.2.3 | `test_p022_name_codes_equiv`、`test_p022_name_window_carry` |
| INV-6 | §3.2.4 | `test_p022_suspend_state_equiv` |
| INV-7 | 无新依赖 | AST + pyproject |
| INV-8 | §3.6 | `test_p022_parallel_payload_subset` + 串并行 |
| INV-9 | 只读 | `test_p022_inputs_immutable` |
| INV-10 | M-1/M-3 | CHECKLIST §6 |
| INV-11 | 未改 | 既有 |
| INV-12 | §3.5 | `test_p022_turnover_bitwise` |
| INV-13 | M-6 | CHECKLIST §6 |
| INV-14 | bool 面板回退 | `test_p022_suspend_bool_path_unchanged` |
| INV-15 | §3.3.1 | `test_p022_pct_row_bitwise` |

---

## 8. 测试矩阵与红→绿计划

### 8.1 新增/修改测试（`tests/test_tradability_p022.py`）

| 用例 | 断言 |
|---|---|
| `test_p022_name_codes_equiv` | 随机 fixture（含 NaN/ST/退）→ 紧凑 vs object 路径 `is_st`/`is_delisting`/`name_missing_cells` 全等 |
| `test_p022_name_window_carry` | 窗口首个日期前有名称；紧凑路径窗口首日不继承（与 object 切片路径一致） |
| `test_p022_suspend_state_equiv` | object `S/R/None` → mask/missing 全等；`suspend_missing_cells` 相等 |
| `test_p022_suspend_bool_path_unchanged` | bool 面板 + 缺列 → `kind="raw"`，`test_p021_d5_suspend_reindex_dtype` 行为不变 |
| `test_p022_slice_identity` | 全量命中 `_slice` 返回 `is` 同对象（float/raw）；name 的 codes 数组同对象；suspend 的 `(mask, missing)` 同对象 |
| `test_p022_slice_contract` | 所有 kind 均返回 `(data, aux)`；缺失行列填充（codes→NaN、mask→False、missing→True）|
| `test_p022_frame_no_copy` | `np.shares_memory(inputs.high, cache_array)` 为 True |
| `test_p022_frame_fastpath_negative` | `fill=0/""`、int/float32/object、行列不一致 → 不命中快路径 |
| `test_p022_cache_compact` | name `float32`、suspend bool；无 object 大列 |
| `test_p022_report_meta_bitwise` | 固定 fixture 的 `report/meta/diagnostics/turnover` 与 3.10.0 基线字面量逐键相等 |
| `test_p022_turnover_bitwise` | 随机 T×N（含 NaN/Inf、T=1、N=1）新老实现 `np.array_equal(equal_nan=True)` |
| `test_p022_pct_row_bitwise` | 随机 board/ST/退/日期：`_pct_matrix` 与逐行 `_pct_row` 全等（含 gap） |
| `test_p022_pct_limit_table_branch` | `limit_up` 提供时不计算 pct、不并 pct unknown；报告与 3.10.0 一致 |
| `test_p022_missing_fields_compact` | 紧凑 name/suspend 路径不误加 `missing_fields`；真缺失仍追加 |
| `test_p022_parallel_payload_subset` | monkeypatch executor 捕获 args：`factor_data` 键集合 == chunk |
| `test_p022_inputs_immutable` | 二次 build 前后缓存抽样哈希不变 |
| `test_p022_builder_legacy_positional` | 13 个位置参数调用结果与关键字调用一致 |
| `test_p022_builder_errors` | E-1~E-4：形状/LUT 一维/LUT 长度/成对/未知 kind 均 `ValueError` |
| `test_p022_turnover_int_input` | 非浮点入参 → float64 输出，与旧实现逐位一致 |
| `test_p022_pct_row_independent` | `rule_pct_or_nan` 逐格旧口径独立复核 `_pct_matrix`（含 unknown/gap） |
| `test_p022_worker_payload_summary_equal` | chunk 子集 vs 全量 `_run_worker` summary 逐位（DataBridge 替身，不依赖外部包） |
| `test_p022_parallel_serial_equal` | 单因子串行 vs `run_parallel(n_workers=1)` summary 逐位（缺 `Factor_Trading_v3_0` 时跳过） |
| `test_p022_name_unique_fallback` | 唯一值 >2^24 → `kind="raw"`（E-5） |
| `test_p022_script_schema` | mock 小数据根 → JSON 含 `u7/u8` 键集合（`r3` 需全量数据根） |

### 8.2 红→绿顺序

| 步 | 红 | 绿 |
|---|---|---|
| A1 | 新增 loader 用例：`_PanelRecord` 不存在 / `_slice` 非 same object | 紧凑缓存/快路径用例通过 |
| A2 | builder 新参数 `TypeError` | 等价/逐位用例通过 |
| A3 | `_pct_row` 不存在 / turnover 新实现未接线 | `pct/turnover` 对拍通过 |
| A4 | payload 用例捕获到完整 dict | 子集断言通过；串并行相等 |
| A5 | 版本锚点 3.10.0 | 6 锚点 3.10.1；CHANGELOG |

### 8.3 基线抓取（Step 9 第一件事）

在**未改任何代码**前，对 4 个固定 fixture 运行引擎并 dump `report/meta/diagnostics/turnover`：

| # | fixture | 覆盖 |
|---|---|---|
| F-1 | 8×4 全“普通”、suspend 全 NaN、无 limit | 基础路径 |
| F-2 | ST 名称 + ffill（含首日 NaN） | name/ST 派生 |
| F-3 | suspend `S` + `R` + None | 停牌语义 |
| F-4 | `stk_limit_partial` + bse（2020-07-27 前后）+ unknown board | 限价表/规则 gap |

将 4 组字面量写入 `tests/golden/p022_baseline.json`（或测试内常量），改后逐键断言（INV-2）。

---

## 9. Review 记录（Step 6）

> 独立只读子代理（general-purpose，只读约束），2026-11-23。裁决 **PASS_WITH_FIXES（2×P1 / 5×P2 / 4×P3）**，全部处置。

| # | 级别 | 发现 | 处置 |
|---|---|---|---|
| 1 | P1 | `_slice` 返回形态不自洽（name 返回 ndarray、float 返回裸 DF） | §3.1.4 统一为 `(data, aux)`；name data 为 DataFrame |
| 2 | P1 | apply 漏 `limit_up is not None` 分支，会把 pct unknown 并进外部限价路径 | §3.3.1 代码块补 `if limit_up is None / else` |
| 3 | P2 | 未写 `kind="raw"` 回退传参 | §3.1.5 补 name/suspend raw 分支 |
| 4 | P2 | 单 fixture 锁不住 INV-2 | §8.3 扩为 4 个 fixture（基础/ST/S/R/limit+bse） |
| 5 | P2 | 测试矩阵缺 slice 契约、快路径负例、missing_fields、limit 分支 | §8.1 增 4 例 |
| 6 | P2 | turnover 固定 float64 缓冲会让 float32 入参不逐位 | §3.5 改为输入 dtype 保持 |
| 7 | P2 | `idx.max()` 空数组抛错 | §3.2.3 增加 `valid.any()` 守卫 |
| 8 | P3 | `np.factorize` 笔误 | §2.1 已改 `pd.factorize` |
| 9 | P3 | `_frame` dtype 判定需更严格 | §3.2.2 明确全 float64 + 负例 |
| 10 | P3 | `del/gc` 不降解码瞬时峰 | §3.1.2 补峰值边界说明（M-6） |
| 11 | P3 | `_pct_row` 每行算 gap 后丢弃 | 实施时提供 `return_gaps=False` 轻量参数 |

> 复审确认 PASS：紧凑 name 逐格等价、先切片后 ffill 正确；`_frame` fill/dtype 不会误命中；turnover 对 float64 的 NaN/Inf/N=1/T=1 与非连续行逐位一致；engine 原地累加语义不变；worker 子集/空 chunk/重名安全；首次加载顺序不影响 `test_p021_loader_cache` 读计数。

### 9.1 Step 9 实施记录（2026-11-23）

- **红**：`tests/test_tradability_p022.py` collection error（`ImportError: cannot import name '_pct_row'`，同时缺 `_PanelRecord`/`_PANEL_CACHE`）。
- **绿**：**23 passed / 1 skipped**；分批 A1 9 / A2 3 / A3 5 / A4 4+1s / A5 2（明细见 CHECKLIST §12.1）。
- **基线抓取**：改前 B0 写入 `tests/golden/p022_baseline.json`（F1_basic / F2_st / F3_suspend / F4_limit_bse），改后 4 组逐键相等（`test_p022_report_meta_bitwise`）。
- **E1 内存读数**（全样本 1475×5688，2020-01-02~2026-01-30）：cache deep 1140.1 → **430.7 MB**；build 22.43 → **15.64 s**；build tracemalloc 2585.1 → **1249.4 MB**；build 后 RSS 2201.3 → **1345.4 MB**；worker RSS 3348 → **2463.5 MB**；隔离基线引擎（`tradability=None`）540.1 MB。
- **门禁裁决**：M-3 未达 1024 MB → 按 DESIGN §8 停止并回报；用户裁决 **P-022 有条件通过 + 新开 P-023**（不在本批引入分块 apply）。
- **K-5**：默认工件 SHA `82728CE103D49AF211DD12DE87D9784040FC909C83FB7A88D521AF30A89B2548` 复跑逐位一致。
- **版本**：3.10.1 六锚点 + CHANGELOG。

### 9.2 Step 10 ADD 审计记录（2026-11-23）

- 独立只读子代理（异构基座）裁决 **PASS_WITH_FIXES**，质量门 **2/5 档位 C**；**2×P1 / 5×P2 / 3×P3** 共 10 条发现全部处置（逐条见 CHECKLIST §12.2）。
- 关键修复：`compute_turnover` 非浮点 dtype、LUT 一维/成对校验、脚本 `--price-panel`（U-8 外部面板口径）、独立旧口径 pct 断言、chunk 子集 summary 等价用例、CHECKLIST 统计与证据名订正、CHANGELOG v3.10.1。
- 最终全量回归（最终代码状态）：**2227 passed / 35 skipped / 0 failed**（933.81 s）。

---

**Review 签字**: Step 6 独立只读复审 PASS_WITH_FIXES（2×P1/5×P2/4×P3 全部处置） 日期: 2026-11-23；§9.1/§9.2 为 Step 9/10 补记。

---

## 10. 实施步骤（Step 9 执行顺序）

| 步骤 | 文件 | 内容 | 测试 |
|---|---|---|---|
| B0 | — | 抓取逐位基线（§8.3） | 无 |
| B1 | loader | `_PanelRecord` + 紧凑 name/suspend + 加载顺序 + `_slice` 快路径 | `test_p022_*`（loader 组） |
| B2 | builder | 5 个可选参数 + `_frame` 快路径 + `missing_fields` | 等价/逐位组 |
| B3 | tradability | `_pct_row` + apply 按行 | pct 对拍 |
| B4 | engine/factor_metrics | effective 按行 + turnover 单行缓冲 | turnover 对拍 + TP6-11 |
| B5 | parallel_runner | worker 子集 | payload/串并行 |
| B6 | script + 版本 | 脚本 + 6 锚点 + CHANGELOG | 脚本 schema + 版本测试 |
| B7 | 全量 | 定向 + 全量回归 + 内存探针 | CHECKLIST §6 |

---

## 11. 派生需求与未决项

**派生需求（实施中新增）**：

- **DR-1** `_PanelRecord` 具体类型：DESIGN 只要求“统一记录”；实施用 `__slots__` 轻量类。
- **DR-2** `_slice` 统一返回 `(data, aux)`（复审 P1-1）：float/raw→(DataFrame, None)、name→(DataFrame, aux)、suspend→((mask, missing), None)。
- **DR-3** name 唯一值上限 2^24：float32 精确整数上限；超限回退 raw。
- **DR-4** `_take_codes/_take_bool` 缺失填充规则：codes→NaN、mask→False、missing→True。
- **DR-5** `_pct_row(..., return_gaps=False)`：apply 路径省 gap 分配。
- **DR-6** 脚本 `FakeDL`：复用 P-021 测试的替身模式；不依赖外部 `factor-trading-v3`。
- **DR-7** 版本 3.10.1：patch；若 Step 9 发现行为变更则升 3.11.0 并回报。

**未决项**：

- **U-2** ~~M-3 实测（Step 9）~~ → **已由 Step 9 回答**：worker RSS 3348 → 2463.5 MB，未达 ≤1024 MB；失败门禁触发，用户裁决“收口 + 开 P-023”（离线 name 紧凑缓存 + worker 日期分片）。
- **U-1** `stk_limit` 外部一致率（token 后）。
- **U-3** 非标准 `price_data` mismatch 样例（条件触发）。
- **U-4** 健康度/漂移阈值重标定（本批不重标定；R-3 实测 0/3 告警翻转）。

---

**Review 签字**: Step 6 复审 PASS_WITH_FIXES（2026-11-23）；Step 9/10 记录已回填（§9.1/§9.2）。
