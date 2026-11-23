# 设计文档：P-021 tradability 生产启用

---
id: p021-tradability-production-enablement-DESIGN
type: design
version: 1.4
status: verified
date: 2026-11-23
depends: [p021-tradability-production-enablement-RESEARCH]
upstream: null
---

> **Feature**: P-021 tradability 生产启用（C 内部对拍 + A 证据层）
> **创建日期**: 2026-11-23
> **状态**: verified（Step 3-4 完成；Step 4 复审链已处置（§9.4-§9.7）；Step 8 一致性复审 PASS_WITH_FIXES 已处置（§9.8）；**Step 10 独立 ADD 审计 PASS_WITH_FIXES 已处置（§9.9：1×P1/2×P2/5×P3）**）
> **Spec 步骤**: Step 3-4
> **基于调研**: [RESEARCH.md](./RESEARCH.md)（v1.1 verified）
> **批次档位**: **T1**（Layer-1：`backtest/` + `tests/` + `scripts/`）
> **决策确认**: 2026-11-23 用户确认 **D1 `next_open` / D2 `fallback_raw` / D3 规则前移 2020-07-27 / D4 只披露 / D5 条件性 `stk_limit`**；同日确认新增 **D6 数据不足降级模式 `execution_only_open`**。

---

## 1. 设计目标

把已在 P-006/P-020 交付但**默认关闭、未接生产**的 tradability 能力，按已确认的 D1-D6 启用为「证据层」：只改变 `turnover` 并新增披露块，**不改变 IC / spread / `long_short_returns`**。本设计覆盖 **C 批（内部一致性对拍）→ A 批（数据装载 + 引擎开关 + 管道/并行接线 + 报告块）**；B 批（收益层）不在本设计内。

**一句话**：让生产回测能在不引入外部 token 的前提下，用本地 OHLCV + `adj` + 名称/停牌面板跑出可复核的 tradability 读数；数据不足时按 **D6 `execution_only_open`** 显式降级为 T+1 开盘成交（限价能算就算），并为未来 `stk_limit` 留出零改签名的覆盖入口。

## 2. 设计依据

### 2.1 调研结论 → 设计决策

| 调研发现 | 设计决策 | 引用 |
|---|---|---|
| R-1/R-2：启用只改 `turnover` + 新增块 | 引擎仍只在 `tradability_inputs != None` 时启用；指标路径零改动 | RESEARCH §4.1 |
| R-5：管道只传 close、并行未接线 | 新增 `TradabilitySpec` + 管道/并行可选入参；默认 `None` 零变更 | RESEARCH §3.1/§4.1 |
| R-10/O-9：bse 2020-01-02 抛 `ValueError` | **D3** 规则前移 2020-07-27；更早 → gap + unknown，不抛错 | RESEARCH §4.3/§4.4 |
| O-8/T-9：`execute_at` 声明未消费 | **D1** 实现 `next_open`；库默认改 `same_close`，生产 loader 显式 `next_open` | RESEARCH §4.4 |
| O-2/U-2：`adj` 缺 81 日 | **D2** 原始昨收回退 + 计数披露；token 到位后 `stk_limit` 覆盖 | RESEARCH §4.2/§5.6/§5.7 |
| O-1/T-4：一字仅占触板 5.46% | **D4** 只披露 `one_word_*` + 三态触达计数；不做一字-only | RESEARCH §4.4 |
| O-7/T-10：`'R'` 被当停牌 | 构建器只把 `'S'` 映射为停牌；`'R'` 可交易 | RESEARCH §4.3 |
| D0-D5 分级 | 新增 `diagnostics` 子块（`data_tier/missing_fields/bias_direction`），**不改 report 9 键 / meta 13 键** | RESEARCH §4.2 |
| U-2 已验证不可得；开源无全量替代 | C 批降级为内部一致性 + 规则边界；`stk_limit` 仅留可选 CSV/Parquet 入口 | RESEARCH §5.6/§5.7 |
| 当前无「数据不足自动降级」；`high/low` 缺失会静默放行 | **D6** 新增 `mode ∈ {full, execution_only_open, off}`；`execution_only_open` 用 T+1 开盘成交，缺 `high/low` 跳过一字诊断，缺 `adj` 用昨收，`open/prev` 面板不足则 `off` | RESEARCH §4.2 D5 收窄注记 + D6 用户确认（2026-11-23）；落点 §5.10 |

### 2.2 相关 ADR

| ADR | 决策 | 对本设计的影响 |
|---|---|---|
| ADR-0010 | Layer 判定三问 | 触及 `backtest/`、`tests/`、`scripts/` → T1 |
| ADR-0004（spec 流程） | 四件套 + Review 门禁 | 本批全流程执行 |
| ADR-0002（职责边界） | 显式声明不覆盖域 | B 批收益层 / 空头腿 / 分钟级不纳入 |

### 2.3 职责边界

- **职责内**：`TradabilityPolicy` 的执行时点与未知限价策略；`apply_tradability` 的 `next_open` 语义；构建器的停牌/降级/分级/规则 gap；`TradabilityInputs` 的可选 `ref/limit_up/limit_down/codes/diagnostics`；标准数据根 loader；管道与并行运行器的可选接线；报告块 v2。
- **职责外**：`long_short_returns`/`spread` 改用 effective 权重（B 批）；空头腿券源/成本；分钟级撮合；`stk_limit` 的在线拉取与 token 管理；`data_contract.py` 的 `return` 单位修正。
- **能力边界**：无法在无 token 时证明自算限价与交易所逐格一致；本设计只交付**内部一致性 + 规则边界 + 格式适配**，外部一致率留 V-8。
- **能力边界补充**：完全缺 `adj` 且未提供 `ref` 时 fail-closed；loader 可用 `ref=prev` 降级（D6）。空头腿不后移，`turnover` 仍按 `effective_long_only` 披露。

## 3. 架构设计

### 3.1 整体架构

```
E:\Ashare_data\market_data/*.pkl
        │  TradabilitySpec.build(dates, codes)   ← 进程内面板缓存
        │  mode 解析：full / execution_only_open / off
        ▼
build_tradability_inputs ──► TradabilityInputs{ref, limit_up/down, diagnostics}
        │                              │
        │                              ├─► apply_tradability_with_diagnostics
        │                              │      ├─ same_close（库默认，兼容）
        │                              │      ├─ next_open（生产 full）
        │                              │      └─ execution_only_open（降级：open 成交）
        ▼                              ▼
PipelineBacktestRunner / ParallelFactorRunner
        │
        ▼
FactorBacktestEngine ──► result['tradability']{report, meta, diagnostics, 4 口径键}
                           └─ turnover 变化；IC/spread/LS 不变
```

### 3.2 模块划分

| 模块 | 职责 | 输入 | 输出 | 依赖 |
|---|---|---|---|---|
| `tradability.py`（改） | 规则表、`next_open`、外部限价覆盖、诊断 | 面板数组 + policy | `(effective, report[, diagnostics])` | numpy |
| `tradability_inputs.py`（改） | 面板 → inputs/meta/diagnostics | 10 个面板 | `(inputs, meta)` | pandas/numpy |
| `tradability_loader.py`（新） | 标准数据根读取、对齐、模式解析、可选限价表 | `data_root/dates/codes` | `(inputs, meta)` | pandas |
| `pipeline_integration.py`（改） | 单跑接线 | `tradability_spec` | 透传 engine | 无新依赖 |
| `parallel_runner.py`（改） | 逐因子切片接线 | `tradability_spec` | 透传 engine | 无新依赖 |
| `engine.py`（改） | 块 v2 + 校验 | `tradability_inputs` | `result['tradability']` | 无新依赖 |

### 3.3 数据流（D5 顺序 + D6 模式）

0. **模式解析**：`TradabilitySpec` 按 `mode/auto_degrade/min_coverage` 解析为 `full / execution_only_open / off`；`off` 直接返回 `None`（旧路径）。
1. **停牌**：`stock_suspend` → 仅 `'S'` 为 True；`'R'`/缺失为 False；缺失格计数。
2. **`adj` 参考价**：`ref = prev × adj[t-1] / adj[t]`；单侧缺失且 `unknown_policy="fallback_raw"` → `ref = prev` 并计数；`"pass"` 保持 NaN（legacy）。
3. **ST / 退市**：`stock_name` 先按日前向填充，再 `ST`/`退` 字符串判定；缺失格/日计数。
4. **上市日**：`list_date` → IPO 前 5 日 `no_limit`；缺失 → D4 披露。
5. **`stk_limit`（条件性）**：若提供 CSV/Parquet 快照，逐格覆盖自算 `up/down`；缺失格回退自算并计数；无 token 时不触发。

> 与 D5 表述一致：当前无 token，实际执行顺序为 **停牌 → `adj` 回退 → ST/退市 → 上市日**；`stk_limit` 为前置可选层。

### 3.4 控制流

- **C 批**（验证前置）：`scripts/verify_tradability_consistency.py` 产出内部一致率 JSON；单测覆盖规则边界与 mock 限价表扰动。
- **A 批**（生产启用）：调用方构造 `TradabilitySpec()` → `PipelineBacktestRunner(..., tradability_spec=spec)` 或 `ParallelFactorRunner(..., tradability_spec=spec)` → 引擎挂载块。
- 默认 `tradability_spec=None` / `tradability_inputs=None` → 旧路径逐位不变。

## 4. 接口定义

### 4.1 `TradabilityPolicy`（字段扩展，默认值兼容）

```python
@dataclass(frozen=True)
class TradabilityPolicy(object):
    execute_at: str = "same_close"      # next_open | same_close
    t_plus_1: bool = True
    renormalize: bool = False
    eps: float = _EPS
    unknown_policy: str = "pass"        # pass | fallback_raw | block
    mode: str = "full"                  # full | execution_only_open | off
```

- **默认值变更说明**：`execute_at` 原默认 `"next_open"` 但从未被消费，实际行为等于 `same_close`；本设计把默认值改为 `"same_close"`，使「默认=旧行为」成立。生产 `TradabilitySpec` 显式 `execute_at="next_open", unknown_policy="fallback_raw", mode="full"`。
- 非法值：`execute_at not in {...}` / `unknown_policy not in {...}` / `mode not in {...}` → `ValueError`；`mode=="execution_only_open"` 要求 `execute_at=="next_open"`。
- `unknown_policy`：`pass` 未知放行+计数（legacy）；`fallback_raw` 用昨收回退；`block` 仅用于无基准极端格（不作为 81 日缺口默认）。

### 4.2 `apply_tradability_with_diagnostics`（新增；`apply_tradability` 保留 2 元组）

```python
def apply_tradability_with_diagnostics(
    target_w, prev_close, high, low, close, open_, volume, suspended,
    board, is_st, dates, policy=None, adj=None, is_delisting=None,
    no_limit=None, ref=None, limit_up=None, limit_down=None,
):
    """返回 (effective_w, report, diagnostics)；report 九键恒 int。"""

def apply_tradability(...):  # 签名同 v3.9.10 + limit_up/limit_down 关键字
    """兼容包装：返回 (effective_w, report)。"""
```

**`next_open` 语义**：

| 项 | `same_close`（默认） | `next_open`（生产） |
|---|---|---|
| 目标权重 | `target_w[t]` | `target_w[t-1]`；`t=0` 补 0 |
| 执行价 | `high[t]/low[t]` | `open_[t]/open_[t]` |
| 买入封锁 | `high >= up - eps` | `open >= up - eps` |
| 卖出封锁 | `low <= down + eps` | `open <= down + eps` |
| 末信号 | 消费 | 丢弃（不执行） |
| `carried` | 对 `target_w[-1]` | 对 `target_w[-2]`（若有） |
| 执行价缺失 | 按旧「无证据不阻塞」 | **阻塞**并计 `exec_price_missing_cells` |

- `one_word_up/down` 仅在 `mode=="full"` 时按**执行日** `high==low` 与限价判定（D4）；`execution_only_open` 下保留键但计 0，并置 `one_word_disabled=True`。
- `limit_up/limit_down` 同时提供时：跳过 `_pct_matrix`，`up/down` 直接取表；`unk = ~finite(up)|~finite(down)`；`limit_table_source="stk_limit"`。
- **`execution_only_open`**：仍按 `next_open` 后移目标与 `open` 判定；`high/low` 可为 NaN（只影响一字诊断，不影响成交）；单格 `open` 非有限 → 阻塞 + `exec_price_missing_cells`；单格 `prev/ref` 不可判定 → `limit_unknown` + `unknown_policy`（`pass`/`block`）。
- **`off`**：引擎不调用推进，返回旧 `turnover`，不挂 `tradability` 块；若直接调用 `apply_tradability_with_diagnostics`（经 `policy.mode="off"`，不经关键字），返回 `(target_w 原样, 9 键全 0 int report, {"mode": "off", "schema_version": 2})`（no-op）。
- `diagnostics` 键：`execution_timing`、`exec_up_touch_cells`、`exec_down_touch_cells`、`high_up_touch_cells`、`low_down_touch_cells`、`exec_price_missing_cells`、`limit_table_source`、`schema_version=2`。
- **空头腿**：引擎仍只对多头腿调用推进；`positions<0` 原样透传（不后移）。`turnover_basis` 保持 `effective_long_only`，负权重存在时属混合口径，已在 `leg_scope` 披露。

### 4.3 `TradabilityInputs`（末尾追加可选字段）

```python
@dataclass(frozen=True, eq=False)
class TradabilityInputs(object):
    # ... v3.9.10 既有 14 字段不变 ...
    ref: np.ndarray = None          # (T,N) 含 fallback 的参考价；None → apply 从 adj 派生
    limit_up: np.ndarray = None     # (T,N) 外部限价表；None → 自算
    limit_down: np.ndarray = None
    codes: np.ndarray = None        # (N,) 代码，用于诊断/对齐
    diagnostics: dict = None        # P-021 诊断块（构建器产出）
```

- 引擎校验：`adj is None and ref is None` → `ValueError`（`mode=="execution_only_open"` 时 loader 会传 `ref=prev`）；`limit_up/down` 必须成对且形状 `(T,N)`；`codes` 若给出须为 `(N,)`。
- 既有 `TradabilityInputs(...)` 关键字构造全部兼容。

### 4.4 `build_tradability_inputs`（签名追加可选参数）

```python
def build_tradability_inputs(close, high, low, open_, volume, suspend, name,
                             adj=None, list_date=None, policy=None,
                             st_overrides=None, limit_up=None, limit_down=None,
                             ref=None):
    """返回 (inputs, meta)；meta 仍为 13 键；diagnostics 挂 inputs.diagnostics。"""
```

**行为增量**：

1. **停牌**：`suspend` 先 reindex，再 `== "S"`；`'R'`/None/NaN → False；`suspend_missing_cells/days` 计数。
2. **名称**：`name` reindex 后按日前向填充；`name_missing_cells/days` 计数；ST/退市判定基于填充后名称。
3. **参考价**：`adj/ref` 至少一个；`ref` 优先。`ref` 未给时 `ref = _ref_from_adj(prev, adj)`；`unknown_policy=="fallback_raw"` 时 `ref = where(~finite(ref) & finite(prev) & prev>0, prev, ref)`；`ref_fallback_cells/days` 计数。`adj` 缺失且 `ref` 未给 → `ValueError`。
4. **规则 gap**：`_pct_matrix(..., return_gaps=True)`；BSE 2020-07-27 前 → `pct=NaN` + gap 计数，不抛错。
5. **限价表**：`limit_up/down` 给出时用于 `one_word_*` 与 inputs 字段；`limit_table_source="stk_limit"`。
6. **诊断**：`data_tier/missing_fields/bias_direction/price_basis_detail/rule_gap_reason/mode` 等写入 `inputs.diagnostics`；`ref` 来自昨收时 `meta["price_basis"]="raw_close"`；`execution_only_open` 下 `meta["one_word_up_cells"]=meta["one_word_down_cells"]=0`；`adj is None` 时 `meta["adj_missing_days"]=T`。

### 4.5 `TradabilitySpec`（新模块）

```python
@dataclass(frozen=True)
class TradabilitySpec(object):
    data_root: str = r"E:\Ashare_data"
    panel_dir: str = "market_data"
    policy: TradabilityPolicy = field(default_factory=lambda: TradabilityPolicy(
        execute_at="next_open", unknown_policy="fallback_raw", mode="full"))
    mode: str = "auto"                  # auto | full | execution_only_open | off
    auto_degrade: bool = True
    min_coverage: float = 0.99
    stk_limit_path: Optional[str] = None

    def build(self, dates, codes):
        """按给定日期/代码对齐读取面板，返回 (TradabilityInputs | None, meta)。"""
```

**模式解析（D6）**：

| 请求 `mode` | 数据条件 | 解析结果 |
|---|---|---|
| `off` | — | `off`；返回 `None`，旧路径 |
| `full` | `high/low/open/prev` 覆盖 ≥ `min_coverage` 且 `adj` 存在（或 `ref` 给出） | `full` |
| `full` | 条件不满足且 `auto_degrade=True` | `execution_only_open`；`degrade_reason` 记录 |
| `full` | 条件不满足且 `auto_degrade=False` | `ValueError`（fail-closed） |
| `execution_only_open` | `open/prev` 覆盖 ≥ `min_coverage` | `execution_only_open`；`high/low` 可缺省，`adj` 缺失用 `ref=prev` |
| `auto` | 满足 `full` 条件 | `full` |
| `auto` | 不满足 `full` 但 `open/prev` 满足 | `execution_only_open` |
| 任意 | `open/prev` 覆盖 < `min_coverage` | `off`；`degrade_reason="open_or_prev_unavailable"` |

- **字段分工**：`TradabilitySpec.mode` 是**请求**；`policy.mode` 是**解析后**结果（`dataclasses.replace` 写入）；`diagnostics.mode/mode_requested` 分别记录两者。
- **覆盖率口径**：`eligible = isfinite(close) & ~suspended`；`high_low/open/prev` 覆盖率均按 eligible 计算，避免停牌/未上市的 NaN 触发误降级；**`prev` 的 t=0 为结构性 NaN，`prev_close_coverage` 分母排除 t=0**（否则 T<100 的并行因子切片必然误降级）。
- 进程内 `_PANEL_CACHE`（模块级 dict）：同一 worker/进程只读一次 pickle，后续按 `dates/codes` reindex。
- `stk_limit_path`：**A 批承诺 CSV**（列 `ts_code, trade_date, up_limit, down_limit`；按 `ts_code[:6]` 映射；缺格回退自算并计 `limit_table_missing_cells`）；Parquet 需探测 pyarrow（沿用 `execution/shell/loaders.py has_pyarrow` 先例），缺失 → `ValueError` 提示改用 CSV，零新增运行时依赖。
- `codes_not_found`：请求但不在 `stock_close` 面板的代码（前 20 个）写入 diagnostics；若全部缺失 → `ValueError`。
- 失败策略：数据根/必需面板缺失 → `ValueError`（fail-closed）；模式不足 → 按上表降级/关闭，**不静默**。

### 4.6 引擎报告块 v2

```python
result['tradability'] = {
    'report': {...9 键 int...},                 # 契约不变
    'meta': {...13 键...},                      # 契约不变
    'diagnostics': {..., 'schema_version': 2},  # P-021 新增
    'price_basis': meta['price_basis'],         # raw_adj_ref 或 raw_close（ref=prev）
    'leg_scope': 'long_only',
    'short_leg_unmodeled': True,
    'turnover_basis': 'effective_long_only',
}
```

- `diagnostics` 合并构建器与推进期字段：`mode`、`mode_requested`、`degrade_reason`、`one_word_disabled`、`high_low_coverage`、`open_coverage`、`prev_close_coverage`、`adj_source`、`data_tier`、`missing_fields`、`bias_direction`、`price_basis_detail`、`unknown_policy`、`ref_fallback_cells/days`、`name_missing_cells/days`、`suspend_missing_cells/days`、`rule_gap_cells/days/reason`、`limit_table_source`、`limit_table_missing_cells`、`limit_table_duplicate_rows`、`codes_not_found`、`close_mismatch_cells`、`execution_timing`、`exec_up_touch_cells`、`exec_down_touch_cells`、`high_up_touch_cells`、`low_down_touch_cells`、`exec_price_missing_cells`。
- `summary()` 不消费新键 → 摘要不变；健康度/漂移仍只消费 `turnover`。

### 4.7 运行器接线

```python
PipelineBacktestRunner(config=None, tradability_spec=None)
ParallelFactorRunner(n_workers=None, tradability_spec=None)
run_parallel(factor_data, price_data, n_workers=None, tradability_spec=None)
```

- 单跑：`run()` 内用 `spec.build(price_data.columns, price_data.index)`（dates, codes），把 inputs 传给 `FactorBacktestEngine`。
- 并行：`_run_worker` 用因子切片后的 `spec.build(cd, cs)`（dates, codes），每 worker 独立缓存。
- `spec=None` → 签名与行为逐位不变（既有测试零改动）。

## 5. 设计决策与替代方案

### 5.1 D1 执行时点（采纳 `next_open`，库默认 `same_close`）

- 做法：`apply_tradability_with_diagnostics` 内部按 policy 生成 `target_all` 与 `exec_price`；`next_open` 时目标后移 1 日、执行价取 `open`。
- 被拒 A：保持默认 `next_open` 并改写全部 19 处 `apply_tradability` 测试。拒绝理由：公共函数默认行为突变，测试与外部调用方大面积改值；代价 = 高 churn + 无收益（生产由 loader 控 policy）。
- 被拒 B：在引擎层先 `positions.shift(1)` 再调用原函数。拒绝理由：`turnover`/`carried`/报告口径分散在两层，难以保证 `one_word` 与 `pending` 一致；代价 = 双源口径。

### 5.2 D2 未知限价（采纳 `fallback_raw` + 计数）

- 做法：构建器生成 `inputs.ref`（含 fallback）；引擎传 `ref=inputs.ref`；diagnostics 记 `ref_fallback_cells/days`、`data_tier="D1"`。
- **完全缺 `adj`**：`mode="auto"/"execution_only_open"` 时 loader 传 `ref=prev`（`price_basis="raw_close"`、`adj_source="none"`），仍可运行；`mode="full"` 且 `auto_degrade=False` → `ValueError`。
- 被拒 A：未知即整日封锁。拒绝理由：403,499 格缺口日会被 100% 过度封锁；代价 = 系统性低估交易能力。
- 被拒 B：保持现状放行且不披露。拒绝理由：缺口日在缺口期承载约 24.9% 跌停触板，无披露会误导；代价 = 结论不可复核。
- 被拒 C：仅依赖 `stk_limit`。拒绝理由：U-2 已验证不可得；代价 = 生产永远无法启用。

### 5.3 D3 北交所早期（采纳规则前移 + gap）

- 做法：`bse` 规则 `effective_from="2020-07-27"`（精选层 30% 近似）；更早 → `_pct_matrix` 留 NaN + `rule_gap_reason="neeq_pre_select"`；`apply` 计 `limit_unknown`。
- 被拒 A：裁剪 2020-07-27 前 bse。拒绝理由：丢失 8,792 格 / 194 只（全样本 0.13%）；代价 = 样本选择偏差。
- 被拒 B：建模 NEEQ 竞价/做市逐股方式。拒绝理由：需逐股交易方式表，成本高且仅 0.13%；代价 = 超出证据层范围。
- 被拒 C：保留 2021-11-15 起点。拒绝理由：2020-07-27~2021-11-15 的 29,187 格精选层会全部 unknown；代价 = 无谓缺口。

### 5.4 D4 三态（采纳只披露）

- 做法：保留 `one_word_up/down`（report）+ `exec_*/high_*` 触板计数（diagnostics）；不新增 `limit_mode` 行为；`execution_only_open` 下一字诊断关闭并披露。
- 被拒 A：一字-only 封锁。拒绝理由：一字仅占触板 5.46%，会把约 94% 触板格与 32% 炸板日错误处理；代价 = 过度保守。
- 被拒 B：按开盘/盘中三态分别建模。拒绝理由：需要分钟级或逐笔数据；代价 = 超出 A 批。

### 5.5 D5 数据顺序与 `stk_limit`（采纳条件性覆盖）

- 做法：`TradabilitySpec.stk_limit_path` 可选；有表则逐格覆盖，缺格回退自算；无表则自算。顺序固定为「停牌 → `adj` 回退 → ST/退市 → 上市日」，`stk_limit` 为前置可选层。
- **边界**：A 批 `stk_limit` 是**覆盖层**，不替代 `adj/ref` 基准；完全无 `adj` 时 loader 用 `ref=prev` 降级（D6），完全无 `ref` 且无 `adj` → `off`（D5 的「一次覆盖」指限价语义，不改变 inputs 构造契约）。
- 被拒 A：等 token 到位再启用。拒绝理由：U-2 已验证不可得，生产将无限期阻塞；代价 = 证据层无法交付。
- 被拒 B：按缺口大小排序（先 ST 后退市）。拒绝理由：未按「风险降低/成本」排序；`stk_limit` 一次覆盖多类缺口；代价 = 多轮返工。
- 被拒 C：在线拉取 `stk_limit`。拒绝理由：运行时引入 token/网络依赖；代价 = 生产稳定性与合规风险。

### 5.6 报告块（采纳 `diagnostics` 第三子块）

- 做法：`report`/`meta` 键集合冻结；新增 `diagnostics` 子块 + `schema_version=2`。
- 被拒 A：把新字段并入 `meta`（13→30 键）。拒绝理由：破坏既有 meta 契约与测试；代价 = 下游消费方需同步改。
- 被拒 B：把新字段并入 `report`（9→20 键）。拒绝理由：report 恒 int 的契约与 `summary`/持久化假设被打破；代价 = 序列化/兼容风险。
- 被拒 C：不披露，仅日志。拒绝理由：报告不可复核，V-13 无证据出口；代价 = 审计不可通过。

### 5.7 停牌语义（采纳 `'S'` only）

- 做法：构建器 `suspend == "S"`；`'R'`/缺失 False + 计数。
- 被拒 A：沿用 `astype(bool)`。拒绝理由：`'R'` 2,625 格被误封锁；代价 = 高估不可交易。
- 被拒 B：`'S'` 与 `'R'` 都视为停牌。拒绝理由：复牌日应可交易；代价 = 系统性漏成交。

### 5.8 并行接线（采纳 `TradabilitySpec` 懒加载）

- 做法：spec 只含路径/策略（小对象，可 pickle）；worker 内按因子切片 build，进程内缓存面板。
- 被拒 A：父进程构建全局 `TradabilityInputs` 后 pickle 给 worker。拒绝理由：约 0.67 GB/份 × workers，Windows spawn 复制昂贵；代价 = 内存/启动时间。
- 被拒 B：并行路径不接线。拒绝理由：批量生产仍无 tradability；代价 = 生产启用不完整。
- 风险：每 worker 缓存全量面板（约 0.67 GB），V-7 预算 ≤1 GB/worker；超限则登记 U-4。

### 5.9 版本与交付

- 包版本 **3.10.0**（minor：启用态新增能力；默认路径不变）；CHANGELOG 明示「启用态 `turnover`/报告块变化，IC/收益不变」。
- C 批先行的验证脚本与单测；A 批实现后跑 V-1~V-15。

### 5.10 D6 数据不足降级（采纳 `execution_only_open`）

- 做法：`TradabilitySpec.mode ∈ {auto, full, execution_only_open, off}` + `auto_degrade` + `min_coverage`；解析表见 §4.5。
- `execution_only_open`：T+1 开盘成交；限价可算则算（`ref=prev` 回退）；`high/low` 缺失 → 一字诊断关闭；`open/prev` 面板不足 → `off`；单格 `open` 缺失 → 阻塞 + 计数。
- 披露：`mode/mode_requested/degrade_reason/one_word_disabled/*_coverage`；**不静默**。
- 被拒 A：纯 T+1 开盘、完全不做限价检查。拒绝理由：变成乐观口径，无法区分「开盘可成交」与「开盘涨停」；代价 = 高估可交易。
- 被拒 B：维持 D5「数据不足即关闭」。拒绝理由：拿不到 T+1 开盘的执行证据，且 `high/low` 缺失时当前会静默放行；代价 = 证据层不完整。
- 被拒 C：`full` 不足直接 `ValueError`。拒绝理由：生产批次因个别面板缺失整体失败；代价 = 可用性差。
- 被拒 D：自动降级不披露。拒绝理由：`turnover` 口径变化不可复核；代价 = 审计不可通过。

## 6. 数据结构

### 6.1 `diagnostics`（P-021 v2）

| 键 | 类型 | 来源 | 说明 |
|---|---|---|---|
| `schema_version` | int | 引擎 | 固定 2 |
| `mode` | str | 解析器 | `full/execution_only_open/off` |
| `mode_requested` | str | 解析器 | `auto/full/execution_only_open/off` |
| `degrade_reason` | str/null | 解析器 | `high_low_or_adj_insufficient/open_or_prev_unavailable` |
| `one_word_disabled` | bool | 构建器 | `execution_only_open` 下为 True |
| `high_low_coverage` | float | 构建器 | eligible 格中 `high & low` 有效率 |
| `open_coverage` | float | 构建器 | eligible 格中 `open` 有效率 |
| `prev_close_coverage` | float | 构建器 | eligible 格中 `prev` 有效率（分母排除 t=0 结构性 NaN） |
| `adj_source` | str | 构建器 | `adj/ref_fallback/none` |
| `data_tier` | str | 构建器 | D0/D1/D2/D3/D4/D5，组合取最差 |
| `missing_fields` | list[str] | 构建器 | `adj/name/suspend/list_date/ohlc` |
| `bias_direction` | str | 构建器 | `none/optimistic/conservative/unavailable` |
| `price_basis_detail` | str | 构建器 | `raw_adj_ref_full/raw_adj_ref_with_fallback/raw_close` |
| `unknown_policy` | str | 构建器 | `pass/fallback_raw/block` |
| `ref_fallback_cells/days` | int | 构建器 | D2 回退规模 |
| `name_missing_cells/days` | int | 构建器 | D2 名称缺口 |
| `suspend_missing_cells/days` | int | 构建器 | D3 停牌缺口 |
| `rule_gap_cells/days` | int | 构建器 | D3 规则空档（BSE 早期） |
| `rule_gap_reason` | str/null | 构建器 | `neeq_pre_select` / `unknown_board` |
| `limit_table_source` | str | 构建器/引擎 | `self_computed/stk_limit/stk_limit_partial`；引擎合并时 `missing_cells>0` 强制恢复 `stk_limit_partial`（Step 10 审计 P1-①） |
| `limit_table_missing_cells` | int | 构建器 | 限价表缺格回退数 |
| `limit_table_duplicate_rows` | int | loader | 限价表重复键去重行数（Step 8 P1-② 回写；Step 10 审计 #6 勘正来源：构建器只见对齐后数组，仅 loader 写入） |
| `execution_timing` | str | 推进期 | `same_close/t_plus_1_open` |
| `exec_up_touch_cells/exec_down_touch_cells` | int | 推进期 | 执行价触板格（`next_open` 用 `open`；`same_close` 用 `high/low`） |
| `high_up_touch_cells/low_down_touch_cells` | int | 推进期 | 盘中触板格（`high/low`，与 RESEARCH 127,937/43,613 同口径） |
| `exec_price_missing_cells` | int | 推进期 | 执行价缺失导致的阻塞格 |
| `codes_not_found` | list[str] | loader | 请求但不在 close 面板的代码（前 20 个） |
| `coverage` | dict | loader | `{"high_low","open","prev": float, "eligible_cells": int}`；模式解析的输入快照（Step 10 审计 #4 补登记；引擎块经合并透出） |
| `close_mismatch_cells` | int | 引擎 | `inputs.close` 与引擎 `dl.close` 不一致的格数（0 为理想；不阻断） |

### 6.2 数据分级判定

| 级别 | 触发 | `bias_direction` |
|---|---|---|
| D0 | 无以下缺口 | `none` |
| D1 | `ref_fallback_cells>0` 或 `adj_source=="ref_fallback/none"` | `optimistic` |
| D2 | `name_missing_cells>0` | `optimistic` |
| D3 | `suspend_missing_cells>0` | `optimistic` |
| D4 | `list_date` 缺失/无命中 | `conservative` |
| D5 | `open/prev` 不可用（`mode=off`） | `unavailable` |

组合取最差（D1>D2>D3>D4）；`bias_direction` 取主导方向（D1-D3 乐观，D4-only 保守）。**完全缺 `adj`** 时 loader 传 `ref=prev` → D1 + `price_basis="raw_close"`；只有 `adj/ref` 都不可得且 `open/prev` 面板不足才 `off`。
> **D5 收窄（D6）**：`high/low` 缺失不再等同 D5——可降级 `execution_only_open`，以 `one_word_disabled=True` 单独披露；D5 仅当执行价/昨收不可用、无法运行时触发。

## 7. 错误处理

| 场景 | 处理 | 可见信息 |
|---|---|---|
| 数据根/必需面板缺失 | `ValueError`（fail-closed） | `TradabilitySpec: 缺少面板 <name>` |
| `adj` 与 `ref` 均未提供（直接调构建器） | `ValueError` | 既有「需要 adj」消息扩展为「需要 adj 或 ref」 |
| 完全缺 `adj`（loader） | `ref=prev` + D1 披露；`mode="full"` 且 `auto_degrade=False` → `ValueError` | `price_basis="raw_close"`、`adj_source="none"` |
| `open/prev` 面板覆盖 < `min_coverage` | 解析为 `off`，旧路径（不挂块） | **loader `logger.warning`**：`mode_requested/degrade_reason/coverage`（off 无 diagnostics 载体，INV-15 豁免） |
| `full` 条件不足且 `auto_degrade=True` | 降级 `execution_only_open` | `mode/mode_requested/degrade_reason` |
| `execution_only_open` 下 `high/low` 缺失 | 一字诊断关闭，成交仍按 `open` | `one_word_disabled=True` |
| `limit_up` 与 `limit_down` 不成对 | `ValueError` | 明确成对要求 |
| 未知板块 | 不抛错；`limit_unknown` + `unknown_codes` | 沿用 v3.9.10 |
| BSE 2020-07-27 前 | 不抛错；gap + `limit_unknown` | `rule_gap_reason="neeq_pre_select"` |
| 执行价 `open` 非有限 | 该格不可买/卖；计 `exec_price_missing_cells` | diagnostics |
| 停牌面板缺列 | 视为非停牌 + D3 披露 | `suspend_missing_cells` |
| 限价表缺格 | 回退自算 + `limit_table_missing_cells` | diagnostics |
| 并行 worker 构建失败 | 异常向上抛，不静默降级 | 批次失败 |

## 8. 不变式（Invariants）

1. **INV-1**：`tradability_inputs=None` 时引擎输出逐位不变（TP6-11 六项基线 + turnover）。
2. **INV-2**：启用后 `rank_icir/pearson_icir/hit_rate/spread/long_short_returns` 逐位不变（V-1）。
3. **INV-3**：`report` 9 键集合与 int 类型不变。
4. **INV-4**：`meta` 13 键集合不变；新披露只进 `diagnostics`。
5. **INV-5**：`same_close` 路径与 v3.9.10 逐位一致（既有 19 处调用零改值）。
6. **INV-6**：`next_open` 的目标后移 1 日、首日 0、末信号丢弃、执行价取 `open`；`carried` 对后移目标。
7. **INV-7**：`fallback_raw` 下 `prev` 有限则 `ref` 有限；`limit_unknown` 只统计真正不可判定格。
8. **INV-8**：BSE 2020-07-27 前不抛错；gap 计数 ≥ 对应 `limit_unknown` 的必要条件可核。
9. **INV-9**：`'S'` 才停牌；`'R'`/缺失可交易并计 D3。
10. **INV-10**：提供 `stk_limit` 表时逐格优先；`limit_table_source` 与实际来源一致。
11. **INV-11**：整个 `tradability` 块（`report/meta/diagnostics/口径键`）可 `json.dumps`；计数一律 `int(...)`，不得残留 numpy 标量。
12. **INV-12**：并行切片 build 与全量 build 在同一 `(dates, codes)` 上数组与 `report` 逐位一致；`meta/diagnostics` 按切片范围重算。
13. **INV-13**：`mode="off"`（含 `open/prev` 覆盖不足）时不挂 `tradability` 块，`turnover` 与旧路径逐位一致。
14. **INV-14**：`execution_only_open` 的目标后移/`open` 判定与 `next_open` 同构；`one_word_up/down` 恒 0 且 `one_word_disabled=True`；逐格 `open` 缺失 → 阻塞 + 计数。
15. **INV-15**：降级到 `execution_only_open` 必须在 `diagnostics` 同时出现 `mode/mode_requested/degrade_reason`；降级到 `off` 不挂块（INV-13），必须由 loader 以 `logger.warning` 记录 `mode_requested/degrade_reason/coverage`——两条路径都不得静默降级。

## 9. 幻觉抑制审查（Step 4 Review）

### 9.1 设计基于已验证的调研结论

- [x] 每条决策可追溯到 RESEARCH 的 R-/O-/D-/U- 编号；D6 为用户确认增补（§5.10），其数据条件来自 RESEARCH D0-D5
- [x] 无未经验证假设：D1 的 `next_open` 语义由 RESEARCH §4.4 锁定；D2 的 81 日缺口由 E1 锁定；D3 的 8,792 格由 E1 锁定
- [x] 无归因扭曲：本设计**不**声称提升收益/IC；只改 `turnover` 与披露
- [x] 未把「开源替代」写成已解决外部对拍：V-8 仍留 token
- [x] D6 `execution_only_open` 由用户确认；`off` 路径由 INV-13 锁定，降级披露由 INV-15 锁定

### 9.2 替代方案审查

- [x] 24 个被拒方案（§5.1-§5.8、§5.10 的 A/B/C/D），各带拒绝理由与代价
- [x] 每个关键决策都有「不做/晚做/换做法」的代价对照

### 9.3 职责边界审查

- [x] 明确 B 批收益层、空头腿、分钟级不在本设计
- [x] 明确能力边界：无 token 不承诺外部一致率
- [x] 未越界修改 `execution/`、`data_contract.py`、`summary()` 语义

### 9.4 Step 4 独立复审记录

> **RULE-4 声明**：本复核由撰写后的独立 pass 执行，但与撰写同属单会话——标注为**自查（单视角）**；建议 DESIGN 签字前由异构基座做第二会话复审（RULE-5，非阻断）。

- 复审方式：完稿后只读复读 RESEARCH §4-§6、当前 `tradability.py`/`tradability_inputs.py`/`engine.py`/`pipeline_integration.py`/`parallel_runner.py` 与既有 TP6 测试，逐条核对本设计的接口与不变式。
- 结论：**PASS（自查·单视角）**；0×P1 / 0×P2 / 4×P3（已在正文处置）：
  - P3-1：`execute_at` 默认值改为 `same_close` 属「死字段激活」而非行为变更——已在 §4.1/§5.1 写明。
  - P3-2：`price_basis` 仍写 `raw_adj_ref`、更细口径放 `diagnostics.price_basis_detail`——已在 §4.4/§6.1 写明，避免破坏既有 meta 测试。
  - P3-3：完全缺 `adj` 时 loader 用 `ref=prev` 降级为 D1；只有 `adj/ref` 都不可得且 `open/prev` 不足才 `off`——已在 §2.3/§4.5/§6.2/§7 写明。
  - P3-4：`execution_only_open` 的一字诊断关闭属有意降级，不用于三态结论——已在 §4.2/§5.4/§5.10 写明。
- 归因扭曲检查：本设计不引用学术结论支撑收益方向；学术分歧（磁吸/冷却）不影响 D1-D5（RESEARCH §5.5②）。
- 职责边界检查：B 批/空头腿/分钟级/`data_contract` 明确列为「职责外」。

### 9.5 独立只读复审记录（同基座，2026-11-23）

- 复审方式：独立只读子代理（Explore，未给编辑权限）读取 DESIGN/RESEARCH 与 6 个代码/测试文件，按 10 项检查逐条核对。
- 结论：**PASS（0×P1 / 0×P2）**。确认：D1-D5 可追溯、无自创数字；无 overclaim；报告/meta 契约与诊断块设计一致；边界声明完整。
- 复审列出的「接口字段尚不存在」「引擎尚未接线」等条目，均为本设计的**计划变更**（尚未实施的 delta），不是设计缺陷；实施阶段按 §10.4 顺序落地。
- 复审未覆盖：`close_mismatch_cells` 的运行时精度、并行内存实测、`stk_limit` 外部一致率——分别登记 U-2（内存）、U-1（外部一致率）、U-7（模式阈值）与 V-7/V-8。
- RULE-5 建议：同基座复审只消除记忆污染；DESIGN 签字前建议异构基座第二会话复审（非阻断）。

### 9.6 D6 增补复核（2026-11-23）

- 触发：用户确认新增 `execution_only_open` 降级模式（D6）。
- 复核：D6 只改变「数据不足时的执行/披露」，不改 D1-D5 的任何数值口径；`report/meta` 契约仍冻结；`off` 与旧路径逐位一致（INV-13）；`execution_only_open` 与 `next_open` 同构（INV-14）；降级必须披露（INV-15）。
- 结论：**PASS**；新增 1 个开放项 U-7（`min_coverage` 阈值标定），不阻断 DESIGN。
- **覆盖声明**：D6 为增补，§9.5 的独立只读复审未覆盖 D6；建议异构复审时一并覆盖 §5.10/§4.5。

### 9.7 异构复审记录（RULE-5，2026-11-23）

- **异构性声明**：DESIGN 撰写于前序会话（DeepSeek 基座）；本复审由当前会话的**独立只读子代理**执行（GLM 基座）——满足 RULE-5「reviewer 与 implementer 异构基座」。前两轮 Explore 型子代理仅返回片段未出结论（如实登记，不计入复审）。
- **复审范围**：10 项检查 = D1-D5 全量 + D6（§4.5/§5.10，§9.5 未覆盖的 delta）+ 接线参数序、测试影响、IO 依赖杂项。
- **结论**：**PASS_WITH_FIXES（1×P1 / 2×P2 / 4×P3）**，7 项全部处置：
  - **P1**（INV-15 × off 自相矛盾：off 不挂块则 diagnostics 无载体）→ **已修**：INV-15 拆为两条披露通道——`execution_only_open` 进 diagnostics；`off` 由 loader `logger.warning` 记录（§7/§8）。
  - **P2-1**（D3 gap 化使既有 bse 2020-01-06 `ValueError` 断言必挂，设计未登记改测）→ **已修**：§10.2/§10.3 登记断言改写为「不抛错 + `limit_unknown>0`」，属 O-9 解阻断的有意行为变更。
  - **P2-2**（`prev` 的 t=0 结构性 NaN 计入覆盖率 → T<100 并行切片必然误降级）→ **已修**：`prev_close_coverage` 分母排除 t=0（§4.5/§6.1）。
  - **P3-1**（policy.mode 默认 full 与 spec.mode 默认 auto 同名歧义）→ §10.1 明示「请求 vs 解析」归属。
  - **P3-2**（off no-op 返回形状未锁定 9 键 int）→ §4.2 锁定三元组 `(target, 9 键全 0 int, {"mode","schema_version"})`。
  - **P3-3**（`stk_limit_path` 支持 Parquet 与「零新增运行时依赖」冲突）→ §4.5 A 批承诺 CSV；Parquet 走 `has_pyarrow` 探测、缺失 `ValueError`。
  - **P3-4**（§6.2 收窄 D5 未回写真相源 RESEARCH §4.2）→ RESEARCH §4.2 已增补 D6 收窄注记。
- **复审确认 PASS 项**：D1 死字段激活中性（`execute_at` 无测试断言）；D2 直接调用仍 fail-closed（既有 adj-None 用例不破）；D6(b) 时点约束 fail-closed 合理（spec 默认工厂提供唯一合法组合）；D6(f) meta 值变化不破坏 13 键冻结契约（既有断言仅在 adj 在场时触发）；接线参数序正确（`price_data.columns`=dates / `index`=stocks；worker `cd/cs` 同构）；`TradabilitySpec` frozen dataclass 可 pickle。
- **复审后版本**：v1.1 → **v1.2**（上述 7 处修订；D1-D6 决策与 INV-1~14 语义不变）。

### 9.8 Step 8 三对文档一致性复审记录（2026-11-23）

- 方式：独立只读子代理（general-purpose，未给编辑权限）按六项检查（RESEARCH↔DESIGN / DESIGN↔IMPL / IMPL↔CHECKLIST / 术语 / 版本 / CHECKLIST 自身质量）逐条核对；主会话先行机械校验（版本锚点 grep、术语计数、INV/用例组 grep、链接可达）。
- 结论：**PASS_WITH_FIXES（2×P1 / 2×P2 / 6×P3）**，全部处置：
  - **P1-①**（C 批验收项整体缺失：DESIGN §10.3 的 `test_p021_consistency_*` 规则边界与 `test_p021_mock_stk_limit_*` 扰动、IMPL §8.4 `test_p021_mock_stk_limit_perturb`、§3.6 脚本在 CHECKLIST 零对应）→ CHECKLIST §2 增 F-19/F-20/F-21（脚本 JSON 产出 / 规则边界 4 项 / mock 扰动 4 类 + 重复键），§10.1 同步 78→81。
  - **P1-②**（IMPL §3.3(5) 新增 `limit_table_duplicate_rows` 未回写 DESIGN）→ §4.6 合并清单与 §6.1 键表各补一行（本版唯一契约变更）。
  - **P2-①**（RESEARCH L439 写「DESIGN v1.1 verified」过期）→ RESEARCH 就地勘误为 v1.3（不改 RESEARCH 版本，仅前向引用指针）。
  - **P2-②**（IMPL §3.6/§8.1 未逐项列 C 批规则边界、缺 `tests/test_tradability_consistency.py` 文件行）→ IMPL §3.6 补 gem 2020-08-24 / ST 2026-07-06 / 低价 0.01 元 / half-up 四项；§8.1 补文件行。
  - P3-①（§2.1 D6 行自引用）→ 引用列改「RESEARCH §4.2 D5 收窄注记 + D6 用户确认」。P3-②（DESIGN §7「execution_only_open 下 high/low 缺失」IMPL §6 无行）→ IMPL §6 补行。P3-③（`self_computed` 无赋值点）→ IMPL §3.2.6 补默认赋值 + CHECKLIST F-12/N-10 补场景。P3-④（CHECKLIST C-4 词表缺 `same_close`）→ 补齐七词。P3-⑤（4 个测试名 IMPL 未登记）→ IMPL §8.1 补名。P3-⑥（IMPL「写入 §6.1」歧义）→ 改「写入 DESIGN §6.1」。
- 复核确认 PASS：D1-D6 可追溯（十条逐行有编号）；INV-1~15 双向齐备；术语七词语义一致；版本 3.10.0/3.9.10 无第三种混入；CHECKLIST §10.1 形态与算术合规。
- **复审后版本**：v1.2 → **v1.3**（本节处置；D1-D6 决策与 INV-1~15 语义不变）。

### 9.9 Step 10 独立只读 ADD 审计记录（2026-11-23）

- 方式：独立只读子代理（异构基座，只读探针 = 3 组定向 pytest 重放 57 例全绿 + 2 次 python -c 只读验证 + 静态读码；审计不写代码，D-002）。
- 裁决：**PASS_WITH_FIXES**，ADD 质量门 **4.3/5 档位 A**；计数 **1×P1 / 2×P2 / 5×P3**（另 1 条未核实观察项）。
- 主会话处置（详见 CHECKLIST §12.2）：P1-①（引擎合并覆盖 `stk_limit_partial` → INV-10 块级失真）已修复 + 块级测试 `test_p021_partial_limit_source_block` 红→绿；P2-①（off no-op diagnostics 10 键偏离 §4.2 的 2 键锁定）→ **实现收窄**为 2 键并补强 `test_p021_mode_off_noop` 键集合断言；P2-②（Step 9 后修复未登记）→ IMPL §8.1/§9.8/§11.1 同步；P3 五项 + 观察项逐条处置（§6.1 键表补 `coverage`、来源列勘正；INV-12 测试加强为直接对比；docstring 6 元组；list_date fixture `test_p021_loader_list_date_panel`）。
- 审计期间主会话先行发现并修复（与审计 P2-② 互证）：**真实数据根全部面板 index 为字符串日期** → loader reindex 全 miss → `eligible_cells=0` → 默认 spec 恒 `off`；`_read_panel` 归一化 `pd.to_datetime`（非日期索引面板容错跳过），修复后真实数据根 `mode=full`、eligible 7,203,655 格、tier=D1（缺 name/suspend/list_date，符合 §6.2 组合取最差）。
- 性能补证：P-1 全样本完整构建 **15.90 s ≤ 30 s** ✅；K-5 默认工件重跑 SHA `82728CE1…` 逐位一致 ✅；P-2 实测 worker RSS **3348 MB > 1 GB 预算** → 登记待办（CHECKLIST §6）。
- **审计后版本**：v1.3 → **v1.4**（§6.1 键表 3 处勘正/补登记；契约语义不变——`coverage` 为补登记既有行为，`limit_table_source` 恢复规则为 INV-10 原义澄清）。

## 10. 对实施的输入

### 10.1 关键工程约束

- 只改 `backtest/tradability.py`、`backtest/tradability_inputs.py`、`backtest/tradability_loader.py`（新）、`backtest/engine.py`、`backtest/pipeline_integration.py`、`backtest/parallel_runner.py`、`tests/`、`scripts/`、台账/版本文件。
- Python 3.9；零新增运行时依赖；loader 的 IO 与纯构建器分离。
- `report`/`meta` 键集合冻结；`diagnostics` 为唯一新增块。
- 生产 loader 默认 `execute_at="next_open", unknown_policy="fallback_raw"`，`TradabilitySpec.mode="auto"`（**请求**默认；解析结果写入 `policy.mode`，policy 侧解析默认 `full`）；库默认 `same_close/pass/full`。
- `execution_only_open` 必须显式披露 `one_word_disabled=True`；不得把一字计数当 0 参与三态结论。
- 所有 diagnostics 计数用 `int(...)`；不得输出 numpy 标量。
- 包版本 **3.10.0**；默认路径工件 SHA 逐位不变。

### 10.2 风险与缓解

| 风险 | 缓解 |
|---|---|
| `next_open` 改变启用态读数，误判为回归 | INV-2 锁 IC/收益；V-2 只对比 `turnover` 分布；文档明示 |
| `fallback_raw` 掩盖真实缺口 | D1 披露 + `ref_fallback_cells`；V-11 三策略对照 |
| BSE 规则前移引入 2020-07-27~2021-11-15 近似 | `rule_gap_reason` + 文档披露；B 批敏感性 |
| `'R'` 语义修改影响旧读数 | 单测 + V-12；仅启用态变化 |
| 并行 worker 内存超预算 | V-7 ≤1 GB/worker；超限登记 U-2 |
| `stk_limit` 表部分覆盖 | `limit_table_missing_cells` + 回退自算；V-8 待 token |
| 现有测试因默认值变更失败 | 默认 `same_close/pass`，既有测试零改值；新增生产 loader 用例 |
| 空头腿未后移导致 `turnover` 混合口径被误读 | `leg_scope/turnover_basis` 保持披露；B 批再统一 |
| 完全缺 `adj` 被误当 D1 | loader 用 `ref=prev` + D1 披露；`full` 且 `auto_degrade=False` → `ValueError`；不得无披露 |
| D3 gap 化使既有 bse 2020-01-06 `ValueError` 断言必挂（test_tradability.py 错误表用例） | **有意行为变更**（O-9 解阻断）；§10.3 登记断言改写为「不抛错 + `limit_unknown>0`」 |
| loader 的 `stock_close` 与引擎 `price_data` 不一致 → 限价基准错 | `close_mismatch_cells` 披露（不阻断，保留 TP6-9b 语义）；生产要求同一数据根 |
| 自动降级掩盖数据质量 | `mode_requested/degrade_reason/*_coverage` 全披露；V-15 降级链用例 |
| `execution_only_open` 被误读为完整限价证据 | `one_word_disabled=True`；报告 `leg_scope/turnover_basis` 保持；文档标注「仅执行证据」 |

### 10.3 测试矩阵（C → A）

| 批次 | 用例组 | 覆盖 |
|---|---|---|
| C | `test_p021_consistency_*` | `ref_ret` vs `ref_adj` 公式、规则边界（BSE 2020-07-27 / gem 2020-08-24 / ST 2026-07-06 / 0.01 元 / half-up） |
| C | `test_p021_mock_stk_limit_*` | 18 行 mock 格式、缺列/重复/非正/`up<down`、错价/缺行/多代码检出 |
| A | `test_p021_d1_*` | 目标后移、open 谓词、首日 0、末信号丢弃、`turnover` 后移、open NaN 阻塞、same_close 旧行为 |
| A | `test_p021_d2_*` | adj 缺口回退、计数、D1 分级、`pass` legacy |
| A | `test_p021_d3_*` | BSE 前移、pre-select gap 不抛错、计数；**改写**既有 bse 2020-01-06 断言（`ValueError` → 不抛错 + `limit_unknown>0`） |
| A | `test_p021_d4_*` | 一字计数、`exec_*/high_*` 触板计数、诊断键 |
| A | `test_p021_d5_*` | `'S'` only、D0-D5 判定、限价表覆盖/缺格 |
| A | `test_p021_loader_*` | 对齐、切片一致、CSV 适配、fail-closed |
| A | `test_p021_engine_*` | 块 v2、IC 零变化、管道/并行透传、默认路径不变 |
| A | `test_p021_mode_*` | `auto→full`、`full→execution_only_open` 降级、`open/prev` 不足→`off`、`one_word_disabled`、`degrade_reason`、`off` 逐位旧路径 |

### 10.4 实施顺序

1. **C**：一致性脚本 + 规则边界/mock 限价表单测（先红后绿）。
2. **A1**：BSE 规则前移 + `_pct_matrix` gap + 停牌 `'S'` 映射（解阻断/语义）。
3. **A2**：`next_open` + `apply_tradability_with_diagnostics` + 引擎块 v2。
4. **A3**：`ref` fallback + data tier + diagnostics + D6 模式解析。
5. **A4**：`TradabilitySpec` loader + 管道/并行接线。
6. **A5**：全量回归 + V-1~V-15 + 台账/版本。

## 11. 未决项登记（四元块）与决策矩阵

**11.1 未决项登记**：

- **U-1 `stk_limit` 外部一致率（V-8）**
  - **判据**：token 到位后 2020-01-02~2026-01-30 逐格对拍 ≥99.9%
  - **触发条件**：用户提供 token 或离线快照
  - **当前倾向**：不阻塞 A 批；C 批用内部一致性替代
  - **证据等级**：E0（待 token）

- **U-2 并行面板内存**
  - **判据**：`n_workers=4` 时每 worker 峰值 ≤1 GB
  - **触发条件**：V-7 实测超预算
  - **当前倾向**：进程内缓存 + 按因子切片；超限则降 `n_workers` 或登记优化
  - **证据等级**：E0

- **U-3 分级阈值 99%**
  - **判据**：`adj/name/suspend` 覆盖率实测与 D0 稳定性
  - **触发条件**：首个生产批次完成后
  - **当前倾向**：沿用 99%；按覆盖率分层披露
  - **证据等级**：E0

- **U-4 ST 名称推断外部交叉验证**
  - **判据**：`namechange` 与名称推断差异清单
  - **触发条件**：拿到 `namechange` 快照
  - **当前倾向**：A 批保持名称推断 + D2 披露
  - **证据等级**：E0

- **U-5 退市整理期公告表**
  - **判据**：退市整理首日无涨跌幅与名称识别差异
  - **触发条件**：拿到交易所公告表
  - **当前倾向**：名称含「退」+ 首日 `no_limit`；D4/名称缺口披露
  - **证据等级**：E2/E0

- **U-6 三态敏感性（B 批）**
  - **判据**：`limit_mode=one_word` 与默认口径的 `turnover` 差异
  - **触发条件**：B 批立项
  - **当前倾向**：A 批只披露，不做一字-only
  - **证据等级**：E0

- **U-7 模式阈值 `min_coverage`**
  - **判据**：`full → execution_only_open` 的切换阈值在真实数据上不误降级/误升级
  - **触发条件**：首个生产批次完成后
  - **当前倾向**：`min_coverage=0.99`；先按 99% 跑，读数偏差 >1% 再标定
  - **证据等级**：E0

**11.2 决策矩阵**：不启用。D1-D6 已由用户裁决；本设计剩余项为可逆的工程实现选择（Type-2），先做再改。

---

**Review 签字**: Step 4 自查 PASS（4×P3 处置）+ 同基座只读复审 PASS（0×P1/0×P2）+ **异构复审 PASS_WITH_FIXES（1×P1/2×P2/4×P3 全部处置，§9.7）** 日期: 2026-11-23
