# 调研文档：P-021 tradability 生产启用

---
id: p021-tradability-production-enablement-RESEARCH
type: design
version: 1.1
status: verified
date: 2026-11-23
depends: [p006-tradability-engine-integration, p020-tradability-cleanup-and-ledger]
upstream: null
---

> **Feature**: P-021 tradability 生产启用（影响面 / 数据可得性 / 口径裁决）
> **创建日期**: 2026-11-23
> **状态**: verified（Step 1-2 完成 + Step 2 复核 PASS，见 §5.5；复核为**自查·单视角**，RULE-4——建议 DESIGN 签字前异构复审）
> **Spec 步骤**: Step 1-2
> **批次档位**: **T1**（立项后触及 `backtest/` 与 `tests/`；本文件零代码）
> **收敛来源**: 五份 `docs/research/` 预调研（映射见 §8）；本文件为**唯一决策真值源**，源文档保留为证据附录
> **数据快照**: `E:\Ashare_data\market_data`，2020-01-02 ~ 2026-01-30，1475 交易日 × 5688 只（`close` 口径）
> **一句话**: 启用 tradability **不改变 IC/收益**，只改变 `turnover` 并新增报告块；启用前必须先解 **北交所早期规则硬失败**，并裁决 **执行时点**、**`adj` 缺口策略**两项口径。

---

## 1. 调研目标

**核心问题**:

1. 生产启用后哪些读数会变、变化量级多大、是否影响既有结论？（影响面）
2. 自算限价与本地数据是否足以支撑「证据层」结论？缺 `adj` / ST / 停牌 / 退市 / 限价表时如何降级？（数据与口径）
3. 执行时点、未知限价、北交所早期、三态、数据补强顺序五项分歧如何裁决？（决策锚点）

**非目标（本批不回答）**:

- 收益层净收益口径（`long_short_returns` 改用 effective 权重）——单独立项。
- 空头腿券源/融券成本建模；分钟级/逐笔撮合与挂单队列。
- 外部数据采购与运行时依赖引入（`stk_limit` 仅作离线对拍/补数源）。

---

## 2. 调研方法

### 2.1 工具与证据出口

| 工具 | 用途 | 查询/范围 |
|---|---|---|
| WebSearch / WebFetch | 官方规则、社区实践、数据源文档 | 见 §7；官方页面片段与摘要 |
| 本地 Python 探针（E1） | 全样本限价/触板/缺口/执行时点量化 | 8 组，口径见 §9 |
| Read / Grep | 代码锚点与既有裁决 | `backtest/tradability*.py`、`engine.py`、`factor_metrics.py`、`data_contract.py`、P-006/P-020 四件套 |
| 前批 Tushare 文档全文 | `stk_limit` 字段/覆盖 | 提纲 S7（✅ 全文，前批） |
| 学术检索 | 磁吸效应 / T+1 / 执行时点 | DOI/arXiv 条目已于 Step 2 复核全部解析（§5.5①） |

### 2.2 范围与口径

- **时间**: 2020-01-02 ~ 2026-01-30；`close` 1475 日，`adj` 交集 1394 日（缺 81 日）。
- **领域**: A 股涨跌停判定（主板/创业板/科创板/北交所）、ST、停牌、退市整理、除权参考价、T+1。
- **排除**: 港股/美股、期货、期权；分钟级成交队列。
- **证据等级**: E1 = 本机代码/数据实测；E2 = 官方规则/仓库设计原文；E3 = 社区二手；E0 = 待测。
- **三种「触及」定义**（全文严格区分）:
  1. **精确相等**：`绝对差(high, up) <= eps`；
  2. **引擎谓词**：`high >= up - eps`（`apply_tradability` 实际使用）；
  3. **执行价口径**：`close >= up - eps`（same_close）或 `open[t+1] >= up[t+1] - eps`（next_open）。
- **报价池**：本文触板/封锁计数是**报价可行性池**，未乘真实调仓 delta；真实 `turnover` 影响需 B 批用因子权重测量。
- **限价近似**：按板块名义档位（main 10%、gemstar 20%、bse 30%），**未**细分 ST 5%（2026-07-06 前主板）、创业板 2020-08-24 前 10%、低价股 0.01 元 → 触板池为**下限**。

### 2.3 收敛纪律

- 五份源文档的 E1 读数**不重跑**；本文件只做归并、去重、口径统一与冲突裁决。
- 冲突时以本文件 §4/§6 为准；源文档保留原始上下文与更细的推导。
- 不新增未经实测的数字；凡外推均标「量级估计」并给出假设。

---

## 3. 调研发现（一）：现状基线

### 3.1 能力与接线

| 组件 | 状态 | 锚点 |
|---|---|---|
| 判定与推进核心 | 已交付（9 键报告恒 `int`） | [tradability.py](../../backtest/tradability.py#L304-L461) |
| 面板构建器 | 已交付（13 键 meta） | [tradability_inputs.py](../../backtest/tradability_inputs.py#L29-L162) |
| 引擎接线 | 已交付但**默认关闭**（`tradability_inputs=None`） | [engine.py](../../backtest/engine.py#L63-L106)、[L285-L332](../../backtest/engine.py#L285-L332) |
| 生产管道接线 | **未接线**（只传 `close`） | [pipeline_integration.py](../../backtest/pipeline_integration.py#L136-L146) |
| 批量运行器 | **未接线**（逐因子交集切片） | [parallel_runner.py](../../backtest/parallel_runner.py#L52-L68) |
| CLI / 配置开关 | **不存在** | `DEFAULT_CONFIG`（engine.py L43-48）无该键 |

### 3.2 影响传导（E1）

```
positions ──启用──> apply_tradability ──> effective_w ──> compute_turnover
                                                  └──> result['tradability']{report, meta, 4 口径键}
rank_ic / pearson_ic / hit_rate / spread / long_short_returns ← 不经过 positions
```

- 唯一数值变化是 `turnover`（多头腿推进、空头腿透传），外加每因子一个 `tradability` 块。
- `turnover` 下游：`health_bridge`（拥挤度 L121-125/L187-190）与 `unified_drift`（L266）→ 健康度/漂移判定会变。
- `summary()` 只取 4 个标量 + mean IC（L393-399）→ 新增键不影响摘要。
- 前向收益为 **close-to-close**（`fwd_ret[t]=close[t+1]/close[t]-1`，engine L173）→ `long_short_returns` 不代表可交易净收益（R-4）。

### 3.3 数据形状与缺口（E1）

| 文件 | 形状 | 覆盖 | 对齐/缺口 | 备注 |
|---|---|---|---|---|
| `stock_close.pkl` | 1475×5688 | 2020-01-02 ~ 2026-01-30 | — | NaN 14.13% |
| `stock_high/low/open/volume.pkl` | 同 close | 同上 | 日期/列一致 | 原始价（未复权） |
| `stock_adj.pkl` | 1394×5691 | 同上 | **缺 81 日（5.49%）** | NaN 12.64%，max 10055.64 |
| `stock_name.pkl` | 1474×6053 | 同上 | **缺 2026-01-30** | ST 265,296（2.97%，全 name 面板口径） |
| `stock_suspend.pkl` | 1475×5681 | 同上 | **少 7 列** | `None` / `'S'` 18,242 / `'R'` 2,700 |
| `stock_return.pkl` | 1475×5688 | 同上 | 无缺口 | **百分数**（p99=10.01，max=200,400） |
| `list_date_df.pkl` | 5797×1 | 全历史 | 索引裸 6 位代码 | 列 `list_date` |
| `all_dates.pkl` | 1475 | 同上 | — | `list` |

- 面板列并集 **6053**，`close` 仅 5688；365 个代码只在其他面板。
- 板块前缀（并集）：`300` 978 / `002` 973 / `600` 874 / `603` 619 / `688` 605 / `000` 506 / `301` 452 / **`920` 293** / `601` 231 / `605` 113。
- 缺口清单 G-1~G-6：`adj` 81 日 / name 末日 / suspend 列集 / 无独立 ST 表 / 无退市标志 / 无权威限价表。

### 3.4 关键代码锚点

| 位置 | 事实 |
|---|---|
| [tradability.py L31-L41](../../backtest/tradability.py#L31-L41) | `DEFAULT_LIMIT_RULES`：main 10%（ST 5%→2026-07-06 起 10%）、star 20%、gem 10%→20%（2020-08-24）、bse 30%（自 2021-11-15） |
| [tradability.py L160-L191](../../backtest/tradability.py#L160-L191) | `compute_limits` 支持低价 ST（`prev<0.1` → ±0.01 元），但生产两处调用均未传 `is_st` → **未接线** |
| [tradability.py L234-L255](../../backtest/tradability.py#L234-L255) | `_ref_from_adj`：`adj` 单侧缺失 → `ref=NaN`（不回退原始昨收） |
| [tradability.py L316-L318](../../backtest/tradability.py#L316-L318) | `execute_at` 仅做合法性校验，循环体内**从未消费** |
| [tradability.py L385-L386](../../backtest/tradability.py#L385-L386) | `can_buy = ~susp & (~judge or not (high >= up - eps))`；`open_`/`volume` 未参与 |
| [tradability_inputs.py L51](../../backtest/tradability_inputs.py#L51) | `suspend` 直接 `astype(bool)` → `'S'` 与 `'R'` 都成停牌 |
| [tradability_inputs.py L74-L102](../../backtest/tradability_inputs.py#L74-L102) | `no_limit`：所有板块上市后前 5 个交易日 + 退市整理首日 |
| [engine.py L304-L311](../../backtest/engine.py#L304-L311) | 报告块 4 口径键：`price_basis / leg_scope / short_leg_unmodeled / turnover_basis` |
| [data_contract.py L662](../../backtest/data_contract.py#L662) | `return` 一致性检查按 decimal `[-1,10]`，与实际百分数不符（当前主链路未消费 `stock_return`） |

---

## 4. 综合分析：影响面、分级与决策锚点

### 4.1 影响面结论 R-1~R-10

| # | 结论 | 等级 |
|---|---|---|
| R-1 | 启用后 `rank_icir / pearson_icir / hit_rate / spread / long_short_returns` **逐位不变** | E1 |
| R-2 | 唯一数值变化是 `turnover`（多头腿推进、空头腿透传），并新增 `result['tradability']` 块 | E1 |
| R-3 | `turnover` 是健康度拥挤度与漂移特征输入 → **健康度/漂移判定会变**（中风险，需阈值敏感性） | E1 |
| R-4 | 收益层未接：`long_short_returns` 仍用因子秩与 fwd return，**不代表可交易净收益** | E1 |
| R-5 | 生产调用图**零接线**：管道只传 close，批量运行器逐因子交集切片 | E1 |
| R-6 | 本机数据接近 D0，但有两个洞（`adj` 缺 81 日、`name` 缺 1 日）；若降级，偏差方向均为**乐观** | E1 |
| R-7 | 口径误差量级：除权不对齐 → 主板除权日涨停漏判 **206/369（55.8%）**；固定 0.095 阈值 → 误判 **26,029 格** | E1 |
| R-8 | 默认路径（`tradability_inputs=None`）有 TP6-11 字面量锁定，启用必须另建端到端门禁 | E1 |
| R-9 | 「触及即封锁」是 DESIGN §14.4 的有意裁决；代价首次量化：一字板仅占 **5.62%**（精确相等）/ **5.46%**（引擎谓词） | E1 |
| R-10 | **启用前置阻断**：296 只 bse × 2020-01-02 → `_pct_matrix` 首日抛 `ValueError`（`bse` 规则自 2021-11-15） | E1 |

### 4.2 数据分级 D0-D5

| 级别 | 判据 | 处置 | 披露 | 偏差方向 |
|---|---|---|---|---|
| **D0** | 7 字段齐备且覆盖 ≥ 阈值（建议 99%） | 正常路径；`price_basis="raw_adj_ref"` | `data_tier`、`missing_fields` | 无系统偏差 |
| **D1** | `adj` 缺失/覆盖 < 99% | `ref` 回退 `prev_close`；`prev` 也缺失时记 `limit_unknown` | `data_tier`、`price_basis="raw_close"`、`exdiv_unadjusted_days`、`ref_fallback_days` | **乐观**（除权日漏判涨停约 56%） |
| **D2** | `name` 缺失/覆盖 < 99% | `is_st` 前向填充；全缺则 False | `st_assumed_cells` | **乐观**（限价过宽） |
| **D3** | `suspend` 缺失/列集不可对齐 | `volume==0 & high==low` 推断；不可推断则 False | `suspend_unmodeled`、`inferred_suspended_cells` | **乐观**（高估可交易） |
| **D4** | `list_date` 缺失 | `no_limit` 全 False | `ipo_unmodeled` | **保守**（高估封锁） |
| **D5** | 无 high/low | **不启用**；报告省略 tradability 块 | `data_tier="unavailable"` | 不可用 |

> **D5 定义收窄（2026-11-23，D6 用户确认）**：`high/low` 缺失不再直接「不启用」——可降级 `execution_only_open`（T+1 开盘成交、一字诊断关闭）；仅 `open/prev` 不可用才 `off`。执行口径以 [DESIGN.md](./DESIGN.md) §6.2/§5.10 为准；本表保留调研期分级原貌。

**三条降级纪律**：① 不得向上兼容（缺 `adj` 禁写 `raw_adj_ref`）；② 每级必须同时含 `data_tier` 与 `missing_fields`；③ D1~D5 各至少 1 例测试。组合缺失取最差级，`bias_direction="optimistic"` 时禁止进入收益结论。

### 4.3 未决事项 O-1~O-11

| # | 事项 | 类型 | 方向 | 量级（E1） | 优先级 | 处置 |
|---|---|---|---|---|---|---|
| O-1 | 触及/打开/一字三态 | 已裁决未量化 | 保守 | 一字 5.62%/5.46%，约 94% 触板格被封锁 | P2 | 保持口径 + 披露 + B 批敏感性 |
| O-2 | `adj` 缺 81 日 | 数据缺口 | 乐观 | 缺口日承载 24.9% 跌停触板（下限） | **P1** | 优先 `stk_limit`；否则回退 + 披露 |
| O-3 | 低价股 0.01 元 | 已实现未接线 | 双向（极少数） | ST 格 2.85%，`prev<0.1` 仅 1 格 | P3 | 接线或删参；补 0.05 元档 |
| O-4 | 退市整理 | 已覆盖·数据源弱 | 偏保守 | 名称缺失 1 日 | P2 | 接公告表；补 `name_missing_days` |
| O-5 | ST 仅名称推断 | 未覆盖（数据源） | 乐观（漏记） | ST 格 225,581（2.85%，close 对齐口径） | P2 | `namechange` 构造逐日面板 |
| O-6 | 空头腿未建模 | 未建模 | 乐观 | 券源/成本全忽略 | P2 | 维持 `long_only` 披露；B 批不做空 |
| O-7 | 停牌 `'R'`/列集 | 语义缺陷 + 未覆盖 | 双向 | `'R'` 2,625 格；缺 7 列 | P2 | 显式 `suspend=='S'`；披露 |
| O-8 | `execute_at` 未消费 | 未实现/口径错配 | 双向 | 主板 90.7% 过度封锁、0.150% 漏封 | **P1** | 实现 `next_open`（D1） |
| O-9 | 北交所早期规则 | 未覆盖 → **硬失败** | 阻断 | 296 只 bse × 2020-01-02 抛错 | **P1** | 规则前移 + 早期 unknown（D3） |
| O-10 | 开盘一字 vs 盘中封板 | 未建模（`open_` 未用） | 保守 | 开盘即涨停 11.65%（含一字） | P2 | 披露；分钟级验证可选 |
| O-11 | `carried` 键语义 | 文档-实现偏差 | 无（报告） | 终态快照 ≠ 累计顺延 | P3 | 文档勘误或改名 |

### 4.4 五项决策锚点 D1-D5

| # | 决策 | 推荐 | 关键量化 | 被拒备选与代价 |
|---|---|---|---|---|
| **D1** | 执行时点 | **实现 `next_open`**：`target_w.shift(1)` + `open` 判定 | 封锁池 touch **127,937** / close **86,039** / next_open **17,373**；卖出 43,613 / 24,694 / 11,591 | A `same_close`（Qlib 默认，但需逐因子时点审计）；C 保持现状（字段与实现不一致，禁用） |
| **D2** | 未知限价（`adj` 缺口） | **原始昨收回退 + 披露**；有 `stk_limit` 则优先 | 81 日 / **403,499 格**；回退判定翻转约 **18 买 / 155 卖（量级估计）**；整日封锁 = 100% 过度封锁 | A 整日封锁（过度）；B 现状放行（无披露）；D `stk_limit`（最优，若可得） |
| **D3** | 北交所早期 | **规则前移 2020-07-27；更早 `neeq_pre_select` unknown + 披露** | 2020-07-27 前 **8,792 格/194 只**（全样本 0.13%）；精选层段 29,187 格 | B 裁剪（丢 15.6% bse 格）；C 建模 NEEQ 竞价/做市（成本高、仅 0.13%） |
| **D4** | 三态 | **只披露 + B 批 `limit_mode=one_word` 敏感性；不做一字-only** | 一字 6,990/127,937=**5.46%**；一字-only 会把 32% 炸板日全部放行 | C 一字-only（过激）；D1 定案后三态改为「执行日状态」 |
| **D5** | 数据补强顺序 | **`stk_limit` → 停牌 → `adj` 回退 → ST → 退市** | `stk_limit` 一次覆盖限价/除权/ST/北交所/低价股；停牌与 `adj` 回退零外部依赖 | 原「按缺口大小」排序被「风险降低/成本」取代 |

> **D5 执行分支（U-2 已验证）**：`stk_limit` 当前不可得（§5.6）→ 实际顺序为 **停牌 → `adj` 回退 → ST → 退市**；token 到位后前置 `stk_limit` 并补 V-8 外部对拍。

**D1 的等价实现**（供 DESIGN 参考）：`apply_tradability(target_w.shift(1), ...)`，执行谓词从 `high/low` 改为 `open`；首日目标补 0，最后一日信号丢弃；`turnover` 序列后移 1 日，报告标 `execution_timing="t_plus_1_open"`。

### 4.5 关键量化索引（E1）

| 指标 | 读数 | 口径 |
|---|---:|---|
| 可计算 OHLC 格（有限值） | 6,784,896 | 1394 日 × 5688 只中的有限格 |
| 精确触板（买/卖） | 115,923 / 31,205 | 精确相等 |
| 引擎触板（买/卖） | 127,937 / 43,613 | `>=` 谓词 |
| 一字板（精确/引擎，买） | 6,512（5.62%）/ 6,990（5.46%） | `high==low` |
| 除权股票×日（数据分级口径） | 主板 24,538 / 双创 12,823 | `close/high/low/adj` 交集 |
| 除权日限价错 | 62.3% / 71.8% | 主板 / 双创 |
| 除权日涨停漏判 | 206/369（55.8%）/ 29/56（51.8%） | 主板 / 双创 |
| 0.095 阈值误判/漏判 | 26,029 / 212 | 主板精确涨停 101,890 |
| 0.10 阈值误判/漏判 | 9,622 / 38,449 | 同上 |
| `adj` 缺口 | 81 日 / 403,499 格 | 2020-01-10 ~ 2025-04-10 |
| 缺口日触板（精确 / 引擎，买/卖） | 7,448 / 10,366；7,477 / 10,393 | 原始昨收近似 |
| 缺口日跌停触板占比 | **24.9%（精确）/ 19.2%（引擎）** | 10,366/41,571；10,393/54,006 |
| `stock_return` 缺口日 vs 原始收益 | 403,499 格全一致（max 5e-7） | 无除权信息 |
| `ref_ret` vs `ref_adj`（除权格） | 99.86% / 99.91% / 92.7% | 主板 / 双创 / 北交所（0.1% 内） |
| bse 有效格 | 8,792 / 29,187 / 204,831 | 2020-07-27 前 / 精选层 / 北交所 |
| 停牌 `'R'` | 2,625 格 | 对齐后 |
| ST 格 | 225,581（2.85%） | close 对齐 1393 日 |
| 低价 ST（`prev<0.1`） | 1 格 | — |

> 除权格计数随样本交集不同：§4.5 的 24,538/12,823 为 `close/high/low/adj` 交集；`ref_ret` 校验用 24,863/12,834/1,018（含 `return` 交集，合计 38,715）。两者不可混用。

### 4.6 外部与社区证据（摘要）

- **官方规则**：沪深北交易所除权参考价公式与四舍五入至 0.01 元；风险警示 5%、前收 ≤0.1 元 → 0.01 元；退市整理 10%、前收 ≤0.05 元 → 0.01 元；精选层/北交所 30%；NEEQ 基础/创新层竞价 −50%/+100%、做市无涨跌幅。
- **社区实践**：Qlib 固定 0.095 阈值 + `forbid_all_trade_at_limit`；RiceQuant/RQAlpha/JoinQuant 以当日限价为拒单基准；Tushare `stk_limit` 为权威对拍源；社区普遍**不做除权参考价对齐**；三态口径（未触及/触及打开/全天一字）为少数正确实践。
- **学术**：磁吸效应（B-1 ✅《计量经济学报》2021：跌停强于涨停、盘中强于开盘；B-2 ✅ 台湾磁吸）；冷却效应（B-3 ✅，与 B-1 结论相反——学术分歧，仲裁见 §5.5②）；T+1 隔夜折价 **14 bps**（B-4 ✅，期刊名已订正为 *J. Financial Markets*）；T+0/T+1 制度成本（B-5 ✅）。

#### 4.6.1 方案 landscape

| 方案 | 代表 | 误差（主板实测） | 本仓取舍 |
|---|---|---|---|
| 自算精确价（除权参考价 + half-up） | 本仓 `compute_limits` | 基准（精确涨停 101,890） | **主路径** |
| 固定 0.095 阈值 | Qlib 配置 / 社区 | 误判 26,029、漏判 212 | 仅粗筛，禁止主路径 |
| 固定 0.099 / 0.10 阈值 | 部分社区 | 12,362/2,279；9,622/38,449 | 明确不可用 |
| 数据商限价表 | Tushare `stk_limit` | 权威 | **对拍/补数源**（离线） |
| 全复权价 | 部分自建栈 | 价格水平失真，不能与交易所限价对齐 | 不可用于限价 |

### 4.7 研究空白与本仓差异点

1. **除权对齐**：社区普遍直接用昨收×比例，不做除权参考价；本仓已实现 `_ref_from_adj`，但缺 81 日 `adj` → 差距在数据而非算法。
2. **限价来源**：社区多用固定阈值；本仓规则表更细（板块/ST/日期/北交所），但缺权威 `stk_limit` 对拍，规则正确性尚未外部证明。
3. **三态与执行时点**：社区有三态口径但无统一「执行日状态」定义；本仓当前是「T 日 high/low」混合口径，需 D1 收敛。
4. **未知限价降级**：社区平台通常由数据层兜底（总有 `limit_up/down`），没有成熟「缺 `adj` 日」的公开实践；本仓需自行定义并披露。

---

## 5. 幻觉抑制审查（Step 2 Review）

### 5.1 引用验证表（F4）

> 标识符解析状态：**已验证** = 官方页面/条款片段或仓内原文直读；**摘要级** = 仅搜索摘要，未回原文；**未验证** = 解析失败或未执行。`✅` 只用于已验证项。

#### 5.1.1 官方规则与数据源

| # | 引用 | ID | 层 | 读取日 | 发布/版本 | 验证方式 | 状态 | 命中或差异 |
|---|---|---|---|---|---|---|---|---|
| A-1 | 上交所交易规则（2026 修订）4.3.2/§4.4 | https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml | T1 | 2026-11-23 | 2026 修订 | 官方页面片段 | ✅ 片段 | 除权公式、风险警示板范围命中 |
| A-2 | 深交所交易规则 4.4.2 | https://www.szse.cn/disclosure/notice/general/t20060515_499577.html | T1 | 2026-11-23 | 页面未标版本 | 搜索摘要 | 摘要级 | 除权公式旁证 |
| A-3 | 北交所交易规则 4.3.2 | https://www.bse.cn/jygl_list/200028217.html | T1 | 2026-11-23 | 页面未标版本 | 搜索摘要 | 摘要级 | 北交所除权口径旁证 |
| A-4 | 证监会法规详情 第七条 | https://neris.csrc.gov.cn/falvfagui/rdqsHeader/mainbody?navbarId=3&secFutrsLawId=66010d2fe45148d09ba2eb3e1bbbbe33 | T1 | 2026-11-23 | 条款页 | 条款片段 | ✅ 条款 | 风险警示 5%、0.1 元→0.01 元；退市整理 10%、0.05 元→0.01 元 |
| A-5 | 证监会法规详情 第七十四条 | https://neris.csrc.gov.cn/falvfagui/rdqsHeader/mainbody?navbarId=3&secFutrsLawId=40b7025332804891a7a6f6c7b0595828 | T1 | 2026-11-23 | 条款页 | 条款片段 | ✅ 条款 | NEEQ 竞价 −50%/+100% |
| A-6 | 全国股转《新三板投资者手册》 | https://www.neeq.com.cn/uploads/1/file/public/202006/20200605104834_4kiddpghe7.pdf | T1 | 2026-11-23 | 2020-06-05 发布 | 摘要 + PDF | ✅ 表格片段 | 精选层 ±30%、创新层竞价 −50%/+100%、做市无涨跌幅 |
| A-7 | 全国股转《股票交易规则》第九十一条 | https://www.neeq.com.cn/class_d/200011897.html | T1 | 2026-11-23 | 页面未标版本 | 条款片段 | ✅ 条款 | 连续竞价 30% |
| A-8 | 中证网：精选层 7 月 27 日开市 | https://www.cs.com.cn/xwzx/hg/202007/t20200723_6079034.html | T2 | 2026-11-23 | 2020-07-23 | 搜索摘要 | 摘要级 | 精选层开市、成交首日无涨跌幅 |
| A-9 | 深交所：退市整理股票涨跌幅 | http://www.szse.cn/investor/institute/rules/t20231228_605143.html | T1 | 2026-11-23 | 页面未标版本 | 搜索摘要 | 摘要级 | 主板退市整理 10%、首日不限 |
| A-10 | 上海证券报：主板 ST 5%→10% | http://paper.cnstock.com/html/2026-07/07/content_2240331.htm | T2 | 2026-11-23 | 2026-07-07 | 搜索摘要 | 摘要级 | 2026-07-06 起生效 |
| A-11 | 证监会：暂停转融券业务 | https://www.csrc.gov.cn/csrc/c100028/c7493852/content.shtml | T1 | 2026-11-23 | 2024-07-10 | 页面摘要 | ✅ 摘要 | 7/11 暂停；保证金 100%/私募 120%，7/22 起 |
| A-12 | 证监会：全面注册制答记者问 | http://www.csrc.gov.cn/csrc/c100028/c7047624/content.shtml | T1 | 2026-11-23 | 2023-02 | 页面摘要 | ✅ 摘要 | 主板新股前 5 个交易日不设涨跌幅 |
| A-13 | 中证网：主板交易新规（2023-04-10） | https://www.cs.com.cn/gppd/gsyj/202304/t20230410_6335974.html | T2 | 2026-11-23 | 2023-04-10 | 搜索摘要 | 摘要级 | 第 6 日起 10%；此前首日 144%/64% |
| A-14 | Tushare `stk_limit` | https://tushare.pro/document/2?doc_id=183 | T1 | 2026-11-23（前批） | 文档页 | 前批 WebFetch 全文 | ✅ 全文 | 2007-01-04 起、含 exchange |
| A-15 | Tushare `suspend_d` | https://tushare.pro/document/2?doc_id=214 | T1 | 2026-11-23（前批） | 文档页 | 搜索摘要 | 摘要级 | `S`-停牌 / `R`-复牌 |
| A-16 | Tushare `namechange` | https://tushare.pro/document/2?doc_id=100 | T1 | 2026-11-23（前批） | 文档页 | 搜索摘要 | 摘要级 | ST 变更历史 |
| A-17 | Tushare `limit_list_d` | https://tushare.pro/document/2?doc_id=298 | T1 | 2026-11-23（前批） | 文档页 | 搜索摘要 | 摘要级 | 2020 年起、不含 ST |
| A-18 | Qlib Workflow（`deal_price`） | https://qlib.readthedocs.io/en/stable/component/workflow.html | T1 | 2026-11-23 | stable 文档 | 官方页面片段 | ✅ 片段 | `deal_price: close` 默认 |
| A-19 | RiceQuant 回测（撮合基准） | https://www.ricequant.com/doc/quant/backtest | T1 | 2026-11-23 | 页面未标版本 | 官方页面片段 | ✅ 片段 | 当前收盘价 / 下一开盘价两种均支持 |
| A-20 | RQAlpha 基础 API | https://rqalpha.readthedocs.io/zh-cn/develop/api/base_api.html | T1 | 2026-11-23 | 页面未标版本 | 搜索摘要 | 摘要级 | `limit_up`/`limit_down` 为 bar 属性 |
| A-21 | JoinQuant API PDF | https://cdn.joinquant.com/help/img/JoinQuantAPI.pdf | T1 | 2026-11-23 | PDF | 搜索摘要 | 摘要级 | 涨停/跌停不成交、市价单取消 |

#### 5.1.2 学术

| # | 引用 | ID | 层 | 读取日 | 发布/版本 | 验证方式 | 状态 | 命中或差异 |
|---|---|---|---|---|---|---|---|---|
| B-1 | 陆昌, 刘洋, 杨晓光 (2021). 基于反事实模拟的中国股市涨跌停板磁吸效应研究. 《计量经济学报》1(1):217-232 | DOI 10.12012/2020-0008-16 | T1 | 2026-11-23 | 2021-01-27 出版 | **期刊官网全文页**（Crossref 无此注册 → 降级命中） | ✅ 已验证 | 摘要逐字确认：「stronger near lower price limit than near upper」（跌停强于涨停）、「middle of the trading day … than at the opening period」（盘中强于开盘）；完整元数据（作者/卷期页/收稿日）命中 |
| B-2 | Cho, Russell, Tiao & Tsay (2003). The magnet effect of price limits | DOI 10.1016/S0927-5398(02)00024-5 | T1 | 2026-11-23 | JEF 10(1-2):133-168, 2003-02 | Crossref works API | ✅ 已验证 | 标题/四位作者/卷期页/年份全匹配 |
| B-3 | Wan, Wang, Jiang, Xie & Zhou (2018). The cooling-off effect of price limits in the Chinese stock markets | arXiv:1803.09422 | T1 | 2026-11-23 | 2018-03-26 v1；journal_ref Physica A 505:153-163 | arXiv API | ✅ 已验证 | 标题/五位作者/摘要命中；正式 DOI 10.1016/j.physa.2018.03.066；结论与 B-1 相反（见 §5.5② 仲裁） |
| B-4 | Qiao & Dam (2020). The overnight return puzzle and the "T+1" trading rule in Chinese stock markets | PII S1386418120300033 | T1 | 2026-11-23 | **J. Financial Markets** 50:100534, 2020-09 | Crossref alternative-id | ✅ 已验证（**期刊名错配已订正**：原文误写 JBF） | 「estimate the average T+1 discount at **14 bps**」摘要逐字确认（RePEc/Rug PDF 双通道） |
| B-5 | Wu & Qin (2015). Do We Need to Recover T+0 Trading? Evidence from the Chinese Stock Market | DOI 10.1080/1540496X.2015.1080495 | T1 | 2026-11-23 | EMFT 51(6):1084-1098, 2015 | Crossref works API | ✅ 已验证 | 标题/两位作者/卷期页/年份全匹配 |

#### 5.1.3 社区

| # | 引用 | ID | 层 | 读取日 | 发布/版本 | 验证方式 | 状态 | 命中或差异 |
|---|---|---|---|---|---|---|---|---|
| C-1 | 腾讯云：涨停判断不能写 `return>=0.1` | https://developer.cloud.tencent.com/article/2773854 | T3 | 2026-11-23（继承） | 无版本 | 搜索摘要 | 摘要级 | 三态口径 |
| C-2 | 华为云：涨跌停/停复牌处理 | https://bbs.huaweicloud.com/blogs/517427 | T3 | 2026-11-23（继承） | 无版本 | 搜索摘要 | 摘要级 | 板块/ST/北交所规则旁证 |
| C-3 | 迪雅数据：涨停价四舍五入 | https://www.diyadata.cn/guide/limit-up-price.html | T3 | 2026-11-23（继承） | 无版本 | 搜索摘要 | 摘要级 | 四舍五入 + 一字板 |
| C-4 | 博客园：成交/涨跌停用不复权真实价 | https://www.cnblogs.com/quantlab-notes/p/23530463 | T3 | 2026-11-23（继承） | 无版本 | 搜索摘要 | 摘要级 | 少数正确实践 |
| C-5 | 华安证券：换手板 90.8% / 一字 9.2% | 提纲 C-5（无公开链接） | T3 | 2026-11-23（继承） | 无版本 | 前批摘要 | 摘要级 | 与一字 5.46%/5.62% 同量级 |

### 5.2 技术声明验证

| # | 声明 | 来源 | 状态 |
|---|---|---|---|
| T-1 | 启用只改 `turnover`，IC/收益不变 | engine L271-318（E1） | ✅ 已验证 |
| T-2 | 除权日限价错 62.3%/71.8%，涨停漏判 55.8% | 本机探针（E1） | ✅ 已验证 |
| T-3 | 0.095 阈值误判 26,029 / 漏判 212 | 本机探针（E1） | ✅ 已验证 |
| T-4 | 一字 5.62%（精确）/ 5.46%（引擎） | 本机探针（E1） | ✅ 已验证 |
| T-5 | `adj` 缺 81 日，缺口日承载 24.9% 跌停触板 | 本机探针（E1） | ✅ 已验证 |
| T-6 | `stock_return` 缺口日退化为原始收益 | 本机探针（E1） | ✅ 已验证 |
| T-7 | `ref_ret` 在除权格复现 `ref_adj` 99.86%/99.91% | 本机探针（E1） | ✅ 已验证 |
| T-8 | bse 2020-01-02 构建抛 `ValueError` | 本机复现（E1） | ✅ 已验证 |
| T-9 | `execute_at` 声明未消费 | 代码直读（E1） | ✅ 已验证 |
| T-10 | 停牌 `'R'` 2,625 格被误判 | 本机探针（E1） | ✅ 已验证 |
| T-11 | ST 2.85%，低价 ST 1 格 | 本机探针（E1） | ✅ 已验证 |
| T-12 | 所有板块前 5 日 `no_limit` 未分板块/日期 | 代码直读 + 官方规则（E1/E2） | ✅ 已验证（方向） |

### 5.3 待修正项

- [x] 修正 `docs/research` 中 1 处失效链接（`../spec/` → `../../spec/`）。
- [x] 统一一字口径：5.46%（引擎）/ 5.62%（精确相等）并在三处加脚注。
- [x] 决策锚点补 F1/F2/F4 引用表与 U-6~U-9 四元登记。
- [x] 本文件收敛五份源文档，建立唯一决策真值源。
- [x] 学术 DOI 5 条全部解析（B-1~B-5，超额完成；1 处期刊名错配已订正）——见 §5.5①。
- [x] S1-S6 社区条目明确降级为「旁证，不承载关键结论」——关键结论由官方规则（A-1~A-21）+ 本仓 E1 承载——见 §5.5⑤。
- [x] 历史三份（提纲/分级/未决项）来源表的 F1/F2：决定性条目已在 §5.1 补齐；源文档为附录级，不再逐行迁移——见 §5.5⑤。
- [x] `stk_limit` 可得性验证（U-2）：2026-11-23 验证为**当前环境不可得**（无 token/包/缓存；API 可达 40101；PyPI 1.4.29 可装）→ 走 `fallback_raw` 分支，token 到位后可升级——见 §5.6。
- [x] 开源源替代调研 + Tushare 格式 mock 干跑：**无免注册全量替代**；AkShare 仅事件池；Tushare 配置保留；干跑 PLUMBING_OK（18/18 + 4 类扰动检出）——见 §5.7。
- [ ] 因子时点审计（仅 D1-A 分支触发，U-4；D1 推荐 `next_open` 则不需要）。

### 5.4 Step 2 门禁自查

| 门禁 | 状态 | 说明 |
|---|---|---|
| (a) FALSIFIED 断言改写 | ✅ | 4 条已改写：「低价股未实现」→「已实现未接线」；「退市首日未覆盖」→「已覆盖，缺口在名称」；「三态未建模」→「有意裁决未量化」；「ST 2.97%」→ 分口径 2.97%/2.85% |
| (b) CONFLICT / STEP_GAP 仲裁 | ✅ | 三态 vs 执行时点 → 以 D1 `next_open` 统一；「未知即封锁」vs「回退」→ 以 D2 回退为准；bse 规则空档 → D3 A |
| (c) 阻断性断言双源 | ✅ | 精选层 30%（A-6/A-7/A-8）；除权公式（A-1/A-2/A-3）；0.1 元（A-4/A-1）；Qlib 默认（A-18）；单源项已标「单源/摘要级」 |
| (d) 假设转四元 | ✅ | U-1~U-9 见 §6.4；D1-D5 已于 2026-11-23 用户确认（见 [DESIGN.md](./DESIGN.md)），不属未决假设 |

### 5.5 Step 2 复核记录（2026-11-23，独立 pass）

> **RULE-4 声明**：本复核由撰写后的独立 pass 执行，但与撰写同属单会话——标注为**自查（单视角）**；建议 DESIGN 签字前由异构基座做第二会话复审（RULE-5，非阻断）。

**① 标识符解析（引用核验四步：抽取 → 解析 → 字段比对 → 落状态）**——5/5 解析，1 处元数据错配订正：

| ID | 通道 | 结果 |
|---|---|---|
| DOI 10.12012/2020-0008-16 | Crossref **失败**（Resource not found）→ 降级期刊官网 | ✅ 命中：《计量经济学报》2021, 1(1):217-232，陆昌/刘洋/杨晓光（收稿 2020-04-05，出版 2021-01-27）；摘要逐字确认两条方向性结论 |
| DOI 10.1016/S0927-5398(02)00024-5 | Crossref works API | ✅ 元数据全匹配（Cho/Russell/Tiao/Tsay，JEF 10(1-2):133-168, 2003-02） |
| arXiv:1803.09422 | arXiv API | ✅ 命中（Wan/Wang/Jiang/Xie/Zhou, 2018-03-26 v1；journal_ref Physica A 505:153-163；正式 DOI 10.1016/j.physa.2018.03.066） |
| PII S1386418120300033 | Crossref alternative-id | ⚠️→✅ **期刊名错配**：实为 *Journal of Financial Markets* 50:100534 (2020-09)，Qiao & Dam（v1.0 误写 JBF）→ 已订正；「14 bps」摘要逐字确认（RePEc + Groningen PDF 双通道） |
| DOI 10.1080/1540496X.2015.1080495 | Crossref works API | ✅ 元数据全匹配（Wu & Qin，EMFT 51(6):1084-1098, 2015） |

**② CONFLICT 仲裁（B-1 vs B-3，学术方向相反）**：Lu/Liu/Yang (2021) 反事实模拟法支持中国市场**磁吸效应**（跌停强于涨停、盘中强于开盘）；Wan et al. (2018) Logit 法支持**冷却效应**（接近限价时条件概率降低）——两文对中国市场结论相反，且 Lu 文引言亦承认 Wan 文为否定证据。**仲裁：不影响 D1-D5 与本文件任何决策**。理由：触板率全部由本仓自有数据 E1 实测承载（§4.5），学术结论仅用于动机层（「限价附近动态存在 → 需要披露」）；「触及即封锁」的保守方向与披露式设计对磁吸/冷却两种效应均稳健。登记为已知学术分歧，不升门禁、不改裁决。

**③ E1 锚点重放**：本轮重放 T-9（`execute_at` 仅出现于 [L196](../../backtest/tradability.py#L196)/[L317-318](../../backtest/tradability.py#L317-L318)，grep 6 处命中中 4 处为 `carried` 定义与计算——确认循环体未消费）与 O-11（`carried` = [L459-460](../../backtest/tradability.py#L459-L460) 末日终态快照）；T-1（engine L285-332）、T-8（bse `ValueError` 复现）、T-2~T-7/T-10/T-12 由同日探针读数承载，复跑口径见 §9。

**④ 通道降级声明（F3）**：仅 1 条降级——B-1 Crossref 通道失败 → 期刊官网通道命中（失败原因：该刊 DOI 注册于自有系统，非 Crossref）；其余通道一次成功。

**⑤ 待修正项处置**：学术解析 ✅（超额：原计划 2 条，实际 5 条）；S1-S6 降级旁证 ✅；历史三份 F1/F2 ✅（决定性条目已入 §5.1，附录级不再迁移）；**U-2 已闭环**（2026-11-23 验证为当前环境不可得 → 走 `fallback_raw`，见 §5.6）；U-4 因子时点保持开放（仅 D1-A 分支触发）。

**⑥ 门禁复核**：(a) 4 条 FALSIFIED 改写留痕 ✅；(b) 3 组冲突仲裁（三态×时点 / 封锁×回退 / 磁吸×冷却）✅；(c) 阻断断言双源（精选层 30%：A-6/A-7/A-8；除权公式：A-1/A-2/A-3；0.1 元：A-4+A-1；单源项均标「摘要级/单源」）✅；(d) U-1~U-9 四元完整（判据/触发/倾向/等级齐备）✅。

**结论**：**Step 2 Review PASS（自查·单视角）**。RESEARCH v1.1 可进入 Step 3（DESIGN），前置条件：① D1-D5 **已于 2026-11-23 用户确认**（见 [DESIGN.md](./DESIGN.md)）；② U-2 **已验证：当前环境不可得（缺 token），按 D2 `fallback_raw` 分支**（§5.6）；③ 异构复审建议（非阻断）。

### 5.6 U-2 验证记录：`stk_limit` 可得性（2026-11-23）

> **结论：当前环境不可得（缺凭证），但网络、接口与安装源均验证可用。** 按 D2/D5 回退分支推进；若后续提供 token，可无缝切换到权威源并补做 V-8。

| 检查项 | 方法 | 读数 | 判定 |
|---|---|---|---|
| Python 包 | `importlib.util.find_spec('tushare')` | base = False；open-webui = False | 未安装（PyPI 最新 **1.4.29**，可安装） |
| 环境变量 | Process/User/Machine 三作用域匹配 `TUSHARE\|TS_TOKEN` | 全部未设置 | 无 token |
| token 文件 | `~/.tushare/token` 等 6 处候选 | 均不存在 | 无 token |
| 本地缓存 | `E:\Ashare_data` 深度 3 搜索 `*limit*` | **0 命中** | 无 `stk_limit` 快照 |
| 凭据管理器 | `cmdkey /list` 过滤 tushare | 0 命中 | 无凭据 |
| 网络 | `HEAD https://api.tushare.pro` | **HTTP 200** | 可达 |
| 接口 | POST `stk_limit`，空 token | **`code=40101, msg=您上传Token！`** | 端点在线、强制 token |
| 安装源 | PyPI `tushare` JSON | **1.4.29** | 可安装 |

**含义与分支**：

- 「不可得」的原因是**凭证缺失**，不是网络或包；用户提供 token 后，用 HTTP API 即可直接对拍，无需改代码或新增运行时依赖。
- token 还需具备 `stk_limit` 接口权限（Tushare 点数门槛）；无 token 无法在本次验证点数。
- 当前默认：D2 走 `fallback_raw` + 披露；D5 实际顺序变为 **停牌 → `adj` 回退 → ST → 退市**，`stk_limit` 作为条件性升级（trigger = token 到位）。
- C 批对拍降级为**内部一致性对拍**（`ref_ret` vs `_ref_from_adj` 99.86%/99.91%/92.7% + 规则边界用例）；V-8 外部一致率留待 token。
- 开源替代已检索（§5.7）：**源码级确认**无免注册全量限价源（AkShare 380 个 `.py` 中股票 `up_limit/down_limit` 0 命中，仅事件池子集含「涨停价」）；Tushare 配置保留，已用 Tushare 格式 mock 完成通路干跑。

**复跑口径**（不打印 token）：

```
python -c "import importlib.util; print(importlib.util.find_spec('tushare') is not None)"
# POST https://api.tushare.pro
# body: {"api_name":"stk_limit","token":"<TOKEN>","params":{"ts_code":"000001.SZ","trade_date":"20240102"},
#        "fields":"ts_code,trade_date,up_limit,down_limit"}
```

### 5.7 开源源替代调研与 Tushare 格式干跑（2026-11-23）

> **结论：未发现免注册、可离线快照的逐日全市场限价开源源。** Tushare `stk_limit` 保留为唯一权威全量源（token 到位即启用）；当前按 D2 `fallback_raw` 推进。AkShare 仅有 6 个 `stock_zt_pool_*` 事件池（部分含**子集**涨停价），可作子集抽查，不承载限价主源。

**① 候选源对比**

| 源 | 免注册 | 逐日全市场 `up_limit/down_limit` | 覆盖/形态 | 结论 |
|---|---|---|---|---|
| Tushare `stk_limit` | 否（token + 点数权限） | **是** | 2007-01-04 起，逐日逐股 `ts_code, trade_date, up_limit, down_limit` | **保留为权威源**；U-2 待 token |
| AkShare 1.20.65 | 是 | **否** | 6 个 `stock_zt_pool_*` **事件级**接口；源码扫描：`stock_zt_pool_previous_em/strong_em/sub_new_em/zbgc_em` 含「涨停价」列（**仅事件子集**），`stock_zt_pool_em/dtgc_em` 不含限价列；**无全市场逐日 `up_limit/down_limit`** | 仅可作**子集/事件级抽查**；不作主源 |
| Baostock | 是 | **否** | 仅 OHLCV + 基础财务；无涨跌停价字段 | 不适用 |
| JoinQuant `jqdatasdk` | 否（需账号） | **是**（`high_limit/low_limit`） | `get_price` 支持 `high_limit` / `low_limit`；需 JQ 账号与额度 | 非免注册开源；不引入 |
| efinance / adata 等 Eastmoney 封装 | 是 | **否** | 与 AkShare 同类，事件/快照级 | 不适用 |

> 证据等级：**E1（源码级）**——AkShare 1.20.65 wheel（1,146,639 B）解包 **380 个 `.py`**：`up_limit/down_limit` 仅命中 `futures/futures_comm_js.py`（期货手续费），股票限价 **0 命中**；`high_limit/low_limit` **0 命中**；函数名含 `limit/zt_pool` 的仅 6 个 `stock_zt_pool_*` 事件池接口；其中 4 个含「涨停价」列（子集），`stock_zt_pool_em/dtgc_em` 不含限价列。版本与安装源亦为 E1（PyPI JSON）；`requires_python >=3.11.5`，本机 base Python **3.13.5** 满足；但「可安装」≠「有全市场限价表」。

**② Tushare 配置保留（不落 token）**

- 端点：`POST https://api.tushare.pro`；`api_name="stk_limit"`。
- 字段：`ts_code, trade_date, up_limit, down_limit`（可加 `exchange`）。
- 鉴权：环境变量 `TUSHARE_TOKEN` 或 `~/.tushare/token`；**本文件与仓库不写入真实 token**。
- 客户端：HTTP 直连即可（§5.6）；`tushare==1.4.29` 可选；token 需具备 `stk_limit` 点数权限。
- 升级触发：token 到位 → C 批外部对拍（V-8 ≥99.9%）→ D5 前置 `stk_limit`。

**③ Tushare 格式 mock 干跑（plumbing test）**

- 构造：本地真实 `close/adj` × 6 只（主板 600519/600036/000001、创业板 300750、科创板 688981、北交所 920002）× 3 个涨跌日 = **18 行**，字段严格按 `ts_code/trade_date/up_limit/down_limit`。
- 通路：mock → `(date × code)` 矩阵 → 与独立自算限价逐格对比。
- 读数：干净样本 **18/18 一致（100%）**；注入扰动均被检出——错价 **1/1**、缺行 **1/1**、多代码 **1/1**、重复键 **1/1**。
- 判定：**PLUMBING_OK**（数据通路与校验器可用）。
- **边界声明**：mock 由同一公式构造，100% 属构造必然，**不证明限价准确性**；准确性只能由 `stk_limit` 外部对拍（V-8）证明。
- 复跑口径：临时脚本 `%TEMP%\p021_probe\mock_stk_limit_dryrun.py` 运行后删除，不入仓。

**④ 对决策的影响**

- D2 维持 **`fallback_raw` + 披露**；不因开源替代而改变。
- D5 维持「token 到位前从停牌起」；`stk_limit` 为条件性升级。
- C 批维持**内部一致性对拍**；AkShare 事件池（4 个子集含「涨停价」）为可选子集抽查（需联网、非阻断）；V-8 留待 token。
- 未新增开放项：U-2 仍为「已验证不可得」，开放项仅 U-4。

---

## 6. 对设计的输入

### 6.1 五项决策（2026-11-23 用户已确认）

> 用户已确认全部五项；设计落点见 [DESIGN.md](./DESIGN.md)（v1.3 verified；含 D6 `execution_only_open` 降级）。

| # | 决策 | 推荐 | 备选 | 影响 | 置信度 | 触发条件 |
|---|---|---|---|---|---|---|
| D-1 | 执行时点 | `next_open` | `same_close`（需因子时点审计） | 封锁池 127,937→17,373；turnover 序列后移 1 日 | 中高 | 已确认 |
| D-2 | `adj` 缺口 | 原始昨收回退 + 披露 | 整日封锁 / `stk_limit` | 81 日 / 403,499 格；翻转约 18 买/155 卖 | 高 | 已确认（U-2 不可得 → `fallback_raw`） |
| D-3 | 北交所早期 | 规则前移 2020-07-27 + 早期 unknown | 裁剪 / 建模 NEEQ | 8,792 格（0.13%） | 高 | 已确认 |
| D-4 | 三态 | 只披露 + B 批敏感性 | 一字-only | 一字 5.46%/5.62% | 高 | 已确认 |
| D-5 | 数据顺序 | `stk_limit` → 停牌 → `adj` 回退 → ST → 退市 | 按缺口大小 | 成本/风险矩阵 | 中高 | 已确认（token 到位前从停牌起） |

### 6.2 关键约束（供 DESIGN 落 INV）

1. **IC/收益不变**：启用前后 5 个指标逐位相等（V-1）。
2. **默认路径不变**：`tradability_inputs=None` 时 TP6-11 与工件 SHA 逐位不变。
3. **全样本可构建**：2020-01-02 起含 296 只 bse 不抛错，`rule_gap_days` 有披露。
4. **执行时点一致**：`execution_timing` 与 `execute_at` 一致；不得保留「T 日 high/low」混合口径。
5. **未知限价策略可观测**：`unknown_policy ∈ {block, pass, fallback_raw}`；缺口日不得静默。
6. **分级披露**：`data_tier / missing_fields / bias_direction` 三键齐备；D1-D3 不得进入结论性收益。
7. **停牌语义**：`suspend=='S'` 才是停牌；`'R'` 可交易；缺列有披露。
8. **报告可序列化**：`report` 9 键恒 int；`meta` 的 `Counter` / numpy 标量需 JSON 往返测试。
9. **禁止默认 main 10%**：unknown 板块/日期必须走 unknown 分支，不得猜档位。
10. **`stock_return` 不作为 ref 主源**：缺口日无除权信息，且存在极端值（max 200,400%）。

### 6.3 风险与验证清单

| # | 风险 | 方向 | 验证 |
|---|---|---|---|
| 1 | 北交所早期规则缺失 → 构建失败 | 阻断 | V-9：全样本构建 |
| 2 | `adj` 缺口 → 不封锁 | 乐观（集中） | V-11：缺口日三策略对照 |
| 3 | 除权对齐机制已实现但数据缺口 | 乐观 | V-8：`stk_limit` 对拍 |
| 4 | 执行时点错配 | 双向 | V-10：两口径双跑 |
| 5 | 触及即封锁（三态） | 保守 | V-13：披露字段一致性 |
| 6 | 停牌 `'R'` / 缺列 | 双向 | V-12：S/R 用例 |
| 7 | 新股 `no_limit` 不分板块/日期 | 乐观 | V-14：板块/日期分支用例 |
| 8 | ST 名称推断 | 乐观（漏记） | V-15：`namechange` 交叉验证 |
| 9 | 空头腿未建模 | 乐观 | 报告 `leg_scope="long_only"` |
| 10 | 健康度/漂移翻转 | 中 | V-3/V-4：批跑翻转率 |

**V-1~V-15**（进入 CHECKLIST）：

| # | 验证项 | 判据 |
|---|---|---|
| V-1 | IC 类零变化 | 启用/不启用两跑，5 指标逐位相等 |
| V-2 | `turnover` 变化量级 | 均值/中位数/P95/最大 |
| V-3 | 健康度翻转率 | 翻转因子数 / 总因子数 |
| V-4 | 漂移翻转率 | 同上 |
| V-5 | 报告可序列化 | `json.dumps(result['tradability'])` 成功 |
| V-6 | 消融 trivial 判定 | 单臂前后一致或给出解释 |
| V-7 | 性能预算 | 构建 ≤30 s、峰值 ≤1 GB |
| V-8 | 限价对拍 | 与 `stk_limit` 一致率 ≥99.9% |
| V-9 | 全样本可构建 | 含 bse 2020 不抛错，`rule_gap_days` 披露 |
| V-10 | 执行时点一致 | `execution_timing` 与 `execute_at` 一致 + 双跑 |
| V-11 | 未知限价策略 | 缺口日按 `unknown_policy` 执行 |
| V-12 | 停牌语义 | `'R'` 可交易；缺列披露 |
| V-13 | 三态披露 | `blocked_buy ≤ up_touch_cells`，一字数披露 |
| V-14 | `no_limit` 分支 | 主板 2023-04-10 前 / 北交所仅首日 |
| V-15 | ST 交叉验证 | `namechange` 与名称推断差异清单 |

### 6.4 未决项登记（四元块）

- **U-1 收益层是否纳入 P-021**
  - **判据**：`long_short_returns` / `spread` 是否改用 effective 权重
  - **触发条件**：用户要求「可交易净收益」口径
  - **当前倾向**：先只启用证据层（turnover + 报告），收益层单独立项
  - **证据等级**：E1（当前代码不改收益）

- **U-2 `stk_limit` 可得性**
  - **判据**：能拉取 2020-01-02~2026-01-30 并与自算限价对拍 ≥99.9%
  - **触发条件**：用户提供 token 时（当前环境已于 2026-11-23 验证为不可得，见 §5.6）
  - **当前倾向**：**已验证不可得 → 走 `fallback_raw`**；token 到位后切 `stk_limit` 并补 V-8；已检索开源替代，无免注册全量源（§5.7）
  - **证据等级**：E1（§5.6 九项检查：包/环境变量/文件/缓存/凭据/网络/接口/安装源）+ E1/E2（§5.7 替代源对比与 mock 干跑）

- **U-3 缺口日除权密度**
  - **判据**：用 `stk_limit`/公告表核验 81 日实际除权事件数与判定翻转数
  - **触发条件**：拿到权威限价表或公告表
  - **当前倾向**：翻转 <200 格，回退可接受；缺口日不含 6-7 月分红高峰
  - **证据等级**：E1（36 格下界）+ E0（外推）

- **U-4 因子时点**
  - **判据**：逐因子标注数据截止日，证明 T 日收盘前可得
  - **触发条件**：仅当 D1 改选 A（`same_close`）
  - **当前倾向**：选 B（`next_open`）则不需要
  - **证据等级**：E0

- **U-5 NEEQ 2020-07-27 前逐股交易方式**
  - **判据**：逐股确认竞价/做市
  - **触发条件**：仅当要把 8,792 格从 unknown 升级为规则判定
  - **当前倾向**：维持 unknown + 披露
  - **证据等级**：E2（规则）+ E0（逐股方式）

- **U-6 分级阈值 99%**
  - **判据**：`adj/name/suspend` 覆盖率实测与 D0 稳定性
  - **触发条件**：`stk_limit` 对拍完成后
  - **当前倾向**：沿用 99% 建议值，按覆盖率分层披露
  - **证据等级**：E0

- **U-7 批量面板缓存粒度**
  - **判据**：构建耗时与内存
  - **触发条件**：单批构建 >30 s 或峰值 >1 GB
  - **当前倾向**：按日期区间缓存一次，逐因子 reindex
  - **证据等级**：E0

- **U-8 D1-D3 是否只作敏感性**
  - **判据**：对拍一致率与降级口径差异
  - **触发条件**：C 批对拍完成后
  - **当前倾向**：只作敏感性，不进结论性收益
  - **证据等级**：E0

- **U-9 报告持久化（Counter/NaN/numpy 标量）**
  - **判据**：`json.dumps` / 缓存往返成功
  - **触发条件**：DESIGN 定稿前
  - **当前倾向**：`meta` 的 `Counter` 转 `dict`，numpy 标量转 Python 原生
  - **证据等级**：E0

### 6.5 建议批次切分

| 方案 | 范围 | 风险 | 产出 |
|---|---|---|---|
| **C 对拍** | `stk_limit` 抽样对拍 + 差异清单（含 81 缺口日/除权日/ST/北交所） | 低 | 一致率报告，作为 A 的前置 |
| **A 证据层** | 数据装载 + 引擎开关 + turnover/报告落盘 | 中 | 可复跑的可交易性证据读数 |
| **B 收益层** | A + `long_short_returns` 改用 effective 权重 | 高 | 净收益口径，单独立项 |

> **C 批降级（U-2 不可得时）**：改为**内部一致性对拍**——`ref_ret` vs `_ref_from_adj`（99.86%/99.91%/92.7%）+ 除权/ST/北交所规则边界用例；V-8 外部一致率留待 token 到位。

**顺序**：C → A；B 单独立项。首批必须先修 **bse 早期规则**（解阻断）与 **停牌 `'S'` 映射**；`adj` 缺口用回退 + 披露缓解。

---

## 7. 参考文献

> 完整 ID / 层 / 日期 / 状态见 §5.1；此处按主题列条目，未重复验证细节。

**官方规则**

1. 上交所交易规则（2026 修订）—— 除权参考价、风险警示板：https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml
2. 深交所交易规则 4.4.2 —— 除权参考价：https://www.szse.cn/disclosure/notice/general/t20060515_499577.html
3. 北交所交易规则 4.3.2 —— 除权参考价：https://www.bse.cn/jygl_list/200028217.html
4. 证监会法规详情 第七条 —— 风险警示/退市整理 0.01 元：https://neris.csrc.gov.cn/falvfagui/rdqsHeader/mainbody?navbarId=3&secFutrsLawId=66010d2fe45148d09ba2eb3e1bbbbe33
5. 证监会法规详情 第七十四条 —— NEEQ 竞价 −50%/+100%：https://neris.csrc.gov.cn/falvfagui/rdqsHeader/mainbody?navbarId=3&secFutrsLawId=40b7025332804891a7a6f6c7b0595828
6. 全国股转《新三板投资者手册》：https://www.neeq.com.cn/uploads/1/file/public/202006/20200605104834_4kiddpghe7.pdf
7. 全国股转《股票交易规则》第九十一条：https://www.neeq.com.cn/class_d/200011897.html
8. 中证网：精选层 7 月 27 日开市：https://www.cs.com.cn/xwzx/hg/202007/t20200723_6079034.html
9. 深交所：退市整理股票涨跌幅：http://www.szse.cn/investor/institute/rules/t20231228_605143.html
10. 上海证券报：2026-07-06 主板 ST 5%→10%：http://paper.cnstock.com/html/2026-07/07/content_2240331.htm
11. 证监会：暂停转融券业务（2024-07-10）：https://www.csrc.gov.cn/csrc/c100028/c7493852/content.shtml
12. 证监会：全面注册制答记者问：http://www.csrc.gov.cn/csrc/c100028/c7047624/content.shtml
13. 中证网：主板交易新规（2023-04-10）：https://www.cs.com.cn/gppd/gsyj/202304/t20230410_6335974.html
14. 上交所风险警示板页面：http://www.sse.com.cn/disclosure/listedinfo/riskplate/

**数据源与平台文档**

15. Tushare `stk_limit`：https://tushare.pro/document/2?doc_id=183
16. Tushare `suspend_d`：https://tushare.pro/document/2?doc_id=214
17. Tushare `namechange`：https://tushare.pro/document/2?doc_id=100
18. Tushare `limit_list_d`：https://tushare.pro/document/2?doc_id=298
19. Qlib Workflow（`deal_price`）：https://qlib.readthedocs.io/en/stable/component/workflow.html
20. RiceQuant 回测（撮合基准）：https://www.ricequant.com/doc/quant/backtest
21. RQAlpha 基础 API：https://rqalpha.readthedocs.io/zh-cn/develop/api/base_api.html
22. JoinQuant API PDF：https://cdn.joinquant.com/help/img/JoinQuantAPI.pdf
23. Qlib 数据组件（NameDFilter）：https://qlib.readthedocs.io/en/latest/component/data.html

> 开源替代（U-2 补充，§5.7）：AkShare 股票数据文档 https://akshare.akfamily.xyz/data/stock/stock.html ；Baostock 官网 http://www.baostock.com/ ；JoinQuant 见第 22 条。

**社区**

24. 腾讯云：回测涨停判断：https://developer.cloud.tencent.com/article/2773854
25. 华为云：涨跌停/停复牌处理：https://bbs.huaweicloud.com/blogs/517427
26. 迪雅数据：涨停价四舍五入：https://www.diyadata.cn/guide/limit-up-price.html
27. 博客园：成交/涨跌停用不复权真实价：https://www.cnblogs.com/quantlab-notes/p/23530463
28. 华安证券：换手板/一字板统计（提纲 C-5，无公开链接；摘要级）。

**学术**

29. 陆昌, 刘洋, 杨晓光 (2021). 基于反事实模拟的中国股市涨跌停板磁吸效应研究. 《计量经济学报》1(1):217-232. DOI 10.12012/2020-0008-16（✅ 期刊官网全文页）
30. Cho, D.D., Russell, J., Tiao, G.C., Tsay, R. (2003). The magnet effect of price limits: evidence from high-frequency data on Taiwan Stock Exchange. *Journal of Empirical Finance* 10(1-2):133-168. DOI 10.1016/S0927-5398(02)00024-5（✅ Crossref）
31. Wan, Y.-L., Wang, G.-J., Jiang, Z.-Q., Xie, W.-J., Zhou, W.-X. (2018). The cooling-off effect of price limits in the Chinese stock markets. *Physica A* 505:153-163. arXiv:1803.09422（✅ arXiv API）
32. Qiao, K., Dam, L. (2020). The overnight return puzzle and the "T+1" trading rule in Chinese stock markets. *Journal of Financial Markets* 50:100534. PII S1386418120300033（✅ Crossref；期刊名已订正）
33. Wu, Y., Qin, F. (2015). Do We Need to Recover T+0 Trading? Evidence from the Chinese Stock Market. *Emerging Markets Finance and Trade* 51(6):1084-1098. DOI 10.1080/1540496X.2015.1080495（✅ Crossref）

---

## 8. 附录 A：五份源文档映射

| 源文档 | 版本 | 覆盖内容 | 本文件落点 |
|---|---|---|---|
| [调研提纲](../../docs/research/RESEARCH_TRADABILITY_PRODUCTION_ENABLEMENT_OUTLINE.md) | v0.4 | RQ-A1~E2、现状基线、S1-S13、G-1~G-6、批次切分 | §1、§3、§4.6、§6.5 |
| [数据分级与降级](../../docs/research/RESEARCH_TRADABILITY_DATA_TIERS_AND_DEGRADATION.md) | v1.0 | D0-D5、降级矩阵、除权实测、社区缺失实践 | §4.2、§4.5 |
| [影响面报告](../../docs/research/RESEARCH_TRADABILITY_PRODUCTION_IMPACT_REPORT.md) | v1.2 | R-1~R-10、层×变化、口径风险 1-12、V-1~V-13 | §4.1、§6.3 |
| [未决事项专项验证](../../docs/research/RESEARCH_TRADABILITY_OPEN_ITEMS_VERIFICATION.md) | v1.0 | O-1~O-11、三态、`adj` 缺口集中度、bse 硬失败、`execute_at` | §4.3、§4.5 |
| [五项决策锚点](../../docs/research/RESEARCH_TRADABILITY_DECISION_ANCHORS.md) | v1.1 | D1-D5、F1/F2/F4 表、充分性自检、U-6~U-9 | §4.4、§5、§6.1 |

> 源文档保留为**证据附录**：包含更细的推导、探针读数与历史版本。冲突时以本文件 §4/§6 为准；本文件未新增实测数据。

---

## 9. 附录 B：探针与复跑口径

1. **限价**：`ref = prev × adj[t-1] / adj[t]`（half-up 到分）；`up = half_up(ref×(1+pct))`，`down = half_up(ref×(1−pct))`。
2. **精确触板**：`绝对差(high, up) <= eps`（卖侧 `绝对差(low, down) <= eps`）。
3. **引擎触板**：`high >= up - eps`（卖侧 `low <= down + eps`）。
4. **一字**：`high == low` 且触板。
5. **三态**：一字 / 非一字·开盘涨停（`open >= up - eps`）/ 非一字·开盘未涨停；收盘封板 `close >= up - eps`，炸板 `close < up - eps`。
6. **次日开盘**：`open[t+1] >= up[t+1] - eps`（卖侧 `<= down[t+1] + eps`），要求 `t` 与 `t+1` 均可计算。
7. **缺口回退**：`ref = prev`；`ref_ret = close / (1 + ret/100)`（`ret` 为百分数）。
8. **样本**：`adj` ∩ OHLC = 1394 日；缺口日 81 日单列；限价按板块名义档位，未细分 ST/创业板 2020/低价股。
9. **Tushare mock 干跑（§5.7）**：6 只 × 3 个涨跌日 = 18 行，字段 `ts_code/trade_date/up_limit/down_limit`；mock 由 `ref = prev×adj[t-1]/adj[t]` + 板块档位构造；校验器检查缺列/重复键/非正限价/`up<down`，并与自算逐格对比；扰动注入（错价 ±0.10、删行、多代码、重复键）验证可检出。

> 探针脚本为一次性文件，已删除；按上述公式可从 `E:\Ashare_data\market_data` 复跑。关键读数见 §4.5。

---

**Review 签字**: Step 2 Review **PASS**（自查·单视角，RULE-4；记录见 §5.5） 日期: 2026-11-23
