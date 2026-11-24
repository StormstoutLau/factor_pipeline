# 批次 Session：τ 融合口径冻结（P-027 Stage 0）

---
id: p027-tau-fusion-freeze-SESSION
type: session
version: 1.1
status: verified
date: 2026-11-24
depends: []
upstream: null
---

> **批次**：P-027 Stage 0——τ 融合口径冻结（文档层）
> **档位**：**T3**（Layer-0 文档 / 账本）
> **判档依据**（SPEC_PROCESS v1.7.0 §判档规则 1）：改动路径 = `docs/PROGRESS.md` / `docs/PROJECT_STATUS.md` / `docs/analysis/ENDOGENEITY_PREMIUM_GOVERNANCE_ANALYSIS.md` / `spec/p027-tau-fusion-freeze/SESSION.md`，与 `{scripts/, tests/, tools/, .pre-commit-config.yaml, .github/workflows/}` 交集为 **∅** → Layer-0 → T3。
> **裁剪理由**：本批只冻结 τ 的定位、权重版本与报告字段规格；**零代码 / 零门禁**，不改变任何默认输出。Stage 0 的报告字段接入属 Layer-1（运行时输出契约变更），另立 T1 子批，不在本批夹带。
> **Spec 步骤**：T3 五步决策流（判档 → 事实核对 → 裁决 → 实施 → 验收）。
> **回退点**：本批未产生 git 提交；回退 = `git checkout -- docs/PROGRESS.md docs/PROJECT_STATUS.md docs/analysis/ENDOGENEITY_PREMIUM_GOVERNANCE_ANALYSIS.md` + 删除本目录。

---

## 0. 决策流（五步）

| 步 | 动作 | 结论 | 证据出口 |
|---|---|---|---|
| 1 | 判档与登记 | T3；P-027 由 `pending` 转 `in-progress`（Stage 0a 完成，0b 待 T1） | `docs/PROGRESS.md` P-027 行 |
| 2 | 事实核对 | F-1~F-8：权重硬编码、有效权重漂移、全部 opt-in、S4 回退、报告无权重字段 | §1 |
| 3 | 裁决 | D1-D6：τ=heuristic summary v1、权重 v1 冻结、字段规格、E5 experimental、禁新增消费者、代码延后 | §2 |
| 4 | 实施 | 文档冻结 + P 台账同步；零代码 | §3 |
| 5 | 验收 | 静态核对 + E-TODO 出口（可执行校验器未运行，见 §4） | §4-§6 |

---

## 1. 事实核对（E1，全部为仓内事实）

> **F1/F2 口径**：本批不使用外部来源；内部文件以「路径 + 行号区间」替代来源版本。
> **F3 降级链**：无外部检索；可执行校验器降级说明见 §4。
> **F4 引用验证表**：N/A（外部引用 0 条）。
> **F5 先失败记录**：N/A（零代码）。

| # | 事实 | 读数 | 来源 |
|---|---|---|---|
| F-1 | τ 权重硬编码、不可配置 | `weights={oster_delta:0.4, aet:0.3, ife:0.2, lewbel:0.1}`；orchestrator 无参构造 `EndogeneityThreatAssessor()`；`PipelineV2Config` 无权重字段 | `modules/endogeneity_check/core/threat_assessor.py` L31-L36；`diagnostic_orchestrator.py` L63；`pipelines_v2.py` L544-L583 |
| F-2 | 有效权重随方法开关漂移 | 默认 `oster+aet` → 0.571 / 0.429；`+IFE` → 0.444 / 0.333 / 0.222；全开 → 0.400 / 0.300 / 0.200 / 0.100 | `threat_assessor.py` L67-L79；`pipelines_v2.py` L547-L549 / L1855-L1865 |
| F-3 | τ 全部为 opt-in，远程消费者有限 | E3 `enable_endogeneity_check=False`；E5 `enable_endogeneity_regularization=False`；E6 `enable_endogeneity_estimators=False`；消费者 = E5、优化器（`lambda_endogeneity=0`）、`FactorSignificanceTest(threat_taus=)` | `pipelines_v2.py` L546 / L574 / L583；`pipelines_v2.py` L2069-L2129；`optimizer.py` L113 / L391-L419；`backtest/factor_significance.py` L536 |
| F-4 | S4 可静默回退到插补后 | `s4_data = decoupled_factor if decoupled_factor is not None else imputed_factor`；final τ 取 S4 | `pipelines_v2.py` L1912；`diagnostic_orchestrator.py` L180 |
| F-5 | 报告无权重/阶段字段 | `.py` 中 `weights_version` / `effective_weights` / `s4_input_stage` / `stage_fallback` 命中 **0**；`check_endogeneity` 仅产出 `s1`-`s4` + `final_assessment` | grep 读数；`pipelines_v2.py` L1877-L1925 |
| F-6 | τ 未进入 Layer 3 / 生产治理记录 | `diagnose()` 无 τ 入参；`_combine_label` 仅 `return_type × premium_health`；`GovernanceRecord.build()` 仅测试调用 | `modules/factor_health/__init__.py` L799-L803 / L1236-L1252；`backtest/governance.py` L395-L398 / L425 |
| F-7 | 融合无统计基座（前序结论） | 权重未标定、补偿型聚合、无 CI；0.3 / 0.7 未与权重联合标定 | 本仓分析 §11（L381-L449）、§12（L453-L555） |
| F-8 | P-009 未启动且已有准入条件 | P-009 `pending / P3`，准入前置 P-027 Stage 2 | `docs/PROGRESS.md` L28 |

---

## 2. 裁决与规格（Step 3-4）

| # | 裁决 | 内容 |
|---|---|---|
| D1 | τ 定位冻结 | τ = **`heuristic summary v1`**，不是统计估计；不得作为新增决策层基座；报告/文档不得表述为「内生性已修正」 |
| D2 | 权重冻结 | `0.4 / 0.3 / 0.2 / 0.1`（oster / aet / ife / lewbel）登记为 **先验权重 v1**；不新增配置项；有效权重按启用方法归一化；**τ 不可跨配置比较** |
| D3 | 报告字段规格（T1 实施） | `weights_version='v1'`；`effective_weights`（仅启用方法，归一化后）；S4 补 `s4_input_stage ∈ {decoupled, imputed_fallback}` + `stage_fallback: bool`；E5 输出补 `experimental=True`。落点：S2/S3/S4 + `final_assessment`。**数值输出不变**，但新增键属输出契约变更 → Layer-1 → T1 |
| D4 | E5 标注 | E5 三层正则化统一标注 **experimental / heuristic**；不作为「内生性已处理」的证据；默认关闭不变 |
| D5 | 禁止新增消费者 | P-009 / Layer 3 交互在 P-027 Stage 2 通过前不启动；优化器、显著性检验不得新增 τ 依赖 |
| D6 | 代码延后 | Stage 0 代码字段（D3）不在 T3 内实施；另立 **T1 子批**（仍属 P-027，另登记实施记录） |

### 2.1 不变式

- **INV-1**：本批零代码——不修改任何 `.py` / `.toml` / `.yaml` / `.json` / 测试。
- **INV-2**：权重冻结为 v1（0.4 / 0.3 / 0.2 / 0.1），不新增配置字段。
- **INV-3**：默认行为零变更（E3 / E5 / E6 仍全部关闭）。
- **INV-4**：P-027 状态为 `in-progress`；Stage 0a（文档）完成，Stage 0b（代码）待 T1。
- **INV-5**：P-009 准入条件保持指向 P-027 Stage 2，不得提前启动。
- **INV-6**：D3 字段仅登记规格，不在本批代码中出现。

---

## 3. 实施记录（Step 5-6，零代码）

| 文件 | 位置 | 改动 |
|---|---|---|
| `spec/p027-tau-fusion-freeze/SESSION.md` | 本文件 | 新建 T3 session（判档 / 事实 / 裁决 / 实施 / 验收） |
| `docs/analysis/ENDOGENEITY_PREMIUM_GOVERNANCE_ANALYSIS.md` | §11 标题后 | 增冻结声明：加权融合定位为 `heuristic summary v1`，裁决见 §13 |
| 同上 | §13 标题后 | 增执行状态：Stage 0 文档冻结完成；代码字段待 T1；P-027 `in-progress` |
| `docs/PROGRESS.md` | P-027 行 | 状态 `pending` → **`in-progress`**；依据列补本 session 与 T3 裁剪理由；验收①拆为 0a（文档，完成）/ 0b（代码，待 T1） |
| `docs/PROJECT_STATUS.md` | §2 优先级视图 | P1 = P-027（in-progress：Stage 0 文档冻结完成，Stage 1 探针待启动） |

> **零代码自证**：本批全部写入均通过 Write / Edit 限定在 `docs/` 与 `spec/`；未触碰任何代码 / 配置 / 测试文件。

---

## 4. 机械核验（Step 8）

| 检查 | 方法 | 读数 |
|---|---|---|
| 代码字段未出现 | Grep `weights_version\|effective_weights\|s4_input_stage\|stage_fallback` over `*.py` | **0 命中**（仅文档命中） |
| P-027 状态 | Read `docs/PROGRESS.md` P-027 行 | `in-progress`，链接本 session |
| P-009 准入 | Read `docs/PROGRESS.md` P-009 行 | 仍指向 P-027 Stage 2 |
| P 号范围 | Grep `P-001 ~ P-027` | SPEC_COMPLIANCE / PROJECT_STATUS 一致 |
| 零代码 | 写入范围自证（Write/Edit 仅 docs/spec） | **0 个代码文件** |
| 三校验器 / `console_gen --check` | — | **未执行**：权威校验器在 `F:\Spec_Workflow`（仓外）；当前工作区标记 untrusted，禁止执行仓内脚本/命令。降级为静态 grep/Read + 写入范围自证；待工作区信任后补跑 |

---

## 5. E-TODO 出口（SPEC_COMPLIANCE §7，T3 简化执行）

| 步 | 结果 |
|---|---|
| E1 候选清单 | B-1 权重无版本 / B-2 有效权重漂移 / B-3 S4 回退无标记 / B-4 E5 无 experimental 标注 / B-5 P-009 无前置 |
| E2 映射 | B-1/B-2→D2；B-3→D3；B-4→D4；B-5→D5；映射率 **100%** |
| E3 逐行状态 | P-027 → `in-progress`（0a done / 0b 待 T1）；P-009 保持 `pending` |
| E4 证据链接 | 本文件 §1/§3/§4 + 分析 §11/§12/§13 + PROGRESS P-027 |
| E5 双写 | PROGRESS P-027 行与本文件 §3 一致；PROJECT_STATUS §2 视图同步 |

---

## 6. Step 10 审计（T3 裁剪）

本批为 **T3 文档 / 账本级**，无代码、无门禁、无运行时变更；按 T3 裁剪不启独立 ADD 审计。以 §4 静态核验 + 写入范围自证替代。结论：**PASS（条件：可执行校验器未运行，待工作区信任后补跑）**。

---

## 7. 结论与后续

- **Stage 0a 文档冻结完成**：τ 定位、权重 v1、报告字段规格、E5 experimental、P-009 门禁全部落文档。
- **Stage 0b（代码字段）已落盘（2026-11-24）**：`weights_version` / `effective_weights` / `s4_input_stage` / `stage_fallback` / E5 `experimental` 已实现，测试已补；**验证未执行**（工作区 untrusted，pytest/回归待可信环境）。详见 [T1 四文档](../p027-stage0b-disclosure-fields/RESEARCH.md)。
- **Stage 1 执行（2026-11-24）**：固定 `winsor_rank_z`，12 因子；G1 16.7% / G2 翻转 18.8% / G3 p=0.317，三项全失败 → Stage 2 判定 τ 仅展示、E5 experimental、P-009 关闭为「不实现」。见 [TAU_FUSION_STAGE1_P027.md](../../docs/analysis/TAU_FUSION_STAGE1_P027.md)；工件 `out/p027_stage1_probe.{py,json}`。
- **下一步**：Stage 0b 的测试/回归待可信环境执行；Stage 1 已完成，Stage 2 判定 τ 仅展示。
- P-027 保持 `in-progress`（Stage 0b 已落盘，测试/回归待可信环境）；Stage 2 已判定 τ 仅展示，P-009 已关闭为「不实现」。
