# 调研文档：P-023 tradability worker 内存第二阶

---
id: p023-tradability-memory-phase2-RESEARCH
type: design
version: 1.1
status: verified
date: 2026-11-24
depends: [p022-tradability-closeout]
upstream: null
---

> **Feature**: P-023（离线 name 紧凑缓存 + worker 日期分片 + M-2/M-3 复测）
> **创建日期**: 2026-11-24
> **状态**: verified（Step 1-2 完成；Step 2 机械核验 PASS，记录见 §11；**v1.1 = Step 4 复审补充 §4.5 读数**）
> **Spec 步骤**: Step 1-2
> **批次档位**: **T1**（触及 `backtest/` 运行时、`scripts/`、`tests/`；数据根新增派生文件）
> **裁剪理由**: 不降档。离线缓存改变 loader 的 IO/缓存契约；日期分片改变 worker 执行路径与 apply 状态边界；两者均需逐位门禁与全量回归。
> **上游依据**: P-022 [CHECKLIST](../p022-tradability-closeout/CHECKLIST.md) §6/§10.2（M-2/M-3 未达）、P-022 [DESIGN](../p022-tradability-closeout/DESIGN.md) §8 失败门禁（用户裁决：收口 + 开 P-023）、[PROGRESS](../../docs/PROGRESS.md) P-023 行。

---

## 1. 调研目标

**核心问题**：

1. **离线 name 紧凑缓存**：把 `stock_name.pkl` 转为紧凑 `.npz` 能消除多少解码内存/耗时？格式如何保证与 pkl 路径逐位等价、无 pickle 依赖且可回退？
2. **worker 日期分片**：P-022 后 worker 全样本 RSS 2463.5 MB 的构成是什么？按日期分片需要切哪些数组、跨块保留哪些状态，才能在不改变 `report` 9 键 / `meta` 13 键 / `turnover` 的前提下降到 ≤1024 MB？
3. **M-2 预算**：P-022 build tracemalloc 峰值 1249.4 MB 的主要来源是什么？离线 npz + 分片构建能否将其降到 ≤1024 MB？

## 2. 调研方法

### 2.1 工具与范围

| 工具 | 用途 | 查询/对象 |
|---|---|---|
| 仓库读码 | loader/builder/engine/worker 事实锚点 | `backtest/tradability_loader.py`、`tradability_inputs.py`、`tradability.py`、`engine.py`、`parallel_runner.py` |
| Python 只读探针（`%TEMP%\\p023_probe\\`，工作区外） | E1 实测：pkl/npz 体积与解码、build 分阶段峰值、60 日分片 build/apply、worker 分片原型 | 标准数据根 `E:\\Ashare_data\\market_data`；全样本 1475×5688 |
| WebFetch | 外部格式/安全口径 | NumPy `savez`/`load`、pandas `read_pickle`、Python `pickle` |

- **时间范围**：2026-11-24 实测（数据根 `stock_name.pkl` mtime 2026-01-30）。
- **排除**：float 面板的离线格式迁移（npy/npz/parquet）不在本批调研范围；仅在 §6.3 作为被拒/后续候选记录。

### 2.2 数据根事实

| 文件 | 大小 | 备注 |
|---|---|---|
| `stock_name.pkl` | **102,051,886 B（≈102.1 MB）** | object DataFrame，1474×6053 |
| `stock_close.pkl` | 67,189,474 B | float64 DataFrame，1475×5688 |
| `stock_suspend.pkl` | 8,489,265 B | 1475×5681，object（本数据根全 object；loader 兼容 bool 列路径） |
| 其余 float 面板（high/low/open/volume/adj） | 各 ≈67.2 MB | float64 |
| 数据根可写性 | **True** | 迁移脚本可在 `market_data/` 写入派生文件 |

> **标签不一致（设计输入）**：name 为 1474×6053、suspend 为 1475×5681、close 为 1475×5688；三者的行/列集合并不相同。离线 npz **必须自带 index/columns**，loader 按标签切片（不能假设与 close 同形）。

---

## 3. 代码事实（现状）

| # | 锚点 | 事实 |
|---|---|---|
| F-1 | [tradability_loader.py L254-L266](../../backtest/tradability_loader.py#L254-L266) | `_read_panel` 对每个面板 `pd.read_pickle` 整帧；`_PANEL_CACHE` 以 `(root, panel_dir, name)` 为键常驻 |
| F-2 | [tradability_loader.py L269-L288](../../backtest/tradability_loader.py#L269-L288) | name 在进程内紧凑化：`pd.factorize` → float32 码（NaN 表缺失）+ `(uniques, st_lut, del_lut)`；唯一值 >2^24 回退 raw |
| F-3 | [tradability_inputs.py L87-L101](../../backtest/tradability_inputs.py#L87-L101) | `build_tradability_inputs` 纯函数，输出 `TradabilityInputs` + 13 键 meta；紧凑 name/suspend 走可选参数 |
| F-4 | [tradability_inputs.py L238-L246](../../backtest/tradability_inputs.py#L238-L246) | builder 先构造整幅 `prev`（T×N）再 `_ref_from_adj` 得整幅 `ref` |
| F-5 | [tradability_inputs.py L259-L260](../../backtest/tradability_inputs.py#L259-L260) | `_pct_matrix` 返回整幅 `pct_mat` 与 `gap_mask`；逐日 `compute_limits` 仅用于一字诊断 |
| F-6 | [tradability.py L443-L472](../../backtest/tradability.py#L443-L472) | apply 的 `target_all` 为前移 1 日；跨日状态 = `pending` / `locked_until`（绝对 t）/ `w_prev` |
| F-7 | [tradability.py L582-L584](../../backtest/tradability.py#L582-L584) | `report["carried"]` 只由最后一行 effective vs target 决定 |
| F-8 | [engine.py L309-L351](../../backtest/engine.py#L309-L351) | 引擎整幅 `positions` → 整幅 `prev_close` → 整幅 apply → 整幅 mismatch（`np.isclose`）→ `compute_turnover` |
| F-9 | [engine.py L280-L303](../../backtest/engine.py#L280-L303) | IC/ICIR/decay/hit-rate 仅依赖 factor 与 fwd_returns；**不依赖 tradability** |
| F-10 | [engine.py L353-L358](../../backtest/engine.py#L353-L358) | 多空收益 `compute_long_short_returns(factor_t, fwd_ret_t)` 亦不依赖 tradability |
| F-11 | [parallel_runner.py L34-L78](../../backtest/parallel_runner.py#L34-L78) | worker 对每个因子 `spec.build(cd, cs)` 构建**全样本** inputs，再 `engine.run()` |
| F-12 | [tradability_loader.py L103-L233](../../backtest/tradability_loader.py#L103-L233) | `build` 先按全样本切片/覆盖率/`_resolve_mode`，再调用 builder；`mode` 由全样本覆盖率决定 |

> **关键结论（F-9/F-10）**：tradability 只影响 `turnover` 与 `tradability` 块；IC/ICIR/decay/LS/spread 与它无关。因此分片只需覆盖「inputs/build + apply + turnover」，指标路径可保持整幅。

---

## 4. E1 实测读数

> 探针位置：`C:\\Users\\Peng\\AppData\\Local\\Temp\\p023_probe\\`（工作区外）；命令均带 `PYTHONPATH=F:\\Coding`。RSS 为 psutil 进程 RSS（20 ms 采样 max）；tracemalloc 为 Python/NumPy 跟踪峰值。

### 4.1 `stock_name.pkl` 解码 vs 紧凑 npz

| 指标 | pkl（现状） | npz（候选） |
|---|---|---|
| 文件大小 | 102.1 MB | **34.5 MB**（`np.savez` 未压缩；含 codes/index/columns/uniques/LUT） |
| 读取耗时 | **0.86–0.93 s** | **0.03 s** |
| 读取增量 RSS | **+686 MB**（218.6 → 904.8） | **+21 MB**（871.6 → 892.6；其中 codes 34 MB） |
| 对象 deep 内存 | **567 MB**（object DataFrame） | 34 MB codes + 字符串元数据（<1 MB） |
| 形状 / 缺失 / 唯一名 | 1474×6053 / 1,528,982 / 8,770 | 同左（codes NaN 表缺失） |
| 进程内紧凑化 | 1.29 s（peak RSS 1237.9） | 无需（直接构造 `_PanelRecord`） |
| 逐位校验 | — | codes / index / columns / uniques **全部相等** |
| 依赖 | `pickle`（安全告警） | `np.load(..., allow_pickle=False)`（纯数值/字符串） |

- `.npz` 是**未压缩 zip + 每成员 .npy**，`np.load` 返回 `NpzFile`，需 `with` 关闭；文档中的 `mmap_mode` 示例仅针对 `.npy`，`.npz` 返回的是 `NpzFile` 而非可映射数组（见参考文献 R-2）。
- `savez` 的 `allow_pickle` 默认为 True，但本格式全部用数值/`<U` 字符串数组，写入时无需对象数组；读取端可强制 `allow_pickle=False`（R-1/R-2）。

### 4.2 build 峰值分解（npz name）

| 阶段 | tracemalloc cur | tracemalloc peak | 说明 |
|---|---|---|---|
| 面板读取完成（含 name npz） | 398.8 MB | 398.8 MB | 6 个 float 面板各 64.3 MB；suspend 读取瞬时 136.3 MB |
| `spec.build`（缓存已命中） | 559.9 MB | **1214.4 MB** | 增量 654 MB：`prev` 67 + `_ref_from_adj` 瞬态（ratio/raw/cents/aligned ≈300–400）+ `pct_mat` 67 + 布尔/覆盖掩码 |
| 60 日分片 build（缓存已命中） | 19.7 MB | **46.4 MB** | 0.08 s/块 |
| 60 日分片 apply | 27.5 MB | **31.4 MB** | 0.13 s/块；effective 2.6 MB |

- 对照 P-022（pkl name）：build 15.64 s / tracemalloc **1249.4 MB** / build 后 RSS 1345.4 MB（P-022 E1 记录；与本次探针环境存在机器/缓存差异，时间不直接相减归因）。
- npz name：build **2.06 s**（无 tracemalloc）/ 3.26 s（含 tracemalloc 开销），tracemalloc **1214.4 MB**，build 后 RSS 945.4 MB（同进程峰值 1473.8 MB 来自 pandas 反序列化瞬态）。
- **结论**：npz 消除了解码常驻，但 **M-2 仍卡在整幅 `prev/ref/pct_mat`**；只有分片构建才能把峰值压到 ≈450–500 MB。

### 4.3 worker 全样本内存构成（npz name）

| 阶段 | RSS | peak | 说明 |
|---|---|---|---|
| 解释器 + factor/price/fwd（1475×5688） | 447.8 MB | 447.8 | factor 67 + price 67 + fwd 67 + 解释器 ≈218 |
| 面板缓存预热（6 float + suspend；name npz 记录另计 34 MB） | 849.3 MB | 883.8 | cache deep **396.8 MB**（不含 name npz 的 34 MB；RSS 已包含） |
| 25×60 日流式 build+apply+turnover | 916.3 MB | **959.6 MB** | 5.65 s；turnover 1474 行 |
| + 全幅 IC 计算（含 `hstack` padding） | 981.2 MB | **981.2 MB** | +21.5 MB RSS（tracemalloc 侧 +67 MB） |
| 对照：整幅 inputs 路径 | 1202.4 MB | **1337.1 MB** | apply 0.89 s；inputs 数组 **480.1 MB** |

- 对照 P-022 实测（pkl name）：worker RSS **2463.5 MB**；隔离基线引擎（`tradability=None`）540.1 MB。
- 分片原型 **981 MB** 已接近预算，但**余量仅 ≈43 MB**，且原型未包含：`close_mismatch_cells` 整幅 `np.isclose`、引擎 positions 整幅、以及 spawn 进程的额外开销 → 设计必须补齐额外节省项（见 §6.2）。

### 4.4 其他读数

- 数据根可写：True（探针创建/删除 `.p023_write_probe` 成功）。
- `volume` 在 apply 内**未被消费**（仅签名/形状校验与 `TradabilityInputs` 字段保留）；本批不据此改契约，仅记录为潜在节省项（§6.3-E）。
- 分片开销：每因子 25 块 ×（0.08 s build + 0.13 s apply）≈ 5.3 s；对照整幅 apply 0.89 s + build 2.06 s。分片带来的单因子耗时增量约 +2.4 s，属可接受范围。

### 4.5 spawn 基线与「逐块读面板」原型（关键补充）

| 路径 | 峰值 RSS | 说明 |
|---|---|---|
| npz name + **整幅 inputs**（spawn 子进程） | **1548.9 MB** | 与 P-022 协议同构（psutil 50 ms）；对照 pkl 版 2463.5 MB → npz 单省 ≈915 MB |
| **逐块读面板**（无 float 面板常驻缓存；name npz 34 MB + suspend 紧凑 16 MB） | **514.7 MB**（同进程） | 25 块 × 4 面板 `pd.read_pickle` + build + apply + 块内 IC；循环 7.7 s |
| 估算 spawn 版逐块读 | **≈730 MB** | 514.7 + spawn/DataLoader 差额 ≈212（由 1548.9−1337.1 同口径推得） |

- 逐块读的关键：**不保留 6 个 float 面板的整幅缓存**；每块从 pkl 读取所需行后立即释放。OS page cache 使读取开销可控（原型 100 次读取 + 构建/apply 共 7.7 s）；生产 plan 预扫 + build 各读一次，约 **225 次**读取（25×(4+5)），M-1 预估 ≈8–10 s。
- 该路径下 M-3 预算余量 ≈294 MB，显著优于「保留整幅 cache + 分块 apply」的 981 MB 原型（余量 43 MB）。
- 代价：单因子额外 IO/构建耗时约 +2~4 s；可通过「块外层循环、因子内层」在多因子 worker 中摊薄（记入设计 R-6）。


---

## 5. 分片约束分析（设计输入）

### 5.1 跨日状态（必须保留）

| 状态 | 位置 | 跨块处理 |
|---|---|---|
| `pending`（精确未成交缺口） | apply L470 | 块末保存、块初注入 |
| `locked_until`（T+1 锁定，**绝对 t**） | apply L471 | 保存绝对索引；块内 t 需加全局偏移 |
| `w_prev`（上一日 effective） | apply L472 | 块末保存、块初注入；同时提供跨块首行 turnover |
| `target_all` 前移 1 日 | apply L443-L449 | 块首行 target 取上一块最后一行 target |
| `prev_close` 前移 1 日 | engine L317-L319 | 块首行需上一日 close（1 行 lookback） |
| `ref` 的除权比 | `_ref_from_adj` | 块首行需上一日 adj 与 close（2 行 lookback） |
| name `ffill` | builder L178 | 块首行需上一块最后一个有效名称码（按列 carry） |
| `report["carried"]` | apply L582-L584 | 只在**最后一块**计算 |
| `report`/`diagnostics` 计数 | apply 全文 | 逐块求和；`limit_table_source` 的 partial 标记按全局缺失数判定 |
| `close_mismatch_cells` | engine L340-L341 | 逐块计数求和（避免整幅 `np.isclose` 瞬态） |

### 5.2 meta 13 键的聚合规则

- **mode/coverage**：必须先按全样本覆盖率解析一次（F-12），再对每块使用同一 `policy`；否则块级 `_resolve_mode` 可能把部分块降级为 `off`。
- **计数类**：`name_missing_*` / `suspend_missing_*` / `ref_fallback_*` / `rule_gap_*` / `one_word_*` / `limit_table_missing_cells` 均为整数计数，可逐块求和（`*_days` 为逐日 any，可求和）。
- **比率类**：`high_low_coverage` / `open_coverage` / `prev_close_coverage` 用「分子计数/分母计数」全局相除；与整幅一次计算在整数计数下逐位一致。
- **分级/字段**：`data_tier` / `bias_direction` / `missing_fields` / `price_basis` / `adj_source` / `board_counts` 由全局计数与面板存在性决定，分块聚合后可复现。

### 5.3 指标路径

- IC/ICIR/decay/hit-rate/LS/spread 仅依赖 factor 与 fwd（F-9/F-10），**不分片**，避免跨块 IC 拼接误差。
- 唯一可省的大数组是 `np.hstack([padding, fwd_ret_t])` 的 67 MB 拷贝；设计应提供不复制 padding 的等价路径（用切片视图或将 NaN 首列语义内联），并纳入逐位门禁。

---

## 6. 候选方案

### 6.1 A：仅离线 npz（不充分）

- name 解码消除，build 15.64→2.06 s；但 M-2 仍 1214.4 MB、M-3 预估 ≈1900 MB（2463.5−567），**两项均不达**。不采纳为本批唯一方案。

### 6.2 B：离线 npz + 逐块读面板 + 分片 build/apply（推荐）

1. **离线 name 紧凑缓存**：新增派生文件（名称/格式见 U-1），内容 = float32 codes + index + columns + uniques + st_lut + del_lut（无 pickle）；loader 优先读、缺失/校验失败回退 pkl；迁移脚本幂等、临时文件 + 原子替换、可回退（删除派生文件）。
2. **逐块读面板（流式 worker）**：worker 的 plan 模式不保留 float 面板整幅缓存；每块按标签从 `stock_*.pkl` 读取所需行（close/high/low/open/adj），构建后立即释放。name 用 npz（34 MB），suspend 紧凑一次（16 MB）。
3. **分片构建**：`TradabilitySpec` 增加「全样本 plan + 逐块 inputs」路径；plan 负责覆盖率/mode/全局 meta 骨架，块构建复用现有纯 builder，并注入关键帧（prev/adj/name carry/全局日期位置）。
4. **分片 apply**：`apply_tradability_with_diagnostics` 增加可选 `state`（pending/locked_until/全局 t 偏移/target 前一行）；逐块返回 `effective` + `report/diag` 增量；最后一块定 `carried`；turnover 跨块含块首行与空头腿。
5. **引擎流式分支**：仅当启用分片（worker）时，`_evaluate_factor` 以块循环计算 positions/apply/turnover；IC/LS 保持整幅（含现有 `hstack` padding）；`close_mismatch_cells` 逐块求和。
- 原型读数：逐块读同进程峰值 **514.7 MB**，估算 spawn ≈**730 MB**；M-3 余量 ≈294 MB。

### 6.3 被拒/后续候选

| 方案 | 结论 | 理由 |
|---|---|---|
| C 仅提高内存预算 | 拒绝 | 用户裁决为 ≤1 GB；不静默放宽 |
| D float 面板离线 npy/npz（mmap） | 后续候选 | 可再把 cache 396.8 MB 降为按页读取，但涉及 6 个面板的数据根迁移、范围大于本批；`npz` 不支持 mmap（R-2），需 `.npy` 目录方案 |
| E 丢弃 `volume` 缓存 | 待设计裁决 | apply 未消费 volume，但 `TradabilityInputs.volume` 是契约字段；若采用需显式契约变更/测试，暂不作为首选 |
| F lazy inputs（逐行访问） | 备选 | 状态无需跨块，但需新增 lazy 类并改写 apply 访问路径；与 B 内存同量级，复杂度更高 |
| G 仅减少 worker 数 | 拒绝 | 单 worker 峰值不变（P-022 A 已拒） |

---

## 7. 风险登记

| # | 风险 | 缓解 |
|---|---|---|
| R-1 | 分块边界破坏逐位（name ffill / locked_until / target 前移 / carried） | P-022 4 组 fixture + 全样本 SHA + 块边界专项用例（块长 1/2/60/全量） |
| R-2 | meta 聚合与整幅不一致（比率/天数/分级） | 整数计数聚合 + 与整幅 build 的 13 键逐键对拍 |
| R-3 | M-3 余量仅 ≈43 MB，spawn/引擎开销可能击穿 | 先补 `hstack` 与 mismatch 分块；Step 9 以 spawn 实测为门禁；不达标则启用 U-2 备选 |
| R-4 | npz 与 pkl 版本漂移（数据更新后忘记重建） | npz 记录 `source_mtime/source_size/format_version`；loader 校验 mtime/size 不一致则回退 pkl 并 warning |
| R-5 | 数据根写入失败/并发迁移 | 临时文件 + `os.replace` 原子替换；失败不覆盖 pkl；`--force/--dry-run`；并发锁文件可选 |
| R-6 | `allow_pickle=False` 与字符串 dtype 兼容 | 全部字符串用 `<U` 定宽数组；读取端显式 `allow_pickle=False`；跨平台编码测试 |
| R-7 | 分片导致单因子耗时上升 | 块长可配（默认 60 交易日）；测 20/40/60/120 块的耗时/内存折中 |
| R-8 | 非 worker 路径行为变化 | 流式仅由 `TradabilitySpec` 显式开关启用；`build()` 与引擎默认路径逐位不变 |

---

## 8. 未决项登记（四元块）

- **U-1 派生文件命名与格式版本**
  - **判据**：loader 按固定键读取且校验通过；pkl 原文件不被修改；删除派生文件即可回退。
  - **触发条件**：Step 3 DESIGN 定稿前。
  - **当前倾向**：`market_data/stock_name_compact.npz`（与 `stock_name.pkl` 并存）；键 = `codes/index/columns/uniques/st_lut/del_lut/source_mtime/source_size/format_version`。
  - **证据等级**：E1（本调研 §4.1）。

- **U-2 M-3 余量不足时的追加节省项**
  - **判据**：spawn worker 实测 peak ≤1024 MB。
  - **触发条件**：Step 9 M-3 复测 >1024 MB。
  - **当前倾向**：优先 `hstack` 消除 + mismatch 分块；仍不足则评估 volume 缓存/块长。
  - **证据等级**：E1（原型 981.2 MB）。

- **U-3 默认块长**
  - **判据**：块长 ∈ {20, 40, 60, 120} 的 (peak, 耗时) 读数；默认值写入 DESIGN。
  - **触发条件**：Step 9。
  - **当前倾向**：60 交易日（≈3 个月，25 块/全样本）。
  - **证据等级**：E1（60 日块 0.08 s build / 0.13 s apply）。

- **U-4 分片与 `mode=auto/off` 的交互**
  - **判据**：plan 阶段全局解析 mode；块内不再触发降级；`off` 时不加载任何面板。
  - **触发条件**：Step 3 DESIGN。
  - **当前倾向**：全局解析一次，块内只消费已解析 policy。
  - **证据等级**：E2（代码事实 F-12）。

- **U-5 外部限价表（`stk_limit`）分片**
  - **判据**：`--price-panel`/`stk_limit_path` 场景下分块与整幅 `report` 一致。
  - **触发条件**：U-1 token 到位或现有 CSV 可用。
  - **当前倾向**：按块切片限价表；缺格回退规则不变。
  - **证据等级**：E2（现有 `load_stk_limit` 接口）。

---

## 9. 置信度与验证

| 结论 | 置信度 | 依据 |
|---|---|---|
| name pkl 解码 ≈567 MB、npz ≈34.5 MB/0.03 s | ★★★★★ | 直接实测（§4.1），两次复跑一致 |
| npz 单独不足以达成 M-2/M-3 | ★★★★★ | build tm 1214.4 MB（§4.2）；worker 预估 ≈1900 MB |
| 60 日分片可把 build/apply 增量压到 ≤50 MB | ★★★★★ | tracemalloc 46.4/31.4 MB（§4.2） |
| 逐块读面板（无整幅 cache）worker 峰值 ≈730 MB | ★★★★☆ | 同进程 514.7 MB + spawn 差额 212（§4.5）；需 Step 9 spawn 实测确认 |
| 分片原型（整幅 cache）峰值 ≈981 MB | ★★★★☆ | RSS 实测（§4.3）；余量不足，已改为逐块读 |
| 跨块状态与 meta 聚合可逐位复现 | ★★★★☆ | 代码逐行核对（§5）；需 Step 9 实测锁定 |
| 默认块长 60 | ★★★☆☆ | 单点实测；U-3 待多块长读数 |

**外部引用验证（2026-11-24 WebFetch）**：

| # | 引用 | 版本/页面 | 验证点 |
|---|---|---|---|
| R-1 | NumPy `numpy.savez` | NumPy 2.5.0 文档 | 未压缩 `.npz` = zip + 每成员 `.npy`；`savez` 的 `allow_pickle` 默认 True（安全/可移植性说明） |
| R-2 | NumPy `numpy.load` | NumPy 2.5.0 文档 | `allow_pickle` 默认 **False**；`mmap_mode` 适用于 `.npy`；`.npz` 返回 `NpzFile` 且必须关闭 |
| R-3 | pandas `read_pickle` | pandas 3.1.1 文档 | 整对象反序列化；无部分读取接口；仅保证当前/上一 major 版本兼容 |
| R-4 | Python `pickle` 文档 | Python 3 文档 | 反序列化不可信数据可执行任意代码（安全告警） |

---

## 10. 对设计的输入（摘要）

1. **D1 离线缓存**：格式、键、校验（mtime/size）、回退、迁移脚本 IO 契约。
2. **D2 流式 plan/build**：worker 不保留 float 面板整幅缓存（逐块读 pkl）；全样本 mode/coverage 先解析；关键帧/name carry；meta 聚合表。
3. **D3 分片 apply**：state 结构、`locked_until` 绝对索引、块首 target/prev、turnover 含空头腿、carried 末块。
4. **D4 引擎流式分支**：仅 worker 启用；IC/LS 整幅（保留 hstack）；mismatch 分块；默认路径零改动。
5. **D5 逐位门禁**：P-022 4 fixture + TP6-11 + 全样本默认 SHA + 块长参数化用例。
6. **D6 预算**：M-2 ≤1024 MB、M-3 ≤1024 MB、M-1 ≤30 s；失败时按 U-2 处置，不得静默放宽。

---

## 11. Step 2 核验记录（2026-11-24）

| # | 检查项 | 读数/处置 |
|---|---|---|
| 1 | 代码锚点 | 12 处锚点逐条 `Read` 复核，行号与描述一致（loader L254/L269/L103、inputs L87/L238/L259、tradability L443/L582、engine L280/L309/L353、runner L34） |
| 2 | 数值自洽 | 1475/60 → 25 块；6×64.3+16.3≈402 MB ≈ cache deep 396.8（差值=标签/浮点取整）；1475×5688×8 B=67.1 MB/面板；fwd 67.1 MB |
| 3 | 与 P-022 台账对齐 | M-2 1249.4 MB、M-3 2463.5 MB、cache 430.7 MB、build 15.64 s 均与 P-022 CHECKLIST §6 一致 |
| 4 | 外部引用 | R-1~R-4 均于 2026-11-24 WebFetch 复核（NumPy 2.5.0 / pandas 3.1.1 / Python 3 文档） |
| 5 | 探针可复现 | 4 个探针脚本与命令见 §2.1；输出 JSON 已留存在会话记录，关键读数写入 §4 |
| 6 | 发现与处置 | P3-① 初稿称 suspend “object/bool 混用” → 实测本数据根全 object，已订正；P3-② `mmap` 表述过宽 → 改为“文档示例仅针对 `.npy`”；P3-③ cache deep 未区分 name npz → 已标注 34 MB 另计 |

**结论**：PASS（自查·单视角，0×P1 / 0×P2 / 3×P3 已就地订正）。

---

**Review 签字**: 主会话机械核验（Step 2，2026-11-24）。
