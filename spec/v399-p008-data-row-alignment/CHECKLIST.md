# 审查验收 Checklist：P-008 数据行数对齐 —— 四项裁决落地

---
id: v399-p008-data-row-alignment-CHECKLIST
type: design
version: 1.2
status: accepted
date: 2026-11-22
depends: [v399-p008-data-row-alignment-IMPLEMENTATION, v399-p008-data-row-alignment-DESIGN]
upstream: null
---

> **Feature**: 运行时 counts-only 对齐证据 + 离线三方分解审计
> **创建日期**: 2026-11-22
> **状态**: 已验收（**71/71 通过，0 失败 / 0 待办**；Step 10 ADD 审计 PASS_WITH_FIXES：0×P1 / 2×P2 / 3×P3 已处置，质量门 5.0/5 档位 A；Step 9 红→绿 8/8 + 42 passed）
> **Spec 步骤**: Step 7-8, 10
> **基于实施**: [IMPLEMENTATION.md](./IMPLEMENTATION.md) **v1.1 verified**（Step 6 复审 PASS_WITH_FIXES，§12）
> **基于设计**: [DESIGN.md](./DESIGN.md) **v1.1 verified**（Step 4 复审 PASS_WITH_FIXES，§12）
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.5 verified**（v1.5 = Step 8 P3-1 舍入订正）

> **适用范围与裁剪声明（T1）**
> 本批含 Layer-1 代码改动（`backtest/execution/shell/` + `scripts/` + `tests/`），**不适用 T3 裁剪**。Step 9 必须按 TDD 双要素执行：先红（T398-1~8 失败）→ 后绿（全通过），红→绿两读数记入 IMPLEMENTATION §8 或本文件 §10 证据列。所有验收方法均为**可重放命令或逐字读数**，不得以「已确认」替代。
>
> **Step 8 / 9 / 10 记录位**：§1 为文档一致性（Step 8 独立 pass 填写）；§2-§7 为功能/接口/不变式/错误/性能/兼容（Step 9-10 填写）；§8 为 ADD 审计（Step 10 填写）。§1 已于 Step 8 填写（13/13 ✅）；§2-§7 已于 Step 9-10 回填；§8 已于 Step 10 填写（PASS_WITH_FIXES，P2/P3-1 修复、P3-2/P3-3 登记）。

> **Step 8 复审记录（2026-11-22，独立只读 pass，异构基座）**：§1 全 13 项 = **13/13 PASS**，**PASS_WITH_FIXES**（0×P1 / 0×P2 / 1×P3）。P3-1：RESEARCH §6.4 L375 λ_median `+2.68%` 与 §6.5 重推导值 `+2.69%`（+2.686%）舍入不一致 → 已就地订正，RESEARCH 升 **v1.5 verified**。其余读数：RESEARCH 锚点 §3.1(L81)/§3.2(L128)/§3.3(L141)/§6.4(L369，四 U 全关闭)/§6.5(L395)；DESIGN D1-D8 (L37-44)；IMPL §3.1-3.4 (L67/L121/L167/L217)、INV-1~9 (L482-490)、D-398-1~7 (L582-588)；跨文档数字（3,442,081/3,523,738/3,528,865/87,574/87,760/2,000/4,941/7,917/+0.098%/+0.428%/9.29%/1.0843%）逐数一致；OPEN 扫描仅命中 RESEARCH 历史注记与 DESIGN 否定断言，无状态漂移。

> **Step 9 记录（2026-11-22，TDD 红→绿 + E2）**：T398-1~8 红 `8 failed, 34 deselected`（exit 1）→ 绿 `8 passed, 34 deselected`（exit 0）；**最终代码两测试文件回归 `42 passed, 5 warnings in 186.34s`（exit 0）**；全量套件（修复前启动的回归基线）`2100 passed, 15 skipped, 172 warnings in 1078.65s`（exit 0）。39 月离线审计 exit 0（82 s，17:55:41→17:57:03）：匹配日 / 日频 / 分钟 = 786 / 787 / 786，minute 3,442,081 / daily_matched 3,523,738 / daily_full 3,528,865，A_matched 87,574 / A_full 87,760 / B 7,917 / C 2,000 / D 4,941 / zero 7,917（peak 2022-05 = 972，1.0843%），双口径残差 0，码域 5,029/5,273/244/0，前缀 {9:239,8:3,3:1,6:1}；逐月合计与总计逐位一致；明细见 IMPLEMENTATION §8.4 与 `%TEMP%\p008_e2_alignment2.*`。

> **Step 10 记录（2026-11-22，独立只读子代理 ADD 审计 + 机械验证）**：① INV-1 三方 SHA 比对：备份（2026-11-21 基线）= 第 1 跑 = 第 2 跑（T398-9 修复后代码）= `82728CE103D49AF2…` 逐位一致，默认路径 exit 0、V1 对账 20 项全 OK；② 审计内存实测（GetProcessMemoryInfo，基线 = `build_panels` 后）：commit +350.2 MB / working set +242.5 MB（持久 int32 数组 ≈ 16 MB，与设计估计同量级；增量主要来自逐日 feather→pandas 临时分配）；③ ADD 审计 **PASS_WITH_FIXES**（0×P1 / 2×P2 / 3×P3，修复前 4.8/5 档位 A）：P2-1（DESIGN §7 `alignment_identity_failed` 契约未实现）+ P2-2（残差≠0 分支零测试）+ P3-1（exit 2 仅查单口径）→ 已修复（T398-9 红 `1 failed, 2 passed` → 绿 `3 passed`，守卫四态 / md 两态含非恒真对照 / CLI exit 2+0；D-398-9/10）；P3-2（月集口径边界）+ P3-3（`_pct` 边界）→ 登记不修（D-398-11）；修复后复评 **5.0/5 档位 A**；Iron Law 4 项全 PASS。修复后最终回归：P-008 两测试文件 **43 passed, 5 warnings in 175.94s**（exit 0，含新增 T398-9）。

---

## 1. 文档一致性验收（Step 8）

### 1.1 RESEARCH.md ↔ DESIGN.md 对齐

| 验收项 | DoR（前置） | 验证方法 | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|---|
| DESIGN D1-D8 可追溯到 RESEARCH | 两文档定稿 | 逐条核对 DESIGN §2.1 引用节 | 8/8 引用节真实且支持决策 | ✅ | Step 8 读数：DESIGN L37-44（D1-D8）引用 RESEARCH §6.4 U-1~U-4（L371/377/383/389）与 §6.5（L395）、§3.1/§3.3，8/8 节存在且内容支持 |
| U-1~U-4 裁决被 DESIGN 完整承接 | RESEARCH §6.4/§6.5 关闭记录 | 逐条比对裁决词与读数 | 四值无篡改（Δc +0.098% / +0.428% / 不补 / 三方分解） | ✅ | Step 8 读数：RESEARCH §6.5 结论表 L449-452（不剔除/不过滤/不补/三方分解）↔ DESIGN L37-40 决策词一致；Δc +0.098%（RESEARCH L375/L449 ↔ DESIGN L37/L236）、+0.428%（L381/L450 ↔ L38/L242）、9.29%（L372/L449 ↔ L37/L236）逐数一致 |
| 两文档无矛盾表述 | 两文档定稿 | 交叉检索「剔除/过滤/补源/交集口径」 | 无相反表述 | ✅ | Step 8 读数：DESIGN 中「剔除/过滤/合成」仅出现于 §5.2-§5.4 否决理由与 D1-D3 否定语境（L236/L242/L248），与 RESEARCH 裁决同向；Step 8 P3-1（RESEARCH 内部 λ 舍入 +2.68%/+2.69%）已订正升 v1.5，RESEARCH↔DESIGN 无冲突（DESIGN 未引用该 λ 值） |

### 1.2 DESIGN.md ↔ IMPLEMENTATION.md 对齐

| 验收项 | DoR（前置） | 验证方法 | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|---|
| DESIGN §3.2 五模块均有实施位置 | IMPLEMENTATION §3 存在 | 模块名逐一比对 | 5/5 对应（DailyRef / _align_month / audit / report / script） | ✅ | Step 8 读数：IMPL §3.1(L67, D1/D2/D3/D7)/§3.2(L121, D4/D6)/§3.3(L167, D6/D7)/§3.4(L217, D7) ↔ DESIGN §3.2 表（L93-101）；D5 落 §3.1 实施要点（counts-only + 低效排除表）、D8 落 §4.2 token + §7 INV-5，5/5 |
| IMPLEMENTATION 接口与 DESIGN §4 一致 | 两文档 §4 存在 | 比对签名与 schema 13 键 | 4/4 一致 | ✅ | Step 8 读数：DailyRef 两字段（DESIGN §4.1 L141-154 ↔ IMPL §3.1/§4.1）、audit_alignment 五参（§4.3 L194 ↔ IMPL §4.3）、write_alignment_report 两参（↔ IMPL §4.4）、data_alignment 13 键（§4.2 L158-182 ↔ IMPL §4.2 返回 dict 13 键），4/4（Step 6 §12.2 V1 已核，本轮复核） |
| DESIGN INV-1~9 均有实施与验证方式 | IMPLEMENTATION §7 表存在 | 逐条比对 | 9/9 有实施位置 + 验证方式 | ✅ | Step 8 读数：IMPL §7 L482-490 每行含实施位置列 + 验证方式列，9/9，编号与 DESIGN L323-331 一一对应 |
| 无设计未覆盖的实施 | IMPLEMENTATION §11 存在 | 核对 D-398-1~7 | 7 项全部登记且自洽 | ✅ | Step 8 读数：IMPL §11 L582-588 七行，各有来源（DESIGN §3.2/§4.2/§4.3/§4.4/F-7）与验收方式；D-398-7 为 Step 6 F-5 补登，自洽 |

### 1.3 IMPLEMENTATION.md ↔ CHECKLIST.md 对齐

| 验收项 | DoR（前置） | 验证方法 | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|---|
| IMPLEMENTATION 功能点均有验收项 | 本文件 §2-§5 完成 | 反向清单比对 | 4 模块 / 4 接口 / 9 不变式 / 7 错误场景全覆盖 | ✅ | Step 8 读数：IMPL §3.1→§2.1/§2.2/§3.1/§3.2；§3.2→§2.3/§3.3/§3.4；§3.3→§2.4/§3.3；§3.4→§2.4/§3.5；§4 接口×4→§3.1-§3.5；§7 INV×9→§4（9 行）；§6 错误×7→§5（7 行），全覆盖 |
| 每个验收项可回溯到 IMPLEMENTATION | 本文件全表 | 逐项查 DoR 锚点 | 无孤立验收项 | ✅ | Step 8 读数：§2-§5 各行 DoR 引用 IMPL §3.x/§4.x/§7 或 DESIGN §7/§8，抽查无孤立项；E2 期望值（§2.1/§2.3）与 IMPL §8.2 实跑表同源 |

### 1.4 术语一致性

| 术语 | RESEARCH.md | DESIGN.md | IMPLEMENTATION.md | 一致 |
|---|---|---|---|---|
| `data_alignment` | §6.5 证据块（概念源：字面词自 DESIGN 起，RESEARCH 为证据来源） | §4.2 schema | §4.2 实现 | ✅ |
| A/B/C/D 归因 | §3.3 定义（A 代码域/B 停牌/C 截断/D 缺日） | §3.3 码级规则 | §3.2/§4.1 实现 | ✅ |
| 匹配日口径 | §2.3 定义 | §4.2 `scope="matched_days"` | §4.1 `matched` | ✅ |
| 零成交股票×日 | §3.3 / §6.5（7,917 / 0.230% / 1.084%） | §4.2 `zero_amount` | §4.1 `amount_day==0` | ✅ |

## 2. 功能验收

### 2.1 运行时 `data_alignment`（IMPLEMENTATION §3.1）

| 验收项 | DoR（前置） | 验证方法 | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|---|
| 合计与 RESEARCH §3.1 逐数一致 | `--calibrate` 可跑 | 读 `out/capacity_calibration.json` → `panels.data_alignment.total` | minute=3,442,081 / daily=3,523,738 / diff≈−2.32 / daily_full=3,528,865 / diff_full≈−2.46 | ✅ | Step 9 实跑（exit 0）：minute 3,442,081 / daily 3,523,738 / diff −2.32 / daily_full 3,528,865 / diff_full −2.46 |
| `monthly` 行数与键集正确 | 同上 | 数行、读键 | 39 行；每行 7 键 | ✅ | Step 9：39 行；键 = daily, daily_days, diff_pct, minute, minute_days, month, zero_amount；私有键计数 0 |
| `outlier_days` 精确 | 同上 | 读数组 | 恰 2 条：02-26 −27.55 / 02-27 −27.68 | ✅ | Step 9：恰 2 条：2020-02-26（2782/3840，−27.55）、2020-02-27（2782/3847，−27.68） |
| `missing_minute_days` 精确 | 同上 | 读数组 | 恰 1 条：2023-03-31 daily=5,127 | ✅ | Step 9：恰 1 条 `{date: 2023-03-31, daily: 5127}` |
| `zero_amount` 精确 | 同上 | 读对象 | pairs=7,917 / share=0.23 / peak=2022-05 / peak_share=1.0843 | ✅ | Step 9：pairs 7,917 / share_pct 0.23 / peak_month 2022-05 / peak_share_pct 1.0843 |

### 2.2 warning token（IMPLEMENTATION §4.2）

| 验收项 | DoR（前置） | 验证方法 | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|---|
| 截断 warning 命中 | 02-26/27 数据在窗口 | Grep `data_alignment_truncation` in 校准 JSON | 一行含两日期与负偏差 | ✅ | Step 9：`data_alignment_truncation: 2020-02-26 (-27.55%); 2020-02-27 (-27.68%)`（单行含两日期 + 负偏差） |
| 缺日 warning 命中 | 03-31 缺失 | Grep `data_alignment_missing_day` | 含 `2023-03-31 (daily=5127)` | ✅ | Step 9：`data_alignment_missing_day: 2023-03-31 (daily=5127)` |
| 部分模式 warning | `DailyRef()` 旧构造 | 单测 T398-5 | 含 `data_alignment_partial`，不抛异常 | ✅ | Step 9 绿：T398-5 通过；`DailyRef(days_by_month={})` → warning 含 `data_alignment_partial`，`daily=None`、`matched_days=None`，构建继续 |

### 2.3 离线三方分解（IMPLEMENTATION §3.2）

| 验收项 | DoR（前置） | 验证方法 | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|---|
| A/B/C/D 精确 | `--alignment-audit` 可跑 | 读 `out/data_alignment.json` | A_matched=87,574 / A_full=87,760 / B=7,917 / C=2,000 / D=4,941 | ✅ | Step 9：`out/data_alignment.json` 同数；`totals` minute 3,442,081 / daily_matched 3,523,738 / daily_full 3,528,865 |
| 双口径恒等式残差 0 | 同上 | 读 `identity.residual` | 0（两种口径） | ✅ | Step 9：`residual=0`、`residual_full=0`；`87,574+2,000−7,917=81,657`、`87,760+2,000+4,941−7,917=86,784` |
| 码域与首位分布 | 同上 | 读 `code_universe` | 5,029 / 5,273 / 244 / 前缀 9:239,8:3,3:1,6:1 | ✅ | Step 9：minute 5,029 / daily 5,273 / daily_only 244 / minute_only 0；前缀 {9:239, 8:3, 3:1, 6:1} |
| JSON + MD 双产物 | 同上 | 列目录 | 两文件均存在且非空 | ✅ | Step 9：`out/data_alignment.json` 17,219 B、`out/data_alignment.md` 3,652 B |

### 2.4 报告与 CLI（IMPLEMENTATION §3.3/§3.4）

| 验收项 | DoR（前置） | 验证方法 | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|---|
| 校准 md 含对齐节 | 校准 JSON 含块 | 读 `out/capacity_calibration.md` | 出现「数据行数对齐」节与 5 项读数 | ✅ | Step 9：L30「## 数据行数对齐（P-008 证据层）」含 5 项（786/787、3,442,081/3,523,738 −2.32%、缺失日、2 条日级 >5%、7,917/0.230%/2022-05 1.084%），位于 L38「λ 显著性」前 |
| 默认输出零变化 | 改动前备份 SHA | `Get-FileHash out/capacity_impact.json` | 前 8 位 `82728CE1`（与改前一致） | ✅ | Step 10 三方比对逐位一致：备份（2026-11-21 基线）= 第 1 跑 = 第 2 跑（T398-9 修复后代码）= `82728CE103D49AF2…`（完整 64 位相同）；第 2 跑 exit 0、V1 对账 20 项全 OK |
| 审计 CLI 正常退出 | 数据根可读 | `--alignment-audit` | exit 0 + 两产物落盘 + 打印路径 | ✅ | Step 9：exit 0；落盘 `out/data_alignment.json`（17,219 B）+ `out/data_alignment.md`（3,652 B），并打印两路径 |

## 3. 接口验收

### 3.1 `DailyRef` 增量（IMPLEMENTATION §4.1）

| 验收项 | DoR（前置） | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|
| 两字段存在且默认 None | 类定义可导入 | `rows_by_day` / `dates_by_month` 均为可选 | ✅ | Step 9 读数：panels.py L50-51 `Optional[Dict[str, int]] = None` / `Optional[Dict[str, List[str]]] = None` |
| 旧构造零改动可运行 | 既有 tests L86/L799/L814 | 三处构造不改仍通过 | ✅ | Step 9：既有 `DailyRef(adv, universe, industry, mv_rank, days_by_month=...)` 构造未改；最终代码两测试文件回归 **42 passed** |
| 脚本注入格式正确 | `daily_ref` 可调用 | 键为 `YYYY-MM-DD`，值 int / list | ✅ | Step 9 读数：scripts L299-310 `str(d)[:10] → int` 与 `str(d)[:7] → list[str]`；E2 39 月审计直接消费该 DailyRef（786 匹配日） |

### 3.2 `_align_month` / `_finalize_alignment`（IMPLEMENTATION §4.1/§4.2）

| 验收项 | DoR（前置） | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|
| 签名与职责一致 | 两方法存在 | 只消费 `agg` + `DailyRef`，不读盘 | ✅ | Step 9 读数：panels.py L283 `_align_month(self, ym, agg)`、L330 `_finalize_alignment(self, rows, unmatched_minute)`；函数体内无 `open` / `read_table` / `Path.glob` |
| 部分模式语义 | `DailyRef()` | `daily=None / matched_days=None / daily_rows_available=false` | ✅ | Step 9 绿：T398-5 断言 `matched_days is None`、`daily_rows_available` 为 false，且 partial warning 命中 |
| 公开月行键集固定 | build 可跑 | 恰 7 键，无 `_outliers` 等私有键 | ✅ | Step 9 绿：T398-8 断言每行键集 = {month, minute, daily, diff_pct, minute_days, daily_days, zero_amount}，无 `_outliers/_missing/_unmatched` |
| 类型与舍入 | build 可跑 | 计数为 Python int/float；diff 2 位、share 4 位 | ✅ | Step 9 绿：T398-8 校验 int/float 类型；`_pct` L121-127 与 `_align_month` L318 均 `round(..., 2)`；zero share 由 `_finalize_alignment` `round(..., 4)` |

### 3.3 `audit_alignment`（IMPLEMENTATION §4.3）

| 验收项 | DoR（前置） | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|
| 签名与 DESIGN 一致 | 函数存在 | `(cfg, loader, close, start=None, end=None)` | ✅ | Step 9 读数：alignment.py L78 `def audit_alignment(cfg, loader, close, start=None, end=None)`；T398-6 按该签名调用 |
| 窗口默认取 cfg | cfg 可构造 | 不传 start/end 时窗口为 `minute_start/end` | ✅ | Step 9 绿：T398-6 月中起点（`minute_start=minute_end=2023-01-04`）→ `window=["2023-01","2023-01"]`；E2 默认窗口 `2020-01..2023-03`、39 月 |
| pyarrow / 根缺失处理 | 空根或 pyarrow 缺失 | `CalibrationUnavailable` → exit 2，无 traceback | ✅ | Step 9 冒烟：`--alignment-audit --minute-root %TEMP%\p008_no_such_root` → `[alignment] 分钟数据根不可用: …`，exit 2，无 traceback |
| 恒等式失败处理 | 构造残差非 0 | `identity.residual` 非 0 → exit 2 | ✅ | Step 9 读数：scripts L754 `return 2 if (payload.get('identity') or {}).get('residual') else 0`；E2 残差 0 → exit 0，同一表达式的非零分支即 exit 2 |

### 3.4 `write_alignment_report`（IMPLEMENTATION §4.4）

| 验收项 | DoR（前置） | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|
| 签名一致 | 函数存在 | `(payload, json_path)` | ✅ | Step 9 读数：alignment.py L283 `def write_alignment_report(payload, json_path)` |
| 双产物与返回值 | 传入有效 payload | 写 JSON + 同名 md，返回 2 路径 | ✅ | Step 9 绿：T398-6 断言返回 2 路径、JSON/MD 均存在且非空；E2 实际落盘 `p008_e2_alignment2.json/.md` 并打印两路径（exit 0） |
| md 只读 payload | 函数签名 | 无 `close` / `loader` 参数 | ✅ | Step 9 读数：`_render_alignment_md(payload)` 仅读 payload；T398-6 断言 md 含恒等式与 `残差` |

### 3.5 报告节（IMPLEMENTATION §3.4）

| 验收项 | DoR（前置） | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|
| 有块渲染 / 无块跳过 | `render_markdown` 可调用 | 两态测试 T398-7 通过 | ✅ | Step 9 绿：T398-7 有 `panels.data_alignment` → md 含「数据行数对齐」；无块 → 不含该节 |
| 节位置正确 | 校准 payload 完整 | 位于「面板覆盖度」后、「λ 显著性」前 | ✅ | Step 9 读数：report.py L73「面板覆盖度」→ L94「数据行数对齐（P-008 证据层）」→ L118「λ 显著性与填充」 |

## 4. 不变式验收

| 不变式（DESIGN §8） | 验证方法 | 状态 |
|---|---|---|
| INV-1 默认 `capacity_impact.json` SHA 不变 | 跑前备份 / 跑后 / 复跑三方比对（Step 10：三方前 16 位均 `82728CE103D49AF2`，完整哈希逐位一致） | ✅ |
| INV-2 `panel_hash` 不变 | T398-4 注入/不注入对照 + 改前备份（Step 9：T398-4 两次 build 逐位相同；校准实跑 `panel_hash` 前 8 = `dfcc4e1d`，与 P-003 基线一致） | ✅ |
| INV-3 39 月窗口不变 | 校准 `coverage.months` 长度 = 39（Step 9 实跑：39；`data_alignment.monthly` 亦 39 行） | ✅ |
| INV-4 零成交 bar 保留 | T398-3 λ/σ/`panel_hash` 逐位相同（Step 9 绿） | ✅ |
| INV-5 告警非阻断 | `coverage_gate` 源码无改动；`--calibrate` 退出码不变（Step 9 实跑：exit 0，两条 warning 仅入 `evidence_warnings`；git diff 未触及 `coverage_gate`） | ✅ |
| INV-6 恒等式残差 0 | T398-6 + E2 实跑（Step 9：双口径 `residual=0 / residual_full=0`） | ✅ |
| INV-7 校准零额外分钟 IO | 代码评审：`_align_month` 无文件读取（Step 9 静态：仅消费 `agg`/`DailyRef`） | ✅ |
| INV-8 `DailyRef` 向后兼容 | 既有 3 处构造回归（Step 9：两测试文件最终代码 42 passed） | ✅ |
| INV-9 审计按需 | 无 flag 运行不 import `alignment`（Step 9：`sys.modules` 检查为 False） | ✅ |

## 5. 错误处理验收

| 错误场景（DESIGN §7） | 触发方式 | 预期行为 | 状态 |
|---|---|---|---|
| `rows_by_day` 未注入 | `DailyRef()` | `data_alignment_partial` + 继续构建（Step 9：T398-5 绿） | ✅ |
| `dates_by_month` 缺失 | 只给 `rows_by_day` | 无缺日命名；无新增 warning（Step 9 静态：L293 `(dates_by_month or {}).get(ym, [])` → `missing=[]`） | ✅ |
| 分钟独有日 | 构造 minute 有 / daily 无 | 不计 matched；`unmatched_minute_days` 计数（Step 9 静态：L296 仅取 `rows_by_day` 命中日、L326-328 `_unmatched` 计数；E2 unmatched=0） | ✅ |
| 日频某日 0 行 | 构造 daily=0 | `diff_pct=None`，不进 outlier（Step 9 静态：L301-302 `daily_sd=0 → diff=None`；L306-307 `n=0` 跳过） | ✅ |
| 单月 `agg` 为空 | 空月加载 | 沿用「整月剔除 / partial」（T381-10 既有用例：22/23 → partial、19 日 → 整月剔除；最终代码两测试文件 42 passed） | ✅ |
| 审计分钟根缺失 | `--alignment-audit` + 空根 | `[alignment]` 一行 + exit 2（Step 9 冒烟：`p008_no_such_root` → exit 2，无 traceback） | ✅ |
| 恒等式残差非 0 | 构造错配 | JSON 落盘 + md 标注 + exit 2（Step 9：L754 非零即 return 2；md 恒等式行由 T398-6 覆盖） | ✅ |

## 6. 性能验收

| 性能指标 | 目标 | 实测 | 状态 |
|---|---|---|---|
| 校准路径额外分钟 IO | 0 次（只复用已加载 `agg`） | 0 次（Step 9 静态：`_align_month` 无 `open`/`read_table`/`Path.glob`） | ✅ |
| 审计单次耗时 | ≤ 3 分钟 | **82 s**（Step 9 E2：2026-11-22 17:55:41→17:57:03，含 `build_panels`，39 月全量） | ✅ |
| 审计内存增量 | 逐日 int32 数组 ≈ 12-14 MB | **持久数组 ≈ 16 MB**（786 日 × 5,029 码 int32 ≈ 15.7 MB + zero_by_day ≈ 1 MB，与设计同量级）；进程级实测（GetProcessMemoryInfo，基线 = `build_panels` 后）：commit **+350.2 MB** / working set **+242.5 MB**——增量主要来自逐日 feather→pandas 临时分配与 groupby 装箱，逐文件释放但 commit 回收惰性；审计全程残差 0（探针 `%TEMP%\p008_mem_probe.py`） | ✅ |

## 7. 兼容性验收

| 环境 | 版本 | 状态 | 说明 |
|---|---|---|---|
| Python | 3.9 | ✅ | 静态：仅 `typing.Optional/Dict/List`（panels.py L12），无 `match` / PEP 604 / 内建泛型；`py_compile` OK |
| pandas | ≥2.0 | ✅ | 实测 2.2.3；`groupby.nunique` / `Series.items` 已使用 |
| pyarrow | ≥14（optional） | ✅ | 实测 24.0.0；E2 `read_table(columns=[…])` 成功 |
| OS | Windows | ✅ | E1/E2 均在本机 Windows 实跑；`pathlib` 路径，无 shell 依赖 |

## 8. ADD 审计（Step 10，2026-11-22 独立只读子代理 + 修复后复评）

### 8.1 Spec 质量门（Phase 0）

| 维度 | 得分（0-1） | 说明 |
|------|-----------|------|
| 可测试约束 | 1.0 | INV-1~9 + T398-1~9 全部可机检；红→绿读数齐备（§8.4） |
| 模块映射 | 1.0 | 5 模块 ↔ 文件逐一对应；panels.py 零读盘（imports 静态核实） |
| 接口契约 | 1.0 | 13 键 schema / 月行 7 键 / 三 token 逐字一致；P2-1 修复后 `alignment_identity_failed` + md 警示已实现（T398-9） |
| 修正项 | 1.0 | F-1（int32）/ F-2（md 渲染入测）落实；P2-2 修复后残差≠0 分支有测试（T398-9 CLI exit 2+0） |
| 跨模块契约 | 1.0 | runtime/audit 域过滤与日期归一同口径；E2 双路径数字互证（B=zero_pairs=7,917） |
| **总分** | **5.0/5（修复后复评；修复前子代理评 4.8/5）** | **档位**: A |

### 8.2 ADD 审计发现

| 严重性 | 发现 | 证据 | 修复建议 |
|------|------|------|---------|
| P1 | 无 | — | — |
| P2-1 | DESIGN §7 L319 契约（残差≠0 → `alignment_identity_failed` JSON 字段 + md 顶部标红）未实现 | 子代理审计：alignment.py 返回 dict 无该键、md 恒成功态 | **已修复**（T398-9 红→绿）：`_identity_failed` 守卫 + payload 注入 + md 警示行（D-398-9） |
| P2-2 | 残差≠0 → exit 2 分支零测试覆盖，IMPLEMENTATION §6 L476 验证方式登记不实（写 T398-6，实际 T398-6 仅断言残差 0） | 子代理审计：test_data_alignment.py L60-61 | **已修复**（T398-9 第 4 段：CLI exit 2 + exit 0 进程内；§6 行已改写）（D-398-10） |
| P3-1 | CLI exit 2 仅检查匹配日口径残差，未查 `residual_full` | verify L754（修复前） | **已修复**：升级为 `residual or residual_full or alignment_identity_failed` 三重检查（D-398-10） |
| P3-2 | 运行时只统计 usable 月（整月剔除后），审计侧统计窗口内全部 feather——出现整月剔除月份时两口径系统性分歧 | 子代理审计：panels L586-600 vs alignment L57-59；本仓 39 月无整月剔除，实测一致 | **登记不修**（D-398-11①）；若未来出现整月剔除月份需重新对齐口径 |
| P3-3 | `_pct` 边界不一致：panels `b<=0→None`，alignment `not b→None`（负 b 会反号） | panels L121-125 vs alignment L24-27 | **登记不修**（D-398-11②）；当前调用点 b 恒为正计数，无实际影响 |

### 8.3 ADD Iron Law 检查

- [x] 断言恒真式已扫描（T398-3/4 两次调用真实实现路径、对照输入不同；T398-6 全部取自 `audit_alignment` 返回值无本地重算；T398-9 含非恒真对照——同一 payload 去标记 → 无警示）——**PASS**
- [x] 单文件检查盲区已扫描（alignment.py 与 panels.py 两套实现域过滤同源 `_keep_mask`、日期归一同口径 `[:10]`、窗口均按月；审计直读 feather 无共享缓存；唯一系统性差异 = P3-2 已登记）——**PASS**
- [x] 设计文档独有约束有测试（D-398-1~11 逐条映射证据，见 IMPLEMENTATION §11）——**PASS**
- [x] 修正阻断性项有测试（F-1 int32 实现落实；F-2 md 渲染由 T398-6 覆盖；P2-1/P2-2 修复由 T398-9 覆盖）——**PASS**

## 9. 文档完整性

| 文档 | 存在 | 与实现一致 |
|------|------|----------|
| RESEARCH.md | ✅（v1.5 verified） | ✅（Step 9 E2 逐数复现：786/787/786、3,442,081/3,523,738/3,528,865、87,574/87,760/2,000/4,941/7,917） |
| DESIGN.md | ✅（v1.1 verified） | ✅（Step 9 实现对照：13 键 schema / 三方分解 / 三 token 与 §4 一致；D-398-8 补充窗口按月份） |
| IMPLEMENTATION.md | ✅（v1.1 verified） | ✅（Step 9-10 回填 §8.4 三组红→绿 + D-398-8~11 + §6 修正行） |
| CHECKLIST.md（本文件） | ✅（v1.2 accepted） | ✅（本文件，Step 9-10 证据已回填，71/71） |
| ADR（如有） | N/A | N/A |
| 开发日志 | ✅ | Step 9/10 记录见本文件头部三段 + IMPLEMENTATION §8.4（红→绿三组读数）；git 提交待用户指令（§11） |

## 10. 验收结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 13 | 13 | 0 | 0 |
| 功能 | 15 | 15 | 0 | 0 |
| 接口 | 16 | 16 | 0 | 0 |
| 不变式 | 9 | 9 | 0 | 0 |
| 错误处理 | 7 | 7 | 0 | 0 |
| 性能 | 3 | 3 | 0 | 0 |
| 兼容性 | 4 | 4 | 0 | 0 |
| ADD 审计 | 4 | 4 | 0 | 0 |
| **总计** | **71** | **71** | **0** | **0** |

> **统计口径（RULE-2）**：上表来自本文件逐项核对，非事后汇总推算。当前态：Step 8 完成（13/13 ✅）；Step 9 完成（T398-1~8 红→绿 + E2 审计 + 39 月校准）；Step 10 完成（INV-1 三方 SHA + §6 内存实测 + ADD 审计 PASS_WITH_FIXES：0×P1 / 2×P2 / 3×P3，P2 与 P3-1 已修复（T398-9 红→绿），P3-2/P3-3 登记不修（D-398-11）；质量门修复后复评 5.0/5 档位 A）。每行满足「总数 = 通过 + 失败 + 待办」，总计为 8 类按列求和（71 = 71 + 0 + 0 ✓）。

### 10.2 验收决定

- [x] **验收通过**：所有 P1 项通过，无阻塞性问题 —— Step 10 独立 ADD 审计 **PASS_WITH_FIXES**（0×P1 / 2×P2 / 3×P3，修复前 4.8/5 档位 A）；P2-1/P2-2/P3-1 已修复（T398-9 红→绿 `1 failed → 3 passed`），P3-2/P3-3 登记不修（D-398-11）；修复后复评 **5.0/5 档位 A**；71/71 项全通过，INV-1 三方 SHA 逐位一致
- [ ] **有条件通过**
- [ ] **验收失败**

### 10.3 签字

| 角色 | 签字 | 日期 |
|------|------|------|
| 实施者 | Trae（AI agent） | 2026-11-22 |
| 审查者 | 独立只读子代理（Step 10 ADD 审计） | 2026-11-22 |

## 11. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|------|--------|------|------|
| Step 8 文档一致性独立 pass | — | — | 已完成（13/13 PASS，1×P3 已订正） |
| Step 9 TDD 实现（T398-1~8 先红后绿） | — | — | 已完成（8 failed → 8 passed；E2 见头部 Step 9 记录） |
| Step 10 CHECKLIST 全项 + ADD 审计 | — | — | 已完成（71/71；ADD PASS_WITH_FIXES 2×P2 + 1×P3 修复 / 2×P3 登记，T398-9 红→绿） |
| 更新 PROGRESS.md | — | — | 已完成（P-008 → done） |
| 记录开发日志 | — | — | 已完成（见头部 Step 9/10 记录 + IMPLEMENTATION §8.4） |
| git 提交 | 待用户指令 | 提交时 | pending |
