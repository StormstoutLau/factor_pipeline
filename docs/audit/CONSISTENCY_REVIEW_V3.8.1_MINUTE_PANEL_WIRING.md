# CONSISTENCY REVIEW — v3.8.1 真实分钟面板编排接线（步骤 8）

> **版本**: v1.0（2026-11-20）
> **对应调研**: [RESEARCH_V3.8.1_MINUTE_PANEL_WIRING.md](../research/RESEARCH_V3.8.1_MINUTE_PANEL_WIRING.md) **v1.2**（§9 步骤 2 复审闭环）
> **对应设计**: [DESIGN_V3.8.1_MINUTE_PANEL_WIRING.md](../private/DESIGN_V3.8.1_MINUTE_PANEL_WIRING.md) **v1.1**（§13 步骤 4 复审 PASS_WITH_FIXES + R2 勘误 2026-11-20）
> **对应实施**: [EXECUTION_V3.8.1_MINUTE_PANEL_WIRING.md](../EXECUTION_V3.8.1_MINUTE_PANEL_WIRING.md) **v1.2**（步骤 6 复审 PASS_WITH_FIXES F1-F10 见其 §10；步骤 8 修正 M2/M3/M6/M7/M8/M11）
> **对应清单**: [CHECKLIST_V3.8.1_MINUTE_PANEL_WIRING.md](CHECKLIST_V3.8.1_MINUTE_PANEL_WIRING.md) **v1.1**（步骤 7 产出 84 项；步骤 8 修正 10 处）
> **方法**: 四方文档逐条 grep 取回原文比对（全部 **E4 级证据**——文档间逐字比对；代码未实施，不读实现）
> **结论**: **PASS** —— CRITICAL 0 / MAJOR 0 / MINOR 11，全部当场修正；设计与调研零改动

---

## §1 结论

对调研 / 设计 / 实施 / 清单四份文档按 **8 个维度**做交叉对账（版本锚点、W→E→测试落点、22 例分布、数值口径、门禁命令、不变量、修复链引用、台账计数）。

- **无 CRITICAL / MAJOR**：11 处偏差全部为 **MINOR 文档级漂移**（计数错、编号矛盾、skipif 条件缺失、清单引用滞后），不涉及数值口径、架构决策或门禁裁定；
- **全部当场修正**：CHECKLIST 10 处编辑（v1.0→v1.1）、EXECUTION 13 处编辑（v1.1→v1.2）；设计与调研零改动（设计 W10 的 `--no-panel-cache` 以实施注记 R12 披露，不回改设计正文）；
- 修正后四份文档在受约束口径上完全一致：config 19 字段（删 `tau_max_minutes`）/ 覆盖度门禁 ≥0.95 中位 · ≥0.90 最差 · 深主板>0 / 22 例分布 19+2+门禁 / 版本锚点 5 处代码 + CHANGELOG 共 6 处 / 全量 **2048 passed / 15 skipped / 0 failed** / 默认 `out/capacity_impact.json` SHA256 `82728CE1…` 逐位不变 / 包版本 **3.9.1**（A1）。

**可以进入步骤 9（TDD 实施）。**

---

## §2 一致性矩阵（8 维）

| # | 维度 | 上游 → 下游 | 对账结果 |
|---|------|------------|---------|
| 1 | 版本锚点链 | EXECUTION §3.1（6 处）↔ CHECKLIST §4/§7 ↔ 裁决 A1（3.9.1） | M3 修正前 EXECUTION 三处写作「6 锚点 + 2 测试常量 + CHANGELOG」（重复计数）；修正后统一为「**5 处代码锚点 + CHANGELOG，共 6 处**」，三处一致 |
| 2 | W→E→测试落点 | 设计 W1-W10 ↔ EXECUTION §1 E0-E6 + S1-S4 ↔ §5.1 T381-01…22 | M2/M6/M7 修正后：W1-W10 每条均有 E 任务落点 + 至少一个 T381 用例或全量门禁覆盖；W10 的 `--no-panel-cache` 以单旗标 `--panel-cache`（默认关）等价实现，R12 披露 |
| 3 | 测试分布 22 例 | EXECUTION §1/§5.1/§5.2 ↔ CHECKLIST §2-E6/§3/§5-G1 ↔ PROJECT_STATUS | 修正 M1/M2 后三方一致：`tests/test_minute_panels.py` **19** 例（T381-01…18 + 20）+ `tests/test_execution_capacity.py` **2** 例（T381-19/21）+ 全量门禁 **1**（T381-22）= **22** |
| 4 | 数值口径 | 调研 B/U ↔ 设计 W ↔ EXECUTION §2 ↔ CHECKLIST §3 DoD | 五方一致：config **19 字段**（16−1+4，删 `tau_max_minutes`）；覆盖度门禁 ≥0.95 中位 / ≥0.90 最差 / 深主板>0；partial_month ≥20 日；观测样本 ≤200,000；`fill_ratio>0.30 → c_interval_only`；`cost(h)=(20/h)·AUM·turnover·2·(fee+impact)/1e4`；`plateau_sd = AUM×std(月超额)`（步骤 6 F3 修正后，月尺度）；窗口点 73−W+1；κ 情景 `sorted({1.0, cfg.kappa, 2.0})`；`block_size_mode` 校验型仅 `auto` |
| 5 | 门禁命令与读数 | EXECUTION §5 ↔ CHECKLIST §5 G1-G10 ↔ PROJECT_STATUS | M4/M9 修正后一致：全量 **2048 passed / 15 skipped / 0 failed**（2026+22），环境性 skip 须附理由；G8 版本号 grep 限定 `--include=*.py --include=*.toml`（.md 含历史版本号，「零命中」不可满足）+ CHANGELOG 人工核对；默认 SHA256 `82728CE1…` 逐位不变 |
| 6 | 不变量与兼容性 | 设计 §0.3 六条不变量 ↔ EXECUTION §2/§4 引用 ↔ CHECKLIST §4 兼容性 12 项 | 语义包含、无冲突：EXECUTION 引用不变量 1（默认路径逐位）/ 3（禁止边 `backtest.execution` 不 import scripts）/ 4（runner 固定键集零改动）/ 5（警告必须消费，步骤 6 F4 修复后闭合）；清单 §4 为超集（另含 `build_panels` 仅加键、依赖零增、Py3.9 AST、缓存不入库、版本锚点） |
| 7 | 修复链引用 | 步骤 6 F1-F10 ↔ EXECUTION §10 ↔ CHECKLIST 红形态/DoD ↔ 设计 R2 勘误 | 闭合：F1-F10 修正已写入 EXECUTION v1.1 正文与 §10.2；清单红形态与其对齐（M5 修正 T381-15 红形态后）；设计 R2 勘误已于步骤 6 回改；F3（plateau_sd 月尺度）已进矩阵维 4 口径 |
| 8 | 台账计数 | CHECKLIST 84 项（RULE-2）↔ §1-§9 ↔ PROJECT_STATUS 引用 | 逐节复算一致：§2 E 任务 **7** + §3 测试 **22** + §4 兼容性 **12** + §5 门禁/性能/证据出口 **21**（10+5+6）+ §6 风险/回滚 **14**（9+5）+ §7 文档同步 **8** = **84**；M10 修正文件数（7→8）后，§4-5 与头部档位行均为「新增 2 + 修改 5 + 追加 1」 |

---

## §3 偏差与处置（M1-M11）

| # | 级别 | 位置 | 偏差 | 处置（落点） |
|---|------|------|------|-------------|
| M1 | MINOR | CHECKLIST §2-E6 / §5-G1 | 测试文件分布计数错：E6 写 3 例（capacity 实为 2：T381-19/21）；G1 未区分 T381-22 是全量门禁（非测试文件用例） | E6 改「2 例（T381-19/21），T381-22 为全量门禁」；G1 改「0 failed（环境性 skip 附理由）+ 分布 19/2/门禁」 |
| M2 | MINOR | EXECUTION §1-E0 | E0 验收出口 `-k "loader"`（T381-01/02/05/06）与 §5.2 批次矛盾（06 属 R2、缺 03/04） | 改为 `（T381-01/02/03/04/05）`，与 `-k "loader"` 选择器及 R1/R2 批次一致 |
| M3 | MINOR | EXECUTION §3.1 标题 / 待决表 A / §10.4-A1 | 版本锚点重复计数：「6 处机械同步 + 2 处测试常量」实为 5 处代码锚点 + CHANGELOG = 6 处 | 三处统一改为「5 处代码锚点 + CHANGELOG，共 6 处」 |
| M4 | MINOR | CHECKLIST §5-G1/G4 | 未容忍环境性 skip：`E:\Level 1 Data` / `E:\Ashare_data` 缺失时 T381-17/18/20 skip 会破坏「2048 passed」字面读数 | G1/G4 加「环境性 skip 须附理由，不判失败」 |
| M5 | MINOR | CHECKLIST §3-T381-15 | 红形态写 `ImportError: resolve_evidence_level`——该函数 v3.8.0 已存在，不可能红 | 改 `ImportError: MinutePanelBuilder`（E2 产物，真实红形态） |
| M6 | MINOR | EXECUTION §5.2 | 红→绿批次分配矛盾：R5 混入 loader 级 T381-03；R2 漏 03 | R2=T381-03/04/06/07（4 绿）、R5=T381-17/18（2 绿），与 §1 出口及 §5.1 文件归属一致 |
| M7 | MINOR | 设计 W10 ↔ EXECUTION §2.6.5 | W10 的 `--no-panel-cache` 未单独实现——`--panel-cache` 单旗标默认关，语义等价但无记录 | EXECUTION §2.6.5 args 块加注 + §10.3 新增实施注记 **R12**（CLI 面无冗余开关）；设计正文不回改 |
| M8 | MINOR | CHECKLIST §3 头 / EXECUTION §2.6 末 | T381-20 skipif 只写 `E:\Level 1 Data`，缺 `E:\Ashare_data`（该用例读日频基准） | 双落「skipif 条件叠加，缺任一即 skip」 |
| M9 | MINOR | CHECKLIST §5-G8 | 版本号 grep 未限文件类型：.md 文档含历史 3.9.0，「零命中」不可满足 | 加 `--include=*.py --include=*.toml` + CHANGELOG 人工核对 |
| M10 | MINOR | CHECKLIST §4-5（及头部档位行） | 文件数写 7，实际白名单 8（新增 2 + 修改 5 + 追加 1） | 改 8 并列明；头部档位行同步（M10 同类） |
| M11 | MINOR | EXECUTION §3.7 | 文档清单缺 CHECKLIST（步骤 7）与 CONSISTENCY_REVIEW（步骤 8） | 补齐两项 |

**修正落点统计**：CHECKLIST 10 处编辑（头部升 v1.1 + M1/M4/M5/M6/M8/M9/M10）；EXECUTION 13 处编辑（头部升 v1.2 + §0.2 两行 + M2/M3/M6/M7/M8/M11）。

---

## §4 编号与术语一致性

以下编号前缀存在跨文档复用，**保留不改号**，引用时以来源前缀消歧（本文件与后续步骤 9/10 引用一律带前缀）：

| 前缀 | 归属 | 消歧方式 |
|------|------|---------|
| **R1-R5** | ① 设计复审注记（设计 §13.4）；② 清单回滚点（CHECKLIST §6） | 「设计 R2」/「回滚 R3」 |
| **R6-R12** | 实施注记（EXECUTION §10.3，R12 为步骤 8 新增） | 「实施 R12」 |
| **F1-F6 / F1-F10** | ① 设计复审发现（设计 §13）；② 实施复审发现（EXECUTION §10.2） | 「设计 F3」/「步骤 6 F3」 |
| **M1-M11** | 本步骤（步骤 8）一致性发现 | 单义，不再复用 |
| **T381-01…22** | 测试用例编号 ↔ 描述性测试名 | 步骤 9 用描述性测试名，编号仅在清单/审查文档作映射（沿用 v3.8.0 惯例） |

单义编号（无冲突）：W1-W10（设计决策）、E0-E6（实施任务）、S1-S4（设计结构决策）、G1-G10（门禁）、X1-X9（风险）、B1-B18/U1-U14（调研）、A1-E（步骤 6 裁决）。

---

## §5 缺口检查（过度 / 欠设计）

| 方向 | 结论 |
|------|------|
| 欠设计 | **无**——W1-W10 每条均有 E 任务落点 + 至少一个 T381 用例或全量门禁覆盖（矩阵维 2/3）；面板契约 13 消费键均有读键方（§2.6.3/§2.6.4） |
| 过度设计 | **无新增**——M7 确认 CLI 面无冗余开关（R12）；未引入任何新依赖、新模块、新配置字段 |
| 设计未指定、实施注记兜底 | R6-R11（步骤 6 已披露）：滑窗容量取均值 / `impact_bps` 不随 h 变化 / 等距抽样替代分层抽样 / 日频基准口径差 / `daily` 参数保留对齐签名 / pyarrow skipif——均为**报告披露型**，不改变数值口径 |

---

## §6 审查通过的不变量（步骤 9 不得破坏）

设计 §0.3 六条不变量全文以设计文档为准（步骤 9 逐条遵守）；其中已在本步骤交叉验证引用一致的：

1. **默认路径逐位不变**：`python scripts/verify_capacity_impact.py`（无参数）输出与当前逐位一致，`out/capacity_impact.json` SHA256 `82728CE1…` 不变（不变量 1）；
2. **禁止边**：`backtest/execution/**` 不得 `import scripts` / `from scripts`，日频组合面板由脚本注入（不变量 3）；
3. **runner 零改动**：`run_calibration(cfg, capacity_fn, breakeven_fn, panels)` 固定键集，面板元数据经脚本 `attach_panel_meta` 后挂（不变量 4；步骤 6 F4 修复后警告合并进 `result['evidence_warnings']`，不变量 5 闭合）。

**门禁口径（已裁定，步骤 9/10 不得变更）**：

| 口径 | 值 | 来源 |
|------|-----|------|
| 全量测试 | **2048 passed / 15 skipped / 0 failed**（2026+22），环境性 skip 须附理由 | A1 裁决 + M4 |
| 默认快照 | `out/capacity_impact.json` SHA256 `82728CE1…` 逐位不变 | EXECUTION 头部纪律 |
| 包版本 | **3.9.1**（5 处代码锚点 + CHANGELOG，共 6 处，EXECUTION §3.1） | 步骤 6 A1 裁决 + M3 |
| 计数纪律 | CHECKLIST 汇总只能来自逐行状态计数（RULE-2） | 清单 §1 |
| 阶段纪律 | E0→E2→E1→E4→E6（S1），E3 并行；E6 必须在 E0-E5 全绿后 | 清单 §2 |

> **步骤 9 实测回注（2026-11-20）**：全量实测 **2047 passed / 15 skipped / 0 failed**（808.70 s）= 基线 2026 + 新增 **21** 个可执行用例；本表「2048」为含门禁 `T381-22` 自身的登记口径（门禁不是用例），二者不矛盾。计数口径已在 [CHECKLIST §3.4](CHECKLIST_V3.8.1_MINUTE_PANEL_WIRING.md) 显式说明。

---

## §7 对步骤 9 的约束（衍生命令）

1. **文件白名单（8 个，不得越界）**：
   - 新增：`backtest/execution/shell/panels.py`、`tests/test_minute_panels.py`
   - 修改：`backtest/execution/config.py`、`backtest/execution/shell/loaders.py`、`backtest/execution/shell/runner.py`、`backtest/execution/shell/report.py`、`scripts/verify_capacity_impact.py`
   - 追加：`tests/test_execution_capacity.py`（T381-19/21 回归型用例）
2. **红→绿批次（M6 修正后分配，红读数必须先登记，清单升级规则 5）**：

   | 批次 | 用例 | 红形态 | 绿判据 |
   |------|------|--------|--------|
   | R1 | T381-01/02/05（E0） | `ImportError: MIN_STOCK_CODE` / `AttributeError: load_month_regression` | 3 绿 |
   | R2 | T381-03/04/06/07（E0/E2） | `ImportError: MinuteDayAggregate` | 4 绿 |
   | R3 | T381-08/09/10/11（E2） | `ImportError: MinutePanelBuilder` | 4 绿 |
   | R4 | T381-12/13/14/15/16（E1/E2） | `ImportError: build_daily_panels` | 5 绿 |
   | R5 | T381-17/18（E4/E5） | 报告缺段 / 覆盖度失败 | 2 绿 |
   | R6 | T381-19/20/21 + 全量（E3/E6） | 默认输出漂移 | 4 绿 + 2048 passed |

3. **版本同步**：3.9.1 六处按 EXECUTION §3.1 清单机械替换（5 处代码锚点 + CHANGELOG 标题注明「对应路线图批次 v3.8.1」）；
4. **skipif 纪律**：T381-17/18/20 需 `E:\Level 1 Data`；T381-20 **另需** `E:\Ashare_data`（条件叠加，缺任一即 skip，附理由）；T381-03/04/05/10 需 `skipif(not has_pyarrow(), reason="calib extra 未安装")`；
5. **派生命令（修正后口径）**：
   - `pytest tests/test_minute_panels.py -k "loader"`（E0 出口，5 例）
   - `pytest tests/test_minute_panels.py -k "daily"` / `-k "minute"`（E1/E2 出口）
   - `pytest tests/test_execution_capacity.py`（E3 + T381-19/21 回归）
   - `python scripts/verify_capacity_impact.py --calibrate --no-minute`（E4 出口，exit 0）
   - 全量 `pytest`（R6 收口：2048 passed / 15 skipped / 0 failed）
   - G8 版本号核查：`grep -rn "3\.9\.0" --include=*.py --include=*.toml <白名单范围>` 零命中 + CHANGELOG 人工核对

---

## §8 汇总

| 项 | 读数 |
|----|------|
| 对账维度 | 8 / 8 全过（M2/M3/M4/M6/M9 修正后） |
| 发现总数 | **11**（CRITICAL **0** / MAJOR **0** / MINOR **11**） |
| 修正情况 | 11/11 当场修正；CHECKLIST 10 处编辑（→v1.1）、EXECUTION 13 处编辑（→v1.2）；设计/调研零改动 |
| 残余风险 | 0（无未决项；M7 以实施注记 R12 披露为终态） |
| 证据等级 | 全部 E4（文档间逐字比对，grep 取回原文与行号后修正）；无 E5 |
| **结论** | **PASS** —— 进入步骤 9（TDD 实施） |

---

## §9 工件链终态

| 顺序 | 工件 | 版本 | 状态 |
|------|------|------|------|
| 1 | [RESEARCH_V3.8.1](../research/RESEARCH_V3.8.1_MINUTE_PANEL_WIRING.md) | v1.2 | 步骤 2 复审闭环（§9） |
| 2 | [DESIGN_V3.8.1](../private/DESIGN_V3.8.1_MINUTE_PANEL_WIRING.md) | v1.1 | 步骤 4 复审闭环（§13）+ R2 勘误（步骤 6 回改） |
| 3 | [EXECUTION_V3.8.1](../EXECUTION_V3.8.1_MINUTE_PANEL_WIRING.md) | **v1.2** | 步骤 6 复审闭环（§10）+ 步骤 8 修正（M2/M3/M6/M7/M8/M11） |
| 4 | [CHECKLIST_V3.8.1](CHECKLIST_V3.8.1_MINUTE_PANEL_WIRING.md) | **v1.1** | 步骤 7 产出（84 项）+ 步骤 8 修正（10 处）；**待步骤 9 回填** |
| 5 | 本文件 | v1.0 | 步骤 8 终态（PASS） |
| 6 | [PROJECT_STATUS](../PROJECT_STATUS.md) | — | 步骤 8 完成块已同步（2026-11-20） |

**下一步**：步骤 9 TDD 实施（按 §7 约束执行；完成后步骤 10 审计复核）。
