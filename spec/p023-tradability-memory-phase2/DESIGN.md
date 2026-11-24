# 设计文档：P-023 tradability worker 内存第二阶

---
id: p023-tradability-memory-phase2-DESIGN
type: design
version: 1.4
status: verified
date: 2026-11-24
depends: [p023-tradability-memory-phase2-RESEARCH]
upstream: null
---

> **Feature**: P-023（离线 name 紧凑缓存 + worker 日期分片 + M-2/M-3 复测）
> **创建日期**: 2026-11-24
> **状态**: verified（v1.0 → Step 4 复审 FAIL（4×P1）→ v1.1 → 复审 FAIL（2×P1）→ v1.2 → **PASS_WITH_FIXES** → v1.3 处置 P2/P3 → v1.4 Step 8 一致性对齐；记录见 §11）
> **Spec 步骤**: Step 3-4
> **基于调研**: [RESEARCH.md](./RESEARCH.md)（v1.1 verified；§4.5 为 Step 4 复审补充读数）
> **批次档位**: **T1**（Layer-1：`backtest/` + `scripts/` + `tests/` + 数据根派生文件）
> **包版本**: 3.10.1 → **3.11.0**（minor：新增可选流式路径与离线缓存脚本；默认路径零变更）

---

## 1. 目标与边界

1. `stock_name.pkl`（567 MB 解码常驻）→ 34.5 MB 紧凑 `.npz`（离线派生、可回退）；保留 pkl 回退。
2. worker 启用 tradability 时：**逐块读面板（不保留 float 面板整幅缓存）+ 60 交易日分块 build/apply/turnover**；M-3 目标 ≤1024 MB（同进程实测 514.7 MB，spawn 估算 ≈730 MB）。
3. 默认路径与启用整幅路径的 `report` 9 键 / `meta` 13 键 / `diagnostics` / `turnover` / IC / LS **逐位不变**。

**职责外**：float 面板离线格式迁移；`PipelineBacktestRunner` 整幅路径改造；B 批收益层；`stk_limit` 外部一致率。

---

## 2. 设计决策

| # | 决策 | 依据 |
|---|---|---|
| D1 | 新增 `stock_name_compact.npz`（未压缩、无 pickle）；loader 优先读、校验失败回退 pkl | RESEARCH §4.1 |
| D2 | 幂等迁移脚本 `scripts/build_name_compact_cache.py`（临时文件 + `os.replace`，不修改 pkl） | RESEARCH R-4/R-5 |
| D3 | `TradabilitySpec` 增加 plan/chunk API；**流式 plan 不缓存 float 面板**（name/suspend 紧凑记录除外），每块按标签读 pkl | RESEARCH §4.5 |
| D4 | builder 增加关键帧参数（`prev_close0`/`adj_prev0`/`name_carry`/`no_limit_override`）+ `return_counts`；`build()` 主体**零改动** | RESEARCH §4.2 + 复审 P1-2/P1-3/P2-11 |
| D5 | apply 增加 `state`/`target_prev`/`t_offset`/`is_last_chunk`；状态拆 `w_prev_long`（apply）与 `turnover_prev`（含空头腿） | RESEARCH §4.5 + 复审 P1-1/P2-8 |
| D6 | 引擎新增 `tradability_plan=` 流式分支：positions/apply/mismatch/turnover 按块；**IC/LS 保持整幅与现有 hstack** | RESEARCH §4.2/§4.3 + 复审 P1-1 |
| D7 | worker 在 `spec` 且 `max_dates_per_chunk` 非 None 时走 plan 流式；`build()` 仍为整幅 | RESEARCH F-11 |
| D8 | 块长默认 **60 交易日**；`max_dates_per_chunk=None` 显式关闭 worker 流式 | RESEARCH U-3 |
| D9 | 预算：M-1 ≤30 s、M-2/M-3 ≤1024 MB；失败按 U-2，不放宽 | RESEARCH §4.5/§8 R-3 + P-022 DESIGN §8 |

---

## 3. 改动文件

| 文件 | 改动 |
|---|---|
| `backtest/tradability_loader.py` | npz 读取/校验/回退；`TradabilityPlan`/`TradabilityChunk`/`ChunkResult`；`build_plan/iter_chunks/build_chunk/finalize`；`_read_panel_chunk`（无缓存）；`name_compact_path` / `max_dates_per_chunk` 字段 |
| `backtest/tradability_inputs.py` | builder 关键帧参数 + `return_counts`；plan 侧独立聚合器（**不改 `build()` 主体**） |
| `backtest/tradability.py` | `TradabilityApplyState`；apply 状态/偏移/块首 target；`_ref_from_adj(prev_adj=)` |
| `backtest/engine.py` | `tradability_plan=` 构造参数与 `_evaluate_factor_streaming`；分块 mismatch；IC/LS 路径不变 |
| `backtest/parallel_runner.py` | `_run_worker` 在 `spec` 下构建 plan（默认 60 日块） |
| `scripts/build_name_compact_cache.py`（新） | 离线迁移 CLI |
| `scripts/verify_tradability_memory.py`（新） | M-1/M-2/M-3 可复现证据 |
| `tests/test_tradability_p023.py`（新） | 格式/回退/分块逐位/预算 schema |
| 版本 6 锚点 + `CHANGELOG.md` | 3.11.0 |

---

## 4. 详细设计

### 4.1 D1 离线 name 紧凑缓存

**文件**：默认 `<data_root>/<panel_dir>/stock_name_compact.npz`；`TradabilitySpec.name_compact_path` 可覆盖。

**键与 dtype**：

| 键 | dtype | 含义 |
|---|---|---|
| `format_version` | int32 0-d | 当前 = 1 |
| `codes` | float32 (T, N) | factorize 码；缺失 = NaN |
| `index` | `<U{maxlen}` (T,) | 日期字符串 |
| `columns` | `<U{maxlen}` (N,) | 代码字符串（保留原标签） |
| `uniques` | `<U{maxlen}` (K,) | 唯一名称（factorize 顺序） |
| `st_lut` / `del_lut` | bool (K,) | `"ST" in name` / `"退" in name` |
| `source_mtime` | float64 0-d | pkl `st_mtime` |
| `source_size` | int64 0-d | pkl 字节数 |

- 字符串宽度按实际 `max(len)` 生成（`<U`），不写死；写入前断言全部为 `str`。
- 读取：`with np.load(path, allow_pickle=False) as z:` 内 `.copy()` 各数组；`NpzFile` 不得逃逸。
- 校验：`format_version==1`；`codes.ndim==2 & float32`；行/列长度匹配；LUT 一维且长度 == `len(uniques)`；有限码 ∈ `[0, K)`；若 pkl 存在则 `source_size==st_size` 且 `|source_mtime-st_mtime|<=1e-3`。
- 任一失败 → `logger.warning("name_compact_fallback: ...")` + pkl 路径；不抛错。成功 → `_PanelRecord("name", ...)` 入 `_PANEL_CACHE`。
- **标签独立**：name index/columns 与 close 不同形（RESEARCH §2.2），仍按标签 `_take_codes`。

### 4.2 D2 迁移脚本

```
python scripts/build_name_compact_cache.py \
  --data-root E:\Ashare_data --panel-dir market_data \
  [--out ...\stock_name_compact.npz] [--force] [--dry-run]
```

- 幂等：目标存在且 `source_size/mtime` 匹配 → `up-to-date`，exit 0（`--force` 重建）。
- 原子：同目录 `*.tmp-<pid>` → round-trip 校验 → `os.replace`；失败删临时文件、不触碰 pkl。
- 可回退：删除 npz 即回到 pkl；脚本从不写 pkl。
- 退出码：0 成功/已最新；2 参数或校验失败。

### 4.3 D3 plan 与逐块读面板

```python
plan = spec.build_plan(dates, codes)      # mode/coverage 全局解析；不缓存 float 面板
for chunk in plan.iter_chunks():          # 默认 60 交易日
    res = plan.build_chunk(chunk)         # ChunkResult(inputs, counts, prev_close0, close_last, name_last)
meta = plan.finalize()                    # 幂等；13 键 + diagnostics 由 counts 同源生成
```

**逐块读**：`_read_panel_chunk(name, index_chunk, columns)`：

1. `pd.read_pickle(stock_<name>.pkl)` → `_normalize_index` → `reindex(index=chunk_dates, columns=codes)` → 返回副本；**不写 float 面板缓存**（name/suspend 紧凑记录例外）；调用方用完即释放。
2. name：从 npz 记录 `_take_codes` 切片（缓存 34 MB）。
3. suspend：plan 初始化时读一次并紧凑为 `(mask, missing)`（16 MB），逐块切片。
4. `list_date`：plan 初始化时读一次（小），全局派生 `no_limit` 位置。

**plan 预扫（覆盖率）**：逐块读 close/high/low/open，累加：

- `eligible_cells` = `isfinite(close) & ~suspended`；
- `high_low_covered` = `isfinite(high) & isfinite(low) & eligible`；
- `open_covered` = `isfinite(open) & eligible`；
- `prev_eligible/prev_covered`：块 `[s,e)` 的 prev = close[s-1:e-1]，**s=0 行置 False**；s>0 时首行用上一块末行 close（lookback）。
- 由全局计数得 `high_low/open/prev` 覆盖率 → `_resolve_mode` 解析一次。

**关键帧**：

| 参数 | 取值 |
|---|---|
| `prev_close0` | `close_full[s-1]`（s>0；plan 预扫保留上一块末行 close） |
| `adj_prev0` | `adj_full[s-1]`（s>0 且 adj 存在） |
| `name_carry` | 上一块 **ffill 后末行**的名称码（s>0；plan 维护 `last_filled_name`；上一块全 NaN 时自然为 NaN） |
| `no_limit_override` | plan **全局**预计算后切片：① 每个 `list_date` 在**请求 dates 序列**中的前 5 个位置（list_date 查找保持“精确键优先 + `_norm_code` 回退（首见优先）”；`no_limit_source="list_date"` 当至少一只股票命中，否则 `"delisting_only"`）；② 每股票**首个退市日**位置；再 `&= ~suspend` |

- `st_overrides`：`TradabilitySpec.build()` **从不传入**该参数（loader L220-L231），故 Spec 路径恒为 `st_calibration_source="none"`、`st_date_unverified=0`；plan 直接继承该口径，不引入额外 carry。
- **缺码校验**：plan 在覆盖率计算前先做 `codes` 与 close 面板列的匹配；全部不在 → `ValueError("请求代码均不在 stock_close 面板")`（与 `build()` L125-L126 一致），**不得**静默降级为 off。

**build_chunk**：调用 `build_tradability_inputs(..., 上述参数, return_counts=True)`；返回 chunk inputs + counts。**mode=off**：plan 预扫仍读 close/high/low/open 以计算 coverage，随后返回 `None` + 4 键 off meta（`mode/mode_requested/degrade_reason/coverage`，与 `build()` 的 off 返回逐键一致）；worker 引擎在 `plan.mode=="off"` 时按块计算 positions/turnover、**不挂 tradability 块**（等价于整幅引擎 L312-L315 的旧 turnover 路径）。

**最终 meta/diagnostics 聚合**：

| 类别 | 键 | 规则 |
|---|---|---|
| 比率 | `high_low_coverage/open_coverage/prev_close_coverage` | 全局分子/分母 |
| 天数/计数 | `name_missing_*`、`suspend_missing_*`、`ref_fallback_*`、`rule_gap_*`、`one_word_*`、`limit_table_missing_cells`、`st_stock_days`、`delisting_stock_days`、`no_limit_cells`、`adj_missing_days`、`st_date_unverified` | 逐块求和 |
| 静态 | `board_counts`、`unknown_codes`、`no_limit_source`、`st_calibration_source`、`price_basis`、`rounding_basis`、`adj_source`、`data_tier`、`bias_direction`、`missing_fields`、`price_basis_detail`、`unknown_policy`、`one_word_disabled`、`mode` | 由全局 flags/计数派生 |
| 引擎侧 | `close_mismatch_cells` | 逐块 `count_nonzero(~isclose(chunk.close, price_close[s:e], equal_nan=True))` 求和 |
| apply 侧 | `report` 9 键、`diagnostics` 的 `exec_*`/`high_*`/`limit_table_source` | 逐块求和；`limit_table_source` 按全局缺失数定 partial；`carried` 取末块 |

- `missing_fields`：`name` 判定用原始 `name_missing_cells`（不含 carry），并保持“compact 或 raw 任一提供”条件。
- **`build()` 零改动**：上述聚合器为新增私有函数，仅 plan 使用；用全样本对拍锁定其与 `build()` 的 13 键/诊断逐键一致。

### 4.4 D4 builder 关键帧参数

`build_tradability_inputs(..., *, prev_close0=None, adj_prev0=None, name_carry=None, no_limit_override=None, return_counts=False)`：

1. `prev` 构造后 `prev[0] = prev_close0`（若提供）。
2. `_ref_from_adj(prev, adj, prev_adj=adj_prev0)`：`prev_adj` 非 None 时补 `out[0]`，**完整复刻** `ok/exdiv/|ratio-1|>1e-6/_to_cents` 逻辑；默认 None 时 `out[0]=NaN`（旧行为）。
3. name 紧凑路径：`name_missing = raw.isna()` **先于 carry 计算**；随后在 `raw` 副本上把第 0 行 NaN 码替换为 `name_carry`，再 `ffill`。object 回退路径同理（字符串 carry）。
4. `no_limit`：若提供 `no_limit_override`（块形状 bool），直接作为种子并在末尾 `&= ~suspend_a`；否则走现有 list_date/退市首日逻辑（旧行为）。
5. `st_date_unverified`：保持现状；Spec 路径无 `st_overrides` → 0。
6. `return_counts=True` 返回 `(inputs, counts)`；默认 False 返回 `(inputs, meta)`（现状）。

### 4.5 D5 分块 apply 与 turnover

```python
@dataclass
class TradabilityApplyState:
    pending: np.ndarray        # (N,)
    locked_until: np.ndarray   # (N,) int，绝对 t
    w_prev_long: np.ndarray    # (N,) 多头 effective 上一行（apply 内部用）
    turnover_prev: np.ndarray  # (N,) 多头+空头合成后上一行（turnover 边界用）
```

`apply_tradability_with_diagnostics(..., *, state=None, target_prev=None, t_offset=0, is_last_chunk=True, return_state=False)`：

- `target_all[0] = 0`（`t_offset==0`）或 `target_prev`；其余 `target_all[t]=target_w[t-1]`。
- 循环内 `t_global=t_offset+t`；`locked_until` 比较/赋值用 `t_global`。
- apply 内部只读写 `state.w_prev_long`（与整幅 `w_prev` 同义，保持多头语义）。
- `state=None` → 零初值；返回 4 元组当 `return_state=True`，否则 3 元组（现状）。
- `report["carried"]` 仅 `is_last_chunk=True` 时计算，否则 0。
- **turnover**：引擎在块内先合成 `effective = eff_long + min(positions_chunk, 0)`（与整幅同式）；**仅当 s>0** 追加块首行 `0.5*sum(|effective[0] - state.turnover_prev|)`，再追加块内 `compute_turnover(effective)`（s=0 时整幅 `compute_turnover` 也无边界行，保持 T-1 总长度）；块末由**引擎**更新 `state.turnover_prev = effective[-1].copy()`；`w_prev_long` 由 apply 维护，`turnover_prev` 由引擎维护，二者不得混用。

### 4.6 D6 引擎流式分支

构造：`FactorBacktestEngine(..., tradability_inputs=None, tradability_plan=None)`；同时提供 → `ValueError`。

`_evaluate_factor`：plan 非 None → `_evaluate_factor_streaming`；否则原路径。

**流式流程**：

1. **IC/LS 路径完全不变**（factor/fwd 整幅、`hstack` padding、decay/LS/spread 原样）。
2. 逐块 `[s,e)`：
   - `pos_chunk = self._build_positions(factor[s:e])`；
   - `target_prev = np.clip(pos_prev_row, 0)`（上一块末行；s=0 不用）；
   - `res = plan.build_chunk(chunk)`（`ChunkResult`）；`inputs_chunk = res.inputs`；
   - `prev_close_chunk`：首行取 `res.prev_close0`（s>0；s=0 为 NaN），其余 `inputs_chunk.close[:-1]`（与整幅 `prev_close[1:]=inputs.close[:-1]` 同源）；
   - `apply(..., target_w=np.clip(pos_chunk, 0.0, None), state=state, target_prev=target_prev, t_offset=s, is_last_chunk=(e==T), return_state=True)`；
   - 合成空头腿 → turnover（§4.5，使用 `state.turnover_prev`）；
   - `mismatch += count_nonzero(~isclose(inputs_chunk.close, self._close[s:e], equal_nan=True))`；
   - 累加 report/diag；释放块数组。
3. 末块 `carried`；末块后调用 `plan.finalize()`（幂等）；`meta=plan.meta`；块键与现状同 9 键。
4. **`plan.mode=="off"`**：不调用 build_chunk/apply/mismatch；按块 `positions → compute_turnover`（含跨块首行）并拼接，不挂 tradability 块；与整幅引擎 L312-L315 等价。
5. **默认路径零改动**：`tradability_plan=None` 时走原 `_evaluate_factor`（含 IC hstack）。

### 4.7 D7 worker 接线

```python
if spec is not None:
    if getattr(spec, "max_dates_per_chunk", None) is None:
        inputs, _ = spec.build(cd, cs); plan = None
    else:
        plan = spec.build_plan(cd, cs); inputs = None
    engine = FactorBacktestEngine(..., tradability_inputs=inputs,
                                  tradability_plan=plan)
```

- 6 元组签名不变；缺面板/代码 → `ValueError`（与现状一致）。
- T ≤ 块长（单块）时流式与整幅逐位一致（测试锁定）。

### 4.8 D8 块长与预算口径

| 指标 | 口径 | 预算 | 预期（RESEARCH §4.5） |
|---|---|---|---|
| M-1 | 全样本 `build_plan` 预扫 + 首轮全部分块 build（不含 apply） | ≤30 s | ≈8–10 s（预扫与 build 各读一次面板，约 2× IO） |
| M-2 | 同上过程 tracemalloc peak（**无 float 整幅缓存**；含冷缓存首块 pkl 反序列化瞬态） | ≤1024 MB | ≈500–550 MB |
| M-3 | spawn 子进程 `build_plan + 单因子流式 run` RSS（psutil 50 ms） | ≤1024 MB | ≈730 MB |
| M-4 | 常驻（name npz 34 + suspend 紧凑 16） | ≤500 MB | ≈50 MB（无 float cache） |
| M-5 | 与 3.10.1 固定 fixture 逐位 | 100% | — |
| M-6 | 首次加载高水位（plan 完成后 RSS） | ≤1400 MB（**仅披露，不作为门禁**） | ≈730 MB（与 M-3 同向） |

- 默认块长 60（`TradabilitySpec.max_dates_per_chunk=60`）；`None` 关闭 worker 流式。M-3 >1024 MB 时按 U-2 处置（块长 40/120、多因子块外层循环摊薄 IO），不静默放宽。
- **2× IO 说明**：plan 预扫（close/high/low/open）与 build_chunk（close/high/low/open/adj）各读一次；OS page cache 下仍满足 M-1 ≤30 s，作为已知代价登记（R-6）。

### 4.9 D9 版本与交付

- 包版本 **3.11.0**（minor：新增可选流式路径与离线缓存脚本；默认路径零变更）。
- 6 锚点 + `CHANGELOG.md` v3.11.0。
- 证据：`scripts/verify_tradability_memory.py` → `out/tradability_memory_p023.json`（M-1/M-2/M-3、块长、数据根 mtime、行数）。

---

## 5. 兼容性与回退

| 场景 | 行为 |
|---|---|
| 未启用 tradability | 零改动 |
| 启用 + `max_dates_per_chunk=None` | `spec.build()` 整幅路径，与 3.10.1 逐位一致 |
| 启用 + 流式 | `report/meta/diagnostics/turnover` 与整幅逐位一致（门禁）；单因子 IO/耗时 +2~4 s（块长可调） |
| npz 缺失/过期/损坏 | 回退 pkl，warning；结果与 3.10.1 一致 |
| 删除 npz | 完全回退；无代码改动 |
| 数据根只读 | 可读已有 npz；脚本 exit 2，不影响运行 |

---

## 6. 不变式（INV）

| # | 不变式 | 验证 |
|---|---|---|
| INV-1 | 默认路径逐位不变 | TP6-11 + 默认 SHA |
| INV-2 | 启用整幅路径与 3.10.1 逐位不变 | P-022 4 fixture |
| INV-3 | 流式 == 整幅：`report`/`meta`/`diagnostics`/`turnover`/IC/ICIR/decay/hit_rate/LS/spread 逐位 | 4 fixture × 块长 {1,2,7,60,T} |
| INV-4 | `report` 9 键 / `meta` 13 键 / diagnostics 键集合冻结 | 键集合断言 |
| INV-5 | npz vs pkl name 语义逐格一致 | round-trip + builder 对拍 |
| INV-6 | npz 缺失/过期/损坏 → pkl 结果不变 | 故障注入 |
| INV-7 | 迁移脚本幂等、原子、不写 pkl；删 npz 可回退 | 幂等/`--dry-run`/mock replace |
| INV-8 | 零新增运行时依赖；py3.9/pandas≥2.0/numpy≥1.22 | pyproject diff + AST |
| INV-9 | plan 聚合 meta/diagnostics == `build()`（逐键） | 全样本/小块对拍 |
| INV-10 | 跨块状态（pending/locked_until/target/`w_prev_long`/`turnover_prev`）逐位；多头与合成状态不混用 | 边界专项 + 全样本 |
| INV-11 | name ffill carry 逐位；`name_missing` 取原始 NaN | 跨块 ST/退市用例 |
| INV-12 | mismatch/turnover（含空头腿）分块聚合逐位 | 全样本/构造用例 |
| INV-13 | M-1 ≤30 s；M-2/M-3 ≤1024 MB | 证据脚本 |
| INV-14 | 流式不修改缓存/面板数组 | 二次 plan 前后哈希 |
| INV-15 | npz 临时文件/半成品不可被 loader 读取 | 原子性测试 |

---

## 7. 测试矩阵

| 组 | 用例 | 覆盖 |
|---|---|---|
| npz 格式 | round-trip；`allow_pickle=False`；dtype/宽度/形状校验 | INV-5 |
| npz 回退 | 缺失/损坏/版本不符/mtime 过期 → pkl | INV-6/15 |
| 迁移脚本 | 幂等 skip；`--force`；`--dry-run`；pkl 字节不变 | INV-7 |
| lookback | `prev_close0`/`adj_prev0` 与整幅第 s 行逐位；name carry（含首块全 NaN）；`no_limit_override`（IPO 5 日窗口 + 退市首日）跨块对拍 `no_limit_cells` | INV-9/11 |
| apply 状态 | pending、`locked_until`、target 前移、carried 末块、`w_prev_long` 与 `turnover_prev` 分离；s=0 无边界行（turnover 长度 T-1） | INV-10 |
| 引擎流式 | 4 fixture × 块长 1/2/7/60/T；report/meta/diag/turnover 逐位 | INV-3 |
| 指标 | 流式 vs 整幅 rank/pearson IC、ICIR、decay、hit_rate、LS、spread | INV-3 |
| 聚合 | 全样本 plan meta/diagnostics vs `build()` 逐键；`plan.mode=="off"` 时 4 键 off meta 与旧 turnover；`build_plan` 缺码 ValueError | INV-9 |
| 默认/整幅 | P-022 基线 + TP6-11 | INV-1/2 |
| worker | `_run_worker` 流式 summary == 非流式；缺面板 ValueError；输入 N/board 维度校验 | INV-3/异常 |
| 键冻结 | `report` 9 / `meta` 13 / diagnostics 集合 | INV-4 |
| 依赖/语法 | pyproject 无新增；AST py3.9 | INV-8 |
| 缓存只读 | 二次 plan 前后缓存哈希 | INV-14 |
| 预算 | 证据脚本 JSON 键/阈值/数据根 mtime | INV-13 |

---

## 8. 风险与缓解

| # | 风险 | 缓解 |
|---|---|---|
| R-1 | 块边界语义漂移 | 单块路径与整幅共用 builder/apply；边界专项 |
| R-2 | plan 聚合与 build 不一致 | 新增聚合器对拍 13 键+诊断全键 |
| R-3 | 逐块读 pkl 导致耗时上升 | OS cache；块长可调；多因子块外层循环作为后续优化 |
| R-4 | npz 过期未发现 | mtime/size 校验 + 回退 warning |
| R-5 | 迁移脚本中断 | 临时文件 + `os.replace`；loader 只读正式名 |
| R-6 | 多因子重复读面板 | 记录单因子 +2~4 s；可选块外层循环摊薄 |
| R-7 | 字符串 `dtype` 截断 | 动态 `<U maxlen` + 写入前断言 str |
| R-8 | spawn 开销击穿预算 | M-3 用 P-022 同协议 spawn 实测；预期余量 ≈294 MB |

---

## 9. 未决项

| ID | 判据 | 触发 | 倾向 | 等级 |
|---|---|---|---|---|
| U-1 | npz 默认文件名/格式版本 | Step 3 | `stock_name_compact.npz` / v1 | E1 |
| U-2 | M-3 未达时追加节省 | Step 9 | 块长/多因子块外层 | E1 |
| U-3 | 默认块长 | Step 9 多块长读数 | 60 | E1 |
| U-4 | 流式与 `mode=auto/off` | Step 3 | plan 全局解析；off 不挂块 | E2 |
| U-5 | `stk_limit` 分片 | token/CSV | 一次加载后逐块切片（不重复读 CSV） | E2 |

---

## 10. 被拒方案

| 方案 | 拒绝理由 |
|---|---|
| 仅离线 npz | M-2 1214.4 MB、M-3 spawn 1548.9 MB，均不达 |
| 保留整幅 float 缓存 + 分块 apply | 同进程峰值 981.2 MB，spawn 预估 >1.2 GB，余量不足 |
| 去掉 IC `hstack` | `compute_ic_series` 契约固定 `returns[:,t+1]`，去 padding 会整体错位；保持原样 |
| float 面板离线 npy/mmap | 本批无需（逐块读已 ≈730 MB），且扩大数据根迁移范围 |
| 丢弃 volume 缓存 | apply 未消费，但为契约字段；暂不改 |
| 提高预算/减少 worker | 用户裁决 ≤1 GB；单 worker 峰值不变 |

---

## 11. Step 4 复审记录

### 11.1 v1.0 复审（2026-11-24，独立只读子代理，裁决 FAIL）

| # | 级别 | 发现 | v1.1 处置 |
|---|---|---|---|
| 1 | P1 | IC 去 hstack 差一错误；`compute_long_short_returns` 仍需 padded | **撤销**去 hstack；IC/LS 路径完全保持现状（§4.6-1） |
| 2 | P1 | `no_limit`/`st_date_unverified` 以块内第 0 行为锚点，跨界渗漏 | 新增 `date_positions`（全局交易日位置）与 `st_override_seen` carry（§4.3/§4.4） |
| 3 | P1 | `name_missing` 若在 carry 后计算会改变 meta/tier | 明确 **missing 先算、carry 仅用于 ffill**（§4.4-3） |
| 4 | P1 | M-6 实测 1473.8 MB 与预算矛盾；hstack 节省不成立 | 改为**逐块读面板、不保留 float 整幅缓存**；新增 §4.5 读数（514.7 MB 同进程，spawn ≈730 MB）；M-6 预期同步下降 |
| 5 | P2 | 块首 prev_close 未定义 | 用上一块 inputs.close 末行（§4.6-2） |
| 6 | P2 | prev_close_coverage 分母跨块口径 | 预扫按全局 prev 计数（s=0 首行为 False） |
| 7 | P2 | carry 语义/ref 公式表述不足 | carry = 上一块 ffill 后末行；`_ref_from_adj` 完整复刻（§4.4-2） |
| 8 | P2 | turnover 空头腿未计入跨块 w_prev | 合成后 effective 再存 w_prev（§4.5） |
| 9 | P2 | meta/diagnostics 聚合清单不全 | §4.3 增补 `st_stock_days/delisting_stock_days/no_limit_cells/adj_missing_days/st_date_unverified` 等 |
| 10 | P2 | mode=off/降级路径未定义 | §4.3 明确 off 返回与旧 turnover 路径 |
| 11 | P2 | `build()` 零改动与抽 `_finalize_meta` 冲突 | 保持 `build()` 原样；聚合器仅 plan 使用并对拍 |
| 12 | P2 | 测试矩阵缺 INV-4/8/14 与指标逐位 | §7 已补 |
| 13 | P2 | M-3 余量风险未量化 | 改用逐块读；预期余量 ≈294 MB，spawn 实测门禁 |
| 14 | P3 | 字符串 dtype 写死 `<U9/<U10` 会截断 | 改为动态 `<U maxlen>` + str 断言（§4.1） |
| 15 | P3 | `max_dates_per_chunk` 默认值改变 worker 行为 | 保留默认 60，但明确 `build()` 不受影响、`None` 可关闭；输出逐位门禁 |
| 16 | P3 | `stk_limit` 逐块重复读 CSV | plan 一次加载后切片（§9 U-5） |
| 17 | P3 | 探针未入库 | 证据脚本固化命令/环境/mtime（§4.9） |

### 11.2 v1.1 复审（2026-11-24，同一独立只读子代理，裁决 FAIL：2×P1）

| # | 级别 | 发现 | v1.2 处置 |
|---|---|---|---|
| 18 | P1 | `w_prev` 同时承担多头 apply 与合成 turnover，回灌会污染 pending/锁定 | 拆 `w_prev_long`（apply）与 `turnover_prev`（turnover 边界），明确不得混用（§4.5/§4.6） |
| 19 | P1 | `date_positions` 无法复现全局 IPO 5 日窗口；退市首日仍以块内首行为锚点 | 改为 plan **全局预计算** `no_limit_override`（全局 IPO 位置 + 每股票首个退市日）后切片；builder 仅 `&= ~suspend`（§4.3/§4.4） |
| 20 | P2 | plan 预扫 + build_chunk 2× IO 未登记，M-1 估值偏低 | M-1 改为 ≈8–10 s 并登记 2× IO（§4.8/R-6） |
| 21 | P2 | `st_override_seen` 无触发路径（Spec 不传 `st_overrides`） | 删除该参数；明确 Spec 路径恒 0/"none"（§4.3） |
| 22 | P2 | mode=off 的 meta/引擎路径未定义 | 定义 4 键 off meta 与按块旧 turnover（§4.3/§4.6-4） |
| 23 | P2 | 测试缺 IPO/退市跨块、plan off、维度校验 | §7 已补 |
| 24 | P3 | §3 与 §4.3 对 `build()` 改动的表述矛盾 | 统一为“plan 侧独立聚合器，`build()` 主体零改动”（§3/§4.3） |
| 25 | P3 | RESEARCH “24 块”与 1475/60=25 不符 | RESEARCH §4.5 订正为 25 块 |
| 26 | P3 | M-6 与 M-3 门禁关系不清 | M-6 标注“仅披露、不设门禁”（§4.8） |
| 27 | P3 | worker 默认流式的耗时变化未写入兼容表 | §5 兼容表已补 +2~4 s 说明 |

### 11.3 v1.2 复审（2026-11-24，同一独立只读子代理，裁决 **PASS_WITH_FIXES**）

| # | 级别 | 发现 | v1.3 处置 |
|---|---|---|---|
| 28 | P2 | turnover 块首边界未限定 s>0，会产生 T 行 | §4.5 明确“仅 s>0 追加边界行”，保持 T-1 |
| 29 | P2 | 未写明 `target_w=np.clip(pos_chunk,0)` | §4.6-2 已补 |
| 30 | P2 | `no_limit_override` 锚点/键归一/source 未定义 | §4.3 明确“请求 dates 位置 + 精确键优先/`_norm_code` 首见 + `no_limit_source` 规则” |
| 31 | P2 | `build_plan` 缺码应 ValueError，不得静默 off | §4.3 增缺码校验（与 build L125-L126 一致） |
| 32 | P3 | RESEARCH “96 次读取”与 2× IO 不符 | RESEARCH §4.5 订正为 ≈225 次（预扫 4 + build 5）×25 |
| 33 | P3 | 缺 name carry 首块全 NaN / s=0 / 缺码用例 | §7 已补 |
| 34 | P3 | `turnover_prev` 写入方未明确 | §4.5 明确由引擎在块末写入，apply 不写 |

### 11.4 v1.4 Step 8 文档一致性对齐（2026-11-24）

| # | 级别 | 发现 | 处置 |
|---|---|---|---|
| 35 | P2 | §3/§4.3 写 `finalize_meta(agg_counts)`，与 IMPL `finalize()` 不一致 | 统一为 `plan.finalize()`（幂等）；§3 落 `ChunkResult` |
| 36 | P2 | §4.6 `inputs_chunk, _ = plan.build_chunk()` 与 `ChunkResult` 契约不一致 | 改为 `res = plan.build_chunk(chunk)`；首行 `res.prev_close0`；末块后 `plan.finalize()` |
| 37 | P3 | D4/D5/D6/D9 依据仅引复审/他批，无 RESEARCH 事实编号 | 补 `RESEARCH §4.2/§4.3/§4.5/§8 R-3` |
| 38 | P3 | IMPL §8.1 `npz_fallback` 写“3 例”，场景实为 4 | 改为“4 例参数化” |

---

**Review 签字**: Step 4 独立只读复审 PASS_WITH_FIXES（v1.2，2026-11-24）；v1.3 处置完成；v1.4 Step 8 一致性对齐完成。
