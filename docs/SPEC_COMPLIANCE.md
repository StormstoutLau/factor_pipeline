# SPEC 合规声明（Adoption & Deviations）

---
id: spec-compliance
type: process-spec
version: 1.2
status: verified
date: 2026-11-24
depends: [v392-calibration-unit-fix-RESEARCH, v392-calibration-unit-fix-DESIGN, v392-calibration-unit-fix-IMPLEMENTATION, v392-calibration-unit-fix-CHECKLIST]
upstream: SPEC_PROCESS.md
---

> **权威来源**: `F:\Spec_Workflow`（2026-11-20 本地快照），本仓副本 [spec/SPEC_PROCESS.md](../spec/SPEC_PROCESS.md) 仅作自包含引用，冲突时以 F 仓为准。
> **生效范围**: 自 **v3.9.3** 起的新批次强制执行；v3.9.2 已按四件套回填；v3.9.1 及更早批次**豁免**（档案保留原路径，不回改）。

## §1 载体就位情况

| 规范要求 | 载体 | 状态 |
|---------|------|------|
| 流程本体（自包含） | [spec/SPEC_PROCESS.md](../spec/SPEC_PROCESS.md) | ✅ 已随仓 |
| 四件套模板 | [spec/templates/](../spec/templates/)（RESEARCH / DESIGN / IMPLEMENTATION / CHECKLIST，另含 ADR 与决策矩阵模板） | ✅ 已随仓 |
| 批次目录 | [spec/v392-calibration-unit-fix/](../spec/v392-calibration-unit-fix/)（RESEARCH / DESIGN / IMPLEMENTATION / CHECKLIST / CONSISTENCY_REVIEW / AUDIT） | ✅ 已迁移 |
| 待办真值源 | [docs/PROGRESS.md](PROGRESS.md)（P-001 ~ P-025，状态词 `pending/in-progress/blocked/done`） | ✅ 已建立 |
| 开发日志 | [docs/dev-log/](dev-log/) | ✅ 已建立（首条 DEV-LOG-2026-11-20） |
| 合规登记 | 本文件 | ✅ |

## §2 四文档契约（DC1/DC2）

v3.9.2 六份文档均已补 front-matter（H1 后 10 行内）：

| 文档 | id | version | status |
|------|----|---------|--------|
| RESEARCH.md | `v392-calibration-unit-fix-RESEARCH` | 1.1 | verified |
| DESIGN.md | `v392-calibration-unit-fix-DESIGN` | 1.1 | verified |
| IMPLEMENTATION.md | `v392-calibration-unit-fix-IMPLEMENTATION` | 1.1 | verified |
| CHECKLIST.md | `v392-calibration-unit-fix-CHECKLIST` | 1.0 | accepted |
| CONSISTENCY_REVIEW.md | `v392-calibration-unit-fix-CONSISTENCY-REVIEW` | 1.0 | verified |
| AUDIT.md | `v392-calibration-unit-fix-AUDIT` | 1.0 | verified |

## §3 偏差登记（DC4 命名空间：`D-0xx`）

| ID | 偏差 | 依据/事实 | 处置 | 到期 |
|----|------|----------|------|------|
| D-001 | **RULE-5 异构复审未满足**：v3.9.2 步骤 2/4/6/10 由实施同一会话完成 | 本机无第二基座模型可用 | v3.9.3 起步骤 10 交独立子代理（同基座时在 AUDIT 首行显式标注「同基座降级」） | v3.9.3 |
| D-002 | **审计者自行修复**：v3.9.2 审计中当场修复 A-1/A-3，违反 ADD「审计者永不自动修复」 | `spec/v392-calibration-unit-fix/AUDIT.md` §4 | v3.9.3 起 AUDIT 只列问题 + 复现命令；修复另立 `REWORK.md` 或新 P 行，审计不写代码 | v3.9.3 |
| D-003 | **ADR 单体承载**：ADR 条目集中在根 `DECISIONS.md`，未拆为 `adr/ADR-xxxx-*.md` | 历史 55+ 条，拆分成本高 | 保留单体，ADR 命名空间登记见 §4；拆分不单独立项 | 长期 |
| D-004 | **Layer-1 工具未激活**：无 step-gate / doc-contract validator / rework-graph / 证据 SVG | SPEC_PROCESS §「迁移最小集」允许按需激活 | 以人工清单（CHECKLIST + AUDIT 探针）替代；需要时另批接入 | 按需 |
| D-005 | **历史文档命名遗留**：v3.9.1 及更早用 `EXECUTION_*.md`，分散在 `docs/research`、`docs/private`、`docs/audit` | 迁移最小集允许历史豁免 | 不回改；新批次一律 `spec/<feature>/IMPLEMENTATION.md` | 长期 |

> **v3.9.2 审计结论的效力**：D-001/D-002 意味着该次审计是「同会话复审」，只能作为**自审 + 证据复核**，不等同于 RULE-5 的独立审计；结论已在 AUDIT.md 如实披露，不追认其独立性。

## §4 命名空间登记（DC4）

| 命名空间 | 载体 | 当前范围 | 说明 |
|---------|------|---------|------|
| `ADR-0xx` | `DECISIONS.md` | ADR-001 ~ ADR-058 | 单体承载（D-003） |
| `P-0xx` | `docs/PROGRESS.md` | P-001 ~ P-025 | 待办真值源，编号单调不复用 |
| `D-0xx` | 本文件 §3 | D-001 ~ D-005 | 合规偏差 |
| `v392-calibration-unit-fix-*` | `spec/v392-calibration-unit-fix/` | 6 文档 | 批次文档命名空间 |
| `RULE-1~6` | `spec/SPEC_PROCESS.md` | 全局 | 由权威规范定义，本仓不重定义 |
| `E1~E5` | 各 AUDIT/CHECKLIST | 实例级 | 证据等级，不作全局编号 |

## §5 旧路径映射（v3.9.2）

| 旧路径 | 新路径 |
|--------|--------|
| `docs/research/RESEARCH_V3.9.2_CALIBRATION_DIAGNOSIS.md` | `spec/v392-calibration-unit-fix/RESEARCH.md` |
| `docs/private/DESIGN_CALIBRATION_UNIT_CONSISTENCY_V3.9.2.md` | `spec/v392-calibration-unit-fix/DESIGN.md` |
| `docs/EXECUTION_V3.9.2_CALIBRATION_UNIT_FIX.md` | `spec/v392-calibration-unit-fix/IMPLEMENTATION.md` |
| `docs/audit/CHECKLIST_V3.9.2_CALIBRATION_UNIT_FIX.md` | `spec/v392-calibration-unit-fix/CHECKLIST.md` |
| `docs/audit/CONSISTENCY_REVIEW_V3.9.2_CALIBRATION_UNIT_FIX.md` | `spec/v392-calibration-unit-fix/CONSISTENCY_REVIEW.md` |
| `docs/audit/2026-11-20-v3.9.2-calibration-unit-fix-audit.md` | `spec/v392-calibration-unit-fix/AUDIT.md` |

## §6 生效规则

1. 新批次**先登记 P 行**，再建 `spec/<feature>/`，四件套缺一不得进入步骤 3。
2. 步骤 10 审计**不由实施会话执行**；无法异构时必须在 AUDIT 首行标注「同基座降级」。
3. 审计只取证、不修复；修复走 REWORK 或新 P 行。
4. 每批收尾更新 `PROGRESS.md` 与 `docs/dev-log/`，并在 CHANGELOG 指向 `spec/<feature>/`。
5. 每批收尾必须通过 **E-TODO 出口门禁**（§7），未通过不得将 CHECKLIST 置为 `accepted`。

## §7 出口门禁 E-TODO（每批必过）

| 步 | 动作 | 通过判据 |
|----|------|---------|
| E1 | 扫描本批 `RESEARCH.md` 的 `U*/B*`、`AUDIT.md` 的 `A*/FO*/观察`、`DESIGN.md` 的「不做/遗留」 | 生成候选清单（编号去重） |
| E2 | 每项映射到 ① P 行 ② 已闭环证据 ③ 不修复裁决（ADR / 批次决策） | 映射率 100%，无「仅文字登记」项 |
| E3 | CHECKLIST 逐行状态非「待」；汇总数由逐行统计（RULE-2） | 逐行计数与 §7 汇总一致，失败项有处置 |
| E4 | `done` 项带证据链接；`blocked` 项写触发条件 | 抽查 10% 通过 |
| E5 | 结果同时写入 CHECKLIST §7 与 `PROGRESS.md` | 两处一致，无单边更新 |

> 违规样例（2026-11-20 已纠正）：B9 粒度偏差只在 DESIGN 写「登记遗留」而无 P 号；v3.9.2 CHECKLIST 37 行停在「待」而 §7 汇总写「40 通过」。
