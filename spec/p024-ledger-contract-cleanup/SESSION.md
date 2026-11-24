# 批次 Session：台账 / 契约小收口（P-024）

---
id: p024-ledger-contract-cleanup-SESSION
type: session
version: 1.0
status: verified
date: 2026-11-24
depends: []
upstream: null
---

> **批次**：P-024 台账 / 契约小收口
> **档位**：**T3**（Layer-0 纯文档 / 账本）
> **判档依据**（SPEC_PROCESS v1.7.0 §判档规则 1）：改动路径 = `docs/PROGRESS.md` / `docs/PROJECT_STATUS.md` / `docs/SPEC_COMPLIANCE.md` / `docs/ARCHITECTURE.md` / `spec/p023-tradability-memory-phase2/CHECKLIST.md` / `spec/p024-ledger-contract-cleanup/SESSION.md`，与 `{scripts/, tests/, tools/, .pre-commit-config.yaml, .github/workflows/}` 交集为 **∅**；零 `.py` / `.toml` / `.yaml` 改动 → Layer-0 → T3。
> **裁剪理由**：无运行时 / 公开接口 / 门禁变更；`PROGRESS` 仅追加 P-024/P-025 与视图同步，不改状态词表或派生规则（DC2.1）；`stock_return` 契约修复**不在本批**，转 P-025。
> **Spec 步骤**：T3 五步决策流（判档 → 事实核对 → 裁决 → 实施 → 验收）。
> **回退点**：本批未产生 git 提交；回退 = `git checkout -- docs/PROGRESS.md docs/PROJECT_STATUS.md docs/SPEC_COMPLIANCE.md docs/ARCHITECTURE.md spec/p023-tradability-memory-phase2/CHECKLIST.md` + 删除本目录。

---

## 0. 决策流（五步）

| 步 | 动作 | 结论 | 证据出口 |
|---|---|---|---|
| 1 | 判档与登记 | T3；PROGRESS 登记 P-024（本批）与 P-025（stock_return 契约待办） | `docs/PROGRESS.md` P-024/P-025 行 |
| 2 | 事实核对 | F-1 ~ F-6 六项存量偏差 | §1 |
| 3 | 裁决 | D1-D4：修账本、修 CHECKLIST 读数、ARCHITECTURE 指向既有裁决、契约修复转 P-025 | §2 |
| 4 | 实施 | 五个文档定点编辑；零代码 | §3 |
| 5 | 验收 | 机械核验 + 交叉复核（证据 JSON / git 事实） | §4-§5 |

---

## 1. 事实核对（Step 1-2，全部为仓内 E1）

> **F1/F2 口径**：本批不使用外部来源，全部判据来自仓内文件；内部文件以 `vX.Y` + 行号区间替代来源版本。
> **F3 降级链**：无降级（未使用检索通道）。
> **F4 引用验证表**：N/A——外部引用 0 条。
> **F5 先失败记录**：N/A——无代码 / fixture 改动。

| # | 事实 | 读数 | 来源（编辑前版本 + 行号） |
|---|---|---|---|
| F-1 | `SPEC_COMPLIANCE` 的 P 号范围 | §1 写 **P-001 ~ P-011**；§4 写 **P-001 ~ P-009**；PROGRESS 实际最大 **P-023** | `docs/SPEC_COMPLIANCE.md` v1.1 L23 / L57；`docs/PROGRESS.md` L36 |
| F-2 | P-023 提交状态 | CHECKLIST §11 写「用户明确『先不提交』，保持工作区」；实际已提交 `17b981e` 并推送（`3dd8232..17b981e`，`master...origin/master` 同步） | `spec/p023-tradability-memory-phase2/CHECKLIST.md` v1.2 L214；`git log/push` 2026-11-24 |
| F-3 | P-023 最终读数 | §2/§8/§11 三处仍写 **16.86 s / 619.4 MB**；§6/§9/§12.1 与证据 JSON 为 **16.80 s / 618.6 MB** | CHECKLIST L102 / L158 / L216 vs L129 / L166 / L167 / L235；`out/tradability_memory_p023.json`：`m1.total_s=16.801226`、`m3.peak_rss_mb=618.6` |
| F-4 | MissingTypeDiagnoser 处置 | `ARCHITECTURE` 仍写「P3 待办 (expanding EM)」；P-011 已裁决**不修复 + 触发条件**（生产固定 `strategy='ffill_ts'`，不调用 `HierarchicalImputer`） | `docs/ARCHITECTURE.md` L422；`spec/v398-p011-dev-backlog-triage/RESEARCH.md` §3.3 L130-L138 |
| F-5 | `stock_return` 契约口径 | `stock_return.pkl` 为**百分数**（1475×5688，p99=10.01，max=200,400），而 `data_contract.py` 的 `return` 一致性检查按 decimal `[-1,10]`；当前主链路未消费；PROGRESS 无对应 P 行 | `spec/p021-tradability-production-enablement/RESEARCH.md` L108 / L128；`docs/research/RESEARCH_TRADABILITY_DECISION_ANCHORS.md` L129；`backtest/data_contract.py` L657-L671 |
| F-6 | PROGRESS 优先级视图 | P3 仅列 P-009 / P-018；P-024/P-025 未登记 | `docs/PROGRESS.md` L45（编辑前） |

---

## 2. 偏差与裁决（Step 3-4）

| # | 偏差 | 裁决 | 理由 |
|---|---|---|---|
| D1 | SPEC_COMPLIANCE P 号范围过期 | 更新为 **P-001 ~ P-025**（§1 + §4），文档升 **v1.2** | P 号单调；新增 P-024/P-025 后，合规登记必须覆盖最大号 |
| D2 | P-023 CHECKLIST 提交状态与最终读数不一致 | 升 **v1.3**；L214 改为「已提交并推送 `17b981e`」；L102/L158/L216 统一为 **16.80 s / 618.6 MB** | 以证据 JSON 与 §6/§12.1 为准；提交事实以 git 为准 |
| D3 | ARCHITECTURE 把已裁决项写成「P3 待办」 | 改为「已知局限；P-011 裁决不修复 + 触发条件」并链接 P-011 §3.3 | 不重复立项；保留重开条件，避免把「不修复」误读为「未处理」 |
| D4 | `stock_return` 百分数 vs decimal 契约口径 | **不在本批改代码**；新登记 **P-025**（pending / P3），验收含 unit-aware 检查 + 测试 + 全量回归 | 当前主链路未消费；仓内调研原文即「登记为数据契约待办」。改代码属运行时变更，需 T1/T2 流程，不在 T3 小收口内夹带 |

### 2.1 不变式（本批验收依据）

- **INV-1**：本批零代码——不改任何 `.py` / `.toml` / `.yaml` / `.json` / 测试。
- **INV-2**：P 号单调、不复用；P-024 为收口批、P-025 为契约待办。
- **INV-3**：P-023 读数统一为 **16.80 s / 618.6 MB**，与证据 JSON 逐项一致。
- **INV-4**：P-023 CHECKLIST 提交状态与 git 事实一致。
- **INV-5**：ARCHITECTURE 行与 P-011 裁决一致，不再把已裁决项写成「待办」。
- **INV-6**：SPEC_COMPLIANCE 的 P 号范围覆盖 PROGRESS 当前最大号 P-025。

---

## 3. 实施记录（Step 5-6，零代码）

| 文件 | 位置 | 改动 |
|---|---|---|
| `docs/PROGRESS.md` | 待办表 P-023 后 | 新增 **P-024**（本批，done）与 **P-025**（stock_return 契约，pending）；P-023 行的 CHECKLIST 引用升 v1.3 |
| `docs/PROGRESS.md` | 优先级口径 P3 | 追加 **P-025** |
| `docs/SPEC_COMPLIANCE.md` | front-matter | `version` 1.1 → **1.2**；`date` → **2026-11-24** |
| `docs/SPEC_COMPLIANCE.md` | §1 / §4 | P 号范围 → **P-001 ~ P-025** |
| `spec/p023-tradability-memory-phase2/CHECKLIST.md` | front-matter / 状态行 | `version` 1.2 → **1.3**；状态行登记 v1.3 仅修正 §11 与 M-3/耗时读数 |
| 同上 | §2 N-13 / §8 A-4 / §11 | 16.86 → **16.80 s**；619.4 → **618.6 MB**；提交状态改为 **`17b981e` 已推送** |
| `docs/ARCHITECTURE.md` | §9.1 已知限制 | MissingTypeDiagnoser 行改为「P-011 裁决不修复 + 触发条件」并链接 P-011 §3.3 |
| `docs/PROJECT_STATUS.md` | §2 / §3 | 真值源范围 → P-001~P-025；P3 视图追加 P-025；§3 增 `stock_return` → P-025 行 |
| `spec/p024-ledger-contract-cleanup/SESSION.md` | 本文件 | T3 session（判档 / 事实 / 裁决 / 实施 / 验收） |

> **零代码自证**：`git diff --stat` 仅 5 个 `docs/` / `spec/` 文件（19 insertions / 16 deletions）；`git diff --name-only` 过滤 `*.py|*.toml|*.yaml|*.yml` 为 **0 行**。

---

## 4. 机械核验（Step 8）

| 检查 | 命令 / 方法 | 读数 |
|---|---|---|
| P 号范围残留 | `grep -rn "P-001 ~ P-011\|P-001 ~ P-009" docs/` | 仅 `docs/dev-log/DEV-LOG-2026-11-20.md` 历史记录 1 处（历史事实，不回改）；现行合规声明 **0 处** |
| P-023 旧读数残留 | `grep -n "619.4\|16.86\|先不提交\|保持工作区" spec/p023-tradability-memory-phase2/CHECKLIST.md` | **0 处** |
| P-024/P-025 登记 | `grep -n "P-024\|P-025" docs/PROGRESS.md` | 两行均存在；P-024=done、P-025=pending |
| 零代码 | `git diff --name-only` 过滤代码/配置后缀 | **0 个** |
| 改动范围 | `git diff --stat` | 5 files changed, 19 insertions(+), 16 deletions(-) |

---

## 5. E-TODO 出口（SPEC_COMPLIANCE §7，T3 简化执行）

| 步 | 结果 |
|---|---|
| E1 候选清单 | B-1（合规范围）/ B-2（提交状态）/ B-3（读数）/ B-4（契约口径） |
| E2 映射 | B-1→D1；B-2/B-3→D2；B-4→D4 + P-025；映射率 100% |
| E3 逐行状态 | P-024 → done；P-025 → pending；PROGRESS/PROJECT_STATUS 双写一致 |
| E4 证据链接 | 本文件 §1/§3/§4 + `out/tradability_memory_p023.json` + git `17b981e` |
| E5 双写 | PROGRESS P-024 行与本文件 §3 一致；P-025 行与本文件 D4 一致 |

---

## 6. Step 10 审计（T3 裁剪）

本批为 **T3 文档/账本级**，无代码、无门禁、无运行时变更；按 T3 裁剪不启独立 ADD 审计，以 §4 机械核验 + 证据 JSON / git 事实交叉复核替代。结论：**PASS（0×P1 / 0×P2 / 0×P3）**。

---

## 7. 结论与后续

- P-024 收口完成：合规范围、CHECKLIST 提交状态与读数、ARCHITECTURE 裁决指针、契约待办登记四项全部闭合。
- P-025 保持 **pending / P3**：需要决定是否修 `data_contract` 的 unit-aware 检查；若启动，按 T1/T2 批次另行立项，默认门禁行为变更须留痕并跑全量回归。
