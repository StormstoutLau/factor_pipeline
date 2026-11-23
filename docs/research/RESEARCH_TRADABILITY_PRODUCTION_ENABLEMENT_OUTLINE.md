# tradability 生产启用 — 影响面与数据可得性调研提纲

> **版本**: v0.4（提纲；2026-11-23；v0.2 增补数据分级/降级/除权补充调研；v0.3 增补影响面报告并回填结论；v0.4 增补未决事项专项验证）
> **补充调研**: [RESEARCH_TRADABILITY_DATA_TIERS_AND_DEGRADATION.md](RESEARCH_TRADABILITY_DATA_TIERS_AND_DEGRADATION.md)（D0-D5 分级机制、无 ST/退市/限价表的社区实践、除权对齐实测误差）
> **影响面报告**: [RESEARCH_TRADABILITY_PRODUCTION_IMPACT_REPORT.md](RESEARCH_TRADABILITY_PRODUCTION_IMPACT_REPORT.md)（v1.2：影响面总表、数据分级调节、口径风险 1-12、V-1~V-15 验证清单、构建门禁）
> **未决事项专项验证**: [RESEARCH_TRADABILITY_OPEN_ITEMS_VERIFICATION.md](RESEARCH_TRADABILITY_OPEN_ITEMS_VERIFICATION.md)（O-1~O-11：三态实测、`adj` 缺口集中度、bse 硬失败、执行时点错配、停牌 `'R'` 语义、外部证据表）
> **性质**: **调研提纲（pre-Step 1）**——不是四件套，不构成 verified 调研；用于界定问题、盘点事实、预置检索式与验收门禁
> **依据**: P-006（v3.9.9 引擎接入）／P-020（v3.9.10 小口径收尾）已交付事实；本机数据实测（2026-11-23，数据根 `E:\Ashare_data`）
> **产出定位**: 事实基线 + 待答问题 + 社区案例初筛 + 建议批次切分（**不实施**；实施归后续 T1 批次）
> **批次登记**: [PROGRESS.md](../PROGRESS.md) **P-021（pending / P3）**
> **已收敛（2026-11-23）**: 本提纲为证据附录；P-021 决策真值源见 [spec/p021-tradability-production-enablement/RESEARCH.md](../../spec/p021-tradability-production-enablement/RESEARCH.md)（v1.1 verified）。

---

## §1 调研问题清单

### A 组：口径正确性（本仓模型是否可信）

- **RQ-A1**：本仓「昨收/除权参考价 × 板块/ST/日期规则 → 限价 → high/low 判定」与交易所真实限价（`up_limit/down_limit`）的逐格一致率是多少？不一致集中在哪些情形（除权、ST 变更日、注册制前后、北交所）？
- **RQ-A2**：「一字板」用 `high == low` 且价等于限价（±eps）判定，与社区三态口径（未触及 / 触及打开 / 全天封死）相比，会高估还是低估不可成交面？
- **RQ-A3**：T+1 与 `execute_at=next_open` 的组合是否与 A 股实际委托规则一致？开盘一字板 vs 盘中封板是否应区别对待？
- **RQ-A4**：空头腿未建模（`short_leg_unmodeled=True`）时，`turnover` 只对多头腿推进的口径，是否足以支撑「生产启用」的结论？

### B 组：影响面（启用后哪些读数会变）

- **RQ-B1**：启用后仅 `turnover` 与新增 `tradability` 块变化，`rank_icir / pearson_icir / hit_rate / spread / long_short_returns` 是否确实零变化？（初步：代码层已确认，待端到端复跑）
- **RQ-B2**：`turnover` 变化如何传导到健康度（`health_bridge` 拥挤度）与漂移（`unified_drift`）判定？阈值是否需重标定？
- **RQ-B3**：消融批次（L1-L4）的 BH-FDR / trivial 判定是否因 `turnover` 语义改变而改变结论？
- **RQ-B4**：生产管道（`pipeline_integration` / `parallel_runner`）如何把面板切片到「逐因子」网格？全局单例面板是否可用？
- **RQ-B5**：报告持久化（JSON / 缓存 / 指纹日志）是否会被新增 `tradability` 块（含 `Counter` / numpy 标量）阻断？

### C 组：数据可得性（能否覆盖全样本）

- **RQ-C1**：9 个输入字段在 `E:\Ashare_data\market_data` 的覆盖率、日期对齐、缺失结构如何？
- **RQ-C2**：`adj` 缺 81 个交易日会对 `limit_unknown` 造成多大比例？是否需要回退口径（如用未除权昨收 + 标记）？
- **RQ-C3**：ST 仅能由 `stock_name` 字符串推断，可靠性如何（更名日前后、`*ST` / `ST` / `SST` 前缀、退市整理）？是否需要外部 ST 表交叉验证？
- **RQ-C4**：退市标志 `is_delisting` 无本地数据源，缺失对限价判定（退市整理期 10%/5%）影响多大？
- **RQ-C5**：是否引入外部权威限价表（Tushare `stk_limit`，2007-01-04 起）作为对拍源？离线快照的存储与更新成本？

### D 组：工程接入

- **RQ-D1**：启用的开关注入点选在引擎参数（现状）还是配置项（`DEFAULT_CONFIG`）还是运行器（`pipeline_integration` / `parallel_runner`）？
- **RQ-D2**：面板构建成本（1475×6053 对齐 + 每天限价计算）在批量（数百因子 × 多批次）下是否可接受？是否需要按批次缓存一次 `TradabilityInputs`？
- **RQ-D3**：默认路径零变更（`tradability_inputs=None`）如何用机械门禁守护（现有 TP6-11 字面量 + 新增端到端 SHA）？

### E 组：验收

- **RQ-E1**：用哪些外部证据定义「口径正确」（与 `stk_limit` 对拍一致率、与 `limit_list_d` 事件集的重合率）？
- **RQ-E2**：哪些读数变化属于「预期内」、哪些属于「回归」？容忍带如何设定？

---

## §2 现状基线（E1 实测）

### 2.1 能力现状

| 组件 | 状态 | 锚点 |
|---|---|---|
| 判定与推进核心 | 已交付（9 键报告恒 int） | [tradability.py](../../backtest/tradability.py) L304-397 |
| 面板构建器 | 已交付（13 键 meta） | [tradability_inputs.py](../../backtest/tradability_inputs.py) L29-162 |
| 引擎接线 | 已交付但**默认关闭** | [engine.py](../../backtest/engine.py) L63-106、L285-332 |
| 生产管道接线 | **未接线**（只传 close） | [pipeline_integration.py](../../backtest/pipeline_integration.py) L136-146 |
| 批量运行器接线 | **未接线**（逐因子重切片） | [parallel_runner.py](../../backtest/parallel_runner.py) L52-68 |
| CLI / 配置开关 | **不存在** | `DEFAULT_CONFIG`（engine.py L43-48）无该键 |
| 数据装载 | 独立脚本未提供 | 全仓 `build_tradability_inputs` 仅测试调用 |

**结论 C-0**：`tradability` 目前是「引擎可选能力 + 完整单测」，**没有任何生产入口**；`P-020` 之后口径层已收敛，剩余工作是「数据装载 + 开关注入 + 报告消费」。

### 2.2 影响传导（代码层已确认）

```
positions ──(启用)──> apply_tradability ──> effective_w ──> compute_turnover ──> turnover
                                                    └──> result['tradability']{report, meta, 4 口径键}
rank_ic / pearson_ic / hit_rate / spread / long_short_returns  ← 不经过 positions（engine.py L271-283, L313-318）
```

- `turnover` 下游消费方：`health_bridge`（拥挤度，L121-125/L187-190）与 `unified_drift`（L266）→ 健康度/漂移判定会随启用而变。
- `summary()` 仅取 4 个标量键 + mean IC（L393-399）→ 新增键不影响摘要。
- `report` 9 键均为 `int`；`meta` 含 `Counter(str→int)` 与 int/str → JSON 可序列化性待验证（RQ-B5）。

### 2.3 数据实测（2026-11-23，`E:\Ashare_data\market_data`）

| 文件 | 形状 | 覆盖 | 与 `close` 对齐 | 备注 |
|---|---|---|---|---|
| `stock_close.pkl` | 1475×5688 | 2020-01-02 ~ 2026-01-30 | — | NaN 14.13% |
| `stock_high/low/open/volume.pkl` | 同 close | 同上 | 列/日期一致 | 原始价（未复权） |
| `stock_adj.pkl` | 1394×5691 | 2020-01-02 ~ 2026-01-30 | **缺 81 个交易日** | NaN 12.64%，max 10055.64 |
| `stock_name.pkl` | 1474×6053 | 缺 **2026-01-30** | 少 1 日 | ST 单元格 265,296（2.97%） |
| `stock_suspend.pkl` | 1475×5681 | 同 close 日期 | **列集不同**（少 7 列） | 取值 `None` / `'S'`(18,242) / `'R'`(2,700) |
| `list_date_df.pkl` | 5797×1 | 全历史 | 索引为**裸 6 位代码** | 列名 `list_date` |
| `all_dates.pkl` | 1475 | 2020-01-02 ~ 2026-01-30 | — | `list` |
| 面板列并集 | **6053** | — | close 仅 5688 | 365 个代码只在其他面板 |

**板块前缀分布（并集）**：`300` 978 / `002` 973 / `600` 874 / `603` 619 / `688` 605 / `000` 506 / `301` 452 / **`920` 293** / `601` 231 / `605` 113。

**一字板量级（high==low 上限估计）**：31,022 格 = 有效格 0.431%；逐年 2020 0.78% / 2021 0.48% / 2022 0.34% / 2023 0.14% / 2024 0.29% / 2025 0.19% / 2026 0.25%。

### 2.4 数据缺口清单（初步）

| # | 缺口 | 影响 | 候选处置（待调研） |
|---|---|---|---|
| G-1 | `adj` 缺 81 个交易日 | 除权参考价 NaN → `limit_unknown` 上升 | 前后向填充 / 用 `ref=prev_close` 回退并标记 / 补齐源数据 |
| G-2 | `stock_name` 缺最后 1 日 | 末 ST 状态缺失 | 前向填充（T-1 状态） |
| G-3 | `suspend` 列集与 close 不同（5681 vs 5688） | 形状校验失败 | 按 close 网格 reindex，缺失列视为「非停牌」并计数披露 |
| G-4 | 无独立 ST 历史表 | ST 判定依赖名称字符串 | 外部 ST 表交叉验证（Tushare `namechange` / `bak_basic`） |
| G-5 | 无退市标志 | `is_delisting=None`，退市整理期按普通档 | 外部退市表 / 名称含「退」规则（需实测精度） |
| G-6 | 无权威限价表 | 限价只能自算，无法对拍 | Tushare `stk_limit`（2007-01-04 起）离线快照 |

---

## §3 影响面矩阵（提纲）

> **正式结论见** [影响面报告](RESEARCH_TRADABILITY_PRODUCTION_IMPACT_REPORT.md)：启用不改变 IC/收益，只改 `turnover`；`turnover` 传导至健康度/漂移；数据分级缺失导致乐观偏差。下表为待测项，报告 §2 已给出证据锚点与门禁。

| 层 | 启用后变化 | 风险等级 | 调研动作 |
|---|---|---|---|
| 指标 | `turnover` 序列变（多头腿推进、空头腿透传） | **高** | 全样本前后对照；分布/均值/极值 |
| 指标 | IC / ICIR / hit / spread / LS 收益 | 无（代码层确认） | 端到端复跑证实 |
| 健康度 | 拥挤度分数、分位、结论 | **中** | `health_bridge` 阈值敏感性 |
| 漂移 | 漂移特征/裁决 | **中** | `unified_drift` 前后一致性 |
| 消融 | BH 分母 / trivial 判定 | **中** | L1-L4 单臂复跑 |
| 报告 | 新增 `tradability` 块；持久化体积 | 低-中 | JSON/缓存往返测试 |
| 批量 | 逐因子面板切片（交集不同） | **高** | 面板缓存策略与内存预算 |
| 性能 | 构建一次 ≈ O(T×N) + 每日规则查表 | 低-中 | 计时 + 峰值内存 |
| 默认路径 | `None` 时逐位不变 | — | TP6-11 + 工件 SHA 门禁 |

---

## §4 社区案例初筛（12 条）

> 验证状态：**✅ 全文抓取** = 本批 WebFetch 读全文；**⚠️ 摘要级** = 仅搜索摘要命中，未抓全文；**—** = 未独立验证。

| # | 来源 | 做法/结论 | 对本仓的启示 | 状态 |
|---|---|---|---|---|
| S1 | Qlib 文档（配置示例） | `limit_threshold: 0.095` 固定阈值模拟涨跌停无法成交；`deal_price` 可选 close/open/vwap | 固定阈值无法覆盖 20%/30%/5%/无限制；本仓板块+ST+日期规则更细，但**需与真实限价对拍**证明 | ⚠️ 摘要级 |
| S2 | Qlib API（中文镜像） | `forbid_all_trade_at_limit=True` 时涨停/跌停**双向全禁交易**；`limit_threshold` 多空同阈值 | 本仓是**方向性**（涨停禁买、跌停禁卖）；差异需量化（保守/激进方向） | ⚠️ 摘要级 |
| S3 | Qlib 文档（数据约定） | 停牌股票 OHLCV 置 NaN | 本仓用 `suspended` 掩码而非 NaN；`close` 已有 14% NaN（停牌+未上市），需区分 | ⚠️ 摘要级 |
| S4 | RiceQuant 回测文档 | 涨跌停价、停牌、退市、未上市均导致下单失败；单边市买单/卖单无法成交 | 与本仓 9 键报告语义一致（`blocked_buy/sell`、`limit_unknown`、`suspended`） | ⚠️ 摘要级（全文未含该节） |
| S5 | RQAlpha API | `limit_up` / `limit_down` 为 bar 属性 | 权威实现同样以「当日限价」为判定基准，而非收益率阈值 | ⚠️ 摘要级 |
| S6 | JoinQuant API PDF | 已涨停/跌停时对应买单/卖单不成交；市价单取消、限价单挂单 | 本仓 `execute_at=next_open` 隐含「次日开盘撮合」，未建模挂单队列 → 需口径声明 | ⚠️ 摘要级 |
| S7 | Tushare `stk_limit` | 官方每日涨停价/跌停价，2007-01-04 起，含 `exchange`（SSE/SZSE/BSE） | **最佳对拍源**；可实测 RQ-A1 一致率，并校准除权/ST/北交所边界 | ✅ 全文抓取 |
| S8 | Tushare `suspend_d` | `suspend_type`：`S`-停牌 / `R`-复牌；日级覆盖 | 与本地 `stock_suspend` 的 `'S'/'R'` 语义一致；构建器应只把 `'S'` 映射为停牌 | ⚠️ 摘要级 |
| S9 | Tushare `limit_list_d` | 每日涨跌停/炸板列表，2020 年起，**不含 ST** | 可作为一字板事件的第二验证集（注意 ST 缺口，不能单靠它判召回） | ⚠️ 摘要级 |
| S10 | 腾讯云社区（回测涨停判断） | 不能用 `return >= 0.1`；应分三态：未触及 / 触及打开 / 全天一字，第三类保守判不成交 | 本仓 `high==low` 属「全天一字」判据；需补「触及打开」的可成交假设说明 | ⚠️ 摘要级 |
| S11 | 华为云社区（涨跌停/停复牌处理） | 主板 ±10%、创业板/科创板 ±20%、ST ±5%、北交所 ±30%、新股前几日无限制；信号层按不成交更保守 | 与本仓 `rule_pct` 规则表一致；可作为外部规则旁证 | ⚠️ 摘要级 |
| S12 | diyadata（涨停价四舍五入） | 涨停价四舍五入规则直接决定打板回测成败；一字板应标记不可成交 | 支持本仓「整数分 half-up + eps 容差」；需用 `stk_limit` 实测四舍五入一致率 | ⚠️ 摘要级 |
| S13 | 证监会 / 中国政府网（2023-02-01） | 全面注册制：主板新股上市前 5 个交易日不设涨跌幅；科创板/创业板前 5 日无限制、此后 20% | 本仓 `no_limit` 规则必须按**板块 + 日期**分段（注册制改革前后），现已按 `list_date` 处理，待实测 | ✅ 全文抓取 |

> 社区案例的共同盲区：几乎都**不做除权参考价对齐**（直接用昨收×比例），除权日会算错限价；本仓 `_ref_from_adj` 是差异点，需用 `stk_limit` 证明其收益。
> **S13 勘误（2026-11-23）**：本仓 `no_limit` 实际是「所有板块上市后前 5 个交易日」，**未**按板块/日期分段；2023-04-10 前主板（首日 44%/36%）与北交所（仅首日无限制）会被过度放宽，详见[未决事项专项验证](RESEARCH_TRADABILITY_OPEN_ITEMS_VERIFICATION.md) O-9/V-10。

---

## §5 调研方法与检索式（可复跑）

### 5.1 通道与降级链（F3）

| 目标 | 主通道 | 备用 | 已读本地事实 | 失败声明 |
|---|---|---|---|---|
| 官方撮合规则 | WebFetch 官方文档 | 搜索摘要 | 本仓 `rule_pct` 规则表 | 「未验证」，不标 ✅ |
| 社区实践 | WebSearch 中英文 | 社区文章全文 | 代码现有实现 | 「摘要级」 |
| 权威限价对拍 | Tushare `stk_limit` 离线拉取 | 交易所公告 | 本地 OHLCV | 「样本外不可得」并披露 |
| 数据可得性 | 本机 pickle 实测 | 数据契约 | `data_contract.py` | 「缺失」 |

### 5.2 预置检索式

1. `qlib limit_threshold forbid_all_trade_at_limit exchange implementation`
2. `rqalpha limit_up limit_down bar_dict source`
3. `joinquant 涨停 买单 不成交 市价单 取消`
4. `tushare stk_limit 每日涨跌停价格 up_limit down_limit`
5. `tushare suspend_d S R 停复牌`
6. `A股 回测 一字板 不可成交 三态 high==low`
7. `除权 涨停价 计算 昨收 复权 因子`
8. `北交所 30% 涨跌幅 920 代码`
9. `注册制 主板 前5个交易日 不设涨跌幅 2023`
10. `ST 股票 涨跌幅 5% 2020 创业板 20% 规则`

### 5.3 引用核验（F4）

- 本提纲外部引用 **13 条（≥3）** → 已建 §4 表；`✅ 全文抓取` 2 条（S7、S13），其余 11 条标 `⚠️ 摘要级`。
- 正式 RESEARCH 阶段需把 S1/S2/S4/S5/S6 升级为全文核验，或明确降级为「社区旁证，不承载关键结论」。

---

## §6 关键差异点（本仓 vs 社区主流）

| 维度 | 社区主流 | 本仓 | 需证明 |
|---|---|---|---|
| 限价来源 | 固定 9.5%/10% 阈值 | 昨收×板块/ST/日期规则 + 除权参考价 + half-up 取整 | 与 `stk_limit` 一致率 ≥ 目标阈值 |
| 涨停处理 | 常为双向全禁 | 方向性：涨停禁买 / 跌停禁卖 | 与真实委托可成交性方向一致 |
| 一字板 | 三态分类，第三类不成交 | `high==low` 且价≈限价 | 覆盖率/误判率 |
| 停牌 | OHLCV=NaN | `suspended` 掩码 + close NaN | 两种口径的交集/差集 |
| 空头腿 | 多空同规则 | 空头腿未建模（透传） | 口径披露是否充分 |
| 收益影响 | 多数引擎直接改撮合 | **不改收益，仅改 turnover** | 明确「证据层」定位是否满足生产需求 |

---

## §7 交付物与门禁（若立项为 T1 批次）

1. **RESEARCH.md**：RQ-A1 一致率实测（`stk_limit` 抽样 ≥ 12 个月 × 全市场）、G-1~G-6 处置裁决、S1-S6 全文核验。
2. **DESIGN.md**：开关注入点（引擎/配置/运行器）、面板缓存与逐因子切片方案、`is_delisting` 取舍、报告持久化契约、INV（默认路径逐位不变）。
3. **IMPLEMENTATION.md**：数据装载器接口 + 回退点；批量运行器改造；性能预算。
4. **CHECKLIST.md**：默认路径 SHA 门禁、口径一致率阈值、turnover 前后对照表、健康度/漂移/消融回归清单。
5. **Step 10 审计 + 异构复审**：同 P-020 双视角。

---

## §8 风险与未决项（四元登记）

- **U-1 生产启用是否包含「收益层」**
  - 判据：`long_short_returns` / `spread` 是否改用 effective 权重
  - 触发条件：用户要求「可交易净收益」口径
  - 当前倾向：**先只启用证据层**（turnover + 报告），收益层单独立项
  - 证据等级：E1（当前代码不改收益）

- **U-2 是否引入外部权威限价快照**
  - 判据：自算限价与 `stk_limit` 一致率是否低于阈值
  - 触发条件：一致率 < 99.9% 或关键边界（除权/ST/北交所）出现系统偏差
  - 当前倾向：先自算 + 抽样对拍，不引入新依赖
  - 证据等级：E2

- **U-3 `adj` 81 日缺口处置**
  - 判据：`limit_unknown` 占比
  - 触发条件：> 0.5% 的股票×日
  - 当前倾向：前后向填充 + 披露；不回退为未除权昨收
  - 证据等级：E1（缺口已实测，影响未测）

- **U-4 批量面板缓存粒度**
  - 判据：构建耗时与内存
  - 触发条件：单批构建 > 30 s 或峰值 > 1 GB
  - 当前倾向：按「日期区间」缓存一次，逐因子 reindex
  - 证据等级：E0（待测）

---

## §9 建议的批次切分（待用户裁决）

| 方案 | 范围 | 风险 | 产出 |
|---|---|---|---|
| **A（推荐）证据层启用** | 数据装载 + 引擎开关 + turnover/报告落盘 | 中 | 可复跑的「可交易性证据」读数 |
| B 收益层启用 | A + `long_short_returns` 改用 effective 权重 | 高 | 净收益口径，需重做基线 |
| C 只做口径对拍 | 仅 `stk_limit` 对拍报告，不接线 | 低 | 一致率报告，作为 A 的前置 |

> 建议顺序：**C → A**（先用 1 个月全市场对拍证明口径，再接线）；B 单独立项。

---

## §10 参考来源

1. [Qlib 回测系统详解（limit_threshold / deal_price）](https://www.wuzao.com/p/qlib/tutorial/backtesting-system) ⚠️
2. [QLib API 参考（forbid_all_trade_at_limit）](https://www.wuzao.com/p/qlib/document/reference/api.html) ⚠️
3. [QLib Documentation v0.6.1（停牌 OHLCV=NaN 约定）](https://qlib.readthedocs.io/_/downloads/en/v0.6.1/pdf/) ⚠️
4. [Ricequant 回测文档（下单失败情形 / 单边市）](https://www.ricequant.com/doc/quant/backtest.html) ⚠️
5. [RQAlpha 基础 API（limit_up / limit_down）](https://rqalpha.readthedocs.io/zh-cn/develop/api/base_api.html) ⚠️
6. [JoinQuant API 文档（涨停跌停不成交）](https://cdn.joinquant.com/help/img/JoinQuantAPI.pdf) ⚠️
7. [Tushare stk_limit 每日涨跌停价格](https://tushare.pro/document/2?doc_id=183) ✅
8. [Tushare suspend_d 停复牌](https://tushare.pro/document/2?doc_id=214) ⚠️
9. [Tushare limit_list_d 涨跌停列表](https://tushare.pro/document/2?doc_id=298) ⚠️
10. [腾讯云社区：回测里的涨停判断为什么不能写成 return >= 0.1](https://developer.cloud.tencent.com/article/2773854) ⚠️
11. [华为云社区：A 股涨跌停、停牌与复牌在回测中的正确处理](https://bbs.huaweicloud.com/blogs/517427) ⚠️
12. [迪雅数据：涨停价四舍五入规则与打板回测](https://www.diyadata.cn/guide/limit-up-price.html) ⚠️
13. [中国政府网：证监会就全面实行股票发行注册制答记者问（2023-02-01）](https://www.gov.cn/zhengce/2023-02/01/content_5739609.htm) ✅
