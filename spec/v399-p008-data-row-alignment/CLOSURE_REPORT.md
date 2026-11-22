# P-008 批次全流程闭环总结报告

- **Feature**: 数据行数对齐（分钟 / 日频覆盖核对）——运行时 counts-only 对齐证据层 + 离线三方分解审计
- **批次**: v3.9.8（spec 目录 `spec/v399-p008-data-row-alignment/`；包版本未 bump，随 v3.9.8 发版，见 §8 勘误 E-1）
- **档位**: T1（Layer-1 代码改动：`backtest/execution/shell/` + `scripts/` + `tests/`）
- **周期**: 2026-11-22（Step 1 ~ Step 10 单日完成）
- **状态**: **已闭环**——CHECKLIST v1.2 accepted（71/71），git `587b7f8` + `9be0bf8` 已推送 origin/master
- **依据**: SPEC_PROCESS v1.7.2 十步流程；RULE-1 时序独立 / RULE-2 统计溯源 / RULE-5 异构基座 / F5 红→绿

---

## 1. 裁决基础（Step 1-2 调研 → U-1~U-4 关闭）

RESEARCH **v1.5 verified**（v1.5 = Step 8 P3-1 λ 舍入订正）。39 月（2020-01 ~ 2023-03）探针实测：

| 指标 | 读数 |
|---|---|
| 交易日 | 匹配日 / 日频 / 分钟 = **786 / 787 / 786**（03-31 分钟整日缺失） |
| 股票×日 | 分钟 **3,442,081** vs 日频（匹配日）**3,523,738** = **−2.32%**；全窗口 3,528,865 = −2.46% |
| 月度差异 | 全部 < 5%（无触发月份） |
| 日级异常 | 仅 2020-02-26（−27.55%）/ 02-27（−27.68%）截断 + 2023-03-31 整日缺失（−100%） |
| 零成交股票×日 | **7,917 / 0.230%**，峰值 2022-05 = 972（1.0843%） |
| 外部锚点 | 10 条（T1×8 / T3×2，F4 表 + Crossref/arXiv 复解析） |

四项裁决（RESEARCH §6.5，独立 Δc 复算 + 三方分解支撑）：

| 裁决 | 结论 | 依据 |
|---|---|---|
| U-1 截断日 | **不剔除** 02-26/27 | Δc +0.098%，月成交额 −9.29% |
| U-2 零成交 bar | **不过滤** | Δc +0.428%，codes 5,029 不变 |
| U-3 缺日 | **不补** 2023-03-31 | 单日缺失，口径影响可披露 |
| U-4 归因口径 | **三方分解主口径 + 交集残差作 B 指标** | A（码域）/ B（停牌/独有日）/ C（截断）/ D（缺日）码级规则 |

Step 2 独立复核 + 异构复审 PASS（§5.7/§5.8：探针复跑、156 格全表复算、零成交 bar 全量验证 7,917/7,917、F-1/F-2 两项 P2 已订正）。

## 2. 十步流程时间线

| Step | 产出 | 版本 / 结论 |
|---|---|---|
| 1-2 | RESEARCH.md（调研 + 独立复核 + 异构复审） | v1.5 verified |
| 3-4 | DESIGN.md（D1-D8 采纳四裁决、INV-1~9、13 键 schema、6 项否决方案） | v1.1 verified（Step 4 复审 PASS_WITH_FIXES：1×P2 F-7 + 4×P3 已处置） |
| 5-6 | IMPLEMENTATION.md（四模块 + T398-1~8 计划 + D-398-1~7） | v1.1 verified（Step 6 复审 PASS_WITH_FIXES：2×P2 F-1/F-2 + 3×P3 已处置） |
| 7 | CHECKLIST.md（8 类 71 项，DoR/DoD + 证据位） | v1.0 → v1.2 accepted |
| 8 | 文档一致性独立复审 | **13/13 PASS**（1×P3 λ 舍入订正 → RESEARCH v1.5） |
| 9 | TDD 实现 + E2 实跑 | 红 `8 failed` → 绿 `8 passed`；详见 §4-§5 |
| 10 | CHECKLIST 全项 + ADD 独立审计 | **71/71**；ADD PASS_WITH_FIXES 已处置；质量门 5.0/5 档位 A |

## 3. 实现面（Step 9-10 代码落盘）

| 文件 | 变更 | 要点 |
|---|---|---|
| [panels.py](../../backtest/execution/shell/panels.py) | 改 | `DailyRef` 增 `rows_by_day` / `dates_by_month`；新增 `_pct` / `_alignment_warnings` / `_align_month` / `_finalize_alignment`；`build()` 接线产出 `panels["data_alignment"]`（13 键 schema），零额外分钟 IO |
| [alignment.py](../../backtest/execution/shell/alignment.py) | 新 | 离线审计 `audit_alignment`（三方分解 + `_identity_failed` 独立守卫）+ `write_alignment_report`（JSON/MD 双产物）；逐日 int32 数组；窗口按月份判定（D-398-8） |
| [report.py](../../backtest/execution/shell/report.py) | 改 | 「数据行数对齐（P-008 证据层）」节，位于覆盖度后、λ 显著性前；无块整段跳过 |
| [verify_capacity_impact.py](../../scripts/verify_capacity_impact.py) | 改 | `daily_ref` 注入逐日行数；`attach_panel_meta` 透传；`--alignment-audit` 分支（默认路径零变更，不 import alignment）；exit 2 三重检查（残差 / residual_full / failed 标记） |
| [test_minute_panels.py](../../tests/test_minute_panels.py) | 改 | T398-1~5、T398-8 |
| [test_data_alignment.py](../../tests/test_data_alignment.py) | 新 | T398-6、T398-7、T398-9 |

**TDD 红→绿（三组，F5）**：

| 组 | 红 | 绿 |
|---|---|---|
| T398-1~8（Step 9） | `8 failed, 34 deselected`（exit 1） | `8 passed, 34 deselected`（exit 0） |
| T398-9（Step 10 ADD 修复） | `1 failed, 2 passed`（exit 1，AttributeError） | `3 passed`（exit 0） |
| 最终回归 | — | 两测试文件 **43 passed, 5 warnings in 175.94s**（exit 0） |

衍生需求 D-398-1~11 全部登记于 IMPLEMENTATION §11（D-398-8 = 审计窗口按月份，Step 9 E2 发现按日期过滤漏 2020-01；D-398-9/10 = ADD P2 修复；D-398-11 = P3 两项登记不修）。

## 4. 核心验证证据链

### 4.1 三方分解（39 月离线审计，exit 0，82 s）

```
totals: minute 3,442,081 | daily_matched 3,523,738 | daily_full 3,528,865
        both 3,434,164 | B 7,917 | A_matched 87,574 | A_full 87,760 | C 2,000 | D 4,941
恒等式（匹配日）: 87,574 + 2,000 − 7,917 = 81,657
恒等式（全窗口）: 87,760 + 2,000 + 4,941 − 7,917 = 86,784
残差: 0 / 0（双口径）    scope: 786 / 787 / 786    window: 2020-01..2023-03（39 月）
码域: 分钟 5,029 / 日频 5,273 / 日频独有 244 / 分钟独有 0；前缀 {9:239, 8:3, 3:1, 6:1}
逐月: 39 行合计与总计逐位一致；outlier 恰 2 条（02-26 −27.55 / 02-27 −27.68）
```

产物：`out/data_alignment.json`（17,219 B）+ `out/data_alignment.md`（3,652 B）。

### 4.2 运行时校准（`--calibrate --panel-cache`，exit 0）

- `panels.data_alignment`：total 3,442,081 / 3,523,738（−2.32%）/ 3,528,865（−2.46%）；monthly 39 行 × 7 键、私有键 0；zero_amount = 7,917 / 0.23% / 2022-05 / 1.0843%
- 两条 warning 入 `evidence_warnings`（truncation + missing_day），非阻断（INV-5）
- `coverage.months` = 39（INV-3）；`panel_hash` 前 8 = `dfcc4e1d`，与 P-003 基线一致（INV-2）

### 4.3 不变式 INV-1~9 全达成

| 不变式 | 证据 |
|---|---|
| INV-1 默认 SHA 不变 | 三方比对（备份 / 第 1 跑 / 第 2 跑修复后代码）完整 64 位逐位一致 `82728CE1…` |
| INV-2 panel_hash 不变 | T398-4 注入/不注入对照逐位相同 + 校准实跑 dfcc4e1d |
| INV-3 39 月窗口 | coverage.months = 39，data_alignment.monthly = 39 行 |
| INV-4 零成交 bar 保留 | T398-3 λ/σ/panel_hash 逐位相同 |
| INV-5 告警非阻断 | coverage_gate 零改动；--calibrate exit 0 |
| INV-6 恒等式残差 0 | T398-6 + E2 双口径 0 |
| INV-7 零额外分钟 IO | `_align_month` 静态核实无读盘 |
| INV-8 DailyRef 兼容 | 既有 3 处构造零改动，回归 43 passed |
| INV-9 审计按需 | 默认路径 `sys.modules` 无 alignment |

### 4.4 性能与兼容

- 审计耗时 82 s（目标 ≤ 3 分钟）；校准路径额外分钟 IO = 0
- 审计内存：持久 int32 数组 ≈ 16 MB（786 日 × 5,029 码，与设计估计同量级）；进程级 commit +350.2 MB / ws +242.5 MB（逐日 feather→pandas 临时分配，逐文件释放）
- 兼容性：Python 3.13 实测（语法面 3.9 兼容）、pandas 2.2.3、pyarrow 24.0.0、Windows 本机
- 全量套件：**2100 passed / 15 skipped / 0 failed**（1078.65 s）

## 5. ADD 独立审计（Step 10）

独立只读子代理结论：**PASS_WITH_FIXES（0×P1 / 2×P2 / 3×P3，修复前 4.8/5 档位 A）**；Iron Law 4 项全 PASS（恒真式 / 盲区 / 设计独有约束 / 修正项）。

| 编号 | 发现 | 处置 |
|---|---|---|
| P2-1 | DESIGN §7 `alignment_identity_failed` 契约未实现 | **已修复**：`_identity_failed` 独立守卫 + payload 注入 + md 顶部警示行（T398-9，D-398-9） |
| P2-2 | 残差≠0 分支零测试 + §6 验证方式登记不实 | **已修复**：T398-9（守卫四态 / md 两态含非恒真对照 / CLI exit 2+0），§6 改写（D-398-10） |
| P3-1 | CLI exit 2 仅查匹配日口径 | **已修复**：三重检查 `residual or residual_full or alignment_identity_failed` |
| P3-2 | 运行时只统计 usable 月，审计统计全部 feather——出现整月剔除月份时两口径分歧 | **登记不修**（D-398-11①；本仓 39 月无整月剔除，实测一致） |
| P3-3 | `_pct` 边界不一致（panels b≤0 / alignment not b） | **登记不修**（D-398-11②；调用点 b 恒为正计数） |

修复后复评：**5.0/5 档位 A**。

## 6. 交付清单与 git

- spec 文档 4 份：RESEARCH v1.5 / DESIGN v1.1 / IMPLEMENTATION v1.1 / CHECKLIST v1.2（均 accepted/verified）
- 代码 4 文件（3 改 1 新）+ 测试 2 文件（1 改 1 新）+ 探针 `probe_alignment.py`
- 证据产物：`out/data_alignment.json/.md`、`out/capacity_calibration.json/.md`（含对齐节）
- git：**`587b7f8`**（提交信息标 `feat(v3.9.9)`，包版本实际 3.9.8，见 §8 勘误 E-1；12 文件，+2853 行）+ **`9be0bf8`** docs（哈希补记），已推送 origin/master

## 7. 遗留与后续

| 项 | 状态 |
|---|---|
| P3-2 / P3-3 口径边界 | 登记 D-398-11，暂不修（触发条件：出现整月剔除月份 / `_pct` 负分母调用点） |
| git 提交 | 已完成（`587b7f8` / `9be0bf8`） |
| 待办 | **无**——P-008 无剩余待验收项 |

> 结论：P-008 十步全流程闭环。运行时对齐为 counts-only 证据层（λ/σ/impact/coverage/panel_hash/默认 SHA 逐位不变），离线审计提供 A/B/C/D 归因与双口径恒等式防线；四项裁决（不剔除 / 不过滤 / 不补 / 三方分解）在实现与证据层面完整落地。

## 8. 勘误与台账对账（P-019，2026-11-23）

> **触发**：P-010（v3.9.8）完成后对账发现本报告与 CHECKLIST 以 `v3.9.9` 作批次标签，而包版本四处锚点（`pyproject.toml` L7 / `__init__.py` L58 / `config_v2.py` L371 / `reporting.py` L40）自 v3.9.7 起一直为 **3.9.8**——P-008 从未 bump 版本。**裁决**：不改写已推送的 git 历史，以本文档勘误对账（依据 [P-019 SESSION](../p019-version-ledger-reconcile/SESSION.md)，T3 Layer-0 纯文档）。

| 编号 | 位置 | 原文 | 订正 |
|---|---|---|---|
| E-1 | 本报告 L4 | 批次 v3.9.9 | 批次 **v3.9.8**（包版本未 bump，随 3.9.8 发版） |
| E-1 | 本报告 §6 git 行 | `587b7f8` feat(v3.9.9) | `587b7f8`（提交信息标 v3.9.9 为笔误，包版本实际 3.9.8） |
| E-1 | CHECKLIST §11 git 行 | `587b7f8` feat(v3.9.9) | 同上 |

- **发版口径**：**v3.9.8 = 覆盖 P-011（`decc96c`）/ P-008（`587b7f8`）/ P-010（`3dabaff`）三批的同一发版号**；`CHANGELOG.md` v3.9.8 条目已补 P-008 / P-011 两小节。
- **不改写历史**：`587b7f8` 提交信息保留原文；以本条勘误为唯一权威解释。
