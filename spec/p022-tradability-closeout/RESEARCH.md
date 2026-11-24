# 调研文档：P-022 tradability 收口包

---
id: p022-tradability-closeout-RESEARCH
type: design
version: 1.2
status: verified
date: 2026-11-23
depends: [p021-tradability-production-enablement]
upstream: null
---

> **Feature**: P-022（P-021 遗留四项收口：P-2 内存 / U-7 阈值 / U-8 阈值 / R-3 敏感性）
> **创建日期**: 2026-11-23
> **状态**: verified（Step 1-2 完成；Step 2 自查 + 机械核验 PASS，记录见 §9；**v1.2 = Step 10 审计 A-3 订正**：§4.5/§5.4 的 R-3 数字改为 Step 9 脚本口径）
> **Spec 步骤**: Step 1-2
> **批次档位**: **T1**（触及 `backtest/` 运行时、`tests/`、`scripts/`；判档规则见 `spec/SPEC_PROCESS.md`「批次档位与裁剪理由」第 1 条）
> **裁剪理由**: 不降档。P-2 改变 loader/builder 的内存布局与缓存契约，属启用态运行路径；U-7/U-8 为阈值裁决，需可复现读数与回归；R-3 只产出敏感性证据、不改代码。

---

## 1. 调研目标

**核心问题**：

1. P-021 遗留的 **P-2（并行 worker RSS 3348 MB > 1 GB）** 由哪些对象构成？在不改变任何数值结果（默认路径与启用路径逐位一致）的前提下，哪些可以消除或压缩？目标 ≤1 GB 是否可达？
2. **U-7**：`TradabilitySpec.min_coverage=0.99` 在真实数据根上是否会误降级/误升级？应保留还是改值？
3. **U-8**：`close_mismatch_cells`（`inputs.close` vs 引擎 `price_data['close']`）在标准数据源上的实测值是多少？阈值应如何裁决（仅披露 / 告警 / 阻断）？
4. **R-3**：启用 tradability 后 `turnover` 变化是否会改变健康度拥挤度判定（阈值 0.80）或漂移判定（turnover 权重 0.20）？是否需要为健康度/漂移阈值做敏感性调整？

**非目标**：B 批收益层（`long_short_returns`/`spread` 改用 effective 权重，口径未定）；`stk_limit` 外部一致率（U-1，token 阻塞）；`data_contract.py` 单位修正；空头腿/分钟级撮合。

---

## 2. 调研方法

### 2.1 工具与通道

| 工具 | 用途 | 查询/对象 |
|---|---|---|
| Read / Grep | 仓内代码事实（E1） | `tradability_loader.py` / `tradability_inputs.py` / `tradability.py` / `engine.py` / `parallel_runner.py` |
| Python 只读探针（临时脚本，工作区外） | 真实数据根实测（E1） | 面板体积、构建峰值、月度覆盖率、close 对拍、3 因子健康度/漂移敏感性 |
| pandas/numpy 微探针（E1） | 拷贝语义验证 | `reindex` / `fillna` / `astype` / `to_numpy` / `np.ix_` 的 `shares_memory` |
| 外部锚点 | 背景约束（非决定性） | pandas `reindex`/`to_numpy` 文档、NumPy 索引文档、Python `multiprocessing` spawn 文档（沿用 P-021 X-3/X-5） |

### 2.2 范围与基线

- 包版本：**3.10.0**（P-021 已提交 `d96dc7c`）；本批目标 **3.10.1**（patch）。
- 数据根：`E:\Ashare_data\market_data`，实测面板 `close` = **1475 交易日 × 5688 代码**（2020-01-02 ~ 2026-01-30，8,389,800 格）；`name` 面板为 1474×6053。
- 约束：零新增运行时依赖；`report` 9 键 / `meta` 13 键冻结；默认路径与启用路径数值逐位不变。

---

## 3. 现状事实（E1）

### 3.1 P-2 内存构成

| # | 位置 | 事实 |
|---|---|---|
| F-1-1 | [tradability_loader.py L26-L27](../../backtest/tradability_loader.py#L26-L27) | `_PANEL_CACHE` 为进程内全局 dict，key=`(data_root, panel_dir, name)`，value 为**整帧 DataFrame**（全历史 × 全代码） |
| F-1-2 | [tradability_loader.py L71-L76](../../backtest/tradability_loader.py#L71-L76) | 每次 `build` 读取 8 个面板：`high/low/open/volume/adj/suspend/name/list_date`；`close` 另读 |
| F-1-3 | [tradability_loader.py L189-L193](../../backtest/tradability_loader.py#L189-L193) | `_slice` 对每个面板执行 `frame.reindex(index=index, columns=codes)`；即使标签完全相同也产生新对象（微探针 `reindex_same_shares=False`） |
| F-1-4 | [tradability_inputs.py L23-L27](../../backtest/tradability_inputs.py#L23-L27) | `_frame` 对已对齐面板再做 `reindex → fillna → astype` 三连拷贝（`fillna_nan_shares=False` / `astype_same_shares=False`） |
| F-1-5 | [tradability_inputs.py L43-L47](../../backtest/tradability_inputs.py#L43-L47) | `_normalize_panel`（`adj/limit/ref`）同样经 `_panel(...).to_numpy()`，`adj` 再拷一份 |
| F-1-6 | [tradability_inputs.py L115-L137](../../backtest/tradability_inputs.py#L115-L137) | `name` 全程 object：`ffill().fillna("")` + 逐列 `str(v)` 推导 `is_st`/`is_delisting`（567 MB 常驻 + 每次 build 的字符串运算） |
| F-1-7 | [tradability_inputs.py L50-L71](../../backtest/tradability_inputs.py#L50-L71) | `suspend` 为 object（`'S'/'R'/None`），`_suspend_mask` 按列 `astype(object).eq("S")`，192 MB 常驻 |
| F-1-8 | [parallel_runner.py L44-L76](../../backtest/parallel_runner.py#L44-L76) | worker 入参含**完整** `factor_data` 与 `price_data`；每个因子再 `spec.build(cd, cs)`（按该因子交集切片） |
| F-1-9 | [parallel_runner.py L228-L231](../../backtest/parallel_runner.py#L228-L231) | 每个 worker chunk 都携带完整 `factor_data`（而非仅本 chunk 的因子），spawn 序列化/常驻成本按“全部因子”计 |
| F-1-10 | [tradability.py L428-L451](../../backtest/tradability.py#L428-L451) | `apply` 另分配 `target_all`（next_open）与 `pct_mat`；`ref` 由 builder 提供的 `inputs.ref` 传入，不重复计算 |
| F-1-11 | [engine.py L317-L331](../../backtest/engine.py#L317-L331) | 引擎另建 `prev_close`（T×N）与 `effective = effective_long + min(positions,0)`（再一份 T×N） |
| F-1-12 | [engine.py L337-L338](../../backtest/engine.py#L337-L338) | `close_mismatch_cells = count_nonzero(~isclose(inputs.close, self._close, equal_nan=True))`；`self._close` 来自 `data_loader.price_data['close']`（[L101](../../backtest/engine.py#L101)） |

### 3.2 U-7 阈值

| # | 位置 | 事实 |
|---|---|---|
| F-2-1 | [tradability_loader.py L208-L229](../../backtest/tradability_loader.py#L208-L229) | `open/prev` 覆盖 < `min_coverage` → `off`；`full` 另需 `high_low ≥ min_coverage` 且 `has_adj` |
| F-2-2 | [tradability_loader.py L47](../../backtest/tradability_loader.py#L47) | 默认 `min_coverage=0.99`（P-021 DESIGN §11.1 当前倾向 99%） |
| F-2-3 | [tradability_inputs.py L261-L271](../../backtest/tradability_inputs.py#L261-L271) | 覆盖口径：`eligible = isfinite(close) & ~suspend`；`prev` 排除 t=0 |
| F-2-4 | [CHECKLIST.md §6 P-1/P-2](../p021-tradability-production-enablement/CHECKLIST.md#L143-L150) | P-021 全样本读数：`high_low=1.0 / open=1.0 / prev=0.9984`，`mode=full`；P-2 内存超预算登记 |

### 3.3 U-8 阈值

| # | 位置 | 事实 |
|---|---|---|
| F-3-1 | [engine.py L337-L338](../../backtest/engine.py#L337-L338) | mismatch 仅写入 `diagnostics`，无阈值、无告警、无阻断 |
| F-3-2 | [p021 IMPLEMENTATION §11.2](../p021-tradability-production-enablement/IMPLEMENTATION.md#L657-L662) | U-8 登记为「`close_mismatch_cells` 阈值（E0；当前只披露不阻断）」 |
| F-3-3 | [pipeline_integration.py L144-L152](../../backtest/pipeline_integration.py#L144-L152) | 管道将 `price_data`（来自调用方）交给引擎，同时用其 index/columns 构建 spec；二者同源时 mismatch 应为 0 |

### 3.4 R-3 消费链

| # | 位置 | 事实 |
|---|---|---|
| F-4-1 | [health_bridge.py L120-L127](../../backtest/health_bridge.py#L120-L127) | `_map_crowding_metrics`：`turnover = nanmean(engine_result['turnover'])` |
| F-4-2 | [health_bridge.py L183-L193](../../backtest/health_bridge.py#L183-L193) | 拥挤度得分 = `_normalize_score(turnover, best=0.0, worst=1.0)` → `100×(1−turnover)`（截断 [0,100]） |
| F-4-3 | [health_bridge.py L361-L372](../../backtest/health_bridge.py#L361-L372) | 拥挤度告警阈值 `crowding_turnover_threshold=0.80`（[health.py L69](../../modules/factor_fingerprint/core/health.py#L69)） |
| F-4-4 | [health.py L93-L99](../../modules/factor_fingerprint/core/health.py#L93-L99) | 综合健康分权重：efficacy 0.35 / **crowding 0.25** / capacity 0.15 / decay 0.15 / regime 0.10 |
| F-4-5 | [unified_drift.py L30-L52](../../backtest/unified_drift.py#L30-L52) | 漂移权重：structure 0.45 / performance 0.35 / **turnover 0.20**；阈值 warning 15 / drift 30 / severe 50（管道覆盖为 30/50/70） |
| F-4-6 | [unified_drift.py L225-L249](../../backtest/unified_drift.py#L225-L249) | `turnover_drift = max(0, (late/early − 1))×100`；前后半段均值 |
| F-4-7 | [health.py L423-L456](../../modules/factor_fingerprint/core/health.py#L423-L456) | 健康等级：≥3 维告警 → CRITICAL；1-2 维 → WARNING；无告警且 score<60 → WATCH；否则 HEALTHY |

---

## 4. 实测读数（E1，2026-11-23）

### 4.1 面板体积与构建峰值

数据根：`E:\Ashare_data\market_data`；`close` 1475×5688（8,389,800 格）；`name` 1474×6053。

| 对象 | 文件 MB | `memory_usage(deep=True)` MB |
|---|---|---|
| `stock_close/high/low/open/volume.pkl` | 64.08 ×5 | **64.1 ×5** |
| `stock_adj.pkl` | 60.59 | **60.6** |
| `stock_suspend.pkl` | 8.1 | **192.4**（object） |
| `stock_name.pkl` | 97.32 | **567.1**（object） |
| **`_PANEL_CACHE` 合计** | — | **1140.1**（实测直接求和；上表各行四舍五入，逐行相加有 ±0.5 MB 舍入差） |

| 指标 | 读数 |
|---|---|
| `spec.build` 全样本耗时 | **22.43 s**（P-021 P-1 预算 ≤30 s，仍满足） |
| `tracemalloc` 构建峰值 | **2585.1 MB** |
| 进程 RSS（build 前 → build 后） | **294.4 → 2201.3 MB** |
| 清空 `_PANEL_CACHE` 后 RSS | **816.9 MB** |
| `TradabilityInputs` 数组合计 | **464.1 MB**（close/high/low/open/volume/adj/ref/suspend/no_limit） |
| 构建模式 / 覆盖 | `full`；`high_low=1.0`、`open=1.0`、`prev=0.9984`、`eligible=7,203,655` |

**口径说明**：P-021 记录的 **worker RSS 3348 MB** 为并行 worker 内实测（含引擎与数据载荷），本表为**构建路径单进程**复现（2201 MB）；两者不矛盾，但说明“≤1 GB”必须同时约束 **面板缓存 + 构建中间数组 + worker 载荷**，只压缩构建峰值不够。

### 4.2 拷贝语义微探针

| 操作 | `np.shares_memory` | 含义 |
|---|---|---|
| `df.to_numpy()` | **True** | float64 C 连续时是视图，可零拷贝下传 |
| `df.reindex(index=df.index, columns=df.columns)` | **False** | 即使标签相同也复制（当前 `_slice`/`_frame` 的隐式成本） |
| `df.fillna(np.nan)` | **False** | `_frame` 的填充步骤必然复制 |
| `df.astype(float)`（同 dtype） | **False** | `_frame` 的 astype 也复制 |
| `arr[np.ix_(rows, cols)]` | **False** | 子集切片必须复制（全量命中可走同对象快路径） |

### 4.3 U-7 月度覆盖（73 个月，2020-01 ~ 2026-01）

| 口径 | 最小值 | 最大值 | 低于 0.99 的月份 |
|---|---|---|---|
| `high_low` | **1.000000** | 1.000000 | 无 |
| `open` | **1.000000** | 1.000000 | 无 |
| `prev` | **0.994429**（2020-04） | 0.999880（2024-02） | 无 |

- 73/73 月解析为 **`full`**；`execution_only_open=0`、`off=0`。
- 年度 `prev` 最低值：2020 **0.994429** / 2021 **0.995562** / 2022 **0.996558** / 2023 **0.999060** / 2024 **0.999568** / 2025 **0.998924** / 2026-01 **0.999547**。
- `prev` 的最小安全边际 = **0.99 − 0.994429 = 0.004429**（约 0.44 个百分点）。

### 4.4 U-8 close 对拍

| 指标 | 读数 |
|---|---|
| 对拍格数 `inputs.close.size` | **8,389,800** |
| mismatch cells（`np.isclose(..., equal_nan=True)` 取反） | **0** |
| mismatch ratio | **0.000000** |
| 条件 | `inputs.close` 与同一 `stock_close.pkl` 转置得到的 `price_data['close']` |

> 该读数证明“同源时 mismatch=0”，不证明任意调用方 `price_data` 都与标准数据根一致；后者只能在运行期由 `close_mismatch_cells` 披露。

### 4.5 R-3 健康度/漂移敏感性（3 个真实因子，全样本）

| 因子 | turnover 均值（off → on） | 变化 | 拥挤度得分（off → on） | 健康分增量 | 拥挤告警 off/on | turnover_drift（off → on） | 组合漂移增量 | ICIR/LS 一致 |
|---|---|---|---|---|---|---|---|---|
| `mom20` | 0.346440 → 0.345175 | **−0.365%** | 65.36 → 65.48 | **+0.032** | False / False | 4.349 → 4.335 | **−0.0028** | ✅ |
| `rev5` | 0.674831 → 0.660959 | **−2.056%** | 32.52 → 33.90 | **+0.347** | False / False | 0.405 → 0.307 | **−0.0196** | ✅ |
| `vol20` | 0.133388 → 0.133259 | **−0.097%** | 86.66 → 86.67 | **+0.003** | False / False | 0.0 → 0.0 | **0.0000** | ✅ |

> 口径：Step 9 证据脚本 `scripts/verify_tradability_closeout.py --only r3` 实跑（`out/tradability_closeout_r3.json`，`pct_change(fill_method=None)`）。早期只读探针读数（−0.415%/−2.175%/−0.163%，drift ≤0.003）仅用于 DESIGN 初稿，已被本表取代。

- 3/3 因子 **无拥挤度告警翻转**（均远离 0.80）；综合健康分变化 ≤ **0.347**；组合漂移增量绝对值 ≤ **0.020**（远离 warning 30 / drift 50 / severe 70）。
- `rank_icir` 与 `long_short_returns` 逐位一致（`icir_identical=True`、`ls_identical=True`）。

---

## 5. 结论与候选方案

### 5.1 P-2 根因分解

| 根因 | 量级（E1） | 可消除性 |
|---|---|---|
| R1 `name` object 常驻 + 每次 ffill/逐列推断 | **567 MB** 常驻；每次 build 全列字符串运算 | 可消除：按唯一名称编码（8,771 个唯一名 → int16/float32 码）+ 预计算 ST/退市查找表 |
| R2 `suspend` object 常驻 | **192 MB** 常驻（实际仅 `S` 18,242 / `R` 2,700 / None 其余） | 可消除：int8 状态（missing/S/other）+ bool mask |
| R3 `_slice`/`_frame` 对已对齐面板重复拷贝 | 5 个 float 面板 + adj + 每因子 6×64 MB 级 | 可消除：对齐快路径返回同对象；`_frame` 免 `fillna(nan)`/同 dtype `astype` |
| R4 worker 载荷携带全部 `factor_data` | 随因子数量线性增长（每因子 T×N×8 B） | 可消除：仅传本 chunk 因子子集 |
| R5 `apply`/引擎的 T×N 中间数组 | `target_all`+`pct_mat`+`prev_close`+`effective` 副本 | 部分可消除：`effective` 原地累加；`pct` 可按行计算（需逐位验证） |

**候选方案**（供 DESIGN 裁决）：

- **A（基线，不采纳）**：仅调小 worker 数/按内存预算配置。不改变单 worker 峰值，P-2 仍超预算。
- **B（紧凑缓存）**：`name` 仅缓存 float32 码 + 唯一名查找表；`suspend` 缓存 int8/布尔状态；float 面板保持 float64 DataFrame/数组。预计缓存 **1140 → ≈430 MB**。
- **C（零拷贝快路径）**：`_slice` 全量命中返回同对象；`_frame`/`_normalize_panel` 对齐且 float64 且 fill=NaN 时返回原 df；`to_numpy()` 视图下传。预计再省 **≈300-380 MB** 峰值/常驻。
- **D（worker 载荷裁剪）**：`_run_group` 仅把本 chunk 的因子子集与必要 `price_data` 传给 worker。预计按因子数线性节省。
- **E（引擎原地化）**：`effective = effective_long + min(positions,0)` 改 `effective_long += ...`；`pct_mat` 按行计算。预计再省 **≈64-128 MB**。
- **F（分块 apply，不采纳为本批）**：按月/按段流式 apply，内存 O(chunk)。收益最大但需处理 `pending/locked_until` 跨块状态，风险高，且会把本批从“收口”扩大到架构改造。

**目标可达性判断**：B+C+D+E 后，单 worker（1 因子、全样本）稳态估算 = 缓存 ≈430 + inputs 增量 ≈100 + 引擎/应用 ≈500 + 数据载荷 ≈190 ≈ **1.2 GB**；再叠加 E 的 `pct` 行计算与原地化可压到 **≈1.0-1.1 GB**。因此 DESIGN 需把“≤1 GB”绑定到明确的度量口径（构建后稳态 + 单因子 apply 峰值），并在 Step 9 实测；若仍略超，优先追加 E，不引入 F。

### 5.2 U-7 裁决建议

- **保留 `min_coverage=0.99`**。73/73 月 `full`，`prev` 最低 0.994429，无一个月触发降级/升级；0.99 在当前数据根上是“不误降级”的下界，且与 D0 分级口径一致。
- 不新增/不改默认值；将上述月度读数写入文档与回归脚本，作为后续数据更新后的复标定基线。若未来 `prev` 跌破 0.99，`off` 是**预期行为**（无法可靠计算昨收），不是缺陷。

### 5.3 U-8 裁决建议

- 实测同源 **0 / 8,389,800**。**阈值裁定为 0 容忍 + 仅披露**：任何 `close_mismatch_cells > 0` 表示调用方 `price_data` 与标准数据根不同源，属**调用方契约问题**，不应在引擎内静默阻断（会误伤合法的自定义价格源）。
- 建议在设计与文档中明确：`close_mismatch_cells` 为诊断键；若 `>0`，报告使用者应检查 `price_data` 来源；本批不新增门禁、不改 9/13 键。

### 5.4 R-3 裁决建议

- 3 个真实因子实测：turnover 变化 **−0.10% ~ −2.06%**，健康分变化 **≤0.347**，拥挤告警 **0/3 翻转**，组合漂移增量绝对值 **≤0.020**。**不调整健康度/漂移阈值**，不新增代码门禁；把敏感性表纳入文档与可复现脚本，作为“turnover 口径变更不影响健康度/漂移结论”的证据。
- 若未来出现靠近 0.80 的因子，仍按既有告警语义处理；本批不引入“tradability-aware 阈值”。

---

## 6. 未决项登记

| ID | 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|---|
| U-1 | `stk_limit` 外部一致率 | token 到位 | 保持 `fallback_raw` + 披露 | E0 |
| U-2 | 内存优化后 worker 实测 | Step 9 | B+C+D+E 组合，目标 ≤1 GB；不足则追加 E | E1（本批复测） |
| U-3 | `close_mismatch_cells > 0` 的真实调用方样例 | 出现非标准 `price_data` | 仅披露，不阻断 | E0 |
| U-4 | 健康度/漂移阈值是否需按 turnover 口径重标定 | 出现告警翻转 | 本批结论：不重标定 | E1（3 因子） |

---

## 7. 外部锚点与可复核性

| # | 源 | 层 | 锚点 | 用途 |
|---|---|---|---|---|
| X-1 | pandas `DataFrame.reindex` 文档 | T1 | 返回新对象；标签不同时填充缺失 | 解释 F-1-3 的复制成本（并以微探针 E1 验证同标签也复制） |
| X-2 | pandas `DataFrame.to_numpy` 文档 | T1 | `copy=False` 时尽可能返回视图 | 零拷贝下传的前提（E1：float64 C 连续时 shares=True） |
| X-3 | NumPy 索引文档 | T1 | 基础索引返回视图；高级索引（`np.ix_`）返回副本 | 子集切片必须复制，全量命中才可同对象 |
| X-4 | Python `multiprocessing` 文档 | T1 | Windows 默认 spawn；入参需 pickle；子进程重新导入模块 | worker 载荷裁剪（D）的约束 |
| X-5 | P-021 锚点 X-3/X-5 | T1 | 同上 | 沿用，不重复论证 |

**可复核性**：第 4 节全部读数为本机 E1 实测，脚本命令与输出路径记录于 Step 9 实施文档；外部文档仅用于解释机制，不承载“数值结论”。

---

## 8. 充分性自检

- [x] 四个核心问题均有 E1 读数（P-2 构成/峰值、U-7 73 月、U-8 对拍、R-3 3 因子）。
- [x] 每个结论标注证据等级；未把机制解释写成实测结论。
- [x] 关键代码事实带文件 + 行号。
- [x] 未决项按四元登记（判据/触发/倾向/等级）。
- [x] 非目标明确（B 批、U-1、单位修正、空头腿、分钟级）。
- [x] 外部锚点 ≥3 条，且与机制解释对应。
- [x] Step 2 自查 + 机械核验 PASS（§9）；独立只读通道未产出有效裁决，已如实登记，Step 4 复审改用独立只读子代理补强。

---

**Review 签字**: Step 2 自查 + 机械核验 PASS（15 组代码锚点逐条比对、第 4 节读数与探针输出逐项一致） 日期: 2026-11-23

---

## 9. Step 2 复核记录（自查 + 机械核验）

| # | 检查 | 结果 |
|---|---|---|
| R-1 | 代码锚点：`tradability_loader.py` L26/L47/L71/L189/L208、`tradability_inputs.py` L23/L43/L50/L115/L261、`tradability.py` L428/L445、`engine.py` L101/L317/L337、`parallel_runner.py` L44/L228、`health_bridge.py` L120/L183/L361、`health.py` L69/L93/L423、`unified_drift.py` L30/L225 | ✅ 15 组逐条命中描述内容 |
| R-2 | 第 4 节读数与探针输出 | ✅ 1140.1 / 567.1 / 192.4 / 2585.1 / 2201.3 / 464.1 / 22.43 s / 8,389,800 / 0 / 73 月全 full / prev min 0.994429 逐项一致 |
| R-3 | 算术自洽 | ✅ 安全边际 0.004429；P-2 估算 430+100+500+190≈1.2 GB；年度最低值与月表一致；合计行已补舍入说明 |
| R-4 | 证据等级诚实性 | ✅ 机制解释与 E1 实测分列；`close_mismatch=0` 明确限定“同源”条件，不外推任意调用方 |
| R-5 | 外部锚点层级 | ✅ X-1~X-4 为 T1 官方文档，仅作机制解释；决定性数值均来自 E1 |

> **独立复核说明**：Step 2 曾尝试由只读子代理复核，但该通道返回检索片段而非裁决；本文件不据此宣称“独立复核通过”。Step 4（DESIGN）将使用独立只读子代理完成异构复审。

