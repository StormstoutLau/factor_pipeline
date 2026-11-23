# 实施文档：P-021 tradability 生产启用

---
id: p021-tradability-production-enablement-IMPLEMENTATION
type: design
version: 1.5
status: verified
date: 2026-11-23
depends: [p021-tradability-production-enablement-DESIGN, p021-tradability-production-enablement-RESEARCH]
upstream: null
---

> **Feature**: P-021 tradability 生产启用（C 内部对拍 + A 证据层）
> **创建日期**: 2026-11-23
> **状态**: verified（Step 5 完稿；Step 6 独立复审已处置（§9.5）；异构复审双视角已处置（§9.6）；Step 8 一致性复审 PASS_WITH_FIXES 已处置（§9.7）；Step 9 实测同步（§9.8）；**Step 10 独立 ADD 审计 PASS_WITH_FIXES 已处置（§9.9：1×P1/2×P2/5×P3）**）
> **Spec 步骤**: Step 5-6（+§9.7 Step 8；§9.8 Step 9；§9.9 Step 10）
> **基于设计**: [DESIGN.md](./DESIGN.md)（v1.4 verified）
> **基于调研**: [RESEARCH.md](./RESEARCH.md)（v1.1 verified）
> **档位**: **T1** ｜ **包版本**: 3.9.10 → **3.10.0** ｜ **新依赖**: **无**（Parquet 仅走既有可选 pyarrow）

---

## 1. 实施概述

按 DESIGN v1.2 的 D1-D6，把 tradability 从「引擎可选能力」接成「生产可开关的证据层」。实施分 **C 批（验证前置）→ A 批（生产接线）**：

- **C 批**：内部一致性脚本（`ref_ret` vs `ref_adj`）+ 规则边界单测 + Tushare 格式 mock 限价表扰动测试；不依赖 token。
- **A 批**：`tradability.py`（BSE 规则前移、`next_open`、`execution_only_open`、外部限价覆盖、诊断）→ `tradability_inputs.py`（停牌 `'S'`、名称 ffill、`ref` 回退、data tier）→ 新增 `tradability_loader.py`（`TradabilitySpec` + 模式解析 + 面板缓存）→ `engine.py`（块 v2 + `close_mismatch_cells`）→ `pipeline_integration.py` / `parallel_runner.py`（可选 `tradability_spec`）。

**硬边界**：`tradability_inputs=None` / `tradability_spec=None` 时旧路径逐位不变；`report` 9 键与 `meta` 13 键冻结；IC/spread/`long_short_returns` 不变；B 批收益层、空头腿、分钟级不纳入。

## 2. 工程细节

### 2.1 技术栈

| 组件 | 技术 | 版本/约束 | 验证状态 |
|---|---|---|---|
| 语言 | Python | `>=3.9`（`pyproject.toml:10`） | ✅ 仓内约束 |
| 数值 | numpy | `>=1.22.0`（`pyproject.toml:27`）；本机 2.1.3 | ✅ E1 本机 |
| 面板 | pandas | `>=2.0.0`（`pyproject.toml:28`）；本机 2.2.3 | ✅ E1 本机 |
| Parquet（可选） | pyarrow | 既有 `calib` extra（`pyproject.toml:51`）；本机已装 | ✅ 可选，非新增 |
| 测试 | pytest | 既有 `dev` extra（`pyproject.toml:53-56`） | ✅ 不新增 |
| 版本字段 | `pyproject.toml` | 3.10.0（本批写入） | ⏳ 实施时写 |

### 2.2 依赖版本验证（Step 6）

| 依赖 | 声明 | 核验方式 | 结论 |
|---|---|---|---|
| Python | `>=3.9` | `pyproject.toml:10` 直读 | ✅ 不使用 `X \| None` 运行时注解；用 `Optional[...]` |
| numpy | `>=1.22.0` | 本机 `numpy 2.1.3`；`ndarray.item` 文档 | ✅ 只用 `isfinite/count_nonzero/isclose/where` 等稳定 API |
| pandas | `>=2.0.0` | 本机 `pandas 2.2.3`；`reindex`/`ffill` 文档 | ✅ 只用 2.0 已存在的 `reindex/ffill/eq/pivot`；**不用** 2.2 新增的 `limit_area` |
| pyarrow | 既有 `calib` extra | `pyproject.toml:51`；本机已装 | ✅ 非新增；缺失时 `has_pyarrow()` 探测 + `ValueError` |
| pytest | 既有 `dev` extra | `pyproject.toml:53-56` | ✅ 非新增 |

**结论**：零新增依赖 → PyPI 新版本查询 **N/A（理由：无新增）**；Python 3.9 下限的库 API 已逐项核对（见 §2.3）。

### 2.3 外部证据锚点（源码级 / 文档级 / 摘要级）

> 读取日：2026-11-23。`T1` = 源码/官方文档/仓内原文；`T3` = 社区摘要。降级链按 SPEC_PROCESS F3 记录。**可复核性**（异构复审 P2-A）：X-1 精确行号与 X-2 外部数值属离线不可复核项，Step 9 实施时须留存页面快照或 URL hash 落盘 `spec/p021-*/anchors/`，使 T1 声明可复核。

| # | 源 | 层/版本 | 锚点 | 对本实施的约束 |
|---|---|---|---|---|
| X-1 | Qlib `exchange.py`（raw `main`） | T1 / main@2026-11-23 | `suspended = self.quote_df["$close"].isna()`（L246）；`limit_buy = self.quote_df["$change"].ge(limit_threshold) \| suspended`（L260-262）；`deal_price` 支持买/卖两价（L142-147） | Qlib 用**固定收益阈值** + `close` NaN 判停牌；本仓用**精确限价 + 显式停牌面板**，不照搬阈值（RESEARCH R-7：0.095 阈值误判 26,029 格） |
| X-2 | Tushare `stk_limit` 文档 | T1 / 文档页@2026-11-23 | 字段 `ts_code, trade_date, pre_close, up_limit, down_limit, asset_type, exchange`；2007-01-04 起；单次 5800 条；2000 积分 | 限价表 CSV 至少 `ts_code, trade_date, up_limit, down_limit`；在线分页/积分为 token 到达后事项，A 批只读离线快照 |
| X-3 | pandas `DataFrame.reindex` 文档 | T1 / v3.0.6 页（项目 >=2.0） | 新索引缺值填 NaN；`method="ffill"` 仅适用于单调索引，且**不会填原 DataFrame 已有的 NaN**；要填已有 NaN 用 `fillna()` | 名称面板用 `reindex(...).ffill()`，**不用** `reindex(method="ffill")` |
| X-4 | pandas `DataFrame.ffill` 文档 | T1 / v3.0.6 页（项目 >=2.0） | 沿轴传播最后有效值；`limit_area` 为 **2.2.0 新增** | 不用 `limit_area`（pandas 2.0/2.1 无此参数）；只传 `axis` |
| X-5 | Python `multiprocessing` 文档 | T1 / 3.x | Windows 默认 `spawn`（L53）；`set_start_method` 放在 `if __name__ == '__main__'`（L66-73）；子进程重新导入模块 | `TradabilitySpec` 必须模块级、可导入、无闭包/lambda；并行入口保持 `if __name__` 保护 |
| X-6 | numpy `ndarray.item` 文档 | T1 / stable | `.item()` 返回标准 Python 标量；object dtype 原样返回 | 诊断计数用 `int(...)` 或 `.item()`；禁止 `np.int64` 直入 JSON |
| X-7 | 仓内 `pyproject.toml` | T1 / 3.9.10 | Python `>=3.9`（L10）；numpy `>=1.22`（L27）；pandas `>=2.0`（L28）；pyarrow 仅 `calib`（L51；另 `all` extra L58 亦含，同属既有可选，非新增——异构复审 P3-A1） | 3.9 语法；Parquet 可选；零新增依赖 |
| X-8 | RQAlpha / JoinQuant（RESEARCH A-20/A-21） | T3 / 摘要级 | bar 含 `limit_up/limit_down`；涨停/跌停买单/卖单不成交 | 执行日限价判定；仅作旁证，不承载关键结论（RESEARCH 层列对 A-20/A-21 标 T1 系全文抓取状态口径，本表从严按摘要级 T3——异构复审 P3-A3） |
| X-9 | 交易所规则（RESEARCH A-1~A-13） | T1/T2（关键规则由 A-1/A-4~A-7 条款级承载；A-2/A-3/A-8~A-13 为摘要级——异构复审 P3-A2） | 除权参考价、half-up 到分、板块/ST/北交所档位、T+1 | `limit_price` 整数分 half-up；`next_open` 执行时点 |
| X-10 | 本仓 E1 读数（RESEARCH §4.5/§5.6/§5.7） | E1 | 触板 127,937/86,039/17,373；缺口 81 日；BSE 8,792 格；`'R'` 2,625 格；一字 5.46% | 测试期望值与诊断阈值 |

**降级链（F3）**：WebSearch 检索 RQAlpha/JoinQuant 源码两次返回 0 结果 → 降级为 RESEARCH A-20/A-21 摘要级（T3），并在 X-8 标注；未把摘要写成源码级证据。

### 2.4 文件结构（改动面）

```
backtest/tradability.py              # 改：规则/策略/inputs/apply
backtest/tradability_inputs.py       # 改：停牌/名称/ref/gap/meta/diagnostics
backtest/tradability_loader.py       # 新：TradabilitySpec + 面板缓存 + 模式解析 + 限价表
backtest/engine.py                   # 改：校验 + 块 v2 + close_mismatch
backtest/pipeline_integration.py     # 改：可选 tradability_spec
backtest/parallel_runner.py          # 改：可选 tradability_spec
scripts/verify_tradability_consistency.py  # 新：C 批内部对拍
tests/test_tradability.py            # 改：bse 断言 + 新用例
tests/test_tradability_inputs.py     # 改：meta/ref/suspend 用例
tests/test_backtest/test_engine.py   # 改：块 v2/默认路径用例
tests/test_tradability_*.py          # 新：next_open/fallback/bse/mode/loader/pipeline
pyproject.toml / __init__.py / config_v2.py / reporting.py / CHANGELOG.md  # 版本 3.10.0
docs/PROGRESS.md / docs/PROJECT_STATUS.md  # 台账
```

## 3. 模块实施

### 3.1 `backtest/tradability.py`

#### 3.1.1 规则表（D3）

```python
# L31-40 现有；仅改 bse 两行
LimitRule("bse", False, 0.30, "2020-07-27"),
LimitRule("bse", True, 0.30, "2020-07-27"),
```

- `rule_pct` 保持「无命中 → ValueError」，不改变直接调用方契约（RX-1）。
- 新增 `rule_pct_or_nan`：捕获 `ValueError` 返回 `np.nan`，仅供 `_pct_matrix` 使用。
- `_pct_matrix(board, is_st, is_delisting, dates, return_gaps=False)`：
  - `pct = np.full((T,N), np.nan)`；`gaps = np.zeros((T,N), bool)`。
  - 逐日、逐 unique state（≤8）：`code < 0` → `gaps` 标记 + 留 NaN；否则 `rule_pct_or_nan`，NaN → `gaps` 标记。
  - `return_gaps=True` 返回 `(pct, gaps)`；默认只返回 `pct`（保持既有调用方）。
- **行为变更**：`apply_tradability(board=["bse"], dates=2020-01-06/07)` 由 `ValueError` 改为「不抛错 + `pct=NaN` + gap」，既有测试 `tests/test_tradability.py:448-452` 必须改断言（见 §8.3）。

#### 3.1.2 `TradabilityPolicy`（D1/D6）

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

- 校验：`execute_at`、`unknown_policy`、`mode` 非法值 → `ValueError`；`mode=="execution_only_open"` 且 `execute_at!="next_open"` → `ValueError`。
- 库默认 `same_close/pass/full`（旧行为）；生产 `TradabilitySpec.policy` 显式 `next_open/fallback_raw/full`。

#### 3.1.3 `TradabilityInputs`（末尾追加）

```python
@dataclass(frozen=True, eq=False)
class TradabilityInputs(object):
    # ... 现有 14 字段不变 ...
    ref: np.ndarray = None          # (T,N) 含 fallback 的参考价
    limit_up: np.ndarray = None     # (T,N) 外部限价
    limit_down: np.ndarray = None
    codes: np.ndarray = None        # (N,) 代码
    diagnostics: dict = None        # 构建器诊断
```

#### 3.1.4 `apply_tradability_with_diagnostics`（D1/D4/D6）

```python
def apply_tradability_with_diagnostics(
    target_w, prev_close, high, low, close, open_, volume, suspended,
    board, is_st, dates, policy=None, adj=None, is_delisting=None,
    no_limit=None, ref=None, limit_up=None, limit_down=None,
):
    """返回 (effective_w, report, diagnostics)；report 九键恒 int。"""

def apply_tradability(target_w, prev_close, high, low, close, open_, volume,
                      suspended, board, is_st, dates, policy=None, adj=None,
                      is_delisting=None, no_limit=None, ref=None,
                      limit_up=None, limit_down=None):
    """兼容包装：返回 (effective_w, report)；policy 仍为第 12 位。"""
```

实施要点：

1. **校验与 no-op**：
   - 先校验 `target_w` 2D、各面板 `(T,N)`、`board (N,)`、`dates (T,)`（沿用现有 L319-344）。
   - `policy = policy or TradabilityPolicy()`；校验三个枚举。
   - `mode=="off"` → 返回 `(target_w.copy(), {9 键全 0 int}, {"mode":"off","schema_version":2})`；不做任何推进。
2. **目标后移/执行价**：
   - `next_open`：`target_all = np.zeros_like(target_w); target_all[1:] = target_w[:-1]`；`exec_buy = exec_sell = open_`。
   - `same_close`：`target_all = target_w`；`exec_buy = high`、`exec_sell = low`。
   - `exec_price_missing_raw = ~np.isfinite(exec_buy) | ~np.isfinite(exec_sell)`；**仅 `execute_at=="next_open"` 时生效**：`missing_exec_effective = exec_price_missing_raw`（next_open）或**全 False**（same_close）。异构复审 P1-B1：same_close 必须保持「无证据不阻塞」——现行为对 NaN high/low 放行（tradability.py:385-386），且 `tests/test_tradability.py:434-439` 断言 `blocked_buy==0`，无差别拦截会破坏逐位一致承诺。
3. **限价来源**：
   - 若 `limit_up/down` 同时给出：逐日 `up=limit_up[t]`、`down=limit_down[t]`、`unk=~isfinite(up)|~isfinite(down)`；跳过 `_pct_matrix`；`limit_table_source="stk_limit"`。
   - 否则 `pct_mat = _pct_matrix(...)`；`ref_mat = ref if ref is not None else _ref_from_adj(prev_close, adj)`（`adj/ref` 都 None → `ValueError`）；`up,down,unk = compute_limits(prev_close[t], pct_mat[t], ref=ref_mat[t])`；`unk |= ~isfinite(pct_mat[t])`。
4. **执行谓词（顺序修正，Step 6 P2-1）**：
   - `judge = ~unk & ~nolim[t]`；`susp = suspended[t]`。
   - `missing_exec = ~susp & judge & missing_exec_effective[t]`（**先于 pending 定义**；same_close 时该项恒 False → 不生效）。
   - `can_buy = ~susp & (~judge | ~(exec_buy[t] >= up - eps)) & ~missing_exec`；`can_sell = ~susp & (~judge | ~(exec_sell[t] <= down + eps)) & ~missing_exec`。
   - `unknown_policy=="block"` 时：`can_buy &= judge`、`can_sell &= judge`（未知 → 不成交）；`pass/fallback_raw` 保持「未知放行 + `limit_unknown`」。
   - `exec_price_missing_cells`：pending 阶段用 `pending != 0`，delta 阶段用 `busy & (pending == 0)`；各自 `& missing_exec` 后累加（同格最多计一次：阻塞格 pending 不清零 → 仅 pending 阶段计；成交格 pending 清零 → 仅 delta 阶段计。异构复审 P3-B5）。
5. **一字**：仅 `mode=="full"` 计算 `one_word_up/down`（现有 L391-397 逻辑）；否则保持 0，诊断 `one_word_disabled=True`。
6. **推进/报告**：pending、T+1、`blocked_*`、`deferred`、`limit_unknown`、`carried` 逻辑不变；`carried` 对 `target_all[-1]`。
7. **诊断计数**（全部 `int`）：
   - `exec_up_touch_cells` / `exec_down_touch_cells`：`judge & ~susp & (exec_buy >= up - eps)` / `(exec_sell <= down + eps)`。
   - `high_up_touch_cells` / `low_down_touch_cells`：`judge & ~susp & (high >= up - eps)` / `(low <= down + eps)`（与 RESEARCH 127,937/43,613 同口径）。
   - `execution_timing` = `t_plus_1_open` / `same_close`；`limit_table_source`；`schema_version=2`。
8. **性能**：逐日循环 T（现有），日内全向量化；无 T×N Python 循环新增。

### 3.2 `backtest/tradability_inputs.py`

#### 3.2.1 签名

```python
def build_tradability_inputs(close, high, low, open_, volume, suspend, name,
                             adj=None, list_date=None, policy=None,
                             st_overrides=None, limit_up=None, limit_down=None,
                             ref=None):
    """返回 (inputs, meta)；meta 13 键不变；diagnostics 挂 inputs.diagnostics。"""
```

- `adj/ref` 至少一个；都 None → `ValueError("需要 adj 或 ref")`（保留 `test_adj_required` 语义）。
- `policy = policy or TradabilityPolicy()`。

#### 3.2.2 停牌（O-7，Step 6 P2-2 双路径）

```python
def _suspend_mask(df, index, columns):
    """bool 面板：True=停牌（兼容既有调用）；object 面板：仅 'S'=停牌。"""
    if df is None:
        return (np.zeros((len(index), len(columns)), bool),
                np.ones((len(index), len(columns)), bool))
    raw = df.reindex(index=index, columns=columns)
    missing = raw.isna().to_numpy()
    # 按「原始 df 的 dtypes」逐列判定（异构复审 P2-B2）：bool 面板经 reindex
    # 补缺列/行后整帧升型 object，用 raw.dtypes 会整体误入 'S' 路径，
    # 使既有 True 停牌格静默变可交易——恰是本函数要防的回归。
    orig_bool = {c: pd.api.types.is_bool_dtype(t)
                 for c, t in getattr(df, "dtypes", pd.Series(dtype=object)).items()}
    out = np.zeros(raw.shape, dtype=bool)
    for j, col in enumerate(raw.columns):
        if orig_bool.get(col, False):
            out[:, j] = raw[col].fillna(False).astype(bool).to_numpy()
        else:
            out[:, j] = raw[col].astype(object).eq("S").to_numpy(dtype=bool)  # 'R'/None/NaN → False
    return out, missing
```

- **既有 bool 契约**：`suspend=DataFrame(False)`/`True` 仍按 bool 解释（True=停牌），不因 `eq("S")` 回归。**按原始 `df.dtypes` 逐列判定**（异构复审 P2-B2）：bool 面板经 `reindex` 补缺列/行后整帧升型 object（NaN 强制升型），若按 `raw.dtypes` 全帧判定会误入 `'S'` 路径——§3.2.2 末行「缺 7 列由 reindex 产生」正是触发场景。
- **字符串契约**：`'S'`=停牌，`'R'`/None/NaN=可交易。
- 构建器与 loader 共用 `_suspend_mask`（loader 的 eligible 同口径）。
- `suspend_missing_cells/days` 计数；缺 7 列由 reindex 产生 NaN → 同口径。

#### 3.2.3 名称（D2）

```python
name_raw = _frame(name, index, columns, np.nan, object)
name_missing = name_raw.isna().to_numpy()
name_a = name_raw.ffill().fillna("").to_numpy(dtype=object)
```

- 用 `reindex(...).ffill()`（X-3），不用 `reindex(method="ffill")`；不用 `limit_area`（X-4）。
- ST/退市判定基于填充后名称；`name_missing_cells/days` 披露。

#### 3.2.4 参考价/回退（D2/D6）

```python
def _panel(x):
    """DataFrame/Series/ndarray → (T,N) DataFrame；ndarray 需与 index/columns 同形。"""
    if isinstance(x, pd.DataFrame):
        return x.reindex(index=index, columns=columns)
    if isinstance(x, pd.Series):
        return x.to_frame().reindex(index=index, columns=columns)
    return pd.DataFrame(np.asarray(x, dtype=float), index=index, columns=columns)

adj_a = None if adj is None else _panel(adj).to_numpy(dtype=float)
ref_mat = _panel(ref).to_numpy(dtype=float) if ref is not None else _ref_from_adj(prev, adj_a)
fallback = ~np.isfinite(ref_mat) & np.isfinite(prev) & (prev > 0)
if policy.unknown_policy == "fallback_raw":
    ref_mat = np.where(fallback, prev, ref_mat)
ref_fallback_cells = int(fallback.sum())
ref_fallback_days = int(fallback.any(axis=1).sum())
```

- **类型约束**：`ref` 接受 DataFrame/Series/ndarray；ndarray 必须与 `(T,N)` 同形（Step 6 P3-1）。`limit_up/down` 同。
- `adj is None` → loader 传 `ref=prev`（D6），`meta["price_basis"]="raw_close"`、`adj_missing_days=T`。
- `adj_source ∈ {"adj","ref","none"}`；`price_basis_detail ∈ {"raw_adj_ref_full","raw_adj_ref_with_fallback","raw_close"}`。

#### 3.2.5 规则 gap（D3）

```python
pct_mat, gap_mask = _pct_matrix(boards, is_st, is_delisting, dates_arr, return_gaps=True)
rule_gap_cells = int(gap_mask.sum())
rule_gap_days = int(gap_mask.any(axis=1).sum())
rule_gap_reason = "neeq_pre_select" if np.any(gap_mask & (boards == "bse")) else ("unknown_board" if gap_mask.any() else None)
```

- 不抛 `ValueError`；`apply` 侧 `unk |= ~isfinite(pct)` → `limit_unknown`。

#### 3.2.6 一字/限价表（D4/D5）

- `mode=="execution_only_open"`：`one_word_up/down=0`，`meta["one_word_*_cells"]=0`，`one_word_disabled=True`。
- `limit_up/down` 给出：校验 `(T,N)` 成对；用于 `one_word` 与 `inputs` 字段；`limit_table_source="stk_limit"`。
- 未提供限价表（默认路径）：`limit_table_source="self_computed"`（Step 8 P3-③，与 DESIGN §6.1 枚举对齐）。
- 否则用 `compute_limits(prev[t], pct_mat[t], ref=ref_mat[t])` 计 `one_word_*`。

#### 3.2.7 meta/diagnostics

- `meta` 13 键不变；值变化仅：
  - `price_basis="raw_close"`（`ref` 来自昨收时）；
  - `one_word_*_cells=0`（execution_only_open）；
  - `adj_missing_days=T`（adj None）。
- `inputs.diagnostics` 写入 DESIGN §6.1 全部键（含 Step 8 P1-② 回写的 `limit_table_duplicate_rows`）；计数 `int(...)`。

### 3.3 `backtest/tradability_loader.py`（新）

```python
@dataclass(frozen=True)
class TradabilitySpec(object):
    data_root: str = r"E:\Ashare_data"
    panel_dir: str = "market_data"
    policy: TradabilityPolicy = field(default_factory=lambda: TradabilityPolicy(
        execute_at="next_open", unknown_policy="fallback_raw", mode="full"))
    mode: str = "auto"          # auto | full | execution_only_open | off
    auto_degrade: bool = True
    min_coverage: float = 0.99
    stk_limit_path: Optional[str] = None

    def build(self, dates, codes):
        """返回 (TradabilityInputs | None, meta)；off 时 inputs=None。"""
```

实施要点：

1. **面板缓存**：模块级 `_PANEL_CACHE[(data_root, panel_dir, name)] = DataFrame`；每进程只读一次 pickle。
2. **对齐**：`dates/codes` 规范化为 str；所有面板 `reindex(index=dates, columns=codes)`；`prev = close.shift(1)`。
3. **eligible/覆盖率**：`susp_a, missing = _suspend_mask(suspend, dates, codes)`（与构建器共用，bool/object 双路径）；`eligible = isfinite(close) & ~susp_a`；`high_low_coverage = mean(isfinite(high)&isfinite(low), where=eligible)`；`open_coverage`；`prev_close_coverage` **分母排除 t=0**，且 **T≤1 时置 0.0**（无昨收 → 必 off；Step 6 P3-2）。
4. **模式解析**（DESIGN §4.5）：
   - `off` → `(None, meta_off)`；`logger.warning` 记录。
   - `open/prev` 覆盖 < `min_coverage` → `off` + warning。
   - `full` 条件：`high_low_coverage >= min_coverage` 且（`adj` 面板存在或 `ref` 给出）；不足且 `auto_degrade` → `execution_only_open`；不足且 `auto_degrade=False` → `ValueError`。
   - `auto`：满足 full → full；否则 execution_only_open（open/prev 满足时）。
   - 解析结果用 `dataclasses.replace(policy, mode=resolved, execute_at="next_open")` 写入。
5. **限价表（Step 6 P1 修复）**：
   - CSV：`pd.read_csv`；必需列 `ts_code, trade_date, up_limit, down_limit`；`ts_code` → `str[:6]`；**`trade_date` 统一为 `pd.to_datetime(...).dt.strftime("%Y-%m-%d")`**（Tushare 为 `YYYYMMDD`，X-2；不归一化会导致 `reindex` 全 NaN、覆盖层静默失效）。
   - **重复键**：`(code, trade_date)` 重复 → `drop_duplicates(keep="last")` 并计 `limit_table_duplicate_rows`；不静默保留首行。
   - `pivot(index="trade_date", columns="code", values=...)`；reindex 到 `(dates, codes)`。
   - Parquet：本地 `has_pyarrow()` 探测（同 `execution/shell/loaders.py:34-37` 模式，不产生跨包依赖）；缺失 → `ValueError` 提示改用 CSV。
   - 缺格：用自算 `up/down` 填充；`limit_table_missing_cells`；`limit_table_source="stk_limit_partial"`。
6. **调用构建器**：`build_tradability_inputs(...)`；补 loader 诊断 `mode/mode_requested/degrade_reason/*_coverage/codes_not_found`；返回 `(inputs, meta)`。
7. **off 披露**：`meta_off` 含 `mode="off"`、`mode_requested`、`degrade_reason`；loader `logger.warning`（INV-15 第二条通道）。
8. **性能/内存**：面板缓存 ~0.67 GB+/进程（name/suspend 为 object）；`n_workers ≤4` 建议；V-7 实测；超限登记 U-2。

### 3.4 `backtest/engine.py`

1. **校验**（L130-160）：
   - `inputs.adj is None and inputs.ref is None` → `ValueError`（消息改为「需要 adj 或 ref」）。
   - 校验 `ref/limit_up/limit_down` 形状 `(T,N)`、`codes` `(N,)`、`limit_up/down` 成对。
2. **块 v2**（L285-311）：
   ```python
   effective_long, report, apply_diag = apply_tradability_with_diagnostics(
       np.clip(positions, 0.0, None), prev_close, inputs.high, inputs.low,
       inputs.close, inputs.open_, inputs.volume, inputs.suspended, inputs.board,
       inputs.is_st, inputs.dates, policy=inputs.policy, adj=inputs.adj,
       is_delisting=inputs.is_delisting, no_limit=inputs.no_limit,
       ref=inputs.ref, limit_up=inputs.limit_up, limit_down=inputs.limit_down)
   effective = effective_long + np.minimum(positions, 0.0)
   turnover = compute_turnover(effective)
   diag = dict(inputs.diagnostics or {})
   diag.update(apply_diag)
   diag["close_mismatch_cells"] = int(np.count_nonzero(
       ~np.isclose(inputs.close, self._close, equal_nan=True)))
   meta = inputs.meta or {}
   tradability_block = {
       "report": report, "meta": meta, "diagnostics": diag,
       "price_basis": meta.get("price_basis", "raw_adj_ref"),
       "leg_scope": "long_only", "short_leg_unmodeled": True,
       "turnover_basis": "effective_long_only"}
   ```
   - `report` 9 键 int 不变；`meta` 13 键不变；`diagnostics` 新增。
   - **`meta=None` 兼容**（Step 6 P2-3）：既有 TP6-9/9b 构造 `TradabilityInputs` 时不传 `meta`，必须用 `inputs.meta or {}`，否则 `AttributeError`。
   - `close_mismatch_cells` 不阻断（保留 TP6-9b 语义）。
   - `inputs.codes` 若给出：校验 `(N,)` 且唯一；**不**与 DataLoader 股票列序做强制比对（DataLoader 不暴露列名），列序风险由 `close_mismatch_cells` 事后披露（Step 6 P3-5）。
   - **mode 闸门**（异构复审 P3-B7）：`inputs.policy.mode == "off"` 时视同 `tradability_inputs=None`——走 `compute_turnover(positions)` 旧路径、**不挂块**（DESIGN §4.2 / INV-13「off 不挂块」），避免 loader 降级后引擎仍挂全 0 块。
3. **默认路径**：`tradability_inputs is None` 分支零改动；`summary()` 不消费新键。

### 3.5 运行器接线

```python
PipelineBacktestRunner(config=None, tradability_spec=None)
ParallelFactorRunner(n_workers=None, tradability_spec=None)
run_parallel(factor_data, price_data, n_workers=None, tradability_spec=None)
```

- 单跑：`run()` 内 `spec.build(price_data.columns, price_data.index)`（dates, codes）；`inputs=None` 时传 None。
- 并行：`_run_worker` 内 `spec.build(cd, cs)`（dates, codes）；spec 进 args tuple；每 worker 独立缓存。
- **并行结果契约冻结**（异构复审 P2-B3）：worker 返回仍为 `engine.summary()[fn]`（parallel_runner.py:70），**不携带** `tradability` 块；spec 在 worker 内部生效（影响有效仓位/turnover），块级证据需用单进程 `PipelineBacktestRunner` 获取；扩 worker 返回属 B 批。
- `run_quick`（pipeline_integration.py:191-199）**不接线**（非生产快速路径，与 `run()` 的差异以块缺失披露）；如需可 B 批统一。
- `spec=None` → 签名与行为逐位不变。
- **Windows spawn**：spec 是模块级 frozen dataclass（字符串 + policy），无闭包；入口保持 `if __name__`（X-5）。

### 3.6 C 批脚本

`scripts/verify_tradability_consistency.py`：

- 输入：`--data-root`（默认 `E:\Ashare_data`）、`--output`（默认 `out/tradability_consistency.json`）。
- 计算：`ref_adj = _ref_from_adj(prev, adj)`；`ref_ret = close / (1 + stock_return/100)`；逐板块/除权格一致率；BSE 2020-07-27 边界；输出 JSON（含样本数、一致率、mismatch 样例）。
- **规则边界单测**（`tests/test_tradability_consistency.py`，合成数据，Step 8 P2-②）：gem 2020-08-24 前后 10%→20%、ST 2026-07-06 起 5%→10%、低价 ST（`prev<0.1` → ±0.01 元）、half-up 到分；mock 限价表扰动（18/18 一致 + 错价/缺行/多代码/重复键各 1/1 检出 + `limit_table_duplicate_rows`）。
- 不依赖 token；不进 CI（数据根依赖，按 RULE-3 隔离为脚本）。

## 4. 接口实施与回退点

| 接口 | 变更 | 回退点 |
|---|---|---|
| `DEFAULT_LIMIT_RULES` | bse 起点 2020-07-27 | 两行 revert |
| `_pct_matrix(..., return_gaps=False)` | 可选 gap 返回；不抛错 | 删除参数 + 恢复 `rule_pct` 直调 |
| `rule_pct_or_nan`（新） | 新增私有 helper | 删除 helper |
| `TradabilityPolicy` | +`unknown_policy`/`mode` | 删除两字段（默认值不影响旧调用） |
| `TradabilityInputs` | +`ref/limit_up/limit_down/codes/diagnostics` | 删除追加字段 |
| `_suspend_mask`（新，builder/loader 共用） | bool/object 双路径 | 删除 helper + 恢复 `_frame(..., bool)` |
| `_panel`（新，builder 内部） | DataFrame/Series/ndarray 归一 | 删除 helper |
| `apply_tradability_with_diagnostics`（新） | 3 元组 | 删除新函数，`apply_tradability` 恢复原实现 |
| `apply_tradability` | 包装新函数；+可选 `limit_up/down` | 恢复原函数 |
| `build_tradability_inputs` | +`adj=None/ref/limit_up/down` | 单文件 revert |
| `TradabilitySpec`（新） | 新模块 | 删除文件；运行器 `spec=None` |
| `engine._validate/块 v2` | 校验 + diagnostics | 单文件 revert |
| 管道/并行 | 可选 `tradability_spec` | 删除参数（默认 None） |

## 5. 兼容性

### 5.1 Python 版本

| 版本 | 支持 | 说明 |
|---|---|---|
| 3.9 | ✅ | 目标下限；不用 `X \| None`、不用 `match`、不用 `dict \| dict` |
| 3.10–3.12 | ✅ | 同上 |
| 3.13（本机） | ✅ | E1 运行环境 |

### 5.2 依赖兼容

| 组合 | 结论 | 依据 |
|---|---|---|
| pandas 2.0/2.1 + 本实施 | ✅ | 只用 `reindex/ffill/eq/pivot`；不用 2.2 `limit_area`（X-4） |
| numpy 1.22 + 本实施 | ✅ | 只用 `isfinite/count_nonzero/isclose/where` |
| pyarrow 缺失 | ✅ | Parquet 入口 `has_pyarrow()` fail-closed；CSV 路径不受影响 |

### 5.3 向后兼容

- `tradability_inputs=None` / `tradability_spec=None`：旧路径逐位不变（INV-1）。
- 直接调用 `build_tradability_inputs(..., adj=None)` 仍 `ValueError`（`test_adj_required` 保留）；新增 `ref=` 才可运行。
- `apply_tradability` 2 元组契约不变；`report`/`meta` 键集不变。
- 默认 `execute_at` 由 `next_open`（死字段）改为 `same_close`：实际行为不变（旧实现未消费），既有测试零改值。

## 6. 错误处理实施

| 场景 | 异常/处理 | 代码位置 | 测试 |
|---|---|---|---|
| 数据根/必需面板缺失 | `ValueError` | `TradabilitySpec.build` | `test_p021_loader_missing_close` |
| `adj/ref` 都缺（直接构建器） | `ValueError` | `build_tradability_inputs` 入口 | `test_adj_required`（保留） |
| 完全缺 adj（loader） | `ref=prev` + D1；`full` 且 `auto_degrade=False` → `ValueError` | loader 模式解析 | `test_p021_mode_full_no_degrade` |
| `open/prev` 覆盖不足 | `off` + `logger.warning` | loader 模式解析 | `test_p021_mode_off_requested` / `_off_open_missing` / `_t1_off` |
| `full` 不足 + `auto_degrade` | 降级 `execution_only_open` + 诊断 | loader | `test_p021_mode_degrade` |
| `limit_up/down` 不成对 | `ValueError` | `apply`/engine 校验 | `test_p021_limit_table_pair_required` |
| 未知板块 | 不抛错；`limit_unknown` + `unknown_codes` | `_pct_matrix`/apply | 既有 + `test_p021_d3_unknown_board` |
| BSE 2020-07-27 前 | 不抛错；gap + `limit_unknown` | `_pct_matrix` | `test_p021_d3_bse_gap`（改旧断言） |
| 执行价 open 非有限 | 阻塞 + `exec_price_missing_cells` | apply | `test_p021_d1_open_nan_blocks` |
| execution_only_open 下 high/low 缺失 | 一字诊断关闭（`one_word_disabled=True`），成交仍按 open | loader/apply | `test_p021_mode_execution_only_open`（Step 8 P3-②） |
| 停牌面板缺列 | 非停牌 + D3 | builder | `test_p021_d5_suspend_reindex_dtype` |
| 限价表缺格 | 回退自算 + 计数 | loader | `test_p021_mock_stk_limit_perturb` |
| 并行 worker 失败 | 异常上抛 | worker | `test_p021_parallel_worker_error` |

## 7. 不变式实施

| 不变式 | 实施位置 | 验证 |
|---|---|---|
| INV-1 默认路径逐位不变 | `engine.py` `tradability_inputs is None` 分支零改动 | `test_tp6_11_default_baseline_unchanged` |
| INV-2 IC/收益不变 | 指标路径不经过 positions（engine L261-283） | `test_p021_parallel_summary_contract` |
| INV-3 report 9 键 int | `apply` report 初始化 + `int(...)` | `set(report)==9 keys`、`type is int` |
| INV-4 meta 13 键 | builder `meta` 字典不增删键 | `_META_KEYS` 锁 |
| INV-5 same_close 旧行为 | `target_all=target_w`、`exec=high/low` | 既有 19 处调用零改值 |
| INV-6 next_open 语义 | `target_all[1:]=target_w[:-1]`；`exec=open` | `test_p021_d1_*` |
| INV-7 fallback 无 NaN | `ref = where(fallback, prev, ref)` | `test_p021_d2_*` |
| INV-8 BSE 不抛错 | `_pct_matrix` gap | `test_p021_d3_*` |
| INV-9 `'S'` only | `suspend.eq("S")` | `test_p021_d5_suspend_s_only` |
| INV-10 限价表优先 | `limit_up/down` 分支 | `test_p021_mock_stk_limit_perturb` |
| INV-11 JSON 可序列化 | `int(...)`/`.item()`；meta 无 Counter | `test_p021_pipeline_passthrough` |
| INV-12 并行切片一致 | `spec.build(cd, cs)` 同口径 | `test_p021_parallel_slice_equal` |
| INV-13 off 旧路径 | loader 返回 None；engine 不挂块 | `test_p021_mode_off_noop`、`test_p021_engine_mode_off_gate` |
| INV-14 execution_only_open 同构 | `next_open` 分支 + `one_word_disabled` | `test_p021_mode_execution_only_open` |
| INV-15 降级披露 | diagnostics / loader warning | `test_p021_mode_degrade`、`test_p021_mode_off_requested` |

## 8. 测试策略

### 8.1 测试文件与用例

| 文件 | 用例组（Step 9 实测） | 数量（实测） |
|---|---|---|
| `tests/test_tradability.py`（改） | bse 断言改写（`_pct_matrix(return_gaps=True)` + `limit_unknown>=1`）；既有 `test_error_table_contracts` 引为 F-3/C-3 证据 | 0 新增（1 处改写） |
| `tests/test_tradability_inputs.py`（未改） | 既有 `test_adj_required` 保留（E-2）；`ref=` / suspend `'S'` 由新文件承载 | 0 新增 |
| `tests/test_tradability_next_open.py`（新） | 目标后移、open 谓词、首日/末信号、3 元组契约、wrapper、execution_only_open、off、block、policy 校验 | 11 |
| `tests/test_tradability_fallback.py`（新） | adj 缺口回退、D1、pass legacy、`ref=` 直传、loader 无 adj + full 不降级 | 5 |
| `tests/test_tradability_bse.py`（新） | 2020-07-27 规则、pre-select gap、apply gap、未知板块、`'S'`/bool/reindex dtype | 7 |
| `tests/test_tradability_mode.py`（新） | auto→full、full→execution_only、off、阈值、`one_word_disabled`、T≤1 off、缺 close/代码 | 10 |
| `tests/test_tradability_loader.py`（新） | 签名、pickle、缓存（P-5）、切片一致（INV-12，Step 10 #7 加强为全量子块 report 直接对比）、**字符串 index 面板归一化**（DR-13）、**list_date 单行 DataFrame**（观察项 #9） | 6 |
| `tests/test_tradability_consistency.py`（新） | 规则边界 5 + mock 限价表扰动 2 + E-6 不成对 1 | 8 |
| `tests/test_tradability_pipeline.py`（新） | 管道/并行透传、`mode=off` 闸门、worker 错误、签名、**partial 限价表引擎块标记**（DR-15） | 6 |
| `tests/test_backtest/test_engine.py`（未改） | 块 v2/`close_mismatch` 由 `test_p021_pipeline_passthrough` 承载；TP6-9/9b/10/11 零改值 | 0 新增 |

> **计划 vs 实测（Step 9 + Step 10）**：新增合计 **53** 例（`-k "p021"` → 53 passed / 6 skipped，Step 10 修复后实测）。原计划中的 loader 专项（CSV/Parquet 缺失、`trade_date` 归一单测）未单列：`trade_date` 归一由 `test_p021_mock_stk_limit_perturb`（`YYYYMMDD` 输入）隐式覆盖，Parquet 缺失分支为静态核验（K-4）；原计划 `test_backtest/test_engine.py +3` 改由管道测试承载（块 v2/`close_mismatch`）。Step 10 审计修复新增 3 例（`test_p021_loader_str_index_panels` / `test_p021_loader_list_date_panel` / `test_p021_partial_limit_source_block`）。

### 8.2 测试隔离（RULE-3）

- 单测全部用合成面板（`pd.DataFrame` / numpy），**不读** `E:\Ashare_data`。
- loader 测试用 `tmp_path` 写小 pickle/CSV fixture；`TradabilitySpec(data_root=tmp_path)`。
- 并行测试用 `n_workers=2` + 小 fixture；Windows spawn 兼容。
- C 批一致性脚本本体依赖真实数据根、不进 pytest；其 Tushare 格式 mock 扰动部分以 `tests/test_tradability_consistency.py`（合成数据）承载，与 §10 C 行一致（异构复审 P3-B6 消除矛盾）。

### 8.3 既有测试改写

| 用例 | 现状 | 改法 |
|---|---|---|
| `tests/test_tradability.py:448-452` | 断言 bse 2020-01-06 `ValueError`（`target_w` 全 0） | 改为：① 直调 `_pct_matrix(board, is_st, ..., dates, return_gaps=True)` 断言 gap>0；② apply 侧给 nonzero `target_w` 后断言 `report["limit_unknown"] >= 1`（2 元组 report 9 键冻结、无 gap 键——异构复审 P3-B4，原「或 gap 计数>0」经 report 不可达） |
| `tests/test_tradability_inputs.py:166-170` | `adj=None` 抛 `ValueError` | **保留**；新增 `ref=` 可运行用例 |
| `tests/test_backtest/test_engine.py:778-815` | 默认 policy 下 `blocked_buy>=1`；`TradabilityInputs` 不传 `meta` | **断言不改**（库默认 same_close）；实现必须容忍 `meta=None`（§3.4 P2-3） |
| `tests/test_backtest/test_engine.py:818-844` | TP6-9b 不传 `meta`；改 `inputs.close` | **断言不改**；实现必须容忍 `meta=None` |
| `tests/test_backtest/test_engine.py:871-892` | TP6-11 默认基线 | **不改**（INV-1） |

### 8.4 红→绿计划（Step 9 执行，Step 5 只登记）

| 批次 | 先写用例 | 预期红（改代码前） | 预期绿（改代码后） |
|---|---|---|---|
| A1 | `test_p021_d3_bse_gap`（直调 gap + nonzero target 双路径）、`test_p021_d5_suspend_s_only` | bse 抛 `ValueError`；`'R'` 被当停牌 | 不抛错 + gap>0（直调）+ nonzero target 下 `limit_unknown>0`；`'R'` 可交易 |
| A2 | `test_p021_d1_signal_shifted`、`test_p021_d1_open_predicate` | 目标未后移；用 high/low 判定 | 目标后移；open 判定 |
| A3 | `test_p021_d2_fallback_raw`、`test_p021_mode_degrade` | ref 保持 NaN；无 mode 字段 | ref=prev；mode 诊断 |
| A4 | `test_p021_parallel_slice_equal` | loader 不存在 | 对齐/切片一致 |
| C | `test_p021_mock_stk_limit_perturb` | 适配器不存在 | 18/18 + 4 类扰动检出 |

### 8.5 性能预算

| 项 | 预算 | 验证 |
|---|---|---|
| 单次 `build`（全样本） | ≤30 s | V-7（未执行；P-1 待办） |
| 并行每 worker 峰值 | ≤1 GB | V-7（U-2） |
| `apply` 全样本 | 与 v3.9.10 同阶（O(T) 日循环） | 计时对比 |
| 无新增 O(T×N) Python 循环 | 静态检查 | 读码 + 基准 |

## 9. 幻觉抑制审查（Step 6 Review）

### 9.1 依赖版本验证

- [x] 无新增依赖 → PyPI 新版本查询 N/A（理由：零新增）
- [x] Python 3.9 下限 API 核对：`Optional`、`dataclasses.replace`、`np.isfinite/count_nonzero/isclose`、`pd.reindex/ffill/eq/pivot` 均 ≥ 下限
- [x] 无虚构库/函数：Qlib/Tushare/pandas/Python/numpy 锚点均为实读（X-1~X-7）
- [ ] pyarrow 缺失路径在 CI 环境复跑（依赖安装矩阵，非阻断）

### 9.2 接口签名验证

- [x] `TradabilityPolicy` 新字段有默认值，既有位置参数调用不破
- [x] `TradabilityInputs` 追加字段在末尾且有默认值，关键字构造兼容
- [x] `apply_tradability_with_diagnostics` 参数与 DESIGN §4.2 一致；`apply_tradability` 包装保持 2 元组
- [x] `build_tradability_inputs` 新参数均有默认值；`adj/ref` 至少一个
- [x] `TradabilitySpec.build` 返回 `(inputs|None, meta)`；`Optional` 兼容 3.9
- [x] `PipelineBacktestRunner` / `ParallelFactorRunner` / `run_parallel` 新增参数均有默认 None

### 9.3 实施与设计对齐

- [x] 每个模块对应 DESIGN §3.2；每个接口对应 DESIGN §4
- [x] D1-D6 均落到代码位置（§3.1-§3.5）
- [x] 无设计未覆盖的实施（新增仅 C 脚本与测试）
- [x] 报告/元数据契约冻结（INV-3/INV-4）

### 9.4 低效操作排除

- [x] 无 O(T×N) Python 循环新增（apply 逐日 T；日内向量化）
- [x] 无重复读 pickle（模块级 `_PANEL_CACHE`）
- [x] 无父进程全量 `TradabilityInputs` pickle（spec 懒加载）
- [x] 无 `iterrows` 限价表（pivot/reindex）
- [x] 无 `reindex(method="ffill")` 误区（X-3）
- [x] 无 numpy 标量入 JSON（X-6）

### 9.5 Step 6 复审记录

- 方式：独立只读子代理（general-purpose，未给编辑权限）读取 IMPLEMENTATION/DESIGN + 6 个代码/测试文件 + pyproject.toml；按 6 项检查逐条核对。
- 结论：**PASS_WITH_FIXES（1×P1 / 3×P2 / 5×P3）**，全部处置：
  - **P1**（`stk_limit` CSV 的 `trade_date` 未归一化；Tushare 为 `YYYYMMDD`，与 `dates` 的 `%Y-%m-%d` 不一致 → `reindex` 全 NaN，覆盖层静默失效）→ §3.3(5) 增加 `pd.to_datetime(...).strftime` + 重复键 `drop_duplicates` + `limit_table_duplicate_rows`。
  - **P2-1**（`exec_missing = busy & ...` 依赖 pending 之后才定义的 `busy`，顺序不可实现）→ §3.1.4 改为 `missing_exec` 先定义，pending/delta 两阶段分别计数。
  - **P2-2**（仅 `.eq("S")` 会让既有 bool `True` 停牌静默变可交易；loader 同缺陷）→ §3.2.2 新增 `_suspend_mask` bool/object 双路径，builder/loader 共用。
  - **P2-3**（`inputs.meta.get(...)` 在 `meta=None` 时 `AttributeError`；TP6-9/9b 正是此构造）→ §3.4 改为 `(inputs.meta or {})`，§8.3 登记两例。
  - **P3-1**（`ref` 类型未定；`_frame` 要求 `.reindex`，ndarray 会崩）→ §3.2.4 新增 `_panel` 归一（DataFrame/Series/ndarray）。
  - **P3-2**（T=1 时 `prev` 分母 0 → `nan < min_coverage` 恒 False，永不 off）→ §3.3(3) 置 0.0。
  - **P3-3**（`unknown_policy="block"` 无消费分支）→ §3.1.4 增加 `can_buy/sell &= judge`。
  - **P3-4**（wrapper 参数序未写）→ §3.1.4 补完整签名；policy 保持第 12 位，新参数追加末尾。
  - **P3-5**（`inputs.codes` 与引擎列序未校验）→ §3.4 声明只校验长度/唯一性，列序由 `close_mismatch_cells` 披露。
- **复审确认 PASS**：零新增依赖；3.9 API 下限；模块/接口/INV 全覆盖；低效排除表成立；`np.isclose(equal_nan=True)` 形状已由 `_validate` 锁定。
- **复审后版本**：v1.0 in-review → **v1.1 verified**；DESIGN 不变（v1.2）。

### 9.6 异构复审记录（双视角并行，2026-11-23）

- 方式：两个并行只读子代理（general-purpose，未给编辑权限）。**视角 A** = 证据锚点对抗核查（§2.2 + X-1~X-10 + RESEARCH 数字逐字比对）；**视角 B** = 工程/接口/测试对抗核查（§3-§11 × 真实代码与测试 10 文件）。两视角互不共享结论。
- **视角 A：PASS**（0×P1 / 1×P2 / 3×P3），全部处置：
  - **P2-A**（X-1 精确行号、X-2 外部数值离线不可复核）→ §2.3 注记：Step 9 实施时留存快照/URL hash 落盘 `spec/p021-*/anchors/`。
  - **P3-A1**（X-7 漏 `all` extra L58 亦含 pyarrow）→ X-7 已补注；结论不变（既有可选、非新增）。
  - **P3-A2**（X-9 层级未区分摘要级条目）→ 层列已注明：关键规则由 A-1/A-4~A-7 条款级承载，A-2/A-3/A-8~A-13 为摘要级。
  - **P3-A3**（A-20/A-21 跨文档层列口径差：RESEARCH 层列 T1 vs 本表 T3）→ X-8 加注（RESEARCH 系全文抓取状态口径，本表从严 T3）；RESEARCH 不改版。
  - 确证：X-10 全部 E1 数字与 RESEARCH 逐字一致；X-4 `limit_area` 2.2.0 新增经 pandas whatsnew GH#56149 确证；X-3/X-5/X-6 与官方文档语义一致。
- **视角 B：PASS_WITH_FIXES**（1×P1 / 2×P2 / 4×P3），全部处置：
  - **P1-B1**（`missing_exec` 无条件生效破坏 same_close 逐位一致：现行为对 NaN high/low 放行（tradability.py:385-386），`test_tradability.py:434-439` 断言 `blocked_buy==0`，无差别拦截必挂且 §8.3 未登记）→ §3.1.4(2)(4)：`missing_exec_effective` 仅 `next_open` 生效，same_close 恒 False。
  - **P2-B2**（`_suspend_mask` 全帧 dtype 判定漏口：bool 面板经 reindex 补缺列整帧升型 object → 误入 `'S'` 路径 → 既有 True 停牌格静默变可交易——正是该函数要防的回归）→ §3.2.2 改按**原始 `df.dtypes`** 逐列判定。
  - **P2-B3**（并行 worker 返回 `summary()` 丢弃 `tradability` 块，§3.5/§8.1 未规划断言）→ §3.5 声明并行结果契约冻结（块不外传、spec 内部生效、块证据走单进程；扩返回属 B 批）；§8.1 补契约断言。
  - **P3-B4**（bse 断言改写不可直接执行：原用例 `target_w` 全 0 → `limit_unknown` 恒 0；2 元组 report 无 gap 键）→ §8.3 改为直调 `_pct_matrix(return_gaps=True)` + nonzero target 双路径。
  - **P3-B5**（阻塞格 `exec_price_missing_cells` 双计：pending 与 busy 同日同格各计一次）→ §3.1.4(4) delta 阶段加 `pending == 0` 条件。
  - **P3-B6**（测试矩阵缺口：DESIGN §10.3 `test_p021_d4_*` 无对应组；§8.2 与 §10 C 行文件矛盾；`run_quick` 未接线）→ §8.1 补 D4 组；§8.2 措辞对齐；§3.5 声明 `run_quick` 不接线。
  - **P3-B7**（引擎缺 mode 闸门：`policy.mode=="off"` 的 inputs 仍调 apply 并挂全 0 块，违背 DESIGN §4.2/INV-13）→ §3.4 增闸门：off 视同 None。
  - 复核确认 PASS：`TradabilityInputs`（frozen）末尾追加字段合法且不破坏 14 字段序；wrapper 保持 policy 第 12 位（tests:39-43 兼容）；现签名已含 `ref`（tradability.py:306），追加 `limit_up/down` 无冲突；engine 接线点（校验 L130-160 / 块 L285-311 / result L313-332）与真实代码一致；`TradabilitySpec` frozen dataclass pickle 走实例 `__dict__`，`default_factory` lambda 属类属性不入实例态 → Windows spawn 安全；`testpaths=["tests"]` 兼容新文件命名；3.9 / pandas 2.0 API 下限守住；diagnostics 独立字典不触 report 9 键 / meta 13 键冻结。
  - 勘误（不计级）：`has_pyarrow` 实际位于 `backtest/execution/shell/loaders.py:34`。
- **复审后版本**：v1.1 → **v1.2 verified**（本节处置均已落盘对应章节）；DESIGN → v1.3（Step 8 补键，见 §9.7）。

### 9.7 Step 8 三对文档一致性复审记录（2026-11-23）

- 方式：主会话机械校验（版本锚点 grep、术语计数、INV/用例组 grep、链接可达、`git status`）＋ 独立只读子代理六项语义核对。结论 **PASS_WITH_FIXES（2×P1 / 2×P2 / 6×P3）**，全部处置：
  - **P1-①** C 批验收项在 CHECKLIST 零对应 → CHECKLIST §2 增 F-19/F-20/F-21，§10.1 78→81。
  - **P1-②** `limit_table_duplicate_rows` 未回写 DESIGN → DESIGN §4.6/§6.1 补行（DESIGN 升 v1.3）。
  - **P2-①** RESEARCH L439 过期版本引用 → 就地勘误为 v1.3。
  - **P2-②** 本文件 §3.6/§8.1 未逐项列 C 批 → §3.6 补规则边界四项，§8.1 补 `tests/test_tradability_consistency.py` 行。
  - P3-①～P3-⑥ → DESIGN §2.1 引用列、本文件 §6 补行、§3.2.6 `self_computed` 默认、§3.2.7「DESIGN §6.1」消歧、§8.1 补 4 个测试名；CHECKLIST C-4 词表补 `same_close`、F-12/N-10 补 `self_computed` 场景。
  - 复核确认 PASS：D1-D6 十条逐行可追溯、INV-1~15 双向齐备、术语七词一致、版本无第三种混入、CHECKLIST §10.1 形态/算术合规。
- **复审后版本**：v1.2 → **v1.3 verified**（本节处置；无接口契约变更，`limit_table_duplicate_rows` 契约变更落 DESIGN 侧）。

### 9.8 Step 9 TDD 实施记录（2026-11-23）

- **红→绿**：C/A1 首跑 **6 failed / 8 passed**（`_pct_matrix` 缺 `return_gaps` → `TypeError`；BSE `ValueError`；停牌 `'S'` 未识别；旧 bse 断言；loader `ModuleNotFoundError`）→ 全绿；A2/A3/A4 测试先行后绿。新增合计 **50** 例（consistency 8 / bse 7 / next_open 11 / fallback 5 / mode 10 / loader 4 / pipeline 5），`-k "p021"` → **50 passed / 6 skipped**；tradability 相关 9 文件 **89 passed**；TP6 基线定向 **4 passed**。
- **§8.1 同步**：计划数改为实测数；未单列的 loader CSV/Parquet 专项按「`trade_date` 归一由 `test_p021_mock_stk_limit_perturb` 隐式覆盖、Parquet 缺失为静态核验（K-4）」登记；`test_engine.py` 零改值（块 v2/`close_mismatch` 由 `test_p021_pipeline_passthrough` 承载）。
- **测试名校正**：§6/§7 计划名与实现名不一致的 11 处已改为实际函数名（`..._pair_required`、`..._suspend_reindex_dtype`、`..._mock_stk_limit_perturb`、`..._pipeline_passthrough`、`..._mode_off_noop`、`..._mode_off_requested`、`..._d2_fallback_raw`、`..._mode_execution_only_open`、`..._d1_open_nan_blocks` 等）。
- **C 批实跑**：`scripts/verify_tradability_consistency.py`（E1 数据根）→ n_dates=1394、n_codes=5688、有限格 6,784,896、一致率 **95.82%**（`rtol=1e-3, atol=0.005`；公式级内部对拍，非外部准确率）；BSE 2020-07-27=0.30、2020-07-24=null。
- **版本**：包 3.10.0（6 锚点）+ CHANGELOG v3.10.0；CHECKLIST v1.2（81 项 = 74 通过 / 0 失败 / 7 待办，待 Step 10）。
- **版本**：v1.3 → **v1.4**（Step 9 实测同步；无接口/契约变更）。

### 9.9 Step 10 独立 ADD 审计处置记录（2026-11-23）

- **审计**：独立只读子代理（异构基座，3 组定向重放 57 例全绿 + 2 次 python -c 只读验证）→ **PASS_WITH_FIXES**，质量门 **4.3/5 档位 A**，**1×P1 / 2×P2 / 5×P3**（详见 CHECKLIST §12.2 逐行处置）。
- **P1-①** 引擎合并覆盖 `stk_limit_partial`（INV-10 块级失真）→ `engine.py` 合并后按 `limit_table_missing_cells>0` 恢复标记 + `test_p021_partial_limit_source_block` 红→绿（DR-15）。
- **P2-①** off no-op diagnostics 10 键偏离 DESIGN §4.2 锁定的 2 键 → 实现收窄为 2 键 + `test_p021_mode_off_noop` 键集合断言（DR-14）。
- **P2-②** Step 9 后修复未登记 → 本节 + §8.1（53 例）+ §11.1 DR-13 登记；同时登记 **loader 面板 index 归一化**修复（真实数据根字符串日期 → 恒 `off`，修复后 `mode=full`、eligible 7,203,655 格）。
- **P3-#4/#5/#6** DESIGN §6.1 补 `coverage` 键、来源列勘正（DESIGN 升 v1.4）；**#7** INV-12 测试加强为全量子块 report 直接对比；**#8** `_run_worker` docstring 6 元组；**#9（观察项）** 补 `test_p021_loader_list_date_panel`。
- **性能补证**：P-1 全样本完整构建 15.90 s（≤30 s）✅；K-5 重跑 SHA `82728CE1…` 逐位一致 ✅；P-2 实测 worker RSS 3348 MB > 1 GB 预算 → CHECKLIST §6 登记待办。
- **定向回归**：tradability 相关 10 文件 **97 passed / 20 skipped**；`-k "p021"` → **53 passed / 6 skipped**；全量重跑读数见 CHECKLIST §12.1。
- **版本**：v1.4 → **v1.5**（Step 10 处置；DR-13~15 为新增派生需求登记，接口契约变更仅 P1-① 的披露恢复，与 DESIGN §6.1 对齐）。

## 10. 实施步骤（Step 9 执行顺序）

| 步骤 | 文件 | 内容 | 测试 |
|---|---|---|---|
| **C** | `scripts/verify_tradability_consistency.py` + `tests/test_tradability_consistency.py` | `ref_ret` vs `ref_adj`、规则边界、mock 限价表扰动 | 先红后绿 |
| **A1** | `tradability.py` / `tradability_inputs.py` / `tests/test_tradability.py` | BSE 2020-07-27 + gap；`'S'` only | `test_p021_d3_*`、`test_p021_d5_suspend_s_only` |
| **A2** | `tradability.py` / `engine.py` / `tests/test_tradability_next_open.py` | `next_open` + `apply_tradability_with_diagnostics` + 块 v2 | `test_p021_d1_*`、`test_p021_engine_*` |
| **A3** | `tradability_inputs.py` / `tradability_loader.py` / `tests/test_tradability_mode.py` | `ref` fallback、data tier、D6 模式解析 | `test_p021_d2_*`、`test_p021_mode_*` |
| **A4** | `tradability_loader.py` / `pipeline_integration.py` / `parallel_runner.py` / `tests/test_tradability_loader.py` | spec、管道/并行接线、限价表 | `test_p021_loader_*`、`test_p021_pipeline_*` |
| **A5** | 版本/台账/全量 | 3.10.0、CHANGELOG、PROGRESS/PROJECT_STATUS、全量回归 | V-1~V-15 |

## 11. 派生需求与未决项

**11.1 派生需求（实施中新增、非 DESIGN 显式声明）**：

- **DR-1** `close_mismatch_cells`：DESIGN §9.7 复审新增；实施于 engine；不阻断（保留 TP6-9b 语义）。
- **DR-2** `_PANEL_CACHE` 进程内缓存：DESIGN §4.5 已声明「进程内缓存」，实施细节（key 粒度）为派生。
- **DR-3** `limit_table_source="stk_limit_partial"`：DESIGN §6.1 已列枚举，实施中新增「缺格回退自算」具体路径。
- **DR-4** `mode_off` 的 `meta_off` 返回结构：DESIGN §4.5 只写「返回 None」；实施补 `{mode, mode_requested, degrade_reason, coverage}` 供 loader warning（Step 10 审计 #5 勘正第 4 键；INV-15 要求 warning 含 coverage）。
- **DR-5** `_suspend_mask` bool/object 双路径：DESIGN §5.7 只写 `'S'` only；实施需兼容既有 bool 面板（True=停牌），否则回归。
- **DR-6** `unknown_policy="block"` 的消费分支：DESIGN §4.1 列了 `block`；实施在 `apply` 中以 `can_buy/sell &= judge` 落地。
- **DR-7** `_panel` 归一：DESIGN 未限定 `ref/limit_up/down` 的容器类型；实施支持 DataFrame/Series/ndarray。
- **DR-8** `trade_date` 归一 + 重复键去重：DESIGN 只写 CSV 列名；实施按 Tushare `YYYYMMDD` 归一。
- **DR-9** T≤1 的 `prev_close_coverage=0.0`：DESIGN 只写「排除 t=0」；实施补边界。
- **DR-10** `meta=None` 兼容：DESIGN 未提；实施用 `(inputs.meta or {})` 兼容既有构造。
- **DR-11** 引擎 mode 闸门：`inputs.policy.mode=="off"` 视同 None、不挂块（异构复审 P3-B7；DESIGN §4.2/INV-13）。
- **DR-12** 并行结果契约冻结：worker 返回仍为 `summary()`，`tradability` 块不外传（异构复审 P2-B3；扩返回属 B 批）。
- **DR-13** 面板 index 归一化（Step 10 审计 P2-② 登记）：真实数据根面板 index 为字符串日期（object）→ `_read_panel` 归一化 `pd.to_datetime`；非日期索引面板（如 list_date 元数据表）解析失败容错跳过。否则 reindex 全 miss → `eligible_cells=0` → 默认 spec 恒 `off`（真实数据根复现）。测试 `test_p021_loader_str_index_panels`。
- **DR-14** off no-op diagnostics 收窄（Step 10 审计 P2-①）：`apply_tradability_with_diagnostics` 的 `mode=="off"` 分支返回 2 键 `{"mode","schema_version"}`，对齐 DESIGN §4.2 锁定文本；`test_p021_mode_off_noop` 断言键集合。
- **DR-15** 引擎 `stk_limit_partial` 标记恢复（Step 10 审计 P1-①）：引擎合并 diagnostics 时 `limit_table_missing_cells>0` → 强制 `limit_table_source="stk_limit_partial"`（apply 侧无条件写 `"stk_limit"` 会覆盖 builder 的 partial 标记，INV-10）。测试 `test_p021_partial_limit_source_block`。

**11.2 未决项**：

- **U-7** `min_coverage` 阈值标定（DESIGN §11.1；E0，首个生产批次后）。
- **U-2** 并行内存（E0；V-7 实测）。
- **U-1** `stk_limit` 外部一致率（E0；token 到位后 V-8）。
- **U-8** `close_mismatch_cells` 阈值（E0；当前只披露不阻断）。

---

**Review 签字**: Step 6 独立只读复审（PASS_WITH_FIXES；1×P1/3×P2/5×P3 已处置，§9.5）＋ 异构复审双视角（A: PASS，1×P2/3×P3；B: PASS_WITH_FIXES，1×P1/2×P2/4×P3——均已处置，§9.6） 日期: 2026-11-23
