# tradability 未决事项专项验证（未实现 / 未建模 / 未覆盖）

> **版本**: v1.0（2026-11-23）
> **性质**: 补充调研 · 验证报告（**不实施**）
> **上游依据**: [调研提纲 v0.4](RESEARCH_TRADABILITY_PRODUCTION_ENABLEMENT_OUTLINE.md) /
> [数据分级补充调研 v1.0](RESEARCH_TRADABILITY_DATA_TIERS_AND_DEGRADATION.md) /
> [生产启用影响面报告 v1.2](RESEARCH_TRADABILITY_PRODUCTION_IMPACT_REPORT.md) /
> [五项决策锚点 v1.1](RESEARCH_TRADABILITY_DECISION_ANCHORS.md) /
> P-006 [DESIGN §14.4](../../spec/p006-tradability-engine-integration/DESIGN.md)
> **证据等级**: E1 = 本机代码/数据实测；E2 = 官方规则原文（页面/条款片段）；E3 = 社区二手；E0 = 待测
> **一句话**: 本轮 11 项未决事项中，**2 项属已实现未接线、1 项属设计有意裁决、1 项属已覆盖**；
> 同时新发现 **1 项硬阻断（北交所早期规则 → 构建器直接抛错）** 与 **1 项时点错配（`execute_at` 声明未消费）**，
> 以及 **`adj` 缺口恰好集中在三大跌停日**（缺口日承载约 19.2%-24.9% 的跌停触板格，取决于触及口径）。
> **已收敛（2026-11-23）**: 本文件为证据附录；P-021 决策真值源见 [spec/p021-tradability-production-enablement/RESEARCH.md](../../spec/p021-tradability-production-enablement/RESEARCH.md)（v1.1 verified）。

---

## §1 本轮结论与对上一轮的更正

### 1.1 结论摘要

| # | 结论 | 等级 |
|---|---|---|
| V-1 | 「触及即不可成交」是 DESIGN §14.4 的**有意裁决**，不是遗漏；代价首次量化：一字板仅占触及格 **5.62%**，即 **94.38%** 的触板格被保守封锁 | E1 |
| V-2 | `adj` 缺 **81/1475 日（5.49%）**；缺口日约 **7,448** 个涨停触板、**10,366** 个跌停触板；**2025-04-07 / 2020-02-03 / 2024-02-05** 三个极端跌停日全部落在缺口日 | E1 |
| V-3 | 缺口日跌停触板占全样本约 **19.2%（引擎）/ 24.9%（精确相等）**，而当前 `_ref_from_adj` 在缺口日返回 NaN → `judge=False` → **整日不封锁**（乐观偏差集中放大） | E1 |
| V-4 | **硬阻断**：本地面板含 296 只北交所映射股票、起始 2020-01-02，而 `bse` 规则自 2021-11-15 起 → `_pct_matrix` 在首日抛 `ValueError`，全样本构建不可用 | E1 |
| V-5 | `TradabilityPolicy.execute_at` **仅校验、从未消费**；`open_` / `volume` 只做形状校验；判定用 T 日 high/low 而默认语义是 T+1 开盘 → 时点错配 | E1 |
| V-6 | 次日开盘口径下：主板 **94,053/103,728（90.7%）** 触板格属「当前封锁但次日开盘可成交」；反向漏封 **6,502 格（0.150%）**；卖出侧漏封 **8,436 格（0.195%）** | E1 |
| V-7 | 停牌列 `'R'`（复牌）被 `bool()` 当作停牌 → **2,625 格**过度封锁；另有 **7 列**缺失 → 9,758 格永不判停牌（乐观，上界） | E1 |
| V-8 | 低价股「涨跌幅 0.01 元」规则**已实现但未接线**（两处生产调用点均未传 `is_st`）；实测仅 **1 格** `prev<0.1` 的 ST，影响可忽略 | E1 / E2 |
| V-9 | 退市整理首日 `no_limit` **已实现**（名称含「退」首日）；真正缺口是名称缺失日（2026-01-30）与无公告表交叉验证 | E1 |
| V-10 | 北交所/主板新股 `no_limit` 的前 5 日规则未按板块与日期分支：对 2023-04-10 前主板新股（首日 44%/36%、第 2-5 日 ±10%）与北交所（仅首日无限制）**过度宽松**（乐观） | E1 / E2 |

### 1.2 对上一轮措辞的更正（重要）

| 上一轮表述 | 复核结论 | 证据 |
|---|---|---|
| 「低价股 0.01 元细则未实现」 | **部分更正**：`compute_limits` 已实现该分支，但 `build_tradability_inputs` 与 `apply_tradability` 两处调用均未传 `is_st` → **已实现未接线**；且缺 0.05 元退市整理档 | [tradability.py](../../backtest/tradability.py#L160-L191)、[tradability_inputs.py](../../backtest/tradability_inputs.py#L131)、[tradability.py](../../backtest/tradability.py#L381) |
| 「退市整理首日未纳入 `no_limit`」 | **更正**：已纳入（`is_delisting` 首日置 `no_limit=True`）；且退市不套 ST 限价 | [tradability_inputs.py](../../backtest/tradability_inputs.py#L66-L102)、[tradability.py](../../backtest/tradability.py#L218) |
| 「触及 vs 一字三态未建模」 | **更正**：是 DESIGN §14.4 显式裁决「触及即不可成交」；缺的是**量化披露**与收益层敏感性 | [RESEARCH_SYNTHETIC_VALIDATION_TRACEABILITY.md](RESEARCH_SYNTHETIC_VALIDATION_TRACEABILITY.md#L590-L592) |
| 「ST 仅名称推断（2.97% 格）」 | **维持**，量化为 **2.85%**（口径为 1393 日 × 5688 列）；`st_overrides` 只统计不修正 | §4.6 |

---

## §2 方法与口径

### 2.1 代码锚点（本轮重读）

| 位置 | 事实 |
|---|---|
| [tradability.py L381-L386](../../backtest/tradability.py#L381-L386) | `compute_limits(prev_close[t], pct_t, ref=ref_t)` **未传 `is_st`**；`can_buy = ~susp & (~judge \| ~(high >= up - eps))` |
| [tradability.py L391-L397](../../backtest/tradability.py#L391-L397) | 一字板计数 = `judge & ~susp & high==low & \|high-up\|<=eps` |
| [tradability.py L234-L255](../../backtest/tradability.py#L234-L255) | `_ref_from_adj`：`adj` 单侧缺失 → `ref=NaN`（不回退原始昨收） |
| [tradability.py L316-L318](../../backtest/tradability.py#L316-L318) | `execute_at` 仅做合法性校验，循环体内无消费 |
| [tradability.py L458-L460](../../backtest/tradability.py#L458-L460) | `carried` = **最后一日**终态未平缺口数（快照，非累计流量） |
| [tradability_inputs.py L51](../../backtest/tradability_inputs.py#L51) | `suspend` 直接 `astype(bool)` → `'S'` 与 `'R'` 都是 True |
| [tradability_inputs.py L74-L102](../../backtest/tradability_inputs.py#L74-L102) | `no_limit`：上市后前 5 个交易日（不分板块/日期）+ 退市整理首日 |
| [tradability_inputs.py L104-L120](../../backtest/tradability_inputs.py#L104-L120) | `st_overrides` 只计算 `st_date_unverified`，不改变派生状态 |
| [engine.py L304-L311](../../backtest/engine.py#L304-L311) | 报告块 4 个口径键：`price_basis / leg_scope / short_leg_unmodeled / turnover_basis` |

### 2.2 探针口径（E1）

- **样本**：`stock_close/high/low/open/adj` 交集，**1394 个交易日**（2020-01-02 ~ 2026-01-30）× **5688 只**；`close` 本身 1475 日，交集损失 81 日全部来自 `adj`（`open/high/low` 无缺失，已核对）。
- **板块**：main 3360 / gemstar（创业板+科创板）2032 / bse 296，全部可映射，无 `unknown`。
- **限价口径**：按板块名义档位（main 10%、gemstar 20%、bse 30%），**未**细分 ST 5%（2026-07-06 前主板）与低价股 0.01 元规则 → 触板总量为**下限**。
  另有两处已知近似：① 创业板 2020-08-24 前实际为 10%，探针统一按 20% → 该段触板被**低估**；
  ② 退市整理期按板块普通档、未单列。主板一字占比（6.04%）受 ST 影响有限，作为稳健锚点。
- **三态定义**：一字 = `high==low==up`；非一字·开盘涨停 = `open>=up-eps` 且非一字；非一字·开盘未涨停 = `open<up-eps`；收盘封板 = `close>=up-eps`；炸板 = `close<up-eps`。
- **次日开盘口径**：对 `t` 与 `t+1` 都可计算的格，用 `open[t+1] >= up[t+1]-eps`（买）/`open[t+1] <= dn[t+1]+eps`（卖）判定「次日开盘是否已触板」；这是**报价可行性池**，未乘真实调仓 delta。
- **adj 缺口日**：以原始昨收近似限价（缺口日无法判断是否除权；除权日占比极低），结果记为**下限估计**。

---

## §3 未决事项总表

| # | 事项 | 类型 | 偏差方向 | 量级（E1） | 优先级 | 处置建议 |
|---|---|---|---|---|---|---|
| O-1 | 触及 / 打开 / 一字三态 | 已裁决未量化 | **保守** | 一字 5.62%（精确相等口径）/ 5.46%（引擎 `high>=limit-eps` 口径），约 94% 触板格被封锁 | P2 | 保持口径；新增披露键 + B 批敏感性 |
| O-2 | `adj` 缺 81 日 | 数据缺口 | **乐观** | 缺口日承载 19.2%-24.9% 跌停触板（取决于触及口径） | **P1** | 优先 `stk_limit`；否则原始昨收回退 + 披露（决策锚点 D2） |
| O-3 | 低价股 0.01 元 | 已实现未接线 | 双向（极少数） | ST 格 2.85%，其中 `prev<0.1` 仅 1 格 | P3 | 接线或删参数；补 0.05 元档 |
| O-4 | 退市整理 | 已覆盖·数据源弱 | 偏保守 | 名称缺失 1 日 | P2 | 接公告表；补 `name_missing_days` |
| O-5 | ST 仅名称推断 | 未覆盖（数据源） | 乐观（漏记） | ST 格 225,581（2.85%） | P2 | `namechange` 构造逐日面板 |
| O-6 | 空头腿未建模 | 未建模 | 乐观 | 券源/成本全忽略 | P2 | 维持 `long_only` 披露；B 批不做空 |
| O-7 | 停牌 `'R'` 语义 / 列集 | 语义缺陷 + 未覆盖 | 双向 | `'R'` 2,625 格；缺 7 列 | P2 | 显式 `suspend=='S'`；补列缺失披露 |
| O-8 | `execute_at` 未消费 | 未实现 / 口径错配 | **双向** | 主板 90.7% 过度封锁、0.150% 漏封 | **P1** | 裁决执行时点；实现或改名 |
| O-9 | 北交所早期规则 | 未覆盖 → **硬失败** | 阻断 | 296 只 bse × 2020-01-02 抛错 | **P1** | 补精选层规则 + 早期 unknown 策略 |
| O-10 | 开盘一字 vs 盘中封板 | 未建模（`open_` 未用） | 保守 | 开盘即涨停 11.65%（含一字） | P2 | 披露；分钟级验证列为可选 |
| O-11 | `carried` 键语义 | 文档-实现偏差 | 无（报告） | 终态快照 ≠ 累计顺延 | P3 | 文档勘误或改名 `unfilled_last_day` |

> 偏差方向不能相互抵消：O-1（保守）作用于「达标触板日的可交易判定」，O-2（乐观）作用于「81 个缺口日尤其是极端跌停日」，两者子集与日期均不重叠。

---

## §4 逐项证据

### 4.1 O-1 三态分布（E1）

| 板块 | 触板格 | 一字 | 一字占比 | 非一字·开盘涨停 | 非一字·开盘未涨停 | 收盘封板 | 炸板 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 主板 | 103,728 | 6,261 | 6.04% | 6,366 | 91,101 | 70,119（67.6%） | 33,609（32.4%） |
| 创业板+科创板 | 11,612 | 241 | 2.08% | 585 | 10,786 | 8,196（70.6%） | 3,416（29.4%） |
| 北交所 | 583 | 10 | 1.72% | 39 | 534 | 454（77.9%） | 129（22.1%） |
| **合计** | **115,923** | **6,512** | **5.62%** | **6,990（6.03%）** | **102,421（88.35%）** | **78,769（67.95%）** | **37,154（32.05%）** |

- 跌停侧：触板 31,205，一字 1,688（**5.41%**），开盘跌停 4,550（14.58%），收盘封死 17,133（54.9%），炸板 14,072（45.1%）。
- 与社区口径对照：腾讯云社区要求分「未触及 / 触及打开 / 全天一字」三态（提纲 S10）；华安证券口径「换手板 90.8% / 一字板 9.2%」（E3），与本仓「打开板 ≈94.4%」同量级。
- **裁决含义**：本仓「触及即封锁」对应的是「保守上界」，不是错误；但必须有字段披露，否则读者会把 `blocked_buy` 理解为「全部不可成交」。

### 4.2 O-2 除权对齐缺口（E1）

| 项 | 读数 |
|---|---:|
| `close` 交易日 | 1475 |
| `adj` 交易日 | 1394 |
| 缺口 | **81 日（5.49%）**，2020-01-10 ~ 2025-04-10 |
| 缺口日涨停触板（近似） | 7,448 |
| 缺口日跌停触板（近似） | **10,366** |
| 缺口日跌停触板占全样本 | **24.9%（精确相等，10,366/41,571）/ 19.2%（引擎，10,393/54,006）** |
| 缺口日涨停触板占全样本 | 6.0% |

缺口日按跌停触板排序（前 4 日合计 8,971 格 = 缺口日跌停触板的 86.5%）：

| 日期 | 跌停触板 | 涨停触板 |
|---|---:|---:|
| 2025-04-07 | 3,626 | 37 |
| 2020-02-03 | 2,593 | 74 |
| 2024-02-05 | 1,920 | 32 |
| 2024-02-06 | 832 | 307 |

- 机制：`_ref_from_adj` 在 `adj` 缺失处返回 NaN → `compute_limits` 置 `unknown` → `judge=False` → **既不封买也不封卖**；`limit_unknown` 只在「有调仓意图」时计数，不能反映「整日未判定」。
- 结论：这不是均匀的 5.5% 噪声，而是**集中命中限价约束最强的日子**。若按当前实现启用，跌停卖出约束在最需要生效的日期全部失效。

### 4.3 O-8 执行时点错配（E1）

| 口径 | 主板 | 创业板+科创板 | 北交所 |
|---|---:|---:|---:|
| 触板格（买） | 103,728 | 11,612 | 583 |
| 当前封锁但 `t+1` 开盘未触板（过度保守） | 94,053（90.7%） | 11,217（96.6%） | 565（96.9%） |
| 当前放行但 `t+1` 开盘已触板（漏封，占可交易格） | 6,502（0.150%） | 840（0.038%） | 256（0.109%） |
| `t+1` 开盘触板总格 | 15,903 | 1,200 | 270 |
| 卖出：当前封锁但 `t+1` 开盘未跌停 | 27,503（91.1%） | 893（89.4%） | 12（80.0%） |
| 卖出：当前放行但 `t+1` 开盘已跌停（占可交易格） | 8,436（0.195%） | 470（0.021%） | 109（0.046%） |

- `execute_at="next_open"` 是默认值，但判定使用 `t` 日 `high/low`；`open_`、`volume` 完全未参与。
- 因此当前实现的实际语义是「以 T 日报价判定 T 日收盘调仓」，与字段声明不一致。两种修法二选一：
  1. **改语义**：声明 `same_close`，删除 `next_open` 选项与误导性注释；
  2. **改实现**：判定平移到 `t+1`（用 `open/high/low[t+1]`），并处理最后一日与 `t+1` 停牌/无报价。
- 上面两组数说明：修法不同，偏差方向相反，必须先裁决再谈「启用后 turnover 变化」。

### 4.4 O-9 北交所早期规则硬失败（E1）

复现（不依赖包导入，直接加载模块）：

```
_pct_matrix(np.array(['bse']), np.zeros((1,1),bool), None, ['2020-01-02'])
ValueError: 无涨跌幅规则: board=bse is_st=False date=2020-01-02
```

- 本地面板：`bse` 映射 **296 只**，`close` 起始 **2020-01-02**；规则表 `bse` 仅自 **2021-11-15** → 全样本 `build_tradability_inputs` 首日即抛错。
- 外部事实：精选层 **2020-07-27** 开市，涨跌幅 **30%**、成交首日不设涨跌幅（E2，全国股转/中证网）；北交所 2021-11-15 开市沿用 30%。
- 即使把 `bse` 规则起点前移至 2020-07-27，仍有 2020-01-02 ~ 2020-07-24 约 140 个交易日的空档；这些日期对应新三板基础层/创新层，不能按 A 股连续竞价 30% 处理。
- 建议：`rule_pct` 增加「无规则 → unknown」的宽松模式（当前是硬抛），并由构建器把该段标为 `limit_unknown` / `no_limit`，同时披露 `rule_gap_days`；严禁默认成 main 10%。

### 4.5 O-7 停牌语义（E1）

| 项 | 读数 |
|---|---:|
| `stock_suspend` 形状 | 1394 × 5681 |
| 非空取值 | `'S'` 17,669 / `'R'` 2,625 |
| 相对 `close` 缺失列 | 7 列（9,758 格） |
| `'R'` 被 `bool()` 判为停牌 | 2,625 格（0.033%） |

- `stock_suspend` 是 **'S'/'R' 事件表**（[RESEARCH_GOVERNANCE_BASE.md L244](RESEARCH_GOVERNANCE_BASE.md#L244)），不是逐日 0/1 状态；`astype(bool)` 把复牌日也变成停牌。
- 缺失 7 列被 reindex 为 False → 这 7 只股票永不判停牌（乐观上界 9,758 格）。
- 建议：显式 `suspend = (value == 'S')`；meta 增 `suspend_resume_cells / suspend_missing_columns`。

### 4.6 O-3 / O-5 ST 与低价股（E1）

| 项 | 读数 |
|---|---:|
| `stock_name` 形状 | 1393 × 6053（缺 2026-01-30） |
| ST 格 | 225,581（占 5688 列面板 **2.85%**） |
| ST 且 `prev_close < 0.1` 元 | **1 格** |
| `st_overrides` 作用 | 仅累计 `st_date_unverified`，不改正状态 |

- 低价股 0.01 元规则：`compute_limits(low_price_st_rule=True)` 已实现 `prev<0.1 → up=prev+0.01`，但生产两处调用均未传 `is_st` → 实际永不触发；影响仅 1 格，优先级 P3。
- 缺 0.05 元「退市整理」档：`compute_limits` 只有 ST 0.1 元分支，没有 `is_delisting & prev<=0.05 → 0.01 元` 分支（E2 条款见 §5）。
- ST 漏记（名称未及时变更）会把 5% 当 10% → 限价过宽 → 不封锁 → 乐观；`st_date_unverified` 已能提示偏差，但未进入报告块。

### 4.7 O-4 / O-6 / O-10 / O-11（简）

| # | 事实 | 影响 |
|---|---|---|
| O-4 | 退市状态由名称含「退」逐日派生；首日 `no_limit=True`；退市不套 ST | 名称缺失日（1 日）退市状态丢失；无公告表交叉验证 |
| O-6 | 引擎 `effective = effective_long + min(positions,0)`；报告 `short_leg_unmodeled=True` | 空头假设无限融券；2023-10 至 2024-07 融券制度连续收紧（E2），实际券源与成本远劣于假设 |
| O-10 | `open_` 未参与判定；一字 5.62%，开盘即涨停 11.65% | 「开盘涨停但盘中打开」6,990 格在开盘瞬间买不到、盘中可能买到；当前一律封锁（保守），且无法区分 |
| O-11 | `carried` 只统计最后一日终态缺口 | 与 DESIGN §14.4「carried/deferred 计数」的措辞不完全一致，建议文档勘误 |

---

## §5 外部证据表

> 验证标记：**✅** = 本轮读到原文/条款片段；**⚠️** = 检索到官方页面或摘要，未逐字全文复核；**E1** = 本机实测。
> 社区证据的完整 13 条清单见[提纲 §5](RESEARCH_TRADABILITY_PRODUCTION_ENABLEMENT_OUTLINE.md#L130-L150)，本表只列本轮新增/复核项。

### 5.1 官方规则（E2）

| # | 来源 | 关键结论 | 支撑 | 验证 |
|---|---|---|---|---|
| E2-1 | [上交所交易规则（2026 修订）§4.4 风险警示板](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml) | 风险警示板/退市整理股票的适用范围与交易事项 | O-3/O-4 | ⚠️ |
| E2-2 | [证监会法规详情 第七条](https://neris.csrc.gov.cn/falvfagui/rdqsHeader/mainbody?navbarId=3&secFutrsLawId=66010d2fe45148d09ba2eb3e1bbbbe33) | 风险警示 5%，A 股前收 ≤0.1 元 → 0.01 元；退市整理 10%，前收 ≤0.05 元 → 0.01 元 | O-3 | ✅ 条款片段 |
| E2-3 | [证监会：暂停转融券业务（2024-07-10）](https://www.csrc.gov.cn/csrc/c100028/c7493852/content.shtml) | 转融券自 2024-07-11 暂停；融券保证金 80%→100%、私募 100%→120%，2024-07-22 起 | O-6 | ✅ 摘要 |
| E2-4 | [证监会全面注册制答记者问](http://www.csrc.gov.cn/csrc/c100028/c7047624/content.shtml) | 主板新股上市前 5 个交易日不设涨跌幅 | O-9/O-10 | ✅ 摘要 |
| E2-5 | [中证网：主板交易新规（2023-04-10）](https://www.cs.com.cn/gppd/gsyj/202304/t20230410_6335974.html) | 第 6 日起 10%；此前首日不高于发行价 144%、不低于 64% | O-9 | ⚠️ |
| E2-6 | [全国股转：精选层订单价格问答](https://www.neeq.com.cn/hot_qa/200008764.html) | 精选层 30% 涨跌幅限制 | O-9 | ✅ 摘要 |
| E2-7 | [中证网：精选层 7 月 27 日开市](https://www.cs.com.cn/xwzx/hg/202007/t20200723_6079034.html) | 精选层成交首日不设涨跌幅 | O-9 | ⚠️ |

### 5.2 学术（E3，均为摘要级）

| # | 文献 | 关键结论 | 支撑 | 验证 |
|---|---|---|---|---|
| A-1 | 涨跌停磁吸效应（中文期刊，DOI [10.12012/2020-0008-16](https://doi.org/10.12012/2020-0008-16)） | 跌停磁吸强于涨停；盘中接近强于开盘接近 | O-1/O-10 | ⚠️ |
| A-2 | Cho, Russell, Tiao & Tsay (2003), *J. Empirical Finance* 10(1-2):133-168，DOI [10.1016/S0927-5398(02)00024-5](https://doi.org/10.1016/S0927-5398(02)00024-5) | 台湾高频数据：价格接近限价时加速趋近（磁吸） | O-1/O-10 | ⚠️ |
| A-3 | [arXiv:1803.09422](https://arxiv.org/abs/1803.09422) | 涨跌停的冷却效应检验 | O-1 | ⚠️ |
| A-4 | *J. Banking & Finance* (2020), PII [S1386418120300033](https://www.sciencedirect.com/science/article/pii/S1386418120300033) | T+1 制度下隔夜收益折价（约 14 bps） | O-8 | ⚠️ |
| A-5 | “Do We Need to Recover T+0 Trading?”, *EMFT* (2015)，DOI [10.1080/1540496X.2015.1080495](https://doi.org/10.1080/1540496X.2015.1080495) | T+0/T+1 制度成本讨论 | O-8 | ⚠️ |
| A-6 | 深交所 T+1 制度研究报告（PDF） | T+1 对流动性与定价的影响评估 | O-8 | ⚠️ |

### 5.3 社区二手（E3）

| # | 来源 | 关键结论 | 支撑 | 验证 |
|---|---|---|---|---|
| C-1 | 腾讯云社区「回测涨停判断」 | 不能只用 `return>=0.1`；应分未触及/触及打开/全天一字三态 | O-1 | ⚠️（提纲 S10） |
| C-2 | Qlib `Exchange` | `limit_threshold=0.095` + `forbid_all_trade_at_limit` | O-1/O-3 | ⚠️（提纲 S1/S2） |
| C-3 | RQAlpha / RiceQuant 撮合 | 涨跌停/停牌拒单规则与容差实现 | O-1/O-4 | ⚠️（提纲） |
| C-4 | Tushare `suspend_d` / `namechange` / `stk_limit` | `S`-停牌 / `R`-复牌；ST 变更历史；逐日限价对拍源 | O-5/O-7 | ⚠️（提纲 S8/S9） |
| C-5 | 华安证券涨停统计 | 换手板 90.8% / 一字板 9.2% | O-1 | ⚠️（提纲） |

### 5.4 外部口径与本仓对照

| 维度 | 社区/官方常见做法 | 本仓现状 | 差异结论 |
|---|---|---|---|
| 触板可成交性 | 三态：未触及 / 触及打开 / 全天封死 | 二态：未触及 / 触及即封锁 | 本仓保守；需披露 |
| 未知限价 | 多数平台直接拒单或跳过 | `unknown → 不封锁`（乐观） | 与「保守证据层」定位冲突，需裁决 |
| 停牌事件 | `S` 停牌、`R` 复牌分开处理 | `bool()` 合并 | 复牌日被误封锁 |
| 除权限价 | 多数社区用固定阈值，不做除权对齐 | 已实现 `_ref_from_adj`（优于社区） | 方向正确；缺 `adj` 的日子反而退化 |
| 新股无涨跌幅 | 按板块/日期分支 | 全板块前 5 日 | 2023-04-10 前主板与北交所过度宽松 |

---

## §6 裁决建议

### 6.1 必须先裁决的五个问题（进入 DESIGN 的输入）

| # | 问题 | 选项 | 建议 |
|---|---|---|---|
| U-1 | 执行时点 | A `same_close` 改名；B 实现 `next_open` 判定；C 保留现状 + 披露 | **B**（仓库 C9/C10；A 需先做因子时点审计）；禁止 C |
| U-2 | 未知限价策略 | A 未知 → 封锁（保守）；B 未知 → 放行（现状）；C 原始昨收回退 + 披露 | **C**（证据见[决策锚点 D2](RESEARCH_TRADABILITY_DECISION_ANCHORS.md)）；有 `stk_limit` 时优先权威值 |
| U-3 | 北交所早期 | A 补精选层规则 + 2020-07-27 前 unknown；B 裁剪 2021-11-15 前区间；C 剔除 bse | **A**（保留样本），`rule_pct` 增宽松模式 |
| U-4 | 三态 | A 只披露；B 增 `limit_mode=one_word` 敏感性；C 改为可成交 | **A**（本批）+ **B**（B 批收益层） |
| U-5 | 数据补强顺序 | `stk_limit` → 停牌 → `adj` 回退 → ST → 退市公告 | 按「风险降低/成本」排序，见[决策锚点 D5](RESEARCH_TRADABILITY_DECISION_ANCHORS.md) |

> 五项已完成决策锚点补充调研（2026-11-23）：[RESEARCH_TRADABILITY_DECISION_ANCHORS.md](RESEARCH_TRADABILITY_DECISION_ANCHORS.md)。其中 **U-2 的推荐已由「未知即封锁」修正为「原始昨收回退 + 披露」**：81 日缺口共 403,499 格，`stock_return` 在缺口日退化为原始收益（无除权信息），回退的判定翻转仅约 18 买/155 卖，整日封锁属过度处置。

### 6.2 对 P-021 批次切分的影响

- **C 批（对拍）前置条件增加**：先修 O-9（否则全样本构建直接抛错），并把 O-2 缺口日纳入对拍样本（否则一致率会被缺口日拉低且无法解释）。
- **A 批（证据层）**：O-1/O-7/O-10 只需披露，不阻断；O-8 必须先裁决，否则 `turnover` 变化无法归因。
- **B 批（收益层）**：继续保持不做空（O-6）；三态敏感性（U-4 B）可作为收益层首个实验。

### 6.3 门禁增补（追加到影响面报告 §6）

1. **构建门禁**：全样本（2020-01-02 起，含 296 只 bse）`build_tradability_inputs` 必须成功返回，且 `meta.rule_gap_days` 有披露。
2. **时点门禁**：报告块必须含 `execution_timing`（`t_day_quotes` / `t_plus_1_open`），并与 `TradabilityPolicy.execute_at` 一致。
3. **未知限价门禁**：报告块必须含 `unknown_policy`（`block` / `pass` / `fallback_raw`）与 `limit_unknown_cells`（含非 busy 格）。
4. **停牌门禁**：`suspend_resume_cells` 与 `suspend_missing_columns` 必须披露。
5. **三态门禁**：`up_touch_cells / up_touch_one_word_cells` 必须披露（与 `blocked_buy` 并列），避免把保守上界读成真实不可成交。

---

## §7 引用

- [调研提纲 v0.4](RESEARCH_TRADABILITY_PRODUCTION_ENABLEMENT_OUTLINE.md)（RQ-A1~E2、13 条社区案例、缺口 G-1~G-6）
- [数据分级与降级 v1.0](RESEARCH_TRADABILITY_DATA_TIERS_AND_DEGRADATION.md)（D0-D5、无 ST/退市/限价表实践、除权专题）
- [生产启用影响面报告 v1.2](RESEARCH_TRADABILITY_PRODUCTION_IMPACT_REPORT.md)（R-1~R-10、层×变化总表、口径风险 1-12、V-1~V-13）
- 代码锚点：[tradability.py](../../backtest/tradability.py#L160-L191)、[tradability.py](../../backtest/tradability.py#L234-L255)、[tradability.py](../../backtest/tradability.py#L378-L461)、[tradability_inputs.py](../../backtest/tradability_inputs.py#L29-L162)、[engine.py](../../backtest/engine.py#L285-L332)
- 设计裁决：[RESEARCH_SYNTHETIC_VALIDATION_TRACEABILITY.md §14.4](RESEARCH_SYNTHETIC_VALIDATION_TRACEABILITY.md#L588-L592)（触及即不可成交）
- 数据语义：[RESEARCH_GOVERNANCE_BASE.md L244](RESEARCH_GOVERNANCE_BASE.md#L244)（`stock_suspend` 为 S/R 事件表）
