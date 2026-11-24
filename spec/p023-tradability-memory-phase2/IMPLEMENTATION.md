# 实施文档：P-023 tradability worker 内存第二阶

---
id: p023-tradability-memory-phase2-IMPLEMENTATION
type: design
version: 1.2
status: verified
date: 2026-11-24
depends: [p023-tradability-memory-phase2-DESIGN, p023-tradability-memory-phase2-RESEARCH]
upstream: null
---

> **Feature**: P-023（离线 name 紧凑缓存 + worker 日期分片 + M-2/M-3 复测）
> **创建日期**: 2026-11-24
> **状态**: verified（v1.0 → Step 6 独立复审 PASS_WITH_FIXES（2×P1/6×P2/5×P3）→ v1.1 处置 → v1.2 收口；记录见 §9）
> **Spec 步骤**: Step 5-6
> **基于设计**: [DESIGN.md](./DESIGN.md)（v1.4 verified）
> **基于调研**: [RESEARCH.md](./RESEARCH.md)（v1.1 verified）
> **档位**: **T1** ｜ **包版本**: 3.10.1 → **3.11.0** ｜ **新依赖**: 无

---

## 1. 实施概述

四组改动，全部向后兼容：

1. **离线 name 缓存**：`stock_name_compact.npz` 写入/读取/校验/回退 + 迁移脚本。
2. **plan/分块构建**：`TradabilitySpec.build_plan()` → `TradabilityPlan`；逐块**读 pkl（不缓存 float 面板）**、构造 `TradabilityInputs`、聚合 meta/diagnostics。
3. **分块 apply**：`TradabilityApplyState` + `t_offset/target_prev/is_last_chunk/return_state`；跨块 pending/locked/w_prev_long/turnover_prev。
4. **worker/引擎接线**：`FactorBacktestEngine(tradability_plan=)` 流式分支；`_run_worker` 默认 plan（60 日块）。

**默认路径零改动**：`tradability_inputs=None`、`tradability_spec=None`、`TradabilitySpec.build()`（整幅）均保持 3.10.1 行为。

---

## 2. 版本与依赖

- 包版本 **3.11.0**，6 锚点：`pyproject.toml:7`、`__init__.py:58`、`config_v2.py:371`、`reporting.py:40`、`tests/test_fix3_version_unification.py:34`、`tests/test_backtest/verify_fix3_manual.py:21`。
- 零新增运行时依赖；仅用 `numpy`/`pandas`/`os`/`json`/`zipfile`（npz 读取由 numpy 内部完成）。
- Python ≥3.9 语法；不使用 `X | None` 类型注解。

---

## 3. 模块实施

### 3.1 `backtest/tradability_loader.py`

#### 3.1.1 常量与 npz 读写

```python
NAME_COMPACT_FORMAT_VERSION = 1
NAME_COMPACT_NAME = "stock_name_compact.npz"
NAME_COMPACT_KEYS = ("format_version", "codes", "index", "columns",
                     "uniques", "st_lut", "del_lut",
                     "source_mtime", "source_size")

def build_name_compact_payload(frame) -> dict:
    """object name DataFrame → npz payload（codes/index/columns/uniques/LUT/源元数据）。"""

def load_name_compact(path, pkl_path=None) -> Optional[_PanelRecord]:
    """读取并校验 npz；失败返回 None（调用方回退 pkl）。"""

def write_name_compact(path, frame, source_path) -> dict:
    """原子写：临时文件 → round-trip 校验 → os.replace；返回统计。"""
```

- `codes` 由 `_compact_panel` 已有路径生成（float32 + NaN）；`index/columns/uniques` 用 `np.asarray([str(x) ...], dtype=str)`，宽度自动 `<U maxlen`。
- 读取时**还原标签类型**：`index = pd.DatetimeIndex(pd.to_datetime([str(x) for x in z["index"]]))`、`columns = pd.Index([str(x) for x in z["columns"]])`、`uniques = tuple(str(x) ...)`；否则 `_slice/_take_codes` 的 `Index.equals` 失败。
- `source_mtime = os.stat(source_path).st_mtime`、`source_size = st_size`。
- 读取校验见 DESIGN §4.1；`NpzFile` 用 `with` 并 `.copy()`。
- 失败 warning 前缀固定 `name_compact_fallback:`（便于测试/运维检索）。

#### 3.1.2 `_read_panel` 改造

```python
def _read_panel(self, name):
    if name == "name":
        rec = load_name_compact(self._name_compact_path(), self._name_pkl_path())
        if rec is not None:
            _PANEL_CACHE[key] = rec
            return rec
    ...  # 现有 pkl 路径
```

- 新增 `_name_compact_path()`：`self.name_compact_path or os.path.join(data_root, panel_dir, NAME_COMPACT_NAME)`。
- npz 成功时**不再解码 pkl**；失败走现有路径。
- `_PANEL_CACHE` 键不变；npz record 与 pkl record 同结构。

#### 3.1.3 `TradabilitySpec` 新字段

```python
name_compact_path: Optional[str] = None
max_dates_per_chunk: Optional[int] = 60
```

- `max_dates_per_chunk` 仅被 worker/plan 使用；`build()` 不读取。
- 校验：非 None 时须为 `int >= 1`（`build_plan` 入口）。

#### 3.1.4 `TradabilityChunk` / `TradabilityPlan`

```python
@dataclass(frozen=True)
class TradabilityChunk:
    start: int
    stop: int
    index: pd.DatetimeIndex

@dataclass
class ChunkResult:
    inputs: TradabilityInputs
    counts: dict
    prev_close0: Optional[np.ndarray]   # 本块首行应使用的上一日 close（s>0）
    close_last: np.ndarray              # 本块末行 close（供下一块）
    name_last: np.ndarray               # 本块 ffill 后末行名称码

class TradabilityPlan:
    index, codes, policy, mode, coverage, chunk_days
    meta, diagnostics                   # finalize() 后填充（dict）
    def iter_chunks(self): ...
    def build_chunk(self, chunk) -> ChunkResult
    def finalize(self): ...             # 汇总 _agg + 静态 flags → meta/diagnostics
```

`build_plan` 流程：

1. `index = DatetimeIndex(dates)`；`codes` 去重保持顺序；`codes` 全部不在 close 面板 → `ValueError`。
2. 读 `list_date`；读 suspend 一次紧凑；name 用 npz/pkl 记录；**stk_limit 若配置则一次加载**（`load_stk_limit(path, index, codes)`，逐块切片；内存随表大小增加，U-5 披露）。
3. **覆盖率预扫**：逐块 `_read_panel_chunk` close/high/low/open；累加 `_cov_counts`（含 prev lookback，s=0 行不计）。**该计数只用于覆盖率/mode，不再与 chunk counts 相加**。
4. `_resolve_mode` 解析；`policy = replace(...)`；记录 `mode_requested/degrade_reason/codes_not_found`。
5. 预计算 `no_limit_global`（DESIGN §4.3）与 `first_delisting_pos`。
6. `mode=="off"` → 4 键 off meta；`iter_chunks()` 仍可迭代（引擎走旧 turnover）。

`_read_panel_chunk(name, index, codes)`：

```python
frame = _normalize_index(pd.read_pickle(path))
src_cols = frame.columns          # 首块用于 codes 存在性校验
out = frame.reindex(index=index, columns=pd.Index(codes))
del frame                         # 逐面板释放，避免 5 个整幅同时驻留
return out, src_cols
```

- **不写 float 面板缓存**（name/suspend 紧凑记录仍复用 `_PANEL_CACHE`）；name 走 `_take_codes`；suspend 走 `_take_bool`。
- 每次只读一个面板，切片后立即释放整幅；调用方用完即释放。

`build_chunk`：

- 计算 `prev_close0/adj_prev0/name_carry/no_limit_override`（DESIGN §4.3）；stk_limit 切片。
- 读 close/high/low/open（adj 若存在；**volume 不读，传 `volume=None`** → builder 生成 NaN 块，apply 不消费，显式披露）。
- `build_tradability_inputs(..., return_counts=True)`；返回 `ChunkResult`。
- 更新 `self._agg`：**只累加 name/suspend/ref_fallback/rule_gap/one_word/limit_table/st_* 等计数；覆盖率键不累加**（由 `_cov_counts` 唯一来源）。
- `_agg` 额外键：`rule_gap_bse_cells`（gap & board=="bse"）、`limit_table_duplicate_rows`、`st_stock_days`、`delisting_stock_days`、`no_limit_cells`、`adj_missing_days`、`st_date_unverified`。

`finalize()`：

- 生成 **meta 13 键** + **diagnostics 全键**（与 `build()` 尾部逐键一致），包括：
  - `rule_gap_reason`（bse gap → `"neeq_pre_select"`；否则 `"unknown_board"`/None）；
  - `mode_requested/degrade_reason/codes_not_found/coverage`；
  - `limit_table_source/limit_table_missing_cells/limit_table_duplicate_rows`；
  - `adj_source/data_tier/missing_fields/price_basis_detail`（adj 缺失时 `adj_source="none"`、`data_tier="D1"`、`missing_fields += ["adj"]`）；
  - 比率用 `_cov_counts` 全局分子/分母。
- 幂等：重复调用返回同一 dict；`plan.meta/diagnostics` 缓存。
- **不调用/不修改 `build()`**；实现为 plan 侧独立函数，INV-9 对拍锁定。

### 3.2 `backtest/tradability_inputs.py`

#### 3.2.1 builder 新参数

```python
def build_tradability_inputs(close, high, low, open_, volume, suspend, name,
                             adj=None, list_date=None, policy=None,
                             st_overrides=None, limit_up=None,
                             limit_down=None, ref=None,
                             name_codes=None, name_st_lut=None,
                             name_del_lut=None, suspend_mask=None,
                             suspend_missing=None, *,
                             prev_close0=None, adj_prev0=None,
                             name_carry=None, no_limit_override=None,
                             return_counts=False):
```

- **既有 19 个位置参数槽（前 7 个必填；`adj` 第 8 位、`ref` 第 14 位、`suspend_missing` 第 19 位）与全部关键字调用不变**；新参数 keyword-only（第 20 位起）。
- `volume=None` → `_frame(volume, ..., np.nan, float)` 生成全 NaN 块；**apply 不消费 volume**，故流式路径不读该面板（语义零影响，显式披露）。
- `prev[0] = prev_close0`（提供时）。
- `_ref_from_adj(prev, adj, prev_adj=adj_prev0)`。
- name 紧凑：`name_missing` 先算；`raw` 副本第 0 行 NaN→carry；再 ffill。
- `no_limit`：提供 override 时 `no_limit = override & ~suspend_a`；否则原逻辑。
- `return_counts=True`：返回 `(inputs, counts)`；counts 键：

```
eligible_cells, high_low_covered, open_covered, prev_eligible, prev_covered,
name_missing_cells, name_missing_days, suspend_missing_cells,
suspend_missing_days, ref_fallback_cells, ref_fallback_days,
rule_gap_cells, rule_gap_days, one_word_up, one_word_down,
limit_table_missing_cells, st_date_unverified,
no_limit_cells, st_stock_days, delisting_stock_days, adj_missing_days,
last_filled_name  # ndarray，供 plan carry
```

- 默认 False → 返回 `(inputs, meta)`（逐位不变）。

#### 3.2.2 `build()` 零改动

- 不重排/不抽取尾部；仅新增分支（默认参数为 None/False 时走原路径）。
- INV-2 用 P-022 4 fixture 锁定。

### 3.3 `backtest/tradability.py`

#### 3.3.1 `_ref_from_adj`

```python
def _ref_from_adj(prev_close, adj, prev_adj=None):
    ...
    if prev_adj is not None:
        # 与 out[1:] 相同的 ok/exdiv/_to_cents 逻辑，只为第 0 行
```

- `prev_adj=None` → `out[0]=NaN`（旧行为逐位）。

#### 3.3.2 apply 状态

```python
@dataclass
class TradabilityApplyState:
    pending: np.ndarray
    locked_until: np.ndarray
    w_prev_long: np.ndarray
    turnover_prev: Optional[np.ndarray] = None   # 引擎维护
```

```python
def apply_tradability_with_diagnostics(
    ..., policy=None, adj=None, is_delisting=None, no_limit=None,
    ref=None, limit_up=None, limit_down=None, *,
    state=None, target_prev=None, t_offset=0,
    is_last_chunk=True, return_state=False):
```

- 初始化：`pending = state.pending.copy()`（或 zeros）、`locked_until = state.locked_until.copy()`、`w_prev = state.w_prev_long.copy()`。
- `target_all[0] = target_prev if t_offset else 0.0`。
- 循环内 `t_global = t_offset + t`；`locked_until` 用 `t_global`。
- 末尾：`state.pending/locked_until/w_prev_long` 更新；`turnover_prev` 原样透传（由引擎写）。
- `report["carried"]`：`is_last_chunk` 才计算，否则 0。
- 返回：`return_state=True` → **4 元组 `(effective_long, report, diag, state)`**；否则 3 元组（现状，逐位不变）。`mode=off` 由引擎短路，不调用 apply。

### 3.4 `backtest/engine.py`

#### 3.4.1 构造

```python
def __init__(self, data_loader, config=None, fwd_returns=None,
             tradability_inputs=None, tradability_plan=None):
    if tradability_inputs is not None and tradability_plan is not None:
        raise ValueError("tradability_inputs 与 tradability_plan 不能同时提供")
    self._tradability_plan = tradability_plan
    if tradability_plan is not None:
        self._validate_tradability_plan(tradability_plan)
```

- 校验 plan 的 `n_dates/n_stocks` 与引擎一致；`mode`/policy 合法。

#### 3.4.2 `_evaluate_factor`

```python
if self._tradability_plan is not None:
    return self._evaluate_factor_streaming(factor_name)
...  # 现有路径
```

`_evaluate_factor_streaming`：

1. IC/ICIR/decay/hit-rate/LS/spread：**复制现有实现**（factor/fwd 整幅、hstack padding）。
2. `state = TradabilityApplyState(zeros, full(-1), zeros)`
3. `if plan.mode == "off":` 按块 `_build_positions` → `compute_turnover`（块首边界行取上一块末行正部，s=0 不追加）并拼接；不挂块；输出长度 T-1。
4. 否则逐块：
   - `pos_chunk = self._build_positions(factor[s:e])`；
   - `target_prev = np.clip(pos_prev_row, 0)`；
   - `res = plan.build_chunk(chunk)`（`ChunkResult`）；`inputs_chunk = res.inputs`；
   - `prev_close_chunk`：s=0 为 NaN 首行 + `inputs_chunk.close[:-1]`；s>0 首行为 `res.prev_close0`，其余 `inputs_chunk.close[:-1]`；
   - `apply(np.clip(pos_chunk,0,None), prev_close_chunk, ..., state=state, target_prev=target_prev, t_offset=s, is_last_chunk=(e==T), return_state=True)` → `(eff_long, report, apply_diag, state)`；
   - 合成 `effective = eff_long + np.minimum(pos_chunk, 0.0)`；
   - turnover：s>0 先追加边界行（`state.turnover_prev`），再 `compute_turnover(effective)`；`state.turnover_prev = effective[-1].copy()`；
   - mismatch 分块累加（`~isclose(inputs_chunk.close, self._close[s:e])`）；
   - `report/apply_diag` 累加；`pos_prev_row = pos_chunk[-1].copy()`；`del res, inputs_chunk, pos_chunk, effective` 释放块。
5. 末块后**调用一次 `plan.finalize()`**（幂等，缓存）；`meta = plan.meta`；`diag = dict(plan.diagnostics)` + apply_diag 累加 + `{"close_mismatch_cells": mismatch}`；`limit_table_missing_cells>0 → limit_table_source="stk_limit_partial"`（沿用现状 P1-① 规则）；`report` 保留 9 键；`tradability_block` 结构与现状一致。

#### 3.4.3 默认路径

- `tradability_plan=None` → 原 `_evaluate_factor` 一行不改。

### 3.5 `backtest/parallel_runner.py`

```python
if spec is not None:
    if getattr(spec, "max_dates_per_chunk", None) is None:
        inputs, _ = spec.build(cd, cs); plan = None
    else:
        plan = spec.build_plan(cd, cs); inputs = None
    engine = FactorBacktestEngine(
        dl, config=config, fwd_returns=shared_fwd,
        tradability_inputs=inputs, tradability_plan=plan)
```

- `_run_worker` 签名（6 元组）不变。
- 缺面板/缺码异常上抛（现有契约）。

### 3.6 `scripts/build_name_compact_cache.py`

```
--data-root (必填) --panel-dir (默认 market_data) --out (默认派生路径)
--force  --dry-run
```

流程：读 pkl → `build_name_compact_payload` → `write_name_compact`（临时 + round-trip + replace）→ 打印 JSON（源/目标大小、shape、唯一名、耗时）。
幂等：目标存在且 mtime/size 匹配 → `{"status":"up-to-date"}` exit 0。
错误：exit 2（参数/读失败/校验失败）。

### 3.7 `scripts/verify_tradability_memory.py`

```
--data-root --panel-dir --out out/tradability_memory_p023.json
--dates-limit (默认全样本) --codes-limit (默认全部) --chunk-days 60
--skip-spawn  --child
```

- `--child`：内部入口（父进程以同解释器 `subprocess.Popen([sys.executable, __file__, *args, "--child"])` 启动），执行 M-1/M-2 路径后 `returncode=0`；不递归 spawn。
- `--skip-spawn`：m3=null；默认执行 M-3。

输出键：

```json
{"meta": {"data_root","panel_dir","n_dates","n_codes","chunk_days","run_at","run_index","mode"},
 "m1": {"plan_s","build_all_chunks_s","total_s"},
 "m2": {"tracemalloc_peak_mb"},
 "m3": {"peak_rss_mb","returncode"},
 "m4": {"name_mb","suspend_mb","total_mb"},
 "m6": {"rss_after_mb"},
 "rows": [{"chunk":0,"dates":60,"build_s":0.08,"apply_s":null}]}
```

- M-3 通过 `subprocess` 启动同脚本 `--child`，父进程 psutil 50 ms 采样；`--skip-spawn` 时 m3=null。
- 不新增项目依赖；`psutil` 缺失 → exit 2 并提示（开发证据工具）。
- **M-1 冷读风险**：首次运行含 OS 文件缓存冷启动（pkl 102 MB×多面板）；判定以**第二次运行** `total_s` 为准（JSON 记录 `run_index`），冷读读数仅保留在运行日志中（不写入 JSON），不作为失败依据。
- `apply_s` 恒为 null（apply 由 M-3 子进程覆盖）；`rows` 只记录分块 build 秒。

### 3.8 版本/文档

- 6 锚点 → 3.11.0；`CHANGELOG.md` v3.11.0；PROGRESS/PROJECT_STATUS 收口（Step 10）。

---

## 4. 接口契约

| 接口 | 契约 |
|---|---|
| `TradabilitySpec.build()` | 返回 `(inputs, meta)`；行为与 3.10.1 逐位一致 |
| `TradabilitySpec.build_plan()` | 返回 plan；缺码 ValueError；off 时 plan.mode="off" |
| `TradabilityPlan.build_chunk()` | 返回 `ChunkResult(inputs, counts, prev_close0, close_last, name_last)`；inputs 只含本块 T×N |
| `build_tradability_inputs` | 旧 19 位置参数槽（前 7 必填）+ 全部关键字兼容；新参数 keyword-only |
| `apply_tradability_with_diagnostics` | 默认返回 3 元组；`return_state=True` → 4 元组；既有 18 位置参数槽（前 11 必填，`policy`…`limit_down` 为 12–18 位）不变；新参数 keyword-only |
| `FactorBacktestEngine` | 新增第 5 参数 `tradability_plan=None`；旧 4 参数调用不变 |
| `_run_worker` | 6 元组签名/返回契约不变 |

---

## 5. 兼容性与回退

| 场景 | 行为 |
|---|---|
| 默认路径 | 零改动 |
| `max_dates_per_chunk=None` | worker 走 `spec.build()` 整幅 |
| npz 失败 | 回退 pkl；warning |
| plan 异常 | worker 上抛；不静默降级 |
| 删除 npz | 回退 pkl |
| 旧调用 apply/builder | 返回元组/位置参数不变 |

---

## 6. 错误场景

| # | 场景 | 期望 |
|---|---|---|
| E-1 | npz 缺键/形状错/版本不符/mtime 过期 | 回退 pkl + warning（不抛） |
| E-2 | npz 字符串含非 str | 回退 pkl + warning |
| E-3 | `codes` 全部不在 close 面板 | `ValueError`（plan 与 build 一致） |
| E-4 | `max_dates_per_chunk<=0` | `ValueError` |
| E-5 | `tradability_inputs` 与 `tradability_plan` 同时提供 | `ValueError` |
| E-6 | plan 形状与引擎不符 | `ValueError` |
| E-7 | 迁移脚本 pkl 缺失/不可写 | exit 2，不产生半文件 |
| E-8 | npz 读取期间 SafeExit/OSError | 回退 pkl + warning |

---

## 7. INV 实施映射

| INV | 落点 |
|---|---|
| INV-1 | engine 默认分支未改；TP6-11 |
| INV-2 | builder 默认参数；`build()` 未改；P-022 fixture |
| INV-3 | `_evaluate_factor_streaming` 复用 IC/LS 原实现；测试块长参数化 |
| INV-4 | 块组装 9 键；plan meta 13 键；diagnostics 原键 |
| INV-5 | npz round-trip + builder 对拍 |
| INV-6 | `load_name_compact` 返回 None → pkl |
| INV-7 | `write_name_compact` 原子 + 幂等 |
| INV-8 | 无新依赖；AST 检查 |
| INV-9 | `_finalize_plan_meta` vs `build()` 逐键 |
| INV-10 | `TradabilityApplyState` + 边界测试 |
| INV-11 | `name_carry` + `name_missing` 顺序 |
| INV-12 | 分块 mismatch/turnover 求和 |
| INV-13 | 证据脚本 |
| INV-14 | plan 只读切片；哈希测试 |
| INV-15 | 临时文件 + 正式名分离 |

---

## 8. 测试矩阵与红→绿计划

### 8.1 新增 `tests/test_tradability_p023.py`

| 用例 | 断言 |
|---|---|
| `test_p023_npz_roundtrip` | codes/index/columns/uniques/LUT 全等；`allow_pickle=False` |
| `test_p023_npz_loader_equiv` | npz 与 pkl 路径 `is_st`/`is_delisting`/missing 全等 |
| `test_p023_npz_fallback` | 缺失/损坏/版本/mtime 过期 → pkl（4 例参数化） |
| `test_p023_migrate_idempotent` | 二次运行 `up-to-date`；pkl 字节不变 |
| `test_p023_migrate_dry_run` | 不写文件 |
| `test_p023_plan_meta_equal` | 小块/全样本 plan meta+diagnostics == `build()` |
| `test_p023_chunk_lookback` | `prev_close0/adj_prev0` 与整幅第 s 行逐位 |
| `test_p023_name_carry` | 跨块 ST/退市；首块全 NaN |
| `test_p023_no_limit_cross_chunk` | IPO 5 日窗口 + 退市首日 `no_limit_cells` 对拍 |
| `test_p023_apply_state_boundary` | pending/locked/target/carried 逐位 |
| `test_p023_turnover_boundary` | 块长 {1,2,7,60} turnover 与整幅逐位；s=0 长度 T-1 |
| `test_p023_stream_engine_equal` | 4 fixture × 块长 → report/meta/diag/turnover/IC/LS 逐位 |
| `test_p023_plan_off` | off meta 4 键 + 旧 turnover |
| `test_p023_worker_stream_equal` | `_run_worker` 流式 summary == 整幅（DataBridge 替身） |
| `test_p023_errors` | E-3~E-6 |
| `test_p023_script_schema` | 证据脚本 JSON 键 |
| `test_p023_npz_atomic` | round-trip 失败/写入中断 → 无正式文件、无 `*.tmp-*` 残留；pkl 字节不变 |
| `test_p023_cache_immutable` | 同一 `TradabilitySpec` 连续两次 `build_plan/build_chunk`：`_PANEL_CACHE` 与调用方数组哈希不变（INV-14） |
| `test_p023_ref_fallback_tier` | adj 含缺格 → ref fallback；plan `data_tier`/diagnostics 与整幅一致（Step 10 审计 P1） |
| `test_p023_key_freeze` | 流式 `report` 9 键 / `meta` 13 键 / `diagnostics` 键集合 == 整幅路径（不增不减） |

### 8.2 红→绿顺序

| 步 | 红 | 绿 |
|---|---|---|
| A1 | npz 读写/迁移 API 不存在（ImportError/AttributeError） | 格式/回退/幂等用例通过 |
| A2 | plan/chunk API 不存在 | lookback/meta 对拍通过 |
| A3 | apply 新参数 TypeError | 状态/边界/turnover 通过 |
| A4 | engine 无 `tradability_plan` 参数 | 4 fixture 流式逐位通过 |
| A5 | worker 未接线 / 证据脚本缺失 | worker 等价 + 脚本 schema |

### 8.3 基线

- 直接复用 P-022 `tests/golden/p022_baseline.json`（4 fixture）；不新增基线文件。
- 全样本默认 SHA `82728CE1…` 与 `panel_hash dfcc4e1d…` 作为 INV-1 外部锚点。

---

## 9. Review 记录（Step 6）

**复审方式**：独立只读子代理（不共享本会话推理），对照 DESIGN v1.3 / RESEARCH v1.1 / 现有代码锚点逐条核验。
**裁决**：v1.0 **PASS_WITH_FIXES**（2×P1 / 6×P2 / 5×P3）→ v1.1 处置 → **v1.2 verified**。

### 9.1 P1（阻断）

| # | 问题 | 处置 | 落点 |
|---|---|---|---|
| P1-① | `finalize_meta` 缺 `rule_gap_reason`/`coverage`/mode 字段/`limit_table_duplicate_rows`，且未定义 finalize 调用时机 | 新增 `plan.finalize()`（幂等、缓存 `meta/diagnostics`）+ 完整键表；引擎末块后调用一次 | §3.1.4、§3.4.2 |
| P1-② | 覆盖率预扫与 `build_chunk` 重复累加 | 明确 `_cov_counts` 为覆盖率**唯一来源**，chunk `counts` 不累加覆盖率键 | §3.1.4 |

### 9.2 P2

| # | 问题 | 处置 | 落点 |
|---|---|---|---|
| P2-1 | `stk_limit` 逐块重复加载 | 一次 `load_stk_limit`，逐块切片；内存随表大小（U-5 披露） | §3.1.4 step 2 |
| P2-2 | adj 完全缺失时 D1 语义未写 | finalize 键表：`adj_source="none"`、`data_tier="D1"`、`missing_fields += ["adj"]`、`ref=prev` | §3.1.4 |
| P2-3 | `prev_close_row` 来源不清 | 改由 `ChunkResult(prev_close0, close_last, name_last)` 返回 | §3.1.4、§3.4.2 |
| P2-4 | npz 标签类型还原缺失 | 读取时还原 `DatetimeIndex`/`Index`/`tuple`，否则 `Index.equals` 失败 | §3.1.1 |
| P2-5 | 逐面板整幅驻留 | `_read_panel_chunk` 切片后 `del frame`，每次只驻留一个面板 | §3.1.4 |
| P2-6 | 缺 INV-14 哈希/原子性/键冻结用例 | 新增 `test_p023_cache_immutable`、`test_p023_npz_atomic`、`test_p023_key_freeze` | §8.1 |

### 9.3 P3

| # | 问题 | 处置 | 落点 |
|---|---|---|---|
| P3-1 | 旧位置参数数量表述不准 | 改为“19 个位置参数槽（前 7 必填；`adj` 第 8、`ref` 第 14、`suspend_missing` 第 19）”；apply 为 18 槽（前 11 必填） | §3.2.1、§4 |
| P3-2 | `volume=None` 语义未披露 | 生成全 NaN 块；apply 不消费 → 流式不读该面板 | §3.2.1 |
| P3-3 | `return_state` 4 元组与 off 分支未写 | 明确 4 元组顺序；off 由引擎短路、不调用 apply | §3.3.2、§3.4.2 |
| P3-4 | 证据脚本缺子进程入口 | 增 `--child`（不递归 spawn）与 `--skip-spawn` | §3.7 |
| P3-5 | M-1 冷读风险 | 以第二次运行读数判定；JSON 记 `run_index` | §3.7 |

### 9.4 复审结论

- 与 DESIGN D1–D9 / INV-1~15 一一对应，无新增未覆盖决策。
- 默认路径零改动边界成立：`build()` 主体、`_evaluate_factor` 旧分支、apply 3 元组均未改。
- **PASS**：进入 Step 7 CHECKLIST。

---

## 10. 实施步骤（Step 9 执行顺序）

| 步 | 文件 | 内容 | 测试 |
|---|---|---|---|
| B0 | — | 确认基线（P-022 fixture、默认 SHA） | 无 |
| B1 | loader | npz 读写/校验/回退 + `build_name_compact_payload` | A1 |
| B2 | script | 迁移脚本 + 证据脚本骨架 | A1/A5 |
| B3 | inputs | builder 关键帧参数 + counts | A2 |
| B4 | loader | plan/chunk/聚合 | A2 |
| B5 | tradability | state/offset/target/carried | A3 |
| B6 | engine | `tradability_plan` 流式分支 | A4 |
| B7 | runner | worker 接线 | A5 |
| B8 | 版本/文档 | 6 锚点 + CHANGELOG | 版本测试 |
| B9 | 全量 | 定向 + 全量回归 + M-1/M-2/M-3 | CHECKLIST §6 |

---

## 11. 派生需求与未决项

**派生需求（预计，实施中补充）**：

- **DR-1** `_finalize_plan_meta` 与 `build()` 尾部重复：为保证 `build()` 零改动，接受重复并以 INV-9 对拍锁定。
- **DR-2** plan 的 `counts` 携带 `last_filled_name`（ndarray），避免 plan 自行重算 name ffill。
- **DR-3** `no_limit_global` 以“请求 dates 位置”为锚点（非全数据日历），与 builder 原语义一致。
- **DR-4** `mode=off` 时 plan 仍迭代块以生成旧 turnover；不构造 inputs。
- **DR-5** 证据脚本 `psutil` 仅开发期使用，不写入 pyproject。

**未决项**：

- **U-1** npz 默认文件名/格式版本（DESIGN U-1，Step 3 已倾向）。
- **U-2** M-3 未达时追加节省（DESIGN U-2）。
- **U-3** 默认块长（DESIGN U-3）。
- **U-4** `mode=auto/off` 分块交互（DESIGN U-4）。
- **U-5** `stk_limit` 分片（DESIGN U-5）。
