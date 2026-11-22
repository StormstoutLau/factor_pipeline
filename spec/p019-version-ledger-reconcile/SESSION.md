# 批次 Session：台账 / 版本号对账（P-019）

---
id: p019-version-ledger-reconcile-SESSION
type: session
version: 1.1
status: verified
date: 2026-11-23
depends: []
upstream: null
---

> **批次**：P-019 台账 / 版本号对账
> **档位**：**T3**（Layer-0 纯文档 / 账本）
> **判档依据**（SPEC_PROCESS v1.7.0 §判档规则 1）：改动路径 = `docs/PROGRESS.md` / `docs/PROJECT_STATUS.md` / `CHANGELOG.md` / `spec/v399-p008-data-row-alignment/{CLOSURE_REPORT,CHECKLIST}.md`，与 `{scripts/, tests/, tools/, .pre-commit-config.yaml, .github/workflows/}` 交集为 **∅** → Layer-0 → T3。
> **裁剪理由**：无运行时 / 公开接口 / 门禁 / 真值源 / 契约变更（强制升级条款四条均未命中），故不建四件套，以**本 session + PROGRESS 行**交付。
> **Spec 步骤**：T3 五步决策流（判档 → 事实核对 → 裁决 → 实施 → 验收）；Step 10 独立只读审计。
> **回退点**：本批**未产生 git 提交**；回退 = `git checkout -- <下表文件>`（工作区四个文档 + 本文件）。

---

## 0. 决策流（五步）

| 步 | 动作 | 结论 | 证据出口 |
|---|---|---|---|
| 1 | 判档与登记 | T3；PROGRESS 先登记 P-019 行（立项即登记） | `docs/PROGRESS.md` P-019 行 |
| 2 | 事实核对 | 三处存量偏差 B-1 / B-2 / B-3 | §1 表格 |
| 3 | 裁决 | 方案 A（3.9.8 为发版号 + 文档勘误，不改写历史） | §3 |
| 4 | 实施 | 四个文档定点编辑（零代码） | §4 |
| 5 | 验收 | 机械核验 + 独立只读审计 | §5 + §7 |

---

## 1. 事实核对（Step 1-2，全部为仓内 E1）

> **F1/F2 口径**：本批**不使用外部来源**，全部判据来自仓内文件；按 SPEC_PROCESS v1.7.2 §契约取证字段形态，内部文件以 **`vX.Y` + 行号区间** 替代来源版本。
> **F3 降级链**：无降级（未使用检索通道）。
> **F4 引用验证表**：N/A——外部引用 0 条（<3 条亦不触发建表）。
> **F5 先失败记录**：N/A——无代码 / fixture 改动。

| # | 事实 | 读数 | 来源（版本 + 行号） |
|---|---|---|---|
| F-1 | 包版本四处锚点 | 全部 **3.9.8** | `pyproject.toml` L7；`__init__.py` L58；`config_v2.py` L371；`reporting.py` L40 |
| F-2 | 版本测试断言 | 全部 **3.9.8** | `tests/test_fix3_version_unification.py` L34；`tests/test_backtest/verify_fix3_manual.py` L21 |
| F-3 | 近期提交标签 | `3dabaff`=feat(v3.9.8) P-010；`11639db`=docs(v3.9.9) P-008 闭环；`9be0bf8`=docs(v3.9.9) P-008 哈希补记；`587b7f8`=feat(v3.9.9) P-008；`decc96c`=docs(v3.9.8) P-011 | `git log --oneline -8`（2026-11-23 读取） |
| F-4 | P-008 文档中的批次标签 | 3 处写 `v3.9.9` | CLOSURE_REPORT L4 / L131；CHECKLIST L274 |
| F-5 | CHANGELOG 顶部条目 | 依次 v3.9.8(P-010) / v3.9.7 / v3.9.6，**无 P-008 条目**，v3.9.8 条目只写 P-010 | `CHANGELOG.md` L3-L52（编辑前） |
| F-6 | PROJECT_STATUS §1 路线图 | 止于 **v3.9.7**，「当前在 v3.9.7」 | `docs/PROJECT_STATUS.md` L70-L71（编辑前） |
| F-7 | PROJECT_STATUS §2 优先级视图 | 仍列 P-008 / P-010 / P-011 为 P2 | `docs/PROJECT_STATUS.md` L128（编辑前） |
| F-8 | PROJECT_STATUS 阻塞项① | 「无分钟/逐笔数据 → c 系数不可实证校准」 | `docs/PROJECT_STATUS.md` L183（编辑前） |

**对账判读**：包版本从未出现 `3.9.9`（F-1/F-2 共 6 个锚点全为 3.9.8），说明 P-008 未 bump 版本、以 `v3.9.9` 作批次标签属**文档标签漂移**而非发版事实；F-5~F-8 为同一漂移在账本层的三处投影。

---

## 2. 偏差清单

- **B-1（版本标签）**：P-008 文档 3 处以 `v3.9.9` 作批次标签，与包版本 3.9.8 冲突。
- **B-2（发版记录）**：`CHANGELOG.md` 缺 P-008 条目，v3.9.8 条目未覆盖同期 P-008 / P-011，导致「3.9.8 到底包含什么」无单一答案。
- **B-3（状态视图）**：`PROJECT_STATUS.md` 路线图停在 v3.9.7、优先级视图包含已完成项（P-008/P-010/P-011）、阻塞项① 的**理由**（无分钟数据）已被 39 月分钟面板证伪。

---

## 3. 裁决（Step 3-4）

### 3.1 方案对比

| 方案 | 描述 | 优点 | 代价 / 缺点 | 裁决 |
|---|---|---|---|---|
| **A（选）** | 承认 **3.9.8 = 覆盖 P-011 + P-008 + P-010 的发版号**；P-008 文档加勘误并改标签；CHANGELOG v3.9.8 补两小节；刷新 PROJECT_STATUS | 与包版本事实一致；零代码、零历史改写；一次收口三处偏差 | 需在 P-008 文档留勘误痕迹（可接受，且是诚实做法） | **采纳** |
| B（否） | 补 bump 到 **3.9.9** 重新发版，使文档标签成真 | 标签字面自洽 | ~3.9.8 已发布且包版本已定；为纯文档批次再发一版会导致 3.9.9 无实质运行时内容，制造新歧义；还需改 6 个版本锚点 + 跑版本测试 | **否决** |
| C（否） | rebase / 改写 `587b7f8` 提交信息为 `feat(v3.9.8)` | 历史字面完美 | **已推送 origin/master**，改写需 force-push，破坏公共历史且不可逆；命中「破坏性契约 / 历史」红线 | **否决** |

### 3.2 决策依据（E1）

1. 包版本是**构建事实**，6 个锚点（F-1/F-2）一致为 3.9.8 → 以构建事实为准，标签服从事实，而非反向 bump。
2. 历史不可变性优先于字面整洁：`587b7f8` 的提交信息是历史事实的一部分，只能**追加解释**（勘误），不能**覆盖**。
3. 三个偏差同源（B-1 标签漂移 → B-2 记录缺失 → B-3 视图过期），一次对账即可收口，无需拆批。

### 3.3 不变式（INV，本批验收依据）

- **INV-1**：包版本 6 锚点保持 **3.9.8**，本批**不得**改动任何 `.toml` / `.py`。
- **INV-2**：git 历史不改写——不 rebase、不 amend、不 force-push；`587b7f8` 提交信息保留原文。
- **INV-3**：所有残留 `v3.9.9` 字样只能是「提交信息原文引用」或「勘误说明」，不得作为**现行批次标签**出现。
- **INV-4**：`CHANGELOG.md` v3.9.8 条目必须同时可检索到 P-008 与 P-011。
- **INV-5**：`PROJECT_STATUS.md` 路线图末行版本 = v3.9.8；优先级视图不再出现已完成项作为待办。

---

## 4. 实施记录（Step 5-6，零代码）

| 文件 | 位置 | 改动 |
|---|---|---|
| `docs/PROGRESS.md` | 待办表 P-018 后 | 新增 **P-019** 行（依据列含「T3：Layer-0 文档对账，零代码 / 零门禁」裁剪理由） |
| `CHANGELOG.md` | L3 标题 | 扩为「月聚类 CI + 粒度披露（P-010）/ 数据行数对齐（P-008）/ 存量待办裁决（P-011）」 |
| `CHANGELOG.md` | v3.9.8 条目内、v3.9.7 之前 | 新增「P-008 数据行数对齐」「P-011 存量待办裁决」两小节（含 3.9.8 发版口径与 E-1 指针） |
| `docs/PROJECT_STATUS.md` | 头部 L3 | 更新日期 2026-11-21 → **2026-11-23** |
| `docs/PROJECT_STATUS.md` | §1 路线图 | 新增 **v3.9.8** 行；「当前在」标记移至 v3.9.8 |
| `docs/PROJECT_STATUS.md` | §2 L128-L129 | 真值源范围 P-001~P-017 → **P-001~P-019**；优先级视图改为 P2 = P-006、P3 = P-009 / P-018 |
| `docs/PROJECT_STATUS.md` | 阻塞项① | 由「无数据 → 不可校准」改为「数据条件已解除、口径仍受限」+ 实测读数（c=2.910690、r²=0.5606 → c_effective 回退 0.5） |
| `spec/v399-p008-data-row-alignment/CLOSURE_REPORT.md` | L4 / §6 git 行 | 批次标签 v3.9.9 → **v3.9.8**；git 行标注提交信息笔误 |
| `spec/v399-p008-data-row-alignment/CLOSURE_REPORT.md` | 文末 | 新增 **§8 勘误与台账对账**（E-1 三行 + 发版口径 + 不改写历史声明） |
| `spec/v399-p008-data-row-alignment/CHECKLIST.md` | §11 git 行 | 标注提交信息标 feat(v3.9.9)、包版本实际 3.9.8，指向 E-1 |

> **零代码自证**：本批未编辑任何 `*.py` / `*.toml` / `*.yaml`；INV-1 由 §5 的版本锚点 grep 复核。

---

## 5. 机械核验（Step 8 一致性 + Step 10 三校验器兜底）

### 5.1 残留 `v3.9.9` 扫描（INV-3）

```
$ grep -rn "v3\.9\.9" --include=*.md .
CHANGELOG.md:27              ← 勘误说明（引用提交信息原文）
CLOSURE_REPORT.md:131        ← 勘误说明
CLOSURE_REPORT.md:145        ← 勘误说明（触发段）
CLOSURE_REPORT.md:149/150/151 ← 勘误表（原文列）
CHECKLIST.md:274             ← 勘误说明
PROGRESS.md:32               ← P-019 偏差描述
```

**判读**：**8 处**（不含本文件自身；本文件因撰写勘误说明必然出现该字样）全部归入「提交信息原文 / 勘误说明 / 偏差描述」三类；**作为现行批次标签的 0 处** → INV-3 **PASS**。

### 5.2 包版本锚点（INV-1）

```
$ grep -rn "3\.9\.8" --include=*.toml --include=*.py .
pyproject.toml:7 / __init__.py:58 / config_v2.py:371 / reporting.py:40
tests/test_fix3_version_unification.py:34 / tests/test_backtest/verify_fix3_manual.py:21
```

6 处全为 3.9.8，`3.9.9` 在代码/配置中 **0 处** → INV-1 **PASS**（且本批未触碰这些文件）。

### 5.3 CHANGELOG / PROJECT_STATUS 可检索性（INV-4 / INV-5）

- `CHANGELOG.md` v3.9.8 条目内可检索到 `P-008` 与 `P-011` 两个小节标题 → INV-4 **PASS**。
- `PROJECT_STATUS.md` 路线图末行版本 = `v3.9.8`，`← 当前在 v3.9.8` → INV-5 **PASS**；优先级视图已无 P-008/P-010/P-011。

### 5.4 git 历史（INV-2）

`git log --oneline -8` 读数与 F-3 一致，`587b7f8` / `9be0bf8` / `11639db` 提交信息一字未改；本批**未执行** commit / amend / rebase / push → INV-2 **PASS**。

---

## 6. E-TODO 出口（SPEC_COMPLIANCE §7，T3 简化执行）

| 步 | 结果 |
|---|---|
| E1 候选清单 | 本批无 RESEARCH/U 项、无 DESIGN 遗留；B-1~B-3 即全部候选 |
| E2 映射 | B-1 → P-008 勘误 E-1（已闭环）；B-2 → CHANGELOG 补记（已闭环）；B-3 → PROJECT_STATUS 三处刷新（已闭环）；映射率 100% |
| E3 逐行状态 | 本批无 CHECKLIST；PROGRESS P-019 行由 pending → done |
| E4 证据链接 | 本文件 §1/§4/§5 提供链接与读数 |
| E5 双写 | PROGRESS P-019 行与本文件 §7 结论一致 |

---

## 7. Step 10 独立审计

**执行者**：独立只读子代理（Explore，2026-11-23），只读取证、未改任何文件。
**结论**：**PASS_WITH_FIXES**——0×P1 / 0×P2 / 3×P3（后经复核，三条均为**已实现事实的复述**，非缺陷）。INV-1~INV-5 全部 **PASS**。

| # | 级别 | 位置 | 事实 | 处置 |
|---|---|---|---|---|
| A-1 | P2 | 本文件 §7 | 审计前本节为待回填占位 | 已回填本节，非缺陷 |
| A-2 | P3 | 本文件 §5.1 | 残留 `v3.9.9` 8 处（不含本文件），全为勘误 / 提交信息原文引用 | 符合 INV-3，**不修** |
| A-3 | P3 | 本文件 §5.2-§5.3 | 6 锚点均 3.9.8；CHANGELOG 可检索 P-008 / P-011 | 符合 INV-1 / INV-4，**不修** |

**交叉核对**：`PROJECT_STATUS.md` 阻塞项① 的 `c=2.910690` / `r²=0.5606` / `c_effective` 回退 0.5 / 月聚类 CI `[2.888499, 2.935933]` 与 `spec/p010-granularity-bias/IMPLEMENTATION.md` 及 `PROGRESS.md` P-010 行**一致**。

**审计口径**：D-002（审计只取证、不修复）；本批无回修项，无新增 backlog。
