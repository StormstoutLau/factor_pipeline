# tradability 生产启用 — 影响面报告

> **版本**: v1.2（2026-11-23；v1.1→v1.2 按[五项决策锚点 v1.0](RESEARCH_TRADABILITY_DECISION_ANCHORS.md)修订 §4 风险 #2/#4 处置口径并补链接；v1.1 = 增补未决事项专项验证的 R-9/R-10、§4 六条口径风险、V-9~V-13 与构建门禁）
> **性质**: 影响面报告（基于 [调研提纲 v0.4](RESEARCH_TRADABILITY_PRODUCTION_ENABLEMENT_OUTLINE.md) + [补充调研 v1.0](RESEARCH_TRADABILITY_DATA_TIERS_AND_DEGRADATION.md) + [未决事项专项验证 v1.0](RESEARCH_TRADABILITY_OPEN_ITEMS_VERIFICATION.md) + [五项决策锚点 v1.1](RESEARCH_TRADABILITY_DECISION_ANCHORS.md)）；**不实施**
> **结论等级**: E1 = 代码/数据实测；E2 = 官方规则；E3 = 社区二手；E0 = 待测
> **一句话**: 启用 tradability **不改变任何 IC/收益读数**，只改变 `turnover` 并新增报告块；真正的影响来自 `turnover` 向下游健康度/漂移的传导，以及数据分级缺失带来的**乐观偏差**。
> **已收敛（2026-11-23）**: 本报告为证据附录；P-021 决策真值源见 [spec/p021-tradability-production-enablement/RESEARCH.md](../../spec/p021-tradability-production-enablement/RESEARCH.md)（v1.1 verified）。

---

## §1 结论摘要

| # | 结论 | 等级 |
|---|---|---|
| R-1 | 启用后 `rank_icir / pearson_icir / hit_rate / spread / long_short_returns` **逐位不变**（这些指标不经过 positions） | E1 |
| R-2 | 唯一数值变化是 `turnover`（多头腿推进、空头腿透传），并新增 `result['tradability']` 块 | E1 |
| R-3 | `turnover` 是健康度拥挤度与漂移特征的输入 → **健康度/漂移判定会变**，属中风险，需阈值敏感性 | E1 |
| R-4 | 收益层未接：`long_short_returns` 仍用因子秩与 fwd return，**不代表可交易净收益** | E1 |
| R-5 | 生产调用图**零接线**：管道只传 close，批量运行器按逐因子交集切片 | E1 |
| R-6 | 本机数据接近 D0，但有两个洞（`adj` 缺 81 日、`name` 缺最后 1 日）；若按字段缺失降到 D1-D3，偏差方向均为**乐观** | E1 |
| R-7 | 口径误差量级：除权不对齐 → 主板除权日涨停漏判 **206/369（55.8%）**；固定 0.095 阈值 → 误判 **26,029 格** | E1 |
| R-8 | 默认路径（`tradability_inputs=None`）有 TP6-11 字面量锁定，启用必须另建端到端门禁 | E1 |
| R-9 | 「触及即封锁」是 DESIGN §14.4 的有意裁决，但代价首次量化：一字板仅占触板格 **5.62%**（6,512/115,923），**94.38%** 的触板格被保守封锁 | E1 |
| R-10 | **启用前置阻断**：本地面板含 296 只北交所映射股票、起始 2020-01-02，而 `bse` 规则自 2021-11-15 起 → `_pct_matrix` 首日抛 `ValueError`，全样本构建不可用 | E1 |

---

## §2 影响面总表

| 层 | 启用后变化 | 量级/方向 | 证据 | 门禁 |
|---|---|---|---|---|
| **指标：IC 类** | 无 | 0 | engine.py L271-283（不读 positions） | 端到端双跑比对（V-1） |
| **指标：turnover** | 多头腿被限价/停牌/一字板推进后重算 | 待测，预期上升（被封锁权重不交易）+ 现金拖累 | engine.py L285-303 | 分布/均值/极值对照（V-2） |
| **报告** | 新增 `tradability{report(9 int), meta(13), 4 口径键}` | 每因子 +1 块 | engine.py L304-311 | 键集合与类型断言 |
| **持久化** | JSON/缓存多一层嵌套；`meta.board_counts` 为 Counter | 体积增 ~KB/因子 | 待测 | 往返序列化（V-5） |
| **健康度** | 拥挤度分位变化 → 结论可能翻转 | 中 | health_bridge L121-125/L187-190 | 翻转率统计（V-3） |
| **漂移** | 漂移特征变化 → 裁决可能翻转 | 中 | unified_drift L266 | 翻转率统计（V-4） |
| **消融** | `turnover` 语义变 → trivial/BH 判定可能变 | 中 | scripts/run_ablation* | 单臂复跑（V-6） |
| **批量/性能** | 面板构建 1 次 + 逐因子 reindex | 构建 O(T×N)；内存 1475×5688×8B×~6 ≈ 400 MB | 本机形状实测 | 计时/峰值（V-7） |
| **默认路径** | 无 | 0 | TP6-11 | 既有测试 + 工件 SHA |
| **口径** | 除权/ST/停牌/退市规则误差 | 见 §3/§4 | 本机实测 | 对拍（V-8） |

### 2.1 指标层（最关键）

```
positions ──启用──> apply_tradability ──> effective_w ──> compute_turnover
rank_ic / pearson_ic / hit_rate / spread / ls_returns  ← 不经过 positions
```

- 因此「启用会不会改变因子排名」的答案是**不会**；改变的是「同一排名下的换手与可交易证据」。
- 这决定了批次定位：**证据层启用（方案 A）**，不是收益层（方案 B）。

### 2.2 报告层

- `report` 9 键恒 `int`（`blocked_buy/blocked_sell/suspended/limit_unknown/one_word_up/one_word_down/...`）。
- `meta` 13 键含 `Counter(str→int)`、int、str；`board_counts` 与 `st_date_unverified` 需确认 JSON 往返。
- 新增键对 `summary()`（只取 4 标量 + mean IC）**无影响**；但直接 dump 原始 results 的脚本需确认。

### 2.3 下游传导

| 下游 | 用 `turnover` 做什么 | 启用后风险 |
|---|---|---|
| `health_bridge` | 拥挤度指标 → 健康分/结论 | 分位阈值未针对「可交易口径」标定，可能整体下移 |
| `unified_drift` | 漂移特征输入 | 特征分布变化 → 裁决翻转 |
| 消融脚本 | summary 的 `turnover` 字段 | trivial 判定可能变化 |

### 2.4 批量与性能

- 面板构建：1475 日 × 5688 只 × 6 个 float64 矩阵 ≈ **400 MB**，加 name/suspend 对象矩阵更高 → 必须**按批次构建一次并缓存**，不可逐因子重建。
- `parallel_runner` 逐因子按 `intersection` 重切片；面板必须逐因子 reindex，否则形状校验直接抛错（engine L105-106 → `_validate_tradability_inputs`）。

---

## §3 数据分级对影响面的调节

| 级别 | 对指标层 | 对报告层 | 对结论可信度 | 必须披露 |
|---|---|---|---|---|
| D0 完整 | turnover 可解释 | 完整 9 键 | 可用于证据结论 | `data_tier="D0"` |
| D1 缺 adj | turnover 在除权日偏乐观 | 完整 + `price_basis="raw_close"` | **不可用于结论**；仅敏感性 | `exdiv_unadjusted_days` |
| D2 缺 ST | ST 限价过宽 → turnover 偏乐观 | 完整 + `st_assumed_cells` | 同上 | `st_assumed_cells` |
| D3 缺停牌 | 停牌日被当可交易 | 完整 + `suspend_unmodeled` | 同上 | `inferred_suspended_cells` |
| D4 缺上市日 | 新股前 5 日被当有限制 | 完整 + `ipo_unmodeled` | 偏差保守，可接受 | `ipo_unmodeled` |
| D5 仅 close | 不启用 | 无块 | 不可用 | `data_tier="unavailable"` |

- 本机现状：`adj` 缺 81/1475 日（5.5%）、`name` 缺 2026-01-30 → 严格判定落在 **D1**；若逐格 NaN 可容忍（`limit_unknown` 承载），可按 D0 运行并附缺口披露。
- **裁决点**：覆盖率阈值（建议 99%）与「逐格缺失 vs 整列缺失」的区分方式，需在 DESIGN 定稿。

---

## §4 口径风险清单（按影响排序）

| # | 风险 | 实测 | 方向 | 处置 |
|---|---|---|---|---|
| 1 | **北交所早期规则缺失** | 296 只 bse × 2020-01-02 → 构建抛 `ValueError`（`bse` 规则自 2021-11-15 起） | **阻断** | 补精选层 30%（2020-07-27 起）+ 早期 unknown 模式 |
| 2 | **`adj` 缺 81 日（5.49%）**：缺口日 `ref=NaN` → 全量 `limit_unknown` → 不封锁 | 缺口日约 10,366 个跌停触板（下限）；三大跌停日 2025-04-07 / 2020-02-03 / 2024-02-05 全在缺口日（占缺口日跌停触板 86.5%） | **乐观（集中）** | 优先 `stk_limit`；否则原始昨收回退 + `ref_fallback_days` 披露（决策锚点 D2；`stock_return` 不能填缺口） |
| 3 | 除权参考价未对齐（机制已实现，缺口见 #2） | 主板除权日限价错 62.3%；涨停漏判 55.8% | 乐观 | 保留 `_ref_from_adj`；按 #2 补数据 |
| 4 | **`execute_at` 声明未消费**；`open_`/`volume` 未参与判定 | 主板 90.7% 触板格在次日开盘口径下本可成交；反向漏封 0.150%（卖出侧 0.195%） | **双向** | 推荐实现 `next_open`（仓库 C9/C10；决策锚点 D1）；封锁池 127,937→17,373 |
| 5 | 触及 vs 一字未区分（DESIGN §14.4 有意裁决） | 一字 5.62%（精确相等）/ 5.46%（引擎 `>=`），约 94% 触板格被过度封锁 | **保守** | 保持口径 + 披露 `up_touch_cells / up_touch_one_word_cells` |
| 6 | 停牌 `'R'` 复牌日被 `bool()` 当停牌；相对 close 缺 7 列 | `'R'` 2,625 格过度封锁；7 列 → 9,758 格永不判停牌 | 双向 | 显式 `suspend=='S'`；披露 `suspend_resume_cells / suspend_missing_columns` |
| 7 | 新股前 5 日 `no_limit` 不分板块/日期 | 2023-04-10 前主板（首日 44%/36%、第 2-5 日 ±10%）与北交所（仅首日无限制）被过度放宽 | 乐观 | `no_limit` 按板块 + 日期分支 |
| 8 | 缺独立 ST 表（名称推断） | ST 格 2.85%（1393 日 × 5688 列口径；1474 日口径 2.97%）；`st_date_unverified` 只计数 | 乐观（漏记） | `namechange` 构造逐日面板 |
| 9 | 缺退市公告表 | 整理首日 `no_limit` 已覆盖；名称缺失 1 日 → 状态丢失 | 偏保守 | 接公告表；补 `name_missing_days` 披露 |
| 10 | 固定收益率阈值替代限价 | 0.095 误判 26,029；0.10 漏判 38,449 | 双向（净高估涨停） | 禁止作为主路径 |
| 11 | 空头腿未建模 | `short_leg_unmodeled=True`；融券制度 2023-10~2024-07 持续收紧 | 乐观 | 维持 `leg_scope="long_only"` 披露 |
| 12 | 低价股「涨跌幅 0.01 元」 | 规则已实现但两处调用未传 `is_st`；实测 `prev<0.1` 的 ST 仅 1 格 | 可忽略 | 接线或显式删参；补 0.05 元退市整理档 |

---

## §5 待验证清单（进入 DESIGN/CHECKLIST 的输入）

| # | 验证项 | 判据 | 方法 |
|---|---|---|---|
| V-1 | IC 类零变化 | 启用/不启用两跑，5 指标逐位相等 | 小样本端到端 |
| V-2 | turnover 变化量级 | 输出均值/中位数/P95/最大 | 全样本前后对照 |
| V-3 | 健康度翻转率 | 结论翻转因子数 / 总因子数 | 批跑对照 |
| V-4 | 漂移翻转率 | 同上 | 批跑对照 |
| V-5 | 报告可序列化 | `json.dumps(result['tradability'])` 成功 | 单元测试 |
| V-6 | 消融 trivial 判定 | 单臂前后结论一致或给出解释 | L1-L4 复跑 |
| V-7 | 性能预算 | 构建 ≤30 s、峰值 ≤1 GB | 计时 + tracemalloc |
| V-8 | 限价对拍 | 与 `stk_limit` 一致率 ≥99.9% | 抽样 2 个月（含分红季） |
| V-9 | 全样本可构建 | 2020-01-02 起含 296 只 bse 不抛错，`rule_gap_days` 有披露 | 全样本构建 |
| V-10 | 执行时点一致 | `execution_timing` 与 `execute_at` 一致；两口径对照给出差异 | 单测 + 双跑 |
| V-11 | 未知限价策略 | 缺口日按 `unknown_policy` 执行（保守时封锁） | 构造 `adj` 缺口日用例 |
| V-12 | 停牌语义 | `'R'` 日可交易；缺 7 列有披露 | 构造 `S`/`R` 用例 |
| V-13 | 三态披露 | 报告块含触板总数与一字数，且 `blocked_buy ≤ up_touch_cells` | 端到端 |

---

## §6 建议门禁

1. **默认路径**：`tradability_inputs=None` 时 TP6-11 与工件 SHA 逐位不变（已有）。
2. **启用路径**：新端到端测试，断言 V-1（IC 不变）+ V-2（turnover 有变化）+ 报告键集合。
3. **分级**：D1-D5 各 1 例，断言 `data_tier`/`missing_fields`/`bias_direction`。
4. **口径**：V-8 一致率未达标前，只允许输出「证据层」结论，不得写收益结论。
5. **披露**：报告必须含 `price_basis / leg_scope / short_leg_unmodeled / turnover_basis` 四键（已实现）。
6. **构建**：全样本（2020-01-02 起非空 bse）构建必须成功，且 `execution_timing / unknown_policy / suspend_missing_columns` 三项披露齐备（见[专项验证](RESEARCH_TRADABILITY_OPEN_ITEMS_VERIFICATION.md) §6.3）。

---

## §7 引用

- [调研提纲 v0.4](RESEARCH_TRADABILITY_PRODUCTION_ENABLEMENT_OUTLINE.md)（RQ-A1~E2、数据实测、社区案例）
- [补充调研 v1.0](RESEARCH_TRADABILITY_DATA_TIERS_AND_DEGRADATION.md)（D0-D5、缺失实践、除权专题）
- [未决事项专项验证 v1.0](RESEARCH_TRADABILITY_OPEN_ITEMS_VERIFICATION.md)（O-1~O-11、三态实测、次日开盘错配、bse 硬失败、外部证据表）
- [五项决策锚点 v1.1](RESEARCH_TRADABILITY_DECISION_ANCHORS.md)（D1-D5 量化对比、外部口径、推荐与「什么会改变推荐」、F4 表与充分性自检）
- 代码锚点：[engine.py](../../backtest/engine.py#L271-L332)、[tradability.py](../../backtest/tradability.py#L304-L397)、[tradability_inputs.py](../../backtest/tradability_inputs.py#L29-L162)、[health_bridge.py](../../backtest/health_bridge.py#L121-L190)、[unified_drift.py](../../backtest/unified_drift.py#L266)
