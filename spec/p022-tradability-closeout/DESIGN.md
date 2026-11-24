# 设计文档：P-022 tradability 收口包

---
id: p022-tradability-closeout-DESIGN
type: design
version: 1.2
status: verified
date: 2026-11-23
depends: [p022-tradability-closeout-RESEARCH]
upstream: null
---

> **Feature**: P-022（P-2 内存 / U-7 阈值 / U-8 阈值 / R-3 敏感性）
> **创建日期**: 2026-11-23
> **状态**: verified（Step 3 完成；Step 4 独立只读复审 PASS_WITH_FIXES 已处置，记录见 §12；**v1.2 = Step 10 审计 A-3/A-9 订正**：§4.7 R-3 脚本口径 + §8 M-6 口径对齐）
> **Spec 步骤**: Step 3-4
> **基于调研**: [RESEARCH.md](./RESEARCH.md)（v1.2 verified）
> **批次档位**: **T1**（Layer-1：`backtest/` + `tests/` + `scripts/`）
> **包版本**: 3.10.0 → **3.10.1**（patch；无数值行为变更，仅内存布局/执行路径与文档）

---

## 1. 设计目标

1. **P-2**：把并行 worker 峰值 RSS 从 3348 MB 压到 **≤1024 MB**，且**不改变任何数值结果**（默认路径与启用路径逐位一致）。
2. **U-7**：以 73 个月真实覆盖读数裁决 `min_coverage`；当前证据支持**保留 0.99**，只补可复现校准。
3. **U-8**：以 0/8,389,800 实测裁决 `close_mismatch_cells`；阈值定为 **0 容忍 + 仅披露**，不新增门禁。
4. **R-3**：以 3 因子敏感性表裁决健康度/漂移阈值；结论为**不重标定**，只补证据。

**非目标**：B 批收益层；`stk_limit` 外部一致率（U-1）；分块/流式 apply（候选 F，风险高于收益）；空头腿/分钟级撮合；`data_contract.py` 单位修正。

---

## 2. 设计依据

### 2.1 调研结论 → 设计决策

| 调研发现 | 设计决策 | 引用 |
|---|---|---|
| `_PANEL_CACHE` 1140.1 MB，其中 `name` 567.1 + `suspend` 192.4 | **D1** 紧凑缓存：`name` → float32 码 + 唯一名查找表；`suspend` → bool mask/missing；float 面板保持 float64 | RESEARCH §4.1 / F-1-1~F-1-7 |
| `reindex`/`fillna`/`astype` 即使无变化也复制 | **D2** 零拷贝快路径：全量命中返回同对象；已对齐 float64 + fill=NaN 时跳过三连拷贝 | RESEARCH §4.2 / F-1-3~F-1-5 |
| worker 携带全部 `factor_data` | **D3** 载荷裁剪：仅传本 chunk 因子子集（`price_data` 保持全量交集所需） | F-1-8/F-1-9 |
| `apply`/引擎 T×N 中间数组 | **D4** 原地化：`effective` 原地累加；`pct_mat` 按行计算；`compute_turnover` 按行差 | F-1-10/F-1-11 |
| 73/73 月 `full`；`prev` min 0.994429 | **D5** 保留 `min_coverage=0.99`；不新增/不改默认 | RESEARCH §4.3 |
| 同源 mismatch 0 / 8,389,800 | **D6** 阈值 0 容忍、仅披露；不新增门禁、不改 9/13 键 | RESEARCH §4.4 |
| 3 因子无告警翻转、健康分 Δ≤0.36 | **D7** 不重标定健康度/漂移阈值；只补敏感性证据 | RESEARCH §4.5 |
| 分块 apply 收益最大但需跨块状态 | **D8（被拒）** 本批不引入 F；如 D1-D4 后仍超预算，优先复核测量口径而非架构改造 | RESEARCH §5.1 |
| 默认路径有 TP6-11 字面量锁定 | **D9** 默认路径与启用路径均建立逐位门禁；优化仅允许内存布局变化 | P-006/P-021 既有门禁 |

### 2.2 相关 ADR

| ADR | 决策 | 对本设计的影响 |
|---|---|---|
| ADR-0010 | Layer 判定三问 | 触及 `backtest/`/`tests/`/`scripts/` → T1 |
| ADR-0004 | 四件套 + Review 门禁 | 本批完整执行 |
| ADR-0002 | 职责边界 | B 批/空头腿/分钟级明确排除 |

### 2.3 职责边界

- **职责内**：loader 缓存表示、切片/构建的零拷贝路径、worker 载荷、apply/引擎的内存原地化、U-7/U-8/R-3 的阈值裁决与证据脚本。
- **职责外**：收益层口径（B 批）；`stk_limit` 在线拉取；分块/流式 apply；`transient` 内存的跨进程共享（Windows spawn 下不引入共享内存）。
- **能力边界**：≤1 GB 的度量口径绑定“单 worker、单因子、全样本（1475×5688）、构建后稳态 + apply 峰值”；不同因子数量/股票池的扩展由 D3 载荷裁剪缓解，但不承诺任意规模线性不变。

---

## 3. 架构设计

### 3.1 内存布局（改后）

```
E:\Ashare_data\market_data\stock_*.pkl
        │  首次读取，进程内缓存（紧凑表示）
        ▼
_PANEL_CACHE
  ├─ float 面板（close/high/low/open/volume/adj）: DataFrame(float64)   ≈380 MB
  ├─ name: float32 码面板 (T×N, NaN=缺失) + uniques + is_st/退 LUT      ≈34 MB
  └─ suspend: bool mask + bool missing                                  ≈16 MB
        │  _slice：全量命中 → 同对象；子集 → np.ix_ / reindex 一次
        ▼
build_tradability_inputs（新增可选紧凑状态参数）
  ├─ float：对齐且 float64 且 fill=NaN → 直接返回原 df → to_numpy 视图
  ├─ name：ffill(码) → LUT 映射 is_st / is_delisting（无 object 字符串）
  └─ suspend：直接使用预计算 mask/missing
        ▼
TradabilityInputs（数组多为缓存视图；ref/mask 为新分配）
        ▼
engine / apply
  ├─ effective 原地累加（不再复制一份）
  ├─ pct 按行计算（不分配 T×N pct_mat）
  └─ compute_turnover 按行差（不分配 2×T×N diff/abs）
```

### 3.2 模块划分

| 模块 | 职责 | 改动 |
|---|---|---|
| `tradability_loader.py` | 面板读取/紧凑缓存/切片/模式解析 | 缓存值改为 `_Panel` 记录；`_read_panel` 对 name/suspend 预计算紧凑状态；`_slice` 增加同对象快路径 |
| `tradability_inputs.py` | 面板 → inputs/meta/diagnostics | 新增可选 `name_codes/name_st_lut/name_del_lut/suspend_mask/suspend_missing`；`_frame`/`_normalize_panel` 快路径 |
| `tradability.py` | apply 推进 | `pct_mat` 按行计算；其余语义不变 |
| `engine.py` | 引擎接线 | `effective_long += min(positions,0)`；其余不变 |
| `factor_metrics.py` | 换手率 | `compute_turnover` 按行差（结果逐位一致） |
| `parallel_runner.py` | worker 载荷 | `_run_group` 仅传本 chunk 因子子集 |
| `scripts/verify_tradability_closeout.py`（新） | U-7/U-8/R-3 可复现证据 | 输出 JSON：月度覆盖、close 对拍、3 因子敏感性 |

---

## 4. 决策详述

### 4.1 D1 紧凑缓存

**name**：
- 首次读取后 `pd.factorize(flat, sort=False)` → `codes int64`（-1 = NaN）+ `uniques`（实测 8,771 个）。
- 缓存的是**原始码**（不做 ffill）；切片后再由 builder 对码 `ffill`，保证窗口首日不继承窗口外名称。
- `codes.astype(np.float32).reshape(shape)`，-1 → `np.nan`；float32 可精确表示 ≤2^24 的整数，8,771 远低于上限。
- `is_st_lut = ["ST" in str(u) for u in uniques]`；`is_del_lut = ["退" in str(u)]`（只对唯一名做一次字符串判断）。
- 释放原始 object 面板。
- **语义等价**：码与名称一一对应，切片后 `ffill(码)` ≡ 切片后 `ffill(名称)`；`is_st/退` 只取决于填充后的名称；`name_missing` 取 ffill 前的 NaN。

**suspend**：
- **仅当面板不含 bool 列**时预计算紧凑状态（按原始 dtype 逐列判定：object/other → `eq("S")`；缺失单独记录）。
- 缓存 `mask`（bool）+ `missing`（bool），释放原始 object 面板。
- 若面板含 bool 列：**保留原始 DataFrame 路径**（不压缩）。理由：bool 面板经 loader 切片补列后整帧升型 object，现行 `_suspend_mask` 会按切片后的 dtypes 判定；预计算会改变该边界行为。bool 面板仅出现在测试/直调场景，保留原路径可确保逐位一致（P2-5 处置）。
- 真实数据根 `suspend` 为 object（`S` 18,242 / `R` 2,700 / None 其余），走紧凑路径。

**float 面板**：保持 float64 DataFrame；不改 dtype（避免任何数值变化）。

**首次加载顺序**（P1-2 处置）：`name → compact → del/gc → suspend → del/gc → float 面板`，避免 name 567 MB 与 float 面板同时常驻；`_read_panel` 在紧凑化后显式 `del frame` 并 `gc.collect()`。

### 4.2 D2 零拷贝快路径

- `_slice(frame, index, codes)`：若 `frame.index.equals(index) and frame.columns.equals(pd.Index(codes))` → 返回 `frame` 本身（必须先把 `codes` 归一为 `pd.Index`，否则 int 列永不命中）。
- `_frame(df, index, columns, fill, dtype)`：
  - `df is None` → 原逻辑；
  - `df.index.equals(index) and df.columns.equals(columns)` 且**所有列 dtype 均为 `float64`** 且 `np.isnan(fill)` → **返回 `df`**（不 reindex/fillna/astype）；
  - 否则原逻辑。
- `_normalize_panel` 同理：对齐 float64 → 直接 `to_numpy()`（视图）。
- **安全前提**：builder/apply 只读这些数组；D4 的所有原地写只作用于本地新数组（`effective`/`pct_row`）。

### 4.3 D3 worker 载荷裁剪

- `_run_group` 构造 `worker_args` 时使用 `subset = {fn: factor_data[fn] for fn in chunk}`。
- `_run_worker` 签名不变；worker 只读取 `subset` 中自己的名字。
- **理由**：worker 在 `chunk` 内逐因子评估，从不访问其他因子；裁剪后 pickle/常驻与因子总数解耦。

### 4.4 D4 apply/引擎内存原地化

1. `engine`：`effective = effective_long + np.minimum(positions, 0.0)` → `effective_long += np.minimum(positions, 0.0)`（`effective_long` 是 apply 返回的新数组，调用方不再使用；`positions` 与缓存视图均不被改写）。
2. `apply`：**仅 `pct_mat` 改为按行计算**：
   - `pct_row = _pct_row(board, st_mat, del_mat, dates[t])`（与 `_pct_matrix` 第 t 行同一 `rule_pct_or_nan`，含 gap/unknown 分支）；
   - `ref` 保持整幅语义：`inputs.ref` 提供时直接按行取 `ref[t]`；`ref is None` 且 `adj is not None` 时仍调用整幅 `_ref_from_adj(prev_close, adj)`（`_ref_from_adj` 依赖 `(T,N)` 形状，逐行调用会全 NaN——P1-1）。引擎生产路径由 builder 提供 `ref`，因此该分支只影响直调 apply 的调用方，内存不优于现状。
3. `compute_turnover`（复用单行缓冲，避免 2×T×N 临时）：
   ```python
   turnover = np.empty(T - 1)
   buf = np.empty(positions.shape[1])
   for t in range(1, T):
       np.subtract(positions[t], positions[t - 1], out=buf)
       np.abs(buf, out=buf)
       turnover[t - 1] = 0.5 * np.sum(buf)
   ```
   与 `0.5*sum(abs(diff), axis=1)` 逐元素同运算、同行内求和顺序，结果逐位一致（含 NaN/Inf）。

### 4.5 D5 U-7 裁决

- 保留 `min_coverage=0.99`，不改默认、不新增字段。
- 证据：73/73 月 `full`；`prev` min 0.994429（margin 0.004429）；`high_low/open` 恒 1.0。
- 交付：`scripts/verify_tradability_closeout.py --data-root ... --u7` 输出月度表；文档记录年度最低值。

### 4.6 D6 U-8 裁决

- 阈值 = **0 容忍 + 仅披露**：任何 `close_mismatch_cells > 0` 表示调用方 `price_data` 与标准数据根不同源；引擎不阻断、不告警（避免误伤合法自定义价格源）。
- 不新增 diagnostics 键（保留既有 `close_mismatch_cells`）；不改 9/13 键。
- 交付：脚本 `--u8` 输出对拍读数；文档写明“同源 0 是基线”。

### 4.7 D7 R-3 裁决

- 不调整 `crowding_turnover_threshold=0.80`、健康分权重、漂移权重/阈值。
- 交付：脚本 `--r3` 输出 3 因子敏感性表（turnover 均值/drift/crowding/alert/health Δ/combined Δ/ICIR-LS 一致性）。
- 文档结论（Step 9 脚本口径，`out/tradability_closeout_r3.json`）：turnover 变化 **−0.10%~−2.06%**，健康分 Δ**≤0.347**，告警 **0/3** 翻转，组合漂移增量绝对值 **≤0.020**。

### 4.8 D8 被拒方案

| 方案 | 拒绝理由 |
|---|---|
| 仅限制 worker 数（A） | 单 worker 峰值不变，P-2 仍超预算 |
| 分块/流式 apply（F） | 需跨块维护 `pending/locked_until/w_prev`，回归面大于收口批；且与 P-2 的“缓存+拷贝”主因不匹配 |
| float32 存价格面板 | 会改变限价比较结果，违反逐位一致 |
| 进程间共享内存/memmap | 零新增依赖约束下不可行（Windows spawn + numpy memmap 仍引入文件生命周期管理） |
| 关闭面板缓存 | 换 IO 时间且不降低构建峰值，batch 内多因子退化 |

### 4.9 D9 逐位门禁

- **默认路径**：TP6-11 字面量 + 全量回归 + 默认工件 SHA `82728CE1…` 不变。
- **启用路径**：固定 fixture（P-021 loader/pipeline 用例）的 `report`/`meta`/`diagnostics`/`turnover` 字面量在改前抓取为基线，改后逐键断言；定向 `-k "p021 or p022"` 全绿。
- **紧凑语义**：新增“原始 object 路径 vs 紧凑路径”等价测试（随机 fixture，含首行 NaN、窗口前名称、ST/退/普通、bool/object suspend）。

---

## 5. 接口设计

### 5.1 `build_tradability_inputs`（向后兼容扩展）

```python
def build_tradability_inputs(
    close, high, low, open_, volume, suspend, name,
    adj=None, list_date=None, policy=None, st_overrides=None,
    limit_up=None, limit_down=None, ref=None,
    name_codes=None, name_st_lut=None, name_del_lut=None,
    suspend_mask=None, suspend_missing=None,
):
```

- 新增参数全部可选且位于末尾；旧调用**逐位不变**。
- `name_codes` 提供时优先于 `name`；`name` 可为 `None`。
- `suspend_mask/missing` 提供时跳过 `_suspend_mask`。
- **missing_fields 判定修正（P2-4）**：`"name"` 仅在 `name is None and name_codes is None` 时追加；`"suspend"` 仅在 `suspend is None and suspend_mask is None` 时追加。否则紧凑路径会误报缺字段、破坏 INV-2。
- 形状校验：`name_codes` `(T,N)`；LUT 一维 bool；mask/missing `(T,N)` bool，否则 `ValueError`。

### 5.2 loader 内部缓存记录

```python
# _PANEL_CACHE[key] = {
#   "kind": "float" | "name_codes" | "suspend_state" | "raw",
#   "index": pd.Index, "columns": pd.Index,
#   "data": DataFrame | ndarray | (mask, missing) | (codes, uniques, st_lut, del_lut),
# }
```

- `_read_panel(name)` 返回统一记录；`build` 按 kind 取用。
- `_slice` 返回与 kind 对应的切片；全量命中直接复用。
- **访问器（P2-6）**：新增 `_panel_df(rec)` / `_panel_columns(rec)` / `_panel_index(rec)`，替换 `build` 中 L65/L84/L88-L90/L108/L144 等直接 DataFrame 用法（`close.columns`、`close.to_numpy`、`adj is None` 判定等）；float 记录返回 DataFrame，name/suspend 记录返回紧凑结构。
- 缓存仍为进程内全局，key 不变；测试 `test_p021_loader_cache` 的 read 计数语义不变。

### 5.3 `compute_turnover`

签名与返回不变；内部改为按行差，`T<2` 仍返回 `np.array([])`。

---

## 6. 不变式（INV）

| # | 不变式 | 验证 |
|---|---|---|
| INV-1 | `tradability_inputs=None` 时旧路径逐位不变 | TP6-11 + 默认 SHA + 全量回归 |
| INV-2 | 启用路径同一输入的 `report`/`meta`/`diagnostics`/`turnover` 与 3.10.0 逐位一致 | 固定 fixture 字面量断言 |
| INV-3 | `report` 9 键、`meta` 13 键冻结；diagnostics 不新增/不删除键 | 键集合断言 |
| INV-4 | `build_tradability_inputs` 旧调用兼容（位置/关键字） | 既有全部调用测试 |
| INV-5 | 紧凑 name 与 object name 的 `is_st`/`is_delisting`/`name_missing_*` 逐格一致（**先切片后 ffill**；含首行 NaN、窗口前名称） | 等价性单测 |
| INV-6 | 紧凑 suspend 与现行 `_suspend_mask` 逐格一致（**仅 object 面板走紧凑；含 bool 列的面板保留原路径**） | 等价性单测 + P-021 三形态回归 |
| INV-7 | 零新增运行时依赖；Python 3.9 / pandas 2.0 / numpy 1.22 兼容 | `pyproject.toml` 不变 + AST 检查 |
| INV-8 | worker 载荷裁剪不改变并行结果 | 串行 vs 并行 summary 逐位相等 |
| INV-9 | 缓存数组不被 builder/apply 原地修改 | `np.shares_memory` + 二次 build 前后缓存抽样哈希一致 |
| INV-10 | 内存预算：M-3 worker 峰值 ≤1024 MB；M-1 构建 ≤30 s | Step 9/10 实测（探针脚本） |
| INV-11 | `close_mismatch_cells` 仍为 int；U-8 不改门禁 | 既有键断言 + 定向用例 |
| INV-12 | `compute_turnover` 按行差与旧实现逐位一致（含 NaN/Inf、T<2、N=1） | 新老实现对拍单测（随机矩阵） |
| INV-13 | 首次加载高水位如实披露（M-6），不混入 M-3 | 探针读数 + 文档 |
| INV-14 | bool suspend 面板路径逐位不变（reindex 升型 quirk 保留） | `test_p021_d5_suspend_reindex_dtype` + 新增 loader 路径用例 |
| INV-15 | `_pct_row` 与 `_pct_matrix` 第 t 行逐位一致（含 unknown/gap/一字） | 随机 board/ST/日期对拍单测 |

---

## 7. 测试矩阵

| 组 | 用例 | 覆盖 |
|---|---|---|
| 紧凑 name | `test_p022_name_codes_equiv`（随机 6×4，含 NaN/ST/退/窗口前名称）| INV-5 |
| 紧凑 suspend | `test_p022_suspend_state_equiv`（object `S/R/None` + bool + 补列升型）| INV-6 |
| 零拷贝 | `test_p022_slice_identity`（全量命中 `is` 同对象）；`test_p022_frame_no_copy`（`np.shares_memory`）| D2 / INV-9 |
| 缓存结构 | `test_p022_cache_compact`（name 为 float32、suspend 为 bool；无 object 大列）| D1 |
| 逐位 | `test_p022_report_meta_bitwise`（固定 fixture 与基线字面量）| INV-2/INV-3 |
| turnover | `test_p022_turnover_bitwise`（随机 T×N 新老实现 `==`）| INV-12 |
| 载荷 | `test_p022_parallel_payload_subset`（monkeypatch 捕获 worker_args，断言仅本 chunk 因子）| D3 / INV-8 |
| 默认路径 | 复用 TP6-11 / `test_p021_*` 既有用例 | INV-1 |
| 脚本 | `test_p022_closeout_script_schema`（mock 数据根 → JSON 键集合）| D5-D7 |

---

## 8. 性能/内存度量口径

**探针**（Step 9/10，工作区外临时脚本；读数写入 CHECKLIST §6）：

| 指标 | 口径 | 预算 |
|---|---|---|
| M-1 构建耗时 | 全样本 `spec.build`，单进程 | ≤30 s |
| M-2 构建峰值 | `tracemalloc` peak（全样本） | ≤1024 MB |
| M-3 worker 稳态 RSS | spawn 子进程内 `spec.build` + 单因子 `engine.run()`，**紧凑缓存建立后**，psutil 50 ms 采样取 max | **≤1024 MB** |
| M-4 缓存常驻 | `_PANEL_CACHE` deep MB | ≤500 MB |
| M-5 结果一致性 | 与 3.10.0 固定 fixture 字面量逐位 | 100% |
| M-6 首次加载高水位 | 首次 build 完成后的进程 **RSS**（含 name/suspend 解码常驻；一次性容器扩张已回缩），与 M-3 的 spawn 子进程口径分开 | ≤1400 MB，披露 |

> **口径边界（P1-2，Step 10 对齐）**：`name` pickle 解码的一次性峰值未单独采样；M-6 取“build 完成后 RSS”以覆盖解码常驻成本，Step 9 实测 **1345.4 MB**（改前 2201.3 MB）。M-3 不计入该一次性成本，但 M-6 必须如实披露。若要求“含 M-6 也 ≤1 GB”，需离线把 `stock_name.pkl` 迁移为紧凑格式（**P-023**，涉及数据根写入），不在本批范围。
>
> **失败门禁**：Step 9 若 M-3 >1024 MB，**停止并回报分项读数**（缓存/inputs/引擎/载荷），由用户决定“追加 D8 分块 apply 立项”或“调整预算”，不得静默放宽 INV-10。

---

## 9. 版本与交付

- 包版本 **3.10.1**（patch）：`pyproject.toml` / `__init__.py` / `config_v2.py` / `reporting.py` / CHANGELOG。
- CHANGELOG 明示：内存布局与执行路径优化；默认/启用路径数值逐位不变；U-7/U-8/R-3 阈值裁决。
- 文档：本四件套 + PROGRESS/PROJECT_STATUS 台账 + `docs/research` 不新增（证据在 spec 内）。

---

## 10. 风险与缓解

| # | 风险 | 缓解 |
|---|---|---|
| R-1 | 零拷贝导致缓存被下游原地修改 | 只读约定 + INV-9 测试；D4 原地写仅限本地数组 |
| R-2 | 紧凑 name/suspend 语义漂移 | INV-5/6 等价测试 + 既有 P-021 suspend 三形态回归 |
| R-3 | worker 载荷裁剪改变结果 | INV-8 串并行逐位测试 |
| R-4 | 内存预算未达标 | M-3 分项读数；D8 禁止本批引入分块 apply |
| R-5 | `compute_turnover` 按行差性能下降 | 单层 1474 次向量运算；Step 9 计时，预算 +10% 内 |

---

## 11. 未决项

| ID | 判据 | 触发 | 倾向 | 等级 |
|---|---|---|---|---|
| U-1 | `stk_limit` 外部一致率 | token 到位 | 保持现状 | E0 |
| U-2 | M-3 实测是否达标 | Step 9 | D1-D4 全上；不达标则登记 | E1 |
| U-3 | 非标准 `price_data` 的 mismatch 样例 | 出现调用方 | 仅披露 | E0 |
| U-4 | 健康度/漂移阈值重标定 | 告警翻转 | 本批不重标定 | E1 |

---

## 12. Review 记录（Step 4）

> 独立只读子代理（general-purpose，只读约束），2026-11-23。裁决 **PASS_WITH_FIXES（2×P1 / 5×P2 / 3×P3）**，全部处置。

| # | 级别 | 发现 | 处置 |
|---|---|---|---|
| 1 | P1 | D4 逐行 `ref` 不可行：`_ref_from_adj` 依赖 `(T,N)` 形状，单行会全 NaN，直调 `adj` 路径破坏限价 | §4.4(2) 改为**仅 pct 按行**；ref 保持整幅，生产路径由 builder 提供 `ref` 不分配 |
| 2 | P1 | 预算不可达：`name` 解码 567 MB 与 float 面板叠加，峰值 1.1-1.2 GB | §4.1 增加首次加载顺序（name→compact→gc→suspend→float）；§8 拆分 M-3/M-6 并加失败门禁 |
| 3 | P2 | 紧凑 name 必须先切片后 ffill | §4.1 明确缓存原始码；INV-5 增加窗口前名称用例 |
| 4 | P2 | 紧凑路径传 `name=None/suspend=None` 会误加 `missing_fields` | §5.1 增加条件修正（P2-4） |
| 5 | P2 | suspend 预计算与 bool 面板 reindex 升型 quirk 不等价 | §4.1 改为**含 bool 列不压缩**，保留原路径；INV-14 |
| 6 | P2 | `_read_panel` 改记录后 DataFrame 用法未列 | §5.2 增加 `_panel_df/_panel_columns/_panel_index` 访问器 |
| 7 | P2 | 测试矩阵缺 pct 行/unknown/gap、13 位置参数、二次 build 哈希 | §6 增 INV-15；INV-9/12 扩边界 |
| 8 | P3 | `_slice` 需先归一 `pd.Index(codes)` | §4.2 已改 |
| 9 | P3 | turnover 按行慢，建议复用缓冲 | §4.4(3) 改为 `np.subtract(..., out=buf)` + `np.abs(out=)` |
| 10 | P3 | 内存/耗时风险 | §10 R-5 保留 +10% 预算，Step 9 计时 |

> 复审确认 PASS：D2 零拷贝不会污染缓存（engine L317 用新数组、L330 只改 apply 返回数组）；D3 worker 仅访问本 chunk 因子，空 chunk/重名安全。

---

**Review 签字**: Step 4 独立只读复审 PASS_WITH_FIXES（2×P1/5×P2/3×P3 全部处置） 日期: 2026-11-23
