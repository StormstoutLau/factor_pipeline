# 实施文档：P-006 tradability 接入回测引擎与限价取整口径

---
id: p006-tradability-engine-integration-IMPLEMENTATION
type: design
version: 1.3
status: draft
date: 2026-11-23
depends: [p006-tradability-engine-integration-DESIGN, p006-tradability-engine-integration-RESEARCH]
upstream: null
---

> **Feature**: P-006 —— `tradability` 接入 `FactorBacktestEngine`，并入 P-007 限价取整口径
> **创建日期**: 2026-11-23
> **状态**: draft（Step 5-6 完成；v1.1 = Step 6 异构复审 PASS_WITH_FIXES 已处置：2×P2 + 5×P3，记录见 §14；v1.2 = Step 8 文档一致性复审涉本文件项已处置（P3-2/3/4/5 + D-6-4 来源），记录见 [DESIGN.md §15](./DESIGN.md)；v1.3 = Step 9 TDD 红→绿实施完成，记录见 §15）
> **Spec 步骤**: Step 5-6；Step 8 处置（v1.2）；Step 9 实施（v1.3）
> **基于设计**: [DESIGN.md](./DESIGN.md) **v1.3**（Step 4 复审处置 + Step 5/6 勘误 6 处 + Step 8 复审勘误均已吸收）
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.4**（Step 2 引用复核 PASS）
> **档位**: **T1** ｜ **包版本**: 3.9.8 → **3.9.9** ｜ **新依赖**: 无（numpy / pandas / pytest 均为现有依赖）

---

## 1. 实施概述

本实施分 6 步（第 1-5 步为改动项，第 6 步为全量回归，见 §10）、触及 2 个既有源文件 + 1 个新增模块 + 3 个测试文件 + CHANGELOG：

1. **`backtest/tradability.py`**（改）：新增 `board_of`、`compute_limits`、`TradabilityInputs`；`limit_price` 重写为整数分 half-up（三分支 + NaN 掩码）；`apply_tradability` 追加 `adj/is_delisting/no_limit/ref` 可选参数、2D `is_st`、`pct` 状态缓存、9 键报告与单桶优先级。
2. **`backtest/tradability_inputs.py`**（新增）：`build_tradability_inputs` 把 pandas 面板派生为 `TradabilityInputs` + meta（板块/ST/退市/无限制日/adj 覆盖/一字板计数/校准状态）。
3. **`backtest/engine.py`**（改）：`__init__` 增 `tradability_inputs=None`；`_evaluate_factor` 在 `_build_positions` 后对**多头腿**调用 `apply_tradability`，换手用有效权重；仅在启用时追加 `results[factor]['tradability']`。
4. **测试**：`tests/test_tradability.py`（TP6-1/2/3/5/6/8/12）、`tests/test_tradability_inputs.py`（新增，TP6-4/7 构建器侧/TP6-8 派生侧）、`tests/test_backtest/test_engine.py`（TP6-9~11）。
5. **版本 3.9.9** 落 7 处 + CHANGELOG。
6. **全量回归**：`pytest -q` 零失败 + 默认基线逐位一致（§10 Step 6）。

全程不触碰 `factor_metrics.py`、`data_bridge.py`、`panels.py`、`verify_long_side_research.py`。

## 2. 工程细节

### 2.1 技术栈

| 组件 | 技术 | 版本 | 验证状态 |
|---|---|---|---|
| 语言 | Python | 3.9+（`requires-python >=3.9`） | ✅ 仓内现有约束 |
| 数值 | numpy | 现有锁定版本（`isfinite` / `broadcast_arrays` / `floor`） | ✅ 现有依赖 |
| 面板 | pandas | 现有锁定版本（`DataFrame.apply` / `reindex` / `fillna`） | ✅ `data_bridge.py` 已在用 |
| 测试 | pytest | 现有版本（`approx` / `parametrize`） | ✅ `tests/test_tradability.py` 已在用 |
| 新增依赖 | **无** | — | ✅ |

### 2.2 依赖版本验证

| 依赖 | 声明版本 | 使用 API | 兼容性 | 验证方式 |
|---|---|---|---|---|
| numpy | 现有锁定 | `np.isfinite` / `np.floor` / `np.broadcast_arrays` / `np.where` / `np.asarray` | ✅ | 仓内既有调用（`tradability.py` / `factor_metrics.py`） |
| pandas | 现有锁定 | `DataFrame.reindex` / `apply` / `fillna` / `eq` | ✅ | `data_bridge.py` L176-L181 既有同构用法 |
| pytest | 现有锁定 | `approx` / `parametrize` / `raises` | ✅ | `tests/test_tradability.py` L94-L100 |

**无新增第三方依赖**，不涉及 PyPI 版本核对；`decimal` 仅测试侧使用（stdlib）。

### 2.3 文件结构（改动面）

```
backtest/
├── tradability.py            # 改：board_of / compute_limits / TradabilityInputs /
│                             #     limit_price 重写 / apply_tradability 扩展 / 报告 9 键
├── tradability_inputs.py     # 新增：build_tradability_inputs（pandas → 数组 + meta）
└── engine.py                 # 改：__init__ 增参 + _evaluate_factor 多头腿分支
tests/
├── test_tradability.py       # 增：TP6-1/2/3/5/6/8/12（含 apply 侧 TP6-7/8）
├── test_tradability_inputs.py# 新增：TP6-4/7 构建器侧、TP6-8 派生侧 + meta 断言
└── test_backtest/test_engine.py
                              # 增：TP6-9~11（启用/空头腿/默认基线）
CHANGELOG.md                  # 增：3.9.9 条目
```

### 2.4 算法与源码级证据锚点（2026-11-23 实际抓取）

> 验证方式：规则条款用官方页/PDF 原文（RESEARCH §5.4 已签字）；源码用 GitHub raw 抓取；API 文档用官方页抓取；社区案例用页面直读。全部为本次实际抓取，非记忆引用。

| # | 层级 | 锚点（原文要点） | 对应实施 | 状态 |
|---|---|---|---|---|
| E1 | 规则·算法 | 上交所 2026 规则 3.3.17 / 深交所 2026 规则 3.3.19：涨跌幅限制价格**四舍五入**至申报价格最小变动单位；差额 <1 档按前收 ±1 档；限价 <1 档取 1 档 | `limit_price` 三分支 + `_to_cents` half-up | ✅ 正文逐字（RESEARCH §5.4） |
| E2 | 源码·数值 | NumPy `numpy.round` 文档原文：**"For values exactly halfway between rounded decimal values, NumPy rounds to the nearest even value"**；且 **"np.round uses a fast but sometimes inexact algorithm"**，文档示例 `np.round(16.055, 2), round(16.055, 2)` → **`(16.06, 16.05)`**（np.round 的快速缩放算法对该 IEEE 值产生偏差，Python `round` 更精确） | 禁用 `np.round`；整数分 `(pc×(10000±bp)+5000)//10000` | ✅ numpy 2.1 官方文档抓取；示例方向按原文复核（Step 6 P2-1 订正） |
| E3 | 源码·算法 | Zipline-reloaded `finance/execution.py::asymmetric_round_price` 注释原文：**"relies on rounding half away from zero, unlike numpy's bankers' rounding"**；实现走 `consistent_round` 而非 `np.round` | half-up（正数远离零）；与 E2 互相印证 | ✅ GitHub raw 抓取（main） |
| E4 | 源码·判定 | RQAlpha `rqalpha/utils/price_limits.py`：`PRICE_LIMIT_TOLERANCE = 1e-6`；`reaches_limit_up` 返回 `price >= limit_up - tick_size + PRICE_LIMIT_TOLERANCE`；并提供 `reaches_limit_up_vectorized` 的 Series 向量化版本 | `compute_limits` 的比较方向与 `policy.eps=1e-8`（仅浮点补偿）；向量化实现形态 | ✅ GitHub raw 抓取（master） |
| E5 | 源码·对照 | Qlib `qlib/backtest/exchange.py::Exchange._update_limit` 原文：`LT_FLT = "float"  # the trading limitation is based on abs($change) < limit_threshold`；`limit_buy = $change.ge(limit_threshold) | suspended` | 否决 C（启发式）；仅作回退对照，不进门禁 | ✅ GitHub raw 抓取（main）；文档默认 0.095 |
| E6 | 厂商文档·复权 | Tushare `pro_bar` 复权说明：**前复权 = 当日收盘价 × 当日复权因子 / 最新复权因子；后复权 = 当日收盘价 × 当日复权因子** | `ref = prev_raw × adj[t−1]/adj[t]` 的代数依据（hfq 连续） | ✅ tushare.pro doc_id=146 抓取 |
| E7 | 官方·代码段 | 深交所《证券代码区间表（2025 年 12 月修订）》：`0 0 0` 主板 A 股；`0 0 1` 主板存托凭证/主板 A 股（001001-001199 存托凭证）；`0 0 2-4` 主板 A 股；`3 0 0-9` **创业板股票/创业板存托凭证**（300000-309799 股票、309800-309999 存托凭证） | `board_of` 采用**区间**映射：main=000–004、gem=300–309（而非仅 300/301/302） | ✅ SZSE 官方 PDF 抓取 |
| E8 | 官方·切换日 | 中航成飞（原中航电测）公告：证券代码 **300114 → 302132**，启用日 **2025-02-17**，且**"启用当日股票交易设置涨跌幅限制"**；T 日市值按旧码 T−1 收盘价计算 | 302 归 gem；板块/代码切换日照常判定，不得误当"无涨跌幅限制日" | ✅ SZSE 巨潮 PDF 抓取 |
| E9 | 官方·CDR | 上交所公司概况页 689009：**"种类：科创板CDR"**，上市日 2020-10-29 | `board_of('689009') == 'star'` | ✅ 上交所页面抓取 |
| E10 | 官方媒体·代码段 | 新华网/央视：北交所 277 只股票全面启用 **920** 开头代码；此前部分存量沿用新三板时期 **43、83、87** 老代码 | `board_of` 的 bse 前缀 43/83/87/92 | ✅ 新华网 2025 报道抓取 |
| E11 | 官方文档·舍入模式 | Python `decimal` 文档：默认上下文 `Context(prec=28, rounding=ROUND_HALF_EVEN, ...)`（逐字）；同页 Rounding modes 列出 `ROUND_HALF_UP` | 测试基准用 `Decimal(str(x)).quantize(..., ROUND_HALF_UP)`；生产用整数分等价实现 | ✅ 默认上下文逐字抓取；`ROUND_HALF_UP` 语义由 E3/E12 交叉支撑（模式表未逐字摘录） |
| E12 | 社区·正例 | 迪雅数据长文：`round(yesterday_close * (1 + limit), 2)` 是银行家舍入，**精确实现应改用 `Decimal` 的 `ROUND_HALF_UP`**；并给出 `10.25×1.1=11.275 → 11.28` tie 例 | TP6-1/TP6-2 的用例来源；D2 裁决的社区佐证 | ✅ 页面全文抓取（C1） |
| E13 | 社区·**反例** | 火山引擎开发者社区《如何正确使用 A 股实时行情 API》：其代码注释写 **"交易所规则：涨停价向下取整到分，跌停价向上取整到分"**，实现为 `math.floor(...)/math.ceil(...)` | **不得采信**：与 E1 明文"四舍五入"冲突；作为社区分歧证据，说明必须有规则原文 + 定向用例，不能抄社区实现 | ✅ 页面直抓（2026-06-19） |
| E14 | 厂商文档·可成交性 | 聚宽 API：涨停/跌停时对应买单/卖单**不成交**，市价单取消、限价单挂单；米筐：单边市买卖单**无法成交**，尽管 bar 成交量非 0 | `can_trade` 的语义边界；`blocked_*` 只表达"价格不可成交" | ✅ RESEARCH §5.4 D5/D6 已逐字签字 |

**核验纠错记录（幻觉抑制实例）**：
- 初拟 `board_of` 仅列 `300/301/302`；抓取 E7 后发现深交所区间表把 **300–309 全部**划归创业板（含 3098–3099 存托凭证），故实施采用区间而非枚举（D-6-4）。
- 初拟把 E13 当"社区实现参考"；逐字读后发现其 `floor/ceil` 与 E1 相反，改登记为**反例**，并据此在 TP6-3 增加边界对照。

**算法对照（实现动作 ↔ 锚点）**：

| 实现动作 | 算法 | 锚点 |
|---|---|---|
| `_to_cents(x) = floor(x*100 + 0.5)` | 两位小数 → 整数分，half-up | E1 + E11 |
| `lc = (pc*(10000±bp) + 5000)//10000` | 整数分 half-up，无浮点乘 | E1 + E2 |
| `where(abs(lc-pc) < 1, pc ± 1, lc)` | 差额 <1 档分支 | E1 |
| `where(lc < 1, 1, lc)` | 限价 <1 档分支 | E1 |
| `high >= up - eps` / `low <= down + eps` | 封板判定（eps 仅浮点补偿） | E4 + E14 |
| `ref = prev * adj[t-1] / adj[t]` | 除权参考价 | E6 + RESEARCH S1 4.3.2 |
| `board_of` 区间映射 | 板块归属 | E7/E8/E9/E10 |

### 2.5 社区案例对照与采信裁决

> 同一问题在外部社区存在**相互冲突**的实现；本节逐条与规则原文对照后给出采信裁决，防止"抄社区代码"替代规则取证。

| 案例 | 主张/实现 | 与规则原文对照 | 裁决 |
|---|---|---|---|
| 迪雅数据（E12） | Python `round` 是银行家舍入，应用 `Decimal(ROUND_HALF_UP)` | 与 E1 "四舍五入"一致 | **采信为工程建议**，不作规则源；进入 TP6-2 基准 |
| 火山引擎社区（E13） | 注释称"涨停向下取整、跌停向上取整"，用 `math.floor/math.ceil` | 与 E1 "四舍五入"**冲突** | **不采信**；登记为反例，说明社区实现不能作依据 |
| RQAlpha（E4） | `price >= limit_up - tick_size + 1e-6` | 1 档容差是浮点比较补偿，非业务容差 | **采信为容差边界**；本实现 `eps=1e-8` 仅吸收二进制误差 |
| Qlib（E5） | `$change >= limit_threshold`（0.095） | 启发式阈值，非交易所限价 | **仅作回退对照**，不进门禁 |
| 聚宽/米筐（E14） | 涨跌停时买单/卖单不成交、市价取消/挂单 | 与厂商回测语义一致 | **采信为语义边界**；`blocked_*` 只表达价格不可成交 |

## 3. 模块实施

### 3.1 `backtest/tradability.py`

#### 职责

规则表、板块映射、限价计算、可交易性推进（DESIGN §3.2）。顶层依赖保持 `stdlib + numpy`，无 pandas / 无 IO。

#### 实施要点

1. **`board_of(code)`**（新增，DESIGN §4.1 + D-6-4）：
   - 归一化：`str(code).split('.')[0].zfill(6)`；非 6 位数字 → `unknown`。
   - 区间映射：`600/601/603/605 → main`；`000-004 → main`；`300-309 → gem`；`688/689 → star`；`43/83/87/92 → bse`；其余 `unknown`。
   - 返回 `unknown` 不抛错；**禁止**默认 `main`（INV-3）。
2. **`_to_cents(x)`**（内部）：
   - 先 `valid = np.isfinite(x)`，只在 valid 子集上 `np.floor(x*100 + 0.5)` 转 `int64`；无效位置最后回填 NaN。
   - 禁止 `np.rint(NaN)` / `int(NaN)`（P1-1 教训）。
3. **`limit_price(prev_close, pct, side="up")`**（重写，签名不变）：
   - 广播 `prev_close`/`pct`；`valid = isfinite(prev) & isfinite(pct) & (pct >= 0) & (pct <= 1)`，越界 `ValueError`。
   - `bp = floor(pct*10000 + 0.5)`；`scale = 10000 ± bp`；`lc = (pc*scale + 5000)//10000`。
   - 分支 ① `abs(lc-pc) < 1 → pc ± 1`；② `lc < 1 → 1`；③ 其余。
   - 标量入参返回 `float`，数组入参返回同形状 `ndarray`；`side` 非法 `ValueError`。
4. **`compute_limits(prev_close, pct, ref=None, is_st=None, low_price_st_rule=True)`**（新增）：
   - `basis = ref if ref is not None else prev_close`；`unknown = ~isfinite(prev) | ~isfinite(pct) | (ref 提供但 ~isfinite(ref)) | (prev <= 0) | (ref 提供且 ref <= 0)`。
   - `up/down = limit_price(basis, pct, "up"/"down")`。
   - 低价 ST：`is_st & (prev_cents < 10)` → `up = prev_cents + 1`、`down = max(prev_cents - 1, 1)`（用 **原始 prev** 判 0.1 元门槛，不用 ref；与 E1 分支①等价，见 TP6-12）。
   - 返回 `(up, down, unknown)`；未知板块由调用方在 `pct` 缺失/`board` 掩码中并入 `unknown`。
5. **`TradabilityInputs`**（新增 frozen dataclass，DESIGN §4.5）：字段与默认值照 DESIGN；`eq=False`（ndarray 字段不可做 `==`/hash）；不含方法。
6. **`_pct_matrix(board, is_st, is_delisting, dates)`**（内部，D-6-6）：
   - `is_st` 支持 `(N,)` / `(T,N)`；`is_delisting=None` 视为全 False；`eff_st = is_st & ~is_delisting`（退市优先，D6）。
   - 状态编码 `state = board_code*2 + eff_st`；每日对出现的状态值最多 10 次 `rule_pct`；`unknown` 状态不查表，直接留给 `unknown` 掩码。
   - 返回 `pct(T,N)`（unknown 位置 NaN）。
7. **`apply_tradability(...)` 扩展**（DESIGN §4.4）：
   - 新 kwargs 追加在 `policy` 之后：`adj=None, is_delisting=None, no_limit=None, ref=None`；位置调用完全兼容。
   - `ref` 优先于 `adj`；仅当 `adj` 给出且 `ref is None` 时，**先做缺失前置**：`adj[t]` 或 `adj[t-1]` 任一非有限/非正 → `ref = NaN`（→ unknown，不回退 prev，D-6-7/DESIGN §4.3）；再判除权日（`abs(adj[t]/adj[t-1]-1) > 1e-6`）：是则 `ref = _to_cents(prev * adj[t-1]/adj[t])`，否则 `ref = prev`（D-6-2，避免浮点漂移改判）。`t=0` 无 `adj[t-1]` → `ref` 保持 NaN → unknown；`prev<=0` / `ref<=0` → unknown（D-6-12）。**ref 对齐披露（D-6-17）**：`_to_cents` 是 float 意义下的 half-up 近似——数学值恰为 x.xx5 的构造输入可能偏 ±1 分（Step 6 实测 8,941 个精确 tie 构造中 22.7% 向下偏）；真实 hfq 比率命中概率≈0，登记为已知残余，不构造测试固化。
   - 每日：`up, down, unk = compute_limits(...)`；`judge = ~unk & ~no_limit[t]`（`no_limit=None` 视为全 False）；`can_buy = ~susp & (~judge | ~(high >= up - eps))`；`can_sell` 镜像。
   - 桶优先级（D-6-1/INV-5）：`blocked_suspend = busy & susp`；`limit_unknown = busy & ~susp & ~no_limit[t] & unk`（**不是** `~judge`，否则 `no_limit` 格会被误计）；`blocked_buy = buy & ~can_buy & ~susp & judge`；`blocked_sell` 同；`t1_mask` 从 `blocked_sell` 扣除。
   - 一字板：`one_word_up += count(judge & ~susp & (high == low) & (abs(high-up) <= eps))`，跌停镜像（D-6-5）。
   - 报告恒 9 键、值均为 `int`（INV-9）；`pending`/`carried` 逻辑不变。
8. **`can_trade`**（保持 2 元组）：内部改走 `compute_limits`；`pct` 标量/数组均可；不返回 unknown（unknown 由 `apply_tradability` 统计），避免破坏既有调用。

#### 低效操作排除

| 潜在低效 | 排除措施 |
|---|---|
| 每日 `N` 次 `rule_pct` | 状态缓存，每日 ≤10 次查表 |
| 每格 Python 循环 | `limit_price`/`compute_limits` 全向量化；仅时间维 `T` 循环（与现实现一致） |
| 大数组重复分配 | `ref`/`pct`/`no_limit` 预分配一次；`apply` 内只做布尔组合 |
| 字符串状态键 | 用整数 `state` 编码，避免 `T×N` 字符串拼接 |

### 3.2 `backtest/tradability_inputs.py`（新增）

#### 职责

pandas 面板 → `TradabilityInputs` + meta（DESIGN §4.6）；纯函数、无 IO。

#### 实施要点

1. **对齐**：以 `close.index/columns` 为唯一网格；其余面板 `reindex(index=..., columns=...)`；缺失填 NaN/False。
2. **板块**：对列代码逐个 `board_of`（N 次，一次性），`meta["board_counts"]` 用 `collections.Counter`，`unknown_codes` 截前 20。
3. **ST/退市**：`name.fillna("")` 后按列 `str.contains("ST", regex=False)` / `str.contains("退", regex=False)`；`is_st`/`is_delisting` 为 `(T,N) bool`。
4. **无限制日**：
   - `list_date` 有效时：自该日起的前 5 个交易日（**含上市首日**）置 `no_limit=True`；缺失的股票不臆造上市日。
   - 每只股票的 `is_delisting` 首次为真日置 `no_limit=True`（退市整理首日）。
   - 最后 `no_limit &= ~suspended`；`meta["no_limit_source"] = "list_date" | "delisting_only"`（DESIGN P2-4）。
5. **adj**：`adj`（`(T,N)` float）为必填；`None` → `ValueError`。原样透传；`meta["adj_missing_days"]` = 存在任一列非有限/非正的**日期数**。
6. **一字板**：用 `compute_limits` 全表向量化算 `up/down/unknown`，统计 `high==low` 且 `abs(high-up) <= eps`（与 apply 侧同一表达式，Step 6 P3-5 统一口径），judgeable 且非停牌；写入 `meta["one_word_up_cells"]` / `["one_word_down_cells"]`。
7. **校准状态**：可选 `st_overrides=None`（D-6-3）：提供 DataFrame `[code, effective_date]` 时，逐行与名称派生首个 ST 日比对，`st_date_unverified` 计不一致数，`st_calibration_source="coverage_table"`；未提供则 `0` + `"none"`。
8. **rounding_basis**：`"inferred_half_up"`（存在 bse）否则 `"exchange_half_up"`；`price_basis="raw_adj_ref"`。
9. 返回 `(TradabilityInputs, meta)`；引擎只读回显 meta，不修改。

### 3.3 `backtest/engine.py`

#### 职责

opt-in 接入、多头腿判定、报告挂载（DESIGN §3.4/§4.7）。

#### 实施要点

1. `__init__(self, data_loader, config=None, fwd_returns=None, tradability_inputs=None)`：
   - `None` → 旧路径，零额外属性访问（INV-1）。
   - 非 `None` → `_validate_tradability_inputs`：`(T,N)` 与 `n_dates/n_stocks` 一致、`dates` 长度、`board` 允许值、`adj is not None`（DESIGN §7）。
2. `_evaluate_factor`：
   - `positions = self._build_positions(factor)`（不变）。
   - `None` → `turnover = compute_turnover(positions)`，结果键集合与 v3.9.8 完全一致。
   - 启用：
     ```python
     long_target = np.clip(positions, 0.0, None)
     eff_long, report = apply_tradability(
         long_target, _shift(inputs.close), inputs.high, inputs.low,
         inputs.close, inputs.open_, inputs.volume, inputs.suspended,
         inputs.board, inputs.is_st, inputs.dates,
         policy=inputs.policy, adj=inputs.adj,
         is_delisting=inputs.is_delisting, no_limit=inputs.no_limit)
     effective = eff_long + np.minimum(positions, 0.0)
     turnover = compute_turnover(effective)
     ```
   - `results[factor]['tradability'] = {"report": report, "meta": inputs.meta,
     "price_basis": "raw_adj_ref", "leg_scope": "long_only",
     "short_leg_unmodeled": True, "turnover_basis": "effective_long_only"}`。
3. **不改** IC/ICIR/Decay/HitRate/Spread/LS 收益的输入与顺序；`summary()`/`rank_by_icir()` 不消费新键。
4. `_shift(close)`：`prev = np.full_like(close, np.nan); prev[1:] = close[:-1]`（t=0 → NaN → unknown）。

### 3.4 测试文件

| 文件 | 新增内容 | 覆盖 |
|---|---|---|
| `tests/test_tradability.py` | TP6-1/2/3/5/6/8/12（TP6-8 apply 侧行为）+ 报告 9 键 | 限价算法与权重推进 |
| `tests/test_tradability_inputs.py`（新增） | TP6-4/7（构建器侧 meta）/TP6-8（派生侧） | 板块/ST/退市/无限制日/adj |
| `tests/test_backtest/test_engine.py` | TP6-9/10/11 | 引擎接入、空头腿、默认基线 |

TP6-7 为两半用例（Step 6 P2-2）：构建器侧断言 `meta["adj_missing_days"]` 对**单侧缺失**（`adj[t]`/`adj[t-1]` 恰一个 NaN）计数 >0；apply 侧断言 `report["limit_unknown"] > 0` 且 `blocked_*` 不增加——显式构造单侧缺失，防止被 t=0/双侧缺失兜住漏检。TP6-5 归 `board_of` 纯函数（tradability.py 侧）。

Step 9 落地补充：`test_engine.py` 原模块级 `pytest.importorskip("Factor_Trading_v3_0")` 改为按类 `@unittest.skipUnless`（5 个 DataBridge 测试类跳过），使 TP6-9~11 使用 `_FakeDL` 在不装外部包的环境也始终运行；`test_tradability.py` 共 21 项（T390 9 + TP6 12）、`test_tradability_inputs.py` 10 项。

### 3.5 版本与 CHANGELOG

包版本 **3.9.8 → 3.9.9**，7 个落点（DESIGN §10.1-8）：`pyproject.toml:7`、`__init__.py:58`、`config_v2.py:371`、`reporting.py:40`、`tests/test_fix3_version_unification.py:34`、`tests/test_backtest/verify_fix3_manual.py:21`、`CHANGELOG.md` 顶部。

## 4. 接口实施

### 4.1 `board_of`

```python
def board_of(code) -> str:
    """归一化后按区间映射：main / gem / star / bse / unknown。"""
    code6 = str(code).split(".")[0].zfill(6)
    if len(code6) != 6 or not code6.isdigit():
        return "unknown"
    if code6[:3] in ("600", "601", "603", "605") or "000" <= code6[:3] <= "004":
        return "main"
    if "300" <= code6[:3] <= "309":
        return "gem"
    if code6[:3] in ("688", "689"):
        return "star"
    if code6[:2] in ("43", "83", "87", "92"):
        return "bse"
    return "unknown"
```

**签名一致性**：与 DESIGN §4.1 一致；映射范围按 D-6-4 扩为官方区间 ✅

### 4.2 `limit_price`

```python
def limit_price(prev_close, pct, side="up"):
    """整数分 ROUND_HALF_UP；返回标量或同形状数组；NaN → NaN。"""
    # 1) broadcast + valid 掩码；2) _to_cents；3) bp=round(pct*1e4)；
    # 4) lc=(pc*(10000±bp)+5000)//10000；5) 三分支；6) 复原形状/NaN
```

**签名一致性**：与 DESIGN §4.2 一致（签名不变） ✅

### 4.3 `compute_limits` / `apply_tradability`

```python
def compute_limits(prev_close, pct, ref=None, is_st=None, low_price_st_rule=True):
    """返回 (up, down, unknown)。"""

def apply_tradability(target_w, prev_close, high, low, close, open_, volume,
                      suspended, board, is_st, dates, policy=None,
                      adj=None, is_delisting=None, no_limit=None, ref=None):
    """返回 (effective_w, report)；report 9 键。"""
```

**签名一致性**：与 DESIGN §4.3/§4.4 一致；新参数均追加在 `policy` 后 ✅

### 4.4 `TradabilityInputs` / `build_tradability_inputs`

```python
@dataclass(frozen=True, eq=False)
class TradabilityInputs:
    close; high; low; open_; volume; suspended; dates; board; is_st; adj
    is_delisting=None; no_limit=None; policy=None; meta=None

def build_tradability_inputs(close, high, low, open_, volume, suspend, name,
                             adj, list_date=None, policy=None, st_overrides=None):
    """返回 (TradabilityInputs, meta)。"""
```

**签名一致性**：与 DESIGN §4.5/§4.6 一致；`st_overrides` 为 D-6-3 的 R-6 钩子 ✅

### 4.5 引擎

```python
FactorBacktestEngine(dl, config=None, fwd_returns=None, tradability_inputs=None)
```

**签名一致性**：与 DESIGN §4.7 一致 ✅

## 5. 兼容性

### 5.1 Python 版本兼容

| Python 版本 | 支持 | 说明 |
|---|---|---|
| 3.9 | ✅ | `requires-python >=3.9`；frozen dataclass / `np.broadcast_arrays` 均可用；不使用 3.10+ 语法 |
| 3.10–3.13 | ⚠️ | 语法兼容；Step 9 仅在当前解释器实测，未逐一跑矩阵 |

### 5.2 依赖兼容

| 依赖组合 | 兼容性 | 验证 |
|---|---|---|
| numpy 1.x / 2.x + pandas 1.5+ / 2.x | ⚠️ | 仅用稳定 API（无 `np.float_` 等 2.0 移除项）；以仓内锁定组合为准，未做版本矩阵 |
| `decimal`（测试侧） | ✅ | stdlib，3.9 起 `ROUND_HALF_UP` 稳定 |

### 5.3 向后兼容

1. `apply_tradability` 的位置参数顺序不变，新参数全部 keyword-only 语义（追加在 `policy` 后）；现有 `tests/test_tradability.py` 调用无需改。
2. 报告键 6→9：现有测试无键数断言；直接调用方若做 `len(report)` 会感知变化——已在 DESIGN §14 P2-2 登记为有意变更。
3. 引擎 `results[factor]` 未启用时零新增键（INV-1）；启用时 `summary()` 忽略新键。
4. `limit_price` 的数值结果对非 tie 用例与旧 `np.round` 一致；tie 用例按规则修正（P-007 的目的）。

## 6. 错误处理实施

| 错误场景（DESIGN §7） | 异常类型 | 处理代码 | 测试 |
|---|---|---|---|
| 数组形状不符 `(T,N)` | `ValueError` | `_validate_tradability_inputs`：逐字段检查 | TP6-9 子断言（D-6-14） |
| `dates` 长度 ≠ T | `ValueError` | 同上 | TP6-9 |
| `board` 未知值 | 不抛错 | `board_of` 返回 `unknown`；`pct` NaN → `unknown` 桶 | TP6-5/7 |
| 已映射板块规则无命中 | `ValueError` | `rule_pct` 原逻辑 | 沿用 T390-35 |
| `adj` 缺失/非正/单侧缺失 | 不抛错 | `unknown` 掩码；`limit_unknown` 计数 | TP6-7 |
| `prev_close` NaN（含 t=0） | 不抛错 | `unknown`；停牌优先 | TP6-7 |
| `high/low` NaN | 不抛错 | NaN 比较为 False → 无封板证据（不 block、一字板不计），隐式覆盖于 §3.1-7 表达式 | CHECKLIST §5 负例（Step 9 合成盘执行；Step 8 P3-3 补行） |
| 引擎启用但 `adj is None` | `ValueError` | `_validate_tradability_inputs` | TP6-9 |
| `side` 非法 / `pct` 越界 | `ValueError` | `limit_price` 入口 | TP6-3（side）/ TP6-2（pct） |
| `np.round` 残留 | 测试失败 | `grep` 断言 | TP6-2 附静态检查 |

## 7. 不变式实施

| 不变式（DESIGN §8） | 实施位置 | 验证方式 |
|---|---|---|
| INV-1 默认零变更 | `engine.py::_evaluate_factor` 的 `is None` 分支 | TP6-11 基线字面量逐位 |
| INV-2 整数分 half-up | `tradability.py::_to_cents` / `limit_price` | TP6-1/2 + `grep np.round` |
| INV-3 未知不默认 | `board_of` + `_pct_matrix` 的 unknown 状态 | TP6-5/7 |
| INV-4 除权基准 | `compute_limits` 的 `ref` 优先级 | TP6-6/7 |
| INV-5 计数互斥 | `apply_tradability` 桶优先级 | TP6-7 + 组合负例 |
| INV-6 ST/退分治 | `board_of` + `_pct_matrix` 的 `is_delisting` | TP6-8 |
| INV-7 空头腿不动 | `engine.py` 的 `np.minimum(positions, 0)` | TP6-10 |
| INV-8 规则表不变 | `DEFAULT_LIMIT_RULES` 不改 | T390-31/35 回归 |
| INV-9 报告类型 | `report` 初始化 9 键 `int` | CHECKLIST §2.2「报告恒 9 键且值均为 int」断言（apply 侧；Step 8 P3-4 订正） |

## 8. 测试策略

### 8.1 单元测试

| 模块 | 测试文件 | 用例 | 覆盖目标 |
|---|---|---|---|
| `tradability.py` | `tests/test_tradability.py` | TP6-1/2/3/5/6/8/12 + T390-27~35 回归 | 核心函数分支全覆盖（无覆盖率工具门禁） |
| `tradability_inputs.py` | `tests/test_tradability_inputs.py` | TP6-4/7（meta 侧）/TP6-8（派生侧） | 派生规则全分支 |
| `engine.py` | `tests/test_backtest/test_engine.py` | TP6-9/10/11 | 分支覆盖（启用/未启用） |

### 8.2 集成测试

- 合成盘（`tests/synthetic/panel.py` 现成）构造 3 日 × 2 股：涨停日 blocked、跌停日 blocked、停牌日 freeze；断言 `turnover` 与未启用不同且 `tradability.report` 计数正确。
- 默认路径：同一合成盘在未启用时与基线字面量（Step 9 改动前采集）逐位一致。

### 8.3 属性测试

- TP6-2：价格由整数分生成（`cents/100`，`cents ∈ [1, 100000]`）× `{0.05,0.10,0.20,0.30}` × `{up,down}`，与 `Decimal(str(price))` 的 `quantize(Decimal("0.01"), ROUND_HALF_UP)` 逐值相等，样本 ≥ 10,000，不一致数必须为 0。
- TP6-12：`prev_cents ∈ [1,9]`、ST 5% 全扫描，显式低价分支与通用三分支逐值相等。

### 8.4 回归与门禁

- 全量 `pytest`：既有 `T390-27~35` 全部保持通过；新增用例全绿。
- 默认路径 SHA/逐位：`FactorBacktestEngine` 合成盘 `summary()` + `turnover` 与基线一致。
- 不运行 `verify_long_side_research.py`（其 0.3 路径属诊断，不在本批门禁）。

## 9. 幻觉抑制审查（Step 6 Review）

### 9.1 依赖版本验证

- [x] 无新增第三方依赖；numpy/pandas/pytest 均为仓内现有依赖
- [x] 未引用虚构库或函数（`decimal` 为标准库）
- [x] Python 3.9 下限 API 可用（frozen dataclass / `broadcast_arrays` / `ROUND_HALF_UP`）

### 9.2 接口签名验证

- [x] `board_of` / `limit_price` / `compute_limits` / `apply_tradability` / `TradabilityInputs` / `build_tradability_inputs` / 引擎构造与 DESIGN §4 一致
- [x] `apply_tradability` 新参数追加在 `policy` 后，位置调用兼容
- [x] 标量/数组返回形态、`(N,)`/`(T,N)` `is_st` 双形态可实现

### 9.3 实施与设计对齐

- [x] 3 个模块对应 DESIGN §3.2 的 3 行（tradability / inputs / engine）
- [x] 每个接口对应 DESIGN §4.1~§4.7
- [x] 无设计未覆盖的实施（D-6-1~D-6-10 均登记为派生需求）

### 9.4 低效操作排除

- [x] `pct` 状态缓存（每日 ≤10 次查表），无 `T×N` Python 循环
- [x] 无 IO；构建器只做一次 reindex/映射
- [x] 无重复计算：`compute_limits` 全表算一次供一字板统计，`apply` 内按日复用

> **Step 6 独立复审待执行**：本节为作者自检，不作为 Review 结论。

## 10. 实施步骤

### Step 1：算法层（`tradability.py` 上半）

- 文件：`backtest/tradability.py`
- 内容：`board_of`、`_to_cents`、`limit_price` 重写、`compute_limits`、`TradabilityInputs`。
- 测试：TP6-1/2/3/5/6/12；既有 T390-32 仍绿。（Step 8 P3-2：TP6-6 归 Step 1，与 §3.4/CHECKLIST §2.1 一致）

### Step 2：推进层（`tradability.py` 下半）

- 文件：`backtest/tradability.py`
- 内容：`_pct_matrix`、`apply_tradability` 扩展、9 键报告、桶优先级。
- 测试：TP6-7（apply 侧 report 断言，含单侧缺失）/8/12；T390-27~31/34/35 回归。（Step 8 P3-2：TP6-6 移出本步）

### Step 3：构建器

- 文件：`backtest/tradability_inputs.py`（新增）
- 内容：`build_tradability_inputs` + meta + `st_overrides` 钩子。
- 测试：`tests/test_tradability_inputs.py`（TP6-4/7 meta 侧——含**单侧缺失**构造、TP6-8 派生侧 + meta 键）。

### Step 4：引擎接入

- 文件：`backtest/engine.py`
- 内容：`__init__` 校验、`_evaluate_factor` 分支、`_shift`、结果挂载。
- 测试：TP6-9/10/11（先采集默认基线，再改代码）。

### Step 5：版本与 CHANGELOG

- 文件：7 个版本落点 + `CHANGELOG.md`
- 内容：3.9.9 条目（限价 half-up、opt-in 引擎接入、报告 9 键）。
- 测试：`tests/test_fix3_version_unification.py` / `verify_fix3_manual.py`。

### Step 6：全量回归

- 命令：`python -m pytest -q`
- 判据：0 failed；T390 全绿；TP6 全绿；默认基线逐位一致。

## 11. 派生需求登记（D-6-x）

| ID | 派生需求 | 来源 | 影响 |
|---|---|---|---|
| D-6-1 | `limit_unknown` 仅统计 **busy 且非停牌** 格；面板级缺失由 meta 披露 | DESIGN §6.1 的"格数"细化 | 避免把"整日 adj 缺失 × N"误当交易阻塞 |
| D-6-2 | `ref` 只在除权日重算（`|adj[t]/adj[t-1]−1|>1e-6`），非除权日 `ref=prev` | DESIGN §3.3-4 的"仅除权日不同" | 防止复权因子浮点噪声改判 1 分 |
| D-6-3 | 构建器增 `st_overrides=None`（`[code, effective_date]`） | DESIGN R-6 "公告覆盖表钩子" | 可复现 002122 偏差；未提供时 `source="none"` |
| D-6-4 | `board_of` 用区间映射：main=000–004、gem=300–309 | DESIGN §4.1（v1.3 勘误）+ E7 深交所代码区间表 | 覆盖 302/303/3098 等未来代码 |
| D-6-5 | 一字板只统计 judgeable 且非停牌格 | DESIGN R-3 "独立字段" | 避免未知/停牌污染诊断计数 |
| D-6-6 | `pct` 用整数状态缓存（≤10 查表/日） | DESIGN §10.1-3 | 4.5M 格面板可接受 |
| D-6-7 | `ref` 优先于 `adj`；`adj` 单侧缺失 → unknown | DESIGN §4.3 / P3-6 | 调用方可预计算参考价 |
| D-6-8 | `limit_price` 标量→float、数组→ndarray；`pct∉[0,1]` 抛错 | DESIGN §4.2 / §7 | 保持既有调用形态并防误用 |
| D-6-9 | 报告键 6→9 为有意变更；直接调用方若断言键数需同步 | DESIGN §14 P2-2 | 兼容性披露 |
| D-6-10 | 测试拆分为 3 文件（算法/构建器/引擎） | DESIGN §10.4 | 避免单文件过大、按层定位 |
| D-6-11 | `TradabilityInputs` 用 `@dataclass(frozen=True, eq=False)` | DESIGN §4.5 的可实现性细化 | 避免 ndarray 字段的 `==` 产生歧义数组 |
| D-6-12 | `prev<=0` / `ref<=0` / `t=0` 无 `adj[t-1]` → unknown | DESIGN §4.3 的 unknown 成因补全 | 防止非正价格算出 1 分限价 |
| D-6-13 | DESIGN v1.2 勘误：meta 补 `rounding_basis` | TP6-4 已要求该键，DESIGN §4.6 清单漏列 | 文档一致性；无行为变更 |
| D-6-14 | TP6-9 扩为 3 子断言：形状负例 / `adj=None` 负例 / 涨停拦截 | DESIGN §10.4 TP6-9 只写"涨停日" | 引擎构造契约与行为同测 |
| D-6-15 | TP6-2 增 `pct∉[0,1]` 负例 | DESIGN §4.2 v1.2 新增 `pct` 校验 | 防误用 |
| D-6-16 | `no_limit` 优先于 `limit_unknown`（IPO 日 adj 缺失不计 unknown） | DESIGN v1.2 §6.1 优先级链调整 | 避免无限制日误报不可判定 |
| D-6-17 | `ref` 对齐到分为 **float 意义近似**：数学值恰为 x.xx5 的构造输入可能偏 ±1 分（Step 6 实测 8,941 精确 tie 构造 22.7% 向下偏）；真实 hfq 比率命中概率≈0，登记已知残余，不构造测试 | DESIGN §4.3 "先按 half-up 对齐到分"的 float 语义限定 | 披露性登记；无测试负担 |

## 12. 性能预算

| 项 | 规模 | 预算 | 措施 |
|---|---|---|---|
| 面板 | T=787，N=5,688（窗口） | `apply_tradability` ≤ 2 s | `T` 循环 + 全向量化；状态缓存 |
| 内存 | 6 个 `(T,N)` float64 ≈ 216 MB | 只借用引用，不复制 | `TradabilityInputs` 持有原数组 |
| 构建器 | 5,688 列 × 787 日 | ≤ 5 s | 列级 `str.contains` + 一次 reindex |
| 引擎 | 每因子一次 `apply` | 相对 IC 计算可忽略 | 仅启用时执行 |

## 13. 风险与回滚

| 风险 | 缓解 | 回滚 |
|---|---|---|
| 整数分重写改变既有非 tie 结果 | TP6-2 属性测试 + T390-32 回归 | 单函数回退到旧实现（保留 tag） |
| 默认路径被误改 | INV-1 基线字面量 + `is None` 早分支 | `tradability_inputs=None` 即旧路径 |
| 构建器口径错误 | meta 全量披露 + TP6-4/5/7/8 | 不传构建器结果即不启用 |
| 空头腿语义争议 | `leg_scope="long_only"` + 文档边界 | 关闭 opt-in |

## 14. Step 6 异构复审记录（2026-11-23，独立子代理）

> **复审方式**：独立子代理以怀疑视角复审本文件 v1.0——E1 算术重放（`_to_cents` 10 万全扫描 + 96,000 组合 Decimal 对照 + 8,941 个精确 tie 构造扫描 + 低价 ST 全扫描 + 16 组合优先级链枚举，临时脚本置于 %TEMP%、用后删除、仓库零写入）+ 5 条锚点网络重抓 + 8 个仓内文件只读逐行核对。

> **总结论**：**PASS_WITH_FIXES** —— 2×P2 + 5×P3；核心算术、向后兼容、引擎接入路径、DESIGN v1.2 五处勘误吸收全部成立。已全部处置，版本升 v1.1。

**E1 重放对照表（全部 ✅ 除注明）**：

| # | 重放项 | 结果 |
|---|---|---|
| 1a | `_to_cents(cents/100)` c=1..100,000 全扫描 | 不一致 **0** |
| 1b | 陷阱值 8.35 / 0.07 / 19.99 / 2.675 / 16.055 / 9.225 | 全部落 half-up 正确侧 |
| 2a | 整数分公式 vs Decimal ROUND_HALF_UP，96,000 组合 | 不一致 **0**；tie 命中 5%:1132 / 10%:2398 / 20%:**0** / 30%:2398（20% 档 tie 恒 0 再证） |
| 2b | tie 定向四例 + `np.round(10.25×0.9)=9.22` | 逐值一致；翻转实锤 |
| 3 | ref tie 残留（8,941 精确 tie 构造） | **22.7% 向下偏 1 分** → P3-2 披露（D-6-17） |
| 4 | 低价 ST 等价性 c=1..9 分全扫描 | 0 违例 |
| 5 | 优先级链 16 组合枚举 | 与 DESIGN v1.2 链严格一致 |

**锚点抽查表**：NumPy round（两句原文逐字命中；16.055 示例方向文档原文 `(16.06, 16.05)` → P2-1 订正）；RQAlpha（`PRICE_LIMIT_TOLERANCE = 1e-6` 逐字 ✅）；Zipline（"unlike numpy's bankers' rounding" 逐字 ✅）；Qlib（语义一致 ✅）；689009（"科创板CDR" 命中 ✅）。

**问题处置表**：

| 编号 | 级别 | 问题摘要 | 处置 |
|---|---|---|---|
| P2-1 | P2 | E2 行 NumPy 16.055 示例数值方向写反（原文 `(16.06, 16.05)`） | **已修**：E2 行按原文更正并标注 Step 6 订正；"rounds to nearest even" 与翻转裁决不受影响 |
| P2-2 | P2 | adj 单侧缺失走"非除权日"分支 → `ref=prev` 静默回退，违反 DESIGN §4.3/§6.2/R-5 | **已修**：§3.1-7 除权判定前补显式缺失前置（任一非有限/非正 → ref=NaN → unknown）；TP6-7 定为两半用例并显式构造单侧缺失（§3.4/§8.1/§10 Step2/3 三处对齐） |
| P3-1 | P3 | 头部"基于设计 v1.1"未随 DESIGN v1.2 升版 | **已修**：头部改 v1.2 |
| P3-2 | P3 | "ref 对齐 half-up"在 float 路径不可严格满足（22.7% 构造偏差） | **已修**：§3.1-7 披露 + D-6-17 登记 + DESIGN §4.3 加 float 限定（真实 hfq 比率命中概率≈0） |
| P3-3 | P3 | TP6-5/TP6-7 测试归属三处不一致 | **已修**：TP6-5 归 tradability.py；TP6-7 拆构建器/apply 两半；§3.4/§8.1/§10 三处统一 |
| P3-4 | P3 | 概述"分 6 步"只列 5 项 | **已修**：列表补第 6 项（全量回归） |
| P3-5 | P3 | 一字板 meta 侧与 report 侧字面口径微差 | **已修**：§3.2-6 统一为 `high==low 且 abs(high-up)<=eps` |

**复审确认无问题的关键点**：Python 3.9 API 可用性（`frozen=True, eq=False`/`broadcast_arrays`/`zfill`）；向后兼容（现有测试无键数断言，T390-34 新语义下逐值保持）；引擎接入（`_build_positions` 恒无 NaN，INV-7 恒成立）；未启用分支键集合不变；版本 6 落点行号属实；D-6 互引一致；DESIGN v1.2 勘误 5 处全部吸收；R-1~R-6 全部有落点；内存预算算术合理。

复审后状态：**0×P1 / 0×未处置**，可进入 Step 7（CHECKLIST）。

## 15. Step 9 TDD 实施记录（2026-11-23）

> **红（旧实现 v3.9.8）**：`tests/test_tradability.py` 收集期 `ImportError: cannot import name 'board_of'`（`board_of`/`compute_limits`/`TradabilityInputs` 均缺）；`tests/test_tradability_inputs.py` `ModuleNotFoundError: No module named 'backtest.tradability_inputs'`；`tests/test_backtest/test_engine.py` 新用例 `TypeError: FactorBacktestEngine.__init__() got an unexpected keyword argument 'tradability_inputs'`。
>
> **绿（新实现）**：定向四文件 **44 passed / 20 skipped** —— `test_tradability.py` 21 passed、`test_tradability_inputs.py` 10 passed、`test_engine.py` 4 passed + 20 skipped（5 个 DataBridge 类，外部可选依赖未装）、`test_fix3_version_unification.py` 9 passed。
>
> **默认基线（改动前采集，TP6-11 锁定）**：`rank_icir=-0.25880207857362303`、`pearson_icir=-0.30599173567954446`、`hit_rate=0.36363636363636365`、`spread=-0.1610540425109819`、`mean_rank_ic=-0.10649350649350647`、`turnover=[1.5,1.0,2.0,1.5,2.0,1.0,1.0,1.0,1.0,1.5,1.5]`；结果无 `tradability` 键。
>
> **性能实测（T=787×N=5,688）**：`apply_tradability` **1.463 s** / peak 272.8 MB（≤2 s）；`build_tradability_inputs` **3.676 s** / peak 604.3 MB（≤5 s；初版 7.678 s，名称派生改 `np.fromiter` 单遍后达标）；引擎 default **12.516 s** vs enabled **13.746 s**（+1.23 s，仅启用时）；`np.shares_memory(inputs.close, close) == True`（只传引用）。
>
> **版本落点**：3.9.9 落 7 处（`pyproject.toml:7`、`__init__.py:58`、`config_v2.py:371`、`reporting.py:40`、`tests/test_fix3_version_unification.py:34`、`tests/test_backtest/verify_fix3_manual.py:21`、`CHANGELOG.md` 顶部）。
>
> **环境备注（非代码缺陷）**：全量 `pytest -q` 中 `tests/test_backtest/test_attribution_analyzer.py` 16 例因沙箱禁止访问 `%TEMP%\pytest-of-Peng` 报 `PermissionError`；同文件 `--basetemp=<仓内目录>` 复跑 **16 passed**。其余无新增失败。
>
> **CHECKLIST 回填**：§2-§7 共 98 项全部 ✅（§10.1：102 = 98 通过 + 0 失败 + 4 待 Step 10）。

---

**Review 签字**: _________ 日期: _________
