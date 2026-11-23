# 设计文档：P-006 tradability 接入回测引擎与限价取整口径

---
id: p006-tradability-engine-integration-DESIGN
type: design
version: 1.3
status: draft
date: 2026-11-23
depends: [p006-tradability-engine-integration-RESEARCH]
upstream: null
---

> **Feature**: P-006 —— `tradability` 接入 `FactorBacktestEngine`，并入 P-007 限价取整口径
> **创建日期**: 2026-11-23
> **状态**: draft（Step 3-6 完成；v1.1 = Step 4 异构复审 PASS_WITH_FIXES 已处置：0×P1 + 4×P2 + 7×P3，记录见 §14；v1.2 = Step 5/6 实施周期发现的 6 处小勘误：meta 补 `rounding_basis`、dataclass 加 `eq=False`、unknown 覆盖非正 prev/ref、`no_limit` 优先于 `limit_unknown`、`pct` 越界校验、`ref` 对齐 float 近似披露；v1.3 = Step 8 文档一致性复审 PASS_WITH_FIXES 已处置：0×P1 + 1×P2 + 7×P3 —— §4.1 `board_of` 改区间映射（P2-1）、§4.6 签名补 `st_overrides`（P3-1），记录见 §15；Step 7 [CHECKLIST.md](./CHECKLIST.md) 已建表，Step 8 文档一致性 §1 15/15 通过）
> **Spec 步骤**: Step 3-4（本文件）；Step 5 见 [IMPLEMENTATION.md](./IMPLEMENTATION.md)
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.4**（Step 1 + Step 2 引用复核 PASS）
> **档位**: **T1**（改动 `backtest/engine.py`、`backtest/tradability.py` + `tests/`，属 Layer-1 运行时）
> **包版本**: **3.9.8 → 3.9.9**（patch；默认路径零变更，理由见 D11）

---

## 1. 设计目标

1. **接入**：让引擎路径真正调用限价规则 —— `FactorBacktestEngine` 新增可选 `tradability_inputs`，启用后 `_build_positions` 产出的目标权重先经 `apply_tradability` 推进，再计算换手与输出 `tradability` 报告；默认 `None` 时逐位不变。
2. **定口径**：`limit_price` 改为**整数分 half-up**（禁用 `np.round`），并落地一档三分支、除权参考价、板块/ST/退市分治、低价 ST 下限、无涨跌幅限制日六个边界。
3. **可审计**：`limit_unknown`、`one_word_*`、`price_basis`、`leg_scope` 全部进入输出；未知板块不得默认按 10%。

## 2. 设计依据

### 2.1 调研结论 → 设计决策

| 调研发现 | 设计决策 | 引用 |
|---|---|---|
| 本仓无 `limit_up/limit_down` 字段；原料齐备（close/adj/name/suspend/high/low） | **D1** 规则自算（方案 B）为主路径；不引入外部数据依赖 | RESEARCH §3.6.1 / §6.4 U-3 |
| tie 占 7.05%/10.85%/10.85%（5%/10%/30% 档），20% 档恒 0；`np.round` 相对 half-up 翻转涨停 37、跌停 714（3.56%） | **D2** 整数分 half-up；附 tie 用例与属性测试 | RESEARCH §3.6.3 / §6.4 U-1 |
| 上/深 3.3.17/3.3.19 三分支：四舍五入、差额 <1 档 ±1 档、限价 <1 档取 1 档 | **D3** 三分支显式实现，NaN 安全（防整型下溢） | RESEARCH §3.1 / §5.4 S1/S3 |
| BSE 2026 规则全文无取整条款 | **D4** 按沪深同构 half-up，披露"无明文"假设 | RESEARCH §3.6.4 / U-2 |
| `_board` 缺 `302/689/920/83` 共 298 列（5.2%），且无 `unknown` 出口 | **D5** 单一 `board_of`；`unknown` 为一等值，限价判为不可判定 | RESEARCH §3.6.2 / R-2 |
| 名称含 "ST 或 退" 合计 104,921 股票日（日均 133 只，RESEARCH §3.6.2）；002499 退市整理首日 −52.38% | **D6** `ST` 与 `退` 分治；退市整理首日无涨跌幅限制 | RESEARCH §3.6.2/§3.6.7 / R-4 |
| 除权参考价可反推 97.9%；81 个交易日 `adj` 缺失 | **D7** `ref = prev × adj_{t-1}/adj_t`；缺 adj 标 `limit_unknown`，禁回退原始昨收 | RESEARCH §3.6.5 / R-5 |
| 0.3 启发式相对精确规则差 3.1%（漏 1,235/多 498）；eps=0 召回 56% | **D8** eps 业务容差为 0（整数分）；一字板独立字段；0.3 仅诊断 | RESEARCH §3.6.6 / §6.7 / R-3 |
| 低价 ST：窗口 0 例，全样本 1 例（窗外）；规则为"限制 0.01 元" | **D9** 显式 `prev < 0.1 且 ST → ±1 tick` 分支（与一档分支等价，保留以实现裁决） | RESEARCH §3.6.7 / U-7 |
| 引擎 `_build_positions` 产出**有符号**权重（含统计空头）；LS 收益由因子直接计算、不消费仓位 | **D10** 可交易性只作用于**多头腿**；空头腿透传并标记 `unmodeled`；LS 收益/IC 口径不变 | RESEARCH §3.5 / ADR-0002 |
| 引擎仅接收 `close`，判定原料未进入数据契约 | **D11** 新增 `TradabilityInputs` + 纯函数构建器；默认 `None` 零加载、零变更 | RESEARCH §6.1 / §6.2-9 |
| 名称切换日可能早于公告（002122 早 7 个交易日） | **D12** 名称只作初判；构建器输出 `st_date_unverified` 计数，公告覆盖表留作输入钩子 | RESEARCH §6.7 / R-6 |

### 2.2 相关 ADR

`spec/adr/` 未落盘，本设计直接遵循 `SPEC_PROCESS.md` Step 4 内联的两条教训：
- **ADR-0001**：不得为论证强度裁剪证据形态（本设计不把 A2 摘要级证据外推为估计量，不把 A4 预印本作门禁）。
- **ADR-0002**：显式声明职责外与能力边界（见 §2.3）。

### 2.3 职责边界

**职责内**：限价价格计算、可交易性判定、引擎多/空腿接入、报告字段、输入构建器与板块/ST/退市派生。

**职责外（不回答）**：
- 组合级 P&L、实际撮合与成交量约束（属组合回测/容量证据链，本引擎的 LS 收益是因子统计量）；
- 分钟级封板时序、封单量、开板次数（需分钟数据范式）；
- 接入 Tushare `stk_limit` 等外部限价字段（U-3 裁决：本批不引入新依赖）；
- 修正引擎 `_compute_fwd_returns` 的复权口径（P-006 不动默认路径；R-1 只约束限价判定用 raw+ref）。

**能力边界（回答不了）**：
- 日频只能判"收盘是否钉在限价"，无法区分一字板、T 字板与盘中开板（一字板仅作独立披露）；
- 名称面板无法百分百校准 ST/退市生效日（002122 已实证偏差 7 个交易日）；
- 未映射板块（B 股/其他代码）无法判定限价，只能 `limit_unknown`；
- 统计空头腿在 A 股不可执行，本设计不对其建模；
- 引擎无法自动检测调用方给 `TradabilityInputs.close` 喂入的口径（dl 内无复权标记可查）：口径正确性靠构建器契约 + `price_basis` 披露，不靠运行时数值校验（登记为 §14 P2-3 残余）。

## 3. 架构设计

### 3.1 整体架构

```
调用方（脚本/研究代码）
   │  pandas 面板：close/high/low/open/volume/suspend/name/adj/list_date
   ▼
tradability_inputs.build_tradability_inputs()   ← 新增（pandas，纯函数）
   │  TradabilityInputs(T,N 数组 + board/is_st/is_delisting/no_limit/adj) + meta
   ▼
FactorBacktestEngine(..., tradability_inputs=...)   ← 新增可选参数；None → 旧路径
   │  _build_positions(factor) → positions(T,N)
   │  long_target = clip(positions, 0, None)        ← 只对多头腿判定
   ▼
tradability.apply_tradability(long_target, ...)     ← 既有函数扩展可选 kwargs
   │  compute_limits → limit_price（整数分 half-up）
   │  → effective_long(T,N) + report(dict)
   ▼
effective = effective_long + min(positions, 0)      ← 空头腿原样透传
   │  compute_turnover(effective) → turnover
   ▼
results[factor]['tradability'] = {report, meta, price_basis, leg_scope}
```

### 3.2 模块划分

| 模块 | 职责 | 输入 | 输出 | 依赖 |
|---|---|---|---|---|
| [tradability.py](../../backtest/tradability.py) | 规则表、`board_of`、`limit_price`、`compute_limits`、`apply_tradability` | numpy 数组 + 日期/板块/ST | `(effective_w, report)` | numpy（保持无 pandas/无 IO） |
| [tradability_inputs.py](../../backtest/tradability_inputs.py)（新增） | 面板 → `TradabilityInputs` + meta；板块/ST/退市/无限制日派生 | pandas 面板 | 数据类 + meta dict | numpy + pandas（允许 IO 由调用方完成） |
| [engine.py](../../backtest/engine.py) | opt-in 接入；多头腿判定；报告挂载 | `data_loader` + `tradability_inputs` | `results[factor]` 新增 `tradability` 键 | `tradability`、`factor_metrics` |
| [factor_metrics.py](../../backtest/factor_metrics.py) | **不改**：换手与 LS 收益口径保持 | —— | —— | —— |
| [panels.py](../../backtest/execution/shell/panels.py) | **不改**：`_board` 仅用于容量报告计数，不参与限价规则选择（避免 `board_counts` 变化） | —— | —— | —— |

### 3.3 数据流

1. 调用方按 `(dates × stocks)` 传入面板；构建器对齐到 `close.index/columns`，全部缺失填 NaN/False；
2. `board` 由列代码经 `board_of` 映射为 `{main, star, gem, bse, unknown}`；
3. `is_st` 由 `stock_name` 含 `ST` 逐日派生为 `(T,N)`；`is_delisting` 由含 `退` 派生；`no_limit` = IPO 后前 5 个交易日 ∪ 退市整理名称首日；
4. `adj` 原样透传；`prev_close` 一律由 **`inputs.close`（不复权）位移一行**得到（`t=0` 为 NaN → `limit_unknown`）；引擎 `dl.price_data['close']` 只用于前向收益，与判定口径分离（R-1：同一函数内禁止混用，两口径以 `price_basis` 披露）；
5. 判定按日推进：`pct` 矩阵按 (board, is_st) 状态缓存；`ref` 仅除权日与 `prev_close` 不同；
6. 结果：`effective_long` 回填到有符号权重，`turnover` 用有效权重计算；报告写入 `results[factor]['tradability']`。

### 3.4 控制流

`_evaluate_factor` 内：
`positions = _build_positions(factor)` → `tradability_inputs is None ? compute_turnover(positions) : 多头腿 apply_tradability → 合并 → compute_turnover(effective)`。
IC/ICIR/Decay/HitRate/Spread/LS 收益的计算顺序与输入完全不变。

## 4. 接口定义

### 4.1 `board_of`

```python
def board_of(code) -> str:
    """单一板块映射（区间口径，依据深交所《证券代码区间表》锚点 E7 / IMPL D-6-4；
    Step 8 P2-1 勘误：由枚举改区间）：600/601/603/605、000–004（含 001 CDR）→ main；
    300–309（含 3098–3099 存托凭证）→ gem；688/689 → star；43/83/87/92 → bse；
    其余 → 'unknown'（禁止默认 main）。接受 int / '600000' / '600000.SH'。
    """
```

### 4.2 `limit_price`（重写，签名不变）

```python
def limit_price(prev_close, pct, side="up"):
    """涨跌幅限制价格 = 基准价 × (1 ± pct)，整数分 ROUND_HALF_UP。

    基准价 = ref（除权日，见 §4.3）否则 prev_close；下文"prev"均指该基准价。
    基准价→整数分的提取必须 round-half-up（如 (x*100+0.5)//1 的整数路径），
    禁止 int() 截断（浮点陷阱：3.33×100 = 332.999…，截断会低估 1 分）。
    以分为单位的整数运算：(prev_cents×(10000±pct_bp)+5000)//10000；
    随后应用 S1 3.3.17 / S3 3.3.19 三分支：
      ① |limit − prev| < 1 分 → prev ± 1 分；
      ② limit < 1 分 → 1 分；
      ③ 其余取整数分结果。
    NaN 输入返回 NaN（先掩码后转 int64，禁止 rint(NaN) 整型下溢）。
    side 非法 → ValueError；有限但 pct ∉ [0,1] → ValueError；
    标量入参返回 float，数组入参返回同形状 ndarray。
    """
```

### 4.3 `compute_limits`

```python
def compute_limits(prev_close, pct, ref=None, is_st=None, low_price_st_rule=True):
    """返回 (up, down, unknown)。

    ref: 除权（息）参考价；None 时等于 prev_close（basis=raw）。
         ref 由 adj 比率计算时先按 half-up 对齐到分（交易所参考价本身为
         两位小数报价；float 意义下的近似——精确 x.xx5 构造输入可能偏
         ±1 分，见 IMPLEMENTATION D-6-17，真实 hfq 比率命中概率≈0）；
         adj 单侧缺失（adj[t-1]/adj[t] 恰有一个无效）
         与双侧缺失同样 → unknown，不回退。
    unknown: ~isfinite(prev) | ~isfinite(pct) | (ref 提供但无效) | prev<=0 | ref<=0 | 未知板块。
             （已映射板块规则无命中仍 ValueError，见 §7。）
    低价 ST（is_st & prev<0.1 元）：up = prev+1 分，down = max(prev−1 分, 1 分)。
    """
```

### 4.4 `apply_tradability`（向后兼容扩展）

```python
def apply_tradability(target_w, prev_close, high, low, close, open_, volume,
                      suspended, board, is_st, dates, policy=None,
                      adj=None, is_delisting=None, no_limit=None, ref=None):
    """权重推进；返回 (effective_w, report)。

    扩展入参（默认 None 时与 v3.9.8 行为一致；is_st 为既有入参，新增 2D 支持）：
      adj:         (T,N) 后复权因子；给出时按 ref=prev×adj[t-1]/adj[t] 计算除权参考价。
      is_st:       接受 (N,) 或 (T,N)；2D 表示逐日 ST 状态。
      is_delisting:(N,) 或 (T,N)；为真时按板块普通档（不套 ST 5%）。
      no_limit:    (T,N) bool；为真且非停牌时不做限价判定、busy 格自由成交不计数
                   （IPO 前 5 日/退市整理首日等）；为真且停牌仍进 blocked_suspend。
      ref:         (T,N) 预计算参考价；优先于 adj。
    report 新增键：limit_unknown, one_word_up, one_word_down（键集合 6→9 为
    有意变更，见 INV-9；"默认 None 行为一致"仅指权重推进路径逐位一致）。
    board 允许 'unknown'：该格限价不可判定，计入 limit_unknown，不抛 ValueError。
    """
```

### 4.5 `TradabilityInputs`

```python
@dataclass(frozen=True, eq=False)
class TradabilityInputs:
    close: np.ndarray          # (T,N) 原始不复权收盘
    high: np.ndarray           # (T,N)
    low: np.ndarray            # (T,N)
    open_: np.ndarray          # (T,N)
    volume: np.ndarray         # (T,N)
    suspended: np.ndarray      # (T,N) bool
    dates: np.ndarray          # (T,) 升序日期字符串
    board: np.ndarray          # (N,) {main,star,gem,bse,unknown}
    is_st: np.ndarray          # (T,N) bool（逐日）
    adj: np.ndarray            # (T,N) 后复权因子（引擎路径必填）
    is_delisting: np.ndarray = None   # (T,N) bool
    no_limit: np.ndarray = None       # (T,N) bool
    policy: TradabilityPolicy = None
    meta: dict = None                 # 构建器产出，引擎原样回显
```

### 4.6 `build_tradability_inputs`

```python
def build_tradability_inputs(close, high, low, open_, volume, suspend, name,
                             adj, list_date=None, policy=None, st_overrides=None):
    """pandas 面板（dates×stocks）→ (TradabilityInputs, meta)，纯函数、无 IO。

    meta 键：board_counts / unknown_codes(≤20) / st_stock_days /
             delisting_stock_days / no_limit_cells / no_limit_source /
             adj_missing_days / one_word_up_cells / one_word_down_cells /
             st_date_unverified / st_calibration_source /
             price_basis="raw_adj_ref" / rounding_basis（"inferred_half_up" 若含 bse，
             否则 "exchange_half_up"）。
    no_limit_source ∈ {"list_date", "delisting_only"}：list_date 缺失时
    IPO 前 5 日豁免静默失效是被禁止的——退化为仅退市整理首日，并以
    no_limit_source="delisting_only" 显式披露。
    st_overrides: ST 生效日覆盖表 [code, effective_date]（R-6 钩子，D-6-3；
    Step 8 P3-1 勘误：签名补参，与 IMPL §4.4 / CHECKLIST §3.6 对齐）。
    st_calibration_source ∈ {"none", "coverage_table"}：未提供覆盖表时
    st_date_unverified=0 仅表示"未尝试校准"，以 source="none" 披露。
    同一 (code) 的板块只映射一次；未知板块计入 unknown 且不改写为 main。
    """
```

### 4.7 引擎构造与结果

```python
FactorBacktestEngine(dl, config=None, fwd_returns=None, tradability_inputs=None)

# 启用时 results[factor] 新增：
"tradability": {
    "report": {"blocked_buy": int, "blocked_sell": int, "blocked_suspend": int,
               "t1_locked": int, "deferred": int, "carried": int,
               "limit_unknown": int, "one_word_up": int, "one_word_down": int},
    "meta": {...},                       # 构建器 meta，只读回显
    "price_basis": "raw_adj_ref",
    "leg_scope": "long_only",
    "short_leg_unmodeled": True,
    "turnover_basis": "effective_long_only",
}
# 未启用时 results[factor] 的键集合与 v3.9.8 完全一致。
```

## 5. 替代方案

### 5.1 方案 A：opt-in 引擎参数 + 规则自算（选择）

- 描述：本设计；`TradabilityInputs` 显式传入，默认 `None`。
- 优点：默认路径零加载/零改动；口径可解释、可单测；不新增数据依赖。
- 缺点：调用方需准备 6~8 个面板（由构建器收敛为一次调用）。
- 选择理由：满足验收②（默认不变）且满足①（引擎路径确实调用限价规则）。

### 5.2 方案 B：读外部 `limit_up/limit_down`（否决）

- 描述：接入 Tushare `stk_limit` 或落盘字段。
- 否决理由：本仓 17 个数据文件均无该字段；引入网络/第三方依赖与版本漂移；U-3 已裁决本批不引入。

### 5.3 方案 C：沿用 0.3 启发式直接接线（否决）

- 描述：把 `verify_long_side_research.py` 的阈值判据搬进引擎。
- 否决理由：相对精确规则差 3.1%（漏 1,235/多 498），阈值无规则出处；不可审计。

### 5.4 方案 D：挂在 `DataLoaderV3` / `data_bridge` 上（否决）

- 描述：把 high/low/suspend 等塞进 `price_data`，所有消费者共享。
- 否决理由：外部包契约变更；默认所有调用方被迫加载与校验，违背"数据契约最小化"（RESEARCH §6.2-10）。

### 5.5 方案 E：改造 LS 收益为仓位驱动 P&L（否决）

- 描述：用 `sum(w_eff × fwd_ret)` 替代因子直接计算的 LS 收益。
- 否决理由：改变默认指标语义与全部既有读数；属组合回测 feature，超出 P-006 边界。

## 6. 数据结构

### 6.1 报告 schema（`apply_tradability` 返回值）

| 键 | 类型 | 含义 |
|---|---|---|
| `blocked_buy` | int | 因涨停导致无法加仓的格数（停牌、未知、无限制日另计） |
| `blocked_sell` | int | 因跌停被拒的减仓格数（T+1 另计） |
| `blocked_suspend` | int | 停牌导致无法调整的格数 |
| `t1_locked` | int | 因 T+1 锁定的卖出意图格数 |
| `deferred` | int | 补成交格数（前日挂起、当日成交） |
| `carried` | int | 期末仍未对齐目标的股票数 |
| `limit_unknown` | int | 限价不可判定格数（adj 缺失/首日/未知板块） |
| `one_word_up` | int | `high==low==up` 的一字涨停格数（诊断，不计入 blocked） |
| `one_word_down` | int | `high==low==down` 的一字跌停格数（诊断） |

`limit_unknown`、`one_word_*` 已在 RESEARCH §6.6 R-3/R-5 要求；其余六键沿用 v3.9.0。

**单桶优先级链**（每格至多计入一个 blocked/unknown 桶；v1.2 调整：`no_limit` 先于 `limit_unknown` —— 无涨跌幅限制日不需要 adj，缺失不应误计）：

```
suspended          → blocked_suspend（最高优先，沿用现有基线）
no_limit & busy    → 不计桶（非停牌无涨跌幅限制日 busy 格自由成交）
~can_judge         → limit_unknown（非停牌、非 no_limit：unknown board / NaN prev / NaN pct / ref 或 adj 无效）
blocked_buy/sell   → 价格可判定但触限
t1_locked          → blocked_sell 的 T+1 子集扣除项（沿用现有实现）
```

组合裁决示例：未知板块 + 意图买入 + 停牌 → `blocked_suspend`（停牌优先）；NaN prev + 非停牌 + 买入 → `limit_unknown`；NaN prev + 停牌 → `blocked_suspend`；IPO 日 + adj 缺失 → 不计桶（`no_limit` 优先）。

### 6.2 状态派生规则（构建器）

| 字段 | 规则 | 依据 |
|---|---|---|
| `board` | `board_of(code)`；未知 → `unknown` | R-2 |
| `is_st` | `name` 逐日含 `ST`（含 `*ST`），**不含** `退` | R-4 |
| `is_delisting` | `name` 逐日含 `退` | R-4 |
| `no_limit` | IPO 后前 5 个交易日（`list_date` 起）；退市整理名称首日；suspended 日不参与。**`list_date=None` 时禁止静默失效**：退化为仅退市整理首日，meta `no_limit_source="delisting_only"` 披露 | S1 3.3.13 / S4 4.5.5 / §14 P2-4 |
| `adj` | 原样透传；非正/缺失/单侧缺失（`adj[t-1]` 与 `adj[t]` 恰有一个无效）→ 该日 `limit_unknown` | R-5 / §14 P3-6 |
| `st_date_unverified` | 名称切换日与公告覆盖表不一致的股票数；meta `st_calibration_source` ∈ {`none`,`coverage_table`} 区分"未尝试校准"与"已校准无偏差" | R-6 / §14 P3-5 |

## 7. 错误处理

| 错误场景 | 处理方式 | 用户可见信息 |
|---|---|---|
| 数组形状与 `(T,N)` 不符 | `ValueError`，指出字段名与实际形状 | `close 形状应为 (T,N) (实际 …)` |
| `dates` 长度 ≠ T | `ValueError` | `dates 长度应为 T` |
| `board` 未知值 | 不抛错；该格 `limit_unknown` | 报告计数 + meta `unknown_codes` |
| 规则表无命中（如日期早于 1996） | 已映射板块仍 `ValueError`（沿用）；未知板块跳过 | `无涨跌幅规则: board=… date=…` |
| `adj` 缺失/非正/单侧缺失 | 该格 `limit_unknown`，不回退 prev | 报告 `limit_unknown` |
| `prev_close` 为 NaN（含 t=0） | 非停牌 → `limit_unknown`（不阻塞、不计入 blocked 分母）；停牌 → `blocked_suspend`（优先级链见 §6.1） | 同上 |
| `high/low` 为 NaN | 视为无封板证据（不 block），但若 `close` 缺失且停牌标记为真则按停牌 | —— |
| `pct` 有限但 ∉ [0,1] | `ValueError`（`limit_price` 入口） | `pct 越界: …` |
| 引擎启用但 `inputs.adj is None` | `ValueError`（禁止 raw 基准确认缺失） | `tradability 需要 adj` |
| 引擎启用但形状不匹配引擎网格 | `ValueError` | 字段名 + 期望/实际 |
| `np.round` 残留调用 | 单测静态断言禁止（grep `np.round` in `tradability.py`） | 测试失败信息 |

## 8. 不变式（Invariants）

1. **INV-1 默认零变更**：`tradability_inputs=None` 时，`results[factor]` 的键集合、数组逐位值与 v3.9.8 完全一致（无新增键、无额外面板加载）。
2. **INV-2 整数分 half-up**：`limit_price` 全程整数分运算，`np.round`/`rint` 不得参与限价取整；NaN 入 → NaN 出（先掩码后转 int64）。
3. **INV-3 未知不默认**：`board='unknown'` 的格子只产生 `limit_unknown`，绝不套用 10% 或其他档位。
4. **INV-4 除权基准**：除权日限价用 `ref≠prev_close`；`adj` 缺失 → `limit_unknown`，不回退 `prev_close`。
5. **INV-5 计数互斥**：每格至多计入一个 blocked/unknown 桶，按 §6.1 优先级链裁决：`suspended > no_limit > limit_unknown > blocked_* > t1_locked`；`no_limit` 非停牌 busy 格不入桶（自由成交）。
6. **INV-6 ST/退分治**：`退` 永不走 ST 5% 分支；退市整理首日不判封板。
7. **INV-7 空头腿不动**：引擎启用时 `effective[positions<0] == positions[positions<0]`（逐位），且 `effective >= 0` 部分来自多头腿推进。
8. **INV-8 规则表不变**：`DEFAULT_LIMIT_RULES` 零新增/零改写，`_validate_rules` 通过。
9. **INV-9 报告类型**：九个计数键恒为 Python `int`，与系数值无关（空面板为 0）。键集合 6→9 属有意变更（`apply_tradability` 直接调用方可见；引擎 `results[factor]` 仅在启用时新增 `tradability` 键，未启用时与 v3.9.8 一致——见 INV-1）。

## 9. 幻觉抑制审查（Step 4 Review）

### 9.1 设计基于已验证的调研结论

- [x] 所有设计决策可追溯到 RESEARCH.md（§2.1 表逐条给了章节号）
- [x] 无未经验证的假设（BSE 取整、低价 ST 语义均显式标注"无明文/推定"）
- [x] 无论证驱动的归因扭曲（A2 摘要级、A4 预印本仅作方向性依据，未引具体估计量）

### 9.2 替代方案审查

- [x] 至少列 2 个替代方案（B/C/D/E 共 4 个）
- [x] 每个替代方案有明确的否决理由

### 9.3 职责边界审查

- [x] 职责边界清晰（§2.3 区分职责外与能力边界）
- [x] 不越界吞并其他研究范式（不碰撮合、分钟时序、复权收益修正）

> **Step 4 独立复审待执行**：本节为作者自检，不作为 Review 结论。

## 10. 对实施的输入

### 10.1 关键工程约束

1. `tradability.py` 顶层依赖保持 `stdlib + numpy`，禁止 pandas/IO（构建器另文件）。
2. `limit_price` 与 `compute_limits` 必须先掩码再转整型；`np.rint(NaN)` 下溢是已发生过的 P1（RESEARCH §3.6.3）。
3. `pct` 矩阵按日按状态缓存：每日至多 10 次 `rule_pct` 调用（board×ST 组合上限），禁止 `T×N` 次 Python 级查表。
4. `TradabilityInputs` 数组只借用引用，不复制；引擎只做形状/有限性校验。
5. 报告键只在启用时出现；`results[factor]` 的既有键顺序不得调整。
6. 不修改 `factor_metrics.py`、`data_bridge.py`、`verify_long_side_research.py`（后者 0.3 路径登记为诊断，不进门禁）。
7. 不修改 `panels.py`：其 `_board` 只用于容量报告计数、不参与规则选择；R-2 的"单一映射"约束限定在 tradability 判定路径内，避免 `board_counts` 桶变化。
8. 包版本 7 个落点：`pyproject.toml:7`、`__init__.py:58`、`config_v2.py:371`、`reporting.py:40`、`tests/test_fix3_version_unification.py:34`、`tests/test_backtest/verify_fix3_manual.py:21`、`CHANGELOG.md` 顶部。
9. V3.8.0 §14 "ST 5% `[未核实]`" 回填为 `[已核实-官方]`（S4/S7 + 本批实测），本 Step 3 已执行（见 §13）。

### 10.2 风险与缓解

| 风险 | 缓解措施 |
|---|---|
| 整数分重写与既有 `np.round` 结果不一致 | tie 定向用例 + `Decimal(ROUND_HALF_UP)` 属性测试（≥1,000 随机 2 位价格 × 4 档） |
| 默认路径被无意改动 | INV-1 逐位断言 + 代码分支只在 `is not None` 时进入 |
| 未知板块静默按 10% | INV-3 断言 + `board_of` 单元测试覆盖 302/689/920/83 |
| adj 缺失导致除权日误判 | INV-4 + `limit_unknown` 计数断言 |
| 空头腿被误施加 A 股规则 | INV-7 逐位断言 + `leg_scope="long_only"` 披露 |
| 名称日期偏差（002122） | `st_date_unverified` 披露 + 公告覆盖表钩子（R-6），不在本批做全量校准 |
| 大面板性能退化 | `pct` 缓存（每日 ≤10 次查表）+ 纯向量化比较；构建器一次性派生 |
| 调用方给 `inputs.close` 喂复权价 | 引擎无法自动检测（能力边界 §2.3）：构建器 `price_basis` 披露 + 文档契约约束；TP6-9 用 raw 口径合成盘固化语义 |
| `list_date` 缺失使 IPO 豁免失效 | 禁止静默：退化为 `delisting_only` 并以 `no_limit_source` 披露（§6.2） |

### 10.3 验收映射

| PROGRESS 验收项 | 本设计的落点 | 验证方式 |
|---|---|---|
| ① 引擎路径调用限价规则 | §3.4 / §4.7：`apply_tradability` 在 `_evaluate_factor` 内被调用 | T-6-9/10（合成盘涨停日断言 blocked>0） |
| ② 默认路径输出不变 | D11 / INV-1 | T-6-11（默认结果逐位对照） |
| ③ 回归用例 | §8 INV-1~9 | T-6-1~12（见 §10.4） |
| ④ 限价取整裁决落 DESIGN | D2/D3/D4/D9 + §5 | tie 用例 T-6-1/2；BSE 假设 T-6-4 |

### 10.4 测试计划（TP6）

| ID | 用例 | 断言 |
|---|---|---|
| TP6-1 | tie 定向：`10.25` up/down、`3.33` up/down | `11.28 / 9.23 / 3.66 / 3.00`（注：四例中仅 `10.25 down` 对现版 `np.round` 有区分度 9.23 vs 9.22，其余三例双路径碰巧一致，由 TP6-2 兜底） |
| TP6-2 | 属性测试：价格由整数分生成（`cents/100`）× {5,10,20,30}%，与 `Decimal(str(x)).quantize(…, ROUND_HALF_UP)` 逐值相等 | 0 差异（含 NaN 掩码） |
| TP6-3 | 三分支：`0.01`、`0.09`、`0.10` 边界的 up/down | 差额 <1 分 → ±1 分；<1 分 → 1 分 |
| TP6-4 | BSE 30% + 无明文假设披露 | `10.00 → 13.00 / 7.00`；meta 含 `rounding_basis="inferred_half_up"` |
| TP6-5 | `board_of` 全前缀 + 302/689/920/83 + 未知 | 未映射返回 `unknown`，无默认 `main` |
| TP6-6 | 除权日：`prev=10, adj_prev/adj_t=0.5` | `ref=5`，涨停 `5.50`；非除权日 `ref==prev`（<1e-6） |
| TP6-7 | `adj` 缺失（双侧/单侧）/ `prev` NaN / ref 非分对齐 | `limit_unknown` 计数 >0，`blocked_*` 不增加；ref 先对齐到分（§4.3） |
| TP6-8 | `退` 名称 + 退市整理首日 `no_limit` | 不落 ST 5% 分支；首日不判封板 |
| TP6-9 | 引擎启用：合成盘涨停日 | `blocked_buy>0`，`turnover` 与未启用时不同，`tradability` 键存在 |
| TP6-10 | 引擎启用：空头腿 | `effective[neg] == positions[neg]`；`short_leg_unmodeled=True` |
| TP6-11 | 引擎默认：同一合成盘 | 与 Step 5 改动前采集的基线字面量（`summary()` + `turnover` 数组）逐位一致；无 `tradability` 键 |
| TP6-12 | 低价 ST（`prev=0.09`）与一档分支等价性 | 显式分支结果 == 通用三分支结果（逐值） |

## 11. 未决项登记（四元块）与决策矩阵

**11.1 未决项登记**：

- **U-D1 真实面板 37/714 翻转读数的测试化**
  - **判据**：Step 9 以只读探针对 382,161 个 tie 格复算，读数与 RESEARCH §3.6.3 一致（涨停 37 / 跌停 714）。
  - **触发条件**：Step 9 回归执行时；若数据文件版本变化则重算并更新基线。
  - **当前倾向**：不把 382k 面板塞进单测；以 TP6-1/2 保证算法正确，Step 9 探针读数记入 CHECKLIST 作证据。
  - **证据等级**：E1。

- **U-D2 空头腿的可执行语义**
  - **判据**：是否有组合回测引擎需要融券/股指期货空头约束。
  - **触发条件**：启动组合级 P&L feature 时（非 P-006）。
  - **当前倾向**：本设计只对多头腿判定，空头腿 `unmodeled` 披露。
  - **证据等级**：待核（职责外）。

- **U-D3 ST 生效日公告覆盖表**
  - **判据**：公告覆盖表覆盖数据窗口内全部 ST 切换事件。
  - **触发条件**：`st_date_unverified > 0` 且影响档位边界（±1 日跨涨跌停）时。
  - **当前倾向**：本批只留输入钩子与计数披露，不做全量校准（R-6 允许）。
  - **证据等级**：E1（3 例抽查 1 例偏差）。

**11.2 决策矩阵**：不启用 —— 本设计的方案选择均为**可逆（Type-2）**（opt-in、默认零变更、可单独回退），无 Type-1 不可逆决策。

## 12. 设计决策登记

| ID | 决策 | 理由/依据 |
|---|---|---|
| D1 | 引擎 opt-in + 规则自算（方案 A） | U-3；验收② |
| D2 | 整数分 half-up，禁 `np.round` | U-1；S1 3.3.17 / S3 3.3.19 |
| D3 | 三分支（四舍五入 / 差额 <1 档 / 限价 <1 档） | 同上 |
| D4 | BSE 同构 half-up（无明文，披露假设） | U-2；S5 |
| D5 | 单一 `board_of`（判定路径）；`unknown` 一等值；`panels._board` 计数用途不改 | R-2；298 列未映射 |
| D6 | ST 与退市分治；退市整理首日无限制 | R-4（ST∪退 104,921 股票日，日均 133 只）；S4 4.5.5 / S6 §7 |
| D7 | 除权用 `ref=prev×adj_{t-1}/adj_t`；缺失即 unknown | R-5；S1 4.3.2 / S4a 4.4.3 |
| D8 | eps 业务容差 0；一字板独立计数；0.3 仅诊断 | U-6；R-3 |
| D9 | 低价 ST 显式 ±1 tick 分支 | U-7；S6 §7 |
| D10 | 只判多头腿，空头腿透传 | ADR-0002；引擎 LS 语义 |
| D11 | `TradabilityInputs` + 构建器；默认 None 零加载 | §6.2-10；验收② |
| D12 | 名称仅初判 + `st_date_unverified` 披露 | R-6；002122 实证 |

## 13. V3.8.0 §14 回填记录

`docs/research/RESEARCH_V3.8.0_EXECUTION_CAPACITY.md` §14 制度时间线中：
`| ST 股 5% | 现行 | 需在设计中二次核验具体规则文本 | [未核实] |`
→ 回填为 `[已核实-官方]`，并注明依据：深交所 2023 规则 4.5.5（主板风险警示 5%）、上交所风险警示板办法第七条（5% + 前收 <0.1 元→0.01 元）、2026-07-06 起主板 ST 放宽至 10%（S7）。

## 14. Step 4 异构复审记录（2026-11-23，独立子代理）

> **复审方式**：独立子代理以怀疑视角复审本文件 v1.0——E1 算术重放 4 组（临时脚本置于 %TEMP%、用后删除、仓库零写入：整数分公式 24,000 样本属性对照、TP6-12 全分值扫描、20% 档 tie 恒 0 的 c=0..2,000,000 全扫描、现有代码桶语义采样）+ 契约可实现性静态读码（engine.py / tradability.py / factor_metrics.py / test_tradability.py 逐行）+ 边界完备性 + 引用追溯（§2.1 十二条 + §10.1 版本落点七处 + V3.8.0 §14 回填实证）。

> **总结论**：**PASS_WITH_FIXES** —— 0×P1 + 4×P2 + 7×P3；全部为设计层口径澄清，无算术错误、无不可实现签名、引擎接入陈述与代码一致。已全部处置，版本升 v1.1。

**E1 重放对照表（全部 ✅）**：

| # | 重放项 | 结果 |
|---|---|---|
| R1a-d | tie 四例（10.25/3.33 × up/down）整数分公式 vs Decimal half-up | 逐值一致（11.28/9.23/3.66/3.00）；`np.round` 现版 10.25 down = 9.22 翻转实锤 |
| R2 | 24,000 随机整数分价格 × {5,10,20,30}% vs Decimal | 不一致计数 **0**，最大偏差 0 分 |
| R3 | TP6-12 等价性：prev<0.1 元整数分全扫描（c=1..9 分） | 通用三分支 == 显式低价分支，**逐值等价**（c<10 分时 \|1.05c−c\|<0.5 分必触发分支①） |
| R4 | 20% 档 tie 恒 0：`c×12000 mod 10000` 全扫描 | 违反 0；每 100k 价格中 5%/10%/30% 档 tie 数 5000/10000/10000，20% 档 0 |
| R5a-c | 现有代码桶语义采样（NaN prev × 停牌 × unknown board） | 停牌优先入 `blocked_suspend`；unknown 现版抛 ValueError（新语义为增强） |
| R5d | `np.round` ties-to-even 演示 | `np.round(10.25×0.9)=9.22 ≠ 9.23`，D2 裁决方向获证 |

**问题处置表**：

| 编号 | 级别 | 问题摘要 | 处置 |
|---|---|---|---|
| P2-1 | P2 | 报告桶优先级两处明文冲突（INV-5"停牌只进 blocked_suspend" vs §4.4/§7 unknown 归属），组合场景不可裁决 | **已修**：§6.1 新增单桶优先级链 + 三条组合裁决示例 + `no_limit` busy 格不入桶；INV-5 同步改写。**v1.2 再调整**：`no_limit` 置于 `limit_unknown` 之前（无涨跌幅限制日不需要 adj，缺失不应误计），现行链 `suspended > no_limit > limit_unknown > blocked_* > t1_locked` |
| P2-2 | P2 | §4.4"默认 None 行为一致"与 INV-9 九键 report 张力 | **已修**：§4.4 限定为"权重推进路径逐位一致，键集合 6→9 属有意变更"；INV-9 补两调用方差异说明 |
| P2-3 | P2 | `inputs.close` 与引擎 close 口径一致性未闭环（R-1 无引擎路径抓手） | **已修**：§3.3-4 明确 prev_close 一律由 `inputs.close`（raw）位移，dl close 只用于收益；§2.3 能力边界登记"引擎无法自动检测喂入口径"；§10.2 补风险行 |
| P2-4 | P2 | `list_date=None` 时 IPO 前 5 日豁免静默失效 | **已修**：禁止静默——退化为仅退市整理首日 + meta `no_limit_source` 披露（§4.6/§6.2/§10.2） |
| P3-1 | P3 | 基准价→整数分提取方式未写明（int() 截断陷阱） | **已修**：§4.2 补 round-half-up 提取路径，禁止截断 |
| P3-2 | P3 | 三分支"prev"在除权日应指 ref，未明说 | **已修**：§4.2 注明基准价定义 |
| P3-3 | P3 | §4.3"规则缺失"与 §7 ValueError 语义冲突 | **已修**：§4.3 unknown 成因限定为"未知板块" |
| P3-4 | P3 | D6 行把 ST∪退 合计数 104,921 归到"退"单侧名下 | **已修**：改为"ST 或退 合计"，引用 §3.6.2/§3.6.7 |
| P3-5 | P3 | `st_date_unverified=0` 无法区分"已校准"与"未校准" | **已修**：meta 增 `st_calibration_source` ∈ {none, coverage_table}（§4.6/§6.2） |
| P3-6 | P3 | adj 单侧缺失未显式覆盖；ref 可为非分对齐价格 | **已修**：§4.3 ref 先 half-up 对齐到分 + 单侧缺失 → unknown；TP6-7 同步 |
| P3-7 | P3 | TP6-1 四例中三例对现版 np.round 无区分度 | **已修**：TP6-1 加区分度注（仅 10.25 down 有区分度，TP6-2 兜底） |

**复审确认无问题的关键点**：公式量纲、frozen dataclass 可实现性（py3.9）、`apply_tradability` 位置兼容（新 kwargs 追加于 policy 后；2D is_st 实现改动点 = tradability.py L133-134/L149）、引擎接入陈述（positions 唯一消费点 L246-247；LS 收益输入为因子非仓位 L251，D10 陈述正确）、现有测试无键数断言（九键兼容）、§2.1 引用逐条存在、版本七落点行号属实、panels 不改决策与 R-2 兼容。

复审后状态：**0×P1 / 0×未处置**，可进入 Step 5（IMPLEMENTATION）。

---

## 15. Step 8 文档一致性复审记录（2026-11-23）

> 独立只读复审（异构基座），对象 RESEARCH v1.4 / DESIGN v1.2 / IMPLEMENTATION v1.1 / CHECKLIST v1.0；判据为 CHECKLIST §1 共 15 项。**总结论：PASS_WITH_FIXES —— 0×P1 + 1×P2 + 7×P3**；15 项中 12 ✅ / 3 ⚠️ / 0 ❌（⚠️ 三项根因均为下表 P2-1 / P3-1 / P3-5，处置后转 ✅）。已全部处置，DESIGN 升 v1.3、IMPLEMENTATION 升 v1.2、CHECKLIST 升 v1.1。

| 编号 | 级别 | 问题摘要 | 处置 |
|---|---|---|---|
| P2-1 | P2 | §4.1 `board_of` 残留枚举口径（000/001/002/003→main、300/301/302→gem），与 IMPL §3.1-1/§4.1/D-6-4 及 CHECKLIST 的区间口径（000–004/300–309，依据 E7 深交所代码区间表）相反——对 004 与 303–309 给出相反结果 | **已修**：§4.1 改区间映射并在 docstring 标注依据；IMPL §11 D-6-4 来源改引 §4.1（v1.3）+E7 |
| P3-1 | P3 | §4.6 `build_tradability_inputs` 签名缺 `st_overrides=None`（IMPL §4.4 / CHECKLIST §3.6 均含） | **已修**：签名补参，docstring 注明 R-6 钩子 |
| P3-2 | P3 | IMPL §2.3 文件树注释残留旧 TP6 归属；§10 Step 1 测试清单漏 TP6-6 | **已修**：IMPL §2.3 注释与 §1/§3.4 统一；TP6-6 由 Step 2 移入 Step 1 |
| P3-3 | P3 | IMPL §6 错误表缺「high/low NaN」行（DESIGN §7 / CHECKLIST §5 有） | **已修**：IMPL §6 补行（NaN 比较为 False → 不 block、一字板不计；隐式覆盖 + CHECKLIST §5 负例） |
| P3-4 | P3 | IMPL §7 INV-9 验证方式写「TP6-9 断言全 int」，与 CHECKLIST §2.2 的 9 键 int 断言归属不一致 | **已修**：IMPL §7 INV-9 改指 CHECKLIST §2.2 |
| P3-5 | P3 | IMPL 头部「Step 5 勘误 5 处」与 DESIGN v1.2「6 处小勘误」计数差 1 | **已修**：IMPL 头部改「Step 5/6 勘误 6 处」（第 6 处 ref float 限定系 Step 6 P3-2 处置、D-6-17 登记） |
| P3-6 | P3 | RESEARCH §6.4 U-6 残余（eps 0 与 1 tick 两档并列披露）在 CHECKLIST 无记录位 | **已修**：CHECKLIST §2.2 增「U-6 残余敏感性读数」行，Step 9 执行 |
| P3-7 | P3 | CHECKLIST §1.4 D4 行 RESEARCH 锚点误写 §3.5（应为 §6.6 R-1） | **已修**：锚点订正 |

复审确认无问题的关键面：A1 决策追溯 12/12、A2 未决项 7/7 闭合、A3 风险落点 6/6、B1 模块落点 5/5、B5 改动面无越界、C1/C2 验收覆盖与 TP6 编号一一对应、D1-D3 术语一致；E1 状态词扫描 12 处命中均为历史记录/已闭合条目/披露块，无状态漂移；E2 关键数字（20% 档 tie 恒 0、22.7%/8,941、104,921、版本七落点、9 键、pct ≤10 次/日、0.1 元门槛）跨文档一致。

复审后状态：**0×P1 / 0×未处置**，可进入 Step 9（TDD 红→绿）。

---

**Review 签字**: _________ 日期: _________
