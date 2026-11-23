# 审查验收 Checklist：P-006 tradability 接入回测引擎与限价取整口径

---
id: p006-tradability-engine-integration-CHECKLIST
type: design
version: 1.4
status: done
date: 2026-11-23
depends: [p006-tradability-engine-integration-IMPLEMENTATION, p006-tradability-engine-integration-DESIGN]
upstream: null
---

> **Feature**: P-006 —— `tradability` 接入 `FactorBacktestEngine`，并入 P-007 限价取整口径
> **创建日期**: 2026-11-23
> **状态**: **验收通过（done）**——Step 9 TDD 红→绿完成（§1-§7 共 98/98 ✅）+ Step 10 ADD 审计 **PASS_WITH_FIXES：0×P1 + 1×P2（就地修复 test_tp6_9b）+ 5×P3（1 复核不成立 / 1 文档订正 / 3 登记 P-020）**，质量门 **4.9/5 档位 A**，§10.1 **102/102 通过**，全量回归 **2143 passed / 34 skipped / 0 failed**（Step 8 文档一致性复审 PASS_WITH_FIXES 已处置，见 §1.5 与 [DESIGN.md §15](./DESIGN.md)；红→绿记录 §2.6，审计记录 §8，实施记录 [IMPLEMENTATION §15](./IMPLEMENTATION.md)）
> **Spec 步骤**: Step 7-10
> **基于实施**: [IMPLEMENTATION.md](./IMPLEMENTATION.md) **v1.3**（Step 6 复审 PASS_WITH_FIXES 已处置 §14；Step 8 处置 v1.2；Step 9 记录 §15）
> **基于设计**: [DESIGN.md](./DESIGN.md) **v1.3**（Step 4 复审 PASS_WITH_FIXES 已处置 §14；Step 8 复审记录 §15）
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.4**（Step 2 引用复核 PASS）
> **档位**: **T1** ｜ **包版本**: 3.9.8 → 3.9.9 ｜ **新依赖**: 无

> **适用范围与裁剪声明（T1）**
> 本批含 Layer-1 代码改动（`backtest/tradability.py`、`backtest/tradability_inputs.py`（新增）、`backtest/engine.py` + `tests/`），**不适用 T3 裁剪**。Step 9 必须按 TDD 双要素执行：先红（新增 TP6 用例在旧实现上失败）→ 后绿（全通过），两次读数记入 IMPLEMENTATION §8 或本文件 §2 证据列。所有验收方法均为**可重放命令或逐字读数**，不得以「已确认」替代。

> **Step 8 / 9 / 10 记录位**：§1 由 Step 8 独立只读 pass 填写；§2-§7 由 Step 9 实施与 Step 10 复核回填；§8 由 Step 10 ADD 审计填写；§10.1 统计按逐项状态机械汇总（RULE-2）。

---

## 1. 文档一致性验收（Step 8）

### 1.1 RESEARCH.md ↔ DESIGN.md 对齐

| 验收项 | DoR（前置） | 验证方法 | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|---|
| DESIGN D1-D12 可追溯到 RESEARCH | 两文档定稿 | 逐条核对 DESIGN §2.1 引用节与 §12 登记表 | 12/12 决策均有真实 RESEARCH 章节号，且内容支持决策 | ✅ | 复审 A1：12/12 通过；抽样 D2←§3.6.3（half-up 55,296 vs np.round 55,333）+U-1、D7←§3.6.5（97.9%/81 日）+R-5、D12←§6.7（002122 名称早于公告 7 交易日）+R-6；DESIGN §12 与 §2.1 互引一致 |
| U-1~U-7 未决项全部关闭并被设计承接 | RESEARCH §6.4 关闭记录 | 逐条比对裁决词与设计落点 | 7/7 关闭，无「待定」漂移 | ✅ | 复审 A2：U-1→D2+TP6-1/2、U-2→D4+TP6-4、U-3→D1、U-4→D5/D6/D12、U-5→D7、U-6→D8、U-7→D9+TP6-12；U-6 残余（两档读数）落本文件 §2.2（P3-6 处置） |
| R-1~R-6 风险均有设计落点 | RESEARCH §6.7 / DESIGN §10.2 | 反向清单比对 | 6/6 命中 DESIGN 决策或风险表行 | ✅ | 复审 A3：R-1→§3.3-4/§4.7、R-2→D5/§4.1、R-3→§6.1 一字板诊断+D8、R-4→D6/§6.2、R-5→D7/§6.2/limit_unknown、R-6→D12/§4.6 st_calibration_source |
| 两文档无矛盾表述 | 两文档定稿 | 交叉检索 `unknown` / `no_limit` / `ref` / 区间映射 | 无相反口径（含 `no_limit` 优先级、`ref` float 近似披露） | ✅ | 复审 A4：no_limit 优先链、ref 对齐到分+22.7% 披露、half-up、一字板、unknown 语义三文档一致；P2-1 已修——DESIGN §4.1 残留枚举改区间（DESIGN v1.3 §15），与 IMPL/CHECKLIST 对齐 |

### 1.2 DESIGN.md ↔ IMPLEMENTATION.md 对齐

| 验收项 | DoR（前置） | 验证方法 | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|---|
| DESIGN §3.2 五模块均有落点 | IMPLEMENTATION §2.3/§3 存在 | 模块名逐一比对 | 5/5（3 改 + `factor_metrics.py`/`panels.py` 明确不改） | ✅ | 复审 B1：IMPL §3.1/§3.2/§3.3 对应 tradability.py/tradability_inputs.py/engine.py；factor_metrics/data_bridge/panels/verify_long_side_research 于 IMPL §1 明确不触碰 |
| IMPLEMENTATION 接口与 DESIGN §4.1~§4.7 一致 | 两文档 §4 存在 | 比对签名、参数顺序、返回形态 | 7/7 一致（§4.3/§4.4 在 IMPL 合为 §4.3，§4.5/§4.6 合为 §4.4） | ✅ | 复审 B2：board_of/limit_price/compute_limits/apply_tradability（policy 后追加 4 kwargs）/TradabilityInputs（eq=False）/引擎（6 字段挂载）逐参一致；P3-1 已修——DESIGN v1.3 §4.6 补 st_overrides=None |
| DESIGN INV-1~9 均有实施位置与验证方式 | IMPLEMENTATION §7 表存在 | 逐条比对 | 9/9 含实施位置列 + 验证方式列 | ✅ | 复审 B3：9/9 逐行比对通过；P3-4 已修——IMPL §7 INV-9 验证方式改指本文件 §2.2 的 9 键 int 断言 |
| D-6-1~17 派生需求全部登记且自洽 | IMPLEMENTATION §11 存在 | 核对每行来源与影响 | 17/17 有来源（DESIGN 节/复审编号），互引无冲突 | ✅ | 复审 B4：17/17 有来源，与 DESIGN v1.2 六处勘误 6/6 对应（D-6-13/11/12/16/15/17）；P2-1 同源处置——D-6-4 来源改引 DESIGN §4.1（v1.3）+E7；P3-5 已修——IMPL 头部勘误计数 5→6 |
| 无设计未覆盖的实施 / 无越界改动 | 两文档定稿 | 核对 IMPL §1/§2.3 改动面 | 改动面仅 3 源文件 + 3 测试文件 + 版本 7 落点 + CHANGELOG | ✅ | 复审 B5：改动面合规（2 源 + 1 新增 + 3 测试 + CHANGELOG）；版本 7 落点与 DESIGN §10.1-8 逐项一致；无越界文件 |

### 1.3 IMPLEMENTATION.md ↔ CHECKLIST.md 对齐

| 验收项 | DoR（前置） | 验证方法 | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|---|
| IMPLEMENTATION 功能点均有验收项 | 本文件 §2-§5 完成 | 反向清单比对 | IMPL §3.1-§3.5 → §2.1-§2.5；§4 → §3；§6 → §5；§7 → §4；§12 → §6 全覆盖 | ✅ | 复审 C1：正向+反向全覆盖，无孤立项；P3-3 已修——IMPL §6 补 high/low NaN 行（对齐本文件 §5） |
| 每个验收项可回溯到 IMPLEMENTATION | 本文件全表 | 逐项查 DoR 锚点 | 无孤立验收项；TP6 编号与 DESIGN §10.4 一一对应 | ✅ | 复审 C2：TP6-1~12 一一对应；TP6-5 归 tradability.py、TP6-7 拆两半、TP6-8 两侧、TP6-9 三子断言如实反映；P3-2 已修——IMPL §2.3 注释与 §10 Step1 清单同步（TP6-6 归 Step 1） |

### 1.4 术语一致性

| 术语 | RESEARCH.md | DESIGN.md | IMPLEMENTATION.md | 一致 |
|---|---|---|---|---|
| `ref`（除权参考价） | §3.6.5 `adj_{t-1}/adj_t` | §4.3 `prev×adj[t-1]/adj[t]` + float 近似披露 | §3.1-7 缺失前置 + D-6-17 | ✅（复审 D1） |
| `no_limit` | §3.6.7 IPO/退市整理首日 | §4.4/§6.1 优先于 `limit_unknown` | §3.1-7 `judge = ~unk & ~no_limit` | ✅（复审 D2） |
| `limit_unknown` | §6.6 R-3/R-5 | §6.1 单桶优先级链 | §3.1-7 busy & 非停牌 & 非 no_limit & unk | ✅（复审 D3） |
| `price_basis` / `leg_scope` | §6.6 R-1 口径分离 | §4.7 `raw_adj_ref` / `long_only` | §3.3-2 结果挂载 6 字段 | ✅（复审 D4；P3-7 锚点订正） |

### 1.5 Step 8 复审记录（2026-11-23）

> 独立只读复审（异构基座），判据即本节 §1.1-§1.4 共 15 项。**总结论：PASS_WITH_FIXES —— 0×P1 + 1×P2 + 7×P3**；15 项 12 ✅ / 3 ⚠️ / 0 ❌（⚠️ 均由 P2-1 / P3-1 / P3-5 引起，处置后转 ✅）。处置详表见 [DESIGN.md §15](./DESIGN.md)；CHECKLIST 侧动作：P3-6 增 §2.2 U-6 记录行、P3-7 订正本节 D4 锚点、15 项状态/证据回填。版本：DESIGN v1.3 / IMPLEMENTATION v1.2 / CHECKLIST v1.1。
>
> 复审确认无问题的关键面：A1 决策追溯 12/12；A2 未决项 7/7 闭合；A3 风险落点 6/6；B1 模块落点 5/5；B5 改动面无越界；C1/C2 验收覆盖与 TP6 编号一一对应；D1-D3 术语一致。E1 状态词扫描 12 处命中均为历史记录/已闭合条目/披露块，无状态漂移；E2 关键数字（20% 档 tie 恒 0、22.7%/8,941、104,921、版本七落点、9 键、pct ≤10 次/日、0.1 元门槛）跨文档一致。

## 2. 功能验收

### 2.1 算法层 `tradability.py` 上半（IMPLEMENTATION §3.1-1~4）

| 验收项 | DoR（前置） | 验证方法 | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|---|
| TP6-1 tie 定向四例 | `limit_price` 可导入 | `pytest -q tests/test_tradability.py -k TP6_1` | `10.25` up/down = `11.28/9.23`；`3.33` up/down = `3.66/3.00` | ✅ | 绿：`-k TP6_1` 1 passed；四值逐字命中（`10.25` down=`9.23` 与银行家舍入区分） |
| TP6-2 属性测试 + `pct` 负例 + 静态禁用 `np.round` | 同上 | 同上 `-k TP6_2` | ≥10,000 样本对 `Decimal(ROUND_HALF_UP)` 差异 **0**；`pct∉[0,1]` 抛 `ValueError`；`tradability.py` 无 `np.round`/`np.rint` 限价调用 | ✅ | 绿：2,501 价 × 4 档 × 2 侧 = **20,008** 样本差异 0（断言 `total>=10000`；Step 10 P3-① 订正原 10,004 算术误写）；`pct=1.5/-0.1` ValueError；静态断言无 `np.round(`/`np.rint(`；NaN→NaN |
| TP6-3 三分支边界 | 同上 | `-k TP6_3` | `0.01/0.09/0.10` 边界：差额 <1 分 → ±1 分；限价 <1 分 → 1 分；`side` 非法 `ValueError` | ✅ | 绿：`0.01`→`0.02/0.01`、`0.09`→`0.10/0.08`、`0.10`→`0.11/0.09`；`side="flat"` ValueError |
| TP6-5 `board_of` 全前缀与未知 | `board_of` 可导入 | `-k TP6_5` | 600/601/603/605、000-004、300-309（含 302）、688/689、43/83/87/92 命中；其余（如 900/200/非数字）→ `unknown`，**无默认 main** | ✅ | 绿：`-k TP6_5` 1 passed；含 `302132/309999`→gem、`689009`→star、`920001`→bse；`900001/200001/abc/''`→unknown；`600000`(int)/`600000.SH`→main |
| TP6-6 除权参考价 | `compute_limits` 可导入 | `-k TP6_6` | `prev=10, adj_prev/adj_t=0.5` → `ref=5`、涨停 `5.50`；非除权日 `ref==prev`（<1e-6） | ✅ | 绿：`compute_limits(10,0.1,ref=5)`→`5.50/4.50`；apply 侧 `adj=[2,4,4]` 使 `high=5.50` 封板、次日 ref=prev 放行；`ref=prev` 与不传 ref 逐值一致 |
| TP6-12 低价 ST 与一档分支等价 | 同上 | `-k TP6_12` | `prev_cents=1..9` 全扫描：显式分支 == 通用三分支（逐值） | ✅ | 绿：`cents=1..9` 全扫描 `up/down` 逐值相等（含 `0.01` down 分支②→`0.01`） |

### 2.2 推进层 `tradability.py` 下半（IMPLEMENTATION §3.1-6~8）

| 验收项 | DoR（前置） | 验证方法 | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|---|
| TP6-7 apply 侧：adj 单侧缺失 → unknown | `apply_tradability` 可调用 | `-k TP6_7` | 显式构造 `adj[t]`/`adj[t-1]` 恰一个 NaN：`report["limit_unknown"]>0` 且 `blocked_*` 不增加 | ✅ | 绿：`adj=[2,2,NaN]` → `limit_unknown=1`、`blocked_buy=0`、该格放行 `eff=0.5` |
| TP6-8 apply 侧：退市分治 | 同上 | `-k TP6_8` | `退` 名称不落 ST 5% 分支；退市整理首日不判封板 | ✅ | 绿：ST 5% 下 `high=10.50` 封板（`blocked_buy=1`）；`is_delisting` 同价放行；`no_limit` 日 `high=11.00` 仍放行 |
| 报告恒 9 键且值均为 `int` | 同上 | 断言 `set(report) == 9 键` 且逐值 `type is int` | 空面板全 0；无私有键 | ✅ | 绿：`test_empty_panel_report_zero` 9 键全 0 且 `type is int`；TP6-7 同步断言键集 |
| 单桶优先级链与组合裁决 | 同上 | 构造 16 组合（suspended × no_limit × unknown × blocked） | 与 DESIGN §6.1 链一致：`suspended > no_limit > limit_unknown > blocked_* > t1_locked` | ✅ | 绿：16 组合逐桶读数 `blocked_suspend=8 / limit_unknown=2 / blocked_buy=1`，其余 7 格自由成交（含 2 格 unknown 放行）；每格至多入一桶 |
| U-6 残余：eps 两档敏感性读数（Step 8 P3-6 新增，RESEARCH §6.4 U-6） | `policy.eps` 可配 | Step 9 以 `eps=0` 与 `eps=1 tick` 各跑一次封板计数，两档并列披露 | 两档读数均记入本行证据列 | ✅ | 读数（prev=10, high=10.999, up=11.00）：`eps=0` → `blocked_buy=0`；`eps=0.01`（1 tick）→ `blocked_buy=1`；覆盖 `test_eps_two_readings_u6` |
| T390-27~35 既有回归 | 既有测试文件 | `pytest -q tests/test_tradability.py` | 全部保持通过（无键数断言被破坏） | ✅ | 绿：T390 9 例全通过；`DEFAULT_LIMIT_RULES` 零改动（INV-8） |

### 2.3 构建器 `tradability_inputs.py`（IMPLEMENTATION §3.2）

| 验收项 | DoR（前置） | 验证方法 | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|---|
| TP6-4 BSE 30% + 无明文披露 | 构建器可调用 | `pytest -q tests/test_tradability_inputs.py -k TP6_4` | `10.00 → 13.00 / 7.00`；meta `rounding_basis="inferred_half_up"`（含 bse 时） | ✅ | 绿：`compute_limits(10,0.30)`→`13.00/7.00`；含 bse 面板 `inferred_half_up`，纯 A 股面板 `exchange_half_up` |
| TP6-7 meta 侧：单侧缺失计数 | 同上 | `-k TP6_7` | 单侧 adj 缺失构造下 `meta["adj_missing_days"]>0`（不被 t=0/双侧兜住） | ✅ | 绿：`adj.iloc[3,0]=NaN`（t=2 有限）→ `adj_missing_days=1` |
| TP6-8 派生侧：ST/退市/无限制日 | 同上 | `-k TP6_8` | `is_st` 含 `ST` 不含 `退`；`is_delisting` 含 `退`；退市整理首日 `no_limit=True` | ✅ | 绿：`ST测试`→`is_st=True`、`is_delisting=False`；`退市测试`（t≥4）→`is_delisting=True`、`is_st=False`；`no_limit[4]=True` |
| IPO 前 5 日豁免与缺失披露 | `list_date` 可给/可不给 | 两态断言 | 给出时首日（含）起 5 个交易日 `no_limit`；缺失时 `no_limit_source="delisting_only"`（禁止静默失效） | ✅ | 绿：`list_date=dates[0]` → `no_limit[:5]` 全真、第 6 日假；`dates[2]` → t=2..6；`list_date=None` → `delisting_only` 且仅退市首日 1 格 |
| `st_overrides` 校准钩子 | 可传入 `[code, effective_date]` | 提供/不提供两态 | 提供时不一致数入 `st_date_unverified` 且 `st_calibration_source="coverage_table"`；不提供时 `0` + `"none"` | ✅ | 绿：不提供 → `0/"none"`；一致 → `0/coverage_table`；差 3 交易日 → `1` |
| meta 键齐全 | 构建器返回二元组 | 数键 | DESIGN §4.6 列出的 13 键全部存在，`price_basis="raw_adj_ref"` | ✅ | 绿：`set(meta)` 与 13 键集合逐字相等；`price_basis="raw_adj_ref"`；网格错位面板自动对齐 |

### 2.4 引擎接入 `engine.py`（IMPLEMENTATION §3.3）

| 验收项 | DoR（前置） | 验证方法 | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|---|
| TP6-9 启用路径（3 子断言） | 合成盘可构造 | `pytest -q tests/test_backtest/test_engine.py -k TP6_9` | 涨停日 `blocked_buy>0`；`turnover` 与未启用不同；`tradability` 键存在；形状负例与 `adj=None` 负例抛 `ValueError` | ✅ | 绿：`blocked_buy=1`、`turnover` 与未启用不同、`tradability` 键存在；`close[:2]` 与 `adj=None` 均 ValueError（消息含「tradability 需要 adj」） |
| TP6-10 空头腿透传 | 同上 | `-k TP6_10` | `effective[positions<0] == positions[positions<0]`（逐位）；`short_leg_unmodeled=True` | ✅ | 绿：`np.array_equal(effective[neg], positions[neg])` 为真；`short_leg_unmodeled=True`、`leg_scope="long_only"` |
| TP6-11 默认基线逐位一致 | Step 9 前采集基线字面量 | `-k TP6_11` | `summary()` + `turnover` 数组逐位一致；无 `tradability` 键 | ✅ | 绿：`rank_icir=-0.25880207857362303`、`pearson_icir=-0.30599173567954446`、`hit_rate=0.36363636363636365`、`spread=-0.1610540425109819`、`mean_rank_ic=-0.10649350649350647`；`turnover=[1.5,1.0,2.0,1.5,2.0,1.0,1.0,1.0,1.0,1.5,1.5]`；无 `tradability` 键（基线于改动前采集） |
| 结果挂载字段完整 | 启用态结果可读 | 读 `results[factor]["tradability"]` | 含 `report/meta/price_basis/leg_scope/short_leg_unmodeled/turnover_basis` 六字段且取值符合 DESIGN §4.7 | ✅ | 绿：TP6-9 断言 `price_basis="raw_adj_ref"` + `turnover_basis="effective_long_only"`；其余四字段同测 |

### 2.5 版本与 CHANGELOG（IMPLEMENTATION §3.5）

| 验收项 | DoR（前置） | 验证方法 | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|---|
| 版本 3.9.9 落 7 处 | 代码改动完成 | `Grep "3\.9\.9"` 六文件 + 读 CHANGELOG 顶部 | 7 落点全部为 `3.9.9`，无残留 `3.9.8` 于版本字段 | ✅ | 绿：`pyproject.toml:7`、`__init__.py:58`、`config_v2.py:371`、`reporting.py:40`、`tests/test_fix3_version_unification.py:34`、`tests/test_backtest/verify_fix3_manual.py:21` + `CHANGELOG.md` 新条目；版本字段无 3.9.8 残留 |
| CHANGELOG 条目 | 同上 | 读 `CHANGELOG.md` 顶部 | 条目含「限价 half-up / opt-in 引擎接入 / 报告 9 键」三要点 | ✅ | 绿：`v3.9.9 — tradability 接入回测引擎 + 限价整数分 half-up（P-006）`，三要点齐备 |
| 版本一致性测试 | 同上 | `pytest -q tests/test_fix3_version_unification.py tests/test_backtest/verify_fix3_manual.py` | 全部通过 | ✅ | 绿：`test_fix3_version_unification.py` 9 passed；`verify_fix3_manual.py` 为手动脚本（无 pytest 用例，不产生失败） |

### 2.6 Step 9 TDD 红→绿记录（2026-11-23）

> **红（旧实现）**：新增 TP6 用例在 v3.9.8 代码上失败——`tests/test_tradability.py` 收集期 `ImportError: cannot import name 'board_of'`（`board_of`/`compute_limits`/`TradabilityInputs` 均缺）；`tests/test_tradability_inputs.py` `ModuleNotFoundError: No module named 'backtest.tradability_inputs'`；`tests/test_backtest/test_engine.py` 新用例 `TypeError: FactorBacktestEngine.__init__() got an unexpected keyword argument 'tradability_inputs'`。
>
> **绿（新实现）**：定向四文件 **44 passed / 20 skipped**——`test_tradability.py` 21 passed、`test_tradability_inputs.py` 10 passed、`test_engine.py` 4 passed + 20 skipped（20 skip = 5 个 DataBridge 类，`Factor_Trading_v3_0` 未安装按类跳过）、`test_fix3_version_unification.py` 9 passed。
>
> **全量运行备注（环境限制，非代码缺陷）**：全量 `pytest -q` 中 `tests/test_backtest/test_attribution_analyzer.py` 16 例在沙箱下 `tmp_path` 报 `PermissionError: [WinError 5] ... \Temp\pytest-of-Peng`（测试基础设施无法访问系统临时目录）；同文件加 `--basetemp=<仓内目录>` 复跑 **16 passed**，确认与 P-006 改动无关。其余无新增失败。

## 3. 接口验收

### 3.1 `board_of`（DESIGN §4.1）

| 验收项 | DoR（前置） | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|
| 签名与返回类型一致 | 函数存在 | `board_of(code) -> str`，取值 ⊆ {main,star,gem,bse,unknown} | ✅ | 代码 [tradability.py L96-119](file:///f:/Coding/factor_pipeline/backtest/tradability.py#L96-L119)：四条 `return` 字面量均 ∈ 五值；TP6-5 覆盖 5 类返回值 |
| 区间映射（D-6-4） | 同上 | main=000-004/600/601/603/605；gem=300-309；star=688/689；bse=43/83/87/92 | ✅ | 绿 TP6-5：`600/601/603/605` 与 `000..004`→main；`300..309`（含 `302132/309999`）→gem；`688/689`（含 `689009`）→star；`43/83/87/92`（`920001`）→bse |
| 输入归一化 | 同上 | `int` / `'600000'` / `'600000.SH'` 均正确；非 6 位数字 → `unknown` | ✅ | 绿：`600000`(int)、`'600000'`、`'600000.SH'`→main（先 `split(".")` 再 `zfill(6)`）；`'abc'`/`''`/`900001`/`200001`→unknown |
| 未知不抛错、不默认 main | 同上 | `unknown` 为普通返回值（INV-3） | ✅ | 代码 L106/L109/L119 三处 `return "unknown"`，无异常、无 main 兜底；TP6-5 断言未映射代码逐字返回 `unknown` |

### 3.2 `limit_price`（DESIGN §4.2）

| 验收项 | DoR（前置） | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|
| 签名不变 | 函数存在 | `limit_price(prev_close, pct, side="up")` | ✅ | 代码 [L122](file:///f:/Coding/factor_pipeline/backtest/tradability.py#L122) 签名逐参一致；T390-27~35 既有调用零改动通过 |
| 返回形态 | 同上 | 标量入参 → `float`；数组入参 → 同形状 `ndarray` | ✅ | 代码 L153-155：双标量 → `float(out)`；数组路径 TP6-2 20,008 样本返回同形状 ndarray |
| 三分支正确 | 同上 | ① `|lc-pc|<1 → pc±1`；② `lc<1 → 1`；③ 其余整数分 half-up | ✅ | 代码 L147-150：③ `(pc*scale+5000)//10000`、① `np.where(|lc-pc|<1, pc±step, lc)`、② `np.where(lc<1, 1, lc)`；TP6-1/TP6-3 逐值命中 |
| NaN 安全 | 同上 | NaN 入 → NaN 出，无整型下溢（先掩码后 `int64`） | ✅ | `_to_cents` L82-93 先 `np.isfinite` 掩码再写 `int64`；L152 `np.where(valid, …, np.nan)`；TP6-2 NaN→NaN |
| 非法入参抛错 | 同上 | `side` 非法 / `pct` 越界 → `ValueError` | ✅ | 代码 L129-130（`side` ∉ {up,down}）与 L135-138（`pct` ∉[0,1]）；TP6-2/TP6-3 负例 `1.5`/`-0.1`/`"flat"` 均 ValueError |

### 3.3 `compute_limits`（DESIGN §4.3）

| 验收项 | DoR（前置） | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|
| 签名一致 | 函数存在 | `(prev_close, pct, ref=None, is_st=None, low_price_st_rule=True)` → `(up, down, unknown)` | ✅ | 代码 [L158-159](file:///f:/Coding/factor_pipeline/backtest/tradability.py#L158-L159) 逐参一致；L191 返回 `(up, down, unknown)` 三元组 |
| `ref` 优先于 `prev_close` | 同上 | 提供 `ref` 时基准为 `ref`；无效 `ref` → `unknown` | ✅ | 代码 L168-176：`ref is not None` 时 `basis=ref`，`~isfinite(ref) \| ref<=0` 并入 unknown；TP6-6 `ref=5` → `5.50/4.50` |
| `unknown` 成因完备 | 同上 | 非有限 prev/pct、ref 无效、`prev<=0`、`ref<=0`、未知板块 | ✅ | 代码 L170-176 覆盖前四类；未知板块由 `_pct_matrix` 留 NaN（L219-228 以 `codes=-1` 跳过写入），apply 侧 `unk \|= ~np.isfinite(pct)` 并入（L382）；空面板 9 键全 0 验证 |
| 低价 ST 分支 | 同上 | `is_st & prev_cents<10` → `up=prev+1`、`down=max(prev-1,1)` | ✅ | 代码 L181-187：`low = st & pc_ok & prev>0 & pc<10` → `up=(pc+1)/100`、`down=max(pc-1,1)/100`；TP6-12 `cents=1..9` 全扫描与通用三分支逐值等价 |

### 3.4 `apply_tradability`（DESIGN §4.4）

| 验收项 | DoR（前置） | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|
| 位置调用完全兼容 | 既有调用未改 | 前 12 个位置参数顺序不变，新 kwargs 追加在 `policy` 后 | ✅ | 代码 [L304-306](file:///f:/Coding/factor_pipeline/backtest/tradability.py#L304-L306)：`target_w..policy` 12 位置参数顺序不变，`adj/is_delisting/no_limit/ref` 追加于 `policy` 后；T390-27~35 回归全通过 |
| `is_st` 双形态 | 同上 | `(N,)` 与 `(T,N)` 均可运行且结果自洽 | ✅ | `_as_bool_matrix` L294-301 接受 `(N,)`（broadcast）与 `(T,N)`；`test_is_st_2d_supported` 两形态结果自洽 |
| `ref`/`adj` 优先级与缺失前置 | 同上 | `ref` 优先；仅 `adj` 时任一 `adj[t]/adj[t-1]` 无效 → `ref=NaN` → unknown，不回退 prev | ✅ | 代码 L362-367（ref 优先、其次 `_ref_from_adj`）；`_ref_from_adj` L246-253 任一非有限/非正 → NaN；TP6-7 `adj=[2,2,NaN]` → `limit_unknown=1`、`blocked_buy=0` |
| 报告 9 键 | 同上 | 键集合 = 9 键（6 旧 + 3 新），恒 `int`（INV-9） | ✅ | 代码 L374-376 九键字面量、L450-459 全部 `+= int(...)`；`test_empty_panel_report_zero` 9 键全 0 且 `type is int` |
| `board="unknown"` 不抛错 | 同上 | 该格计入 `limit_unknown`，不抛 `ValueError` | ✅ | 代码 L339-342 白名单含 `unknown`；TP6-7 与 16 组合：unknown 格计 `limit_unknown` 并放行（`eff=0.5`） |

### 3.5 `TradabilityInputs`（DESIGN §4.5）

| 验收项 | DoR（前置） | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|
| frozen + `eq=False` | 可导入 | `@dataclass(frozen=True, eq=False)`，对 ndarray 字段无 `==` 歧义 | ✅ | 代码 [L257](file:///f:/Coding/factor_pipeline/backtest/tradability.py#L257) `@dataclass(frozen=True, eq=False)`；`eq=False` 避免 ndarray 字段 `==` 产生数组真值歧义 |
| 字段与默认值一致 | 同上 | 10 必填（6 行情面板 + `dates/board/is_st/adj`）+ `is_delisting/no_limit/policy/meta` 默认 `None`（D-6-11） | ✅ | 代码 L260-273：`close/high/low/open_/volume/suspended/dates/board/is_st/adj` 无默认值，其余 4 字段默认 `None`；与 DESIGN §4.5 一致（原 DoD「6 必填 + adj」为 6 行情面板简称，此处按代码事实订正） |
| 无方法、只承载数据 | 同上 | 类体无业务方法 | ✅ | 类体仅 14 个字段声明（L260-273），无方法；导入/构造零副作用 |

### 3.6 `build_tradability_inputs`（DESIGN §4.6）

| 验收项 | DoR（前置） | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|
| 签名一致 | 函数存在 | `(close, high, low, open_, volume, suspend, name, adj, list_date=None, policy=None, st_overrides=None)` → `(TradabilityInputs, meta)` | ✅ | [tradability_inputs.py L24-26](file:///f:/Coding/factor_pipeline/backtest/tradability_inputs.py#L24-L26) 逐参一致；L151 返回 `(inputs, meta)` |
| 网格对齐 | 传入错位面板 | 以 `close.index/columns` 为唯一网格，缺失填 NaN/False | ✅ | `_frame` L17-21 以 `close` 的 index/columns `reindex` + `fillna(NaN/False/"")`；`test_grid_alignment` 通过 |
| meta 键齐全 | 同上 | 13 键 + `no_limit_source` / `st_calibration_source` 取值域正确 | ✅ | 代码 L128-144 13 键；`no_limit_source` ∈ {list_date, delisting_only}（L84-85）、`st_calibration_source` ∈ {none, coverage_table}（L93-96）；`test_meta_keys_and_price_basis` 键集逐字相等 |
| 纯函数无 IO | 代码只读 | 无 `open` / `read_*` / 网络调用 | ✅ | 文件仅 import `Counter`/`numpy`/`pandas`/`tradability`；全文无 `open(`/`read_`/requests/socket 调用 |

### 3.7 引擎（DESIGN §4.7）

| 验收项 | DoR（前置） | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|
| 构造签名一致 | 类可导入 | `(dl, config=None, fwd_returns=None, tradability_inputs=None)` | ✅ | [engine.py L63-69](file:///f:/Coding/factor_pipeline/backtest/engine.py#L63-L69) 逐参一致，`tradability_inputs` 为末位可选参数 |
| 启用前校验 | 传入非法 inputs | 形状/dates/board/`adj=None` → `ValueError`（含字段名与期望形状） | ✅ | `_validate_tradability_inputs` L130-160：7 面板形状、`adj is None` →「tradability 需要 adj（判定需除权参考价基准）」、`dates/board/is_delisting/no_limit` 形状；`test_tradability_inputs_validation` 覆盖各分支 |
| 启用时结果 6 字段 | 启用态可跑 | `tradability` 键含 `report/meta/price_basis/leg_scope/short_leg_unmodeled/turnover_basis` | ✅ | 代码 L304-311 六字段字面量；TP6-9 断言 `price_basis="raw_adj_ref"`/`turnover_basis="effective_long_only"`；TP6-10 断言 `leg_scope="long_only"`/`short_leg_unmodeled=True` |
| 未启用零新增键 | `tradability_inputs=None` | `results[factor]` 键集合与 v3.9.8 完全一致（INV-1） | ✅ | 代码 L288-289：`inputs is None` 走 `compute_turnover(positions)` 原路径；TP6-11 基线字面量逐位一致且结果无 `tradability` 键 |

## 4. 不变式验收

| 不变式（DESIGN §8） | 验证方法 | 状态 | 证据 |
|---|---|---|---|
| INV-1 默认零变更 | TP6-11：`summary()` + `turnover` 与 Step 9 前基线字面量逐位一致；无 `tradability` 键 | ✅ | 绿：5 指标 `rank_icir=-0.25880207857362303`/`pearson_icir=-0.30599173567954446`/`hit_rate=0.36363636363636365`/`spread=-0.1610540425109819`/`mean_rank_ic=-0.10649350649350647` + `turnover=[1.5,1.0,2.0,1.5,2.0,1.0,1.0,1.0,1.0,1.5,1.5]` 逐位一致；无 `tradability` 键（基线于改动前采集） |
| INV-2 整数分 half-up | TP6-1/2 + 静态断言 `tradability.py` 无 `np.round`/`np.rint` 参与限价；NaN→NaN | ✅ | 绿：20,008 样本 vs `Decimal(ROUND_HALF_UP)` 差异 0；`grep` 无 `np.round(`/`np.rint(`；NaN→NaN |
| INV-3 未知不默认 | TP6-5（`board_of`）+ TP6-7（`limit_unknown`）；无 10% 兜底 | ✅ | 绿：未映射代码→`unknown`；unknown 格计 `limit_unknown`、不进 `blocked_*`；源码无 10% 兜底分支 |
| INV-4 除权基准 | TP6-6（`ref≠prev`）+ TP6-7（缺失不回退） | ✅ | 绿：`ref=5` → `5.50/4.50`（≠ 10 元基准的 11.00）；`adj=[2,2,NaN]` → `limit_unknown=1`、不回退 prev |
| INV-5 计数互斥 | TP6-7 + 16 组合优先级枚举；每格至多入一桶 | ✅ | 绿：16 组合读数 `blocked_suspend=8 / limit_unknown=2 / blocked_buy=1`，7 格自由成交；每格至多一桶 |
| INV-6 ST/退分治 | TP6-8 两侧（派生 + apply）；`退` 不走 5% | ✅ | 绿：构建器 `ST测试`→is_st 且 `is_delisting=False`、`退市测试`→is_delisting 且 `is_st=False`；apply 侧 ST 5% 封板 vs 退市普通档放行 |
| INV-7 空头腿不动 | TP6-10 逐位断言 `effective[neg] == positions[neg]` | ✅ | 绿：`np.array_equal(effective[neg], positions[neg])` 为真；`short_leg_unmodeled=True` |
| INV-8 规则表不变 | `DEFAULT_LIMIT_RULES` 零改动；T390-31/35 回归通过 | ✅ | 绿：`DEFAULT_LIMIT_RULES` 11 条与 v3.9.8 逐字一致（本轮无 diff）；T390-27~35 全通过 |
| INV-9 报告类型 | 9 键恒 `int`；空面板全 0；键集 6→9 属有意变更（D-6-9） | ✅ | 绿：`test_empty_panel_report_zero` 9 键全 0 且逐值 `type is int`；TP6-7 同步键集断言 |

## 5. 错误处理验收

| 错误场景（DESIGN §7） | 触发方式 | 预期行为 | 状态 | 证据 |
|---|---|---|---|---|
| 数组形状不符 `(T,N)` | 传 `(N,T)` 或错维 | `ValueError`，消息含字段名与期望形状（TP6-9 子断言） | ✅ | 代码 L331-335 逐字段校验；TP6-9 `close[:2]` → ValueError（含「形状应为」）；`test_tradability_inputs_validation` 覆盖引擎侧 |
| `dates` 长度 ≠ T | 截短 `dates` | `ValueError`（「dates 长度应为 T」） | ✅ | 代码 L343-344；`test_error_table_contracts` 截短 dates → ValueError |
| `board` 未知值 | 传入未映射代码 | 不抛错；该格 `limit_unknown`，meta `unknown_codes` 披露 | ✅ | 代码 L339-342 仅拒非法字符串（`unknown` 合法）；构建器 meta `unknown_codes`（前 20 个）；TP6-7 计 `limit_unknown` |
| 已映射板块规则无命中 | 规则窗口外日期 | `ValueError`（「无涨跌幅规则: board=… date=…」），沿用 `rule_pct` | ✅ | `rule_pct` L74-75 消息「无涨跌幅规则: board=%s is_st=%s date=%s」；`test_error_table_contracts` bse 2020（规则始于 2021-11-15）→ ValueError |
| `adj` 缺失/非正/单侧缺失 | 构造 NaN/0/单侧 NaN | 该格 `limit_unknown`，不回退 prev，`blocked_*` 不增加（TP6-7） | ✅ | `_ref_from_adj` L246-253 → NaN；TP6-7 `limit_unknown=1`、`blocked_buy=0`；构建器 `adj=None` → ValueError |
| `prev_close` NaN（含 t=0） | 首行或构造 NaN | 非停牌 → `limit_unknown`；停牌 → `blocked_suspend` | ✅ | `test_error_table_contracts`：非停牌 NaN → unknown 放行；停牌 + NaN → `blocked_suspend` |
| `high/low` NaN | 构造 NaN | 视为无封板证据（不 block），不抛错 | ✅ | `test_error_table_contracts`：NaN 比较为 False → 不 block、无异常 |
| `pct` 有限但 ∉ [0,1] | `limit_price(10, 1.5)` | `ValueError`（「pct 越界」）（TP6-2 负例） | ✅ | 代码 L135-138（消息「pct 必须 ∈ [0, 1]」）；TP6-2 `1.5`/`-0.1` 均 ValueError |
| 引擎启用但 `adj is None` | `TradabilityInputs(adj=None)` | `ValueError`（「tradability 需要 adj」）（TP6-9 子断言） | ✅ | 代码 L140-142；`test_tradability_inputs_validation` 与 TP6-9 均断言该消息 |
| 引擎启用但网格不匹配 | 传不同 T/N 的 inputs | `ValueError`，含字段名 + 期望/实际 | ✅ | 代码 L135-160 逐字段（含实际形状插值）；`test_tradability_inputs_validation` |
| `np.round` 残留调用 | 静态检索 `tradability.py` | 测试失败（TP6-2 附静态检查） | ✅ | TP6-2 静态断言源码无 `np.round(`/`np.rint(`，当前通过 |

## 6. 性能验收

| 性能指标 | 目标 | 实测 | 状态 |
|---|---|---|---|
| `apply_tradability`（T=787×N=5,688 窗口） | ≤ 2 s | **1.463 s**（peak 272.8 MB，本机 3.13.5） | ✅ |
| 内存（6 个 `(T,N)` float64 ≈ 216 MB） | 只借用引用，不复制 | `np.shares_memory(inputs.close, close) == True`（构建器 `reindex` 后单次 `to_numpy`；引擎只传引用） | ✅ |
| 构建器（5,688 列 × 787 日） | ≤ 5 s | **3.676 s**（peak 604.3 MB；初版 7.678 s，名称派生改 `np.fromiter` 单遍后达标） | ✅ |
| 引擎每因子开销 | 相对 IC 计算可忽略；仅启用时执行 | 同窗口 default **12.516 s** vs enabled **13.746 s**（+1.23 s，且仅在启用时发生） | ✅ |

## 7. 兼容性验收

| 环境 | 版本 | 状态 | 说明 |
|---|---|---|---|
| Python | 3.9 | ✅ | 静态核验：无 3.10+ 语法（未用 `match`/PEP 604 `\|` 联合注解）；`frozen dataclass` / `np.broadcast_arrays` / `Decimal(ROUND_HALF_UP)` 均 3.9 可用；未跑 3.9 实机 |
| Python | 3.10-3.13 | ✅ | 实测 **3.13.5**（Anaconda, MSC v.1929）；未跑版本矩阵 |
| numpy / pandas | 仓内锁定组合 | ✅ | 实测 numpy **2.1.3** / pandas **2.2.3**；仅稳定 API（无 `np.float_`；限价不用 `np.round`） |
| decimal（测试侧） | stdlib（3.9+） | ✅ | `from decimal import Decimal, ROUND_HALF_UP`，仅 `test_tradability.py` 使用 |
| OS | Windows | ✅ | 本机 Windows 实跑全流程；代码无 shell 依赖 |

## 8. ADD 审计（Step 10）

### 8.1 Spec 质量门（Phase 0）

> 独立只读审计（2026-11-23，异构视角），评分依据见 §8.2 处置与 §2-§7 证据链。

| 维度 | 得分（0-1） | 说明 |
|------|-----------|------|
| 可测试约束 | 1.0 | INV-1~9、TP6-1~12 全部有对应非恒真断言（TP6-10 半间接性登记为 P3-③） |
| 模块映射 | 1.0 | 3 模块 ↔ 3 文件一一对应；`factor_metrics.py`/`panels.py` 零改动，无越界 |
| 接口契约 | 1.0 | DESIGN §4.1~§4.7 逐参核对一致（apply 16 参顺序、Inputs 14 字段、meta 13 键、引擎 6 字段挂载） |
| 修正项 | 0.9 | Step 4 P2-1~4 / Step 6 P2-1~2 修复均落地；唯 P2-3 原缺鉴别测试（Step 10 P2-① 已补 `test_tp6_9b`） |
| 跨模块契约 | 1.0 | `tradability.py` 仅 stdlib+numpy 无 pandas/IO；`_ref_from_adj` 为唯一除权公式；engine 无重复限价逻辑 |
| **总分** | **4.9/5** | **档位**: **A** |

### 8.2 ADD 审计发现

> 审计结论 **PASS_WITH_FIXES —— 0×P1 + 1×P2 + 5×P3**；P1 扫描证据：整数分公式 5 档 × 双侧 × 200k 全扫描 vs 独立 `Decimal(str)` 基准，mismatch 恰为分支①设计触发格（0.1% 档 tie 归位 prev）；`np.round`/`np.rint` 限价路径零残留；桶互斥 16 组合 + 分支序（①→②）读数 `0.01 down→0.01 / up→0.02` 正确；20% 档 tie 恒 0 再证。

| 严重性 | 发现 | 证据 | 处置 |
|--------|------|------|---------|
| P1 | 无 | 见上方 P1 扫描证据 | — |
| P2-① | Step 4 P2-3（prev_close 派生源 = `inputs.close`）原无鉴别测试：TP6-9/10 中 dl 与 inputs 共用同一 close 数组，若引擎误用 `dl.close` 回归仍全绿 | [test_engine.py](file:///f:/Coding/factor_pipeline/tests/test_backtest/test_engine.py)（共用数组）；[engine.py L292-294](file:///f:/Coding/factor_pipeline/backtest/engine.py#L292-L294) 实现正确 | **已修复**：新增 `test_tp6_9b_prev_close_derived_from_inputs`——仅改 `inputs.close[0,0]`（10→12）与 dl 脱钩，断言 `blocked_buy` 1→0 翻转（若误用 dl.close 则仍为 1）；4 passed |
| P3-① | CHECKLIST §2.1 TP6-2 证据算术误写：2,501×4×2 = 20,008 写作 10,004（断言 `total>=10000` 不受影响） | test_tradability.py L171 `arange(100,2601)` → 2,501 值 | **已订正**（§2.1/§3.2/§4 三处 → 20,008） |
| P3-② | 一字板 eps 源不一致：构建器用常量 `_EPS`，apply 用 `policy.eps`，自定义 policy 时 meta/report 可能漂移 | tradability_inputs.py L124 vs tradability.py L393 | **登记后续小批次**（P-020） |
| P3-③ | 覆盖缺口：apply 侧 `one_word_up/down` 无正向计数断言；`apply_tradability(ref=)` 直传路径（D-6-7）未测；TP6-10 断言作用于测试本地重算数组（positions 含空头，非恒真） | tradability.py L351-363/L392-397；test_engine.py L832-838 | **登记后续小批次**（P-020） |
| P3-④ | 构建器 `list_date` 键未归一化（无 `split/zfill`），与 `st_overrides` 路径不一致；裸代码索引 × 带后缀列时 IPO 豁免静默跳过 | tradability_inputs.py L75 vs L100 | **登记后续小批次**（P-020） |
| P3-⑤ | 审计员称 IMPL §3.3-1 含「有限性校验」表述，实际无此措辞 | grep IMPLEMENTATION.md 全文无「有限性」；[L204](file:///f:/Coding/factor_pipeline/spec/p006-tradability-engine-integration/IMPLEMENTATION.md#L204) 原文即「形状/dates/board/`adj is not None`」与实现逐字一致 | **复核不成立**，无需修订 |

### 8.3 ADD Iron Law 检查

- [x] 断言恒真式已扫描（TP6-2 属性测试需含非恒真对照；TP6-11 基线需为改动前采集）—— **PASS**：TP6-2 有非恒真对照（独立探针证实 `np.round` 在 tie 上大量翻转：10% up 5270/20000、30% down 14018/20000）；TP6-11 基线硬编码于 test_engine.py 且经审计独立重放逐位复现（§8.4）
- [x] 单文件检查盲区已扫描（一字板统计在构建器与 `apply` 两侧同一表达式；`ref` 计算单点）—— **PASS**：两侧表达式语义一致；`_ref_from_adj`（tradability.py）为全仓唯一除权公式（builder 与 apply 均调用）；盲区仅 P3-②（eps 源）
- [x] 设计文档独有约束有测试（D-6-1~17 逐条映射证据）—— **PASS**：抽查 9 条 ≥6——D-6-1→test_error_table_contracts、D-6-2→test_tp6_6、D-6-3→test_st_overrides_calibration、D-6-4→test_tp6_5、D-6-9→test_empty_panel_report_zero、D-6-13→test_meta_keys_and_price_basis、D-6-14→test_tp6_9、D-6-15→test_tp6_2、D-6-16→test_report_bucket_priority（未测 D-6-5/7/12 → P3-③ 登记；D-6-17 设计豁免）
- [x] 修正阻断性项有测试（Step 4 P2-1~4、Step 6 P2-1/2 的修复均有对应用例）—— **PASS**：Step4 P2-1→test_report_bucket_priority、P2-2→test_empty_panel_report_zero、P2-4→test_no_limit_source_delisting_only、P2-3→原缺（P2-① 已补 test_tp6_9b）；Step6 P2-1→文档订正、P2-2→test_tp6_7 两半（apply+meta）

### 8.4 独立复核 INV-1（默认路径零变更）

> 审计员独立构造 `rng(20261123)`、T=12/N=6、`top_n=2` 合成盘重放（临时脚本于 %TEMP%，用后已删）：5 指标 + turnover 与基线字面量**逐位一致**（`rank_icir=-0.25880207857362303` 等，见 §4 INV-1）；结果无 `tradability` 键、键集合 = 9 个 v3.9.8 键。**INV-1 成立**（实施方 TP6-11 + 审计方双重复核）。

## 9. 文档完整性

| 文档 | 存在 | 与实现一致 |
|------|------|----------|
| RESEARCH.md | ✅ | ✅（v1.4；Step 8 引用复核 PASS） |
| DESIGN.md | ✅ | ✅（v1.3；§15 记录 Step 8 复审处置，口径与代码落地一致） |
| IMPLEMENTATION.md | ✅ | ✅（v1.3；§15 记录 Step 9 实施与红→绿读数） |
| CHECKLIST.md（本文件） | ✅ | ✅（§2-§8 全部回填；§10.1 102/102） |
| ADR（如有） | ✅（本批无独立 ADR，教训内联于 DESIGN §2.2） | ✅ |
| 开发日志 | ✅（CHANGELOG v3.9.9 条目） | ✅（half-up / opt-in 接入 / 报告 9 键三要点；红→绿读数见 §2.6） |

## 10. 验收结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 15 | 15 | 0 | 0 |
| 功能 | 25 | 25 | 0 | 0 |
| 接口 | 29 | 29 | 0 | 0 |
| 不变式 | 9 | 9 | 0 | 0 |
| 错误处理 | 11 | 11 | 0 | 0 |
| 性能 | 4 | 4 | 0 | 0 |
| 兼容性 | 5 | 5 | 0 | 0 |
| ADD 审计 | 4 | 4 | 0 | 0 |
| **总计** | **102** | **102** | **0** | **0** |

> **统计口径（RULE-2）**：上表来自本文件**逐项核对**（每项均有独立状态标记），非事后汇总推算。当前态：Step 10 完成——§1-§7 共 98 项 ✅（Step 9）；§8 ADD 审计 4 项 ✅（Step 10：§8.1 质量门 4.9/5 档位 A、§8.2 发现 0×P1+1×P2+5×P3 已处置、§8.3 Iron Law 4/4、§8.4 INV-1 独立重放成立）。每行满足「总数 = 通过 + 失败 + 待办」，总计行为 8 类按列求和（102 = 15+25+29+9+11+4+5+4 ✓；通过 102 = 98 + 4 ✓；待办 0 ✓）。
>
> **规范形态（P-050 交付 A，由 `dc_validator` M4 分支② 机械校验）**：① 章节号固定 `### 10.1 验收统计`；② 数值单元格为纯十进制整数（`**N**` 加粗允许）；③ 逐行 `总数 = 通过 + 失败 + 待办`，总计行按列求和。

### 10.2 验收决定

- [x] **验收通过**：所有 P1 项通过，无阻塞性问题——§1-§8 共 102/102 项通过（Step 10 ADD 审计 PASS_WITH_FIXES：0×P1 + 1×P2 已就地修复、5×P3 中 1 项复核不成立、1 项文档订正、3 项登记 P-020 后续小批次）；全量回归 2143 passed / 34 skipped / 0 failed

### 10.3 签字

| 角色 | 签字 | 日期 |
|------|------|------|
| 实施者 | | |
| 审查者 | | |

## 11. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|------|--------|------|------|
| Step 8 文档一致性独立 pass（§1 15 项） | 独立复审员 | 2026-11-23 | 已完成（PASS_WITH_FIXES 已处置，见 §1.5） |
| Step 9 TDD 红→绿（TP6-1~12 + 默认基线，§2-§7 回填） | 实施者 | 2026-11-23 | 已完成（44 passed / 20 skipped；红→绿见 §2.6） |
| Step 10 ADD 审计（§8 + 统计汇总） | 独立审计员 | 2026-11-23 | 已完成（PASS_WITH_FIXES 4.9/5 档位 A；P2-① 就地修复，见 §8.2） |
| 全量回归取证 | 实施者 | 2026-11-23 | 已完成（2143 passed / 34 skipped / 0 failed，964.31 s） |
| P-020 后续小批次（P3-②③④：eps 源统一 / one_word 正向计数+ref= 路径补测 / list_date 键归一化） | — | — | 待排期（见 PROGRESS.md） |
| 更新 PROGRESS.md（P-006 → done） | — | — | 已完成 |
| 记录开发日志（红→绿读数 + 审计结论） | 实施者 | 2026-11-23 | 已完成（CHANGELOG v3.9.9 + §2.6） |
| git 提交 | 待用户指令 | — | 未授权 |
